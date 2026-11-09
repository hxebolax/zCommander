# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Bloque B: búsqueda de archivos (sección 8.12) y tamaño de carpetas (8.20). Sin wx."""

from __future__ import annotations

import io
import os
import threading
import time
import zipfile

import pytest

from app.services import busqueda, tamano_carpetas
from app.services.busqueda import Criterios, ErrorCriterios
from app.services.vfs import base, resolver
from app.services.vfs.local import ProveedorLocal


@pytest.fixture
def local():
	return ProveedorLocal()


@pytest.fixture
def cinco(tmp_path):
	"""5 archivos: 2 «.txt» con «hola», 1 «.txt» sin él, 1 «.md» con «hola» y uno grande."""
	raiz = tmp_path / "busca"
	(raiz / "sub").mkdir(parents=True)
	(raiz / "uno.txt").write_text("Esto dice hola al mundo", encoding="utf-8")
	(raiz / "sub" / "dos.txt").write_text("HOLA en mayúsculas", encoding="utf-8")
	(raiz / "tres.txt").write_text("adiós", encoding="utf-8")
	(raiz / "cuatro.md").write_text("hola también", encoding="utf-8")
	(raiz / "grande.bin").write_bytes(b"x" * 5000)
	return raiz


def _buscar(local, raiz, **campos):
	encontrados = []
	estadisticas = busqueda.buscar([(local, str(raiz))], Criterios(**campos), al_resultado=encontrados.append)
	return sorted(r.entrada.nombre for r in encontrados), estadisticas, encontrados


def test_txt_con_hola_encuentra_2_de_5(local, cinco):
	nombres, estadisticas, resultados = _buscar(local, cinco, nombres="*.txt", texto="hola")
	assert nombres == ["dos.txt", "uno.txt"]
	assert estadisticas.encontrados == 2
	assert all(r.es_local and os.path.isabs(r.ruta_local) for r in resultados)
	assert {r.mostrar_carpeta for r in resultados} == {str(cinco), str(cinco / "sub")}
	assert "Búsqueda terminada: 2 resultados" in busqueda.resumen(estadisticas)


def test_tamano_minimo_1_kb_excluye_los_pequenos(local, cinco):
	nombres, _e, _r = _buscar(local, cinco, tamano_min=1024)
	assert nombres == ["grande.bin"]
	nombres, _e, _r = _buscar(local, cinco, tamano_max=100, nombres="*.txt")
	assert nombres == ["dos.txt", "tres.txt", "uno.txt"]


def test_opciones_de_texto(local, cinco):
	assert _buscar(local, cinco, nombres="*.txt", texto="HOLA", mayusculas=True)[0] == ["dos.txt"]
	assert _buscar(local, cinco, nombres="*.txt", texto="hola", no_contiene=True)[0] == ["tres.txt"]
	assert _buscar(local, cinco, texto=r"h[aeiou]la", texto_regex=True)[0] == ["cuatro.md", "dos.txt", "uno.txt"]
	(cinco / "palabra.txt").write_text("holanda", encoding="utf-8")
	assert "palabra.txt" not in _buscar(local, cinco, texto="hola", palabra_completa=True)[0]
	assert "palabra.txt" in _buscar(local, cinco, texto="hola")[0]


def test_sin_subcarpetas_profundidad_y_tipo(local, cinco):
	assert _buscar(local, cinco, nombres="*.txt", subcarpetas=False)[0] == ["tres.txt", "uno.txt"]
	assert _buscar(local, cinco, nombres="*.txt", profundidad=0)[0] == ["tres.txt", "uno.txt"]
	assert _buscar(local, cinco, que=busqueda.CARPETAS)[0] == ["sub"]
	assert "sub" in _buscar(local, cinco, que=busqueda.AMBOS)[0]
	assert _buscar(local, cinco, nombres=r"^(uno|tres)\.", nombres_regex=True)[0] == ["tres.txt", "uno.txt"]
	assert _buscar(local, cinco, nombres="*.txt | t*")[0] == ["dos.txt", "uno.txt"]


def test_fechas(local, cinco):
	viejo = time.time() - 30 * 86400
	os.utime(cinco / "tres.txt", (viejo, viejo))
	assert _buscar(local, cinco, nombres="*.txt", hasta=time.time() - 86400)[0] == ["tres.txt"]
	assert "tres.txt" not in _buscar(local, cinco, nombres="*.txt", desde=time.time() - 86400)[0]


