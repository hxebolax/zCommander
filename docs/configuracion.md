# Anexo: claves de configuración

Generado con `python tools/generar_anexos.py` a partir de `app/core/configuracion.py`. No lo edite a mano.

Se guardan en `data/config/settings.json`. El formato de cada clave es `seccion.clave`; el tipo lo fija el valor por defecto. Los valores de fábrica son los del perfil Intermedio. Etiquetas y ayudas: `app/core/descripciones_config.py`.

## Sección general

- `general.confirmar_salida`: bool, por defecto `True`. Pregunta antes de cerrar zCommander con F10 o Alt+X. Página «General» de Preferencias.
- `general.confirmar_eliminar`: bool, por defecto `True`. Pregunta antes de enviar a la papelera. Página «General» de Preferencias.
- `general.confirmar_eliminar_definitivo`: bool, por defecto `True`. Pregunta antes de eliminar sin papelera. Muy recomendable. Página «General» de Preferencias.
- `general.confirmar_ejecutar`: bool, por defecto `False`. Pregunta antes de ejecutar .exe, .bat, .cmd, .msi y accesos directos. Los .ps1, .vbs y .js siempre preguntan. Página «General» de Preferencias.
- `general.usar_papelera`: bool, por defecto `True`. Si se desactiva, Eliminar actúa como Eliminar definitivamente y pide su confirmación. Página «General» de Preferencias.
- `general.consola`: str, por defecto `'cmd'`; admite: cmd, powershell, terminal. Programa que abre «Abrir consola aquí» y las órdenes en consola: cmd, PowerShell o Windows Terminal. Página «General» de Preferencias.
- `general.ejecutar_siempre_en_consola`: bool, por defecto `False`. La línea de órdenes abre una consola que queda abierta en lugar de capturar la salida. Página «General» de Preferencias.
- `general.restaurar_sesion`: bool, por defecto `True`. Vuelve a abrir las carpetas, pestañas y vistas de la última vez. Página «General» de Preferencias.
- `general.asistente_hecho`: bool, por defecto `False`. Interno: el asistente de primer arranque ya se mostró. No aparece en Preferencias.
- `general.tiempo_unidad_s`: int, por defecto `10`; de 2 a 120. Si una unidad o carpeta de red no responde en este tiempo, se da por no disponible. Página «General» de Preferencias.
- `general.aviso_lectura_ms`: int, por defecto `300`; de 0 a 5000. Si leer una carpeta tarda más, se anuncia «Leyendo». Página «General» de Preferencias.
- `general.tamano_historial`: int, por defecto `100`; de 10 a 1000. Cuántas carpetas recuerda cada panel. Página «General» de Preferencias.
- `general.tamano_historial_ordenes`: int, por defecto `200`; de 10 a 2000. Cuántas órdenes recuerda la línea de órdenes. Página «General» de Preferencias.
- `general.pegar_ruta_del_portapapeles`: bool, por defecto `False`. Si el portapapeles tiene texto con una ruta, Pegar va a esa carpeta en lugar de pegar archivos. Página «General» de Preferencias.
- `general.diferencias_externo`: str, por defecto `''`. Orden para comparar dos archivos (%P y %T). Vacío: la comparación interna. Página «Visor y editor» de Preferencias.
- `general.arrancar_con_windows`: bool, por defecto `False`. Solo en la versión compilada: añade zCommander al inicio de Windows. Es la única escritura en el Registro de Windows. Página «General» de Preferencias.
- `general.no_preguntar`: list, por defecto `[]`. Confirmaciones que ya no se preguntan; se recuperan en la página Confirmaciones. No aparece en Preferencias.

## Sección paneles

- `paneles.teclear_en_linea_ordenes`: bool, por defecto `False`. Como en Norton Commander. Si se desactiva, teclear hace búsqueda rápida. Página «Paneles» de Preferencias.
- `paneles.mostrar_ocultos`: bool, por defecto `False`. También con Ctrl+punto. Página «Paneles» de Preferencias.
- `paneles.carpetas_primero`: bool, por defecto `True`. Las carpetas se muestran antes que los archivos. Página «Paneles» de Preferencias.
- `paneles.orden_natural`: bool, por defecto `True`. «archivo2» va antes que «archivo10». Página «Paneles» de Preferencias.
- `paneles.fila_superior`: bool, por defecto `True`. Primera fila de cada carpeta que lleva a la carpeta superior. Página «Paneles» de Preferencias.
- `paneles.entrar_en_comprimidos`: bool, por defecto `True`. ZIP, TAR y 7z se abren como carpetas. Si se desactiva, Intro los abre con su programa. Página «Paneles» de Preferencias.
- `paneles.columnas`: list, por defecto `['nombre', 'extension', 'tamano', 'modificado']`. Se eligen en Opciones, Columnas por defecto. No aparece en Preferencias.
- `paneles.anchos`: dict, por defecto `{}`. Interno: anchos de las columnas. No aparece en Preferencias.
- `paneles.formato_fecha`: str, por defecto `'corta'`; admite: corta, larga, iso. Corta (8/11/2026 14:05), larga (con segundos) o ISO (2026-11-08 14:05). Página «Paneles» de Preferencias.
- `paneles.formato_tamano`: str, por defecto `'legible'`; admite: legible, bytes, mixto. Legible (1,2 MB), en bytes (1.234.567) o mixto (bytes hasta 1 MB). Página «Paneles» de Preferencias.
- `paneles.iconos`: bool, por defecto `False`. Iconos de Windows junto a los nombres. Página «Paneles» de Preferencias.
- `paneles.vigilar_cambios`: bool, por defecto `True`. El panel se actualiza solo cuando cambian los archivos (no en unidades extraíbles). Página «Paneles» de Preferencias.
- `paneles.tiempo_busqueda_rapida_ms`: int, por defecto `1000`; de 300 a 5000. Tiempo durante el que las letras tecleadas se suman a la búsqueda. Página «Paneles» de Preferencias.
- `paneles.retardo_arbol_ms`: int, por defecto `400`; de 0 a 3000. Pausa al moverse por la vista Árbol antes de ir a la carpeta. Página «Paneles» de Preferencias.
- `paneles.orientacion`: str, por defecto `'vertical'`; admite: vertical, horizontal. Lado a lado (vertical) o uno encima de otro (horizontal). Página «Paneles» de Preferencias.
- `paneles.seleccionar_sin_extension`: bool, por defecto `True`. En Renombrar en el sitio, solo queda seleccionado el nombre. Página «Paneles» de Preferencias.
- `paneles.patrones_en_carpetas`: bool, por defecto `False`. Marcar por patrón y filtros incluyen carpetas. Página «Paneles» de Preferencias.
- `paneles.mover_tras_marcar`: bool, por defecto `True`. Como en Norton Commander. Página «Paneles» de Preferencias.
- `paneles.marcas_como`: str, por defecto `'seleccion'`; admite: seleccion, columna. Como selección de la lista: lo marcado queda seleccionado y el lector dice «seleccionado» al final de la fila (y, con varias marcas, «no seleccionado» en las demás). En la columna Marca: lo marcado dice «Marcado» en una columna que puede colocar donde quiera con Columnas y Orden de lectura (si la pone la primera, se oye antes del nombre); la lista no usa la selección para las marcas, así que ningún lector lo dice dos veces. Al elegirla, la columna Marca se añade la primera en las pestañas que no la tienen y no se puede quitar mientras siga elegida. Con NVDA leyendo las cabeceras de tabla, si la Marca va la primera NVDA dice «Nombre:» delante de cada fila sin marcar; para evitarlo, instale el complemento de zCommander para NVDA, ponga la Marca detrás del Nombre con Columnas u Orden de lectura, o desactive en NVDA la lectura de cabeceras de tabla. Página «Accesibilidad» de Preferencias.
- `paneles.lectura`: list, por defecto `[]`. Se elige en Opciones, Personalización, Orden de lectura de las columnas. No aparece en Preferencias.

