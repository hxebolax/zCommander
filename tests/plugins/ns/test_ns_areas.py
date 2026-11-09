# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Áreas del NAS (diseño 2.0, 13.5 y 13.13): todas leen filas del simulador, las ausentes se ocultan y apagar exige dos confirmaciones."""

from __future__ import annotations

import pytest

from app.plugins import api

from .conftest import cliente_de

IDS = ("estado", "almacenamiento", "archivos", "carpetas", "usuarios", "paquetes", "contenedores", "drive", "photos", "tareas", "registros",
	"avisos", "red", "seguridad", "servicios", "monitor", "actualizaciones", "energia")


class ConfirmadorFalso:
	"""``areas.Confirmador`` con respuestas preparadas (los diálogos reales se prueban en test_ns_ui)."""

	def __init__(self, confirmar: bool = True, nombre: str | None = None, pedidos: dict | None = None) -> None:
		self._confirmar = confirmar
		self._nombre = nombre
		self._pedidos = dict(pedidos or {})
		self.preguntas: list[tuple[str, str]] = []

	def confirmar(self, titulo: str, texto: str, peligroso: bool = True) -> bool:
		self.preguntas.append(("confirmar", texto))
		return self._confirmar

	def escribir_nombre(self, titulo: str, texto: str, esperado: str) -> bool:
		self.preguntas.append(("nombre", esperado))
		return self._nombre is not None and self._nombre.casefold() == esperado.casefold()

	def pedir(self, titulo: str, peticion) -> str | None:
		self.preguntas.append(("pedir", peticion.clave))
		return self._pedidos.get(peticion.clave)


def _accion(vista, seccion_id: str, accion_id: str):
	seccion = next(s for s in vista.secciones if s.id == seccion_id)
	return seccion, next(a for a in seccion.acciones if a.id == accion_id)


def test_este_nas_tiene_las_18_areas(ns, arrancar):
	cliente = cliente_de(ns, arrancar())
	assert tuple(a.id for a in ns.areas.disponibles(cliente)) == IDS


@pytest.mark.parametrize("id_area", IDS)
def test_cada_area_devuelve_filas(ns, arrancar, id_area):
	cliente = cliente_de(ns, arrancar())
	vista = ns.areas.cargar(ns.areas.POR_ID[id_area], cliente, {"aviso_temperatura_c": 55})
	assert vista.secciones, id_area
	assert any(s.filas for s in vista.secciones), id_area
	for seccion in vista.secciones:
		for fila in seccion.filas:
			assert len(fila.valores) == len(seccion.columnas), (id_area, seccion.id)
			assert fila.detalle, (id_area, seccion.id)


def test_una_api_ausente_oculta_su_area(ns, arrancar):
	simulador = arrancar()
	for nombre in [n for n in simulador.estado.catalogo if n.startswith("SYNO.Docker.")]:
		del simulador.estado.catalogo[nombre]
	cliente = cliente_de(ns, simulador)
	ids = [a.id for a in ns.areas.disponibles(cliente)]
	assert "contenedores" not in ids and "estado" in ids
	assert ns.areas.POR_ID["contenedores"].disponible(cliente) == (False, "Necesita el paquete Container Manager")


def test_cuenta_sin_privilegios_dice_sin_permiso(ns, arrancar):
	cliente = cliente_de(ns, arrancar(), "lectura", "lectura")
	assert cliente.info.administrador is False
	vista = ns.areas.cargar(ns.areas.POR_ID["almacenamiento"], cliente)
	assert vista.secciones[0].filas[0].valores == ["Sin permiso con esta cuenta"]
	archivos = ns.areas.cargar(ns.areas.POR_ID["archivos"], cliente)
	compartidas = {f.valores[0] for f in archivos.secciones[0].filas}
	assert "Documentos" in compartidas and "Copias" not in compartidas


def test_datos_del_estado(ns, arrancar):
	cliente = cliente_de(ns, arrancar())
	vista = ns.areas.cargar(ns.areas.POR_ID["estado"], cliente, {"aviso_temperatura_c": 55})
	filas = {f.valores[0]: f.valores[1] for f in vista.secciones[0].filas}
	assert filas["Modelo"] == "DS220+"
	assert filas["Versión de DSM"] == "DSM 7.3.2-86009 Update 5"
	assert "J4025" in filas["Procesador"] and filas["Memoria instalada"] == "10 GB"
	assert filas["Volumen 1"].startswith("245 GB usados de 3,49 TB")
	assert filas["Actualización de seguridad"].startswith("Al día")


