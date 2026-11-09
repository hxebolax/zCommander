# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Órdenes del bloque CS: copias de seguridad y perfiles (diseño 2.0, 7 y 10.2).

- ``copia_crear``: diálogo y operación del motor; al terminar suena
  ``copia.creada`` y se anuncia «Copia creada: 2,3 MB, 7 partes».
- ``copia_restaurar`` (también Intro sobre un ``.zcbackup``, con la ruta en
  ``ctx.argumento``): diálogo y operación. Si todas las partes son «En el
  momento» se aplican ya (con ``al_restaurar`` en el bus); si no, se prepara la
  restauración pendiente y se ofrece «Reiniciar ahora» o «Más tarde».
- ``perfil_exportar`` y ``perfil_importar`` (Intro sobre un ``.zcperfil``).
- ``instalar``: tras arrancar, ofrece instalar por el flujo normal (3.10) los
  complementos que trajo una copia restaurada y no estaban instalados.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path

import wx

from app.core import paths
from app.services.copia import crear, pendiente, perfil, restaurar
from app.services.copia.operacion import OperacionCrearCopia, OperacionRestaurarCopia
from app.ui import anuncios
from app.ui.dialogos import cs_comun, cs_crear, cs_perfil, cs_restaurar

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


#: Espera tras arrancar antes de ofrecer los complementos de una copia (que pasen los avisos de 14.8).
ESPERA_OFRECER_MS = 2500
REINTENTOS_OFRECER = 20


def _sonar(evento: str) -> None:
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - un sonido nunca impide nada
		log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)


def carpeta_copias(config) -> Path:
	"""``copia.carpeta`` si está y existe; si no, ``data/backups``."""
	elegida = str(config.obtener("copia.carpeta", "") or "").strip()
	if elegida and Path(elegida).is_dir():
		return Path(elegida)
	return paths.ruta_copias()


def _argumento(ctx) -> str:
	argumento = getattr(ctx, "argumento", None)
	return str(argumento) if isinstance(argumento, (str, Path)) and str(argumento).strip() else ""


# ── Crear ─────────────────────────────────────────────────────────────────────

def copia_crear(ctx) -> None:
	config = ctx.config
	config.guardar_pendiente()
	marcadas = [p for p in config.obtener("copia.partes", []) if isinstance(p, str)]
	opciones = cs_crear.pedir(ctx.ventana, carpeta_copias(config), marcadas, crear.tamano_partes())
	if opciones is None:
		return
	try:
		config.establecer("copia.partes", opciones.partes)
	except Exception:  # noqa: BLE001 - recordar la elección no impide crear la copia
		log.warning("No se pudo recordar la elección de partes", exc_info=True)
	operacion = OperacionCrearCopia(opciones.destino, opciones.partes, "copia", opciones.modo_secretos,
		opciones.contrasena, opciones.descripcion)
	ctx.lanzar(operacion, al_terminar=_al_crear)


def _al_crear(operacion) -> None:
	if operacion.estado.value == "terminada":
		_sonar("copia.creada")


# ── Restaurar ─────────────────────────────────────────────────────────────────

def copia_restaurar(ctx) -> None:
	eleccion = cs_restaurar.pedir(ctx.ventana, _argumento(ctx))
	if eleccion is None:
		return
	if eleccion.carpeta_registros is not None:
		try:
			cuantos = restaurar.extraer_registros(eleccion.ruta, eleccion.carpeta_registros)
			anuncios.anunciar(_("Registros extraídos: {n} en {c}").format(n=cuantos, c=eleccion.carpeta_registros),
				anuncios.RESULTADO)
		except Exception as error:  # noqa: BLE001 - se explica y se sigue con el resto
			log.exception("No se pudieron extraer los registros")
			cs_comun.avisar(ctx.ventana, _("No se pudieron extraer los registros: {e}").format(e=getattr(error, "mensaje", error)))
	if not eleccion.plan.partes:
		return
	ventana = ctx.ventana
	operacion = OperacionRestaurarCopia(eleccion.ruta, eleccion.plan, eleccion.secretos)
	ctx.lanzar(operacion, al_terminar=lambda op: _al_restaurar(ventana, op))


def _al_restaurar(ventana, operacion) -> None:
	resultado = operacion.resultado
	if resultado is None or not resultado.ok:
		return
	if operacion.inmediata:
		_sonar("copia.restaurada")
		return
	eleccion = cs_comun.elegir(ventana, _("La restauración está preparada y se aplicará al reiniciar zCommander. "
		"¿Reiniciar ahora?"), _("Restaurar una copia de seguridad"), [_("&Reiniciar ahora"), _("Más &tarde")])
	if eleccion == 0:
		pendiente.decidir_pendiente(paths.ruta_datos(), "aplicar")
		ejecutar = getattr(ventana, "ejecutar_orden", None)
		if callable(ejecutar):
			ejecutar("reiniciar")
	else:
		anuncios.anunciar(_("La restauración se aplicará la próxima vez que abra zCommander; entonces se le preguntará."),
			anuncios.RESULTADO)


