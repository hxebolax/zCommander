# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Proveedor ZIP: nombres peligrosos, cp850, transacciones que reconstruyen una vez, extraer y comprimir."""

from __future__ import annotations

import os
import zipfile

import pytest

from app.core.tareas import ejecutor_directo
from app.services.operaciones.comprimir import OpcionesComprimir, OperacionComprimir, OperacionExtraer, OperacionProbar
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.eliminar import OperacionEliminar
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import AccionConflicto, AccionError, Estado, Politica, RespuestaConflicto
from app.services.vfs import base, registro_proveedores, resolver  # noqa: F401 - registra los proveedores
from app.services.vfs import zip as modulo_zip
from app.services.vfs.local import ProveedorLocal
from app.services.vfs.zip import ProveedorZip, nombre_seguro


class DecisorFalso:
	def __init__(self) -> None:
		self.textos: list[str] = []

	def resolver_conflictos(self, operacion, conflictos):
		return [RespuestaConflicto(AccionConflicto.SOBRESCRIBIR) for _ in conflictos]

	def preguntar_conflicto(self, operacion, conflicto):
		return RespuestaConflicto(AccionConflicto.SOBRESCRIBIR)

	def preguntar_error(self, operacion, pregunta):
		return AccionError.OMITIR

	def elegir(self, titulo, texto, opciones, predeterminada=0, escape=-1, operacion=None):
		return 0

	def pedir_texto(self, titulo, texto, valor="", oculto=False, operacion=None):
		self.textos.append(texto)
		return None


