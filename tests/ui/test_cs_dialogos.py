# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos y órdenes del bloque CS (diseño 2.0, 7.5, 7.6, 10.2 y 18.2).

Los diálogos se construyen SIN mostrarlos. Avisos, preguntas y cuadros de
archivo pasan por ``app.ui.dialogos.cs_comun`` y se sustituyen aquí.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import procesar_eventos

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services.copia import crear, formato, perfil, restaurar  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.acciones import copia_cs  # noqa: E402
from app.ui.dialogos import cs_comun, cs_crear, cs_perfil, cs_restaurar  # noqa: E402

CONTRASENA = "una contraseña bien larga"


@pytest.fixture
def respuestas(monkeypatch):
	estado = SimpleNamespace(avisos=[], preguntas=[], elecciones=[], si=True, eleccion=0, carpeta=None)
	monkeypatch.setattr(cs_comun, "avisar", lambda padre, texto, titulo="": estado.avisos.append(texto))
	monkeypatch.setattr(cs_comun, "informar", lambda padre, texto, titulo="": estado.avisos.append(texto))

	def preguntar(padre, texto, titulo="", peligroso=True):
		estado.preguntas.append(texto)
		return estado.si

	def elegir(padre, texto, titulo, opciones):
		estado.elecciones.append((texto, list(opciones)))
		return estado.eleccion(texto) if callable(estado.eleccion) else estado.eleccion

	monkeypatch.setattr(cs_comun, "preguntar", preguntar)
	monkeypatch.setattr(cs_comun, "elegir", elegir)
	monkeypatch.setattr(cs_comun, "elegir_carpeta", lambda padre, titulo, inicial="": estado.carpeta)
	return estado


def escribir_json(carpeta: Path, relativa: str, datos) -> None:
	ruta = carpeta / relativa
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_text(json.dumps(datos), encoding="utf-8")


@pytest.fixture
def origen(tmp_path) -> Path:
	carpeta = tmp_path / "origen"
	escribir_json(carpeta, "config/settings.json", {"vista": {"tamano_fuente": 14}, "editor": {"externo": "malo.exe %P"}})
	escribir_json(carpeta, "config/favoritos.json", {"version": 1, "favoritos": [{"nombre": "Fotos", "ruta": "D:\\Fotos"}]})
	escribir_json(carpeta, "config/alias.json", {"version": 1, "alias": [{"nombre": "ll", "orden": "dir /a %1"}]})
	escribir_json(carpeta, "config/macros.json", {"version": 1, "macros": [{"nombre": "M", "pasos": []}]})
	known = "sftp.ejemplo.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEbP8ZAzLyrBt3m7y8hjo9uQKmxBQ2mo6R5W6hyIqvUq\n"
	(carpeta / "config" / "known_hosts").write_text(known, encoding="utf-8")
	escribir_json(carpeta, "config/conexiones.json", {"version": 1, "sitios": [{"id": "s1"}]})
	from app.core.secretos import AlmacenSecretos

	AlmacenSecretos(carpeta / "config" / "secretos.dat").guardar("ftp:s1:contrasena", "secreta")
	return carpeta


@pytest.fixture
def copia(origen, tmp_path) -> Path:
	return crear.crear_copia(tmp_path / "c.zcbackup", formato.PARTES_POR_DEFECTO, "copia", "contrasena", CONTRASENA,
		"Antes de cambiar de equipo", ruta_datos=origen)


@pytest.fixture
def destino(datos_temporales) -> Path:
	datos_temporales.mkdir(parents=True, exist_ok=True)
	return datos_temporales


# ── Crear ─────────────────────────────────────────────────────────────────────