# ── Perfiles ──────────────────────────────────────────────────────────────────

def perfil_exportar(ctx) -> None:
	ctx.config.guardar_pendiente()
	opciones = cs_perfil.pedir_exportar(ctx.ventana, carpeta_copias(ctx.config))
	if opciones is None:
		return
	operacion = OperacionCrearCopia(opciones.destino, perfil.partes_exportar(opciones.incluir_sonidos), "perfil",
		"excluidos", None, opciones.descripcion)
	ctx.lanzar(operacion, al_terminar=_al_crear)


def perfil_importar(ctx) -> None:
	eleccion = cs_perfil.pedir_importar(ctx.ventana, ctx.config, _argumento(ctx))
	if eleccion is None:
		return
	ocupado = wx.BusyCursor()
	try:
		resultado = perfil.importar(eleccion.ruta, ctx.config, eleccion.filas, eleccion.ejecutables)
	except Exception as error:  # noqa: BLE001 - se explica a la persona
		log.exception("No se pudo importar el perfil")
		resultado = None
		mensaje = getattr(error, "mensaje", "") or str(error)
	finally:
		del ocupado
	if resultado is None:
		cs_comun.avisar(ctx.ventana, _("No se pudo importar el perfil: {e}").format(e=mensaje))
		return
	if resultado.ok:
		anuncios.anunciar(resultado.mensaje, anuncios.ESENCIAL, sonido="copia.restaurada")
	else:
		cs_comun.avisar(ctx.ventana, resultado.mensaje)


# ── Complementos de una copia restaurada ──────────────────────────────────────

def ofrecer_complementos(ventana) -> bool:
	"""Ofrece instalar los complementos que trajo la copia (7.6, 8). Devuelve si había algo que ofrecer."""
	ruta_datos = paths.ruta_datos()
	pendientes = restaurar.leer_por_instalar(ruta_datos)
	if not pendientes:
		return False
	padre = ventana.padre() if callable(getattr(ventana, "padre", None)) else ventana
	nombres = ", ".join(f"{p['id']} {p.get('version', '')}".strip() for p in pendientes)
	eleccion = cs_comun.elegir(padre, _("La copia restaurada trae {n} complementos que no están instalados: {c}. Se "
		"instalan por el proceso normal, que muestra el resumen, la firma y los permisos de cada uno.").format(
		n=len(pendientes), c=nombres), _("Complementos de la copia"),
		[_("Instalar &todos"), _("&Uno a uno"), _("&Ninguno")])
	if eleccion is None:
		return True  # Cancelar: se vuelve a ofrecer en el próximo arranque.
	carpeta = restaurar.carpeta_por_instalar(ruta_datos)
	if eleccion == 2:
		restaurar.quitar_por_instalar({p["id"] for p in pendientes}, ruta_datos, borrar_archivos=True)
		return True
	elegidos = []
	for entrada in pendientes:
		if eleccion == 1:
			respuesta = cs_comun.elegir(padre, _("¿Instalar el complemento {c} {v} de la copia?").format(
				c=entrada["id"], v=entrada.get("version", "")), _("Complementos de la copia"), [_("&Instalar"), _("&Omitir")])
			if respuesta != 0:
				continue
		elegidos.append(entrada)
	restaurar.quitar_por_instalar({p["id"] for p in pendientes}, ruta_datos)
	ejecutar = getattr(padre, "ejecutar_orden", None)
	for entrada in elegidos:
		if callable(ejecutar):
			# La instalación normal (3.10) valida el paquete, su firma y pregunta; nunca se instala en silencio.
			ejecutar("complemento_instalar", argumento=str(carpeta / entrada["archivo"]))
	return True


def _limpiar_paquetes_viejos() -> None:
	"""Borra los paquetes que ya se ofrecieron (no figuran en la lista de pendientes)."""
	carpeta = restaurar.carpeta_por_instalar()
	if not carpeta.is_dir():
		return
	vigentes = {p["archivo"] for p in restaurar.leer_por_instalar()}
	for paquete in carpeta.glob("*.zcplugin"):
		if paquete.name not in vigentes:
			paquete.unlink(missing_ok=True)


def instalar(ventana) -> None:
	"""Enganche de arranque (14.9): ofrece los complementos de una copia cuando la ventana está libre."""
	try:
		_limpiar_paquetes_viejos()
	except OSError:
		log.warning("No se pudieron limpiar los paquetes de complementos ya ofrecidos", exc_info=True)
	if not restaurar.leer_por_instalar():
		return
	intentos = [0]

	def intentar() -> None:
		esta_libre = getattr(ventana, "esta_libre", None)
		if callable(esta_libre) and not esta_libre() and intentos[0] < REINTENTOS_OFRECER:
			intentos[0] += 1
			ventana.llamar_mas_tarde(ESPERA_OFRECER_MS, intentar)
			return
		try:
			ofrecer_complementos(ventana)
		except Exception:  # noqa: BLE001 - no impide usar zCommander
			log.exception("No se pudieron ofrecer los complementos de la copia")

	ventana.llamar_mas_tarde(ESPERA_OFRECER_MS, intentar)
