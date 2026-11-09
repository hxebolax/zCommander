# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Descripción de una imagen con un servicio que configura la persona (diseño 2.0, 11.11). Sin wx.

Dos formas, las dos con ``zc.red`` (tiempos de espera, User-Agent propio,
errores en español): un servidor compatible con Ollama (``POST /api/generate``
con la imagen en base64) o una API compatible con OpenAI
(``POST /chat/completions`` con la imagen como ``data:`` URL y la clave en los
secretos del complemento). Nunca es automática: solo la pide la orden
«Describir la imagen», y la primera vez se avisa de adónde va la imagen.
"""

from __future__ import annotations

import base64
import builtins
import json
from typing import Any
from urllib.parse import urlsplit


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorDescripcion(Exception):
	"""Mensaje en español que se puede enseñar tal cual."""


IDIOMAS = {"es": "español", "en": "inglés", "ca": "catalán", "gl": "gallego", "eu": "euskera", "pt": "portugués", "fr": "francés",
	"it": "italiano", "de": "alemán"}


def instrucciones(idioma: str, longitud: str) -> str:
	"""El texto que se manda con la imagen."""
	lengua = IDIOMAS.get((idioma or "es").lower()[:2], idioma or "español")
	if longitud == "detallada":
		return (f"Describe esta imagen en {lengua} para una persona ciega, con detalle: qué se ve, personas, objetos, colores, "
			"disposición, ambiente y cualquier texto que aparezca, copiado tal cual. No inventes lo que no se ve.")
	return (f"Describe esta imagen en {lengua} para una persona ciega, en dos o tres frases: lo principal que se ve y el texto "
		"importante que aparezca. No inventes lo que no se ve.")


def servidor(url: str) -> str:
	"""El nombre del servidor de una dirección, para el aviso de privacidad."""
	partes = urlsplit(url)
	return partes.netloc or url


def _base(url: str) -> str:
	url = (url or "").strip().rstrip("/")
	if not url.startswith(("http://", "https://")):
		raise ErrorDescripcion(_("La dirección del servicio tiene que empezar por http:// o https://"))
	return url


def peticion_ollama(url: str, modelo: str, imagen: bytes, idioma: str, longitud: str) -> tuple[str, dict[str, Any]]:
	"""(dirección, cuerpo JSON) para un servidor compatible con Ollama."""
	if not modelo:
		raise ErrorDescripcion(_("Falta el modelo: escriba en Preferencias el nombre de un modelo de visión, como llava o gemma3"))
	return _base(url) + "/api/generate", {
		"model": modelo, "prompt": instrucciones(idioma, longitud), "images": [base64.b64encode(imagen).decode("ascii")],
		"stream": False,
	}


def peticion_openai(url: str, modelo: str, imagen: bytes, idioma: str, longitud: str) -> tuple[str, dict[str, Any]]:
	"""(dirección, cuerpo JSON) para una API compatible con OpenAI (``/chat/completions``)."""
	if not modelo:
		raise ErrorDescripcion(_("Falta el modelo: escriba en Preferencias el nombre de un modelo con visión"))
	base = _base(url)
	if not base.endswith("/chat/completions"):
		base += "/chat/completions"
	datos = "data:image/jpeg;base64," + base64.b64encode(imagen).decode("ascii")
	return base, {
		"model": modelo,
		"messages": [{"role": "user", "content": [
			{"type": "text", "text": instrucciones(idioma, longitud)},
			{"type": "image_url", "image_url": {"url": datos}},
		]}],
		"max_tokens": 800 if longitud == "detallada" else 300,
	}


def leer_respuesta(servicio: str, cuerpo: bytes | str) -> str:
	"""El texto de la descripción de la respuesta del servicio."""
	try:
		datos = json.loads(cuerpo)
	except ValueError as error:
		raise ErrorDescripcion(_("El servicio no devolvió una respuesta que se entienda")) from error
	if isinstance(datos, dict) and datos.get("error"):
		error = datos["error"]
		mensaje = error.get("message") if isinstance(error, dict) else str(error)
		raise ErrorDescripcion(_("El servicio respondió con un error: {e}").format(e=mensaje))
	if servicio == "ollama":
		texto = str(datos.get("response", "")).strip() if isinstance(datos, dict) else ""
	else:
		try:
			contenido = datos["choices"][0]["message"]["content"]
		except (KeyError, IndexError, TypeError) as error:
			raise ErrorDescripcion(_("El servicio no devolvió ninguna descripción")) from error
		if isinstance(contenido, list):
			contenido = " ".join(str(p.get("text", "")) for p in contenido if isinstance(p, dict))
		texto = str(contenido).strip()
	if not texto:
		raise ErrorDescripcion(_("El servicio no devolvió ninguna descripción"))
	return texto
