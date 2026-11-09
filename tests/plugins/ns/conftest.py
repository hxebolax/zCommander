# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Preparación de las pruebas del bloque NS (NAS Synology; diseño 2.0, 13.13 y 18.2).

SIEMPRE contra el simulador DSM local (127.0.0.1): nunca contra el NAS real ni
con credenciales reales. Cada simulador que se arranca aquí se para al acabar
la prueba, también si falla.
"""

from __future__ import annotations

import datetime
import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.plugins.api import pruebas

RAIZ = Path(__file__).resolve().parents[3]
CARPETA = RAIZ / "plugins" / "synology"
PAQUETE = "zcplugins.zc__synology"
_MODULOS: dict[str, Any] = {}


def modulos() -> SimpleNamespace:
	"""Importa el complemento como lo hace el cargador (paquete ``zcplugins.zc__synology``) y devuelve sus módulos."""
	if not _MODULOS:
		zc = pruebas.anfitrion_de_prueba(CARPETA)
		zc.activar()
		for nombre in ("areas", "busqueda", "catalogo", "cliente", "conexiones", "errores", "metodos_lectura", "operaciones", "preguntas",
				"proveedor", "servidores", "sesion", "ssh", "simulador", "simulador.servidor", "simulador.estado"):
			_MODULOS[nombre.replace(".", "_")] = importlib.import_module(f"{PAQUETE}.{nombre}")
		_MODULOS["complemento"] = zc.instancia
		_MODULOS["zc"] = zc
	return SimpleNamespace(**_MODULOS)


@pytest.fixture
def ns() -> SimpleNamespace:
	return modulos()


class SecretosFalsos:
	"""Almacén de secretos en memoria (en la aplicación es DPAPI)."""

	def __init__(self) -> None:
		self.datos: dict[str, str] = {}

	def obtener(self, nombre: str) -> str | None:
		return self.datos.get(nombre)

	def guardar(self, nombre: str, valor: str) -> None:
		self.datos[nombre] = valor

	def borrar(self, nombre: str) -> None:
		self.datos.pop(nombre, None)


class PreguntasFalsas:
	"""``Preguntas`` del cliente con respuestas preparadas; apunta lo que se le pregunta."""

	def __init__(self, credenciales: Any = None, codigos: list[Any] | None = None, huellas: list[str] | None = None,
			contrasena_dsm: str | None = None) -> None:
		self._credenciales = credenciales
		self._codigos = list(codigos or [])
		self._huellas = list(huellas or [])
		self._contrasena_dsm = contrasena_dsm
		self.preguntado: list[tuple[str, str]] = []

	def credenciales(self, servidor: Any, motivo: str) -> Any:
		self.preguntado.append(("credenciales", motivo))
		return self._credenciales

	def codigo(self, servidor: Any, mensaje: str) -> Any:
		self.preguntado.append(("codigo", mensaje))
		return self._codigos.pop(0) if self._codigos else None

	def huella(self, servidor: Any, huella: str, anterior: str) -> str:
		self.preguntado.append(("huella", anterior))
		return self._huellas.pop(0) if self._huellas else "cancelar"

	def contrasena_dsm(self, servidor: Any, motivo: str) -> str | None:
		self.preguntado.append(("contrasena_dsm", motivo))
		return self._contrasena_dsm


@pytest.fixture
def arrancar(ns):
	"""Fábrica de simuladores; todos se paran al terminar la prueba (ningún simulador queda vivo)."""
	vivos: list[Any] = []

	def crear(modo: str = "lectura", **opciones: Any) -> Any:
		opciones.setdefault("ritmo_tareas", 8.0)
		simulador = ns.simulador.SimuladorDSM(puerto=0, modo=modo, **opciones)
		simulador.iniciar()
		vivos.append(simulador)
		return simulador

	yield crear
	for simulador in vivos:
		simulador.parar()
	assert all(not s.activo for s in vivos)


def servidor_de(ns, simulador: Any, usuario: str = "demo", solo_lectura: bool = True, id_: str = "prueba", **mas: Any) -> Any:
	return ns.servidores.ServidorNAS(id_, "NAS de prueba", "127.0.0.1", simulador.puerto, https=simulador.https, usuario=usuario,
		solo_lectura=solo_lectura, recordar_contrasena=mas.pop("recordar_contrasena", False), **mas)


def cliente_de(ns, simulador: Any, usuario: str = "demo", contrasena: str | None = "demo", solo_lectura: bool = True,
		preguntas: Any = None, secretos: Any = None, conectar: bool = True, **mas: Any) -> Any:
	carpeta_temporal = mas.pop("carpeta_temporal", None)
	servidor = servidor_de(ns, simulador, usuario, solo_lectura, **mas)
	cliente = ns.cliente.ClienteDSM(servidor, secretos, preguntas, tiempo_conexion=5, tiempo_peticion=10, contrasena=contrasena,
		carpeta_temporal=carpeta_temporal)
	if conectar:
		cliente.conectar()
	return cliente


def generar_certificado(carpeta: Path, nombre: str) -> tuple[Path, Path]:
	"""Certificado autofirmado de PRUEBA para 127.0.0.1 (generado al vuelo; nunca se guarda en el repositorio)."""
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import ec
	from cryptography.x509.oid import NameOID

	clave = ec.generate_private_key(ec.SECP256R1())
	sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"synology-{nombre}")])
	ahora = datetime.datetime.now(datetime.UTC)
	certificado = (x509.CertificateBuilder().subject_name(sujeto).issuer_name(sujeto).public_key(clave.public_key())
		.serial_number(x509.random_serial_number()).not_valid_before(ahora - datetime.timedelta(days=1))
		.not_valid_after(ahora + datetime.timedelta(days=30)).sign(clave, hashes.SHA256()))
	ruta_cert, ruta_clave = carpeta / f"{nombre}.pem", carpeta / f"{nombre}.key"
	ruta_cert.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
	ruta_clave.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
		serialization.NoEncryption()))
	return ruta_cert, ruta_clave


def logins(simulador: Any) -> list[dict[str, Any]]:
	return [p for p in simulador.peticiones if p["api"] == "SYNO.API.Auth" and p["method"] == "login"]
