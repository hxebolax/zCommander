# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Configuración y preferencias de la aplicación (archivo JSON portable).

Qué resuelve este módulo y por qué:

- **Valores por defecto en código** (``VALORES_POR_DEFECTO``), agrupados por
  secciones. El archivo solo guarda lo que el usuario tiene; al cargar se
  completa con los valores por defecto, así una preferencia nueva aparece sola
  y un archivo de una versión antigua sigue funcionando.
- **Archivo en ``data/config/settings.json``**, junto al programa (portable).
- **Tolerancia a daños.** Un JSON corrupto se aparta como
  ``settings.json.corrupto-AAAAMMDD_HHMMSS`` (no se pierde), se intenta la copia
  ``settings.json.bak`` y, si tampoco sirve, se arranca con los valores por
  defecto. Todo queda registrado y ``recuperacion`` dice qué pasó para que la
  interfaz se lo cuente al usuario.
- **Escritura atómica**: temporal único en la misma carpeta + ``fsync`` +
  ``os.replace``. Un corte de luz deja el archivo viejo o el nuevo, nunca uno a
  medias. Antes se copia el archivo actual a ``.bak``.
- **Seguro entre hilos** (``RLock`` para los datos, otro candado para el disco:
  la interfaz no espera al ``fsync`` de un guardado de fondo).
- **Claves «seccion.clave»** con ``obtener``/``establecer``.
- **Versión de esquema y migraciones** (claves renombradas, movidas o
  eliminadas) que se aplican una sola vez al cargar.
- **Suscriptores**: las ventanas abiertas se enteran de cada cambio y aplican
  la preferencia al momento (sin reiniciar).
- **Validación opcional** de tipos, rangos y opciones con ``REGLAS``.
- **Guardado inmediato, diferido (agrupa cambios rápidos) o por lotes.**

Los secretos (contraseñas, tokens) NO van aquí: van cifrados en
``data/config/secretos.dat`` (módulo ``secretos``).

