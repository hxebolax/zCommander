# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes de archivo del núcleo: copiar, mover, crear carpeta, eliminar, duplicar, renombrar, deshacer..."""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services import formato
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.eliminar import OperacionEliminar
from app.services.operaciones.modelo import Politica
from app.services.operaciones.renombrar import OperacionRenombrar
from app.services.vfs import resolver, rutas
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _trabajo(ctx, verbo: str):
	"""Elementos de trabajo del panel activo o None (con aviso) si no hay."""
	elementos = ctx.activo.elementos_trabajo()
	if not elementos:
		anuncios.anunciar(_("No hay elementos para {v}").format(v=verbo), anuncios.RESULTADO)
		return None
	return elementos


def _resumen(elementos) -> str:
	carpetas = sum(1 for e in elementos if e.es_carpeta)
	archivos = len(elementos) - carpetas
	texto = formato.recuento(carpetas, archivos)
	bytes_ = sum(e.tamano for e in elementos if not e.es_carpeta and e.tamano > 0)
	return f"{texto} ({formato.tamano_legible(bytes_)})" if bytes_ else texto


#: Asociaciones internas (2.0, 14.9): extensión → orden que se ejecuta con ``argumento`` = la ruta.
#: Van antes que las de la persona; así ningún bloque edita este archivo: cada uno solo
#: hace que su orden acepte la ruta como argumento.
ABRIR_INTERNO: dict[str, str] = {
	"zcplugin": "complemento_instalar",
	"zcbackup": "copia_restaurar",
	"zcperfil": "perfil_importar",
	"zcsonidos": "sonidos_paquetes",
	"zcmacro": "macros",
	"zcteclas": "mapa_teclas",
}


def orden_interna(nombre: str) -> str | None:
	"""Orden que abre ``nombre`` por Intro: asociación interna o valor ``zc:<orden>`` de ``asociaciones.json``."""
	extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
	if extension in ABRIR_INTERNO:
		return ABRIR_INTERNO[extension]
	from app.services import asociaciones

	orden = asociaciones.orden_para(nombre, "abrir") or ""
	if orden.startswith("zc:"):
		return orden[3:].strip() or None
	return None


def _confirmar_alcance(ctx, verbo: str) -> bool:
	"""Hay marcas y el cursor no está en ninguna: se pregunta (sección 5.4).

	2.0 (10.12): con la casilla «No volver a preguntar» (confirmación ``marcas_cursor``);
	silenciada, se actúa sobre los marcados sin preguntar.
	"""
	panel = ctx.activo
	if not panel.cursor_fuera_de_marcas():
		return True
	from app.services import confirmaciones

	if not confirmaciones.debe_preguntar(ctx.config, "marcas_cursor"):
		return True
	from app.ui.accesibilidad import dialogos

	n = len(panel.marcadas())
	eleccion, silenciar = dialogos.elegir_con_casilla(
		ctx.ventana, _("Hay {n} marcados y el cursor está en otro elemento. ¿{v} los {n} marcados?").format(n=n, v=verbo), verbo,
		[_("&Sí"), _("&No")],
	)
	if eleccion == 0 and silenciar:
		confirmaciones.silenciar(ctx.config, "marcas_cursor")
	return eleccion == 0


# ── Copiar y mover ───────────────────────────────────────────────────────────

def copiar(ctx) -> None:
	_copiar_o_mover(ctx, mover=False)


def mover(ctx) -> None:
	_copiar_o_mover(ctx, mover=True)


def _destino_propuesto(ctx, elementos) -> str:
	pasivo = ctx.pasivo
	carpeta = pasivo.mostrar_ruta() if not pasivo.es_lista() else ""
	if len(elementos) == 1 and carpeta:
		return pasivo.proveedor.unir(pasivo.ruta, elementos[0].nombre) if pasivo.es_local() else carpeta
	return carpeta


