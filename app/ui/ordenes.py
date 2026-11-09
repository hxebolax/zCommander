# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Catálogo de órdenes: la ÚNICA lista de lo que zCommander sabe hacer.

De aquí salen la barra de menús, el menú contextual, la barra de teclas, el
mapa de teclas, la paleta de órdenes, el modo de ayuda de teclado, la lista de
teclas del manual (``tools/generar_anexos.py``) y las pruebas que comprueban
que cada orden tiene manejador y que no hay teclas repetidas.

Cada orden:

- ``id``: identificador estable (se guarda en la configuración si se cambia su tecla).
- ``etiqueta``: texto del menú con ``&``.
- ``ayuda``: una frase para la barra de estado, Ctrl+H, la paleta y el manual.
- ``teclas``: atajos de fábrica en formato canónico (``app.services.teclas``).
- ``ambito``: dónde funciona la tecla: ``panel`` (foco en un panel), ``global``
  (en cualquier control de la ventana principal) o ``linea`` (en la línea de órdenes).
- ``manejador``: ``modulo.funcion`` dentro de ``app.ui.acciones``; la función
  recibe un ``ContextoOrden``.
- ``bloque``: quién la programa (ver ``docs/diseno.md``, plan de trabajo).
- ``tipo``: ``normal`` o ``casilla`` (con ``estado``: ``modulo.funcion`` de
  ``app.ui.acciones`` que recibe el ``ContextoOrden`` y devuelve ``bool``).
- ``por_lado``: aparece en los menús Izquierdo y Derecho y actúa sobre ese lado.
- ``fija``: su tecla no se puede cambiar (Tab, Ctrl+H, menú contextual).
- ``param``: argumento fijo que recibe el manejador (``ctx.param``), para
  órdenes que comparten función (ordenar por..., leer columna N...).
