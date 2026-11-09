# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paquetes ``.zcplugin``: validar, instalar, actualizar, volver atrás y desinstalar (diseño 2.0, 3.9 y 3.10). Sin wx.

Bloque PL. Reglas que aplica:

- **Paquete seguro**: el ZIP entero se valida ANTES de escribir nada (sin rutas
  absolutas, ``..``, unidades, flujos alternativos, nombres reservados, enlaces
  ni duplicados; 200 MB expandido y 20 000 miembros como máximo) y se extrae a
  una carpeta temporal de ``data/temp`` contando los bytes reales.
- **Dónde se instala**: un id que no está registrado en esta sesión y no tiene
  ``al_arrancar`` va directo a ``data/plugins/<id>/`` y se registra sin
  reiniciar; cualquier otro caso (actualización o ``al_arrancar``) va a
  ``data/plugins/.pendientes/<id>/`` y se aplica al reiniciar.
- **Confianza**: firma Ed25519 con las claves del proyecto, las de confianza,
  la fijada para el id o, la primera vez, la que declara el paquete (que queda
  fijada); sin firma, la persona acepta y se guarda la suma del paquete en
  ``complementos.confiados``.
- **Al reiniciar** (``aplicar_pendientes``, antes de descubrir): se mueven
  carpetas y nada más. Los ``al_instalar`` y ``al_desinstalar`` de lo aplicado
  se ejecutan después de mostrar la ventana (``ejecutar_gancho``).

