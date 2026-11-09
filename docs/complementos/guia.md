# Guía del autor de complementos de zCommander

Esta guía es para quien programa complementos de zCommander 2.0. Explica cómo se cargan, qué se declara en el manifiesto, qué ofrece la API 1.1, qué reglas de accesibilidad y de seguridad hay que cumplir, cómo se prueban y se publican, y termina con un complemento completo que pasa las herramientas del proyecto.

Lo que dice esta guía está comprobado contra el código de zCommander. La referencia exacta de cada función está en las docstrings de `app/plugins/api.py`; el porqué de cada decisión, en `docs/diseno-2.md`, sección 3.

Convenciones:

- «Complemento» es el término. «Plugin» solo aparece en nombres técnicos como `.zcplugin` o `tools/crear_plugin.py`.
- «Activar» significa cargar el código del complemento. «Habilitar» e «inhabilitar» son decisiones de la persona usuaria.
- `zc` es el objeto `Anfitrion` que recibe el complemento al activarse.
- Las órdenes de consola se escriben para PowerShell y se ejecutan desde la carpeta de zCommander con el Python de su entorno (`.venv\Scripts\python`).

## Qué es un complemento

Un complemento es una carpeta con código Python y un manifiesto (`manifiesto.toml`) que añade a zCommander órdenes, columnas, visores, orígenes de archivos, preferencias, sonidos y ayuda. Se ejecuta dentro del mismo proceso que zCommander, con los mismos permisos de Windows.

Principios que guían todo lo demás:

1. Un complemento nunca empeora la accesibilidad ni la estabilidad de zCommander.
2. Lo que se ve (órdenes, menús, teclas, columnas, preferencias, sonidos, ayuda) se declara en el manifiesto; el código se carga cuando se usa.
3. Solo se importa `app.plugins.api`. Lo demás de `app` puede cambiar sin aviso.
4. La persona decide: ve qué instala, puede inhabilitar, configurar y desinstalar, y puede arrancar sin complementos.

### De serie y de la persona

| Carpeta | Qué contiene |
|---|---|
| `plugins/<carpeta>/` (junto a `main.py` o al ejecutable) | Los 27 complementos de serie. Solo los cambia una actualización de zCommander |
| `data/plugins/<id>/` | Los complementos que instala la persona desde el gestor |
| `data/plugins/.pendientes/<id>/` | Instalaciones y actualizaciones que se aplican al reiniciar |
| `data/plugins/.anteriores/<id>-<versión>/` | Versiones anteriores, para «Volver a la versión anterior» (se guardan dos) |

- El nombre de la carpeta no importa: manda el `id` del manifiesto.
- Un complemento de `plugins/` es «Oficial» solo si su id y su versión están en `app/plugins/serie.py`. Cualquier otra carpeta copiada allí se trata como uno de `data/plugins/`, y el gestor avisa de que se borrará al actualizar zCommander.
- Los id `zc.*` están reservados al proyecto. `tools/crear_plugin.py` los rechaza y el gestor no carga un `zc.*` sin la firma del proyecto.

### Carga perezosa

Al arrancar, zCommander lee y valida los manifiestos y registra los **marcadores**: órdenes en el catálogo y en los menús, teclas, columnas, visores, esquemas, páginas de Preferencias, sonidos... Todo eso sin importar código. El código se importa la primera vez que hace falta:

- La persona ejecuta una de sus órdenes, o una macro o una tarea la ejecuta.
- El panel necesita el valor de una de sus columnas.
- Se abre un archivo con uno de sus visores, o se piden líneas de información.
- Se abre una dirección de uno de sus esquemas (`nube://...`) o un comprimido de una de sus extensiones.
- Se usa su motor de búsqueda, su extractor de texto, una de sus máscaras o una de sus acciones de error.

Mientras no está activo, zCommander responde por él con lo declarado: el estado de las casillas sale de `casilla_defecto`, la disponibilidad en el menú contextual de `disponible_si` y las entradas fijas del selector de unidades de `[[unidades]]`. Abrir un menú nunca activa un complemento.

Si la carga tarda más de 300 ms, se anuncia «Cargando el complemento...». La orden pulsada no se pierde: se guarda una instantánea de los paneles y se ejecuta al terminar la carga, salvo que la persona cambie de carpeta o ejecute otra orden mientras tanto.

### Activación por el manifiesto

El campo `activacion` añade disparadores a los marcadores. Admite dos valores:

- `"al_arrancar"`: se activa tras mostrar la ventana, uno a uno y midiendo el tiempo. Úselo solo si de verdad hace falta (por ejemplo, para vigilar algo desde el principio): alarga cada arranque.
- `"evento:<nombre>"`: se activa la primera vez que se emite ese evento del bus. Desde la API 1.1, el complemento recibe ese primer evento en las funciones que suscribió en `activar()`.

Por defecto, `activacion = []`: basta con los marcadores. Un complemento con `al_arrancar` se instala siempre para el siguiente reinicio.

### Estados

Estos son los estados de `EstadoComplemento` (`app/plugins/estado.py`) y el texto que muestra el gestor.

| Estado | Texto del gestor y significado |
|---|---|
| `REGISTRADO` | «Sin cargar todavía»: marcadores registrados, código sin importar |
| `CARGANDO` | «Cargando»: se está importando y activando |
| `ACTIVO` | «Activo»: código cargado |
| `INHABILITADO` | «Inhabilitado»: la persona lo inhabilitó, o zCommander se cerró mientras lo cargaba |
| `SIN_ACEPTAR` | «Sin aceptar»: sin firma y sin el consentimiento de la persona |
| `INCOMPATIBLE` | «Incompatible»: pide una versión de la API que no hay |
| `FALLIDO` | «Fuera de uso por errores» en esta sesión |
| `ERROR_MANIFIESTO` | «Error en el manifiesto»: no se puede cargar |

Aparte, cada complemento puede tener un cambio pendiente de reiniciar (`Pendiente`: `INSTALAR`, `ACTUALIZAR`, `VOLVER_ATRAS` o `DESINSTALAR`).

### Protección

zCommander se protege de los fallos de un complemento. Conviene saber cómo, porque explica varias reglas de esta guía.

- **Llamadas protegidas**: toda llamada del núcleo al complemento pasa por `estado.llamar_protegido`. Una excepción se registra con el id, la versión y la traza, y se anuncia una vez por sesión: «El complemento X falló al ... Detalles en el registro».
- **Fuera de uso**: tras 3 fallos en la sesión (`complementos.fallos_maximos`), o al primer fallo al importarse o en `activar()`, el complemento pasa a `FALLIDO`. Sus órdenes dicen que no se puede usar y el gestor ofrece inhabilitarlo o volver a intentarlo.
- **Tope de carga**: importar y activar tiene un límite de 30 segundos (`TIEMPO_CARGA_S`). Si se agota, el complemento queda fuera de uso hasta reiniciar.
- **Centinela**: antes de importar se crea un archivo en `data/cache/plugins/cargando/`, que se borra al terminar, vaya bien o mal. Si zCommander muere mientras carga un complemento, el siguiente arranque lo deja fuera y pregunta si inhabilitarlo.
- **Bloqueos de la interfaz**: un vigilante comprueba cada medio segundo si una llamada a un complemento en el hilo de la interfaz pasa de 2 segundos. Si pasa, guarda las trazas de todos los hilos en el registro con el nombre del complemento. El tiempo que la persona pasa en un diálogo abierto con `zc.ui.mostrar_modal` no cuenta.
- **Columnas lentas**: cada valor de columna tiene 5 segundos. Tres agotamientos en una carpeta detienen esa columna en esa carpeta; con 4 hilos abandonados, el complemento deja de recibir peticiones de columnas en la sesión.
- **Modo seguro**: con `--sin-complementos`, con Mayús pulsada al arrancar o con la orden «Reiniciar sin complementos», no se registra ningún complemento.

## Estructura de la carpeta y paquete .zcplugin

Un complemento es una carpeta con esta forma. El paquete `.zcplugin` es un ZIP con ese mismo contenido en la raíz, sin carpeta contenedora y con nombres en UTF-8.

```text
manifiesto.toml          obligatorio
LICENSE                  obligatorio
__init__.py y módulos    el código (la entrada que declara el manifiesto)
doc/es/leeme.md          ayuda: F1 en sus ventanas y botón «Ayuda» del gestor
doc/es/cambios.md        novedades: botón «Novedades» del gestor
sonidos/<id>.wav         sonidos propios por defecto
recursos/                recursos de solo lectura (catálogos, plantillas)
lib/                     bibliotecas de terceros vendorizadas
pruebas/                 pruebas con pytest y api.pruebas
instalacion.py           opcional: al_instalar(zc) y al_desinstalar(zc)
firma.ed25519            opcional: firma del autor
```

`tools/empaquetar_plugin.py` deja fuera las carpetas `__pycache__` y los archivos `.pyc`.

### Dónde guarda sus datos

La carpeta del complemento es de solo lectura: se sustituye entera al actualizar, y la de los de serie no se puede escribir. Lo que el complemento escribe va siempre a:

- `zc.datos`: `data/config/plugins/<id>/`. Sobrevive a las actualizaciones; se borra al desinstalar solo si la persona lo pide.
- `zc.cache`: `data/cache/plugins/<id>/`. Se puede borrar sin perder nada.
- Su configuración: `data/config/plugins/<id>.json`, a través de `zc.config` (ver «Configuración propia»).

