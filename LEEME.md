# zCommander

zCommander es un gestor de archivos de doble panel para Windows, clon accesible de Norton Commander. Está pensado sobre todo para personas ciegas que usan NVDA, JAWS o Narrador, desde las que empiezan hasta las avanzadas, y también para personas con baja visión y para quien prefiere el teclado.

Versión 2.0.1, del 9 de noviembre de 2026. Está escrito en Python 3.15 con wxPython y es portable: todo lo que guarda va en la carpeta data, junto al programa.

La 2.0 añade complementos (con 27 de serie), un sistema de sonidos, actualizaciones de la aplicación y de sus componentes, copias de seguridad de la configuración, RAR y muchos más comprimidos, la raíz «Red», macros y personalización avanzada, y un complemento para NVDA.

El manual para las personas usuarias está en data\docs\manual.md y se abre en la aplicación con F1. La lista de teclas está en data\docs\teclas.md, el mapa de sonidos en data\docs\sonidos.md y las novedades de cada versión en data\docs\changelog.md.

## Licencia

zCommander es software libre con licencia GPL-3.0-or-later (GNU General Public License, versión 3 o posterior). El texto íntegro está en LICENSE y se distribuye en data\docs\licencias\zCommander.

Cada archivo de código propio empieza con dos líneas: SPDX-License-Identifier: GPL-3.0-or-later y Copyright (C) 2026 hxebolax y colaboradores. tools\comprobar_licencias.py falla si falta en alguno.

Los componentes de terceros tienen sus licencias en data\docs\licencias, una carpeta por componente, con la lista en LEEME-LICENCIAS.md y la oferta de fuentes en OFERTA-DE-FUENTES.md. La oferta vale tres años; las fuentes se publican en https://xebolax.synology.me/zCommander/fuentes/. Los complementos que se distribuyan con zCommander deben tener una licencia compatible con la GPL-3.

## Requisitos

- Windows 10 (versión 1809 o posterior) u 11, de 64 bits.
- Para la versión portable compilada no hace falta Python ni ningún otro programa: lleva dentro todo lo necesario, incluidos los runtimes de Visual C++ y los componentes de data\bin.
- Para ejecutarlo desde el código: Python 3.15 instalado con el lanzador py de Windows.
- Opcionales, que instala la persona si los quiere: 7-Zip (RAR y 7z cifrados), WinFsp (montar nubes como letra de unidad) y Everything (búsqueda instantánea).

## Usar la versión portable

1. Extraiga zCommander_v2.0.1.zip en una carpeta donde tenga permiso de escritura (Documentos, una memoria USB). No en Archivos de programa.
2. Entre en la carpeta zCommander que hay dentro y ejecute ZCommander.exe.
3. La primera vez se abre el asistente de primer arranque, que le ayuda a elegir perfil (Novato, Intermedio o Avanzado).

zCommander busca sus versiones nuevas y las instala desde el menú Ayuda, «Buscar actualizaciones» (capítulo «Actualizar zCommander» del manual). También se puede actualizar a mano extrayendo la versión nueva encima: la configuración está en data\config y el ZIP no la trae. Para desinstalar, borre la carpeta (antes, desactive «Arrancar zCommander al iniciar sesión en Windows» si la activó).

## Ejecutar desde el código

Todo se hace con entorno.bat, en la raíz del proyecto. Sin argumentos muestra un menú numerado; con un argumento ejecuta esa orden directamente, por ejemplo entorno.bat pruebas.

| Orden | Qué hace |
|---|---|
| crear | Crea el entorno virtual .venv con Python 3.15 e instala las dependencias (opción 1) |
| instalar | Instala o reinstala requirements.txt y requirements-dev.txt (opción 2) |
| ejecutar | Arranca la aplicación sin consola, con pythonw (opción 3) |
| depurar | Arranca con consola y en modo de desarrollo de Python (opción 4) |
| pruebas | Ejecuta todas las pruebas con pytest (opción 5) |
| compilar | Compila con cx_Freeze y comprueba que el ejecutable arranca (opción 6) |
| comprobar | Comprueba que build\ZCommander\ZCommander.exe arranca y se cierra bien (opción 7) |
| verificar | Verifica la compilación: complementos, biblioteca estándar y licencias (opción 8) |
| empaquetar | Crea el ZIP portable (opción 9) |
| sonidos | Genera los paquetes de sonidos de serie (opción 10) |
| componentes | Comprueba data\bin con la línea base (opción 11) |
| nvda | Construye el complemento de NVDA (opción 12) |
| licencias | Genera data\docs\licencias y lo comprueba (opción 13) |
| publicar | Prepara una versión en dist, sin copiarla al servidor (opción 14) |
| servidor | Prepara una versión y la copia al servidor (opción 15) |
| limpiar | Borra build y las cachés de pytest y ruff; no toca .venv ni data (opción 16) |
| datos | Abre la carpeta data en el Explorador (opción 17) |
| descargar | Descarga a data\bin los componentes de terceros con sus sumas comprobadas (opción 18) |

