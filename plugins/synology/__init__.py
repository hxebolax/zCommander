# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""NAS Synology (``zc.synology``, bloque NS; diseño 2.0, sección 13).

Administra un NAS Synology con DSM desde zCommander, en **solo lectura por
defecto**: estado y salud, almacenamiento, File Station como origen del panel
(``synology://``), carpetas, usuarios, paquetes, contenedores, Drive, Photos,
tareas, registros, avisos, red, seguridad, servicios, monitor, actualizaciones
y apagar o reiniciar con doble confirmación. Incluye un «NAS de
demostración» (el simulador DSM local) para practicar sin riesgo.

``activar`` es barato (se activa al arrancar para que las direcciones
``synology://`` de la sesión funcionen): solo registra funciones; la interfaz,
el cliente y el simulador se importan cuando hacen falta.
"""

from __future__ import annotations

import logging
from typing import Any

from app.plugins import api

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology")

ORDENES = ("estado", "conectar", "desconectar", "abrir_archivos", "area", "tareas_fondo", "enlace", "comprimir", "extraer",
	"modo_escritura", "demostracion", "ssh", "reiniciar", "apagar")


class Complemento(api.Complemento):
	def __init__(self) -> None:
		self.zc: Any = None
		self.almacen: Any = None
		self.conexiones: Any = None
		self._ventanas: dict[str, Any] = {}
		self._quitar_oyente: Any = None

	# ── Ciclo de vida ────────────────────────────────────────────────────────

	def activar(self, zc: api.Anfitrion) -> None:
		from .busqueda import crear_motor
		from .conexiones import Conexiones
		from .proveedor import ESQUEMA, crear_fabrica
		from .servidores import AlmacenServidores

		self.zc = zc
		# Las carpetas de datos y de caché se piden al usarlas: activar no crea nada en data/.
		self.almacen = AlmacenServidores(lambda: zc.datos)
		self.conexiones = Conexiones(self.almacen, self._secretos(), ajuste=self.ajuste, sonar=self._sonar,
			carpeta_temporal=lambda: zc.cache / "subidas")
		self._quitar_oyente = self.conexiones.suscribir(self._al_cambiar_conexion)
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, getattr(self, f"_orden_{id_corto}"))
		zc.ordenes.estado("modo_escritura", self._estado_modo_escritura)
		for id_corto in ("enlace", "comprimir", "extraer"):
			zc.ordenes.disponible(id_corto, self._en_panel_nas)
		zc.vfs.esquema(ESQUEMA, crear_fabrica(self.conexiones, self._preguntas_hilo))
		zc.vfs.unidades(self._unidades)
		zc.busqueda.proveedor("filestation", crear_motor(self.conexiones))
		if api.interfaz() is not None:
			zc.preferencias.dialogo(self._dialogo_preferencias)

	def desactivar(self) -> None:
		"""Al cerrar zCommander: cierra las ventanas, hace ``logout`` en cada NAS y para el NAS de demostración."""
		for ventana in list(self._ventanas.values()):
			try:
				ventana.cerrada = True
				ventana.marco.Destroy()
			except Exception:  # noqa: BLE001 - al cerrar, una ventana ya destruida no impide lo demás
				log.debug("No se pudo cerrar una ventana del NAS", exc_info=True)
		self._ventanas.clear()
		if self._quitar_oyente is not None:
			self._quitar_oyente()
		if self.conexiones is not None and self.conexiones.activas():
			# El «logout» va en un hilo con un tope: un NAS que no responde no retrasa el cierre de zCommander.
			import threading

			hilo = threading.Thread(target=self.conexiones.desconectar_todas, name="zc-synology-cierre", daemon=True)
			hilo.start()
			hilo.join(1.5)
			if hilo.is_alive():
				log.warning("El cierre de sesión con algún NAS no terminó a tiempo; se abandona")

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""Diálogos sin mostrar para ``revisar_teclado`` (la ventana del NAS necesita una conexión: la prueban las pruebas del bloque)."""
		if api.interfaz() is None:
			return []
		from .servidores import ServidorNAS
		from .ui import dialogos

		servidor = ServidorNAS("revision", "NAS de revisión", "192.0.2.10")
		return [dialogos.DialogoServidores(padre, self), dialogos.DialogoServidor(padre, None, set()),
			dialogos.DialogoModoEscritura(padre, "NAS"), dialogos.DialogoCodigo(padre, servidor, "Código"),
			dialogos.DialogoHuella(padre, servidor, "SHA256:" + "AB" * 32, ""), dialogos.DialogoAreas(padre, ["Estado y salud"]),
			dialogos.DialogoEnlace(padre, ["/Documentos/notas.txt"]), dialogos.DialogoComprimir(padre, "notas.zip", 1),
			dialogos.DialogoExtraer(padre, "notas.zip", "/Documentos")]

	# ── Servicios internos ───────────────────────────────────────────────────

	def ajuste(self, clave: str, defecto: Any = None) -> Any:
		if self.zc is None:
			return defecto
		try:
			return self.zc.config.obtener(clave, defecto)
		except Exception:  # noqa: BLE001 - sin configuración (pruebas sin data/) se usa el valor de fábrica
			log.debug("Sin la clave %s", clave, exc_info=True)
			return defecto

	def _secretos(self) -> Any:
		return self.zc.secretos if "secretos" in self.zc.permisos else None

	def _sonar(self, evento: str) -> None:
		try:
			self.zc.sonidos.sonar(evento)
		except Exception:  # noqa: BLE001 - un sonido nunca impide nada
			log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)

	def tiene_contrasena(self, servidor: Any) -> bool:
		secretos = self._secretos()
		try:
			return bool(secretos and secretos.obtener(f"{servidor.id}:contrasena"))
		except Exception:  # noqa: BLE001 - un almacén ilegible cuenta como «sin contraseña»
			log.debug("No se pudo leer la contraseña de %s", servidor.id, exc_info=True)
			return False

	def olvidar_secretos(self, id_servidor: str) -> None:
		secretos = self._secretos()
		if secretos is None:
			return
		for nombre in ("contrasena", "device_id"):
			try:
				secretos.borrar(f"{id_servidor}:{nombre}")
			except Exception:  # noqa: BLE001 - borrar lo que no está no es un fallo
				log.debug("No se pudo borrar %s de %s", nombre, id_servidor, exc_info=True)

	def _preguntas_hilo(self) -> Any:
		"""Preguntas para conectar desde un hilo (el del listado del panel): diálogos propios o, sin ventana, el ``Decisor``."""
		if api.interfaz() is not None:
			from .ui.dialogos import PreguntasInterfaz

			return PreguntasInterfaz()
		from .preguntas import PreguntasDecisor

		try:
			return PreguntasDecisor(self.zc.decisor)
		except api.NoAdmitido:
			return None

	def _unidades(self) -> list[api.UnidadVirtual]:
		"""Entradas del selector de unidades: los NAS guardados y el de demostración si está en marcha."""
		resultado = []
		vistos = set()
		for conexion in self.conexiones.activas():
			vistos.add(conexion.servidor.id)
			resultado.append(api.UnidadVirtual(conexion.servidor.nombre, conexion.servidor.direccion,
				_("NAS conectado, {m}").format(m=_("solo lectura") if conexion.solo_lectura else _("cambios permitidos"))))
		for servidor in self.almacen.todos():
			if servidor.id not in vistos:
				resultado.append(api.UnidadVirtual(servidor.nombre, servidor.direccion, _("NAS sin conectar")))
		return resultado

	def _al_cambiar_conexion(self, id_servidor: str, suceso: str) -> None:
		interfaz = api.interfaz()
		if interfaz is None:
			return

		def aplicar() -> None:
			ventana = self._ventanas.get(id_servidor)
			if ventana is None or ventana.cerrada:
				return
			if suceso == "desconectado":
				ventana.cerrada = True
				ventana.marco.Destroy()
				self._ventanas.pop(id_servidor, None)
			elif suceso == "modo":
				ventana.actualizar_modo()

		interfaz.planificar(aplicar)

	def ventana_cerrada(self, ventana: Any) -> None:
		for clave, valor in list(self._ventanas.items()):
			if valor is ventana:
				del self._ventanas[clave]

	def _padre(self) -> Any:
		import wx

		return wx.GetApp().GetTopWindow() if wx.GetApp() else None

	# ── Conectar y elegir el NAS ─────────────────────────────────────────────

	def _conectar(self, servidor: Any, despues: Any) -> None:
		from .ui.dialogos import PreguntasInterfaz

		zc = self.zc
		zc.anunciar(_("Conectando con {n}...").format(n=servidor.nombre), api.NORMAL)
		preguntas = PreguntasInterfaz()

		def trabajo(tarea: Any) -> Any:
			return self.conexiones.conectar(servidor, preguntas, tarea.token)

		def hecho(conexion: Any) -> None:
			info = conexion.info
			zc.anunciar(_("Conectado con {n}: {r}").format(n=servidor.nombre, r=info.resumen()), api.RESULTADO)
			if info.aviso:
				zc.ui.mostrar_mensaje(info.aviso, _("Aviso de seguridad del NAS"))
			despues(conexion)

		zc.tareas.enviar(trabajo, al_terminar=hecho, al_fallar=lambda e: self._fallo(_("No se ha podido conectar con {n}").format(
			n=servidor.nombre), e), nombre=f"nas-conectar-{servidor.id}")

	def _fallo(self, titulo: str, error: BaseException) -> None:
		if isinstance(error, api.Cancelado):
			self.zc.anunciar(_("Cancelado"), api.NORMAL)
			return
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
		if not isinstance(error, api.ErrorArchivos):
			log.error("%s", titulo, exc_info=error)
		self.zc.anunciar(f"{titulo}: {mensaje}", api.ESENCIAL)
		try:
			self.zc.ui.mostrar_error(mensaje, titulo)
		except api.NoAdmitido:
			log.debug("Sin ventana para mostrar el error", exc_info=True)

	def _con_conexion(self, ctx: api.ContextoComplemento | None, accion: Any, pedir_si_no_hay: bool = True) -> None:
		"""Llama a ``accion(conexion)`` con el NAS del panel, el único conectado o el que elija la persona; conecta si hace falta."""
		conexion = self._conexion_del_panel(ctx)
		if conexion is not None:
			accion(conexion)
			return
		activas = self.conexiones.activas()
		if len(activas) == 1:
			accion(activas[0])
			return
		if len(activas) > 1:
			indice = self.zc.ui.elegir_opcion(_("¿Con qué NAS?"), _("NAS Synology"), [f"&{i + 1} {c.servidor.nombre}"
				for i, c in enumerate(activas[:9])])
			if indice is not None:
				accion(activas[indice])
			return
		if not pedir_si_no_hay:
			self.zc.anunciar(_("No hay ningún NAS conectado."), api.NORMAL)
			return
		guardados = self.almacen.todos()
		if len(guardados) == 1:
			self._conectar(guardados[0], accion)
			return
		self._dialogo_servidores(accion)

	def _conexion_del_panel(self, ctx: api.ContextoComplemento | None) -> Any:
		if ctx is None:
			return None
		from .proveedor import ProveedorSynology

		try:
			proveedor = ctx.activo.proveedor
		except Exception:  # noqa: BLE001 - un panel sin proveedor no es un panel del NAS
			return None
		if isinstance(proveedor, ProveedorSynology):
			return self.conexiones.obtener(proveedor.id_servidor)
		return None

	def _dialogo_servidores(self, despues: Any = None) -> None:
		import wx

		from .ui.dialogos import DialogoServidores

		dialogo = DialogoServidores(self._padre(), self)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			accion, elegido = dialogo.accion, dialogo.elegido
		finally:
			dialogo.Destroy()
		destino = despues or (lambda conexion: self.abrir_ventana(conexion))
		if accion == DialogoServidores.DEMOSTRACION:
			self._iniciar_demostracion(destino)
		elif elegido is not None:
			existente = self.conexiones.obtener(elegido.id)
			if existente is not None:
				destino(existente)
			else:
				self._conectar(elegido, destino)

	def _dialogo_preferencias(self, padre: Any) -> None:
		"""«Abrir la configuración avanzada...» de Preferencias: la lista de NAS con sus conexiones (13.11)."""
		self._dialogo_servidores()

	# ── Ventana ──────────────────────────────────────────────────────────────

	def abrir_ventana(self, conexion: Any, area: str = "estado", seccion: str = "") -> None:
		from .ui.ventana import VentanaNAS

		ventana = self._ventanas.get(conexion.servidor.id)
		if ventana is not None and not ventana.cerrada:
			ventana.ir_a_area(area, seccion)
			ventana.marco.Raise()
			return
		ventana = VentanaNAS(self, conexion, area, seccion)
		self._ventanas[conexion.servidor.id] = ventana
		ventana.mostrar()

	def cambiar_modo(self, conexion: Any, permitir: bool, padre: Any = None) -> None:
		from .ui.dialogos import DialogoModoEscritura

		if permitir:
			persistente = self.ajuste("escritura_hasta", "sesion") == "siempre"
			aceptado, persistente = DialogoModoEscritura.preguntar(padre or self._padre(), conexion.servidor.nombre, persistente)
			if not aceptado:
				self.zc.anunciar(_("El NAS sigue en solo lectura"), api.NORMAL)
				return
			self.conexiones.cambiar_modo(conexion.servidor.id, True, persistente and not conexion.demostracion)
			self.zc.anunciar(_("Cambios permitidos en {n}").format(n=conexion.servidor.nombre), api.ESENCIAL)
		else:
			self.conexiones.cambiar_modo(conexion.servidor.id, False)
			self.zc.anunciar(_("{n} vuelve a solo lectura").format(n=conexion.servidor.nombre), api.ESENCIAL)

	def desconectar_conexion(self, conexion: Any) -> None:
		nombre = conexion.servidor.nombre
		self.zc.tareas.enviar(lambda _t: self.conexiones.desconectar(conexion.servidor.id),
			al_terminar=lambda _r: self.zc.anunciar(_("Desconectado de {n}").format(n=nombre), api.RESULTADO),
			al_fallar=lambda e: self._fallo(_("No se ha podido desconectar de {n}").format(n=nombre), e), nombre="nas-desconectar")

	def decir_estado(self, conexion: Any) -> None:
		from .areas import texto_monitor

		def trabajo(_tarea: Any) -> str:
			uso = conexion.cliente.llamar("SYNO.Core.System.Utilization", "get", type="current")
			return ". ".join(f"{a}: {b}" for a, b in texto_monitor(uso))

		self.zc.tareas.enviar(trabajo, al_terminar=lambda texto: self.zc.anunciar(texto, api.RESULTADO),
			al_fallar=lambda e: self._fallo(_("No se ha podido leer el uso del NAS"), e), nombre="nas-decir-estado")

	def _iniciar_demostracion(self, despues: Any = None) -> None:
		modo = str(self.ajuste("demostracion_modo", "escritura"))
		self.zc.anunciar(_("Arrancando el NAS de demostración..."), api.NORMAL)
		destino = despues or (lambda conexion: self.abrir_ventana(conexion))

		def hecho(conexion: Any) -> None:
			self.zc.anunciar(_("NAS de demostración en marcha, en solo lectura. Los cambios se pierden al cerrar."), api.RESULTADO)
			destino(conexion)

		self.zc.tareas.enviar(lambda tarea: self.conexiones.demostracion(modo, tarea.token), al_terminar=hecho,
			al_fallar=lambda e: self._fallo(_("No se ha podido arrancar el NAS de demostración"), e), nombre="nas-demostracion")

	# ── Órdenes ──────────────────────────────────────────────────────────────

	def _orden_estado(self, ctx: api.ContextoComplemento) -> None:
		self._con_conexion(ctx, lambda conexion: self.abrir_ventana(conexion, "estado"))

	def _orden_conectar(self, ctx: api.ContextoComplemento) -> None:
		self._dialogo_servidores()

	def _orden_desconectar(self, ctx: api.ContextoComplemento) -> None:
		self._con_conexion(ctx, self.desconectar_conexion, pedir_si_no_hay=False)

	def _orden_abrir_archivos(self, ctx: api.ContextoComplemento) -> None:
		self._con_conexion(ctx, lambda conexion: self.zc.abrir_ruta(conexion.servidor.direccion, "activo"))

	def _orden_area(self, ctx: api.ContextoComplemento) -> None:
		def elegir(conexion: Any) -> None:
			import wx

			from .areas import disponibles
			from .ui.dialogos import DialogoAreas

			lista = disponibles(conexion.cliente)
			dialogo = DialogoAreas(self._padre(), [a.titulo for a in lista])
			try:
				if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
					return
				indice = dialogo.lista.GetSelection()
			finally:
				dialogo.Destroy()
			if 0 <= indice < len(lista):
				self.abrir_ventana(conexion, lista[indice].id)

		self._con_conexion(ctx, elegir)

	def _orden_tareas_fondo(self, ctx: api.ContextoComplemento) -> None:
		self._con_conexion(ctx, lambda conexion: self.abrir_ventana(conexion, "archivos", "tareas"), pedir_si_no_hay=False)

	def _en_panel_nas(self, ctx: api.ContextoComplemento) -> bool:
		return self._conexion_del_panel(ctx) is not None

	def _panel_nas(self, ctx: api.ContextoComplemento) -> Any:
		conexion = self._conexion_del_panel(ctx)
		if conexion is None:
			self.zc.anunciar(_("Esta orden funciona en un panel que muestra un NAS (synology://)."), api.NORMAL)
		return conexion

	def _orden_enlace(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .ui.dialogos import DialogoEnlace

		conexion = self._panel_nas(ctx)
		if conexion is None:
			return
		elementos = ctx.activo.elementos_trabajo()
		if not elementos:
			self.zc.anunciar(_("No hay ningún elemento elegido"), api.NORMAL)
			return
		if conexion.solo_lectura:
			from .errores import solo_lectura

			self.zc.anunciar(solo_lectura(conexion.servidor.nombre).mensaje, api.ESENCIAL)
			return
		rutas = [e.ruta for e in elementos]
		dialogo = DialogoEnlace(self._padre(), rutas)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			contrasena, caduca = dialogo.contrasena.GetValue(), dialogo.caduca.GetValue().strip()
		finally:
			dialogo.Destroy()

		def trabajo(_tarea: Any) -> list[dict[str, Any]]:
			parametros: dict[str, Any] = {"path": rutas}
			if contrasena:
				parametros["password"] = contrasena
			if caduca:
				parametros["date_expired"] = caduca
			return conexion.cliente.llamar("SYNO.FileStation.Sharing", "create", parametros=parametros).get("links", [])

		def hecho(enlaces: list[dict[str, Any]]) -> None:
			from .ui.dialogos import copiar_al_portapapeles

			texto = "\n".join(f"{e.get('name')}: {e.get('url')}" for e in enlaces)
			copiar_al_portapapeles("\n".join(str(e.get("url")) for e in enlaces))
			self.zc.anunciar(_n("Enlace creado y copiado al portapapeles", "{n} enlaces creados y copiados al portapapeles",
				len(enlaces)).format(n=len(enlaces)), api.RESULTADO)
			self.zc.ui.mostrar_texto(_("Enlaces compartidos"), texto)

		self.zc.tareas.enviar(trabajo, al_terminar=hecho, al_fallar=lambda e: self._fallo(_("No se ha podido crear el enlace"), e),
			nombre="nas-enlace")

	def _lanzar_tarea(self, conexion: Any, api_nombre: str, parametros: dict[str, Any], texto: str, carpeta: str, ctx: Any) -> None:
		from .operaciones import OperacionNAS

		operacion = OperacionNAS(conexion.cliente, api_nombre, parametros, texto, carpeta, conexion.servidor.id)

		def al_terminar(op: Any) -> None:
			self._sonar("tarea_fin")
			try:
				ctx.activo.refrescar()
			except Exception:  # noqa: BLE001 - el panel puede haber cambiado; no es un fallo
				log.debug("No se pudo refrescar el panel", exc_info=True)

		self.zc.lanzar(operacion, al_terminar=al_terminar)

	def _orden_comprimir(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .ui.dialogos import DialogoComprimir

		conexion = self._panel_nas(ctx)
		if conexion is None:
			return
		elementos = ctx.activo.elementos_trabajo()
		if not elementos:
			self.zc.anunciar(_("No hay ningún elemento elegido"), api.NORMAL)
			return
		if conexion.solo_lectura:
			from .errores import solo_lectura

			self.zc.anunciar(solo_lectura(conexion.servidor.nombre).mensaje, api.ESENCIAL)
			return
		carpeta = ctx.activo.ruta or "/"
		base = elementos[0].nombre_sin_extension if len(elementos) == 1 else carpeta.rstrip("/").rsplit("/", 1)[-1] or "archivos"
		dialogo = DialogoComprimir(self._padre(), f"{base}.zip", len(elementos))
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			valores = dialogo.valores()
		finally:
			dialogo.Destroy()
		if not valores["nombre"]:
			return
		destino = f"{carpeta.rstrip('/')}/{valores['nombre']}"
		parametros: dict[str, Any] = {"path": [e.ruta for e in elementos], "dest_file_path": destino, "level": valores["nivel"],
			"mode": "add", "format": valores["formato"]}
		if valores["contrasena"]:
			parametros["password"] = valores["contrasena"]
		self._lanzar_tarea(conexion, "SYNO.FileStation.Compress", parametros, _("Comprimir en el NAS: {n}").format(n=valores["nombre"]),
			carpeta, ctx)

	def _orden_extraer(self, ctx: api.ContextoComplemento) -> None:
		import wx

		from .ui.dialogos import DialogoExtraer

		conexion = self._panel_nas(ctx)
		if conexion is None:
			return
		elemento = ctx.activo.cursor()
		if elemento is None or elemento.es_carpeta:
			self.zc.anunciar(_("Ponga el cursor sobre un archivo comprimido del NAS"), api.NORMAL)
			return
		if conexion.solo_lectura:
			from .errores import solo_lectura

			self.zc.anunciar(solo_lectura(conexion.servidor.nombre).mensaje, api.ESENCIAL)
			return
		carpeta = ctx.activo.ruta or "/"
		dialogo = DialogoExtraer(self._padre(), elemento.nombre, carpeta)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			destino = dialogo.destino.GetValue().strip() or carpeta
			parametros: dict[str, Any] = {"file_path": elemento.ruta, "dest_folder_path": destino,
				"overwrite": dialogo.sobrescribir.GetValue(), "keep_dir": True, "create_subfolder": dialogo.subcarpeta.GetValue()}
			if dialogo.contrasena.GetValue():
				parametros["password"] = dialogo.contrasena.GetValue()
		finally:
			dialogo.Destroy()
		self._lanzar_tarea(conexion, "SYNO.FileStation.Extract", parametros, _("Extraer en el NAS: {n}").format(n=elemento.nombre),
			destino, ctx)

	def _estado_modo_escritura(self, ctx: api.ContextoComplemento) -> bool:
		conexion = self._conexion_del_panel(ctx) or self.conexiones.unica()
		return conexion is not None and not conexion.solo_lectura

	def _orden_modo_escritura(self, ctx: api.ContextoComplemento) -> None:
		self._con_conexion(ctx, lambda conexion: self.cambiar_modo(conexion, conexion.solo_lectura), pedir_si_no_hay=False)

	def _orden_demostracion(self, ctx: api.ContextoComplemento) -> None:
		from .servidores import ID_DEMOSTRACION

		existente = self.conexiones.obtener(ID_DEMOSTRACION)
		if existente is not None:
			self.abrir_ventana(existente)
			return
		self._iniciar_demostracion()

	def _orden_ssh(self, ctx: api.ContextoComplemento) -> None:
		if not self.ajuste("ssh_activado", False):
			if self.zc.ui.confirmar(_("Las herramientas avanzadas por SSH están desactivadas. Se activan en Preferencias, Complementos, "
					"NAS Synology. ¿Abrir ahora la configuración?"), _("Herramientas por SSH"), peligroso=False):
				self.zc.preferencias.abrir()
			return

		def abrir(conexion: Any) -> None:
			from .ui.dialogos import DialogoSSH

			dialogo = DialogoSSH(self._padre(), self, conexion)
			try:
				self.zc.ui.mostrar_modal(dialogo)
			finally:
				dialogo.Destroy()

		self._con_conexion(ctx, abrir)

	def ejecutar_ssh(self, conexion: Any, datos: dict[str, Any], al_terminar: Any) -> None:
		"""Ejecuta una herramienta SSH en un hilo; ``al_terminar(texto)`` en la interfaz. La contraseña de sudo no se guarda."""
		from .ssh import EjecutorParamiko, HerramientasSSH
		from .ui.dialogos import PreguntasInterfaz

		preguntas = PreguntasInterfaz()
		known_hosts = self.zc.datos / "known_hosts"

		def preguntar_huella(huella: str, anterior: str) -> bool:
			return preguntas.huella(conexion.servidor, huella, anterior) != "cancelar"

		def trabajo(_tarea: Any) -> str:
			ejecutor = EjecutorParamiko(conexion.servidor.host, datos["puerto"], conexion.servidor.usuario, known_hosts, preguntar_huella,
				float(self.ajuste("tiempo_conexion_s", 10)))
			try:
				herramientas = HerramientasSSH(ejecutor, lambda: conexion.solo_lectura, conexion.servidor.nombre)
				sudo, dato = datos["sudo"], datos["dato"]
				if datos["herramienta"] == "smart":
					return herramientas.smart(dato, sudo)
				if datos["herramienta"] == "registros":
					return herramientas.registros(dato, sudo)
				if datos["herramienta"] == "estadisticas":
					return herramientas.estadisticas(sudo)
				if datos["herramienta"] == "compose":
					return herramientas.compose(dato, sudo)
				if datos["herramienta"] == "paquete":
					return herramientas.paquete(dato, datos["accion"], sudo)
				partes = dato.split()
				if len(partes) < 3:
					raise api.NombreNoValido(_("Escriba la API, el método y la versión, por ejemplo: SYNO.Core.System info 3"))
				import json

				return json.dumps(herramientas.webapi(partes[0], partes[1], int(partes[2]), sudo), ensure_ascii=False, indent=2)
			finally:
				ejecutor.cerrar()

		def fallo(error: BaseException) -> None:
			mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
			if not isinstance(error, api.ErrorArchivos):
				log.error("Falló la herramienta SSH", exc_info=error)
			self.zc.anunciar(mensaje, api.ESENCIAL)
			al_terminar(_("Error: {m}").format(m=mensaje))

		self.zc.tareas.enviar(trabajo, al_terminar=al_terminar, al_fallar=fallo, nombre="nas-ssh")

	def _energia(self, ctx: api.ContextoComplemento, accion_id: str) -> None:
		def preparar(conexion: Any) -> None:
			from .areas import consecuencias

			if conexion.solo_lectura:
				from .errores import solo_lectura

				self.zc.anunciar(solo_lectura(conexion.servidor.nombre).mensaje, api.ESENCIAL)
				return
			self.zc.tareas.enviar(lambda _t: consecuencias(conexion.cliente), al_terminar=lambda datos: self._confirmar_energia(
				conexion, accion_id, datos), al_fallar=lambda e: self._fallo(_("No se ha podido consultar el NAS"), e), nombre="nas-energia")

		self._con_conexion(ctx, preparar, pedir_si_no_hay=False)

	def _confirmar_energia(self, conexion: Any, accion_id: str, datos: dict[str, Any]) -> None:
		from . import areas
		from .ui.dialogos import ConfirmadorInterfaz

		seccion = areas.Seccion("energia", "", [], datos=datos)
		accion = areas.accion_energia(accion_id)
		valores = areas.preparar(accion, None, seccion, conexion.cliente, ConfirmadorInterfaz(self._padre()))
		if valores is None:
			self.zc.anunciar(_("Cancelado: el NAS sigue encendido"), api.NORMAL)
			return

		def hecho(resultado: Any) -> None:
			self.zc.anunciar(resultado.mensaje, api.ESENCIAL)
			self.desconectar_conexion(conexion)

		self.zc.tareas.enviar(lambda _t: areas.ejecutar(accion, conexion.cliente, None, valores), al_terminar=hecho,
			al_fallar=lambda e: self._fallo(accion.etiqueta.rstrip("."), e), nombre="nas-energia-ejecutar")

	def _orden_reiniciar(self, ctx: api.ContextoComplemento) -> None:
		self._energia(ctx, "reiniciar")

	def _orden_apagar(self, ctx: api.ContextoComplemento) -> None:
		self._energia(ctx, "apagar")
