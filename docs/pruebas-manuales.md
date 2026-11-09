# Pruebas manuales con lectores de pantalla

Este recorrido comprueba, sin mirar la pantalla, que cada tarea de zCommander se hace solo con el teclado y que el lector dice lo que debe. Es el objetivo 1 de la sección 1.2 del diseño de la 1.x (docs/diseno.md) y la mitigación de sus riesgos 1 y 9 de la sección 21, que las pruebas automáticas no pueden cubrir. El «Recorrido de la versión 2.0» añade lo nuevo de zCommander 2.0 (objetivo 1 de la sección 1.2 de docs/diseno-2.md).

Se hace tres veces: con NVDA, con JAWS y con Narrador. El recorrido común es el mismo para los tres; los capítulos de cada lector dicen cómo prepararlo y qué hay que mirar en especial con él.

Las frases entre comillas latinas son las que debe decir zCommander o el lector. El lector puede añadir palabras propias (el tipo de control, «seleccionado», la posición en la lista); lo que importa es que la información esté y que no se repita.

## Preparación

### Equipo y versión

- Windows 10 de 64 bits (versión 1809 o posterior) o Windows 11.
- La versión compilada (build\ZCommander\ZCommander.exe) o desde el código con entorno.bat ejecutar. Anote cuál.
- Empiece con una carpeta data\config vacía, para que salga el asistente. Si ya existe, cámbiele el nombre mientras dura la prueba.

### Carpeta de prueba

Cree los archivos de prueba con este bloque de PowerShell:

```
$r = "C:\zc-pruebas"
New-Item -ItemType Directory -Force "$r\origen\sub", "$r\destino", "$r\ftp" | Out-Null
1..10 | ForEach-Object { Set-Content -Encoding UTF8 "$r\origen\nota$_.txt" "Nota $_. Hola, esto es una prueba." }
Set-Content -Encoding UTF8 "$r\origen\sub\dentro.txt" "Archivo dentro de la subcarpeta"
Set-Content -Encoding Unicode "$r\origen\utf16.txt" "Texto en UTF-16 con BOM: año, acción, pingüino."
1..700000 | ForEach-Object { "Línea $_ del archivo grande" } | Set-Content -Encoding UTF8 "$r\origen\grande.txt"
1..3 | ForEach-Object { Set-Content -Encoding UTF8 "$r\destino\nota$_.txt" "Versión antigua $_" }
Compress-Archive -Path "$r\origen\nota*.txt" -DestinationPath "$r\copia.zip"
Copy-Item "$r\origen\nota1.txt" "$r\ftp\remoto.txt"
```

Así quedan:

- origen: nota1.txt a nota10.txt, utf16.txt, grande.txt (unos 20 MB) y la carpeta sub.
- destino: nota1.txt, nota2.txt y nota3.txt, con otro contenido, para provocar conflictos.
- copia.zip con las diez notas.
- ftp: la carpeta que servirá el servidor FTP de prueba.

### Servidor FTP de prueba

En una consola, desde la raíz del proyecto:

```
.venv\Scripts\python -m pyftpdlib -p 2121 -w -d C:\zc-pruebas\ftp -u prueba -P prueba
```

Déjelo abierto durante el capítulo de FTP. Ciérrelo con Ctrl+C en esa consola.

### Cómo anotar los resultados

Para cada paso, anote «correcto» o lo que se oyó en su lugar. Si algo falla, anote también:

- El lector y su versión, y la distribución de teclado (NVDA: escritorio o portátil).
- La tecla pulsada y lo que se oyó, palabra por palabra.
- El registro de la sesión: data\logs\sesion_AAAAMMDD_HHMMSS.log (menú Opciones, «Abrir la carpeta de registros»).

Al final de este documento hay una lista de comprobación para copiar en el informe.

## Recorrido común

### 1. Arranque y asistente

1. Arranque zCommander. Debe oír «Iniciando zCommander», y después debe abrirse el «Asistente de zCommander»; el lector debe leer su primer paso, «Bienvenida», con el texto «Qué es zCommander».
2. Recorra los pasos con «Siguiente». En cada uno debe oír, por ejemplo, «Paso 2 de 5: Perfil». En el paso «Perfil», compruebe que está elegido Intermedio. En «Lector de pantalla», deje marcada la casilla «Uso un lector de pantalla (NVDA, JAWS o Narrador)».
3. En el último paso, «Terminar», compruebe el «Resumen», desmarque «Abrir el manual al terminar» y pulse «Terminar». Debe oír «Listo. Perfil Intermedio aplicado.».
4. Debe oír el nombre del panel izquierdo con su carpeta, por ejemplo «Izquierdo: C:\Users\Ana», y la fila del cursor.
5. Vuelva a arrancar ZCommander.exe con zCommander abierto. No debe abrirse otra ventana: debe traerse al frente la que ya estaba.

### 2. Paneles, foco y navegación

1. Pulse Ctrl+G, escriba C:\zc-pruebas\origen y pulse Intro. Debe oír «Izquierdo: C:\zc-pruebas\origen» o el nombre de la carpeta, y la primera fila.
2. Pulse Abajo varias veces. Debe oír cada fila una sola vez. Sin marcas, no debe oír «no seleccionado».
3. Pulse Derecha y después Izquierda. Deben leerse la columna siguiente y la anterior de la fila, sin mover el cursor.
4. Pulse Ctrl+3. Debe leerse la tercera columna.
5. Pulse Intro sobre la carpeta sub. Debe oír su nombre. Pulse Retroceso: debe volver a origen con el cursor en sub.
6. Pulse Tab. Debe oír el nombre del panel derecho con su carpeta. Pulse Ctrl+G, escriba C:\zc-pruebas\destino y pulse Intro.
7. Pulse Tab para volver al izquierdo. Pulse Ctrl+Mayús+P: debe decir la ruta del panel activo. Ctrl+Mayús+O: la del otro. Ctrl+Mayús+S: el resumen de la carpeta. Ctrl+Mayús+E: el espacio libre.
8. Pulse Ctrl+Mayús+U: debe repetir el último anuncio. Púlselo dos veces seguidas: debe decir su versión completa.
9. Pulse Ctrl+Mayús+H. Debe abrirse el historial de anuncios con su hora. Ciérrelo con Escape: el foco debe volver al panel y al elemento donde estaba.
10. Pulse F9. Debe abrirse la barra de menús. Recorra el menú Izquierdo con las flechas: cada elemento debe decir su tecla. Compruebe que el menú Derecho no dice las teclas (solo el del lado activo las anuncia). Cierre con Escape.

