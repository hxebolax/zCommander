# Editor hexadecimal accesible

Ve y edita los bytes de cualquier archivo, también muy grande: solo se lee del disco lo que se ve, y los cambios se guardan aparte hasta que se guarda.

## Órdenes

- **Ver y editar en hexadecimal** (Ctrl+Mayús+F4; menú Complementos, submenú «Documentos y datos», submenú «Editor hexadecimal accesible», y paleta de órdenes): abre el archivo del cursor en el editor.

Los archivos de dentro de un comprimido o de un servidor se abren en solo lectura; «Guardar como» guarda una copia en el disco.

## La ventana del editor

- **Volcado**: las líneas visibles, como «00000010  48 6F 6C 61 ...  Hola...»: desplazamiento, bytes en hexadecimal y su texto.
- **Inspector**: los bytes del cursor leídos como enteros de 8, 16, 32 y 64 bits con y sin signo, coma flotante de 32 y 64 bits, carácter UTF-8 y UTF-16, fecha Unix y FILETIME.
- **Barra de estado**: desplazamiento, modo, columna, orden de bytes, selección y si hay cambios.
- Menús **Archivo**, **Edición** y **Ver**, con todas las órdenes y sus teclas.

Escape cierra la ventana; si hay cambios, pregunta: «Guardar», «Descartar los cambios» o «Cancelar». F1 abre esta ayuda y Ctrl+H dice la ayuda del control enfocado.

## Moverse por el archivo

El cursor de bytes lo lleva el editor. Cada movimiento dice, por ejemplo, «Desplazamiento 0x1A, 4F, letra O» (o, con la preferencia, también el decimal y el binario).

- Flecha izquierda y Flecha derecha: un byte. Flecha arriba y Flecha abajo: una línea.
- Inicio y Fin: principio y fin de la línea. Ctrl+Inicio y Ctrl+Fin: principio y fin del archivo.
- Re Pág y Av Pág: una pantalla.
- Con Mayús, las mismas teclas seleccionan.
- Tab: cambia entre la columna hexadecimal y la de texto.
- Ctrl+G: ir a un desplazamiento: decimal (1234), hexadecimal (0x4D2), relativo (+16, -16) o un porcentaje (50%).

## Editar bytes

- En la columna hexadecimal, dos dígitos cambian el byte; un carácter que no es un dígito hexadecimal suena y se dice.
- En la columna de texto, cada carácter se escribe con la codificación de la columna de texto.
- Insert alterna insertar y sobrescribir. Con NVDA, pulse Insert dos veces seguidas, porque la primera pulsación la usa el lector. En modo insertar, Supr y Retroceso borran.
- Ctrl+Z deshace y Ctrl+Y rehace, sin límite hasta que se guarda.
- Ctrl+C copia la selección como hexadecimal («48 6F 6C 61») y Ctrl+Mayús+C como texto. Ctrl+V pega: en la columna hexadecimal, si lo copiado son pares hexadecimales, esos bytes; si no, el texto.

## Buscar y reemplazar

- Ctrl+F busca bytes en hexadecimal («4F 6B ?? 00», con ?? como comodín) o texto. F3 busca el siguiente y Mayús+F3 el anterior.
- Ctrl+R reemplaza: «Reemplazar el siguiente» o «Reemplazar todos» (se deshace de una vez). El reemplazo puede tener otro tamaño.

La búsqueda recorre el archivo entero por bloques en segundo plano.

## Inspector y orden de bytes

- Ctrl+I dice el inspector entero.
- Ctrl+Mayús+I dice la barra de estado.
- Ctrl+E cambia entre little endian y big endian.

## Guardar

Ctrl+S o F2 guardan; Mayús+F2 guarda como. Se escribe primero un temporal en la misma carpeta y después sustituye al archivo, así nunca queda a medias. Si el archivo cambió en el disco desde que lo abrió, pregunta antes. Tras guardar, Deshacer empieza de nuevo.

## Preferencias

En Preferencias, Complementos, Editor hexadecimal accesible, General:

- **Bytes por línea**: 8, 16 (por defecto) o 32.
- **Orden de bytes del inspector**: little endian (por defecto) o big endian.
- **Codificación de la columna de texto**: Windows-1252 por defecto.
- **Qué se dice al mover el cursor**: solo el valor (por defecto) o el valor, el decimal y el binario.
- **Guardar una copia .bak antes de guardar**: desactivada por defecto.
- **Abrir siempre en solo lectura**: desactivada por defecto.

## Sonidos

- **Tecla no válida en el editor hexadecimal**: al pulsar algo que no es un dígito hexadecimal en la columna hexadecimal.
