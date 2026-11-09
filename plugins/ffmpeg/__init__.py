# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conversor multimedia con FFmpeg (zc.ffmpeg, diseño 2.0, 11.6).

Convierte audio y vídeo con perfiles, extrae el audio de un vídeo, recorta,
normaliza el volumen (``loudnorm`` de dos pasadas, EBU R128), une archivos de
audio y da la información técnica, con el componente ``ffmpeg`` (``ffmpeg.exe``
y ``ffprobe.exe``, localizados con ``zc.componentes`` en cada uso). Cada
conversión es una operación del motor (``OperacionFFmpeg``).
"""

from __future__ import annotations

import builtins
import logging
import os
import tempfile
import threading
from collections.abc import Callable
from typing import Any

from app.plugins import api

from . import perfiles, sonda
from .operacion import OperacionFFmpeg, Trabajo

log = logging.getLogger(__name__)

ORDENES = ("convertir", "extraer_audio", "recortar", "normalizar", "informacion", "unir")
MULTIMEDIA = frozenset({"mp3", "wav", "wma", "m4a", "m4b", "aac", "flac", "ogg", "oga", "opus", "aif", "aiff", "ac3", "amr",
	"ape", "wv", "mka", "mp2", "mpc", "tta", "caf", "mid", "midi", "mp4", "m4v", "mkv", "avi", "wmv", "mov", "webm", "mpg", "mpeg",
	"ts", "m2ts", "flv", "3gp", "ogv", "vob"})
FALTA = "Falta el componente FFmpeg: Opciones, Componentes externos, Restaurar"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def es_multimedia(nombre: str) -> bool:
	return os.path.splitext(nombre)[1].lower().lstrip(".") in MULTIMEDIA


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))
		zc.info.lineas(self._lineas_info)

	# ── Componente ───────────────────────────────────────────────────────────

	def _ejecutable(self, nombre: str) -> str:
		"""Ruta de ``ffmpeg.exe`` o ``ffprobe.exe``; se pide en cada uso (6.3). ``NoAdmitido`` si falta."""
		return str(self.zc.componentes.ejecutable("ffmpeg", nombre))

	def _hay_ffmpeg(self, ctx: api.ContextoComplemento | None = None) -> bool:
		if self.zc.componentes.disponible("ffmpeg"):
			return True
		mensaje = _(FALTA)
		if ctx is not None:
			ctx.anunciar(mensaje, api.ESENCIAL)
		else:
			self.zc.anunciar(mensaje, api.ESENCIAL)
		return False

	def sondear(self, ruta: str, tiempo_s: float = 30) -> sonda.Informacion:
		"""[trabajo] ``ffprobe`` de un archivo local."""
		resultado = self.zc.ejecutar_programa(perfiles.argumentos_sonda(self._ejecutable("ffprobe.exe"), ruta), tiempo_s=tiempo_s)
		if resultado.codigo != 0:
			raise api.ErrorArchivos(sonda.traducir_error(resultado.errores))
		return sonda.analizar(resultado.salida)

	def _duracion(self, ruta: str) -> float:
		return self.sondear(ruta).duracion

	def _lineas_info(self, entrada: Any, proveedor: Any) -> list[str]:
		if entrada.es_carpeta or not self.zc.componentes.disponible("ffmpeg"):
			return []
		local = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if not local:
			return []
		try:
			return sonda.lineas(self.sondear(local, tiempo_s=1.0))
		except (api.ErrorArchivos, ValueError, OSError):
			log.debug("Sin información técnica de %s", local, exc_info=True)
			return []

	# ── Elementos y carpetas ─────────────────────────────────────────────────

	def _elegidos(self, ctx: api.ContextoComplemento, minimo: int = 1) -> tuple[Any, list[str]] | None:
		panel = ctx.objetivo
		proveedor = panel.proveedor
		entradas = [e for e in panel.elementos_trabajo() if not e.es_carpeta and es_multimedia(e.nombre)]
		if not entradas:
			ctx.anunciar(_("No hay archivos de audio o vídeo elegidos"), api.RESULTADO)
			return None
		rutas = [proveedor.ruta_local(e.ruta) for e in entradas]
		if any(r is None for r in rutas):
			ctx.anunciar(_("FFmpeg solo trabaja con archivos del disco o de la red local"), api.RESULTADO)
			return None
		if len(rutas) < minimo:
			ctx.anunciar(_("Marque al menos {n} archivos").format(n=minimo), api.RESULTADO)
			return None
		return proveedor, [str(r) for r in rutas]

	def carpeta_salida(self, ctx: api.ContextoComplemento, origen: str) -> str:
		"""Según ``carpeta_salida``: la del otro panel (si es local), la del original o la elegida."""
		opcion = str(self.zc.config.obtener("carpeta_salida", "otro_panel"))
		if opcion == "elegida":
			elegida = str(self.zc.config.obtener("carpeta_elegida", "") or "")
			if elegida and os.path.isdir(elegida):
				return elegida
		if opcion in ("otro_panel", "elegida"):
			pasivo = ctx.pasivo
			try:
				local = pasivo.proveedor.ruta_local(pasivo.ruta) if pasivo.ruta else None
			except Exception:  # noqa: BLE001 - un panel sin ruta local no sirve de destino
				log.debug("El otro panel no tiene ruta local", exc_info=True)
				local = None
			if local and os.path.isdir(local):
				return local
		return os.path.dirname(origen)

	def _hilos(self) -> int:
		return int(self.zc.config.obtener("hilos", 0) or 0)

	def _lanzar(self, descripcion: str, proveedor: Any, trabajos: list[Trabajo], *, en_cola: bool = False,
			politica: str = "preguntar", conservar_fechas: bool = False) -> None:
		operacion = OperacionFFmpeg(descripcion, proveedor, trabajos, ejecutar=self.zc.ejecutar_programa, duracion_de=self._duracion,
			politica=api.Politica(politica), conservar_fechas=conservar_fechas)
		self.zc.lanzar(operacion, en_cola=en_cola)

	def _en_hilo(self, trabajo: Callable[[], Any], despues: Callable[[Any], None]) -> None:
		import wx

		def correr() -> None:
			try:
				resultado = trabajo()
			except (api.ErrorArchivos, ValueError, OSError) as error:
				mensaje = str(getattr(error, "strerror", None) or error)
				self.zc.anunciar(mensaje, api.ESENCIAL)
				return
			except Exception as error:  # noqa: BLE001 - se informa a la persona
				log.warning("Falló un trabajo del conversor", exc_info=True)
				self.zc.anunciar(_("FFmpeg falló: {e}").format(e=error), api.ESENCIAL)
				return
			wx.CallAfter(despues, resultado)

		threading.Thread(target=correr, name="zc-ffmpeg", daemon=True).start()

	# ── Convertir ────────────────────────────────────────────────────────────

	def _orden_convertir(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .ventanas.convertir import ID_EN_COLA, DialogoConvertir

		if not self._hay_ffmpeg(ctx):
			return
		elegidos = self._elegidos(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		dialogo = DialogoConvertir(self.zc.ui, None, len(rutas), str(self.zc.config.obtener("perfil", "mp3_192")),
			self.carpeta_salida(ctx, rutas[0]), conservar_etiquetas=bool(self.zc.config.obtener("conservar_etiquetas", True)),
			argumentos=next(iter(self.zc.config.obtener("perfiles_propios", []) or []), ""))
		try:
			while True:
				respuesta = self.zc.ui.mostrar_modal(dialogo.dialogo)
				if respuesta not in (wx.ID_OK, ID_EN_COLA):
					return
				try:
					trabajos = self._trabajos_convertir(dialogo, rutas)
				except (perfiles.ErrorArgumentos, OSError) as error:
					self.zc.ui.mostrar_error(str(error), _("Convertir audio o vídeo"), padre=dialogo.dialogo)
					continue
				break
			perfil = perfiles.juntar_perfil(dialogo.id_perfil, dialogo.id_calidad)
			self.zc.config.establecer("perfil", perfil)
			if dialogo.id_perfil == "personalizado":
				texto = dialogo.argumentos.GetValue().strip()
				previos = [p for p in (self.zc.config.obtener("perfiles_propios", []) or []) if p != texto]
				self.zc.config.establecer("perfiles_propios", [texto, *previos][:10])
			nombre = perfiles.PERFILES[dialogo.id_perfil].nombre
			self._lanzar(_("Convertir {q} a {p}").format(q=_que(rutas), p=nombre), proveedor, trabajos, en_cola=respuesta == ID_EN_COLA,
				politica=dialogo.valor_si_existe, conservar_fechas=dialogo.fechas.GetValue())
		finally:
			dialogo.dialogo.Destroy()

	def _trabajos_convertir(self, dialogo: Any, rutas: list[str]) -> list[Trabajo]:
		carpeta = dialogo.carpeta.GetValue().strip()
		if not carpeta or not os.path.isdir(carpeta):
			raise perfiles.ErrorArgumentos(_("La carpeta de salida no existe: {c}").format(c=carpeta))
		perfil, calidad = dialogo.id_perfil, dialogo.id_calidad
		personalizados: list[str] = []
		extension = perfiles.PERFILES[perfil].extension
		if perfil == "personalizado":
			personalizados = perfiles.validar_personalizados(dialogo.argumentos.GetValue(), rutas[0], carpeta)
		ffmpeg = self._ejecutable("ffmpeg.exe")
		etiquetas = dialogo.etiquetas.GetValue()
		hilos = self._hilos()
		trabajos = []
		for contador, origen in enumerate(rutas, start=1):
			extension_salida = extension or os.path.splitext(origen)[1]
			if perfil == "personalizado":
				perfiles.validar_personalizados(dialogo.argumentos.GetValue(), origen, carpeta)
			destino = os.path.join(carpeta, perfiles.nombre_salida(dialogo.nombre.GetValue(), origen, extension_salida, contador))

			def argumentos(temporal: str, origen: str = origen) -> list[str]:
				return perfiles.argumentos_convertir(ffmpeg, origen, temporal, perfil, calidad, conservar_etiquetas=etiquetas,
					hilos=hilos, personalizados=personalizados)

			trabajos.append(Trabajo(origen, destino, [argumentos]))
		return trabajos

	# ── Extraer el audio ─────────────────────────────────────────────────────

	def _orden_extraer_audio(self, ctx: api.ContextoComplemento) -> None:
		if not self._hay_ffmpeg(ctx):
			return
		elegidos = self._elegidos(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		carpeta = self.carpeta_salida(ctx, rutas[0])
		ffmpeg = self._ejecutable("ffmpeg.exe")
		hilos = self._hilos()

		def preparar() -> list[Trabajo]:
			trabajos = []
			for origen in rutas:
				audio = self.sondear(origen).audio
				if not audio:
					self.zc.anunciar(_("{n} no tiene audio").format(n=os.path.basename(origen)), api.RESULTADO)
					continue
				extension = perfiles.EXTENSION_POR_CODEC.get(audio[0].codec, "")
				base = os.path.splitext(os.path.basename(origen))[0]
				alternativas: list[Callable[[str], list[str]]] = []
				if extension:
					alternativas.append(lambda t, o=origen: perfiles.argumentos_extraer_audio(ffmpeg, o, t, True, hilos=hilos))
				else:
					extension = ".mp3"
				# Si copiar el flujo no cabe en ese contenedor, se convierte a MP3 con el mismo nombre de salida.
				alternativas.append(lambda t, o=origen: perfiles.argumentos_extraer_audio(ffmpeg, o, t, False, hilos=hilos))
				trabajos.append(Trabajo(origen, os.path.join(carpeta, base + extension), alternativas))
			return trabajos

		def lanzar(trabajos: list[Trabajo]) -> None:
			if trabajos:
				self._lanzar(_("Extraer el audio de {q}").format(q=_que([t.origen for t in trabajos])), proveedor, trabajos)

		self._en_hilo(preparar, lanzar)

	# ── Recortar ─────────────────────────────────────────────────────────────

	def _orden_recortar(self, ctx: api.ContextoComplemento) -> None:
		if not self._hay_ffmpeg(ctx):
			return
		elegidos = self._elegidos(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		origen = rutas[0]
		carpeta = self.carpeta_salida(ctx, origen)
		self._en_hilo(lambda: self.sondear(origen).duracion, lambda duracion: self._pedir_recorte(proveedor, origen, carpeta, duracion))

	def _pedir_recorte(self, proveedor: Any, origen: str, carpeta: str, duracion: float) -> None:
		import wx

		from .ventanas.convertir import DialogoRecortar

		dialogo = DialogoRecortar(self.zc.ui, None, os.path.basename(origen), sonda.duracion_texto(duracion) if duracion else "")
		try:
			while True:
				if self.zc.ui.mostrar_modal(dialogo.dialogo) != wx.ID_OK:
					return
				try:
					inicio = sonda.interpretar_tiempo(dialogo.inicio.GetValue())
					fin = sonda.interpretar_tiempo(dialogo.fin.GetValue())
					if fin <= inicio:
						raise ValueError(_("El fin tiene que ser posterior al inicio"))
					if duracion and inicio >= duracion:
						raise ValueError(_("El inicio pasa del final del archivo"))
				except ValueError as error:
					self.zc.ui.mostrar_error(str(error), _("Recortar"), padre=dialogo.dialogo)
					continue
				break
			recodificar = dialogo.recodificar.GetValue()
		finally:
			dialogo.dialogo.Destroy()
		ffmpeg = self._ejecutable("ffmpeg.exe")
		hilos = self._hilos()
		base, extension = os.path.splitext(os.path.basename(origen))
		destino = os.path.join(carpeta, _("{n} (recorte)").format(n=base) + extension)
		alternativas = [lambda t: perfiles.argumentos_recortar(ffmpeg, origen, t, inicio, fin, False, hilos=hilos)]
		if not recodificar:
			alternativas.insert(0, lambda t: perfiles.argumentos_recortar(ffmpeg, origen, t, inicio, fin, True, hilos=hilos))
		trabajo = Trabajo(origen, destino, alternativas, duracion=fin - inicio)
		self._lanzar(_("Recortar {n}").format(n=os.path.basename(origen)), proveedor, [trabajo])

	# ── Normalizar ───────────────────────────────────────────────────────────

	def _orden_normalizar(self, ctx: api.ContextoComplemento) -> None:
		if not self._hay_ffmpeg(ctx):
			return
		elegidos = self._elegidos(ctx)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		objetivo = float(self.zc.config.obtener("normalizar_lufs", -16.0))
		carpeta = self.carpeta_salida(ctx, rutas[0])
		texto_objetivo = f"{objetivo:g}".replace(".", ",")
		if not self.zc.ui.confirmar(_("¿Normalizar el volumen de {q} a {o} LUFS? Se crean copias normalizadas en {c}; los originales "
				"no cambian.").format(q=_que(rutas), o=texto_objetivo, c=carpeta), _("Normalizar el volumen")):
			return
		ffmpeg = self._ejecutable("ffmpeg.exe")
		hilos = self._hilos()
		trabajos = []
		for origen in rutas:
			base, extension = os.path.splitext(os.path.basename(origen))
			destino = os.path.join(carpeta, _("{n} (normalizado)").format(n=base) + extension)
			trabajos.append(Trabajo(origen, destino, [], preparar=self._preparar_normalizar(ffmpeg, origen, objetivo, hilos)))
		self._lanzar(_("Normalizar el volumen de {q}").format(q=_que(rutas)), proveedor, trabajos)

	def _preparar_normalizar(self, ffmpeg: str, origen: str, objetivo: float, hilos: int) -> Callable[[Any], list[Any]]:
		def preparar(ctx: Any) -> list[Callable[[str], list[str]]]:
			"""Primera pasada (medir) en el hilo de la operación; devuelve la segunda."""
			informacion = self.sondear(origen)
			frecuencia = informacion.audio[0].frecuencia if informacion.audio else 48000
			resultado = self.zc.ejecutar_programa(perfiles.argumentos_medir_volumen(ffmpeg, origen, objetivo), tiempo_s=24 * 3600,
				cancelacion=ctx.cancelado)
			if getattr(resultado, "cancelado", False):
				raise api.Cancelado()
			if resultado.codigo != 0:
				raise ValueError(sonda.traducir_error(resultado.errores))
			medidas = sonda.medidas_loudnorm(resultado.errores)
			return [lambda t: perfiles.argumentos_normalizar(ffmpeg, origen, t, objetivo, medidas, frecuencia, hilos=hilos)]

		return preparar

	# ── Información técnica ──────────────────────────────────────────────────

	def _orden_informacion(self, ctx: api.ContextoComplemento) -> None:
		if not self._hay_ffmpeg(ctx):
			return
		cursor = ctx.objetivo.cursor()
		if cursor is None or cursor.es_carpeta:
			ctx.anunciar(_("Ponga el cursor en un archivo de audio o vídeo"), api.RESULTADO)
			return
		local = ctx.objetivo.proveedor.ruta_local(cursor.ruta)
		if not local:
			ctx.anunciar(_("FFmpeg solo trabaja con archivos del disco o de la red local"), api.RESULTADO)
			return
		nombre = cursor.nombre
		self._en_hilo(lambda: self.sondear(local), lambda info: self.zc.ui.mostrar_texto(
			_("Información técnica de {n}").format(n=nombre), sonda.texto(info, nombre)))

	# ── Unir ─────────────────────────────────────────────────────────────────

	def _orden_unir(self, ctx: api.ContextoComplemento) -> None:
		if not self._hay_ffmpeg(ctx):
			return
		elegidos = self._elegidos(ctx, minimo=2)
		if elegidos is None:
			return
		proveedor, rutas = elegidos
		extensiones = {os.path.splitext(r)[1].lower() for r in rutas}
		if len(extensiones) > 1:
			ctx.anunciar(_("Para unir, todos los archivos tienen que ser del mismo formato (hay {e})").format(
				e=", ".join(sorted(extensiones))), api.RESULTADO)
			return
		extension = extensiones.pop()
		carpeta = self.carpeta_salida(ctx, rutas[0])
		base = os.path.splitext(os.path.basename(rutas[0]))[0]
		nombre = self.zc.ui.pedir_texto(_("&Nombre del archivo unido:"), _("Unir archivos de audio"), _("{n} (unido)").format(n=base))
		if not nombre or not nombre.strip():
			return
		try:
			nombre_final = perfiles.nombre_salida(nombre.strip(), rutas[0], extension)
		except perfiles.ErrorArgumentos as error:
			self.zc.ui.mostrar_error(str(error), _("Unir archivos de audio"))
			return
		ffmpeg = self._ejecutable("ffmpeg.exe")
		hilos = self._hilos()
		descriptor, lista = tempfile.mkstemp(prefix="zc-unir-", suffix=".txt", dir=str(self.zc.cache))
		with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
			archivo.write(perfiles.lista_concat(rutas))
		total = sum(os.path.getsize(r) for r in rutas if os.path.isfile(r))
		trabajo = Trabajo(rutas[0], os.path.join(carpeta, nombre_final), [lambda t: perfiles.argumentos_unir(ffmpeg, lista, t, hilos=hilos)],
			tamano=total, temporales=[lista])
		self._duracion_total(rutas, trabajo, lambda: self._lanzar(_("Unir {n} archivos").format(n=len(rutas)), proveedor, [trabajo]))

	def _duracion_total(self, rutas: list[str], trabajo: Trabajo, despues: Callable[[], None]) -> None:
		def medir() -> float:
			total = 0.0
			for ruta in rutas:
				try:
					total += self._duracion(ruta)
				except (api.ErrorArchivos, ValueError, OSError):
					log.debug("Sin duración de %s", ruta, exc_info=True)
			return total

		def seguir(total: float) -> None:
			trabajo.duracion = total or -1
			despues()

		self._en_hilo(medir, seguir)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""Los diálogos «Convertir» y «Recortar», sin mostrarlos (3.12)."""
		from .ventanas.convertir import DialogoConvertir, DialogoRecortar

		try:
			ui = self.zc.ui
			ui.crear_campo  # noqa: B018 - comprueba que hay interfaz
		except api.NoAdmitido:
			log.info("Sin interfaz de zCommander no se pueden construir los diálogos del conversor")
			return []
		convertir = DialogoConvertir(ui, padre, 3, "mp3_192", "C:\\")
		recortar = DialogoRecortar(ui, padre, "prueba.mp3", "3:45")
		return [convertir.dialogo, recortar.dialogo]


def _que(rutas: list[str]) -> str:
	return os.path.basename(rutas[0]) if len(rutas) == 1 else _("{n} archivos").format(n=len(rutas))
