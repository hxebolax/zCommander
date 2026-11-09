# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Navegación: abrir, subir, raíz, historial, ir a, cambiar de panel, igualar, intercambiar, cancelar, menús."""

from __future__ import annotations

import builtins
import logging
import os

from app.services import formato
from app.services.vfs import base, resolver
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def abrir(ctx) -> None:
	"""Intro: carpeta, «..», comprimido, asociación, programa o archivo con su programa (sección 8.1)."""
	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is None:
		return
	if entrada.es_superior:
		subir(ctx)
		return
	# 2.0 (9.1): un proveedor puede pedir que Intro ejecute una orden suya con la ruta de la fila
	# (en «Red», entrar en la unidad o el recurso con el proveedor local y escritura, tras reconectar).
	orden_propia = getattr(panel.proveedor, "orden_al_abrir", None)
	if callable(orden_propia):
		id_orden = orden_propia(entrada)
		if id_orden:
			ctx.ejecutar_orden(id_orden, argumento=entrada.ruta)
			return
	if entrada.es_carpeta:
		panel.ir_a(entrada.ruta)
		return
	# 2.0 (14.9): asociaciones internas antes que las de la persona (.zcplugin, .zcbackup...).
	from app.ui.acciones import archivos

	interna = archivos.orden_interna(entrada.nombre)
	if interna:
		ruta = panel.proveedor.ruta_local(entrada.ruta) or entrada.ruta
		ctx.ejecutar_orden(interna, argumento=ruta)
		return
	if ctx.config.obtener("paneles.entrar_en_comprimidos"):
		if resolver.es_comprimido(entrada.nombre):
			_entrar_en_comprimido(ctx, panel, entrada)
			return
		from app.plugins import registro

		complemento = registro.complemento_de_comprimido(entrada.nombre)
		if complemento:
			_entrar_con_complemento(ctx, panel, entrada, complemento)
			return
	_abrir_archivo(ctx, panel, entrada)


def _entrar_en_comprimido(ctx, panel, entrada) -> None:
	try:
		proveedor = resolver.abrir_comprimido(panel.proveedor, entrada.ruta)
	except base.NoAdmitido:
		# 2.0 (14.5): la fábrica dice que no es lo que parece (comprobación por contenido): se abre con su programa.
		_abrir_archivo(ctx, panel, entrada)
		return
	except base.ErrorArchivos as error:
		anuncios.anunciar(error.mensaje, anuncios.ESENCIAL)
		return
	panel.ir_a("", proveedor)


def _entrar_con_complemento(ctx, panel, entrada, id_complemento: str) -> None:
	"""Intro en un comprimido de un complemento sin activar: como una orden con su continuación (3.4)."""
	import threading

	from app.plugins import cargador

	ruta, proveedor = panel.ruta, panel.proveedor
	contador = getattr(ctx.ventana, "contador_ordenes", 0)
	activacion = cargador.asegurar_activo(id_complemento)

	def avisar() -> None:
		if not activacion.done():
			anuncios.anunciar(_("Cargando el complemento..."), anuncios.RESULTADO, sonido="plugin.cargando")

	if not activacion.done():
		temporizador = threading.Timer(0.3, lambda: cargador.planificar(avisar))
		temporizador.daemon = True
		temporizador.start()

	def continuar() -> None:
		try:
			ok = bool(activacion.result())
		except Exception:  # noqa: BLE001 - cancelado al cerrar
			ok = False
		if not ok:
			_abrir_archivo(ctx, panel, entrada)
			return
		if panel.ruta != ruta or panel.proveedor is not proveedor or getattr(ctx.ventana, "contador_ordenes", 0) != contador:
			anuncios.anunciar(_("No se abrió {n}: cambió de carpeta mientras se cargaba el complemento").format(n=entrada.nombre),
				anuncios.ESENCIAL)
			return
		_entrar_en_comprimido(ctx, panel, entrada)

	activacion.add_done_callback(lambda _f: cargador.planificar(continuar))


