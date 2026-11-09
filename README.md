# zCommander

**Gestor de archivos de doble panel para Windows, accesible de verdad con lector de pantalla.**

[![Última versión](https://img.shields.io/github/v/release/hxebolax/zCommander?label=versi%C3%B3n)](https://github.com/hxebolax/zCommander/releases/latest)
[![Licencia GPL-3.0](https://img.shields.io/badge/licencia-GPL--3.0--or--later-blue)](LICENSE)
[![Windows 10 y 11, 64 bits](https://img.shields.io/badge/Windows-10%20%7C%2011%20(64%20bits)-0078D6)](#requisitos)
[![Python 3.15](https://img.shields.io/badge/Python-3.15-3776AB)](#para-programadores)

zCommander es un gestor de archivos al estilo de Norton Commander y Total Commander, con dos listas de archivos, una al lado de la otra, y teclas de función para ver, copiar, mover y eliminar. Está pensado desde el principio para personas ciegas que usan **NVDA, JAWS o el Narrador**, tanto si empiezan como si ya conocen Norton, Total Commander o Far. También sirve a personas con baja visión y a quien prefiere trabajar con el teclado.

Es **portable**, **libre** (GPL-3.0) y habla **español**.

**[Descargar la última versión](https://github.com/hxebolax/zCommander/releases/latest)**

---

## Índice

- [Para quién es](#para-quién-es)
- [Qué ofrece](#qué-ofrece)
- [Accesibilidad](#accesibilidad)
- [Requisitos](#requisitos)
- [Descargar e instalar](#descargar-e-instalar)
- [Primeros pasos](#primeros-pasos)
- [Actualizaciones](#actualizaciones)
- [Privacidad y seguridad](#privacidad-y-seguridad)
- [Documentación](#documentación)
- [Para programadores](#para-programadores)
- [Contribuir](#contribuir)
- [Licencia y créditos](#licencia-y-créditos)

---

## Para quién es

- **Personas ciegas** que quieren un explorador de archivos donde siempre sepan en qué panel, en qué carpeta y sobre qué archivo están, sin sorpresas al volver de un diálogo.
- **Personas con baja visión**, con los colores de alto contraste de Windows y letra de hasta 40 puntos en los paneles.
- **Usuarios avanzados de teclado** que echan de menos Norton o Total Commander. zCommander trae sus esquemas de teclas, además de los de Far y el Explorador.
- **Cualquiera** que quiera ordenar sus archivos, trabajar con comprimidos, servidores y nubes desde un único programa.

## Qué ofrece

### Lo esencial de un gestor de archivos

- **Doble panel con pestañas**: copiar (F5), mover o renombrar (F6), crear carpeta (F7) y eliminar (F8) entre los dos lados, con la papelera de reciclaje.
- **Marcas claras**: marque uno a uno, por rangos o por patrones, y pregunte en cualquier momento qué hay marcado (Alt+Mayús+M). Usted decide si las marcas se leen como «seleccionado» o en una columna «Marca» que puede colocar donde quiera.
- **Copias en segundo plano**, con pausa, cola y una única lista para decidir qué hacer con los archivos que ya existen (F12).
- **Visor y editor** de texto accesibles (F3 y F4), búsqueda de archivos por nombre, contenido, tamaño y fecha (Alt+F7), comparación y sincronización de carpetas y renombrado múltiple (Ctrl+M).
- **Comprimidos como carpetas**: ZIP, 7z, TAR, RAR, ISO, CAB y muchos más.
- **Conexiones**: FTP, FTPS y SFTP, unidades de red y la raíz «Red» con los equipos de su red.
- **Línea de órdenes, menú de usuario, asociaciones de archivos**, sumas de comprobación, dividir y unir archivos y tamaño de carpetas.

### Nubes y NAS

- **Nubes como unidades del panel**: Google Drive, OneDrive y SharePoint, Dropbox, Box, pCloud, MEGA, Yandex, Koofr, Jottacloud, kDrive, Nextcloud, ownCloud, WebDAV, S3 y más de 70 servicios gracias a [rclone](https://rclone.org).
- **Sin claves de API para la mayoría de servicios**: inicia sesión en el navegador o con su usuario y contraseña. zCommander también detecta las carpetas de los programas oficiales que ya tenga instalados (OneDrive, Google Drive para escritorio, Dropbox, iCloud, Synology Drive…) para usarlas sin iniciar sesión.
- **NAS Synology** con su propia ventana accesible.

### 27 complementos de serie

Reproductor multimedia, lector de documentos, reconocimiento de texto (OCR), metadatos y etiquetas de audio, búsqueda instantánea con Everything, conversor multimedia con FFmpeg, buscador de duplicados, ocupación del disco, archivos en uso y procesos, editor hexadecimal, imágenes, sincronización y copias, cifrado de archivos, notas y etiquetas, proyectos, historial del portapapeles, lectura en voz y audiolibros, monitor de carpetas con reglas automáticas, seguridad de descargas, papelera como panel, Git básico, SQLite y CSV, organizador por metadatos, programador de tareas, codificaciones y fines de línea, nubes y NAS Synology.

Cada complemento se activa o desactiva por separado, y se pueden instalar otros firmados.

### A su medida

- Perfiles **Novato, Intermedio y Avanzado**, y perfiles propios que se exportan e importan.
- **Macros**, esquemas de teclas, barra de botones, menús propios, espacios de trabajo y reglas.
- Un **sistema de sonidos** con cinco paquetes de serie, para saber qué pasa sin necesidad de voz.
- **Copias de seguridad** de toda la configuración.
- **Paleta de órdenes** (Ctrl+E): escriba lo que quiere hacer y zCommander le dice además su atajo para que lo aprenda.

## Accesibilidad

La accesibilidad no es un añadido: es el criterio con el que se diseña cada ventana.

- Funciona con **NVDA, JAWS y el Narrador** usando los controles nativos de Windows, sin depender de ningún complemento.
- Cada lista anuncia sus columnas en el **orden de lectura** que usted elija, y puede leer una sola columna sin moverse (Ctrl+1 a Ctrl+0).
- Cada control tiene su **ayuda contextual con Ctrl+H**, y cada pantalla tiene letras de acceso sin repetir.
- Detalle de los anuncios configurable, historial de lo anunciado y **sonidos** para cada acontecimiento.
- **Complemento opcional para NVDA** (incluido) que afina todavía más la lectura de las listas.
- Manual completo con **F1**, escrito para leerse con lector de pantalla y navegable por encabezados.

## Requisitos

- **Windows 10** (versión 1809 o posterior) **u 11, de 64 bits**.
- Si usa lector de pantalla: NVDA 2025 o posterior, JAWS 2025 o posterior o el Narrador de Windows 11. El complemento de zCommander para NVDA necesita NVDA 2026.1 o posterior.
- **No necesita instalar Python ni nada más**: la versión portable lleva dentro todo lo necesario.
- Opcionales: [7-Zip](https://www.7-zip.org) para RAR y 7z cifrados, [WinFsp](https://winfsp.dev) para montar una nube como letra de unidad y [Everything](https://www.voidtools.com) para la búsqueda instantánea.

## Descargar e instalar

1. Descargue `zCommander_v<versión>.zip` de la [página de la última versión](https://github.com/hxebolax/zCommander/releases/latest).
2. En el Explorador, sitúese sobre el archivo, pulse la tecla Aplicaciones y elija **«Extraer todo»**.
3. Elija una carpeta donde tenga permiso de escritura, por ejemplo Documentos o una memoria USB. **No use Archivos de programa**: allí zCommander no podría guardar su configuración.
4. Entre en la carpeta `zCommander` y pulse Intro sobre `ZCommander.exe`.

Si Windows muestra el aviso de SmartScreen, elija «Más información» y después «Ejecutar de todas formas».

zCommander no se instala: todo lo que guarda está en su carpeta `data`. Solo escribe en el registro de Windows si usted activa «Arrancar zCommander al iniciar sesión en Windows». Para desinstalarlo, desactive antes esa opción si la activó, y borre la carpeta.

## Primeros pasos

La primera vez se abre un asistente que le ayuda a elegir perfil. Después, el foco queda en la lista del panel izquierdo.

| Tecla | Qué hace |
|---|---|
| Tab | Pasa al otro panel |
| Alt+F1 y Alt+F2 | Elegir unidad, nube o carpeta especial del lado izquierdo o derecho |
| Insert o Espacio | Marcar el archivo del cursor |
| Alt+Mayús+M | Decir qué hay marcado |
| F3 y F4 | Ver y editar |
| F5 y F6 | Copiar y mover al otro panel |
| F7 | Crear carpeta |
| F8 o Supr | Eliminar (a la papelera) |
| Alt+F7 | Buscar archivos |
| F12 | Operaciones en curso |
| Ctrl+E | Paleta de órdenes |
| F9 o Alt | Barra de menús |
| F1 | Manual |
| Ctrl+H | Ayuda del control enfocado |

La lista completa de teclas está en el menú Ayuda y en [`data/docs/teclas.md`](data/docs/teclas.md).

## Actualizaciones

zCommander busca sus versiones nuevas desde el menú **Ayuda, «Buscar actualizaciones»** y, si lo desea, de forma periódica. **Nunca instala nada sin preguntarle**, y si la versión nueva no arranca, vuelve sola a la anterior.

En **Preferencias, página Actualizaciones**, puede elegir de dónde se descargan:

- **El servidor del autor** (xebolax.synology.me).
- **GitHub** (las releases de este repositorio).
- **Las dos**: se usa la que tenga la versión más nueva, y si una no responde, la otra.
- **Una dirección personalizada**, por ejemplo un espejo en su propia red.

Venga de donde venga, cada actualización tiene que estar **firmada** con la clave de zCommander (Ed25519) y su suma SHA-256 tiene que coincidir. Si no, se descarta.

También se actualizan desde el programa sus componentes externos (rclone, libarchive, 7za y FFmpeg) y los complementos.

## Privacidad y seguridad

- zCommander **no envía datos de uso** ni estadísticas a nadie.
- Solo se conecta a Internet con los servidores y nubes que usted abre, y para buscar actualizaciones si tiene activada esa opción (se desactiva en Preferencias, página Actualizaciones).
- Las contraseñas de servidores y nubes se guardan **cifradas con DPAPI de Windows**, ligadas a su usuario.
- Los complementos y las actualizaciones se verifican con **firmas digitales**.

## Documentación

- [Manual de usuario](data/docs/manual.md): también se abre con F1 dentro del programa.
- [Lista de teclas](data/docs/teclas.md)
- [Novedades de cada versión](data/docs/changelog.md)
- [Sonidos](data/docs/sonidos.md)
- [Guía para crear complementos](docs/complementos/guia.md)
- [Guía técnica del proyecto](LEEME.md): estructura, herramientas, compilación y publicación en detalle.

---

## Para programadores

zCommander está escrito en **Python 3.15** con **wxPython 4.3** y se compila con **cx_Freeze**. Tiene más de 2100 pruebas automáticas con pytest.

### Preparar el entorno

Necesita Windows 10 u 11 de 64 bits, [Python 3.15](https://www.python.org/downloads/windows/) instalado con el lanzador `py` y [Git](https://git-scm.com).

```bash
git clone https://github.com/hxebolax/zCommander.git
```

```bash
cd zCommander
```

Cree el entorno virtual `.venv` con todas las dependencias:

```bash
entorno.bat crear
```

Descargue los programas de terceros a `data\bin` (rclone, libarchive, 7za y FFmpeg):

```bash
entorno.bat descargar
```

Y arranque la aplicación:

```bash
entorno.bat ejecutar
```

`entorno.bat` sin argumentos muestra un menú numerado con todas las órdenes: crear, instalar, ejecutar, depurar, pruebas, compilar, empaquetar, publicar y más.

### Los componentes de `data\bin`

Los ejecutables y las DLL de terceros **no están en el repositorio**: alguno pasa de los 100 MB que admite GitHub. Sí están sus licencias y [`data/bin/linea_base.json`](data/bin/linea_base.json), que dice qué archivo va en cada sitio y con qué suma SHA-256.

`tools/descargar_componentes.py` (o `entorno.bat descargar`) los trae y comprueba cada suma, así que lo que queda en `data\bin` es exactamente lo que se probó en esa versión:

```bash
.venv\Scripts\python tools\descargar_componentes.py
```

- Sin opciones, descarga `zCommander_v<versión>_componentes.zip` de la release de GitHub de la versión del código. Es la forma recomendada.
- Con `--origen`, descarga cada paquete de su proyecto original: GitHub de rclone, 7-Zip y FFmpeg, y MSYS2 para libarchive. El paquete de 7za necesita 7-Zip instalado para abrirse. FFmpeg sale de una compilación «latest» que cambia con el tiempo: si su suma ya no coincide, el script lo dice y no instala nada de FFmpeg.
- `--si` no pregunta antes de usar la red, `--forzar` vuelve a bajar todo, y `--crear-paquete` genera el ZIP de componentes para una release nueva.

Al terminar, construye también el complemento para NVDA en `data\bin\nvda`.

### Pruebas y calidad

```bash
entorno.bat pruebas
```

```bash
.venv\Scripts\ruff check .
```

```bash
.venv\Scripts\python tools\generar_anexos.py --comprobar
```

```bash
.venv\Scripts\python main.py --comprobar-arranque
```

Las pruebas nunca tocan la carpeta `data` real ni Internet: redirigen `data` con la variable `APP_DATA_DIR` a una carpeta temporal. Además de las pruebas, hay comprobadores de teclas (`tools/comprobar_teclas.py`), de letras de acceso de menús y preferencias (`tools/comprobar_menus.py` y `tools/comprobar_preferencias.py`) y de licencias (`tools/comprobar_licencias.py`). Lo que no se puede automatizar, oír la aplicación con cada lector de pantalla, se comprueba con [`docs/pruebas-manuales.md`](docs/pruebas-manuales.md).

### Estructura

| Carpeta | Qué contiene |
|---|---|
| `main.py` | Punto de entrada: registro, idioma, instancia única y arranque de la ventana |
| `app/core` | Infraestructura: rutas, versión, configuración, registro, red, descargas, secretos |
| `app/services` | La lógica, sin wx y probada sin ventanas: sistema de archivos virtual, operaciones, actualizador, componentes, sonidos, macros |
| `app/plugins` | El sistema de complementos y su API pública |
| `app/ui` | Ventanas, diálogos y controles; el catálogo de órdenes está en `app/ui/ordenes.py` |
| `plugins` | Los 27 complementos de serie |
| `nvda_addon` | El complemento de zCommander para NVDA |
| `data` | Lo que viaja con la aplicación: `bin`, `docs`, `sounds`, `locales` e `icons` |
| `docs` | Diseño, anexos generados, investigación y la guía de complementos |
| `tools` | Herramientas de desarrollo, compilación y publicación |
| `tests` | Pruebas con pytest |

**Regla de capas:** `app/ui` usa `app/services`, `app/plugins` y `app/core`. `app/services` y `app/plugins` nunca importan wx ni `app/ui`. Los complementos solo importan `app.plugins.api`.

### Compilar y empaquetar

```bash
entorno.bat compilar
```

```bash
entorno.bat empaquetar
```

La compilación queda en `build\ZCommander` y se comprueba sola que arranca. El ZIP portable queda en `dist\zCommander_v<versión>.zip`. Los pasos previos (anexos, sonidos, componentes, licencias) y la publicación están detallados en la [guía técnica](LEEME.md).

### Publicar una versión

`tools/publicar.py` compila, comprueba y crea en `dist` el ZIP portable, el ZIP de fuentes, el ZIP de componentes y el `version.json` firmado con Ed25519. La clave privada vive en `tools/claves`, que nunca entra en git. Cada release de GitHub lleva:

- `zCommander_v<versión>.zip`: la versión portable.
- `zCommander_v<versión>_fuentes.zip`: el código fuente, que la GPL obliga a ofrecer.
- `zCommander_v<versión>_componentes.zip`: los binarios de `data\bin` para `tools/descargar_componentes.py`.
- `version.json`: el manifiesto firmado que lee el actualizador.

## Contribuir

Las contribuciones son bienvenidas: informes de fallos, ideas, traducciones, complementos y código. Lea [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir una propuesta de cambio.

Si encuentra un fallo, [abra una incidencia](https://github.com/hxebolax/zCommander/issues) contando qué hacía, qué esperaba, qué pasó y con qué lector de pantalla. Adjunte el registro de `data\logs` si puede.

## Licencia y créditos

zCommander es software libre con licencia **GPL-3.0-or-later**. El texto completo está en [LICENSE](LICENSE).

Copyright (C) 2026 hxebolax y colaboradores.

zCommander se apoya en grandes proyectos libres: [wxPython](https://wxpython.org), [rclone](https://rclone.org), [libarchive](https://libarchive.org), [7-Zip](https://www.7-zip.org), [FFmpeg](https://ffmpeg.org), [py7zr](https://github.com/miurahr/py7zr), [paramiko](https://www.paramiko.org), [cryptography](https://cryptography.io) y otros. Sus licencias están en [`data/docs/licencias`](data/docs/licencias), y la oferta de fuentes de los componentes LGPL y GPL en [`OFERTA-DE-FUENTES.md`](data/docs/licencias/OFERTA-DE-FUENTES.md).
