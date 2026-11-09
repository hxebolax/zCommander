# Lectura en voz y audiolibros

Lee archivos de texto y documentos con una voz de Windows, aparte del lector de pantalla, y los convierte en audio. Usa las voces SAPI 5 y, si están instaladas, las voces OneCore de Windows 10 y 11.

Lee directamente los archivos de texto (TXT, MD, LOG, CSV, SRT...). Los documentos (PDF, DOCX, ODT, EPUB, RTF, HTML, FB2) necesitan el complemento Lector de documentos.

## Órdenes

Están en el menú Complementos, submenú «Multimedia», submenú «Lectura en voz y audiolibros», y en la paleta de órdenes. Solo «Leer en voz alta o pausar» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

- **Leer en voz alta o pausar** (Ctrl+F9): lee el archivo del cursor; si ya está leyendo, pausa, y otra vez continúa. Si ya había leído parte de ese archivo, continúa donde lo dejó. Se puede usar como tecla global (Preferencias, página Personalización, botón «Teclas globales...»).
- **Detener la lectura**: detiene y recuerda dónde iba.
- **Frase siguiente** y **Frase anterior**: saltan una frase.
- **Párrafo siguiente** y **Párrafo anterior**: saltan un párrafo; «Párrafo anterior» vuelve primero al principio del párrafo actual.
- **Convertir a audio...**: convierte los archivos marcados (o el del cursor) en audio, como operación con progreso. Nunca se sobrescribe nada.

Las frases se cortan respetando las abreviaturas habituales, como «Sr.» o «etc.».

## El diálogo Convertir a audio

- **Formato** (Alt+F): WAV, MP3 u Opus. Los dos últimos necesitan el componente FFmpeg.
- **Carpeta de salida** (Alt+S) y botón **Examinar...** (Alt+X).
- **Dividir por capítulos** (Alt+D): un archivo por cada encabezado principal del documento, como «Libro - 01 - Prólogo».

## Preferencias

En Preferencias, Complementos, Lectura en voz y audiolibros, página Voz:

- **Nombre de la voz (vacío, la predeterminada)**.
- **Velocidad (de -10 a 10)** y **Tono (de -10 a 10)**: 0 por defecto.
- **Volumen (de 0 a 100)**: 100 por defecto.
- **Formato al convertir a audio**: MP3 por defecto.
- **Pausa entre párrafos (milisegundos)**: 400 por defecto.

El botón «Abrir la configuración avanzada...» abre el diálogo «Voz de lectura», con el desplegable **Voz** (Alt+V), que lista las voces instaladas, y el botón **Probar** (Alt+P).

## Sonidos

- **Fin de la lectura**: al terminar de leer un archivo.
