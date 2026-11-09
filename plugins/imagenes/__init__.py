# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Imágenes: información, descripción y visor (zc.imagenes, diseño 2.0, 11.11).

Dice qué hay en una imagen: formato, dimensiones y EXIF (en Ctrl+Mayús+I, como
columnas y como máscaras de renombrado), el texto que contiene (con
``zc.ocr``, si está) y, solo si la persona lo pide y lo ha configurado, una
descripción de un servicio local compatible con Ollama o de una API compatible
con OpenAI. Ofrece un visor ampliable para baja visión, convierte,
redimensiona y gira por lotes, y quita la ubicación GPS de las fotos.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from app.plugins import api

from . import describir as servicio_descripcion
from . import exif

log = logging.getLogger(__name__)

ORDENES = ("describir", "visor", "convertir", "quitar_gps")
_PROHIBIDOS = str.maketrans({c: "_" for c in '\\/:*?"<>|'})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))
		for columna in ("dimensiones", "fecha_toma", "camara"):
			zc.columnas.extractor(columna, self._extractor(columna))
		zc.info.lineas(self._lineas_info)
		for marcador, funcion in (("[EXIF:fecha]", self._mascara_fecha), ("[EXIF:hora]", self._mascara_hora),
				("[EXIF:ancho]", self._mascara_numero("ancho")), ("[EXIF:alto]", self._mascara_numero("alto")),
				("[EXIF:camara]", self._mascara_camara)):
			zc.renombrado.mascara(marcador, funcion)

	# ── Lectura (hilos) ──────────────────────────────────────────────────────

	def _informacion(self, entrada: Any, proveedor: Any) -> exif.Informacion | None:
		if entrada.es_carpeta or not exif.es_imagen(entrada.nombre):
			return None
		local = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if not local:
			return None
		try:
			return exif.informacion(local)
		except (OSError, ValueError):
			log.debug("Sin información de %s", local, exc_info=True)
			return None

	def _extractor(self, columna: str) -> Callable[[Any, Any, Any], str | None]:
		def extraer(entrada: Any, proveedor: Any, _cancelacion: Any) -> str | None:
			info = self._informacion(entrada, proveedor)
			if info is None:
				return None
			if columna == "dimensiones":
				return f"{info.ancho} × {info.alto}" if info.ancho and info.alto else None
			if columna == "fecha_toma":
				return str(info.exif.get("fecha", ""))[:16] or None
			return info.exif.get("camara") or None

		return extraer

	def _lineas_info(self, entrada: Any, proveedor: Any) -> list[str]:
		info = self._informacion(entrada, proveedor)
		return exif.lineas(info) if info is not None else []

	def _mascara_fecha(self, entrada: Any, proveedor: Any) -> str | None:
		info = self._informacion(entrada, proveedor)
		fecha = str(info.exif.get("fecha", "")) if info is not None else ""
		return fecha[:10] or None

	def _mascara_hora(self, entrada: Any, proveedor: Any) -> str | None:
		info = self._informacion(entrada, proveedor)
		fecha = str(info.exif.get("fecha", "")) if info is not None else ""
		return fecha[11:19].replace(":", ".") or None

	def _mascara_numero(self, campo: str) -> Callable[[Any, Any], str | None]:
		def valor(entrada: Any, proveedor: Any) -> str | None:
			info = self._informacion(entrada, proveedor)
			numero = getattr(info, campo, 0) if info is not None else 0
			return str(numero) if numero else None

		return valor

	def _mascara_camara(self, entrada: Any, proveedor: Any) -> str | None:
		info = self._informacion(entrada, proveedor)
		camara = str(info.exif.get("camara", "")) if info is not None else ""
		return camara.translate(_PROHIBIDOS).strip() or None

	# ── Elementos ────────────────────────────────────────────────────────────

	def _imagenes(self, ctx: api.ContextoComplemento, solo_cursor: bool = False) -> tuple[Any, list[str]] | None:
		if isinstance(ctx.argumento, str) and ctx.argumento.strip() and os.path.isfile(ctx.argumento):
			return None, [ctx.argumento]
		panel = ctx.objetivo
		proveedor = panel.proveedor
		entradas = [panel.cursor()] if solo_cursor else panel.elementos_trabajo()
		entradas = [e for e in entradas if e is not None and not e.es_carpeta and exif.es_imagen(e.nombre)]
		if not entradas:
			ctx.anunciar(_("Ponga el cursor en una imagen") if solo_cursor else _("No hay imágenes elegidas"), api.RESULTADO)
			return None
		rutas = [proveedor.ruta_local(e.ruta) for e in entradas]
		if any(r is None for r in rutas):
			ctx.anunciar(_("Las imágenes tienen que estar en el disco o en la red local"), api.RESULTADO)
			return None
		return proveedor, [str(r) for r in rutas]

	def _carpeta_salida(self, ctx: api.ContextoComplemento, origen: str) -> str:
		pasivo = ctx.pasivo
		try:
			local = pasivo.proveedor.ruta_local(pasivo.ruta) if pasivo.ruta else None
		except Exception:  # noqa: BLE001 - un panel sin ruta local no sirve de destino
			log.debug("El otro panel no tiene ruta local", exc_info=True)
			local = None
		return local if local and os.path.isdir(local) else os.path.dirname(origen)

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _orden_visor(self, ctx: api.ContextoComplemento) -> None:
		from .ventanas import VisorImagen, imagenes_de_la_carpeta

		elegidas = self._imagenes(ctx, solo_cursor=True)
		if elegidas is None:
			return
		ruta = elegidas[1][0]
		visor = VisorImagen(self.zc.ui, None, self, ruta, imagenes_de_la_carpeta(ruta))
		visor.marco.Show()
		visor.area.SetFocus()

	def _orden_describir(self, ctx: api.ContextoComplemento) -> None:
		elegidas = self._imagenes(ctx, solo_cursor=True)
		if elegidas is not None:
			self.describir(elegidas[1][0], None)

	def describir(self, ruta: str, padre: Any) -> None:
		"""[interfaz] Pide la descripción al servicio configurado; explica cómo configurarlo si no hay ninguno."""
		servicio = str(self.zc.config.obtener("servicio", "ninguno"))
		if servicio not in ("ollama", "openai"):
			eleccion = self.zc.ui.elegir_opcion(
				_("Para describir imágenes hay que elegir un servicio en Preferencias, Complementos, Imágenes: un servidor local "
					"compatible con Ollama (por ejemplo, Ollama con un modelo de visión como llava o gemma3) o una API compatible con "
					"OpenAI con su clave. La imagen solo se envía cuando usted lo pide."),
				_("Describir la imagen"), [_("&Abrir las preferencias"), _("&Cerrar")], padre=padre)
			if eleccion == 0:
				self.zc.preferencias.abrir()
			return
		url = str(self.zc.config.obtener("url_servicio", "") or "")
		if not self.zc.config.obtener("aviso_privacidad_mostrado", False):
			if not self.zc.ui.confirmar(_("La imagen se enviará a {s} para describirla. Si ese servidor no es de su equipo, saldrá de él. "
					"¿Continuar? (Este aviso solo se muestra una vez.)").format(s=servicio_descripcion.servidor(url)),
					_("Aviso de privacidad"), padre=padre):
				return
			self.zc.config.establecer("aviso_privacidad_mostrado", True)
		clave = ""
		if servicio == "openai":
			clave = self.zc.secretos.obtener("clave_api") or ""
			if not clave:
				clave = self.zc.ui.pedir_texto(_("&Clave de la API:"), _("Describir la imagen"), "", padre=padre, contrasena=True) or ""
				if not clave.strip():
					return
				clave = clave.strip()
				self.zc.secretos.guardar("clave_api", clave)
		modelo = str(self.zc.config.obtener("modelo", "") or "")
		idioma = str(self.zc.config.obtener("idioma_descripcion", "es") or "es")
		longitud = str(self.zc.config.obtener("longitud", "breve"))
		nombre = os.path.basename(ruta)
		self.zc.anunciar(_("Pidiendo la descripción de {n}...").format(n=nombre), api.NORMAL)

		def trabajo() -> str:
			from . import procesado

			orientacion = int(exif.informacion(ruta).exif.get("orientacion", 1))
			imagen = procesado.jpeg_reducido(ruta, 1024, orientacion)
			if servicio == "ollama":
				direccion, cuerpo = servicio_descripcion.peticion_ollama(url, modelo, imagen, idioma, longitud)
				cabeceras: dict[str, str] = {}
			else:
				direccion, cuerpo = servicio_descripcion.peticion_openai(url, modelo, imagen, idioma, longitud)
				cabeceras = {"Authorization": f"Bearer {clave}"}
			respuesta = self.zc.red.enviar(direccion, cuerpo, cabeceras=cabeceras, tiempo_s=180)
			return servicio_descripcion.leer_respuesta(servicio, respuesta.cuerpo)

		def llegada(texto: str) -> None:
			self.zc.sonidos.sonar("descripcion")
			self.zc.ui.mostrar_texto(_("Descripción de {n}").format(n=nombre), texto)

		self._en_hilo(trabajo, llegada, _("No se pudo describir la imagen: {e}"))

	def reconocer_texto(self, ruta: str) -> None:
		"""[interfaz] Texto de la imagen con ``zc.ocr`` (11.0), en un hilo; sin el complemento, lo dice."""

		def trabajo() -> Any:
			ocr = self.zc.complemento("zc.ocr")
			if ocr is None or not hasattr(ocr, "reconocer"):
				raise api.NoAdmitido(_("Para leer el texto de las imágenes hace falta el complemento Reconocimiento de texto (OCR)"))
			proveedor, _carpeta = self.zc.vfs.resolver(os.path.dirname(ruta))
			try:
				return ocr.reconocer(proveedor, ruta, None)
			finally:
				proveedor.cerrar()

		self.zc.anunciar(_("Reconociendo el texto..."), api.NORMAL)
		self._en_hilo(trabajo, self.zc.ui.mostrar_documento, _("No se pudo reconocer el texto: {e}"))

	def _en_hilo(self, trabajo: Callable[[], Any], despues: Callable[[Any], None], error_texto: str) -> None:
		import wx

		def correr() -> None:
			try:
				resultado = trabajo()
			except Exception as error:  # noqa: BLE001 - se informa a la persona con un mensaje en español
				log.info("Falló un trabajo de imágenes", exc_info=True)
				mensaje = error_texto.format(e=getattr(error, "strerror", None) or error)
				wx.CallAfter(lambda: self.zc.anunciar(mensaje, api.ESENCIAL))
				return
			wx.CallAfter(despues, resultado)

		threading.Thread(target=correr, name="zc-imagenes", daemon=True).start()

	def _orden_convertir(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .operaciones import OpcionesConversion, OperacionConvertir
		from .procesado import FORMATOS, POR_EXTENSION
		from .ventanas import DialogoConvertir

		elegidas = self._imagenes(ctx)
		if elegidas is None:
			return
		proveedor, rutas = elegidas
		dialogo = DialogoConvertir(self.zc.ui, None, len(rutas), self._carpeta_salida(ctx, rutas[0]))
		try:
			while True:
				if self.zc.ui.mostrar_modal(dialogo.dialogo) != wx.ID_OK:
					return
				carpeta = dialogo.carpeta.GetValue().strip()
				mascara = dialogo.nombre.GetValue().strip() or "[N]"
				if not os.path.isdir(carpeta):
					self.zc.ui.mostrar_error(_("La carpeta de salida no existe: {c}").format(c=carpeta), _("Convertir imágenes"),
						padre=dialogo.dialogo)
					continue
				if any(c in mascara for c in '\\/:*?"<>|'):
					self.zc.ui.mostrar_error(_("El nombre no puede llevar \\ / : * ? \" < > |"), _("Convertir imágenes"), padre=dialogo.dialogo)
					continue
				break
			opciones = OpcionesConversion(formato=dialogo.valor_formato, ancho_maximo=dialogo.ancho.GetValue(),
				alto_maximo=dialogo.alto.GetValue(), giro=dialogo.valor_giro, politica=dialogo.valor_si_existe,
				calidad=int(self.zc.config.obtener("calidad_jpeg", 90)))
		finally:
			dialogo.dialogo.Destroy()
		trabajos = []
		for contador, origen in enumerate(rutas, start=1):
			base, extension = os.path.splitext(os.path.basename(origen))
			formato = opciones.formato or POR_EXTENSION.get(extension.lower(), "png")
			nombre = mascara.replace("[N]", base).replace("[C]", f"{contador:02d}") + FORMATOS[formato][1]
			trabajos.append((origen, os.path.join(carpeta, nombre)))
		descripcion = (_("Convertir {n}").format(n=os.path.basename(rutas[0])) if len(rutas) == 1
			else _("Convertir {n} imágenes").format(n=len(rutas)))
		self.zc.lanzar(OperacionConvertir(descripcion, proveedor or _ProveedorLocal(), trabajos, opciones,
			orientacion_de=lambda r: int(exif.informacion(r).exif.get("orientacion", 1))))

	def _orden_quitar_gps(self, ctx: api.ContextoComplemento) -> None:
		from .operaciones import OperacionQuitarGps

		elegidas = self._imagenes(ctx)
		if elegidas is None:
			return
		proveedor, rutas = elegidas
		jpeg = [r for r in rutas if os.path.splitext(r)[1].lower() in (".jpg", ".jpeg", ".jpe")]
		if not jpeg:
			ctx.anunciar(_("Solo se puede quitar la ubicación de las fotos JPEG"), api.RESULTADO)
			return
		pregunta = (_("¿Quitar la ubicación GPS de {n}? La foto no se recomprime y conserva su fecha.").format(n=os.path.basename(jpeg[0]))
			if len(jpeg) == 1 else _("¿Quitar la ubicación GPS de {n} fotos? Las fotos no se recomprimen y conservan su fecha.").format(
				n=len(jpeg)))
		if not self.zc.ui.confirmar(pregunta, _("Quitar la ubicación"), peligroso=True):
			return
		descripcion = (_("Quitar la ubicación de {n}").format(n=os.path.basename(jpeg[0])) if len(jpeg) == 1
			else _("Quitar la ubicación de {n} fotos").format(n=len(jpeg)))
		self.zc.lanzar(OperacionQuitarGps(descripcion, proveedor or _ProveedorLocal(), jpeg))

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""El visor y el diálogo de convertir, sin mostrarlos (3.12)."""
		from .ventanas import DialogoConvertir, VisorImagen

		try:
			ui = self.zc.ui
			ui.VentanaComplemento  # noqa: B018 - comprueba que hay interfaz
		except api.NoAdmitido:
			log.info("Sin interfaz de zCommander no se pueden construir las ventanas de imágenes")
			return []
		visor = VisorImagen(ui, padre, self, os.path.join(str(self.carpeta), "no-existe.png"))
		convertir = DialogoConvertir(ui, padre, 2, "C:\\")
		return [visor.marco, convertir.dialogo]


class _ProveedorLocal:
	"""Lo mínimo de un proveedor local para los carriles cuando la imagen llega por argumento (Intro asociado)."""

	esquema = "local"
	contenedor = None
