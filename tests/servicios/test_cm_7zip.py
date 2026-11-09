# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque CM: 7z con métodos que py7zr no admite (reserva con libarchive o 7za) y el 7-Zip de la persona (8.1, 8.4 y 8.5)."""

from __future__ import annotations

import shutil

import pytest

from app.services import siete_zip_externo
from app.services.operaciones.comprimir import OperacionProbar
from app.services.operaciones.modelo import Estado
from app.services.vfs import base, siete_zip_instalado
from app.services.vfs.libarchive import ProveedorLibarchive
from app.services.vfs.siete_z import ProveedorSieteZ
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


@pytest.fixture
def siete_za():
	ruta = siete_zip_externo.ruta_7za()
	if ruta is None:
		pytest.skip("Falta data/bin/7za/7za.exe")
	return ruta


def _bcj2(tmp_path, siete_za, contrasena=None):
	"""7z con el filtro BCJ2 (el de los .exe), que py7zr 0.11.3 no sabe descomprimir."""
	origen = tmp_path / "origen"
	origen.mkdir()
	(origen / "programa.exe").write_bytes(siete_za.read_bytes()[:40000])
	(origen / "léeme.txt").write_bytes(TEXTO)
	destino = tmp_path / "bcj2.7z"
	interruptores = ["-t7z", "-mf=BCJ2", "-bso0", "-bsp0"]
	if contrasena:
		interruptores.append("-mhe=off")
	siete_zip_externo.ejecutar(siete_za, "a", interruptores, str(destino), [str(origen / "programa.exe"), str(origen / "léeme.txt")],
		contrasena=contrasena)
	return destino, {"programa.exe": siete_za.read_bytes()[:40000], "léeme.txt": TEXTO}


def test_7z_bcj2_sin_cifrar_se_lee_con_libarchive(tmp_path, siete_za, local):
	ruta, esperado = _bcj2(tmp_path, siete_za)
	proveedor = abrir(ruta)
	assert isinstance(proveedor, ProveedorSieteZ)
	assert todo(proveedor) == esperado
	assert isinstance(proveedor._reserva, ProveedorLibarchive)
	prueba = _lanzar(OperacionProbar(local, [str(ruta)]))
	assert prueba.estado == Estado.TERMINADA and not prueba.errores


def test_7z_bcj2_cifrado_se_lee_con_7za(tmp_path, siete_za, monkeypatch):
	ruta, esperado = _bcj2(tmp_path, siete_za, contrasena="clave")
	decisor = fijar(monkeypatch, DecisorConClave(["clave"]))
	proveedor = abrir(ruta)
	assert todo(proveedor) == esperado
	assert isinstance(proveedor._reserva, siete_zip_instalado.ProveedorSieteZipExterno)
	assert decisor.textos


def test_proveedor_externo_con_7za_lista_extrae_y_pide_la_contrasena(tmp_path, siete_za, monkeypatch, local):
	origen = tmp_path / "datos"
	(origen / "sub").mkdir(parents=True)
	(origen / "a ñ.bin").write_bytes(DATOS)
	(origen / "sub" / "b.txt").write_bytes(TEXTO)
	destino = tmp_path / "x.7z"
	siete_zip_externo.crear(siete_za, str(destino), [str(origen)], contrasena="clave", cifrar_nombres=True)
	decisor = fijar(monkeypatch, DecisorConClave(["mala", "clave"]))
	proveedor = siete_zip_instalado.ProveedorSieteZipExterno(local, str(destino), siete_za, "7z")
	assert [e.nombre for e in proveedor.listar("datos")] == ["sub", "a ñ.bin"]
	assert todo(proveedor) == {"datos/a ñ.bin": DATOS, "datos/sub/b.txt": TEXTO}
	assert len(decisor.textos) == 2 and "no es correcta" in decisor.textos[1]
	assert proveedor.probar().correcto
	proveedor.cerrar()


def test_extraer_con_7za_no_deja_carpetas_temporales(tmp_path, siete_za):
	origen = tmp_path / "datos"
	origen.mkdir()
	(origen / "a.txt").write_bytes(b"a")
	destino = tmp_path / "x.7z"
	siete_zip_externo.crear(siete_za, str(destino), [str(origen)])
	extraidos = siete_zip_externo.extraer(siete_za, str(destino), ["datos\\a.txt"])
	assert open(extraidos["datos\\a.txt"], "rb").read() == b"a"
	from app.services.vfs import temporales

	assert not [p for p in temporales.carpeta_temporal().iterdir() if p.name.startswith("7z-")]