def _lanzar(operacion, decisor=None):
	gestor = GestorOperaciones(decisor or DecisorFalso(), max_paralelas=2, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


@pytest.fixture
def local():
	return ProveedorLocal()


def _zip_malicioso(ruta) -> None:
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("bueno.txt", "hola")
		archivo.writestr("../malo.txt", "fuera")
		archivo.writestr("sub/../../peor.txt", "fuera")
		archivo.writestr("/absoluto.txt", "fuera")
		archivo.writestr("C:/unidad.txt", "fuera")
		archivo.writestr("flujo.txt:Zone.Identifier", "fuera")
		archivo.writestr("docs/dentro.txt", "dentro")


def test_nombre_seguro():
	assert nombre_seguro("a/b.txt") == "a/b.txt"
	assert nombre_seguro("a\\b.txt") == "a/b.txt"
	assert nombre_seguro("./a//b.txt") == "a/b.txt"
	assert nombre_seguro("carpeta/") == "carpeta"
	for malo in ("../x", "a/../../x", "/x", "\\\\srv\\x", "C:/x", "c:x", "a:b", "x\x01"):
		assert nombre_seguro(malo) is None, malo


def test_zip_con_rutas_peligrosas_no_las_lista_ni_las_extrae(tmp_path, local):
	ruta = tmp_path / "datos" / "malo.zip"
	ruta.parent.mkdir()
	_zip_malicioso(ruta)
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	assert isinstance(proveedor, ProveedorZip)
	nombres = sorted(e.nombre for e in proveedor.listar(""))
	assert nombres == ["bueno.txt", "docs"]
	assert "../malo.txt" in proveedor.omitidas
	assert len(proveedor.omitidas) == 5
	destino = tmp_path / "datos" / "extraido"
	destino.mkdir()
	entrada = local.info(str(ruta))
	operacion = _lanzar(OperacionExtraer(local, [entrada], local, str(destino), OpcionesCopia()))
	assert (destino / "bueno.txt").read_text(encoding="utf-8") == "hola"
	assert (destino / "docs" / "dentro.txt").read_text(encoding="utf-8") == "dentro"
	assert not (tmp_path / "datos" / "malo.txt").exists()
	assert not (tmp_path / "peor.txt").exists()
	assert not (destino / "flujo.txt").exists()
	# La extracción avisa de lo omitido, pero extrae lo bueno.
	assert operacion.estado == Estado.TERMINADA_CON_ERRORES
	assert any("peligrosa" in e.mensaje for e in operacion.errores)
	proveedor.cerrar()


def test_zip_sin_marca_utf8_se_lee_como_cp850(tmp_path, local):
	ruta = tmp_path / "antiguo.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("AXo.txt", "contenido")
	datos = ruta.read_bytes()
	assert datos.count(b"AXo.txt") == 2  # cabecera local y directorio central
	ruta.write_bytes(datos.replace(b"AXo.txt", "Año.txt".encode("cp850")))
	with zipfile.ZipFile(ruta) as archivo:
		assert not archivo.infolist()[0].flag_bits & 0x800
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	assert [e.nombre for e in proveedor.listar("")] == ["Año.txt"]
	with proveedor.abrir_lectura("Año.txt") as flujo:
		assert flujo.read() == b"contenido"
	proveedor.cerrar()


def test_abrir_ruta_entra_en_el_zip(tmp_path):
	ruta = tmp_path / "x.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("sub/a.txt", "a")
	proveedor, carpeta, cursor = resolver.abrir_ruta(str(ruta))
	assert isinstance(proveedor, ProveedorZip) and carpeta == "" and cursor is None
	assert proveedor.mostrar("sub") == str(ruta) + "\\sub"
	proveedor, carpeta, cursor = resolver.abrir_ruta(str(ruta) + "\\sub")
	assert carpeta == "sub"
	proveedor, carpeta, cursor = resolver.abrir_ruta(str(ruta) + "\\sub\\a.txt")
	assert carpeta == "sub" and cursor == "a.txt"
	assert proveedor.padre("sub/a.txt") == "sub" and proveedor.padre("sub") == "" and proveedor.padre("") is None


def test_copiar_dos_archivos_al_zip_reconstruye_una_vez(tmp_path, local, monkeypatch):
	ruta = tmp_path / "destino.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("viejo.txt", "viejo" * 100)
		archivo.writestr("carpeta/", "")
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "a.txt").write_text("uno", encoding="utf-8")
	(origen / "b.txt").write_text("dos" * 500, encoding="utf-8")
	reconstrucciones: list[int] = []
	original = ProveedorZip._reconstruir

	def contar(self, vista, firma):
		reconstrucciones.append(1)
		return original(self, vista, firma)

	monkeypatch.setattr(ProveedorZip, "_reconstruir", contar)
	proveedor = resolver.abrir_comprimido(local, str(ruta))
	assert proveedor.capacidades.escribir
	entradas = sorted(local.listar(str(origen)), key=lambda e: e.nombre)
	operacion = _lanzar(OperacionCopiar(local, entradas, proveedor, "carpeta", OpcionesCopia()))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert len(reconstrucciones) == 1
	with zipfile.ZipFile(ruta) as archivo:
		assert archivo.testzip() is None
		assert sorted(archivo.namelist()) == ["carpeta/", "carpeta/a.txt", "carpeta/b.txt", "viejo.txt"]
		assert archivo.read("carpeta/b.txt") == b"dos" * 500
		assert archivo.read("viejo.txt") == b"viejo" * 100
		assert not any(n.startswith("~zc") for n in archivo.namelist())
	# El panel ve el cambio (el archivo cambió en el disco y el índice se vuelve a leer).
	assert sorted(e.nombre for e in proveedor.listar("carpeta")) == ["a.txt", "b.txt"]
	assert not any(n.startswith("~zc") for n in os.listdir(tmp_path))
	proveedor.cerrar()


def test_transaccion_descartada_no_escribe(tmp_path, local):
	ruta = tmp_path / "x.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("a.txt", "a")
	antes = ruta.read_bytes()
	proveedor = ProveedorZip(local, str(ruta))
	with pytest.raises(base.Cancelado), proveedor.transaccion():
		with proveedor.abrir_escritura("b.txt") as salida:
			salida.write(b"b")
		proveedor.crear_carpeta("nueva")
		assert {e.nombre for e in proveedor.listar("")} == {"a.txt", "b.txt", "nueva"}
		raise base.Cancelado()
	assert ruta.read_bytes() == antes
	assert [e.nombre for e in proveedor.listar("")] == ["a.txt"]
	proveedor.cerrar()


