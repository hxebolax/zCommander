# Novedades de zCommander

Cada versión tiene su apartado, de la más reciente a la más antigua. Tras actualizar, zCommander muestra una vez las novedades de la versión nueva. También puede verlas en el menú Ayuda, «Novedades de la versión».

## Versión 2.0.2 - 2026-11-10

Corrige un fallo grave de la compilación: en un equipo sin Python instalado, zCommander no podía verificar firmas digitales.

### Correcciones

- «Buscar actualizaciones» fallaba con «Falta el paquete cryptography» en los equipos que no tienen Python instalado, y tampoco se podían comprobar las firmas de los complementos ni abrir las copias de seguridad cifradas. La versión portable llevaba una pieza de Python equivocada. Ahora lleva la correcta, y antes de cada publicación se comprueba en un entorno sin Python que las firmas funcionan y que no falta ninguna DLL.
- Si tiene la 2.0.0 o la 2.0.1 en un equipo sin Python, esta vez no podrá actualizar desde el programa: descargue zCommander_v2.0.2.zip de https://github.com/hxebolax/zCommander/releases/latest y extráigalo encima de su carpeta de zCommander. Su configuración, en data\config, se conserva. Desde la 2.0.2, las actualizaciones vuelven a funcionar desde el menú Ayuda.

## Versión 2.0.1 - 2026-11-09

Corrige el foco al volver de los diálogos, añade dos ayudas para las marcas, le deja elegir de dónde se buscan las actualizaciones y permite conectar las nubes sin crear claves. Todo lo demás sigue igual que en la 2.0.0.

### Correcciones

- Al cerrar un diálogo, el foco vuelve a la lista del panel en el que estaba. Antes, a veces Windows lo dejaba en el panel del otro lado y ese pasaba a ser el activo. Si una orden lleva el foco al otro panel a propósito, o hace clic en él con el ratón, se respeta.
- La barra de título dice siempre la carpeta del panel activo, también al cambiar de panel o de pestaña (Insert+T en NVDA). Antes podía decir la del otro panel.

### Marcas

- Preferencias, página «Accesibilidad», opción nueva «Cómo se muestran las marcas»: «Como selección de la lista» (la de siempre, de fábrica) o «En la columna Marca». Con la columna Marca, lo marcado dice «Marcado» en una columna que puede colocar donde quiera con «Columnas» y «Orden de lectura de las columnas», y la lista no usa la selección para las marcas: ningún lector dice «seleccionado» ni lo repite. Funciona igual con NVDA, JAWS y Narrador, sin complementos. Se aplica al momento y se guarda en los perfiles.
- Con «En la columna Marca», la columna Marca se ve siempre: también en la vista breve, en las vistas por carpeta, en las columnas de «Red» y de los complementos y en las pestañas de un espacio de trabajo, y entra en el orden de lectura aunque no la tengan. En «Columnas» no se puede quitar mientras siga elegida (se dice por qué); sí se puede mover. Las pestañas a las que zCommander añadió la Marca siguen cambiando con «Columnas por defecto» y con los perfiles.
- Con NVDA leyendo las cabeceras de tabla y la Marca la primera, NVDA decía «Nombre:» delante de cada fila sin marcar. El complemento de zCommander para NVDA lo evita; sin él, la ayuda de la opción (Ctrl+H) y el manual explican cómo.
- Alt+Mayús+M dice los elementos marcados: cuántos son, su tamaño y sus nombres (hasta 20). Sin marcas, dice cuál es el elemento de trabajo. También en el menú Archivos, submenú Marcas, «Decir los elementos marcados». Con carpetas cuyo tamaño no se ha calculado no dice «0 bytes»: «3 marcados (1 carpeta), 25 MB en archivos», o «2 marcados (2 carpetas)» si todo son carpetas. El recuento al marcar en grupo y el resumen del panel lo dicen igual.
- El manual explica la opción «Bajar al siguiente al marcar con Insert o Espacio» de la página «Paneles»: si se desactiva, el cursor se queda y se anuncia «Marcado: nombre».