def _abrir_archivo(ctx, panel, entrada) -> None:
	from app.services import asociaciones, variables
	from app.services.windows import shell_basico
	from app.ui.accesibilidad import dialogos

	local = panel.proveedor.ruta_local(entrada.ruta)
	orden = asociaciones.orden_para(entrada.nombre, "abrir")
	if local is None:
		# Comprimido o servidor: se extrae a un temporal (en un hilo) y se abre ese.
		# Un programa que viene de fuera del disco se confirma SIEMPRE, aunque
		# «Confirmar antes de ejecutar» esté desactivado (diseño 14): un Intro
		# dentro de un ZIP descargado no debe bastar para ejecutar lo que traiga.
		if not orden and shell_basico.es_ejecutable(entrada.nombre):
			import wx

			pregunta = _("«{n}» está en {o}. Se extraerá a una carpeta temporal y se ejecutará. ¿Ejecutarlo?").format(
				n=entrada.nombre, o=panel.mostrar_ruta())
			if dialogos.confirmar(ctx.ventana, pregunta, _("Ejecutar"), peligroso=True) != wx.ID_YES:
				return

		def extraer(_tarea):
			return panel.proveedor.extraer_temporal(entrada.ruta)

		def listo(ruta_temporal):
			from app.services.vfs import temporales
			from app.ui.acciones import archivos

			temporales.vigilados.vigilar(ruta_temporal, panel.proveedor, entrada.ruta, archivos.ofrecer_actualizar_desde(ctx.ventana))
			_lanzar(ctx, ruta_temporal, orden, panel)

		ctx.tareas.enviar(extraer, al_terminar=listo, al_fallar=lambda e: anuncios.anunciar(str(e), anuncios.ESENCIAL),
			nombre="extraer-temporal")
		return
	if not orden and shell_basico.es_ejecutable(entrada.nombre) and shell_basico.exige_confirmacion(
			entrada.nombre, bool(ctx.config.obtener("general.confirmar_ejecutar"))):
		import wx

		if dialogos.confirmar(ctx.ventana, _("¿Ejecutar «{n}»?").format(n=entrada.nombre), _("Ejecutar"), peligroso=True) != wx.ID_YES:
			return
	_lanzar(ctx, local, orden, panel)
	del variables


def _lanzar(ctx, ruta: str, orden: str | None, panel) -> None:
	from app.services import variables
	from app.services.windows import shell_basico

	def al_error(error):
		import wx

		wx.CallAfter(anuncios.anunciar, _("No se pudo abrir: {e}").format(e=error), anuncios.ESENCIAL)

	if orden:
		otro = ctx.pasivo
		valores = variables.Valores(cursor=ruta, carpeta=panel.ruta_local() or os.path.dirname(ruta),
			otra_carpeta=otro.ruta_local() or "", cursor_otro=(otro.cursor().ruta if otro.cursor() and otro.es_local() else ""),
			trabajo=[e.ruta for e in panel.elementos_trabajo()] if panel.es_local() else [ruta])
		shell_basico.lanzar(variables.expandir_directo(orden, valores), os.path.dirname(ruta), al_error)
		return
	shell_basico.abrir(ruta, al_error, carpeta=os.path.dirname(ruta))
	anuncios.anunciar(_("Abriendo {n}").format(n=os.path.basename(ruta)), anuncios.DETALLE)


def subir(ctx) -> None:
	panel = ctx.activo
	if panel.es_lista():
		panel.cerrar_lista()
		return
	if _subir_a_red(panel):
		return
	padre = panel.proveedor.padre(panel.ruta) if panel.ruta or panel.proveedor.esquema != "local" else None
	if padre is None and panel.proveedor.contenedor is not None:
		# Raíz de un comprimido: se vuelve a la carpeta que lo contiene, con el cursor en él.
		contenedor, ruta_archivo = panel.proveedor.contenedor
		panel.ir_a(contenedor.padre(ruta_archivo) or "", contenedor, contenedor.nombre(ruta_archivo))
		return
	if padre is None:
		anuncios.anunciar(_("Está en la raíz"), anuncios.RESULTADO)
		return
	panel.ir_a(padre)


