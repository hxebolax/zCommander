# Reconocimiento de texto, OCR

Reconoce el texto de imágenes y de PDF escaneados con el motor de reconocimiento óptico de caracteres (OCR) que trae Windows 10 y 11. Funciona sin Internet: nada sale del equipo.

## Órdenes

Están en el menú Complementos, submenú «Documentos y datos», submenú «Reconocimiento de texto, OCR», y en la paleta de órdenes. Solo «Reconocer el texto» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

- **Reconocer el texto** (Ctrl+Mayús+F3): reconoce la imagen o el PDF del cursor y muestra el texto en el visor interno. En un PDF, cada página es una sección «Página N de M»: F6 va a la siguiente y Ctrl+P a una página. Desde el visor se puede seleccionar y copiar el texto.
- **Reconocer los marcados a archivos de texto...**: reconoce cada imagen o PDF marcado y guarda su texto en un `.txt` con el mismo nombre, junto al archivo (o en la carpeta de salida de las preferencias). Un `.txt` que ya existe no se sustituye, salvo que lo diga la preferencia. Es una operación del motor: la ventana de operaciones (F12) la muestra y se puede pausar o cancelar.
- **Reconocer la imagen del portapapeles**: reconoce la imagen copiada (por ejemplo, una captura de pantalla).
- **Reconocer la ventana en primer plano**: captura la ventana activa y reconoce su texto; sirve para programas inaccesibles. Lo más útil es darle una tecla global (Preferencias, página Personalización, botón «Teclas globales...»): así funciona con zCommander en segundo plano y reconoce la ventana del otro programa.

Al terminar suena «Reconocimiento de texto terminado» y se dice cuántas líneas se han reconocido.

## Imágenes admitidas

PNG, JPEG, BMP, GIF, TIFF, JPEG XR, ICO, HEIC y WebP (las dos últimas, si Windows tiene sus extensiones).

## Idioma del reconocimiento

Windows reconoce los idiomas que tiene instalados con el reconocimiento de texto. Por defecto se usa el de Windows.

Para elegir otro:

1. Abra Preferencias, Complementos, Reconocimiento de texto, OCR.
2. Pulse el botón «Abrir la configuración avanzada...».
3. En el diálogo «Reconocimiento de texto: idioma», elija en «Idioma de reconocimiento» (Alt+I) uno de los idiomas instalados. El texto «Cómo instalar más idiomas» (Alt+M) explica cómo añadir otros.

Para instalar más idiomas en Windows:

1. Abra Configuración de Windows, Hora e idioma, Idioma y región, Agregar un idioma.
2. Elija el idioma y marque «Reconocimiento óptico de caracteres» (o «Escritura a mano y OCR»).

Si Windows no tiene ninguno, el complemento lo dice al intentar reconocer.

## Preferencias

En Preferencias, Complementos, Reconocimiento de texto, OCR, General:

- **Escala de las páginas de PDF**: de 1 a 4 (2 por defecto). Más escala reconoce mejor la letra pequeña y tarda más.
- **Carpeta de salida de los lotes**: vacía por defecto, que significa junto a cada archivo.
- **Sustituir los archivos de texto que ya existan**: desactivada por defecto.
- **Motor**: automático, pywinrt o Windows PowerShell. Los dos usan el mismo OCR de Windows; el automático usa el primero que funcione y lo apunta en el registro.

## Sonidos

- **Reconocimiento de texto terminado**: al terminar un reconocimiento (del archivo, del portapapeles, de la ventana o de un lote).

## Licencias

Usa [pywinrt en GitHub](https://github.com/pywinrt/pywinrt) 4.1.0 (licencia MIT) y typing_extensions 4.16.0 (licencia PSF-2.0); sus textos están en la carpeta `lib`. Si pywinrt no funciona, usa el guion `recursos/ocr.ps1` con Windows PowerShell.
