# Nubes

Con Nubes, cada cuenta de nube y cada servidor WebDAV es una unidad más del panel: se elige con Alt+F1 o Alt+F2, se entra en sus carpetas, se ven y editan sus archivos (F3 y F4), se copian (F5) y se mueven (F6) en los dos sentidos con los conflictos de siempre, se renombran, se eliminan (a la papelera de la nube si la tiene) y se busca en ellas (Alt+F7). El motor es rclone, que viene con zCommander.

## Servicios

Google Drive, OneDrive y SharePoint, Dropbox, Box, pCloud, Mega, Amazon S3 y compatibles (Cloudflare R2, Wasabi, MEGA S4, IDrive e2...), Backblaze B2, Yandex Disk, Koofr, kDrive, Jottacloud, Internxt, Filen, Mail.ru, HiDrive, OpenDrive, SFTP, WebDAV por rclone, Nextcloud y ownCloud, cualquier servidor WebDAV (sin rclone) y, como experimentales, Proton Drive e iCloud Drive.

La opción «Otro servicio de rclone (avanzado)» admite cualquiera de los más de 70 tipos de rclone.

Google Drive necesita un identificador de cliente propio: lo explica la [guía para conectar Google Drive](google-drive.md).

## Órdenes

Están en el menú Complementos, submenú «Nubes y NAS», submenú «Nubes», y en la paleta de órdenes. Solo «Cuentas de nube...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

### Cuentas

- **Cuentas de nube...** (Alt+F11): ventana con las cuentas, su servicio, su motor, su estado («Conectada», «Volver a autorizar», «Sin comprobar», «Volver a configurar») y su espacio.
- **Añadir una cuenta de nube...**: asistente. Se elige el servicio (con búsqueda), se escriben el nombre visible y los datos, se autoriza en el navegador si hace falta y se comprueba la cuenta.
- **Conectar Nextcloud u ownCloud...**: se escribe la dirección del servidor, se autoriza en el navegador y zCommander recibe una contraseña de aplicación (Login Flow v2). Nunca se teclea la contraseña real.
- **Volver a autorizar la cuenta...**: para cuando la autorización caducó o se revocó.
- **Guía para conectar Google Drive**: pasos para crear su identificador de cliente propio.

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
- Página Cuentas: «Segundos que se recuerdan los listados» (30), «Las cuentas nuevas borran a la papelera del servicio» (activada), «Formato de los documentos de Google en cuentas nuevas», «Copiar en el servidor entre cuentas del mismo servicio» (desactivada) y «Compartir en la red solo en este equipo salvo confirmación» (activada).

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
