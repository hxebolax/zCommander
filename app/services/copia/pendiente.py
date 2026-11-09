# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Restauración pendiente al arrancar (diseño 2.0, 7.6 y 14.8). Sin wx.

Las partes que se aplican «Al reiniciar» (preferencias, teclas, sesión,
conexiones, complementos) no se pueden escribir con zCommander abierto: la
configuración, los secretos y los complementos ya están cargados y se
guardarían encima. Por eso restaurar las prepara en
``data/config/.restauracion_pendiente/`` (la copia, ``copia.zcbackup``, y
``restaurar.json`` con lo elegido y los secretos ya descifrados y vueltos a
proteger con DPAPI) y ``main.py`` llama a ``aplicar_pendiente`` en el arranque
siguiente, **antes** de cargar la configuración.

- Si se preparó con «Más tarde» (sin ``reiniciar_ahora``), se pregunta con
  ``preguntar`` (aplicar, descartar o después). Sin ``preguntar`` (modo
  tarea, primer arranque tras actualizar) se deja para otro arranque.
- La copia automática previa se crea **dentro** de ``aplicar_pendiente``, justo
  antes de aplicar: guarda lo que la persona cambió después de prepararla.
- Si algo falla a medias, se vuelve a esa copia y se explica. La carpeta
  pendiente se borra siempre tras intentarlo, para no fallar en cada arranque.
- Nunca lanza: ``main.py`` sigue arrancando pase lo que pase.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


CARPETA = ".restauracion_pendiente"
COPIA = "copia.zcbackup"
DATOS = "restaurar.json"
VERSION = 1


@dataclass(frozen=True)
class ResultadoRestauracion:
	ok: bool
	mensaje: str
	partes: list[str] = field(default_factory=list)
	copia_previa: Path | None = None


@dataclass(frozen=True)
class InfoPendiente:
	"""Lo que recibe ``preguntar``, que devuelve ``"aplicar"``, ``"descartar"`` o ``"despues"``."""

	fecha: datetime
	descripcion: str
	partes: list[str] = field(default_factory=list)


def carpeta_pendiente(ruta_datos: Path) -> Path:
	return Path(ruta_datos) / "config" / CARPETA


def _escribir_datos(carpeta: Path, datos: dict) -> None:
	temporal = carpeta / f"{DATOS}.{os.getpid()}.tmp"
	temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
	os.replace(temporal, carpeta / DATOS)


def _suma(ruta: Path) -> str:
	suma = hashlib.sha256()
	with open(ruta, "rb") as entrada:
		while bloque := entrada.read(1024 * 1024):
			suma.update(bloque)
	return suma.hexdigest()


def preparar_pendiente(ruta_copia: Path, plan, secretos: dict[str, str] | None, ruta_datos: Path,
		descripcion: str = "", reiniciar_ahora: bool = False) -> InfoPendiente:
	"""Deja la restauración lista para el siguiente arranque (sustituye otra pendiente que hubiera)."""
	from app.services.copia import cifrado

	carpeta = carpeta_pendiente(ruta_datos)
	temporal = carpeta.with_name(f"{CARPETA}.{os.getpid()}.tmp")
	shutil.rmtree(temporal, ignore_errors=True)
	temporal.mkdir(parents=True)
	try:
		shutil.copyfile(ruta_copia, temporal / COPIA)
		protegidos = None
		if secretos is not None:
			protegidos = base64.b64encode(cifrado.proteger_local(
				json.dumps(secretos, ensure_ascii=False).encode("utf-8"))).decode("ascii")
		fecha = datetime.now()
		_escribir_datos(temporal, {
			"version": VERSION, "fecha": fecha.isoformat(timespec="seconds"), "descripcion": descripcion,
			"plan": plan.a_dict(), "reiniciar_ahora": bool(reiniciar_ahora), "secretos": protegidos,
			"sha256": _suma(temporal / COPIA), "origen": Path(ruta_copia).name,
		})
		shutil.rmtree(carpeta, ignore_errors=True)
		os.replace(temporal, carpeta)
	except BaseException:
		shutil.rmtree(temporal, ignore_errors=True)
		raise
	log.info("Restauración preparada para el siguiente arranque: partes %s", ", ".join(plan.partes))
	return InfoPendiente(fecha.replace(microsecond=0), descripcion, list(plan.partes))


def _leer(ruta_datos: Path) -> dict | None:
	"""Datos de la pendiente; ``{"_danada": True}`` si la carpeta existe pero no se puede usar."""
	carpeta = carpeta_pendiente(ruta_datos)
	if not carpeta.is_dir():
		return None
	try:
		datos = json.loads((carpeta / DATOS).read_text(encoding="utf-8"))
		if not isinstance(datos, dict) or not isinstance(datos.get("plan"), dict) or not (carpeta / COPIA).is_file():
			raise ValueError("restaurar.json incompleto")
		return datos
	except (OSError, ValueError):
		log.warning("La restauración pendiente de %s está dañada", carpeta, exc_info=True)
		return {"_danada": True}


