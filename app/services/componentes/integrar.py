# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pendientes de componentes e integración tras actualizar la aplicación (diseño 2.0, 6.6, 6.7 y 14.8). Sin wx.

``main.py`` llama a estas funciones en su sitio del arranque, antes de cargar
ninguna DLL de ``data/bin`` (paso 6 de 14.8):

- ``aplicar_pendientes``: termina o deshace un ``instalando.json`` a medias y
  aplica lo que quedó en ``data/bin/.pendiente/`` (pasos 6 a 8 de 6.6, con
  vuelta atrás si la prueba falla). Devuelve los mensajes que la ventana
  anuncia tras mostrarse.
- ``integrar_entrante``: lo que trae una actualización de la aplicación en
  ``data/bin/.entrante/`` (5.3). Cambia la línea base y, componente a
  componente, instala la base nueva si la activa es más antigua (o es la base
  anterior) y conserva la activa si la persona la actualizó a una más nueva.
  Si la aplicación vuelve a la versión anterior sin confirmar su salud, lo
  integrado se revierte en el siguiente arranque (``integracion.json``).
- ``confirmar_integracion``: la llama el actualizador cuando la versión nueva
  confirma su salud (5.4); borra ``.entrante`` e ``integracion.json``.

Nada suena ni se anuncia por la ventana aquí (aún no la hay): los sonidos que
tocan (``comp.revertido``, ``comp.actualizado``) se guardan para que
``componentes_co.instalar`` los pida tras mostrarse. El aviso hablado «Preparando
los componentes nuevos...» usa la voz mínima que ``main.py`` fija con ``fijar_anunciador``.
"""

from __future__ import annotations

import builtins
import json
import logging
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core import red
from app.core.version import APP_VERSION, NOMBRE_APLICACION
from app.services.componentes import fichas, instalar
from app.services.componentes.estado import Entorno

log = logging.getLogger(__name__)

_candado = threading.Lock()
_sonidos: list[str] = []
_anunciador: list[Callable[[str], None] | None] = [None]


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class ResumenIntegracion:
	"""Lo que hizo ``integrar_entrante`` (se anuncia tras mostrar la ventana)."""

	conservados: list[str] = field(default_factory=list)
	instalados: list[str] = field(default_factory=list)
	revertidos: list[str] = field(default_factory=list)
	mensaje: str = ""


def config_red() -> red.ConfiguracionRed:
	return red.ConfiguracionRed(NOMBRE_APLICACION, APP_VERSION)


def fijar_anunciador(funcion: Callable[[str], None] | None) -> None:
	"""Voz mínima (sin configuración) para «Preparando los componentes nuevos...» (6.7)."""
	_anunciador[0] = funcion


def _anunciar(texto: str) -> None:
	funcion = _anunciador[0]
	if funcion is None:
		log.info("%s", texto)
		return
	try:
		funcion(texto)
	except Exception:  # noqa: BLE001 - sin voz se sigue en silencio
		log.debug("No se pudo anunciar «%s»", texto, exc_info=True)


def _anotar_sonido(resultado: instalar.Resultado) -> None:
	if resultado.sonido:
		with _candado:
			_sonidos.append(resultado.sonido)


def sonidos_pendientes() -> list[str]:
	"""Los sonidos del arranque (``comp.revertido`` primero), una sola vez; los pide la ventana ya mostrada."""
	with _candado:
		lista = sorted(set(_sonidos), key=lambda s: s != "comp.revertido")
		_sonidos.clear()
	return lista


def _instalador(entorno: Entorno) -> instalar.Instalador:
	return instalar.Instalador(entorno, config_red())


# ── Pendientes ──────────────────────────────────────────────────────────────


def aplicar_pendientes(ruta_datos: Path) -> list[str]:
	"""Diario a medias y pendientes de ``data/bin`` (6.6). Mensajes para anunciar tras mostrar la ventana."""
	entorno = Entorno.desde_datos(ruta_datos)
	instalador = _instalador(entorno)
	mensajes: list[str] = []
	try:
		mensaje = instalador.recuperar_diario()
		if mensaje:
			mensajes.append(mensaje)
	except instalar.ErrorComponente as error:
		log.error("No se pudo recuperar el diario de componentes: %s", error.mensaje)
		mensajes.append(error.mensaje)
	for id in instalador.pendientes():
		try:
			resultado = instalador.aplicar_pendiente(id)
		except Exception as error:  # noqa: BLE001 - un pendiente roto no impide arrancar
			log.exception("No se pudo aplicar el pendiente de %s", id)
			mensajes.append(_("No se pudo aplicar la actualización pendiente de {c}: {e}").format(c=id, e=error))
			continue
		_anotar_sonido(resultado)
		if resultado.estado == instalar.ACTUALIZADO:
			nombre = (instalador.ficha(id) or {}).get("nombre", id)
			mensajes.append(_("{c} se actualizó a {v}").format(c=nombre, v=resultado.version))
		elif resultado.mensaje and resultado.estado != instalar.SIN_CAMBIOS:
			mensajes.append(resultado.mensaje)
	if entorno.temporal.is_dir():
		instalar._borrar(entorno.temporal)
	return mensajes


# ── Entrantes de una actualización de la aplicación ──────────────────────────


def hay_entrante(ruta_datos: Path) -> bool:
	"""¿Trae algo que integrar la actualización recién instalada?"""
	return (Entorno.desde_datos(ruta_datos).entrante / fichas.NOMBRE_LINEA_BASE).is_file()


def _leer_integracion(entorno: Entorno) -> dict | None:
	try:
		datos = json.loads(entorno.integracion.read_text(encoding="utf-8"))
		return datos if isinstance(datos, dict) else None
	except FileNotFoundError:
		return None
	except (OSError, ValueError):
		log.warning("integracion.json ilegible", exc_info=True)
		return None


def _revertir_integracion(entorno: Entorno, datos: dict) -> ResumenIntegracion:
	"""La aplicación volvió a la versión anterior sin confirmar la salud de la nueva: se deshace lo integrado (6.7)."""
	instalador = _instalador(entorno)
	revertidos: list[str] = []
	for sustituido in reversed(datos.get("sustituidos", [])):
		id = str(sustituido.get("id", ""))
		respaldo = entorno.respaldo / id / str(sustituido.get("respaldo", ""))
		if not id or not (respaldo / "archivos").is_dir():
			log.warning("No está el respaldo de %s para revertir la integración", id)
			continue
		try:
			ficha_respaldo = json.loads((respaldo / "ficha.json").read_text(encoding="utf-8")).get("ficha", {})
			temporal = entorno.temporal / id / "respaldo"
			instalar._borrar(temporal)
			shutil.copytree(respaldo / "archivos", temporal)
			actual = instalador.ficha(id) or ficha_respaldo
			resultado = instalador.instalar_preparado(actual, ficha_respaldo, temporal, mezclar=False, con_en_uso=False)
			instalar._borrar(temporal)
		except (OSError, ValueError, instalar.ErrorComponente):
			log.exception("No se pudo revertir %s", id)
			continue
		if resultado.estado == instalar.ACTUALIZADO:
			revertidos.append(id)
	anterior = Path(str(datos.get("linea_base_anterior", "")))
	if anterior.name and (entorno.respaldo / anterior.name).is_file():
		shutil.copy2(entorno.respaldo / anterior.name, entorno.linea_base)
	entorno.integracion.unlink(missing_ok=True)
	instalar._borrar(entorno.entrante)
	mensaje = ""
	if revertidos:
		mensaje = _("zCommander volvió a la versión anterior y sus componentes también: {l}.").format(l=", ".join(revertidos))
		with _candado:
			_sonidos.append("comp.revertido")
	log.info("Integración revertida: %s", revertidos)
	return ResumenIntegracion(revertidos=revertidos, mensaje=mensaje)


def _misma_base(activa: dict | None, base: dict | None) -> bool:
	return bool(activa and base) and fichas.mapa_sumas(activa.get("archivos", [])) == fichas.mapa_sumas(base.get("archivos", []))


def integrar_entrante(ruta_datos: Path) -> ResumenIntegracion | None:
	"""Integra lo que trajo una actualización de la aplicación (6.7). ``None`` si no hay nada que hacer."""
	entorno = Entorno.desde_datos(ruta_datos)
	previa = _leer_integracion(entorno)
	if previa is not None and str(previa.get("version_app", "")) != APP_VERSION:
		return _revertir_integracion(entorno, previa)
	nueva_base_archivo = entorno.entrante / fichas.NOMBRE_LINEA_BASE
	if not nueva_base_archivo.is_file():
		return None
	_anunciar(_("Preparando los componentes nuevos de zCommander..."))
	try:
		nueva_base = fichas.leer(nueva_base_archivo)
	except (OSError, ValueError):
		log.exception("La línea base que trae la actualización no se puede leer; se conservan los componentes")
		return ResumenIntegracion(mensaje=_("No se pudieron integrar los componentes nuevos: su lista está dañada."))
	problemas = fichas.validar(nueva_base, linea_base=True)
	if problemas:
		log.error("Línea base entrante no válida: %s", problemas)
		return ResumenIntegracion(mensaje=_("No se pudieron integrar los componentes nuevos: su lista no es válida."))
	base_anterior = fichas.leer_o_vacio(entorno.linea_base)
	nombre_copia = f"linea_base-{base_anterior.get('aplicacion') or 'anterior'}.json"
	entorno.respaldo.mkdir(parents=True, exist_ok=True)
	if entorno.linea_base.is_file():
		shutil.copy2(entorno.linea_base, entorno.respaldo / nombre_copia)
	instalador = _instalador(entorno)
	conservados: list[str] = []
	instalados: list[str] = []
	revertidos: list[str] = []
	sustituidos: list[dict] = []
	mensajes: list[str] = []
	# Las fichas activas se leen ANTES de cambiar la línea base (sin componentes.json, lo activo es la base anterior).
	if entorno.instalados.is_file():
		lista_activas = fichas.leer_o_vacio(entorno.instalados).get("componentes", [])
	else:
		lista_activas = [fichas.sin_campos_de_base(f) for f in base_anterior.get("componentes", []) if isinstance(f, dict)]
	activas = {f["id"]: f for f in lista_activas if isinstance(f, dict) and f.get("id")}
	if not entorno.instalados.is_file() and activas:
		fichas.escribir(entorno.instalados, {"formato": fichas.FORMATO, "componentes": list(activas.values())})
	shutil.copy2(nueva_base_archivo, entorno.linea_base)
	nueva_base_archivo.unlink()
	for base in nueva_base.get("componentes", []):
		id = str(base.get("id", ""))
		origen = entorno.entrante / str(base.get("carpeta") or id)
		if not id or not origen.is_dir():
			continue
		nombre = str(base.get("nombre") or id)
		activa = activas.get(id)
		carpeta_activa = entorno.bin / str((activa or base).get("carpeta") or id)
		anterior = fichas.buscar(base_anterior, id)
		instalar_base = (activa is None or not carpeta_activa.is_dir()
			or fichas.comparar_versiones(str(base.get("version", "")), str(activa.get("version", ""))) > 0
			or (_misma_base(activa, anterior) and not _misma_base(activa, base)))
		if not instalar_base:
			if not _misma_base(activa, base):
				conservados.append(id)
				mensajes.append(_("Se conserva {c} {v}, más nueva que la que trae zCommander ({b}).").format(
					c=nombre, v=activa.get("version", ""), b=base.get("version", "")))
			continue
		ficha_nueva = fichas.sin_campos_de_base(base)
		ficha_actual = activa or ficha_nueva
		try:
			resultado = instalador.instalar_preparado(ficha_actual, ficha_nueva, origen, mezclar=False, con_en_uso=False,
				respaldar=carpeta_activa.is_dir())
		except Exception as error:  # noqa: BLE001 - un componente que falla no impide arrancar
			log.exception("No se pudo integrar %s", id)
			mensajes.append(_("No se pudo integrar {c}: {e}").format(c=nombre, e=error))
			continue
		_anotar_sonido(resultado)
		if activa is not None and carpeta_activa.is_dir():
			sustituidos.append({"id": id, "respaldo": instalar._nombre_respaldo(activa)})
		if resultado.estado == instalar.ACTUALIZADO:
			instalados.append(id)
		elif resultado.estado == instalar.REVERTIDO:
			revertidos.append(id)
			mensajes.append(resultado.mensaje)
		elif resultado.mensaje:
			mensajes.append(resultado.mensaje)
	fichas.escribir(entorno.integracion, {"version_app": APP_VERSION, "sustituidos": sustituidos, "linea_base_anterior": nombre_copia})
	if instalados:
		mensajes.insert(0, _("Componentes actualizados con zCommander: {l}.").format(l=", ".join(instalados)))
	log.info("Integración: instalados %s, conservados %s, revertidos %s", instalados, conservados, revertidos)
	return ResumenIntegracion(conservados, instalados, revertidos, " ".join(mensajes))


def confirmar_integracion() -> None:
	"""La versión nueva confirmó su salud (5.4): se borran ``.entrante`` e ``integracion.json`` y se podan los respaldos."""
	entorno = Entorno.actual()
	datos = _leer_integracion(entorno)
	instalar._borrar(entorno.entrante)
	entorno.integracion.unlink(missing_ok=True)
	if datos:
		instalador = _instalador(entorno)
		for sustituido in datos.get("sustituidos", []):
			if sustituido.get("id"):
				instalador.podar_respaldos(str(sustituido["id"]))
	log.info("Integración de componentes confirmada")
