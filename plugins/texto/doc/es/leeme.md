# Codificaciones y fines de línea

Detecta y convierte la codificación y los fines de línea de archivos de texto, uno o muchos. Sirve sobre todo para los textos antiguos en Windows-1252 u OEM 850 (MS-DOS) que el lector de pantalla lee con caracteres raros.

## Órdenes

Están en el menú Complementos, submenú «Documentos y datos», submenú «Codificaciones y fines de línea», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Convertir la codificación y los fines de línea...**: convierte a UTF-8 el archivo del cursor o los marcados. Solo trabaja con archivos del disco.
- **Informe de caracteres no válidos**: revisa el archivo del cursor o los marcados y dice dónde están los caracteres que no valen.

## El diálogo Convertir la codificación y los fines de línea

- **Codificación de destino** (Alt+D): UTF-8 sin BOM o con BOM.
- **Fin de línea** (Alt+F): sin cambio, CRLF (Windows) o LF (Unix).
- **Tabuladores** (Alt+T): sin cambio, tabuladores a espacios, o los espacios de la sangría a tabuladores.
- **Ancho del tabulador** (Alt+A): de 1 a 16 espacios.
- **Quitar los espacios al final de las líneas** (Alt+Q).
- **Guardar una copia .bak del original** (Alt+B).
- **Vista previa** (Alt+R): una fila por archivo con las columnas Archivo, Codificación, Fin de línea y Cambios («Windows-1252 a UTF-8; 12 líneas cambian»). Se recalcula sola al cambiar una opción. Flecha izquierda y Flecha derecha leen las columnas.
- **Estado** (Alt+E): cuántos archivos cambiarán.

Botones: «Convertir» (Alt+V) y «Cancelar» (Alt+C o Escape). F1 abre esta ayuda y Ctrl+H dice la ayuda del control enfocado.

La conversión es una operación del motor: se ve en la ventana de operaciones (F12), se puede pausar y cancelar, y los errores de un archivo no paran los demás. Un archivo con bytes que no valen en su codificación no se convierte (perdería esos caracteres): el informe dice dónde están.

**Deshacer** (Ctrl+Z en el panel) devuelve los archivos a como estaban. Con la copia .bak desactivada, el original se guarda aparte mientras zCommander está abierto y se borra al cerrarlo.

## El informe de caracteres no válidos

Revisa el archivo del cursor o los marcados y muestra, en un texto de solo lectura, cada problema con su línea y su columna: bytes que no valen en la codificación detectada, caracteres de sustitución (el texto ya se estropeó al guardarlo), caracteres nulos y de control. Se apuntan los 50 primeros de cada archivo.

## Columnas Codificación y Fin de línea

En el diálogo de columnas de cada panel se pueden añadir dos columnas de este complemento. Solo miran los archivos de las extensiones de texto (Preferencias) y leen los primeros 64 KB:

- **Codificación**: ASCII, UTF-8, UTF-8 con BOM, UTF-16 LE o BE (con o sin BOM), UTF-32, Windows-1252 u OEM 850.
- **Fin de línea**: CRLF (Windows), LF (Linux y macOS), CR (Mac antiguo), Mezclado o Sin fines de línea.

En un archivo que no parece de texto, las dos dicen «Sin datos».

## Preferencias

En Preferencias, Complementos, Codificaciones y fines de línea, General:

- **Codificación de destino**: la que propone el diálogo (UTF-8 sin BOM por defecto).
- **Fin de línea**: el que propone el diálogo (sin cambio por defecto).
- **Extensiones de texto**: patrones separados por punto y coma en los que miran las columnas.
- **Guardar una copia .bak del original al convertir**: activada por defecto.
