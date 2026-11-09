# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""File Station como origen del panel (diseño 2.0, 13.7 y 13.13): listar, subir y bajar, copiar en el servidor y cancelar."""

from __future__ import annotations

import hashlib
import io
import os
import threading

import pytest

from app.plugins import api

from .conftest import SecretosFalsos, servidor_de

NOMBRE = "Canción de cuna del ñandú (versión larga).bin"


@pytest.fixture
def nas(ns, arrancar, tmp_path):
	"""Conexiones con un NAS simulado en modo escritura y su proveedor (empieza en solo lectura, como siempre)."""
	simulador = arrancar("escritura")
	almacen = ns.servidores.AlmacenServidores(tmp_path / "datos")
	servidor = servidor_de(ns, simulador)
	almacen.guardar(servidor)
	conexiones = ns.conexiones.Conexiones(almacen, SecretosFalsos(), carpeta_temporal=tmp_path / "subidas")
	conexion = conexiones.conectar(servidor, contrasena="demo")
	proveedor, ruta = ns.proveedor.crear_fabrica(conexiones)("synology://prueba/")
	assert ruta == "/"
	yield simulador, conexiones, conexion, proveedor
	conexiones.desconectar_todas()


def _escribir(conexiones, proveedor) -> None:
	conexiones.cambiar_modo("prueba", True)
	assert proveedor.capacidades.escribir


def test_raiz_lista_las_carpetas_compartidas(nas):
	_simulador, _conexiones, _conexion, proveedor = nas
	nombres = {e.nombre for e in proveedor.listar("/")}
	assert {"Documentos", "Multimedia", "photo", "docker", "homes", "Copias"} <= nombres
	assert "web_packages" not in nombres
	assert all(e.es_carpeta for e in proveedor.listar("/"))
	assert proveedor.mostrar("/Documentos") == "synology://prueba/Documentos"
	assert proveedor.padre("/Documentos/Facturas") == "/Documentos" and proveedor.padre("/Documentos") == "/"
	assert proveedor.padre("/") is None
	assert proveedor.servidor == "synology:prueba"
	libre, total = proveedor.espacio_libre("/Documentos")
	assert total == 3838417727488 and libre == total - 245 * 1024 ** 3


def test_entra_y_lista_con_tildes(nas):
	_simulador, _conexiones, _conexion, proveedor = nas
	entradas = {e.nombre: e for e in proveedor.listar("/Documentos")}
	assert entradas["notas.txt"].tamano == 12800 and not entradas["notas.txt"].es_carpeta
	assert entradas["Declaración de la renta"].es_carpeta
	assert "Manual de la caldera — modelo Ñandú 3000.pdf" in entradas
	assert proveedor.info("/Documentos/notas.txt").tamano == 12800
	with pytest.raises(api.NoEncontrado):
		proveedor.info("/Documentos/no-existe.txt")


def test_solo_lectura_por_defecto_en_el_panel(nas):
	_simulador, _conexiones, _conexion, proveedor = nas
	assert proveedor.capacidades.escribir is False
	with pytest.raises(api.SoloLectura, match="solo lectura"):
		proveedor.abrir_escritura("/Documentos/x.txt", 3)
	with pytest.raises(api.SoloLectura):
		proveedor.crear_carpeta("/Documentos/Nueva")


def test_sube_y_baja_3_mb_con_tildes(nas):
	simulador, conexiones, _conexion, proveedor = nas
	_escribir(conexiones, proveedor)
	datos = os.urandom(3 * 1024 * 1024)
	ruta = proveedor.unir("/Documentos", NOMBRE)
	with proveedor.abrir_escritura(ruta, len(datos)) as destino:
		vista = memoryview(datos)
		for inicio in range(0, len(datos), 65536):
			destino.write(vista[inicio:inicio + 65536])
	assert proveedor.info(ruta).tamano == len(datos)
	with proveedor.abrir_lectura(ruta) as origen:
		assert origen.read() == datos
	assert proveedor.suma(ruta, "md5") == hashlib.md5(datos, usedforsecurity=False).hexdigest()
	assert simulador.estado.nodo(f"/Documentos/{NOMBRE}").contenido == datos


def test_subida_sin_tamano_usa_un_temporal_de_la_cache(nas, tmp_path):
	_simulador, conexiones, _conexion, proveedor = nas
	_escribir(conexiones, proveedor)
	with proveedor.abrir_escritura("/Documentos/sin tamaño.txt") as destino:
		destino.write("áéí ñ".encode())
	with proveedor.abrir_lectura("/Documentos/sin tamaño.txt") as origen:
		assert origen.read().decode() == "áéí ñ"
	assert not any((tmp_path / "subidas").glob("*.parcial"))