def test_dialogo_crear_teclado_y_validacion(app_wx, respuestas, tmp_path):
	dialogo = cs_crear.DialogoCrearCopia(None, tmp_path, list(formato.PARTES_POR_DEFECTO), {"preferencias": 4096})
	try:
		afirmar_teclado_correcto(dialogo)
		assert dialogo.partes_marcadas() == list(formato.PARTES_POR_DEFECTO)
		assert not dialogo.lista_partes.IsChecked(dialogo.ids.index("registros"))
		assert "4 KB" in dialogo.lista_partes.GetString(0)
		dialogo.campo_contrasena.SetValue("corta")
		assert dialogo.campo_fortaleza.GetValue().startswith("Débil: menos de 12 caracteres")
		dialogo.campo_repetir.SetValue("otra")
		dialogo._aceptar()
		assert dialogo.resultado is None and "no coinciden" in respuestas.avisos[-1]
		dialogo.campo_contrasena.SetValue(CONTRASENA)
		dialogo.campo_repetir.SetValue(CONTRASENA)
		dialogo.campo_descripcion.SetValue("Prueba")
		dialogo._aceptar()
		resultado = dialogo.resultado
		assert resultado.modo_secretos == "contrasena" and resultado.contrasena == CONTRASENA
		assert resultado.destino.suffix == ".zcbackup" and resultado.descripcion == "Prueba"
		dialogo.resultado = None
		dialogo.opcion_excluir.SetValue(True)
		dialogo._actualizar()
		assert not dialogo.campo_contrasena.IsEnabled()
		dialogo._aceptar()
		assert dialogo.resultado.modo_secretos == "excluidos" and dialogo.resultado.contrasena is None
	finally:
		dialogo.Destroy()


def test_orden_copia_crear_lanza_la_operacion_y_recuerda_las_partes(app_wx, monkeypatch, tmp_path, destino):
	config = Configuracion(destino / "config" / "settings.json")
	lanzadas = []
	opciones = cs_crear.OpcionesCrear(tmp_path / "x.zcbackup", ["macros", "sonidos"], "excluidos", None, "")
	monkeypatch.setattr(cs_crear, "pedir", lambda padre, carpeta, marcadas, tamanos: opciones)
	ctx = SimpleNamespace(config=config, ventana=None, argumento=None,
		lanzar=lambda operacion, al_terminar=None: lanzadas.append((operacion, al_terminar)))
	copia_cs.copia_crear(ctx)
	operacion, _al_terminar = lanzadas[0]
	assert operacion.partes == ["macros", "sonidos"] and config.obtener("copia.partes") == ["macros", "sonidos"]
	from app.core.tareas import TokenCancelacion
	from app.services.operaciones.modelo import ContextoEjecucion, Estado

	operacion.contexto = ContextoEjecucion(TokenCancelacion(), None)
	operacion.ejecutar(operacion.contexto)
	operacion.cambiar_estado(Estado.TERMINADA)
	assert operacion.resumen().startswith("Copia creada: ") and operacion.resumen().endswith("2 partes")


# ── Restaurar ─────────────────────────────────────────────────────────────────

def _dialogo_restaurar(copia: Path, destino: Path) -> cs_restaurar.DialogoRestaurarCopia:
	dialogo = cs_restaurar.DialogoRestaurarCopia(None, "", destino)
	dialogo.campo_archivo.SetValue(str(copia))
	dialogo.cargar(cs_restaurar.leer_copia(copia, destino))
	return dialogo


def test_dialogo_restaurar_teclado_y_ordenes_sin_marcar(app_wx, respuestas, copia, destino):
	dialogo = _dialogo_restaurar(copia, destino)
	try:
		afirmar_teclado_correcto(dialogo)
		# Restaurar es arriesgado: Intro cancela (15.1).
		assert dialogo.GetDefaultItem().GetId() == wx.ID_CANCEL
		assert "Antes de cambiar de equipo" in dialogo.campo_resumen.GetValue()
		assert dialogo.campo_contrasena.IsEnabled()
		textos = [dialogo.lista_ordenes.GetString(i) for i in range(dialogo.lista_ordenes.GetCount())]
		assert "Alias ll: dir /a %1" in textos and "Editor externo: malo.exe %P" in textos
		assert not any(dialogo.lista_ordenes.IsChecked(i) for i in range(dialogo.lista_ordenes.GetCount()))
		dialogo.marcar_orden("alias:ll")
		# Quitar una parte quita sus órdenes; volver a marcarla recupera lo marcado.
		indice = dialogo.ids_partes.index("personalizacion")
		dialogo.lista_partes.Check(indice, False)
		dialogo._refrescar_ordenes()
		assert "alias:ll" not in [e.id for e in dialogo.visibles]
		dialogo.lista_partes.Check(indice, True)
		dialogo._refrescar_ordenes()
		assert dialogo.lista_ordenes.IsChecked([e.id for e in dialogo.visibles].index("alias:ll"))
	finally:
		dialogo.Destroy()