### Actualizaciones

- zCommander se publica también en GitHub (hxebolax/zCommander). Preferencias, página «Actualizaciones», opción nueva «Origen de las actualizaciones»: «Servidor de zCommander (xebolax.synology.me)» (la de siempre, de fábrica), «GitHub (hxebolax/zCommander)», «Las dos: la que tenga la versión más nueva» (si una no responde, se usa la otra sin avisar, y la descarga prueba la otra si falla) o «Una dirección personalizada», que se escribe en «Dirección personalizada del archivo version.json» (solo https). Con cualquier origen se exige la firma de zCommander: nada sin firma se instala nunca. Los mensajes de error dicen qué origen falló. Se aplica en la siguiente búsqueda, sin reiniciar. Con «Una dirección personalizada» la dirección es obligatoria y no puede llevar usuario ni contraseña. Un perfil o una copia de seguridad solo cambian el origen de las actualizaciones si usted lo marca en «Órdenes que se podrán ejecutar».

### Nubes

- Conectar una nube ya no pide claves: el asistente «Añadir una cuenta de nube» agrupa los servicios por cómo se conectan (iniciar sesión en el navegador, correo y contraseña, carpeta del programa oficial o avanzado). En Google Drive, OneDrive, Dropbox, Box, pCloud y los demás de navegador basta con el nombre de la cuenta y «Siguiente»; lo avanzado queda en «Opciones avanzadas...». Jottacloud se autoriza también en el navegador (antes había que pegar un código) y deja elegir sus marcas blancas, como Telia o Elgiganten. Las carpetas de OneDrive, Dropbox, Google Drive para escritorio, iCloud, Box, pCloud, Proton Drive y Synology Drive que ya hay en el equipo se ofrecen al empezar y salen en Alt+F1 y Alt+F2 como un disco más. Google Drive pregunta si usar su carpeta de escritorio, el identificador de rclone (puede dejar de funcionar en 2026) o uno propio. Las preguntas habituales de rclone salen en español, y ya no se vuelve a preguntar si hay navegador tras responder a una de ellas.

## Versión 2.0.0 - 2026-11-09

La 2.0 abre zCommander a los complementos, lo mantiene al día solo, protege su configuración y añade 27 complementos de serie pensados para personas ciegas. Todo lo de la 1.0 sigue igual salvo lo que se dice aquí. El manual (F1) tiene un capítulo para cada novedad.

### Complementos

- Menú nuevo «Complementos», con un submenú por cada complemento y el «Gestor de complementos»: habilitar e inhabilitar (Espacio), configurar (Intro), ayuda, novedades, permisos, registro, actualizar, volver a la versión anterior y desinstalar (Supr).
- Instalar complementos desde un archivo .zcplugin, también con Intro sobre el archivo en un panel, tras ver un resumen con su autor, licencia, firma y permisos. Los que no están firmados piden confirmación y el botón predeterminado es «Cancelar».
- Un complemento que falla no detiene zCommander: tras 3 fallos deja de usarse en la sesión. «Reiniciar sin complementos», en el menú Complementos, o mantener Mayús pulsada al arrancar, arrancan en modo seguro.
- 25 complementos de serie: reproductor multimedia, lector de documentos, reconocimiento de texto (OCR), metadatos y etiquetas de audio, búsqueda instantánea, conversor multimedia con FFmpeg, buscador de duplicados, ocupación del disco, archivos en uso y procesos, editor hexadecimal, imágenes, sincronización avanzada, cifrado de archivos, notas y etiquetas, proyectos y salto rápido, historial del portapapeles, lectura en voz y audiolibros, monitor de carpetas, seguridad de descargas, papelera como panel, Git básico, datos tabulares (SQLite y CSV), organizador por metadatos, programador de tareas y codificaciones. Cada uno tiene su ayuda con F1.
- Complemento «Nubes»: Google Drive, OneDrive, Dropbox, Mega, S3, Nextcloud, WebDAV y muchos más servicios como unidades del panel (Alt+F11 abre las cuentas).
- Complemento «NAS Synology»: estado, discos, carpetas, usuarios, paquetes y contenedores de su NAS, en modo solo lectura por defecto, y File Station en el panel (Ctrl+Mayús+F9). Incluye un NAS de demostración para practicar sin riesgo.