def _copiar_o_mover(ctx, mover: bool) -> None:
	verbo = _("Mover") if mover else _("Copiar")
	elementos = _trabajo(ctx, verbo.lower())
	if elementos is None or not _confirmar_alcance(ctx, verbo):
		return
	from app.ui.dialogos.copiar import DialogoCopiar

	argumento = ctx.argumento if isinstance(getattr(ctx, "argumento", None), dict) else {}
	propuesto = str(argumento.get("destino") or _destino_propuesto(ctx, elementos))
	if argumento.get("sin_dialogo") and argumento.get("destino"):
		# 2.0 (10.1): una macro con «sin_dialogo» copia sin preguntar, con sus valores.
		lanzar_copia(ctx, elementos, propuesto, _opciones_argumento(ctx.config, argumento), mover)
		return
	resumen = _("{v} {r} a:").format(v=verbo, r=_resumen(elementos))
	dialogo = DialogoCopiar(ctx.ventana, resumen, propuesto, mover=mover, configuracion=ctx.config)
	try:
		if dialogo.ShowModal() != wx.ID_OK:
			return
		texto, opciones, en_cola = dialogo.destino(), dialogo.opciones(), dialogo.en_cola
		_anotar_argumento(ctx, {"destino": texto, "politica": str(opciones.politica), "verificar": bool(opciones.verificar),
			"sin_dialogo": True})
	finally:
		dialogo.Destroy()
		ctx.activo.enfocar()
	lanzar_copia(ctx, elementos, texto, opciones, mover, en_cola)


def _anotar_argumento(ctx, valor) -> None:
	"""El diálogo pasa su valor final al grabador de macros antes de cerrarse (10.1)."""
	try:
		ctx.servicio("grabador").anotar_argumento(valor)
	except (KeyError, AttributeError):
		log.debug("Sin grabador de macros", exc_info=True)


def _opciones_argumento(config, argumento: dict) -> OpcionesCopia:
	"""Opciones de copia de una macro: las de la configuración con lo que diga el argumento (10.1)."""
	import dataclasses

	opciones = opciones_por_defecto(config)
	cambios = {}
	if argumento.get("politica"):
		try:
			cambios["politica"] = Politica(str(argumento["politica"]))
		except ValueError:
			log.warning("Política de conflictos desconocida en una macro: %s", argumento["politica"])
	if "verificar" in argumento:
		cambios["verificar"] = bool(argumento["verificar"])
	return dataclasses.replace(opciones, **cambios) if cambios else opciones


def lanzar_copia(
	ctx, elementos, texto_destino: str, opciones: OpcionesCopia, mover: bool, en_cola: bool = False, origen=None,
) -> None:
	"""Interpreta el destino escrito y lanza la operación (también la usan pegar y soltar).

	:param origen: proveedor de ``elementos``; por defecto, el del panel activo
		(pegar y soltar desde el Explorador pasan el proveedor local).
	"""
	panel, pasivo = ctx.activo, ctx.pasivo
	origen = origen or panel.proveedor
	texto = texto_destino.strip()
	if not texto:
		return
	nombre_nuevo = ""

	def lanzar(proveedor, carpeta, nombre: str = "") -> None:
		_avisar_comprimido(ctx, proveedor)
		operacion = OperacionCopiar(origen, list(elementos), proveedor, carpeta, opciones, mover=mover, nombre_nuevo=nombre)
		ctx.lanzar(operacion, en_cola)

	if pasivo.proveedor.mostrar(pasivo.ruta) == texto:
		lanzar(pasivo.proveedor, pasivo.ruta)
		return
	if "://" in texto or panel.proveedor.esquema == "local" or os.path.isabs(texto):
		destino_local = None if "://" in texto else rutas.normalizar(texto if os.path.isabs(texto) else os.path.join(panel.ruta_local() or "", texto))
		if destino_local is not None and resolver.es_comprimido(destino_local) and os.path.isfile(destino_local):
			destino_local = None  # copiar dentro de un comprimido existente
			texto = rutas.normalizar(texto if os.path.isabs(texto) else os.path.join(panel.ruta_local() or "", texto))
		if destino_local is not None and not os.path.isdir(destino_local):
			if len(elementos) == 1 and not destino_local.endswith("\\") and os.path.isdir(os.path.dirname(destino_local)):
				nombre_nuevo = os.path.basename(destino_local)
				destino_local = os.path.dirname(destino_local)
			elif not os.path.exists(destino_local):
				try:
					os.makedirs(destino_local, exist_ok=True)
				except OSError as error:
					anuncios.anunciar(str(error), anuncios.ESENCIAL)
					return
		if destino_local is not None:
			lanzar(resolver.proveedor_local(), destino_local, nombre_nuevo)
			return
		# Red o comprimido: abrir_ruta puede conectar o leer, así que va en un hilo.
		from app.ui.panel_archivos import resolver_en_hilo

		def fallo(error: BaseException) -> None:
			anuncios.anunciar(getattr(error, "mensaje", None) or str(error), anuncios.ESENCIAL)

		resolver_en_hilo(ctx.ventana.tareas, texto, None, lambda r: lanzar(r[0], r[1]), fallo)
		return
	lanzar(pasivo.proveedor, pasivo.proveedor.unir(pasivo.ruta, texto))


