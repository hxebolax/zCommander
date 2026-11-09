# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motores de OCR: el de Windows por pywinrt (vendorizado) o por un guion de PowerShell (sin wx).

- ``MotorWinrt``: ``Windows.Media.Ocr`` y ``Windows.Data.Pdf`` con pywinrt
  (``lib/winrt``, MIT), en el mismo proceso.
- ``MotorPowershell``: ``recursos/ocr.ps1`` con Windows PowerShell 5.1, las mismas
  API de WinRT y la respuesta en una línea JSON (``analizar_salida``).

``elegir`` prueba el preferido con una imagen de un píxel y, si falla, el otro.
Todo se llama en hilos de trabajo.
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import struct
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.plugins import api

log = logging.getLogger("zcplugins.zc.ocr")

IMAGENES = ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "jxr", "ico", "heic", "webp")
TIEMPO_POR_PAGINA_S = 60

COMO_INSTALAR = ("Para instalar más idiomas de reconocimiento de texto: Configuración de Windows, Hora e idioma, Idioma y región, "
	"Agregar un idioma; elija el idioma y marque «Reconocimiento óptico de caracteres» o «Escritura a mano y OCR».")


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorOCR(api.ErrorArchivos):
	"""Error del reconocimiento con el mensaje en español; ``codigo``: «sin_idiomas», «idioma», «sin_winrt», «error»."""

	def __init__(self, mensaje: str, ruta: str = "", codigo: str = "error") -> None:
		super().__init__(mensaje, ruta)
		self.codigo = codigo


def mensaje_sin_idiomas() -> str:
	return _("Windows no tiene ningún idioma con reconocimiento de texto instalado.") + " " + _(COMO_INSTALAR)


@dataclass
class Resultado:
	"""Líneas reconocidas por página (una sola página en una imagen) y el idioma usado."""

	paginas: list[list[str]] = field(default_factory=list)
	idioma: str = ""


def analizar_salida(texto: str) -> dict[str, Any]:
	"""La línea JSON de ``ocr.ps1`` (la última que lo sea). ``ErrorOCR`` si es un error o no se entiende."""
	for linea in reversed([l.strip() for l in texto.splitlines() if l.strip()]):
		if not linea.startswith("{"):
			continue
		try:
			datos = json.loads(linea)
		except ValueError:
			continue
		if datos.get("ok"):
			return datos
		codigo = str(datos.get("codigo", "error"))
		if codigo == "sin_idiomas":
			raise ErrorOCR(mensaje_sin_idiomas(), codigo=codigo)
		if codigo == "idioma":
			raise ErrorOCR(_("El idioma elegido no tiene reconocimiento de texto instalado.") + " " + _(COMO_INSTALAR), codigo=codigo)
		raise ErrorOCR(_("El motor OCR de Windows falló: {e}").format(e=datos.get("error", "")), codigo=codigo)
	raise ErrorOCR(_("El motor OCR de Windows no respondió como se esperaba"))


def resultado_de(datos: dict[str, Any]) -> Resultado:
	paginas = [[str(linea) for linea in pagina] for pagina in datos.get("paginas", [])]
	return Resultado(paginas, str(datos.get("idioma", "")))


def bmp_un_pixel() -> bytes:
	"""Una imagen BMP blanca de 1×1 (para probar el motor sin depender de nada)."""
	cabecera_dib = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 2835, 2835, 0, 0)
	pixeles = b"\xff\xff\xff\x00"
	cabecera = struct.pack("<2sIHHI", b"BM", 14 + 40 + len(pixeles), 0, 0, 14 + 40)
	return cabecera + cabecera_dib + pixeles


# ── pywinrt ──────────────────────────────────────────────────────────────────


