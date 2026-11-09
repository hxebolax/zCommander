# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Teclas de consulta para el lector de pantalla y lectura por columnas."""

from __future__ import annotations

import builtins

from app.services import formato
from app.ui import anuncios


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def decir_ruta(ctx) -> None:
	panel = ctx.activo if ctx.param == "activo" else ctx.pasivo
	lado = _("izquierdo") if panel.lado == "izquierdo" else _("derecho")
	anuncios.anunciar(_("Panel {l}: {r}").format(l=lado, r=panel.mostrar_ruta()), anuncios.RESULTADO)


def decir_resumen(ctx) -> None:
	anuncios.anunciar(ctx.activo.texto_resumen(), anuncios.RESULTADO)


#: Cuántos nombres dice «Decir los elementos marcados» antes de «y N más».
MAX_NOMBRES_MARCADOS = 20


def texto_marcados(panel) -> str:
	"""«3 marcados, 25 MB: informe.pdf, notas.txt, fotos» o, sin marcas, el elemento de trabajo.

	Con carpetas sin calcular: «3 marcados (1 carpeta), 25 MB en archivos: …» o, si solo
	hay carpetas, «2 marcados (2 carpetas): …».

	Sale del modelo (``panel.marcadas()``): es igual con las marcas como selección o en la
	columna Marca, y no cuenta lo que un filtro esconde.
	"""
	marcadas = panel.marcadas()
	if not marcadas:
		entrada = panel.cursor()
		if entrada is None or entrada.es_superior:
			return _("No hay nada marcado")
		return _("No hay nada marcado; el elemento de trabajo es {n}").format(n=entrada.nombre)
	# 2.0.1: las carpetas sin calcular no suman «0 bytes» (``formato.tamano_marcadas``).
	cabeza = formato.plural(len(marcadas), _("{n} marcado"), _("{n} marcados")) + formato.tamano_marcadas(marcadas)
	nombres = [e.nombre for e in marcadas[:MAX_NOMBRES_MARCADOS]]
	resto = len(marcadas) - len(nombres)
	lista = ", ".join(nombres)
	if resto > 0:
		lista += _(" y {n} más").format(n=resto)
	return f"{cabeza}: {lista}"


def decir_marcados(ctx) -> None:
	anuncios.anunciar(texto_marcados(ctx.activo), anuncios.RESULTADO)


def decir_info(ctx) -> None:
	entrada = ctx.activo.cursor()
	if entrada is None:
		anuncios.anunciar(_("Lista vacía"), anuncios.RESULTADO)
		return
	if entrada.es_superior:
		anuncios.anunciar(_("Carpeta superior"), anuncios.RESULTADO)
		return
	propias = _columnas_propias(ctx.activo)
	if propias:
		# 2.0 (9.1): en «Red», lo que dicen sus columnas (tipo, remoto, estado) en lugar de «Carpeta».
		partes = [entrada.nombre, *[v for v in (_valor_propio(ctx.activo, entrada, c) for c in propias) if v]]
	else:
		partes = [entrada.nombre, ctx.activo._tipo(entrada)]  # noqa: SLF001 - el panel sabe describir el tipo
	if (not entrada.es_carpeta and not propias) or entrada.tamano >= 0:
		partes.append(formato.tamano_legible(entrada.tamano))
	if entrada.modificado:
		partes.append(_("modificado el {f}").format(f=formato.fecha(entrada.modificado, "larga")))
	if entrada.creado:
		partes.append(_("creado el {f}").format(f=formato.fecha(entrada.creado, "larga")))
	atributos = formato.atributos_largos(entrada.atributos)
	if atributos:
		partes.append(atributos)
	if ctx.activo.lista_archivos.esta_marcada(ctx.activo.lista_archivos.cursor_indice()):
		partes.append(_("marcado"))
	texto = ", ".join(partes)
	anuncios.anunciar(texto, anuncios.RESULTADO)
	_lineas_de_complementos(ctx, entrada, texto)


def _columnas_propias(panel) -> list[str]:
	"""Ids de las columnas propias del proveedor del panel, sin «nombre» (vacía si no tiene)."""
	from app.ui.panel_archivos import columnas_del_proveedor

	propias = columnas_del_proveedor(panel.proveedor, panel.ruta) or []
	return [c for c, _t in propias if c != "nombre"]


def _valor_propio(panel, entrada, columna: str) -> str:
	valor = getattr(panel.proveedor, "valor_columna", None)
	return str(valor(entrada, columna) or "") if callable(valor) else ""


