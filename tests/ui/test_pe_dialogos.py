# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos del bloque PE (diseño 2.0, sección 10 y 18.2): cada uno pasa ``revisar_teclado`` y hace lo suyo."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

wx = pytest.importorskip("wx")

from app.core.configuracion import Configuracion  # noqa: E402
from app.services import confirmaciones, menus_personalizados, teclas_globales  # noqa: E402
from app.services.macros import Macro, Paso  # noqa: E402
from app.services.teclas import MapaTeclas  # noqa: E402
from app.services.vfs.base import Entrada  # noqa: E402
from app.services.vistas_modelo import ConjuntoVista  # noqa: E402
from app.ui import ordenes  # noqa: E402
from app.ui.accesibilidad.revision_teclado import afirmar_teclado_correcto  # noqa: E402
from app.ui.dialogos import (  # noqa: E402
	f_comun,
	f_preferencias,
	pe_alias,
	pe_confirmaciones,
	pe_esquema,
	pe_espacios,
	pe_macros,
	pe_menus,
	pe_orden_lectura,
	pe_reglas,
	pe_teclas_globales,
	pe_vistas,
)

from ..conftest import procesar_eventos  # noqa: E402


@pytest.fixture
def config(tmp_path):
	return Configuracion(ruta=tmp_path / "settings.json")


@pytest.fixture
def respuestas(monkeypatch):
	estado = SimpleNamespace(avisos=[], preguntas=[], pedidos=[], si=True, textos=[])

	def pedir(padre, etiqueta, titulo, valor="", **opciones):
		estado.pedidos.append(etiqueta)
		return estado.textos.pop(0) if estado.textos else None

	monkeypatch.setattr(f_comun, "avisar", lambda padre, texto, titulo="": estado.avisos.append(texto))
	monkeypatch.setattr(f_comun, "preguntar", lambda padre, texto, titulo="", peligroso=False: estado.preguntas.append(texto) or estado.si)
	monkeypatch.setattr(f_comun, "pedir", pedir)
	return estado


@pytest.fixture
def destruir():
	creados = []
	yield creados.append
	for dialogo in creados:
		if dialogo:
			dialogo.Destroy()
	procesar_eventos(lambda: False, 0.05)


def _mapa() -> MapaTeclas:
	return MapaTeclas(ordenes.teclas_por_defecto(), ordenes.ambitos(), {}, ordenes.fijas())


class PanelFalso:
	def __init__(self) -> None:
		self.columnas = ["nombre", "tamano", "modificado"]
		self.lectura: list[str] = []
		self.conjunto = None
		self.criterio_orden, self.orden_inverso, self.vista, self.filtro = "nombre", False, "completa", ""
		self.ruta = "D:\\Música"
		self.aplicados: list = []
		self.lecturas: list = []

	def mostrar_ruta(self) -> str:
		return self.ruta

	def es_lista(self):
		return None

	def entradas(self):
		return [Entrada(f"c{i}.mp3", f"D:\\Música\\c{i}.mp3") for i in range(3)]

	def aplicar_conjunto(self, conjunto) -> None:
		self.conjunto = conjunto
		self.aplicados.append(conjunto)

	def aplicar_lectura(self, lectura) -> None:
		self.lecturas.append(list(lectura))


def _pe(config):
	"""Un ``ServicioPE`` con una ventana falsa (sin wx.Frame)."""
	from app.ui.acciones import personalizar_pe

	ventana = SimpleNamespace(config=config, mapa_teclas=_mapa(), anunciar=lambda *a, **k: None, todos_los_paneles=lambda: [],
		llamar_mas_tarde=lambda ms, f: None, servicio=lambda n: (_ for _ in ()).throw(KeyError(n)), padre=lambda: None)
	return personalizar_pe.ServicioPE(ventana), ventana


