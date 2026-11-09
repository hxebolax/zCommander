# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Dónde se buscan las versiones nuevas de los componentes (diseño 2.0, 6.2 y 6.4). Sin wx.

Tres fuentes, todas por ``app/core/red.py`` (tiempo de espera siempre,
reintentos solo de GET, ``Retry-After``, mensajes en español):

- **github**: ``/repos/<repositorio>/releases/latest`` o ``/releases/tags/<etiqueta>``.
  La versión sale de ``tag_name`` (sin la «v»), de una expresión regular sobre
  el nombre del asset (``re:``) o del propio programa (``programa``, FFmpeg).
  Una publicación que reutiliza la misma etiqueta (``latest`` de FFmpeg-Builds)
  se compara por el ``digest`` y el ``updated_at`` del asset, sin descargar nada.
  Una rama más alta en la misma publicación (``9.1`` frente a ``9.0``) se
  ofrece como cambio grande.
- **msys2**: el índice ``ucrt64.db`` (un ``tar.zst`` con un ``desc`` por paquete).
- **url**: una URL con la versión (texto o JSON) y otra con el paquete.

Una comprobación hace UNA petición a la API de GitHub por componente (60 por
hora sin autenticar). Ninguna función descarga paquetes: solo el índice o el
archivo de sumas, que son pequeños.
"""

from __future__ import annotations

import builtins
import io
import logging
import re
import tarfile
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from app.core import red
from app.services.componentes import fichas

log = logging.getLogger(__name__)

#: Base de la API de GitHub (las pruebas la cambian por un servidor local).
API_GITHUB = "https://api.github.com"
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorFuente(Exception):
	"""No se pudo saber si hay versión nueva; ``mensaje`` en español."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


@dataclass
class Paquete:
	"""Un archivo que hay que descargar, con su suma y qué se saca de él."""

	url: str
	nombre: str
	sha256: str
	tamano: int = -1
	extraer: dict[str, str] = field(default_factory=dict)


@dataclass
class VersionNueva:
	"""Lo que se ofrece para un componente.

	:param version: la versión nueva («1.77.0»); vacía si la da el programa tras probarlo (FFmpeg).
	:param texto: lo que se ve en la columna «Nueva» («1.77.0», «Compilación nueva de la rama 9.0 (1 de noviembre de 2026)»).
	:param asset: ``{"digest", "actualizado"}`` del asset, para las publicaciones que reutilizan su etiqueta.
	"""

	id: str
	version: str
	texto: str
	paquetes: list[Paquete]
	novedades: str = ""
	cambio_grande: bool = False
	asset: dict[str, str] | None = None
	rama: str = ""
	version_paquete: str = ""

	@property
	def tamano(self) -> int:
		return sum(max(0, p.tamano) for p in self.paquetes)

	def a_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def de_dict(cls, datos: dict[str, Any]) -> VersionNueva:
		paquetes = [Paquete(**p) for p in datos.get("paquetes", [])]
		campos = {k: v for k, v in datos.items() if k in cls.__dataclass_fields__ and k != "paquetes"}
		return cls(paquetes=paquetes, **campos)


def fecha_legible(iso: str) -> str:
	"""«2026-11-01T12:00:00Z» → «1 de noviembre de 2026»."""
	try:
		momento = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
	except ValueError:
		return str(iso)
	return _("{d} de {m} de {a}").format(d=momento.day, m=_(MESES[momento.month - 1]), a=momento.year)


def sumas_de_texto(texto: str) -> dict[str, str]:
	"""``SHA256SUMS`` o ``checksums.sha256``: «<suma>  <archivo>» (también «*archivo» y rutas) → ``{nombre: suma}``."""
	sumas = {}
	for linea in texto.splitlines():
		encontrado = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", linea)
		if encontrado:
			nombre = encontrado.group(2).replace("\\", "/").rsplit("/", 1)[-1]
			sumas[nombre] = encontrado.group(1).lower()
	return sumas


def _cambio_grande(nueva: str, instalada: str) -> bool:
	return bool(nueva) and fichas.version_principal(nueva) != fichas.version_principal(instalada)