def _avisar_comprimido(ctx, proveedor) -> None:
	"""Aviso de que escribir en un comprimido lo reconstruye entero (diseño 8.15).

	2.0 (10.12): es la confirmación silenciable ``comprimido_escritura``: sale
	hasta que la persona marca «No volver a preguntar».
	"""
	if not proveedor.capacidades.escribir or not resolver.es_comprimido(getattr(proveedor, "ruta_archivo", "") or ""):
		return
	from app.services import confirmaciones

	if not confirmaciones.debe_preguntar(ctx.config, "comprimido_escritura"):
		return
	from app.ui.accesibilidad import dialogos

	_eleccion, silenciar = dialogos.elegir_con_casilla(ctx.ventana, _(
		"Copiar, mover, renombrar o eliminar dentro de un comprimido lo vuelve a escribir entero al terminar. "
		"Con comprimidos grandes puede tardar, y ese último paso no se puede cancelar."),
		_("Escribir en un comprimido"), [_("&Aceptar")])
	if silenciar:
		confirmaciones.silenciar(ctx.config, "comprimido_escritura")


def opciones_por_defecto(config) -> OpcionesCopia:
	return OpcionesCopia(
		politica=Politica(config.obtener("operaciones.politica_conflicto")),
		verificar=bool(config.obtener("operaciones.verificar")),
		conservar_fechas=bool(config.obtener("operaciones.conservar_fechas")),
		copiar_enlaces=bool(config.obtener("operaciones.copiar_enlaces")),
		carpetas_vacias=bool(config.obtener("operaciones.copiar_carpetas_vacias")),
		lista_conflictos=bool(config.obtener("operaciones.lista_conflictos")),
		tamano_bloque=int(config.obtener("operaciones.tamano_bloque_kb")) * 1024,
	)


def duplicar(ctx) -> None:
	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is None or entrada.es_superior:
		return
	from app.services.operaciones import nombres
	from app.ui.dialogos.nombre import pedir_nombre

	propuesto = nombres.nombre_copia(entrada.nombre, lambda n: n in {e.nombre for e in panel.entradas()})
	nombre = pedir_nombre(ctx.ventana, _("Duplicar"), _("&Nombre de la copia:"), propuesto)
	if not nombre:
		return
	operacion = OperacionCopiar(panel.proveedor, [entrada], panel.proveedor, panel.ruta, opciones_por_defecto(ctx.config),
		nombre_nuevo=nombre)
	ctx.lanzar(operacion)


# ── Crear, renombrar, eliminar ──────────────────────────────────────────────────