Las funciones marcadas [trabajo] leen o escriben disco y se llaman en un hilo.
"""

from __future__ import annotations

import ast
import base64
import builtins
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import stat
import threading
import uuid
import zipfile
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import almacen_json, paths
from app.plugins import firma, manifiesto, registro
from app.plugins.estado import EstadoComplemento, Pendiente
from app.services.vfs.base import ErrorArchivos, NoAdmitido

log = logging.getLogger(__name__)

EXTENSION = ".zcplugin"
LIMITE_EXPANDIDO = 200 * 1024 * 1024
LIMITE_MIEMBROS = 20_000
TIEMPO_GANCHO_S = 30.0
ANTERIORES_CONSERVADAS = 2
PENDIENTES = ".pendientes"
ANTERIORES = ".anteriores"
DESINSTALADOS = ".desinstalados"
ACCIONES = "acciones.json"
CLAVES = "claves.json"
#: Lo firmado en el JSON de actualización de un complemento es su JSON canónico sin ``firma_ed25519``
#: y SIN prefijo: así lo firma ``tools/publicar.py --firmar-complementos`` (AC, con ``serializar_canonico``
#: del actualizador). El campo ``id``, que debe coincidir, lo distingue del manifiesto de la aplicación.
PREFIJO_ACTUALIZACION = b""
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_UNIDAD = re.compile(r"^[A-Za-z]:")

TEXTOS_PERMISOS = {
	"red": "Conectarse a Internet y a la red local",
	"ejecutar_programas": "Ejecutar programas",
	"escribir_fuera_de_paneles": "Escribir archivos fuera de las carpetas de los paneles",
	"portapapeles": "Usar el portapapeles",
	"secretos": "Guardar contraseñas y fichas de acceso",
	"sonido": "Reproducir sonido",
	"segundo_plano": "Trabajar en segundo plano",
	"teclas_globales": "Registrar teclas globales",
	"elevacion": "Pedir permisos de administrador",
}


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorPaquete(ErrorArchivos):
	"""Paquete que no se puede instalar; el mensaje es para la persona."""


# ── Carpetas y archivos auxiliares ───────────────────────────────────────────


def carpeta_usuario() -> Path:
	return paths.ruta_plugins_usuario()


def carpeta_pendientes() -> Path:
	return carpeta_usuario() / PENDIENTES


def carpeta_anteriores() -> Path:
	return carpeta_usuario() / ANTERIORES


def carpeta_desinstalados() -> Path:
	return carpeta_usuario() / DESINSTALADOS


def leer_claves() -> dict:
	"""``data/config/plugins/claves.json``: claves de confianza y clave fijada por id (3.9)."""
	datos = almacen_json.leer(CLAVES, {"version": 1, "confiadas": [], "por_id": {}}, carpeta=paths.ruta_config_plugins())
	if not isinstance(datos.get("confiadas"), list):
		datos["confiadas"] = []
	if not isinstance(datos.get("por_id"), dict):
		datos["por_id"] = {}
	return datos


def escribir_claves(datos: dict) -> None:
	almacen_json.escribir(CLAVES, datos, carpeta=paths.ruta_config_plugins())


def _leer_acciones() -> dict[str, dict]:
	datos = almacen_json.leer(ACCIONES, {"version": 1, "acciones": {}}, carpeta=carpeta_pendientes())
	acciones = datos.get("acciones", {})
	return acciones if isinstance(acciones, dict) else {}


def _escribir_acciones(acciones: dict[str, dict]) -> None:
	almacen_json.escribir(ACCIONES, {"version": 1, "acciones": acciones}, carpeta=carpeta_pendientes())


def _obtener(config: Any, clave: str, defecto: Any) -> Any:
	if config is None:
		return defecto
	try:
		return config.obtener(clave)
	except Exception:  # noqa: BLE001 - una configuración sin la clave da el valor por defecto
		log.debug("Sin la clave %s", clave, exc_info=True)
		return defecto


def _confiados(config: Any) -> dict[str, str]:
	valor = _obtener(config, "complementos.confiados", {}) or {}
	return dict(valor) if isinstance(valor, dict) else {}


def fijar_confiado(config: Any, id_complemento: str, suma: str | None) -> None:
	"""Guarda (o borra, con ``None``) la suma aceptada de un complemento sin firma."""
	if config is None:
		return
	confiados = _confiados(config)
	if suma is None:
		if id_complemento not in confiados:
			return
		confiados.pop(id_complemento, None)
	else:
		confiados[id_complemento] = suma
	config.establecer("complementos.confiados", confiados)


def _mover(origen: Path, destino: Path) -> None:
	"""Mueve una carpeta (renombrado si se puede; si no, copia y borra)."""
	destino.parent.mkdir(parents=True, exist_ok=True)
	if destino.exists():
		shutil.rmtree(destino)
	try:
		os.replace(origen, destino)
	except OSError:
		shutil.move(str(origen), str(destino))


def _version_de(carpeta: Path) -> str:
	try:
		return manifiesto.leer(carpeta).version
	except manifiesto.ErrorManifiesto:
		return "0.0.0"


def _tupla_version(texto: str) -> tuple[int, ...]:
	try:
		return tuple(int(x) for x in texto.split("."))
	except ValueError:
		return (0,)


# ── Validación del ZIP ───────────────────────────────────────────────────────


def _problema_nombre(nombre: str) -> str | None:
	if not nombre or "\\" in nombre or nombre.startswith("/") or _UNIDAD.match(nombre):
		return _("ruta absoluta o con unidad")
	if ":" in nombre:
		return _("nombre con dos puntos (flujo alternativo)")
	partes = nombre.rstrip("/").split("/")
	for parte in partes:
		if parte in ("", ".", ".."):
			return _("ruta con «..» o tramos vacíos")
		if parte.split(".")[0].upper() in _RESERVADOS:
			return _("nombre reservado de Windows")
		if parte.endswith((" ", ".")) or any(ord(c) < 32 or c in '<>"|?*' for c in parte):
			return _("nombre no válido en Windows")
	return None


def validar_zip(paquete: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
	"""Valida TODO el ZIP sin escribir nada; devuelve sus archivos (no las carpetas).

	:raises ErrorPaquete: con el primer problema encontrado.
	"""
	miembros = paquete.infolist()
	if len(miembros) > LIMITE_MIEMBROS:
		raise ErrorPaquete(_("El paquete tiene más de {n} archivos").format(n=LIMITE_MIEMBROS))
	vistos: set[str] = set()
	total = 0
	archivos = []
	for info in miembros:
		problema = _problema_nombre(info.filename)
		if problema:
			raise ErrorPaquete(_("El paquete no es seguro: «{n}» ({p})").format(n=info.filename, p=problema))
		modo = (info.external_attr >> 16) & 0o170000
		if modo == stat.S_IFLNK:
			raise ErrorPaquete(_("El paquete no es seguro: «{n}» es un enlace").format(n=info.filename))
		if info.flag_bits & 0x1:
			raise ErrorPaquete(_("El paquete tiene archivos cifrados: «{n}»").format(n=info.filename))
		clave = info.filename.rstrip("/").casefold()
		if clave in vistos:
			raise ErrorPaquete(_("El paquete tiene un archivo repetido: «{n}»").format(n=info.filename))
		vistos.add(clave)
		if info.is_dir():
			continue
		total += info.file_size
		if total > LIMITE_EXPANDIDO:
			raise ErrorPaquete(_("El paquete ocupa más de 200 MB descomprimido"))
		archivos.append(info)
	return archivos


def _extraer(paquete: zipfile.ZipFile, archivos: list[zipfile.ZipInfo], destino: Path) -> None:
	"""Extrae contando los bytes reales (una cabecera que miente no pasa del límite)."""
	total = 0
	for info in archivos:
		ruta = destino.joinpath(*info.filename.split("/"))
		ruta.parent.mkdir(parents=True, exist_ok=True)
		with paquete.open(info) as entrada, open(ruta, "wb") as salida:
			while bloque := entrada.read(1024 * 1024):
				total += len(bloque)
				if total > LIMITE_EXPANDIDO:
					raise ErrorPaquete(_("El paquete ocupa más de 200 MB descomprimido"))
				salida.write(bloque)


def marca_web(ruta: Path) -> bool:
	"""Verdadero si el archivo tiene la marca de la Web (``Zone.Identifier`` con zona 3 o 4)."""
	try:
		with open(f"{ruta}:Zone.Identifier", encoding="utf-8", errors="replace") as flujo:
			texto = flujo.read()
	except OSError:
		return False
	coincide = re.search(r"ZoneId\s*=\s*(\d+)", texto)
	return bool(coincide and int(coincide.group(1)) >= 3)


# ── Análisis del código (avisos del gestor) ──────────────────────────────────


def partes_internas(carpeta: Path) -> list[str]:
	"""Importaciones de ``app.`` fuera de ``app.plugins.api`` (el gestor marca «usa partes internas», 3.5)."""
	encontradas: list[str] = []
	for archivo in sorted(Path(carpeta).rglob("*.py")):
		if "lib" in archivo.relative_to(carpeta).parts[:1]:
			continue
		try:
			arbol = ast.parse(archivo.read_text(encoding="utf-8"))
		except (OSError, SyntaxError, ValueError):
			continue
		for nodo in ast.walk(arbol):
			nombres: list[str] = []
			if isinstance(nodo, ast.Import):
				nombres = [a.name for a in nodo.names]
			elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
				if nodo.module == "app.plugins" and all(a.name == "api" for a in nodo.names):
					continue
				nombres = [nodo.module]
			for nombre in nombres:
				if (nombre == "app" or nombre.startswith("app.")) and nombre not in ("app.plugins.api",):
					encontradas.append(f"{archivo.relative_to(carpeta).as_posix()}: {nombre}")
	return encontradas


def modulos_lib(carpeta: Path) -> set[str]:
	lib = Path(carpeta) / "lib"
	if not lib.is_dir():
		return set()
	return {p.stem.split(".")[0] if p.is_file() else p.name for p in lib.iterdir()
		if (p.is_dir() and (p / "__init__.py").is_file()) or p.suffix in (".py", ".pyd")}


def choques_lib(carpeta: Path | None = None, id_complemento: str = "") -> dict[str, list[str]]:
	"""Módulos de nivel superior de ``lib/`` que traen dos complementos o más (3.8): módulo → ids."""
	por_modulo: dict[str, list[str]] = {}
	for registrado in registro.complementos():
		if registrado.id == id_complemento:
			continue
		for modulo in modulos_lib(registrado.carpeta):
			por_modulo.setdefault(modulo, []).append(registrado.id)
	if carpeta is not None:
		for modulo in modulos_lib(carpeta):
			por_modulo.setdefault(modulo, []).append(id_complemento or str(carpeta))
	return {m: ids for m, ids in por_modulo.items() if len(ids) > 1}


# ── Resumen de un paquete ────────────────────────────────────────────────────


@dataclass
class Resumen:
	"""Lo que la persona ve antes de instalar (3.10), y la carpeta ya extraída en ``data/temp``."""

	ruta: Path
	carpeta: Path
	manifiesto: manifiesto.Manifiesto | None = None
	problemas: list[str] = field(default_factory=list)
	avisos: list[str] = field(default_factory=list)
	archivos: list[tuple[str, int]] = field(default_factory=list)
	tamano: int = 0
	firmado: bool = False
	firma_valida: bool = False
	clave: str | None = None
	clave_nueva: bool = False
	confianza: str = ""
	motivo_firma: str = ""
	descargado: bool = False
	instalada: str = ""
	actualizacion: bool = False
	reinicio: bool = False
	suma: str = ""

	@property
	def instalable(self) -> bool:
		return self.manifiesto is not None and not self.problemas

	@property
	def sin_firma(self) -> bool:
		return not self.firma_valida

	@property
	def id(self) -> str:
		return self.manifiesto.id if self.manifiesto else ""

	def texto(self) -> str:
		"""Resumen accesible en texto (nombre, versión, autor, licencia, confianza, procedencia, permisos...)."""
		from app.services import formato

		lineas: list[str] = []
		datos = self.manifiesto
		if datos is None:
			lineas.append(_("El paquete {n} no se puede instalar.").format(n=self.ruta.name))
		else:
			lineas.append(_("Nombre: {n}").format(n=datos.nombre))
			if self.instalada:
				lineas.append(_("Versión: {v} (instalada: {i})").format(v=datos.version, i=self.instalada))
			else:
				lineas.append(_("Versión: {v}").format(v=datos.version))
			lineas.append(_("Identificador: {i}").format(i=datos.id))
			lineas.append(_("Autor: {a}").format(a=datos.autor))
			lineas.append(_("Licencia: {l}").format(l=datos.licencia))
			lineas.append(_("Descripción: {d}").format(d=datos.descripcion))
			lineas.append(_("Confianza: {c}").format(c=self.confianza))
			if self.motivo_firma:
				lineas.append(_("Firma: {m}").format(m=self.motivo_firma))
			lineas.append(_("Procedencia: {p}").format(
				p=_("Descargado de Internet") if self.descargado else _("Archivo de este equipo o de la red local")))
			lineas.append(_("Archivo: {r}").format(r=self.ruta))
			permisos = [texto_permiso(p) for p in datos.permisos]
			lineas.append(_("Permisos: {p}").format(p="; ".join(permisos) if permisos else _("ninguno")))
			lineas.append(_("Necesita los complementos: {d}").format(
				d=", ".join(datos.requiere_complementos) if datos.requiere_complementos else _("ninguno")))
			lineas.append(_("Necesita los componentes: {c}").format(
				c=", ".join(datos.requiere_componentes) if datos.requiere_componentes else _("ninguno")))
			if self.reinicio:
				lineas.append(_("Se aplicará al reiniciar zCommander."))
		if self.problemas:
			lineas.append("")
			lineas.append(_("No se puede instalar:"))
			lineas.extend(f"- {p}" for p in self.problemas)
		if self.avisos:
			lineas.append("")
			lineas.append(_("Avisos:"))
			lineas.extend(f"- {a}" for a in self.avisos)
		lineas.append("")
		lineas.append(_("{n} archivos, {t}:").format(n=len(self.archivos), t=formato.tamano_legible(self.tamano)))
		lineas.extend(f"{nombre} ({formato.tamano_legible(tamano)})" for nombre, tamano in self.archivos)
		return "\n".join(lineas)


def texto_permiso(permiso: str) -> str:
	if permiso.startswith("internet:"):
		return _("Conectarse a {h}").format(h=permiso.split(":", 1)[1])
	return _(TEXTOS_PERMISOS.get(permiso, permiso))


def _confianza_firma(resumen: Resumen, datos: manifiesto.Manifiesto, claves: dict) -> None:
	"""Comprueba la firma del paquete extraído y fija la confianza (3.9)."""
	por_id = claves.get("por_id", {})
	confiadas = [str(c) for c in claves.get("confiadas", [])]
	reservado = datos.id.startswith("zc.")
	declaracion = firma.leer_declaracion(resumen.carpeta)
	resumen.firmado = declaracion is not None
	if declaracion is not None:
		declarada = firma.declaracion_de(resumen.carpeta)
		if declarada != (datos.id, datos.version):
			resumen.motivo_firma = _("La firma es de otro complemento o de otra versión")
		else:
			if datos.id in por_id:
				lista = [por_id[datos.id]]
			elif reservado:
				lista = list(firma.CLAVES_PROYECTO)
			else:
				lista = [*firma.CLAVES_PROYECTO, *confiadas]
				nueva = firma.clave_declarada(resumen.carpeta)
				if nueva and nueva not in lista:
					lista.append(nueva)
			resultado = firma.verificar_complemento(resumen.carpeta, lista, comprobar_sumas=True)
			if resultado.valida:
				resumen.firma_valida, resumen.clave = True, resultado.clave
			else:
				resumen.motivo_firma = resultado.motivo
	if resumen.firma_valida:
		if resumen.clave in firma.CLAVES_PROYECTO:
			resumen.confianza = _("Oficial")
		elif resumen.clave in confiadas or por_id.get(datos.id) == resumen.clave:
			resumen.confianza = _("Firmado por un autor de confianza")
		else:
			resumen.confianza = _("Firmado por un autor nuevo")
			resumen.clave_nueva = True
			resumen.avisos.append(_("Es la primera vez que se instala este complemento firmado: la clave de su autor quedará "
				"fijada y sus actualizaciones tendrán que venir firmadas con ella."))
		return
	resumen.confianza = _("Sin firma")
	if datos.id in por_id:
		resumen.problemas.append(_("Esta actualización no está firmada por el mismo autor que la versión instalada"))
	elif reservado:
		resumen.problemas.append(_("Los id zc.* están reservados a los complementos oficiales y este paquete no lleva la firma del proyecto"))


def preparar(ruta: Path, config: Any = None) -> Resumen:
	"""Valida el paquete, lo extrae a ``data/temp`` y prepara su resumen [trabajo].

	:raises ErrorPaquete: si el archivo no es un ZIP válido o no es seguro (no se escribe nada).
	"""
	ruta = Path(ruta)
	try:
		with zipfile.ZipFile(ruta) as paquete:
			archivos = validar_zip(paquete)
			destino = paths.ruta_temporales() / f"zcplugin-{uuid.uuid4().hex[:12]}"
			destino.mkdir(parents=True)
			try:
				_extraer(paquete, archivos, destino)
			except BaseException:
				shutil.rmtree(destino, ignore_errors=True)
				raise
	except zipfile.BadZipFile as error:
		raise ErrorPaquete(_("{n} no es un paquete de complemento válido").format(n=ruta.name)) from error
	except OSError as error:
		raise ErrorPaquete(_("No se pudo leer {n}: {e}").format(n=ruta.name, e=error)) from error
	resumen = Resumen(ruta=ruta, carpeta=destino, archivos=[(i.filename, i.file_size) for i in archivos],
		tamano=sum(i.file_size for i in archivos), descargado=marca_web(ruta))
	try:
		datos = manifiesto.leer(destino)
	except manifiesto.ErrorManifiesto as error:
		resumen.problemas.extend(error.problemas)
		resumen.confianza = _("Sin firma")
		return resumen
	resumen.manifiesto = datos
	_revisar(resumen, datos, config)
	return resumen


def _revisar(resumen: Resumen, datos: manifiesto.Manifiesto, config: Any) -> None:
	from app.plugins import api

	if not (resumen.carpeta / "LICENSE").is_file():
		resumen.problemas.append(_("Falta el archivo LICENSE"))
	_confianza_firma(resumen, datos, leer_claves())
	if resumen.sin_firma and not _obtener(config, "complementos.permitir_sin_firma", True):
		resumen.problemas.append(_("Los complementos sin firma no están permitidos (Preferencias, Complementos)"))
	if not manifiesto.compatible(datos, api.API_VERSION, api.API_COMPATIBLE_DESDE):
		resumen.problemas.append(_("Incompatible: necesita la API {v}").format(v=datos.api_minima))
	actual = registro.complemento(datos.id)
	if actual is not None:
		resumen.instalada = actual.manifiesto.version
		if _tupla_version(datos.version) <= _tupla_version(actual.manifiesto.version):
			resumen.problemas.append(_("Ya está instalada la versión {v}, igual o más alta").format(v=actual.manifiesto.version))
		elif actual.manifiesto.api_minima.split(".")[0] != datos.api_minima.split(".")[0]:
			resumen.avisos.append(_("Esta versión pide la API {n} y la instalada pedía la {a}: puede no ser compatible "
				"con lo que guardó la versión anterior").format(n=datos.api_minima, a=actual.manifiesto.api_minima))
	elif (carpeta_usuario() / datos.id).is_dir() or (carpeta_pendientes() / datos.id).is_dir():
		resumen.instalada = _version_de(carpeta_usuario() / datos.id) if (carpeta_usuario() / datos.id).is_dir() else ""
	resumen.actualizacion = actual is not None or (carpeta_usuario() / datos.id).is_dir()
	resumen.reinicio = resumen.actualizacion or "al_arrancar" in datos.activacion
	for requisito in datos.requiere_complementos:
		otro = registro.complemento(manifiesto.id_de_requisito(requisito))
		if otro is None:
			resumen.avisos.append(_("Necesita el complemento {r}, que no está instalado").format(r=requisito))
	for componente in datos.requiere_componentes:
		try:
			from app.services.componentes import estado as estado_componentes

			disponible = estado_componentes.disponible(componente)
		except Exception:  # noqa: BLE001 - sin el servicio de componentes se avisa igual
			log.debug("No se pudo comprobar el componente %s", componente, exc_info=True)
			disponible = False
		if not disponible:
			resumen.avisos.append(_("Necesita el componente {c}, que no está disponible").format(c=componente))
	if resumen.descargado:
		resumen.avisos.append(_("Descargado de Internet"))
	if resumen.sin_firma and not resumen.problemas:
		resumen.avisos.insert(0, _("Este complemento no está firmado. Ejecutará código con sus mismos permisos de Windows. "
			"Instálelo solo si confía en su autor."))
	internas = partes_internas(resumen.carpeta)
	if internas:
		resumen.avisos.append(_("Usa partes internas de zCommander que pueden cambiar sin aviso: {p}").format(p=", ".join(internas[:5])))
	for modulo, ids in choques_lib(resumen.carpeta, datos.id).items():
		resumen.avisos.append(_("Su biblioteca {m} también la trae {o}; se usará la del primero que se active").format(
			m=modulo, o=", ".join(i for i in ids if i != datos.id)))
	try:
		resumen.suma = firma.suma_paquete(resumen.carpeta, datos.id, datos.version)
	except OSError:
		log.warning("No se pudo calcular la suma del paquete %s", resumen.ruta, exc_info=True)


def descartar(resumen: Resumen) -> None:
	"""Borra la carpeta temporal de un resumen que no se instala."""
	shutil.rmtree(resumen.carpeta, ignore_errors=True)


# ── Instalar ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Instalado:
	"""Resultado de ``instalar``: ``directo`` = ya en ``data/plugins`` y listo sin reiniciar."""

	id: str
	carpeta: Path
	directo: bool
	pendiente: Pendiente


def instalar(resumen: Resumen, config: Any = None) -> Instalado:
	"""Mueve el paquete ya extraído a su sitio y guarda la confianza [trabajo].

	:raises ErrorPaquete: si el resumen no es instalable.
	"""
	if not resumen.instalable or resumen.manifiesto is None:
		raise ErrorPaquete("; ".join(resumen.problemas) or _("El paquete no se puede instalar"))
	datos = resumen.manifiesto
	if resumen.reinicio:
		destino = carpeta_pendientes() / datos.id
		pendiente = Pendiente.ACTUALIZAR if resumen.actualizacion else Pendiente.INSTALAR
		acciones = _leer_acciones()
		if acciones.pop(datos.id, None) is not None:
			_escribir_acciones(acciones)
	else:
		destino = carpeta_usuario() / datos.id
		pendiente = Pendiente.NINGUNO
	_mover(resumen.carpeta, destino)
	if resumen.firma_valida and resumen.clave and resumen.clave not in firma.CLAVES_PROYECTO:
		claves = leer_claves()
		if claves["por_id"].get(datos.id) != resumen.clave:
			claves["por_id"][datos.id] = resumen.clave
			escribir_claves(claves)
	if resumen.sin_firma:
		fijar_confiado(config, datos.id, resumen.suma)
	else:
		fijar_confiado(config, datos.id, None)
	log.info("Complemento %s %s instalado en %s (%s)", datos.id, datos.version, destino,
		"al reiniciar" if resumen.reinicio else "sin reiniciar")
	return Instalado(datos.id, destino, not resumen.reinicio, pendiente)


def deshacer_instalacion(instalado: Instalado, config: Any = None) -> None:
	"""Quita una instalación directa cuyo ``al_instalar`` falló o se agotó (3.10)."""
	shutil.rmtree(instalado.carpeta, ignore_errors=True)
	fijar_confiado(config, instalado.id, None)
	log.warning("Instalación de %s deshecha", instalado.id)


# ── Pendientes de reiniciar ──────────────────────────────────────────────────


def pendientes() -> dict[str, Pendiente]:
	"""Cambio pendiente de reiniciar de cada id (carpetas de ``.pendientes`` y ``acciones.json``)."""
	resultado: dict[str, Pendiente] = {}
	carpeta = carpeta_pendientes()
	if carpeta.is_dir():
		for sub in carpeta.iterdir():
			if sub.is_dir():
				id_ = _id_de_carpeta(sub)
				if id_:
					existe = (carpeta_usuario() / id_).is_dir() or registro.complemento(id_) is not None
					resultado[id_] = Pendiente.ACTUALIZAR if existe else Pendiente.INSTALAR
		for id_, accion in _leer_acciones().items():
			if accion.get("accion") == "desinstalar":
				resultado[id_] = Pendiente.DESINSTALAR
			elif accion.get("accion") == "volver_atras":
				resultado[id_] = Pendiente.VOLVER_ATRAS
	return resultado


def _id_de_carpeta(carpeta: Path) -> str:
	try:
		return manifiesto.leer(carpeta).id
	except manifiesto.ErrorManifiesto:
		return carpeta.name


def marcar_desinstalar(id_complemento: str, borrar_datos: bool) -> None:
	"""Desinstalar al reiniciar; con ``borrar_datos`` también su configuración, datos, caché y secretos (3.10)."""
	acciones = _leer_acciones()
	acciones[id_complemento] = {"accion": "desinstalar", "borrar_datos": bool(borrar_datos)}
	_escribir_acciones(acciones)
	shutil.rmtree(carpeta_pendientes() / id_complemento, ignore_errors=True)


def anteriores(id_complemento: str) -> list[tuple[str, Path]]:
	"""Versiones guardadas en ``.anteriores`` (de la más alta a la más baja)."""
	carpeta = carpeta_anteriores()
	if not carpeta.is_dir():
		return []
	encontradas = []
	for sub in carpeta.iterdir():
		if sub.is_dir() and sub.name.startswith(id_complemento + "-"):
			encontradas.append((sub.name[len(id_complemento) + 1:], sub))
	return sorted(encontradas, key=lambda par: _tupla_version(par[0]), reverse=True)


def marcar_volver_atras(id_complemento: str) -> str:
	"""Vuelve a la versión anterior al reiniciar; devuelve la versión. ``ErrorPaquete`` si no hay ninguna."""
	disponibles = anteriores(id_complemento)
	if not disponibles:
		raise ErrorPaquete(_("No hay ninguna versión anterior guardada"))
	version, carpeta = disponibles[0]
	acciones = _leer_acciones()
	acciones[id_complemento] = {"accion": "volver_atras", "carpeta": carpeta.name, "version": version}
	_escribir_acciones(acciones)
	shutil.rmtree(carpeta_pendientes() / id_complemento, ignore_errors=True)
	return version


def cancelar_pendiente(id_complemento: str) -> None:
	acciones = _leer_acciones()
	if acciones.pop(id_complemento, None) is not None:
		_escribir_acciones(acciones)
	shutil.rmtree(carpeta_pendientes() / id_complemento, ignore_errors=True)


def borrar_datos(id_complemento: str) -> None:
	"""Configuración, datos, caché y secretos de un complemento (desinstalar con «Borrar también...»)."""
	from app.plugins import config_plugins

	config_plugins.registro().quitar(id_complemento)
	base_config = paths.ruta_config_plugins()
	for archivo in (base_config / f"{id_complemento}.json", base_config / f"{id_complemento}.json.bak"):
		try:
			archivo.unlink(missing_ok=True)
		except OSError:
			log.warning("No se pudo borrar %s", archivo, exc_info=True)
	for carpeta in (base_config / id_complemento, paths.ruta_cache_plugins() / id_complemento):
		shutil.rmtree(carpeta, ignore_errors=True)
	try:
		from app.core.secretos import obtener_secretos

		almacen = obtener_secretos()
		prefijo = f"plugin:{id_complemento}:"
		for nombre in [n for n in almacen.nombres() if n.startswith(prefijo)]:
			almacen.borrar(nombre)
	except Exception:  # noqa: BLE001 - sin almacén de secretos no hay nada que borrar
		log.warning("No se pudieron borrar los secretos de %s", id_complemento, exc_info=True)


def _guardar_anterior(id_complemento: str, actual: Path) -> None:
	version = _version_de(actual)
	_mover(actual, carpeta_anteriores() / f"{id_complemento}-{version}")
	for _version, sobrante in anteriores(id_complemento)[ANTERIORES_CONSERVADAS:]:
		shutil.rmtree(sobrante, ignore_errors=True)


@dataclass(frozen=True)
class Aplicado:
	"""Lo aplicado al reiniciar: ``accion`` es ``instalar``, ``actualizar``, ``volver_atras`` o ``desinstalar``."""

	id: str
	accion: str
	carpeta: Path


def aplicar_pendientes(config: Any = None) -> list[Aplicado]:
	"""Paso 1 de 3.4 (al arrancar, tras cargar la configuración): solo mueve carpetas. Nunca lanza."""
	aplicados: list[Aplicado] = []
	base_pendientes = carpeta_pendientes()
	if not base_pendientes.is_dir():
		return aplicados
	acciones = _leer_acciones()
	for id_complemento, accion in list(acciones.items()):
		try:
			actual = carpeta_usuario() / id_complemento
			if accion.get("accion") == "desinstalar":
				if actual.is_dir():
					_mover(actual, carpeta_desinstalados() / id_complemento)
				if accion.get("borrar_datos"):
					borrar_datos(id_complemento)
				fijar_confiado(config, id_complemento, None)
				claves = leer_claves()
				if claves["por_id"].pop(id_complemento, None) is not None:
					escribir_claves(claves)
				aplicados.append(Aplicado(id_complemento, "desinstalar", carpeta_desinstalados() / id_complemento))
			elif accion.get("accion") == "volver_atras":
				anterior = carpeta_anteriores() / str(accion.get("carpeta", ""))
				if not anterior.is_dir() or not accion.get("carpeta"):
					log.warning("No se encontró la versión anterior de %s", id_complemento)
				else:
					temporal = carpeta_anteriores() / f".volviendo-{id_complemento}"
					_mover(anterior, temporal)
					if actual.is_dir():
						_guardar_anterior(id_complemento, actual)
					_mover(temporal, actual)
					if firma.leer_declaracion(actual) is None and config is not None:
						datos = manifiesto.leer(actual)
						fijar_confiado(config, id_complemento, firma.suma_paquete(actual, datos.id, datos.version))
					aplicados.append(Aplicado(id_complemento, "volver_atras", actual))
		except Exception:  # noqa: BLE001 - un pendiente roto no impide arrancar
			log.exception("No se pudo aplicar el cambio pendiente de %s", id_complemento)
		acciones.pop(id_complemento, None)
	if (base_pendientes / ACCIONES).exists():
		try:
			_escribir_acciones(acciones)
		except OSError:
			log.warning("No se pudo actualizar %s", base_pendientes / ACCIONES, exc_info=True)
	for sub in sorted(p for p in base_pendientes.iterdir() if p.is_dir()):
		try:
			id_complemento = manifiesto.leer(sub).id
			actual = carpeta_usuario() / id_complemento
			accion = "actualizar" if actual.is_dir() else "instalar"
			if actual.is_dir():
				_guardar_anterior(id_complemento, actual)
			_mover(sub, actual)
			aplicados.append(Aplicado(id_complemento, accion, actual))
			log.info("Complemento %s: %s aplicado al reiniciar", id_complemento, accion)
		except Exception:  # noqa: BLE001
			log.exception("No se pudo aplicar la instalación pendiente %s", sub)
	return aplicados


# ── al_instalar y al_desinstalar (instalacion.py) ────────────────────────────


class _SinUI:
	def __getattr__(self, nombre: str) -> Any:
		raise NoAdmitido(_("al_instalar y al_desinstalar no pueden usar la interfaz"))


def ejecutar_gancho(carpeta: Path, nombre: str, id_complemento: str, permisos: tuple[str, ...] = ()) -> Future:
	"""Llama a ``instalacion.<nombre>(zc)`` en un hilo de trabajo; el futuro da verdadero si fue bien.

	Sin ``instalacion.py`` o sin esa función, verdadero en el acto. Tope de 30 s: si se
	agota, falso (el hilo se abandona, como en 3.8). Sin preguntas: ``zc.ui`` lanza ``NoAdmitido``.
	"""
	futuro: Future = Future()
	archivo = Path(carpeta) / "instalacion.py"
	if not archivo.is_file():
		futuro.set_result(True)
		return futuro
	candado = threading.Lock()

	def resolver(valor: bool) -> None:
		with candado:
			if not futuro.done():
				futuro.set_result(valor)

	def trabajo() -> None:
		from app.plugins import api

		try:
			nombre_modulo = f"zcplugins_instalacion.{manifiesto.codificar(id_complemento)}"
			spec = importlib.util.spec_from_file_location(nombre_modulo, archivo)
			if spec is None or spec.loader is None:
				raise ImportError(str(archivo))
			modulo = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(modulo)
			funcion = getattr(modulo, nombre, None)
			if funcion is not None:
				zc = api.Anfitrion(id_complemento, Path(carpeta), permisos=permisos)
				zc.ui = _SinUI()  # type: ignore[assignment]
				funcion(zc)
			resolver(True)
		except BaseException:  # noqa: BLE001 - un gancho roto se registra y se trata como fallo
			log.exception("Falló %s de %s", nombre, id_complemento)
			resolver(False)

	def agotado() -> None:
		if not futuro.done():
			log.error("%s de %s tarda más de %s s; se abandona su hilo", nombre, id_complemento, TIEMPO_GANCHO_S)
		resolver(False)

	temporizador = threading.Timer(TIEMPO_GANCHO_S, agotado)
	temporizador.daemon = True
	temporizador.start()
	threading.Thread(target=trabajo, name=f"zc-{nombre}-{id_complemento}", daemon=True).start()
	return futuro


def limpiar_desinstalado(id_complemento: str) -> None:
	shutil.rmtree(carpeta_desinstalados() / id_complemento, ignore_errors=True)


# ── Buscar actualizaciones (3.10) ────────────────────────────────────────────


@dataclass(frozen=True)
class Actualizacion:
	id: str
	nombre: str
	version: str
	url: str
	sha256: str
	tamano: int
	novedades: str


def _clave_actualizacion(registrado: registro.Registrado) -> str | None:
	"""Clave con la que debe venir firmado el JSON de actualización (``None`` si el complemento no está firmado)."""
	claves = leer_claves()
	if registrado.id in claves["por_id"]:
		return str(claves["por_id"][registrado.id])
	if firma.leer_declaracion(registrado.carpeta) is not None:
		resultado = firma.verificar_complemento(registrado.carpeta, [*firma.CLAVES_PROYECTO, *claves["confiadas"]],
			comprobar_sumas=False)
		return resultado.clave if resultado.valida else ""
	return None


def verificar_json_actualizacion(datos: dict, clave: str) -> bool:
	"""Firma Ed25519 del JSON de actualización (todo menos ``firma_ed25519``, en JSON canónico)."""
	from cryptography.exceptions import InvalidSignature
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

	cuerpo = {k: v for k, v in datos.items() if k != "firma_ed25519"}
	contenido = PREFIJO_ACTUALIZACION + json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
	try:
		Ed25519PublicKey.from_public_bytes(base64.b64decode(clave)).verify(
			base64.b64decode(str(datos.get("firma_ed25519", "")), validate=True), contenido)
		return True
	except (InvalidSignature, ValueError, TypeError):
		return False


def firmar_json_actualizacion(datos: dict, clave_privada: bytes) -> dict:
	"""Devuelve ``datos`` con ``firma_ed25519`` (para los autores y las pruebas)."""
	from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

	cuerpo = {k: v for k, v in datos.items() if k != "firma_ed25519"}
	contenido = PREFIJO_ACTUALIZACION + json.dumps(cuerpo, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
	firma_bytes = Ed25519PrivateKey.from_private_bytes(bytes(clave_privada)).sign(contenido)
	return {**cuerpo, "firma_ed25519": base64.b64encode(firma_bytes).decode("ascii")}


def _configuracion_red() -> Any:
	from app.core import red
	from app.core.version import APP_VERSION

	return red.ConfiguracionRed("zCommander", APP_VERSION)


def buscar_actualizaciones(cancelacion: Any = None, obtener: Callable[[str], Any] | None = None) -> list[Actualizacion]:
	"""Consulta el ``url_actualizacion`` de cada complemento que lo declara [trabajo]. Nunca instala nada.

	:param obtener: ``obtener(url) -> dict`` (las pruebas lo sustituyen); por defecto, ``app.core.red``.
	"""
	from app.core import red
	from app.services.vfs.base import comprobar

	if obtener is None:
		def obtener(url: str) -> Any:
			return red.obtener(_configuracion_red(), url, tiempo_s=30).json()

	encontradas: list[Actualizacion] = []
	for registrado in registro.complementos():
		comprobar(cancelacion)
		url = str(registrado.manifiesto.datos.get("url_actualizacion", "") or "")
		if not url.startswith("https://") or registrado.estado == EstadoComplemento.ERROR_MANIFIESTO:
			continue
		try:
			datos = obtener(url)
		except Exception:  # noqa: BLE001 - un servidor que falla no impide mirar los demás
			log.warning("No se pudo consultar la actualización de %s", registrado.id, exc_info=True)
			continue
		if not isinstance(datos, dict) or datos.get("id") != registrado.id:
			log.warning("Respuesta de actualización no válida para %s", registrado.id)
			continue
		version = str(datos.get("version", ""))
		destino = str(datos.get("url", ""))
		if not manifiesto.VERSION_VALIDA.match(version) or not destino.startswith("https://"):
			continue
		if _tupla_version(version) <= _tupla_version(registrado.manifiesto.version):
			continue
		clave = _clave_actualizacion(registrado)
		if clave is not None and (not clave or not verificar_json_actualizacion(datos, clave)):
			log.warning("La actualización de %s no está firmada por su autor; se ignora", registrado.id)
			continue
		encontradas.append(Actualizacion(registrado.id, registrado.nombre, version, destino, str(datos.get("sha256", "")),
			int(datos.get("tamano", -1) or -1), str(datos.get("novedades", ""))))
	return encontradas


def descargar_actualizacion(actualizacion: Actualizacion, cancelacion: Any = None,
		al_progresar: Callable[[int, int], None] | None = None) -> Path:
	"""Descarga el paquete a ``data/temp`` comprobando tamaño y SHA-256 [trabajo]."""
	from app.core import descargas, red

	destino = paths.ruta_temporales() / f"{actualizacion.id}-{actualizacion.version}{EXTENSION}"
	destino.parent.mkdir(parents=True, exist_ok=True)
	try:
		return descargas.descargar(_configuracion_red(), actualizacion.url, destino, sha256=actualizacion.sha256,
			tamano=actualizacion.tamano, cancelacion=cancelacion, al_progresar=al_progresar)
	except red.ErrorHTTP as error:
		raise ErrorPaquete(error.mensaje) from error


def comprobacion_periodica(_contexto: Any = None) -> list:
	"""Comprobación periódica que PL registra en el actualizador (5.4): avisa, nunca instala."""
	from app.services.actualizador import Novedad

	encontradas = buscar_actualizaciones()
	if not encontradas:
		return []
	texto = _("Hay actualizaciones de complementos: {l}. Instálelas desde el gestor de complementos.").format(
		l=", ".join(f"{a.nombre} {a.version}" for a in encontradas))
	return [Novedad("complementos", texto, False)]


def suma_archivo(ruta: Path) -> str:
	suma = hashlib.sha256()
	with open(ruta, "rb") as archivo:
		for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
			suma.update(bloque)
	return suma.hexdigest()
