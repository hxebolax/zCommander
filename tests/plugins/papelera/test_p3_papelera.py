# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Papelera de reciclaje como panel (diseño 2.0, 11.20 y 18.2).

Nunca se vacía ni se restaura nada de la papelera real: las pruebas usan una
papelera de mentira en una carpeta temporal, con sus ``$I`` y ``$R`` como los
deja Windows. La única que mira la papelera real (``interfaz``) solo la lee.
"""

from __future__ import annotations

import os
import struct
import time

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from tests.plugins.p3_comun import contexto_operacion, modulo, preparar


@pytest.fixture
def entorno(tmp_path):
	zc, paquete = preparar("papelera")
	motor = modulo(paquete, "motor")
	bin_ = tmp_path / "$Recycle.Bin" / "S-1-5-21-prueba"
	bin_.mkdir(parents=True)
	zc.instancia.papelera = motor.Papelera(lambda: [str(bin_)])
	return zc, motor, tmp_path, bin_


def _eliminar(motor, bin_, original, contenido: bytes | None, eliminado: float, ident: str) -> None:
	"""Imita a Windows: el contenido pasa a ``$R<id>`` y los datos a ``$I<id>``."""
	extension = os.path.splitext(original)[1]
	ruta_r = bin_ / f"$R{ident}{extension}"
	if contenido is None:
		ruta_r.mkdir()
		(ruta_r / "dentro.txt").write_bytes(b"12345")
		tamano = 5
	else:
		ruta_r.write_bytes(contenido)
		tamano = len(contenido)
	(bin_ / f"$I{ident}{extension}").write_bytes(motor.formar_i(tamano, eliminado, str(original)))


def test_un_elemento_se_ve_con_su_ubicacion_original_y_su_fecha(entorno):
	zc, motor, carpeta, bin_ = entorno
	ahora = time.time()
	_eliminar(motor, bin_, carpeta / "Documentos" / "informe final.docx", b"x" * 300, ahora - 3600, "AB12CD")
	_eliminar(motor, bin_, carpeta / "Fotos", None, ahora - 60, "ZZ9911")
	(bin_ / "$IHUERFA.txt").write_bytes(motor.formar_i(1, ahora, "C:\\perdido.txt"))  # sin su $R: se omite
	proveedor, ruta = zc.instancia.fabrica("papelera://")
	assert ruta == "" and proveedor.esquema == "papelera"
	entradas = proveedor.listar("")
	assert [e.nombre for e in entradas] == ["Fotos", "informe final.docx"]  # lo último eliminado, primero
	informe = entradas[1]
	assert informe.ruta_real == str(carpeta / "Documentos")
	assert informe.tamano == 300 and abs(informe.modificado - (ahora - 3600)) < 1
	assert zc.columna("ubicacion", informe, proveedor) == str(carpeta / "Documentos")
	assert zc.columna("eliminado", informe, proveedor) == api.formato.fecha(ahora - 3600, "larga")
	assert zc.columna("ubicacion", informe, None) is None
	# Se entra en una carpeta eliminada y se sube a la raíz de la papelera.
	fotos = entradas[0]
	assert fotos.es_carpeta
	assert [e.nombre for e in proveedor.listar(fotos.ruta)] == ["dentro.txt"]
	assert proveedor.padre(fotos.ruta) == ""
	assert proveedor.mostrar(os.path.join(fotos.ruta, "dentro.txt")).endswith("Fotos\\dentro.txt")
	assert motor.resumen(zc.instancia.papelera.elementos()) == "2 elementos, 305 bytes"
	assert zc.instancia.unidades()[0].descripcion == "2 elementos, 305 bytes"


def test_restaurar_lo_devuelve_a_su_sitio(entorno):
	zc, motor, carpeta, bin_ = entorno
	original = carpeta / "Proyectos" / "plan.txt"
	_eliminar(motor, bin_, original, b"plan", time.time(), "QW1234")
	proveedor, _r = zc.instancia.fabrica("papelera://")
	elementos = [proveedor.elemento(e.ruta) for e in proveedor.listar("")]
	operacion = motor.OperacionRestaurar(elementos)
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert original.read_bytes() == b"plan"  # la carpeta Proyectos ya no existía: se crea
	assert not list(bin_.iterdir())
	assert operacion.restaurados == [str(original)]


def test_restaurar_sobre_algo_que_ya_existe_pregunta(entorno):
	zc, motor, carpeta, bin_ = entorno
	original = carpeta / "nota.txt"
	original.write_bytes(b"la nueva")
	_eliminar(motor, bin_, original, b"la vieja", time.time(), "AA0001")
	proveedor, _r = zc.instancia.fabrica("papelera://")
	elementos = [proveedor.elemento(e.ruta) for e in proveedor.listar("")]
	decisor = pruebas.DecisorFalso([0])  # «Restaurar con otro nombre»
	operacion = motor.OperacionRestaurar(elementos)
	ctx = contexto_operacion(decisor)
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert decisor.preguntas[0][0] == "elegir"
	assert original.read_bytes() == b"la nueva"
	assert (carpeta / "nota (2).txt").read_bytes() == b"la vieja"


def test_eliminar_definitivo_y_vaciar(entorno):
	zc, motor, carpeta, bin_ = entorno
	_eliminar(motor, bin_, carpeta / "a.txt", b"a", time.time(), "AAAAAA")
	_eliminar(motor, bin_, carpeta / "Carpeta", None, time.time(), "BBBBBB")
	proveedor, _r = zc.instancia.fabrica("papelera://")
	entradas = proveedor.listar("")
	carpeta_eliminada = next(e for e in entradas if e.es_carpeta)
	# Como lo hace el motor: lo de dentro primero y la carpeta después.
	proveedor.eliminar(os.path.join(carpeta_eliminada.ruta, "dentro.txt"))
	proveedor.eliminar(carpeta_eliminada.ruta)
	assert [e.nombre for e in proveedor.listar("")] == ["a.txt"]
	with pytest.raises(api.SoloLectura):
		proveedor.eliminar(str(carpeta / "fuera.txt"))
	vaciadas: list[str] = []
	operacion = motor.OperacionVaciar(["C:", "D:"], vaciar=vaciadas.append)
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert vaciadas == ["C:", "D:"]


def test_formatos_de_i_y_direcciones(entorno):
	_zc, motor, _carpeta, _bin = entorno
	marca = 1_700_000_000.0
	assert motor.leer_i(motor.formar_i(10, marca, "C:\\x\\ñ.txt")) == (10, pytest.approx(marca), "C:\\x\\ñ.txt")
	version_1 = struct.pack("<qqq", 1, 7, motor.marca_a_filetime(marca)) + "D:\\viejo.txt".encode("utf-16-le").ljust(520, b"\x00")
	assert motor.leer_i(version_1)[::2] == (7, "D:\\viejo.txt")
	with pytest.raises(ValueError):
		motor.leer_i(b"corto")
	assert motor.separar_direccion("papelera://") == ""
	assert motor.separar_direccion("papelera://d:/") == "D:"
	assert motor.nombre_libre(__file__) != __file__


def test_restaurar_fuera_de_la_papelera_avisa(entorno):
	zc, _motor, _carpeta, _bin = entorno
	zc.ejecutar("restaurar", pruebas.contexto_de_prueba())
	assert ("Esta orden sirve en el panel de la papelera", api.ESENCIAL) in zc.anuncios


def test_ordenes_con_manejador_real():
	preparar("papelera")
	for orden in ("abrir", "restaurar", "vaciar"):
		funcion = registro.manejador(f"zc.papelera:{orden}")
		assert funcion is not None and not getattr(funcion, "provisional", False)
	assert any(u.direccion == "papelera://" for u in registro.unidades_fijas())


@pytest.mark.interfaz
def test_la_papelera_real_se_lee_sin_tocarla():
	"""Solo lectura: lista la papelera del usuario de pruebas y no cambia nada."""
	zc, paquete = preparar("papelera")
	motor = modulo(paquete, "motor")
	carpetas = motor.carpetas_papelera(motor.unidades_fijas())
	antes = {c: sorted(os.listdir(c)) for c in carpetas}
	elementos = zc.instancia.papelera.elementos()
	assert all(isinstance(e.original, str) and e.tamano >= 0 for e in elementos)
	assert motor.resumen(elementos)
	assert {c: sorted(os.listdir(c)) for c in carpetas} == antes