def _dialogos(config):
	pe, _ventana = _pe(config)
	pe.macros = [Macro("Fotos", pasos=[Paso("ir_a_carpeta", "D:\\Fotos"), Paso("marcar_patron", "*.jpg")])]
	panel = PanelFalso()
	return [
		pe_macros.DialogoMacros(None, pe),
		pe_macros.DialogoMacro(None, pe.macros[0], [], _mapa()),
		pe_macros.DialogoImportarMacro(None, Macro("X", pasos=[Paso("ejecutar_linea", "dir")]), []),
		pe_vistas.DialogoVistas(None, pe, panel),
		pe_vistas.DialogoConjunto(None, ConjuntoVista("Música", ("nombre",)), [], ["nombre"]),
		pe_orden_lectura.DialogoOrdenLectura(None, [("pestana", "Esta pestaña", ["nombre", "tamano"], []),
			("defecto", "Las columnas por defecto", ["nombre"], [])]),
		pe_menus.DialogoMenus(None, menus_personalizados.DatosMenus(), _mapa()),
		pe_esquema.DialogoEsquema(None, config),
		pe_alias.DialogoListaAlias(None, pe),
		pe_alias.DialogoAlias(None, pe_alias.Alias("ll", "dir"), []),
		pe_espacios.DialogoEspacios(None),
		pe_reglas.DialogoReglas(None, pe),
		pe_reglas.DialogoRegla(None, pe_reglas.Regla("R")),
		pe_teclas_globales.DialogoTeclasGlobales(None, config),
		f_preferencias.DialogoPreferenciasZ(None, config),
	]


def test_cada_dialogo_de_pe_pasa_revisar_teclado(app_wx, config):
	dialogos = _dialogos(config)
	try:
		for dialogo in dialogos:
			try:
				afirmar_teclado_correcto(dialogo)
			except AssertionError as error:
				raise AssertionError(f"{dialogo.GetTitle()}: {error}") from None
	finally:
		for dialogo in dialogos:
			dialogo.Destroy()
		procesar_eventos(lambda: False, 0.05)


def test_pagina_confirmaciones_pasa_revisar_teclado_y_recupera(app_wx, config, destruir):
	marco = wx.Frame(None)
	destruir(marco)
	confirmaciones.silenciar(config, "esquema_cambio")
	confirmaciones.silenciar(config, "ftp_sin_cifrar:servidor")
	pagina = pe_confirmaciones.crear(marco, config)
	afirmar_teclado_correcto(pagina)
	indice = pagina.ids.index("esquema_cambio")
	assert pagina.lista.IsChecked(indice) is False, "silenciada: desmarcada"
	assert pagina.silenciadas()[:1] == ["esquema_cambio"]
	pagina.restablecer()
	assert pagina.validar() is None and pagina.aplicar()
	assert confirmaciones.debe_preguntar(config, "esquema_cambio")
	assert confirmaciones.debe_preguntar(config, "ftp_sin_cifrar:servidor")
	assert "eliminar_definitivo" not in pagina.ids


def test_preferencias_arbol_busqueda_y_paginas(app_wx, config, destruir, monkeypatch):
	dialogo = f_preferencias.DialogoPreferenciasZ(None, config, pagina="Personalización")
	destruir(dialogo)
	assert isinstance(dialogo.libro, wx.Treebook)
	titulos = dialogo.titulos()
	assert titulos[:3] == ["General", "Paneles", "Vista"] and "Confirmaciones" in titulos and "Complementos" in titulos
	assert titulos.index("Confirmaciones") == titulos.index("Personalización") + 1
	assert dialogo.libro.GetSelection() == titulos.index("Personalización")
	resultados = dialogo.buscar_opciones("papelera")
	assert any(clave == "general.usar_papelera" for clave, _p in resultados)
	dialogo.buscar.ChangeValue("papelera")
	dialogo.filtrar()
	assert dialogo.resultados.GetCount() >= 1
	assert dialogo.ir_al_resultado(0)
	assert dialogo.libro.GetSelection() == titulos.index("General")
	assert dialogo.indice_de("complemento:no.existe") is None
	# El botón «Teclas globales...» está al final de la página Personalización.
	pagina = dialogo.libro.GetPage(titulos.index("Personalización"))
	assert any(isinstance(h, wx.Button) and "globales" in h.GetLabel() for h in pagina.GetChildren())
	# Aplicar guarda; la página Confirmaciones también.
	dialogo.control_de("vista.tamano_fuente").SetValue(20)
	assert dialogo.aplicar()
	assert config.obtener("vista.tamano_fuente") == 20


