# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque D: conexiones FTP, FTPS y SFTP y unidades de red de Windows.

- ``conexiones`` (Ctrl+K): gestor de sitios; al conectar, la conexión se abre
  en una tarea SIN tiempo máximo (los sockets ya tienen el suyo) porque puede
  esperar a que la persona confirme la huella del servidor o escriba la
  contraseña; después el panel lista la carpeta inicial.
- ``desconectar``: lleva el panel a la última carpeta local de su historial
  (o a la personal); la ventana cierra la conexión si ningún otro panel la usa.
- ``conectar_unidad`` y ``desconectar_unidad``: diálogos propios (con el de
  Windows a un botón) y las llamadas a Windows en hilos desechables, porque
  pueden colgarse con la red caída (diseño 9.7). Desde la 2.0 son del bloque
  RD (diseño 2.0, 9.4 y 9.5): letra automática o sin letra, cifrado,
  contraseña recordada en Windows, error 1219, conexiones sin letra y sacar a
  los paneles de la unidad antes de desconectarla.

Las preguntas de la conexión (huella, contraseña, aviso de FTP sin cifrar)
las responde ``DecisorInmediato``: la persona acaba de pedir conectar, así que
se muestran al momento en vez de esperar en la ventana de operaciones.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Callable, Sequence

import wx

from app.services import conexiones as mod_conexiones
from app.services.vfs import base, resolver
from app.ui import anuncios

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ESQUEMAS_REMOTOS = ("ftp", "sftp")


# ── Preguntas inmediatas ─────────────────────────────────────────────────────


def _dialogo_opciones(padre, titulo: str, texto: str, opciones: Sequence[str], predeterminada: int) -> wx.Dialog:
	from app.ui.accesibilidad.dialogos import DialogoMensaje

	dialogo = DialogoMensaje(padre, texto, titulo, opciones=list(opciones), icono=wx.ICON_WARNING)
	if 0 <= predeterminada < len(dialogo.ids_opciones):
		boton = dialogo.FindWindow(dialogo.ids_opciones[predeterminada])
		if isinstance(boton, wx.Button):
			boton.SetDefault()
			if not isinstance(dialogo.cuerpo, wx.TextCtrl):
				def al_iniciar(evento, boton=boton):
					wx.CallAfter(boton.SetFocus)
					evento.Skip()

				dialogo.Bind(wx.EVT_INIT_DIALOG, al_iniciar)
	return dialogo


class DecisorInmediato:
	"""``elegir`` y ``pedir_texto`` del ``Decisor`` que muestran el diálogo enseguida.

	Se llaman desde el hilo que conecta y lo bloquean hasta la respuesta; el
	diálogo se abre en el hilo de la interfaz con ``wx.CallAfter``. Como los
	de la cola de decisiones, ignora las teclas de sus primeros 300 ms.
	"""

	def __init__(self, ventana: wx.Window | None) -> None:
		self._ventana = ventana

	def _preguntar(self, crear: Callable, interpretar: Callable, cancelar):
		if threading.current_thread() is threading.main_thread():
			raise RuntimeError("DecisorInmediato se usa desde un hilo de trabajo, nunca desde el de la interfaz")
		listo = threading.Event()
		caja = {"valor": cancelar}

		def mostrar() -> None:
			from app.ui.decisiones import ignorar_teclas_iniciales

			try:
				padre = self._ventana if self._ventana else None
				foco_previo = wx.Window.FindFocus()
				dialogo = crear(padre)
				ignorar_teclas_iniciales(dialogo)
				try:
					caja["valor"] = interpretar(dialogo, dialogo.ShowModal())
				finally:
					dialogo.Destroy()
					if foco_previo:
						foco_previo.SetFocus()
			except Exception:  # noqa: BLE001 - sin respuesta se cancela, pero queda la traza
				log.exception("No se pudo mostrar la pregunta de la conexión")
			finally:
				listo.set()

		try:
			wx.CallAfter(mostrar)
		except Exception:  # noqa: BLE001 - sin wx.App (cerrando) no hay a quién preguntar
			log.warning("No se pudo preguntar: la interfaz no está disponible", exc_info=True)
			return cancelar
		while not listo.wait(0.5):
			if wx.GetApp() is None:
				return cancelar
		return caja["valor"]

	def elegir(self, titulo: str, texto: str, opciones: Sequence[str], predeterminada: int = 0, escape: int = -1,
			operacion=None) -> int:
		anuncios.anunciar(titulo, anuncios.ESENCIAL)

		def interpretar(dialogo, codigo):
			ids = dialogo.ids_opciones
			return ids.index(codigo) if codigo in ids else escape

		return self._preguntar(lambda padre: _dialogo_opciones(padre, titulo, texto, opciones, predeterminada), interpretar, escape)

	def pedir_texto(self, titulo: str, texto: str, valor: str = "", oculto: bool = False, operacion=None) -> str | None:
		from app.ui.accesibilidad.dialogos import DialogoTexto

		def interpretar(dialogo, codigo):
			return dialogo.GetValue() if codigo == wx.ID_OK else None

		return self._preguntar(lambda padre: DialogoTexto(padre, texto, titulo, valor, contrasena=oculto), interpretar, None)


