# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque E: renombrado múltiple (Ctrl+M), atributos y fechas, y crear enlace.

Cada manejador recoge los elementos de trabajo del panel activo, abre su
diálogo (``app/ui/dialogos/e_*.py``) y deja el trabajo en el disco a una
operación del motor (renombrar y atributos, con progreso, cola y resumen) o a
una tarea corta (crear un enlace). No hay órdenes casilla en este bloque, así
que no hay funciones de estado.

Listas de resultados (búsqueda, cesta, vista plana): sus rutas son locales y
absolutas, pero ``ProveedorResultados.padre`` devuelve ``None``; por eso aquí
se renombra con el proveedor local y luego se actualizan las rutas de la lista.
"""

from __future__ import annotations

import builtins
import logging
import os

from app.services import formato, renombrado
from app.services.operaciones.atributos import OperacionAtributos
from app.services.operaciones.renombrar import OperacionRenombrar
from app.services.vfs import resolver
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _trabajo(ctx, verbo: str):
	"""Elementos de trabajo del panel activo, o ``None`` (con aviso) si no hay ninguno (sección 5.4)."""
	elementos = ctx.activo.elementos_trabajo()
	if not elementos:
		anuncios.anunciar(_("No hay elementos para {v}").format(v=verbo), anuncios.RESULTADO)
		return None
	return elementos


def _preferencias_lectura(config):
	"""Lectura por columnas de la vista previa con las mismas preferencias que la lista de archivos."""
	from app.ui.accesibilidad.composicion import PreferenciasLectura

	def leer() -> PreferenciasLectura:
		return PreferenciasLectura(
			numero_fila=bool(config.obtener("accesibilidad.leer_numero_fila")),
			cabecera=bool(config.obtener("accesibilidad.leer_cabecera")),
			contenido=bool(config.obtener("accesibilidad.leer_contenido")),
		)

	return leer


# ── Renombrado múltiple ──────────────────────────────────────────────────────

def renombrado_multiple(ctx) -> None:
	from app.ui.dialogos import e_renombrado

	panel = ctx.activo
	entradas = _trabajo(ctx, _("renombrar"))
	if entradas is None:
		return
	proveedor = panel.proveedor
	if not proveedor.capacidades.escribir:
		anuncios.anunciar(_("Aquí no se puede renombrar"), anuncios.RESULTADO)
		return
	es_lista = proveedor.esquema == "resultados"
	proveedor_trabajo = resolver.proveedor_local() if es_lista else proveedor
	elementos = renombrado.elementos_desde_entradas(entradas, proveedor_trabajo)
	existentes = None
	if not es_lista and elementos:
		existentes = {elementos[0].carpeta_ruta: [e.nombre for e in panel.entradas() if not e.es_superior]}
	pares = e_renombrado.pedir_renombrado(
		ctx.ventana, elementos, existentes, validar_windows=proveedor_trabajo.esquema == "local",
		leer_preferencias=_preferencias_lectura(ctx.config))
	if not pares:
		return
	operacion = OperacionRenombrar(proveedor_trabajo, pares, descripcion=descripcion_lote(panel, len(pares)))
	cursor = panel.cursor()
	nuevo_cursor = next((n for r, n in pares if cursor is not None and r == cursor.ruta), None)

	def tras(op) -> None:
		if es_lista:
			actualizar_lista(proveedor, pares, proveedor_trabajo)
		if nuevo_cursor:
			panel.refrescar(al_terminar=lambda ok: panel.ir_a_nombre(nuevo_cursor))
		else:
			panel.refrescar()

	ctx.lanzar(operacion, al_terminar=tras)


def descripcion_lote(panel, cantidad: int) -> str:
	"""«Renombrar 12 elementos en D:\\Fotos» (lo dice el resumen y «Deshacer»)."""
	que = formato.plural(cantidad, _("{n} elemento"), _("{n} elementos"))
	return _("Renombrar {q} en {c}").format(q=que, c=panel.mostrar_ruta())


def actualizar_lista(proveedor, pares: list[tuple[str, str]], local) -> None:
	"""Cambia en la lista de resultados las rutas de los que se renombraron de verdad."""
	if not hasattr(proveedor, "rutas"):
		return
	cambios: dict[str, str] = {}
	for ruta, nuevo in pares:
		destino = local.unir(local.padre(ruta) or "", nuevo)
		if os.path.lexists(destino) and (ruta.casefold() == destino.casefold() or not os.path.lexists(ruta)):
			cambios[ruta.casefold()] = destino
	proveedor.rutas = [cambios.get(r.casefold(), r) for r in proveedor.rutas]


# ── Atributos y fechas ───────────────────────────────────────────────────────

def atributos(ctx) -> None:
	from app.ui.dialogos import e_atributos

	panel = ctx.activo
	entradas = _trabajo(ctx, _("cambiar atributos"))
	if entradas is None:
		return
	proveedor = panel.proveedor
	capacidades = proveedor.capacidades
	local = proveedor.esquema in ("local", "resultados")
	if not (capacidades.atributos or capacidades.permisos or local):
		anuncios.anunciar(_("Este origen no admite atributos, fechas ni permisos"), anuncios.RESULTADO)
		return
	cambios = e_atributos.pedir_atributos(
		ctx.ventana, entradas, atributos=capacidades.atributos, fechas=local or capacidades.permisos,
		creacion=local, permisos=capacidades.permisos)
	if cambios is None:
		return
	if cambios.vacio:
		anuncios.anunciar(_("No ha cambiado nada"), anuncios.RESULTADO)
		return
	operacion = OperacionAtributos(proveedor, entradas, cambios)
	ctx.lanzar(operacion, al_terminar=lambda op: panel.refrescar())


# ── Crear enlace ─────────────────────────────────────────────────────────────

def _carpeta_del_enlace(ctx) -> str | None:
	"""Carpeta propuesta para el enlace: la del otro panel si está en el disco; si no, la del activo."""
	for panel in (ctx.pasivo, ctx.activo):
		if panel is not None and panel.es_local() and not panel.es_lista():
			carpeta = panel.ruta_local()
			if carpeta:
				return carpeta
	return None


def propuesta_enlace(carpeta: str, destino: str, nombre: str) -> str:
	"""Ruta del enlace por defecto: el mismo nombre en ``carpeta``; si está ocupado, «nombre (2)»."""
	from app.services.operaciones import nombres

	ruta = os.path.join(carpeta, nombre)
	if os.path.lexists(ruta) or os.path.normcase(ruta) == os.path.normcase(destino):
		ruta = os.path.join(carpeta, nombres.nombre_libre(nombre, lambda n: os.path.lexists(os.path.join(carpeta, n))))
	return ruta


def crear_enlace(ctx) -> None:
	from app.services.windows import enlaces
	from app.ui.dialogos import e_enlace

	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is None or entrada.es_superior:
		anuncios.anunciar(_("Ponga el cursor en el archivo o la carpeta a la que apuntará el enlace"), anuncios.RESULTADO)
		return
	destino = panel.proveedor.ruta_local(entrada.ruta) if panel.es_local() or panel.es_lista() else None
	carpeta = _carpeta_del_enlace(ctx)
	if not destino or not carpeta:
		anuncios.anunciar(_("Los enlaces solo se pueden crear en el disco local"), anuncios.RESULTADO)
		return
	respuesta = e_enlace.pedir_enlace(ctx.ventana, destino, propuesta_enlace(carpeta, destino, entrada.nombre),
		enlaces.UNION if entrada.es_carpeta and not enlaces.puede_crear_simbolicos() else enlaces.SIMBOLICO)
	if respuesta is None:
		return
	tipo, enlace, destino = respuesta
	lanzar_enlace(ctx, tipo, enlace, destino, entrada.es_carpeta)


def lanzar_enlace(ctx, tipo: str, enlace: str, destino: str, es_carpeta: bool) -> None:
	"""Crea el enlace en un hilo; si faltan privilegios para el simbólico, ofrece una unión o un acceso directo."""
	from app.services.windows import enlaces

	def trabajo(_tarea):
		enlaces.crear(tipo, enlace, destino)
		return enlace

	def listo(_ruta) -> None:
		anuncios.anunciar(_("{t} creado: {n}").format(t=enlaces.nombre_tipo(tipo), n=os.path.basename(enlace)), anuncios.RESULTADO)
		carpeta = os.path.normcase(os.path.dirname(enlace))
		for panel in (ctx.activo, ctx.pasivo):
			local = panel.ruta_local() if panel is not None and panel.es_local() else None
			if local and os.path.normcase(local.rstrip("\\")) == carpeta.rstrip("\\"):
				panel.refrescar()

	def fallo(error: BaseException) -> None:
		if isinstance(error, enlaces.SinPrivilegios):
			ofrecer_alternativa(ctx, enlace, destino, es_carpeta)
			return
		mensaje = getattr(error, "mensaje", "") or str(error)
		log.info("No se pudo crear el enlace %s: %s", enlace, mensaje)
		anuncios.anunciar(_("No se pudo crear el enlace: {m}").format(m=mensaje), anuncios.ESENCIAL)

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="crear-enlace")


def ofrecer_alternativa(ctx, enlace: str, destino: str, es_carpeta: bool) -> None:
	"""Explica cómo activar el modo de desarrollador y ofrece crear una unión (carpetas) o un acceso directo."""
	from app.services.windows import enlaces
	from app.ui.accesibilidad import dialogos

	opciones: list[tuple[str, str]] = []
	if es_carpeta:
		opciones.append((_("Crear una &unión"), enlaces.UNION))
	opciones.append((_("Crear un &acceso directo"), enlaces.ACCESO_DIRECTO))
	opciones.append((_("&Cancelar"), ""))
	eleccion = dialogos.elegir_opcion(ctx.ventana, enlaces.mensaje_sin_privilegios(), _("Crear enlace"), [t for t, _tipo in opciones])
	if eleccion is None or not opciones[eleccion][1]:
		return
	tipo = opciones[eleccion][1]
	nuevo = enlace if tipo != enlaces.ACCESO_DIRECTO or enlace.lower().endswith(".lnk") else enlace + ".lnk"
	motivo = enlaces.problema(tipo, nuevo, destino)
	if motivo:
		dialogos.mostrar_error(ctx.ventana, motivo, _("Crear enlace"))
		return
	lanzar_enlace(ctx, tipo, nuevo, destino, es_carpeta)

