# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Genera data/docs/licencias/ con el texto de la licencia de cada componente distribuido (diseño 2.0, 2.2).

Uso (desde la raíz, con el entorno virtual del proyecto activo)::

	python tools/generar_licencias.py              # escribe lo que haya cambiado
	python tools/generar_licencias.py --comprobar  # 1 si algo no está al día

Crea una carpeta por componente (``COMPONENTES``) con los textos que hay que
acompañar, tomados de donde los publica cada uno: los ``dist-info`` del entorno
virtual, la instalación de Python, ``data/bin`` (paquetes oficiales y de MSYS2),
las carpetas ``lib/`` de los complementos de serie y algunos textos fijos de este
archivo (avisos sin texto propio en el paquete). Después escribe
``LEEME-LICENCIAS.md`` (qué lleva zCommander, con qué licencia y dónde está su
texto) y ``OFERTA-DE-FUENTES.md`` (2.4).

La tabla ``COMPONENTES`` es la única fuente: la usan también
``tools/comprobar_licencias.py`` (qué carpeta, qué módulos de la compilación y qué
ids de ``linea_base.json`` corresponden a cada componente) y las pruebas.
"""

from __future__ import annotations

import argparse
import html.parser
import importlib.metadata
import json
import platform
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LICENCIAS = RAIZ / "data" / "docs" / "licencias"
LEEME = "LEEME-LICENCIAS.md"
OFERTA = "OFERTA-DE-FUENTES.md"
URL_PROYECTO = "https://xebolax.synology.me/zCommander/"
URL_FUENTES_TERCEROS = "https://xebolax.synology.me/zCommander/fuentes/"
COMPILACION = RAIZ / "build" / "ZCommander"

# Grupos, en el orden en que salen en LEEME-LICENCIAS.md.
GRUPOS = {
	"propio": "zCommander",
	"python": "Componentes de Python dentro del proceso",
	"bin": "Programas y bibliotecas de data/bin",
	"complementos": "Bibliotecas incluidas en los complementos de serie",
	"otros": "Sonidos y runtime de Visual C++",
}


@dataclass(frozen=True)
class Componente:
	"""Un componente distribuido y de dónde sale el texto de su licencia.

	``archivos``: pares (origen, destino dentro de la carpeta del componente). El
	origen es ``repo:<ruta>`` (desde la raíz; una carpeta se copia entera),
	``dist:<distribución>:<ruta en el dist-info>``, ``site:<ruta en site-packages>``,
	``python:<ruta en la instalación de Python>``, ``html:<ídem>`` (se guarda como
	texto), ``texto:<clave de TEXTOS>`` o ``build:<ruta en build/ZCommander>``
	(solo existe tras compilar: si falta, se conserva la copia que ya hay).
	"""

	carpeta: str
	nombre: str
	version: str | Callable[[], str]
	licencia: str
	obligacion: str
	uso: str
	grupo: str
	archivos: tuple[tuple[str, str], ...]
	pypi: tuple[str, ...] = ()
	ids: tuple[str, ...] = ()
	modulos: tuple[str, ...] = ()
	fuentes: str = ""
	notas: tuple[str, ...] = field(default=())

	def version_texto(self) -> str:
		return self.version() if callable(self.version) else self.version


def _version_dist(nombre: str) -> Callable[[], str]:
	def leer() -> str:
		try:
			return importlib.metadata.version(nombre)
		except importlib.metadata.PackageNotFoundError:
			return "no instalada"

	return leer


def _version_base(identificador: str) -> Callable[[], str]:
	def leer() -> str:
		try:
			datos = json.loads((RAIZ / "data" / "bin" / "linea_base.json").read_text(encoding="utf-8"))
		except (OSError, ValueError):
			return "desconocida"
		ficha = next((c for c in datos.get("componentes", []) if c.get("id") == identificador), {})
		return str(ficha.get("version", "desconocida"))

	return leer


def _version_app() -> str:
	texto = (RAIZ / "app" / "core" / "version.py").read_text(encoding="utf-8")
	encontrada = re.search(r"APP_VERSION\s*=\s*[\"']([^\"']+)[\"']", texto)
	return encontrada.group(1) if encontrada else "0.0.0"


LGPL_21 = "dist:paramiko:licenses/LICENSE"

TEXTOS = {
	"lz4": """LZ4 Library
Copyright (c) 2011-2020, Yann Collet
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
""",
	"nvda": """NVDA Controller Client (nvdaControllerClient64.dll)
Copyright (C) NV Access Limited y colaboradores de NVDA.