def test_contrasena_incorrecta_permite_reintentar_sin_perder_lo_elegido(app_wx, respuestas, copia, destino):
	dialogo = _dialogo_restaurar(copia, destino)
	try:
		dialogo.marcar_orden("alias:ll")
		dialogo.campo_contrasena.SetValue("mala")
		dialogo._aceptar()
		assert procesar_eventos(lambda: not dialogo.ocupado and respuestas.avisos, 15)
		assert respuestas.avisos[-1] == "La contraseña no es correcta o la copia está dañada."
		assert dialogo.resultado is None and "alias:ll" in dialogo.marcas
		respuestas.eleccion = 0  # «No aceptarla», la predeterminada, para cada huella
		dialogo.campo_contrasena.SetValue(CONTRASENA)
		dialogo._aceptar()
		assert procesar_eventos(lambda: dialogo.resultado is not None, 15)
	finally:
		dialogo.Destroy()
	resultado = dialogo.resultado
	assert resultado.secretos == {"ftp:s1:contrasena": "secreta"}
	assert resultado.plan.marcados == {"alias:ll"} and "clave:editor.externo" in resultado.plan.excluidos
	assert resultado.plan.modo == "combinar" and resultado.plan.huellas_aceptadas == set()
	texto, opciones = respuestas.elecciones[0]
	assert "sftp.ejemplo.com, puerto 22" in texto and opciones == ["&No aceptarla", "&Aceptarla"]


def test_restaurar_sin_contrasena_pregunta_y_sigue_sin_secretos(app_wx, respuestas, copia, destino):
	dialogo = _dialogo_restaurar(copia, destino)
	try:
		respuestas.eleccion = 1  # Aceptar la huella
		dialogo._aceptar()
		assert "¿Restaurar sin ellas?" in respuestas.preguntas[0]
		assert dialogo.resultado.secretos is None
		assert len(dialogo.resultado.plan.huellas_aceptadas) == 1
	finally:
		dialogo.Destroy()


def test_sustituir_avisa_de_las_huellas_y_no_las_pregunta(app_wx, respuestas, copia, destino):
	dialogo = _dialogo_restaurar(copia, destino)
	try:
		dialogo.opcion_sustituir.SetValue(True)
		respuestas.si = True
		dialogo.campo_contrasena.SetValue("")
		dialogo._aceptar()
		assert any("huellas de servidores" in p for p in respuestas.preguntas)
		assert not respuestas.elecciones and dialogo.resultado.plan.modo == "sustituir"
	finally:
		dialogo.Destroy()


def test_copia_ilegible_se_explica(app_wx, respuestas, tmp_path, destino):
	malo = tmp_path / "malo.zcbackup"
	malo.write_bytes(b"no es un zip")
	dialogo = cs_restaurar.DialogoRestaurarCopia(None, str(malo), destino)
	try:
		assert procesar_eventos(lambda: respuestas.avisos, 10)
		assert respuestas.avisos[0] == "El archivo no es una copia de seguridad de zCommander o está dañado."
		dialogo._aceptar()
		assert dialogo.resultado is None
	finally:
		dialogo.Destroy()


def test_orden_restaurar_prepara_la_pendiente_y_ofrece_reiniciar(app_wx, respuestas, monkeypatch, copia, destino):
	plan = restaurar.PlanRestauracion(partes=["preferencias"])
	eleccion = cs_restaurar.EleccionRestaurar(copia, plan, None)
	argumentos = []
	monkeypatch.setattr(cs_restaurar, "pedir", lambda padre, ruta="": argumentos.append(ruta) or eleccion)
	lanzadas = []
	ordenes = []
	ventana = SimpleNamespace(ejecutar_orden=lambda orden, *a, **k: ordenes.append(orden))
	ctx = SimpleNamespace(ventana=ventana, argumento=str(copia), config=None,
		lanzar=lambda operacion, al_terminar=None: lanzadas.append((operacion, al_terminar)))
	copia_cs.copia_restaurar(ctx)
	assert argumentos == [str(copia)]
	operacion, al_terminar = lanzadas[0]
	assert not operacion.inmediata
	from app.core.tareas import TokenCancelacion
	from app.services.copia import pendiente
	from app.services.operaciones.modelo import ContextoEjecucion

	operacion.ejecutar(ContextoEjecucion(TokenCancelacion(), None))
	assert pendiente.consultar_pendiente(destino).descripcion == "Antes de cambiar de equipo"
	respuestas.eleccion = 0
	al_terminar(operacion)
	assert ordenes == ["reiniciar"]
	assert json.loads((pendiente.carpeta_pendiente(destino) / "restaurar.json").read_text(encoding="utf-8"))["reiniciar_ahora"]