### lib/: bibliotecas vendorizadas

- Python puro o `.pyd` para `cp315-win_amd64`.
- `lib/` no se añade a `sys.path`. Importe de forma relativa: `from .lib import pypdf`.
- Para las bibliotecas que se importan a sí mismas por su nombre, el cargador instala un buscador de módulos propio del complemento al final de `sys.meta_path`, que solo resuelve los nombres de nivel superior de su `lib/`.
- Ningún módulo de nivel superior de `lib/` puede llamarse como uno de la biblioteca estándar ni del contrato de bibliotecas (por ejemplo `wx`, `comtypes`, `cryptography`, `paramiko`, `py7zr`, `markdown` o `app`). El manifiesto no se valida si ocurre.
- Si dos complementos traen el mismo módulo, el gestor lo avisa y se usa el del primero que se active.

Lo que ya trae zCommander y no hay que vendorizar: la biblioteca estándar de Python 3.15, wxPython, pywin32, comtypes, Send2Trash, cryptography, paramiko (con bcrypt y PyNaCl), py7zr, Markdown y accessible_output2. Aun así, para anunciar se usa `zc.anunciar`, nunca accessible_output2.

### instalacion.py

Opcional. Puede definir `al_instalar(zc)` y `al_desinstalar(zc)`:

- Se ejecutan en un hilo de trabajo, con 30 segundos como máximo. Si se agotan o lanzan una excepción, cuenta como fallo y la instalación se deshace.
- Reciben un `Anfitrion` normal, pero sin interfaz: `zc.ui` lanza `NoAdmitido`. No pueden preguntar nada.
- El archivo se carga suelto, fuera del paquete del complemento: no use importaciones relativas en él.
- Lo instalado al reiniciar ejecuta sus funciones después de mostrar la ventana.

### firma.ed25519

Es un JSON que escribe `tools/empaquetar_plugin.py --firmar`. Tiene los campos `formato`, `id`, `version`, `archivos` (ruta y SHA-256 de cada archivo), `firma` (en base64) y `clave` (la clave pública del autor, en base64). La clave no forma parte de lo firmado: sirve para fijarla la primera vez que se instala. Detalles en «Seguridad».

## El manifiesto

`manifiesto.toml` se lee con `tomllib` y lo valida `app/plugins/manifiesto.py`. Si algo falla, el complemento queda en `ERROR_MANIFIESTO` y el gestor muestra todos los problemas en español.

Empiece el archivo con las dos líneas de cabecera de licencia, como comentarios TOML (ver «Licencia»).

### Campos obligatorios

| Campo | Valor |
|---|---|
| `formato` | `1` |
| `id` | Minúsculas y cifras en tramos separados por puntos, al menos dos tramos: `ana.lineas`. Se admite `_` dentro de un tramo, pero no al final ni doble. Ningún tramo puede ser una palabra reservada de Python. `zc.*` está reservado |
| `nombre` | Nombre visible, en español |
| `descripcion` | Una frase, en español |
| `version` | `mayor.menor.parche`, por ejemplo `1.0.0` |
| `autor` | Texto |
| `licencia` | Identificador SPDX, por ejemplo `GPL-3.0-or-later` |
| `api_minima` | Versión de la API que necesita, `mayor.menor` |
| `api_probada` | Versión de la API con la que se probó; no puede ser menor que `api_minima` |
| `entrada` | `"modulo:Clase"` relativo a la carpeta, normalmente `"__init__:Complemento"` |

El complemento se carga si `api_minima` es menor o igual que la versión de la API y `api_probada` es mayor o igual que `API_COMPATIBLE_DESDE`. Con zCommander 2.0 (API 1.1, compatible desde la 1.0), sirven `api_minima = "1.0"` o `"1.1"` y `api_probada = "1.0"` o mayor.

### Campos opcionales

| Campo | Valor |
|---|---|
| `activacion` | Lista con `"al_arrancar"` y `"evento:<nombre>"`. Por defecto, vacía |
| `permisos` | Lista de permisos (ver «Seguridad») |
| `nivel` | `novato` (por defecto), `intermedio` o `avanzado`: nivel por defecto de sus órdenes |
| `web`, `codigo_fuente` | Direcciones `https://`; el gestor las muestra en los detalles |
| `url_actualizacion` | Dirección `https://` del JSON de actualización |
| `ayuda`, `cambios` | Rutas dentro del paquete; por defecto `doc/es/leeme.md` y `doc/es/cambios.md` |
| `prueba` | Id corto de la orden que usa `--comprobar-arranque --complemento-prueba`; por defecto, la primera orden. Debe poder ejecutarse sin argumento y sin preguntar |
| `dialogo_preferencias` | `true` si tiene un diálogo de configuración propio. Por defecto `false` |
| `[requiere]` | `complementos = ["zc.metadatos >= 1.0"]` y `componentes = ["ffmpeg"]`. Las dependencias se activan antes que él |
| `bloque` | Solo para los complementos de serie |

Campos que el diseño describe y que esta versión acepta sin usarlos todavía: `plataforma` (con `python = "3.15"`), `[recomienda]` y las tablas `[[internas]]`, `[[eventos]]`, `[[secretos]]` y `[[componentes]]`. No hacen daño, pero no cambian nada.

### Órdenes: [[ordenes]]

Cada orden se declara con una tabla `[[ordenes]]`. Su id completo es `<id del complemento>:<id corto>`, por ejemplo `ana.lineas:contar`.

| Campo | Valor |
|---|---|
| `id` | Id corto: minúsculas, cifras y `_`. Único en el complemento. Obligatorio |
| `etiqueta` | Texto del menú con su letra de acceso (`&`). Obligatorio |
| `ayuda` | Una frase. La dice Ctrl+H y la paleta. Obligatorio |
| `ambito` | `global` (por defecto) o `panel` |
| `menu` | `complementos` (por defecto), `archivos`, `comandos`, `herramientas`, `contextual` o `ninguno` |
| `teclas` | Lista de teclas en formato canónico, por ejemplo `["Alt+Shift+L"]` |
| `tipo` | `normal` (por defecto) o `casilla` |
| `casilla_defecto` | Estado de la casilla mientras el complemento no está activo. Por defecto `false` |
| `disponible_si` | Patrón de nombre con el que la orden sale habilitada en el menú contextual sin activar el complemento. Vacío: siempre |
| `nivel` | `novato`, `intermedio` o `avanzado` |
| `paleta` | Si sale en la paleta de órdenes. Por defecto `true` |
| `tecla_global` | Si puede usarse como tecla global. Por defecto `false` |
| `argumento` | `""` (por defecto), `ruta`, `patron`, `texto` o `json`: lo que graba una macro y recibe el manejador |

Reglas que comprueban el manifiesto y `tools/validar_plugin.py`:

- La letra de acceso no se repite entre las órdenes del mismo menú del complemento.
- Las teclas están en formato canónico: modificadores en inglés y en el orden `Ctrl+Alt+Shift+tecla`. «Ctrl+Mayús+L» se escribe `Ctrl+Shift+L`.
- Ninguna tecla es reservada ni la usa ya una orden del núcleo o de un complemento de serie con un ámbito que choque. Si choca, zCommander no se la da y el gestor lo dice en los detalles.
- Evite Ctrl+Alt: en los teclados españoles equivale a AltGr.

### Columnas, visores y demás tablas

| Tabla | Campos |
|---|---|
| `[[columnas]]` | `id`, `titulo`, `tipo` (`texto`, `numero`, `tamano`, `fecha` o `duracion`; sirve para ordenar y alinear), `lenta` |
| `[[visores]]` | `id`, `nombre`, `patrones`, `vista_rapida` (por defecto `true`), `prioridad`, `ventana` (`true` si abre una ventana propia) |
| `[[info]]` | `nombre`, `patrones`: archivos para los que añade líneas de información |
| `[[esquemas]]` | `prefijo` sin `://` (por ejemplo `nube`), `nombre` |
| `[[comprimidos]]` | `extensiones`, `nombre`, `escritura` |
| `[[unidades]]` | `texto`, `direccion`, `descripcion`; `dinamicas = true` si además hay que preguntar al complemento |
| `[[busqueda]]` | `id`, `nombre`: motor de búsqueda |
| `[[extractores]]` | `nombre`, `patrones`: texto de documentos para buscar por contenido |
| `[[mascaras]]` | `marcador` con prefijo propio en mayúsculas, como `[MP3:artista]`; `descripcion` |
| `[[acciones_error]]` | `id`, `etiqueta`, `ayuda`, `codigos_windows` (lista de enteros; vacía significa cualquier error) |

Notas:

- Los ids de columnas y sonidos son únicos en el complemento.
- Un marcador de máscara no puede coincidir con los del renombrado de zCommander (`[N]`, `[E]`, `[C]`, `[Y]`, `[y]`, `[M]`, `[D]`, `[h]`, `[m]`, `[s]`, `[t]`, `[P]`, `[G]`).
- `[[columnas]]` acepta también `patrones`, pero esta versión no los usa: la columna se pide para todos los elementos y su función devuelve `None` en los que no le interesan.

### Configuración y páginas de Preferencias

Una tabla `[[paginas]]` por página (`id`, `titulo`) y una `[[configuracion]]` por clave.

