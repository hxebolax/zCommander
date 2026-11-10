# Licencias de zCommander y de sus componentes

zCommander es software libre: puede redistribuirlo y modificarlo según la Licencia Pública General de GNU, versión 3 o posterior (GPL-3.0-or-later). Se distribuye sin ninguna garantía. Copyright © 2026 hxebolax y colaboradores.

Este documento enumera cada componente de terceros que viaja con zCommander, su licencia y la carpeta de `data/docs/licencias/` donde está el texto que hay que acompañar. Lo genera `tools/generar_licencias.py` y lo comprueba `tools/comprobar_licencias.py`; no se edita a mano.

Todas las licencias de esta lista son compatibles con la GPL-3.0.

## zCommander

### zCommander (núcleo, herramientas, complementos de serie, simulador DSM y complemento de NVDA)

- Versión: 2.0.2.
- Licencia: GPL-3.0-or-later.
- Obligación: Dar la Fuente Correspondiente.
- Uso en zCommander: Todo el programa.
- Componente de `data/bin/linea_base.json`: `nvda`.
- Textos de la licencia: carpeta `zCommander/`.
- Fuentes: https://xebolax.synology.me/zCommander/ (archivo zCommander_v<versión>_fuentes.zip de cada versión).
- El complemento de NVDA (`data/bin/nvda/zCommander-<versión>.nvda-addon`, id `nvda` de la línea base) es parte de zCommander y tiene su misma licencia.

## Componentes de Python dentro del proceso

### Python y su biblioteca estándar

- Versión: 3.15.0.
- Licencia: PSF-2.0 (con componentes permisivos incorporados).
- Obligación: Avisos.
- Uso en zCommander: Intérprete y biblioteca estándar (python315.dll, lib/).
- Textos de la licencia: carpeta `Python/`.

### wxPython

- Versión: 4.3.2.
- Licencia: LGPL-2.0-or-later WITH WxWindows-exception-3.1.
- Obligación: Avisos y oferta de fuentes.
- Uso en zCommander: Interfaz gráfica (lib/wx).
- Paquete de PyPI: `wxPython`.
- Textos de la licencia: carpeta `wxPython/`.
- Fuentes: https://pypi.org/project/wxPython/4.3.2/#files (wxpython-4.3.2.tar.gz).

### pywin32

- Versión: 312.
- Licencia: PSF-2.0.
- Obligación: Avisos.
- Uso en zCommander: Integración con Windows (COM, shell, red, credenciales).
- Paquete de PyPI: `pywin32`.
- Textos de la licencia: carpeta `pywin32/`.
- Pythonwin, Scintilla, isapi y adodbapi no se distribuyen.

### comtypes

- Versión: 1.4.17.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Interfaces COM (UI Automation, propiedades).
- Paquete de PyPI: `comtypes`.
- Textos de la licencia: carpeta `comtypes/`.

### Send2Trash

- Versión: 2.1.0.
- Licencia: BSD-3-Clause.
- Obligación: Avisos.
- Uso en zCommander: Papelera de reciclaje.
- Paquete de PyPI: `Send2Trash`.
- Textos de la licencia: carpeta `Send2Trash/`.

### Python-Markdown

- Versión: 3.11.3.
- Licencia: BSD-3-Clause.
- Obligación: Avisos.
- Uso en zCommander: Manual y ayuda en HTML.
- Paquete de PyPI: `Markdown`.
- Textos de la licencia: carpeta `Markdown/`.

### paramiko

- Versión: 5.1.0.
- Licencia: LGPL-2.1.
- Obligación: Avisos y oferta de fuentes.
- Uso en zCommander: SFTP.
- Paquete de PyPI: `paramiko`.
- Textos de la licencia: carpeta `paramiko/`.
- Fuentes: https://pypi.org/project/paramiko/5.1.0/#files (paramiko-5.1.0.tar.gz).

### invoke (dependencia de paramiko)

- Versión: 3.0.3.
- Licencia: BSD-2-Clause.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de paramiko.
- Paquete de PyPI: `invoke`.
- Textos de la licencia: carpeta `invoke/`.

### cryptography (con OpenSSL incorporado)

- Versión: 50.0.2.
- Licencia: Apache-2.0 OR BSD-3-Clause.
- Obligación: Avisos.
- Uso en zCommander: Firmas Ed25519 de actualizaciones y complementos, copias cifradas, SFTP.
- Paquete de PyPI: `cryptography`.
- Textos de la licencia: carpeta `cryptography/`.

### bcrypt

- Versión: 5.0.0.
- Licencia: Apache-2.0.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de paramiko.
- Paquete de PyPI: `bcrypt`.
- Textos de la licencia: carpeta `bcrypt/`.

### PyNaCl (con libsodium)

- Versión: 1.6.2.
- Licencia: Apache-2.0 (libsodium: ISC).
- Obligación: Avisos.
- Uso en zCommander: Dependencia de paramiko.
- Paquete de PyPI: `PyNaCl`.
- Textos de la licencia: carpeta `PyNaCl/`.

### cffi

