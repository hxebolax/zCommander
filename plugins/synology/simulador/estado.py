# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Estado en memoria del NAS falso (diseño 2.0, 13.9; synology.md 7.6).

Se carga de ``datos/nas_ds220plus.json`` (datos ficticios coherentes con el
DS220+ real, marcados como ficticios) y se completa con lo que se genera: el
árbol de archivos de unas 200 entradas, unos 50 sucesos del registro y las
fechas relativas a «ahora». Nada se guarda en disco: al parar el simulador, se
pierde (es lo que promete el «NAS de demostración»).
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import secrets
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .comun import ErrorSim

CARPETA_DATOS = Path(__file__).resolve().parent / "datos"
BLOQUE = 64 * 1024
#: Por encima de este tamaño, el MD5 de un archivo ficticio no se calcula leyendo su contenido generado.
MD5_REAL_HASTA = 64 * 1024 * 1024


def cargar_json(nombre: str) -> dict[str, Any]:
	with (CARPETA_DATOS / nombre).open(encoding="utf-8") as archivo:
		return json.load(archivo)


@dataclass
class Nodo:
	"""Archivo o carpeta del árbol de File Station."""

	nombre: str
	es_carpeta: bool
	tamano: int = 0
	modificado: float = 0.0
	creado: float = 0.0
	contenido: bytes | None = None
	propietario: str = "pepe"
	hijos: dict[str, Nodo] = field(default_factory=dict)

	def clonar(self) -> Nodo:
		return copy.deepcopy(self)


@dataclass
class TareaFondo:
	"""Tarea en segundo plano de File Station: avanza con el tiempo (13.9: un 10 % por segundo de fábrica)."""

	taskid: str
	api: str
	params: dict[str, Any]
	inicio: float
	ritmo: float
	total: int = 0
	aplicar: bool = True
	al_terminar: Callable[[], dict[str, Any] | None] | None = None
	resultado: dict[str, Any] = field(default_factory=dict)
	error: int = 0
	detenida: bool = False
	terminada: bool = False
	usuario: str = ""

	def progreso(self, ahora: float | None = None) -> float:
		if self.terminada:
			return 1.0
		ahora = time.monotonic() if ahora is None else ahora
		return max(0.0, min(1.0, (ahora - self.inicio) * self.ritmo))

	def avanzar(self) -> None:
		"""Cuando llega al 100 %, aplica su efecto una sola vez (en el modo ``escritura``)."""
		if self.terminada or self.detenida or self.progreso() < 1.0:
			return
		self.terminada = True
		if self.aplicar and self.al_terminar is not None:
			try:
				extra = self.al_terminar()
			except ErrorSim as error:
				self.error = error.codigo
				return
			if extra:
				self.resultado.update(extra)


@dataclass
class SesionSim:
	sid: str
	synotoken: str
	usuario: str
	administrador: bool
	ip: str
	peticiones: int = 0