| Campo de `[[configuracion]]` | Valor |
|---|---|
| `clave` | Minúsculas, cifras y `_`, sin puntos. Única. Obligatoria |
| `tipo` | `bool`, `entero`, `decimal`, `texto`, `opcion`, `carpeta`, `archivo`, `lista` o `diccionario` |
| `defecto` | Valor de fábrica, del tipo declarado. Obligatorio |
| `etiqueta` | Texto de la etiqueta con su letra de acceso (`&`) |
| `ayuda` | Una frase para Ctrl+H |
| `pagina` | Id de una de sus `[[paginas]]` |
| `minimo`, `maximo` | Límites de `entero` y `decimal` |
| `opciones` | Para `opcion`: `[["valor", "Etiqueta"], ...]`; el defecto debe ser uno de los valores |
| `interna` | `true` si no se muestra en Preferencias |
| `ejecuta` | `true` si el valor es un programa que zCommander ejecutará. Booleano |

### Sonidos: [[sonidos]]

| Campo | Valor |
|---|---|
| `id` | Parte del id de evento tras «:». Obligatorio. El evento completo es `<id del complemento>:<id>` |
| `nombre` | Nombre visible; por defecto, el `id` |
| `descripcion` | Cuándo suena |
| `prioridad` | `alta`, `media` (por defecto) o `baja` |
| `por_defecto` | Si suena de fábrica. Por defecto `true` |
| `archivo` | Por defecto `sonidos/<id>.wav` |

## La API: app/plugins/api.py

La API es una fachada única: `from app.plugins import api`. No importa wx ni `app.ui`; lo de la interfaz llega por una sola inyección que hace la ventana. Sin ventana (en las pruebas), lo que necesita la interfaz lanza `NoAdmitido` y `zc.anunciar` solo escribe en el registro.

### Versiones

- `api.API_VERSION = (1, 1)` y `api.API_COMPATIBLE_DESDE = (1, 0)`.
- Una versión menor solo añade. Quitar algo exige cambiar la versión principal y avisar antes.
- `tests/plugins/test_api_estable.py` compara la firma pública con una instantánea guardada, para que nada se rompa sin querer.

Novedades de la 1.1, todas añadidos a la 1.0:

- `zc.columnas.invalidar(rutas=None)`: olvida los valores guardados de sus columnas (de esas rutas o de todas). Úselo cuando cambia algo que no toca el archivo, como un comentario; después, `refrescar()` del panel vuelve a pedirlos.
- Paso de deshacer `restaurar`: vuelve a poner una copia sobre el archivo si este no cambió desde entonces.
- `zc.ui.mostrar_diferencias(ruta_a, ruta_b)`: la ventana de diferencias del núcleo.
- `zc.abrir_ayuda(pagina)`: abre `doc/es/<pagina>.md` del complemento.
- `Proveedor.orden_preferido` y resultados de búsqueda con direcciones de un proveedor.
- Activación por `[[esquemas]]` y entrega del evento que activa el complemento.
- `api.pruebas.contexto_de_prueba(..., anfitrion=zc)`: los anuncios del contexto van a `zc.anuncios`.

Si su complemento usa algo de la 1.1, declare `api_minima = "1.1"`.

### Reglas de hilos

Cada método de la API dice en su docstring o en el diseño en qué hilo se puede llamar:

- **[cualquiera]**: desde cualquier hilo; la fachada lleva al hilo de la interfaz lo que haga falta. Por ejemplo `zc.anunciar`, `zc.lanzar`, `zc.abrir_ruta`, `zc.sonidos.sonar`, `zc.deshacer.registrar`.
- **[trabajo]**: bloquea; nunca en el hilo de la interfaz. Por ejemplo `zc.ejecutar_programa`, `zc.red.*`, `zc.vfs.resolver`, `zc.renombrado.evaluar`, y las preguntas con `zc.decisor`.
- **[interfaz]**: solo en el hilo de la interfaz. Por ejemplo `zc.ui.*`, `zc.abrir_ayuda`, `zc.ejecutar_orden`, `zc.escribir_en_linea`, `ctx.anunciar` y los paneles del contexto.

Y estas reglas de tiempo:

- Lo que corre en el hilo de la interfaz (manejadores de órdenes, estados de casillas, eventos del bus, acciones de error) dura menos de 20 ms, sin contar el tiempo en un diálogo modal. Lo largo va a `zc.tareas` o a una operación con `zc.lanzar`.
- Lo que corre en un hilo (columnas, visores, información, búsqueda, extractores, fábricas de proveedores, unidades) acepta la cancelación, la comprueba a menudo con `api.comprobar(cancelacion)` y no toca wx.
- En el hilo de la interfaz se pregunta con `zc.ui`; desde un hilo o una operación, con `zc.decisor`.

### La clase Complemento

La entrada del manifiesto apunta a una subclase de `api.Complemento`:

- `activar(zc)`: registra sus funciones sobre `zc`. Nada lento y ningún diálogo: `zc.ui` lanza `RuntimeError` si se abre un diálogo mientras el complemento se está cargando. Lo que haya que preguntar al activarse se aplaza con `zc.complemento_futuro(zc.id).add_done_callback(...)`.
- `desactivar()`: libera lo suyo al cerrar zCommander. Entre todos los complementos hay un tope de 2 segundos, que solo se mide.
- `ventanas_para_revisar(padre)`: opcional. Crea sin mostrarlas sus ventanas y diálogos para que `tools/validar_plugin.py` les pase `revisar_teclado`.
- `puede_cerrar()`: opcional, [interfaz]. Devolver falso cancela el cierre de zCommander; puede preguntar con `zc.ui`.

El gestor pone en la instancia los atributos `id` y `carpeta`.

### El anfitrión: zc

Servicios de `zc`:

| Atributo | Para qué |
|---|---|
| `id`, `version_app`, `carpeta`, `permisos` | Datos del complemento y de zCommander |
| `datos`, `cache` | Carpetas propias para escribir (se crean al pedirlas) |
| `registro` | `logging.Logger` llamado `zcplugins.<id>`; el gestor lo muestra en «Ver su registro» |
| `config` | Su configuración, con claves cortas |
| `secretos` | Sus contraseñas y fichas; exige el permiso `secretos` |
| `tareas` | `GestorTareas` propio (2 hilos) para trabajo en segundo plano |
| `decisor` | Preguntas desde hilos y operaciones [trabajo] |
| `ordenes`, `columnas`, `visores`, `info`, `busqueda`, `renombrado`, `errores`, `eventos`, `vfs`, `preferencias` | Registros de los puntos de extensión |
| `sonidos` | `sonar(evento)` [cualquiera] |
| `componentes` | Programas de `data/bin` (FFmpeg, 7za...): `ruta`, `ejecutable`, `disponible` |
| `red` | HTTP: `obtener`, `enviar`, `descargar` [trabajo]; exige `red` o `internet:<host>` |
| `ui` | Diálogos y controles accesibles [interfaz] |
| `deshacer` | `registrar(accion)` en la pila de deshacer del núcleo |
| `espacios`, `vistas` | Espacios de trabajo y conjuntos de columnas por carpeta |

Métodos de `zc`:

| Método | Hilo y uso |
|---|---|
| `anunciar(texto, nivel, completo, interrumpir)` | [cualquiera] Anuncio al lector de pantalla |
| `lanzar(operacion, en_cola, al_terminar)` | [cualquiera] Operación larga con progreso, pausa, cola y deshacer |
| `ejecutar_programa(argumentos, ...)` | [trabajo] Programa externo sin consola ni shell; exige `ejecutar_programas` |
| `abrir_programa(argumentos, carpeta)` | [cualquiera] Programa que sigue abierto aunque se cierre zCommander; exige `ejecutar_programas` |
| `abrir_ruta(texto, lado)` | [cualquiera] Lleva un panel a una ruta o dirección |
| `abrir_ayuda(pagina)` | [interfaz] Abre su ayuda o una página de `doc/es/` |
| `ejecutar_orden(id, lado, argumento=...)` | [interfaz] Ejecuta una orden del catálogo |
| `ejecutar_orden_futuro(id, lado, argumento=...)` | [interfaz] Igual, con un futuro que se resuelve al terminar |
| `escribir_en_linea(texto)` | [interfaz] Pone texto en la línea de órdenes sin ejecutarlo |
| `exportar(nombre, objeto)` | En `activar()`: ofrece una función a otros complementos |
| `complemento(id)` | [cualquiera] Lo exportado por otro complemento, o `None` |
| `complemento_futuro(id)` | [cualquiera] Lo mismo, como futuro |

### El contexto de una orden

El manejador de una orden recibe un `ContextoComplemento` [interfaz]:

- `orden`: id completo de la orden.
- `activo` y `pasivo`: los dos paneles; `objetivo`: el panel sobre el que actúa (el activo, o el del menú Izquierdo o Derecho si se lanzó desde allí).
- `argumento`: el de una macro, el de `zc <orden> <argumento>` o la ruta de Intro sobre un archivo asociado.
- `anunciar(...)` y `sonar(evento)`.

Cada panel ofrece `lado`, `proveedor`, `ruta`, `mostrar_ruta()`, `cursor()`, `marcadas()`, `elementos_trabajo()` (las marcadas o, si no hay, el elemento del cursor) y `refrescar()`. No hay acceso a la ventana, a los controles ni a los servicios internos: lo que haga falta va por `zc`.

### Tipos re-exportados y utilidades

