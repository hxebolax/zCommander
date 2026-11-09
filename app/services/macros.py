# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Macros: secuencias de órdenes del catálogo, grabables y editables (diseño 2.0, 10.1). Sin wx.

Por qué así:

- Una macro es una LISTA DE ÓRDENES con su argumento (nunca teclas): sigue
  valiendo aunque la persona cambie de esquema de teclas o de idioma.
- Se guardan en ``data/config/macros.json`` con ``almacen_json`` (escritura
  atómica y copia ``.bak``). Un ``.zcmacro`` es el JSON de UNA macro.
- El grabador (``Grabador``) lo llama la ventana por llamada directa y ANTES
  del manejador de cada orden (10.1); los diálogos de las órdenes con
  argumento pasan su valor final con ``anotar_argumento``.
- El ejecutor (``EjecutorMacros``) nunca bloquea el hilo de la interfaz: cada
  paso empieza cuando se resuelve el futuro del anterior, cuando termina la
  operación que lanzó (si ``esperar``) y cuando el panel ha terminado de leer
  la carpeta a la que fue. Todo lo que necesita de la ventana le llega por el
  protocolo ``AnfitrionMacros`` (lo implementa ``personalizar_pe``).
"""

from __future__ import annotations

import builtins
import copy
import json
import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.core import almacen_json
from app.services.macros_argumentos import ARGUMENTOS, ESPERAN_OPERACION, PASOS_ESPECIALES, argumento_de

log = logging.getLogger(__name__)

ARCHIVO = "macros.json"
EXTENSION = ".zcmacro"
VERSION = 1
POR_DEFECTO: dict[str, Any] = {"version": VERSION, "macros": []}
#: Profundidad máxima de macros dentro de macros (evita bucles «A llama a B que llama a A»).
PROFUNDIDAD_MAXIMA = 5
#: Órdenes tras las que se espera a que el panel termine de leer su carpeta.
NAVEGACION = frozenset({
	"ir_a_carpeta", "subir", "entrar", "raiz", "carpeta_personal", "atras", "adelante", "pestana_nueva",
	"espacios_trabajo", "favoritos", "historial_carpetas", "volver_a_leer", "unidad_izquierda", "unidad_derecha",
})
#: Pasos que ejecutan programas u órdenes: al importar se ofrecen SIN marcar (10.1, 10.2).
EJECUTAN = frozenset({"ejecutar_linea", "menu_usuario", "ejecutar_en_consola"})
ESPERA_LECTURA_S = 30.0
#: Tras una orden de navegación, cuánto se espera como mucho a que el panel EMPIECE a cambiar
#: (la ruta se resuelve en un hilo antes de leer la carpeta: «no está leyendo» no basta).
ESPERA_CAMBIO_S = 2.0


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorMacro(ValueError):
	"""Una macro o un ``.zcmacro`` no válidos (mensaje en español)."""


# ── Modelo ──────────────────────────────────────────────────────────────────


@dataclass
class Paso:
	"""Un paso: id de orden (o ``paso:decir``...), su argumento y si espera a su operación."""

	orden: str
	argumento: Any = None
	esperar: bool | None = None

	def espera(self) -> bool:
		return self.esperar if self.esperar is not None else self.orden in ESPERAN_OPERACION

	def como_dict(self) -> dict[str, Any]:
		datos: dict[str, Any] = {"orden": self.orden}
		if self.argumento is not None:
			datos["argumento"] = copy.deepcopy(self.argumento)
		if self.esperar is not None:
			datos["esperar"] = bool(self.esperar)
		return datos

	@classmethod
	def desde_dict(cls, datos: Any) -> Paso:
		if not isinstance(datos, dict) or not isinstance(datos.get("orden"), str) or not datos["orden"].strip():
			raise ErrorMacro(_("Un paso de la macro no tiene orden"))
		esperar = datos.get("esperar")
		return cls(datos["orden"].strip(), copy.deepcopy(datos.get("argumento")), bool(esperar) if esperar is not None else None)


@dataclass
class Macro:
	nombre: str
	tecla: str = ""
	menu: bool = True
	paleta: bool = True
	pasos: list[Paso] = field(default_factory=list)

	def como_dict(self) -> dict[str, Any]:
		return {"nombre": self.nombre, "tecla": self.tecla, "menu": self.menu, "paleta": self.paleta,
			"pasos": [p.como_dict() for p in self.pasos]}

	@classmethod
	def desde_dict(cls, datos: Any) -> Macro:
		if not isinstance(datos, dict):
			raise ErrorMacro(_("La macro no tiene el formato esperado"))
		nombre = validar_nombre(str(datos.get("nombre", "")))
		pasos = datos.get("pasos", [])
		if not isinstance(pasos, list):
			raise ErrorMacro(_("Los pasos de la macro «{n}» no son una lista").format(n=nombre))
		return cls(nombre, str(datos.get("tecla", "") or ""), bool(datos.get("menu", True)), bool(datos.get("paleta", True)),
			[Paso.desde_dict(p) for p in pasos])


def validar_nombre(nombre: str) -> str:
	"""Nombre limpio de una macro, o ``ErrorMacro``: sin «:» (va en el id ``macro:<nombre>``) ni vacío."""
	limpio = " ".join(nombre.split())
	if not limpio:
		raise ErrorMacro(_("La macro necesita un nombre"))
	if ":" in limpio or len(limpio) > 80:
		raise ErrorMacro(_("El nombre de una macro no puede llevar dos puntos ni pasar de 80 caracteres"))
	return limpio


# ── Archivo ─────────────────────────────────────────────────────────────────


def cargar(carpeta: Path | None = None) -> list[Macro]:
	"""Macros guardadas; las dañadas se saltan (y se registra)."""
	datos = almacen_json.leer(ARCHIVO, POR_DEFECTO, carpeta)
	resultado: list[Macro] = []
	vistos: set[str] = set()
	for elemento in datos.get("macros", []) if isinstance(datos, dict) else []:
		try:
			macro = Macro.desde_dict(elemento)
		except ErrorMacro as error:
			log.warning("Macro descartada de %s: %s", ARCHIVO, error)
			continue
		if macro.nombre.casefold() in vistos:
			log.warning("Macro repetida descartada: %s", macro.nombre)
			continue
		vistos.add(macro.nombre.casefold())
		resultado.append(macro)
	return resultado


def guardar(macros: Sequence[Macro], carpeta: Path | None = None) -> None:
	almacen_json.escribir(ARCHIVO, {"version": VERSION, "macros": [m.como_dict() for m in macros]}, carpeta)


def buscar(macros: Sequence[Macro], nombre: str) -> Macro | None:
	clave = nombre.strip().casefold()
	return next((m for m in macros if m.nombre.casefold() == clave), None)


def nombre_libre(macros: Sequence[Macro], base: str) -> str:
	"""``base`` o ``base (2)``, ``base (3)``... el primero que no esté usado."""
	if buscar(macros, base) is None:
		return base
	n = 2
	while buscar(macros, f"{base} ({n})") is not None:
		n += 1
	return f"{base} ({n})"


def exportar(macro: Macro, ruta: Path) -> None:
	datos = {"version": VERSION, "macro": macro.como_dict()}
	Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def leer_archivo(ruta: Path) -> Macro:
	"""Lee un ``.zcmacro`` (sin aplicarlo); ``ErrorMacro`` si no es válido."""
	try:
		texto = Path(ruta).read_text(encoding="utf-8-sig")
		datos = json.loads(texto)
	except (OSError, ValueError) as error:
		raise ErrorMacro(_("No se pudo leer la macro: {e}").format(e=error)) from error
	if not isinstance(datos, dict) or int(datos.get("version", 0) or 0) > VERSION:
		raise ErrorMacro(_("El archivo no es una macro de esta versión de zCommander"))
	return Macro.desde_dict(datos.get("macro", datos))


# ── Textos y seguridad ──────────────────────────────────────────────────────


def texto_argumento(argumento: Any) -> str:
	if argumento is None:
		return ""
	if isinstance(argumento, dict):
		return ", ".join(f"{k}: {v}" for k, v in argumento.items())
	return str(argumento)


def texto_paso(paso: Paso, etiqueta_de: Callable[[str], str]) -> str:
	"""Texto completo de un paso («Ejecutar en la línea de órdenes: del /s /q %P»)."""
	if paso.orden == "paso:decir":
		nombre = _("Decir")
	elif paso.orden == "paso:esperar":
		nombre = _("Esperar (milisegundos)")
	elif paso.orden == "paso:sonar":
		nombre = _("Sonido")
	elif paso.orden.startswith("macro:"):
		nombre = _("Macro {n}").format(n=paso.orden[6:])
	else:
		nombre = etiqueta_de(paso.orden)
	argumento = texto_argumento(paso.argumento)
	return f"{nombre}: {argumento}" if argumento else nombre


def ejecuta_programas(paso: Paso, permisos_de: Callable[[str], Sequence[str]] | None = None) -> bool:
	"""Verdadero si el paso ejecuta programas u órdenes (se importa sin marcar)."""
	if paso.orden in EJECUTAN or paso.orden.startswith("macro:"):
		return True
	if ":" in paso.orden and not paso.orden.startswith("paso:") and permisos_de is not None:
		return "ejecutar_programas" in tuple(permisos_de(paso.orden.split(":", 1)[0]))
	return False


def sin_pasos(macro: Macro, quitar: Sequence[int]) -> Macro:
	"""Copia de la macro sin los pasos de esos índices (los no marcados al importar)."""
	quitados = set(quitar)
	return Macro(macro.nombre, macro.tecla, macro.menu, macro.paleta, [p for i, p in enumerate(macro.pasos) if i not in quitados])


def argumento_valido(orden: str, argumento: Any) -> Any:
	"""Normaliza un argumento escrito a mano según la tabla ``ARGUMENTOS`` (``ErrorMacro`` si no vale)."""
	tipo = argumento_de(orden)
	if tipo is None:
		if orden in PASOS_ESPECIALES:
			return argumento
		return None
	if argumento in (None, ""):
		return None
	if tipo.tipo == "json":
		if isinstance(argumento, str):
			try:
				argumento = json.loads(argumento)
			except ValueError as error:
				raise ErrorMacro(_("El argumento debe ser un objeto JSON, por ejemplo {{\"destino\": \"E:\\\\Copia\"}}")) from error
		if not isinstance(argumento, dict):
			raise ErrorMacro(_("El argumento debe ser un objeto JSON"))
		desconocidos = [k for k in argumento if tipo.campos and k not in tipo.campos]
		if desconocidos:
			raise ErrorMacro(_("Campos no admitidos: {c}. Admitidos: {a}").format(c=", ".join(desconocidos), a=", ".join(tipo.campos)))
		return argumento
	if orden == "paso:esperar":
		try:
			return max(0, int(str(argumento)))
		except ValueError as error:
			raise ErrorMacro(_("Escriba los milisegundos con cifras")) from error
	return str(argumento)


# ── Grabador ────────────────────────────────────────────────────────────────


class Grabador:
	"""El grabador de 10.1 (protocolo ``servicios_nucleo.Grabador``).

	La ventana llama a ``anotar`` antes del manejador de cada orden grabable; el
	diálogo de la orden llama después a ``anotar_argumento`` con su valor final.
	Mientras corre una macro no se graba (sus pasos ya son de otra macro).
	"""

	def __init__(self, en_ejecucion: Callable[[], bool] = lambda: False) -> None:
		self.grabando = False
		self.pasos: list[Paso] = []
		self._en_ejecucion = en_ejecucion

	def empezar(self) -> None:
		self.pasos = []
		self.grabando = True

	def terminar(self) -> list[Paso]:
		self.grabando = False
		pasos, self.pasos = self.pasos, []
		return pasos

	def anotar(self, id_orden: str, argumento: Any) -> None:
		if not self.grabando or self._en_ejecucion():
			return
		self.pasos.append(Paso(id_orden, self._normalizar(id_orden, argumento)))

	def anotar_argumento(self, valor: Any) -> None:
		"""El valor final del diálogo de la última orden (solo si admite argumento)."""
		if not self.grabando or not self.pasos or self._en_ejecucion():
			return
		ultimo = self.pasos[-1]
		if argumento_de(ultimo.orden) is None or valor is None:
			return
		ultimo.argumento = self._normalizar(ultimo.orden, valor)

	@staticmethod
	def _normalizar(id_orden: str, argumento: Any) -> Any:
		tipo = ARGUMENTOS.get(id_orden)
		if argumento is None or tipo is None:
			return copy.deepcopy(argumento) if argumento_de(id_orden) is not None else None
		if tipo.tipo == "json" and isinstance(argumento, dict):
			datos = {k: v for k, v in argumento.items() if not tipo.campos or k in tipo.campos}
			if "sin_dialogo" in tipo.campos:
				# Lo grabado se reproduce tal cual: sin volver a preguntar lo que ya se contestó.
				datos.setdefault("sin_dialogo", True)
			return datos
		return str(argumento) if tipo.tipo != "json" else copy.deepcopy(argumento)


# ── Ejecutor ────────────────────────────────────────────────────────────────


class AnfitrionMacros(Protocol):
	"""Lo que el ejecutor necesita de la ventana (lo implementa ``personalizar_pe``)."""

	def ejecutar_orden_futuro(self, id_orden: str, argumento: Any = None) -> Future: ...
	def llamar_mas_tarde(self, ms: int, funcion: Callable[[], None]) -> None: ...
	def anunciar(self, texto: str, nivel: str, sonido: str = "") -> None: ...
	def sonar(self, evento: str) -> None: ...
	def obtener(self, clave: str) -> Any: ...
	def suscribir_operaciones(self, al_empezar: Callable[[Any], None], al_terminar: Callable[[Any], None]) -> Callable[[], None]: ...
	def leyendo(self) -> bool: ...
	def estado_paneles(self) -> Any: ...
	def etiqueta(self, id_orden: str) -> str: ...


@dataclass
class _Ejecucion:
	nombre: str
	pasos: list[Paso]
	indice: int = 0
	numero: int = 0
	total: int = 0
	operaciones: list[Any] = field(default_factory=list)
	esperando: Any = None
	paso_actual: Paso | None = None
	detenida: bool = False
	estado_antes: Any = None


class EjecutorMacros:
	"""Servicio ``macros`` (protocolo ``servicios_nucleo.ServicioMacros``): ejecuta, detiene y recuerda la última."""

	def __init__(self, anfitrion: AnfitrionMacros, fuente: Callable[[], Sequence[Macro]]) -> None:
		self._anfitrion = anfitrion
		self._fuente = fuente
		self._actual: _Ejecucion | None = None
		self._cancelar_suscripcion: Callable[[], None] | None = None
		self.ultima: str = ""
		#: Avisos de fin para las pruebas y para quien quiera saber el resultado: (nombre, ok).
		self.al_terminar: Callable[[str, bool], None] | None = None

	# Protocolo ServicioMacros ------------------------------------------------

	def en_curso(self) -> bool:
		return self._actual is not None

	def detener(self) -> bool:
		ejecucion = self._actual
		if ejecucion is None:
			return False
		ejecucion.detenida = True
		self._terminar(ejecucion, ok=False, aviso=_("Macro {n} detenida").format(n=ejecucion.nombre))
		return True

	def ejecutar(self, nombre: str) -> None:
		macro = buscar(list(self._fuente()), nombre)
		if macro is None:
			self._anfitrion.anunciar(_("No existe la macro «{n}»").format(n=nombre), "esencial", "aviso.error")
			return
		self.ejecutar_macro(macro)

	def ejecutar_macro(self, macro: Macro) -> None:
		"""Ejecuta una macro aunque no esté guardada («Probar» del editor)."""
		if self._actual is not None:
			self._anfitrion.anunciar(_("Ya hay una macro en curso; Escape la detiene"), "resultado")
			return
		try:
			pasos = self._expandir(macro, 0)
		except ErrorMacro as error:
			self._anfitrion.anunciar(str(error), "esencial", "aviso.error")
			return
		self.ultima = macro.nombre
		ejecucion = _Ejecucion(macro.nombre, pasos, total=len(pasos))
		self._actual = ejecucion
		self._cancelar_suscripcion = self._anfitrion.suscribir_operaciones(self._al_empezar_operacion, self._al_terminar_operacion)
		if not pasos:
			self._terminar(ejecucion, ok=True)
			return
		self._siguiente(ejecucion)

	# Interno -----------------------------------------------------------------

	def _expandir(self, macro: Macro, profundidad: int) -> list[Paso]:
		"""Pasos de la macro con las macros que llama ya desplegadas (hasta ``PROFUNDIDAD_MAXIMA``)."""
		if profundidad > PROFUNDIDAD_MAXIMA:
			raise ErrorMacro(_("La macro «{n}» se llama a sí misma demasiadas veces").format(n=macro.nombre))
		resultado: list[Paso] = []
		for paso in macro.pasos:
			if paso.orden.startswith("macro:"):
				otra = buscar(list(self._fuente()), paso.orden[6:])
				if otra is None:
					raise ErrorMacro(_("La macro «{n}» llama a «{o}», que no existe").format(n=macro.nombre, o=paso.orden[6:]))
				resultado.extend(self._expandir(otra, profundidad + 1))
			else:
				resultado.append(paso)
		return resultado

	def _siguiente(self, ejecucion: _Ejecucion) -> None:
		if ejecucion is not self._actual or ejecucion.detenida:
			return
		if ejecucion.indice >= len(ejecucion.pasos):
			self._terminar(ejecucion, ok=True)
			return
		paso = ejecucion.pasos[ejecucion.indice]
		ejecucion.indice += 1
		ejecucion.numero += 1
		ejecucion.paso_actual = paso
		ejecucion.operaciones = []
		etiqueta = texto_paso(paso, self._anfitrion.etiqueta)
		if self._anfitrion.obtener("macros.anunciar_pasos"):
			self._anfitrion.anunciar(_("Paso {i} de {t}: {p}").format(i=ejecucion.numero, t=ejecucion.total, p=etiqueta), "detalle",
				"macro.paso")
		if paso.orden.startswith("paso:"):
			self._paso_especial(ejecucion, paso)
			return
		ejecucion.estado_antes = self._anfitrion.estado_paneles() if paso.orden in NAVEGACION else None
		try:
			futuro = self._anfitrion.ejecutar_orden_futuro(paso.orden, paso.argumento)
		except Exception:  # noqa: BLE001 - una orden que lanza es un paso fallido, no un fallo de la macro
			log.exception("Falló el paso %s de la macro %s", paso.orden, ejecucion.nombre)
			self._fallo(ejecucion)
			return
		futuro.add_done_callback(lambda f: self._anfitrion.llamar_mas_tarde(0, lambda: self._tras_orden(ejecucion, paso, f)))

	def _paso_especial(self, ejecucion: _Ejecucion, paso: Paso) -> None:
		if paso.orden == "paso:decir":
			self._anfitrion.anunciar(str(paso.argumento or ""), "resultado")
		elif paso.orden == "paso:sonar" and paso.argumento:
			self._anfitrion.sonar(str(paso.argumento))
		elif paso.orden == "paso:esperar":
			try:
				ms = max(0, int(paso.argumento or 0))
			except (TypeError, ValueError):
				ms = 0
			self._anfitrion.llamar_mas_tarde(ms, lambda: self._despues(ejecucion))
			return
		else:
			log.warning("Paso especial desconocido: %s", paso.orden)
			self._fallo(ejecucion)
			return
		self._despues(ejecucion)

	def _tras_orden(self, ejecucion: _Ejecucion, paso: Paso, futuro: Future) -> None:
		if ejecucion is not self._actual or ejecucion.detenida:
			return
		try:
			ok = bool(futuro.result())
		except Exception:  # noqa: BLE001 - un futuro roto es un paso fallido
			log.debug("El futuro del paso %s falló", paso.orden, exc_info=True)
			ok = False
		if not ok:
			self._fallo(ejecucion)
			return
		pendientes = [o for o in ejecucion.operaciones if not _final(o)]
		if paso.espera() and pendientes:
			ejecucion.esperando = pendientes[0]
			return
		fallidas = [o for o in ejecucion.operaciones if _fallida(o)]
		if paso.espera() and fallidas:
			self._fallo(ejecucion)
			return
		self._esperar_lectura(ejecucion, paso, time.monotonic())

	def _esperar_lectura(self, ejecucion: _Ejecucion, paso: Paso, inicio: float) -> None:
		"""Tras ir a una carpeta, el paso siguiente espera a que el panel la haya leído."""
		if ejecucion is not self._actual or ejecucion.detenida:
			return
		if paso.orden in NAVEGACION:
			transcurrido = time.monotonic() - inicio
			sin_cambio = self._anfitrion.estado_paneles() == ejecucion.estado_antes and transcurrido < ESPERA_CAMBIO_S
			if (sin_cambio or self._anfitrion.leyendo()) and transcurrido < ESPERA_LECTURA_S:
				self._anfitrion.llamar_mas_tarde(50, lambda: self._esperar_lectura(ejecucion, paso, inicio))
				return
		self._despues(ejecucion)

	def _despues(self, ejecucion: _Ejecucion) -> None:
		pausa = int(self._anfitrion.obtener("macros.pausa_ms") or 0)
		if pausa > 0:
			self._anfitrion.llamar_mas_tarde(pausa, lambda: self._siguiente(ejecucion))
		else:
			self._siguiente(ejecucion)

	def _fallo(self, ejecucion: _Ejecucion) -> None:
		paso = ejecucion.paso_actual
		etiqueta = texto_paso(paso, self._anfitrion.etiqueta) if paso is not None else ""
		if self._anfitrion.obtener("macros.detener_en_error"):
			self._terminar(ejecucion, ok=False, aviso=_("La macro se detuvo en el paso {i}: {p}").format(i=ejecucion.numero, p=etiqueta))
			return
		self._anfitrion.anunciar(_("Falló el paso {i}: {p}").format(i=ejecucion.numero, p=etiqueta), "resultado", "aviso.error")
		self._despues(ejecucion)

	def _al_empezar_operacion(self, operacion: Any) -> None:
		ejecucion = self._actual
		paso = ejecucion.paso_actual if ejecucion is not None else None
		if paso is not None and getattr(operacion, "orden_origen", "") == paso.orden:
			ejecucion.operaciones.append(operacion)

	def _al_terminar_operacion(self, operacion: Any) -> None:
		ejecucion = self._actual
		if ejecucion is None or ejecucion.esperando is not operacion:
			return
		ejecucion.esperando = None
		if _fallida(operacion):
			self._fallo(ejecucion)
			return
		pendientes = [o for o in ejecucion.operaciones if not _final(o)]
		if pendientes:
			ejecucion.esperando = pendientes[0]
			return
		self._despues(ejecucion)

	def _terminar(self, ejecucion: _Ejecucion, ok: bool, aviso: str = "") -> None:
		if ejecucion is not self._actual:
			return
		self._actual = None
		if self._cancelar_suscripcion is not None:
			try:
				self._cancelar_suscripcion()
			except Exception:  # noqa: BLE001 - cancelar dos veces no importa
				log.debug("No se pudo cancelar la suscripción de la macro", exc_info=True)
			self._cancelar_suscripcion = None
		if ok:
			self._anfitrion.anunciar(_("Macro {n} terminada").format(n=ejecucion.nombre), "resultado", "macro.fin")
		elif aviso:
			self._anfitrion.anunciar(aviso, "esencial", "aviso.error")
		if self.al_terminar is not None:
			self.al_terminar(ejecucion.nombre, ok)


def _estado(operacion: Any) -> Any:
	return getattr(operacion, "estado", None)


def _final(operacion: Any) -> bool:
	return bool(getattr(_estado(operacion), "final", True))


def _fallida(operacion: Any) -> bool:
	valor = getattr(_estado(operacion), "value", "")
	return valor in ("fallida", "cancelada")
