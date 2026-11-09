# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Manejadores de las órdenes de Nubes (diseño 2.0, 12.6): diálogos en el hilo de la interfaz, red en hilos.

Cada manejador dura menos de 20 ms fuera de los diálogos modales (3.7): lo que
habla con rclone o con un servidor va en ``zc.tareas`` mientras un
``DialogoEspera`` lo explica, o en una operación del motor (``zc.lanzar``) con
su progreso, su cancelación y su resumen.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from app.plugins import api

from .. import nextcloud
from ..cuentas import Cuenta, Servicio, carpeta_drive_escritorio
from ..operaciones import OperacionRclone, carril, resumen_informe
from ..servicio import Nubes, Paso, texto_estado
from . import comun, oauth

if TYPE_CHECKING:
	from ..servicio import Alta

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

URL_WINFSP = "https://winfsp.dev/rel/"


def padre_por_defecto() -> wx.Window | None:
	aplicacion = wx.GetApp()
	return aplicacion.GetTopWindow() if aplicacion else None


def documento_markdown(titulo: str, texto: str) -> api.Documento:
	"""Un ``api.Documento`` con una sección por encabezado de Markdown (F6 salta entre secciones en el visor)."""
	secciones: list[api.Seccion] = []
	actual_titulo, actual_nivel, lineas = titulo, 1, []
	for linea in texto.splitlines():
		coincide = re.match(r"^(#{1,6})\s+(.*)$", linea)
		if coincide:
			if lineas or secciones:
				secciones.append(api.Seccion(actual_titulo, actual_nivel, "\n".join(lineas).strip()))
			actual_titulo, actual_nivel, lineas = coincide.group(2).strip(), len(coincide.group(1)), []
		else:
			lineas.append(linea)
	secciones.append(api.Seccion(actual_titulo, actual_nivel, "\n".join(lineas).strip()))
	return api.Documento(titulo=titulo, secciones=tuple(secciones))