def test_abrir_preferencias_en_una_pagina_que_no_existe_lo_dice(app_wx, config, monkeypatch):
	from app.ui import anuncios

	monkeypatch.setattr(f_comun, "mostrar", lambda dialogo, *a, **k: dialogo.Destroy())
	f_preferencias.abrir(None, config, pagina="complemento:no.existe")
	assert any("Página no disponible" in a.texto for a in anuncios.historial())


def test_esquema_explorador_aplicado_deja_f2_en_renombrar(app_wx, config, destruir, monkeypatch):
	dialogo = pe_esquema.DialogoEsquema(None, config)
	destruir(dialogo)
	dialogo.lista.SetSelection(pe_esquema.ORDEN.index("explorador"))
	dialogo._describir()  # noqa: SLF001 - lo que hace EVT_LISTBOX
	assert dialogo.cambios.GetItemCount() >= 3
	monkeypatch.setattr(pe_esquema, "elegir_con_casilla", lambda *a, **k: (0, True))
	assert dialogo.aplicar()
	assert config.obtener("teclado.esquema") == "explorador"
	assert not confirmaciones.debe_preguntar(config, "esquema_cambio"), "«No volver a preguntar» marcado"
	mapa = MapaTeclas(ordenes.teclas_por_defecto(config.obtener("teclado.esquema")), ordenes.ambitos(), {}, ordenes.fijas())
	assert mapa.orden_de("F2", ("panel", "global")) == "renombrar"


def test_importar_macro_sin_los_pasos_no_marcados(app_wx, config, respuestas, destruir):
	macro = Macro("Riesgo", pasos=[Paso("ir_a_carpeta", "C:\\"), Paso("ejecutar_linea", "del /s /q %P"), Paso("menu_usuario", "Compilar")])
	dialogo = pe_macros.DialogoImportarMacro(None, macro, [])
	destruir(dialogo)
	assert [dialogo.lista.IsChecked(i) for i in range(3)] == [True, False, False]
	assert dialogo.lista.GetString(1) == "Ejecutar la orden: del /s /q %P" or "del /s /q %P" in dialogo.lista.GetString(1)
	assert dialogo.aceptar()
	assert dialogo.quitados == 2 and [p.orden for p in dialogo.importada.pasos] == ["ir_a_carpeta"]


def test_orden_de_lectura_como_mucho_15(app_wx, destruir):
	columnas = [f"c{i}" for i in range(20)]
	dialogo = pe_orden_lectura.DialogoOrdenLectura(None, [("pestana", "Esta pestaña", columnas, [])])
	destruir(dialogo)
	assert len(dialogo.marcadas()) == 15
	assert dialogo.marcar(16) is False
	dialogo.lista.SetSelection(1)
	dialogo.mover(-1)
	assert dialogo.marcadas()[0] == "c1"


def test_vistas_aplicar_a_esta_carpeta(app_wx, config, respuestas, destruir):
	pe, _v = _pe(config)
	panel = PanelFalso()
	dialogo = pe_vistas.DialogoVistas(None, pe, panel)
	destruir(dialogo)
	pe.vistas.conjuntos.append(ConjuntoVista("Música", ("nombre", "tamano")))
	dialogo.rellenar(0)
	assert dialogo.aplicar_ruta()
	assert pe.vistas.reglas[0].patron == "D:\\Música\\**"
	config.establecer("vista.columnas_por_carpeta", True)
	pe.al_cambiar_carpeta(panel=panel, ruta=panel.ruta)
	assert panel.conjunto is not None and panel.conjunto.nombre == "Música"


def test_regla_de_tamano_desde_el_editor(app_wx, respuestas, destruir):
	assert pe_reglas.leer_tamano("1 GB") == 1024 ** 3 and pe_reglas.leer_tamano("1,5 kb") == 1536
	dialogo = pe_reglas.DialogoRegla(None, pe_reglas.Regla("Grandes"))
	destruir(dialogo)
	dialogo.mayor.ChangeValue("1 GB")
	dialogo.color.SetSelection(1)
	assert dialogo.aceptar()
	assert dialogo.regla.condicion.tamano_min == 1024 ** 3
	assert any("solo se ve" in a for a in respuestas.avisos)


