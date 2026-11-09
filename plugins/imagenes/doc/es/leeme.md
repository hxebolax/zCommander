# Imágenes: información, descripción y visor

Dice qué hay en una imagen y ofrece un visor ampliable para baja visión.

## Órdenes

Están en el menú Complementos, submenú «Multimedia», submenú «Imágenes: información, descripción y visor», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Describir la imagen...**: pide una descripción de la imagen del cursor al servicio que haya elegido en Preferencias (un servidor local compatible con Ollama o una API compatible con OpenAI). Si no hay servicio, explica cómo elegirlo y ofrece «Abrir las preferencias». La descripción se muestra en un texto que se puede leer y copiar.
- **Ver la imagen ampliada**: abre el visor con la imagen del cursor. Para que F3 o Intro lo abran, ponga en Asociaciones (menú Opciones) la acción `zc:zc.imagenes:visor` para los patrones de imagen que quiera.
- **Convertir o redimensionar imágenes...**: abre el diálogo «Convertir o redimensionar imágenes». Es una operación con progreso.
- **Quitar la ubicación (GPS)...**: quita la ubicación de las fotos JPEG elegidas sin recomprimirlas y conservando su fecha (pregunta antes).

## Información, columnas y renombrado

- La información del elemento (Ctrl+Mayús+I) añade el formato, las dimensiones, los megapíxeles, la orientación, la profundidad de color y, en las fotos, el EXIF: fecha de la toma, cámara, objetivo, exposición y ubicación GPS.
- Columnas: Dimensiones, Fecha de la toma y Cámara.
- Renombrado múltiple: `[EXIF:fecha]` (AAAA-MM-DD), `[EXIF:hora]` (HH.MM.SS), `[EXIF:ancho]`, `[EXIF:alto]` y `[EXIF:camara]`.

## El visor de imágenes

Es una ventana no modal: Escape la cierra y F1 abre esta ayuda.

- **Imagen** (Alt+I): el área con la imagen. Con el foco en ella, las flechas la desplazan cuando está ampliada.
- **Estado** (Alt+E): texto de solo lectura con el nombre, las dimensiones, la ampliación, el giro y la posición en la carpeta («imagen 3 de 12»).
- Botones: «Ajustar a la ventana», «Tamaño real», «Ampliar», «Reducir», «Girar a la derecha», «Girar a la izquierda», «Siguiente imagen», «Imagen anterior», «Alto contraste» (grises con más contraste), «Describir...», «Reconocer el texto» (necesita el complemento Reconocimiento de texto, OCR), «Información» y «Cerrar».

Teclas del visor:

- Más y Menos: amplían y reducen.
- Av Pág y Re Pág: imagen siguiente y anterior de la carpeta.
- Flechas: desplazan la imagen ampliada, con el foco en la imagen.

Las fotos se muestran derechas según su EXIF. Girar en el visor no cambia el archivo.

## El diálogo Convertir o redimensionar imágenes

- **Formato** (Alt+F): JPEG, PNG, BMP, TIFF, GIF o el mismo.
- **Ancho máximo en píxeles (0 sin límite)** (Alt+M) y **Alto máximo en píxeles (0 sin límite)** (Alt+T): reduce sin deformar y nunca amplía.
- **Girar** (Alt+G).
- **Carpeta de salida** (Alt+S) y botón **Examinar...** (Alt+X).
- **Nombre** (Alt+N): admite `[N]` y `[C]`.
- **Si existe** (Alt+E).

## Preferencias

En Preferencias, Complementos, Imágenes: información, descripción y visor:

- Página Descripción: «Servicio de descripción» (ninguno por defecto), «Dirección del servicio», «Modelo», «Idioma de la descripción» y «Longitud» (breve o detallada).
- Página Conversión: «Calidad de JPEG al convertir» (de 50 a 100; 90 por defecto).

## Privacidad

- La descripción nunca se pide sola: solo cuando usted elige «Describir la imagen...» o el botón «Describir...».
- La primera vez avisa de adónde se enviará la imagen. Se envía reducida a 1024 píxeles.
- Solo se admite http hacia la propia máquina; cualquier otro servidor tiene que ser https.
- La clave de una API compatible con OpenAI se pide la primera vez y se guarda cifrada en los secretos de zCommander.

## Sonidos

- **Descripción recibida**: al llegar la descripción de una imagen.
