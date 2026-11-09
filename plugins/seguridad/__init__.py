# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Seguridad de descargas e integridad (``zc.seguridad``, diseño 2.0, 11.19; bloque P4).

Ayuda a decidir si un archivo es de fiar: firma Authenticode (también como
columna e información del elemento), comparar su suma con la del
portapapeles, analizarlo con Microsoft Defender, buscar su hash en VirusTotal
(solo con la clave propia de la persona y solo el hash, nunca el archivo) y ver
o quitar la marca de la Web.

Privacidad: lo único que sale del equipo es el SHA-256 que se envía a
VirusTotal cuando la persona lo pide, y la primera vez se avisa de ello.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_seguridad")

#: Orígenes remotos cuyas copias se analizan con Defender si ``analizar_descargas`` está activa.
ESQUEMAS_REMOTOS = frozenset({"ftp", "ftps", "sftp", "nube", "synology", "webdav"})
SECRETO_VT = "clave_virustotal"


def _ruta_local(proveedor: api.Proveedor | None, entrada: api.Entrada) -> str | None:
	if entrada is None or entrada.es_superior:
		return None
	if proveedor is None:
		return entrada.ruta
	return proveedor.ruta_local(entrada.ruta)


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		for orden in ("firma", "comparar_suma", "defender", "virustotal", "quitar_marca"):
			zc.ordenes.manejador(orden, getattr(self, orden))
		zc.columnas.extractor("firma", self.columna_firma)
		zc.columnas.extractor("marca_web", self.columna_marca)
		zc.info.lineas(self.lineas_info)
		zc.eventos.suscribir("al_terminar_operacion", self._al_terminar_operacion)
		try:
			zc.preferencias.dialogo(self.dialogo_clave)
		except api.NoAdmitido:
			log.debug("Sin interfaz: el diálogo de la clave de VirusTotal se registra al abrir la ventana")

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			self.zc.ui.crear_campo  # noqa: B018 - comprueba que hay interfaz (sin ella, NoAdmitido)
		except api.NoAdmitido:
			return []
		from . import dialogos

		return [dialogos.DialogoClave(padre, self.zc, "")]

	# ── Utilidades ──────────────────────────────────────────────────────────

	def _archivo_cursor(self, ctx: api.ContextoComplemento) -> tuple[api.Entrada, str] | None:
		panel = ctx.objetivo
		entrada = panel.cursor()
		ruta = _ruta_local(panel.proveedor, entrada) if entrada is not None else None
		if entrada is None or entrada.es_carpeta or not ruta:
			self.zc.anunciar(_("Elija un archivo del disco"), api.RESULTADO)
			return None
		return entrada, ruta

	def _fallo(self, error: BaseException) -> None:
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
		if isinstance(error, api.Cancelado):
			return
		self.zc.anunciar(mensaje, api.ESENCIAL)

	# ── Órdenes ─────────────────────────────────────────────────────────────

	def firma(self, ctx: api.ContextoComplemento) -> None:
		elegido = self._archivo_cursor(ctx)
		if elegido is None:
			return
		from . import firma

		def listo(resultado: firma.ResultadoFirma) -> None:
			if resultado.sospechosa:
				self.zc.sonidos.sonar("sin_firma")
			self.zc.anunciar(resultado.texto, api.RESULTADO)

		self.zc.tareas.enviar(lambda _t: firma.verificar(elegido[1]), al_terminar=listo, al_fallar=self._fallo, nombre="zc.seguridad:firma")

	def comparar_suma(self, ctx: api.ContextoComplemento) -> None:
		elegido = self._archivo_cursor(ctx)
		if elegido is None:
			return
		from . import comprobaciones

		texto = self._texto_portapapeles()
		esperada = comprobaciones.extraer_suma(texto or "")
		algoritmo = esperada[0] if esperada else str(self.zc.config.obtener("algoritmo", "sha256"))
		nombre = comprobaciones.NOMBRES.get(algoritmo, algoritmo)
		entrada, ruta = elegido
		self.zc.anunciar(_("Calculando el {a} de {n}...").format(a=nombre, n=entrada.nombre), api.DETALLE)

		def calcular(tarea: Any) -> str:
			with open(ruta, "rb") as lector:
				return comprobaciones.calcular_suma(lector, algoritmo, lambda: api.comprobar(tarea.token))

		def listo(suma: str) -> None:
			if esperada is None:
				texto_final = _("El portapapeles no tiene una suma. {a} de {n}: {s}").format(a=nombre, n=entrada.nombre, s=suma)
			elif suma == esperada[1]:
				texto_final = _("Coincide con el {a} del portapapeles").format(a=nombre)
			else:
				self.zc.sonidos.sonar("amenaza")
				texto_final = _("No coincide con el {a} del portapapeles. El del archivo es {s}").format(a=nombre, s=suma)
			self.zc.anunciar(texto_final, api.RESULTADO, completo=texto_final)

		self.zc.tareas.enviar(calcular, al_terminar=listo, al_fallar=self._fallo, nombre="zc.seguridad:suma")

	def _texto_portapapeles(self) -> str | None:
		"""Texto del portapapeles [interfaz]."""
		import wx

		if not wx.TheClipboard.Open():
			return None
		try:
			if not wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_UNICODETEXT)):
				return None
			datos = wx.TextDataObject()
			return datos.GetText() if wx.TheClipboard.GetData(datos) else None
		finally:
			wx.TheClipboard.Close()

	def defender(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		rutas = [r for r in (_ruta_local(panel.proveedor, e) for e in panel.elementos_trabajo()) if r]
		if not rutas:
			self.zc.anunciar(_("Elija archivos o carpetas del disco"), api.RESULTADO)
			return
		self.zc.anunciar(_("Analizando con Defender..."), api.DETALLE)
		self.zc.tareas.enviar(lambda tarea: self.analizar_con_defender(rutas, tarea), al_terminar=self._anunciar_defender,
			al_fallar=self._fallo, nombre="zc.seguridad:defender")

	def analizar_con_defender(self, rutas: list[str], cancelacion: Any = None) -> Any:
		"""Analiza cada ruta con ``MpCmdRun.exe`` y junta las amenazas [trabajo]."""
		from . import comprobaciones

		mpcmdrun = comprobaciones.ruta_mpcmdrun()
		if not mpcmdrun:
			raise api.NoAdmitido(_("No se encuentra Microsoft Defender en este equipo"))
		amenazas: list[str] = []
		for ruta in rutas:
			resultado = self.zc.ejecutar_programa(comprobaciones.argumentos_defender(mpcmdrun, ruta), tiempo_s=1800,
				cancelacion=getattr(cancelacion, "token", cancelacion))
			if resultado.cancelado:
				raise api.Cancelado()
			salida = resultado.salida + resultado.errores
			texto = salida.decode("utf-16-le", errors="replace") if b"\x00" in salida[:200] else salida.decode("mbcs", errors="replace")
			interpretado = comprobaciones.interpretar_defender(texto, resultado.codigo)
			if interpretado.error:
				return interpretado
			amenazas.extend(interpretado.amenazas)
		return comprobaciones.ResultadoDefender(tuple(amenazas), analizado=True)

	def _anunciar_defender(self, resultado: Any) -> None:
		if resultado.amenazas:
			self.zc.sonidos.sonar("amenaza")
			self.zc.anunciar(resultado.texto, api.ESENCIAL, completo=resultado.texto)
		else:
			self.zc.anunciar(resultado.texto, api.RESULTADO)

	def virustotal(self, ctx: api.ContextoComplemento) -> None:
		elegido = self._archivo_cursor(ctx)
		if elegido is None:
			return
		clave = self.zc.secretos.obtener(SECRETO_VT)
		if not clave:
			clave = self._pedir_clave()
			if not clave:
				return
		if not self.zc.config.obtener("aviso_virustotal", False):
			if not self.zc.ui.confirmar(_("Para buscar en VirusTotal se envía a www.virustotal.com la suma SHA-256 del archivo, "
					"nunca el archivo. VirusTotal es un servicio de Google con sus propias condiciones. ¿Continuar?"),
					_("Buscar en VirusTotal")):
				return
			self.zc.config.establecer("aviso_virustotal", True)
		entrada, ruta = elegido
		self.zc.anunciar(_("Consultando VirusTotal..."), api.DETALLE)

		def consultar(tarea: Any) -> Any:
			from . import comprobaciones

			with open(ruta, "rb") as lector:
				suma = comprobaciones.calcular_suma(lector, "sha256", lambda: api.comprobar(tarea.token))
			return self.consultar_virustotal(suma, clave)

		def listo(resultado: Any) -> None:
			if resultado.amenaza:
				self.zc.sonidos.sonar("amenaza")
			self.zc.anunciar(resultado.texto, api.ESENCIAL if resultado.amenaza else api.RESULTADO, completo=resultado.texto)

		self.zc.tareas.enviar(consultar, al_terminar=listo, al_fallar=self._fallo, nombre="zc.seguridad:virustotal")

	def consultar_virustotal(self, sha256: str, clave: str) -> Any:
		"""Busca el hash (solo el hash) en VirusTotal [trabajo]."""
		from . import comprobaciones

		try:
			respuesta = self.zc.red.obtener(comprobaciones.url_virustotal(sha256), cabeceras={"x-apikey": clave}, tiempo_s=30)
		except api.ErrorRed as error:
			estado = getattr(error.__cause__, "estado", 0)
			if estado == 404:
				return comprobaciones.ResultadoVirusTotal(False)
			if estado in (401, 403):
				raise api.ErrorAcceso(_("VirusTotal no acepta la clave. Revísela en la configuración del complemento.")) from error
			if estado == 429:
				raise api.ErrorRed(_("Ha llegado al límite de consultas de VirusTotal de su clave. Inténtelo más tarde.")) from error
			raise
		return comprobaciones.interpretar_virustotal(respuesta.json())

	def _pedir_clave(self) -> str | None:
		clave = self.zc.ui.pedir_texto(_("Clave de la API de &VirusTotal:"), _("Buscar en VirusTotal"), "", contrasena=True,
			ayuda=_("Su clave personal de VirusTotal (en su perfil de virustotal.com, «API key»). Se guarda cifrada en este equipo."))
		if not clave or not clave.strip():
			return None
		clave = clave.strip()
		self.zc.secretos.guardar(SECRETO_VT, clave)
		return clave

	def dialogo_clave(self, padre: Any) -> None:
		"""Configuración avanzada: poner, cambiar u olvidar la clave de VirusTotal [interfaz]."""
		from . import dialogos

		dialogos.configurar_clave(self.zc, padre, SECRETO_VT)

	def quitar_marca(self, ctx: api.ContextoComplemento) -> None:
		from . import comprobaciones

		panel = ctx.objetivo
		marcados = []
		for entrada in panel.elementos_trabajo():
			ruta = _ruta_local(panel.proveedor, entrada)
			if ruta and not entrada.es_carpeta and comprobaciones.leer_marca(ruta) is not None:
				marcados.append(ruta)
		if not marcados:
			self.zc.anunciar(_("Ninguno de los elementos tiene la marca de la Web"), api.RESULTADO)
			return
		que = os.path.basename(marcados[0]) if len(marcados) == 1 else _n("{n} archivo", "{n} archivos", len(marcados)).format(n=len(marcados))
		if not self.zc.ui.confirmar(_("¿Quitar la marca de la Web de {q}? Windows dejará de avisar de que vienen de Internet "
				"al abrirlos. Hágalo solo si confía en su origen.").format(q=que), _("Quitar la marca de la Web"), peligroso=True):
			return
		quitadas = 0
		for ruta in marcados:
			try:
				quitadas += comprobaciones.quitar_marca(ruta)
			except OSError as error:
				self.zc.anunciar(_("No se pudo quitar la marca de {n}: {e}").format(n=os.path.basename(ruta), e=error.strerror),
					api.ESENCIAL)
		panel.refrescar()
		self.zc.anunciar(_n("Marca quitada de {n} archivo", "Marca quitada de {n} archivos", quitadas).format(n=quitadas), api.RESULTADO)

	# ── Columnas e información (en hilos) ───────────────────────────────────

	def columna_firma(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		from . import firma

		if entrada.es_carpeta or not firma.admite_firma(entrada.nombre):
			return ""
		ruta = _ruta_local(proveedor, entrada)
		return firma.verificar(ruta).corto if ruta else None

	def columna_marca(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		from . import comprobaciones

		if entrada.es_carpeta:
			return ""
		ruta = _ruta_local(proveedor, entrada)
		if not ruta:
			return None
		marca = comprobaciones.leer_marca(ruta)
		return marca.texto if marca is not None else ""

	def lineas_info(self, entrada: api.Entrada, proveedor: api.Proveedor) -> list[str]:
		from . import comprobaciones, firma

		ruta = _ruta_local(proveedor, entrada)
		if not ruta or entrada.es_carpeta:
			return []
		lineas = []
		if firma.admite_firma(entrada.nombre):
			lineas.append(_("Firma: {t}").format(t=firma.verificar(ruta).texto))
			lineas.extend(comprobaciones.lineas_ejecutable(comprobaciones.datos_ejecutable(ruta)))
		marca = comprobaciones.leer_marca(ruta)
		if marca is not None:
			lineas.append(_("Origen: {d}").format(d=marca.descripcion))
		return lineas

	# ── Analizar lo descargado ──────────────────────────────────────────────

	def _al_terminar_operacion(self, operacion: Any = None, **_datos: Any) -> None:
		if operacion is None or not self.zc.config.obtener("analizar_descargas", False):
			return
		rutas = self.rutas_descargadas(operacion)
		if rutas:
			self.zc.tareas.enviar(lambda tarea: self.analizar_con_defender(rutas, tarea), al_terminar=self._avisar_descarga,
				al_fallar=lambda e: log.info("No se analizó lo descargado: %s", e), nombre="zc.seguridad:descargas")

	@staticmethod
	def rutas_descargadas(operacion: Any) -> list[str]:
		"""Destinos locales de una copia o movimiento desde FTP, SFTP o una nube."""
		origen = getattr(operacion, "origen", None)
		destino = getattr(operacion, "destino", None)
		if getattr(origen, "esquema", "") not in ESQUEMAS_REMOTOS or getattr(destino, "esquema", "") != "local":
			return []
		pares = getattr(operacion, "pares_hechos", lambda: [])()
		return [str(d) for _o, d in pares]

	def _avisar_descarga(self, resultado: Any) -> None:
		if resultado.amenazas:
			self.zc.sonidos.sonar("amenaza")
			self.zc.anunciar(_("En lo descargado: {t}").format(t=resultado.texto), api.ESENCIAL)
		elif resultado.error:
			self.zc.anunciar(resultado.texto, api.DETALLE)
		else:
			self.zc.anunciar(_("Lo descargado está limpio según Defender"), api.DETALLE)
