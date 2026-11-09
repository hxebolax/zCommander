# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lector de documentos (zc.documentos, diseño 2.0, 11.2).

Convierte PDF, DOCX, ODT, EPUB, RTF, HTML, FB2 (y .doc con Word) en un
``api.Documento`` con secciones que se lee en el visor interno (F3: F6 y
Mayús+F6 de sección en sección, Ctrl+L la lista, Ctrl+P ir a una página) y en
la Vista rápida. Además: columnas Páginas, Título y Autor; líneas de
«Información del elemento»; extractor de texto para «Buscar archivos»;
«Convertir a texto...» (operación) y «Propiedades del documento».

Exporta ``convertir(proveedor, ruta, cancelacion) -> Documento`` (tabla de 11.0).
"""

from __future__ import annotations

import builtins
import os
import threading
from collections import OrderedDict
from typing import Any

from app.plugins import api

from .servicios import lector
from .servicios.comun import ErrorDocumento, Opciones

#: Metadatos guardados por (ruta, tamaño, fecha): las tres columnas no leen tres veces el mismo documento.
_MAXIMO_CACHE = 512


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._cache: OrderedDict[tuple[str, int, float], dict[str, str]] = OrderedDict()
		self._candado = threading.Lock()
		zc.ordenes.manejador("convertir", self.orden_convertir)
		zc.ordenes.manejador("propiedades", self.orden_propiedades)
		zc.visores.visor("documento", self.visor)
		zc.columnas.extractor("paginas", lambda e, p, c: self._columna(e, p, c, "paginas"))
		zc.columnas.extractor("titulo", lambda e, p, c: self._columna(e, p, c, "titulo"))
		zc.columnas.extractor("autor", lambda e, p, c: self._columna(e, p, c, "autor"))
		zc.info.lineas(self.lineas_info)
		zc.busqueda.extractor(self.extraer_texto)
		zc.exportar("convertir", self.convertir)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			ui = self.zc.ui
			ui.crear_campo  # noqa: B018 - sin la ventana de zCommander lanza NoAdmitido
		except api.NoAdmitido:
			self.zc.registro.info("Sin la interfaz de zCommander no se pueden construir los diálogos para revisarlos")
			return []
		from .ui.dialogo_convertir import DialogoConvertir

		return [DialogoConvertir(padre, ui, ["informe.pdf", "libro.epub"], "txt", "utf-8", "D:\\Textos")]

	# ── Preferencias ─────────────────────────────────────────────────────────

	def opciones(self) -> Opciones:
		return Opciones(marcas_pagina=bool(self.zc.config.obtener("marcas_pagina", True)),
			texto_alternativo=bool(self.zc.config.obtener("texto_alternativo", True)))

	def maximo(self) -> int:
		return int(self.zc.config.obtener("tamano_maximo_mb", 100)) * 1024 * 1024

	def formatos(self) -> list[str]:
		valor = self.zc.config.obtener("formatos", None)
		return list(valor) if isinstance(valor, list) and valor else list(lector.FORMATOS)

	def admitido(self, nombre: str) -> bool:
		return lector.admitido(nombre, self.formatos())

	# ── Funciones de trabajo (en hilos) ──────────────────────────────────────

	def _ocr(self) -> Any:
		"""Lo que exporta ``zc.ocr`` (activándolo y esperando) o ``None``; solo desde un hilo de trabajo."""
		try:
			return self.zc.complemento("zc.ocr")
		except Exception:  # noqa: BLE001 - sin OCR se sigue sin él
			self.zc.registro.debug("zc.ocr no está disponible", exc_info=True)
			return None

	def convertir(self, proveedor: api.Proveedor, ruta: str, cancelacion: Any = None, *, con_ocr: bool = False) -> api.Documento:
		"""[trabajo] Función exportada: el ``Documento`` de un archivo (``ErrorArchivos`` si no se puede)."""
		reconocer = None
		if con_ocr:
			ocr = self._ocr()
			reconocer = getattr(ocr, "reconocer", None) if ocr is not None else None
		return lector.convertir(proveedor, ruta, cancelacion, self.opciones(), self.maximo(), str(self.zc.cache), reconocer)

	def visor(self, proveedor: api.Proveedor, ruta: str, cancelacion: Any) -> api.Documento | None:
		"""Visor (F3 y Vista rápida). ``None`` deja el archivo al visor interno (formato desactivado)."""
		nombre = proveedor.nombre(ruta)
		if not self.admitido(nombre):
			return None
		try:
			documento = self.convertir(proveedor, ruta, cancelacion)
		except api.Cancelado:
			raise
		except api.ErrorArchivos as error:
			titulo = os.path.splitext(nombre)[0]
			return api.Documento(titulo, (api.Seccion(titulo, 1, ""),), {}, error.mensaje)
		if documento.aviso and lector.extension(nombre) == "pdf" and self._ocr() is not None:
			documento = api.Documento(documento.titulo, documento.secciones, documento.metadatos,
				documento.aviso + " " + _("Pulse Control+Mayúsculas+F3 en el panel para reconocer su texto."))
		return documento

	def extraer_texto(self, proveedor: api.Proveedor, ruta: str, cancelacion: Any) -> str | None:
		"""Extractor para «Buscar también dentro de documentos»."""
		if not self.admitido(proveedor.nombre(ruta)) or lector.extension(ruta) == "doc":
			return None
		try:
			return lector.texto_plano(self.convertir(proveedor, ruta, cancelacion))
		except api.Cancelado:
			raise
		except api.ErrorArchivos:
			return None

	def metadatos(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any = None) -> dict[str, str]:
		clave = (entrada.ruta, entrada.tamano, entrada.modificado)
		with self._candado:
			if clave in self._cache:
				self._cache.move_to_end(clave)
				return self._cache[clave]
		try:
			datos = lector.metadatos(proveedor, entrada.ruta, cancelacion, self.maximo())
		except api.Cancelado:
			raise
		except api.ErrorArchivos:
			datos = {}
		with self._candado:
			self._cache[clave] = datos
			while len(self._cache) > _MAXIMO_CACHE:
				self._cache.popitem(last=False)
		return datos

	def _columna(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any, campo: str) -> str | None:
		if entrada.es_carpeta or not self.admitido(entrada.nombre):
			return None
		return self.metadatos(entrada, proveedor, cancelacion).get(campo) or None

	def lineas_info(self, entrada: api.Entrada, proveedor: api.Proveedor) -> list[str]:
		if entrada.es_carpeta or not self.admitido(entrada.nombre):
			return []
		return lineas_de(lector.FORMATOS[lector.extension(entrada.nombre)], self.metadatos(entrada, proveedor))

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def orden_propiedades(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		cursor = panel.cursor()
		if cursor is None or cursor.es_carpeta or not lector.admitido(cursor.nombre):
			ctx.anunciar(_("Sitúese en un documento: PDF, DOCX, ODT, EPUB, RTF, HTML o FB2"), api.ESENCIAL)
			return
		proveedor = panel.proveedor

		def trabajo(tarea: Any) -> tuple[list[str], bool]:
			datos = self.metadatos(cursor, proveedor, tarea)
			escaneado = False
			if lector.extension(cursor.nombre) == "pdf":
				from .servicios import pdf

				try:
					escaneado = pdf.sin_texto(lector.leer_bytes(proveedor, cursor.ruta, self.maximo(), tarea))
				except api.ErrorArchivos:
					escaneado = False
			hay_ocr = escaneado and self._ocr() is not None
			return lineas_de(lector.FORMATOS[lector.extension(cursor.nombre)], datos, escaneado), hay_ocr

		def mostrar(resultado: tuple[list[str], bool]) -> None:
			lineas, hay_ocr = resultado
			ctx.anunciar(". ".join(lineas) + ".", api.RESULTADO)
			if hay_ocr and self.zc.ui.confirmar(_("{n} no tiene texto: probablemente está escaneado. ¿Reconocer su texto con OCR?").format(
					n=cursor.nombre), _("PDF sin texto")):
				self.zc.ejecutar_orden("zc.ocr:reconocer")

		self.zc.tareas.enviar(trabajo, al_terminar=mostrar, nombre="zc.documentos:propiedades",
			al_fallar=lambda error: ctx.anunciar(_("No se pudieron leer las propiedades: {e}").format(
				e=getattr(error, "mensaje", "") or error), api.ESENCIAL))

	def orden_convertir(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		elementos = [e for e in panel.elementos_trabajo() if not e.es_carpeta and lector.admitido(e.nombre)]
		if not elementos:
			ctx.anunciar(_("Elija uno o varios documentos: PDF, DOCX, ODT, EPUB, RTF, HTML o FB2"), api.ESENCIAL)
			return
		proveedor = panel.proveedor
		otro = ctx.pasivo if ctx.pasivo is not panel else ctx.activo
		carpeta_pasiva = otro.proveedor.ruta_local(otro.ruta) or "" if otro.ruta else ""
		todos_locales = all(proveedor.ruta_local(e.ruta) for e in elementos)
		if not todos_locales and not carpeta_pasiva:
			ctx.anunciar(_("Estos documentos no están en el disco: abra una carpeta del disco en el otro panel para guardar allí el texto"),
				api.ESENCIAL)
			return
		from .ui.dialogo_convertir import DialogoConvertir

		dialogo = DialogoConvertir(None, self.zc.ui, [e.nombre for e in elementos], self.zc.config.obtener("formato_salida", "txt"),
			self.zc.config.obtener("codificacion_salida", "utf-8"), carpeta_pasiva, al_ayuda=self.zc.abrir_ayuda)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != _id_ok():
				return
			formato, codificacion, carpeta = dialogo.eleccion()
		finally:
			dialogo.Destroy()
		if not carpeta and not todos_locales:
			ctx.anunciar(_("Estos documentos no están en el disco: elija guardarlos en la carpeta del otro panel"), api.ESENCIAL)
			return
		from .servicios.salida import Elemento, OperacionConvertirDocumentos, destino_para

		lista = [Elemento(proveedor, e.ruta, destino_para(carpeta or os.path.dirname(proveedor.ruta_local(e.ruta) or ""), e.nombre, formato))
			for e in elementos]
		self.zc.lanzar(OperacionConvertirDocumentos(lista, formato, codificacion,
			lambda p, r, c: self.convertir(p, r, c, con_ocr=True)))


def lineas_de(formato: str, datos: dict[str, str], escaneado: bool = False) -> list[str]:
	"""Líneas de información de un documento: «Documento PDF, 80 páginas», «Título: ...»."""
	primera = _("Documento {f}").format(f=formato)
	if datos.get("paginas"):
		primera += ", " + (_("1 página") if datos["paginas"] == "1" else _("{n} páginas").format(n=datos["paginas"]))
	elif datos.get("capitulos"):
		primera += ", " + _("{n} capítulos").format(n=datos["capitulos"])
	lineas = [primera]
	for clave, nombre in (("titulo", _("Título")), ("autor", _("Autor")), ("fecha", _("Fecha")), ("asunto", _("Asunto"))):
		if datos.get(clave):
			lineas.append(f"{nombre}: {datos[clave]}")
	if escaneado:
		lineas.append(_("Sin texto: probablemente escaneado"))
	return lineas


def _id_ok() -> int:
	import wx

	return wx.ID_OK


__all__ = ["Complemento", "ErrorDocumento"]
