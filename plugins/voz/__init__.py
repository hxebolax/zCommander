# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura en voz y audiolibros (zc.voz, diseño 2.0, 11.17).

Lee archivos de texto y documentos con una voz de Windows (SAPI 5 y, si están,
las voces OneCore), aparte del lector de pantalla: de corrido, con pausa,
frase y párrafo anterior y siguiente, y recordando dónde se dejó. Convierte uno
o varios archivos en audio (WAV, y MP3 u Opus con el componente FFmpeg) como
operación, dividiendo por capítulos con ``zc.documentos`` si está.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from typing import Any

from app.plugins import api

from . import texto as modulo_texto
from .lector import Lector, Posiciones

log = logging.getLogger(__name__)

ORDENES = ("leer", "detener", "exportar", "frase_siguiente", "frase_anterior", "parrafo_siguiente", "parrafo_anterior")
#: Se leen directamente (texto plano); lo demás necesita el lector de documentos.
TEXTO = frozenset({"txt", "text", "md", "markdown", "log", "csv", "tsv", "srt", "vtt", "ini", "cfg", "nfo", "json", "xml", "py",
	"bat", "cmd", "ps1", "tex", "rst", "lst", "diz"})
DOCUMENTOS = frozenset({"pdf", "docx", "odt", "epub", "rtf", "html", "htm", "xhtml", "fb2", "doc"})
#: Tope de lo que se lee de un archivo de texto (un registro enorme no se carga entero).
MAXIMO_TEXTO = 64 * 1024 * 1024


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def extension(nombre: str) -> str:
	return os.path.splitext(nombre)[1].lower().lstrip(".")


