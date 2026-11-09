# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Metadatos y etiquetas de audio (zc.metadatos, diseño 2.0, 11.4).

Lee y edita las etiquetas de MP3, FLAC, M4A, OGG, Opus, WMA y WAV con mutagen
(vendorizado en ``lib/``): columnas, líneas de «Información del elemento»,
editor accesible de uno o varios archivos, etiquetas desde el nombre, numerar,
quitar, portada, exportar la lista de pistas y máscaras ``[MP3:…]`` para el
renombrado. Los cambios son operaciones del motor con deshacer.

Exporta ``leer_etiquetas(proveedor, ruta) -> dict[str, str]`` (11.0), que usan
el reproductor y el buscador de duplicados.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from app.plugins import api

from . import etiquetas
from .operacion import Copias, OperacionEtiquetas, OperacionExportar

log = logging.getLogger(__name__)

ORDENES = ("editar", "desde_nombre", "numerar", "quitar", "portada", "exportar")
MASCARA_POR_DEFECTO = "[pista] - [artista] - [titulo]"
#: Columnas del conjunto «Música» que se propone al activarse (10.4).
COLUMNAS_MUSICA = ("nombre", "zc.metadatos:pista", "zc.metadatos:artista", "zc.metadatos:titulo", "zc.metadatos:album",
	"zc.metadatos:duracion")
