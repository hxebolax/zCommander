# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Anuncios de zCommander al lector de pantalla, con niveles de detalle.

Niveles (de más a menos importante):

- ``esencial``: errores, preguntas pendientes y fin de operaciones. Siempre
  que los anuncios estén activos. Nunca interrumpen (no se pierden por la
  coalescencia de la cola de voz).
- ``resultado``: respuesta a algo que la persona acaba de pedir y que no tiene
  respuesta nativa (recuento al marcar por patrón, «Pestaña 2 de 3», teclas de
  consulta). Siempre que los anuncios estén activos.
- ``normal``: cambio de carpeta, marcas al moverse, alcance de una orden.
  Con detalle «normal» o «detallado».
- ``detalle``: consejos y datos extra (número de elementos). Solo «detallado».

Cada anuncio puede tener una forma completa: el historial guarda las dos y
«Repetir el último anuncio» pulsado dos veces dice la completa.

Nunca se anuncia lo que el lector ya lee solo al mover el foco (nombre de la
fila, «seleccionado», nombre de la lista).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from app.ui.accesibilidad import voz

ESENCIAL, RESULTADO, NORMAL, DETALLE = "esencial", "resultado", "normal", "detalle"
_ORDEN = {ESENCIAL: 0, RESULTADO: 0, NORMAL: 1, DETALLE: 2}
_UMBRAL = {"breve": 0, "normal": 1, "detallado": 2}


@dataclass(frozen=True)
class Anuncio:
	momento: float
	texto: str
	completo: str
	nivel: str


_estado = {"activos": True, "detalle": "normal", "sustituir": False}
_historial: deque[Anuncio] = deque(maxlen=500)
_ultima_repeticion = [0.0]


def configurar(activos: bool | None = None, detalle: str | None = None, sustituir: bool | None = None) -> None:
	"""Aplica ``accesibilidad.anuncios``, ``accesibilidad.detalle`` y ``sonidos.sustituir_anuncios`` (2.0, 4.5)."""
	if activos is not None:
		_estado["activos"] = bool(activos)
	if detalle is not None:
		_estado["detalle"] = detalle if detalle in _UMBRAL else "normal"
	if sustituir is not None:
		_estado["sustituir"] = bool(sustituir)


def se_dice(nivel: str) -> bool:
	"""``True`` si un anuncio de ese nivel se diría con las preferencias actuales."""
	if nivel == ESENCIAL:
		# Errores, decisiones pendientes y fin de operaciones se dicen siempre.
		return True
	if not _estado["activos"]:
		return False
	return _ORDEN.get(nivel, 1) <= _UMBRAL.get(_estado["detalle"], 1)


def _sonar(sonido: str) -> bool:
	"""Pide el sonido; ``True`` solo si sustituye al anuncio (preferencia, evento sustituible y aceptado)."""
	from app.services.sonidos import catalogo, servicio

	evento = catalogo.evento(sonido)
	sustituible = bool(evento and evento.sustituye_anuncio)
	aceptado = servicio.sonar(sonido, sustituye=sustituible)
	return bool(_estado["sustituir"] and sustituible and aceptado)


def anunciar(texto: str, nivel: str = NORMAL, completo: str = "", interrumpir: bool | None = None, sonido: str = "") -> None:
	"""Envía ``texto`` al lector si el nivel lo permite. Siempre queda en el historial.

	:param completo: versión larga (para «repetir dos veces»); vacía = la misma.
	:param interrumpir: por defecto, los esenciales no interrumpen y los demás sí
		(un cambio de carpeta reemplaza al anterior si se navega deprisa).
	:param sonido: evento de sonido que acompaña al anuncio (2.0, 4.3). Si
		``sonidos.sustituir_anuncios`` está activo, el evento es sustituible y el
		sonido se aceptó, el texto no se dice (pero queda en el historial). Los
		esenciales nunca se omiten.
	"""
	texto = (texto or "").strip()
	sustituido = _sonar(sonido) if sonido else False
	if not texto:
		return
	_historial.append(Anuncio(time.time(), texto, completo or texto, nivel))
	if not se_dice(nivel) or (sustituido and nivel != ESENCIAL):
		return
	if interrumpir is None:
		interrumpir = nivel not in (ESENCIAL,)
	# Los esenciales van por su propio canal, que no se puede desactivar.
	canal = voz.NAVEGACION if nivel in (RESULTADO, NORMAL, DETALLE) else ESENCIAL
	voz.hablar(texto, interrumpir=interrumpir, canal=canal, forzar=nivel == ESENCIAL)


def repetir_ultimo() -> None:
	"""Repite el último anuncio; si se pide otra vez en menos de 1,5 s, dice la forma completa."""
	if not _historial:
		voz.hablar("No hay anuncios todavía", canal=voz.NAVEGACION)
		return
	ultimo = _historial[-1]
	ahora = time.monotonic()
	completo = ahora - _ultima_repeticion[0] < 1.5
	_ultima_repeticion[0] = ahora
	voz.hablar(ultimo.completo if completo else ultimo.texto, interrumpir=True, canal=voz.NAVEGACION)


def historial() -> list[Anuncio]:
	return list(_historial)