def es_legible(nombre: str) -> bool:
	return extension(nombre) in TEXTO | DOCUMENTOS


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.lector: Lector | None = None
		self._voz: Any = None
		self._prueba: Any = None
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))
		try:
			zc.preferencias.dialogo(self.abrir_dialogo_voz)
		except api.NoAdmitido:
			log.debug("Sin interfaz: el diálogo de la voz se registrará cuando la haya")

	def desactivar(self) -> None:
		if self.lector is not None:
			self.lector.cerrar()
		for voz in (self._voz, self._prueba):
			if voz is not None:
				voz.cerrar()
		self._voz = self._prueba = None

	# ── Voz y lector ─────────────────────────────────────────────────────────

	def ajustes(self, voz: str | None = None) -> Any:
		from .sapi import Ajustes

		obtener = self.zc.config.obtener
		return Ajustes(voz=str(obtener("voz", "") or "") if voz is None else voz, velocidad=int(obtener("velocidad", 0)),
			tono=int(obtener("tono", 0)), volumen=int(obtener("volumen", 100)))

	def _al_cambiar_config(self, clave: str, _anterior: Any, _nuevo: Any) -> None:
		if self._voz is not None and clave in ("voz", "velocidad", "tono", "volumen"):
			self._voz.fijar(self.ajustes())

	def obtener_lector(self) -> Lector:
		if self.lector is None:
			from .sapi import VozSapi

			# La configuración se abre aquí y no en activar(): activar no escribe nada en data.
			self.zc.config.suscribir(self._al_cambiar_config)
			self._voz = VozSapi(_planificar, self.ajustes())
			self.lector = Lector(self._voz, anunciar=self.zc.anunciar, sonar=self.zc.sonidos.sonar, posiciones=Posiciones(self.zc.datos),
				pausa_parrafo_ms=lambda: int(self.zc.config.obtener("pausa_parrafo_ms", 400)),
				tono=lambda: int(self.zc.config.obtener("tono", 0)))
		return self.lector

	# ── Texto de un archivo ──────────────────────────────────────────────────

	def secciones(self, ruta: str, cancelacion: Any = None) -> list[tuple[str, int, str]]:
		"""[trabajo] (título, nivel, texto) de un archivo: texto plano directamente; documentos con ``zc.documentos``."""
		if extension(ruta) in TEXTO:
			with open(ruta, "rb") as archivo:
				datos = archivo.read(MAXIMO_TEXTO)
			return [("", 1, modulo_texto.decodificar(datos))]
		documentos = self.zc.complemento("zc.documentos")
		if documentos is None or not hasattr(documentos, "convertir"):
			raise api.NoAdmitido(_("Para leer {e} hace falta el complemento Lector de documentos").format(e=extension(ruta).upper()))
		proveedor, _carpeta = self.zc.vfs.resolver(os.path.dirname(ruta))
		try:
			documento = documentos.convertir(proveedor, ruta, cancelacion)
		finally:
			proveedor.cerrar()
		return [(s.titulo, int(s.nivel), s.texto) for s in documento.secciones]

	@staticmethod
	def texto_completo(secciones: list[tuple[str, int, str]]) -> str:
		bloques = []
		for titulo, _nivel, texto in secciones:
			if titulo:
				bloques.append(titulo)
			if texto:
				bloques.append(texto)
		return "\n\n".join(bloques)

	# ── Órdenes de lectura ───────────────────────────────────────────────────

	def _orden_leer(self, ctx: api.ContextoComplemento) -> None:
		if self.lector is not None and self.lector.activo:
			self.lector.pausa_continuar()
			return
		ruta = ctx.argumento if isinstance(ctx.argumento, str) and os.path.isfile(ctx.argumento) else ""
		if not ruta:
			cursor = ctx.objetivo.cursor()
			if cursor is None or cursor.es_carpeta or not es_legible(cursor.nombre):
				ctx.anunciar(_("Ponga el cursor en un archivo de texto o un documento"), api.RESULTADO)
				return
			ruta = ctx.objetivo.proveedor.ruta_local(cursor.ruta) or ""
			if not ruta:
				ctx.anunciar(_("Solo se leen archivos del disco o de la red local"), api.RESULTADO)
				return
		lector = self.obtener_lector()
		nombre = os.path.basename(ruta)
		ctx.anunciar(_("Leyendo {n}").format(n=nombre), api.NORMAL)

		def trabajo() -> None:
			try:
				texto = self.texto_completo(self.secciones(ruta))
			except (api.ErrorArchivos, OSError, ValueError) as error:
				self.zc.anunciar(str(getattr(error, "strerror", None) or error), api.ESENCIAL)
				return
			_planificar(lambda: lector.leer(texto, ruta, nombre))

		threading.Thread(target=trabajo, name="zc-voz-leer", daemon=True).start()

	def _orden_detener(self, ctx: api.ContextoComplemento) -> None:
		if self.lector is None:
			ctx.anunciar(_("No se está leyendo nada"), api.RESULTADO)
			return
		self.lector.detener()

	def _mover(self, ctx: api.ContextoComplemento, metodo: str) -> None:
		if self.lector is None or not self.lector.frases:
			ctx.anunciar(_("No se está leyendo nada"), api.RESULTADO)
			return
		getattr(self.lector, metodo)()

	def _orden_frase_siguiente(self, ctx: api.ContextoComplemento) -> None:
		self._mover(ctx, "frase_siguiente")

	def _orden_frase_anterior(self, ctx: api.ContextoComplemento) -> None:
		self._mover(ctx, "frase_anterior")

	def _orden_parrafo_siguiente(self, ctx: api.ContextoComplemento) -> None:
		self._mover(ctx, "parrafo_siguiente")

	def _orden_parrafo_anterior(self, ctx: api.ContextoComplemento) -> None:
		self._mover(ctx, "parrafo_anterior")

	# ── Convertir a audio ────────────────────────────────────────────────────

	def _orden_exportar(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from . import operacion, sapi
		from .dialogos import DialogoExportar

		panel = ctx.objetivo
		proveedor = panel.proveedor
		entradas = [e for e in panel.elementos_trabajo() if not e.es_carpeta and es_legible(e.nombre)]
		if not entradas:
			ctx.anunciar(_("No hay archivos de texto ni documentos elegidos"), api.RESULTADO)
			return
		rutas = [proveedor.ruta_local(e.ruta) for e in entradas]
		if any(r is None for r in rutas):
			ctx.anunciar(_("Solo se convierten archivos del disco o de la red local"), api.RESULTADO)
			return
		rutas = [str(r) for r in rutas]
		hay_ffmpeg = self.zc.componentes.disponible("ffmpeg")
		dialogo = DialogoExportar(self.zc.ui, None, len(rutas), str(self.zc.config.obtener("formato_salida", "mp3")),
			self._carpeta_salida(ctx, rutas[0]), hay_ffmpeg, True)
		try:
			while True:
				if self.zc.ui.mostrar_modal(dialogo.dialogo) != wx.ID_OK:
					return
				carpeta = dialogo.carpeta.GetValue().strip()
				if os.path.isdir(carpeta):
					break
				self.zc.ui.mostrar_error(_("La carpeta de salida no existe: {c}").format(c=carpeta), _("Convertir a audio"),
					padre=dialogo.dialogo)
			formato = dialogo.valor_formato
			dividir = dialogo.dividir.GetValue()
		finally:
			dialogo.dialogo.Destroy()
		if not hay_ffmpeg and formato != "wav":
			ctx.anunciar(_("Falta el componente FFmpeg: Opciones, Componentes externos"), api.ESENCIAL)
			return

		def obtener_piezas(ruta: str, contexto: Any) -> list[operacion.Pieza]:
			nombre = os.path.splitext(os.path.basename(ruta))[0]
			return operacion.piezas_de_documento(nombre, self.secciones(ruta, getattr(contexto, "token", None)), dividir)

		descripcion = (_("Convertir {n} a audio").format(n=os.path.basename(rutas[0])) if len(rutas) == 1
			else _("Convertir {n} archivos a audio").format(n=len(rutas)))
		self.zc.lanzar(operacion.OperacionAudiolibro(descripcion, proveedor, rutas, carpeta=carpeta, formato=formato,
			obtener_piezas=obtener_piezas, exportar_wav=sapi.exportar_wav, ajustes=self.ajustes(),
			pausa_ms=int(self.zc.config.obtener("pausa_parrafo_ms", 400)),
			ffmpeg=(lambda: str(self.zc.componentes.ejecutable("ffmpeg", "ffmpeg.exe"))) if hay_ffmpeg else None,
			ejecutar=self.zc.ejecutar_programa if hay_ffmpeg else None))

	def _carpeta_salida(self, ctx: api.ContextoComplemento, origen: str) -> str:
		pasivo = ctx.pasivo
		try:
			local = pasivo.proveedor.ruta_local(pasivo.ruta) if pasivo.ruta else None
		except Exception:  # noqa: BLE001 - un panel sin ruta local no sirve de destino
			log.debug("El otro panel no tiene ruta local", exc_info=True)
			local = None
		return local if local and os.path.isdir(local) else os.path.dirname(origen)

	# ── Configuración avanzada: la voz ───────────────────────────────────────

	def abrir_dialogo_voz(self, padre: Any) -> None:
		"""[interfaz] Diálogo propio de Preferencias (``dialogo_preferencias = true``): elegir y probar la voz."""
		import wx

		from . import sapi
		from .dialogos import DialogoVoz

		try:
			voces = sapi.voces()
		except Exception:  # noqa: BLE001 - sin SAPI se dice y no se abre nada
			log.warning("No se pudieron listar las voces", exc_info=True)
			self.zc.ui.mostrar_error(_("No se pudieron leer las voces de Windows."), _("Voz de lectura"), padre=padre)
			return
		dialogo = DialogoVoz(self.zc.ui, padre, voces, str(self.zc.config.obtener("voz", "") or ""), self._probar_voz)
		try:
			if self.zc.ui.mostrar_modal(dialogo.dialogo) == wx.ID_OK:
				self.zc.config.establecer("voz", dialogo.elegida)
		finally:
			dialogo.dialogo.Destroy()
			if self._prueba is not None:
				self._prueba.cerrar()
				self._prueba = None

	def _probar_voz(self, voz: str) -> None:
		from .sapi import VozSapi

		if self._prueba is None:
			self._prueba = VozSapi(_planificar, self.ajustes(voz))
		else:
			self._prueba.fijar(self.ajustes(voz))
		self._prueba.hablar(modulo_texto.xml_sapi(_("Esta es la voz con la que zCommander leerá sus documentos."),
			int(self.zc.config.obtener("tono", 0))), 0, lambda _n: None)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""«Convertir a audio» y «Voz de lectura», sin mostrarlos (3.12)."""
		from .dialogos import DialogoExportar, DialogoVoz

		try:
			ui = self.zc.ui
			ui.crear_campo  # noqa: B018 - comprueba que hay interfaz
		except api.NoAdmitido:
			log.info("Sin interfaz de zCommander no se pueden construir los diálogos de la voz")
			return []
		exportar = DialogoExportar(ui, padre, 2, "mp3", "C:\\", True, True)
		voz = DialogoVoz(ui, padre, ["Voz de prueba"], "", lambda _v: None)
		return [exportar.dialogo, voz.dialogo]


def _planificar(funcion: Any) -> None:
	import wx

	wx.CallAfter(funcion)