# ── Utilidades ───────────────────────────────────────────────────────────────


def _mensaje(error: BaseException) -> str:
	from app.services import errores

	return errores.mensaje_para_usuario(error)


def _en_hilo(funcion: Callable[[], object], al_terminar: Callable[[object], None], al_fallar: Callable[[BaseException], None],
		nombre: str) -> None:
	"""Ejecuta ``funcion`` en un hilo desechable (fuera del grupo de tareas) y responde en la interfaz."""

	def trabajo() -> None:
		try:
			resultado = funcion()
		except Exception as error:  # noqa: BLE001 - se entrega a la interfaz, que lo anuncia
			log.info("%s falló: %s", nombre, error)
			wx.CallAfter(al_fallar, error)
			return
		wx.CallAfter(al_terminar, resultado)

	threading.Thread(target=trabajo, name=nombre, daemon=True).start()


def _repositorio(ctx) -> mod_conexiones.Conexiones:
	secretos = None
	try:
		secretos = ctx.servicio("secretos")
	except Exception:  # noqa: BLE001 - sin el servicio se usa el almacén por defecto
		log.debug("Servicio de secretos no disponible", exc_info=True)
	return mod_conexiones.Conexiones(secretos)


def _carpeta_local_de(panel) -> str:
	"""Última carpeta local del historial del panel, o la personal."""
	try:
		historial = list(panel.historial())
	except Exception:  # noqa: BLE001 - un panel sin historial va a la carpeta personal
		log.debug("Panel sin historial", exc_info=True)
		historial = []
	for texto in historial:
		if "://" not in texto and len(texto) >= 3 and texto[1:3] == ":\\":
			return texto
	return os.path.expanduser("~")


# ── Conexiones FTP y SFTP ────────────────────────────────────────────────────


def conexiones(ctx) -> None:
	"""Ctrl+K: gestor de sitios; «Conectar» abre el sitio en el panel."""
	from app.ui.dialogos.d_conexiones import DialogoConexiones

	repo = _repositorio(ctx)
	dialogo = DialogoConexiones(ctx.ventana, repo)
	try:
		elegido = dialogo.sitio_elegido if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()
	panel = ctx.objetivo
	panel.enfocar()
	if elegido is not None:
		conectar_sitio(ctx, elegido, panel)