- Sistema de archivos: `Entrada`, `Proveedor`, `Capacidades`, `Ubicacion`, `UnidadVirtual`, `ResultadoPar`.
- Errores: `ErrorArchivos` y sus clases (`ErrorAcceso`, `NoEncontrado`, `YaExiste`, `SoloLectura`, `ErrorRed`, `NombreNoValido`, `SinEspacio`), `Cancelado` y `NoAdmitido`. Los mensajes van en español.
- Operaciones: `Operacion`, `Estado`, `Progreso`, `ContextoEjecucion`, `Politica`, `OpcionesCopia`, `OperacionCopiar`, `OperacionEliminar`, `OperacionRenombrar`, `PreguntaError`, `AccionError`, `Decisor`, `RespuestasAutomaticas`, `clave_carril`, `AccionDeshacer`, `Paso`.
- Otros: `TokenCancelacion`, `CriteriosBusqueda`, `ResultadoPrograma`, `RespuestaRed`, `Documento` y `Seccion`.
- Niveles de anuncio: `api.ESENCIAL`, `api.RESULTADO`, `api.NORMAL` y `api.DETALLE`.
- `api.formato`: tamaños, fechas y duraciones legibles.
- `api.comprobar(cancelacion)`: lanza `Cancelado` si se pidió cancelar. Acepta un token o una tarea.
- `api.traduccion(dominio)`: devuelve `_` y `ngettext` del complemento. Hoy solo se entrega el español.
- `api.provisional(id_corto)`: manejador marcado que anuncia que la orden aún no está programada. `tools/validar_plugin.py` da error si una orden solo tiene este manejador.

### NoAdmitido

`api.NoAdmitido` significa «esto no se puede hacer aquí». Lo lanzan:

- `zc.red`, `zc.secretos`, `zc.ejecutar_programa` y `zc.abrir_programa` si falta el permiso.
- Lo que necesita la ventana cuando no la hay (pruebas, `al_instalar`).
- `zc.componentes.ruta` si el componente falta o está en mantenimiento.

Si su código debe funcionar también sin ventana, capture `api.NoAdmitido`, como hacen los complementos de serie al registrar un diálogo de preferencias.

### api.pruebas

Ayudas sin wx para las pruebas del complemento: `from app.plugins.api import pruebas`.

| Nombre | Qué hace |
|---|---|
| `anfitrion_de_prueba(carpeta, config=None, permisos=())` | Lee el manifiesto, registra el complemento y devuelve un `AnfitrionFalso`. `config` fija valores de su configuración; los permisos, por defecto, son los del manifiesto |
| `AnfitrionFalso` | Apunta en `anuncios` (texto y nivel), `sonidos_pedidos` y `operaciones_lanzadas`. Métodos: `activar()`, `ejecutar(id_corto, contexto)`, `columna(id_corto, entrada)`, `visor(id_corto, ruta)` y `emitir(evento, **datos)` |
| `PanelFalso(entradas, cursor=0, marcadas=(), ruta="", proveedor=None, lado="izquierdo")` | Un panel con entradas fijas; `marcadas` son nombres. Sin proveedor, usa el local |
| `contexto_de_prueba(activo, pasivo, argumento, anfitrion)` | Contexto de una orden. Con `anfitrion`, `ctx.anunciar` apunta en `anfitrion.anuncios` |
| `DecisorFalso(respuestas)` | Devuelve las respuestas en orden y guarda lo preguntado en `preguntas` |

Dos detalles comprobados:

- `ctx.sonar` llama al servicio de sonidos real; en las pruebas solo se apunta lo que se pide con `zc.sonidos.sonar`.
- `zc.config.establecer` escribe el JSON de configuración en `data/config/plugins/`. `tools/validar_plugin.py` ejecuta las pruebas con `APP_DATA_DIR` apuntando a una carpeta temporal; si las ejecuta usted con pytest, fije esa variable para no tocar su configuración real.

## Puntos de extensión

Todo se registra en `activar(zc)`. Lo declarado en el manifiesto existe como marcador antes; el código solo pone las funciones.

### Órdenes

```python
zc.ordenes.manejador("contar", self.contar)            # función(ctx) [interfaz]
zc.ordenes.estado("pausar", lambda ctx: self.pausado)  # órdenes casilla: devuelve el estado
zc.ordenes.disponible("contar", self.hay_texto)        # devuelve falso para inhabilitar el elemento de menú
```

- Las órdenes salen en el menú «Co&mplementos» (un submenú por complemento) o en el menú que diga `menu`, en la paleta y en el mapa de teclas.
- Las macros y las tareas del programador (`zc.programador`) ejecutan órdenes por su id con `ejecutar_orden_futuro` y esperan a que terminen. Para que funcionen sin la persona, la orden debe poder ejecutarse con su `argumento` y sin preguntar.
- Una orden puede ser el programa de Abrir, Ver o Editar de un patrón en las asociaciones, con el valor `zc:<id de orden>`. Recibe la ruta en `ctx.argumento`.

### Columnas

```python
zc.columnas.extractor("lineas", funcion)  # funcion(entrada, proveedor, cancelacion) -> str | None
```

- Se llama en un hilo del grupo propio del complemento (2 hilos), con 5 segundos por valor.
- `None` se muestra como «Sin datos». Mientras se calcula, la fila muestra «…».
- Los valores se guardan por ruta, tamaño y fecha. Si su valor cambia sin que cambie el archivo, llame a `zc.columnas.invalidar(rutas)`.
- La persona añade la columna con la orden «Col&umnas...» del panel.

### Visores y vista rápida

```python
zc.visores.visor("documento", funcion)  # funcion(proveedor, ruta, cancelacion) -> api.Documento, en un hilo
zc.visores.ventana("tabla", funcion)    # funcion(proveedor, ruta) [interfaz]: abre una ventana propia
```

Un `Documento` tiene `titulo`, `secciones` (tupla de `Seccion(titulo, nivel, texto, pagina)`), `metadatos` y `aviso`. El visor interno lo muestra con F6 y Mayús+F6 entre secciones, Ctrl+L para la lista de secciones y Ctrl+P para ir a una página. Es la forma preferida: accesible sin escribir ninguna ventana. La vista rápida solo usa visores que devuelven `Documento`.

F3 usa la asociación «Ver» si la hay; si no, el visor de complemento de mayor `prioridad` cuyo patrón coincide; si no, el visor interno.

### Información del elemento

```python
zc.info.lineas(funcion)  # funcion(entrada, proveedor) -> list[str], en un hilo
```

Añade líneas a Ctrl+Mayús+I y a la vista Información para los archivos de los patrones de `[[info]]`. Debe tardar menos de un segundo.

### Búsqueda: motores y extractores

```python
zc.busqueda.proveedor("instantanea", funcion)  # funcion(criterios, emitir, cancelacion); emitir(ruta) por cada resultado
zc.busqueda.extractor(funcion)                 # funcion(proveedor, ruta, cancelacion) -> str | None
```

- Un motor sale en el desplegable «&Motor de búsqueda» del diálogo Buscar archivos. Desde la API 1.1 puede emitir direcciones de un proveedor (con `://`).
- Un extractor da el texto de documentos (PDF, DOCX...) para la casilla «Buscar también dentro de docu&mentos».

### Máscaras de renombrado

```python
zc.renombrado.mascara("[MP3:artista]", funcion)  # funcion(entrada, proveedor) -> str | None
texto = zc.renombrado.evaluar(plantilla, entrada, proveedor)  # [trabajo] con todas las máscaras
```

Las máscaras salen en «Insertar marcador» del renombrado múltiple; la vista previa muestra «…» hasta que llega su valor.

### Acciones de error

```python
zc.errores.accion("ver_quien", aplica, funcion)
# aplica(pregunta) -> bool: decide con pregunta.codigo_windows y pregunta.excepcion, nunca con el texto
# funcion(pregunta) -> AccionError | None [interfaz]: REINTENTAR, OMITIR o CANCELAR; None vuelve a preguntar
```

El botón sale en la pregunta de error de las operaciones. Sin activar el complemento, decide `codigos_windows` del manifiesto; ya activo, además `aplica()`.

### Proveedores VFS, esquemas, comprimidos y unidades

```python
zc.vfs.esquema("nube", fabrica)                  # fabrica(direccion) -> (proveedor, ruta)
zc.vfs.comprimido((".xyz",), fabrica)            # fabrica(proveedor_padre, ruta) -> proveedor
zc.vfs.unidades(funcion)                         # funcion() -> list[UnidadVirtual], en un hilo
proveedor, ruta = zc.vfs.resolver("nube://...")  # [trabajo]; quien lo pide lo cierra
```

- Un proveedor es una subclase de `api.Proveedor`. Solo lanza `ErrorArchivos`: cualquier otra excepción de la fábrica se convierte en un `ErrorArchivos` con el nombre del complemento.
- Si una fábrica de comprimidos lanza `NoAdmitido`, Intro abre el archivo con su programa.
- Las entradas fijas de `[[unidades]]` salen en el selector sin activar el complemento; con `dinamicas = true`, el complemento se activa en segundo plano la primera vez que se abre el selector.

### Eventos del bus

```python
cancelar = zc.eventos.suscribir("al_cambiar_carpeta", funcion)  # funcion(**datos) en el hilo de la interfaz
zc.eventos.emitir("terminado", total=3)                         # emite «<id>:terminado»
```

