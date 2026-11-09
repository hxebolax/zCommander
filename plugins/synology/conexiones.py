# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conexiones abiertas con los NAS y el «NAS de demostración» (diseño 2.0, 13.3 y 13.9).

Un único registro por sesión de zCommander: la ventana del NAS, el proveedor
``synology://`` y las órdenes comparten el mismo ``ClienteDSM`` de cada
servidor. Sin wx: lo que hay que preguntar llega por un objeto ``Preguntas``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.plugins import api

from . import errores
from .cliente import ClienteDSM, InfoNAS
from .servidores import ID_DEMOSTRACION, AlmacenServidores, ServidorNAS

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.conexiones")

#: Cuenta del NAS de demostración (inventada; está en ``simulador/datos/credenciales_prueba.json``).
CUENTA_DEMOSTRACION = ("demo", "demo")


@dataclass
class Conexion:
	servidor: ServidorNAS
	cliente: ClienteDSM
	info: InfoNAS
	simulador: Any = None

	@property
	def demostracion(self) -> bool:
		return self.simulador is not None

	@property
	def solo_lectura(self) -> bool:
		return self.cliente.solo_lectura

	def titulo(self) -> str:
		nombre = self.servidor.nombre
		if not self.solo_lectura:
			return _("CAMBIOS PERMITIDOS: NAS Synology: {n}").format(n=nombre)
		return _("NAS Synology: {n}").format(n=nombre)


