# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque CM: crear comprimidos con los formatos nuevos de 8.1 y 8.6 (Python, libarchive y 7za), y leerlos después."""

from __future__ import annotations

import tarfile
import zipfile

import pytest

from app.core import procesos
from app.services import comprimir, siete_zip_externo
from app.services.operaciones.comprimir import OpcionesComprimir, OperacionComprimir, OperacionProbar
from app.services.operaciones.modelo import Estado
from app.services.vfs import base, resolver
from app.services.vfs.zip import ProveedorZip
from app.services.vfs.local import ProveedorLocal
from tests.servicios.cm_comun import (  # noqa: F401 - fixtures
	DATOS,
	TEXTO,
	ConfigFalsa,
	DecisorConClave,
	abrir,
	fijar,
	recursos_reales,
	servicios_cm,
	todo,
)
from tests.servicios.test_c_zip import _lanzar


@pytest.fixture
def local():
	return ProveedorLocal()


pytestmark = [pytest.mark.componentes, pytest.mark.usefixtures("recursos_reales", "servicios_cm")]

ESPERADO = {"src/música ñ.bin": DATOS, "src/sub/léeme.txt": TEXTO, "src/vacío.txt": b""}


def _origen(tmp_path):
	origen = tmp_path / "src"
	(origen / "sub").mkdir(parents=True)
	(origen / "música ñ.bin").write_bytes(DATOS)
	(origen / "sub" / "léeme.txt").write_bytes(TEXTO)
	(origen / "vacío.txt").write_bytes(b"")
	return origen


def _comprimir(local, tmp_path, destino, **opciones):
	origen = _origen(tmp_path)
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(origen))], str(destino), OpcionesComprimir(**opciones)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	return destino


@pytest.fixture
def sin_7za(monkeypatch):
	monkeypatch.setattr(siete_zip_externo, "ruta_7za", lambda: None)


# ── Python ───────────────────────────────────────────────────────────────────


def test_tar_zst_se_crea_y_se_lee_con_python(tmp_path, local):
	destino = _comprimir(local, tmp_path, tmp_path / "copia.tar.zst", formato="tar.zst", nivel="maximo")
	with tarfile.open(destino, "r:zst") as tar:
		assert tar.extractfile("src/sub/léeme.txt").read() == TEXTO
	proveedor = abrir(destino)
	assert type(proveedor).__name__ == "ProveedorTar"
	assert todo(proveedor) == ESPERADO


def test_zst_suelto_se_crea_por_elemento_y_se_lee(tmp_path, local):
	origen = _origen(tmp_path)
	carpeta = tmp_path / "salida"
	carpeta.mkdir()
	entradas = [local.info(str(origen / "música ñ.bin")), local.info(str(origen / "sub")), local.info(str(origen / "vacío.txt"))]
	operacion = _lanzar(OperacionComprimir(local, entradas, str(carpeta), OpcionesComprimir(formato="zst", por_elemento=True)))
	# La carpeta no se puede comprimir en .zst: se avisa y lo demás se hace.
	assert len(operacion.errores) == 1 and "carpeta" in operacion.errores[0].mensaje
	assert sorted(p.name for p in carpeta.iterdir()) == ["música ñ.bin.zst", "vacío.txt.zst"]
	from compression import zstd

	assert zstd.decompress((carpeta / "música ñ.bin.zst").read_bytes()) == DATOS
	assert todo(abrir(carpeta / "música ñ.bin.zst")) == {"música ñ.bin": DATOS}


@pytest.mark.parametrize("formato", ["gz", "bz2", "xz"])
def test_flujos_de_python_ida_y_vuelta(tmp_path, local, formato):
	origen = _origen(tmp_path)
	destino = tmp_path / f"léeme.txt.{formato}"
	operacion = _lanzar(OperacionComprimir(local, [local.info(str(origen / "sub" / "léeme.txt"))], str(destino),
		OpcionesComprimir(formato=formato)))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert todo(abrir(destino)) == {"léeme.txt": TEXTO}


def test_zip_con_zstandard_metodo_93(tmp_path, local):
	destino = _comprimir(local, tmp_path, tmp_path / "copia.zip", formato="zip", variante="zstd")
	with zipfile.ZipFile(destino) as archivo:
		metodos = {i.filename: i.compress_type for i in archivo.infolist() if not i.is_dir()}
	assert set(metodos.values()) == {zipfile.ZIP_ZSTANDARD}
	assert todo(abrir(destino)) == ESPERADO
	# Añadir dentro del ZIP (transacción) con el método de Preferencias.
	proveedor = ProveedorZip(local, str(destino))
	proveedor.metodo = "zstd"
	with proveedor.transaccion(), proveedor.abrir_escritura("nuevo.txt") as salida:
		salida.write(b"nuevo")
	proveedor.cerrar()
	with zipfile.ZipFile(destino) as archivo:
		assert archivo.getinfo("nuevo.txt").compress_type == zipfile.ZIP_ZSTANDARD
		assert archivo.read("nuevo.txt") == b"nuevo"


