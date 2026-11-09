# Guía para conectar Google Drive

Google Drive necesita que usted cree su propio «identificador de cliente» (client id) en la consola de Google. El identificador compartido de rclone se retira durante 2026 y dejará de funcionar sin previo aviso. zCommander no registra una aplicación propia en Google. Esta guía explica los pasos uno a uno; hace falta hacerlo una sola vez y vale para todas sus cuentas de Google Drive.

Los nombres de los botones están en inglés porque así aparecen en la consola de Google si su cuenta está en inglés; si la tiene en español, verá su traducción. La consola es una página web compleja: con NVDA o JAWS conviene moverse por encabezados (H), por botones (B) y por campos de formulario (F), y usar la búsqueda del navegador (Ctrl+F) para encontrar cada texto.

## Antes de empezar

- Necesita una cuenta de Google (puede ser la misma de su Drive o cualquier otra).
- Tenga a mano zCommander con el asistente «Añadir una cuenta de nube» abierto en Google Drive, o abra estos pasos con la orden «Guía para conectar Google Drive» del menú Complementos, submenú «Nubes y NAS», submenú «Nubes».

## Paso 1: entrar en la consola y crear un proyecto

1. Abra en el navegador la [consola de Google Cloud](https://console.cloud.google.com/) e inicie sesión.
2. Busque el selector de proyectos (un botón con el nombre del proyecto o «Select a project») y pulse «New project» («Proyecto nuevo»).
3. Escriba un nombre, por ejemplo «zCommander de Ana», y pulse «Create» («Crear»). Espere a que se cree y asegúrese de que es el proyecto elegido.

## Paso 2: activar la API de Google Drive

1. En el campo de búsqueda de la consola escriba «Google Drive API» y pulse Intro.
2. Entre en el resultado «Google Drive API» y pulse el botón «Enable» («Habilitar»).

## Paso 3: pantalla de consentimiento (público «Externo»)

1. Abra el menú de navegación y entre en «APIs & Services», «OAuth consent screen» (o «Google Auth Platform»).
2. Pulse «Get started» («Comenzar»). Escriba un nombre de aplicación (por ejemplo «zCommander») y su correo como correo de asistencia.
3. En «Audience» («Público») elija «External» («Externo»). Escriba su correo de contacto, acepte las condiciones y pulse «Create» («Crear»).

## Paso 4: ámbito de acceso a Drive

1. Entre en «Data Access» («Acceso a los datos») y pulse «Add or remove scopes» («Añadir o quitar permisos»).
2. Baje hasta el campo «Manually add scopes» («Añadir permisos manualmente») y escriba: https://www.googleapis.com/auth/drive
3. Pulse «Add to table» («Añadir a la tabla»), después «Update» («Actualizar») y por último «Save» («Guardar») al final de la página.

Si la cuenta de zCommander va a ser de solo lectura, puede usar en su lugar https://www.googleapis.com/auth/drive.readonly.

## Paso 5: crear el cliente «App de escritorio»

1. Entre en «Clients» («Clientes») o en «Overview» y pulse «Create OAuth client» («Crear cliente de OAuth»).
2. En «Application type» («Tipo de aplicación») elija «Desktop app» («Aplicación de escritorio») y pulse «Create».
3. La página muestra el «Client ID» (identificador de cliente) y el «Client secret» (secreto). Cópielos: cada uno tiene su propio botón de copiar. Guárdelos en un lugar seguro.

## Paso 6: publicar la aplicación (para que el acceso no caduque a los 7 días)

1. Entre en «Audience» («Público»), pulse «Publish app» («Publicar aplicación») y confirme.
2. Si el botón está desactivado, Google pide antes una página de inicio y una política de privacidad, aunque la aplicación sea solo para usted: entre en «Branding» («Imagen de marca»), rellene «Application home page» y «Application privacy policy link» (sirve una página gratuita propia) y «Authorized domains», guarde y vuelva a «Audience».
3. Mientras la aplicación esté en «Testing» («Pruebas»), añádase como usuario de prueba con «Add users»; en ese estado la autorización caduca a los 7 días y habría que volver a autorizar.

Al autorizar, Google puede avisar de que la aplicación no está verificada: es su propia aplicación, así que puede pulsar «Advanced» («Configuración avanzada») y «Go to ... (unsafe)» («Ir a ...»).

## Paso 7: volver a zCommander

1. En el asistente, en los datos de Google Drive, pegue el identificador en «Identificador de cliente (client id)» y el secreto en «Secreto del cliente».
2. Pulse «Siguiente» y después «Abrir el navegador». Inicie sesión con la cuenta de Google Drive que quiere usar y conceda el acceso.
3. Vuelva a zCommander: detecta solo la autorización, suena un aviso y dice el espacio de la cuenta.

El secreto se guarda cifrado en este equipo. Si cambia de equipo, tendrá que volver a autorizar la cuenta.

## Alternativa sin identificador: Google Drive para escritorio

Si tiene instalado Google Drive para escritorio, su unidad (normalmente G:) ya se puede usar en zCommander como cualquier disco. El asistente la ofrece si la encuentra; en ese caso no se crea ninguna cuenta de rclone.