def test_ocultos_y_su_contenido(local, cinco):
	import ctypes

	oculta = cinco / "oculta"
	oculta.mkdir()
	(oculta / "dentro.txt").write_text("hola", encoding="utf-8")
	ctypes.windll.kernel32.SetFileAttributesW(str(oculta), 0x2)
	assert "dentro.txt" not in _buscar(local, cinco, nombres="*.txt")[0]
	assert "dentro.txt" in _buscar(local, cinco, nombres="*.txt", ocultos=True)[0]


@pytest.mark.parametrize(("contenido", "codificacion"), [
	("canción".encode("utf-16-le"), "utf-16"),
	(b"\xff\xfe" + "canción".encode("utf-16-le"), "automatica"),
	("canción".encode("cp1252"), "ansi"),
	("canción".encode("utf-8"), "utf-8"),
	("canción".encode("cp1252"), "automatica"),
])
def test_codificaciones(contenido, codificacion):
	expresion = busqueda.compilar_texto(Criterios(texto="CANCIÓN"))
	assert busqueda.contiene(io.BytesIO(contenido), expresion, codificacion)


def test_texto_partido_entre_bloques():
	expresion = busqueda.compilar_texto(Criterios(texto="aguja"))
	datos = b"a" * 1000 + "agu".encode() + "ja ñ".encode()
	assert busqueda.contiene(io.BytesIO(datos), expresion, "utf-8", bloque=1001)
	# Un carácter de dos bytes partido entre bloques se decodifica bien.
	expresion = busqueda.compilar_texto(Criterios(texto="ñu"))
	datos = b"x" * 9 + "ñu".encode()
	assert busqueda.contiene(io.BytesIO(datos), expresion, "utf-8", bloque=10)


def test_expresion_mal_escrita():
	with pytest.raises(ErrorCriterios):
		busqueda.compilar_texto(Criterios(texto="(", texto_regex=True))
	with pytest.raises(ErrorCriterios):
		busqueda.compilar_nombres(Criterios(nombres="[", nombres_regex=True))


def test_nube_no_se_lee_sin_permiso():
	class Nube(base.Proveedor):
		esquema = "prueba"
		abiertos = 0

		def listar(self, ruta, cancelacion=None):
			return [base.Entrada("n.txt", "/n.txt", tamano=4, en_nube=True)]

		def info(self, ruta):
			return base.Entrada("n.txt", ruta)

		def padre(self, ruta):
			return None if ruta in ("", "/") else "/"

		def unir(self, carpeta, nombre):
			return carpeta.rstrip("/") + "/" + nombre

		def raiz(self, ruta):
			return "/"

		def mostrar(self, ruta):
			return "prueba:" + ruta

		def abrir_lectura(self, ruta):
			Nube.abiertos += 1
			return io.BytesIO(b"hola")

	proveedor = Nube()
	encontrados = []
	busqueda.buscar([(proveedor, "/")], Criterios(texto="hola"), al_resultado=encontrados.append)
	assert encontrados == [] and Nube.abiertos == 0
	busqueda.buscar([(proveedor, "/")], Criterios(texto="hola", nube=True), al_resultado=encontrados.append)
	assert len(encontrados) == 1 and Nube.abiertos == 1
	assert not encontrados[0].es_local


def test_la_busqueda_se_cancela(local, tmp_path):
	raiz = tmp_path / "muchos"
	for i in range(30):
		(raiz / f"c{i}").mkdir(parents=True)
		for j in range(20):
			(raiz / f"c{i}" / f"a{j}.txt").write_text("hola", encoding="utf-8")
	cancelacion = base.Cancelacion()
	vistos = []

	def al_resultado(resultado):
		vistos.append(resultado)
		if len(vistos) == 5:
			cancelacion.cancelar()

	with pytest.raises(base.Cancelado):
		busqueda.buscar([(local, str(raiz))], Criterios(texto="hola"), cancelacion, al_resultado)
	assert len(vistos) == 5


def test_cancelar_desde_otro_hilo(local, tmp_path):
	raiz = tmp_path / "hilo"
	raiz.mkdir()
	for j in range(200):
		(raiz / f"a{j}.txt").write_text("x" * 100, encoding="utf-8")
	cancelacion = base.Cancelacion()
	errores = []

	def trabajo():
		try:
			busqueda.buscar([(local, str(raiz))], Criterios(), cancelacion, lambda r: time.sleep(0.01))
		except base.Cancelado as error:
			errores.append(error)

	hilo = threading.Thread(target=trabajo)
	hilo.start()
	time.sleep(0.05)
	cancelacion.cancelar()
	hilo.join(5)
	assert not hilo.is_alive() and errores


def test_maximo_de_resultados(local, cinco):
	_n, estadisticas, resultados = _buscar(local, cinco, max_resultados=2)
	assert len(resultados) == 2 and estadisticas.limitado


