# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque C: comprimir, extraer, probar, sumas de comprobación, dividir y unir.

Cada manejador corre en el hilo de la interfaz: recoge los elementos de
trabajo, muestra su diálogo (``app/ui/dialogos/c_*.py``) y lanza la operación
de ``app/services/operaciones/comprimir.py`` con ``ctx.lanzar``. Nada de E/S
lenta aquí: abrir un comprimido, listarlo o leerlo ocurre dentro de la
operación, en su hilo. Al terminar, la ventana anuncia ``resumen()`` (nivel
esencial) y refresca los paneles afectados.
"""

from __future__ import annotations

import builtins
import logging
import os

import wx

from app.services import comprimir as servicio_comprimir
from app.services import dividir as servicio_dividir
from app.services import formato, sumas
from app.services.operaciones.comprimir import (
	OperacionComprimir,
	OperacionCrearSumas,
	OperacionDividir,
	OperacionExtraer,
	OperacionProbar,
	OperacionUnir,
	OperacionVerificarSumas,
)
from app.services.operaciones.copiar import OperacionCopiar
from app.services.vfs import base, resolver, rutas
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Utilidades ───────────────────────────────────────────────────────────────


def _avisar(texto: str) -> None:
	anuncios.anunciar(texto, anuncios.RESULTADO)


def _trabajo(ctx, verbo: str):
	elementos = ctx.activo.elementos_trabajo()
	if not elementos:
		_avisar(_("No hay elementos para {v}").format(v=verbo))
		return None
	return elementos


def _origen(panel) -> base.Proveedor:
	"""Proveedor del que se leen los elementos (las listas de resultados contienen rutas locales reales)."""
	if panel.proveedor.esquema == "resultados":
		return resolver.proveedor_local()
	return panel.proveedor


def _carpeta_local(panel) -> str | None:
	"""Carpeta del disco que muestra el panel, o None (comprimido, servidor o lista de resultados)."""
	if panel.es_lista() or not panel.es_local():
		return None
	return panel.ruta_local()


def _carpeta_destino(ctx) -> str:
	"""Carpeta propuesta como destino: la del otro panel si es del disco; si no, la del activo; si no, nada."""
	return _carpeta_local(ctx.pasivo) or _carpeta_local(ctx.activo) or ""


def _resumen(elementos) -> str:
	carpetas = sum(1 for e in elementos if e.es_carpeta)
	texto = formato.recuento(carpetas, len(elementos) - carpetas)
	bytes_ = sum(e.tamano for e in elementos if not e.es_carpeta and e.tamano > 0)
	return f"{texto} ({formato.tamano_legible(bytes_)})" if bytes_ else texto


def _ruta_absoluta(texto: str, base_: str) -> str:
	texto = texto.strip().strip('"')
	if not os.path.isabs(texto) and base_:
		texto = os.path.join(base_, texto)
	return rutas.normalizar(texto)


def _modal(ctx, dialogo: wx.Dialog) -> bool:
	"""Muestra el diálogo y devuelve el foco al panel; True si se aceptó."""
	try:
		return dialogo.ShowModal() == wx.ID_OK
	finally:
		ctx.activo.enfocar()


def _asegurar_carpeta(carpeta: str) -> bool:
	if os.path.isdir(rutas.con_prefijo_largo(carpeta)):
		return True
	try:
		os.makedirs(rutas.con_prefijo_largo(carpeta), exist_ok=True)
	except OSError as error:
		from app.services import errores

		anuncios.anunciar(errores.mensaje_para_usuario(error), anuncios.ESENCIAL)
		return False
	return True


def _es_comprimido(entrada) -> bool:
	return not entrada.es_carpeta and not entrada.es_superior and resolver.es_comprimido(entrada.nombre)


# ── Comprimir ────────────────────────────────────────────────────────────────


def _anotar_argumento(ctx, valor) -> None:
	"""El diálogo pasa su valor final al grabador de macros antes de cerrarse (2.0, 10.1)."""
	try:
		ctx.servicio("grabador").anotar_argumento(valor)
	except (KeyError, AttributeError):
		log.debug("Sin grabador de macros", exc_info=True)


def comprimir(ctx) -> None:
	"""Alt+F5: crea un comprimido con los elementos de trabajo (por defecto en el otro panel)."""
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos.c_comprimir import DialogoComprimir

	panel = ctx.activo
	elementos = _trabajo(ctx, _("comprimir"))
	if elementos is None:
		return
	carpeta = _carpeta_destino(ctx)
	nombre = servicio_comprimir.nombre_propuesto(elementos, panel.mostrar_ruta(), "zip")
	propuesto = os.path.join(carpeta, nombre) if carpeta else nombre
	# 2.0 (10.1): el argumento de una macro rellena el diálogo; con «sin_dialogo» no se muestra.
	argumento = ctx.argumento if isinstance(getattr(ctx, "argumento", None), dict) else {}
	if argumento.get("nombre"):
		propuesto = os.path.join(carpeta, str(argumento["nombre"])) if carpeta and not os.path.isabs(str(argumento["nombre"])) 			else str(argumento["nombre"])
	dialogo = DialogoComprimir(ctx.ventana, _("Comprimir {r}").format(r=_resumen(elementos)), propuesto,
		hay_carpetas=any(e.es_carpeta for e in elementos))
	try:
		if not argumento.get("sin_dialogo") and not _modal(ctx, dialogo):
			return
		texto, opciones, en_cola = dialogo.destino(), dialogo.opciones(), dialogo.en_cola
		if argumento.get("sin_dialogo") and argumento.get("variante") == "zstd" and opciones.formato == "zip":
			# 2.0 (8.6, 10.1): la macro reproduce también el ZIP con Zstandard. El cifrado AES no: necesita
			# una contraseña y la contraseña nunca se guarda en la macro (sin diálogo no hay quien la escriba).
			opciones.variante = "zstd"
		_anotar_argumento(ctx, {"nombre": texto, "formato": servicio_comprimir.formato_de(texto) or "",
			"variante": opciones.variante if opciones.formato == "zip" else "", "sin_dialogo": True})
	finally:
		dialogo.Destroy()
	destino = _ruta_absoluta(texto, carpeta or (_carpeta_local(panel) or ""))
	if not os.path.isabs(destino):
		dialogos.mostrar_error(ctx.ventana, _("El comprimido tiene que crearse en una carpeta del disco."), _("Comprimir"))
		return
	origen = _origen(panel)
	if opciones.por_elemento:
		if servicio_comprimir.formato_de(destino) is not None and not os.path.isdir(destino):
			destino = os.path.dirname(destino)
		if not _asegurar_carpeta(destino):
			return
		decision = _preguntar_si_existen(ctx, OperacionComprimir(origen, list(elementos), destino, opciones).destinos())
		if decision is None:
			return
		opciones.si_existe = decision
	else:
		if servicio_comprimir.formato_de(destino) != opciones.formato:
			destino += servicio_comprimir.extension(opciones.formato)
		if not _asegurar_carpeta(os.path.dirname(destino)):
			return
		if _dentro_de_los_origenes(origen, elementos, destino):
			dialogos.mostrar_error(ctx.ventana, _("El comprimido no puede guardarse dentro de lo que se comprime."), _("Comprimir"))
			return
		if os.path.exists(rutas.con_prefijo_largo(destino)):
			eleccion = dialogos.elegir_opcion(ctx.ventana, _("Ya existe {n}. ¿Qué quiere hacer?").format(n=os.path.basename(destino)),
				_("Comprimir"), [_("&Añadir al comprimido"), _("&Sustituirlo"), _("&Cancelar")])
			if eleccion not in (0, 1):
				return
			opciones.anadir = eleccion == 0
	if opciones.mover:
		pregunta = _("Al terminar se probará el comprimido y, si está bien, se borrarán DEFINITIVAMENTE los originales ({r}). "
			"¿Continuar?").format(r=_resumen(elementos))
		if dialogos.confirmar(ctx.ventana, pregunta, _("Mover al comprimido"), peligroso=True) != wx.ID_YES:
			return
	ctx.lanzar(OperacionComprimir(origen, list(elementos), destino, opciones), en_cola)


def _preguntar_si_existen(ctx, destinos: list[str]) -> str | None:
	"""Con «Un comprimido por cada elemento»: qué hacer con los que ya existen (una sola pregunta para todos).

	Devuelve ``""`` si no existe ninguno, una de ``SI_EXISTE`` o ``None`` si se cancela.
	Como con el comprimido único, nunca se añade a uno existente sin preguntar.
	"""
	from app.services.operaciones.comprimir import SI_EXISTE, botones_si_existe
	from app.ui.accesibilidad import dialogos

	existentes = [os.path.basename(r) for r in destinos if os.path.exists(rutas.con_prefijo_largo(r))]
	if not existentes:
		return ""
	if len(existentes) == 1:
		texto = _("Ya existe {n}. ¿Qué quiere hacer?").format(n=existentes[0])
	else:
		lista = ", ".join(existentes[:3])
		if len(existentes) > 3:
			lista += ", " + _("y {n} más").format(n=len(existentes) - 3)
		texto = _("Ya existen {k} de los comprimidos ({lista}). ¿Qué quiere hacer con ellos?").format(
			k=len(existentes), lista=lista)
	eleccion = dialogos.elegir_opcion(ctx.ventana, texto, _("Comprimir"), botones_si_existe())
	if eleccion is None or not 0 <= eleccion < len(SI_EXISTE):
		return None
	return SI_EXISTE[eleccion]


def _dentro_de_los_origenes(origen: base.Proveedor, elementos, destino: str) -> bool:
	if origen.esquema != "local":
		return False
	for entrada in elementos:
		local = origen.ruta_local(entrada.ruta) or entrada.ruta
		if rutas.normalizar(local).casefold() == destino.casefold():
			return True
		if entrada.es_carpeta and rutas.esta_dentro(destino, local):
			return True
	return False


# ── Extraer ──────────────────────────────────────────────────────────────────


def extraer(ctx) -> None:
	"""Alt+F9: extrae los comprimidos de trabajo (o, dentro de uno, lo marcado) al otro panel."""
	from app.ui.accesibilidad import dialogos
	from app.ui.acciones.archivos import opciones_por_defecto
	from app.ui.dialogos.c_comprimir import DialogoExtraer

	panel = ctx.activo
	elementos = _trabajo(ctx, _("extraer"))
	if elementos is None:
		return
	dentro = panel.proveedor.contenedor is not None
	archivos = [e for e in elementos if _es_comprimido(e)]
	if not dentro and not archivos:
		_avisar(_("No hay comprimidos entre los elementos de trabajo"))
		return
	if dentro and archivos and len(archivos) == len(elementos):
		dentro = False  # Comprimidos dentro de un comprimido: se extraen como comprimidos.
	que = elementos if dentro else archivos
	pasivo = ctx.pasivo
	propuesto = pasivo.mostrar_ruta() if not pasivo.es_lista() else (_carpeta_local(panel) or "")
	resumen = _("Extraer {r}").format(r=_resumen(que))
	argumento = ctx.argumento if isinstance(getattr(ctx, "argumento", None), dict) else {}
	if argumento.get("destino"):
		propuesto = str(argumento["destino"])
	dialogo = DialogoExtraer(ctx.ventana, resumen, propuesto, ctx.config, por_carpeta=len(que) > 1 and not dentro)
	try:
		if not argumento.get("sin_dialogo") and not _modal(ctx, dialogo):
			return
		texto, patron, politica = dialogo.destino(), dialogo.patron(), dialogo.politica()
		por_carpeta, contrasena, en_cola = dialogo.por_carpeta(), dialogo.contrasena(), dialogo.en_cola
		_anotar_argumento(ctx, {"destino": texto, "sin_dialogo": True})
	finally:
		dialogo.Destroy()
	opciones = opciones_por_defecto(ctx.config)
	opciones.patron, opciones.politica = patron, politica
	if not pasivo.es_lista() and texto == pasivo.mostrar_ruta():
		destino, carpeta = pasivo.proveedor, pasivo.ruta
	else:
		carpeta = _ruta_absoluta(texto, _carpeta_local(panel) or "")
		if "://" in texto or not os.path.isabs(carpeta):
			dialogos.mostrar_error(ctx.ventana, _("Escriba una carpeta del disco o elija el destino en el otro panel."), _("Extraer"))
			return
		if not _asegurar_carpeta(carpeta):
			return
		destino = resolver.proveedor_local()
	if dentro:
		fijar = getattr(panel.proveedor, "fijar_contrasena", None)
		if contrasena and callable(fijar):
			fijar(contrasena)
		opciones.subcarpeta_por_elemento = False
		ctx.lanzar(OperacionCopiar(panel.proveedor, list(que), destino, carpeta, opciones), en_cola)
		return
	ctx.lanzar(OperacionExtraer(_origen(panel), archivos, destino, carpeta, opciones, por_carpeta, contrasena), en_cola)


# ── Probar ───────────────────────────────────────────────────────────────────


def probar(ctx) -> None:
	"""Alt+Mayús+F9: lee los comprimidos de trabajo (o el comprimido en el que está el panel) comprobando sus CRC."""
	panel = ctx.activo
	elementos = panel.elementos_trabajo()
	archivos = [e for e in elementos if _es_comprimido(e)]
	if archivos:
		operacion = OperacionProbar(_origen(panel), [e.ruta for e in archivos])
	elif panel.proveedor.contenedor is not None:
		contenedor, ruta = panel.proveedor.contenedor
		operacion = OperacionProbar(contenedor, [ruta])
	else:
		_avisar(_("No hay comprimidos que probar"))
		return
	ctx.lanzar(operacion)


# ── Sumas de comprobación ────────────────────────────────────────────────────


def sumas_crear(ctx) -> None:
	"""Calcula sumas de los elementos de trabajo y las guarda (o copia la de un archivo al portapapeles)."""
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos.c_sumas import DialogoCrearSumas

	panel = ctx.activo
	elementos = _trabajo(ctx, _("calcular sus sumas"))
	if elementos is None:
		return
	un_archivo = len(elementos) == 1 and not elementos[0].es_carpeta
	carpeta = _carpeta_local(panel) or _carpeta_local(ctx.pasivo) or ""
	nombre = elementos[0].nombre if len(elementos) == 1 else (os.path.basename(panel.mostrar_ruta().rstrip("\\/")) or "sumas")
	dialogo = DialogoCrearSumas(ctx.ventana, _("Sumas de {r}").format(r=_resumen(elementos)), carpeta, nombre, un_archivo)
	try:
		if not _modal(ctx, dialogo):
			return
		algoritmo, uno_por_archivo = dialogo.algoritmo(), dialogo.uno_por_archivo()
		al_portapapeles, texto_carpeta, nombre_archivo = dialogo.al_portapapeles(), dialogo.carpeta(), dialogo.nombre_archivo()
	finally:
		dialogo.Destroy()
	destino = ""
	if not al_portapapeles:
		destino = _ruta_absoluta(texto_carpeta, carpeta)
		if not os.path.isabs(destino):
			dialogos.mostrar_error(ctx.ventana, _("Las sumas se guardan en una carpeta del disco."), _("Crear sumas de comprobación"))
			return
		if not _asegurar_carpeta(destino):
			return
	operacion = OperacionCrearSumas(_origen(panel), list(elementos), algoritmo.id, destino or carpeta, uno_por_archivo,
		nombre_archivo, guardar=not al_portapapeles)

	def al_terminar(op) -> None:
		if not al_portapapeles or not op.sumas:
			return
		from app.ui.dialogo_texto import copiar_al_portapapeles

		suma = op.sumas[0][1]
		copiada = copiar_al_portapapeles(suma)
		texto = _("{a} de {n}: {s}").format(a=algoritmo.nombre, n=elementos[0].nombre, s=suma)
		if not copiada:
			texto += _(". No se pudo copiar al portapapeles")
		anuncios.anunciar(texto, anuncios.ESENCIAL)

	ctx.lanzar(operacion, al_terminar=al_terminar)


def sumas_verificar(ctx) -> None:
	"""Verifica con el archivo de sumas del cursor (o el que se elija) y muestra la lista de resultados."""
	panel = ctx.activo
	cursor = panel.cursor()
	proveedor = _origen(panel)
	if cursor is not None and not cursor.es_superior and not cursor.es_carpeta and sumas.es_archivo_de_sumas(cursor.nombre):
		ruta = cursor.ruta
	else:
		ruta = _elegir_archivo_de_sumas(ctx)
		if not ruta:
			return
		proveedor = resolver.proveedor_local()
	operacion = OperacionVerificarSumas(proveedor, ruta)

	def al_terminar(op) -> None:
		if not op.verificaciones or not ctx.ventana:
			return
		from app.ui.dialogos.c_sumas import DialogoResultadosSumas

		dialogo = DialogoResultadosSumas(ctx.ventana, op.descripcion(), op.verificaciones)
		try:
			dialogo.ShowModal()
		finally:
			dialogo.Destroy()
			ctx.activo.enfocar()

	ctx.lanzar(operacion, al_terminar=al_terminar)


def _elegir_archivo_de_sumas(ctx) -> str | None:
	"""Diálogo nativo de Windows para abrir un archivo de sumas (es accesible con todos los lectores)."""
	tipos = ";".join("*" + a.extension for a in sumas.ALGORITMOS)
	comodines = _("Archivos de sumas ({t})|{t}|Todos los archivos (*.*)|*.*").format(t=tipos)
	carpeta = _carpeta_local(ctx.activo) or ""
	with wx.FileDialog(ctx.ventana, _("Elija el archivo de sumas"), carpeta, "", comodines,
			wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialogo:
		try:
			if dialogo.ShowModal() != wx.ID_OK:
				return None
			return dialogo.GetPath()
		finally:
			ctx.activo.enfocar()


# ── Dividir y unir ───────────────────────────────────────────────────────────


def dividir(ctx) -> None:
	"""Divide el archivo del cursor en partes ``.001``, ``.002``... más un ``.crc``."""
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos.c_dividir import DialogoDividir

	panel = ctx.activo
	elementos = _trabajo(ctx, _("dividir"))
	if elementos is None:
		return
	if len(elementos) != 1 or elementos[0].es_carpeta:
		_avisar(_("Dividir trabaja con un solo archivo"))
		return
	entrada = elementos[0]
	carpeta = _carpeta_destino(ctx)
	resumen = _("Dividir {n} ({t})").format(n=entrada.nombre, t=formato.tamano_legible(max(0, entrada.tamano)))
	dialogo = DialogoDividir(ctx.ventana, resumen, carpeta, entrada.tamano)
	try:
		if not _modal(ctx, dialogo):
			return
		tamano, texto = dialogo.tamano_parte(), dialogo.carpeta()
	finally:
		dialogo.Destroy()
	destino = _ruta_absoluta(texto, carpeta)
	if not os.path.isabs(destino) or tamano is None:
		dialogos.mostrar_error(ctx.ventana, _("Las partes se guardan en una carpeta del disco."), _("Dividir archivo"))
		return
	if not _asegurar_carpeta(destino):
		return
	ctx.lanzar(OperacionDividir(_origen(panel), entrada, destino, tamano))


def unir(ctx) -> None:
	"""Une las partes desde la ``.001`` (o cualquier parte) del cursor."""
	from app.ui.accesibilidad import dialogos
	from app.ui.dialogos.c_dividir import DialogoUnir

	panel = ctx.activo
	cursor = panel.cursor()
	carpeta_panel = _carpeta_local(panel)
	if cursor is None or cursor.es_superior or cursor.es_carpeta or not carpeta_panel:
		_avisar(_("Ponga el cursor en la primera parte (.001) de un archivo dividido del disco"))
		return
	local = panel.proveedor.ruta_local(cursor.ruta) or cursor.ruta
	base_, punto, numero = cursor.nombre.rpartition(".")
	if not punto or not numero.isdigit() or len(numero) < 3:
		_avisar(_("«{n}» no es una parte de un archivo dividido (.001)").format(n=cursor.nombre))
		return
	primera = os.path.join(os.path.dirname(local), servicio_dividir.nombre_parte(base_, 1))
	if not os.path.isfile(rutas.con_prefijo_largo(primera)):
		_avisar(_("No se encuentra la primera parte {n}").format(n=os.path.basename(primera)))
		return
	carpeta = _carpeta_destino(ctx) or os.path.dirname(local)
	propuesto = os.path.join(carpeta, servicio_dividir.nombre_original(primera))
	partes = servicio_dividir.buscar_partes(primera)
	resumen = _("Unir {p} desde {n}").format(p=formato.plural(len(partes), _("{n} parte"), _("{n} partes")),
		n=os.path.basename(primera))
	dialogo = DialogoUnir(ctx.ventana, resumen, propuesto)
	try:
		if not _modal(ctx, dialogo):
			return
		texto = dialogo.destino()
	finally:
		dialogo.Destroy()
	destino = _ruta_absoluta(texto, carpeta)
	if not _asegurar_carpeta(os.path.dirname(destino)):
		return
	if os.path.exists(rutas.con_prefijo_largo(destino)):
		pregunta = _("Ya existe {n}. ¿Sustituirlo?").format(n=os.path.basename(destino))
		if dialogos.confirmar(ctx.ventana, pregunta, _("Unir archivos"), peligroso=True) != wx.ID_YES:
			return
	ctx.lanzar(OperacionUnir(primera, destino))
