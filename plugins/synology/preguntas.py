# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Preguntas de la conexión con el ``Decisor`` de zCommander (sin wx).

Es la versión de respaldo: con la ventana de zCommander abierta, el complemento
usa los diálogos propios de ``ui/dialogos.py`` (con la casilla «Recordar este
equipo» junto al código y la huella leída por grupos). Los textos son los
mismos en los dos casos y viven aquí.
"""

from __future__ import annotations

from typing import Any

from app.plugins import api

from .cliente import huella_legible

_, _n = api.traduccion("zc_synology")

OPCIONES_HUELLA = ("recordar", "sesion", "cancelar")


def texto_huella(servidor: Any, huella: str, anterior: str) -> str:
	if anterior:
		return _("Atención: el certificado del NAS {n} ({h}:{p}) ha cambiado.\n\nHuella anterior:\n{a}\n\nHuella nueva:\n{b}\n\n"
			"Si no lo ha renovado usted, alguien podría estar interceptando la conexión. Acéptelo solo si sabe por qué ha cambiado.").format(
			n=servidor.nombre, h=servidor.host, p=servidor.puerto, a=huella_legible(anterior), b=huella_legible(huella))
	return _("El NAS {n} ({h}:{p}) presenta un certificado que zCommander no conoce (los NAS traen uno autofirmado de fábrica).\n\n"
		"Huella SHA-256:\n{b}\n\nCompruebe que coincide con la de DSM, en Panel de control, Seguridad, Certificado, antes de aceptarlo.").format(
		n=servidor.nombre, h=servidor.host, p=servidor.puerto, b=huella_legible(huella))


class PreguntasDecisor:
	"""``Preguntas`` sobre el ``Decisor``: bloquea el hilo de trabajo mientras la persona contesta en la interfaz."""

	def __init__(self, decisor: Any) -> None:
		self._decisor = decisor

	def credenciales(self, servidor: Any, motivo: str) -> tuple[str, str, bool] | None:
		return self._decisor.pedir_credenciales(_("Conectar con {n}").format(n=servidor.nombre), motivo, servidor.usuario)

	def codigo(self, servidor: Any, mensaje: str) -> tuple[str, bool] | None:
		codigo = self._decisor.pedir_texto(_("Verificación en dos pasos"), mensaje + "\n" + _("Código de verificación:"))
		return (codigo, False) if codigo else None

	def huella(self, servidor: Any, huella: str, anterior: str) -> str:
		opciones = [_("Aceptar y &recordar"), _("Aceptar &solo esta vez"), _("&Cancelar")]
		eleccion = self._decisor.elegir(_("Certificado del NAS"), texto_huella(servidor, huella, anterior), opciones, 2, 2)
		return OPCIONES_HUELLA[eleccion] if 0 <= int(eleccion) < len(OPCIONES_HUELLA) else "cancelar"

	def contrasena_dsm(self, servidor: Any, motivo: str) -> str | None:
		return self._decisor.pedir_texto(_("Confirmar la contraseña"), motivo, oculto=True)