## Sección vista

- `vista.linea_ordenes_visible`: bool, por defecto `True`. Campo para escribir órdenes de Windows debajo de los paneles. Página «Vista» de Preferencias.
- `vista.barra_teclas_visible`: bool, por defecto `True`. Botones con la acción de cada tecla F (para el ratón). Página «Vista» de Preferencias.
- `vista.barra_estado_visible`: bool, por defecto `True`. Mensajes, operaciones en curso y espacio libre. Página «Vista» de Preferencias.
- `vista.tema`: str, por defecto `'sistema'`; admite: sistema, norton, alto_contraste. Sistema (colores de Windows), Norton clásico (azul y cian) o alto contraste. Página «Vista» de Preferencias.
- `vista.fuente`: str, por defecto `''`. Vacío: el de Windows. Página «Vista» de Preferencias.
- `vista.tamano_fuente`: int, por defecto `10`; de 8 a 40. De 8 a 40. Se aplica al momento a las listas de los paneles. El visor y el editor tienen su propio tamaño en la página «Visor y editor». Página «Vista» de Preferencias.
- `vista.vista_rapida_kb`: int, por defecto `256`; de 4 a 65536. Cuánto se lee de cada archivo en la vista rápida. Página «Vista» de Preferencias.
- `vista.barra_botones_visible`: bool, por defecto `False`. Barra de botones configurable debajo de los paneles. Alt+Mayús+F11 lleva a ella. Página «Vista» de Preferencias.
- `vista.teclas_en_menus`: bool, por defecto `True`. Cada elemento de menú dice su tecla. Página «Vista» de Preferencias.
- `vista.menus_por_nivel`: bool, por defecto `False`. Los menús muestran solo las órdenes del nivel del perfil; al final de cada menú, Mostrar todas las órdenes. Página «Personalización» de Preferencias.
- `vista.columnas_por_carpeta`: bool, por defecto `True`. Al entrar en una carpeta se aplica el conjunto de columnas de su regla. Página «Personalización» de Preferencias.
- `vista.recordar_vista_por_carpeta`: bool, por defecto `False`. El orden, la vista y el filtro que cambie en una carpeta se recuerdan al volver. Página «Personalización» de Preferencias.

## Sección accesibilidad

- `accesibilidad.anuncios`: bool, por defecto `True`. Si se desactiva, zCommander no dice nada por su cuenta salvo errores y preguntas. Página «Accesibilidad» de Preferencias.
- `accesibilidad.detalle`: str, por defecto `'normal'`; admite: breve, normal, detallado. Breve: solo lo esencial y la respuesta a lo que pide. Normal: también cambios de carpeta y marcas. Detallado: también consejos y recuentos. Página «Accesibilidad» de Preferencias.
- `accesibilidad.progreso_voz`: str, por defecto `'inicio_fin'`; admite: hitos, inicio_fin, final. Cada 25 %, al empezar y al terminar, o solo al terminar. Página «Accesibilidad» de Preferencias.
- `accesibilidad.consejos`: bool, por defecto `False`. Una frase con las teclas útiles al entrar en un comprimido, un servidor o una lista de resultados, y al arrancar. Página «Accesibilidad» de Preferencias.
- `accesibilidad.leer_numero_fila`: bool, por defecto `True`. Al leer columnas con Izquierda, Derecha o Ctrl+número. Página «Accesibilidad» de Preferencias.
- `accesibilidad.leer_cabecera`: bool, por defecto `True`. Al leer columnas con Izquierda, Derecha o Ctrl+número. Página «Accesibilidad» de Preferencias.
- `accesibilidad.leer_contenido`: bool, por defecto `True`. Si se desactivan las tres, se dice el contenido. Página «Accesibilidad» de Preferencias.
- `accesibilidad.retardo_voz_ms`: int, por defecto `150`; de 0 a 2000. Espera antes de hablar para no pisar lo que el lector dice al mover el foco. Página «Accesibilidad» de Preferencias.
- `accesibilidad.salida_voz`: str, por defecto `'automatica'`; admite: automatica, lector, uia, ninguna. Automática (NVDA o JAWS directamente; Narrador y otros por notificaciones de Windows), siempre por el lector, siempre por notificaciones, o ninguna. Página «Accesibilidad» de Preferencias.
- `accesibilidad.sapi_sin_lector`: bool, por defecto `False`. Sin lector de pantalla, los anuncios se dicen con SAPI. Página «Accesibilidad» de Preferencias.
- `accesibilidad.silencio_nvda`: bool, por defecto `True`. Cuando zCommander mueve el foco por su cuenta (al volver a leer, al aplicar un filtro), el complemento de zCommander para NVDA no lo anuncia. Página «Accesibilidad» de Preferencias.
- `accesibilidad.complemento_nvda_ofrecido`: bool, por defecto `False`. Interno: ya se ofreció instalar el complemento de zCommander para NVDA. No aparece en Preferencias.

## Sección operaciones

