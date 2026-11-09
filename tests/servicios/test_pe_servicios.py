# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Servicios del bloque PE, personalización avanzada (diseño 2.0, sección 10 y 18.2). Sin ventanas."""

from __future__ import annotations

import time
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.configuracion import Configuracion
from app.services import (
	alias,
	arranque_windows,
	confirmaciones,
	esquemas_teclas,
	linea_ordenes,
	macros,
	menus_personalizados,
	paleta,
	perfiles_propios,
	plantillas,
	reglas,
	teclas_globales,
	vistas_carpeta,
)
from app.services.macros import Macro, Paso
from app.services.vfs.base import Entrada
from app.ui import ordenes

# ── Esquemas de teclas ──────────────────────────────────────────────────────


def test_explorador_deja_f2_en_renombrar_y_menu_usuario_sin_tecla():
	teclas = ordenes.teclas_por_defecto("explorador")
	assert "F2" in teclas["renombrar"]
	assert teclas["menu_usuario"] == ()
	assert "Ctrl+Shift+N" in teclas["crear_carpeta"]


def test_far_ctrl_i_no_confirmada_queda_como_norton():
	assert "filtro" not in esquemas_teclas.ESQUEMAS["far"]
	assert ordenes.teclas_por_defecto("far")["filtro"] == ordenes.teclas_por_defecto("norton")["filtro"]


def test_diferencias_de_un_esquema():
	fabrica = {o.id: tuple(o.teclas) for o in ordenes.catalogo()}
	cambios = {d.orden: d for d in esquemas_teclas.diferencias(fabrica, "norton", "total_commander")}
	assert cambios["filtro_rapido"].nuevas == ("Ctrl+S",)
	assert cambios["busqueda_rapida"].nuevas == ()
	assert esquemas_teclas.diferencias(fabrica, "far", "far") == []


# ── Macros ───────────────────────────────────────────────────────────────────


def test_macros_se_guardan_y_cargan(tmp_path):
	lista = [Macro("Fotos", "Ctrl+Alt+F", True, False, [Paso("ir_a_carpeta", "D:\\Fotos"), Paso("copiar", {"destino": "E:\\", "sin_dialogo": True})])]
	macros.guardar(lista, tmp_path)
	cargadas = macros.cargar(tmp_path)
	assert cargadas[0].como_dict() == lista[0].como_dict()
	assert cargadas[0].pasos[1].espera() and not cargadas[0].pasos[0].espera()


def test_nombre_de_macro_sin_dos_puntos():
	with pytest.raises(macros.ErrorMacro):
		macros.validar_nombre("a:b")
	assert macros.validar_nombre("  Mi   macro ") == "Mi macro"


def test_grabador_anota_orden_y_argumento_del_dialogo():
	grabador = macros.Grabador()
	grabador.empezar()
	grabador.anotar("ir_a_carpeta", "D:\\Fotos")
	grabador.anotar("marcar_patron", None)
	grabador.anotar_argumento("*.jpg")
	grabador.anotar("copiar", None)
	grabador.anotar_argumento({"destino": "E:\\Copia", "politica": "omitir", "verificar": False, "otro": 1})
	pasos = grabador.terminar()
	assert [(p.orden, p.argumento) for p in pasos] == [
		("ir_a_carpeta", "D:\\Fotos"), ("marcar_patron", "*.jpg"),
		("copiar", {"destino": "E:\\Copia", "politica": "omitir", "verificar": False, "sin_dialogo": True}),
	]
	assert grabador.grabando is False


def test_importar_deja_sin_marcar_lo_que_ejecuta(tmp_path):
	macro = Macro("Peligrosa", pasos=[Paso("ir_a_carpeta", "C:\\"), Paso("ejecutar_linea", "del /s /q %P"), Paso("macro:Otra")])
	ruta = tmp_path / "m.zcmacro"
	macros.exportar(macro, ruta)
	leida = macros.leer_archivo(ruta)
	assert [macros.ejecuta_programas(p) for p in leida.pasos] == [False, True, True]
	texto = macros.texto_paso(leida.pasos[1], lambda i: "Ejecutar en la línea de órdenes")
	assert texto == "Ejecutar en la línea de órdenes: del /s /q %P"
	assert len(macros.sin_pasos(leida, [1, 2]).pasos) == 1