def conectar_sitio(ctx, sitio: mod_conexiones.Sitio, panel=None) -> None:
	"""Conecta ``sitio`` en una tarea y, si va bien, abre su carpeta inicial en ``panel``."""
	panel = panel or ctx.objetivo
	proveedor = mod_conexiones.crear_proveedor(sitio)
	proveedor.decisor = DecisorInmediato(ctx.ventana)
	anuncios.anunciar(_("Conectando con {n}...").format(n=sitio.nombre), anuncios.RESULTADO)
	ctx.estado(_("Conectando con {s}...").format(s=proveedor.mostrar("/")))

	def trabajo(tarea) -> str:
		proveedor.conectar()
		base.comprobar(tarea)
		carpeta = proveedor.carpeta_inicial
		if carpeta != "/" and not proveedor.existe(carpeta):
			log.info("La carpeta inicial %s no existe en %s; se abre la raíz", carpeta, proveedor.servidor)
			return "/"
		return carpeta

	def listo(carpeta: str) -> None:
		if carpeta != proveedor.carpeta_inicial:
			anuncios.anunciar(_("La carpeta inicial no existe; se abre la raíz del servidor"), anuncios.ESENCIAL)
		ctx.estado(_("Conectado a {s}").format(s=proveedor.mostrar("/")))
		panel.ir_a(carpeta, proveedor)

	def fallo(error: BaseException) -> None:
		from app.core.tareas import TareaCancelada

		try:
			proveedor.cerrar()
		except Exception:  # noqa: BLE001 - cerrar una conexión fallida no debe tapar el error
			log.debug("Fallo al cerrar tras no conectar", exc_info=True)
		if isinstance(error, TareaCancelada):
			anuncios.anunciar(_("Conexión cancelada"), anuncios.RESULTADO)
			ctx.estado("")
			return
		mensaje = _("No se pudo conectar con {n}: {e}").format(n=sitio.nombre, e=_mensaje(error))
		ctx.estado(mensaje)
		anuncios.anunciar(mensaje, anuncios.ESENCIAL)

	tarea = ctx.tareas.enviar(trabajo, al_terminar=listo, al_fallar=fallo, nombre=f"conectar-{sitio.protocolo}",
		clave_unica=f"conectar:{sitio.id}")
	try:
		panel.vincular_tarea(tarea, _("conexión con {n}").format(n=sitio.nombre))
	except Exception:  # noqa: BLE001 - un panel sin vincular_tarea solo pierde Escape para cancelar
		log.debug("No se pudo vincular la tarea de conexión al panel", exc_info=True)


def desconectar(ctx) -> None:
	"""Cierra la conexión del panel: vuelve a su última carpeta local."""
	panel = ctx.objetivo
	proveedor = panel.proveedor
	if proveedor.esquema not in ESQUEMAS_REMOTOS:
		anuncios.anunciar(_("Este panel no está conectado a ningún servidor"), anuncios.RESULTADO)
		return
	servidor = proveedor.mostrar("/")
	destino = _carpeta_local_de(panel)
	local = resolver.proveedor_local()

	def tras(ok: bool) -> None:
		if ok:
			anuncios.anunciar(_("Desconectado de {s}").format(s=servidor), anuncios.RESULTADO)
		elif destino != os.path.expanduser("~"):
			panel.ir_a(os.path.expanduser("~"), local, al_terminar=tras_personal)

	def tras_personal(ok: bool) -> None:
		if ok:
			anuncios.anunciar(_("Desconectado de {s}").format(s=servidor), anuncios.RESULTADO)

	panel.ir_a(destino, local, al_terminar=tras)


# ── Unidades de red ──────────────────────────────────────────────────────────


def _hwnd(ctx) -> int:
	try:
		return int(ctx.ventana.GetHandle())
	except Exception:  # noqa: BLE001 - sin ventana, los cuadros de Windows salen sin dueño
		log.debug("Sin manejador de ventana", exc_info=True)
		return 0


def _cuadro_windows(ctx, conectar: bool) -> None:
	from app.services.windows import red
	from app.ui.accesibilidad import dialogos

	try:
		hecho = red.dialogo_conectar_windows(_hwnd(ctx)) if conectar else red.dialogo_desconectar_windows(_hwnd(ctx))
	except red.ErrorUnidadRed as error:
		dialogos.mostrar_error(ctx.ventana, error.mensaje, _("Unidades de red"))
		return
	if hecho:
		anuncios.anunciar(_("Unidad de red conectada") if conectar else _("Unidad de red desconectada"), anuncios.RESULTADO)
	ctx.activo.enfocar()


def _panel_en_red(panel) -> bool:
	from app.services.vfs import red as vfs_red

	return isinstance(getattr(panel, "proveedor", None), vfs_red.ProveedorRed)


def _fila_del_cursor(panel):
	"""Fila de la raíz «Red» o de un servidor bajo el cursor (``FilaRed``), o ``None``."""
	if panel is None or not _panel_en_red(panel):
		return None
	entrada = panel.cursor()
	if entrada is None or entrada.es_superior:
		return None
	return panel.proveedor.fila(entrada.ruta)