La versión de Python se fija en la variable VERSION_PY al principio de entorno.bat (3.15). Si el lanzador py no la encuentra, compruebe con py -0p qué versiones tiene instaladas.

Primeros pasos con el código:

1. entorno.bat crear
2. entorno.bat descargar (los ejecutables y las DLL de data\bin no están en git: los trae tools\descargar_componentes.py)
3. entorno.bat ejecutar

Argumentos de main.py (los desconocidos se anotan en el registro y se ignoran):

- Una ruta de carpeta abre el panel izquierdo en ella; una ruta de archivo, su carpeta con el cursor en él. Si zCommander ya está abierto, le pasa la ruta y se cierra.
- --comprobar-arranque arranca sin mostrar la ventana y sale con código 0 si todo fue bien. Con --complemento-prueba y una carpeta, carga además ese complemento. Lo usan las pruebas, la orden comprobar y tools\publicar.py.
- --sin-complementos arranca en modo seguro, sin complementos (también manteniendo Mayús pulsada al arrancar).
- --desarrollo-complementos y una carpeta carga un complemento en desarrollo desde ella.
- --probar-componente y un id (con --carpeta opcional) prueba un componente de data\bin y sale con 0 si funciona.
- --tarea y --modo-tarea los usa el programador de tareas; --al-iniciar-sesion, el arranque con Windows; --tras-actualizar y --esperar-pid, el actualizador.

La variable de entorno APP_DATA_DIR cambia la carpeta data por otra (la usan las pruebas y la orden comprobar, para no ensuciar la carpeta real). APP_DEPURACION=1 la pone la orden depurar.

## Estructura de carpetas

- main.py: punto de entrada. Configura el registro, el idioma y la instancia única, aplica lo pendiente (restauraciones, componentes) y arranca la ventana.
- app\core: infraestructura sin lógica de archivos: rutas, versión, configuración, almacén JSON, registro, tareas en hilos, instancia única, secretos cifrados, red y descargas (biblioteca estándar), procesos (Job Object) y documentación.
- app\services: la lógica, sin wx y probada sin ventanas: sistema de archivos virtual (vfs: disco, comprimidos con libarchive y 7-Zip, FTP, SFTP, raíz «Red»), operaciones, sonidos, componentes, copias de seguridad, actualizador, macros, reglas, espacios y la integración con Windows (windows).
- app\plugins: el sistema de complementos, sin wx: la API pública (api.py, versión 1.1), manifiestos, cargador, protección, firma, paquetes y gestor.
- app\ui: ventanas, diálogos y controles. El catálogo de órdenes, del que salen menús, teclas, barra de teclas, paleta y lista de teclas, está en app\ui\ordenes.py. Los manejadores de cada orden van en app\ui\acciones.
- plugins: los 27 complementos de serie, cada uno con su manifiesto.toml, su código, su ayuda en doc\es y sus sonidos. Viajan junto al ejecutable, fuera de data.
- nvda_addon: el código del complemento de zCommander para NVDA.
- data: lo que la aplicación necesita o genera. Viajan en la compilación bin, sounds, locales, docs e icons. Nunca viajan config, logs, temp, cache, backups, plugins (los de la persona), sounds_usuario, plantillas ni ninguna otra carpeta generada al usarla.
- data\bin: los componentes de terceros (rclone, libarchive, 7za, FFmpeg) y el complemento de NVDA generado, con su ficha en componentes.json y la línea base probada en linea_base.json.
- docs: documentación de desarrollo. diseno-2.md es el diseño de la 2.0 y diseno.md el de la 1.x; ordenes.md, configuracion.md y componentes.md son anexos generados desde el código; complementos\guia.md es la guía del autor de complementos; pruebas-manuales.md es el recorrido de comprobación con cada lector de pantalla; investigacion y revision guardan la investigación previa y las revisiones.
- tools: herramientas de desarrollo (lista abajo).
- tests: pruebas con pytest. tests\servicios no usa wx; tests\ui crea ventanas reales sin mostrarlas; tests\plugins prueba los complementos.
- entorno.bat, setup_cx.py, requirements.txt, requirements-dev.txt y pyproject.toml.

