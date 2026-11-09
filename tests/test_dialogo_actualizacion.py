# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Interfaz del actualizador (diseño 2.0, 5.4 y 18.2): diálogo, comprobación manual y periódica, avisos del arranque.

De la plantilla del agente «actualizador». Controles wx reales sin mostrarlos de
forma modal; el flujo de descarga corre en su hilo contra un servidor HTTP local,
sin lanzar el script real.
"""

from __future__ import annotations

import dataclasses
import types

import pytest

wx = pytest.importorskip("wx")
pytest.importorskip("cryptography")

from tests.apoyo_actualizador import Servidor, cargar_firmador, publicar  # noqa: E402
from tests.conftest import procesar_eventos  # noqa: E402

from app.services import actualizador  # noqa: E402
from app.ui import anuncios  # noqa: E402
from app.ui import dialogo_actualizacion as dialogo_mod  # noqa: E402
from app.ui.accesibilidad import dialogos  # noqa: E402
from app.ui.accesibilidad.revision_teclado import informe, revisar_teclado  # noqa: E402


@pytest.fixture
def config(tmp_path):
	instalacion = tmp_path / "Mi App"
	instalacion.mkdir()
	(instalacion / "ZCommander.exe").write_bytes(b"EXE 1.0.0")
	return actualizador.Configuracion(version_actual="1.0.0", carpeta_app=instalacion, comando=[], permitir_desde_codigo=True)


@pytest.fixture
def sonidos(monkeypatch):
	from app.services.sonidos import servicio

	pedidos: list[str] = []
	monkeypatch.setattr(servicio, "sonar", lambda evento, *a, **k: pedidos.append(evento) or True)
	return pedidos


INFO = actualizador.InfoActualizacion(
	version="1.1.0",
	archivo="zCommander_v1.1.0.zip",
	url_zip="https://ejemplo.invalid/zCommander_v1.1.0.zip",
	sha256="0" * 64,
	tamano=10,
	fecha="2026-11-08",
	novedades="- Mejora A\n- Arreglo B",
)


class VentanaFalsa:
	"""Lo que usan las piezas de AC del protocolo ``VentanaServicios`` (14.9)."""

	def __init__(self, libre: bool = True) -> None:
		self.libre = libre
		self.anuncios: list[tuple[str, str, str]] = []
		self.programadas: list[tuple[int, object]] = []
		self.enviadas: list = []
		self.salidas = 0
		self.config = types.SimpleNamespace(obtener=lambda clave: {"actualizaciones.comprobar": True,
			"actualizaciones.intervalo_horas": 24}[clave])
		self.tareas = self
		self.suscritas: dict[str, object] = {}

	# VentanaServicios
	def anunciar(self, texto, nivel="normal", completo="", sonido=""):
		self.anuncios.append((texto, nivel, sonido))

	def llamar_mas_tarde(self, ms, funcion):
		self.programadas.append((ms, funcion))

	def esta_libre(self):
		return self.libre

	def padre(self):
		return None

	def servicio(self, nombre):
		assert nombre == "eventos"
		return types.SimpleNamespace(suscribir=lambda evento, funcion: self.suscritas.__setitem__(evento, funcion))

	def salir(self):
		self.salidas += 1

	# GestorTareas: ejecuta en el acto
	def enviar(self, funcion, al_terminar=None, al_fallar=None, **_opciones):
		from app.core.tareas import TokenCancelacion

		tarea = types.SimpleNamespace(token=TokenCancelacion(), cancelar=lambda motivo="": None)
		self.enviadas.append(tarea)
		try:
			resultado = funcion(tarea)
		except Exception as error:  # noqa: BLE001 - como el gestor real, el fallo va a al_fallar
			al_fallar(error)
		else:
			al_terminar(resultado)
		return tarea


# ── Diálogo ──────────────────────────────────────────────────────────────────


def test_etiquetas_novedades_y_teclas(app_wx, config):
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO)
	try:
		assert dialogo.GetTitle() == "Actualización disponible"
		assert dialogo.boton_actualizar.GetLabel() == "&Actualizar ahora"
		assert dialogo.boton_omitir.GetLabel() == "Omitir esta &versión"
		assert dialogo.boton_mas_tarde.GetLabel() == "&Más tarde"
		assert dialogo.boton_mas_tarde.GetId() == wx.ID_CANCEL and dialogo.GetEscapeId() == wx.ID_CANCEL
		assert dialogo.GetDefaultItem() is dialogo.boton_actualizar
		assert "1.0.0" in dialogo.resumen.GetLabel() and "1.1.0" in dialogo.resumen.GetLabel()
		assert dialogo.novedades.GetValue() == "- Mejora A\n- Arreglo B"
		assert not dialogo.novedades.IsEditable()
		assert dialogo.novedades.GetWindowStyle() & wx.TE_MULTILINE
		hijos = list(dialogo.GetChildren())
		anterior = hijos[hijos.index(dialogo.novedades) - 1]
		assert isinstance(anterior, wx.StaticText) and anterior.GetLabel() == "&Novedades:"
		assert not dialogo.estado.IsShown()  # el progreso aparece al actualizar
		assert dialogo.barra.GetName() == "Progreso de la actualización"
		assert dialogo.novedades.GetHelpText() and dialogo.boton_actualizar.GetHelpText()
	finally:
		dialogo.Destroy()


def test_dialogo_pasa_revisar_teclado(app_wx, config):
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO)
	try:
		dialogo._mostrar_progreso(True)
		problemas = [p for p in revisar_teclado(dialogo) if not p.aviso]
		assert not problemas, informe(problemas)
		dialogo._al_fallar("Sin conexión.")  # con «Reintentar» tampoco hay choques
		problemas = [p for p in revisar_teclado(dialogo) if not p.aviso]
		assert not problemas, informe(problemas)
	finally:
		dialogo.Destroy()


def test_sin_novedades_lo_dice(app_wx, config):
	info = dataclasses.replace(INFO, novedades="")
	dialogo = dialogo_mod.DialogoActualizacion(None, config, info)
	try:
		assert "no ha publicado novedades" in dialogo.novedades.GetValue()
	finally:
		dialogo.Destroy()


def test_desde_codigo_no_ofrece_instalar(app_wx, config):
	config.permitir_desde_codigo = False
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO)
	try:
		assert not dialogo.boton_actualizar.IsEnabled()
		assert "código fuente" in dialogo.estado.GetValue()
	finally:
		dialogo.Destroy()


def test_foco_inicial(app_wx, config):
	periodico = dialogo_mod.DialogoActualizacion(None, config, INFO, foco_en_novedades=True)
	manual = dialogo_mod.DialogoActualizacion(None, config, INFO)
	try:
		vistos = []
		periodico.novedades.SetFocus = lambda: vistos.append("novedades")
		manual.boton_actualizar.SetFocus = lambda: vistos.append("actualizar")
		periodico._enfocar_inicial()
		manual._enfocar_inicial()
		assert vistos == ["novedades", "actualizar"]
	finally:
		periodico.Destroy()
		manual.Destroy()


def test_progreso_por_hitos_y_fases(app_wx, config):
	dichos: list[str] = []
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO, anunciar=dichos.append)
	try:
		for hecho in range(0, 1001, 7):
			dialogo.actualizar_progreso("descarga", hecho, 1000)
		dialogo.actualizar_progreso("descarga", 1000, 1000)
		dialogo.actualizar_progreso("verificacion", 0, 1)
		assert dialogo.barra.GetValue() == 0
		descargas = [texto for texto in dichos if texto.startswith("Descargando:")]
		assert [texto.split(":")[1].split("%")[0].strip() for texto in descargas] == ["25", "50", "75", "100"]
		assert dichos[-1] == "Verificando el paquete..."
		assert dialogo.estado.GetValue() == "Verificando el paquete..."
	finally:
		dialogo.Destroy()


def test_omitir_guarda_la_version(app_wx, config):
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO)
	try:
		dialogo._al_omitir(None)
		assert dialogo.resultado == dialogo.RESULTADO_OMITIR
		assert actualizador.leer_estado(config)["version_omitida"] == "1.1.0"
	finally:
		dialogo.Destroy()


def test_error_ofrece_reintentar_y_lleva_el_foco(app_wx, config):
	dichos: list[str] = []
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO, anunciar=dichos.append)
	try:
		dialogo._al_fallar("No se pudo conectar con el servidor de actualizaciones.")
		assert dialogo.boton_actualizar.GetLabel() == "&Reintentar" and dialogo.boton_actualizar.IsEnabled()
		assert dialogo.estado.GetValue().startswith("No se pudo conectar")
		assert dichos[-1].startswith("No se pudo conectar")
	finally:
		dialogo.Destroy()


def test_escape_durante_la_descarga_cancela_y_no_cierra(app_wx, config):
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO, anunciar=lambda t: None)
	try:
		dialogo._hilo = types.SimpleNamespace(is_alive=lambda: True)
		evento = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
		evento.SetKeyCode(wx.WXK_ESCAPE)
		dialogo._al_pulsar(evento)
		assert dialogo._cancelar.is_set()
		assert dialogo.resultado == dialogo.RESULTADO_MAS_TARDE and dialogo.estado.GetValue() == "Cancelando la descarga..."
	finally:
		dialogo._hilo = None
		dialogo.Destroy()


def test_flujo_completo_en_hilo(app_wx, config, tmp_path, monkeypatch, sonidos):
	firmador = cargar_firmador()
	monkeypatch.delenv(firmador.VARIABLE_CONTRASENA, raising=False)
	clave = tmp_path / "k.key"
	config.claves_publicas = (firmador.generar(clave),)
	servidor = Servidor(tmp_path / "servidor")
	try:
		publicar(servidor.carpeta, "1.1.0", {"ZCommander.exe": b"EXE 1.1.0", "lib/a.txt": b"a" * 500}, clave, novedades="- Nueva")
		config.url_manifiesto = servidor.url("version.json")
		info = None
		for _intento in range(20):  # el bucle local de este equipo corta a veces (ronda 2-4)
			try:
				info = actualizador.comprobar(config)
				break
			except actualizador.ErrorRed:
				continue
		lanzados, cierres, dichos = [], [], []
		monkeypatch.setattr(actualizador, "lanzar_sustitucion", lanzados.append)
		monkeypatch.setattr(dialogo_mod, "reglas_de_salida", lambda padre: True)
		dialogo = dialogo_mod.DialogoActualizacion(None, config, info, anunciar=dichos.append, al_cerrar_app=lambda: cierres.append(1))
		try:
			dialogo._al_actualizar(None)
			assert not dialogo.boton_actualizar.IsEnabled()
			assert dialogo.boton_mas_tarde.GetLabel() == "&Cancelar"
			assert procesar_eventos(lambda: bool(cierres) or dialogo.boton_actualizar.GetLabel() == "&Reintentar", 20)
			assert cierres, (dichos, dialogo.estado.GetValue())
			assert lanzados and lanzados[0].name == "actualizar.bat"
			assert dialogo.resultado == dialogo.RESULTADO_ACTUALIZAR
			assert any("volverá a abrirse" in texto for texto in dichos)
			assert "act.descargada" in sonidos
		finally:
			dialogo.Destroy()
	finally:
		servidor.cerrar()


def test_no_actualizar_ahora_conserva_y_mas_tarde_descarta(app_wx, config, monkeypatch, sonidos):
	lanzados = []
	monkeypatch.setattr(actualizador, "lanzar_sustitucion", lanzados.append)
	monkeypatch.setattr(dialogo_mod, "reglas_de_salida", lambda padre: False)
	preparada = config.carpeta_trabajo / "actualizar.bat"
	(config.carpeta_trabajo / "nueva").mkdir(parents=True)
	preparada.write_text("rem", encoding="utf-8")
	dialogo = dialogo_mod.DialogoActualizacion(None, config, INFO, anunciar=lambda t: None)
	try:
		dialogo._al_preparada(preparada)
		assert not lanzados and dialogo._bat_preparado == preparada
		assert dialogo.boton_actualizar.GetLabel() == "&Actualizar ahora" and dialogo.boton_actualizar.IsEnabled()
		assert "preparada" in dialogo.estado.GetValue()
		dialogo._al_mas_tarde(None)
		assert not preparada.exists() and not (config.carpeta_trabajo / "nueva").exists()
	finally:
		dialogo.Destroy()


class _Operaciones:
	def __init__(self) -> None:
		self.lista = ["copiar"]
		self.canceladas = 0

	def en_marcha(self):
		return list(self.lista)

	def cancelar_todas(self):
		self.canceladas += 1
		self.lista = []


@pytest.mark.parametrize(("eleccion", "esperado", "canceladas"), [(None, False, 0), (2, False, 0), (1, True, 1)])
def test_reglas_de_salida_con_operaciones(app_wx, monkeypatch, eleccion, esperado, canceladas):
	operaciones = _Operaciones()
	marco = wx.Frame(None)
	marco.operaciones = operaciones
	preguntas = []
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda padre, mensaje, titulo, opciones: preguntas.append(opciones) or eleccion)
	try:
		assert dialogo_mod.reglas_de_salida(marco) is esperado
		assert operaciones.canceladas == canceladas
		assert preguntas == [["&Esperar y actualizar", "Cancelar las operaciones y a&ctualizar", "&No actualizar ahora"]]
		operaciones.lista = []
		assert dialogo_mod.reglas_de_salida(marco), "sin operaciones no se pregunta"
		assert len(preguntas) == 1
	finally:
		marco.Destroy()


def test_cerrar_la_aplicacion_usa_salir_y_no_minimiza(app_wx, monkeypatch):
	llamadas = []

	class Ventana:
		def salir(self):
			llamadas.append("salir")

		def Close(self, force=False):  # noqa: N802 - API de wx
			llamadas.append("close")

	monkeypatch.setattr(wx.App, "GetTopWindow", lambda self: Ventana())
	dialogo_mod._cerrar_aplicacion()
	assert llamadas == ["salir"]


# ── Comprobación manual ──────────────────────────────────────────────────────


def test_manual_al_dia_suena_y_se_anuncia(app_wx, config, sonidos):
	dichos: list[str] = []
	dialogo_mod.informar_manual(None, config, None, None, dichos.append)
	assert sonidos == ["act.al_dia"]
	assert dichos == ["Sin novedades: zCommander está al día (versión 1.0.0)."]


def test_manual_con_error_usa_los_dialogos_accesibles(app_wx, config, monkeypatch):
	recibidos = []
	monkeypatch.setattr(dialogos, "mostrar_mensaje", lambda padre, mensaje, titulo, icono=None: recibidos.append((mensaje, titulo, icono)))
	dialogo_mod.informar_manual(None, config, None, "Sin conexión.", None)
	assert recibidos == [("Sin conexión.", "Buscar actualizaciones", wx.ICON_WARNING)]


def test_manual_con_version_nueva_abre_el_dialogo(app_wx, config, monkeypatch):
	abiertos = []
	monkeypatch.setattr(dialogo_mod, "mostrar_dialogo", lambda padre, c, info, anunciar=None, **k: abiertos.append((info, k)))
	dialogo_mod.informar_manual(None, config, INFO, None, None)
	assert abiertos == [(INFO, {})]


def test_orden_buscar_actualizaciones_comprueba_en_un_hilo(app_wx, monkeypatch):
	from app.ui.acciones import actualizar_ac

	llamadas, informados = [], []
	monkeypatch.setattr(actualizador, "comprobar", lambda c, respetar_omitida: llamadas.append(respetar_omitida))
	monkeypatch.setattr(dialogo_mod, "informar_manual", lambda *argumentos: informados.append(argumentos))
	ctx = types.SimpleNamespace(ventana=None)
	actualizar_ac.buscar_actualizaciones(ctx)
	assert procesar_eventos(lambda: bool(informados), 5)
	assert llamadas == [False]  # la manual no respeta la versión omitida
	assert informados[0][2] is None and informados[0][3] is None
	assert not getattr(actualizar_ac.buscar_actualizaciones, "provisional", False)


# ── Comprobación periódica ───────────────────────────────────────────────────


def test_comprobador_periodico_anuncia_y_espera_a_que_la_ventana_este_libre(app_wx, config, monkeypatch):
	monkeypatch.setattr(actualizador, "_comprobaciones", {})
	actualizador.registrar_comprobacion("CO", lambda token: [actualizador.Novedad("CO", "rclone 1.77.0 disponible", False)],
		lambda: True)
	monkeypatch.setattr(actualizador, "comprobar", lambda c, respetar_omitida: INFO)
	abiertos = []
	monkeypatch.setattr(dialogo_mod, "mostrar_dialogo", lambda padre, c, info, anunciar=None, **k: abiertos.append((info, k)))
	ventana = VentanaFalsa(libre=False)
	comprobador = dialogo_mod.ComprobadorPeriodico(ventana, config, ventana.config)
	comprobador.iniciar()
	assert ventana.programadas[0][0] == 60_000  # la primera, a los 60 s del arranque
	ventana.programadas.pop(0)[1]()
	assert ventana.anuncios[0] == ("rclone 1.77.0 disponible", anuncios.NORMAL, "")
	texto, nivel, sonido = ventana.anuncios[1]
	assert texto.startswith("Hay una versión nueva de zCommander: 1.1.0.") and "Ayuda, Buscar actualizaciones" in texto
	assert (nivel, sonido) == (anuncios.ESENCIAL, "act.disponible")
	assert not abiertos, "con un diálogo o un menú abiertos, no se abre solo"
	reintento = next(funcion for ms, funcion in ventana.programadas if ms == 2000)
	ventana.libre = True
	reintento()
	assert abiertos == [(INFO, {"foco_en_novedades": True})]
	assert any(ms == 3_600_000 for ms, _f in ventana.programadas)  # y vuelve a mirar cada hora
	# Ya se pasó: hasta que no se cumpla el intervalo no hay otra pasada.
	assert not comprobador.comprobar_si_toca()
	comprobador.detener()


def test_comprobador_sin_nada_activo_no_consulta(app_wx, config, monkeypatch):
	monkeypatch.setattr(actualizador, "_comprobaciones", {})
	ventana = VentanaFalsa()
	ventana.config = types.SimpleNamespace(obtener=lambda clave: {"actualizaciones.comprobar": False,
		"actualizaciones.intervalo_horas": 24}[clave])
	comprobador = dialogo_mod.ComprobadorPeriodico(ventana, config, ventana.config)
	assert not comprobador.comprobar_si_toca() and not ventana.enviadas


def test_instalar_engancha_avisos_y_comprobacion(app_wx, monkeypatch):
	from app.services import eventos
	from app.ui.acciones import actualizar_ac

	ventana = VentanaFalsa()
	actualizar_ac.instalar(ventana)
	try:
		assert not getattr(actualizar_ac.instalar, "provisional", False)
		assert actualizar_ac.comprobador() is not None
		assert ventana.programadas[0][0] == 60_000
		assert actualizador._oyente_arranque[0] is not None
		ventana.suscritas[eventos.AL_CERRAR]()
		assert actualizar_ac.comprobador() is None and actualizador._oyente_arranque[0] is None
		ventana.programadas.pop(0)[1]()  # detenido: no consulta nada
		assert not ventana.enviadas
	finally:
		actualizador.fijar_oyente_arranque(None)
	tarea = VentanaFalsa()
	tarea.arranque = types.SimpleNamespace(modo="tarea")
	actualizar_ac.instalar(tarea)
	try:
		assert actualizar_ac.comprobador() is None and not tarea.programadas
	finally:
		actualizador.fijar_oyente_arranque(None)


# ── Arranque (5.2, 5.4) ──────────────────────────────────────────────────────


def test_atender_arranque_instalada_y_revertida(app_wx, config):
	ventana = VentanaFalsa()
	dialogo_mod.atender_arranque(ventana, config, actualizador.ResultadoArranque(instalada="1.1.0"))
	assert ventana.anuncios == [("zCommander se ha actualizado a la versión 1.1.0.", anuncios.RESULTADO, "act.instalada")]
	ventana.anuncios.clear()
	dialogo_mod.atender_arranque(ventana, config, actualizador.ResultadoArranque(mensaje="Se volvió atrás.", revertida=True))
	assert ventana.anuncios == [("Se volvió atrás.", anuncios.ESENCIAL, "act.revertida")]
	assert not ventana.programadas


@pytest.mark.parametrize("eleccion", [0, 1, None])
def test_salud_sin_confirmar_pregunta_al_estar_libre(app_wx, config, monkeypatch, eleccion):
	pendiente = actualizador.SinConfirmar("1.1.0", 4242, "1.0.0")
	ventana = VentanaFalsa(libre=False)
	preguntas, seguidas, lanzados = [], [], []
	monkeypatch.setattr(dialogos, "elegir_opcion", lambda padre, mensaje, titulo, opciones: preguntas.append((mensaje, opciones))
		or eleccion)
	monkeypatch.setattr(actualizador, "seguir_con_esta_version", seguidas.append)
	monkeypatch.setattr(actualizador, "preparar_vuelta_atras", lambda c: config.carpeta_trabajo / "actualizar.bat")
	monkeypatch.setattr(actualizador, "lanzar_sustitucion", lanzados.append)
	dialogo_mod.atender_arranque(ventana, config, actualizador.ResultadoArranque(sin_confirmar=pendiente))
	ventana.programadas.pop(0)[1]()
	assert not preguntas, "no se pregunta con la ventana ocupada"
	ventana.libre = True
	ventana.programadas.pop(0)[1]()
	assert preguntas and preguntas[0][1] == ["&Volver a la versión anterior", "&Seguir con esta versión"]
	assert "1.1.0" in preguntas[0][0] and "1.0.0" in preguntas[0][0]
	if eleccion == 0:
		assert lanzados and not seguidas
		ms, cerrar = ventana.programadas[-1]
		cerrar()
		assert ms == 1500 and ventana.salidas == 1
	elif eleccion == 1:
		assert seguidas == [config] and not lanzados
	else:
		assert not seguidas and not lanzados, "cancelar deja la pregunta para el próximo arranque"


def test_restauracion_pendiente_no_se_pregunta_antes_de_ok(app_wx, tmp_path, monkeypatch, datos_temporales):
	"""Tras actualizar, la pregunta por una restauración pendiente llega después de la marca «ok» (5.2, 7.6)."""
	from app.core.configuracion import Configuracion
	from app.services import sesion
	from app.services.copia import pendiente
	from app.services.servicios_nucleo import ArranqueInfo
	from app.ui import ventana_principal as modulo_ventana

	marcador = datos_temporales / "temp" / "actualizacion" / "salud.txt"
	vistos = []

	def consultar(ruta_datos):
		vistos.append(marcador.is_file())
		return None

	monkeypatch.setattr(pendiente, "consultar_pendiente", consultar)
	monkeypatch.setattr(sesion, "cargar", lambda: {
		**sesion.POR_DEFECTO,
		"lados": {"izquierdo": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0},
			"derecho": {"pestanas": [sesion.pestana(ruta=str(tmp_path))], "actual": 0}},
	})
	config = Configuracion()
	config.establecer("general.confirmar_salida", False)
	ventana = modulo_ventana.VentanaPrincipal(config, arranque=dataclasses.replace(ArranqueInfo.nulo(), tras_actualizar=True))
	try:
		ventana._tras_mostrar()
		assert procesar_eventos(lambda: bool(vistos), 3)
		assert vistos == [True], "la restauración pendiente se consulta con «ok» ya escrito"
		assert actualizador.ultimo_arranque().instalada
	finally:
		ventana.Close(True)
		procesar_eventos(lambda: False, 0.3)
		actualizador.fijar_oyente_arranque(None)