def crear_carpeta(ctx) -> None:
	panel = ctx.activo
	if not panel.proveedor.capacidades.escribir or panel.es_lista():
		anuncios.anunciar(_("Aquí no se pueden crear carpetas"), anuncios.RESULTADO)
		return
	from app.ui.dialogos.nombre import pedir_nombre

	if getattr(ctx, "argumento", None):
		nombre = str(ctx.argumento)  # 2.0 (10.1): una macro trae el nombre
	else:
		nombre = pedir_nombre(ctx.ventana, _("Crear carpeta"), _("&Nombre de la carpeta:"), "", permitir_ruta=True)
		if not nombre:
			return
		_anotar_argumento(ctx, nombre)
	ruta = panel.ruta
	for parte in nombre.replace("/", "\\").split("\\"):
		if parte:
			ruta = panel.proveedor.unir(ruta, parte)
	primera = nombre.replace("/", "\\").split("\\")[0]

	def trabajo(_tarea):
		# Los niveles que aún no existen se anotan ANTES de crearlos: deshacer
		# «a\b\c» quita las tres, de dentro afuera, si siguen vacías.
		from app.services.operaciones.deshacer import pasos_carpetas_nuevas

		pasos = pasos_carpetas_nuevas(ruta) if panel.es_local() else []
		panel.proveedor.crear_carpeta(ruta)
		return pasos

	def listo(pasos) -> None:
		if panel.es_local():
			from app.services.operaciones.deshacer import AccionDeshacer, Paso

			ctx.servicio("deshacer").registrar(AccionDeshacer(_("Crear la carpeta {n}").format(n=nombre),
				pasos or [Paso("quitar_carpeta", ruta)]))
		anuncios.anunciar(_("Carpeta creada: {n}").format(n=nombre), anuncios.RESULTADO, sonido="op.carpeta_creada")
		panel.refrescar(al_terminar=lambda ok: panel.ir_a_nombre(primera))

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: anuncios.anunciar(getattr(e, "mensaje", str(e)), anuncios.ESENCIAL),
		nombre="crear-carpeta")


def renombrar(ctx) -> None:
	panel = ctx.activo
	entrada = panel.cursor()
	if entrada is None or entrada.es_superior:
		return
	from app.ui.dialogos.nombre import pedir_nombre

	nombre = pedir_nombre(ctx.ventana, _("Renombrar"), _("&Nombre nuevo:"), entrada.nombre,
		seleccionar_sin_extension=bool(ctx.config.obtener("paneles.seleccionar_sin_extension")) and not entrada.es_carpeta)
	if not nombre or nombre == entrada.nombre:
		return
	operacion = OperacionRenombrar(panel.proveedor, [(entrada.ruta, nombre)])

	def tras(op) -> None:
		if not op.errores:
			panel.refrescar(al_terminar=lambda ok: panel.ir_a_nombre(nombre))

	ctx.lanzar(operacion, al_terminar=tras)


def eliminar(ctx) -> None:
	papelera = bool(ctx.config.obtener("general.usar_papelera"))
	_eliminar(ctx, papelera)


def eliminar_definitivo(ctx) -> None:
	_eliminar(ctx, False)


