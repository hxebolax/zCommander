# Ocupación del disco accesible

Dice qué ocupa el espacio de una unidad o carpeta, con listas que se leen en lugar de gráficos.

## Órdenes

- **Analizar la ocupación...** (Ctrl+Mayús+F7; menú Complementos, submenú «Orden y limpieza del disco», submenú «Ocupación del disco accesible»): analiza una carpeta o unidad.
- **Los 100 archivos más grandes** (menú Complementos, submenú «Orden y limpieza del disco», submenú «Ocupación del disco accesible»): abre la lista de archivos grandes y antiguos.
- **Ocupación por extensión** (mismo submenú): abre la lista por extensiones.
- **Ir a esta carpeta en el disco** (mismo submenú): lleva el otro panel a la carpeta real del elemento del cursor.

Solo «Analizar la ocupación...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas. Todas están también en la paleta de órdenes.

## Analizar una carpeta o unidad

El diálogo «Analizar la ocupación» tiene:

- **Qué analizar (carpeta o unidad)** (Alt+Q): se propone la del panel activo.
- **Seguir enlaces y uniones** (Alt+E).
- **Tamaño en el disco en lugar del tamaño de los archivos** (Alt+D).
- **Incluir archivos de la nube sin descargar** (Alt+N).
- Botones **Analizar** (Alt+A) y **Cancelar** (Alt+C).

El análisis es una operación: se ve en la ventana de operaciones (F12), donde se puede cancelar; si se cancela, el resultado queda marcado como incompleto. Al terminar se abre en el panel activo y se dice el resumen («D:\Datos: 120 GB en 34 000 archivos y 2 100 carpetas; la unidad tiene 200 GB libres de 500 GB»).

Si la carpeta ya se analizó, se ofrece **Usar el último análisis** o **Analizar de nuevo**: el último análisis de cada carpeta se guarda.

## El análisis en el panel

El panel muestra el análisis como si fuera una carpeta: Intro entra en una carpeta y Retroceso sube. Las carpetas tienen su tamaño total.

Para oír el porcentaje y el número de archivos, añada las columnas **Porcentaje del padre**, **Porcentaje del total** y **Archivos** en las columnas del panel. El panel lo muestra de mayor a menor tamaño mientras no elija otro orden. Ver, Copiar y las demás órdenes trabajan sobre los archivos reales.

## La lista de archivos grandes y antiguos

La ventana «Archivos grandes y antiguos» se abre con «Los 100 archivos más grandes».

- **Mostrar** (Alt+M): cambia entre los 100 archivos más grandes y los archivos no modificados en más de N años (los 500 más grandes, con el total).
- **Resumen** (Alt+R).
- **Archivos** (Alt+A): lista con Nombre, Tamaño, Carpeta y Modificado.
- **Ir al archivo** (Alt+I o Intro en la lista): lleva el otro panel a la carpeta del archivo, con el cursor sobre él.
- **Enviar al panel** (Alt+P): muestra la lista en el panel activo como lista de resultados.
- **Exportar...** (Alt+X): guarda esta lista en un archivo de texto o CSV.
- **Cerrar** (Alt+E o Escape).

F1 abre esta ayuda.

## La lista por extensiones

La ventana «Ocupación por extensión» tiene:

- **Resumen** (Alt+R).
- **Lista de extensiones** (Alt+L): con Extensión, Tamaño, Porcentaje y Archivos.
- **Exportar el informe...** (Alt+X): guarda el informe completo en texto o todas las carpetas en CSV.
- **Cerrar** (Alt+E o Escape).

Si el panel activo no muestra un análisis, estas listas usan el último de la sesión o el guardado de la carpeta del panel.

## Preferencias

En Preferencias, Complementos, Ocupación del disco accesible, General:

- **Seguir enlaces y uniones**: desactivada por defecto.
- **Tamaño en el disco en lugar del tamaño de los archivos**: desactivada por defecto.
- **Incluir archivos de la nube sin descargar**: desactivada por defecto.
- **Años sin modificar para considerar un archivo antiguo**: 2 por defecto.
