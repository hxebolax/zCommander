# Manual de zCommander

Versión 2.0.0. Este manual explica cómo instalar y usar zCommander. Está pensado para leerse con un lector de pantalla: cada capítulo es un encabezado de nivel 2 y cada apartado, de nivel 3. Las instrucciones se dan siempre con el teclado.

Para abrir este manual desde zCommander, pulse F1. Para ver todas las teclas, pulse Mayús+F1 o abra el menú Ayuda y elija «Lista de teclas».

Las teclas se escriben como en Windows en español: Ctrl, Alt, Mayús, Intro, Escape, Supr, Retroceso, Re Pág, Av Pág, Insert, Aplicaciones. Num +, Num - y Num * son las teclas más, menos y asterisco del teclado numérico (las «grises» de Norton Commander). Una combinación se escribe con «+» y sin espacios: Ctrl+Mayús+S. Las teclas de este manual son las de fábrica. Si cambia alguna en el mapa de teclas, los menús y la paleta de órdenes dicen la suya; la lista de teclas (Mayús+F1) muestra siempre las de fábrica.

## Qué es zCommander

zCommander es un gestor de archivos de doble panel para Windows. Es un clon accesible de Norton Commander: dos listas de archivos, una al lado de la otra, y teclas de función para ver, copiar, mover y eliminar.

Está hecho sobre todo para personas que usan lector de pantalla (NVDA, JAWS o Narrador), tanto si empiezan como si ya usaban Norton, Total Commander o Far. También sirve a personas con baja visión y a quien prefiere el teclado.

Qué puede hacer con él:

- Moverse por las carpetas y copiar, mover, renombrar y eliminar archivos sabiendo siempre en qué panel y en qué carpeta está.
- Marcar archivos uno a uno, por rangos o por patrones, y saber en todo momento cuántos hay marcados.
- Copiar en segundo plano, con pausa, cola y una lista para decidir de una vez qué hacer con los archivos que ya existen.
- Ver y editar textos, buscar archivos, comparar y sincronizar carpetas, renombrar muchos archivos a la vez.
- Entrar en comprimidos ZIP, TAR y 7z como si fueran carpetas, y trabajar con servidores FTP, FTPS y SFTP.
- Escribir órdenes de Windows, crear su propio menú de usuario y decidir con qué programa se abre cada tipo de archivo.

Novedades de la versión 2.0, cada una con su capítulo en este manual:

- Complementos que amplían zCommander, con 27 de serie: reproductor, lector de documentos, OCR, nubes, NAS Synology y muchos más.
- Un sistema de sonidos completo, con cinco paquetes de sonidos de serie.
- Actualizaciones de zCommander y de sus componentes desde el propio programa.
- Copias de seguridad de la configuración y perfiles que se pueden pasar a otra persona.
- RAR, ISO, CAB y muchos más comprimidos, y la raíz «Red» con los equipos de su red.
- Macros, esquemas de teclas, barra de botones, menús propios, espacios de trabajo, reglas y otras formas de adaptar zCommander.
- Un complemento para NVDA que mejora la lectura de las listas.

## Primeros pasos

### Requisitos

- Windows 10 (versión 1809 o posterior) u 11, de 64 bits.
- Un lector de pantalla, si lo usa: NVDA 2025 o posterior, JAWS 2025 o posterior o el Narrador de Windows 11. El complemento de zCommander para NVDA necesita NVDA 2026.1 o posterior.
- No necesita instalar Python ni ningún otro programa. Los programas que usan algunas funciones (rclone para las nubes, FFmpeg para el audio y el vídeo, 7za y libarchive para los comprimidos) vienen dentro de zCommander.
- Algunas funciones usan programas que instala usted, si los quiere: 7-Zip para los RAR y 7z cifrados, WinFsp para montar una nube como letra de unidad y Everything para la búsqueda instantánea.

### Instalar la versión portable

zCommander es portable: no se instala en el sistema ni escribe en el registro de Windows. Todo lo que guarda está dentro de su carpeta.

1. Descargue el archivo zCommander_v2.0.0.zip.
2. En el Explorador, sitúese sobre el archivo, pulse la tecla Aplicaciones y elija «Extraer todo».
3. Elija una carpeta donde tenga permiso de escritura, por ejemplo en Documentos o en una memoria USB. No la ponga en Archivos de programa: allí zCommander no podría guardar su configuración.
4. Dentro de la carpeta extraída hay otra llamada zCommander. Entre en ella y pulse Intro sobre ZCommander.exe.

Si Windows muestra el aviso de SmartScreen, elija «Más información» y después «Ejecutar de todas formas».

### Arrancar por primera vez

Al arrancar, zCommander dice «Iniciando zCommander». La primera vez se abre después el asistente de primer arranque (apartado siguiente). Al terminarlo, el foco está en la lista del panel izquierdo. El lector dice el nombre del panel y su carpeta, por ejemplo «Izquierdo: C:\Users\Ana», y después la fila del cursor.

Si los consejos están activos (perfil Novato), zCommander dice además: «Panel izquierdo. Tab cambia de panel, F1 abre la ayuda». Los consejos solo se oyen con el detalle de los anuncios en «Detallado», que es el del perfil Novato.

Si zCommander ya está abierto y lo vuelve a arrancar, no se abre otra ventana: se trae al frente la que ya estaba. Si no puede traerla, avisa «zCommander ya está en ejecución.».

La primera vez que arranca la versión 2.0, nueva o actualizada, zCommander avisa una sola vez de que los sonidos están activados y de que puede desactivarlos en Preferencias, página «Sonidos», o con Ctrl+F11 (capítulo «Sonidos»).

Si NVDA está en marcha y el complemento de zCommander para NVDA no está instalado, zCommander le ofrece instalarlo una sola vez, después del asistente (capítulo «El complemento de zCommander para NVDA»).

Si mantiene pulsada la tecla Mayús mientras arranca zCommander, arranca en modo seguro, sin ningún complemento (capítulo «Complementos»).

### El asistente de primer arranque

El diálogo se llama «Asistente de zCommander» y tiene cinco pasos. Se avanza con el botón «Siguiente», se vuelve con «Atrás» y se termina con «Terminar», que está disponible en todos los pasos. Al cambiar de paso se anuncia, por ejemplo, «Paso 2 de 5: Perfil».

1. «Bienvenida»: el texto «Qué es zCommander», una explicación breve de qué es un gestor de doble panel.
2. «Perfil»: la lista «Perfil» con Novato, Intermedio y Avanzado, y el texto «Descripción» del elegido. Se propone el perfil que coincide con sus preferencias actuales; la primera vez, Intermedio.
3. «Lector de pantalla»: la casilla «Uso un lector de pantalla (NVDA, JAWS o Narrador)». Si la deja marcada, se activan los anuncios y la salida automática por el lector; si la desmarca, los anuncios se desactivan.
4. «Colores»: la lista «Tema de colores», con «Sistema (colores de Windows)», «Norton clásico» y «Alto contraste».
5. «Terminar»: el texto «Resumen» con lo elegido y la casilla «Abrir el manual al terminar».

Nada se aplica hasta pulsar «Terminar». Entonces se anuncia, por ejemplo, «Listo. Perfil Intermedio aplicado.» y, si dejó marcada la casilla, se abre este manual. Si cancela el asistente la primera vez, no vuelve a salir al arrancar: se anuncia «Asistente cancelado. Puede abrirlo cuando quiera desde Opciones.». Puede volver a abrirlo cuando quiera desde el menú Opciones, «Asistente de primer arranque».

### Elegir perfil: Novato, Intermedio o Avanzado

Un perfil es un punto de partida: pone de una vez varias preferencias. Después puede cambiar cada una por separado. Para cambiar de perfil, abra el menú Opciones y elija «Perfil de usuario»; se le pedirá confirmación y se le dirá cuántas preferencias cambiarán.

Perfil Novato:

- La línea de órdenes está oculta y teclear letras en un panel hace búsqueda rápida.
- Pregunta antes de eliminar a la papelera, antes de salir y antes de ejecutar programas con Intro.
- Los anuncios son detallados, el progreso de las operaciones está en «Cada 25 %» y se dan consejos al llegar a sitios nuevos.
- Columnas por defecto: nombre, tipo, tamaño y fecha de modificación.
- Los menús muestran solo las órdenes básicas. Al final de cada menú, «Ver todas las órdenes en los menús» enseña el resto.

Perfil Intermedio (el de fábrica):

- La línea de órdenes está visible; teclear letras hace búsqueda rápida.
- Pregunta antes de eliminar a la papelera y antes de salir, pero no antes de ejecutar programas.
- Anuncios normales; el progreso se dice al empezar y al terminar; sin consejos.
- Columnas por defecto: nombre, extensión, tamaño y fecha de modificación.

Perfil Avanzado:

- Teclear letras en un panel del disco escribe en la línea de órdenes, como en Norton Commander. En un comprimido o un servidor, hace búsqueda rápida.
- No pregunta antes de eliminar a la papelera ni antes de salir.
- Muestra los archivos ocultos y de sistema.
- Anuncios breves; el progreso solo se dice al terminar.
- Columnas por defecto: nombre, extensión, tamaño, fecha de modificación y atributos.

Las columnas del perfil son las columnas por defecto, las de Opciones, «Columnas por defecto». Al aplicar un perfil o cambiar las columnas por defecto, las pestañas abiertas que tenían las columnas por defecto anteriores pasan a las nuevas al momento. Las pestañas a las que eligió otras columnas con «Columnas», en el menú Izquierdo o Derecho, las conservan.

En los tres perfiles los sonidos están activados.

Además de estos tres, puede guardar su configuración como un perfil propio con nombre y pasárselo a otra persona (capítulo «Copias de seguridad y perfiles»).

Los perfiles no cambian la confirmación de eliminar definitivamente (sin papelera): está activada de fábrica y solo se quita en Preferencias, página «General», «Confirmar al eliminar definitivamente».

El perfil activo no se guarda aparte: zCommander compara sus preferencias con cada perfil. Si ha cambiado alguna por su cuenta, el diálogo de perfil dice «Perfil actual: Personalizado».

### Actualizar y desinstalar

- zCommander busca versiones nuevas por su cuenta y le ofrece instalarlas; también puede buscarlas en el menú Ayuda, «Buscar actualizaciones». Lo explica el capítulo «Actualizar zCommander».
- También puede actualizar a mano: cierre zCommander y extraiga la versión nueva encima de la anterior. Su configuración se conserva porque está en la carpeta data\config, que el ZIP no trae.
- Tras actualizar, zCommander muestra una vez las novedades de la versión. También puede verlas en el menú Ayuda, «Novedades de la versión».
- Para desinstalar, cierre zCommander y borre su carpeta. Si activó «Arrancar zCommander al iniciar sesión en Windows», desactívela antes en Preferencias, página «General»: es lo único que zCommander escribe fuera de su carpeta por su cuenta. Las demás excepciones están en el capítulo «Dónde guarda sus datos».

## La ventana principal

### Las zonas de la ventana

De arriba abajo, la ventana tiene:

1. La barra de menús: Izquierdo, Archivos, Comandos, Complementos, Opciones, Mis órdenes (solo si le ha puesto algo), Derecho y Ayuda. F9 la abre, como en Norton Commander; Alt también.
2. La zona central, con los dos paneles o, si lo pide, con la salida de las órdenes.
3. La barra de botones, si la ha activado (capítulo «Personalización avanzada»). No está en el orden de tabulación: se llega a ella con Alt+Mayús+F11.
4. La línea de órdenes, si está visible.
5. La barra de teclas, con los botones F1 a F10. Es para el ratón y no está en el orden de tabulación.
6. La barra de estado, con dos partes: la primera dice «Listo» o lo que está pasando (por ejemplo «Leyendo...» o un error); la segunda, el espacio libre de la unidad o las operaciones en curso.

### Los dos paneles

Cada mitad de la ventana es un lado: el izquierdo y el derecho. Cada lado muestra un panel con una lista de archivos. El panel que tiene el foco es el panel activo; el otro es el panel pasivo. Copiar y mover llevan del activo al pasivo.

- Tab y Mayús+Tab pasan al otro panel. No recorren los demás controles de la ventana.
- Al llegar a un panel, el lector dice su nombre, que es el lado y la carpeta: «Derecho: D:\Música». Si hay marcas o un filtro, zCommander añade «3 marcados» o «filtro *.mp3».
- Si el otro lado está oculto, Tab no hace nada y se anuncia «El otro panel está oculto».
- Cada panel tiene debajo una línea de resumen, por ejemplo «12 carpetas y 40 archivos, 1,2 GB. Marcados: 3, 25 MB». Si hay un filtro, añade «Filtro: *.mp3» o «Filtro rápido: texto». Para oírla sin moverse, pulse Ctrl+Mayús+S.
- En una carpeta que no es la raíz, la primera fila es «..», que lleva a la carpeta superior. Se puede quitar en Preferencias, página «Paneles», «Mostrar la fila «..» para subir».
- Las carpetas van antes que los archivos. En la columna Tamaño de una carpeta se lee «Carpeta» o, si lo ha calculado, su tamaño.

Para ocultar o mostrar un lado, use Ctrl+F1 (izquierdo) o Ctrl+F2 (derecho); se anuncia «Lado izquierdo oculto» o «Lado izquierdo visible», y si oculta el lado que tiene el foco, el foco pasa al otro. Ctrl+P oculta o muestra el panel pasivo. Ctrl+U intercambia los dos paneles. Alt+Z lleva el otro panel a la misma carpeta que el activo.

### La línea de órdenes

Debajo de los paneles hay una etiqueta con la carpeta del panel activo y un campo para escribir órdenes de Windows. Se ve con el perfil Intermedio y el Avanzado.

- Para ir a ella, pulse Mayús+F2. Si estaba oculta, se muestra.
- Para volver al panel, pulse Tab, Mayús+Tab o, con la línea vacía, Escape. Si hay una orden en marcha, Escape con la línea vacía la detiene primero (se anuncia «Orden detenida»); otro Escape vuelve al panel.

El capítulo «Línea de órdenes, menú de usuario y asociaciones» explica cómo usarla.

### La salida de las órdenes

Lo que escriben las órdenes que ejecuta desde la línea de órdenes se guarda en un texto de solo lectura. Ctrl+O oculta los paneles y muestra ese texto, como en Norton Commander.

- Al mostrarla, el foco va al final de lo último escrito y se anuncia «Salida de las órdenes».
- Recorra el texto con las flechas, como cualquier texto.
- Tab va a la línea de órdenes, si está visible.
- Pulse otra vez Ctrl+O para volver a los paneles. El foco vuelve al panel y al elemento donde estaba.
- Mientras los paneles están ocultos, las órdenes que actúan sobre un panel avisan «Los paneles están ocultos: muestre los paneles primero».
- La salida guarda lo que escriben las órdenes de la línea de órdenes, del menú de usuario y de las asociaciones, hasta unos dos millones de caracteres; lo más antiguo se descarta.

### La barra de teclas y la barra de estado

La barra de teclas muestra qué hace cada tecla F. Su texto cambia al pulsar Mayús, Ctrl o Alt. Con el lector no hace falta: las mismas acciones están en los menús y en la lista de teclas.

La barra de estado se puede ocultar en Preferencias, página «Vista». Para oír su información sin buscarla, use las teclas de consulta (capítulo «Moverse y navegar», apartado «Teclas de consulta»).

### Pestañas

Cada lado puede tener varias pestañas. Cada pestaña es un panel con su carpeta, su orden y su filtro.

- Ctrl+T abre una pestaña nueva con la misma carpeta.
- Ctrl+W cierra la pestaña actual. La última no se cierra: se anuncia «Es la única pestaña de este lado».
- Ctrl+Tab y Ctrl+Mayús+Tab pasan a la pestaña siguiente y a la anterior del lado activo.
- Alt+1 a Alt+9 van a la pestaña con ese número. Si no existe, se anuncia, por ejemplo, «No hay pestaña 5».
- En el menú del lado (Izquierdo o Derecho), el submenú «Pestañas» reúne todas estas órdenes y además «Cerrar las demás pestañas», «Bloquear o desbloquear la pestaña» y «Lista de pestañas», que abre el diálogo «Pestañas» para elegir una.

Al cambiar de pestaña se anuncia, por ejemplo, «Pestaña 2 de 3, Documentos». El título de cada pestaña es el nombre de su carpeta.

Una pestaña bloqueada no cambia de carpeta: si entra en otra carpeta, sube con Retroceso o la fila «..», o va a otra carpeta con Ctrl+G o el selector de unidades, se abre una pestaña nueva en ese lado. Al bloquearla se anuncia «Pestaña bloqueada» y su título lleva un asterisco al final, por ejemplo «Documentos *».

### Vistas de cada lado

Cada lado puede mostrar una de estas vistas. Se eligen en el menú Izquierdo o Derecho, y actúan sobre ese lado.

- Vista completa: todas las columnas elegidas.
- Vista breve: solo los nombres.
- Información (Ctrl+L): el texto de solo lectura «Información», con los datos del elemento del cursor del otro panel (nombre, carpeta, tipo, tamaño, fechas, atributos, disponibilidad si solo está en la nube, permisos, destino si es un enlace y versión si es un programa o una biblioteca) y de su unidad (tipo, libre, total, sistema de archivos, etiqueta, número de serie y, en una unidad de red, a qué está conectada). Se actualiza poco después de mover el cursor en el otro panel.
- Árbol: el «Árbol de carpetas» de la unidad que tenía el otro panel al elegir la vista. Al moverse por él, tras una pausa, el otro panel va a la carpeta elegida. La pausa es la preferencia «Espera del árbol antes de cambiar el otro panel», en la página «Paneles» (400 milisegundos de fábrica), y se aplica al momento. No tiene tecla de fábrica; puede asignarle una en el mapa de teclas.
- Vista rápida (Ctrl+Q): el texto «Vista rápida», con el contenido del archivo del cursor del otro panel, como texto o en hexadecimal si es binario. Lee como mucho los primeros 256 kilobytes y lo dice al final, por ejemplo «(Se muestran los primeros 256 KB.)»; el límite se cambia en Preferencias, página «Vista». No lee solos los archivos que solo están en la nube, ni los de rutas de red, servidores o comprimidos guardados en la red: muestra «Pulse Intro para leer el archivo.».

Con el teclado, Ctrl+L y Ctrl+Q ponen la vista en el lado pasivo, como en Norton. Pulsar otra vez la misma tecla vuelve a la última vista de lista de ese lado (completa o breve).

Dentro de las vistas Información y Vista rápida valen las teclas de cualquier texto (flechas, Ctrl+A, Ctrl+C) y las teclas de toda la ventana. En el Árbol, las flechas, Num +, Num - y Num * abren y cierran ramas, las letras buscan una carpeta e Intro lleva el otro panel a la carpeta elegida. Tab o Mayús+Tab, desde cualquiera de las tres vistas, vuelven al otro panel.

Con el foco en una vista, el panel activo sigue siendo la lista del otro lado: F3, F5 o F8 actúan sobre sus elementos, y la carpeta de la vista es el destino de copiar y mover.

### Los menús

Pulse F9 o Alt para abrir la barra de menús, y las flechas para recorrerla. Cada menú tiene una letra de acceso, que el lector anuncia.

- Izquierdo y Derecho: vistas, ordenación, filtro, columnas, «Columnas y vista de esta carpeta», volver a leer, unidad, pestañas y mostrar u ocultar el lado. Actúan sobre su lado. Solo el menú del lado activo anuncia las teclas, para no oír la misma tecla dos veces.
- Archivos: abrir, ver, ver con el visor externo, editar y «Abrir con otro programa»; después copiar, «Renombrar o mover», «Copiar aquí con otro nombre», «Renombrar en el sitio», crear carpeta, crear archivo nuevo, eliminar, eliminar definitivamente y deshacer; «Atributos y fechas», propiedades y «Menú contextual de Windows»; los submenús Marcas y Portapapeles; el menú de usuario; y al final «Reiniciar zCommander» y salir. Salir es siempre lo último.
- Comandos: moverse (ir a la carpeta, árbol de carpetas, historial de carpetas, favoritos, añadir a favoritos e historial de órdenes); buscar y comparar (buscar archivos, comparar y sincronizar carpetas, comparar archivos por contenido y renombrado múltiple); los submenús Paneles, Herramientas (tamaño de carpetas, vista plana, sumas, dividir, unir y crear enlace), Cesta, Comprimidos y Red; y al final las operaciones en curso, la consola y el Explorador.
- Complementos: «Gestor de complementos», «Instalar un complemento desde un archivo» y «Reiniciar sin complementos»; debajo, un submenú por categoría (Multimedia, Documentos y datos, Orden y limpieza del disco, Sistema y seguridad, Automatización, y Nubes y NAS, más «Otros complementos» si instala alguno) y, dentro de cada una, un submenú por complemento con todas sus órdenes. Las órdenes de los complementos solo están aquí: los demás menús son los de zCommander.
- Opciones: preferencias y el submenú Perfiles; los submenús Personalización (esquema de teclas, mapa de teclas, menús y barras, barra de botones, «Ver todas las órdenes en los menús», columnas por defecto, orden de lectura, reglas, alias y plantillas), Macros y Sonidos; editar el menú de usuario, editar las asociaciones y mostrar los archivos ocultos; componentes externos y el submenú «Copia de seguridad»; asistente, guardar la sesión y valores de fábrica; y las carpetas de datos y de registros.
- Mis órdenes (Alt+R): el menú que llena usted con sus órdenes y macros favoritas. Solo aparece si tiene algo (capítulo «Personalización avanzada»).
- Ayuda: manual, lista de teclas, novedades, ayuda del control, paleta de órdenes, modo de ayuda de teclado, historial de anuncios, mapa de sonidos, buscar actualizaciones, instalar el complemento de zCommander para NVDA, información para soporte y acerca de zCommander.

Cada elemento del menú dice su tecla, si la tiene.

Con la preferencia «Menús según el nivel del perfil» (activada en el perfil Novato), los menús solo muestran las órdenes de su nivel. La casilla «Ver todas las órdenes en los menús», que entonces aparece al final de cada menú (y siempre en el menú Opciones), las muestra todas. Las teclas y la paleta de órdenes no cambian.

El menú contextual de zCommander se abre con Mayús+F10 o con Aplicaciones, con el foco en un panel. Tiene abrir, ver, editar, copiar, «Renombrar o mover», «Renombrar en el sitio», eliminar, copiar al portapapeles, cortar, pegar, copiar las rutas completas, comprimir, extraer, añadir a la cesta, propiedades y el menú contextual de Windows.

### Estados del panel

- Leyendo: si una carpeta tarda en leerse (más de 300 milisegundos), se anuncia «Leyendo» y la barra de estado dice «Leyendo» y la ruta. Escape cancela, se anuncia «Lectura cancelada» y el panel se queda en la carpeta en la que estaba.
- Error: si la carpeta no se puede leer, el panel se queda donde estaba y avisa del motivo, por ejemplo «No tiene permiso o el archivo está protegido.» seguido de la ruta.
- Carpeta borrada desde fuera: al volver a leerla, se anuncia «La carpeta ya no existe» y el panel sube a la primera carpeta superior que exista.
- Unidad que no responde: tras 10 segundos se da un error, sin que la ventana se congele.
- Servidor desconectado: si se pierde la conexión con un FTP o SFTP, se reintenta una vez sin avisar; si también falla, se anuncia «Se perdió la conexión con el servidor; se reintentó una vez sin éxito.» y el panel se queda donde estaba.
- El panel se actualiza solo cuando cambian los archivos de su carpeta, con la preferencia «Actualizar solo al cambiar los archivos» (página «Paneles»). Solo se vigilan los discos fijos que no son USB y las unidades de red, y solo la pestaña visible de cada lado; los cambios se recogen con un segundo de espera. Para volver a leer a mano, pulse Ctrl+R: conserva el cursor y las marcas y anuncia «Actualizado».

## Moverse y navegar

### Moverse por la lista

- Las flechas Arriba y Abajo, Inicio, Fin, Re Pág y Av Pág mueven el cursor por la lista.
- Izquierda y Derecha no mueven el cursor: leen la columna anterior o la siguiente de la fila (apartado «Leer las columnas»).
- Al moverse, el lector lee la fila del cursor.

### Entrar, salir y abrir

- Intro en una carpeta entra en ella. Al entrar se anuncia su nombre; si está vacía, por ejemplo «Fotos, carpeta vacía». Con el detalle «Detallado», se dice también cuántos elementos tiene.
- Intro en «..», Retroceso, Ctrl+Re Pág o Alt+Arriba suben a la carpeta superior. El cursor queda en la carpeta de la que salió.
- Ctrl+Av Pág entra en la carpeta o en el comprimido del cursor.
- Ctrl+Retroceso va a la raíz de la unidad.
- Ctrl+Mayús+Inicio va a su carpeta personal.
- En una lista (resultados enviados al panel, cesta o vista plana), Retroceso vuelve a la carpeta de la que partió. En la raíz de una unidad, Retroceso dice «Está en la raíz».
- Intro en un comprimido ZIP, TAR o 7z entra en él como en una carpeta (capítulo «Comprimidos»).
- Intro en un archivo lo abre con el programa que le haya asignado en las asociaciones o, si no hay, con el programa predeterminado de Windows.
- Intro en un programa del disco lo ejecuta en su carpeta. Si lo pide la preferencia «Confirmar antes de ejecutar programas con Intro», se pregunta antes. Los archivos .ps1, .vbs, .js, .wsf y .scr preguntan siempre. Si el programa tiene una asociación para abrir, se usa sin preguntar. Un programa que está dentro de un comprimido o en un servidor se confirma siempre, aunque la preferencia esté desactivada: se pregunta, por ejemplo, ««instalar.exe» está en D:\Descargas\juego.zip. Se extraerá a una carpeta temporal y se ejecutará. ¿Ejecutarlo?», e Intro responde «No».

Cada panel recuerda la última carpeta visitada de cada unidad: al volver a la unidad D, va a la carpeta en la que estaba.

### Búsqueda rápida

Teclear letras en un panel lleva el cursor al siguiente elemento cuyo nombre empieza así, sin distinguir mayúsculas ni acentos. Busca desde la fila del cursor hacia abajo y, al llegar al final, sigue desde el principio. Si no hay ninguno, suena un pitido y se anuncia «Sin coincidencias» con lo tecleado. Las letras se suman mientras no pase un segundo entre una y otra; ese tiempo se cambia en Preferencias, página «Paneles», «Duración de la búsqueda rápida (milisegundos)».

- Mientras la búsqueda está viva, Espacio añade un espacio a lo buscado y Retroceso borra la última letra.
- Pasado ese segundo, Espacio vuelve a marcar y Retroceso vuelve a subir de carpeta.
- Ctrl+S abre el diálogo «Búsqueda rápida», con un campo «Buscar», para escribir con calma. Intro o Escape lo cierran.
- Mayús+F2 con una búsqueda viva pasa lo tecleado a la línea de órdenes.

Con el perfil Avanzado, o con la preferencia «Al teclear en un panel, escribir en la línea de órdenes», las letras se escriben en la línea de órdenes, como en Norton Commander, si el panel está en el disco; en un comprimido o un servidor siguen haciendo búsqueda rápida. Si la línea tiene texto, Espacio y Retroceso también se escriben en ella.

### Ir a una carpeta

Pulse Ctrl+G. Se abre el diálogo «Ir a la carpeta» con el campo «Ruta». Puede escribir:

- Una ruta completa o relativa: D:\Fotos o ..\Otra.
- Una variable de entorno, como %USERPROFILE%, o ~ para su carpeta personal.
- Una ruta de red: \\servidor\recurso.
- Una dirección ftp:// o sftp://, que abre la conexión (capítulo «FTP, FTPS y SFTP»).
- red:// para la raíz «Red», y las direcciones de los complementos, como las de una cuenta de nube o de un NAS (synology://).
- La ruta de un archivo: el panel va a su carpeta con el cursor en él.

### Historial, atrás y adelante

- Alt+Izquierda vuelve a la carpeta anterior del panel; Alt+Derecha avanza a la siguiente.
- Alt+F12 o Alt+Abajo abren el diálogo «Historial de carpetas», con el campo «Buscar» y la lista «Carpetas visitadas» de ese panel. Abajo pasa del campo a la lista. Elija una y pulse Intro o el botón «Ir».
- Cada panel recuerda hasta 100 carpetas. Se cambia en Preferencias, página «General», «Tamaño del historial de carpetas» (de 10 a 1000).