### 3. Marcas y cambio de modo de selección

Este es el riesgo 1 del diseño: el modelo de marcas solo se ha comprobado con MSAA. Hágalo con calma y anote cualquier repetición o silencio.

1. En origen, con el cursor en nota1.txt y sin marcas, pulse Abajo dos veces. Debe oír cada fila una vez, sin «no seleccionado».
2. Pulse Espacio. Debe oír «Marcado: nota3.txt» (o el nombre del cursor) y después la fila siguiente, una sola vez. Es el momento en que la lista pasa a selección múltiple.
3. Pulse Abajo y Arriba varias veces. En cada fila el lector debe decir si está seleccionada o no. La fila marcada debe decir «seleccionado»; las demás, «no seleccionado» o nada, según el lector. Moverse no debe cambiar las marcas.
4. Pulse Insert sobre otra fila. Si el lector se queda la tecla, anótelo y siga con Espacio. Con NVDA, pruebe a pulsar Insert dos veces seguidas.
5. Pulse Ctrl+Espacio sobre otra fila. Debe marcarla sin moverse.
6. Pulse Mayús+Abajo tres veces. Deben quedar marcadas las filas recorridas, sin perder las anteriores.
7. Pulse Ctrl+Mayús+S. Debe decir cuántos hay marcados y cuánto ocupan.
8. Pulse Tab y después Tab otra vez. Al volver al panel izquierdo, debe oír su nombre y «5 marcados» o el número que haya.
9. Pulse Ctrl+Mayús+A. Deben quitarse todas las marcas. La lista vuelve a selección simple: al moverse con Abajo no debe oír «no seleccionado» y la fila del cursor no debe repetirse.
10. Pulse Num +. Debe abrirse el campo del patrón. Escriba *.txt | nota1* y pulse Intro. Debe oír «Marcados» seguido del número de archivos y su tamaño. nota1.txt y nota10.txt deben quedar sin marcar. Si el lector se queda Num +, anótelo y use Ctrl+Mayús+M.
11. Pulse Ctrl+Mayús+Q, escriba nota2* y pulse Intro. Debe desmarcarse nota2.txt.
12. Pulse Ctrl+Mayús+N. Deben invertirse las marcas de los archivos.
13. Pulse Ctrl+R. Deben conservarse el cursor y las marcas, y debe oír «Actualizado».
14. Entre en sub con Intro y vuelva con Retroceso. Las marcas se han perdido (Ctrl+Mayús+R no las recupera: solo devuelve las de la última operación; se prueba en el capítulo 4).
15. Pulse Ctrl+F, escriba nota y pulse Abajo. Pulse Ctrl+A: deben marcarse solo los visibles. Pulse Escape: se quita el filtro y las marcas de las notas siguen. Lo que estaba marcado y no se veía (utf16.txt, grande.txt) vuelve a verse marcado; mientras estaba oculto no contaba en «marcados» (Ctrl+Mayús+S).
16. Desmarque todo con Ctrl+Mayús+A.

Señales de fallo que hay que anotar sin falta: el lector no dice «seleccionado» en una fila marcada, dice «seleccionado» en todas, repite la fila al marcar o al cambiar de modo, o se queda en silencio tras la primera marca.

### 4. Copiar con conflictos

1. En origen, marque nota1.txt a nota5.txt (Mayús+Abajo cinco veces desde nota1.txt). El cursor queda en nota6.txt, fuera de las marcas.
2. Pulse F5. Como el cursor está fuera de las marcas, primero debe preguntar «Hay 5 marcados y el cursor está en otro elemento. ¿Copiar los 5 marcados?». Responda «Sí». Debe abrirse el diálogo de copiar con el foco en «Destino», que debe contener C:\zc-pruebas\destino. Pulse Mayús+Tab hasta «Resumen»: debe decir «Copiar 5 archivos», su tamaño entre paréntesis y «a:».
3. Vuelva a «Destino» y pulse Intro. Tras el análisis debe abrirse la lista de conflictos con 3 filas (nota1.txt a nota3.txt). Cada fila debe leer Nombre, Origen, Acción («Omitir») y Destino.
4. Sobre la primera fila, pulse S. Debe oír la acción y el nombre, como «Sobrescribir: nota1.txt». Baje a la segunda y pulse C, y en la tercera pulse E: cada cambio debe anunciarse.
5. Seleccione las tres filas con Mayús+Arriba y pulse O. Debe oír «Omitir: 3 filas».
6. Vuelva a la primera, pulse S y después el botón «Aplicar a todos». Las tres deben quedar en Sobrescribir.
7. Pulse Tab hasta «Mostrar» y elija «Solo los de destino más reciente». Vuelva a «Todos».
8. Pulse «Continuar». Debe oír el resumen de la copia, por ejemplo «Copiar 5 elementos a C:\zc-pruebas\destino: terminada, 5 archivos» seguido del tamaño. Las marcas de origen deben quitarse.
9. Pulse Tab para ir al panel derecho: deben estar las notas copiadas y los paneles actualizados. Vuelva a origen con Tab y pulse Ctrl+Mayús+R: deben volver a marcarse nota1.txt a nota5.txt. Desmárquelas con Ctrl+Mayús+A.
10. Repita los pasos 1 y 2 con las mismas notas y pulse «Cancelar la operación» en la lista: no debe copiarse nada.
11. En Preferencias, página «Operaciones», desactive «Mostrar la lista de conflictos antes de copiar». Copie de nuevo nota1.txt. Debe salir la pregunta individual con el foco en «Omitir». Pulse Escape: debe omitirse. Vuelva a activar la lista.
12. Sitúese en nota6.txt, sin marcas, y pulse F6. El botón principal debe llamarse «Mover». Pulse Intro: nota6.txt debe desaparecer de origen.
13. Pulse Ctrl+Z en el panel. Debe preguntar «¿Deshacer:» y qué deshará. Acepte: debe oír «Deshecho:» y nota6.txt vuelve a origen.

### 5. Ventana de operaciones con F12

