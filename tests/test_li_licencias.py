# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque LI: licencias y compilación (diseño 2.0, 2, 17 y 18.2).

- Todo archivo propio tiene la cabecera SPDX y el titular (2.1).
- ``data/docs/licencias`` está al día y ``LEEME-LICENCIAS.md`` nombra cada
  componente de ``linea_base.json`` y cada paquete de ``requirements.txt`` (2.2).
- Las DLL no libres de accessible_output2 se borran y se detectan (2.3); la
  compilación real no las lleva (``lento``, solo si hay compilación).
- ``tools/empaquetar.py`` omite los datos de la persona y los restos de ``data/bin``.
- «Acerca de» muestra el titular y la frase de la licencia y pasa ``revisar_teclado`` (2.5).
"""

from __future__ import annotations

import ast
import json
import re
import zipfile
from pathlib import Path

import pytest

from tools import comprobar_licencias, empaquetar, generar_licencias, verificar_build

RAIZ = Path(__file__).resolve().parents[1]
COMPILACION = RAIZ / "build" / "ZCommander"
SEIS_DLL = ("SAAPI32.dll", "dolapi.dll", "PCTKUSR.dll", "PCTKUSR64.dll", "ZDSRAPI.dll", "ZDSRAPI_x64.dll")


def _setup_cx():
	return verificar_build._setup_cx()


# ── Cabeceras y textos de licencia ───────────────────────────────────────────


def test_todo_archivo_propio_tiene_la_cabecera_spdx():
	sin_cabecera = comprobar_licencias.archivos_sin_cabecera()
	assert not sin_cabecera, "Sin «SPDX-License-Identifier: GPL-3.0-or-later» y el titular:\n" + "\n".join(sin_cabecera)


def test_la_comprobacion_de_cabecera_detecta_su_falta(tmp_path):
	(tmp_path / "app").mkdir()
	(tmp_path / "app" / "bien.py").write_text(
		"# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright (C) 2026 hxebolax y colaboradores\n", encoding="utf-8")
	(tmp_path / "app" / "mal.py").write_text('"""Sin cabecera."""\n', encoding="utf-8")
	(tmp_path / "app" / "lib").mkdir()
	(tmp_path / "app" / "lib" / "ajeno.py").write_text("", encoding="utf-8")  # vendorizado: no es propio
	(tmp_path / "entorno.bat").write_bytes(
		b"@echo off\r\nrem SPDX-License-Identifier: GPL-3.0-or-later\r\nrem Copyright (C) 2026 hxebolax y colaboradores\r\n")
	assert comprobar_licencias.archivos_sin_cabecera(tmp_path) == ["app/mal.py"]


def test_textos_de_licencia_al_dia():
	assert generar_licencias.desfasados() == []


def test_leeme_lista_cada_componente_de_la_linea_base_y_de_requirements():
	texto = (RAIZ / "data" / "docs" / "licencias" / "LEEME-LICENCIAS.md").read_text(encoding="utf-8")
	for ficha in comprobar_licencias.linea_base():
		assert f"`{ficha['id']}`" in texto, ficha["id"]
	for paquete in comprobar_licencias.paquetes_requeridos():
		assert f"`{paquete.lower()}`" in texto.lower(), paquete
	assert comprobar_licencias.problemas_leeme() == []


def test_cada_carpeta_de_licencias_tiene_su_texto():
	carpeta = RAIZ / "data" / "docs" / "licencias"
	for componente in generar_licencias.COMPONENTES:
		textos = [p for p in (carpeta / componente.carpeta).rglob("*") if p.is_file() and p.stat().st_size > 0]
		assert textos, componente.carpeta
	gpl = (carpeta / "zCommander" / "GPL-3.0.txt").read_bytes().replace(b"\r\n", b"\n")
	assert gpl == (RAIZ / "LICENSE").read_bytes().replace(b"\r\n", b"\n")


def test_oferta_de_fuentes_nombra_los_componentes_lgpl_y_gpl():
	texto = (RAIZ / "data" / "docs" / "licencias" / "OFERTA-DE-FUENTES.md").read_text(encoding="utf-8")
	assert "tres años" in texto
	for nombre in ("wxPython", "paramiko", "py7zr", "NVDA Controller Client", "libiconv", "7za", "FFmpeg", "mutagen"):
		assert nombre in texto, nombre


def test_repositorio_sin_problemas_de_licencias():
	assert comprobar_licencias.problemas_repositorio() == []


# ── DLL no libres y compilación ──────────────────────────────────────────────


def _compilacion_falsa(raiz: Path) -> Path:
	carpeta = raiz / "ZCommander"
	ao2 = carpeta / "lib" / "accessible_output2" / "lib"
	ao2.mkdir(parents=True)
	for nombre in (*SEIS_DLL, "nvdaControllerClient32.dll", "nvdaControllerClient64.dll"):
		(ao2 / nombre).write_bytes(b"MZ")
	(carpeta / "ZCommander.exe").write_bytes(b"MZ")
	return carpeta


def test_setup_borra_las_dll_no_libres_y_la_comprobacion_las_detecta(tmp_path):
	carpeta = _compilacion_falsa(tmp_path)
	encontradas = comprobar_licencias.dll_prohibidas(carpeta)
	assert len(encontradas) == 7
	borradas = _setup_cx().borrar_dll_no_libres(carpeta)
	assert sorted(Path(b).name for b in borradas) == sorted([*SEIS_DLL, "nvdaControllerClient32.dll"])
	assert comprobar_licencias.dll_prohibidas(carpeta) == []
	assert (carpeta / "lib" / "accessible_output2" / "lib" / "nvdaControllerClient64.dll").is_file()


def test_la_comprobacion_de_compilacion_reconoce_cada_componente(tmp_path):
	carpeta = _compilacion_falsa(tmp_path)
	_setup_cx().borrar_dll_no_libres(carpeta)
	lib = carpeta / "lib"
	for nombre in ("wx", "json", "paramiko", "Crypto", "win32api.pyd", "_cffi_backend.cp315-win_amd64.pyd", "libcrypto-3.dll",
			"library.zip", "app"):
		(lib / nombre).write_bytes(b"") if "." in nombre else (lib / nombre).mkdir()
	(lib / "paquete_desconocido").mkdir()
	(lib / "numpy").mkdir()
	(carpeta / "vcruntime140.dll").write_bytes(b"MZ")
	(carpeta / "raro.dll").write_bytes(b"MZ")
	problemas = comprobar_licencias.problemas_compilacion(carpeta)
	texto = "\n".join(problemas)
	assert "lib/paquete_desconocido" in texto
	assert "lib/numpy no debe distribuirse" in texto
	assert "raro.dll" in texto
	for conocido in ("lib/wx", "lib/json", "lib/paramiko", "lib/Crypto", "win32api", "_cffi_backend", "libcrypto", "library.zip",
			"lib/app", "vcruntime140", "DLL no libre"):
		assert conocido not in texto, conocido


@pytest.mark.lento
def test_la_compilacion_no_contiene_las_seis_dll():
	if not (COMPILACION / "ZCommander.exe").is_file():
		pytest.skip("No hay compilación en build/ZCommander (python setup_cx.py build)")
	assert comprobar_licencias.dll_prohibidas(COMPILACION) == []
	assert verificar_build.comprobar_dll(COMPILACION) == []


def test_setup_cx_lleva_lo_de_la_2_0():
	setup = _setup_cx()
	assert "py7zr" in setup.PAQUETES and "cryptography" in setup.PAQUETES
	assert {"numpy", "pythonwin", "win32ui", "pygments"} <= set(setup.EXCLUDES)
	assert "unittest" not in setup.EXCLUDES
	destinos = {d for _, d in setup.archivos_de_plugins()}
	assert "plugins/ocr/recursos/ocr.ps1" in destinos
	assert any(d.endswith("_table.pywinrt") for d in destinos)
	assert not any("__pycache__" in d or ".ruff_cache" in d or Path(d).name.startswith("test_") for d in destinos)
	assert not any(d.startswith("plugins/nubes/") and d.endswith(".pyc") for d in destinos)
	datos = {d for _, d in setup.archivos_de_data()}
	assert "data/docs/licencias/LEEME-LICENCIAS.md" in datos
	assert not any(Path(d).parts[1] in setup.DATA_PROHIBIDO for d in datos)
	assert not any(empaquetar.omitir_de_bin(Path(*Path(d).parts[2:])) for d in datos if d.startswith("data/bin/"))


def test_sumas_de_serie_cubren_cada_archivo_copiado():
	setup = _setup_cx()
	sumas = setup.sumas_serie()
	copiados = [d for _, d in setup.archivos_de_plugins() if len(Path(d).parts) > 2]
	assert sum(len(v) for v in sumas.values()) == len(copiados)
	assert "zc.ocr" in sumas and "recursos/ocr.ps1" in sumas["zc.ocr"]


def test_verificar_build_compara_las_sumas_congeladas(tmp_path):
	plugins = tmp_path / "plugins" / "ejemplo"
	plugins.mkdir(parents=True)
	(plugins / "manifiesto.toml").write_text('id = "prueba.ejemplo"\n', encoding="utf-8")
	(plugins / "__init__.py").write_text("X = 1\n", encoding="utf-8")
	reales = verificar_build.sumas_de_plugins(tmp_path / "plugins")
	assert set(reales["prueba.ejemplo"]) == {"manifiesto.toml", "__init__.py"}
	codigo = compile(f"SUMAS = {reales!r}\n", "serie_sumas.py", "exec")
	import importlib.util
	import marshal

	destino = tmp_path / "lib" / "app" / "plugins"
	destino.mkdir(parents=True)
	(destino / "serie_sumas.pyc").write_bytes(importlib.util.MAGIC_NUMBER + b"\0" * 12 + marshal.dumps(codigo))
	assert verificar_build.leer_sumas_congeladas(tmp_path) == reales


def test_verificar_build_exige_un_solo_complemento_de_nvda(tmp_path):
	nvda = tmp_path / "data" / "bin" / "nvda"
	nvda.mkdir(parents=True)
	assert verificar_build.comprobar_nvda(tmp_path, "2.0.0")
	with zipfile.ZipFile(nvda / "zCommander-2.0.0.nvda-addon", "w") as paquete:
		paquete.writestr("manifest.ini", 'name = zCommander\nversion = 2.0.0\n')
	assert verificar_build.comprobar_nvda(tmp_path, "2.0.0") == []
	(nvda / "zCommander-1.9.0.nvda-addon").write_bytes(b"")
	assert verificar_build.comprobar_nvda(tmp_path, "2.0.0")


# ── Paquete ZIP ──────────────────────────────────────────────────────────────


def test_personales_de_empaquetar_coinciden_con_setup_cx():
	arbol = ast.parse((RAIZ / "setup_cx.py").read_text(encoding="utf-8"))
	prohibido = next(ast.literal_eval(n.value) for n in arbol.body
		if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "DATA_PROHIBIDO")
	assert set(empaquetar.PERSONALES) == prohibido


def test_empaquetar_omite_datos_de_la_persona_y_restos_de_bin(tmp_path):
	origen = tmp_path / "ZCommander"
	(origen / "ZCommander.exe").parent.mkdir(parents=True)
	(origen / "ZCommander.exe").write_bytes(b"MZ")
	incluir = ["data/bin/rclone/rclone.exe", "data/bin/linea_base.json", "data/bin/componentes.json", "data/docs/manual.md",
		"plugins/voz/__init__.py"]
	omitir = ["data/plugins/x.y/manifiesto.toml", "data/sounds_usuario/a.wav", "data/plantillas/b.txt", "data/config/settings.json",
		"data/bin/respaldo/rclone/1.0/archivos/rclone.exe", "data/bin/.pendiente/ffmpeg/pendiente.json",
		"data/bin/.entrante/libarchive/x.dll", "data/bin/estado_componentes.json", "data/bin/instalando.json",
		"data/bin/integracion.json", "data/bin/rclone.nueva/rclone.exe", "data/bin/ffmpeg.vieja/ffmpeg.exe",
		"plugins/voz/__pycache__/x.pyc", "data/bin/descarga.parcial"]
	for relativa in incluir + omitir:
		ruta = origen / relativa
		ruta.parent.mkdir(parents=True, exist_ok=True)
		ruta.write_bytes(b"x")
	destino, incluidos, omitidos = empaquetar.empaquetar(origen, tmp_path / "z.zip")
	with zipfile.ZipFile(destino) as archivo:
		nombres = set(archivo.namelist())
	assert nombres == {f"zCommander/{r}" for r in ["ZCommander.exe", *incluir]}
	assert (incluidos, omitidos) == (len(incluir) + 1, len(omitir))


def test_nombre_del_paquete_es_el_del_actualizador():
	texto = (RAIZ / "tools" / "empaquetar.py").read_text(encoding="utf-8")
	assert re.search(r'f"zCommander_v\{version\(\)\}\.zip"', texto)


# ── «Acerca de» ──────────────────────────────────────────────────────────────


def test_acerca_de_muestra_titular_y_licencia(app_wx):
	from app.ui import acerca_de

	texto = acerca_de.texto_acerca_de()
	assert "Copyright © 2026 hxebolax y colaboradores. Licencia GPL-3.0 o posterior." in texto
	assert ("Este programa es software libre: puede redistribuirlo y modificarlo según la Licencia Pública General de GNU, "
		"versión 3 o posterior. Se distribuye sin ninguna garantía.") in texto
	assert acerca_de.URL_FUENTES in texto
	assert "WinFsp" not in texto


def test_acerca_de_pasa_revisar_teclado(app_wx):
	from app.ui import acerca_de
	from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado

	dialogo = acerca_de.DialogoAcercaDe(None)
	try:
		problemas = [p for p in revisar_teclado(dialogo) if not p.aviso]
		assert not problemas, informe(problemas)
		assert acerca_de.frase_licencia() in dialogo.campo.GetValue()
		etiquetas = [b.GetLabel() for b in (dialogo.boton_licencia, dialogo.boton_terceros, dialogo.boton_oferta,
			dialogo.boton_copiar, dialogo.boton_cerrar)]
		assert etiquetas == ["Ver la &licencia", "Componentes de &terceros", "&Oferta de fuentes", "Co&piar la información", "&Cerrar"]
		assert dialogo.GetEscapeId() == acerca_de.wx.ID_CANCEL
	finally:
		dialogo.Destroy()


def test_acerca_de_avisa_de_winfsp_si_nubes_lo_uso(app_wx, datos_temporales):
	from app.core import paths
	from app.ui import acerca_de

	(paths.ruta_config_plugins() / "zc.nubes.json").write_text(json.dumps({"aviso_winfsp_mostrado": True}), encoding="utf-8")
	texto = acerca_de.texto_acerca_de()
	assert "WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos" in texto
	assert "https://github.com/winfsp/winfsp" in texto


def test_botones_de_acerca_de_abren_sus_documentos(app_wx, datos_temporales):
	import shutil

	from app.ui import acerca_de, visor_ayuda

	# Copia de los documentos reales en la data temporal: la prueba no toca data/ del proyecto.
	shutil.copytree(RAIZ / "data" / "docs" / "licencias", datos_temporales / "docs" / "licencias")
	for identificador, titulo in ((acerca_de.ID_LICENCIA, "Licencia Pública General de GNU, versión 3"),
			(acerca_de.ID_TERCEROS, "Licencias de zCommander y de sus componentes"),
			(acerca_de.ID_OFERTA, "Oferta de fuentes de zCommander")):
		visor = acerca_de.abrir_documento_de_licencias(None, int(identificador), mostrar=False)
		try:
			assert visor is not None
			assert visor.GetTitle() == titulo
		finally:
			visor_ayuda._abiertos.pop(visor.GetTitle(), None)
			visor.Destroy()
	assert acerca_de.abrir_documento_de_licencias(None, int(acerca_de.wx.ID_CANCEL)) is None


# ── Fuentes de terceros (2.4) ────────────────────────────────────────────────


@pytest.fixture
def servidor_fuentes(tmp_path):
	"""Servidor HTTP local con un «PyPI» de juguete y un archivo de fuentes directo."""
	import hashlib
	import http.server
	import threading

	contenido = {"/archivos/demo-1.0.tar.gz": b"fuentes de demo", "/archivos/otro-src.7z": b"7z de prueba"}
	puerto: list[int] = []

	class Manejador(http.server.BaseHTTPRequestHandler):
		def do_GET(self):  # noqa: N802 - API de http.server
			if self.path == "/pypi/demo/1.0/json":
				base = f"http://127.0.0.1:{puerto[0]}"
				datos = {"urls": [
					{"packagetype": "bdist_wheel", "url": f"{base}/no", "filename": "demo.whl", "digests": {"sha256": "0"}},
					{"packagetype": "sdist", "url": f"{base}/archivos/demo-1.0.tar.gz", "filename": "demo-1.0.tar.gz",
						"digests": {"sha256": hashlib.sha256(contenido["/archivos/demo-1.0.tar.gz"]).hexdigest()}}]}
				cuerpo = json.dumps(datos).encode("utf-8")
			elif self.path in contenido:
				cuerpo = contenido[self.path]
			else:
				self.send_error(404)
				return
			self.send_response(200)
			self.send_header("Content-Length", str(len(cuerpo)))
			self.end_headers()
			self.wfile.write(cuerpo)

		def log_message(self, *argumentos):
			pass

	servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
	puerto.append(servidor.server_address[1])
	hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
	hilo.start()
	try:
		yield f"http://127.0.0.1:{puerto[0]}"
	finally:
		servidor.shutdown()
		servidor.server_close()


def test_fuentes_terceros_descarga_con_sumas(tmp_path, servidor_fuentes):
	from tools import fuentes_terceros as ft

	from app.core import red

	directa = ft.Fuente("Otro", f"{servidor_fuentes}/archivos/otro-src.7z", "otro-src.7z")
	config = red.ConfiguracionRed("zCommander", "prueba", proxy="ninguno")
	# En este equipo la conexión local se corta a veces (WinError 10054 de un filtro de red, como en
	# test_n2_descargas): se reintenta como haría la persona; las descargas son reanudables.
	for _intento in range(20):
		try:
			hechos = ft.descargar_todo(tmp_path / "fuentes", config=config, base_pypi=f"{servidor_fuentes}/pypi",
				pypi=[("demo", "1.0")], directas=[directa])
			break
		except (OSError, red.ErrorHTTP):
			continue
	else:
		pytest.fail("La descarga local falló 20 veces seguidas")
	assert sorted(p.name for p in hechos) == ["demo-1.0.tar.gz", "otro-src.7z"]
	sumas = (tmp_path / "fuentes" / "SHA256SUMS.txt").read_text(encoding="utf-8")
	assert "demo-1.0.tar.gz" in sumas and "otro-src.7z" in sumas


def test_fuentes_terceros_sin_descargar_no_se_conecta(capsys, monkeypatch):
	from tools import fuentes_terceros as ft

	monkeypatch.setattr(ft, "commit_ffmpeg", lambda ruta=None: "d4070a14ce")
	monkeypatch.setattr(ft, "descargar_todo", lambda *a, **k: pytest.fail("no debe descargar"))
	assert ft.main([]) == 0
	salida = capsys.readouterr().out
	assert "No se ha descargado nada" in salida
	assert "FFmpeg/FFmpeg/archive/d4070a14ce.tar.gz" in salida
	assert "7z2606-src.7z" in salida and "mingw-w64-libiconv" in salida