### Favoritos

- Ctrl+D abre la lista «Favoritos», con su nombre y su ruta. Intro o el botón «Ir» van al elegido.
- Los botones «Añadir la carpeta actual», «Renombrar», «Subir», «Bajar» y «Eliminar» mantienen la lista.
- Ctrl+Mayús+D añade la carpeta actual a favoritos y le pide un nombre. Si la carpeta ya es favorita, le cambia el nombre y anuncia «Favorito renombrado».

### Árbol de carpetas

Alt+F10 abre el diálogo con el «Árbol de carpetas» de la unidad actual. Las ramas se cargan al abrirlas y puede buscar tecleando el nombre. Los botones son «Ir», «Crear carpeta», «Renombrar» y «Eliminar»; el panel solo cambia de carpeta con «Ir» o Intro. Donde no se puede escribir, los tres últimos están desactivados.

### Elegir unidad

Alt+F1 abre el diálogo «Unidad del lado izquierdo» y Alt+F2, «Unidad del lado derecho». En el menú de cada lado está también «Unidad». La lista «Unidades y carpetas» tiene una fila por unidad, por ejemplo «C:, Disco local, Sistema, NTFS, 120 GB libres de 476 GB» (letra, tipo, etiqueta, sistema de archivos y espacio). Aparecen las unidades de red, las extraíbles y las ópticas; una unidad vacía o que no contesta dice «sin disco o sin respuesta». Debajo están los favoritos, que se leen «Favorito: nombre, ruta», y las carpetas especiales (Carpeta personal, Escritorio, Documentos, Descargas, Imágenes, Música y Vídeos), con su ruta. Al final están «Red» (capítulo «Red y unidades de red») y las unidades que añaden los complementos, como cada cuenta de nube, File Station de cada NAS o la papelera de reciclaje. Teclear la letra de una unidad va a ella; Intro o el botón «Ir» llevan el lado a la fila elegida.

### Abrir una carpeta en el otro lado

Ctrl+Izquierda abre en el lado izquierdo la carpeta del cursor (o la actual, si el cursor está en un archivo). Ctrl+Derecha hace lo mismo en el lado derecho.

### Ordenar la lista

- Ctrl+F3 ordena por nombre, Ctrl+F4 por extensión, Ctrl+F5 por fecha de modificación y Ctrl+F6 por tamaño. Pulsar otra vez la misma tecla invierte el orden.
- Ctrl+F7 muestra los elementos en el orden del disco.
- En el menú del lado están además «Ordenar por tipo», «Orden inverso» y «Agrupar las carpetas al principio». Esta última es una preferencia de toda la ventana: cambia los dos lados.

### Archivos ocultos

Ctrl+punto muestra u oculta los archivos ocultos y de sistema. También está en el menú Opciones y en Preferencias, página «Paneles».

### Leer las columnas

Para oír una sola columna de la fila del cursor sin moverse:

- Derecha lee la columna siguiente e Izquierda, la anterior.
- Ctrl+1 a Ctrl+9 leen las columnas 1 a 9, y Ctrl+0 la columna 10.

Lo que se dice se elige en Preferencias, página «Accesibilidad»: el número de fila, el nombre de la columna y su contenido.

### Teclas de consulta

Estas teclas dicen información sin mover el foco. Lo que dicen queda en el historial de anuncios.

- Ctrl+Mayús+P: la ruta del panel activo.
- Ctrl+Mayús+O: la ruta del otro panel.
- Ctrl+Mayús+S: el resumen de la carpeta (carpetas, archivos, tamaño, marcas y filtro).
- Alt+Mayús+M: los elementos marcados del panel activo: cuántos son, su tamaño y sus nombres (capítulo «Marcar y elementos de trabajo»).
- Ctrl+Mayús+I: la información del elemento del cursor (tipo, tamaño, fechas y atributos).
- Ctrl+Mayús+E: el espacio libre y total de la unidad.
- Ctrl+Mayús+T: el estado de las operaciones (porcentaje, velocidad, tiempo restante y decisiones pendientes).
- Ctrl+Mayús+U: repite el último anuncio. Pulsado dos veces seguidas, dice su versión completa.
- Ctrl+Mayús+H: abre el historial de anuncios de la sesión, con su hora. Se puede copiar.

## Marcar y elementos de trabajo

### Qué son las marcas

Marcar es señalar varios elementos para operar con todos a la vez. zCommander sigue el modelo de Norton Commander: el cursor es el elemento en el que está, y las marcas son aparte.

Los elementos de trabajo de una orden son los marcados. Si no hay ninguno marcado, es el elemento del cursor. La fila «..» nunca es un elemento de trabajo. Si no queda ninguno, zCommander lo dice, por ejemplo «No hay elementos para copiar», y no hace nada.

### Qué dice el lector al marcar

Hay dos formas de mostrar las marcas. Se elige en Preferencias, página «Accesibilidad», en «Cómo se muestran las marcas». Se aplica al momento al pulsar «Aplicar» o «Aceptar», sin reiniciar, y las marcas que ya tenga se conservan. Mientras no la cambie, zCommander funciona como siempre, con la primera.

«Como selección de la lista (el lector dice "seleccionado")» es la forma de siempre y la de fábrica. Las marcas son la selección de Windows, así que el lector las anuncia como «seleccionado» o «no seleccionado».

- Sin marcas, la lista funciona como cualquier lista de Windows: la fila del cursor aparece seleccionada y el lector no dice «no seleccionado» al moverse.
- En cuanto marca el primer elemento, la lista pasa a selección múltiple. Al moverse con las flechas, el lector dice en cada fila si está seleccionada (marcada) o no. Moverse ya no cambia las marcas.
- Al quitar la última marca, la lista vuelve a ser una lista normal.

«En la columna Marca (el lector solo lo dice una vez)» muestra las marcas en una columna propia, «Marca», que dice «Marcado» en las filas marcadas y está vacía en las demás.

- La lista no usa la selección para las marcas: siempre es una lista normal, con solo la fila del cursor seleccionada. Así ningún lector (NVDA, JAWS, Narrador u otro) dice «seleccionado» ni «no seleccionado» por las marcas, y nada se dice dos veces. No hace falta el complemento de NVDA.
- Al moverse por las filas, los lectores se saltan las celdas vacías, así que una fila sin marcar no dice «Marcado». La columna sigue ahí: si la lee con Ctrl y su número, dice «Sin datos», y NVDA+Mayús+J del complemento de NVDA dice «Marca: vacío».
- La columna Marca se coloca donde quiera, como las demás: en el menú del lado, «Columnas» (con «Subir» y «Bajar»), y en «Orden de lectura de las columnas» (capítulo «Personalización avanzada»). Si la pone la primera, se oye «Marcado» antes del nombre; si la pone la última, al final de la fila.
- Con NVDA leyendo las cabeceras de tabla (opción «Cabeceras de tabla» de Formato de documento) y la Marca la primera, NVDA dice «Nombre:» delante de cada fila sin marcar: no dice la cabecera de la primera columna, pero sí la de la siguiente cuando la primera está vacía. El complemento de zCommander para NVDA lo evita. Sin él, ponga la Marca detrás del Nombre (con «Columnas» o con «Orden de lectura de las columnas») o desactive en NVDA la lectura de cabeceras de tabla.
- Al elegir esta forma, la columna Marca se añade la primera en las pestañas que no la tienen (y la primera del orden de lectura, si eligió uno). Al volver a «Como selección de la lista», se quita de las pestañas en las que la añadió zCommander; si la había puesto usted, se queda.
- Mientras esta forma esté elegida, la columna Marca se ve siempre: también en la vista breve, en las vistas por carpeta, en las columnas propias de «Red» o de un complemento y en las pestañas que restaura un espacio de trabajo, aunque no la tengan (sin cambiarlos). En «Columnas» no se puede quitar: se vuelve a marcar y se dice por qué; sí puede moverla.
- Para quien ve la pantalla, las filas marcadas se muestran en negrita (y con el color de lo marcado del tema Norton clásico).
- Todo lo demás funciona igual: las teclas de marcar, marcar por patrón, invertir, el resumen, la vista plana, la cesta y las órdenes que actúan sobre los marcados.

Para saber qué hay marcado, pulse Alt+Mayús+M: dice cuántos hay, cuánto ocupan y sus nombres, por ejemplo «3 marcados, 25 MB: informe.pdf, notas.txt, fotos». Las carpetas cuyo tamaño no se ha calculado no tienen tamaño: si hay alguna, dice cuántas carpetas son y solo el tamaño de los archivos, por ejemplo «3 marcados (1 carpeta), 25 MB en archivos: informe.pdf, notas.txt, fotos», o, si todo son carpetas, «2 marcados (2 carpetas): fotos, música». El recuento al marcar en grupo y el resumen del panel lo dicen igual. Dice hasta 20 nombres y, si hay más, «y 5 más». Sin marcas dice «No hay nada marcado; el elemento de trabajo es» y el nombre del cursor. También está en el menú Archivos, submenú Marcas, «Decir los elementos marcados». Ctrl+Mayús+S dice el resumen de la carpeta, con cuántos hay marcados. Al volver a un panel con marcas, zCommander dice cuántas hay.

### Marcar uno a uno

- Espacio o Insert marcan o desmarcan el elemento del cursor y bajan al siguiente. Se anuncia «Marcado: nombre» o «Desmarcado: nombre» (salvo con el detalle «Breve»), y después el lector lee la fila siguiente.
- Ctrl+Espacio marca o desmarca sin moverse, como en el Explorador.
- Para no bajar al marcar, desactive en Preferencias, página «Paneles», la casilla «Bajar al siguiente al marcar con Insert o Espacio». Entonces el cursor se queda en el elemento y se anuncia «Marcado: nombre» o «Desmarcado: nombre».

Insert es la tecla modificadora de NVDA, JAWS y Narrador. Si su lector no deja pasar Insert, use Espacio. Con NVDA, pulsar Insert dos veces seguidas la deja pasar a zCommander.

### Marcar un rango

Estas teclas marcan desde el cursor hasta la posición nueva, sin quitar las marcas que ya había:

- Mayús+Arriba y Mayús+Abajo: el elemento del cursor, y suben o bajan.
- Mayús+Re Pág y Mayús+Av Pág: una página hacia arriba o hacia abajo.
- Mayús+Inicio y Mayús+Fin: hasta el primero o hasta el último.

### Marcar y desmarcar por patrón

Como las teclas grises de Norton Commander:

- Num + o Ctrl+Mayús+M: marca por patrón. Se abre un campo para escribir el patrón, por ejemplo *.txt.
- Num - o Ctrl+Mayús+Q: desmarca por patrón.
- Num * o Ctrl+Mayús+N: invierte las marcas de los archivos; las carpetas quedan sin marcar.
- Mayús+Num +: marca todos los archivos con la extensión del cursor.
- Mayús+Num -: los desmarca.

NVDA y JAWS usan el teclado numérico en su distribución de escritorio. Si su lector se queda con Num +, Num - o Num *, use Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N.

Al marcar en grupo se anuncia el recuento, por ejemplo «Marcados 12, 340 MB».

### Cómo se escriben los patrones

- El asterisco (*) vale por cualquier grupo de caracteres y la interrogación (?) por uno solo.
- Se pueden poner varios separados por punto y coma, coma o espacio: *.mp3;*.flac.
- Lo que va tras una barra vertical (|) se excluye: *.* | *.bak marca todo menos las copias .bak.
- *.* coincide también con los nombres sin extensión.
- No se distinguen mayúsculas de minúsculas.
- Por defecto, marcar por patrón y el filtro (Ctrl+F12) solo se aplican a archivos. Para incluir carpetas, active en Preferencias, página «Paneles», la casilla «Marcar por patrón incluye las carpetas». Desmarcar por patrón quita también las marcas de las carpetas que coinciden.
- Los diálogos recuerdan los últimos patrones que usó.

### Otras formas de marcar

- Ctrl+A marca todo lo visible y Ctrl+Mayús+A desmarca todo.
- Ctrl+Mayús+R restaura las marcas que había al lanzar la última operación (copiar, mover, eliminar...). Así puede repetir una orden sobre los mismos archivos después de copiarlos. Si entonces no había marcas, marca el elemento que estaba en el cursor.
- En el menú Archivos, submenú Marcas, están «Guardar las marcas en un archivo» y «Cargar las marcas desde un archivo».
- Sin teclado numérico, puede marcar por patrón con el filtro rápido: pulse Ctrl+F, escriba el texto, vuelva a la lista con Abajo y pulse Ctrl+A. Al quitar el filtro con Escape, las marcas de lo que se veía se conservan, y lo que ya estaba marcado antes de filtrar vuelve a verse marcado.

### Cuándo se pierden las marcas

- Las marcas se pierden al salir de la carpeta, como en Norton. Ctrl+Mayús+R no las recupera: solo devuelve las de la última operación.
- Al volver a leer la carpeta (Ctrl+R o un cambio desde fuera), el cursor y las marcas se conservan. Las de archivos que ya no existen se quitan.
- Cuando un elemento marcado deja de verse (por el filtro rápido, un filtro o al ocultar los archivos ocultos), su marca se aparta: no cuenta en «marcados» ni entra en las órdenes mientras no se ve, y vuelve a estar marcado cuando se ve de nuevo. Esto dura mientras no salga de la carpeta; «Desmarcar todo» también quita estas marcas.
- Cuando termina cualquier operación (copiar, mover, eliminar, comprimir...), aunque sea con errores, se quitan todas las marcas de los dos paneles. Si se cancela o falla, se conservan.

### Alcance de las órdenes

- Las órdenes que abren un diálogo (copiar, mover, eliminar) dicen en él sobre qué actúan.
- Las que actúan sin diálogo anuncian su alcance: eliminar sin confirmación dice «3 marcados a la papelera» o «canción.mp3 a la papelera», y añadir a la cesta, «3 añadidos; la cesta tiene 12».
- Si hay marcas y el cursor está en otro elemento, zCommander pregunta antes de copiar o mover: «Hay 3 marcados y el cursor está en otro elemento. ¿Copiar los 3 marcados?» (o «¿Mover...?»), con los botones «Sí» y «No» y la casilla «No volver a preguntar». Si la marca y responde «Sí», ya no se pregunta y se actúa sobre los marcados; se recupera en Preferencias, página «Confirmaciones». Al eliminar, en ese caso se pide la confirmación normal, aunque esté desactivada, mientras no haya silenciado esta pregunta.

## Ver archivos con F3

F3 abre el archivo del cursor en el visor de zCommander. Si en las asociaciones hay un programa para «Ver» ese tipo de archivo, se usa ese programa. F3 sobre una carpeta calcula su tamaño. Alt+F3 abre siempre el visor externo de Preferencias; si no hay ninguno, avisa «No hay visor externo configurado. Puede elegirlo en Preferencias, página Visor y editor.».

### El visor interno

El visor es una ventana propia, titulada con el nombre del archivo y «Visor», y se pueden abrir varias. Muestra el archivo en el texto de solo lectura «Contenido de» seguido del nombre, que el lector recorre por líneas, palabras y caracteres. Un archivo binario se abre directamente en hexadecimal y se anuncia «Archivo binario: se muestra en hexadecimal».

La barra de estado del visor tiene cuatro partes: «Línea 12, columna 5» (en hexadecimal, «Desplazamiento» con el número en decimal y en hexadecimal); la codificación, con «(detectada)» si la eligió zCommander; «Texto» o «Hexadecimal»; y el tamaño del archivo, con el bloque si se ve por bloques.

### Teclas y menús del visor

Estas teclas solo valen dentro de la ventana del visor. Todas están también en sus menús: Archivo, Edición, Ver y Ayuda.

- F2: activa o desactiva el ajuste de línea. Se anuncia «Ajuste de línea activado» o «desactivado».
- F4: alterna entre texto y hexadecimal.
- F8: abre el diálogo «Codificación», con la lista «Codificación»: «Automática (detectar)», «UTF-8», «UTF-16 (little endian)», «UTF-16 (big endian)», «Windows-1252 (ANSI)», «ISO-8859-1 (Latin-1)», «OEM 850 (MS-DOS Europa)» y «OEM 437 (MS-DOS EE. UU.)». La codificación inicial se elige en Preferencias, página «Visor y editor»; de fábrica, automática.
- F7 o Ctrl+F: buscar. El diálogo tiene el campo «Buscar» y las casillas «Distinguir mayúsculas y minúsculas», «Solo la palabra completa», «Expresión regular» y «Buscar hacia atrás». Si no lo encuentra, dice «No se encontró» y el texto; si vuelve a empezar, «Búsqueda desde el principio».
- F3: buscar el siguiente. Mayús+F3: buscar el anterior.
- Ctrl+G: ir a una línea (diálogo «Ir a la línea»); en hexadecimal, a un desplazamiento, que puede escribir en hexadecimal empezando por 0x.
- Ctrl+C copia y Ctrl+A selecciona todo.
- Ctrl+Mayús+I: dice la barra de estado del visor.
- Ctrl+H: ayuda del control enfocado.
- Escape o F10: cierra el visor.

El tamaño de la letra se cambia en el menú Ver del visor, con «Aumentar la letra» y «Reducir la letra»; se anuncia, por ejemplo, «Letra de 12 puntos», y se guarda para la próxima vez. En el menú Ayuda del visor, «Teclas del visor» muestra estas teclas.

### Documentos por secciones

Algunos complementos enseñan al visor a leer otros archivos: el lector de documentos abre PDF, DOCX, ODT, EPUB, RTF, HTML y FB2; y el reconocimiento de texto (OCR) muestra en él el texto reconocido. Estos documentos se dividen en secciones (páginas, capítulos o partes):

- F6 pasa a la sección siguiente y Mayús+F6 a la anterior.
- Ctrl+L abre la lista de secciones, con un campo para buscar por su título.
- Ctrl+P va a una página por su número.
- La barra de estado dice dónde está, por ejemplo «Sección 3 de 12: Introducción».

Con estos documentos, la Vista rápida (Ctrl+Q) muestra también su texto.

### Archivos grandes y archivos de otros sitios

- Hasta 16 MB, el archivo se carga entero. Mientras se carga, el texto y la barra de estado dicen «Cargando...». El límite se cambia en Preferencias, página «Visor y editor», «Cargar enteros los archivos de hasta (MB)».
- Si es mayor, se ve por bloques de 1 MB. En hexadecimal se ve siempre por bloques de 1 MB, sea cual sea el tamaño. Ctrl+Av Pág y Ctrl+Re Pág pasan al bloque siguiente o al anterior y se anuncia, por ejemplo, «Bloque 3 de 120»; la barra de estado dice el tamaño y «bloque 3 de 120». En el último bloque se anuncia «Es el último bloque», y si el archivo se ve entero, «El archivo se ve entero: no hay más bloques». La búsqueda recorre todos los bloques.
- Un archivo de un comprimido o de un servidor se copia antes a una carpeta temporal, que se borra al cerrar el visor.
- Si el archivo solo está en la nube (OneDrive), se le pregunta antes de descargarlo: ««nombre» solo está en la nube. ¿Descargarlo para verlo?».

## Editar archivos con F4

F4 abre el archivo del cursor para editarlo. Se usa, por este orden: el programa de las asociaciones para «Editar»; el editor externo, si activó «Usar un editor externo con F4» en Preferencias, página «Visor y editor»; y si no, el editor interno. Si activó el editor externo pero no escribió ninguno, se anuncia «No hay editor externo configurado: se usa el interno».

### El editor interno

Es una ventana propia, titulada con el nombre del archivo y «Editor» (y «(modificado)» si hay cambios sin guardar), con el texto editable sin formato «Texto de» seguido del nombre. Conserva la codificación, el tipo de fin de línea y la marca de codificación (BOM) del archivo; al guardar como, puede cambiarlos.

- No abre archivos de más de 64 MB: le dice que use el visor (F3).
- Si el archivo no parece de texto, pregunta antes: ««nombre» no parece un archivo de texto: editarlo y guardarlo puede dañarlo. ¿Abrirlo igualmente?». El botón predeterminado es «No».
- La barra de estado dice la línea y la columna, la codificación (con «con BOM» si la lleva), el fin de línea y «Modificado» o «Sin cambios».

### Teclas y menús del editor

Todas las órdenes están en sus menús: Archivo, Edición, Herramientas y Ayuda.

- F2 o Ctrl+S: guardar; se anuncia «Guardado» y el nombre. Mayús+F2: guardar como.
- Escape o F10: cerrar. Si hay cambios, se pregunta ««nombre» tiene cambios sin guardar.», con los botones «Guardar», «No guardar» y «Cancelar». La misma pregunta sale al cerrar zCommander con el editor abierto.
- Ctrl+Z: deshacer. Ctrl+Y: rehacer.
- Ctrl+X, Ctrl+C y Ctrl+V: cortar, copiar y pegar. Ctrl+A: seleccionar todo.
- F7 o Ctrl+F: buscar. F3: buscar el siguiente. Mayús+F3: buscar el anterior.
- Ctrl+R: reemplazar. El diálogo «Reemplazar» no bloquea el editor y tiene los campos «Buscar» y «Reemplazar por», tres casillas como las de buscar y los botones «Buscar siguiente», «Reemplazar», «Reemplazar todo» y «Cerrar».
- Ctrl+G: ir a una línea.
- F5: insertar la fecha y la hora, como 08/11/2026 14:05.
- Ctrl+Mayús+I: dice la barra de estado del editor.
- Ctrl+H: ayuda del control enfocado.
- En el menú Archivo está además «Volver a cargar», que pregunta si hay cambios sin guardar. En el menú Herramientas, «Contar líneas, palabras y caracteres», «Aumentar la letra» y «Reducir la letra». En el menú Ayuda, «Teclas del editor».

### Guardar como

El diálogo tiene el campo «Ruta del archivo» con el botón «Examinar», la lista «Codificación», la lista «Fin de línea» («CRLF (Windows)», «LF (Unix, Linux y macOS)» o «CR (Mac antiguo)») y la casilla «Escribir la marca BOM al principio». Si el archivo de destino ya existe, pregunta si sustituirlo.

Si el texto tiene un carácter que no cabe en la codificación del archivo, al guardar se le pregunta, con los botones «Guardar en UTF-8» y «Cancelar».

### Guardado seguro

El editor escribe primero un archivo temporal en la misma carpeta y lo cambia por el original al terminar. Si el archivo cambió en el disco mientras lo editaba, pregunta ««nombre» ha cambiado en el disco desde que lo abrió. ¿Sobrescribirlo con su versión?», con «No» como botón predeterminado. Con «Guardar una copia .bak al editar» activa, antes de sustituirlo copia la versión anterior añadiendo .bak al nombre completo: notas.txt pasa a notas.txt.bak.

Un archivo de un comprimido se puede editar, pero no guardar dentro: al abrirlo se anuncia «El archivo está en un comprimido: al guardar se pedirá una carpeta del disco», y al guardar se abre «Guardar como». Un archivo de un servidor se lee directamente y, al guardar, se pregunta «¿Subir los cambios de «nombre» a» seguido de la carpeta del servidor.

Si abrió un archivo de un comprimido o de un servidor con un programa externo, al volver a zCommander, si cambió, se le pregunta ««nombre» ha cambiado. ¿Actualizarlo en» seguido de su carpeta.

## Copiar y mover con F5 y F6

F5 copia los elementos de trabajo a la carpeta del otro panel. F6 los mueve o, si cambia el nombre en el destino, los renombra.

### El diálogo de copiar o mover

El diálogo siempre aparece, como en Norton. El foco empieza en el campo «Destino».

- «Resumen»: texto de solo lectura, por ejemplo «Copiar 1 carpeta y 3 archivos (45 MB) a:». El tamaño es el de los archivos elegidos, sin contar lo que hay dentro de las carpetas.
- «Destino»: la carpeta del otro panel. Si copia un solo elemento, la ruta acaba en su nombre, para que pueda copiarlo con otro nombre. Si el destino termina en barra invertida o es una carpeta que existe, los elementos van dentro. Si no existe y copia varios, se crea la carpeta.
- «Solo los que coinciden con»: un patrón; por defecto, *.
- «Si el archivo ya existe»: Preguntar, Sobrescribir, Omitir, Sobrescribir si es más antiguo, Sobrescribir si cambia el tamaño, Renombrar la copia automáticamente o Renombrar el existente automáticamente. El valor inicial es el de Preferencias, página «Operaciones»; de fábrica, Preguntar.
- Casillas: «Conservar fechas y atributos», «Verificar después de copiar», «Copiar los enlaces como enlaces» y «Copiar también las carpetas vacías». Sus valores iniciales salen de Preferencias, página «Operaciones»: de fábrica, todas activadas salvo «Verificar después de copiar». Si desactiva «Copiar también las carpetas vacías», no se crean en el destino las carpetas que quedarían sin ningún archivo.
- Botones: «Copiar» o «Mover», «En cola» y «Cancelar».

Intro pulsa «Copiar» o «Mover» y la operación empieza al momento. «En cola», o F2 en el diálogo, la deja esperando a que terminen las demás operaciones puestas en cola.

### Qué pasa durante la copia

1. Al lanzarla, con el progreso por voz «Al empezar y al terminar» (el de fábrica), se anuncia «Empieza:» y la operación, por ejemplo «Empieza: Copiar 3 elementos a D:\Copias».
2. Primero se analiza lo que se va a copiar: se cuentan los archivos y los bytes y se buscan los que ya existen. En la ventana de operaciones su estado es «Analizando».
3. Después del análisis se comprueba el espacio libre (salvo al mover dentro de la misma unidad). Si no cabe, se pregunta «Hacen falta» tantos bytes «y hay» tantos «libres en el destino.», con los botones «Continuar de todos modos» y «Cancelar»; el predeterminado es «Cancelar».
4. Si hay archivos que ya existen y eligió «Preguntar», se abre la lista de conflictos (apartado siguiente).
5. Después se copia. Cada archivo se escribe con un nombre temporal y se le pone su nombre al terminar: nunca queda un archivo a medias con el nombre bueno.
6. Al terminar, los paneles afectados se actualizan y se anuncia un resumen: la operación, su estado y las cifras, por ejemplo «Copiar 3 elementos a D:\Copias: terminada, 400 archivos, 2,1 GB, 2 omitidos, 1 error, 1 min 20 s».

Mover dentro de la misma unidad del disco, sin patrón y a un nombre que no existe, es instantáneo: solo se cambia de sitio. En los demás casos se copia y cada original se borra solo después de copiarlo (y verificarlo, si lo pidió); si algo falla, el original se conserva.

Copiar una carpeta dentro de sí misma, o un archivo sobre sí mismo, se rechaza al analizar: la operación termina como fallida, por ejemplo «Copiar notas a D:\Notas: fallida, 1 error», y el motivo («El origen y el destino son el mismo» o «No se puede copiar una carpeta dentro de sí misma») está en la ventana de operaciones (F12), botón «Detalles». Los enlaces simbólicos y las uniones nunca se recorren: se copian como enlace o se omiten, según la casilla.

### La lista de conflictos

Si algunos archivos ya existen en el destino, antes de copiar nada se abre una lista con todos ellos. El título del diálogo es la operación, y la lista se llama «Conflictos». Cada fila tiene Nombre (con la ruta relativa), Origen (tamaño y fecha), Acción y Destino (tamaño y fecha). La acción inicial de cada fila es Omitir: si pulsa Intro sin cambiar nada, no se pierde ningún archivo.

Para cambiar la acción, sitúese en una fila (o seleccione varias con Ctrl+Espacio, Mayús+Arriba y Mayús+Abajo) y pulse una letra, sin Alt:

- S: sobrescribir.
- O: omitir.
- C: renombrar la copia.
- E: renombrar el existente.

Cada cambio se anuncia: con una fila, la acción y el nombre; con varias, por ejemplo «Sobrescribir: 12 filas». También puede usar el menú contextual de la lista.

Además, el diálogo tiene:

