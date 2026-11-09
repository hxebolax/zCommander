# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Traducción al español de las preguntas habituales de rclone en un alta (sin wx).

rclone pregunta en inglés con un nombre estable (``Option.Name``, por ejemplo
``config_type`` o ``config_2fa``). Aquí se traduce el texto y, en las preguntas
con opciones, la explicación de cada opción por su valor. Si una pregunta no
tiene traducción, se muestra el texto de rclone como hasta ahora. Algunas llevan
datos variables (la unidad encontrada, el teléfono al que se envía el código):
se sacan del texto original con una expresión regular.
"""

from __future__ import annotations

import re
from typing import Any

from app.plugins import api

_ = api.traduccion("zc_nubes")[0]

#: Explicación de cada opción por su valor (``config_type`` la comparten OneDrive y Jottacloud).
_OPCIONES = {
	"config_type": {
		"onedrive": "OneDrive personal o de empresa",
		"sharepoint": "Sitio raíz de SharePoint",
		"url": "Sitio de SharePoint por su nombre o su dirección (por ejemplo misitio o https://contoso.sharepoint.com/sites/misitio)",
		"search": "Buscar un sitio de SharePoint",
		"driveid": "Escribir el identificador de la unidad (avanzado)",
		"siteid": "Escribir el identificador del sitio (avanzado)",
		"path": "Ruta de SharePoint dentro del servidor (avanzado), por ejemplo /teams/hr",
		"standard": "Estándar: pegar un código personal de inicio de sesión que se crea en la web del servicio",
		"traditional": "Tradicional: iniciar sesión en el navegador (recomendada)",
		"legacy": "Antigua: usuario y contraseña (ya no la admite ningún servicio conocido)",
	},
	"config_is_local": {"true": "Sí", "false": "No"},
}

_TIPOS_UNIDAD = {"personal": "personal", "business": "de empresa", "documentLibrary": "biblioteca de documentos"}


def _texto_fijo(nombre: str, original: str) -> str:
	if nombre == "config_type":
		if "Type of authentication" in original:
			return _("Forma de iniciar sesión.")
		return _("Tipo de conexión: qué parte de OneDrive o SharePoint quiere usar.")
	if nombre == "config_driveid":
		return _("Elija la unidad que quiere usar.")
	if nombre == "config_drive_ok":
		encontrada = re.search(r'Found drive "(?P<n>[^"]*)" of type "(?P<t>[^"]*)"\s*URL:\s*(?P<u>\S*)', original)
		if encontrada:
			tipo = _TIPOS_UNIDAD.get(encontrada["t"], encontrada["t"])
			texto = _("Se ha encontrado la unidad «{n}», de tipo {t}.").format(n=encontrada["n"], t=tipo)
			if encontrada["u"]:
				texto += " " + _("Dirección: {u}.").format(u=encontrada["u"])
			return texto + " " + _("¿Es la unidad correcta?")
		return _("¿Es la unidad correcta?")
	if nombre == "config_change_team_drive":
		actual = re.search(r'Change current Shared Drive \(Team Drive\) ID "([^"]*)"', original)
		if actual:
			return _("¿Cambiar la unidad compartida que usa ahora la cuenta ({i})?").format(i=actual.group(1))
		return _("¿Configurar la cuenta como una unidad compartida de Google (antes unidad de equipo)? Elija No para usar Mi unidad.")
	if nombre == "config_team_drive":
		return _("Elija la unidad compartida de Google que quiere usar.")
	if nombre == "config_2fa":
		texto = _("Verificación en dos pasos: escriba el código de su aplicación de autenticación.")
		if "sms" in original.casefold():
			texto += " " + _("Si prefiere recibirlo en un mensaje de texto, escriba sms.")
		return texto
	if nombre == "config_2fa_sms":
		telefono = re.search(r"sent to (.+?)\s*$", original.strip())
		if telefono:
			return _("Escriba el código de verificación que se ha enviado a {t}.").format(t=telefono.group(1))
		return _("Escriba el código de verificación que ha recibido en un mensaje de texto.")
	if nombre == "config_2fa_phone":
		return _("Elija el teléfono al que se enviará el código de verificación por mensaje de texto.")
	if nombre == "config_shared_client_id":
		servicio = re.search(r"shared (.+?) client_id", original)
		return _("El identificador compartido de rclone para {s} se retira y dejará de funcionar durante 2026. Si sigue con él, la "
			"cuenta funcionará mientras Google lo permita y después habrá que volver a autorizarla con un identificador propio. "
			"¿Seguir con el identificador compartido?").format(s=servicio.group(1) if servicio else _("este servicio"))
	if nombre == "config_is_local":
		return _("¿Autorizar con el navegador de este equipo? Elija No solo si este equipo no tiene navegador: entonces tendrá que "
			"autorizar desde otro equipo con rclone.")
	if nombre == "config_non_standard":
		return _("¿Usar un dispositivo o un punto de montaje distinto del habitual? Elija No para ver el archivo de la aplicación "
			"oficial; Sí, para la sección de sincronización o de copias de seguridad.")
	if nombre == "config_traditional":
		return _("Servicio al que conectar (Jottacloud o una de sus marcas blancas).")
	if nombre == "config_refresh_token":
		return _("La cuenta ya tiene una autorización. ¿Sustituirla por una nueva?")
	return ""


def traducir(nombre: str, original: str, ejemplos: list[tuple[str, str]]) -> tuple[str, list[tuple[str, str]], bool]:
	"""(texto, ejemplos, traducida): la pregunta en español si se conoce; si no, la de rclone tal cual."""
	texto = _texto_fijo(nombre, original or "")
	opciones = _OPCIONES.get(nombre, {})
	traducidos = [(valor, _(opciones[valor]) if valor in opciones else ayuda) for valor, ayuda in ejemplos]
	if not texto:
		return original or nombre, traducidos, False
	return texto, traducidos, True


def traducir_paso(paso: Any) -> tuple[str, list[tuple[str, str]], bool]:
	"""Atajo para un ``servicio.Paso``."""
	return traducir(paso.nombre, paso.ayuda, paso.ejemplos)