def test_avisos_de_salud(ns, arrancar):
	simulador = arrancar()
	simulador.escenario(disco_aviso=True, temperatura=61)
	cliente = cliente_de(ns, simulador)
	estado = ns.areas.cargar(ns.areas.POR_ID["estado"], cliente, {"aviso_temperatura_c": 55}).avisos()
	assert any("Temperatura alta" in t for t in estado.values())
	assert any("Unidad 2" in t for t in estado.values())
	contenedores = ns.areas.cargar(ns.areas.POR_ID["contenedores"], cliente).avisos()
	assert any("homeassistant" in t for t in contenedores.values())
	seguridad = ns.areas.cargar(ns.areas.POR_ID["seguridad"], cliente).avisos()
	assert any("caduca en" in t for t in seguridad.values())


def test_accion_de_escritura_en_solo_lectura_se_bloquea(ns, arrancar):
	cliente = cliente_de(ns, arrancar("escritura"))
	vista = ns.areas.cargar(ns.areas.POR_ID["contenedores"], cliente)
	seccion, parar = _accion(vista, "contenedores", "parar")
	fila = next(f for f in seccion.filas if f.clave == "jellyfin")
	with pytest.raises(api.SoloLectura):
		ns.areas.preparar(parar, fila, seccion, cliente, ConfirmadorFalso())


def test_parar_contenedor_en_modo_simular_confirma_y_no_cambia(ns, arrancar):
	simulador = arrancar("simular")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	vista = ns.areas.cargar(ns.areas.POR_ID["contenedores"], cliente)
	seccion, parar = _accion(vista, "contenedores", "parar")
	fila = next(f for f in seccion.filas if f.clave == "jellyfin")
	confirmador = ConfirmadorFalso()
	valores = ns.areas.preparar(parar, fila, seccion, cliente, confirmador)
	assert confirmador.preguntas == [("confirmar", "¿Parar el contenedor jellyfin?")]
	resultado = ns.areas.ejecutar(parar, cliente, fila, valores)
	assert resultado.mensaje == "Contenedor jellyfin parado"
	assert simulador.diario[-1]["api"] == "SYNO.Docker.Container" and simulador.diario[-1]["params"]["name"] == "jellyfin"
	assert next(c for c in simulador.estado.datos["contenedores"] if c["name"] == "jellyfin")["status"] == "running"