- El desplegable «Mostrar»: «Todos» o «Solo los de destino más reciente».
- El texto «Descripción», con los datos de la fila del cursor.
- Botones: «Comparar» (compara los dos archivos de la fila), «Aplicar a todos» (pone la acción de la fila del cursor en todas las filas que se ven con el «Mostrar» elegido), «Sobrescribir los más antiguos» (resuelve todo de una vez), «Continuar» y «Cancelar la operación».

El renombrado automático añade « (2)», « (3)» y así sucesivamente antes de la extensión. Una carpeta que ya existe se une con la nueva sin preguntar; los archivos de dentro siguen la lista. Si un archivo del disco de destino es de solo lectura y elige sobrescribirlo, se le quita ese atributo antes.

### La pregunta de uno en uno

Si desactiva «Mostrar la lista de conflictos antes de copiar» en Preferencias, página «Operaciones», se pregunta por cada archivo. El título es la operación, y el texto «Conflicto» dice, por ejemplo: «Ya existe «nota.txt». Origen: 2 KB, 08/11/2026 10:15. Destino: 1 KB, 01/10/2026 9:00. El origen es más reciente.». Los botones son «Sobrescribir», «Sobrescribir todos», «Omitir», «Omitir todos», «Sobrescribir los más antiguos», «Renombrar...», «Renombrar todos automáticamente», «Comparar» y «Cancelar la operación». El foco empieza en «Omitir» y Escape equivale a Omitir.

### Conflictos tardíos y errores

- Si un archivo del destino aparece o cambia después del análisis, es un conflicto tardío. No para la copia: se aparta, y al final se abre la lista de conflictos solo con esos archivos.
- Un error en un archivo (en uso, sin permiso) tampoco para la copia: se anota y se sigue con los demás. Al final, la ventana de operaciones ofrece «Reintentar los que fallaron».
- Un error que afecta a todo (disco lleno, unidad desconectada) detiene la operación con una pregunta titulada «Error:» y la operación, que dice el motivo, el elemento y la operación, con los botones «Reintentar», «Omitir», «Omitir todos» y «Cancelar». «Omitir todos» omite también, sin volver a preguntar, los siguientes errores del mismo tipo en esa operación.

## Operaciones en segundo plano con F12

Las copias, los movimientos y las demás operaciones largas van en segundo plano: puede seguir trabajando mientras tanto.

### La ventana de operaciones

F12 abre la ventana de operaciones en curso. No es modal: puede volver a la ventana principal o cerrarla, y las operaciones siguen.

- La lista «Operaciones» tiene una fila por operación, con las columnas Operación, Estado y Progreso (por ejemplo «45 %»). Los estados son: En cola, Analizando, Espera su decisión, En marcha, Verificando, En pausa, Terminada, Terminada con errores, Cancelada o Fallida.
- El texto «Información de la operación» muestra, para la elegida, la operación (qué se copia y adónde) y las líneas «Estado», «Archivo actual» (con su porcentaje), «Total», «Bytes», «Archivos», «Velocidad», «Tiempo restante», «Tiempo transcurrido», «Omitidos» y «Errores». Nunca le quita el foco.
- Botones: «Atender la decisión pendiente», «Pausar» (que pasa a llamarse «Reanudar»), «Cancelar la operación», «Detalles» (los errores, que se pueden copiar), «Reintentar los que fallaron» (solo en copias y movimientos), «Limpiar las terminadas» y «Cerrar».
- Escape o «Cerrar» ocultan la ventana. F12 la vuelve a mostrar tal como estaba.

### Cuándo empieza cada operación

- Lo que lanza con el botón principal empieza enseguida, salvo que otra operación esté usando el mismo disco de origen o de destino. Así dos copias al mismo disco no se estorban, y dos copias entre discos distintos van a la vez.
- Lo que pone «En cola» espera en una sola cola y se hace de una en una.
- Como mucho van 3 operaciones a la vez. Puede cambiarlo en Preferencias, página «Operaciones», «Operaciones a la vez»; se aplica al reiniciar.

### Progreso por voz

- La preferencia «Progreso de las operaciones por voz» (página «Accesibilidad») tiene tres valores. «Al empezar y al terminar» (perfil Intermedio) anuncia «Empieza:» y la operación al lanzarla, y el resumen al terminar. «Solo al terminar» (perfil Avanzado) dice solo el resumen. «Cada 25 %» (perfil Novato) dice además el avance de cada operación al pasar por el 25, el 50 y el 75 %, por ejemplo «Copiar notas a D:\Notas: 50 %», una sola vez cada uno.
- Ctrl+Mayús+T dice el estado en cualquier momento, desde cualquier sitio de la ventana principal. Si hay decisiones pendientes, añade cuáles esperan y que F12 las atiende.
- El resumen final, los errores y las preguntas se anuncian siempre.
- Con los sonidos activados, una operación suena al empezar, al terminar (con otro sonido si hay errores o falla) y cuando espera su decisión. La opción «Progreso de las operaciones» de Preferencias, página «Sonidos», añade un sonido cada 25 % o cada 10 %, más agudo cuanto más avanza. Los sonidos no interrumpen al lector (capítulo «Sonidos»).

### Decisiones pendientes

Si una operación necesita que decida algo (archivos que ya existen, un error, una contraseña):

- Si la lanzó hace menos de 3 segundos, es la última que lanzó y está en la ventana principal sin otro diálogo abierto, la pregunta aparece enseguida.
- Si no, no le interrumpe: se anuncia la operación seguida de «espera su decisión», por ejemplo «Copiar 3 elementos a D:\Copias: espera su decisión», y se le recuerda cada minuto. Con varias, se dice «3 decisiones pendientes. La primera:» y la operación.
- Para atenderla, pulse F12 y el botón «Atender la decisión pendiente», que abre la primera que espera. También se abre sola cuando vuelve a la ventana principal desde otra ventana, si no hay ningún diálogo abierto.
- Durante sus primeros 300 milisegundos, los diálogos de decisión no atienden teclas, para que una tecla que iba dirigida al panel no pulse un botón por error.

### Salir con operaciones en marcha

Si sale con operaciones en marcha, se le dice cuántas hay, por ejemplo «Hay 2 operaciones en curso.», con los botones «Esperar y salir», «Cancelar las operaciones y salir», «No salir» y «Cancelar». «Cancelar» y Escape no salen.

## Crear carpeta con F7

F7 abre el diálogo «Crear carpeta», con el campo «Nombre de la carpeta». Puede crear varios niveles a la vez: a\b\c. Si el nombre no vale (un nombre reservado de Windows o un carácter prohibido), el mensaje dice qué falla. Donde no se puede escribir, se anuncia «Aquí no se pueden crear carpetas».

Al crearla, se anuncia «Carpeta creada:» y el nombre escrito, y el cursor va a la carpeta nueva; si creó varios niveles, a la primera de ellas.

## Eliminar

### Eliminar a la papelera

F8 o Supr envían los elementos de trabajo a la papelera de Windows. Si la confirmación está activa, se pregunta, por ejemplo, «¿Enviar a la papelera 1 carpeta y 3 archivos (45 MB)?», con los botones «Eliminar» y «Cancelar». Intro pulsa «Eliminar». Si la confirmación está desactivada, solo se anuncia el alcance, por ejemplo «3 marcados a la papelera».

Si la unidad no tiene papelera (una unidad de red o extraíble) o la ruta es demasiado larga, se avisa: «Esta unidad no tiene papelera (o la ruta es demasiado larga): los archivos se eliminarán definitivamente.», con los botones «Eliminar definitivamente» y «Cancelar». Intro pulsa «Cancelar», para que un Intro accidental no borre nada. Después se pide la confirmación del borrado definitivo, si está activa.

En un comprimido o un servidor no hay papelera: F8 y Supr eliminan definitivamente, con la confirmación del borrado definitivo.

En otros sitios, eliminar cambia así:

- En una cuenta de nube, lo eliminado va a la papelera del servicio si la tiene y la cuenta lo tiene activado (capítulo «Nubes»).
- En la papelera de reciclaje abierta como panel (Ctrl+F8, complemento «Papelera de reciclaje como panel»), Supr elimina definitivamente.
- En la raíz «Red» no se elimina nada: F8 y Supr dicen «En Red no se elimina nada. Para quitar una unidad o conexión, use Desconectar unidad de red.».
- En un NAS Synology solo se puede eliminar con los cambios permitidos en ese NAS (capítulo «NAS Synology»).

### Eliminar definitivamente

Mayús+F8 o Mayús+Supr eliminan sin pasar por la papelera. Con la confirmación activa (lo está de fábrica), se pregunta, por ejemplo, «¿Eliminar DEFINITIVAMENTE 3 archivos (45 MB)? No se puede deshacer.», con los botones «Eliminar» y «Cancelar». El botón predeterminado es «Cancelar»: pulsar Intro sin pensar no borra nada. Si desactiva «Confirmar al eliminar definitivamente» en Preferencias, página «General», solo se anuncia «Eliminando» y el alcance.

El borrado definitivo muestra su progreso en la ventana de operaciones y no sigue enlaces ni uniones. Si encuentra un archivo de solo lectura, pregunta ««nombre» es de solo lectura. ¿Eliminarlo?», con los botones «Eliminar», «Eliminar todos», «Omitir» y «Cancelar»; el predeterminado es «Omitir».

Si desactiva «Eliminar envía a la papelera» en Preferencias, página «General», F8 y Supr también eliminan definitivamente y piden su confirmación.

Si hay marcas y el cursor está en otro elemento, se pide la confirmación aunque esté desactivada, salvo que haya silenciado la «Pregunta de marcas y cursor» (con la casilla «No volver a preguntar» de esa pregunta al copiar o mover, o en Preferencias, página «Confirmaciones»).

Tras eliminar, el cursor queda en el elemento siguiente. Eliminar no se puede deshacer con Ctrl+Z: para recuperar lo que envió a la papelera, use la papelera de Windows o ábrala en un panel con Ctrl+F8 y elija «Restaurar a su sitio» (complemento «Papelera de reciclaje como panel»).

## Renombrar, duplicar y crear archivo

### Renombrar en el sitio

Mayús+F6 abre el diálogo «Renombrar», con el campo «Nombre nuevo» y el nombre actual. En un archivo queda seleccionado el nombre sin la extensión, para que pueda escribir encima sin perderla; puede cambiarlo en Preferencias, página «Paneles», «Al renombrar, seleccionar el nombre sin la extensión». En una carpeta se selecciona el nombre entero. El nombre se valida antes de aplicarlo. Cambiar solo mayúsculas por minúsculas también funciona.

F6 también renombra: si en el campo «Destino» escribe un nombre nuevo en la misma carpeta, mueve el archivo a ese nombre.

### Copiar aquí con otro nombre

Mayús+F5 copia el elemento del cursor en la misma carpeta. Abre el diálogo «Duplicar», con el campo «Nombre de la copia», y le propone «nombre (copia).ext»; si ya existe, «nombre (copia 2).ext».

### Crear archivo nuevo

Mayús+F4 abre el diálogo «Crear archivo», con el campo «Nombre del archivo nuevo» y la lista «Plantilla». La plantilla «Archivo vacío» es la inicial; las de serie son «Texto con fecha», «Markdown con título», «HTML básico», «CSV con cabecera» y «Archivo por lotes», y también aparecen las suyas, todas por orden alfabético (capítulo «Personalización avanzada»). Si el nombre no lleva extensión, se pone la de la plantilla. Crea el archivo en la carpeta del panel, anuncia «Archivo creado:» y el nombre, y lo abre para editarlo con la misma regla que F4 (asociación, editor externo o editor interno). Si ya existía, no lo toca: anuncia ««nombre» ya existía: se abre sin cambiarlo».

## Atributos y fechas

En el menú Archivos, elija «Atributos y fechas». El diálogo tiene:

- Casillas «Solo lectura», «Oculto», «Sistema», «Archivo» y «No indexar el contenido». Con un elemento, cada casilla está marcada o no; con varios, tiene tres estados: sin cambio, sí y no.
- Para la fecha de modificación: la casilla «Modificación sin cambio», marcada al principio, el campo «Fecha de modificación», que se activa al desmarcarla, y el botón «Ahora (modificación)». Las fechas se escriben como AAAA-MM-DD hh:mm:ss.
- En el disco, lo mismo para la creación: «Creación sin cambio», «Fecha de creación» y «Ahora (creación)».
- En un servidor SFTP, el campo «Permisos (octal, por ejemplo 644)».
- Si hay carpetas entre los elementos, la casilla «Aplicar también a las subcarpetas y su contenido».

Los cambios se aplican en segundo plano y al terminar se anuncia un resumen. Si no cambió nada, se anuncia «No ha cambiado nada».

## Propiedades, Abrir con y menú contextual de Windows

- Alt+Intro abre el diálogo de propiedades de Windows del elemento del cursor o de los marcados.
- «Abrir con otro programa», en el menú Archivos, abre el diálogo «Abrir con» de Windows.
- Ctrl+Aplicaciones o Alt+Mayús+F10, con el foco en un panel, abren el menú contextual del Explorador para los elementos de trabajo, con sus submenús «Enviar a» y «Abrir con». Lo que haga desde él lo hace Windows, así que no se puede deshacer en zCommander; solo «Cambiar nombre» lo hace zCommander. Si eligió algo, al cerrarlo el panel se actualiza.

Estas tres funciones solo valen para archivos del disco, no para comprimidos ni servidores, ni para rutas muy largas.

## Enlaces

En el menú Comandos, submenú Herramientas, elija «Crear enlace». El diálogo pide:

- «Tipo de enlace»: enlace simbólico, unión de carpeta, enlace duro o acceso directo (.lnk).
- «Destino (a dónde apunta)», con el botón «Examinar». Se propone el elemento del cursor.
- «Nombre del enlace (ruta completa)», que por defecto está en el otro panel.
- «Explicación»: un texto que describe el tipo elegido.

Al crearlo se anuncia el tipo y el nombre, por ejemplo «Enlace simbólico creado: notas».

Si Windows exige privilegios para crear un enlace simbólico, el diálogo le explica cómo activar el modo de desarrollador y le ofrece los botones «Crear una unión» (solo para carpetas), «Crear un acceso directo» y «Cancelar». Si ya sabe que no tiene ese permiso y el destino es una carpeta, el diálogo propone de entrada una unión.

En la lista, el tipo de un enlace dice «Enlace a» seguido de su destino, y la vista Información muestra adónde apunta.

## Buscar archivos con Alt+F7

Alt+F7 abre el diálogo de búsqueda. Tiene tres páginas, General, Contenido y Avanzado; pase de una a otra con Ctrl+Tab. En cualquier campo, Ctrl+H explica para qué sirve.

### Página General

- «Nombres»: patrones como los de marcar. Con la casilla «Nombres como expresión regular», se toman como expresión regular.
- «Buscar en»: por defecto, la carpeta actual. Puede poner varias separadas por punto y coma, usar el botón «Examinar» o marcar «En todas las unidades fijas».
- La casilla «Subcarpetas» y la «Profundidad máxima» (0 es sin límite).
- «Cargar búsqueda guardada»: al elegir una, rellena los criterios y anuncia «Cargada la búsqueda» y su nombre. Supr la borra de la lista, tras preguntar. «Guardar búsqueda como» guarda los criterios actuales con un nombre.
- En «Nombres», lo que va tras una barra vertical (|) se excluye, como al marcar. En «Buscar en» puede usar variables de entorno como %USERPROFILE%.

### Página Contenido

- «Texto contenido»: el texto que deben contener los archivos. Vacío, no se mira el contenido.
- Las casillas «Distinguir mayúsculas», «Palabra completa» y «Expresión regular».
- «Codificación»: automática, UTF-8, UTF-16 o ANSI (Windows-1252).
- «Que no contenga el texto»: busca los archivos que no lo contienen.
- «Leer también los archivos en la nube»: sin ella, no se leen los archivos de OneDrive que no están descargados.
- «Buscar también dentro de documentos»: busca el texto también dentro de PDF, DOCX, ODT, EPUB y otros documentos. Solo aparece si hay un complemento que sabe leerlos, como el lector de documentos.

### Página Avanzado

- «Tamaño mínimo» y «Tamaño máximo», con su «Unidad del tamaño».
- «Modificado desde» y «Modificado hasta», con fechas día/mes/año, o «Solo los últimos días».
- «Incluir ocultos y de sistema».
- «Tipo de elemento»: archivos, carpetas o archivos y carpetas.
- «Dentro de comprimidos ZIP y TAR».
- «Motor de búsqueda»: el de zCommander, que recorre las carpetas, u otro que aporte un complemento: «Índice: Everything o búsqueda de Windows» (complemento «Búsqueda instantánea») o «NAS Synology (Universal Search o File Station)». Los resultados de un NAS se pueden ver y abrir, pero no enviar al panel.

### Resultados

El diálogo no bloquea la ventana principal: puede volver a los paneles mientras busca. Los resultados aparecen en la lista «Resultados», con Nombre, Carpeta, Tamaño y Fecha, mientras se busca y sin mover su cursor. El recuento está en el campo «Estado». Al terminar se anuncia, por ejemplo, «Búsqueda terminada: 120 resultados en 4 s». Si llega al máximo de resultados de Preferencias, página «Búsqueda» (100000 de fábrica), se detiene y lo dice.

- El botón «Buscar» empieza la búsqueda; mientras busca se llama «Detener» y la para. Escape también la detiene; un segundo Escape cierra el diálogo.
- «Nueva búsqueda» detiene la búsqueda si sigue, vacía los resultados, conserva los criterios y lleva el foco a «Nombres», en la página General.
- «Ver (F3)» y «Editar (F4)» abren el archivo elegido en el visor o el editor sin mover el panel. Sobre una carpeta dicen «Es una carpeta: use Ir al archivo».
- Intro en la lista, o «Ir al archivo», cierra el diálogo y lleva el panel activo a la carpeta del archivo, con el cursor en él.
- «Enviar al panel» cierra el diálogo y abre los resultados en el panel activo como una lista sobre la que funcionan todas las órdenes. Solo funciona con resultados del disco: si hay resultados de comprimidos o servidores, el botón está desactivado y, al terminar la búsqueda, el anuncio y el campo «Estado» añaden «Solo se pueden enviar resultados del disco».
- «Guardar resultados» los guarda en un archivo de texto (UTF-8) y anuncia cuántos guardó y dónde.
- «Cerrar» cierra el diálogo.

## Comparar y sincronizar carpetas

### Comparar carpetas

Ctrl+F10 compara las carpetas de los dos paneles. Primero pregunta «¿Cómo se comparan los archivos de los dos paneles?», con los botones «Nombre», «Nombre y fecha», «Nombre, fecha y tamaño», «Contenido» y «Cancelar». Después marca en cada panel los archivos que no están en el otro o que son más recientes, como en Norton; si tienen la misma fecha pero distinto tamaño o contenido (según el criterio), los marca en los dos lados. Las fechas se dan por iguales si se diferencian en 2 segundos o menos. Solo compara los archivos de las carpetas actuales, no las carpetas ni su contenido. Se anuncia «Diferencias: 5 a la izquierda, 2 a la derecha» o «Las carpetas son iguales».

### Sincronizar carpetas

Ctrl+Mayús+F10 abre el diálogo «Sincronizar carpetas» con las carpetas de los dos paneles en los campos «Izquierda» y «Derecha». El foco empieza en el botón «Comparar». Elija:

- «Dirección»: «De izquierda a derecha» (la inicial), «De derecha a izquierda» o «En los dos sentidos».
- «Criterio»: «Fecha», «Fecha y tamaño» (el inicial) o «Contenido».
- La casilla «Incluir subcarpetas» (marcada) y el «Patrón de archivos» (*).
- «Ignorar diferencias de fecha de hasta 2 s», marcada, útil con memorias USB.
- «Eliminar en el destino lo que no está en el origen», desmarcada; no está disponible en los dos sentidos.

El botón «Comparar» llena la lista «Diferencias» con una fila por diferencia: Nombre (con la ruta relativa), Izquierda (tamaño y fecha, «Carpeta» y la fecha, o «No existe»), Acción y Derecha. Una carpeta que solo está en un lado es una sola fila. La acción se lee como texto: «Copiar a la derecha», «Copiar a la izquierda», «Eliminar a la derecha», «Eliminar a la izquierda», «Nada» o «Conflicto: cambiaron los dos». Cuando en un lado hay un archivo y en el otro una carpeta con el mismo nombre, se lee «Archivo frente a carpeta: nada». El campo «Estado» dice el resultado, por ejemplo «12 diferencias» y un resumen, o «Las carpetas son iguales». Si cambia la dirección o la casilla de eliminar después de comparar, las acciones propuestas se recalculan solas, sin volver a leer el disco, y se anuncia «Acciones recalculadas»; los cambios hechos a mano en la lista se sustituyen.

Para cambiar la acción de las filas seleccionadas, o de la del cursor, pulse una letra:

- D: copiar a la derecha.
- I: copiar a la izquierda.
- N: nada.
- B: borrar en el lado de destino (en los dos sentidos, borrar donde falta el otro).

Cada cambio se anuncia, por ejemplo «Copiar a la derecha: 3 filas». Las letras no saltan de fila. Las mismas acciones están en el menú contextual de la lista (Aplicaciones o Mayús+F10). Intro en la lista, o el botón «Comparar contenido», compara los dos archivos de la fila. El desplegable «Mostrar» filtra la lista: Todas, Copiar a la derecha, Copiar a la izquierda, Eliminar, Nada o Conflictos.

El botón «Sincronizar» pregunta «Se hará:» con un resumen y «¿Sincronizar?»; si hay borrados, el botón predeterminado es «No». Al aceptar, cierra el diálogo y hace las acciones como una operación en segundo plano, con progreso, cola y resumen: primero copia, sobrescribiendo sin preguntar, y después borra (a la papelera, si «Eliminar envía a la papelera» está activa y la unidad la admite). Las filas con «Nada» o con conflicto no se tocan. Si no hay nada que hacer, se anuncia «No hay nada que sincronizar».

## Renombrado múltiple con Ctrl+M

Ctrl+M renombra de una vez los elementos de trabajo con máscaras, contador, buscar y reemplazar.

### Campos del diálogo

- «Máscara del nombre» (por defecto [N]) y «Máscara de la extensión» (por defecto [E]).
- El botón «Insertar marcador» le ofrece la lista de máscaras para no tener que recordarlas.
- «Buscar» y «Reemplazar por». Sin «Expresión regular», puede poner varios textos separados por barra vertical (|) y otros tantos reemplazos; si «Reemplazar por» tiene uno solo, sustituye a todos los buscados. Con «Expresión regular», la barra vertical es parte de la expresión, y en «Reemplazar por» puede usar $1 o \1.
- Casillas «Expresión regular», «Distinguir mayúsculas», «Solo la primera coincidencia» y «Aplicar también a la extensión».
- «Mayúsculas del nombre» y «Mayúsculas de la extensión»: Sin cambio, minúsculas, MAYÚSCULAS, Primera letra o Cada Palabra.
- El contador: «Contador, valor inicial», «Contador, incremento» y «Contador, cifras».

Primero se aplican las máscaras, después buscar y reemplazar y por último las mayúsculas.

### Máscaras

Son las mismas de Total Commander:

- [N] es el nombre sin extensión. [N1] es su primer carácter; [N2-5], del segundo al quinto; [N2,5], cinco caracteres desde el segundo; [N-3,3], tres caracteres desde el antepenúltimo; [N3-], desde el tercero hasta el final. Por ejemplo, [N2-5] sobre «abcdef» da «bcde».
- [E] es la extensión, con los mismos tramos.
- [P] es la carpeta que contiene el archivo y [G], la carpeta de encima de esa. También admiten tramos.
- [C] es el contador con los valores de los campos. [C10+5:3] empieza en 10, sube de 5 en 5 y usa 3 dígitos: 010, 015, 020. Cada parte se puede poner sola: [C10], [C+5] o [C:3].
- De la fecha de modificación: [Y] año de cuatro cifras, [y] de dos, [M] mes, [D] día, [h] hora, [m] minutos y [s] segundos; [d] la fecha como AAAA-MM-DD y [t] la hora como hh.mm.ss.
- [U] pone en mayúsculas lo que sigue, [L] en minúsculas, [F] la primera letra de cada palabra en mayúscula y [n] lo deja sin cambio.
- [[ y ]] escriben corchetes.

### Vista previa y renombrado

La lista «Vista previa de los nombres» tiene Nombre actual, Nombre nuevo y Estado: «Sin cambios», «Correcto», «Duplicado», «Ya existe en la carpeta», «Máscara no válida» o «Nombre no válido» con el motivo (por ejemplo «Nombre no válido: carácter :»). Se actualiza un momento después de dejar de escribir. El campo «Resumen» dice cuántos se renombrarán.

El botón «Renombrar» aplica los cambios. Si alguna fila tiene un problema, no se renombra nada: un mensaje dice «No se puede renombrar:», el resumen y cuál es la primera fila con problemas, y después el foco va a esa fila (o a «Máscara del nombre», si la máscara está mal). Si ningún nombre cambia, dice «No hay nombres que cambiar: todos quedan igual.». Los cambios en cadena (a pasa a b y b pasa a c) se resuelven solos. Todo el lote se puede deshacer con Ctrl+Z.

Los complementos añaden sus máscaras, por ejemplo las etiquetas de audio del complemento de metadatos; salen también en «Insertar marcador». Mientras se calcula su valor, la vista previa muestra «…» en esa fila, y «Renombrar» espera a que termine el cálculo.

El botón «Insertar marcador» escribe la máscara elegida en el último campo de máscara que usó. El botón «Plantillas» abre un menú con «Guardar la combinación actual» y los submenús «Cargar» y «Borrar»; borrar pide confirmación.

## Comprimidos

### Entrar en un comprimido

Intro o Ctrl+Av Pág sobre un comprimido lo abren como si fuera una carpeta. La etiqueta del panel muestra la ruta con el comprimido, por ejemplo C:\datos\copia.zip\carpeta.

- Dentro puede ver (F3), copiar al otro panel (eso es extraer), buscar y comparar.
- Retroceso en la raíz del comprimido vuelve a la carpeta que lo contiene.
- Si desactiva «Intro entra en los comprimidos» en Preferencias, página «Paneles», Intro y Ctrl+Av Pág los abren con su programa.
- Con los consejos activos, al entrar se dice, por ejemplo, «Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido».

### Qué comprimidos se abren

Sin instalar nada:

- ZIP (también los comprimidos con Zstandard y los cifrados con AES, pidiendo la contraseña) y ZIPX.
- 7z.
- TAR y sus variantes: .tar.gz, .tgz, .tar.bz2, .tbz, .tar.xz, .txz, .tar.zst, .tzst, .tar.lz, .tar.lz4, .tar.lzma, .tlz y .tar.Z.
- RAR, de la versión 2.9 a RAR5, sin cifrar, también sólidos y en varias partes.
- CAB, ISO (sin UDF), LHA y LZH, cpio, ar, .deb, .rpm, XAR (.pkg) y WARC.
- Los archivos .gz, .bz2, .xz, .lzma, .zst, .lz, .lz4 y .Z sueltos se ven como una carpeta con un solo archivo dentro: el original, sin la extensión de compresión. Si desactiva «Abrir los .gz, .bz2, .xz y .zst sueltos como carpeta» en Preferencias, página «Comprimidos», Intro los abre con su programa.

Un RAR en varias partes (x.part1.rar y x.part2.rar, o x.rar con x.r00 y x.r01) se abre desde cualquiera de las partes y se lee entero. Todas las partes tienen que estar juntas en la misma carpeta del disco.

Con 7-Zip instalado en el equipo, zCommander lo usa también para:

- RAR cifrados y los 7z cifrados que zCommander no puede leer por sí mismo, pidiendo la contraseña.
- ARJ, CHM, MSI, NSIS, WIM, VHD, VHDX, DMG y SquashFS.

zCommander no instala 7-Zip ni lo trae: usa el que haya en el equipo. Lo busca solo; si lo tiene en otra carpeta, escríbala en Preferencias, página «Comprimidos», «Carpeta de 7-Zip». Sin 7-Zip, al entrar en un RAR cifrado suena el sonido de cifrado no admitido y se explica: «Este RAR está cifrado. zCommander no puede descifrarlo sin 7-Zip instalado.».

Los nombres de los ZIP antiguos del Explorador, que no indican su codificación, se leen como OEM 850 para que las eñes y los acentos salgan bien.