class MotorWinrt:
	nombre = "winrt"

	def __init__(self) -> None:
		import asyncio  # noqa: F401 - comprobado al crear: sin él no hay motor

		from winrt.windows.media.ocr import OcrEngine  # resuelto por el buscador de lib/ del complemento

		self._ocr = OcrEngine
		self._candado = threading.Lock()

	def idiomas(self) -> list[tuple[str, str]]:
		return [(l.language_tag, l.display_name) for l in self._ocr.available_recognizer_languages]

	def _motor(self, idioma: str) -> Any:
		if not list(self._ocr.available_recognizer_languages):
			raise ErrorOCR(mensaje_sin_idiomas(), codigo="sin_idiomas")
		if idioma:
			from winrt.windows.globalization import Language

			try:
				motor = self._ocr.try_create_from_language(Language(idioma))
			except Exception:  # noqa: BLE001 - etiqueta de idioma mal escrita
				motor = None
			if motor is None:
				raise ErrorOCR(_("El idioma {i} no tiene reconocimiento de texto instalado.").format(i=idioma) + " " + _(COMO_INSTALAR),
					codigo="idioma")
			return motor
		motor = self._ocr.try_create_from_user_profile_languages()
		return motor or self._ocr.try_create_from_language(list(self._ocr.available_recognizer_languages)[0])

	def reconocer(self, ruta: str, idioma: str = "", escala: float = 2.0, cancelacion: Any = None) -> Resultado:
		import asyncio

		try:
			return asyncio.run(self._reconocer(ruta, idioma, escala, cancelacion))
		except (api.ErrorArchivos, api.Cancelado):
			raise
		except Exception as error:  # noqa: BLE001 - errores de WinRT (OSError con HRESULT)
			log.warning("Falló el OCR con pywinrt de %s", ruta, exc_info=True)
			raise ErrorOCR(_("El motor OCR de Windows no pudo leer {n}: {e}").format(n=os.path.basename(ruta), e=error), ruta) from error

	async def _reconocer(self, ruta: str, idioma: str, escala: float, cancelacion: Any) -> Resultado:
		from winrt.windows.graphics.imaging import BitmapDecoder
		from winrt.windows.storage import FileAccessMode, StorageFile

		motor = self._motor(idioma)
		archivo = await StorageFile.get_file_from_path_async(os.path.abspath(ruta))
		paginas: list[list[str]] = []
		if ruta.lower().endswith(".pdf"):
			from winrt.windows.data.pdf import PdfDocument, PdfPageRenderOptions
			from winrt.windows.storage.streams import InMemoryRandomAccessStream

			documento = await PdfDocument.load_from_file_async(archivo)
			for numero in range(documento.page_count):
				api.comprobar(cancelacion)
				pagina = documento.get_page(numero)
				flujo = InMemoryRandomAccessStream()
				opciones = PdfPageRenderOptions()
				opciones.destination_width = int(min(self._ocr.max_image_dimension, pagina.size.width * escala))
				await pagina.render_to_stream_async(flujo, opciones)
				decodificador = await BitmapDecoder.create_async(flujo)
				mapa = await decodificador.get_software_bitmap_async()
				resultado = await motor.recognize_async(mapa)
				paginas.append([linea.text for linea in resultado.lines])
		else:
			flujo = await archivo.open_async(FileAccessMode.READ)
			decodificador = await BitmapDecoder.create_async(flujo)
			mapa = await decodificador.get_software_bitmap_async()
			resultado = await motor.recognize_async(mapa)
			paginas.append([linea.text for linea in resultado.lines])
		return Resultado(paginas, motor.recognizer_language.language_tag)


# ── PowerShell ───────────────────────────────────────────────────────────────


class MotorPowershell:
	"""``ocr.ps1`` lanzado sin consola con ``ejecutar(argumentos, tiempo_s, cancelacion) -> ResultadoPrograma``."""

	nombre = "powershell"

	def __init__(self, guion: Path, ejecutar: Callable[..., Any]) -> None:
		self.guion = guion
		self._ejecutar = ejecutar

	def _llamar(self, extra: list[str], tiempo_s: float, cancelacion: Any = None) -> dict[str, Any]:
		sistema = os.environ.get("SystemRoot", r"C:\Windows")
		powershell = os.path.join(sistema, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
		argumentos = [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(self.guion), *extra]
		resultado = self._ejecutar(argumentos, tiempo_s=tiempo_s, cancelacion=cancelacion)
		if getattr(resultado, "cancelado", False):
			raise api.Cancelado()
		return analizar_salida(resultado.salida.decode("utf-8-sig", errors="replace"))

	def idiomas(self) -> list[tuple[str, str]]:
		datos = self._llamar(["-Idiomas"], 60)
		return [(str(i.get("etiqueta", "")), str(i.get("nombre", ""))) for i in datos.get("idiomas", [])]

	def reconocer(self, ruta: str, idioma: str = "", escala: float = 2.0, cancelacion: Any = None) -> Resultado:
		extra = ["-Entrada", os.path.abspath(ruta), "-Escala", f"{escala:.2f}"]
		if idioma:
			extra += ["-Idioma", idioma]
		paginas = 1
		if ruta.lower().endswith(".pdf"):
			paginas = 50
		return resultado_de(self._llamar(extra, TIEMPO_POR_PAGINA_S * paginas, cancelacion))


# ── Elección ─────────────────────────────────────────────────────────────────


def probar(motor: Any, carpeta: Path) -> bool:
	"""Reconoce una imagen de un píxel: verdadero si el motor funciona (aunque no haya texto)."""
	ruta = carpeta / "prueba-1px.bmp"
	try:
		carpeta.mkdir(parents=True, exist_ok=True)
		ruta.write_bytes(bmp_un_pixel())
		motor.reconocer(str(ruta))
		return True
	except ErrorOCR as error:
		# Sin idiomas el motor funciona: el mensaje se dirá al reconocer.
		return error.codigo == "sin_idiomas"
	except Exception:  # noqa: BLE001 - cualquier fallo descarta este motor
		log.info("El motor OCR %s no funciona aquí", getattr(motor, "nombre", motor), exc_info=True)
		return False
	finally:
		try:
			ruta.unlink(missing_ok=True)
		except OSError:
			log.debug("No se pudo borrar la imagen de prueba", exc_info=True)


def elegir(preferencia: str, carpeta: Path, crear_powershell: Callable[[], Any]) -> Any:
	"""El primer motor que funciona según ``preferencia`` (``automatico``, ``winrt`` o ``powershell``)."""
	orden = ["powershell", "winrt"] if preferencia == "powershell" else ["winrt", "powershell"]
	for nombre in orden:
		try:
			motor = MotorWinrt() if nombre == "winrt" else crear_powershell()
		except Exception:  # noqa: BLE001 - pywinrt no carga, o falta el permiso de ejecutar programas
			log.info("No se pudo crear el motor OCR %s", nombre, exc_info=True)
			continue
		if probar(motor, carpeta):
			log.info("Motor OCR elegido: %s", nombre)
			return motor
	raise ErrorOCR(_("No se pudo usar el motor OCR de Windows (hace falta Windows 10 o 11)"), codigo="sin_winrt")
