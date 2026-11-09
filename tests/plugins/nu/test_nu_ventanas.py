# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Ventanas de Nubes (diseño 2.0, 12.5, 12.7, 15.1 y 18.2): todas pasan ``revisar_teclado``.

Se construyen SIN mostrarlas, con los controles accesibles de zCommander
(``zc.ui`` a través de una interfaz de prueba con ``app.ui.api_ui``) y también
sin la ventana de zCommander (como en ``tools/validar_plugin.py``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.plugins import api  # noqa: E402
from app.ui import api_ui  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from tests.plugins.nu.comun import modulo  # noqa: E402


class InterfazPrueba:
	modulo_ui = api_ui

	def __init__(self) -> None:
		self.anuncios: list[str] = []

	def planificar(self, funcion) -> None:
		funcion()

	def en_hilo_interfaz(self) -> bool:
		return True

	def anunciar(self, texto, nivel, completo="", interrumpir=None, sonido="") -> None:
		self.anuncios.append(texto)

	def abrir_ayuda(self, id_complemento, pagina="") -> None:
		self.anuncios.append("ayuda")


@pytest.fixture
def con_interfaz():
	interfaz = InterfazPrueba()
	api.fijar_interfaz(interfaz)
	yield interfaz
	api.fijar_interfaz(None)


def _revisar_todas(zc) -> int:
	padre = wx.Frame(None, title="Prueba")
	ventanas = zc.instancia.ventanas_para_revisar(padre)
	try:
		for ventana in ventanas:
			teclas = ["Supr", "Intro", "F1"] if isinstance(ventana, wx.Dialog) else []
			afirmar_teclado_correcto(ventana, teclas_propias=teclas)
		return len(ventanas)
	finally:
		for ventana in ventanas:
			ventana.Destroy()
		padre.Destroy()


def test_todas_las_ventanas_pasan_revisar_teclado_con_los_controles_de_zcommander(app_wx, zc, con_interfaz):
	assert _revisar_todas(zc) >= 40


def test_todas_las_ventanas_pasan_revisar_teclado_sin_la_ventana_de_zcommander(app_wx, zc):
	assert api.interfaz() is None
	assert _revisar_todas(zc) >= 40


def test_ventana_de_cuentas_muestra_estado_en_texto_y_habilita_botones(app_wx, zc, con_interfaz):
	cuentas = modulo("cuentas")
	ui_cuentas = modulo("ui.cuentas")
	ordenes = modulo("ui.ordenes")
	nubes = zc.instancia.nubes
	nubes.cuentas.guardar(cuentas.Cuenta(id="ana", nombre="Google Drive de Ana", servicio="drive"))
	nubes.cuentas.guardar(cuentas.Cuenta(id="copia", nombre="Restaurada", servicio="onedrive", volver_a_configurar=True))
	dialogo = ui_cuentas.DialogoCuentas(zc, None, ordenes.Ordenes(zc, nubes))
	try:
		assert dialogo.lista.GetItemCount() == 2
		textos = [[dialogo.lista.GetItem(f, c).GetText() for c in range(5)] for f in range(2)]
		assert textos[0][:4] == ["Google Drive de Ana", "Google Drive", "rclone", "Sin comprobar"]
		assert textos[1][3] == "Volver a configurar"
		assert dialogo.boton_eliminar.IsEnabled()
		dialogo.poner_espacio("ana", "10 GB libres")
		assert dialogo.lista.GetItem(0, 4).GetText() == "10 GB libres"
	finally:
		dialogo.Destroy()


def test_letras_unicas_en_los_datos_de_cada_servicio(app_wx, zc):
	asistente = modulo("ui.asistente")
	comun = modulo("ui.comun")
	for servicio in zc.instancia.nubes.catalogo.lista(True):
		dialogo = asistente.DialogoDatos(zc, None, servicio)
		try:
			letras = [comun.letra(e) for e in dialogo.etiquetas.values()]
			assert len(letras) == len(set(letras)) and None not in letras, servicio.id
		finally:
			dialogo.Destroy()


def test_datos_rehace_los_campos_al_mostrar_las_contrasenas(app_wx, zc):
	asistente = modulo("ui.asistente")
	servicio = zc.instancia.nubes.catalogo.servicio("mega")
	dialogo = asistente.DialogoDatos(zc, None, servicio)
	try:
		dialogo.controles["user"].SetValue("ana@ejemplo.com")
		dialogo.controles["pass"].SetValue("secreta")
		assert dialogo.controles["pass"].GetWindowStyleFlag() & wx.TE_PASSWORD
		dialogo.mostrar.SetValue(True)
		dialogo._alternar()
		assert not dialogo.controles["pass"].GetWindowStyleFlag() & wx.TE_PASSWORD
		assert dialogo.valores()["pass"] == "secreta" and dialogo.valores()["user"] == "ana@ejemplo.com"
		afirmar_teclado_correcto(dialogo)
	finally:
		dialogo.Destroy()


def test_pregunta_de_rclone_con_el_control_que_toca(app_wx, zc):
	asistente = modulo("ui.asistente")
	servicio = modulo("servicio")
	casos = [
		({"Name": "x", "Type": "bool", "DefaultStr": "true"}, wx.Choice, "true"),
		({"Name": "x", "Exclusive": True, "Examples": [{"Value": "a", "Help": "A"}, {"Value": "b", "Help": "B"}], "DefaultStr": "b"},
			wx.Choice, "b"),
		({"Name": "x", "Examples": [{"Value": "a"}], "DefaultStr": "otra"}, wx.ComboBox, "otra"),
		({"Name": "x", "IsPassword": True}, wx.TextCtrl, ""),
	]
	for opcion, clase, esperado in casos:
		dialogo = asistente.DialogoPregunta(zc, None, servicio.Paso("pregunta", opcion=opcion))
		try:
			assert isinstance(dialogo.control, clase)
			assert dialogo.respuesta() == esperado
		finally:
			dialogo.Destroy()


def test_propiedades_valida_el_fragmento_y_devuelve_los_cambios(app_wx, zc):
	propiedades = modulo("ui.propiedades")
	cuentas = modulo("cuentas")
	assert propiedades.validar_fragmento("64M", "potencia_2") == ""
	assert propiedades.validar_fragmento("10M", "potencia_2")
	assert propiedades.validar_fragmento("3M", "potencia_2")
	assert propiedades.validar_fragmento("10M", "multiplo_320k") == ""
	assert propiedades.validar_fragmento("1M", "multiplo_320k")
	catalogo = zc.instancia.nubes.catalogo
	cuenta = cuentas.Cuenta(id="ana", nombre="Ana", servicio="drive", opciones={"chunk_size": "8M"})
	dialogo = propiedades.DialogoPropiedades(zc, None, cuenta, catalogo.servicio("drive"))
	try:
		dialogo.fragmento.SetValue("64M")
		dialogo.papelera.SetValue(False)
		nueva, cambios, _secreto = dialogo.resultado()
		assert cambios["chunk_size"] == "64M" and cambios["use_trash"] == "false"
		assert nueva.opciones["chunk_size"] == "64M" and not nueva.papelera
	finally:
		dialogo.Destroy()


def test_horario_de_franjas_ida_y_vuelta(app_wx, zc):
	franjas = modulo("ui.franjas")
	texto = "08:00,512k 12:00,10M:1M 23:00,off"
	leidas = franjas.leer_horario(texto)
	assert [(f.hora, f.subida_kib, f.bajada_kib) for f in leidas] == [("08:00", 512, 512), ("12:00", 10240, 1024), ("23:00", 0, 0)]
	assert franjas.escribir_horario(leidas) == texto
	with pytest.raises(ValueError):
		franjas.leer_horario("a las ocho")
	dialogo = franjas.DialogoFranjas(zc, None, texto)
	try:
		dialogo.hora.SetValue("18:30")
		dialogo.subida.SetValue(100)
		dialogo.bajada.SetValue(200)
		dialogo.anadir()
		assert dialogo.horario() == "08:00,512k 12:00,10M:1M 18:30,100k:200k 23:00,off"
	finally:
		dialogo.Destroy()


def test_dialogo_de_espera_ofrece_navegador_copiar_y_cancelar(app_wx, zc, con_interfaz):
	oauth = modulo("ui.oauth")
	dialogo = oauth.DialogoEspera(zc, None, "Autorizar", "Se abrirá el navegador", url="http://127.0.0.1:53682/auth?state=x",
		otro_equipo=True)
	try:
		etiquetas = {b.GetLabel() for b in dialogo.panel.GetChildren() if isinstance(b, wx.Button)}
		assert {"Abrir el &navegador", "&Copiar el enlace", "A&utorizar desde otro equipo...", "Cance&lar"} <= etiquetas
		assert dialogo.boton_navegador.IsThisEnabled()
		assert dialogo.barra.GetName() == "Progreso de la espera"
		assert dialogo.estado.GetValue()
	finally:
		dialogo.Destroy()


def test_documento_de_la_guia_tiene_secciones(zc):
	ordenes = modulo("ui.ordenes")
	ruta = zc.instancia.nubes.carpeta / "doc" / "es" / "google-drive.md"
	documento = ordenes.documento_markdown("Guía", ruta.read_text(encoding="utf-8"))
	titulos = [s.titulo for s in documento.secciones]
	assert any("Paso 5" in t for t in titulos) and any("publicar" in t.lower() for t in titulos)


def test_puede_cerrar_sin_motor_no_pregunta(zc):
	assert zc.instancia.puede_cerrar() is True


def test_ordenes_sin_cuentas_avisan_sin_abrir_dialogos(zc):
	contexto = api.pruebas.contexto_de_prueba()
	for orden in ("vaciar_papelera", "espacio", "cifrada", "union", "duplicados"):
		zc.ejecutar(orden, contexto)
	assert any("No hay cuentas de nube" in t or "al menos dos cuentas" in t for t, _n in zc.anuncios)


def test_enlace_fuera_de_una_nube_avisa(zc):
	zc.ejecutar("enlace", api.pruebas.contexto_de_prueba(activo=SimpleNamespace(proveedor=None, ruta="", cursor=lambda: None)))
	assert any("cuenta de nube" in t for t, _n in zc.anuncios)