1. En origen, sitúese en grande.txt y pulse F5. En el diálogo, pulse F2 (En cola). La copia queda en cola o empieza enseguida.
2. Pulse F12. Debe abrirse la ventana de operaciones con el foco en la lista «Operaciones». La fila debe decir la operación, su estado y su progreso.
3. Pulse Tab hasta «Información de la operación». Recórralo con las flechas: debe mostrar la operación y las líneas «Estado», «Archivo actual», «Total», «Bytes», «Velocidad» y «Tiempo restante». Mientras está ahí, el texto debe actualizarse, pero el foco no debe moverse ni debe oírse nada sin pedirlo. Anote si el texto no cambia hasta que se mueve por la lista.
4. Pulse «Pausar». El botón debe pasar a «Reanudar» y el estado a «En pausa». Pulse «Reanudar».
5. Pulse Escape. La ventana se oculta y la operación sigue. Desde el panel, pulse Ctrl+Mayús+T: debe decir el porcentaje y el tiempo restante.
6. Al terminar debe oír el resumen sin interrumpir lo que el lector esté diciendo.
7. Prueba de decisión en segundo plano: copie otra vez grande.txt al mismo destino con F5 e Intro, y pase enseguida a otra ventana de Windows. Debe oír «Copiar grande.txt a C:\zc-pruebas\destino: espera su decisión». Al volver a zCommander, la lista de conflictos debe abrirse sola. Si no se abre, pulse F12 y «Atender la decisión pendiente». Elija Omitir y continúe.
8. Lance una copia larga y pulse F10. Debe decir «Hay 1 operaciones en curso.» o el número que haya, con los botones «Esperar y salir», «Cancelar las operaciones y salir», «No salir» y «Cancelar». Elija «No salir».

### 6. Eliminar

1. En destino, sitúese en una nota y pulse F8. Debe preguntar «¿Enviar a la papelera 1 archivo» con su tamaño, con los botones «Eliminar» y «Cancelar». Pulse «Eliminar». El cursor debe quedar en el elemento siguiente.
2. Pulse Mayús+Supr sobre otra nota. Debe preguntar «¿Eliminar DEFINITIVAMENTE 1 archivo» con su tamaño y «No se puede deshacer.», con el foco en «Cancelar». Pulse Escape: no debe borrarse nada.

### 7. Comprimidos

1. En el panel izquierdo, vaya a C:\zc-pruebas y pulse Intro sobre copia.zip. La etiqueta del panel debe decir la ruta con el comprimido: C:\zc-pruebas\copia.zip.
2. Pulse F3 sobre una nota: debe abrirse el visor con su texto. Ciérrelo con Escape.
3. Con el panel derecho en destino, marque dos notas y pulse F5. Debe abrirse el diálogo de copiar: es la extracción. Si hay conflictos, debe salir la lista de conflictos.
4. Pulse Retroceso en la raíz del comprimido: debe volver a C:\zc-pruebas con el cursor en copia.zip.
5. Vaya a origen, marque tres notas y pulse Alt+F5. Elija el formato 7z y acepte. Al terminar, el 7z debe estar en el otro panel.
6. Entre en el 7z con Intro. Pulse F7: no debe poder crear la carpeta y debe oír «Aquí no se pueden crear carpetas».
7. Sobre el 7z, pulse Alt+Mayús+F9. Debe dar el resumen de la prueba sin errores.
8. Con los consejos activos y el detalle «Detallado» (perfil Novato), al entrar en un comprimido debe oír «Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido».

### 8. FTP

Con el servidor FTP de prueba en marcha:

1. Pulse Ctrl+K. Debe abrirse «Conexiones FTP y SFTP». Sin sitios, debe decir «No hay sitios guardados. Pulse Nuevo para crear uno.» con el foco en «Nuevo».
2. Pulse «Nuevo». Rellene «Nombre del sitio» Prueba, protocolo FTP, servidor 127.0.0.1, puerto 2121, usuario prueba y la contraseña del servidor. Cada campo debe anunciar su etiqueta. Acepte: debe oír «Sitio Prueba creado».
3. Pulse «Conectar». Debe salir el aviso de que la contraseña viaja sin cifrar, con «Conectar igualmente» y «Cancelar». Pulse «Conectar igualmente». El panel activo debe decir «Izquierdo: ftp://prueba@127.0.0.1:2121/» y listar remoto.txt.
4. Pulse F3 sobre remoto.txt: debe verse su texto.
5. Copie remoto.txt al otro panel con F5. Debe terminar con su resumen.
6. Copie una nota del otro panel al servidor. Debe aparecer en el panel remoto.
7. Pulse Mayús+F6 sobre el archivo subido y renómbrelo. Elimínelo con F8.
8. En el menú Comandos, submenú Red, elija «Desconectar». Debe oír «Desconectado de ftp://prueba@127.0.0.1:2121/» y el panel debe volver a la última carpeta del disco en la que estuvo.
9. Edite el sitio con una contraseña equivocada y conecte. Debe oír «No se pudo conectar con Prueba: Usuario o contraseña incorrectos.».
10. Pare el servidor y conecte. Debe oír que no se pudo conectar y el motivo, sin que la ventana se congele.
11. Conexión rápida: pulse Ctrl+G y escriba ftp://prueba@127.0.0.1:2121/ con el servidor en marcha. Debe conectar o pedir la contraseña.

Si dispone de un servidor SFTP, conéctese una vez y compruebe que la primera vez sale «Servidor desconocido» con la huella y los botones «Aceptar y recordar», «Aceptar solo esta vez» y «Cancelar».

### 9. Visor

1. En origen, pulse F3 sobre utf16.txt. Debe abrirse el visor con el foco en el texto. Recorra con las flechas: deben leerse bien «año», «acción» y «pingüino».
2. Pulse Ctrl+Mayús+I. Debe decir la barra de estado del visor, con la codificación UTF-16.
3. Pulse F4. Debe pasar a hexadecimal; la primera línea empieza por 00000000. Pulse F4 otra vez para volver al texto.
4. Pulse F8. Debe abrirse el diálogo «Codificación». Elija «Windows-1252 (ANSI)»: el texto debe verse mal. Vuelva a F8 y elija «UTF-16 (little endian)».
5. Pulse F2. Debe oír «Ajuste de línea activado» o «desactivado».
6. Cierre con Escape y abra grande.txt con F3. Mientras carga, el texto dice «Cargando...». Pulse Ctrl+Mayús+I: la barra de estado debe decir el tamaño y «bloque 1 de» y el total.
7. Pulse Ctrl+F, escriba Línea 650000 y busque. Debe encontrarla aunque esté en otro bloque. Pulse F3: busca la siguiente coincidencia.
8. Pulse Ctrl+G y vaya a la línea 10. Pulse Ctrl+Av Pág: debe pasar al bloque siguiente y decir «Bloque 2 de» y el total.
9. Pulse F10. El visor se cierra y el foco vuelve al panel, al mismo archivo.
10. Pulse F4 sobre una nota. Debe abrirse el editor con el foco en el texto. Escriba algo y pulse Escape: debe preguntar si guardar, con «Guardar», «No guardar» y «Cancelar». Pulse «Cancelar», después F2 para guardar (debe oír «Guardado:» y el nombre) y Escape para cerrar. Ábrala con F3 y compruebe el cambio.