Regla de capas: app\ui usa app\services, app\plugins y app\core; app\services y app\plugins nunca importan wx ni app\ui. Los complementos solo importan app.plugins.api.

## Herramientas de tools

- generar_anexos.py: genera docs\ordenes.md, docs\configuracion.md, docs\componentes.md, data\docs\teclas.md, data\docs\sonidos.md y app\plugins\serie.py. Con --comprobar, falla si no están al día.
- comprobar_teclas.py: compara las teclas del código con data\docs\teclas.md.
- comprobar_menus.py y comprobar_preferencias.py: letras de acceso de los menús y de cada página de Preferencias.
- notas_version.py: notas de una versión del registro de cambios.
- generar_sonidos.py: genera los 5 paquetes de sonidos de serie por síntesis, siempre con los mismos bytes (--comprobar lo verifica).
- preparar_componentes.py: escribe data\bin\linea_base.json desde data\bin; con --comprobar, falla si no coinciden.
- descargar_componentes.py: descarga a data\bin los ejecutables y las DLL de terceros y comprueba cada suma con linea_base.json. Sin opciones los baja del recurso zCommander_v<versión>_componentes.zip de la release de GitHub; con --origen, de cada proyecto original; con --crear-paquete crea ese ZIP para publicarlo.
- construir_complemento.py: genera data\bin\nvda\zCommander-<versión>.nvda-addon.
- generar_licencias.py y comprobar_licencias.py: generan data\docs\licencias y comprueban cabeceras, licencias de terceros y que no viaje ninguna DLL no libre.
- fuentes_terceros.py: reúne las fuentes de los componentes LGPL y GPL para la oferta de fuentes.
- crear_plugin.py, validar_plugin.py y empaquetar_plugin.py: crear, validar y empaquetar (y firmar) complementos; la plantilla está en tools\plantilla_plugin. Se explican en docs\complementos\guia.md.
- firmar_version.py: claves Ed25519 y firma del manifiesto de actualización.
- empaquetar.py: crea el ZIP portable.
- verificar_build.py: comprueba una compilación antes de empaquetarla.
- publicar.py: prepara y publica una versión (apartado «Publicar una versión»).
- generar_provisionales.py y revision_egm.py: módulos provisionales de órdenes y revisiones con EGM, para el desarrollo.

## Dependencias

Las de la aplicación están en requirements.txt, con las versiones probadas en Python 3.15:

- wxPython 4.3.2: la interfaz.
- pywin32 312 y comtypes 1.4.17: portapapeles, menú contextual de Windows, unidades de red y COM.
- Send2Trash 2.1.0: la papelera de reciclaje.
- paramiko 5.1.0: SFTP.
- py7zr 0.11.3: comprimidos 7z. Las versiones 1.x aún no se pueden instalar en Python 3.15.
- cryptography 50.0.2: firmas Ed25519 de complementos y actualizaciones, y copias de seguridad cifradas. Es obligatoria.
- Markdown 3.11.3: el manual en formato de página en el visor de ayuda.
- accessible_output2 0.17, con libloader y platform_utils: voz directa con NVDA y JAWS. Es opcional; sin él, los anuncios van por las notificaciones de Windows. La compilación no lleva sus DLL no libres.

Los componentes de data\bin no son paquetes de Python: rclone 1.76.0, libarchive 3.8.11, 7za 26.06 y FFmpeg 9.0.2, con su origen y sus sumas en docs\componentes.md. Algunos complementos de serie llevan bibliotecas en su carpeta lib (mutagen, pypdf, dulwich).

Las de desarrollo están en requirements-dev.txt, que incluye las anteriores: cx_Freeze 8.7.4, pytest 9.2.0, ruff 0.17.4 y pyftpdlib 2.2.0 (servidor FTP local para las pruebas).

## Pruebas

