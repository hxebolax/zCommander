# zCommander 2.0: documento de diseño

## 0. Cómo leer este documento

Este documento describe todo lo que añade zCommander 2.0 sobre la versión 1.0.0, ya programada y probada (759 pruebas), para revisarlo con ojos nuevos antes de programar y para que cualquier persona o agente pueda programar una parte sin adivinar. Se lee por encabezados.

El diseño de la 1.x está en [diseno.md](diseno.md) (versión 1.5 del documento). **Todo lo que dice sigue vigente** salvo lo que este documento cambia de forma expresa; las referencias «1.x §8.15» remiten a sus secciones. Lo que aquí no se menciona no cambia.

### 0.1 Mapa del documento

- 0 y 1: cómo leer, glosario, cifras comprobadas (0.6), objetivos medibles y alcance.
- 2: licencias y componentes de terceros.
- 3: sistema de complementos.
- 4: sonidos.
- 5 a 7: actualizador de la aplicación, actualizador de componentes y copia de seguridad.
- 8 a 10: comprimidos ampliados, unidades de red y personalización avanzada (núcleo).
- 11 a 13: los 25 complementos de serie generales, el complemento «Nubes» y el complemento «NAS Synology» con su simulador (los 27 complementos de serie).
- 14: cambios en el núcleo 1.x (órdenes, configuración, módulos, ganchos, argumentos).
- 15 a 17: accesibilidad, seguridad y privacidad, compilación y distribución.
- 18 y 19: pruebas y plan de trabajo por bloques.
- 20: riesgos. 21: historial del documento.

### 0.2 Fuentes únicas, anexos e investigación

Igual que en la 1.x (1.x §0.2), lo que cambia a menudo vive en el código y se publica en anexos generados con `python tools/generar_anexos.py`; una prueba falla si no están al día. En la 2.0 los anexos crecen:

- [ordenes.md](ordenes.md): todas las órdenes, las del núcleo y las de los complementos de serie (estas se leen de sus manifiestos). Fuente: `app/ui/ordenes.py` y `plugins/*/manifiesto.toml`.
- [configuracion.md](configuracion.md): todas las claves, también las `plugin.<id>.*`. Fuente: `app/core/configuracion.py` y los manifiestos.
- `data/docs/teclas.md` (lista de teclas) y `data/docs/sonidos.md` (mapa de sonidos, nuevo). Fuente: catálogo de órdenes y catálogo de sonidos.
- `docs/componentes.md` (nuevo): componentes de `data/bin` con versión, licencia, origen y sumas. Fuente: `data/bin/linea_base.json`.
- Interfaces en código nuevas: `app/plugins/api.py` (fachada de complementos), `app/plugins/estado.py` (estados de los complementos y llamadas protegidas), `app/plugins/firma.py` (firma de complementos), `app/services/sonidos/catalogo.py` (eventos de sonido), `app/services/eventos.py` (bus de eventos), `app/plugins/interfaz.py` (lo que la API recibe de la interfaz), `app/services/servicios_nucleo.py` (servicios de la ventana, `VentanaServicios` y `ArranqueInfo`), `app/services/componentes/fichas.py` (fichas de componentes), `app/services/copia/formato.py` (formato `.zcbackup`), `app/services/confirmaciones.py` (confirmaciones silenciables), `app/ui/paginas_propias.py` (páginas propias de Preferencias) y la tabla `main.py` de 14.8 (puntos de entrada del arranque).
- Investigación en la que se apoya: [investigacion/plugins.md](investigacion/plugins.md), [investigacion/nubes.md](investigacion/nubes.md), [investigacion/rclone.md](investigacion/rclone.md), [investigacion/synology.md](investigacion/synology.md), [investigacion/comprimidos-y-red.md](investigacion/comprimidos-y-red.md), [investigacion/socialrss-youtubero.md](investigacion/socialrss-youtubero.md) y [investigacion/binarios-descargados.md](investigacion/binarios-descargados.md). Este documento decide; la investigación justifica. Si se contradicen, manda este documento.

### 0.3 Agentes y plantillas

Como la 1.x (1.x §0.3), se usan los agentes de `E:\Antigravity\Agentes\agentes` con las convenciones de `E:\Antigravity\Agentes\compartido\perfil-desarrollador.md`. Sus plantillas se copian al proyecto; el proyecto no depende de esa carpeta para funcionar. En la 2.0 entran:

- **actualizador**: `app/services/actualizador.py`, `app/ui/dialogo_actualizacion.py`, `tools/firmar_version.py` y sus pruebas (sección 5).
- **complemento-nvda**: `nvda_addon/`, `tools/construir_complemento.py`, `app/ui/instalar_complemento.py`, `app/ui/senales_nvda.py` (sección 10.16).
- **red-http**: se adoptan sus **reglas** (tiempos de espera siempre, reintentos solo de GET, respeto de `Retry-After`, mensajes en español, URL redactadas en el registro, descargas a `.parcial` verificadas con tamaño y SHA-256), pero **no su dependencia** `requests`: `app/core/red.py` y `app/core/descargas.py` son módulos nuevos sobre `urllib.request` y `http.client` de la biblioteca estándar (la descarga parte del código de la plantilla del actualizador, que ya es solo biblioteca estándar: `_abrir` solo https con tiempo de espera y control de redirecciones, y `descargar` con `.parcial`, `Range`, el caso 416 y el tope de tamaño), con el almacén de certificados de Windows (`ssl.create_default_context()` lo carga en Windows) y el proxy del sistema (`urllib.request.getproxies()`). Motivo: ningún paquete nuevo en tiempo de ejecución, y la misma pila que ya proponen nubes.md y synology.md.
- **configuracion**, **accesibilidad-wx**, **hilos-y-tareas**, **pruebas** y **documentacion-usuario**: siguen como en la 1.x; la 2.0 añade claves, pantallas, tareas, pruebas y documentos con sus reglas (sobre todo: etiqueta creada antes de cada control, `revisar_teclado` en cada ventana, nada lento en el hilo de la interfaz, nada de `data/` real ni de Internet en las pruebas).

### 0.4 Convenciones de escritura

Las de la 1.x (1.x §0.4). Además:

- «Complemento» y «plugin» son sinónimos; la interfaz dice siempre «complemento».
- Las órdenes de complementos se escriben con su id completo: `zc.reproductor:reproducir`.
- Las claves de configuración de un complemento se escriben `plugin.<id>.<clave>` (sección 3.6).
- «N2», «PL», «SO»... son bloques del plan de trabajo (sección 19). «N2» es el núcleo 2.0: un solo bloque que fija los contratos y hace todos los enganches en la 1.x antes de que empiece ningún otro (19.1).
- «—» en la columna Tecla de una tabla significa «sin tecla de fábrica» (la orden está en menús y en la paleta, y se le puede dar tecla en el mapa de teclas). La única orden sin tecla ni menú es `traer_al_frente`, que solo sirve como tecla global (objetivo 2 de 1.2).
- Las teclas de las tablas y fichas se escriben en español para leerlas («Ctrl+Mayús+F5», «Re Pág»); en el código y en los manifiestos van en el formato canónico de `app.services.teclas` (`Ctrl+Shift+F5`, `PgUp`, `Ctrl+Space`).
- En las fichas de los complementos (11 a 13), `datos/…` es la carpeta de datos del complemento (`Anfitrion.datos`, es decir, `data/config/plugins/<id>/`, escribible y que sobrevive a actualizar); los recursos de solo lectura que trae el paquete están en su carpeta `recursos/` (3.3).
- «Versión más alta» compara dos versiones (`2.1.0` es más alta que `2.0.3`); «versión principal» es el primer número (`2` en `2.1.0`), el que cambia cuando algo deja de ser compatible.

### 0.5 Glosario nuevo

Vale el glosario de la 1.x (1.x §0.5). Términos nuevos:

- **Complemento**: paquete de código Python que amplía zCommander por los puntos de extensión de la sección 3.5. Los **de serie** viajan con zCommander en `plugins/` (junto al ejecutable); los **de la persona** se instalan en `data/plugins/`.
- **Complementos de serie**: los 27 que trae zCommander: los 25 generales de la sección 11, «Nubes» (12) y «NAS Synology» (13).
- **Paquete de complemento** (`.zcplugin`, 3.3) y **paquete de sonidos** (carpeta o `.zcsonidos`, 4.6) son cosas distintas; «paquete» a secas no se usa.
- **Manifiesto**: archivo `manifiesto.toml` de un complemento; declara qué aporta sin ejecutar su código.
- **Marcador**: orden, columna, visor, esquema o evento que zCommander conoce por el manifiesto antes de cargar el código del complemento.
- **Activación**: primera carga del código de un complemento, la primera vez que hace falta (carga perezosa). «Activar», «activo» y el estado `ACTIVO` se usan **solo** en este sentido (y «desactivar()», su contrario, al cerrar).
- **Habilitar e inhabilitar**: la preferencia de la persona de usar o no un complemento (gestor, 3.11; clave `complementos.inhabilitados`). Un complemento habilitado puede estar sin activar todavía («Sin cargar todavía»).
- **Sin aceptar**: complemento sin firma que apareció en `data/plugins/` sin pasar por la instalación del gestor (carpeta copiada a mano, carpeta portable sincronizada) o cuyo paquete cambió; no se carga hasta que la persona lo acepta (3.9).
- **API de complementos**: la fachada `app/plugins/api.py`, única parte del código que un complemento puede importar con garantías; tiene versión (`API_VERSION`).
- **Centinela**: archivo `data/cache/plugins/cargando/<id codificado>` (uno por complemento que se está activando) que delata un cierre brusco durante su carga; al arrancar, solo se excluye ese complemento (3.8).
- **Modo seguro**: arranque sin ningún complemento (argumento `--sin-complementos`, Mayús pulsada al arrancar u orden «Reiniciar sin complementos»). Un centinela no activa el modo seguro.
- **Componente**: programa, biblioteca o paquete que vive en `data/bin/<id>/` y tiene su ficha en `data/bin/componentes.json`: los de terceros (rclone, libarchive, 7za, FFmpeg) y el complemento de NVDA que genera zCommander (`nvda`, no actualizable aparte).
- **ContextoComplemento**: lo que recibe el manejador de una orden de complemento (3.7): paneles de solo consulta, argumento, anunciar y sonar; sin la ventana ni los servicios internos.
- **Línea base**: versiones de los componentes que trae y ha probado cada versión de zCommander (`data/bin/linea_base.json`, solo lectura).
- **Paquete de sonidos**: carpeta con un `paquete.json` y un `.wav` por evento.
- **Evento de sonido**: algo que puede sonar, con id, nombre, descripción, categoría, prioridad y archivo (sección 4.2).
- **Bus de eventos**: `app/services/eventos.py`; avisa de lo que pasa en la aplicación (cambio de carpeta, fin de operación...) a quien se suscriba: complementos, macros, reglas. Solo informa: nada que deba ocurrir en un orden preciso (la grabación de macros, por ejemplo) depende de él.
- **Copia de seguridad**: archivo `.zcbackup` con la configuración elegida de la persona (sección 7). Un **perfil exportable** (`.zcperfil`) es una copia limitada y siempre sin secretos.
- **Macro**: lista de órdenes del catálogo con argumentos, grabable y editable (sección 10.1).
- **Espacio de trabajo**: disposición completa de la ventana guardada con nombre (sección 10.9).
- **Esquema de teclas**: juego de teclas de fábrica alternativo (Norton, Total Commander, Far, Explorador) sobre el que se aplican las teclas personalizadas.
- **Raíz «Red»**: lista virtual de unidades de red, conexiones, servidores y equipos (sección 9).
- **rcd**: `rclone rcd`, el motor de nubes que corre como proceso hijo oculto (sección 12).
- **DSM**: sistema operativo de los NAS Synology; **File Station** es su gestor de archivos, que zCommander usa como origen `synology://`.
- **Simulador DSM**: servidor DSM falso local que responde como el NAS real (sección 13.9).
- **Modo solo lectura** (NAS): estado por defecto de cada NAS en zCommander; bloquea en el cliente toda llamada que no esté en la lista blanca de lectura.
- **Ed25519**: algoritmo de firma con el que se firman el manifiesto de actualización y, si se quiere, los complementos (es obligatoria solo para un `zc.*` que esté en `data/plugins/`, es decir, una actualización de un complemento de serie, 3.9).
- **AES-256-GCM** y **scrypt**: cifrado autenticado y derivación de una clave a partir de una contraseña; los usan las copias de seguridad y el complemento de cifrado.
- **SPDX**: identificador normalizado de licencia (`GPL-3.0-or-later`).
- **Job Object**: objeto de Windows que mata los procesos hijos (rclone, FFmpeg, 7za) si zCommander muere.
- **OAuth**: autorización por el navegador para que una aplicación use una cuenta de nube sin conocer su contraseña.
- **WinFsp**: controlador de Windows, que instala la persona, necesario para montar una nube como letra de unidad.
- **Oferta de fuentes**: aviso que la GPL y la LGPL obligan a dar con los binarios: dónde conseguir el código fuente exacto.

### 0.6 Cifras comprobadas

Recuento hecho con un script sobre este documento (tablas y fichas; borrador 4) y contrastado con `app/ui/ordenes.py`, `app/core/configuracion.py` y `data/docs/teclas.md`. Los anexos generados (0.2) son la cifra oficial cuando existan; si no coinciden con esta tabla, se corrige la tabla.

| Qué | Núcleo | Complementos de serie | Total |
|---|---|---|---|
| Órdenes nuevas | 45 (14.1.2; `complemento_recargar` solo existe en modo desarrollo) | 123: 89 de la sección 11, 20 de Nubes (12.6) y 14 del NAS (13.10) | 168 |
| Órdenes de la 1.x que siguen | 181 | — | 181 |
| Claves de configuración nuevas | 54 (14.3; la nueva es `paneles.lectura`, 10.5) | 131 `plugin.<id>.*` (11 a 13: 108 de la sección 11, 14 de Nubes y 9 del NAS) | 185 |
| Claves de la 1.x que desaparecen por migración | 4 (14.3) | — | 4 |
| Eventos de sonido | 122 (más 11 variantes de `op.progreso`, 4.2) | 31 (11 a 13) | 153 |
| Bloques del plan | N2, PL, SO, AC, CO, CS, CM, RD, PE, NV, LI, P1 a P5, NU, NS y DO (N2 vuelve a ser un solo bloque, 19.1) | | 19 |

## 1. Objetivos medibles y alcance de la 2.0

### 1.1 Qué resuelve la 2.0

La 1.0 es un gestor de doble panel completo y accesible, pero cerrado: todo lo que no está en el núcleo exige otro programa (con otra curva de accesibilidad), no se actualiza solo, no tiene copias de su configuración, no lee RAR ni las nubes, y sus avisos sonoros son tres. La 2.0 lo abre (complementos), lo mantiene vivo (actualizaciones de la aplicación y de sus componentes), protege la configuración de la persona (copias de seguridad), amplía comprimidos y red, da un sistema de sonidos completo y añade 27 complementos de serie pensados para personas ciegas (secciones 11 a 13).

### 1.2 Objetivos medibles

zCommander 2.0 se da por bueno si:

1. Cada tarea nueva de las secciones 3 a 13 se completa solo con teclado y con NVDA, JAWS y Narrador, siguiendo la parte 2.0 de `docs/pruebas-manuales.md` (bloque DO), sin mirar la pantalla.
2. Todas las órdenes del catálogo, las del núcleo y las de los 27 complementos de serie, tienen manejador y tecla o menú (salvo `traer_al_frente`, que solo existe para las teclas globales, 10.15), y ninguna tecla de fábrica se repite en un mismo ámbito con todos los complementos de serie habilitados y con cada uno de los cuatro esquemas de teclas (prueba automática).
3. Cada ventana y diálogo nuevos, también los de los complementos de serie, pasan `revisar_teclado` sin problemas (prueba automática).
4. Las pruebas automáticas pasan (las 759 de la 1.x y las nuevas de la sección 18) y `ruff check` no da errores.
5. Con los 27 complementos de serie instalados y habilitados, la ventana aparece en menos de 1,5 s (el objetivo de la 1.x) y la importación de los complementos con `activacion = ["al_arrancar"]` suma menos de 100 ms medidos con `medicion_arranque` (prueba marcada como lenta).
6. Un complemento que lanza una excepción al importarse, al activarse o en un manejador no impide arrancar ni usar el resto; tras 3 fallos deja de usarse en la sesión (estado `FALLIDO`); un cierre brusco durante su carga se detecta en el arranque siguiente (pruebas automáticas con los complementos rotos de `tests/datos/plugins/`).
7. Una actualización de la aplicación se instala y, si la versión nueva no confirma su arranque, se vuelve sola a la anterior (pruebas de la plantilla del actualizador, más una prueba manual con la publicación real en `https://xebolax.synology.me/zCommander/`).
8. Un componente actualizado que no pasa su orden de prueba vuelve solo a la versión anterior, y «Restaurar los componentes originales» deja exactamente la línea base (mismas sumas SHA-256).
9. Una copia de seguridad creada y restaurada en una carpeta `data` vacía reproduce byte a byte los archivos elegidos, y los secretos se recuperan solo con la contraseña correcta (prueba automática).
10. Cada evento del catálogo de sonidos (los del núcleo y los de los complementos de serie) tiene archivo en cada uno de los 5 paquetes de serie; `tools/generar_sonidos.py` genera dos veces los mismos bytes; pedir un sonido tarda menos de 5 ms en el hilo de la interfaz (pruebas automáticas).
11. zCommander lista y extrae RAR, RAR5, CAB, ISO, LHA, cpio, deb, rpm, xar, zipx, ZIP con AES, 7z sin cifrar, `.tar.zst` y flujos sueltos (`.gz`, `.bz2`, `.xz`, `.zst`) con los datos de prueba de la sección 18.
12. La raíz «Red» muestra unidades, conexiones sin letra y servidores recientes en menos de 1 s, y los equipos de la red a medida que se descubren, sin congelar la interfaz; Escape cancela el descubrimiento.
13. La compilación arranca en un Windows sin Python, carga un complemento de prueba (`--comprobar-arranque --complemento-prueba <carpeta>`), no contiene ninguna de las DLL no libres de accessible_output2 y su carpeta `data/docs/licencias/` está completa (`tools/comprobar_licencias.py` devuelve 0).

### 1.3 Qué incluye la 2.0

1. Licencia GPL-3.0-or-later para todo zCommander, avisos de terceros y oferta de fuentes (sección 2).
2. Sistema de complementos con API versionada, carga perezosa, protección, configuración propia por complemento, gestor accesible y herramientas para autores (sección 3).
3. Sistema de sonidos con un único catálogo de eventos, motor sin dependencias, preferencias, paquetes con manifiesto, 5 paquetes de serie generados y mapa de sonidos (sección 4).
4. Actualizador de la aplicación firmado y con vuelta atrás (sección 5).
5. Actualizador de los componentes de `data/bin` con respaldo, prueba y vuelta atrás (sección 6).
6. Copia de seguridad y restauración de la configuración, con secretos cifrados por contraseña (sección 7).
7. Comprimidos ampliados: zstd, libarchive, 7za y el 7-Zip de la persona (sección 8).
8. Unidades de red completas con la raíz «Red» navegable (sección 9).
9. Personalización avanzada: macros, perfiles propios, vistas por carpeta, menús y barras configurables, esquemas de teclas, alias, espacios de trabajo, reglas, teclas globales, complemento de NVDA y más (sección 10).
10. Los 25 complementos de serie (sección 11), el complemento «Nubes» (sección 12) y el complemento «NAS Synology» con su simulador (sección 13).

### 1.4 Fuera de alcance de la 2.0 (con motivo)

- **Índice remoto (tienda) de complementos**: exige un servidor con revisión, firmas y moderación que hoy no hay quien mantenga. Se instala desde archivo, y cada complemento puede declarar su propia URL de actualización (3.10). El formato del índice de plugins.md 2.8 queda como base para el futuro.
- **Complementos en un proceso aparte**: coste alto (comunicación entre procesos, cx_Freeze, interfaz) para una protección que en Python solo es parcial; se mitiga con llamadas protegidas, centinela y modo seguro (3.8).
- **Complementos de Total Commander (WCX, WFX, WLX, WDX)**: siguen fuera por el motivo de la 1.x (1.x §1.4).
- **Teclas en dos pasos** (prefijo y letra): complican el despachador, el modo de ayuda de teclado y la lista de teclas; las órdenes sin tecla están en menús y paleta, y se les puede dar tecla en el mapa de teclas o con una macro.
- **Configuración distinta por lector de pantalla** (plugins.md 5.12) y **sincronizar la configuración entre equipos** (5.20): los perfiles propios y las copias de seguridad cubren el caso con menos riesgo.
- **Editor de temas** (5.14) y **filtros guardados con tecla** (5.16): los temas de la 1.x, el alto contraste de Windows y las macros cubren lo esencial; se aplazan.
- **Montar ISO o VHD como letra de unidad**, **dispositivos portátiles MTP**, **recuperar archivos borrados**, **editor del Registro como panel** y **terminal integrado**: valen los motivos de plugins.md 4.1.
- **Elegir el dispositivo de audio de los sonidos**: `PlaySound` usa el dispositivo predeterminado de Windows; elegir otro exigiría una biblioteca de audio que no es de la biblioteca estándar.
- **Traducciones**: como en la 1.x, todo va marcado con `_()` y cada complemento tiene su dominio, pero solo se entrega el español.
- **Descripción de imágenes con la IA local de Windows**: exige PC Copilot+ e identidad de paquete (plugins.md 11); el complemento de imágenes usa un servicio que configura la persona.
- **Bandeja del sistema**: sigue fuera (1.x §1.4).

### 1.5 Qué cambia de la 1.x §1.4

- «RAR: no hay biblioteca libre fiable» deja de valer: libarchive lo lee sin cifrar y el 7-Zip de la persona, si lo tiene, también cifrado (sección 8).
- «TAR con zst» entra (sección 8).
- «Actualización automática por Internet» entra (secciones 5 y 6).
- Los complementos propios en Python entran (sección 3); los de Total Commander siguen fuera.
- «Miniaturas y visor de imágenes» entra solo como visor ampliable del complemento de imágenes (11.11); el panel sigue sin miniaturas.
- «Límite de velocidad de copia» entra solo para las nubes (límites de rclone, 12.9); la copia del núcleo sigue sin límite.

## 2. Licencias y componentes de terceros

### 2.1 Licencia de zCommander

- Todo zCommander (núcleo, herramientas, complementos de serie, simulador DSM, complemento de NVDA y documentos) se publica bajo **GPL-3.0-or-later**.
- `LICENSE` en la raíz del repositorio con el texto íntegro de la GPL-3.0 (el de gnu.org, sin cambios). Se copia a `data/docs/licencias/zCommander/GPL-3.0.txt` para la distribución.
- Cada archivo de código propio (`.py`, `.bat`, `.toml` de manifiestos) empieza con dos líneas de comentario: `SPDX-License-Identifier: GPL-3.0-or-later` y `Copyright (C) 2026 hxebolax y colaboradores`; el titular se fija en `app/core/version.py` como `TITULAR = "hxebolax y colaboradores"` (decidido en 21.2.1; lo añade N2). `tools/comprobar_licencias.py` falla si falta en algún archivo propio.
- Los complementos que se distribuyan junto a zCommander deben ser GPL-3.0 o compatibles (MIT, BSD, Apache-2.0, ISC, CC0, LGPL, GPL-2.0-or-later, MPL-2.0), porque se cargan en el mismo proceso y forman una obra combinada (plugins.md 2.8). El gestor muestra la licencia de cada complemento y avisa si no está en esa lista; en los instalados desde archivo no lo impide: decide la persona.

### 2.2 Componentes de terceros

`tools/generar_licencias.py` crea `data/docs/licencias/` con una carpeta por componente (texto de la licencia y avisos de copyright, tomados de los `dist-info`, de los paquetes de MSYS2 y de los paquetes oficiales) y `data/docs/licencias/LEEME-LICENCIAS.md` con las tablas de abajo. `tools/comprobar_licencias.py` compara esa carpeta con `requirements.txt`, `data/bin/linea_base.json` y las carpetas `lib/` de los complementos de serie, y falla si falta algo.

Componentes de Python, dentro del proceso (versiones de 1.x §15):

| Componente | Licencia | Obligación principal |
|---|---|---|
| Python 3.15 y su biblioteca estándar | PSF-2.0 (con terceros permisivos) | Avisos |
| wxPython 4.3.2 | LGPL-2.0+ con la excepción de wxWindows | Avisos y oferta de fuentes |
| pywin32 312, comtypes, Send2Trash, Markdown | PSF, MIT, BSD-3, BSD-3 | Avisos |
| paramiko 5.1.0 y py7zr 0.11.3 | LGPL-2.1 y LGPL-2.1+ | Avisos y oferta de fuentes |
| cryptography (en la 1.x llega solo como dependencia de paramiko; la 2.0 la fija con su versión en `requirements.txt` porque pasa a ser obligatoria), bcrypt, PyNaCl, cffi y demás dependencias | Apache-2.0, BSD, MIT, ISC | Avisos |
| accessible_output2 0.17 (solo su código Python y `nvdaControllerClient64.dll`) y sus dependencias `libloader` y `platform_utils` | MIT; nvdaControllerClient LGPL-2.1 | Avisos y oferta de fuentes de nvdaControllerClient |
| cx_Freeze (base congelada) y runtime de Visual C++ | PSF-2.0 y MIT; «Biblioteca del Sistema» | Avisos |

Componentes de `data/bin/<id>/` (ya descargados, verificados e instalados el 8 de noviembre de 2026; origen y sumas en binarios-descargados.md; fichas completas en 6.2):

| id | Componente | Versión base | Licencia | Cómo se usa |
|---|---|---|---|---|
| `rclone` | `rclone.exe` | 1.76.0 | MIT | Proceso aparte (`rclone rcd`); complemento Nubes |
| `libarchive` | `libarchive-13.dll` y 7 DLL dependientes de MSYS2 UCRT64: `libb2-1`, `libbz2-1`, `libiconv-2`, `liblz4`, `liblzma-5`, `libzstd`, `zlib1` (usa CNG y XmlLite de Windows, sin OpenSSL ni libgcc) | 3.8.11 (paquete 3.8.11-1) | BSD-2 (libarchive), Zlib, bzip2, 0BSD (xz), BSD-2 (lz4), BSD-3 (zstd), CC0 (libb2), LGPL-2.1+ (libiconv) | Dentro del proceso por `ctypes` (núcleo, sección 8) |
| `7za` | `7za.exe` de 7-Zip Extra, sin unRAR | 26.06 | LGPL-2.1+ y BSD-3 | Proceso aparte, opcional (sección 8) |
| `ffmpeg` | `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe` y 7 DLL (`avcodec-63`, `avdevice-63`, `avfilter-12`, `avformat-63`, `avutil-61`, `swresample-7`, `swscale-10`), compilación GPL «shared» de FFmpeg-Builds | 9.0.2 (n9.0) | GPL-3.0-or-later | Proceso aparte (complementos Conversor multimedia, Reproductor y Lectura en voz) |
| `nvda` | Complemento de zCommander para NVDA (`zCommander-<versión>.nvda-addon`), generado por `tools/construir_complemento.py` | La de zCommander | GPL-3.0-or-later | Lo instala la persona en su NVDA; no se actualiza aparte (6.2) |

Bibliotecas vendorizadas en complementos de serie (`plugins/<carpeta>/lib/`, sección 11): mutagen (GPL-2.0-or-later), pypdf (BSD-3) y dulwich (Apache-2.0 o GPL-2.0-or-later), todas Python puro; y, solo si existen ruedas para Python 3.15 al implementar, Pillow (MIT-CMU) y `winrt-*` de pywinrt (MIT). Todas compatibles con GPL-3.

### 2.3 Lo que no se distribuye

- **DLL no libres de accessible_output2**: `SAAPI32.dll` (System Access), `dolapi.dll` (Dolphin), `PCTKUSR.dll` y `PCTKUSR64.dll` (PC-Talker), `ZDSRAPI.dll` y `ZDSRAPI_x64.dll` (Zhengdu). `setup_cx.py` las borra de la compilación, junto con `nvdaControllerClient32.dll` (la compilación es de 64 bits), y `tools/comprobar_licencias.py` falla si alguna aparece. Siguen NVDA (`nvdaControllerClient64.dll`, LGPL), JAWS (por COM, sin DLL), SAPI y las notificaciones UIA. `app/ui/accesibilidad/voz.py` ya crea en la 1.x solo NVDA, JAWS y SAPI5, cada una en su propio `try` (`_salida_ao2`); solo queda una rama `else` a la que nunca se llega que importa `accessible_output2.outputs.auto.Auto`. N2 borra esa rama y añade una prueba que simula la ausencia de las DLL no libres.
- **7z.dll y 7z.exe completos, 7-Zip-zstd, NanaZip y UnRAR**: contienen código con la restricción de unRAR o no libre (comprimidos-y-red.md A.3). Si la persona tiene 7-Zip instalado, zCommander lo usa sin distribuirlo (8.5).
- **WinFsp**: lo instala la persona si quiere montar nubes como letra de unidad; zCommander solo lo detecta (12.8).
- **Everything, `es.exe` y su SDK**: licencia sin aclarar; el complemento de búsqueda instantánea habla con el Everything que ya tenga instalado la persona (11.5).
- Los PDF de Synology de `adjuntos/synology/docs/` (propietarios) y los repositorios de `adjuntos/` no entran ni en la compilación ni en el ZIP de fuentes; `.gitignore` excluye `adjuntos/synology/docs/` y `adjuntos/synology/repos/`.

### 2.4 Oferta de fuentes

- La GPL-3 (§6) obliga a dar la Fuente Correspondiente de zCommander (los `.pyc` de la compilación no son fuente) y de FFmpeg (compilación GPL); la LGPL, la de wxPython, paramiko, py7zr, nvdaControllerClient, libiconv y 7za.
- `tools/publicar.py` crea, junto al paquete de cada versión, `zCommander_v<versión>_fuentes.zip` con el repositorio de esa versión (sin `adjuntos/`, sin `tools/claves/`, sin datos) y lo publica en `https://xebolax.synology.me/zCommander/`.
- `tools/fuentes_terceros.py` descarga, con permiso expreso de quien publica, las fuentes exactas de los componentes LGPL y GPL de la versión (sdist de PyPI, paquetes `.src.tar.zst` de MSYS2, `7z2606-src.7z`, el código de FFmpeg n9.0 de la compilación usada y los guiones de FFmpeg-Builds de esa fecha) y las deja en `%USERPROFILE%\SynologyDrive\web\zCommander\fuentes\<versión>\`, que se publica como `https://xebolax.synology.me/zCommander/fuentes/<versión>/`. Se conservan al menos tres años después de la última versión que los use.
- `data/docs/licencias/OFERTA-DE-FUENTES.md` dice, en español, qué se puede pedir, dónde está y que la oferta vale tres años; lo enlaza «Acerca de».

### 2.5 «Acerca de»

El diálogo de la 1.x (`app/ui/acerca_de.py`) muestra en un texto de solo lectura: nombre, versión, titular, la frase «Este programa es software libre: puede redistribuirlo y modificarlo según la Licencia Pública General de GNU, versión 3 o posterior. Se distribuye sin ninguna garantía.» y la dirección de las fuentes. Botones: «Ver la &licencia» (abre `GPL-3.0.txt` en el visor de ayuda), «Componentes de &terceros» (abre `LEEME-LICENCIAS.md`), «&Oferta de fuentes», «Co&piar la información» y «&Cerrar». Si el complemento Nubes ha montado alguna vez una unidad con WinFsp, se añade el aviso que exige su excepción FLOSS («WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos», con enlace a su repositorio; rclone.md 4.8).

## 3. Sistema de complementos

Se adopta el diseño de plugins.md sección 2 con las decisiones de abajo. Lo que plugins.md propone y aquí no se recoge (índice remoto, proceso aparte, proveedor externo tipo extfs) queda fuera (1.4).

### 3.1 Principios

1. Un complemento nunca empeora la accesibilidad ni la estabilidad de zCommander.
2. Lo que se ve (órdenes, menús, teclas, columnas, preferencias, sonidos, ayuda) se declara en el manifiesto; el código se carga cuando se usa.
3. La API es pequeña, estable, en español y versionada; lo que no está en `app/plugins/api.py` no está garantizado.
4. Mismas reglas que el núcleo: capas (`services` sin `wx`), trabajo largo en el motor de operaciones o en `GestorTareas`, errores `ErrorArchivos` con mensaje en español, anuncios por niveles, preguntas por el `Decisor`.
5. La persona decide: ve qué instala (autor, licencia, firma, permisos, archivos), puede inhabilitar, configurar y desinstalar, y puede arrancar sin complementos.

### 3.2 Carpetas

| Carpeta | Contenido | Quién escribe |
|---|---|---|
| `<raíz>/plugins/<carpeta>/` | Complementos de serie (junto a `main.py` o al `.exe`; fuera de `data`) | Solo una actualización de zCommander |
| `data/plugins/<id>/` | Complementos instalados por la persona | El gestor |
| `data/plugins/.pendientes/<id>/` | Instalaciones y actualizaciones que se aplican al reiniciar (las que no se pueden activar en caliente, 3.10) | El gestor |
| `data/plugins/.anteriores/<id>-<versión>/` | Versión anterior, para «Volver a la versión anterior» | El gestor |
| `data/config/plugins/<id>.json` | Configuración del complemento (3.6) | La API |
| `data/config/plugins/<id>/` | Datos del complemento que sobreviven a actualizar y desinstalar | El complemento, por la API (`Anfitrion.datos`) |
| `data/cache/plugins/<id>/` | Cachés que se pueden borrar | El complemento (`zc.cache`) |
| `data/cache/plugins/indice.json` | Manifiestos ya validados (fecha y tamaño de cada archivo); no sustituye a la comprobación de firma (3.9) | El gestor |
| `data/cache/plugins/cargando/<id codificado>` | Centinelas: un archivo por complemento que se está activando (3.8) | El cargador |
| `data/config/plugins/claves.json` | Claves públicas de confianza y clave fijada por id (3.9) | El gestor |
| `data/cache/pycache/` | `.pyc` del código de zCommander desde el código fuente (`sys.pycache_prefix`) y de los complementos de serie, estos solo comprobados por hash (`CHECKED_HASH`, 3.9); los de `data/plugins/` nunca usan `.pyc` | Python y el cargador |

- El nombre de la carpeta no importa: manda el `id` del manifiesto. Los de serie usan el nombre corto (`plugins/synology/` tiene `id = "zc.synology"`). Si el mismo `id` está en `plugins/` y en `data/plugins/`, gana la versión más alta (así un complemento de serie se puede actualizar sin tocar la carpeta del programa), siempre que la copia de `data/plugins/` pase la comprobación de firma de 3.9: un `zc.*` sin la firma del proyecto no sustituye nunca al de serie. Dos carpetas con el mismo `id` en la misma ubicación son un error de manifiesto para las dos (`ERROR_MANIFIESTO`, «El id zc.x está repetido en dos carpetas»): no se carga ninguna.
- **Confianza por ubicación, solo para la lista de serie**: `app/plugins/serie.py` (sin wx) tiene `SERIE: dict[str, str]` (id → versión de los 27 complementos de serie; lo genera `tools/generar_anexos.py` desde los manifiestos y `test_anexos_al_dia` comprueba que está al día) y `SUMAS: dict[str, dict[str, str]] | None` (id → ruta relativa → SHA-256 de cada archivo), que importa de `app/plugins/serie_sumas.py` si existe y si no vale `None`. `serie_sumas.py` solo existe en la versión compilada: lo genera `setup_cx.py` con las sumas de los archivos que copia a `build/ZCommander/plugins/`, lo congela con el paquete `app` y lo borra del código fuente al terminar (está en `.gitignore`). Un complemento de `<raíz>/plugins/` es «Oficial» sin firma **solo si su id y su versión están en `SERIE`** (y, en la compilada, sus archivos coinciden con `SUMAS`, comprobado al importar, 3.9). Cualquier otra carpeta de `<raíz>/plugins/` (copiada a mano, dejada por otro programa) se trata como si estuviera en `data/plugins/`: firma, clave fijada o consentimiento (3.9), y el gestor avisa «Este complemento está en la carpeta del programa y se borrará al actualizar zCommander; instálelo desde el gestor», porque la actualización sustituye entera esa carpeta (5.3). La firma del proyecto solo se exige a los `zc.*` de `data/plugins/` (actualizaciones sueltas de los de serie). El modelo de amenaza está en 16.
- `paths.py` gana `ruta_plugins_serie()`, `ruta_plugins_usuario()`, `ruta_cache()`, `ruta_config_plugins()` y `ruta_cache_plugins()`.

### 3.3 Paquete `.zcplugin` y manifiesto

El paquete es un ZIP con el contenido de la carpeta del complemento en la raíz (sin carpeta contenedora), nombres en UTF-8:

```
manifiesto.toml          obligatorio
__init__.py y módulos    el código (entrada declarada en el manifiesto)
lib/                     dependencias vendorizadas (Python puro o .pyd cp315-win_amd64), sin tocar sys.path (3.4)
doc/es/leeme.md          ayuda (la abre el visor de ayuda con F1)
doc/es/cambios.md        novedades del complemento
sonidos/<nombre>.wav     sonidos propios por defecto; <nombre> es la parte del id de evento tras «:»
recursos/                recursos de solo lectura (catálogos, plantillas, guiones)
LICENSE                  obligatorio
firma.ed25519            opcional (3.9)
```

Los datos que el complemento escribe nunca van en su carpeta (se sustituye al actualizar y la de serie es de solo lectura): van en `Anfitrion.datos` (`data/config/plugins/<id>/`) o en `Anfitrion.cache`.

Manifiesto (TOML, leído con `tomllib`). Campos de nivel superior:

| Campo | Obligatorio | Valor |
|---|---|---|
| `formato` | sí | `1` (versión del formato del manifiesto) |
| `id` | sí | `[a-z][a-z0-9]*(_[a-z0-9]+)*(\.[a-z][a-z0-9]*(_[a-z0-9]+)*)+`, por ejemplo `zc.reproductor` o `ana.utilidades` (sin `__` ni `_` al final de un tramo, para que el nombre de módulo de 3.4 no sea ambiguo). `zc.*` está reservado a los oficiales: en `<raíz>/plugins/` valen sin firma solo los de la lista `serie.SERIE` (confianza por ubicación, 3.2) y en cualquier otro caso solo con la firma del proyecto (3.9) |
| `bloque` | no | Solo complementos de serie: bloque del plan que lo programa (`P1` a `P5`, `NU`, `NS`); lo usa la prueba de provisionales (19.4). Se ignora en los demás |
| `nombre`, `descripcion` | sí | Texto en español |
| `version` | sí | `mayor.menor.parche` |
| `autor`, `licencia` | sí | `licencia` en SPDX |
| `web`, `codigo_fuente` | no | URL https |
| `api_minima`, `api_probada` | sí | `"1.0"`; se carga si `api_minima <= API_VERSION` y `api_probada >= API_COMPATIBLE_DESDE` |
| `plataforma` | no | `cualquiera` (por defecto) o `win_amd64`; con `.pyd`, además `python = "3.15"` |
| `entrada` | sí | `"modulo:Clase"` relativo a la carpeta |
| `activacion` | no | Disparadores **además** de los marcadores: `al_arrancar`, `evento:<nombre>` (activa al emitirse ese evento del bus). Por defecto `[]`. Cualquier marcador declarado (orden, columna, visor, esquema, comprimido, info, búsqueda, extractor, máscara, acción de error, unidades, línea de órdenes) activa el complemento la primera vez que el núcleo lo usa, sin tener que nombrarlo aquí (3.4) |
| `permisos` | no | Lista de 3.9 |
| `nivel` | no | `novato`, `intermedio` o `avanzado` (nivel por defecto de sus órdenes, 10.11) |
| `ayuda`, `cambios` | no | Rutas dentro del paquete (por defecto `doc/es/leeme.md`, `doc/es/cambios.md`) |
| `url_actualizacion` | no | URL https de un JSON de actualización (3.10) |
| `prueba` | no | Id corto de la orden que ejecuta `--comprobar-arranque --complemento-prueba` (14.8) para saber si el complemento funciona; por defecto, la primera de `[[ordenes]]`. Debe poder ejecutarse sin argumento y sin preguntar nada |
| `dialogo_preferencias` | no | `true` si el complemento tiene un diálogo de configuración propio (3.6): el botón «Abrir la configuración avanzada...» aparece sin activar el complemento. Por defecto `false` |
| `[requiere]` | no | `complementos = ["zc.metadatos >= 1.0"]`, `componentes = ["ffmpeg"]` |
| `[recomienda]` | no | Igual que `requiere`, pero no impide cargar: activa funciones si están |

Tablas de contribuciones (cada una opcional y repetible con `[[...]]`):

| Tabla | Campos | Punto de extensión (3.5) |
|---|---|---|
| `[[ordenes]]` | `id`, `etiqueta`, `ayuda`, `ambito` (`panel` o `global`), `menu` (`complementos` por defecto, `archivos`, `comandos`, `herramientas`, `contextual`, `ninguno`; dónde se colocan, 14.2), `teclas` (lista en formato canónico), `tipo` (`normal` o `casilla`), `casilla_defecto` (estado que muestra la casilla mientras el complemento no está activado; no por defecto), `disponible_si` (patrón de nombre con el que la orden aparece habilitada en el menú contextual sin activar el complemento; vacío = siempre), `nivel`, `paleta` (sí por defecto), `tecla_global` (puede usarse como tecla global, 10.15), `argumento` (`""` sin argumento, por defecto; `ruta`, `patron`, `texto` o `json`: lo que graba una macro y recibe `ContextoComplemento.argumento`, 10.1) | Órdenes |
| `[[columnas]]` | `id`, `titulo`, `patrones`, `tipo` (`texto`, `numero`, `tamano`, `fecha`, `duracion`), `lenta` | Columnas |
| `[[visores]]` | `id`, `nombre`, `patrones`, `vista_rapida` (sí por defecto), `prioridad`, `ventana` (no por defecto: el visor abre una ventana propia en lugar de devolver un `Documento`) | Visores |
| `[[info]]` | `nombre`, `patrones` | Líneas de «Información del elemento» |
| `[[unidades]]` | `texto`, `direccion`, `descripcion` (textos fijos que el selector muestra sin activar el complemento); `dinamicas = true` si además hay que preguntar al complemento por más: entonces el complemento se activa en segundo plano la primera vez que se abre el selector en la sesión, y sus entradas dinámicas se añaden cuando llegan (3.4) | Entradas del selector de unidades |
| `[[internas]]` | `nombre`, `ayuda` | Órdenes internas de la línea de órdenes (`zc <nombre> ...`, 10.8) |
| `[[esquemas]]` | `prefijo`, `nombre` | Proveedores VFS por dirección |
| `[[comprimidos]]` | `extensiones`, `nombre`, `escritura` | Proveedores de comprimidos |
| `[[busqueda]]` | `id`, `nombre` | Proveedores de búsqueda |
| `[[extractores]]` | `patrones`, `nombre` | Texto para buscar por contenido |
| `[[mascaras]]` | `marcador` con prefijo propio en mayúsculas y dos puntos, como `[EXIF:fecha]` o `[MP3:artista]`; `descripcion`. Un marcador que coincide con uno de la 1.x (1.x §8.14: `[N]`, `[E]`, `[C]`, `[Y]`, `[y]`, `[t]`...) o con el de otro complemento ya registrado se rechaza al validar y al registrar (gana el que ya estaba y el gestor lo dice) | Renombrado múltiple |
| `[[acciones_error]]` | `id`, `etiqueta`, `ayuda`, `codigos_windows` (lista de enteros: el botón sale sin activar el complemento solo si el `codigo_windows` de la pregunta está en la lista; vacía, por defecto, = cualquier error; 3.4) | Acciones extra en la pregunta de error |
| `[[eventos]]` | `nombre` | Eventos del bus |
| `[[paginas]]` | `id`, `titulo` | Páginas de Preferencias |
| `[[configuracion]]` | `clave`, `tipo` (`bool`, `entero`, `decimal`, `texto`, `opcion`, `carpeta`, `archivo`, `lista`, `diccionario`), `defecto`, `etiqueta`, `ayuda`, `pagina`, `minimo`, `maximo`, `opciones` (`[["valor", "Etiqueta"]]`), `interna`, `ejecuta` (`true` si el valor es un programa o una orden que zCommander ejecutará, como `ruta_git`; una copia de seguridad no la restaura sin que la persona la marque, 7.2; por defecto `false`, salvo en las de tipo `archivo`, que valen `true` si no dicen otra cosa) | Configuración propia |
| `[[secretos]]` | `nombre`, `descripcion` | Secretos |
| `[[sonidos]]` | `id` (la parte tras «:»; el único obligatorio), `nombre` (por defecto, el `id`), `descripcion` (por defecto `""`), `prioridad` (`alta`, `media` o `baja`; por defecto `media`), `por_defecto` (por defecto `true`), `archivo` (por defecto `sonidos/<id>.wav`); la categoría es siempre `plugin:<id del complemento>` (4.2) | Sonidos |
| `[[componentes]]` | Los campos de la ficha de componente (6.2). Los componentes de la línea base (rclone, libarchive, 7za, FFmpeg, `nvda`) no se declaran aquí: su ficha está en `linea_base.json` con `dueno` | Componentes de `data/bin` |

Validación (`app/plugins/manifiesto.py`, con mensajes en español en el gestor y en el registro): campos obligatorios, `id` válido y no reservado (un `zc.*` solo vale en `<raíz>/plugins/` o con la firma del proyecto, 3.9), versiones bien formadas, `api_minima <= api_probada`, licencia SPDX presente, órdenes con etiqueta y ayuda, letras de acceso sin repetir dentro de su menú, teclas en formato canónico de `app.services.teclas`, claves de configuración `[a-z][a-z0-9_]*` sin puntos, tipos y valores por defecto coherentes, ids de órdenes, sonidos y columnas únicos en el complemento, marcadores de máscara con prefijo propio que no chocan con los de la 1.x, `codigos_windows` como lista de enteros, `ejecuta` como booleano, `prueba` que nombra una orden declarada, y ningún módulo de nivel superior de `lib/` con el nombre de un módulo de la biblioteca estándar o del contrato de bibliotecas de 3.7.

**Quién escribe los manifiestos de serie**: cada bloque P1 a P5, NU y NS es dueño del `manifiesto.toml` completo de sus complementos. N2 solo deja la primera versión con `id`, `bloque`, los campos obligatorios de nivel superior, `[[ordenes]]` (id, etiqueta, ayuda de una frase, teclas en formato canónico, ámbito, menú, nivel, argumento) y los ids de `[[sonidos]]` (los demás campos de cada sonido toman los valores por defecto de la tabla, que ya son válidos); con eso el catálogo y las teclas de todos son reales desde N2. El bloque dueño completa el resto a partir de su ficha (columnas, visores, esquemas, comprimidos, info, unidades, búsqueda, extractores, acciones de error, configuración, páginas, secretos, permisos y los datos de cada sonido), y la prueba de choques de teclas (`tests/ui/test_n2_teclas.py`) se repite en la definición de terminado de cada bloque (19.4).

### 3.4 Ciclo de vida

Estado de carga (enumeración `EstadoComplemento` de `app/plugins/estado.py`, módulo sin wx que crea N2 y del que PL es dueño posterior; `gestor.py` y `cargador.py` solo lo importan): `INCOMPATIBLE`, `INHABILITADO` (la persona lo inhabilitó: `complementos.inhabilitados`), `SIN_ACEPTAR` (sin firma, llegó a `data/plugins/` sin pasar por la instalación o cambió desde que se aceptó, 3.9), `REGISTRADO` (marcadores sin código; el gestor dice «Sin cargar todavía»), `CARGANDO`, `ACTIVO` (código cargado), `FALLIDO` (fuera de uso en esta sesión por fallos, 3.8) y `ERROR_MANIFIESTO`. Aparte, cada complemento tiene un **cambio pendiente de reiniciar** (`Pendiente`, en el mismo módulo: `NINGUNO`, `INSTALAR`, `ACTUALIZAR`, `VOLVER_ATRAS`, `DESINSTALAR`), de modo que «Activo, se actualizará al reiniciar» o «Inhabilitado, se desinstalará al reiniciar» se pueden representar.

Vocabulario (0.5): «activar», «activo» y `ACTIVO` se refieren solo a cargar el código; la preferencia de la persona es «habilitar» o «inhabilitar».

Arranque (en `main.py`; el orden completo con lo que no es de complementos está en 14.8):

1. Aplicar las instalaciones de `data/plugins/.pendientes/`, las vueltas atrás y las desinstalaciones marcadas (tras cargar la configuración). Aquí solo se mueven carpetas: los `al_instalar` y `al_desinstalar` de lo aplicado se ejecutan después de mostrar la ventana (3.10).
2. Modo seguro: `--sin-complementos` o Mayús pulsada al arrancar (comprobada con `GetAsyncKeyState`). En modo seguro no se registra ningún complemento.
3. Centinelas: cada archivo de `data/cache/plugins/cargando/` nombra un complemento cuya activación quedó a medias; ese complemento (y los de `complementos.inhabilitados`) se excluye en este arranque y se pregunta por él tras mostrar la ventana (3.8). El resto se carga con normalidad.
4. Descubrir: recorrer `plugins/` y `data/plugins/`, leer manifiestos (con `indice.json` si nada cambió), validar (un id repetido en la misma ubicación es un error para las dos carpetas, 3.2), comprobar compatibilidad y confianza (3.9). En `<raíz>/plugins/`, los que no están en `serie.SERIE` con su versión se tratan como los de `data/plugins/` (3.2). En `data/plugins/` se comprueba aquí la firma sobre la lista de archivos y sumas que trae (sin leer los archivos, así el arranque desde un pendrive no abre miles de archivos), que no haya archivos fuera de esa lista, que un id con clave fijada traiga una firma válida de esa clave (si no, se rechaza) y que uno sin firma esté en `complementos.confiados` (si no, queda `SIN_ACEPTAR`). Las sumas de los archivos se comprueban justo antes de importar (activación, paso 2).
5. Registrar marcadores: órdenes en el catálogo, menús, teclas en el `MapaTeclas`, columnas, visores, info, unidades, esquemas y extensiones de comprimidos, búsqueda, extractores, máscaras, acciones de error, órdenes internas, eventos de sonido, claves y páginas de configuración, componentes. Sin importar código. El registro de marcadores solo cambia en el hilo principal (aquí, antes de que exista la ventana) o en el hilo de la interfaz (3.10).
6. Crear y mostrar la ventana.
7. Con `wx.CallAfter`, activar los complementos con `al_arrancar`, uno a uno, midiendo cada uno; preguntar por los centinelas y por los `SIN_ACEPTAR` (3.8, 3.9).

**Activación** (`app/plugins/cargador.py`): una máquina de estados que vive en el hilo de la interfaz. Ningún hilo tiene un candado tomado mientras espera a otro, y el hilo de la interfaz nunca espera, así que no puede haber interbloqueos.

- `cargador.asegurar_activo(id: str) -> concurrent.futures.Future[bool]` [cualquiera]: si el complemento está `ACTIVO`, devuelve un futuro ya resuelto con verdadero; si está `FALLIDO`, `INHABILITADO`, `SIN_ACEPTAR` o `INCOMPATIBLE`, resuelto con falso; si está `CARGANDO`, el futuro de la carga en curso; si está `REGISTRADO`, crea el futuro, pasa a `CARGANDO` y empieza la carga. El estado solo se lee y se cambia en el hilo de la interfaz: llamada desde un hilo de trabajo, la petición pasa a la interfaz por el planificador (`cargador.fijar_planificador(planificador)`, función del módulo que `main.py` llama con `wx.CallAfter` justo después de crear `wx.App`, 14.8, porque `app/plugins` no importa wx) y el futuro se devuelve en el acto.
- **Dependencias primero**: si el manifiesto tiene `[requiere] complementos`, antes del paso 1 el cargador pide `asegurar_activo` de cada dependencia y **encadena sus futuros**: la carga de A empieza cuando todas sus dependencias se han resuelto con verdadero; si una se resuelve con falso, A queda `FALLIDO` con «Falta el complemento B, que X necesita». Así `zc.complemento(B)` dentro del `activar()` de A siempre devuelve lo exportado por una dependencia declarada. **Ciclos**: el cargador guarda la cadena de dependencias pendientes de cada carga; si al encadenar aparece un id que ya está en la cadena, todos los de ese ciclo se resuelven con falso y se registra «Dependencia circular entre A y B»; ninguno queda a medio activar.
- **Pasos de la carga**: 1) se crea su centinela `data/cache/plugins/cargando/<id codificado>` (un archivo por complemento, así varias activaciones a la vez no se pisan); 2) en el **hilo del cargador** (un hilo propio, `zc-cargador`; nunca el grupo de hilos del complemento ni el `GestorTareas`), se comprueban las sumas de sus archivos contra su firma, su entrada de `complementos.confiados` o `serie.SUMAS` (3.9): un complemento firmado (o de serie) con archivos cambiados queda `FALLIDO` con «Los archivos del complemento X han cambiado desde que se instaló»; uno sin firma aceptado con la suma cambiada pasa a `SIN_ACEPTAR` (se pregunta otra vez, 3.9); en los dos casos no se importa nada; 3) en ese mismo hilo, se importa la entrada como paquete `zcplugins.<id codificado>`, donde el id se codifica cambiando cada `.` por `__` (sin ambigüedad, porque los ids no pueden llevar `__`), con el **cargador de módulos verificado** de 3.9, que vuelve a comprobar la suma de cada archivo al leerlo. Su `lib/` **no** se añade a `sys.path`: el código del complemento importa lo vendorizado de forma relativa (`from .lib import pypdf`) y, para las bibliotecas que se importan a sí mismas por su nombre (mutagen, dulwich), el cargador instala un `MetaPathFinder` propio del complemento al **final** de `sys.meta_path`, que solo resuelve los nombres de nivel superior que hay en su `lib/` (también con el cargador verificado) y que nada más puede resolver (nunca tapa la biblioteca estándar, el contrato de bibliotecas de 3.7 ni el código de zCommander). Los pasos 2 y 3 tienen un **tope de `TIEMPO_CARGA_S = 30` s**: si se agota (código que se cuelga al importarse), el complemento queda `FALLIDO` con «El complemento X tarda demasiado en cargarse», el hilo se abandona (Python no puede matarlo; el cargador crea otro `zc-cargador` para las cargas siguientes) y el gestor **no** ofrece «Volver a intentarlo» en esa sesión (el candado de importación de ese módulo sigue tomado por el hilo colgado); 4) de vuelta en el hilo de la interfaz, `activar(zc)`; 5) el centinela se borra en un `finally`, también si la importación o `activar()` lanzan o se agota el tope (un fallo normal nunca se toma por un cierre brusco), y el futuro se resuelve con verdadero o falso.
- **Continuaciones fuera de la transición**: quien espera un futuro de activación en el hilo de la interfaz (una orden encolada, `complemento_futuro`, una columna, el diálogo de error) lo hace con `add_done_callback`, pero esa función **solo publica** la continuación con el planificador; la continuación corre después, en una vuelta propia del bucle de eventos, envuelta en `estado.llamar_protegido`. Nunca se ejecuta dentro de `set_result` (que la llamaría a mitad de la transición del paso 5 y, como hace `concurrent.futures`, se tragaría su excepción).
- **`activar()` no abre diálogos**: `ui.mostrar_modal` (y las preguntas de `zc.ui`) lanzan `RuntimeError` («Un complemento no puede abrir un diálogo dentro de activar()») mientras el complemento está `CARGANDO`, porque el bucle anidado de un modal procesaría otras activaciones y continuaciones en mitad de la transición. Lo que haya que preguntar al activarse se aplaza: `zc.complemento_futuro(zc.id).add_done_callback(...)`, cuya continuación el cargador publica cuando la transición ha terminado. `tools/validar_plugin.py` lo avisa.
- **Una orden** de un complemento que no está `ACTIVO` no espera: se encola como continuación del futuro con una **instantánea inmutable del objetivo** tomada al pulsar la tecla: `ObjetivoCongelado(lado, proveedor, ruta, cursor, marcadas, elementos_trabajo)` de cada panel (dataclass sin wx en `app/plugins/registro.py`). El `ContextoComplemento` de la continuación recibe paneles que responden con esa instantánea (`refrescar()` sí actúa sobre el panel real), así una orden destructiva nunca actúa sobre el elemento al que la persona se movió mientras oía «Cargando el complemento...». Si antes de que se resuelva la persona cambia de carpeta en ese panel o ejecuta otra orden, la continuación se descarta y se anuncia «No se ejecutó Reproducir: cambió de carpeta mientras se cargaba el complemento» (o «...: ejecutó otra orden mientras se cargaba el complemento»). Si se resuelve con falso, se anuncia el motivo. Si la carga tarda más de 300 ms, se anuncia «Cargando el complemento...» (suena `plugin.cargando`).
- **Macros y tareas esperan cada orden**: `ejecutar_orden_futuro(id_orden, lado=None, *, argumento=None) -> Future[bool]` [interfaz] (en `VentanaPrincipal`, `ContextoOrden` y `Anfitrion`, 3.7 y 14.9) ejecuta la orden como `ejecutar_orden` y devuelve un futuro que se resuelve cuando su manejador ha terminado: en el acto para las del núcleo y las de complementos activos; al terminar la continuación para las de un complemento que se estaba cargando; con falso si la orden no estaba disponible, falló, se descartó o su complemento no se pudo activar. El ejecutor de macros (PE, 10.1) y `ejecutar_tarea` de `zc.programador` (11.24) pasan al paso siguiente solo cuando se resuelve el futuro del anterior (y, con `esperar`, cuando termina además su operación).
- **Un hilo de trabajo** (proveedor, línea de información, visor, búsqueda) que necesita el complemento espera el futuro con `asegurar_activo(id).result(TIEMPO_CARGA_S)` (o hasta su cancelación) sin tener ningún candado tomado. **Las columnas no esperan**: `registro.valor_columna` no manda trabajo al grupo de hilos del complemento hasta que el futuro se resuelve (con `add_done_callback`, publicado como arriba), y los 5 s por valor de 3.8 empiezan a contar desde ese momento; mientras tanto la fila muestra «…». Así una primera activación lenta no gasta los agotamientos que detienen una columna.
- **`zc.complemento(id)`** (3.7): desde un hilo de trabajo espera el futuro como arriba; desde el hilo de la interfaz (también dentro de `activar()`) nunca importa en el acto: devuelve lo exportado si el otro ya está `ACTIVO` (siempre lo está si es una dependencia declarada en `[requiere]`) y, si no, pide su activación y devuelve `None`. Quien lo necesita en la interfaz usa `zc.complemento_futuro(id)` y sigue cuando se resuelve.

Mientras un complemento no está activado, el núcleo responde por él con lo declarado: estado de las casillas con `casilla_defecto`, disponibilidad en el menú contextual con `disponible_si` y entradas fijas del selector de unidades con `[[unidades]]`. Así abrir un menú o el menú contextual no activa ningún complemento. Excepciones, todas sin bloquear el hilo de la interfaz:

- El selector de unidades con `dinamicas = true` (3.3): ese complemento se activa en segundo plano la primera vez que se abre el selector en la sesión; el selector muestra ya las fijas y añade las dinámicas cuando llegan (14.5).
- **Intro sobre un comprimido** de una extensión de `[[comprimidos]]` cuyo complemento no está activo (`acciones/navegacion.py` llama a `resolver.abrir_comprimido` en el hilo de la interfaz): se trata como una orden, con su continuación, su instantánea del panel y «Cargando el complemento...»; al resolverse, abre el comprimido como carpeta.
- **Vista previa del renombrado múltiple** (`dialogos/e_renombrado.py`): `renombrado.calcular` deja de llamarse en el hilo de la interfaz y se calcula en un hilo; las filas que esperan una máscara de un complemento (que se activa como en cualquier hilo de trabajo, y además lee metadatos) muestran «…» hasta que llega su valor.
- **Acciones de error**: el gestor de decisiones muestra el botón según el manifiesto (`codigos_windows` de `[[acciones_error]]`, 3.3), sin activar el complemento; si ya está activo, su `aplica()` tiene además que dar verdadero. Al pulsarlo con el complemento sin activar, el diálogo de error dice «Cargando el complemento...» con los botones inhabilitados hasta que el futuro se resuelve (el bucle del diálogo modal sigue atendiendo la activación) y entonces llama a su función (14.6).

**Al cerrar**, dentro de `VentanaPrincipal._al_cerrar` de la 1.x y en este orden exacto:

1. `cargador.congelar()`, antes de cualquier pregunta: desde aquí no empieza ninguna activación ni corre ninguna continuación (las que lleguen se descartan y se registran). Así el bucle anidado de «Esperar y salir» de la 1.x (`wx.SafeYield`) no activa complementos ni lanza operaciones nuevas, y `operaciones.en_marcha()` se puede vaciar. Si después la salida se cancela, `cargador.descongelar()`.
2. **Fase con veto** (todavía se puede cancelar el cierre): la pregunta de salida de la 1.x (operaciones en curso o `general.confirmar_salida`) y después `puede_cerrar()` de cada complemento activo, en orden de activación y protegido (método opcional de `Complemento`, 3.7, que puede preguntar con `zc.ui`; falso cancela el cierre). Ahí va, por ejemplo, la pregunta de Nubes por unidades montadas con subidas pendientes (12.2, 12.8). En el autocierre del modo tarea no hay ninguna pregunta (11.24).
3. **Fase irrevocable de la 1.x**: `_saliendo`, temporizador, `decisiones.cancelar_todas()`, `operaciones.apagar(3.0)`, `conexiones.cerrar_todas()`, procesos de la línea de órdenes, geometría y sesión, `soltar_proveedor` de cada panel y `tareas.apagar(3.0)`.
4. `bus.vaciar()`: entrega en el acto lo que estaba en la cola del bus (`al_copiar_portapapeles`, `al_terminar_orden`...), para no perder lo emitido antes de cerrar.
5. `bus.emitir_sincrono("al_cerrar")` (14.4): los suscriptores se llaman en el acto, protegidos, **antes** de `desactivar()`, así los complementos que guardan estado en ese evento (frecuencias, historial del portapapeles) no lo pierden.
6. `desactivar()` de cada complemento activo, protegido. El tope de 2 s entre todos **solo se mide**: una función que corre en el hilo de la interfaz no se puede interrumpir; si se pasa, se registra qué complemento tardó.
7. `bus.cerrar()` y `cargador.cerrar()`: desde aquí las emisiones y las peticiones de activación se descartan y se registran, los hilos que esperan un futuro se despiertan con `Cancelado`, y `cargador.cerrar()` borra los centinelas de las cargas que siguen en curso (un cierre normal nunca se toma por un cierre brusco en el arranque siguiente). La bandera de cierre y las llamadas al planificador comparten un mismo candado, así ninguna llamada a `wx.CallAfter` se cuela después de destruir `wx.App` (no hay `PyNoAppError`).
8. `api.fijar_interfaz(None)` (3.7), `sonidos.cerrar()` (4.3) y la destrucción de las ventanas, como en la 1.x.

### 3.5 Puntos de extensión

Todos se registran desde `activar(zc)` sobre el objeto `Anfitrion` (3.7). Lo declarado en el manifiesto existe como marcador antes de la activación; el código solo pone las funciones.

| Punto | Qué permite | Dónde engancha en el núcleo |
|---|---|---|
| Órdenes | Acciones con id `<id>:<orden>`, tecla, ámbito, tipo casilla, argumento | Catálogo dinámico (14.1); `bloque` del manifiesto; manejador `complementos_pl.ejecutar` con `param` = id completo, que activa el complemento si hace falta y llama al manejador con un `ContextoComplemento` (3.7) |
| Menús y paleta | Menú «Co&mplementos» con un submenú por complemento; anclas en Archivos, Comandos > Herramientas y menú contextual | `MENUS` dinámico; `tools/comprobar_menus.py` sobre el catálogo completo |
| Proveedores VFS y esquemas | Orígenes nuevos (`nube://`, `synology://`, `papelera://`) | `resolver.registrar_esquema`, `resolver.registrar_unidades` (14.5); las entradas fijas de `[[unidades]]` salen en el selector sin activar el complemento, y las dinámicas activan el complemento en segundo plano al abrir el selector la primera vez (3.4) |
| Formatos de comprimido | Extensiones nuevas como carpeta | `resolver.registrar_comprimido`; si la fábrica lanza `NoAdmitido`, Intro abre el archivo con su programa (14.5) |
| Columnas | Valores por archivo (duración, artista, firma, Git) | `ListaArchivos` con columnas externas (`fijar_columnas_externas`, 19.1): la lista pide cada valor a `app.plugins.registro.valor_columna`, que nunca bloquea, manda el cálculo al grupo de hilos propio del complemento (3.8), guarda la caché por (ruta, tamaño, fecha), aplica el tiempo máximo de 5 s por valor y avisa para repintar la fila (contrato en 3.13). Título, tipo (para ordenar y alinear) y si es lenta salen del manifiesto por `registro.catalogo_columnas()` |
| Información del elemento | Líneas extra en Ctrl+Mayús+I y en la vista Información, para los archivos de los patrones de `[[info]]` | `consulta.decir_info` y `vistas.py` llaman a `app.plugins.registro.lineas_info(entrada, proveedor)` en un hilo |
| Visores (F3) y Vista rápida | Convertir un archivo en un `Documento` con secciones, o abrir una ventana propia (visores con `ventana = true`, como el de tablas de 11.22) | Visor interno: F3 usa la asociación «ver»; si no hay, el visor de complemento de mayor prioridad cuyo patrón coincide; si no, el visor interno. La Vista rápida solo usa visores que devuelven `Documento` |
| Funciones exportadas | Un complemento ofrece funciones a otros (etiquetas, OCR, conversión de documentos) | `zc.exportar(nombre, objeto)` y `zc.complemento(id)` (3.7) |
| Ventanas propias | Reproductor, editor hexadecimal, tablas | `api.ui` (3.7); prueba obligatoria con `revisar_teclado` |
| Proveedores de búsqueda | Resultados de motores externos | Diálogo Buscar archivos (1.x §8.12): desplegable «Motor» y lista de resultados |
| Extractores de texto | Buscar texto dentro de PDF, DOCX, EPUB | Búsqueda por contenido con la casilla «Buscar también dentro de documentos» |
| Máscaras de renombrado | `[a]`, `[EXIF:fecha]`... | Renombrado múltiple (1.x §8.14) y el organizador |
| Operaciones | Trabajo largo con progreso, pausa, cola y deshacer | `zc.lanzar(operacion)`; clase base `Operacion` del motor (1.x §9.6) |
| Acciones de error | Botones extra en la pregunta de error del motor | El gestor de decisiones de la interfaz (14.6); las operaciones no cambian |
| Eventos | Suscribirse al bus | `app/services/eventos.py` (14.4) |
| Preferencias | Páginas propias declarativas o un diálogo propio (marcado con `dialogo_preferencias = true` en el manifiesto) | Nodo «Complementos» del diálogo de Preferencias (10.18); el diálogo propio se registra con `paginas_propias.registrar_dialogo_complemento` (3.6) |
| Secretos | Contraseñas y fichas de acceso | `AlmacenSecretos` con prefijo `plugin:<id>:` |
| Sonidos | Eventos propios con su archivo | Catálogo de sonidos (4.2) |
| Ayuda | Manual y novedades del complemento | Visor de ayuda; F1 en sus ventanas; botón «Ayuda» del gestor |
| Componentes | Binarios en `data/bin/<id>/` | Catálogo de componentes (6.2) |
| Línea de órdenes | Órdenes internas propias `zc <nombre> [argumentos]` (por ejemplo `zc git status`), con salida a «Salida de órdenes» | `linea_ordenes.py` (10.8) con `zc.ordenes.interna` (3.7) |
| Asociaciones | Ser el programa de Abrir, Ver o Editar de un patrón | Valor `zc:<id de orden>` en `asociaciones.json` |

Fuera de la API (a propósito): acceso directo a los controles wx de la ventana principal, al despachador de teclas y a la lista de archivos; el `ContextoOrden` del núcleo (con su `ventana`, sus operaciones y `servicio()`, que daría acceso a todos los secretos); parches de módulos internos. El gestor marca «usa partes internas» si detecta importaciones de `app.` fuera de `app.plugins.api` (análisis con `ast` al validar).

### 3.6 Configuración propia de cada complemento

- Cada complemento con `[[configuracion]]` tiene su propia `Configuracion` (la clase de la 1.x) en `data/config/plugins/<id>.json`, con sección única `ajustes`, valores por defecto y `REGLAS` construidos desde el manifiesto. Así una configuración dañada de un complemento no toca la de zCommander, y desinstalar puede borrarla.
- **Nombre completo de una clave**: `plugin.<id>.<clave>`, por ejemplo `plugin.zc.reproductor.salto_corto_s`. Se separa por el último punto: todo lo que hay entre `plugin.` y el último punto es el id. Es el nombre que usan el anexo `configuracion.md`, las copias de seguridad, las macros y las páginas de Preferencias.
- Desde el complemento se usan claves cortas: `zc.config.obtener("salto_corto_s")`, `zc.config.establecer("salto_corto_s", 10)`, `zc.config.suscribir(funcion, prefijo="")`, `zc.config.restablecer()`. Los avisos de `suscribir` llegan siempre en el hilo de la interfaz (la fachada los pasa con el planificador de 14.4, aunque el cambio venga de un hilo o del temporizador de `establecer_diferido`).
- **Páginas de Preferencias declarativas**: cada `[[paginas]]` crea una página hija del nodo «Complementos > <nombre del complemento>»; cada clave no interna se muestra en la página de su campo `pagina` con el control de su tipo (los de `dialogo_preferencias.py`; `lista` y `diccionario` con un editor de lista accesible). La letra de acceso la escribe el autor con `&` en la `etiqueta` del manifiesto; `tools/validar_plugin.py` comprueba que no se repite en la página (contando los botones del diálogo de Preferencias) y lo dice con el nombre de la clave. `tools/comprobar_preferencias.py` sigue siendo solo para `descripciones_config.py` del núcleo (no reescribe manifiestos: `tomllib` solo lee).
- **Diálogo propio**: si el manifiesto dice `dialogo_preferencias = true`, el botón «Configurar» del gestor y la página del complemento en Preferencias muestran «Abrir la configuración avanzada...» **sin activar el complemento** (Preferencias no activa ninguno para pintarse). Al pulsarlo, se pide la activación (3.4) y, cuando termina, se llama en el hilo de la interfaz a la función que el complemento registró en `activar()` con `zc.preferencias.dialogo(funcion)`; esa llamada la pasa la API a `app.ui.paginas_propias.registrar_dialogo_complemento(id, funcion)` (10.18). Si el complemento no llega a registrarla, se anuncia «El complemento X no tiene configuración avanzada». Las páginas declarativas se construyen con el mismo protocolo `PaginaPropia` de las páginas propias del núcleo (10.18), así que participan igual en Aceptar, Cancelar, Aplicar y «Valores de fábrica de esta página».
- **Secretos**: `zc.secretos.obtener(nombre)`, `guardar(nombre, valor)`, `borrar(nombre)` sobre `secretos.dat` con el nombre `plugin:<id>:<nombre>`; solo si el manifiesto declara el permiso `secretos`. Al desinstalar con «Borrar también su configuración y sus datos», se borran.
- El registro global `app/plugins/config_plugins.py` (`ConfigPlugins.obtener(clave_completa)`, `establecer(clave_completa, valor)`, `claves()`) resuelve los nombres completos para Preferencias, copias y macros.

### 3.7 API (`app/plugins/api.py`)

Fachada única, importable como `from app.plugins import api`; los complementos no importan nada más de `app`. `API_VERSION = (1, 1)` y `API_COMPATIBLE_DESDE = (1, 0)` (la 1.1, de la integración final, solo añade a la 1.0: `zc.columnas.invalidar(rutas=None)`, el paso de deshacer `restaurar`, `zc.ui.mostrar_diferencias(ruta_a, ruta_b)`, `zc.abrir_ayuda(pagina)` que abre `doc/es/<pagina>.md`, `Proveedor.orden_preferido`, resultados de búsqueda con direcciones de un proveedor, la activación por `[[esquemas]]` y la entrega del evento que activa un complemento; `docs/revision/integracion-final.md`). Cambios de la versión menor solo añaden; quitar algo exige cambiar la versión principal y un aviso de obsolescencia una versión antes. `tests/plugins/test_api_estable.py` compara la firma pública con una instantánea guardada en `tests/datos/api_1_0.json`. La instantánea **se congela al cerrar PL y P1** (los primeros que usan la API de verdad), no en N2: hasta entonces el dueño de `api.py` puede añadir o corregir lo que pidan los bloques y regenera la instantánea con `test_api_estable.py --actualizar`; después solo se añade. `api.py` tiene **un único dueño en cada momento**: N2 mientras lo crea, PL desde que N2 termina hasta que PL termina, y el coordinador después (19.1, 19.3); quien necesita algo nuevo se lo pide a ese dueño. `api.py` no importa `app.ui` ni wx (regla de capas, 3.13): todo lo de la interfaz llega por **una sola inyección**, `api.fijar_interfaz(interfaz: InterfazAnfitrion | None) -> None`, que la ventana llama al construirse y con `None` al cerrar (3.4, paso 8; protocolo `InterfazAnfitrion` abajo), y las anotaciones con tipos de wx van entre comillas (`"wx.Window"`), sin importar wx ni siquiera bajo `TYPE_CHECKING`.

Contrato (firmas; los tipos re-exportados son los de la 1.x, la misma clase y no una copia). Cada método dice en qué hilo se puede llamar: **[cualquiera]** (la fachada pasa a la interfaz lo que haga falta), **[trabajo]** (bloquea: nunca en el hilo de la interfaz) o **[interfaz]**.

```python
API_VERSION: tuple[int, int]
API_COMPATIBLE_DESDE: tuple[int, int]

# Re-exportados del núcleo
Entrada, Proveedor, Capacidades, Ubicacion, UnidadVirtual, ResultadoPar
                                                                # app.services.vfs.base (N2 mueve allí UnidadVirtual y crea ResultadoPar, 14.5)
ErrorArchivos, ErrorAcceso, NoEncontrado, YaExiste, SoloLectura, ErrorRed, NombreNoValido, SinEspacio, Cancelado, NoAdmitido
                                                                # app.services.vfs.base; ErrorRed es la única clase de error de red (14.9)
Operacion, Estado, Progreso, ContextoEjecucion, Politica, OpcionesCopia, OperacionCopiar, OperacionEliminar, OperacionRenombrar
PreguntaError, AccionError, Decisor, clave_carril, RespuestasAutomaticas
                                                                # app.services.operaciones.modelo (RespuestasAutomaticas, 14.6)
TokenCancelacion                                                # app.core.tareas (el objeto de cancelación de la 1.x)
AccionDeshacer, Paso                                            # app.services.operaciones.deshacer
CriteriosBusqueda                                               # alias de app.services.busqueda.Criterios
ESENCIAL, RESULTADO, NORMAL, DETALLE                            # niveles de anuncio (cadenas)
formato                                                         # app.services.formato (tamano_legible, fecha, duracion...)
comprobar(cancelacion) -> None                                  # lanza Cancelado

def traduccion(nombre_modulo: str) -> tuple[Callable[[str], str], Callable[[str, str, int], str]]
def provisional(id_corto: str) -> Callable[["ContextoComplemento"], None]
    # manejador provisional marcado (anuncia «Esta orden del complemento aún no está programada»); lo usan
    # los esqueletos de N2 y la prueba de provisionales de 18.1 lo detecta por la marca, no por el texto

class Complemento:
    id: str                          # lo pone el gestor
    carpeta: Path
    def activar(self, zc: "Anfitrion") -> None: ...
    def desactivar(self) -> None: ...
    def ventanas_para_revisar(self, padre: "wx.Window") -> list["wx.TopLevelWindow"]: ...
        # opcional: crea (sin mostrarlas) sus ventanas y diálogos para que tools/validar_plugin.py les pase
        # revisar_teclado (3.12); por defecto, lista vacía
    def puede_cerrar(self) -> bool: ...
        # opcional [interfaz]: fase con veto del cierre (3.4, paso 2); puede preguntar con zc.ui; falso cancela
        # el cierre de zCommander. Por defecto, verdadero

@dataclass(frozen=True)
class Seccion:
    titulo: str
    nivel: int = 1                   # 1 a 6
    texto: str = ""
    pagina: int = 0                  # 0 si no aplica

@dataclass(frozen=True)
class Documento:
    titulo: str
    secciones: tuple[Seccion, ...]
    metadatos: dict[str, str] = field(default_factory=dict)
    aviso: str = ""                  # «PDF sin texto: probablemente escaneado»

class PanelComplemento(Protocol):    # vista de un panel para el complemento [interfaz]
    lado: str                         # «izquierdo» o «derecho»
    @property
    def proveedor(self) -> Proveedor  # propiedades, como en el PanelProtocolo de la 1.x (app/ui/contexto.py)
    @property
    def ruta(self) -> str
    def mostrar_ruta(self) -> str
    def cursor(self) -> Entrada | None
    def marcadas(self) -> list[Entrada]
    def elementos_trabajo(self) -> list[Entrada]
    def refrescar(self) -> None

@dataclass
class ContextoComplemento:           # lo que recibe un manejador de orden de complemento [interfaz]
    orden: str                        # id completo, «zc.reproductor:reproducir»
    activo: PanelComplemento
    pasivo: PanelComplemento
    lado_objetivo: str | None = None  # si la orden se lanzó desde el menú Izquierdo o Derecho
    argumento: Any = None             # el de una macro, el de `zc <orden> <argumento>` o la ruta de Intro sobre un archivo asociado
    @property
    def objetivo(self) -> PanelComplemento   # propiedad, como ContextoOrden.objetivo de la 1.x
    def anunciar(self, texto: str, nivel: str = NORMAL, completo: str = "", interrumpir: bool | None = None) -> None
    def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool   # la firma única de 4.3
    # Sin `ventana`, sin `servicio()`, sin el gestor de operaciones: lo que haga falta va por el Anfitrion.

class Anfitrion:
    id: str                          # id del complemento
    version_app: str
    carpeta: Path                    # carpeta del complemento (solo lectura)
    datos: Path                      # data/config/plugins/<id>/ (se crea al pedirla)
    cache: Path                      # data/cache/plugins/<id>/
    registro: logging.Logger         # «zcplugins.<id>»
    config: "ConfigComplemento"
    secretos: "SecretosComplemento"  # NoAdmitido si falta el permiso «secretos»; solo los suyos («plugin:<id>:*»)
    tareas: GestorTareas
    decisor: Decisor                 # [trabajo]: preguntas desde hilos y operaciones; en el hilo de la interfaz se pregunta con `ui`
    ordenes: "RegistroOrdenes"
    vfs: "RegistroVFS"
    columnas: "RegistroColumnas"
    visores: "RegistroVisores"
    info: "RegistroInfo"
    busqueda: "RegistroBusqueda"
    renombrado: "RegistroMascaras"
    errores: "RegistroAccionesError"
    eventos: "RegistroEventos"
    preferencias: "RegistroPreferencias"
    sonidos: "SonidosComplemento"
    componentes: "ComponentesComplemento"
    red: "ClienteRed"                # NoAdmitido si falta el permiso «red» o «internet:<host>»
    ui: "ModuloUI"
    deshacer: "DeshacerComplemento"
    espacios: "EspaciosTrabajo"
    vistas: "VistasCarpeta"
    def anunciar(self, texto: str, nivel: str = NORMAL, completo: str = "", interrumpir: bool | None = None) -> None   # [cualquiera]
    def lanzar(self, operacion: Operacion, en_cola: bool = False, al_terminar: Callable[[Operacion], None] | None = None) -> None   # [cualquiera]
            # si se llama dentro del manejador de una orden y operacion.orden_origen está vacío, lo rellena con el id de esa orden (10.1)
    def ejecutar_programa(self, argumentos: list[str], *, entrada: bytes = b"", carpeta: str | None = None,
            tiempo_s: float = 60, cancelacion=None, al_leer: Callable[[bytes], None] | None = None,
            entorno: dict[str, str] | None = None) -> "ResultadoPrograma"                                  # [trabajo]
            # Solo con el permiso «ejecutar_programas»; envuelve app.core.procesos.lanzar (14.9): sin consola, sin shell,
            # en su propio Job anidado dentro del Job Object global de zCommander (la cancelación termina su árbol)
    def abrir_programa(self, argumentos: list[str], *, carpeta: str | None = None) -> int                  # [cualquiera]
            # Solo con «ejecutar_programas»: un programa que debe seguir abierto aunque se cierre zCommander (un editor,
            # el programa de una asociación); envuelve procesos.lanzar_independiente, fuera del Job Object; devuelve el PID
    def abrir_ruta(self, texto: str, lado: str | None = None) -> None     # [cualquiera] lleva un panel a una ruta o dirección
    def abrir_ayuda(self, pagina: str = "") -> None                       # [interfaz]
    def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None   # [interfaz]
            # la firma única de 10.1, igual en ContextoOrden y en la ventana
    def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> "Future[bool]"   # [interfaz]
            # lo mismo, con un futuro que se resuelve cuando el manejador ha terminado (3.4); lo usan las tareas (11.24)
    def escribir_en_linea(self, texto: str) -> None                      # [interfaz] pone el texto en la línea de órdenes sin ejecutarlo
    def exportar(self, nombre: str, objeto: Any) -> None                 # en activar(): ofrece una función o clase a otros complementos
    def complemento(self, id: str) -> SimpleNamespace | None             # [cualquiera] lo exportado por otro complemento; None si falta,
            # está inhabilitado o falló. Desde un hilo de trabajo lo activa si hace falta y espera (3.4); desde el hilo de la
            # interfaz nunca importa en el acto: si aún no está activo, pide su activación y devuelve None
    def complemento_futuro(self, id: str) -> "Future[SimpleNamespace | None]"   # [cualquiera] lo mismo como futuro, sin esperar

@dataclass(frozen=True)
class ResultadoPrograma:             # de app.core.procesos, re-exportada
    codigo: int
    salida: bytes
    errores: bytes
    cancelado: bool

class RegistroOrdenes:
    def manejador(self, id_corto: str, funcion: Callable[[ContextoComplemento], None]) -> None
    def estado(self, id_corto: str, funcion: Callable[[ContextoComplemento], bool]) -> None   # órdenes casilla
    def disponible(self, id_corto: str, funcion: Callable[[ContextoComplemento], bool]) -> None # desactiva el elemento de menú
    def interna(self, nombre: str, funcion: Callable[[list[str], Callable[[str], None], Any], int]) -> None
        # `zc <nombre> args` en la línea de órdenes (declarada en [[internas]]): recibe los argumentos, una función que
        # escribe una línea en «Salida de órdenes» y la cancelación; se llama en un hilo y devuelve el código de salida

class RegistroVFS:
    def esquema(self, prefijo: str, fabrica: Callable[[str], tuple[Proveedor, str]]) -> None
    def comprimido(self, extensiones: tuple[str, ...], fabrica: Callable[[Proveedor, str], Proveedor]) -> None
    def unidades(self, funcion: Callable[[], list[UnidadVirtual]]) -> None
        # entradas dinámicas del selector de unidades: se llama en un hilo; el selector muestra antes las fijas de
        # [[unidades]] y añade o actualiza (descripción con el espacio libre) lo que devuelva
    def resolver(self, direccion: str) -> tuple[Proveedor, str]          # [trabajo] proveedor nuevo para una dirección
                                                                         # sin panel; quien lo pide lo cierra

# UnidadVirtual (re-exportada de vfs.base): texto «Google Drive de Ana», direccion «nube://ana_drive/», descripcion «15 GB libres de 100 GB»

class RegistroColumnas:
    def extractor(self, id_corto: str, funcion: Callable[[Entrada, Proveedor, Any], str | None]) -> None
        # se llama en un hilo del grupo propio del complemento con un objeto de cancelación; None = «Sin datos»

class RegistroVisores:
    def visor(self, id_corto: str, funcion: Callable[[Proveedor, str, Any], Documento]) -> None       # en un hilo
    def ventana(self, id_corto: str, funcion: Callable[[Proveedor, str], None]) -> None              # [interfaz] visor con ventana propia

class RegistroInfo:
    def lineas(self, funcion: Callable[[Entrada, Proveedor], list[str]]) -> None    # en un hilo; < 1 s

class RegistroBusqueda:
    def proveedor(self, id_corto: str, funcion: Callable[[CriteriosBusqueda, Callable[[str], None], Any], None]) -> None
    def extractor(self, funcion: Callable[[Proveedor, str, Any], str | None]) -> None

class RegistroMascaras:
    def mascara(self, marcador: str, funcion: Callable[[Entrada, Proveedor], str | None]) -> None
    def evaluar(self, plantilla: str, entrada: Entrada, proveedor: Proveedor) -> str     # [trabajo] con todas las máscaras
        # registradas (las de la 1.x y las de cualquier complemento, activándolo); la usa el organizador (11.23)

class RegistroAccionesError:
    def accion(self, id_corto: str, aplica: Callable[[PreguntaError], bool], funcion: Callable[[PreguntaError], AccionError | None]) -> None
        # aplica() decide con pregunta.codigo_windows y pregunta.excepcion (14.6), nunca leyendo el mensaje; solo se
        # consulta si el complemento ya está activo: sin activar, manda el filtro codigos_windows del manifiesto (3.3, 3.4);
        # funcion() se llama en el hilo de la interfaz y devuelve REINTENTAR, OMITIR o CANCELAR (None: vuelve a preguntar)

class RegistroEventos:
    def suscribir(self, nombre: str, funcion: Callable[..., None]) -> Callable[[], None]   # devuelve «cancelar»; avisa en el hilo de la interfaz
    def emitir(self, nombre: str, **datos) -> None                                          # [cualquiera] solo eventos propios «<id>:<nombre>»

class RegistroPreferencias:
    def dialogo(self, funcion: Callable[["wx.Window"], None]) -> None   # exige dialogo_preferencias = true en el manifiesto (3.6)
    def abrir(self) -> None                                             # [interfaz] abre Preferencias en la página del complemento

class ConfigComplemento:
    def obtener(self, clave: str, por_defecto=...) -> Any
    def establecer(self, clave: str, valor: Any) -> bool
    def establecer_varias(self, cambios: dict[str, Any]) -> bool
    def suscribir(self, funcion: Callable[[str, Any, Any], None], prefijo: str = "") -> Callable[[], None]
    def restablecer(self) -> None

class SecretosComplemento:
    def obtener(self, nombre: str) -> str | None
    def guardar(self, nombre: str, valor: str) -> None
    def borrar(self, nombre: str) -> None

class SonidosComplemento:
    def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool
        # [cualquiera] «<id>:<evento>» propio o un id del núcleo («op.fin»); verdadero si el sonido se aceptó (4.3)

class ComponentesComplemento:                     # ruta() y ejecutable() se piden en cada uso y nunca se guardan (6.3)
    def ruta(self, id_componente: str) -> Path    # carpeta de data/bin/<id>; NoAdmitido si falta o está en mantenimiento (6.3)
    def ejecutable(self, id_componente: str, nombre: str) -> Path   # ídem
    def disponible(self, id_componente: str) -> bool
    def al_detener(self, id_componente: str, funcion: Callable[[], bool]) -> None
        # solo el dueño del componente: cómo pararlo para actualizarlo (6.6); se llama en un hilo y devuelve
        # False si hay trabajo en curso y no se puede parar

class DeshacerComplemento:
    def registrar(self, accion: AccionDeshacer) -> None   # [cualquiera] añade una acción a la pila de deshacer del núcleo

class EspaciosTrabajo:                                    # espacios de trabajo del núcleo (10.9) [interfaz]
    def listar(self) -> list[str]
    def guardar_actual(self, nombre: str, nota: str = "") -> None
    def abrir(self, nombre: str) -> None

class VistasCarpeta:                                      # vistas por carpeta del núcleo (10.4) [cualquiera]
    def conjuntos(self) -> list[str]                      # solo lectura
    def proponer_conjunto(self, nombre: str, columnas: list[str], lectura: list[str],
            extensiones: list[str] = (), proporcion: float = 0.6) -> bool
        # añade el conjunto y su regla de contenido solo si no existe uno con ese nombre; nunca cambia los de la persona

@dataclass(frozen=True)
class RespuestaRed:                       # de app.core.red, re-exportada
    estado: int
    cabeceras: dict[str, str]
    cuerpo: bytes
    url_final: str
    def texto(self) -> str                    # con el juego de caracteres de la cabecera (UTF-8 si no dice)
    def json(self) -> Any

class ClienteRed:                                  # fachada en app/plugins sobre app/core/red.py y app/core/descargas.py (14.9),
                                                   # con el User-Agent «zCommander/<versión> (<id>)»; traduce ErrorHTTP a ErrorRed  [trabajo]
    def obtener(self, url: str, *, cabeceras: dict | None = None, tiempo_s: float = 30) -> RespuestaRed
    def enviar(self, url: str, datos: bytes | dict, *, metodo: str = "POST", cabeceras: dict | None = None, tiempo_s: float = 30) -> RespuestaRed
    def descargar(self, url: str, destino: Path, *, sha256: str = "", tamano: int = -1, cancelacion=None,
            al_progresar: Callable[[int, int], None] | None = None) -> Path
        # destino: archivo final, o carpeta existente (el nombre sale de la URL); al_progresar(hechos, total), total −1 si no se sabe

class ModuloUI:   # [interfaz] sin wx: delega cada nombre, con __getattr__, en InterfazAnfitrion.modulo_ui, que es el
                  # módulo app.ui.api_ui (N2, con wx; dueño posterior PL). Así zc.ui.VentanaComplemento es una clase
                  # real de wx sin que app/plugins importe wx. Sin interfaz (pruebas sin wx) lanza NoAdmitido.
                  # Dentro de activar() sus diálogos lanzan RuntimeError (3.4).
    preparar_dialogo, crear_botonera, crear_campo, mostrar_mensaje, mostrar_error, confirmar, elegir_opcion, pedir_texto
    ListaAccesible, CheckListBoxAccesible, SliderAccesible, IndicadorProgreso
    def mostrar_modal(self, dialogo: "wx.Dialog") -> int                  # ShowModal con el vigilante de bloqueos en pausa (3.8);
                                                                          # los complementos no llaman a ShowModal directamente
    def mostrar_texto(self, titulo: str, texto: str) -> None              # ventana de solo lectura accesible
    def mostrar_documento(self, documento: Documento) -> None             # el visor interno con secciones
    def mostrar_resultados(self, titulo: str, rutas: Sequence[str], lado: str | None = None) -> None
    def movimiento_silencioso(self, ventana: "wx.Window") -> None         # marca de 10.16 antes de mover el foco por código
    VentanaComplemento   # clase de app.ui.api_ui, subclase de wx.Frame: no modal; Escape cierra; F1 abre la ayuda del
                         # complemento; registra su revisar_teclado en modo desarrollo

# Submódulo api.pruebas (sin wx; para las pruebas de los complementos y, poco a poco, las del núcleo)
def anfitrion_de_prueba(carpeta: Path, config: dict | None = None, permisos: Sequence[str] = ()) -> "AnfitrionFalso"
class AnfitrionFalso(Anfitrion):
    anuncios: list[tuple[str, str]]          # (texto, nivel)
    sonidos_pedidos: list[str]               # lo que se pidió por `sonidos.sonar` (sonidos es un SonidosComplemento falso que lo apunta)
    operaciones_lanzadas: list[Operacion]
    def ejecutar(self, id_corto: str, contexto: ContextoComplemento | None = None) -> None   # activa si hace falta y llama al manejador
    def columna(self, id_corto: str, entrada: Entrada, proveedor: Proveedor | None = None) -> str | None
    def visor(self, id_corto: str, ruta: str, proveedor: Proveedor | None = None) -> Documento
    def emitir(self, evento: str, **datos) -> None
class PanelFalso(PanelComplemento):
    def __init__(self, entradas: Sequence[Entrada] = (), cursor: int = 0, marcadas: Sequence[str] = (), ruta: str = "", proveedor: Proveedor | None = None)
class DecisorFalso(Decisor):
    def __init__(self, respuestas: Sequence[Any] = ())   # devuelve las respuestas en orden; .preguntas guarda lo preguntado
def contexto_de_prueba(activo: PanelFalso | None = None, pasivo: PanelFalso | None = None, argumento: Any = None) -> ContextoComplemento
```

`api.pruebas` consolida solo el `DecisorFalso`, hoy repetido en `tests/servicios/test_operaciones.py` y otros cuatro archivos de la 1.x: N2 lo escribe aquí a partir de esos, las pruebas nuevas lo importan de `api.pruebas` y las de la 1.x se cambian cuando se toquen. `api.pruebas.PanelFalso` es **nuevo** (implementa `PanelComplemento`, con su constructor); el `PanelFalso` de `tests/ui/g_comun.py` (atributos y otro constructor) y el `ContextoFalso` de `tests/ui/test_d_dialogos.py` y `test_e_dialogos.py` siguen para las pruebas de la 1.x, porque imitan el `ContextoOrden` del núcleo y no el contrato de los complementos.

**Inyección de la interfaz**: el protocolo `InterfazAnfitrion` vive en `app/plugins/interfaz.py` (sin wx; N2, dueño posterior PL) y lo implementa `app/ui/interfaz_anfitrion.py` (N2, con wx) sobre la ventana principal. Es lo único por lo que `api.py` llega a la interfaz: las fachadas de `Anfitrion`, `ModuloUI`, `RegistroPreferencias` y `DeshacerComplemento` lo llaman, y una fachada [cualquiera] llamada desde un hilo pasa la llamada con `planificar`. Sin interfaz fijada (pruebas sin wx, `--probar-componente`), los métodos [interfaz] lanzan `NoAdmitido` y `anunciar` solo escribe en el registro.

```python
class InterfazAnfitrion(Protocol):          # app/plugins/interfaz.py
    modulo_ui: ModuleType                   # app.ui.api_ui, en el que delega ModuloUI
    def planificar(self, funcion: Callable[[], None]) -> None          # [cualquiera] wx.CallAfter
    def en_hilo_interfaz(self) -> bool                                  # [cualquiera]
    def anunciar(self, texto: str, nivel: str, completo: str = "", interrumpir: bool | None = None,
            sonido: str = "") -> None                                   # [interfaz] app.ui.anuncios.anunciar
    def ejecutar_orden(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None   # [interfaz]
    def ejecutar_orden_futuro(self, id_orden: str, lado: str | None = None, *, argumento: Any = None) -> "Future[bool]"   # [interfaz]
    def lanzar(self, operacion: Operacion, en_cola: bool, al_terminar: Callable[[Operacion], None] | None,
            *, orden_origen: str) -> None                               # [interfaz] VentanaPrincipal.lanzar_operacion
    def abrir_ruta(self, texto: str, lado: str | None = None) -> None   # [interfaz]
    def abrir_ayuda(self, id_complemento: str, pagina: str = "") -> None   # [interfaz] visor de ayuda con doc/es/leeme.md
    def escribir_en_linea(self, texto: str) -> None                     # [interfaz]
    def registrar_deshacer(self, accion: AccionDeshacer) -> None        # [interfaz] ventana.servicio("deshacer").registrar
    def registrar_dialogo_complemento(self, id: str, funcion: Callable[["wx.Window"], None]) -> None
                                                                        # [interfaz] app.ui.paginas_propias (10.18)
    def abrir_preferencias(self, id: str) -> None                       # [interfaz] f_preferencias.abrir(..., pagina="complemento:<id>") (10.18)
    def panel(self, lado: str) -> PanelComplemento                      # [interfaz] «izquierdo», «derecho», «activo» o «pasivo»

def fijar_interfaz(interfaz: InterfazAnfitrion | None) -> None          # en api.py
```

**Destino de cada fachada**: varias partes del `Anfitrion` delegan en servicios de otros bloques. Para que ninguno de esos bloques tenga que editar `api.py`, N2 fija aquí la función de destino de cada fachada y la deja provisional en el módulo del bloque dueño (lista de 19.1, «Provisionales en archivos de otros bloques»); el bloque la implementa en su sitio sin tocar la fachada:

| Fachada | Función de destino (módulo del bloque dueño) | Provisional de N2 | Dueño |
|---|---|---|---|
| `ComponentesComplemento.ruta`, `ejecutable`, `disponible`, `al_detener` | `app.services.componentes.estado.ruta(id: str) -> Path`, `ejecutable(id: str, nombre: str) -> Path`, `disponible(id: str) -> bool`, `registrar_al_detener(id: str, funcion: Callable[[], bool]) -> None` | `ruta` = `paths.ruta_binarios() / <carpeta>` según el `linea_base.json` provisional; `disponible` mira si existe; `registrar_al_detener` guarda la función | CO |
| `EspaciosTrabajo.listar`, `guardar_actual`, `abrir` | `app.services.espacios.listar() -> list[str]`, `guardar_actual(nombre: str, nota: str = "") -> None`, `abrir(nombre: str) -> None` | Lista vacía; las otras lanzan `NoAdmitido` | PE |
| `VistasCarpeta.conjuntos`, `proponer_conjunto` | `app.services.vistas_carpeta.conjuntos() -> list[str]`, `proponer_conjunto(nombre, columnas, lectura, extensiones=(), proporcion=0.6) -> bool` | Lista vacía; `proponer_conjunto` devuelve falso | PE |
| `RegistroPreferencias.dialogo`, `abrir` | Por `InterfazAnfitrion`: `app.ui.paginas_propias.registrar_dialogo_complemento(id: str, funcion: Callable[["wx.Window"], None]) -> None` y `abrir_preferencias(id: str) -> None`, que llama a `app.ui.dialogos.f_preferencias.abrir(padre, config, pagina="complemento:<id>")` | El registro es funcional; `f_preferencias.abrir` es provisional (abre el diálogo de la 1.x y anuncia «Página no disponible», 19.1) | N2 (`paginas_propias.py`); PE (`f_preferencias.abrir`) |
| `DeshacerComplemento.registrar` | Por `InterfazAnfitrion.registrar_deshacer`: `ventana.servicio("deshacer").registrar(accion)` (la pila de deshacer de la 1.x) | Funcional | N2 |
| `Anfitrion.sonidos` | `app.services.sonidos.servicio.sonar` (4.3) | Funcional con el motor provisional | N2; SO pone el motor |

Reglas del contrato:

- Todo lo que recibe una función del complemento en un hilo (extractores, visores, líneas de información, búsqueda, fábricas, unidades, órdenes internas) acepta cancelación y no toca wx; lo que se llama en el hilo de la interfaz (manejadores, estados, eventos, acciones de error) dura menos de 20 ms **sin contar el tiempo que la persona pasa en un diálogo modal** abierto con `ui.mostrar_modal`, o manda el trabajo a `zc.tareas` o `zc.lanzar`.
- En el hilo de la interfaz se pregunta con `zc.ui.*`; desde un hilo de trabajo o una operación, con `zc.decisor` (que lanza `RuntimeError` si se llama desde el hilo de la interfaz, como el de la 1.x).
- Los proveedores de un complemento solo lanzan `ErrorArchivos`; cualquier otra excepción se convierte en `ErrorArchivos` genérico con el nombre del complemento.
- **Contrato de bibliotecas disponibles** (parte de la API 1.x): biblioteca estándar de Python 3.15 para Windows completa (salvo la lista negra de 17.1: `tkinter`, `turtle`, `idlelib`, `test`, `ensurepip`, `venv` y los demás que se nombran allí), wxPython 4.3.2, pywin32, comtypes, Send2Trash, cryptography, paramiko (con bcrypt y PyNaCl), py7zr, Markdown y accessible_output2. El resto, en `lib/`.

### 3.8 Protección

- **Llamadas protegidas**: toda entrada del núcleo al complemento pasa por `app.plugins.estado.llamar_protegido(id_complemento: str, funcion, *args, **kwargs) -> Any | None` (N2; la usan el cargador, el bus, el gestor de decisiones y PL; devuelve `None` si la función lanzó): captura la excepción, la registra con id, versión y traza, y anuncia una vez por sesión y complemento, como esencial: «El complemento Reproductor multimedia falló al reproducir. Detalles en el registro.».
- **Fuera de uso tras 3 fallos** (`complementos.fallos_maximos`) en la sesión, o al primer fallo al importar o en `activar()`: `llamar_protegido` lleva el contador y pasa el complemento a `FALLIDO`; sus órdenes avisan «El complemento X no se puede usar en esta sesión por errores» y el gestor ofrece «&Inhabilitarlo» o «&Volver a intentarlo» (este último no, si falló por agotar el tope de carga de 3.4: hasta reiniciar).
- **Centinela**: antes de importar se crea `data/cache/plugins/cargando/<id codificado>` (un archivo por complemento, con la hora); se borra en un `finally` al terminar la carga, haya ido bien o mal (3.4). Si al arrancar queda alguno, el último arranque murió activando ese complemento: se arranca sin él (los demás se cargan) y se pregunta por cada uno (esencial, tras mostrar la ventana) «zCommander se cerró mientras cargaba el complemento X. ¿Inhabilitarlo?» con «&Inhabilitarlo» (predeterminado), «&Cargarlo de nuevo» y «&Preguntar la próxima vez».
- **Modo seguro**: `--sin-complementos`, Mayús pulsada al arrancar u orden «Reiniciar sin complementos». Se anuncia al arrancar («Modo seguro: complementos desactivados») y suena `app.sin_complementos`. Si zCommander se cerró de forma anómala dos veces seguidas (marcador en `data/cache/arranques.json`), el arranque siguiente lo propone.
- **Bloqueos de la interfaz**: un **solo hilo vigilante** propio (creado al arrancar, en `estado.py`), no un `faulthandler.dump_traceback_later` por llamada (en CPython cada uno cancela y crea un hilo, y el temporizador es global). Antes de cada llamada a un complemento en el hilo de la interfaz, `llamar_protegido` apila un **latido** (marca de tiempo e id del complemento; una pila, así una llamada anidada, como un manejador que ejecuta la orden de otro complemento, no borra la exterior) y lo desapila al volver; `ui.mostrar_modal` pone el latido en pausa mientras el diálogo está abierto. El vigilante mira el latido de arriba cada 0,5 s y, si pasa de 2 s, llama una vez a `faulthandler.dump_traceback(file=<archivo>, all_threads=True)` sobre el `fallo_nativo.log` que la 1.x ya tiene abierto (`app/core/registro.py`, un archivo con `fileno()`) y apunta qué complemento era. Así queda en el registro qué complemento bloqueó la interfaz, sin trazas falsas mientras la persona usa un diálogo.
- **Tiempo de los eventos**: se mide cada manejador de evento (sin el tiempo en diálogos modales); si pasa de 20 ms tres veces, se registra un aviso con el nombre (y se anuncia solo en modo desarrollo).
- **Columnas y proveedores lentos**: los extractores de columnas, visores, líneas de información y búsqueda de cada complemento van en un **grupo de hilos propio** de ese complemento (2 hilos como máximo, creado por `app/plugins/registro.py`), nunca en el `GestorTareas` de la ventana, para que un extractor colgado no deje sin hilos el listado de carpetas ni el espacio libre. Tiempo máximo de 5 s por valor, contado desde que la activación del complemento ha terminado (la espera a la carga no cuenta, 3.4); Python no puede matar un hilo, así que el que se agota se abandona y se cuenta: tres agotamientos en una carpeta detienen esa columna en esa carpeta con el aviso «La columna Duración tarda demasiado aquí», y con 4 hilos abandonados a la vez el complemento deja de recibir peticiones de columnas en la sesión (se anuncia una vez y el gestor lo dice).
- **Choques de bibliotecas**: el gestor detecta si dos complementos traen el mismo módulo de nivel superior en `lib/` y lo avisa; como el `MetaPathFinder` de cada complemento va al final de `sys.meta_path` (3.4), el primero que se activa resuelve ese nombre para los dos (gana el primero en `sys.modules`). Los complementos de serie no comparten ninguna biblioteca vendorizada (mutagen solo en `zc.metadatos`, pypdf solo en `zc.documentos`, dulwich solo en `zc.git`; los demás usan sus funciones con `zc.complemento`), así que no se renombran.
- **Auditoría opcional** (`complementos.auditoria`): un gancho `sys.addaudithook` registra `socket.connect` y `subprocess.Popen` originados en módulos `zcplugins.*` sin el permiso correspondiente. Solo registra; no es una barrera (PEP 578).

### 3.9 Seguridad: permisos, confianza y firma

- **Permisos declarados** (se muestran en lenguaje claro al instalar y en el gestor): `red` («conectarse a Internet y a la red local»), `internet:<host>` («conectarse a <host>»), `ejecutar_programas`, `escribir_fuera_de_paneles`, `portapapeles`, `secretos`, `sonido`, `segundo_plano`, `teclas_globales`, `elevacion` («pedir permisos de administrador»). No son una barrera técnica (un módulo Python puede hacer cualquier cosa), pero la API solo da la red (`zc.red`), los secretos (`zc.secretos`), `zc.ejecutar_programa` y las teclas globales a quien declara `red` o `internet:<host>`, `secretos`, `ejecutar_programas` y `teclas_globales`.
- **Firma Ed25519 opcional**: `firma.ed25519` en la raíz del paquete contiene, en base64, la firma de `b"zcommander-complemento-v1\n"` seguido del JSON canónico `{"id":..., "version":..., "archivos": {"ruta": "sha256", ...}}` de todos los archivos del paquete salvo la propia firma (serialización canónica de la plantilla del actualizador: claves ordenadas, sin espacios, UTF-8). El prefijo separa el dominio: una firma de complemento no vale como firma de un manifiesto de actualización ni al revés, aunque las firme la misma pareja de claves. Un paquete con algún archivo que no está en esa lista se rechaza.
- **Módulo `app/plugins/firma.py`** (sin wx; lo crea N2 y PL es su dueño posterior): `CLAVES_PROYECTO: tuple[str, ...]` (claves públicas del proyecto, en tupla para poder rotarlas, igual que `CLAVES_PUBLICAS_ED25519` del actualizador); `contenido_firmado(carpeta: Path, id: str, version: str) -> bytes` (el prefijo y el JSON canónico de arriba); `suma_paquete(carpeta: Path, id: str, version: str) -> str` (SHA-256 en hexadecimal de ese mismo contenido: la «suma del paquete»); `firmar_complemento(carpeta: Path, id: str, version: str, clave_privada: bytes) -> bytes` (la usan `tools/empaquetar_plugin.py` y `tools/publicar.py`); `verificar_complemento(carpeta: Path, claves: Sequence[str], *, comprobar_sumas: bool) -> ResultadoFirma` (`ResultadoFirma(valida: bool, clave: str | None, motivo: str)`; con `comprobar_sumas=False` solo comprueba la firma sobre la lista declarada y que los archivos presentes sean exactamente los de la lista, sin leerlos; con `True` lee y suma cada archivo). Las pruebas inyectan una clave de prueba; nunca usan la del proyecto.
- **Claves de confianza**: las del proyecto (`CLAVES_PROYECTO`) y las que la persona añada en el gestor («Confiar en este autor»), en `data/config/plugins/claves.json` (`{"version": 1, "confiadas": [...], "por_id": {"ana.utilidades": "<clave pública>"}}`).
- **Clave fijada por id** (confianza en el primer uso): la primera vez que se instala un complemento firmado, su clave queda fijada para ese id en `por_id`. Una actualización de ese id tiene que venir firmada con la misma clave; sin firma o con otra clave se rechaza («Esta actualización no está firmada por el mismo autor que la versión instalada»). Cambiar de clave exige desinstalar y volver a instalar con la confirmación de un complemento nuevo. Los `zc.*` de `data/plugins/` solo aceptan `CLAVES_PROYECTO`. **La clave fijada también se exige al cargar**: un id que está en `por_id` y cuya carpeta no trae una firma válida de esa clave (por ejemplo, porque alguien borró `firma.ed25519` o cambió un archivo) se rechaza al descubrir, con «El complemento X ya no lleva la firma de su autor; no se carga».
- **Confianza por ubicación**: los complementos de `<raíz>/plugins/` cuyo id y versión están en `app/plugins/serie.py` (los de serie) son «Oficial» sin firma, ni desde el código fuente ni compilados (3.2); cualquier otro de esa carpeta se trata como uno de `data/plugins/`. La firma del proyecto solo hace falta para un `zc.*` fuera de esa lista, que es la forma de publicar una actualización de un complemento de serie sin una versión nueva de zCommander (`tools/publicar.py --firmar-complementos`, 5.6).
- **Consentimiento para lo que no tiene firma** (`complementos.confiados`, diccionario `id → suma del paquete aceptada`): cuando la persona instala desde el gestor un complemento sin firma y acepta la advertencia, se guarda su `suma_paquete`. Un complemento sin firma de `data/plugins/` (o de `.pendientes/`, o de `<raíz>/plugins/` fuera de la lista de serie) solo se carga si su id está en `confiados` con la suma de lo que hay en disco; si no (carpeta copiada a mano, carpeta portable sincronizada, otro programa, o archivos cambiados después de aceptarlo, también si el cambio se descubre al activar, 3.4), queda `SIN_ACEPTAR`: no se importa nada y, tras mostrar la ventana, se pregunta una vez por cada uno «Hay un complemento sin firma que no se instaló desde zCommander: X, de Y. Ejecutará código con sus mismos permisos de Windows. ¿Aceptarlo?» con «&No aceptarlo» (predeterminado), «&Aceptarlo» y «Ver los &detalles...» (el resumen de 3.10). Aceptarlo guarda su suma en `confiados`. Al actualizar o desinstalar se actualiza o se borra su entrada. `confiados` nunca viaja en una copia de seguridad (7.2).
- **Cuándo se comprueba**: al descubrir, en cada arranque, se verifica la firma de los complementos firmados de `data/plugins/` sobre su lista de archivos (`comprobar_sumas=False`: barato, sin leer los archivos) y que su id cumpla la clave fijada; `indice.json` solo ahorra volver a validar el manifiesto, nunca la firma. Las sumas de los archivos se comprueban **al activar y al leer cada archivo**: en el paso 2 de 3.4 (todas, antes de importar nada) y otra vez, archivo por archivo, al importarlo. Así el arranque desde un pendrive no lee miles de archivos. Fuentes de las sumas: la lista firmada, la de `complementos.confiados` (que se calcula al aceptar) o, para los de serie en la versión compilada, `serie.SUMAS`; desde el código fuente los de serie no se comprueban (`SUMAS = None`).
- **Cargador de módulos verificado** (`app/plugins/cargador.py`): todo módulo de `zcplugins.<id>` (la entrada, los submódulos que se importan tarde, como `from .ui import ventana` dentro de un manejador, y lo de `lib/` que resuelve su `MetaPathFinder`) se carga con `CargadorVerificado`, subclase de `importlib.machinery.SourceFileLoader` para los `.py` y de `ExtensionFileLoader` para los `.pyd`. Para un `.py`, lee el archivo **una vez**, comprueba su SHA-256 contra la lista ya validada y compila **desde esos mismos bytes** (`source_to_code`); un archivo que no está en la lista o cuya suma no coincide lanza `ImportError` («El archivo X del complemento Y ha cambiado») y cuenta como fallo de importación (3.8). Los complementos de `data/plugins/` **nunca** leen ni escriben `.pyc` (`get_code` no usa la caché), así una `.pyc` dejada en `data/cache/pycache/` no se ejecuta; los de serie pueden usar `.pyc` solo con validación por hash (`CHECKED_HASH`) contra la fuente ya comprobada. Una `.pyd` no se puede cargar desde bytes: se comprueba su suma justo antes de `create_module`; esa ventana mínima entre comprobar y cargar la acepta el modelo de amenaza de 16.
- **Tres niveles de confianza**, mostrados como texto: «Oficial» (de serie en `<raíz>/plugins/`, o firma del proyecto), «Firmado por un autor de confianza» y «Sin firma». Instalar uno sin firma muestra: «Este complemento no está firmado. Ejecutará código con sus mismos permisos de Windows. Instálelo solo si confía en su autor.»; el botón predeterminado es «&Cancelar». `complementos.permitir_sin_firma` (sí por defecto) puede prohibirlos.
- **Marca de la Web**: si el `.zcplugin` la tiene, la pregunta lo dice («Descargado de Internet»).
- **Paquete seguro**: se valida el ZIP entero antes de escribir nada, con las reglas de `extraer_seguro` de la plantilla del actualizador (sin rutas absolutas, `..`, unidades, flujos alternativos, nombres reservados, enlaces ni duplicados; 200 MB expandido y 20 000 miembros como máximo).

### 3.10 Instalar, actualizar, desinstalar

- **Instalar desde archivo**: botón del gestor, orden `complemento_instalar` o Intro sobre un `.zcplugin` en un panel. Pasos: validar el paquete, leer el manifiesto, comprobar compatibilidad, firma, licencia, dependencias y componentes; mostrar un **resumen accesible** en un texto de solo lectura (nombre, versión, autor, licencia, confianza, procedencia, permisos, dependencias, componentes, lista de archivos y tamaño); botones «&Instalar» y «&Cancelar». Regla única de dónde se extrae:
  - Si ese `id` no está registrado en esta sesión (ni en `plugins/` ni en `data/plugins/`) y no tiene `al_arrancar`: se extrae a una carpeta temporal hermana, se renombra a `data/plugins/<id>/`, se registran sus marcadores y queda listo sin reiniciar (se activa al primer uso). La validación y la extracción van en un hilo; el registro de marcadores y la subida del contador de versión del catálogo se hacen **solo en el hilo de la interfaz** (con el planificador), porque el registro y `CATALOGO` se recorren desde él (paleta, despachador). Un hilo que necesite leer el catálogo usa la instantánea inmutable que devuelve `catalogo()` (una tupla, 14.1.1). Si es sin firma, al instalar se guarda su suma en `complementos.confiados` (3.9).
  - En cualquier otro caso (actualización, o complemento con `al_arrancar`): se extrae a `data/plugins/.pendientes/<id>/`, su `Pendiente` pasa a `INSTALAR` o `ACTUALIZAR` y se ofrece «&Reiniciar ahora».
- `instalacion.py` opcional en el paquete con `al_instalar(zc)` y `al_desinstalar(zc)`: sin preguntas. Se ejecutan **en un hilo de trabajo** con el `Anfitrion` normal del complemento (sin `ui`: lanza `NoAdmitido`) y el hilo de la interfaz espera su futuro sin bloquearse, con 30 s como máximo; si se agota, se registra y se trata como un fallo (el hilo se abandona, como en 3.8). Si `al_instalar` falla o se agota, la instalación se deshace. Los de lo aplicado al reiniciar (3.4, paso 1) se ejecutan después de mostrar la ventana, no antes: así no hace falta ningún perfil de arranque sin interfaz y no alargan el arranque que vigila el actualizador (5.2).
- **Actualizar**: misma vía con una versión más alta del mismo `id`, firmada con la clave fijada para ese id si la instalada estaba firmada (3.9). La carpeta se sustituye entera al reiniciar (la anterior va a `data/plugins/.anteriores/<id>-<versión>/`, se guardan las dos últimas); la configuración y los datos sobreviven porque viven en `data/config/plugins/`. Si cambia la versión principal de la API que pide, se avisa antes.
- **Buscar actualizaciones de complementos**: para los que declaran `url_actualizacion`, el gestor descarga ese JSON (`{"id", "version", "url", "sha256", "tamano", "novedades", "firma_ed25519"}`, https, firmado con la misma clave que el paquete si el paquete está firmado) cuando la persona pulsa «Buscar actualizaciones» y, si `actualizaciones.complementos_comprobar` está activa, junto a la comprobación periódica de la aplicación (5.4), en la que PL se registra con `actualizador.registrar_comprobacion` (5.4). Nunca instala sin que la persona lo confirme.
- **Volver a la versión anterior**: desde `data/plugins/.anteriores/`, aplicado al reiniciar.
- **Desinstalar**: se marca y se borra al reiniciar; pregunta aparte «¿Borrar también su configuración y sus datos?» (por defecto «No»). Sus teclas personalizadas se conservan por si se reinstala. Los de serie no se desinstalan: se inhabilitan.

### 3.11 Gestor de complementos (ventana)

`app/ui/dialogos/pl_gestor.py`, orden `complementos` (menús Complementos y Opciones):

- Lista nativa (`ListaAccesible`) con columnas Nombre, Versión, Estado (texto: «Activo», «Sin cargar todavía», «Inhabilitado», «Sin aceptar», «Incompatible: necesita la API 1.1», «Falló al cargar», «Fuera de uso por errores», «Error en el manifiesto», y tras una coma el cambio pendiente si lo hay: «Activo, se actualizará al reiniciar», «Inhabilitado, se desinstalará al reiniciar», «Se instalará al reiniciar»), Origen («De serie», «Instalado»), Confianza y Autor.
- Texto de solo lectura con la descripción, permisos, licencia, web, componentes que usa, tiempo de carga y, si falló, el último error.
- Botones: «&Habilitar» o «In&habilitar» (y «&Aceptar» en uno `SIN_ACEPTAR`), «Con&figurar», «A&yuda», «&Novedades», «&Instalar desde un archivo...», «&Buscar actualizaciones», «Volver a la versión an&terior», «D&esinstalar», «Abrir su ca&rpeta», «Ver su re&gistro» (líneas del registro con `zcplugins.<id>`), «Ver los &permisos» y «&Cerrar». «&Reiniciar ahora» aparece cuando hay cambios pendientes. Las letras exactas las comprueba `revisar_teclado`.
- Intro en la lista equivale a «Configurar»; Supr a «Desinstalar» (con confirmación); Espacio a «Habilitar o inhabilitar».
- «Información para soporte» (1.x §12) añade la lista de complementos instalados con versión, estado y confianza (14.9).

### 3.12 Herramientas para autores

- `tools/crear_plugin.py <carpeta> --id ana.ejemplo --nombre "Ejemplo"`: genera una plantilla con manifiesto, una orden, una página de Preferencias con una clave, un sonido, ayuda, `LICENSE` (GPL-3.0) y una prueba con `api.pruebas`. La plantilla es `tools/plantilla_plugin/`.
- `tools/validar_plugin.py <carpeta o .zcplugin>`: valida el manifiesto, licencias, letras y teclas (contra el catálogo del núcleo y de los complementos de serie), los nombres de `lib/` (3.3), importa el complemento en un proceso limpio, ejecuta `revisar_teclado` sobre sus ventanas (las que devuelve el método opcional `Complemento.ventanas_para_revisar(padre)`, 3.7), ejecuta sus pruebas y devuelve 0 si todo va bien.
- `tools/empaquetar_plugin.py <carpeta> [--firmar <clave>]`: crea el `.zcplugin` y, si se pide, su `firma.ed25519` con `app.plugins.firma.firmar_complemento` (3.9; no con `tools/firmar_version.py`, que firma manifiestos de actualización con otro prefijo).
- **Modo desarrollo** (`--desarrollo-complementos <carpeta>` o `complementos.modo_desarrollo`): carga un complemento desde una carpeta cualquiera, añade al catálogo la orden `complemento_recargar` («Recargar el complemento en desarrollo», que solo existe en este modo, 14.1.2) y anuncia los avisos de tiempo y de accesibilidad.
- Guía del autor: `docs/complementos/guia.md` (bloque DO), con las reglas de accesibilidad de 15.3.

### 3.13 Módulos

- Sin wx (`app/plugins/`, regla de capas de `tests/test_n_arquitectura.py::test_capas_sin_interfaz`, que N2 amplía a `app/plugins` **sin ninguna excepción**: ningún módulo de `app/plugins` importa wx ni `app.ui`, ni siquiera de forma perezosa):
  - `api.py`: la fachada, con `fijar_interfaz` (3.7). `ModuloUI` delega en `app.ui.api_ui` y `ContextoComplemento` recibe sus paneles de la interfaz, todo por la única inyección de `InterfazAnfitrion`.
  - `interfaz.py` (N2): el protocolo `InterfazAnfitrion` (3.7).
  - `serie.py`: `SERIE` (lo genera `tools/generar_anexos.py`) y `SUMAS` (de `serie_sumas.py`, que genera `setup_cx.py` solo para la compilada) de los complementos de serie (3.2).
  - `estado.py` (N2): `EstadoComplemento`, `Pendiente`, `llamar_protegido` con el contador de fallos y el paso a `FALLIDO`, y el hilo vigilante de bloqueos (3.8).
  - `firma.py` (N2): firma y verificación de complementos (3.9).
  - `manifiesto.py`: lectura y validación (3.3).
  - `registro.py` (`app/plugins/registro.py`, no confundir con `app/core/registro.py`, el registro de la aplicación): marcadores y registros de funciones, y `ObjetivoCongelado` (3.4). Contratos que usan otros módulos:
    - `registrar_serie(carpeta: Path | None = None) -> None`: lee los manifiestos de los complementos de serie (`carpeta`, por defecto `paths.ruta_plugins_serie()`), los valida y registra sus marcadores **sin importar código ni leer la configuración de la persona**; la usan `tools/generar_anexos.py`, `comprobar_menus.py`, `comprobar_teclas.py`, `generar_provisionales.py` y la fixture `complementos_serie` de las pruebas (18.1). `vaciar() -> None` deja el registro vacío (solo pruebas).
    - `catalogo_columnas() -> list[ColumnaExterna]`, con `@dataclass(frozen=True) ColumnaExterna(id: str, titulo: str, tipo: str, lenta: bool, complemento: str)` (`id` = `<id del complemento>:<columna>`; `tipo` el de `[[columnas]]`, que la lista usa para ordenar y alinear; lo leen `ListaArchivos` y el diálogo de columnas de PE).
    - `valor_columna(id: str, entrada: Entrada, proveedor: Proveedor, al_listo: Callable[[], None]) -> str | None` [interfaz]: nunca bloquea. Si el valor está en la caché por (ruta, tamaño, fecha), lo devuelve; si no, manda el cálculo al grupo de hilos del complemento (activándolo si hace falta, 3.4) y devuelve `None`: la lista muestra «…» y, cuando el valor llega (o se agota el tiempo y queda «Sin datos»), `al_listo` se llama en el hilo de la interfaz y la lista repinta esa fila.
    - `lineas_info(entrada: Entrada, proveedor: Proveedor) -> list[str]` [trabajo]: las líneas de todos los complementos cuyo `[[info]]` coincide, en el orden de los complementos; las de un complemento que falla o se agota se omiten.
    - `acciones_error_aplicables(pregunta: PreguntaError) -> list[AccionAplicable]` [interfaz] (nunca activa un complemento: decide con `codigos_windows` del manifiesto y, si está activo, con su `aplica()`, 3.4), con `@dataclass(frozen=True) AccionAplicable(id: str, etiqueta: str, funcion: Callable[[PreguntaError], AccionError | None])` (14.6).
  - `cargador.py`: descubrimiento, `CargadorVerificado` y el `MetaPathFinder` de `lib/` (3.9), centinelas, la máquina de estados de la activación con el hilo `zc-cargador` y `TIEMPO_CARGA_S` (`asegurar_activo`, 3.4), `fijar_planificador(planificador)` (función del módulo), `arrancar`, `congelar`, `descongelar`, `cerrar` y `ejecutar_tarea_programada` (11.24).
  - `gestor.py` (PL): gestión de lo instalado, pendientes, consentimientos.
  - `paquetes.py` (PL): validar, instalar, actualizar, desinstalar.
  - `config_plugins.py`, `auditoria.py`, `prueba.py` (`--complemento-prueba`, 14.8).
- Con wx: `app/ui/api_ui.py` (lo que `ModuloUI` delega: diálogos accesibles, `VentanaComplemento`, `mostrar_modal`; N2, dueño posterior PL), `app/ui/interfaz_anfitrion.py` (la implementación de `InterfazAnfitrion` sobre la ventana; N2), `app/ui/dialogos/pl_gestor.py`, `pl_instalar.py` (resumen), `app/ui/acciones/complementos_pl.py` (órdenes del núcleo y el manejador genérico `ejecutar`, que crea el `ContextoComplemento` a partir del `ContextoOrden`).

## 4. Sonidos

Sustituye `app/ui/sonidos.py` de la 1.x (tres avisos con `MessageBeep` o con los WAV opcionales `operacion_terminada.wav`, `operacion_error.wav` y `carpeta_vacia.wav` de `data/sounds`, y tonos con `Beep`). Modelo: el de socialrss (socialrss-youtubero.md 2) con un solo catálogo en lugar de tres listas.

### 4.1 Principios

- **Un sonido nunca sustituye a la información**: todo lo que suena se puede saber de otra forma (anuncio, consulta, historial, ventana de operaciones). La excepción es voluntaria: `sonidos.sustituir_anuncios` (4.5).
- **Corto y sin tapar la voz**: los de navegación duran 150 ms como mucho; los de resultado, 600 ms; solo el de arranque llega a 1,2 s.
- **Nunca bloquea**: pedir un sonido encola y vuelve; la reproducción va en un hilo propio.
- **Una sola fuente de verdad**: `app/services/sonidos/catalogo.py` (sin wx). De ahí salen Preferencias, el mapa de sonidos, el anexo `data/docs/sonidos.md`, el generador y las pruebas de completitud de los paquetes.

### 4.2 Catálogo de eventos

Cada evento es un `EventoSonido(id, nombre, descripcion, categoria, prioridad, por_defecto, variantes=(), sustituye_anuncio=False)`:

- `id`: `categoria.nombre` en el núcleo, siempre con un punto; `<id del complemento>:<nombre>` en los complementos.
- `categoria`: en el núcleo, el prefijo del id (`nav`, `panel`, `tecla_global`...); en los complementos, `plugin:<id del complemento>`. El nombre visible de cada categoría está en `CATEGORIAS: dict[str, str]` de `catalogo.py` («Navegación», «Teclas globales»...; para `plugin:<id>`, el nombre del complemento).
- **Archivo**: en el núcleo, el id con los puntos cambiados por guiones bajos y `.wav` (`nav.carpeta_vacia` → `nav_carpeta_vacia.wav`); con variantes, `<archivo>_<variante>.wav`. En un complemento, `<nombre>` es la parte del id tras «:»: dentro de un **paquete de sonidos**, `plugins/<id del complemento>/<nombre>.wav`; dentro del **paquete del complemento** (`.zcplugin` o su carpeta), `sonidos/<nombre>.wav` (o el `archivo` de su `[[sonidos]]`).
- `prioridad`: `alta` (errores, preguntas, decisiones, fin de operaciones, actualizaciones), `media` (resultados) o `baja` (navegación, cursor, marcas).
- `por_defecto`: si suena con los valores de fábrica. Los de cursor y navegación vienen desactivados porque compiten con el lector.
- `sustituye_anuncio`: el anuncio que acompaña al evento se puede omitir si suena (4.5).

En las tablas, «Fábrica» dice si está activo por defecto y «Sust.» si puede sustituir su anuncio.

#### Sistema (`app`, prioridad alta)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `app.arranque` | Arranque | Aparece la ventana principal | Sí | No |
| `app.cierre` | Cierre | zCommander va a cerrarse | No | No |
| `app.sin_complementos` | Modo seguro | Arranca sin complementos | Sí | No |

#### Navegación (`nav`, prioridad baja salvo indicación)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `nav.entrar` | Entrar en una carpeta | Intro o Ctrl+Av Pág en una carpeta | No | No |
| `nav.subir` | Subir de carpeta | Retroceso, «..» o Alt+Arriba | No | No |
| `nav.raiz` | Raíz | Se llega a la raíz de la unidad | No | No |
| `nav.carpeta_vacia` | Carpeta vacía | La carpeta abierta no tiene elementos (media) | Sí | Sí |
| `nav.leyendo` | Lectura lenta | Leer la carpeta tarda más que `general.aviso_lectura_ms` | No | Sí |
| `nav.historial` | Historial | Atrás o Adelante | No | No |
| `nav.unidad` | Cambio de unidad | Se elige otra unidad u origen | No | No |
| `nav.entrar_comprimido` | Entrar en un comprimido | Se abre un comprimido como carpeta (media) | Sí | No |
| `nav.salir_comprimido` | Salir de un comprimido | Retroceso en la raíz del comprimido | No | No |
| `nav.lista_resultados` | Lista de resultados | El panel muestra una búsqueda, vista plana o cesta (media) | Sí | No |
| `nav.tope` | Principio o final | Arriba en la primera fila o Abajo en la última | No | No |
| `nav.carpeta_desaparecida` | Carpeta borrada | La carpeta abierta desapareció y el panel subió (alta) | Sí | No |

#### Cursor (`cursor`, prioridad baja; suenan al llegar el cursor a un elemento)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `cursor.carpeta` | Carpeta | El cursor llega a una carpeta | No | No |
| `cursor.archivo` | Archivo | El cursor llega a un archivo | No | No |
| `cursor.comprimido` | Comprimido | El cursor llega a un comprimido que se puede abrir como carpeta | No | No |
| `cursor.ejecutable` | Ejecutable | El cursor llega a un `.exe`, `.bat`, `.cmd`, `.msi`, `.ps1`... | No | No |
| `cursor.enlace` | Enlace | El cursor llega a un enlace o unión | No | No |
| `cursor.oculto` | Oculto | El cursor llega a un elemento oculto o de sistema | No | No |
| `cursor.marcado` | Marcado | El cursor llega a un elemento marcado | No | No |
| `cursor.nube` | Solo en la nube | El cursor llega a un archivo no descargado | No | No |
| `cursor.superior` | Fila «..» | El cursor llega a la fila para subir | No | No |

Si varios se aplican (un comprimido oculto y marcado), suena solo el primero de esta prioridad: marcado, comprimido, ejecutable, enlace, nube, oculto, carpeta o archivo.

#### Marcas (`marca`, prioridad baja)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `marca.marcar` | Marcar | Se marca un elemento | Sí | Sí |
| `marca.desmarcar` | Desmarcar | Se desmarca un elemento | Sí | Sí |
| `marca.grupo` | Marcar en grupo | Marcar por patrón, todo o por extensión | Sí | No |
| `marca.quitar_todas` | Desmarcar todo | Se quitan todas las marcas | Sí | Sí |
| `marca.invertir` | Invertir | Se invierten las marcas | Sí | No |
| `marca.restaurar` | Restaurar | Se restauran las marcas anteriores | No | No |

#### Paneles, pestañas y vistas (`panel`, `pestana`, `vista`, `filtro`, `busqueda_rapida`, `orden`; prioridad baja)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `panel.cambiar` | Cambiar de panel | Tab | No | No |
| `panel.oculto` | Otro panel oculto | Tab con el otro lado oculto (media) | Sí | Sí |
| `pestana.nueva` | Pestaña nueva | Se abre una pestaña | No | No |
| `pestana.cerrar` | Cerrar pestaña | Se cierra una pestaña | No | No |
| `pestana.cambiar` | Cambiar de pestaña | Se pasa a otra pestaña | No | Sí |
| `vista.cambiar` | Cambiar de vista | Completa, breve, Información, Árbol o Vista rápida | No | No |
| `filtro.aplicar` | Filtro aplicado | Se aplica un filtro o el filtro rápido | No | No |
| `filtro.quitar` | Filtro quitado | Se quita el filtro | No | Sí |
| `busqueda_rapida.sin_coincidencia` | Sin coincidencias | La búsqueda rápida no encuentra nada (media) | Sí | No |
| `busqueda_rapida.fin` | Fin de la búsqueda rápida | Pasa el tiempo de la búsqueda rápida (sustituye al tono de la 1.x §5.5) | No | No |
| `orden.cambiar` | Cambio de orden | Ctrl+F3 a Ctrl+F7 | No | No |

#### Ventanas, diálogos y menús (`dialogo`, `menu`, `paleta`, `ayuda_teclado`, `salida`, `barra_botones`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `dialogo.abrir` | Abrir diálogo | Se abre un diálogo de zCommander (baja) | No | No |
| `dialogo.cerrar` | Cerrar diálogo | Se cierra un diálogo (baja) | No | No |
| `menu.abrir` | Abrir menú | F9, Alt o un menú contextual (baja) | No | No |
| `menu.cerrar` | Cerrar menú | Se cierra el menú sin elegir (baja) | No | No |
| `paleta.abrir` | Paleta de órdenes | Ctrl+E (baja) | No | No |
| `ayuda_teclado.entrar` | Entrar en la ayuda de teclado | Mayús+F12 activa el modo (media) | Sí | No |
| `ayuda_teclado.salir` | Salir de la ayuda de teclado | Escape o Mayús+F12 lo desactivan (media) | Sí | No |
| `salida.mostrar` | Salida de las órdenes | Ctrl+O muestra la salida (baja) | No | No |
| `barra_botones.entrar` | Barra de botones | El foco entra en la barra de botones (baja) | No | No |

#### Avisos (`aviso`, prioridad alta)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `aviso.error` | Error | Se muestra o anuncia un error | Sí | No |
| `aviso.advertencia` | Advertencia | Se muestra una advertencia | Sí | No |
| `aviso.informacion` | Información | Se muestra un mensaje informativo | No | No |
| `aviso.pregunta` | Pregunta | Se abre una confirmación | Sí | No |
| `aviso.no_disponible` | No disponible | Orden que no se puede usar aquí o «No hay elementos» | Sí | Sí |
| `aviso.sin_permiso` | Sin permiso | Windows niega el acceso | Sí | No |

#### Operaciones (`op`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `op.inicio` | Empieza una operación | Una operación pasa a «En marcha» (media) | Sí | Sí |
| `op.progreso` | Progreso | Variantes `10` a `90` (y `25`, `75`): cada 10 % o cada 25 % según `sonidos.progreso` (baja) | Sí (lo filtra `sonidos.progreso`) | No |
| `op.pausa` | Pausa | Una operación se pausa (media) | Sí | Sí |
| `op.reanudar` | Reanudar | Una operación se reanuda (media) | Sí | Sí |
| `op.decision` | Espera su decisión | Una operación espera una respuesta (alta) | Sí | No |
| `op.fin` | Terminada | Una operación termina bien (alta) | Sí | No |
| `op.fin_errores` | Terminada con errores | Termina con errores u omitidos (alta) | Sí | No |
| `op.cancelada` | Cancelada | Se cancela una operación (alta) | Sí | No |
| `op.fallida` | Fallida | Una operación falla por completo (alta) | Sí | No |
| `op.en_cola` | En cola | Una operación espera en la cola (baja) | No | Sí |
| `op.conflictos` | Conflictos | Se abre la lista de conflictos (alta) | Sí | No |
| `op.deshacer` | Deshacer | Se deshace una acción (media) | Sí | No |
| `op.papelera` | A la papelera | Termina un envío a la papelera (media) | No | No |
| `op.eliminado` | Eliminado | Termina una eliminación definitiva (media) | No | No |
| `op.carpeta_creada` | Carpeta creada | Se crea una carpeta (media) | No | Sí |
| `op.renombrado` | Renombrado | Se renombra un elemento (media) | No | Sí |

#### Portapapeles (`portapapeles`, prioridad media)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `portapapeles.copiar` | Copiar al portapapeles | Ctrl+C con archivos | Sí | Sí |
| `portapapeles.cortar` | Cortar | Ctrl+X con archivos | Sí | Sí |
| `portapapeles.pegar` | Pegar | Ctrl+V lanza la copia | No | No |
| `portapapeles.texto` | Texto copiado | Se copian rutas, nombres o la ruta de la carpeta | No | Sí |

#### Búsqueda y comparación (`busqueda`, `comparar`, `tamano`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `busqueda.inicio` | Empieza la búsqueda | Buscar archivos empieza (baja) | No | No |
| `busqueda.primer_resultado` | Primer resultado | Aparece el primer resultado (baja) | No | No |
| `busqueda.fin` | Búsqueda terminada | Termina con resultados (media) | Sí | No |
| `busqueda.sin_resultados` | Sin resultados | Termina sin resultados (media) | Sí | No |
| `comparar.iguales` | Iguales | Comparar carpetas o archivos: son iguales (media) | Sí | No |
| `comparar.diferencias` | Diferencias | Comparar carpetas o archivos: hay diferencias (media) | Sí | No |
| `tamano.calculado` | Tamaño calculado | Termina el cálculo del tamaño de carpetas (media) | No | No |

#### Línea de órdenes (`linea`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `linea.ejecutar` | Ejecutar | Intro en la línea de órdenes (baja) | No | No |
| `linea.fin` | Orden terminada | La orden termina con código 0 (media) | Sí | No |
| `linea.error` | Orden con error | La orden termina con otro código (alta) | Sí | No |

#### Comprimidos (`comprimido`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `comprimido.probado` | Comprimido correcto | Probar comprimido termina sin errores (media) | Sí | No |
| `comprimido.danado` | Comprimido dañado | Probar o abrir encuentra daños (alta) | Sí | No |
| `comprimido.contrasena` | Pide contraseña | Un comprimido cifrado pide la contraseña (alta) | Sí | No |
| `comprimido.cifrado_sin_motor` | Cifrado no admitido | Un RAR o 7z cifrado sin 7-Zip instalado (alta) | Sí | No |

#### Red (`red`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `red.conectar` | Conectado | Se conecta un servidor, una unidad o un recurso (media) | Sí | No |
| `red.desconectar` | Desconectado | Se desconecta (media) | Sí | No |
| `red.perdida` | Conexión perdida | Se pierde una conexión (alta) | Sí | No |
| `red.reconectada` | Reconectada | Una unidad o conexión vuelve (media) | Sí | No |
| `red.equipo` | Equipo encontrado | El descubrimiento encuentra un equipo (baja) | No | No |
| `red.descubrir_fin` | Búsqueda de equipos terminada | Termina el descubrimiento (media) | No | No |
| `red.credenciales` | Pide credenciales | Un servidor pide usuario y contraseña (alta) | Sí | No |
| `red.huella` | Huella nueva | Huella o certificado desconocido o cambiado (alta) | Sí | No |

#### Actualizaciones y componentes (`act`, `comp`; prioridad alta)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `act.disponible` | Actualización disponible | Hay una versión nueva de zCommander | Sí | No |
| `act.descargada` | Actualización descargada | Termina la descarga y se puede instalar | Sí | No |
| `act.instalada` | Actualización instalada | Primer arranque correcto de la versión nueva | Sí | No |
| `act.revertida` | Actualización revertida | Se volvió a la versión anterior | Sí | No |
| `act.al_dia` | Sin novedades | La comprobación manual no encuentra nada (media) | No | No |
| `comp.disponible` | Componentes nuevos | Hay versiones nuevas de componentes | Sí | No |
| `comp.actualizado` | Componente actualizado | Un componente se actualizó y pasó su prueba | Sí | No |
| `comp.revertido` | Componente revertido | Un componente volvió a la versión anterior | Sí | No |

#### Complementos (`plugin`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `plugin.instalado` | Complemento instalado | Se instala o actualiza un complemento (media) | Sí | No |
| `plugin.activado` | Complemento activado | Se carga su código (baja) | No | No |
| `plugin.inhabilitado` | Complemento inhabilitado | La persona lo inhabilita en el gestor (baja) | No | No |
| `plugin.fallo` | Complemento con fallos | Un complemento falla o queda fuera de uso por errores (alta) | Sí | No |
| `plugin.cargando` | Cargando complemento | La carga tarda más de 300 ms (baja) | No | Sí |

#### Copias, macros, reglas y personalización (`copia`, `macro`, `regla`, `espacio`, `tecla_global`)

| id | Nombre | Cuándo suena | Fábrica | Sust. |
|---|---|---|---|---|
| `copia.creada` | Copia creada | Termina una copia de seguridad (media) | Sí | No |
| `copia.restaurada` | Copia restaurada | Termina una restauración (media) | Sí | No |
| `macro.grabar` | Grabación empezada | Empieza la grabación de una macro (media) | Sí | Sí |
| `macro.parar` | Grabación terminada | Termina la grabación (media) | Sí | Sí |
| `macro.paso` | Paso de macro | Se ejecuta cada paso (baja) | No | No |
| `macro.fin` | Macro terminada | Termina una macro (media) | No | No |
| `regla.a` | Aviso de regla A | Lo eligen las reglas (10.10) (baja) | Sí | No |
| `regla.b` | Aviso de regla B | Ídem | Sí | No |
| `regla.c` | Aviso de regla C | Ídem | Sí | No |
| `espacio.abierto` | Espacio de trabajo | Se abre un espacio de trabajo (media) | No | Sí |
| `tecla_global.recibida` | Tecla global | Llega una tecla global con zCommander en segundo plano (media) | No | No |

Total del núcleo: **122 eventos** (más las 11 variantes de `op.progreso`: 10, 20, 25, 30, 40, 50, 60, 70, 75, 80 y 90). Los complementos de serie añaden **31** (sus fichas en las secciones 11 a 13). Los complementos de la persona añaden los suyos con `[[sonidos]]`.

### 4.3 Dónde se piden

- Función única, sin wx, en `app/services/sonidos/servicio.py` (N2; así la pueden llamar los servicios: `comp.*`, `copia.*`, `red.equipo` desde el descubrimiento, los hilos de los complementos). **Una sola firma** en todo el documento, la misma en `ContextoOrden.sonar`, `ContextoComplemento.sonar` y `Anfitrion.sonidos.sonar`: `sonar(evento: str, variante: str = "", *, sustituye: bool = False) -> bool`. Se puede llamar desde cualquier hilo. El servicio solo filtra (sonidos activos según `sonidos.activos` y evento activo según el diccionario calculado al cambiar la configuración) y pasa la petición al reproductor; devuelve lo que diga el reproductor. Verdadero quiere decir que el sonido se **aceptó** (4.4). `sustituye=True` lo pone `anuncios.anunciar` cuando la petición puede sustituir un anuncio (abajo).
- La reproducción se inyecta: `servicio.iniciar(config: Configuracion, reproductor: Reproductor) -> None` y `servicio.cerrar() -> None`. Protocolo completo (en `servicio.py`):

```python
class Reproductor(Protocol):
    def sonar(self, evento: EventoSonido, variante: str, sustituye: bool) -> bool
        # Resuelve el archivo (paquete, herencia, archivo del complemento: 4.4), aplica el volumen y la caché,
        # decide con la cola de prioridades y encola. Verdadero si lo aceptó: volumen mayor que 0, archivo
        # encontrado y válido, y no descartado en el momento. Con sustituye=True la decisión es definitiva (4.4).
        # Menos de 5 ms; nunca bloquea.
    def recargar(self) -> None      # cambió el paquete, el volumen o los paquetes instalados: vacía la caché
    def cerrar(self) -> None        # vacía la cola, para el sonido en curso y espera al hilo 0,5 s como máximo
```

  El motor de 4.4 (`app/services/sonidos/motor.py`, SO) es el reproductor real. `app/ui/sonidos.py` lo reescribe N2 con dos funciones, `iniciar(config: Configuracion) -> None` (crea el reproductor y llama a `servicio.iniciar`) y `cerrar() -> None`, que llama la ventana al construirse y al salir; desaparece la clase `Sonidos(config)` de la 1.x. Mientras SO no termina, el reproductor de N2 es provisional: el `winsound` de la 1.x para `op.fin`, `op.fin_errores`, `aviso.error` y `nav.carpeta_vacia`, y falso (no aceptado) para el resto. SO es el dueño posterior de `app/ui/sonidos.py`. Sin reproductor (pruebas, `--probar-componente`), `sonar` devuelve falso y no hace nada.
- **Quién pone cada llamada** (lista completa por id o por categoría; los ids son los de 4.2):
  - **N2**, en los puntos del núcleo 1.x, con el reproductor provisional: `app.arranque` y `app.cierre`; todos los de `nav.*`, `cursor.*`, `marca.*`, `panel.*`, `pestana.*`, `vista.*`, `filtro.*`, `busqueda_rapida.*`, `orden.cambiar`, `dialogo.*`, `menu.*`, `paleta.abrir`, `ayuda_teclado.*`, `salida.mostrar`, `aviso.*`, `op.*`, `portapapeles.*`, `busqueda.*`, `comparar.*`, `tamano.calculado` y `linea.*`; de comprimidos, solo `comprimido.probado` y `comprimido.danado`; de red, `red.conectar`, `red.desconectar`, `red.perdida` y `red.huella`. También cambia la llamada de la 1.x `sonidos.aviso("carpeta_vacia")` de `panel_archivos.py` por `sonar("nav.carpeta_vacia")` y las de `ventana_principal.py` (19.1).
  - **PL**: `app.sin_complementos` y todos los `plugin.*`.
  - **AC**: todos los `act.*`. **CO**: todos los `comp.*`. **CS**: `copia.creada` y `copia.restaurada`.
  - **CM**: `comprimido.cifrado_sin_motor` y `comprimido.contrasena`.
  - **RD**: `red.equipo`, `red.descubrir_fin`, `red.credenciales` y `red.reconectada`.
  - **PE**: todos los `macro.*` y `regla.*`, `espacio.abierto`, `tecla_global.recibida` y `barra_botones.entrar`.
  - **Cada complemento**: los suyos (`<id>:<nombre>`). **SO** pone el motor real y no pone llamadas.
- `anuncios.anunciar` gana el parámetro opcional `sonido: str = ""`: pide el sonido con `sonar(sonido, sustituye=evento_sustituible)` y, solo si `sonidos.sustituir_anuncios` está activo, el evento es sustituible y `sonar` devolvió verdadero, el texto no se dice (pero sí se guarda en el historial de anuncios). Para que «aceptado» sea definitivo, un sonido pedido con `sustituye=True` no se descarta ni se agrupa después en la cola (4.4): si en ese momento no puede sonar (suena uno de prioridad mayor), el reproductor devuelve falso y el texto se dice. Con volumen 0 tampoco se acepta. Los anuncios esenciales nunca se omiten.

### 4.4 Motor (`app/services/sonidos/motor.py`; `app/ui/sonidos.py` solo lo crea y lo inyecta)

El motor implementa el protocolo `Reproductor` de 4.3: recibe el `EventoSonido` ya filtrado por el servicio y hace todo lo de abajo (resolución del archivo, volumen, caché y cola).

- **Sin dependencias**: lectura de WAV con `wave`, volumen con `array` y reproducción con `PlaySoundW` de `winmm.dll` por `ctypes` con `SND_MEMORY | SND_ASYNC | SND_NODEFAULT`. No se usa `winsound` porque no permite `SND_ASYNC` con `SND_MEMORY`. El búfer del sonido en curso se guarda en `self._sonando` hasta que acaba (duración más 50 ms) o lo sustituye otro, para que Windows no lea memoria liberada.
- **Volumen**: `sonidos.volumen` de 0 a 100; ganancia en decibelios `(volumen − 100) × 0,4` (de 0 dB con 100 a −39,6 dB con 1); el volumen 0 es una excepción a la fórmula: silencio (no se reproduce nada y `sonar` devuelve falso). Las muestras de 16 bits se escalan una vez por (archivo, volumen) y se guardan en caché (máximo 32 MB; se vacía al cambiar volumen o paquete).
- **Formatos admitidos**: WAV PCM de 8 o 16 bits, mono o estéreo, de 8 000 a 48 000 Hz, de 10 s y 2 MB como máximo. Lo de 8 bits se convierte a 16 al cargar. Un archivo no válido se registra una vez y se trata como ausente.
- **Cola con prioridades**: un hilo `sonidos` con una condición; tres huecos, uno por prioridad. Reglas: un sonido de prioridad alta corta el que suena si es de prioridad menor; uno de prioridad baja se descarta si está sonando uno de prioridad mayor; varias peticiones bajas seguidas se agrupan (solo suena la última) y como mucho una cada `sonidos.intervalo_navegacion_ms`; las altas nunca se descartan (se encadenan, como mucho 4 en cola). Excepción: una petición que sustituye un anuncio (4.3) se acepta o se rechaza en el momento y, si se acepta, ya no se descarta ni se agrupa.
- **Resolución del archivo** de un evento: paquete elegido (de serie en `data/sounds/<paquete>/` o propio en `data/sounds_usuario/<paquete>/`) → su cadena `hereda` → paquete `clasico` → `sonidos/<nombre>.wav` del paquete del complemento (solo eventos de complemento) → silencio.
- **Coste**: `sonar()` comprueba `sonidos.activos`, el volumen y si el evento está activo (consulta en un diccionario calculado al cambiar la configuración, no en cada llamada), y encola. Menos de 5 ms (objetivo 10 de 1.2).
- **Tonos de progreso**: desaparece `Beep`; `op.progreso` con sus variantes los sustituye. `sonidos.progreso` decide `no`, `cada_25` o `cada_10`; con `cada_25` suenan las variantes 25, 50 y 75 (los paquetes incluyen `op_progreso_25.wav` y `op_progreso_75.wav` además de las de 10 en 10). **Lo decide la ventana en su latido** (`VentanaPrincipal.seguir_progreso`, el mismo seguimiento por operación que los anuncios de voz de la 1.x), nunca el hilo de la operación: con `cada_10`, cuando `nueva_decena` cambia, `servicio.sonar("op.progreso", str(decena))`; con `cada_25`, al pasar cada hito 25, 50 y 75, `servicio.sonar("op.progreso", str(hito))`, una vez cada uno. El evento `op.progreso` está activo de fábrica (`por_defecto=True`): quien lo calla es `sonidos.progreso = "no"`.
- **Cierre**: `motor.cerrar()` vacía la cola, para el sonido en curso con `PlaySoundW(None, None, 0)` y espera al hilo 0,5 s como máximo.

### 4.5 Preferencias → Sonidos

Página propia (no declarativa; `app/ui/dialogos/so_pagina_sonidos.py` con la función `crear(padre: wx.Window, config: Configuracion) -> PaginaPropia`; N2 ya deja la referencia `"app.ui.dialogos.so_pagina_sonidos:crear"` en `PAGINAS_PROPIAS` y el módulo provisional, 10.18). Controles, en este orden de creación (cada etiqueta antes de su control):

1. Casilla «&Activar los sonidos» (`sonidos.activos`).
2. «&Volumen:» `SliderAccesible` de 0 a 100 que anuncia «70 de 100» (`sonidos.volumen`, con `establecer_diferido`); al soltar, suena `aviso.informacion` con el volumen nuevo.
3. «&Paquete:» desplegable con los paquetes instalados («Clásico, de serie», «Mi paquete, propio»).
4. «Ca&tegoría:» desplegable con «Todas» y las categorías del catálogo (filtra la lista).
5. «&Sonidos:» `CheckListBoxAccesible`; cada elemento dice «Carpeta vacía: suena al entrar en una carpeta sin elementos», con su estado «marcado» o «no marcado» anunciado por la técnica de la plantilla de accesibilidad (`NotifyWinEvent`). Espacio activa o desactiva; Ctrl+A y Ctrl+Mayús+A todos y ninguno de la categoría visible. Se guarda en `sonidos.eventos` como diferencias con el valor de fábrica.
6. Botón «P&robar» (también Intro en la lista): suena el evento elegido con el paquete y el volumen elegidos aunque esté desactivado.
7. «Pro&greso de las operaciones:» desplegable No, Cada 25 %, Cada 10 % (`sonidos.progreso`).
8. Casilla «Los sonidos s&ustituyen a algunos anuncios» (`sonidos.sustituir_anuncios`), con la ayuda Ctrl+H: «Si un evento tiene sonido activo, no se dice su anuncio breve (por ejemplo, Marcado). Los errores y las preguntas se dicen siempre.».
9. «&Intervalo mínimo de los sonidos de navegación (milisegundos):» (`sonidos.intervalo_navegacion_ms`).
10. Botones «Restablecer los sonidos de &fábrica» (solo `sonidos.eventos`) y «Paquetes de sonidos...» (abre el asistente de 4.7).

La orden `sonidos_silenciar` (Ctrl+F11) cambia `sonidos.activos` desde cualquier sitio y anuncia «Sonidos desactivados» o «Sonidos activados» (resultado; suena `aviso.informacion` al activarlos). `sonidos_volumen_subir` y `sonidos_volumen_bajar` (menú Opciones > Sonidos, sin tecla de fábrica) cambian el volumen de 10 en 10 y anuncian «Volumen de los sonidos: 80».

Migración de la 1.x (esquema 2, 14.3):

- **Sonidos activos para todos**: la 1.x guarda en `settings.json` todos los valores fusionados con los de fábrica, y su valor de fábrica de `accesibilidad.sonidos` era `false`, así que no se puede distinguir quien los apagó de quien nunca tocó la casilla. Por eso la 2.0 activa los sonidos a todo el mundo, en instalaciones nuevas y al actualizar: la migración borra `accesibilidad.sonidos` y deja `sonidos.activos` en su valor de fábrica (sí).
- **Aviso una sola vez**: en el primer arranque de la 2.0 (nueva o actualizada), tras mostrar la ventana, se anuncia como esencial «Los sonidos están activados; puede desactivarlos en Preferencias, Sonidos» (también Ctrl+F11), y se marca `sonidos.aviso_inicial_mostrado`.
- `accesibilidad.tonos_progreso` verdadero pasa a `sonidos.progreso = "cada_10"`, falso a `"no"`.
- **WAV propios de la 1.x**: si `data/sounds/` tiene alguno de los tres WAV sueltos de la 1.x, `app.services.sonidos.paquetes.migrar_1x(ruta_datos: Path, config: Configuracion) -> bool` (SO; la única firma, la de 14.8; lo llama `main.py` tras la configuración, y devuelve verdadero si creó el paquete) crea el paquete propio `data/sounds_usuario/mis_sonidos_1x/` («Mis sonidos 1.x», `hereda: clasico`) con `operacion_terminada.wav` para `op.fin`, `operacion_error.wav` para `op.fin_errores` y `op.fallida`, y `carpeta_vacia.wav` para `nav.carpeta_vacia` (por el campo `archivos` de 4.6), mueve allí los WAV y elige ese paquete en `sonidos.paquete`. Es idempotente.

### 4.6 Paquetes de sonidos

- **De serie**: `data/sounds/<id>/` (se distribuyen y los actualiza el actualizador de la aplicación). **Propios**: `data/sounds_usuario/<id>/` (de la persona; nunca se distribuyen ni se tocan al actualizar; entran en la copia de seguridad).
- **Manifiesto** `paquete.json`:

```json
{
  "formato": 1,
  "id": "suave",
  "nombre": "Suave",
  "autor": "Proyecto zCommander",
  "licencia": "CC0-1.0",
  "version": "1.0.0",
  "descripcion": "Tonos de seno con ataque lento, a bajo volumen.",
  "hereda": "clasico",
  "generado_por": "tools/generar_sonidos.py 1.0",
  "archivos": {}
}
```

  `hereda` (opcional, `clasico` por defecto en los propios, `null` en `clasico`) dice de dónde sale un sonido que falta. `archivos` (opcional) permite otro nombre de archivo para un evento (`{"op.fin": "terminado.wav"}`).
- **Exportar e importar**: `.zcsonidos` es un ZIP con el contenido de la carpeta en la raíz. Al importar se valida: solo `paquete.json`, `LICENCIA.txt` opcional y `.wav` (también en `plugins/<id del complemento>/<nombre>.wav`, 4.2); cada WAV con las reglas de 4.4; nombres seguros como en 3.9; 50 MB expandido como máximo; `id` distinto de los de serie (si coincide con uno propio, se pregunta si se sustituye). Intro sobre un `.zcsonidos` en un panel ofrece importarlo.
- **Al menos 5 paquetes de serie completos**, generados por síntesis (4.8), licencia CC0-1.0, cada uno con un estilo:
  - `clasico` (Clásico): tonos de onda triangular, intervalos claros (éxito sube una tercera mayor, error baja una cuarta), es el paquete por defecto y la base de la herencia.
  - `suave` (Suave): senos con ataque y caída lentos, filtrado paso bajo, volumen 6 dB por debajo; para quien usa sonidos todo el día.
  - `retro` (Retro 8 bits): ondas cuadradas y arpegios rápidos cuantizados, al estilo de las consolas antiguas.
  - `minimalista` (Minimalista): clics y golpes de 5 a 40 ms (ruido filtrado y senos muy cortos); lo mínimo para distinguir eventos sin ocupar tiempo de voz.
  - `cristal` (Cristal): campanas por síntesis FM con parciales inarmónicos y una cola de reverberación corta, en el estilo «orquestal y cristal».

### 4.7 Asistente de paquetes (`app/ui/dialogos/so_paquetes.py`)

Orden `sonidos_paquetes` y botón de la página Sonidos. Pantalla inicial: lista de paquetes (de serie y propios) con «&Nuevo a partir de este...», «&Editar» (solo propios), «E&xportar...», «&Importar...», «&Eliminar» (solo propios, con confirmación) y «&Cerrar». Crear o editar abre el asistente con Atrás, Siguiente y Terminar:

1. **Base**: paquete del que se copia (el seleccionado).
2. **Datos**: Nombre, Identificador (propuesto desde el nombre), Autor, Licencia (desplegable con CC0-1.0, CC-BY-4.0, GPL-3.0-or-later y «Otra»), Descripción.
3. **Sonidos**: categoría y lista (Evento, Origen: «Propio», «Heredado de Clásico»); botones «P&robar», «&Sustituir por un archivo WAV...» (selector de archivos; valida el WAV y lo copia con el nombre que toca), «&Volver al heredado» y «Probar el &original».
4. **Resumen**: cuántos sonidos propios y heredados; casilla «Usar este paquete ahora»; botón «E&xportar como .zcsonidos...».

### 4.8 Generador (`tools/generar_sonidos.py`)

- `python tools/generar_sonidos.py [--paquete <id>] [--complementos] [--comprobar]` escribe `data/sounds/<id>/` con todos los eventos del catálogo del núcleo y de los complementos de serie (`plugins/<id del complemento>/<nombre>.wav`) y su `paquete.json`. Con `--complementos`, escribe además la carpeta `sonidos/` de cada complemento de serie (`plugins/<carpeta>/sonidos/<nombre>.wav`, con el estilo del paquete `clasico`). Las dos cosas son del bloque SO, a partir de los `[[sonidos]]` de los manifiestos.
- **Determinista**: solo biblioteca estándar (`math`, `array`, `wave`, `random.Random(semilla_fija)` cuando hace falta ruido); misma entrada, mismos bytes. `--comprobar` regenera en una carpeta temporal y falla si algún archivo difiere de lo guardado (lo usa una prueba).
- **Receta por evento**: una tabla en el propio generador (`RECETAS: dict[str, Receta]`) con familia de sonido por categoría y dirección (subir, bajar, plano), duración y número de notas; cada paquete aplica su estilo (forma de onda, envolvente, filtro, reverberación, transposición). Reglas: pares opuestos con direcciones opuestas (marcar sube, desmarcar baja; conectar sube, desconectar baja); errores graves y descendentes; éxitos ascendentes; navegación corta y aguda; pico a −3 dBFS y RMS igualado dentro de cada paquete; WAV mono de 16 bits a 44 100 Hz.
- Pruebas: cada evento del catálogo tiene archivo en cada paquete de serie; cada archivo pasa la validación de 4.4; duraciones dentro de los límites de 4.1; generación determinista.

### 4.9 Mapa de sonidos

- **Ayuda → «Mapa de &sonidos...»** (orden `mapa_sonidos`, `app/ui/dialogos/so_mapa.py`): «&Paquete:» (desplegable), «&Categoría:» (desplegable) y una `ListaAccesible` con columnas Evento, Cuándo suena y Estado («Activo» o «Desactivado»). Intro o «&Reproducir» lo hacen sonar aunque esté desactivado; «Ir a las &preferencias» abre la página Sonidos con ese evento elegido; «&Cerrar». Sirve para aprender qué significa cada sonido y para comparar paquetes.
- **Anexo** `data/docs/sonidos.md`, generado por `tools/generar_anexos.py`: un apartado por categoría con una lista «Nombre (id): cuándo suena. Activo por defecto: sí/no.», más los de cada complemento de serie. Lo abre el visor de ayuda y lo enlaza el manual.

## 5. Actualizador de la aplicación

Se copia la plantilla del agente `actualizador` (el modelo de YouTubeRO, socialrss-youtubero.md 1) y se respetan sus diez reglas de oro. Aquí solo va lo propio de zCommander.

### 5.1 Archivos

| Archivo | Origen | Cambios para zCommander |
|---|---|---|
| `app/services/actualizador.py` | Plantilla | Constantes de 5.2; `DATA_ENTRANTE` (5.3); usa `app/core/paths.py`; su `_abrir` y su `descargar` pasan a `app/core/descargas.py` (N2, 14.9) y el actualizador los usa desde allí: una sola implementación de descarga |
| `app/ui/dialogo_actualizacion.py` | Plantilla | Anuncios con `app/ui/anuncios.py` y sonidos `act.*`; menú Ayuda desde el catálogo (orden `buscar_actualizaciones`), no con `anadir_menu_ayuda` |
| `tools/firmar_version.py` | Plantilla | Ninguno (`generar`, `firmar`, `verificar`); la firma de complementos, con su prefijo, está en `app/plugins/firma.py` (3.9) |
| `tools/publicar.py` | Nuevo (modelo de YouTubeRO) | 5.6 |
| Plantilla del `.bat` de sustitución | Plantilla | Salud en dos fases (5.2): es un cambio declarado de la plantilla, que hace AC |
| `tests/test_actualizador.py`, `test_firma.py`, `test_sustitucion.py`, `test_dialogo_actualizacion.py`, `test_versiones.py`, `apoyo_actualizador.py` | Plantilla | Nombres y constantes de zCommander |

### 5.2 Constantes

- `NOMBRE_APP = "zCommander"`, `EJECUTABLE = "ZCommander.exe"`.
- `URL_MANIFIESTO = "https://xebolax.synology.me/zCommander/version.json"`.
- `CLAVES_PUBLICAS_ED25519 = ("<clave pública generada con firmar_version.py generar>",)`, tupla para poder rotar claves.
- `DATA_ACTUALIZABLE = ("sounds", "locales", "docs", "icons")`: lo único de `data` que una versión nueva puede refrescar (sin borrar nada). **No incluye `bin`** (5.3) ni `sounds_usuario`, `plugins`, `config`, `cache`, `logs`, `backups`, `temp`.
- **Salud en dos fases** (cambio declarado de la plantilla del actualizador; el `.bat` es de AC): la versión nueva escribe la marca `iniciado <versión> <PID>` muy pronto (paso 4 de 14.8, con `actualizador.marcar_inicio()`, antes de aplicar ningún pendiente) y `ok <versión>` cuando confirma su salud tras mostrar la ventana (5.4). El `.bat` espera `iniciado` como mucho `ESPERA_SALUD = 60` s; en cuanto la ve, amplía la espera de `ok` hasta `ESPERA_SALUD_TOTAL = 300` s, porque el primer arranque tras actualizar puede integrar componentes grandes (6.7: FFmpeg son unos 208 MB que se copian dos veces) y probarlos, y en un pendrive eso pasa de 60 s. Si no llega `iniciado` en 60 s, o llega y el proceso de ese PID ya no vive sin haber escrito `ok`, vuelve a la versión anterior como en la plantilla. **Si se agotan los 300 s con el proceso nuevo vivo** (la persona tarda en contestar algo, o la integración de un pendrive lento sigue en marcha), el `.bat` **no** vuelve atrás (la plantilla no mata la aplicación y revertir con sus archivos abiertos dejaría una instalación mezclada): escribe `salud sin confirmar <versión>` en el estado del actualizador, conserva el respaldo de la versión anterior y termina. El siguiente arranque de la versión nueva lo ve: si llega a escribir `ok`, la confirma como siempre (y borra la marca); si se encuentra la marca de un arranque anterior que tampoco llegó a `ok`, lo anuncia tras mostrar la ventana y ofrece «&Volver a la versión anterior» (lanza el `.bat` de vuelta atrás con `procesos.lanzar_independiente` y sale) o «&Seguir con esta versión». Además, tras actualizar, nada pregunta a la persona antes de `ok`: la pregunta por una restauración pendiente se hace después (7.6, 14.8).
- `ESPERA_CIERRE = 90` y los límites de la plantilla (manifiesto de 256 KB; paquete de 2 GB; 4 GB expandido; 50 000 miembros). El paquete de la 2.0 pesa unos 330 MB por FFmpeg y rclone: cabe.
- Paquete: `zCommander_v<versión>.zip`. Manifiesto: el de la plantilla (`app`, `version`, `file`, `sha256`, `size`, `date`, `novedades`, `firma_ed25519`), firmado entero.
- Estado en `data/config/actualizaciones.json` (versión confirmada para el anti-retroceso, versión omitida, resultado de la última sustitución), como en la plantilla.

### 5.3 Componentes y complementos al actualizar

- La carpeta del programa (con `plugins/` de serie dentro) se sustituye entera por la nueva, como en la plantilla.
- El `data/bin` del paquete **no** se copia sobre los componentes activos (la persona puede haberlos actualizado). El `.bat` lo copia a `data/bin/.entrante/` (`DATA_ENTRANTE = {"bin": "bin/.entrante"}`, añadido a la plantilla). En el primer arranque de la versión nueva, **antes de cargar ninguna DLL** (14.8), `componentes.integrar_entrante()` (6.7) compara cada componente con la línea base nueva: si el activo es más antiguo que la nueva base, instala la base (con respaldo); si es más nuevo (la persona lo actualizó), lo conserva y lo dice en el resumen de novedades. Si después la versión nueva no confirma su salud y la plantilla vuelve a la anterior, lo integrado se revierte (6.7).
- Los complementos de la persona (`data/plugins/`) no se tocan. Al arrancar, el gestor vuelve a comprobar su compatibilidad con la API nueva; los incompatibles quedan «Incompatible» con el motivo y se avisa una vez.
- Los paquetes de sonidos de serie se refrescan (`sounds` está en `DATA_ACTUALIZABLE`); los propios no.

### 5.4 Interfaz y comprobación periódica

- Ayuda → «Buscar ac&tualizaciones...» (orden `buscar_actualizaciones`): comprobación manual; con «Sin novedades» suena `act.al_dia` y se anuncia como resultado.
- Comprobación periódica (`ComprobadorPeriodico` de la plantilla) si `actualizaciones.comprobar` está activa: la primera a los 60 s del arranque y después cada `actualizaciones.intervalo_horas`. Es compartida: AC añade `actualizador.registrar_comprobacion(nombre: str, funcion: Callable[[TokenCancelacion], list[Novedad]], activa: Callable[[], bool]) -> None` (`TokenCancelacion` es el objeto de cancelación de la 1.x, `app/core/tareas.py`), con la que CO (componentes, con su propio intervalo en días) y PL (actualizaciones de complementos) se suman a la misma pasada; `@dataclass(frozen=True) Novedad(origen: str, texto: str, esencial: bool)` es lo que se anuncia. `registrar_comprobacion` y `Novedad` los deja N2 en `app/services/actualizador.py` (archivo de AC) como provisionales: el registro guarda y no hace nada hasta que AC termine. Si hay versión nueva: suena `act.disponible`, se anuncia como esencial «Hay una versión nueva de zCommander: 2.1.0. Se abrirá su diálogo; también está en Ayuda, Buscar actualizaciones.» y el diálogo **no** se abre solo mientras haya un diálogo o menú abierto o una operación esperando decisión; se abre en cuanto la ventana principal está libre, con el foco en «&Novedades».
- Diálogo de la plantilla: resumen, «&Novedades:» y «&Estado:» de solo lectura, barra de progreso con nombre; botones «&Actualizar ahora», «Omitir esta &versión» y «&Más tarde» (que pasa a «&Cancelar» al descargar y a «&Reintentar» si falla). Voz solo en los hitos 25, 50, 75 y 100 % y en los cambios de fase.
- Antes de cerrar para instalar, zCommander aplica sus reglas de salida (1.x §8.5): si hay operaciones en marcha, pregunta «Esperar y actualizar», «Cancelar las operaciones y actualizar» o «No actualizar ahora».
- Tras actualizar: `--tras-actualizar`; `actualizador.al_arrancar(tras_actualizar: bool) -> None` escribe la marca `ok` (5.2) tras mostrar la ventana, suena `act.instalada`, llama a `app.services.componentes.integrar.confirmar_integracion() -> None` (6.7; provisional de N2, de CO: es una dependencia declarada de AC hacia CO, 19.3) y se muestran las novedades una vez (visor de ayuda de la 1.x). Si se volvió atrás, suena `act.revertida` y se explica como esencial.
- Desde el código fuente no se sustituye nada (`puede_instalar` es falso): la comprobación funciona y el diálogo lo dice.

### 5.5 Seguridad

Las de la plantilla (firma antes de mirar ningún campo, anti-retroceso solo con lo confirmado, extracción segura, solo https, sin matar la aplicación). La clave privada vive en `tools/claves/` (con un `.gitignore` que lo excluye todo) y con una copia fuera del equipo; si existe la variable `FIRMA_CONTRASENA`, el PEM va cifrado.

### 5.6 Publicar (`tools/publicar.py`)

`python tools/publicar.py [--servidor] [--sin-fuentes] [--firmar-complementos <id> ...]`:

1. Lee la versión de `app/core/version.py` y exige su entrada en `data/docs/changelog.md` (`tools/notas_version.py`).
2. Compila con `setup_cx.py` y comprueba que arranca (`ZCommander.exe --comprobar-arranque --complemento-prueba tests/datos/plugins/ejemplo`).
3. Ejecuta `tools/comprobar_licencias.py` sobre la compilación.
4. Crea `zCommander_v<versión>.zip` con `tools/empaquetar.py` (sin datos personales).
5. Crea `version.json` con las novedades del registro de cambios y lo firma con `tools/firmar_version.py`.
6. Crea `zCommander_v<versión>_fuentes.zip` (2.4), salvo con `--sin-fuentes`.
7. Paso opcional, solo con `--firmar-complementos`: para cada id de serie nombrado, crea `zc.<carpeta>-<versión>.zcplugin` firmado con la clave del proyecto (`app.plugins.firma.firmar_complemento`, 3.9) y el JSON de actualización de 3.10 firmado igual. Es la forma de publicar una actualización de un complemento de serie, que la persona instala en `data/plugins/` sin esperar a una versión nueva de zCommander. Los de `plugins/` dentro del paquete de la aplicación no se firman (confianza por ubicación, 3.2).
8. Con `--servidor`, copia a `%USERPROFILE%\SynologyDrive\web\zCommander\` **primero** el ZIP y el ZIP de fuentes y **después** `version.json` (así nadie ve un manifiesto que apunta a un paquete que aún no está); los complementos firmados del paso 7, igual: primero el `.zcplugin` y después su JSON. Comprueba al final que los tamaños copiados coinciden.

## 6. Actualizador de componentes

### 6.1 Qué hace

Mantiene al día los programas y bibliotecas de `data/bin/<id>/` (6.2) sin actualizar zCommander entero: dice qué hay nuevo, deja elegir qué actualizar, guarda copia de lo que sustituye, prueba lo nuevo y, si falla, vuelve solo a lo anterior. Permite volver a la versión anterior de un componente y restaurar los originales (la línea base).

### 6.2 Fichas (`data/bin/componentes.json`) y línea base (`data/bin/linea_base.json`)

`componentes.json` describe lo **instalado** (lo cambia el actualizador de componentes). `linea_base.json` tiene la misma forma, la genera `tools/preparar_componentes.py` al compilar y es de solo lectura: lo que trae y ha probado esta versión de zCommander. Los componentes de la línea base se declaran solo ahí (con su `dueno`, aunque sea un complemento de serie, como `zc.nubes` para rclone); los complementos de la persona pueden declarar componentes propios con `[[componentes]]`, que se añaden al catálogo con `dueno = "<id del complemento>"`. El esquema de la ficha es un contrato de N2 (lo usan el `linea_base.json` provisional de N2, los manifiestos y CO) y se valida con `app/services/componentes/fichas.py`.

Ficha (ejemplo con los datos reales de rclone):

```json
{
  "formato": 1,
  "componentes": [
    {
      "id": "rclone",
      "nombre": "rclone",
      "version": "1.76.0",
      "licencia": "MIT",
      "dueno": "zc.nubes",
      "carpeta": "rclone",
      "archivos": [
        {"ruta": "rclone.exe", "sha256": "<suma del archivo instalado>", "tamano": 85647872},
        {"ruta": "LICENCIA-MIT.txt", "sha256": "...", "tamano": 1115}
      ],
      "licencias": ["LICENCIA-MIT.txt"],
      "fuente": {
        "tipo": "github",
        "repositorio": "rclone/rclone",
        "patron_asset": "rclone-v{version}-windows-amd64.zip",
        "extraer": {"rclone-v{version}-windows-amd64/rclone.exe": "rclone.exe"}
      },
      "verificacion": {"tipo": "sha256sums", "asset": "SHA256SUMS"},
      "prueba": {"ejecutable": "rclone.exe", "argumentos": ["version"], "salida_contiene": "rclone v{version}", "tiempo_s": 20},
      "en_uso": {"procesos": ["rclone.exe"], "detener": true, "al_reiniciar": false},
      "opcional": false,
      "actualizable": true,
      "novedades": "https://rclone.org/changelog/"
    }
  ]
}
```

Campos:

- `id`, `nombre`, `version`, `licencia` (SPDX), `dueno` (`nucleo` o id de complemento), `carpeta` (dentro de `data/bin`).
- `archivos`: cada archivo instalado con su SHA-256 y tamaño; sirve para comprobar la integridad al arrancar (solo tamaño, rápido) y al actualizar (sumas).
- `licencias`: archivos de licencia que acompañan al componente (se copian también a `data/docs/licencias/<id>/`).
- `fuente.tipo` (marcadores que se sustituyen en `patron_asset`, `extraer`, `url_paquete` y `salida_contiene`: `{version}`, la versión completa, «26.06»; `{version_sin_punto}`, sin puntos, «2606»; `{rama}`, el campo `rama` tal cual, «9.0», sin la «n»):
  - `github`: `{"tipo": "github", "repositorio": "dueño/nombre", "etiqueta": "" | "latest" | "<etiqueta fija>", "rama": "" | "9.0", "patron_asset": "...", "version_desde": "tag_name" | "programa" | "re:<expresión>", "extraer": {...}}`. API `https://api.github.com/repos/<repositorio>/releases/latest` o, si `etiqueta` no está vacía, `releases/tags/<etiqueta>`. `version_desde`: `tag_name` (por defecto; quitando la `v` inicial), `programa` (la versión la da la `prueba` tras descargar, como en FFmpeg) o `re:` con una expresión regular cuyo primer grupo, aplicado al nombre del asset, da la versión. `extraer` dice qué miembros del paquete van a qué archivos (comodines permitidos: `"*/bin/*.dll": "."`). Una publicación que reutiliza siempre la misma etiqueta (`latest` de FFmpeg-Builds) se compara por el `digest` y el `updated_at` del asset que da la API, guardados en `componentes.json` (`"asset": {"digest": "sha256:...", "actualizado": "2026-11-01T..."}`): si cambian, hay «Compilación nueva de la rama 9.0 (1 de noviembre de 2026)», sin descargar nada para saberlo.
  - `msys2`: `{"tipo": "msys2", "indice": "https://mirror.msys2.org/mingw/ucrt64/ucrt64.db", "principal": "mingw-w64-ucrt-x86_64-libarchive", "paquetes": {"<nombre de paquete>": {"extraer": {"ucrt64/bin/libarchive-13.dll": "libarchive-13.dll"}}, ...}}`. El índice es un `tar.zst` con un `desc` por paquete con `%VERSION%`, `%FILENAME%` y `%SHA256SUM%`. La versión del componente es la del paquete `principal` (sin el `-1` del paquete; el paquete completo, «3.8.11-1», va en `version_paquete`).
  - `url`: `{"tipo": "url", "url_version": "https://...", "formato_version": "texto" | "json:<clave>", "url_paquete": "https://.../{version}...", "url_sumas": "https://..."}`; `json:<clave>` toma la versión de esa clave de primer nivel del JSON.
- `verificacion.tipo`: `sha256sums` (`{"tipo": "sha256sums", "asset": "SHA256SUMS"}`: un archivo de sumas de la propia publicación, como `SHA256SUMS` o `checksums.sha256`), `digest_github` (el campo `digest: "sha256:..."` que la API de GitHub da para cada asset), `msys2` (la suma del índice) o `sha256` (`{"tipo": "sha256", "valor": "..."}`, fija en la ficha). Siempre se comprueba el SHA-256 del paquete descargado antes de abrirlo. La firma PGP de rclone y MSYS2 **no** se verifica en la aplicación (no hay `gpg`); se verificó a mano para la línea base (binarios-descargados.md) y queda como riesgo (20).
- `prueba`, en una de dos formas: la de un programa, `{"ejecutable": "rclone.exe", "argumentos": [...], "salida_contiene": "...", "tiempo_s": 20}` (sin `tipo`); o la de una biblioteca que se carga en el proceso (libarchive), `{"tipo": "zcommander", "argumentos": ["--probar-componente", "libarchive"], "tiempo_s": 20}`: zCommander se lanza a sí mismo sin interfaz (el argumento se atiende al principio de `main`, antes de la instancia única y de cualquier pendiente, 14.8), carga la DLL desde la carpeta que se le indique y llama a `archive_version_details()`; código 0 si coincide con la versión. Quien la lanza añade la carpeta: el instalador de componentes, en el paso 4 de 6.6, añade `--carpeta data/temp/componentes/<id>/nuevo/` (la versión nueva antes de instalarla); en el paso 8, sin `--carpeta` (la de su sitio definitivo, `data/bin/<carpeta>`).
- `en_uso`: `procesos` (los que lo usan; se buscan solo entre los hijos de zCommander con `app.core.procesos.hijos_vivos`, 14.9), `detener` (verdadero si su dueño registra con `zc.componentes.al_detener` cómo pararlo cuando no hay trabajo en curso; no es una orden del catálogo), `esperar_s` (segundos que se espera a que terminen los procesos de `procesos` cuando cada uso es un proceso corto, como 7za o FFmpeg; 0 por defecto = no se espera) y `al_reiniciar: true` cuando no se puede sustituir en caliente (DLL cargadas en el proceso).
- `opcional`: si puede faltar (el gestor ofrece «Instalar» para descargarlo con permiso); `actualizable: false` para lo que se genera con zCommander (`nvda`).
- Solo en `linea_base.json`: `url_paquete_exacta` y `sha256_paquete` (el paquete exacto de la base y su suma), para poder volver a descargarla si se borró su respaldo (6.6).

Línea base de la 2.0 (versiones y orígenes de binarios-descargados.md):

| id | Versión | `fuente` | `verificacion` | `prueba` | `en_uso` |
|---|---|---|---|---|---|
| `rclone` | 1.76.0 | `github`, `rclone/rclone`, `rclone-v{version}-windows-amd64.zip` | `sha256sums` (`SHA256SUMS`) | `rclone version` contiene `rclone v1.76.0` | `rclone.exe`; `detener: true` (lo registra `zc.nubes`) |
| `libarchive` | 3.8.11 | `msys2`, principal `mingw-w64-ucrt-x86_64-libarchive` y paquetes `-zstd`, `-zlib`, `-xz`, `-lz4`, `-libiconv`, `-bzip2`, `-libb2` (8 DLL) | `msys2` | `--probar-componente libarchive` | En el proceso: `al_reiniciar: true` |
| `7za` | 26.06 | `github`, `ip7z/7zip`, `7z{version_sin_punto}-extra.7z`, miembro `x64/7za.exe` (se abre con py7zr, 6.6) | `digest_github` | `7za i` con código 0 | `7za.exe`; `esperar_s: 30` (cada uso es un proceso corto) |
| `ffmpeg` | 9.0.2 (rama 9.0) | `github`, `FFmpeg-Builds/FFmpeg-Builds` (antes `BtbN/FFmpeg-Builds`, 21.2.7), `etiqueta: latest`, `rama: 9.0`, `ffmpeg-n{rama}-latest-win64-gpl-shared-{rama}.zip`; `version_desde: programa`; novedades por `digest` y `updated_at` del asset | `sha256sums` (`checksums.sha256`) | `ffmpeg -version` contiene `ffmpeg version` y `ffprobe -version` | `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`; `esperar_s: 30`; si siguen vivos (una conversión larga, el reproductor), se aplica al reiniciar |
| `nvda` | la de zCommander | — | — | — | `actualizable: false` |

FFmpeg-Builds publica «latest» sin número de versión estable en el nombre: la ficha fija la **rama** (`9.0`); una compilación nueva de la misma rama se detecta por el asset (arriba) y una rama nueva (`9.1`) se ofrece como cambio grande, con el aviso de abajo. Una rama nueva o un cambio de versión principal de cualquier componente se marca «Cambio grande: puede cambiar su comportamiento».

### 6.3 Estado y respaldos

- `data/config/estado_componentes.json`: última comprobación, versiones nuevas conocidas por componente con sus novedades (texto corto o URL) y versiones omitidas.
- Respaldos: `data/bin/respaldo/<id>/<versión>/` con los archivos sustituidos y su ficha. Se guardan las dos últimas versiones de cada componente más, siempre, la de la línea base si alguna vez se sustituyó.
- Pendientes: `data/bin/.pendiente/<id>/` (lo que se aplica al reiniciar) y `data/bin/.entrante/` (lo que trae una actualización de la aplicación, 5.3).
- **En mantenimiento**: mientras un componente se detiene, se sustituye o se restaura, `componentes` lo marca «en mantenimiento» (en memoria y en el diario de 6.6). En ese estado `ruta()`, `ejecutable()` y `disponible()` de 3.7 responden como si faltara («El componente rclone se está actualizando; inténtelo dentro de un momento») y su dueño no puede arrancarlo (por ejemplo, el siguiente uso de un panel `nube://` no vuelve a arrancar rcd hasta que termine). Por eso **`ruta()` y `ejecutable()` se piden en cada uso y nunca se guardan** (ni en un atributo al activarse ni en una caché): un complemento que guarda la `Path` se salta el mantenimiento. `tools/validar_plugin.py` avisa, con `ast`, si el resultado de `zc.componentes.ruta` o `ejecutable` se asigna a un atributo de `self` o a una variable de módulo.

### 6.4 Comprobar

- Manual: Opciones → «Componentes e&xternos...» (orden `componentes`) y el botón «&Buscar versiones nuevas».
- Periódica: si `actualizaciones.componentes_comprobar` está activa, cada `actualizaciones.componentes_intervalo_dias`, dentro de la comprobación de la aplicación (registrada con `actualizador.registrar_comprobacion`, 5.4). Si hay novedades, suena `comp.disponible` y se anuncia como esencial «Hay versiones nuevas de 2 componentes. Opciones, Componentes externos.»; nunca descarga sin la persona.
- Todo en hilos con `app/core/red.py` (tiempos de espera, reintentos de GET, `Retry-After`; la API de GitHub sin autenticar admite 60 peticiones por hora: una comprobación hace una por componente).

### 6.5 Diálogo «Componentes externos» (`app/ui/dialogos/co_componentes.py`)

- `ListaAccesible` con columnas Componente, Instalada, Nueva («—» si no hay), Origen («Línea base», «Actualizada», «Falta»), Licencia y Usado por (núcleo o complemento). Casillas en cada fila para elegir qué actualizar (`EnableCheckBoxes`); las filas sin versión nueva no tienen casilla activa.
- Texto de solo lectura «&Detalles:» con las novedades del componente elegido, su tamaño de descarga, el aviso de cambio grande y el estado de su prueba.
- Botones: «&Buscar versiones nuevas», «&Actualizar los elegidos», «&Volver a la versión anterior» (del componente del cursor; solo si hay respaldo), «&Restaurar los componentes originales...» (todos a la línea base; confirma con la lista de cambios), «&Instalar» (componentes opcionales que faltan), «&Omitir esta versión», «Abrir su &carpeta» y «&Cerrar». `revisar_teclado` decide las letras definitivas.
- Progreso de cada componente en una barra con nombre y anuncios por fase («Descargando rclone», «Comprobando», «Probando», «rclone actualizado a 1.77.0»).

### 6.6 Actualizar un componente (operación `OperacionComponente` del motor)

Para cada componente elegido, en este orden:

1. **Descargar** a `data/temp/componentes/<id>/` con `descargas.descargar` (`.parcial`, reanudable).
2. **Verificar** el SHA-256 del paquete con la fuente de `verificacion`. Si no coincide: se borra y se informa; no se toca nada.
3. **Extraer** solo los miembros de `extraer` a `data/temp/componentes/<id>/nuevo/`, con las reglas de extracción segura (nombres validados, sin enlaces), **sin usar libarchive** (así actualizar o restaurar libarchive no depende de libarchive, y CO no depende de CM): `.zip` con `zipfile`, `.pkg.tar.zst` con `tarfile` (`r:zst`), `.7z` con py7zr; si py7zr no admite el filtro del `.7z` (BCJ2), con el `7za` activo o el 7-Zip de la persona, y si no hay ninguno, se explica y no se toca nada.
4. **Probar** la versión nueva desde esa carpeta con su `prueba` (con `--carpeta` en la de tipo `zcommander`, 6.2). Si falla, se para aquí: la instalación no se toca.
5. **Mantenimiento y uso**: el componente pasa a «en mantenimiento» (6.3). Si algún proceso de `en_uso` está vivo: si tiene `esperar_s`, se espera como mucho ese tiempo a que terminen (se anuncia «Esperando a que termine 7za»); si tiene `detener` y su función registrada devuelve verdadero (por ejemplo, rclone sin transferencias), se ha detenido; si siguen vivos tras la espera, si la función devuelve falso, si no tiene `detener` ni `esperar_s` o si `al_reiniciar` es verdadero, se deja en `data/bin/.pendiente/<id>/`, se quita el mantenimiento y se dice «Se aplicará al reiniciar zCommander» (con «&Reiniciar ahora»).
6. **Respaldar** la versión activa en `data/bin/respaldo/<id>/<versión>/`.
7. **Sustituir** con un diario: se escribe `data/bin/instalando.json` (`{"id", "version_anterior", "version_nueva", "paso", "sumas_nueva": {"ruta": "sha256"}}`, con las sumas de la ficha nueva); se copia la carpeta activa entera a una hermana `data/bin/<carpeta>.nueva/` con los archivos nuevos encima; se hacen **dos renombrados**, `<carpeta>` → `<carpeta>.vieja` y `<carpeta>.nueva` → `<carpeta>`, entre los que la carpeta falta un instante (nunca quedan versiones mezcladas; mientras, el componente sigue en mantenimiento); se borra `<carpeta>.vieja` y se actualiza la ficha en `componentes.json`. En Windows un renombrado falla si hay algún identificador abierto en la carpeta (el antivirus, el vigilante de cambios de un panel que la muestra, el directorio de trabajo de un proceso): antes de renombrar se sacan los paneles de zCommander de esa carpeta, y cada renombrado se reintenta 5 veces con esperas de 0,2, 0,5, 1, 2 y 4 s; si sigue fallando, se deshace lo hecho, lo nuevo pasa a `data/bin/.pendiente/<id>/` y se dice «Se aplicará al reiniciar zCommander». Al arrancar, un `instalando.json` que quedó a medias se termina si `<carpeta>.nueva` está **completa** (sus archivos tienen exactamente las `sumas_nueva` del diario) o se deshace (vuelve `<carpeta>.vieja`) antes de cargar nada.
8. **Probar otra vez** desde su sitio definitivo. Si falla, **vuelta atrás automática**: restaurar el respaldo con el mismo procedimiento, ficha anterior, suena `comp.revertido` y se explica «La versión 1.77.0 de rclone no funcionó y se ha vuelto a la 1.76.0. Detalles en el registro.».
9. Se quita el mantenimiento y se borra el diario; suena `comp.actualizado` y se anuncia el resumen.

Los pendientes se aplican en el arranque siguiente, antes de cargar complementos y antes de cargar libarchive, con los pasos 6 a 8 (y vuelta atrás si la prueba falla). «Volver a la versión anterior» y «Restaurar los componentes originales» siguen los pasos 5 a 8 con los archivos del respaldo; si el respaldo de la línea base no está (se borró a mano), se descarga de su origen exacto (URL y suma en `linea_base.json`), con permiso.

### 6.7 Integrar lo que trae una actualización de la aplicación

`componentes.integrar_entrante()` en el primer arranque tras actualizar (5.3), dentro de `main.py` junto a `aplicar_pendientes()` y **antes de cargar ninguna DLL** (14.8), así la versión nueva nunca arranca con la libarchive antigua:

- Si hay algo que integrar, antes de empezar se anuncia con la voz mínima de la 1.x, sin configuración (la salida que encuentre: NVDA, JAWS o SAPI5), «Preparando los componentes nuevos de zCommander...», porque puede tardar y aún no hay ventana ni sonidos.
- Primero se mueve `data/bin/.entrante/linea_base.json` a `data/bin/linea_base.json` (con copia de la anterior en `data/bin/respaldo/linea_base-<versión de la app anterior>.json`).
- Por cada componente de `.entrante`, si su versión es más alta que la activa o la activa es la base anterior, se instala con los pasos 6 a 8 de 6.6 (sin «en uso»: aún no corre nada); si la activa es más nueva, se conserva.
- Se escribe `data/bin/integracion.json` con la versión de la aplicación y lo sustituido, y se devuelve un `ResumenIntegracion` (14.8) con lo conservado, lo instalado y lo revertido. Nada se anuncia ni suena en este paso: el resumen y los avisos (`comp.revertido` incluido) se dan tras mostrar la ventana (14.8, paso 11). `.entrante` y los respaldos se guardan hasta que el actualizador confirma la salud (`componentes.confirmar_integracion()`, 5.4); entonces se borran `.entrante` e `integracion.json`.
- Si en un arranque `integracion.json` existe y su versión no es la que arranca (la plantilla volvió a la anterior por falta de salud), se restauran los respaldos que lista, y la `linea_base.json` anterior, antes de cargar nada.

### 6.8 Integridad al arrancar

Al arrancar se comprueba (en un hilo, solo existencia y tamaño) que los archivos de cada componente están; lo lanza `componentes_co.instalar` (14.9) con `ventana.tareas`. Si falta alguno: el componente queda «Dañado», sus funciones dicen «Falta el componente X: Opciones, Componentes externos, Restaurar» y el diálogo ofrece restaurarlo.

### 6.9 Módulos

`app/services/componentes/` (sin wx): `fichas.py` (lectura, validación y escritura de `componentes.json` y `linea_base.json`; N2 deja la validación del esquema de 6.2), `fuentes.py` (GitHub, MSYS2, URL), `instalar.py` (pasos de 6.6, diario y la operación), `en_uso.py` (procesos y funciones `al_detener` registradas), `estado.py` (incluido el mantenimiento), `integrar.py` (`aplicar_pendientes`, `integrar_entrante`, `confirmar_integracion`, `ResumenIntegracion`), `prueba.py` (`probar_componente`). N2 crea `fichas.py`, `estado.py` (con las funciones de destino de 3.7), `integrar.py` y `prueba.py` como provisionales con sus firmas (19.1); CO es su dueño posterior. Con wx: `app/ui/dialogos/co_componentes.py`, `app/ui/acciones/componentes_co.py`. Herramienta: `tools/preparar_componentes.py` (genera `linea_base.json` desde `data/bin` y las fuentes; con `--descargar`, y permiso, vuelve a bajar y verificar la línea base). Argumento nuevo de `main.py`: `--probar-componente <id> [--carpeta <ruta>]` (14.8).

## 7. Copia de seguridad de la aplicación

### 7.1 Qué hace

Guarda en un solo archivo `.zcbackup` la parte de la configuración que elija la persona y la restaura en este equipo o en otro, eligiendo qué restaurar y si se combina con lo que hay o lo sustituye. Las contraseñas se pueden llevar cifradas con una contraseña de la copia.

### 7.2 Partes

| id | Nombre en el diálogo | Qué incluye | Se aplica |
|---|---|---|---|
| `preferencias` | Preferencias | `settings.json` salvo `teclado.*` y `ventana.*` | Al reiniciar |
| `teclas` | Perfiles y mapa de teclas | `teclado.*`, `data/config/perfiles/` (perfiles propios) | Al reiniciar |
| `sesion` | Sesión e historiales | `sesion.json` (carpetas, pestañas, historiales, cesta), `espacios.json`, `paleta.json` | Al reiniciar |
| `personalizacion` | Favoritos, menú de usuario, asociaciones y plantillas | `favoritos.json`, `menu_usuario.json`, `asociaciones.json`, `plantillas_renombrado.json`, `busquedas.json`, `menus.json`, `vistas_carpeta.json`, `reglas.json`, `alias.json`, `data/plantillas/` | En el momento |
| `conexiones` | Conexiones (FTP, SFTP, WebDAV, nubes y NAS) | `conexiones.json`, `hosts_conocidos.json`, `known_hosts`, `rclone.conf`, `data/config/plugins/zc.nubes/`, `data/config/plugins/zc.synology/`, `red.json`; y sus secretos (`ftp:*`, `plugin:zc.nubes:*`, `plugin:zc.synology:*`) | Al reiniciar |
| `complementos` | Complementos instalados y su configuración | La lista de ids instalados con su versión y una copia de cada uno como paquete (`partes/complementos/paquetes/<id>.zcplugin`, con su firma si la tenía), `data/config/plugins/` (salvo lo de `conexiones` y salvo `claves.json`), `complementos.inhabilitados` y `complementos.fallos_maximos`, y secretos `plugin:*` | Configuración al reiniciar; los paquetes, por el flujo de instalación (7.6) |
| `sonidos` | Paquetes de sonidos propios | `data/sounds_usuario/` | En el momento |
| `macros` | Macros | `macros.json` | En el momento |
| `registros` | Registros (para soporte) | `data/logs/` (desactivada por defecto; rclone no escribe registro propio, 12.2, y si quedara un `rclone.log` de otra versión se excluye) | No se restaura: solo se extrae a una carpeta elegida |

- Las contraseñas de unidades de red (Administrador de credenciales de Windows) **no** se copian: no se pueden leer (comprimidos-y-red.md B.3). La copia lo dice.
- `rclone.conf` va cifrado con su propia contraseña aleatoria, que está en `secretos.dat` (12.3): sin incluir los secretos, las cuentas de nube no se podrán abrir tras restaurar y la copia lo advierte. Algunos servicios rotan sus fichas de acceso (OneDrive): tras restaurar, `zc.nubes` comprueba cada cuenta con `operations/about` la primera vez que se usa y, si falla por autorización, la marca «Volver a autorizar» (12.7) en lugar de dar un error en cada uso.
- Los complementos de serie no se copian (vienen con zCommander); sí su estado (habilitado o no) y su configuración.
- La copia nunca lleva `data/config/plugins/claves.json`, ninguna clave `seguridad.*` (en la 1.x, `seguridad.menus_locales_confiados`: ruta → SHA-256 de un `zcommander.menu.json` local aceptado, `app/services/menu_usuario.py`) ni las claves de confianza de los complementos (`complementos.permitir_sin_firma`, `complementos.auditoria`, `complementos.modo_desarrollo` y `complementos.confiados`): la confianza en autores, complementos sin firma y menús locales se decide en cada equipo (3.9). Esas claves no se guardan al crear la copia y, si una copia ajena las trae, se ignoran al restaurar.
- **Lo que hace ejecutar programas u órdenes** no se restaura sin que la persona lo marque, igual que en el `.zcperfil` (10.2). Al restaurar, la segunda lista «Órdenes que se podrán ejecutar» (7.6) recoge, con su texto completo y **sin marcar**: las entradas del menú de usuario (`menu_usuario.json`), las asociaciones (`asociaciones.json`), los alias (`alias.json`), las macros (`macros.json`), las **claves que ejecutan programas u órdenes**, marcadas con el atributo `ejecuta`: en el núcleo, el conjunto `EJECUTA: frozenset[str]` de `app/core/descripciones_config.py` (`editor.usar_externo`, `editor.externo`, `visor.externo`, `general.diferencias_externo` y `comprimidos.ruta_7zip`; `general.consola` no, porque solo elige entre `cmd`, `powershell` y `terminal`; N2 lo crea y quien añade una clave así la añade allí, y una prueba de N2 comprueba que cada nombre de `EJECUTA` es una clave que existe), y en los complementos el campo `ejecuta` de `[[configuracion]]` (3.3; por ejemplo `plugin.zc.git.ruta_git`), las reglas y carpetas de `zc.monitor` (pueden mover archivos y ejecutar órdenes o macros), las tareas de `zc.programador` y los **remotos de `rclone.conf` con opciones que ejecutan programas** (`bearer_token_command` de WebDAV, `ssh` de SFTP y cualquier opción cuyo nombre termine en `_command`; rclone las ejecuta al usar la cuenta y heredan su entorno, con `RCLONE_CONFIG_PASS`). Lo que no se marca no se restaura y se conserva lo actual; un remoto no marcado se quita del `rclone.conf` restaurado y su cuenta queda «Volver a configurar» (12.7). Para leer y editar el `rclone.conf` cifrado de la copia, CS usa `rclone config dump` y `rclone config delete` con `procesos.lanzar`, el `rclone` de `componentes.ruta("rclone")` y `RCLONE_CONFIG_PASS` en el entorno (nunca en los argumentos).
- Las huellas de servidores (`known_hosts` y `hosts_conocidos.json`, parte `conexiones`) no se añaden en bloque: al combinar, cada huella nueva o distinta de la copia se confirma una a una (7.6), porque una huella aceptada permite suplantar ese servidor.

### 7.3 Formato `.zcbackup`

Un ZIP (`ZIP_DEFLATED`) con:

```
manifiesto.json
partes/<id>/...           los archivos tal cual, con su ruta relativa a data/
partes/<id>/valores.json  para preferencias y teclas: {"seccion.clave": valor} (solo esas claves; no confundir con claves.json, el de claves públicas de 3.9)
secretos.bin              opcional: secretos cifrados (7.4)
```

`manifiesto.json`:

```json
{
  "formato": 1,
  "tipo": "copia",
  "app": "zCommander",
  "version_app": "2.0.0",
  "version_esquema": 2,
  "fecha": "2026-11-20T18:30:00",
  "descripcion": "Antes de cambiar de equipo",
  "partes": {"preferencias": {"archivos": [{"ruta": "config/settings.json", "sha256": "...", "tamano": 4211}]}},
  "secretos": {"modo": "contrasena", "kdf": {"algoritmo": "scrypt", "n": 131072, "r": 8, "p": 1, "sal": "<base64>"}, "cifrado": "AES-256-GCM", "nombres": ["ftp:3f2a...:contrasena"]}
}
```

- `tipo`: `copia`, `automatica` (7.6) o `perfil` (`.zcperfil`, 10.2).
- `secretos.modo`: `contrasena` (cifrados con la contraseña de la copia), `dpapi` (solo copias automáticas: los secretos van protegidos con DPAPI de este usuario; no sirven en otro equipo) o `excluidos`.
- Las sumas de cada archivo se comprueban al restaurar; uno que no coincide anula la restauración de su parte.

### 7.4 Cifrado de los secretos

- Clave: `hashlib.scrypt(contraseña_utf8, salt=sal_16_bytes, n=2**17, r=8, p=1, maxmem=128*r*(n+2) + 64 MiB, dklen=32)` (unos 192 MiB; el límite por defecto de OpenSSL, 32 MiB, no basta).
- `secretos.bin` = nonce de 12 bytes + `AESGCM(clave).encrypt(nonce, json_utf8_de_los_secretos, datos_asociados=sha256(manifiesto canónico))` (`cryptography`, fijada en `requirements.txt`, 2.2). El manifiesto canónico es `manifiesto.json` sin el campo `secretos.nombres`, serializado con `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` y codificado en UTF-8 (no los bytes tal como están en el ZIP). Los datos asociados impiden mezclar el archivo de secretos de otra copia.
- La contraseña se pide dos veces al crear (con medidor de fortaleza en texto: «Débil: menos de 12 caracteres») y una al restaurar; una contraseña incorrecta da «La contraseña no es correcta o la copia está dañada» y permite reintentar sin perder lo elegido. No hay recuperación sin la contraseña, y el diálogo lo dice.

### 7.5 Crear (`app/ui/dialogos/cs_crear.py`, orden `copia_crear`)

- «&Guardar en:» con «Examinar...» (por defecto `copia.carpeta` o `data/backups/`, nombre `zCommander-AAAA-MM-DD.zcbackup`).
- «&Qué guardar:» `CheckListBoxAccesible` con las partes de 7.2 y su tamaño; marcadas por defecto todas salvo `registros` (recuerda la última elección en `copia.partes`).
- «&Contraseñas:» opción «Incluirlas cifradas con una contraseña» (por defecto) o «No incluirlas». Con la primera, «Contrase&ña de la copia:» y «&Repita la contraseña:».
- «&Descripción:» (opcional).
- Botones «&Crear la copia» y «&Cancelar». Se crea como operación del motor (progreso, cancelar); al terminar suena `copia.creada` y se anuncia «Copia creada: 2,3 MB, 7 partes».

### 7.6 Restaurar (`app/ui/dialogos/cs_restaurar.py`, orden `copia_restaurar`; también Intro sobre un `.zcbackup`)

1. Elegir el archivo; se valida (ZIP seguro, manifiesto, sumas) y se muestra un resumen en un texto de solo lectura: versión de origen, fecha, descripción, partes con su tamaño, si trae secretos y cómo.
2. «&Qué restaurar:» casillas con las partes que trae la copia.
3. «Órdenes que se podrán &ejecutar:» segunda lista con casillas, **sin marcar** por defecto, con lo de 7.2 que hace ejecutar programas u órdenes (cada elemento con su texto completo: «Menú de usuario: Compilar → cmd /c make %P», «Ruta de 7-Zip: \\\\otro\\recurso\\7z.exe», «Editor externo: notepad.exe %P», «Regla del monitor Descargas: ejecutar la macro Limpiar», «Cuenta de nube Trabajo (WebDAV): ejecuta obtener-token.cmd para conectarse»). Solo se restaura lo marcado.
4. «&Modo:» «Combinar con lo actual» (por defecto) o «Sustituir lo actual».
   - Combinar: en listas (favoritos por ruta, conexiones por `id`, macros por nombre, asociaciones por patrón, alias por nombre, reglas por nombre, complementos por `id`) se añaden los elementos que no existen y se conservan los actuales; en preferencias y teclas se aplican los valores de la copia que difieren de los de fábrica y el resto se conserva. `rclone.conf` y `cuentas.json` de las nubes van juntos y no se mezclan (el archivo de rclone está cifrado): si ya hay cuentas de nube, se conservan las actuales y se avisa de que las de la copia hay que añadirlas de nuevo; si no hay ninguna, se restauran las de la copia. Las **huellas de servidores** nuevas o distintas se confirman una a una antes de aplicar nada: «La copia trae esta huella para sftp.ejemplo.com, puerto 22 (ssh-ed25519 SHA256:...). ¿Aceptarla?» con «&No aceptarla» (predeterminado) y «&Aceptarla».
   - Sustituir: cada parte elegida queda igual que en la copia (salvo lo no marcado del paso 3); el resumen avisa de que se sustituyen todas las huellas de servidores conocidas.
5. Si trae secretos con contraseña: «Contrase&ña de la copia:».
6. Aplicar:
   - Si todas las partes elegidas son «En el momento»: se crea la **copia automática previa** (`data/backups/automaticas/antes-de-restaurar-AAAAMMDD-HHMMSS.zcbackup`, con las mismas partes y los secretos en modo `dpapi`; se conservan las `copia.conservar_automaticas` más recientes), se escriben ya y se emite el evento del bus `al_restaurar` (`partes: list[str]`). Cada servicio con datos en esas partes está suscrito y vuelve a leer su archivo con su función `recargar()` (contrato de N2 en 14.4): favoritos, menú de usuario, asociaciones, plantillas de renombrado y búsquedas guardadas (`busquedas.json`) de la 1.x, que suscribe N2; menús, vistas, reglas, alias y macros, que suscribe PE; paquetes de sonidos, que suscribe SO. Suena `copia.restaurada`.
   - Si alguna es «Al reiniciar»: se prepara `data/config/.restauracion_pendiente/` (archivos y `restaurar.json` con fecha de preparación, descripción, modo, partes, lo marcado del paso 3 y secretos ya descifrados y vueltos a proteger con DPAPI) y se ofrece «&Reiniciar ahora» o «Más &tarde». Con «Reiniciar ahora» se anota `reiniciar_ahora: true`.
7. **Al arrancar**, `app.services.copia.pendiente.aplicar_pendiente(ruta_datos: Path, preguntar: Callable[[InfoPendiente], str] | None) -> ResultadoRestauracion | None` se ejecuta en `main.py` **antes** de cargar la configuración (14.8):
   - Si la restauración se preparó con «Más tarde» (no lleva `reiniciar_ahora`), antes de aplicarla se pregunta con un diálogo nativo de Windows (ya existe `wx.App`, 14.8): «Hay una restauración pendiente de la copia "Antes de cambiar de equipo", preparada el 20 de noviembre de 2026 a las 18:30. Lo que haya cambiado desde entonces en esas partes se sustituirá.» con «&Aplicarla ahora» (predeterminado), «&Descartarla» (borra la carpeta pendiente) y «Más &tarde» (la deja para el siguiente arranque). `preguntar` es esa función, que pasa `main.py`; con `None` (modo tarea, 11.24, y el primer arranque tras actualizar, `--tras-actualizar`) se aplica sin preguntar solo si lleva `reiniciar_ahora`, y si no se deja pendiente. **Tras actualizar no se pregunta nada antes de que la versión nueva confirme su salud** (5.2): la pregunta se hace después de la marca `ok`, en el paso 11 de 14.8, con `consultar_pendiente(ruta_datos: Path) -> InfoPendiente | None` (sin aplicar nada) y las mismas tres opciones; «Aplicarla ahora» llama a `decidir_pendiente(ruta_datos, "aplicar")`, que anota `reiniciar_ahora: true`, y reinicia zCommander (como «Reiniciar», 14.8); «Descartarla» llama a `decidir_pendiente(ruta_datos, "descartar")`; «Más tarde» no hace nada.
   - Justo antes de aplicar, crea **dentro de `aplicar_pendiente`** la copia automática previa (como arriba). Así guarda el estado de ese momento, con lo que la persona cambió después de preparar la restauración, y no el del momento en que la pidió.
   - Aplica, borra la carpeta y devuelve el resultado para anunciarlo tras mostrar la ventana. Si algo falla a medias, restaura esa copia automática y lo explica.
   - `@dataclass(frozen=True) ResultadoRestauracion(ok: bool, mensaje: str, partes: list[str], copia_previa: Path | None)` e `InfoPendiente(fecha: datetime, descripcion: str, partes: list[str])` (lo que recibe `preguntar`, que devuelve `"aplicar"`, `"descartar"` o `"despues"`) viven en `app/services/copia/pendiente.py` (sin wx), con `consultar_pendiente` y `decidir_pendiente(ruta_datos: Path, decision: str) -> None` (`"aplicar"` o `"descartar"`), que N2 crea como provisionales (`aplicar_pendiente` y `consultar_pendiente` devuelven `None`; `decidir_pendiente` no hace nada) y CS completa.
8. **Complementos**: la configuración y los secretos de la parte `complementos` se aplican como el resto; los paquetes no se escriben directamente en `data/plugins/`. Tras mostrar la ventana, cada `<id>.zcplugin` de la copia que no esté instalado (o, con «Sustituir», que tenga otra versión) se ofrece por el flujo normal de instalación de 3.10, con su resumen accesible, su firma, su clave fijada y su pregunta; la persona puede instalarlos todos, uno a uno o ninguno. Así un `.zcbackup` ajeno abierto con Intro nunca instala código, claves de confianza ni órdenes ejecutables en silencio.

### 7.7 Versiones

- Copia de una versión anterior: se restaura y las migraciones de cada archivo (las de `Configuracion` y las de los JSON auxiliares con su `"version"`) la ponen al día al cargar.
- Copia de una versión más nueva: si `formato` es mayor que el conocido, se rechaza («Esta copia es de una versión más nueva de zCommander; actualice primero»); si solo `version_app` o `version_esquema` son mayores, se avisa y se puede seguir (las claves desconocidas se conservan, 1.x §10).

### 7.8 Módulos

`app/services/copia/` (sin wx): `formato.py` (partes, manifiesto, validación, `leer_manifiesto(ruta: Path) -> ManifiestoCopia`, la lista de 7.2 de lo que hace ejecutar órdenes), `crear.py` (`crear_copia(destino: Path, partes: Sequence[str], tipo: str, modo_secretos: str, contrasena: str | None, descripcion: str, progreso, cancelacion) -> Path`, que usan también la exportación de `.zcperfil` y las copias automáticas), `restaurar.py`, `cifrado.py`, `combinar.py` (también la confirmación de huellas), `pendiente.py` (provisional de N2, 7.6). Con wx: `app/ui/dialogos/cs_crear.py`, `cs_restaurar.py`, `cs_perfil.py` (exportar e importar `.zcperfil` con su vista previa, 10.2), `app/ui/acciones/copia_cs.py`.

## 8. Comprimidos ampliados (núcleo)

Amplía 1.x §8.15 según comprimidos-y-red.md parte A. Navegar, ver, extraer (copiar desde el proveedor con el motor), buscar dentro y probar funcionan igual en todos los formatos; escribir dentro como carpeta sigue siendo solo de ZIP.

### 8.1 Formatos y motor

| Formato | Ver y navegar | Crear (Alt+F5) | Motor |
|---|---|---|---|
| ZIP (almacenado, deflate, zstd método 93) | Sí, y escritura dentro | Sí (método elegible) | `zipfile` |
| ZIP con AES (WinZip) | Sí, con contraseña | Sí, AES-256 | Lectura: libarchive; creación: 7za si está, si no libarchive |
| ZIPX | Sí | No | libarchive |
| TAR, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.tar.zst`, `.tzst` | Sí | Sí | `tarfile` (`r:zst` y `w:zst` de Python 3.15) |
| `.tar.lz`, `.tar.lz4`, `.tar.lzma`, `.tlz`, `.tar.Z` | Sí | `.tar.lz` y `.tar.lz4` | libarchive |
| `.gz`, `.bz2`, `.xz`, `.lzma`, `.zst` sueltos | Carpeta con un archivo | Sí (un archivo por elemento) | `gzip`, `bz2`, `lzma`, `compression.zstd` |
| `.lz`, `.lz4`, `.Z` sueltos | Carpeta con un archivo | No | libarchive (formato `raw`) |
| 7z | Sí (ya existe, py7zr); si py7zr no admite el método (BCJ2, ARM64, zstd) y no está cifrado, libarchive | Sí: con AES por py7zr o 7za; sin cifrar también libarchive | py7zr, 7za, libarchive |
| RAR 2.9 a 4.x y RAR5 sin cifrar (sólidos y multivolumen) | Sí | No (formato propietario) | libarchive |
| RAR y 7z cifrados | Solo con el 7-Zip de la persona | No | `7z.exe` instalado |
| CAB, LHA y LZH, cpio, ar, `.deb`, `.rpm`, XAR (`.pkg`), WARC | Sí | cpio, XAR | libarchive |
| ISO 9660 con Joliet y Rock Ridge | Sí (no UDF) | Sí (ISO 9660) | libarchive |
| ARJ, CHM, MSI, NSIS, WIM, VHD(X), DMG, UDF, SquashFS | Solo con el 7-Zip de la persona | No | `7z.exe` instalado |

Extensiones registradas (`resolver.registrar_comprimido`): las de la tabla, más `.r00`/`.part1.rar` para multivolumen (se abren desde la primera parte con todas las partes, con la función ancha `archive_read_open_filenames_w`; CM comprueba al empezar que `libarchive-13.dll` 3.8.11 la exporta y, si no, deja el multivolumen sin registrar y lo dice en el registro). Con el 7-Zip de la persona se registran además `arj`, `chm`, `msi`, `wim`, `vhd`, `vhdx`, `dmg`, `squashfs` y `nsis` (solo si se detecta y `comprimidos.usar_7zip_instalado` está activa).

### 8.2 Proveedor libarchive (`app/services/vfs/libarchive.py` y `app/services/libarchive/`)

- `app/services/libarchive/ffi.py`: carga `data/bin/libarchive/libarchive-13.dll` con `os.add_dll_directory(carpeta)` y ruta absoluta (las dependencias se buscan en la carpeta de la DLL, nunca en `PATH`), con `argtypes` y `restype` explícitos de las funciones de comprimidos-y-red.md A.7; solo las funciones anchas (`_w`). Si la DLL falta o no carga, los formatos de libarchive quedan sin registrar y se registra la causa (y 6.8 lo explica).
- `lectura.py`: índice (`archive_read_next_header` con `archive_entry_pathname_w`, tamaño, fecha, tipo, cifrado) y lectura de un miembro a un flujo por bloques de 1 MiB. Cada nombre pasa por `nombre_seguro()` del proveedor de comprimidos (1.x §9.4); los enlaces se omiten. En formatos sólidos se reutiliza la estrategia de `siete_z.py` (temporales previos del bloque) y, cuando el motor pide muchos miembros, una extracción por lotes en el orden del archivo.
- `escritura.py`: creación con `archive_write_*` (ZIP con `zip:encryption=aes256` y `archive_write_set_passphrase`, 7z sin cifrar, ISO, cpio, tar con filtros).
- `ProveedorLibarchive(ProveedorComprimido)`: solo lectura; un objeto `archive` por hilo (`clonar()` abre otro); progreso con `archive_filter_bytes`; cancelación entre bloques; errores de `archive_error_string` traducidos a `ErrorArchivos` en español (el inglés va al registro).
- **Cifrado**: libarchive solo descifra ZIP. Si una entrada de RAR o 7z está cifrada: con el 7-Zip de la persona, se usa (8.5); sin él, suena `comprimido.cifrado_sin_motor` y se explica «Este RAR está cifrado. zCommander no puede descifrarlo sin 7-Zip instalado» (nunca «contraseña incorrecta»).
- Reserva: si `zipfile` lanza «compression method» o «encryption not supported» con un ZIP, `ProveedorZip` pasa la lectura a libarchive (con la contraseña del `Decisor`).

### 8.3 Flujos sueltos (`app/services/vfs/flujo.py`)

`ProveedorFlujoUnico`: `nombre.ext.gz` se ve como una carpeta con un solo archivo `nombre.ext` (sin la extensión de compresión; si no queda nombre, `contenido`). Tamaño desconocido (−1) salvo en gzip (campo ISIZE, módulo 4 GiB). Solo lectura. Con `comprimidos.flujos_como_carpeta` desactivada, Intro abre el archivo con su programa.

### 8.4 7za (`app/services/siete_zip_externo.py`)

- Si `data/bin/7za/7za.exe` existe y `comprimidos.usar_7za` está activa, Comprimir lo usa para 7z (multihilo, AES con cabeceras cifradas) y ZIP con AES-256, con progreso real (`-bsp2`, porcentajes por `\r`).
- Llamada con `app.core.procesos.lanzar` (sin consola ni shell, lista de argumentos, rutas tras `--`, `-spd`, en el Job Object global), con la contraseña **por la entrada estándar** (nunca `-p<clave>`). `-p` vacío no significa lo mismo en todas las órdenes de 7-Zip; lo comprobado con 7za 26.06 (21.3) fija estas reglas:
  - **Crear** (`a`) sin contraseña: sin `-p`. Con contraseña (también con `-mhe=on`): `-p` vacío y la contraseña escrita **una vez** en la entrada estándar (una línea basta).
  - **Listar, probar o extraer** (`l`, `t`, `x`, `e`) con una contraseña conocida: **sin** `-p`, y la contraseña escrita en la entrada estándar (7za la pide y la lee de ahí). Con `-p` vacío no la lee: la toma como vacía y falla con «Wrong password».
  - **Saber si un comprimido está cifrado** sin esperar: `-p` vacío y la entrada estándar cerrada; si hace falta contraseña, falla enseguida.

  Códigos de salida de comprimidos-y-red.md A.3 traducidos a mensajes.
- Lista de miembros con `@lista.txt` en UTF-8 (`-scsUTF-8`) en `data/temp`.

### 8.5 7-Zip instalado

- Detección: `HKLM\SOFTWARE\7-Zip` y `HKCU\Software\7-Zip`, valores `Path64` y `Path`, y `comprimidos.ruta_7zip` si la persona la fija. Se comprueba que existe `7z.exe` y se lee su versión (`7z i`).
- Uso (`ProveedorSieteZipInstalado`, solo lectura): RAR y 7z cifrados y los formatos de la última fila de 8.1. Listado con `7z l -slt -sccUTF-8 -ba` (formato de comprimidos-y-red.md A.3), lectura de un miembro con `7z e -so ... -- miembro`. Las contraseñas siguen las mismas reglas que 7za en 8.4 (el `7z.exe` instalado es el mismo programa de consola): sin `-p` y la contraseña por la entrada estándar para listar y extraer; `-p` vacío con la entrada cerrada para saber si está cifrado. Nunca se distribuye ni se actualiza desde zCommander.

### 8.6 Diálogo Comprimir (cambios en `app/ui/dialogos/c_comprimir.py`)

- «&Formato:» gana ZIP (Zstandard), ZIP cifrado con AES-256, TAR.ZST, TAR.LZ4, TAR.LZ, ISO, cpio y los flujos `.gz`, `.bz2`, `.xz`, `.zst` (estos crean un archivo comprimido por elemento; con carpetas se desactivan y se dice por qué).
- «Contrase&ña:» se habilita en 7z y ZIP con AES; «Cifrar también los &nombres» en 7z.
- «Motor:» informativo (texto de solo lectura: «7za 26.06», «libarchive 3.8.11», «Python»), para que la persona sepa qué se usa.

### 8.7 Seguridad

Igual que la 1.x (1.x §14): validación de nombres en el proveedor, marca de la Web heredada, temporales en `data/temp/extraidos`. Además: la DLL se carga solo desde `data/bin/libarchive` (ruta absoluta); los procesos 7za y 7z van con `app.core.procesos` (Job Object global, tiempo máximo, sin consola); ninguna contraseña en la línea de órdenes ni en el registro.

### 8.8 Módulos y dueños

Bloque CM: `app/services/libarchive/ffi.py`, `lectura.py`, `escritura.py`; `app/services/vfs/libarchive.py`, `flujo.py`, `siete_zip_instalado.py`; `app/services/siete_zip_externo.py`; cambios en `app/services/vfs/zip.py` (después de los de N2: dueño posterior, 19.1), `tar.py`, `siete_z.py`, `app/services/comprimir.py`, `app/services/operaciones/comprimir.py` y `app/ui/dialogos/c_comprimir.py` (también después de N2, que les añade el argumento de las macros, 19.1). `app/services/vfs/registro_proveedores.py` no lo toca: N2 deja ya en `MODULOS` los nombres nuevos (`vfs.libarchive`, `vfs.flujo`, `vfs.siete_zip_instalado`, `vfs.red`), que la 1.x tolera mientras no existen (`ModuleNotFoundError`). Argumento `--probar-componente libarchive` (6.2) implementado aquí en `app/services/libarchive/prueba.py`, que `componentes.prueba.probar_componente` llama.

## 9. Unidades de red completas (núcleo)

Amplía 1.x §8.22 con las 15 funciones de comprimidos-y-red.md B.8. La conexión FTP, FTPS y SFTP (1.x §8.16) no cambia.

### 9.1 Raíz «Red»

- Dirección `red://` (esquema registrado con `resolver.registrar_esquema("red", ...)`), proveedor `ProveedorRed` (`app/services/vfs/red.py`), solo lectura. Se llega con la orden `red_raiz` (Ctrl+Mayús+K), con «Red» en el selector de unidades (Alt+F1 y Alt+F2) y escribiendo `red://` en Ir a la carpeta.
- Una sola lista (no carpetas por grupo, para llegar antes con el lector), ordenada por grupo y nombre, con estas columnas: Nombre, Tipo, Remoto, Estado. Tipos y orden:
  1. «Unidad de red»: `Z:` con su remoto y estado («Conectada», «Desconectada: Intro para volver a conectar», «No disponible»), de `WNetOpenEnum` con `RESOURCE_CONNECTED` y `RESOURCE_REMEMBERED` más `NetUseEnum(None, 2)`.
  2. «Conexión sin letra»: `\\servidor\recurso` conectados sin letra.
  3. «Servidor reciente» y «Servidor favorito»: de `data/config/red.json` (`{"version": 1, "recientes": ["\\\\DS220"], "favoritos": [{"nombre": "NAS", "ruta": "\\\\DS220"}]}`; 20 recientes).
  4. «Equipo encontrado»: del descubrimiento (9.2), que llega poco a poco.
  5. «Otro proveedor»: `\\wsl.localhost`, `\\tsclient`, «WebDAV (WebClient)», «SSHFS» y «NFS» si están instalados (`red.mostrar_otros_proveedores`).
- Intro: en una unidad o conexión lleva el panel a esa ruta (proveedor local); en una unidad desconectada intenta reconectar (9.4) y entra; en un servidor o equipo lleva a `\\equipo` (lista de recursos, 1.x §8.22, ampliada en 9.3). Retroceso en `\\equipo` vuelve a `red://` con el cursor en el equipo.
- Con el cursor en una unidad o conexión, las órdenes `desconectar_unidad_red` (9.5), `red_reconectar` (9.4) y `red_info` (9.6) actúan sobre ella sin preguntar cuál. F8 y Supr no desconectan (el proveedor es de solo lectura y avisa «Use Desconectar unidad de red»).
- La vista se rellena en dos tiempos: lo local (unidades, conexiones, recientes) en menos de 1 s; los equipos se añaden según llegan, sin mover el cursor del lector (la lista conserva el elemento enfocado, 1.x §5.6), con la fila «Buscando equipos...» mientras dura y el anuncio final «Búsqueda terminada: 3 equipos» (resultado; suena `red.descubrir_fin`). Escape cancela el descubrimiento (en el lugar que le toca en la orden «Cancelar o quitar», 10.1).

### 9.2 Descubrir equipos (`app/services/windows/red_descubrir.py`)

- Fuentes, en hilos desechables con COM iniciado y tiempo máximo `red.tiempo_descubrir_s` entre todas:
  1. Carpeta «Red» del shell (`SHGetSpecialFolderLocation(0, CSIDL_NETWORK)`, `EnumObjects`, `GetDisplayNameOf(SHGDN_FORPARSING)`), quedándose con lo que empieza por `\\`; los dispositivos SSDP se ignoran. Se leen de uno en uno (`IEnumIDList.Next`) para entregar resultados a medida que llegan.
  2. mDNS, si `red.descubrir_mdns`: `DnsServiceBrowse` de `dnsapi.dll` con `_smb._tcp.local` (Windows 10 1903 o posterior), cancelable con `DnsServiceBrowseCancel`.
  3. Dominio, si `red.descubrir_dominio` y `NetGetJoinInformation` dice `NetSetupDomainName`: búsqueda LDAP `(objectCategory=computer)` por ADSI.
- No se usan `NetServerEnum` ni el nivel de dominio de `WNetOpenEnum` (fallan sin SMB1, error 6118 tras 31 s; comprimidos-y-red.md B.1).
- Resultado: `EquipoRed(nombre, ruta_unc, fuente, direccion)` sin duplicados (por nombre en mayúsculas). Con `red.descubrir_al_entrar` desactivada, solo se busca con la orden `red_buscar_equipos` (sin tecla de fábrica, en Comandos > Red) o con «Volver a leer» (Ctrl+R, la orden de la 1.x) en `red://`, que relanza el descubrimiento.

### 9.3 Recursos de un servidor

- `\\servidor`: `NetShareEnum(servidor, 1)`; si falla, `WNetOpenEnum` sobre el contenedor del servidor con su proveedor. Los recursos `$` se muestran solo con `paneles.mostrar_ocultos`; las impresoras van al final con tipo «Impresora» y no se puede entrar en ellas.
- Errores 5, 86 o 1326 piden credenciales (9.4) y se repite. Error 1219 ofrece «Cerrar las conexiones a este servidor y reintentar» o «Usar otro nombre del servidor (su IP)».
- Cada servidor visitado se añade a «Servidores recientes».

### 9.4 Conectar con credenciales

- **Estado de la 1.x**: la orden `conectar_unidad_red` (`app/ui/acciones/red_d.py`, `conectar_unidad`) ya usa un diálogo propio, `DialogoConectarUnidad` de `app/ui/dialogos/d_unidad.py` (letra, carpeta compartida, usuario, contraseña, recordar), y `desconectar_unidad_red` usa `DialogoDesconectarUnidad` (olvidar, forzar, con la pregunta de forzar ante 2401 y 2404); los cuadros de Windows solo salen como alternativa interna (`_cuadro_windows`). `app/services/windows/red.py` ya tiene `conectar(letra, remoto, usuario, contrasena, recordar)` (también sin letra) y `desconectar(letra, forzar, olvidar)`, y `UnidadRed` ya tiene `conectada` y `recordada`.
- **Lo que cambia**: RD **amplía** esos dos diálogos en `d_unidad.py` (no se crean otros): «&Carpeta compartida:» gana la lista de recientes; «&Letra:» gana «Sin letra» y «Automática» (las libres de la Z hacia atrás); se añaden las casillas «&Volver a conectar al iniciar sesión» y «E&xigir cifrado SMB» (`red.exigir_cifrado`) a las de la 1.x («&Usuario:», vacío para la cuenta actual de Windows; «C&ontraseña:»; «&Recordar la contraseña» en el Administrador de credenciales de Windows). Botones «Co&nectar» y «&Cancelar».
- API, compatible con la llamada de la 1.x (`red.conectar(letra, remoto, ...)` en `red_d.py`): `red.conectar(letra: str, remoto: str, usuario: str = "", contrasena: str = "", recordar: bool = False, *, persistente: bool = True, exigir_cifrado: bool = False) -> str` (devuelve la letra usada o «»; `letra` vacía = sin letra, `"*"` = automática); usa `WNetAddConnection2` con `CONNECT_UPDATE_PROFILE` (solo si `persistente`) y `CONNECT_REQUIRE_PRIVACY`; letra automática con `WNetUseConnection` y `CONNECT_REDIRECT` (`ctypes`); credenciales con `win32cred.CredWrite` (`CRED_TYPE_DOMAIN_PASSWORD`, `CRED_PERSIST_ENTERPRISE`). La contraseña no se guarda en zCommander ni se registra.
- **Sin letra**: orden `red_conectar_recurso` (el mismo diálogo con «Sin letra» fijado); al terminar, el panel va al recurso.
- **Reconectar** (`red.reconectar(letra)`): al entrar en una unidad que da 1201 (recordada, no conectada), si `red.reconectar_al_entrar`, `WNetRestoreSingleConnectionW` (`ctypes`) o `WNetAddConnection2` con el remoto recordado; si faltan credenciales, el diálogo de 9.4 con el remoto puesto. Orden `red_reconectar` para hacerlo a mano. Mensaje: «Z: no está disponible (\\DS220\home). Intro para volver a conectar».
- Pregunta de credenciales desde hilos: método nuevo del protocolo `Decisor` (N2, 14.6), `pedir_credenciales(titulo: str, texto: str, usuario: str = "", operacion: Operacion | None = None) -> tuple[str, str, bool] | None` (usuario, contraseña, recordar; `None` si se cancela), implementado en `ui/decisiones.py` y en los decisores falsos. El diálogo vive en `app/ui/dialogos/rd_credenciales.py` con la función `pedir(padre: wx.Window, titulo: str, texto: str, usuario: str) -> tuple[str, str, bool] | None`: lo **crea N2** con un diálogo provisional (usuario y contraseña) y `decisiones.py` lo importa desde el principio; RD es su dueño posterior y lo completa (casilla «Recordar», ayuda, sonido `red.credenciales`) sin tocar `decisiones.py`. `pedir_texto` de la 1.x solo pide un texto.

### 9.5 Desconectar y olvidar

- Orden `desconectar_unidad_red`: el `DialogoDesconectarUnidad` de la 1.x se amplía con las conexiones sin letra en la lista y la casilla «Olvidar también la contraseña guardada» junto a «Olvidar la conexión»; `red.desconectar(letra_o_remoto, forzar, olvidar, *, olvidar_credencial: bool = False)` sigue usando `WNetCancelConnection2`. Nuevo: antes se saca a los paneles de zCommander de esa unidad (su directorio de trabajo la bloquea). La pregunta de 2401 o 2404 es la de la 1.x («¿Desconectar a la fuerza? Los programas que usan archivos de Z: pueden perder datos.», foco en «&No»).
- Orden `red_contrasenas`: lista de credenciales de tipo dominio guardadas (`CredEnumerate`), con «&Olvidar» (`CredDelete`) y confirmación.
- Los cuadros de Windows, que en la 1.x solo salen como alternativa interna, pasan a ser órdenes propias: `red_cuadro_conectar` y `red_cuadro_desconectar` (sobre el `_cuadro_windows` de `red_d.py`).

### 9.6 Información de la conexión (`app/services/windows/red_info.py`)

`informacion(ruta) -> InfoRed` con espacio (`GetDiskFreeSpaceEx`), volumen (`GetVolumeInformation`), remoto, usuario y proveedor (`WNetGetConnection`, `WNetGetUser`, `WNetGetUniversalName`), estado (`NetUseEnum` nivel 2) y detalle SMB por WMI (`MSFT_SmbConnection`: dialecto, cifrado, firma, archivos abiertos; `MSFT_SmbMultichannelConnection`: velocidad del enlace). Se usa en:

- La orden `red_info` (en la raíz «Red», sobre la fila del cursor): un texto de solo lectura con todo.
- Ctrl+Mayús+I y la vista Información sobre una unidad o ruta de red: una línea con el resumen («Z:, \\DS220\home, conectada, SMB 3.1.1 cifrada, usuario ana, 1,2 TB libres de 2 TB, enlace a 1 Gbps»).
- `copiar_ruta_unc`: copia `WNetGetUniversalName` de los elementos de trabajo (de `Z:\carpeta` a `\\srv\rec\carpeta`); suena `portapapeles.texto`.

### 9.7 WebDAV, SSHFS y NFS

- WebDAV como letra (redirector WebClient): en el diálogo de 9.4, una dirección `https://...` o `\\servidor@SSL@puerto\DavWWWRoot\carpeta` se conecta con `WNetAddConnection2`. Si el servicio WebClient está deshabilitado (`QueryServiceConfig`), se explica sin intentar cambiarlo; se recuerda que Microsoft lo declaró obsoleto y que el complemento Nubes ofrece WebDAV propio.
- SSHFS-Win y NFS: se detectan sus proveedores (`HKLM\SYSTEM\CurrentControlSet\Control\NetworkProvider\Order` y `WNetGetProviderName`) y se ofrecen sus formas de ruta (`\\sshfs\usuario@host!puerto\ruta`; `\\servidor\exportacion`) en la ayuda del campo; no se instalan.

### 9.8 Sesiones y archivos abiertos (opcional, elevado)

Orden `red_sesiones`: ventana con dos listas (Sesiones: equipo, usuario, tiempo, inactividad; Archivos abiertos: ruta, usuario, bloqueos) de `NetSessionEnum` (10 o 502) y `NetFileEnum` (3), con «Cerrar la &sesión» y «Cerrar el &archivo» (`NetSessionDel`, `NetFileClose`), con confirmación. Si zCommander no está elevado, la orden explica que hace falta ejecutarlo como administrador y que zCommander no se eleva solo.

### 9.9 Errores y tiempos

- Todo en hilos desechables con tiempo máximo (1.x §9.7) y `SetErrorMode(SEM_FAILCRITICALERRORS)`. Los dos cuadros de Windows, en el hilo de la interfaz.
- `_mensaje_error` de `red.py` añade: 64 «Se perdió la conexión con el servidor», 1201 «La unidad está desconectada», 1208 (texto del proveedor con `WNetGetLastError`), 1240 «La cuenta no puede iniciar sesión desde este equipo», 1272 (`ERROR_SMB_GUEST_LOGON_BLOCKED`) «Windows bloqueó el acceso como invitado (SMB sin autenticación)», 6118 «Windows ya no puede listar los equipos del grupo de trabajo; se buscan por detección de redes».
- Elevación: un zCommander elevado no ve las letras de la sesión sin elevar; el mensaje lo explica (directiva `EnableLinkedConnections`) sin cambiar nada.

### 9.10 Módulos y dueños

Bloque RD: `app/services/windows/red.py` (ampliado: `UnidadRed` conserva `conectada` y `recordada` y gana `proveedor` y `usuario`; las conexiones sin letra tienen `letra` vacía; `conectar` y `desconectar` con los parámetros nuevos de 9.4 y 9.5, `reconectar`, `credenciales`, `recursos`), `red_descubrir.py`, `red_info.py`, `red_servidor.py`; `app/services/vfs/red.py` (su módulo ya está en `MODULOS` desde N2); `app/services/red_recientes.py` (`red.json`); `app/ui/dialogos/d_unidad.py` (ampliado), `rd_credenciales.py`, `rd_contrasenas.py`, `rd_info.py`, `rd_sesiones.py`; `app/ui/acciones/red_d.py` (las órdenes de unidades de red de la 1.x) y `red_rd.py` (las nuevas). Las conexiones FTP y SFTP de `red_d.py` no cambian.

## 10. Personalización avanzada (núcleo)

Las mejoras de plugins.md sección 5 que entran en la 2.0 (las que no, en 1.4). Todas con su recorrido completo de preferencia (agente de configuración) y diálogos que pasan `revisar_teclado`.

### 10.1 Macros

- **Formato** `data/config/macros.json`:

```json
{"version": 1, "macros": [
  {"nombre": "Fotos a la copia", "tecla": "", "menu": true, "paleta": true,
   "pasos": [
     {"orden": "ir_a_carpeta", "argumento": "D:\\Fotos"},
     {"orden": "marcar_patron", "argumento": "*.jpg;*.jpeg"},
     {"orden": "copiar", "argumento": {"destino": "E:\\Copia\\Fotos", "politica": "omitir", "sin_dialogo": true}, "esperar": true},
     {"orden": "paso:decir", "argumento": "Copia lanzada"}
   ]}
]}
```

- Cada macro es una orden dinámica del catálogo con id `macro:<nombre>` (bloque `PE`, ámbito global, manejador `personalizar_pe.ejecutar_macro` con `param` = nombre, 14.1.1): aparece en la paleta, en Opciones > Macros y en el menú «Mis órdenes» si `menu`, y puede tener tecla (se guarda en `teclado.personalizadas` como cualquier otra) o tecla global (10.15). En el menú de usuario (F2) y en las asociaciones se escribe `zc:macro:<nombre>`.
- **Órdenes con argumento** (tabla `ARGUMENTOS: dict[str, Argumento]` de `app/services/macros_argumentos.py`, de N2, con `@dataclass(frozen=True) Argumento(tipo: Literal["ruta", "patron", "texto", "json"], campos: tuple[str, ...] = ())`, donde `campos` son las claves admitidas de un argumento `json`; las demás órdenes se graban sin argumento y al reproducirlas abren su diálogo): `ir_a_carpeta` (`ruta`: ruta o dirección), `marcar_patron`, `desmarcar_patron` y `filtro` (`patron`), `crear_carpeta` (`texto`: nombre), `copiar` y `mover` (`json`: `destino`, `politica`, `verificar`, `sin_dialogo`), `comprimir` (`json`: `formato`, `nombre`, `sin_dialogo`), `extraer` (`json`: `destino`, `sin_dialogo`), `ejecutar_linea` (`texto`: la orden), `menu_usuario` (`texto`: etiqueta de la entrada), `espacios_trabajo` (`texto`: nombre del espacio que se abre sin mostrar la lista; no hay orden `abrir_espacio`, 14.1.2) y, de las pestañas, solo `pestana_nueva` (`ruta`: la carpeta que abre). Las demás `pestana_*` (`pestana_cerrar`, `pestana_cerrar_otras`, `pestana_siguiente`, `pestana_anterior`, `pestana_bloquear` y `pestana_1` a `pestana_9`) y `ordenar_*` son deterministas (lo que necesitan va en su `param`) y se graban sin argumento. Además, las órdenes de complementos que declaren `argumento` en su `[[ordenes]]` (3.3), que lo reciben en `ContextoComplemento.argumento`. Pasos especiales, que no son órdenes del catálogo (prefijo `paso:`, distinto de `macro:`, así ninguna macro puede tener su id): `paso:decir` (anuncia un texto, nivel resultado), `paso:esperar` (milisegundos) y `paso:sonar` (id de evento de sonido).
- **Cómo llega el argumento**: una sola firma en todo el documento, `ejecutar_orden(id_orden: str, lado: str | None = None, *, argumento: Any = None) -> None`, en `ContextoOrden`, en `Anfitrion` (3.7) y en `VentanaPrincipal` (que además tiene `desde_menu: bool = False`, también solo por nombre). `lado` sigue pudiendo ir por posición porque la 1.x ya lo pasa así (`dialogos_f.py`, `contexto.py`, el menú de `ventana_principal.py` y dos pruebas); todo lo nuevo va solo por nombre. El manejador lee el argumento en `ctx.argumento`. Para cada orden de `ARGUMENTOS`, N2 adapta (19.1) su manejador (en `acciones/archivos.py`, `navegacion.py`, `marcas.py`, `vista.py`, `comprimidos_c.py`, `linea.py`) y su diálogo de la 1.x (`dialogos/copiar.py`, `nombre.py`, `c_comprimir.py`): con `argumento`, usan esos valores; con `sin_dialogo`, no muestran el diálogo; y antes de cerrarse el diálogo llaman a `ctx.servicio("grabador").anotar_argumento(valor)` (N2 registra el servicio `grabador` como uno que no hace nada hasta que PE lo sustituye; protocolo en 14.9). El formato de cada argumento es el de la tabla `ARGUMENTOS`, que N2 fija en `app/services/macros_argumentos.py` (sin wx) y PE usa.
- **Grabar**: `macro_grabar` (Ctrl+Mayús+G, casilla) empieza y termina. La grabación es **solo por llamada directa y síncrona**, nunca por el bus (que entrega más tarde): `VentanaPrincipal.ejecutar_orden`, por donde pasan el despachador, la paleta, los menús y la barra, llama a `servicio("grabador").anotar(id_orden, argumento)` **antes** de llamar al manejador, si el grabador está grabando y la orden es `grabable`; así el paso queda apuntado antes de que su diálogo llame a `anotar_argumento`. Los diálogos de las órdenes con argumento pasan sus valores finales con `grabador.anotar_argumento(valor)` antes de cerrarse. No se graban teclas sueltas ni las órdenes con `grabable = False` en el catálogo (campo nuevo de `Orden`, 14.1.1): las de consulta de 1.x §6.4 (decir la ruta, el espacio, las marcas, leer columnas...), `macro_grabar`, `macro_ultima` y `cancelar`. No se decide por la tecla: `marcar_patron` (Ctrl+Mayús+M) sí se graba. Al terminar se pide el nombre y se abre el editor. Suenan `macro.grabar` y `macro.parar`; la etiqueta de la ventana añade «Grabando macro».
- **Ejecutar**: los pasos se ejecutan en orden en el hilo de la interfaz con `ctx.ejecutar_orden_futuro(id, argumento=...)` (3.4), sin bloquearlo: el paso siguiente empieza cuando se resuelve el futuro del anterior (una orden de un complemento que se estaba cargando ya se ha ejecutado; un futuro resuelto con falso cuenta como paso fallido), y un paso que lanza una operación con `esperar` (por defecto en copiar, mover, comprimir y extraer) deja la macro en espera hasta el `al_terminar_operacion` de esa operación. Para saber qué operación lanzó un paso, N2 añade a `Operacion` el atributo `orden_origen` (el id de la orden en cuyo manejador se lanzó) y el bus emite `al_empezar_operacion` con él. Lo pone **`ContextoOrden.lanzar`** (`operacion.orden_origen = self.orden` antes de pasarla a la ventana; el gestor de operaciones no recibe el contexto); las llamadas directas de la 1.x a `ventana.lanzar_operacion` (`acciones/archivos.py`, `windows_g.py`) pasan el id con el parámetro nuevo `ventana.lanzar_operacion(operacion, en_cola=False, al_terminar=None, *, orden_origen: str = "")`; en los complementos lo pone `Anfitrion.lanzar` (3.7). `macros.pausa_ms` entre pasos; `macros.anunciar_pasos` anuncia cada paso (detalle); con `macros.detener_en_error`, un paso que falla (excepción, orden no disponible, operación fallida o cancelada) detiene la macro y se anuncia «La macro se detuvo en el paso 3: Copiar». `macro_ultima` (Ctrl+Mayús+L) repite la última ejecutada.
- **Escape en el panel** (orden `cancelar`, «Cancelar o quitar», de la 1.x): en la 2.0 hace lo primero que se pueda de esta lista, en este orden: 1) detener la macro en curso; 2) cancelar la lectura, el cálculo o el descubrimiento de equipos en curso del panel (en `red://`, 9.1); 3) quitar el filtro rápido; 4) detener la orden lanzada desde la línea de órdenes. N2 cambia su manejador (`navegacion.cancelar`) y su ayuda en el catálogo con esa lista; el paso 1 llama al servicio `macros` (que PE sustituye) y el 2 al proveedor del panel.
- **Editor** (`app/ui/dialogos/pe_macros.py`, orden `macros`): lista de macros (Nombre, Tecla, Pasos) con «&Nueva», «&Editar», «&Duplicar», «E&liminar», «E&jecutar», «&Grabar una nueva», «E&xportar...» e «&Importar...» (`.zcmacro`: JSON con una macro). Importar (también Intro sobre un `.zcmacro`) muestra antes una **vista previa** con la lista «Órdenes que se podrán ejecutar» de 10.2: cada paso con su texto completo («Ejecutar en la línea de órdenes: del /s /q %P», «Menú de usuario: Compilar»), **sin marcar** los que ejecutan programas u órdenes (`ejecutar_linea`, `menu_usuario`, órdenes de complementos con permiso `ejecutar_programas` y `macro:` de otras macros); la macro se importa con los pasos marcados y sin los demás, y se dice cuántos se quitaron («Se importó la macro sin 2 pasos que no marcó»). El editor de una macro: «&Nombre:», casillas «En el menú Mis órdenes» y «En la paleta», «&Tecla:» (botón que captura la tecla y avisa de choques, como el mapa de teclas), lista de pasos (Orden, Argumento) con «&Añadir paso...» (elige la orden con el buscador de la paleta), «&Cambiar el argumento...», «&Subir», «&Bajar», «&Quitar» y «&Probar».

### 10.2 Perfiles propios exportables

- Además de Novato, Intermedio y Avanzado (1.x §2.2), perfiles con nombre en `data/config/perfiles/<nombre>.json` (`{"version": 1, "nombre": "...", "descripcion": "...", "valores": {"seccion.clave": valor}}`, solo claves de preferencias y teclas, nunca secretos ni `ventana.*`).
- El diálogo de perfil (orden `perfil`) los lista junto a los de fábrica, con «&Guardar la configuración actual como perfil...» (orden `perfil_guardar_propio`), «&Renombrar» y «&Eliminar» en los propios.
- **`.zcperfil`** (bloque CS: formato, órdenes, diálogo y vista previa en `cs_perfil.py`; PE solo aporta `perfil_guardar_propio`): una copia de seguridad de tipo `perfil` (7.3) con las partes `preferencias`, `teclas`, `personalizacion` y `macros` y, si se pide, los paquetes de sonidos propios; **nunca** secretos ni conexiones. Órdenes `perfil_exportar` y `perfil_importar` (también Intro sobre un `.zcperfil`). Importar muestra una **vista previa** en una lista (Preferencia, Valor actual, Valor del perfil) con casillas para elegir qué se aplica, y siempre combina. Lo que ejecuta programas u órdenes (entradas del menú de usuario, asociaciones, alias y macros) va en una segunda lista aparte, «Órdenes que se podrán ejecutar», con el texto completo de cada una y **sin marcar** por defecto: la persona marca una a una las que acepta. Sirve para que un formador prepare la configuración de sus alumnos.

### 10.3 Sonidos por evento

Cubierto por la sección 4 (cada evento activable, paquetes y sustitución de anuncios).

### 10.4 Columnas y vista por carpeta

- `data/config/vistas_carpeta.json`:

```json
{"version": 1,
 "conjuntos": [{"nombre": "Música", "columnas": ["nombre", "zc.metadatos:artista", "zc.metadatos:titulo", "zc.metadatos:duracion"],
                "anchos": {}, "orden": "nombre", "inverso": false, "vista": "completa", "filtro": "",
                "lectura": ["nombre", "zc.metadatos:titulo", "zc.metadatos:duracion"]}],
 "reglas": [{"tipo": "ruta", "patron": "D:\\Música\\**", "conjunto": "Música"},
            {"tipo": "contenido", "extensiones": ["mp3", "flac", "m4a"], "proporcion": 0.6, "conjunto": "Música"}],
 "recordadas": {"D:\\Fotos": {"orden": "fecha", "inverso": true, "vista": "completa"}}}
```

- Al entrar en una carpeta (si `vista.columnas_por_carpeta`): la primera regla que coincide (las de ruta antes que las de contenido; la de contenido se evalúa con la lista ya leída) aplica su conjunto a la pestaña. Al salir a una carpeta sin regla, se vuelve a las columnas de la pestaña. Se anuncia el conjunto aplicado solo con detalle («Vista Música»).
- Con `vista.recordar_vista_por_carpeta`, el orden, la vista y el filtro que la persona cambie en una carpeta se recuerdan en `recordadas` (como mucho 500 carpetas, las más recientes) y se aplican al volver.
- El panel aplica un conjunto con `PanelArchivos.aplicar_conjunto(conjunto: ConjuntoVista | None)` (enganche de N2, 19.1). `ConjuntoVista` es un dataclass sin wx que N2 define en `app/services/vistas_modelo.py` con los campos del JSON de arriba (`nombre`, `columnas`, `anchos`, `orden`, `inverso`, `vista`, `filtro`, `lectura`); PE lo usa en `vistas_carpeta.py`.
- Columnas disponibles: las de la 1.x más las de los complementos activos (`<id>:<columna>`).
- Diálogo (`pe_vistas.py`, orden `columnas_carpeta`, por lado): «Conjunto para esta carpeta:», lista de conjuntos con «&Nuevo», «&Editar» (el diálogo de columnas de la 1.x más «Orden de lectura»), «&Eliminar», y reglas con «&Aplicar a esta carpeta y sus subcarpetas», «Aplicar a carpetas con mayoría de...».

### 10.5 Orden de lectura de las columnas

- Cada conjunto (y las columnas de la pestaña) tiene `lectura`: qué columnas y en qué orden se leen con Izquierda y Derecha y con Ctrl+1 a Ctrl+0 (1.x §6.4), y en qué orden se colocan en la lista (lo que el lector lee al moverse por las filas). Las columnas que no están en `lectura` se ven pero van al final.
- Con el complemento de NVDA de zCommander (10.16) se puede ir más allá: «Leer al moverse solo estas columnas». zCommander publica el orden en la propiedad de ventana `zCommander.OrdenLectura` de la lista (un entero de 64 bits con un índice de columna de 4 bits por posición, terminado en `0xF`; con `senales_nvda.publicar_orden_lectura`, 10.16) y el complemento de NVDA compone la fila con esas columnas. Como las columnas de `lectura` se colocan las primeras en la lista, sus índices van de 0 a 14: `lectura` admite **15 columnas como máximo** (15 posiciones de 4 bits más el terminador ocupan los 64 bits, y el índice 15 es el propio terminador); el diálogo no deja marcar una decimosexta y lo dice («Como mucho 15 columnas se leen al moverse»). Sin el complemento, NVDA lee todas en el orden de la lista.
- **Dónde se guarda**: en cada conjunto, su campo `lectura` (10.4); en cada pestaña, el campo nuevo `lectura` de esa pestaña en `sesion.json` (lista de ids de columna; vacía = el orden de sus columnas); y para las columnas por defecto, la clave nueva del núcleo `paneles.lectura` (lista, `[]` de fábrica = el orden de las columnas por defecto; 14.3).
- **Cómo se aplica**: con el enganche de N2 `PanelArchivos.aplicar_lectura(lectura: list[str]) -> None`, que coloca esas columnas primero en la lista, en ese orden, deja las demás al final y llama a `senales_nvda.publicar_orden_lectura` (10.16). El panel lo llama al abrir una pestaña, al aplicar un conjunto (`aplicar_conjunto` usa su `lectura`) y cuando cambia la preferencia.
- Diálogo `pe_orden_lectura.py` (orden `orden_lectura`): lista de columnas con casillas (se leen o no) y «&Subir» y «&Bajar»; «Aplicar &a:» con «Esta pestaña», «Este conjunto» (si hay uno aplicado) o «Las columnas por defecto».

### 10.6 Menús, barra de botones y barra de teclas configurables

- `data/config/menus.json`:

```json
{"version": 1,
 "ocultas": ["sin_ordenar", "ordenar_tipo"],
 "mis_ordenes": ["macro:Fotos a la copia", "-", "zc.reproductor:reproducir", "favoritos"],
 "barra_botones": ["copiar", "mover", "eliminar", "-", "zc.nubes:cuentas"],
 "barra_teclas": {"Shift+F7": "zc.duplicados:buscar"}}
```

- **Ocultar** elementos de los menús de fábrica (no se pueden reordenar, para que manual y menús sigan iguales para todo el mundo); las órdenes ocultas siguen con su tecla y en la paleta.
- **«Mis ó&rdenes»**: menú propio de la barra (Alt+R) que aparece cuando tiene elementos: órdenes, macros, órdenes de complementos y separadores, en el orden que elija la persona.
- **Barra de botones**: barra nativa (`wx.ToolBar` con botones de texto) bajo los paneles, visible con `vista.barra_botones_visible` (orden casilla `barra_botones`). Cada botón tiene el nombre de su orden y su tecla en la ayuda. Está fuera del orden de tabulación (Tab cambia de panel); se entra con `ir_barra_botones` (Alt+Mayús+F11, como Total Commander 10): Izquierda y Derecha recorren los botones, Intro o Espacio ejecutan, Escape vuelve al panel. Suena `barra_botones.entrar`.
- **Barra de teclas F** (1.x §4.1): cada hueco (tecla con o sin Mayús, Ctrl o Alt) puede llevar otra orden; la etiqueta corta se calcula de la orden o la escribe la persona.
- La barra se coloca con el enganche de N2 `VentanaPrincipal.colocar_barra_botones(barra: wx.Window | None) -> None` (la pone bajo los paneles, fuera del orden de tabulación, o la quita).
- Diálogo `pe_menus.py` (orden `personalizar_menus`), con cuatro pestañas: «Menús» (árbol de menús con casillas para mostrar u ocultar), «Mis órdenes» y «Barra de botones» (listas con «&Añadir...» con el buscador de la paleta, «&Separador», «&Subir», «&Bajar», «&Quitar») y «Barra de teclas» (lista de huecos con «&Cambiar...»). «Restablecer» por pestaña.

### 10.7 Esquemas de teclas

- `teclado.esquema`: `norton` (por defecto, la 1.x), `total_commander`, `far` o `explorador`. El `MapaTeclas` se construye así: teclas de fábrica del catálogo, después los cambios del esquema, después `teclado.personalizadas`. Una tecla de esquema que choca con la de un complemento deja al complemento sin esa tecla y el gestor lo dice.
- Los esquemas son datos (`app/services/esquemas_teclas.py`, `ESQUEMAS: dict[str, dict[str, tuple[str, ...]]]`, solo las diferencias con `norton`, con ids de orden y teclas en formato canónico). **N2 crea ese archivo** con exactamente las diferencias de abajo, para que la prueba de choques de N2 (14.1.3) tenga contra qué pasar desde el principio; después es de PE, que al contrastarlas con la ayuda oficial de cada programa (21.2.5) puede cambiarlas, pero vuelve a pasar `tests/ui/test_n2_teclas.py` en su definición de terminado. Las teclas F de Norton (F3 a F8, F10) no cambian en ningún esquema. Diferencias (el anexo de órdenes publica la lista exacta; la prueba de choques de 1.2 se pasa con cada esquema):
  - **Total Commander**: Ctrl+S filtro rápido (búsqueda rápida queda sin tecla: se busca tecleando); Ctrl+L calcular el tamaño de las carpetas de trabajo (Información queda sin tecla); Ctrl+F10 quitar el filtro; Mayús+F2 comparar carpetas (Ir a la línea de órdenes queda sin tecla: se llega tecleando); Ctrl+F conexiones FTP y SFTP (además de Ctrl+K).
  - **Far**: Ctrl+T vista Árbol en el lado pasivo (pestaña nueva queda sin tecla); Ctrl+I filtro (además de Ctrl+F12); Mayús+F1 comprimir (la lista de teclas sigue en el menú Ayuda); Mayús+F2 extraer (Ir a la línea de órdenes queda sin tecla).
  - **Explorador**: F2 renombrar en el sitio (menú de usuario queda sin tecla; sigue en Archivos); Ctrl+Mayús+N crear carpeta (invertir las marcas conserva Num * y queda en el menú); Ctrl+L Ir a la carpeta (Información queda sin tecla).
- Una orden que pierde su tecla por un esquema se anuncia en la vista previa del diálogo («Búsqueda rápida: queda sin tecla») y sigue en menús y paleta.
- Diálogo `pe_esquema.py` (orden `esquema_teclas`): lista de esquemas con su descripción y la lista de diferencias que aplicaría (Orden, Tecla actual, Tecla del esquema); «&Aplicar» pide confirmación y dice cuántas teclas cambian; las personalizadas se conservan. El mapa de teclas (1.x §8.26, orden `mapa_teclas` de la 1.x) gana «E&xportar...» e «&Importar...» (`.zcteclas`: JSON `{"version": 1, "esquema": "...", "personalizadas": {...}}`); Intro sobre un `.zcteclas` abre el mapa de teclas con la importación (14.9).

### 10.8 Alias y órdenes internas de la línea de órdenes

- `data/config/alias.json`: `{"version": 1, "alias": [{"nombre": "ll", "orden": "dir /a %1"}, {"nombre": "fotos", "orden": "zc ir_a_carpeta D:\\Fotos"}]}`. `%1` a `%9` y `%*` son los argumentos escritos tras el alias; las variables de 1.x §8.17 (`%P`, `%M`...) valen igual y con la misma protección contra inyección (1.x §14).
- **Órdenes internas**: `zc <id de orden> [argumento]` ejecuta una orden del catálogo (con argumento si lo admite, 10.1) sin lanzar ningún proceso; `zc macro <nombre>` ejecuta una macro; `zc <nombre> [argumentos]` ejecuta una orden interna de un complemento (`[[internas]]` y `zc.ordenes.interna`, 3.7; por ejemplo `zc git status`), en un hilo y con su salida en «Salida de órdenes»; `zc ayuda` lista las órdenes internas en la salida. N2 deja en `app/services/linea_ordenes.py` el reconocimiento de `zc` (órdenes del catálogo y de complementos); los alias y el autocompletar son de PE, que es el dueño posterior de ese archivo.
- **Autocompletar** (`linea_autocompletar`, Ctrl+Espacio en la línea de órdenes, si `linea.autocompletar`): completa rutas del panel activo, alias y nombres de orden tras `zc `; con varias opciones, la primera pulsación completa lo común y anuncia «3 opciones»; la segunda abre una lista para elegir. Tab sigue volviendo al panel (1.x §6.2).
- Diálogo `pe_alias.py` (orden `alias`): lista con «&Nuevo», «&Editar», «E&liminar» y «&Probar» (muestra la orden expandida sin ejecutarla).

### 10.9 Espacios de trabajo

- Un espacio de trabajo guarda la disposición completa: pestañas de cada lado con su carpeta, vista, orden, filtro, columnas y bloqueo; lado activo; lados visibles; orientación de los paneles; salida de órdenes visible; barra de botones visible; y, opcional, la cesta. `data/config/espacios.json`: `{"version": 1, "espacios": [{"nombre": "Proyecto web", "nota": "", "disposicion": {...mismo formato que sesion.json...}, "con_cesta": false}]}`.
- Orden `espacios_trabajo` (Ctrl+Mayús+W): lista de espacios con «&Abrir» (Intro), «&Guardar el actual como...» (también la orden `espacio_guardar`), «&Sustituir con el actual», «&Renombrar», «E&liminar». Abrir un espacio guarda antes la sesión actual como espacio «Anterior» (para volver). Suena `espacio.abierto` y se anuncia «Espacio de trabajo Proyecto web».
- El complemento «Proyectos y salto rápido» (11.15) usa estos espacios y añade la nota y el salto por frecuencia.

### 10.10 Reglas de anuncio, color y sonido

- `data/config/reglas.json`: lista ordenada de reglas `{"nombre": "Grandes", "activa": true, "condicion": {...}, "efectos": {...}}`.
  - Condición (todas las partes que se pongan se tienen que cumplir): `patron` (como 1.x §5.3), `tamano_min` y `tamano_max` (bytes), `modificado_hace_menos_de` y `modificado_hace_mas_de` (días), `atributos` (`solo_lectura`, `oculto`, `sistema`, `comprimido_ntfs`, `cifrado_ntfs`, `enlace`, `en_nube`), `es_carpeta`.
  - Efectos: `color` (uno de seis colores del tema actual con nombre: «Rojo», «Verde», «Azul», «Ámbar», «Morado», «Gris»), `texto` (palabra corta que se muestra en la columna nueva «Regla» y se lee con Ctrl+número o, si la persona la coloca primera, al moverse), `sonido` (`regla.a`, `regla.b` o `regla.c`, suena al llegar el cursor) y `anuncio` (frase que se dice tras lo que lee el lector, con el retardo de anuncios y nivel detalle).
- La primera regla activa que coincide decide los efectos de cada elemento (sin mezclar). Se evalúan al formatear la fila (con caché por entrada), sin E/S extra.
- **Nada solo con color**: una regla con `color` y sin `texto` ni `sonido` ni `anuncio` se guarda, pero el editor avisa «Este efecto solo se ve».
- Diálogo `pe_reglas.py` (orden `reglas`): lista con «&Nueva», «&Editar», «&Subir», «&Bajar», «E&liminar» y «&Probar con el elemento del cursor» (dice qué regla se aplicaría). `reglas.activas` las enciende o apaga todas.

### 10.11 Menús según el nivel del perfil

- Cada orden del catálogo gana `nivel` (`novato`, `intermedio`, `avanzado`); el bloque N2 los asigna a las 181 de la 1.x (criterio: las de 1.x §8.1 a §8.8 y las de consulta, novato; las de búsqueda, comparación, comprimidos y red, intermedio; enlaces, atributos, sumas, dividir y unir, menú de Windows, avanzado). Las de complementos lo traen en el manifiesto.
- Con `vista.menus_por_nivel` activa, los menús muestran solo las órdenes de nivel menor o igual al del perfil actual (Personalizado cuenta como avanzado); al final de cada menú, la casilla «&Mostrar todas las órdenes» (orden `todas_las_ordenes`) los muestra todos. Las teclas y la paleta no cambian. El perfil Novato la activa (1.x §2.2 gana esta fila).

### 10.12 Confirmaciones una a una

- Las confirmaciones que no son de seguridad ganan la casilla «No volver a preguntar». La lista es cerrada y vive en `app/services/confirmaciones.py` (N2, sin wx): `CONFIRMACIONES: dict[str, Confirmacion]` con `Confirmacion(etiqueta, ayuda)`, `debe_preguntar(config, id) -> bool` (falso si están silenciados el id completo **o su prefijo antes de «:»**: silenciar `ftp_sin_cifrar` vale para todos los sitios, como hacía `ftp.avisar_sin_cifrar`; un id que no es de la lista se pregunta siempre) y `silenciar(config, id) -> None`. Ids: `comprimido_escritura` (aviso de escritura en comprimidos), `ftp_sin_cifrar` (aviso de FTP sin cifrar; por sitio se guarda `ftp_sin_cifrar:<id del sitio>`), `marcas_cursor` (pregunta de marcas y cursor, 1.x §5.4), `esquema_cambio` (avisos de cambio de esquema), `copia_sin_secretos` (crear una copia sin contraseñas) y `complemento_autor_confiado` (instalar un complemento de un autor ya confiado). Las silenciadas se guardan en `general.no_preguntar`. Los complementos no añaden confirmaciones silenciables en la API 1.0.
- La migración 1 → 2 (14.3) pasa a esta lista las dos claves de la 1.x que hacían este papel: `ftp.avisar_sin_cifrar` falso añade `ftp_sin_cifrar`, y `operaciones.aviso_comprimido_mostrado` verdadero añade `comprimido_escritura`; las dos claves se borran.
- **Quién las usa** (enganches de N2 en la 1.x, 19.1): `app/services/vfs/ftp.py` (`_avisar_sin_cifrar`, que hoy lee `ftp.avisar_sin_cifrar`) pregunta con `debe_preguntar(config, f"ftp_sin_cifrar:{id del sitio}")` y, en una conexión sin sitio guardado (Ctrl+G con una dirección), con `ftp_sin_cifrar:<servidor>`; la pregunta, desde el hilo del proveedor, es `Decisor.elegir_con_casilla(titulo, texto, opciones, casilla, predeterminada=0, escape=-1, operacion=None) -> tuple[int, bool]` (método nuevo del protocolo de 14.6: índice elegido y si se marcó «No volver a preguntar»), que implementan `GestorDecisiones` (con `dialogos.elegir_con_casilla(padre, mensaje, titulo, opciones, casilla=CASILLA_NO_PREGUNTAR) -> tuple[int | None, bool]`, versión de `app/ui/accesibilidad/dialogos.py` sobre `DialogoMensaje` con casilla) y `api.pruebas.DecisorFalso` (devuelve la respuesta encolada, `(0, False)` por defecto); `app/ui/acciones/archivos.py` (aviso de escritura en comprimidos, que hoy lee y escribe `operaciones.aviso_comprimido_mostrado`) usa `comprimido_escritura`; la pregunta de marcas y cursor (`acciones/archivos.py` y `panel_archivos.py`, 1.x §5.4) gana la casilla con `marcas_cursor`. Las demás las ponen sus bloques (PE `esquema_cambio`, CS `copia_sin_secretos`, PL `complemento_autor_confiado`).
- **Nunca** se pueden silenciar: eliminar definitivamente, vaciar papeleras, sobrescribir una copia de seguridad, restaurar, apagar o reiniciar el NAS, desactivar el modo solo lectura del NAS, instalar un complemento sin firma, ejecutar `.ps1`, `.vbs` y `.js`.
- Página de Preferencias «Confirmaciones» (propia): lista con casillas de todas las confirmaciones silenciables; desmarcada quiere decir «no se pregunta»; «Volver a preguntar &todas».

### 10.13 Plantillas de archivo nuevo

- Mayús+F4 (1.x §8.8) gana «&Plantilla:» (desplegable): «Archivo vacío» y las plantillas de `data/docs/plantillas/` (de serie: texto con fecha, Markdown con título, HTML básico, CSV con cabecera, `.bat` con `@echo off`) y de `data/plantillas/` (de la persona). El archivo nuevo toma la extensión de la plantilla si el nombre no tiene; dentro de la plantilla se sustituyen `{{fecha}}`, `{{hora}}`, `{{nombre}}` y `{{usuario}}`.
- Orden `plantillas_archivo`: abre `data/plantillas/` en un panel (y la crea con una copia de las de serie si no existe).

### 10.14 Paleta con favoritas y frecuentes, y búsqueda en Preferencias

- La paleta (1.x §6.5) muestra primero las favoritas y después las 10 más usadas, cada una con su tecla. Dentro de la paleta, Ctrl+D marca o desmarca la orden elegida como favorita. Datos en `data/config/paleta.json` (`{"version": 1, "favoritas": [...], "usos": {"id": número}}`): el servicio de la paleta cuenta los usos en memoria con el evento del bus `al_terminar_orden` y guarda el archivo de forma diferida (5 s después del último cambio y al cerrar), no en cada orden.
- Preferencias gana el campo «&Buscar una opción:» arriba: al escribir, una lista muestra las preferencias cuyo nombre o ayuda contienen el texto (también las de complementos), con su página; Intro lleva a la página y pone el foco en el control.

### 10.15 Teclas globales

- Teclas que funcionan con zCommander en segundo plano, con `RegisterHotKey` sobre la ventana principal (`wx.Window.RegisterHotKey` y `EVT_HOTKEY`), por los enganches de N2 `VentanaPrincipal.registrar_tecla_global(id_orden: str, tecla: str) -> bool` (falso si Windows la rechaza) y `liberar_teclas_globales() -> None`. Solo si `teclado.globales_activas` está activa (desactivada por defecto) y solo para órdenes de una lista blanca: `traer_al_frente` (pseudoorden: restaura y activa la ventana), `ir_a_carpeta` (trae al frente y lo abre), `decir_operaciones`, `sonidos_silenciar`, `macro:*` y las órdenes de complementos con `tecla_global = true` (por ejemplo, pausar el reproductor).
- `teclado.globales`: `{"id_orden": "Ctrl+Alt+Mayús+Z"}`; no hay ninguna de fábrica. Se aconsejan combinaciones con Ctrl+Alt+Mayús o con Win+Alt (las de Win solas son de Windows). Si `RegisterHotKey` falla (la usa otro programa), se avisa con el nombre de la tecla y se deja sin registrar.
- Página «Personalización» de Preferencias: «Teclas &globales...» (botón de `BOTONES_PAGINA`, 10.18) abre una lista (`app/ui/dialogos/pe_teclas_globales.py`; Orden, Tecla global) con «&Cambiar...» (captura la tecla), «&Quitar». Suena `tecla_global.recibida` al recibirla si está activo.

### 10.16 Complemento de NVDA de zCommander

- Plantillas del agente `complemento-nvda`, adaptadas: `nvda_addon/manifest.ini` (`name = zCommander`, versión igual a la de zCommander, `minimumNVDAVersion = 2026.1`, `lastTestedNVDAVersion` = la última probada de verdad), `nvda_addon/addon/appModules/zcommander.py` (el ejecutable `ZCommander.exe`), traducción en `locale/es`, documentación en `doc/es/readme.md`, `tools/construir_complemento.py` que genera `data/bin/nvda/zCommander-<versión>.nvda-addon`.
- Funciones:
  1. **Lectura completa de celdas largas**: NVDA corta a 511 caracteres cada celda de un `SysListView32`; el appModule lee el texto completo (búfer de 16 384) en las listas de zCommander (la columna Ruta de las listas de resultados, nombres largos).
  2. **Movimiento silencioso**: cuando zCommander mueve el foco por su cuenta (tras volver a leer, al restaurar marcas, al aplicar un filtro, al volver de un diálogo al mismo elemento), marca antes la propiedad de ventana `zCommander.MovimientoSilencioso` con la hora; el appModule no anuncia ese foco si la marca tiene menos de 500 ms. Se activa con `accesibilidad.silencio_nvda`. `app/ui/senales_nvda.py` es de N2 (pequeño y completo desde N2: `marcar_movimiento_silencioso(hwnd: int) -> None` y `publicar_orden_lectura(hwnd: int, indices: Sequence[int]) -> None`, con la codificación de 10.5), y N2 pone las llamadas en los sitios donde zCommander mueve el foco por su cuenta (`lista_archivos.py`, `panel_archivos.py`); NV hace el appModule que las lee y PE solo las usa desde sus diálogos.
  3. **Orden de lectura** de 10.5 (propiedad `zCommander.OrdenLectura`).
  4. Gesto **NVDA+Mayús+J**: lee la fila completa con todas las columnas y sus cabeceras (reasignable en «Gestos de entrada» de NVDA).
- Instalación: Preferencias → Accesibilidad, botón «Instalar el complemento de zCommander para &NVDA...», y la orden `complemento_nvda` (Ayuda). Explica qué hace, pide confirmación y abre el `.nvda-addon` con `os.startfile` (NVDA pide su propia confirmación y se reinicia). Nunca se copia nada a la carpeta de NVDA. Si NVDA está activo y el complemento no está instalado, el asistente de primer arranque y la primera vez tras actualizar a la 2.0 lo ofrecen una vez (`accesibilidad.complemento_nvda_ofrecido`).
- zCommander funciona igual sin el complemento: cada función tiene su comportamiento sin él.

### 10.17 Arrancar con Windows

`general.arrancar_con_windows` (página General): solo en la versión compilada. Al activarla se escribe el valor `zCommander` en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` con `"<ruta del exe>" --al-iniciar-sesion`; al desactivarla, se borra. Es la única escritura de zCommander en el Registro de Windows y solo por petición expresa; las demás cosas que la 2.0 deja fuera de `data/` también a petición de la persona están en la lista de excepciones al principio 3 de 1.x §3 (sección 16). Al arrancar, si el valor existe y apunta a otra carpeta (la portable se movió), se pregunta si se corrige. `--al-iniciar-sesion` arranca minimizado y sin anuncios hasta que la ventana recibe el foco.

### 10.18 Diálogo de Preferencias 2.0

- Pasa de `wx.Notebook` a `wx.Treebook` (árbol nativo y páginas): General, Paneles, Vista, Accesibilidad, Sonidos, Operaciones, Visor y editor, Búsqueda, Red, Comprimidos, Actualizaciones, Personalización, Confirmaciones y el nodo Complementos con una página por complemento con configuración. Con el foco en el árbol, las flechas cambian de página; Ctrl+Tab y Ctrl+Mayús+Tab también desde los controles.
- Las páginas declarativas salen de `DESCRIPCIONES` (1.x) y de los manifiestos (`app.plugins.config_plugins`); el diálogo (`f_preferencias.py`, PE) las construye todas, también las de complementos, sin activar ninguno. Las propias se registran en `app/ui/paginas_propias.py` (archivo de N2, el único registro). **N2 deja los diccionarios ya rellenos con referencias perezosas en texto** (`"módulo:función"`, que el diálogo importa al abrir la página) y crea cada módulo de destino como provisional (una página que dice «Esta página aún no está disponible»); así ningún bloque edita `paginas_propias.py`, solo su módulo:
  - `PAGINAS_PROPIAS: dict[str, str]`, de título de página a referencia de una fábrica `crear(padre: wx.Window, config: Configuracion) -> PaginaPropia`: `"Sonidos": "app.ui.dialogos.so_pagina_sonidos:crear"` (SO) y `"Confirmaciones": "app.ui.dialogos.pe_confirmaciones:crear"` (PE).
  - `PaginaPropia` (protocolo, un `wx.Panel`): `validar() -> str | None` (texto del error, o nada), `aplicar() -> bool` (escribe en la configuración; falso si no pudo), `restablecer() -> None` («Valores de fábrica de esta página») y `control_inicial() -> wx.Window` (dónde se pone el foco al llegar). Aceptar y Aplicar llaman a `validar` y `aplicar` de cada página cambiada; Cancelar no llama a nada (las páginas no escriben hasta `aplicar`).
  - `BOTONES_PAGINA: dict[str, list[tuple[str, str]]]`, de título de página a pares (etiqueta, referencia de una función `(padre: wx.Window) -> None`): botones que se añaden al final de una página declarativa sin convertirla en propia: `"Accesibilidad": [("Instalar el complemento de zCommander para &NVDA...", "app.ui.instalar_complemento:abrir")]` (NV) y `"Personalización": [("Teclas &globales...", "app.ui.dialogos.pe_teclas_globales:abrir")]` (PE). Sus letras cuentan en `revisar_teclado` de la página.
  - **Diálogos propios de complementos**: no son páginas propias. Cada página de complemento es declarativa (sus `[[configuracion]]`) y, si el manifiesto dice `dialogo_preferencias = true`, lleva al final el botón «Abrir la configuración &avanzada...» (3.6). La función se registra en tiempo de ejecución con `registrar_dialogo_complemento(id: str, funcion: Callable[[wx.Window], None]) -> None` (la llama la API cuando el complemento usa `zc.preferencias.dialogo`); el botón pide la activación y llama a la función registrada. `abrir_preferencias(id: str) -> None` abre Preferencias en la página de ese complemento (`zc.preferencias.abrir`) llamando a `app.ui.dialogos.f_preferencias.abrir(padre: wx.Window, config: Configuracion, pagina: str | None = None) -> None`, punto de entrada del diálogo que N2 añade a `f_preferencias.py` (archivo de la 1.x; dueño posterior PE) como provisional: abre el diálogo de la 1.x (`mostrar`) y, si se pide una página, anuncia «Página no disponible»; PE lo completa con el `Treebook` (`pagina` es el título de una página o `complemento:<id>`).
- Aceptar, Cancelar, Aplicar y «Valores de &fábrica de esta página» como en la 1.x; el campo de búsqueda de 10.14 arriba de todo.

## 11. Los 25 complementos de serie generales

Con «Nubes» (12) y «NAS Synology» (13) forman los 27 complementos de serie.

### 11.0 Reglas comunes

- Lista y orden: los de plugins.md sección 4, salvo que el «6. Más comprimidos con 7-Zip» se sustituye por el **Conversor multimedia con FFmpeg** (los comprimidos ya están en el núcleo, sección 8) y el «10. Nube y WebDAV» por el **Editor hexadecimal accesible** (la nube es el complemento aparte de la sección 12).
- Viven en `plugins/<carpeta>/` con `id = "zc.<carpeta>"`, licencia GPL-3.0-or-later, sin firma (son de confianza por estar en la carpeta del programa, 3.2; sus actualizaciones sueltas en `data/plugins/` sí van firmadas, 3.9 y 5.6), `api_minima = api_probada = "1.0"`, ayuda en `doc/es/leeme.md` y novedades en `doc/es/cambios.md`.
- Todos en español, con anuncios por niveles, preguntas por el `Decisor`, trabajo largo como operación del motor (progreso, pausa, cola, F12) y ventanas que pasan `revisar_teclado`.
- Sus órdenes van en el menú «Co&mplementos», en un submenú por complemento, salvo que la ficha diga otro ancla. «Tecla» es la de fábrica, comprobada contra la 1.x y contra las demás fichas (14.1.3); «—» es sin tecla.
- Sus claves de configuración son `plugin.<id>.<clave>`; en las fichas se escriben solo con la clave corta, con tipo y valor de fábrica, en su página «Complementos > <nombre>».
- «Pruebas mínimas» son las del bloque que lo programa (sección 18), en `tests/plugins/<carpeta>/`.
- Ningún complemento de serie se carga al arrancar salvo los que lo dicen (`al_arrancar`, fijo en su manifiesto): Portapapeles, Monitor, Programador, Proyectos y Nubes, y los que tienen columnas visibles por defecto (ninguno). `activacion` es estática: Monitor y Nubes la declaran siempre y su `activar()` vuelve enseguida sin hacer nada si no hace falta (Monitor sin carpetas vigiladas; Nubes con `arrancar = al_usar`). Los cinco entran en el presupuesto de 100 ms del objetivo 5 de 1.2.
- **Funciones que unos complementos de serie usan de otros** (siempre con `zc.complemento(id)`, que activa el otro si hace falta y devuelve `None` si no está: quien llama tiene que funcionar sin él; desde el hilo de la interfaz, con `zc.complemento_futuro(id)`, porque allí `complemento` nunca espera, 3.4). Cada complemento las ofrece con `zc.exportar` en su `activar()`; las firmas son parte de su contrato y su bloque las prueba:

| Complemento | Exporta | Lo usan |
|---|---|---|
| `zc.metadatos` | `leer_etiquetas(proveedor: Proveedor, ruta: str) -> dict[str, str]` (claves `artista`, `titulo`, `album`, `pista`, `anio`, `genero`, `duracion_s`) | Reproductor (11.1), Duplicados (11.7) |
| `zc.ocr` | `reconocer(proveedor: Proveedor, ruta: str, cancelacion) -> Documento` | Documentos (11.2), Imágenes (11.11) |
| `zc.documentos` | `convertir(proveedor: Proveedor, ruta: str, cancelacion) -> Documento` | Lectura en voz (11.17) |
| `zc.notas` | `etiquetar(ruta: str, etiqueta: str) -> None` | Monitor (11.18) |
| `zc.sincronizacion` | `operacion_de_tarea(nombre: str) -> Operacion` | Programador (11.24) |
| `zc.monitor` | `operacion_de_reglas(carpeta: str) -> Operacion` | Programador (11.24) |
| `zc.programador` | `ejecutar_tarea(id: str, al_terminar: Callable[[int], None]) -> None` [interfaz]: lanza la tarea en esta instancia (su operación con `zc.lanzar` o su macro y sus órdenes con `zc.ejecutar_orden_futuro`, esperando el futuro de cada una, 3.4) y llama a `al_terminar` con el código de salida (0 bien, 1 con errores, 2 no se pudo empezar) | `cargador.ejecutar_tarea_programada` (orden `tarea` de la instancia única, 11.24 y 14.8) |

  Las máscaras de renombrado de otros complementos se usan con `zc.renombrado.evaluar` (3.7), no con funciones exportadas; los espacios de trabajo, con `zc.espacios`.

### 11.1 Reproductor multimedia (`zc.reproductor`, bloque P1)

- **Qué hace**: reproduce audio (y el sonido de los vídeos) del cursor, de los marcados o de una carpeta mientras se sigue navegando; recuerda dónde se dejó cada archivo largo.
- **Motor**: `wx.media.MediaCtrl` (motor de Windows y sus códecs). Si un formato no se puede abrir con él y está el componente `ffmpeg`, se usa `ffplay.exe -nodisp -autoexit -loglevel error` como proceso aparte (Job Object) para reproducirlo, con avance y retroceso reiniciando en la posición (`-ss`). `ffprobe` da duración y etiquetas cuando `MediaCtrl` no las sabe.
- **Funciones**: reproducir, pausa, detener; avanzar y retroceder (corto, medio y largo); ir a un porcentaje o a un tiempo («1:23:00»); siguiente y anterior; volumen; velocidad (0,5x a 3x si el motor lo admite; con ffplay no); repetir uno o todos; aleatorio; **decir posición y duración** bajo demanda («12:30 de 45:10, 27 %»), nunca solo; **continuar donde se dejó** (archivos de más de `recordar_desde_min` minutos); marcadores con nombre; listas M3U y M3U8 (abrir y guardar); temporizador de apagado; anuncio del título al cambiar de pista (con las etiquetas de `zc.metadatos` si está).
- **Ventana del reproductor** (no modal, `VentanaComplemento`): lista nativa de la cola (Número, Título, Duración), texto de estado de solo lectura y botones. Teclas propias de la ventana: Espacio pausa, Izquierda y Derecha salto corto, Ctrl+Izquierda y Ctrl+Derecha salto medio, Re Pág y Av Pág salto largo, Más (+) y Menos (-) volumen, Ctrl+Más y Ctrl+Menos velocidad (Arriba y Abajo son de la lista de la cola), P posición, G ir a tiempo, M marcador, Ctrl+M lista de marcadores, R repetir, A aleatorio, Escape cierra la ventana (la reproducción sigue).
- **Órdenes**:

| id | Etiqueta | Tecla | Ámbito |
|---|---|---|---|
| `zc.reproductor:reproducir` | &Reproducir | Ctrl+Mayús+F5 | global |
| `zc.reproductor:ventana` | &Mostrar el reproductor | Alt+Mayús+F2 | global |
| `zc.reproductor:pausa` | &Pausa o continuar | Alt+Mayús+F5 | global (tecla global posible) |
| `zc.reproductor:detener` | &Detener | Alt+Mayús+F6 | global (tecla global posible) |
| `zc.reproductor:retroceder` | Re&troceder | Alt+Mayús+F7 | global |
| `zc.reproductor:avanzar` | &Avanzar | Alt+Mayús+F8 | global |
| `zc.reproductor:posicion` | Decir la p&osición | Alt+Mayús+F3 | global |
| `zc.reproductor:siguiente` | &Siguiente pista | — | global |
| `zc.reproductor:anterior` | Pista a&nterior | — | global |
| `zc.reproductor:anadir_cola` | Añadir a la &cola | — | panel |
| `zc.reproductor:guardar_lista` | &Guardar la cola como M3U... | — | global |
| `zc.reproductor:temporizador` | &Temporizador de apagado... | — | global |

- **Configuración**: `salto_corto_s` (entero, 5), `salto_medio_s` (30), `salto_largo_s` (300), `volumen` (entero 0–100, 80), `velocidad` (decimal 0,5–3, 1,0), `recordar_posicion` (bool, sí), `recordar_desde_min` (entero, 10), `anunciar_pista` (bool, sí), `usar_ffplay` (bool, sí), `formatos_intro` (texto, vacío: no se asocia a Intro; por ejemplo `*.mp3;*.m4b`), `posiciones` (diccionario interno: ruta → segundos, guardado en `datos/posiciones.json` por tamaño). Asociación «Abrir» opcional con `zc:zc.reproductor:reproducir`.
- **Sonidos**: `zc.reproductor:pista` (cambio de pista), `zc.reproductor:fin_lista` (termina la cola), `zc.reproductor:marcador` (marcador guardado).
- **Dependencias**: `wx.media` (wxPython); componente `ffmpeg` recomendado (`[recomienda]`). Permisos `sonido`, `segundo_plano`, `ejecutar_programas`.
- **Pruebas mínimas**: formato de tiempos («1:23:00» ↔ 4980 s); posición recordada y restaurada para un archivo de más de 10 min; lista M3U con rutas relativas y UTF-8 leída y escrita; la ventana pasa `revisar_teclado`; con un `MediaCtrl` falso, pausa, salto y velocidad cambian el estado esperado; sin `ffmpeg`, la orden con un formato no admitido avisa «Este formato necesita el componente FFmpeg».

### 11.2 Lector de documentos (`zc.documentos`, P2)

- **Qué hace**: convierte PDF, DOCX, ODT, EPUB, RTF, HTML y FB2 en un `Documento` con secciones que se lee en el visor interno (F3) y en la Vista rápida.
- **Funciones**: secciones por encabezado (el visor da F6 y Mayús+F6 para sección siguiente y anterior, y Ctrl+L para la lista de secciones, 14.7); páginas de PDF («Página 12 de 80»; Ctrl+P ir a página en el visor); metadatos (título, autor, páginas, fecha) en Ctrl+Mayús+I y como columnas; «PDF sin texto: probablemente escaneado» con la oferta de reconocerlo (si está `zc.ocr`); guardar como TXT o Markdown (uno o los marcados, como operación); extractor de texto para Buscar archivos; tablas como texto lineal («Tabla de 3 columnas. Fila 1: ...»); notas al pie al final de su sección.
- **Órdenes**: `zc.documentos:convertir` «&Convertir a texto...» (—, global); `zc.documentos:propiedades` «&Propiedades del documento» (—, panel).
- **Columnas**: `paginas` (Páginas), `titulo` (Título), `autor` (Autor); lentas.
- **Configuración**: `formatos` (lista, todos), `tamano_maximo_mb` (entero, 100), `marcas_pagina` (bool, sí), `texto_alternativo` (bool, sí), `formato_salida` (opción `txt` o `md`, `txt`), `codificacion_salida` (opción `utf-8` o `utf-8-sig`, `utf-8`).
- **Dependencias**: pypdf vendorizado (`lib/`); DOCX, ODT, EPUB y FB2 con `zipfile` y `xml.etree`; HTML con `html.parser`; RTF con un analizador propio pequeño. `.doc` antiguo con Word por COM si está instalado (si no, «Para .doc hace falta Microsoft Word»).
- **Pruebas mínimas**: un DOCX generado en la prueba con dos encabezados da dos secciones con su nivel; un PDF de dos páginas generado con pypdf da «Página 2 de 2»; un EPUB con dos capítulos da dos secciones en orden; un PDF sin texto da el aviso; el extractor encuentra «hola» dentro de un DOCX en Buscar archivos; un nombre de miembro malicioso en un EPUB no sale de la carpeta temporal.

### 11.3 Reconocimiento de texto, OCR (`zc.ocr`, P2)

- **Qué hace**: reconoce el texto de imágenes y PDF escaneados con el motor OCR de Windows, sin Internet.
- **Funciones**: OCR del archivo del cursor al visor (por líneas, con «Página N»); OCR por lotes de los marcados a un `.txt` junto a cada archivo (operación); PDF escaneado: renderizar cada página y reconocerla; elegir idioma entre los instalados y explicar cómo instalar más; OCR de la imagen del portapapeles; OCR de la ventana en primer plano (para programas inaccesibles: captura con `PrintWindow`); copiar el resultado.
- **Motor**: `Windows.Media.Ocr` y `Windows.Data.Pdf`. Vía preferente: paquetes `winrt-*` de pywinrt vendorizados (si hay ruedas para Python 3.15). Vía de reserva, sin paquetes: un guion de Windows PowerShell 5.1 (`ocr.ps1` dentro del complemento) que usa las mismas API de WinRT y devuelve JSON por la salida estándar, lanzado con `-NoProfile -ExecutionPolicy Bypass -File` sin consola. Se elige la que funcione al activarse (prueba con una imagen de 1 píxel) y se registra cuál.
- **Órdenes**: `zc.ocr:reconocer` «&Reconocer el texto» (Ctrl+Mayús+F3, global); `zc.ocr:lotes` «Reconocer los marcados a &archivos de texto...» (—, global); `zc.ocr:portapapeles` «Reconocer la imagen del &portapapeles» (—, global); `zc.ocr:ventana` «Reconocer la &ventana en primer plano» (—, global; tecla global posible).
- **Configuración**: `idioma` (texto, vacío = el de Windows), `escala_pdf` (decimal 1–4, 2,0), `carpeta_salida` (carpeta, vacío = junto al archivo), `sobrescribir` (bool, no), `motor` (opción `automatico`, `winrt`, `powershell`).
- **Sonidos**: `zc.ocr:fin` (termina un reconocimiento).
- **Dependencias**: Windows 10 o 11 con al menos un idioma OCR; permiso `ejecutar_programas` (reserva PowerShell), `portapapeles`.
- **Pruebas mínimas**: con un motor falso, una imagen da su texto por líneas en el visor y el lote crea `foto.txt` junto a `foto.png` sin sobrescribir uno existente; el analizador del JSON de `ocr.ps1` acepta la salida de ejemplo guardada; sin idiomas OCR, el mensaje explica cómo instalarlos. Prueba real marcada `@pytest.mark.interfaz` con una imagen de texto generada.

### 11.4 Metadatos y etiquetas de audio (`zc.metadatos`, P1)

- **Qué hace**: lee y edita etiquetas de MP3, FLAC, M4A, OGG, Opus, WMA y WAV.
- **Funciones**: columnas; líneas en Ctrl+Mayús+I; **editor accesible** de uno o varios archivos (formulario con etiqueta antes de cada campo; con varios, cada campo empieza en «(sin cambio)»); numerar pistas en el orden del panel; etiquetas desde el nombre de archivo con una máscara (`[pista] - [artista] - [titulo]`) con vista previa; quitar etiquetas; añadir o extraer la portada; exportar la lista de pistas (texto o CSV); máscaras de renombrado.
- **Órdenes**: `zc.metadatos:editar` «&Editar las etiquetas...» (Ctrl+Mayús+F2, panel); `zc.metadatos:desde_nombre` «Etiquetas &desde el nombre...» (—, panel); `zc.metadatos:numerar` «&Numerar las pistas» (—, panel); `zc.metadatos:quitar` «&Quitar las etiquetas...» (—, panel); `zc.metadatos:portada` «&Portada...» (—, panel); `zc.metadatos:exportar` «E&xportar la lista de pistas...» (—, panel).
- **Columnas**: `artista`, `titulo`, `album`, `pista`, `anio` (Año), `genero`, `duracion` (tipo duración), `bitrate` (Tasa de bits), `frecuencia`, `canales`, `portada` (Sí/No). Todas lentas.
- **Máscaras** (con el prefijo `MP3:` para no chocar con las de la 1.x, como `[EXIF:…]` en Imágenes; valen para todos los formatos de audio que lee, no solo MP3): `[MP3:artista]`, `[MP3:titulo]`, `[MP3:album]`, `[MP3:pista]` (con dos cifras), `[MP3:anio]` y `[MP3:genero]`. En la 1.x `[t]` es la hora y `[y]` el año con dos cifras (1.x §8.14), y siguen siéndolo.
- **Configuración**: `version_id3` (opción `2.3` o `2.4`, `2.3`), `conservar_fechas` (bool, sí), `columnas_musica` (bool, sí: crea al activarse el conjunto «Música» de 10.4 con su regla de contenido).
- **Sonidos**: `zc.metadatos:guardado` (se guardan las etiquetas).
- **Dependencias**: mutagen vendorizado en `lib/` (se importa por su nombre con el `MetaPathFinder` del complemento, 3.4). Operación por lotes con deshacer (copia de las etiquetas anteriores en `datos/deshacer/`, acción registrada con `zc.deshacer.registrar`). `columnas_musica` usa `zc.vistas.proponer_conjunto`.
- **Pruebas mínimas**: un MP3 y un FLAC generados en la prueba con etiquetas conocidas dan sus columnas; editar dos archivos a la vez con un campo en «(sin cambio)» no lo toca; `[MP3:pista] - [MP3:titulo]` renombra «03 - Hola.mp3» y `[t]` sigue dando la hora de la 1.x; la máscara `[pista] - [artista] - [titulo]` sobre «01 - Ana - Canción.mp3» rellena los tres campos; el editor pasa `revisar_teclado`.

### 11.5 Búsqueda instantánea (`zc.busqueda_instantanea`, P5)

- **Qué hace**: busca nombres en todo el equipo en milisegundos con Everything (si está instalado y abierto) o con el índice de búsqueda de Windows.
- **Funciones**: ventana con campo «&Buscar:» y lista virtual de resultados que se actualiza al escribir (tras 300 ms sin teclear; recuento anunciado como resultado tras la pausa); sintaxis de Everything (`ext:pdf`, `size:>1gb`, `dm:today`); «&Enviar al panel» como lista de resultados; Intro va al archivo en el panel activo; motor del diálogo Buscar archivos («Usar el índice»); búsquedas guardadas; texto contenido con el índice de Windows.
- **Motores**: Everything por su protocolo de mensajes (`WM_COPYDATA` a la ventana `EVERYTHING_TASKBAR_NOTIFICATION`, consulta y respuesta como en `everything_ipc.h`), por `ctypes`, sin distribuir nada de Everything; índice de Windows por OLE DB (`Search.CollatorDSO`) con `win32com.client`.
- **Órdenes**: `zc.busqueda_instantanea:abrir` «&Búsqueda instantánea...» (Ctrl+Mayús+F, global, ancla Comandos).
- **Configuración**: `motor` (opción `automatico`, `everything`, `windows`), `max_resultados` (entero, 1000), `incluir_ocultos` (bool, no), `carpetas_excluidas` (lista, vacía), `retardo_ms` (entero 100–2000, 300).
- **Dependencias**: pywin32 (incluido). Proveedor de búsqueda (3.5).
- **Pruebas mínimas**: el traductor de la consulta a SQL del índice de Windows (`*.pdf` en `C:\Docs`) da la cadena esperada; el analizador de la respuesta de Everything acepta un búfer de ejemplo; sin motores, la ventana lo explica; la ventana pasa `revisar_teclado`.

### 11.6 Conversor multimedia con FFmpeg (`zc.ffmpeg`, P1)

- **Qué hace**: convierte audio y vídeo, extrae el audio de un vídeo, recorta, normaliza el volumen y da la información técnica, con el componente `ffmpeg` (FFmpeg 9.0.2 GPL, `ffmpeg.exe` y `ffprobe.exe`).
- **Funciones**:
  - **Convertir** los elementos de trabajo con perfiles: MP3 (128, 192, 320 kb/s o VBR), AAC/M4A, Opus, OGG Vorbis, FLAC, WAV, MP4 (H.264 + AAC), WebM (VP9 + Opus), MKV (copiar flujos), y «Personalizado» (argumentos de FFmpeg escritos por la persona, validados: sin `-y` sobre el original ni rutas fuera de la carpeta de salida).
  - **Extraer audio** de un vídeo (copiando el flujo si se puede, o convirtiendo).
  - **Recortar**: inicio y fin («0:01:30» a «0:05:00»), sin recodificar si se puede.
  - **Normalizar** el volumen (filtro `loudnorm` de dos pasadas, EBU R128, objetivo configurable).
  - **Información técnica** (`ffprobe -print_format json -show_format -show_streams`): duración, contenedor, flujos con códec, tasa de bits, frecuencia, canales, resolución y fotogramas por segundo, en un texto de solo lectura y en Ctrl+Mayús+I.
  - **Unir** archivos de audio del mismo formato (demuxer `concat`).
- Cada conversión es una operación del motor (`OperacionFFmpeg`): carriles de origen y destino (`clave_carril`), progreso real leyendo `-progress pipe:1` (`out_time_us`, en microsegundos, frente a la duración de `ffprobe`; no `out_time_ms`, que pese a su nombre también viene en microsegundos), pausa entre archivos, cancelación (termina el proceso lanzado con `app.core.procesos` y borra el archivo a medias), errores por archivo con la última línea de `stderr` traducida («Formato no reconocido», «Códec no disponible»). La salida se escribe a un temporal y se renombra (como el motor de copia). Nunca sobrescribe el original: política de conflictos del motor.
- **Diálogo** «Convertir» (`ventanas/convertir.py`): «&Perfil:», «&Calidad:» (según el perfil), «&Carpeta de salida:» (por defecto el otro panel), «&Nombre:» (máscara `[N]` como el renombrado; por defecto el mismo nombre con la extensión nueva), casillas «&Conservar las etiquetas» y «C&onservar las fechas», «Si &existe:» (políticas del motor). Botones «Con&vertir», «&En cola» y «&Cancelar».
- **Órdenes**: `zc.ffmpeg:convertir` «&Convertir audio o vídeo...» (Ctrl+Mayús+F6, global); `zc.ffmpeg:extraer_audio` «&Extraer el audio...» (—, global); `zc.ffmpeg:recortar` «&Recortar...» (—, global); `zc.ffmpeg:normalizar` «&Normalizar el volumen...» (—, global); `zc.ffmpeg:informacion` «&Información técnica» (—, panel); `zc.ffmpeg:unir` «&Unir archivos de audio...» (—, global).
- **Configuración**: `perfil` (texto, `mp3_192`), `carpeta_salida` (opción `otro_panel`, `misma`, `elegida`; `otro_panel`), `carpeta_elegida` (carpeta, vacía), `hilos` (entero 0–16, 0 = automático), `normalizar_lufs` (decimal −30 a −10, −16), `conservar_etiquetas` (bool, sí), `perfiles_propios` (lista interna).
- **Dependencias**: componente `ffmpeg` (`[requiere] componentes = ["ffmpeg"]`); permiso `ejecutar_programas`. Sin el componente, sus órdenes dicen «Falta el componente FFmpeg: Opciones, Componentes externos».
- **Pruebas mínimas**: el constructor de argumentos de cada perfil da la lista esperada (sin `shell`, rutas tras sus opciones); el analizador de `-progress` calcula el porcentaje; el analizador de `ffprobe` lee un JSON de ejemplo guardado; un argumento personalizado con `-y` sobre el original se rechaza; con FFmpeg real (`@pytest.mark.lento`), convertir un WAV de 1 s generado en la prueba a FLAC y a MP3 da archivos válidos (los lee `ffprobe`) y cancelar a medias no deja el destino.

### 11.7 Buscador de duplicados (`zc.duplicados`, P3)

- **Qué hace**: encuentra archivos iguales en una o varias carpetas y ayuda a decidir qué conservar.
- **Funciones**: criterios por contenido (tamaño, después hash parcial de 64 KB y completo con BLAKE2b), por nombre, por nombre y tamaño, o por etiquetas de audio (con `zc.metadatos`); resultados en una ventana con lista (Grupo, Nombre, Carpeta, Tamaño, Fecha) que se lee «Grupo 3 de 40, 2 copias, 12 MB recuperables»; marcado automático (conservar el más antiguo, el más reciente, el de una carpeta preferida, el de ruta más corta) con resumen hablado; enviar a la papelera los marcados (operación de eliminar del núcleo); sustituir por enlaces duros (misma unidad NTFS); exportar informe; enviar al panel.
- **Órdenes**: `zc.duplicados:buscar` «Buscar &duplicados...» (Mayús+F7, global, ancla Comandos > Herramientas).
- **Configuración**: `tamano_minimo_kb` (entero, 1), `excluir` (texto, `*.tmp;Thumbs.db;desktop.ini`), `incluir_ocultos` (bool, no), `carpeta_preferida` (carpeta, vacía), `accion` (opción `papelera`, `enlace_duro`; `papelera`).
- **Pruebas mínimas**: tres archivos iguales y uno distinto del mismo tamaño dan un grupo de tres; «conservar el más antiguo» marca los otros dos; el análisis se cancela; sustituir por enlace duro deja un solo contenido (mismo índice de archivo) en NTFS.

### 11.8 Ocupación del disco accesible (`zc.ocupacion`, P3)

- **Qué hace**: dice qué ocupa el espacio, con listas que se leen.
- **Funciones**: análisis de una unidad o carpeta (operación); proveedor de solo lectura `ocupacion://<id del análisis>/ruta` que se navega en el panel con las columnas Nombre, Tamaño, Porcentaje del padre, Porcentaje del total, Archivos y Modificado, ordenado por tamaño («Vídeos: 45 GB, 38 %, 1 200 archivos»); los 100 archivos más grandes; ocupación por extensión; por antigüedad (no modificados en más de N años); resumen de la unidad; exportar a texto o CSV; «Ir a esta carpeta» en el disco (lleva el otro panel); recordar el último análisis de cada carpeta (`datos/analisis/`).
- **Órdenes**: `zc.ocupacion:analizar` «Analizar la &ocupación...» (Ctrl+Mayús+F7, global, ancla Comandos > Herramientas); `zc.ocupacion:mayores` «Los &100 archivos más grandes» (—, global); `zc.ocupacion:extensiones` «Ocupación por &extensión» (—, global); `zc.ocupacion:ir` «&Ir a esta carpeta en el disco» (—, panel).
- **Configuración**: `seguir_enlaces` (bool, no), `tamano_en_disco` (bool, no: tamaño lógico), `incluir_nube` (bool, no), `anios_antiguedad` (entero, 2).
- **Dependencias**: reutiliza `recorrido.py` y `tamano_carpetas.py` del núcleo.
- **Pruebas mínimas**: un árbol generado con tamaños conocidos da los porcentajes exactos; el proveedor `ocupacion://` lista y sube; las uniones no se siguen; cancelar deja el análisis parcial marcado como incompleto.

### 11.9 Archivos en uso y procesos (`zc.procesos`, P4)

- **Qué hace**: dice qué programa tiene abierto un archivo y permite cerrarlo; lista los procesos.
- **Funciones**: «¿Quién usa este archivo?» sobre los elementos de trabajo (Restart Manager: `RmStartSession`, `RmRegisterResources`, `RmGetList`, por `ctypes`); **acción de error** en el motor: con un error de acceso por archivo en uso, la pregunta de error gana «Ver qué programa lo &usa» y «&Cerrar ese programa y reintentar» (con confirmación; nunca procesos del sistema ni el propio zCommander); ventana de procesos con lista (Nombre, PID, Memoria, CPU, Usuario, Ruta), «&Terminar» (con confirmación), «Cambiar la &prioridad», «Abrir su &carpeta» en el panel y «&Copiar la información».
- **Órdenes**: `zc.procesos:quien_usa` «¿&Quién usa este archivo?» (—, panel); `zc.procesos:lista` «&Procesos...» (Ctrl+Mayús+F12, global).
- **Configuración**: `refresco_s` (entero 1–60, 3), `mostrar_sistema` (bool, no).
- **Sonidos**: `zc.procesos:cerrado` (un programa se cerró a petición).
- **Dependencias**: pywin32 (`win32process`, `win32api`, `win32pdh` para CPU); sin psutil.
- **Acción de error**: el manifiesto declara `codigos_windows = [32, 33]` (`ERROR_SHARING_VIOLATION` y `ERROR_LOCK_VIOLATION`) en sus `[[acciones_error]]`, así los botones salen en el primer error sin activar el complemento (3.4); `aplica()` mira `pregunta.codigo_windows` (14.6), nunca el texto del mensaje.
- **Pruebas mínimas**: un archivo abierto por un subproceso de la prueba aparece con su PID en «¿Quién usa?»; la acción de error aparece solo con errores de archivo en uso (código 32 o 33); los procesos del sistema no se pueden terminar desde la lista.

### 11.10 Editor hexadecimal accesible (`zc.hexadecimal`, P2)

- **Qué hace**: ve y edita los bytes de cualquier archivo, también muy grande, de forma accesible.
- **Ventana** (`VentanaComplemento`): un `TextCtrl` multilínea de solo lectura con el volcado visible (líneas «00000010  48 6F 6C 61 ...  Hola...»), un texto de solo lectura «&Inspector:» y una barra de estado. El cursor de bytes lo lleva zCommander: Izquierda y Derecha mueven un byte, Arriba y Abajo una línea (16 bytes), Inicio y Fin principio y fin de la línea, Ctrl+Inicio y Ctrl+Fin principio y fin del archivo, Re Pág y Av Pág una pantalla; cada movimiento coloca el cursor del texto en el byte (con la marca de movimiento silencioso de 10.16, por `zc.ui.movimiento_silencioso`) y anuncia «Desplazamiento 0x1A, 4F, letra O» (con el nivel de detalle: solo el valor, o también decimal y binario). Tab alterna entre la columna hexadecimal y la de texto.
- **Edición**: en la columna hexadecimal, dos dígitos sobrescriben el byte (un dígito no válido suena `zc.hexadecimal:no_valido`); en la de texto, cada carácter se escribe con la codificación elegida; Insert alterna insertar y sobrescribir (con NVDA, Insert dos veces); Supr y Retroceso borran en modo insertar; Mayús con flechas selecciona; Ctrl+C copia la selección como hexadecimal y Ctrl+Mayús+C como texto; Ctrl+V pega hexadecimal o texto; Ctrl+Z y Ctrl+Y deshacer y rehacer sin límite en la sesión.
- **Buscar y reemplazar** (Ctrl+F, F3, Mayús+F3, Ctrl+R): por hexadecimal (`4F 6B ?? 00`, con comodín) o texto (con codificación), en todo el archivo por bloques en un hilo.
- **Ir a desplazamiento** (Ctrl+G): decimal, `0x` hexadecimal, `+n` o `-n` relativo, o porcentaje.
- **Inspector de tipos** (Ctrl+I lo anuncia; Ctrl+Mayús+I dice la barra de estado): en el cursor, entero de 8, 16, 32 y 64 bits con y sin signo en orden de bytes elegible, coma flotante de 32 y 64 bits, carácter UTF-8 y UTF-16, fecha Unix y FILETIME; Ctrl+E cambia el orden de bytes.
- **Archivos grandes**: tabla de piezas (archivo original más lista de cambios); solo se lee lo visible; guardar (Ctrl+S o F2) escribe a un temporal en la misma carpeta y lo sustituye (con `.bak` si `copia_seguridad`); guardar como (Mayús+F2); si el archivo cambió en disco, avisa. Archivos de comprimidos o servidores: solo lectura, «Guardar como» en local.
- **Órdenes**: `zc.hexadecimal:editar` «Editar en &hexadecimal» (Ctrl+Mayús+F4, global, ancla Archivos).
- **Configuración**: `bytes_por_linea` (opción 8, 16, 32; 16), `orden_bytes` (opción `little`, `big`; `little`), `codificacion_texto` (opción como el visor, `cp1252`), `anuncio` (opción `valor`, `completo`; `valor`), `copia_seguridad` (bool, no), `abrir_solo_lectura` (bool, no).
- **Sonidos**: `zc.hexadecimal:no_valido` (tecla no válida en la columna hexadecimal).
- **Pruebas mínimas** (la lógica en `servicios/` sin wx): la tabla de piezas inserta, sobrescribe, borra, deshace y rehace y guarda un archivo de 3 MB con los bytes esperados; buscar `48 ?? 6C` encuentra «Hel»; el inspector de `01 00 00 00` da 1 en `little` y 16 777 216 en `big`; ir a `0x10`, `+16` y `50%` da los desplazamientos esperados; la ventana pasa `revisar_teclado`; mover el cursor anuncia el texto esperado.

### 11.11 Imágenes: información, descripción y visor (`zc.imagenes`, P1)

- **Qué hace**: dice qué hay en una imagen y ofrece un visor para baja visión.
- **Funciones**: información (formato, ancho y alto, megapíxeles, orientación, profundidad) y EXIF (fecha de la toma, cámara, objetivo, exposición, GPS) en Ctrl+Mayús+I y como columnas; texto de la imagen con `zc.ocr` (`reconocer`, 11.0); **descripción opcional y explícita** con un servicio que configura la persona: un servidor local compatible con Ollama o una API compatible con OpenAI (clave en secretos); aviso de privacidad la primera vez («La imagen se enviará a <servidor>»); nunca automática; visor ampliable (ajustar, 100 %, zoom, girar, siguiente y anterior, alto contraste) con el estado en texto; convertir, redimensionar y girar por lotes (operación); quitar los metadatos GPS; máscaras.
- **Órdenes**: `zc.imagenes:describir` «&Describir la imagen...» (—, panel); `zc.imagenes:visor` «Ver la imagen &ampliada» (—, panel; visor registrado para F3 en imágenes si la persona lo elige en asociaciones); `zc.imagenes:convertir` «&Convertir o redimensionar imágenes...» (—, global); `zc.imagenes:quitar_gps` «&Quitar la ubicación (GPS)...» (—, panel).
- **Columnas**: `dimensiones`, `fecha_toma`, `camara`. **Máscaras**: `[EXIF:fecha]` (AAAA-MM-DD), `[EXIF:hora]`, `[ancho]`, `[alto]`, `[camara]`.
- **Configuración**: `servicio` (opción `ninguno`, `ollama`, `openai`; `ninguno`), `url_servicio` (texto, `http://127.0.0.1:11434`), `modelo` (texto, vacío), `idioma_descripcion` (texto, `es`), `longitud` (opción `breve`, `detallada`; `breve`), `calidad_jpeg` (entero 50–100, 90), `aviso_privacidad_mostrado` (bool interno). Secreto `clave_api`.
- **Sonidos**: `zc.imagenes:descripcion` (llega la descripción).
- **Dependencias**: lectura y escritura con `wx.Image` y metadatos con el sistema de propiedades de Windows (`win32com.propsys`, `System.Photo.*`); Pillow vendorizado solo si hay rueda para Python 3.15 (quitar GPS sin recomprimir, más formatos). Permisos `red` (servicio), `secretos`.
- **Pruebas mínimas**: un JPEG generado con EXIF conocido da fecha y dimensiones; la máscara `[EXIF:fecha]` renombra como se espera; con un servidor de descripción falso local, la descripción llega y sin `servicio` la orden explica cómo configurarlo; el visor pasa `revisar_teclado`.

### 11.12 Sincronización avanzada y copias (`zc.sincronizacion`, P5)

- **Qué hace**: tareas de sincronización y copia con nombre, que recuerdan el estado anterior y conservan versiones.
- **Funciones**: perfiles con origen, destino (cualquier proveedor: local, red, FTP, SFTP, nube; abiertos sin panel con `zc.vfs.resolver`), dirección, criterios, exclusiones y filtros (reutiliza `diferencias_carpetas.py`); modos espejo, actualizar y dos sentidos **con base de datos del último estado** (`sqlite3` en `datos/<perfil>.db`: detecta borrados y renombrados en cada lado); versiones: lo sustituido o borrado va a `_versiones\AAAA-MM-DD\` con límite de días o de tamaño; simulación con informe en lista; ejecutar uno o todos; informe final hablado y guardado; uso desde el programador (11.24).
- **Órdenes**: `zc.sincronizacion:perfiles` «&Tareas de sincronización...» (—, global, ancla Comandos); `zc.sincronizacion:ejecutar_todas` «&Ejecutar todas las tareas» (—, global).
- **Configuración**: `tolerancia_fecha_s` (entero, 2), `verificar` (bool, no), `dias_versiones` (entero, 30), `max_versiones_mb` (entero, 1024).
- **Pruebas mínimas**: dos sentidos con base de estado: un archivo borrado a la izquierda tras la primera sincronización se borra a la derecha (y no se vuelve a copiar); un sustituido va a `_versiones`; la simulación no cambia nada.

### 11.13 Cifrado de archivos (`zc.cifrado`, P4)

- **Qué hace**: cifra y descifra archivos y carpetas con contraseña.
- **Formato `.zcc`**: cabecera `ZCC1` + longitud y JSON de parámetros (`{"kdf": "scrypt", "n": 131072, "r": 8, "p": 1, "sal": "...", "nombre": "original.ext", "tamano": n, "bloque": 1048576}`) + bloques AES-256-GCM de 1 MiB, cada uno con nonce = prefijo aleatorio de 8 bytes + contador de 4 bytes y la cabecera como datos asociados; el último bloque lleva una marca de final para impedir el truncado. Documentado en `doc/es/formato-zcc.md`.
- **Funciones**: cifrar los marcados en `.zcc` (uno por archivo; las carpetas, primero a un ZIP) o en un 7z con AES-256 compatible con 7-Zip (py7zr o 7za); descifrar con Intro (asociación «Abrir» de `*.zcc`) o desde el menú; contraseña con confirmación y medidor de fortaleza en texto; enviar el original a la papelera tras comprobar el cifrado (opcional); ver un `.zcc` en el visor sin dejar el descifrado fuera de `data/temp`; aviso claro: si se pierde la contraseña, no hay recuperación. No promete borrado seguro (1.x §1.4).
- **Órdenes**: `zc.cifrado:cifrar` «&Cifrar...» (Ctrl+Mayús+F8, global); `zc.cifrado:descifrar` «&Descifrar...» (—, global).
- **Configuración**: `formato` (opción `zcc`, `7z`; `zcc`), `coste_scrypt` (opción `normal` n=2^17, `alto` n=2^19; `normal`), `borrar_originales` (bool, no), `recordar_en_sesion` (bool, no). `hashlib.scrypt` se llama siempre con `maxmem = 128*r*(n+2) + 64 MiB` (el límite por defecto de OpenSSL, 32 MiB, no basta ni para `normal`): unos 192 MiB con `normal` y unos 576 MiB con `alto`; la ayuda de la opción dice que `alto` reserva más de medio gigabyte al cifrar y al descifrar.
- **Dependencias**: `cryptography` y `hashlib.scrypt`; py7zr o el componente `7za`.
- **Pruebas mínimas**: cifrar y descifrar 3 MB devuelve los mismos bytes; cambiar un byte o truncar el último bloque da «El archivo está dañado o la contraseña no es correcta»; la contraseña equivocada no deja ningún archivo descifrado; el original solo va a la papelera tras comprobar.

### 11.14 Notas, comentarios y etiquetas (`zc.notas`, P3)

- **Qué hace**: comentarios en archivos y carpetas y etiquetas con nombre y color.
- **Funciones**: comentario por archivo compatible con `descript.ion` (formato de Total Commander, Double Commander y 4DOS), columna «Comentario»; nota por carpeta que se anuncia al entrar («Esta carpeta tiene una nota», nivel normal, suena `zc.notas:nota_carpeta`) y se lee con la orden; etiquetas con nombre y color («Urgente», «Facturas»), como columna y en texto, nunca solo con color; buscar por etiqueta o comentario (lista de resultados); filtro por etiqueta; los comentarios viajan al copiar y mover dentro de zCommander (evento `al_terminar_operacion`, con los pares reales origen → destino de `operacion.pares_hechos()`, que ya tienen en cuenta los renombrados por conflicto, 14.5) si `viajar` está activa.
- **Órdenes**: `zc.notas:comentario` «&Comentario o nota...» (Ctrl+N, panel: edita el del cursor o, en «..», la nota de la carpeta); `zc.notas:leer_nota` «&Leer la nota de la carpeta» (—, global); `zc.notas:etiquetas` «&Etiquetas...» (—, panel); `zc.notas:buscar` «&Buscar por etiqueta o comentario...» (—, global).
- **Columnas**: `comentario`, `etiquetas`.
- **Configuración**: `almacen` (opción `descript_ion`, `base_central`; `descript_ion`; la base central en `datos/notas.db` para carpetas de solo lectura y de red), `anunciar_notas` (bool, sí), `viajar` (bool, sí), `etiquetas` (lista interna con nombre y color).
- **Sonidos**: `zc.notas:nota_carpeta`.
- **Pruebas mínimas**: leer y escribir `descript.ion` con nombres con espacios (entre comillas) y caracteres no ASCII; un comentario viaja al copiar el archivo; una nota se anuncia al entrar.

### 11.15 Proyectos y salto rápido (`zc.proyectos`, P5)

- **Qué hace**: lleva a cualquier carpeta frecuente escribiendo parte de su nombre y gestiona proyectos sobre los espacios de trabajo del núcleo (10.9).
- **Funciones**: **salto rápido**: un campo «&Ir a:» con lista; escribir «fact» propone las carpetas que lo contienen ordenadas por frecuencia y antigüedad de uso (algoritmo de «frecencia» como zoxide, con los cambios de carpeta del bus); Intro lleva el panel; carpetas recientes de Windows (lista de elementos recientes del shell); proyecto = espacio de trabajo del núcleo (con `zc.espacios`: listar, guardar el actual, abrir) + nota + carpetas propias.
- **Órdenes**: `zc.proyectos:salto` «&Salto rápido...» (Ctrl+Mayús+J, global); `zc.proyectos:proyectos` «&Proyectos...» (—, global).
- **Configuración**: `max_carpetas` (entero, 1000), `peso_frecuencia` (decimal, 1,0), `media_vida_dias` (entero, 14), `excluidas` (lista, `C:\Windows`).
- **Activación**: `al_arrancar` (para contar los cambios de carpeta desde el principio); datos en `datos/frecencia.json`.
- **Pruebas mínimas**: con visitas simuladas, «fact» propone primero la más frecuente y reciente; la media vida reduce el peso de lo antiguo; las excluidas no aparecen.

### 11.16 Historial del portapapeles (`zc.portapapeles`, P4)

- **Qué hace**: recuerda lo que se copió (texto y listas de archivos) y permite volver a pegarlo.
- **Funciones**: ventana con lista (Contenido: el texto o «3 archivos de D:\Fotos», Hora, Fijado); buscar; fijar; pegar como texto en la línea de órdenes (`zc.escribir_en_linea`), como archivos en el panel o **como archivo nuevo** (texto copiado a `nota.txt` en la carpeta del panel); anunciar las copias hechas fuera de zCommander (opcional, como ClipSpeak); borrar uno o todo. Respeta el formato `ExcludeClipboardContentFromMonitorProcessing` de los gestores de contraseñas (no se guarda).
- **Órdenes**: `zc.portapapeles:historial` «&Historial del portapapeles...» (Ctrl+Mayús+V, panel).
- **Configuración**: `elementos` (entero 5–500, 50), `guardar_entre_sesiones` (bool, no; en `datos/historial.json` cifrado con DPAPI), `anunciar_externas` (bool, no).
- **Sonidos**: `zc.portapapeles:copia_externa`.
- **Activación**: `al_arrancar` (escucha con `AddClipboardFormatListener` sobre una ventana oculta). Permiso `portapapeles`.
- **Pruebas mínimas**: dos textos y una lista de archivos copiados en la prueba aparecen en orden; un elemento con el formato de exclusión no se guarda; «pegar como archivo nuevo» crea `nota.txt` sin sobrescribir.

### 11.17 Lectura en voz y audiolibros (`zc.voz`, P1)

- **Qué hace**: lee archivos de texto y documentos con una voz de Windows (aparte del lector de pantalla) y los convierte en audio.
- **Funciones**: leer de corrido con pausa, continuar, frase y párrafo anterior y siguiente, velocidad; recordar dónde se dejó; exportar a WAV (SAPI `SpFileStream`) y, con el componente `ffmpeg`, a MP3 u Opus, uno o varios archivos como operación (audiolibros); dividir por capítulos (con `zc.documentos`, `convertir`, 11.0; FFmpeg por `zc.componentes.ejecutable("ffmpeg", "ffmpeg.exe")`); voces SAPI 5 y, si están, OneCore.
- **Órdenes**: `zc.voz:leer` «&Leer en voz alta o pausar» (Ctrl+F9, global; tecla global posible); `zc.voz:detener` «&Detener la lectura» (—, global); `zc.voz:exportar` «&Convertir a audio...» (—, global); `zc.voz:frase_siguiente`, `zc.voz:frase_anterior`, `zc.voz:parrafo_siguiente`, `zc.voz:parrafo_anterior` (—, global, solo paleta y menú).
- **Configuración**: `voz` (texto, vacío = la predeterminada), `velocidad` (entero −10 a 10, 0), `tono` (entero −10 a 10, 0), `volumen` (entero 0–100, 100), `formato_salida` (opción `wav`, `mp3`, `opus`; `mp3`), `pausa_parrafo_ms` (entero, 400).
- **Sonidos**: `zc.voz:fin` (termina la lectura).
- **Dependencias**: SAPI por COM (comtypes o pywin32); OneCore con pywinrt si está; componente `ffmpeg` recomendado.
- **Pruebas mínimas**: la división en frases y párrafos de un texto en español con abreviaturas («Sr.», «p. ej.») da los cortes esperados; con una voz falsa, pausa y continuar reanudan en la frase correcta; exportar llama a FFmpeg con los argumentos esperados.

### 11.18 Monitor de carpetas y reglas automáticas (`zc.monitor`, P5)

- **Qué hace**: vigila carpetas (Descargas, escaneos) y avisa o actúa cuando llega algo.
- **Funciones**: anuncio al llegar un archivo cuando termina de escribirse («Nuevo en Descargas: factura.pdf, 2 MB»); reglas «si coincide el patrón, el tamaño o la antigüedad, entonces mover, copiar, renombrar con máscara, extraer, etiquetar (`zc.notas`, `etiquetar`, 11.0) o ejecutar una orden o macro (`zc.ejecutar_orden`, en el hilo de la interfaz)»; las carpetas vigiladas se abren sin panel con `zc.vfs.resolver`; simulación de las reglas sobre lo que ya hay; registro de lo hecho con deshacer de la última acción; pausar todo.
- **Órdenes**: `zc.monitor:reglas` «&Monitor de carpetas...» (—, global); `zc.monitor:pausar` «&Pausar o reanudar el monitor» (—, global, casilla); `zc.monitor:registro` «&Registro del monitor...» (—, global).
- **Configuración**: `carpetas` (lista, vacía), `reglas` (lista interna; editor propio), `retraso_s` (entero 1–600, 5), `nivel_anuncio` (opción `normal`, `resultado`, `ninguno`; `resultado`).
- **Sonidos**: `zc.monitor:archivo_nuevo`, `zc.monitor:regla_aplicada`.
- **Activación**: `al_arrancar`, siempre (la activación es estática, 11.0); si no hay carpetas vigiladas, `activar()` vuelve sin abrir ningún vigilante. Las carpetas se vigilan con `ReadDirectoryChangesW` en hilos con pywin32.
- **Pruebas mínimas**: un archivo creado en una carpeta temporal vigilada se anuncia una vez cuando deja de crecer; la regla «*.pdf → mover a Documentos» lo mueve; la simulación lista sin mover; deshacer devuelve el archivo.

### 11.19 Seguridad de descargas e integridad (`zc.seguridad`, P4)

- **Qué hace**: ayuda a decidir si un archivo es de fiar.
- **Funciones**: firma Authenticode de ejecutables e instaladores («Firmado por Mozilla Corporation, firma válida» o «Sin firma»; `WinVerifyTrust` y `CryptQueryObject` por `ctypes`), como columna e información; comparar la suma con la del portapapeles («Coincide con el SHA-256 del portapapeles»); analizar con Microsoft Defender (`MpCmdRun.exe -Scan -ScanType 3 -File`); buscar el hash en VirusTotal (opcional, con clave propia, solo el hash, nunca el archivo); ver y quitar la marca de la Web (`marca_web.py` del núcleo); versión e información del ejecutable (empresa, producto, versión, arquitectura).
- **Órdenes**: `zc.seguridad:firma` «Comprobar la &firma digital» (—, panel); `zc.seguridad:comparar_suma` «Comparar la suma con el &portapapeles» (—, panel); `zc.seguridad:defender` «Analizar con &Defender» (—, panel); `zc.seguridad:virustotal` «Buscar en &VirusTotal» (—, panel); `zc.seguridad:quitar_marca` «Quitar la marca de la &Web...» (—, panel).
- **Columnas**: `firma` (Firma), `marca_web` (Origen).
- **Configuración**: `analizar_descargas` (bool, no: analiza con Defender lo que se copia desde FTP, SFTP o nube), `algoritmo` (opción `sha256`, `sha1`, `md5`; `sha256`). Secreto `clave_virustotal`. Permisos `internet:www.virustotal.com`, `ejecutar_programas`, `secretos`.
- **Sonidos**: `zc.seguridad:sin_firma` (al comprobar un ejecutable sin firma o con firma no válida), `zc.seguridad:amenaza` (Defender o VirusTotal encuentran algo).
- **Pruebas mínimas**: un ejecutable firmado del sistema (`C:\Windows\System32\notepad.exe`) da «firma válida» y un `.exe` copiado y modificado da «firma no válida»; la comparación con el portapapeles reconoce la suma en mayúsculas o minúsculas y con espacios; el analizador de la salida de MpCmdRun acepta ejemplos guardados.

### 11.20 Papelera de reciclaje como panel (`zc.papelera`, P3)

- **Qué hace**: muestra la papelera en un panel con ruta original y fecha de eliminación.
- **Funciones**: proveedor `papelera://` (todas las unidades, o `papelera://D:/`) con columnas Nombre, Ubicación original, Fecha de eliminación y Tamaño, ordenado por fecha (lo último borrado primero); restaurar a su sitio (`IFileOperation`) o copiar a otro panel; buscar dentro; eliminar definitivamente los marcados o vaciar (confirmación con el foco en «&Cancelar»; suena `op.eliminado`); resumen («312 elementos, 4,2 GB»). «Papelera» aparece en el selector de unidades.
- **Órdenes**: `zc.papelera:abrir` «Abrir la &papelera» (Ctrl+F8, global); `zc.papelera:restaurar` «&Restaurar a su sitio» (—, panel); `zc.papelera:vaciar` «&Vaciar la papelera...» (—, global).
- **Configuración**: `unidades` (lista, vacía = todas).
- **Dependencias**: shell de Windows con pywin32 (`CSIDL_BITBUCKET`, `IShellFolder2.GetDetailsEx`).
- **Pruebas mínimas** (marcadas `interfaz` porque tocan la papelera real del usuario de pruebas: solo con archivos creados en la prueba): enviar un archivo a la papelera y verlo con su ubicación original; restaurarlo; el diálogo de vaciar pone el foco en Cancelar.

### 11.21 Git básico (`zc.git`, P4)

- **Qué hace**: muestra el estado de un repositorio y hace las operaciones más comunes.
- **Funciones**: columna «Git» («modificado», «nuevo», «sin seguimiento», «ignorado»); al entrar en un repositorio, anuncio de la rama y los cambios («Rama main, 3 cambios», detalle; suena `zc.git:repositorio`); añadir, quitar, confirmar los marcados con mensaje; diferencias con la ventana de diferencias del núcleo; historial del archivo o la carpeta en una lista; traer, enviar y cambiar de rama; clonar en la carpeta del panel; deshacer los cambios de un archivo (con confirmación); orden interna de la línea de órdenes `zc git <subórdenes>` (`[[internas]]` con `nombre = "git"`, `zc.ordenes.interna`; la salida va a «Salida de órdenes»).
- **Órdenes**: `zc.git:estado` «&Estado de Git» (Ctrl+Mayús+F11, global); `zc.git:anadir` «&Añadir» (—, panel); `zc.git:confirmar` «&Confirmar...» (—, global); `zc.git:diferencias` «&Diferencias» (—, panel); `zc.git:historial` «&Historial...» (—, panel); `zc.git:traer` «&Traer» (—, global); `zc.git:enviar` «E&nviar» (—, global); `zc.git:rama` «Cambiar de &rama...» (—, global); `zc.git:clonar` «C&lonar...» (—, global); `zc.git:descartar` «Des&cartar los cambios...» (—, panel).
- **Columnas**: `estado`.
- **Configuración**: `ruta_git` (archivo, vacío = buscar `git.exe` instalado), `anunciar_al_entrar` (bool, sí), `refresco_s` (entero, 5).
- **Sonidos**: `zc.git:repositorio` (al entrar en un repositorio).
- **Dependencias**: `git.exe` instalado (GPL-2.0, programa aparte) para todo; sin él, dulwich vendorizado para leer estado, historial y diferencias (solo lectura). Permiso `ejecutar_programas`, `red` (traer y enviar).
- **Pruebas mínimas** (con un repositorio creado en la prueba con dulwich): un archivo nuevo, uno modificado y uno ignorado dan sus estados; el historial lista dos confirmaciones; sin `git.exe`, confirmar dice «Hace falta Git instalado».

### 11.22 Datos tabulares: SQLite y CSV (`zc.tablas`, P2)

- **Qué hace**: abre bases SQLite como carpetas y muestra CSV y tablas como tablas accesibles.
- **Funciones**: entrar en un `.db`, `.sqlite` o `.sqlite3` como carpeta (la fábrica comprueba la cabecera «SQLite format 3»; si no, `NoAdmitido` y se abre con su programa) con una entrada `tabla.csv` por tabla y vista; F3 sobre una tabla o un CSV/TSV abre el **visor de tabla** (visor con `ventana = true`, registrado con `zc.visores.ventana`, 3.7): `ListaAccesible` virtual con cabeceras, que se lee por columnas (Izquierda, Derecha, Ctrl+1 a Ctrl+0); Ctrl+F filtrar, Ctrl+G ir a fila, Ctrl+O ordenar por la columna actual, Ctrl+E exportar a CSV, F5 consulta SQL (solo SQLite, en solo lectura salvo que se desactive); estructura de la tabla (columnas y tipos); detección de separador y codificación del CSV; copiar una tabla al otro panel la exporta a CSV.
- **Órdenes**: `zc.tablas:ver_tabla` «Ver como &tabla» (—, panel); `zc.tablas:consulta` «&Consulta SQL...» (—, global). (El id es `zc.tablas`, en la carpeta `plugins/tablas/`, para no confundirlo con `Anfitrion.datos`, la carpeta de datos de cada complemento.)
- **Configuración**: `solo_lectura` (bool, sí), `filas_maximas` (entero, 1 000 000), `separador` (opción `automatico`, `,`, `;`, tabulador; `automatico`).
- **Dependencias**: `sqlite3` y `csv` (biblioteca estándar).
- **Pruebas mínimas**: una base creada en la prueba con dos tablas se lista como dos `.csv`; el visor de un CSV con `;` y tildes en Windows-1252 muestra las cabeceras; una consulta `SELECT` da sus filas y `DELETE` se rechaza en solo lectura; el visor pasa `revisar_teclado`.

### 11.23 Organizador y renombrado por metadatos (`zc.organizador`, P3)

- **Qué hace**: ordena archivos en carpetas y les pone nombre según su contenido.
- **Funciones**: plantillas como `Fotos\[EXIF:fecha:AAAA]\[EXIF:fecha:MM]` (fecha EXIF), `Música\[MP3:artista]\[MP3:album]\[MP3:pista] - [MP3:titulo]` (etiquetas), `Documentos\[Y]` (fecha de modificación o del PDF); las plantillas se resuelven con `zc.renombrado.evaluar` (3.7), que usa las máscaras de todos los complementos; vista previa en lista (Nombre actual, Destino nuevo, Estado) como el renombrado múltiple; ejecutar como operación con deshacer (`OperacionCopiar` con `mover=True`; su deshacer es el del motor, y lo que no cubra se registra con `zc.deshacer.registrar(AccionDeshacer)`); plantillas guardadas; integración con las reglas del monitor (11.18).
- **Órdenes**: `zc.organizador:organizar` «&Organizar por metadatos...» (—, global, ancla Comandos > Herramientas).
- **Configuración**: `plantillas` (lista interna), `sin_dato` (texto, `Sin fecha`), `accion` (opción `mover`, `copiar`; `mover`).
- **Dependencias**: máscaras de `zc.metadatos`, `zc.imagenes` y `zc.documentos` (`[recomienda]`); las de la 1.x siempre.
- **Pruebas mínimas**: tres fotos con fechas EXIF distintas van a sus carpetas de año y mes en la vista previa; dos que darían el mismo destino se marcan «Duplicado»; deshacer las devuelve.

### 11.24 Programador de tareas (`zc.programador`, P5)

- **Qué hace**: ejecuta tareas de zCommander a una hora o con una frecuencia, también con zCommander cerrado.
- **Funciones**: tareas de sincronización (11.12), copia, reglas del monitor, limpieza (a la papelera lo de más de N días en una carpeta), macros y entradas del menú de usuario; una vez, a diario, semanal, al iniciar sesión; registro de ejecuciones con resultado; ejecutar ahora; avisar del resultado al abrir zCommander o con una notificación de Windows.
- **Ejecución**: con «Usar el Programador de tareas de Windows» (por defecto), crea una tarea de Windows por COM (`Schedule.Service`) que lanza `ZCommander.exe --tarea <id>` (14.8), con `TASK_LOGON_INTERACTIVE_TOKEN`: se ejecuta en la sesión de la persona y con su usuario, así DPAPI descifra `secretos.dat` (con S4U no podría) y la ventana minimizada aparece en su escritorio; si la sesión no está iniciada a la hora, la tarea se ejecuta al iniciarla (`StartWhenAvailable`). **Siempre se ejecuta dentro de la instancia normal de zCommander**: nunca hay dos procesos sobre la misma carpeta `data` ni dos `rclone rcd`, y no hay modo sin ventana.
  - **Si zCommander está abierto**: `main.py` reenvía la tarea a esa instancia **solo** con `instancia_unica.dejar_orden("tarea", [id])` (sin la orden `mostrar` de la 1.x) y sale. Las órdenes `tarea` del buzón **no traen la ventana al frente ni cuentan como uso**. La ventana recoge la orden `tarea` (14.8) y llama a `app.plugins.cargador.ejecutar_tarea_programada(id, al_terminar)`, que activa `zc.programador` si hace falta (con su futuro, 3.4) y llama a su `ejecutar_tarea` exportada (11.0). La operación o la macro corren como cualquier otra (ventana de operaciones, F12, cola).
  - **Si no lo está**: el proceso que lanzó el Programador **no** se queda como instancia. Si `procesos.puede_salir_del_job()` (14.9) dice que puede salir del Job del Programador, suelta su instancia única, lanza la instancia real con `procesos.lanzar_independiente([<ejecutable>, "--modo-tarea"])` (fuera de cualquier Job: la persona la seguirá usando y no debe heredar los límites ni la prioridad de la tarea), espera a que la nueva tenga el mutex de la instancia única (60 s como máximo) y le deja la orden con `instancia_unica.dejar_orden_esperando("tarea", [id], tiempo_s=600)` (14.8), que vuelve cuando la nueva la ha recogido; entonces termina con 0 (1 si algo se agotó, con el motivo en el registro). Si no puede salir del Job, se queda como instancia en modo tarea, protegida por los ajustes de la tarea de Windows de abajo. La instancia en modo tarea arranca como siempre, pero **minimizada, sin quitar el foco a la ventana activa y sin anunciar nada** (ni «Iniciando zCommander» ni sonidos) salvo los errores, y ejecuta la tarea en cuanto la recibe.
  - **Autocierre**: la instancia que se abrió para la tarea se cierra sola al terminar **si la persona no la ha usado mientras** (la ventana queda «usada», `VentanaPrincipal.usada`, cuando se activa sin estar minimizada o cuando la persona ejecuta una orden por teclado, menú, paleta, barra o reenvío de otra instancia, es decir, por `ejecutar_orden` sin futuro; las órdenes que la tarea o una macro ejecutan con `ejecutar_orden_futuro` y las órdenes `tarea` del buzón no cuentan; abrir zCommander a mano mientras tanto solo trae al frente esta instancia, que entonces cuenta como usada y se queda abierta) **y no queda trabajo**: ninguna tarea en curso ni en la cola del motor, y ninguna orden `tarea` sin recoger en el buzón. El autocierre **no pregunta nada**: ignora `general.confirmar_salida` y no muestra «Hay N operaciones en curso» (si las hubiera, no se cierra). Si durante la tarea algo pidió una decisión a la persona, cuenta como usada y no se cierra.
  - **Ajustes de la tarea de Windows** (para que Windows nunca mate ni frene a zCommander): `ExecutionTimeLimit = PT0S` (sin límite), `MultipleInstancesPolicy = Parallel` (una segunda ejecución con la anterior abierta reenvía la orden por el buzón), `Priority = 4` (prioridad normal; la 7 por defecto es baja), `DisallowStartIfOnBatteries = false` y `StopIfGoingOnBatteries = false`.
  - **Decisiones sin preguntar**: la tarea guarda sus respuestas automáticas (política de conflictos y qué hacer ante un error: omitir, por defecto, o cancelar) y su operación se lanza con `operacion.respuestas_automaticas = RespuestasAutomaticas(...)` (14.6): el gestor de decisiones normal de la ventana responde con ellas sin mostrar nada y apunta cada decisión en el registro de la tarea. Lo que no tiene respuesta automática (por ejemplo, una contraseña) se pregunta con normalidad: la ventana minimizada parpadea en la barra de tareas y suena `aviso.pregunta`, y responder cuenta como usar zCommander (no se cierra solo).
  - Las macros y las entradas del menú de usuario se ejecutan igual, con `zc.ejecutar_orden_futuro` en el hilo de la interfaz, esperando el futuro de cada orden antes de seguir (3.4).
  - El resultado de cada ejecución va a `datos/registro.json` y, si `notificaciones`, a una notificación de Windows.
  Sin el Programador de Windows, solo se ejecutan con zCommander abierto.
- **Órdenes**: `zc.programador:tareas` «&Programador de tareas...» (—, global); `zc.programador:registro` «&Registro de ejecuciones...» (—, global).
- **Configuración**: `usar_windows` (bool, sí), `notificaciones` (bool, sí).
- **Sonidos**: `zc.programador:tarea_fin` (al abrir zCommander tras tareas ejecutadas, o al terminar una con zCommander abierto).
- **Activación**: `al_arrancar` (comprueba tareas pendientes y resultados). Permisos `ejecutar_programas`, `segundo_plano`.
- **Pruebas mínimas**: la tarea XML generada para el Programador de Windows (comparada con una esperada, con `TASK_LOGON_INTERACTIVE_TOKEN`, `StartWhenAvailable`, `ExecutionTimeLimit = PT0S`, `MultipleInstancesPolicy = Parallel`, `Priority = 4`, `DisallowStartIfOnBatteries = false` y `StopIfGoingOnBatteries = false`); `ejecutar_tarea` de una limpieza de prueba con respuestas automáticas no muestra ninguna pregunta, apunta sus decisiones y llama a `al_terminar` con 0; con la instancia abierta, `--tarea` deja la orden `tarea` en el buzón y sale; sin instancia, el proceso de la tarea lanza la instancia real (simulada) y sale cuando esta ha recogido la orden; la instancia en modo tarea arranca minimizada, ejecuta la tarea y se cierra sola al terminar sin preguntar (con `general.confirmar_salida` activa), pero no se cierra si en medio se ejecutó una orden, si queda otra tarea en la cola o en el buzón, o si se pidió una decisión.

### 11.25 Codificaciones y fines de línea (`zc.texto`, P2)

- **Qué hace**: detecta y convierte la codificación y los fines de línea de archivos de texto, uno o muchos.
- **Funciones**: columnas «Codificación» (UTF-8, UTF-8 con BOM, UTF-16, Windows-1252, OEM 850...) y «Fin de línea» (CRLF, LF, CR, mezclado); convertir los marcados a UTF-8 con o sin BOM y a CRLF o LF con vista previa del número de cambios; tabuladores a espacios y al revés; quitar espacios al final de línea; informe de caracteres no válidos; operación con deshacer (copia `.bak` o en `datos/deshacer/`, acción registrada con `zc.deshacer.registrar`).
- **Órdenes**: `zc.texto:convertir` «&Convertir la codificación y los fines de línea...» (—, global); `zc.texto:informe` «&Informe de caracteres no válidos» (—, global).
- **Columnas**: `codificacion`, `fin_linea`.
- **Configuración**: `destino` (opción `utf8`, `utf8_bom`; `utf8`), `fin_linea` (opción `crlf`, `lf`, `sin_cambio`; `sin_cambio`), `extensiones` (texto, `*.txt;*.md;*.csv;*.ini;*.bat;*.py;*.html;*.xml;*.json`), `copia_bak` (bool, sí).
- **Dependencias**: `codificacion.py` del núcleo.
- **Pruebas mínimas**: un archivo Windows-1252 con «año» pasa a UTF-8 con los mismos caracteres; uno con fines mezclados se informa «mezclado» y queda en CRLF; deshacer recupera los bytes originales.

## 12. Complemento «Nubes» (`zc.nubes`, bloque NU)

Según nubes.md y rclone.md, que justifican cada decisión; aquí van los contratos. Carpeta `plugins/nubes/`.

### 12.1 Qué hace

Cada cuenta de nube (Google Drive, OneDrive y SharePoint, Dropbox, Box, pCloud, Mega, S3 y compatibles, Backblaze B2, Yandex, Koofr, kDrive, Jottacloud, Internxt, Filen, Proton Drive e iCloud experimentales) y cada servidor WebDAV (Nextcloud, ownCloud, Synology, servidores propios) es una **unidad más del panel**: se lista, se entra, se ve, se edita, se copia (F5) y se mueve (F6) en los dos sentidos con el motor de la 1.x y sus conflictos, se renombra, se elimina (a la papelera de la nube si la tiene) y se busca. Además: copiar y mover de nube a nube en el servidor, sincronizar, emparejar en los dos sentidos, comprobar, deduplicar, vaciar la papelera, cuota, enlaces para compartir, carpetas cifradas, uniones, montar como letra (con WinFsp) y compartir en la red.

### 12.2 Motor rclone (`motor.py`, `cliente_rc.py`, `errores.py`)

- Un solo `rclone rcd` por sesión (y, como las tareas programadas corren dentro de la instancia normal, 11.24, nunca dos procesos con el mismo `rclone.conf`), arrancado bajo demanda (primer uso de una cuenta) o al iniciar (`arrancar = al_iniciar`; el manifiesto declara siempre `al_arrancar` y, con `al_usar`, `activar()` no arranca rcd, 11.0), con la línea de órdenes de rclone.md 2.1 **sin `--log-file`**: `data/bin/rclone/rclone.exe rcd --rc-addr 127.0.0.1:<puerto> --rc-serve --rc-job-expire-duration 10m --rc-server-write-timeout 24h --rc-server-read-timeout 24h --config <data>/config/rclone.conf --cache-dir <data>/cache/rclone --temp-dir <data>/temp --ask-password=false --log-level NOTICE --use-json-log`. El registro de rclone sale por `stderr` (abajo) y nunca hay un `rclone.log` en disco.
- **Puerto**: aleatorio, elegido en Python (enlazar a 0, leer y cerrar); si rclone no arranca por puerto ocupado, se reintenta con otro (3 veces). Entre cerrar y que rclone lo ocupe, otro proceso local podría quedarse con el puerto. Por eso, **antes de enviar ninguna petición** (ninguna lleva credenciales hasta entonces), se comprueba con `GetExtendedTcpTable` de `iphlpapi.dll` (`ctypes`, `TCP_TABLE_OWNER_PID_LISTENER`, IPv4) que el dueño del socket que escucha en `127.0.0.1:<puerto>` es el PID del hijo; si no lo es (o el puerto aún no escucha tras 10 s), se mata el hijo y se reintenta con otro puerto y **credenciales nuevas**. Solo después se hace la primera llamada (`core/pid`, que debe devolver el mismo PID).
- **Entorno del hijo** (nunca argumentos): `RCLONE_RC_USER` y `RCLONE_RC_PASS` aleatorios y **nuevos en cada intento de arranque** (`secrets.token_urlsafe(32)`; un reintento en otro puerto o un rcd arrancado de nuevo tras morir nunca reutiliza los anteriores), `RCLONE_CONFIG_PASS` (12.3), `RCLONE_TRANSFERS`, `RCLONE_BWLIMIT` (con horario) y los demás globales de la configuración.
- **Proceso**: con `app.core.procesos.popen` (14.9): ruta absoluta, `CREATE_NO_WINDOW`, `stdin=DEVNULL`, en el **Job Object** global de zCommander con `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (si zCommander muere, rclone y sus montajes mueren). Un hilo lee `stderr` (una línea JSON por mensaje, por `--use-json-log`) y pasa cada mensaje al registro de zCommander (`zcplugins.zc.nubes.rclone`) después de redactarlo con el filtro de `app/core/registro.py` (16: `token=`, `access_token`, `refresh_token`, `Authorization`, `RCLONE_*_PASS`...). Como no hay `--log-file`, no queda ningún registro de rclone sin redactar ni puede viajar en las copias (7.2).
- Al arrancar: `core/version` (si no es la del componente, aviso en el registro) y `config/paths` (que todo esté en `data`). Si muere, los proveedores lanzan `ErrorRed("El motor de nubes se ha detenido")`, suena `zc.nubes:motor_detenido` y el siguiente uso lo arranca, salvo que el componente `rclone` esté en mantenimiento (6.3): entonces el proveedor dice «El motor de nubes se está actualizando» y no lo arranca.
- Al salir (3.4): en la fase con veto, `puede_cerrar()` pregunta si hay unidades montadas con subidas pendientes (`vfs/queue`) o transferencias en marcha («Hay 3 subidas pendientes en la unidad N:. ¿Salir de todos modos?», con «&No salir» predeterminado); en `desactivar()`, `mount/unmountall`, `serve/stopall` y `core/quit` en un hilo, esperando su fin como mucho 5 s; si no responde, `TerminateProcess`.
- **Cliente**: `ClienteRC(puerto, usuario, contrasena)` con `llamar(ruta: str, **parametros) -> dict`, `llamar_asincrono(ruta, grupo, **parametros) -> int` (jobid), `esperar_trabajo(jobid, grupo, progreso: Callable[[int, int, float], None], cancelacion) -> dict` (consulta `job/status` y `core/stats` 4 veces por segundo como mucho; con cancelación, `job/stop`), `abrir_objeto(remoto, ruta, desde=0) -> BinaryIO` (GET con `Range` por `--rc-serve`). `http.client` con autenticación básica, POST con JSON, tiempos de espera.
- **Errores**: `errores.traducir(respuesta_o_excepcion) -> ErrorArchivos` con la tabla de rclone.md 3.8 (404 y «object not found» → `NoEncontrado`; 401/403 y `invalid_grant` → `ErrorAcceso` «La autorización de la cuenta caducó: Reconectar»; «quota exceeded» y «storage full» → `SinEspacio`; 429 y límites de velocidad → `ErrorRed` «El servicio pide esperar; se reintentará»; «failed to start auth webserver» → «Otro programa está usando el puerto de autorización 53682»). El texto original solo va al registro.
- **Componente**: `[requiere] componentes = ["rclone"]`; en `activar()` registra `zc.componentes.al_detener("rclone", detener)`, una función (no una orden del catálogo) que el actualizador de componentes llama desde un hilo (6.6): si no hay transferencias ni montajes, hace `core/quit`, espera a que el proceso termine y devuelve verdadero; si hay trabajo, devuelve falso.

### 12.3 Configuración cifrada de rclone

- `data/config/rclone.conf`, siempre cifrado por rclone (NaCl secretbox). La contraseña: 32 bytes aleatorios en base64, generada la primera vez y guardada en `secretos.dat` como `plugin:zc.nubes:rclone_config_pass` (DPAPI).
- **Cifrado antes de la primera cuenta**: antes de dar de alta ninguna cuenta (y antes de arrancar rcd con ese archivo), se cifra el archivo vacío con `rclone config encryption set --config <data>/config/rclone.conf`, con la contraseña escrita **dos veces** en la entrada estándar, una por línea (rclone 1.76 la pide y la confirma, comprobado en 21.3; nunca en los argumentos ni en el entorno de esa orden). Después se comprueba que el archivo empieza por `# Encrypted rclone configuration File`; si no, se borra, se aborta el alta y se explica «No se pudo cifrar la configuración de las nubes; no se ha guardado ninguna cuenta». Así ningún token llega nunca al disco ni a una copia en claro. La misma comprobación se hace en cada arranque de rcd: un `rclone.conf` con cuentas y sin la marca no se usa.
- Si DPAPI no puede descifrar (carpeta copiada a otro equipo): se aparta `rclone.conf` como `rclone.conf.ilegible-FECHA` y se explica «Las cuentas de nube están cifradas para otro usuario o equipo. Vuelva a añadirlas.».
- Nunca van al registro `config/get` ni `config/dump`.

### 12.4 Proveedores

- **`ProveedorRclone`** (`proveedor.py`, esquema `nube`): dirección `nube://<cuenta>/ruta`; `fs = "<cuenta>:"`. Correspondencia con `Proveedor` según nubes.md 5.4 (listar con `operations/list`, `info` con `operations/stat`, leer en flujo por `--rc-serve`, escribir con `operations/uploadfile` en flujo o `transferir`, `crear_carpeta` con `operations/mkdir`, eliminar con `operations/deletefile` y `operations/purge`, renombrar con `operations/movefile` o `sync/move`, `espacio_libre` con `operations/about`). `Capacidades` desde `operations/fsinfo`: `escribir`, `papelera`, `renombrar_barato` (Move o DirMove), `escritura_atomica` (verdadero en todos los servicios de objetos), `copia_servidor` (Copy). `servidor = "nube:<cuenta>"` (un carril por cuenta, y la identidad que el motor compara antes de mover, 14.5). `mostrar()` da «Google Drive de Ana:\Documentos». `mismo_volumen()` verdadero dentro de la misma cuenta (mover = `operations/movefile` en el servidor); el motor solo lo pregunta si origen y destino son de la misma cuenta. `transferir_lote` (14.5) con `sync/copy` (o `sync/move`) y la lista de archivos del filtro `--files-from` (parámetro `_filter` de la API remota), cuando los dos lados son rclone o el origen es local: un solo trabajo `_async` para miles de archivos pequeños, con `RCLONE_TRANSFERS` en paralelo. `suma(ruta, "sha256" | "md5" | "sha1")` con `operations/hashsum` cuando el servicio la tiene (verificación sin volver a leer, 14.5). Caché de listados de `cache_listados_s` (Ctrl+R la invalida).
- **Nombres duplicados** (Drive, Mega): si el listado trae dos entradas con el mismo nombre, el panel muestra la primera, anuncia «Hay 2 elementos con el mismo nombre: archivo.txt» (resultado) y ofrece «Buscar nombres duplicados» (12.6).
- **Google Docs**: tamaño desconocido (−1); se exportan con el formato de la cuenta (`docx`, `xlsx`, `pptx` por defecto); al editarlos se avisa de que se subirá un archivo nuevo.
- **`ProveedorWebDAV`** (`webdav.py`, esquemas `webdav` y `webdavs`, biblioteca estándar): `PROPFIND` (profundidad 1) para listar, `GET` con `Range`, `PUT`, `MKCOL`, `DELETE`, `MOVE` y `COPY` con `Overwrite: F`, cuota con `quota-available-bytes`. Contraseña en `plugin:zc.nubes:webdav:<id>:contrasena`. Certificados: verificación normal y, si falla, huella fijada como en FTPS (1.x §8.16). Rclone `webdav` queda como reserva para servidores raros.
- **Nextcloud y ownCloud, Login Flow v2** (`nextcloud.py`): `POST https://<servidor>/index.php/login/v2`, se abre o copia la URL `login`, y se consulta `poll` con su `token` cada 2 s (hasta 10 min) hasta recibir `server`, `loginName` y `appPassword`; la contraseña de aplicación se guarda en secretos y se crea la cuenta WebDAV `https://<servidor>/remote.php/dav/files/<usuario>/`.
- Ambos registran `resolver.registrar_unidades`: cada cuenta aparece en Alt+F1 y Alt+F2 con su nombre y su espacio.

### 12.5 Cuentas, catálogo de servicios y asistente

- `data/config/plugins/zc.nubes/cuentas.json` (sin secretos):

```json
{"version": 1, "cuentas": [
  {"id": "ana_drive", "nombre": "Google Drive de Ana", "servicio": "drive", "motor": "rclone",
   "carpeta_inicial": "/", "solo_lectura": false, "papelera": true,
   "limite_subida_kib": 0, "limite_bajada_kib": 0, "opciones": {"export_formats": "docx,xlsx,pptx", "chunk_size": "64M"},
   "client_id_propio": false, "cifrada_sobre": "", "union_de": []}
]}
```

- **Catálogo de servicios** (`servicios.json`, datos, no código): por servicio, `id`, nombre en español, tipo de rclone (o `webdav_nativo`), forma de autenticación (`oauth`, `contrasena`, `contrasena_2fa`, `clave_acceso`, `token_pegado`, `clave_api`, `login_flow_v2`), campos que se piden con su etiqueta y ayuda, opciones avanzadas con valor por defecto, nivel de rclone (los de nivel 4 se marcan «experimental» y se ocultan salvo `mostrar_experimentales`), enlaces de ayuda y avisos («Proton: integración no oficial», «iCloud: el acceso caduca a los 30 días», «Google: necesita un identificador de cliente propio»). Añadir una nube es añadir una ficha. Otros complementos pueden aportar fichas (`zc.nubes` lee `recursos/servicios/*.json` del paquete de los complementos que declaren `[recomienda] complementos = ["zc.nubes"]`). El catálogo propio está en `plugins/nubes/recursos/servicios.json`.
- **Asistente «Añadir una cuenta de nube»** (`ui/asistente.py`, orden `zc.nubes:anadir`): elegir servicio (lista con búsqueda) → nombre visible → los campos del servicio → autorización → comprobación (`operations/about` o listar la raíz) → resumen («Cuenta añadida: Google Drive de ana@ejemplo.com. 15 GB, 7 usados», esencial, suena `zc.nubes:conectar`) con «&Abrir ahora». Para cualquier pregunta de rclone (`config/create` sin interacción, rclone.md 5.1), el asistente presenta el control que toca según `Type`, `Exclusive`, `Examples` e `IsPassword`: casilla, lista, campo o contraseña con «Mostrar».
- **OAuth accesible** (`ui/oauth.py`; rclone.md 5.2 y nubes.md 10): `config/create` con `config_auth_no_browser=true` y `_async`; `config/oauthstatus` da `authUrl`; diálogo «Se abrirá el navegador para que inicie sesión en <servicio> y autorice a zCommander (rclone). Cuando termine, vuelva aquí: zCommander lo detectará solo.» con «Abrir el &navegador» (predeterminado), «&Copiar el enlace» y «&Cancelar» (`config/oauthstop`). Espera con un texto de estado de solo lectura, barra indeterminada con nombre y un anuncio cada 30 s («Sigue esperando la autorización»); suena `zc.nubes:oauth_espera` al empezar y `zc.nubes:oauth_ok` al terminar, que trae la ventana al frente. Tiempo máximo 10 minutos. **Pegar el token**: «&Autorizar desde otro equipo...» enseña la orden `rclone authorize "<tipo>"` para copiarla y un campo multilínea para pegar el resultado. 2FA (Mega, Proton, Internxt, iCloud): campo «Código de verificación» sin tiempo límite visual.
- **Guía de Google Drive** (`doc/es/google-drive.md`, orden `zc.nubes:guia_google`): paso a paso accesible para crear el identificador de cliente propio en Google Cloud Console (proyecto, API de Drive, pantalla de consentimiento Externa, ámbito `drive`, cliente «App de escritorio», **publicar** la aplicación para que el token no caduque a los 7 días), con los nombres exactos de los botones y la forma de llegar a ellos con el teclado; el asistente de Drive la ofrece y pide el id y el secreto (en secretos `plugin:zc.nubes:<cuenta>:client_secret`). No se registra una aplicación de zCommander (21.2.2).
- **Sin identificador propio** (Drive): el asistente explica que el identificador compartido de rclone se retira en 2026 (nubes.md 4.1) y ofrece, en este orden, «Crear mi &identificador (guía)», «Usar la carpeta de Google Drive para &escritorio» (solo si se detecta: la unidad o carpeta que configura Google Drive para escritorio, leída de `HKCU\Software\Google\DriveFS`; lleva el panel a esa carpeta y no crea ninguna cuenta de rclone) y «Seguir con el identificador de rclone mientras funcione» (se permite, con el aviso de que dejará de funcionar sin previo aviso). La detección se comprueba con Google Drive para escritorio al implementar.

### 12.6 Funciones y órdenes

| id | Etiqueta | Tecla | Ámbito | Qué hace (API de rclone) |
|---|---|---|---|---|
| `zc.nubes:cuentas` | Cuentas de &nube... | Alt+F11 | global | Ventana «Cuentas de nube» (12.7) |
| `zc.nubes:anadir` | &Añadir una cuenta de nube... | — | global | Asistente (12.5) |
| `zc.nubes:nextcloud` | Conectar &Nextcloud u ownCloud... | — | global | Asistente con Login Flow v2 |
| `zc.nubes:enlace` | Copiar un &enlace para compartir... | — | panel | `operations/publiclink` (con caducidad si el servicio la admite); «Enlace copiado» |
| `zc.nubes:quitar_enlace` | &Quitar el enlace compartido | — | panel | `publiclink` con `unlink` |
| `zc.nubes:vaciar_papelera` | &Vaciar la papelera de la nube... | — | global | `operations/cleanup` (confirmación con foco en Cancelar) |
| `zc.nubes:espacio` | Espacio de la n&ube | — | global | `operations/about`: usado, libre, papelera |
| `zc.nubes:sincronizar` | &Sincronizar con la nube... | — | global | `sync/sync` con `dryRun` primero y lista de cambios; `BackupDir` opcional |
| `zc.nubes:emparejar` | Emparejar carpetas (en los &dos sentidos)... | — | global | `sync/bisync` con asistente: primero `dryRun` y `resync`, `workdir` en `data/cache/rclone/bisync`, `maxDelete` 50 %, resumen de conflictos |
| `zc.nubes:comprobar` | Co&mprobar carpetas... | — | global | `operations/check` (tamaño y suma; con «Bajar para comparar», `download`); resultado en lista |
| `zc.nubes:duplicados` | Buscar nombres &duplicados... | — | global | `dedupe` por `core/command` con `list` y después la acción elegida (conservar el más nuevo, renombrar), siempre con simulación antes |
| `zc.nubes:cifrada` | Crear una carpeta &cifrada en la nube... | — | global | `config/create` de tipo `crypt` sobre una carpeta de una cuenta; contraseña y sal con «Generar» y aviso de que sin ellas no hay recuperación |
| `zc.nubes:union` | &Unir varias cuentas en una unidad... | — | global | `config/create` de tipo `union` (política de creación «más espacio libre») o `combine` (una carpeta por cuenta) |
| `zc.nubes:montar` | &Montar como letra de unidad... | — | global | `mount/mount` con `vfs_cache_mode=writes`, `network_mode`, `volname`; solo con WinFsp (12.8) |
| `zc.nubes:montajes` | Unidades &montadas... | — | global | `mount/listmounts`, «Desmontar» (avisa si `vfs/queue` tiene subidas pendientes) |
| `zc.nubes:servir` | Compartir en la &red... | — | global | `serve/start` con `webdav`, `sftp`, `http` o `dlna`; solo `127.0.0.1` salvo confirmación expresa (y aviso del cortafuegos); usuario y contraseña aleatorios; anuncia la dirección |
| `zc.nubes:servicios_activos` | Carpetas &compartidas por zCommander... | — | global | `serve/list` y «Dejar de compartir» |
| `zc.nubes:limites` | &Pausar o reanudar los límites de velocidad | — | global | `core/bwlimit` (`off` o el valor de la configuración) |
| `zc.nubes:reconectar` | Volver a &autorizar la cuenta... | — | global | `config/update` con `config_refresh_token` y el flujo OAuth (rclone.md 5.4) |
| `zc.nubes:guia_google` | &Guía para conectar Google Drive | — | global | Abre la guía en el visor de ayuda |

- Parar el motor para actualizar rclone no es una orden: es la función `al_detener` de 12.2.
- **Copiar y mover de nube a nube** no es una orden: F5 y F6 entre dos paneles de nube usan los ganchos `transferir_lote` y `transferir` (14.5): misma cuenta → copia o movimiento en el servidor; dos cuentas del mismo servicio → `ServerSideAcrossConfigs` si `copia_entre_cuentas`, con vuelta a la copia normal si falla; servicios distintos → rclone hace de puente en flujo, sin disco.
- Ver (F3) y editar (F4): `extraer_temporal` y, al guardar, el «actualizar desde temporal» de la 1.x.
- Buscar (Alt+F7): recorrido con `operations/list` y `recurse`; buscar por contenido avisa de que baja los archivos; en Drive, el proveedor de búsqueda `zc.nubes:drive_query` usa `backend/command` `query` (búsqueda en el servidor).
- **Progreso, pausa y cancelación**: cada transferencia y orden larga es una operación del motor de zCommander con `_async` y `_group: "zc-<id de operación>"`; progreso de `core/stats`; cancelar con `job/stopgroup`; la pausa no existe en rclone y se aplica entre archivos.

### 12.7 Ventana «Cuentas de nube» y configuración por cuenta

- Lista (Nombre, Servicio, Motor, Estado: «Conectada», «Volver a autorizar», «Sin comprobar», Espacio) con «&Abrir» (Intro: lleva el panel activo), «&Añadir...», «&Propiedades...», «&Reconectar...», «&Eliminar...» (desconecta y revoca si se puede, `config/delete`, borra sus secretos; confirmación con foco en Cancelar), «&Espacio», «&Cerrar».
- **Propiedades de una cuenta** (diálogo con pestañas, generado desde el catálogo del servicio): General (nombre visible, carpeta inicial, solo lectura, borrar a la papelera del servicio), Caché (`cache_listados_s` propio), Velocidad (límites de subida y bajada propios y horario, 12.9), Fragmentos (tamaño de fragmento validado por servicio: potencia de 2 en Drive, múltiplo de 320 KiB en OneDrive), Servicio (Google: formato de exportación de Docs, unidad compartida, accesos directos; OneDrive: personal, empresa o biblioteca de SharePoint; S3: proveedor, región, punto de acceso, clase de almacenamiento; pCloud: región), Avanzado (identificador de cliente propio, `copia_entre_cuentas`), Cifrado y uniones (si la cuenta es una carpeta cifrada o una unión: de qué cuentas sale).

### 12.8 Montar con WinFsp

Solo si WinFsp está instalado: clave `HKLM\SOFTWARE\WOW6432Node\WinFsp`, valor `InstallDir`, o `%ProgramFiles(x86)%\WinFsp\bin\winfsp-x64.dll` (se comprueba al implementar; rclone.md 4.8). Si no está, la orden explica qué es WinFsp, que necesita administrador y ofrece abrir su página de descarga (no lo instala). Diálogo: cuenta, «&Letra:» (libres o «automática»), «Modo de &caché:» (escrituras por defecto), «&Nombre del volumen:», casilla «Como unidad de &red». Aviso: zCommander no debe estar elevado (la letra no se vería). Suena `zc.nubes:montada`. Al salir con unidades montadas: «Hay 2 unidades de nube montadas; se desmontarán» (y si hay subidas pendientes, se espera o se pregunta).

### 12.9 Configuración del complemento

Página «Complementos > Nubes»:

| Clave | Tipo | Fábrica | Regla |
|---|---|---|---|
| `arrancar` | opción | `al_usar` | `al_usar`, `al_iniciar` |
| `transferencias` | entero | 4 | 1–32 |
| `limite_subida_kib` | entero | 0 | 0–10 000 000 (0 = sin límite) |
| `limite_bajada_kib` | entero | 0 | Ídem |
| `horario_limites` | texto | vacío | Formato de rclone (`08:00,512k 23:00,off`), editado con un diálogo de franjas (hora, subida, bajada) |
| `cache_listados_s` | entero | 30 | 0–3600 |
| `reintentos` | entero | 3 | 0–10 |
| `mostrar_experimentales` | bool | no | |
| `registro_detallado` | bool | no | Nivel INFO de rclone; nunca `--dump` |
| `papelera_por_defecto` | bool | sí | Para cuentas nuevas |
| `formato_docs` | texto | `docx,xlsx,pptx` | Para cuentas de Google nuevas |
| `copia_entre_cuentas` | bool | no | `ServerSideAcrossConfigs` |
| `servir_solo_local` | bool | sí | Compartir solo en 127.0.0.1 salvo confirmación |
| `aviso_winfsp_mostrado` | bool interna | no | Para el aviso de «Acerca de» (2.5) |

Secretos: `rclone_config_pass`, `<cuenta>:client_secret`, `webdav:<id>:contrasena`. Cambiar `transferencias` u `horario_limites` reinicia rcd cuando no hay transferencias (si las hay, se aplica al terminar y se dice).

### 12.10 Sonidos

`zc.nubes:conectar`, `zc.nubes:desconectar`, `zc.nubes:oauth_espera`, `zc.nubes:oauth_ok`, `zc.nubes:sincronizacion_fin`, `zc.nubes:montada`, `zc.nubes:motor_detenido`.

### 12.11 Seguridad

La de nubes.md 9: tokens solo en `rclone.conf` cifrado y secretos en `secretos.dat`; rcd solo en 127.0.0.1 con usuario y contraseña aleatorios, sin `--rc-no-auth`, sin `--rc-web-gui` y sin `--rc-allow-origin`; nada secreto en argumentos; Job Object; ruta absoluta al ejecutable; ámbitos mínimos (`drive` o `drive.readonly` si la cuenta es de solo lectura; `Files.ReadWrite.All` y `offline_access` en OneDrive); avisos de Proton e iCloud como integraciones no oficiales. Permisos del manifiesto: `red`, `secretos`, `ejecutar_programas`, `segundo_plano`.

### 12.12 Archivos

`plugins/nubes/`: `manifiesto.toml`, `__init__.py` (clase `Complemento`), `motor.py`, `cliente_rc.py`, `errores.py`, `proveedor.py`, `webdav.py`, `nextcloud.py`, `cuentas.py`, `recursos/servicios.json`, `operaciones.py` (`OperacionRclone` para sincronizar, emparejar, comprobar, deduplicar), `ui/asistente.py`, `ui/oauth.py`, `ui/cuentas.py`, `ui/propiedades.py`, `ui/sincronizar.py`, `ui/emparejar.py`, `ui/montar.py`, `ui/servir.py`, `ui/cifrada.py`, `ui/union.py`, `ui/franjas.py`, `doc/es/leeme.md`, `doc/es/google-drive.md`, `sonidos/`.

### 12.13 Pruebas mínimas (sin cuentas reales, rclone.md 10)

- Con `rclone.exe` de `data/bin` y un `rclone.conf` de prueba cifrado en una carpeta temporal: arrancar rcd en `127.0.0.1` con puerto aleatorio; `ProveedorRclone` sobre un remoto `memory` lista, crea carpeta, sube con `uploadfile`, lee con `Range`, mueve, borra y da `about` del local; copiar un archivo local de 50 MB a `memory` con `_async` da progreso que avanza y `job/stop` a medias lanza `Cancelado`; ruta inexistente da `NoEncontrado`.
- `rclone config encryption set` deja `rclone.conf` empezando por `# Encrypted rclone configuration File` antes de la primera cuenta, y un alta con un archivo sin esa marca se aborta sin guardar nada; arrancar sin `RCLONE_CONFIG_PASS` con `--ask-password=false` da un error claro; si el dueño del puerto según `GetExtendedTcpTable` no es el PID del hijo (otro proceso escuchando en el puerto elegido), no se envía ninguna petición y el reintento usa otro puerto y otras credenciales; no se crea ningún `rclone.log` y lo que rclone escribe en `stderr` llega redactado al registro.
- `transferir_lote` de 200 archivos pequeños de una carpeta temporal a `memory` hace un solo trabajo y conserva la lista de conflictos del análisis previo.
- Matar el proceso padre de prueba mata rclone (Job Object).
- WebDAV nativo contra `rclone serve webdav` de una carpeta temporal con usuario y contraseña: listar, subir, bajar, renombrar, borrar, cuota.
- Login Flow v2 contra un servidor `http.server` falso que responde 404 dos veces y después 200.
- OAuth contra un servidor OAuth falso (`auth_url` y `token_url` apuntando a él): `oauthstatus` da la URL, `oauthstop` cancela, y el alta termina con token.
- `crypt` sobre `memory`: los nombres salen cifrados en el remoto base y en claro en la cuenta cifrada.
- El asistente y la ventana de cuentas pasan `revisar_teclado`; el traductor de errores da los mensajes de 12.2.
- Montar (marca `winfsp`, solo si está instalado en la máquina de pruebas).

## 13. Complemento «NAS Synology» (`zc.synology`, bloque NS)

Según synology.md (los métodos y parámetros de cada API están en su sección 4; aquí van los contratos). Carpeta `plugins/synology/`. El NAS de referencia es un DS220+ con DSM 7.3 y el catálogo real de 841 API.

### 13.1 Principios

1. **Solo lectura por defecto**: cada NAS empieza en modo solo lectura; el cliente bloquea toda llamada que no esté en la lista blanca de lectura (`metodos_lectura.py`, compartida con el simulador). Para cambiar algo, la persona lo desactiva expresamente para ese NAS (13.6) y además confirma cada acción.
2. **Guiado por el catálogo**: al conectar, `SYNO.API.Info query=all` (en caché por servidor y versión de DSM); cada llamada usa `max(minVersion, min(versión preferida, maxVersion))` (hay API con `minVersion` 2, como `SYNO.DSM.Info`, `SYNO.DSM.Network` y `SYNO.FileStation.Upload`, que con la versión 1 darían el error 104); si la versión que el cliente sabe manejar queda fuera del rango del NAS, esa función se oculta con el motivo; lo que el NAS no tiene se oculta con el motivo («Necesita el paquete Hyper Backup»), nunca según el modelo.
3. **Cliente propio con la biblioteca estándar** (`http.client`, `ssl`, `json`, `uuid`, `hashlib`); POST con todo en el cuerpo (en la URL solo `api`, `version` y `method`); codificación JSON de cada parámetro cuando la API declara `requestFormat: "JSON"`.
4. **HTTPS con huella fijada**; nunca la contraseña por HTTP salvo al simulador en 127.0.0.1.
5. Áreas que el usuario de la cuenta no puede usar (error 105 o 160) se muestran como «Sin permiso con esta cuenta», sin fallar en cada pantalla.

### 13.2 Cliente (`cliente.py`, `sesion.py`, `errores.py`)

- `ClienteDSM(servidor: ServidorNAS, secretos, decisor)` con `conectar(cancelacion) -> InfoNAS`, `llamar(api: str, metodo: str, version: int | None = None, **parametros) -> dict`, `llamar_compuesta(peticiones: list[dict], modo="sequential") -> list[dict]` (`SYNO.Entry.Request`), `subir(ruta_carpeta, nombre, flujo, tamano, sobrescribir, progreso, cancelacion)`, `descargar(ruta, progreso, cancelacion) -> BinaryIO`, `tarea_fondo(api, parametros_start, progreso, cancelacion) -> dict` (patrón `start` → `taskid` → `status` → `stop`/`clean`) y `desconectar()` (`logout`; también al cerrar zCommander).
- **Sesión**: `SYNO.API.Auth` v7 `login` con `format=sid`, `enable_syno_token=yes`, `session=webui` y `device_id` guardado si lo hay; después `_sid` en el cuerpo y la cabecera `X-SYNO-TOKEN`. Con 106, 107 o 119, un solo reintento de inicio de sesión y de la petición. Con 150 (cambió la IP), nuevo inicio. Con 407 (IP bloqueada) **no** se reintenta: «El NAS ha bloqueado esta dirección tras varios intentos fallidos».
- **2FA**: con 403 o 406, el diálogo accesible «&Código de verificación:» (6 dígitos) con la casilla «&Recordar este equipo» (suena `zc.synology:otp`); se repite con `otp_code`, `enable_device_token=yes` y `device_name = "zCommander-<equipo>"`; el `device_id` se guarda en secretos. 404 es código incorrecto (se puede repetir, contando intentos). Si el `device_id` deja de valer, se borra y se vuelve a pedir el código. La aprobación por el móvil de Secure SignIn no se admite en la 2.0 (synology.md 2.2): se explica que hace falta una cuenta con código TOTP.
- **Confirmación de contraseña** de DSM para operaciones sensibles: `SYNO.Core.User.PasswordConfirm` `auth` → `SynoConfirmPWToken`, pedida con el `Decisor` cada vez.
- **HTTPS**: primera conexión con `CERT_NONE` solo para leer el certificado (`getpeercert(binary_form=True)`), mostrar su huella SHA-256 en un diálogo accesible (leída por grupos de 4, copiable) con «Aceptar y &recordar», «Aceptar &solo esta vez» y «&Cancelar»; después se compara la huella **antes** de enviar credenciales; si cambia, aviso claro y nueva confirmación (suena `red.huella`). Alternativas: CA propia en un archivo PEM o certificado válido (verificación normal).
- **Registro sin secretos**: se enmascaran `account`, `passwd`, `_sid`, `SynoToken`, `device_id`, `otp_code`, `passphrase` y `unzip_password`; nunca se registra el cuerpo de las respuestas de `SYNO.API.Auth`.
- **Errores**: `errores.mensaje(codigo, api) -> str` con las tablas de synology.md 3 en español; el 116 se traduce «Operación bloqueada: el servidor está en modo de solo lectura».
- **Tiempos**: conectar `tiempo_conexion_s`, cada petición `tiempo_peticion_s`; subidas y descargas sin límite total pero con progreso y cancelación.

### 13.3 Servidores guardados

`data/config/plugins/zc.synology/servidores.json`:

```json
{"version": 1, "servidores": [
  {"id": "casa", "nombre": "NAS de casa", "host": "192.168.1.50", "puerto": 5001, "https": true,
   "huella": "SHA256:...", "ca_propia": "", "usuario": "pepe", "solo_lectura": true,
   "recordar_contrasena": true, "demostracion": false}
]}
```

Secretos: `plugin:zc.synology:<id>:contrasena` y `plugin:zc.synology:<id>:device_id`. Orden `zc.synology:conectar` abre la lista de servidores con «&Conectar», «&Nuevo», «&Editar», «&Eliminar» y «NAS de &demostración».

### 13.4 Ventana del NAS (`ui/ventana.py`)

- Ventana no modal «NAS Synology: <nombre>» (`VentanaComplemento`). A la izquierda, la lista «&Áreas:» (lista nativa con las áreas de 13.5 que el NAS tiene); al elegir una con Intro o al moverse por ella tras 400 ms, a la derecha aparece su vista: una `ListaAccesible` con sus filas, un texto de solo lectura «&Detalle:» con el elemento elegido, y la fila de botones de acciones del área. F6 alterna entre la lista de áreas y la vista; Ctrl+R vuelve a leer el área; Escape cierra la ventana; F1 la ayuda del complemento.
- El **estado de la conexión** y el modo («Solo lectura» o «Cambios permitidos») van en el título de la ventana y en un texto de estado; con el modo de escritura, el título empieza por «CAMBIOS PERMITIDOS:» para que el lector lo diga al volver a la ventana.
- Las vistas se refrescan cada `refresco_estado_s` solo si están visibles y sin mover el foco ni anunciar las filas que no cambian; los cambios de estado relevantes (un disco pasa a aviso, un contenedor se para) se anuncian una vez, como esenciales si son avisos de salud (suena `zc.synology:aviso_salud`), si `anunciar_avisos` está activa.
- Las acciones que cambian algo están desactivadas en solo lectura, con la ayuda Ctrl+H «Desactive el modo solo lectura del NAS para usar esta acción».

### 13.5 Áreas

Cada área usa las API de synology.md 4 que existen en este NAS. «L» son acciones de lectura (siempre); «E» de escritura (con modo de escritura y confirmación).

| Área | API principales (synology.md) | Lista y detalle | Acciones |
|---|---|---|---|
| Estado y salud | `SYNO.Core.System` `info`, `SYNO.DSM.Info`, `SYNO.Core.System.Status`, `SystemHealth`, `Utilization`, `DSMNotify`, `Hardware.NeedReboot` (4.1) en una petición compuesta | Resumen: modelo, DSM y si falta la actualización de seguridad (aviso de synology.md 0.1 si es anterior a 7.3.2-86009 Update 2), tiempo encendido, temperatura, CPU, memoria, volúmenes, avisos | L: copiar el resumen |
| Almacenamiento y discos | `SYNO.Storage.CGI.Storage` `load_info`, `Core.Storage.Disk`, `Storage.CGI.Smart`, `Volume`, `Pool` (4.2) | Volúmenes, grupos y discos (modelo, temperatura, estado S.M.A.R.T.) | L: información S.M.A.R.T.; E: prueba S.M.A.R.T. rápida o completa, limpieza de datos |
| File Station | `SYNO.FileStation.*` (4.3) | Abre el NAS en el panel (13.7); además lista de tareas en segundo plano (`BackgroundTask`) y enlaces compartidos (`Sharing`) | L: abrir en el panel, ver tareas; E: crear, editar y borrar enlaces, limpiar tareas terminadas |
| Carpetas compartidas | `SYNO.Core.Share`, `Share.Permission` (4.4) | Carpetas con cifrado, papelera, cuota; permisos por usuario y grupo | E: cambiar permisos de un usuario o grupo |
| Usuarios y grupos | `SYNO.Core.User`, `Core.Group` (4.5) | Usuarios (activo, grupos, último acceso) y grupos | E: activar o desactivar un usuario, cambiar su contraseña (con confirmación de DSM) |
| Paquetes | `SYNO.Core.Package`, `Package.Control`, `Package.Server` (4.6) | Paquetes con versión y estado; los que tienen actualización | E: iniciar, parar, actualizar |
| Container Manager | `SYNO.Docker.Container`, `Container.Log`, `Container.Resource`, `Project`, `Image`, `Utils` (4.7) | Contenedores (estado, salud), proyectos, imágenes | L: registros (últimas 200 líneas en un texto de solo lectura), uso de recursos; E: iniciar, parar, reiniciar contenedor o proyecto |
| Synology Drive | `SYNO.SynologyDrive`, `Drive.Connection` (4.8) | Estado del servicio, equipos conectados | L |
| Synology Photos | `SYNO.Foto.*` (4.9) | Estado e indexación | E: volver a indexar |
| Tareas programadas | `SYNO.Core.TaskScheduler` (4.10) | Tareas con próxima ejecución e historial | E: ejecutar ahora, activar o desactivar |
| Registros y conexiones | `SYNO.Core.SyslogClient.Log`, `SyslogClient.Status`, `Core.CurrentConnection` (4.11) | Sucesos (fecha, nivel, texto) y conexiones actuales | L: filtrar, exportar a texto; E: expulsar una conexión |
| Notificaciones | `SYNO.Core.DSMNotify` (4.12) | Avisos de DSM | L |
| Red | `SYNO.DSM.Network`, `Core.Network.Interface`, `Core.DDNS.Record`, `Core.QuickConnect` (4.13) | Interfaces, DDNS, QuickConnect | L |
| Seguridad | `SYNO.Core.SecurityScan.Status`, `SecurityAdvisor.LoginActivity`, `Core.Security.AutoBlock.Rules`, `Core.Certificate.CRT` (4.14) | Asesor de seguridad, accesos, IP bloqueadas, certificados con caducidad | L: analizar con el Asesor (crea una tarea, no cambia nada); E: desbloquear una IP |
| Servicios | `SYNO.Core.FileServ.SMB`, `Core.Terminal`, `SYNO.WebDAV.Common` (4.15) | Estado de SMB, SSH, WebDAV y otros | E: activar o desactivar un servicio |
| Monitor de recursos | `SYNO.Core.System.Utilization` (4.17) | CPU, memoria, red y disco, refrescados cada `refresco_estado_s` | L: decir el estado (Ctrl+Mayús+T dentro de la ventana) |
| Actualizaciones | `SYNO.Core.Upgrade.Server` `check`, `Upgrade.Setting` (4.16) | Versión instalada y disponible | L: comprobar; E: descargar e instalar (doble confirmación como apagar) |
| Apagar y reiniciar | `SYNO.Core.System` v1 `shutdown` y `reboot` (4.16) | — | E: apagar o reiniciar con **doble confirmación**: la primera explica las consecuencias (foco en «&Cancelar»); la segunda exige escribir el nombre del NAS |

Las áreas no disponibles en el NAS (synology.md 4.23) no aparecen.

### 13.6 Modo solo lectura y modo de escritura

- Por NAS (`solo_lectura` en `servidores.json`), activo al crear el servidor.
- Desactivarlo: orden `zc.synology:modo_escritura` (casilla) o en las propiedades del servidor. Diálogo: «Va a permitir que zCommander cambie cosas en el NAS <nombre>: arrancar y parar paquetes y contenedores, cambiar permisos, usuarios y servicios, borrar y mover archivos. Cada acción pedirá confirmación. ¿Permitir cambios?» con «&Permitir cambios» y «&Cancelar» (predeterminado). Suena `zc.synology:cambios_permitidos`. Se puede elegir «Solo durante esta sesión» (por defecto) o «Hasta que lo vuelva a activar».
- Con el modo de escritura, cada acción **E** se confirma con un diálogo que dice exactamente qué se va a hacer («¿Parar el contenedor jellyfin?»); las de File Station usan los diálogos normales de zCommander (F5, F6, F8 ya confirman).
- En solo lectura, el proveedor `synology://` es de solo lectura (`Capacidades.escribir = False`) y cualquier método de escritura lanza `SoloLectura` con el mensaje del 116.

### 13.7 File Station como origen del panel

- `ProveedorSynology` (`proveedor.py`, esquema `synology`): dirección `synology://<id servidor>/<carpeta compartida>/ruta`; la raíz lista las carpetas compartidas (`List.list_share`). `listar` con `List.list` y `additional=["real_path","size","owner","time","perm","type"]` paginado; `info` con `List.getinfo`; leer con `Download.download` (`mode=open`) en flujo; escribir con `Upload.upload` (v3 con `overwrite`) en flujo multipart con el archivo como última parte; `crear_carpeta` con `CreateFolder`; `renombrar` con `Rename` (misma carpeta) o `CopyMove` con `remove_src` (otra carpeta); `eliminar` con `Delete` (respeta la papelera de la carpeta compartida: `Capacidades.papelera` si la tiene); `espacio_libre` del volumen; `suma(ruta, "md5")` con la tarea `MD5`. `servidor = "synology:<id>"`.
- Copiar o mover dentro del mismo NAS usa el gancho `transferir` con `CopyMove` como tarea en segundo plano (en el servidor, sin bajar ni subir); el progreso viene de `status`.
- Buscar (Alt+F7) en `synology://` usa el proveedor de búsqueda `zc.synology:filestation` con `SYNO.FileStation.Search` (y Universal Search si está, `SYNO.Finder.FileIndexing.Search`).
- Comprimir y extraer en el NAS: órdenes del complemento (`zc.synology:comprimir`, `zc.synology:extraer`) con `Compress` y `Extract` como tareas en segundo plano.
- El NAS aparece en el selector de unidades («NAS de casa»).

### 13.8 SSH opcional («Herramientas avanzadas por SSH»)

- Desactivado por defecto (`ssh_activado`). Con paramiko (ya presente), autenticación con clave pública del agente de OpenSSH de Windows; la contraseña de `sudo` se pide cada vez y nunca se guarda.
- Funciones: atributos S.M.A.R.T. en bruto (`sudo smartctl -a -d sat /dev/sataN`), registros largos de un contenedor (`docker logs --tail N`), `docker stats --no-stream`, `docker compose pull` y `up -d` de un proyecto, y rescate (reiniciar o parar un paquete con `synopkg` cuando la interfaz web no responde). Transporte alternativo `sudo synowebapi --exec api=... method=... version=...` con los mismos analizadores. Todas son de escritura salvo S.M.A.R.T., registros y estadísticas, y siguen las reglas de 13.6.
- Huella del servidor SSH como en SFTP (1.x §8.16).

### 13.9 Simulador DSM (`plugins/synology/simulador/`)

- **Para qué**: probar todo el complemento sin tocar el NAS real (pytest y pruebas manuales con NVDA) y ofrecer a la persona un **«NAS de demostración»** para aprender sin riesgo.
- **Estructura**: `servidor.py` (`http.server.ThreadingHTTPServer`, enrutado por `(api, method)`, arranque `SimuladorDSM(puerto=0, modo="lectura", https=False, datos=None).iniciar() -> url` y `.parar()`; también ejecutable como `python -I plugins/synology/simulador/servidor.py --puerto 55001 --modo simular`), `estado.py` (estado en memoria), `manejadores/<área>.py` (un módulo por área: `auth`, `sistema`, `almacenamiento`, `filestation`, `carpetas`, `usuarios`, `paquetes`, `docker`, `drive`, `photos`, `tareas`, `registros`, `notificaciones`, `red`, `seguridad`, `servicios`, `actualizaciones`), `datos/api_info.json` (copia del catálogo real `adjuntos/synology/api_info_5000.json`, hecha por `tools/copiar_catalogo_dsm.py`; el archivo de `adjuntos` no se distribuye), `datos/nas_ds220plus.json` (datos ficticios coherentes de synology.md 7.6, marcados como ficticios), `datos/credenciales_prueba.json` (cuentas inventadas: `demo`/`demo`, `prueba2fa` con código fijo `123456`, `lectura` sin privilegios).
- **Comportamiento** (synology.md 7.3): valida `api`, `version` y `method` contra el catálogo (101, 102, 103, 104); sesión con `sid` y `synotoken` aleatorios (119 y 105); escenario 2FA; tareas en segundo plano que avanzan un 10 % por segundo; inyección de fallos por `/__control` solo desde 127.0.0.1 (latencia, caducidad de sesión, bloqueo de IP, 502); HTTPS opcional con el certificado de prueba `tests/datos/dsm_falso_cert.pem` (generado una vez); File Station sobre un árbol en memoria o sobre una carpeta temporal.
- **Modos** (synology.md 7.4): `lectura` (escrituras rechazadas con 116), `simular` (responden con la forma real y apuntan en un diario `/__control/diario` sin cambiar nada) y `escritura` (cambian el estado en memoria). Lista blanca de lectura compartida con el cliente (`metodos_lectura.py`); todo lo demás cuenta como escritura.
- **NAS de demostración**: en la lista de servidores, «NAS de &demostración» arranca el simulador en un hilo en `127.0.0.1` (HTTP, puerto aleatorio) en el modo `demostracion_modo` (escritura en memoria por defecto) y conecta como `demo`. El cliente sigue empezando en solo lectura, así la persona practica también el cambio de modo. La ventana dice «NAS de demostración: los cambios se pierden al cerrar». Suena `zc.synology:demostracion_iniciada`.

### 13.10 Órdenes

| id | Etiqueta | Tecla | Ámbito |
|---|---|---|---|
| `zc.synology:estado` | &Estado del NAS | Ctrl+Mayús+F9 | global (abre la ventana en el área Estado; conecta si hace falta) |
| `zc.synology:conectar` | &Conectar con un NAS... | — | global |
| `zc.synology:desconectar` | &Desconectar del NAS | — | global |
| `zc.synology:abrir_archivos` | Abrir File Station en el &panel | — | global |
| `zc.synology:area` | Ir a un á&rea del NAS... | — | global (lista de áreas; Intro abre la ventana en ella) |
| `zc.synology:tareas_fondo` | &Tareas en segundo plano del NAS... | — | global |
| `zc.synology:enlace` | Crear un &enlace compartido... | — | panel (en `synology://`) |
| `zc.synology:comprimir` | Comprimir en el &NAS... | — | panel |
| `zc.synology:extraer` | E&xtraer en el NAS... | — | panel |
| `zc.synology:modo_escritura` | Permitir &cambios en el NAS | — | global (casilla) |
| `zc.synology:demostracion` | NAS de de&mostración | — | global |
| `zc.synology:ssh` | Herramientas avanzadas por &SSH... | — | global |
| `zc.synology:reiniciar` | &Reiniciar el NAS... | — | global |
| `zc.synology:apagar` | Apa&gar el NAS... | — | global |

### 13.11 Configuración

Página «Complementos > NAS Synology»: `tiempo_conexion_s` (entero 2–60, 10), `tiempo_peticion_s` (entero 5–300, 30), `refresco_estado_s` (entero 2–300, 10), `anunciar_avisos` (bool, sí), `aviso_temperatura_c` (entero 40–80, 55), `ssh_activado` (bool, no), `registro_detallado` (bool, no; nunca registra secretos), `demostracion_modo` (opción `escritura`, `simular`, `lectura`; `escritura`), `escritura_hasta` (opción `sesion`, `siempre`; `sesion`).

### 13.12 Sonidos

`zc.synology:conectado`, `zc.synology:desconectado`, `zc.synology:aviso_salud`, `zc.synology:tarea_fin`, `zc.synology:cambios_permitidos`, `zc.synology:demostracion_iniciada`, `zc.synology:otp`. Los ids de sonido y los de órdenes son espacios de nombres distintos, pero en los complementos de serie no se repiten para no confundir.

### 13.13 Pruebas mínimas (siempre contra el simulador, nunca contra el NAS real)

- Inicio de sesión correcto, incorrecto (400) y con 2FA (403 → código → `device_id` guardado → siguiente inicio sin código); 106 durante una petición produce un solo reintento; 407 no reintenta.
- La codificación JSON de parámetros cumple synology.md 1.2 (`name="plex"` va como `"\"plex\""`).
- En solo lectura, `Package.Control start` no llega a enviarse (bloqueo en el cliente) y en el simulador en modo `lectura` da 116 con el mensaje en español; en modo `simular` el diario registra la llamada y el estado no cambia.
- `ProveedorSynology` lista la raíz (carpetas compartidas), entra, sube y baja un archivo de 3 MB con nombre con tildes, copia en el servidor con progreso y cancela una tarea (`stop`).
- La huella fijada se rechaza si el simulador cambia de certificado.
- Cada área disponible devuelve filas con los datos ficticios; una API ausente del catálogo oculta su área.
- Apagar exige las dos confirmaciones (con diálogos simulados) y en el simulador en modo `escritura` deja el NAS falso «apagado».
- La ventana del NAS y los diálogos pasan `revisar_teclado`.
- El registro no contiene ningún valor de `passwd`, `_sid`, `SynoToken` ni `device_id` tras una sesión completa (prueba con `caplog`).

## 14. Cambios en el núcleo 1.x

### 14.1 Catálogo de órdenes

#### 14.1.1 Catálogo dinámico

- `app/ui/ordenes.py` conserva `Orden`, `MENUS`, `MENU_LADO`, `MENU_CONTEXTUAL`, `BARRA_TECLAS` y `SOLO_TECLA` de la 1.x. La tupla estática de la 1.x pasa a llamarse `CATALOGO_NUCLEO`.
- `Orden` gana tres campos con valor por defecto (no rompen nada): `nivel: str = "novato"` (10.11), `tecla_global: bool = False` (10.15) y `grabable: bool = True` (10.1; N2 pone `False` en las de consulta de 1.x §6.4, `macro_grabar`, `macro_ultima` y `cancelar`).
- Función nueva `catalogo() -> tuple[Orden, ...]`: `CATALOGO_NUCLEO` + órdenes de complementos registrados (de `app/plugins/registro.py`, con `bloque` = el `bloque` del manifiesto o `"COMPLEMENTO"` en los de la persona, `manejador="complementos_pl.ejecutar"`, `param` = id completo y, en las de tipo casilla, `estado="complementos_pl.estado"`, que devuelve la `casilla_defecto` del manifiesto mientras el complemento no está activado y su función `estado` después) + macros (`macro:<nombre>`, `bloque="PE"`, `manejador="personalizar_pe.ejecutar_macro"`, `param` = nombre). Devuelve siempre una **tupla nueva e inmutable** (una instantánea), que un hilo puede recorrer sin peligro. Se recalcula solo cuando cambia, con un contador de versión.
- **Fuente de las macros y aviso de cambio** (N2, en `ordenes.py`): `fijar_fuente_macros(funcion: Callable[[], list[tuple[str, bool, bool]]]) -> None` (la fija PE al arrancar su servicio de macros; cada tupla es nombre, en el menú «Mis órdenes» y en la paleta; sin fuente, no hay macros) y `catalogo_cambiado() -> None`, que sube el contador de versión y emite el evento del bus `al_cambiar_catalogo` (14.4). La llaman el registro de complementos al registrar o quitar marcadores y el servicio de macros al crear, renombrar o borrar una. **Solo se llama en el hilo de la interfaz** (el registro de marcadores y `CATALOGO` se recorren desde él: paleta, despachador; 3.10); desde un hilo se pasa con el planificador.
- **`CATALOGO` y `POR_ID` siguen existiendo con la misma forma de uso**, para no romper a nadie: `CATALOGO` es ahora el catálogo dinámico completo, un objeto de secuencia vivo (se recorre, se indexa y tiene `len` como la tupla de la 1.x, pero cada vez refleja `catalogo()`), y `POR_ID` un objeto de tipo diccionario vivo (`POR_ID[id]`, `in`, `get`, `items`) que se recalcula con el catálogo. Así siguen funcionando los usos de `POR_ID[...]` de `ventana_principal.py`, `barra_teclas.py`, `acciones/archivos.py`, `acciones/dialogos_f.py`, `dialogos/c_sumas.py`, `dialogos/f_mapa_teclas.py`, `services/sumas.py`, `services/operaciones/comprimir.py`, `tools/comprobar_menus.py`, `tools/generar_anexos.py` y las pruebas. `teclas_por_defecto()`, `ambitos()` y `fijas()` ya son funciones en la 1.x; pasan a calcularse sobre `catalogo()`.
- **Menús desde el catálogo vivo**: `MENUS`, `MENU_LADO` y `MENU_CONTEXTUAL` conservan la forma de la 1.x (tuplas de (etiqueta, lista), ids, `None` como separador y submenús anidados) y **solo llevan ids del núcleo que existen siempre** (las 45 nuevas en su sitio de 14.2, salvo `complemento_recargar`), así `POR_ID[elemento]` de cada texto sigue valiendo en `ventana_principal.py` y en `tools/comprobar_menus.py`. Lo dinámico lo añaden dos funciones nuevas que devuelven esa misma forma ya expandida con el catálogo vivo: `menus() -> tuple` (en «Co&mplementos», `complemento_recargar` en modo desarrollo, un separador y un submenú por complemento; «Mis ó&rdenes» con las macros de `menu = true`, solo si hay alguna; y las órdenes de complementos con `menu = "archivos"`, `"comandos"` o `"herramientas"` al final de su menú, tras un separador y por orden alfabético, 14.2) y `menu_contextual() -> tuple` (las de `menu = "contextual"` al final, tras un separador). Las letras de los submenús de Complementos las calcula `letras_submenus(nombres: Sequence[str], ocupadas: set[str]) -> list[str]`: para cada nombre, la primera de sus letras que no esté ocupada, en orden; si no queda ninguna, sin letra (y `comprobar_menus.py` lo avisa). La ventana y `comprobar_menus.py` construyen y comprueban los menús **solo** con `menus()` y `menu_contextual()`.
- **Modo desarrollo y complementos de serie fuera de la aplicación**: `fijar_modo_desarrollo(activo: bool) -> None` (lo llama `cargador.arrancar` con `complementos.modo_desarrollo` o `--desarrollo-complementos`; por defecto falso) decide si `catalogo()` incluye `complemento_recargar`. Las herramientas y las pruebas, que no arrancan el cargador, ven los complementos de serie con `app.plugins.registro.registrar_serie()` (3.13, 18.1).
- N2 revisa a la vez a todos los consumidores que tomaban una copia del catálogo al importar o que deben ver el catálogo completo (la paleta, `f_paleta.disponibles(catalogo=...)`, que hoy enlaza `ordenes.CATALOGO` al importarse; el mapa de teclas, `f_mapa_teclas.py`; los anexos; `tools/comprobar_menus.py`), para que lean el catálogo vivo. Ese cambio es de N2 aunque `f_paleta.py` y `f_mapa_teclas.py` sean después de PE (19.1).
- El catálogo cambia al instalar complementos y al crear o borrar macros (activar un complemento no lo cambia: sus órdenes ya estaban como marcadores): la ventana está suscrita a `al_cambiar_catalogo` y reconstruye despachador, menús y barras (como ya hace al cambiar `teclado.personalizadas`, 1.x §9.5).
- Una orden de un complemento inhabilitado o fallido sigue en el catálogo hasta reiniciar (para no mover los menús bajo los pies), pero avisa «El complemento X está inhabilitado» o «no se puede usar en esta sesión por errores».
- `complemento_recargar` solo está en el catálogo en modo desarrollo (3.12): `catalogo()` la incluye si se llamó a `fijar_modo_desarrollo(True)` (con `complementos.modo_desarrollo` activa o `--desarrollo-complementos`). Fuera de ese modo no existe, así que no es una excepción al objetivo 2 de 1.2.
- `tools/generar_provisionales.py` y la prueba `tests/test_n_arquitectura.py::test_ningun_manejador_provisional` (1.x §17) se amplían a los bloques de la 2.0 (18.1, 19.4). `generar_provisionales.py` registra la serie con `registrar_serie()`, **salta** las órdenes cuyo manejador es de complementos o de macros (`complementos_pl.ejecutar`, `complementos_pl.estado` y `personalizar_pe.ejecutar_macro`, que N2 escribe a mano: las dos primeras reales y la tercera provisional de PE) y añade a `EXTRA` la función `instalar` de cada módulo de acciones de bloque (14.9), que escribe como función sin efecto seguida de `instalar.provisional = True` (la prueba de provisionales lee esa marca, 18.1): `{"windows_g": ["instalar", "instalar_panel"], "complementos_pl": ["instalar"], "sonidos_so": ["instalar"], "componentes_co": ["instalar"], "actualizar_ac": ["instalar"], "copia_cs": ["instalar"], "red_rd": ["instalar"], "personalizar_pe": ["instalar", "ejecutar_macro"], "nvda_nv": ["instalar"]}`.

#### 14.1.2 Órdenes nuevas del núcleo

Menús: «Op» Opciones, «Ay» Ayuda, «Co» Comandos, «Cm» Complementos, «Ar» Archivos, «Lado» menú Izquierdo y Derecho, «—» solo tecla y paleta. La tabla copia `_ORDENES_2` de `app/ui/ordenes.py` (etiqueta con las letras que dejó `tools/comprobar_menus.py`, tecla, bloque, **manejador**, **estado** de las casillas, **ayuda** de Ctrl+H, **nivel** del perfil, 10.11, y si vale como **tecla global**, 10.15); si no coinciden, manda el código. Todas son `grabable` salvo `macro_grabar`, `macro_ultima` y las de consulta (14.1.1). (Ronda 4, precisión 4.)

| id | Etiqueta | Tecla | Ámbito | Menú | Bloque | Manejador | Estado | Nivel | Tecla global | Ayuda |
|---|---|---|---|---|---|---|---|---|---|---|
| `complementos` | Gestor de comp&lementos... | — | global | Cm, Op | PL | `complementos_pl.complementos` | — | intermedio | no | Lista de complementos: habilitar, configurar, actualizar e instalar. |
| `complemento_instalar` | &Instalar un complemento desde un archivo... | — | global | Cm | PL | `complementos_pl.complemento_instalar` | — | intermedio | no | Instala un complemento .zcplugin tras mostrar su resumen, su firma y sus permisos. |
| `complemento_recargar` | &Recargar el complemento en desarrollo | — | global | Cm (la orden solo existe en modo desarrollo, 14.1.1) | PL | `complementos_pl.complemento_recargar` | — | avanzado | no | Vuelve a cargar el complemento de la carpeta de desarrollo (solo en modo desarrollo). |
| `reiniciar` | &Reiniciar zCommander | — | global | Ay | PL | `complementos_pl.reiniciar` | — | novato | no | Cierra zCommander y lo vuelve a abrir. |
| `reiniciar_sin_complementos` | Reiniciar sin c&omplementos | — | global | Ay | PL | `complementos_pl.reiniciar_sin_complementos` | — | intermedio | no | Reinicia zCommander en modo seguro, sin cargar ningún complemento. |
| `sonidos_silenciar` | &Silenciar los sonidos (casilla) | Ctrl+F11 | global | Op > Sonidos | SO | `sonidos_so.sonidos_silenciar` | `sonidos_so.es_silenciado` | novato | sí | Activa o desactiva todos los sonidos de zCommander. |
| `sonidos_volumen_subir` | S&ubir el volumen de los sonidos | — | global | Op > Sonidos | SO | `sonidos_so.sonidos_volumen_subir` | — | novato | no | Sube 10 el volumen de los sonidos y lo anuncia. |
| `sonidos_volumen_bajar` | &Bajar el volumen de los sonidos | — | global | Op > Sonidos | SO | `sonidos_so.sonidos_volumen_bajar` | — | novato | no | Baja 10 el volumen de los sonidos y lo anuncia. |
| `sonidos_paquetes` | Pa&quetes de sonidos... | — | global | Op > Sonidos | SO | `sonidos_so.sonidos_paquetes` | — | intermedio | no | Crea, edita, exporta e importa paquetes de sonidos. |
| `mapa_sonidos` | Mapa de &sonidos... | — | global | Ay | SO | `sonidos_so.mapa_sonidos` | — | novato | no | Lista de todos los sonidos con cuándo suenan; se pueden escuchar. |
| `buscar_actualizaciones` | Buscar ac&tualizaciones... | — | global | Ay | AC | `actualizar_ac.buscar_actualizaciones` | — | novato | no | Comprueba si hay una versión nueva de zCommander. |
| `componentes` | Componentes e&xternos... | — | global | Op | CO | `componentes_co.componentes` | — | avanzado | no | rclone, libarchive, 7za y FFmpeg: versiones, actualizaciones y restaurar los originales. |
| `copia_crear` | &Crear una copia de seguridad... | — | global | Op > Copia de seguridad | CS | `copia_cs.copia_crear` | — | novato | no | Guarda en un archivo .zcbackup la configuración que elija. |
| `copia_restaurar` | &Restaurar una copia de seguridad... | — | global | Op > Copia de seguridad | CS | `copia_cs.copia_restaurar` | — | novato | no | Restaura una copia .zcbackup eligiendo qué partes. |
| `perfil_exportar` | E&xportar un perfil... | — | global | Op > Perfiles | CS | `copia_cs.perfil_exportar` | — | intermedio | no | Guarda preferencias, teclas, personalización y macros en un .zcperfil, sin contraseñas. |
| `perfil_importar` | Im&portar un perfil... | — | global | Op > Perfiles | CS | `copia_cs.perfil_importar` | — | intermedio | no | Aplica un .zcperfil eligiendo qué se aplica. |
| `red_raiz` | &Red | Ctrl+Mayús+K | global | Co > Red | RD | `red_rd.red_raiz` | — | intermedio | no | Muestra unidades de red, conexiones, servidores recientes y equipos de la red. |
| `red_buscar_equipos` | &Buscar equipos en la red | — | global | Co > Red | RD | `red_rd.red_buscar_equipos` | — | intermedio | no | Busca los equipos de la red local y los añade a la raíz Red. |
| `red_conectar_recurso` | Abrir un recurso &compartido con otra cuenta... | — | global | Co > Red | RD | `red_rd.red_conectar_recurso` | — | intermedio | no | Abre una carpeta compartida con otro usuario y contraseña. |
| `red_reconectar` | &Volver a conectar la unidad | — | panel | Co > Red | RD | `red_rd.red_reconectar` | — | intermedio | no | Vuelve a conectar la unidad de red del panel. |
| `red_contrasenas` | Contraseñas &guardadas de servidores... | — | global | Co > Red | RD | `red_rd.red_contrasenas` | — | intermedio | no | Lista y borra las credenciales de servidores guardadas en Windows. |
| `red_info` | &Información de la conexión | — | global | Co > Red | RD | `red_rd.red_info` | — | intermedio | no | Servidor, usuario, protocolo y cifrado de la conexión del panel. |
| `copiar_ruta_unc` | Copiar la ruta &UNC | — | panel | Ar > Portapapeles | RD | `red_rd.copiar_ruta_unc` | — | intermedio | no | Copia la ruta \\servidor\recurso de los elementos de una unidad de red. |
| `red_sesiones` | &Sesiones y archivos abiertos por la red... | — | global | Co > Red | RD | `red_rd.red_sesiones` | — | avanzado | no | Quién tiene abiertos archivos de este equipo por la red (pide permisos de administrador). |
| `red_cuadro_conectar` | Conectar con el cuadro de &Windows... | — | global | Co > Red | RD | `red_rd.red_cuadro_conectar` | — | avanzado | no | Abre el cuadro de Windows para conectar una unidad de red. |
| `red_cuadro_desconectar` | Desconectar con el c&uadro de Windows... | — | global | Co > Red | RD | `red_rd.red_cuadro_desconectar` | — | avanzado | no | Abre el cuadro de Windows para desconectar una unidad de red. |
| `macro_grabar` | &Grabar una macro (casilla) | Ctrl+Mayús+G | global | Op > Macros | PE | `personalizar_pe.macro_grabar` | `personalizar_pe.es_grabando` | intermedio | no | Empieza o termina la grabación de una macro con las órdenes que ejecute. |
| `macro_ultima` | Ejecutar la ú&ltima macro | Ctrl+Mayús+L | global | Op > Macros | PE | `personalizar_pe.macro_ultima` | — | intermedio | no | Repite la última macro ejecutada. |
| `macros` | &Macros... | — | global | Op > Macros | PE | `personalizar_pe.macros` | — | intermedio | no | Crea, edita, ejecuta, exporta e importa macros. |
| `columnas_carpeta` | Columnas &y vista de esta carpeta... | — | global (por lado) | Lado | PE | `personalizar_pe.columnas_carpeta` | — | intermedio | no | Conjunto de columnas y vista que se aplica a esta carpeta o a carpetas parecidas. |
| `orden_lectura` | &Orden de lectura de las columnas... | — | global | Op > Personalización | PE | `personalizar_pe.orden_lectura` | — | intermedio | no | Qué columnas se leen al moverse por las filas y en qué orden. |
| `personalizar_menus` | Personalizar &menús y barras... | — | global | Op > Personalización | PE | `personalizar_pe.personalizar_menus` | — | avanzado | no | Oculta elementos de menú, llena Mis órdenes, la barra de botones y la barra de teclas. |
| `barra_botones` | Mostrar la barra de &botones (casilla) | — | global | Op > Personalización | PE | `personalizar_pe.barra_botones` | `personalizar_pe.es_barra_botones` | intermedio | no | Muestra u oculta la barra de botones configurable. |
| `ir_barra_botones` | Ir a la barra de botones | Alt+Mayús+F11 | global | — | PE | `personalizar_pe.ir_barra_botones` | — | intermedio | no | Pone el foco en la barra de botones; Escape vuelve al panel. |
| `esquema_teclas` | &Esquema de teclas... | — | global | Op > Personalización | PE | `personalizar_pe.esquema_teclas` | — | avanzado | no | Teclas como Norton Commander, Total Commander, Far o el Explorador. |
| `alias` | &Alias de la línea de órdenes... | — | global | Op > Personalización | PE | `personalizar_pe.alias` | — | avanzado | no | Nombres cortos para órdenes largas de la línea de órdenes. |
| `linea_autocompletar` | Autocompletar | Ctrl+Espacio | línea | — | PE | `personalizar_pe.linea_autocompletar` | — | intermedio | no | Completa rutas, alias y órdenes internas en la línea de órdenes. |
| `espacios_trabajo` | &Espacios de trabajo... | Ctrl+Mayús+W | global | Co > Paneles | PE | `personalizar_pe.espacios_trabajo` | — | intermedio | no | Disposiciones de pestañas y paneles guardadas con nombre. |
| `espacio_guardar` | Guardar el espacio de &trabajo... | — | global | Co > Paneles | PE | `personalizar_pe.espacio_guardar` | — | intermedio | no | Guarda la disposición actual como espacio de trabajo. |
| `reglas` | &Reglas de anuncio, color y sonido... | — | global | Op > Personalización | PE | `personalizar_pe.reglas` | — | avanzado | no | Reglas que marcan con color, texto, sonido o anuncio los elementos que cumplen una condición. |
| `todas_las_ordenes` | &Ver todas las órdenes en los menús (casilla) | — | global | Op | PE | `personalizar_pe.todas_las_ordenes` | `personalizar_pe.es_todas_las_ordenes` | novato | no | Con los menús según el nivel, muestra también las órdenes de los otros niveles. |
| `perfil_guardar_propio` | &Guardar la configuración como perfil... | — | global | Op > Perfiles | PE | `personalizar_pe.perfil_guardar_propio` | — | intermedio | no | Guarda las preferencias y teclas actuales como un perfil con nombre. |
| `plantillas_archivo` | &Plantillas de archivo nuevo | — | global | Op > Personalización | PE | `personalizar_pe.plantillas_archivo` | — | intermedio | no | Abre la carpeta de las plantillas de Crear archivo nuevo. |
| `traer_al_frente` | Traer zCommander al frente | — | global | — (solo para teclas globales) | PE | `personalizar_pe.traer_al_frente` | — | novato | sí | Restaura y activa la ventana de zCommander (solo como tecla global). |
| `complemento_nvda` | Instalar el &complemento de zCommander para NVDA... | — | global | Ay | NV | `nvda_nv.complemento_nvda` | — | novato | no | Explica qué hace el complemento de NVDA y lo instala si lo acepta. |

Son **45 órdenes nuevas del núcleo**. Además `conectar_unidad_red` y `desconectar_unidad_red` cambian de bloque (de D a RD) y sus diálogos de la 1.x se amplían (9.4 y 9.5), y el submenú Opciones > Perfiles recoge la orden `perfil` de la 1.x.

#### 14.1.3 Teclas nuevas y comprobación de choques

Teclas que estaban libres en la 1.x (comprobado contra `data/docs/teclas.md` y `app/ui/ordenes.py`) y se usan en la 2.0, con su dueño:

- Núcleo: Ctrl+F11 (`sonidos_silenciar`), Ctrl+Mayús+K (`red_raiz`), Ctrl+Mayús+G (`macro_grabar`), Ctrl+Mayús+L (`macro_ultima`), Ctrl+Mayús+W (`espacios_trabajo`), Alt+Mayús+F11 (`ir_barra_botones`), Ctrl+Espacio en la línea de órdenes (`linea_autocompletar`; en el panel sigue siendo «Marcar sin mover», ámbitos distintos).
- Complementos de serie: Ctrl+Mayús+F (búsqueda instantánea), Ctrl+Mayús+J (salto rápido), Ctrl+Mayús+V (historial del portapapeles, ámbito panel), Ctrl+N (comentario, ámbito panel), Ctrl+F8 (papelera), Ctrl+F9 (lectura en voz), Alt+F11 (cuentas de nube), Mayús+F7 (duplicados), Ctrl+Mayús+F2 (etiquetas), Ctrl+Mayús+F3 (OCR), Ctrl+Mayús+F4 (hexadecimal), Ctrl+Mayús+F5 (reproducir), Ctrl+Mayús+F6 (convertir), Ctrl+Mayús+F7 (ocupación), Ctrl+Mayús+F8 (cifrar), Ctrl+Mayús+F9 (estado del NAS), Ctrl+Mayús+F11 (Git), Ctrl+Mayús+F12 (procesos), Alt+Mayús+F2, F3, F5, F6, F7 y F8 (reproductor).
- Quedan libres a propósito en el esquema Norton (el de fábrica), para la persona y los complementos de terceros: Ctrl+I (el esquema Far la usa para el filtro, 10.7), Ctrl+J, Ctrl+Y, Mayús+F11, Alt+0, Ctrl+Mayús+F1, Alt+Mayús+F1 y Alt+Mayús+F12.
- Reglas de la 1.x que se respetan (1.x §6.1): sin Ctrl+Alt+letra, sin Alt+letra (salvo los menús: la barra gana «Co&mplementos», Alt+M, y «Mis ó&rdenes», Alt+R, que ninguna orden usaba), sin Insert ni teclado numérico como única vía, sin Alt+F4 (por eso Alt+Mayús+F4 no se usa: Windows puede tratarlo como cerrar), sin teclas de edición en ámbito global (Ctrl+Mayús+V, X, Y, Z solo en ámbito panel).
- Prueba `tests/ui/test_n2_teclas.py`: ninguna tecla de fábrica se repite en ámbitos que se solapan (panel con global; línea con global) con el núcleo, los 27 complementos de serie y cada uno de los cuatro esquemas de `esquemas_teclas.py` (que crea N2, 10.7); ninguna es reservada ni fija; los complementos de terceros que choquen se quedan sin la tecla y el gestor lo dice. Se repite en la definición de terminado de PE y de cada bloque de complementos (19.4).

### 14.2 Menús

- Barra: Izquierdo (I), Archivos (A), Comandos (C), **Co&mplementos (M)**, Opciones (O), **Mis ó&rdenes (R)** (solo si tiene elementos), Derecho (D), Ayuda (U).
- «Complementos»: «Gestor de complementos...», «Instalar un complemento desde un archivo...», en modo desarrollo «Recargar el complemento en desarrollo», separador y un submenú por complemento con órdenes de menú `complementos` (por orden alfabético de nombre; cada submenú con la letra de `ordenes.letras_submenus`). Todo lo dinámico de este apartado lo devuelven `ordenes.menus()` y `ordenes.menu_contextual()` (14.1.1); `MENUS` solo tiene la parte fija.
- «Opciones» se reorganiza con submenús: Perfiles (perfil, guardar como perfil, exportar, importar), Personalización (esquema, menús y barras, barra de botones, orden de lectura, reglas, alias, plantillas), Macros, Copia de seguridad, Sonidos (silenciar, subir y bajar el volumen, paquetes); y entradas para Gestor de complementos, Componentes externos y Mostrar todas las órdenes.
- **Órdenes de complementos: un solo sitio** (cambiado el 9 de noviembre de 2026, a petición de la persona usuaria). Todas las órdenes de un complemento van juntas en su submenú del menú Complementos, también las que su manifiesto declara con `menu = "archivos"`, `"comandos"` o `"herramientas"` (valores que se siguen aceptando por compatibilidad con la API 1.0, `MENUS_DE_COMPLEMENTO` en `ordenes.py`). Los menús del núcleo no llevan órdenes de complementos: antes «Ver y editar en hexadecimal» quedaba debajo de Salir y Ocupación o Sincronización quedaban partidos entre dos menús. Los submenús de complemento se agrupan por categoría (`CATEGORIAS_COMPLEMENTOS`: Multimedia P1, Documentos y datos P2, Orden y limpieza del disco P3, Sistema y seguridad P4, Automatización P5, Nubes y NAS NU y NS, y «Otros complementos» para los de terceros), porque 27 submenús en un solo nivel no tienen letras de acceso para todos. Los menús del núcleo se reordenaron por grupos (Archivos termina en «Reiniciar zCommander» y Salir; «Reiniciar sin complementos» pasa a Complementos; «Mapa de teclas» y «Ver todas las órdenes en los menús» entran en Personalización; el gestor de complementos ya no se repite en Opciones; «Crear enlace» sigue en Herramientas). La prueba `tests/ui/test_n2_menus.py` comprueba que ninguna orden de la barra se repite y que Salir es lo último de Archivos.
- «Ayuda» añade Mapa de sonidos, Buscar actualizaciones e Instalar el complemento para NVDA (Reiniciar va en Archivos y Reiniciar sin complementos en Complementos).
- «Comandos > Red» se rehace con las órdenes de 14.1.2 más las de la 1.x (conexiones, desconectar).
- `MENU_CONTEXTUAL` admite órdenes de complementos con `menu = "contextual"` al final, tras un separador (solo las de ámbito panel; habilitadas según su `disponible` si el complemento está activo, o según `disponible_si` del manifiesto si no lo está, sin activarlo).
- Al abrir un menú, la ventana calcula el estado de las casillas solo del menú que se abre (`evento.GetMenu()`), no de todos como en la 1.x (`_al_abrir_menu`); las casillas de complementos sin activar muestran su `casilla_defecto` (3.4). Cambio de N2 en `ventana_principal.py`.
- La tecla de cada orden se muestra en los menús tras `\t` (1.x §6.3) si `vista.teclas_en_menus` está activa, también en Complementos, Mis órdenes y macros.

### 14.3 Configuración

`VERSION_ESQUEMA = 2`. Migración 1 → 2 (`MIGRACIONES[1]`, idempotente):

- `accesibilidad.sonidos` se borra **sin** trasladar su valor: `sonidos.activos` queda en su valor de fábrica (sí) para todos, porque en la 1.x el `false` de fábrica se guarda escrito en `settings.json` y no se distingue de una elección (4.5).
- `accesibilidad.tonos_progreso` se convierte en `sonidos.progreso` («cada_10» si era verdadera, «no» si falsa) y se elimina.
- `ftp.avisar_sin_cifrar` falso añade `ftp_sin_cifrar` a `general.no_preguntar`, y `operaciones.aviso_comprimido_mostrado` verdadero añade `comprimido_escritura` (10.12); las dos se eliminan.

Las secciones de los complementos no van en `settings.json` (3.6).

Claves nuevas del núcleo (todas con su etiqueta, ayuda y página en `descripciones_config.py`, con las páginas nuevas `SONIDOS`, `COMPRIMIDOS`, `ACTUALIZACIONES`, `PERSONALIZACION`, `CONFIRMACIONES` y `COMPLEMENTOS`):

| Clave | Tipo | Fábrica | Regla | Página |
|---|---|---|---|---|
| `complementos.inhabilitados` | lista | `[]` | ids | interna (gestor) |
| `complementos.permitir_sin_firma` | bool | sí | | Complementos |
| `complementos.fallos_maximos` | entero | 3 | 1–10 | Complementos |
| `complementos.modo_desarrollo` | bool | no | | Complementos |
| `complementos.auditoria` | bool | no | | Complementos |
| `complementos.confiados` | diccionario | `{}` | id → suma del paquete sin firma que la persona aceptó (`firma.suma_paquete`, 3.9) | interna |
| `sonidos.activos` | bool | sí | | Sonidos |
| `sonidos.volumen` | entero | 70 | 0–100 | Sonidos |
| `sonidos.paquete` | texto | `clasico` | id de paquete instalado | Sonidos |
| `sonidos.eventos` | diccionario | `{}` | id de evento → bool (solo diferencias con fábrica) | Sonidos (lista propia) |
| `sonidos.progreso` | opción | `no` | `no`, `cada_25`, `cada_10` | Sonidos |
| `sonidos.sustituir_anuncios` | bool | no | | Sonidos |
| `sonidos.intervalo_navegacion_ms` | entero | 40 | 0–500 | Sonidos |
| `sonidos.aviso_inicial_mostrado` | bool | no | | interna (aviso de 4.5) |
| `actualizaciones.comprobar` | bool | sí | | Actualizaciones |
| `actualizaciones.intervalo_horas` | entero | 24 | 1–720 | Actualizaciones |
| `actualizaciones.componentes_comprobar` | bool | sí | | Actualizaciones |
| `actualizaciones.componentes_intervalo_dias` | entero | 7 | 1–90 | Actualizaciones |
| `actualizaciones.complementos_comprobar` | bool | sí | | Actualizaciones |
| `copia.carpeta` | texto (carpeta) | vacío (= `data/backups`) | | General |
| `copia.conservar_automaticas` | entero | 5 | 1–50 | General |
| `copia.partes` | lista | todas salvo `registros` | ids de 7.2 | interna |
| `comprimidos.usar_libarchive` | bool | sí | | Comprimidos |
| `comprimidos.usar_7za` | bool | sí | | Comprimidos |
| `comprimidos.usar_7zip_instalado` | bool | sí | | Comprimidos |
| `comprimidos.ruta_7zip` | texto (carpeta) | vacío (detectar) | | Comprimidos |
| `comprimidos.metodo_zip` | opción | `deflate` | `deflate`, `zstd`, `almacenar` | Comprimidos |
| `comprimidos.flujos_como_carpeta` | bool | sí | | Comprimidos |
| `red.descubrir_al_entrar` | bool | sí | | Red |
| `red.descubrir_mdns` | bool | sí | | Red |
| `red.descubrir_dominio` | bool | sí | | Red |
| `red.tiempo_descubrir_s` | entero | 45 | 5–300 | Red |
| `red.reconectar_al_entrar` | bool | sí | | Red |
| `red.exigir_cifrado` | bool | no | | Red |
| `red.mostrar_otros_proveedores` | bool | sí | | Red |
| `teclado.esquema` | opción | `norton` | `norton`, `total_commander`, `far`, `explorador` | Personalización |
| `teclado.globales` | diccionario | `{}` | id de orden → tecla | Personalización (lista propia) |
| `teclado.globales_activas` | bool | no | | Personalización |
| `paneles.lectura` | lista | `[]` | ids de columna; vacía = el orden de las columnas por defecto (10.5) | Paneles (diálogo de orden de lectura) |
| `vista.barra_botones_visible` | bool | no | | Vista |
| `vista.teclas_en_menus` | bool | sí | | Vista |
| `vista.menus_por_nivel` | bool | no | | Personalización |
| `vista.columnas_por_carpeta` | bool | sí | | Personalización |
| `vista.recordar_vista_por_carpeta` | bool | no | | Personalización |
| `general.arrancar_con_windows` | bool | no | | General |
| `general.no_preguntar` | lista | `[]` | ids de confirmación silenciables | Confirmaciones (lista propia) |
| `linea.alias_activos` | bool | sí | | Personalización |
| `linea.autocompletar` | bool | sí | | Personalización |
| `macros.anunciar_pasos` | bool | no | | Personalización |
| `macros.pausa_ms` | entero | 0 | 0–5000 | Personalización |
| `macros.detener_en_error` | bool | sí | | Personalización |
| `reglas.activas` | bool | sí | | Personalización |
| `accesibilidad.silencio_nvda` | bool | sí | | Accesibilidad |
| `accesibilidad.complemento_nvda_ofrecido` | bool | no | | interna |

Son **54 claves nuevas del núcleo** (y desaparecen 4 por migración). Los complementos de serie añaden **131 claves `plugin.<id>.*`** (secciones 11 a 13). La tabla de perfiles de 1.x §2.2 gana dos filas: «Menús según el nivel» (`vista.menus_por_nivel`: Novato sí, Intermedio no, Avanzado no) y «Sonidos» (`sonidos.activos`: sí en los tres).

Archivos auxiliares nuevos en `data/config`, todos con `"version": 1` y leídos y escritos con `almacen_json.py`: `macros.json` (10.1), `perfiles/<nombre>.json` (10.2), `vistas_carpeta.json` (10.4), `menus.json` (10.6), `alias.json` (10.8), `espacios.json` (10.9), `reglas.json` (10.10), `paleta.json` (10.14), `red.json` (9.1), `estado_componentes.json` (6.3), `actualizaciones.json` (5.2), `plugins/<id>.json` y `plugins/<id>/` (3.6), `plugins/claves.json` (3.9). En `data/bin`: `componentes.json` y `linea_base.json` (6.2).

### 14.4 Bus de eventos (`app/services/eventos.py`, sin wx)

- `Bus` con `suscribir(nombre: str, funcion: Callable[..., None]) -> Callable[[], None]`, `emitir(nombre: str, **datos) -> None`, `emitir_sincrono(nombre: str, **datos) -> None`, `vaciar() -> None`, `fijar_planificador(planificador: Callable[[Callable[[], None]], None])` y `cerrar() -> None`. **Un solo bus por proceso**: `eventos.bus() -> Bus` lo crea la primera vez y devuelve siempre el mismo; así lo usan el código sin interfaz que no recibe la ventana (`ordenes.catalogo_cambiado`, el servicio de copias al emitir `al_restaurar`, la fachada `zc.eventos`), y `ventana.servicio("eventos")` devuelve ese mismo objeto (las pruebas lo sustituyen con `eventos.reiniciar()`). Como vive en `services` sin wx, `main.py` le fija el planificador (`wx.CallAfter`) justo después de crear `wx.App` (14.8).
- **Puente de la configuración**: `eventos.puentear_configuracion(config: Configuracion) -> Callable[[], None]` suscribe una función a `Configuracion.suscribir` (que avisa en el hilo que hizo el cambio) que reemite cada cambio como `al_cambiar_preferencia`; lo llama `main.py` tras cargar la configuración (paso 7 de 14.8).
  - `emitir` se puede llamar desde **cualquier hilo** y es **asíncrono**: encola la entrega y vuelve; los suscriptores se llaman **siempre en el hilo de la interfaz**, en el orden de emisión. Así `al_cambiar_preferencia` (que `Configuracion._notificar` avisa en el hilo que hizo el cambio, incluido el temporizador de `establecer_diferido`), `al_conectar` (hilos de listado), `al_copiar_portapapeles` y los eventos de los monitores de los complementos llegan todos al hilo de la interfaz. Sin planificador (pruebas), se entrega en el acto en el hilo que emite.
  - `emitir_sincrono` solo se llama en el hilo de la interfaz y llama a los suscriptores en el acto, antes de volver. Lo usa `al_cerrar` (3.4), para que llegue antes de `desactivar()` y no se quede en la cola de `wx.CallAfter` cuando el bucle de eventos termina.
  - `vaciar()`: solo en el hilo de la interfaz; entrega en el acto, en orden, todo lo que estaba en la cola (lo publicado con el planificador que aún no ha corrido se marca como entregado y no se repite). La ventana lo llama al cerrar antes de `al_cerrar` (3.4, paso 4).
  - `cerrar()`: a partir de ahí `emitir` descarta (y registra) lo que llegue, y las entregas pendientes no se hacen. La ventana lo llama al salir, tras `desactivar()` de los complementos (3.4, paso 7).
  - Cada suscriptor se llama protegido (una excepción se registra y no corta a los demás); los de complementos pasan además por `estado.llamar_protegido` y la medición de tiempo (3.8).
  - **El bus solo informa**: lo que tiene que ocurrir en un orden preciso respecto a la orden o al diálogo (grabar un paso de macro, 10.1) va por llamada directa, nunca por el bus.
- Eventos del núcleo (datos entre paréntesis): `al_arrancar` (tras mostrar la ventana), `al_cerrar` (síncrono), `al_cambiar_carpeta` (`panel`, `proveedor`, `ruta`), `al_cambiar_cursor` (`panel`, `entrada`; tras 300 ms sin moverse), `al_cambiar_marcas` (`panel`, `cuantas`), `al_activar_panel` (`lado`), `al_empezar_operacion` (`operacion`, con `operacion.orden_origen`, 10.1), `al_terminar_operacion` (`operacion`), `al_cambiar_preferencia` (`clave`, `anterior`, `nuevo`), `al_conectar` y `al_desconectar` (`proveedor`), `al_ejecutar_orden` (`id`, `argumento`; **se emite** justo antes de ejecutar la orden, pero, como la entrega es asíncrona, los suscriptores lo reciben después), `al_terminar_orden` (`id`, `argumento`, `ok: bool`; después), `al_copiar_portapapeles` (`tipo`), `al_restaurar` (`partes: list[str]`; tras restaurar partes «En el momento», 7.6), `al_cambiar_catalogo` (sin datos; lo emite `ordenes.catalogo_cambiado`, 14.1.1, y la ventana reconstruye despachador, menús y barras).
- **Contrato `recargar()`**: cada servicio que guarda un archivo de una parte de copia «En el momento» (7.2) tiene `recargar() -> None` (vuelve a leer su archivo y avisa a su interfaz) y se suscribe a `al_restaurar` con las partes que le tocan. N2 suscribe los de la 1.x (favoritos, menú de usuario, asociaciones, plantillas de renombrado y búsquedas guardadas, de la parte `personalizacion`); PE, los suyos (menús, vistas por carpeta, reglas y alias de `personalizacion`, y las macros); SO, los paquetes de sonidos propios. Nadie más: los datos de Nubes y del NAS están en la parte `conexiones`, que se aplica al reiniciar.
- Los usan: complementos (`zc.eventos.suscribir`), macros (fin de pasos con `al_terminar_operacion`; la grabación no, 10.1), paleta (frecuencias con `al_terminar_orden`), reglas, copias (`al_restaurar`), la ventana (`al_cambiar_catalogo`) y la Vista Información.

### 14.5 Ganchos del sistema de archivos virtual

En `app/services/vfs/base.py` (bloque N2), todos opcionales y compatibles con los proveedores de la 1.x:

- `Capacidades` gana `renombrar_barato: bool = True` (si renombrar es caro, como en S3, el motor no usa temporales con renombrado final), `escritura_atomica: bool = False` (la subida solo aparece completa al terminar: el motor escribe directamente con el nombre final), `copia_servidor: bool = False` (el proveedor puede copiar dentro de sí mismo sin pasar los bytes por zCommander) y `nombres_duplicados: bool = False` (puede haber dos entradas con el mismo nombre).
- `Proveedor.transferir(origen: Proveedor, ruta_origen: str, ruta_destino: str, progreso: Callable[[int, int], None], cancelacion) -> bool`: si devuelve `True`, el proveedor de destino hizo la copia por su cuenta (copia en el servidor, subida por fragmentos con reintentos, nube a nube) e informó del progreso; si devuelve `False` (por defecto), el motor copia por bloques como en la 1.x.
- `Proveedor.transferir_lote(origen: Proveedor, pares: Sequence[tuple[str, str]], mover: bool, progreso: Callable[[int, int], None], cancelacion) -> list[ResultadoPar] | None`: copia (o mueve) de una vez una lista de archivos ya decidida por el análisis del motor (conflictos resueltos, destinos renombrados incluidos). `None` (por defecto) = no lo admite y el motor sigue archivo a archivo; si no, un `ResultadoPar` por par (`@dataclass(frozen=True) ResultadoPar(origen: str, destino: str, ok: bool, error: ErrorArchivos | None = None)`, definido por N2 en `vfs/base.py` y re-exportado por la API, 3.7), con lo que el motor arma fallidos, omitidos y deshacer como en la 1.x. El motor lo usa cuando el destino lo admite para ese origen (NU: ambos lados rclone, o local → rclone).
- `Proveedor.mismo_volumen(ruta_a, ruta_b)` ya existe en la 1.x y `OperacionCopiar` ya lo llama para cualquier proveedor (`copiar.py`, al mover y al comprobar el espacio; la base devuelve `False`). Lo que cambia: el motor **solo** lo pregunta si origen y destino son el mismo volumen lógico, es decir, `clave_carril(origen, ruta_a) == clave_carril(destino, ruta_b)` (mismo esquema y misma identidad de servidor o cuenta: `nube:<cuenta>`, `synology:<id>`), porque las rutas de nube, FTP y SFTP son relativas («/x») y el proveedor de origen no sabe nada del de destino. Los proveedores nuevos solo tienen que sobrescribir `mismo_volumen` y dar en `servidor` su identidad completa. Prueba de N2: dos proveedores falsos del mismo esquema con distinta cuenta nunca mueven con `renombrar`.
- `Operacion.orden_origen: str = ""` (10.1; lo pone `ContextoOrden.lanzar`, o el parámetro `orden_origen` de `ventana.lanzar_operacion` en las llamadas directas) y `OperacionCopiar.pares_hechos() -> list[tuple[str, str]]`: los pares origen → destino que de verdad se copiaron o movieron, con los nombres finales tras los conflictos (lo usan las notas, 11.14).
- `Proveedor.suma(ruta: str, algoritmo: str) -> str | None`: suma que el origen ya conoce (rclone, File Station); la verificación del motor (1.x §9.6) la usa si los dos lados la dan con el mismo algoritmo, en lugar de volver a leer.
- `Proveedor.abrir_escritura(ruta, tamano: int = -1)`: el tamaño previsto (rclone y File Station lo necesitan para subir en flujo). N2 cambia la firma en `base.py`, `local.py`, `zip.py`, `ftp.py`, `sftp.py` y `resultados.py` (todos los que la definen en la 1.x).
- `UnidadVirtual(texto, direccion, descripcion="")` pasa a `vfs/base.py` (la re-exporta la API) y `resolver.registrar_unidades(funcion: Callable[[], list[UnidadVirtual]])` da entradas para el selector de unidades (nubes, NAS, Red, Papelera); `resolver.unidades_virtuales()` las junta con las fijas de los manifiestos (3.3). El selector (`dialogos/f_unidades.py`, N2) muestra primero las fijas y las de la 1.x, y añade las dinámicas cuando llegan de su hilo.
- `resolver.abrir_comprimido`: si la fábrica lanza `NoAdmitido`, Intro abre el archivo con su asociación (para comprobaciones por contenido, como SQLite).
- `OperacionCopiar` (`app/services/operaciones/copiar.py`) aplica estos ganchos en ese orden: `transferir_lote` (para todos los archivos del plan, tras el análisis); si no, por archivo, `transferir`; si no, `escritura_atomica`; si no, la copia de la 1.x. El análisis, la lista de conflictos, la marca de la Web y el deshacer no cambian.

### 14.6 Decisiones: acciones extra

Las operaciones de la 1.x no cambian: `Decisor.preguntar_error(operacion, pregunta) -> AccionError` sigue devolviendo `REINTENTAR`, `OMITIR` o `CANCELAR` (`AccionError` es un `StrEnum` y no puede llevar un id). Lo nuevo vive en la interfaz:

- `PreguntaError` (en `modelo.py`) gana `codigo_windows: int = 0` (el `winerror` del `OSError`) y `excepcion: BaseException | None = None`, que rellenan `copiar.py`, `eliminar.py` y las demás operaciones del núcleo al preguntar. Así `aplica()` decide «archivo en uso» por el código (32 o 33), nunca leyendo el mensaje en español.
- El `GestorDecisiones` (`app/ui/decisiones.py`) pide a `app.plugins.registro.acciones_error_aplicables(pregunta) -> list[AccionAplicable]` (`AccionAplicable(id: str, etiqueta: str, funcion: Callable[[PreguntaError], AccionError | None])`, 3.13; N2 inyecta esta función en la ventana) las acciones que aplican, y las muestra como botones adicionales del diálogo de error, tras «Reintentar». Aplican según el filtro `codigos_windows` del manifiesto sin activar el complemento y, si ya está activo, además según su `aplica()`; la `funcion` de una acción de un complemento sin activar pide la activación, muestra «Cargando el complemento...» con los botones inhabilitados y llama a la función real cuando el futuro se resuelve (3.4). Si la persona elige una, el gestor llama a su función en el hilo de la interfaz (el diálogo ya está en él), protegida con `estado.llamar_protegido`, y traduce el resultado: `REINTENTAR`, `OMITIR` o `CANCELAR` se devuelven a la operación tal cual; `None` vuelve a mostrar la misma pregunta. Es el enganche del complemento de procesos (11.9).
- El protocolo `Decisor` gana `pedir_credenciales(titulo, texto, usuario="", operacion=None) -> tuple[str, str, bool] | None` (9.4), implementado en `ui/decisiones.py` y en `api.pruebas.DecisorFalso`.
- **Respuestas automáticas** (para las tareas programadas, 11.24; no hay decisor aparte ni modo sin ventana): `modelo.py` gana `@dataclass(frozen=True) RespuestasAutomaticas(conflicto: Politica, error: AccionError = AccionError.OMITIR, registro: logging.Logger | None = None)` y `Operacion.respuestas_automaticas: RespuestasAutomaticas | None = None`. El `GestorDecisiones` normal, antes de preguntar nada de una operación que las tiene, responde con ellas (conflictos según `conflicto`, errores con `error`) sin mostrar ningún diálogo ni anunciar, y apunta cada decisión en `registro`. Lo que no tiene respuesta automática (`elegir`, `pedir_texto`, `pedir_credenciales`) se pregunta como siempre. El `DecisorNoInteractivo` y `no_interactivo.py` del borrador 2 desaparecen.

### 14.7 Visor interno

`app/ui/ventanas/visor.py` acepta un `Documento` (3.7) además de un archivo: muestra el texto de las secciones con su título y, si hay páginas, marcas «Página N». Teclas nuevas del visor (propias de su ventana): F6 sección siguiente, Mayús+F6 sección anterior, Ctrl+L lista de secciones (diálogo con búsqueda; Intro va), Ctrl+P ir a una página; la barra de estado dice «Sección 3 de 12: Introducción». `data/docs/teclas.md` y `tools/comprobar_teclas.py` las recogen. La Vista rápida usa el mismo `Documento` cuando un visor de complemento lo da.

### 14.8 Argumentos de `main.py`

`main.py` es de N2 y ningún bloque lo edita después: N2 deja el análisis de **todos** los argumentos con `argparse` (la 1.x descarta todo lo que empieza por `--` al reenviar archivos, `main.py` l. 137; con `argparse`, `--tarea <id>` ya no se confunde con un archivo) y las llamadas a estos puntos de entrada, con su firma, que N2 deja provisionales en el módulo del bloque dueño (lista de 19.1) y cada bloque implementa:

| Argumento o paso | Punto de entrada (módulo, firma y retorno) | Provisional de N2 | Dueño |
|---|---|---|---|
| Restauración pendiente | `app.services.copia.pendiente.aplicar_pendiente(ruta_datos: Path, preguntar: Callable[[InfoPendiente], str] \| None) -> ResultadoRestauracion \| None` (7.6); tras actualizar, `consultar_pendiente(ruta_datos: Path) -> InfoPendiente \| None` y `decidir_pendiente(ruta_datos: Path, decision: str) -> None` en el paso 11 | `aplicar_pendiente` y `consultar_pendiente` devuelven `None`; `decidir_pendiente` no hace nada | CS |
| Componentes pendientes y diario | `app.services.componentes.integrar.aplicar_pendientes(ruta_datos: Path) -> list[str]`: los mensajes que hay que anunciar tras mostrar la ventana («rclone se actualizó a 1.77.0», «La versión 1.77.0 de rclone no funcionó y se ha vuelto a la 1.76.0») | Lista vacía | CO |
| Entrantes de una actualización | `app.services.componentes.integrar.integrar_entrante(ruta_datos: Path) -> ResumenIntegracion \| None` (6.7), con `@dataclass(frozen=True) ResumenIntegracion(conservados: list[str], instalados: list[str], revertidos: list[str], mensaje: str)` en el mismo módulo (sin wx) | Devuelve `None` | CO |
| Confirmar lo integrado | `app.services.componentes.integrar.confirmar_integracion() -> None` (6.7), que llama `actualizador.al_arrancar` | No hace nada | CO |
| WAV propios de la 1.x | `app.services.sonidos.paquetes.migrar_1x(ruta_datos: Path, config: Configuracion) -> bool` (4.5) | Devuelve falso | SO |
| Marca de inicio para el actualizador | `app.services.actualizador.marcar_inicio(tras_actualizar: bool) -> None`: escribe `iniciado <versión> <PID>` (5.2) | No hace nada | AC |
| `--sin-complementos`, `--desarrollo-complementos <carpeta>` y los complementos en general | `app.plugins.cargador.arrancar(config: Configuracion, modo_seguro: bool, desarrollo: Path \| None) -> Cargador` (llama a `ordenes.fijar_modo_desarrollo`, 14.1.1) | Funcional (3.4) | N2; PL lo completa |
| `--comprobar-arranque [--complemento-prueba <carpeta>]` | `app.plugins.prueba.comprobar_complemento(carpeta: Path) -> int` (carga ese complemento y ejecuta la orden de su campo `prueba`, 3.3; 0 si funciona) | Devuelve 0 | PL |
| `--tras-actualizar` (lo pone el `.bat` del actualizador) | `app.services.actualizador.al_arrancar(tras_actualizar: bool) -> None` (5.4): escribe `ok` tras mostrar la ventana | No hace nada | AC |
| `--probar-componente <id> [--carpeta <ruta>]` | `app.services.componentes.prueba.probar_componente(id: str, carpeta: Path \| None) -> int` (6.2), que para libarchive llama a `app.services.libarchive.prueba.probar(carpeta: Path \| None) -> int` | Devuelven 1 | CO (CM para libarchive) |
| `--tarea <id>` | Siempre en la instancia normal (11.24). Con otra instancia abierta: `instancia_unica.dejar_orden("tarea", [id])` y salir. Sin ella: lanzar la instancia real con `--modo-tarea` y entregarle la orden (paso 4), o quedarse como instancia en modo tarea si no puede salir del Job. La ventana atiende cada orden `tarea` del buzón con `app.plugins.cargador.ejecutar_tarea_programada(id: str, al_terminar: Callable[[int], None]) -> None` [interfaz], que activa `zc.programador` y llama a su `ejecutar_tarea` (11.0) | Funcional (reenvío, lanzamiento, modo tarea, autocierre y llamada); `ejecutar_tarea_programada` llama a `al_terminar(2)` si `zc.programador` no exporta la función | N2; P5 (la tarea) |
| `--modo-tarea` | Lo pone el proceso de una tarea al lanzar la instancia real: arranca en modo tarea (minimizada, sin quitar el foco, sin anuncios salvo errores, con autocierre; 11.24) y espera la orden `tarea` por el buzón | Funcional | N2 |
| `--al-iniciar-sesion` | Lo atiende la ventana (`ArranqueInfo.modo = "sesion"`): arranca minimizada y sin anuncios hasta recibir el foco (10.17) | Funcional | N2; PE escribe el valor de `Run` |
| `--esperar-pid <pid>` | Lo pone «Reiniciar» (y «Reiniciar sin complementos», con `--sin-complementos`), lanzado con `procesos.lanzar_independiente` (14.9): ver el paso 2 | Funcional | N2 |

`app/core/instancia_unica.py` (N2): `ORDENES_VALIDAS` gana `"tarea"`; una orden `tarea` caduca a los 600 s (`MAX_EDAD_TAREA`), no a los 60 s de las demás, porque la instancia que la recibe puede estar arrancando (6.7); función nueva `hay_instancia(id_aplicacion: str, ruta_datos: Path | None = None) -> bool` (sin wx: `OpenMutexW(SYNCHRONIZE, False, nombre_exclusion(id_aplicacion, ruta_datos))`, verdadero si el mutex de la instancia única de esa carpeta `data` existe; no lo toma, así sirve para esperar a que exista o deje de existir en los pasos 2 y 4); función nueva `dejar_orden_esperando(orden: str, argumentos: list[str], tiempo_s: float) -> bool`, que deja la orden como `dejar_orden` y espera a que su archivo desaparezca del buzón (la instancia la recogió, porque `recoger_ordenes` borra cada archivo) o a que se agote el tiempo (devuelve falso; `dejar_orden` no cambia). La ventana recoge las órdenes `tarea` como las demás y, para cada una, llama a `ejecutar_tarea_programada` (varias tareas que se solapan se ejecutan una tras otra en la misma instancia, por la cola del motor).

**Lo que `main.py` pasa a la ventana**: `VentanaPrincipal(config, instancia=None, *, arranque: ArranqueInfo | None = None)` (la 1.x tiene `VentanaPrincipal(config, instancia)`, `main.py` l. 205). Con `arranque=None` la ventana usa `ArranqueInfo.nulo()`: `cargador=CargadorNulo()` (de `servicios_nucleo.py`: `congelar`, `descongelar`, `cerrar` y `ejecutar_tarea_programada` no hacen nada y `activos()` da una lista vacía), `bus=eventos.bus()` y `modo="normal"`; así las 5 pruebas de la 1.x que construyen `VentanaPrincipal(config)` no cambian. `ArranqueInfo` está definido en `app/services/servicios_nucleo.py` (sin wx; los tipos de otros módulos van como anotaciones en texto):

```python
@dataclass(frozen=True)
class ArranqueInfo:
    cargador: "Cargador"                        # el de cargador.arrancar (paso 8)
    bus: "Bus"                                  # eventos.bus()
    modo: Literal["normal", "tarea", "sesion"] = "normal"  # tarea: --modo-tarea, o --tarea sin poder salir del Job; sesion: --al-iniciar-sesion
    tarea: str | None = None                    # id de la tarea si esta instancia se quedó con ella (sin salir del Job)
    tras_actualizar: bool = False               # --tras-actualizar
    avisos: tuple[str, ...] = ()                # mensajes de los pasos 5 y 6 para el paso 11
    integracion: "ResumenIntegracion | None" = None    # paso 6
    restauracion: "ResultadoRestauracion | None" = None   # paso 5

    @classmethod
    def nulo(cls) -> "ArranqueInfo": ...         # CargadorNulo(), eventos.bus(), modo normal
```

El modo tarea tiene un solo dueño: `main.py` lo decide (paso 4) y la ventana lo aplica con `arranque.modo` (minimizada, sin anuncios, autocierre de 11.24).

Orden de arranque de `main.py` en la 2.0 (añade a 1.x §9.2):

1. **Cortocircuitos**, al principio de `main`, antes de la instancia única, de cualquier pendiente y de la configuración de la persona, cada uno con un **registro mínimo propio** (un archivo `data/logs/prueba-<fecha>.log`, solo biblioteca estándar, para que un fallo deje diagnóstico):
   - `--probar-componente`: prueba y sale con su código.
   - `--comprobar-arranque`: hace su comprobación de la 1.x (construye la ventana y la cierra), más `--complemento-prueba`, sin instancia única y sin pendientes. **Su secuencia es propia** y no la del arranque normal: `fijar_recursos` → `VARIABLE_DATA` en la carpeta temporal (`data/temp/comprobar-arranque-<pid>`) → registro → `wx.App` y planificadores → configuración → `cargador.arrancar` → ventana **sin mostrar** → `prueba.comprobar_complemento` si viene `--complemento-prueba` → cerrar la ventana y borrar la carpeta temporal. No hace los pasos 5, 6, 10 ni 11 (ni restauración, ni componentes, ni `al_arrancar`, ni avisos). Usa una carpeta de datos temporal **solo para lo escribible** (`config`, `cache`, `logs`, `plugins`, `temp`, `backups`), y lee de la `data` real los recursos distribuibles (`bin`, `sounds`, `locales`, `docs`, `icons`), así la prueba de la compilación sigue cubriendo la carga de libarchive y los paquetes de sonidos. Para eso `main.py` llama a `paths.fijar_recursos(paths.ruta_datos())` con la `data` real y después pone la variable `VARIABLE_DATA` de `paths.py` (la que ya redirige `ruta_datos()` en la 1.x) en la carpeta temporal: `fijar_recursos(ruta: Path) -> None` hace que `ruta_binarios()`, `ruta_sonidos()`, `ruta_traducciones()`, `ruta_documentacion()` y `ruta_iconos()` salgan de `ruta` y no de `ruta_datos()`. Sale con su código.

   Así una prueba lanzada por el actualizador de componentes con zCommander abierto no se reenvía a la instancia abierta ni vuelve a aplicar pendientes.
2. `--esperar-pid`, si viene: espera a que termine ese proceso (`OpenProcess` con `SYNCHRONIZE` nada más empezar, cuando el proceso viejo aún vive porque es él quien lanza este; si `OpenProcess` falla, ya terminó). Tras 30 s, **sigue esperando** al mutex de la instancia única (`instancia_unica.hay_instancia(ID_APLICACION)` hasta que dé falso) en lugar de reenviar nada (el proceso viejo puede tardar en desmontar nubes o esperar subidas), anunciando con la voz mínima «Esperando a que se cierre zCommander...» cada 30 s, hasta 5 minutos; si se agota, se dice «No se pudo reiniciar: zCommander sigue abierto» y sale.
3. Registro.
4. **`wx.App(False)`, los planificadores y la instancia única**, antes de tocar nada de `data/`. Se decide crear `wx.App` aquí, antes de la instancia única (como ya hace la 1.x, `main.py` l. 167-174): `InstanciaUnica` usa `wx.SingleInstanceChecker` y las preguntas nativas de los pasos 5 y 7.6 la necesitan; crearla cuesta poco. **Justo después de crearla**, `eventos.bus().fijar_planificador(wx.CallAfter)` y `cargador.fijar_planificador(wx.CallAfter)` (desde aquí, todo lo que se entrega a la interfaz pasa por el bucle de eventos). Después, la instancia única:
   - Si ya hay otra instancia, se le reenvían los argumentos (archivos, o `--tarea` con `dejar_orden("tarea", ...)`) y se sale sin aplicar ningún pendiente.
   - Si no la hay y viene `--tarea <id>`: si `procesos.puede_salir_del_job()`, este proceso suelta la instancia única (`liberar()`), lanza `procesos.lanzar_independiente([<ejecutable>, "--modo-tarea"])`, espera hasta 60 s a que la nueva tenga el mutex (`instancia_unica.hay_instancia(ID_APLICACION)`; este proceso ya no tiene `wx.SingleInstanceChecker`), le deja la orden con `dejar_orden_esperando("tarea", [id], 600)` y sale con 0 (1 si algo se agotó); no aplica ningún pendiente. Si no puede salir del Job, sigue como instancia con `modo = "tarea"` y `tarea = id`.
   - Si esta es la instancia, se llama a `actualizador.marcar_inicio(tras_actualizar)` (5.2).
5. `copia.pendiente.aplicar_pendiente()` (7.6), con la pregunta de una restauración preparada con «Más tarde», salvo en modo tarea y tras actualizar (entonces `preguntar = None`; tras actualizar se pregunta en el paso 11).
6. `componentes.integrar.aplicar_pendientes()` (diario de 6.6 y pendientes) e `integrar_entrante()` (6.7, con el anuncio de voz mínima si hay algo que integrar): todo antes de cargar ninguna DLL de `data/bin`. Sus mensajes van a `ArranqueInfo.avisos` para el paso 11.
7. Configuración (con su migración), `eventos.puentear_configuracion(config)` (14.4) y `sonidos.paquetes.migrar_1x()`.
8. Complementos: pendientes, modo seguro, centinelas, descubrimiento y marcadores (`cargador.arrancar`, 3.4).
9. Catálogo y mapa de teclas; `VentanaPrincipal(config, instancia, arranque=ArranqueInfo(...))` (aquí se cargan libarchive y los proveedores de `registro_proveedores`). Al construirse, la ventana registra sus servicios (14.9), llama a `api.fijar_interfaz(InterfazVentana(self))` (3.7) y, en el orden fijo de 14.9, a `instalar(self)` de cada módulo de acciones de bloque.
10. Lo hace la ventana con `wx.CallAfter` tras mostrarse, con lo que recibió en `ArranqueInfo`: `actualizador.al_arrancar()` (marca `ok`); complementos con `al_arrancar`; `al_instalar` y `al_desinstalar` de lo aplicado en el paso 8 (3.10); bus `al_arrancar`; en modo tarea con `arranque.tarea`, `ejecutar_tarea_programada` (las que llegan por el buzón se atienden igual).
11. También la ventana, después del paso 10: avisos pendientes, todos ya con la ventana y los sonidos: restauración aplicada, mensajes de componentes del paso 6 (y sus sonidos, `comp.revertido` incluido), complementos de una copia por instalar (7.6), centinelas y complementos sin aceptar (3.8, 3.9), actualización, «salud sin confirmar» de un arranque anterior (5.2), aviso inicial de los sonidos (4.5) y, tras actualizar, la pregunta por una restauración pendiente con `consultar_pendiente` (7.6). En modo tarea, solo los errores.

### 14.9 Otros cambios del núcleo

- `ContextoOrden` gana `sonar(evento: str, variante: str = "", *, sustituye: bool = False) -> bool` (la firma única de 4.3) y `argumento: Any = None` (el de una macro, el de `zc <orden> <argumento>` o la ruta de Intro sobre un archivo asociado); su `ejecutar_orden` pasa a `ejecutar_orden(id_orden, lado=None, *, argumento=None)` (10.1) y gana `ejecutar_orden_futuro(id_orden, lado=None, *, argumento=None) -> Future[bool]` (3.4; también en `VentanaPrincipal`), y su `lanzar` pone `operacion.orden_origen = self.orden` antes de pasarla a la ventana, cuyo `lanzar_operacion` gana `orden_origen: str = ""` solo por nombre (10.1). Los complementos no lo reciben: reciben `ContextoComplemento` (3.7).
- `ventana.servicio(nombre)` gana estos nombres, que **existen desde N2** (con objetos nulos que no hacen nada hasta que su bloque los sustituye con `registrar_servicio`, abajo), con su protocolo (en `app/services/servicios_nucleo.py`, N2, sin wx):
  - `"eventos"`: el `Bus` de `eventos.bus()` (14.4). `"sonidos"`: el `servicio` de 4.3. `"plugins"`: el `Cargador` (3.4).
  - `"grabador"` (PE): `Grabador` con `grabando: bool`, `anotar(id_orden: str, argumento: Any) -> None` y `anotar_argumento(valor: Any) -> None` (10.1). El nulo tiene `grabando = False` y no hace nada.
  - `"macros"` (PE): `ServicioMacros` con `en_curso() -> bool`, `detener() -> bool` (verdadero si había una macro y la detuvo; lo usa el paso 1 de `navegacion.cancelar`, 10.1) y `ejecutar(nombre: str) -> None`. El nulo dice que no hay ninguna en curso.
  - `"componentes"` (CO): las funciones de `app.services.componentes.estado` de 3.7 (`ruta`, `ejecutable`, `disponible`, `registrar_al_detener`) más `estado_de(id: str) -> str` («Instalado», «Falta», «En mantenimiento», «Dañado»), con la versión provisional de N2.
  - `"confirmaciones"`: el módulo `app.services.confirmaciones` (10.12: `debe_preguntar`, `silenciar`).
- **Enganches de arranque de cada bloque**: cada módulo de acciones de bloque (`app/ui/acciones/sonidos_so.py`, `complementos_pl.py`, `componentes_co.py`, `actualizar_ac.py`, `copia_cs.py`, `red_rd.py`, `personalizar_pe.py` y `nvda_nv.py`) tiene `instalar(ventana: VentanaServicios) -> None`. N2 crea cada una como provisional sin efecto (también en `EXTRA` de `generar_provisionales.py`, 14.1.1) y la ventana las llama **una vez, tras construirse y antes del paso 10 de 14.8, en este orden fijo** (tupla `INSTALADORES` de `ventana_principal.py`): SO, PL, CO, AC, CS, RD, PE, NV; cada llamada protegida (un fallo se registra y no impide las demás). Cada bloque solo rellena la suya; CM y LI no la necesitan (CM entra por `registro_proveedores.MODULOS`, que deja N2, 8.8). Lo que hace cada una: SO sustituye el reproductor provisional y da el aviso inicial (4.5); PL registra su comprobación periódica y el gestor; CO registra el servicio `componentes`, su comprobación periódica y la comprobación de integridad de 6.8 en un hilo; AC arranca el `ComprobadorPeriodico` (5.4); CS se suscribe a lo suyo; RD llama a `resolver.registrar_unidades` para «Red» (9.1); PE sustituye `grabador` y `macros`, llama a `ordenes.fijar_fuente_macros`, pone el decorador de filas de las reglas, la barra de botones y las teclas globales; NV ofrece el complemento de NVDA (10.16).
- Protocolo `VentanaServicios` (en `servicios_nucleo.py`, sin wx; lo implementa `VentanaPrincipal`), lo único de la ventana que pueden usar esas funciones:

```python
class VentanaServicios(Protocol):
    config: Configuracion
    tareas: GestorTareas
    def registrar_servicio(self, nombre: str, objeto: Any) -> None   # sustituye el nulo de uno de los nombres de arriba; otro nombre: ValueError
    def servicio(self, nombre: str) -> Any
    def anunciar(self, texto: str, nivel: str = NORMAL, completo: str = "", sonido: str = "") -> None
    def llamar_mas_tarde(self, ms: int, funcion: Callable[[], None]) -> None    # wx.CallLater, en el hilo de la interfaz
    def esta_libre(self) -> bool            # sin diálogo ni menú abierto ni operación esperando decisión (5.4)
    def padre(self) -> "wx.Window"          # la ventana principal, para los diálogos
    def fijar_decorador_fila(self, funcion: Callable[[Entrada], EfectoFila | None] | None) -> None   # en las listas de los dos lados (10.10)
    def colocar_barra_botones(self, barra: "wx.Window | None") -> None
    def registrar_tecla_global(self, id_orden: str, tecla: str) -> bool
    def liberar_teclas_globales(self) -> None
```

- `anuncios.anunciar` gana `sonido: str = ""` (4.3).
- `app/ui/acciones/archivos.abrir` (Intro): asociaciones internas antes que las de la persona, con la tabla `ABRIR_INTERNO: dict[str, str]` (extensión → id de orden, que se ejecuta con `argumento` = la ruta) que N2 deja completa: `.zcplugin` → `complemento_instalar`; `.zcbackup` → `copia_restaurar`; `.zcperfil` → `perfil_importar`; `.zcsonidos` → `sonidos_paquetes` (importar); `.zcmacro` → `macros` (importar, con la vista previa de 10.1); `.zcteclas` → `mapa_teclas` (importar, 10.7). Los valores `zc:<id de orden>` de `asociaciones.json` se ejecutan igual. Así ningún bloque edita `archivos.py`: cada uno solo hace que su orden acepte la ruta como argumento.
- `PreguntaError` y `Decisor` (14.6), `Operacion.orden_origen` y `pares_hechos` (14.5).
- `paths.py` gana: `ruta_plugins_serie()`, `ruta_plugins_usuario()`, `ruta_cache()`, `ruta_config_plugins()`, `ruta_cache_plugins()`, `ruta_copias()`, `ruta_sonidos_usuario()`, `ruta_plantillas()`, `ruta_plantillas_serie()` y `fijar_recursos(ruta: Path) -> None` (para `--comprobar-arranque`, 14.8).
- «Información para soporte» (1.x §12) añade complementos instalados con versión, estado y confianza, componentes con versión y origen, y paquete de sonidos (enganche de N2 en el módulo de la 1.x que la genera; PL, CO y SO aportan sus líneas con funciones de sus módulos que N2 deja provisionales: `app.plugins.gestor.lineas_soporte`, `app.services.componentes.estado.lineas_soporte` y `app.services.sonidos.paquetes.lineas_soporte`, cada una `() -> list[str]`).
- `app/core/red.py` y `app/core/descargas.py`, nuevos (0.3), solo biblioteca estándar y sin importar `app.services` (regla de capas):
  - `red.py`: `ConfiguracionRed(nombre_app, version_app, proxy="sistema", tiempo_conexion=10, tiempo_lectura=30)`; `obtener(config: ConfiguracionRed, url: str, *, cabeceras: dict[str, str] | None = None, tiempo_s: float = 30) -> RespuestaRed`; `enviar(config, url, datos: bytes | dict, *, metodo: str = "POST", cabeceras=None, tiempo_s: float = 30) -> RespuestaRed`; `RespuestaRed(estado, cabeceras, cuerpo, url_final)` con `texto()` y `json()` (la misma de 3.7, definida aquí y re-exportada); `class ErrorHTTP(Exception)` con `categoria` (`conexion`, `tiempo`, `certificado`, `http`, `cancelado`), `estado` y `mensaje` en español; `clasificar_error(e) -> InfoError(categoria, mensaje, reintentar)`; `redactar_url(url) -> str`. Se llama `ErrorHTTP`, no `ErrorRed` como en la plantilla red-http, para no tener dos clases con el mismo nombre: la de los complementos y del VFS es `vfs.base.ErrorRed`, y la fachada `ClienteRed` (en `app/plugins`) convierte `ErrorHTTP` en `ErrorRed`.
  - `descargas.py`: `descargar(config: ConfiguracionRed, url: str, destino: Path, *, sha256: str = "", tamano: int = -1, cancelacion=None, al_progresar: Callable[[int, int], None] | None = None) -> Path` (destino: archivo final o carpeta existente; `.parcial` reanudable con `Range`, caso 416, tope de tamaño y SHA-256), a partir de `_abrir` y `descargar` de la plantilla del actualizador, que después los usa desde aquí (5.1).
- `app/core/procesos.py` (nuevo, N2, sin wx): un **Job Object global** para todos los procesos hijos de zCommander, creado al arrancar con `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (si zCommander muere, mueren rclone, FFmpeg, 7za, PowerShell, git...), y **un Job anidado por cada `lanzar` y cada `popen`**, hijo del global (Windows 8 o posterior admite Jobs anidados). Funciones:
  - **Errores**: `app/core` no puede importar `app.services`, así que `procesos.py` define `class ErrorProceso(Exception)` con el atributo `mensaje: str` (el texto para la persona, ya traducido). Lo lanzan `lanzar`, `popen` y `lanzar_independiente` cuando no hay programa, la ruta no es completa, se pide un intérprete de órdenes o no se puede meter el proceso en su Job; `Anfitrion.ejecutar_programa` (3.7) lo convierte en `ErrorArchivos(error.mensaje)` para los complementos, que nunca ven `ErrorProceso`.
  - `lanzar(argumentos: list[str], *, entrada: bytes = b"", carpeta: str | None = None, tiempo_s: float = 60, cancelacion=None, al_leer: Callable[[bytes], None] | None = None, entorno: dict[str, str] | None = None) -> ResultadoPrograma`: sin consola (`CREATE_NO_WINDOW`), sin shell, lista de argumentos, ruta absoluta; espera al final o hasta el tiempo máximo. Si se cancela o se agota, termina **todo su árbol** con `TerminateJobObject` sobre su Job anidado (también los nietos: `git-remote-https`, ssh, los procesos de PowerShell), así nada sigue vivo contando en `hijos_vivos` ni en el `en_uso` de CO.
  - `popen(argumentos, **opciones) -> subprocess.Popen` (proceso largo en su Job anidado, para rcd, ffplay y el OCR por PowerShell); `terminar_arbol(proceso: subprocess.Popen) -> None` hace lo mismo que la cancelación de `lanzar`.
  - **Sin escapes del Job**: `lanzar` y `popen` crean el proceso con `CREATE_SUSPENDED`, lo asignan a su Job anidado con `AssignProcessToJobObject` y solo entonces lo reanudan con `NtResumeProcess` de `ntdll.dll` sobre el identificador de proceso (`subprocess` no da el del hilo principal); así ningún nieto nace antes de que el hijo esté en el Job. **Si la asignación falla**, el proceso suspendido se termina con `TerminateProcess` y se lanza `ErrorArchivos("No se pudo controlar el programa X")`; nunca queda un proceso suspendido.
  - `puede_salir_del_job() -> bool`: consulta `QueryInformationJobObject(NULL, JobObjectExtendedLimitInformation)` sobre el Job en el que está zCommander (si está en alguno: el del Programador de tareas, el de otro lanzador) y dice si admite `JOB_OBJECT_LIMIT_BREAKAWAY_OK`; sin Job, verdadero.
  - `lanzar_independiente(argumentos: list[str], *, carpeta: str | None = None) -> int` (PID): proceso **fuera** del Job Object, que sobrevive a zCommander: «Reiniciar» con `--esperar-pid`, el `.bat` del actualizador, la instancia real de una tarea programada (11.24) y los programas que abre la persona o que deben seguir abiertos, como el editor que lanza `zc.git` o un programa de una asociación. Con `CREATE_NEW_PROCESS_GROUP` y, si zCommander está dentro de un Job ajeno, `CREATE_BREAKAWAY_FROM_JOB` solo si `puede_salir_del_job()`; si no puede, lanza sin esa marca (el proceso queda en el Job ajeno, nunca en el de zCommander) y lo registra como aviso.
  - `hijos_vivos(nombre_exe: str) -> list[int]` (PID de los procesos del Job global, también los de sus Jobs anidados, con ese nombre; lo usa CO para `en_uso`).
  - `Anfitrion.ejecutar_programa` siempre usa `lanzar`. Lo usan CM (7za, 7z), CO (prueba y uso), P1 (FFmpeg), P2 (PowerShell), P4 (git, MpCmdRun), NU (rclone) y `Anfitrion.ejecutar_programa`.
- `app/services/confirmaciones.py` (10.12), `app/services/macros_argumentos.py` (tabla `ARGUMENTOS`, 10.1), `app/services/vistas_modelo.py` (`ConjuntoVista` y `EfectoFila`, 19.1) y `app/services/servicios_nucleo.py` (protocolos de los servicios de la ventana, `VentanaServicios` y `ArranqueInfo`, arriba y 14.8): nuevos, de N2.
- `app/core/descripciones_config.py` gana `EJECUTA: frozenset[str]`, las claves del núcleo cuyo valor es un programa o una orden que zCommander ejecuta (7.2).
- `app/core/version.py` gana `TITULAR` (2.1).

### 14.10 Módulos nuevos y dueños (resumen)

«N2, dueño posterior X» quiere decir que N2 crea el archivo (con el contrato completo y, donde haga falta, funciones provisionales) y después solo lo edita X (19.1).

| Módulo o carpeta | Bloque |
|---|---|
| `app/plugins/api.py`, `interfaz.py`, `manifiesto.py`, `registro.py`, `cargador.py`, `config_plugins.py`, `estado.py`, `firma.py`, `app/ui/api_ui.py` | N2 (versión funcional mínima; `firma.py` completa); dueño posterior PL, que la completa sin cambiar la API pública una vez congelada (3.7, `test_api_estable`) |
| `app/plugins/gestor.py`, `paquetes.py`, `auditoria.py`, `prueba.py`; `app/ui/dialogos/pl_*.py`; `tools/crear_plugin.py`, `validar_plugin.py`, `empaquetar_plugin.py`, `tools/plantilla_plugin/` | PL (`prueba.py` y `gestor.lineas_soporte`, provisionales de N2) |
| `app/ui/acciones/complementos_pl.py` | N2 deja el `ejecutar` y el `estado` reales (activación con su instantánea y despacho al registro, necesarios para su criterio de salida), `instalar` provisional y provisionales para las órdenes de PL; PL completa el resto sin cambiar `ejecutar` ni `estado` |
| `app/services/sonidos/catalogo.py`, `app/services/sonidos/servicio.py` (`sonar` y `Reproductor`, 4.3) | N2 |
| `app/ui/sonidos.py` (reescrito con `iniciar` y `cerrar`, 4.3) | N2; dueño posterior SO |
| `app/services/sonidos/motor.py`, `wav.py`; `app/ui/dialogos/so_*.py`; `app/ui/acciones/sonidos_so.py`; `tools/generar_sonidos.py`; `data/sounds/*/`; las carpetas `sonidos/` de los complementos de serie | SO (`so_pagina_sonidos.py` provisional de N2) |
| `app/services/sonidos/paquetes.py` | N2 (provisional: `migrar_1x`, `lineas_soporte`); dueño posterior SO |
| `app/services/eventos.py`, `app/core/red.py`, `app/core/descargas.py`, `app/core/procesos.py`, `app/services/confirmaciones.py`, `app/services/macros_argumentos.py`, `app/services/vistas_modelo.py`, `app/services/servicios_nucleo.py`, `app/ui/paginas_propias.py`, `app/ui/senales_nvda.py`, `app/ui/interfaz_anfitrion.py`, `app/plugins/serie.py` (lo regenera `generar_anexos.py`; `serie_sumas.py` lo genera `setup_cx.py`, de LI) | N2 |
| `app/services/actualizador.py` (provisional de N2: `registrar_comprobacion`, `Novedad`, `marcar_inicio`, `al_arrancar`), `app/ui/dialogo_actualizacion.py`, `app/ui/acciones/actualizar_ac.py`, `tools/firmar_version.py`, `tools/publicar.py`, el `.bat` de la plantilla (salud en dos fases, 5.2) | AC |
| `app/services/componentes/*` (provisionales de N2: `fichas.py` con el esquema, `estado.py`, `integrar.py`, `prueba.py`), `app/ui/dialogos/co_componentes.py`, `app/ui/acciones/componentes_co.py`, `tools/preparar_componentes.py`, `data/bin/componentes.json`, `data/bin/linea_base.json` (el provisional lo deja N2) | CO |
| `app/services/copia/*` (`pendiente.py`, provisional de N2), `app/ui/dialogos/cs_*.py` (también `cs_perfil.py` del `.zcperfil`), `app/ui/acciones/copia_cs.py` | CS |
| Sección 8.8 (con `vfs/zip.py`, `c_comprimir.py` y `operaciones/comprimir.py` como dueño posterior a N2; `app/services/libarchive/prueba.py`, provisional de N2) | CM |
| Sección 9.10 (con `app/ui/acciones/red_d.py` y `app/ui/dialogos/d_unidad.py` de la 1.x, y `app/ui/dialogos/rd_credenciales.py`, que crea N2, 9.4) | RD |
| `app/services/macros.py`, `esquemas_teclas.py` (lo crea N2 con las diferencias de 10.7), `vistas_carpeta.py` y `espacios.py` (provisionales de N2 con las funciones de destino de 3.7), `reglas.py`, `alias.py`, `menus_personalizados.py`, `plantillas.py`, `paleta.py`, `arranque_windows.py`, `teclas_globales.py`; `app/ui/dialogos/pe_*.py` (`pe_confirmaciones.py` y `pe_teclas_globales.py`, provisionales de N2, 10.18); `app/ui/barra_botones.py`; `app/ui/acciones/personalizar_pe.py`; cambios en `f_preferencias.py` (N2 le añade `abrir(padre, config, pagina=None)` provisional, 10.18), `f_perfil.py`, `f_paleta.py`, `f_mapa_teclas.py` (salvo el paso al catálogo vivo, que hace N2, 14.1.1), `f_columnas.py` (también las columnas de complementos, que lee de `app.plugins.registro.catalogo_columnas()`); dueño posterior de `app/services/linea_ordenes.py` (alias y autocompletar, 10.8) | PE |
| `app/services/busqueda.py` y `app/ui/dialogos/b_buscar.py` (motores de búsqueda y extractores de complementos), `app/services/renombrado.py` (máscaras), `app/ui/ventanas/visor.py` (14.7) | PL, como dueño posterior a N2 |
| `nvda_addon/`, `tools/construir_complemento.py`, `app/ui/instalar_complemento.py` (provisional de N2 para el botón de 10.18), `app/ui/acciones/nvda_nv.py` | NV |
| `tools/generar_licencias.py`, `comprobar_licencias.py`, `fuentes_terceros.py`, `data/docs/licencias/` (con la copia de `LICENSE`), `tools/empaquetar.py`, `tools/verificar_build.py`, `app/ui/acerca_de.py`; dueño posterior de `setup_cx.py` y `requirements.txt` | LI (`LICENSE`, los cambios de 17.1 en `setup_cx.py` y `cryptography` en `requirements.txt` los hizo N2 por encargo del coordinador, ronda 4) |
| `plugins/<carpeta>/` de cada complemento de serie (con su `manifiesto.toml` completo, 3.3) y sus pruebas | P1 a P5, NU, NS |

## 15. Accesibilidad

Valen todas las reglas de 1.x §11 y las del agente `accesibilidad-wx`. Lo nuevo de la 2.0:

### 15.1 Ventanas y diálogos nuevos

- Cada ventana y diálogo nuevo (gestor de complementos, componentes, copia de seguridad, mapa y asistente de sonidos, red, macros, menús, reglas, vistas, esquemas, ventana del NAS, cuentas de nube, asistente de nubes, reproductor, editor hexadecimal, visor de tablas, etc.) pasa `revisar_teclado` en una prueba de su bloque, con la etiqueta creada antes de cada control, letras de acceso únicas por pantalla (contando Aceptar, Cancelar y Aplicar), foco inicial útil, Escape que cierra o cancela, Ctrl+H con ayuda en cada control y F1 con la ayuda que toca (manual o la del complemento).
- Acciones destructivas o arriesgadas con el foco inicial en la opción segura: desinstalar complementos, restaurar copias, restaurar componentes, vaciar papeleras, quitar enlaces, apagar y reiniciar el NAS, permitir cambios en el NAS, instalar un complemento sin firma, desconectar a la fuerza.
- Las listas con casillas usan `CheckListBoxAccesible` o `ListaAccesible` con casillas (estado anunciado); las listas multicolumna, `ListaAccesible` (lectura por columnas con las preferencias de la 1.x). Nada de `wx.SpinCtrlDouble`, `wx.SearchCtrl`, `wx.grid` ni controles dibujados a mano; los deslizadores son `SliderAccesible` («70 de 100»).
- Las esperas largas (OAuth, descubrimiento de red, descargas, conversiones) tienen un texto de estado de solo lectura que el lector puede leer, una barra con nombre y un anuncio periódico prudente (cada 30 s como mucho), además del progreso por hitos del motor.

### 15.2 Información que no puede depender de un sonido o un color

Todo sonido tiene su equivalente en texto (anuncio, historial o consulta) y todo color de las reglas su texto o sonido (10.10). El estado de un complemento, de un componente o de una cuenta es texto («Activo», «Falta», «Desconectada»), nunca un icono.

### 15.3 Reglas obligatorias para los complementos

Las de plugins.md 2.12, que la guía del autor recoge y `tools/validar_plugin.py` comprueba donde puede: preferir los contratos de datos (`Documento`, columnas, filas, páginas declarativas, diálogos de `api.ui`) a ventanas propias; ventanas propias solo con `api.ui`; `revisar_teclado` en todas; anuncios solo con `zc.anunciar` y su nivel, nunca accessible_output2 directamente ni lo que el lector ya dice al mover el foco; ninguna pregunta desde un hilo (siempre el `Decisor`); teclas según 1.x §6.1; colores y letra del tema; prueba manual mínima con NVDA, JAWS y Narrador antes de publicar (lista corta en la guía).

### 15.4 Voz sin las DLL no libres

`voz.py` crea solo las salidas NVDA, JAWS y SAPI5 (2.3). Con un lector distinto (System Access, Dolphin, PC-Talker, Zhengdu) zCommander usa las notificaciones UIA (como con Narrador, 1.x §11), que esos lectores pueden leer o no: se documenta en el manual y en riesgos.

### 15.5 Pruebas manuales

`docs/pruebas-manuales.md` gana la parte 2.0 (bloque DO): un recorrido por cada sección 3 a 13 con NVDA, JAWS y Narrador, incluido el complemento de NVDA (celdas largas y movimiento silencioso) y la lectura de los diálogos de espera.

## 16. Seguridad y privacidad

Valen 1.x §14. Lo nuevo:

- **Código de terceros**: los complementos se ejecutan con los permisos de la persona; no hay aislamiento real. Mitigación: permisos declarados y visibles, firma opcional con tres niveles de confianza, clave fijada por id (exigida también al cargar) y separación de dominio en lo firmado, sumas comprobadas al activar y otra vez al leer cada archivo con el cargador de módulos verificado (sin `.pyc` para los de `data/plugins/`, 3.9), confianza por ubicación solo para la lista de serie de `app/plugins/serie.py` (3.2), consentimiento guardado para cada complemento sin firma (los que aparecen en `data/plugins/` sin pasar por el gestor quedan «Sin aceptar»), aviso con «Cancelar» predeterminado para los no firmados, `ContextoComplemento` sin acceso a la ventana ni a los secretos ajenos, `lib/` sin tocar `sys.path`, auditoría opcional, modo seguro, desactivación tras fallos (3.3 a 3.9). Las copias de seguridad nunca instalan complementos ni claves de confianza sin pasar por la instalación normal, ni restauran órdenes ejecutables o huellas de servidores sin que la persona las marque una a una (7.2, 7.6); lo mismo al importar un `.zcmacro` (10.1) o un `.zcperfil` (10.2).
- **Modelo de amenaza de los complementos** (lo que las sumas y la firma protegen y lo que no): protegen contra **cambios no buscados en lo que ya se aceptó**: una carpeta sincronizada o un programa que deja o cambia archivos en `data/plugins/` o en `<raíz>/plugins/`, una `.pyc` sembrada en `data/cache/pycache/`, una actualización suelta que no viene del mismo autor, una copia de seguridad ajena. **No** protegen contra un programa malicioso que ya se ejecuta con los permisos de la persona: quien puede escribir en `data/` puede escribir también `complementos.confiados` y `data/config/plugins/claves.json`, y quien puede escribir en la carpeta del programa puede cambiar el propio `.exe`. Por eso no se cifra ni se firma nada local con una clave guardada en el equipo, y la ventana mínima entre comprobar una `.pyd` y cargarla (3.9) se acepta.
- **Actualizaciones**: firma Ed25519 del manifiesto entero con clave incrustada, anti-retroceso con la versión confirmada, solo https, extracción segura, vuelta atrás (5.5). La clave privada nunca entra en el repositorio ni en el servidor.
- **Componentes**: SHA-256 de cada paquete descargado contra la suma publicada por su origen (6.2), ejecutables siempre con ruta absoluta desde `data/bin`, DLL con `os.add_dll_directory` y ruta absoluta, procesos sin consola, sin shell y en el Job Object global (`app/core/procesos.py`), prueba antes y después de sustituir, sustitución con diario (con las sumas de lo nuevo) y renombrado de carpetas con reintentos (6.6). La firma PGP de las sumas no se verifica en la aplicación (riesgo 20.6).
- **Copias de seguridad**: secretos con AES-256-GCM y scrypt (n = 2^17), datos asociados para no mezclar copias, copia automática antes de restaurar, sumas de cada archivo. Las copias sin secretos lo dicen; los `.zcperfil` nunca los llevan.
- **Secretos**: en `secretos.dat` con DPAPI (1.x), con espacios propios: `ftp:*`, `plugin:<id>:*` (incluidos `plugin:zc.nubes:*` y `plugin:zc.synology:*`); `rclone.conf` cifrado con contraseña aleatoria guardada en DPAPI. Nunca en `settings.json`, en JSON auxiliares, en argumentos de procesos ni en el registro. `app/core/registro.py` añade a su filtro de redacción (que también pasa a lo que rclone escribe en `stderr`, 12.2) `token=`, `access_token`, `Authorization`, `refresh_token`, `_sid`, `SynoToken`, `passwd`, `otp_code`, `device_id`, `appPassword` y `RCLONE_*_PASS`.
- **Red y servicios locales**: rcd solo en 127.0.0.1 con usuario y contraseña aleatorios y nuevos en cada intento, y comprobación con `GetExtendedTcpTable` de que el puerto es del proceso hijo antes de enviarle ninguna petición (12.2); sin `--log-file`; `rclone.conf` cifrado antes de la primera cuenta (12.3); «Compartir en la red» de las nubes solo en 127.0.0.1 salvo confirmación expresa; el simulador DSM y su `/__control` solo en 127.0.0.1; TLS verificado siempre y, si no se puede (certificados propios), huella fijada con aviso al cambiar.
- **NAS**: modo solo lectura por defecto con lista blanca de métodos en el cliente; doble confirmación para apagar, reiniciar y actualizar DSM; un solo intento por acción de la persona (nunca bucles de contraseña que activen el bloqueo de IP); aviso de la vulnerabilidad CVE-2026-40530 si el DSM es anterior a 7.3.2-86009 Update 2.
- **Privacidad**: ningún dato sale del equipo sin una acción de la persona, salvo las comprobaciones de actualizaciones (que solo envían el User-Agent «zCommander/<versión>» al servidor del proyecto y a GitHub y MSYS2 para los componentes) y lo que configure la persona (nubes, NAS, descripción de imágenes, VirusTotal con solo el hash). La descripción de imágenes y VirusTotal avisan la primera vez de qué se envía y a dónde. Las comprobaciones periódicas se pueden desactivar.
- **Excepciones a la portabilidad** (principio 3 de 1.x §3: todo en `data/`). La 2.0 deja algo fuera de `data/` solo en estos casos, y siempre por una acción expresa de la persona:
  1. El valor `zCommander` de `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` («Arrancar con Windows», 10.17): la única escritura en el Registro de Windows.
  2. Las tareas del Programador de tareas de Windows que crea el programador (11.24).
  3. Las conexiones de red persistentes (`CONNECT_UPDATE_PROFILE`, casilla «Volver a conectar al iniciar sesión», 9.4), que Windows guarda en el perfil del usuario.
  4. Las credenciales que se guardan en el Administrador de credenciales de Windows («Recordar la contraseña», 9.4).
  5. Las unidades de nube montadas con WinFsp (12.8), que existen mientras zCommander está abierto.
  6. El complemento de NVDA, que instala NVDA en su propia carpeta cuando la persona lo acepta (10.16).
  Todo lo demás (configuración, secretos, cachés, registros, copias, complementos y componentes) está en `data/`. El manual (bloque DO) lista estas excepciones.
- **Datos de prueba**: credenciales inventadas en el simulador; nunca las reales en el repositorio, en las pruebas ni en el registro.

## 17. Compilación y distribución

### 17.1 `setup_cx.py`

- `PAQUETES` pasa a incluir `cryptography` como obligatorio (sale de `PAQUETES_OPCIONALES`, donde está en la 1.x; firma de actualizaciones, copias, complemento de cifrado), `libloader` y `platform_utils` (dependencias de accessible_output2) y `wx.media`, `wx.html2`, `win32com.shell`, `win32com.propsys`, `win32cred`, `win32job`, `win32net`, `win32wnet`, `winreg`, `ctypes.wintypes`, `sqlite3`, `tomllib`, `compression` enteros.
- **Biblioteca estándar completa** para los complementos (3.7): se añaden a `packages` los módulos de `sys.stdlib_module_names` que **existen en el CPython de Windows de la máquina que compila** (`importlib.util.find_spec(nombre) is not None`), salvo la lista negra: `tkinter`, `turtle`, `turtledemo`, `idlelib`, `test`, `ensurepip`, `venv`, `lib2to3`, `pydoc_data`, `antigravity` y `this` (tienen efectos al importarse o dependen de lo excluido), `curses` (está en disco pero sin `_curses` en Windows) y los solo POSIX por si alguno respondiera (`posix`, `pwd`, `grp`, `fcntl`, `termios`, `tty`, `pty`, `resource`, `syslog`, `readline`, `_posixsubprocess`). Sin ese filtro cx_Freeze se detiene con «No module named …». `unittest` **vuelve** (se quita de `EXCLUDES`). Una prueba de la compilación (`tools/verificar_build.py`) importa cada módulo de esa misma lista filtrada desde el ejecutable congelado.
- **Complementos de serie**: `include_files` copia `plugins/` (raíz del repositorio) a `build/ZCommander/plugins/` con los filtros de `PATRONES_EXCLUIDOS` (sin `__pycache__`, sin pruebas); sus `.py` viajan como fuente (los complementos son GPL y legibles).
- **`data` distribuible**: `DATA_DISTRIBUIBLE = ["bin", "sounds", "locales", "docs", "icons"]`; `plugins` sale de la lista (los de la persona nunca se distribuyen) y entra en `DATA_PROHIBIDO` junto a `sounds_usuario`, `plantillas` y `backups`. De `data/bin` se excluyen `respaldo/`, `.pendiente/` y `.entrante/`.
- **DLL no libres de accessible_output2**: tras compilar, se borran de `lib/accessible_output2/lib/` las seis de 2.3 y `nvdaControllerClient32.dll`; `tools/comprobar_licencias.py` falla si alguna sigue.
- `sys.pycache_prefix` apunta a `data/cache/pycache` desde `main.py` (para que nada escriba `__pycache__` en la carpeta del programa); los complementos de `data/plugins/` nunca usan `.pyc` y los de serie solo con validación por hash (3.9).
- `setup_cx.py` calcula, antes de congelar, el SHA-256 de cada archivo de `plugins/` que va a copiar (con los mismos filtros de `PATRONES_EXCLUIDOS`), escribe `app/plugins/serie_sumas.py` (3.2), congela y lo borra del código fuente al terminar; `tools/verificar_build.py` comprueba que la compilación lo lleva y que las sumas coinciden con `build/ZCommander/plugins/`.
- Manifiesto de Windows como en la 1.x (rutas largas y DPI por monitor).

### 17.2 Antes de compilar

1. `python tools/generar_anexos.py --comprobar` (anexos al día, también `sonidos.md` y `componentes.md`).
2. `python tools/generar_sonidos.py --comprobar` (los paquetes de serie son los que genera el generador).
3. `python tools/preparar_componentes.py --comprobar` (cada archivo de `data/bin` coincide con `linea_base.json`).
4. `python tools/construir_complemento.py` (el `.nvda-addon` al día).
5. `python tools/generar_licencias.py` y `python tools/comprobar_licencias.py`.
6. `python tools/validar_plugin.py plugins/*` (los 27 complementos de serie).

### 17.3 Paquete y tamaño

- Paquete: `zCommander_v<versión>.zip` (el nombre que espera el actualizador; sustituye a `zCommander-<versión>-win64.zip` de la 1.x), creado por `tools/empaquetar.py`.
- Tamaño estimado: `data/bin` unos 290 MB sin comprimir (FFmpeg unos 208 MB, rclone unos 86 MB, libarchive 4 MB, 7za 1,3 MB), la biblioteca estándar completa unas decenas de MB más que la 1.x, sonidos unos 5 MB (5 paquetes de unos 150 archivos cortos). Se mide al compilar y se anota en el registro de cambios; riesgo 20.8.

### 17.4 `entorno.bat`

Gana las opciones «Generar sonidos», «Preparar componentes», «Construir el complemento de NVDA», «Comprobar licencias», «Publicar (sin servidor)» y «Publicar en el servidor».

## 18. Pruebas

Valen las de 1.x §17 (las 759 siguen pasando). Reglas: nunca `data/` real ni Internet (servidores locales: simulador DSM, `rclone serve`, `http.server`, pyftpdlib), nunca el NAS real, nunca cuentas reales; lo que necesita binarios reales de `data/bin` lleva la marca `componentes` y se ejecuta por defecto solo si el binario está; lo lento, `lento`; lo que toca el sistema (papelera real, registro de Windows, teclas globales), `interfaz`.

### 18.1 Pruebas comunes nuevas y pruebas de la 1.x que cambian

Las pruebas de arquitectura de la 1.x viven en `tests/test_n_arquitectura.py` (`test_capas_sin_interfaz`, `test_ningun_manejador_provisional`, `test_sin_pendientes_en_el_codigo`, `test_anexos_al_dia`, `test_lista_de_teclas_coincide_con_el_codigo`...). N2 las modifica así, lo primero de todo (19.1), para que las 759 de la 1.x sigan en verde con los provisionales de la 2.0:

- `test_capas_sin_interfaz`: se amplía de `app/core` y `app/services` a `app/plugins`, **sin ninguna excepción**: ningún módulo de `app/plugins` importa wx ni `app.ui` (ni siquiera de forma perezosa ni bajo `TYPE_CHECKING`; la interfaz llega por `api.fijar_interfaz` y `ModuloUI` delega en `InterfazAnfitrion.modulo_ui`, 3.7). Una prueba nueva del mismo archivo comprueba con `ast` que ningún complemento de serie importa `app.` fuera de `app.plugins.api`.
- `test_ningun_manejador_provisional`: se parametriza por bloque. El archivo tiene `BLOQUES_ABIERTOS = {"PL", "SO", "AC", "CO", "CS", "CM", "RD", "PE", "NV", "LI", "P1", "P2", "P3", "P4", "P5", "NU", "NS"}`; un manejador provisional de un bloque abierto se permite y uno de un bloque cerrado falla. Cuenta dos clases de provisionales:
  - Los de los módulos de acciones (los de `tools/generar_provisionales.py`, por el bloque de su orden en el catálogo, y las funciones `instalar` de 14.9, por el sufijo del módulo, cuando tienen la marca `provisional = True` que les pone `generar_provisionales.py`). Las órdenes con manejador `complementos_pl.ejecutar` o `complementos_pl.estado` no cuentan aquí (son reales desde N2); `personalizar_pe.ejecutar_macro` cuenta como provisional de PE.
  - Los de los complementos de serie: para cada uno, la prueba crea `api.pruebas.anfitrion_de_prueba(carpeta)`, importa su clase de entrada y llama a `activar(zc)`; comprueba que **cada id de su `[[ordenes]]` tiene manejador** y lee la marca `provisional = True` que `api.provisional` pone en la función devuelta. Un provisional cuenta para el `bloque` de su manifiesto.

  Cada bloque se quita de la lista en su definición de terminado (19.4); al final queda vacía.
- `test_sin_pendientes_en_el_codigo`: sigue buscando «Todavía no disponible» y `NotImplementedError` en `app/`, y ahora también en `plugins/`, pero permite la marca en los archivos de un bloque abierto: los módulos de acciones con el sufijo del bloque (`sonidos_so.py` → SO, `red_rd.py` → RD...), los provisionales en archivos de otros bloques de la tabla de 19.1 (por su dueño posterior) y la carpeta de cada complemento de serie según su `bloque`. `app/plugins/api.py` no usa ese texto: lo que aún no tiene implementación lanza `NoAdmitido` con «Esta función de la API no está disponible en esta versión», a través de una única función `api._sin_implementar(nombre)` que la prueba cuenta como provisional del bloque PL.
- `test_anexos_al_dia`: con los anexos nuevos (0.2) y `app/plugins/serie.py` (3.2).
- `test_lista_de_teclas_coincide_con_el_codigo` (`tools/comprobar_teclas.py`): compara con `data/docs/teclas.md` también las teclas de las 45 órdenes nuevas del núcleo y las de los 27 complementos de serie (que ve por `registrar_serie`). N2 pone `teclas.md` al día (19.1); después, cada bloque que añade teclas propias de una ventana (por ejemplo, las del visor de 14.7, PL) las añade en su definición de terminado (19.4).
- `tests/ui/test_n2_teclas.py` (nueva): choques de teclas de 14.1.3.
- `tests/ui/test_n2_menus.py` (nueva): `tools/comprobar_menus.py` sin problemas con `ordenes.menus()` y `menu_contextual()` sobre el catálogo completo y con «Mis órdenes» lleno.
- Prueba de arranque con los 27 complementos de serie (`lento`): ventana en menos de 1,5 s y menos de 100 ms de `al_arrancar`.
- **Complementos de serie en las pruebas**: `tests/conftest.py` gana la fixture `complementos_serie` (alcance `session`, `autouse`), que llama una vez a `app.plugins.registro.registrar_serie()`: el catálogo de las pruebas es el de la aplicación (núcleo y 27 complementos), sin importar código de ningún complemento ni leer `data/`. Las pruebas que necesitan el registro vacío usan la fixture `registro_vacio` (llama a `registro.vaciar()` y vuelve a registrar la serie al terminar). El bus único de 14.4 se reinicia en cada prueba con `eventos.reiniciar()` (fixture `autouse` de alcance `function`).

**Pruebas de la 1.x que N2 reescribe** porque el diseño cambia lo que comprueban, en el mismo paso de 19.1 que hace el cambio. Si al programar aparece otra, se reescribe igual y se añade a esta lista.

- `tests/ui/test_n_correcciones.py`: `test_sonidos_respetan_las_casillas` y `test_tonos_suben_con_el_porcentaje_y_van_en_otro_hilo` crean `sonidos.Sonidos(config, carpeta_sonidos=...)` con `accesibilidad.sonidos` y `accesibilidad.tonos_progreso`, que desaparecen (4.3, 14.3). La primera pasa a probar `servicio.sonar` con un reproductor falso (`sonidos.activos` y `sonidos.eventos` filtran); la segunda, que el reproductor provisional de N2 nunca bloquea (el tono suena en otro hilo). `test_fin_de_operacion_suena_si_estan_activos` comprueba que la ventana pide `sonar("op.fin")`. Además, las dos del seguimiento del progreso (`test_cada_25_anuncia_hitos_y_al_empezar_y_terminar_no` y `test_tonos_cada_10_y_decision`, l. 142-184 de la 1.x) comprueban ahora los `sonar("op.progreso", ...)` que pide la ventana en su latido (4.4): 25, 50 y 75 con `cada_25`, y 10, 20, 40 con `cada_10` (una vez por decena, aunque se salte alguna).
- `tests/test_arranque.py`: `test_arranque_completo_y_cierre` (el registro de `--comprobar-arranque` es `data/logs/prueba-<fecha>.log` y su carpeta temporal se borra, 14.8) y `test_segunda_instancia_pide_mostrar_y_sale` (la primera instancia se arranca como arranque normal, porque `--comprobar-arranque` ya no toma la instancia única).
- `tests/servicios/test_d_ftp.py`: su `ConfigFalsa` con `ftp.avisar_sin_cifrar` pasa a `general.no_preguntar` con `ftp_sin_cifrar:<id del sitio>` (10.12), en las dos pruebas que lo usan.
- `tests/test_n_arquitectura.py`: las de arriba.
- `tests/test_configuracion.py` y `tests/test_dialogo_preferencias.py` ya parchean `VERSION_ESQUEMA` con su propia plantilla (`tests/_config_plantilla.py`), así que la versión 2 no las cambia; `test_letras_de_preferencias_sin_choques` incluye las claves nuevas de 14.3 con sus letras (N2 las elige sin choques en `descripciones_config.py`).

### 18.2 Mínimos por bloque

- **N2**, por archivo (todas forman parte de su criterio de salida, 19.1):
  - `tests/servicios/test_n2_eventos.py`: `eventos.bus()` devuelve siempre el mismo bus; el bus entrega en el hilo del planificador lo emitido desde otro hilo y llama a todos los suscriptores aunque uno falle; `emitir_sincrono` llama en el acto; `vaciar()` entrega lo pendiente en orden y no lo repite después; tras `cerrar()`, `emitir` descarta; el puente de la configuración emite `al_cambiar_preferencia` con un cambio hecho desde otro hilo.
  - `tests/servicios/test_n2_red.py`: `redactar_url` oculta `token=`; `clasificar_error` da la categoría y el mensaje en español de cada error.
  - `tests/servicios/test_n2_descargas.py`: `descargar` reanuda un `.parcial` con `Range` y rechaza un SHA-256 distinto (servidor `http.server` local).
  - `tests/servicios/test_n2_procesos.py` (nuevo): `lanzar` mete el hijo en su Job anidado antes de reanudarlo (un nieto que crea al empezar también está en el Job); cancelar o agotar el tiempo termina también el nieto (`TerminateJobObject`); si `AssignProcessToJobObject` falla (simulado), el proceso suspendido se termina y se lanza `ErrorArchivos`; `hijos_vivos` encuentra un hijo de un Job anidado; `lanzar_independiente` deja un proceso que sobrevive al cierre del Job; con `puede_salir_del_job()` falso (simulado), lanza sin `CREATE_BREAKAWAY_FROM_JOB` y lo registra.
  - `tests/servicios/test_n2_vfs_ganchos.py`: `OperacionCopiar` usa `transferir_lote` o `transferir` si el proveedor los admite y la copia por bloques si no, escribe sin temporal con `escritura_atomica`, y con dos proveedores falsos del mismo esquema y distinta cuenta nunca mueve con `renombrar`; `PreguntaError` lleva el código 32 de un archivo abierto por otro proceso.
  - `tests/plugins/test_n2_manifiesto.py`: un manifiesto válido se lee y cada campo malo da su mensaje en español (también `codigos_windows` y `ejecuta`); `plugin.prueba.ejemplo.volumen` se resuelve al complemento `prueba.ejemplo` y la clave `volumen` (los complementos de prueba no usan `zc.*`, reservado); dos carpetas con el mismo id en la misma ubicación quedan las dos en `ERROR_MANIFIESTO`; `registrar_serie` registra los marcadores de los 27 sin importar ningún módulo `zcplugins.*`.
  - `tests/plugins/test_n2_cargador.py`: un complemento de ejemplo registra una orden y su manejador se ejecuta desde el catálogo; uno que lanza al importar queda `FALLIDO` y el resto funciona; el centinela se escribe y se borra también cuando `activar()` lanza; dos disparos a la vez dan una sola activación (el segundo recibe el mismo futuro); `activar()` se llama en el hilo de la interfaz aunque el disparo venga de un hilo; una orden ejecutada mientras su complemento está `CARGANDO` no bloquea la interfaz, se ejecuta al terminar la carga con la instantánea del objetivo tomada al pulsar, y se descarta con su aviso si entretanto se cambia de carpeta o se ejecuta otra orden; la continuación no corre dentro de `set_result` (corre en otra vuelta del planificador) y su excepción se registra; `ejecutar_orden_futuro` se resuelve cuando ha corrido la continuación; un hilo que espera la activación no tiene ningún candado tomado; `valor_columna` no manda trabajo hasta que la activación termina y los 5 s cuentan desde ahí; `prueba.lento` con un tope de carga reducido para la prueba queda `FALLIDO`, sin «Volver a intentarlo», y la carga siguiente usa otro hilo; un complemento con `[requiere] complementos` activa antes su dependencia y ve lo que exporta en su `activar()`; dos que se requieren el uno al otro dan «dependencia circular» y ninguno queda a medio activar; `mostrar_modal` dentro de `activar()` lanza `RuntimeError`; `zc.complemento` llamado desde la interfaz con el otro sin activar devuelve `None` sin importar nada; tras `congelar()` no empieza ninguna activación y tras `descongelar()` sí; tras `cerrar()`, quien espera un futuro recibe `Cancelado` y no queda ningún centinela; `al_cerrar` llega a los suscriptores antes de `desactivar()`; un complemento con `lib/` no cambia `sys.path` y su `MetaPathFinder` no tapa un módulo de la biblioteca estándar; un archivo cambiado después de activar hace fallar su importación tardía; una `.pyc` puesta en `data/cache/pycache/` para uno de `data/plugins/` no se usa; un complemento sin firma aceptado y cambiado pasa a `SIN_ACEPTAR`.
  - `tests/plugins/test_n2_firma.py`: `firma.verificar_complemento` con una clave de prueba acepta lo firmado y rechaza un byte cambiado (con `comprobar_sumas=True`) o un archivo de más; un `zc.*` sin firma de la lista de `serie.SERIE` en `<raíz>/plugins/` es «Oficial», y uno que no está en la lista (o con otra versión) se trata como de `data/plugins/` y se rechaza; un complemento de prueba sin firma copiado a `data/plugins/` queda `SIN_ACEPTAR` y con su suma en `complementos.confiados` se carga.
  - `tests/plugins/test_api_estable.py`: la firma pública de la API coincide con la instantánea; `api.py` no importa `app.ui`; sin `fijar_interfaz`, los métodos [interfaz] lanzan `NoAdmitido`.
  - `tests/servicios/test_n2_catalogo_sonidos.py`: cada evento del catálogo tiene id único, categoría conocida y prioridad válida; `sonar` sin reproductor devuelve falso y con uno falso pasa `sustituye`.
  - `tests/test_n2_migracion.py`: la migración 1 → 2 deja `sonidos.activos` verdadero con `accesibilidad.sonidos = false`, convierte `accesibilidad.tonos_progreso = true` en `sonidos.progreso = "cada_10"`, lleva `ftp.avisar_sin_cifrar = false` y `operaciones.aviso_comprimido_mostrado = true` a `general.no_preguntar` y es idempotente; cada nombre de `EJECUTA` es una clave que existe.
  - `tests/test_n2_instancia.py`: `hay_instancia` da falso sin instancia y verdadero mientras un `InstanciaUnica` de la misma carpeta `data` está viva, sin crear ningún mutex; `ORDENES_VALIDAS` acepta `tarea` y caduca a los 600 s; `dejar_orden_esperando` vuelve verdadero cuando otro hilo recoge la orden y falso si se agota; `--tarea` con otra instancia deja la orden y sale; sin instancia (procesos simulados), el proceso de la tarea lanza la instancia con `--modo-tarea`, le entrega la orden y sale, y si no puede salir del Job se queda como instancia en modo tarea.
  - `tests/ui/test_n2_contexto.py`: `ContextoOrden.lanzar` pone `orden_origen`; `ContextoOrden.sonar` y `argumento`; la grabación de macros apunta el paso antes de que el diálogo llame a `anotar_argumento`.
  - `tests/ui/test_n2_decisiones.py`: el gestor de decisiones responde con las `RespuestasAutomaticas` de una operación sin mostrar nada; una acción de error con `codigos_windows = [32]` aparece con el código 32 sin activar el complemento, no aparece con el 5, y al pulsarla activa el complemento y llama a su función; `pedir_credenciales` desde un hilo usa `rd_credenciales.pedir`.
  - `tests/ui/test_n2_ventana.py`: la ventana llama una vez a `instalar` de cada módulo de bloque en el orden de 14.9 y un `instalar` que lanza no impide los demás; `servicio()` da los nombres nuevos de 14.9 con sus nulos y `registrar_servicio` los sustituye; `api.fijar_interfaz` se llama al construirse y con `None` al cerrar; el cierre sigue el orden de 3.4 (congelar antes de la pregunta, `puede_cerrar` que veta deja todo como estaba y descongela, `vaciar`, `al_cerrar`, `desactivar`, `bus.cerrar`, `cargador.cerrar`); en modo tarea, el autocierre no pregunta aunque `general.confirmar_salida` esté activa y no cierra con otra tarea en la cola; los menús salen de `ordenes.menus()` y se reconstruyen con `al_cambiar_catalogo`; `POR_ID` y `CATALOGO` ven una orden de complemento registrada después de importarlos.
  - `tests/ui/test_n2_voz.py`: `voz.py` arranca sin las DLL no libres.
  - `tests/ui/test_n2_senales_nvda.py`: `publicar_orden_lectura` codifica `[0, 3, 1]` y 15 columnas (el máximo) como dice 10.5, y `marcar_movimiento_silencioso` pone la propiedad con la hora.
  - Las de 18.1 (arquitectura modificada con todos los bloques abiertos, `test_n2_teclas.py`, `test_n2_menus.py`) y las de la 1.x reescritas de 18.1.
- **PL** (`tests/plugins/test_pl_*.py`, `tests/ui/test_pl_gestor.py`): instalar un `.zcplugin` válido de un id nuevo sin `al_arrancar` lo deja en `data/plugins/<id>/` y usable sin reiniciar; instalar una actualización (o uno con `al_arrancar`) lo deja en `.pendientes` y lo aplica en el reinicio simulado; un ZIP con `../malo.py` se rechaza sin escribir nada; un paquete con firma válida es «Oficial» y con un byte cambiado o un archivo de más es «Sin firma»; una actualización firmada con otra clave que la fijada para su id se rechaza; tres fallos desactivan el complemento en la sesión; actualizar conserva `data/config/plugins/<id>.json`; desinstalar con «borrar datos» los borra y sin ello los conserva; la página declarativa de un complemento aparece en Preferencias y guarda en su JSON; una columna de complemento se calcula en un hilo y respeta el tiempo máximo; un visor devuelve un `Documento` que el visor muestra con F6 entre secciones; una acción de error aparece en la pregunta de error; el gestor pasa `revisar_teclado`; `tools/validar_plugin.py` devuelve 0 con la plantilla de `crear_plugin.py` y 1 con un manifiesto sin licencia; la compilación carga un complemento de prueba (`--comprobar-arranque --complemento-prueba`, marca `lento`).
- **SO** (`tests/servicios/test_so_*.py`, `tests/ui/test_so_*.py`): `sonar()` tarda menos de 5 ms (media de 1000 llamadas con el motor falso); una alta corta una baja; varias bajas seguidas suenan solo la última; el volumen 50 escala las muestras con la ganancia de 4.4; un WAV de 24 bits o de 12 s se rechaza; la herencia resuelve un evento que falta en un paquete propio al de `clasico`; importar un `.zcsonidos` con un `.exe` dentro se rechaza; el generador es determinista y cada paquete de serie está completo (núcleo y complementos de serie); la página Sonidos, el mapa y el asistente pasan `revisar_teclado`; `migrar_1x` con `operacion_terminada.wav` en `data/sounds/` crea «Mis sonidos 1.x» con ese archivo para `op.fin` y lo elige, y una segunda vez no hace nada; con «sustituir anuncios», un evento que no puede sonar (volumen 0 o uno de prioridad mayor sonando) no omite su texto.
- **AC** (las de la plantilla, adaptadas: firma, versiones, anti-retroceso, descarga, ZIP peligrosos, diálogo y sustitución real con el `.bat` sobre una instalación falsa, unos 40 s, marca `lento`): además, el `.bat` con la marca `iniciado` espera más de 60 s a `ok`; si a los 300 s el proceso de ese PID sigue vivo no vuelve atrás y deja «salud sin confirmar», y si murió sin `ok` vuelve atrás; sin `iniciado` vuelve atrás a los 60 s; tras actualizar, una restauración pendiente no se pregunta antes de `ok`; `DATA_ENTRANTE` lleva `data/bin` del paquete a `data/bin/.entrante/` sin tocar los componentes activos; `tools/publicar.py --servidor` sobre una carpeta temporal copia el ZIP antes que `version.json`, y con `--firmar-complementos` crea un `.zcplugin` que `firma.verificar_complemento` acepta con la clave de prueba.
- **CO** (`tests/servicios/test_co_*.py`, `tests/ui/test_co_componentes.py`): con un servidor local que imita la API de GitHub y el índice de MSYS2, detecta la versión nueva; un paquete con suma distinta se rechaza sin tocar nada; un componente cuya prueba falla tras sustituir vuelve solo al respaldo (sumas iguales a las de antes); «Restaurar los originales» deja las sumas de `linea_base.json`; un componente en uso con `al_reiniciar` queda pendiente y se aplica en el arranque simulado; un `instalando.json` a medias se termina (si `.nueva` tiene las `sumas_nueva`) o se deshace al arrancar sin dejar archivos mezclados; un renombrado que falla (carpeta abierta en la prueba) se reintenta y, si sigue fallando, queda pendiente para el reinicio; un componente con `esperar_s` espera a que acabe su proceso; un componente en mantenimiento responde «falta» a `ruta()`; una ficha `latest` con el mismo `digest` no ofrece nada y con otro ofrece la compilación nueva; los `.7z` y `.pkg.tar.zst` se extraen sin libarchive; `integrar_entrante` conserva un componente más nuevo que la base y, si la aplicación vuelve atrás sin confirmar su salud, lo integrado se revierte; `--probar-componente libarchive` devuelve 0 con la DLL real (marca `componentes`) aunque haya otra instancia abierta; el diálogo pasa `revisar_teclado`.
- **CS** (`tests/servicios/test_cs_*.py`, `tests/ui/test_cs_*.py`): crear y restaurar en un `data` vacío reproduce los archivos byte a byte; los secretos se recuperan con la contraseña y una contraseña mala no restaura nada; «combinar» favoritos añade los nuevos y conserva los actuales; «sustituir» deja la parte igual a la copia; la copia automática previa existe y restaurarla deja el estado anterior; una copia con `formato` 99 se rechaza; la restauración pendiente se aplica antes de cargar la configuración; una parte «En el momento» emite `al_restaurar` y un servicio suscrito vuelve a leer su archivo; la parte `complementos` no escribe en `data/plugins/` ni trae `claves.json` ni `complementos.confiados`, y ofrece cada paquete por la instalación normal; el manifiesto canónico de los datos asociados no depende del orden de las claves; un `.zcperfil` nunca contiene `secretos.bin` ni `conexiones`, y su vista previa muestra los alias y las macros aparte y sin marcar; una restauración preparada con «Más tarde» pregunta al arrancar y «Descartarla» borra la carpeta pendiente; la copia automática previa de una restauración pendiente se crea al aplicarla, no al prepararla; el menú de usuario, los alias y `comprimidos.ruta_7zip` de una copia no se restauran si no se marcan; al combinar, una huella de servidor nueva no se añade sin confirmarla; la copia no lleva `complementos.permitir_sin_firma` ni `seguridad.menus_locales_confiados`, y una copia ajena que los trae no los restaura; `editor.externo` y una clave de complemento con `ejecuta = true` no se restauran sin marcarlas; un `rclone.conf` con un remoto con `bearer_token_command` lo lista sin marcar y, sin marcarlo, el remoto no se restaura; los diálogos pasan `revisar_teclado`.
- **CM** (`tests/servicios/test_cm_*.py`, con datos de prueba de `tests/datos/comprimidos/`: los RAR, RAR5, CAB, LHA, ISO, XAR y 7z BCJ2 pequeños de la batería de pruebas de libarchive, licencia BSD, copiados con su aviso; el resto se genera en la prueba): cada formato de 8.1 se lista y extrae (marca `componentes`); una entrada con `../` se omite; un RAR cifrado sin 7-Zip da el mensaje de 8.2 y no «contraseña incorrecta»; `.tar.zst` y `.zst` se crean y leen con Python; un ZIP con método 93 se lee y escribe; crear un ZIP AES-256 con libarchive y leerlo con la contraseña; 7za crea un 7z con contraseña por la entrada estándar (nunca en los argumentos: se comprueba la lista de argumentos) y sin contraseña no lleva `-p`; `nombre.txt.gz` se ve como carpeta con `nombre.txt`; un RAR multivolumen con nombre no ASCII se abre desde la primera parte.
- **RD** (`tests/servicios/test_rd_*.py`, `tests/ui/test_rd_*.py`, con `win32wnet`, `win32net` y WMI simulados): la raíz «Red» muestra unidades, conexiones sin letra y recientes con su tipo y estado; el descubrimiento añade equipos sin mover el cursor y Escape lo cancela; 1201 al entrar ofrece reconectar; 1219 ofrece cerrar las conexiones; 2401 pregunta antes de forzar; `conectar` con «Recordar» llama a `CredWrite` con `CRED_TYPE_DOMAIN_PASSWORD` y nunca guarda la contraseña en zCommander; la llamada de la 1.x `red.conectar(letra, remoto, usuario, contrasena, recordar)` sigue funcionando; 1272 da el mensaje de invitado bloqueado; `pedir_credenciales` desde un hilo devuelve usuario, contraseña y «recordar»; `copiar_ruta_unc` de `Z:\a` da `\\srv\rec\a`; los diálogos pasan `revisar_teclado`; una prueba real (`interfaz`) lista los recursos de `\\localhost`.
- **PE** (`tests/servicios/test_pe_*.py`, `tests/ui/test_pe_*.py`): grabar ir a carpeta, marcar por patrón y copiar sin diálogo produce los tres pasos con sus argumentos y reproducirlos da el mismo resultado; una macro se detiene en el paso que falla; un paso con una orden de un complemento que se está cargando no deja empezar el siguiente hasta que se ha ejecutado; los esquemas no chocan; aplicar el de Explorador deja F2 en renombrar; un alias con `%1` y un nombre peligroso se expande protegido (1.x §14); `zc ir_a_carpeta D:\x` cambia el panel sin lanzar procesos; abrir un espacio de trabajo restaura pestañas y vistas y guarda «Anterior»; una regla «más de 1 GB» con texto pone la columna Regla y su sonido; con `vista.menus_por_nivel` y perfil Novato el menú Archivos no muestra «Crear enlace»; una confirmación silenciada no pregunta y la lista de Confirmaciones la recupera; «Eliminar definitivamente» no es silenciable; la vista por carpeta de contenido se aplica con un 60 % de MP3; la búsqueda en Preferencias encuentra «papelera»; arrancar con Windows escribe y borra el valor (`interfaz`, en una clave de prueba); las teclas globales registran y liberan (`interfaz`); cada diálogo pasa `revisar_teclado`.
- **NV** (las de la plantilla del agente: constructor, código del complemento con un NVDA falso, instalación con diálogo simulado): además, el appModule decodifica la propiedad `zCommander.OrdenLectura` que publica `senales_nvda.py` para `[0, 3, 1]` y para 15 columnas (el máximo); el paquete generado tiene `minimumNVDAVersion = 2026.1` y la versión de zCommander. (La codificación y las llamadas de `senales_nvda.py` las prueba N2.)
- **LI** (`tests/test_li_licencias.py`): todo archivo propio tiene la cabecera SPDX; `LEEME-LICENCIAS.md` lista cada componente de `linea_base.json` y de `requirements.txt`; la compilación no contiene las seis DLL (`lento`); «Acerca de» pasa `revisar_teclado` y muestra la frase de la licencia.
- **P1 a P5, NU, NS**: las «Pruebas mínimas» de cada ficha (11.1 a 11.25, 12.13 y 13.13), más, por complemento: su manifiesto completo valida, sus órdenes tienen manejador real (ninguno marcado con `api.provisional`), sus funciones exportadas (11.0) tienen la firma de la tabla, sus ventanas pasan `revisar_teclado`, sus sonidos existen en los 5 paquetes, la prueba de choques de teclas pasa con su manifiesto, y `tools/validar_plugin.py` devuelve 0.
- **DO**: `tools/comprobar_teclas.py` sin teclas sin documentar (también las de los complementos y las de las ventanas nuevas); cada sección 3 a 13 tiene su apartado en el manual; cada complemento de serie tiene `doc/es/leeme.md` con todas sus órdenes; `tools/notas_version.py` encuentra las notas de la 2.0.

## 19. Plan de trabajo

Como en la 1.x (1.x §20): primero un núcleo que fija los contratos, los conecta con la 1.x y deja provisionales; después bloques en paralelo, cada uno dueño exclusivo de sus archivos; la documentación al final.

### 19.1 Núcleo 2.0 (N2, primero)

N2 es **un solo bloque**: fija todos los contratos y hace todos los enganches en la 1.x. **Ningún otro bloque empieza hasta que N2 termina**; así, cuando empiezan, cada contrato existe, la interfaz ya lo usa y ningún bloque tiene que esperar a que otro cierre un archivo compartido. «Dueño posterior» quiere decir que N2 crea o cambia el archivo y después solo lo edita ese bloque, para lo suyo. Los archivos de N2 sin dueño posterior no los edita nadie más.

N2 trabaja en este orden interno (cada paso se apoya en el anterior). Las 759 pruebas de la 1.x se ejecutan al cerrar cada paso; las que el diseño cambia se reescriben en el mismo paso que el cambio (18.1).

**0. Pruebas de arquitectura**, antes que nada: `tests/test_n_arquitectura.py` modificada como dice 18.1, con todos los bloques en `BLOQUES_ABIERTOS`, y las fixtures `complementos_serie`, `registro_vacio` y el reinicio del bus en `tests/conftest.py`.

**1. Contratos sin wx** (lo que otros bloques importan o implementan):
- **Complementos**: `app/plugins/api.py` completa como contrato (lo que no esté implementado lanza `NoAdmitido` por `api._sin_implementar`, 18.1), con `ContextoComplemento`, `api.provisional`, `api.pruebas`, `fijar_interfaz` y las fachadas que delegan en las funciones de destino de 3.7; `interfaz.py` (`InterfazAnfitrion`, 3.7); `estado.py` (`EstadoComplemento`, `Pendiente`, `llamar_protegido`, vigilante de bloqueos, 3.8); `firma.py` completo (3.9); `serie.py` (3.2); `manifiesto.py` (también `codigos_windows` y `ejecuta`); `app/plugins/registro.py` (`ColumnaExterna`, `valor_columna`, `lineas_info`, `AccionAplicable`, `ObjetivoCongelado`, `registrar_serie`, `vaciar`, 3.13); `cargador.py` (descubrir con la comprobación de 3.2 y 3.9, registrar marcadores, máquina de estados de 3.4 con dependencias, hilo `zc-cargador` y tope de carga, `CargadorVerificado`, centinelas por id, `MetaPathFinder` de `lib/`, `fijar_planificador`, `arrancar`, `congelar`, `descongelar`, `cerrar` y `ejecutar_tarea_programada`); `config_plugins.py`; instantánea provisional `tests/datos/api_1_0.json` (se congela al cerrar PL y P1, 3.7); complementos de prueba en `tests/datos/plugins/`: carpetas `ejemplo`, `roto_importar`, `roto_activar` y `lento`, con ids `prueba.ejemplo`, `prueba.roto_importar`, `prueba.roto_activar` y `prueba.lento`.
- **Protocolos de la ventana**: `app/services/servicios_nucleo.py` (`Grabador`, `ServicioMacros` y los demás de 14.9, `VentanaServicios`, `ArranqueInfo`).
- **Tipos de contrato en archivos de la 1.x**: `vfs/base.py` (firmas de los ganchos de 14.5, `UnidadVirtual`, `ResultadoPar`; la base con sus valores por defecto); `operaciones/modelo.py` (`PreguntaError` con `codigo_windows` y `excepcion`, `pedir_credenciales` en `Decisor`, `Operacion.orden_origen`, `RespuestasAutomaticas` y `Operacion.respuestas_automaticas`).
- **Configuración**: claves de 14.3 (54) con reglas, descripciones, páginas y letras; `EJECUTA` (7.2); migración 1 → 2 con prueba; tabla de perfiles; `app/services/confirmaciones.py` (10.12); `TITULAR` en `version.py`; `paths.py` (rutas nuevas y `fijar_recursos`); `core/instancia_unica.py` (`"tarea"` en `ORDENES_VALIDAS`, `MAX_EDAD_TAREA`, `dejar_orden_esperando`).
- **Los 27 complementos de serie como esqueleto**: `plugins/<carpeta>/manifiesto.toml` con la parte de N2 de 3.3 (`id`, `bloque`, campos obligatorios, `[[ordenes]]` e ids de `[[sonidos]]`, tal como dicen las secciones 11 a 13) y `__init__.py` con manejadores `api.provisional`. No se firman (confianza por ubicación con `serie.py`, 3.2).
- **Provisionales en archivos de otros bloques**, cada uno con su firma definitiva y su dueño posterior (el bloque lo completa sin cambiar la firma):

| Archivo | Lo que deja N2 (firma exacta y provisional) | Dueño posterior |
|---|---|---|
| `app/services/copia/pendiente.py` | `aplicar_pendiente(ruta_datos, preguntar) -> ResultadoRestauracion \| None` y `consultar_pendiente(ruta_datos) -> InfoPendiente \| None` (devuelven `None`), `decidir_pendiente(ruta_datos, decision) -> None` (no hace nada), `ResultadoRestauracion`, `InfoPendiente` (7.6) | CS |
| `app/services/componentes/fichas.py` | `validar(datos: dict, *, linea_base: bool) -> list[str]`: mensajes en español, vacía si es válida; completa (el esquema de 6.2) | CO |
| `app/services/componentes/estado.py` | `ruta(id) -> Path`, `ejecutable(id, nombre) -> Path`, `disponible(id) -> bool`, `registrar_al_detener(id, funcion) -> None`, `estado_de(id) -> str`, `lineas_soporte() -> list[str]` (3.7, 14.9) | CO |
| `app/services/componentes/integrar.py` | `aplicar_pendientes(ruta_datos) -> list[str]`, `integrar_entrante(ruta_datos) -> ResumenIntegracion \| None`, `confirmar_integracion() -> None`, `ResumenIntegracion` (14.8) | CO |
| `app/services/componentes/prueba.py` | `probar_componente(id: str, carpeta: Path \| None) -> int` (devuelve 1) | CO |
| `app/services/libarchive/prueba.py` | `probar(carpeta: Path \| None) -> int` (devuelve 1; 0 si libarchive funciona), que llama `probar_componente` | CM |
| `data/bin/linea_base.json` | Línea base provisional con los datos de binarios-descargados.md | CO |
| `app/services/sonidos/paquetes.py` | `migrar_1x(ruta_datos, config) -> bool` (falso), `lineas_soporte() -> list[str]` | SO |
| `app/ui/dialogos/so_pagina_sonidos.py` | `crear(padre: wx.Window, config: Configuracion) -> PaginaPropia` (página provisional, 10.18) | SO |
| `app/services/actualizador.py` | `registrar_comprobacion(nombre, funcion, activa) -> None` (guarda y no hace nada), `Novedad`, `marcar_inicio(tras_actualizar) -> None`, `al_arrancar(tras_actualizar) -> None` (5.2, 5.4) | AC |
| `app/plugins/prueba.py` | `comprobar_complemento(carpeta: Path) -> int` (devuelve 0, 14.8) | PL |
| `app/plugins/gestor.py` | `lineas_soporte() -> list[str]` | PL |
| `app/services/espacios.py` | `listar() -> list[str]` (vacía), `guardar_actual(nombre, nota="") -> None` y `abrir(nombre) -> None` (`NoAdmitido`) (3.7) | PE |
| `app/services/vistas_carpeta.py` | `conjuntos() -> list[str]` (vacía), `proponer_conjunto(...) -> bool` (falso) (3.7) | PE |
| `app/ui/dialogos/pe_confirmaciones.py` | `crear(padre: wx.Window, config: Configuracion) -> PaginaPropia` (página provisional, 10.18) | PE |
| `app/ui/dialogos/pe_teclas_globales.py` | `abrir(padre: wx.Window) -> None` (anuncia «Todavía no disponible», 10.18) | PE |
| `app/ui/dialogos/f_preferencias.py` (de la 1.x) | `abrir(padre: wx.Window, config: Configuracion, pagina: str \| None = None) -> None`: abre el diálogo de la 1.x (`mostrar`) y, si se pide una página, anuncia «Página no disponible» (10.18) | PE |
| `app/ui/dialogos/rd_credenciales.py` | `pedir(padre, titulo, texto, usuario) -> tuple[str, str, bool] \| None` con un diálogo provisional de usuario y contraseña (9.4) | RD |
| `app/ui/instalar_complemento.py` | `abrir(padre: wx.Window) -> None` (botón de 10.18) | NV |
| `app/ui/acciones/{complementos_pl,sonidos_so,componentes_co,actualizar_ac,copia_cs,red_rd,personalizar_pe,nvda_nv}.py` | `instalar(ventana: VentanaServicios) -> None` sin efecto (14.9) y los manejadores provisionales de sus órdenes (en `personalizar_pe.py`, también `ejecutar_macro`); `complementos_pl.ejecutar` y `estado` son reales | El bloque del sufijo |

**2. Catálogo vivo y menús**: `ordenes.py` con `CATALOGO_NUCLEO`, `catalogo()` como instantánea, `CATALOGO` y `POR_ID` vivos, `grabable`, `nivel` y `tecla_global`, `fijar_fuente_macros`, `catalogo_cambiado`, `fijar_modo_desarrollo`, `menus()`, `menu_contextual()` y `letras_submenus` (`MENUS` queda con ids del núcleo, 14.1.1); las 45 órdenes nuevas con sus manejadores provisionales (anuncian «Todavía no disponible») en los módulos de acciones de la tabla anterior; `nivel` de las 181 órdenes de la 1.x; `esquemas_teclas.py` con las diferencias de 10.7; `tools/generar_provisionales.py`, `comprobar_menus.py`, `comprobar_teclas.py` y `generar_anexos.py` con `registrar_serie` (14.1.1); los consumidores que tomaban una copia del catálogo (`f_paleta.py`, `f_mapa_teclas.py`) leen el vivo. Desde aquí, el catálogo y las teclas de todos los complementos de serie son reales y la prueba de choques pasa.

**3. Servicios comunes**: `app/services/eventos.py` (`bus()`, planificador, `emitir_sincrono`, `vaciar`, `cerrar`, `puentear_configuracion`, `al_restaurar` y `al_cambiar_catalogo`), `app/core/red.py`, `app/core/descargas.py`, `app/core/procesos.py` (Job global y anidados, `puede_salir_del_job`, `lanzar_independiente`, 14.9); sonidos: `app/services/sonidos/catalogo.py` completo (los 122 eventos, `CATEGORIAS` y la lectura de los de manifiestos), `servicio.py` con `sonar()` y el protocolo `Reproductor` (4.3) y `app/ui/sonidos.py` reescrito con `iniciar` y `cerrar` y el reproductor provisional (dueño posterior SO); `app/services/macros_argumentos.py`, `app/services/vistas_modelo.py`; `app/ui/paginas_propias.py` (los diccionarios con referencias perezosas, `registrar_dialogo_complemento`, `abrir_preferencias`, 10.18); `app/ui/senales_nvda.py` (10.16); `app/ui/api_ui.py` (dueño posterior PL) y `app/ui/interfaz_anfitrion.py`; `app/core/registro.py` (redacción nueva de 16, también para lo que llega de rclone, y acceso al archivo de `faulthandler` para el vigilante de 3.8); `app/ui/accesibilidad/voz.py` (borrar la rama de `Auto`).

**4. Enganches en la 1.x** (con dueño posterior, ese bloque lo edita después solo para lo suyo):
- `ui/ventana_principal.py`: constructor `VentanaPrincipal(config, instancia=None, *, arranque: ArranqueInfo | None = None)` (14.8; sin `arranque`, `ArranqueInfo.nulo()`); `servicio()` con los nombres de 14.9 y sus nulos, `registrar_servicio`; `api.fijar_interfaz(InterfazVentana(self))`; la tupla `INSTALADORES` y la llamada a cada `instalar` en su orden (14.9); el protocolo `VentanaServicios` (`llamar_mas_tarde`, `esta_libre`, `padre`, `fijar_decorador_fila`, `colocar_barra_botones`, `registrar_tecla_global(id_orden, tecla) -> bool`, `liberar_teclas_globales()`); menús y barra reconstruibles desde `ordenes.menus()` (suscrita a `al_cambiar_catalogo`) y estado de las casillas solo del menú que se abre (14.2); `ejecutar_orden` con argumento y con la llamada directa al grabador (10.1) y `ejecutar_orden_futuro` (3.4); `lanzar_operacion` con `orden_origen`; eventos del bus (`al_ejecutar_orden` y `al_terminar_orden`); los pasos 10 y 11 de 14.8 tras mostrarse; la orden `tarea` del buzón, el modo tarea y su autocierre sin preguntas (11.24); `--al-iniciar-sesion`; `_al_cerrar` en el orden exacto de 3.4 (`congelar`, fase con veto con `puede_cerrar`, `vaciar`, `emitir_sincrono`, `desactivar`, `bus.cerrar`, `cargador.cerrar`, `fijar_interfaz(None)`); las llamadas de la 1.x a `self.sonidos.aviso`, `tonos_activos`, `tono_decision` y `tono_progreso` (que leen `accesibilidad.tonos_progreso`, que la migración borra) pasan a `sonar("op.fin")`, `sonar("op.fin_errores")`, `sonar("op.decision")` y `sonar("op.progreso", variante)`, y la ventana llama a `sonidos.iniciar(config)` y `sonidos.cerrar()` en lugar de crear `Sonidos(config)`.
- `ui/contexto.py` (`sonar`, `argumento`, `ejecutar_orden` con argumento, `ejecutar_orden_futuro`, `lanzar` con `orden_origen`); `ui/anuncios.py` (`sonido`).
- `ui/panel_archivos.py`: eventos del bus, `aplicar_conjunto(conjunto: ConjuntoVista | None)` (10.4), `aplicar_lectura(lectura: list[str])` y el campo `lectura` de cada pestaña en `sesion.json` (10.5), `sonar("nav.carpeta_vacia")` en lugar de `sonidos.aviso("carpeta_vacia")`, la casilla `marcas_cursor` (10.12), llamadas a `senales_nvda.marcar_movimiento_silencioso`.
- `ui/lista_archivos.py`: `fijar_columnas_externas(funcion: Callable[[str, Entrada, Proveedor, Callable[[], None]], str | None])` (la ventana le pasa `registro.valor_columna`; el primer argumento es el id de columna `<id>:<columna>`, el último el aviso para repintar la fila, 3.13), `fijar_decorador_fila(funcion: Callable[[Entrada], EfectoFila | None])` con `EfectoFila(color: str | None, texto: str, sonido: str, anuncio: str)` de `vistas_modelo.py` (color y columna Regla de 10.10), y las llamadas a `senales_nvda`.
- `acciones/archivos.py` (`ABRIR_INTERNO`, valores `zc:`, `orden_origen` en sus llamadas a `lanzar_operacion`, `comprimido_escritura` en lugar de `operaciones.aviso_comprimido_mostrado` y la casilla `marcas_cursor`, 10.12), `windows_g.py` (`orden_origen`), `navegacion.py` (`cancelar` con la lista de 10.1; Intro en un comprimido de un complemento sin activar como continuación, 3.4), y los manejadores y diálogos de las órdenes de `ARGUMENTOS` (10.1): `dialogos/copiar.py`, `nombre.py`, `c_comprimir.py` (dueño posterior CM), `marcas.py`, `vista.py`, `comprimidos_c.py`, `linea.py`.
- `vfs/ftp.py` (`debe_preguntar(config, f"ftp_sin_cifrar:{id}")` en lugar de `ftp.avisar_sin_cifrar`, 10.12, y `abrir_escritura` con `tamano`), `vfs/local.py`, `sftp.py`, `resultados.py` (`abrir_escritura` con `tamano`, ganchos); `zip.py` (ídem; dueño posterior CM); `resolver.py` (`registrar_unidades`, `unidades_virtuales`, `abrir_comprimido` con `NoAdmitido` → abrir con la asociación, 14.5); `registro_proveedores.py` (todos los módulos nuevos en `MODULOS`, 8.8).
- `operaciones/copiar.py` (ganchos, identidad antes de `mismo_volumen`, `pares_hechos`, `codigo_windows`), `eliminar.py` y las demás operaciones (`codigo_windows` y `excepcion` en `PreguntaError`), `operaciones/comprimir.py` (argumento de macros; dueño posterior CM).
- `ui/decisiones.py`: acciones extra por `acciones_error_aplicables` con el filtro del manifiesto y la activación al pulsar (3.4, 14.6), `pedir_credenciales` con `rd_credenciales.pedir`, respuestas automáticas (14.6).
- Las llamadas `sonar(...)` de los puntos del núcleo 1.x de la lista de N2 en 4.3.
- `ui/vistas.py` y `acciones/consulta.py`: líneas de información de `app.plugins.registro.lineas_info`, en un hilo.
- `dialogos/f_unidades.py` (unidades virtuales y activación en segundo plano de las dinámicas, 3.4); `f_paleta.py` y `f_mapa_teclas.py` (catálogo vivo; dueño posterior PE); `f_preferencias.py` (`abrir` provisional; dueño posterior PE).
- `services/linea_ordenes.py` (`zc <orden>` y órdenes internas de complementos; dueño posterior PE); `services/busqueda.py` y `dialogos/b_buscar.py` (`Criterios` admite motor y extractores de complementos; dueño posterior PL); `services/renombrado.py` (máscaras de complementos con la regla de choques de 3.3; dueño posterior PL) y `dialogos/e_renombrado.py` (vista previa calculada en un hilo con «…», 3.4); `ui/ventanas/visor.py` (`Documento`; dueño posterior PL).
- Servicios de la 1.x con datos de la parte `personalizacion`: `recargar()` y su suscripción a `al_restaurar` en favoritos, menú de usuario, asociaciones, plantillas de renombrado y búsquedas guardadas (14.4).
- «Información para soporte» (14.9), `data/cache/arranques.json` y la propuesta del modo seguro tras dos cierres anómalos (3.8), Mayús al arrancar con `GetAsyncKeyState` (3.4).

**5. Arranque**: `main.py` (todo 14.8: `argparse`, planificadores tras `wx.App`, `--tarea` sin instancia con `lanzar_independiente` y `dejar_orden_esperando`, `--modo-tarea`, `fijar_recursos` en `--comprobar-arranque`, `puentear_configuracion`, `ArranqueInfo` y los puntos de entrada provisionales).

**6. Pruebas, lista de teclas y anexos**: todas las de N2 de 18.2 y las de la 1.x reescritas de 18.1; `data/docs/teclas.md` al día con las teclas de las 45 órdenes nuevas del núcleo (14.1.2) y **un apartado por cada complemento de serie** con las teclas de su manifiesto; `tools/generar_anexos.py` genera `ordenes.md` y `configuracion.md` con los complementos, `data/docs/sonidos.md`, `docs/componentes.md` (desde el `linea_base.json` provisional) y `app/plugins/serie.py`.

**Criterio de salida de N2** (todos los demás bloques empiezan cuando se cumple):
- Las **759 pruebas de la 1.x en verde**, con las de 18.1 reescritas y las de `tests/test_n_arquitectura.py` modificadas con todos los bloques en `BLOQUES_ABIERTOS`.
- **Todas las pruebas de N2 de 18.2** en verde, archivo por archivo.
- `data/docs/teclas.md` actualizado con las 45 órdenes del núcleo y un apartado por complemento de serie (`test_lista_de_teclas_coincide_con_el_codigo` en verde); prueba de choques de teclas (con los cuatro esquemas) y de menús en verde; anexos al día; las cifras de 0.6 coinciden con los anexos generados.
- Catálogo completo (núcleo y 27 complementos) con manejadores reales o provisionales; un complemento de ejemplo se descubre, se activa al ejecutar su orden (con la máquina de estados de 3.4) y sus fallos se aíslan.
- Cada provisional de la tabla del paso 1 existe con su firma; cada enganche del paso 4 existe con su firma y lo usa la interfaz; la ventana llama a cada `instalar` y los nombres nuevos de `servicio()` existen con sus nulos; las llamadas de sonido de N2 de 4.3 están puestas.
- El catálogo de sonidos está completo y la migración de configuración pasa sus pruebas.

**Camino crítico**: N2 → PL → integración de los complementos de serie en la interfaz (P1 a P5, NU, NS) → DO. Todo lo demás (SO, AC, CO, CS, CM, RD, PE, NV y LI) corre en paralelo con ese camino a partir del final de N2. PL es el bloque más cargado del camino: mientras no termina, los complementos prueban sus funciones con `api.pruebas` (19.3).

### 19.2 Bloques (en paralelo tras N2)

Cada bloque escribe solo sus archivos (14.10) y su módulo de `acciones` (con su función `instalar`, 14.9); usa los contratos y los enganches que dejó N2 sin editar los archivos donde están, salvo aquellos de los que es dueño posterior (19.1). Si necesita algo que no está, lo pide: lo de `api.py` a su dueño del momento (3.7) y lo demás al coordinador, que lo hace y actualiza este documento.

- **PL, complementos**: sección 3 completa sobre lo que dejó N2 (gestor, paquetes, firma, protección completa, instalación, actualización, desinstalación, puntos de extensión enganchados en la interfaz: columnas, visores con `Documento` y teclas nuevas del visor de 14.7 en `ui/ventanas/visor.py`, información, búsqueda, extractores, máscaras en `services/renombrado.py`, acciones de error, preferencias de complementos), gestor, herramientas para autores, guía técnica para DO.
- **SO, sonidos**: sección 4 completa (motor, paquetes, página, asistente, mapa, generador y los 5 paquetes).
- **AC, actualizador de la aplicación**: sección 5.
- **CO, actualizador de componentes**: sección 6 (`componentes.json` y `linea_base.json` definitivos con las sumas de los archivos instalados).
- **CS, copia de seguridad**: sección 7 y todo el `.zcperfil` de 10.2 (formato, órdenes `perfil_exportar` y `perfil_importar`, vista previa).
- **CM, comprimidos**: sección 8.
- **RD, red**: sección 9.
- **PE, personalización**: sección 10 salvo el `.zcperfil` de 10.2 (CS) y 10.16 (NV); incluye el diálogo de Preferencias 2.0 (10.18) con las páginas declarativas de los complementos y `f_preferencias.abrir` con su página.
- **NV, complemento de NVDA**: 10.16 (el appModule; `senales_nvda.py` lo deja N2).
- **LI, licencias y compilación**: sección 2 y 17 (también `serie_sumas.py` en `setup_cx.py`, 3.2).
- **P1, multimedia**: reproductor (11.1), metadatos (11.4), conversor FFmpeg (11.6), imágenes (11.11), lectura en voz (11.17).
- **P2, documentos y datos**: documentos (11.2), OCR (11.3), editor hexadecimal (11.10), datos tabulares (11.22), codificaciones (11.25).
- **P3, orden y limpieza**: duplicados (11.7), ocupación (11.8), notas (11.14), papelera (11.20), organizador (11.23).
- **P4, sistema y seguridad**: procesos (11.9), cifrado (11.13), portapapeles (11.16), seguridad (11.19), Git (11.21).
- **P5, automatización**: búsqueda instantánea (11.5), sincronización (11.12), proyectos (11.15), monitor (11.18), programador (11.24: su `ejecutar_tarea` exportada, a la que llama `cargador.ejecutar_tarea_programada` que dejó N2, sin editar `main.py` ni la ventana).
- **NU, Nubes**: sección 12.
- **NS, NAS Synology**: sección 13 con el simulador.
- **DO, documentación** (al final): manual (un apartado por cada sección 3 a 13), revisión de la lista de teclas, registro de cambios de la 2.0, `docs/pruebas-manuales.md` parte 2.0, guía del autor de complementos (`docs/complementos/guia.md`), revisión de las ayudas de los 27 complementos, LEEME.

### 19.3 Dependencias entre bloques

- Todos dependen de N2 y empiezan cuando N2 cumple su criterio de salida. Lo que necesitan para engancharse a la aplicación ya está: los contratos, los enganches en la 1.x, los nombres de `servicio()` con sus nulos, `registrar_servicio`, la función `instalar` de su módulo de acciones que la ventana ya llama (14.9), `InterfazAnfitrion` y el bus único. Ninguno edita `ordenes.py`, `configuracion.py`, `descripciones_config.py`, `catalogo.py` ni `servicio.py` de sonidos, `main.py`, `ventana_principal.py`, `paginas_propias.py`, los manifiestos de otro bloque ni los archivos de 19.1 de los que no es dueño posterior. `api.py` tiene un único dueño en cada momento (N2, después PL, después el coordinador; 3.7), y `cargador.py`, `estado.py`, `firma.py` e `interfaz.py` solo los edita PL tras N2.
- PL antes que nada que necesite columnas, visores, búsqueda, máscaras, acciones de error o funciones exportadas **enganchados en la interfaz** (P1, P2, P3, P4, P5, NU, NS); mientras tanto, los complementos prueban sus funciones con `api.pruebas`.
- PL y PE: las páginas de Preferencias de los complementos aparecen en el `Treebook` de PE (10.18); la prueba de PL «aparece en Preferencias» se cierra cuando PE ha terminado el diálogo (hasta entonces, PL la prueba con la página construida sin diálogo).
- AC antes que la comprobación periódica de CO y de PL (`registrar_comprobacion`, 5.4); mientras, CO y PL prueban su función de comprobación sola. AC depende a su vez de CO para `confirmar_integracion` (5.4, 6.7): mientras CO no termina, llama al provisional de N2.
- CO antes que la integración final de CM (la DLL la localiza `componentes`), P1 (FFmpeg) y NU (rclone, que registra su `al_detener`); mientras, usan las rutas de `data/bin` de la línea base provisional. CO no depende de CM (6.6 extrae sin libarchive).
- LI depende de CO para la `linea_base.json` definitiva que lee `comprobar_licencias.py`.
- SO antes que los paquetes completos de los complementos (el generador crea sus sonidos desde sus manifiestos completos).
- CS depende de PE y SO para la restauración «En el momento» (sus servicios se suscriben a `al_restaurar` con `recargar()`, 14.4; NU no tiene datos «En el momento»), de PL para ofrecer los complementos de una copia por la instalación normal (7.6) y de CO para leer el `rclone.conf` de una copia con el `rclone` de `componentes` (7.2; mientras, con el de la línea base provisional). PE no depende de CS: el `.zcperfil` es entero de CS.
- P4 (acción de error de `zc.procesos`) usa el gestor de decisiones de N2 (14.6), no cambia operaciones.
- P5 (proyectos) usa los espacios de trabajo de PE por `zc.espacios`, y P1 (`columnas_musica`) las vistas por carpeta de PE por `zc.vistas`: hasta que PE termine, esas llamadas se prueban con `api.pruebas`.
- Entre complementos de bloques distintos (tabla de 11.0): quien usa una función exportada tiene que funcionar sin ella, así que ningún bloque espera a otro; la prueba conjunta se hace cuando los dos han terminado.
- NV usa `senales_nvda.py` y las llamadas que deja N2 (10.16); no depende de PE.
- NU usa los ganchos VFS de N2 (`transferir`, `transferir_lote`, identidad de `servidor`) y el gancho `puede_cerrar` (3.4); NS no depende de nadie más que de N2 y PL.
- DO depende de todos.
- **Camino crítico** (19.1): N2 → PL → integración de los complementos de serie → DO. La instantánea de la API se congela al cerrar PL y P1.

### 19.4 Definición de terminado (cada bloque)

- Todas sus funciones programadas, sin «pendiente», `NotImplementedError`, el aviso provisional ni manejadores `api.provisional`; el bloque se quita de `BLOQUES_ABIERTOS` en `tests/test_n_arquitectura.py` y `test_ningun_manejador_provisional` y `test_sin_pendientes_en_el_codigo` siguen en verde (18.1).
- Sus pruebas de 18.2 pasan y no rompen las demás; `ruff check` limpio.
- PE y los bloques de complementos (P1 a P5, NU, NS): `tests/ui/test_n2_teclas.py` en verde con sus esquemas o sus manifiestos completos.
- Si añade teclas propias de una ventana, o cambia las de un complemento de serie, las añade en su apartado de `data/docs/teclas.md` (solo esas líneas; DO revisa el texto al final) y `test_lista_de_teclas_coincide_con_el_codigo` sigue en verde.
- Su función `instalar` (14.9), si la tiene, hace lo suyo y nada más, sin el aviso provisional.
- Sus ventanas y diálogos pasan `revisar_teclado`.
- Sus textos visibles en español, con anuncios por niveles y sonidos del catálogo.
- Si toca algo visible: lo que necesita DO apuntado en `docs/notas-documentacion.md` (sección por bloque).
- Lo no verificado con lectores reales queda listado como pendiente.

## 20. Riesgos

1. **Aislamiento de complementos**: un complemento puede colgar o tumbar el proceso (código nativo, bucles en el hilo de la interfaz). Impacto alto. Mitigación: 3.8 (protegidas, centinela, modo seguro, `faulthandler`); complementos de serie revisados. Señal: arranques que mueren con el centinela presente.
2. **Rendimiento de arranque** con 27 complementos: leer manifiestos y construir catálogo y menús. Mitigación: `indice.json`, carga perezosa, presupuesto medido (1.2.5). Señal: la prueba lenta falla.
3. **Choques de teclas y letras** en un catálogo que crece y cambia con lo que instala la persona. Mitigación: prueba de choques con los de serie y los cuatro esquemas; los de terceros se quedan sin tecla y se avisa; `comprobar_menus` sobre el catálogo completo.
4. **Lectores reales**: los diálogos de espera, el editor hexadecimal (cursor de bytes propio), la barra de botones y el visor de tablas solo se prueban con MSAA. Mitigación: pruebas manuales al terminar cada bloque; alternativa preparada en el editor hexadecimal: modo «una línea por byte» en una lista.
5. **Python 3.15 y ruedas**: Pillow y `winrt-*` pueden no tener ruedas cp315. Mitigación: alternativas sin ellas ya diseñadas (wx + propiedades de Windows; OCR con PowerShell). Señal: `pip download` sin rueda.
6. **Cadena de suministro de componentes**: la suma SHA-256 viene del mismo origen que el binario; sin verificar la firma PGP, un origen comprometido podría colar un binario. Impacto alto pero poco probable. Mitigación: https, sumas publicadas aparte (`SHA256SUMS`, índice de MSYS2), prueba de funcionamiento, respaldo y vuelta atrás, nunca automático. Mejora futura: un índice de componentes probado y firmado con Ed25519 por el proyecto en `xebolax.synology.me`.
7. **Google Drive**: el identificador compartido de rclone se retira en 2026; sin identificador propio, Drive dejará de funcionar. Mitigación: guía accesible (12.5), aviso en el asistente y la carpeta de Google Drive para escritorio como alternativa. Decidido en 21.2.2: el proyecto no registra una aplicación propia (nubes.md 4.2).
8. **Tamaño de la distribución**: unos 330 MB comprimidos por FFmpeg y rclone. Mitigación posible si molesta: marcar `ffmpeg` y `rclone` como opcionales en la línea base y ofrecer su descarga desde «Componentes externos» con permiso (el diseño ya lo permite con `opcional`).
9. **Licencias**: obligación de fuentes de FFmpeg GPL (todas sus bibliotecas) y de los LGPL durante tres años (el titular ya está fijado, 21.2.1). Mitigación: `fuentes_terceros.py` y `comprobar_licencias.py` en la publicación.
10. **API web de DSM sin documentar** (Docker, Drive, Photos, Storage) y apretón de manos Noise de DSM 7.3: pueden cambiar o exigirse. Mitigación: catálogo como guía, respuestas reales a capturar en el NAS con permiso (synology.md 7.8), simulador como referencia; plan B Noise (synology.md 2.3).
11. **Bloqueo de IP del NAS** por intentos fallidos: mitigado con un intento por acción y sin reintentos de contraseña.
12. **WebClient obsoleto y SMB1 retirado**: descubrimiento por Function Discovery y mDNS; WebDAV propio en el complemento Nubes.
13. **`PlaySoundW` asíncrono desde memoria**: si el búfer se libera antes de tiempo, se oiría basura o fallaría. Mitigación: referencia guardada hasta el final y pruebas con muchos sonidos seguidos; alternativa: escribir el WAV escalado a `data/cache/sonidos/` y reproducir desde archivo.
14. **Restauraciones a medias** (corte de luz al aplicar): mitigado con aplicación al arrancar antes de cargar nada y copia automática previa.
15. **Alcance**: la 2.0 es mayor que la 1.0. Mitigación: contratos fijados por N2, bloques independientes, complementos que se pueden publicar uno a uno (un complemento de serie sin terminar puede salir inhabilitado en una 2.0 si su bloque se retrasa, con la decisión del coordinador).

## 21. Historial del documento y dudas resueltas

### 21.1 Historial

- 2.0-borrador (8 de noviembre de 2026): primera versión del diseño de zCommander 2.0 sobre el diseño 1.5 (zCommander 1.0.0, 759 pruebas), con las trece decisiones tomadas por la persona usuaria (licencia, binarios, actualizador, componentes, copias, complementos, 25 complementos de serie, Nubes, NAS Synology, comprimidos, red, sonidos y personalización) y la investigación de `docs/investigacion/`. Copia guardada en [revision/diseno-2.0-borrador.md](revision/diseno-2.0-borrador.md).
- 2.0-borrador 2 (8 de noviembre de 2026): ronda 1 de la revisión EGM de la 2.0 (comprensión, preparación para implementar, crítica de diseño y exactitud técnica; unos 100 hallazgos) resuelta con las decisiones del coordinador; acta en [revision/ronda-2-1.md](revision/ronda-2-1.md). Cambios principales: módulos comunes nuevos de N2 (`app/core/procesos.py`, `app/services/sonidos/servicio.py`, `app/services/confirmaciones.py`, `app/ui/paginas_propias.py`, `app/ui/senales_nvda.py`, `vistas_modelo.py`, `macros_argumentos.py`, `no_interactivo.py`); `ContextoComplemento` y funciones exportadas entre complementos; activación con candado, centinela por id y `activar()` en el hilo de la interfaz; `lib/` sin `sys.path`; firma con clave fijada por id; `CATALOGO` y `POR_ID` vivos; manifiestos de serie de cada bloque; orden de arranque de `main.py` con puntos de entrada; componentes en mantenimiento y con diario; cifras comprobadas en 0.6.
- 2.0-borrador 3 (8 de noviembre de 2026): ronda 2 de la revisión EGM (preparación para implementar, diseño y seguridad, y comprensión; 56 hallazgos) resuelta con las decisiones del coordinador; acta en [revision/ronda-2-2.md](revision/ronda-2-2.md) y copia del borrador 2 en [revision/diseno-2.0-borrador-2.md](revision/diseno-2.0-borrador-2.md). Cambios principales: las tareas programadas se ejecutan siempre en la instancia normal (orden `tarea` de la instancia única, modo tarea minimizado, `RespuestasAutomaticas`; desaparecen el modo sin ventana, el mutex `zCommander-tarea` y `DecisorNoInteractivo`); confianza por ubicación de `<raíz>/plugins/` y firma solo para los `zc.*` de `data/plugins/`, con `app/plugins/firma.py`; activación como máquina de estados en el hilo de la interfaz (`asegurar_activo`) sin candados ni interbloqueos, con `estado.py`; clave fijada exigida al cargar, sumas antes de importar y complementos «Sin aceptar»; N2 dividido en N2a (contratos y provisionales en archivos de otros bloques) y N2b (enganches), con camino crítico y la API congelada al cerrar PL y P1; contratos nuevos (destino de las fachadas, `Reproductor`, `ResultadoRestauracion`, `ResumenIntegracion`, `ResultadoPar`, `ColumnaExterna`, `valor_columna`, `AccionAplicable`, grabación síncrona de macros, `fijar_fuente_macros` y `al_cambiar_catalogo`, `paneles.lectura`); rclone sin `--log-file`, con credenciales por intento y dueño del puerto comprobado; lista «Órdenes que se podrán ejecutar» en `.zcbackup` y `.zcmacro`; salud del actualizador en dos fases; restauración pendiente con pregunta y copia previa al aplicar; `procesos.lanzar_independiente` y creación suspendida; cierre con `emitir_sincrono`; habilitar e inhabilitar frente a activar; máscaras `[MP3:…]`; `zc.tablas`; 54 claves del núcleo y 20 bloques.
- 2.0-borrador 4 (8 de noviembre de 2026): ronda 3 de la revisión EGM (preparación para implementar, y diseño y seguridad; 22 hallazgos, 5 bloqueantes) resuelta con las decisiones del coordinador; acta en [revision/ronda-2-3.md](revision/ronda-2-3.md) y copia del borrador 3 en [revision/diseno-2.0-borrador-3.md](revision/diseno-2.0-borrador-3.md). Cambios principales: **N2 vuelve a ser un solo bloque** (contratos sin wx, catálogo vivo y menús, servicios comunes, enganches en la 1.x, `main.py` y pruebas, en ese orden), con criterio de salida que incluye las 759 pruebas de la 1.x (con la lista de las que se reescriben en 18.1), `data/docs/teclas.md` al día y todas sus pruebas de 18.2, separadas por archivo; 19 bloques; enganches de arranque `instalar(ventana: VentanaServicios)` por módulo de bloque, en orden fijo, con `registrar_servicio`; inyección única de la interfaz en la API (`InterfazAnfitrion`, `api.fijar_interfaz`), bus único `eventos.bus()` con `vaciar` y puente de la configuración, `ArranqueInfo` y planificadores fijados tras crear `wx.App`; `ordenes.menus()` y `menu_contextual()` con `MENUS` solo del núcleo, `letras_submenus`, `fijar_modo_desarrollo` y `registro.registrar_serie`; activación con dependencias encadenadas, hilo `zc-cargador` con tope de 30 s, continuaciones publicadas fuera de `set_result`, instantánea del objetivo, `ejecutar_orden_futuro` para macros y tareas, columnas que no gastan tiempo en la carga, sin diálogos en `activar()` y comportamiento sin activar de comprimidos, vista previa del renombrado y acciones de error (`codigos_windows`); cierre en orden exacto dentro de `_al_cerrar` (`congelar`, `puede_cerrar`, `vaciar`); tareas programadas lanzadas como instancia real fuera del Job del Programador (`--modo-tarea`, `dejar_orden_esperando`), ajustes de la tarea de Windows y autocierre sin preguntas; claves `ejecuta` (`EJECUTA`) y remotos de rclone que ejecutan programas en la lista sin marcar de las copias, y `seguridad.*` fuera de ellas; salud del actualizador que no revierte con el proceso nuevo vivo y restauración pendiente preguntada después de `ok`; cargador de módulos verificado sin `.pyc` para `data/plugins`, confianza por ubicación solo para la lista `app/plugins/serie.py` y modelo de amenaza en 16; Job anidado por proceso con `TerminateJobObject` y `puede_salir_del_job`; firmas exactas de todos los provisionales (`fichas.validar`, `libarchive.prueba.probar`, `f_preferencias.abrir`...).
- 2.0-borrador 5 (8 de noviembre de 2026): precisiones de la ronda 4, aplicadas al programar N2; acta en [revision/ronda-2-4.md](revision/ronda-2-4.md) y copia del borrador 4 en [revision/diseno-2.0-borrador-4.md](revision/diseno-2.0-borrador-4.md). Cambios: `instancia_unica.hay_instancia` (sin wx) en los pasos 2 y 4 de 14.8; `VentanaPrincipal(config, instancia=None, *, arranque=None)` con `ArranqueInfo.nulo()` y `CargadorNulo`; `procesos.ErrorProceso` convertido en `ErrorArchivos` por `Anfitrion.ejecutar_programa`; tabla de las 45 órdenes del núcleo con manejador, estado, ayuda, nivel y tecla global, copiada del código; sonido de progreso decidido por la ventana en su latido y `op.progreso` activo de fábrica, con las pruebas de la 1.x que eso reescribe en 18.1; órdenes `tarea` que no traen la ventana al frente ni cuentan como uso, y qué es «usada»; `debe_preguntar` con el prefijo antes de «:», `ftp_sin_cifrar:<servidor>` sin sitio y `Decisor.elegir_con_casilla`; secuencia propia de `--comprobar-arranque`; marca `provisional = True` de los `instalar`; `ARGUMENTOS: dict[str, Argumento]` con `espacios_trabajo` y `pestana_nueva`.

### 21.2 Dudas resueltas por el coordinador (8 de noviembre de 2026)

1. **Titular del copyright**: «hxebolax» (el nombre con que la persona publica sus proyectos, p. ej. github.com/hxebolax/SocialRSS) y «colaboradores de zCommander». Cabecera SPDX `GPL-3.0-or-later` en cada módulo; Acerca de dice «Copyright © 2026 hxebolax y colaboradores. Licencia GPL-3.0 o posterior». Se fija en `app/core/version.py` como `TITULAR = "hxebolax y colaboradores"` (2.1), que usan la cabecera de cada archivo y «Acerca de».
2. **Google Drive**: «traiga su propio identificador» con una guía accesible paso a paso dentro del asistente; mientras no lo haya, se ofrece la carpeta local de Google Drive para escritorio si existe. No se registra una aplicación de zCommander (exigiría la evaluación anual CASA).
3. **FFmpeg y rclone van en el paquete** (la persona pidió los binarios en `data/bin`). El actualizador de componentes permite actualizarlos y volver a la línea base.
4. **Sonidos activos por defecto** (orientan a la persona ciega, que es el público principal), en instalaciones nuevas **y al actualizar desde la 1.x**: como en la 1.x el valor de fábrica era `false` y se guardaba escrito en `settings.json`, no se puede saber quién los apagó a propósito, así que se activan a todos y la primera vez se anuncia una sola vez «Los sonidos están activados; puede desactivarlos en Preferencias, Sonidos». Los WAV propios de `data/sounds/` de la 1.x pasan a un paquete propio «Mis sonidos 1.x» (4.5). (Revisado en la ronda 2-1: el borrador decía que quien los tenía apagados los conservaba apagados.)
5. Las diferencias de los esquemas de teclas se contrastan con la ayuda oficial de cada programa durante la implementación (bloque PE, sobre el `esquemas_teclas.py` que deja N2 con las de 10.7); lo que no se pueda confirmar se deja como en el esquema Norton, y cualquier cambio vuelve a pasar la prueba de choques.
6. Secure SignIn (aprobación en el móvil) queda fuera; se usa TOTP.
7. El repositorio de FFmpeg-Builds se ha trasladado de `BtbN/FFmpeg-Builds` a `FFmpeg-Builds/FFmpeg-Builds` (GitHub redirige); la ficha usa el nuevo y acepta el antiguo. Asset: `ffmpeg-n<mayor>.<menor>-latest-win64-gpl-shared-<mayor>.<menor>.zip` y `checksums.sha256` de la misma publicación.
8. Firma PGP: se acepta el riesgo residual en la 2.0. La aplicación verifica la suma SHA-256 publicada por el origen, descargada por HTTPS con certificado válido, y la línea base guarda las sumas de cada archivo; un índice de componentes firmado por el proyecto queda para una versión posterior.
9. Ruedas de Pillow y `winrt-*` para 3.15: se comprueban al implementar; si no existen, se usan las alternativas del diseño sin ellas.

### 21.3 Comprobado en este equipo (8 de noviembre de 2026)

Lo que el borrador 2 dejaba «por confirmar al implementar», probado con los binarios de `data/bin`:

- **libarchive 3.8.11** exporta `archive_read_open_filenames_w`, `archive_read_open_filename_w`, `archive_entry_pathname_w`, `archive_read_add_passphrase`, `archive_write_set_options` y `archive_filter_bytes`.
- **7za 26.06, contraseñas sin ponerlas en la línea de órdenes**:
	- *Crear* (`a`) con contraseña: pasar `-p` vacío y escribir la contraseña en la entrada estándar (una línea basta; dos líneas iguales también funcionan). Con `-mhe=on` también. Sin contraseña: no pasar `-p`.
	- *Listar, probar o extraer* (`l`, `t`, `x`, `e`) un comprimido cifrado: **no** pasar `-p`; 7za pide la contraseña y la lee de la entrada estándar. Con `-p` vacío NO la lee (la toma como vacía y falla con «Wrong password»). Para saber si un comprimido está cifrado sin esperar: `-p` vacío y entrada estándar cerrada; falla enseguida.
- **rclone 1.76.0**: `rclone config encryption set` lee la contraseña nueva **dos veces** de la entrada estándar («Enter NEW configuration password» y «Confirm…») y deja el archivo con la cabecera `# Encrypted rclone configuration File` y `RCLONE_ENCRYPT_V0:`. Con `RCLONE_CONFIG_PASS` en el entorno, `rclone config create` añade remotos y el archivo sigue cifrado. La comprobación «el archivo empieza por la marca de cifrado» de §12.3 usa esa cabecera.
