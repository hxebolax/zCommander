# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ocupación del disco accesible (diseño 2.0, 11.8 y 18.2): pruebas mínimas de la ficha y de su motor."""

from __future__ import annotations

import _winapi
import os
import threading

import pytest

from app.plugins import api
from tests.plugins.p3_comun import contexto_operacion, modulo, preparar


@pytest.fixture
def entorno(tmp_path):
	zc, paquete = preparar("ocupacion")
	return zc, paquete, modulo(paquete, "motor"), tmp_path


def _archivo(ruta, tamano: int) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_bytes(b"x" * tamano)


def _arbol(raiz) -> None:
	"""1 000 bytes en total: Vídeos 600 (400 + 200 en Viejos), Música 300, raíz 100."""
	_archivo(raiz / "Vídeos" / "a.mp4", 400)
	_archivo(raiz / "Vídeos" / "Viejos" / "b.mp4", 200)
	_archivo(raiz / "Música" / "c.mp3", 300)
	_archivo(raiz / "leeme.txt", 100)


def test_un_arbol_con_tamanos_conocidos_da_los_porcentajes_exactos(entorno):
	_zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	analisis = motor.analizar(str(raiz))
	assert analisis.completo
	assert (analisis.nodo.tamano, analisis.nodo.archivos, analisis.nodo.carpetas) == (1000, 4, 3)
	videos, musica = analisis.nodo.hijos
	assert (videos.nombre, videos.tamano, videos.archivos) == ("Vídeos", 600, 2)
	assert (musica.nombre, musica.tamano) == ("Música", 300)
	assert motor.porcentaje(videos.tamano, analisis.nodo.tamano) == "60 %"
	viejos = analisis.buscar(str(raiz / "Vídeos" / "Viejos"))
	assert motor.porcentaje(viejos.tamano, videos.tamano) == "33,3 %"
	assert motor.porcentaje(viejos.tamano, analisis.nodo.tamano) == "20 %"
	assert motor.describir(videos, analisis.nodo.tamano) == "Vídeos: 600 bytes, 60 %, 2 archivos"
	assert [a.tamano for a in analisis.mayores] == [400, 300, 200, 100]
	assert analisis.extensiones_ordenadas()[0] == ("mp4", 600, 2)


def test_el_proveedor_ocupacion_lista_y_sube(entorno):
	zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	analisis = motor.analizar(str(raiz))
	zc.instancia.analisis[analisis.id] = analisis
	proveedor, ruta = zc.instancia.fabrica(analisis.direccion)
	assert proveedor.esquema == "ocupacion" and ruta == str(raiz)
	entradas = proveedor.listar(ruta)
	assert [(e.nombre, e.es_carpeta, e.tamano) for e in entradas] == [("Vídeos", True, 600), ("Música", True, 300), ("leeme.txt", False, 100)]
	videos = entradas[0]
	assert proveedor.padre(videos.ruta) == str(raiz)
	assert proveedor.padre(str(raiz)) is None
	dentro = proveedor.listar(videos.ruta)
	assert [e.nombre for e in dentro] == ["a.mp4", "Viejos"]
	assert proveedor.padre(dentro[1].ruta) == videos.ruta
	assert "Ocupación de" in proveedor.mostrar(videos.ruta)
	assert not proveedor.capacidades.escribir
	with proveedor.abrir_lectura(dentro[0].ruta) as archivo:
		assert len(archivo.read()) == 400
	# Columnas del complemento.
	assert zc.columna("porcentaje_padre", dentro[1], proveedor) == "33,3 %"
	assert zc.columna("porcentaje_total", videos, proveedor) == "60 %"
	assert zc.columna("archivos", videos, proveedor) == "2"
	assert zc.columna("porcentaje_total", videos, None) is None


def test_las_uniones_no_se_siguen(entorno):
	_zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	fuera = carpeta / "fuera"
	_archivo(fuera / "enorme.bin", 5000)
	_winapi.CreateJunction(str(fuera), str(raiz / "union"))
	analisis = motor.analizar(str(raiz))
	assert analisis.nodo.tamano == 1000
	assert analisis.buscar(str(raiz / "union")) is None
	siguiendo = motor.analizar(str(raiz), motor.Opciones(seguir_enlaces=True))
	assert siguiendo.nodo.tamano == 6000