def test_dentro_de_comprimidos(local, cinco, monkeypatch):
	"""Con un proveedor de ZIP mínimo registrado (el real es del bloque C)."""

	class Zip(base.Proveedor):
		esquema = "zip"

		def __init__(self, contenedor, ruta):
			super().__init__()
			self.archivo = zipfile.ZipFile(contenedor.abrir_lectura(ruta))
			self.ruta_archivo = ruta
			self.cerrado = False

		def listar(self, ruta, cancelacion=None):
			prefijo = ruta + "/" if ruta else ""
			nombres = {n[len(prefijo):].split("/")[0] for n in self.archivo.namelist() if n.startswith(prefijo)}
			return [base.Entrada(n, prefijo + n, tamano=self.archivo.getinfo(prefijo + n).file_size) for n in sorted(nombres) if n]

		def info(self, ruta):
			return base.Entrada(ruta.split("/")[-1], ruta)

		def padre(self, ruta):
			return None if not ruta else ruta.rpartition("/")[0]

		def unir(self, carpeta, nombre):
			return f"{carpeta}/{nombre}" if carpeta else nombre

		def raiz(self, ruta):
			return ""

		def mostrar(self, ruta):
			return self.ruta_archivo + ("\\" + ruta.replace("/", "\\") if ruta else "")

		def abrir_lectura(self, ruta):
			return self.archivo.open(ruta)

		def cerrar(self):
			self.cerrado = True
			super().cerrar()

	with zipfile.ZipFile(cinco / "paquete.zip", "w") as z:
		z.writestr("nota.txt", "hola desde el zip")
		z.writestr("otra.txt", "nada")
	monkeypatch.setitem(resolver._comprimidos, "zip", Zip)
	nombres, _e, resultados = _buscar(local, cinco, nombres="*.txt", texto="hola", comprimidos=True)
	assert nombres == ["dos.txt", "nota.txt", "uno.txt"]
	del_zip = next(r for r in resultados if r.entrada.nombre == "nota.txt")
	assert not del_zip.es_local
	assert del_zip.mostrar_ruta() == str(cinco / "paquete.zip" / "nota.txt")
	assert not del_zip.proveedor.cerrado
	# Sin la casilla no se mira dentro.
	assert "nota.txt" not in _buscar(local, cinco, nombres="*.txt", texto="hola")[0]


def test_busquedas_guardadas(datos_temporales):
	assert busqueda.cargar_guardadas() == []
	busqueda.guardar_busqueda("Textos", {"nombres": "*.txt"})
	busqueda.guardar_busqueda("Fotos", {"nombres": "*.jpg"})
	busqueda.guardar_busqueda("textos", {"nombres": "*.md"})
	guardadas = busqueda.cargar_guardadas()
	assert [b["nombre"] for b in guardadas] == ["Fotos", "textos"]
	assert guardadas[1]["campos"] == {"nombres": "*.md"}
	from app.core import almacen_json

	assert almacen_json.leer(busqueda.ARCHIVO_GUARDADAS, {})["version"] == 1
	assert [b["nombre"] for b in busqueda.borrar_busqueda("FOTOS")] == ["textos"]


def test_texto_resultados(local, cinco):
	_n, _e, resultados = _buscar(local, cinco, nombres="uno.txt")
	assert busqueda.texto_resultados(resultados) == str(cinco / "uno.txt") + "\r\n"


# ── Tamaño de carpetas ───────────────────────────────────────────────────────

def test_tamano_de_carpetas(local, cinco):
	(cinco / "sub" / "otra").mkdir()
	(cinco / "sub" / "otra" / "x.bin").write_bytes(b"1" * 2048)
	entradas = local.listar(str(cinco))
	carpetas = tamano_carpetas.carpetas_calculables(entradas)
	assert [c.nombre for c in carpetas] == ["sub"]
	lotes = []
	resultados = tamano_carpetas.calcular(local, carpetas, al_lote=lotes.append)
	assert sum(len(lote) for lote in lotes) == 1
	totales = resultados[0].totales
	assert (totales.archivos, totales.carpetas) == (2, 1)
	assert totales.bytes == len("HOLA en mayúsculas".encode()) + 2048
	texto = tamano_carpetas.describir("sub", totales)
	assert texto.startswith("sub: ") and "2 archivos" in texto and "1 carpeta" in texto


def test_tamano_se_cancela(local, cinco):
	cancelacion = base.Cancelacion()
	cancelacion.cancelar()
	with pytest.raises(base.Cancelado):
		tamano_carpetas.calcular(local, tamano_carpetas.carpetas_calculables(local.listar(str(cinco))), cancelacion)