"""

from __future__ import annotations

import builtins
import dataclasses
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace, dataclass
from typing import Any

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	"""Marca para traducir más tarde (los descriptores se crean al importar)."""
	return texto


PANEL, GLOBAL, LINEA = "panel", "global", "linea"


@dataclass(frozen=True)
class Orden:
	id: str
	etiqueta: str
	ayuda: str
	teclas: tuple[str, ...] = ()
	ambito: str = PANEL
	manejador: str = ""
	bloque: str = "N"
	tipo: str = "normal"
	estado: str = ""
	por_lado: bool = False
	fija: bool = False
	param: str = ""
	# 2.0 (14.1.1): nivel del perfil (10.11), si sirve como tecla global (10.15) y si se graba en las macros (10.1).
	nivel: str = "novato"
	tecla_global: bool = False
	grabable: bool = True


def _o(id_, etiqueta, ayuda, teclas=(), ambito=PANEL, manejador="", bloque="N", **resto) -> Orden:
	return Orden(id_, etiqueta, ayuda, tuple(teclas), ambito, manejador, bloque, **resto)


_ORDENES: list[Orden] = [
	# ── Navegación ───────────────────────────────────────────────────────────
	_o("abrir", N_("&Abrir"), N_("Entra en la carpeta o el comprimido, o abre el archivo con su programa."), ["Return"], PANEL, "navegacion.abrir"),
	_o("subir", N_("Carpeta &superior"), N_("Va a la carpeta que contiene la actual."), ["Back", "Ctrl+PgUp", "Alt+Up"], PANEL, "navegacion.subir"),
	_o("entrar", N_("&Entrar"), N_("Entra en la carpeta o el comprimido del cursor."), ["Ctrl+PgDn"], PANEL, "navegacion.entrar"),
	_o("raiz", N_("&Raíz de la unidad"), N_("Va a la carpeta raíz de la unidad actual."), ["Ctrl+Back"], PANEL, "navegacion.raiz"),
	_o("carpeta_personal", N_("Carpeta &personal"), N_("Va a su carpeta de usuario."), ["Ctrl+Shift+Home"], PANEL, "navegacion.carpeta_personal"),
	_o("atras", N_("A&trás"), N_("Vuelve a la carpeta anterior del historial del panel."), ["Alt+Left"], PANEL, "navegacion.atras"),
	_o("adelante", N_("Adela&nte"), N_("Avanza a la carpeta siguiente del historial del panel."), ["Alt+Right"], PANEL, "navegacion.adelante"),
	_o("ir_a_carpeta", N_("&Ir a la carpeta..."), N_("Escriba una ruta, una dirección ftp:// o sftp:// o una variable como %USERPROFILE%."), ["Ctrl+G"], GLOBAL, "navegacion.ir_a_carpeta"),
	_o("cambiar_panel", N_("Cambiar de panel"), N_("Pasa al otro panel."), ["Tab", "Shift+Tab"], PANEL, "navegacion.cambiar_panel", fija=True),
	_o("intercambiar_paneles", N_("&Intercambiar paneles"), N_("Intercambia el contenido de los paneles izquierdo y derecho."), ["Ctrl+U"], GLOBAL, "navegacion.intercambiar_paneles"),
	_o("igualar_paneles", N_("I&gualar paneles"), N_("Lleva el otro panel a la misma carpeta que el activo."), ["Alt+Z"], GLOBAL, "navegacion.igualar_paneles"),
	_o("abrir_en_izquierdo", N_("Abrir en el lado i&zquierdo"), N_("Abre en el lado izquierdo la carpeta del cursor, o la actual."), ["Ctrl+Left"], PANEL, "navegacion.abrir_en_lado", param="izquierdo"),
	_o("abrir_en_derecho", N_("Abrir en el lado &derecho"), N_("Abre en el lado derecho la carpeta del cursor, o la actual."), ["Ctrl+Right"], PANEL, "navegacion.abrir_en_lado", param="derecho"),
	_o("volver_a_leer", N_("Volver a l&eer"), N_("Vuelve a leer la carpeta conservando cursor y marcas."), ["Ctrl+R"], GLOBAL, "navegacion.volver_a_leer", por_lado=True),
	_o("cancelar", N_("Cancelar o quitar"), N_("Cancela la lectura o el cálculo en curso del panel o quita el filtro rápido, en ese orden; si no hay nada, detiene la orden lanzada desde la línea de órdenes."), ["Escape"], PANEL, "navegacion.cancelar"),
	_o("abrir_menus", N_("Abrir la barra de menús"), N_("Abre la barra de menús, como en Norton Commander (Alt también la abre)."), ["F9"], GLOBAL, "navegacion.abrir_menus", fija=True),
	_o("ir_linea_ordenes",N_("Ir a la línea de órdenes"), N_("Muestra la línea de órdenes y pone el foco en ella. Con búsqueda rápida activa, le pasa lo tecleado."), ["Shift+F2"], GLOBAL, "navegacion.ir_linea_ordenes"),
	_o("historial_carpetas", N_("Historial de &carpetas..."), N_("Lista de carpetas visitadas en este panel."), ["Alt+F12", "Alt+Down"], PANEL, "dialogos_f.historial_carpetas", "F"),
	_o("favoritos", N_("&Favoritos..."), N_("Carpetas favoritas: ir, añadir, renombrar, ordenar y borrar."), ["Ctrl+D"], GLOBAL, "dialogos_f.favoritos", "F"),
	_o("agregar_favorito", N_("&Añadir a favoritos..."), N_("Añade la carpeta actual a favoritos."), ["Ctrl+Shift+D"], GLOBAL, "dialogos_f.agregar_favorito", "F"),
	_o("unidad_izquierda", N_("Unidad del lado izquierdo..."), N_("Elige unidad o carpeta especial para el lado izquierdo."), ["Alt+F1"], GLOBAL, "dialogos_f.unidad", "F", param="izquierdo"),
	_o("unidad_derecha", N_("Unidad del lado derecho..."), N_("Elige unidad o carpeta especial para el lado derecho."), ["Alt+F2"], GLOBAL, "dialogos_f.unidad", "F", param="derecho"),
	_o("unidad", N_("Unida&d..."), N_("Elige unidad o carpeta especial para este lado."), [], GLOBAL, "dialogos_f.unidad", "F", por_lado=True),
	_o("arbol_carpetas", N_("Árbo&l de carpetas..."), N_("Elige una carpeta en un árbol de la unidad."), ["Alt+F10"], GLOBAL, "dialogos_f.arbol_carpetas", "F"),

	# ── Vista y paneles ──────────────────────────────────────────────────────
	_o("vista_completa", N_("Vista &completa"), N_("Muestra todas las columnas elegidas."), [], GLOBAL, "vista.vista", por_lado=True, tipo="casilla", estado="vista.es_vista", param="completa"),
	_o("vista_breve", N_("Vista &breve"), N_("Muestra solo los nombres."), [], GLOBAL, "vista.vista", por_lado=True, tipo="casilla", estado="vista.es_vista", param="breve"),
	_o("vista_informacion", N_("&Información"), N_("Muestra en este lado la información del elemento del otro panel."), ["Ctrl+L"], GLOBAL, "vista.vista", por_lado=True, tipo="casilla", estado="vista.es_vista", param="informacion"),
	_o("vista_arbol", N_("Árb&ol"), N_("Muestra en este lado el árbol de carpetas; el otro panel sigue la carpeta elegida."), [], GLOBAL, "vista.vista", por_lado=True, tipo="casilla", estado="vista.es_vista", param="arbol"),
	_o("vista_rapida", N_("Vista &rápida"), N_("Muestra en este lado el contenido del archivo del cursor del otro panel."), ["Ctrl+Q"], GLOBAL, "vista.vista", por_lado=True, tipo="casilla", estado="vista.es_vista", param="rapida"),
	_o("ordenar_nombre", N_("Ordenar por &nombre"), N_("Ordena por nombre; otra vez invierte el orden."), ["Ctrl+F3"], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="nombre"),
	_o("ordenar_extension", N_("Ordenar por e&xtensión"), N_("Ordena por extensión; otra vez invierte el orden."), ["Ctrl+F4"], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="extension"),
	_o("ordenar_fecha", N_("Ordenar por &fecha"), N_("Ordena por fecha de modificación; otra vez invierte el orden."), ["Ctrl+F5"], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="fecha"),
	_o("ordenar_tamano", N_("Ordenar por &tamaño"), N_("Ordena por tamaño; otra vez invierte el orden."), ["Ctrl+F6"], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="tamano"),
	_o("ordenar_tipo", N_("Ordenar por ti&po"), N_("Ordena por tipo de archivo."), [], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="tipo"),
	_o("sin_ordenar", N_("&Sin ordenar"), N_("Muestra los elementos en el orden del disco."), ["Ctrl+F7"], GLOBAL, "vista.ordenar", por_lado=True, tipo="casilla", estado="vista.es_orden", param="sin_orden"),
	_o("orden_inverso", N_("Orden in&verso"), N_("Invierte el orden actual."), [], GLOBAL, "vista.orden_inverso", por_lado=True, tipo="casilla", estado="vista.es_inverso"),
	_o("carpetas_primero", N_("A&grupar las carpetas al principio"), N_("Muestra las carpetas antes que los archivos."), [], GLOBAL, "vista.carpetas_primero", por_lado=True, tipo="casilla", estado="vista.es_carpetas_primero"),
	_o("filtro", N_("Fi&ltro..."), N_("Elige qué archivos se muestran con un patrón (*.mp3;*.flac)."), ["Ctrl+F12"], GLOBAL, "vista.filtro", por_lado=True),
	_o("filtro_rapido", N_("Filtro r&ápido"), N_("Escriba para quedarse solo con los elementos que contienen el texto. Escape lo quita."), ["Ctrl+F"], PANEL, "vista.filtro_rapido"),
	_o("quitar_filtro", N_("&Quitar el filtro"), N_("Vuelve a mostrar todos los elementos."), [], GLOBAL, "vista.quitar_filtro", por_lado=True),
	_o("mostrar_ocultos", N_("Mostrar archivos &ocultos y de sistema"), N_("Muestra u oculta los archivos ocultos y de sistema."), ["Ctrl+."], GLOBAL, "vista.mostrar_ocultos", tipo="casilla", estado="vista.es_mostrar_ocultos"),
	_o("busqueda_rapida", N_("Búsqueda rápi&da"), N_("Escriba el principio de un nombre para llevar el cursor a él."), ["Ctrl+S"], PANEL, "vista.busqueda_rapida"),
	_o("mostrar_lado", N_("&Mostrar u ocultar este lado"), N_("Oculta o muestra este lado de la ventana."), [], GLOBAL, "vista.mostrar_lado", por_lado=True),
	_o("mostrar_izquierdo", N_("Mostrar u ocultar el lado izquierdo"), N_("Oculta o muestra el lado izquierdo."), ["Ctrl+F1"], GLOBAL, "vista.mostrar_lado", param="izquierdo"),
	_o("mostrar_derecho", N_("Mostrar u ocultar el lado derecho"), N_("Oculta o muestra el lado derecho."), ["Ctrl+F2"], GLOBAL, "vista.mostrar_lado", param="derecho"),
	_o("mostrar_paneles", N_("Mostrar u ocultar los &paneles"), N_("Oculta los dos paneles y muestra la salida de las órdenes, o al revés."), ["Ctrl+O"], GLOBAL, "vista.mostrar_paneles"),
	_o("panel_pasivo", N_("Mostrar u ocultar el panel pa&sivo"), N_("Oculta o muestra el panel que no tiene el foco."), ["Ctrl+P"], GLOBAL, "vista.panel_pasivo"),
	_o("pestana_nueva", N_("Pestaña &nueva"), N_("Abre una pestaña con la misma carpeta."), ["Ctrl+T"], GLOBAL, "vista.pestana_nueva", por_lado=True),
	_o("pestana_cerrar", N_("&Cerrar pestaña"), N_("Cierra la pestaña actual (la última no se cierra)."), ["Ctrl+W"], GLOBAL, "vista.pestana_cerrar", por_lado=True),
	_o("pestana_cerrar_otras", N_("Cerrar las &demás pestañas"), N_("Cierra todas las pestañas de este lado salvo la actual."), [], GLOBAL, "vista.pestana_cerrar_otras", por_lado=True),
	_o("pestana_siguiente", N_("Pestaña si&guiente"), N_("Pasa a la pestaña siguiente del lado activo."), ["Ctrl+Tab"], GLOBAL, "vista.pestana_mover", por_lado=True, param="1"),
	_o("pestana_anterior", N_("Pestaña an&terior"), N_("Pasa a la pestaña anterior del lado activo."), ["Ctrl+Shift+Tab"], GLOBAL, "vista.pestana_mover", por_lado=True, param="-1"),
	_o("pestana_bloquear", N_("&Bloquear o desbloquear la pestaña"), N_("Una pestaña bloqueada no cambia de carpeta: al entrar en otra se abre una pestaña nueva."), [], GLOBAL, "vista.pestana_bloquear", por_lado=True, tipo="casilla", estado="vista.es_pestana_bloqueada"),
	_o("lista_pestanas", N_("&Lista de pestañas..."), N_("Elige una pestaña de este lado en una lista."), [], GLOBAL, "vista.lista_pestanas", por_lado=True),
	*[
		_o(f"pestana_{n}", N_("Pestaña {n}").replace("{n}", str(n)), N_("Va a la pestaña con ese número."), [f"Alt+{n}"], GLOBAL, "vista.pestana_numero", param=str(n))
		for n in range(1, 10)
	],
	_o("columnas", N_("Col&umnas..."), N_("Elige qué columnas se ven en este lado, su orden y su ancho."), [], GLOBAL, "dialogos_f.columnas", "F", por_lado=True),

	# ── Archivos ─────────────────────────────────────────────────────────────
	_o("menu_usuario", N_("Menú de &usuario..."), N_("Órdenes propias definidas en Opciones, Editar el menú de usuario."), ["F2"], GLOBAL, "dialogos_f.menu_usuario", "F"),
	_o("ver", N_("&Ver"), N_("Abre el archivo en el visor."), ["F3"], GLOBAL, "visor.ver", "A"),
	_o("ver_externo", N_("Ver con el visor e&xterno"), N_("Abre el archivo con el visor externo configurado."), ["Alt+F3"], GLOBAL, "visor.ver_externo", "A"),
	_o("editar", N_("&Editar"), N_("Abre el archivo en el editor."), ["F4"], GLOBAL, "visor.editar", "A"),
	_o("crear_archivo", N_("Crear archivo &nuevo..."), N_("Pide un nombre, crea el archivo vacío y lo abre en el editor."), ["Shift+F4"], GLOBAL, "visor.crear_archivo", "A"),
	_o("copiar", N_("&Copiar..."), N_("Copia los elementos de trabajo al otro panel."), ["F5"], GLOBAL, "archivos.copiar"),
	_o("mover", N_("&Renombrar o mover..."), N_("Mueve los elementos de trabajo al otro panel, o los renombra."), ["F6"], GLOBAL, "archivos.mover"),
	_o("crear_carpeta", N_("Crear car&peta..."), N_("Crea una carpeta en el panel activo."), ["F7"], GLOBAL, "archivos.crear_carpeta"),
	_o("eliminar", N_("E&liminar..."), N_("Envía los elementos de trabajo a la papelera."), ["F8", "Delete"], GLOBAL, "archivos.eliminar"),
	_o("eliminar_definitivo", N_("Eliminar &definitivamente..."), N_("Elimina sin pasar por la papelera."), ["Shift+F8", "Shift+Delete"], GLOBAL, "archivos.eliminar_definitivo"),
	_o("duplicar", N_("Copiar a&quí con otro nombre..."), N_("Copia el elemento en la misma carpeta con otro nombre."), ["Shift+F5"], GLOBAL, "archivos.duplicar"),
	_o("renombrar", N_("Renombrar en el s&itio..."), N_("Cambia el nombre del elemento del cursor."), ["Shift+F6"], GLOBAL, "archivos.renombrar"),
	_o("atributos", N_("Atri&butos y fechas..."), N_("Cambia atributos y fechas de los elementos de trabajo."), [], GLOBAL, "edicion_e.atributos", "E"),
	_o("propiedades", N_("Pr&opiedades"), N_("Abre las propiedades de Windows."), ["Alt+Return"], GLOBAL, "windows_g.propiedades", "G"),
	_o("crear_enlace", N_("Crear en&lace..."), N_("Crea un enlace simbólico, una unión, un enlace duro o un acceso directo."), [], GLOBAL, "edicion_e.crear_enlace", "E"),
	_o("abrir_con", N_("Abrir con otro pro&grama..."), N_("Elige el programa con el que abrir el archivo."), [], GLOBAL, "windows_g.abrir_con", "G"),
	_o("menu_windows", N_("Menú contextual de &Windows"), N_("Abre el menú contextual del Explorador para los elementos de trabajo."), ["Ctrl+Menu", "Alt+Shift+F10"], PANEL, "windows_g.menu_windows", "G"),
	_o("menu_contextual", N_("Menú contextual"), N_("Abre el menú contextual de zCommander."), ["Shift+F10", "Menu"], PANEL, "archivos.menu_contextual", fija=True),
	_o("salir", N_("&Salir"), N_("Cierra zCommander."), ["F10", "Alt+X"], GLOBAL, "archivos.salir"),

	# ── Marcas ───────────────────────────────────────────────────────────────
	_o("marcar", N_("Marcar y bajar"), N_("Marca o desmarca el elemento del cursor y baja al siguiente."), ["Insert", "Space"], PANEL, "marcas.marcar"),
	_o("marcar_sin_mover", N_("Marcar sin mover"), N_("Marca o desmarca el elemento del cursor sin moverse."), ["Ctrl+Space"], PANEL, "marcas.marcar_sin_mover"),
	_o("marcar_subir", N_("Extender la marca hacia arriba"), N_("Marca el elemento del cursor y sube."), ["Shift+Up"], PANEL, "marcas.marcar_rango", param="-1"),
	_o("marcar_bajar", N_("Extender la marca hacia abajo"), N_("Marca el elemento del cursor y baja."), ["Shift+Down"], PANEL, "marcas.marcar_rango", param="1"),
	_o("marcar_pagina_arriba", N_("Marcar una página hacia arriba"), N_("Marca desde el cursor una página hacia arriba."), ["Shift+PgUp"], PANEL, "marcas.marcar_rango", param="-pagina"),
	_o("marcar_pagina_abajo", N_("Marcar una página hacia abajo"), N_("Marca desde el cursor una página hacia abajo."), ["Shift+PgDn"], PANEL, "marcas.marcar_rango", param="pagina"),
	_o("marcar_hasta_inicio", N_("Marcar hasta el principio"), N_("Marca desde el cursor hasta el primer elemento."), ["Shift+Home"], PANEL, "marcas.marcar_rango", param="inicio"),
	_o("marcar_hasta_fin", N_("Marcar hasta el final"), N_("Marca desde el cursor hasta el último elemento."), ["Shift+End"], PANEL, "marcas.marcar_rango", param="fin"),
	_o("marcar_patron", N_("&Marcar por patrón..."), N_("Marca los elementos que coinciden con un patrón (*.txt;*.md, exclusiones con |)."), ["KP_ADD", "Ctrl+Shift+M"], PANEL, "marcas.marcar_patron"),
	_o("desmarcar_patron", N_("&Desmarcar por patrón..."), N_("Desmarca los elementos que coinciden con un patrón."), ["KP_SUBTRACT", "Ctrl+Shift+Q"], PANEL, "marcas.desmarcar_patron"),
	_o("invertir_marcas", N_("&Invertir las marcas"), N_("Marca lo no marcado y desmarca lo marcado (solo archivos)."), ["KP_MULTIPLY", "Ctrl+Shift+N"], PANEL, "marcas.invertir"),
	_o("marcar_todo", N_("Marcar &todo"), N_("Marca todos los elementos visibles."), ["Ctrl+A"], PANEL, "marcas.marcar_todo"),
	_o("desmarcar_todo", N_("D&esmarcar todo"), N_("Quita todas las marcas."), ["Ctrl+Shift+A"], PANEL, "marcas.desmarcar_todo"),
	_o("marcar_extension", N_("Marcar la misma e&xtensión"), N_("Marca todos los archivos con la extensión del cursor."), ["Shift+KP_ADD"], PANEL, "marcas.extension", param="marcar"),
	_o("desmarcar_extension", N_("Desmarcar la misma extensió&n"), N_("Desmarca todos los archivos con la extensión del cursor."), ["Shift+KP_SUBTRACT"], PANEL, "marcas.extension", param="desmarcar"),
	_o("restaurar_marcas", N_("&Restaurar las marcas"), N_("Vuelve a marcar lo que estaba marcado antes de la última operación."), ["Ctrl+Shift+R"], PANEL, "marcas.restaurar"),
	_o("guardar_marcas", N_("&Guardar las marcas en un archivo..."), N_("Guarda los nombres marcados en un archivo de texto."), [], PANEL, "marcas.guardar"),
	_o("cargar_marcas", N_("&Cargar las marcas desde un archivo..."), N_("Marca los nombres que aparecen en un archivo de texto."), [], PANEL, "marcas.cargar"),

	# ── Portapapeles ─────────────────────────────────────────────────────────
	_o("portapapeles_copiar", N_("&Copiar al portapapeles"), N_("Copia los elementos de trabajo al portapapeles (compatible con el Explorador)."), ["Ctrl+C"], PANEL, "windows_g.portapapeles_copiar", "G"),
	_o("portapapeles_cortar", N_("Cor&tar"), N_("Corta los elementos de trabajo para pegarlos en otro sitio."), ["Ctrl+X"], PANEL, "windows_g.portapapeles_cortar", "G"),
	_o("portapapeles_pegar", N_("&Pegar"), N_("Pega en la carpeta del panel activo los archivos del portapapeles."), ["Ctrl+V"], PANEL, "windows_g.portapapeles_pegar", "G"),
	_o("copiar_rutas", N_("Copiar las &rutas completas"), N_("Copia como texto las rutas completas de los elementos de trabajo."), ["Ctrl+Shift+C"], PANEL, "archivos.copiar_rutas"),
	_o("copiar_nombres", N_("Copiar los &nombres"), N_("Copia como texto los nombres de los elementos de trabajo."), [], PANEL, "archivos.copiar_nombres"),
	_o("copiar_ruta_carpeta", N_("Copiar l&a ruta de la carpeta"), N_("Copia como texto la ruta de la carpeta del panel activo."), [], PANEL, "archivos.copiar_ruta_carpeta"),

	# ── Línea de órdenes ─────────────────────────────────────────────────────
	_o("insertar_nombre", N_("Añadir el nombre a la línea de órdenes"), N_("Escribe el nombre del cursor en la línea de órdenes."), ["Ctrl+Return"], PANEL, "linea.insertar_nombre"),
	_o("insertar_ruta", N_("Añadir la ruta completa a la línea de órdenes"), N_("Escribe la ruta completa del cursor en la línea de órdenes."), ["Ctrl+Shift+Return"], PANEL, "linea.insertar_ruta"),
	_o("ejecutar_linea", N_("Ejecutar la orden"), N_("Ejecuta la orden escrita en la carpeta del panel activo."), ["Return"], LINEA, "linea.ejecutar"),
	_o("ejecutar_en_consola", N_("Ejecutar en una consola"), N_("Ejecuta la orden en una consola nueva que queda abierta."), ["Ctrl+Return"], LINEA, "linea.ejecutar_en_consola"),
	_o("linea_anterior", N_("Orden anterior"), N_("Recupera la orden anterior del historial."), ["Up"], LINEA, "linea.historial_mover", param="-1"),
	_o("linea_siguiente", N_("Orden siguiente"), N_("Recupera la orden siguiente del historial."), ["Down"], LINEA, "linea.historial_mover", param="1"),
	_o("linea_vaciar", N_("Vaciar la línea de órdenes"), N_("Borra lo escrito; si ya está vacía, detiene la orden en curso o, si no hay ninguna, vuelve al panel."), ["Escape"], LINEA, "linea.vaciar"),
	_o("linea_al_panel", N_("Volver al panel"), N_("Devuelve el foco al panel activo."), ["Tab", "Shift+Tab"], LINEA, "linea.al_panel", fija=True),
	_o("historial_ordenes", N_("Historial de ó&rdenes..."), N_("Lista de las órdenes ejecutadas, con búsqueda."), ["Alt+F8"], GLOBAL, "dialogos_f.historial_ordenes", "F"),

	# ── Herramientas ─────────────────────────────────────────────────────────
	_o("buscar_archivos", N_("&Buscar archivos..."), N_("Busca por nombre, contenido, tamaño, fecha y atributos."), ["Alt+F7"], GLOBAL, "busqueda_b.buscar_archivos", "B"),
	_o("vista_plana", N_("Vista &plana"), N_("Muestra en una lista todos los archivos de la carpeta y sus subcarpetas."), ["Ctrl+B"], GLOBAL, "busqueda_b.vista_plana", "B", tipo="casilla", estado="busqueda_b.es_vista_plana"),
	_o("comparar_carpetas", N_("C&omparar carpetas..."), N_("Marca en cada panel lo que falta en el otro o es más reciente."), ["Ctrl+F10"], GLOBAL, "busqueda_b.comparar_carpetas", "B"),
	_o("sincronizar_carpetas", N_("&Sincronizar carpetas..."), N_("Compara las carpetas de los dos paneles y copia o elimina para igualarlas."), ["Ctrl+Shift+F10"], GLOBAL, "busqueda_b.sincronizar", "B"),
	_o("tamano_carpetas", N_("Calcular el &tamaño"), N_("Calcula y anuncia el tamaño de las carpetas de trabajo."), ["Shift+Space"], PANEL, "busqueda_b.tamano", "B", param="trabajo"),
	_o("tamano_todas", N_("Calcular el tamaño de t&odas las carpetas"), N_("Calcula el tamaño de todas las carpetas del panel."), ["Alt+Shift+Return"], GLOBAL, "busqueda_b.tamano", "B", param="todas"),
	_o("cesta_agregar", N_("Añadir a la &cesta"), N_("Guarda los elementos de trabajo en la cesta, para operar después con archivos de varias carpetas."), ["Ctrl+Shift+B"], PANEL, "busqueda_b.cesta_agregar", "B"),
	_o("cesta_abrir", N_("Abrir la ce&sta"), N_("Muestra la cesta como una lista en el panel activo."), [], GLOBAL, "busqueda_b.cesta_abrir", "B"),
	_o("cesta_vaciar", N_("Vaciar la cest&a"), N_("Quita todos los elementos de la cesta."), [], GLOBAL, "busqueda_b.cesta_vaciar", "B"),
	_o("comparar_archivos", N_("Comparar archivos por con&tenido..."), N_("Compara el archivo del cursor de cada panel, o los dos marcados."), [], GLOBAL, "visor.comparar_archivos", "A"),
	_o("renombrado_multiple", N_("Renombrado &múltiple..."), N_("Renombra muchos archivos con máscaras, contador, buscar y reemplazar."), ["Ctrl+M"], GLOBAL, "edicion_e.renombrado_multiple", "E"),
	_o("sumas_crear", N_("Crear sumas de &comprobación..."), N_("Calcula CRC32, MD5, SHA-1, SHA-256, SHA-512 o BLAKE2 y las guarda."), [], GLOBAL, "comprimidos_c.sumas_crear", "C"),
	_o("sumas_verificar", N_("&Verificar sumas de comprobación..."), N_("Comprueba los archivos con un archivo de sumas."), [], GLOBAL, "comprimidos_c.sumas_verificar", "C"),
	_o("dividir", N_("&Dividir archivo..."), N_("Divide un archivo en partes de un tamaño dado."), [], GLOBAL, "comprimidos_c.dividir", "C"),
	_o("unir", N_("U&nir archivos..."), N_("Une las partes .001, .002... en el archivo original."), [], GLOBAL, "comprimidos_c.unir", "C"),
	_o("comprimir", N_("Compri&mir..."), N_("Crea un comprimido ZIP, 7z o TAR con los elementos de trabajo."), ["Alt+F5"], GLOBAL, "comprimidos_c.comprimir", "C"),
	_o("extraer", N_("E&xtraer..."), N_("Extrae los comprimidos de trabajo al otro panel."), ["Alt+F6", "Alt+F9"], GLOBAL, "comprimidos_c.extraer", "C"),
	_o("probar_comprimido", N_("&Probar comprimido"), N_("Comprueba que el comprimido no está dañado."), ["Alt+Shift+F9"], GLOBAL, "comprimidos_c.probar", "C"),
	_o("conexiones", N_("Conexiones &FTP y SFTP..."), N_("Gestor de sitios FTP, FTPS y SFTP."), ["Ctrl+K"], GLOBAL, "red_d.conexiones", "D"),
	_o("desconectar", N_("Desco&nectar"), N_("Cierra la conexión del panel activo y vuelve al disco local."), [], GLOBAL, "red_d.desconectar", "D"),
	_o("conectar_unidad_red", N_("Conectar unidad de r&ed..."), N_("Asigna una letra de unidad a un recurso compartido."), [], GLOBAL, "red_d.conectar_unidad", "D"),
	_o("desconectar_unidad_red", N_("Desconectar unidad de re&d..."), N_("Quita una unidad de red asignada."), [], GLOBAL, "red_d.desconectar_unidad", "D"),
	_o("consola", N_("Abrir consola a&quí"), N_("Abre la consola configurada en la carpeta del panel activo."), ["F11"], GLOBAL, "windows_g.consola", "G"),
	_o("explorador", N_("Abrir en el E&xplorador"), N_("Abre la carpeta actual en el Explorador de Windows."), ["Shift+F3"], GLOBAL, "windows_g.explorador", "G"),
	_o("operaciones", N_("Operaciones en c&urso..."), N_("Ventana con las copias, movimientos y demás operaciones, y las decisiones pendientes."), ["F12"], GLOBAL, "archivos.operaciones"),
	_o("deshacer", N_("Des&hacer"), N_("Deshace la última operación que lo admite (renombrar, mover, crear carpeta, copiar)."), ["Ctrl+Z"], PANEL, "archivos.deshacer"),
	_o("paleta_ordenes", N_("&Paleta de órdenes..."), N_("Escriba lo que quiere hacer y elija la orden; se anuncia su atajo para aprenderlo."), ["Ctrl+E"], GLOBAL, "dialogos_f.paleta_ordenes", "F"),
	_o("ayuda_teclado", N_("Modo de a&yuda de teclado"), N_("Mientras está activo, cada tecla dice qué haría sin hacerlo. Escape sale."), ["Shift+F12"], GLOBAL, "dialogos_f.ayuda_teclado", "F"),

	# ── Opciones ─────────────────────────────────────────────────────────────
	_o("preferencias", N_("&Preferencias..."), N_("Todas las opciones de zCommander."), ["Ctrl+,"], GLOBAL, "dialogos_f.preferencias", "F"),
	_o("perfil", N_("Perf&il de usuario..."), N_("Aplica los valores pensados para personas novatas, intermedias o avanzadas."), [], GLOBAL, "dialogos_f.perfil", "F"),
	_o("mapa_teclas", N_("Mapa de &teclas..."), N_("Cambia las teclas de cada orden."), [], GLOBAL, "dialogos_f.mapa_teclas", "F"),
	_o("columnas_defecto", N_("&Columnas por defecto..."), N_("Columnas de los paneles nuevos."), [], GLOBAL, "dialogos_f.columnas_defecto", "F"),
	_o("editar_menu_usuario", N_("Editar el menú de &usuario..."), N_("Crea y cambia las entradas del menú de usuario (F2)."), [], GLOBAL, "dialogos_f.editar_menu_usuario", "F"),
	_o("editar_asociaciones", N_("Editar las &asociaciones..."), N_("Qué programa abre, ve o edita cada tipo de archivo."), [], GLOBAL, "dialogos_f.editar_asociaciones", "F"),
	_o("asistente", N_("Asistente de primer arra&nque..."), N_("Vuelve a elegir perfil, lector de pantalla y tema."), [], GLOBAL, "dialogos_f.asistente", "F"),
	_o("guardar_sesion", N_("&Guardar la sesión ahora"), N_("Guarda carpetas, pestañas y configuración."), ["Shift+F9"], GLOBAL, "archivos.guardar_sesion"),
	_o("restablecer_fabrica", N_("&Restablecer los valores de fábrica..."), N_("Vuelve a las preferencias de fábrica (pide confirmación)."), [], GLOBAL, "dialogos_f.restablecer_fabrica", "F"),
	_o("carpeta_datos", N_("Abrir la carpeta de &datos"), N_("Abre en el Explorador la carpeta data de zCommander."), [], GLOBAL, "ayuda.carpeta_datos"),
	_o("carpeta_registros", N_("Abrir la carpeta de regis&tros"), N_("Abre en el Explorador la carpeta de registros."), [], GLOBAL, "ayuda.carpeta_registros"),

	# ── Ayuda ────────────────────────────────────────────────────────────────
	_o("manual", N_("&Manual de usuario"), N_("Abre el manual."), ["F1"], GLOBAL, "ayuda.manual"),
	_o("lista_teclas", N_("&Lista de teclas"), N_("Muestra todas las teclas de zCommander."), ["Shift+F1"], GLOBAL, "ayuda.lista_teclas"),
	_o("novedades", N_("&Novedades de la versión"), N_("Muestra los cambios de cada versión."), [], GLOBAL, "ayuda.novedades"),
	_o("ayuda_contextual", N_("Ayuda del control &enfocado"), N_("Explica para qué sirve el control que tiene el foco."), ["Ctrl+H"], GLOBAL, "ayuda.ayuda_contextual", fija=True),
	_o("info_soporte", N_("&Información para soporte"), N_("Copia al portapapeles la versión, el sistema y las últimas líneas del registro."), [], GLOBAL, "ayuda.info_soporte"),
	_o("acerca_de", N_("&Acerca de zCommander..."), N_("Versión y datos técnicos."), [], GLOBAL, "ayuda.acerca_de"),

	# ── Consulta para lector de pantalla ─────────────────────────────────────
	_o("decir_ruta", N_("Decir la ruta del panel activo"), N_("Anuncia la carpeta del panel activo."), ["Ctrl+Shift+P"], GLOBAL, "consulta.decir_ruta", param="activo"),
	_o("decir_ruta_otro", N_("Decir la ruta del otro panel"), N_("Anuncia la carpeta del otro panel."), ["Ctrl+Shift+O"], GLOBAL, "consulta.decir_ruta", param="pasivo"),
	_o("decir_resumen", N_("Decir el resumen de la carpeta"), N_("Carpetas, archivos, tamaño, marcas y filtro del panel activo."), ["Ctrl+Shift+S"], GLOBAL, "consulta.decir_resumen"),
	_o("decir_info", N_("Decir la información del elemento"), N_("Tipo, tamaño, fechas y atributos del elemento del cursor."), ["Ctrl+Shift+I"], GLOBAL, "consulta.decir_info"),
	_o("decir_espacio", N_("Decir el espacio libre"), N_("Espacio libre y total de la unidad del panel activo."), ["Ctrl+Shift+E"], GLOBAL, "consulta.decir_espacio"),
	_o("decir_operaciones", N_("Decir el estado de las operaciones"), N_("Porcentaje, velocidad, tiempo restante y decisiones pendientes."), ["Ctrl+Shift+T"], GLOBAL, "consulta.decir_operaciones"),
	_o("repetir_anuncio", N_("Repetir el último anuncio"), N_("Repite el último anuncio; pulsado dos veces seguidas, dice su versión completa."), ["Ctrl+Shift+U"], GLOBAL, "consulta.repetir_anuncio"),
	_o("historial_anuncios", N_("&Historial de anuncios..."), N_("Lista de los anuncios de la sesión, con hora; se puede copiar."), ["Ctrl+Shift+H"], GLOBAL, "consulta.historial_anuncios"),
	*[
		_o(f"leer_columna_{n}", N_("Leer la columna {n}").replace("{n}", str(n)), N_("Lee esa columna de la fila del cursor sin moverse."), [f"Ctrl+{n % 10}"], PANEL, "consulta.leer_columna", param=str(n))
		for n in range(1, 11)
	],
	_o("columna_anterior", N_("Leer la columna anterior"), N_("Lee la columna anterior de la fila del cursor."), ["Left"], PANEL, "consulta.mover_columna", param="-1"),
	_o("columna_siguiente", N_("Leer la columna siguiente"), N_("Lee la columna siguiente de la fila del cursor."), ["Right"], PANEL, "consulta.mover_columna", param="1"),
]

# ── Órdenes nuevas del núcleo 2.0 (diseño 2.0, 14.1.2) ─────────────────────────
# Manejador en el módulo de acciones del bloque dueño (provisional hasta que ese
# bloque lo programe); los de casilla, con su función de estado.
_ORDENES_2: list[Orden] = [
	_o("complementos", N_("Gestor de comp&lementos..."), N_("Lista de complementos: habilitar, configurar, actualizar e instalar."), [], GLOBAL, "complementos_pl.complementos", "PL", nivel="intermedio"),
	_o("complemento_instalar", N_("&Instalar un complemento desde un archivo..."), N_("Instala un complemento .zcplugin tras mostrar su resumen, su firma y sus permisos."), [], GLOBAL, "complementos_pl.complemento_instalar", "PL", nivel="intermedio"),
	_o("complemento_recargar", N_("&Recargar el complemento en desarrollo"), N_("Vuelve a cargar el complemento de la carpeta de desarrollo (solo en modo desarrollo)."), [], GLOBAL, "complementos_pl.complemento_recargar", "PL", nivel="avanzado"),
	_o("reiniciar", N_("Reiniciar &zCommander"), N_("Cierra zCommander y lo vuelve a abrir."), [], GLOBAL, "complementos_pl.reiniciar", "PL"),
	_o("reiniciar_sin_complementos", N_("Reiniciar sin c&omplementos"), N_("Reinicia zCommander en modo seguro, sin cargar ningún complemento."), [], GLOBAL, "complementos_pl.reiniciar_sin_complementos", "PL", nivel="intermedio"),
	_o("sonidos_silenciar", N_("&Silenciar los sonidos"), N_("Activa o desactiva todos los sonidos de zCommander."), ["Ctrl+F11"], GLOBAL, "sonidos_so.sonidos_silenciar", "SO", tipo="casilla", estado="sonidos_so.es_silenciado", tecla_global=True),
	_o("sonidos_volumen_subir", N_("S&ubir el volumen de los sonidos"), N_("Sube 10 el volumen de los sonidos y lo anuncia."), [], GLOBAL, "sonidos_so.sonidos_volumen_subir", "SO"),
	_o("sonidos_volumen_bajar", N_("&Bajar el volumen de los sonidos"), N_("Baja 10 el volumen de los sonidos y lo anuncia."), [], GLOBAL, "sonidos_so.sonidos_volumen_bajar", "SO"),
	_o("sonidos_paquetes", N_("Pa&quetes de sonidos..."), N_("Crea, edita, exporta e importa paquetes de sonidos."), [], GLOBAL, "sonidos_so.sonidos_paquetes", "SO", nivel="intermedio"),
	_o("mapa_sonidos", N_("Mapa de &sonidos..."), N_("Lista de todos los sonidos con cuándo suenan; se pueden escuchar."), [], GLOBAL, "sonidos_so.mapa_sonidos", "SO"),
	_o("buscar_actualizaciones", N_("Buscar ac&tualizaciones..."), N_("Comprueba si hay una versión nueva de zCommander."), [], GLOBAL, "actualizar_ac.buscar_actualizaciones", "AC"),
	_o("componentes", N_("Componentes e&xternos..."), N_("rclone, libarchive, 7za y FFmpeg: versiones, actualizaciones y restaurar los originales."), [], GLOBAL, "componentes_co.componentes", "CO", nivel="avanzado"),
	_o("copia_crear", N_("&Crear una copia de seguridad..."), N_("Guarda en un archivo .zcbackup la configuración que elija."), [], GLOBAL, "copia_cs.copia_crear", "CS"),
	_o("copia_restaurar", N_("&Restaurar una copia de seguridad..."), N_("Restaura una copia .zcbackup eligiendo qué partes."), [], GLOBAL, "copia_cs.copia_restaurar", "CS"),
	_o("perfil_exportar", N_("E&xportar un perfil..."), N_("Guarda preferencias, teclas, personalización y macros en un .zcperfil, sin contraseñas."), [], GLOBAL, "copia_cs.perfil_exportar", "CS", nivel="intermedio"),
	_o("perfil_importar", N_("Im&portar un perfil..."), N_("Aplica un .zcperfil eligiendo qué se aplica."), [], GLOBAL, "copia_cs.perfil_importar", "CS", nivel="intermedio"),
	_o("red_raiz", N_("&Red"), N_("Muestra unidades de red, conexiones, servidores recientes y equipos de la red."), ["Ctrl+Shift+K"], GLOBAL, "red_rd.red_raiz", "RD", nivel="intermedio"),
	_o("red_buscar_equipos", N_("&Buscar equipos en la red"), N_("Busca los equipos de la red local y los añade a la raíz Red."), [], GLOBAL, "red_rd.red_buscar_equipos", "RD", nivel="intermedio"),
	_o("red_conectar_recurso", N_("Abrir un recurso &compartido con otra cuenta..."), N_("Abre una carpeta compartida con otro usuario y contraseña."), [], GLOBAL, "red_rd.red_conectar_recurso", "RD", nivel="intermedio"),
	_o("red_reconectar", N_("&Volver a conectar la unidad"), N_("Vuelve a conectar la unidad de red del panel."), [], PANEL, "red_rd.red_reconectar", "RD", nivel="intermedio"),
	_o("red_contrasenas", N_("Contraseñas &guardadas de servidores..."), N_("Lista y borra las credenciales de servidores guardadas en Windows."), [], GLOBAL, "red_rd.red_contrasenas", "RD", nivel="intermedio"),
	_o("red_info", N_("&Información de la conexión"), N_("Servidor, usuario, protocolo y cifrado de la conexión del panel."), [], GLOBAL, "red_rd.red_info", "RD", nivel="intermedio"),
	_o("copiar_ruta_unc", N_("Copiar la ruta &UNC"), N_("Copia la ruta \\\\servidor\\recurso de los elementos de una unidad de red."), [], PANEL, "red_rd.copiar_ruta_unc", "RD", nivel="intermedio"),
	_o("red_sesiones", N_("&Sesiones y archivos abiertos por la red..."), N_("Quién tiene abiertos archivos de este equipo por la red (pide permisos de administrador)."), [], GLOBAL, "red_rd.red_sesiones", "RD", nivel="avanzado"),
	_o("red_cuadro_conectar", N_("Conectar con el cuadro de &Windows..."), N_("Abre el cuadro de Windows para conectar una unidad de red."), [], GLOBAL, "red_rd.red_cuadro_conectar", "RD", nivel="avanzado"),
	_o("red_cuadro_desconectar", N_("Desconectar con el c&uadro de Windows..."), N_("Abre el cuadro de Windows para desconectar una unidad de red."), [], GLOBAL, "red_rd.red_cuadro_desconectar", "RD", nivel="avanzado"),
	_o("macro_grabar", N_("&Grabar una macro"), N_("Empieza o termina la grabación de una macro con las órdenes que ejecute."), ["Ctrl+Shift+G"], GLOBAL, "personalizar_pe.macro_grabar", "PE", tipo="casilla", estado="personalizar_pe.es_grabando", nivel="intermedio", grabable=False),
	_o("macro_ultima", N_("Ejecutar la ú&ltima macro"), N_("Repite la última macro ejecutada."), ["Ctrl+Shift+L"], GLOBAL, "personalizar_pe.macro_ultima", "PE", nivel="intermedio", grabable=False),
	_o("macros", N_("&Macros..."), N_("Crea, edita, ejecuta, exporta e importa macros."), [], GLOBAL, "personalizar_pe.macros", "PE", nivel="intermedio"),
	_o("columnas_carpeta", N_("Columnas &y vista de esta carpeta..."), N_("Conjunto de columnas y vista que se aplica a esta carpeta o a carpetas parecidas."), [], GLOBAL, "personalizar_pe.columnas_carpeta", "PE", por_lado=True, nivel="intermedio"),
	_o("orden_lectura", N_("&Orden de lectura de las columnas..."), N_("Qué columnas se leen al moverse por las filas y en qué orden."), [], GLOBAL, "personalizar_pe.orden_lectura", "PE", nivel="intermedio"),
	_o("personalizar_menus", N_("Personalizar &menús y barras..."), N_("Oculta elementos de menú, llena Mis órdenes, la barra de botones y la barra de teclas."), [], GLOBAL, "personalizar_pe.personalizar_menus", "PE", nivel="avanzado"),
	_o("barra_botones", N_("Mostrar la barra de &botones"), N_("Muestra u oculta la barra de botones configurable."), [], GLOBAL, "personalizar_pe.barra_botones", "PE", tipo="casilla", estado="personalizar_pe.es_barra_botones", nivel="intermedio"),
	_o("ir_barra_botones", N_("Ir a la barra de botones"), N_("Pone el foco en la barra de botones; Escape vuelve al panel."), ["Alt+Shift+F11"], GLOBAL, "personalizar_pe.ir_barra_botones", "PE", nivel="intermedio"),
	_o("esquema_teclas", N_("&Esquema de teclas..."), N_("Teclas como Norton Commander, Total Commander, Far o el Explorador."), [], GLOBAL, "personalizar_pe.esquema_teclas", "PE", nivel="avanzado"),
	_o("alias", N_("&Alias de la línea de órdenes..."), N_("Nombres cortos para órdenes largas de la línea de órdenes."), [], GLOBAL, "personalizar_pe.alias", "PE", nivel="avanzado"),
	_o("linea_autocompletar", N_("Autocompletar"), N_("Completa rutas, alias y órdenes internas en la línea de órdenes."), ["Ctrl+Space"], LINEA, "personalizar_pe.linea_autocompletar", "PE", nivel="intermedio"),
	_o("espacios_trabajo", N_("&Espacios de trabajo..."), N_("Disposiciones de pestañas y paneles guardadas con nombre."), ["Ctrl+Shift+W"], GLOBAL, "personalizar_pe.espacios_trabajo", "PE", nivel="intermedio"),
	_o("espacio_guardar", N_("Guardar el espacio de &trabajo..."), N_("Guarda la disposición actual como espacio de trabajo."), [], GLOBAL, "personalizar_pe.espacio_guardar", "PE", nivel="intermedio"),
	_o("reglas", N_("&Reglas de anuncio, color y sonido..."), N_("Reglas que marcan con color, texto, sonido o anuncio los elementos que cumplen una condición."), [], GLOBAL, "personalizar_pe.reglas", "PE", nivel="avanzado"),
	_o("todas_las_ordenes", N_("&Ver todas las órdenes en los menús"), N_("Con los menús según el nivel, muestra también las órdenes de los otros niveles."), [], GLOBAL, "personalizar_pe.todas_las_ordenes", "PE", tipo="casilla", estado="personalizar_pe.es_todas_las_ordenes"),
	_o("perfil_guardar_propio", N_("&Guardar la configuración como perfil..."), N_("Guarda las preferencias y teclas actuales como un perfil con nombre."), [], GLOBAL, "personalizar_pe.perfil_guardar_propio", "PE", nivel="intermedio"),
	_o("plantillas_archivo", N_("&Plantillas de archivo nuevo"), N_("Abre la carpeta de las plantillas de Crear archivo nuevo."), [], GLOBAL, "personalizar_pe.plantillas_archivo", "PE", nivel="intermedio"),
	_o("traer_al_frente", N_("Traer zCommander al frente"), N_("Restaura y activa la ventana de zCommander (solo como tecla global)."), [], GLOBAL, "personalizar_pe.traer_al_frente", "PE", tecla_global=True),
	_o("complemento_nvda", N_("Instalar el &complemento de zCommander para NVDA..."), N_("Explica qué hace el complemento de NVDA y lo instala si lo acepta."), [], GLOBAL, "nvda_nv.complemento_nvda", "NV"),
]

# Nivel de las 181 órdenes de la 1.x (10.11): por defecto novato; las de búsqueda,
# comparación, comprimidos y red, intermedio; enlaces, atributos, sumas, dividir y
# unir y el menú de Windows, avanzado.
_INTERMEDIAS = frozenset({
	"buscar_archivos", "vista_plana", "comparar_carpetas", "sincronizar_carpetas", "comparar_archivos", "renombrado_multiple",
	"tamano_carpetas", "tamano_todas", "cesta_agregar", "cesta_abrir", "cesta_vaciar", "comprimir", "extraer", "probar_comprimido",
	"conexiones", "desconectar", "conectar_unidad_red", "desconectar_unidad_red",
})
_AVANZADAS = frozenset({"crear_enlace", "atributos", "sumas_crear", "sumas_verificar", "dividir", "unir", "menu_windows"})
# Órdenes de consulta (1.x §6.4): no se graban en las macros (10.1).
_CONSULTA = frozenset({
	"decir_ruta", "decir_ruta_otro", "decir_resumen", "decir_info", "decir_espacio", "decir_operaciones", "repetir_anuncio",
	"historial_anuncios", "columna_anterior", "columna_siguiente", *(f"leer_columna_{n}" for n in range(1, 11)),
})
# Órdenes de la 1.x que se pueden usar como tecla global (10.15).
_TECLA_GLOBAL_1X = frozenset({"ir_a_carpeta", "decir_operaciones"})
# Cambian de bloque (de D a RD) en la 2.0; sus manejadores de la 1.x se amplían allí (9.4, 9.5).
_A_RD = frozenset({"conectar_unidad_red", "desconectar_unidad_red"})
_AYUDA_CANCELAR = N_("Hace lo primero que se pueda: detener la macro en curso; cancelar la lectura, el cálculo o la búsqueda "
	"de equipos del panel; quitar el filtro rápido; detener la orden lanzada desde la línea de órdenes.")


def _completar_1x(orden: Orden) -> Orden:
	cambios: dict = {}
	if orden.id in _INTERMEDIAS:
		cambios["nivel"] = "intermedio"
	elif orden.id in _AVANZADAS:
		cambios["nivel"] = "avanzado"
	if orden.id in _CONSULTA or orden.id == "cancelar":
		cambios["grabable"] = False
	if orden.id in _TECLA_GLOBAL_1X:
		cambios["tecla_global"] = True
	if orden.id in _A_RD:
		cambios["bloque"] = "RD"
	if orden.id == "cancelar":
		cambios["ayuda"] = _AYUDA_CANCELAR
	return dataclasses.replace(orden, **cambios) if cambios else orden


#: Órdenes del núcleo (las 181 de la 1.x y las nuevas de la 2.0 salvo ``complemento_recargar``,
#: que solo existe en modo desarrollo). Es la tupla estática de la 1.x con otro nombre.
_RECARGAR = next(o for o in _ORDENES_2 if o.id == "complemento_recargar")
CATALOGO_NUCLEO: tuple[Orden, ...] = tuple(_completar_1x(o) for o in _ORDENES) + tuple(o for o in _ORDENES_2 if o is not _RECARGAR)


# ── Catálogo dinámico (14.1.1) ───────────────────────────────────────────────

_dinamico: dict = {"fuente_macros": None, "version_macros": 0, "clave": None, "tupla": (), "por_id": {}}
_candado_catalogo = threading.RLock()


def fijar_fuente_macros(funcion: Callable[[], list[tuple[str, bool, bool]]] | None) -> None:
	"""Fuente de las macros (nombre, en «Mis órdenes», en la paleta); la fija PE al arrancar su servicio."""
	_dinamico["fuente_macros"] = funcion
	catalogo_cambiado()


_personalizador: list = [None]


def fijar_personalizador(objeto: Any) -> None:
	"""PE (10.6, 10.11): objeto con ``menus(tupla) -> tupla``, ``lista(elementos) -> list`` y
	``barra_teclas(modificador, fabrica) -> tupla`` (``menus_personalizados.Personalizador``), o ``None``."""
	_personalizador[0] = objeto
	catalogo_cambiado()


def _personalizar(nombre: str, fabrica: Any, *args: Any) -> Any:
	"""Lo de fábrica pasado por el personalizador; si falla, lo de fábrica (un ``menus.json`` raro no deja sin menús)."""
	objeto = _personalizador[0]
	if objeto is None:
		return fabrica
	try:
		return getattr(objeto, nombre)(*args, fabrica) if args else getattr(objeto, nombre)(fabrica)
	except Exception:  # noqa: BLE001 - se vuelve a lo de fábrica y queda en el registro
		log.exception("Falló la personalización de %s", nombre)
		return fabrica


def menu_lado() -> tuple:
	"""``MENU_LADO`` con lo oculto y el nivel aplicados (10.6, 10.11)."""
	return tuple(_personalizar("lista", MENU_LADO))


def barra_teclas(modificador: str) -> tuple:
	"""Los diez huecos de ``BARRA_TECLAS[modificador]`` con los cambios de la persona (10.6)."""
	return tuple(_personalizar("barra_teclas", BARRA_TECLAS[modificador], modificador))


def fijar_modo_desarrollo(activo: bool) -> None:
	"""Con el modo desarrollo de complementos, el catálogo incluye ``complemento_recargar``."""
	_registro_complementos().fijar_modo_desarrollo(activo)


def _registro_complementos():
	from app.plugins import registro

	return registro


def catalogo_cambiado() -> None:
	"""Sube el contador de versión y emite ``al_cambiar_catalogo`` (en el hilo de la interfaz, 3.10)."""
	with _candado_catalogo:
		_dinamico["version_macros"] += 1
	_avisar_cambio()


def _avisar_cambio() -> None:
	from app.services import eventos

	eventos.bus().emitir(eventos.AL_CAMBIAR_CATALOGO)


def _macros() -> list[tuple[str, bool, bool]]:
	fuente = _dinamico["fuente_macros"]
	if fuente is None:
		return []
	try:
		return [(str(n), bool(m), bool(p)) for n, m, p in fuente()]
	except Exception:  # noqa: BLE001 - una fuente de macros rota no deja sin catálogo
		log.exception("Falló la fuente de macros")
		return []


def _orden_de_complemento(orden: Any) -> Orden:
	return Orden(
		id=orden.id, etiqueta=orden.etiqueta, ayuda=orden.ayuda, teclas=tuple(orden.teclas), ambito=orden.ambito,
		manejador="complementos_pl.ejecutar", bloque=orden.bloque, tipo=orden.tipo,
		estado="complementos_pl.estado" if orden.tipo == "casilla" else "", param=orden.id,
		nivel=orden.nivel or "novato", tecla_global=orden.tecla_global,
	)


def _se_solapan(ambito_a: str, ambito_b: str) -> bool:
	"""Dos ámbitos comparten teclas si son el mismo o si uno de ellos es global."""
	return ambito_a == ambito_b or GLOBAL in (ambito_a, ambito_b)


def _sin_teclas_ocupadas(base: list[Orden], de_complementos: list[Orden]) -> list[Orden]:
	"""Quita a los complementos de TERCEROS las teclas que ya usa otra orden (14.1.3).

	Las del núcleo y las de los complementos de serie se respetan (su choque lo
	impide la prueba de teclas); un complemento de terceros que pida una tecla
	ocupada se queda sin ella, y el gestor lo dice en sus detalles.
	"""
	from app.plugins import serie

	def es_de_serie(orden: Orden) -> bool:
		return orden.id.split(":", 1)[0] in serie.SERIE

	ocupadas = [(t, o.ambito) for o in base for t in o.teclas]
	ocupadas += [(t, o.ambito) for o in de_complementos if es_de_serie(o) for t in o.teclas]
	resultado = []
	for orden in de_complementos:
		if not es_de_serie(orden) and orden.teclas:
			libres = tuple(t for t in orden.teclas
				if not any(t == tecla and _se_solapan(orden.ambito, ambito) for tecla, ambito in ocupadas))
			if libres != orden.teclas:
				log.info("El complemento de %s pierde teclas ocupadas: %s", orden.id,
					", ".join(t for t in orden.teclas if t not in libres))
				orden = replace(orden, teclas=libres)
			ocupadas += [(t, orden.ambito) for t in libres]
		resultado.append(orden)
	return resultado


def catalogo() -> tuple[Orden, ...]:
	"""Instantánea inmutable: núcleo + órdenes de complementos registrados + macros.

	Se recalcula solo cuando cambia algo (versión del registro, de las macros o del
	modo desarrollo); un hilo puede recorrer la tupla sin peligro.
	"""
	registro = _registro_complementos()
	clave = (registro.version(), _dinamico["version_macros"], registro.modo_desarrollo())
	with _candado_catalogo:
		if _dinamico["clave"] == clave:
			return _dinamico["tupla"]
		ordenes_2 = list(CATALOGO_NUCLEO)
		if registro.modo_desarrollo():
			ordenes_2.append(_RECARGAR)
		ordenes_2 += _sin_teclas_ocupadas(ordenes_2, [_orden_de_complemento(o) for o in registro.ordenes()])
		macros = _macros()
		# Letras de acceso propias de las macros: así «Mis órdenes» nunca repite letra.
		etiquetas = letras_submenus([n for n, _m, _p in macros], set())
		for (nombre, _menu, _paleta), etiqueta in zip(macros, etiquetas, strict=True):
			ordenes_2.append(Orden(f"macro:{nombre}", etiqueta, N_("Macro de la persona."), (), GLOBAL,
				"personalizar_pe.ejecutar_macro", "PE", param=nombre, tecla_global=True))
		tupla = tuple(ordenes_2)
		_dinamico.update(clave=clave, tupla=tupla, por_id={o.id: o for o in tupla})
		return tupla


def _por_id() -> dict[str, Orden]:
	catalogo()
	return _dinamico["por_id"]


class _CatalogoVivo(Sequence):
	"""``CATALOGO``: se recorre, se indexa y tiene ``len`` como la tupla de la 1.x, pero refleja ``catalogo()``."""

	def __getitem__(self, indice):  # type: ignore[override]
		return catalogo()[indice]

	def __len__(self) -> int:
		return len(catalogo())

	def __iter__(self):
		return iter(catalogo())

	def __contains__(self, orden: object) -> bool:
		return orden in catalogo()


class _PorIdVivo(Mapping):
	"""``POR_ID``: diccionario de solo lectura que se recalcula con el catálogo."""

	def __getitem__(self, id_orden: str) -> Orden:
		return _por_id()[id_orden]

	def __len__(self) -> int:
		return len(_por_id())

	def __iter__(self):
		return iter(_por_id())

	def __contains__(self, id_orden: object) -> bool:
		return id_orden in _por_id()


CATALOGO: Sequence[Orden] = _CatalogoVivo()
POR_ID: Mapping[str, Orden] = _PorIdVivo()

# ── Menús ────────────────────────────────────────────────────────────────────
# (título, [id | None (separador) | (título_submenú, [ids...])]). «@lado» es el
# menú Izquierdo o Derecho: sus órdenes «por_lado» actúan sobre ese lado.
# Solo ids del núcleo que existen siempre: lo dinámico (submenús de
# complementos, «Mis órdenes», anclas) lo añaden ``menus()`` y ``menu_contextual()``.
LADO = "@lado"
TITULO_COMPLEMENTOS = N_("Co&mplementos")
TITULO_MIS_ORDENES = N_("Mis ó&rdenes")
TITULO_HERRAMIENTAS = N_("&Herramientas")

MENUS: tuple = (
	(N_("&Izquierdo"), LADO),
	# Archivos: abrir y ver; crear, copiar, mover y eliminar; marcas y portapapeles;
	# al final, el menú de usuario y salir (Salir siempre es lo último).
	(N_("&Archivos"), [
		"abrir", "ver", "ver_externo", "editar", "abrir_con",
		None, "copiar", "mover", "duplicar", "renombrar", "crear_carpeta", "crear_archivo",
		"eliminar", "eliminar_definitivo", "deshacer",
		None, "atributos", "propiedades", "menu_windows",
		None, (N_("&Marcas"), [
			"marcar_patron", "desmarcar_patron", "invertir_marcas", "marcar_todo", "desmarcar_todo",
			"marcar_extension", "desmarcar_extension", "restaurar_marcas", None, "guardar_marcas", "cargar_marcas",
		]),
		(N_("Por&tapapeles"), [
			"portapapeles_copiar", "portapapeles_cortar", "portapapeles_pegar", None,
			"copiar_rutas", "copiar_nombres", "copiar_ruta_carpeta", "copiar_ruta_unc",
		]),
		None, "menu_usuario",
		None, "reiniciar", "salir",
	]),
	# Comandos: moverse, buscar y comparar; las herramientas agrupadas en submenús;
	# al final, lo que abre fuera de zCommander y las operaciones en curso.
	(N_("&Comandos"), [
		"ir_a_carpeta", "arbol_carpetas", "historial_carpetas", "favoritos", "agregar_favorito", "historial_ordenes",
		None, "buscar_archivos", "comparar_carpetas", "sincronizar_carpetas", "comparar_archivos", "renombrado_multiple",
		None, (N_("Pa&neles"), [
			"intercambiar_paneles", "igualar_paneles", "mostrar_paneles", "panel_pasivo", "abrir_en_izquierdo", "abrir_en_derecho",
			None, "espacios_trabajo", "espacio_guardar",
		]),
		(TITULO_HERRAMIENTAS, [
			"tamano_carpetas", "tamano_todas", "vista_plana", None, "sumas_crear", "sumas_verificar", None, "dividir", "unir",
			None, "crear_enlace",
		]),
		(N_("C&esta"), ["cesta_agregar", "cesta_abrir", "cesta_vaciar"]),
		(N_("Com&primidos"), ["comprimir", "extraer", "probar_comprimido"]),
		(N_("Re&d"), [
			"red_raiz", "red_buscar_equipos", "red_conectar_recurso", "red_reconectar", "red_info", "red_contrasenas", "red_sesiones",
			None, "conexiones", "desconectar",
			None, "conectar_unidad_red", "desconectar_unidad_red", "red_cuadro_conectar", "red_cuadro_desconectar",
		]),
		None, "operaciones", "consola", "explorador",
	]),
	# Complementos: el gestor y, debajo, un submenú por complemento con TODAS sus órdenes
	# (los menús del núcleo no llevan órdenes de complementos: cada cosa en un solo sitio).
	(TITULO_COMPLEMENTOS, ["complementos", "complemento_instalar", "reiniciar_sin_complementos"]),
	# Opciones: preferencias y perfiles; personalización, macros y sonidos; lo que se
	# edita aparte; componentes y copias; y lo de mantenimiento al final.
	(N_("&Opciones"), [
		"preferencias",
		(N_("Per&files"), ["perfil", "perfil_guardar_propio", "perfil_exportar", "perfil_importar"]),
		None, (N_("Personali&zación"), [
			"esquema_teclas", "mapa_teclas", None, "personalizar_menus", "barra_botones", "todas_las_ordenes",
			None, "columnas_defecto", "orden_lectura", "reglas", None, "alias", "plantillas_archivo",
		]),
		(N_("Macro&s"), ["macro_grabar", "macro_ultima", "macros"]),
		(N_("Son&idos"), ["sonidos_silenciar", "sonidos_volumen_subir", "sonidos_volumen_bajar", "sonidos_paquetes"]),
		None, "editar_menu_usuario", "editar_asociaciones", "mostrar_ocultos",
		None, "componentes", (N_("Copia d&e seguridad"), ["copia_crear", "copia_restaurar"]),
		None, "asistente", "guardar_sesion", "restablecer_fabrica",
		None, "carpeta_datos", "carpeta_registros",
	]),
	(N_("&Derecho"), LADO),
	(N_("Ay&uda"), [
		"manual", "lista_teclas", "novedades", "ayuda_contextual",
		None, "paleta_ordenes", "ayuda_teclado", "historial_anuncios", "mapa_sonidos",
		None, "buscar_actualizaciones", "complemento_nvda",
		None, "info_soporte", "acerca_de",
	]),
)

# Menú de un lado (Izquierdo o Derecho).
MENU_LADO: tuple = (
	"vista_completa", "vista_breve", "vista_informacion", "vista_arbol", "vista_rapida",
	None, "ordenar_nombre", "ordenar_extension", "ordenar_fecha", "ordenar_tamano", "ordenar_tipo", "sin_ordenar",
	"orden_inverso", "carpetas_primero",
	None, "filtro", "quitar_filtro", "columnas", "columnas_carpeta",
	None, "volver_a_leer", "unidad",
	None, (N_("Pest&añas"), [
		"pestana_nueva", "pestana_cerrar", "pestana_cerrar_otras", "pestana_siguiente", "pestana_anterior",
		"pestana_bloquear", "lista_pestanas",
	]),
	None, "mostrar_lado",
)

# Menú contextual del panel (Mayús+F10, Aplicaciones, clic derecho).
#: Etiquetas propias del menú contextual (para que sus letras no se repitan).
ETIQUETAS_CONTEXTUAL: dict[str, str] = {
	"portapapeles_copiar": N_("Copiar al p&ortapapeles"),
	"portapapeles_cortar": N_("Cor&tar"),
	"copiar_rutas": N_("Copiar las r&utas completas"),
	"cesta_agregar": N_("Añadir a la ce&sta"),
	"comprimir": N_("Compri&mir..."),
	"extraer": N_("E&xtraer..."),
	"propiedades": N_("Propie&dades"),
}

MENU_CONTEXTUAL: tuple = (
	"abrir", "ver", "editar", None, "copiar", "mover", "renombrar", "eliminar",
	None, "portapapeles_copiar", "portapapeles_cortar", "portapapeles_pegar", "copiar_rutas",
	None, "comprimir", "extraer", "cesta_agregar", None, "propiedades", "menu_windows",
)

# Barra de teclas: (tecla, orden) por modificador. Las etiquetas son cortas
# (caben en el botón) y se anuncian con su tecla.
BARRA_TECLAS: dict[str, tuple[tuple[str, str, str], ...]] = {
	"": (
		("F1", "manual", N_("Ayuda")), ("F2", "menu_usuario", N_("Menú")), ("F3", "ver", N_("Ver")),
		("F4", "editar", N_("Editar")), ("F5", "copiar", N_("Copiar")), ("F6", "mover", N_("RenMov")),
		("F7", "crear_carpeta", N_("Carpeta")), ("F8", "eliminar", N_("Borrar")), ("F9", "abrir_menus", N_("Menús")),
		("F10", "salir", N_("Salir")),
	),
	"Shift": (
		("F1", "lista_teclas", N_("Teclas")), ("F2", "ir_linea_ordenes", N_("Orden")), ("F3", "explorador", N_("Explor")),
		("F4", "crear_archivo", N_("Nuevo")), ("F5", "duplicar", N_("Duplic")), ("F6", "renombrar", N_("Renom")),
		("F7", "", ""), ("F8", "eliminar_definitivo", N_("Borrar!")), ("F9", "guardar_sesion", N_("Guardar")),
		("F10", "menu_contextual", N_("Contex")),
	),
	"Ctrl": (
		("F1", "mostrar_izquierdo", N_("Izq")), ("F2", "mostrar_derecho", N_("Der")), ("F3", "ordenar_nombre", N_("Nombre")),
		("F4", "ordenar_extension", N_("Ext")), ("F5", "ordenar_fecha", N_("Fecha")), ("F6", "ordenar_tamano", N_("Tamaño")),
		("F7", "sin_ordenar", N_("SinOrd")), ("F8", "", ""), ("F9", "", ""), ("F10", "comparar_carpetas", N_("Compar")),
	),
	"Alt": (
		("F1", "unidad_izquierda", N_("Unid Iz")), ("F2", "unidad_derecha", N_("Unid De")), ("F3", "ver_externo", N_("VerExt")),
		("F4", "", ""), ("F5", "comprimir", N_("Compr")), ("F6", "extraer", N_("Extraer")), ("F7", "buscar_archivos", N_("Buscar")),
		("F8", "historial_ordenes", N_("Histor")), ("F9", "extraer", N_("Extraer")), ("F10", "arbol_carpetas", N_("Árbol")),
	),
}

# Órdenes de tecla que no aparecen en ningún menú (se ven en la lista de teclas y la paleta).
SOLO_TECLA = frozenset({
	"cancelar", "abrir_menus", "cambiar_panel", "subir", "entrar", "raiz", "carpeta_personal", "atras", "adelante", "ir_linea_ordenes",
	"filtro_rapido", "busqueda_rapida", "mostrar_izquierdo", "mostrar_derecho", "unidad_izquierda", "unidad_derecha",
	"menu_contextual", "marcar", "marcar_sin_mover", "marcar_subir", "marcar_bajar", "marcar_pagina_arriba",
	"marcar_pagina_abajo", "marcar_hasta_inicio", "marcar_hasta_fin", "insertar_nombre", "insertar_ruta",
	"ejecutar_linea", "ejecutar_en_consola", "linea_anterior", "linea_siguiente", "linea_vaciar", "linea_al_panel",
	*(f"pestana_{n}" for n in range(1, 10)),
	"decir_ruta", "decir_ruta_otro", "decir_resumen", "decir_info", "decir_espacio", "decir_operaciones", "repetir_anuncio",
	*(f"leer_columna_{n}" for n in range(1, 11)), "columna_anterior", "columna_siguiente",
	# 2.0
	"ir_barra_botones", "linea_autocompletar", "traer_al_frente",
})


def _letra(etiqueta: str) -> str | None:
	i = 0
	while True:
		i = etiqueta.find("&", i)
		if i < 0 or i + 1 >= len(etiqueta):
			return None
		if etiqueta[i + 1] == "&":
			i += 2
			continue
		return etiqueta[i + 1].lower()


def letras_submenus(nombres: Sequence[str], ocupadas: set[str]) -> list[str]:
	"""Etiquetas con letra de acceso para los submenús de Complementos (14.1.1).

	Para cada nombre, la primera de sus letras que no esté ocupada, en orden; si no
	queda ninguna, sin letra (``comprobar_menus.py`` lo avisa).
	"""
	ocupadas_min = {o.lower() for o in ocupadas}
	candidatas = [[(i, c.lower()) for i, c in enumerate(n) if c.isalnum() and c.lower() not in ocupadas_min] for n in nombres]
	# Primero la regla sencilla del diseño (la primera letra libre de cada nombre, en orden).
	asignadas: dict[int, tuple[int, str]] = {}
	usadas: dict[str, int] = {}
	for n, opciones in enumerate(candidatas):
		for indice, letra in opciones:
			if letra not in usadas:
				asignadas[n], usadas[letra] = (indice, letra), n
				break
	# Si alguno se queda sin letra, se reparte de nuevo por emparejamiento (caminos de aumento):
	# con 23 complementos en el menú, la regla sencilla deja sin letra a los últimos aunque
	# aún queden letras libres en su nombre.
	for n in range(len(candidatas)):
		if n in asignadas:
			continue

		def aumentar(actual: int, vistas: set[str]) -> bool:
			for indice, letra in candidatas[actual]:
				if letra in vistas:
					continue
				vistas.add(letra)
				dueno = usadas.get(letra)
				if dueno is None or aumentar(dueno, vistas):
					asignadas[actual], usadas[letra] = (indice, letra), actual
					return True
			return False

		aumentar(n, set())
	resultado = []
	for n, nombre in enumerate(nombres):
		if n in asignadas:
			indice = asignadas[n][0]
			resultado.append(nombre[:indice].replace("&", "&&") + "&" + nombre[indice:].replace("&", "&&"))
		else:
			resultado.append(nombre.replace("&", "&&"))
	return resultado


def _letras_de(elementos) -> set[str]:
	letras = set()
	for elemento in elementos:
		if elemento is None:
			continue
		etiqueta = elemento[0] if isinstance(elemento, tuple) else POR_ID[elemento].etiqueta if elemento in POR_ID else ""
		letra = _letra(etiqueta)
		if letra:
			letras.add(letra)
	return letras


#: Valores de ``menu`` del manifiesto que se muestran en el submenú del complemento.
#: ``archivos``, ``comandos`` y ``herramientas`` se aceptan por compatibilidad con la API 1.0,
#: pero ya no cuelgan la orden de esos menús del núcleo.
MENUS_DE_COMPLEMENTO = frozenset({"complementos", "archivos", "comandos", "herramientas"})


#: Categoría del menú Complementos de cada grupo de complementos de serie (por su bloque).
#: Los de terceros van a «Otros complementos».
CATEGORIAS_COMPLEMENTOS: tuple[tuple[str, frozenset[str]], ...] = (
	(N_("Multimedia"), frozenset({"P1"})),
	(N_("Documentos y datos"), frozenset({"P2"})),
	(N_("Orden y limpieza del disco"), frozenset({"P3"})),
	(N_("Sistema y seguridad"), frozenset({"P4"})),
	(N_("Automatización"), frozenset({"P5"})),
	(N_("Nubes y NAS"), frozenset({"NU", "NS"})),
)
TITULO_OTROS_COMPLEMENTOS = N_("Otros complementos")


def _submenus_por_categoria(
	por_complemento: dict[str, list[str]], nombres: dict[str, str], bloques: dict[str, str], ocupadas: set[str],
) -> list:
	"""Submenús del menú Complementos: una categoría por grupo y, dentro, un submenú por complemento.

	Con 27 complementos en un solo nivel no hay letras de acceso para todos y la
	lista es muy larga; por categorías cada nivel tiene pocas entradas y todas con
	su letra. Las categorías vacías no aparecen.
	"""
	grupos: list[tuple[str, list[str]]] = []
	usados: set[str] = set()
	for titulo, bloques_categoria in CATEGORIAS_COMPLEMENTOS:
		ids = [i for i in por_complemento if bloques.get(i) in bloques_categoria]
		if ids:
			grupos.append((titulo, ids))
			usados.update(ids)
	otros = [i for i in por_complemento if i not in usados]
	if otros:
		grupos.append((TITULO_OTROS_COMPLEMENTOS, otros))
	etiquetas_grupo = letras_submenus([titulo for titulo, _ids in grupos], ocupadas)
	resultado = []
	for etiqueta_grupo, (_titulo, ids) in zip(etiquetas_grupo, grupos, strict=True):
		ids = sorted(ids, key=lambda i: (nombres[i].casefold(), i))
		etiquetas = letras_submenus([nombres[i] for i in ids], set())
		resultado.append((etiqueta_grupo, [(e, por_complemento[i]) for e, i in zip(etiquetas, ids, strict=True)]))
	return resultado


def _anclas(menu: str, contextual: bool = False) -> list[str]:
	"""Órdenes de complementos ancladas en un menú del núcleo, por orden alfabético de etiqueta (14.2)."""
	registro = _registro_complementos()
	ordenes_menu = [o for o in registro.ordenes() if o.menu == menu and (not contextual or o.ambito == PANEL)]
	return [o.id for o in sorted(ordenes_menu, key=lambda o: o.etiqueta.replace("&", "").casefold())]


def menus() -> tuple:
	"""``MENUS`` expandido con el catálogo vivo (misma forma): Complementos, Mis órdenes y anclas (14.1.1, 14.2)."""
	registro = _registro_complementos()
	resultado = []
	mis: list[str] = []
	for titulo, contenido in MENUS:
		if contenido == LADO:
			resultado.append((titulo, contenido))
			continue
		elementos = list(contenido)
		if titulo == TITULO_COMPLEMENTOS:
			if registro.modo_desarrollo():
				elementos.append("complemento_recargar")
			por_complemento: dict[str, list[str]] = {}
			nombres: dict[str, str] = {}
			bloques: dict[str, str] = {}
			for orden in registro.ordenes():
				# Todas las órdenes de un complemento van juntas en SU submenú, también las que
				# su manifiesto ancla en Archivos, Comandos o Herramientas: así un complemento
				# no queda partido entre dos menús ni sus órdenes se mezclan con las del núcleo
				# (antes «Ver y editar en hexadecimal» quedaba debajo de Salir). Las de
				# «contextual» van además al menú contextual.
				if orden.menu in MENUS_DE_COMPLEMENTO:
					por_complemento.setdefault(orden.complemento, []).append(orden.id)
					nombres[orden.complemento] = orden.nombre_complemento
					bloques[orden.complemento] = orden.bloque
			if por_complemento:
				elementos += [None, *_submenus_por_categoria(por_complemento, nombres, bloques, _letras_de(elementos))]
		resultado.append((titulo, elementos))
		if titulo == N_("&Opciones"):
			mis = [f"macro:{n}" for n, en_menu, _p in _macros() if en_menu]
			if mis:
				resultado.append((TITULO_MIS_ORDENES, mis))
	# 2.0 (10.6, 10.11): lo oculto, «Mis órdenes» de la persona y los menús por nivel (PE).
	if _personalizador[0] is None:
		return tuple(resultado)
	return _con_macros(tuple(_personalizar("menus", tuple(resultado))), mis)


def _con_macros(menus_: tuple, macros: list[str]) -> tuple:
	"""Las macros de «Mis órdenes» de la fuente del catálogo que el personalizador no puso (nunca se pierde una)."""
	if not macros:
		return menus_
	resultado = list(menus_)
	indice = next((i for i, (titulo, _c) in enumerate(resultado) if titulo == TITULO_MIS_ORDENES), None)
	puestas = set(_ids_menu(resultado[indice][1])) if indice is not None else set()
	faltan = [m for m in macros if m not in puestas]
	if not faltan:
		return menus_
	if indice is not None:
		actuales = list(resultado[indice][1])
		resultado[indice] = (TITULO_MIS_ORDENES, [*actuales, *([None] if actuales else []), *faltan])
	else:
		despues = next((i + 1 for i, (titulo, _c) in enumerate(resultado) if titulo == N_("&Opciones")), len(resultado))
		resultado.insert(despues, (TITULO_MIS_ORDENES, faltan))
	return tuple(resultado)


def _ids_menu(elementos) -> list[str]:
	ids: list[str] = []
	for elemento in elementos:
		if isinstance(elemento, tuple):
			ids += _ids_menu(elemento[1])
		elif elemento is not None:
			ids.append(str(elemento))
	return ids


def menu_contextual() -> tuple:
	"""``MENU_CONTEXTUAL`` con las órdenes de complementos de ``menu = "contextual"`` al final (ámbito panel)."""
	anclas = _anclas("contextual", contextual=True)
	completo = (*MENU_CONTEXTUAL, None, *anclas) if anclas else MENU_CONTEXTUAL
	return tuple(_personalizar("lista", completo))


def teclas_por_defecto(esquema: str | None = None) -> dict[str, tuple[str, ...]]:
	"""``{id: teclas}`` para construir el ``MapaTeclas``, con las diferencias del esquema si se da (10.7)."""
	teclas = {o.id: o.teclas for o in catalogo()}
	if esquema:
		from app.services import esquemas_teclas

		teclas = esquemas_teclas.aplicar(teclas, esquema)
	return teclas


def ambitos() -> dict[str, str]:
	return {o.id: o.ambito for o in catalogo()}


def fijas() -> frozenset[str]:
	return frozenset(o.id for o in catalogo() if o.fija)


def _al_cambiar_registro() -> None:
	_avisar_cambio()


_registro_complementos().suscribir_cambios(_al_cambiar_registro)
