# Nubes

Con Nubes, cada cuenta de nube y cada servidor WebDAV es una unidad más del panel: se elige con Alt+F1 o Alt+F2, se entra en sus carpetas, se ven y editan sus archivos (F3 y F4), se copian (F5) y se mueven (F6) en los dos sentidos con los conflictos de siempre, se renombran, se eliminan (a la papelera de la nube si la tiene) y se busca en ellas (Alt+F7). El motor es rclone, que viene con zCommander.

## Cuatro formas de conectar

Para casi todas las nubes no hace falta crear claves ni identificadores: basta con iniciar sesión. En el asistente, la columna «Cómo se conecta» dice cuál de estas cuatro formas usa cada servicio, y la lista va en este orden:

1. **Iniciar sesión en el navegador**: Google Drive, OneDrive y SharePoint, Dropbox, Box, pCloud, Yandex Disk, kDrive, Jottacloud, HiDrive, y Nextcloud u ownCloud. Se escribe solo el nombre visible de la cuenta, se pulsa «Siguiente» y se autoriza en el navegador. En kDrive hay que copiar antes el número de la unidad (solo cifras), que aparece en la dirección web de kDrive detrás de «drive/» (se puede pegar la dirección entera). En Jottacloud se elige antes el servicio (Jottacloud o una de sus marcas blancas, como Telia, Elgiganten o MediaMarkt); con esta forma de iniciar sesión solo puede haber una sesión activa en el equipo: si conecta otra cuenta de Jottacloud o usa a la vez el programa oficial, las sesiones se invalidan y hay que volver a autorizar.
2. **Correo y contraseña**: Mega (correo, contraseña y, si la tiene, el código de verificación; antes hay que haber entrado una vez en mega.nz con el navegador), Koofr y Mail.ru (con una contraseña de aplicación, no la normal: el asistente tiene un botón que abre la página donde se crea), Internxt (si tiene verificación en dos pasos, el código se pide después), OpenDrive, cualquier servidor WebDAV y SFTP.
3. **Carpeta del programa oficial**: si tiene instalado el programa de OneDrive, Dropbox, Google Drive para escritorio, iCloud para Windows, Box Drive, pCloud Drive, Proton Drive o Synology Drive, su carpeta se usa como un disco más, sin iniciar sesión en zCommander. Se explica más abajo.
4. **Avanzado (claves propias)**: Amazon S3 y compatibles (Cloudflare R2, Wasabi, MEGA S4, IDrive e2...), Backblaze B2, Filen y «Otro servicio de rclone (avanzado)», que admite cualquiera de los más de 70 tipos de rclone.

Proton Drive e iCloud Drive por rclone son integraciones experimentales: solo salen en la lista si activa «Mostrar los servicios experimentales». Para ellas, la vía recomendada es la carpeta de su programa oficial.

### Google Drive

rclone retira durante 2026 el identificador compartido con el que se conecta a Google. Por eso, al elegir Google Drive y pulsar «Siguiente», zCommander pregunta cómo conectar:

1. **Usar la carpeta de Google Drive para escritorio** (solo si está instalado; normalmente la unidad G:). No caduca y no pide nada.
2. **Iniciar sesión con el identificador de rclone (puede dejar de funcionar en 2026)**. Es lo más sencillo hoy: se autoriza en el navegador y se contesta si la cuenta será una unidad compartida (No, para Mi unidad). Si un día deja de funcionar, la cuenta pedirá volver a autorizar y habrá que usar una de las otras dos formas.
3. **Usar mi propio identificador (avanzado)**: lo explica la [guía para conectar Google Drive](google-drive.md).

zCommander no registra una aplicación propia en Google ni en Microsoft.

### Opciones avanzadas

En casi todos los servicios de navegador (no en Jottacloud, ni en Nextcloud u ownCloud, que tienen su propio paso), el botón «Opciones avanzadas...» de los datos de la cuenta tiene el identificador de cliente propio (y su secreto), por si su organización lo exige, y la casilla «Autorizar desde otro equipo (este no tiene navegador)», que da una orden de rclone para ejecutarla en otro equipo y un campo para pegar lo que escriba. Normalmente no hace falta nada de esto.

## Carpetas de los programas oficiales

zCommander busca en el registro de Windows y en las carpetas habituales las carpetas que crean los programas oficiales de OneDrive (personal y de empresa), Dropbox, Google Drive para escritorio, iCloud para Windows, Box Drive, pCloud Drive, Proton Drive y Synology Drive. Solo busca dónde están: nunca lee ni usa las contraseñas o las fichas de acceso de esos programas.

