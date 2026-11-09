# Formato .zcc

Archivo cifrado por zCommander con AES-256-GCM y una clave derivada de la contraseña con scrypt.

## Estructura

1. Los 4 bytes `ZCC1`.
2. La longitud del JSON de parámetros: 4 bytes, entero sin signo, orden big-endian (como mucho 64 KiB).
3. El JSON de parámetros en UTF-8:

   ```json
   {"kdf": "scrypt", "n": 131072, "r": 8, "p": 1, "sal": "<16 bytes en base64>",
    "prefijo": "<8 bytes en base64>", "nombre": "original.ext", "tamano": 1234,
    "bloque": 1048576, "carpeta": false}
   ```

   - `n`, `r` y `p`: parámetros de scrypt (`n` = 2^17 con el coste «normal» y 2^19 con «alto»).
   - `nombre` y `tamano`: nombre y tamaño en bytes de lo cifrado.
   - `carpeta`: `true` si lo cifrado es un ZIP de una carpeta (al descifrar se extrae).
4. Los bloques cifrados, uno detrás de otro.

## Clave

`clave = scrypt(contraseña en UTF-8, sal, n, r, p, longitud 32)`. zCommander llama a `hashlib.scrypt` con `maxmem = 128 · r · (n + 2) + 64 MiB`.

## Bloques

- Lo cifrado se parte en trozos de `bloque` bytes (1 MiB); el último lleva lo que quede, aunque sea nada (un archivo vacío tiene un único bloque vacío).
- Cada bloque se cifra con AES-256-GCM y ocupa su tamaño más 16 bytes de etiqueta.
- Nonce del bloque número `i` (desde 0): los 8 bytes de `prefijo` seguidos de `i` en 4 bytes big-endian.
- Datos asociados del bloque `i`: la cabecera completa (puntos 1 a 3, tal como está en el archivo), `i` en 4 bytes big-endian y un byte de final: 1 en el último bloque y 0 en los demás.

Así no se puede cambiar la cabecera (nombre, tamaño o parámetros), reordenar bloques, quitar bloques del final (el que pasaría a ser el último no lleva la marca de final) ni añadir bloques. Al descifrar, además, el tamaño total tiene que coincidir con `tamano`.

Cualquier fallo da el mismo mensaje, «El archivo está dañado o la contraseña no es correcta», porque AES-GCM no permite distinguir una contraseña equivocada de un archivo cambiado.