def test_analizar_listado_de_7zip():
	texto = ("Path = carpeta\r\nFolder = +\r\nSize = 0\r\nModified = 2026-11-08 14:53:28\r\nAttributes = D\r\n\r\n"
		"Path = carpeta\\a.txt\r\nFolder = -\r\nSize = 500\r\nModified = 2026-11-08 14:53:28.123\r\nAttributes = R\r\n"
		"Encrypted = +\r\n\r\nPath = enlace\r\nSize = 4\r\nAttributes = A -lrwxrwxrwx\r\n")
	miembros = siete_zip_externo.analizar_listado(texto)
	assert [m.ruta for m in miembros] == ["carpeta", "carpeta\\a.txt", "enlace"]
	assert miembros[0].es_carpeta and not miembros[1].es_carpeta
	assert miembros[1].tamano == 500 and miembros[1].cifrado and miembros[1].solo_lectura and miembros[1].modificado > 0
	assert miembros[2].enlace


def test_reglas_de_contrasena_en_los_argumentos(monkeypatch):
	from app.core import procesos

	llamadas = []

	def falso(argumentos, **opciones):
		llamadas.append((argumentos, opciones["entrada"]))
		return procesos.ResultadoPrograma(0, b"", b"", False)

	monkeypatch.setattr(procesos, "lanzar", falso)
	siete_zip_externo.ejecutar("C:\\7z.exe", "x", [], "a.7z", contrasena="secreta")
	siete_zip_externo.ejecutar("C:\\7z.exe", "l", [], "a.7z")
	siete_zip_externo.ejecutar("C:\\7z.exe", "a", [], "a.7z", contrasena="secreta")
	siete_zip_externo.ejecutar("C:\\7z.exe", "a", [], "a.7z")
	(x, entrada_x), (l, entrada_l), (a, entrada_a), (a2, entrada_a2) = llamadas
	# Extraer con contraseña conocida: SIN -p y la contraseña por la entrada estándar.
	assert not any(p.startswith("-p") for p in x) and entrada_x == b"secreta\r\n"
	# Listar sin contraseña: -p vacío (falla enseguida si hace falta).
	assert "-p" in l and entrada_l == b""
	# Crear con contraseña: -p vacío y la contraseña una vez por la entrada estándar.
	assert "-p" in a and entrada_a == b"secreta\r\n"
	assert not any(p.startswith("-p") for p in a2) and entrada_a2 == b""
	assert all("secreta" not in " ".join(arg) for arg, _e in llamadas)
	assert all(arg[arg.index("--") + 1] == "a.7z" for arg, _e in llamadas)


def test_detectar_7zip_por_configuracion_y_registro(tmp_path, monkeypatch):
	carpeta = tmp_path / "7-Zip"
	carpeta.mkdir()
	(carpeta / "7z.exe").write_bytes(b"MZ")
	fijar(monkeypatch, config=ConfigFalsa(comprimidos__ruta_7zip=str(carpeta)))
	assert siete_zip_instalado.detectar_7zip() == (carpeta / "7z.exe").resolve()
	fijar(monkeypatch, config=ConfigFalsa())
	monkeypatch.setattr(siete_zip_instalado, "_del_registro", lambda: [tmp_path / "no-existe", carpeta])
	assert siete_zip_instalado.detectar_7zip(forzar=True) == (carpeta / "7z.exe").resolve()
	fijar(monkeypatch, config=ConfigFalsa(comprimidos__usar_7zip_instalado=False))
	assert siete_zip_instalado.siete_zip_instalado() is None
	monkeypatch.setattr(siete_zip_instalado, "_del_registro", lambda: [])
	fijar(monkeypatch, config=ConfigFalsa())
	assert siete_zip_instalado.detectar_7zip(forzar=True) is None
	monkeypatch.setattr(siete_zip_instalado, "_detectado", [])


def test_formatos_del_7zip_instalado_sin_7zip_se_abren_con_su_programa(tmp_path, monkeypatch, local):
	monkeypatch.setattr(siete_zip_instalado, "siete_zip_instalado", lambda: None)
	with pytest.raises(base.NoAdmitido):
		siete_zip_instalado._fabrica(local, str(tmp_path / "x.msi"))


def test_7zip_instalado_real_lee_un_7z_cifrado(tmp_path, siete_za, monkeypatch, local):
	instalado = siete_zip_instalado.detectar_7zip(forzar=True)
	if instalado is None:
		pytest.skip("No hay 7-Zip instalado en este equipo")
	origen = tmp_path / "datos"
	origen.mkdir()
	(origen / "a.bin").write_bytes(DATOS)
	destino = tmp_path / "x.7z"
	siete_zip_externo.crear(siete_za, str(destino), [str(origen)], contrasena="clave")
	fijar(monkeypatch, DecisorConClave(["clave"]))
	proveedor = siete_zip_instalado.ProveedorSieteZipExterno(local, str(destino), instalado, "7z")
	assert todo(proveedor) == {"datos/a.bin": DATOS}
	assert siete_zip_externo.version(instalado)
	proveedor.cerrar()
	shutil.rmtree(origen)