class AnfitrionFalso:
	"""Ejecuta las órdenes con funciones falsas; los ``llamar_mas_tarde`` se encolan y se corren con ``correr``."""

	def __init__(self, ordenes_falsas, config=None) -> None:
		self.ordenes = ordenes_falsas
		self.config = config or {"macros.anunciar_pasos": False, "macros.pausa_ms": 0, "macros.detener_en_error": True}
		self.cola: list = []
		self.dichos: list[str] = []
		self.ejecutadas: list[tuple[str, object]] = []
		self.al_empezar = self.al_terminar = None

	def ejecutar_orden_futuro(self, id_orden, argumento=None) -> Future:
		self.ejecutadas.append((id_orden, argumento))
		futuro: Future = Future()
		resultado = self.ordenes[id_orden](argumento, self)
		if isinstance(resultado, Future):
			return resultado
		futuro.set_result(resultado is not False)
		return futuro

	def llamar_mas_tarde(self, ms, funcion) -> None:
		self.cola.append(funcion)

	def anunciar(self, texto, nivel, sonido="") -> None:
		self.dichos.append(texto)

	def sonar(self, evento) -> None:
		self.dichos.append(f"sonido {evento}")

	def obtener(self, clave):
		return self.config[clave]

	def suscribir_operaciones(self, al_empezar, al_terminar):
		self.al_empezar, self.al_terminar = al_empezar, al_terminar
		return lambda: None

	def leyendo(self) -> bool:
		return False

	def estado_paneles(self):
		return object()  # cada consulta, distinto: la navegación falsa termina en el acto

	def etiqueta(self, id_orden: str) -> str:
		return {"copiar": "Copiar", "ir_a_carpeta": "Ir a la carpeta"}.get(id_orden, id_orden)

	def correr(self, maximo: int = 100) -> None:
		for _ in range(maximo):
			if not self.cola:
				return
			self.cola.pop(0)()


def test_la_macro_se_detiene_en_el_paso_que_falla():
	anfitrion = AnfitrionFalso({"ir_a_carpeta": lambda a, h: True, "copiar": lambda a, h: False, "subir": lambda a, h: True})
	macro = Macro("M", pasos=[Paso("ir_a_carpeta", "C:\\"), Paso("copiar"), Paso("subir")])
	ejecutor = macros.EjecutorMacros(anfitrion, lambda: [macro])
	ejecutor.ejecutar("M")
	anfitrion.correr()
	assert [o for o, _a in anfitrion.ejecutadas] == ["ir_a_carpeta", "copiar"]
	assert "La macro se detuvo en el paso 2: Copiar" in anfitrion.dichos
	assert ejecutor.en_curso() is False


def test_un_paso_de_un_complemento_que_carga_no_deja_empezar_el_siguiente():
	pendiente: Future = Future()
	anfitrion = AnfitrionFalso({"zc.prueba:lento": lambda a, h: pendiente, "subir": lambda a, h: True})
	macro = Macro("M", pasos=[Paso("zc.prueba:lento"), Paso("subir")])
	ejecutor = macros.EjecutorMacros(anfitrion, lambda: [macro])
	ejecutor.ejecutar("M")
	anfitrion.correr()
	assert [o for o, _a in anfitrion.ejecutadas] == ["zc.prueba:lento"], "el segundo espera a que se resuelva el futuro"
	pendiente.set_result(True)
	anfitrion.correr()
	assert [o for o, _a in anfitrion.ejecutadas] == ["zc.prueba:lento", "subir"]
	assert "Macro M terminada" in anfitrion.dichos


