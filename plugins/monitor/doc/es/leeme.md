# Monitor de carpetas y reglas automáticas

Vigila carpetas (Descargas, la de los escaneos...) y avisa cuando termina de llegar algo: «Nuevo en Descargas: factura.pdf, 2 MB». Con reglas, además actúa: mueve, copia, renombra, extrae, etiqueta o ejecuta una orden.

Un archivo se anuncia una sola vez, cuando lleva unos segundos sin cambiar y nadie lo está escribiendo: una descarga grande se anuncia al terminar, no mientras llega. Los temporales de los navegadores (`.crdownload`, `.part`) no se anuncian; el archivo llega cuando toma su nombre final. Solo se vigila la carpeta, no sus subcarpetas.

## Órdenes

Están en el menú Complementos, submenú «Automatización», submenú «Monitor de carpetas y reglas automáticas», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Monitor de carpetas...**: abre el diálogo con las carpetas vigiladas y las reglas.
- **Pausar o reanudar el monitor**: es una casilla del menú. Deja de vigilar todas las carpetas hasta reanudarlo o hasta volver a abrir zCommander.
- **Registro del monitor...**: lo que ha hecho, con deshacer.

## El diálogo Monitor de carpetas

- **Carpetas vigiladas** (Alt+G), con los botones **Añadir carpeta...** (Alt+D) y **Quitar carpeta** (Alt+Q). En la lista, Supr también quita la carpeta.
- **Reglas, en orden (se aplica la primera que coincide)** (Alt+R): lista con las columnas Nombre, Si, Entonces y Activa. Se aplica **la primera regla activa que coincide** con el archivo. Intro edita la regla y Supr la borra.
- Botones: **Nueva regla...** (Alt+N), **Editar regla...** (Alt+E), **Borrar regla** (Alt+B), **Subir** (Alt+U), **Bajar** (Alt+J), **Activar o desactivar** (Alt+I), **Simular** (Alt+S; dice qué harían las reglas con lo que ya hay en las carpetas, sin tocar nada), **Aceptar** y **Cancelar**.

Los cambios se guardan al pulsar «Aceptar».

## El diálogo Regla del monitor

- **Nombre** (Alt+N).
- **Patrón de nombre (por ejemplo *.pdf;*.docx)** (Alt+P).
- **Carpeta vigilada** (Alt+V): una o cualquiera.
- **Tamaño mínimo en KB, 0 sin límite** (Alt+M) y **Tamaño máximo en KB, 0 sin límite** (Alt+X).
- **Antigüedad mínima en días, 0 cualquiera** (Alt+D).
- **Qué hacer** (Alt+Q):
  - **Mover** o **Copiar** a la **Carpeta de destino** (Alt+T). Si allí ya hay un archivo con ese nombre, el nuevo se llama «nombre (2)».
  - **Renombrar** con la **Máscara del nombre nuevo** (Alt+S), como en el renombrado múltiple (`[N]`, `[E]`, `[Y]-[M]-[D]`...) y con las máscaras de los complementos.
  - **Extraer** un ZIP, TAR o 7z en la carpeta de destino (o junto al comprimido), en una carpeta con su nombre.
  - **Poner una etiqueta** en el campo **Etiqueta** (Alt+E). Necesita el complemento Notas, comentarios y etiquetas.
  - **Ejecutar una orden o una macro**, escrita en **Orden o macro** (Alt+O), como `zc.reproductor:reproducir` o `macro:Fotos a la copia`. La orden recibe el archivo.
- **Regla activa** (Alt+I).

## El diálogo Registro del monitor

La lista **Registro** (Alt+R) tiene las columnas Fecha, Archivo, Regla, Resultado y Deshecho, con lo más reciente primero.

- **Deshacer la última acción** (Alt+D): devuelve a su sitio el último archivo movido o renombrado, o manda a la papelera la última copia. También se puede deshacer con Deshacer de zCommander (Ctrl+Z).
- **Vaciar el registro** (Alt+V): no toca ningún archivo.
- **Cerrar** (Alt+C o Escape).

## Preferencias

En Preferencias, Complementos, Monitor de carpetas y reglas automáticas, General:

- **Carpetas vigiladas**.
- **Espera antes de actuar, en segundos**: de 1 a 600; 5 por defecto.
- **Nivel de los anuncios**: normal, resultado (por defecto) o ninguno (solo sonidos y registro). Los errores de las reglas se dicen siempre.

## Sonidos

- **Archivo nuevo en una carpeta vigilada**: cuando termina de llegar un archivo.
- **Regla del monitor aplicada**: cuando una regla mueve, copia, renombra, extrae o etiqueta un archivo.

Los dos se pueden cambiar o silenciar en Preferencias, Sonidos.
