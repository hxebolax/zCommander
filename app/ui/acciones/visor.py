# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque A: ver (F3), ver con el visor externo (Alt+F3), editar (F4), crear archivo (Mayús+F4) y comparar archivos.

Reglas de la sección 8.2 y 8.3 del diseño, en este orden:

- **F3**: la asociación del tipo para «ver» (``asociaciones.orden_para``) o,
  si no hay, el visor interno. En una carpeta, calcula su tamaño (como en
  Total Commander).
- **Alt+F3**: siempre el programa de ``visor.externo``; si está vacío, avisa.
- **F4**: la asociación para «editar»; si no hay, ``editor.externo`` cuando
  ``editor.usar_externo`` está activo; si no, el editor interno.
- **Mayús+F4**: pide un nombre, crea el archivo vacío en la carpeta del panel
  y lo abre siguiendo la regla de F4 (si ya existe, lo abre sin tocarlo).
- **Comparar archivos**: los dos marcados del panel activo o el del cursor de
  cada panel; la ventana de diferencias decide si usa el programa externo.

Un archivo que no está en el disco (comprimido o servidor) se extrae a
``data/temp/extraidos`` en un hilo antes de dárselo a un programa externo, y
se vigila: si el programa lo cambia, al volver a zCommander se ofrece
actualizarlo en su origen (``archivos.ofrecer_actualizar_desde``). Los
archivos que solo están en la nube se descargan solo si la persona lo confirma.
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.core.tareas import TareaCancelada
from app.services import asociaciones
from app.services.vfs import base
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mensaje(error: BaseException) -> str:
	from app.ui.ventanas.visor import mensaje_error

	return mensaje_error(error)


def _archivo_del_cursor(ctx, para: str) -> base.Entrada | None:
	"""Archivo del cursor del panel activo, o ``None`` (con aviso) si es una carpeta o no hay."""
	entrada = ctx.activo.cursor()
	if entrada is None or entrada.es_superior:
		anuncios.anunciar(_("No hay ningún archivo para {p}").format(p=para), anuncios.RESULTADO)
		return None
	if entrada.es_carpeta:
		anuncios.anunciar(_("«{n}» es una carpeta: elija un archivo para {p}").format(n=entrada.nombre, p=para), anuncios.RESULTADO)
		return None
	return entrada


def _confirmar_nube(ctx, entrada: base.Entrada, para: str) -> bool:
	"""Los archivos que solo están en la nube se descargan al leerlos: se pregunta antes (sección 8.2)."""
	if not entrada.en_nube:
		return True
	from app.ui.accesibilidad import dialogos

	pregunta = _("«{n}» solo está en la nube. ¿Descargarlo para {p}?").format(n=entrada.nombre, p=para)
	return dialogos.confirmar(ctx.ventana, pregunta, _("Archivo en la nube")) == wx.ID_YES


def _lanzar_programa(ctx, panel, ruta_local: str, plantilla: str) -> None:
	"""Lanza ``plantilla`` (con %P y las demás variables) sin ``cmd`` y en un hilo."""
	from app.services import variables
	from app.services.windows import shell_basico

	otro = ctx.pasivo
	cursor_otro = otro.cursor() if otro is not None else None
	valores = variables.Valores(
		cursor=ruta_local, carpeta=panel.ruta_local() or os.path.dirname(ruta_local),
		otra_carpeta=(otro.ruta_local() or "") if otro is not None else "",
		cursor_otro=cursor_otro.ruta if cursor_otro is not None and not cursor_otro.es_superior and otro.es_local() else "",
		trabajo=[ruta_local],
	)

	def al_error(error: BaseException) -> None:
		wx.CallAfter(anuncios.anunciar, _("No se pudo abrir el programa: {e}").format(e=error), anuncios.ESENCIAL)

	try:
		linea = variables.expandir_directo(plantilla, valores)
	except Exception as error:  # noqa: BLE001 - una plantilla mal escrita se explica, no rompe la orden
		log.warning("No se pudo expandir la orden «%s»: %s", plantilla, error, exc_info=True)
		anuncios.anunciar(_("La orden «{o}» no es válida: {e}").format(o=plantilla, e=error), anuncios.ESENCIAL)
		return
	shell_basico.lanzar(linea, os.path.dirname(ruta_local), al_error)
	anuncios.anunciar(_("Abriendo {n}").format(n=os.path.basename(ruta_local)), anuncios.DETALLE)