class Ordenes:
	"""Las 20 órdenes de Nubes y lo que comparten las ventanas."""

	def __init__(self, zc: Any, nubes: Nubes) -> None:
		self.zc = zc
		self.nubes = nubes

	# ── Utilidades ─────────────────────────────────────────────────────────

	def _en_hilo(self, funcion: Callable[[Any], Any], al_terminar: Callable[[Any], None] | None = None, nombre: str = "zc-nubes") -> None:
		def al_fallar(error: BaseException) -> None:
			if isinstance(error, api.Cancelado) or type(error).__name__ == "TareaCancelada":
				self.zc.anunciar(_("Cancelado"), api.RESULTADO)
				return
			self._error(error)

		self.zc.tareas.enviar(funcion, al_terminar=al_terminar, al_fallar=al_fallar, nombre=nombre)

	def _error(self, error: BaseException) -> None:
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else _("Error inesperado: {e}").format(e=error)
		if not isinstance(error, api.ErrorArchivos):
			log.error("Error en Nubes", exc_info=error)
		comun.error(self.zc, mensaje)

	def _esperar(self, padre: wx.Window | None, titulo: str, explicacion: str, funcion: Callable[[Any], Any]) -> Any:
		"""``funcion(tarea)`` en un hilo con un diálogo de espera; ``None`` si se cancela o falla (ya avisado)."""
		try:
			return oauth.esperar(self.zc, padre, titulo, explicacion, funcion)
		except api.Cancelado:
			self.zc.anunciar(_("Cancelado"), api.RESULTADO)
		except Exception as error:  # noqa: BLE001 - cualquier fallo se explica a la persona
			self._error(error)
		return None

	def _cuentas(self, *, solo_rclone: bool = False) -> list[Cuenta]:
		return [c for c in self.nubes.cuentas.lista() if not solo_rclone or c.motor == "rclone"]

	@staticmethod
	def _cuenta_del_panel(panel: Any) -> Cuenta | None:
		proveedor = getattr(panel, "proveedor", None)
		return getattr(proveedor, "cuenta", None) if getattr(proveedor, "esquema", "") == "nube" else None

	def _cuenta_objetivo(self, ctx: api.ContextoComplemento, *, solo_rclone: bool = True, pregunta: str = "") -> Cuenta | None:
		"""La cuenta del panel activo; si no, la única que hay o la que elija la persona."""
		cuenta = self._cuenta_del_panel(ctx.activo)
		if cuenta is not None and (not solo_rclone or cuenta.motor == "rclone"):
			return cuenta
		cuentas = self._cuentas(solo_rclone=solo_rclone)
		if not cuentas:
			self.zc.anunciar(_("No hay cuentas de nube; añada una con Añadir una cuenta de nube"), api.RESULTADO)
			return None
		if len(cuentas) == 1:
			return cuentas[0]
		eleccion = comun.opcion(self.zc, pregunta or _("¿Con qué cuenta?"), _("Elegir una cuenta de nube"), [c.nombre for c in cuentas])
		return cuentas[eleccion] if eleccion is not None and 0 <= eleccion < len(cuentas) else None

	def direccion_panel(self, panel: Any) -> str:
		"""Dirección que entiende rclone para la carpeta de un panel («nube://cuenta/ruta» o una ruta local)."""
		cuenta = self._cuenta_del_panel(panel)
		ruta = getattr(panel, "ruta", "") or ""
		if cuenta is not None:
			return f"nube://{cuenta.id}/{ruta.strip('/')}"
		proveedor = getattr(panel, "proveedor", None)
		if getattr(proveedor, "esquema", "") == "local":
			return ruta
		return ""

	def _opciones_cuentas(self, solo_rclone: bool = True) -> list[tuple[str, str]]:
		return [(c.id, c.nombre) for c in self._cuentas(solo_rclone=solo_rclone)]

	# ── Cuentas ─────────────────────────────────────────────────────────────

	def cuentas(self, ctx: api.ContextoComplemento) -> None:
		from .cuentas import DialogoCuentas

		dialogo = DialogoCuentas(self.zc, padre_por_defecto(), self)
		try:
			if self.nubes.motor.vivo():
				for cuenta in self._cuentas():
					self.espacio_de(cuenta, al_terminar=lambda texto, c=cuenta: dialogo and dialogo.poner_espacio(c.id, texto),
						silencioso=True)
			comun.mostrar_modal(self.zc, dialogo)
		finally:
			dialogo.Destroy()

	def espacio_de(self, cuenta: Cuenta, al_terminar: Callable[[str], None] | None = None, *, silencioso: bool = False) -> None:
		def trabajo(_tarea: Any) -> str:
			return self.nubes.espacio(cuenta)

		def hecho(texto: str) -> None:
			if not silencioso:
				self.zc.anunciar(f"{cuenta.nombre}: {texto}", api.RESULTADO)
			if al_terminar is not None:
				al_terminar(texto)

		def fallo(error: BaseException) -> None:
			mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
			if al_terminar is not None:
				al_terminar(texto_estado(self.nubes.estado(cuenta)) if not silencioso else mensaje)
			if not silencioso:
				self._error(error)

		self.zc.tareas.enviar(trabajo, al_terminar=hecho, al_fallar=fallo, nombre="zc-nubes-espacio")

	def anadir(self, ctx: api.ContextoComplemento) -> None:
		self.asistente(padre_por_defecto())

	def asistente(self, padre: wx.Window | None, servicio: Servicio | None = None, existente: Cuenta | None = None) -> Cuenta | None:
		"""El asistente completo; devuelve la cuenta añadida o ``None``."""
		from .asistente import DialogoDatos, DialogoServicio

		if servicio is None:
			dialogo = DialogoServicio(self.zc, padre, self.nubes.catalogo, bool(self.nubes.opcion("mostrar_experimentales", False)))
			try:
				if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
					return None
				servicio = dialogo.elegido()
			finally:
				dialogo.Destroy()
			if servicio is None:
				return None
		if servicio.id == "nextcloud":
			return self.conectar_nextcloud(padre)
		datos = DialogoDatos(self.zc, padre, servicio, existente.nombre if existente else "", guia=lambda: self.mostrar_guia())
		try:
			if comun.mostrar_modal(self.zc, datos) != wx.ID_OK:
				return None
			nombre, valores = datos.nombre_visible(), datos.valores()
		finally:
			datos.Destroy()
		if servicio.motor == "webdav":
			return self._alta_webdav(padre, servicio, nombre, valores, existente)
		if servicio.tipo == "drive" and not valores.get("client_id") and not self._drive_sin_identificador(padre):
			return None
		cuenta, parametros = self.nubes.nueva_cuenta(servicio, nombre, valores, id=existente.id if existente else "")
		secretos = {"client_secret": valores.get("client_secret", "")}
		alta = self.nubes.alta(cuenta, parametros)
		if self._correr_alta(padre, alta, servicio.nombre, cuenta, secretos, nuevo=existente is None):
			return cuenta
		return None

	def _drive_sin_identificador(self, padre: wx.Window | None) -> bool:
		"""Drive sin identificador propio (nubes.md 4.1): guía, carpeta de Drive para escritorio o seguir con el de rclone."""
		carpeta = carpeta_drive_escritorio()
		opciones = [_("Crear mi &identificador (guía)")]
		if carpeta:
			opciones.append(_("Usar la carpeta de Google Drive para &escritorio"))
		opciones.append(_("&Seguir con el identificador de rclone mientras funcione"))
		texto = _("No ha escrito un identificador de cliente propio. El identificador compartido de rclone para Google se retira "
			"en 2026 y dejará de funcionar sin previo aviso.")
		if carpeta:
			texto += " " + _("Google Drive para escritorio está instalado en {c}.").format(c=carpeta)
		eleccion = comun.opcion(self.zc, texto, _("Google Drive sin identificador propio"), opciones)
		if eleccion is None:
			return False
		elegido = opciones[eleccion]
		if "identificador (gu" in elegido.replace("&", ""):
			self.mostrar_guia()
			return False
		if carpeta and "escritorio" in elegido:
			self.zc.abrir_ruta(carpeta)
			return False
		return True

	def _correr_alta(self, padre: wx.Window | None, alta: Alta, nombre_servicio: str, cuenta: Cuenta, secretos: dict[str, str], *,
			nuevo: bool = True, reconexion: bool = False) -> bool:
		from .asistente import DialogoPregunta

		def deshacer() -> None:
			alta.cancelar()
			if nuevo and not reconexion:
				self._en_hilo(lambda _t: self.nubes.borrar_remoto(cuenta.id), nombre="zc-nubes-deshacer")

		paso: Paso | None = self._esperar(padre, _("Añadir una cuenta de nube"), _("Preparando la cuenta en el motor de nubes..."),
			lambda tarea: alta.empezar(tarea))
		if paso is None:
			deshacer()
			return False
		while paso.tipo != "fin":
			if paso.tipo == "oauth":
				explicacion = _("Se abrirá el navegador para que inicie sesión en {s} y autorice a zCommander (rclone). Cuando termine, "
					"vuelva aquí: zCommander lo detectará solo.").format(s=nombre_servicio)
				dialogo = oauth.DialogoEspera(self.zc, padre, _("Autorizar {s}").format(s=nombre_servicio), explicacion, url=paso.url,
					otro_equipo=not reconexion, estado=_("Pulse Abrir el navegador o copie el enlace."))
				try:
					codigo = dialogo.lanzar(lambda tarea: alta.esperar(tarea), sonido_inicio="oauth_espera", sonido_fin="oauth_ok")
					siguiente = dialogo.resultado
				except Exception as error:  # noqa: BLE001 - se explica y se deshace el alta
					self._error(error)
					deshacer()
					return False
				finally:
					dialogo.Destroy()
				if codigo == oauth.OTRO_EQUIPO:
					alta.cancelar()
					alta.parametros["config_is_local"] = "false"
					alta.parametros.pop("config_auth_no_browser", None)
					paso = self._esperar(padre, _("Autorizar desde otro equipo"), _("Preparando la autorización..."),
						lambda tarea: alta.empezar(tarea))
					if paso is None:
						deshacer()
						return False
					continue
				if codigo != wx.ID_OK or siguiente is None:
					self.zc.anunciar(_("Autorización cancelada"), api.RESULTADO)
					deshacer()
					return False
				paso = siguiente
				continue
			valor = self._preguntar(padre, paso, nombre_servicio, DialogoPregunta)
			if valor is None:
				deshacer()
				return False
			anterior = paso
			paso = self._esperar(padre, _("Añadir una cuenta de nube"), _("Enviando la respuesta a rclone..."),
				lambda tarea, v=valor, p=anterior: alta.responder(v, p, tarea))
			if paso is None:
				deshacer()
				return False
		if reconexion:
			datos = self._esperar(padre, _("Volver a autorizar"), _("Comprobando la cuenta..."),
				lambda _t: (self.nubes.limpiar_cache(), self.nubes.comprobar(cuenta))[1])
			if datos is None:
				return False
			self.zc.sonidos.sonar("oauth_ok")
			self.zc.anunciar(_("Cuenta autorizada de nuevo: {n}. {e}").format(n=cuenta.nombre, e=self.nubes.texto_espacio(datos)),
				api.ESENCIAL)
			return True
		datos = self._esperar(padre, _("Añadir una cuenta de nube"), _("Comprobando la cuenta..."),
			lambda _t: self.nubes.terminar_alta(cuenta, secretos))
		if datos is None:
			return False
		self._cuenta_anadida(cuenta, datos)
		return True

	def _preguntar(self, padre: wx.Window | None, paso: Paso, nombre_servicio: str, clase: Any) -> str | None:
		if paso.es_token:
			orden = paso.orden_authorize() or "rclone authorize"
			dialogo = oauth.DialogoToken(self.zc, padre, orden, paso.ayuda)
			try:
				return dialogo.valor() if comun.mostrar_modal(self.zc, dialogo) == wx.ID_OK else None
			finally:
				dialogo.Destroy()
		dialogo = clase(self.zc, padre, paso, nombre_servicio)
		try:
			return dialogo.respuesta() if comun.mostrar_modal(self.zc, dialogo) == wx.ID_OK else None
		finally:
			dialogo.Destroy()

	def _cuenta_anadida(self, cuenta: Cuenta, datos: dict[str, Any]) -> None:
		self.zc.sonidos.sonar("conectar")
		texto = _("Cuenta añadida: {n}. {e}").format(n=cuenta.nombre, e=self.nubes.texto_espacio(datos))
		self.zc.anunciar(texto, api.ESENCIAL)
		eleccion = comun.opcion(self.zc, texto, _("Cuenta añadida"), [_("&Abrir ahora"), _("&Cerrar")])
		if eleccion == 0:
			self.zc.abrir_ruta(cuenta.direccion)

	def _alta_webdav(self, padre: wx.Window | None, servicio: Servicio, nombre: str, valores: dict[str, str],
			existente: Cuenta | None) -> Cuenta | None:
		url = valores.get("url", "").strip()
		if not url.lower().startswith(("http://", "https://")):
			comun.error(self.zc, _("La dirección WebDAV debe empezar por http:// o https://"))
			return None
		id = existente.id if existente else self.nubes.cuentas.id_libre(nombre)
		cuenta = Cuenta(id=id, nombre=nombre, servicio=servicio.id, motor="webdav", url=url, usuario=valores.get("user", ""),
			papelera=False)
		contrasena = valores.get("pass", "")

		def trabajo(_tarea: Any) -> dict[str, Any]:
			self.zc.secretos.guardar(f"webdav:{cuenta.id}:contrasena", contrasena)
			self.nubes.cuentas.guardar(cuenta)
			try:
				return self.nubes.comprobar(self.nubes.cuenta(cuenta.id))
			except api.ErrorArchivos:
				self.nubes.cuentas.quitar(cuenta.id)
				self.zc.secretos.borrar(f"webdav:{cuenta.id}:contrasena")
				raise

		datos = self._esperar(padre, _("Añadir un servidor WebDAV"), _("Comprobando la conexión con {u}...").format(u=url), trabajo)
		if datos is None:
			return None
		self._cuenta_anadida(cuenta, datos)
		return cuenta

	def nextcloud(self, ctx: api.ContextoComplemento) -> None:
		self.conectar_nextcloud(padre_por_defecto())

	def conectar_nextcloud(self, padre: wx.Window | None) -> Cuenta | None:
		servidor = comun.pedir(self.zc, _("&Dirección del servidor (por ejemplo https://nube.ejemplo.com):"),
			_("Conectar Nextcloud u ownCloud"))
		if not servidor:
			return None
		inicio = self._esperar(padre, _("Conectar Nextcloud u ownCloud"), _("Pidiendo al servidor el inicio de sesión..."),
			lambda _t: nextcloud.iniciar(self.zc.red, servidor))
		if inicio is None:
			return None
		explicacion = _("Se abrirá el navegador para que inicie sesión en su Nextcloud u ownCloud y conceda el acceso a zCommander. "
			"Cuando termine, vuelva aquí: zCommander lo detectará solo.")
		dialogo = oauth.DialogoEspera(self.zc, padre, _("Autorizar Nextcloud u ownCloud"), explicacion, url=inicio.login,
			estado=_("Pulse Abrir el navegador o copie el enlace."))
		try:
			codigo = dialogo.lanzar(lambda tarea: nextcloud.esperar_credenciales(self.zc.red, inicio, tarea),
				sonido_inicio="oauth_espera", sonido_fin="oauth_ok")
			credenciales = dialogo.resultado
		except Exception as error:  # noqa: BLE001 - se explica a la persona
			self._error(error)
			return None
		finally:
			dialogo.Destroy()
		if codigo != wx.ID_OK or credenciales is None:
			self.zc.anunciar(_("Autorización cancelada"), api.RESULTADO)
			return None
		anfitrion = urllib.parse.urlsplit(credenciales.servidor).hostname or credenciales.servidor
		nombre = _("{s} de {u}").format(s=anfitrion, u=credenciales.usuario)
		valores = {"url": credenciales.url_webdav, "user": credenciales.usuario, "pass": credenciales.contrasena_app}
		servicio = self.nubes.catalogo.servicio("nextcloud") or self.nubes.catalogo.servicio("webdav_nativo")
		return self._alta_webdav(padre, servicio, nombre, valores, None)  # type: ignore[arg-type]

	def propiedades(self, padre: wx.Window | None, cuenta: Cuenta) -> None:
		from .franjas import DialogoFranjas
		from .propiedades import DialogoPropiedades

		def editar_horario(ventana: wx.Window, horario: str) -> str | None:
			dialogo = DialogoFranjas(self.zc, ventana, horario)
			try:
				return dialogo.horario() if comun.mostrar_modal(self.zc, dialogo) == wx.ID_OK else None
			finally:
				dialogo.Destroy()

		secreto = self.zc.secretos.obtener(f"{cuenta.id}:client_secret") or ""
		dialogo = DialogoPropiedades(self.zc, padre, cuenta, self.nubes.catalogo.servicio(cuenta.servicio), secreto_cliente=secreto,
			copia_entre_cuentas_general=bool(self.nubes.opcion("copia_entre_cuentas", False)),
			cache_general=int(self.nubes.opcion("cache_listados_s", 30)), editar_horario=editar_horario)
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			nueva, cambios, secreto_nuevo = dialogo.resultado()
		finally:
			dialogo.Destroy()

		def guardar(_tarea: Any) -> None:
			if secreto_nuevo:
				self.zc.secretos.guardar(f"{nueva.id}:client_secret", secreto_nuevo)
			self.nubes.guardar_propiedades(nueva, cambios)

		if self._esperar(padre, _("Propiedades de la cuenta"), _("Guardando..."), lambda t: (guardar(t), True)[1]):
			self.zc.anunciar(_("Propiedades guardadas"), api.RESULTADO)

	def reconectar(self, ctx: api.ContextoComplemento) -> None:
		cuenta = self._cuenta_objetivo(ctx, solo_rclone=False, pregunta=_("¿Qué cuenta quiere volver a autorizar?"))
		if cuenta is not None:
			self.reconectar_cuenta(padre_por_defecto(), cuenta)

	def reconectar_cuenta(self, padre: wx.Window | None, cuenta: Cuenta, al_terminar: Callable[[], None] | None = None) -> None:
		servicio = self.nubes.catalogo.servicio(cuenta.servicio)
		if cuenta.volver_a_configurar or cuenta.motor == "webdav" or servicio is None or not servicio.es_oauth:
			if servicio is None:
				comun.error(self.zc, _("La cuenta {n} no se puede volver a autorizar desde aquí: elimínela y vuelva a crearla.").format(
					n=cuenta.nombre))
				return
			self.asistente(padre, servicio, existente=cuenta)
		else:
			alta = self.nubes.reconectar(cuenta)
			self._correr_alta(padre, alta, servicio.nombre, cuenta, {}, nuevo=False, reconexion=True)
		if al_terminar is not None:
			al_terminar()

	def eliminar_cuenta(self, cuenta: Cuenta, al_terminar: Callable[[], None] | None = None) -> None:
		def hecho(_r: Any) -> None:
			self.zc.sonidos.sonar("desconectar")
			self.zc.anunciar(_("Cuenta eliminada: {n}").format(n=cuenta.nombre), api.RESULTADO)
			if al_terminar is not None:
				al_terminar()

		self._en_hilo(lambda _t: self.nubes.eliminar_cuenta(cuenta), hecho, "zc-nubes-eliminar")

	def guia_google(self, ctx: api.ContextoComplemento) -> None:
		self.mostrar_guia()

	def mostrar_guia(self) -> None:
		ruta = self.nubes.carpeta / "doc" / "es" / "google-drive.md"
		texto = ruta.read_text(encoding="utf-8")
		modulo = comun.ui(self.zc)
		if modulo is None:
			self.zc.anunciar(_("Guía para conectar Google Drive"), api.RESULTADO)
			return
		try:
			modulo.mostrar_documento(documento_markdown(_("Guía para conectar Google Drive"), texto))
		except (AttributeError, api.NoAdmitido):
			modulo.mostrar_texto(_("Guía para conectar Google Drive"), texto)

	# ── Enlaces, papelera y espacio ─────────────────────────────────────────

	def _objetivo_panel(self, ctx: api.ContextoComplemento) -> tuple[Cuenta, str, str] | None:
		cuenta = self._cuenta_del_panel(ctx.activo)
		entrada = ctx.activo.cursor() if cuenta is not None else None
		if cuenta is None or cuenta.motor != "rclone":
			self.zc.anunciar(_("Esta orden funciona sobre un elemento de una cuenta de nube de rclone"), api.RESULTADO)
			return None
		if entrada is None:
			self.zc.anunciar(_("No hay ningún elemento en el cursor"), api.RESULTADO)
			return None
		return cuenta, entrada.ruta, entrada.nombre

	def enlace(self, ctx: api.ContextoComplemento) -> None:
		objetivo = self._objetivo_panel(ctx)
		if objetivo is None:
			return
		cuenta, ruta, nombre = objetivo
		caducidad = comun.pedir(self.zc, _("&Caducidad del enlace (vacía, sin caducidad; por ejemplo 7d o 12h):"),
			_("Enlace para compartir {n}").format(n=nombre))
		if caducidad is None:
			return

		def hecho(url: str) -> None:
			if url and comun.copiar_al_portapapeles(url):
				self.zc.anunciar(_("Enlace copiado"), api.RESULTADO, completo=url)
			else:
				comun.avisar(self.zc, _("Enlace de {n}: {u}").format(n=nombre, u=url))

		self._en_hilo(lambda _t: self.nubes.enlace(cuenta, ruta, caducidad.strip()), hecho, "zc-nubes-enlace")

	def quitar_enlace(self, ctx: api.ContextoComplemento) -> None:
		objetivo = self._objetivo_panel(ctx)
		if objetivo is None:
			return
		cuenta, ruta, nombre = objetivo
		if not comun.confirmar(self.zc, _("¿Quitar el enlace compartido de {n}? Quien lo tenga dejará de poder abrirlo.").format(n=nombre),
				_("Quitar el enlace compartido"), peligroso=True):
			return
		self._en_hilo(lambda _t: self.nubes.enlace(cuenta, ruta, quitar=True),
			lambda _r: self.zc.anunciar(_("Enlace quitado: {n}").format(n=nombre), api.RESULTADO), "zc-nubes-enlace")

	def vaciar_papelera(self, ctx: api.ContextoComplemento) -> None:
		cuenta = self._cuenta_objetivo(ctx, pregunta=_("¿De qué cuenta quiere vaciar la papelera?"))
		if cuenta is None:
			return
		if not comun.confirmar(self.zc, _("¿Vaciar la papelera de {n}? Lo que hay en ella se borrará para siempre.").format(
				n=cuenta.nombre), _("Vaciar la papelera de la nube"), peligroso=True):
			return
		self.zc.lanzar(OperacionRclone(self.nubes, _("Vaciar la papelera de {n}").format(n=cuenta.nombre), "operations/cleanup",
			{"fs": cuenta.remoto}, carriles=frozenset({carril(self.nubes, cuenta.remoto)})))

	def espacio(self, ctx: api.ContextoComplemento) -> None:
		cuenta = self._cuenta_objetivo(ctx, solo_rclone=False, pregunta=_("¿De qué cuenta quiere saber el espacio?"))
		if cuenta is not None:
			self.espacio_de(cuenta)

	# ── Sincronizar, emparejar, comprobar, duplicados ──────────────────────────

	def _fs(self, direccion: str) -> str | None:
		try:
			return self.nubes.fs_de(direccion)
		except api.ErrorArchivos as error:
			comun.error(self.zc, error.mensaje)
			return None

	def sincronizar(self, ctx: api.ContextoComplemento) -> None:
		from .sincronizar import TEXTO_CAMBIO, DialogoCambios, DialogoRutas

		padre = padre_por_defecto()
		dialogo = DialogoRutas(self.zc, padre, _("Sincronizar con la nube"), self.direccion_panel(ctx.activo),
			self.direccion_panel(ctx.pasivo), [("suma", _("Comparar por su&ma (más lento, más seguro)"),
				_("Compara el contenido en lugar del tamaño y la fecha."), False)],
			explicacion=_("Deja el destino igual que el origen: copia lo nuevo y lo cambiado y BORRA en el destino lo que no está en "
				"el origen. Antes se muestra una simulación."), con_copias=True)
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			origen, destino = dialogo.rutas()
			suma = dialogo.valor("suma")
			copias = dialogo.copias.GetValue().strip() if dialogo.copias is not None else ""
		finally:
			dialogo.Destroy()
		fs_origen, fs_destino = self._fs(origen), self._fs(destino)
		if not fs_origen or not fs_destino:
			return
		config: dict[str, Any] = {"CheckSum": True} if suma else {}
		parametros: dict[str, Any] = {"srcFs": fs_origen, "dstFs": fs_destino, "combined": True}
		if copias:
			fs_copias = self._fs(copias)
			if not fs_copias:
				return
			config["BackupDir"] = fs_copias
		simulacion = self._esperar(padre, _("Simular la sincronización"), _("Comparando las carpetas; no se cambia nada..."),
			lambda tarea: self.nubes.ejecutar("sync/sync", cancelacion=tarea, _config={**config, "DryRun": True}, **parametros))
		if simulacion is None:
			return
		grupos = resumen_informe(simulacion)
		filas = [(TEXTO_CAMBIO[c], r) for c in ("+", "*", "-", "!") for r in grupos[c]]
		resumen = _("Se copiarán {a}, se actualizarán {b} y se borrarán {c} en el destino.").format(a=len(grupos["+"]),
			b=len(grupos["*"]), c=len(grupos["-"]))
		cambios = DialogoCambios(self.zc, padre, _("Cambios de la sincronización"), resumen, filas, boton_accion=_("&Sincronizar"))
		try:
			if comun.mostrar_modal(self.zc, cambios) != wx.ID_OK:
				return
		finally:
			cambios.Destroy()
		self.zc.lanzar(OperacionRclone(self.nubes, _("Sincronizar {o} con {d}").format(o=origen, d=destino), "sync/sync",
			{**parametros, **({"_config": config} if config else {})},
			carriles=frozenset({carril(self.nubes, fs_origen), carril(self.nubes, fs_destino)}), sonido_fin="sincronizacion_fin"))

	def emparejar(self, ctx: api.ContextoComplemento) -> None:
		from .emparejar import DialogoEmparejar
		from .sincronizar import TEXTO_CAMBIO_COMPROBAR, DialogoCambios

		padre = padre_por_defecto()
		dialogo = DialogoEmparejar(self.zc, padre, self.direccion_panel(ctx.activo), self.direccion_panel(ctx.pasivo))
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			datos = dialogo.datos()
		finally:
			dialogo.Destroy()
		ruta1, ruta2 = self._fs(datos["carpeta1"]), self._fs(datos["carpeta2"])
		if not ruta1 or not ruta2:
			return
		self.nubes.rutas.bisync.mkdir(parents=True, exist_ok=True)
		parametros: dict[str, Any] = {"path1": ruta1, "path2": ruta2, "workdir": str(self.nubes.rutas.bisync),
			"maxDelete": int(datos["maximo"]), "conflictResolve": datos["conflictos"], "resilient": True, "recover": True}
		if datos["inicial"]:
			parametros["resync"] = True

		def simular(tarea: Any) -> tuple[dict, str]:
			comparacion: dict = {}
			try:
				comparacion = self.nubes.ejecutar("operations/check", cancelacion=tarea, conservar_salida=True, srcFs=ruta1,
					dstFs=ruta2, combined=True)
			except Exception as fallo:  # noqa: BLE001 - las diferencias hacen fallar check; se quiere su informe
				comparacion = getattr(fallo, "salida", {}) or {}
			try:
				self.nubes.ejecutar("sync/bisync", cancelacion=tarea, dryRun=True, **parametros)
			except api.Cancelado:
				raise
			except api.ErrorArchivos as error:
				return comparacion, error.mensaje
			return comparacion, ""

		resultado = self._esperar(padre, _("Simular el emparejamiento"), _("Comparando las dos carpetas; no se cambia nada..."), simular)
		if resultado is None:
			return
		comparacion, problema = resultado
		grupos = resumen_informe(comparacion)
		filas = [(TEXTO_CAMBIO_COMPROBAR[c], r) for c in ("+", "-", "*", "!") for r in grupos[c]]
		resumen = _("Solo en la primera: {a}. Solo en la segunda: {b}. Distintos: {c}.").format(a=len(grupos["+"]), b=len(grupos["-"]),
			c=len(grupos["*"]))
		if problema:
			if "resync" in problema.lower() or not datos["inicial"]:
				resumen += " " + _("La simulación avisa: {p}. Si es la primera vez, marque la sincronización inicial.").format(p=problema)
			else:
				resumen += " " + _("La simulación avisa: {p}").format(p=problema)
		cambios = DialogoCambios(self.zc, padre, _("Emparejar: simulación"), resumen, filas, boton_accion=_("&Emparejar"))
		try:
			if comun.mostrar_modal(self.zc, cambios) != wx.ID_OK:
				return
		finally:
			cambios.Destroy()

		def al_terminar(_salida: dict) -> None:
			conflictos = self._conflictos(ruta1, ruta2)
			texto = _("Emparejamiento terminado.") + " " + (_("Conflictos: {n} archivos renombrados con «conflict».").format(
				n=len(conflictos)) if conflictos else _("Sin conflictos."))
			self.zc.anunciar(texto, api.RESULTADO, completo=texto + ("\n" + "\n".join(conflictos[:50]) if conflictos else ""))

		self.zc.lanzar(OperacionRclone(self.nubes, _("Emparejar {a} y {b}").format(a=datos["carpeta1"], b=datos["carpeta2"]), "sync/bisync",
			parametros, carriles=frozenset({carril(self.nubes, ruta1), carril(self.nubes, ruta2)}), al_terminar=al_terminar,
			sonido_fin="sincronizacion_fin"))

	def _conflictos(self, *rutas: str) -> list[str]:
		encontrados: list[str] = []
		for fs in rutas:
			try:
				datos = self.nubes.llamar("operations/list", fs=fs, remote="", opt={"recurse": True, "filesOnly": True,
					"noMimeType": True, "noModTime": True})
			except api.ErrorArchivos:
				continue
			encontrados.extend(f"{fs}/{d.get('Path')}" for d in datos.get("list", []) if ".conflict" in str(d.get("Name", "")))
		return encontrados

	def comprobar(self, ctx: api.ContextoComplemento) -> None:
		from .sincronizar import TEXTO_CAMBIO_COMPROBAR, DialogoCambios, DialogoRutas

		padre = padre_por_defecto()
		dialogo = DialogoRutas(self.zc, padre, _("Comprobar carpetas"), self.direccion_panel(ctx.activo), self.direccion_panel(ctx.pasivo),
			[("bajar", _("&Bajar para comparar (lento; para servicios sin sumas)"),
				_("Compara bajando el contenido en lugar de usar las sumas del servicio."), False)],
			boton_aceptar=_("Co&mprobar"), explicacion=_("Compara las dos carpetas por tamaño y suma, sin cambiar nada."))
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			origen, destino = dialogo.rutas()
			bajar = dialogo.valor("bajar")
		finally:
			dialogo.Destroy()
		fs_origen, fs_destino = self._fs(origen), self._fs(destino)
		if not fs_origen or not fs_destino:
			return

		def mostrar(salida: dict) -> None:
			grupos = resumen_informe(salida)
			filas = [(TEXTO_CAMBIO_COMPROBAR[c], r) for c in ("*", "+", "-", "!") for r in grupos[c]]
			resumen = _("Iguales: {i}. Distintos: {d}. Solo en el origen: {o}. Solo en el destino: {s}. Errores: {e}.").format(
				i=len(grupos["="]), d=len(grupos["*"]), o=len(grupos["+"]), s=len(grupos["-"]), e=len(grupos["!"]))
			self.zc.anunciar(resumen, api.RESULTADO)

			def abrir() -> None:
				ventana = DialogoCambios(self.zc, padre_por_defecto(), _("Resultado de la comprobación"), resumen, filas)
				try:
					comun.mostrar_modal(self.zc, ventana)
				finally:
					ventana.Destroy()

			wx.CallAfter(abrir)

		operacion = OperacionRclone(self.nubes, _("Comprobar {o} y {d}").format(o=origen, d=destino), "operations/check",
			{"srcFs": fs_origen, "dstFs": fs_destino, "combined": True, "match": True, "download": bajar},
			carriles=frozenset({carril(self.nubes, fs_origen), carril(self.nubes, fs_destino)}), al_terminar=mostrar)
		operacion.aceptar_diferencias = True
		self.zc.lanzar(operacion)

	def duplicados(self, ctx: api.ContextoComplemento) -> None:
		from .sincronizar import DialogoDuplicados, DialogoInforme

		padre = padre_por_defecto()
		propia = self._cuenta_del_panel(ctx.activo)
		cuentas = self._opciones_cuentas()
		if not cuentas:
			self.zc.anunciar(_("No hay cuentas de nube; añada una con Añadir una cuenta de nube"), api.RESULTADO)
			return
		dialogo = DialogoDuplicados(self.zc, padre, cuentas, propia.id if propia else "", ctx.activo.ruta if propia else "/")
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			cuenta = self.nubes.cuenta(comun.valor_elegido(dialogo.cuenta))
			carpeta, modo = dialogo.carpeta.GetValue().strip() or "/", comun.valor_elegido(dialogo.modo)
			por_contenido = dialogo.por_contenido.GetValue()
		finally:
			dialogo.Destroy()
		for paso, titulo, boton in (("list", _("Nombres duplicados"), _("&Simular la acción")),
				("simular", _("Simulación de la acción"), _("&Aplicar la acción"))):
			informe = self._esperar(padre, titulo, _("Buscando nombres duplicados en {n}...").format(n=cuenta.nombre),
				lambda _t, p=paso: self.nubes.duplicados(cuenta, carpeta, "list" if p == "list" else modo, True, por_contenido))
			if informe is None:
				return
			ventana = DialogoInforme(self.zc, padre, titulo, informe, boton)
			try:
				if comun.mostrar_modal(self.zc, ventana) != wx.ID_OK:
					return
			finally:
				ventana.Destroy()
		resultado = self._esperar(padre, _("Resolver duplicados"), _("Aplicando la acción en {n}...").format(n=cuenta.nombre),
			lambda _t: self.nubes.duplicados(cuenta, carpeta, modo, False, por_contenido))
		if resultado is not None:
			self.zc.anunciar(_("Duplicados resueltos en {n}").format(n=cuenta.nombre), api.RESULTADO)

	# ── Carpetas cifradas y uniones ────────────────────────────────────────────

	def cifrada(self, ctx: api.ContextoComplemento) -> None:
		from .cifrada import DialogoCifrada

		cuentas = self._opciones_cuentas()
		if not cuentas:
			self.zc.anunciar(_("No hay cuentas de nube; añada una con Añadir una cuenta de nube"), api.RESULTADO)
			return
		padre = padre_por_defecto()
		propia = self._cuenta_del_panel(ctx.activo)
		dialogo = DialogoCifrada(self.zc, padre, cuentas, propia.id if propia else "")
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			datos = dialogo.datos()
		finally:
			dialogo.Destroy()
		base = self.nubes.cuenta(datos["cuenta"])
		nueva = self._esperar(padre, _("Crear una carpeta cifrada"), _("Creando la carpeta cifrada..."),
			lambda _t: self.nubes.crear_cifrada(base, datos["carpeta"], datos["nombre"], datos["contrasena"], datos["sal"], datos["nombres"]))
		if nueva is not None:
			self._cuenta_anadida(nueva, {})

	def union(self, ctx: api.ContextoComplemento) -> None:
		from .union import DialogoUnion

		cuentas = self._opciones_cuentas()
		if len(cuentas) < 2:
			self.zc.anunciar(_("Hacen falta al menos dos cuentas de nube de rclone para unirlas"), api.RESULTADO)
			return
		padre = padre_por_defecto()
		dialogo = DialogoUnion(self.zc, padre, cuentas)
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			datos = dialogo.datos()
		finally:
			dialogo.Destroy()
		elegidas = [self.nubes.cuenta(i) for i in datos["cuentas"]]
		nueva = self._esperar(padre, _("Unir cuentas"), _("Creando la unidad..."),
			lambda _t: self.nubes.crear_union(datos["nombre"], elegidas, datos["tipo"], datos["politica"]))
		if nueva is not None:
			self._cuenta_anadida(nueva, {})

	# ── Montar y servir ─────────────────────────────────────────────────────

	def montar(self, ctx: api.ContextoComplemento) -> None:
		from ..servicio import winfsp_instalado
		from .montar import DialogoMontar

		if not winfsp_instalado():
			if comun.confirmar(self.zc, _("Para montar una nube como letra de unidad hace falta WinFsp (Windows File System Proxy), un "
					"controlador libre que instala usted con permisos de administrador; zCommander no lo instala. ¿Abrir su página "
					"de descarga?"), _("Falta WinFsp")):
				comun.abrir_navegador(URL_WINFSP)
			return
		cuentas = self._opciones_cuentas()
		if not cuentas:
			self.zc.anunciar(_("No hay cuentas de nube; añada una con Añadir una cuenta de nube"), api.RESULTADO)
			return
		padre = padre_por_defecto()
		propia = self._cuenta_del_panel(ctx.activo)
		dialogo = DialogoMontar(self.zc, padre, cuentas, propia.id if propia else "")
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			datos = dialogo.datos()
		finally:
			dialogo.Destroy()
		cuenta = self.nubes.cuenta(datos["cuenta"])
		punto = self._esperar(padre, _("Montar como letra de unidad"), _("Montando {n}...").format(n=cuenta.nombre),
			lambda _t: self.nubes.montar(cuenta, datos["letra"], datos["modo"], datos["volumen"], datos["red"]))
		if punto:
			self.zc.sonidos.sonar("montada")
			self.zc.anunciar(_("{n} montada en {p}").format(n=cuenta.nombre, p=punto), api.RESULTADO)

	def montajes(self, ctx: api.ContextoComplemento) -> None:
		from .montar import DialogoMontajes

		padre = padre_por_defecto()

		def desmontar(punto: str) -> None:
			pendientes = self.nubes.pendientes_subida()
			if pendientes and not comun.confirmar(self.zc, _("Quedan {n} archivos por subir. Si desmonta ahora, se perderán. ¿Desmontar "
					"de todos modos?").format(n=pendientes), _("Desmontar"), peligroso=True):
				return
			if self._esperar(padre, _("Desmontar"), _("Desmontando {p}...").format(p=punto), lambda _t: (self.nubes.desmontar(punto), True)[1]):
				self.zc.anunciar(_("{p} desmontada").format(p=punto), api.RESULTADO)

		dialogo = DialogoMontajes(self.zc, padre, self.nubes.montajes, desmontar)
		try:
			comun.mostrar_modal(self.zc, dialogo)
		finally:
			dialogo.Destroy()

	def servir(self, ctx: api.ContextoComplemento) -> None:
		from .servir import DialogoServir

		padre = padre_por_defecto()
		origenes = [(c.remoto, c.nombre) for c in self._cuentas(solo_rclone=True)]
		local = self.direccion_panel(ctx.activo)
		if local and not local.startswith("nube://"):
			origenes.insert(0, (local, _("Carpeta del panel activo: {c}").format(c=local)))
		propia = self._cuenta_del_panel(ctx.activo)
		if not origenes:
			self.zc.anunciar(_("No hay nada que compartir: abra una carpeta local o añada una cuenta de nube"), api.RESULTADO)
			return
		solo_local = bool(self.nubes.opcion("servir_solo_local", True))
		dialogo = DialogoServir(self.zc, padre, origenes, propia.remoto if propia else origenes[0][0], solo_local=solo_local)
		try:
			if comun.mostrar_modal(self.zc, dialogo) != wx.ID_OK:
				return
			datos = dialogo.datos()
		finally:
			dialogo.Destroy()
		if datos["red"] and not comun.confirmar(self.zc, _("Cualquier equipo de su red local podrá conectarse con el usuario y la "
				"contraseña. Windows puede preguntar si permite el acceso en su cortafuegos. ¿Compartir en la red?"),
				_("Compartir en la red local"), peligroso=True):
			return
		fs = datos["origen"]
		if os.path.isabs(fs):
			fs = fs.replace("\\", "/")
		resultado = self._esperar(padre, _("Compartir en la red"), _("Arrancando el servidor..."),
			lambda _t: self.nubes.servir(datos["tipo"], fs, solo_local=not datos["red"], puerto=datos["puerto"], usuario=datos["usuario"],
				contrasena=datos["contrasena"], solo_lectura=datos["solo_lectura"]))
		if resultado:
			direccion = resultado["addr"]
			texto = _("Compartido por {t} en {d}.").format(t=datos["tipo"].upper(), d=direccion)
			if datos["tipo"] != "dlna":
				texto += " " + _("Usuario {u}, contraseña {c}.").format(u=datos["usuario"], c=datos["contrasena"])
			comun.avisar(self.zc, texto, _("Compartir en la red"))

	def servicios_activos(self, ctx: api.ContextoComplemento) -> None:
		from .servir import DialogoServicios

		padre = padre_por_defecto()

		def parar(id: str) -> None:
			if self._esperar(padre, _("Dejar de compartir"), _("Parando el servidor..."), lambda _t: (self.nubes.dejar_de_servir(id), True)[1]):
				self.zc.anunciar(_("Se ha dejado de compartir"), api.RESULTADO)

		dialogo = DialogoServicios(self.zc, padre, self.nubes.servicios_activos, parar)
		try:
			comun.mostrar_modal(self.zc, dialogo)
		finally:
			dialogo.Destroy()

	def limites(self, ctx: api.ContextoComplemento) -> None:
		if not self.nubes.motor.vivo():
			self.nubes.limites_pausados = not self.nubes.limites_pausados
			self.zc.anunciar(_("Límites de velocidad en pausa") if self.nubes.limites_pausados else _("Límites de velocidad reanudados"),
				api.RESULTADO)
			return
		self._en_hilo(lambda _t: self.nubes.alternar_limites(), lambda pausados: self.zc.anunciar(
			_("Límites de velocidad en pausa") if pausados else _("Límites de velocidad reanudados"), api.RESULTADO), "zc-nubes-limites")
