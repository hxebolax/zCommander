# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""«Órdenes que se podrán ejecutar» de una copia o un perfil (diseño 2.0, 7.2, 7.6 y 10.2). Sin wx.

Lo que hace ejecutar programas u órdenes no se restaura sin que la persona lo
marque una a una. Este módulo lo encuentra en una copia y le da a cada cosa un
id estable y su texto completo:

- ``menu_usuario:<etiqueta>``, ``asociaciones:<patrón>``, ``alias:<nombre>`` y
  ``macros:<nombre>``: cada elemento de esas listas que no está igual aquí.
- ``clave:<seccion.clave>``: las claves del núcleo de ``EJECUTA`` con otro valor.
- ``plugin:<id>:<clave>``: claves de complementos con ``ejecuta = true`` en su
  ``[[configuracion]]`` (o las de ``EJECUTA_COMPLEMENTOS``); si no se conoce el
  manifiesto del complemento, toda su configuración es un solo elemento
  ``plugin:<id>:*``, porque no se puede saber qué ejecuta.
- ``programador:*``: las tareas de ``zc.programador``.
- ``rclone:<remoto>``: remotos de ``rclone.conf`` con opciones que ejecutan programas.

Lo no marcado es ``PlanRestauracion.excluidos``: el que aplica solo mira esos
ids, así la restauración pendiente al arrancar (sin complementos cargados)
filtra exactamente lo mismo que se vio en el diálogo.
"""

from __future__ import annotations

import builtins
import io
import json
import logging
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.copia import combinar, formato, rclone
from app.services.copia.crear import valores_actuales
from app.services.copia.formato import CopiaAbierta, ErrorCopia

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class ElementoEjecutable:
	id: str
	parte: str
	texto: str


@dataclass
class Analisis:
	elementos: list[ElementoEjecutable] = field(default_factory=list)
	#: ``rclone.conf`` cifrado sin la contraseña a mano: se revisa tras descifrar los secretos.
	rclone_sin_revisar: bool = False
	avisos: list[str] = field(default_factory=list)

	@property
	def ids(self) -> set[str]:
		return {e.id for e in self.elementos}


def _valor_texto(valor: Any) -> str:
	if isinstance(valor, bool):
		return _("activada") if valor else _("desactivada")
	if isinstance(valor, str):
		return valor or _("(vacío)")
	return json.dumps(valor, ensure_ascii=False)


def etiqueta_clave(clave: str) -> str:
	from app.core.descripciones_config import DESCRIPCIONES

	descripcion = DESCRIPCIONES.get(clave)
	if not descripcion:
		return clave
	return descripcion[0].replace("&", "").rstrip(":").strip()


# ── Textos de los elementos ───────────────────────────────────────────────────

def _texto_menu(entrada: dict, prefijo: str = "") -> str:
	etiqueta = str(entrada.get("etiqueta", ""))
	submenu = entrada.get("submenu") if isinstance(entrada.get("submenu"), list) else []
	if submenu:
		hijos = "; ".join(_texto_menu(h) for h in submenu if isinstance(h, dict))
		return f"{prefijo}{etiqueta} ({_('submenú')}): {hijos}"
	ordenes = entrada.get("ordenes", [])
	ordenes = [ordenes] if isinstance(ordenes, str) else [o for o in ordenes if isinstance(o, str)] if isinstance(ordenes, list) else []
	return f"{prefijo}{etiqueta} → {' && '.join(ordenes) or _('(sin órdenes)')}"


def texto_elemento(archivo: str, elemento: dict) -> str:
	if archivo == "config/menu_usuario.json":
		return _("Menú de usuario: {t}").format(t=_texto_menu(elemento))
	if archivo == "config/asociaciones.json":
		acciones = [f"{_(n)} {elemento[c]}" for c, n in (("abrir", "abrir con"), ("ver", "ver con"), ("editar", "editar con"))
			if isinstance(elemento.get(c), str) and elemento[c]]
		return _("Asociación {p}: {a}").format(p=elemento.get("patron", ""), a="; ".join(acciones) or _("(sin órdenes)"))
	if archivo == "config/alias.json":
		return _("Alias {n}: {o}").format(n=elemento.get("nombre", ""), o=elemento.get("orden", ""))
	if archivo == "config/macros.json":
		pasos = []
		for paso in elemento.get("pasos", []) if isinstance(elemento.get("pasos"), list) else []:
			if isinstance(paso, dict):
				argumento = paso.get("argumento")
				texto = str(paso.get("orden", ""))
				if argumento not in (None, ""):
					texto += " " + (argumento if isinstance(argumento, str) else json.dumps(argumento, ensure_ascii=False))
				pasos.append(texto)
		return _("Macro {n}: {p}").format(n=elemento.get("nombre", ""), p="; ".join(pasos) or _("(sin pasos)"))
	return json.dumps(elemento, ensure_ascii=False)


# ── Datos locales ─────────────────────────────────────────────────────────────

def _leer_local_json(ruta_datos: Path, relativa: str) -> Any:
	try:
		return json.loads((Path(ruta_datos) / relativa).read_text(encoding="utf-8-sig"))
	except FileNotFoundError:
		return None
	except (OSError, ValueError):
		log.warning("No se pudo leer %s para comparar con la copia", relativa, exc_info=True)
		return None


def _leer_local(ruta_datos: Path, relativa: str) -> bytes | None:
	try:
		return (Path(ruta_datos) / relativa).read_bytes()
	except OSError:
		return None


# ── Configuración de los complementos ─────────────────────────────────────────

def id_de_config(ruta: str) -> str | None:
	"""``config/plugins/zc.git.json`` → ``zc.git``; ``None`` si no es la configuración de un complemento."""
	if not ruta.startswith("config/plugins/") or ruta.count("/") != 2 or not ruta.endswith(".json"):
		return None
	return ruta[len("config/plugins/"):-len(".json")] or None


def declaraciones_de_paquete(paquete: bytes) -> list[dict] | None:
	"""Los ``[[configuracion]]`` del manifiesto de un ``.zcplugin`` (None si no se puede leer)."""
	try:
		with zipfile.ZipFile(io.BytesIO(paquete)) as zf:
			with zf.open("manifiesto.toml") as entrada:
				datos = tomllib.loads(entrada.read(1024 * 1024).decode("utf-8"))
	except (KeyError, zipfile.BadZipFile, OSError, ValueError, UnicodeDecodeError):
		return None
	declaraciones = datos.get("configuracion", [])
	return [d for d in declaraciones if isinstance(d, dict)] if isinstance(declaraciones, list) else []


def claves_que_ejecutan(id_complemento: str, copia: CopiaAbierta | None = None) -> set[str] | None:
	"""Claves cortas con ``ejecuta`` de un complemento; ``None`` si no se conoce su manifiesto."""
	from app.plugins import registro

	declaraciones: list[dict] | None = None
	registrado = registro.complemento(id_complemento)
	if registrado is not None:
		declaraciones = registrado.manifiesto.tabla("configuracion")
	elif copia is not None:
		paquete = f"{formato.PAQUETES}{id_complemento}.zcplugin"
		if copia.tiene("complementos", paquete) and "complementos" not in copia.danadas:
			declaraciones = declaraciones_de_paquete(copia.leer("complementos", paquete))
	extra = formato.EJECUTA_COMPLEMENTOS.get(id_complemento, frozenset())
	if declaraciones is None:
		return set(extra) if extra else None
	return {str(d["clave"]) for d in declaraciones if d.get("ejecuta") is True and "clave" in d} | set(extra)


def _ajustes(datos: Any) -> dict:
	from app.plugins.config_plugins import SECCION

	ajustes = datos.get(SECCION) if isinstance(datos, dict) else None
	return ajustes if isinstance(ajustes, dict) else {}


# ── Análisis ──────────────────────────────────────────────────────────────────

def analizar(copia: CopiaAbierta, partes: list[str] | None = None, ruta_datos: Path | None = None,
		secretos: dict[str, str] | None = None, ejecutable_rclone: Path | None = None) -> Analisis:
	"""Lo que la copia haría ejecutar y aún no está igual en este equipo."""
	from app.core import paths
	from app.core.descripciones_config import EJECUTA

	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	partes = [p for p in (partes if partes is not None else copia.partes) if p in copia.partes_validas]
	analisis = Analisis()
	anotar = analisis.elementos.append
	for parte in partes:
		for archivo in copia.archivos_datos(parte):
			if archivo.ruta in combinar.LISTAS_EJECUTABLES:
				_analizar_lista(copia, parte, archivo.ruta, ruta_datos, anotar)
	if "preferencias" in partes:
		actuales = valores_actuales(ruta_datos)
		for clave, valor in sorted(copia.valores("preferencias").items()):
			if clave in EJECUTA and not combinar.iguales(actuales.get(clave), valor):
				anotar(ElementoEjecutable(f"clave:{clave}", "preferencias",
					f"{etiqueta_clave(clave)}: {_valor_texto(valor)}"))
	if "complementos" in partes:
		_analizar_complementos(copia, ruta_datos, anotar)
	if "conexiones" in partes and copia.tiene("conexiones", formato.RCLONE_CONF):
		_analizar_rclone(copia, ruta_datos, secretos, ejecutable_rclone, analisis)
	return analisis


def _analizar_lista(copia: CopiaAbierta, parte: str, ruta: str, ruta_datos: Path, anotar) -> None:
	datos = copia.leer_json(parte, ruta)
	if datos is None:
		return
	campo = combinar.LISTAS[ruta][1]
	locales = {combinar._clave(e.get(campo)): e for e in combinar.elementos_lista(_leer_local_json(ruta_datos, ruta), ruta)}
	for elemento in combinar.elementos_lista(datos, ruta):
		actual = locales.get(combinar._clave(elemento.get(campo)))
		if actual is not None and combinar.iguales(actual, elemento):
			continue
		anotar(ElementoEjecutable(combinar.id_elemento(ruta, elemento), parte, texto_elemento(ruta, elemento)))


def _analizar_complementos(copia: CopiaAbierta, ruta_datos: Path, anotar) -> None:
	programador_distinto = False
	for archivo in copia.archivos_datos("complementos"):
		if archivo.ruta.startswith(formato.CARPETA_PROGRAMADOR):
			if _leer_local(ruta_datos, archivo.ruta) != copia.leer("complementos", archivo.ruta):
				programador_distinto = True
			continue
		id_complemento = id_de_config(archivo.ruta)
		if id_complemento is None:
			continue
		ajustes = _ajustes(copia.leer_json("complementos", archivo.ruta))
		if not ajustes:
			continue
		locales = _ajustes(_leer_local_json(ruta_datos, archivo.ruta))
		claves = claves_que_ejecutan(id_complemento, copia)
		if claves is None:
			if not combinar.iguales(ajustes, locales):
				anotar(ElementoEjecutable(f"plugin:{id_complemento}:*", "complementos",
					_("Toda la configuración del complemento {c}, que no está instalado (no se sabe qué ejecuta): {v}").format(
						c=id_complemento, v=json.dumps(ajustes, ensure_ascii=False))))
			continue
		for clave in sorted(claves):
			if clave in ajustes and not combinar.iguales(ajustes[clave], locales.get(clave)):
				anotar(ElementoEjecutable(f"plugin:{id_complemento}:{clave}", "complementos",
					_("Complemento {c}, {k}: {v}").format(c=id_complemento, k=clave, v=_valor_texto(ajustes[clave]))))
	if programador_distinto:
		tareas = [a.ruta[len(formato.CARPETA_PROGRAMADOR):] for a in copia.archivos_datos("complementos")
			if a.ruta.startswith(formato.CARPETA_PROGRAMADOR)]
		anotar(ElementoEjecutable("programador:*", "complementos",
			_("Tareas del programador de tareas (se ejecutan solas, a su hora): {a}").format(a=", ".join(tareas))))


def _nombres_cuentas(copia: CopiaAbierta) -> dict[str, str]:
	datos = copia.leer_json("conexiones", formato.CUENTAS_NUBES, {}) if copia.tiene("conexiones", formato.CUENTAS_NUBES) else {}
	cuentas = datos.get("cuentas") if isinstance(datos, dict) else None
	return {str(c.get("id")): str(c.get("nombre") or c.get("id")) for c in cuentas or [] if isinstance(c, dict) and c.get("id")}


def _analizar_rclone(copia: CopiaAbierta, ruta_datos: Path, secretos: dict[str, str] | None,
		ejecutable: Path | None, analisis: Analisis) -> None:
	contenido = copia.leer("conexiones", formato.RCLONE_CONF)
	contrasena = (secretos or {}).get(f"{formato.SECRETOS_NUBES}rclone_config_pass")
	if rclone.cifrado(contenido) and not contrasena:
		analisis.rclone_sin_revisar = True
		return
	try:
		remotos = rclone.remotos(contenido, contrasena or "", Path(ruta_datos) / "temp", ejecutable)
	except ErrorCopia as error:
		# Sin poder revisarlo, ningún remoto se da por bueno: se trata como uno solo sin marcar.
		analisis.avisos.append(error.mensaje)
		analisis.elementos.append(ElementoEjecutable("rclone:*", "conexiones",
			_("Todas las cuentas de nube de la copia (no se pudieron revisar: {e})").format(e=error.mensaje)))
		return
	nombres = _nombres_cuentas(copia)
	for remoto in rclone.ejecutables(remotos):
		tipo = remoto.tipo.upper() if remoto.tipo in ("webdav", "sftp", "ftp") else remoto.tipo or "?"
		analisis.elementos.append(ElementoEjecutable(f"rclone:{remoto.nombre}", "conexiones",
			_("Cuenta de nube {n} ({t}): ejecuta {v} para conectarse ({o})").format(
				n=nombres.get(remoto.nombre, remoto.nombre), t=tipo, v=remoto.valor, o=remoto.opcion)))
