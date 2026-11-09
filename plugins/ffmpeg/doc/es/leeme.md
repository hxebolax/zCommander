# Conversor multimedia con FFmpeg

Convierte audio y vídeo, extrae el audio de un vídeo, recorta, normaliza el volumen, une archivos y da la información técnica.

Usa el componente FFmpeg (menú Opciones, «Componentes externos»). Si falta, las órdenes dicen «Falta el componente FFmpeg: Opciones, Componentes externos».

Cada conversión es una operación: tiene progreso real, se puede pausar entre archivos y cancelar (el archivo a medias se borra) y va a la cola de operaciones. El original nunca se sobrescribe: si el archivo de salida coincidiera con él, se crea «nombre (2)».

## Órdenes

Están en el menú Complementos, submenú «Multimedia», submenú «Conversor multimedia con FFmpeg», y en la paleta de órdenes. Trabajan con los archivos marcados o, si no hay ninguno, con el del cursor. Los archivos nuevos van, por defecto, a la carpeta del otro panel.

- **Convertir audio o vídeo...** (Ctrl+Mayús+F6): abre el diálogo «Convertir audio o vídeo».
- **Extraer el audio...**: saca el audio de un vídeo copiando el flujo (sin pérdida) si se puede; si no, lo convierte a MP3.
- **Recortar...**: pide el **Inicio** y el **Fin** (como 0:01:30 y 0:05:00) y crea «nombre (recorte)». Sin recodificar es rápido y sin pérdida, pero en un vídeo corta en el fotograma clave más cercano; marque «Recodificar para cortar justo en el segundo» si necesita exactitud.
- **Normalizar el volumen...**: normaliza con el filtro loudnorm de dos pasadas (EBU R128) a la sonoridad de Preferencias y crea «nombre (normalizado)».
- **Información técnica**: duración, contenedor y flujos (códec, tasa de bits, frecuencia, canales, resolución y fotogramas por segundo) del archivo del cursor, en un texto de solo lectura que se puede copiar.
- **Unir archivos de audio...**: une los archivos marcados, del mismo formato y en el orden del panel, en uno solo (sin recodificar). Pide el **Nombre del archivo unido**.

Solo «Convertir audio o vídeo...» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

## El diálogo Convertir audio o vídeo

- **Perfil** (Alt+P): MP3, AAC (M4A), Opus, OGG Vorbis, FLAC, WAV, MP4 (H.264 y AAC), WebM (VP9 y Opus), MKV (copiar los flujos) o Personalizado.
- **Calidad** (Alt+L): la del perfil (tasa de bits, calidad o compresión).
- **Argumentos de FFmpeg (solo con Personalizado)** (Alt+M): opciones de códec, como `-c:a libmp3lame -b:a 128k`. No se admiten `-y`, `-i`, opciones que escriben otros archivos ni rutas fuera de la carpeta de salida. Se recuerdan los últimos que usó.
- **Carpeta de salida** (Alt+S) y botón **Examinar...** (Alt+X).
- **Nombre** (Alt+N): `[N]` es el nombre original sin extensión, `[E]` su extensión y `[C]` un contador. La extensión del perfil se pone sola.
- **Conservar las etiquetas** (Alt+T) y **Conservar las fechas** (Alt+F).
- **Si existe** (Alt+E): preguntar, cambiar el nombre, omitir o sobrescribir el que ya existe.
- Botones **Convertir** (Alt+V), **En cola** (Alt+O; empieza cuando terminen las operaciones anteriores) y **Cancelar** (Alt+C).

## Información del elemento

La información del elemento (Ctrl+Mayús+I) añade la información técnica de los vídeos y de los formatos de audio que no lee el complemento Metadatos y etiquetas de audio.

## Preferencias

En Preferencias, Complementos, Conversor multimedia con FFmpeg, General:

- **Perfil que se propone al convertir**: MP3 de 192 kb/s por defecto.
- **Carpeta de salida**: la carpeta del otro panel (por defecto), la del original o la elegida en el campo siguiente.
- **Carpeta elegida**.
- **Hilos de FFmpeg (0 es automático)**: 0 por defecto.
- **Volumen al normalizar (LUFS)**: de -30 a -10; -16 por defecto.
- **Conservar las etiquetas al convertir**: activada por defecto.