def _eliminar(ctx, papelera: bool) -> None:
	panel = ctx.activo
	if panel.proveedor.esquema == "red":
		# 2.0 (9.1): F8 y Supr no desconectan; se dice qué orden lo hace (el texto de ``ProveedorRed.eliminar``).
		anuncios.anunciar(_("En Red no se elimina nada. Para quitar una unidad o conexión, use Desconectar unidad de red."),
			anuncios.RESULTADO)
		return
	elementos = _trabajo(ctx, _("eliminar"))
	if elementos is None:
		return
	if not panel.proveedor.capacidades.escribir and panel.proveedor.esquema != "resultados":
		anuncios.anunciar(_("Aquí no se puede eliminar"), anuncios.RESULTADO)
		return
	if papelera and panel.proveedor.esquema in ("local", "resultados"):
		from app.services.windows import papelera as modulo_papelera

		if not all(modulo_papelera.admite_papelera(e.ruta) for e in elementos):
			# Es una eliminación definitiva que la persona no pidió: Intro pulsa «Cancelar».
			if not _confirmar_eliminar(
				ctx.ventana, _("Esta unidad no tiene papelera (o la ruta es demasiado larga): los archivos se eliminarán definitivamente."),
				peligroso=True, boton=_("Eliminar &definitivamente"),
			):
				return
			papelera = False
	elif papelera:
		papelera = False
	confirmar = ctx.config.obtener("general.confirmar_eliminar" if papelera else "general.confirmar_eliminar_definitivo")
	from app.services import confirmaciones

	if confirmar or (panel.cursor_fuera_de_marcas() and confirmaciones.debe_preguntar(ctx.config, "marcas_cursor")):
		pregunta = (_("¿Enviar a la papelera {r}?") if papelera else _("¿Eliminar DEFINITIVAMENTE {r}? No se puede deshacer.")).format(
			r=_resumen(elementos))
		if not _confirmar_eliminar(ctx.ventana, pregunta, peligroso=not papelera):
			return
	else:
		anuncios.anunciar(_("{a} a la papelera").format(a=panel.describir_alcance()) if papelera else
			_("Eliminando {a}").format(a=panel.describir_alcance()), anuncios.ESENCIAL)
	indice = panel.lista_archivos.cursor_indice()
	for otro in ctx.ventana.todos_los_paneles():
		if any(e.es_carpeta and otro.vigila_dentro_de(e.ruta) for e in elementos):
			otro.dejar_de_vigilar()

	def tras(_op) -> None:
		panel.refrescar(al_terminar=lambda ok: panel.lista_archivos.mover_cursor(min(indice, len(panel.entradas()) - 1)))

	ctx.lanzar(OperacionEliminar(panel.proveedor, list(elementos), papelera=papelera), al_terminar=tras)


# ── Menú contextual, portapapeles de texto, ventana ──────────────────────────────

def menu_contextual(ctx) -> None:
	from app.ui import ordenes

	ventana = ctx.ventana
	menu = wx.Menu()
	for elemento in ordenes.MENU_CONTEXTUAL:
		if elemento is None:
			menu.AppendSeparator()
			continue
		orden = ordenes.POR_ID[elemento]
		etiqueta = _(ordenes.ETIQUETAS_CONTEXTUAL.get(elemento, orden.etiqueta))
		tecla = ventana.mapa_teclas.primera_tecla(elemento)
		item = menu.Append(wx.ID_ANY, etiqueta + (f"\t{tecla}" if tecla else ""), _(orden.ayuda))
		menu.Bind(wx.EVT_MENU, lambda _e, i=elemento: wx.CallAfter(ventana.ejecutar_orden, i), item)
	lista = ctx.activo.lista_archivos
	indice = max(0, lista.cursor_indice())
	rect = lista.GetItemRect(indice) if lista.GetItemCount() else wx.Rect(0, 0, 0, 0)
	try:
		lista.PopupMenu(menu, wx.Point(rect.x + 20, rect.y + rect.height))
	finally:
		menu.Destroy()


def _copiar_texto(texto: str) -> bool:
	from app.ui.dialogo_texto import copiar_al_portapapeles

	return copiar_al_portapapeles(texto)


def copiar_rutas(ctx) -> None:
	elementos = _trabajo(ctx, _("copiar"))
	if elementos and _copiar_texto("\r\n".join(e.ruta for e in elementos)):
		anuncios.anunciar(formato.plural(len(elementos), _("{n} ruta copiada"), _("{n} rutas copiadas")), anuncios.RESULTADO,
			sonido="portapapeles.texto")


def copiar_nombres(ctx) -> None:
	elementos = _trabajo(ctx, _("copiar"))
	if elementos and _copiar_texto("\r\n".join(e.nombre for e in elementos)):
		anuncios.anunciar(formato.plural(len(elementos), _("{n} nombre copiado"), _("{n} nombres copiados")), anuncios.RESULTADO,
			sonido="portapapeles.texto")