- `operaciones.politica_conflicto`: str, por defecto `'preguntar'`; admite: preguntar, sobrescribir, omitir, sobrescribir_si_mas_antiguo, sobrescribir_si_cambia_tamano, renombrar_copia, renombrar_existente. Qué hacer por defecto al copiar o mover sobre un archivo que ya existe. Se puede cambiar en cada copia. Página «Operaciones» de Preferencias.
- `operaciones.verificar`: bool, por defecto `False`. Relee origen y copia y compara sus sumas SHA-256. Más lento. Página «Operaciones» de Preferencias.
- `operaciones.conservar_fechas`: bool, por defecto `True`. La copia mantiene la fecha de modificación y los atributos del original. Página «Operaciones» de Preferencias.
- `operaciones.copiar_enlaces`: bool, por defecto `True`. Si se desactiva, los enlaces y uniones se omiten (nunca se sigue lo que apuntan). Página «Operaciones» de Preferencias.
- `operaciones.copiar_carpetas_vacias`: bool, por defecto `True`. Crea en el destino las carpetas sin archivos. Página «Operaciones» de Preferencias.
- `operaciones.max_paralelas`: int, por defecto `3`; de 1 a 8. Cuántas operaciones en discos distintos pueden ir en paralelo. Se aplica al reiniciar. Página «Operaciones» de Preferencias.
- `operaciones.tamano_bloque_kb`: int, por defecto `1024`; de 64 a 65536. Trozo con el que se copia cuando no es disco local. Página «Operaciones» de Preferencias.
- `operaciones.lista_conflictos`: bool, por defecto `True`. Con varios archivos que ya existen, una sola lista para decidir. Si se desactiva, se pregunta de uno en uno. Página «Operaciones» de Preferencias.

## Sección visor

- `visor.externo`: str, por defecto `''`. Orden para Alt+F3, con %P para el archivo. Las asociaciones tienen prioridad. Página «Visor y editor» de Preferencias.
- `visor.ajuste_linea`: bool, por defecto `True`. Las líneas largas continúan debajo. También con F2 en el visor. Página «Visor y editor» de Preferencias.
- `visor.codificacion`: str, por defecto `'automatica'`; admite: automatica, utf-8, utf-16-le, utf-16-be, cp1252, latin-1, cp850, cp437. Automática o una fija. Página «Visor y editor» de Preferencias.
- `visor.limite_mb`: int, por defecto `16`; de 1 a 2048. Los mayores se ven por bloques. Página «Visor y editor» de Preferencias.
- `visor.tamano_fuente`: int, por defecto `11`; de 8 a 40. En puntos. Página «Visor y editor» de Preferencias.

## Sección editor

- `editor.usar_externo`: bool, por defecto `False`. Si se activa, F4 abre el editor externo en lugar del interno. Página «Visor y editor» de Preferencias.
- `editor.externo`: str, por defecto `'notepad.exe %P'`. Orden con %P para el archivo, por ejemplo notepad.exe %P. Página «Visor y editor» de Preferencias.
- `editor.copia_seguridad`: bool, por defecto `False`. Antes de guardar, el editor deja la versión anterior con extensión .bak. Página «Visor y editor» de Preferencias.
- `editor.tamano_fuente`: int, por defecto `11`; de 8 a 40. En puntos. Página «Visor y editor» de Preferencias.

## Sección busqueda

- `busqueda.subcarpetas`: bool, por defecto `True`. Valor inicial de la casilla en Buscar archivos. Página «Búsqueda» de Preferencias.
- `busqueda.ocultos`: bool, por defecto `False`. Valor inicial en Buscar archivos. Página «Búsqueda» de Preferencias.
- `busqueda.max_resultados`: int, por defecto `100000`; de 100 a 1e+07. La búsqueda se detiene al llegar a este número. Página «Búsqueda» de Preferencias.

## Sección ftp

- `ftp.tiempo_espera_s`: int, por defecto `30`; de 5 a 600. Si el servidor no responde en este tiempo, se da error. Página «Red» de Preferencias.
- `ftp.pasivo`: bool, por defecto `True`. Recomendado detrás de un router. Página «Red» de Preferencias.

## Sección teclado

- `teclado.personalizadas`: dict, por defecto `{}`. Se cambian en Opciones, Mapa de teclas. No aparece en Preferencias.
- `teclado.esquema`: str, por defecto `'norton'`; admite: norton, total_commander, far, explorador. Norton (el de fábrica), Total Commander, Far o Explorador. Página «Personalización» de Preferencias.
- `teclado.globales`: dict, por defecto `{}`. Se eligen con el botón Teclas globales. No aparece en Preferencias.
- `teclado.globales_activas`: bool, por defecto `False`. Teclas que funcionan con zCommander en segundo plano. Página «Personalización» de Preferencias.

## Sección registro

- `registro.nivel`: str, por defecto `'INFO'`; admite: DEBUG, INFO, WARNING, ERROR. DEBUG, INFO, WARNING o ERROR. No aparece en Preferencias.

## Sección ventana

- `ventana.x`: int, por defecto `-1`.  No aparece en Preferencias.
- `ventana.y`: int, por defecto `-1`.  No aparece en Preferencias.
- `ventana.ancho`: int, por defecto `1100`.  No aparece en Preferencias.
- `ventana.alto`: int, por defecto `760`.  No aparece en Preferencias.
- `ventana.maximizada`: bool, por defecto `False`.  No aparece en Preferencias.
- `ventana.division`: float, por defecto `0.5`; de 0.1 a 0.9.  No aparece en Preferencias.

## Sección seguridad

- `seguridad.menus_locales_confiados`: dict, por defecto `{}`. Carpetas cuyo zcommander.menu.json se ha aceptado (ruta y suma). No aparece en Preferencias.

## Sección complementos

- `complementos.inhabilitados`: list, por defecto `[]`. Se cambian en el gestor de complementos. No aparece en Preferencias.
- `complementos.permitir_sin_firma`: bool, por defecto `True`. Si se desactiva, no se instalan ni cargan complementos sin firma. Página «Complementos» de Preferencias.
- `complementos.fallos_maximos`: int, por defecto `3`; de 1 a 10. Tras estos fallos en una sesión, el complemento deja de usarse hasta reiniciar. Página «Complementos» de Preferencias.
- `complementos.modo_desarrollo`: bool, por defecto `False`. Para autores: permite recargar un complemento y anuncia sus avisos de tiempo y accesibilidad. Página «Complementos» de Preferencias.
- `complementos.auditoria`: bool, por defecto `False`. Apunta en el registro las conexiones y procesos de los complementos sin el permiso correspondiente. Página «Complementos» de Preferencias.
- `complementos.confiados`: dict, por defecto `{}`. Interno: suma de cada complemento sin firma que aceptó. No aparece en Preferencias.

## Sección sonidos

