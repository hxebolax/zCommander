# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Notas, comentarios y etiquetas (diseño 2.0, 11.14 y 18.2): pruebas mínimas de la ficha y de su motor."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from app.services.vfs import resolver
from tests.plugins.p3_comun import RAIZ, contexto_operacion, esperar, modulo, preparar


@pytest.fixture
def entorno(tmp_path):
	zc, paquete = preparar("notas")
	return zc, modulo(paquete, "motor"), tmp_path


def test_descript_ion_con_espacios_comillas_y_no_ascii(entorno):
	_zc, motor, carpeta = entorno
	# Un descript.ion como lo deja Total Commander en ANSI (cp1252), con comillas y una línea múltiple.
	(carpeta / "descript.ion").write_bytes(
		'"mi informe.txt" Revisar el lunes\r\nfactura.pdf Pagada en efectivo\r\n"año 2026.xlsx" Línea 1\\nLínea 2\x04\xc2\r\n'.encode("cp1252"))
	descript = motor.leer_descript(str(carpeta))
	assert descript.entradas["mi informe.txt"] == ("mi informe.txt", "Revisar el lunes")
	assert descript.entradas["factura.pdf"][1] == "Pagada en efectivo"
	assert descript.entradas["año 2026.xlsx"][1] == "Línea 1\nLínea 2"
	assert descript.codificacion in ("mbcs", "cp1252")
	# Escribir y volver a leer conserva todo, también las comillas y la línea múltiple.
	descript.entradas["canción ñ.mp3"] = ("canción ñ.mp3", "Para el viaje")
	motor.escribir_descript(str(carpeta), descript)
	crudo = (carpeta / "descript.ion").read_bytes().decode(descript.codificacion if descript.codificacion != "mbcs" else "mbcs")
	assert '"mi informe.txt" Revisar el lunes' in crudo and '"canción ñ.mp3" Para el viaje' in crudo
	assert "Línea 1\\nLínea 2\x04\xc2" in crudo
	otra = motor.leer_descript(str(carpeta))
	assert otra.entradas == descript.entradas


def test_comentario_nuevo_crea_descript_ion_oculto_en_utf8(entorno):
	zc, motor, carpeta = entorno
	archivo = carpeta / "ñandú con espacios.txt"
	archivo.write_text("hola", encoding="utf-8")
	almacen = zc.instancia.almacen
	assert almacen.fijar_comentario(str(archivo), "Nota con acentos: ¿qué tal?\nY otra línea") == "descript_ion"
	descript = carpeta / "descript.ion"
	assert descript.read_bytes().startswith(b"\xef\xbb\xbf")
	assert os.stat(descript).st_file_attributes & 0x2  # oculto, como lo dejan los demás gestores
	assert almacen.comentario(str(archivo)) == "Nota con acentos: ¿qué tal?\nY otra línea"
	# Se puede volver a escribir aunque esté oculto, y borrar el último comentario quita el archivo.
	almacen.fijar_comentario(str(archivo), "Otro")
	assert almacen.comentario(str(archivo)) == "Otro"
	almacen.fijar_comentario(str(archivo), "")
	assert not descript.exists()


def test_base_central_y_raiz_de_unidad(entorno):
	zc, motor, carpeta = entorno
	almacen = motor.Almacen(zc.datos / "notas.db", "base_central")
	archivo = carpeta / "x.txt"
	archivo.write_text("x", encoding="utf-8")
	assert almacen.fijar_comentario(str(archivo), "En la base") == "base_central"
	assert not (carpeta / "descript.ion").exists()
	assert almacen.comentario(str(archivo)) == "En la base"
	assert (zc.datos / "notas.db").is_file()


def test_un_comentario_viaja_al_copiar_el_archivo(entorno):
	zc, _motor, carpeta = entorno
	origen, destino = carpeta / "origen", carpeta / "destino"
	origen.mkdir()
	destino.mkdir()
	archivo = origen / "plano casa.dwg"
	archivo.write_text("plano", encoding="utf-8")
	(destino / "plano casa.dwg").write_text("ya estaba", encoding="utf-8")  # conflicto: la copia se renombra
	almacen = zc.instancia.almacen
	almacen.fijar_comentario(str(archivo), "Versión final")
	zc.instancia.etiquetar(str(archivo), "Urgente")
	local = resolver.proveedor_local()
	entrada = local.info(str(archivo))
	opciones = api.OpcionesCopia(politica=api.Politica.RENOMBRAR_COPIA, lista_conflictos=False)
	operacion = api.OperacionCopiar(local, [entrada], local, str(destino), opciones)
	ctx = contexto_operacion()
	operacion.contexto = ctx
	ctx.operacion = operacion
	operacion.ejecutar(ctx)
	(_o, copiado), = operacion.pares_hechos()
	assert os.path.basename(copiado) != "plano casa.dwg"
	zc.emitir("al_terminar_operacion", operacion=operacion)
	assert esperar(lambda: almacen.comentario(copiado) == "Versión final")
	assert almacen.etiquetas(copiado) == ["Urgente"]
	assert almacen.comentario(str(archivo)) == "Versión final"  # al copiar, el original lo conserva
	assert almacen.comentario(str(destino / "plano casa.dwg")) == ""


def test_al_mover_el_comentario_se_va_con_el_archivo(entorno):
	zc, _motor, carpeta = entorno
	origen, destino = carpeta / "a", carpeta / "b"
	origen.mkdir()
	destino.mkdir()
	archivo = origen / "f.txt"
	archivo.write_text("f", encoding="utf-8")
	(origen / "otro.txt").write_text("o", encoding="utf-8")
	almacen = zc.instancia.almacen
	almacen.fijar_comentario(str(archivo), "Se mueve")
	almacen.fijar_comentario(str(origen / "otro.txt"), "Se queda")
	zc.instancia.viajar([(str(archivo), str(destino / "f.txt"))], mover=True)
	assert almacen.comentario(str(destino / "f.txt")) == "Se mueve"
	assert almacen.comentario(str(archivo)) == ""
	assert almacen.comentario(str(origen / "otro.txt")) == "Se queda"