def _subir_a_red(panel) -> bool:
	"""2.0 (9.1, 9.3): Retroceso en ``\\\\servidor\\recurso`` lleva a ``\\\\servidor`` de «Red» (cursor en el
	recurso) y en ``\\\\servidor`` a la raíz «Red» (cursor en el servidor). Verdadero si lo hizo."""
	if panel.proveedor.esquema != "local":
		return False
	ruta = (panel.ruta or "").rstrip("\\")
	if not ruta.startswith("\\\\") or ruta.startswith("\\\\?"):
		return False
	partes = [p for p in ruta.lstrip("\\").split("\\") if p]
	if len(partes) not in (1, 2):
		return False
	from app.services.vfs import red as vfs_red

	proveedor = vfs_red.proveedor_red()
	servidor = "\\\\" + partes[0]
	if len(partes) == 2:
		panel.ir_a(servidor, proveedor, partes[1])
	else:
		panel.ir_a("", proveedor, proveedor.nombre(servidor))
	return True


def entrar(ctx) -> None:
	entrada = ctx.activo.cursor()
	if entrada is not None and (entrada.es_carpeta or resolver.es_comprimido(entrada.nombre)):
		abrir(ctx)


def raiz(ctx) -> None:
	panel = ctx.activo
	if panel.proveedor.contenedor is not None and not panel.ruta:
		subir(ctx)
		return
	panel.ir_a(panel.proveedor.raiz(panel.ruta))


def carpeta_personal(ctx) -> None:
	ctx.activo.ir_a(os.path.expanduser("~"), resolver.proveedor_local())


def atras(ctx) -> None:
	if not ctx.activo.atras():
		anuncios.anunciar(_("No hay carpeta anterior"), anuncios.RESULTADO)


def adelante(ctx) -> None:
	if not ctx.activo.adelante():
		anuncios.anunciar(_("No hay carpeta siguiente"), anuncios.RESULTADO)


def ir_a_carpeta(ctx) -> None:
	from app.ui.accesibilidad import dialogos

	panel = ctx.activo
	if ctx.argumento:
		# 2.0 (10.1): con argumento (macro, «zc ir_a_carpeta», tecla global) no hay diálogo.
		texto = str(ctx.argumento)
	else:
		texto = dialogos.pedir_texto(ctx.ventana, _("&Ruta:"), _("Ir a la carpeta"), panel.mostrar_ruta(),
			ayuda=_("Ruta de una carpeta o archivo, %VARIABLE%, ~, \\\\servidor\\recurso o ftp:// y sftp://."))
		if not texto:
			return
		_anotar_argumento(ctx, texto)

	def resolver_en_hilo(_tarea):
		return resolver.abrir_ruta(texto, base.Ubicacion(panel.proveedor, panel.ruta))

	def listo(resultado):
		proveedor, ruta, cursor = resultado
		panel.ir_a(ruta, proveedor, cursor)

	ctx.tareas.enviar(resolver_en_hilo, al_terminar=listo,
		al_fallar=lambda e: anuncios.anunciar(getattr(e, "mensaje", str(e)), anuncios.ESENCIAL), nombre="ir-a",
		tiempo_maximo=float(ctx.config.obtener("general.tiempo_unidad_s")))


def _panel_con_foco(ventana):
	"""Panel que contiene el foco (su lista, su filtro o su vista), o ``None``."""
	import wx

	foco = wx.Window.FindFocus()
	if foco is None:
		return None
	for panel in ventana.todos_los_paneles():
		if foco is panel or panel.IsDescendant(foco):
			return panel
	return None


def cambiar_panel(ctx) -> None:
	"""Tab: pasa al panel opuesto al que tiene el foco.

	Se parte del panel con el foco, no de ``ctx.activo``: una vista
	(Información, Vista rápida o Árbol) no hace activo a su panel, porque las
	órdenes de panel siguen siendo las del otro lado. Si se partiera del activo,
	Tab desde la vista del lado pasivo «iría» a ese mismo lado y el foco no
	saldría nunca de la vista.
	"""
	origen = _panel_con_foco(ctx.ventana) or ctx.activo
	otro = ctx.ventana.panel_opuesto(origen)
	lado = ctx.ventana.lado(otro.lado)
	if not lado.IsShown() or not ctx.ventana.divisor.IsShown():
		anuncios.anunciar(_("El otro panel está oculto"), anuncios.RESULTADO, sonido="panel.oculto")
		return
	anuncios.anunciar("", anuncios.DETALLE, sonido="panel.cambiar")
	otro.enfocar()