- `sonidos.activos`: bool, por defecto `True`. Sonidos que acompañan a lo que pasa en zCommander. También con Ctrl+F11. Página «Sonidos» de Preferencias.
- `sonidos.volumen`: int, por defecto `70`; de 0 a 100. De 0 a 100. Página «Sonidos» de Preferencias.
- `sonidos.paquete`: str, por defecto `'clasico'`. Paquete de sonidos elegido. Página «Sonidos» de Preferencias.
- `sonidos.eventos`: dict, por defecto `{}`. Qué eventos suenan (solo lo cambiado respecto a los valores de fábrica). No aparece en Preferencias.
- `sonidos.progreso`: str, por defecto `'no'`; admite: no, cada_25, cada_10. No, cada 25 % o cada 10 %. Página «Sonidos» de Preferencias.
- `sonidos.sustituir_anuncios`: bool, por defecto `False`. Si un evento tiene sonido activo, no se dice su anuncio breve (por ejemplo, Marcado). Los errores y las preguntas se dicen siempre. Página «Sonidos» de Preferencias.
- `sonidos.intervalo_navegacion_ms`: int, por defecto `40`; de 0 a 500. Como mucho un sonido de navegación en este tiempo. Página «Sonidos» de Preferencias.
- `sonidos.aviso_inicial_mostrado`: bool, por defecto `False`. Interno: ya se dijo que los sonidos están activados. No aparece en Preferencias.

## Sección actualizaciones

- `actualizaciones.comprobar`: bool, por defecto `True`. Comprueba de vez en cuando si hay una versión nueva. Nunca instala sin preguntar. Página «Actualizaciones» de Preferencias.
- `actualizaciones.intervalo_horas`: int, por defecto `24`; de 1 a 720. Intervalo entre comprobaciones de la aplicación. Página «Actualizaciones» de Preferencias.
- `actualizaciones.componentes_comprobar`: bool, por defecto `True`. rclone, libarchive, 7za y FFmpeg. Página «Actualizaciones» de Preferencias.
- `actualizaciones.componentes_intervalo_dias`: int, por defecto `7`; de 1 a 90. Intervalo entre comprobaciones de los componentes. Página «Actualizaciones» de Preferencias.
- `actualizaciones.complementos_comprobar`: bool, por defecto `True`. Para los complementos que publican sus actualizaciones. Página «Actualizaciones» de Preferencias.
- `actualizaciones.fuente`: str, por defecto `'servidor'`; admite: servidor, github, ambas, personalizada. De dónde se busca la versión nueva de zCommander. Servidor de zCommander: xebolax.synology.me, el de siempre. GitHub: las versiones publicadas en el repositorio hxebolax/zCommander. Las dos: se consultan ambas y se ofrece la versión más nueva; si una no responde, se usa la otra sin avisar, y la descarga prueba la otra si falla. Una dirección personalizada: la que escriba en el campo siguiente (por ejemplo, una copia en su red). Con cualquier origen se exige la firma de zCommander: una versión sin firma o firmada por otro nunca se instala. Se aplica en la siguiente búsqueda, sin reiniciar. Los componentes y los complementos tienen su propio origen. Página «Actualizaciones» de Preferencias.
- `actualizaciones.url_personalizada`: str, por defecto `''`. Solo se usa con el origen «Una dirección personalizada», y solo está disponible al elegirlo; con ese origen es obligatoria. Escriba la dirección completa del archivo version.json, que tiene que empezar por https:// y no puede llevar usuario ni contraseña. El archivo tiene que estar firmado por zCommander; el paquete se descarga de la misma carpeta o de las direcciones que indique el archivo. Página «Actualizaciones» de Preferencias.

## Sección copia

- `copia.carpeta`: str, por defecto `''`. Dónde se guardan las copias de seguridad. Vacío: la carpeta backups de data. Página «General» de Preferencias.
- `copia.conservar_automaticas`: int, por defecto `5`; de 1 a 50. Las copias automáticas previas a una restauración más antiguas se borran. Página «General» de Preferencias.
- `copia.partes`: list, por defecto `['preferencias', 'teclas', 'sesion', 'personalizacion', 'conexiones', 'complementos', 'sonidos', 'macros']`. Interno: partes que se eligieron la última vez. No aparece en Preferencias.

## Sección comprimidos

- `comprimidos.usar_libarchive`: bool, por defecto `True`. libarchive abre muchos formatos de comprimido como carpetas. Página «Comprimidos» de Preferencias.
- `comprimidos.usar_7za`: bool, por defecto `True`. El 7za que trae zCommander crea y lee 7z cifrados. Página «Comprimidos» de Preferencias.
- `comprimidos.usar_7zip_instalado`: bool, por defecto `True`. Para RAR y 7z cifrados, si 7-Zip está instalado en el equipo. Página «Comprimidos» de Preferencias.
- `comprimidos.ruta_7zip`: str, por defecto `''`. Vacío: se busca sola. Página «Comprimidos» de Preferencias.
- `comprimidos.metodo_zip`: str, por defecto `'deflate'`; admite: deflate, zstd, almacenar. Deflate (el más compatible), Zstandard o almacenar sin comprimir. Página «Comprimidos» de Preferencias.
- `comprimidos.flujos_como_carpeta`: bool, por defecto `True`. Un archivo comprimido suelto se ve como una carpeta con un archivo dentro. Página «Comprimidos» de Preferencias.

## Sección red

- `red.descubrir_al_entrar`: bool, por defecto `True`. Al abrir la raíz Red se buscan los equipos de la red local en segundo plano. Página «Red» de Preferencias.
- `red.descubrir_mdns`: bool, por defecto `True`. Encuentra NAS, impresoras y equipos que se anuncian por mDNS (Bonjour). Página «Red» de Preferencias.
- `red.descubrir_dominio`: bool, por defecto `True`. Si el equipo está en un dominio, consulta sus equipos. Página «Red» de Preferencias.
- `red.tiempo_descubrir_s`: int, por defecto `45`; de 5 a 300. La búsqueda de equipos se detiene pasado este tiempo. Página «Red» de Preferencias.
- `red.reconectar_al_entrar`: bool, por defecto `True`. Si una unidad de red está desconectada, se intenta volver a conectar al entrar en ella. Página «Red» de Preferencias.
- `red.exigir_cifrado`: bool, por defecto `False`. No se conecta a servidores que no admiten cifrado. Página «Red» de Preferencias.
- `red.mostrar_otros_proveedores`: bool, por defecto `True`. La raíz Red muestra también las conexiones de otros proveedores de Windows. Página «Red» de Preferencias.

## Sección linea

- `linea.alias_activos`: bool, por defecto `True`. Los alias se expanden al ejecutar. Página «Personalización» de Preferencias.
- `linea.autocompletar`: bool, por defecto `True`. Completa rutas, alias y órdenes internas. Página «Personalización» de Preferencias.

## Sección macros

- `macros.anunciar_pasos`: bool, por defecto `False`. Dice cada paso al ejecutarse (nivel detalle). Página «Personalización» de Preferencias.
- `macros.pausa_ms`: int, por defecto `0`; de 0 a 5000. De 0 a 5000. Página «Personalización» de Preferencias.
- `macros.detener_en_error`: bool, por defecto `True`. Un paso que falla detiene la macro y lo dice. Página «Personalización» de Preferencias.

