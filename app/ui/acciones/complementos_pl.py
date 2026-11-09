# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes de complementos (diseño 2.0, 3.4, 3.5 y 14.1.1) y del bloque PL.

- ``ejecutar`` y ``estado`` son REALES desde N2 (los usa cada orden de
  complemento del catálogo, con ``param`` = id completo): activan el complemento
  si hace falta, sin bloquear la interfaz, con la instantánea inmutable del
  objetivo tomada al pulsar la tecla, y llaman protegido a su manejador con un
  ``ContextoComplemento``. PL completa el resto del módulo sin cambiarlos.
- Las órdenes propias de PL: gestor de complementos, instalar desde un archivo
  (también Intro sobre un ``.zcplugin``, con la ruta como argumento), recargar
  el complemento en desarrollo, reiniciar y reiniciar sin complementos.
- ``instalar`` (14.9): comprobación periódica de actualizaciones, auditoría y,
  tras mostrar la ventana, los ``al_instalar``/``al_desinstalar`` de lo aplicado
  al reiniciar y las preguntas por los centinelas y los complementos sin aceptar.
"""

from __future__ import annotations

import builtins
import logging
import threading
from typing import Any

from app.plugins import api, cargador, registro
from app.plugins import estado as estado_complementos
from app.plugins.estado import EstadoComplemento
from app.ui import anuncios

log = logging.getLogger(__name__)

#: Tras este tiempo sin activarse se anuncia «Cargando el complemento...» (3.4).
AVISO_CARGA_S = 0.3


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def _resolver(ctx: Any, valor: bool) -> None:
	futuro = ctx.extra.get("futuro")
	if futuro is not None and not futuro.done():
		futuro.set_result(valor)


def _etiqueta(orden: Any, id_completo: str) -> str:
	return (orden.etiqueta if orden else id_completo).replace("&", "")


def _motivo_no_usable(registrado: Any) -> str:
	nombre = registrado.nombre
	if registrado.estado == EstadoComplemento.INHABILITADO:
		return _("El complemento {n} está inhabilitado").format(n=nombre)
	if registrado.estado == EstadoComplemento.FALLIDO:
		return _("El complemento {n} no se puede usar en esta sesión por errores").format(n=nombre)
	if registrado.estado == EstadoComplemento.SIN_ACEPTAR:
		return _("El complemento {n} no está aceptado; acéptelo en el gestor de complementos").format(n=nombre)
	if registrado.estado == EstadoComplemento.INCOMPATIBLE:
		return _("El complemento {n} no es compatible con esta versión de zCommander").format(n=nombre)
	return _("El complemento {n} tiene un error en su manifiesto").format(n=nombre)


def _contexto(ctx: Any, activo: Any, pasivo: Any) -> api.ContextoComplemento:
	return api.ContextoComplemento(orden=ctx.param, activo=activo, pasivo=pasivo, lado_objetivo=ctx.lado_objetivo,
		argumento=getattr(ctx, "argumento", None))


def ejecutar(ctx) -> None:
	"""Manejador genérico de toda orden de complemento (``param`` = id completo)."""
	id_completo = ctx.param
	id_complemento, _corto = registro.separar_orden(id_completo)
	registrado = registro.complemento(id_complemento)
	orden = registro.orden(id_completo)
	if registrado is None:
		anuncios.anunciar(_("El complemento {c} no está instalado").format(c=id_complemento), anuncios.ESENCIAL)
		_resolver(ctx, False)
		return
	if registrado.estado in cargador.NO_USABLES:
		anuncios.anunciar(_motivo_no_usable(registrado), anuncios.ESENCIAL, sonido="aviso.no_disponible")
		_resolver(ctx, False)
		return
	if registrado.estado == EstadoComplemento.ACTIVO:
		_resolver(ctx, api.ejecutar_manejador(id_completo, _contexto(ctx, api.PanelVista(ctx.activo), api.PanelVista(ctx.pasivo))))
		return
	# Sin activar: la orden no espera. Se encola como continuación del futuro con una
	# instantánea del objetivo tomada AHORA (3.4).
	ctx.extra["futuro_tomado"] = True
	congelados = (registro.instantanea(ctx.activo), registro.instantanea(ctx.pasivo))
	contador = getattr(ctx.ventana, "contador_ordenes", 0)
	activacion = cargador.asegurar_activo(id_complemento)
	etiqueta = _etiqueta(orden, id_completo)

	def avisar_carga() -> None:
		if not activacion.done():
			anuncios.anunciar(_("Cargando el complemento..."), anuncios.RESULTADO, sonido="plugin.cargando")

	if not activacion.done():
		temporizador = threading.Timer(AVISO_CARGA_S, lambda: cargador.planificar(avisar_carga))
		temporizador.daemon = True
		temporizador.start()

	def continuar() -> None:
		actual = cargador.actual()
		if actual is not None and actual.congelado:
			log.info("Orden %s descartada: zCommander se está cerrando", id_completo)
			_resolver(ctx, False)
			return
		try:
			ok = bool(activacion.result())
		except Exception:  # noqa: BLE001 - cancelado al cerrar o con error: no se ejecuta
			ok = False
		if not ok:
			ahora = registro.complemento(id_complemento)
			motivo = ahora.motivo if ahora and ahora.motivo else _motivo_no_usable(ahora or registrado)
			anuncios.anunciar(_("No se ejecutó {o}: {m}").format(o=etiqueta, m=motivo), anuncios.ESENCIAL)
			_resolver(ctx, False)
			return
		for real, congelado in ((ctx.activo, congelados[0]), (ctx.pasivo, congelados[1])):
			if real.ruta != congelado.ruta or real.proveedor is not congelado.proveedor:
				anuncios.anunciar(_("No se ejecutó {o}: cambió de carpeta mientras se cargaba el complemento").format(o=etiqueta),
					anuncios.ESENCIAL)
				_resolver(ctx, False)
				return
		if getattr(ctx.ventana, "contador_ordenes", 0) != contador:
			anuncios.anunciar(_("No se ejecutó {o}: ejecutó otra orden mientras se cargaba el complemento").format(o=etiqueta),
				anuncios.ESENCIAL)
			_resolver(ctx, False)
			return
		contexto = _contexto(ctx, api.PanelCongelado(congelados[0], ctx.activo), api.PanelCongelado(congelados[1], ctx.pasivo))
		_resolver(ctx, api.ejecutar_manejador(id_completo, contexto))

	def publicar(_futuro: Any) -> None:
		# Solo se publica: la continuación corre en otra vuelta del bucle, protegida (3.4).
		cargador.planificar(lambda: estado_complementos.llamar_protegido(id_complemento, continuar))

	activacion.add_done_callback(publicar)


def estado(ctx) -> bool:
	"""Estado de una orden casilla de complemento: ``casilla_defecto`` hasta que se activa, después su función."""
	id_completo = ctx.param
	id_complemento, _corto = registro.separar_orden(id_completo)
	orden = registro.orden(id_completo)
	defecto = bool(orden.casilla_defecto) if orden else False
	if registro.estado(id_complemento) != EstadoComplemento.ACTIVO:
		return defecto
	funcion = registro.funcion("estado", id_completo)
	if funcion is None:
		return defecto
	contexto = _contexto(ctx, api.PanelVista(ctx.activo), api.PanelVista(ctx.pasivo))
	return bool(estado_complementos.llamar_protegido(id_complemento, funcion, contexto))



# ── Órdenes del bloque PL ────────────────────────────────────────────────────


def _teclas_ocupadas() -> dict[str, str]:
	"""Tecla → orden de todo el catálogo (el gestor dice qué teclas perdió un complemento de terceros)."""
	from app.ui import ordenes

	ocupadas: dict[str, str] = {}
	for orden in ordenes.catalogo():
		for tecla in orden.teclas:
			ocupadas.setdefault(tecla, orden.id)
	return ocupadas


def complementos(ctx) -> None:
	"""Gestor de complementos (3.11)."""
	from app.ui.dialogos import b_buscar, pl_gestor

	pl_gestor.mostrar(ctx.ventana, ctx.config, al_reiniciar=lambda: reiniciar_aplicacion(ctx.ventana),
		ocupadas=_teclas_ocupadas(), leer_preferencias=b_buscar.preferencias_lectura(ctx.config))


def complemento_instalar(ctx) -> None:
	"""Instala un ``.zcplugin``: el de ``argumento`` (Intro sobre el archivo, macros) o el que se elija (3.10)."""
	from pathlib import Path

	from app.ui.dialogos import pl_gestor

	argumento = getattr(ctx, "argumento", None)
	ruta = Path(str(argumento)) if argumento else pl_gestor.elegir_archivo(ctx.ventana)
	if ruta is None:
		return
	pl_gestor.instalar_desde_archivo(ctx.ventana, ctx.config, ruta, al_reiniciar=lambda: reiniciar_aplicacion(ctx.ventana))


def complemento_recargar(ctx) -> None:
	"""Modo desarrollo: vuelve a cargar el complemento de la carpeta de desarrollo (3.12)."""
	actual = cargador.actual()
	if actual is None or actual.desarrollo is None:
		anuncios.anunciar(_("No hay ningún complemento en desarrollo"), anuncios.RESULTADO)
		return
	futuro = actual.recargar()

	def terminado() -> None:
		try:
			ok = bool(futuro.result())
		except Exception:  # noqa: BLE001 - cancelado al cerrar o con error
			ok = False
		anuncios.anunciar(_("Complemento recargado") if ok else _("El complemento no se pudo recargar; detalles en el registro"),
			anuncios.RESULTADO if ok else anuncios.ESENCIAL)

	futuro.add_done_callback(lambda _f: cargador.planificar(terminado))


def reiniciar(ctx) -> None:
	"""Cierra zCommander y lo vuelve a abrir (14.8: ``--esperar-pid``)."""
	reiniciar_aplicacion(ctx.ventana)


def reiniciar_sin_complementos(ctx) -> None:
	"""Reinicia en modo seguro, sin cargar ningún complemento (3.8)."""
	reiniciar_aplicacion(ctx.ventana, sin_complementos=True)


def orden_de_lanzamiento(*extra: str) -> list[str]:
	"""Cómo se lanza otra vez zCommander: el ``.exe`` o el intérprete con ``main.py`` (como ``main.py``)."""
	import sys

	from app.core import paths

	if getattr(sys, "frozen", False):
		return [sys.executable, *extra]
	return [sys.executable, str(paths.ruta_base() / "main.py"), *extra]


def reiniciar_aplicacion(ventana: Any, sin_complementos: bool = False, lanzar: Any = None) -> bool:
	"""Lanza la instancia nueva (fuera del Job, con ``--esperar-pid``) SOLO si el cierre sigue adelante.

	La instancia nueva se lanza en ``al_cerrar`` (fase irrevocable del cierre, 3.4):
	si la persona cancela la salida (operaciones en curso, un complemento que veta),
	no queda ningún proceso esperando. Devuelve verdadero si se lanzó.
	"""
	import os

	from app.core import procesos
	from app.services import eventos

	argumentos = orden_de_lanzamiento("--esperar-pid", str(os.getpid()), *(["--sin-complementos"] if sin_complementos else []))
	lanzado = {"hecho": False}
	lanzador = lanzar or procesos.lanzar_independiente

	def al_cerrar(**_datos: Any) -> None:
		if lanzado["hecho"]:
			return
		lanzado["hecho"] = True
		try:
			lanzador(argumentos)
			log.info("Reinicio pedido%s", " sin complementos" if sin_complementos else "")
		except Exception:  # noqa: BLE001 - si no se puede lanzar, zCommander se cierra igual (lo pidió la persona)
			log.exception("No se pudo lanzar la instancia nueva para reiniciar")

	cancelar = eventos.bus().suscribir(eventos.AL_CERRAR, al_cerrar)
	ventana.Close()
	if not lanzado["hecho"]:
		cancelar()
		anuncios.anunciar(_("No se reinició: zCommander sigue abierto"), anuncios.RESULTADO)
	return lanzado["hecho"]


# ── Enganche al arrancar (14.9) ──────────────────────────────────────────────


def instalar(ventana) -> None:
	"""PL al arrancar: comprobación periódica, auditoría, avisos de desarrollo y lo que se hace tras mostrar la ventana."""
	from app.plugins import auditoria, paquetes
	from app.services import actualizador, eventos

	config = ventana.config

	def comprobar_activa() -> bool:
		try:
			return bool(config.obtener("actualizaciones.complementos_comprobar"))
		except Exception:  # noqa: BLE001 - sin la clave, la comprobación queda activa (valor de fábrica)
			return True

	actualizador.registrar_comprobacion("complementos", paquetes.comprobacion_periodica, comprobar_activa)
	try:
		config.suscribir(lambda _c, _a, _n: auditoria.desde_configuracion(config), "complementos.auditoria")
	except Exception:  # noqa: BLE001 - una configuración falsa sin suscribir (pruebas)
		log.debug("No se pudo suscribir la auditoría a la configuración", exc_info=True)
	actual = ventana.servicio("plugins")
	if hasattr(actual, "preguntas_en_interfaz"):
		actual.preguntas_en_interfaz = True
	if getattr(actual, "modo_desarrollo", False):
		estado_complementos.fijar_aviso_desarrollo(lambda texto: anuncios.anunciar(texto, anuncios.RESULTADO))
	eventos.bus().suscribir(eventos.AL_ARRANCAR, lambda **_d: ventana.llamar_mas_tarde(200, lambda: tras_arrancar(ventana)))


def tras_arrancar(ventana) -> None:
	"""Tras mostrar la ventana (14.8, pasos 10 y 11): ganchos de lo aplicado al reiniciar y preguntas de 3.8 y 3.9."""
	actual = ventana.servicio("plugins")
	for aplicado in list(getattr(actual, "aplicados", []) or []):
		_ejecutar_gancho_aplicado(aplicado)
	if actual is not None:
		actual.aplicados = []
	arranque = getattr(ventana, "arranque", None)
	if getattr(arranque, "modo", "normal") == "tarea":
		return
	padre = ventana.padre() if hasattr(ventana, "padre") else ventana
	for id_complemento in list(getattr(actual, "centinelas", []) or []):
		preguntar_centinela(padre, ventana.config, id_complemento)
	for id_complemento in list(getattr(actual, "sin_aceptar", []) or []):
		if registro.estado(id_complemento) == EstadoComplemento.SIN_ACEPTAR:
			preguntar_sin_aceptar(padre, ventana.config, id_complemento)
	if actual is not None:
		actual.centinelas, actual.sin_aceptar = [], []


def _ejecutar_gancho_aplicado(aplicado: Any) -> None:
	from app.plugins import manifiesto, paquetes

	try:
		datos = manifiesto.leer(aplicado.carpeta)
	except manifiesto.ErrorManifiesto:
		log.warning("Sin manifiesto para el gancho de %s", aplicado.id, exc_info=True)
		if aplicado.accion == "desinstalar":
			paquetes.limpiar_desinstalado(aplicado.id)
		return
	nombre = "al_desinstalar" if aplicado.accion == "desinstalar" else "al_instalar"
	futuro = paquetes.ejecutar_gancho(aplicado.carpeta, nombre, datos.id, datos.permisos)

	def terminado(_f: Any) -> None:
		if not futuro.result():
			anuncios.anunciar(_("El complemento {n} falló al prepararse; detalles en el registro").format(n=datos.nombre),
				anuncios.ESENCIAL, sonido="plugin.fallo")
		if aplicado.accion == "desinstalar":
			paquetes.limpiar_desinstalado(aplicado.id)

	futuro.add_done_callback(lambda f: cargador.planificar(lambda: terminado(f)))


def preguntar_centinela(padre: Any, config: Any, id_complemento: str) -> None:
	"""zCommander se cerró mientras cargaba el complemento: ¿inhabilitarlo? (3.8)."""
	from app.plugins import gestor
	from app.ui.dialogos import pl_gestor

	nombre = estado_complementos.nombre_de(id_complemento)
	eleccion = pl_gestor.elegir(padre, _("zCommander se cerró mientras cargaba el complemento {n}. ¿Inhabilitarlo?").format(n=nombre),
		_("Complemento"), [_("&Inhabilitarlo"), _("&Cargarlo de nuevo"), _("&Preguntar la próxima vez")])
	if eleccion == 0:
		gestor.inhabilitar(config, id_complemento)
	elif eleccion == 1:
		gestor.habilitar(config, id_complemento)
	else:
		actual = cargador.actual()
		if actual is not None:
			actual._crear_centinela(id_complemento)  # noqa: SLF001 - se vuelve a preguntar en el próximo arranque


def preguntar_sin_aceptar(padre: Any, config: Any, id_complemento: str) -> None:
	"""Complemento sin firma que no pasó por la instalación: ¿aceptarlo? (3.9). Por defecto, no."""
	from app.plugins import gestor
	from app.ui.dialogos import pl_gestor

	registrado = registro.complemento(id_complemento)
	if registrado is None:
		return
	texto = _("Hay un complemento sin firma que no se instaló desde zCommander: {n}, de {a}. Ejecutará código con sus mismos "
		"permisos de Windows. ¿Aceptarlo?").format(n=registrado.nombre, a=registrado.manifiesto.autor)
	while True:
		eleccion = pl_gestor.elegir(padre, texto, _("Complemento sin firma"),
			[_("&No aceptarlo"), _("&Aceptarlo"), _("Ver los &detalles...")])
		if eleccion == 2:
			pl_gestor.mostrar_texto(padre, registrado.nombre, gestor.detalles(id_complemento))
			continue
		if eleccion == 1:
			gestor.aceptar(config, id_complemento)
			anuncios.anunciar(_("{n} aceptado").format(n=registrado.nombre), anuncios.RESULTADO)
		return