def _lineas_de_complementos(ctx, entrada, texto: str) -> None:
	"""En un hilo, lo que se añade al anuncio de Ctrl+Mayús+I.

	2.0 (3.5): las líneas de los complementos cuyo ``[[info]]`` coincide. 2.0 (9.6): sobre una
	unidad o ruta de red, una línea con el resumen de la conexión.
	"""
	from app.plugins import registro
	from app.ui import vistas

	proveedor = ctx.activo.proveedor
	con_complementos = any(registro.coincide(entrada.nombre, i.get("patrones", [])) for r in registro.complementos()
		for i in r.manifiesto.tabla("info"))
	ruta_red = vistas.ruta_para_resumen_red(proveedor, entrada, ctx.activo.ruta)
	if not con_complementos and not ruta_red:
		return

	def trabajo(_tarea):
		lineas = list(registro.lineas_info(entrada, proveedor)) if con_complementos else []
		resumen = vistas.resumen_red(ruta_red) if ruta_red else ""
		return [*lineas, resumen] if resumen else lineas

	def listo(lineas) -> None:
		if lineas:
			anuncios.anunciar(", ".join([texto, *lineas]), anuncios.RESULTADO)

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda _e: None, nombre="info-complementos")


def decir_espacio(ctx) -> None:
	panel = ctx.activo

	def trabajo(_tarea):
		return panel.proveedor.espacio_libre(panel.ruta)

	def listo(espacio) -> None:
		if not espacio:
			anuncios.anunciar(_("No se sabe el espacio libre aquí"), anuncios.RESULTADO)
			return
		libre, total = espacio
		anuncios.anunciar(_("{l} libres de {t}").format(l=formato.tamano_legible(libre), t=formato.tamano_legible(total)), anuncios.RESULTADO)

	ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=lambda _e: anuncios.anunciar(_("No se sabe el espacio libre aquí"), anuncios.RESULTADO))


def decir_operaciones(ctx) -> None:
	en_marcha = ctx.operaciones.en_marcha()
	if not en_marcha:
		texto = _("No hay operaciones en curso")
	else:
		partes = []
		for operacion in en_marcha:
			p = operacion.instantanea()
			trozo = f"{operacion.descripcion()}, {operacion.estado.texto.lower()}"
			if p.porcentaje is not None:
				trozo += f", {p.porcentaje} %"
			if p.velocidad:
				trozo += ", " + formato.velocidad(p.velocidad)
			if p.restante_s:
				trozo += ", " + _("quedan {t}").format(t=formato.duracion(p.restante_s))
			partes.append(trozo)
		texto = ". ".join(partes)
	pendientes = ctx.servicio("decisiones").pendientes()
	if pendientes:
		texto += ". " + _("Esperan su decisión: {d}. Pulse F12 para atenderlas.").format(d=", ".join(pendientes))
	anuncios.anunciar(texto, anuncios.RESULTADO)


def repetir_anuncio(ctx) -> None:
	anuncios.repetir_ultimo()


def historial_anuncios(ctx) -> None:
	from app.ui.dialogo_texto import mostrar_texto

	lineas = [f"{formato.fecha(a.momento, 'larga')}  {a.completo}" for a in reversed(anuncios.historial())]
	mostrar_texto(ctx.ventana, _("Historial de anuncios"), _("&Anuncios, el más reciente primero:"), "\n".join(lineas) or _("Ninguno"), copiable=True)


def _anunciar_celda(ctx, columna: int) -> None:
	from app.ui.accesibilidad.composicion import PreferenciasLectura, componer_anuncio_celda
	from app.ui.accesibilidad import voz

	lista = ctx.activo.lista_archivos
	fila = lista.cursor_indice()
	if fila < 0:
		voz.hablar(_("Lista vacía"), canal=voz.NAVEGACION)
		return
	if not 0 <= columna < len(lista.columnas):
		voz.hablar(_("No existe la columna {n}").format(n=columna + 1), canal=voz.NAVEGACION)
		return
	preferencias = PreferenciasLectura(
		numero_fila=bool(ctx.config.obtener("accesibilidad.leer_numero_fila")),
		cabecera=bool(ctx.config.obtener("accesibilidad.leer_cabecera")),
		contenido=bool(ctx.config.obtener("accesibilidad.leer_contenido")),
	)
	texto = componer_anuncio_celda(fila, lista.cabecera(columna), lista.texto_celda(fila, columna), globales=preferencias)
	lista.columna_actual = columna
	voz.hablar(texto, canal=voz.NAVEGACION)


def leer_columna(ctx) -> None:
	_anunciar_celda(ctx, int(ctx.param) - 1)


def mover_columna(ctx) -> None:
	lista = ctx.activo.lista_archivos
	nueva = max(0, min(len(lista.columnas) - 1, lista.columna_actual + int(ctx.param)))
	_anunciar_celda(ctx, nueva)
