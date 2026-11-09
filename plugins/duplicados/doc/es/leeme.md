# Buscador de duplicados

Encuentra archivos iguales en una o varias carpetas y ayuda a decidir qué conservar.

## Órdenes

- **Buscar duplicados...** (Mayús+F7; menú Complementos, submenú «Orden y limpieza del disco», submenú «Buscador de duplicados»): abre el diálogo «Buscar duplicados».

## El diálogo Buscar duplicados

- **Dónde buscar (carpetas separadas por punto y coma)** (Alt+D): una o varias carpetas. Se propone la carpeta del panel activo, o las carpetas marcadas.
- **Criterio** (Alt+R):
  - Por contenido: compara el tamaño y, entre los del mismo tamaño, una suma BLAKE2b de los primeros 64 KB y después la del archivo entero. Es lo más seguro.
  - Por nombre, o por nombre y tamaño.
  - Por etiquetas de audio (artista, título y duración), si está el complemento «Metadatos y etiquetas de audio».
- **Tamaño mínimo en KB** (Alt+T).
- **Excluir (patrones separados por punto y coma)** (Alt+X): patrones como `*.tmp;Thumbs.db`.
- **Incluir archivos ocultos y de sistema** (Alt+O).
- Botones **Buscar** (Alt+B) y **Cancelar** (Alt+C).

La búsqueda es una operación más: se ve en la ventana de operaciones (F12), donde se puede pausar o cancelar. Nunca sigue enlaces ni uniones.

## La lista de duplicados

La ventana «Duplicados encontrados» tiene un **Resumen** (Alt+R) y la lista **Duplicados (marque las copias que quiere quitar)** (Alt+D).

Cada fila es una copia, con las columnas Grupo, Nombre, Carpeta, Tamaño y Fecha. Al pasar a otro grupo se dice, por ejemplo, «Grupo 3 de 40, 2 copias, 12 MB recuperables». Espacio marca o desmarca la copia que se quiere quitar.

Botones:

- **Marcado automático...** (Alt+A): marca todas las copias menos una en cada grupo. Se conserva el más antiguo, el más reciente, el de la carpeta preferida o el de ruta más corta, y se dice cuántos quedan marcados y cuánto ocupan.
- **Quitar todas las marcas** (Alt+Q).
- **Ir al archivo** (Alt+I): lleva el panel activo a la carpeta del archivo de la fila.
- **Enviar los marcados a la papelera** (Alt+P): con confirmación; nunca deja un grupo sin ninguna copia.
- **Sustituir por enlaces duros** (Alt+L): cada copia marcada pasa a ser un enlace duro al archivo que se conserva (misma unidad NTFS). Los archivos siguen en su sitio y el contenido ocupa una sola vez; cambiar uno cambia todos.
- **Exportar informe...** (Alt+X): en texto o en CSV.
- **Enviar al panel** (Alt+N): las copias marcadas (o todas) como lista de resultados en el panel.
- **Cerrar** (Alt+E o Escape).

F1 abre esta ayuda.

## Preferencias

En Preferencias, Complementos, Buscador de duplicados, General:

- **Tamaño mínimo en KB**: 1 por defecto.
- **Excluir (patrones separados por punto y coma)**: `*.tmp;Thumbs.db;desktop.ini` por defecto.
- **Incluir archivos ocultos y de sistema**: desactivada por defecto.
- **Carpeta preferida**: la que conserva el marcado automático.
- **Acción predeterminada con los marcados**: enviar a la papelera (por defecto) o sustituir por enlaces duros.
