# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Enlaces simbólicos, uniones, enlaces duros y accesos directos (bloque E, sección 8.11)."""

from __future__ import annotations

import os

import pytest

from app.services.vfs import base
from app.services.vfs.local import ProveedorLocal
from app.services.windows import enlaces


@pytest.fixture
def origen(tmp_path):
	(tmp_path / "datos").mkdir()
	(tmp_path / "datos" / "nota.txt").write_text("hola", encoding="utf-8")
	(tmp_path / "enlaces").mkdir()
	return tmp_path


def test_union_de_carpeta(origen):
	enlace = str(origen / "enlaces" / "atajo")
	enlaces.crear(enlaces.UNION, enlace, str(origen / "datos"))
	assert os.path.isdir(enlace)
	assert (origen / "enlaces" / "atajo" / "nota.txt").read_text(encoding="utf-8") == "hola"
	assert enlaces.tipo_de(enlace) == enlaces.UNION
	# El panel lo ve como enlace (no lo sigue al borrar ni al recorrer).
	entrada = ProveedorLocal().info(enlace)
	assert entrada.es_enlace and entrada.es_carpeta
	assert os.path.normcase(entrada.destino_enlace) == os.path.normcase(str(origen / "datos"))


def test_enlace_duro(origen):
	enlace = str(origen / "enlaces" / "otra-nota.txt")
	enlaces.crear(enlaces.DURO, enlace, str(origen / "datos" / "nota.txt"))
	assert (origen / "enlaces" / "otra-nota.txt").read_text(encoding="utf-8") == "hola"
	(origen / "datos" / "nota.txt").write_text("cambiado", encoding="utf-8")
	assert (origen / "enlaces" / "otra-nota.txt").read_text(encoding="utf-8") == "cambiado"
	assert enlaces.tipo_de(enlace) == enlaces.DURO


def test_acceso_directo(origen):
	pytest.importorskip("win32com.shell")
	enlace = str(origen / "enlaces" / "nota.lnk")
	enlaces.crear(enlaces.ACCESO_DIRECTO, enlace, str(origen / "datos" / "nota.txt"))
	assert os.path.isfile(enlace)
	assert os.path.normcase(enlaces.destino_acceso_directo(enlace)) == os.path.normcase(str(origen / "datos" / "nota.txt"))
	assert enlaces.tipo_de(enlace) == enlaces.ACCESO_DIRECTO


def test_simbolico_o_mensaje_de_privilegios(origen):
	enlace = str(origen / "enlaces" / "simbolico.txt")
	try:
		enlaces.crear(enlaces.SIMBOLICO, enlace, str(origen / "datos" / "nota.txt"))
	except enlaces.SinPrivilegios as error:
		# Sin modo de desarrollador ni administrador: se explica cómo activarlo.
		assert "modo de desarrollador" in error.mensaje
		assert "Para programadores" in error.mensaje
		assert not os.path.lexists(enlace)
		return
	assert os.path.islink(enlace)
	assert enlaces.tipo_de(enlace) == enlaces.SIMBOLICO
	assert (origen / "enlaces" / "simbolico.txt").read_text(encoding="utf-8") == "hola"


def test_error_1314_se_convierte_en_sin_privilegios(origen, monkeypatch):
	def sin_permiso(*args, **kwargs):
		raise OSError(None, "El cliente no dispone de un privilegio requerido", args[1], enlaces.ERROR_PRIVILEGIO)

	monkeypatch.setattr(os, "symlink", sin_permiso)
	with pytest.raises(enlaces.SinPrivilegios) as info:
		enlaces.crear(enlaces.SIMBOLICO, str(origen / "enlaces" / "s"), str(origen / "datos"))
	assert isinstance(info.value, base.ErrorAcceso)
	assert "unión" in info.value.mensaje and "acceso directo" in info.value.mensaje


@pytest.mark.parametrize(("tipo", "enlace", "destino", "fragmento"), [
	(enlaces.UNION, "enlaces\\u", "datos\\nota.txt", "solo puede apuntar a una carpeta"),
	(enlaces.DURO, "enlaces\\d", "datos", "solo puede apuntar a un archivo"),
	(enlaces.ACCESO_DIRECTO, "enlaces\\a.txt", "datos\\nota.txt", ".lnk"),
	(enlaces.SIMBOLICO, "enlaces\\s", "datos\\falta.txt", "No existe el destino"),
	(enlaces.SIMBOLICO, "falta\\s", "datos", "No existe la carpeta"),
	(enlaces.SIMBOLICO, "enlaces\\a:b", "datos", "carácter"),
	(enlaces.SIMBOLICO, "", "datos", "ruta completa"),
	(enlaces.SIMBOLICO, "enlaces\\s", "", "destino"),
	(enlaces.SIMBOLICO, "datos\\nota.txt", "datos", "Ya existe"),
	("raro", "enlaces\\s", "datos", "desconocido"),
])
def test_problemas(origen, tipo, enlace, destino, fragmento):
	ruta_enlace = str(origen / enlace) if enlace else ""
	ruta_destino = str(origen / destino) if destino else ""
	motivo = enlaces.problema(tipo, ruta_enlace, ruta_destino)
	assert motivo and fragmento in motivo, motivo
	if tipo in enlaces.TIPOS:
		with pytest.raises(base.ErrorArchivos):
			enlaces.crear(tipo, ruta_enlace, ruta_destino)


def test_union_no_admite_red(origen):
	motivo = enlaces.problema(enlaces.UNION, str(origen / "enlaces" / "u"), "\\\\servidor\\recurso")
	assert motivo  # no existe o es de red: en los dos casos se rechaza


def test_destino_relativo_desde_la_carpeta_del_enlace(origen):
	assert enlaces.problema(enlaces.UNION, str(origen / "enlaces" / "u"), "..\\datos") is None
	enlaces.crear(enlaces.UNION, str(origen / "enlaces" / "u"), "..\\datos")
	assert (origen / "enlaces" / "u" / "nota.txt").exists()


def test_textos_de_tipos():
	for tipo in enlaces.TIPOS:
		assert enlaces.nombre_tipo(tipo)
		assert enlaces.explicacion(tipo)
	assert isinstance(enlaces.puede_crear_simbolicos(), bool)
