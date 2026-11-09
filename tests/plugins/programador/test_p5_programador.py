# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de zc.programador (diseño 2.0, 11.24 y 18.2). Nunca crea tareas reales en Windows: el COM es falso.

Las pruebas de ``--tarea``, del buzón, del modo tarea y del autocierre son de
N2 (``tests/test_n2_instancia.py`` y ``tests/ui/test_n2_ventana.py``): aquí se
prueba lo que hace el complemento cuando ``cargador.ejecutar_tarea_programada``
llama a su ``ejecutar_tarea``.
"""

from __future__ import annotations

import datetime
import os
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from app.plugins import api, registro
from app.plugins.api import pruebas
from tests.plugins import p5_comun

NOMBRE = "programador"


def _anfitrion():
	"""Anfitrión con el Programador de Windows simulado: ninguna prueba crea tareas reales."""
	creado = p5_comun.anfitrion(NOMBRE)
	windows = p5_comun.modulo(NOMBRE, "windows")
	creado.instancia.windows = windows.ProgramadorWindows(lambda: _ServicioFalso())
	return creado


@pytest.fixture
def zc():
	creado = _anfitrion()
	yield creado
	creado.instancia.desactivar()


@pytest.fixture
def tareas(zc):
	return p5_comun.modulo(NOMBRE, "tareas")


@pytest.fixture
def windows(zc):
	return p5_comun.modulo(NOMBRE, "windows")


@pytest.fixture
def papelera_falsa(monkeypatch):
	"""La papelera real del sistema no se toca: «enviar» borra el archivo de la carpeta temporal."""
	from app.services.windows import papelera

	enviados: list[str] = []

	def enviar(rutas):
		for ruta in rutas:
			enviados.append(ruta)
			os.remove(ruta)

	monkeypatch.setattr(papelera, "enviar", enviar)
	return enviados


def _lanzar_en_el_acto(zc, monkeypatch, decisor=None):
	"""``zc.lanzar`` que ejecuta la operación en este hilo y llama a ``al_terminar`` (como haría la ventana)."""
	lanzadas = []

	def lanzar(operacion, en_cola=False, al_terminar=None):
		lanzadas.append(operacion)
		contexto = api.ContextoEjecucion(threading.Event(), decisor or pruebas.DecisorFalso())
		contexto.operacion = operacion
		operacion.contexto = contexto
		operacion.ejecutar(contexto)
		if al_terminar is not None:
			al_terminar(operacion)

	monkeypatch.setattr(zc, "lanzar", lanzar)
	return lanzadas


def _viejo(ruta, dias: float) -> None:
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_text("x", encoding="utf-8")
	momento = time.time() - dias * 86400
	os.utime(ruta, (momento, momento))


# ── XML y Programador de Windows ─────────────────────────────────────────────


XML_DIARIA = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>zCommander</Author>
    <Description>Copia de &amp; fotos: Ejecutar una tarea de sincronización: Fotos</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-11-09T08:30:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>EQUIPO\\ana</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>C:\\zCommander\\ZCommander.exe</Command>
      <Arguments>--tarea ab12cd34</Arguments>
      <WorkingDirectory>C:\\zCommander</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def test_xml_de_la_tarea_de_windows_es_el_esperado(tareas, windows):
	tarea = tareas.Tarea("Copia de & fotos", objetivo="Fotos", hora="08:30", id="ab12cd34")
	xml = windows.xml_tarea(tarea, "C:\\zCommander\\ZCommander.exe", "--tarea ab12cd34", "C:\\zCommander", "EQUIPO\\ana",
		hoy=datetime.date(2026, 11, 9))
	assert xml == XML_DIARIA


def test_xml_semanal_una_vez_y_al_iniciar_sesion(tareas, windows):
	hoy = datetime.date(2026, 11, 9)
	semanal = windows.xml_tarea(tareas.Tarea("S", objetivo="x", frecuencia=tareas.SEMANAL, dias_semana=[4, 0], hora="7:05"),
		"z.exe", "", "C:\\", "ana", hoy)
	assert "<DaysOfWeek>\n          <Monday />\n          <Friday />\n        </DaysOfWeek>" in semanal
	assert "<StartBoundary>2026-11-09T07:05:00</StartBoundary>" in semanal
	una = windows.xml_tarea(tareas.Tarea("U", objetivo="x", frecuencia=tareas.UNA_VEZ, fecha="2026-12-31", hora="23:59"),
		"z.exe", "", "C:\\", "ana", hoy)
	assert "<TimeTrigger>\n      <StartBoundary>2026-12-31T23:59:00</StartBoundary>" in una
	sesion = windows.xml_tarea(tareas.Tarea("L", objetivo="x", frecuencia=tareas.AL_INICIAR_SESION), "z.exe", "", "C:\\", "ana",
		hoy)
	assert "<LogonTrigger>\n      <Enabled>true</Enabled>\n      <UserId>ana</UserId>" in sesion
	for xml in (semanal, una, sesion):
		for ajuste in ("<LogonType>InteractiveToken</LogonType>", "<StartWhenAvailable>true</StartWhenAvailable>",
				"<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>", "<MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>",
				"<Priority>4</Priority>", "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
				"<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"):
			assert ajuste in xml


def test_el_comando_lanza_zcommander_con_tarea(windows):
	programa, argumentos, carpeta = windows.comando("ab12cd34")
	assert argumentos.endswith("--tarea ab12cd34")
	assert "main.py" in argumentos and programa.lower().endswith(("pythonw.exe", "python.exe"))
	assert os.path.isdir(carpeta)


class _CarpetaFalsa:
	def __init__(self) -> None:
		self.registradas: dict[str, tuple] = {}
		self.borradas: list[str] = []

	def RegisterTask(self, nombre, xml, banderas, usuario, clave, inicio):  # noqa: N802 - API COM
		self.registradas[nombre] = (xml, banderas, usuario, clave, inicio)

	def DeleteTask(self, nombre, banderas):  # noqa: N802 - API COM
		self.borradas.append(nombre)
		self.registradas.pop(nombre, None)

	def CreateFolder(self, nombre):  # noqa: N802 - API COM
		raise AssertionError("no se crea dentro de zCommander")


class _ServicioFalso:
	"""``Schedule.Service`` falso: nunca toca el Programador de tareas real."""

	def __init__(self) -> None:
		self.carpeta: _CarpetaFalsa | None = None
		self.creadas: list[str] = []
		servicio = self

		class _Raiz:
			def CreateFolder(self, nombre):  # noqa: N802 - API COM
				servicio.creadas.append(nombre)
				servicio.carpeta = _CarpetaFalsa()
				return servicio.carpeta

		self._raiz = _Raiz()

	def GetFolder(self, ruta):  # noqa: N802 - API COM
		if ruta == "\\":
			return self._raiz
		if self.carpeta is None:
			raise OSError("no existe")
		return self.carpeta


def test_registrar_y_borrar_con_el_com_simulado(tareas, windows):
	servicio = _ServicioFalso()
	programador = windows.ProgramadorWindows(lambda: servicio)
	tarea = tareas.Tarea("Copia", objetivo="x", id="00aa11bb")
	programador.registrar(tarea)
	assert servicio.creadas == ["zCommander"]
	xml, banderas, usuario, clave, inicio = servicio.carpeta.registradas["zCommander 00aa11bb"]
	assert (banderas, usuario, clave, inicio) == (windows.TASK_CREATE_OR_UPDATE, None, None, windows.TASK_LOGON_INTERACTIVE_TOKEN)
	assert "--tarea 00aa11bb" in xml
	programador.borrar(tarea)
	assert servicio.carpeta.borradas == ["zCommander 00aa11bb"]
	assert programador.sincronizar([tarea], usar_windows=True) == []
	assert "zCommander 00aa11bb" in servicio.carpeta.registradas


def test_un_error_del_programador_de_windows_se_explica(tareas, windows):
	def roto():
		raise OSError(5, "Acceso denegado")

	with pytest.raises(windows.ErrorProgramador, match="no aceptó el cambio"):
		windows.ProgramadorWindows(roto).registrar(tareas.Tarea("x", objetivo="y"))


# ── ejecutar_tarea (contrato con el cargador, 11.0) ──────────────────────────


def test_exporta_ejecutar_tarea(zc):
	funcion = registro.exportados("zc.programador")["ejecutar_tarea"]
	codigos: list[int] = []
	funcion("no-existe", codigos.append)
	assert codigos == [2]


def test_limpieza_con_respuestas_automaticas_termina_con_0_sin_preguntar(zc, tareas, tmp_path, monkeypatch, papelera_falsa):
	carpeta = tmp_path / "Temporales"
	_viejo(carpeta / "viejo.log", 40)
	_viejo(carpeta / "sub" / "viejo2.log", 40)
	_viejo(carpeta / "nuevo.log", 1)
	tarea = tareas.Tarea("Limpiar", tipo=tareas.LIMPIEZA, objetivo=str(carpeta), dias=30)
	tareas.guardar_tareas(zc.datos, [tarea])
	decisor = pruebas.DecisorFalso()
	lanzadas = _lanzar_en_el_acto(zc, monkeypatch, decisor)
	codigos: list[int] = []
	zc.instancia.ejecutar_tarea(tarea.id, codigos.append)
	assert codigos == [0]
	assert decisor.preguntas == []
	assert sorted(os.path.basename(r) for r in papelera_falsa) == ["viejo.log", "viejo2.log"]
	assert (carpeta / "nuevo.log").exists()
	automaticas = lanzadas[0].respuestas_automaticas
	assert automaticas.conflicto == api.Politica.OMITIR and automaticas.error == api.AccionError.OMITIR
	ejecucion = zc.instancia.registro_ejecuciones.leer()[-1]
	assert (ejecucion.codigo, ejecucion.nombre) == (0, "Limpiar") and ejecucion.fin
	assert tareas.leer_tareas(zc.datos)[0].resultado == 0
	assert "zc.programador:tarea_fin" in zc.sonidos_pedidos


def test_las_decisiones_automaticas_quedan_apuntadas_sin_mostrar_nada(zc, tareas, tmp_path, monkeypatch, app_wx, papelera_falsa):
	"""Con el gestor de decisiones real: la carpeta ilegible se omite sola y la decisión queda en el registro."""
	from app.services.vfs import resolver as modulo_resolver
	from app.ui.decisiones import GestorDecisiones

	carpeta = tmp_path / "Temporales"
	_viejo(carpeta / "viejo.log", 40)
	(carpeta / "bloqueada").mkdir()
	local = modulo_resolver.proveedor_local()

	class Proveedor:
		esquema = "local"

		def listar(self, ruta, cancelacion=None):
			if ruta.endswith("bloqueada"):
				raise api.ErrorAcceso("Acceso denegado", ruta)
			return local.listar(ruta, cancelacion)

		def __getattr__(self, nombre):
			return getattr(local, nombre)

	monkeypatch.setattr(zc.vfs, "resolver", lambda direccion: (Proveedor(), direccion))
	tarea = tareas.Tarea("Limpiar", tipo=tareas.LIMPIEZA, objetivo=str(carpeta), dias=30)
	tareas.guardar_tareas(zc.datos, [tarea])
	_lanzar_en_el_acto(zc, monkeypatch, GestorDecisiones(None))
	codigos: list[int] = []
	zc.instancia.ejecutar_tarea(tarea.id, codigos.append)
	assert codigos == [1]
	ejecucion = zc.instancia.registro_ejecuciones.leer()[-1]
	assert any("bloqueada" in d and "omitir" in d for d in ejecucion.decisiones), ejecucion.decisiones
	assert not (carpeta / "viejo.log").exists()


def test_macro_espera_el_futuro_de_su_orden(zc, tareas, app_wx):
	interfaz = p5_comun.con_interfaz()
	try:
		tarea = tareas.Tarea("Fotos", tipo=tareas.MACRO, objetivo="Fotos a la copia")
		tareas.guardar_tareas(zc.datos, [tarea])
		codigos: list[int] = []
		zc.instancia.ejecutar_tarea(tarea.id, codigos.append)
		assert interfaz.ordenes == [("macro:Fotos a la copia", None)]
		interfaz.resultado_orden = False
		zc.instancia.ejecutar_tarea(tarea.id, codigos.append)
		assert codigos == [0, 1]
	finally:
		api.fijar_interfaz(None)


def test_entrada_del_menu_de_usuario_lleva_su_nombre_como_argumento(zc, tareas, app_wx):
	interfaz = p5_comun.con_interfaz()
	try:
		tarea = tareas.Tarea("Menú", tipo=tareas.MENU_USUARIO, objetivo="Comprimir copias")
		tareas.guardar_tareas(zc.datos, [tarea])
		zc.instancia.ejecutar_tarea(tarea.id, lambda _c: None)
		assert interfaz.ordenes == [("menu_usuario", "Comprimir copias")]
	finally:
		api.fijar_interfaz(None)


def test_sincronizacion_usa_la_operacion_exportada(zc, tareas, monkeypatch):
	class Operacion(api.Operacion):
		def descripcion(self):
			return "Sincronizar Fotos"

		def ejecutar(self, ctx):
			self.cambiar_estado(api.Estado.TERMINADA)

	pedidas: list[str] = []

	def futuro_de(id_complemento):
		futuro: Future = Future()
		futuro.set_result(SimpleNamespace(operacion_de_tarea=lambda nombre: pedidas.append(nombre) or Operacion())
			if id_complemento == "zc.sincronizacion" else None)
		return futuro

	monkeypatch.setattr(zc, "complemento_futuro", futuro_de)
	lanzadas = _lanzar_en_el_acto(zc, monkeypatch)
	sincronizar = tareas.Tarea("S", tipo=tareas.SINCRONIZACION, objetivo="Fotos", conflicto="sobrescribir", error="cancelar")
	reglas = tareas.Tarea("R", tipo=tareas.REGLAS, objetivo="C:\\Descargas")
	tareas.guardar_tareas(zc.datos, [sincronizar, reglas])
	codigos: list[int] = []
	zc.instancia.ejecutar_tarea(sincronizar.id, codigos.append)
	zc.instancia.ejecutar_tarea(reglas.id, codigos.append)
	assert pedidas == ["Fotos"] and codigos == [0, 2]
	assert lanzadas[0].respuestas_automaticas.conflicto == api.Politica.SOBRESCRIBIR
	assert lanzadas[0].respuestas_automaticas.error == api.AccionError.CANCELAR
	assert "Falta el complemento Monitor" in zc.instancia.registro_ejecuciones.leer()[-1].resumen


def test_copia_abre_origen_y_destino_sin_panel(zc, tareas, tmp_path):
	origen = tmp_path / "a" / "informe.txt"
	origen.parent.mkdir()
	origen.write_text("hola", encoding="utf-8")
	(tmp_path / "b").mkdir()
	tarea = tareas.Tarea("C", tipo=tareas.COPIA, objetivo=str(origen), destino=str(tmp_path / "b"), conflicto="sobrescribir")
	operacion = zc.instancia._operacion_copia(tarea)
	assert isinstance(operacion, api.OperacionCopiar)
	assert [e.nombre for e in operacion.entradas] == ["informe.txt"]
	with pytest.raises(api.NoEncontrado):
		zc.instancia._operacion_copia(tareas.Tarea("C", tipo=tareas.COPIA, objetivo=str(tmp_path / "no.txt"), destino=str(tmp_path)))


def test_cuando_vence_una_tarea(tareas):
	ahora = datetime.datetime(2026, 11, 9, 10, 0).timestamp()  # lunes
	diaria = tareas.Tarea("D", objetivo="x", hora="09:00")
	assert tareas.vence(diaria, ahora)
	diaria.ultima = datetime.datetime(2026, 11, 9, 9, 0, 5).timestamp()
	assert not tareas.vence(diaria, ahora)
	assert not tareas.vence(tareas.Tarea("D", objetivo="x", hora="11:00"), ahora)
	assert not tareas.vence(tareas.Tarea("S", objetivo="x", frecuencia=tareas.SEMANAL, dias_semana=[1], hora="09:00"), ahora)
	assert tareas.vence(tareas.Tarea("S", objetivo="x", frecuencia=tareas.SEMANAL, dias_semana=[0], hora="09:00"), ahora)
	assert tareas.vence(tareas.Tarea("U", objetivo="x", frecuencia=tareas.UNA_VEZ, fecha="2026-11-01", hora="09:00"), ahora)
	assert not tareas.vence(tareas.Tarea("U", objetivo="x", frecuencia=tareas.UNA_VEZ, fecha="2026-11-10", hora="09:00"), ahora)
	assert not tareas.vence(tareas.Tarea("D", objetivo="x", hora="09:00", activa=False), ahora)


def test_sin_programador_de_windows_ejecuta_lo_que_toca(zc, tareas, monkeypatch):
	zc.config.establecer("usar_windows", False)
	ejecutadas: list[str] = []
	monkeypatch.setattr(zc.instancia, "ejecutar_tarea", lambda id_tarea, al_terminar: ejecutadas.append(id_tarea))
	tarea = tareas.Tarea("D", objetivo="x", hora="00:00")
	tareas.guardar_tareas(zc.datos, [tarea])
	assert zc.instancia.comprobar_vencidas() == [tarea.id] == ejecutadas
	zc.config.establecer("usar_windows", True)
	assert zc.instancia.comprobar_vencidas() == []


def test_el_com_real_no_se_usa_en_las_pruebas(windows, tareas):
	with pytest.raises(windows.ErrorProgramador, match="no se usa el Programador de tareas real"):
		windows._servicio_real()


def test_al_activarse_avisa_de_lo_ejecutado_mientras_estaba_cerrado(tareas, tmp_path):
	primero = _anfitrion()
	registro_ejecuciones = primero.instancia.registro_ejecuciones
	registro_ejecuciones.apuntar(tareas.Ejecucion("a", "Copia nocturna", time.time() - 3600, time.time() - 3000, 0, "bien"))
	registro_ejecuciones.apuntar(tareas.Ejecucion("b", "Limpieza", time.time() - 2000, time.time() - 1900, 1, "con errores"))
	primero.instancia.desactivar()
	segundo = _anfitrion()
	segundo.instancia._tras_activar()
	assert segundo.anuncios[-1] == ("Tareas programadas ejecutadas desde la última vez: 2, 1 con errores. "
		"Detalles en Registro de ejecuciones.", api.ESENCIAL)
	assert "zc.programador:tarea_fin" in segundo.sonidos_pedidos
	assert registro_ejecuciones.sin_ver() == []
	segundo.instancia.desactivar()


def test_validacion_de_una_tarea(tareas):
	assert tareas.Tarea("", objetivo="x").error_de_datos() == "Escriba un nombre para la tarea."
	assert "objetivo" in tareas.Tarea("a").error_de_datos()
	assert "HH:MM" in tareas.Tarea("a", objetivo="x", hora="25:00").error_de_datos()
	assert "AAAA-MM-DD" in tareas.Tarea("a", objetivo="x", frecuencia=tareas.UNA_VEZ).error_de_datos()
	assert "destino" in tareas.Tarea("a", tipo=tareas.COPIA, objetivo="x").error_de_datos()
	assert tareas.Tarea("a", objetivo="x").error_de_datos() == ""


def test_ordenes_con_manejador_real(zc):
	for orden in ("tareas", "registro"):
		manejador = registro.manejador(f"zc.programador:{orden}")
		assert manejador is not None and not getattr(manejador, "provisional", False)


# ── Diálogos (wx) ────────────────────────────────────────────────────────────


@pytest.fixture
def interfaz(app_wx):
	creada = p5_comun.con_interfaz()
	yield creada
	api.fijar_interfaz(None)


def test_dialogos_pasan_revisar_teclado(zc, interfaz):
	ventanas = zc.instancia.ventanas_para_revisar(None)
	assert len(ventanas) == 3
	try:
		for ventana in ventanas:
			assert p5_comun.problemas_de_teclado(ventana) == [], ventana.GetTitle()
	finally:
		for ventana in ventanas:
			ventana.Destroy()


def test_editor_habilita_lo_que_usa_cada_tipo(zc, tareas, interfaz):
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	editor = ventana.DialogoTarea(zc, None, tareas.Tarea("L", tipo=tareas.LIMPIEZA, objetivo="C:\\Temp",
		frecuencia=tareas.SEMANAL, dias_semana=[2, 5]))
	try:
		assert editor.dias.IsEnabled() and not editor.destino.IsEnabled() and editor.dias_semana.IsEnabled()
		assert editor.etiqueta_objetivo.GetLabel() == "&Objetivo, carpeta que se limpia:"
		assert editor.tarea().dias_semana == [2, 5]
		editor.tipo.SetSelection(list(tareas.TIPOS).index(tareas.COPIA))
		editor._habilitar()
		assert editor.destino.IsEnabled() and not editor.dias.IsEnabled()
		assert "destino" in editor.tarea().error_de_datos()
	finally:
		editor.Destroy()


def test_registro_muestra_las_decisiones(zc, tareas, interfaz):
	zc.instancia.registro_ejecuciones.apuntar(tareas.Ejecucion("a", "Limpieza", time.time(), time.time(), 1, "con errores",
		["Limpiar: error en C:\\x (Acceso denegado): «omitir»"]))
	ventana = p5_comun.modulo(NOMBRE, "ventana")
	dialogo = ventana.DialogoRegistro(zc.instancia, None)
	try:
		assert dialogo.lista.valores_fila(0)[1:3] == ["Limpieza", "Con errores"]
		dialogo.lista.enfocar_fila(0, anunciar=False)
		dialogo._mostrar_detalles()
		assert "Decisiones tomadas sin preguntar" in dialogo.detalles.GetValue()
	finally:
		dialogo.Destroy()
