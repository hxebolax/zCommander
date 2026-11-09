# Notas, comentarios y etiquetas

Pone comentarios en archivos y carpetas, notas en las carpetas y etiquetas con nombre y color.

## Órdenes

Están en el menú Complementos, submenú «Orden y limpieza del disco», submenú «Notas, comentarios y etiquetas», y en la paleta de órdenes. Solo «Comentario o nota...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

- **Comentario o nota...** (Ctrl+N): edita el comentario del elemento del cursor o, sobre «..», la nota de la carpeta en la que está.
- **Leer la nota de la carpeta**: lee la nota de la carpeta actual.
- **Etiquetas...**: pone o quita etiquetas a los elementos de trabajo.
- **Buscar por etiqueta o comentario...**: busca en una carpeta y sus subcarpetas.

## Comentarios y notas de carpeta

El diálogo tiene el campo **Texto del comentario** (o **Texto de la nota**, Alt+T), que puede tener varias líneas, y los botones **Guardar** (Alt+G), **Quitar** (Alt+Q) y **Cancelar** (Alt+C). «Guardar» con el texto vacío o «Quitar» borran el comentario.

Los comentarios se guardan en el archivo `descript.ion` de cada carpeta, el mismo que usan Total Commander y Double Commander, así que se ven también allí. La nota de una carpeta es su comentario en el `descript.ion` de la carpeta superior. Donde no se puede escribir (carpetas de solo lectura, unidades de red sin permiso, la raíz de una unidad) se guardan en la base de zCommander, y se dice.

Al entrar en una carpeta con nota se dice «Esta carpeta tiene una nota» y suena su sonido. La orden «Leer la nota de la carpeta» la lee.

## El diálogo Etiquetas

- **Etiquetas de** los elementos elegidos (Alt+E): lista de casillas con cada etiqueta y su color en texto («Urgente (rojo)»). Espacio pone o quita la etiqueta, Ctrl+A marca todas y Ctrl+Mayús+A las desmarca.
- **Nueva etiqueta...** (Alt+N): crea una con nombre y color, y la deja marcada.
- **Aceptar** y **Cancelar**.

Al aceptar, las etiquetas marcadas se ponen a todos los elementos; las que tenían todos y desmarque se quitan. El color nunca es la única información: siempre se dice. F1 abre esta ayuda.

## Columnas

Añada en las columnas del panel **Comentario** (la primera línea) y **Etiquetas**.

## Buscar por etiqueta o comentario

El diálogo tiene:

- **Texto que contiene el comentario** (Alt+T).
- **Etiqueta** (Alt+E).
- **Dónde buscar** (Alt+D).
- **Incluir subcarpetas** (Alt+S).
- Botones **Buscar** (Alt+B) y **Cancelar**.

Busca lo que tiene un comentario con un texto, una etiqueta o las dos cosas. Sin texto y con una etiqueta funciona como filtro por etiqueta. Los resultados salen como lista en el panel.

## Al copiar y mover

Si está activada la preferencia, el comentario y las etiquetas van con el archivo cuando se copia o se mueve dentro de zCommander (también con el nombre que reciba por un conflicto).

## Preferencias

En Preferencias, Complementos, Notas, comentarios y etiquetas, General:

- **Dónde se guardan los comentarios**: en `descript.ion` junto a los archivos (por defecto) o en la base de zCommander.
- **Decir al entrar si la carpeta tiene nota**: activada por defecto.
- **Llevar comentarios y etiquetas al copiar y mover**: activada por defecto.

## Sonidos

- **Nota de carpeta**: al entrar en una carpeta que tiene una nota.