def abrir_con_programa(ctx, panel, proveedor: base.Proveedor, ruta: str, plantilla: str) -> None:
	"""Abre ``ruta`` con un programa externo; si no está en el disco, la extrae y la vigila."""
	local = proveedor.ruta_local(ruta)
	if local is not None:
		_lanzar_programa(ctx, panel, local, plantilla)
		return
	from app.ui.ventanas.visor import extraer

	def trabajo(tarea):
		return extraer(proveedor, ruta, tarea)

	def listo(temporal: str) -> None:
		from app.services.vfs import temporales
		from app.ui.acciones import archivos

		temporales.vigilados.vigilar(temporal, proveedor, ruta, archivos.ofrecer_actualizar_desde(ctx.ventana))
		_lanzar_programa(ctx, panel, temporal, plantilla)

	def fallo(error: BaseException) -> None:
		if not isinstance(error, TareaCancelada):
			anuncios.anunciar(_("No se pudo extraer «{n}»: {e}").format(n=proveedor.nombre(ruta), e=_mensaje(error)), anuncios.ESENCIAL)

	anuncios.anunciar(_("Extrayendo {n}...").format(n=proveedor.nombre(ruta)), anuncios.DETALLE)
	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="extraer-para-programa")


# ── Ver ─────────────────────────────────────────────────────────────────────────


def ver(ctx) -> None:
	"""F3: asociación para «ver» o visor interno; en una carpeta, su tamaño."""
	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is not None and entrada.es_carpeta and not entrada.es_superior:
		ctx.ejecutar_orden("tamano_carpetas")
		return
	entrada = _archivo_del_cursor(ctx, _("ver"))
	if entrada is None or not _confirmar_nube(ctx, entrada, _("verlo")):
		return
	orden = asociaciones.orden_para(entrada.nombre, "ver")
	if orden:
		abrir_con_programa(ctx, panel, panel.proveedor, entrada.ruta, orden)
		return
	from app.ui.ventanas import visor

	visor.abrir(ctx.ventana, panel.proveedor, entrada.ruta, ctx.config, ctx.tareas)


def ver_externo(ctx) -> None:
	"""Alt+F3: siempre el programa de ``visor.externo`` con %P."""
	plantilla = str(ctx.config.obtener("visor.externo") or "").strip()
	if not plantilla:
		anuncios.anunciar(_("No hay visor externo configurado. Puede elegirlo en Preferencias, página Visor y editor."),
			anuncios.RESULTADO)
		return
	entrada = _archivo_del_cursor(ctx, _("ver"))
	if entrada is None or not _confirmar_nube(ctx, entrada, _("verlo")):
		return
	abrir_con_programa(ctx, ctx.activo, ctx.activo.proveedor, entrada.ruta, plantilla)


# ── Editar ──────────────────────────────────────────────────────────────────────


def editar_ruta(ctx, panel, proveedor: base.Proveedor, ruta: str) -> None:
	"""Regla de F4 sobre un archivo concreto (también la usa crear archivo)."""
	nombre = proveedor.nombre(ruta) or ruta
	orden = asociaciones.orden_para(nombre, "editar")
	if not orden and ctx.config.obtener("editor.usar_externo"):
		orden = str(ctx.config.obtener("editor.externo") or "").strip()
		if not orden:
			anuncios.anunciar(_("No hay editor externo configurado: se usa el interno"), anuncios.RESULTADO)
	if orden:
		abrir_con_programa(ctx, panel, proveedor, ruta, orden)
		return
	from app.ui.ventanas import editor

	editor.abrir(ctx.ventana, proveedor, ruta, ctx.config, ctx.tareas)


def editar(ctx) -> None:
	"""F4: asociación para «editar», editor externo si está activo, o editor interno."""
	entrada = _archivo_del_cursor(ctx, _("editar"))
	if entrada is None or not _confirmar_nube(ctx, entrada, _("editarlo")):
		return
	editar_ruta(ctx, ctx.activo, ctx.activo.proveedor, entrada.ruta)