Basado en la plantilla del agente «configuracion», con las preferencias de zCommander.
"""

from __future__ import annotations

import builtins
import copy
import json
import logging
import os
import shutil
import threading
import time
import urllib.parse
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	"""Traduce con el ``_`` que gettext instala en ``builtins`` (se busca al llamar, no al importar)."""
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# Variable de entorno que redirige la carpeta data (la usan las pruebas).
VARIABLE_DATA = "APP_DATA_DIR"

NOMBRE_ARCHIVO = "settings.json"

# Clave de la raíz del JSON donde se guarda la versión del esquema.
CLAVE_VERSION = "version_esquema"

# Versión actual del esquema. Súbela cuando añadas una migración.
VERSION_ESQUEMA = 2

# ── Valores por defecto de zCommander ───────────────────────────────────────
# Un diccionario por sección. Cada valor fija también el TIPO esperado. La
# lista comentada de cada clave (qué hace, quién la usa) está en
# docs/configuracion.md, generado con tools/generar_anexos.py.
COLUMNAS_DISPONIBLES = ("nombre", "extension", "tipo", "tamano", "modificado", "creado", "atributos", "ruta")

VALORES_POR_DEFECTO: dict[str, dict[str, Any]] = {
	"general": {
		"confirmar_salida": True,
		"confirmar_eliminar": True,
		"confirmar_eliminar_definitivo": True,
		"confirmar_ejecutar": False,
		"usar_papelera": True,
		"consola": "cmd",
		"ejecutar_siempre_en_consola": False,
		"restaurar_sesion": True,
		"asistente_hecho": False,
		"tiempo_unidad_s": 10,
		"aviso_lectura_ms": 300,
		"tamano_historial": 100,
		"tamano_historial_ordenes": 200,
		"pegar_ruta_del_portapapeles": False,
		"diferencias_externo": "",
		# 2.0 (diseño 2.0, 14.3)
		"arrancar_con_windows": False,
		"no_preguntar": [],
	},
	"paneles": {
		"teclear_en_linea_ordenes": False,
		"mostrar_ocultos": False,
		"carpetas_primero": True,
		"orden_natural": True,
		"fila_superior": True,
		"entrar_en_comprimidos": True,
		"columnas": ["nombre", "extension", "tamano", "modificado"],
		"anchos": {},
		"formato_fecha": "corta",
		"formato_tamano": "legible",
		"iconos": False,
		"vigilar_cambios": True,
		"tiempo_busqueda_rapida_ms": 1000,
		"retardo_arbol_ms": 400,
		"orientacion": "vertical",
		"seleccionar_sin_extension": True,
		"patrones_en_carpetas": False,
		"mover_tras_marcar": True,
		# 2.0.1: cómo se ven y se leen las marcas: «seleccion» (la selección de la lista, como
		# siempre) o «columna» (columna «Marca»; la lista no usa la selección para las marcas).
		"marcas_como": "seleccion",
		# 2.0: orden de lectura de las columnas por defecto (10.5); vacía = el de las columnas.
		"lectura": [],
	},
	"vista": {
		"linea_ordenes_visible": True,
		"barra_teclas_visible": True,
		"barra_estado_visible": True,
		"tema": "sistema",
		"fuente": "",
		"tamano_fuente": 10,
		"vista_rapida_kb": 256,
		# 2.0
		"barra_botones_visible": False,
		"teclas_en_menus": True,
		"menus_por_nivel": False,
		"columnas_por_carpeta": True,
		"recordar_vista_por_carpeta": False,
	},
	"accesibilidad": {
		"anuncios": True,
		"detalle": "normal",
		"progreso_voz": "inicio_fin",
		"consejos": False,
		"leer_numero_fila": True,
		"leer_cabecera": True,
		"leer_contenido": True,
		"retardo_voz_ms": 150,
		"salida_voz": "automatica",
		"sapi_sin_lector": False,
		# 2.0: movimiento silencioso con el complemento de NVDA (10.16) y si ya se ofreció instalarlo.
		"silencio_nvda": True,
		"complemento_nvda_ofrecido": False,
	},
	"operaciones": {
		"politica_conflicto": "preguntar",
		"verificar": False,
		"conservar_fechas": True,
		"copiar_enlaces": True,
		"copiar_carpetas_vacias": True,
		"max_paralelas": 3,
		"tamano_bloque_kb": 1024,
		"lista_conflictos": True,
	},
	"visor": {
		"externo": "",
		"ajuste_linea": True,
		"codificacion": "automatica",
		"limite_mb": 16,
		"tamano_fuente": 11,
	},
	"editor": {
		"usar_externo": False,
		"externo": "notepad.exe %P",
		"copia_seguridad": False,
		"tamano_fuente": 11,
	},
	"busqueda": {
		"subcarpetas": True,
		"ocultos": False,
		"max_resultados": 100000,
	},
	"ftp": {
		"tiempo_espera_s": 30,
		"pasivo": True,
	},
	"teclado": {
		"personalizadas": {},
		# 2.0: esquema de teclas (10.7) y teclas globales (10.15).
		"esquema": "norton",
		"globales": {},
		"globales_activas": False,
	},
	"registro": {
		"nivel": "INFO",
	},
	"ventana": {
		"x": -1,
		"y": -1,
		"ancho": 1100,
		"alto": 760,
		"maximizada": False,
		"division": 0.5,
	},
	"seguridad": {
		"menus_locales_confiados": {},
	},
	# ── Secciones nuevas de la 2.0 (diseño 2.0, 14.3) ──────────────────────
	"complementos": {
		"inhabilitados": [],
		"permitir_sin_firma": True,
		"fallos_maximos": 3,
		"modo_desarrollo": False,
		"auditoria": False,
		"confiados": {},
	},
	"sonidos": {
		"activos": True,
		"volumen": 70,
		"paquete": "clasico",
		"eventos": {},
		"progreso": "no",
		"sustituir_anuncios": False,
		"intervalo_navegacion_ms": 40,
		"aviso_inicial_mostrado": False,
	},
	"actualizaciones": {
		"comprobar": True,
		"intervalo_horas": 24,
		"componentes_comprobar": True,
		"componentes_intervalo_dias": 7,
		"complementos_comprobar": True,
		"fuente": "servidor",
		"url_personalizada": "",
	},
	"copia": {
		"carpeta": "",
		"conservar_automaticas": 5,
		"partes": ["preferencias", "teclas", "sesion", "personalizacion", "conexiones", "complementos", "sonidos", "macros"],
	},
	"comprimidos": {
		"usar_libarchive": True,
		"usar_7za": True,
		"usar_7zip_instalado": True,
		"ruta_7zip": "",
		"metodo_zip": "deflate",
		"flujos_como_carpeta": True,
	},
	"red": {
		"descubrir_al_entrar": True,
		"descubrir_mdns": True,
		"descubrir_dominio": True,
		"tiempo_descubrir_s": 45,
		"reconectar_al_entrar": True,
		"exigir_cifrado": False,
		"mostrar_otros_proveedores": True,
	},
	"linea": {
		"alias_activos": True,
		"autocompletar": True,
	},
	"macros": {
		"anunciar_pasos": False,
		"pausa_ms": 0,
		"detener_en_error": True,
	},
	"reglas": {
		"activas": True,
	},
}


@dataclass(frozen=True)
class Regla:
	"""Restricciones opcionales de una clave.

	:param minimo: valor mínimo (números).
	:param maximo: valor máximo (números).
	:param opciones: valores admitidos (listas cerradas).
	:param longitud_maxima: longitud máxima (textos).
	:param comprobar: función que devuelve el motivo si el valor no vale (p. ej. una dirección https).
	"""

	minimo: float | None = None
	maximo: float | None = None
	opciones: tuple[Any, ...] | None = None
	longitud_maxima: int | None = None
	comprobar: Callable[[Any], str | None] | None = None
	"""Comprobación propia: devuelve el mensaje del error, o ``None`` si el valor vale."""


def comprobar_url_https(valor: Any) -> str | None:
	"""Motivo por el que ``valor`` no es una dirección https completa, o ``None`` si vale (o está vacía)."""
	texto = str(valor or "").strip()
	if not texto:
		return None
	try:
		partes = urllib.parse.urlsplit(texto)
	except ValueError:
		partes = None
	if partes is None or partes.scheme.lower() != "https" or not partes.hostname or any(c.isspace() for c in texto):
		return _("La dirección tiene que ser completa y empezar por https:// (por ejemplo, https://ejemplo.org/zCommander/version.json).")
	if "@" in partes.netloc:
		# 2.0.1: un usuario o una contraseña en la dirección quedarían a la vista en la
		# configuración, en los registros y en las copias de seguridad.
		return _("La dirección no puede llevar usuario ni contraseña (lo que va antes de «@»). Quítelos: "
			"la dirección del archivo version.json tiene que ser pública.")
	return None


# Reglas por clave «seccion.clave». Las claves sin regla solo comprueban el tipo.
REGLAS: dict[str, Regla] = {
	"general.consola": Regla(opciones=("cmd", "powershell", "terminal")),
	"general.tiempo_unidad_s": Regla(minimo=2, maximo=120),
	"general.aviso_lectura_ms": Regla(minimo=0, maximo=5000),
	"general.tamano_historial": Regla(minimo=10, maximo=1000),
	"general.tamano_historial_ordenes": Regla(minimo=10, maximo=2000),
	"paneles.formato_fecha": Regla(opciones=("corta", "larga", "iso")),
	"paneles.formato_tamano": Regla(opciones=("legible", "bytes", "mixto")),
	"paneles.tiempo_busqueda_rapida_ms": Regla(minimo=300, maximo=5000),
	"paneles.retardo_arbol_ms": Regla(minimo=0, maximo=3000),
	"paneles.orientacion": Regla(opciones=("vertical", "horizontal")),
	"paneles.marcas_como": Regla(opciones=("seleccion", "columna")),
	"vista.tema": Regla(opciones=("sistema", "norton", "alto_contraste")),
	"vista.tamano_fuente": Regla(minimo=8, maximo=40),
	"vista.vista_rapida_kb": Regla(minimo=4, maximo=65536),
	"accesibilidad.detalle": Regla(opciones=("breve", "normal", "detallado")),
	"accesibilidad.progreso_voz": Regla(opciones=("hitos", "inicio_fin", "final")),
	"accesibilidad.retardo_voz_ms": Regla(minimo=0, maximo=2000),
	"accesibilidad.salida_voz": Regla(opciones=("automatica", "lector", "uia", "ninguna")),
	"operaciones.politica_conflicto": Regla(opciones=(
		"preguntar", "sobrescribir", "omitir", "sobrescribir_si_mas_antiguo", "sobrescribir_si_cambia_tamano",
		"renombrar_copia", "renombrar_existente",
	)),
	"operaciones.max_paralelas": Regla(minimo=1, maximo=8),
	"operaciones.tamano_bloque_kb": Regla(minimo=64, maximo=65536),
	"visor.codificacion": Regla(opciones=("automatica", "utf-8", "utf-16-le", "utf-16-be", "cp1252", "latin-1", "cp850", "cp437")),
	"visor.limite_mb": Regla(minimo=1, maximo=2048),
	"visor.tamano_fuente": Regla(minimo=8, maximo=40),
	"editor.tamano_fuente": Regla(minimo=8, maximo=40),
	"busqueda.max_resultados": Regla(minimo=100, maximo=10000000),
	"ftp.tiempo_espera_s": Regla(minimo=5, maximo=600),
	"registro.nivel": Regla(opciones=("DEBUG", "INFO", "WARNING", "ERROR")),
	"ventana.division": Regla(minimo=0.1, maximo=0.9),
	# 2.0 (diseño 2.0, 14.3)
	"complementos.fallos_maximos": Regla(minimo=1, maximo=10),
	"sonidos.volumen": Regla(minimo=0, maximo=100),
	"sonidos.progreso": Regla(opciones=("no", "cada_25", "cada_10")),
	"sonidos.intervalo_navegacion_ms": Regla(minimo=0, maximo=500),
	"actualizaciones.intervalo_horas": Regla(minimo=1, maximo=720),
	"actualizaciones.componentes_intervalo_dias": Regla(minimo=1, maximo=90),
	"actualizaciones.fuente": Regla(opciones=("servidor", "github", "ambas", "personalizada")),
	"actualizaciones.url_personalizada": Regla(longitud_maxima=2048, comprobar=comprobar_url_https),
	"copia.conservar_automaticas": Regla(minimo=1, maximo=50),
	"comprimidos.metodo_zip": Regla(opciones=("deflate", "zstd", "almacenar")),
	"red.tiempo_descubrir_s": Regla(minimo=5, maximo=300),
	"teclado.esquema": Regla(opciones=("norton", "total_commander", "far", "explorador")),
	"macros.pausa_ms": Regla(minimo=0, maximo=5000),
}


class ErrorConfiguracion(Exception):
	"""Error de configuración que el llamante debe conocer (no se oculta)."""


class ErrorValidacion(ErrorConfiguracion, ValueError):
	"""Valor que no cumple el tipo o la regla de su clave."""


# ── Migraciones ──────────────────────────────────────────────────────────────

def renombrar_clave(datos: dict, antigua: str, nueva: str) -> bool:
	"""Mueve el valor de ``antigua`` a ``nueva`` (ambas «seccion.clave»).

	Si la clave nueva ya existe, gana la nueva (el usuario ya la configuró con
	una versión más reciente) y la antigua se elimina igualmente.

	:return: ``True`` si había algo que mover.
	"""
	sec_antigua, _, clave_antigua = antigua.partition(".")
	sec_nueva, _, clave_nueva = nueva.partition(".")
	origen = datos.get(sec_antigua)
	if not isinstance(origen, dict) or clave_antigua not in origen:
		return False
	valor = origen.pop(clave_antigua)
	destino = datos.setdefault(sec_nueva, {})
	if isinstance(destino, dict):
		destino.setdefault(clave_nueva, valor)
	if not origen:
		# Sección vacía tras el traslado: se elimina para no dejar restos.
		datos.pop(sec_antigua, None)
	return True


def eliminar_clave(datos: dict, clave: str) -> bool:
	"""Elimina una clave obsoleta. ``True`` si existía."""
	seccion, _, nombre = clave.partition(".")
	contenedor = datos.get(seccion)
	if isinstance(contenedor, dict) and nombre in contenedor:
		del contenedor[nombre]
		return True
	return False


# MIGRACIONES[n] lleva los datos de la versión n a la n+1. Cada función recibe
# el diccionario TAL COMO SE LEYÓ del archivo (antes de completar con los
# valores por defecto) y lo modifica en el sitio. Deben ser idempotentes.
def _anadir_no_preguntar(datos: dict, id_confirmacion: str) -> None:
	"""Añade una confirmación silenciada a ``general.no_preguntar`` sin repetirla (idempotente)."""
	general = datos.setdefault("general", {})
	if not isinstance(general, dict):
		return
	lista = general.get("no_preguntar")
	if not isinstance(lista, list):
		lista = []
	if id_confirmacion not in lista:
		lista.append(id_confirmacion)
	general["no_preguntar"] = lista


def _migrar_1_a_2(datos: dict) -> None:
	"""Esquema 1 (zCommander 1.x) → 2 (zCommander 2.0), diseño 2.0, 14.3.

	- ``accesibilidad.sonidos`` se borra SIN trasladar su valor: la 1.x guardaba
	  escrito su ``false`` de fábrica y no se distingue de una elección, así que
	  ``sonidos.activos`` queda en su valor de fábrica (sí) para todo el mundo
	  (4.5, 21.2.4).
	- ``accesibilidad.tonos_progreso`` pasa a ``sonidos.progreso``.
	- ``ftp.avisar_sin_cifrar`` falso y ``operaciones.aviso_comprimido_mostrado``
	  verdadero pasan a ``general.no_preguntar`` (confirmaciones de 10.12).
	"""
	eliminar_clave(datos, "accesibilidad.sonidos")
	accesibilidad = datos.get("accesibilidad")
	if isinstance(accesibilidad, dict) and "tonos_progreso" in accesibilidad:
		tonos = bool(accesibilidad.pop("tonos_progreso"))
		sonidos = datos.setdefault("sonidos", {})
		if isinstance(sonidos, dict):
			sonidos.setdefault("progreso", "cada_10" if tonos else "no")
	ftp = datos.get("ftp")
	if isinstance(ftp, dict) and "avisar_sin_cifrar" in ftp:
		if ftp.pop("avisar_sin_cifrar") is False:
			_anadir_no_preguntar(datos, "ftp_sin_cifrar")
	operaciones = datos.get("operaciones")
	if isinstance(operaciones, dict) and "aviso_comprimido_mostrado" in operaciones:
		if operaciones.pop("aviso_comprimido_mostrado") is True:
			_anadir_no_preguntar(datos, "comprimido_escritura")


MIGRACIONES: dict[int, Callable[[dict], None]] = {1: _migrar_1_a_2}


# ── Rutas ────────────────────────────────────────────────────────────────────

def carpeta_datos() -> Path:
	"""Carpeta ``data`` portable (única fuente: ``app.core.paths``)."""
	from app.core import paths

	return paths.ruta_datos()


def ruta_por_defecto() -> Path:
	"""``data/config/settings.json``."""
	return carpeta_datos() / "config" / NOMBRE_ARCHIVO


# ── Utilidades internas ──────────────────────────────────────────────────────

_SIN_VALOR = object()


def _fusionar(base: dict, encima: dict) -> None:
	"""Pone ``encima`` sobre ``base`` de forma recursiva.

	Las secciones y claves desconocidas se CONSERVAN: pueden ser de una versión
	más nueva de la aplicación o de un complemento, y descartarlas borraría la
	configuración del usuario al abrir una versión anterior.
	"""
	for clave, valor in encima.items():
		if isinstance(valor, dict) and isinstance(base.get(clave), dict):
			_fusionar(base[clave], valor)
		else:
			base[clave] = copy.deepcopy(valor)


def _tipo_compatible(valor: Any, referencia: Any) -> bool:
	"""Comprueba que ``valor`` tiene el tipo del valor por defecto ``referencia``.

	``bool`` es subclase de ``int`` en Python: se distinguen explícitamente para
	que ``True`` no pase por un número ni ``1`` por un booleano. Un ``int`` sí vale
	donde se espera ``float`` (el JSON escribe ``1.0`` como ``1`` a veces).
	"""
	if referencia is None:
		return True
	if isinstance(referencia, bool):
		return isinstance(valor, bool)
	if isinstance(referencia, int):
		return isinstance(valor, int) and not isinstance(valor, bool)
	if isinstance(referencia, float):
		return isinstance(valor, (int, float)) and not isinstance(valor, bool)
	return isinstance(valor, type(referencia))


def validar_valor(clave: str, valor: Any, reglas: dict[str, Regla] | None = None,
		por_defecto: dict | None = None) -> None:
	"""Lanza ``ErrorValidacion`` si ``valor`` no es válido para ``clave``."""
	reglas = REGLAS if reglas is None else reglas
	por_defecto = VALORES_POR_DEFECTO if por_defecto is None else por_defecto
	seccion, _, nombre = clave.partition(".")
	referencia = por_defecto.get(seccion, {}).get(nombre, _SIN_VALOR)
	if referencia is not _SIN_VALOR and not _tipo_compatible(valor, referencia):
		raise ErrorValidacion(
			f"«{clave}» espera {type(referencia).__name__} y recibió {type(valor).__name__}."
		)
	regla = reglas.get(clave)
	if regla is None:
		return
	if regla.opciones is not None and valor not in regla.opciones:
		raise ErrorValidacion(f"«{clave}» solo admite: {', '.join(map(str, regla.opciones))}.")
	if isinstance(valor, (int, float)) and not isinstance(valor, bool):
		if regla.minimo is not None and valor < regla.minimo:
			raise ErrorValidacion(f"«{clave}» debe ser como mínimo {regla.minimo}.")
		if regla.maximo is not None and valor > regla.maximo:
			raise ErrorValidacion(f"«{clave}» debe ser como máximo {regla.maximo}.")
	if isinstance(valor, str) and regla.longitud_maxima is not None and len(valor) > regla.longitud_maxima:
		raise ErrorValidacion(f"«{clave}» admite como máximo {regla.longitud_maxima} caracteres.")
	if regla.comprobar is not None:
		motivo = regla.comprobar(valor)
		if motivo:
			raise ErrorValidacion(motivo)


def _reemplazar(origen: Path, destino: Path, intentos: int = 5) -> None:
	"""``os.replace`` con reintentos.

	En Windows el reemplazo falla con ``PermissionError`` (WinError 5 o 32) si
	un antivirus, el indexador o una copia de seguridad tiene el destino abierto
	un instante. Se reintenta con una espera corta antes de rendirse.
	"""
	espera = 0.05
	for intento in range(1, intentos + 1):
		try:
			os.replace(origen, destino)
			return
		except PermissionError:
			if intento == intentos:
				raise
			log.debug("Reemplazo de %s bloqueado, reintento %d", destino.name, intento, exc_info=True)
			time.sleep(espera)
			espera *= 2


class _Suscriptor:
	"""Función suscrita a los cambios, con referencia débil si es un método.

	Con una referencia normal, una ventana cerrada seguiría viva en memoria (y
	recibiendo avisos sobre controles ya destruidos). Con ``WeakMethod`` se
	borra sola cuando la ventana desaparece.
	"""

	def __init__(self, funcion: Callable[[str, Any, Any], None], prefijo: str) -> None:
		self.prefijo = prefijo
		if hasattr(funcion, "__self__") and hasattr(funcion, "__func__"):
			self._ref: Callable[[], Any] = weakref.WeakMethod(funcion)
		else:
			self._ref = lambda: funcion

	def funcion(self) -> Callable[[str, Any, Any], None] | None:
		return self._ref()


# ── Clase principal ──────────────────────────────────────────────────────────

class Configuracion:
	"""Preferencias de la aplicación persistidas en JSON.

	Uso típico::

		config = obtener_configuracion()
		tamano = config.obtener("apariencia.tamano_fuente")
		config.establecer("apariencia.tamano_fuente", 14)   # guarda y avisa

	:param ruta: archivo JSON (por defecto ``data/config/settings.json``).
	:param por_defecto: valores por defecto (por defecto ``VALORES_POR_DEFECTO``).
	:param reglas: reglas de validación (por defecto ``REGLAS``).
	:param version: versión del esquema actual.
	:param migraciones: funciones de migración por versión de origen.
	"""

	def __init__(
		self,
		ruta: Path | str | None = None,
		por_defecto: dict[str, dict[str, Any]] | None = None,
		reglas: dict[str, Regla] | None = None,
		version: int | None = None,
		migraciones: dict[int, Callable[[dict], None]] | None = None,
	) -> None:
		self.ruta = Path(ruta) if ruta is not None else ruta_por_defecto()
		self._por_defecto = copy.deepcopy(VALORES_POR_DEFECTO if por_defecto is None else por_defecto)
		self._reglas = REGLAS if reglas is None else reglas
		# Se lee al crear (no al definir la función) para que una migración nueva cuente siempre.
		self._version = VERSION_ESQUEMA if version is None else version
		self._migraciones = MIGRACIONES if migraciones is None else migraciones
		# Datos: RLock porque un suscriptor puede volver a leer la configuración.
		self._candado = threading.RLock()
		# Disco: separado del de datos para que obtener()/establecer() no esperen al fsync.
		self._candado_disco = threading.Lock()
		self._datos: dict[str, Any] = {}
		self._suscriptores: list[_Suscriptor] = []
		self._profundidad_lote = 0
		self._cambios_lote: list[tuple[str, Any, Any]] = []
		self._pendiente_lote = False
		self._temporizador: threading.Timer | None = None
		# No se sobrescribe un archivo que no se pudo LEER (permisos, disco): se
		# perdería la configuración real del usuario.
		self._guardado_bloqueado = False
		#: True si no existía archivo (primer arranque): útil para autodetectar idioma.
		self.primer_arranque = False
		#: Texto con lo que se recuperó al cargar (None si todo fue bien).
		self.recuperacion: str | None = None
		self.cargar()

	# ── Carga ────────────────────────────────────────────────────────────────

	def _leer_json(self, ruta: Path) -> dict:
		"""Lee y decodifica ``ruta``. Lanza ``ValueError`` si no es un objeto JSON."""
		texto = ruta.read_text(encoding="utf-8")
		datos = json.loads(texto)
		if not isinstance(datos, dict):
			raise ValueError("el archivo no contiene un objeto JSON")
		return datos

	def _apartar_corrupto(self) -> Path | None:
		"""Copia el archivo dañado a ``settings.json.corrupto-FECHA`` (se conserva)."""
		marca = datetime.now().strftime("%Y%m%d_%H%M%S")
		destino = self.ruta.with_name(f"{self.ruta.name}.corrupto-{marca}")
		try:
			shutil.copy2(self.ruta, destino)
			return destino
		except OSError:
			log.error("No se pudo apartar la configuración dañada %s", self.ruta, exc_info=True)
			return None

	def cargar(self) -> None:
		"""Carga el archivo, lo migra, lo completa y lo valida.

		Nunca lanza por un archivo dañado: la aplicación debe poder arrancar.
		"""
		with self._candado:
			self.recuperacion = None
			self._guardado_bloqueado = False
			leidos: dict | None = None
			reescribir = False
			if not self.ruta.exists():
				log.info("Sin archivo de configuración; se usan los valores por defecto (%s)", self.ruta)
				self.primer_arranque = True
				# Una configuración nueva ya nace en el esquema actual: no hay nada que migrar
				# (antes se anunciaba «migrada de la versión 1 a la 2» en una instalación nueva).
				leidos = {CLAVE_VERSION: self._version}
				reescribir = True
			else:
				try:
					leidos = self._leer_json(self.ruta)
				except (ValueError, UnicodeDecodeError) as error:
					apartado = self._apartar_corrupto()
					log.error("Configuración dañada (%s); copia apartada en %s", error, apartado)
					leidos = self._leer_respaldo()
					if leidos is not None:
						self.recuperacion = "La configuración estaba dañada y se ha recuperado la copia anterior."
					else:
						leidos = {}
						self.recuperacion = (
							"La configuración estaba dañada y se han restablecido los valores de fábrica."
						)
					reescribir = True
				except OSError:
					log.error("No se pudo leer la configuración %s; no se sobrescribirá", self.ruta, exc_info=True)
					self._guardado_bloqueado = True
					self.recuperacion = "No se pudo leer la configuración; se usan valores de fábrica sin guardar."
					leidos = {}

			original = copy.deepcopy(leidos)
			reescribir |= self._migrar(leidos)
			datos = copy.deepcopy(self._por_defecto)
			_fusionar(datos, leidos)
			reescribir |= self._sanear(datos)
			datos[CLAVE_VERSION] = max(self._version, int(leidos.get(CLAVE_VERSION, 0) or 0))
			self._datos = datos
			# Si faltaban claves nuevas o se migró/saneó algo, se deja el archivo al día.
			if reescribir or original != datos:
				self.guardar()

	def _leer_respaldo(self) -> dict | None:
		"""Intenta ``settings.json.bak`` (último guardado correcto)."""
		respaldo = self.ruta.with_name(self.ruta.name + ".bak")
		if not respaldo.is_file():
			return None
		try:
			datos = self._leer_json(respaldo)
			log.warning("Configuración recuperada desde %s", respaldo.name)
			return datos
		except (OSError, ValueError, UnicodeDecodeError):
			log.error("La copia %s tampoco es válida", respaldo.name, exc_info=True)
			return None

	def _migrar(self, datos: dict) -> bool:
		"""Aplica las migraciones pendientes. Devuelve ``True`` si cambió algo."""
		try:
			actual = int(datos.get(CLAVE_VERSION, 1) or 1)
		except (TypeError, ValueError):
			actual = 1
		if actual > self._version:
			# Archivo escrito por una versión MÁS NUEVA: no se toca su estructura.
			log.warning(
				"La configuración es de la versión de esquema %d y esta aplicación usa la %d; "
				"se conservan las claves desconocidas.", actual, self._version,
			)
			return False
		cambiado = False
		for version in range(actual, self._version):
			migracion = self._migraciones.get(version)
			if migracion is None:
				continue
			try:
				migracion(datos)
				log.info("Configuración migrada de la versión %d a la %d", version, version + 1)
				cambiado = True
			except Exception:
				# Una migración rota no debe impedir arrancar: se registra y se sigue
				# con lo que haya; el saneado posterior repone valores por defecto.
				log.exception("Falló la migración de configuración %d → %d", version, version + 1)
		datos[CLAVE_VERSION] = self._version
		return cambiado or actual != self._version

	def _sanear(self, datos: dict) -> bool:
		"""Sustituye por su valor por defecto cada valor de tipo o rango inválido."""
		cambiado = False
		for seccion, claves in self._por_defecto.items():
			if not isinstance(datos.get(seccion), dict):
				log.warning("Sección «%s» inválida en la configuración; se restablece", seccion)
				datos[seccion] = copy.deepcopy(claves)
				cambiado = True
				continue
			for nombre, defecto in claves.items():
				clave = f"{seccion}.{nombre}"
				try:
					validar_valor(clave, datos[seccion].get(nombre), self._reglas, self._por_defecto)
				except ErrorValidacion as error:
					log.warning("Valor no válido en la configuración (%s); se usa el de fábrica", error)
					datos[seccion][nombre] = copy.deepcopy(defecto)
					cambiado = True
		return cambiado

	# ── Lectura y escritura de valores ───────────────────────────────────────

	def obtener(self, clave: str, por_defecto: Any = _SIN_VALOR) -> Any:
		"""Devuelve el valor de «seccion.clave».

		Devuelve una COPIA: modificar una lista devuelta no altera la
		configuración sin pasar por ``establecer`` (ni se salta los avisos).

		:raises KeyError: si la clave no existe y no se da ``por_defecto``.
		"""
		with self._candado:
			actual: Any = self._datos
			for parte in clave.split("."):
				if not isinstance(actual, dict) or parte not in actual:
					if por_defecto is _SIN_VALOR:
						raise KeyError(clave)
					return por_defecto
				actual = actual[parte]
			return copy.deepcopy(actual)

	def valor_por_defecto(self, clave: str) -> Any:
		"""Valor de fábrica de «seccion.clave» (``KeyError`` si no existe)."""
		seccion, _, nombre = clave.partition(".")
		return copy.deepcopy(self._por_defecto[seccion][nombre])

	def claves(self) -> list[str]:
		"""Todas las claves «seccion.clave» conocidas (las de fábrica)."""
		return [f"{s}.{c}" for s, claves in self._por_defecto.items() for c in claves]

	def regla(self, clave: str) -> Regla | None:
		"""Regla de validación de la clave (``None`` si solo se comprueba el tipo)."""
		return self._reglas.get(clave)

	def validar(self, clave: str, valor: Any) -> None:
		"""Lanza ``ErrorValidacion`` si ``valor`` no sirve para ``clave`` (no cambia nada)."""
		validar_valor(clave, valor, self._reglas, self._por_defecto)

	def establecer(self, clave: str, valor: Any, *, guardar: bool = True) -> bool:
		"""Cambia «seccion.clave», guarda (si ``guardar``) y avisa a los suscriptores.

		:return: ``True`` si el valor cambió.
		:raises ErrorValidacion: si el valor no cumple su tipo o su regla.
		"""
		return self.establecer_varias({clave: valor}, guardar=guardar)

	def establecer_varias(self, cambios: dict[str, Any], *, guardar: bool = True) -> bool:
		"""Cambia varias claves con UN solo guardado. Valida todas antes de tocar nada."""
		for clave, valor in cambios.items():
			validar_valor(clave, valor, self._reglas, self._por_defecto)
		avisos: list[tuple[str, Any, Any]] = []
		with self._candado:
			for clave, valor in cambios.items():
				seccion, punto, nombre = clave.partition(".")
				if not punto or not seccion or not nombre:
					raise KeyError(f"Clave mal formada: «{clave}» (se espera «seccion.clave»)")
				contenedor = self._datos.setdefault(seccion, {})
				anterior = copy.deepcopy(contenedor.get(nombre, None))
				if nombre in contenedor and contenedor[nombre] == valor and type(contenedor[nombre]) is type(valor):
					continue
				contenedor[nombre] = copy.deepcopy(valor)
				avisos.append((clave, anterior, copy.deepcopy(valor)))
			if not avisos:
				return False
			if self._profundidad_lote > 0:
				self._cambios_lote.extend(avisos)
				self._pendiente_lote = self._pendiente_lote or guardar
				return True
		if guardar:
			self.guardar()
		self._notificar(avisos)
		return True

	def establecer_diferido(self, clave: str, valor: Any, retraso: float = 0.8) -> bool:
		"""Como ``establecer``, pero agrupa el guardado ``retraso`` segundos.

		Para controles que cambian muchas veces por segundo (volumen, velocidad):
		cada pulsación de flecha no debe escribir el archivo con ``fsync`` en el
		hilo de la interfaz. Llama a ``guardar_pendiente()`` al cerrar.
		"""
		cambiado = self.establecer(clave, valor, guardar=False)
		if cambiado:
			with self._candado:
				if self._temporizador is not None:
					self._temporizador.cancel()
				self._temporizador = threading.Timer(max(0.05, retraso), self._al_vencer_temporizador)
				self._temporizador.daemon = True
				self._temporizador.name = "config-guardado-diferido"
				self._temporizador.start()
		return cambiado

	def _al_vencer_temporizador(self) -> None:
		with self._candado:
			self._temporizador = None
		try:
			self.guardar()
		except Exception:
			# En un hilo de temporizador nadie recogería la excepción: se registra.
			log.exception("Falló el guardado diferido de la configuración")

	def guardar_pendiente(self) -> None:
		"""Guarda YA si hay un guardado diferido en espera (al cerrar la aplicación)."""
		with self._candado:
			temporizador, self._temporizador = self._temporizador, None
		if temporizador is not None:
			temporizador.cancel()
			self.guardar()

	@contextmanager
	def lote(self) -> Iterator[Configuracion]:
		"""Agrupa varios ``establecer`` en un solo guardado y un solo reparto de avisos.

		Si el bloque lanza una excepción, lo ya cambiado se queda en memoria y se
		guarda igualmente (los cambios eran válidos uno a uno).
		"""
		with self._candado:
			self._profundidad_lote += 1
		try:
			yield self
		finally:
			with self._candado:
				self._profundidad_lote -= 1
				terminado = self._profundidad_lote == 0
				avisos, guardar = [], False
				if terminado:
					avisos, self._cambios_lote = self._cambios_lote, []
					guardar, self._pendiente_lote = self._pendiente_lote, False
			if terminado:
				if guardar:
					self.guardar()
				self._notificar(avisos)

	def restablecer(self, seccion: str | None = None, *, guardar: bool = True) -> None:
		"""Vuelve a los valores de fábrica (todo o una sección) y avisa."""
		with self.lote():
			secciones = [seccion] if seccion else list(self._por_defecto)
			cambios = {
				f"{s}.{c}": copy.deepcopy(v) for s in secciones for c, v in self._por_defecto[s].items()
			}
			self.establecer_varias(cambios, guardar=guardar)
		log.info("Configuración restablecida a valores de fábrica: %s", seccion or "todas las secciones")

	# ── Guardado ─────────────────────────────────────────────────────────────

	def guardar(self) -> None:
		"""Escribe el archivo de forma atómica y deja una copia ``.bak`` del anterior.

		:raises ErrorConfiguracion: si no se pudo escribir (disco lleno, permisos).
		"""
		with self._candado:
			if self._guardado_bloqueado:
				log.warning("Guardado omitido: el archivo original no se pudo leer y no se sobrescribe")
				return
			texto = json.dumps(self._datos, ensure_ascii=False, indent=2, sort_keys=False)
		with self._candado_disco:
			carpeta = self.ruta.parent
			# Temporal ÚNICO (proceso + hilo) en la MISMA carpeta: os.replace solo es
			# atómico dentro del mismo volumen, y dos guardados no comparten temporal.
			temporal = carpeta / f"{self.ruta.name}.{os.getpid()}-{threading.get_ident()}.tmp"
			try:
				carpeta.mkdir(parents=True, exist_ok=True)
				with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
					archivo.write(texto)
					archivo.flush()
					os.fsync(archivo.fileno())
				if self.ruta.exists():
					try:
						shutil.copy2(self.ruta, self.ruta.with_name(self.ruta.name + ".bak"))
					except OSError:
						# Sin .bak se pierde una red de seguridad, no el guardado.
						log.warning("No se pudo actualizar la copia .bak de la configuración", exc_info=True)
				_reemplazar(temporal, self.ruta)
				log.debug("Configuración guardada en %s", self.ruta)
			except OSError as error:
				try:
					temporal.unlink(missing_ok=True)
				except OSError:
					log.debug("No se pudo borrar el temporal %s", temporal, exc_info=True)
				log.error("No se pudo guardar la configuración en %s", self.ruta, exc_info=True)
				raise ErrorConfiguracion(f"No se pudo guardar la configuración: {error}") from error

	# ── Suscriptores ─────────────────────────────────────────────────────────

	def suscribir(self, funcion: Callable[[str, Any, Any], None], prefijo: str = "") -> Callable[[], None]:
		"""Avisa a ``funcion(clave, anterior, nuevo)`` de cada cambio.

		El aviso llega en el hilo que hizo el cambio. Si ``funcion`` toca
		controles wx, debe pasar por ``wx.CallAfter``.

		:param prefijo: solo claves que empiecen así (``"apariencia."``).
		:return: función que cancela la suscripción.
		"""
		suscriptor = _Suscriptor(funcion, prefijo)
		with self._candado:
			self._suscriptores.append(suscriptor)

		def cancelar() -> None:
			with self._candado:
				if suscriptor in self._suscriptores:
					self._suscriptores.remove(suscriptor)

		return cancelar

	def _notificar(self, avisos: list[tuple[str, Any, Any]]) -> None:
		"""Reparte los avisos FUERA del candado (un suscriptor lento no bloquea a nadie)."""
		if not avisos:
			return
		with self._candado:
			vivos = [s for s in self._suscriptores if s.funcion() is not None]
			self._suscriptores = vivos
			suscriptores = list(vivos)
		for clave, anterior, nuevo in avisos:
			for suscriptor in suscriptores:
				if not clave.startswith(suscriptor.prefijo):
					continue
				funcion = suscriptor.funcion()
				if funcion is None:
					continue
				try:
					funcion(clave, anterior, nuevo)
				except Exception:
					# Un suscriptor roto no debe impedir que los demás se enteren.
					log.exception("Falló un suscriptor de la configuración al cambiar «%s»", clave)


# ── Instancia compartida ─────────────────────────────────────────────────────

_instancia: Configuracion | None = None
_candado_instancia = threading.Lock()


def obtener_configuracion() -> Configuracion:
	"""Instancia única, creada la primera vez que se pide (no al importar).

	Crearla al importar escribiría en ``data`` durante las pruebas o al
	importar el módulo desde herramientas.
	"""
	global _instancia
	with _candado_instancia:
		if _instancia is None:
			_instancia = Configuracion()
		return _instancia
