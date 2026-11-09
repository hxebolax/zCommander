# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de ``zc.cifrado`` (diseño 2.0, 11.13 y 18.2)."""

from __future__ import annotations

import io
import os
import threading

import pytest

from app.plugins import api
from app.plugins.api import pruebas
from app.services.vfs import resolver
from tests.plugins import p4_comun

MENSAJE = "El archivo está dañado o la contraseña no es correcta"


@pytest.fixture
def zc():
	return p4_comun.anfitrion("cifrado")


@pytest.fixture
def zcc(zc):
	return p4_comun.modulo(zc, "zcc")


@pytest.fixture
def ops(zc, zcc, monkeypatch):
	# Coste bajo en las operaciones para que las pruebas vayan deprisa (el formato es el mismo).
	monkeypatch.setitem(zcc.COSTES, "normal", 2**12)
	return p4_comun.modulo(zc, "operaciones")


def _cifrado(zcc, datos: bytes, contrasena: str = "una frase larga", n: int = 2**12) -> bytes:
	salida = io.BytesIO()
	zcc.cifrar(io.BytesIO(datos), salida, contrasena, "datos.bin", len(datos), n=n)
	return salida.getvalue()


def _contexto(operacion, decisor=None):
	ctx = api.ContextoEjecucion(threading.Event(), decisor or pruebas.DecisorFalso())
	ctx.operacion = operacion
	operacion.contexto = ctx
	return ctx


def test_tres_megas_vuelven_iguales(zcc):
	datos = os.urandom(3 * 1024 * 1024 + 12345)
	cifrado = _cifrado(zcc, datos)
	assert cifrado.startswith(b"ZCC1") and datos not in cifrado
	salida = io.BytesIO()
	zcc.descifrar(io.BytesIO(cifrado), salida, "una frase larga")
	assert salida.getvalue() == datos


def test_vacio_y_multiplo_exacto_del_bloque(zcc):
	for datos in (b"", os.urandom(2 * zcc.BLOQUE)):
		salida = io.BytesIO()
		zcc.descifrar(io.BytesIO(_cifrado(zcc, datos)), salida, "una frase larga")
		assert salida.getvalue() == datos


def test_un_byte_cambiado_o_truncado_da_el_mensaje(zcc):
	datos = os.urandom(3 * zcc.BLOQUE)
	cifrado = bytearray(_cifrado(zcc, datos))
	cambiado = bytes(cifrado[:-100]) + bytes([cifrado[-100] ^ 1]) + bytes(cifrado[-99:])
	ultimo_fuera = bytes(cifrado[: len(cifrado) - (zcc.BLOQUE + zcc.ETIQUETA)])
	cola_cortada = bytes(cifrado[:-5])
	anadido = bytes(cifrado) + os.urandom(zcc.BLOQUE + zcc.ETIQUETA)
	cabecera_cambiada = bytes(cifrado).replace(b'"datos.bin"', b'"datos.exe"', 1)
	for malo in (cambiado, ultimo_fuera, cola_cortada, anadido, cabecera_cambiada):
		with pytest.raises(zcc.ErrorZcc) as error:
			zcc.descifrar(io.BytesIO(malo), io.BytesIO(), "una frase larga")
		assert error.value.mensaje == MENSAJE


def test_contrasena_equivocada_da_el_mensaje(zcc):
	with pytest.raises(zcc.ErrorZcc) as error:
		zcc.descifrar(io.BytesIO(_cifrado(zcc, b"secreto")), io.BytesIO(), "otra")
	assert error.value.mensaje == MENSAJE


def test_memoria_de_scrypt_basta(zcc):
	assert zcc.memoria_scrypt(2**17) // (1024 * 1024) == 192
	assert zcc.memoria_scrypt(2**19) // (1024 * 1024) == 576
	assert len(zcc.derivar_clave("x", b"s" * 16, 2**17)) == 32