def test_cancelar_la_confirmacion_no_envia_nada(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	vista = ns.areas.cargar(ns.areas.POR_ID["paquetes"], cliente)
	seccion, iniciar = _accion(vista, "paquetes", "iniciar")
	fila = next(f for f in seccion.filas if f.clave == "Python2")
	assert ns.areas.preparar(iniciar, fila, seccion, cliente, ConfirmadorFalso(confirmar=False)) is None
	assert simulador.diario == []


def test_apagar_exige_dos_confirmaciones_y_deja_el_nas_apagado(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	vista = ns.areas.cargar(ns.areas.POR_ID["energia"], cliente)
	seccion, apagar = _accion(vista, "energia", "apagar")
	# Primera confirmación sí, nombre mal escrito: no se apaga.
	confirmador = ConfirmadorFalso(nombre="otro")
	assert ns.areas.preparar(apagar, None, seccion, cliente, confirmador) is None
	assert [p[0] for p in confirmador.preguntas] == ["confirmar", "nombre"]
	assert "Se cortarán 4 conexiones abiertas" in confirmador.preguntas[0][1]
	assert not simulador.estado.apagado
	# Primera confirmación no: ni siquiera se pide el nombre.
	confirmador = ConfirmadorFalso(confirmar=False, nombre="NAS-Casa")
	assert ns.areas.preparar(apagar, None, seccion, cliente, confirmador) is None
	assert [p[0] for p in confirmador.preguntas] == ["confirmar"]
	# Las dos: el NAS falso queda apagado y deja de responder.
	confirmador = ConfirmadorFalso(nombre="nas-casa")
	valores = ns.areas.preparar(apagar, None, seccion, cliente, confirmador)
	assert valores == {} and confirmador.preguntas[1] == ("nombre", "NAS-Casa")
	resultado = ns.areas.ejecutar(apagar, cliente, None, valores)
	assert resultado.desconectar and simulador.estado.apagado
	assert [p for p in simulador.peticiones if p["api"] == "SYNO.Core.System" and p["method"] == "shutdown"][-1]["version"] == "1"
	with pytest.raises(api.ErrorRed):
		cliente.llamar("SYNO.DSM.Info", "getinfo")


def test_reiniciar_cierra_las_sesiones(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	accion = ns.areas.accion_energia("reiniciar")
	seccion = ns.areas.Seccion("energia", "", [], datos=ns.areas.consecuencias(cliente))
	valores = ns.areas.preparar(accion, None, seccion, cliente, ConfirmadorFalso(nombre="NAS-Casa"))
	ns.areas.ejecutar(accion, cliente, None, valores)
	assert simulador.estado.reinicios == 1 and not simulador.estado.sesiones


def test_cambiar_permiso_y_desbloquear_ip_en_escritura(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	vista = ns.areas.cargar(ns.areas.POR_ID["carpetas"], cliente)
	seccion, accion = _accion(vista, "permisos", "permiso")
	fila = next(f for f in seccion.filas if f.clave == "Documentos:lectura")
	valores = ns.areas.preparar(accion, fila, seccion, cliente, ConfirmadorFalso(pedidos={"permiso": "Lectura y escritura"}))
	ns.areas.ejecutar(accion, cliente, fila, valores)
	permiso = next(p for p in simulador.estado.datos["permisos"]["Documentos"] if p["name"] == "lectura")
	assert permiso["is_writable"] is True
	vista = ns.areas.cargar(ns.areas.POR_ID["seguridad"], cliente)
	seccion, desbloquear = _accion(vista, "bloqueadas", "desbloquear")
	fila = seccion.filas[0]
	ns.areas.ejecutar(desbloquear, cliente, fila, ns.areas.preparar(desbloquear, fila, seccion, cliente, ConfirmadorFalso()))
	assert fila.datos["ip"] not in {b["ip"] for b in simulador.estado.datos["seguridad"]["ip_bloqueadas"]}


def test_cambiar_contrasena_pide_la_confirmacion_de_dsm(ns, arrancar):
	from .conftest import PreguntasFalsas

	simulador = arrancar("escritura")
	preguntas = PreguntasFalsas(contrasena_dsm="demo")
	cliente = cliente_de(ns, simulador, solo_lectura=False, preguntas=preguntas)
	vista = ns.areas.cargar(ns.areas.POR_ID["usuarios"], cliente)
	seccion, accion = _accion(vista, "usuarios", "contrasena")
	fila = next(f for f in seccion.filas if f.clave == "lectura")
	valores = ns.areas.preparar(accion, fila, seccion, cliente, ConfirmadorFalso(pedidos={"nueva": "Nueva-1234", "repetida": "Nueva-1234"}))
	assert ns.areas.ejecutar(accion, cliente, fila, valores).mensaje == "Contraseña de lectura cambiada"
	assert preguntas.preguntado[-1][0] == "contrasena_dsm"
	assert simulador.diario[-1]["params"]["password"] == "***"


def test_busqueda_universal_y_file_station(ns, arrancar):
	simulador = arrancar()
	cliente = cliente_de(ns, simulador)
	assert "/Documentos/notas.txt" in ns.busqueda.buscar_en_nas(cliente, "notas")
	pdf = ns.busqueda.buscar_en_nas(cliente, "*.pdf;*.docx | *.bak", carpetas=["/Documentos"])
	assert "/Documentos/Facturas/Factura luz enero 2026.pdf" in pdf and all(r.startswith("/Documentos/") for r in pdf)
	assert ns.busqueda.patrones("*.pdf;*.docx | *.bak") == "*.pdf,*.docx"


def test_motor_de_busqueda_entrega_direcciones_synology(ns, arrancar, tmp_path):
	from types import SimpleNamespace

	from .conftest import servidor_de

	simulador = arrancar()
	almacen = ns.servidores.AlmacenServidores(tmp_path)
	conexiones = ns.conexiones.Conexiones(almacen)
	conexiones.conectar(servidor_de(ns, simulador, id_="casa"), contrasena="demo")
	encontrados: list[str] = []
	ns.busqueda.crear_motor(conexiones)(SimpleNamespace(nombres="Platero*", max_resultados=10), encontrados.append, None)
	assert encontrados == ["synology://casa/Multimedia/Audiolibros/Platero y yo.mp3"]
	conexiones.desconectar_todas()


def test_enlaces_compartidos_crear_editar_y_borrar(ns, arrancar):
	simulador = arrancar("escritura")
	cliente = cliente_de(ns, simulador, solo_lectura=False)
	enlaces = cliente.llamar("SYNO.FileStation.Sharing", "create", path=["/Documentos/notas.txt"], password="clave")["links"]
	assert enlaces[0]["url"].startswith("https://") and enlaces[0]["has_password"] and "password" not in enlaces[0]
	vista = ns.areas.cargar(ns.areas.POR_ID["archivos"], cliente)
	seccion, editar = _accion(vista, "enlaces", "editar_enlace")
	fila = seccion.filas[0]
	valores = ns.areas.preparar(editar, fila, seccion, cliente, ConfirmadorFalso(pedidos={"caduca": "2026-12-31"}))
	assert ns.areas.ejecutar(editar, cliente, fila, valores).mensaje == "Enlace de /Documentos/notas.txt: caduca 2026-12-31"
	assert next(iter(simulador.estado.enlaces.values()))["date_expired"] == "2026-12-31"
	_seccion, borrar = _accion(vista, "enlaces", "borrar_enlace")
	ns.areas.ejecutar(borrar, cliente, fila, ns.areas.preparar(borrar, fila, seccion, cliente, ConfirmadorFalso()))
	assert simulador.estado.enlaces == {}