Eventos del núcleo: `al_arrancar`, `al_cerrar`, `al_cambiar_carpeta`, `al_cambiar_cursor`, `al_cambiar_marcas`, `al_activar_panel`, `al_empezar_operacion`, `al_terminar_operacion`, `al_cambiar_preferencia`, `al_conectar`, `al_desconectar`, `al_ejecutar_orden`, `al_terminar_orden`, `al_copiar_portapapeles`, `al_restaurar` y `al_cambiar_catalogo`. Los datos de cada uno están en `docs/diseno-2.md`, 14.4.

- Un complemento solo emite eventos propios: `emitir` les pone el prefijo `<id>:`.
- Cada suscriptor se mide: si pasa de 20 ms tres veces, se registra un aviso.
- `al_cerrar` se entrega en el acto, antes de `desactivar()`: es el sitio para guardar estado.

### Páginas de Preferencias y diálogo propio

- Las páginas declarativas (`[[paginas]]` y `[[configuracion]]`) aparecen en Preferencias, Complementos, nombre del complemento, sin escribir código. Participan en Aceptar, Cancelar, Aplicar y «Valores de fábrica de esta página».
- Si necesita un diálogo propio, ponga `dialogo_preferencias = true` en el manifiesto y registre la función en `activar()` con `zc.preferencias.dialogo(funcion)`, donde `funcion(padre)` abre el diálogo. El botón «Abrir la configuración avanzada...» aparece sin activar el complemento.
- `zc.preferencias.abrir()` [interfaz] abre Preferencias en la página del complemento.

### Operaciones largas y deshacer

Para trabajo largo sobre archivos, cree una subclase de `api.Operacion` y lánzela con `zc.lanzar(operacion)`. Así tiene progreso, pausa, cola, ventana de operaciones y preguntas por el gestor de decisiones. Lo que se pueda deshacer se registra con `zc.deshacer.registrar(api.AccionDeshacer(...))`. Para trabajo corto en segundo plano, `zc.tareas.enviar(funcion, *args)`: la función recibe la tarea como primer argumento, que sirve de cancelación.

### Funciones para otros complementos

```python
zc.exportar("etiquetar", self.etiquetar)   # en activar()
notas = zc.complemento("zc.notas")         # en un hilo: lo activa y espera
```

En el hilo de la interfaz, `zc.complemento(id)` nunca importa en el acto: si el otro no está activo, pide su activación y devuelve `None`. Use `zc.complemento_futuro(id)` y siga cuando se resuelva. Si lo necesita siempre, declárelo en `[requiere]`: estará activo antes que usted.

### Órdenes internas de la línea de órdenes

```python
zc.ordenes.interna("git", funcion)  # funcion(argumentos, escribir, cancelacion) -> código de salida, en un hilo
```

La persona escribe `zc git status` en la línea de órdenes; `escribir(linea)` va a «Salida de órdenes». En esta versión la orden interna solo existe cuando el complemento ya está activo: la tabla `[[internas]]` del manifiesto todavía no se lee.

### Ventanas propias

Solo cuando ningún contrato de datos (documento, columna, página declarativa, diálogo de `zc.ui`) sirve. Use `zc.ui.VentanaComplemento(padre, titulo, zc.id)`, una ventana no modal en la que Escape cierra y F1 abre la ayuda del complemento. En modo desarrollo, la primera vez que se muestra pasa `revisar_teclado`. Las reglas están en «Accesibilidad obligatoria».

## Configuración propia, secretos, sonidos y ayuda

### Configuración propia

- Cada complemento con `[[configuracion]]` tiene su archivo `data/config/plugins/<id>.json`, con la sección `ajustes`. Una configuración dañada de un complemento no toca la de zCommander.
- Nombre completo de una clave: `plugin.<id>.<clave>`, por ejemplo `plugin.ana.lineas.tamano_maximo_mb`. Es el que usan las copias de seguridad, las macros y el anexo de configuración.
- Desde el complemento se usan claves cortas:

```python
valor = zc.config.obtener("tamano_maximo_mb")
zc.config.establecer("tamano_maximo_mb", 50)  # aplica minimo, maximo y opciones del manifiesto
zc.config.establecer_varias({"a": 1, "b": 2})
cancelar = zc.config.suscribir(funcion, prefijo="")  # funcion(clave, anterior, nuevo), en el hilo de la interfaz
zc.config.restablecer()                              # vuelve a los valores de fábrica
```

### Secretos

Contraseñas y fichas de acceso, cifradas en `secretos.dat` con el nombre `plugin:<id>:<nombre>`. Exige el permiso `secretos`; sin él, `zc.secretos` lanza `NoAdmitido`.

```python
zc.secretos.guardar("token", valor)
token = zc.secretos.obtener("token")  # None si no hay
zc.secretos.borrar("token")
```

Nunca guarde un secreto en `zc.config` ni en `zc.datos`.

### Sonidos propios

- Cada `[[sonidos]]` crea el evento `<id del complemento>:<id>` en el catálogo de sonidos, en la categoría del complemento. La persona lo oye, lo cambia o lo calla en Preferencias, Sonidos.
- Suene con `zc.sonidos.sonar("contado")` [cualquiera] o `ctx.sonar("contado")`. También puede usar un evento del núcleo con su id completo (`"op.fin"`).
- El archivo por defecto es `sonidos/<id>.wav`. Formatos admitidos: WAV PCM de 8 o 16 bits, mono o estéreo, de 8 000 a 48 000 Hz, 10 segundos y 2 MB como máximo.
- Los paquetes de sonidos pueden traer su versión en `plugins/<id del complemento>/<id>.wav`; si el paquete no la trae, suena la del complemento.
- `tools/crear_plugin.py` deja un pitido de ejemplo en `sonidos/saludo.wav`. `tools/generar_sonidos.py --complementos` solo genera los de los complementos de serie.
- Un sonido nunca es la única señal de algo: acompáñelo de un anuncio o de un texto en pantalla.

### Ayuda

- `doc/es/leeme.md`: la ayuda del complemento, en Markdown. La abren el botón «A&yuda» del gestor y F1 en sus ventanas. Escríbala para la persona usuaria: órdenes con su tecla y su menú, columnas, preferencias y sonidos.
- `doc/es/cambios.md`: las novedades de cada versión, para el botón «&Novedades» del gestor.
- `zc.abrir_ayuda(pagina)` [interfaz] abre `doc/es/<pagina>.md` si existe (con o sin `.md`) y, si no, la ayuda principal. Nunca sale de la carpeta del complemento.
- `tools/validar_plugin.py` avisa si falta la ayuda.

## Accesibilidad obligatoria

zCommander es para personas ciegas. Un complemento que no se puede usar con lector de pantalla y teclado no se publica. Estas reglas son obligatorias; `tools/validar_plugin.py` comprueba las que puede.

### Prefiera los contratos de datos

Antes de escribir una ventana, mire si basta con un `Documento` en el visor, una columna, una línea de información, una página declarativa de Preferencias o un diálogo de `zc.ui` (`confirmar`, `elegir_opcion`, `pedir_texto`, `mostrar_mensaje`, `mostrar_error`, `mostrar_texto`, `mostrar_documento`, `mostrar_resultados`). Ya son accesibles.

### Si escribe ventanas

- Todas con `zc.ui`: `VentanaComplemento` para ventanas no modales y `zc.ui.mostrar_modal(dialogo)` para los modales. Nunca `ShowModal` directamente (el validador lo avisa).
- Cada etiqueta (`wx.StaticText`) se crea justo antes de su control, para que el lector la asocie. `zc.ui.crear_campo(padre, "&Nombre:", wx.TextCtrl, ayuda="...", sizer=...)` lo hace por usted.
- Letras de acceso (`&`) en cada etiqueta y botón, sin repetirse dentro de la misma ventana.
- Ayuda en cada control (`ayuda=` de `crear_campo` o `SetHelpText`), que Ctrl+H dice. `zc.ui.preparar_dialogo(dialogo)` pone Escape y Ctrl+H.
- Botones con texto en español: `zc.ui.crear_botonera(padre, wx.OK | wx.CANCEL)` los crea con las etiquetas de zCommander. En una confirmación peligrosa, el predeterminado es «No» o «Cancelar».
- Listas con `zc.ui.ListaAccesible`, casillas con `CheckListBoxAccesible`, deslizadores con `SliderAccesible` y progreso con `IndicadorProgreso`.
- Antes de mover el foco por código, `zc.ui.movimiento_silencioso(ventana)`.
- Devuelva sus ventanas en `ventanas_para_revisar(padre)` para que el validador les pase `revisar_teclado`. Capture `api.NoAdmitido` si se construyen sin interfaz.

Así lo hace un complemento de serie (fragmento de `plugins/busqueda_instantanea/ventana.py`):

```python
self.marco = ui.VentanaComplemento(padre, "Búsqueda instantánea", zc.id, size=(760, 560))
panel = wx.Panel(self.marco)
cuerpo = wx.BoxSizer(wx.VERTICAL)
_, self.campo = ui.crear_campo(panel, "&Buscar:", wx.TextCtrl, sizer=cuerpo, style=wx.TE_PROCESS_ENTER,
	ayuda="Escriba parte del nombre. Intro va al primer resultado.")
self.boton_cerrar = wx.Button(panel, wx.ID_CLOSE, label="&Cerrar")
self.boton_cerrar.SetHelpText("Cierra la búsqueda instantánea (también con Escape).")
```

### Anuncios