## Sección reglas

- `reglas.activas`: bool, por defecto `True`. Enciende o apaga todas las reglas. Página «Personalización» de Preferencias.

## Claves de los complementos de serie

Cada complemento guarda las suyas en `data/config/plugins/<id>.json`; su nombre completo es `plugin.<id>.<clave>` (diseño 2.0, 3.6).

- `plugin.zc.busqueda_instantanea.motor`: opcion, por defecto `'automatico'`. Qué motor usa la búsqueda instantánea. Con texto contenido siempre se usa el índice de Windows.
- `plugin.zc.busqueda_instantanea.max_resultados`: entero, por defecto `1000`. Cuántos resultados se muestran como mucho en cada búsqueda.
- `plugin.zc.busqueda_instantanea.incluir_ocultos`: bool, por defecto `False`. Si se marca, los resultados incluyen archivos y carpetas ocultos o de sistema.
- `plugin.zc.busqueda_instantanea.carpetas_excluidas`: lista, por defecto `[]`. Lo que esté dentro de estas carpetas no aparece en los resultados.
- `plugin.zc.busqueda_instantanea.retardo_ms`: entero, por defecto `300`. Tiempo sin teclear tras el que se lanza la búsqueda y se anuncia el recuento.
- `plugin.zc.cifrado.formato`: opcion, por defecto `'zcc'`. El .zcc solo lo abre zCommander; el 7z lo abre también 7-Zip. El diálogo Cifrar recuerda el último elegido.
- `plugin.zc.cifrado.coste_scrypt`: opcion, por defecto `'normal'`. Cuánto trabajo cuesta probar cada contraseña. «Alto» resiste mejor a quien intente adivinarla, pero reserva más de medio gigabyte de memoria al cifrar y al descifrar.
- `plugin.zc.cifrado.borrar_originales`: bool, por defecto `False`. Después de comprobar que lo cifrado se descifra bien, los originales van a la papelera. No es un borrado seguro.
- `plugin.zc.cifrado.recordar_en_sesion`: bool, por defecto `False`. Recuerda en memoria la última contraseña que sirvió para descifrar, hasta cerrar zCommander. Nunca se guarda en disco.
- `plugin.zc.documentos.formatos`: lista, por defecto `['pdf', 'docx', 'doc', 'odt', 'epub', 'rtf', 'html', 'fb2']`. Extensiones que abre el lector de documentos (pdf, docx, doc, odt, epub, rtf, html, fb2). Las que quite se ven con el visor interno.
- `plugin.zc.documentos.tamano_maximo_mb`: entero, por defecto `100`. Los documentos más grandes no se convierten (el visor lo dice).
- `plugin.zc.documentos.marcas_pagina`: bool, por defecto `True`. Cada página del PDF es una sección «Página N de M»: F6 va a la siguiente y Control+P a una página.
- `plugin.zc.documentos.texto_alternativo`: bool, por defecto `True`. Dice «[Imagen: descripción]» donde el documento tiene una imagen con texto alternativo.
- `plugin.zc.documentos.formato_salida`: opcion, por defecto `'txt'`. El que propone «Convertir a texto».
- `plugin.zc.documentos.codificacion_salida`: opcion, por defecto `'utf-8'`. La que propone «Convertir a texto».
- `plugin.zc.duplicados.tamano_minimo_kb`: entero, por defecto `1`. Los archivos más pequeños no se comparan. 0 compara todos.
- `plugin.zc.duplicados.excluir`: texto, por defecto `'*.tmp;Thumbs.db;desktop.ini'`. Archivos y carpetas que nunca se comparan.
- `plugin.zc.duplicados.incluir_ocultos`: bool, por defecto `False`. Marcado, también se comparan los archivos ocultos y los de sistema.
- `plugin.zc.duplicados.carpeta_preferida`: carpeta, por defecto `''`. Con «Conservar el de la carpeta preferida», se conserva la copia que está en esta carpeta.
- `plugin.zc.duplicados.accion`: opcion, por defecto `'papelera'`. Qué botón es el predeterminado (Intro) en la lista de duplicados.
- `plugin.zc.ffmpeg.perfil`: opcion, por defecto `'mp3_192'`. Perfil y calidad con los que se abre el diálogo Convertir. Cambia solo al usar otro.
- `plugin.zc.ffmpeg.carpeta_salida`: opcion, por defecto `'otro_panel'`. Dónde se crean los archivos convertidos, extraídos, recortados, normalizados o unidos.
- `plugin.zc.ffmpeg.carpeta_elegida`: carpeta, por defecto `''`. Carpeta de salida cuando se elige «La carpeta elegida abajo». Vacía o inexistente: la del otro panel.
- `plugin.zc.ffmpeg.hilos`: entero, por defecto `0`. Cuántos núcleos del procesador usa FFmpeg. 0 deja que lo decida FFmpeg; un número bajo deja el equipo más libre mientras convierte.
- `plugin.zc.ffmpeg.normalizar_lufs`: decimal, por defecto `-16.0`. Sonoridad objetivo de Normalizar el volumen, de -30 a -10. -16 es la habitual en podcasts y audiolibros; -23, la de la televisión europea (EBU R128).
- `plugin.zc.ffmpeg.conservar_etiquetas`: bool, por defecto `True`. Valor con el que se abre la casilla del diálogo Convertir: copia el artista, el título y las demás etiquetas al archivo convertido.
- `plugin.zc.ffmpeg.perfiles_propios`: lista, por defecto `[]`. Argumentos personalizados guardados.
- `plugin.zc.git.ruta_git`: archivo, por defecto `''`. Ruta de git.exe. Si se deja vacío, se usa el Git instalado en el equipo. Sin Git, solo se pueden ver el estado, el historial y las diferencias.
- `plugin.zc.git.anunciar_al_entrar`: bool, por defecto `True`. Al entrar en una carpeta de un repositorio Git, dice la rama y cuántos cambios hay, con un sonido.
- `plugin.zc.git.refresco_s`: entero, por defecto `5`. La columna Git vuelve a preguntar el estado del repositorio como mucho cada tantos segundos.
- `plugin.zc.hexadecimal.bytes_por_linea`: opcion, por defecto `'16'`. Cuántos bytes tiene cada línea del volcado; Arriba y Abajo se mueven este número de bytes.
- `plugin.zc.hexadecimal.orden_bytes`: opcion, por defecto `'little'`. Cómo lee el inspector los enteros y las fechas. Control+E lo cambia en el editor.
- `plugin.zc.hexadecimal.codificacion_texto`: opcion, por defecto `'cp1252'`. Con la que se muestran, se escriben y se buscan los caracteres en la columna de texto.
- `plugin.zc.hexadecimal.anuncio`: opcion, por defecto `'valor'`. «Desplazamiento 0x1A, 4F, letra O», o además el decimal y el binario del byte.
- `plugin.zc.hexadecimal.copia_seguridad`: bool, por defecto `False`. Copia el archivo como .bak antes de sustituirlo al guardar.
- `plugin.zc.hexadecimal.abrir_solo_lectura`: bool, por defecto `False`. Abre los archivos sin poder cambiarlos (Guardar como sigue funcionando).
- `plugin.zc.imagenes.servicio`: opcion, por defecto `'ninguno'`. Quién describe las imágenes. Ninguno por defecto: la imagen solo sale del equipo si elige un servicio y pide una descripción.
- `plugin.zc.imagenes.url_servicio`: texto, por defecto `'http://127.0.0.1:11434'`. Para Ollama, como http://127.0.0.1:11434. Para una API compatible con OpenAI, la dirección base, como https://api.openai.com/v1. Solo se admite http en la propia máquina; fuera de ella, https.
- `plugin.zc.imagenes.modelo`: texto, por defecto `''`. Nombre del modelo con visión que describe, como llava, gemma3 o gpt-4o-mini.
- `plugin.zc.imagenes.idioma_descripcion`: texto, por defecto `'es'`. Código del idioma en el que se pide la descripción: es (español), ca, gl, eu, en, pt, fr, it o de.
- `plugin.zc.imagenes.longitud`: opcion, por defecto `'breve'`. Cuánto se pide que diga la descripción.
- `plugin.zc.imagenes.calidad_jpeg`: entero, por defecto `90`. De 50 a 100. Más calidad, archivos más grandes. 90 apenas se distingue del original.
- `plugin.zc.imagenes.aviso_privacidad_mostrado`: bool, por defecto `False`. Se pone a verdadero tras avisar la primera vez de adónde se envía la imagen.
- `plugin.zc.metadatos.version_id3`: opcion, por defecto `'2.3'`. Versión de las etiquetas ID3 que se escribe en los MP3 y WAV. La 2.3 la leen todos los reproductores, también los antiguos y los de los coches.
- `plugin.zc.metadatos.conservar_fechas`: bool, por defecto `True`. Al guardar etiquetas, el archivo conserva su fecha de modificación: el orden por fecha del panel no cambia.
- `plugin.zc.metadatos.columnas_musica`: bool, por defecto `True`. Al activarse el complemento, crea (si no existe) el conjunto de columnas Música (Pista, Artista, Título, Álbum y Duración) y su regla: se usa en las carpetas con mayoría de archivos de audio.
- `plugin.zc.monitor.carpetas`: lista, por defecto `[]`. Carpetas en las que se avisa de lo que llega y se aplican las reglas. También se cambian en Monitor de carpetas.
- `plugin.zc.monitor.reglas`: lista, por defecto `[]`. Reglas del monitor, en orden; se editan en Monitor de carpetas.
- `plugin.zc.monitor.retraso_s`: entero, por defecto `5`. Un archivo se da por llegado cuando lleva este tiempo sin cambiar (así una descarga se anuncia al terminar).
- `plugin.zc.monitor.nivel_anuncio`: opcion, por defecto `'resultado'`. Cuándo se dice lo que llega. Los errores de las reglas se dicen siempre.
- `plugin.zc.notas.almacen`: opcion, por defecto `'descript_ion'`. descript.ion es el formato de Total Commander y Double Commander; donde no se puede escribir se usa la base de zCommander.
- `plugin.zc.notas.anunciar_notas`: bool, por defecto `True`. Al entrar en una carpeta con nota se dice «Esta carpeta tiene una nota» y suena su sonido.
- `plugin.zc.notas.viajar`: bool, por defecto `True`. Al copiar o mover dentro de zCommander, el comentario y las etiquetas van con el archivo.
- `plugin.zc.notas.etiquetas`: lista, por defecto `[{'nombre': 'Urgente', 'color': 'rojo'}, {'nombre': 'Importante', 'color': 'naranja'}, {'nombre': 'Facturas', 'color': 'verde'}, {'nombre': 'Pendiente', 'color': 'azul'}]`. Etiquetas disponibles con su nombre y color; se editan en la orden Etiquetas.
- `plugin.zc.nubes.arrancar`: opcion, por defecto `'al_usar'`. El motor de nubes (rclone) puede arrancar al usar una cuenta por primera vez o al iniciar zCommander.
- `plugin.zc.nubes.transferencias`: entero, por defecto `4`. Cuántos archivos copia rclone a la vez. En Google Drive conviene 2 a 4. Al cambiarlo se reinicia el motor si no hay transferencias.
- `plugin.zc.nubes.reintentos`: entero, por defecto `3`. Veces que rclone repite una operación que falló por un error pasajero.
- `plugin.zc.nubes.registro_detallado`: bool, por defecto `False`. Guarda en el registro de zCommander más mensajes de rclone, siempre sin contraseñas ni fichas de acceso. Nunca se vuelcan cabeceras.
- `plugin.zc.nubes.mostrar_experimentales`: bool, por defecto `False`. Muestra en el asistente los servicios que rclone marca como experimentales, como Proton Drive o iCloud Drive.
- `plugin.zc.nubes.limite_subida_kib`: entero, por defecto `0`. Velocidad máxima de subida de todas las nubes juntas.
- `plugin.zc.nubes.limite_bajada_kib`: entero, por defecto `0`. Velocidad máxima de bajada de todas las nubes juntas.
- `plugin.zc.nubes.horario_limites`: texto, por defecto `''`. Por ejemplo 08:00,512k 23:00,off: de 8 a 23 limita a 512 KiB/s y después sin límite. Si hay horario, manda sobre los límites fijos. También se edita por franjas en las propiedades de cada cuenta.
- `plugin.zc.nubes.cache_listados_s`: entero, por defecto `30`. Durante este tiempo no se vuelve a pedir a la nube el contenido de una carpeta ya listada. 0 lo pide siempre.
- `plugin.zc.nubes.papelera_por_defecto`: bool, por defecto `True`. Lo que se borra va a la papelera de la nube, si el servicio la tiene.
- `plugin.zc.nubes.formato_docs`: texto, por defecto `'docx,xlsx,pptx'`. Formatos con los que se bajan los Documentos, Hojas y Presentaciones de Google, separados por comas.
- `plugin.zc.nubes.copia_entre_cuentas`: bool, por defecto `False`. Usa ServerSideAcrossConfigs de rclone; si falla, la copia pasa por zCommander.
- `plugin.zc.nubes.servir_solo_local`: bool, por defecto `True`. Compartir en la red escucha solo en 127.0.0.1 si no se confirma expresamente abrirlo a la red local.
- `plugin.zc.nubes.carpetas_programas`: bool, por defecto `True`. Las carpetas que ya crean OneDrive, Dropbox, Google Drive para escritorio, iCloud, Box, pCloud, Proton Drive o Synology Drive salen en Alt+F1 y Alt+F2 como un disco más, sin iniciar sesión. Desactívela para ocultarlas todas.
- `plugin.zc.nubes.carpetas_ocultas`: lista, por defecto `[]`. Interna: rutas de las carpetas de los programas oficiales que la persona no quiere ver en el selector.
- `plugin.zc.nubes.carpetas_vistas`: lista, por defecto `[]`. Interna: rutas que el asistente ya enseñó, para no volver a preguntar por ellas.
- `plugin.zc.nubes.aviso_winfsp_mostrado`: bool, por defecto `False`. Interna: si ya se mostró el aviso de WinFsp de Acerca de.
- `plugin.zc.ocr.idioma`: texto, por defecto `''`. Etiqueta del idioma de reconocimiento (es-ES); vacío es el de Windows.
- `plugin.zc.ocr.escala_pdf`: decimal, por defecto `2.0`. Cuánto se amplía cada página antes de reconocerla, de 1 a 4. Más escala reconoce mejor la letra pequeña y tarda más.
- `plugin.zc.ocr.carpeta_salida`: carpeta, por defecto `''`. Dónde se guardan los archivos de texto de «Reconocer los marcados». Vacía: junto a cada archivo.
- `plugin.zc.ocr.sobrescribir`: bool, por defecto `False`. Si está desactivada, un archivo de texto que ya existe no se toca y se omite.
- `plugin.zc.ocr.motor`: opcion, por defecto `'automatico'`. Automático usa pywinrt y, si no funciona, PowerShell. Los dos usan el mismo OCR de Windows.
- `plugin.zc.ocupacion.seguir_enlaces`: bool, por defecto `False`. Cuenta también lo que hay al otro lado de los enlaces simbólicos y las uniones, sin contar dos veces lo mismo.
- `plugin.zc.ocupacion.tamano_en_disco`: bool, por defecto `False`. Cuenta lo que de verdad ocupa cada archivo en el disco (comprimidos, dispersos y clúster). Es más lento.
- `plugin.zc.ocupacion.incluir_nube`: bool, por defecto `False`. Cuenta los archivos de OneDrive y similares que no ocupan sitio en este equipo.
- `plugin.zc.ocupacion.anios_antiguedad`: entero, por defecto `2`. La lista de archivos antiguos muestra los que no se han modificado en más de estos años.
- `plugin.zc.organizador.sin_dato`: texto, por defecto `'Sin fecha'`. Si un marcador no da nada (una foto sin fecha EXIF), la carpeta se llama así.
- `plugin.zc.organizador.accion`: opcion, por defecto `'mover'`. Lo que se elige al abrir el organizador: mover o copiar los archivos.
- `plugin.zc.organizador.plantillas`: lista, por defecto `[{'nombre': 'Fotos por fecha EXIF', 'carpetas': 'Fotos\\[EXIF:fecha:AAAA]\\[EXIF:fecha:MM]', 'archivo': '[N]'}, {'nombre': 'Música por artista y álbum', 'carpetas': 'Música\\[MP3:artista]\\[MP3:album]', 'archivo': '[MP3:pista] - [MP3:titulo]'}, {'nombre': 'Documentos por año', 'carpetas': 'Documentos\\[Y]', 'archivo': '[N]'}]`. Plantillas guardadas; se guardan desde el organizador.
- `plugin.zc.papelera.unidades`: lista, por defecto `[]`. Letras de unidad como C: o D:. Sin ninguna, se muestran las papeleras de todas las unidades fijas.
- `plugin.zc.portapapeles.elementos`: entero, por defecto `50`. Cuántas copias guarda el historial. Los elementos fijados no cuentan al borrar los más antiguos.
- `plugin.zc.portapapeles.guardar_entre_sesiones`: bool, por defecto `False`. Guarda el historial en la carpeta de datos, cifrado para su usuario de Windows, y lo recupera al volver a abrir zCommander. Lo que los gestores de contraseñas marcan como privado nunca se guarda.
- `plugin.zc.portapapeles.anunciar_externas`: bool, por defecto `False`. Dice lo que se acaba de copiar fuera de zCommander, con un sonido.
- `plugin.zc.procesos.refresco_s`: entero, por defecto `3`. Cada cuántos segundos se vuelve a leer la lista de procesos mientras la ventana está abierta.
- `plugin.zc.procesos.mostrar_sistema`: bool, por defecto `False`. Incluye en la lista los procesos de Windows y de los servicios (nunca se pueden terminar desde zCommander).
- `plugin.zc.programador.usar_windows`: bool, por defecto `True`. Si se desmarca, las tareas solo se ejecutan mientras zCommander está abierto.
- `plugin.zc.programador.notificaciones`: bool, por defecto `True`. Además del anuncio y del registro de ejecuciones, muestra una notificación al terminar cada tarea.
- `plugin.zc.proyectos.max_carpetas`: entero, por defecto `1000`. Cuántas carpetas recuerda el salto rápido; al pasarse se olvidan las de menos puntuación.
- `plugin.zc.proyectos.peso_frecuencia`: decimal, por defecto `1.0`. Cuánto cuenta el número de visitas frente a lo reciente: 0 solo lo reciente; 1 por defecto; más de 1, la frecuencia manda.
- `plugin.zc.proyectos.media_vida_dias`: entero, por defecto `14`. Una carpeta que no se visita desde hace estos días pesa la mitad en el salto rápido.
- `plugin.zc.proyectos.excluidas`: lista, por defecto `['C:\\Windows']`. Estas carpetas y lo que tienen dentro nunca se proponen ni se cuentan.
- `plugin.zc.reproductor.salto_corto_s`: entero, por defecto `5`. Segundos que avanzan o retroceden Avanzar, Retroceder y las flechas izquierda y derecha de la ventana del reproductor.
- `plugin.zc.reproductor.salto_medio_s`: entero, por defecto `30`. Segundos que saltan Control más flecha izquierda o derecha en la ventana del reproductor.
- `plugin.zc.reproductor.salto_largo_s`: entero, por defecto `300`. Segundos que saltan Re Pág y Av Pág en la ventana del reproductor.
- `plugin.zc.reproductor.volumen`: entero, por defecto `80`. Volumen del reproductor, de 0 a 100. Más y Menos lo cambian en la ventana del reproductor y el cambio se guarda.
- `plugin.zc.reproductor.velocidad`: decimal, por defecto `1.0`. Velocidad de reproducción, de 0,5 a 3. Solo con el motor de Windows; con FFplay siempre es 1.
- `plugin.zc.reproductor.usar_ffplay`: bool, por defecto `True`. Si Windows no puede abrir un archivo (Ogg, Opus, MKV...) y está el componente FFmpeg, se reproduce con FFplay. Con FFplay no se puede cambiar la velocidad.
- `plugin.zc.reproductor.recordar_posicion`: bool, por defecto `True`. Al volver a reproducir un archivo largo (un audiolibro, un podcast) continúa donde se dejó.
- `plugin.zc.reproductor.recordar_desde_min`: entero, por defecto `10`. Solo se recuerda la posición de los archivos que duran al menos estos minutos.
- `plugin.zc.reproductor.anunciar_pista`: bool, por defecto `True`. Dice el número y el título de la pista (de sus etiquetas, si está el complemento de metadatos) cada vez que cambia.
- `plugin.zc.reproductor.formatos_intro`: texto, por defecto `''`. Patrones separados por punto y coma, como *.mp3;*.m4b. Vacío: Intro abre los archivos con el programa de Windows. Una asociación Abrir propia para esos patrones (Opciones, Asociaciones) tiene preferencia.
- `plugin.zc.reproductor.posiciones`: diccionario, por defecto `{}`. Ruta y segundos de cada archivo largo; se guardan en datos/posiciones.json.
- `plugin.zc.seguridad.analizar_descargas`: bool, por defecto `False`. Al terminar una copia desde un servidor o una nube al disco, analiza lo copiado con Microsoft Defender y avisa si encuentra algo.
- `plugin.zc.seguridad.algoritmo`: opcion, por defecto `'sha256'`. Al comparar con el portapapeles, el algoritmo se deduce de la suma copiada; este es el que se usa si no hay ninguna.
- `plugin.zc.seguridad.aviso_virustotal`: bool, por defecto `False`. Verdadero cuando ya se avisó de qué se envía a VirusTotal.
- `plugin.zc.sincronizacion.tolerancia_fecha_s`: entero, por defecto `2`. Diferencia de fecha que no cuenta como cambio. 2 segundos cubre las memorias USB con FAT; 3600 también los cambios de hora.
- `plugin.zc.sincronizacion.verificar`: bool, por defecto `False`. Tras copiar, vuelve a leer el archivo para comprobar que la copia es idéntica. Es más lento.
- `plugin.zc.sincronizacion.dias_versiones`: entero, por defecto `30`. Las versiones (lo sustituido o borrado, en la carpeta _versiones) más antiguas que estos días se borran.
- `plugin.zc.sincronizacion.max_versiones_mb`: entero, por defecto `1024`. Si las versiones de una tarea ocupan más, se borran los días más antiguos hasta caber.
- `plugin.zc.synology.tiempo_conexion_s`: entero, por defecto `10`. Cuánto se espera a que el NAS acepte la conexión antes de dar el error «no responde».
- `plugin.zc.synology.tiempo_peticion_s`: entero, por defecto `30`. Cuánto se espera la respuesta de cada petición. Las subidas y descargas no tienen límite total.
- `plugin.zc.synology.refresco_estado_s`: entero, por defecto `10`. Cada cuánto se vuelve a leer el área visible de la ventana del NAS, sin mover el foco.
- `plugin.zc.synology.anunciar_avisos`: bool, por defecto `True`. Dice una vez cada aviso nuevo (un disco con problemas, un contenedor que falla, un certificado que caduca).
- `plugin.zc.synology.aviso_temperatura_c`: entero, por defecto `55`. A partir de esta temperatura, el área Estado y salud la marca como aviso.
- `plugin.zc.synology.ssh_activado`: bool, por defecto `False`. Desactivado de fábrica. Usa la clave pública del agente de OpenSSH de Windows; la contraseña de sudo se pide cada vez y nunca se guarda.
- `plugin.zc.synology.registro_detallado`: bool, por defecto `False`. Anota en el registro cada petición con sus parámetros. Nunca anota contraseñas, sesiones ni códigos.
- `plugin.zc.synology.demostracion_modo`: opcion, por defecto `'escritura'`. Qué hace el NAS de demostración cuando se le pide un cambio. En los tres casos se empieza en solo lectura.
- `plugin.zc.synology.escritura_hasta`: opcion, por defecto `'sesion'`. Lo que propone el diálogo «Permitir cambios en el NAS». Solo durante la sesión es lo más seguro.
- `plugin.zc.tablas.solo_lectura`: bool, por defecto `True`. Rechaza las consultas que cambian datos (INSERT, UPDATE, DELETE, CREATE...). Desactívela solo si sabe lo que hace.
- `plugin.zc.tablas.filas_maximas`: entero, por defecto `1000000`. El visor y las consultas dejan de leer al llegar a este número de filas y lo dicen en el estado.
- `plugin.zc.tablas.separador`: opcion, por defecto `'automatico'`. Automático lo detecta en cada archivo; los .tsv usan siempre el tabulador.
- `plugin.zc.texto.destino`: opcion, por defecto `'utf8'`. Codificación que propone el diálogo Convertir. Con BOM, los programas antiguos de Windows reconocen mejor el UTF-8.
- `plugin.zc.texto.fin_linea`: opcion, por defecto `'sin_cambio'`. Fin de línea que propone el diálogo Convertir. Sin cambio deja los que tiene cada archivo.
- `plugin.zc.texto.extensiones`: texto, por defecto `'*.txt;*.md;*.csv;*.ini;*.bat;*.py;*.html;*.xml;*.json'`. Patrones separados por punto y coma de los archivos en los que las columnas Codificación y Fin de línea miran el contenido.
- `plugin.zc.texto.copia_bak`: bool, por defecto `True`. Deja el original con la extensión .bak junto al archivo convertido. Sin ella, Deshacer recupera el original mientras zCommander siga abierto.
- `plugin.zc.voz.voz`: texto, por defecto `''`. Nombre exacto de la voz de Windows, como Microsoft Helena Desktop - Spanish (Spain). Es más cómodo elegirla con «Abrir la configuración avanzada...», que lista las voces y deja probarlas.
- `plugin.zc.voz.velocidad`: entero, por defecto `0`. Velocidad de la voz: 0 es la normal de la voz; los positivos, más rápido.
- `plugin.zc.voz.tono`: entero, por defecto `0`. Tono de la voz: 0 es el normal; los positivos, más agudo.
- `plugin.zc.voz.volumen`: entero, por defecto `100`. Volumen de la voz de lectura, aparte del volumen de Windows.
- `plugin.zc.voz.formato_salida`: opcion, por defecto `'mp3'`. Formato que se propone en Convertir a audio. MP3 y Opus necesitan el componente FFmpeg.
- `plugin.zc.voz.pausa_parrafo_ms`: entero, por defecto `400`. Silencio entre un párrafo y el siguiente, al leer y en los audios.
