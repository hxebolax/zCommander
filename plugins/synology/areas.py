# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Las áreas del NAS (diseño 2.0, 13.5): qué se lee, cómo se muestra y qué acciones tiene cada una. Sin wx.

Cada área carga una ``Vista`` con una o varias secciones (filas con columnas y
un detalle legible) y declara sus acciones: las de **lectura** se pueden usar
siempre; las de **escritura** solo con el modo de cambios permitido y tras una
confirmación que dice exactamente qué se va a hacer (13.6). Apagar, reiniciar
e instalar DSM piden **dos** confirmaciones: la segunda exige escribir el
nombre del NAS.

Las áreas cuyo API principal no está en el catálogo del NAS no aparecen (13.5);
las que la cuenta no puede usar dicen «Sin permiso con esta cuenta» (13.1).

Las preguntas se hacen ANTES, en el hilo de la interfaz (``preparar``), y la
llamada al NAS después, en un hilo de trabajo (``ejecutar``).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from app.plugins import api

from . import errores
from .cliente import ClienteDSM, aviso_seguridad

_, _n = api.traduccion("zc_synology")
log = logging.getLogger("zcplugins.zc.synology.areas")
F = api.formato

DIAS_AVISO_CERTIFICADO = 90


# ── Modelo ───────────────────────────────────────────────────────────────────


@dataclass
class Fila:
	valores: list[str]
	detalle: str = ""
	clave: str = ""
	datos: dict[str, Any] = field(default_factory=dict)
	#: Texto del aviso de salud de esta fila (vacío si no hay aviso).
	aviso: str = ""


@dataclass
class Resultado:
	"""Lo que devuelve una acción: un mensaje para anunciar y, si hace falta, algo que mostrar o hacer."""

	mensaje: str
	texto: str = ""
	titulo: str = ""
	copiar: str = ""
	abrir: str = ""
	refrescar: bool = True
	desconectar: bool = False


@dataclass
class Peticion:
	"""Un dato que la acción pide antes de ejecutarse."""

	clave: str
	etiqueta: str
	tipo: str = "texto"  # texto, contrasena, opcion
	opciones: tuple[str, ...] = ()
	valor: str = ""


@dataclass
class Accion:
	id: str
	etiqueta: str
	ayuda: str
	escritura: bool
	funcion: Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]
	necesita_fila: bool = True
	confirmacion: Callable[[Fila | None, Any], str] | None = None
	doble: bool = False
	pedir: tuple[Peticion, ...] = ()
	disponible: Callable[[Fila], bool] | None = None
	por_defecto: bool = False

	def aplicable(self, fila: Fila | None) -> bool:
		if self.necesita_fila and fila is None:
			return False
		if self.disponible is not None and fila is not None:
			return self.disponible(fila)
		return True


@dataclass
class Seccion:
	id: str
	titulo: str
	columnas: list[str]
	filas: list[Fila] = field(default_factory=list)
	acciones: list[Accion] = field(default_factory=list)
	vacia: str = ""
	datos: dict[str, Any] = field(default_factory=dict)


@dataclass
class Vista:
	area: str
	secciones: list[Seccion]
	resumen: str = ""

	def avisos(self) -> dict[str, str]:
		"""Clave → texto de cada fila con aviso de salud (para anunciarlos una sola vez, 13.4)."""
		return {f"{s.id}:{f.clave}": f.aviso for s in self.secciones for f in s.filas if f.aviso}


@dataclass
class Area:
	id: str
	titulo: str
	ayuda: str
	apis: tuple[str, ...]
	cargar: Callable[[ClienteDSM, dict[str, Any]], Vista]

	def disponible(self, cliente: ClienteDSM) -> tuple[bool, str]:
		"""El área aparece si el NAS tiene al menos una de sus API (13.5: según el catálogo, nunca el modelo)."""
		if cliente.catalogo is None:
			return False, _("No hay conexión")
		motivos = []
		for nombre in self.apis:
			ok, motivo = cliente.catalogo.disponible(nombre)
			if ok:
				return True, ""
			motivos.append(motivo)
		return False, motivos[0] if motivos else ""


class Confirmador(Protocol):
	"""Preguntas de las acciones, en el hilo de la interfaz."""

	def confirmar(self, titulo: str, texto: str, peligroso: bool = True) -> bool: ...
	def escribir_nombre(self, titulo: str, texto: str, esperado: str) -> bool: ...
	def pedir(self, titulo: str, peticion: Peticion) -> str | None: ...


# ── Utilidades de presentación ───────────────────────────────────────────────

_ESTADOS = {
	"running": "En marcha", "stop": "Parado", "stopped": "Parado", "normal": "Correcto", "warning": "Aviso", "warn": "Aviso",
	"degraded": "Degradado", "crashed": "Dañado", "healthy": "Correcta", "unhealthy": "Con problemas", "error": "Error",
	"RUNNING": "En marcha", "STOPPED": "Parado", "ERROR": "Con errores", "connected": "Conectada", "disconnected": "Desconectada",
	"safe": "Correcto", "danger": "Peligro", "info": "Información", "err": "Error", "crit": "Crítico", "service_ready": "Funcionando",
	"login_success": "Conectado", "sincronizado": "Sincronizado", "en espera": "En espera", "starting": "Iniciándose",
}


def estado(valor: Any) -> str:
	texto = str(valor or "")
	return _(_ESTADOS.get(texto, _ESTADOS.get(texto.lower(), texto or "Desconocido")))


def si_no(valor: Any) -> str:
	return _("Sí") if valor else _("No")


def tamano(valor: Any) -> str:
	try:
		return F.tamano_legible(int(valor))
	except (TypeError, ValueError):
		return ""


def porcentaje(parte: Any, total: Any) -> int:
	try:
		total_n = int(total)
		return round(100 * int(parte) / total_n) if total_n else 0
	except (TypeError, ValueError):
		return 0


def fecha(marca: Any) -> str:
	try:
		return F.fecha(float(marca)) if marca else ""
	except (TypeError, ValueError):
		return str(marca or "")


def detalle(columnas: Sequence[str], valores: Sequence[str], extra: str = "") -> str:
	lineas = [f"{c}: {v}" for c, v in zip(columnas, valores, strict=False) if v not in ("", None)]
	if extra:
		lineas.append(extra)
	return "\n".join(lineas)


def fila(columnas: Sequence[str], valores: Sequence[Any], clave: str = "", datos: dict[str, Any] | None = None, aviso: str = "",
		extra: str = "") -> Fila:
	textos = ["" if v is None else str(v) for v in valores]
	return Fila(textos, detalle(columnas, textos, (aviso + "\n" if aviso else "") + extra if (aviso or extra) else ""), clave or textos[0],
		dict(datos or {}), aviso)


def sin_permiso(area: str, titulo: str) -> Vista:
	return Vista(area, [Seccion("permiso", titulo, [_("Aviso")], [Fila([_("Sin permiso con esta cuenta")],
		_("La cuenta con la que se ha conectado no puede usar esta área del NAS. Conéctese con una cuenta del grupo administrators."),
		"permiso")])], _("Sin permiso con esta cuenta"))


def _intentar(funcion: Callable[[], Any], defecto: Any = None) -> Any:
	"""Una lectura opcional dentro de un área: si falta la API, se deja sin esa parte."""
	try:
		return funcion()
	except errores.FuncionAusente:
		return defecto


def _nombre_nas(cliente: ClienteDSM) -> str:
	info = cliente.info
	return (info.nombre_host if info is not None and info.nombre_host else "") or cliente.servidor.nombre


def _hecho(texto: str, **extra: Any) -> Resultado:
	return Resultado(texto, **extra)


# ── 1. Estado y salud ────────────────────────────────────────────────────────


