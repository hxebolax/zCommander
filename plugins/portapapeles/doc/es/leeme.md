# Historial del portapapeles

Recuerda lo que se copia (texto y listas de archivos), en zCommander y en cualquier otro programa, y permite volver a pegarlo.

## Órdenes

- **Historial del portapapeles...** (Ctrl+Mayús+V; menú Complementos, submenú «Sistema y seguridad», submenú «Historial del portapapeles», y paleta de órdenes): abre el diálogo «Historial del portapapeles». Si el historial está vacío, lo dice.

## El diálogo Historial del portapapeles

- **Buscar** (Alt+S): escriba parte del texto o del nombre de un archivo.
- **Historial** (Alt+H): lista con las columnas Contenido (el texto, o «3 archivos de D:\Fotos»), Hora y Fijado. Lo más reciente va primero. Intro vuelve a poner el elemento en el portapapeles; Supr lo borra.
- **Pegar en la línea de órdenes** (Alt+L): escribe el texto (o las rutas de los archivos) en la línea de órdenes, sin ejecutarlo.
- **Pegar como archivos** (Alt+R): copia los archivos del elemento a la carpeta del panel.
- **Pegar como archivo nuevo** (Alt+N): crea `nota.txt` con el texto en la carpeta del panel; si ya existe, «nota (2).txt». Nunca sobrescribe nada.
- **Copiar al portapapeles** (Alt+C).
- **Fijar o soltar** (Alt+F): un elemento fijado no se borra cuando el historial se llena.
- **Borrar** (Alt+B) y **Borrar todo** (Alt+T, con confirmación; también los fijados).
- **Cerrar** (Alt+E o Escape).

## Preferencias

En Preferencias, Complementos, Historial del portapapeles, General:

- **Número de elementos que se recuerdan**: de 5 a 500; 50 de fábrica.
- **Guardar el historial al cerrar zCommander**: desactivada de fábrica. Se guarda en la carpeta de datos, cifrado para su usuario de Windows (otro usuario u otro equipo no pueden leerlo). Al desactivarla se borra lo guardado.
- **Anunciar lo que se copia en otros programas**: desactivada de fábrica. Dice lo que se acaba de copiar fuera de zCommander, con un sonido.

## Sonidos

- **Copia en otro programa**: suena cuando otro programa copia algo (si está activado el anuncio).

## Privacidad

- Lo que los gestores de contraseñas marcan como privado (el formato `ExcludeClipboardContentFromMonitorProcessing`, o «no incluir en el historial») nunca se guarda ni se anuncia.
- El historial solo se guarda en el disco si activa «Guardar el historial al cerrar zCommander», y entonces va cifrado para su usuario de Windows.