def _paneles(ctx) -> list:
	todos = getattr(ctx.ventana, "todos_los_paneles", None)
	if callable(todos):
		try:
			return list(todos())
		except Exception:  # noqa: BLE001 - una ventana falsa sin pestañas
			log.debug("No se pudieron listar los paneles", exc_info=True)
	return [p for p in (ctx.izquierdo, ctx.derecho) if p is not None]


def _refrescar_red(ctx) -> None:
	"""Vuelve a leer los paneles que muestran la raíz «Red» (el estado de las unidades cambió)."""
	for panel in _paneles(ctx):
		if _panel_en_red(panel) and not panel.ruta:
			panel.refrescar(conservar=True)


def _remoto_inicial(ctx, panel) -> str:
	if isinstance(ctx.argumento, str) and ctx.argumento.strip():
		return ctx.argumento.strip()
	fila = _fila_del_cursor(panel)
	if fila is not None and fila.ruta.startswith("\\\\"):
		from app.services.windows import red

		return fila.ruta.rstrip("\\") + ("\\" if red.es_servidor(fila.ruta) else "")
	if fila is not None and fila.ruta.lower().startswith("red://"):
		return {"webdav": "https://", "sshfs": "\\\\sshfs\\", "nfs": "\\\\"}.get(fila.ruta[len("red://"):], "")
	ruta = panel.ruta if panel.es_local() else ""
	return ruta if ruta.startswith("\\\\") else ""


def _recientes() -> list[str]:
	from app.services import red_recientes

	try:
		return [*(f.ruta for f in red_recientes.favoritos()), *red_recientes.recientes()]
	except Exception:  # noqa: BLE001 - sin recientes el diálogo funciona igual
		log.debug("No se pudieron leer los servidores recientes", exc_info=True)
		return []


def conectar_unidad(ctx, sin_letra: bool = False) -> None:
	"""Asigna una letra a un recurso compartido (o lo abre sin letra) con ``WNetAddConnection2`` en un hilo.

	2.0 (9.4): letra automática o sin letra, exigir cifrado, recordar la contraseña en
	Windows, servidores recientes y el error 1219 (cerrar las conexiones o usar la IP).
	Si el servidor rechaza las credenciales, el diálogo se vuelve a abrir con lo escrito.
	"""
	from app.services.windows import red
	from app.ui.accesibilidad import dialogos

	try:
		letras = red.letras_libres()
	except Exception as error:  # noqa: BLE001 - sin letras no se puede ofrecer el diálogo
		log.exception("No se pudieron calcular las letras libres")
		dialogos.mostrar_error(ctx.ventana, _mensaje(error), _("Conectar unidad de red"))
		return
	panel = ctx.objetivo
	exigir = bool(ctx.config.obtener("red.exigir_cifrado")) if getattr(ctx, "config", None) is not None else False
	_pedir_y_conectar(ctx, panel, letras, _remoto_inicial(ctx, panel), "", sin_letra, exigir)


