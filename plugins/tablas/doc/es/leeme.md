# Datos tabulares: SQLite y CSV

Abre bases de datos SQLite como carpetas y muestra los CSV y las tablas en una lista que se lee por columnas, como los paneles.

## Órdenes

Están en el menú Complementos, submenú «Documentos y datos», submenú «Datos tabulares: SQLite y CSV», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Ver como tabla**: abre el visor de tabla con el CSV o la tabla del cursor.
- **Consulta SQL...**: abre el diálogo «Consulta SQL» con la base del cursor o con la base en la que está el panel.

## Bases SQLite como carpetas

Intro sobre un archivo `.db`, `.sqlite` o `.sqlite3` entra en él como si fuera una carpeta: hay un archivo `<tabla>.csv` por cada tabla y vista. Si el archivo no es una base SQLite (otros programas también usan `.db`), se abre con su programa como siempre.

Dentro de la base todo es de solo lectura. Copiar una tabla al otro panel (F5) la guarda como CSV (UTF-8 con BOM y separada por comas). F3 sobre una tabla abre el visor de tabla.

## El visor de tabla

F3 sobre un `.csv`, `.tsv` o `.tab`, o sobre una tabla de una base, abre el visor de tabla en una ventana propia. También lo abre la orden «Ver como tabla». La Vista rápida sigue mostrando el texto del CSV.

- **Datos** (Alt+D): una fila por registro. Flecha arriba y Flecha abajo cambian de fila; Flecha izquierda y Flecha derecha cambian de columna y la leen; Ctrl+1 a Ctrl+0 leen la columna 1 a 10.
- **Estado** (Alt+S): cuántas filas y columnas hay, el filtro y el orden. Si la tabla tiene más filas que el máximo de las preferencias, lo dice.

### Menú Tabla

- **Filtrar...** (Ctrl+F): muestra solo las filas que contienen un texto en cualquier columna. Vacío quita el filtro.
- **Ir a la fila...** (Ctrl+G): por su número.
- **Ordenar por la columna actual** (Ctrl+O): la columna en la que está; otra vez, al revés. Los números se ordenan como números, también «1.234,5».
- **Exportar a CSV...** (Ctrl+E): guarda las filas visibles (con el filtro y el orden).
- **Consulta SQL...** (F5): solo en las tablas de una base SQLite.
- **Estructura de la tabla** (Ctrl+T): las columnas y sus tipos; en un CSV, la codificación y el separador detectados.
- **Cerrar** (Escape).

F1 abre esta ayuda y Ctrl+H dice la ayuda del control enfocado.

### Cómo se leen los CSV

Del CSV se detectan la codificación (UTF-8, UTF-8 con BOM, UTF-16 o Windows-1252) y el separador (coma, punto y coma, tabulador o barra vertical). La primera fila son las cabeceras.

## El diálogo Consulta SQL

- **SQL** (Alt+S): la consulta. Ctrl+Intro la ejecuta.
- **Ejecutar** (Alt+E).
- **Resultados** (Alt+R): las filas, que se leen por columnas como en el visor.
- **Estado** (Alt+T): el número de filas o el error.
- **Exportar a CSV...** (Alt+X) y **Cerrar** (Alt+C o Escape).

Con «Consultas SQL en solo lectura» activada (por defecto), una consulta que cambiaría datos (INSERT, UPDATE, DELETE, CREATE, DROP...) no se ejecuta y el estado lo explica.

## Preferencias

En Preferencias, Complementos, Datos tabulares: SQLite y CSV, General:

- **Consultas SQL en solo lectura**: activada por defecto.
- **Filas máximas que se leen**: 1 000 000 por defecto.
- **Separador de los CSV**: automático (por defecto), coma, punto y coma o tabulador.
