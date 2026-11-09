# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""tools/descargar_componentes.py: trae a data/bin los binarios de la línea base con sus sumas (sin red)."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from tools import descargar_componentes as dc


def _base(carpeta: Path, archivos: dict[str, bytes]) -> dict:
	"""Una línea base mínima con un componente «demo» y sus archivos (binarios y licencia)."""
	return {"componentes": [{
		"id": "demo", "carpeta": "demo",
		"archivos": [{"ruta": r, "sha256": hashlib.sha256(c).hexdigest(), "tamano": len(c)} for r, c in archivos.items()],
	}]}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
	archivos = {"demo.exe": b"MZ ejecutable", "demo.dll": b"MZ biblioteca", "LICENCIA.txt": b"licencia"}
	bin_ = tmp_path / "bin"
	bin_.mkdir()
	base = _base(bin_, archivos)
	monkeypatch.setattr(dc, "BIN", bin_)
	monkeypatch.setattr(dc, "DIST", tmp_path / "dist")
	monkeypatch.setattr(dc, "leer_base", lambda: base)
	return bin_, base, archivos


def test_solo_ejecutables_y_dll_se_descargan(entorno):
	_bin, base, _archivos = entorno
	assert sorted(dc.binarios_esperados(base)) == ["demo/demo.dll", "demo/demo.exe"]


def test_pendientes_detecta_faltan_y_sumas_distintas(entorno):
	bin_, base, archivos = entorno
	esperados = dc.binarios_esperados(base)
	assert sorted(dc.pendientes(esperados)) == ["demo/demo.dll", "demo/demo.exe"]
	(bin_ / "demo").mkdir()
	(bin_ / "demo" / "demo.exe").write_bytes(archivos["demo.exe"])
	(bin_ / "demo" / "demo.dll").write_bytes(b"MZ manipulada")
	assert dc.pendientes(esperados) == ["demo/demo.dll"]


def test_paquete_de_release_ida_y_vuelta(entorno, tmp_path, monkeypatch):
	bin_, base, archivos = entorno
	(bin_ / "demo").mkdir()
	for nombre, contenido in archivos.items():
		(bin_ / "demo" / nombre).write_bytes(contenido)
	assert dc.main(["--crear-paquete"]) == 0
	paquete = tmp_path / "dist" / dc.nombre_paquete()
	with zipfile.ZipFile(paquete) as zf:
		assert sorted(zf.namelist()) == ["demo/demo.dll", "demo/demo.exe"]
	shutil.rmtree(bin_ / "demo")

	from app.core import descargas

	pedidas = []

	def descargar_falso(_config, url, destino, **_kw):
		pedidas.append(url)
		final = Path(destino) / dc.nombre_paquete()
		shutil.copyfile(paquete, final)
		return final

	monkeypatch.setattr(descargas, "descargar", descargar_falso)
	assert dc.main(["--si", "--sin-nvda"]) == 0
	assert pedidas == [dc.url_paquete()]
	assert pedidas[0].startswith("https://github.com/hxebolax/zCommander/releases/download/v")
	assert dc.pendientes(dc.binarios_esperados(base)) == []


def test_paquete_con_suma_distinta_no_se_instala(entorno, tmp_path, monkeypatch):
	bin_, _base, _archivos = entorno
	malo = tmp_path / "malo.zip"
	with zipfile.ZipFile(malo, "w") as zf:
		zf.writestr("demo/demo.exe", b"MZ troyano")
		zf.writestr("demo/demo.dll", b"MZ biblioteca")
		zf.writestr("../fuera.txt", b"x")

	from app.core import descargas

	monkeypatch.setattr(descargas, "descargar", lambda _c, _u, destino, **_k: Path(shutil.copyfile(malo, Path(destino) / "p.zip")))
	assert dc.main(["--si", "--sin-nvda"]) == 1  # un nombre con «..» se rechaza antes de escribir nada
	assert not (tmp_path / "fuera.txt").exists()
	assert not (bin_ / "demo").exists()


def test_paquete_sin_nombres_peligrosos_y_suma_mala(entorno, tmp_path, monkeypatch):
	bin_, _base, archivos = entorno
	malo = tmp_path / "malo.zip"
	with zipfile.ZipFile(malo, "w") as zf:
		zf.writestr("demo/demo.exe", b"MZ troyano")
		zf.writestr("demo/demo.dll", archivos["demo.dll"])

	from app.core import descargas

	monkeypatch.setattr(descargas, "descargar", lambda _c, _u, destino, **_k: Path(shutil.copyfile(malo, Path(destino) / "p.zip")))
	assert dc.main(["--si", "--sin-nvda"]) == 1
	assert not (bin_ / "demo" / "demo.exe").exists()
	assert (bin_ / "demo" / "demo.dll").read_bytes() == archivos["demo.dll"]


def test_la_linea_base_real_tiene_sumas_de_todos_los_binarios():
	base = json.loads((Path(dc.RAIZ) / "data" / "bin" / "linea_base.json").read_text(encoding="utf-8"))
	esperados = dc.binarios_esperados(base)
	assert {r.split("/")[0] for r in esperados} == {"rclone", "libarchive", "7za", "ffmpeg"}
	assert all(len(e["sha256"]) == 64 and e["tamano"] > 0 for e in esperados.values())


def test_publicar_crea_el_paquete_de_componentes(tmp_path):
	from tools import publicar

	assert publicar.crear_componentes(tmp_path, tmp_path / "dist", "9.9.9") is None  # sin linea_base.json
	bin_ = tmp_path / "data" / "bin"
	(bin_ / "demo").mkdir(parents=True)
	contenido = b"MZ ejecutable"
	(bin_ / "demo" / "demo.exe").write_bytes(contenido)
	base = _base(bin_, {"demo.exe": contenido})
	(bin_ / "linea_base.json").write_text(json.dumps(base), encoding="utf-8")
	zip_ = publicar.crear_componentes(tmp_path, tmp_path / "dist", "9.9.9")
	assert zip_.name == "zCommander_v9.9.9_componentes.zip"
	with zipfile.ZipFile(zip_) as zf:
		assert zf.namelist() == ["demo/demo.exe"]