Biblioteca que usa accessible_output2 para hablar con el lector de pantalla
NVDA. Se distribuye sin modificar, como la publica accessible_output2, con la
GNU Lesser General Public License, versión 2.1 (texto en LGPL-2.1.txt).

Código fuente: https://github.com/nvaccess/nvda (carpeta nvdaHelper/client).
zCommander ofrece además una copia de las fuentes durante tres años (véase
OFERTA-DE-FUENTES.md).

zCommander NO distribuye las demás DLL que trae el paquete accessible_output2
(SAAPI32.dll, dolapi.dll, PCTKUSR.dll, PCTKUSR64.dll, ZDSRAPI.dll y
ZDSRAPI_x64.dll, de licencia privativa o sin aclarar) ni nvdaControllerClient32.dll.
""",
	"vc": """Runtime de Microsoft Visual C++ 2015-2022

Los archivos vcruntime140*.dll, msvcp140*.dll, concrt140.dll, vcamp140.dll,
vccorlib140.dll y vcomp140.dll que hay junto a ZCommander.exe son el «código
distribuible» del runtime de Visual C++ de Microsoft. Los incluye cx_Freeze
(opción include_msvcr) para que zCommander arranque en un Windows sin el
redistribuible instalado. Se distribuyen sin modificar.

Para la GPL-3.0 son «Bibliotecas del Sistema» (sección 1) del compilador: no
forman parte de la Fuente Correspondiente de zCommander.

Los términos de Microsoft están en LICENSE.txt (los copia cx_Freeze en
share/licenses/vc_redist de la compilación).
""",
	"python_build": """Python para Windows: componentes incorporados

La compilación de zCommander lleva el intérprete de Python (python315.dll) y
la parte de su biblioteca estándar que se usa, con las bibliotecas que la
instalación oficial de Python para Windows incorpora: OpenSSL (libcrypto-3.dll,
libssl-3.dll; Apache-2.0), libffi (libffi-8.dll; MIT), SQLite (sqlite3.dll;
dominio público), expat, zlib, bzip2, xz/liblzma, zstd, mpdecimal y HACL*.