def _extraer(ficha: dict, version: str, rama: str) -> dict[str, str]:
	mapa = (ficha.get("fuente") or {}).get("extraer") or {}
	return {fichas.sustituir(k, version=version, rama=rama): fichas.sustituir(v, version=version, rama=rama) for k, v in mapa.items()}


def comprobar(ficha: dict, config: red.ConfiguracionRed) -> VersionNueva | None:
	"""Versión nueva del componente instalado ``ficha``, o ``None`` si está al día.

	:raises ErrorFuente: con el mensaje en español (sin red, servidor con error, suma que falta...).
	"""
	fuente = ficha.get("fuente") or {}
	if not ficha.get("actualizable", True) or not fuente:
		return None
	tipo = fuente.get("tipo")
	try:
		if tipo == "github":
			return _github(ficha, config)
		if tipo == "msys2":
			return _msys2(ficha, config)
		if tipo == "url":
			return _url(ficha, config)
	except red.ErrorHTTP as error:
		log.warning("No se pudo comprobar %s: %s", ficha.get("id"), error.mensaje)
		raise ErrorFuente(error.mensaje) from error
	except (ValueError, KeyError, TypeError, tarfile.TarError, OSError) as error:
		log.warning("Respuesta que no se entiende al comprobar %s", ficha.get("id"), exc_info=True)
		raise ErrorFuente(_("La respuesta del servidor de {c} no se entiende.").format(c=ficha.get("nombre", ficha.get("id")))) from error
	raise ErrorFuente(_("Tipo de fuente desconocido: {t}").format(t=tipo))


# ── GitHub ───────────────────────────────────────────────────────────────────


