# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Lectura y validación de ``manifiesto.toml`` (diseño 2.0, 3.3). Sin wx.

El manifiesto declara lo que un complemento aporta SIN ejecutar su código:
con él se registran los marcadores (órdenes, sonidos, columnas...) antes de
la activación. Los mensajes de validación van en español: los muestra el
gestor y quedan en el registro.

Lo crea N2 con todas las reglas de 3.3; dueño posterior PL.
"""

from __future__ import annotations

import builtins
import keyword
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMATO = 1
NOMBRE = "manifiesto.toml"

ID_VALIDO = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*(\.[a-z][a-z0-9]*(_[a-z0-9]+)*)+$")
ID_CORTO = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
CLAVE_VALIDA = re.compile(r"^[a-z][a-z0-9_]*$")
VERSION_VALIDA = re.compile(r"^\d+\.\d+\.\d+$")
API_VALIDA = re.compile(r"^\d+\.\d+$")
ENTRADA_VALIDA = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
MASCARA_VALIDA = re.compile(r"^\[[A-Z][A-Z0-9_]+:[^\]\s]+\]$")
SPDX = re.compile(r"^[A-Za-z0-9.+-]+( (AND|OR|WITH) [A-Za-z0-9.+-]+)*$")

BLOQUES_SERIE = ("P1", "P2", "P3", "P4", "P5", "NU", "NS")
AMBITOS = ("panel", "global")
MENUS = ("complementos", "archivos", "comandos", "herramientas", "contextual", "ninguno")
NIVELES = ("novato", "intermedio", "avanzado")
TIPOS_ORDEN = ("normal", "casilla")
ARGUMENTOS = ("", "ruta", "patron", "texto", "json")
TIPOS_COLUMNA = ("texto", "numero", "tamano", "fecha", "duracion")
TIPOS_CONFIG = ("bool", "entero", "decimal", "texto", "opcion", "carpeta", "archivo", "lista", "diccionario")
PRIORIDADES = ("alta", "media", "baja")
PERMISOS = ("red", "ejecutar_programas", "escribir_fuera_de_paneles", "portapapeles", "secretos", "sonido",
	"segundo_plano", "teclas_globales", "elevacion")
#: Marcadores de máscara de la 1.x (1.x §8.14): ninguno de un complemento puede coincidir.
MASCARAS_NUCLEO = frozenset({"[N]", "[E]", "[C]", "[Y]", "[y]", "[M]", "[D]", "[h]", "[m]", "[s]", "[t]", "[P]", "[G]"})
#: Bibliotecas del contrato de 3.7: ningún módulo de ``lib/`` puede llamarse así.
CONTRATO_BIBLIOTECAS = frozenset({"wx", "win32api", "win32con", "pywintypes", "pythoncom", "win32com", "comtypes",
	"send2trash", "cryptography", "paramiko", "bcrypt", "nacl", "py7zr", "markdown", "accessible_output2", "app"})


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorManifiesto(Exception):
	"""Manifiesto que no se puede usar; ``problemas`` lista los mensajes en español."""

	def __init__(self, problemas: list[str], carpeta: Path | None = None) -> None:
		super().__init__("; ".join(problemas))
		self.problemas = problemas
		self.carpeta = carpeta


@dataclass(frozen=True)
class OrdenManifiesto:
	id: str
	etiqueta: str
	ayuda: str
	ambito: str = "global"
	menu: str = "complementos"
	teclas: tuple[str, ...] = ()
	tipo: str = "normal"
	casilla_defecto: bool = False
	disponible_si: str = ""
	nivel: str = ""
	paleta: bool = True
	tecla_global: bool = False
	argumento: str = ""


@dataclass(frozen=True)
class Manifiesto:
	"""Un manifiesto ya validado. Las tablas que N2 no interpreta quedan en ``datos``."""

	id: str
	nombre: str
	descripcion: str
	version: str
	autor: str
	licencia: str
	api_minima: str
	api_probada: str
	entrada: str
	bloque: str = ""
	formato: int = FORMATO
	activacion: tuple[str, ...] = ()
	permisos: tuple[str, ...] = ()
	nivel: str = "novato"
	prueba: str = ""
	dialogo_preferencias: bool = False
	requiere_complementos: tuple[str, ...] = ()
	requiere_componentes: tuple[str, ...] = ()
	ordenes: tuple[OrdenManifiesto, ...] = ()
	sonidos: tuple[dict, ...] = ()
	datos: dict[str, Any] = field(default_factory=dict, compare=False)

	@property
	def codificado(self) -> str:
		"""Id para el nombre del paquete de Python: cada «.» pasa a «__» (3.4)."""
		return codificar(self.id)

	def tabla(self, nombre: str) -> list[dict]:
		valor = self.datos.get(nombre, [])
		return [v for v in valor if isinstance(v, dict)] if isinstance(valor, list) else []

	@property
	def orden_prueba(self) -> str:
		return self.prueba or (self.ordenes[0].id if self.ordenes else "")


def codificar(id: str) -> str:
	return id.replace(".", "__")


def _letra(etiqueta: str) -> str | None:
	encontrada = re.search(r"&([^&\s])", etiqueta)
	return encontrada.group(1).casefold() if encontrada else None


def _version_api(texto: str) -> tuple[int, int]:
	mayor, menor = texto.split(".")
	return int(mayor), int(menor)


def _bool(datos: dict, clave: str, problemas: list[str], donde: str, defecto: bool = False) -> bool:
	valor = datos.get(clave, defecto)
	if not isinstance(valor, bool):
		problemas.append(_("{d}: «{c}» debe ser verdadero o falso").format(d=donde, c=clave))
		return defecto
	return valor


def _validar_teclas(teclas: Any, problemas: list[str], donde: str) -> tuple[str, ...]:
	from app.services import teclas as modulo_teclas

	if not isinstance(teclas, list) or not all(isinstance(t, str) for t in teclas):
		problemas.append(_("{d}: «teclas» debe ser una lista de textos").format(d=donde))
		return ()
	resultado = []
	for tecla in teclas:
		try:
			canonica = modulo_teclas.normalizar(tecla)
		except Exception:  # noqa: BLE001 - normalizar lanza con teclas imposibles
			canonica = ""
		if canonica != tecla:
			problemas.append(_("{d}: la tecla «{t}» no está en formato canónico").format(d=donde, t=tecla))
			continue
		resultado.append(tecla)
	return tuple(resultado)


def _validar_ordenes(datos: dict, problemas: list[str]) -> tuple[OrdenManifiesto, ...]:
	ordenes = []
	vistos: set[str] = set()
	letras: dict[str, dict[str, str]] = {}
	for indice, orden in enumerate(datos.get("ordenes", []) or []):
		donde = _("Orden {n}").format(n=indice + 1)
		if not isinstance(orden, dict):
			problemas.append(_("{d}: debe ser una tabla").format(d=donde))
			continue
		id_ = orden.get("id")
		if not isinstance(id_, str) or not ID_CORTO.match(id_):
			problemas.append(_("{d}: id «{i}» no válido").format(d=donde, i=id_))
			continue
		donde = _("Orden {i}").format(i=id_)
		if id_ in vistos:
			problemas.append(_("{d}: id repetido").format(d=donde))
		vistos.add(id_)
		etiqueta, ayuda = orden.get("etiqueta"), orden.get("ayuda")
		if not isinstance(etiqueta, str) or not etiqueta.strip():
			problemas.append(_("{d}: falta la etiqueta").format(d=donde))
			etiqueta = id_
		if not isinstance(ayuda, str) or not ayuda.strip():
			problemas.append(_("{d}: falta la ayuda").format(d=donde))
			ayuda = ""
		ambito = orden.get("ambito", "global")
		if ambito not in AMBITOS:
			problemas.append(_("{d}: ámbito «{a}» no válido").format(d=donde, a=ambito))
		menu = orden.get("menu", "complementos")
		if menu not in MENUS:
			problemas.append(_("{d}: menú «{m}» no válido").format(d=donde, m=menu))
		tipo = orden.get("tipo", "normal")
		if tipo not in TIPOS_ORDEN:
			problemas.append(_("{d}: tipo «{t}» no válido").format(d=donde, t=tipo))
		nivel = orden.get("nivel", "")
		if nivel and nivel not in NIVELES:
			problemas.append(_("{d}: nivel «{n}» no válido").format(d=donde, n=nivel))
		argumento = orden.get("argumento", "")
		if argumento not in ARGUMENTOS:
			problemas.append(_("{d}: argumento «{a}» no válido").format(d=donde, a=argumento))
		disponible_si = orden.get("disponible_si", "")
		if not isinstance(disponible_si, str):
			problemas.append(_("{d}: «disponible_si» debe ser un patrón").format(d=donde))
			disponible_si = ""
		letra = _letra(etiqueta)
		if letra is not None and menu != "ninguno":
			ocupadas = letras.setdefault(menu, {})
			if letra in ocupadas:
				problemas.append(_("{d}: la letra de acceso {l} ya la usa la orden {o}").format(d=donde, l=letra.upper(), o=ocupadas[letra]))
			ocupadas[letra] = id_
		ordenes.append(OrdenManifiesto(
			id=id_, etiqueta=etiqueta, ayuda=ayuda, ambito=ambito, menu=menu,
			teclas=_validar_teclas(orden.get("teclas", []), problemas, donde),
			tipo=tipo, casilla_defecto=_bool(orden, "casilla_defecto", problemas, donde),
			disponible_si=disponible_si, nivel=nivel, paleta=_bool(orden, "paleta", problemas, donde, True),
			tecla_global=_bool(orden, "tecla_global", problemas, donde), argumento=argumento,
		))
	return tuple(ordenes)


def _validar_sonidos(datos: dict, problemas: list[str]) -> tuple[dict, ...]:
	sonidos = []
	vistos: set[str] = set()
	for indice, sonido in enumerate(datos.get("sonidos", []) or []):
		donde = _("Sonido {n}").format(n=indice + 1)
		if not isinstance(sonido, dict) or not isinstance(sonido.get("id"), str) or not ID_CORTO.match(sonido["id"]):
			problemas.append(_("{d}: falta un id válido").format(d=donde))
			continue
		if sonido["id"] in vistos:
			problemas.append(_("Sonido {i}: id repetido").format(i=sonido["id"]))
		vistos.add(sonido["id"])
		if sonido.get("prioridad", "media") not in PRIORIDADES:
			problemas.append(_("Sonido {i}: prioridad no válida").format(i=sonido["id"]))
		if not isinstance(sonido.get("por_defecto", True), bool):
			problemas.append(_("Sonido {i}: «por_defecto» debe ser verdadero o falso").format(i=sonido["id"]))
		sonidos.append(dict(sonido))
	return tuple(sonidos)


def _validar_tablas(datos: dict, problemas: list[str]) -> None:
	"""Reglas de las tablas que N2 no interpreta todavía (las completa PL al engancharlas)."""
	vistos: set[str] = set()
	for columna in datos.get("columnas", []) or []:
		if not isinstance(columna, dict) or not isinstance(columna.get("id"), str) or not ID_CORTO.match(columna["id"]):
			problemas.append(_("Columna sin id válido"))
			continue
		if columna["id"] in vistos:
			problemas.append(_("Columna {i}: id repetido").format(i=columna["id"]))
		vistos.add(columna["id"])
		if columna.get("tipo", "texto") not in TIPOS_COLUMNA:
			problemas.append(_("Columna {i}: tipo no válido").format(i=columna["id"]))
	for mascara in datos.get("mascaras", []) or []:
		marcador = mascara.get("marcador") if isinstance(mascara, dict) else None
		if not isinstance(marcador, str) or not MASCARA_VALIDA.match(marcador):
			problemas.append(_("Máscara «{m}»: necesita un prefijo propio en mayúsculas y dos puntos, como [EXIF:fecha]").format(m=marcador))
		elif marcador in MASCARAS_NUCLEO:
			problemas.append(_("Máscara «{m}»: coincide con una de zCommander").format(m=marcador))
	for accion in datos.get("acciones_error", []) or []:
		if not isinstance(accion, dict):
			problemas.append(_("Acción de error no válida"))
			continue
		codigos = accion.get("codigos_windows", [])
		if not isinstance(codigos, list) or not all(isinstance(c, int) and not isinstance(c, bool) for c in codigos):
			problemas.append(_("Acción de error {i}: «codigos_windows» debe ser una lista de enteros").format(i=accion.get("id")))
	claves: set[str] = set()
	for config in datos.get("configuracion", []) or []:
		if not isinstance(config, dict):
			problemas.append(_("Configuración no válida"))
			continue
		clave = config.get("clave")
		if not isinstance(clave, str) or not CLAVE_VALIDA.match(clave):
			problemas.append(_("Configuración: clave «{c}» no válida (minúsculas, cifras y guiones bajos, sin puntos)").format(c=clave))
			continue
		if clave in claves:
			problemas.append(_("Configuración {c}: clave repetida").format(c=clave))
		claves.add(clave)
		tipo = config.get("tipo")
		if tipo not in TIPOS_CONFIG:
			problemas.append(_("Configuración {c}: tipo «{t}» no válido").format(c=clave, t=tipo))
		elif not _defecto_coherente(tipo, config.get("defecto"), config):
			problemas.append(_("Configuración {c}: el valor por defecto no es del tipo {t}").format(c=clave, t=tipo))
		if "ejecuta" in config and not isinstance(config["ejecuta"], bool):
			problemas.append(_("Configuración {c}: «ejecuta» debe ser verdadero o falso").format(c=clave))


def _defecto_coherente(tipo: str, defecto: Any, config: dict) -> bool:
	if defecto is None:
		return False
	if tipo == "bool":
		return isinstance(defecto, bool)
	if tipo == "entero":
		return isinstance(defecto, int) and not isinstance(defecto, bool)
	if tipo == "decimal":
		return isinstance(defecto, (int, float)) and not isinstance(defecto, bool)
	if tipo in ("texto", "carpeta", "archivo"):
		return isinstance(defecto, str)
	if tipo == "opcion":
		opciones = [o[0] for o in config.get("opciones", []) if isinstance(o, list) and o]
		return isinstance(defecto, str) and (not opciones or defecto in opciones)
	if tipo == "lista":
		return isinstance(defecto, list)
	return isinstance(defecto, dict)


def _validar_lib(carpeta: Path | None, problemas: list[str]) -> None:
	if carpeta is None:
		return
	lib = Path(carpeta) / "lib"
	if not lib.is_dir():
		return
	prohibidos = set(sys.stdlib_module_names) | CONTRATO_BIBLIOTECAS
	for elemento in lib.iterdir():
		nombre = elemento.stem.split(".")[0] if elemento.is_file() else elemento.name
		if nombre in prohibidos:
			problemas.append(_("lib/{n} tiene el nombre de un módulo de Python o del contrato de bibliotecas").format(n=elemento.name))


def validar(datos: dict, carpeta: Path | None = None) -> Manifiesto:
	"""Valida los datos de un manifiesto. Lanza ``ErrorManifiesto`` con todos los problemas."""
	problemas: list[str] = []
	if datos.get("formato") != FORMATO:
		problemas.append(_("Formato de manifiesto desconocido: {f}").format(f=datos.get("formato")))
	for campo in ("id", "nombre", "descripcion", "version", "autor", "licencia", "api_minima", "api_probada", "entrada"):
		if not isinstance(datos.get(campo), str) or not str(datos.get(campo)).strip():
			problemas.append(_("Falta el campo obligatorio «{c}»").format(c=campo))
	id_ = str(datos.get("id", ""))
	if id_ and not ID_VALIDO.match(id_):
		problemas.append(_("El id «{i}» no es válido: minúsculas y cifras separadas por puntos, como ana.utilidades").format(i=id_))
	if any(keyword.iskeyword(parte) for parte in id_.split(".")):
		problemas.append(_("El id «{i}» contiene una palabra reservada de Python").format(i=id_))
	version = str(datos.get("version", ""))
	if version and not VERSION_VALIDA.match(version):
		problemas.append(_("La versión «{v}» debe tener la forma mayor.menor.parche").format(v=version))
	minima, probada = str(datos.get("api_minima", "")), str(datos.get("api_probada", ""))
	for nombre, valor in (("api_minima", minima), ("api_probada", probada)):
		if valor and not API_VALIDA.match(valor):
			problemas.append(_("«{c}» debe tener la forma mayor.menor").format(c=nombre))
	if API_VALIDA.match(minima) and API_VALIDA.match(probada) and _version_api(minima) > _version_api(probada):
		problemas.append(_("«api_minima» no puede ser mayor que «api_probada»"))
	licencia = str(datos.get("licencia", ""))
	if licencia and not SPDX.match(licencia):
		problemas.append(_("La licencia «{l}» no es un identificador SPDX").format(l=licencia))
	entrada = str(datos.get("entrada", ""))
	if entrada and not ENTRADA_VALIDA.match(entrada):
		problemas.append(_("La entrada «{e}» debe tener la forma módulo:Clase").format(e=entrada))
	bloque = datos.get("bloque", "")
	if bloque and bloque not in BLOQUES_SERIE:
		problemas.append(_("Bloque «{b}» desconocido").format(b=bloque))
	nivel = datos.get("nivel", "novato")
	if nivel not in NIVELES:
		problemas.append(_("Nivel «{n}» no válido").format(n=nivel))
	activacion = datos.get("activacion", [])
	if not isinstance(activacion, list) or not all(isinstance(a, str) and (a == "al_arrancar" or a.startswith("evento:")) for a in activacion):
		problemas.append(_("«activacion» admite al_arrancar y evento:<nombre>"))
		activacion = []
	permisos = datos.get("permisos", [])
	if not isinstance(permisos, list) or not all(isinstance(p, str) and (p in PERMISOS or p.startswith("internet:")) for p in permisos):
		problemas.append(_("Hay permisos desconocidos en «permisos»"))
		permisos = []
	for url in ("web", "codigo_fuente", "url_actualizacion"):
		if url in datos and not str(datos[url]).startswith("https://"):
			problemas.append(_("«{c}» debe ser una dirección https").format(c=url))
	requiere = datos.get("requiere", {}) or {}
	complementos = tuple(str(c) for c in requiere.get("complementos", []) or []) if isinstance(requiere, dict) else ()
	componentes = tuple(str(c) for c in requiere.get("componentes", []) or []) if isinstance(requiere, dict) else ()
	ordenes = _validar_ordenes(datos, problemas)
	sonidos = _validar_sonidos(datos, problemas)
	_validar_tablas(datos, problemas)
	_validar_lib(carpeta, problemas)
	prueba = datos.get("prueba", "")
	if prueba and prueba not in {o.id for o in ordenes}:
		problemas.append(_("«prueba» nombra la orden «{p}», que no está declarada").format(p=prueba))
	dialogo = _bool(datos, "dialogo_preferencias", problemas, _("Manifiesto"))
	if problemas:
		raise ErrorManifiesto(problemas, carpeta)
	return Manifiesto(
		id=id_, nombre=str(datos["nombre"]), descripcion=str(datos["descripcion"]), version=version,
		autor=str(datos["autor"]), licencia=licencia, api_minima=minima, api_probada=probada, entrada=entrada,
		bloque=str(bloque or ""), activacion=tuple(activacion), permisos=tuple(permisos), nivel=str(nivel),
		prueba=str(prueba or ""), dialogo_preferencias=dialogo, requiere_complementos=complementos,
		requiere_componentes=componentes, ordenes=ordenes, sonidos=sonidos, datos=dict(datos),
	)


def leer(carpeta: Path) -> Manifiesto:
	"""Lee y valida ``<carpeta>/manifiesto.toml``. Lanza ``ErrorManifiesto``."""
	ruta = Path(carpeta) / NOMBRE
	try:
		with ruta.open("rb") as archivo:
			datos = tomllib.load(archivo)
	except FileNotFoundError as error:
		raise ErrorManifiesto([_("No hay manifiesto.toml")], Path(carpeta)) from error
	except (OSError, tomllib.TOMLDecodeError) as error:
		raise ErrorManifiesto([_("El manifiesto no se puede leer: {e}").format(e=error)], Path(carpeta)) from error
	return validar(datos, Path(carpeta))


def id_de_requisito(texto: str) -> str:
	"""«zc.metadatos >= 1.0» → «zc.metadatos»."""
	return re.split(r"[\s<>=!]", texto.strip(), maxsplit=1)[0]


def compatible(manifiesto: Manifiesto, api_version: tuple[int, int], api_compatible_desde: tuple[int, int]) -> bool:
	"""Se carga si ``api_minima <= API_VERSION`` y ``api_probada >= API_COMPATIBLE_DESDE``."""
	return _version_api(manifiesto.api_minima) <= api_version and _version_api(manifiesto.api_probada) >= api_compatible_desde