LICENSE.txt es la licencia de Python (PSF-2.0) con las condiciones adicionales
de la versión binaria de Windows. LICENCIAS-INCORPORADAS.txt es el apartado
«Licenses and Acknowledgements for Incorporated Software» de la documentación
de esta misma versión de Python, con el aviso de cada componente incorporado.
""",
}


COMPONENTES: tuple[Componente, ...] = (
	Componente(
		"zCommander", "zCommander (núcleo, herramientas, complementos de serie, simulador DSM y complemento de NVDA)",
		_version_app, "GPL-3.0-or-later", "Dar la Fuente Correspondiente", "Todo el programa", "propio",
		(("repo:LICENSE", "GPL-3.0.txt"),), ids=("nvda",), modulos=("app",),
		fuentes="https://xebolax.synology.me/zCommander/ (archivo zCommander_v<versión>_fuentes.zip de cada versión)",
		notas=("El complemento de NVDA (`data/bin/nvda/zCommander-<versión>.nvda-addon`, id `nvda` de la línea base) "
			"es parte de zCommander y tiene su misma licencia.",),
	),
	Componente(
		"Python", "Python y su biblioteca estándar", platform.python_version, "PSF-2.0 (con componentes permisivos incorporados)",
		"Avisos", "Intérprete y biblioteca estándar (python315.dll, lib/)", "python",
		(("python:LICENSE.txt", "LICENSE.txt"), ("html:Doc/html/license.html", "LICENCIAS-INCORPORADAS.txt"),
			("texto:python_build", "LEEME.txt")),
	),
	Componente(
		"wxPython", "wxPython", _version_dist("wxPython"), "LGPL-2.0-or-later WITH WxWindows-exception-3.1",
		"Avisos y oferta de fuentes", "Interfaz gráfica (lib/wx)", "python",
		(("dist:wxPython:licenses/LICENSE.txt", "LICENSE.txt"), ("site:wx/lib/pubsub/LICENSE_BSD_Simple.txt", "pubsub-LICENSE_BSD_Simple.txt")),
		pypi=("wxPython",), modulos=("wx",), fuentes="https://pypi.org/project/wxPython/4.3.2/#files (wxpython-4.3.2.tar.gz)",
	),
	Componente(
		"pywin32", "pywin32", _version_dist("pywin32"), "PSF-2.0", "Avisos", "Integración con Windows (COM, shell, red, credenciales)",
		"python",
		(("dist:pywin32:licenses/win32/License.txt", "win32-License.txt"), ("dist:pywin32:licenses/com/License.txt", "com-License.txt"),
			("dist:pywin32:licenses/com/win32comext/mapi/src/MAPIStubLibrary/LICENSE", "MAPIStubLibrary-LICENSE.txt")),
		pypi=("pywin32",), modulos=("win32", "win32com", "win32comext", "pywintypes", "pythoncom", "pywin32_system32", "_win32sysloader"),
		notas=("Pythonwin, Scintilla, isapi y adodbapi no se distribuyen.",),
	),
	Componente(
		"comtypes", "comtypes", _version_dist("comtypes"), "MIT", "Avisos", "Interfaces COM (UI Automation, propiedades)", "python",
		(("dist:comtypes:licenses/LICENSE.txt", "LICENSE.txt"),), pypi=("comtypes",), modulos=("comtypes",),
	),
	Componente(
		"Send2Trash", "Send2Trash", _version_dist("Send2Trash"), "BSD-3-Clause", "Avisos", "Papelera de reciclaje", "python",
		(("dist:Send2Trash:licenses/LICENSE", "LICENSE.txt"),), pypi=("Send2Trash",), modulos=("send2trash",),
	),
	Componente(
		"Markdown", "Python-Markdown", _version_dist("Markdown"), "BSD-3-Clause", "Avisos", "Manual y ayuda en HTML", "python",
		(("dist:Markdown:licenses/LICENSE.md", "LICENSE.md"),), pypi=("Markdown",), modulos=("markdown",),
	),
	Componente(
		"paramiko", "paramiko", _version_dist("paramiko"), "LGPL-2.1", "Avisos y oferta de fuentes", "SFTP", "python",
		(("dist:paramiko:licenses/LICENSE", "LICENSE.txt"),), pypi=("paramiko",), modulos=("paramiko",),
		fuentes="https://pypi.org/project/paramiko/5.1.0/#files (paramiko-5.1.0.tar.gz)",
	),
	Componente(
		"invoke", "invoke (dependencia de paramiko)", _version_dist("invoke"), "BSD-2-Clause", "Avisos", "Dependencia de paramiko",
		"python", (("dist:invoke:licenses/LICENSE", "LICENSE.txt"),), pypi=("invoke",), modulos=("invoke",),
	),
	Componente(
		"cryptography", "cryptography (con OpenSSL incorporado)", _version_dist("cryptography"), "Apache-2.0 OR BSD-3-Clause",
		"Avisos", "Firmas Ed25519 de actualizaciones y complementos, copias cifradas, SFTP", "python",
		(("dist:cryptography:licenses/LICENSE", "LICENSE.txt"), ("dist:cryptography:licenses/LICENSE.APACHE", "LICENSE.APACHE.txt"),
			("dist:cryptography:licenses/LICENSE.BSD", "LICENSE.BSD.txt")),
		pypi=("cryptography",), modulos=("cryptography",),
	),
	Componente(
		"bcrypt", "bcrypt", _version_dist("bcrypt"), "Apache-2.0", "Avisos", "Dependencia de paramiko", "python",
		(("dist:bcrypt:LICENSE", "LICENSE.txt"),), pypi=("bcrypt",), modulos=("bcrypt",),
	),
	Componente(
		"PyNaCl", "PyNaCl (con libsodium)", _version_dist("PyNaCl"), "Apache-2.0 (libsodium: ISC)", "Avisos", "Dependencia de paramiko",
		"python",
		(("dist:PyNaCl:licenses/LICENSE", "LICENSE.txt"), ("dist:PyNaCl:licenses/licenses/LICENSE.libsodium.txt", "LICENSE.libsodium.txt")),
		pypi=("PyNaCl",), modulos=("nacl",),
	),
	Componente(
		"cffi", "cffi", _version_dist("cffi"), "MIT-0", "Avisos", "Dependencia de cryptography, bcrypt y PyNaCl", "python",
		(("dist:cffi:licenses/LICENSE", "LICENSE.txt"),), pypi=("cffi",), modulos=("cffi", "_cffi_backend"),
	),
	Componente(
		"pycparser", "pycparser", _version_dist("pycparser"), "BSD-3-Clause", "Avisos", "Dependencia de cffi", "python",
		(("dist:pycparser:licenses/LICENSE", "LICENSE.txt"),), pypi=("pycparser",), modulos=("pycparser",),
	),
	Componente(
		"py7zr", "py7zr", _version_dist("py7zr"), "LGPL-2.1-or-later", "Avisos y oferta de fuentes",
		"Comprimidos 7z y paquetes de componentes", "python",
		(("dist:py7zr:LICENSE", "LICENSE.txt"),), pypi=("py7zr",), modulos=("py7zr",),
		fuentes="https://pypi.org/project/py7zr/0.11.3/#files (py7zr-0.11.3.tar.gz)",
	),
	Componente(
		"pycryptodome", "pycryptodome (dependencia de py7zr)", _version_dist("pycryptodome"), "BSD-2-Clause AND Unlicense AND MIT",
		"Avisos", "Cifrado AES de los 7z", "python",
		(("dist:pycryptodome:licenses/LICENSE.rst", "LICENSE.rst"),
			("dist:pycryptodome:licenses/src/mldsa-native/LICENSE", "mldsa-native-LICENSE.txt"),
			("dist:pycryptodome:licenses/src/mlkem-native/LICENSE", "mlkem-native-LICENSE.txt")),
		pypi=("pycryptodome",), modulos=("Crypto",),
	),
	Componente(
		"texttable", "texttable (dependencia de py7zr)", _version_dist("texttable"), "MIT", "Avisos", "Dependencia de py7zr", "python",
		(("dist:texttable:licenses/LICENSE", "LICENSE.txt"),), pypi=("texttable",), modulos=("texttable",),
	),
	Componente(
		"accessible_output2", "accessible_output2 (solo su código Python)", _version_dist("accessible_output2"), "MIT", "Avisos",
		"Voz directa con NVDA, JAWS o SAPI5", "python",
		(("dist:accessible_output2:LICENSE", "LICENSE.txt"),), pypi=("accessible_output2",), modulos=("accessible_output2",),
		notas=("Sus DLL no libres no se distribuyen (véase «Lo que no se distribuye»).",),
	),
	Componente(
		"libloader", "libloader (dependencia de accessible_output2)", _version_dist("libloader"), "MIT", "Avisos",
		"Dependencia de accessible_output2", "python",
		(("dist:libloader:licenses/LICENSE", "LICENSE.txt"),), pypi=("libloader",), modulos=("libloader",),
	),
	Componente(
		"platform_utils", "platform_utils (dependencia de accessible_output2)", _version_dist("platform_utils"), "MIT", "Avisos",
		"Dependencia de accessible_output2", "python",
		(("dist:platform_utils:licenses/LICENSE", "LICENSE.txt"),), pypi=("platform_utils",), modulos=("platform_utils",),
	),
	Componente(
		"platformdirs", "platformdirs (dependencia de platform_utils)", _version_dist("platformdirs"), "MIT", "Avisos",
		"Dependencia de accessible_output2", "python",
		(("dist:platformdirs:licenses/LICENSE", "LICENSE.txt"),), pypi=("platformdirs",), modulos=("platformdirs",),
	),
	Componente(
		"nvdaControllerClient", "NVDA Controller Client (nvdaControllerClient64.dll, dentro de accessible_output2)", "la de accessible_output2 0.17",
		"LGPL-2.1", "Avisos y oferta de fuentes", "Hablar con NVDA", "python",
		(("texto:nvda", "LEEME.txt"), (LGPL_21, "LGPL-2.1.txt")),
		fuentes="https://github.com/nvaccess/nvda (nvdaHelper/client)",
	),
	Componente(
		"cx_Freeze", "cx_Freeze (arranque del ejecutable congelado)", _version_dist("cx_Freeze"), "PSF-2.0 (freeze-core: MIT)", "Avisos",
		"ZCommander.exe y la carga de lib/", "python",
		(("dist:cx_Freeze:licenses/LICENSE.md", "LICENSE.md"), ("dist:freeze_core:licenses/LICENSE", "freeze-core-LICENSE.txt")),
		modulos=("library.zip", "library.dat"),
		notas=("cx_Freeze deja además `frozen_application_license.txt` junto a `ZCommander.exe`.",),
	),
	Componente(
		"rclone", "rclone (`rclone.exe`)", _version_base("rclone"), "MIT", "Avisos", "Proceso aparte (`rclone rcd`); complemento Nubes",
		"bin", (("repo:data/bin/rclone/LICENCIA-MIT.txt", "LICENSE.txt"),), ids=("rclone",),
	),
	Componente(
		"libarchive", "libarchive (`libarchive-13.dll`) y sus 7 DLL de MSYS2 UCRT64 (libb2-1, libbz2-1, libiconv-2, liblz4, liblzma-5, "
		"libzstd y zlib1)", _version_base("libarchive"),
		"BSD-2-Clause (libarchive), Zlib, bzip2-1.0.6, 0BSD (xz), BSD-2-Clause (lz4), BSD-3-Clause (zstd), CC0-1.0 (libb2), "
		"LGPL-2.1-or-later (libiconv)", "Avisos y oferta de fuentes (libiconv)", "Dentro del proceso por ctypes (comprimidos)", "bin",
		(("repo:data/bin/libarchive/licencias", ""), ("texto:lz4", "lz4/LICENSE")), ids=("libarchive",),
		fuentes="https://mirror.msys2.org/mingw/sources/ (mingw-w64-libiconv-1.19.1-1.src.tar.zst)",
		notas=("Los textos también viajan en `data/bin/libarchive/licencias/`, salvo el de lz4, que solo está aquí.",),
	),
	Componente(
		"7-Zip", "7za (`7za.exe` de 7-Zip Extra, sin unRAR)", _version_base("7za"), "LGPL-2.1-or-later AND BSD-3-Clause AND BSD-2-Clause",
		"Avisos y oferta de fuentes", "Proceso aparte, opcional (comprimidos)", "bin",
		(("repo:data/bin/7za/LICENCIA.txt", "License.txt"), (LGPL_21, "LGPL-2.1.txt")), ids=("7za",),
		fuentes="https://github.com/ip7z/7zip/releases/download/26.06/7z2606-src.7z",
	),
	Componente(
		"FFmpeg", "FFmpeg (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` y 7 DLL; compilación GPL «shared» de FFmpeg-Builds)",
		_version_base("ffmpeg"), "GPL-3.0-or-later", "Dar la Fuente Correspondiente",
		"Proceso aparte (Conversor multimedia, Reproductor y Lectura en voz)", "bin",
		(("repo:data/bin/ffmpeg/LICENCIA-GPL3.txt", "GPL-3.0.txt"),), ids=("ffmpeg",),
		fuentes="https://github.com/FFmpeg/FFmpeg/tree/n9.0 y los guiones de https://github.com/FFmpeg-Builds/FFmpeg-Builds "
			"de la compilación usada",
	),
	Componente(
		"mutagen", "mutagen (complemento Metadatos, `plugins/metadatos/lib/mutagen/`)", "1.48.1", "GPL-2.0-or-later",
		"Dar la fuente (va como código Python legible)", "Etiquetas de audio", "complementos",
		(("repo:plugins/metadatos/lib/mutagen/COPYING", "COPYING.txt"), ("repo:plugins/metadatos/lib/LEEME.txt", "LEEME.txt")),
		modulos=("mutagen",), fuentes="https://pypi.org/project/mutagen/1.48.1/#files (mutagen-1.48.1.tar.gz)",
	),
	Componente(
		"pypdf", "pypdf (complemento Lector de documentos, `plugins/documentos/lib/pypdf/`)", "7.0.0", "BSD-3-Clause", "Avisos",
		"Lectura de PDF", "complementos", (("repo:plugins/documentos/lib/LICENCIA-pypdf.txt", "LICENSE.txt"),), modulos=("pypdf",),
	),
	Componente(
		"pywinrt", "pywinrt (complemento OCR, `plugins/ocr/lib/winrt/`: winrt-runtime y los espacios Windows.Media.Ocr, "
		"Graphics.Imaging, Storage, Storage.Streams, Data.Pdf, Globalization, Foundation y Foundation.Collections)", "4.1.0", "MIT",
		"Avisos", "OCR de Windows", "complementos", (("repo:plugins/ocr/lib/LICENCIA-winrt.txt", "LICENSE.txt"),), modulos=("winrt",),
	),
	Componente(
		"typing_extensions", "typing_extensions (complemento OCR, `plugins/ocr/lib/typing_extensions.py`)", "4.16.0", "PSF-2.0",
		"Avisos", "Dependencia de pywinrt", "complementos",
		(("repo:plugins/ocr/lib/LICENCIA-typing_extensions.txt", "LICENSE.txt"),), modulos=("typing_extensions",),
	),
	Componente(
		"sonidos", "Paquetes de sonidos de serie (`data/sounds/`: Clásico, Suave, Retro 8 bits, Minimalista y Cristal) y sonidos de "
		"los complementos de serie", "1.0", "CC0-1.0", "Ninguna", "Sonidos de la interfaz", "otros",
		(("repo:data/sounds/clasico/LICENCIA.txt", "LICENCIA.txt"),),
		notas=("Generados por síntesis con `tools/generar_sonidos.py`, sin material de terceros; cada paquete lleva su `LICENCIA.txt`.",),
	),
	Componente(
		"runtime-VC++", "Runtime de Microsoft Visual C++ 2015-2022", "14", "Código distribuible de Microsoft («Biblioteca del Sistema»)",
		"Avisos", "Lo carga Python y las extensiones nativas", "otros",
		(("texto:vc", "LEEME.txt"), ("build:share/licenses/vc_redist/LICENSE.txt", "LICENSE.txt")),
		modulos=("vcruntime140", "vcruntime140_1", "vcruntime140_threads", "msvcp140", "msvcp140_1", "msvcp140_2",
			"msvcp140_atomic_wait", "msvcp140_codecvt_ids", "concrt140", "vcamp140", "vccorlib140", "vcomp140"),
	),
)

NO_DISTRIBUIDO = (
	"DLL no libres de accessible_output2: `SAAPI32.dll` (System Access), `dolapi.dll` (Dolphin), `PCTKUSR.dll` y `PCTKUSR64.dll` "
	"(PC-Talker), `ZDSRAPI.dll` y `ZDSRAPI_x64.dll` (Zhengdu); tampoco `nvdaControllerClient32.dll` (la compilación es de 64 bits). "
	"`setup_cx.py` las borra y `tools/comprobar_licencias.py` falla si alguna aparece. La voz sigue con NVDA, JAWS (por COM), SAPI5 y "
	"las notificaciones de UI Automation.",
	"`7z.dll` y `7z.exe` completos, 7-Zip-zstd, NanaZip y UnRAR (restricción de unRAR o licencia no libre). Si la persona tiene 7-Zip "
	"instalado, zCommander lo usa sin distribuirlo.",
	"WinFsp: lo instala la persona si quiere montar nubes como letra de unidad; zCommander solo lo detecta.",
	"Everything, `es.exe` y su SDK: el complemento de búsqueda instantánea usa el Everything que ya tenga instalado la persona.",
	"Pythonwin, Scintilla, isapi y adodbapi de pywin32, y NumPy y Pygments (dependencias opcionales de otros paquetes).",
)


# ── Lectura de orígenes ──────────────────────────────────────────────────────


def _site_packages() -> Path:
	"""Carpeta site-packages del entorno: la que contiene el dist-info de wxPython."""
	carpeta = _dist_info("wxPython")
	return carpeta.parent if carpeta else Path(sys.prefix) / "Lib" / "site-packages"


def _dist_info(nombre: str) -> Path | None:
	try:
		distribucion = importlib.metadata.distribution(nombre)
	except importlib.metadata.PackageNotFoundError:
		return None
	ruta = getattr(distribucion, "_path", None)
	return Path(ruta) if ruta else None


class _TextoHTML(html.parser.HTMLParser):
	"""Saca el texto de la página de licencias de la documentación de Python (sin scripts ni estilos)."""

	BLOQUES = {"p", "div", "pre", "h1", "h2", "h3", "h4", "li", "tr", "section", "br", "dt", "dd"}

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.partes: list[str] = []
		self._ignorar = 0
		self._pre = 0

	def handle_starttag(self, etiqueta, atributos):
		if etiqueta in {"script", "style", "nav", "head"}:
			self._ignorar += 1
		if etiqueta == "pre":
			self._pre += 1
		if etiqueta in self.BLOQUES:
			self.partes.append("\n")

	def handle_endtag(self, etiqueta):
		if etiqueta in {"script", "style", "nav", "head"} and self._ignorar:
			self._ignorar -= 1
		if etiqueta == "pre" and self._pre:
			self._pre -= 1
		if etiqueta in self.BLOQUES:
			self.partes.append("\n")

	def handle_data(self, datos):
		if not self._ignorar:
			self.partes.append(datos if self._pre else re.sub(r"\s+", " ", datos))


def _texto_de_html(ruta: Path) -> str:
	lector = _TextoHTML()
	lector.feed(ruta.read_text(encoding="utf-8", errors="replace"))
	texto = "".join(lector.partes)
	lineas = [linea.rstrip() for linea in texto.splitlines()]
	limpio = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
	# Solo el contenido: del título del artículo («History and License¶») al índice lateral.
	inicio = limpio.find("History and License¶")
	if inicio >= 0:
		limpio = limpio[inicio:]
	fin = limpio.find("\nTable of Contents")
	if fin > 0:
		limpio = limpio[:fin]
	return limpio.replace("¶", "").strip() + "\n"


def leer_origen(origen: str) -> list[tuple[str, bytes]] | None:
	"""Contenido de un origen como lista de (ruta relativa, bytes); None si no existe aquí."""
	tipo, _, resto = origen.partition(":")
	if tipo == "texto":
		return [("", TEXTOS[resto].encode("utf-8"))]
	if tipo == "dist":
		nombre, _, interna = resto.partition(":")
		carpeta = _dist_info(nombre)
		ruta = carpeta / interna if carpeta else None
	elif tipo == "site":
		ruta = _site_packages() / resto
	elif tipo == "python":
		ruta = Path(sys.base_prefix) / resto
	elif tipo == "html":
		ruta = Path(sys.base_prefix) / resto
		return [("", _texto_de_html(ruta).encode("utf-8"))] if ruta.is_file() else None
	elif tipo == "build":
		ruta = COMPILACION / resto
	elif tipo == "repo":
		ruta = RAIZ / resto
	else:
		raise ValueError(f"Origen desconocido: {origen}")
	if ruta is None or not ruta.exists():
		return None
	if ruta.is_dir():
		return [(p.relative_to(ruta).as_posix(), p.read_bytes()) for p in sorted(ruta.rglob("*")) if p.is_file()]
	return [("", ruta.read_bytes())]


def archivos_esperados(componente: Componente) -> dict[str, bytes | None]:
	"""Ruta relativa a ``data/docs/licencias`` → contenido (None si el origen no está en este equipo)."""
	resultado: dict[str, bytes | None] = {}
	for origen, destino in componente.archivos:
		contenido = leer_origen(origen)
		if contenido is None:
			resultado[f"{componente.carpeta}/{destino}"] = None
			continue
		for relativa, datos in contenido:
			nombre = "/".join(p for p in (componente.carpeta, destino, relativa) if p)
			resultado[nombre] = datos
	return resultado


# ── Documentos ───────────────────────────────────────────────────────────────


def _lineas_componente(c: Componente) -> list[str]:
	lineas = [f"### {c.nombre}", "", f"- Versión: {c.version_texto()}.", f"- Licencia: {c.licencia}.", f"- Obligación: {c.obligacion}.",
		f"- Uso en zCommander: {c.uso}."]
	if c.pypi:
		lineas.append("- Paquete de PyPI: " + ", ".join(f"`{p}`" for p in c.pypi) + ".")
	if c.ids:
		lineas.append("- Componente de `data/bin/linea_base.json`: " + ", ".join(f"`{i}`" for i in c.ids) + ".")
	lineas.append(f"- Textos de la licencia: carpeta `{c.carpeta}/`.")
	if c.fuentes:
		lineas.append(f"- Fuentes: {c.fuentes}.")
	lineas += [f"- {nota}" for nota in c.notas]
	lineas.append("")
	return lineas


def generar_leeme() -> str:
	lineas = [
		"# Licencias de zCommander y de sus componentes",
		"",
		"zCommander es software libre: puede redistribuirlo y modificarlo según la Licencia Pública General de GNU, versión 3 o "
		"posterior (GPL-3.0-or-later). Se distribuye sin ninguna garantía. Copyright © 2026 hxebolax y colaboradores.",
		"",
		"Este documento enumera cada componente de terceros que viaja con zCommander, su licencia y la carpeta de "
		"`data/docs/licencias/` donde está el texto que hay que acompañar. Lo genera `tools/generar_licencias.py` y lo comprueba "
		"`tools/comprobar_licencias.py`; no se edita a mano.",
		"",
		"Todas las licencias de esta lista son compatibles con la GPL-3.0.",
		"",
	]
	for grupo, titulo in GRUPOS.items():
		lineas += [f"## {titulo}", ""]
		for componente in (c for c in COMPONENTES if c.grupo == grupo):
			lineas += _lineas_componente(componente)
	lineas += ["## Lo que no se distribuye", ""]
	lineas += [f"- {texto}" for texto in NO_DISTRIBUIDO]
	lineas += [
		"",
		"## Oferta de fuentes (LGPL y GPL)",
		"",
		"Las licencias LGPL y GPL obligan a dar acceso al código fuente de estos componentes: zCommander, FFmpeg, mutagen, "
		"wxPython, paramiko, py7zr, NVDA Controller Client, libiconv (de libarchive) y 7za. Para cada versión publicada, "
		f"zCommander guarda una copia de esas fuentes en {URL_FUENTES_TERCEROS}<versión>/ durante al menos tres años desde la "
		"última versión que las use. Los detalles están en `OFERTA-DE-FUENTES.md`.",
		"",
	]
	return "\n".join(lineas)


def generar_oferta() -> str:
	lgpl_gpl = [c for c in COMPONENTES if c.fuentes]
	lineas = [
		"# Oferta de fuentes de zCommander",
		"",
		"zCommander se publica con la Licencia Pública General de GNU, versión 3 o posterior (GPL-3.0-or-later), y lleva "
		"componentes con licencias LGPL y GPL. Esas licencias le dan derecho a recibir el código fuente completo de cada uno, "
		"en la versión exacta que acompaña a su zCommander.",
		"",
		"## Qué puede pedir",
		"",
		"- El código fuente completo de zCommander de su versión (la «Fuente Correspondiente» de la GPL-3.0): los `.pyc` de la "
		"versión compilada no son fuente.",
		"- El código fuente de cada componente LGPL o GPL de la lista de abajo, en la versión que lleva su zCommander.",
		"",
		"## Dónde está",
		"",
		f"- zCommander: junto a cada versión, en {URL_PROYECTO}, el archivo `zCommander_v<versión>_fuentes.zip`.",
		f"- Componentes de terceros: {URL_FUENTES_TERCEROS}<versión>/, con los paquetes de fuentes exactos (sdist de PyPI, "
		"paquetes `.src.tar.zst` de MSYS2, el código de 7-Zip y el de FFmpeg con los guiones de la compilación usada).",
		"- Si alguno de esos enlaces no funciona, puede pedir las fuentes al titular, hxebolax, por los medios de contacto de la "
		"página del proyecto. Se entregan sin más coste que el de hacer la copia.",
		"",
		"## Cuánto tiempo vale",
		"",
		"Esta oferta vale durante tres años desde la última vez que se distribuyó la versión que la contiene (y, como mínimo, "
		"mientras se ofrezcan recambios o asistencia para ella).",
		"",
		"## Componentes con obligación de dar las fuentes",
		"",
	]
	for componente in lgpl_gpl:
		lineas.append(f"- {componente.nombre}, versión {componente.version_texto()} ({componente.licencia}): {componente.fuentes}.")
	lineas.append("")
	return "\n".join(lineas)


def contenidos() -> dict[str, bytes | None]:
	"""Todo lo que debe haber en ``data/docs/licencias`` (ruta relativa → bytes, o None si no se puede generar aquí)."""
	resultado: dict[str, bytes | None] = {}
	for componente in COMPONENTES:
		resultado.update(archivos_esperados(componente))
	resultado[LEEME] = generar_leeme().encode("utf-8")
	resultado[OFERTA] = generar_oferta().encode("utf-8")
	return resultado


def _normalizar(datos: bytes) -> bytes:
	"""Compara sin tener en cuenta los finales de línea (git puede cambiarlos)."""
	return datos.replace(b"\r\n", b"\n")


def desfasados(destino: Path = LICENCIAS) -> list[str]:
	"""Archivos que faltan o no coinciden con su origen (los que no se pueden generar aquí solo tienen que existir)."""
	problemas = []
	for relativa, datos in contenidos().items():
		ruta = destino / relativa
		if not ruta.is_file() or ruta.stat().st_size == 0:
			problemas.append(f"Falta {relativa}")
		elif datos is not None and _normalizar(ruta.read_bytes()) != _normalizar(datos):
			problemas.append(f"No está al día {relativa}")
	return problemas


def generar(destino: Path = LICENCIAS) -> tuple[list[str], list[str]]:
	"""Escribe lo que haya cambiado. Devuelve (escritos, sin origen en este equipo)."""
	escritos, sin_origen = [], []
	for relativa, datos in contenidos().items():
		ruta = destino / relativa
		if datos is None:
			if not ruta.is_file():
				sin_origen.append(relativa)
			continue
		if ruta.is_file() and _normalizar(ruta.read_bytes()) == _normalizar(datos):
			continue
		ruta.parent.mkdir(parents=True, exist_ok=True)
		ruta.write_bytes(datos)
		escritos.append(relativa)
	return escritos, sin_origen


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--comprobar", action="store_true", help="Falla si algún archivo falta o no está al día.")
	opciones = analizador.parse_args(argumentos)
	for flujo in (sys.stdout, sys.stderr):
		if hasattr(flujo, "reconfigure"):
			flujo.reconfigure(errors="replace")
	if opciones.comprobar:
		problemas = desfasados()
		for problema in problemas:
			print(problema)
		if not problemas:
			print("data/docs/licencias al día.")
		return 1 if problemas else 0
	escritos, sin_origen = generar()
	for relativa in escritos:
		print(f"Escrito {relativa}")
	for relativa in sin_origen:
		print(f"AVISO: no se encuentra el origen de {relativa} en este equipo (compile primero si es de build/).")
	if not escritos:
		print("Nada que cambiar.")
	return 1 if sin_origen else 0


if __name__ == "__main__":
	sys.exit(main())
