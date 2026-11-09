# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestión de los complementos instalados (diseño 2.0, 3.9 a 3.11). Sin wx.

Bloque PL. Es el modelo del gestor de complementos (``app/ui/dialogos/pl_gestor.py``):

- Filas de la lista (Nombre, Versión, Estado, Origen, Confianza, Autor) con el
  estado en TEXTO y el cambio pendiente tras una coma (3.11, 15.2).
- Detalles: descripción, permisos en lenguaje claro, licencia, web, componentes,
  dependencias, tiempo de carga y último error.
- Habilitar, inhabilitar, aceptar un complemento sin firma, confiar en su autor,
  volver a intentarlo y el registro de un complemento.
- ``lineas_soporte`` para «Información para soporte» (14.9).

Las funciones que cambian el estado del registro se llaman en el hilo de la interfaz.
"""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.plugins import estado as modulo_estado
from app.plugins import firma, paquetes, registro
from app.plugins.estado import EstadoComplemento, Pendiente

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass(frozen=True)
class Fila:
	"""Una fila del gestor. ``id`` vacío en una carpeta con el manifiesto roto."""

	id: str
	nombre: str
	version: str
	estado: str
	origen: str
	confianza: str
	autor: str
	carpeta: Path

	def valores(self) -> list[str]:
		return [self.nombre, self.version, self.estado, self.origen, self.confianza, self.autor]


_TEXTOS_PENDIENTE = {
	Pendiente.ACTUALIZAR: "se actualizará al reiniciar",
	Pendiente.VOLVER_ATRAS: "volverá a la versión anterior al reiniciar",
	Pendiente.DESINSTALAR: "se desinstalará al reiniciar",
	Pendiente.INSTALAR: "se instalará de nuevo al reiniciar",
}


def texto_estado(registrado: registro.Registrado, pendiente: Pendiente = Pendiente.NINGUNO) -> str:
	"""Estado en texto (3.11): «Activo», «Sin cargar todavía», «Incompatible: necesita la API 1.1»..."""
	estado = registrado.estado
	if estado == EstadoComplemento.ACTIVO:
		texto = _("Activo")
	elif estado == EstadoComplemento.REGISTRADO:
		texto = _("Sin cargar todavía")
	elif estado == EstadoComplemento.CARGANDO:
		texto = _("Cargando")
	elif estado == EstadoComplemento.INHABILITADO:
		texto = _("Inhabilitado")
	elif estado == EstadoComplemento.SIN_ACEPTAR:
		texto = _("Sin aceptar")
	elif estado == EstadoComplemento.INCOMPATIBLE:
		texto = registrado.motivo or _("Incompatible")
	elif estado == EstadoComplemento.ERROR_MANIFIESTO:
		texto = _("Error en el manifiesto")
	elif registrado.motivo.startswith((_("Falló al"), _("El complemento"), _("Los archivos"), _("Falta el"), _("Dependencia"))):
		texto = _("Falló al cargar")
	else:
		texto = _("Fuera de uso por errores")
	pendiente = registrado.pendiente if pendiente == Pendiente.NINGUNO else pendiente
	if pendiente != Pendiente.NINGUNO:
		texto = f"{texto}, {_(_TEXTOS_PENDIENTE[pendiente])}"
	return texto


def texto_origen(registrado: registro.Registrado) -> str:
	if registrado.origen == "serie":
		return _("De serie")
	if registrado.origen == "desarrollo":
		return _("En desarrollo")
	if registrado.origen == "suelto":
		return _("En la carpeta del programa")
	return _("Instalado")


def filas() -> list[Fila]:
	"""Todas las filas: registrados, carpetas con el manifiesto roto e instalaciones pendientes."""
	pendientes = paquetes.pendientes()
	resultado: list[Fila] = []
	for registrado in registro.complementos():
		pendiente = pendientes.get(registrado.id, Pendiente.NINGUNO)
		registrado.pendiente = pendiente
		datos = registrado.manifiesto
		resultado.append(Fila(datos.id, datos.nombre, datos.version, texto_estado(registrado, pendiente), texto_origen(registrado),
			registrado.confianza or _("Sin firma"), datos.autor, registrado.carpeta))
	for carpeta, _problemas in registro.errores():
		resultado.append(Fila("", carpeta.name, "", _("Error en el manifiesto"), _("Instalado"), "", "", carpeta))
	for id_complemento, pendiente in pendientes.items():
		if registro.complemento(id_complemento) is None and pendiente == Pendiente.INSTALAR:
			carpeta = paquetes.carpeta_pendientes() / id_complemento
			try:
				from app.plugins import manifiesto

				datos = manifiesto.leer(carpeta)
				resultado.append(Fila(datos.id, datos.nombre, datos.version, _("Se instalará al reiniciar"), _("Instalado"),
					"", datos.autor, carpeta))
			except Exception:  # noqa: BLE001 - un pendiente roto se ve igual, con su carpeta
				log.debug("Pendiente sin manifiesto legible: %s", carpeta, exc_info=True)
	return resultado


def hay_pendientes() -> bool:
	return bool(paquetes.pendientes())


def detalles(id_complemento: str, carpeta: Path | None = None, ocupadas: dict[str, str] | None = None) -> str:
	"""Texto de solo lectura del gestor para un complemento (o una carpeta con el manifiesto roto)."""
	registrado = registro.complemento(id_complemento) if id_complemento else None
	if registrado is None:
		for ruta, problemas in registro.errores():
			if carpeta is not None and ruta == carpeta:
				return _("Error en el manifiesto de {c}:").format(c=ruta) + "\n" + "\n".join(f"- {p}" for p in problemas)
		return _("Se instalará al reiniciar zCommander.") if id_complemento else ""
	datos = registrado.manifiesto
	lineas = [datos.descripcion, ""]
	lineas.append(_("Identificador: {i}").format(i=datos.id))
	lineas.append(_("Estado: {e}").format(e=texto_estado(registrado)))
	if registrado.motivo:
		lineas.append(_("Motivo: {m}").format(m=registrado.motivo))
	lineas.append(_("Autor: {a}").format(a=datos.autor))
	lineas.append(_("Licencia: {l}").format(l=datos.licencia))
	for campo, titulo in (("web", _("Web")), ("codigo_fuente", _("Código fuente"))):
		if datos.datos.get(campo):
			lineas.append(f"{titulo}: {datos.datos[campo]}")
	lineas.append(_("Confianza: {c}").format(c=registrado.confianza or _("Sin firma")))
	permisos = [paquetes.texto_permiso(p) for p in datos.permisos]
	lineas.append(_("Permisos: {p}").format(p="; ".join(permisos) if permisos else _("ninguno")))
	if datos.requiere_complementos:
		lineas.append(_("Necesita los complementos: {d}").format(d=", ".join(datos.requiere_complementos)))
	if datos.requiere_componentes:
		lineas.append(_("Usa los componentes: {c}").format(c=", ".join(datos.requiere_componentes)))
	if registrado.tiempo_carga:
		lineas.append(_("Tiempo de carga: {t} ms").format(t=round(registrado.tiempo_carga * 1000)))
	fallos = modulo_estado.fallos(datos.id)
	if fallos:
		lineas.append(_("Fallos en esta sesión: {n}").format(n=fallos))
	if registrado.origen == "suelto":
		lineas.append(_("Este complemento está en la carpeta del programa y se borrará al actualizar zCommander; instálelo desde el gestor."))
	internas = paquetes.partes_internas(registrado.carpeta) if registrado.origen != "serie" else []
	if internas:
		lineas.append(_("Usa partes internas de zCommander: {p}").format(p=", ".join(internas[:5])))
	for modulo, ids in paquetes.choques_lib().items():
		if datos.id in ids:
			lineas.append(_("Su biblioteca {m} también la traen: {o}").format(m=modulo, o=", ".join(i for i in ids if i != datos.id)))
	sin_tecla = teclas_perdidas(datos.id, ocupadas)
	if sin_tecla:
		lineas.append(_("Teclas que no se le dieron porque ya las usa otra orden: {t}").format(t=", ".join(sin_tecla)))
	lineas.append(_("Carpeta: {c}").format(c=registrado.carpeta))
	return "\n".join(lineas)


def teclas_perdidas(id_complemento: str, ocupadas: dict[str, str] | None = None) -> list[str]:
	"""Teclas del manifiesto de un complemento de terceros que ya usa otra orden (14.1.3).

	:param ocupadas: tecla → id de orden de todo el catálogo (lo da la interfaz, que
		conoce el catálogo del núcleo); sin él solo se comparan los complementos.
	"""
	registrado = registro.complemento(id_complemento)
	if registrado is None or registrado.origen == "serie":
		return []
	propias = {f"{id_complemento}:{o.id}" for o in registrado.manifiesto.ordenes}
	otras: dict[str, str] = {}
	for orden in registro.ordenes():
		if orden.id not in propias:
			for tecla in orden.teclas:
				otras.setdefault(tecla, orden.id)
	for tecla, id_orden in (ocupadas or {}).items():
		if id_orden not in propias:
			otras.setdefault(tecla, id_orden)
	return [t for o in registrado.manifiesto.ordenes for t in o.teclas if t in otras]


# ── Acciones de la persona ───────────────────────────────────────────────────


def _lista(config: Any, clave: str) -> list[str]:
	try:
		valor = config.obtener(clave)
	except Exception:  # noqa: BLE001
		valor = []
	return [str(v) for v in (valor or [])]


def inhabilitar(config: Any, id_complemento: str) -> None:
	"""Lo apunta en ``complementos.inhabilitados``; sus órdenes avisan en el acto «está inhabilitado»."""
	inhabilitados = _lista(config, "complementos.inhabilitados")
	if id_complemento not in inhabilitados:
		config.establecer("complementos.inhabilitados", [*inhabilitados, id_complemento])
	registrado = registro.complemento(id_complemento)
	if registrado is not None and registrado.estado not in (EstadoComplemento.ERROR_MANIFIESTO, EstadoComplemento.INCOMPATIBLE):
		registrado.estado_antes = registrado.estado  # type: ignore[attr-defined]
		registro.fijar_estado(id_complemento, EstadoComplemento.INHABILITADO)


def habilitar(config: Any, id_complemento: str) -> None:
	inhabilitados = _lista(config, "complementos.inhabilitados")
	if id_complemento in inhabilitados:
		config.establecer("complementos.inhabilitados", [i for i in inhabilitados if i != id_complemento])
	registrado = registro.complemento(id_complemento)
	if registrado is None or registrado.estado != EstadoComplemento.INHABILITADO:
		return
	from app.plugins import cargador

	actual = cargador.actual()
	activo = actual is not None and actual.instancia(id_complemento) is not None
	registro.fijar_estado(id_complemento, EstadoComplemento.ACTIVO if activo else EstadoComplemento.REGISTRADO)
	registrado.motivo = ""


def aceptar(config: Any, id_complemento: str) -> None:
	"""Acepta un complemento sin firma (``SIN_ACEPTAR``): guarda la suma del paquete en ``complementos.confiados``."""
	registrado = registro.complemento(id_complemento)
	if registrado is None:
		return
	suma = firma.suma_paquete(registrado.carpeta, registrado.id, registrado.manifiesto.version)
	paquetes.fijar_confiado(config, id_complemento, suma)
	registrado.suma_aceptada = suma
	registrado.sumas = None
	registrado.motivo = ""
	registrado.confianza = _("Sin firma")
	if registrado.estado == EstadoComplemento.SIN_ACEPTAR:
		registro.fijar_estado(id_complemento, EstadoComplemento.REGISTRADO)


def puede_confiar_en_autor(id_complemento: str) -> bool:
	registrado = registro.complemento(id_complemento)
	if registrado is None or registrado.origen == "serie":
		return False
	clave = clave_del_autor(id_complemento)
	return bool(clave) and clave not in paquetes.leer_claves()["confiadas"] and clave not in firma.CLAVES_PROYECTO


def clave_del_autor(id_complemento: str) -> str | None:
	registrado = registro.complemento(id_complemento)
	if registrado is None:
		return None
	return paquetes.leer_claves()["por_id"].get(id_complemento) or firma.clave_declarada(registrado.carpeta)


def confiar_en_autor(id_complemento: str) -> bool:
	"""Añade la clave del autor a las de confianza de ``claves.json`` (3.9)."""
	clave = clave_del_autor(id_complemento)
	if not clave:
		return False
	claves = paquetes.leer_claves()
	if clave not in claves["confiadas"]:
		claves["confiadas"].append(clave)
		paquetes.escribir_claves(claves)
	registrado = registro.complemento(id_complemento)
	if registrado is not None and registrado.confianza != _("Oficial"):
		registrado.confianza = _("Firmado por un autor de confianza")
	return True


def puede_reintentar(id_complemento: str) -> bool:
	registrado = registro.complemento(id_complemento)
	return registrado is not None and registrado.estado == EstadoComplemento.FALLIDO and registrado.reintentable


def reintentar(id_complemento: str) -> bool:
	"""«Volver a intentarlo»: un complemento fuera de uso vuelve a ``REGISTRADO`` (no si agotó el tope de carga)."""
	if not puede_reintentar(id_complemento):
		return False
	modulo_estado.olvidar(id_complemento)
	from app.plugins import cargador

	actual = cargador.actual()
	activo = actual is not None and actual.instancia(id_complemento) is not None
	registro.fijar_estado(id_complemento, EstadoComplemento.ACTIVO if activo else EstadoComplemento.REGISTRADO)
	registrado = registro.complemento(id_complemento)
	if registrado is not None:
		registrado.motivo = ""
	return True


def puede_desinstalar(id_complemento: str) -> bool:
	registrado = registro.complemento(id_complemento)
	if registrado is None:
		return (paquetes.carpeta_pendientes() / id_complemento).is_dir()
	return registrado.origen in ("usuario", "suelto") and registrado.carpeta.parent == paquetes.carpeta_usuario()


def desinstalar(id_complemento: str, borrar_datos: bool) -> None:
	"""Marca el complemento para borrarlo al reiniciar (sus teclas personalizadas se conservan)."""
	registrado = registro.complemento(id_complemento)
	if registrado is None:
		paquetes.cancelar_pendiente(id_complemento)
		return
	paquetes.marcar_desinstalar(id_complemento, borrar_datos)
	registrado.pendiente = Pendiente.DESINSTALAR


def volver_atras(id_complemento: str) -> str:
	version = paquetes.marcar_volver_atras(id_complemento)
	registrado = registro.complemento(id_complemento)
	if registrado is not None:
		registrado.pendiente = Pendiente.VOLVER_ATRAS
	return version


def tiene_ayuda(id_complemento: str) -> bool:
	return ruta_documento(id_complemento, "ayuda") is not None


def ruta_documento(id_complemento: str, cual: str) -> Path | None:
	"""``doc/es/leeme.md`` (``ayuda``) o ``doc/es/cambios.md`` (``cambios``) del complemento, si existe."""
	registrado = registro.complemento(id_complemento)
	if registrado is None:
		return None
	defecto = "doc/es/leeme.md" if cual == "ayuda" else "doc/es/cambios.md"
	ruta = registrado.carpeta / str(registrado.manifiesto.datos.get(cual, defecto))
	return ruta if ruta.is_file() else None


def lineas_registro(id_complemento: str, maximo: int = 400) -> list[str]:
	"""Líneas del registro de la sesión con ``zcplugins.<id>`` o que nombran el complemento («Ver su registro»)."""
	from app.core import paths

	carpeta = paths.ruta_registros()
	sesiones = sorted(carpeta.glob("sesion_*.log")) if carpeta.is_dir() else []
	if not sesiones:
		return []
	marcas = (f"zcplugins.{id_complemento}", f" {id_complemento} ", f" {id_complemento}:", f"({id_complemento})")
	resultado: list[str] = []
	try:
		with open(sesiones[-1], encoding="utf-8", errors="replace") as archivo:
			for linea in archivo:
				if any(marca in linea for marca in marcas):
					resultado.append(linea.rstrip("\n"))
	except OSError:
		log.warning("No se pudo leer el registro de la sesión", exc_info=True)
	return resultado[-maximo:]


def lineas_soporte() -> list[str]:
	"""Una línea por complemento registrado: nombre, id, versión, estado y confianza (14.9)."""
	lineas = []
	for registrado in registro.complementos():
		datos = registrado.manifiesto
		confianza = f", {registrado.confianza}" if registrado.confianza else ""
		lineas.append(f"{datos.nombre} ({datos.id}) {datos.version}: {texto_estado(registrado)}{confianza}")
	return lineas