- Versión: 2.1.1.
- Licencia: MIT-0.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de cryptography, bcrypt y PyNaCl.
- Paquete de PyPI: `cffi`.
- Textos de la licencia: carpeta `cffi/`.

### pycparser

- Versión: 3.12.
- Licencia: BSD-3-Clause.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de cffi.
- Paquete de PyPI: `pycparser`.
- Textos de la licencia: carpeta `pycparser/`.

### py7zr

- Versión: 0.11.3.
- Licencia: LGPL-2.1-or-later.
- Obligación: Avisos y oferta de fuentes.
- Uso en zCommander: Comprimidos 7z y paquetes de componentes.
- Paquete de PyPI: `py7zr`.
- Textos de la licencia: carpeta `py7zr/`.
- Fuentes: https://pypi.org/project/py7zr/0.11.3/#files (py7zr-0.11.3.tar.gz).

### pycryptodome (dependencia de py7zr)

- Versión: 4.4.0.
- Licencia: BSD-2-Clause AND Unlicense AND MIT.
- Obligación: Avisos.
- Uso en zCommander: Cifrado AES de los 7z.
- Paquete de PyPI: `pycryptodome`.
- Textos de la licencia: carpeta `pycryptodome/`.

### texttable (dependencia de py7zr)

- Versión: 1.7.2.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de py7zr.
- Paquete de PyPI: `texttable`.
- Textos de la licencia: carpeta `texttable/`.

### accessible_output2 (solo su código Python)

- Versión: 0.17.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Voz directa con NVDA, JAWS o SAPI5.
- Paquete de PyPI: `accessible_output2`.
- Textos de la licencia: carpeta `accessible_output2/`.
- Sus DLL no libres no se distribuyen (véase «Lo que no se distribuye»).

### libloader (dependencia de accessible_output2)

- Versión: 1.4.3.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de accessible_output2.
- Paquete de PyPI: `libloader`.
- Textos de la licencia: carpeta `libloader/`.

### platform_utils (dependencia de accessible_output2)

- Versión: 1.6.3.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de accessible_output2.
- Paquete de PyPI: `platform_utils`.
- Textos de la licencia: carpeta `platform_utils/`.

### platformdirs (dependencia de platform_utils)

- Versión: 4.14.5.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de accessible_output2.
- Paquete de PyPI: `platformdirs`.
- Textos de la licencia: carpeta `platformdirs/`.

### NVDA Controller Client (nvdaControllerClient64.dll, dentro de accessible_output2)

- Versión: la de accessible_output2 0.17.
- Licencia: LGPL-2.1.
- Obligación: Avisos y oferta de fuentes.
- Uso en zCommander: Hablar con NVDA.
- Textos de la licencia: carpeta `nvdaControllerClient/`.
- Fuentes: https://github.com/nvaccess/nvda (nvdaHelper/client).

### cx_Freeze (arranque del ejecutable congelado)

- Versión: 8.7.4.
- Licencia: PSF-2.0 (freeze-core: MIT).
- Obligación: Avisos.
- Uso en zCommander: ZCommander.exe y la carga de lib/.
- Textos de la licencia: carpeta `cx_Freeze/`.
- cx_Freeze deja además `frozen_application_license.txt` junto a `ZCommander.exe`.

## Programas y bibliotecas de data/bin

### rclone (`rclone.exe`)

- Versión: 1.76.0.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: Proceso aparte (`rclone rcd`); complemento Nubes.
- Componente de `data/bin/linea_base.json`: `rclone`.
- Textos de la licencia: carpeta `rclone/`.

### libarchive (`libarchive-13.dll`) y sus 7 DLL de MSYS2 UCRT64 (libb2-1, libbz2-1, libiconv-2, liblz4, liblzma-5, libzstd y zlib1)

- Versión: 3.8.11.
- Licencia: BSD-2-Clause (libarchive), Zlib, bzip2-1.0.6, 0BSD (xz), BSD-2-Clause (lz4), BSD-3-Clause (zstd), CC0-1.0 (libb2), LGPL-2.1-or-later (libiconv).
- Obligación: Avisos y oferta de fuentes (libiconv).
- Uso en zCommander: Dentro del proceso por ctypes (comprimidos).
- Componente de `data/bin/linea_base.json`: `libarchive`.
- Textos de la licencia: carpeta `libarchive/`.
- Fuentes: https://mirror.msys2.org/mingw/sources/ (mingw-w64-libiconv-1.19.1-1.src.tar.zst).
- Los textos también viajan en `data/bin/libarchive/licencias/`, salvo el de lz4, que solo está aquí.

### 7za (`7za.exe` de 7-Zip Extra, sin unRAR)

- Versión: 26.06.
- Licencia: LGPL-2.1-or-later AND BSD-3-Clause AND BSD-2-Clause.
- Obligación: Avisos y oferta de fuentes.
- Uso en zCommander: Proceso aparte, opcional (comprimidos).
- Componente de `data/bin/linea_base.json`: `7za`.
- Textos de la licencia: carpeta `7-Zip/`.
- Fuentes: https://github.com/ip7z/7zip/releases/download/26.06/7z2606-src.7z.