### Escribir dentro de un ZIP

En un ZIP puede copiar, mover, renombrar y eliminar archivos y crear carpetas. Los cambios se juntan y el ZIP se reconstruye una sola vez al terminar la operación. Si la operación se cancela o falla, el ZIP no se toca. La primera vez se le avisa: «Copiar, mover, renombrar o eliminar dentro de un comprimido lo vuelve a escribir entero al terminar. Con comprimidos grandes puede tardar, y ese último paso no se puede cancelar.», con el botón «Aceptar» y la casilla «No volver a preguntar». Si la marca, el aviso no vuelve a salir; se recupera en Preferencias, página «Confirmaciones».

Los demás comprimidos son de solo lectura como carpeta. Para añadir archivos a ellos, use Comprimir.

### Comprimir

Alt+F5 abre el diálogo «Comprimir» con los elementos de trabajo. El foco empieza en «Archivo comprimido». Tiene:

- «Resumen»: texto de solo lectura, por ejemplo «Comprimir 1 carpeta y 3 archivos (45 MB)».
- «Archivo comprimido»: la ruta del comprimido. Por defecto, en la carpeta del otro panel (si es del disco) y con el nombre del elemento, o de la carpeta actual si comprime varios.
- «Formato»: ZIP (el inicial), 7z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, «ZIP (Zstandard)», «ZIP cifrado con AES-256», TAR.ZST, TAR.LZ4, TAR.LZ, «ISO (imagen de disco)», cpio y XAR. Si no hay carpetas entre lo que comprime, también .gz, .bz2, .xz y .zst, que crean un archivo comprimido por cada elemento. Al cambiar el formato, cambia la extensión del nombre.
- «Nivel de compresión»: Sin compresión, Rápido, Normal (el inicial) o Máximo.
- «Contraseña (7z y ZIP con AES)» y «Confirmar contraseña», disponibles con 7z y con «ZIP cifrado con AES-256» (cifrado AES-256). En 7z se puede dejar vacía; el ZIP cifrado la necesita. Si no coinciden, se avisa «Las dos contraseñas no coinciden.».
- La casilla «Cifrar también los nombres», solo en 7z con contraseña: sin la contraseña no se puede ni ver qué archivos contiene.
- La casilla «Un comprimido por cada elemento».
- La casilla «Mover al comprimido (borra los originales)». Antes de empezar se pide confirmación: al terminar se prueba el comprimido y, si está bien, los originales se borran definitivamente, sin pasar por la papelera.
- «Motor»: texto de solo lectura que dice qué programa creará el comprimido: Python, libarchive o el 7za que trae zCommander, con su versión.
- Botones «Comprimir», «En cola» (también F2) y «Cancelar».

ZIP (Zstandard) es más rápido, pero algunos programas antiguos no lo abren. El método de los ZIP normales, y de lo que se añade dentro de un ZIP, se elige en Preferencias, página «Comprimidos», «Método de compresión ZIP».

Si el comprimido ya existe, se pregunta «Ya existe» y el nombre, «¿Qué quiere hacer?», con los botones «Añadir al comprimido», «Sustituirlo» y «Cancelar». Con «Un comprimido por cada elemento», si alguno ya existe se pregunta una sola vez para todos, con los botones «Añadir al comprimido», «Sustituirlo», «Cambiar el nombre» (crea, por ejemplo, «a (2).zip»), «Omitirlo» y «Cancelar». No se puede guardar el comprimido dentro de lo que se comprime.

RAR no se puede crear: es un formato cerrado.

### Extraer

Alt+F6 o Alt+F9 abren el diálogo «Extraer» para los comprimidos de trabajo; dentro de un comprimido, extraen lo marcado. El foco empieza en «Destino». Tiene:

- «Resumen», de solo lectura.
- «Destino»: la carpeta del otro panel.
- «Solo los que coinciden con»: un patrón; por defecto, *.
- «Si el archivo ya existe»: las mismas opciones que al copiar, con la lista de conflictos si elige Preguntar.
- La casilla «Cada comprimido en su propia carpeta», marcada si extrae más de un comprimido.
- «Contraseña (si la pide)».
- Botones «Extraer», «En cola» (también F2) y «Cancelar».

Por seguridad, no se extrae ninguna entrada del comprimido que intente escribir fuera de la carpeta de destino ni las de tipos no admitidos; se anota, por ejemplo, «No se extraen 2 entradas con rutas peligrosas o de un tipo no admitido.». Si el comprimido venía de Internet, los archivos extraídos también llevan esa marca, y Windows avisará antes de ejecutarlos.

### Probar

Alt+Mayús+F9 lee el comprimido entero comprobando que no está dañado y da un resumen, por ejemplo «Probar copia.zip: correcto, 10 archivos, 2 MB». Dentro de un comprimido, prueba ese comprimido.

### Preferencias de los comprimidos

En Preferencias, página «Comprimidos», con su valor de fábrica:

- «Usar libarchive para leer RAR, CAB, ISO y otros» (activada).
- «Usar 7za para crear 7z con contraseña» (activada).
- «Usar el 7-Zip instalado si lo hay» (activada) y «Carpeta de 7-Zip» (vacía: lo busca zCommander).
- «Método de compresión ZIP» (deflate, el de siempre).
- «Abrir los .gz, .bz2, .xz y .zst sueltos como carpeta» (activada).

libarchive y 7za son componentes de zCommander que se actualizan en Opciones, «Componentes externos» (capítulo «Componentes externos»).

## FTP, FTPS y SFTP

### El gestor de conexiones

Ctrl+K abre el diálogo «Conexiones FTP y SFTP». La lista «Sitios» tiene las columnas Nombre, Protocolo, Servidor (con el puerto si no es el habitual) y Usuario («anónimo» si está vacío). Si no hay ninguno, dice «No hay sitios guardados. Pulse Nuevo para crear uno.» y el foco empieza en «Nuevo».

- Botones: «Conectar» (el predeterminado), «Nuevo», «Editar», «Duplicar», «Eliminar» y «Cerrar».
- En la lista, Intro conecta, F2 edita y Supr elimina.
- Al eliminar un sitio se pregunta «¿Eliminar el sitio «nombre» y su contraseña guardada?», con «No» como botón predeterminado. Se borran también su contraseña y su frase de clave guardadas.

«Nuevo» y «Editar» abren el diálogo «Nuevo sitio» o «Editar sitio», con estos campos:

- «Nombre del sitio».
- «Protocolo»: «FTP», «FTP con TLS explícito (FTPS)» o «SFTP (SSH)».
- «Servidor» y «Puerto» (21 al principio; 22 con SFTP).
- «Usuario (vacío para anónimo)». En SFTP es obligatorio.
- «Contraseña». Si la deja vacía al editar, se conserva la guardada.
- La casilla «Guardar la contraseña (cifrada)», marcada. Si la desmarca, la contraseña se le pide al conectar y se borran la contraseña y la frase de clave guardadas.
- «Carpeta remota inicial» (/ al principio).
- La casilla «Modo pasivo (FTP)», marcada, y «Codificación de los nombres (FTP)»: UTF-8 o «Latin-1 (ISO-8859-1)». No están disponibles en SFTP.
- «Tiempo de espera (segundos)»: 30 al principio, de 5 a 600.
- «Clave privada (SFTP, opcional)», con el botón «Examinar», y «Frase de la clave privada». Solo en SFTP; la frase, solo con «Guardar la contraseña» marcada.

Al aceptar se comprueban los datos; si algo falla, se dice el motivo y el foco va a ese campo. Se anuncia, por ejemplo, «Sitio Prueba creado» o «Sitio Prueba guardado».

### Conexión rápida

Pulse Ctrl+G y escriba una dirección como ftp://usuario@servidor/carpeta, ftps://servidor o sftp://usuario@servidor:2222/carpeta. Si la dirección coincide con un sitio guardado, se usan sus ajustes. Si hace falta, se le pide la contraseña; la que escriba al conectar se olvida al desconectar.

### Trabajar en un servidor

Al conectar, el panel activo muestra la carpeta remota y su etiqueta dice, por ejemplo, «Izquierdo: ftp://ana@servidor/carpeta» (con el usuario si no es anónimo y el puerto si no es el habitual). Si la carpeta inicial no existe, se abre la raíz y se avisa «La carpeta inicial no existe; se abre la raíz del servidor». Puede listar, entrar, ver, editar, copiar en los dos sentidos (con la lista de conflictos), mover, renombrar, eliminar y crear carpetas. En SFTP también puede cambiar los permisos en el menú Archivos, «Atributos y fechas», con el campo «Permisos (octal, por ejemplo 644)».

Las transferencias usan una conexión aparte, así que puede seguir navegando mientras se copia.

Para desconectar, elija «Desconectar» en el menú Comandos, submenú Red: el panel vuelve a la última carpeta del disco en la que estuvo (o a su carpeta personal) y se anuncia «Desconectado de» y la dirección del servidor. Al salir de zCommander se cierran todas las conexiones.

### Seguridad de las conexiones

- La primera vez que se conecta a un servidor FTPS o SFTP, el diálogo «Servidor desconocido» muestra su huella, con los botones «Aceptar y recordar», «Aceptar solo esta vez» y «Cancelar». Si la huella cambia más adelante, el diálogo «Atención: la huella del servidor ha cambiado» lo explica y muestra las dos huellas, con «Aceptar la nueva y recordarla», «Aceptar solo esta vez» y «Cancelar», que es el predeterminado: puede ser un servidor distinto.
- Con FTP sin cifrar y un usuario con contraseña, la primera vez para cada sitio se avisa de que el usuario y la contraseña viajan en claro, con los botones «Conectar igualmente» y «Cancelar». Sin sitio guardado, se avisa una vez por sesión. El aviso se quita para todos los sitios en Preferencias, página «Confirmaciones», desmarcando «Aviso de conexión FTP sin cifrar».
- Los archivos descargados llevan la marca de Internet, para que Windows avise antes de ejecutarlos.

### Errores de red

Los mensajes dicen qué pasa. Al conectar, empiezan por «No se pudo conectar con» y el sitio, y siguen, por ejemplo, con «El servidor no responde.» o «Usuario o contraseña incorrectos.». Si se pierde la conexión, zCommander reintenta una vez sin avisar; si tampoco puede, dice «Se perdió la conexión con el servidor; se reintentó una vez sin éxito.».

## Línea de órdenes, menú de usuario y asociaciones

### Ejecutar órdenes

Escriba una orden de Windows en la línea de órdenes y pulse Intro. Se ejecuta en la carpeta del panel activo; si el panel está en un comprimido o un servidor, en su carpeta personal.

- cd ruta, cd .., cd \ y una letra de unidad con dos puntos (D:) cambian la carpeta del panel sin ejecutar nada. cd solo va a su carpeta personal, y D: va a la última carpeta que visitó en esa unidad.
- Las demás órdenes se ejecutan en segundo plano: se anuncia «Ejecutando». Lo que escriben se añade a la salida de las órdenes, que ve con Ctrl+O. Al terminar se anuncia, por ejemplo, «Orden terminada, código 0», y los paneles se actualizan.
- Para detener una orden que no termina, pulse Escape en el panel (si no hay ninguna macro en marcha ni ninguna lectura, cálculo, búsqueda de equipos ni filtro rápido que cancelar) o Escape con la línea de órdenes vacía. Se detiene la orden con todos los programas que lanzó y se anuncia «Orden detenida». Al salir de zCommander se detienen las que sigan en marcha.
- Ctrl+Intro en la línea de órdenes ejecuta la orden en una consola nueva que queda abierta. Hace falta para programas que le hacen preguntas. Con «Ejecutar las órdenes siempre en una consola nueva», en Preferencias, página «General», todas van así. Si eligió Windows Terminal como consola, estas órdenes se abren en cmd.
- Arriba y Abajo recorren las órdenes anteriores. Alt+F8 abre el diálogo «Historial de órdenes», con búsqueda y la lista «Órdenes ejecutadas»: Intro pone la orden elegida en la línea de órdenes, y el botón «Ejecutar ahora» la ejecuta. Se recuerdan 200.
- Escape vacía la línea; si ya está vacía, detiene la orden en marcha, y si no hay ninguna, vuelve al panel.

Desde el panel, Ctrl+Intro escribe el nombre del cursor en la línea de órdenes y Ctrl+Mayús+Intro, su ruta completa.

En la línea de órdenes, Ctrl+Espacio autocompleta rutas, alias y órdenes de zCommander, y zc seguido del nombre de una orden la ejecuta sin lanzar ningún programa. Los alias son órdenes cortas suyas. Todo ello se explica en el capítulo «Personalización avanzada».

### El menú de usuario

F2 abre su menú de usuario: la lista «Entradas», con sus órdenes propias y su tecla rápida, por ejemplo «A: Comprimir con 7-Zip». Intro, el botón «Ejecutar» o la tecla de la entrada la ejecutan. En un submenú, Retroceso o el botón «Volver al nivel superior» suben. Si el menú está vacío, se anuncia «El menú de usuario está vacío. Créelo en Opciones, Editar el menú de usuario.».

Para crearlo o cambiarlo, abra el menú Opciones y elija «Editar el menú de usuario». La lista «Entradas de este nivel» tiene los botones «Nueva», «Editar», «Eliminar», «Subir» y «Bajar». Cada entrada tiene «Etiqueta», «Tecla rápida», «Órdenes, una por línea» y dos casillas: «Ejecutar en una consola que queda abierta» y «Refrescar los paneles al terminar». Dos entradas del mismo nivel no pueden tener la misma tecla rápida. También admite submenús: «Abrir el submenú» entra en uno y «Volver al nivel superior» sale.

Si la carpeta actual es del disco y tiene un archivo zcommander.menu.json, sus entradas aparecen primero, como el NC.MNU de Norton. Por seguridad, al pulsar F2 se le pregunta si confía en esa carpeta, con los botones «Confiar y usarlo» y «No usarlo». Si confía, no se vuelve a preguntar mientras el archivo no cambie; si elige «No usarlo», se le preguntará la próxima vez.

### Asociaciones

Las asociaciones deciden qué programa se usa para cada tipo de archivo con Intro (abrir), F3 (ver) y F4 (editar). Son reglas en orden: un patrón, como *.txt;*.md, y una orden para cada acción. Para cada acción gana la primera regla que coincide y tiene esa orden escrita; si su campo está vacío, se mira la siguiente regla que coincida, y si ninguna tiene orden, se hace lo normal. Con «Intro entra en los comprimidos» activa, Intro entra en los comprimidos sin mirar las asociaciones.

Como orden puede escribir también zc: seguido del nombre de una orden de zCommander o de un complemento, por ejemplo zc:zc.reproductor:reproducir, o zc:macro: y el nombre de una macro.

Algunos tipos de archivo tienen una acción de fábrica con Intro: un .zcplugin se instala, un .zcbackup se restaura, un .zcperfil, un .zcsonidos, un .zcmacro o un .zcteclas se importan, un .zcc se descifra y los formatos de audio se reproducen con el reproductor. Para los .zcc y el audio, sus propias reglas ganan a estas; los archivos propios de zCommander (.zcplugin, .zcbackup y los demás) siempre hacen lo suyo.

Para editarlas, abra el menú Opciones y elija «Editar las asociaciones». La lista «Reglas (gana la primera que coincide)» tiene los botones «Subir», «Bajar», «Nueva», «Editar» y «Eliminar». Cada regla tiene «Patrón», «Orden para abrir (Intro)», «Orden para ver (F3)» y «Orden para editar (F4)».

### Variables

En el menú de usuario puede usar todas estas variables. En las asociaciones y en los programas externos (visor, editor y diferencias) valen todas menos %L y %?Título?valor%, que allí se dejan tal cual.

- %N: nombre del elemento del cursor, con extensión.
- %B: nombre sin extensión.
- %E: extensión.
- %P: ruta completa del elemento del cursor.
- %D: carpeta del panel activo.
- %O: carpeta del otro panel.
- %T: ruta completa del elemento del cursor del otro panel.
- %M: rutas de todos los elementos de trabajo.
- %L: ruta de un archivo temporal con los elementos de trabajo, una ruta por línea en UTF-8.
- %?Título?valor%: le pide un dato en un diálogo con un campo llamado «Título» y ese valor inicial. El dato no puede llevar comillas dobles.
- %%: el signo de porcentaje.

Ejemplo: 7z a %O\%N.7z %M crea en el otro panel un 7z con el nombre del cursor y todos los elementos de trabajo.

zCommander pone las comillas por usted, así que un nombre con espacios o con signos como & no rompe la orden. Si escribe usted las comillas ("%P"), la variable va dentro tal cual; %M debe ir sola y fuera de comillas. En el menú de usuario, si la orden resultante pasa de 8000 caracteres, no se ejecuta y se le avisa que use %L.

## Portapapeles y arrastrar y soltar

- Ctrl+C copia al portapapeles los elementos de trabajo y Ctrl+X los corta. Se anuncia, por ejemplo, «3 elementos copiados al portapapeles». Son compatibles con el Explorador.
- Ctrl+V pega en la carpeta del panel activo lo que haya en el portapapeles, también lo copiado en el Explorador. Pegar usa el mismo motor que copiar, con su lista de conflictos. Si pega en la misma carpeta de la que copió, se crean copias con «(copia)» en el nombre. Si algún archivo del portapapeles ya no existe, se avisa.
- Con «Pegar una ruta del portapapeles lleva a ella», en Preferencias, página «General», si el portapapeles tiene una ruta como texto, Ctrl+V va a esa carpeta.
- Ctrl+Mayús+C copia como texto las rutas completas de los elementos de trabajo. «Copiar los nombres» y «Copiar la ruta de la carpeta» están en el menú Archivos, submenú Portapapeles.
- Con el ratón, arrastrar de un panel al otro o al Explorador copia; con Mayús, mueve. Soltar desde el Explorador en un panel copia a su carpeta; con Mayús, mueve.

## Sumas, dividir, unir y comparar archivos

Estas funciones están en el menú Comandos, submenú Herramientas, salvo «Comparar archivos por contenido», que está directamente en Comandos.

### Crear sumas de comprobación

El diálogo tiene la lista «Algoritmo» (CRC32 en formato SFV, MD5, SHA-1, SHA-256, SHA-512 o BLAKE2b; SHA-256 al principio), la casilla «Un archivo de sumas por cada archivo», «Guardar en» y «Nombre del archivo de sumas», y los botones «Calcular» y «Cancelar». El formato es compatible con sha256sum; las rutas de las subcarpetas se escriben con barra invertida. Con un solo archivo, puede marcar «Copiar la suma al portapapeles y anunciarla»: se anuncia, por ejemplo, «SHA-256 de foto.jpg:» y la suma.

### Verificar sumas de comprobación

Con el archivo de sumas en el cursor (o eligiéndolo), abre una ventana con el «Resumen» y la lista «Archivos comprobados», con Nombre y Resultado: «Correcto», «Distinto», «No encontrado» o «Error de lectura», y el botón «Cerrar». Al terminar se anuncia el resumen.

### Dividir y unir

- Dividir archivo trabaja con un solo archivo. En «Tamaño de cada parte» elija 1,44 MB, 100 MB (el inicial), 650 MB, 700 MB, 4095 MB, 4,7 GB o «Personalizado», que activa «Tamaño personalizado» y «Unidad» (KB, MB o GB). Elija también la «Carpeta de destino» y pulse «Dividir». Las partes conservan el nombre completo: video.mp4 da video.mp4.001, video.mp4.002 y así sucesivamente, como mucho 9999 partes. Además se crea video.crc con el nombre original, el tamaño y la suma CRC32.
- Unir archivos: con cualquier parte en el cursor (no hace falta que sea la .001), busca la primera, junta las partes en orden y comprueba el resultado con el .crc si existe. El diálogo tiene el campo «Archivo de destino», con el nombre propuesto a partir del .crc, y los botones «Unir» y «Cancelar». Si el destino ya existe, pregunta si sustituirlo.

### Comparar archivos por contenido

Compara el archivo del cursor de cada panel, o los dos marcados de un panel.

- Si son textos, abre una ventana con la lista de diferencias, por ejemplo «Línea 12: cambiada», y, para la elegida, las dos versiones en los textos de solo lectura «Texto del izquierdo» y «Texto del derecho», seguidos del nombre de cada archivo. Los botones «Siguiente» y «Anterior» recorren las diferencias, «Volver a comparar» repite la comparación y «Cerrar» (o Escape) cierra la ventana. Si solo cambian la codificación o los fines de línea, dice «El texto es igual; cambian la codificación o los fines de línea».
- Si son binarios, abre la misma ventana con una sola fila: «Los archivos son iguales» o, por ejemplo, «Distintos a partir del byte 4096», y en los dos textos el volcado hexadecimal de esa zona.
- Si prefiere otro programa, indíquelo en «Programa externo de diferencias», en Preferencias, página «Visor y editor».

## Tamaño de carpetas

- Mayús+Espacio calcula el tamaño de las carpetas de trabajo y lo anuncia, por ejemplo «Documentos: 1,2 GB, 3400 archivos, 210 carpetas».
- Alt+Mayús+Intro calcula el de todas las carpetas del panel.
- El resultado aparece en la columna Tamaño. Escape cancela el cálculo.
- No se siguen enlaces ni uniones y no se descargan archivos de la nube.
- Los tamaños se olvidan al salir de la carpeta.

## Filtros y vista plana

### Filtro

Ctrl+F12 abre el diálogo «Filtro», con el desplegable «Mostrar solo los que coinciden con». Escriba un patrón, por ejemplo *.mp3;*.flac, con exclusiones tras la barra vertical. Las carpetas se filtran solo si está activa «Marcar por patrón incluye las carpetas» en Preferencias, página «Paneles». El filtro activo se dice en la etiqueta del panel, «Izquierdo: D:\Música, filtro *.mp3», y en el resumen. Para quitarlo, escriba *.* en el filtro o elija «Quitar el filtro» en el menú del lado, que quita también el filtro rápido.

### Filtro rápido

Ctrl+F muestra el campo «Filtro rápido» debajo de la lista. Al escribir, la lista se queda con los elementos cuyo nombre contiene el texto, sin distinguir mayúsculas ni acentos. Con el detalle «Detallado», se anuncia cuántos elementos quedan.

- Intro o Abajo vuelven a la lista y conservan el filtro.
- Escape en el campo, o en la lista, quita el filtro.

### Vista plana

Ctrl+B muestra en una lista todos los archivos de la carpeta y de sus subcarpetas; se anuncia «Leyendo las subcarpetas». Puede marcarlos y usar cualquier orden sobre ellos. Se calcula en segundo plano y Escape lo cancela. Tiene el mismo máximo de resultados que la búsqueda y, si llega a él, lo dice. Ctrl+B otra vez, o Retroceso, vuelve a la carpeta. Solo funciona en el disco: en un comprimido o un servidor avisa y no hace nada.

La lista muestra las columnas de la pestaña con la columna Ruta detrás de Nombre, porque los archivos vienen de carpetas distintas. Lo mismo pasa con los resultados de la búsqueda enviados al panel y con la cesta. Si en una de estas listas elige otras columnas con «Columnas» (menú Izquierdo o Derecho), valen para las listas de esa pestaña; las de sus carpetas no cambian. La columna Ruta también se puede elegir para las carpetas normales, donde repite la carpeta del panel.

## Red y unidades de red

Las órdenes de red están en el menú Comandos, submenú Red. Las conexiones FTP, FTPS y SFTP tienen su propio capítulo.

### La raíz «Red»

Ctrl+Mayús+K lleva el panel activo a la raíz «Red». También se llega eligiendo «Red» en el selector de unidades (Alt+F1 o Alt+F2) o escribiendo red:// en «Ir a la carpeta» (Ctrl+G).

Es una sola lista con las columnas Nombre, Tipo, Remoto y Estado. Los tipos van en este orden:

1. «Unidad de red»: las letras de unidad conectadas a la red, como Z:, con su carpeta remota y su estado («Conectada», «Desconectada: Intro para volver a conectar» o «No disponible»).
2. «Conexión sin letra»: recursos \\servidor\recurso conectados sin letra.
3. «Servidor favorito» y «Servidor reciente»: los servidores que ha visitado (los 20 últimos).
4. «Equipo encontrado»: los equipos de su red, que van apareciendo según se encuentran.
5. «Otro proveedor»: WSL, escritorio remoto, WebDAV, SSHFS o NFS, si están instalados en el equipo.

Mientras se buscan equipos hay una fila «Buscando equipos...». Al terminar se anuncia, por ejemplo, «Búsqueda terminada: 3 equipos». La búsqueda no mueve el cursor y no congela la ventana. Escape la detiene, y Ctrl+R (volver a leer) la vuelve a lanzar. zCommander busca equipos en la carpeta Red de Windows, por mDNS y, si el equipo está en un dominio, en el dominio.

En la raíz «Red»:

- Intro en una unidad o conexión entra en ella. En una unidad desconectada, la vuelve a conectar (pidiendo usuario y contraseña si hace falta) y entra.
- Intro en un servidor o un equipo lista sus recursos compartidos. Retroceso vuelve a la raíz «Red» con el cursor en ese equipo.
- F8 y Supr no desconectan nada: se avisa que use «Desconectar unidad de red».
- Con el cursor en una unidad o conexión, «Desconectar unidad de red», «Volver a conectar la unidad» e «Información de la conexión» actúan sobre ella sin preguntar cuál.

### Recursos de un servidor

Ctrl+G con \\servidor, o Intro sobre un equipo, muestra sus recursos compartidos. Los recursos ocultos (los que terminan en $) solo se ven con los archivos ocultos visibles (Ctrl+punto). Las impresoras salen al final y no se puede entrar en ellas.

Si el servidor pide usuario y contraseña, se abre el diálogo «Credenciales de» seguido del servidor, con el mensaje, «Usuario», «Contraseña» y la casilla «Recordar la contraseña en Windows». Si deja vacío el usuario, se usa su cuenta de Windows.

Si Windows no deja conectar porque ya hay otra conexión con ese servidor con otro usuario (error 1219), zCommander ofrece cerrar las conexiones a ese servidor y reintentar, o usar otro nombre del servidor, como su dirección IP.

### Conectar una unidad de red

«Conectar unidad de red» abre el diálogo con:

- «Letra de unidad»: una letra libre, «Automática (la elige Windows)» o «Sin letra».
- «Carpeta de red (\\servidor\recurso)», con los servidores recientes en la lista. Ctrl+H en este campo explica también cómo escribir una dirección WebDAV, SSHFS o NFS.
- Las casillas «Volver a conectar al iniciar sesión», «Exigir cifrado SMB» y «Conectar con otras credenciales».
- «Usuario», «Contraseña» y la casilla «Recordar la contraseña en Windows».
- Los botones «Usar el cuadro de Windows...», «Conectar» y «Cancelar».

«Abrir un recurso compartido con otra cuenta» es el mismo diálogo con «Sin letra»: al conectar, el panel va al recurso.

Una dirección https:// conecta una carpeta WebDAV como letra de unidad, con el servicio WebClient de Windows. Si ese servicio está desactivado, zCommander lo explica sin cambiarlo. Microsoft ha declarado obsoleto WebClient: para WebDAV es mejor el complemento «Nubes».

La contraseña nunca se guarda en zCommander: si marca «Recordar la contraseña en Windows», la guarda Windows en su Administrador de credenciales.

### Volver a conectar y desconectar

- Al entrar en una unidad recordada que está desconectada, zCommander la vuelve a conectar sola si está activa «Volver a conectar las unidades de red al entrar» (Preferencias, página «Red»). Si no, se dice, por ejemplo, «Z: no está disponible (\\DS220\home). Intro para volver a conectar». «Volver a conectar la unidad» lo hace a mano.
- «Desconectar unidad de red» abre la lista «Unidades de red», con las conexiones sin letra también, y las casillas «Olvidar la conexión (no volver a conectarla al iniciar sesión)», «Olvidar también la contraseña guardada» y «Forzar aunque haya archivos abiertos». Antes de desconectar, los paneles que estaban en esa unidad salen de ella. Si hay archivos abiertos, se pregunta si desconectar a la fuerza, con el foco en «No».
- «Conectar con el cuadro de Windows» y «Desconectar con el cuadro de Windows» abren los cuadros de Windows de siempre.