def _cargar_estado(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	peticiones = [
		{"api": "SYNO.Core.System", "method": "info"}, {"api": "SYNO.DSM.Info", "method": "getinfo"},
		{"api": "SYNO.Core.System.Status", "method": "get"}, {"api": "SYNO.Core.System.SystemHealth", "method": "get"},
		{"api": "SYNO.Core.System.Utilization", "method": "get"}, {"api": "SYNO.Core.DSMNotify", "method": "notify", "action": "load"},
		{"api": "SYNO.Core.Hardware.NeedReboot", "method": "get"}, {"api": "SYNO.Storage.CGI.Storage", "method": "load_info"},
	]
	resultados = cliente.llamar_compuesta(peticiones)
	datos = {r.get("api"): r.get("data") or {} for r in resultados if r.get("success")}
	if not datos:
		codigos = {int((r.get("error") or {}).get("code", 0)) for r in resultados}
		if codigos & errores.SIN_PERMISO:
			return sin_permiso("estado", _("Estado y salud"))
	sistema, dsm = datos.get("SYNO.Core.System", {}), datos.get("SYNO.DSM.Info", {})
	uso = datos.get("SYNO.Core.System.Utilization", {})
	columnas = [_("Dato"), _("Valor")]
	filas: list[Fila] = []
	version = str(dsm.get("version_string") or sistema.get("firmware_ver") or (cliente.info.version if cliente.info else ""))
	temperatura = int(sistema.get("sys_temp") or dsm.get("temperature") or 0)
	limite = int(ajustes.get("aviso_temperatura_c", 55))
	cpu = uso.get("cpu", {})
	memoria = uso.get("memory", {})

	def poner(dato: str, valor: Any, aviso: str = "", clave: str = "") -> None:
		filas.append(fila(columnas, [dato, valor], clave or dato, aviso=aviso))

	poner(_("Nombre"), _nombre_nas(cliente))
	poner(_("Modelo"), sistema.get("model") or dsm.get("model", ""))
	if sistema.get("cpu_series"):
		poner(_("Procesador"), _("{f} {s} de {n} núcleos a {v} MHz").format(f=sistema.get("cpu_family", ""), s=sistema["cpu_series"],
			n=sistema.get("cpu_cores", "?"), v=sistema.get("cpu_clock_speed", "?")))
	ram = int(sistema.get("ram_size") or dsm.get("ram") or 0)
	if ram:
		poner(_("Memoria instalada"), F.tamano_legible(ram * 1024 * 1024))
	aviso = aviso_seguridad(version)
	poner(_("Versión de DSM"), version)
	poner(_("Actualización de seguridad"), _("Falta: ") + aviso if aviso else _("Al día (boletín Synology-SA-26:06 corregido)"),
		aviso, "seguridad")
	encendido = dsm.get("uptime")
	poner(_("Tiempo encendido"), F.duracion(float(encendido)) if encendido else sistema.get("up_time", ""))
	aviso_temp = _("Temperatura alta: {t} °C").format(t=temperatura) if temperatura >= limite else ""
	poner(_("Temperatura del sistema"), _("{t} °C").format(t=temperatura) if temperatura else "", aviso_temp, "temperatura")
	if cpu:
		total_cpu = int(cpu.get("user_load", 0)) + int(cpu.get("system_load", 0)) + int(cpu.get("other_load", 0))
		poner(_("Procesador en uso"), _("{p} %").format(p=total_cpu))
	if memoria:
		poner(_("Memoria en uso"), _("{p} %").format(p=memoria.get("real_usage", 0)))
	almacen = datos.get("SYNO.Storage.CGI.Storage", {})
	for volumen in almacen.get("volumes", []):
		tamanos = volumen.get("size", {})
		estado_v = str(volumen.get("status", ""))
		texto = _("{u} usados de {t} ({p} %), {e}").format(u=tamano(tamanos.get("used")), t=tamano(tamanos.get("total")),
			p=porcentaje(tamanos.get("used"), tamanos.get("total")), e=estado(estado_v))
		poner(_("Volumen {v}").format(v=volumen.get("num_id", volumen.get("id"))), texto,
			_("El volumen {v} está {e}").format(v=volumen.get("id"), e=estado(estado_v).lower()) if estado_v != "normal" else "",
			f"volumen:{volumen.get('id')}")
	for disco in almacen.get("disks", []):
		if str(disco.get("smart_status", "normal")) != "normal" or str(disco.get("status", "normal")) != "normal":
			poner(_("Disco {d}").format(d=disco.get("name")), estado(disco.get("smart_status")),
				_("{d}: estado S.M.A.R.T. {e}").format(d=disco.get("name"), e=estado(disco.get("smart_status")).lower()),
				f"disco:{disco.get('id')}")
	salud = datos.get("SYNO.Core.System.SystemHealth", {}).get("rule", {})
	if salud:
		poner(_("Salud del sistema"), estado(salud.get("type")))
	avisos = datos.get("SYNO.Core.DSMNotify", {}).get("items", [])
	poner(_("Avisos de DSM"), _n("{n} aviso", "{n} avisos", len(avisos)).format(n=len(avisos)))
	reinicio = datos.get("SYNO.Core.Hardware.NeedReboot", {})
	if reinicio:
		poner(_("Necesita reiniciar"), si_no(reinicio.get("need_reboot")))
	resumen = "\n".join(f"{f.valores[0]}: {f.valores[1]}" for f in filas)
	acciones = [Accion("copiar", _("Copiar el resumen"), _("Copia al portapapeles todo el estado del NAS."), False,
		lambda c, f, v: _hecho(_("Resumen copiado al portapapeles"), copiar=resumen, refrescar=False), necesita_fila=False)]
	return Vista("estado", [Seccion("resumen", _("Resumen"), columnas, filas, acciones)], resumen)


# ── 2. Almacenamiento ────────────────────────────────────────────────────────


def _smart(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	dispositivo = f"/dev/{f.datos['id']}"
	try:
		datos = cliente.llamar("SYNO.Core.Storage.Disk", "get_smart_info", device=dispositivo)
	except errores.FuncionAusente:
		datos = cliente.llamar("SYNO.Storage.CGI.Smart", "get_smart_info", device=dispositivo)
	lineas = [_("Estado S.M.A.R.T. de {d}: {e}").format(d=f.valores[0], e=estado(datos.get("status"))), ""]
	for atributo in datos.get("smartInfo", []):
		lineas.append(_("{i} {n}: valor {c}, peor {p}, umbral {u}, en bruto {r}, {e}").format(i=atributo.get("id"), n=atributo.get("name"),
			c=atributo.get("current"), p=atributo.get("worst"), u=atributo.get("threshold"), r=atributo.get("raw"), e=atributo.get("status")))
	return _hecho(_("Información S.M.A.R.T. de {d}").format(d=f.valores[0]), texto="\n".join(lineas),
		titulo=_("S.M.A.R.T. de {d}").format(d=f.valores[0]), refrescar=False)


def _prueba_smart(tipo: str) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		cliente.llamar("SYNO.Core.Storage.Disk", "do_smart_test", device=f"/dev/{f.datos['id']}", type=tipo)
		return _hecho(_("Prueba S.M.A.R.T. iniciada en {d}").format(d=f.valores[0]))

	return ejecutar


def _limpieza(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Storage.CGI.Pool", "data_scrubbing", pool_path=f.datos.get("grupo", "reuse_1"))
	return _hecho(_("Limpieza de datos iniciada"))


def _cargar_almacenamiento(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Storage.CGI.Storage", "load_info")
	except errores.SinPermiso:
		return sin_permiso("almacenamiento", _("Almacenamiento y discos"))
	c_vol = [_("Volumen"), _("Estado"), _("Usado"), _("Total"), _("Uso"), _("Sistema de archivos"), _("Limpieza de datos")]
	volumenes = []
	for v in datos.get("volumes", []):
		tamanos = v.get("size", {})
		estado_v = str(v.get("status", ""))
		volumenes.append(fila(c_vol, [v.get("vol_path", v.get("id")), estado(estado_v), tamano(tamanos.get("used")),
			tamano(tamanos.get("total")), f"{porcentaje(tamanos.get('used'), tamanos.get('total'))} %", str(v.get("fs_type", "")).upper(),
			_("En curso") if v.get("scrubbingStatus") else _("No")], str(v.get("id")), {"grupo": v.get("pool_path")},
			_("El volumen {v} está {e}").format(v=v.get("vol_path"), e=estado(estado_v).lower()) if estado_v != "normal" else ""))
	c_grupo = [_("Grupo"), _("Estado"), _("Tipo"), _("Discos"), _("Tamaño")]
	grupos = [fila(c_grupo, [_("Grupo {n}").format(n=g.get("num_id")), estado(g.get("status")), g.get("raid_desc") or g.get("device_type"),
		", ".join(g.get("disks", [])), tamano((g.get("size") or {}).get("total"))], str(g.get("id")), {"grupo": g.get("id")},
		_("El grupo {g} está {e}").format(g=g.get("num_id"), e=estado(g.get("status")).lower()) if g.get("status") != "normal" else "")
		for g in datos.get("storagePools", [])]
	c_disco = [_("Disco"), _("Estado S.M.A.R.T."), _("Temperatura"), _("Modelo"), _("Sectores dañados"), _("Tamaño"), _("Número de serie")]
	discos = []
	for d in datos.get("disks", []):
		smart = str(d.get("smart_status", ""))
		aviso = _("{d}: estado S.M.A.R.T. {e}, {u} sectores dañados").format(d=d.get("name"), e=estado(smart).lower(),
			u=d.get("unc", 0)) if smart != "normal" or d.get("unc") else ""
		discos.append(fila(c_disco, [d.get("name"), estado(smart), _("{t} °C").format(t=d.get("temp")), d.get("model"), d.get("unc", 0),
			tamano(d.get("size_total")), d.get("serial")], str(d.get("id")), {"id": d.get("id")}, aviso))
	tiene_disk = cliente.disponible("SYNO.Core.Storage.Disk")
	acciones_disco = [Accion("smart", _("Información S.M.A.R.T."), _("Muestra los atributos S.M.A.R.T. del disco elegido."), False,
		_smart, por_defecto=True)]
	if tiene_disk:
		acciones_disco += [
			Accion("prueba_rapida", _("Prueba S.M.A.R.T. rápida"), _("Lanza una prueba S.M.A.R.T. rápida en el disco elegido."), True,
				_prueba_smart("quick"), confirmacion=lambda f, s: _("¿Iniciar una prueba S.M.A.R.T. rápida en {d}?").format(d=f.valores[0])),
			Accion("prueba_completa", _("Prueba S.M.A.R.T. completa"),
				_("Lanza una prueba S.M.A.R.T. completa: tarda horas y el disco va más lento mientras tanto."), True,
				_prueba_smart("extend"), confirmacion=lambda f, s: _("¿Iniciar una prueba S.M.A.R.T. completa en {d}? Tardará varias horas.").format(
					d=f.valores[0])),
		]
	acciones_grupo = []
	if cliente.disponible("SYNO.Storage.CGI.Pool"):
		acciones_grupo.append(Accion("limpieza", _("Iniciar la limpieza de datos"),
			_("Comprueba y repara la coherencia de los datos del grupo de almacenamiento. Tarda horas."), True, _limpieza,
			confirmacion=lambda f, s: _("¿Iniciar la limpieza de datos de {g}? El NAS irá más lento durante horas.").format(g=f.valores[0])))
	return Vista("almacenamiento", [
		Seccion("volumenes", _("Volúmenes"), c_vol, volumenes, list(acciones_grupo)),
		Seccion("grupos", _("Grupos de almacenamiento"), c_grupo, grupos, list(acciones_grupo)),
		Seccion("discos", _("Discos"), c_disco, discos, acciones_disco),
	])


# ── 3. File Station ──────────────────────────────────────────────────────────


def _abrir_compartida(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	return _hecho(_("Abriendo {c} en el panel").format(c=f.valores[0]), abrir=f"synology://{cliente.servidor.id}{f.datos['ruta']}",
		refrescar=False)


def _buscar(cliente: ClienteDSM, _f: Fila | None, valores: dict[str, Any]) -> Resultado:
	from .busqueda import buscar_en_nas

	patron = str(valores.get("patron", "")).strip()
	encontrados = buscar_en_nas(cliente, patron, maximo=500)
	if not encontrados:
		return _hecho(_("No se ha encontrado nada con «{p}»").format(p=patron), refrescar=False)
	texto = "\n".join(f"synology://{cliente.servidor.id}{r}" for r in encontrados)
	return _hecho(_n("{n} resultado", "{n} resultados", len(encontrados)).format(n=len(encontrados)), texto=texto,
		titulo=_("Resultados de «{p}» en el NAS").format(p=patron), refrescar=False)


def _limpiar_tareas(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.FileStation.BackgroundTask", "clear_finished")
	return _hecho(_("Tareas terminadas quitadas de la lista"))


def _copiar_enlace(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	return _hecho(_("Enlace copiado al portapapeles"), copiar=f.datos.get("url", ""), refrescar=False)


def _editar_enlace(cliente: ClienteDSM, f: Fila | None, valores: dict[str, Any]) -> Resultado:
	caduca = str(valores.get("caduca", "")).strip()
	if caduca and not (len(caduca) == 10 and caduca[4] == caduca[7] == "-" and caduca.replace("-", "").isdigit()):
		return Resultado(_("Escriba la fecha como AAAA-MM-DD; no se ha cambiado nada."), refrescar=False)
	cliente.llamar("SYNO.FileStation.Sharing", "edit", id=[f.datos["id"]], date_expired=caduca)
	return _hecho(_("Enlace de {p}: caduca {c}").format(p=f.valores[0], c=caduca or _("nunca")))


def _borrar_enlace(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.FileStation.Sharing", "delete", id=[f.datos["id"]])
	return _hecho(_("Enlace borrado"))


def _limpiar_enlaces(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.FileStation.Sharing", "clear_invalid")
	return _hecho(_("Enlaces rotos borrados"))


def descripcion_tarea(tarea: dict[str, Any]) -> str:
	nombres = {"SYNO.FileStation.CopyMove": _("Mover") if (tarea.get("params") or {}).get("remove_src") else _("Copiar"),
		"SYNO.FileStation.Delete": _("Borrar"), "SYNO.FileStation.Compress": _("Comprimir"), "SYNO.FileStation.Extract": _("Extraer")}
	return nombres.get(str(tarea.get("api")), str(tarea.get("api", "")).rsplit(".", 1)[-1])


def _cargar_archivos(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	secciones = []
	datos = cliente.llamar("SYNO.FileStation.List", "list_share", additional=["real_path", "volume_status", "time"], offset=0, limit=0)
	c_comp = [_("Carpeta compartida"), _("Ruta real"), _("Espacio libre")]
	compartidas = []
	for compartida in datos.get("shares", []):
		extra = compartida.get("additional") or {}
		libre = (extra.get("volume_status") or {}).get("freespace")
		compartidas.append(fila(c_comp, [compartida.get("name"), extra.get("real_path", ""), tamano(libre)], str(compartida.get("name")),
			{"ruta": compartida.get("path")}))
	secciones.append(Seccion("compartidas", _("Carpetas compartidas"), c_comp, compartidas, [
		Accion("abrir", _("Abrir en el panel"), _("Abre la carpeta compartida elegida en el panel activo de zCommander."), False,
			_abrir_compartida, por_defecto=True),
		Accion("buscar", _("Buscar en el NAS..."), _("Busca archivos por nombre en todo el NAS (Universal Search si está; si no, File Station)."),
			False, _buscar, necesita_fila=False, pedir=(Peticion("patron", _("&Nombre o parte del nombre:")),)),
	], _("No hay carpetas compartidas visibles con esta cuenta.")))
	tareas = _intentar(lambda: cliente.llamar("SYNO.FileStation.BackgroundTask", "list", offset=0, limit=0), {})
	if tareas is not None:
		c_tarea = [_("Operación"), _("Elemento"), _("Progreso"), _("Estado")]
		filas = []
		for tarea in tareas.get("tasks", []):
			params = tarea.get("params") or {}
			elemento = params.get("path") or params.get("file_path") or ""
			if isinstance(elemento, list):
				elemento = ", ".join(str(e) for e in elemento)
			terminado = tarea.get("finished")
			filas.append(fila(c_tarea, [descripcion_tarea(tarea), elemento, f"{round(float(tarea.get('progress', 0)) * 100)} %",
				_("Terminada") if terminado else _("En curso")], str(tarea.get("taskid")), dict(tarea)))
		secciones.append(Seccion("tareas", _("Tareas en segundo plano"), c_tarea, filas, [
			Accion("limpiar_tareas", _("Quitar las terminadas"), _("Quita de la lista las tareas de File Station que ya han terminado."), True,
				_limpiar_tareas, necesita_fila=False, confirmacion=lambda f, s: _("¿Quitar de la lista las tareas terminadas?")),
		], _("No hay tareas de File Station en segundo plano.")))
	enlaces = _intentar(lambda: cliente.llamar("SYNO.FileStation.Sharing", "list", offset=0, limit=0), {})
	if enlaces is not None:
		c_enlace = [_("Elemento"), _("Enlace"), _("Caduca"), _("Contraseña"), _("Estado")]
		filas = [fila(c_enlace, [e.get("path"), e.get("url"), e.get("date_expired") or _("Nunca"), si_no(e.get("has_password")),
			_("Válido") if e.get("status") == "valid" else str(e.get("status", ""))], str(e.get("id")), dict(e)) for e in enlaces.get("links", [])]
		secciones.append(Seccion("enlaces", _("Enlaces compartidos"), c_enlace, filas, [
			Accion("copiar_enlace", _("Copiar el enlace"), _("Copia al portapapeles la dirección del enlace elegido."), False, _copiar_enlace,
				por_defecto=True),
			Accion("editar_enlace", _("Cambiar la caducidad..."), _("Cambia la fecha en la que el enlace elegido deja de funcionar."), True,
				_editar_enlace, pedir=(Peticion("caduca", _("&Caduca el (AAAA-MM-DD, vacío para nunca):")),),
				confirmacion=lambda f, s: _("¿Cambiar la caducidad del enlace de {p}?").format(p=f.valores[0])),
			Accion("borrar_enlace", _("Borrar el enlace"), _("Borra el enlace elegido: quien lo tenga ya no podrá usarlo."), True,
				_borrar_enlace, confirmacion=lambda f, s: _("¿Borrar el enlace de {p}? Quien lo tenga ya no podrá abrirlo.").format(p=f.valores[0])),
			Accion("limpiar_enlaces", _("Borrar los enlaces rotos"), _("Borra los enlaces cuyo archivo ya no existe."), True, _limpiar_enlaces,
				necesita_fila=False, confirmacion=lambda f, s: _("¿Borrar los enlaces de archivos que ya no existen?")),
		], _("No hay enlaces compartidos. Créelos desde el panel con Crear un enlace compartido.")))
	return Vista("archivos", secciones)


# ── 4. Carpetas compartidas ──────────────────────────────────────────────────

_PERMISOS = (("rw", "Lectura y escritura"), ("ro", "Solo lectura"), ("na", "Sin acceso"))


def _texto_permiso(p: dict[str, Any]) -> str:
	if p.get("is_deny"):
		return _("Sin acceso")
	if p.get("is_writable"):
		return _("Lectura y escritura")
	if p.get("is_readonly"):
		return _("Solo lectura")
	return _("Sin permisos propios")


def _cambiar_permiso(cliente: ClienteDSM, f: Fila | None, valores: dict[str, Any]) -> Resultado:
	elegido = str(valores.get("permiso", ""))
	codigo = next((c for c, t in _PERMISOS if _(t) == elegido), "ro")
	permiso = {"name": f.datos["usuario"], "is_readonly": codigo == "ro", "is_writable": codigo == "rw", "is_deny": codigo == "na",
		"is_custom": False}
	cliente.llamar("SYNO.Core.Share.Permission", "set", name=f.datos["carpeta"], user_group_type="local_user", permissions=[permiso])
	return _hecho(_("Permiso de {u} en {c}: {p}").format(u=f.datos["usuario"], c=f.datos["carpeta"], p=elegido))


def _cargar_carpetas(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.Share", "list", shareType="all", additional=["hidden", "encryption", "is_aclmode",
			"recyclebin", "share_quota", "support_snapshot"])
	except errores.SinPermiso:
		return sin_permiso("carpetas", _("Carpetas compartidas"))
	c_carpeta = [_("Carpeta"), _("Descripción"), _("Cifrada"), _("Papelera"), _("Cuota"), _("Oculta"), _("Instantáneas")]
	carpetas = [fila(c_carpeta, [c.get("name"), c.get("desc"), si_no(c.get("encryption")), si_no(c.get("enable_recycle_bin")),
		tamano(int(c.get("share_quota") or 0) * 1024 * 1024) if c.get("share_quota") else _("Sin cuota"), si_no(c.get("hidden")),
		si_no(c.get("support_snapshot"))], str(c.get("name"))) for c in datos.get("shares", [])]
	c_permiso = [_("Carpeta"), _("Usuario"), _("Permiso")]
	permisos = []
	if cliente.disponible("SYNO.Core.Share.Permission"):
		for carpeta in datos.get("shares", []):
			nombre = str(carpeta.get("name"))
			lista = _intentar(lambda n=nombre: cliente.llamar("SYNO.Core.Share.Permission", "list", name=n, user_group_type="local_user",
				offset=0, limit=-1), {}) or {}
			for p in lista.get("items", []):
				permisos.append(fila(c_permiso, [nombre, p.get("name"), _texto_permiso(p)], f"{nombre}:{p.get('name')}",
					{"carpeta": nombre, "usuario": p.get("name")}))
	return Vista("carpetas", [
		Seccion("carpetas", _("Carpetas compartidas"), c_carpeta, carpetas),
		Seccion("permisos", _("Permisos por usuario"), c_permiso, permisos, [
			Accion("permiso", _("Cambiar el permiso..."), _("Cambia lo que el usuario elegido puede hacer en la carpeta compartida."), True,
				_cambiar_permiso, pedir=(Peticion("permiso", _("&Permiso:"), "opcion", tuple(_(t) for _c, t in _PERMISOS)),),
				confirmacion=lambda f, s: _("¿Cambiar el permiso de {u} en la carpeta {c}?").format(u=f.datos["usuario"], c=f.datos["carpeta"])),
		], _("No hay permisos propios de usuarios.")),
	])


# ── 5. Usuarios y grupos ─────────────────────────────────────────────────────


def _activo(f: Fila) -> bool:
	return f.datos.get("expired") == "normal"


def _activar_usuario(activar: bool) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		cliente.llamar("SYNO.Core.User", "set", name=f.datos["name"], expired="normal" if activar else "true")
		return _hecho((_("Usuario {u} activado") if activar else _("Usuario {u} desactivado")).format(u=f.datos["name"]))

	return ejecutar


def _contrasena_usuario(cliente: ClienteDSM, f: Fila | None, valores: dict[str, Any]) -> Resultado:
	nueva, repetida = str(valores.get("nueva", "")), str(valores.get("repetida", ""))
	if not nueva or nueva != repetida:
		return Resultado(_("Las dos contraseñas no coinciden; no se ha cambiado nada."), refrescar=False)
	token = cliente.confirmar_contrasena()
	cliente.llamar("SYNO.Core.User", "set", name=f.datos["name"], password=nueva, SynoConfirmPWToken=token)
	return _hecho(_("Contraseña de {u} cambiada").format(u=f.datos["name"]))


def _cargar_usuarios(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.User", "list", type="local", offset=0, limit=-1, additional=["email", "description", "expired"])
	except errores.SinPermiso:
		return sin_permiso("usuarios", _("Usuarios y grupos"))
	grupos = _intentar(lambda: cliente.llamar("SYNO.Core.Group", "list", offset=0, limit=-1), {}) or {}
	miembros: dict[str, list[str]] = {}
	for grupo in grupos.get("groups", []):
		for miembro in grupo.get("members", []):
			miembros.setdefault(str(miembro), []).append(str(grupo.get("name")))
	c_usuario = [_("Usuario"), _("Estado"), _("Descripción"), _("Correo"), _("Grupos"), _("Último acceso")]
	usuarios = [fila(c_usuario, [u.get("name"), _("Activo") if u.get("expired") == "normal" else _("Desactivado"), u.get("description"),
		u.get("email"), ", ".join(u.get("groups") or miembros.get(str(u.get("name")), [])), u.get("last_login", "")], str(u.get("name")),
		dict(u)) for u in datos.get("users", [])]
	c_grupo = [_("Grupo"), _("Descripción"), _("Miembros")]
	filas_grupo = [fila(c_grupo, [g.get("name"), g.get("description"), ", ".join(g.get("members", []))], str(g.get("name")))
		for g in grupos.get("groups", [])]
	return Vista("usuarios", [
		Seccion("usuarios", _("Usuarios"), c_usuario, usuarios, [
			Accion("desactivar", _("Desactivar el usuario"), _("Impide que el usuario elegido inicie sesión en el NAS."), True,
				_activar_usuario(False), disponible=_activo,
				confirmacion=lambda f, s: _("¿Desactivar el usuario {u}? No podrá iniciar sesión en el NAS.").format(u=f.valores[0])),
			Accion("activar", _("Activar el usuario"), _("Permite de nuevo que el usuario elegido inicie sesión."), True,
				_activar_usuario(True), disponible=lambda f: not _activo(f),
				confirmacion=lambda f, s: _("¿Activar el usuario {u}?").format(u=f.valores[0])),
			Accion("contrasena", _("Cambiar la contraseña..."), _("Cambia la contraseña del usuario elegido; DSM pide antes la suya."), True,
				_contrasena_usuario, pedir=(Peticion("nueva", _("&Contraseña nueva:"), "contrasena"),
					Peticion("repetida", _("&Repita la contraseña:"), "contrasena")),
				confirmacion=lambda f, s: _("¿Cambiar la contraseña de {u}?").format(u=f.valores[0])),
		]),
		Seccion("grupos", _("Grupos"), c_grupo, filas_grupo),
	])


# ── 6. Paquetes ──────────────────────────────────────────────────────────────


def _paquete(accion: str) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		if accion == "actualizar":
			cliente.llamar("SYNO.Core.Package.Installation", "upgrade", id=f.datos["id"])
			return _hecho(_("Paquete {p} actualizado").format(p=f.valores[0]))
		cliente.llamar("SYNO.Core.Package.Control", accion, id=f.datos["id"])
		return _hecho((_("Paquete {p} iniciado") if accion == "start" else _("Paquete {p} parado")).format(p=f.valores[0]))

	return ejecutar


def _cargar_paquetes(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.Package", "list", additional=["description", "status", "startable", "autoupdate", "install_type"])
	except errores.SinPermiso:
		return sin_permiso("paquetes", _("Paquetes"))
	disponibles = _intentar(lambda: cliente.llamar("SYNO.Core.Package.Server", "list", blforcereload=False, blloadothers=False), {}) or {}
	versiones = {str(p.get("id")): str(p.get("version", "")) for p in disponibles.get("packages", [])}
	columnas = [_("Paquete"), _("Estado"), _("Versión"), _("Actualización")]
	filas = []
	for paquete in sorted(datos.get("packages", []), key=lambda p: str(p.get("name", "")).casefold()):
		extra = paquete.get("additional") or {}
		nueva = versiones.get(str(paquete.get("id")), "")
		actualizacion = nueva if nueva and nueva != paquete.get("version") else ""
		filas.append(fila(columnas, [paquete.get("name"), estado(extra.get("status")), paquete.get("version"),
			_("Hay una nueva: {v}").format(v=actualizacion) if actualizacion else _("Al día")], str(paquete.get("id")),
			{"id": paquete.get("id"), "estado": extra.get("status"), "actualizable": bool(actualizacion), "startable": extra.get("startable", True)},
			extra=str(extra.get("description", ""))))
	return Vista("paquetes", [Seccion("paquetes", _("Paquetes instalados"), columnas, filas, [
		Accion("iniciar", _("Iniciar el paquete"), _("Pone en marcha el paquete elegido."), True, _paquete("start"),
			disponible=lambda f: f.datos.get("estado") != "running" and f.datos.get("startable", True),
			confirmacion=lambda f, s: _("¿Iniciar el paquete {p}?").format(p=f.valores[0])),
		Accion("parar", _("Parar el paquete"), _("Detiene el paquete elegido; sus servicios dejan de funcionar."), True, _paquete("stop"),
			disponible=lambda f: f.datos.get("estado") == "running" and f.datos.get("startable", True),
			confirmacion=lambda f, s: _("¿Parar el paquete {p}? Sus servicios dejarán de funcionar.").format(p=f.valores[0])),
		Accion("actualizar", _("Actualizar el paquete"), _("Instala la versión nueva del paquete elegido (lo para mientras tanto)."), True,
			_paquete("actualizar"), disponible=lambda f: bool(f.datos.get("actualizable")),
			confirmacion=lambda f, s: _("¿Actualizar el paquete {p}? Se detendrá mientras se instala.").format(p=f.valores[0])),
	])])


# ── 7. Container Manager ─────────────────────────────────────────────────────


def _contenedor(accion: str, texto: str) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		cliente.llamar("SYNO.Docker.Container", accion, name=f.datos["name"])
		return _hecho(texto.format(c=f.datos["name"]))

	return ejecutar


def _registro_contenedor(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	datos = cliente.llamar("SYNO.Docker.Container.Log", "get", name=f.datos["name"], offset=0, limit=200, sort_dir="ASC")
	lineas = [f"{r.get('created', '')} {r.get('stream', '')}: {r.get('text', '')}" for r in datos.get("logs", [])]
	return _hecho(_("Registro de {c}: {n} líneas").format(c=f.datos["name"], n=len(lineas)), texto="\n".join(lineas) or _("(vacío)"),
		titulo=_("Registro de {c}").format(c=f.datos["name"]), refrescar=False)


def _recursos_contenedor(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	datos = cliente.llamar("SYNO.Docker.Container.Resource", "get")
	propio = next((r for r in datos.get("resources", []) if r.get("name") == f.datos["name"]), {})
	texto = _("{c}: procesador {p} %, memoria {m} ({mp} %)").format(c=f.datos["name"], p=propio.get("cpu", 0),
		m=tamano(propio.get("memory", 0)), mp=propio.get("memoryPercent", 0))
	return _hecho(texto, refrescar=False)


def _proyecto(accion: str) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		cliente.llamar("SYNO.Docker.Project", accion, id=f.datos["id"])
		return _hecho((_("Proyecto {p} iniciado") if accion == "start" else _("Proyecto {p} parado")).format(p=f.valores[0]))

	return ejecutar


def _cargar_contenedores(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Docker.Container", "list", offset=0, limit=-1, type="all")
	except errores.SinPermiso:
		return sin_permiso("contenedores", _("Container Manager"))
	recursos = _intentar(lambda: cliente.llamar("SYNO.Docker.Container.Resource", "get"), {}) or {}
	por_nombre = {r.get("name"): r for r in recursos.get("resources", [])}
	c_cont = [_("Contenedor"), _("Estado"), _("Salud"), _("Imagen"), _("Procesador"), _("Memoria"), _("En marcha desde")]
	contenedores = []
	for c in datos.get("containers", []):
		recurso = por_nombre.get(c.get("name"), {})
		salud = str(c.get("health", ""))
		aviso = _("El contenedor {c} tiene problemas de salud").format(c=c.get("name")) if salud == "unhealthy" else ""
		contenedores.append(fila(c_cont, [c.get("name"), estado(c.get("status")), estado(salud) if salud else _("Sin comprobación"),
			c.get("image"), f"{recurso.get('cpu', 0)} %", tamano(recurso.get("memory", 0)), c.get("up_status", "")], str(c.get("name")),
			{"name": c.get("name"), "status": c.get("status")}, aviso))
	marcha = lambda f: f.datos.get("status") == "running"  # noqa: E731 - condición corta de las acciones
	acciones_cont = [
		Accion("registro", _("Ver el registro"), _("Muestra las últimas 200 líneas del registro del contenedor."), False,
			_registro_contenedor, por_defecto=True),
		Accion("recursos", _("Uso de recursos"), _("Dice el procesador y la memoria que usa el contenedor."), False, _recursos_contenedor),
		Accion("iniciar", _("Iniciar el contenedor"), _("Pone en marcha el contenedor elegido."), True,
			_contenedor("start", _("Contenedor {c} iniciado")), disponible=lambda f: not marcha(f),
			confirmacion=lambda f, s: _("¿Iniciar el contenedor {c}?").format(c=f.valores[0])),
		Accion("parar", _("Parar el contenedor"), _("Detiene el contenedor elegido."), True, _contenedor("stop", _("Contenedor {c} parado")),
			disponible=marcha, confirmacion=lambda f, s: _("¿Parar el contenedor {c}?").format(c=f.valores[0])),
		Accion("reiniciar", _("Reiniciar el contenedor"), _("Para y vuelve a poner en marcha el contenedor elegido."), True,
			_contenedor("restart", _("Contenedor {c} reiniciado")), disponible=marcha,
			confirmacion=lambda f, s: _("¿Reiniciar el contenedor {c}?").format(c=f.valores[0])),
	]
	secciones = [Seccion("contenedores", _("Contenedores"), c_cont, contenedores, acciones_cont, _("No hay contenedores."))]
	proyectos = _intentar(lambda: cliente.llamar("SYNO.Docker.Project", "list"), None)
	if proyectos is not None:
		nombres_id = {c.get("id"): c.get("name") for c in datos.get("containers", [])}
		c_proy = [_("Proyecto"), _("Estado"), _("Contenedores"), _("Carpeta")]
		filas = []
		for p in (proyectos.values() if isinstance(proyectos, dict) else proyectos):
			if not isinstance(p, dict):
				continue
			aviso = _("El proyecto {p} tiene errores").format(p=p.get("name")) if p.get("status") == "ERROR" else ""
			filas.append(fila(c_proy, [p.get("name"), estado(p.get("status")), ", ".join(str(nombres_id.get(i, i))[:30] for i in p.get("containerIds", [])),
				p.get("share_path")], str(p.get("id")), {"id": p.get("id"), "status": p.get("status")}, aviso))
		secciones.append(Seccion("proyectos", _("Proyectos"), c_proy, filas, [
			Accion("iniciar_proyecto", _("Iniciar el proyecto"), _("Pone en marcha todos los contenedores del proyecto."), True,
				_proyecto("start"), disponible=lambda f: f.datos.get("status") != "RUNNING",
				confirmacion=lambda f, s: _("¿Iniciar el proyecto {p}?").format(p=f.valores[0])),
			Accion("parar_proyecto", _("Parar el proyecto"), _("Detiene todos los contenedores del proyecto."), True, _proyecto("stop"),
				disponible=lambda f: f.datos.get("status") != "STOPPED",
				confirmacion=lambda f, s: _("¿Parar el proyecto {p} y todos sus contenedores?").format(p=f.valores[0])),
		], _("No hay proyectos.")))
	imagenes = _intentar(lambda: cliente.llamar("SYNO.Docker.Image", "list", offset=0, limit=-1, show_dsm=False), None)
	if imagenes is not None:
		c_img = [_("Imagen"), _("Etiquetas"), _("Tamaño"), _("Actualización")]
		secciones.append(Seccion("imagenes", _("Imágenes"), c_img, [fila(c_img, [i.get("repository"), ", ".join(i.get("tags", [])),
			tamano(i.get("size")), _("Hay una nueva") if i.get("upgradable") else _("Al día")], str(i.get("repository")))
			for i in imagenes.get("images", [])], vacia=_("No hay imágenes.")))
	return Vista("contenedores", secciones)


# ── 8. Synology Drive y 9. Photos ────────────────────────────────────────────


def _cargar_drive(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		estado_drive = cliente.llamar("SYNO.SynologyDrive", "get_status")
	except errores.SinPermiso:
		return sin_permiso("drive", _("Synology Drive"))
	resumen = _intentar(lambda: cliente.llamar("SYNO.SynologyDrive.Connection", "summary"), {}) or {}
	equipos = _intentar(lambda: cliente.llamar("SYNO.SynologyDrive.Connection", "list", offset=0, limit=200), {}) or {}
	c_res = [_("Dato"), _("Valor")]
	filas_res = [fila(c_res, [_("Servicio"), estado(estado_drive.get("status"))]), fila(c_res, [_("Versión"), estado_drive.get("version", "")]),
		fila(c_res, [_("Equipos conectados"), resumen.get("total", len(equipos.get("items", [])))]),
		fila(c_res, [_("Carpetas de equipo"), resumen.get("team_folders", "")])]
	c_eq = [_("Equipo"), _("Tipo de cliente"), _("Usuario"), _("Dirección"), _("Estado"), _("Última conexión")]
	filas_eq = [fila(c_eq, [e.get("device_name"), e.get("client_type"), e.get("user_name"), e.get("ip_address"), estado(e.get("status")),
		e.get("last_connected")]) for e in equipos.get("items", [])]
	return Vista("drive", [Seccion("estado", _("Estado del servicio"), c_res, filas_res),
		Seccion("equipos", _("Equipos conectados"), c_eq, filas_eq, vacia=_("No hay equipos conectados."))])


def _reindexar(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Foto.Index", "reindex")
	return _hecho(_("Synology Photos ha empezado a volver a indexar"))


def _cargar_photos(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		indice = cliente.llamar("SYNO.Foto.Index", "get")
	except errores.SinPermiso:
		return sin_permiso("photos", _("Synology Photos"))
	columnas = [_("Dato"), _("Valor")]
	filas = [fila(columnas, [_("Indexación"), _("En curso") if indice.get("indexing") else _("Terminada")]),
		fila(columnas, [_("Fotos"), F.miles(int(indice.get("photo_count", 0) or 0))]),
		fila(columnas, [_("Vídeos"), F.miles(int(indice.get("video_count", 0) or 0))]),
		fila(columnas, [_("Último índice"), indice.get("last_index_time", "")])]
	return Vista("photos", [Seccion("indice", _("Índice de fotos"), columnas, filas, [
		Accion("reindexar", _("Volver a indexar"), _("Synology Photos vuelve a leer todas las fotos (útil tras copiarlas desde zCommander)."),
			True, _reindexar, necesita_fila=False,
			confirmacion=lambda f, s: _("¿Volver a indexar todas las fotos? Puede tardar horas y el NAS irá más lento.")),
	])])


# ── 10. Tareas programadas ───────────────────────────────────────────────────


def _ejecutar_tarea(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Core.TaskScheduler", "run", tasks=[{"id": f.datos["id"], "real_owner": f.datos.get("real_owner", "root")}])
	return _hecho(_("Tarea {t} ejecutada").format(t=f.valores[0]))


def _activar_tarea(activar: bool) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		cliente.llamar("SYNO.Core.TaskScheduler", "set_enable", status=[{"id": f.datos["id"],
			"real_owner": f.datos.get("real_owner", "root"), "enable": activar}])
		return _hecho((_("Tarea {t} activada") if activar else _("Tarea {t} desactivada")).format(t=f.valores[0]))

	return ejecutar


def _cargar_tareas(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.TaskScheduler", "list", sort_by="next_trigger_time", sort_direction="ASC", offset=0, limit=-1)
	except errores.SinPermiso:
		return sin_permiso("tareas", _("Tareas programadas"))
	historial = _intentar(lambda: cliente.llamar("SYNO.Core.TaskScheduler", "get_history_status_list", offset=0, limit=-1), {}) or {}
	ultimas = {str(h.get("id")): h for h in historial.get("list", [])}
	tipos = {"script": _("Script"), "smart_test": _("Prueba S.M.A.R.T."), "recycle": _("Vaciar papeleras"), "beep": _("Pitido")}
	columnas = [_("Tarea"), _("Activa"), _("Tipo"), _("Próxima ejecución"), _("Última ejecución"), _("Resultado")]
	filas = []
	for t in datos.get("tasks", []):
		ultima = ultimas.get(str(t.get("id")), {})
		filas.append(fila(columnas, [t.get("name"), si_no(t.get("enable")), tipos.get(str(t.get("type")), str(t.get("type", ""))),
			t.get("next_trigger_time") or _("Ninguna"), ultima.get("last_run_time", ""), ultima.get("result", "")], str(t.get("id")), dict(t),
			extra=_("Acción: {a}").format(a=t.get("action", "")) if t.get("action") else ""))
	return Vista("tareas", [Seccion("tareas", _("Tareas programadas"), columnas, filas, [
		Accion("ejecutar", _("Ejecutar ahora"), _("Ejecuta ya la tarea elegida, sin esperar a su hora."), True, _ejecutar_tarea,
			confirmacion=lambda f, s: _("¿Ejecutar ahora la tarea {t}?").format(t=f.valores[0])),
		Accion("desactivar_tarea", _("Desactivar la tarea"), _("La tarea deja de ejecutarse a su hora."), True, _activar_tarea(False),
			disponible=lambda f: bool(f.datos.get("enable")), confirmacion=lambda f, s: _("¿Desactivar la tarea {t}?").format(t=f.valores[0])),
		Accion("activar_tarea", _("Activar la tarea"), _("La tarea vuelve a ejecutarse a su hora."), True, _activar_tarea(True),
			disponible=lambda f: not f.datos.get("enable"), confirmacion=lambda f, s: _("¿Activar la tarea {t}?").format(t=f.valores[0])),
	], _("No hay tareas programadas."))])


# ── 11. Registros y conexiones ───────────────────────────────────────────────

_NIVELES = {"info": "Información", "warn": "Aviso", "err": "Error", "crit": "Crítico"}


def _filtrar(cliente: ClienteDSM, _f: Fila | None, valores: dict[str, Any]) -> Resultado:
	palabra = str(valores.get("palabra", "")).strip()
	datos = cliente.llamar("SYNO.Core.SyslogClient.Log", "list", start=0, limit=1000, target="LOCAL", logtype="system,connection",
		keyword=palabra)
	lineas = [f"{r.get('time')} {_(_NIVELES.get(str(r.get('level')), str(r.get('level'))))} {r.get('who')}: {r.get('descr')}"
		for r in datos.get("items", [])]
	return _hecho(_n("{n} suceso con «{p}»", "{n} sucesos con «{p}»", len(lineas)).format(n=len(lineas), p=palabra),
		texto="\n".join(lineas) or _("Ninguno"), titulo=_("Sucesos con «{p}»").format(p=palabra), refrescar=False)


def _exportar(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	datos = cliente.llamar("SYNO.Core.SyslogClient.Log", "list", start=0, limit=5000, target="LOCAL", logtype="system,connection")
	lineas = [f"{r.get('time')}\t{_(_NIVELES.get(str(r.get('level')), str(r.get('level'))))}\t{r.get('logtype')}\t{r.get('who')}\t"
		f"{r.get('descr')}" for r in datos.get("items", [])]
	return _hecho(_n("{n} suceso exportado", "{n} sucesos exportados", len(lineas)).format(n=len(lineas)), texto="\n".join(lineas),
		titulo=_("Registro del NAS"), refrescar=False)


def _expulsar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Core.CurrentConnection", "kick_connection", connection=[{"who": f.datos.get("who"), "type": f.datos.get("type"),
		"from": f.datos.get("from"), "pid": f.datos.get("pid")}])
	return _hecho(_("Conexión de {u} cerrada").format(u=f.datos.get("who")))


def _cargar_registros(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.SyslogClient.Log", "list", start=0, limit=200, target="LOCAL", logtype="system,connection")
	except errores.SinPermiso:
		return sin_permiso("registros", _("Registros y conexiones"))
	c_suc = [_("Fecha"), _("Nivel"), _("Tipo"), _("Usuario"), _("Suceso")]
	sucesos = [fila(c_suc, [r.get("time"), _(_NIVELES.get(str(r.get("level")), str(r.get("level")))),
		_("Conexión") if r.get("logtype") == "Connection" else _("Sistema"), r.get("who"), r.get("descr")], f"{r.get('time')}:{i}")
		for i, r in enumerate(datos.get("items", []))]
	secciones = [Seccion("sucesos", _("Sucesos del sistema y de conexión"), c_suc, sucesos, [
		Accion("filtrar", _("Filtrar..."), _("Muestra solo los sucesos que contienen un texto."), False, _filtrar, necesita_fila=False,
			pedir=(Peticion("palabra", _("&Texto que buscar:")),)),
		Accion("exportar", _("Exportar a texto"), _("Muestra todo el registro como texto, para leerlo, copiarlo o guardarlo."), False,
			_exportar, necesita_fila=False),
	], _("El registro está vacío."))]
	conexiones = _intentar(lambda: cliente.llamar("SYNO.Core.CurrentConnection", "get", offset=0, limit=-1), None)
	if conexiones is not None:
		c_con = [_("Usuario"), _("Tipo"), _("Desde"), _("Recurso"), _("Desde la hora")]
		filas = [fila(c_con, [c.get("who"), c.get("type"), c.get("from"), c.get("descr"), c.get("time")], f"{c.get('pid')}", dict(c))
			for c in conexiones.get("items", [])]
		secciones.append(Seccion("conexiones", _("Conexiones actuales"), c_con, filas, [
			Accion("expulsar", _("Cerrar la conexión"), _("Expulsa al usuario de esa conexión (puede volver a entrar)."), True, _expulsar,
				disponible=lambda f: bool(f.datos.get("can_be_kicked", True)),
				confirmacion=lambda f, s: _("¿Cerrar la conexión {t} de {u} desde {d}?").format(t=f.valores[1], u=f.valores[0], d=f.valores[2])),
		], _("No hay nadie conectado.")))
	return Vista("registros", secciones)


# ── 12. Notificaciones ───────────────────────────────────────────────────────


def _cargar_avisos(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.DSMNotify", "notify", action="load")
	except errores.SinPermiso:
		return sin_permiso("avisos", _("Notificaciones"))
	columnas = [_("Fecha"), _("Nivel"), _("Título"), _("Mensaje")]
	filas = []
	for aviso in datos.get("items", []):
		nivel = str(aviso.get("level", "info"))
		texto_aviso = f"{aviso.get('title')}: {aviso.get('msg')}" if nivel in ("error", "warning", "crit") else ""
		filas.append(fila(columnas, [fecha(aviso.get("time")), estado(nivel), aviso.get("title"), aviso.get("msg")], str(aviso.get("id")),
			aviso=texto_aviso))
	return Vista("avisos", [Seccion("avisos", _("Avisos de DSM"), columnas, filas, vacia=_("No hay avisos pendientes."))])


# ── 13. Red ──────────────────────────────────────────────────────────────────


def _cargar_red(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		resumen = cliente.llamar("SYNO.DSM.Network", "list")
	except errores.SinPermiso:
		return sin_permiso("red", _("Red"))
	c_res = [_("Dato"), _("Valor")]
	filas = [fila(c_res, [_("Nombre del servidor"), resumen.get("hostname", "")]), fila(c_res, [_("Puerta de enlace"), resumen.get("gateway", "")]),
		fila(c_res, [_("DNS"), ", ".join(resumen.get("dns", []))]), fila(c_res, [_("Grupo de trabajo"), resumen.get("workgroup", "")])]
	secciones = [Seccion("resumen", _("Resumen"), c_res, filas)]
	interfaces = _intentar(lambda: cliente.llamar("SYNO.Core.Network.Interface", "list"), None)
	if interfaces is not None:
		c_if = [_("Interfaz"), _("Estado"), _("Dirección IP"), _("Máscara"), _("Velocidad"), _("MAC"), _("DHCP")]
		lista = interfaces if isinstance(interfaces, list) else interfaces.get("interfaces", [])
		secciones.append(Seccion("interfaces", _("Interfaces"), c_if, [fila(c_if, [i.get("ifname"), estado(i.get("status")), i.get("ip"),
			i.get("mask"), _("{v} Mb/s").format(v=i.get("speed")) if i.get("speed") else "", i.get("mac"), si_no(i.get("use_dhcp"))],
			str(i.get("ifname"))) for i in lista]))
	ddns = _intentar(lambda: cliente.llamar("SYNO.Core.DDNS.Record", "list"), None)
	if ddns is not None:
		c_dd = [_("Proveedor"), _("Nombre"), _("IP externa"), _("Estado"), _("Actualizado")]
		secciones.append(Seccion("ddns", _("DDNS"), c_dd, [fila(c_dd, [r.get("provider"), r.get("hostname"), r.get("ip"), estado(r.get("status")),
			r.get("last_updated")]) for r in ddns.get("records", [])], vacia=_("No hay registros DDNS.")))
	quick = _intentar(lambda: cliente.llamar("SYNO.Core.QuickConnect", "get_misc_config"), None)
	if quick is not None:
		secciones.append(Seccion("quickconnect", _("QuickConnect"), c_res, [fila(c_res, [_("Activado"), si_no(quick.get("enabled"))]),
			fila(c_res, [_("Identificador"), quick.get("server_alias", "")]), fila(c_res, [_("Estado"), estado(quick.get("status"))]),
			fila(c_res, [_("Retransmisión"), si_no(quick.get("relay_enabled"))])]))
	return Vista("red", secciones)


# ── 14. Seguridad ────────────────────────────────────────────────────────────


def _analizar(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Core.SecurityScan.Operation", "start", items="ALL", notify=False)
	return _hecho(_("El Asesor de seguridad ha empezado a analizar el NAS"))


def _desbloquear(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
	cliente.llamar("SYNO.Core.Security.AutoBlock.Rules", "delete", ip=[f.datos["ip"]], type="deny")
	return _hecho(_("Dirección {i} desbloqueada").format(i=f.datos["ip"]))


_MESES = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _dias_hasta(texto: str) -> int | None:
	"""Días hasta «Jan  1 00:00:00 2027 GMT» (formato de OpenSSL que usa DSM; sin depender del idioma del sistema)."""
	partes = texto.replace("GMT", "").split()
	try:
		if len(partes) >= 4 and partes[0][:3].lower() in _MESES:
			hora, minuto, segundo = (int(p) for p in partes[2].split(":"))
			momento = datetime(int(partes[3]), _MESES[partes[0][:3].lower()], int(partes[1]), hora, minuto, segundo, tzinfo=UTC)
		else:
			momento = parsedate_to_datetime(texto)
	except (TypeError, ValueError, IndexError):
		return None
	return int((momento.timestamp() - time.time()) // 86400)


def _cargar_seguridad(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	secciones = []
	try:
		asesor = _intentar(lambda: cliente.llamar("SYNO.Core.SecurityScan.Status", "system_get"), None)
	except errores.SinPermiso:
		return sin_permiso("seguridad", _("Seguridad"))
	if asesor is not None:
		c_as = [_("Categoría"), _("Resultado"), _("Detalle")]
		filas = []
		for clave, item in (asesor.get("items") or {}).items():
			nivel = str(item.get("failSeverity", ""))
			aviso = f"{item.get('title')}: {item.get('description')}" if nivel in ("warning", "danger") else ""
			filas.append(fila(c_as, [item.get("title", clave), estado(nivel), item.get("description", "")], str(clave), aviso=aviso))
		acciones = []
		if cliente.disponible("SYNO.Core.SecurityScan.Operation"):
			acciones.append(Accion("analizar", _("Analizar con el Asesor"), _("Lanza un análisis del Asesor de seguridad (no cambia nada)."),
				False, _analizar, necesita_fila=False))
		secciones.append(Seccion("asesor", _("Asesor de seguridad"), c_as, filas, acciones))
	accesos = _intentar(lambda: cliente.llamar("SYNO.SecurityAdvisor.LoginActivity", "list", offset=0, limit=100), None)
	if accesos is not None:
		c_acc = [_("Usuario"), _("Dirección"), _("Fecha"), _("Resultado"), _("Lugar")]
		secciones.append(Seccion("accesos", _("Inicios de sesión"), c_acc, [fila(c_acc, [a.get("user"), a.get("ip"), fecha(a.get("time")),
			a.get("result"), a.get("location")], f"{a.get('time')}:{a.get('ip')}") for a in accesos.get("items", [])]))
	bloqueadas = _intentar(lambda: cliente.llamar("SYNO.Core.Security.AutoBlock.Rules", "list", type="deny", offset=0, limit=-1), None)
	if bloqueadas is not None:
		c_bl = [_("Dirección IP"), _("Bloqueada desde"), _("Caduca"), _("Lugar")]
		secciones.append(Seccion("bloqueadas", _("Direcciones bloqueadas"), c_bl, [fila(c_bl, [r.get("ip"), fecha(r.get("recordTime")),
			fecha(r.get("expireTime")) if r.get("expireTime") else _("Nunca"), r.get("location")], str(r.get("ip")), {"ip": r.get("ip")})
			for r in bloqueadas.get("rules", [])], [
			Accion("desbloquear", _("Desbloquear la dirección"), _("Quita la dirección elegida de la lista de bloqueo automático."), True,
				_desbloquear, confirmacion=lambda f, s: _("¿Desbloquear la dirección {i}?").format(i=f.valores[0])),
		], _("No hay direcciones bloqueadas.")))
	certificados = _intentar(lambda: cliente.llamar("SYNO.Core.Certificate.CRT", "list"), None)
	if certificados is not None:
		c_cert = [_("Certificado"), _("Caduca"), _("Días que quedan"), _("Emitido por"), _("Servicios"), _("Predeterminado")]
		filas = []
		for c in certificados.get("certificates", []):
			dias = _dias_hasta(str(c.get("valid_till", "")))
			nombre = (c.get("subject") or {}).get("common_name", "") or c.get("desc", "")
			aviso = _("El certificado {c} caduca en {d} días").format(c=nombre, d=dias) if dias is not None and dias <= DIAS_AVISO_CERTIFICADO else ""
			filas.append(fila(c_cert, [nombre, c.get("valid_till"), "" if dias is None else dias, (c.get("issuer") or {}).get("common_name", ""),
				", ".join(s.get("display_name", "") for s in c.get("services", [])), si_no(c.get("is_default"))], str(c.get("id")), aviso=aviso,
				extra=str(c.get("desc", ""))))
		secciones.append(Seccion("certificados", _("Certificados"), c_cert, filas))
	if not secciones:
		return sin_permiso("seguridad", _("Seguridad"))
	return Vista("seguridad", secciones)


# ── 15. Servicios ────────────────────────────────────────────────────────────

#: API → (nombre, campo que lo activa, campo del puerto, consecuencia de desactivarlo).
SERVICIOS: dict[str, tuple[str, str, str, str]] = {
	"SYNO.Core.FileServ.SMB": ("SMB (carpetas de Windows)", "enable_samba", "", "los equipos con Windows dejarán de ver las carpetas"),
	"SYNO.Core.Terminal": ("SSH", "enable_ssh", "ssh_port", "nadie podrá entrar por SSH, tampoco las herramientas avanzadas de zCommander"),
	"SYNO.WebDAV.Common": ("WebDAV por HTTPS", "enable_https", "https_port", "las unidades WebDAV conectadas dejarán de funcionar"),
	"SYNO.Core.FileServ.NFS": ("NFS", "enable_nfs", "", "los equipos con Linux que montan carpetas por NFS las perderán"),
	"SYNO.Core.FileServ.FTP": ("FTP", "enable_ftp", "portnum", "los programas de FTP no podrán conectar"),
	"SYNO.Core.FileServ.FTP.SFTP": ("SFTP", "enable", "portnum", "los programas de SFTP no podrán conectar"),
}


def _servicio(activar: bool) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, f: Fila | None, _v: dict[str, Any]) -> Resultado:
		api_nombre = f.datos["api"]
		cliente.llamar(api_nombre, "set", parametros={SERVICIOS[api_nombre][1]: activar})
		return _hecho((_("Servicio {s} activado") if activar else _("Servicio {s} desactivado")).format(s=f.valores[0]))

	return ejecutar


def _cargar_servicios(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	columnas = [_("Servicio"), _("Estado"), _("Puerto")]
	filas = []
	sin_permiso_ = 0
	for api_nombre, (nombre, campo, puerto, consecuencia) in SERVICIOS.items():
		if not cliente.disponible(api_nombre):
			continue
		try:
			datos = cliente.llamar(api_nombre, "get")
		except errores.SinPermiso:
			sin_permiso_ += 1
			continue
		activo = bool(datos.get(campo))
		filas.append(fila(columnas, [_(nombre), _("Activado") if activo else _("Desactivado"), datos.get(puerto, "") if puerto else ""],
			api_nombre, {"api": api_nombre, "activo": activo, "consecuencia": _(consecuencia)}))
	if not filas and sin_permiso_:
		return sin_permiso("servicios", _("Servicios"))
	return Vista("servicios", [Seccion("servicios", _("Servicios"), columnas, filas, [
		Accion("activar_servicio", _("Activar el servicio"), _("Activa el servicio elegido en el NAS."), True, _servicio(True),
			disponible=lambda f: not f.datos.get("activo"), confirmacion=lambda f, s: _("¿Activar el servicio {s}?").format(s=f.valores[0])),
		Accion("desactivar_servicio", _("Desactivar el servicio"), _("Desactiva el servicio elegido en el NAS."), True, _servicio(False),
			disponible=lambda f: bool(f.datos.get("activo")),
			confirmacion=lambda f, s: _("¿Desactivar el servicio {s}? Consecuencia: {c}.").format(s=f.valores[0], c=f.datos["consecuencia"])),
	])])


# ── 16. Monitor de recursos ──────────────────────────────────────────────────


def texto_monitor(uso: dict[str, Any]) -> list[tuple[str, str]]:
	cpu, memoria = uso.get("cpu", {}), uso.get("memory", {})
	red = next((n for n in uso.get("network", []) if n.get("device") == "total"), {})
	disco = (uso.get("disk") or {}).get("total", {})
	volumenes = (uso.get("space") or {}).get("volume", [])
	total_cpu = int(cpu.get("user_load", 0)) + int(cpu.get("system_load", 0)) + int(cpu.get("other_load", 0))
	return [
		(_("Procesador"), _("{p} % (carga de 1 minuto {c})").format(p=total_cpu, c=round(int(cpu.get("1min_load", 0)) / 100, 2))),
		(_("Memoria"), _("{p} % en uso, {l} libres").format(p=memoria.get("real_usage", 0),
			l=tamano(int(memoria.get("avail_real", 0)) * 1024))),
		(_("Red"), _("recibe {r}, envía {e}").format(r=F.velocidad(float(red.get("rx", 0))) or "0", e=F.velocidad(float(red.get("tx", 0))) or "0")),
		(_("Discos"), _("{p} % de uso").format(p=disco.get("utilization", 0))),
	] + [(_("Volumen {v}").format(v=v.get("display_name")), _("{p} % lleno").format(p=v.get("utilization", 0))) for v in volumenes]


def _cargar_monitor(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		uso = cliente.llamar("SYNO.Core.System.Utilization", "get", type="current",
			resource=["cpu", "memory", "network", "disk", "space"])
	except errores.SinPermiso:
		return sin_permiso("monitor", _("Monitor de recursos"))
	except errores.ErrorDSM as error:
		if error.codigo != 1055:
			raise
		uso = {}
	columnas = [_("Recurso"), _("Uso")]
	pares = texto_monitor(uso)
	resumen = ". ".join(f"{a}: {b}" for a, b in pares)
	return Vista("monitor", [Seccion("uso", _("Uso en este momento"), columnas, [fila(columnas, [a, b], a) for a, b in pares], [
		Accion("decir", _("Decir el estado"), _("Dice el uso actual del procesador, la memoria, la red y los discos (Control+Mayúsculas+T)."),
			False, lambda c, f, v: Resultado(resumen, refrescar=False), necesita_fila=False),
	])], resumen)


# ── 17. Actualizaciones ──────────────────────────────────────────────────────


def _instalar_dsm(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
	if cliente.disponible("SYNO.Core.Upgrade.Server.Download"):
		cliente.llamar("SYNO.Core.Upgrade.Server.Download", "start")
	cliente.llamar("SYNO.Core.Upgrade", "start")
	return Resultado(_("Actualización de DSM en marcha: el NAS se reiniciará y se cerrará la conexión"), desconectar=True)


def _cargar_actualizaciones(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	try:
		datos = cliente.llamar("SYNO.Core.Upgrade.Server", "check", user_reading=True, need_auto_smallupdate=True, need_promotion=False)
	except errores.SinPermiso:
		return sin_permiso("actualizaciones", _("Actualizaciones"))
	ajuste = _intentar(lambda: cliente.llamar("SYNO.Core.Upgrade.Setting", "get"), {}) or {}
	nueva = (datos.get("update") or {})
	columnas = [_("Dato"), _("Valor")]
	instalada = cliente.info.version if cliente.info else ""
	disponible = bool(nueva.get("available"))
	filas = [fila(columnas, [_("Versión instalada"), instalada], aviso=aviso_seguridad(instalada)),
		fila(columnas, [_("Actualización disponible"), (_("Sí: {v}").format(v=nueva.get("version")) if disponible else _("No, DSM está al día"))]),
		fila(columnas, [_("Reinicio necesario"), si_no(nueva.get("reboot") == "now") if disponible else ""]),
		fila(columnas, [_("Actualización automática"), {"security": _("Solo las de seguridad"), "all": _("Todas"), "none": _("Desactivada")}.get(
			str(ajuste.get("autoupdate_type", "")), str(ajuste.get("autoupdate_type", "")))]),
		fila(columnas, [_("Última comprobación"), ajuste.get("last_check", "")])]
	acciones = [Accion("comprobar", _("Comprobar ahora"), _("Pregunta a Synology si hay una versión nueva de DSM."), False,
		lambda c, f, v: Resultado(_("Comprobado")), necesita_fila=False)]
	if disponible and cliente.disponible("SYNO.Core.Upgrade"):
		acciones.append(Accion("instalar", _("Descargar e instalar..."), _("Descarga e instala la versión nueva de DSM. El NAS se reiniciará."),
			True, _instalar_dsm, necesita_fila=False, doble=True,
			confirmacion=lambda f, s: _("Va a instalar {v} en el NAS. El NAS se reiniciará y se cortarán todas las conexiones durante varios "
				"minutos. ¿Seguir?").format(v=s.get("version", ""))))
	return Vista("actualizaciones", [Seccion("dsm", _("DSM"), columnas, filas, acciones, datos={"version": nueva.get("version", "")})])


# ── 18. Apagar y reiniciar ───────────────────────────────────────────────────


def _energia(metodo: str) -> Callable[[ClienteDSM, Fila | None, dict[str, Any]], Resultado]:
	def ejecutar(cliente: ClienteDSM, _f: Fila | None, _v: dict[str, Any]) -> Resultado:
		parametros = {"force": False, "local": True} if metodo == "shutdown" else {"force": False}
		cliente.llamar("SYNO.Core.System", metodo, 1, parametros=parametros)
		texto = _("El NAS se está apagando") if metodo == "shutdown" else _("El NAS se está reiniciando")
		return Resultado(texto, desconectar=True, refrescar=False)

	return ejecutar


def consecuencias(cliente: ClienteDSM) -> dict[str, Any]:
	"""Conexiones abiertas y tareas de File Station en curso, para la primera confirmación de apagar o reiniciar (synology.md 4.16)."""
	conexiones = _intentar(lambda: cliente.llamar("SYNO.Core.CurrentConnection", "get", offset=0, limit=-1), {}) or {}
	tareas = _intentar(lambda: cliente.llamar("SYNO.FileStation.BackgroundTask", "list", offset=0, limit=0), {}) or {}
	en_curso = [t for t in tareas.get("tasks", []) if not t.get("finished")]
	return {"conexiones": len(conexiones.get("items", [])), "tareas": len(en_curso), "nombre": _nombre_nas(cliente)}


def texto_energia(accion: str, datos: dict[str, Any]) -> str:
	verbo = _("apagar") if accion == "apagar" else _("reiniciar")
	partes = [_("Va a {v} el NAS {n}.").format(v=verbo, n=datos.get("nombre", ""))]
	partes.append(_n("Se cortará {c} conexión abierta.", "Se cortarán {c} conexiones abiertas.", int(datos.get("conexiones", 0))).format(
		c=datos.get("conexiones", 0)))
	if datos.get("tareas"):
		partes.append(_n("Hay {t} tarea de File Station en curso que se interrumpirá.", "Hay {t} tareas de File Station en curso que se "
			"interrumpirán.", int(datos["tareas"])).format(t=datos["tareas"]))
	if accion == "apagar":
		partes.append(_("Para volver a encenderlo tendrá que pulsar su botón o usar Wake on LAN."))
	partes.append(_("¿Seguir?"))
	return " ".join(partes)


def accion_energia(accion_id: str) -> Accion:
	"""«reiniciar» o «apagar»: doble confirmación; la segunda exige escribir el nombre del NAS (13.5)."""
	if accion_id == "reiniciar":
		return Accion("reiniciar", _("Reiniciar el NAS..."), _("Reinicia el NAS. Pide dos confirmaciones: la segunda, escribir su nombre."),
			True, _energia("reboot"), necesita_fila=False, doble=True, confirmacion=lambda f, s: texto_energia("reiniciar", s))
	return Accion("apagar", _("Apagar el NAS..."), _("Apaga el NAS. Pide dos confirmaciones: la segunda, escribir su nombre."), True,
		_energia("shutdown"), necesita_fila=False, doble=True, confirmacion=lambda f, s: texto_energia("apagar", s))


def _cargar_energia(cliente: ClienteDSM, ajustes: dict[str, Any]) -> Vista:
	datos = consecuencias(cliente)
	columnas = [_("Dato"), _("Valor")]
	filas = [fila(columnas, [_("Nombre del NAS"), datos["nombre"]]), fila(columnas, [_("Conexiones abiertas"), datos["conexiones"]]),
		fila(columnas, [_("Tareas de File Station en curso"), datos["tareas"]])]
	return Vista("energia", [Seccion("energia", _("Apagar y reiniciar"), columnas, filas,
		[accion_energia("reiniciar"), accion_energia("apagar")], datos=datos)])


# ── Catálogo de áreas ────────────────────────────────────────────────────────

AREAS: tuple[Area, ...] = (
	Area("estado", _("Estado y salud"), _("Modelo, DSM, seguridad, temperatura, procesador, memoria, volúmenes y avisos."),
		("SYNO.Core.System", "SYNO.DSM.Info"), _cargar_estado),
	Area("almacenamiento", _("Almacenamiento y discos"), _("Volúmenes, grupos de almacenamiento y discos con su S.M.A.R.T."),
		("SYNO.Storage.CGI.Storage",), _cargar_almacenamiento),
	Area("archivos", _("File Station"), _("Carpetas compartidas, tareas en segundo plano y enlaces compartidos."),
		("SYNO.FileStation.List",), _cargar_archivos),
	Area("carpetas", _("Carpetas compartidas"), _("Carpetas compartidas con cifrado, papelera, cuota y permisos por usuario."),
		("SYNO.Core.Share",), _cargar_carpetas),
	Area("usuarios", _("Usuarios y grupos"), _("Usuarios con su estado y sus grupos."), ("SYNO.Core.User",), _cargar_usuarios),
	Area("paquetes", _("Paquetes"), _("Paquetes instalados con versión, estado y actualizaciones."), ("SYNO.Core.Package",), _cargar_paquetes),
	Area("contenedores", _("Container Manager"), _("Contenedores, proyectos e imágenes de Docker."), ("SYNO.Docker.Container",),
		_cargar_contenedores),
	Area("drive", _("Synology Drive"), _("Estado del servicio y equipos conectados."), ("SYNO.SynologyDrive",), _cargar_drive),
	Area("photos", _("Synology Photos"), _("Estado del índice de fotos."), ("SYNO.Foto.Index",), _cargar_photos),
	Area("tareas", _("Tareas programadas"), _("Tareas del Programador de tareas de DSM."), ("SYNO.Core.TaskScheduler",), _cargar_tareas),
	Area("registros", _("Registros y conexiones"), _("Sucesos del sistema y conexiones actuales."), ("SYNO.Core.SyslogClient.Log",),
		_cargar_registros),
	Area("avisos", _("Notificaciones"), _("Avisos pendientes de DSM."), ("SYNO.Core.DSMNotify",), _cargar_avisos),
	Area("red", _("Red"), _("Interfaces, DDNS y QuickConnect."), ("SYNO.DSM.Network",), _cargar_red),
	Area("seguridad", _("Seguridad"), _("Asesor de seguridad, inicios de sesión, direcciones bloqueadas y certificados."),
		("SYNO.Core.SecurityScan.Status", "SYNO.Core.Security.AutoBlock.Rules", "SYNO.Core.Certificate.CRT"), _cargar_seguridad),
	Area("servicios", _("Servicios"), _("SMB, SSH, WebDAV, NFS, FTP y SFTP."), tuple(SERVICIOS), _cargar_servicios),
	Area("monitor", _("Monitor de recursos"), _("Procesador, memoria, red y discos en este momento."), ("SYNO.Core.System.Utilization",),
		_cargar_monitor),
	Area("actualizaciones", _("Actualizaciones"), _("Versión de DSM instalada y disponible."), ("SYNO.Core.Upgrade.Server",),
		_cargar_actualizaciones),
	Area("energia", _("Apagar y reiniciar"), _("Apagar o reiniciar el NAS con doble confirmación."), ("SYNO.Core.System",), _cargar_energia),
)

POR_ID: dict[str, Area] = {a.id: a for a in AREAS}


def disponibles(cliente: ClienteDSM) -> list[Area]:
	return [a for a in AREAS if a.disponible(cliente)[0]]


def cargar(area: Area, cliente: ClienteDSM, ajustes: dict[str, Any] | None = None) -> Vista:
	"""[trabajo] La vista del área. 105 y 160 se convierten en «Sin permiso con esta cuenta»."""
	try:
		return area.cargar(cliente, ajustes or {})
	except errores.SinPermiso:
		return sin_permiso(area.id, area.titulo)


# ── Ejecutar acciones ────────────────────────────────────────────────────────


def preparar(accion: Accion, fila_: Fila | None, seccion: Seccion, cliente: ClienteDSM, confirmador: Confirmador) -> dict[str, Any] | None:
	"""[interfaz] Pide los datos y las confirmaciones de una acción. ``None`` si la persona cancela (o el modo no lo permite)."""
	if accion.escritura and cliente.solo_lectura:
		raise errores.solo_lectura(cliente.servidor.nombre)
	valores: dict[str, Any] = {}
	for peticion in accion.pedir:
		respuesta = confirmador.pedir(accion.etiqueta.rstrip("."), peticion)
		if respuesta is None:
			return None
		valores[peticion.clave] = respuesta
	if accion.escritura:
		texto = accion.confirmacion(fila_, seccion.datos) if accion.confirmacion else _("¿{a}?").format(a=accion.etiqueta.rstrip("."))
		if not confirmador.confirmar(accion.etiqueta.rstrip("."), texto, True):
			return None
		if accion.doble:
			nombre = str(seccion.datos.get("nombre") or _nombre_nas(cliente))
			if not confirmador.escribir_nombre(accion.etiqueta.rstrip("."), _("Para confirmar, escriba el nombre del NAS: {n}").format(n=nombre),
					nombre):
				return None
	return valores


def ejecutar(accion: Accion, cliente: ClienteDSM, fila_: Fila | None, valores: dict[str, Any]) -> Resultado:
	"""[trabajo] Ejecuta la acción ya confirmada."""
	if accion.escritura:
		cliente.comprobar_escritura("SYNO.Core.System", "set")
	return accion.funcion(cliente, fila_, valores)