def copiar_ruta_carpeta(ctx) -> None:
	if _copiar_texto(ctx.activo.mostrar_ruta()):
		anuncios.anunciar(_("Ruta copiada: {r}").format(r=ctx.activo.mostrar_ruta()), anuncios.RESULTADO, sonido="portapapeles.texto")


def operaciones(ctx) -> None:
	ctx.ventana.mostrar_operaciones()


def deshacer(ctx) -> None:
	from app.ui.accesibilidad import dialogos

	registro = ctx.servicio("deshacer")
	accion = registro.ultima()
	if accion is None:
		anuncios.anunciar(_("No hay nada que deshacer"), anuncios.RESULTADO)
		return
	if dialogos.confirmar(ctx.ventana, _("¿Deshacer: {d}?").format(d=accion.descripcion), _("Deshacer")) != wx.ID_YES:
		return
	registro.sacar_ultima()

	def trabajo(_tarea):
		return registro.deshacer(accion)

	def listo(resultado) -> None:
		texto = _("Deshecho: {d}").format(d=accion.descripcion)
		if resultado.omitidos:
			texto += _(". No se pudo deshacer {n} porque cambiaron").format(n=len(resultado.omitidos))
		anuncios.anunciar(texto, anuncios.ESENCIAL)
		for panel in (ctx.activo, ctx.pasivo):
			panel.refrescar()

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda e: anuncios.anunciar(str(e), anuncios.ESENCIAL), nombre="deshacer")


def guardar_sesion(ctx) -> None:
	ctx.ventana.guardar_sesion()


def salir(ctx) -> None:
	ctx.ventana.salir()


def ofrecer_actualizar_desde(ventana):
	"""``al_cambiar`` para ``temporales.vigilados``: ofrece subir el temporal cambiado a su comprimido o servidor."""

	def al_cambiar(ruta_local: str, proveedor, ruta: str) -> None:
		from app.ui.accesibilidad import dialogos

		pregunta = _("«{n}» ha cambiado. ¿Actualizarlo en {d}?").format(n=os.path.basename(ruta_local), d=proveedor.mostrar(proveedor.padre(ruta) or ""))
		if dialogos.confirmar(ventana, pregunta, _("Actualizar")) != wx.ID_YES:
			return
		local = resolver.proveedor_local()
		opciones = OpcionesCopia(politica=Politica.SOBRESCRIBIR, conservar_fechas=False)
		operacion = OperacionCopiar(local, [local.info(ruta_local)], proveedor, proveedor.padre(ruta) or "", opciones,
			nombre_nuevo=proveedor.nombre(ruta))
		# 2.0 (10.1): la llamada directa dice en qué orden se lanzó (la lee lanzar_operacion).
		operacion.orden_origen = "editar"
		ventana.lanzar_operacion(operacion)

	return al_cambiar


def _confirmar_eliminar(padre, pregunta: str, peligroso: bool, boton: str = "") -> bool:
	"""Botones «Eliminar» y «Cancelar» (diseño 8.7): dicen la acción, no «Sí» y «No».

	En la eliminación definitiva, Intro pulsa «Cancelar», para que un Intro
	accidental no borre nada. También la usa el aviso de unidad sin papelera
	(``boton`` = «Eliminar definitivamente»).
	"""
	from app.ui.accesibilidad import dialogos

	dialogo = dialogos.DialogoMensaje(padre, pregunta, _("Eliminar"), opciones=[boton or _("&Eliminar"), _("&Cancelar")],
		icono=wx.ICON_WARNING if peligroso else wx.ICON_QUESTION)
	ids = list(dialogo.ids_opciones)
	if peligroso and len(ids) > 1:
		boton = dialogo.FindWindowById(ids[1])
		if boton is not None:
			boton.SetDefault()
			boton.SetFocus()
	resultado = dialogos._mostrar(dialogo)  # noqa: SLF001 - mismo cierre y foco que el resto de diálogos
	return bool(ids) and resultado == ids[0]
