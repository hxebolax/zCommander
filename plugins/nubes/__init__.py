# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Complemento Nubes (``zc.nubes``, diseño 2.0, 12): cada cuenta de nube es una unidad más del panel.

``activar`` solo registra (rápido, sin abrir diálogos ni arrancar rclone, salvo
que la configuración diga ``arrancar = al_iniciar``, y entonces en un hilo):

- los 20 manejadores de órdenes (``ui/ordenes.py``, que se importa al usarlos);
- los esquemas ``nube`` (cuentas), ``webdav`` y ``webdavs`` (direcciones sueltas);
- las unidades dinámicas del selector (Alt+F1 y Alt+F2), y empieza en un hilo la
  búsqueda de las carpetas de los programas oficiales de nube;
- ``al_detener`` del componente rclone (para que el actualizador pueda pararlo);
- el aviso de cambios de configuración (reinicia rcd si hace falta).

Al cerrar: ``puede_cerrar`` pregunta si hay subidas pendientes o trabajos en
marcha; ``desactivar`` desmonta, deja de servir y cierra rcd en un hilo (5 s
como mucho; si no responde, se termina el proceso).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.plugins import api

_ = api.traduccion("zc_nubes")[0]

log = logging.getLogger("zcplugins.zc.nubes")

ORDENES = ("cuentas", "anadir", "nextcloud", "enlace", "quitar_enlace", "vaciar_papelera", "espacio", "sincronizar", "emparejar",
	"comprobar", "duplicados", "cifrada", "union", "montar", "montajes", "servir", "servicios_activos", "limites", "reconectar",
	"guia_google")
