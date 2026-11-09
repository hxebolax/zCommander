# Búsqueda instantánea

Busca nombres de archivo en todo el equipo en milisegundos. Usa **Everything** si lo tiene instalado y abierto y, si no, el **índice de búsqueda de Windows**.

zCommander no instala ni trae Everything: solo habla con él cuando está abierto. Puede descargarlo gratis de la [página de Everything en voidtools](https://www.voidtools.com/).

## Órdenes

- **Búsqueda instantánea con Everything...** (Ctrl+Mayús+F; menú Complementos, submenú «Automatización», submenú «Búsqueda instantánea»): abre la ventana «Búsqueda instantánea».

## La ventana Búsqueda instantánea

- **Buscar** (Alt+B): escriba parte del nombre. Al dejar de teclear (300 milisegundos por defecto) se busca y se anuncia el número de resultados. Intro en este campo va al primer resultado.
- **Texto contenido (solo con el índice de Windows)** (Alt+T): busca archivos que contienen ese texto. Siempre usa el índice de Windows.
- **Búsquedas guardadas** (Alt+G): elija una para repetirla.
- **Estado** (Alt+E): dice el motor que se usa, el número de resultados o, si no hay ningún motor, por qué y qué hacer.
- **Resultados** (Alt+R): lista con las columnas Nombre y Carpeta. Intro va al archivo en el panel activo.
- Botones: **Ir al archivo** (Alt+I), **Enviar al panel** (Alt+P; todos los resultados como lista en el panel activo, para copiarlos, borrarlos o lo que necesite), **Guardar la búsqueda** (Alt+D), **Olvidar la búsqueda guardada** (Alt+O) y **Cerrar** (Alt+C o Escape).

F1 abre esta ayuda y Ctrl+H dice la ayuda del control enfocado.

### Sintaxis de búsqueda

El campo «Buscar» admite la sintaxis de Everything. Con el índice de Windows, esta sintaxis se traduce a su lenguaje.

- `ext:pdf` o `ext:pdf;docx`: por extensión.
- `size:>1gb`: por tamaño.
- `dm:today`, `dm:yesterday` o `dm:2026-11-01`: por fecha de modificación.
- Comodines `*` y `?`.
- `|` para «o», `!` para «no» y comillas para frases.

## Buscar con el índice desde Buscar archivos

En «Buscar archivos» (Alt+F7), pestaña «Avanzado», campo «Motor de búsqueda», elija «Índice: Everything o búsqueda de Windows». Los patrones de nombre (`*.txt;*.md | *.bak`) y el texto contenido se buscan con el índice, en todo el equipo, en lugar de recorrer las carpetas.

## Preferencias

En Preferencias, Complementos, Búsqueda instantánea, General:

- **Motor de búsqueda**: automático (Everything si está abierto; si no, el índice de Windows), solo Everything o solo el índice de búsqueda de Windows.
- **Máximo de resultados**: 1000 por defecto.
- **Incluir archivos ocultos y de sistema**: desactivada por defecto.
- **Carpetas excluidas**: lo que hay dentro no aparece.
- **Retardo antes de buscar, en milisegundos**: de 100 a 2000; 300 por defecto.