### Sonidos

- Un sistema de sonidos completo: más de 150 sonidos que se pueden activar uno a uno en Preferencias, página «Sonidos», con volumen propio.
- Cinco paquetes de sonidos de serie: Clásico, Suave, Retro 8 bits, Minimalista y Cristal. Puede crear los suyos a partir de uno de ellos y compartirlos como .zcsonidos.
- Ctrl+F11 silencia o activa todos los sonidos. El volumen se sube y se baja desde Opciones, submenú «Sonidos».
- Mapa de sonidos, en el menú Ayuda, para escuchar qué significa cada sonido.
- Los sonidos están activados de fábrica, también al actualizar desde la 1.0; se avisa una vez al arrancar. Los tonos de progreso de la 1.0 pasan a la opción «Progreso de las operaciones» de la página «Sonidos», y sus archivos WAV propios, a un paquete «Mis sonidos 1.x».

### Actualizaciones y componentes

- zCommander busca versiones nuevas cada día y, si hay una, la ofrece con sus novedades. También en Ayuda, «Buscar actualizaciones». Si la versión nueva no arranca, se vuelve sola a la anterior.
- Ventana «Componentes externos» (menú Opciones) para actualizar rclone, libarchive, 7za y FFmpeg, con prueba y vuelta atrás automática, y «Restaurar los componentes originales».

### Copias de seguridad y perfiles

- Crear y restaurar copias de seguridad de la configuración (.zcbackup) eligiendo qué partes. Las contraseñas pueden ir cifradas con una contraseña de la copia.
- Exportar e importar perfiles (.zcperfil) para pasar una configuración a otra persona, con vista previa de lo que se aplica.
- Guardar la configuración actual como perfil propio, junto a Novato, Intermedio y Avanzado.
- Antes de restaurar se guarda una copia automática de lo que había.

### Comprimidos

- Se abren como carpetas RAR y RAR5 sin cifrar (también multivolumen), CAB, ISO, LHA, cpio, deb, rpm, XAR, ZIPX, ZIP con AES, .tar.zst, .tar.lz, .tar.lz4 y los .gz, .bz2, .xz, .zst sueltos.
- Con 7-Zip instalado en el equipo, también RAR y 7z cifrados, ARJ, CHM, MSI, WIM, VHD, DMG y otros.
- Comprimir (Alt+F5) crea además ZIP con Zstandard, ZIP cifrado con AES-256, TAR.ZST, TAR.LZ4, TAR.LZ, ISO, cpio, XAR y archivos .gz, .bz2, .xz y .zst sueltos, y dice qué motor usa.

### Red

- Raíz «Red» (Ctrl+Mayús+K, o «Red» en Alt+F1 y Alt+F2): unidades de red, conexiones sin letra, servidores recientes y los equipos de la red a medida que se encuentran.
- Conectar unidades de red con letra automática o sin letra, exigiendo cifrado SMB y recordando la contraseña en Windows; volver a conectar una unidad desconectada; información de la conexión; copiar la ruta UNC; contraseñas guardadas de servidores; y sesiones y archivos abiertos por la red (como administrador).

### Personalización

