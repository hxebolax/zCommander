# Reproductor multimedia

Reproduce audio, y el sonido de los vídeos, mientras sigue usando zCommander. Recuerda dónde dejó cada archivo largo (audiolibros, podcasts) y continúa ahí la próxima vez.

Usa el motor de Windows y sus códecs (MP3, WAV, WMA, M4A, AAC, FLAC, MP4...). Lo que Windows no sabe abrir (Ogg, Opus, MKV, WebM...) lo reproduce con FFplay si está el componente FFmpeg; si no está, se lo dice: «Este formato necesita el componente FFmpeg».

## Órdenes

Están en el menú Complementos, submenú «Multimedia», submenú «Reproductor multimedia», y en la paleta de órdenes. «Siguiente pista», «Pista anterior», «Añadir a la cola», «Guardar la cola como M3U...» y «Temporizador de apagado...» no tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Reproducir** (Ctrl+Mayús+F5): reproduce los archivos marcados; si no hay ninguno, el del cursor. Sobre una carpeta, reproduce sus archivos de audio y vídeo por orden de nombre; sobre una lista M3U o M3U8, la lista.
- **Mostrar el reproductor** (Alt+Mayús+F2): abre la ventana del reproductor.
- **Pausa o continuar** (Alt+Mayús+F5): pausa o continúa. Se puede usar como tecla global (Preferencias, página Personalización, botón «Teclas globales...»).
- **Detener** (Alt+Mayús+F6): detiene. Se puede usar como tecla global.
- **Retroceder** (Alt+Mayús+F7) y **Avanzar** (Alt+Mayús+F8): un salto corto atrás o adelante.
- **Decir la posición** (Alt+Mayús+F3): dice, por ejemplo, «12:30 de 45:10, 27 %». La posición nunca se anuncia sola.
- **Siguiente pista** y **Pista anterior**: cambian de pista. Pista anterior vuelve primero al principio de la pista si ya han pasado unos segundos.
- **Añadir a la cola**: añade el archivo del cursor o los marcados al final de la cola.
- **Guardar la cola como M3U...**: guarda la cola en una lista M3U8 (o M3U) con rutas relativas, en UTF-8.
- **Temporizador de apagado...**: detiene la reproducción cuando pasan los minutos que escriba (0 lo quita).

## La ventana del reproductor

No es modal: puede volver a los paneles sin cerrarla, y cerrarla (Escape o el botón «Cerrar») no detiene la música. F1 abre esta ayuda.

- **Cola de reproducción** (Alt+O): lista con Número, Título y Duración. La pista que suena dice «actual» en su número. Intro reproduce la elegida; Supr la quita de la cola.
- **Estado** (Alt+E): texto de solo lectura con la pista, la posición, el motor, el volumen, la velocidad, la repetición y el temporizador.
- **Volumen** (Alt+U; deslizador) y **Velocidad** (Alt+V; de 0,5x a 3x; con FFplay no se puede cambiar).
- Botones: «Pausa o continuar», «Detener», «Pista anterior», «Siguiente pista», «Ir a un tiempo...», «Añadir marcador...», «Lista de marcadores...», «Repetir», «Aleatorio», «Abrir una lista M3U...», «Guardar la cola como M3U...», «Quitar de la cola», «Temporizador de apagado...» y «Cerrar».

### Teclas de la ventana del reproductor

- Espacio: pausa o continúa (sobre un botón, lo pulsa).
- Flecha izquierda y Flecha derecha: salto corto atrás y adelante. Ctrl+Flecha izquierda y Ctrl+Flecha derecha: salto medio. Re Pág y Av Pág: salto largo.
- Más y Menos: volumen. Ctrl+Más y Ctrl+Menos: velocidad.
- P: dice la posición. G: ir a un tiempo (como 1:23:00) o a un porcentaje (como 50 %).
- M: añade un marcador con nombre. Ctrl+M: lista de marcadores de la pista (ir a uno o borrarlo).
- R: cambia entre sin repetir, repetir la pista y repetir la cola. A: orden aleatorio.
- Flecha arriba y Flecha abajo: se mueven por la cola. Intro reproduce la pista elegida y Supr la quita.
- Ctrl+1 a Ctrl+3: leen la columna Número, Título o Duración de la pista elegida.

## Preferencias

En Preferencias, Complementos, Reproductor multimedia:

- Página Reproducción: «Salto corto (segundos)» (5 por defecto), «Salto medio (segundos)» (30), «Salto largo (segundos)» (300), «Volumen» (80), «Velocidad» (1) y «Usar FFplay para los formatos que Windows no abre» (activada).
- Página Posiciones y anuncios: «Recordar dónde se dejó cada archivo largo» (activada), «Recordar desde (minutos de duración)» (10), «Anunciar el título al cambiar de pista» (activada) y «Formatos que se reproducen con Intro» (vacío).

Las posiciones recordadas y los marcadores se guardan en la carpeta de datos del complemento (`data/config/plugins/zc.reproductor/`). Si el archivo cambia de tamaño, su posición se olvida.

Para que Intro reproduzca ciertos archivos, escriba sus patrones en «Formatos que se reproducen con Intro» (por ejemplo `*.mp3;*.m4b`): zCommander los abre con el reproductor sin más pasos. Si en Asociaciones hay una acción Abrir propia para alguno de esos patrones, gana la suya.

## Sonidos

- **Cambio de pista**: empieza otra pista de la cola.
- **Fin de la cola**: termina la última pista de la cola.
- **Marcador guardado**: se guarda un marcador en la pista que suena.

Se pueden cambiar o silenciar en Preferencias, Sonidos. Todo lo que suena también se anuncia.

## Títulos de las pistas

Si está el complemento Metadatos y etiquetas de audio, la cola y los anuncios usan el artista y el título de las etiquetas; si no, el nombre del archivo.