def _pedir_y_conectar(ctx, panel, letras, remoto: str, usuario: str, sin_letra: bool, exigir: bool, letra_previa: str = "") -> None:
	from app.services.windows import red
	from app.ui.dialogos.d_unidad import DialogoConectarUnidad

	dialogo = DialogoConectarUnidad(ctx.ventana, letras, remoto, recientes=_recientes(), sin_letra=sin_letra,
		exigir_cifrado=exigir, usuario=usuario)
	try:
		if letra_previa and letra_previa in dialogo.letras:
			dialogo.lista_letra.SetSelection(dialogo.letras.index(letra_previa))
			dialogo._actualizar()  # noqa: SLF001 - el diálogo es de este bloque
		codigo = dialogo.ShowModal()
		letra, remoto, usuario, contrasena, persistente = dialogo.datos()
		recordar, cifrado = dialogo.opciones()
	finally:
		dialogo.Destroy()
	if codigo == wx.ID_MORE:
		_cuadro_windows(ctx, conectar=True)
		return
	panel.enfocar()
	if codigo != wx.ID_OK:
		return
	destino = letra if letra not in ("", "*") else (_("una letra libre") if letra == "*" else _("sin letra"))
	anuncios.anunciar(_("Conectando {r} ({l})...").format(r=remoto, l=destino), anuncios.RESULTADO)

	def conectar(servidor_alternativo: str = "") -> str:
		usado = remoto if not servidor_alternativo else remoto.replace(red.servidor_de(remoto), servidor_alternativo, 1)
		return red.conectar(letra, usado, usuario, contrasena, recordar, persistente=persistente, exigir_cifrado=cifrado)

	def listo(letra_usada) -> None:
		from app.services import red_recientes

		servidor = red.servidor_de(remoto)
		if servidor and remoto.startswith("\\\\"):
			red_recientes.anotar_reciente(servidor)
		if letra_usada:
			texto = _("Unidad {l} conectada a {r}").format(l=letra_usada, r=remoto)
			ctx.estado(_("Unidad {l} conectada").format(l=letra_usada))
		else:
			texto = _("Conectado a {r}").format(r=remoto)
			ctx.estado(texto)
		anuncios.anunciar(texto, anuncios.RESULTADO, sonido="red.conectar")
		_refrescar_red(ctx)
		if letra_usada or remoto.startswith("\\\\"):
			panel.ir_a((letra_usada + "\\") if letra_usada else remoto, resolver.proveedor_local())

	def fallo(error: BaseException) -> None:
		from app.ui.accesibilidad import dialogos

		codigo_error = getattr(error, "codigo", 0)
		if codigo_error == red.ERROR_SESSION_CREDENTIAL_CONFLICT:
			_resolver_1219(ctx, remoto, conectar, listo, fallo)
			return
		mensaje = _mensaje(error)
		anuncios.anunciar(mensaje, anuncios.ESENCIAL)
		dialogos.mostrar_error(ctx.ventana, mensaje, _("Conectar unidad de red"))
		if codigo_error in red.CODIGOS_CREDENCIALES or codigo_error == red.ERROR_SMB_GUEST_LOGON_BLOCKED:
			# Se vuelve a pedir con lo escrito (la contraseña no: se escribe otra vez).
			_pedir_y_conectar(ctx, panel, letras, remoto, usuario, sin_letra, cifrado, letra if letra not in ("", "*") else "")
			return
		panel.enfocar()

	_en_hilo(conectar, listo, fallo, "conectar-unidad")


def _resolver_1219(ctx, remoto: str, conectar, listo, fallo) -> None:
	"""Error 1219: ofrece cerrar las conexiones a ese servidor y reintentar, o usar su IP (9.3)."""
	from app.services.windows import red
	from app.ui.accesibilidad import dialogos

	servidor = red.servidor_de(remoto)
	opciones = [_("Cerrar las &conexiones a este servidor y reintentar"), _("Usar otro &nombre del servidor (su IP)"), _("&Cancelar")]
	texto = _("Ya hay una conexión a {s} con otro usuario y Windows no admite dos a la vez con el mismo nombre.").format(s=servidor)
	eleccion = dialogos.elegir_opcion(ctx.ventana, texto, _("Conectar unidad de red"), opciones)
	if eleccion == 0:
		def cerrar_y_conectar():
			red.cerrar_conexiones_servidor(servidor)
			return conectar()

		_en_hilo(cerrar_y_conectar, listo, fallo, "conectar-unidad-1219")
	elif eleccion == 1:
		def por_ip():
			import socket

			return conectar(socket.gethostbyname(servidor))

		_en_hilo(por_ip, listo, fallo, "conectar-unidad-ip")
	else:
		ctx.objetivo.enfocar()


