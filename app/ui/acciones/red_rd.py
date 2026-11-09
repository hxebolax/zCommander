# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque RD: unidades de red completas (diseño 2.0, sección 9).

- ``red_raiz`` (Ctrl+Mayús+K): lleva el panel a ``red://``. Con argumento (la
  ruta de una fila; es lo que ejecuta Intro en la raíz o en un servidor, ver
  ``ProveedorRed.orden_al_abrir``) entra en esa fila: un servidor se lista en
  ``red://``; una unidad o recurso se abre con el proveedor local tras
  volver a conectarlo si hace falta (1201) y pedir credenciales si el
  servidor las pide; WebDAV, SSHFS y NFS abren «Conectar unidad de red».
- ``red_buscar_equipos``: vuelve a buscar los equipos (también Ctrl+R en ``red://``).
- ``red_conectar_recurso``: el diálogo de conectar con «Sin letra» fijado.
- ``red_reconectar``, ``red_info`` y ``copiar_ruta_unc``: sobre la fila del
  cursor en ``red://`` o sobre la unidad del panel.
- ``red_contrasenas``, ``red_sesiones`` y los dos cuadros de Windows.

``instalar`` registra «Red» en el selector de unidades, sigue la búsqueda de
equipos (refresca los paneles en ``red://`` sin mover el cursor, suena
``red.equipo`` y anuncia «Búsqueda terminada: 3 equipos») y la ata a Escape
del panel. Todo lo que puede colgarse con la red caída va en hilos.
"""

from __future__ import annotations

import builtins
import logging
import threading
from collections.abc import Callable

import wx

from app.services.vfs import red as vfs_red
from app.services.vfs import resolver
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Espera antes de refrescar los paneles cuando llegan equipos (se agrupan los que llegan juntos).
RETARDO_REFRESCO_MS = 400
#: Lo que se escribe en «Carpeta de red» al elegir un proveedor que se conecta con el diálogo (9.7).
PREFIJOS_OTROS = {"webdav": "https://", "sshfs": "\\\\sshfs\\", "nfs": "\\\\"}


# ── Utilidades ───────────────────────────────────────────────────────────────


def _en_hilo(funcion: Callable[[], object], al_terminar: Callable[[object], None], al_fallar: Callable[[BaseException], None],
		nombre: str) -> threading.Thread:
	"""Hilo desechable: las llamadas de red pueden quedarse colgadas con la red caída (9.9)."""
	from app.services.windows import red

	def trabajo() -> None:
		try:
			with red.sin_cuadros_de_error():
				resultado = funcion()
		except Exception as error:  # noqa: BLE001 - se entrega a la interfaz, que lo anuncia
			log.info("%s falló: %s", nombre, error)
			wx.CallAfter(al_fallar, error)
			return
		wx.CallAfter(al_terminar, resultado)

	hilo = threading.Thread(target=trabajo, name=nombre, daemon=True)
	hilo.start()
	return hilo


def _mensaje(error: BaseException) -> str:
	from app.services import errores

	return getattr(error, "mensaje", "") or errores.mensaje_para_usuario(error)


def _error(ctx, error: BaseException, titulo: str) -> None:
	from app.ui.accesibilidad import dialogos

	if isinstance(error, vfs_red.base.Cancelado):
		anuncios.anunciar(error.mensaje, anuncios.RESULTADO)
		return
	mensaje = _mensaje(error)
	anuncios.anunciar(mensaje, anuncios.ESENCIAL)
	dialogos.mostrar_error(ctx.ventana, mensaje, titulo)


def en_raiz(panel) -> bool:
	return panel is not None and isinstance(getattr(panel, "proveedor", None), vfs_red.ProveedorRed) and vfs_red.es_raiz(panel.ruta)


def _en_red(panel) -> bool:
	return panel is not None and isinstance(getattr(panel, "proveedor", None), vfs_red.ProveedorRed)


def fila_del_cursor(panel):
	"""Fila de ``red://`` o de un servidor bajo el cursor, o ``None``."""
	if not _en_red(panel):
		return None
	entrada = panel.cursor()
	if entrada is None or entrada.es_superior:
		return None
	return panel.proveedor.fila(entrada.ruta)


def _unidad_de_ruta(ruta: str):
	"""``UnidadRed`` de una ruta («Z:\\carpeta» o «\\\\srv\\rec»), o ``None``."""
	from app.services.windows import red

	ruta = (ruta or "").strip()
	if len(ruta) >= 2 and ruta[1] == ":":
		return red.unidad(ruta[:2])
	if ruta.startswith("\\\\"):
		partes = [p for p in ruta[2:].split("\\") if p]
		if len(partes) >= 2:
			return red.unidad(f"\\\\{partes[0]}\\{partes[1]}")
	return None


def _ruta_objetivo(ctx) -> str:
	"""Lo que la orden trata: la fila del cursor en ``red://`` o la carpeta del panel."""
	panel = ctx.objetivo
	fila = fila_del_cursor(panel)
	if fila is not None:
		return fila.ruta
	if _en_red(panel):
		return panel.proveedor.ruta_local(panel.ruta) or panel.ruta
	return panel.ruta_local() or ""


# ── Búsqueda de equipos y raíz ───────────────────────────────────────────────


class _Seguimiento:
	"""Sigue la búsqueda de equipos en la interfaz (lo crea ``instalar``)."""

	def __init__(self, ventana) -> None:
		from app.services import eventos

		self.ventana = ventana
		try:
			bus = ventana.servicio("eventos")
		except (KeyError, AttributeError):
			bus = eventos.bus()
		self._cancelar = [
			bus.suscribir(eventos.AL_CAMBIAR_CARPETA, self.al_cambiar_carpeta),
			bus.suscribir(eventos.AL_EJECUTAR_ORDEN, self.al_ejecutar_orden),
			bus.suscribir(eventos.AL_CERRAR, self.cerrar),
			vfs_red.suscribir(self.al_buscar),
		]
		self._refresco_pendiente = False

	def cerrar(self, **_datos) -> None:
		for cancelar in self._cancelar:
			cancelar()
		self._cancelar = []
		vfs_red.cancelar_descubrimiento("cierre")

	def _config(self, clave: str, defecto):
		try:
			return self.ventana.config.obtener(clave)
		except (KeyError, AttributeError):
			return defecto

	def paneles(self) -> list:
		todos = getattr(self.ventana, "todos_los_paneles", None)
		try:
			return list(todos()) if callable(todos) else []
		except Exception:  # noqa: BLE001 - ventana cerrándose
			log.debug("No se pudieron listar los paneles", exc_info=True)
			return []

	def al_cambiar_carpeta(self, panel=None, proveedor=None, ruta="", **_datos) -> None:
		if not isinstance(proveedor, vfs_red.ProveedorRed) or not vfs_red.es_raiz(ruta):
			return
		if bool(self._config("red.descubrir_al_entrar", True)) and vfs_red.conviene_buscar():
			buscar(panel, relanzar=False)
		else:
			vincular(panel)

	def al_ejecutar_orden(self, id="", argumento=None, **_datos) -> None:  # noqa: A002 - nombre del dato del bus
		if id != "volver_a_leer":
			return
		panel = getattr(self.ventana, "activo", None)
		if en_raiz(panel):
			buscar(panel, relanzar=True)

	def al_buscar(self, evento: str, dato) -> None:
		"""Avisos de la búsqueda (en un hilo de trabajo): todo se pasa al hilo de la interfaz."""
		try:
			wx.CallAfter(self._en_interfaz, evento, dato)
		except Exception:  # noqa: BLE001 - sin wx.App (cerrando) ya no hay a quién avisar
			log.debug("No se pudo pasar el aviso de la búsqueda a la interfaz", exc_info=True)

	def _en_interfaz(self, evento: str, dato) -> None:
		if evento == vfs_red.EQUIPO_NUEVO:
			from app.services.sonidos import servicio

			servicio.sonar("red.equipo")
			self._programar_refresco()
		elif evento == vfs_red.BUSQUEDA_EMPIEZA:
			self._refrescar()
		elif evento == vfs_red.BUSQUEDA_TERMINA:
			lista, cancelada = dato
			if not cancelada:
				anuncios.anunciar(_("Búsqueda terminada: {n}").format(n=_cuantos(len(lista))), anuncios.RESULTADO,
					sonido="red.descubrir_fin")
			self._refrescar()

	def _programar_refresco(self) -> None:
		if self._refresco_pendiente:
			return
		self._refresco_pendiente = True
		wx.CallLater(RETARDO_REFRESCO_MS, self._refrescar)

	def _refrescar(self) -> None:
		self._refresco_pendiente = False
		refrescar_raiz(self.paneles())


def _cuantos(n: int) -> str:
	return _("1 equipo") if n == 1 else _("{n} equipos").format(n=n)


_seguimiento: _Seguimiento | None = None


def refrescar_raiz(paneles) -> None:
	"""Vuelve a leer los paneles que muestran ``red://``. El panel conserva el elemento del cursor (1.x 5.6)."""
	for panel in paneles:
		if en_raiz(panel):
			panel.refrescar(conservar=True)


def vincular(panel) -> None:
	"""Ata la búsqueda en marcha a Escape del panel (orden «Cancelar o quitar», 10.1)."""
	actual = vfs_red.busqueda_actual()
	if actual is not None and panel is not None:
		panel.vincular_tarea(actual, _("búsqueda de equipos"))


def buscar(panel, relanzar: bool = True):
	"""Empieza (o vuelve a empezar) la búsqueda de equipos y la ata al panel."""
	try:
		actual = vfs_red.iniciar_descubrimiento(relanzar=relanzar)
	except Exception:  # noqa: BLE001 - sin búsqueda la raíz sigue con lo local
		log.exception("No se pudo empezar la búsqueda de equipos")
		anuncios.anunciar(_("No se pudo buscar equipos en la red"), anuncios.ESENCIAL)
		return None
	vincular(panel)
	return actual


def _unidades_virtuales() -> list:
	return [vfs_red.unidad_virtual()]


def instalar(ventana) -> None:
	"""Enganche al arrancar (14.9): «Red» en el selector de unidades y el seguimiento de la búsqueda de equipos."""
	global _seguimiento
	resolver.registrar_unidades(_unidades_virtuales)
	if _seguimiento is not None:
		_seguimiento.cerrar()
	_seguimiento = _Seguimiento(ventana)


# ── Órdenes ──────────────────────────────────────────────────────────────────

_aviso_elevacion_dado = [False]


def red_raiz(ctx) -> None:
	"""Ctrl+Mayús+K: la raíz «Red». Con argumento (Intro en una fila), entra en esa fila."""
	panel = ctx.objetivo
	if ctx.argumento:
		abrir(ctx, str(ctx.argumento))
		return
	from app.services.windows import red

	if red.es_elevado() and not _aviso_elevacion_dado[0]:
		_aviso_elevacion_dado[0] = True
		anuncios.anunciar(red.aviso_elevacion(), anuncios.ESENCIAL)
	panel.ir_a("", vfs_red.proveedor_red())


def abrir(ctx, ruta: str) -> None:
	"""Entra en ``ruta`` de una fila de ``red://`` o de un servidor (9.1)."""
	from app.services.windows import red

	panel = ctx.objetivo
	proveedor = vfs_red.proveedor_red()
	ruta = ruta.strip()
	if vfs_red.es_raiz(ruta):
		panel.ir_a("", proveedor)
		return
	if ruta.lower() == vfs_red.RUTA_BUSCANDO:
		actual = vfs_red.busqueda_actual()
		hallados = len(actual.equipos()) if actual is not None else 0
		anuncios.anunciar(_("Buscando equipos: {n} hasta ahora. Escape la detiene.").format(n=vfs_red.formato_encontrados(hallados)),
			anuncios.RESULTADO)
		return
	otro = ruta[len(vfs_red.DIRECCION):].lower() if ruta.lower().startswith(vfs_red.DIRECCION) else ""
	if otro in PREFIJOS_OTROS:
		ctx.ejecutar_orden("conectar_unidad_red", argumento=PREFIJOS_OTROS[otro])
		return
	if otro:
		ruta = vfs_red.ruta_de_direccion(ruta)
	fila = proveedor.fila(ruta)
	if fila is not None and fila.clase == vfs_red.IMPRESORA:
		anuncios.anunciar(_("No se puede entrar en una impresora"), anuncios.RESULTADO)
		return
	if red.es_servidor(ruta):
		panel.ir_a(ruta.rstrip("\\"), proveedor)
		return
	entrar(ctx, panel, ruta, reconectar_siempre=True)


def entrar(ctx, panel, ruta: str, reconectar_siempre: bool = False) -> None:
	"""Prepara la carpeta real (reconectar, credenciales) en un hilo y lleva el panel a ella con el proveedor local."""
	proveedor = vfs_red.proveedor_red()
	cancelacion = vfs_red.base.Cancelacion()

	class _Espera:
		"""Para Escape del panel mientras se conecta (``vincular_tarea``)."""

		terminada = False

		def cancelar(self, _motivo: str = "") -> None:
			cancelacion.cancelar()

	espera = _Espera()

	def preparar() -> bool:
		return proveedor.preparar(ruta, cancelacion, reconectar_siempre=reconectar_siempre)

	def listo(conectado) -> None:
		espera.terminada = True
		if cancelacion.is_set():
			return
		if conectado:
			anuncios.anunciar(_("{r} conectada de nuevo").format(r=ruta.rstrip("\\")), anuncios.RESULTADO, sonido="red.reconectada")
			refrescar_raiz([p for p in _paneles(ctx) if p is not panel])
		if ruta.startswith("\\\\"):
			from app.services import red_recientes
			from app.services.windows import red

			red_recientes.anotar_reciente(red.servidor_de(ruta))
		panel.ir_a(ruta, resolver.proveedor_local())

	def fallo(error: BaseException) -> None:
		espera.terminada = True
		if isinstance(error, vfs_red.base.Cancelado) or cancelacion.is_set():
			anuncios.anunciar(getattr(error, "mensaje", "") or _("Cancelado"), anuncios.RESULTADO)
			return
		_error(ctx, error, _("Red"))
		panel.enfocar()

	anuncios.anunciar(_("Abriendo {r}...").format(r=ruta.rstrip("\\")), anuncios.DETALLE)
	_en_hilo(preparar, listo, fallo, "red-entrar")
	try:
		panel.vincular_tarea(espera, _("conexión con {r}").format(r=ruta.rstrip("\\")))
	except Exception:  # noqa: BLE001 - un panel sin vincular_tarea solo pierde Escape
		log.debug("No se pudo vincular la espera al panel", exc_info=True)


def _paneles(ctx) -> list:
	todos = getattr(ctx.ventana, "todos_los_paneles", None)
	if callable(todos):
		try:
			return list(todos())
		except Exception:  # noqa: BLE001 - ventana falsa
			log.debug("No se pudieron listar los paneles", exc_info=True)
	return [p for p in (ctx.izquierdo, ctx.derecho) if p is not None]


def red_buscar_equipos(ctx) -> None:
	"""Busca (o vuelve a buscar) los equipos de la red local y lleva el panel a ``red://``."""
	panel = ctx.objetivo
	anuncios.anunciar(_("Buscando equipos en la red"), anuncios.RESULTADO)
	buscar(panel, relanzar=True)
	if not en_raiz(panel):
		panel.ir_a("", vfs_red.proveedor_red())


def red_conectar_recurso(ctx) -> None:
	"""Abre un recurso compartido con otra cuenta, sin letra (9.4)."""
	from app.ui.acciones import red_d

	red_d.conectar_unidad(ctx, sin_letra=True)


def red_reconectar(ctx) -> None:
	"""Vuelve a conectar la unidad de la fila del cursor (en ``red://``) o la del panel (9.4)."""
	from app.services.windows import red

	panel = ctx.objetivo
	ruta = _ruta_objetivo(ctx)

	def buscar_unidad():
		return _unidad_de_ruta(ruta)

	def tengo(unidad) -> None:
		if unidad is None:
			anuncios.anunciar(_("Aquí no hay una unidad de red que volver a conectar"), anuncios.RESULTADO)
			return
		if unidad.estado_efectivo == red.CONECTADA:
			anuncios.anunciar(_("{l} ya está conectada").format(l=unidad.nombre), anuncios.RESULTADO)
			return
		anuncios.anunciar(_("Volviendo a conectar {l}...").format(l=unidad.nombre), anuncios.RESULTADO)

		def listo(_resultado) -> None:
			anuncios.anunciar(_("{l} conectada de nuevo").format(l=unidad.nombre), anuncios.RESULTADO, sonido="red.reconectada")
			refrescar_raiz(_paneles(ctx))
			if not _en_red(panel) and panel.ruta_local() and panel.ruta_local().upper().startswith(unidad.nombre.upper()):
				panel.refrescar(conservar=True)

		_en_hilo(lambda: vfs_red.proveedor_red().reconectar(unidad), listo, lambda e: _error(ctx, e, _("Volver a conectar")),
			"red-reconectar")

	_en_hilo(buscar_unidad, tengo, lambda e: _error(ctx, e, _("Volver a conectar")), "red-buscar-unidad")


def red_contrasenas(ctx) -> None:
	"""Lista y borra las credenciales de servidores guardadas en Windows (9.5)."""
	from app.services.windows import red

	def mostrar(credenciales) -> None:
		from app.ui.dialogos import f_comun
		from app.ui.dialogos.rd_contrasenas import DialogoContrasenas

		dialogo = DialogoContrasenas(ctx.ventana, credenciales, lambda c: red.olvidar_credencial_de(c.objetivo), red.credenciales)
		f_comun.mostrar(dialogo)

	_en_hilo(red.credenciales, mostrar, lambda e: _error(ctx, e, _("Contraseñas guardadas de servidores")), "red-credenciales")


def red_info(ctx) -> None:
	"""Información de la conexión de la fila del cursor (en ``red://``) o de la carpeta del panel (9.6)."""
	from app.services.windows import red, red_info as servicio_info

	ruta = _ruta_objetivo(ctx)
	if not ruta or vfs_red.es_virtual(ruta) or (red.es_servidor(ruta) and fila_del_cursor(ctx.objetivo) is None):
		anuncios.anunciar(_("Este panel no está en una unidad ni en un recurso de red"), anuncios.RESULTADO)
		return
	if not red.es_ruta_de_red(ruta):
		anuncios.anunciar(_("{r} no está en una unidad de red").format(r=ruta), anuncios.RESULTADO)
		return

	def mostrar(info) -> None:
		from app.ui.dialogos import rd_info

		anuncios.anunciar(info.resumen(), anuncios.DETALLE)
		rd_info.mostrar(ctx.ventana, info)
		ctx.objetivo.enfocar()

	anuncios.anunciar(_("Leyendo la información de la conexión..."), anuncios.DETALLE)
	_en_hilo(lambda: servicio_info.informacion(ruta.rstrip("\\") if len(ruta) == 3 and ruta[1] == ":" else ruta), mostrar,
		lambda e: _error(ctx, e, _("Información de la conexión")), "red-info")


def rutas_unc(rutas: list[str]) -> list[str]:
	"""``WNetGetUniversalName`` de cada ruta (las UNC quedan igual). Lanza el primer error si no se convierte ninguna."""
	from app.services.windows import red

	resultado, primero = [], None
	for ruta in rutas:
		try:
			resultado.append(red.ruta_unc(ruta))
		except red.ErrorUnidadRed as error:
			primero = primero or error
	if not resultado and primero is not None:
		raise primero
	return resultado


def copiar_ruta_unc(ctx) -> None:
	"""Copia la ruta \\\\servidor\\recurso de los elementos de una unidad de red (9.6)."""
	panel = ctx.objetivo
	elementos = panel.elementos_trabajo()
	if not elementos:
		anuncios.anunciar(_("No hay nada que copiar"), anuncios.RESULTADO)
		return
	rutas: list[str] = []
	for entrada in elementos:
		fila = panel.proveedor.fila(entrada.ruta) if _en_red(panel) else None
		if fila is not None:
			rutas.append(fila.remoto if fila.clase == vfs_red.UNIDAD and fila.remoto else fila.ruta)
		else:
			rutas.append(panel.proveedor.ruta_local(entrada.ruta) or entrada.ruta)
	rutas = [r for r in rutas if r and not vfs_red.es_virtual(r)]

	def listo(convertidas) -> None:
		from app.ui.dialogo_texto import copiar_al_portapapeles

		if not copiar_al_portapapeles("\r\n".join(convertidas)):
			anuncios.anunciar(_("No se pudo abrir el portapapeles"), anuncios.ESENCIAL)
			return
		texto = (_("Ruta UNC copiada: {r}").format(r=convertidas[0]) if len(convertidas) == 1
			else _("{n} rutas UNC copiadas").format(n=len(convertidas)))
		anuncios.anunciar(texto, anuncios.RESULTADO, sonido="portapapeles.texto")

	def fallo(error: BaseException) -> None:
		from app.services.windows import red

		if getattr(error, "codigo", 0) == red.ERROR_NOT_CONNECTED:
			anuncios.anunciar(_("No está en una unidad de red: no tiene ruta UNC"), anuncios.RESULTADO)
			return
		anuncios.anunciar(_mensaje(error), anuncios.ESENCIAL)

	if not rutas:
		anuncios.anunciar(_("No hay nada que copiar"), anuncios.RESULTADO)
		return
	_en_hilo(lambda: rutas_unc(rutas), listo, fallo, "red-ruta-unc")


def red_sesiones(ctx) -> None:
	"""Sesiones y archivos abiertos por la red en este equipo (9.8; pide administrador)."""
	from app.services.windows import red_servidor
	from app.ui.accesibilidad import dialogos

	if not red_servidor.es_elevado():
		dialogos.mostrar_mensaje(ctx.ventana, red_servidor.aviso_sin_elevacion(), _("Sesiones y archivos abiertos por la red"))
		return

	def leer():
		return red_servidor.sesiones(), red_servidor.archivos_abiertos()

	def mostrar(datos) -> None:
		from app.ui.dialogos import f_comun
		from app.ui.dialogos.rd_sesiones import DialogoSesiones

		sesiones, archivos = datos
		f_comun.mostrar(DialogoSesiones(ctx.ventana, sesiones, archivos, leer, red_servidor.cerrar_sesion, red_servidor.cerrar_archivo))

	_en_hilo(leer, mostrar, lambda e: _error(ctx, e, _("Sesiones y archivos abiertos por la red")), "red-sesiones")


def red_cuadro_conectar(ctx) -> None:
	"""El cuadro «Conectar a unidad de red» de Windows (en el hilo de la interfaz: es modal)."""
	from app.ui.acciones import red_d

	red_d._cuadro_windows(ctx, conectar=True)  # noqa: SLF001 - función del mismo bloque


def red_cuadro_desconectar(ctx) -> None:
	"""El cuadro «Desconectar unidades de red» de Windows."""
	from app.ui.acciones import red_d

	red_d._cuadro_windows(ctx, conectar=False)  # noqa: SLF001 - función del mismo bloque