def crear_archivo(ctx) -> None:
	"""Mayús+F4: pide un nombre, crea el archivo vacío en la carpeta del panel y lo abre en el editor."""
	panel = ctx.activo
	proveedor = panel.proveedor
	if panel.es_lista() or not proveedor.capacidades.escribir:
		anuncios.anunciar(_("Aquí no se pueden crear archivos"), anuncios.RESULTADO)
		return
	from app.services import plantillas as servicio_plantillas
	from app.ui.dialogos.nombre import pedir_nombre

	# 2.0 (10.13): «Plantilla:» con «Archivo vacío» y las de serie y de la persona.
	try:
		lista = servicio_plantillas.disponibles()
	except OSError:
		log.warning("No se pudieron leer las plantillas de archivo nuevo", exc_info=True)
		lista = []
	eleccion = [0]
	opciones = [_("Archivo vacío"), *(p.titulo for p in lista)] if lista else []
	nombre = pedir_nombre(ctx.ventana, _("Crear archivo"), _("&Nombre del archivo nuevo:"), "", seleccionar_sin_extension=False,
		opciones=opciones, etiqueta_opciones=_("&Plantilla:"), eleccion=eleccion,
		ayuda_opciones=_("Contenido inicial del archivo. Si el nombre no lleva extensión, se pone la de la plantilla."))
	if not nombre:
		return
	plantilla = lista[eleccion[0] - 1] if lista and 0 < eleccion[0] <= len(lista) else None
	nombre = servicio_plantillas.nombre_final(nombre, plantilla)
	ruta = proveedor.unir(panel.ruta, nombre)

	def trabajo(_tarea) -> bool:
		if proveedor.existe(ruta):
			return False
		datos = servicio_plantillas.contenido(plantilla, nombre)
		with proveedor.transaccion(), proveedor.abrir_escritura(ruta, len(datos)) as flujo:
			if datos:
				flujo.write(datos)
		return True

	def listo(creado: bool) -> None:
		anuncios.anunciar(_("Archivo creado: {n}").format(n=nombre) if creado else
			_("«{n}» ya existía: se abre sin cambiarlo").format(n=nombre), anuncios.RESULTADO)
		panel.refrescar(al_terminar=lambda ok: panel.ir_a_nombre(nombre))
		editar_ruta(ctx, panel, proveedor, ruta)

	def fallo(error: BaseException) -> None:
		if not isinstance(error, TareaCancelada):
			anuncios.anunciar(_("No se pudo crear «{n}»: {e}").format(n=nombre, e=_mensaje(error)), anuncios.ESENCIAL)

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="crear-archivo")


# ── Comparar ────────────────────────────────────────────────────────────────────


def archivos_a_comparar(ctx) -> tuple[tuple[base.Proveedor, str], tuple[base.Proveedor, str]] | None:
	"""Los dos marcados del panel activo o el del cursor de cada panel (sección 8.19)."""
	activo, pasivo = ctx.activo, ctx.pasivo
	marcadas = activo.marcadas()
	if len(marcadas) == 2:
		pares = [(activo.proveedor, marcadas[0]), (activo.proveedor, marcadas[1])]
	else:
		pares = [(activo.proveedor, activo.cursor()), (pasivo.proveedor, pasivo.cursor() if pasivo is not None else None)]
	if any(e is None or e.es_carpeta or e.es_superior for _p, e in pares):
		anuncios.anunciar(_("Para comparar hacen falta dos archivos: el del cursor de cada panel o dos marcados en un panel"),
			anuncios.RESULTADO)
		return None
	(prov_a, a), (prov_b, b) = pares
	if prov_a is prov_b and a.ruta == b.ruta:
		anuncios.anunciar(_("Es el mismo archivo en los dos lados"), anuncios.RESULTADO)
		return None
	return (prov_a, a.ruta), (prov_b, b.ruta)


def comparar_archivos(ctx) -> None:
	"""Compara por contenido dos archivos en la ventana de diferencias (o con el programa externo)."""
	pareja = archivos_a_comparar(ctx)
	if pareja is None:
		return
	from app.ui.ventanas import diferencias

	diferencias.abrir(ctx.ventana, *pareja)


# ── Para otros bloques ──────────────────────────────────────────────────────────


def abrir_archivo(padre: wx.Window | None, proveedor: base.Proveedor, ruta: str, editar: bool = False) -> wx.Frame:
	"""Abre el visor interno (o el editor interno si ``editar``) sobre un archivo de cualquier proveedor.

	No depende del panel activo ni de las asociaciones: la usa, por ejemplo, el
	diálogo de resultados de búsqueda (bloque B). La configuración y el gestor
	de tareas se buscan en ``padre`` y sus antecesores (la ventana principal).
	Se llama en el hilo de la interfaz; la lectura del archivo va en un hilo.
	Devuelve la ventana abierta (``VentanaVisor`` o ``VentanaEditor``).
	"""
	from app.ui.ventanas import editor, visor

	config, tareas = visor.configuracion_de(padre), visor.tareas_de(padre)
	if editar:
		return editor.abrir(padre, proveedor, ruta, config, tareas)
	return visor.abrir(padre, proveedor, ruta, config, tareas)