- De fábrica, todas las carpetas encontradas salen ya en el selector de unidades (Alt+F1 y Alt+F2), sin hacer nada.
- La primera vez que abre «Añadir una cuenta de nube...» con carpetas nuevas, el asistente empieza diciendo, por ejemplo, «Este equipo ya tiene OneDrive e iCloud Drive. ¿Usar sus carpetas sin iniciar sesión?». La lista tiene una casilla por carpeta (Espacio la marca o la desmarca). «Usar estas carpetas» guarda la elección y termina; «Añadir además una cuenta de nube...» la guarda y sigue con la lista de servicios.
- Cada carpeta sale en el selector con su nombre, «carpeta del programa oficial» y su ruta, y se abre como un disco más. Las que desmarque en el asistente dejan de salir.
- Para volver a elegir, en la lista de servicios del asistente elija «Carpeta de un programa oficial (OneDrive, Dropbox, Google Drive, iCloud...)». Para ocultarlas todas, desactive «Mostrar en el selector de unidades las carpetas de los programas oficiales de nube» en la página Cuentas de las preferencias.

Qué se encuentra: OneDrive por su registro y sus variables de entorno; Dropbox por su archivo info.json; Google Drive para escritorio por su letra de unidad (en modo réplica, sin letra, no se encuentra: añada esa carpeta a favoritos); iCloud por su carpeta iCloudDrive; Box Drive por su carpeta Box, solo si el programa está instalado; pCloud Drive por la etiqueta de su unidad; y Proton Drive y Synology Drive solo si Windows los tiene en su registro de sincronización (Synology Drive, solo con la sincronización bajo demanda). Una carpeta de red que no responde se salta sin esperar.

Limitaciones: hace falta el programa oficial instalado y con la sesión iniciada; desde la carpeta no hay enlaces para compartir, papelera de la nube ni espacio de la cuenta; y abrir un archivo que solo está en la nube hace que el programa lo descargue primero, lo que puede tardar. Si necesita esas funciones, añada además la cuenta de nube.

## Órdenes

Están en el menú Complementos, submenú «Nubes y NAS», submenú «Nubes», y en la paleta de órdenes. Solo «Cuentas de nube...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

### Cuentas

- **Cuentas de nube...** (Alt+F11): ventana con las cuentas, su servicio, su motor, su estado («Conectada», «Volver a autorizar», «Sin comprobar», «Volver a configurar») y su espacio.
- **Añadir una cuenta de nube...**: asistente. Si hay carpetas nuevas de programas oficiales, primero las ofrece. Después se elige el servicio (con búsqueda; la columna «Cómo se conecta» dice qué pedirá), se escribe el nombre visible y, solo si el servicio lo pide, el correo y la contraseña u otros datos; se autoriza en el navegador si hace falta y se comprueba la cuenta. Si rclone hace alguna pregunta más, sale en español cuando es una de las habituales (tipo de conexión de OneDrive, unidad, código de verificación...).
- **Conectar Nextcloud u ownCloud...**: se escribe la dirección del servidor, se autoriza en el navegador y zCommander recibe una contraseña de aplicación (Login Flow v2). Nunca se teclea la contraseña real.
- **Volver a autorizar la cuenta...**: para cuando la autorización caducó o se revocó.
- **Guía para conectar Google Drive**: las formas de conectar Google Drive y, si lo necesita, los pasos para crear su identificador de cliente propio.

### Enlaces, papelera y espacio

- **Copiar un enlace para compartir...**: crea un enlace del elemento del cursor (con caducidad si el servicio la admite) y lo copia.
- **Quitar el enlace compartido**: deja de compartir el elemento del cursor (con confirmación).
- **Vaciar la papelera de la nube...**: con confirmación; el foco empieza en «Cancelar».
- **Espacio de la nube**: dice el espacio usado, el libre y el de la papelera.

### Sincronizar y comprobar

- **Sincronizar con la nube...**: deja el destino igual que el origen. Primero muestra una simulación con la lista de cambios; si lo confirma, lo hace como una operación con progreso. Puede guardar lo borrado o sobrescrito en una carpeta de copias.
- **Emparejar carpetas (en los dos sentidos)...**: mantiene dos carpetas iguales en los dos sentidos. Es avanzada: muestra una simulación, para si se fuera a borrar más del porcentaje elegido y al terminar dice los conflictos.
- **Comprobar carpetas...**: compara dos carpetas por tamaño y suma y muestra las diferencias en una lista.
- **Buscar nombres duplicados...**: Google Drive y Mega permiten dos archivos con el mismo nombre. Lista los duplicados, simula la acción elegida (conservar el más nuevo, renombrar...) y la aplica si lo confirma.

### Carpetas cifradas, uniones y unidades

- **Crear una carpeta cifrada en la nube...**: cifra en este equipo el contenido y los nombres de una carpeta de otra cuenta. Sin la contraseña y la sal no hay recuperación posible.
- **Unir varias cuentas en una unidad...**: mezcla varias cuentas en una sola (el espacio se suma) o pone cada una en su carpeta.
- **Montar como letra de unidad...**: necesita WinFsp, que instala usted (zCommander no lo instala). La unidad existe mientras zCommander está abierto.
- **Unidades montadas...**: lista y desmonta (avisa si quedan subidas pendientes).