def test_copiar_espera_al_fin_de_su_operacion():
	operacion = SimpleNamespace(orden_origen="copiar", estado=SimpleNamespace(final=False, value="en_marcha"))

	def copiar(argumento, anfitrion):
		anfitrion.al_empezar(operacion)
		return True

	anfitrion = AnfitrionFalso({"copiar": copiar, "subir": lambda a, h: True})
	macro = Macro("M", pasos=[Paso("copiar", {"destino": "E:\\", "sin_dialogo": True}), Paso("subir")])
	ejecutor = macros.EjecutorMacros(anfitrion, lambda: [macro])
	ejecutor.ejecutar("M")
	anfitrion.correr()
	assert [o for o, _a in anfitrion.ejecutadas] == ["copiar"]
	operacion.estado = SimpleNamespace(final=True, value="terminada")
	anfitrion.al_terminar(operacion)
	anfitrion.correr()
	assert [o for o, _a in anfitrion.ejecutadas] == ["copiar", "subir"]


def test_detener_la_macro_en_curso():
	pendiente: Future = Future()
	anfitrion = AnfitrionFalso({"a": lambda a, h: pendiente})
	ejecutor = macros.EjecutorMacros(anfitrion, lambda: [Macro("M", pasos=[Paso("a"), Paso("a")])])
	ejecutor.ejecutar("M")
	anfitrion.correr()
	assert ejecutor.detener() is True and ejecutor.en_curso() is False
	pendiente.set_result(True)
	anfitrion.correr()
	assert len(anfitrion.ejecutadas) == 1


def test_macro_que_se_llama_a_si_misma_no_se_ejecuta():
	anfitrion = AnfitrionFalso({})
	ejecutor = macros.EjecutorMacros(anfitrion, lambda: [Macro("A", pasos=[Paso("macro:A")])])
	ejecutor.ejecutar("A")
	assert anfitrion.ejecutadas == [] and any("demasiadas veces" in d for d in anfitrion.dichos)


# ── Alias y línea de órdenes ─────────────────────────────────────────────────


def test_alias_con_argumento_peligroso_se_expande_protegido():
	resultado = alias.expandir_linea("ll a&calc.txt", [alias.Alias("ll", "dir /a %1")])
	assert resultado is not None and not resultado.interna
	assert "&calc" not in resultado.orden, "el argumento no se pega en la orden"
	assert resultado.orden == 'dir /a "%ZC_1%"'
	assert resultado.entorno == {"ZC_1": "a&calc.txt"}


def test_alias_con_todos_los_argumentos_y_variables():
	valores = SimpleNamespace(cursor="C:\\a.txt", carpeta="C:\\", otra_carpeta="D:\\", cursor_otro="", trabajo=[])
	resultado = alias.expandir(alias.Alias("x", "copy %P %*"), ["uno", "dos"], valores)
	assert resultado.orden.count("%ZC_") == 3
	assert set(resultado.entorno.values()) == {"C:\\a.txt", "uno", "dos"}


def test_alias_zc_es_interno_y_sin_entorno():
	resultado = alias.expandir_linea("fotos", [alias.Alias("fotos", "zc ir_a_carpeta D:\\Fotos")])
	assert resultado.interna and resultado.orden == "zc ir_a_carpeta D:\\Fotos" and resultado.entorno == {}
	assert alias.expandir_linea("dir", [alias.Alias("ll", "dir")]) is None


def test_alias_no_validos():
	with pytest.raises(alias.ErrorAlias):
		alias.validar(alias.Alias("zc", "dir"))
	with pytest.raises(alias.ErrorAlias):
		alias.validar(alias.Alias("a b", "dir"))


def test_zc_ir_a_carpeta_se_reconoce_sin_procesos():
	zc = linea_ordenes.analizar_zc("zc ir_a_carpeta D:\\x")
	assert zc is not None and zc.nombre == "ir_a_carpeta" and zc.resto == "D:\\x"


def test_autocompletar_rutas_y_ordenes(tmp_path):
	(tmp_path / "Documentos").mkdir()
	(tmp_path / "Docs viejos").mkdir()
	(tmp_path / "datos.txt").write_text("x", encoding="utf-8")
	opciones = linea_ordenes.candidatos("cd Do", str(tmp_path), [], [])
	assert opciones == ["Docs viejos\\", "Documentos\\"]
	completado = linea_ordenes.completar("cd Do", opciones)
	assert completado.texto == "cd Doc" and len(completado.opciones) == 2
	unico = linea_ordenes.completar("type da", linea_ordenes.candidatos("type da", str(tmp_path), [], []))
	assert unico.texto == "type datos.txt "
	assert linea_ordenes.candidatos("zc ir_", "", [], ["ir_a_carpeta", "ver"]) == ["ir_a_carpeta"]
	assert linea_ordenes.candidatos("l", str(tmp_path), ["ll"], []) == ["ll"]
	assert linea_ordenes.poner_opcion("cd Do", "Docs viejos\\") == 'cd "Docs viejos\\'


