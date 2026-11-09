# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Monitor de carpetas y reglas automáticas (zc.monitor, diseño 2.0, 11.18; bloque P5).

Se activa siempre al arrancar (la activación es estática, 11.0), pero sin
carpetas vigiladas ``activar`` vuelve enseguida sin abrir ningún vigilante.

Hilos: uno por carpeta (``ReadDirectoryChangesW``) y un revisor que decide
cuándo un archivo ha terminado de llegar y le aplica las reglas (mover,
copiar, renombrar, extraer, etiquetar). Lo que necesita la interfaz (anunciar,
sonar, ejecutar una orden, registrar el deshacer) llega a su hilo por el
evento propio ``zc.monitor:llegada`` del bus.
"""

from __future__ import annotations

import os
import time

from app.plugins import api

EVENTO_LLEGADA = "llegada"
NIVELES = {"normal": api.NORMAL, "resultado": api.RESULTADO}


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.pausado = False
		self._vigilantes: list = []
		self._revisor = None
		self.estabilidad = None
		self._registro = None
		zc.ordenes.manejador("reglas", self.dialogo_reglas)
		zc.ordenes.manejador("pausar", self.pausar)
		zc.ordenes.estado("pausar", lambda _ctx: self.pausado)
		zc.ordenes.manejador("registro", self.dialogo_registro)
		zc.exportar("operacion_de_reglas", self.operacion_de_reglas)
		self._cancelar = [zc.eventos.suscribir(f"{zc.id}:{EVENTO_LLEGADA}", self._al_llegar_interfaz),
			zc.config.suscribir(self._al_cambiar_config)]
		if self.carpetas():
			self.arrancar()

	def desactivar(self) -> None:
		self.detener()
		for cancelar in getattr(self, "_cancelar", []):
			cancelar()

	# ── Configuración ────────────────────────────────────────────────────────

	def carpetas(self) -> list[str]:
		return [str(c) for c in self.zc.config.obtener("carpetas", []) or [] if str(c).strip()]

	def reglas(self):
		from . import reglas

		return reglas.leer_reglas(self.zc.config.obtener("reglas", []) or [])

	@property
	def registro(self):
		if self._registro is None:
			from . import reglas

			self._registro = reglas.Registro(self.zc.datos)
		return self._registro

	def _al_cambiar_config(self, clave: str, _anterior, _nuevo) -> None:
		if clave in ("carpetas", "retraso_s") and not self.pausado:
			self.arrancar()

	# ── Vigilancia ───────────────────────────────────────────────────────────

	def arrancar(self) -> list[str]:
		"""(Re)abre los vigilantes de las carpetas configuradas. Devuelve los problemas encontrados."""
		from . import vigilante

		self.detener()
		carpetas = self.carpetas()
		if not carpetas or self.pausado:
			return []
		problemas = []
		self.estabilidad = vigilante.Estabilidad(float(self.zc.config.obtener("retraso_s", 5)))
		for carpeta in carpetas:
			if not os.path.isdir(carpeta):
				problemas.append(f"La carpeta vigilada {carpeta} no existe")
				continue
			hilo = vigilante.Vigilante(carpeta, self.estabilidad.notificar)
			hilo.start()
			self._vigilantes.append(hilo)
		self._revisor = vigilante.Revisor(self.estabilidad, self.al_llegar)
		self._revisor.start()
		for problema in problemas:
			self.zc.registro.warning(problema)
		return problemas

	def detener(self) -> None:
		for hilo in self._vigilantes:
			hilo.detener()
		if self._revisor is not None:
			self._revisor.detener()
		for hilo in [*self._vigilantes, *([self._revisor] if self._revisor else [])]:
			hilo.join(0.5)
		self._vigilantes, self._revisor = [], None

	def esperar_listo(self, tiempo_s: float = 5) -> bool:
		"""Espera a que todos los vigilantes estén leyendo (para las pruebas)."""
		return all(h.listo.wait(tiempo_s) for h in self._vigilantes)

	# ── Llegada de un archivo (hilo del revisor) ─────────────────────────────

	def _herramientas(self):
		from . import reglas

		return reglas.Herramientas(evaluar_mascara=self._evaluar_mascara, etiquetar=self._etiquetar)

	def _evaluar_mascara(self, mascara: str, ruta: str) -> str:
		"""[trabajo] Nombre nuevo con las máscaras del renombrado múltiple (y las de los complementos)."""
		proveedor, _carpeta = self.zc.vfs.resolver(os.path.dirname(ruta))
		return self.zc.renombrado.evaluar(mascara, proveedor.info(ruta), proveedor)

	def _etiquetar(self, ruta: str, etiqueta: str) -> None:
		"""[trabajo] Etiqueta con ``zc.notas`` (11.0); sin ese complemento, error explicado."""
		from . import reglas

		notas = self.zc.complemento("zc.notas")
		funcion = getattr(notas, "etiquetar", None) if notas is not None else None
		if funcion is None:
			raise reglas.ErrorRegla("Para etiquetar hace falta el complemento Notas, comentarios y etiquetas")
		funcion(ruta, etiqueta)

	def _carpeta_vigilada(self, ruta: str) -> str:
		padre = os.path.normcase(os.path.dirname(ruta))
		return next((c for c in self.carpetas() if os.path.normcase(os.path.normpath(c)) == padre), os.path.dirname(ruta))

	def al_llegar(self, ruta: str) -> None:
		"""[hilo del revisor] Un archivo terminó de llegar: aplica la primera regla y avisa a la interfaz."""
		from . import reglas

		if self.pausado:
			return
		carpeta = self._carpeta_vigilada(ruta)
		try:
			info = os.stat(ruta)
		except OSError:
			return
		regla = reglas.primera_que_coincide(self.reglas(), ruta, carpeta, info.st_size, info.st_mtime)
		hecho = None
		if regla is not None:
			try:
				hecho = reglas.aplicar(regla, ruta, self._herramientas())
			except reglas.ErrorRegla as error:
				hecho = reglas.Hecho(regla.nombre, regla.accion, ruta, str(error), ok=False)
			if hecho.nueva_ruta and hecho.nueva_ruta != ruta and self.estabilidad is not None:
				self.estabilidad.ignorar(hecho.nueva_ruta)
			self.registro.apuntar(carpeta, hecho)
		self.zc.eventos.emitir(EVENTO_LLEGADA, ruta=ruta, carpeta=carpeta, tamano=info.st_size, hecho=hecho)

	# ── En el hilo de la interfaz ────────────────────────────────────────────

	def texto_llegada(self, ruta: str, carpeta: str, tamano: int, hecho) -> str:
		nombre_carpeta = os.path.basename(carpeta.rstrip("\\/")) or carpeta
		texto = f"Nuevo en {nombre_carpeta}: {os.path.basename(ruta)}, {api.formato.tamano_legible(tamano)}"
		if hecho is not None:
			if hecho.ok:
				texto += f". Regla {hecho.regla}: {hecho.texto}"
			else:
				texto += f". La regla {hecho.regla} falló: {hecho.texto}"
		return texto

	def _al_llegar_interfaz(self, ruta: str = "", carpeta: str = "", tamano: int = 0, hecho=None, **_datos) -> None:
		nivel = str(self.zc.config.obtener("nivel_anuncio", "resultado"))
		self.zc.sonidos.sonar("archivo_nuevo")
		if hecho is not None and hecho.ok:
			self.zc.sonidos.sonar("regla_aplicada")
		texto = self.texto_llegada(ruta, carpeta, tamano, hecho)
		if hecho is not None and not hecho.ok:
			self.zc.anunciar(texto, api.ESENCIAL)
		elif nivel in NIVELES:
			self.zc.anunciar(texto, NIVELES[nivel])
		if hecho is None or not hecho.ok:
			return
		if hecho.orden:
			try:
				self.zc.ejecutar_orden(hecho.orden, argumento=hecho.archivo)
			except api.NoAdmitido as error:
				self.zc.anunciar(f"No se pudo ejecutar {hecho.orden}: {error}", api.ESENCIAL)
		self._registrar_deshacer(hecho)

	def _registrar_deshacer(self, hecho) -> None:
		"""Además del registro propio, la acción entra en Deshacer del núcleo (si es del mismo disco)."""
		datos = hecho.deshacer or {}
		origen, destino = datos.get("origen", ""), datos.get("destino", "")
		if not destino:
			return
		try:
			if datos.get("tipo") == "copiar":
				info = os.stat(destino)
				paso = api.Paso("a_papelera", destino, tamano=info.st_size, modificado=info.st_mtime)
			elif os.path.splitdrive(origen)[0].casefold() == os.path.splitdrive(destino)[0].casefold():
				paso = api.Paso("renombrar", destino, origen)
			else:
				return
			self.zc.deshacer.registrar(api.AccionDeshacer(f"Monitor: {hecho.regla}", [paso]))
		except (OSError, api.NoAdmitido):
			self.zc.registro.debug("No se registró el deshacer de %s", destino, exc_info=True)

	# ── Contrato con el programador ──────────────────────────────────────────

	def operacion_de_reglas(self, carpeta: str) -> api.Operacion:
		"""La operación que aplica las reglas a lo que ya hay en ``carpeta``."""
		from . import operacion

		al_aplicar = self.estabilidad.ignorar if self.estabilidad is not None else None
		return operacion.OperacionReglas(carpeta, self.reglas(), self.registro, self._herramientas(), al_aplicar)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def pausar(self, ctx: api.ContextoComplemento) -> None:
		self.pausado = not self.pausado
		if self.pausado:
			self.detener()
			ctx.anunciar("Monitor de carpetas en pausa", api.RESULTADO)
			return
		problemas = self.arrancar()
		if not self.carpetas():
			ctx.anunciar("Monitor de carpetas reanudado; no hay carpetas vigiladas", api.RESULTADO)
		else:
			ctx.anunciar("Monitor de carpetas reanudado" + (". " + ". ".join(problemas) if problemas else ""), api.RESULTADO)

	def dialogo_reglas(self, ctx: api.ContextoComplemento) -> None:
		from . import reglas, ventana

		dialogo = ventana.DialogoMonitor(self, None, propuesta=ctx.activo.ruta if ctx.activo.proveedor.esquema == "local" else "")
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ventana.wx.ID_OK:
				return
			carpetas, lista = dialogo.valores()
		finally:
			dialogo.Destroy()
		self.zc.config.establecer_varias({"carpetas": carpetas, "reglas": reglas.a_lista(lista)})
		problemas = self.arrancar() if not self.pausado else []
		estado = "en pausa" if self.pausado else f"vigilando {len(carpetas)} carpetas" if carpetas else "sin carpetas vigiladas"
		self.zc.anunciar(f"Monitor guardado: {estado}, {len(lista)} reglas" + (". " + ". ".join(problemas) if problemas else ""),
			api.RESULTADO)

	def dialogo_registro(self, ctx: api.ContextoComplemento) -> None:
		from . import ventana

		dialogo = ventana.DialogoRegistro(self, None)
		try:
			self.zc.ui.mostrar_modal(dialogo)
		finally:
			dialogo.Destroy()

	def deshacer_ultimo(self) -> str:
		from . import reglas

		try:
			texto = self.registro.deshacer_ultimo()
		except reglas.ErrorRegla as error:
			texto = str(error)
		self.zc.anunciar(texto, api.RESULTADO)
		return texto

	def simular_texto(self, carpetas: list[str], lista) -> str:
		"""[hilo] Texto de la simulación de ``lista`` sobre lo que ya hay en ``carpetas``."""
		from . import reglas

		lineas = []
		for carpeta in carpetas:
			try:
				hechos = reglas.simular(lista, carpeta, time.time())
			except reglas.ErrorRegla as error:
				lineas.append(str(error))
				continue
			lineas.append(f"{carpeta}: {len(hechos)} archivos afectados" if len(hechos) != 1 else f"{carpeta}: 1 archivo afectado")
			lineas.extend(f"  {os.path.basename(h.archivo)}: regla {h.regla}. {h.texto}" for h in hechos)
		return "\n".join(lineas) or "No hay carpetas vigiladas que simular"

	def ventanas_para_revisar(self, padre):
		from . import reglas, ventana

		try:
			return [ventana.DialogoMonitor(self, padre), ventana.DialogoRegla(self.zc, padre, reglas.Regla("Ejemplo"), []),
				ventana.DialogoRegistro(self, padre)]
		except api.NoAdmitido:
			return []