- Macros: grabar (Ctrl+Mayús+G), repetir la última (Ctrl+Mayús+L), editar, exportar e importar con vista previa.
- Esquemas de teclas de Total Commander, Far y el Explorador, además del de Norton Commander. El mapa de teclas exporta e importa sus teclas (.zcteclas).
- Menú «Mis órdenes», barra de botones (Alt+Mayús+F11 para llegar a ella) y barra de teclas configurables; también se pueden ocultar elementos de los menús.
- Columnas y vista por carpeta, orden de lectura de las columnas, espacios de trabajo (Ctrl+Mayús+W), reglas de anuncio, color y sonido, alias de la línea de órdenes con autocompletar (Ctrl+Espacio) y plantillas para crear archivos nuevos (Mayús+F4).
- Teclas globales, que funcionan con zCommander en segundo plano.
- Preferencias con un árbol de páginas y el campo «Buscar una opción»; páginas nuevas Sonidos, Comprimidos, Actualizaciones, Personalización, Confirmaciones y una por cada complemento.
- La paleta de órdenes (Ctrl+E) muestra primero las favoritas (Ctrl+D) y las más usadas.
- Las confirmaciones que no son de seguridad se pueden silenciar en la nueva página «Confirmaciones» de Preferencias; algunas tienen además la casilla «No volver a preguntar».
- Con el perfil Novato, los menús muestran solo las órdenes básicas; «Ver todas las órdenes en los menús», en Opciones, enseña el resto.
- Arrancar zCommander al iniciar sesión en Windows (página «General»; solo en la versión compilada).

### Accesibilidad

- Complemento de zCommander para NVDA (en el menú Ayuda): lee enteras las celdas largas, evita que NVDA repita el elemento cuando zCommander mueve el foco por su cuenta, respeta el orden de lectura de las columnas y lee la fila completa con NVDA+Mayús+J.
- El visor (F3) recorre por secciones los documentos que abren los complementos: F6 y Mayús+F6, Ctrl+L para la lista de secciones y Ctrl+P para ir a una página.

### Licencia

- zCommander es software libre con licencia GPL-3.0 o posterior. «Acerca de» muestra la licencia, los componentes de terceros y la oferta de fuentes.

### Correcciones

- Menús más ordenados. Cada complemento tiene todas sus órdenes juntas en su submenú, dentro de una categoría del menú Complementos (Multimedia, Documentos y datos, Orden y limpieza del disco, Sistema y seguridad, Automatización, y Nubes y NAS), y ya no aparecen sueltas en Archivos, Comandos o Herramientas: «Ver y editar en hexadecimal» quedaba debajo de Salir. Salir vuelve a ser lo último de Archivos, junto a «Reiniciar zCommander». «Reiniciar sin complementos» pasa al menú Complementos. «Mapa de teclas» entra en Personalización. El gestor de complementos ya no está repetido en Opciones.
- Al entrar en una carpeta, disco o comprimido, el cursor va siempre a la primera fila. Antes se quedaba en el mismo número de fila que tenía en la carpeta anterior. Al subir con Retroceso sigue quedando en la carpeta de la que se sale, y Volver a leer (Ctrl+R) no mueve el cursor.
- En la lista de teclas, la tecla B de «Sincronizar carpetas» decía «Volver a la acción propuesta»; borra en el lado de destino, como dice el manual.

## Versión 1.0.0 - 2026-11-08

Primera versión de zCommander, un gestor de archivos de doble panel para Windows, clon accesible de Norton Commander. Todo lo que sigue es nuevo.

### Ventana y navegación

- Dos paneles con vistas completa, breve, Información (Ctrl+L), Árbol y Vista rápida (Ctrl+Q).
- Pestañas en cada lado (Ctrl+T, Ctrl+W, Ctrl+Tab, Alt+1 a Alt+9), que se pueden bloquear.
- Historial de carpetas por panel (Alt+Izquierda, Alt+Derecha, Alt+F12), favoritos (Ctrl+D), ir a una carpeta (Ctrl+G), árbol de carpetas (Alt+F10) y selector de unidades (Alt+F1 y Alt+F2).
- Ordenación (Ctrl+F3 a Ctrl+F7), filtro (Ctrl+F12), filtro rápido (Ctrl+F), búsqueda rápida tecleando y archivos ocultos (Ctrl+punto).
- Línea de órdenes, salida de las órdenes (Ctrl+O) y barra de teclas F1 a F10.
- La sesión se recuerda: carpetas, pestañas, vistas, historiales y cesta.

### Marcas