# ── Reglas ───────────────────────────────────────────────────────────────────


def test_regla_mas_de_1_gb_con_texto_y_sonido():
	grandes = reglas.Regla("Grandes", condicion=reglas.Condicion(tamano_min=1024 ** 3), texto="Grande", sonido="regla.a")
	decorar = reglas.decorador(lambda: [grandes], lambda: True)
	efecto = decorar(Entrada("iso.iso", "C:\\iso.iso", tamano=2 * 1024 ** 3))
	assert efecto is not None and efecto.texto == "Grande" and efecto.sonido == "regla.a"
	assert decorar(Entrada("p.txt", "C:\\p.txt", tamano=10)) is None
	assert reglas.decorador(lambda: [grandes], lambda: False)(Entrada("i", "C:\\i", tamano=2 * 1024 ** 3)) is None


def test_reglas_primera_que_coincide_y_condiciones(tmp_path):
	ahora = time.time()
	hoy = reglas.Regla("Hoy", condicion=reglas.Condicion(modificado_hace_menos_de=1), texto="Hoy")
	solo = reglas.Regla("Solo", condicion=reglas.Condicion(atributos=("solo_lectura",)), texto="SL")
	entrada = Entrada("a.txt", "C:\\a.txt", modificado=ahora - 3600, atributos=0x1)
	assert reglas.primera([hoy, solo], entrada, ahora).nombre == "Hoy"
	assert reglas.primera([solo, hoy], entrada, ahora).nombre == "Solo"
	reglas.guardar([hoy, solo], tmp_path)
	assert [r.nombre for r in reglas.cargar(tmp_path)] == ["Hoy", "Solo"]


def test_regla_solo_color_avisa_y_sin_efecto_no_vale():
	assert reglas.Regla("R", color="Rojo", condicion=reglas.Condicion(patron="*.x")).solo_color()
	with pytest.raises(reglas.ErrorRegla):
		reglas.validar(reglas.Regla("R", condicion=reglas.Condicion(patron="*.x")))


# ── Vistas por carpeta ─────────────────────────────────────────────────────────


def test_vista_por_contenido_con_un_60_por_ciento_de_mp3():
	assert vistas_carpeta.proponer_conjunto("Música", ["nombre", "zc.metadatos:artista"], ["nombre"], ["mp3", "flac"], 0.6)
	assert vistas_carpeta.proponer_conjunto("Música", ["nombre"], []) is False, "no se duplica"
	datos = vistas_carpeta.cargar()
	seis_de_diez = [f"c{i}.mp3" for i in range(6)] + [f"d{i}.txt" for i in range(4)]
	cinco_de_diez = [f"c{i}.mp3" for i in range(5)] + [f"d{i}.txt" for i in range(5)]
	assert vistas_carpeta.elegir(datos, "E:\\Varios", seis_de_diez).nombre == "Música"
	assert vistas_carpeta.elegir(datos, "E:\\Varios", cinco_de_diez) is None
	assert vistas_carpeta.conjuntos() == ["Música"]


def test_vista_por_ruta_antes_que_contenido_y_recordadas():
	datos = vistas_carpeta.DatosVistas()
	from app.services.vistas_modelo import ConjuntoVista

	datos.conjuntos = [ConjuntoVista("A"), ConjuntoVista("B")]
	datos.reglas = [vistas_carpeta.ReglaVista("contenido", "B", extensiones=("txt",), proporcion=0.5),
		vistas_carpeta.ReglaVista("ruta", "A", patron="D:\\Música\\**")]
	assert vistas_carpeta.elegir(datos, "D:\\Música\\Rock\\80", ["a.txt"]).nombre == "A"
	assert vistas_carpeta.elegir(datos, "D:\\Música", []).nombre == "A"
	assert vistas_carpeta.elegir(datos, "D:\\Músicas", ["a.txt"]).nombre == "B"
	for i in range(vistas_carpeta.MAX_RECORDADAS + 5):
		vistas_carpeta.recordar(datos, f"C:\\c{i}", "fecha", True, "completa", "")
	assert len(datos.recordadas) == vistas_carpeta.MAX_RECORDADAS and vistas_carpeta.recordada(datos, "C:\\c0") is None
	assert vistas_carpeta.lectura_valida([f"c{i}" for i in range(20)] + ["c1"]) == [f"c{i}" for i in range(15)]