### 10. Renombrado múltiple

1. En origen, marque nota1.txt a nota5.txt y pulse Ctrl+M.
2. El foco debe estar en «Máscara del nombre», con [N]. Escriba documento_[C] y espere un momento.
3. Vaya a la lista de vista previa. Cada fila debe leer Nombre actual, Nombre nuevo y Estado «Correcto».
4. Cambie la máscara a documento (sin contador). La vista previa debe decir «Duplicado». Pulse el botón «Renombrar»: debe salir un mensaje que empieza por «No se puede renombrar:» y dice la primera fila con problemas; al cerrarlo, el foco debe ir a esa fila y no debe renombrarse nada.
5. Vuelva a documento_[C10+5:3]. Los nombres nuevos deben ser documento_010, documento_015 y así sucesivamente. Renombre.
6. En el panel, pulse Ctrl+Z. Debe preguntar «¿Deshacer: Renombrar 5 elementos en» con la carpeta. Acepte: debe oír «Deshecho:» y vuelven los nombres originales.

### 11. Preferencias

1. Pulse Ctrl+coma. Debe abrirse Preferencias en la página General, con el foco en la primera opción.
2. Pulse Ctrl+Tab para recorrer las páginas: General, Paneles, Vista, Accesibilidad, Operaciones, Visor y editor, Búsqueda y Red. El lector debe decir el nombre de cada página.
3. En cualquier opción, pulse Ctrl+H. Debe explicar para qué sirve.
4. En Accesibilidad, cambie «Detalle de los anuncios» a «detallado» y pulse «Aplicar». Sin cerrar, vuelva al panel y entre en una carpeta: ahora debe decir también el número de elementos.
5. Vuelva a Preferencias, página «Accesibilidad», pulse «Valores de fábrica de esta página» y confirme. Debe oír «Valores de fábrica puestos en la página Accesibilidad. Pulse Aceptar para guardarlos.». Solo deben cambiar las opciones de esa página. Pulse «Cancelar»: no debe guardarse nada.
6. Abra el menú Opciones, «Perfil de usuario». Debe decir «Perfil actual: Intermedio». Elija Novato en la lista «Perfiles» y pulse «Aplicar el perfil»: debe preguntar «¿Aplicar el perfil Novato?» y cuántas preferencias cambiarán. Acepte: debe oír «Perfil Novato aplicado:» con el número. La línea de órdenes debe ocultarse al momento. Vuelva a Intermedio.

### 12. Mapa de teclas

1. Abra el menú Opciones, «Mapa de teclas». La lista debe leer Orden, Teclas y Ámbito.
2. Escriba Ver para buscar. Elija «Ver con el visor externo».
3. Pulse «Cambiar» y después Ctrl+R. Debe avisar «Ctrl+R ya es Volver a leer: ¿quitársela?». Responda que no.
4. Busque «Cambiar de panel» y pulse «Cambiar»: no debe dejar cambiar Tab, porque es una tecla fija.
5. Pulse «Restablecer todas» y cierre.

### 13. Paleta de órdenes y ayuda de teclado

1. Pulse Ctrl+E. Debe abrirse la «Paleta de órdenes» con el foco en el campo «Buscar».
2. Escriba copiar. La lista debe quedarse con las órdenes de copiar. Baje con Abajo y elija «Copiar las rutas completas». Pulse Intro: debe ejecutarse y anunciar «Atajo: Ctrl+Mayús+C».
3. Pulse Mayús+F12. Debe anunciar «Modo de ayuda de teclado activado: cada tecla dice qué hace. Escape sale.».
4. Pulse F5. Debe decir «Copiar» y su ayuda, sin abrir el diálogo. Pulse F8: debe decir «Eliminar» sin eliminar nada.
5. Pulse Escape. Debe anunciar «Modo de ayuda de teclado desactivado». Pulse Mayús+F12 dos veces para comprobar que también sale con la misma tecla.

### 14. Ayuda, manual y lista de teclas

1. Pulse F1. Debe abrirse el manual en un visor no modal.
   - Si se ve como página: con el modo exploración, H debe saltar de encabezado en encabezado.
   - Si se ve como texto: el foco empieza en el contenido; Mayús+Tab lleva a la lista «Secciones». Elija «Copiar y mover con F5 y F6» y pulse Intro: el cursor del contenido debe saltar a ese encabezado y el lector debe leerlo.
2. Pulse Ctrl+F, escriba conflictos y acepte. Debe ir a la primera coincidencia. F3 va a la siguiente.
3. Sin cerrar el manual, vuelva a la ventana principal: debe poder usarla.
4. Vuelva al manual y pulse Escape: se cierra.
5. Pulse Mayús+F1. Debe abrirse la lista de teclas en el visor, con el título «Teclas de la aplicación».
6. Con el foco en el panel, pulse Ctrl+H. Debe explicar el panel. Repítalo en la línea de órdenes (Mayús+F2).
7. En el menú Ayuda, elija «Información para soporte». Debe anunciar «Información para soporte copiada al portapapeles».

### 15. Línea de órdenes

1. Pulse Mayús+F2. El foco debe ir a la línea de órdenes.
2. Escriba dir y pulse Intro. Debe oír «Ejecutando» y, al terminar, «Orden terminada, código 0».
3. Pulse Ctrl+O. Debe anunciar «Salida de las órdenes» con el foco al final de la salida. Recórrala con las flechas. Pulse Ctrl+O otra vez: vuelve a los paneles, al elemento donde estaba.
4. Vuelva a la línea, pulse Arriba: debe recuperar dir. Pulse Escape: se vacía. Escape otra vez: vuelve al panel.
5. Escriba ping -n 60 127.0.0.1 y pulse Intro. Con la línea vacía, pulse Escape: debe oír «Orden detenida» y el foco sigue en la línea. Repítalo pulsando Escape en el panel (sin filtro rápido): también debe oír «Orden detenida».

