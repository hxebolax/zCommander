# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque CM: proveedor libarchive (diseño 2.0, 8.2 y 18.2), con comprimidos reales creados en la prueba.

RAR no se puede crear con ninguna herramienta libre: ``cm_muestras`` escribe a
mano RAR 5 y RAR 4 sin compresión con datos binarios conocidos (también un
RAR 5 cifrado y un multivolumen). La descompresión RAR de verdad (PPMd, LZSS,
filtros) no se prueba aquí: no hay muestras comprimidas en el repositorio.
"""

from __future__ import annotations

import gzip
import io
import lzma
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from app.services.libarchive import ffi, lectura, prueba
from app.services.operaciones.comprimir import OperacionExtraer, OperacionProbar
from app.services.operaciones.modelo import Estado
from app.services.vfs import base, resolver
from app.services.vfs.libarchive import ProveedorLibarchive, partes_de, rar_solido
from app.services.vfs.local import ProveedorLocal
from tests.servicios import cm_muestras as muestras
from tests.servicios.cm_comun import (  # noqa: F401 - fixtures
	DATOS,
	TEXTO,
	ConfigFalsa,
	DecisorConClave,
	abrir,
	escribir_libarchive,
	recursos_reales,
	fijar,
	servicios_cm,
	todo,
)
from tests.servicios.test_c_zip import _lanzar


@pytest.fixture
def local():
	return ProveedorLocal()


pytestmark = [pytest.mark.componentes, pytest.mark.usefixtures("recursos_reales", "servicios_cm")]

MIEMBROS = [("carpeta", None), ("carpeta/música ñ.bin", DATOS), ("léeme.txt", TEXTO)]
ESPERADO = {"carpeta/música ñ.bin": DATOS, "léeme.txt": TEXTO}


# ── Cada formato de 8.1 se lista y se extrae ──────────────────────────────────


def test_rar5_se_lista_y_extrae_y_omite_rutas_peligrosas(tmp_path):
	ruta = muestras.rar5(tmp_path / "datos.rar", [*MIEMBROS, ("../fuera.txt", b"malo"), ("C:/Windows/x.txt", b"malo")])
	proveedor = abrir(ruta)
	assert isinstance(proveedor, ProveedorLibarchive)
	assert [e.nombre for e in proveedor.listar("")] == ["carpeta", "léeme.txt"]
	assert proveedor.info("carpeta/música ñ.bin").tamano == len(DATOS)
	assert todo(proveedor) == ESPERADO
	assert sorted(proveedor.omitidas) == ["../fuera.txt", "C:/Windows/x.txt"]
	assert proveedor.descripcion() == "Archivo RAR"
	proveedor.cerrar()


def test_rar4_se_lista_y_extrae(tmp_path):
	ruta = muestras.rar4(tmp_path / "viejo.rar", [("dir/a.txt", b"hola rar4"), ("b.bin", DATOS)])
	proveedor = abrir(ruta)
	assert todo(proveedor) == {"dir/a.txt": b"hola rar4", "b.bin": DATOS}
	proveedor.cerrar()


def test_rar_solido_se_detecta_y_guarda_los_anteriores_de_paso(tmp_path):
	miembros = [(f"f{i}.bin", bytes([i]) * 5000) for i in range(6)]
	solido = muestras.rar5(tmp_path / "solido.rar", miembros, solido=True)
	normal = muestras.rar5(tmp_path / "normal.rar", miembros)
	assert rar_solido(str(solido)) and not rar_solido(str(normal))
	assert rar_solido(str(muestras.rar4(tmp_path / "v4.rar", [("a", b"1")]))) is False
	proveedor = abrir(solido)
	# Se pide el último: los anteriores quedan guardados y no se vuelve a empezar.
	with proveedor.abrir_lectura("f5.bin") as flujo:
		assert flujo.read() == bytes([5]) * 5000
	assert len(proveedor._previos) == 5
	for i in range(5):
		with proveedor.abrir_lectura(f"f{i}.bin") as flujo:
			assert flujo.read() == bytes([i]) * 5000
	assert proveedor._previos == {}
	proveedor.cerrar()


def test_lectura_en_orden_reutiliza_el_cursor(tmp_path, monkeypatch):
	ruta = muestras.rar5(tmp_path / "orden.rar", [(f"f{i}.bin", bytes([i]) * 100) for i in range(5)])
	aperturas = []
	original = lectura.Lector.__init__

	def contar(self, *args, **kwargs):
		aperturas.append(1)
		original(self, *args, **kwargs)

	monkeypatch.setattr(lectura.Lector, "__init__", contar)
	proveedor = abrir(ruta)
	proveedor.indice()
	antes = len(aperturas)
	assert todo(proveedor) == {f"f{i}.bin": bytes([i]) * 100 for i in range(5)}
	assert len(aperturas) - antes == 1
	proveedor.cerrar()


def test_lha_rpm_y_cab(tmp_path):
	lha = muestras.lha(tmp_path / "a.lzh", [("dir/a.txt", b"hola lha"), ("b.bin", DATOS)])
	assert todo(abrir(lha)) == {"dir/a.txt": b"hola lha", "b.bin": DATOS}
	rpm = muestras.rpm(tmp_path / "paquete.rpm", [("./usr/share/a.txt", b"hola rpm")])
	assert todo(abrir(rpm)) == {"usr/share/a.txt": b"hola rpm"}
	(tmp_path / "datos.bin").write_bytes(DATOS)
	cab = muestras.cab(tmp_path / "datos.cab", tmp_path / "datos.bin")
	if cab is None:
		pytest.skip("Sin makecab.exe para crear el CAB")
	proveedor = abrir(cab)
	assert proveedor.descripcion() == "Archivo CAB"
	assert todo(proveedor) == {"datos.bin": DATOS}


@pytest.mark.parametrize(("nombre", "funcion", "filtro"), [
	("imagen.iso", "archive_write_set_format_iso9660", None),
	("datos.cpio", "archive_write_set_format_cpio_newc", None),
	("datos.xar", "archive_write_set_format_xar", None),
	("datos.pkg", "archive_write_set_format_xar", None),
	("datos.tar.lz", "archive_write_set_format_pax_restricted", "archive_write_add_filter_lzip"),
	("datos.tar.lz4", "archive_write_set_format_pax_restricted", "archive_write_add_filter_lz4"),
	("datos.tar.lzma", "archive_write_set_format_pax_restricted", "archive_write_add_filter_lzma"),
	("datos.tlz", "archive_write_set_format_pax_restricted", "archive_write_add_filter_lzip"),
	("datos.tar.Z", "archive_write_set_format_pax_restricted", "archive_write_add_filter_compress"),
])
def test_formatos_escritos_con_libarchive_se_leen(tmp_path, nombre, funcion, filtro):
	ruta = escribir_libarchive(tmp_path / nombre, funcion, MIEMBROS, filtro)
	proveedor = abrir(ruta)
	assert isinstance(proveedor, ProveedorLibarchive)
	assert todo(proveedor) == ESPERADO
	assert proveedor.probar().correcto
	proveedor.cerrar()


def test_deb_ar_y_warc(tmp_path):
	# Un .deb es un ar con «debian-binary» y dos tar dentro: se ven los tres miembros.
	control = io.BytesIO()
	with tarfile.open(fileobj=control, mode="w:gz") as tar:
		informacion = tarfile.TarInfo("control")
		informacion.size = 4
		tar.addfile(informacion, io.BytesIO(b"Pkg\n"))
	deb = escribir_libarchive(tmp_path / "paquete.deb", "archive_write_set_format_ar_svr4",
		[("debian-binary", b"2.0\n"), ("control.tar.gz", control.getvalue())])
	contenido = todo(abrir(deb))
	assert contenido["debian-binary"] == b"2.0\n" and "control.tar.gz" in contenido
	warc = escribir_libarchive(tmp_path / "web.warc", "archive_write_set_format_warc", [("http://ejemplo/a.txt", b"hola warc")])
	assert b"hola warc" in b"".join(todo(abrir(warc)).values())


def test_zipx_con_lzma_y_bzip2(tmp_path):
	ruta = tmp_path / "datos.zipx"
	with zipfile.ZipFile(ruta, "w") as archivo:
		archivo.writestr(zipfile.ZipInfo("lzma.bin"), DATOS, compress_type=zipfile.ZIP_LZMA)
		archivo.writestr(zipfile.ZipInfo("bzip2.txt"), TEXTO, compress_type=zipfile.ZIP_BZIP2)
	assert todo(abrir(ruta)) == {"lzma.bin": DATOS, "bzip2.txt": TEXTO}


def test_zip_aes_se_lee_desde_el_proveedor_zip_con_libarchive(tmp_path, monkeypatch):
	from app.services.libarchive import escritura

	ruta = tmp_path / "cifrado.zip"
	escritor = escritura.EscritorArchive(str(ruta), "zip", "normal", "secreta")
	escritor.carpeta("carpeta")
	for nombre, datos in ESPERADO.items():
		escritor.archivo(nombre, len(datos), 1_700_000_000, io.BytesIO(datos))
	escritor.cerrar()
	decisor = fijar(monkeypatch, DecisorConClave(["mala", "secreta"]))
	proveedor = abrir(ruta)
	assert type(proveedor).__name__ == "ProveedorZip"
	assert todo(proveedor) == ESPERADO
	assert len(decisor.textos) == 2 and "no es correcta" in decisor.textos[1]
	proveedor.cerrar()


def test_flujos_sueltos_de_libarchive(tmp_path):
	for extension, filtro in (("lz", "archive_write_add_filter_lzip"), ("lz4", "archive_write_add_filter_lz4"),
			("Z", "archive_write_add_filter_compress")):
		ruta = escribir_libarchive(tmp_path / f"informe.pdf.{extension}", "archive_write_set_format_raw",
			[("informe.pdf", DATOS)], filtro)
		proveedor = abrir(ruta)
		assert [e.nombre for e in proveedor.listar("")] == ["informe.pdf"]
		assert proveedor.info("informe.pdf").tamano == -1
		assert todo(proveedor) == {"informe.pdf": DATOS}


def test_flujos_sueltos_de_python(tmp_path):
	(tmp_path / "nombre.txt.gz").write_bytes(gzip.compress(TEXTO))
	proveedor = abrir(tmp_path / "nombre.txt.gz")
	assert [e.nombre for e in proveedor.listar("")] == ["nombre.txt"]
	assert proveedor.info("nombre.txt").tamano == len(TEXTO)
	assert todo(proveedor) == {"nombre.txt": TEXTO}
	(tmp_path / ".xz").write_bytes(lzma.compress(DATOS))
	assert todo(abrir(tmp_path / ".xz")) == {"contenido": DATOS}
	(tmp_path / "datos.lzma").write_bytes(lzma.compress(DATOS, format=lzma.FORMAT_ALONE))
	assert todo(abrir(tmp_path / "datos.lzma")) == {"datos": DATOS}
	(tmp_path / "falso.gz").write_bytes(b"esto no es gzip")
	with pytest.raises(base.ErrorArchivos):
		abrir(tmp_path / "falso.gz").listar("")


def test_flujos_como_carpeta_desactivado_abre_con_su_programa(tmp_path, monkeypatch):
	fijar(monkeypatch, config=ConfigFalsa(comprimidos__flujos_como_carpeta=False))
	(tmp_path / "a.txt.gz").write_bytes(gzip.compress(b"x"))
	with pytest.raises(base.NoAdmitido):
		abrir(tmp_path / "a.txt.gz")


# ── Cifrado ──────────────────────────────────────────────────────────────────


def test_rar_cifrado_sin_7zip_da_el_mensaje_de_8_2(tmp_path, monkeypatch):
	from app.services.sonidos import servicio
	from app.services.vfs import siete_zip_instalado

	sonidos = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, variante="", **_k: sonidos.append(evento) or True)
	monkeypatch.setattr(siete_zip_instalado, "motor_lectura", lambda formato: None)
	ruta = muestras.rar5(tmp_path / "secreto.rar", [("libre.txt", b"uno"), ("secreto.txt", b"0123456789")],
		cifrados={"secreto.txt"})
	proveedor = abrir(ruta)
	with proveedor.abrir_lectura("libre.txt") as flujo:
		assert flujo.read() == b"uno"
	with pytest.raises(base.ErrorAcceso) as error:
		proveedor.abrir_lectura("secreto.txt")
	assert error.value.mensaje == "Este RAR está cifrado. zCommander no puede descifrarlo sin 7-Zip instalado."
	assert "incorrecta" not in error.value.mensaje
	assert sonidos == ["comprimido.cifrado_sin_motor"]


def test_rar_cifrado_con_7zip_pasa_a_la_reserva(tmp_path, monkeypatch):
	from app.services.vfs import siete_zip_instalado

	usados = []

	class Reserva(siete_zip_instalado.ProveedorSieteZipExterno):
		def abrir_lectura(self, ruta):
			usados.append(ruta)
			return io.BytesIO(b"descifrado")

	monkeypatch.setattr(siete_zip_instalado, "motor_lectura", lambda formato: "C:\\7-Zip\\7z.exe")
	monkeypatch.setattr(siete_zip_instalado, "ProveedorSieteZipExterno", Reserva)
	ruta = muestras.rar5(tmp_path / "secreto.rar", [("secreto.txt", b"0123456789")], cifrados={"secreto.txt"})
	proveedor = abrir(ruta)
	assert proveedor.abrir_lectura("secreto.txt").read() == b"descifrado"
	assert usados == ["secreto.txt"]


# ── Multivolumen ─────────────────────────────────────────────────────────────


def test_rar_multivolumen_con_nombre_no_ascii_desde_la_primera_parte(tmp_path):
	partes = muestras.rar5_multivolumen(tmp_path, "música ñ", "canción €.bin", DATOS, extra=("primero.txt", b"primero"))
	assert partes_de(str(partes[1])) == [str(p) for p in partes]
	for parte in partes:
		proveedor = abrir(parte)
		assert todo(proveedor) == {"primero.txt": b"primero", "canción €.bin": DATOS}
		proveedor.cerrar()


def test_rar_antiguo_r00_abre_el_conjunto(tmp_path):
	(tmp_path / "copia.rar").write_bytes(b"x")
	(tmp_path / "copia.r00").write_bytes(b"x")
	(tmp_path / "copia.r01").write_bytes(b"x")
	esperado = [str(tmp_path / n) for n in ("copia.rar", "copia.r00", "copia.r01")]
	assert partes_de(str(tmp_path / "copia.r01")) == esperado
	assert partes_de(str(tmp_path / "copia.rar")) == esperado
	assert resolver.extension_comprimido("copia.r00") == "r00"


def test_multivolumen_registrado_porque_la_dll_lo_exporta():
	assert ffi.tiene(ffi.FUNCION_MULTIVOLUMEN)
	assert resolver.es_comprimido("x.r00")


# ── Operaciones, panel y prueba del componente ───────────────────────────────


def test_extraer_y_probar_con_las_operaciones(tmp_path, local):
	ruta = muestras.rar5(tmp_path / "datos.rar", MIEMBROS)
	destino = tmp_path / "destino"
	destino.mkdir()
	operacion = _lanzar(OperacionExtraer(local, [local.info(str(ruta))], local, str(destino)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert (destino / "carpeta" / "música ñ.bin").read_bytes() == DATOS
	assert (destino / "léeme.txt").read_bytes() == TEXTO
	probar = _lanzar(OperacionProbar(local, [str(ruta)]))
	assert probar.estado == Estado.TERMINADA and not probar.errores


def test_probar_detecta_datos_danados(tmp_path):
	# LHA guarda un CRC-16 de cada archivo que libarchive comprueba al leer.
	ruta = muestras.lha(tmp_path / "danado.lzh", [("a.bin", DATOS), ("b.txt", TEXTO)])
	contenido = bytearray(ruta.read_bytes())
	contenido[200] ^= 0xFF
	ruta.write_bytes(bytes(contenido))
	resultado = abrir(ruta).probar()
	assert not resultado.correcto
	assert resultado.errores[0][0] == "a.bin"


@pytest.mark.parametrize("nombre", ["datos.rar", "imagen.iso", "datos.cab"])
def test_entrar_desde_el_panel(tmp_path, nombre):
	from app.ui.acciones import navegacion

	if nombre.endswith(".rar"):
		ruta = muestras.rar5(tmp_path / nombre, MIEMBROS)
	elif nombre.endswith(".iso"):
		ruta = escribir_libarchive(tmp_path / nombre, "archive_write_set_format_iso9660", MIEMBROS)
	else:
		(tmp_path / "léeme.txt").write_bytes(TEXTO)
		ruta = muestras.cab(tmp_path / nombre, tmp_path / "léeme.txt")
		if ruta is None:
			pytest.skip("Sin makecab.exe")
	local = resolver.proveedor_local()
	destinos = []
	panel = SimpleNamespace(proveedor=local, ir_a=lambda ruta_, proveedor: destinos.append((ruta_, proveedor)))
	navegacion._entrar_en_comprimido(SimpleNamespace(), panel, local.info(str(ruta)))
	assert len(destinos) == 1 and destinos[0][0] == ""
	assert "léeme.txt" in [e.nombre for e in destinos[0][1].listar("")]
	destinos[0][1].cerrar()


def test_probar_componente_libarchive(tmp_path):
	assert prueba.probar(None) == 0
	assert prueba.probar(tmp_path / "vacia") == 1
	from app.services.componentes import prueba as prueba_componentes

	assert prueba_componentes.probar_componente("libarchive", None) == 0


def test_error_de_un_archivo_que_no_es_comprimido(tmp_path):
	(tmp_path / "falso.rar").write_bytes(b"esto no es un rar" * 10)
	with pytest.raises(base.ErrorArchivos) as error:
		abrir(tmp_path / "falso.rar").listar("")
	assert "no es un comprimido válido" in error.value.mensaje