def _sacar_paneles(ctx, unidad, despues) -> None:
	"""Saca a los paneles (de todas las pestañas) de la unidad o conexión antes de desconectarla (9.5).

	Su carpeta vigilada y el directorio de trabajo bloquean la desconexión (2404).
	``despues()`` se llama cuando todos han salido.
	"""
	prefijos = [p.upper() for p in (unidad.letra, unidad.remoto) if p]

	def dentro(panel) -> bool:
		ruta = panel.ruta or ""
		return any(ruta.upper().startswith(p) for p in prefijos)

	afectados = [p for p in _paneles(ctx) if p.es_local() and dentro(p)]
	try:
		if any(os.getcwd().upper().startswith(p) for p in prefijos):
			os.chdir(os.path.expanduser("~"))
	except OSError:
		log.debug("No se pudo cambiar el directorio de trabajo", exc_info=True)
	if not afectados:
		despues()
		return
	pendientes = {"n": len(afectados)}

	def uno_mas(_ok: bool) -> None:
		pendientes["n"] -= 1
		if pendientes["n"] == 0:
			despues()

	for panel in afectados:
		dejar = getattr(panel, "dejar_de_vigilar", None)
		if callable(dejar):
			dejar()
		panel.ir_a(os.path.expanduser("~"), resolver.proveedor_local(), al_terminar=uno_mas, forzar_aqui=True)


def desconectar_unidad(ctx) -> None:
	"""Quita una letra de red o una conexión sin letra (``WNetCancelConnection2`` en un hilo).

	Con el cursor en una unidad o conexión de la raíz «Red», el diálogo solo ofrece esa.
	Antes saca a los paneles de esa unidad. Pregunta antes de forzar si hay archivos
	abiertos (2401, 2404), con el foco en «No».
	"""
	from app.services.windows import red
	from app.ui.accesibilidad import dialogos

	def mostrar(unidades) -> None:
		from app.ui.dialogos.d_unidad import DialogoDesconectarUnidad

		dialogo = DialogoDesconectarUnidad(ctx.ventana, unidades)
		try:
			codigo = dialogo.ShowModal()
			elegida = dialogo.elegida()
			olvidar, forzar = dialogo.opciones()
			credencial = dialogo.olvidar_credencial()
		finally:
			dialogo.Destroy()
		if codigo == wx.ID_MORE:
			_cuadro_windows(ctx, conectar=False)
			return
		ctx.activo.enfocar()
		if codigo == wx.ID_OK and elegida is not None:
			_sacar_paneles(ctx, elegida, lambda: quitar(elegida, olvidar, forzar, credencial))

	def quitar(unidad, olvidar: bool, forzar: bool, credencial: bool) -> None:
		def listo(_resultado) -> None:
			anuncios.anunciar(_("Unidad {l} desconectada").format(l=unidad.nombre), anuncios.RESULTADO, sonido="red.desconectar")
			_refrescar_red(ctx)

		def fallo(error: BaseException) -> None:
			if getattr(error, "codigo", 0) in (red.ERROR_OPEN_FILES, red.ERROR_DEVICE_IN_USE) and not forzar:
				pregunta = _("{m}\n\n¿Desconectar a la fuerza? Los programas que usan archivos de {l} pueden perder datos.").format(
					m=_mensaje(error), l=unidad.nombre)
				if dialogos.confirmar(ctx.ventana, pregunta, _("Desconectar unidad de red"), peligroso=True) == wx.ID_YES:
					quitar(unidad, olvidar, True, credencial)
				return
			mensaje = _mensaje(error)
			anuncios.anunciar(mensaje, anuncios.ESENCIAL)
			dialogos.mostrar_error(ctx.ventana, mensaje, _("Desconectar unidad de red"))

		_en_hilo(lambda: red.desconectar(unidad.nombre, forzar, olvidar, olvidar_credencial=credencial), listo, fallo,
			"desconectar-unidad")

	def fallo_lista(error: BaseException) -> None:
		dialogos.mostrar_error(ctx.ventana, _mensaje(error), _("Desconectar unidad de red"))

	fila = _fila_del_cursor(ctx.objetivo)
	if fila is not None and fila.clase in ("unidad", "conexion"):
		nombre = fila.ruta.rstrip("\\") if fila.clase == "unidad" else fila.ruta

		def una_sola():
			unidad = red.unidad(nombre)
			return [unidad] if unidad is not None else red.unidades_red()

		_en_hilo(una_sola, mostrar, fallo_lista, "listar-unidades-red")
		return
	_en_hilo(red.unidades_red, mostrar, fallo_lista, "listar-unidades-red")