def test_metodo_zip_de_preferencias(tmp_path, local, monkeypatch):
	fijar(monkeypatch, config=ConfigFalsa(comprimidos__metodo_zip="zstd"))
	destino = _comprimir(local, tmp_path, tmp_path / "copia.zip", formato="zip")
	with zipfile.ZipFile(destino) as archivo:
		assert archivo.getinfo("src/sub/léeme.txt").compress_type == zipfile.ZIP_ZSTANDARD


# ── libarchive ───────────────────────────────────────────────────────────────


def test_zip_aes256_con_libarchive_y_leerlo_con_la_contrasena(tmp_path, local, monkeypatch, sin_7za):
	assert comprimir.motor("zip", "aes").startswith("libarchive 3.8")
	destino = _comprimir(local, tmp_path, tmp_path / "cifrado.zip", formato="zip", variante="aes", contrasena="clave ñ")
	with zipfile.ZipFile(destino) as archivo:
		cifrados = [i for i in archivo.infolist() if not i.is_dir() and i.file_size]
	# 99 = AES de WinZip (libarchive no cifra los archivos vacíos: no hay nada que proteger).
	assert len(cifrados) == 2 and all(i.flag_bits & 0x1 and i.compress_type == 99 for i in cifrados)
	fijar(monkeypatch, DecisorConClave(["clave ñ"]))
	assert todo(abrir(destino)) == ESPERADO
	prueba = _lanzar(OperacionProbar(local, [str(destino)], contrasena="clave ñ"))
	assert prueba.estado == Estado.TERMINADA and not prueba.errores


@pytest.mark.parametrize("formato", ["iso", "cpio", "xar", "tar.lz", "tar.lz4"])
def test_formatos_de_libarchive_se_crean_y_se_leen(tmp_path, local, formato):
	assert comprimir.motor(formato).startswith("libarchive")
	destino = _comprimir(local, tmp_path, tmp_path / f"copia.{formato}", formato=formato)
	proveedor = abrir(destino)
	assert type(proveedor).__name__ == "ProveedorLibarchive"
	assert todo(proveedor) == ESPERADO


def test_iso_no_deja_temporales_fuera_de_data(tmp_path, local, monkeypatch):
	import os

	visto = {}
	from app.services.libarchive import escritura

	original = escritura.EscritorArchive._abrir

	def espiar(self, *args):
		visto["tmp"] = os.environ.get("TMP")
		original(self, *args)

	monkeypatch.setattr(escritura.EscritorArchive, "_abrir", espiar)
	antes = os.environ.get("TMP")
	_comprimir(local, tmp_path, tmp_path / "copia.iso", formato="iso")
	from app.services.vfs import temporales

	assert visto["tmp"] == str(temporales.carpeta_temporal())
	assert os.environ.get("TMP") == antes


def test_formatos_ofrecidos():
	claves = [c for c, _t in comprimir.textos_formatos()]
	assert claves[:6] == ["zip", "7z", "tar", "tar.gz", "tar.bz2", "tar.xz"]
	for clave in ("zip:zstd", "zip:aes", "tar.zst", "tar.lz4", "tar.lz", "iso", "cpio", "xar", "gz", "bz2", "xz", "zst"):
		assert clave in claves
	con_carpetas = [c for c, _t in comprimir.textos_formatos(hay_carpetas=True)]
	assert "gz" not in con_carpetas and "zst" not in con_carpetas
	assert comprimir.formato_de("a.tar.zst") == "tar.zst" and comprimir.formato_de("b.txt.gz") == "gz"
	assert comprimir.formato_de("c.tar.gz") == "tar.gz"
	assert comprimir.quitar_extension_comprimido("copia.tar.lz4") == "copia"
	assert comprimir.admite_contrasena("zip", "aes") and not comprimir.admite_contrasena("zip", "zstd")
	with pytest.raises(base.NoAdmitido):
		comprimir.crear_escritor("zip", "x.zip", contrasena="clave", variante="zstd")