### Información de la conexión y rutas UNC

- «Información de la conexión» muestra en un texto de solo lectura la unidad, la carpeta remota, el usuario, el espacio libre, el estado y, si zCommander se ejecuta como administrador, la versión de SMB, si va cifrada y la velocidad del enlace. Sin permisos de administrador, Windows no deja leer esos tres datos.
- Ctrl+Mayús+I y la vista Información (Ctrl+L) sobre una unidad de red dicen un resumen en una línea.
- «Copiar la ruta UNC», en el menú Archivos, submenú Portapapeles, copia la ruta de red de los elementos de trabajo: de Z:\carpeta pasa a \\servidor\recurso\carpeta.

### Contraseñas guardadas y sesiones

- «Contraseñas guardadas de servidores» lista los servidores con una contraseña guardada en Windows. «Olvidar...» la borra, tras confirmarlo.
- «Sesiones y archivos abiertos por la red» muestra quién está conectado a las carpetas que comparte este equipo y qué archivos tiene abiertos, con «Cerrar la sesión...», «Cerrar el archivo...» y «Actualizar». Solo funciona con zCommander ejecutado como administrador; si no, lo explica. zCommander nunca se eleva solo.

### Preferencias de la red

En Preferencias, página «Red», además de las de FTP:

- «Buscar equipos al entrar en la raíz «Red»» (activada): al entrar, busca los equipos en segundo plano si la última búsqueda tiene más de 10 minutos.
- «Buscar equipos también por mDNS» y «Buscar equipos también en el dominio» (activadas).
- «Tiempo máximo de la búsqueda de equipos (segundos)» (45).
- «Volver a conectar las unidades de red al entrar» (activada).
- «Exigir conexiones cifradas» (desactivada): no se conecta a servidores que no admiten cifrado.
- «Mostrar otros proveedores de red (WebDAV, NFS)» (activada).

Las conexiones que se vuelven a conectar al iniciar sesión y las contraseñas recordadas las guarda Windows, fuera de la carpeta de zCommander, y solo cuando usted lo pide.

## Consola y Explorador

- F11 abre una consola en la carpeta del panel activo. Por defecto es cmd; en Preferencias, página «General», campo «Consola», puede elegir PowerShell o Windows Terminal. Solo funciona en carpetas del disco: en otro sitio dice «La consola solo se puede abrir en una carpeta del disco».
- Mayús+F3 abre la carpeta actual en el Explorador de Windows, con el elemento del cursor seleccionado.

## Deshacer

Ctrl+Z deshace la última operación que lo admite. Antes pregunta qué se deshará, por ejemplo «¿Deshacer: Renombrar 12 elementos en D:\Fotos?», y pide confirmación. Al terminar dice «Deshecho:» y la operación; si algo había cambiado y no se pudo deshacer, lo añade.

Se pueden deshacer:

- Renombrar, uno o muchos.
- Mover dentro de la misma unidad del disco. Mover entre unidades no se puede deshacer.
- Crear una carpeta, si sigue vacía. Si creó varios niveles (a\b\c), se quitan todos los que creó, de dentro afuera, mientras sigan vacíos.
- Copiar: las copias que no han cambiado desde entonces van a la papelera. Si copió una carpeta y no ha cambiado, va entera a la papelera; si cambió algo dentro, van a la papelera los archivos que siguen igual y lo modificado o añadido se queda (se dice como omitido).

No se deshace eliminar (para eso está la papelera de Windows) ni nada hecho en un servidor o en un comprimido. Se recuerdan las 20 últimas acciones de la sesión; al cerrar zCommander se olvidan.

## La cesta

La cesta reúne archivos de varias carpetas para operar con ellos juntos.

- Ctrl+Mayús+B añade los elementos de trabajo a la cesta y anuncia, por ejemplo, «3 añadidos; la cesta tiene 12».
- «Abrir la cesta», en el menú Comandos, submenú Cesta, la muestra en el panel activo como una lista, con las columnas de la pestaña. Sobre ella funcionan todas las órdenes: copiar, mover, comprimir, eliminar. Retroceso vuelve a la carpeta.
- Al abrirla, se quitan los elementos que ya no existen y se anuncia, por ejemplo, «Se quitaron de la cesta 2 que ya no existen». Si está vacía, dice «La cesta está vacía». Si añade algo que ya estaba, dice «Ya estaban en la cesta» y cuántos tiene.
- «Vaciar la cesta» pide confirmación.

La cesta admite archivos y carpetas del disco; con otros dice «La cesta solo admite elementos del disco». Se guarda con la sesión.

## Complementos

Un complemento es un paquete que añade órdenes, columnas, visores o ventanas a zCommander. zCommander trae 27 complementos de serie (capítulos «Los complementos de serie», «Nubes» y «NAS Synology») y puede instalar otros desde un archivo .zcplugin.

Las órdenes de cada complemento están en el menú Complementos, dentro de su categoría, en un submenú con su nombre, y en la paleta de órdenes (Ctrl+E). Todas sus órdenes están juntas en ese submenú y en ningún otro menú. Las que tienen tecla de fábrica están en la lista de teclas (Mayús+F1), en un apartado por complemento.

Cada complemento tiene su propia ayuda: con el foco en una de sus ventanas, F1 la abre. También está en el gestor de complementos, botón «Ayuda».

### Cuándo se carga un complemento

Un complemento no se carga al arrancar zCommander, sino la primera vez que hace falta: al usar una de sus órdenes, al entrar en una de sus carpetas o al mostrar una de sus columnas. Por eso zCommander arranca igual de rápido con todos habilitados. La primera vez que use una orden de un complemento puede tardar un momento.

### El gestor de complementos

Abra el menú Complementos o el menú Opciones y elija «Gestor de complementos». La lista «Complementos instalados» tiene las columnas Nombre, Versión, Estado, Origen, Confianza y Autor.

- Estado: «Activo», «Sin cargar todavía», «Inhabilitado», «Sin aceptar», «Falló al cargar», «Fuera de uso por errores», «Error en el manifiesto» o «Incompatible», con el motivo. Si hay un cambio pendiente, se añade, por ejemplo, «se actualizará al reiniciar».
- Origen: «De serie» o «Instalado».
- Confianza: «Oficial», «Firmado por un autor de confianza» o «Sin firma».

El texto de solo lectura «Detalles» dice la descripción, los permisos, la licencia, la web y, si falló, el último error del complemento elegido.

En la lista:

- Intro abre su configuración, como el botón «Configurar».
- Espacio lo habilita o lo inhabilita.
- Supr lo desinstala, con confirmación.

Los botones son «Inhabilitar» o «Habilitar», «Aceptar» (solo en uno sin aceptar), «Volver a intentarlo» (en uno fuera de uso por errores), «Confiar en este autor», «Configurar», «Ayuda», «Novedades», «Instalar desde un archivo...», «Buscar actualizaciones», «Volver a la versión anterior», «Desinstalar», «Abrir su carpeta», «Ver su registro», «Ver los permisos» y «Cerrar». Cuando hay cambios que se aplican al reiniciar, aparece también «Reiniciar ahora».

Los complementos de serie no se desinstalan: se inhabilitan. Un complemento inhabilitado no aparece en los menús ni en la paleta, y sus teclas quedan libres.

### Instalar un complemento

1. Elija «Instalar un complemento desde un archivo», en el menú Complementos, o el botón «Instalar desde un archivo...» del gestor. También puede pulsar Intro sobre un archivo .zcplugin en un panel.
2. zCommander comprueba el paquete y muestra el «Resumen del complemento» en un texto de solo lectura: nombre, versión, autor, licencia, confianza, procedencia (si se descargó de Internet), permisos, componentes que usa y archivos.
3. Lea el resumen y pulse «Instalar», o «Cancelar» para no instalar nada.

Si el complemento no está firmado, se avisa: «Este complemento no está firmado. Ejecutará código con sus mismos permisos de Windows. Instálelo solo si confía en su autor.», y el botón predeterminado es «Cancelar». Puede prohibir los complementos sin firma desactivando «Permitir complementos sin firma» en Preferencias, página «Complementos».

Si se puede, el complemento queda listo enseguida: se anuncia, por ejemplo, «Ejemplo 1.0.0 instalado; ya puede usarlo.». Si no (una actualización, o un complemento que se carga al arrancar), se instala al reiniciar zCommander, y se le ofrece «Reiniciar ahora».

Los permisos se dicen en lenguaje claro, por ejemplo «conectarse a Internet y a la red local» o «ejecutar programas». Un complemento se ejecuta con sus mismos permisos de Windows: instale solo los de autores en los que confíe.

### Actualizar, volver atrás y desinstalar

- «Buscar actualizaciones», en el gestor, pregunta a cada complemento que lo admite si hay una versión nueva. Nunca instala nada sin preguntar: le dice qué hay y le ofrece ver su resumen para instalarla. Si está activa «Buscar actualizaciones de los complementos» (Preferencias, página «Actualizaciones»), también se buscan junto con las de zCommander.
- Una actualización de un complemento firmado tiene que venir firmada por el mismo autor; si no, se rechaza.
- «Volver a la versión anterior» vuelve, al reiniciar, a la versión que había antes de la última actualización.
- «Desinstalar» (o Supr en la lista) pregunta «¿Desinstalar» y el nombre, y después «¿Borrar también su configuración y sus datos?». En las dos preguntas el botón predeterminado es «No». El complemento se borra al reiniciar zCommander.

La configuración y los datos de cada complemento se guardan en data\config\plugins, así que sobreviven a sus actualizaciones.

### Configurar un complemento

Los complementos con opciones tienen su página en Preferencias, dentro de la rama «Complementos» del árbol de páginas. El botón «Configurar» del gestor (o Intro en su lista) abre Preferencias directamente en esa página. Algunos tienen además el botón «Abrir la configuración avanzada...» al final de su página.

### Si un complemento falla

- Un complemento que da un error no detiene zCommander. Se anuncia una vez, por ejemplo «El complemento Reproductor multimedia falló al reproducir. Detalles en el registro.».
- Tras 3 errores en la misma sesión, el complemento queda «Fuera de uso por errores» hasta reiniciar. El número se cambia en Preferencias, página «Complementos», «Fallos antes de dejar de usar un complemento». En el gestor, «Volver a intentarlo» lo vuelve a usar.
- Si zCommander se cerró de golpe mientras cargaba un complemento, al arrancar de nuevo lo deja sin cargar y pregunta qué hacer, con los botones «Inhabilitarlo» (el predeterminado), «Cargarlo de nuevo» y «Preguntar la próxima vez».
- Si aparece en la carpeta de complementos uno sin firma que no se instaló desde zCommander (copiado a mano, por ejemplo), no se carga: se pregunta si aceptarlo, con «No aceptarlo» (el predeterminado), «Aceptarlo» y «Ver los detalles...».

### Arrancar sin complementos

El modo seguro arranca zCommander sin ningún complemento. Se anuncia «Modo seguro: complementos desactivados». Hay tres formas de entrar:

- En el menú Complementos, «Reiniciar sin complementos».
- Mantener pulsada la tecla Mayús mientras arranca zCommander.
- Si zCommander se cerró de forma anómala dos veces seguidas, al arrancar se le propone.

Para volver al modo normal, use «Reiniciar zCommander», en el menú Archivos, o cierre y vuelva a abrir zCommander.

### Preferencias de los complementos

En Preferencias, página «Complementos»:

- «Permitir complementos sin firma» (activada).
- «Fallos antes de dejar de usar un complemento» (3).
- «Modo desarrollo de complementos» (desactivada): solo para quien programa complementos.
- «Registrar conexiones y programas de los complementos» (desactivada): anota en el registro las conexiones de red y los programas que lanzan los complementos sin haberlo declarado. Solo informa; no los impide.

## Los complementos de serie

zCommander trae 27 complementos de serie: los 25 de este capítulo y los de los dos capítulos siguientes, «Nubes» y «NAS Synology». Todos vienen habilitados y se pueden inhabilitar en el gestor de complementos. Cada uno tiene su ayuda completa, con todas sus órdenes, ventanas, teclas, preferencias y sonidos: púlsela con F1 dentro de sus ventanas o con el botón «Ayuda» del gestor.

Este es un resumen de cada uno, con la orden por la que empezar.

### Reproductor multimedia

Reproduce audio mientras navega, con una cola de reproducción. «Reproducir» (Ctrl+Mayús+F5) reproduce el archivo del cursor, los marcados o la carpeta; «Mostrar el reproductor» (Alt+Mayús+F2) abre su ventana. Desde cualquier sitio de la ventana principal, Alt+Mayús+F5 pausa o continúa, Alt+Mayús+F6 detiene, Alt+Mayús+F7 y Alt+Mayús+F8 retroceden y avanzan, y Alt+Mayús+F3 dice la posición.

Recuerda dónde dejó cada archivo de más de 10 minutos, admite marcadores, listas M3U8 y un temporizador de apagado. Usa el reproductor de Windows y, para lo que Windows no abre, FFmpeg. Cerrar su ventana no detiene la música.

### Lector de documentos

Lee PDF, DOCX, ODT, EPUB, RTF, HTML y FB2 (y DOC, si tiene Word) en el visor de zCommander: pulse F3 sobre el documento y recórralo por secciones (capítulo «Ver archivos con F3»). Añade las columnas Páginas, Título y Autor, «Buscar también dentro de documentos» en Buscar archivos y, en el menú Complementos, «Convertir a texto...» y «Propiedades del documento».

### Reconocimiento de texto, OCR

Reconoce el texto de imágenes y PDF escaneados con el OCR de Windows. «Reconocer el texto» (Ctrl+Mayús+F3) reconoce el archivo del cursor y lo muestra en el visor. También reconoce la imagen del portapapeles, la ventana en primer plano y varios archivos a la vez. «Reconocer la ventana en primer plano» es útil como tecla global (apartado «Teclas globales» del capítulo «Personalización avanzada»). El idioma se elige en su configuración avanzada, y su ayuda explica cómo instalar más idiomas en Windows.

### Metadatos y etiquetas de audio

Lee y edita etiquetas y portadas de MP3, FLAC, M4A y otros. «Editar las etiquetas...» (Ctrl+Mayús+F2) edita las del archivo del cursor o de los marcados; con varios, los campos distintos dicen «(sin cambio)». También pone etiquetas desde el nombre con vista previa, numera pistas, quita etiquetas, cambia la portada y exporta la lista de pistas. Añade columnas como Artista, Título y Duración, y máscaras para el renombrado múltiple. Los cambios se deshacen con Ctrl+Z mientras zCommander sigue abierto.

### Búsqueda instantánea

Busca nombres en todo el equipo al instante con Everything, si lo tiene instalado, o con el índice de Windows. «Búsqueda instantánea con Everything...» (Ctrl+Mayús+F, menú Complementos, submenú «Automatización», submenú «Búsqueda instantánea») abre su ventana: escriba en «Buscar», pulse Intro para ir al primer resultado e Intro en la lista para ir al archivo. También añade su motor a Buscar archivos (Alt+F7).

### Conversor multimedia con FFmpeg

Convierte, recorta, normaliza y une audio y vídeo. «Convertir audio o vídeo...» (Ctrl+Mayús+F6) convierte los elementos de trabajo con un perfil. En el menú Complementos están además extraer el audio, recortar sin volver a comprimir, normalizar el volumen, unir archivos de audio e información técnica. El original nunca se sobrescribe. Las conversiones van en la ventana de operaciones (F12).

### Buscador de duplicados

Encuentra archivos iguales y ayuda a quitar las copias. «Buscar duplicados...» (Mayús+F7, menú Complementos, submenú «Orden y limpieza del disco», submenú «Buscador de duplicados») compara por contenido, por nombre, por nombre y tamaño o por etiquetas de audio. La lista agrupa las copias y dice, por ejemplo, «Grupo 3 de 40, 2 copias, 12 MB recuperables». Puede enviar copias a la papelera, cambiarlas por enlaces duros o guardar un informe. Nunca deja un grupo sin ninguna copia.

### Ocupación del disco accesible

Dice qué ocupa el espacio con listas que se leen bien. «Analizar la ocupación...» (Ctrl+Mayús+F7, menú Complementos, submenú «Orden y limpieza del disco», submenú «Ocupación del disco accesible») analiza una unidad o carpeta como una operación (F12 la cancela) y la abre en el panel, ordenada de mayor a menor, con las columnas «Porcentaje del padre», «Porcentaje del total» y «Archivos». También lista los 100 archivos más grandes, los antiguos y la ocupación por extensión.

### Archivos en uso y procesos

Dice qué programa usa un archivo y le deja cerrarlo. «¿Quién usa este archivo?» lo dice para el elemento del cursor; «Procesos...» (Ctrl+Mayús+F12) abre la lista de procesos del equipo. Cuando una copia o un borrado fallan porque un archivo está en uso, la pregunta de error ofrece cerrar ese programa y reintentar. Nunca cierra servicios, procesos críticos, el Explorador ni zCommander.

### Editor hexadecimal accesible

Ve y edita los bytes de cualquier archivo, también muy grande. «Ver y editar en hexadecimal» (Ctrl+Mayús+F4, menú Complementos, submenú «Documentos y datos», submenú «Editor hexadecimal accesible») abre el archivo del cursor. Tab cambia entre la columna hexadecimal y la de texto, Insert alterna entre insertar y sobrescribir, y Ctrl+I abre el inspector de valores. Tras guardar, Deshacer empieza de nuevo.

### Imágenes: información, descripción y visor

Añade a la información del elemento (Ctrl+Mayús+I) las dimensiones y los datos EXIF de las fotos, abre un visor ampliable («Ver la imagen ampliada») y convierte o redimensiona imágenes. «Describir la imagen» la envía a un servicio de descripción que configure usted; está desactivado de fábrica y la primera vez avisa de qué se envía y a dónde. «Quitar la ubicación (GPS)» la borra sin volver a comprimir la imagen. Las órdenes están en el menú Complementos, submenú «Multimedia», submenú «Imágenes: información, descripción y visor».

### Sincronización avanzada y copias

Guarda tareas de sincronización con nombre: espejo, actualizar o en los dos sentidos, con versiones de lo que se sustituye. «Tareas de sincronización...» (menú Complementos, submenú «Automatización», submenú «Sincronización avanzada y copias») las crea y las ejecuta; «Ejecutar todas las tareas» las lanza todas. Se pueden programar con el programador de tareas.

### Cifrado de archivos

Cifra y descifra archivos y carpetas con contraseña, en formato .zcc o 7z. «Cifrar...» (Ctrl+Mayús+F8) cifra los elementos de trabajo; Intro sobre un archivo .zcc lo descifra. La contraseña no se puede recuperar.

### Notas, comentarios y etiquetas

Pone comentarios a los archivos en descript.ion, compatibles con Total Commander y Double Commander, notas a las carpetas y etiquetas. «Comentario o nota...» (Ctrl+N) edita el comentario del elemento del cursor o, sobre la fila «..», la nota de la carpeta. Añade las columnas «Comentario» y «Etiquetas». El color de una etiqueta siempre se dice también con texto.

### Proyectos y salto rápido

«Salto rápido...» (Ctrl+Mayús+J) lleva el panel a una carpeta frecuente escribiendo parte de su nombre: Abajo pasa de «Ir a» a la lista e Intro abre la carpeta. «Proyectos...» guarda la ventana tal como está (pestañas y vistas, como un espacio de trabajo) con una nota y sus carpetas.

### Historial del portapapeles

Recuerda lo que copia en cualquier programa para volver a pegarlo. «Historial del portapapeles...» (Ctrl+Mayús+V) abre la lista: Intro vuelve a poner el elemento en el portapapeles y Supr lo borra. Lo que los gestores de contraseñas marcan como privado nunca se guarda ni se anuncia.

### Lectura en voz y audiolibros

Lee archivos de texto y documentos con una voz de Windows y los convierte en audio. «Leer en voz alta o pausar» (Ctrl+F9) lee el archivo del cursor, pausa y continúa; también se puede usar como tecla global. Recorre por frases y párrafos y continúa donde lo dejó. «Convertir a audio...» crea audiolibros en WAV, MP3 u Opus, divididos por capítulos con el lector de documentos. La voz se elige y se prueba en su configuración avanzada.

### Monitor de carpetas y reglas automáticas

Vigila carpetas, avisa cuando llegan archivos y aplica reglas: mover, copiar, renombrar, extraer, etiquetar o ejecutar una orden o una macro. «Monitor de carpetas...», en el menú Complementos, submenú «Automatización», abre las reglas y las carpetas vigiladas; «Pausar o reanudar el monitor» y «Registro del monitor» completan el control.

### Seguridad de descargas e integridad

Comprueba un archivo descargado: «Comprobar la firma digital», «Comparar la suma con el portapapeles», «Analizar con Defender», «Buscar en VirusTotal» y «Quitar la marca de la Web». Están en el menú Complementos, submenú «Sistema y seguridad», submenú «Seguridad de descargas e integridad», sin tecla de fábrica. VirusTotal solo recibe la suma SHA-256 del archivo, nunca el archivo, y solo con su propia clave de VirusTotal; la primera vez se avisa de qué se envía.

### Papelera de reciclaje como panel

«Abrir la papelera» (Ctrl+F8) muestra la papelera de Windows en el panel activo, con las columnas «Ubicación original» y «Fecha de eliminación», lo más reciente primero. «Restaurar a su sitio» devuelve lo elegido (y pregunta si el sitio está ocupado), F5 lo copia al otro panel, Supr lo elimina definitivamente y «Vaciar la papelera» la vacía, con el foco en «Cancelar».

### Git básico

Trabaja con repositorios Git: «Estado de Git» (Ctrl+Mayús+F11) dice la rama y los cambios del repositorio de la carpeta actual. En el menú Complementos, submenú «Sistema y seguridad», submenú «Git básico», están añadir, confirmar, diferencias, historial, traer, enviar, cambiar de rama, clonar y descartar los cambios.

### Datos tabulares: SQLite y CSV

Intro sobre una base de datos SQLite la abre como carpeta, con un archivo .csv por cada tabla, de solo lectura. F3 sobre un CSV, o «Ver como tabla», abre el visor de tabla, que se lee por columnas con Flecha izquierda, Flecha derecha y Ctrl+1 a Ctrl+0, y permite filtrar, ordenar y exportar. Las consultas SQL son de solo lectura de fábrica.

### Organizador y renombrado por metadatos

Ordena y renombra archivos en carpetas según su fecha EXIF o sus etiquetas de audio, con una plantilla de carpetas y otra de nombre y una vista previa con el estado de cada archivo. «Organizar por metadatos...» está en el menú Complementos, submenú «Orden y limpieza del disco», submenú «Organizador y renombrado por metadatos». El resultado se deshace con Ctrl+Z.

### Programador de tareas

Ejecuta sincronizaciones, copias, limpiezas, macros u órdenes a una hora o cada cierto tiempo, también con zCommander cerrado: para eso crea tareas en el Programador de tareas de Windows, solo cuando usted lo pide. «Programador de tareas...» y «Registro de ejecuciones» están en el menú Complementos.

### Codificaciones y fines de línea

Añade las columnas Codificación y Fin de línea, y convierte textos a UTF-8 y a los fines de línea que elija. «Convertir la codificación y los fines de línea...» e «Informe de caracteres no válidos» están en el menú Complementos. La conversión se deshace con Ctrl+Z mientras zCommander sigue abierto.

## Nubes

El complemento «Nubes» convierte cada cuenta de nube en una unidad más del panel. Se elige con el selector de unidades (Alt+F1 o Alt+F2), se entra en sus carpetas, se ven y editan sus archivos (F3 y F4), se copian (F5) y se mueven (F6) con la lista de conflictos de siempre, se renombran, se eliminan y se busca en ellas (Alt+F7). El motor es rclone, que viene con zCommander.

### Cuatro formas de conectar

Para casi todas las nubes no hace falta crear claves ni identificadores: basta con iniciar sesión. El asistente dice en la columna «Cómo se conecta» cuál de estas cuatro formas usa cada servicio, y la lista va en este orden:

1. Iniciar sesión en el navegador: Google Drive, OneDrive y SharePoint, Dropbox, Box, pCloud, Yandex Disk, kDrive, Jottacloud, HiDrive, y Nextcloud u ownCloud. Solo se escribe el nombre visible de la cuenta. En kDrive hay que copiar además el número de la unidad (solo cifras), que está en la dirección web de kDrive detrás de «drive/» (puede pegar la dirección entera). En Jottacloud se elige antes el servicio (Jottacloud o una de sus marcas blancas, como Telia, Elgiganten o MediaMarkt), y solo puede haber una sesión activa en el equipo: si conecta otra cuenta de Jottacloud o usa a la vez su programa oficial, las sesiones se invalidan y hay que volver a autorizar.
2. Correo y contraseña: Mega (antes hay que haber entrado una vez en mega.nz con el navegador), Koofr y Mail.ru (con una contraseña de aplicación, no la normal; el asistente tiene un botón que abre la página donde se crea), Internxt, OpenDrive, cualquier servidor WebDAV y SFTP.
3. Carpeta del programa oficial: OneDrive, Dropbox, Google Drive para escritorio, iCloud para Windows, Box Drive, pCloud Drive, Proton Drive y Synology Drive, si tiene instalado su programa con la sesión iniciada. Se explica en «Carpetas de los programas oficiales».
4. Avanzado (claves propias): Amazon S3 y compatibles, Backblaze B2, Filen y «Otro servicio de rclone (avanzado)», que admite cualquiera de los más de 70 tipos de rclone.

Proton Drive e iCloud Drive por rclone son experimentales y solo salen si activa «Mostrar los servicios experimentales» en las preferencias del complemento; para ellas es mejor la carpeta de su programa oficial.

### Añadir una cuenta

1. En el menú Complementos, submenú «Nubes y NAS», submenú «Nubes», elija «Añadir una cuenta de nube...».
2. Si zCommander encuentra carpetas de programas oficiales que todavía no le ha enseñado, empieza por ellas (lo explica «Carpetas de los programas oficiales»). Pulse «Añadir además una cuenta de nube...» para seguir.
3. Elija el servicio en la lista (puede escribir para buscarlo) y pulse «Siguiente».
4. Escriba un nombre visible para la cuenta, por ejemplo «OneDrive de Ana». Si el servicio pide correo y contraseña u otros datos, escríbalos también. Pulse «Siguiente».
5. Si el servicio se autoriza en el navegador, pulse «Abrir el navegador», inicie sesión y conceda el acceso. Mientras espera, el texto de estado dice qué pasa y se anuncia cada cierto tiempo. Al volver, zCommander lo detecta solo.
6. zCommander comprueba la cuenta, dice su espacio y la añade.

Si rclone necesita preguntar algo más (por ejemplo, en OneDrive, si es una cuenta personal o un sitio de SharePoint, o un código de verificación), la pregunta sale en español cuando es una de las habituales.

En casi todos los servicios de navegador (no en Jottacloud, ni en Nextcloud u ownCloud), el botón «Opciones avanzadas...» tiene el identificador de cliente propio, por si su organización lo exige, y «Autorizar desde otro equipo», para cuando este equipo no tiene navegador. Normalmente no hace falta.

Para Nextcloud u ownCloud, use «Conectar Nextcloud u ownCloud...»: escriba la dirección del servidor y autorice en el navegador. zCommander recibe una contraseña de aplicación; nunca escribe usted su contraseña real.

### Google Drive

rclone retira durante 2026 el identificador compartido con el que se conecta a Google. Al elegir Google Drive y pulsar «Siguiente», zCommander pregunta cómo conectar:

1. Usar la carpeta de Google Drive para escritorio (solo si está instalado; normalmente la unidad G:). No pide nada y no caduca.
2. Iniciar sesión con el identificador de rclone. Es lo más sencillo hoy: tras autorizar, se contesta si la cuenta será una unidad compartida (No, para Mi unidad). Puede dejar de funcionar en 2026: entonces la cuenta pedirá volver a autorizar y habrá que usar otra forma.
3. Usar su propio identificador (avanzado). La orden «Guía para conectar Google Drive» explica paso a paso cómo crearlo en la consola de Google.

zCommander no registra una aplicación propia en Google ni en Microsoft.

### Carpetas de los programas oficiales