def test_fortaleza_en_texto(zcc):
	assert zcc.fortaleza("abc")[1].startswith("Muy débil")
	assert zcc.fortaleza("abcdefghi")[1].startswith("Débil: menos de 12")
	assert zcc.fortaleza("aaaaaaaaaaaaaaaa")[1].startswith("Débil")
	assert zcc.fortaleza("correcto caballo bateria grapa")[0] == 4


def test_cifrar_y_descifrar_con_la_operacion(zc, ops, tmp_path):
	original = tmp_path / "informe.txt"
	contenido = os.urandom(200_000)
	original.write_bytes(contenido)
	carpeta = tmp_path / "Fotos"
	(carpeta / "sub").mkdir(parents=True)
	(carpeta / "a.jpg").write_bytes(b"jpg")
	(carpeta / "sub" / "b.txt").write_text("hola")
	proveedor = resolver.proveedor_local()
	entradas = [p4_comun.entrada(original), p4_comun.entrada(carpeta)]
	cifrar = ops.OperacionCifrar(proveedor, entradas, "frase de prueba", papelera=lambda r: pytest.fail("no se pidió"))
	cifrar.ejecutar(_contexto(cifrar))
	assert not cifrar.errores, cifrar.errores
	assert (tmp_path / "informe.txt.zcc").is_file() and (tmp_path / "Fotos.zcc").is_file()
	original.rename(tmp_path / "antes.txt")
	import shutil

	shutil.rmtree(carpeta)
	descifrar = ops.OperacionDescifrar(proveedor, [p4_comun.entrada(tmp_path / "informe.txt.zcc"),
		p4_comun.entrada(tmp_path / "Fotos.zcc")], "frase de prueba")
	descifrar.ejecutar(_contexto(descifrar))
	assert not descifrar.errores, descifrar.errores
	assert (tmp_path / "informe.txt").read_bytes() == contenido
	assert (tmp_path / "Fotos" / "sub" / "b.txt").read_text() == "hola"
	assert (tmp_path / "Fotos" / "a.jpg").read_bytes() == b"jpg"
	assert not list(tmp_path.glob("*.parcial")) and not list(tmp_path.glob("*.zip"))


def test_nunca_sobrescribe(zc, ops, tmp_path):
	original = tmp_path / "a.txt"
	original.write_text("uno")
	(tmp_path / "a.txt.zcc").write_text("ya estaba")
	operacion = ops.OperacionCifrar(resolver.proveedor_local(), [p4_comun.entrada(original)], "frase de prueba")
	operacion.ejecutar(_contexto(operacion))
	assert (tmp_path / "a.txt.zcc").read_text() == "ya estaba"
	assert (tmp_path / "a.txt (2).zcc").is_file()


def test_contrasena_equivocada_no_deja_nada_descifrado(zc, ops, tmp_path):
	original = tmp_path / "secreto.txt"
	original.write_bytes(os.urandom(3 * 1024 * 1024))
	proveedor = resolver.proveedor_local()
	cifrar = ops.OperacionCifrar(proveedor, [p4_comun.entrada(original)], "la buena")
	cifrar.ejecutar(_contexto(cifrar))
	original.unlink()
	descifrar = ops.OperacionDescifrar(proveedor, [p4_comun.entrada(tmp_path / "secreto.txt.zcc")], "la mala")
	descifrar.ejecutar(_contexto(descifrar))
	assert [e.mensaje for e in descifrar.errores] == [MENSAJE]
	assert sorted(p.name for p in tmp_path.iterdir()) == ["secreto.txt.zcc"]
	# Con la función de volver a preguntar, la segunda contraseña sirve.
	preguntas = []
	descifrar = ops.OperacionDescifrar(proveedor, [p4_comun.entrada(tmp_path / "secreto.txt.zcc")], "la mala",
		pedir=lambda titulo, texto: preguntas.append(texto) or "la buena")
	descifrar.ejecutar(_contexto(descifrar))
	assert not descifrar.errores and preguntas and (tmp_path / "secreto.txt").is_file()