def test_escrituras_sueltas_renombrar_y_eliminar(tmp_path, local):
	ruta = tmp_path / "x.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("sub/a.txt", "a")
		archivo.writestr("b.txt", "b")
	proveedor = ProveedorZip(local, str(ruta))
	proveedor.crear_carpeta("nueva/dentro")
	proveedor.renombrar("sub", "otra")
	with pytest.raises(base.YaExiste):
		proveedor.renombrar("b.txt", "otra")
	with pytest.raises(base.NombreNoValido):
		proveedor.crear_carpeta("con:dos")
	with pytest.raises(base.ErrorAcceso):
		proveedor.eliminar("otra")
	_lanzar(OperacionEliminar(proveedor, [proveedor.info("b.txt")], papelera=False))
	with zipfile.ZipFile(ruta) as archivo:
		assert sorted(archivo.namelist()) == ["nueva/", "nueva/dentro/", "otra/", "otra/a.txt"]
		assert archivo.read("otra/a.txt") == b"a"
	proveedor.cerrar()


def test_extraer_cada_uno_en_su_carpeta_con_marca_de_la_web(tmp_path, local):
	from app.services.windows import marca_web

	for nombre in ("uno", "dos"):
		with zipfile.ZipFile(tmp_path / f"{nombre}.zip", "w") as archivo:
			archivo.writestr("leeme.txt", nombre)
	marcado = marca_web.escribir(str(tmp_path / "uno.zip"), marca_web.INTERNET)
	destino = tmp_path / "salida"
	destino.mkdir()
	entradas = [local.info(str(tmp_path / "uno.zip")), local.info(str(tmp_path / "dos.zip"))]
	operacion = _lanzar(OperacionExtraer(local, entradas, local, str(destino), OpcionesCopia(politica=Politica.SOBRESCRIBIR),
		por_carpeta=True))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert (destino / "uno" / "leeme.txt").read_text(encoding="utf-8") == "uno"
	assert (destino / "dos" / "leeme.txt").read_text(encoding="utf-8") == "dos"
	if marcado:
		# marca_web.leer abre en modo texto y convierte CRLF en LF: se compara el contenido.
		assert "ZoneId=3" in (marca_web.leer(str(destino / "uno" / "leeme.txt")) or "")
		assert marca_web.leer(str(destino / "dos" / "leeme.txt")) is None


def test_comprimir_zip_y_anadir(tmp_path, local):
	origen = tmp_path / "proyecto"
	(origen / "src").mkdir(parents=True)
	(origen / "src" / "a.py").write_bytes(b"print(1)\n" * 50)
	(origen / "vacia").mkdir()
	(origen / "leeme.txt").write_text("hola", encoding="utf-8")
	destino = tmp_path / "copia.zip"
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(origen))], str(destino), OpcionesComprimir(nivel="maximo")))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	with zipfile.ZipFile(destino) as archivo:
		assert archivo.testzip() is None
		assert sorted(archivo.namelist()) == ["proyecto/", "proyecto/leeme.txt", "proyecto/src/", "proyecto/src/a.py",
			"proyecto/vacia/"]
	nuevo = tmp_path / "nuevo.txt"
	nuevo.write_text("añadido", encoding="utf-8")
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(nuevo))], str(destino), OpcionesComprimir(anadir=True)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	with zipfile.ZipFile(destino) as archivo:
		assert archivo.read("nuevo.txt").decode("utf-8") == "añadido"
		assert archivo.read("proyecto/src/a.py") == b"print(1)\n" * 50
	prueba = _lanzar(OperacionProbar(local, [str(destino)]))
	assert prueba.estado == Estado.TERMINADA
	assert "correcto" in prueba.resumen()