def _publicacion(fuente: dict, config: red.ConfiguracionRed) -> dict:
	etiqueta = str(fuente.get("etiqueta") or "")
	camino = f"tags/{urllib.parse.quote(etiqueta)}" if etiqueta else "latest"
	url = f"{API_GITHUB}/repos/{fuente['repositorio']}/releases/{camino}"
	respuesta = red.obtener(config, url, cabeceras={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
	datos = respuesta.json()
	if not isinstance(datos, dict) or not isinstance(datos.get("assets"), list):
		raise ValueError("publicación sin assets")
	return datos


def _sha256_github(ficha: dict, publicacion: dict, asset: dict, config: red.ConfiguracionRed) -> str:
	verificacion = ficha.get("verificacion") or {}
	tipo = verificacion.get("tipo")
	if tipo == "digest_github":
		digest = str(asset.get("digest") or "")
		return digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else ""
	if tipo == "sha256":
		return str(verificacion.get("valor", "")).lower()
	if tipo == "sha256sums":
		nombre = str(verificacion.get("asset", ""))
		sumas_asset = next((a for a in publicacion["assets"] if a.get("name") == nombre), None)
		if sumas_asset is None:
			return ""
		texto = red.obtener(config, str(sumas_asset["browser_download_url"])).texto()
		return sumas_de_texto(texto).get(str(asset["name"]), "")
	return ""


def _novedades(ficha: dict, publicacion: dict) -> str:
	cuerpo = str(publicacion.get("body") or "").strip()
	if len(cuerpo) > 1500:
		cuerpo = cuerpo[:1500].rstrip() + "…"
	enlace = str(ficha.get("novedades") or publicacion.get("html_url") or "")
	partes = [p for p in (cuerpo, _("Más información: {u}").format(u=enlace) if enlace else "") if p]
	return "\n\n".join(partes)


def _patron_rama(patron: str) -> re.Pattern:
	"""Expresión que reconoce el patrón del asset con cualquier rama («9.0», «9.1», «10.0»)."""
	trozos = [re.escape(t) for t in patron.split("{rama}")]
	expresion = trozos[0]
	for indice, trozo in enumerate(trozos[1:]):
		# La primera vez captura la rama; las siguientes exigen la misma («-n9.0-...-9.0.zip»).
		expresion += (r"(?P<rama>\d+(?:\.\d+)*)" if indice == 0 else "(?P=rama)") + trozo
	return re.compile("^" + expresion + "$")


def _github(ficha: dict, config: red.ConfiguracionRed) -> VersionNueva | None:
	fuente = ficha["fuente"]
	publicacion = _publicacion(fuente, config)
	assets = [a for a in publicacion["assets"] if isinstance(a, dict) and a.get("name")]
	desde = str(fuente.get("version_desde") or "tag_name")
	rama = str(fuente.get("rama") or "")
	instalada = str(ficha.get("version", ""))
	if desde == "programa":
		return _github_por_asset(ficha, publicacion, assets, rama, config)
	if desde.startswith("re:"):
		expresion = re.compile(desde[3:])
		candidatos = []
		for asset in assets:
			encontrado = expresion.search(str(asset["name"]))
			if encontrado and encontrado.groups():
				candidatos.append((encontrado.group(1), asset))
		if not candidatos:
			raise ValueError("ningún asset con la expresión")
		version, asset = max(candidatos, key=lambda c: fichas.partes_version(c[0]))
	else:
		version = str(publicacion.get("tag_name") or "")
		version = version[1:] if version[:1] in ("v", "V") else version
		nombre = fichas.sustituir(fuente["patron_asset"], version=version, rama=rama)
		asset = next((a for a in assets if a["name"] == nombre), None)
		if asset is None:
			if fichas.comparar_versiones(version, instalada) <= 0:
				return None
			raise ErrorFuente(_("La publicación {v} de {c} no trae el paquete {n}.").format(v=version, c=ficha.get("nombre"), n=nombre))
	if fichas.comparar_versiones(version, instalada) <= 0:
		return None
	sha = _sha256_github(ficha, publicacion, asset, config)
	if not sha:
		raise ErrorFuente(_("No se encontró la suma SHA-256 publicada del paquete de {c}.").format(c=ficha.get("nombre")))
	paquete = Paquete(str(asset["browser_download_url"]), str(asset["name"]), sha, int(asset.get("size") or -1), _extraer(ficha, version, rama))
	return VersionNueva(ficha["id"], version, version, [paquete], _novedades(ficha, publicacion), _cambio_grande(version, instalada), rama=rama)


def _github_por_asset(ficha: dict, publicacion: dict, assets: list[dict], rama: str, config: red.ConfiguracionRed) -> VersionNueva | None:
	"""Etiqueta reutilizada (``latest``): rama más alta o compilación nueva por ``digest`` y ``updated_at``."""
	fuente = ficha["fuente"]
	patron = str(fuente["patron_asset"])
	por_rama: dict[str, dict] = {}
	if "{rama}" in patron:
		expresion = _patron_rama(patron)
		for asset in assets:
			encontrado = expresion.match(str(asset["name"]))
			if encontrado:
				por_rama[encontrado.group("rama")] = asset
	else:
		nombre = fichas.sustituir(patron, rama=rama)
		encontrado = next((a for a in assets if a["name"] == nombre), None)
		if encontrado is not None:
			por_rama[rama] = encontrado
	if not por_rama:
		raise ErrorFuente(_("La publicación de {c} no trae ningún paquete {p}.").format(c=ficha.get("nombre"), p=patron))
	mas_alta = max(por_rama, key=fichas.partes_version)
	cambio_grande = False
	if rama and fichas.comparar_versiones(mas_alta, rama) > 0:
		elegida, cambio_grande = mas_alta, True
	elif rama in por_rama:
		elegida = rama
	else:
		raise ErrorFuente(_("La publicación de {c} ya no trae la rama {r}.").format(c=ficha.get("nombre"), r=rama))
	asset = por_rama[elegida]
	digest = str(asset.get("digest") or "")
	actualizado = str(asset.get("updated_at") or "")
	conocido = ficha.get("asset") or {}
	if not cambio_grande and digest and digest == conocido.get("digest"):
		return None
	if not cambio_grande and not digest and actualizado and actualizado == conocido.get("actualizado"):
		return None
	sha = _sha256_github(ficha, publicacion, asset, config)
	if not sha:
		raise ErrorFuente(_("No se encontró la suma SHA-256 publicada del paquete de {c}.").format(c=ficha.get("nombre")))
	fecha = fecha_legible(actualizado) if actualizado else ""
	if cambio_grande:
		texto = _("Rama {r} ({f})").format(r=elegida, f=fecha) if fecha else _("Rama {r}").format(r=elegida)
	else:
		texto = _("Compilación nueva de la rama {r} ({f})").format(r=elegida, f=fecha) if fecha else _("Compilación nueva de la rama {r}").format(r=elegida)
	paquete = Paquete(str(asset["browser_download_url"]), str(asset["name"]), sha, int(asset.get("size") or -1), _extraer(ficha, "", elegida))
	return VersionNueva(ficha["id"], "", texto, [paquete], _novedades(ficha, publicacion), cambio_grande,
		asset={"digest": digest, "actualizado": actualizado}, rama=elegida)


# ── MSYS2 ────────────────────────────────────────────────────────────────────


def leer_indice_msys2(contenido: bytes, nombres: set[str]) -> dict[str, dict[str, str]]:
	"""``{paquete: {"version", "archivo", "sha256", "tamano"}}`` de los paquetes pedidos del índice (``tar.zst``)."""
	encontrados: dict[str, dict[str, str]] = {}
	with tarfile.open(fileobj=io.BytesIO(contenido), mode="r:*") as indice:
		for miembro in indice:
			if not miembro.isfile() or not miembro.name.endswith("/desc"):
				continue
			carpeta = miembro.name.rsplit("/", 1)[0]
			if not any(carpeta.startswith(nombre + "-") for nombre in nombres):
				continue
			archivo = indice.extractfile(miembro)
			if archivo is None:
				continue
			campos: dict[str, list[str]] = {}
			for bloque in archivo.read().decode("utf-8", errors="replace").split("\n\n"):
				lineas = [linea for linea in bloque.strip().splitlines() if linea]
				if lineas and lineas[0].startswith("%"):
					campos[lineas[0]] = lineas[1:]
			nombre = (campos.get("%NAME%") or [""])[0]
			if nombre in nombres:
				encontrados[nombre] = {
					"version": (campos.get("%VERSION%") or [""])[0],
					"archivo": (campos.get("%FILENAME%") or [""])[0],
					"sha256": (campos.get("%SHA256SUM%") or [""])[0].lower(),
					"tamano": (campos.get("%CSIZE%") or ["-1"])[0],
				}
	return encontrados


def version_sin_revision(version_paquete: str) -> str:
	"""«3.8.11-1» → «3.8.11»; «1~2.0-3» → «2.0» (época y revisión del paquete fuera)."""
	sin_epoca = version_paquete.split("~", 1)[-1]
	return sin_epoca.rsplit("-", 1)[0] if "-" in sin_epoca else sin_epoca


def _msys2(ficha: dict, config: red.ConfiguracionRed) -> VersionNueva | None:
	fuente = ficha["fuente"]
	paquetes: dict[str, dict] = fuente["paquetes"]
	principal = str(fuente["principal"])
	indice_url = str(fuente["indice"])
	contenido = red.obtener(config, indice_url, tiempo_s=60).cuerpo
	encontrados = leer_indice_msys2(contenido, {*paquetes, principal})
	faltan = sorted(n for n in {*paquetes, principal} if n not in encontrados)
	if faltan:
		raise ErrorFuente(_("El índice de MSYS2 no trae {p}.").format(p=", ".join(faltan)))
	completa = encontrados[principal]["version"]
	instalada = str(ficha.get("version_paquete") or ficha.get("version", ""))
	if fichas.comparar_versiones(completa, instalada) <= 0:
		return None
	version = version_sin_revision(completa)
	base_url = indice_url.rsplit("/", 1)[0] + "/"
	lista = []
	for nombre, datos in paquetes.items():
		info = encontrados[nombre]
		if not info["sha256"]:
			raise ErrorFuente(_("El índice de MSYS2 no trae la suma de {p}.").format(p=nombre))
		mapa = (datos or {}).get("extraer") or {}
		tamano = int(info["tamano"]) if str(info["tamano"]).isdigit() else -1
		lista.append(Paquete(base_url + urllib.parse.quote(info["archivo"]), info["archivo"], info["sha256"], tamano,
			{fichas.sustituir(k, version=version): fichas.sustituir(v, version=version) for k, v in mapa.items()}))
	novedades = _("Paquete {p} {v} de MSYS2.").format(p=principal, v=completa)
	if ficha.get("novedades"):
		novedades += "\n\n" + _("Más información: {u}").format(u=ficha["novedades"])
	return VersionNueva(ficha["id"], version, version, lista, novedades, _cambio_grande(version, str(ficha.get("version", ""))),
		version_paquete=completa)


# ── URL ──────────────────────────────────────────────────────────────────────


def _url(ficha: dict, config: red.ConfiguracionRed) -> VersionNueva | None:
	fuente = ficha["fuente"]
	respuesta = red.obtener(config, str(fuente["url_version"]))
	formato = str(fuente.get("formato_version") or "texto")
	if formato.startswith("json:"):
		version = str(respuesta.json()[formato[5:]]).strip()
	else:
		version = respuesta.texto().strip().splitlines()[0].strip()
	version = version[1:] if version[:1] in ("v", "V") else version
	instalada = str(ficha.get("version", ""))
	if fichas.comparar_versiones(version, instalada) <= 0:
		return None
	url_paquete = fichas.sustituir(str(fuente["url_paquete"]), version=version)
	nombre = urllib.parse.unquote(urllib.parse.urlsplit(url_paquete).path.rsplit("/", 1)[-1])
	verificacion = ficha.get("verificacion") or {}
	sha = ""
	if verificacion.get("tipo") == "sha256":
		sha = str(verificacion.get("valor", "")).lower()
	elif fuente.get("url_sumas"):
		texto = red.obtener(config, fichas.sustituir(str(fuente["url_sumas"]), version=version)).texto()
		sha = sumas_de_texto(texto).get(nombre, "")
	if not sha:
		raise ErrorFuente(_("No se encontró la suma SHA-256 publicada del paquete de {c}.").format(c=ficha.get("nombre")))
	paquete = Paquete(url_paquete, nombre, sha, -1, _extraer(ficha, version, ""))
	novedades = _("Más información: {u}").format(u=ficha["novedades"]) if ficha.get("novedades") else ""
	return VersionNueva(ficha["id"], version, version, [paquete], novedades, _cambio_grande(version, instalada))


# ── Paquete exacto de la línea base ──────────────────────────────────────────


def paquetes_de_base(base: dict) -> VersionNueva:
	"""El paquete (o los paquetes) exacto de la línea base, para volver a bajarla si se borró su respaldo (6.6)."""
	version = str(base.get("version", ""))
	rama = str((base.get("fuente") or {}).get("rama") or "")
	fuente = base.get("fuente") or {}
	lista = []
	if fuente.get("tipo") == "msys2":
		for exacto in base.get("paquetes_exactos", []):
			datos = (fuente.get("paquetes") or {}).get(exacto.get("paquete"), {})
			mapa = {fichas.sustituir(k, version=version): fichas.sustituir(v, version=version) for k, v in (datos.get("extraer") or {}).items()}
			nombre = urllib.parse.unquote(str(exacto["url"]).rsplit("/", 1)[-1])
			lista.append(Paquete(str(exacto["url"]), nombre, str(exacto["sha256"]).lower(), -1, mapa))
	elif base.get("url_paquete_exacta"):
		nombre = urllib.parse.unquote(str(base["url_paquete_exacta"]).rsplit("/", 1)[-1])
		lista.append(Paquete(str(base["url_paquete_exacta"]), nombre, str(base.get("sha256_paquete", "")).lower(), -1,
			_extraer(base, version, rama)))
	if not lista:
		raise ErrorFuente(_("La línea base no dice de dónde volver a descargar {c}.").format(c=base.get("nombre", base.get("id"))))
	return VersionNueva(str(base["id"]), version, version, lista, rama=rama, asset=base.get("asset"),
		version_paquete=str(base.get("version_paquete", "")))