#: Claves cuyo cambio exige reiniciar rcd (12.9).
CLAVES_MOTOR = frozenset({"transferencias", "horario_limites", "limite_subida_kib", "limite_bajada_kib", "reintentos",
	"registro_detallado"})


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		from .servicio import Nubes

		self.zc = zc
		self.nubes = Nubes(zc, self.carpeta)
		self._ordenes: Any = None
		for id_corto in ORDENES:
			zc.ordenes.manejador(id_corto, self._manejador(id_corto))
		zc.ordenes.disponible("enlace", self._en_cuenta_de_nube)
		zc.ordenes.disponible("quitar_enlace", self._en_cuenta_de_nube)
		zc.vfs.esquema("nube", self.nubes.fabrica_nube)
		zc.vfs.esquema("webdav", self._fabrica_webdav)
		zc.vfs.esquema("webdavs", self._fabrica_webdav)
		zc.vfs.unidades(self.nubes.unidades)
		if zc.config.obtener("carpetas_programas", True):
			# Las carpetas de los programas oficiales se buscan ya, en su hilo: así el primer Alt+F1 no espera.
			self.nubes.asegurar_deteccion()
		zc.componentes.al_detener("rclone", self._detener_para_actualizar)
		self._cancelar_suscripcion = zc.config.suscribir(self._al_cambiar_configuracion)
		if zc.config.obtener("arrancar", "al_usar") == "al_iniciar":
			zc.tareas.enviar(lambda _tarea: self.nubes.motor.arrancar(), al_fallar=self._fallo_arranque, nombre="zc-nubes-arranque")

	def _fabrica_webdav(self, direccion: str) -> Any:
		from .webdav import fabrica_direccion   # ssl y xml solo cuando se usa una dirección webdav://

		return fabrica_direccion(self.nubes, direccion)

	# Órdenes -------------------------------------------------------------------

	def ordenes(self) -> Any:
		if self._ordenes is None:
			from .ui.ordenes import Ordenes

			self._ordenes = Ordenes(self.zc, self.nubes)
		return self._ordenes

	def _manejador(self, id_corto: str) -> Any:
		def manejador(ctx: api.ContextoComplemento) -> None:
			getattr(self.ordenes(), id_corto)(ctx)

		manejador.__name__ = f"nubes_{id_corto}"
		return manejador

	@staticmethod
	def _en_cuenta_de_nube(ctx: api.ContextoComplemento) -> bool:
		proveedor = getattr(ctx.activo, "proveedor", None)
		return getattr(proveedor, "esquema", "") == "nube" and getattr(getattr(proveedor, "cuenta", None), "motor", "") == "rclone"

	# Motor ---------------------------------------------------------------------

	def _fallo_arranque(self, error: BaseException) -> None:
		mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
		log.warning("No se pudo arrancar el motor de nubes al iniciar: %s", mensaje)
		self.zc.anunciar(_("No se pudo arrancar el motor de nubes: {m}").format(m=mensaje), api.RESULTADO)

	def _detener_para_actualizar(self) -> bool:
		"""``al_detener`` del componente rclone (6.6): para rcd si no hay transferencias ni montajes (en un hilo)."""
		if self.nubes.motor.hay_trabajo():
			return False
		self.nubes.motor.detener()
		return True

	def _al_cambiar_configuracion(self, clave: str, _anterior: Any, _nuevo: Any) -> None:
		if clave not in CLAVES_MOTOR or not self.nubes.motor.vivo():
			return
		self.zc.tareas.enviar(lambda _tarea: self.nubes.aplicar_configuracion(),
			al_terminar=lambda mensaje: mensaje and self.zc.anunciar(mensaje, api.RESULTADO), nombre="zc-nubes-configuracion")

	# Cierre --------------------------------------------------------------------

	def puede_cerrar(self) -> bool:
		"""Fase con veto del cierre (3.4): subidas pendientes o transferencias en marcha."""
		motor = getattr(getattr(self, "nubes", None), "motor", None)
		if motor is None or not motor.vivo():
			return True
		pendientes = self.nubes.pendientes_subida()
		montajes = self.nubes.montajes()
		trabajando = motor.hay_trabajo() and not montajes
		if pendientes or trabajando:
			unidades = ", ".join(m["punto"] for m in montajes)
			if pendientes:
				texto = _("Hay {n} subidas pendientes en {u}. Si sale ahora se perderán. ¿Salir de todos modos?").format(
					n=pendientes, u=unidades or _("las unidades de nube"))
			else:
				texto = _("Hay transferencias de nube en marcha. Si sale ahora se cortarán. ¿Salir de todos modos?")
			from .ui import comun

			eleccion = comun.opcion(self.zc, texto, _("Nubes"), [_("&No salir"), _("&Salir de todos modos")])
			if eleccion != 1:
				return False
		if montajes:
			self.zc.anunciar(_("Hay {n} unidades de nube montadas; se desmontarán").format(n=len(montajes)), api.RESULTADO)
		return True

	def desactivar(self) -> None:
		nubes = getattr(self, "nubes", None)
		if nubes is None:
			return
		cancelar = getattr(self, "_cancelar_suscripcion", None)
		if callable(cancelar):
			cancelar()
		if not nubes.motor.vivo():
			return
		hilo = threading.Thread(target=nubes.motor.detener, args=(5.0,), daemon=True, name="zc-nubes-cierre")
		hilo.start()
		hilo.join(6.0)

	# Revisión de teclado (3.12) ------------------------------------------------

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		"""Todas las ventanas del complemento, construidas sin mostrarlas, para ``revisar_teclado``."""
		from .cuentas import Cuenta
		from .locales import CarpetaNube
		from .servicio import Paso
		from .ui import asistente, cifrada, cuentas, emparejar, franjas, montar, oauth, propiedades, servir, sincronizar, union
		from .ui.ordenes import Ordenes

		zc = self.zc
		catalogo = self.nubes.catalogo
		ordenes = Ordenes(zc, self.nubes)
		ejemplo = Cuenta(id="ejemplo", nombre="Ejemplo", servicio="drive", cifrada_sobre="otra", opciones={"remote": "otra:Cifrado"})
		opciones = [("ana", "Google Drive de Ana"), ("pepe", "OneDrive de Pepe")]
		ventanas = [
			cuentas.DialogoCuentas(zc, padre, ordenes),
			asistente.DialogoServicio(zc, padre, catalogo, True),
			oauth.DialogoEspera(zc, padre, "Autorizar", "Explicación", url="http://127.0.0.1:53682/auth"),
			oauth.DialogoEspera(zc, padre, "Esperar", "Explicación"),
			oauth.DialogoToken(zc, padre, 'rclone authorize "drive"'),
			propiedades.DialogoPropiedades(zc, padre, ejemplo, catalogo.servicio("drive")),
			sincronizar.DialogoRutas(zc, padre, "Sincronizar", "C:\\", "nube://ana/", [("suma", "Comparar por su&ma", "", False)],
				explicacion="x", con_copias=True),
			sincronizar.DialogoCambios(zc, padre, "Cambios", "Resumen", [("Se copiará", "a.txt")], boton_accion="&Sincronizar"),
			sincronizar.DialogoDuplicados(zc, padre, opciones),
			sincronizar.DialogoInforme(zc, padre, "Informe", "texto", "&Aplicar la acción"),
			emparejar.DialogoEmparejar(zc, padre),
			cifrada.DialogoCifrada(zc, padre, opciones),
			union.DialogoUnion(zc, padre, opciones),
			montar.DialogoMontar(zc, padre, opciones),
			montar.DialogoMontajes(zc, padre, lambda: [], lambda _p: None),
			servir.DialogoServir(zc, padre, [("ana:", "Google Drive de Ana")]),
			servir.DialogoServicios(zc, padre, lambda: [], lambda _i: None),
			franjas.DialogoFranjas(zc, padre, "08:00,512k 23:00,off"),
		]
		carpetas = [CarpetaNube("OneDrive - Personal", "OneDrive", r"C:\Users\ana\OneDrive", "prueba"),
			CarpetaNube("iCloud Drive", "iCloud Drive", r"C:\Users\ana\iCloudDrive", "prueba")]
		ventanas.append(asistente.DialogoCarpetas(zc, padre, carpetas, [True, False]))
		for servicio in catalogo.lista(True):
			ventanas.append(asistente.DialogoDatos(zc, padre, servicio, guia=lambda: None, abrir_enlace=lambda _url: None))
			if servicio.avanzadas_alta or servicio.es_oauth:
				ventanas.append(asistente.DialogoAvanzadas(zc, padre, servicio, guia=lambda: None))
		ejemplos_pasos = [
			Paso("pregunta", opcion={"Name": "config_change_team_drive", "Help": "¿Unidad compartida?", "Type": "bool", "Default": False}),
			Paso("pregunta", opcion={"Name": "region", "Help": "Región", "Exclusive": True,
				"Examples": [{"Value": "global", "Help": "Global"}, {"Value": "cn", "Help": "China"}]}),
			Paso("pregunta", opcion={"Name": "pass", "Help": "Contraseña", "IsPassword": True}),
			Paso("pregunta", opcion={"Name": "config_token", "Help": "rclone authorize \"drive\""}),
			Paso("pregunta", opcion={"Name": "config_type", "Help": "Type of connection", "Exclusive": True,
				"Examples": [{"Value": "onedrive", "Help": "OneDrive Personal or Business"}, {"Value": "sharepoint", "Help": "Root Sharepoint site"}]}),
		]
		for paso in ejemplos_pasos:
			ventanas.append(asistente.DialogoPregunta(zc, padre, paso, "Google Drive"))
		return ventanas
