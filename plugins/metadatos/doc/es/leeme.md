# Metadatos y etiquetas de audio

Lee y edita las etiquetas (artista, título, álbum, pista, año y género) y la portada de los archivos MP3, FLAC, M4A, OGG, Opus, WMA y WAV. Usa la biblioteca mutagen (GPL-2.0 o posterior).

## Órdenes

Están en el menú Complementos, submenú «Multimedia», submenú «Metadatos y etiquetas de audio», y en la paleta de órdenes. Trabajan con los archivos marcados del panel o, si no hay ninguno, con el del cursor. Todas las que cambian archivos son operaciones (progreso, pausa, ventana de operaciones con F12) y se pueden deshacer durante la sesión con la orden Deshacer de zCommander.

- **Editar las etiquetas...** (Ctrl+Mayús+F2): formulario con Artista, Título, Álbum, Pista, Año y Género. Con un archivo, muestra sus valores y su «Información del archivo» (duración, tasa de bits, frecuencia, canales, portada); borrar un campo quita esa etiqueta. Con varios, cada campo empieza en «(sin cambio)»: lo que deje así no se toca en ningún archivo.
- **Etiquetas desde el nombre...**: rellena las etiquetas a partir del nombre del archivo con una **Máscara** (Alt+M), como `[pista] - [artista] - [titulo]`. Campos: `[pista]`, `[artista]`, `[titulo]`, `[album]`, `[anio]`, `[genero]`; `[*]` salta un trozo. La **Vista previa** (Alt+V) dice qué saldrá de cada nombre o «No encaja».
- **Numerar las pistas**: numera las pistas marcadas en el orden del panel (1/12, 2/12...). Hacen falta al menos dos.
- **Quitar las etiquetas...**: quita todas las etiquetas y la portada (pregunta antes; «No» es lo predeterminado).
- **Portada...**: «Añadir o cambiar la portada...» (JPEG o PNG), «Extraer la portada...» a un archivo o «Quitar la portada».
- **Exportar la lista de pistas...**: guarda la lista en texto (una línea por pista con su duración) o en CSV con punto y coma (lo abre Excel).

Solo «Editar las etiquetas...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

## Columnas, información y renombrado

- Columnas: Artista, Título, Álbum, Pista, Año, Género, Duración, Tasa de bits (kb/s), Frecuencia (Hz), Canales y Portada (Sí o No). Se eligen en el diálogo de columnas; al activarse, el complemento propone el conjunto «Música», que se aplica en las carpetas con mayoría de archivos de audio.
- La información del elemento (Ctrl+Mayús+I) añade las etiquetas y los datos técnicos.
- Renombrado múltiple: `[MP3:artista]`, `[MP3:titulo]`, `[MP3:album]`, `[MP3:pista]` (con dos cifras), `[MP3:anio]` y `[MP3:genero]`. Valen para todos los formatos de audio que lee, no solo MP3. Los marcadores de zCommander (`[t]` la hora, `[y]` el año con dos cifras...) no cambian.

## Deshacer los cambios

Antes de cambiar un archivo se guarda una copia en la carpeta de datos del complemento (nunca junto al archivo). Deshacer (Ctrl+Z) vuelve a poner la copia si el archivo no ha cambiado desde entonces.

Las copias se borran al cerrar zCommander: deshacer solo vale durante la sesión. Los archivos de más de 512 MB se cambian sin copia y no se pueden deshacer.

## Preferencias

En Preferencias, Complementos, Metadatos y etiquetas de audio, General:

- **Versión de ID3 al guardar MP3**: 2.3 (la que leen todos los reproductores; por defecto) o 2.4.
- **Conservar la fecha de los archivos al cambiar sus etiquetas**: activada por defecto.
- **Proponer el conjunto de columnas «Música»**: activada por defecto.

## Sonidos

- **Etiquetas guardadas**: al terminar de guardar un cambio.