def test_mover_al_comprimido_borra_tras_probar(tmp_path, local):
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "a.txt").write_text("a", encoding="utf-8")
	(origen / "b.txt").write_text("b", encoding="utf-8")
	entradas = local.listar(str(origen))
	destino = tmp_path / "todo.zip"
	operacion = _lanzar(OperacionComprimir(local, entradas, str(destino), OpcionesComprimir(mover=True)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert operacion.originales_borrados
	assert os.listdir(origen) == []
	with zipfile.ZipFile(destino) as archivo:
		assert sorted(archivo.namelist()) == ["a.txt", "b.txt"]


def test_probar_detecta_un_zip_danado(tmp_path, local):
	ruta = tmp_path / "danado.zip"
	with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as archivo:
		archivo.writestr("a.txt", "AAAAAAAAAAAAAAAAAAAA")
		archivo.writestr("b.txt", "bien")
	datos = ruta.read_bytes()
	ruta.write_bytes(datos.replace(b"AAAAAAAAAAAAAAAAAAAA", b"AAAAAAAAAABAAAAAAAAA"))
	operacion = _lanzar(OperacionProbar(local, [str(ruta)]))
	assert operacion.estado == Estado.TERMINADA_CON_ERRORES
	assert len(operacion.errores) == 1 and "a.txt" in operacion.errores[0].ruta
	assert "1 error" in operacion.resumen()


def test_cancelar_la_copia_al_zip_no_escribe_nada(tmp_path, local):
	ruta = tmp_path / "x.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("a.txt", "a")
	antes = ruta.read_bytes()
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "grande.bin").write_bytes(os.urandom(256 * 1024))
	proveedor = ProveedorZip(local, str(ruta))

	class Cancelador(DecisorFalso):
		pass

	operacion = OperacionCopiar(local, local.listar(str(origen)), proveedor, "", OpcionesCopia(tamano_bloque=64 * 1024))
	original = operacion.progresar

	def progresar(**cambios):
		original(**cambios)
		if cambios.get("bytes_actual", 0) > 0:
			operacion.cancelar()

	operacion.progresar = progresar
	_lanzar(operacion, Cancelador())
	assert operacion.estado == Estado.CANCELADA
	assert ruta.read_bytes() == antes
	proveedor.cerrar()


def test_copia_cruda_conserva_miembros_y_quitar_extra():
	extra = b"\x01\x00\x04\x00abcd" + b"\x0a\x00\x02\x00xy"
	assert modulo_zip._quitar_extra(extra, 0x0001) == b"\x0a\x00\x02\x00xy"
	assert modulo_zip.fecha_zip(0)[0] >= 2024
	assert modulo_zip.fecha_zip(315532800 - 86400 * 400)[0] == 1980


def test_lector_abierto_no_impide_reconstruir(tmp_path, local):
	"""El panel acaba de leer un miembro (el ZIP sigue abierto unos segundos) y otra operación lo modifica."""
	ruta = tmp_path / "x.zip"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr("a.txt", "a")
	panel = ProveedorZip(local, str(ruta))
	with panel.abrir_lectura("a.txt") as flujo:
		assert flujo.read() == b"a"
	clon = panel.clonar()
	assert clon is not panel
	clon.crear_carpeta("nueva")
	assert sorted(e.nombre for e in panel.listar("")) == ["a.txt", "nueva"]
	with panel.abrir_lectura("a.txt") as flujo:
		assert flujo.read() == b"a"
	clon.cerrar()
	panel.cerrar()


def test_ocioso_cierra_tras_un_rato_sin_uso():
	import time

	cerrados: list[object] = []
	abierto = modulo_zip.Ocioso(object, cerrados.append, segundos=0.2)
	for _ in range(4):
		with abierto.usar():
			pass
		time.sleep(0.08)
	assert cerrados == []
	time.sleep(0.5)
	assert len(cerrados) == 1