# ── Menús personalizados y menús por nivel ───────────────────────────────────


def _personalizador(datos, nivel="novato", por_nivel=True, todas=False):
	return menus_personalizados.Personalizador(lambda: datos, lambda: nivel, lambda: por_nivel, lambda: todas, ordenes.POR_ID.get)


def _ids(elementos) -> set[str]:
	resultado = set()
	for e in elementos:
		if isinstance(e, tuple):
			resultado |= _ids(e[1]) if isinstance(e[1], list | tuple) else set()
		elif e:
			resultado.add(e)
	return resultado


def test_novato_con_menus_por_nivel_no_ve_crear_enlace():
	menus = _personalizador(menus_personalizados.DatosMenus()).menus(ordenes.menus())
	todos = set().union(*(_ids(c) for _t, c in menus if c != ordenes.LADO))
	assert "crear_enlace" not in todos and "copiar" in todos
	assert "crear_enlace" in set().union(*(_ids(c) for _t, c in _personalizador(menus_personalizados.DatosMenus(), todas=True).menus(
		ordenes.menus()) if c != ordenes.LADO))
	archivos = dict(menus)["&Archivos"]
	assert archivos[-1] == "todas_las_ordenes" or "todas_las_ordenes" not in archivos


def test_ocultar_y_mis_ordenes():
	datos = menus_personalizados.DatosMenus(ocultas=["copiar", "sin_ordenar"], mis_ordenes=["favoritos", "-", "ver"])
	personalizador = _personalizador(datos, por_nivel=False)
	menus = dict(personalizador.menus(ordenes.menus()))
	assert "copiar" not in _ids(menus["&Archivos"])
	assert menus["Mis ó&rdenes"] == ["favoritos", None, "ver"]
	assert "sin_ordenar" not in personalizador.lista(ordenes.MENU_LADO)


def test_barra_de_teclas_con_un_hueco_cambiado():
	datos = menus_personalizados.DatosMenus(barra_teclas={"Shift+F7": ("favoritos", "")})
	huecos = _personalizador(datos).barra_teclas("Shift", ordenes.BARRA_TECLAS["Shift"])
	assert huecos[6] == ("F7", "favoritos", "Favorit")
	assert menus_personalizados.etiqueta_corta("&Buscar duplicados...") == "Buscar"


# ── Confirmaciones ────────────────────────────────────────────────────────────


def test_confirmacion_silenciada_no_pregunta_y_se_recupera(tmp_path):
	config = Configuracion(ruta=tmp_path / "s.json")
	confirmaciones.silenciar(config, "esquema_cambio")
	assert confirmaciones.debe_preguntar(config, "esquema_cambio") is False
	confirmaciones.volver_a_preguntar(config)
	assert confirmaciones.debe_preguntar(config, "esquema_cambio") is True


def test_eliminar_definitivamente_no_es_silenciable(tmp_path):
	config = Configuracion(ruta=tmp_path / "s.json")
	assert "eliminar_definitivo" not in confirmaciones.CONFIRMACIONES
	with pytest.raises(ValueError):
		confirmaciones.silenciar(config, "eliminar_definitivo")


# ── Paleta, perfiles, plantillas, teclas globales, arranque con Windows ──────