# ── Perfiles ──────────────────────────────────────────────────────────────────

def test_dialogo_exportar_perfil(app_wx, respuestas, tmp_path):
	dialogo = cs_perfil.DialogoExportarPerfil(None, tmp_path)
	try:
		afirmar_teclado_correcto(dialogo)
		dialogo.casilla_sonidos.SetValue(True)
		dialogo._aceptar()
		assert dialogo.resultado.incluir_sonidos and dialogo.resultado.destino.suffix == ".zcperfil"
	finally:
		dialogo.Destroy()


def test_dialogo_importar_perfil_con_vista_previa(app_wx, respuestas, origen, destino, tmp_path):
	ruta = perfil.exportar(tmp_path / "curso.zcperfil", ruta_datos=origen)
	config = Configuracion(destino / "config" / "settings.json")
	dialogo = cs_perfil.DialogoImportarPerfil(None, config, "", destino)
	try:
		dialogo.campo_archivo.SetValue(str(ruta))
		dialogo.cargar(cs_perfil.leer_perfil(ruta, config, destino))
		afirmar_teclado_correcto(dialogo)
		filas = [dialogo.lista.valores_fila(i) for i in range(dialogo.lista.numero_filas())]
		assert ["Tamaño de la letra de las listas", "10", "14"] in filas or any(f[2] == "14" for f in filas)
		assert dialogo.lista.filas_marcadas() == list(range(dialogo.lista.numero_filas()))
		textos = [dialogo.lista_ordenes.GetString(i) for i in range(dialogo.lista_ordenes.GetCount())]
		assert "Alias ll: dir /a %1" in textos and any(t.startswith("Macro M") for t in textos)
		assert not any(dialogo.lista_ordenes.IsChecked(i) for i in range(dialogo.lista_ordenes.GetCount()))
		dialogo._aceptar()
		assert dialogo.resultado.ejecutables == [] and dialogo.resultado.filas
	finally:
		dialogo.Destroy()


def test_importar_una_copia_como_perfil_se_rechaza(origen, copia):
	with pytest.raises(formato.ErrorCopia):
		cs_perfil.leer_perfil(copia, Configuracion(origen / "config" / "settings.json"))


# ── Complementos de una copia ─────────────────────────────────────────────────

def test_instalar_ofrece_los_complementos_por_la_instalacion_normal(app_wx, respuestas, destino):
	carpeta = restaurar.carpeta_por_instalar(destino)
	carpeta.mkdir(parents=True)
	(carpeta / "prueba.git.zcplugin").write_bytes(b"PK")
	(carpeta / "viejo.zcplugin").write_bytes(b"PK")
	escribir_json(carpeta, "pendientes.json", {"version": 1, "complementos": [
		{"id": "prueba.git", "version": "1.2.0", "archivo": "prueba.git.zcplugin"}]})
	programadas, ordenes = [], []

	class Ventana:
		def llamar_mas_tarde(self, ms, funcion):
			programadas.append(funcion)

		def esta_libre(self):
			return True

		def padre(self):
			return self

		def ejecutar_orden(self, orden, lado=None, *, argumento=None):
			ordenes.append((orden, argumento))

	copia_cs.instalar(Ventana())
	assert not (carpeta / "viejo.zcplugin").exists()
	respuestas.eleccion = 0  # Instalar todos
	programadas.pop()()
	assert ordenes == [("complemento_instalar", str(carpeta / "prueba.git.zcplugin"))]
	assert "prueba.git 1.2.0" in respuestas.elecciones[0][0]
	assert restaurar.leer_por_instalar(destino) == []
	assert copia_cs.ofrecer_complementos(Ventana()) is False