## Recorrido de la versión 2.0

Esta parte comprueba lo que añade zCommander 2.0 (objetivo 1 de la sección 1.2 de docs/diseno-2.md). Se hace también con NVDA, con JAWS y con Narrador, después del recorrido común. Casi nada de esta parte se ha probado todavía con un lector de pantalla real: cada paso que falle es un hallazgo valioso.

### Preparación de la 2.0

- Use la versión compilada para el capítulo 25 (complemento de NVDA) y el 30 (compilación); el resto vale también desde el código.
- Prepare, si puede, un RAR sin cifrar, un RAR en dos partes y un RAR cifrado (con 7-Zip o WinRAR), un PDF con varias páginas, un MP3 con etiquetas, una foto con datos EXIF y un CSV. Póngalos en C:\zc-pruebas\2.0.
- Empaquete el complemento de prueba desde la raíz del proyecto, para el capítulo 17:

```
.venv\Scripts\python tools\empaquetar_plugin.py tests\datos\plugins\ejemplo --salida C:\zc-pruebas\2.0\ejemplo.zcplugin
```

- Anote el resultado de cada paso como en el recorrido común. Si un paso no se puede hacer (no tiene NAS, ni cuenta de nube, ni 7-Zip), anote «no probado» y por qué.

### 16. Sonidos

1. Arranque la 2.0 por primera vez (también tras actualizar desde la 1.0). Una sola vez debe oír que los sonidos están activados y que se desactivan en Preferencias, Sonidos, o con Ctrl+F11.
2. Pulse Ctrl+F11: «Sonidos desactivados». Otra vez: «Sonidos activados», con un sonido.
3. En el menú Opciones, submenú Sonidos, use «Subir el volumen de los sonidos»: debe oír «Volumen de los sonidos: 80» y una muestra.
4. Abra Preferencias, página «Sonidos». El deslizador «Volumen» debe leerse «70 de 100» (o el valor actual). En la lista «Sonidos», Espacio debe decir «marcado» o «no marcado»; Ctrl+A y Ctrl+Mayús+A deben decir «Todas marcadas» o «Todas desmarcadas» una sola vez; Intro debe hacer sonar el sonido elegido.
5. Active «Los sonidos sustituyen a algunos anuncios» y marque un archivo con Espacio: debe sonar y no decirse «Marcado». Ponga el volumen a 0: debe volver a decirse.
6. En el menú Ayuda, abra «Mapa de sonidos». Escuche los cinco paquetes: dentro de cada uno, marcar y desmarcar, entrar y subir, cambiar de panel, error, operación terminada y progreso deben distinguirse sin mirar; ninguno debe tapar la voz ni cansar; el volumen debe ser parejo. Si usa un portátil, compruebe que los sonidos graves de Suave y Cristal se oyen.
7. Abra «Paquetes de sonidos», elija Clásico y pulse «Nuevo a partir de este...». Cada paso debe anunciarse, por ejemplo «Paso 2 de 4: Datos». En el paso Sonidos, «Sustituir por un archivo WAV...» con un WAV de 24 bits debe dar un mensaje claro de por qué no vale.
8. Exporte el paquete como .zcsonidos, bórrelo y vuelva a instalarlo con Intro sobre el archivo en un panel.

### 17. Complementos

1. Abra el menú Complementos. Debe tener «Gestor de complementos», «Instalar un complemento desde un archivo» y un submenú por complemento. Recorra dos submenús.
2. Abra el «Gestor de complementos». La lista debe leerse por columnas (Nombre, Versión, Estado, Origen, Confianza, Autor) y «Detalles» debe cambiar al moverse sin quitar el foco.
3. Elija un complemento de serie y pulse Espacio: «inhabilitado». Sus órdenes deben desaparecer de los menús. Pulse Espacio otra vez para habilitarlo.
4. Pulse Intro sobre un complemento con opciones: debe abrirse Preferencias en su página.
5. En un panel, pulse Intro sobre el .zcplugin del complemento de prueba. El «Resumen del complemento» debe leerse entero con las flechas y, al no estar firmado, el botón predeterminado debe ser «Cancelar». Instálelo y ejecute su orden desde el menú Complementos.
6. Desinstálelo con Supr en el gestor: dos preguntas con «No» como botón predeterminado.
7. Cierre zCommander y arránquelo con Mayús pulsada: debe oír «Modo seguro: complementos desactivados». Vuelva con Ayuda, «Reiniciar zCommander».
8. Copie a mano la carpeta tests\datos\plugins\ejemplo dentro de data\plugins y arranque: debe preguntar si aceptarlo, con el foco en «No aceptarlo». Respóndalo y borre después esa carpeta.

### 18. Actualizar zCommander

1. En el menú Ayuda, elija «Buscar actualizaciones». Si no hay versión nueva, debe oír «Sin novedades: zCommander está al día» y la versión, con un sonido.
2. Si hay una versión publicada más nueva que la que prueba (o con una versión anterior instalada aparte), el diálogo «Actualización disponible» debe abrirse con el foco en «Novedades». El progreso debe anunciarse al 25, 50, 75 y 100 %, sin más.
3. Con una copia en marcha, pulse «Actualizar ahora»: debe preguntar con «Esperar y actualizar», «Cancelar las operaciones y actualizar» y «No actualizar ahora».
4. Tras actualizar, zCommander debe volver a abrirse solo y decir «zCommander se ha actualizado a la versión» y su número.