def test_cancelar_deja_el_analisis_parcial_marcado_como_incompleto(entorno):
	_zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	cancelacion = threading.Event()
	vistas: list[str] = []

	def avanzar(ruta, _archivos, _bytes) -> None:
		vistas.append(ruta)
		if len(vistas) == 2:
			cancelacion.set()

	analisis = motor.analizar(str(raiz), cancelacion=cancelacion, al_avanzar=avanzar)
	assert not analisis.completo
	assert analisis.nodo.tamano < 1000
	assert "incompleto" in analisis.resumen()


def test_la_operacion_cancelada_queda_incompleta(entorno):
	_zc, _paquete, motor, carpeta = entorno
	_arbol(carpeta / "datos")
	operacion = motor.OperacionAnalizar(str(carpeta / "datos"), motor.Opciones())
	ctx = contexto_operacion(cancelado=True)
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	assert operacion.estado == api.Estado.CANCELADA
	assert not operacion.analisis.completo


def test_el_ultimo_analisis_se_recuerda(entorno):
	zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	analisis = motor.analizar(str(raiz))
	guardado = motor.guardar(analisis, zc.instancia.carpeta_analisis)
	assert guardado.parent == zc.datos / "analisis"
	leido = motor.cargar(zc.instancia.carpeta_analisis, motor.id_de(str(raiz)))
	assert leido is not None and leido.nodo.tamano == 1000 and leido.buscar(str(raiz / "Vídeos" / "Viejos")).tamano == 200
	assert [a.ruta for a in leido.mayores] == [a.ruta for a in analisis.mayores]
	zc.instancia.analisis.clear()
	proveedor, ruta = zc.instancia.fabrica(f"ocupacion://{analisis.id}/")
	assert proveedor.analisis.nodo.tamano == 1000 and ruta == str(raiz)
	with pytest.raises(api.NoEncontrado):
		zc.instancia.fabrica("ocupacion://000000000000/")


def test_informes(entorno):
	_zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	analisis = motor.analizar(str(raiz))
	texto = motor.informe_texto(analisis)
	assert "Vídeos: 600 bytes, 60 %, 2 archivos" in texto
	csv = motor.informe_csv(analisis).splitlines()
	assert csv[0].startswith("Carpeta;Bytes;Porcentaje del padre")
	assert len(csv) == 5
	assert motor.lista_csv(analisis.mayores).count("\n") == 5


def test_ir_lleva_el_otro_panel_a_lo_real(entorno, monkeypatch):
	zc, _paquete, motor, carpeta = entorno
	from app.plugins.api import pruebas

	raiz = carpeta / "datos"
	_arbol(raiz)
	analisis = motor.analizar(str(raiz))
	proveedor = motor.ProveedorOcupacion(analisis)
	idas: list[tuple[str, str | None]] = []
	monkeypatch.setattr(zc, "abrir_ruta", lambda texto, lado=None: idas.append((texto, lado)))
	activo = pruebas.PanelFalso(proveedor.listar(str(raiz)), ruta=str(raiz), proveedor=proveedor)
	zc.ejecutar("ir", pruebas.contexto_de_prueba(activo=activo))
	assert idas == [(str(raiz / "Vídeos"), "derecho")]
	zc.ejecutar("ir", pruebas.contexto_de_prueba())
	assert ("Esta orden sirve en un panel con un análisis de ocupación", api.ESENCIAL) in zc.anuncios
	assert os.path.isdir(idas[0][0])


def test_tamano_en_el_disco_redondea_al_cluster(entorno):
	_zc, _paquete, motor, carpeta = entorno
	raiz = carpeta / "datos"
	_arbol(raiz)
	en_disco = motor.analizar(str(raiz), motor.Opciones(tamano_en_disco=True))
	cluster = motor._cluster(str(raiz))
	assert en_disco.nodo.tamano >= 1000
	assert en_disco.nodo.tamano % cluster == 0 or en_disco.nodo.tamano < 4 * cluster