class EstadoNAS:
	"""Todo lo que el NAS falso sabe. Los manejadores lo leen y lo cambian con ``candado`` tomado."""

	def __init__(self, datos: dict[str, Any] | str | Path | None = None, *, semilla: int = 2026) -> None:
		if datos is None:
			datos = cargar_json("nas_ds220plus.json")
		elif not isinstance(datos, dict):
			with Path(datos).open(encoding="utf-8") as archivo:
				datos = json.load(archivo)
		self.datos: dict[str, Any] = copy.deepcopy(datos)
		self.catalogo: dict[str, Any] = cargar_json("api_info.json")["data"]
		self.cuentas: dict[str, Any] = cargar_json("credenciales_prueba.json")["cuentas"]
		self.candado = threading.RLock()
		self.azar = random.Random(semilla)
		self.arranque = time.time() - float(self.datos["sistema"].get("encendido_s", 0))
		self.sesiones: dict[str, SesionSim] = {}
		self.dispositivos: dict[str, str] = {}  # device_id → usuario
		self.fallos_login: dict[str, int] = {}
		self.tareas: dict[str, TareaFondo] = {}
		self.busquedas: dict[str, dict[str, Any]] = {}
		self.enlaces: dict[str, dict[str, Any]] = {}
		self.apagado = False
		self.reinicios = 0
		self.ritmo_tareas = 0.1
		self._secuencia = 0
		ahora = time.time()
		self.raiz = Nodo("", True, modificado=ahora, creado=ahora)
		self._construir_arbol(self.datos.get("arbol", {}), ahora)
		self.registros = self._generar_registros(ahora)

	# ── Utilidades ────────────────────────────────────────────────────────────

	def nuevo_id(self, prefijo: str = "FileStation_") -> str:
		self._secuencia += 1
		return f"{prefijo}{self._secuencia:04X}{secrets.token_hex(6).upper()}"

	def ahora(self) -> float:
		return time.time()

	def encendido_s(self) -> int:
		return int(time.time() - self.arranque)

	@property
	def sistema(self) -> dict[str, Any]:
		return self.datos["sistema"]

	# ── Árbol de archivos ─────────────────────────────────────────────────────

	def _construir_arbol(self, arbol: dict[str, Any], ahora: float) -> None:
		def poner(padre: Nodo, nombre: str, valor: Any, profundidad: int) -> None:
			fecha = ahora - self.azar.randint(3600, 400 * 86400)
			if isinstance(valor, dict):
				nodo = Nodo(nombre, True, modificado=fecha, creado=fecha - 86400)
				padre.hijos[nombre] = nodo
				for hijo, valor_hijo in valor.items():
					poner(nodo, hijo, valor_hijo, profundidad + 1)
			else:
				padre.hijos[nombre] = Nodo(nombre, False, int(valor), fecha, fecha - 3600)

		for nombre, valor in arbol.items():
			poner(self.raiz, nombre, valor, 0)
		# Lo generado: fotos y música con nombres realistas (para llegar a unas 200 entradas).
		fotos = self._asegurar_carpeta("/photo/2025/Vacaciones en Cádiz")
		for numero in range(1, 56):
			fecha = ahora - (120 - numero) * 86400
			fotos.hijos[f"IMG_20250712_{numero:04d}.jpg"] = Nodo(
				f"IMG_20250712_{numero:04d}.jpg", False, self.azar.randint(2_400_000, 5_800_000), fecha, fecha)
		cumple = self._asegurar_carpeta("/photo/2026/Cumpleaños de Lucía")
		for numero in range(1, 31):
			nombre = f"PXL_20260304_{numero:03d}.{'mp4' if numero % 7 == 0 else 'jpg'}"
			tamano = self.azar.randint(40_000_000, 90_000_000) if nombre.endswith("mp4") else self.azar.randint(1_800_000, 4_200_000)
			cumple.hijos[nombre] = Nodo(nombre, False, tamano, ahora - 250 * 86400, ahora - 250 * 86400)
		albumes = {
			"Mecano - Entre el cielo y el suelo": ["Hijo de la Luna", "Cruz de navajas", "Me cuesta tanto olvidarte",
				"Ay, qué pesado", "Barco a Venus", "La fuerza del destino"],
			"Paco de Lucía - Fuente y caudal": ["Entre dos aguas", "Solera", "Fuente y caudal", "Cepa andaluza", "Aires choqueros"],
			"Rosalía - Motomami": ["Saoko", "Candy", "La fama", "Bulerías", "Chicken teriyaki", "Hentai", "Bizcochito"],
			"Los Secretos - Algo prestado": ["Déjame", "Pero a tu lado", "Ojos de gata", "Agárrate a mí, María", "Sobre un vidrio mojado"],
			"Joaquín Sabina - 19 días y 500 noches": ["Ganas de...", "19 días y 500 noches", "Contigo", "Barbi superstar",
				"Una canción para la Magdalena"],
		}
		for album, canciones in albumes.items():
			carpeta = self._asegurar_carpeta(f"/Multimedia/Música/{album}")
			for posicion, cancion in enumerate(canciones, 1):
				nombre = f"{posicion:02d} - {cancion}.flac"
				carpeta.hijos[nombre] = Nodo(nombre, False, self.azar.randint(18_000_000, 42_000_000), ahora - 900 * 86400,
					ahora - 900 * 86400)
		casa = self._asegurar_carpeta("/Documentos/Casa")
		for numero, tema in enumerate(["Garantía lavadora", "Garantía frigorífico", "Escritura del piso", "Certificado energético",
				"Recibo IBI 2025", "Recibo IBI 2026", "Plano de la cocina", "Presupuesto del fontanero", "Seguro del hogar",
				"Comunidad de vecinos - acta de junio", "Comunidad de vecinos - acta de diciembre", "Instrucciones del termostato"], 1):
			nombre = f"{tema}.pdf"
			casa.hijos[nombre] = Nodo(nombre, False, self.azar.randint(80_000, 2_500_000), ahora - numero * 20 * 86400,
				ahora - numero * 20 * 86400)

	def _asegurar_carpeta(self, ruta: str) -> Nodo:
		nodo = self.raiz
		for parte in partes(ruta):
			if parte not in nodo.hijos:
				ahora = time.time()
				nodo.hijos[parte] = Nodo(parte, True, modificado=ahora, creado=ahora)
			nodo = nodo.hijos[parte]
		return nodo

	def contar_entradas(self) -> int:
		def contar(nodo: Nodo) -> int:
			return sum(1 + (contar(h) if h.es_carpeta else 0) for h in nodo.hijos.values())

		return contar(self.raiz)

	def nodo(self, ruta: str) -> Nodo:
		"""El nodo de ``ruta`` («/Documentos/notas.txt»). Lanza 408 si no existe."""
		nodo = self.raiz
		for parte in partes(ruta):
			if not nodo.es_carpeta or parte not in nodo.hijos:
				raise ErrorSim(408, [{"code": 408, "path": ruta}])
			nodo = nodo.hijos[parte]
		return nodo

	def existe(self, ruta: str) -> bool:
		try:
			self.nodo(ruta)
		except ErrorSim:
			return False
		return True

	def padre_de(self, ruta: str) -> tuple[Nodo, str]:
		trozos = partes(ruta)
		if not trozos:
			raise ErrorSim(400)
		padre = self.nodo("/" + "/".join(trozos[:-1])) if len(trozos) > 1 else self.raiz
		if not padre.es_carpeta:
			raise ErrorSim(408, [{"code": 408, "path": ruta}])
		return padre, trozos[-1]

	def es_compartida(self, nombre: str) -> dict[str, Any] | None:
		return next((c for c in self.datos["carpetas"] if c["name"] == nombre), None)

	def contenido(self, nodo: Nodo, ruta: str) -> Iterator[bytes]:
		"""Bytes de un archivo: los subidos tal cual; los ficticios, generados (sin guardarlos en memoria)."""
		if nodo.contenido is not None:
			for inicio in range(0, len(nodo.contenido), BLOQUE):
				yield nodo.contenido[inicio:inicio + BLOQUE]
			return
		patron = f"Contenido ficticio del NAS de demostración: {ruta}\n".encode()
		bloque = (patron * (BLOQUE // len(patron) + 1))[:BLOQUE]
		quedan = nodo.tamano
		while quedan > 0:
			parte = bloque[:min(BLOQUE, quedan)]
			quedan -= len(parte)
			yield parte

	def md5(self, nodo: Nodo, ruta: str) -> str:
		if nodo.contenido is None and nodo.tamano > MD5_REAL_HASTA:
			return hashlib.md5(f"{ruta}:{nodo.tamano}".encode(), usedforsecurity=False).hexdigest()
		suma = hashlib.md5(usedforsecurity=False)
		for parte in self.contenido(nodo, ruta):
			suma.update(parte)
		return suma.hexdigest()

	def tamano_total(self, nodo: Nodo) -> tuple[int, int, int]:
		"""(carpetas, archivos, bytes) bajo ``nodo``."""
		if not nodo.es_carpeta:
			return 0, 1, nodo.tamano
		carpetas = archivos = total = 0
		for hijo in nodo.hijos.values():
			if hijo.es_carpeta:
				carpetas += 1
			c, a, t = self.tamano_total(hijo)
			carpetas, archivos, total = carpetas + c, archivos + a, total + t
		return carpetas, archivos, total

	# ── Volumen ───────────────────────────────────────────────────────────────

	def volumen(self) -> dict[str, Any]:
		return self.datos["volumenes"][0]

	def espacio(self) -> tuple[int, int]:
		"""(libre, total) del volumen en bytes."""
		volumen = self.volumen()
		total, usado = int(volumen["total"]), int(volumen["usado"])
		return max(0, total - usado), total

	def sumar_uso(self, bytes_: int) -> None:
		volumen = self.volumen()
		volumen["usado"] = str(max(0, int(volumen["usado"]) + int(bytes_)))

	# ── Registros ─────────────────────────────────────────────────────────────

	def _generar_registros(self, ahora: float) -> list[dict[str, Any]]:
		plantillas = [
			("info", "Connection", "pepe", "El usuario [pepe] de [192.168.1.20] ha iniciado sesión en [DSM] con contraseña."),
			("info", "Connection", "pepe", "El usuario [pepe] de [192.168.1.20] ha accedido a la carpeta compartida [Documentos] por SMB."),
			("info", "Connection", "lectura", "El usuario [lectura] de [192.168.1.31] ha accedido a [Multimedia] por WebDAV."),
			("warn", "Connection", "admin", "El usuario [admin] de [203.0.113.7] no ha podido iniciar sesión en [DSM]: contraseña incorrecta."),
			("warn", "System", "SYSTEM", "La dirección [203.0.113.7] se ha bloqueado por demasiados intentos fallidos."),
			("info", "System", "SYSTEM", "La prueba S.M.A.R.T. rápida de [Unidad 1] ha terminado: estado normal."),
			("info", "System", "SYSTEM", "La prueba S.M.A.R.T. rápida de [Unidad 2] ha terminado: estado normal."),
			("info", "System", "SYSTEM", "Se ha vaciado la papelera de todas las carpetas compartidas."),
			("info", "System", "SYSTEM", "El paquete [Container Manager] se ha iniciado."),
			("warn", "System", "SYSTEM", "El contenedor [homeassistant] no supera la comprobación de salud."),
			("info", "System", "SYSTEM", "La configuración de DSM se ha copiado en la cuenta de Synology."),
			("info", "System", "pepe", "La tarea programada [Actualizar contenedores] ha terminado correctamente."),
			("err", "System", "SYSTEM", "La tarea programada [Copia rsync] se ha interrumpido."),
			("info", "System", "SYSTEM", "La IP externa ha cambiado a [203.0.113.25]; DDNS actualizado."),
		]
		registros = []
		for numero in range(50):
			nivel, tipo, quien, texto = plantillas[numero % len(plantillas)]
			momento = ahora - numero * 2700 - self.azar.randint(0, 900)
			registros.append({
				"time": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(momento)), "level": nivel, "logtype": tipo,
				"who": quien, "descr": texto, "orden": momento,
			})
		return registros

	def anotar_registro(self, nivel: str, texto: str, quien: str = "SYSTEM") -> None:
		momento = time.time()
		self.registros.insert(0, {"time": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(momento)), "level": nivel,
			"logtype": "System", "who": quien, "descr": texto, "orden": momento})


def partes(ruta: str) -> list[str]:
	return [p for p in str(ruta or "").replace("\\", "/").split("/") if p]


def normalizar(ruta: str) -> str:
	return "/" + "/".join(partes(ruta))