def test_una_nota_se_anuncia_al_entrar(entorno):
	zc, _motor, carpeta = entorno
	con_nota = carpeta / "Facturas 2026"
	con_nota.mkdir()
	(carpeta / "sin nota").mkdir()
	zc.instancia.almacen.fijar_comentario(str(con_nota), "Pagar antes del día 5")
	assert (carpeta / "descript.ion").is_file()  # la nota de una carpeta va en el descript.ion de su superior
	panel = SimpleNamespace(lado="izquierdo")
	local = resolver.proveedor_local()
	zc.emitir("al_cambiar_carpeta", panel=panel, proveedor=local, ruta=str(carpeta / "sin nota"))
	zc.emitir("al_cambiar_carpeta", panel=panel, proveedor=local, ruta=str(con_nota))
	assert esperar(lambda: ("Esta carpeta tiene una nota", api.NORMAL) in zc.anuncios)
	assert zc.sonidos_pedidos == ["zc.notas:nota_carpeta"]
	assert zc.anuncios.count(("Esta carpeta tiene una nota", api.NORMAL)) == 1
	# La orden la lee; en «..» Ctrl+N edita la nota de la carpeta.
	zc.ejecutar("leer_nota", pruebas.contexto_de_prueba(activo=pruebas.PanelFalso(ruta=str(con_nota))))
	assert ("Pagar antes del día 5", api.RESULTADO) in zc.anuncios


def test_no_se_anuncia_si_esta_desactivado(entorno):
	zc, _motor, carpeta = entorno
	zc.config.establecer("anunciar_notas", False)
	(carpeta / "c").mkdir()
	zc.instancia.almacen.fijar_comentario(str(carpeta / "c"), "nota")
	zc.emitir("al_cambiar_carpeta", panel=SimpleNamespace(lado="derecho"), proveedor=resolver.proveedor_local(), ruta=str(carpeta / "c"))
	assert not esperar(lambda: zc.anuncios, 0.3)


def test_etiquetas_en_texto_con_su_color_y_columnas(entorno):
	zc, motor, carpeta = entorno
	archivo = carpeta / "a.pdf"
	archivo.write_text("a", encoding="utf-8")
	etiquetar = registro.exportados("zc.notas")["etiquetar"]
	etiquetar(str(archivo), "Urgente")
	etiquetar(str(archivo), "Proyecto Sol")
	assert {"nombre": "Proyecto Sol", "color": ""} in zc.config.obtener("etiquetas")
	entrada = resolver.proveedor_local().info(str(archivo))
	assert zc.columna("etiquetas", entrada) == "Proyecto Sol, Urgente (rojo)"
	zc.instancia.almacen.fijar_comentario(str(archivo), "Primera\nSegunda")
	assert zc.columna("comentario", entrada) == "Primera"
	assert motor.texto_etiquetas(["Facturas"], zc.config.obtener("etiquetas")) == "Facturas (verde)"


def test_buscar_por_comentario_y_por_etiqueta(entorno):
	zc, _motor, carpeta = entorno
	almacen = zc.instancia.almacen
	for nombre in ("uno.txt", "sub/dos.txt", "sub/tres.txt"):
		ruta = carpeta / nombre
		ruta.parent.mkdir(parents=True, exist_ok=True)
		ruta.write_text("x", encoding="utf-8")
	almacen.fijar_comentario(str(carpeta / "uno.txt"), "Factura de la luz")
	almacen.fijar_comentario(str(carpeta / "sub" / "dos.txt"), "factura del agua")
	almacen.etiquetar(str(carpeta / "sub" / "tres.txt"), "Facturas")
	almacen.etiquetar(str(carpeta / "sub" / "dos.txt"), "Facturas")
	assert [Path(r).name for r in almacen.buscar(str(carpeta), "FACTURA")] == ["dos.txt", "uno.txt"]
	assert [Path(r).name for r in almacen.buscar(str(carpeta), "factura", subcarpetas=False)] == ["uno.txt"]
	assert [Path(r).name for r in almacen.buscar(str(carpeta), "", "Facturas")] == ["dos.txt", "tres.txt"]
	assert [Path(r).name for r in almacen.buscar(str(carpeta), "agua", "Facturas")] == ["dos.txt"]


def test_ordenes_con_manejador_real_y_sonido_en_los_paquetes():
	zc, _paquete = preparar("notas")
	for orden in ("comentario", "leer_nota", "etiquetas", "buscar"):
		funcion = registro.manejador(f"zc.notas:{orden}")
		assert funcion is not None and not getattr(funcion, "provisional", False)
	assert callable(registro.exportados("zc.notas")["etiquetar"])
	for paquete in ("clasico", "cristal", "minimalista", "retro", "suave"):
		assert (RAIZ / "data" / "sounds" / paquete / "plugins" / "zc.notas" / "nota_carpeta.wav").is_file()
	assert (RAIZ / "plugins" / "notas" / "sonidos" / "nota_carpeta.wav").is_file()
	assert zc.config.obtener("almacen") == "descript_ion"


def test_etiquetar_tiene_la_firma_de_la_tabla_de_11_0():
	import inspect

	preparar("notas")
	firma = inspect.signature(registro.exportados("zc.notas")["etiquetar"])
	assert list(firma.parameters) == ["ruta", "etiqueta"]
	assert firma.return_annotation in (None, "None")
