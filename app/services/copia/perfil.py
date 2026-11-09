# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Perfiles exportables ``.zcperfil`` (diseño 2.0, 10.2). Sin wx.

Un ``.zcperfil`` es una copia de tipo ``perfil`` con las partes preferencias,
teclas, personalización y macros y, si se pide, los paquetes de sonidos
propios; **nunca** secretos ni conexiones. Sirve, por ejemplo, para que un
formador prepare la configuración de sus alumnos.

Importar siempre combina y muestra antes una vista previa: una lista de lo que
cambia (Preferencia, Valor actual, Valor del perfil) con casillas marcadas, y
aparte, sin marcar, «Órdenes que se podrán ejecutar» (menú de usuario,
asociaciones, alias, macros y claves que ejecutan programas). Solo se aplica
lo marcado. Antes se crea la copia automática previa, como al restaurar.
"""

from __future__ import annotations

import builtins
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core import paths
from app.services.copia import combinar, crear, ejecutables, formato, restaurar
from app.services.copia.ejecutables import ElementoEjecutable, etiqueta_clave
from app.services.copia.formato import CopiaAbierta
from app.services.copia.pendiente import ResultadoRestauracion

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


PARTES_BASE = ("preferencias", "teclas", "personalizacion", "macros")

NOMBRES_ARCHIVOS = {
	"config/favoritos.json": N_("Favoritos"),
	"config/plantillas_renombrado.json": N_("Plantillas de renombrado"),
	"config/busquedas.json": N_("Búsquedas guardadas"),
	"config/menus.json": N_("Menús y barra de botones"),
	"config/vistas_carpeta.json": N_("Columnas y vistas por carpeta"),
	"config/reglas.json": N_("Reglas de anuncio, color y sonido"),
}
GRUPOS = {"plantillas/": ("grupo:plantillas", N_("Plantillas de archivo nuevo")),
	"sounds_usuario/": ("grupo:sonidos", N_("Paquetes de sonidos propios"))}


@dataclass(frozen=True)
class FilaPerfil:
	id: str
	preferencia: str
	actual: str
	nuevo: str


@dataclass
class VistaPerfil:
	filas: list[FilaPerfil] = field(default_factory=list)
	ejecutables: list[ElementoEjecutable] = field(default_factory=list)
	#: Fila de archivo o grupo → rutas a las que afecta.
	rutas: dict[str, list[str]] = field(default_factory=dict)


def partes_exportar(incluir_sonidos: bool) -> list[str]:
	return [*PARTES_BASE, *(["sonidos"] if incluir_sonidos else [])]


def exportar(destino: Path, incluir_sonidos: bool = False, descripcion: str = "", progreso=None, cancelacion=None,
		ruta_datos: Path | None = None) -> Path:
	return crear.crear_copia(destino, partes_exportar(incluir_sonidos), "perfil", "excluidos", None, descripcion, progreso,
		cancelacion, ruta_datos=ruta_datos)


def _texto(valor: Any) -> str:
	return ejecutables._valor_texto(valor)


def _contar(datos: Any, ruta: str) -> str:
	if datos is None:
		return _("No hay")
	if ruta in combinar.LISTAS:
		return _("{n} elementos").format(n=len(combinar.elementos_lista(datos, ruta)))
	return _("Sí")


def vista_previa(copia: CopiaAbierta, config, ruta_datos: Path | None = None) -> VistaPerfil:
	"""Lo que el perfil cambiaría aquí y lo que haría ejecutar."""
	from app.core.descripciones_config import EJECUTA

	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	partes = [p for p in copia.partes_validas if p in formato.PARTES_PERFIL]
	vista = VistaPerfil()
	for parte in ("preferencias", "teclas"):
		if parte not in partes:
			continue
		valores = restaurar.migrar_valores(copia.valores(parte), copia.manifiesto.version_esquema)
		for clave, valor in sorted(valores.items()):
			if formato.parte_de_clave(clave) != parte or clave in EJECUTA:
				continue
			actual = config.obtener(clave, None)
			if combinar.iguales(actual, valor):
				continue
			vista.filas.append(FilaPerfil(f"valor:{clave}", etiqueta_clave(clave), _texto(actual), _texto(valor)))
	grupos: dict[str, list[str]] = {}
	for parte in partes:
		for archivo in copia.archivos_datos(parte):
			ruta = archivo.ruta
			if ruta in combinar.LISTAS_EJECUTABLES:
				continue
			local = ruta_datos / ruta
			try:
				igual = local.read_bytes() == copia.leer(parte, ruta)
			except OSError:
				igual = False
			if igual:
				continue
			grupo = next((g for prefijo, g in GRUPOS.items() if ruta.startswith(prefijo)), None)
			if grupo is not None:
				grupos.setdefault(grupo[0], []).append(ruta)
				continue
			nombre = _(NOMBRES_ARCHIVOS[ruta]) if ruta in NOMBRES_ARCHIVOS else (
				_("Perfil propio {n}").format(n=Path(ruta).stem) if ruta.startswith("config/perfiles/") else ruta)
			actual = restaurar._json(restaurar._leer(local)) if local.is_file() else None
			id_fila = f"archivo:{ruta}"
			vista.filas.append(FilaPerfil(id_fila, nombre, _contar(actual, ruta),
				_contar(copia.leer_json(parte, ruta), ruta) + " " + _("(se combina)")))
			vista.rutas[id_fila] = [ruta]
	for id_grupo, nombre in GRUPOS.values():
		rutas = grupos.get(id_grupo)
		if rutas:
			vista.filas.append(FilaPerfil(id_grupo, _(nombre), "", _("{n} archivos nuevos o distintos").format(n=len(rutas))))
			vista.rutas[id_grupo] = rutas
	vista.ejecutables = ejecutables.analizar(copia, partes, ruta_datos).elementos
	return vista


def importar(ruta: Path, config, filas_marcadas: Sequence[str], ejecutables_marcados: Sequence[str],
		ruta_datos: Path | None = None) -> ResultadoRestauracion:
	"""Aplica lo marcado del perfil (siempre combinando) y avisa con ``al_restaurar``."""
	from app.services import eventos

	ruta_datos = Path(ruta_datos) if ruta_datos else paths.ruta_datos()
	filas_marcadas, ejecutables_marcados = set(filas_marcadas), set(ejecutables_marcados)
	with CopiaAbierta(ruta) as copia:
		vista = vista_previa(copia, config, ruta_datos)
		ids_ejecutables = {e.id for e in vista.ejecutables}
		excluidos_archivos = {r for id_fila, rutas in vista.rutas.items() if id_fila not in filas_marcadas for r in rutas}
		# Los archivos sin fila (iguales a los de aquí) no hace falta tocarlos.
		con_fila = {r for rutas in vista.rutas.values() for r in rutas}
		for parte in copia.partes_validas:
			for archivo in copia.archivos_datos(parte):
				if archivo.ruta not in con_fila and archivo.ruta not in combinar.LISTAS_EJECUTABLES:
					excluidos_archivos.add(archivo.ruta)
		permitidas = {f.id[len("valor:"):] for f in vista.filas if f.id.startswith("valor:") and f.id in filas_marcadas}
		permitidas |= {i[len("clave:"):] for i in ejecutables_marcados & ids_ejecutables if i.startswith("clave:")}
		plan = restaurar.PlanRestauracion(partes=[p for p in copia.partes_validas if p in formato.PARTES_PERFIL],
			modo="combinar", ejecutables=ids_ejecutables, marcados=ejecutables_marcados & ids_ejecutables,
			archivos_excluidos=excluidos_archivos, ofrecer_complementos=False)
		resultado, aplicado = restaurar.restaurar_con_previa(copia, plan, None, ruta_datos, config=config,
			claves_permitidas=permitidas)
	if aplicado is None:
		return resultado
	momento = [p for p in aplicado.partes if formato.PARTES[p].aplicacion == formato.MOMENTO]
	if momento:
		eventos.bus().emitir(eventos.AL_RESTAURAR, partes=momento)
	quitados = len(ids_ejecutables - ejecutables_marcados)
	texto = _("Perfil importado.")
	if quitados:
		texto += " " + _("No se aplicaron {n} órdenes que no marcó.").format(n=quitados)
	for aviso in aplicado.avisos:
		texto += " " + aviso
	return ResultadoRestauracion(True, texto, aplicado.partes, resultado.copia_previa)