- Solo con `zc.anunciar` o `ctx.anunciar`, nunca con accessible_output2 (el validador lo avisa).
- Elija el nivel:
  - `ESENCIAL`: errores, preguntas pendientes y fin de operaciones. Se dice siempre y no interrumpe.
  - `RESULTADO`: la respuesta a algo que la persona acaba de pedir y que no tiene respuesta nativa. Se dice siempre.
  - `NORMAL`: cambios de carpeta, marcas, alcance de una orden. Con detalle «normal» o «detallado».
  - `DETALLE`: consejos y datos extra. Solo con detalle «detallado».
- No anuncie lo que el lector ya dice al mover el foco.
- Use `completo` para la versión larga: «Repetir el último anuncio» pulsado dos veces la dice.

### Nada lento en el hilo de la interfaz

Si el hilo de la interfaz se bloquea, Windows marca la ventana como «No responde» y el lector de pantalla se queda mudo. Los manejadores duran menos de 20 ms y mandan el trabajo a `zc.tareas` o `zc.lanzar`. El vigilante de bloqueos registra al culpable si pasa de 2 segundos.

### Nada que dependa solo de un color o de un sonido

Un color siempre va también en texto (las etiquetas de `zc.notas` dicen su color con palabras). Un sonido siempre acompaña a un anuncio o a un texto, nunca lo sustituye. Use los colores y la letra del tema.

### Prueba manual antes de publicar

Además del validador, recorra el complemento con NVDA, JAWS y Narrador:

1. Cada orden se encuentra en su menú y en la paleta, y se dice su tecla.
2. Cada ventana se recorre entera con Tab y Mayús+Tab, y cada control dice su etiqueta.
3. Ctrl+H dice la ayuda de cada control y F1 abre la ayuda del complemento.
4. Escape cierra cada ventana y el foco vuelve a donde estaba.
5. Los anuncios llegan una vez, con el nivel adecuado, y no tapan lo que el lector dice solo.
6. Con el sonido apagado no se pierde ninguna información.

## Seguridad

### Permisos

Se declaran en `permisos` y se muestran en lenguaje claro al instalar y en el gestor. No son una barrera técnica (un módulo Python puede hacer cualquier cosa), pero la API solo da la red, los secretos, los programas y las teclas globales a quien los declara.

| Permiso | Texto que ve la persona |
|---|---|
| `red` | Conectarse a Internet y a la red local |
| `internet:<host>` | Conectarse a `<host>` |
| `ejecutar_programas` | Ejecutar programas |
| `escribir_fuera_de_paneles` | Escribir archivos fuera de las carpetas de los paneles |
| `portapapeles` | Usar el portapapeles |
| `secretos` | Guardar contraseñas y fichas de acceso |
| `sonido` | Reproducir sonido |
| `segundo_plano` | Trabajar en segundo plano |
| `teclas_globales` | Registrar teclas globales |
| `elevacion` | Pedir permisos de administrador |

Declare solo lo que use. Un permiso desconocido invalida el manifiesto.

### Confianza

El gestor y el resumen de instalación muestran la confianza como texto:

- «Oficial»: de serie, o firmado con la clave del proyecto.
- «Firmado por un autor de confianza»: firma válida de una clave que la persona aceptó («Confiar en este a&utor» en el gestor) o fijada para ese id.
- «Firmado por un autor nuevo»: lo muestra el resumen de instalación la primera vez que se instala un complemento firmado; al instalarlo, su clave queda fijada para ese id.
- «Sin firma»: la instalación lo advierte («Este complemento no está firmado. Ejecutará código con sus mismos permisos de Windows. Instálelo solo si confía en su autor.») y el botón predeterminado es «&Cancelar». `complementos.permitir_sin_firma` puede prohibirlos.

Un complemento sin firma solo se carga si la persona lo aceptó y sus archivos no han cambiado desde entonces (`complementos.confiados` guarda su suma). Si se copió a mano, o cambió, queda «Sin aceptar» y zCommander pregunta tras mostrar la ventana.

### Firma Ed25519

La firma es opcional pero muy recomendable. `app/plugins/firma.py` firma `b"zcommander-complemento-v1\n"` seguido del JSON canónico (claves ordenadas, sin espacios, UTF-8) de `{"archivos": {ruta: sha256}, "id": ..., "version": ...}` con todos los archivos del paquete salvo la propia firma. El prefijo impide que una firma de complemento valga para otra cosa.

Lo que se comprueba:

- Al instalar: la firma, con todas las sumas, y que el id y la versión de la firma coinciden con el manifiesto.
- Al arrancar: la firma sobre la lista de archivos y que no sobra ni falta ninguno, sin leerlos.
- Al activar y al importar cada archivo: su SHA-256. Un archivo cambiado deja el complemento fuera de uso. Los complementos de `data/plugins/` nunca usan `.pyc`.
- **Clave fijada por id**: la primera instalación firmada fija la clave del autor para ese id. Las actualizaciones tienen que venir firmadas con la misma clave; si no, se rechazan. Si alguien borra la firma de un complemento con clave fijada, no se carga.

Guarde la clave privada fuera del complemento y no la publique. Si la pierde, no podrá publicar actualizaciones de ese id: la persona tendría que desinstalar e instalar de nuevo.

Para crear una clave, este guion (comprobado) escribe los 32 bytes de la clave privada en hexadecimal:

```python
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

privada = Ed25519PrivateKey.generate().private_bytes(
	serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
Path("ana.clave").write_text(privada.hex(), encoding="ascii")
print("Clave guardada en ana.clave. No la publique ni la pierda.")
```

No la guarde con una redirección de PowerShell 5.1 (`>`): escribe UTF-16 y `tools/empaquetar_plugin.py` no la reconoce.

### Actualizaciones por url_actualizacion

Si el manifiesto declara `url_actualizacion`, el gestor descarga ese JSON cuando la persona pulsa «&Buscar actualizaciones» y, si `actualizaciones.complementos_comprobar` está activa, en la comprobación periódica de zCommander. Nunca instala sin que la persona lo confirme.

El JSON tiene estos campos:

| Campo | Valor |
|---|---|
| `id` | El del complemento; si no coincide, se ignora |
| `version` | `mayor.menor.parche`, más alta que la instalada |
| `url` | Dirección `https://` del `.zcplugin` |
| `sha256` | Suma del paquete en hexadecimal; la descarga se comprueba |
| `tamano` | Bytes del paquete |
| `novedades` | Texto que ve la persona |
| `firma_ed25519` | Firma en base64. Obligatoria si el complemento está firmado |

La firma se hace sobre el JSON canónico (claves ordenadas, sin espacios, UTF-8) de todos los campos menos `firma_ed25519`, sin prefijo, y con la misma clave que el paquete. Es lo que hace `paquetes.firmar_json_actualizacion` (y `tools/publicar.py --firmar-complementos` para los de serie). Este guion, comprobado, lo genera; ejecútelo con `PYTHONPATH` apuntando a la carpeta de zCommander (en PowerShell, `$env:PYTHONPATH = "C:\ruta\de\zCommander"`):

```python
import json
from pathlib import Path

from app.plugins import paquetes

clave = bytes.fromhex(Path("ana.clave").read_text(encoding="ascii").strip())
paquete = Path("ana.lineas-1.0.1.zcplugin")
datos = {
	"id": "ana.lineas",
	"version": "1.0.1",
	"url": "https://ejemplo.org/zcommander/ana.lineas-1.0.1.zcplugin",
	"sha256": paquetes.suma_archivo(paquete),
	"tamano": paquete.stat().st_size,
	"novedades": "Cuenta también los archivos .ini.",
}
firmado = paquetes.firmar_json_actualizacion(datos, clave)
Path("ana.lineas.json").write_text(json.dumps(firmado, ensure_ascii=False, indent=1), encoding="utf-8")
```

Un JSON firmado que se altera después no pasa `paquetes.verificar_json_actualizacion`, y el gestor lo ignora.

### Instalar, actualizar y desinstalar

- Un complemento nuevo sin `al_arrancar` queda listo sin reiniciar. Una actualización, o uno con `al_arrancar`, se aplica al reiniciar.
- Al actualizar, la carpeta se sustituye entera; la configuración y los datos sobreviven. Si cambia la versión principal de la API que pide, se avisa.
- Al desinstalar, se pregunta aparte si borrar también su configuración y sus datos (por defecto, no). Los de serie no se desinstalan: se inhabilitan.

### Auditoría opcional

Con `complementos.auditoria` activada, un gancho `sys.addaudithook` apunta en el registro las conexiones (`socket.connect`) y los procesos (`subprocess.Popen`) que salen de un módulo `zcplugins.*` sin el permiso correspondiente (`red` o `internet:<host>`; `ejecutar_programas`). Solo registra: no es una barrera. Sirve para comprobar que su complemento declara lo que usa.

### Partes internas

El gestor y el validador avisan «usa partes internas» si el código importa algo de `app.` que no sea `app.plugins.api`. Lo interno puede cambiar en cualquier versión sin aviso.

## Herramientas

Todas se ejecutan desde la carpeta de zCommander, con su Python.

### tools/crear_plugin.py

```text
crear_plugin.py [-h] --id ID --nombre NOMBRE [--autor AUTOR] [--descripcion DESCRIPCION] carpeta
```

- `carpeta`: nueva o vacía.
- `--id`: id del complemento; rechaza los no válidos y los `zc.*`.
- `--nombre`: nombre visible en español.
- `--autor` y `--descripcion`: opcionales.