Los programas oficiales de OneDrive, Dropbox, Google Drive para escritorio, iCloud para Windows, Box Drive, pCloud Drive, Proton Drive y Synology Drive dejan en el equipo una carpeta, o una letra de unidad, con los archivos de la cuenta. zCommander las busca en el registro de Windows y en las carpetas habituales. Solo busca dónde están: nunca lee ni usa las contraseñas o los datos de acceso de esos programas.

- De fábrica, todas las carpetas encontradas salen ya en el selector de unidades (Alt+F1 y Alt+F2), sin hacer nada.
- Al abrir «Añadir una cuenta de nube...» con carpetas nuevas, el asistente dice, por ejemplo, «Este equipo ya tiene OneDrive e iCloud Drive. ¿Usar sus carpetas sin iniciar sesión?». La lista tiene una casilla por carpeta: Espacio la marca o la desmarca. «Usar estas carpetas» guarda la elección y termina; «Añadir además una cuenta de nube...» la guarda y sigue con la lista de servicios.
- Cada carpeta sale en el selector con su nombre, «carpeta del programa oficial» y su ruta, y se abre como un disco más. Las que desmarque en el asistente dejan de salir.
- Para volver a elegir, elija en la lista de servicios del asistente «Carpeta de un programa oficial (OneDrive, Dropbox, Google Drive, iCloud...)». Para ocultarlas todas, desactive «Mostrar en el selector de unidades las carpetas de los programas oficiales de nube», en Preferencias, rama «Complementos», «Nubes», página «Cuentas».

Qué se encuentra: OneDrive y Dropbox siempre que su programa tenga la sesión iniciada; Google Drive para escritorio, por su letra de unidad (en modo réplica, sin letra, no se encuentra: añada esa carpeta a favoritos); iCloud por su carpeta iCloudDrive; Box Drive por su carpeta Box, solo si el programa está instalado; pCloud Drive por la etiqueta de su unidad; y Proton Drive y Synology Drive solo si Windows los tiene en su registro de sincronización (Synology Drive, solo con la sincronización bajo demanda). Una carpeta de red que no responde se salta sin esperar.

Limitaciones: hace falta el programa oficial instalado y con la sesión iniciada; desde la carpeta no hay enlaces para compartir, ni papelera de la nube, ni espacio de la cuenta; y abrir un archivo que solo está en la nube hace que el programa lo descargue primero, lo que puede tardar. Si necesita esas funciones, añada además la cuenta de nube.

### La ventana «Cuentas de nube»

«Cuentas de nube...» (Alt+F11) muestra cada cuenta con su servicio, su estado («Conectada», «Volver a autorizar», «Sin comprobar» o «Volver a configurar») y su espacio. Intro abre la cuenta elegida en el panel activo y Supr la elimina, con confirmación. Los botones son «Abrir», «Añadir...», «Propiedades...», «Reconectar...», «Eliminar...», «Espacio» y «Cerrar». En «Propiedades...» cada cuenta tiene su carpeta inicial, solo lectura, papelera, caché y límites propios.

### Más órdenes de Nubes

Todas están en el menú Complementos, submenú «Nubes y NAS», submenú «Nubes»:

- Copiar un enlace para compartir, quitar el enlace compartido, vaciar la papelera de la nube (con el foco en «Cancelar») y el espacio de la nube.
- «Sincronizar con la nube...» y «Emparejar carpetas (en los dos sentidos)...»: primero muestran una simulación con la lista de cambios y solo los hacen si usted lo confirma.
- «Comprobar carpetas...» y «Buscar nombres duplicados...».
- «Crear una carpeta cifrada en la nube...» y «Unir varias cuentas en una unidad...».
- «Montar como letra de unidad...» y «Unidades montadas...»: necesitan WinFsp, que instala usted. La unidad existe mientras zCommander está abierto.
- «Compartir en la red...» y «Carpetas compartidas por zCommander...»: comparten una cuenta o una carpeta por WebDAV, SFTP, HTTP o DLNA, de fábrica solo en este equipo.
- «Pausar o reanudar los límites de velocidad».

Copiar y mover entre dos paneles de nube no necesita órdenes especiales: dentro de la misma cuenta lo hace el servidor, y entre servicios distintos rclone hace de puente sin pasar por el disco.

### Seguridad de las cuentas

- Los datos de acceso de las cuentas se guardan en data\config\rclone.conf, cifrado con una contraseña aleatoria que protege Windows. Si copia zCommander a otro equipo o a otra cuenta de Windows, tendrá que volver a añadir las cuentas.
- El motor rclone solo escucha en este equipo, con una contraseña nueva en cada arranque, y no escribe registros propios.
- Las preferencias del complemento (motor, velocidad y cuentas) están en Preferencias, rama «Complementos», «Nubes».

La ayuda del complemento (F1 en sus ventanas) explica todas las órdenes y preferencias.

## NAS Synology

El complemento «NAS Synology» controla un NAS Synology con DSM: estado y salud, discos, carpetas, usuarios, paquetes, contenedores, servicios, seguridad y más. Además, File Station se abre como una carpeta más en el panel.

### Solo lectura por defecto

Cada NAS empieza en modo solo lectura: zCommander puede verlo todo, pero no cambia nada. Las acciones que cambian algo aparecen desactivadas (Ctrl+H explica por qué) y, si se intentan, zCommander las bloquea antes de enviar nada al NAS.

Para cambiar algo, active «Permitir cambios en el NAS», en el menú Complementos, submenú «Nubes y NAS», submenú «NAS Synology», o la casilla «Permitir cambios en este NAS» de la ventana del NAS. Se explica qué se permitirá y se elige «Solo durante esta sesión» (lo recomendado) o «Hasta que lo vuelva a activar». Con los cambios permitidos, el título de la ventana empieza por «CAMBIOS PERMITIDOS» y cada acción pide confirmación.

Apagar, reiniciar e instalar DSM piden dos confirmaciones: la primera explica las consecuencias, con el foco en la opción segura, y la segunda pide escribir el nombre del NAS.

### Practicar con el NAS de demostración

La orden «NAS de demostración» arranca un NAS simulado dentro de su equipo: responde como un DS220+ con DSM 7.3.2, con discos, carpetas, usuarios, paquetes y contenedores inventados. Nada sale a la red y lo que cambie se pierde al cerrar zCommander. Es la forma segura de aprender el complemento antes de usarlo con su NAS.

### Dar de alta su NAS

1. En el menú Complementos, submenú «Nubes y NAS», submenú «NAS Synology», elija «Conectar con un NAS...» y pulse «Nuevo...».
2. Escriba un «Nombre», la «Dirección (nombre o IP)» y su «Usuario» de DSM. Deje marcada «Usar HTTPS (recomendado)» y el «Puerto» 5001.
3. La primera vez, zCommander muestra la huella del certificado del NAS. Compárela con la de DSM (Panel de control, Seguridad, Certificado) y pulse «Aceptar y recordar». Si un día cambia, zCommander avisa antes de enviar la contraseña.
4. Si su cuenta tiene verificación en dos pasos, escriba el código en «Código de verificación». Con «Recordar este equipo», DSM no lo vuelve a pedir.

La contraseña solo se guarda, cifrada, si marca «Recordar la contraseña». zCommander prueba la contraseña una sola vez cada vez que usted conecta, para no provocar el bloqueo automático de DSM.

### La ventana del NAS

«Estado del NAS» (Ctrl+Mayús+F9) abre la ventana del NAS, conectando si hace falta. Tiene la «Conexión», la lista de «Áreas», la «Sección» (si el área tiene varias partes), los «Elementos» del área y el «Detalle» del elegido, con los botones de las acciones del área.

- F6 pasa de las áreas a los elementos y al revés.
- Ctrl+R vuelve a leer el área.
- Ctrl+Mayús+T dice el uso del procesador, la memoria, la red y los discos.
- Aplicaciones o Mayús+F10, en la lista de elementos, abren el menú de acciones.
- Escape cierra la ventana; la conexión sigue abierta.

Las áreas que su NAS no tiene no aparecen. Cuando surge un aviso de salud nuevo (un disco con sectores dañados, un certificado que caduca, la falta de una actualización de seguridad de DSM), zCommander lo dice una sola vez.

### File Station en el panel

«Abrir File Station en el panel» muestra las carpetas compartidas del NAS en el panel activo, con direcciones como synology://nas_de_casa/Documentos. También aparece en el selector de unidades. Puede ver, copiar, mover, renombrar, crear carpetas y borrar como en cualquier carpeta, si los cambios están permitidos. Copiar o mover dentro del mismo NAS lo hace el propio NAS. «Crear un enlace compartido...», «Comprimir en el NAS...» y «Extraer en el NAS...» trabajan en el propio NAS, con su progreso en la ventana de operaciones.

### Qué conviene probar con su NAS

zCommander se ha probado con el NAS de demostración, no con todos los modelos reales. La primera vez que lo use con su NAS, compruebe con calma, todavía en solo lectura:

1. Que la conexión pide y recuerda la huella del certificado y, si la tiene, la verificación en dos pasos.
2. Que el área «Estado y salud» dice bien el modelo, la versión de DSM, la temperatura y los volúmenes.
3. Que «Almacenamiento y discos» lista todos sus discos con su estado S.M.A.R.T.
4. Que File Station en el panel lista sus carpetas compartidas y que puede ver un archivo con F3.
5. Que una búsqueda en el NAS (Alt+F7 con el motor del NAS) encuentra un archivo conocido.
6. Que las áreas de los paquetes que tiene instalados (Container Manager, Synology Drive, Synology Photos) aparecen y se leen bien.

Después, si lo necesita, permita los cambios solo durante la sesión y pruebe primero algo inofensivo, como crear y borrar una carpeta de prueba en File Station. No pruebe apagar, reiniciar ni actualizar DSM en un momento en que el NAS esté en uso. Si algo no se lee bien, anote el área, el modelo de NAS y la versión de DSM y comuníquelo.

La ayuda del complemento (F1 en la ventana del NAS) explica todas las áreas, órdenes y preferencias, y las herramientas avanzadas por SSH, desactivadas de fábrica.

## Sonidos

zCommander tiene un sonido corto para cada cosa que pasa: entrar en una carpeta, marcar, terminar una copia, un error, una pregunta, conectar con un servidor. Sirven para saber qué pasa sin esperar a la voz. Nunca son la única forma de saberlo: todo lo que suena se anuncia, queda en el historial de anuncios o se puede consultar.

Los sonidos están activados de fábrica. Suenan al volumen de Windows, por el dispositivo de audio predeterminado.

### Activar, silenciar y cambiar el volumen

- Ctrl+F11 silencia o activa todos los sonidos desde cualquier sitio de la ventana principal. Se anuncia «Sonidos desactivados» o «Sonidos activados».
- En el menú Opciones, submenú Sonidos, «Subir el volumen de los sonidos» y «Bajar el volumen de los sonidos» lo cambian de 10 en 10: se anuncia, por ejemplo, «Volumen de los sonidos: 80», y suena una muestra. No tienen tecla de fábrica; puede darles una en el mapa de teclas.

### La página Sonidos de Preferencias

En Preferencias, página «Sonidos»:

1. «Activar los sonidos»: la casilla general.
2. «Volumen»: un deslizador de 0 a 100 (70 de fábrica) que se lee, por ejemplo, «70 de 100». Al soltarlo, suena una muestra.
3. «Paquete»: el paquete de sonidos que se usa.
4. «Categoría»: «Todas» o una categoría (Navegación, Marcas, Operaciones, Red...), para filtrar la lista.
5. «Sonidos»: la lista con casillas de todos los sonidos de la categoría. Cada elemento dice su nombre y cuándo suena. Espacio activa o desactiva el elegido; Ctrl+A los activa todos y Ctrl+Mayús+A los desactiva todos, solo los de la categoría que se ve.
6. «Probar», o Intro en la lista: suena el sonido elegido, aunque esté desactivado.
7. «Progreso de las operaciones»: No (el de fábrica), Cada 25 % o Cada 10 %. Suena un tono más agudo cuanto más avanza cada operación.
8. «Los sonidos sustituyen a algunos anuncios»: si un sonido está activo, no se dice su anuncio breve (por ejemplo, «Marcado»). Los errores y las preguntas se dicen siempre. Con el volumen a 0, los anuncios vuelven.
9. «Intervalo mínimo de los sonidos de navegación (milisegundos)» (40): evita que, al moverse rápido, los sonidos se amontonen.
10. «Restablecer los sonidos de fábrica»: vuelve a activar o desactivar cada sonido como venía.
11. «Paquetes de sonidos...»: abre el gestor de paquetes.

### Los paquetes de sonidos

Un paquete es un juego completo de sonidos. Los cinco de serie tienen los mismos sonidos con distinto carácter:

- Clásico: tonos claros, con intervalos fáciles de reconocer. Es el de fábrica.
- Suave: tonos más lentos, filtrados y 6 decibelios más bajos, para usar todo el día.
- Retro 8 bits: ondas cuadradas y arpegios, como las consolas antiguas.
- Minimalista: clics y golpes muy cortos, que apenas ocupan tiempo de voz.
- Cristal: campanas con una cola corta.

En todos valen las mismas reglas: lo que abre, entra, marca o conecta sube de tono; lo que cierra, sale, desmarca o desconecta baja; los errores son graves y descendentes; terminar bien sube; y los sonidos de los complementos empiezan con un destello agudo muy corto.

### Crear y compartir paquetes

En el menú Opciones, submenú Sonidos, elija «Paquetes de sonidos» (o el botón «Paquetes de sonidos...» de la página Sonidos). La lista «Paquetes instalados» tiene los de serie y los suyos, con su «Descripción» y los botones «Nuevo a partir de este...», «Editar...» (solo los suyos), «Exportar...», «Importar...», «Eliminar» (solo los suyos, con confirmación), «Usar este paquete» y «Cerrar». Intro en la lista usa el paquete elegido.

«Nuevo a partir de este...» y «Editar...» abren un asistente de cuatro pasos, con los botones «Atrás», «Siguiente», «Terminar» y «Cancelar». Al cambiar de paso se anuncia, por ejemplo, «Paso 2 de 4: Datos».

1. Base: el «Paquete base» del que salen los sonidos que no cambie.
2. Datos: «Nombre», «Identificador», «Autor», «Licencia» y «Descripción».
3. Sonidos: elija una «Categoría» y un sonido en «Eventos», y use «Probar», «Sustituir por un archivo WAV...», «Volver al heredado» o «Probar el original». Intro en la lista prueba el sonido.
4. Resumen: cuántos sonidos son suyos y cuántos heredados, la casilla «Usar este paquete ahora» y el botón «Exportar como .zcsonidos...».

Los archivos WAV tienen que ser PCM de 8 o 16 bits, mono o estéreo, de 8000 a 48000 Hz, de 10 segundos y 2 MB como mucho. Si no lo son, se dice por qué.

Un paquete exportado es un archivo .zcsonidos. Para instalar uno, use «Importar...» o pulse Intro sobre el archivo en un panel. Sus paquetes se guardan en data\sounds_usuario y entran en las copias de seguridad.

Si en la 1.0 usaba los archivos operacion_terminada.wav, operacion_error.wav o carpeta_vacia.wav de data\sounds, la 2.0 los pasa a un paquete propio llamado «Mis sonidos 1.x» y lo elige.

### El mapa de sonidos

En el menú Ayuda, «Mapa de sonidos» sirve para aprender qué significa cada sonido y comparar paquetes. Elija el «Paquete» y la «Categoría»; la lista «Sonidos» tiene las columnas Evento, Cuándo suena y Estado («Activo» o «Desactivado»). Intro o el botón «Reproducir» lo hacen sonar, aunque esté desactivado. «Ir a las preferencias» abre la página Sonidos con ese sonido elegido.

La lista completa de los sonidos, con cuándo suena cada uno, está también en el archivo sonidos.md de la carpeta data\docs.

## Actualizar zCommander

zCommander puede buscar, descargar e instalar sus versiones nuevas. Cada versión está firmada: zCommander comprueba la firma antes de instalar nada.

### Buscar actualizaciones

- En el menú Ayuda, «Buscar actualizaciones» lo comprueba en el momento. Si no hay nada nuevo, dice «Sin novedades: zCommander está al día» y su versión, con un sonido.
- Además, con «Buscar actualizaciones de zCommander» activa (Preferencias, página «Actualizaciones»), lo comprueba solo: la primera vez un minuto después de arrancar y después cada «Cada cuántas horas» (24 de fábrica).
- Las dos usan el origen que elija en «Origen de las actualizaciones» (apartado siguiente).

### De dónde se buscan las actualizaciones

zCommander se publica en el servidor del proyecto y también en GitHub, en el repositorio hxebolax/zCommander, con una publicación por versión. En Preferencias, página «Actualizaciones», la opción «Origen de las actualizaciones» decide dónde se busca:

- «Servidor de zCommander (xebolax.synology.me)»: el de siempre, de fábrica.
- «GitHub (hxebolax/zCommander)»: la última versión publicada en GitHub. La descarga también llega de GitHub.
- «Las dos: la que tenga la versión más nueva»: pregunta a los dos, uno detrás de otro, y le ofrece la versión más nueva. Si uno no responde, usa el otro sin avisarle; solo si fallan los dos le dice el error, con el nombre de cada uno. Si la descarga falla en uno, prueba en el otro antes de rendirse.
- «Una dirección personalizada»: la dirección del archivo version.json que escriba en «Dirección personalizada del archivo version.json», por ejemplo una copia en la red de su empresa. Es obligatoria con esta opción, tiene que empezar por https:// y no puede llevar usuario ni contraseña; si no es así, al aplicar se le avisa y el foco va al campo. Ese campo solo está disponible con esta opción; con las demás, Tab lo salta. El paquete se descarga de la misma carpeta que el version.json y, si no está, de las otras direcciones que indique el archivo (por ejemplo, GitHub).

Con cualquier origen, la seguridad es la misma: la información de la versión nueva tiene que llevar la firma de zCommander, y el paquete descargado tiene que coincidir con el tamaño y la huella SHA-256 firmados, venga de donde venga. Una versión sin firma o firmada por otro nunca se instala, ni siquiera desde una dirección personalizada. El cambio se aplica en la siguiente búsqueda, sin reiniciar.

Si algo falla, el mensaje dice con quién: por ejemplo, «No se pudo conectar con GitHub. Compruebe la conexión a Internet.». El registro de zCommander apunta qué origen se consultó y de dónde se descargó cada versión.

Los componentes externos y los complementos tienen su propio origen: esta opción no les afecta.

Si hay una versión nueva, suena un aviso y se anuncia, por ejemplo, «Hay una versión nueva de zCommander: 2.1.0.». El diálogo de la actualización no le interrumpe: se abre en cuanto no hay ningún otro diálogo, menú ni decisión pendiente.

### El diálogo «Actualización disponible»

El foco empieza en «Novedades», un texto de solo lectura con lo que trae la versión. Debajo están el texto «Estado» y una barra de progreso. Los botones son:

- «Actualizar ahora»: descarga la versión nueva. El progreso se anuncia al 25, 50, 75 y 100 %. Si falla, el botón pasa a llamarse «Reintentar».
- «Omitir esta versión»: no se vuelve a ofrecer esta versión.
- «Más tarde»: cierra el diálogo. Mientras descarga, se llama «Cancelar»; Escape también cancela la descarga, que se reanuda la próxima vez.

Al terminar la descarga, zCommander se cierra, se sustituye y vuelve a abrirse solo en unos segundos. Si hay operaciones en marcha, antes le pregunta, con los botones «Esperar y actualizar», «Cancelar las operaciones y actualizar» y «No actualizar ahora».

Desde el código fuente, zCommander comprueba si hay versión nueva, pero no se instala: el diálogo lo dice.

### Después de actualizar

- Se anuncia «zCommander se ha actualizado a la versión» y su número, con un sonido, y se muestran las novedades una vez.
- Si la versión nueva no llega a arrancar bien, zCommander vuelve solo a la anterior, lo explica y no le vuelve a ofrecer esa versión.
- Si la versión nueva tarda más de 5 minutos en confirmar que arranca bien (por ejemplo, porque prepara componentes grandes en una memoria USB lenta), no se deshace nada; en el arranque siguiente se le pregunta, con «Volver a la versión anterior» y «Seguir con esta versión».

La actualización nunca toca su carpeta data: ni la configuración, ni los complementos que instaló, ni sus paquetes de sonidos. Los componentes de data\bin que traiga la versión nueva se integran al primer arranque, conservando los que usted haya actualizado a una versión más nueva.

Mientras haga falta, la versión anterior se guarda en data\temp\version_anterior, y lo que hizo la actualización queda en data\logs\actualizacion.log.

### Qué se envía

La comprobación solo envía al origen elegido (el servidor del proyecto, xebolax.synology.me, GitHub o su dirección personalizada) el nombre y la versión del programa («zCommander/2.0.1»). Nada más. GitHub redirige las descargas a sus servidores de archivos (githubusercontent.com); zCommander solo sigue redirecciones que sigan siendo https.

## Componentes externos

Algunas funciones usan programas de otros proyectos, que viven en la carpeta data\bin: rclone (las nubes), libarchive (RAR, ISO y otros comprimidos), 7za (crear 7z y ZIP cifrados) y FFmpeg (el reproductor, el conversor y la lectura en voz). Se llaman componentes. Cada versión de zCommander trae unos probados; la ventana «Componentes externos» los mantiene al día.

### La ventana «Componentes externos»

En el menú Opciones, elija «Componentes externos». La lista «Componentes» tiene las columnas Componente, Instalada, Nueva, Origen, Licencia y Usado por. Origen dice, por ejemplo, «Línea base» (el que trajo zCommander), «Actualizada», «Falta», «Dañado», «En mantenimiento», «Pendiente de reiniciar» o «Lo genera zCommander» (el complemento de NVDA). Solo las filas con una versión nueva tienen casilla para marcarlas.

El texto «Detalles» dice las novedades, el tamaño de la descarga y el resultado de la prueba del componente elegido. El texto «Estado» y su barra dicen qué se está haciendo.

Los botones son:

- «Buscar versiones nuevas».
- «Actualizar los elegidos»: descarga, comprueba la suma, prueba la versión nueva y, si funciona, sustituye la actual guardando una copia. Si después de sustituirla la prueba falla, vuelve sola a la anterior y lo explica.
- «Volver a la versión anterior», del componente elegido.
- «Restaurar los componentes originales...»: vuelve todos a los que trajo zCommander. Pregunta antes con la lista de cambios y el foco en «No».
- «Instalar»: instala, con su permiso, un componente que falta.
- «Omitir esta versión».
- «Abrir su carpeta».
- «Reiniciar ahora»: solo aparece si algo no se pudo sustituir en marcha y se aplicará al reiniciar.
- «Cerrar», que también cancela lo que esté en marcha.

Si está activa «Buscar versiones nuevas de los componentes» (Preferencias, página «Actualizaciones»), zCommander lo comprueba cada «Cada cuántos días los componentes» (7 de fábrica) y avisa, por ejemplo, «Hay versiones nuevas de 2 componentes. Opciones, Componentes externos.». Nunca descarga nada sin usted.

Si falta algún archivo de un componente, sus funciones dicen «Falta el componente» y su nombre, con la indicación de ir a Opciones, «Componentes externos», para restaurarlo.

Las copias de las versiones sustituidas se guardan en data\bin\respaldo: las dos últimas de cada componente y siempre la original.

## Copias de seguridad y perfiles

### Crear una copia de seguridad

Una copia de seguridad guarda en un solo archivo .zcbackup la parte de su configuración que elija, para recuperarla en este equipo o en otro.

1. En el menú Opciones, submenú «Copia de seguridad», elija «Crear una copia de seguridad».
2. En «Guardar en», escriba dónde se guarda o use «Examinar...». De fábrica, en data\backups, con un nombre como zCommander-2026-11-09.zcbackup. La carpeta de fábrica se cambia en Preferencias, página «General», «Carpeta de las copias de seguridad».
3. En la lista con casillas «Qué guardar», marque las partes. Todas salen marcadas salvo los registros.
4. En «Contraseñas guardadas (FTP, nubes, NAS, complementos)», elija «Incluirlas cifradas con una contraseña» y escriba dos veces la «Contraseña de la copia» (el campo «Fortaleza» dice si es débil), o elija «No incluirlas».
5. Escriba una «Descripción», si quiere, y pulse «Crear la copia».

Se crea en segundo plano y se anuncia, por ejemplo, «Copia creada: 2,3 MB, 7 partes».

La contraseña de la copia no se puede recuperar: sin ella, las contraseñas guardadas de la copia no se pueden usar. Las contraseñas de las unidades de red de Windows nunca se copian, porque Windows no deja leerlas.

### Las partes de una copia

- Preferencias: todas, salvo las teclas y la ventana. Se aplican al reiniciar.
- Perfiles y mapa de teclas: teclas personalizadas, esquema y perfiles propios. Al reiniciar.
- Sesión e historiales: carpetas y pestañas, historiales, cesta, espacios de trabajo y paleta. Al reiniciar.
- Favoritos, menú de usuario, asociaciones y plantillas, con las búsquedas, menús, vistas, reglas y alias. Se aplican en el momento.
- Conexiones (FTP, SFTP, WebDAV, nubes y NAS), con sus huellas y sus contraseñas si se incluyen. Al reiniciar.
- Complementos instalados y su configuración. La configuración, al reiniciar; los complementos se le ofrecen para instalarlos.
- Paquetes de sonidos propios. En el momento.
- Macros. En el momento.
- Registros (para soporte): no se restauran; solo se extraen a una carpeta.

### Restaurar una copia

1. En el menú Opciones, submenú «Copia de seguridad», elija «Restaurar una copia de seguridad», o pulse Intro sobre un archivo .zcbackup en un panel.
2. Elija el «Archivo de la copia» y pulse «Leer la copia». El «Resumen» dice de qué versión es, su fecha, su descripción, sus partes y si trae contraseñas.
3. En «Qué restaurar», marque las partes.
4. Revise la lista «Órdenes que se podrán ejecutar». Sale sin marcar: tiene las entradas del menú de usuario, asociaciones, alias, macros, programas externos y reglas que ejecutan algo, además del origen y la dirección personalizada de las actualizaciones (deciden de dónde se descargan e instalan), cada una con su texto completo. Solo se restaura lo que marque. Revíselas una a una, sobre todo en copias que no haya hecho usted.
5. Elija el «Modo»: «Combinar con lo actual» (el de fábrica) añade lo que falta y conserva lo que tiene; «Sustituir lo actual» deja cada parte como en la copia.
6. Si la copia trae contraseñas, escriba la «Contraseña de la copia».
7. Pulse «Restaurar».

Al combinar, cada huella de servidor nueva o distinta se le pregunta una a una, con «No aceptarla» (el predeterminado) y «Aceptarla»: una huella aceptada permite conectarse a ese servidor sin aviso.

Antes de restaurar, zCommander guarda una copia automática de lo que había en data\backups\automaticas (se conservan las 5 más recientes; el número se cambia en Preferencias, página «General», «Copias automáticas que se conservan»). Para deshacer una restauración, restaure esa copia.

Si todas las partes elegidas se aplican en el momento, se aplican ya. Si alguna se aplica al reiniciar, se le ofrece «Reiniciar ahora» o «Más tarde». Con «Más tarde», al arrancar se le pregunta, con «Aplicarla ahora», «Descartarla» y «Más tarde».

Los complementos de la copia que no tiene instalados se le ofrecen después, uno a uno, con su resumen, como al instalarlos desde un archivo. Una copia nunca instala nada sin preguntar.

### Perfiles propios

Además de Novato, Intermedio y Avanzado, puede guardar su configuración como un perfil con nombre. En el menú Opciones, submenú Perfiles, elija «Guardar la configuración como perfil» y escriba el «Nombre del perfil». El diálogo «Perfil de usuario» lo lista junto a los de fábrica, con «Renombrar...» y «Eliminar» para los suyos.

### Exportar e importar un perfil

Un archivo .zcperfil lleva sus preferencias, teclas, personalización y macros, y, si lo pide, sus paquetes de sonidos. Nunca lleva contraseñas ni conexiones. Sirve, por ejemplo, para que un formador prepare la configuración de sus alumnos.