_PROHIBIDOS = str.maketrans({c: "_" for c in '\\/:*?"<>|'})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self.cache = etiquetas.Cache()
		self._copias: Copias | None = None
		self._empezado = False
		self._candado = threading.Lock()
		self.mascara = MASCARA_POR_DEFECTO
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))
		for columna in ("artista", "titulo", "album", "pista", "anio", "genero", "duracion", "bitrate", "frecuencia", "canales",
				"portada"):
			zc.columnas.extractor(columna, self._extractor(columna))
		zc.info.lineas(self._lineas_info)
		for campo in etiquetas.CLAVES:
			zc.renombrado.mascara(f"[MP3:{campo}]", self._mascara(campo))
		zc.exportar("leer_etiquetas", self.leer_etiquetas)

	def desactivar(self) -> None:
		if self._copias is not None:
			borradas = self._copias.limpiar()
			if borradas:
				log.info("Borradas %d copias de deshacer de esta sesión", borradas)

	@property
	def copias(self) -> Copias:
		"""Las copias de deshacer (su lista va en la carpeta de datos, que se crea al pedirla)."""
		if self._copias is None:
			self._copias = Copias(self.zc.datos)
		return self._copias

	def _empezar(self) -> None:
		"""La primera vez que se usa (no en ``activar``, que no escribe nada): limpieza y conjunto «Música», en un hilo."""
		with self._candado:
			if self._empezado:
				return
			self._empezado = True
		threading.Thread(target=self._al_empezar, name="zc-metadatos-inicio", daemon=True).start()

	def _al_empezar(self) -> None:
		"""Fuera del hilo de la interfaz: copias de un cierre brusco y el conjunto «Música»."""
		try:
			self.copias.limpiar()
		except Exception:  # noqa: BLE001 - una copia que no se borra no impide usar el complemento
			log.warning("No se pudieron limpiar las copias de deshacer", exc_info=True)
		if self.zc.config.obtener("columnas_musica", True):
			try:
				self.zc.vistas.proponer_conjunto(_("Música"), list(COLUMNAS_MUSICA), list(COLUMNAS_MUSICA),
					extensiones=sorted(etiquetas.EXTENSIONES), proporcion=0.6)
			except Exception:  # noqa: BLE001 - sin vistas por carpeta, las columnas se eligen a mano
				log.info("No se pudo proponer el conjunto Música", exc_info=True)

	# ── Lectura (hilos) ──────────────────────────────────────────────────────

	def leer_etiquetas(self, proveedor: Any, ruta: str) -> dict[str, str]:
		"""[trabajo] Función exportada (11.0): etiquetas de un archivo de audio.

		Claves ``artista``, ``titulo``, ``album``, ``pista``, ``anio``, ``genero`` y
		``duracion_s`` (más ``bitrate``, ``frecuencia``, ``canales`` y ``portada``).
		Con ``proveedor`` ``None``, ``ruta`` es una ruta local. Diccionario vacío si
		el archivo no tiene etiquetas que se puedan leer.
		"""
		self._empezar()
		local = ruta if proveedor is None else (proveedor.ruta_local(ruta) or proveedor.extraer_temporal(ruta))
		try:
			return dict(self.cache.leer(local))
		except (etiquetas.ErrorEtiquetas, OSError):
			log.debug("Sin etiquetas en %s", ruta, exc_info=True)
			return {}

	def _datos(self, entrada: Any, proveedor: Any) -> dict[str, str] | None:
		self._empezar()
		if entrada.es_carpeta or not etiquetas.es_audio(entrada.nombre):
			return None
		local = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if not local:
			return None
		try:
			return self.cache.leer(local)
		except (etiquetas.ErrorEtiquetas, OSError):
			log.debug("Sin etiquetas en %s", local, exc_info=True)
			return None

	def _extractor(self, columna: str) -> Callable[[Any, Any, Any], str | None]:
		def extraer(entrada: Any, proveedor: Any, _cancelacion: Any) -> str | None:
			datos = self._datos(entrada, proveedor)
			if datos is None:
				return None
			if columna == "duracion":
				return etiquetas.texto_duracion(datos.get("duracion_s", "")) or None
			if columna == "pista":
				return datos.get("pista", "").split("/", 1)[0].strip() or None
			if columna == "portada":
				return _("Sí") if datos.get("portada") == "si" else _("No")
			if columna == "bitrate":
				valor = datos.get("bitrate", "")
				return str(round(int(valor) / 1000)) if valor.isdigit() else None
			return datos.get(columna) or None

		return extraer

	def _lineas_info(self, entrada: Any, proveedor: Any) -> list[str]:
		datos = self._datos(entrada, proveedor)
		return etiquetas.lineas(datos) if datos is not None else []

	def _mascara(self, campo: str) -> Callable[[Any, Any], str | None]:
		def valor(entrada: Any, proveedor: Any) -> str | None:
			datos = self._datos(entrada, proveedor)
			if datos is None:
				return None
			texto = datos.get(campo, "")
			if campo == "pista":
				texto = etiquetas.numero_pista(texto, 2)
			return texto.translate(_PROHIBIDOS).strip() or None

		return valor

	# ── Elementos de trabajo ─────────────────────────────────────────────────

	def _audios(self, ctx: api.ContextoComplemento, minimo: int = 1) -> tuple[Any, list[str]] | None:
		"""(proveedor, rutas locales) de los elementos de trabajo de audio, o ``None`` tras avisar."""
		self._empezar()
		panel = ctx.objetivo
		proveedor = panel.proveedor
		entradas = [e for e in panel.elementos_trabajo() if not e.es_carpeta and etiquetas.es_audio(e.nombre)]
		if not entradas:
			ctx.anunciar(_("No hay archivos de audio elegidos"), api.RESULTADO)
			return None
		rutas = [proveedor.ruta_local(e.ruta) for e in entradas]
		if any(r is None for r in rutas):
			ctx.anunciar(_("Las etiquetas solo se pueden cambiar en archivos del disco o de la red local"), api.RESULTADO)
			return None
		if len(rutas) < minimo:
			ctx.anunciar(_("Marque al menos {n} archivos de audio").format(n=minimo), api.RESULTADO)
			return None
		return proveedor, [str(r) for r in rutas]

	def _lanzar(self, descripcion: str, proveedor: Any, trabajos: list[tuple[str, Callable[[str], None]]]) -> None:
		operacion = OperacionEtiquetas(descripcion, proveedor, trabajos, self.copias,
			conservar_fechas=bool(self.zc.config.obtener("conservar_fechas", True)), al_cambiar=self.cache.olvidar)

		def al_terminar(op: Any) -> None:
			if op.hechos:
				self.zc.sonidos.sonar("guardado")

		self.zc.lanzar(operacion, al_terminar=al_terminar)

	def _version(self) -> str:
		return str(self.zc.config.obtener("version_id3", "2.3"))

	def _en_hilo(self, trabajo: Callable[[], Any], despues: Callable[[Any], None]) -> None:
		"""Lee en un hilo y sigue en la interfaz (leer etiquetas de muchos archivos no bloquea)."""
		import wx

		def correr() -> None:
			try:
				resultado = trabajo()
			except Exception as error:  # noqa: BLE001 - se informa a la persona
				log.warning("Falló la lectura de etiquetas", exc_info=True)
				mensaje = str(error)
				wx.CallAfter(lambda: self.zc.anunciar(_("No se pudieron leer las etiquetas: {e}").format(e=mensaje), api.ESENCIAL))
				return
			wx.CallAfter(despues, resultado)

		threading.Thread(target=correr, name="zc-metadatos-leer", daemon=True).start()

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _orden_editar(self, ctx: api.ContextoComplemento) -> None:
		elegidos = self._audios(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos

		def leer() -> dict[str, str] | None:
			return dict(self.cache.leer(rutas[0])) if len(rutas) == 1 else None

		self._en_hilo(leer, lambda valores: self._mostrar_editor(proveedor, rutas, valores))

	def _mostrar_editor(self, proveedor: Any, rutas: list[str], valores: dict[str, str] | None) -> None:
		import wx

		from .dialogos import DialogoEditar

		informacion = "\n".join(etiquetas.lineas(valores)[-5:]) if valores is not None else ""
		dialogo = DialogoEditar(self.zc.ui, None, [os.path.basename(r) for r in rutas], valores, informacion)
		try:
			if self.zc.ui.mostrar_modal(dialogo.dialogo) != wx.ID_OK:
				return
			cambios = dialogo.cambios()
		finally:
			dialogo.dialogo.Destroy()
		if not cambios:
			self.zc.anunciar(_("No se cambió ninguna etiqueta"), api.RESULTADO)
			return
		version = self._version()
		self._lanzar(_("Editar las etiquetas de {n}").format(n=_que(rutas)), proveedor,
			[(r, lambda ruta, c=dict(cambios): etiquetas.escribir(ruta, c, version)) for r in rutas])

	def _orden_desde_nombre(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .dialogos import DialogoDesdeNombre

		elegidos = self._audios(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		dialogo = DialogoDesdeNombre(self.zc.ui, None, rutas, self.mascara)
		try:
			if self.zc.ui.mostrar_modal(dialogo.dialogo) != wx.ID_OK:
				return
			self.mascara = dialogo.mascara.GetValue()
			resultados = dict(dialogo.resultados)
		finally:
			dialogo.dialogo.Destroy()
		if not resultados:
			self.zc.anunciar(_("Ningún nombre encaja con la máscara: no se cambió nada"), api.RESULTADO)
			return
		version = self._version()
		self._lanzar(_("Etiquetas desde el nombre de {n}").format(n=_que(list(resultados))), proveedor,
			[(r, lambda ruta, c=campos: etiquetas.escribir(ruta, c, version)) for r, campos in resultados.items()])

	def _orden_numerar(self, ctx: api.ContextoComplemento) -> None:
		elegidos = self._audios(ctx, minimo=2)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		total = len(rutas)
		version = self._version()
		self._lanzar(_("Numerar {n} pistas").format(n=total), proveedor,
			[(r, lambda ruta, n=numero: etiquetas.escribir(ruta, {"pista": f"{n}/{total}"}, version))
				for numero, r in enumerate(rutas, start=1)])

	def _orden_quitar(self, ctx: api.ContextoComplemento) -> None:
		elegidos = self._audios(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		pregunta = (_("¿Quitar todas las etiquetas y la portada de {n}?").format(n=os.path.basename(rutas[0])) if len(rutas) == 1
			else _("¿Quitar todas las etiquetas y la portada de {n} archivos?").format(n=len(rutas)))
		if not self.zc.ui.confirmar(pregunta, _("Quitar las etiquetas"), peligroso=True):
			return
		self._lanzar(_("Quitar las etiquetas de {n}").format(n=_que(rutas)), proveedor, [(r, etiquetas.quitar) for r in rutas])

	def _orden_portada(self, ctx: api.ContextoComplemento) -> None:
		elegidos = self._audios(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		eleccion = self.zc.ui.elegir_opcion(
			_("¿Qué quiere hacer con la portada de {n}?").format(n=_que(rutas)), _("Portada"),
			[_("&Añadir o cambiar la portada..."), _("E&xtraer la portada..."), _("&Quitar la portada")])
		if eleccion == 0:
			self._poner_portada(proveedor, rutas)
		elif eleccion == 1:
			self._extraer_portada(rutas[0])
		elif eleccion == 2:
			version = self._version()
			self._lanzar(_("Quitar la portada de {n}").format(n=_que(rutas)), proveedor,
				[(r, lambda ruta: etiquetas.poner_portada(ruta, b"", version)) for r in rutas])

	def _poner_portada(self, proveedor: Any, rutas: list[str]) -> None:
		import wx

		dialogo = wx.FileDialog(None, _("Elegir la imagen de la portada"), defaultDir=os.path.dirname(rutas[0]),
			wildcard=_("Imágenes JPEG o PNG (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png"), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			imagen = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		try:
			with open(imagen, "rb") as archivo:
				datos = archivo.read(20 * 1024 * 1024 + 1)
			if len(datos) > 20 * 1024 * 1024:
				raise etiquetas.ErrorEtiquetas(_("La imagen pasa de 20 MB: elija una más pequeña"))
			etiquetas.tipo_imagen(datos)
		except (OSError, etiquetas.ErrorEtiquetas) as error:
			self.zc.ui.mostrar_error(str(getattr(error, "strerror", None) or error), _("Portada"))
			return
		version = self._version()
		self._lanzar(_("Poner la portada en {n}").format(n=_que(rutas)), proveedor,
			[(r, lambda ruta: etiquetas.poner_portada(ruta, datos, version)) for r in rutas])

	def _extraer_portada(self, ruta: str) -> None:
		import wx

		try:
			portada = etiquetas.leer_portada(ruta)
		except (etiquetas.ErrorEtiquetas, OSError, ValueError) as error:
			self.zc.ui.mostrar_error(str(error), _("Extraer la portada"))
			return
		if portada is None:
			self.zc.anunciar(_("{n} no tiene portada").format(n=os.path.basename(ruta)), api.RESULTADO)
			return
		datos, mime = portada
		extension = ".png" if "png" in mime else ".jpg"
		dialogo = wx.FileDialog(None, _("Guardar la portada"), defaultDir=os.path.dirname(ruta),
			defaultFile=os.path.splitext(os.path.basename(ruta))[0] + extension, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
			wildcard=_("Imagen (*{e})|*{e}").format(e=extension))
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.GetPath()
		finally:
			dialogo.Destroy()
		try:
			with open(destino, "wb") as archivo:
				archivo.write(datos)
		except OSError as error:
			self.zc.ui.mostrar_error(_("No se pudo guardar la portada: {e}").format(e=error.strerror or error), _("Extraer la portada"))
			return
		self.zc.anunciar(_("Portada guardada en {n}").format(n=os.path.basename(destino)), api.RESULTADO)

	def _orden_exportar(self, ctx: api.ContextoComplemento) -> None:
		import wx

		elegidos = self._audios(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		dialogo = wx.FileDialog(None, _("Exportar la lista de pistas"), defaultDir=os.path.dirname(rutas[0]),
			defaultFile=_("Lista de pistas") + ".txt",
			wildcard=_("Texto (*.txt)|*.txt|CSV con punto y coma (*.csv)|*.csv"), style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.GetPath()
			if dialogo.GetFilterIndex() == 1 and not destino.lower().endswith(".csv"):
				destino = os.path.splitext(destino)[0] + ".csv"
		finally:
			dialogo.Destroy()
		self.zc.lanzar(OperacionExportar(proveedor, rutas, destino, self.cache.leer))

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""El editor (uno y varios archivos) y «Etiquetas desde el nombre», sin mostrarlos (3.12)."""
		from .dialogos import DialogoDesdeNombre, DialogoEditar

		try:
			ui = self.zc.ui
			ui.crear_campo  # noqa: B018 - comprueba que hay interfaz
		except api.NoAdmitido:
			log.info("Sin interfaz de zCommander no se pueden construir los diálogos de etiquetas")
			return []
		uno = DialogoEditar(ui, padre, ["01 - Ana - Canción.mp3"], {"artista": "Ana", "titulo": "Canción"}, "Duración: 3:45")
		varios = DialogoEditar(ui, padre, ["a.mp3", "b.mp3"], None)
		desde = DialogoDesdeNombre(ui, padre, ["C:\\Música\\01 - Ana - Canción.mp3"], MASCARA_POR_DEFECTO)
		return [uno.dialogo, varios.dialogo, desde.dialogo]


def _que(rutas: list[str]) -> str:
	return os.path.basename(rutas[0]) if len(rutas) == 1 else _("{n} archivos").format(n=len(rutas))