def test_el_original_solo_va_a_la_papelera_tras_comprobar(zc, ops, zcc, tmp_path, monkeypatch):
	original = tmp_path / "a.txt"
	original.write_text("contenido")
	enviados = []
	proveedor = resolver.proveedor_local()
	operacion = ops.OperacionCifrar(proveedor, [p4_comun.entrada(original)], "frase de prueba", borrar_originales=True,
		papelera=lambda ruta: enviados.append((ruta, (tmp_path / "a.txt.zcc").is_file())))
	operacion.ejecutar(_contexto(operacion))
	assert enviados == [(str(original), True)]
	# Si la comprobación falla, el original no se toca y no queda ningún .zcc.
	(tmp_path / "a.txt.zcc").unlink()
	enviados.clear()

	def comprobacion_mala(*args, **kwargs):
		raise zcc.ErrorZcc()

	monkeypatch.setattr(zcc, "descifrar", comprobacion_mala)
	operacion = ops.OperacionCifrar(proveedor, [p4_comun.entrada(original)], "frase de prueba", borrar_originales=True,
		papelera=lambda ruta: enviados.append(ruta))
	operacion.ejecutar(_contexto(operacion))
	assert enviados == [] and operacion.errores
	assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt"]


def test_formato_7z_compatible(zc, ops, tmp_path):
	import py7zr

	original = tmp_path / "a.txt"
	original.write_text("contenido del 7z")
	operacion = ops.OperacionCifrar(resolver.proveedor_local(), [p4_comun.entrada(original)], "frase de prueba", formato="7z")
	operacion.ejecutar(_contexto(operacion))
	assert not operacion.errores, operacion.errores
	with py7zr.SevenZipFile(tmp_path / "a.txt.7z", "r", password="frase de prueba") as archivo:
		assert archivo.readall()["a.txt"].read() == b"contenido del 7z"


def test_visor_descifra_en_memoria(zc, zcc, tmp_path):
	ruta = tmp_path / "nota.txt.zcc"
	ruta.write_bytes(_cifrado(zcc, "Línea secreta".encode()))
	zc._decisor = pruebas.DecisorFalso(["una frase larga", "otra"])
	zc.activar()
	documento = zc.instancia.ver(resolver.proveedor_local(), str(ruta), None)
	assert documento.secciones[0].texto == "Línea secreta" and not documento.aviso
	malo = zc.instancia.ver(resolver.proveedor_local(), str(ruta), None)
	assert malo.aviso == MENSAJE
	assert sorted(p.name for p in tmp_path.iterdir() if p.name != "data") == ["nota.txt.zcc"]


def test_descifrar_sin_zcc_lo_dice(zc, tmp_path):
	otro = tmp_path / "a.txt"
	otro.write_text("x")
	zc.ejecutar("descifrar", pruebas.contexto_de_prueba(activo=p4_comun.panel([otro])))
	assert zc.anuncios == [("No hay archivos cifrados (.zcc) que descifrar", api.RESULTADO)]


def test_dialogo_cifrar_pasa_revisar_teclado(zc, app_wx):
	from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto

	zc.activar()
	api.fijar_interfaz(p4_comun.InterfazFalsa())
	try:
		(dialogo,) = zc.instancia.ventanas_para_revisar(None)
		afirmar_teclado_correcto(dialogo)
		assert dialogo.problema() == "Escriba una contraseña"
		dialogo.contrasena.SetValue("una frase larga")
		assert dialogo.medidor.GetValue().startswith("Fuerte") or dialogo.medidor.GetValue().startswith("Aceptable")
		dialogo.repetida.SetValue("otra")
		assert dialogo.problema() == "Las dos contraseñas no coinciden"
		dialogo.repetida.SetValue("una frase larga")
		assert dialogo.problema() == "" and dialogo.opciones().formato == "zcc"
		dialogo.Destroy()
	finally:
		api.fijar_interfaz(None)