def test_copia_en_el_servidor_con_progreso(nas):
	simulador, conexiones, _conexion, proveedor = nas
	_escribir(conexiones, proveedor)
	avances: list[tuple[int, int]] = []
	hecho = proveedor.transferir(proveedor, "/Documentos/notas.txt", "/Copias/notas copiadas.txt", lambda h, t: avances.append((h, t)),
		threading.Event())
	assert hecho is True
	assert avances and avances[-1][0] == avances[-1][1]
	assert proveedor.info("/Copias/notas copiadas.txt").tamano == 12800
	assert proveedor.info("/Documentos/notas.txt").tamano == 12800
	assert any(p["api"] == "SYNO.FileStation.CopyMove" for p in simulador.peticiones)
	assert not any(p["api"] == "SYNO.FileStation.Download" for p in simulador.peticiones)


def test_cancela_una_tarea_del_nas_con_stop(nas):
	simulador, conexiones, conexion, proveedor = nas
	_escribir(conexiones, proveedor)
	simulador.escenario(ritmo_tareas=0.05)
	cancelacion = threading.Event()

	def progreso(_hechos: int, _total: int) -> None:
		cancelacion.set()

	with pytest.raises(api.Cancelado):
		conexion.cliente.tarea_fondo("SYNO.FileStation.CopyMove", {"path": ["/Multimedia/Películas"], "dest_folder_path": "/Copias",
			"overwrite": False, "remove_src": False}, progreso=progreso, cancelacion=cancelacion, intervalo=0.05)
	assert any(p["api"] == "SYNO.FileStation.CopyMove" and p["method"] == "stop" for p in simulador.peticiones)
	assert not simulador.estado.existe("/Copias/Películas")


def test_renombrar_mover_crear_y_borrar(nas):
	simulador, conexiones, _conexion, proveedor = nas
	_escribir(conexiones, proveedor)
	proveedor.crear_carpeta("/Documentos/Carpeta nueva")
	assert proveedor.info("/Documentos/Carpeta nueva").es_carpeta
	with pytest.raises(api.YaExiste):
		proveedor.crear_carpeta("/Documentos/Carpeta nueva")
	proveedor.renombrar("/Documentos/Lista de la compra.md", "/Documentos/Lista de la compra (vieja).md")
	assert proveedor.existe("/Documentos/Lista de la compra (vieja).md")
	proveedor.renombrar("/Documentos/Lista de la compra (vieja).md", "/Documentos/Carpeta nueva/Lista.md")
	assert proveedor.existe("/Documentos/Carpeta nueva/Lista.md") and not proveedor.existe("/Documentos/Lista de la compra (vieja).md")
	proveedor.eliminar("/Documentos/Carpeta nueva", recursivo=True)
	assert not proveedor.existe("/Documentos/Carpeta nueva")
	assert simulador.estado.existe("/Documentos/#recycle/Carpeta nueva")
	with pytest.raises(api.ErrorAcceso):
		proveedor.eliminar("/Documentos", recursivo=True)


def test_fabrica_con_un_nas_desconocido(ns, tmp_path):
	conexiones = ns.conexiones.Conexiones(ns.servidores.AlmacenServidores(tmp_path))
	with pytest.raises(api.NoEncontrado, match="Conectar con un NAS"):
		ns.proveedor.crear_fabrica(conexiones)("synology://nadie/Documentos")
	assert ns.proveedor.separar_direccion("synology://Casa/Documentos//Facturas/") == ("casa", "/Documentos/Facturas")


def test_conecta_al_listar_si_no_estaba_conectado(ns, arrancar, tmp_path):
	simulador = arrancar()
	almacen = ns.servidores.AlmacenServidores(tmp_path)
	almacen.guardar(servidor_de(ns, simulador, id_="casa"))
	secretos = SecretosFalsos()
	secretos.guardar("casa:contrasena", "demo")
	conexiones = ns.conexiones.Conexiones(almacen, secretos)
	almacen.guardar(servidor_de(ns, simulador, id_="casa", recordar_contrasena=True))
	proveedor, _ruta = ns.proveedor.crear_fabrica(conexiones)("synology://casa/")
	assert "Documentos" in {e.nombre for e in proveedor.listar("/")}
	assert conexiones.obtener("casa") is not None
	conexiones.desconectar_todas()


def test_subida_cancelada_no_deja_archivo(nas):
	simulador, conexiones, conexion, _proveedor = nas
	_escribir(conexiones, _proveedor)
	cancelacion = threading.Event()
	flujo = io.BytesIO(b"x" * (1024 * 1024))

	def progreso(hechos: int, _total: int) -> None:
		if hechos >= 256 * 1024:
			cancelacion.set()

	with pytest.raises(api.Cancelado):
		conexion.cliente.subir("/Documentos", "a medias.bin", flujo, 1024 * 1024, progreso=progreso, cancelacion=cancelacion)
	assert not simulador.estado.existe("/Documentos/a medias.bin")