def _info(datos: dict) -> InfoPendiente:
	try:
		fecha = datetime.fromisoformat(str(datos.get("fecha", "")))
	except ValueError:
		fecha = datetime.now().replace(microsecond=0)
	partes = datos["plan"].get("partes", [])
	return InfoPendiente(fecha, str(datos.get("descripcion", "")), [str(p) for p in partes] if isinstance(partes, list) else [])


def _borrar(ruta_datos: Path) -> None:
	shutil.rmtree(carpeta_pendiente(ruta_datos), ignore_errors=True)


def consultar_pendiente(ruta_datos: Path) -> InfoPendiente | None:
	"""Datos de la restauración pendiente sin aplicar nada (``None`` si no hay o está dañada)."""
	datos = _leer(Path(ruta_datos))
	if datos is None or datos.get("_danada"):
		return None
	return _info(datos)


def decidir_pendiente(ruta_datos: Path, decision: str) -> None:
	"""``"aplicar"``: se aplicará en el próximo arranque sin preguntar. ``"descartar"``: se borra."""
	ruta_datos = Path(ruta_datos)
	if decision == "descartar":
		_borrar(ruta_datos)
		log.info("Restauración pendiente descartada")
		return
	if decision != "aplicar":
		log.warning("Decisión desconocida sobre la restauración pendiente: %r", decision)
		return
	datos = _leer(ruta_datos)
	if datos is None or datos.get("_danada"):
		return
	datos["reiniciar_ahora"] = True
	_escribir_datos(carpeta_pendiente(ruta_datos), datos)


def _secretos(datos: dict) -> dict[str, str] | None:
	from app.services.copia import cifrado

	protegidos = datos.get("secretos")
	if not isinstance(protegidos, str) or not protegidos:
		return None
	claro = cifrado.desproteger_local(base64.b64decode(protegidos))
	valor: Any = json.loads(claro.decode("utf-8"))
	return {str(k): str(v) for k, v in valor.items()} if isinstance(valor, dict) else None


def aplicar_pendiente(ruta_datos: Path, preguntar: Callable[[InfoPendiente], str] | None) -> ResultadoRestauracion | None:
	"""Aplica la restauración preparada, si la hay; ``None`` si no hay nada o se deja para más tarde."""
	ruta_datos = Path(ruta_datos)
	try:
		datos = _leer(ruta_datos)
		if datos is None:
			return None
		if datos.get("_danada"):
			_borrar(ruta_datos)
			return ResultadoRestauracion(False, _("La restauración pendiente estaba dañada y se ha descartado; vuelva a "
				"restaurar la copia."))
		info = _info(datos)
		if not datos.get("reiniciar_ahora"):
			if preguntar is None:
				return None
			try:
				decision = preguntar(info)
			except Exception:  # noqa: BLE001 - sin poder preguntar, se deja para otro arranque
				log.exception("No se pudo preguntar por la restauración pendiente")
				return None
			if decision == "descartar":
				_borrar(ruta_datos)
				return ResultadoRestauracion(True, _("Se ha descartado la restauración pendiente."))
			if decision != "aplicar":
				return None
		return _aplicar(ruta_datos, datos)
	except Exception as error:  # noqa: BLE001 - main.py sigue arrancando pase lo que pase
		log.exception("Falló la restauración pendiente")
		_borrar(ruta_datos)
		return ResultadoRestauracion(False, _("No se pudo aplicar la restauración pendiente: {e}").format(
			e=getattr(error, "mensaje", "") or error))


def _aplicar(ruta_datos: Path, datos: dict) -> ResultadoRestauracion:
	from app.services.copia.formato import CopiaAbierta, ErrorCopia
	from app.services.copia.restaurar import PlanRestauracion, restaurar_con_previa

	carpeta = carpeta_pendiente(ruta_datos)
	copia = carpeta / COPIA
	if datos.get("sha256") and _suma(copia) != datos["sha256"]:
		_borrar(ruta_datos)
		return ResultadoRestauracion(False, _("La copia de la restauración pendiente ha cambiado desde que se preparó; "
			"no se ha aplicado. Vuelva a restaurarla."))
	plan = PlanRestauracion.desde_dict(datos["plan"])
	avisos = []
	try:
		secretos = _secretos(datos)
	except (ErrorCopia, ValueError) as error:
		log.warning("No se pudieron recuperar los secretos de la restauración pendiente", exc_info=True)
		secretos = None
		avisos.append(getattr(error, "mensaje", "") or _("No se pudieron recuperar las contraseñas de la copia."))
	try:
		with CopiaAbierta(copia) as abierta:
			resultado, _aplicado = restaurar_con_previa(abierta, plan, secretos, ruta_datos)
	finally:
		_borrar(ruta_datos)
	if avisos:
		resultado = ResultadoRestauracion(resultado.ok, " ".join([resultado.mensaje, *avisos]), resultado.partes,
			resultado.copia_previa)
	return resultado