- Exportar: en el menú Opciones, submenú Perfiles, «Exportar un perfil». Elija dónde guardarlo («Guardar en»), marque si quiere «Incluir los paquetes de sonidos propios», escriba una «Descripción» y pulse «Exportar».
- Importar: «Importar un perfil», o Intro sobre un .zcperfil. Elija el «Archivo del perfil» y pulse «Leer el perfil». La lista «Qué se aplica» compara cada preferencia con su valor actual, con casillas para elegir. La lista «Órdenes que se podrán ejecutar» sale sin marcar, como al restaurar. Pulse «Importar». Importar un perfil siempre combina: no borra nada suyo.

## Personalización avanzada

Las órdenes de este capítulo están en el menú Opciones, submenús Personalización y Macros, salvo donde se dice otra cosa. Sus preferencias están en Preferencias, página «Personalización».

### Macros

Una macro es una lista de órdenes que se ejecutan seguidas. Cada macro es una orden más: aparece en la paleta, puede tener tecla y puede ir en el menú «Mis órdenes».

Para grabar una:

1. Pulse Ctrl+Mayús+G. Se anuncia que empieza la grabación y el título de la ventana dice «Grabando macro».
2. Haga lo que quiere repetir con las órdenes de zCommander: ir a una carpeta, marcar por patrón, copiar...
3. Pulse otra vez Ctrl+Mayús+G. Escriba el nombre de la macro; se abre su editor.

Se graban las órdenes y lo que escribe en sus diálogos (la carpeta de destino de una copia, el patrón al marcar). No se graban las teclas de moverse ni las de consulta.

- Ctrl+Mayús+L repite la última macro ejecutada.
- Escape en el panel detiene la macro que esté en marcha.
- Si un paso falla, la macro se detiene y dice en qué paso, por ejemplo «La macro se detuvo en el paso 3: Copiar». Se cambia en «Detener la macro si un paso falla».

«Macros», en el submenú Macros, abre la lista «Macros» con «Nueva», «Editar», «Duplicar», «Eliminar», «Ejecutar», «Grabar una nueva», «Exportar...» e «Importar...». El editor de una macro tiene «Nombre», las casillas «En el menú Mis órdenes» y «En la paleta», «Tecla» con «Elegir la tecla...» y «Dejar sin tecla», y la lista «Pasos» con «Añadir paso...», «Cambiar el argumento...», «Subir», «Bajar», «Quitar» y «Probar». Además de órdenes, un paso puede decir un texto, esperar unos milisegundos o hacer sonar un sonido.

Una macro exportada es un archivo .zcmacro. Al importarla (también con Intro sobre el archivo), los pasos que ejecutan programas u órdenes salen sin marcar: solo se importan los que marque.

En el menú de usuario (F2) y en las asociaciones, una macro se escribe zc:macro: seguido de su nombre.

### Esquemas de teclas

Un esquema cambia algunas teclas de fábrica para parecerse a otro programa. En el submenú Personalización, «Esquema de teclas» muestra la lista «Esquemas»: Norton Commander (el de fábrica), Total Commander, Far Manager y Explorador de Windows. Para el elegido, «Descripción» explica qué cambia y la lista «Teclas que cambian» tiene las columnas Orden, Tecla actual y Tecla del esquema; «queda sin tecla» quiere decir que esa orden sigue en los menús y en la paleta. «Aplicar el esquema...» pide confirmación y dice cuántas teclas cambian. Sus teclas personalizadas se conservan.

Las teclas F3 a F8 y F10 son las mismas en todos los esquemas.

El mapa de teclas (Opciones, «Mapa de teclas») tiene ahora «Exportar...» e «Importar...»: un archivo .zcteclas lleva su esquema y sus teclas personalizadas. Intro sobre un .zcteclas abre la importación.

### Menús, «Mis órdenes» y barras

«Personalizar menús y barras» tiene cuatro pestañas; Ctrl+Tab pasa de una a otra:

- «Menús»: la lista «Elementos de los menús (marcados se ven)». Desmarque lo que no use para ocultarlo. Los menús no se pueden reordenar, para que este manual siga valiendo; lo oculto sigue con su tecla y en la paleta.
- «Mis órdenes»: los elementos del menú propio «Mis órdenes» (Alt+R), con «Añadir una orden...», «Separador», «Subir», «Bajar» y «Quitar».
- «Barra de botones»: los botones de la barra, con los mismos botones y «Etiqueta corta del botón».
- «Barra de teclas»: la lista «Huecos de la barra de teclas», con «Cambiar...», «Dejar vacío» y «Quitar el cambio», para poner otra orden en una tecla F de la barra.

Cada pestaña tiene «Restablecer esta pestaña».

La barra de botones se muestra con «Mostrar la barra de botones», en el submenú Personalización (o en Preferencias, página «Vista»). Queda bajo los paneles y fuera del orden de tabulación. Para usarla, pulse Alt+Mayús+F11: Izquierda y Derecha recorren los botones, Inicio y Fin van al primero y al último, Intro o Espacio ejecutan, y Escape o Tab vuelven al panel.

### Columnas y vista de cada carpeta

En el menú del lado, «Columnas y vista de esta carpeta» abre la lista «Conjuntos». Un conjunto es una vista con nombre: columnas, «Ordenar por», «Orden inverso», «Vista» y «Filtro». Sus botones son «Nuevo...», «Editar...», «Eliminar», «Aplicar a esta carpeta y sus subcarpetas», «Aplicar a carpetas con mayoría de...» (por ejemplo, la mayoría de archivos mp3, flac o m4a) y «Quitar las reglas de esta carpeta». El texto «Conjunto aplicado ahora» dice cuál se usa.

Al entrar en una carpeta con un conjunto, el panel lo aplica; al salir, vuelve a las columnas de la pestaña. Con detalle «Detallado» se anuncia, por ejemplo, «Vista Música». Los complementos añaden columnas, como Duración o Comentario.

En Preferencias, página «Personalización»: «Columnas y vista por carpeta» (activada) y «Recordar el orden y la vista de cada carpeta» (desactivada), que recuerda el orden, la vista y el filtro que cambie en cada carpeta.

### Orden de lectura de las columnas

«Orden de lectura de las columnas» decide qué columnas se leen al moverse con Izquierda, Derecha y Ctrl+1 a Ctrl+0, y en qué orden se colocan en la lista. En «Aplicar en» elija «Esta pestaña», el conjunto de la carpeta o «Las columnas por defecto». En la lista con casillas «Columnas que se leen, en este orden», marque las columnas y ordénelas con «Subir» y «Bajar». Se leen como mucho 15.

Con el complemento de zCommander para NVDA, NVDA lee al moverse solo esas columnas, en ese orden. Sin él, NVDA lee todas en el orden de la lista.

Si muestra las marcas en la columna Marca, póngala aquí la primera para oír «Marcado» antes del nombre, o donde prefiera.

### Reglas de anuncio, color y sonido

Una regla da un aviso a los elementos que cumplen una condición: por ejemplo, decir «grande» en los archivos de más de 1 GB, o sonar al llegar a un archivo de solo lectura.

«Reglas de anuncio, color y sonido» abre la lista «Reglas» con «Nueva...», «Editar...», «Activar o desactivar», «Subir», «Bajar», «Eliminar» y «Probar con el elemento del cursor», que dice qué regla se le aplicaría.

Cada regla tiene un «Nombre», la casilla «Regla activa», una condición («Patrón», «Más grande que», «Más pequeño que», «Modificado hace menos de» o «más de» unos días, «Es» archivo o carpeta y «Atributos que debe tener») y sus efectos: «Color», «Texto de la columna Regla», «Sonido» y «Anuncio al llegar el cursor». Se aplica la primera regla activa que coincide.

Un color solo se ve: si una regla solo tiene color, el editor avisa «Este efecto solo se ve». Póngale también un texto, un sonido o un anuncio.

### Alias y autocompletar en la línea de órdenes

Un alias es una orden corta que se escribe en la línea de órdenes y se cambia por otra más larga. «Alias de la línea de órdenes» abre la lista «Alias» con «Nuevo...», «Editar...», «Eliminar» y «Probar...», que muestra la orden completa sin ejecutarla. Cada alias tiene «Nombre» y «Orden». En la orden, %1 a %9 son las palabras escritas tras el alias y %* todas; valen también las variables de siempre, como %P y %M.

En la línea de órdenes:

- zc seguido del nombre de una orden de zCommander la ejecuta sin lanzar ningún programa, por ejemplo zc ir_a_carpeta D:\Fotos.
- zc macro seguido del nombre de una macro la ejecuta.
- zc ayuda lista estas órdenes en la salida de las órdenes.
- Ctrl+Espacio autocompleta rutas, alias y nombres de orden tras zc. Con varias opciones, la primera pulsación completa lo común y dice cuántas hay; la segunda abre una lista para elegir.

Se activan o desactivan en Preferencias, página «Personalización»: «Alias en la línea de órdenes» y «Autocompletar en la línea de órdenes con Ctrl+Espacio».

### Espacios de trabajo

Un espacio de trabajo guarda la disposición completa de la ventana: las pestañas de cada lado con su carpeta, vista, orden, filtro y columnas, el lado activo, los lados visibles y las barras. Ctrl+Mayús+W (o Comandos, submenú Paneles, «Espacios de trabajo») abre la lista «Espacios», con «Abrir» (también Intro), «Guardar el actual como...», «Sustituir con el actual», «Renombrar...» y «Eliminar». Al abrir uno se anuncia, por ejemplo, «Espacio de trabajo Proyecto web». Antes, la disposición que tenía se guarda como el espacio «Anterior», para volver a ella.

### Confirmaciones

Las preguntas y avisos que no son de seguridad se pueden silenciar; algunos, como el aviso al escribir en un comprimido o la pregunta de marcas y cursor, tienen la casilla «No volver a preguntar». En Preferencias, página «Confirmaciones», la lista «Confirmaciones que se hacen (desmarcada: no se pregunta)» las reúne: el aviso al escribir en un comprimido, el de conexión FTP sin cifrar, la pregunta de marcas y cursor, el aviso al cambiar el esquema de teclas, el aviso al crear una copia sin contraseñas y la pregunta al instalar un complemento de un autor de confianza. «Volver a preguntar todas» las recupera.

Nunca se pueden silenciar: eliminar definitivamente, vaciar papeleras, restaurar una copia, apagar o reiniciar un NAS, permitir cambios en un NAS, instalar un complemento sin firma ni ejecutar archivos .ps1, .vbs y .js.

### Plantillas de archivo nuevo

«Plantillas de archivo nuevo» abre en el panel su carpeta de plantillas, data\plantillas, y la crea con una copia de las de serie si no existe. Cada archivo de esa carpeta es una plantilla que aparece en «Crear archivo» (Mayús+F4). Dentro de una plantilla, {{fecha}}, {{hora}}, {{nombre}} y {{usuario}} se cambian por la fecha, la hora, el nombre del archivo nuevo y su usuario de Windows.

### La paleta de órdenes con favoritas

La paleta de órdenes (Ctrl+E) muestra primero sus órdenes favoritas y después las 10 que más usa. Dentro de la paleta, Ctrl+D marca o desmarca la orden elegida como favorita.

### Teclas globales

Una tecla global funciona aunque zCommander esté en segundo plano, mientras está abierto. Sirve, por ejemplo, para traer zCommander al frente, silenciar sus sonidos, pausar el reproductor, leer en voz alta, reconocer el texto de la ventana en primer plano o ejecutar una macro.

1. En Preferencias, página «Personalización», marque «Activar las teclas globales».
2. Pulse el botón «Teclas globales...». La lista «Órdenes» tiene las que admiten tecla global.
3. Elija una y pulse «Cambiar...»; pulse la combinación. «Quitar» la deja sin tecla global.

No hay ninguna de fábrica. Use combinaciones con Ctrl+Alt+Mayús, que casi ningún programa usa. Si otro programa ya tiene esa tecla, Windows no la deja registrar y zCommander lo dice.

### Arrancar con Windows

En Preferencias, página «General», «Arrancar zCommander al iniciar sesión en Windows» lo abre al entrar en su sesión, minimizado y sin hablar hasta que la ventana recibe el foco. Solo funciona en la versión compilada. Es la única vez que zCommander escribe en el Registro de Windows, y solo si usted lo activa. Si mueve la carpeta de zCommander, al arrancar le pregunta si corrige la ruta.

## Configuración y perfiles

### Preferencias

Ctrl+coma abre el diálogo «Preferencias». También está en el menú Opciones, «Preferencias».

Arriba está el campo «Buscar una opción». Debajo, un árbol con las páginas y, a su lado, las opciones de la página elegida. Con el foco en el árbol, Arriba y Abajo cambian de página. Desde cualquier opción, Ctrl+Tab y Ctrl+Mayús+Tab pasan a la página siguiente y a la anterior. Tab recorre las opciones. En cualquier opción, Ctrl+H explica para qué sirve.

Para encontrar una opción sin saber en qué página está, escriba parte de su nombre o de su ayuda en «Buscar una opción». La lista «Opciones que coinciden» muestra las que lo contienen, también las de los complementos, con su página. Abajo pasa a la lista; Intro lleva a la página de la opción elegida (desde el campo, a la primera) y pone el foco en ella.

Los botones son «Valores de fábrica de esta página», «Aceptar», «Cancelar» y «Aplicar». Los cambios se aplican al momento en las ventanas abiertas, salvo «Operaciones a la vez», que se aplica al reiniciar. «Valores de fábrica de esta página» pregunta antes y pone los valores de fábrica solo en la página que está viendo; no guarda nada hasta que pulse «Aplicar» o «Aceptar».

Las páginas y sus opciones, con el valor de fábrica entre paréntesis cuando no es una casilla:

- General: «Confirmar antes de salir», «Confirmar al eliminar a la papelera», «Confirmar al eliminar definitivamente», «Confirmar antes de ejecutar programas con Intro», «Eliminar envía a la papelera», «Consola» (Símbolo del sistema (cmd), PowerShell o Windows Terminal), «Ejecutar las órdenes siempre en una consola nueva», «Restaurar carpetas y pestañas al arrancar», «Tiempo máximo de espera de una unidad (segundos)» (10), «Anunciar «Leyendo» tras (milisegundos)» (300), «Tamaño del historial de carpetas» (100), «Tamaño del historial de órdenes» (200), «Pegar una ruta del portapapeles lleva a ella», «Arrancar zCommander al iniciar sesión en Windows» (desactivada), «Carpeta de las copias de seguridad» (vacía: data\backups) y «Copias automáticas que se conservan» (5).
- Paneles: «Al teclear en un panel, escribir en la línea de órdenes», «Mostrar archivos ocultos y de sistema», «Agrupar las carpetas al principio», «Orden natural de los números» («archivo2» antes que «archivo10»), «Mostrar la fila «..» para subir», «Intro entra en los comprimidos», «Formato de las fechas» (corta, larga con segundos o ISO), «Formato de los tamaños» (legible, en bytes o mixto), «Mostrar iconos», «Actualizar solo al cambiar los archivos», «Duración de la búsqueda rápida (milisegundos)» (1000), «Espera del árbol antes de cambiar el otro panel (milisegundos)» (400), «Disposición de los paneles» (lado a lado o uno encima de otro), «Al renombrar, seleccionar el nombre sin la extensión», «Marcar por patrón incluye las carpetas» y «Bajar al siguiente al marcar con Insert o Espacio».
- Vista: «Mostrar la línea de órdenes», «Mostrar la barra de teclas F1 a F10», «Mostrar la barra de estado», «Tema» (Sistema), «Tipo de letra» (vacío: el de Windows), «Tamaño de la letra (puntos)» (de 8 a 40), «Límite de la vista rápida (kilobytes)» (256), «Mostrar la barra de botones» (desactivada) y «Mostrar las teclas en los menús» (activada).
- Accesibilidad: «Anuncios por el lector de pantalla», «Detalle de los anuncios» (Normal), «Progreso de las operaciones por voz» (Al empezar y al terminar), «Consejos al llegar a sitios nuevos», las tres casillas de lectura de columnas («decir el número de fila», «decir el nombre de la columna» y «decir el contenido»), «Cómo se muestran las marcas» (Como selección de la lista; la otra forma es «En la columna Marca», capítulo «Marcar y elementos de trabajo»), «Retardo de los anuncios (milisegundos)» (150), «Salida de los anuncios» (Automática), «Hablar con la voz de Windows si no hay lector», «Movimientos del foco silenciosos con el complemento de NVDA» (activada) y el botón «Instalar el complemento de zCommander para NVDA...». Se explican en el capítulo «Accesibilidad y lectores de pantalla».
- Sonidos: la página propia del capítulo «Sonidos».
- Operaciones: «Si el archivo ya existe» (Preguntar), «Verificar después de copiar», «Conservar fechas y atributos», «Copiar los enlaces como enlaces», «Copiar también las carpetas vacías», «Operaciones a la vez» (3, de 1 a 8), «Tamaño de bloque para comprimidos y red (kilobytes)» (1024) y «Mostrar la lista de conflictos antes de copiar».
- Visor y editor: «Programa externo de diferencias», «Visor externo», «Ajuste de línea en el visor», «Codificación del visor» (Automática; también UTF-8, UTF-16, Windows (ANSI, 1252), Latín 1 y OEM de MS-DOS), «Cargar enteros los archivos de hasta (MB)» (16), «Tamaño de letra del visor» (11), «Usar un editor externo con F4», «Editor externo», «Guardar una copia .bak al editar» y «Tamaño de letra del editor» (11).
- Búsqueda: «Buscar en subcarpetas por defecto», «Incluir archivos ocultos por defecto» y «Máximo de resultados» (100000).
- Red: «Tiempo de espera de FTP y SFTP (segundos)» (30), «Modo pasivo de FTP por defecto» y las de la raíz «Red» y las unidades de red (capítulo «Red y unidades de red»).
- Comprimidos: las del capítulo «Comprimidos».
- Actualizaciones: «Buscar actualizaciones de zCommander» (activada), «Cada cuántas horas» (24), «Origen de las actualizaciones» (Servidor de zCommander; también GitHub, las dos o una dirección personalizada), «Dirección personalizada del archivo version.json» (vacía; solo con una dirección personalizada), «Buscar versiones nuevas de los componentes» (activada), «Cada cuántos días los componentes» (7) y «Buscar actualizaciones de los complementos» (activada).
- Personalización: «Menús según el nivel del perfil», «Columnas y vista por carpeta», «Recordar el orden y la vista de cada carpeta», «Esquema de teclas», «Activar las teclas globales» con el botón «Teclas globales...», «Alias en la línea de órdenes», «Autocompletar en la línea de órdenes con Ctrl+Espacio», «Anunciar cada paso de las macros», «Pausa entre los pasos de las macros (milisegundos)» (0), «Detener la macro si un paso falla» y «Aplicar las reglas de anuncio, color y sonido». Se explican en el capítulo «Personalización avanzada».
- Confirmaciones: la lista de preguntas que se pueden silenciar (capítulo «Personalización avanzada»).
- Complementos: las preferencias generales de los complementos (capítulo «Complementos») y, debajo, una página por cada complemento con opciones.

El aviso de FTP sin cifrar ya no está en la página «Red»: se activa o desactiva en la página «Confirmaciones». Los tonos de progreso y los sonidos de aviso de la 1.0 ya no están en «Accesibilidad»: los sustituye la página «Sonidos».

### Perfil

En el menú Opciones, submenú Perfiles, «Perfil de usuario» muestra la lista «Perfiles», con Novato, Intermedio, Avanzado y sus perfiles propios, el texto «Descripción» del elegido y la frase «Perfil actual:» con el perfil, o «Personalizado». El botón «Aplicar el perfil...» pregunta, por ejemplo, «¿Aplicar el perfil Novato?» seguido de «Al aplicarlo cambiarán» y el número de preferencias. Al aplicarlo se anuncia «Perfil Novato aplicado:» y cuántas preferencias cambiaron; si ya estaba aplicado, «El perfil Novato ya está aplicado». Los botones «Guardar la configuración actual como perfil...», «Renombrar...» y «Eliminar» manejan sus perfiles propios (capítulo «Copias de seguridad y perfiles»). Qué cambia cada perfil de fábrica se explica en «Elegir perfil: Novato, Intermedio o Avanzado», en el capítulo «Primeros pasos».

### Mapa de teclas

En el menú Opciones, «Mapa de teclas» muestra la lista «Órdenes» con sus columnas Orden, Teclas y Ámbito. En el campo «Buscar» puede escribir parte del nombre, de la ayuda o de la tecla para encontrar una orden; Abajo pasa a la lista.

1. Elija la orden en la lista.
2. Pulse «Cambiar» (o Intro en la lista). Se abre un campo, «Pulse la tecla», que captura la siguiente tecla que pulse.
3. Pulse la tecla nueva. Si ya la usa otra orden, se le pregunta, por ejemplo: «Ctrl+R ya es Volver a leer: ¿quitársela?». Al terminar se anuncia la orden y sus teclas.

Los demás botones son «Añadir otra tecla...» (una orden puede tener varias), «Quitar» (la orden queda sin tecla, pero sigue en los menús y en la paleta), «Restablecer esta», «Restablecer todas», que pide confirmación, y «Exportar...» e «Importar...», que guardan y cargan su esquema y sus teclas en un archivo .zcteclas.

La lista incluye las órdenes de los complementos y sus macros. Si un complemento instalado trae una tecla que ya usa otra orden, el complemento se queda sin esa tecla y se le avisa; puede darle otra en este mapa de teclas.

Algunas teclas son fijas y no se pueden cambiar: Tab (cambiar de panel y volver al panel desde la línea de órdenes), Ctrl+H (ayuda del control), F9 (barra de menús), Mayús+F10 y Aplicaciones (menú contextual). Tampoco se pueden usar las que reserva Windows, Alt con la letra de un menú ni las letras sin Ctrl ni Alt, que sirven para escribir y para la búsqueda rápida; el mensaje dice por qué.

El ámbito dice dónde funciona cada tecla: con el foco en un panel, en toda la ventana principal o en la línea de órdenes. Dos órdenes pueden compartir tecla si sus ámbitos no se solapan: Intro abre en el panel y ejecuta en la línea de órdenes.

### Columnas

En el menú Izquierdo o Derecho, «Columnas» elige qué columnas ve ese lado, su orden y su ancho: la lista «Columnas (marcadas se ven, en este orden)», con casillas, los botones «Subir», «Bajar» y «Restablecer» (las columnas y anchos de fábrica) y el campo «Ancho de la columna elegida (píxeles)». Al mover una columna se anuncia su posición, por ejemplo «Tamaño, posición 3 de 7». Los cambios se aplican al pulsar «Aceptar». En el menú Opciones, «Columnas por defecto» hace lo mismo para los paneles nuevos.

Las columnas disponibles son Nombre, Extensión, Tipo, Tamaño, Modificado, Creado, Atributos y Ruta, la columna Regla de las reglas de anuncio, color y sonido, la columna Marca (dice «Marcado» en las filas marcadas; capítulo «Marcar y elementos de trabajo»), y las que añaden los complementos, como Duración, Comentario o Codificación. La columna Nombre no se puede quitar. Mientras un complemento calcula el valor de una columna, la celda muestra «…».

Para que cada carpeta tenga sus propias columnas, y para elegir qué columnas se leen al moverse, vea el capítulo «Personalización avanzada».

### Temas y letra

En Preferencias, página «Vista», campo «Tema»:

- Sistema: los colores de Windows. Es el de fábrica.
- Norton clásico: fondo azul, texto cian, marcados en amarillo y el cursor con fondo cian.
- Alto contraste: los colores del modo de alto contraste de Windows.

El tipo y el tamaño de la letra de la página «Vista» (de 8 a 40 puntos) se aplican al momento a los paneles. El visor y el editor tienen su propio tamaño, en la página «Visor y editor» o con «Aumentar la letra» y «Reducir la letra» en sus menús.

### Restablecer los valores de fábrica

En el menú Opciones, elija «Restablecer los valores de fábrica». Antes, si quiere conservar su configuración, haga una copia de seguridad (capítulo «Copias de seguridad y perfiles»). Se le pide confirmación: «¿Volver a todas las preferencias de fábrica? También se pierden las teclas personalizadas, las columnas por defecto y las carpetas de confianza de los menús locales. Los favoritos, el menú de usuario y las asociaciones no se tocan.». Al aceptar, todas las preferencias vuelven a los valores de fábrica, que son los del perfil Intermedio, y se anuncia «Valores de fábrica restablecidos». El asistente no vuelve a salir al arrancar.

El capítulo «Solución de problemas» explica cómo hacerlo a mano si zCommander no arranca.

## La sesión y el arranque

### Qué se guarda en la sesión

zCommander recuerda, para la próxima vez: las carpetas, pestañas (y si están bloqueadas), vistas, orden, filtros, columnas e historial de carpetas de cada pestaña; la pestaña elegida y el lado activo; el historial de órdenes; y la cesta.

- Se guarda al salir, cada 5 minutos y cuando pulsa Mayús+F9 («Guardar la sesión ahora»), que anuncia «Sesión guardada».
- Una pestaña que estaba en un comprimido o un servidor vuelve a abrirlo al arrancar; si no puede, se abre la primera carpeta del disco que exista subiendo desde allí o, si no hay ninguna, su carpeta personal. Lo mismo pasa si una carpeta guardada ya no existe.
- Una pestaña que mostraba una lista (resultados, cesta o vista plana) se abre en la carpeta de la que partió.
- Para no restaurar la sesión, desactive «Restaurar carpetas y pestañas al arrancar» en Preferencias, página «General».
- Para guardar disposiciones con nombre y volver a ellas cuando quiera, use los espacios de trabajo (capítulo «Personalización avanzada»).

### Abrir zCommander en una carpeta

Si arranca ZCommander.exe con la ruta de una carpeta (por ejemplo, desde un acceso directo), el panel izquierdo se abre en ella. Con la ruta de un archivo, se abre su carpeta con el cursor en él. Si zCommander ya estaba abierto, la ventana abierta recibe la ruta y se trae al frente. Si pasa varias rutas, solo se usa la primera.

### Reiniciar

En el menú Archivos, «Reiniciar zCommander» lo cierra y lo vuelve a abrir, por ejemplo para aplicar un complemento o una copia de seguridad. «Reiniciar sin complementos», en el menú Complementos, lo abre en modo seguro (capítulo «Complementos»).

### Salir

F10 o Alt+X cierran zCommander. Si la confirmación está activa, se pregunta «¿Salir de zCommander?». F10 sale; no abre la barra de menús (para eso está F9). Si hay operaciones en marcha, se pregunta qué hacer con ellas (capítulo «Operaciones en segundo plano con F12»), y si hay un editor con cambios sin guardar, se pregunta si guardarlos.

## Aprender las teclas

### Paleta de órdenes

Ctrl+E abre el diálogo «Paleta de órdenes»: el campo «Buscar» y la lista «Órdenes», con cada orden, su tecla y su ayuda. Escriba lo que quiere hacer, por ejemplo «copiar», y la lista se queda con las órdenes que lo contienen; se anuncia cuántas hay y la primera, o «Ninguna orden coincide». Abajo pasa a la lista e Intro en el campo ejecuta la primera. Elija una con las flechas y pulse Intro, o el botón «Ejecutar»: la orden se ejecuta y se anuncia su tecla, por ejemplo «Atajo: F5», para que la aprenda. Si no tiene, se dice «Esta orden no tiene atajo; está en los menús y en la paleta.».

Con el campo vacío, la lista empieza por sus órdenes favoritas y sigue con las 10 que más usa. Ctrl+D, o el botón «Favorita», marca o desmarca como favorita la orden elegida. La paleta incluye las órdenes de los complementos y sus macros.

### Modo de ayuda de teclado

Mayús+F12 activa el modo de ayuda de teclado. Mientras está activo, cada tecla que pulse dice el nombre y la ayuda de su orden, sin ejecutarla. Para salir, pulse Escape o Mayús+F12 otra vez. Al entrar se anuncia «Modo de ayuda de teclado activado: cada tecla dice qué hace. Escape sale.», y al salir, «Modo de ayuda de teclado desactivado».

### Ayuda del control

En cualquier control de zCommander, Ctrl+H explica para qué sirve.

### Lista de teclas