def test_menus_ocultar_y_hueco_de_la_barra_de_teclas(app_wx, respuestas, destruir):
	dialogo = pe_menus.DialogoMenus(None, menus_personalizados.DatosMenus(), _mapa())
	destruir(dialogo)
	indice = next(i for i, (o, _t) in enumerate(dialogo.fabrica) if o == "copiar")
	dialogo.casillas.Check(indice, False)
	assert dialogo.poner_hueco("Shift+F7", "favoritos")
	assert dialogo.aceptar()
	assert dialogo.datos.ocultas == ["copiar"]
	assert dialogo.datos.barra_teclas["Shift+F7"] == ("favoritos", "")
	assert "Shift+F7" in dialogo.personalizadas().get("favoritos", [])


def test_teclas_globales_desde_la_lista(app_wx, config, respuestas, destruir):
	dialogo = pe_teclas_globales.DialogoTeclasGlobales(None, config)
	destruir(dialogo)
	assert "traer_al_frente" in dialogo.ids and "eliminar" not in dialogo.ids
	assert dialogo.poner("traer_al_frente", "Ctrl+Alt+Shift+Z")
	assert config.obtener("teclado.globales") == {"traer_al_frente": "Ctrl+Alt+Shift+Z"}
	assert not dialogo.poner("ir_a_carpeta", "Ctrl+Alt+Shift+Z"), "repetida"
	dialogo.lista.enfocar_fila(0, anunciar=False)
	dialogo.quitar()
	assert config.obtener("teclado.globales") == {}
	assert teclas_globales.validas({"eliminar": "Ctrl+Alt+E"}, ordenes.POR_ID.get) == {}


def test_paleta_ctrl_d_favorita_y_primero_las_favoritas(app_wx, destruir):
	from app.services import paleta
	from app.ui.dialogos import f_paleta

	paleta.fijar(paleta.Paleta(retraso_s=0))
	try:
		dialogo = f_paleta.DialogoPaleta(None, _mapa())
		destruir(dialogo)
		dialogo.campo.ChangeValue("mover")
		dialogo.filtrar(anunciar=False)
		assert dialogo.alternar_favorita() is True
		dialogo.campo.ChangeValue("")
		dialogo.filtrar(anunciar=False)
		assert dialogo.visibles[0].id == dialogo.visibles[0].id and paleta.actual().es_favorita(dialogo.visibles[0].id)
		assert dialogo.lista.GetString(0).startswith("Favorita:")
	finally:
		paleta.fijar(None)


def test_pagina_de_un_complemento_en_preferencias(app_wx, config, destruir):
	"""Las páginas de PL (``pl_preferencias``) van bajo «Complementos» y ``pagina="complemento:<id>"`` las abre."""
	from app.plugins import config_plugins, registro

	id_complemento = registro.complementos()[0].manifiesto.id
	anteriores = config_plugins.registro().declaraciones(id_complemento)
	config_plugins.registro().declarar(id_complemento, [{"clave": "nivel", "tipo": "entero", "defecto": 5, "etiqueta": "&Nivel",
		"ayuda": "Nivel de prueba para buscar.", "minimo": 0, "maximo": 10}])
	try:
		dialogo = f_preferencias.DialogoPreferenciasZ(None, config, pagina=f"complemento:{id_complemento}")
		destruir(dialogo)
		assert dialogo.pagina_pedida_encontrada
		indice = dialogo.indice_de(f"complemento:{id_complemento}")
		assert dialogo.libro.GetSelection() == indice
		assert dialogo.libro.GetPageParent(indice) == dialogo.titulos().index("Complementos")
		afirmar_teclado_correcto(dialogo)
		assert ("", indice) in dialogo.buscar_opciones("nivel de prueba")
		assert dialogo.aplicar()
	finally:
		config_plugins.registro().declarar(id_complemento, anteriores)
