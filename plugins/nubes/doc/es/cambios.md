# Novedades de Nubes

## 1.1.0

- Conectar sin claves: el asistente agrupa los servicios por cómo se conectan (columna «Cómo se conecta»: iniciar sesión en el navegador, correo y contraseña, carpeta del programa oficial o avanzado). En Google Drive, OneDrive, Dropbox, Box y los demás de navegador basta con el nombre visible y «Siguiente»; el identificador de cliente propio y «Autorizar desde otro equipo» pasan al botón «Opciones avanzadas...».
- Carpetas de los programas oficiales (OneDrive, Dropbox, Google Drive para escritorio, iCloud, Box, pCloud, Proton Drive y Synology Drive): el asistente las ofrece al empezar y salen en el selector de unidades (Alt+F1 y Alt+F2) como un disco más. Preferencia nueva para ocultarlas.
- Google Drive pregunta cómo conectar: la carpeta de Google Drive para escritorio, el identificador de rclone (puede dejar de funcionar en 2026) o uno propio.
- Jottacloud y sus marcas blancas se conectan en el navegador (antes pedían pegar un código); solo admiten una sesión activa por equipo. Volver a autorizar una cuenta de Jottacloud conserva su dispositivo y su punto de montaje. kDrive pide el número de la unidad, que rclone necesita (solo cifras; se puede pegar la dirección web).
- Las preguntas habituales de rclone salen en español (tipo de conexión de OneDrive, unidad, unidad compartida, códigos de verificación...).
- Corregido: tras responder a una pregunta de rclone, el alta volvía a preguntar si había navegador y podía intentar abrirlo por su cuenta.

## 1.0.0

- Primera versión: cuentas de nube como unidades del panel con rclone, WebDAV nativo y Nextcloud con Login Flow v2, asistente accesible con autorización en el navegador, sincronizar, emparejar, comprobar, duplicados, papelera, espacio, enlaces, carpetas cifradas, uniones, montaje con WinFsp, compartir en la red y límites de velocidad con horario.