### Compartir en la red y velocidad

- **Compartir en la red...**: comparte una cuenta o la carpeta del panel por WebDAV, SFTP, HTTP o DLNA. Por defecto solo en este equipo; abrirlo a la red local pide confirmación.
- **Carpetas compartidas por zCommander...**: lista lo compartido; permite copiar la dirección y dejar de compartir.
- **Pausar o reanudar los límites de velocidad**: quita o vuelve a poner los límites de la configuración.

## Teclas dentro de las ventanas

- Asistente «Añadir una cuenta de nube»: en la lista de servicios, escribir en «Buscar un servicio» filtra la lista e Intro pasa al siguiente paso; en la lista de carpetas de los programas oficiales, Espacio marca o desmarca cada carpeta.
- Ventana «Cuentas de nube»: Intro abre la cuenta elegida en el panel activo y Supr la elimina (con confirmación). Botones: «Abrir», «Añadir...», «Propiedades...», «Reconectar...», «Eliminar...», «Espacio» y «Cerrar».
- Ventana «Unidades montadas»: Supr desmonta la unidad elegida.
- Ventana «Carpetas compartidas por zCommander»: Supr deja de compartir lo elegido.
- En todas las ventanas de Nubes: Escape cierra o cancela, Ctrl+H explica el control enfocado y F1 abre esta ayuda.
- En las listas, Flecha izquierda y Flecha derecha recorren las columnas.

## Copiar y mover entre nubes

F5 y F6 entre dos paneles de nube no necesitan órdenes especiales:

- Dentro de la misma cuenta se copia o se mueve en el servidor.
- Entre dos cuentas del mismo servicio se puede copiar en el servidor (preferencia «Copiar en el servidor entre cuentas del mismo servicio»).
- Entre servicios distintos, rclone hace de puente sin pasar por el disco.

Muchos archivos pequeños se copian en un solo trabajo, varios a la vez.

## Preferencias

En Preferencias, Complementos, Nubes:

- Página Motor de nubes: «Cuándo arrancar el motor de nubes» (al usar una cuenta por primera vez, por defecto, o al iniciar zCommander), «Transferencias simultáneas» (4), «Reintentos de cada operación» (3), «Registro detallado de rclone (nivel INFO)» y «Mostrar los servicios experimentales».
- Página Velocidad: «Límite de subida en KiB/s (0 sin límite)», «Límite de bajada en KiB/s (0 sin límite)» y «Horario de límites (formato de rclone)».
- Página Cuentas: «Segundos que se recuerdan los listados» (30), «Las cuentas nuevas borran a la papelera del servicio» (activada), «Formato de los documentos de Google en cuentas nuevas», «Copiar en el servidor entre cuentas del mismo servicio» (desactivada), «Compartir en la red solo en este equipo salvo confirmación» (activada) y «Mostrar en el selector de unidades las carpetas de los programas oficiales de nube» (activada).

Cada cuenta tiene además sus propiedades («Propiedades...» en la ventana «Cuentas de nube»): carpeta inicial, solo lectura, papelera, caché, límites propios, tamaño de fragmento, opciones del servicio e identificador de cliente propio.

## Sonidos

- **Cuenta de nube conectada**: al añadir una cuenta y comprobarla.
- **Cuenta de nube eliminada**: al eliminar una cuenta.
- **Esperando la autorización**: al empezar a esperar la autorización en el navegador.
- **Autorización recibida**: al llegar la autorización del navegador.
- **Sincronización terminada**: al terminar de sincronizar o de emparejar carpetas.
- **Unidad de nube montada**: al montar una cuenta como letra de unidad.
- **Motor de nubes detenido**: si el motor de nubes (rclone) se detiene sin que se le pida.

## Seguridad y privacidad

- Las fichas de acceso de las cuentas están en `data/config/rclone.conf`, cifrado con una contraseña aleatoria que se guarda protegida por Windows (DPAPI). Si copia la carpeta a otro equipo o usuario, tendrá que volver a añadir las cuentas.
- Las contraseñas de WebDAV y los secretos de cliente se guardan cifrados del mismo modo; nunca en archivos de texto ni en el registro.
- El motor rclone escucha solo en este equipo, con usuario y contraseña aleatorios nuevos en cada arranque, y no escribe ningún registro propio en disco.
- Proton Drive e iCloud Drive son integraciones no oficiales.

## Licencias

El montaje usa WinFsp - Windows File System Proxy, Copyright (C) Bill Zissimopoulos. Más información en el [proyecto WinFsp en GitHub](https://github.com/winfsp/winfsp).
