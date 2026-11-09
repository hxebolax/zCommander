# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque B: buscar archivos, comparar y sincronizar carpetas, tamaño, vista plana y cesta.

Cada manejador se ejecuta en el hilo de la interfaz y manda lo lento a
``ctx.tareas`` (buscar, comparar, sumar, recorrer) o al motor de operaciones
(sincronizar). Las tareas largas de un panel se vinculan a él
(``vincular_tarea``) para que Escape las cancele.

Restricción de la sección 20.2: «Enviar al panel», la vista plana y la cesta
solo trabajan con rutas del disco local.
"""

from __future__ import annotations

import builtins
import logging
import os
import weakref

import wx

from app.services import diferencias_carpetas as dc
from app.services import formato, tamano_carpetas
from app.services.diferencias_carpetas import Criterio
from app.services.recorrido import recorrer
from app.services.vfs import base, resolver
from app.ui import anuncios

log = logging.getLogger(__name__)

#: El diálogo de búsqueda abierto (no modal; solo uno a la vez).
_busqueda_abierta: weakref.ReferenceType | None = None


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _mensaje(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or str(error) or error.__class__.__name__


def _es_cancelacion(error: BaseException) -> bool:
	from app.core.tareas import TareaCancelada

	return isinstance(error, TareaCancelada)


def _panel_activo(ctx):
	"""El panel activo en ESTE momento (un diálogo no modal puede sobrevivir a un cambio de panel)."""
	return getattr(ctx.ventana, "activo", None) or ctx.activo


def _maximo(ctx) -> int:
	try:
		return int(ctx.config.obtener("busqueda.max_resultados"))
	except Exception:  # noqa: BLE001 - una clave que falta no impide la orden: valor de fábrica
		log.warning("No se pudo leer busqueda.max_resultados", exc_info=True)
		return 100000


# ── Buscar archivos (Alt+F7) ────────────────────────────────────────────────

def buscar_archivos(ctx) -> None:
	global _busqueda_abierta
	abierto = _busqueda_abierta() if _busqueda_abierta is not None else None
	if abierto:
		abierto.Raise()
		abierto.campo_nombres.SetFocus()
		return
	from app.ui.dialogos.b_buscar import DialogoBuscar

	panel = ctx.activo
	texto = panel.mostrar_ruta() if panel.ruta or panel.es_lista() else (panel.ruta_local() or "")
	datos_panel = (panel.proveedor, panel.ruta, panel.mostrar_ruta())

	def al_cerrar() -> None:
		global _busqueda_abierta
		_busqueda_abierta = None
		destino = _panel_activo(ctx)
		if destino is not None:
			wx.CallAfter(destino.enfocar)

	dialogo = DialogoBuscar(
		ctx.ventana, ctx.config, ctx.tareas, texto, datos_panel,
		al_ir=lambda r: _ir_a_resultado(ctx, r),
		al_ver=lambda r, editar: _ver_resultado(ctx, r, editar),
		al_enviar=lambda titulo, rutas: _enviar_al_panel(ctx, titulo, rutas),
		al_cerrar=al_cerrar,
	)
	_busqueda_abierta = weakref.ref(dialogo)
	dialogo.Show()


def _ir_a_resultado(ctx, resultado, orden: str = "") -> None:
	"""Lleva el panel activo a la carpeta del resultado con el cursor en él; con ``orden``, la ejecuta después."""
	panel = _panel_activo(ctx)
	proveedor = resultado.proveedor if not resultado.es_local else resolver.proveedor_local()
	carpeta = resultado.carpeta if not resultado.es_local else os.path.dirname(resultado.ruta_local)
	nombre = resultado.entrada.nombre

	def listo(ok: bool) -> None:
		if not ok:
			return
		panel.ir_a_nombre(nombre)
		if orden:
			ctx.ventana.ejecutar_orden(orden)
		else:
			panel.enfocar()

	panel.ir_a(carpeta, proveedor, cursor=nombre, al_terminar=listo)


def _ver_resultado(ctx, resultado, editar: bool) -> None:
	"""F3 o F4 en los resultados: abre el visor o el editor sin mover el panel ni cerrar la búsqueda."""
	from app.ui.acciones import visor

	if resultado.es_local:
		visor.abrir_archivo(ctx.ventana, resolver.proveedor_local(), resultado.ruta_local, editar=editar)
	else:
		visor.abrir_archivo(ctx.ventana, resultado.proveedor, resultado.entrada.ruta, editar=editar)


def _enviar_al_panel(ctx, titulo: str, rutas: list[str]) -> None:
	panel = _panel_activo(ctx)
	panel.abrir_lista(titulo, rutas)
	panel.enfocar()


# ── Comparar carpetas (Ctrl+F10) ─────────────────────────────────────────────

_CRITERIOS_COMPARAR = (Criterio.NOMBRE, Criterio.FECHA, Criterio.TAMANO, Criterio.CONTENIDO)


def _paneles_comparables(ctx) -> bool:
	izquierdo, derecho = ctx.izquierdo, ctx.derecho
	if izquierdo is None or derecho is None:
		anuncios.anunciar(_("Hacen falta los dos paneles"), anuncios.RESULTADO)
		return False
	if izquierdo.proveedor is derecho.proveedor and izquierdo.ruta == derecho.ruta:
		anuncios.anunciar(_("Los dos paneles muestran la misma carpeta"), anuncios.RESULTADO)
		return False
	return True


def comparar_carpetas(ctx) -> None:
	if not _paneles_comparables(ctx):
		return
	from app.ui.accesibilidad import dialogos

	eleccion = dialogos.elegir_opcion(
		ctx.ventana, _("¿Cómo se comparan los archivos de los dos paneles?"), _("Comparar carpetas"),
		[_("&Nombre"), _("Nombre y &fecha"), _("Nombre, fecha y &tamaño"), _("C&ontenido")],
	)
	ctx.activo.enfocar()
	if eleccion is None:
		return
	ejecutar_comparacion(ctx, _CRITERIOS_COMPARAR[eleccion])


def ejecutar_comparacion(ctx, criterio: Criterio):
	"""Compara los dos paneles en un hilo y marca en cada uno lo que falta en el otro o es más reciente."""
	izquierdo, derecho = ctx.izquierdo, ctx.derecho
	lado_i = (izquierdo.proveedor, izquierdo.ruta)
	lado_d = (derecho.proveedor, derecho.ruta)
	# Con nombre, fecha o tamaño basta lo ya listado; el contenido se lee en el hilo.
	entradas_i = [e for e in izquierdo.entradas() if not e.es_superior and not e.es_carpeta]
	entradas_d = [e for e in derecho.entradas() if not e.es_superior and not e.es_carpeta]

	def trabajo(tarea):
		return comparar_listados(lado_i, entradas_i, lado_d, entradas_d, criterio, tarea.token)

	def listo(diferencias) -> None:
		marcas_i, marcas_d = dc.marcas(diferencias)
		for panel, marcas in ((izquierdo, marcas_i), (derecho, marcas_d)):
			panel.desmarcar_todo()
			if marcas:
				panel.marcar(lambda e, m=marcas: not e.es_carpeta and e.nombre.casefold() in m)
		anuncios.anunciar(dc.anuncio_marcas(len(marcas_i), len(marcas_d)), anuncios.RESULTADO)

	def fallo(error: BaseException) -> None:
		if _es_cancelacion(error):
			return
		log.error("Falló la comparación de carpetas", exc_info=error)
		anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)

	if criterio == Criterio.CONTENIDO:
		anuncios.anunciar(_("Comparando el contenido"), anuncios.RESULTADO)
	tarea = ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="comparar-carpetas")
	if tarea is not None:
		ctx.activo.vincular_tarea(tarea, _("Comparar carpetas"))
	return tarea


def comparar_listados(lado_i, entradas_i, lado_d, entradas_d, criterio: Criterio, cancelacion=None) -> list[dc.Diferencia]:
	"""Diferencias entre dos listados ya hechos (sin subcarpetas): lo que hace Ctrl+F10.

	Reutiliza el cálculo de ``diferencias_carpetas`` con un proveedor que
	devuelve los listados del panel, para no volver a leer las carpetas.
	"""
	return dc.comparar((_Listado(lado_i[0], entradas_i), lado_i[1]), (_Listado(lado_d[0], entradas_d), lado_d[1]),
		criterio, subcarpetas=False, solo_archivos=True, cancelacion=cancelacion)


class _Listado(base.Proveedor):
	"""Proveedor de solo lectura que repite un listado ya hecho y lee del proveedor real."""

	def __init__(self, real: base.Proveedor, entradas) -> None:
		super().__init__()
		self.real = real
		self.esquema = real.esquema
		self._entradas = list(entradas)

	def listar(self, ruta, cancelacion=None):
		return list(self._entradas)

	def info(self, ruta):
		return self.real.info(ruta)

	def padre(self, ruta):
		return self.real.padre(ruta)

	def unir(self, carpeta, nombre):
		return self.real.unir(carpeta, nombre)

	def raiz(self, ruta):
		return self.real.raiz(ruta)

	def mostrar(self, ruta):
		return self.real.mostrar(ruta)

	def abrir_lectura(self, ruta):
		return self.real.abrir_lectura(ruta)


# ── Sincronizar (Ctrl+Mayús+F10) ─────────────────────────────────────────────

def sincronizar(ctx) -> None:
	from app.ui.dialogos.b_sincronizar import DialogoSincronizar

	lados = []
	for panel in (ctx.izquierdo, ctx.derecho):
		lados.append((panel.proveedor, panel.ruta, panel.mostrar_ruta()) if panel is not None and not panel.es_lista() else None)
	dialogo = DialogoSincronizar(ctx.ventana, ctx.config, ctx.tareas, lados[0], lados[1])
	try:
		aceptado = dialogo.ShowModal() == wx.ID_OK
		operacion = dialogo.operacion
	finally:
		dialogo.Destroy()
		ctx.activo.enfocar()
	if aceptado and operacion is not None:
		ctx.lanzar(operacion)


# ── Tamaño de carpetas (Mayús+Espacio y Alt+Mayús+Intro) ─────────────────────

def tamano(ctx) -> None:
	panel = ctx.objetivo
	if ctx.param == "todas":
		carpetas = tamano_carpetas.carpetas_calculables(panel.entradas())
		if not carpetas:
			anuncios.anunciar(_("No hay carpetas en este panel"), anuncios.RESULTADO)
			return
	else:
		trabajo = panel.elementos_trabajo()
		carpetas = tamano_carpetas.carpetas_calculables(trabajo)
		if not carpetas:
			archivos = [e for e in trabajo if not e.es_carpeta]
			if archivos:
				total = sum(e.tamano for e in archivos if e.tamano > 0)
				que = archivos[0].nombre if len(archivos) == 1 else formato.plural(len(archivos), _("{n} archivo"), _("{n} archivos"))
				anuncios.anunciar(f"{que}: {formato.tamano_legible(total)}", anuncios.RESULTADO)
			else:
				anuncios.anunciar(_("No hay carpetas para calcular"), anuncios.RESULTADO)
			return
	calcular_tamanos(ctx, panel, carpetas)


def calcular_tamanos(ctx, panel, carpetas):
	"""Suma las carpetas en un hilo y va poniendo el tamaño en la columna Tamaño. Escape lo cancela."""
	proveedor_panel = panel.proveedor
	ruta_panel = panel.ruta
	descripcion = _("Calcular el tamaño")

	def mismo_sitio() -> bool:
		return bool(panel) and panel.proveedor is proveedor_panel and panel.ruta == ruta_panel

	def al_lote(lote) -> None:
		# Desde el hilo: los tamaños llegan a la interfaz por lotes (como mucho 4 por segundo).
		from app.core.tareas import ejecutar_en_interfaz

		ejecutar_en_interfaz(poner, list(lote))

	def poner(lote) -> None:
		if not mismo_sitio():
			return  # se fue de la carpeta: los tamaños se olvidan (sección 8.20)
		for resultado in lote:
			panel.fijar_tamano(resultado.nombre, resultado.totales.bytes)

	def trabajo(tarea):
		proveedor = proveedor_panel.clonar()
		try:
			return tamano_carpetas.calcular(proveedor, carpetas, tarea.token, al_lote=al_lote, al_avanzar=tarea.progresar)
		finally:
			if proveedor is not proveedor_panel:
				proveedor.cerrar()

	def al_progresar(progreso) -> None:
		if progreso.total:
			ctx.estado(_("Calculando el tamaño: {h} de {t}, {n}").format(h=int(progreso.hecho) + 1, t=int(progreso.total), n=progreso.texto))

	def listo(resultados) -> None:
		ctx.estado("")
		if not resultados:
			return
		anuncios.anunciar(tamano_carpetas.describir_varias(resultados), anuncios.RESULTADO, sonido="tamano.calculado")

	def fallo(error: BaseException) -> None:
		ctx.estado("")
		if _es_cancelacion(error):
			return
		log.error("Falló el cálculo del tamaño de las carpetas", exc_info=error)
		anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)

	if len(carpetas) > 1:
		anuncios.anunciar(_("Calculando el tamaño de {c}").format(c=formato.plural(len(carpetas), _("{n} carpeta"), _("{n} carpetas"))),
			anuncios.NORMAL)
	tarea = ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, al_progresar=al_progresar, nombre=f"tamano-{panel.lado}")
	if tarea is not None:
		panel.vincular_tarea(tarea, descripcion)
	return tarea


# ── Vista plana (Ctrl+B) ─────────────────────────────────────────────────────

def _titulo_vista_plana(ruta: str) -> str:
	return _("Vista plana: {r}").format(r=ruta)


def _prefijo_vista_plana() -> str:
	return _("Vista plana") + ":"


def es_vista_plana(ctx) -> bool:
	panel = ctx.objetivo
	titulo = panel.es_lista() if panel is not None else None
	return bool(titulo) and titulo.startswith(_prefijo_vista_plana())


def vista_plana(ctx):
	panel = ctx.objetivo
	if es_vista_plana(ctx):
		panel.cerrar_lista()
		return None
	carpeta = panel.ruta_local() if panel.es_local() and not panel.es_lista() else None
	if not carpeta:
		anuncios.anunciar(_("La vista plana solo funciona en carpetas del disco"), anuncios.RESULTADO)
		return None
	maximo = _maximo(ctx)
	mostrar = panel.mostrar_ruta()

	def trabajo(tarea):
		local = resolver.proveedor_local()
		rutas: list[str] = []
		limitado = False
		for elemento in recorrer(local, carpeta, tarea.token, incluir_carpetas=False):
			rutas.append(elemento.entrada.ruta)
			if len(rutas) >= maximo:
				limitado = True
				break
		return rutas, limitado

	def listo(resultado) -> None:
		rutas, limitado = resultado
		if not panel or panel.ruta_local() != carpeta or panel.es_lista():
			return  # el panel ya está en otro sitio
		panel.abrir_lista(_titulo_vista_plana(mostrar), rutas)
		texto = _("Vista plana: {n}").format(n=formato.plural(len(rutas), _("{n} archivo"), _("{n} archivos")))
		if limitado:
			texto += _(" (se llegó al máximo)")
		anuncios.anunciar(texto, anuncios.RESULTADO)

	def fallo(error: BaseException) -> None:
		if _es_cancelacion(error):
			return
		log.error("Falló la vista plana de %s", carpeta, exc_info=error)
		anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)

	anuncios.anunciar(_("Leyendo las subcarpetas"), anuncios.NORMAL)
	tarea = ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre=f"vista-plana-{panel.lado}")
	if tarea is not None:
		panel.vincular_tarea(tarea, _("Vista plana"))
	return tarea


# ── Cesta ────────────────────────────────────────────────────────────────────

def _titulo_cesta() -> str:
	return _("Cesta")


def cesta_agregar(ctx) -> None:
	panel = ctx.activo
	elementos = panel.elementos_trabajo()
	if not elementos:
		anuncios.anunciar(_("No hay elementos"), anuncios.RESULTADO)
		return
	rutas = [panel.proveedor.ruta_local(e.ruta) for e in elementos] if panel.proveedor.esquema in ("local", "resultados") else []
	locales = [r for r in rutas if r]
	if not locales:
		anuncios.anunciar(_("La cesta solo admite elementos del disco"), anuncios.ESENCIAL)
		return
	cesta = ctx.servicio("cesta")
	nuevos = cesta.anadir(locales)
	if nuevos:
		texto = _("{a}; la cesta tiene {n}").format(
			a=formato.plural(nuevos, _("{n} añadido"), _("{n} añadidos")), n=len(cesta))
	else:
		texto = _("Ya estaban en la cesta; tiene {n}").format(n=len(cesta))
	anuncios.anunciar(texto, anuncios.ESENCIAL)


def cesta_abrir(ctx):
	cesta = ctx.servicio("cesta")
	rutas = cesta.rutas()
	if not rutas:
		anuncios.anunciar(_("La cesta está vacía"), anuncios.RESULTADO)
		return None
	panel = ctx.objetivo

	def trabajo(tarea):
		# Comprobar la existencia puede tocar unidades de red: en un hilo.
		faltan = []
		for indice, ruta in enumerate(rutas):
			if indice % 256 == 0:
				base.comprobar(tarea.token)
			if not os.path.exists(ruta):
				faltan.append(ruta)
		return faltan

	def listo(faltan) -> None:
		if faltan:
			cesta.quitar(faltan)
			anuncios.anunciar(_("Se quitaron de la cesta {n} que ya no existen").format(n=len(faltan)), anuncios.ESENCIAL)
		if not len(cesta):
			anuncios.anunciar(_("La cesta está vacía"), anuncios.RESULTADO)
			return
		if panel.es_lista() == _titulo_cesta():
			panel.cerrar_lista()
		panel.abrir_lista(_titulo_cesta(), cesta.rutas())
		panel.enfocar()

	def fallo(error: BaseException) -> None:
		if _es_cancelacion(error):
			return
		log.error("No se pudo abrir la cesta", exc_info=error)
		anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)

	return ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre="cesta-abrir")


def cesta_vaciar(ctx) -> None:
	cesta = ctx.servicio("cesta")
	if not len(cesta):
		anuncios.anunciar(_("La cesta ya está vacía"), anuncios.RESULTADO)
		return
	from app.ui.accesibilidad import dialogos

	respuesta = dialogos.confirmar(ctx.ventana, _("¿Vaciar la cesta? Tiene {n}. Los archivos no se borran.").format(
		n=formato.plural(len(cesta), _("{n} elemento"), _("{n} elementos"))), _("Vaciar la cesta"), peligroso=True)
	ctx.activo.enfocar()
	if respuesta != wx.ID_YES:
		return
	cesta.vaciar()
	for panel in (ctx.izquierdo, ctx.derecho):
		if panel is not None and panel.es_lista() == _titulo_cesta():
			panel.cerrar_lista()
	anuncios.anunciar(_("Cesta vaciada"), anuncios.RESULTADO)