def test_paleta_favoritas_y_frecuentes(tmp_path):
	p = paleta.Paleta(tmp_path, retraso_s=0)
	for _ in range(3):
		p.al_terminar_orden(id="copiar", ok=True)
	p.al_terminar_orden(id="ver", ok=True)
	p.al_terminar_orden(id="mover", ok=False)
	assert p.frecuentes() == ["copiar", "ver"]
	assert p.alternar_favorita("mover") is True
	assert p.primero(["copiar", "ver", "mover", "eliminar"]) == ["mover", "copiar", "ver"]
	otra = paleta.Paleta(tmp_path)
	assert otra.favoritas == ["mover"] and otra.usos == {"copiar": 3, "ver": 1}


def test_perfil_propio_guardar_aplicar_renombrar(tmp_path):
	config = Configuracion(ruta=tmp_path / "s.json")
	config.establecer("vista.tamano_fuente", 18)
	perfil = perfiles_propios.capturar(config, "Clase")
	assert "ventana.x" not in perfil.valores and "general.asistente_hecho" not in perfil.valores
	perfiles_propios.guardar(perfil)
	config.establecer("vista.tamano_fuente", 10)
	cargado = perfiles_propios.listar()[0]
	assert perfiles_propios.aplicar(config, cargado) == 1 and config.obtener("vista.tamano_fuente") == 18
	perfiles_propios.renombrar("Clase", "Martes")
	assert [p.nombre for p in perfiles_propios.listar()] == ["Martes"]
	with pytest.raises(perfiles_propios.ErrorPerfil):
		perfiles_propios.validar_nombre("Novato", ("Novato",))


def test_plantillas_de_serie_con_variables(tmp_path):
	serie = Path(__file__).resolve().parents[2] / "data" / "docs" / "plantillas"
	disponibles = plantillas.disponibles(serie, tmp_path / "no")
	nombres = {p.titulo for p in disponibles}
	assert {"Texto con fecha", "Markdown con título", "HTML básico", "CSV con cabecera", "Archivo por lotes"} <= nombres
	md = next(p for p in disponibles if p.extension == ".md")
	assert plantillas.nombre_final("notas", md) == "notas.md" and plantillas.nombre_final("x.txt", md) == "x.txt"
	assert plantillas.contenido(md, "notas.md").decode("utf-8").startswith("# notas")
	propia = plantillas.preparar_carpeta_propia(serie, tmp_path / "propias")
	assert (propia / "HTML básico.html").exists()


def test_teclas_globales_lista_blanca_y_comprobacion():
	assert teclas_globales.permitida("traer_al_frente") and teclas_globales.permitida("macro:X")
	assert not teclas_globales.permitida("eliminar", ordenes.POR_ID["eliminar"])
	assert teclas_globales.comprobar("ctrl+alt+mayús+z", "ir_a_carpeta", {}) == "Ctrl+Alt+Shift+Z"
	with pytest.raises(ValueError):
		teclas_globales.comprobar("Shift+Z", "ir_a_carpeta", {})
	with pytest.raises(ValueError):
		teclas_globales.comprobar("Ctrl+Alt+Z", "ir_a_carpeta", {"traer_al_frente": "Ctrl+Alt+Z"})


def test_arranque_windows_ruta_registrada():
	assert arranque_windows.ruta_registrada('"C:\\zc\\ZCommander.exe" --al-iniciar-sesion') == Path("C:\\zc\\ZCommander.exe")
	assert arranque_windows.orden(Path("C:\\a b\\z.exe")) == '"C:\\a b\\z.exe" --al-iniciar-sesion'


@pytest.mark.interfaz
def test_arrancar_con_windows_escribe_y_borra_el_valor():
	clave = r"Software\zCommanderPruebas\Run"
	exe = Path("C:\\Pruebas\\ZCommander.exe")
	try:
		arranque_windows.aplicar(True, exe, clave)
		assert arranque_windows.leer(clave) == '"C:\\Pruebas\\ZCommander.exe" --al-iniciar-sesion'
		assert arranque_windows.apunta_a_otra_carpeta(Path("D:\\Otra\\ZCommander.exe"), clave)
		assert not arranque_windows.apunta_a_otra_carpeta(exe, clave)
		arranque_windows.aplicar(False, exe, clave)
		assert arranque_windows.leer(clave) is None
	finally:
		import winreg

		for subclave in (clave, r"Software\zCommanderPruebas"):
			try:
				winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subclave)
			except OSError:
				pass