Mayús+F1 abre, en el mismo visor que el manual, la lista de todas las teclas de fábrica («Teclas de la aplicación»), agrupadas por dónde funcionan, con un apartado por cada complemento de serie. También está en el menú Ayuda, «Lista de teclas». Si cambió alguna tecla en el mapa de teclas o eligió otro esquema de teclas, la lista no lo refleja: los menús y la paleta de órdenes sí dicen la tecla que tiene ahora.

## Accesibilidad y lectores de pantalla

### Qué lee el lector y qué anuncia zCommander

zCommander usa los controles normales de Windows, así que su lector lee solo las listas, los campos y los botones. Además, zCommander le envía anuncios con lo que el lector no puede saber por sí mismo: el resultado de una copia, cuántos hay marcados, que una carpeta está vacía. Nunca anuncia lo que el lector ya dice al mover el foco.

Los anuncios tienen cuatro niveles:

- Esencial: errores, preguntas y fin de las operaciones. Se dicen siempre, aunque haya desactivado los anuncios, y nunca interrumpen.
- Resultado: la respuesta a lo que acaba de pedir, por ejemplo «Marcados 12, 340 MB».
- Normal: cambios de carpeta, alcance de las órdenes y marcas.
- Detalle: datos extra, como el número de elementos al entrar en una carpeta.

### Cuánto habla zCommander

En Preferencias, página «Accesibilidad»:

- «Anuncios por el lector de pantalla»: si la desactiva, zCommander solo dice los esenciales.
- «Detalle de los anuncios»: breve (esenciales y resultados), normal (además, los normales) o detallado (además, los de detalle).
- «Consejos al llegar a sitios nuevos»: una frase con las teclas útiles al arrancar y al entrar en un comprimido o un servidor. Los consejos son anuncios de detalle: solo se oyen con «Detalle de los anuncios» en «Detallado».
- «Progreso de las operaciones por voz»: «Cada 25 %», «Al empezar y al terminar» o «Solo al terminar». «Cada 25 %» dice también el 25, el 50 y el 75 % de cada operación.
- Las tres casillas de lectura de columnas deciden qué se dice con Izquierda, Derecha y Ctrl+número: el número de fila, el nombre de la columna y su contenido. Si desactiva las tres, se dice el contenido.
- «Retardo de los anuncios (milisegundos)»: espera antes de hablar (150 de fábrica, de 0 a 2000), para no pisar lo que el lector dice al mover el foco.
- «Movimientos del foco silenciosos con el complemento de NVDA»: lo explica el capítulo «El complemento de zCommander para NVDA».

Los sonidos se configuran aparte, en la página «Sonidos» (capítulo «Sonidos»). Si activa «Los sonidos sustituyen a algunos anuncios» en esa página, los anuncios breves que tienen sonido (por ejemplo, «Marcado») dejan de decirse.

Si se pierde un anuncio, Ctrl+Mayús+U lo repite y Ctrl+Mayús+H abre el «Historial de anuncios», con el texto de solo lectura «Anuncios, el más reciente primero» (los últimos 500 de la sesión, con su hora) y los botones «Copiar al portapapeles» y «Cerrar».

### Voz directa o notificaciones de Windows

La opción «Salida de los anuncios» decide cómo llegan los anuncios a su lector:

- Automática (la de fábrica): con NVDA o JAWS, zCommander les habla directamente. Con Narrador u otro lector, usa las notificaciones de Windows (UI Automation), que Narrador lee.
- Siempre por el lector: siempre voz directa.
- Siempre por notificaciones: siempre notificaciones de Windows.
- Ninguna: zCommander no envía ningún anuncio, ni siquiera los esenciales; solo quedan en el historial de anuncios. Las preguntas siguen apareciendo como diálogos.

Las notificaciones de Windows separan la navegación de los avisos esenciales, para que un mensaje de navegación no borre un error que aún no se ha dicho.

Sin lector de pantalla, zCommander no habla. Si quiere oír los anuncios con la voz de Windows, active «Hablar con la voz de Windows si no hay lector».

### Con NVDA

- La salida automática habla directamente con NVDA.
- Insert es la tecla de NVDA. Para marcar, use Espacio; o pulse Insert dos veces seguidas para que llegue a zCommander.
- En la distribución de escritorio, NVDA usa el teclado numérico. Si Num +, Num - o Num * no llegan a zCommander, use Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N.
- En el manual (F1) en formato de página, use el modo exploración: H salta al siguiente encabezado y 2 o 3 al siguiente de ese nivel.
- El complemento de zCommander para NVDA mejora la lectura de las listas (capítulo «El complemento de zCommander para NVDA»). zCommander se lo ofrece una vez si NVDA está en marcha.

### Con JAWS

- La salida automática habla directamente con JAWS.
- Insert también es la tecla de JAWS: marque con Espacio.
- Si JAWS se queda con las teclas del teclado numérico, use Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N para marcar, desmarcar e invertir.
- En el manual en formato de página, el cursor virtual de JAWS recorre los encabezados con H.

### Con Narrador

- Narrador recibe los anuncios por las notificaciones de Windows. Hace falta Windows 10 versión 1709 o posterior.
- Si usa Insert como tecla de Narrador, marque con Espacio.
- En el manual en formato de página, use el modo de examen de Narrador para saltar por encabezados.
- Si Narrador no dice los anuncios de zCommander, compruebe que «Salida de los anuncios» está en «Automática» o en «Siempre por notificaciones».

### Con otros lectores de pantalla

Con lectores como System Access, Dolphin o PC-Talker, zCommander envía los anuncios por las notificaciones de Windows, como con Narrador. Que se oigan depende de que el lector las lea. Si no las lee, active «Hablar con la voz de Windows si no hay lector», o consulte los anuncios con Ctrl+Mayús+U y Ctrl+Mayús+H.

### El visor del manual

F1 abre este manual en un visor que no bloquea la ventana principal: puede consultarlo mientras trabaja.

- Si su equipo tiene el motor de Edge (WebView2), el manual se muestra como una página con encabezados, listas y tablas reales, que recorre con el modo exploración de su lector.
- Si no, se muestra como texto: delante hay una lista «Secciones» con todos los encabezados. Elija uno y pulse Intro para saltar a él. El texto está en el campo «Contenido».
- En los dos casos, Ctrl+F busca, F3 busca el siguiente y Escape cierra el visor. También tiene los botones «Buscar... (Ctrl+F)», «Buscar siguiente (F3)» y «Cerrar». Si no encuentra el texto, dice «No se encontró» y el texto.

### Baja visión

- Temas Sistema, Norton clásico y Alto contraste.
- Letra de 8 a 40 puntos para los paneles, y tamaños propios para el visor y el editor.
- El cursor y las marcas se distinguen también en el panel pasivo.
- zCommander respeta la escala de pantalla de Windows.
- Las reglas de anuncio, color y sonido pueden dar color a los archivos que le interesen (capítulo «Personalización avanzada»).
- El complemento de imágenes tiene un visor ampliable, con alto contraste.

## El complemento de zCommander para NVDA

zCommander trae un complemento para NVDA que mejora la lectura de sus listas. zCommander funciona igual sin él: el complemento solo afina lo que NVDA no puede saber por sí mismo. Solo actúa mientras zCommander está en primer plano.

### Qué mejora

- Texto completo en las listas: NVDA corta cada columna a 511 caracteres; con el complemento, en zCommander se leen enteras, por ejemplo una ruta muy larga en los resultados de una búsqueda.
- Sin repeticiones: cuando zCommander recoloca el foco por su cuenta (al volver a leer la carpeta, al restaurar las marcas, al aplicar un filtro o al volver de un diálogo al mismo elemento), NVDA no vuelve a leer el elemento en el que ya estaba. Se desactiva en Preferencias, página «Accesibilidad», «Movimientos del foco silenciosos con el complemento de NVDA».
- Orden de lectura: si eligió qué columnas se leen y en qué orden (capítulo «Personalización avanzada»), NVDA lee al moverse solo esas, en ese orden.
- Las marcas no dependen del complemento: si no quiere oír «seleccionado» en las filas marcadas, elija en Preferencias, página «Accesibilidad», «Cómo se muestran las marcas», «En la columna Marca». Funciona igual con NVDA, JAWS y Narrador (capítulo «Marcar y elementos de trabajo»).
- Leer la fila completa: el gesto de NVDA NVDA+Mayús+J lee todas las columnas de la fila con su cabecera. Pulsado dos veces seguidas, abre la fila en una ventana donde puede leerla con las flechas y copiarla. Es un gesto de NVDA, no una tecla de zCommander: se cambia en el menú de NVDA, Preferencias, «Gestos de entrada», categoría «zCommander».

### Instalarlo

1. En el menú Ayuda, elija «Instalar el complemento de zCommander para NVDA». También está en Preferencias, página «Accesibilidad», botón «Instalar el complemento de zCommander para NVDA...».
2. zCommander explica qué hace, dice la versión que ofrece y, si ya lo tiene, la instalada. Pulse «Abrir el instalador de NVDA», o «Cancelar», que es el botón predeterminado.
3. NVDA muestra su propia ventana de instalación, pide confirmación y se reinicia.

Si NVDA está en marcha al arrancar y el complemento no está instalado, zCommander se lo ofrece una sola vez, después del asistente de primer arranque.

El complemento lo instala NVDA en su propia carpeta: es una de las pocas cosas que quedan fuera de la carpeta de zCommander, y solo si usted lo acepta. Para desactivarlo o quitarlo, use el menú de NVDA, Herramientas, «Tienda de complementos», pestaña «Complementos instalados».

Necesita NVDA 2026.1 o posterior, y solo actúa con la versión compilada de zCommander (ZCommander.exe), no al ejecutarlo desde el código.

## Privacidad y seguridad

### Qué sale de su equipo

zCommander no envía estadísticas. Solo se conecta a Internet en estos casos:

- Para buscar actualizaciones de zCommander, si está activada esa opción: solo envía el nombre y la versión del programa al servidor del proyecto.
- Para buscar versiones nuevas de los componentes, en sus páginas de origen (GitHub y MSYS2), si está activada esa opción.
- Para buscar actualizaciones de los complementos que lo admiten, si está activada esa opción.
- Con los servidores, nubes y NAS que usted abra.
- Con lo que usted configure en un complemento: la descripción de imágenes y VirusTotal avisan la primera vez de qué se envía y a dónde. VirusTotal solo recibe la suma SHA-256 del archivo.

Las comprobaciones de actualizaciones se desactivan en Preferencias, página «Actualizaciones».

### Contraseñas

- Las contraseñas de los servidores, las nubes, el NAS y los complementos se guardan cifradas con el cifrado de Windows ligado a su cuenta, en data\config\secretos.dat, nunca en texto. Por eso no sirven en otro equipo ni en otra cuenta: si copia zCommander a otro ordenador, tendrá que escribirlas de nuevo, o llevarlas en una copia de seguridad cifrada con contraseña.
- Las cuentas de nube se guardan en data\config\rclone.conf, cifrado con una contraseña aleatoria guardada del mismo modo.
- Las contraseñas de unidades de red que pida recordar las guarda Windows en su Administrador de credenciales, no zCommander.
- Los registros nunca guardan contraseñas ni fichas de acceso: las quitan de las direcciones del tipo ftp://usuario:clave@servidor y de las respuestas de los servidores.

### Programas y órdenes

- Antes de ejecutar un programa con Intro, se pregunta según la preferencia «Confirmar antes de ejecutar programas con Intro». Los archivos .ps1, .vbs, .js, .wsf y .scr del disco preguntan siempre, y cualquier programa que esté dentro de un comprimido o en un servidor también, con «No» como respuesta de Intro.
- Los nombres de archivo se pasan a las órdenes de forma segura: un archivo llamado, por ejemplo, a&calc.txt no puede lanzar otro programa.
- Un menú de usuario local (zcommander.menu.json) solo se usa si confía en esa carpeta. Mientras no confíe, se pregunta cada vez que pulsa F2, y se vuelve a preguntar si el archivo cambia.
- Las copias de seguridad, los perfiles y las macros que importe nunca añaden órdenes que ejecuten programas sin que usted las marque una a una.

### Complementos

Un complemento se ejecuta con sus mismos permisos de Windows: zCommander no puede encerrarlo. Para protegerle:

- Antes de instalar se ven su autor, su licencia, su firma y sus permisos, y los que no están firmados piden confirmación con «Cancelar» como botón predeterminado.
- Un complemento firmado solo se actualiza con la firma del mismo autor, y si alguien cambia sus archivos después de instalarlo, no se carga.
- Un complemento que aparece en la carpeta sin pasar por el gestor no se carga hasta que usted lo acepta.
- Puede arrancar sin complementos en cualquier momento (capítulo «Complementos»).

### Archivos de Internet

- Lo que descarga de FTP o SFTP, y lo que extrae de un comprimido descargado de Internet, lleva la marca de Internet de Windows. Así Windows le avisa antes de ejecutarlo.
- Al extraer, se rechaza todo archivo del comprimido que intente escribir fuera de la carpeta de destino.

### Archivos temporales

Lo que se extrae para verlo o abrirlo con otro programa va a data\temp\extraidos. Lo del visor se borra al cerrarlo, y al arrancar zCommander se vacía la carpeta entera, por si quedaron restos.

### Información para soporte

En el menú Ayuda, «Información para soporte» copia al portapapeles la versión de zCommander, de Windows, de Python y de wxPython, la carpeta de datos, el perfil, los complementos instalados con su versión y su estado, los componentes, los paquetes de sonidos y las últimas 50 líneas del registro más reciente, y anuncia «Información para soporte copiada al portapapeles». Antes de enviarla a alguien, péguela en un documento y revise que no hay rutas o nombres que prefiera no compartir.

## Licencia y «Acerca de»

zCommander es software libre: puede usarlo, copiarlo, estudiarlo, modificarlo y redistribuirlo según la Licencia Pública General de GNU (GPL), versión 3 o posterior. Se distribuye sin ninguna garantía.

Los programas de terceros que trae (wxPython, rclone, libarchive, 7za, FFmpeg y otros) tienen sus propias licencias, todas libres. Sus textos están en la carpeta data\docs\licencias, con una carpeta por componente.

La oferta de fuentes dice dónde conseguir el código fuente exacto de zCommander y de sus componentes; vale durante tres años.

En el menú Ayuda, «Acerca de zCommander» abre un diálogo con el texto de solo lectura «Información»: nombre, versión, copyright, licencia, la dirección del código fuente y datos técnicos (versiones de Python y wxPython, sistema y carpetas). Sus botones son:

- «Ver la licencia»: abre el texto de la GPL en el visor de ayuda.
- «Componentes de terceros»: abre la lista de componentes con su licencia.
- «Oferta de fuentes»: explica cómo conseguir el código fuente.
- «Copiar la información»: copia todo el texto al portapapeles, por ejemplo para un correo de soporte.
- «Cerrar», o Escape.

Los tres primeros cierran el diálogo y abren el documento en el visor, con el foco en su contenido. Si alguna vez montó una nube como letra de unidad, «Acerca de» añade el aviso de WinFsp que exige su licencia.

## Dónde guarda sus datos

Todo está en la carpeta data, junto a ZCommander.exe. Para abrirla, use el menú Opciones, «Abrir la carpeta de datos».

- data\config: su configuración. Contiene settings.json (preferencias, con su copia settings.json.bak), sesion.json (carpetas y pestañas), novedades.json (la última versión de la que vio las novedades), favoritos.json, menu_usuario.json, asociaciones.json, conexiones.json, busquedas.json, plantillas_renombrado.json, secretos.dat (contraseñas cifradas), las huellas de los servidores (hosts_conocidos.json y known_hosts) y los archivos de la 2.0: macros.json, menus.json, alias.json, reglas.json, espacios.json, vistas_carpeta.json, paleta.json, red.json, rclone.conf (cuentas de nube, cifrado), la carpeta perfiles (perfiles propios) y la carpeta plugins (configuración y datos de cada complemento).
- data\plugins: los complementos que instala usted. Los de serie están en la carpeta plugins del programa, fuera de data.
- data\sounds: los paquetes de sonidos de serie. data\sounds_usuario: los suyos.
- data\bin: los componentes (rclone, libarchive, 7za, FFmpeg y el complemento de NVDA), con sus copias en data\bin\respaldo.
- data\backups: las copias de seguridad, si no eligió otra carpeta, y las automáticas en data\backups\automaticas.
- data\plantillas: sus plantillas de archivo nuevo, si las ha creado.
- data\logs: los registros de cada sesión. Se abre con el menú Opciones, «Abrir la carpeta de registros».
- data\cache: datos que se pueden borrar sin perder nada.
- data\temp: los archivos temporales.
- data\docs: este manual, la lista de teclas, el mapa de sonidos, las novedades y las licencias.

Para guardar su configuración, use las copias de seguridad (capítulo «Copias de seguridad y perfiles»). Recuerde que las contraseñas guardadas solo sirven en el mismo equipo y la misma cuenta, salvo que las lleve en una copia cifrada con contraseña.

### Lo que queda fuera de la carpeta data

zCommander guarda fuera de su carpeta solo estas cosas, y siempre porque usted lo pide:

1. «Arrancar zCommander al iniciar sesión en Windows»: un valor en el Registro de Windows.
2. Las tareas que crea el programador de tareas, en el Programador de tareas de Windows.
3. Las unidades de red que se vuelven a conectar al iniciar sesión, que guarda Windows.
4. Las contraseñas de red que pide recordar, en el Administrador de credenciales de Windows.
5. Las nubes montadas como letra de unidad con WinFsp, que existen mientras zCommander está abierto.
6. El complemento de zCommander para NVDA, que instala NVDA en su propia carpeta.

## Preguntas frecuentes

### ¿Puedo usar zCommander desde una memoria USB?

Sí. Es portable: copie la carpeta completa y ejecútelo desde allí. Las contraseñas guardadas no sirven en otro equipo.

### Pulso Insert y no marca nada

Su lector de pantalla usa Insert como tecla propia. Marque con Espacio. Con NVDA, también puede pulsar Insert dos veces seguidas.

### No tengo teclado numérico. ¿Cómo marco por patrón?

Use Ctrl+Mayús+M para marcar por patrón, Ctrl+Mayús+Q para desmarcar y Ctrl+Mayús+N para invertir. También puede filtrar con Ctrl+F y marcar lo visible con Ctrl+A.

### ¿Cómo sé qué tengo marcado?

Al moverse por la lista con marcas, el lector dice «seleccionado» en cada fila marcada, o «Marcado» si muestra las marcas en la columna Marca. Alt+Mayús+M dice cuántos hay marcados, cuánto ocupan y sus nombres; Ctrl+Mayús+S, el resumen de la carpeta con las marcas.

### Al teclear letras no se escribe en la línea de órdenes

Es lo normal con los perfiles Novato e Intermedio: las letras hacen búsqueda rápida. Para escribir órdenes, pulse Mayús+F2. Si prefiere el comportamiento de Norton, active en Preferencias, página «Paneles», «Al teclear en un panel, escribir en la línea de órdenes», o elija el perfil Avanzado.

### ¿Cómo copio a una carpeta que no está en el otro panel?

Pulse F5 y escriba la carpeta en el campo «Destino». Si no existe y copia varios elementos, se crea.

### ¿Puedo deshacer un borrado?

No con Ctrl+Z. Lo que envió a la papelera se recupera abriendo la papelera en un panel con Ctrl+F8 y eligiendo «Restaurar a su sitio», o desde la papelera de Windows. Lo eliminado definitivamente no se puede recuperar.

### ¿Por qué en una unidad de red se elimina sin papelera?

Windows no tiene papelera en las unidades de red ni en muchas extraíbles. zCommander le avisa antes y le deja cancelar.

### ¿Se pueden abrir archivos RAR?

Sí, desde la versión 2.0: Intro entra en un RAR como en una carpeta, también en los de varias partes. Los RAR cifrados necesitan 7-Zip instalado en el equipo (capítulo «Comprimidos»). Crear RAR no se puede.

### ¿Cómo cambio una tecla?

En el menú Opciones, «Mapa de teclas». Elija la orden, pulse «Cambiar» y pulse la tecla nueva.

### ¿Cómo vuelvo a ver el asistente del principio?

En el menú Opciones, «Asistente de primer arranque».

### zCommander habla demasiado, o demasiado poco

Cambie «Detalle de los anuncios» en Preferencias, página «Accesibilidad»: breve, normal o detallado. El progreso de las operaciones se ajusta aparte en «Progreso de las operaciones por voz».

### ¿Qué ha cambiado en esta versión?

En el menú Ayuda, «Novedades de la versión».

### ¿Cómo desactivo los sonidos?

Pulse Ctrl+F11. Para quitar solo algunos, desmárquelos en Preferencias, página «Sonidos».

### ¿Qué significa este sonido?

En el menú Ayuda, «Mapa de sonidos» le deja escuchar cada sonido con su nombre y cuándo suena. Todo lo que suena se dice también: Ctrl+Mayús+U repite el último anuncio.

### ¿Cómo paso mi configuración a otro equipo?

Cree una copia de seguridad con las contraseñas cifradas con una contraseña de la copia y restáurela en el otro equipo (capítulo «Copias de seguridad y perfiles»). Las contraseñas de las unidades de red de Windows hay que escribirlas de nuevo.

### ¿Cómo hago que zCommander se parezca a Total Commander?

En el menú Opciones, submenú Personalización, elija «Esquema de teclas» y el esquema Total Commander.

### Un complemento no me sirve. ¿Puedo quitarlo?

En el gestor de complementos (menú Complementos), elíjalo y pulse Espacio para inhabilitarlo. Los de serie no se desinstalan, pero inhabilitados no aparecen en los menús ni ocupan teclas.

## Solución de problemas

### zCommander no arranca

- Compruebe que ha extraído el ZIP completo y que no lo ejecuta desde dentro del ZIP.
- No lo ponga en Archivos de programa ni en otra carpeta donde no pueda escribir.
- Si Windows muestra el aviso de SmartScreen, elija «Más información» y después «Ejecutar de todas formas».
- Si sospecha de un complemento, arranque manteniendo pulsada la tecla Mayús: zCommander arranca sin complementos (modo seguro).
- Si sigue sin arrancar, busque el archivo arranque_fallido.log en la carpeta data\logs y envíelo a quien le dé soporte.

### Un complemento no funciona

- Abra el gestor de complementos (menú Complementos) y mire su estado. «Fuera de uso por errores» se arregla con «Volver a intentarlo» o reiniciando; «Incompatible» necesita una versión del complemento para esta versión de zCommander; «Sin aceptar» necesita que pulse «Aceptar».
- «Ver su registro» muestra lo que el complemento ha anotado en esta sesión. Inclúyalo si pide ayuda a su autor.
- Si un complemento dice «Falta el componente», abra Opciones, «Componentes externos», y restáurelo.

### La actualización volvió a la versión anterior

Si la versión nueva no arrancó bien, zCommander volvió solo a la anterior y lo dijo al arrancar. Esa versión ya no se le ofrecerá sola. El detalle está en data\logs\actualizacion.log; envíelo a quien le dé soporte. Puede volver a intentarlo más adelante desde el menú Ayuda, «Buscar actualizaciones».

### Un componente falla o falta

Abra Opciones, «Componentes externos». Si su origen dice «Falta» o «Dañado», use «Restaurar los componentes originales...». Si falló tras actualizarlo, use «Volver a la versión anterior».

### El lector no dice los anuncios de zCommander

- Compruebe en Preferencias, página «Accesibilidad», que «Anuncios por el lector de pantalla» está activada y que «Salida de los anuncios» está en «Automática».
- Con Narrador, pruebe «Siempre por notificaciones». Con NVDA o JAWS, pruebe «Siempre por el lector».
- Los errores y las preguntas se dicen siempre; si tampoco los oye, cierre y vuelva a abrir zCommander con el lector ya en marcha.

### El lector no dice «seleccionado» o repite filas al marcar

Pulse Ctrl+Mayús+S para saber cuántos hay marcados. Anote qué lector y qué versión usa, guarde el registro de la sesión (apartado «Registros para el soporte») y comuníquelo: es justo lo que más interesa comprobar en esta versión.

### Una tecla no hace nada

- Si oye el nombre de la orden en lugar de ejecutarse, está activo el modo de ayuda de teclado. Pulse Escape para salir.
- Algunas teclas solo funcionan con el foco en un panel. Pulse Tab o Escape para volver al panel y pruebe otra vez.
- Puede que su lector se quede la tecla. Pruebe la tecla alternativa (por ejemplo, Espacio en lugar de Insert) o la orden desde el menú.
- Puede que la haya cambiado en el mapa de teclas. Compruébelo en Opciones, «Mapa de teclas», o en la paleta de órdenes (Ctrl+E); la lista de teclas (Mayús+F1) solo muestra las de fábrica.

### Una copia no avanza

Pulse Ctrl+Mayús+T. Si dice que espera su decisión, pulse F12 y el botón «Atender la decisión pendiente». Si está en pausa, pulse «Reanudar». Si espera a otra operación del mismo disco, terminará cuando acabe esa.

### Una carpeta tarda mucho o una unidad no responde

Pulse Escape para cancelar la lectura: el panel se queda en la carpeta en la que estaba. Una unidad que no responde da error tras 10 segundos; puede cambiar ese tiempo en Preferencias, página «General».

### No se puede eliminar, abrir con o ver las propiedades de un archivo con una ruta muy larga

La papelera, el menú contextual de Windows, las propiedades y abrir con el programa asociado no admiten rutas muy largas. zCommander le avisa. Copiar, mover y eliminar definitivamente sí funcionan.

### No se puede crear un enlace simbólico

Windows exige privilegios o el modo de desarrollador. El diálogo de enlaces le explica cómo activarlo y le ofrece crear una unión (para carpetas) o un acceso directo.

### No suena nada

- Compruebe que los sonidos están activados: pulse Ctrl+F11 y escuche si dice «Sonidos activados».
- Compruebe en Preferencias, página «Sonidos», que el volumen no está a 0 y que el sonido que espera está marcado.
- zCommander usa el dispositivo de audio predeterminado de Windows y su volumen.

### Las preferencias no se guardan

zCommander no puede escribir en su carpeta. Muévala a una carpeta suya, como Documentos, fuera de Archivos de programa.

### Registros para el soporte

Cada sesión deja un registro en data\logs con un nombre como sesion_20261108_101500.log. Para abrir la carpeta, use el menú Opciones, «Abrir la carpeta de registros».

Si informa de un fallo, envíe:

1. El registro más reciente de data\logs, y arranque_fallido.log o fallo_nativo.log si existen.
2. La información del menú Ayuda, «Información para soporte», que se copia al portapapeles.
3. Qué hizo, qué esperaba y qué pasó, con el lector y la versión que usa.

### Restablecer los valores de fábrica

Desde zCommander: menú Opciones, «Restablecer los valores de fábrica».

Si zCommander no arranca o no puede llegar al menú:

1. Cierre zCommander.
2. En la carpeta data\config, cambie el nombre de settings.json, por ejemplo a settings.json.viejo.
3. Arranque zCommander: se abrirá con los valores de fábrica y el asistente.

Si el archivo de preferencias está dañado, zCommander lo aparta solo con un nombre como settings.json.corrupto-20261108_101500, intenta recuperar la copia settings.json.bak y, si tampoco sirve, arranca con los valores de fábrica.

Para empezar completamente de cero, borre toda la carpeta data\config. Perderá también favoritos, conexiones, contraseñas guardadas, menú de usuario y asociaciones.

## Referencia rápida de teclas

Las teclas más usadas, con el foco en un panel:

- Tab: cambiar de panel.
- Intro: entrar o abrir. Retroceso: carpeta superior.
- Espacio o Insert: marcar y bajar. Num + o Ctrl+Mayús+M: marcar por patrón.
- F3: ver. F4: editar. F5: copiar. F6: mover o renombrar. F7: crear carpeta. F8: eliminar.
- F9: menús. F10: salir. F12: operaciones en curso.
- Ctrl+E: paleta de órdenes. Mayús+F12: modo de ayuda de teclado. Ctrl+H: ayuda del control.

La lista completa está en la lista de teclas: pulse Mayús+F1, o abra el menú Ayuda y elija «Lista de teclas». También puede leerla en el archivo teclas.md de la carpeta data\docs.
