# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Fichas de componentes: esquema, lectura y escritura de ``componentes.json`` y ``linea_base.json`` (diseño 2.0, 6.2). Sin wx.

- ``componentes.json`` describe lo INSTALADO (lo cambia el actualizador de
  componentes); ``linea_base.json`` tiene la misma forma, es de solo lectura y
  dice lo que trae y ha probado esta versión de zCommander (la genera
  ``tools/preparar_componentes.py``).
- La validación del esquema es un contrato (la dejó N2; la usan la línea base,
  los manifiestos y CO). Los mensajes van en español para el registro y el diálogo.
- La escritura es atómica (temporal y ``os.replace`` con reintentos): un corte
  de luz nunca deja un ``componentes.json`` a medias.
- Utilidades comunes del bloque: marcadores (``{version}``, ``{version_sin_punto}``,
  ``{rama}``), comparación de versiones y sumas de una carpeta.
"""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FORMATO = 1
NOMBRE_INSTALADOS = "componentes.json"
NOMBRE_LINEA_BASE = "linea_base.json"
#: Campos que solo van en ``linea_base.json``: el paquete exacto de la base y su suma (6.2).
SOLO_LINEA_BASE = ("url_paquete_exacta", "sha256_paquete", "paquetes_exactos")
_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TIPOS_FUENTE = ("github", "msys2", "url")
TIPOS_VERIFICACION = ("sha256sums", "digest_github", "msys2", "sha256")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _es_texto(valor: Any) -> bool:
	return isinstance(valor, str) and bool(valor.strip())


def _validar_fuente(fuente: Any, donde: str) -> list[str]:
	if fuente is None:
		return []
	if not isinstance(fuente, dict):
		return [_("{d}: «fuente» debe ser un objeto").format(d=donde)]
	tipo = fuente.get("tipo")
	if tipo not in TIPOS_FUENTE:
		return [_("{d}: tipo de fuente desconocido «{t}»").format(d=donde, t=tipo)]
	problemas = []
	if tipo == "github":
		if not _es_texto(fuente.get("repositorio")) or "/" not in str(fuente.get("repositorio")):
			problemas.append(_("{d}: la fuente github necesita «repositorio» con la forma dueño/nombre").format(d=donde))
		if not _es_texto(fuente.get("patron_asset")):
			problemas.append(_("{d}: la fuente github necesita «patron_asset»").format(d=donde))
		desde = fuente.get("version_desde", "tag_name")
		if not (desde in ("tag_name", "programa") or (isinstance(desde, str) and desde.startswith("re:"))):
			problemas.append(_("{d}: «version_desde» debe ser tag_name, programa o re:<expresión>").format(d=donde))
	elif tipo == "msys2":
		if not _es_texto(fuente.get("indice")) or not _es_texto(fuente.get("principal")):
			problemas.append(_("{d}: la fuente msys2 necesita «indice» y «principal»").format(d=donde))
		if not isinstance(fuente.get("paquetes"), dict) or not fuente.get("paquetes"):
			problemas.append(_("{d}: la fuente msys2 necesita «paquetes»").format(d=donde))
	elif tipo == "url":
		if not _es_texto(fuente.get("url_version")) or not _es_texto(fuente.get("url_paquete")):
			problemas.append(_("{d}: la fuente url necesita «url_version» y «url_paquete»").format(d=donde))
	if "extraer" in fuente and not isinstance(fuente["extraer"], dict):
		problemas.append(_("{d}: «extraer» debe ser un objeto miembro → archivo").format(d=donde))
	return problemas


def _validar_verificacion(verificacion: Any, donde: str) -> list[str]:
	if verificacion is None:
		return []
	if not isinstance(verificacion, dict) or verificacion.get("tipo") not in TIPOS_VERIFICACION:
		return [_("{d}: «verificacion» debe tener un tipo de {t}").format(d=donde, t=", ".join(TIPOS_VERIFICACION))]
	if verificacion["tipo"] == "sha256sums" and not _es_texto(verificacion.get("asset")):
		return [_("{d}: la verificación sha256sums necesita «asset»").format(d=donde)]
	if verificacion["tipo"] == "sha256" and not _SHA256.match(str(verificacion.get("valor", ""))):
		return [_("{d}: la verificación sha256 necesita un «valor» de 64 cifras hexadecimales").format(d=donde)]
	return []


def _validar_prueba(prueba: Any, donde: str) -> list[str]:
	if prueba is None:
		return []
	if not isinstance(prueba, dict):
		return [_("{d}: «prueba» debe ser un objeto").format(d=donde)]
	problemas = []
	if prueba.get("tipo") == "zcommander":
		if not isinstance(prueba.get("argumentos"), list):
			problemas.append(_("{d}: la prueba zcommander necesita «argumentos»").format(d=donde))
	elif "tipo" in prueba:
		problemas.append(_("{d}: tipo de prueba desconocido «{t}»").format(d=donde, t=prueba.get("tipo")))
	else:
		if not _es_texto(prueba.get("ejecutable")):
			problemas.append(_("{d}: la prueba necesita «ejecutable»").format(d=donde))
		if not isinstance(prueba.get("argumentos", []), list):
			problemas.append(_("{d}: «argumentos» de la prueba debe ser una lista").format(d=donde))
		adicionales = prueba.get("adicionales", [])
		if not isinstance(adicionales, list) or any(not isinstance(a, dict) or not _es_texto(a.get("ejecutable")) for a in adicionales):
			problemas.append(_("{d}: «adicionales» de la prueba debe ser una lista de pruebas con «ejecutable»").format(d=donde))
	tiempo = prueba.get("tiempo_s", 20)
	if not isinstance(tiempo, (int, float)) or isinstance(tiempo, bool) or tiempo <= 0:
		problemas.append(_("{d}: «tiempo_s» de la prueba debe ser un número positivo").format(d=donde))
	return problemas


def _validar_en_uso(en_uso: Any, donde: str) -> list[str]:
	if en_uso is None:
		return []
	if not isinstance(en_uso, dict):
		return [_("{d}: «en_uso» debe ser un objeto").format(d=donde)]
	problemas = []
	if not isinstance(en_uso.get("procesos", []), list):
		problemas.append(_("{d}: «procesos» de en_uso debe ser una lista").format(d=donde))
	for clave in ("detener", "al_reiniciar"):
		if clave in en_uso and not isinstance(en_uso[clave], bool):
			problemas.append(_("{d}: «{c}» de en_uso debe ser verdadero o falso").format(d=donde, c=clave))
	esperar = en_uso.get("esperar_s", 0)
	if not isinstance(esperar, (int, float)) or isinstance(esperar, bool) or esperar < 0:
		problemas.append(_("{d}: «esperar_s» de en_uso debe ser un número no negativo").format(d=donde))
	return problemas


def _validar_ficha(ficha: Any, indice: int, linea_base: bool) -> list[str]:
	donde = _("Componente {n}").format(n=indice + 1)
	if not isinstance(ficha, dict):
		return [_("{d}: debe ser un objeto").format(d=donde)]
	if _es_texto(ficha.get("id")):
		donde = _("Componente {i}").format(i=ficha["id"])
	problemas = []
	for campo in ("id", "nombre", "version", "licencia", "dueno", "carpeta"):
		if not _es_texto(ficha.get(campo)):
			problemas.append(_("{d}: falta el campo «{c}»").format(d=donde, c=campo))
	if _es_texto(ficha.get("id")) and not _ID.match(ficha["id"]):
		problemas.append(_("{d}: el id solo admite minúsculas, cifras y guiones bajos").format(d=donde))
	carpeta = str(ficha.get("carpeta", ""))
	if carpeta and (".." in Path(carpeta).parts or Path(carpeta).is_absolute() or "/" in carpeta or "\\" in carpeta):
		problemas.append(_("{d}: «carpeta» debe ser un nombre simple dentro de data/bin").format(d=donde))
	archivos = ficha.get("archivos", [])
	if not isinstance(archivos, list):
		problemas.append(_("{d}: «archivos» debe ser una lista").format(d=donde))
	else:
		for archivo in archivos:
			if not isinstance(archivo, dict) or not _es_texto(archivo.get("ruta")):
				problemas.append(_("{d}: cada archivo necesita «ruta»").format(d=donde))
				continue
			if ".." in Path(archivo["ruta"]).parts or Path(archivo["ruta"]).is_absolute():
				problemas.append(_("{d}: ruta no válida «{r}»").format(d=donde, r=archivo["ruta"]))
			if not _SHA256.match(str(archivo.get("sha256", ""))):
				problemas.append(_("{d}: «{r}» necesita un sha256 de 64 cifras hexadecimales").format(d=donde, r=archivo["ruta"]))
			tamano = archivo.get("tamano")
			if not isinstance(tamano, int) or isinstance(tamano, bool) or tamano < 0:
				problemas.append(_("{d}: «{r}» necesita un tamaño entero").format(d=donde, r=archivo["ruta"]))
	if not isinstance(ficha.get("licencias", []), list):
		problemas.append(_("{d}: «licencias» debe ser una lista").format(d=donde))
	for campo in ("opcional", "actualizable"):
		if campo in ficha and not isinstance(ficha[campo], bool):
			problemas.append(_("{d}: «{c}» debe ser verdadero o falso").format(d=donde, c=campo))
	problemas += _validar_fuente(ficha.get("fuente"), donde)
	problemas += _validar_verificacion(ficha.get("verificacion"), donde)
	problemas += _validar_prueba(ficha.get("prueba"), donde)
	problemas += _validar_en_uso(ficha.get("en_uso"), donde)
	if ficha.get("actualizable", True) and ficha.get("fuente") is None:
		problemas.append(_("{d}: un componente actualizable necesita «fuente»").format(d=donde))
	asset = ficha.get("asset")
	if asset is not None and (not isinstance(asset, dict) or not str(asset.get("digest", "")).startswith("sha256:")):
		problemas.append(_("{d}: «asset» necesita «digest» con la forma sha256:<suma>").format(d=donde))
	if linea_base:
		if "sha256_paquete" in ficha and not _SHA256.match(str(ficha["sha256_paquete"])):
			problemas.append(_("{d}: «sha256_paquete» debe tener 64 cifras hexadecimales").format(d=donde))
		if "url_paquete_exacta" in ficha and not str(ficha["url_paquete_exacta"]).startswith("https://"):
			problemas.append(_("{d}: «url_paquete_exacta» debe ser https").format(d=donde))
		exactos = ficha.get("paquetes_exactos", [])
		if not isinstance(exactos, list) or any(
			not isinstance(p, dict) or not str(p.get("url", "")).startswith("https://") or not _SHA256.match(str(p.get("sha256", "")))
			for p in exactos):
			problemas.append(_("{d}: cada paquete de «paquetes_exactos» necesita «url» https y «sha256»").format(d=donde))
	elif any(campo in ficha for campo in SOLO_LINEA_BASE):
		problemas.append(_("{d}: «sha256_paquete», «url_paquete_exacta» y «paquetes_exactos» solo van en la línea base").format(d=donde))
	return problemas


def validar(datos: dict, *, linea_base: bool) -> list[str]:
	"""Mensajes en español de lo que no cumple el esquema de 6.2; lista vacía si es válida."""
	if not isinstance(datos, dict):
		return [_("El archivo de componentes debe contener un objeto JSON")]
	problemas = []
	if datos.get("formato") != FORMATO:
		problemas.append(_("Formato de componentes desconocido: {f}").format(f=datos.get("formato")))
	componentes = datos.get("componentes")
	if not isinstance(componentes, list):
		return [*problemas, _("Falta la lista «componentes»")]
	vistos: set[str] = set()
	for indice, ficha in enumerate(componentes):
		problemas += _validar_ficha(ficha, indice, linea_base)
		if isinstance(ficha, dict) and _es_texto(ficha.get("id")):
			if ficha["id"] in vistos:
				problemas.append(_("El componente {i} está repetido").format(i=ficha["id"]))
			vistos.add(ficha["id"])
	return problemas


# ── Lectura y escritura ──────────────────────────────────────────────────────


def leer(ruta: Path) -> dict:
	"""Lee un archivo de fichas (sin validar). Lanza ``OSError`` o ``ValueError`` si no se puede."""
	datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
	if not isinstance(datos, dict):
		raise ValueError(_("El archivo de componentes debe contener un objeto JSON"))
	return datos


def leer_o_vacio(ruta: Path) -> dict:
	"""Como ``leer``, pero un archivo que falta o no se entiende da una lista vacía (y se registra)."""
	try:
		return leer(ruta)
	except FileNotFoundError:
		log.debug("No existe %s", ruta)
	except (OSError, ValueError):
		log.warning("No se pudo leer %s", ruta, exc_info=True)
	return {"formato": FORMATO, "componentes": []}


def a_texto(datos: dict) -> str:
	"""JSON con tabulaciones y sin escapar las tildes (así lo escriben la herramienta y el actualizador)."""
	return json.dumps(datos, ensure_ascii=False, indent="\t") + "\n"


def escribir(ruta: Path, datos: dict, intentos: int = 6) -> None:
	"""Escritura atómica: temporal en la misma carpeta y ``os.replace`` (reintenta si otro proceso lo tiene abierto)."""
	ruta = Path(ruta)
	ruta.parent.mkdir(parents=True, exist_ok=True)
	temporal = ruta.with_name(f"{ruta.name}.{os.getpid()}.tmp")
	temporal.write_text(a_texto(datos), encoding="utf-8")
	for intento in range(intentos):
		try:
			os.replace(temporal, ruta)
			return
		except PermissionError:
			if intento + 1 == intentos:
				temporal.unlink(missing_ok=True)
				raise
			time.sleep(0.1 * (intento + 1))


def buscar(datos: dict, id: str) -> dict | None:
	"""La ficha ``id`` de un archivo de fichas, o ``None``."""
	for ficha in datos.get("componentes", []) if isinstance(datos, dict) else []:
		if isinstance(ficha, dict) and ficha.get("id") == id:
			return ficha
	return None


def poner(datos: dict, ficha: dict) -> dict:
	"""Copia de ``datos`` con ``ficha`` en el lugar de la del mismo id (o al final)."""
	nuevo = copy.deepcopy(datos) if isinstance(datos, dict) else {"formato": FORMATO, "componentes": []}
	nuevo.setdefault("formato", FORMATO)
	componentes = nuevo.setdefault("componentes", [])
	for indice, actual in enumerate(componentes):
		if isinstance(actual, dict) and actual.get("id") == ficha.get("id"):
			componentes[indice] = copy.deepcopy(ficha)
			return nuevo
	componentes.append(copy.deepcopy(ficha))
	return nuevo


def sin_campos_de_base(ficha: dict) -> dict:
	"""La ficha sin los campos que solo van en la línea base (para ``componentes.json``)."""
	return {clave: copy.deepcopy(valor) for clave, valor in ficha.items() if clave not in SOLO_LINEA_BASE}


# ── Marcadores y versiones ───────────────────────────────────────────────────


def sustituir(texto: str, *, version: str = "", rama: str = "") -> str:
	"""Cambia ``{version}``, ``{version_sin_punto}`` y ``{rama}`` (6.2)."""
	return (str(texto).replace("{version_sin_punto}", version.replace(".", ""))
		.replace("{version}", version).replace("{rama}", rama))


def partes_version(version: str) -> tuple[int, ...]:
	"""«1.76.0» → (1, 76, 0); «3.8.11-1» → (3, 8, 11, 1); «1~2.0» quita la época de MSYS2."""
	limpio = str(version).strip().lstrip("vVn")
	if "~" in limpio:
		limpio = limpio.split("~", 1)[1]
	return tuple(int(n) for n in re.findall(r"\d+", limpio))


def comparar_versiones(a: str, b: str) -> int:
	"""−1, 0 o 1 según ``a`` sea más baja, igual o más alta que ``b`` (cifra a cifra)."""
	pa, pb = partes_version(a), partes_version(b)
	largo = max(len(pa), len(pb))
	pa, pb = pa + (0,) * (largo - len(pa)), pb + (0,) * (largo - len(pb))
	return (pa > pb) - (pa < pb)


def version_principal(version: str) -> int:
	"""El primer número de la versión (el que cambia cuando algo deja de ser compatible)."""
	partes = partes_version(version)
	return partes[0] if partes else 0


# ── Sumas ────────────────────────────────────────────────────────────────────


def sha256_archivo(ruta: Path) -> str:
	suma = hashlib.sha256()
	with Path(ruta).open("rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			suma.update(bloque)
	return suma.hexdigest()


def sumas_de_carpeta(carpeta: Path) -> list[dict]:
	"""``[{"ruta", "sha256", "tamano"}]`` de cada archivo de ``carpeta`` (rutas con «/», en orden)."""
	carpeta = Path(carpeta)
	if not carpeta.is_dir():
		return []
	archivos = []
	for ruta in sorted((p for p in carpeta.rglob("*") if p.is_file()), key=lambda p: p.relative_to(carpeta).as_posix().casefold()):
		archivos.append({"ruta": ruta.relative_to(carpeta).as_posix(), "sha256": sha256_archivo(ruta), "tamano": ruta.stat().st_size})
	return archivos


def mapa_sumas(archivos: list[dict]) -> dict[str, str]:
	"""``{ruta en minúsculas: sha256}`` de la lista ``archivos`` de una ficha (Windows no distingue mayúsculas)."""
	return {str(a.get("ruta", "")).casefold(): str(a.get("sha256", "")).lower() for a in archivos if isinstance(a, dict)}