- Todas: entorno.bat pruebas, o .venv\Scripts\python -m pytest tests -q.
- Solo la documentación y el visor de ayuda: .venv\Scripts\python -m pytest tests/test_documentacion.py tests/test_visor_ayuda.py -q.
- Estilo y errores: .venv\Scripts\ruff check .
- Anexos al día: .venv\Scripts\python tools\generar_anexos.py --comprobar. Si cambia el catálogo de órdenes, la configuración, un manifiesto o la línea base, regenérelos sin --comprobar.
- Teclas documentadas: .venv\Scripts\python tools\comprobar_teclas.py --teclas data\docs\teclas.md.
- Licencias: .venv\Scripts\python tools\generar_licencias.py --comprobar y .venv\Scripts\python tools\comprobar_licencias.py.
- Un complemento: .venv\Scripts\python tools\validar_plugin.py plugins\<carpeta>.
- Arranque: .venv\Scripts\python main.py --comprobar-arranque.
- Notas de la versión: .venv\Scripts\python tools\notas_version.py --changelog data\docs\changelog.md.

Las pruebas nunca tocan la carpeta data real ni Internet: redirigen data con APP_DATA_DIR a una carpeta temporal, y el NAS se prueba contra un simulador local.

Lo que no se puede automatizar, oír la aplicación con NVDA, JAWS y Narrador, se comprueba siguiendo docs\pruebas-manuales.md, que tiene un recorrido para la 1.x y otro para la 2.0.

## Compilar con cx_Freeze

1. Antes de compilar: tools\generar_anexos.py --comprobar, tools\generar_sonidos.py --comprobar, tools\preparar_componentes.py --comprobar, tools\construir_complemento.py y tools\generar_licencias.py.
2. entorno.bat compilar (o .venv\Scripts\python setup_cx.py build; con --debug, el ejecutable lleva consola).
3. El resultado queda en build\ZCommander, con ZCommander.exe, los runtimes de Visual C++, la carpeta plugins con los complementos de serie y una carpeta data limpia, copiada por lista blanca (bin, sounds, locales, docs e icons, sin los respaldos de data\bin).
4. La orden compilar termina comprobando que el ejecutable arranca (--comprobar-arranque) con una carpeta de datos aparte, build\comprobacion_data. entorno.bat verificar comprueba además los complementos, la biblioteca estándar y las licencias de la compilación.
5. Para distribuirlo, ejecute .venv\Scripts\python tools\empaquetar.py. Crea dist\zCommander_v<versión>.zip (la versión sale de app\core\version.py) con el contenido de build\ZCommander dentro de una carpeta zCommander. Omite las carpetas personales de data y los archivos .log, .tmp y .bak, y dice cuántos omitió. Si no hay compilación, termina con código 1.

El manifiesto de tools\zcommander.manifest declara la versión, las rutas largas y el DPI por monitor.

## Publicar una versión

1. Cambie APP_VERSION en app\core\version.py (y la versión de pyproject.toml) y escriba su entrada en data\docs\changelog.md: sus líneas son las novedades que ve la persona al actualizar.
2. Ejecute .venv\Scripts\python tools\publicar.py. Comprueba la entrada del registro de cambios, compila, prueba el arranque con un complemento de ejemplo, comprueba las licencias, crea dist\zCommander_v<versión>.zip, el ZIP de fuentes y dist\version.json firmado con la clave de tools\claves (que nunca sale de esa carpeta).
3. Cuando todo esté bien, ejecute .venv\Scripts\python tools\publicar.py --servidor. Copia primero los paquetes y después version.json a la carpeta sincronizada con el servidor, y comprueba los tamaños.
4. En GitHub (hxebolax/zCommander), cree una publicación (release) con la etiqueta v<versión>, por ejemplo v2.0.1, y suba como recursos, con estos nombres exactos, zCommander_v<versión>.zip, zCommander_v<versión>_fuentes.zip, zCommander_v<versión>_componentes.zip (lo crea publicar.py en dist con los binarios de data\bin; es lo que descarga tools\descargar_componentes.py a quien clona el repositorio) y el mismo dist\version.json firmado. Ese version.json lleva el campo firmado espejos.github con la dirección del ZIP en esa publicación (salvo con --sin-github). Márquela como la última publicación (no como borrador ni como versión preliminar): las instalaciones leen https://github.com/hxebolax/zCommander/releases/latest/download/version.json.

El actualizador de la aplicación lee, según el «Origen de las actualizaciones» de Preferencias, https://xebolax.synology.me/zCommander/version.json, el version.json de la última publicación de GitHub, los dos (gana la versión más nueva) o una dirección personalizada; con cualquiera comprueba su firma Ed25519 con la clave pública incrustada y descarga el paquete. Con --firmar-complementos y unos ids, publicar.py publica además actualizaciones firmadas de complementos de serie sueltos. Otras opciones: --sin-fuentes, --sin-github, --sin-compilar, --sin-comprobar, --destino y --clave (publicar.py --help).
