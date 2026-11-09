# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Notas, comentarios y etiquetas (zc.notas, diseño 2.0, 11.14).

- Ctrl+N edita el comentario del elemento del cursor o, en «..», la nota de
  la carpeta. Los comentarios van en ``descript.ion`` (compatible con Total
  Commander y Double Commander) o en la base central ``datos/notas.db``.
- Al entrar en una carpeta con nota se dice «Esta carpeta tiene una nota» y
  suena ``zc.notas:nota_carpeta``; la orden «Leer la nota de la carpeta» la lee.
- Etiquetas con nombre y color, siempre dichas con su color en texto.
- Columnas «Comentario» y «Etiquetas»; búsqueda por etiqueta o comentario.
- Los comentarios y las etiquetas viajan al copiar y mover dentro de
  zCommander (``al_terminar_operacion`` con ``pares_hechos``).
- Exporta ``etiquetar(ruta, etiqueta)`` para el monitor de carpetas (11.0).

Se activa con el primer cambio de carpeta (``evento:al_cambiar_carpeta``) para
poder anunciar las notas; ``activar()`` solo registra funciones.
"""

from __future__ import annotations

import os
from typing import Any

from app.plugins import api

from . import motor

_ = api.traduccion("zc.notas")[0]


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.almacen = motor.Almacen(lambda: zc.datos / "notas.db", lambda: str(zc.config.obtener("almacen")))
		self._ultima: dict[str, str] = {}
		zc.ordenes.manejador("comentario", self.comentario)
		zc.ordenes.manejador("leer_nota", self.leer_nota)
		zc.ordenes.manejador("etiquetas", self.etiquetas)
		zc.ordenes.manejador("buscar", self.buscar)
		zc.columnas.extractor("comentario", self._columna_comentario)
		zc.columnas.extractor("etiquetas", self._columna_etiquetas)
		zc.eventos.suscribir("al_cambiar_carpeta", self._al_cambiar_carpeta)
		zc.eventos.suscribir("al_terminar_operacion", self._al_terminar_operacion)
		zc.exportar("etiquetar", self.etiquetar)

	# Funciones exportadas (11.0) -------------------------------------------------

	def etiquetar(self, ruta: str, etiqueta: str) -> None:
		"""Pone ``etiqueta`` a ``ruta`` (la crea, sin color, si no existe). Se puede llamar desde cualquier hilo."""
		etiqueta = str(etiqueta).strip()
		if not etiqueta:
			return
		definidas = self._definidas()
		if not any(d["nombre"].casefold() == etiqueta.casefold() for d in definidas):
			self.zc.config.establecer("etiquetas", [*definidas, {"nombre": etiqueta, "color": ""}])
		self.almacen.etiquetar(ruta, etiqueta)

	def _definidas(self) -> list[dict]:
		valor = self.zc.config.obtener("etiquetas")
		return [dict(d) for d in (valor or []) if isinstance(d, dict) and str(d.get("nombre", "")).strip()]

	# Columnas (en un hilo del complemento) ---------------------------------------

	def _ruta_local(self, entrada: api.Entrada, proveedor: api.Proveedor) -> str | None:
		if entrada.es_superior:
			return None
		return proveedor.ruta_local(entrada.ruta)

	def _columna_comentario(self, entrada: api.Entrada, proveedor: api.Proveedor, _cancelacion: Any) -> str | None:
		ruta = self._ruta_local(entrada, proveedor)
		return motor.primera_linea(self.almacen.comentario(ruta)) if ruta else None

	def _columna_etiquetas(self, entrada: api.Entrada, proveedor: api.Proveedor, _cancelacion: Any) -> str | None:
		ruta = self._ruta_local(entrada, proveedor)
		return motor.texto_etiquetas(self.almacen.etiquetas(ruta), self._definidas()) if ruta else None

	# Órdenes -------------------------------------------------------------------

	def comentario(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		panel = ctx.activo
		cursor = panel.cursor()
		objetivo = cursor.ruta if cursor is not None else panel.ruta
		ruta = panel.proveedor.ruta_local(objetivo) if objetivo else None
		if not ruta:
			self.zc.anunciar(_("Los comentarios solo se pueden poner en el disco"), api.ESENCIAL)
			return
		es_nota = cursor is None
		nombre = os.path.basename(ruta.rstrip("\\/")) or ruta
		dialogo = ui.DialogoComentario(None, self.zc, nombre, self.almacen.comentario(ruta), es_nota)
		try:
			respuesta = self.zc.ui.mostrar_modal(dialogo)
			texto = dialogo.texto()
		finally:
			dialogo.Destroy()
		if respuesta == ui.ID_QUITAR:
			texto = ""
		elif respuesta != ui.wx.ID_OK:
			return
		try:
			destino = self.almacen.fijar_comentario(ruta, texto)
		except Exception as error:  # noqa: BLE001 - sqlite3 y el disco: se dice y se registra
			self.zc.registro.exception("No se pudo guardar el comentario de %s", ruta)
			self.zc.anunciar(_("No se pudo guardar: {e}").format(e=error), api.ESENCIAL)
			return
		if texto.strip():
			mensaje = _("Nota guardada") if es_nota else _("Comentario guardado")
			if destino == "base_central" and self.zc.config.obtener("almacen") == "descript_ion":
				mensaje += _(" en la base de zCommander: aquí no se puede escribir descript.ion")
		else:
			mensaje = _("Nota quitada") if es_nota else _("Comentario quitado")
		self.zc.anunciar(mensaje, api.RESULTADO)
		# El archivo no cambia (ni tamaño ni fecha): sin esto la columna «Comentario» seguiría con el valor viejo.
		self.zc.columnas.invalidar([objetivo, ruta])
		panel.refrescar()

	def leer_nota(self, ctx: api.ContextoComplemento) -> None:
		ruta = ctx.activo.proveedor.ruta_local(ctx.activo.ruta) if ctx.activo.ruta else None
		nota = self.almacen.comentario(ruta) if ruta else ""
		if nota:
			self.zc.anunciar(nota, api.RESULTADO)
		else:
			self.zc.anunciar(_("Esta carpeta no tiene nota"), api.RESULTADO)

	def etiquetas(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		panel = ctx.activo
		rutas = [r for r in (panel.proveedor.ruta_local(e.ruta) for e in panel.elementos_trabajo()) if r]
		if not rutas:
			self.zc.anunciar(_("No hay elementos del disco a los que poner etiquetas"), api.ESENCIAL)
			return
		actuales = [set(self.almacen.etiquetas(r)) for r in rutas]
		comunes = set.intersection(*actuales) if actuales else set()
		dialogo = ui.DialogoEtiquetas(None, self.zc, self._definidas(), comunes, len(rutas))
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ui.wx.ID_OK:
				return
			elegidas, definidas = dialogo.elegidas(), dialogo.definidas
		finally:
			dialogo.Destroy()
		if definidas != self._definidas():
			self.zc.config.establecer("etiquetas", definidas)
		for ruta, tenia in zip(rutas, actuales, strict=True):
			for etiqueta in set(elegidas) - tenia:
				self.almacen.etiquetar(ruta, etiqueta)
			for etiqueta in (comunes - set(elegidas)) & tenia:
				self.almacen.quitar_etiqueta(ruta, etiqueta)
		texto = motor.texto_etiquetas(elegidas, definidas) if elegidas else _("ninguna")
		self.zc.anunciar(_("Etiquetas: {e}").format(e=texto), api.RESULTADO)
		self.zc.columnas.invalidar([*rutas, *(e.ruta for e in panel.elementos_trabajo())])
		panel.refrescar()

	def buscar(self, ctx: api.ContextoComplemento) -> None:
		from . import ui

		carpeta = ctx.activo.proveedor.ruta_local(ctx.activo.ruta) if ctx.activo.ruta else ""
		dialogo = ui.DialogoBuscar(None, self.zc, carpeta or "", self._definidas())
		try:
			if self.zc.ui.mostrar_modal(dialogo) != ui.wx.ID_OK:
				return
			texto, etiqueta, carpeta, subcarpetas = dialogo.criterios()
		finally:
			dialogo.Destroy()
		if not texto.strip() and not etiqueta:
			self.zc.anunciar(_("Escriba un texto o elija una etiqueta"), api.ESENCIAL)
			return
		if not os.path.isdir(carpeta):
			self.zc.anunciar(_("No existe la carpeta {c}").format(c=carpeta), api.ESENCIAL)
			return
		self.zc.sonidos.sonar("busqueda.inicio")

		def al_terminar(rutas: list[str]) -> None:
			if not rutas:
				self.zc.sonidos.sonar("busqueda.sin_resultados")
				self.zc.anunciar(_("No hay ningún elemento con ese comentario o etiqueta"), api.RESULTADO)
				return
			self.zc.sonidos.sonar("busqueda.fin")
			titulo = _("Etiqueta {e}").format(e=etiqueta) if etiqueta and not texto.strip() else _("Comentarios con «{t}»").format(t=texto.strip() or etiqueta)
			self.zc.ui.mostrar_resultados(titulo, rutas)
			self.zc.anunciar(api.formato.plural(len(rutas), _("{n} resultado"), _("{n} resultados")), api.RESULTADO)

		self.zc.tareas.enviar(lambda tarea: self.almacen.buscar(carpeta, texto, etiqueta, subcarpetas, tarea), al_terminar=al_terminar,
			al_fallar=lambda error: self.zc.anunciar(_("No se pudo buscar: {e}").format(e=error), api.ESENCIAL), nombre="notas-buscar")

	# Eventos -------------------------------------------------------------------

	def _al_cambiar_carpeta(self, panel: Any = None, proveedor: Any = None, ruta: str = "", **_datos: Any) -> None:
		if not self.zc.config.obtener("anunciar_notas") or proveedor is None or not ruta:
			return
		local = proveedor.ruta_local(ruta)
		lado = str(getattr(panel, "lado", ""))
		if not local or self._ultima.get(lado) == local:
			return
		self._ultima[lado] = local

		def comprobar(_tarea: Any) -> bool:
			return bool(self.almacen.comentario(local))

		def avisar(tiene: bool) -> None:
			if tiene and self._ultima.get(lado) == local:
				self.zc.sonidos.sonar("nota_carpeta")
				self.zc.anunciar(_("Esta carpeta tiene una nota"), api.NORMAL)

		self.zc.tareas.enviar(comprobar, al_terminar=avisar, nombre="notas-nota-carpeta")

	def _al_terminar_operacion(self, operacion: Any = None, **_datos: Any) -> None:
		if operacion is None or not self.zc.config.obtener("viajar"):
			return
		pares_hechos = getattr(operacion, "pares_hechos", None)
		if not callable(pares_hechos):
			return
		origen, destino = getattr(operacion, "origen", None), getattr(operacion, "destino", None)
		if origen is None or destino is None:
			return
		pares = []
		for ruta_origen, ruta_destino in pares_hechos():
			a, b = origen.ruta_local(ruta_origen), destino.ruta_local(ruta_destino)
			if a and b:
				pares.append((a, b))
		if not pares:
			return
		mover = bool(getattr(operacion, "mover", False))
		self.zc.tareas.enviar(lambda _t: self.viajar(pares, mover), nombre="notas-viajar",
			al_fallar=lambda error: self.zc.registro.warning("No viajaron los comentarios: %s", error))

	def viajar(self, pares: list[tuple[str, str]], mover: bool) -> None:
		"""Lleva comentarios y etiquetas de cada origen a su destino [trabajo]."""
		for origen, destino in pares:
			try:
				self.almacen.copiar(origen, destino, mover)
			except Exception:  # noqa: BLE001 - un par que falla no deja sin los demás
				self.zc.registro.warning("No se pudo llevar el comentario de %s a %s", origen, destino, exc_info=True)

	def ventanas_para_revisar(self, padre: Any) -> list:
		from . import ui

		try:
			return [ui.DialogoComentario(padre, self.zc, "x.txt", "Hola"), ui.DialogoComentario(padre, self.zc, "Carpeta", "", True),
				ui.DialogoEtiquetas(padre, self.zc, self._definidas(), set(), 2), ui.DialogoBuscar(padre, self.zc, "C:\\", self._definidas())]
		except api.NoAdmitido:
			self.zc.registro.info("Sin interfaz: las ventanas se revisan en las pruebas del bloque")
			return []