### FFmpeg (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` y 7 DLL; compilación GPL «shared» de FFmpeg-Builds)

- Versión: 9.0.2.
- Licencia: GPL-3.0-or-later.
- Obligación: Dar la Fuente Correspondiente.
- Uso en zCommander: Proceso aparte (Conversor multimedia, Reproductor y Lectura en voz).
- Componente de `data/bin/linea_base.json`: `ffmpeg`.
- Textos de la licencia: carpeta `FFmpeg/`.
- Fuentes: https://github.com/FFmpeg/FFmpeg/tree/n9.0 y los guiones de https://github.com/FFmpeg-Builds/FFmpeg-Builds de la compilación usada.

## Bibliotecas incluidas en los complementos de serie

### mutagen (complemento Metadatos, `plugins/metadatos/lib/mutagen/`)

- Versión: 1.48.1.
- Licencia: GPL-2.0-or-later.
- Obligación: Dar la fuente (va como código Python legible).
- Uso en zCommander: Etiquetas de audio.
- Textos de la licencia: carpeta `mutagen/`.
- Fuentes: https://pypi.org/project/mutagen/1.48.1/#files (mutagen-1.48.1.tar.gz).

### pypdf (complemento Lector de documentos, `plugins/documentos/lib/pypdf/`)

- Versión: 7.0.0.
- Licencia: BSD-3-Clause.
- Obligación: Avisos.
- Uso en zCommander: Lectura de PDF.
- Textos de la licencia: carpeta `pypdf/`.

### pywinrt (complemento OCR, `plugins/ocr/lib/winrt/`: winrt-runtime y los espacios Windows.Media.Ocr, Graphics.Imaging, Storage, Storage.Streams, Data.Pdf, Globalization, Foundation y Foundation.Collections)

- Versión: 4.1.0.
- Licencia: MIT.
- Obligación: Avisos.
- Uso en zCommander: OCR de Windows.
- Textos de la licencia: carpeta `pywinrt/`.

### typing_extensions (complemento OCR, `plugins/ocr/lib/typing_extensions.py`)

- Versión: 4.16.0.
- Licencia: PSF-2.0.
- Obligación: Avisos.
- Uso en zCommander: Dependencia de pywinrt.
- Textos de la licencia: carpeta `typing_extensions/`.

## Sonidos y runtime de Visual C++

### Paquetes de sonidos de serie (`data/sounds/`: Clásico, Suave, Retro 8 bits, Minimalista y Cristal) y sonidos de los complementos de serie

- Versión: 1.0.
- Licencia: CC0-1.0.
- Obligación: Ninguna.
- Uso en zCommander: Sonidos de la interfaz.
- Textos de la licencia: carpeta `sonidos/`.
- Generados por síntesis con `tools/generar_sonidos.py`, sin material de terceros; cada paquete lleva su `LICENCIA.txt`.

### Runtime de Microsoft Visual C++ 2015-2022

- Versión: 14.
- Licencia: Código distribuible de Microsoft («Biblioteca del Sistema»).
- Obligación: Avisos.
- Uso en zCommander: Lo carga Python y las extensiones nativas.
- Textos de la licencia: carpeta `runtime-VC++/`.

## Lo que no se distribuye

- DLL no libres de accessible_output2: `SAAPI32.dll` (System Access), `dolapi.dll` (Dolphin), `PCTKUSR.dll` y `PCTKUSR64.dll` (PC-Talker), `ZDSRAPI.dll` y `ZDSRAPI_x64.dll` (Zhengdu); tampoco `nvdaControllerClient32.dll` (la compilación es de 64 bits). `setup_cx.py` las borra y `tools/comprobar_licencias.py` falla si alguna aparece. La voz sigue con NVDA, JAWS (por COM), SAPI5 y las notificaciones de UI Automation.
- `7z.dll` y `7z.exe` completos, 7-Zip-zstd, NanaZip y UnRAR (restricción de unRAR o licencia no libre). Si la persona tiene 7-Zip instalado, zCommander lo usa sin distribuirlo.
- WinFsp: lo instala la persona si quiere montar nubes como letra de unidad; zCommander solo lo detecta.
- Everything, `es.exe` y su SDK: el complemento de búsqueda instantánea usa el Everything que ya tenga instalado la persona.
- Pythonwin, Scintilla, isapi y adodbapi de pywin32, y NumPy y Pygments (dependencias opcionales de otros paquetes).

## Oferta de fuentes (LGPL y GPL)

Las licencias LGPL y GPL obligan a dar acceso al código fuente de estos componentes: zCommander, FFmpeg, mutagen, wxPython, paramiko, py7zr, NVDA Controller Client, libiconv (de libarchive) y 7za. Para cada versión publicada, zCommander guarda una copia de esas fuentes en https://xebolax.synology.me/zCommander/fuentes/<versión>/ durante al menos tres años desde la última versión que las use. Los detalles están en `OFERTA-DE-FUENTES.md`.
