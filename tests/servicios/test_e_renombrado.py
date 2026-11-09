# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Renombrado múltiple (bloque E): máscaras, contador, fechas, buscar y reemplazar, mayúsculas,
duplicados, cadenas con temporales, deshacer y plantillas."""

from __future__ import annotations

import os
import time

import pytest

from app.core.tareas import ejecutor_directo
from app.services import renombrado as r
from app.services.operaciones.deshacer import RegistroDeshacer
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.renombrar import OperacionRenombrar
from app.services.vfs.local import ProveedorLocal


def _e(nombre: str, carpeta_ruta: str = "C:\\Fotos", modificado: float = 0.0, es_carpeta: bool = False) -> r.Elemento:
	partes = [p for p in carpeta_ruta.split("\\") if p]
	return r.Elemento(ruta=carpeta_ruta + "\\" + nombre, nombre=nombre, es_carpeta=es_carpeta, carpeta_ruta=carpeta_ruta,
		carpeta=partes[-1] if partes else "", superior=partes[-2] if len(partes) > 1 else "", modificado=modificado)


def _nuevos(elementos, **opciones) -> list[str]:
	calculo = r.calcular(elementos, r.OpcionesRenombrado(**opciones))
	assert calculo.error is None, calculo.error
	return [x.nuevo for x in calculo.resultados]


def _uno(nombre: str, mascara: str, **opciones) -> str:
	return _nuevos([_e(nombre)], mascara_nombre=mascara, **opciones)[0]


# ── Máscaras de nombre y extensión ──────────────────────────────────────────

@pytest.mark.parametrize(("mascara", "esperado"), [
	("[N]", "abcdef.txt"),
	("[N1]", "a.txt"),
	("[N2-5]", "bcde.txt"),
	("[N2,5]", "bcdef.txt"),
	("[N-3,3]", "def.txt"),
	("[N3-]", "cdef.txt"),
	("[N-2]", "e.txt"),
	("[N2--2]", "bcde.txt"),
	("[N10-12]", ".txt"),
	("x[N]y", "xabcdefy.txt"),
	("[[[N]]]", "[abcdef].txt"),
])
def test_tramos_del_nombre(mascara, esperado):
	assert _uno("abcdef.txt", mascara) == esperado


def test_ejemplos_del_diseno():
	# Sección 17.1, parte E.
	assert r.evaluar(r.compilar("[N2-5]"), _e("abcdef"), 0, r.OpcionesRenombrado()) == "bcde"
	assert r.evaluar(r.compilar("[N-3,3]"), _e("abcdef"), 0, r.OpcionesRenombrado()) == "def"


def test_extension_y_carpetas():
	assert _nuevos([_e("foto.JPEG")], mascara_extension="[E1-3]") == ["foto.JPE"]
	assert _nuevos([_e("foto.jpg")], mascara_nombre="[N]_[E]", mascara_extension="png") == ["foto_jpg.png"]
	# Sin extensión: [E] vacío y no queda un punto colgando.
	assert _nuevos([_e("LEEME")]) == ["LEEME"]
	assert _nuevos([_e(".gitignore")], mascara_nombre="[N]2") == [".gitignore2"]
	# Las carpetas no tienen extensión aunque lleven un punto.
	assert _nuevos([_e("v1.0", es_carpeta=True)], mascara_nombre="[N]-copia") == ["v1.0-copia"]


def test_carpeta_y_superior():
	elemento = _e("a.txt", carpeta_ruta="D:\\Viajes\\Roma")
	assert _nuevos([elemento], mascara_nombre="[G]-[P]-[N]") == ["Viajes-Roma-a.txt"]


def test_contador():
	elementos = [_e(f"f{i}.jpg") for i in range(3)]
	assert _nuevos(elementos, mascara_nombre="[C10+5:3]") == ["010.jpg", "015.jpg", "020.jpg"]
	assert _nuevos(elementos, mascara_nombre="foto [C]", contador_inicio=1, contador_paso=1, contador_digitos=2) == [
		"foto 01.jpg", "foto 02.jpg", "foto 03.jpg"]
	# Un campo de la máscara sustituye solo a ese valor de los campos del diálogo.
	assert _nuevos(elementos, mascara_nombre="[C:4]", contador_inicio=7, contador_paso=2) == ["0007.jpg", "0009.jpg", "0011.jpg"]
	assert _nuevos(elementos[:2], mascara_nombre="[C0+-1]") == ["0.jpg", "-1.jpg"]


def test_fechas_de_modificacion():
	marca = time.mktime((2023, 7, 9, 8, 5, 3, 0, 0, -1))
	elemento = _e("IMG_1.jpg", modificado=marca)
	assert _nuevos([elemento], mascara_nombre="[Y]-[M]-[D]") == ["2023-07-09.jpg"]
	assert _nuevos([elemento], mascara_nombre="[y][M][D]_[h][m][s]") == ["230709_080503.jpg"]
	assert _nuevos([elemento], mascara_nombre="[d] [t]") == ["2023-07-09 08.05.03.jpg"]


def test_mayusculas_en_la_mascara():
	assert _uno("hola mundo.txt", "[U][N]") == "HOLA MUNDO.txt"
	assert _uno("HOLA Mundo.txt", "[L][N]") == "hola mundo.txt"
	assert _uno("hola mundo.txt", "[F][N]") == "Hola Mundo.txt"
	assert _uno("hola.txt", "[U]a[n]b[N]") == "Abhola.txt"


@pytest.mark.parametrize("mascara", ["[N", "a]", "[]", "[X]", "[N2-x]", "[C+]", "[Yz]"])
def test_mascaras_no_validas(mascara):
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(mascara_nombre=mascara))
	assert calculo.error
	assert calculo.hay_problemas
	assert calculo.resultados[0].estado == r.ERROR
	assert "Máscara no válida" in r.resumen(calculo)
	assert r.pares(calculo) == []


# ── Buscar y reemplazar, mayúsculas ─────────────────────────────────────────

def test_buscar_y_reemplazar():
	assert _nuevos([_e("foto_foto.jpg")], buscar="foto", reemplazar="img") == ["img_img.jpg"]
	assert _nuevos([_e("foto_foto.jpg")], buscar="foto", reemplazar="img", solo_primera=True) == ["img_foto.jpg"]
	assert _nuevos([_e("Foto.jpg")], buscar="foto", reemplazar="x") == ["x.jpg"]
	assert _nuevos([_e("Foto.jpg")], buscar="foto", reemplazar="x", distinguir_mayusculas=True) == ["Foto.jpg"]
	# Varios pares a la vez: intercambio.
	assert _nuevos([_e("a-b.txt")], buscar="a|b", reemplazar="b|a") == ["b-a.txt"]
	# Un solo reemplazo vale para todos los buscados.
	assert _nuevos([_e("a b_c.txt")], buscar=" |_", reemplazar="-") == ["a-b-c.txt"]
	# Sin «aplicar también a la extensión», la extensión no se toca.
	assert _nuevos([_e("txt.txt")], buscar="txt", reemplazar="doc") == ["doc.txt"]
	assert _nuevos([_e("txt.txt")], buscar="txt", reemplazar="doc", aplicar_extension=True) == ["doc.doc"]


def test_expresion_regular():
	assert _nuevos([_e("IMG_0001.jpg")], buscar=r"IMG_(\d+)", reemplazar=r"foto-\1", regex=True) == ["foto-0001.jpg"]
	assert _nuevos([_e("IMG_0001.jpg")], buscar=r"IMG_(\d+)", reemplazar="foto-$1", regex=True) == ["foto-0001.jpg"]
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(buscar="(", regex=True))
	assert calculo.error and "Expresión regular" in calculo.error


def test_mayusculas_de_nombre_y_extension():
	assert _nuevos([_e("mi FOTO.JPG")], mayusculas_nombre="minusculas", mayusculas_extension="minusculas") == ["mi foto.jpg"]
	assert _nuevos([_e("mi foto.jpg")], mayusculas_nombre="mayusculas") == ["MI FOTO.jpg"]
	assert _nuevos([_e("mi FOTO.jpg")], mayusculas_nombre="primera") == ["Mi foto.jpg"]
	assert _nuevos([_e("mi foto-de_viaje.jpg")], mayusculas_nombre="palabras") == ["Mi Foto-De_Viaje.jpg"]
	assert r.cambiar_mayusculas("01 abc", "primera") == "01 Abc"


def test_orden_de_aplicacion():
	# Máscara, después reemplazo, después mayúsculas.
	assert _nuevos([_e("abc.txt")], mascara_nombre="[N]-x", buscar="b-", reemplazar="B", mayusculas_nombre="mayusculas") == ["ABC-X.txt"]
	assert _nuevos([_e("abc.txt")], mascara_nombre="[N]x", buscar="cx", reemplazar="Z", mayusculas_nombre="minusculas") == ["abz.txt"]


# ── Estados de la vista previa ──────────────────────────────────────────────

def test_duplicados_y_estados():
	elementos = [_e("a.jpg"), _e("b.jpg"), _e("c.jpg")]
	calculo = r.calcular(elementos, r.OpcionesRenombrado(mascara_nombre="foto"))
	assert [x.estado for x in calculo.resultados] == [r.DUPLICADO] * 3
	assert [x.texto for x in calculo.resultados] == ["Duplicado"] * 3
	assert calculo.hay_problemas and calculo.primera_mala() == 0
	assert r.pares(calculo) == []

	calculo = r.calcular(elementos, r.OpcionesRenombrado())
	assert {x.estado for x in calculo.resultados} == {r.SIN_CAMBIOS}
	assert calculo.resultados[0].texto == "Sin cambios"
	assert not calculo.hay_problemas and calculo.primera_mala() == -1

	# Uno queda igual y otro pasa a llamarse como él: el que cambia es el duplicado.
	calculo = r.calcular([_e("a.jpg"), _e("b.jpg")], r.OpcionesRenombrado(buscar="b", reemplazar="a"))
	assert [x.estado for x in calculo.resultados] == [r.SIN_CAMBIOS, r.DUPLICADO]
	assert calculo.primera_mala() == 1

	# Mismo nombre en carpetas distintas no es duplicado.
	calculo = r.calcular([_e("a.jpg", "C:\\x"), _e("b.jpg", "C:\\y")], r.OpcionesRenombrado(mascara_nombre="foto"))
	assert {x.estado for x in calculo.resultados} == {r.CORRECTO}


def test_cadena_y_solo_mayusculas_son_correctos():
	# a→b y b→a: los nombres finales no chocan, se resuelven con temporales.
	calculo = r.calcular([_e("a.txt"), _e("b.txt")], r.OpcionesRenombrado(buscar="a|b", reemplazar="b|a"))
	assert [x.estado for x in calculo.resultados] == [r.CORRECTO, r.CORRECTO]
	calculo = r.calcular([_e("foto.jpg")], r.OpcionesRenombrado(mayusculas_nombre="mayusculas"))
	assert calculo.resultados[0].estado == r.CORRECTO
	assert calculo.resultados[0].texto == "Correcto"


def test_nombres_no_validos():
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(mascara_nombre="a:b"))
	assert calculo.resultados[0].estado == r.NO_VALIDO
	assert calculo.resultados[0].texto == "Nombre no válido: carácter :"
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(mascara_nombre="CON"))
	assert calculo.resultados[0].estado == r.NO_VALIDO and "reservado" in calculo.resultados[0].texto
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(mascara_nombre="", mascara_extension=""))
	assert calculo.resultados[0].estado == r.NO_VALIDO
	# Fuera del disco local solo se rechazan vacíos y barras.
	calculo = r.calcular([_e("a.txt")], r.OpcionesRenombrado(mascara_nombre="a:b"), validar_windows=False)
	assert calculo.resultados[0].estado == r.CORRECTO


def test_ya_existe_en_la_carpeta():
	existentes = {"C:\\Fotos": {"a.jpg", "b.jpg", "otro.jpg"}}
	calculo = r.calcular([_e("a.jpg")], r.OpcionesRenombrado(mascara_nombre="otro"), existentes=existentes)
	assert calculo.resultados[0].estado == r.YA_EXISTE
	# El nombre de otro elemento del lote que también se renombra sí se puede usar.
	calculo = r.calcular([_e("a.jpg"), _e("b.jpg")], r.OpcionesRenombrado(buscar="a|b", reemplazar="b|a"), existentes=existentes)
	assert [x.estado for x in calculo.resultados] == [r.CORRECTO, r.CORRECTO]


def test_resumen():
	calculo = r.calcular([_e("a.jpg"), _e("b.jpg"), _e("c.png")], r.OpcionesRenombrado(buscar="a", reemplazar="b"))
	assert r.resumen(calculo) == "0 se renombran, 2 sin cambios, 1 duplicado"
	calculo = r.calcular([_e("a.jpg")], r.OpcionesRenombrado(mascara_nombre="x"))
	assert r.resumen(calculo) == "1 se renombra"


def test_opciones_desde_campos_tolerante():
	opciones = r.OpcionesRenombrado(mascara_nombre="[N]_[C]", contador_digitos=3, regex=True)
	assert r.OpcionesRenombrado.desde_campos(opciones.campos()) == opciones
	raro = r.OpcionesRenombrado.desde_campos({"mascara_nombre": 5, "regex": "sí", "mayusculas_nombre": "raro", "otra": 1,
		"contador_paso": 4})
	assert raro == r.OpcionesRenombrado(contador_paso=4)


# ── Con el disco: cadenas con temporales y deshacer ─────────────────────────

class _Decisor:
	def resolver_conflictos(self, operacion, conflictos):
		return None

	def preguntar_conflicto(self, operacion, conflicto):
		raise AssertionError

	def preguntar_error(self, operacion, pregunta):
		raise AssertionError

	def elegir(self, *args, **kwargs):
		return 0

	def pedir_texto(self, *args, **kwargs):
		return None


def _ejecutar(operacion):
	gestor = GestorOperaciones(_Decisor(), max_paralelas=1, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(30)
	gestor.apagar(1)
	return operacion


def test_intercambio_con_temporales_y_deshacer(tmp_path):
	(tmp_path / "a.txt").write_text("A", encoding="utf-8")
	(tmp_path / "b.txt").write_text("B", encoding="utf-8")
	(tmp_path / "c.txt").write_text("C", encoding="utf-8")
	local = ProveedorLocal()
	entradas = sorted(local.listar(str(tmp_path)), key=lambda e: e.nombre)
	elementos = r.elementos_desde_entradas(entradas, local)
	assert elementos[0].carpeta_ruta == str(tmp_path)
	existentes = {str(tmp_path): {e.nombre for e in entradas}}
	calculo = r.calcular(elementos, r.OpcionesRenombrado(buscar="a|b", reemplazar="b|a"), existentes=existentes)
	assert not calculo.hay_problemas
	pares = r.pares(calculo)
	assert len(pares) == 2  # c.txt no cambia y no se manda
	operacion = _ejecutar(OperacionRenombrar(local, pares, "Renombrar 2 elementos"))
	assert not operacion.errores
	assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "B"
	assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "A"
	assert not any(n.startswith("~zc") for n in os.listdir(tmp_path))
	# Deshacer devuelve los nombres (también en ciclo).
	registro = RegistroDeshacer()
	registro.registrar(operacion.deshacer)
	resultado = registro.deshacer(registro.sacar_ultima())
	assert resultado.hechos == 2 and not resultado.omitidos
	assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "A"
	assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "B"


def test_cadena_a_b_c_y_deshacer(tmp_path):
	for nombre in ("1.txt", "2.txt", "3.txt"):
		(tmp_path / nombre).write_text(nombre, encoding="utf-8")
	local = ProveedorLocal()
	entradas = sorted(local.listar(str(tmp_path)), key=lambda e: e.nombre)
	# 1→2, 2→3, 3→4 con el contador desde 2.
	calculo = r.calcular(r.elementos_desde_entradas(entradas, local), r.OpcionesRenombrado(mascara_nombre="[C2]"),
		existentes={str(tmp_path): {e.nombre for e in entradas}})
	assert [x.nuevo for x in calculo.resultados] == ["2.txt", "3.txt", "4.txt"]
	assert not calculo.hay_problemas
	operacion = _ejecutar(OperacionRenombrar(local, r.pares(calculo)))
	assert not operacion.errores
	assert sorted(os.listdir(tmp_path)) == ["2.txt", "3.txt", "4.txt"]
	assert (tmp_path / "4.txt").read_text(encoding="utf-8") == "3.txt"
	registro = RegistroDeshacer()
	registro.registrar(operacion.deshacer)
	registro.deshacer(registro.sacar_ultima())
	assert sorted(os.listdir(tmp_path)) == ["1.txt", "2.txt", "3.txt"]
	assert (tmp_path / "1.txt").read_text(encoding="utf-8") == "1.txt"


def test_fecha_real_del_archivo(tmp_path):
	archivo = tmp_path / "IMG.jpg"
	archivo.write_text("x", encoding="utf-8")
	marca = time.mktime((2021, 12, 31, 23, 0, 0, 0, 0, -1))
	os.utime(archivo, (marca, marca))
	local = ProveedorLocal()
	elementos = r.elementos_desde_entradas(local.listar(str(tmp_path)), local)
	assert _nuevos(elementos, mascara_nombre="[Y]-[M]-[D]") == ["2021-12-31.jpg"]


# ── Plantillas ──────────────────────────────────────────────────────────────

def test_plantillas(datos_temporales):
	assert r.leer_plantillas() == []
	r.guardar_plantilla("Fotos", r.OpcionesRenombrado(mascara_nombre="[Y]-[C]").campos())
	r.guardar_plantilla("archivo", {"mascara_nombre": "[N]"})
	r.guardar_plantilla("fotos", r.OpcionesRenombrado(mascara_nombre="[d]").campos())  # sustituye sin distinguir mayúsculas
	nombres = [p["nombre"] for p in r.leer_plantillas()]
	assert nombres == ["archivo", "fotos"]
	assert r.OpcionesRenombrado.desde_campos(r.leer_plantillas()[1]["campos"]).mascara_nombre == "[d]"
	assert r.borrar_plantilla("ARCHIVO") is True
	assert r.borrar_plantilla("no existe") is False
	assert [p["nombre"] for p in r.leer_plantillas()] == ["fotos"]
	with pytest.raises(ValueError):
		r.guardar_plantilla("  ", {})
