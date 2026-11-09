# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque F: diálogos y personalización.

Menú de usuario y asociaciones (8.17), favoritos, historiales, árbol y
unidades (8.1), columnas, preferencias, perfil, mapa de teclas, paleta,
ayuda de teclado y asistente (8.26 y 8.27) y valores de fábrica.

Cada manejador recibe un ``ContextoOrden`` en el hilo de la interfaz. Lo que
puede tardar (consultar unidades, resolver una ruta, leer un comprimido) va a
``ctx.tareas`` o lo hace el panel en su hilo (``ir_a_texto``/``ir_historial``).
Los diálogos viven en ``app/ui/dialogos/f_*.py``; aquí solo se decide qué
hacer con lo que devuelven.
"""

from __future__ import annotations

import builtins
import logging
import os
import tempfile
from collections.abc import Callable, Sequence

from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mensaje(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or str(error)


def _ir_texto(panel, texto: str, al_fallar: Callable[[BaseException], None] | None = None) -> None:
	"""Lleva ``panel`` a una ruta escrita (se resuelve en un hilo del panel).

	``ir_a_texto`` es del panel real; el protocolo garantiza ``ir_historial``,
	que hace lo mismo sin el aviso de fallo propio.
	"""
	ir_a_texto = getattr(panel, "ir_a_texto", None)
	if callable(ir_a_texto):
		ir_a_texto(texto, al_fallar=al_fallar)
	else:
		panel.ir_historial(texto)


def _panel_de_lado(ctx, lado: str | None):
	if lado == "izquierdo":
		return ctx.izquierdo
	if lado == "derecho":
		return ctx.derecho
	return ctx.objetivo


# ── Menú de usuario ─────────────────────────────────────────────────────────

def _menu_local(ctx):
	"""Menú local de la carpeta del panel activo, preguntando la confianza si hace falta.

	Devuelve el ``MenuLocal`` (solo se usará si quedó de confianza) y un aviso
	para el diálogo (por ejemplo, «el menú de esta carpeta está dañado»).
	"""
	from app.services import menu_usuario
	from app.ui.dialogos import f_comun

	carpeta = ctx.activo.ruta_local()
	menu = menu_usuario.leer_local(carpeta)
	if menu is None:
		return None, ""
	if menu.error:
		return menu, _("Esta carpeta tiene un menú propio que no se puede usar: {e}").format(e=menu.error)
	if not menu.entradas:
		return menu, ""
	estado = menu_usuario.estado_confianza(ctx.config.obtener(menu_usuario.CLAVE_CONFIANZA) or {}, menu)
	if estado == menu_usuario.CONFIADO:
		return menu, ""
	inicio = (_("El menú de usuario de esta carpeta ha cambiado desde que confió en él.") if estado == menu_usuario.CAMBIADO
		else _("Esta carpeta tiene su propio menú de usuario ({a}).").format(a=menu_usuario.NOMBRE_LOCAL))
	texto = "\n".join([
		inicio,
		_("Sus órdenes se ejecutarían en su equipo con su usuario. Úselo solo si sabe de dónde viene esta carpeta."),
		"",
		_("Contenido:"),
		*menu_usuario.resumen_ordenes(menu.entradas),
	])
	eleccion = f_comun.elegir(ctx.ventana, texto, _("Menú de usuario de la carpeta"),
		[_("C&onfiar y usarlo"), _("&No usarlo")])
	if eleccion == 0:
		menu_usuario.confiar(ctx.config, menu)
		return menu, ""
	return menu, _("El menú de esta carpeta no se usa porque no se ha confiado en él.")


def valores_variables(ctx):
	"""``variables.Valores`` desde los paneles (solo rutas del disco: en un servidor no hay ruta local)."""
	from app.services.variables import Valores

	def ruta_local_de(panel, entrada) -> str:
		if entrada is None or getattr(entrada, "es_superior", False):
			return ""
		if panel.es_local():
			return entrada.ruta
		local = panel.proveedor.ruta_local(entrada.ruta) if hasattr(panel.proveedor, "ruta_local") else None
		return local or ""

	activo, pasivo = ctx.activo, ctx.pasivo
	trabajo = [r for r in (ruta_local_de(activo, e) for e in activo.elementos_trabajo()) if r]
	return Valores(
		cursor=ruta_local_de(activo, activo.cursor()),
		carpeta=activo.ruta_local() or "",
		otra_carpeta=pasivo.ruta_local() or "",
		cursor_otro=ruta_local_de(pasivo, pasivo.cursor()),
		trabajo=trabajo,
	)


def _crear_lista(rutas: Sequence[str]) -> str:
	"""Archivo para ``%L``: una ruta por línea, UTF-8, en ``data/temp`` (se borra al arrancar)."""
	from app.core import paths

	carpeta = paths.ruta_temporales()
	carpeta.mkdir(parents=True, exist_ok=True)
	descriptor, ruta = tempfile.mkstemp(prefix="zc_lista_", suffix=".txt", dir=str(carpeta))
	with os.fdopen(descriptor, "w", encoding="utf-8", newline="\r\n") as salida:
		salida.write("\n".join(rutas) + ("\n" if rutas else ""))
	return ruta


def ejecutar_entrada(ctx, entrada) -> bool:
	"""Expande las órdenes de la entrada y las lanza con el servicio de la línea de órdenes."""
	from app.services import menu_usuario, variables
	from app.ui.dialogos import f_comun

	plantilla = menu_usuario.plantilla(entrada)
	if not plantilla:
		anuncios.anunciar(_("La entrada «{e}» no tiene órdenes").format(e=entrada.etiqueta), anuncios.RESULTADO)
		return False

	def pedir(titulo: str, inicial: str) -> str | None:
		return f_comun.pedir(ctx.ventana, f"&{titulo or _('Dato')}:", entrada.etiqueta, inicial)

	try:
		expansion = variables.expandir(plantilla, valores_variables(ctx), pedir=pedir, crear_lista=_crear_lista)
	except variables.Cancelada:
		anuncios.anunciar(_("Cancelado"), anuncios.RESULTADO)
		return False
	except (ValueError, OSError) as error:
		log.warning("No se pudo preparar la entrada %s del menú de usuario: %s", entrada.etiqueta, error)
		f_comun.avisar(ctx.ventana, _("No se puede ejecutar «{e}»: {m}").format(e=entrada.etiqueta, m=error), _("Menú de usuario"))
		return False
	ctx.servicio("linea").ejecutar(expansion, consola=entrada.consola, refrescar=entrada.refrescar)
	anuncios.anunciar(_("Ejecutando: {e}").format(e=entrada.etiqueta), anuncios.NORMAL)
	return True


def menu_usuario(ctx) -> None:
	from app.services import menu_usuario as servicio
	from app.ui.dialogos import f_menu_usuario

	menu_local, aviso = _menu_local(ctx)
	entradas = servicio.entradas_disponibles(ctx.config, menu_local)
	if not entradas and not aviso:
		anuncios.anunciar(_("El menú de usuario está vacío. Créelo en Opciones, Editar el menú de usuario."), anuncios.RESULTADO)
		return
	if getattr(ctx, "argumento", None):
		# 2.0 (10.1): una macro nombra la entrada por su etiqueta.
		buscada = str(ctx.argumento).replace("&", "").casefold()
		entrada = next((e for e in entradas if e.etiqueta.replace("&", "").casefold() == buscada), None)
		if entrada is None:
			anuncios.anunciar(_("No hay ninguna entrada «{e}» en el menú de usuario").format(e=ctx.argumento), anuncios.ESENCIAL)
			return
		ejecutar_entrada(ctx, entrada)
		return
	entrada = f_menu_usuario.elegir_entrada(ctx.ventana, entradas, aviso)
	if entrada is not None:
		try:
			ctx.servicio("grabador").anotar_argumento(entrada.etiqueta.replace("&", ""))
		except (KeyError, AttributeError):
			log.debug("Sin grabador de macros", exc_info=True)
		ejecutar_entrada(ctx, entrada)


def editar_menu_usuario(ctx) -> None:
	from app.services import menu_usuario as servicio
	from app.ui.dialogos import f_comun, f_menu_usuario

	editadas = f_menu_usuario.editar_menu(ctx.ventana, servicio.cargar())
	if editadas is None:
		return
	try:
		servicio.guardar(editadas)
	except OSError as error:
		log.error("No se pudo guardar el menú de usuario", exc_info=True)
		f_comun.avisar(ctx.ventana, _("No se pudo guardar el menú de usuario: {e}").format(e=error), _("Menú de usuario"))
		return
	anuncios.anunciar(_("Menú de usuario guardado: {n} entradas").format(n=len(editadas)), anuncios.RESULTADO)


def editar_asociaciones(ctx) -> None:
	from app.services import asociaciones
	from app.ui.dialogos import f_asociaciones, f_comun

	reglas = f_asociaciones.editar_asociaciones(ctx.ventana, asociaciones.cargar())
	if reglas is None:
		return
	try:
		asociaciones.guardar(reglas)
	except OSError as error:
		log.error("No se pudieron guardar las asociaciones", exc_info=True)
		f_comun.avisar(ctx.ventana, _("No se pudieron guardar las asociaciones: {e}").format(e=error), _("Asociaciones"))
		return
	anuncios.anunciar(_("Asociaciones guardadas: {n} reglas").format(n=len(reglas)), anuncios.RESULTADO)


# ── Favoritos, historiales, árbol y unidades ────────────────────────────────

def favoritos(ctx) -> None:
	from app.ui.dialogos import f_favoritos

	panel = ctx.activo
	elegido = f_favoritos.elegir_favorito(ctx.ventana, panel.mostrar_ruta())
	if elegido is not None:
		_ir_texto(panel, elegido.ruta, lambda e: anuncios.anunciar(
			_("No se puede ir a «{n}»: {m}").format(n=elegido.nombre, m=_mensaje(e)), anuncios.ESENCIAL))


def agregar_favorito(ctx) -> None:
	from app.services import favoritos as servicio
	from app.ui.dialogos import f_comun, f_favoritos

	panel = ctx.activo
	ruta = panel.mostrar_ruta()
	if panel.es_lista():
		anuncios.anunciar(_("Una lista de resultados no se puede añadir a favoritos"), anuncios.RESULTADO)
		return
	lista = servicio.cargar()
	existente = servicio.buscar(lista, ruta)
	inicial = lista[existente].nombre if existente is not None else servicio.nombre_sugerido(ruta)
	nombre = f_comun.pedir(ctx.ventana, _("&Nombre del favorito:"), _("Añadir a favoritos"), inicial,
		ayuda=_("Nombre con el que aparecerá en Favoritos (Ctrl+D). Carpeta: {r}").format(r=ruta))
	if nombre is None:
		return
	indice = servicio.agregar(lista, nombre, ruta)
	if f_favoritos.guardar(ctx.ventana, lista):
		texto = _("Favorito renombrado: {n}") if existente is not None else _("Añadido a favoritos: {n}")
		anuncios.anunciar(texto.format(n=lista[indice].nombre), anuncios.RESULTADO)


def historial_carpetas(ctx) -> None:
	from app.ui.dialogos import f_historial

	panel = ctx.activo
	carpetas = [c for c in panel.historial() if c]
	if not carpetas:
		anuncios.anunciar(_("El historial de este panel está vacío"), anuncios.RESULTADO)
		return
	elegida = f_historial.elegir_carpeta(ctx.ventana, carpetas)
	if elegida:
		panel.ir_historial(elegida)


def historial_ordenes(ctx) -> None:
	from app.ui.dialogos import f_historial

	linea = ctx.servicio("linea")
	ordenes_previas = [o for o in linea.historial() if o]
	if not ordenes_previas:
		anuncios.anunciar(_("Todavía no se ha ejecutado ninguna orden"), anuncios.RESULTADO)
		return
	resultado = f_historial.elegir_orden(ctx.ventana, ordenes_previas)
	if resultado is None or not resultado[0]:
		return
	orden, accion = resultado
	linea.poner(orden)
	if accion == f_historial.EJECUTAR:
		ctx.ejecutar_orden("ejecutar_linea")


def arbol_carpetas(ctx) -> None:
	from app.ui.dialogos import f_arbol

	panel = ctx.activo
	if panel.es_lista():
		anuncios.anunciar(_("Una lista de resultados no tiene árbol de carpetas"), anuncios.RESULTADO)
		return
	proveedor = panel.proveedor
	raiz = proveedor.raiz(panel.ruta) if panel.ruta else ""

	def lanzar(operacion, al_terminar) -> None:
		ctx.lanzar(operacion, al_terminar=al_terminar)

	elegida = f_arbol.elegir_carpeta(ctx.ventana, proveedor, raiz, panel.ruta, ctx.tareas, lanzar,
		papelera=bool(ctx.config.obtener("general.usar_papelera")))
	if elegida is not None and elegida != panel.ruta:
		panel.ir_a(elegida, proveedor)


def _consultar_unidades(letras: list[str], segundos: float) -> list:
	from app.services.windows import unidades

	return [unidades.info_unidad_con_limite(letra, segundos) for letra in letras]


def unidad(ctx) -> None:
	"""Alt+F1, Alt+F2 y «Unidad...» del menú de un lado: el lado sale del ``param`` o del menú."""
	from app.services import favoritos as servicio_favoritos
	from app.services.windows import unidades
	from app.ui.dialogos import f_unidades
	from app.ui.panel_archivos import nombre_lado

	lado = ctx.param or ctx.lado_objetivo or ctx.activo.lado
	panel = _panel_de_lado(ctx, lado)
	try:
		letras = unidades.letras()
	except (AttributeError, OSError):
		log.warning("No se pudieron leer las letras de unidad", exc_info=True)
		letras = []
	favs = [(f.nombre, f.ruta) for f in servicio_favoritos.cargar()]
	destinos = f_unidades.destinos_iniciales(letras, unidades.tipo_de, favs, unidades.carpetas_especiales())
	segundos = min(5.0, float(ctx.config.obtener("general.tiempo_unidad_s")))
	elegido = f_unidades.elegir_destino(ctx.ventana, _("Unidad del lado {l}").format(l=nombre_lado(panel.lado).lower()), destinos,
		panel.ruta_local() or panel.mostrar_ruta(), ctx.tareas, lambda ls: _consultar_unidades(ls, segundos))
	if elegido is None:
		return
	destino = elegido.ruta
	if elegido.tipo == f_unidades.UNIDAD:
		destino = panel.ultima_carpeta(elegido.letra) or elegido.ruta

		def al_fallar(_error) -> None:
			# La última carpeta de esa unidad ya no existe (o no responde): a la raíz.
			if destino != elegido.ruta:
				_ir_texto(panel, elegido.ruta, lambda e: anuncios.anunciar(_mensaje(e), anuncios.ESENCIAL))
			else:
				anuncios.anunciar(_("La unidad {u} no está disponible").format(u=elegido.letra), anuncios.ESENCIAL)

		_ir_texto(panel, destino, al_fallar)
	else:
		_ir_texto(panel, destino, lambda e: anuncios.anunciar(_mensaje(e), anuncios.ESENCIAL))
	panel.enfocar()


# ── Columnas ────────────────────────────────────────────────────────────────

def columnas(ctx) -> None:
	"""Columnas de la pestaña del lado (las del menú Izquierdo o Derecho, o el activo)."""
	from app.ui.dialogos import f_columnas
	from app.ui.panel_archivos import nombre_lado

	panel = ctx.objetivo
	anchos = dict(ctx.config.obtener("paneles.anchos") or {})
	lista = panel.lista() if hasattr(panel, "lista") else None
	if lista is not None and hasattr(lista, "anchos"):
		anchos.update(lista.anchos())
	visibles = list(panel.columnas)
	marca_puesta = ctx.config.obtener("paneles.marcas_como") == "columna" and "marca" not in visibles
	if marca_puesta:
		# 2.0.1: la «Marca» se ve aunque la pestaña no la tenga (``PanelArchivos._con_marca``): el diálogo lo refleja.
		visibles.insert(0, "marca")
	resultado = f_columnas.elegir_columnas(ctx.ventana, _("Columnas del lado {l}").format(l=nombre_lado(panel.lado).lower()),
		visibles, anchos, ctx.config.obtener("paneles.columnas"))
	if resultado is None:
		return
	elegidas, nuevos_anchos = resultado
	panel.aplicar_columnas(elegidas, nuevos_anchos)
	if marca_puesta and "marca" in elegidas and hasattr(panel, "marca_anadida"):
		# La puso zCommander, no la persona: se quitará sola al volver a las marcas como selección.
		panel.marca_anadida = True
	anuncios.anunciar(_("Columnas: {c}").format(c=", ".join(f_columnas.titulo_columna(c) for c in elegidas)), anuncios.RESULTADO)


def columnas_defecto(ctx) -> None:
	from app.core.configuracion import ErrorConfiguracion
	from app.ui.dialogos import f_columnas, f_comun

	actuales = ctx.config.obtener("paneles.columnas")
	resultado = f_columnas.elegir_columnas(ctx.ventana, _("Columnas por defecto"), actuales,
		dict(ctx.config.obtener("paneles.anchos") or {}), ctx.config.valor_por_defecto("paneles.columnas"))
	if resultado is None:
		return
	elegidas, anchos = resultado
	todos = dict(ctx.config.obtener("paneles.anchos") or {})
	todos.update(anchos)
	try:
		ctx.config.establecer_varias({"paneles.columnas": elegidas, "paneles.anchos": todos})
	except ErrorConfiguracion as error:
		f_comun.avisar(ctx.ventana, _("No se pudieron guardar las columnas: {e}").format(e=error), _("Columnas por defecto"))
		return
	anuncios.anunciar(_("Columnas por defecto guardadas; se usan en las pestañas nuevas y en las que tenían las anteriores"), anuncios.RESULTADO)


# ── Preferencias, perfil, mapa de teclas ────────────────────────────────────

def preferencias(ctx) -> None:
	from app.ui.dialogos import f_preferencias

	f_preferencias.mostrar(ctx.ventana, ctx.config, anunciar=lambda texto: anuncios.anunciar(texto, anuncios.RESULTADO))


def perfil(ctx) -> None:
	from app.ui.dialogos import f_perfil

	f_perfil.mostrar_perfil(ctx.ventana, ctx.config)


def mapa_teclas(ctx) -> None:
	from app.core.configuracion import ErrorConfiguracion
	from app.ui.dialogos import f_comun, f_mapa_teclas

	# 2.0 (10.7): Intro sobre un .zcteclas llega con su ruta como argumento y el diálogo empieza importándolo.
	importar = str(ctx.argumento) if getattr(ctx, "argumento", None) else None
	if importar:
		nuevas = f_mapa_teclas.editar_mapa(ctx.ventana, ctx.mapa_teclas, importar=importar)
	else:
		nuevas = f_mapa_teclas.editar_mapa(ctx.ventana, ctx.mapa_teclas)
	if nuevas is None:
		return
	if nuevas == (ctx.config.obtener("teclado.personalizadas") or {}):
		anuncios.anunciar(_("Las teclas no han cambiado"), anuncios.RESULTADO)
		return
	try:
		ctx.config.establecer("teclado.personalizadas", nuevas)
	except ErrorConfiguracion as error:
		log.error("No se pudo guardar el mapa de teclas", exc_info=True)
		f_comun.avisar(ctx.ventana, _("No se pudo guardar el mapa de teclas: {e}").format(e=error), _("Mapa de teclas"))
		return
	anuncios.anunciar(_("Mapa de teclas guardado"), anuncios.RESULTADO)


# ── Ayuda para aprender las teclas ──────────────────────────────────────────

def paleta_ordenes(ctx) -> None:
	from app.ui import ordenes
	from app.ui.dialogos import f_paleta

	anuncios.anunciar("", anuncios.DETALLE, sonido="paleta.abrir")

	mapa = ctx.mapa_teclas
	elegida = f_paleta.elegir_orden(ctx.ventana, mapa)
	if elegida is None:
		return
	orden = ordenes.POR_ID[elegida]
	ctx.ejecutar_orden(elegida, ctx.lado_objetivo if orden.por_lado else None)
	# Después de ejecutar: el anuncio de la propia orden no debe pisar el atajo que se quiere aprender.
	anuncios.anunciar(f_paleta.anuncio_atajo(orden, mapa), anuncios.RESULTADO, interrumpir=False)


def ayuda_teclado(ctx) -> None:
	"""Mayús+F12: alterna el modo; la ventana anuncia la entrada y la salida (Escape también sale)."""
	ctx.modo_ayuda_teclado = not ctx.modo_ayuda_teclado


# ── Asistente y valores de fábrica ──────────────────────────────────────────

def asistente(ctx) -> None:
	from app.ui.dialogos import f_asistente, f_comun

	eleccion = f_asistente.mostrar_asistente(ctx.ventana, ctx.config)
	if eleccion is None:
		if not ctx.config.obtener("general.asistente_hecho"):
			# No se vuelve a mostrar en cada arranque: queda en Opciones.
			ctx.config.establecer("general.asistente_hecho", True)
			anuncios.anunciar(_("Asistente cancelado. Puede abrirlo cuando quiera desde Opciones."), anuncios.RESULTADO)
		return
	try:
		f_asistente.aplicar(ctx.config, eleccion)
	except Exception as error:  # noqa: BLE001 - ErrorConfiguracion u OSError: se dice a la persona
		log.exception("No se pudo aplicar lo elegido en el asistente")
		f_comun.avisar(ctx.ventana, _("No se pudo guardar lo elegido: {e}").format(e=error), _("Asistente"))
		return
	anuncios.anunciar(_("Listo. Perfil {p} aplicado.").format(p=_perfil_visible(eleccion.perfil)), anuncios.RESULTADO)
	if eleccion.abrir_manual:
		ctx.ejecutar_orden("manual")


def _perfil_visible(perfil_: str) -> str:
	from app.services import perfiles

	return perfiles.nombre_visible(perfil_)


def restablecer_fabrica(ctx) -> None:
	from app.ui.dialogos import f_comun

	texto = _(
		"¿Volver a todas las preferencias de fábrica? También se pierden las teclas personalizadas, las columnas por defecto "
		"y las carpetas de confianza de los menús locales. Los favoritos, el menú de usuario y las asociaciones no se tocan."
	)
	if not f_comun.preguntar(ctx.ventana, texto, _("Restablecer los valores de fábrica"), peligroso=True):
		return
	asistente_hecho = bool(ctx.config.obtener("general.asistente_hecho"))
	try:
		with ctx.config.lote():
			ctx.config.restablecer()
			# El asistente ya se vio: restablecer no debe volver a lanzarlo en el próximo arranque.
			ctx.config.establecer("general.asistente_hecho", asistente_hecho)
	except Exception as error:  # noqa: BLE001 - ErrorConfiguracion u OSError: se dice a la persona
		log.exception("No se pudieron restablecer los valores de fábrica")
		f_comun.avisar(ctx.ventana, _("No se pudieron restablecer los valores de fábrica: {e}").format(e=error), _("Valores de fábrica"))
		return
	anuncios.anunciar(_("Valores de fábrica restablecidos"), anuncios.RESULTADO)