Copia la plantilla `tools/plantilla_plugin/`: manifiesto con una orden, una página de Preferencias con una clave y un sonido; `__init__.py`; `doc/es/leeme.md` y `doc/es/cambios.md`; `LICENSE` con la GPL-3.0; un pitido en `sonidos/saludo.wav`; y una prueba con `api.pruebas`. Devuelve 0 si lo crea y 1 con el motivo si no.

### tools/validar_plugin.py

```text
validar_plugin.py [-h] [--sin-pruebas] objetivo
```

- `objetivo`: carpeta del complemento o paquete `.zcplugin`.
- `--sin-pruebas`: no ejecuta sus pruebas.
- `--hijo` es interno: con él se llama a sí mismo en un proceso limpio.

Comprueba, en este orden:

1. Si es un `.zcplugin`, que el ZIP es seguro con las reglas de la instalación: sin rutas absolutas ni `..`, sin unidades, flujos alternativos, nombres reservados de Windows, enlaces, archivos cifrados ni duplicados; 200 MB descomprimido y 20 000 archivos como máximo.
2. El manifiesto, con todas las reglas de `app/plugins/manifiesto.py`.
3. Que existen `LICENSE` y el módulo de la entrada (si no, error), la ayuda y los archivos de los sonidos declarados (si no, aviso).
4. Las letras de acceso de cada página de Preferencias: que cada clave visible con etiqueta tenga letra (sin etiqueta, solo avisa), que no se repita en la página y que no choque con las del diálogo de Preferencias (A, C, P, V, R y U).
5. Las teclas contra el catálogo del núcleo y de los complementos de serie, y las teclas reservadas.
6. El código: importaciones de partes internas, diálogos dentro de `activar()`, `ShowModal` y accessible_output2 (avisos).
7. En un proceso limpio: importa y activa el complemento con un anfitrión de prueba, comprueba que cada orden tiene un manejador que no es provisional y pasa `revisar_teclado` a las ventanas de `ventanas_para_revisar`.
8. Sus pruebas con pytest, en la carpeta `pruebas/` o `tests/`.

Los pasos 7 y 8 usan una carpeta `data` temporal (variable `APP_DATA_DIR`), que se borra al terminar. Escribe los errores y los avisos y termina con «Resultado: válido.» o «Resultado: no válido.». Devuelve 0 si no hay errores (los avisos no cuentan) y 1 si hay alguno.

### tools/empaquetar_plugin.py

```text
empaquetar_plugin.py [-h] [--firmar CLAVE] [--salida SALIDA] carpeta
```

- `--firmar CLAVE`: archivo con la clave privada Ed25519 (32 bytes en crudo, o en hexadecimal o base64 en una línea). Escribe `firma.ed25519` con `app.plugins.firma.firmar_complemento`.
- `--salida`: ruta del paquete. Por defecto, `<id>-<versión>.zcplugin` junto a la carpeta.

Valida el manifiesto y exige `LICENSE` antes de crear nada. Sin `--firmar`, si la carpeta tiene una `firma.ed25519` que ya no corresponde a los archivos, la borra y avisa. Devuelve 0 y escribe la ruta del paquete, o 1 con el motivo.

No use `tools/firmar_version.py` para complementos: firma los manifiestos de actualización de zCommander con otro prefijo.

### Modo desarrollo

```powershell
.venv\Scripts\python main.py --desarrollo-complementos C:\ruta\de\mi_complemento
```

Carga el complemento desde esa carpeta (confianza «En desarrollo»), añade la orden «&Recargar el complemento en desarrollo» y anuncia los avisos de tiempo y de accesibilidad: una `VentanaComplemento` pasa `revisar_teclado` la primera vez que se muestra. También se activa con la preferencia `complementos.modo_desarrollo`.

## Licencia

Un complemento se carga en el mismo proceso que zCommander y forma con él una obra combinada. Por eso:

- Publíquelo bajo `GPL-3.0-or-later` o una licencia compatible con la GPL-3.0: MIT, BSD, Apache-2.0, ISC, CC0, LGPL, GPL-2.0-or-later o MPL-2.0.
- Ponga el identificador SPDX en el campo `licencia` del manifiesto. Debe ser un identificador SPDX bien formado; si no, el manifiesto no se valida.
- Incluya el texto de la licencia en `LICENSE`. Sin ese archivo, el validador, el empaquetador y el gestor rechazan el complemento. `tools/crear_plugin.py` copia el de zCommander (GPL-3.0).
- Empiece cada archivo de código propio (`.py` y el manifiesto) con dos líneas de comentario:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ana Ejemplo
```

- Las bibliotecas de `lib/` conservan su licencia y su aviso de copyright.

El diseño (`docs/diseno-2.md`, 2.1) prevé que el gestor avise si la licencia de un complemento no está en la lista de compatibles, sin impedir la instalación. En esta versión el gestor y el resumen de instalación muestran la licencia, pero todavía no hacen esa comprobación: es responsabilidad del autor.

## Ejemplo completo: Contador de líneas

Este complemento cuenta las líneas de los archivos de texto elegidos y lo anuncia. Tiene una orden con tecla, una columna, una opción de configuración con su página de Preferencias, un sonido, su ayuda y cuatro pruebas. El código de este apartado es exactamente el que pasó `tools/validar_plugin.py` y `tools/empaquetar_plugin.py` sin errores ni avisos.

### Crear la carpeta

```powershell
.venv\Scripts\python tools\crear_plugin.py C:\complementos\lineas --id ana.lineas --nombre "Contador de líneas" --autor "Ana Ejemplo" --descripcion "Cuenta las líneas de los archivos de texto elegidos y lo anuncia."
```

Después:

1. Cambie el nombre de `sonidos\saludo.wav` a `sonidos\contado.wav`.
2. Borre `pruebas\test_complemento.py` de la plantilla.
3. Sustituya `manifiesto.toml`, `__init__.py`, `doc\es\leeme.md` y `doc\es\cambios.md` por los de abajo y añada `pruebas\test_lineas.py`.
4. Deje `LICENSE` como lo creó la herramienta.

### manifiesto.toml

```toml
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ana Ejemplo
formato = 1
id = "ana.lineas"
nombre = "Contador de líneas"
descripcion = "Cuenta las líneas de los archivos de texto elegidos y lo anuncia."
version = "1.0.0"
autor = "Ana Ejemplo"
licencia = "GPL-3.0-or-later"
api_minima = "1.0"
api_probada = "1.1"
entrada = "__init__:Complemento"

[[ordenes]]
id = "contar"
etiqueta = "Contar &líneas"
ayuda = "Cuenta las líneas de los archivos de texto marcados o del cursor y anuncia el total."
ambito = "panel"
menu = "complementos"
teclas = ["Alt+Shift+L"]

[[columnas]]
id = "lineas"
titulo = "Líneas"
tipo = "numero"
lenta = true

[[paginas]]
id = "general"
titulo = "General"

[[configuracion]]
clave = "tamano_maximo_mb"
tipo = "entero"
defecto = 20
minimo = 1
maximo = 500
etiqueta = "&Tamaño máximo de cada archivo, en MB:"
ayuda = "Los archivos más grandes no se cuentan, para no tardar demasiado."
pagina = "general"

[[sonidos]]
id = "contado"
nombre = "Líneas contadas"
descripcion = "Suena al terminar de contar las líneas."
prioridad = "baja"
```

Por qué así:

- La primera versión probada fue `Ctrl+Shift+L`, y el validador respondió «La tecla Ctrl+Shift+L de la orden contar ya la usa macro_ultima: zCommander no se la dará». `Alt+Shift+L` está libre.
- La letra T de la etiqueta de configuración no choca con las del diálogo de Preferencias (A, C, P, V, R y U).
- `api_minima = "1.0"` porque el código solo usa la API 1.0; las pruebas usan `contexto_de_prueba(..., anfitrion=zc)` de la 1.1, por eso `api_probada = "1.1"`.

### __init__.py

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ana Ejemplo
"""Contador de líneas (ana.lineas): cuenta las líneas de los archivos de texto elegidos.

- La orden «Contar líneas» corre en el hilo de la interfaz: solo reúne los
  archivos y manda el recuento a un hilo con ``zc.tareas``.
- El recuento anuncia el total con ``zc.anunciar``, que vale desde cualquier hilo.
- La columna «Líneas» se calcula en un hilo del complemento y respeta la cancelación.
"""

from __future__ import annotations

from typing import Any

from app.plugins import api

_, ngettext = api.traduccion("ana.lineas")

EXTENSIONES = (".txt", ".md", ".csv", ".log")
BLOQUE = 1024 * 1024


def es_texto(entrada: api.Entrada) -> bool:
	"""Verdadero si la entrada es un archivo con una extensión de texto conocida."""
	return not entrada.es_carpeta and not entrada.es_superior and entrada.nombre.casefold().endswith(EXTENSIONES)


def contar_lineas(proveedor: api.Proveedor, ruta: str, cancelacion: Any = None) -> int:
	"""Líneas de un archivo; la última cuenta aunque no acabe en salto de línea [trabajo]."""
	lineas = 0
	ultimo = b"\n"
	with proveedor.abrir_lectura(ruta) as archivo:
		while bloque := archivo.read(BLOQUE):
			api.comprobar(cancelacion)
			lineas += bloque.count(b"\n")
			ultimo = bloque[-1:]
	return lineas if ultimo == b"\n" else lineas + 1


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		# Solo registra funciones: nada lento y ningún diálogo.
		self.zc = zc
		zc.ordenes.manejador("contar", self.contar)
		zc.columnas.extractor("lineas", self.columna_lineas)

	def _limite(self) -> int:
		return int(self.zc.config.obtener("tamano_maximo_mb")) * 1024 * 1024

	# Orden [interfaz]: dura muy poco; el trabajo va a un hilo.
	def contar(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		archivos = [e for e in panel.elementos_trabajo() if es_texto(e)]
		if not archivos:
			ctx.anunciar(_("No hay archivos de texto entre los elegidos"), api.RESULTADO)
			return
		self.zc.tareas.enviar(self._contar_en_hilo, panel.proveedor, archivos, nombre="ana.lineas:contar")

	# [trabajo]: recibe la tarea, que sirve de cancelación.
	def _contar_en_hilo(self, tarea: Any, proveedor: api.Proveedor, archivos: list[api.Entrada]) -> None:
		limite = self._limite()
		total = contados = omitidos = 0
		for entrada in archivos:
			api.comprobar(tarea)
			if entrada.tamano > limite:
				omitidos += 1
				continue
			try:
				total += contar_lineas(proveedor, entrada.ruta, tarea)
				contados += 1
			except api.ErrorArchivos as error:
				self.zc.registro.warning("No se pudo leer %s: %s", entrada.ruta, error)
				omitidos += 1
		texto = ngettext("{n} línea", "{n} líneas", total).format(n=total)
		texto += " " + ngettext("en {c} archivo", "en {c} archivos", contados).format(c=contados)
		if omitidos:
			texto += ". " + ngettext("{o} archivo sin contar", "{o} archivos sin contar", omitidos).format(o=omitidos)
		self.zc.sonidos.sonar("contado")
		self.zc.anunciar(texto, api.RESULTADO)

	# Columna [trabajo]: None se muestra como «Sin datos».
	def columna_lineas(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		if not es_texto(entrada) or entrada.tamano > self._limite():
			return None
		return str(contar_lineas(proveedor, entrada.ruta, cancelacion))
```

