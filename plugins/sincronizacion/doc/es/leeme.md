# Sincronización avanzada y copias

Guarda tareas de sincronización y de copia con nombre. Cada tarea recuerda cómo quedó la última vez, así que sabe qué se borró o se renombró en cada lado, y conserva versiones de lo que sustituye o borra.

## Órdenes

- **Tareas de sincronización...** (menú Complementos, submenú «Automatización», submenú «Sincronización avanzada y copias»): abre la lista de tareas.
- **Ejecutar todas las tareas** (menú Complementos, submenú «Automatización», submenú «Sincronización avanzada y copias»): pone en cola todas las tareas, una tras otra.

Las dos están también en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

## La lista de tareas

La lista **Tareas guardadas** (Alt+G) tiene las columnas Nombre, Modo, Origen, Destino, Última ejecución y Resultado. Intro edita la tarea y Supr la borra (pregunta antes; no se borra ningún archivo).

Botones: **Nueva...** (Alt+N), **Editar...** (Alt+E), **Borrar** (Alt+B), **Simular** (Alt+S; muestra lo que haría, sin cambiar nada), **Ejecutar** (Alt+J), **Ejecutar todas** (Alt+T), **Ver el último informe** (Alt+V) y **Cerrar** (Alt+C o Escape). Las tareas se ejecutan como cualquier operación: con progreso, pausa, cola y la ventana de operaciones (F12). Al terminar se anuncia el resumen y el informe queda guardado.

## El diálogo Tarea de sincronización

- **Nombre**: con él la usa también el Programador de tareas.
- **Origen** y **Destino**: cualquier carpeta o dirección que entienda zCommander (disco, red, ftp://, sftp:// o una nube). Al crear una tarea se proponen las carpetas de los dos paneles.
- **Modo**:
  - **Espejo**: el destino queda igual que el origen; lo que sobra en el destino se quita.
  - **Actualizar**: copia al destino lo nuevo y lo más reciente; nunca borra.
  - **Dos sentidos**: los cambios de cada lado pasan al otro. Un archivo borrado en un lado se borra en el otro (no vuelve a aparecer), un archivo renombrado se renombra en el otro sin copiarlo, y si un archivo cambió en los dos lados gana el más reciente (el otro queda en las versiones).
- **Incluir solo estos archivos (patrones separados por punto y coma)** y **Excluir (patrones separados por punto y coma)**: por ejemplo `*.docx;*.pdf` o `*.tmp;node_modules`.
- **Incluir subcarpetas** y **Conservar versiones de lo sustituido o borrado** (sí, por defecto): lo que se sustituye o se borra va antes a la carpeta `_versiones\AAAA-MM-DD\` de ese lado.

## Preferencias

En Preferencias, Complementos, Sincronización avanzada y copias, General:

- **Tolerancia de fechas, en segundos**: 2 por defecto (memorias USB con FAT).
- **Comprobar cada archivo copiado leyéndolo de nuevo**: desactivada por defecto.
- **Días que se guardan las versiones**: 30 por defecto.
- **Espacio máximo de las versiones, en MB**: 1024 por defecto; si se pasa, se borran los días más antiguos.