# ── 7za ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def argumentos_7za(monkeypatch):
	"""Anota los argumentos y la entrada de cada llamada a 7za (y la deja seguir de verdad)."""
	llamadas = []
	original = procesos.lanzar

	def espiar(argumentos, **opciones):
		llamadas.append((list(argumentos), opciones.get("entrada", b"")))
		return original(argumentos, **opciones)

	monkeypatch.setattr(procesos, "lanzar", espiar)
	if siete_zip_externo.ruta_7za() is None:
		pytest.skip("Falta data/bin/7za/7za.exe")
	return llamadas


def test_7za_crea_un_7z_con_contrasena_por_la_entrada_estandar(tmp_path, local, argumentos_7za, monkeypatch):
	assert comprimir.motor("7z").startswith("7za 26")
	destino = _comprimir(local, tmp_path, tmp_path / "secreto.7z", formato="7z", contrasena="clave €", cifrar_nombres=True)
	creacion = [(a, e) for a, e in argumentos_7za if a[1] == "a"]
	assert len(creacion) == 1
	argumentos, entrada = creacion[0]
	assert "-p" in argumentos and "-mhe=on" in argumentos
	assert not any("clave" in a for a in argumentos)
	assert entrada == "clave €\r\n".encode()
	# Con los nombres cifrados, py7zr pide la contraseña ya para listar.
	fijar(monkeypatch, DecisorConClave(["clave €"]))
	assert todo(abrir(destino)) == ESPERADO


def test_7za_sin_contrasena_no_lleva_p(tmp_path, local, argumentos_7za):
	destino = _comprimir(local, tmp_path, tmp_path / "libre.7z", formato="7z", nivel="rapido")
	argumentos, entrada = next((a, e) for a, e in argumentos_7za if a[1] == "a")
	assert not any(a.startswith("-p") for a in argumentos)
	assert entrada == b""
	assert "-mx1" in argumentos and "-mmt=on" in argumentos and "-spd" in argumentos and "--" in argumentos
	assert todo(abrir(destino)) == ESPERADO


def test_7za_zip_aes_y_lectura_con_libarchive(tmp_path, local, argumentos_7za, monkeypatch):
	assert comprimir.motor("zip", "aes").startswith("7za")
	destino = _comprimir(local, tmp_path, tmp_path / "cifrado.zip", formato="zip", variante="aes", contrasena="clave")
	argumentos, entrada = next((a, e) for a, e in argumentos_7za if a[1] == "a")
	assert "-mem=AES256" in argumentos and entrada == b"clave\r\n"
	fijar(monkeypatch, DecisorConClave(["clave"]))
	assert todo(abrir(destino)) == ESPERADO


def test_7za_comprime_desde_otro_comprimido(tmp_path, local):
	if siete_zip_externo.ruta_7za() is None:
		pytest.skip("Falta 7za")
	# Lo que no está en el disco (un ZIP) se prepara en data/temp con su nombre y 7za lo comprime.
	zip_origen = _comprimir(local, tmp_path, tmp_path / "origen.zip", formato="zip")
	proveedor = abrir(zip_origen)
	operacion = _lanzar(OperacionComprimir(proveedor, proveedor.listar(""), str(tmp_path / "desde_zip.7z"),
		OpcionesComprimir(formato="7z")))
	assert operacion.estado == Estado.TERMINADA, operacion.errores
	assert todo(abrir(tmp_path / "desde_zip.7z")) == ESPERADO
	from app.services.vfs import temporales

	assert not [p for p in temporales.carpeta_temporal().iterdir() if p.name.startswith("7za-")]


def test_7za_cancelado_no_deja_el_comprimido(tmp_path, local):
	if siete_zip_externo.ruta_7za() is None:
		pytest.skip("Falta 7za")
	escritor = comprimir.crear_escritor("7z", str(tmp_path / "x.tmp"))
	origen = _origen(tmp_path)
	for fuente in comprimir.reunir(local, [local.info(str(origen))]):
		escritor.agregar(fuente)
	cancelacion = base.Cancelacion()
	cancelacion.cancelar()
	with pytest.raises(base.Cancelado):
		escritor.cerrar(cancelacion)
	escritor.descartar()
	assert not (tmp_path / "x.tmp").exists()


def test_resolver_conoce_los_formatos_nuevos():
	for nombre in ("a.tar.zst", "a.tzst", "a.rar", "a.iso", "a.cab", "a.txt.gz", "a.zst", "a.lz4", "a.deb", "a.rpm", "a.zipx"):
		assert resolver.es_comprimido(nombre), nombre
