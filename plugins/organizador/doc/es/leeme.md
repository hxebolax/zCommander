# Organizador y renombrado por metadatos

Ordena archivos en carpetas y les pone nombre según su contenido, con plantillas.

## Órdenes

- **Organizar por metadatos...** (menú Complementos, submenú «Orden y limpieza del disco», submenú «Organizador y renombrado por metadatos», y paleta de órdenes): abre el diálogo «Organizar por metadatos». No tiene tecla de fábrica; se le puede dar una en el mapa de teclas.

Trabaja con los elementos marcados del panel activo, o con el del cursor; de las carpetas se toman todos los archivos que tienen dentro.

## El diálogo Organizar por metadatos

- **Plantillas guardadas** (Alt+G): rellena las dos plantillas siguientes.
- **Plantilla de las carpetas** (Alt+T): cada tramo separado por una barra inversa es una carpeta, dentro de la carpeta base. Por ejemplo `Fotos\[EXIF:fecha:AAAA]\[EXIF:fecha:MM]`, `Música\[MP3:artista]\[MP3:album]` o `Documentos\[Y]`.
- **Plantilla del nombre del archivo** (Alt+N): el nombre nuevo sin la extensión, que se conserva. `[N]` lo deja igual; `[MP3:pista] - [MP3:titulo]` lo cambia por la pista y el título.
- **Carpeta base** (Alt+B): donde se crean las carpetas; se propone la del otro panel.
- **Acción** (Alt+A): mover o copiar.
- **Resumen** (Alt+R).
- **Vista previa** (Alt+P): lista con Nombre actual, Destino nuevo y Estado. Se calcula sola al escribir; el botón **Actualizar la vista previa** (Alt+Z) la vuelve a calcular.
- Botones **Guardar como plantilla...** (Alt+L), **Organizar** (Alt+O) y **Cancelar** (Alt+C o Escape).

F1 abre esta ayuda.

### Marcadores de las plantillas

- Los del renombrado múltiple: `[N]` nombre, `[E]` extensión, `[P]` carpeta, `[Y]` año, `[M]` mes y `[D]` día de modificación, `[C]` contador...
- Los de los complementos: `[EXIF:…]` de Imágenes y `[MP3:…]` de Metadatos y etiquetas de audio.

Si un marcador no da nada (una foto sin fecha EXIF), la carpeta toma el nombre de la preferencia «Nombre de la carpeta cuando falta el dato» («Sin fecha»).

### Estados de la vista previa

- «Listo»: se moverá o copiará.
- «Duplicado»: dos archivos irían al mismo sitio; no se mueve ninguno de los dos.
- «Ya existe», «Sin cambios» y «Error»: no se tocan.

**Organizar** mueve o copia solo los «Listo», como una operación con progreso y con deshacer (Ctrl+Z en el panel): deshacer devuelve los archivos y quita las carpetas creadas si quedaron vacías.

**Guardar como plantilla...** guarda las dos plantillas con un nombre («Nombre de la plantilla»).

## Preferencias

En Preferencias, Complementos, Organizador y renombrado por metadatos, General:

- **Nombre de la carpeta cuando falta el dato**: «Sin fecha» por defecto.
- **Acción por defecto**: mover (por defecto) o copiar.
