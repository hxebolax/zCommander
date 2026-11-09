# Lector de documentos

Convierte PDF, Word (DOCX y, con Microsoft Word instalado, DOC), OpenDocument (ODT), EPUB, RTF, HTML y FictionBook (FB2) en un documento con secciones que se lee en el visor interno y en la Vista rápida, sin abrir programas pesados.

## Leer un documento en el visor y en la Vista rápida

F3 sobre un documento lo abre en el visor interno ya convertido a texto. La Vista rápida (Ctrl+Q) también lo muestra convertido.

- Cada encabezado del documento es una sección. F6 va a la sección siguiente, Mayús+F6 a la anterior y Ctrl+L muestra la lista de secciones con búsqueda. La barra de estado dice, por ejemplo, «Sección 3 de 12: Introducción».
- En los PDF, cada página es una sección «Página 12 de 80» y Ctrl+P va a una página.
- Las tablas se leen como texto: «Tabla de 3 columnas. Fila 1: Nombre; Edad; Ciudad.».
- Las notas al pie van al final de la sección en la que se citan («Nota 1: ...»).
- Las imágenes con texto alternativo se dicen como «[Imagen: descripción]».

Si un PDF casi no tiene texto, el visor avisa «PDF sin texto: probablemente escaneado» y, si está el complemento Reconocimiento de texto, OCR, dice cómo reconocerlo (Ctrl+Mayús+F3 en el panel).

## Órdenes

Están en el menú Complementos, submenú «Documentos y datos», submenú «Lector de documentos», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Propiedades del documento**: dice el tipo, las páginas, el título, el autor y la fecha del documento del cursor. Si es un PDF escaneado y está el complemento de OCR, pregunta si reconocer su texto.
- **Convertir a texto...**: guarda el documento del cursor o los marcados como texto (.txt) o Markdown (.md).

## El diálogo Convertir a texto

- **Formato** (Alt+F): texto (.txt) o Markdown (.md).
- **Codificación** (Alt+D): UTF-8 o UTF-8 con BOM.
- **Guardar en** (Alt+G): junto a cada documento o en la carpeta del otro panel.
- Botones **Convertir** (Alt+O) y **Cancelar** (Alt+C).

La conversión es una operación del motor: la ventana de operaciones (F12) la muestra y se puede pausar y cancelar. Si el archivo de texto ya existe, pregunta si sustituirlo u omitirlo. Un PDF escaneado se reconoce con OCR si está ese complemento.

## Columnas, información y búsqueda

- Columnas **Páginas**, **Título** y **Autor**, en el diálogo de columnas de cada panel. Se calculan en segundo plano.
- La información del elemento (Ctrl+Mayús+I) añade el tipo de documento, las páginas, el título, el autor y la fecha.
- En «Buscar archivos» (Alt+F7), pestaña «Contenido», con «Buscar también dentro de documentos» marcada, se busca el texto dentro de estos documentos.

## Formatos que se leen

- **PDF**: con pypdf. Los PDF protegidos con contraseña de apertura no se pueden leer.
- **DOCX**, **ODT**, **EPUB** y **FB2**: se leen sin programas externos.
- **DOC** (Word 97-2003): necesita Microsoft Word instalado; si no está, se dice «Para .doc hace falta Microsoft Word».
- **RTF** y **HTML**: texto, encabezados, listas y tablas.

## Preferencias

En Preferencias, Complementos, Lector de documentos, General:

- **Formatos que se leen**: los que no estén se ven con el visor interno de siempre.
- **Tamaño máximo de un documento (MB)**: 100 por defecto.
- **Marcas de página en los PDF**: activada por defecto.
- **Leer el texto alternativo de las imágenes**: activada por defecto.
- **Formato al convertir** y **Codificación al convertir**: lo que propone «Convertir a texto».

## Licencias

Lee los PDF con [pypdf en PyPI](https://pypi.org/project/pypdf/) 7.0.0, licencia BSD-3-Clause (texto en `lib/LICENCIA-pypdf.txt`).
