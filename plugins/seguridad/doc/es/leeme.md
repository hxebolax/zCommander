# Seguridad de descargas e integridad

Ayuda a decidir si un archivo es de fiar: su firma digital, su suma, el análisis de Microsoft Defender, lo que sabe VirusTotal y si viene de Internet.

## Órdenes

Están en el menú Complementos, submenú «Sistema y seguridad», submenú «Seguridad de descargas e integridad», y en la paleta de órdenes. Ninguna tiene tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Comprobar la firma digital**: firma Authenticode del archivo del cursor. Por ejemplo: «Firmado por Mozilla Corporation, firma válida», «Sin firma» o «Firma no válida: el archivo ha cambiado después de firmarse». Muchos archivos de Windows están firmados en un catálogo del sistema, y así se dice. Nunca se consulta Internet para esto.
- **Comparar la suma con el portapapeles**: copie la suma que publica la página de descarga (SHA-256, SHA-1, MD5 o SHA-512; da igual mayúsculas, minúsculas o espacios) y ejecute la orden sobre el archivo: «Coincide con el SHA-256 del portapapeles» o «No coincide». Si el portapapeles no tiene una suma, dice la del archivo.
- **Analizar con Defender**: analiza los elementos de trabajo con Microsoft Defender (no borra ni pone en cuarentena nada) y dice si encontró amenazas.
- **Buscar en VirusTotal**: busca la suma SHA-256 del archivo en VirusTotal. **Nunca se envía el archivo, solo su suma.** Hace falta una clave personal de VirusTotal (gratuita, en su perfil de virustotal.com): la primera vez se pide y se guarda cifrada en este equipo. La primera vez también se avisa de qué se envía y a dónde.
- **Quitar la marca de la Web...**: Windows marca lo descargado de Internet para avisar antes de abrirlo. Esta orden quita esa marca de los archivos elegidos, con confirmación. Hágalo solo si confía en su origen.

## Columnas e información del elemento

- Columna **Firma**: el firmante, «Sin firma» o «No válida» (en ejecutables, bibliotecas, instaladores y guiones).
- Columna **Origen**: «Internet», «Intranet»... si el archivo tiene la marca de la Web.
- En la información del elemento (Ctrl+Mayús+I): la firma, la empresa, el producto, la versión y la arquitectura de los ejecutables, y de dónde se descargó el archivo.

## Preferencias

En Preferencias, Complementos, Seguridad de descargas e integridad, General:

- **Analizar con Defender lo que se copia desde FTP, SFTP o una nube**: desactivada de fábrica. Al terminar la copia, avisa si Defender encuentra algo.
- **Suma que se calcula si el portapapeles no tiene ninguna**: SHA-256 (de fábrica), SHA-1 o MD5.
- Botón **Abrir la configuración avanzada...**: abre el diálogo «Clave de VirusTotal» para poner, cambiar u olvidar la clave. El diálogo tiene «Estado» (Alt+E), «Nueva clave de la API de VirusTotal» (Alt+N), «Guardar» (Alt+G), «Olvidar la clave guardada» (Alt+O) y «Cancelar» (Alt+C).

## Sonidos

- **Sin firma**: al comprobar un ejecutable sin firma o con una firma no válida.
- **Amenaza**: cuando Defender o VirusTotal encuentran algo, o la suma no coincide.

## Privacidad

- «Buscar en VirusTotal» solo envía a VirusTotal la suma SHA-256 del archivo, nunca el archivo.
- La clave de VirusTotal es suya y se guarda cifrada en este equipo.
- La primera vez que busca en VirusTotal, zCommander avisa de qué se envía y a dónde.
