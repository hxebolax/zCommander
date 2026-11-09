# Oferta de fuentes de zCommander

zCommander se publica con la Licencia Pública General de GNU, versión 3 o posterior (GPL-3.0-or-later), y lleva componentes con licencias LGPL y GPL. Esas licencias le dan derecho a recibir el código fuente completo de cada uno, en la versión exacta que acompaña a su zCommander.

## Qué puede pedir

- El código fuente completo de zCommander de su versión (la «Fuente Correspondiente» de la GPL-3.0): los `.pyc` de la versión compilada no son fuente.
- El código fuente de cada componente LGPL o GPL de la lista de abajo, en la versión que lleva su zCommander.

## Dónde está

- zCommander: junto a cada versión, en https://xebolax.synology.me/zCommander/, el archivo `zCommander_v<versión>_fuentes.zip`.
- Componentes de terceros: https://xebolax.synology.me/zCommander/fuentes/<versión>/, con los paquetes de fuentes exactos (sdist de PyPI, paquetes `.src.tar.zst` de MSYS2, el código de 7-Zip y el de FFmpeg con los guiones de la compilación usada).
- Si alguno de esos enlaces no funciona, puede pedir las fuentes al titular, hxebolax, por los medios de contacto de la página del proyecto. Se entregan sin más coste que el de hacer la copia.

## Cuánto tiempo vale

Esta oferta vale durante tres años desde la última vez que se distribuyó la versión que la contiene (y, como mínimo, mientras se ofrezcan recambios o asistencia para ella).

## Componentes con obligación de dar las fuentes

- zCommander (núcleo, herramientas, complementos de serie, simulador DSM y complemento de NVDA), versión 2.0.1 (GPL-3.0-or-later): https://xebolax.synology.me/zCommander/ (archivo zCommander_v<versión>_fuentes.zip de cada versión).
- wxPython, versión 4.3.2 (LGPL-2.0-or-later WITH WxWindows-exception-3.1): https://pypi.org/project/wxPython/4.3.2/#files (wxpython-4.3.2.tar.gz).
- paramiko, versión 5.1.0 (LGPL-2.1): https://pypi.org/project/paramiko/5.1.0/#files (paramiko-5.1.0.tar.gz).
- py7zr, versión 0.11.3 (LGPL-2.1-or-later): https://pypi.org/project/py7zr/0.11.3/#files (py7zr-0.11.3.tar.gz).
- NVDA Controller Client (nvdaControllerClient64.dll, dentro de accessible_output2), versión la de accessible_output2 0.17 (LGPL-2.1): https://github.com/nvaccess/nvda (nvdaHelper/client).
- libarchive (`libarchive-13.dll`) y sus 7 DLL de MSYS2 UCRT64 (libb2-1, libbz2-1, libiconv-2, liblz4, liblzma-5, libzstd y zlib1), versión 3.8.11 (BSD-2-Clause (libarchive), Zlib, bzip2-1.0.6, 0BSD (xz), BSD-2-Clause (lz4), BSD-3-Clause (zstd), CC0-1.0 (libb2), LGPL-2.1-or-later (libiconv)): https://mirror.msys2.org/mingw/sources/ (mingw-w64-libiconv-1.19.1-1.src.tar.zst).
- 7za (`7za.exe` de 7-Zip Extra, sin unRAR), versión 26.06 (LGPL-2.1-or-later AND BSD-3-Clause AND BSD-2-Clause): https://github.com/ip7z/7zip/releases/download/26.06/7z2606-src.7z.
- FFmpeg (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` y 7 DLL; compilación GPL «shared» de FFmpeg-Builds), versión 9.0.2 (GPL-3.0-or-later): https://github.com/FFmpeg/FFmpeg/tree/n9.0 y los guiones de https://github.com/FFmpeg-Builds/FFmpeg-Builds de la compilación usada.
- mutagen (complemento Metadatos, `plugins/metadatos/lib/mutagen/`), versión 1.48.1 (GPL-2.0-or-later): https://pypi.org/project/mutagen/1.48.1/#files (mutagen-1.48.1.tar.gz).