- Marcar como en Norton Commander: Insert o Espacio, Mayús con las flechas, Num + y Num - por patrón y Num * para invertir.
- Las mismas órdenes sin teclado numérico: Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N.
- El lector dice «seleccionado» en cada fila marcada, y Ctrl+Mayús+S dice cuántas hay.
- Marcar la misma extensión, restaurar las marcas (Ctrl+Mayús+R) y guardarlas o cargarlas desde un archivo.

### Operaciones con archivos

- Ver (F3) en un visor de texto y hexadecimal, y editar (F4) en un editor que conserva la codificación y el fin de línea.
- Copiar (F5) y mover (F6) en segundo plano, con cola, pausa, verificación y una lista para decidir de una vez qué hacer con los archivos que ya existen.
- Ventana de operaciones en curso (F12), con las decisiones pendientes y «Reintentar los que fallaron».
- Crear carpeta (F7), eliminar a la papelera (F8) o definitivamente (Mayús+F8), renombrar en el sitio (Mayús+F6), duplicar (Mayús+F5) y crear archivo (Mayús+F4).
- Atributos y fechas, propiedades de Windows (Alt+Intro), «Abrir con» y menú contextual del Explorador.
- Enlaces simbólicos, uniones, enlaces duros y accesos directos.
- Deshacer (Ctrl+Z) renombrar, mover, crear carpeta y copiar.

### Herramientas

- Buscar archivos (Alt+F7) por nombre, contenido, tamaño, fecha y atributos, con los resultados en un panel.
- Comparar carpetas (Ctrl+F10) y sincronizarlas (Ctrl+Mayús+F10) con una lista revisable antes de aplicar.
- Renombrado múltiple (Ctrl+M) con las máscaras de Total Commander, vista previa y plantillas.
- Sumas de comprobación, dividir y unir archivos, comparar archivos por contenido y tamaño de carpetas (Mayús+Espacio).
- Vista plana (Ctrl+B) y cesta para reunir archivos de varias carpetas (Ctrl+Mayús+B).
- Portapapeles compatible con el Explorador (Ctrl+C, Ctrl+X, Ctrl+V) y arrastrar y soltar.

### Comprimidos y red

- ZIP, TAR y 7z como carpetas; escritura dentro de los ZIP.
- Comprimir (Alt+F5), extraer (Alt+F6 o Alt+F9) y probar (Alt+Mayús+F9).
- FTP, FTPS y SFTP con gestor de conexiones (Ctrl+K), contraseñas cifradas y comprobación de las huellas de los servidores.
- Unidades de red, rutas \\servidor\recurso y consola en la carpeta actual (F11).

### Personalización

- Perfiles Novato, Intermedio y Avanzado, y asistente de primer arranque.
- Preferencias (Ctrl+coma) que se aplican al momento.
- Mapa de teclas para cambiar cualquier tecla, con aviso de choques.
- Menú de usuario (F2) y asociaciones por tipo de archivo, con variables como %P y %M.
- Columnas por lado, temas Sistema, Norton clásico y Alto contraste, y letra de 8 a 40 puntos.

### Accesibilidad y ayuda

- Pensado para NVDA, JAWS y Narrador: voz directa con NVDA y JAWS, y notificaciones de Windows con Narrador.
- Anuncios por niveles (breve, normal o detallado) y progreso por voz configurable.
- Teclas de consulta: ruta (Ctrl+Mayús+P), resumen (Ctrl+Mayús+S), espacio libre (Ctrl+Mayús+E), estado de las operaciones (Ctrl+Mayús+T), repetir el último anuncio (Ctrl+Mayús+U) e historial de anuncios (Ctrl+Mayús+H).
- Lectura de columnas con Izquierda, Derecha y Ctrl+1 a Ctrl+0.
- Paleta de órdenes (Ctrl+E), modo de ayuda de teclado (Mayús+F12) y ayuda de cada control (Ctrl+H).
- Manual (F1), lista de teclas (Mayús+F1) y estas novedades.