def intercambiar_paneles(ctx) -> None:
	izquierdo, derecho = ctx.izquierdo, ctx.derecho
	ruta_i, prov_i, ruta_d, prov_d = izquierdo.ruta, izquierdo.proveedor, derecho.ruta, derecho.proveedor
	izquierdo.ir_a(ruta_d, prov_d, forzar_aqui=True)
	derecho.ir_a(ruta_i, prov_i, forzar_aqui=True)
	anuncios.anunciar(_("Paneles intercambiados"), anuncios.RESULTADO)


def igualar_paneles(ctx) -> None:
	ctx.pasivo.ir_a(ctx.activo.ruta, ctx.activo.proveedor)
	anuncios.anunciar(_("El otro panel va a {r}").format(r=ctx.activo.mostrar_ruta()), anuncios.RESULTADO)


def abrir_en_lado(ctx) -> None:
	destino = ctx.izquierdo if ctx.param == "izquierdo" else ctx.derecho
	entrada = ctx.activo.cursor()
	if entrada is not None and entrada.es_carpeta and not entrada.es_superior:
		destino.ir_a(entrada.ruta, ctx.activo.proveedor)
	else:
		destino.ir_a(ctx.activo.ruta, ctx.activo.proveedor)


def volver_a_leer(ctx) -> None:
	panel = ctx.objetivo
	# 2.0: «Volver a leer» de verdad. Un proveedor con caché de listados (Nubes) la olvida,
	# y las columnas de complementos de esta carpeta se vuelven a pedir (un comentario
	# nuevo no cambia el tamaño ni la fecha del archivo, que es lo que mira su caché).
	invalidar = getattr(panel.proveedor, "invalidar", None)
	if callable(invalidar):
		try:
			invalidar(panel.ruta)
		except Exception:  # noqa: BLE001 - un proveedor de complemento roto no impide volver a leer
			log.warning("No se pudo invalidar la caché de %s", panel.mostrar_ruta(), exc_info=True)
	if not panel.es_lista():
		from app.plugins import registro

		registro.olvidar_columnas(carpeta=panel.ruta)
	panel.refrescar(conservar=True)
	anuncios.anunciar(_("Actualizado"), anuncios.RESULTADO)


def ir_linea_ordenes(ctx) -> None:
	if ctx.activo.pasar_busqueda_a_linea():
		return
	ctx.ventana.enfocar_linea()


def _anotar_argumento(ctx, valor) -> None:
	"""El diálogo pasa su valor final al grabador de macros antes de cerrarse (10.1)."""
	try:
		ctx.servicio("grabador").anotar_argumento(valor)
	except (KeyError, AttributeError):
		log.debug("Sin grabador de macros", exc_info=True)


def cancelar(ctx) -> None:
	"""Escape en el panel (2.0, 10.1): hace lo primero que se pueda de esta lista.

	1) detener la macro en curso; 2) cancelar la lectura, el cálculo o el
	descubrimiento de equipos del panel; 3) quitar el filtro rápido; 4) detener
	la orden lanzada desde la línea de órdenes (se anuncia «Orden detenida»).
	"""
	try:
		if ctx.servicio("macros").detener():
			anuncios.anunciar(_("Macro detenida"), anuncios.RESULTADO)
			return
	except (KeyError, AttributeError):
		log.debug("Sin servicio de macros", exc_info=True)
	if ctx.activo.cancelar_o_quitar():
		return
	detener = getattr(ctx.ventana, "detener_orden", None)
	if callable(detener):
		detener()


def abrir_menus(ctx) -> None:
	ctx.ventana.abrir_barra_menus()


def describir_carpeta(ctx, panel) -> str:
	return _("{r}, {c}").format(r=panel.mostrar_ruta(), c=formato.recuento(
		sum(1 for e in panel.entradas() if e.es_carpeta and not e.es_superior),
		sum(1 for e in panel.entradas() if not e.es_carpeta)))