class Conexiones:
	"""Registro de conexiones; seguro entre hilos."""

	def __init__(self, almacen: AlmacenServidores, secretos: Any = None, *, ajuste: Callable[[str, Any], Any] | None = None,
			sonar: Callable[[str], None] | None = None, carpeta_temporal: Path | Callable[[], Path] | None = None) -> None:
		self.almacen = almacen
		self._secretos = secretos
		self._ajuste = ajuste or (lambda _clave, defecto: defecto)
		self._sonar = sonar or (lambda _evento: None)
		self._carpeta_temporal = carpeta_temporal
		self._candado = threading.RLock()
		self._activas: dict[str, Conexion] = {}
		self._en_curso: dict[str, threading.Event] = {}
		self._oyentes: list[Callable[[str, str], None]] = []

	# ── Avisos a la interfaz ─────────────────────────────────────────────────

	def suscribir(self, funcion: Callable[[str, str], None]) -> Callable[[], None]:
		"""``funcion(id_servidor, suceso)`` con «conectado», «desconectado» o «modo» (desde cualquier hilo)."""
		self._oyentes.append(funcion)
		return lambda: self._oyentes.remove(funcion) if funcion in self._oyentes else None

	def _avisar(self, id_servidor: str, suceso: str) -> None:
		for funcion in list(self._oyentes):
			try:
				funcion(id_servidor, suceso)
			except Exception:  # noqa: BLE001 - un oyente roto no impide avisar a los demás
				log.warning("Falló un oyente de conexiones", exc_info=True)

	# ── Consulta ─────────────────────────────────────────────────────────────

	def activas(self) -> list[Conexion]:
		with self._candado:
			return list(self._activas.values())

	def obtener(self, id_servidor: str) -> Conexion | None:
		with self._candado:
			return self._activas.get(id_servidor)

	def servidor(self, id_servidor: str) -> ServidorNAS | None:
		conexion = self.obtener(id_servidor)
		if conexion is not None:
			return conexion.servidor
		return self.almacen.obtener(id_servidor)

	def unica(self) -> Conexion | None:
		activas = self.activas()
		return activas[0] if len(activas) == 1 else None

	# ── Conectar ─────────────────────────────────────────────────────────────

	def _nuevo_cliente(self, servidor: ServidorNAS, preguntas: Any, contrasena: str | None = None) -> ClienteDSM:
		return ClienteDSM(servidor, None if servidor.demostracion else self._secretos, preguntas,
			tiempo_conexion=int(self._ajuste("tiempo_conexion_s", 10)), tiempo_peticion=int(self._ajuste("tiempo_peticion_s", 30)),
			sonar=self._sonar, al_guardar_servidor=self.almacen.guardar,
			carpeta_temporal=self._carpeta_temporal() if callable(self._carpeta_temporal) else self._carpeta_temporal,
			registro_detallado=bool(self._ajuste("registro_detallado", False)), contrasena=contrasena)

	def conectar(self, servidor: ServidorNAS, preguntas: Any = None, cancelacion: Any = None, *, contrasena: str | None = None,
			simulador: Any = None) -> Conexion:
		"""[trabajo] Conecta (o devuelve la conexión que ya hay). Dos peticiones a la vez del mismo NAS esperan a la primera."""
		while True:
			with self._candado:
				existente = self._activas.get(servidor.id)
				if existente is not None:
					return existente
				espera = self._en_curso.get(servidor.id)
				if espera is None:
					self._en_curso[servidor.id] = threading.Event()
					break
			espera.wait(60)
		try:
			cliente = self._nuevo_cliente(replace(servidor), preguntas, contrasena)
			info = cliente.conectar(cancelacion)
			conexion = Conexion(cliente.servidor, cliente, info, simulador)
			with self._candado:
				self._activas[servidor.id] = conexion
		finally:
			with self._candado:
				evento = self._en_curso.pop(servidor.id, None)
			if evento is not None:
				evento.set()
		self._sonar("conectado")
		self._avisar(servidor.id, "conectado")
		return conexion

	def conectar_id(self, id_servidor: str, preguntas: Any = None, cancelacion: Any = None) -> Conexion:
		conexion = self.obtener(id_servidor)
		if conexion is not None:
			return conexion
		servidor = self.almacen.obtener(id_servidor)
		if servidor is None:
			raise api.NoEncontrado(_("No hay ningún NAS guardado con el nombre {i}.").format(i=id_servidor))
		return self.conectar(servidor, preguntas, cancelacion)

	def desconectar(self, id_servidor: str) -> bool:
		"""[trabajo] Cierra la sesión (``logout``) y, si es el de demostración, para el simulador."""
		with self._candado:
			conexion = self._activas.pop(id_servidor, None)
		if conexion is None:
			return False
		try:
			conexion.cliente.desconectar()
		finally:
			if conexion.simulador is not None:
				conexion.simulador.parar()
		self._sonar("desconectado")
		self._avisar(id_servidor, "desconectado")
		return True

	def desconectar_todas(self) -> None:
		for conexion in self.activas():
			try:
				self.desconectar(conexion.servidor.id)
			except Exception:  # noqa: BLE001 - al cerrar zCommander nada debe impedir cerrar el resto
				log.warning("No se pudo desconectar de %s", conexion.servidor.nombre, exc_info=True)

	def cambiar_modo(self, id_servidor: str, permitir: bool, persistente: bool = False) -> None:
		conexion = self.obtener(id_servidor)
		if conexion is None:
			raise errores.ErrorSesion(_("Ese NAS no está conectado."), 119)
		conexion.cliente.permitir_cambios(permitir, persistente)
		if permitir:
			self._sonar("cambios_permitidos")
		self._avisar(id_servidor, "modo")

	# ── NAS de demostración ──────────────────────────────────────────────────

	def demostracion(self, modo: str = "escritura", cancelacion: Any = None) -> Conexion:
		"""[trabajo] Arranca el simulador en 127.0.0.1 (HTTP, puerto libre) y conecta como «demo», en solo lectura (13.9)."""
		existente = self.obtener(ID_DEMOSTRACION)
		if existente is not None:
			return existente
		from .simulador import SimuladorDSM

		simulador = SimuladorDSM(puerto=0, modo=modo if modo in ("lectura", "simular", "escritura") else "escritura")
		simulador.iniciar()
		servidor = ServidorNAS(ID_DEMOSTRACION, _("NAS de demostración"), "127.0.0.1", simulador.puerto, https=False,
			usuario=CUENTA_DEMOSTRACION[0], solo_lectura=True, recordar_contrasena=False, demostracion=True)
		try:
			conexion = self.conectar(servidor, None, cancelacion, contrasena=CUENTA_DEMOSTRACION[1], simulador=simulador)
		except BaseException:
			simulador.parar()
			raise
		self._sonar("demostracion_iniciada")
		return conexion