La prueba completa contra el servidor real (https://xebolax.synology.me/zCommander/) está pendiente: hágala con la primera versión publicada después de la 2.0.0.

### 19. Componentes externos

1. En el menú Opciones, abra «Componentes externos». La lista debe leerse por columnas y las filas sin versión nueva no deben tener casilla.
2. Pulse «Buscar versiones nuevas»: el texto «Estado» y los anuncios deben decir qué hace, sin quitar el foco.
3. Pulse «Restaurar los componentes originales...»: la pregunta debe tener el foco en «No». Respóndala «No».
4. Si hay una versión nueva de algún componente, márquela, pulse «Actualizar los elegidos» y escuche las fases («Descargando», «Comprobando», «Probando») y el resumen final.

### 20. Copias de seguridad y perfiles

1. En Opciones, submenú «Copia de seguridad», abra «Crear una copia de seguridad». En la lista «Qué guardar», Espacio debe decir «marcado» o «no marcado». Elija «Incluirlas cifradas con una contraseña» y escriba una contraseña corta: «Fortaleza» debe decir que es débil.
2. Cree la copia: debe oír «Copia creada:» con su tamaño y sus partes.
3. Cambie un favorito y restaure la copia con Intro sobre el .zcbackup. El «Resumen» debe leerse entero. La lista «Órdenes que se podrán ejecutar» debe salir sin marcar y decir el texto completo de cada orden.
4. Restaure con una contraseña equivocada: debe decir «La contraseña no es correcta o la copia está dañada» y dejarle reintentar sin perder lo elegido.
5. Con una parte que se aplica al reiniciar, elija «Más tarde» y vuelva a arrancar: debe preguntar con «Aplicarla ahora», «Descartarla» y «Más tarde».
6. Si la copia trae huellas de servidores distintas, cada pregunta debe tener el foco en «No aceptarla».
7. Exporte un perfil (.zcperfil) e impórtelo: la lista «Qué se aplica» debe leerse con sus casillas y la de órdenes debe salir sin marcar.

### 21. Comprimidos

1. Entre con Intro en el RAR sin cifrar y en el RAR en dos partes (desde la segunda parte): deben listarse como carpetas.
2. Entre en el RAR cifrado sin 7-Zip instalado: debe sonar el aviso y decir «Este RAR está cifrado. zCommander no puede descifrarlo sin 7-Zip instalado.». Con 7-Zip instalado, debe pedir la contraseña.
3. Marque unas notas y pulse Alt+F5. Recorra «Formato»: debe ofrecer ZIP (Zstandard), ZIP cifrado con AES-256, TAR.ZST e ISO, entre otros. Elija «ZIP cifrado con AES-256»: «Contraseña» se habilita y el texto «Motor» dice qué programa lo creará.
4. Cree un .zst de un solo archivo y entre en él con Intro: debe verse como una carpeta con un archivo.

### 22. Red

1. Pulse Ctrl+Mayús+K. La lista debe leerse por columnas (Nombre, Tipo, Remoto, Estado). Mientras busca equipos, la fila «Buscando equipos...» no debe mover el cursor ni hacer que el lector repita la fila; al terminar debe oír «Búsqueda terminada:» y el número de equipos.
2. Pulse Escape mientras busca: la búsqueda se detiene. Ctrl+R la relanza.
3. Abra «Conectar unidad de red». Ctrl+H en «Carpeta de red» debe explicar también las formas de WebDAV, SSHFS y NFS. Conecte un recurso con «Automática (la elige Windows)».
4. Pulse F8 en la raíz «Red»: debe decir que use «Desconectar unidad de red». Desconéctela: la pregunta de forzar, si sale, debe tener el foco en «No».
5. Con zCommander como administrador, «Información de la conexión» debe decir la versión de SMB y si va cifrada; sin elevar, debe decirse el resto sin errores.

### 23. Personalización

1. Pulse Ctrl+Mayús+G, vaya a una carpeta, marque por patrón *.txt y vuelva a pulsar Ctrl+Mayús+G. El título debe haber dicho «Grabando macro». Póngale nombre, márquela «En el menú Mis órdenes» y ejecútela desde Mis órdenes (Alt+R). Ctrl+Mayús+L debe repetirla.
2. En Opciones, Personalización, «Esquema de teclas»: elija Total Commander. La lista «Teclas que cambian» debe leerse por columnas y decir «queda sin tecla» donde toque. Aplíquelo, compruebe que Ctrl+S abre el filtro rápido y vuelva a Norton Commander.
3. Active la barra de botones y pulse Alt+Mayús+F11: debe sonar y el lector debe decir el botón. Izquierda, Derecha, Inicio y Fin deben recorrerla; Escape vuelve al panel.
4. Cree un alias ll con la orden dir /a %1 y pruébelo con «Probar...». En la línea de órdenes, escriba zc ir y pulse Ctrl+Espacio: debe completar o decir cuántas opciones hay; la segunda pulsación abre una lista.
5. Guarde un espacio de trabajo con Ctrl+Mayús+W, cambie de carpetas y ábralo: debe oír «Espacio de trabajo» y su nombre. El espacio «Anterior» debe devolverle a donde estaba.
6. Cree una regla con solo color: el editor debe avisar «Este efecto solo se ve». Póngale un texto y compruebe que se lee en la columna Regla y con «Probar con el elemento del cursor».
7. En «Orden de lectura de las columnas», deje solo Nombre y Tamaño: al moverse con Izquierda y Derecha solo deben leerse esas. Intente marcar más de 15 columnas: debe decir «Como mucho 15 columnas se leen al moverse».
8. Active «Menús según el nivel del perfil» con el perfil Novato: los menús deben acortarse y terminar en «Ver todas las órdenes en los menús».
9. Abra Preferencias. Con el foco en el árbol, las flechas deben cambiar de página y el lector decir su nombre. Escriba «papelera» en «Buscar una opción»: Abajo pasa a «Opciones que coinciden» e Intro lleva a la opción. En la página «Confirmaciones», la lista con casillas debe decir su estado.
10. Active las teclas globales, dé Ctrl+Alt+Mayús+Z a «Traer zCommander al frente», pase a otro programa y púlsela: zCommander debe venir al frente.
11. En la paleta (Ctrl+E), marque una orden con Ctrl+D: debe aparecer la primera con el campo vacío.

### 24. Visor por secciones

1. Pulse F3 sobre el PDF. La barra de estado debe decir «Sección 1 de» y el total. F6 y Mayús+F6 deben cambiar de sección y anunciarlo.
2. Ctrl+L debe abrir la lista de secciones con su campo de búsqueda; Ctrl+P debe ir a una página.
3. En Buscar archivos (Alt+F7), página Contenido, debe estar «Buscar también dentro de documentos»; en Avanzado, «Motor de búsqueda».

### 25. Complemento de zCommander para NVDA (solo con NVDA)

Nada de este capítulo se ha probado aún con NVDA real. Use la versión compilada.

1. En el menú Ayuda, elija «Instalar el complemento de zCommander para NVDA». El diálogo debe tener «Abrir el instalador de NVDA» y «Cancelar», este como predeterminado. Instálelo: NVDA pide confirmación y se reinicia.
2. Busque archivos con una ruta de más de 511 caracteres y envíe los resultados al panel: la columna Ruta debe leerse entera al moverse y con NVDA+Mayús+J.
3. Vuelva a leer la carpeta (Ctrl+R), aplique un filtro y restaure las marcas (Ctrl+Mayús+R): NVDA no debe repetir el elemento en el que ya estaba.
4. Desactive «Movimientos del foco silenciosos con el complemento de NVDA» en Preferencias, página «Accesibilidad»: en el paso 3, NVDA sí debe repetirlo.
5. Con un orden de lectura de tres columnas (capítulo 23, paso 7), al moverse solo deben leerse esas, en ese orden. Con NVDA en «Cabeceras de tabla: no», sin cabeceras.
6. NVDA+Mayús+J dos veces seguidas debe abrir una ventana con la fila completa. El gesto debe aparecer en «Gestos de entrada», categoría «zCommander».
7. Desactive el complemento en la Tienda de complementos de NVDA: zCommander debe leerse como sin él.
8. Tras probarlo, suba NVDA_PROBADA en tools\construir_complemento.py a la versión de NVDA usada.

### 26. Acerca de y licencias

1. En el menú Ayuda, abra «Acerca de zCommander». El lector debe decir «Información» y poder leer el texto con las flechas.
2. «Ver la licencia», «Componentes de terceros» y «Oferta de fuentes» deben abrir el visor de ayuda con el foco en el contenido.
3. «Copiar la información» debe anunciar «Información copiada al portapapeles».

### 27. Complementos de serie

Recorra al menos la orden principal de cada uno, con su ayuda (F1) abierta. Anote en especial:

1. Reproductor: Ctrl+Mayús+F5 sobre el MP3; Alt+Mayús+F5 pausa desde el panel; en su ventana (Alt+Mayús+F2), Espacio y P. Cerrar la ventana no debe parar la música.
2. Lector de documentos: F3 sobre el PDF (capítulo 24) y «Propiedades del documento».
3. OCR: Ctrl+Mayús+F3 sobre una imagen con texto; el texto debe abrirse en el visor y oírse el aviso de fin.
4. Metadatos: Ctrl+Mayús+F2 sobre el MP3; con varios archivos, los campos distintos deben decir «(sin cambio)». Tras guardar, Ctrl+Z en el panel debe deshacer el cambio.
5. Búsqueda instantánea: Ctrl+Mayús+F, escriba y pulse Intro: va al primer resultado.
6. Conversor FFmpeg: Ctrl+Mayús+F6; la conversión debe verse en F12.
7. Duplicados: Mayús+F7; al cambiar de grupo debe decir, por ejemplo, «Grupo 3 de 40, 2 copias»; la casilla de cada copia debe decir su estado.
8. Ocupación: Ctrl+Mayús+F7; al abrirse en el panel debe estar ordenada de mayor a menor; las listas de archivos grandes y por extensión deben leerse por columnas.
9. Procesos: Ctrl+Mayús+F12; intente borrar un archivo abierto en otro programa y compruebe la acción de error «Cerrar ese programa y reintentar».
10. Editor hexadecimal: Ctrl+Mayús+F4; Tab entre columnas, Ctrl+Mayús+I dice la barra de estado.
11. Imágenes: información con Ctrl+Mayús+I sobre la foto; «Ver la imagen ampliada». La primera «Describir la imagen» debe avisar de privacidad.
12. Cifrado: Ctrl+Mayús+F8 sobre una nota; Intro sobre el .zcc debe descifrarlo.
13. Notas: Ctrl+N sobre un archivo y sobre «..»; las columnas Comentario y Etiquetas deben leerse.
14. Proyectos: Ctrl+Mayús+J, Abajo pasa a la lista e Intro abre.
15. Portapapeles: copie algo en el Bloc de notas y abra Ctrl+Mayús+V.
16. Lectura en voz: Ctrl+F9 sobre una nota; otra vez pausa.
17. Monitor, programador, sincronización, seguridad, Git, tablas, organizador y codificaciones: abra su ventana principal y recórrala con Tab; todos los controles deben tener nombre y Ctrl+H debe explicarlos.
18. Papelera: Ctrl+F8 debe abrirla ordenada por fecha, la más reciente primero; «Vaciar la papelera» debe tener el foco en «Cancelar». Cierre zCommander con la papelera abierta en una pestaña y vuelva a abrirlo: debe volver a la papelera.

### 28. Nubes

Sin cuentas reales solo se puede probar parte. Anote qué servicios ha probado.

1. Pulse Alt+F11: la ventana «Cuentas de nube» debe leerse por columnas.
2. «Añadir una cuenta de nube...»: el asistente debe dejar buscar el servicio y leer cada pregunta de rclone con su ayuda.
3. Con un servicio que se autoriza en el navegador, el diálogo de espera debe tener un texto de estado legible, una barra y un anuncio como mucho cada 30 segundos.
4. Con una cuenta añadida: Intro la abre en el panel; F5 y F6 con conflictos; Ctrl+R vuelve a leer la carpeta de la nube.
5. «Sincronizar con la nube...»: la lista de cambios de la simulación debe leerse fila a fila antes de confirmar.
6. «Propiedades...» de una cuenta: sus pestañas deben recorrerse con Ctrl+Tab.

Siguen sin comprobar con cuentas reales: Google Drive con identificador propio, OneDrive y SharePoint, Dropbox, Box, pCloud, Mega, S3, B2, Yandex, Koofr, kDrive, Jottacloud, Internxt, Filen, Proton Drive, iCloud Drive y un Nextcloud real, la detección de Google Drive para escritorio y el montaje con WinFsp.

### 29. NAS Synology

Primero con el NAS de demostración (menú Complementos, «NAS Synology», «NAS de demostración»):

1. Pulse Ctrl+Mayús+F9: la ventana del NAS debe abrirse en el área Estado. F6 pasa de áreas a elementos; Ctrl+R vuelve a leer; Ctrl+Mayús+T dice el uso de recursos; la lista de elementos se lee por columnas.
2. Con el foco en un botón desactivado, Ctrl+H debe explicar por qué (modo solo lectura).
3. «Permitir cambios en el NAS»: el foco inicial debe estar en la opción segura; el título debe empezar por «CAMBIOS PERMITIDOS».
4. Apagar el NAS de demostración: dos confirmaciones, la segunda pide escribir el nombre.
5. Comprima y extraiga en el NAS: el progreso debe verse en F12.
6. Al dar de alta un NAS, los diálogos de huella y de código de verificación deben tener el foco en la opción segura.

Después, si tiene un NAS Synology, haga en modo solo lectura las comprobaciones del apartado «Qué conviene probar con su NAS» del manual, y anote el modelo y la versión de DSM.

### 30. Compilación en un equipo limpio

1. Copie la carpeta compilada a un Windows sin Python ni el redistribuible de Visual C++ y arranque ZCommander.exe: debe abrirse con el asistente.
2. Ejecute ZCommander.exe --comprobar-arranque --complemento-prueba con la carpeta del complemento de ejemplo: debe terminar con código 0.

## Con NVDA

### Preparación con NVDA

- NVDA 2025 o posterior. Haga el recorrido con la distribución de teclado de escritorio y repita el capítulo 3 con la de portátil.
- Abra el visor de voz de NVDA (menú de NVDA, Herramientas) para copiar exactamente lo que se dice.
- En Preferencias de zCommander, página «Accesibilidad», deje «Salida de los anuncios» en «Automática»: los anuncios deben llegar por voz directa.

### Qué mirar con NVDA

- Capítulo 3: con la distribución de escritorio, compruebe si Num +, Num - y Num * llegan a zCommander o se los queda NVDA. Anote el resultado; las alternativas Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N deben funcionar siempre.
- Capítulo 3: Insert pulsado una vez no debe marcar (es la tecla de NVDA); pulsado dos veces seguidas debe marcar.
- Los anuncios de zCommander no deben cortar la lectura de la fila al moverse: primero la fila, después el anuncio.
- Capítulo 14: el manual en formato de página debe abrirse en modo exploración.
- Cambie «Salida de los anuncios» a «Siempre por notificaciones» y repita los pasos 7 y 8 del capítulo 2: NVDA también debe leer las notificaciones de Windows.
- Capítulo 25: todo el capítulo del complemento de NVDA es solo para NVDA. Hágalo dos veces: con el complemento y sin él.
- Capítulos 16 y 23: con «Los sonidos sustituyen a algunos anuncios», compruebe que NVDA no se queda callado en ningún paso que no tenga sonido.

## Con JAWS

### Preparación con JAWS

- JAWS 2025 o posterior, con su configuración por defecto.
- Si su versión tiene historial de voz, úselo para copiar lo que se dice.
- «Salida de los anuncios» en «Automática»: los anuncios deben llegar por voz directa.

### Qué mirar con JAWS

- Capítulo 3: JAWS debe decir el estado de selección de cada fila en la lista con marcas. Anote si dice «seleccionado» o «no seleccionado», y si repite la fila al pasar de selección simple a múltiple.
- Capítulo 3: compruebe si JAWS se queda Num +, Num - o Num *. Insert es la tecla de JAWS: marque con Espacio.
- Compruebe que el cursor virtual de JAWS no se activa en la lista de archivos ni en los diálogos: las flechas deben mover el cursor de la lista.
- Capítulo 4: en la lista de conflictos, las letras S, O, C y E deben cambiar la acción y no saltar a otra fila.
- Capítulo 14: el manual en formato de página debe recorrerse con el cursor virtual y H.
- Capítulos 17, 19, 20 y 29: en las listas con casillas (complementos, componentes, partes de la copia, órdenes que se podrán ejecutar), JAWS debe decir «marcado» o «no marcado» al pulsar Espacio y al moverse.
- Capítulo 23, paso 9: el árbol de páginas de Preferencias debe leerse como árbol, sin activar el cursor virtual.

## Con Narrador

### Preparación con Narrador

- Narrador de Windows 11. Las notificaciones necesitan Windows 10 versión 1709 o posterior.
- «Salida de los anuncios» en «Automática»: con Narrador, zCommander debe usar las notificaciones de Windows.

### Qué mirar con Narrador

Este es el riesgo 9 del diseño: las notificaciones solo se han probado por programa.

- Capítulo 2, pasos 7 y 8: Narrador debe decir las rutas, el resumen, el espacio libre y el último anuncio. Si no dice nada, anótelo: es la señal del riesgo 9.
- Capítulo 5: un aviso esencial (fin de la copia) no debe perderse aunque esté navegando a la vez. Muévase por la lista mientras termina una copia y compruebe que se oye el resumen.
- Capítulo 3: Narrador debe decir el estado de selección de las filas en la lista con marcas.
- Si usa Insert como tecla de Narrador, marque con Espacio.
- Capítulo 14: el manual en formato de página debe recorrerse con el modo de examen de Narrador.
- Capítulos 22 y 28: las esperas largas (búsqueda de equipos, autorización de una nube) deben anunciarse por notificaciones sin cortar la lectura de la lista.
- Capítulo 16: el deslizador de volumen debe leerse con su valor («70 de 100»).

## Lista de comprobación para el informe

Copie esta lista una vez por lector y anote en cada línea «correcto» o lo que falló:

- Lector, versión y distribución de teclado:
- Versión de zCommander y si es compilada o desde el código:
- 1. Arranque y asistente:
- 2. Paneles, foco y navegación:
- 3. Marcas y cambio de modo de selección:
- 4. Copiar con conflictos:
- 5. Ventana de operaciones:
- 6. Eliminar:
- 7. Comprimidos:
- 8. FTP:
- 9. Visor y editor:
- 10. Renombrado múltiple:
- 11. Preferencias y perfil:
- 12. Mapa de teclas:
- 13. Paleta y ayuda de teclado:
- 14. Ayuda, manual y lista de teclas:
- 15. Línea de órdenes:
- 16. Sonidos:
- 17. Complementos:
- 18. Actualizar zCommander:
- 19. Componentes externos:
- 20. Copias de seguridad y perfiles:
- 21. Comprimidos 2.0:
- 22. Red:
- 23. Personalización:
- 24. Visor por secciones:
- 25. Complemento de NVDA (solo NVDA):
- 26. Acerca de y licencias:
- 27. Complementos de serie:
- 28. Nubes (servicios probados):
- 29. NAS Synology (demostración y, si lo hay, modelo y DSM del NAS real):
- 30. Compilación en un equipo limpio:
- Registro de la sesión adjunto:
