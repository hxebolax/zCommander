# Archivos en uso y procesos

Dice qué programa tiene abierto un archivo, permite cerrarlo para seguir trabajando y muestra la lista de procesos del equipo.

## Órdenes

Están en el menú Complementos, submenú «Sistema y seguridad», submenú «Archivos en uso y procesos», y en la paleta de órdenes.

- **¿Quién usa este archivo?**: dice qué programa tiene abierto el archivo del cursor o los marcados (en una carpeta, cualquiera de los archivos que contiene). Por ejemplo: «Lo usa Microsoft Word (PID 4312)». No tiene tecla de fábrica; se le puede dar una en el mapa de teclas.
- **Procesos...** (Ctrl+Mayús+F12): abre la ventana «Procesos».

## Cuando un archivo está en uso

Si al copiar, mover, renombrar o eliminar un archivo Windows dice que otro programa lo está usando, la pregunta de error de zCommander gana dos botones:

- **Ver qué programa lo usa**: dice qué programas lo tienen abierto y vuelve a la pregunta.
- **Cerrar ese programa y reintentar**: pide confirmación (el botón predeterminado es «No») y le pide a ese programa que se cierre, como hace Windows al apagar el equipo. Si el programa pregunta si quiere guardar, contéstele. Si no se cierra, zCommander pregunta si debe forzar el cierre; al forzarlo se pierde lo que no se haya guardado. Después se vuelve a intentar la operación.

Con «Cerrar ese programa y reintentar» nunca se cierran los servicios de Windows, los procesos del sistema, el Explorador de Windows (cierre su ventana) ni el propio zCommander. Si alguno de los programas que usan el archivo no se puede cerrar, no se cierra ninguno.

## La ventana Procesos

- **Filtrar por nombre** (Alt+F): escriba parte del nombre o de la ruta.
- **Lista de procesos** (Alt+L): columnas Nombre, PID, Memoria, CPU, Usuario y Ruta. Se actualiza sola cada pocos segundos sin mover el cursor. Flecha izquierda y Flecha derecha recorren las columnas.
- **Mostrar los procesos del sistema** (Alt+S): casilla; se recuerda.
- **Terminar** (Alt+T, o Supr en la lista): termina el proceso elegido, con confirmación. Los procesos del sistema no se pueden terminar.
- **Cambiar la prioridad...** (Alt+P): baja, por debajo de lo normal, normal, por encima de lo normal o alta.
- **Abrir su carpeta** (Alt+C): lleva el panel activo a la carpeta del ejecutable.
- **Copiar la información** (Alt+O): copia todos los datos del proceso al portapapeles.
- **Actualizar** (Alt+A o F5).
- **Cerrar** (Alt+E o Escape).

F1 abre esta ayuda.

## Preferencias

En Preferencias, Complementos, Archivos en uso y procesos, General:

- **Segundos entre actualizaciones de la lista de procesos**: de 1 a 60; 3 de fábrica.
- **Mostrar los procesos del sistema**: desactivada de fábrica.

## Sonidos

- **Programa cerrado**: suena cuando un programa se cierra a petición suya.