Qué muestra este código:

- `activar()` solo registra. No lee archivos ni pregunta nada.
- El manejador de la orden filtra lo elegido (rápido) y manda el recuento a `zc.tareas`. Si no hay nada que contar, lo dice en el acto con `ctx.anunciar`, porque está en el hilo de la interfaz.
- El recuento, en un hilo, comprueba la cancelación en cada archivo y en cada bloque, y anuncia con `zc.anunciar`, que vale desde cualquier hilo.
- Lee con `proveedor.abrir_lectura`, así funciona en cualquier origen (disco, comprimido, nube), no solo en el disco local.
- Un archivo que no se puede leer no rompe el recuento: se apunta en el registro y se cuenta como «sin contar».
- Los textos pasan por `_` y `ngettext` de `api.traduccion`.

### doc/es/leeme.md

```markdown
# Contador de líneas

Cuenta las líneas de los archivos de texto (txt, md, csv y log) y lo anuncia.

## Órdenes

- **Contar líneas** (Alt+Mayús+L, menú Complementos, Contador de líneas): cuenta las líneas de los archivos marcados o, si no hay ninguno marcado, del archivo del cursor, y anuncia el total. Las carpetas y los archivos que no son de texto no se cuentan.

## Columna

- **Líneas**: número de líneas de cada archivo de texto. Se añade desde el diálogo de columnas del panel. En los demás archivos dice «Sin datos».

## Preferencias

En Preferencias, Complementos, Contador de líneas, General:

- **Tamaño máximo de cada archivo, en MB**: los archivos más grandes no se cuentan. Valor de fábrica: 20.

## Sonido

- **Líneas contadas**: suena al terminar de contar. Se cambia o se calla en Preferencias, Sonidos.
```

### doc/es/cambios.md

```markdown
# Novedades de Contador de líneas

## 1.0.0

- Primera versión: orden «Contar líneas», columna «Líneas» y tamaño máximo configurable.
```

### pruebas/test_lineas.py

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ana Ejemplo
"""Pruebas de «Contador de líneas» con ``api.pruebas`` (sin ventana ni wx)."""

from __future__ import annotations

from pathlib import Path

from app.plugins import api
from app.plugins.api import pruebas

CARPETA = Path(__file__).resolve().parents[1]


def _entrada(ruta: Path) -> api.Entrada:
	return api.Entrada(ruta.name, str(ruta), tamano=ruta.stat().st_size)


def _esperar_tareas(zc: pruebas.AnfitrionFalso) -> None:
	for tarea in zc.tareas.tareas_activas():
		tarea.esperar_fin(10)


def test_cuenta_las_lineas_de_los_archivos_marcados(tmp_path):
	uno = tmp_path / "uno.txt"
	uno.write_text("primera\nsegunda\ntercera", encoding="utf-8")
	dos = tmp_path / "dos.md"
	dos.write_text("# Título\n\nTexto\n", encoding="utf-8")
	foto = tmp_path / "foto.jpg"
	foto.write_bytes(b"\xff\xd8\xff")
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	panel = pruebas.PanelFalso([_entrada(uno), _entrada(dos), _entrada(foto)], marcadas=["uno.txt", "dos.md", "foto.jpg"])
	zc.ejecutar("contar", pruebas.contexto_de_prueba(activo=panel, anfitrion=zc))
	_esperar_tareas(zc)
	assert ("6 líneas en 2 archivos", api.RESULTADO) in zc.anuncios
	assert zc.sonidos_pedidos == ["ana.lineas:contado"]


def test_sin_archivos_de_texto_lo_dice(tmp_path):
	foto = tmp_path / "foto.jpg"
	foto.write_bytes(b"\xff\xd8\xff")
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	panel = pruebas.PanelFalso([_entrada(foto)])
	zc.ejecutar("contar", pruebas.contexto_de_prueba(activo=panel, anfitrion=zc))
	assert zc.anuncios == [("No hay archivos de texto entre los elegidos", api.RESULTADO)]
	assert zc.sonidos_pedidos == []


def test_columna_lineas(tmp_path):
	texto = tmp_path / "notas.log"
	texto.write_text("a\nb\n", encoding="utf-8")
	zc = pruebas.anfitrion_de_prueba(CARPETA)
	assert zc.columna("lineas", _entrada(texto)) == "2"
	assert zc.columna("lineas", api.Entrada("fotos", str(tmp_path), es_carpeta=True)) is None


def test_el_tamano_maximo_sale_de_la_configuracion(tmp_path):
	grande = tmp_path / "grande.txt"
	grande.write_bytes(b"x\n" * (600 * 1024))
	zc = pruebas.anfitrion_de_prueba(CARPETA, config={"tamano_maximo_mb": 1})
	try:
		assert zc.columna("lineas", _entrada(grande)) is None
	finally:
		zc.config.restablecer()
	assert zc.config.obtener("tamano_maximo_mb") == 20
```

Notas sobre las pruebas:

- La orden manda el recuento a `zc.tareas`; `_esperar_tareas` espera a que termine antes de mirar los anuncios.
- El sonido se pide con `zc.sonidos.sonar`, que `AnfitrionFalso` apunta en `sonidos_pedidos`.
- La prueba de configuración vuelve a los valores de fábrica al terminar, para no afectar a las demás.

### Validar y empaquetar

```powershell
.venv\Scripts\python tools\validar_plugin.py C:\complementos\lineas
.venv\Scripts\python tools\empaquetar_plugin.py C:\complementos\lineas
.venv\Scripts\python tools\validar_plugin.py C:\complementos\ana.lineas-1.0.0.zcplugin
.venv\Scripts\python tools\empaquetar_plugin.py C:\complementos\lineas --firmar C:\claves\ana.clave
```

Resultado de cada paso al preparar esta guía:

1. Validar la carpeta: «Resultado: válido.», código 0. Las cuatro pruebas pasan (pytest: «4 passed»).
2. Empaquetar: «Paquete creado: ...\ana.lineas-1.0.0.zcplugin», código 0. El paquete contiene `LICENSE`, `__init__.py`, `doc/es/cambios.md`, `doc/es/leeme.md`, `manifiesto.toml`, `pruebas/test_lineas.py` y `sonidos/contado.wav`.
3. Validar el paquete: «Resultado: válido.», código 0.
4. Empaquetar con firma: «Paquete creado y firmado: ...», código 0. El paquete firmado también es válido y el resumen de instalación dice «Confianza: Firmado por un autor nuevo».

Para comprobar que el validador no da por buenas unas pruebas rotas, se cambió el total esperado de 6 a 7 en una copia: el validador respondió «Sus pruebas fallan» y «Resultado: no válido.».

## Lista de comprobación antes de publicar

1. `tools/validar_plugin.py` devuelve 0 con la carpeta y con el `.zcplugin`, sin avisos que pueda evitar.
2. El manifiesto declara solo los permisos que usa, y la licencia es GPL-3.0-or-later o compatible.
3. Cada archivo propio lleva la cabecera SPDX de dos líneas y el paquete trae `LICENSE`.
4. `doc/es/leeme.md` explica cada orden con su tecla, cada columna, cada preferencia y cada sonido; `doc/es/cambios.md` tiene la versión nueva.
5. Ha hecho la prueba manual con NVDA, JAWS y Narrador.
6. El paquete está firmado con su clave y, si publica actualizaciones, el JSON de `url_actualizacion` está firmado con la misma.
7. Sube la versión en el manifiesto en cada publicación: el gestor no instala una versión igual o más baja que la instalada.
