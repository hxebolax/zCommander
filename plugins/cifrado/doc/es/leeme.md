# Cifrado de archivos

Cifra y descifra archivos y carpetas con una contraseña.

**Importante: si pierde la contraseña, no hay forma de recuperar lo cifrado.** Ni zCommander ni nadie puede hacerlo. Guárdela en un lugar seguro.

## Órdenes

Están en el menú Complementos, submenú «Sistema y seguridad», submenú «Cifrado de archivos», y en la paleta de órdenes.

- **Cifrar...** (Ctrl+Mayús+F8): cifra los elementos de trabajo (los marcados o el del cursor). Cada archivo queda en su propio archivo cifrado junto al original; las carpetas se empaquetan antes en un ZIP.
- **Descifrar...**: descifra los archivos `.zcc` elegidos junto a ellos. No tiene tecla de fábrica; se le puede dar una en el mapa de teclas.

Intro sobre un `.zcc` también lo descifra: es la asociación «Abrir» de fábrica de `*.zcc` (`zc:zc.cifrado:descifrar`). Una asociación propia para `*.zcc` en Asociaciones tiene preferencia.

## El diálogo Cifrar

- **Contraseña** (Alt+S) y **Repita la contraseña** (Alt+R).
- **Fortaleza** (Alt+F): campo de solo lectura que dice cómo de difícil es adivinarla («Débil: menos de 12 caracteres», «Fuerte»...). Una frase de varias palabras es fácil de recordar y difícil de adivinar.
- **Formato** (Alt+T): «Archivo .zcc de zCommander (AES-256-GCM)», que solo abre zCommander, o «7z con AES-256, compatible con 7-Zip» (solo en el disco).
- **Enviar los originales a la papelera tras comprobar el cifrado** (Alt+E): después de comprobar que lo cifrado se descifra bien, los originales van a la papelera. No es un borrado seguro: lo que estaba en el disco puede seguir recuperándose con programas especiales.
- **Aceptar** y **Cancelar**.

Cifrar y descifrar son operaciones como copiar: tienen progreso, se pueden poner en pausa o cancelar y salen en la ventana de operaciones (F12). Nunca se sobrescribe nada: si ya existe un archivo con el nombre de destino, se usa «nombre (2)».

## Descifrar un archivo

zCommander pide la contraseña. Si no es la correcta (o el archivo está dañado), dice «El archivo está dañado o la contraseña no es correcta» y la vuelve a pedir; si cancela, ese archivo se salta. Nunca queda un archivo descifrado a medias.

## Ver un archivo cifrado sin descifrarlo en el disco

F3 sobre un `.zcc` pide la contraseña y muestra su contenido si es un texto (o la lista de archivos si es una carpeta cifrada). Lo descifrado solo está en la memoria: no se escribe en el disco. La Vista rápida no muestra los `.zcc`.

## Preferencias

En Preferencias, Complementos, Cifrado de archivos, General:

- **Formato al cifrar**: .zcc o 7z (el diálogo recuerda el último elegido).
- **Coste de la contraseña**: «Normal» (unos 192 MB de memoria al cifrar y al descifrar) o «Alto» (más de medio gigabyte de memoria; resiste mejor a quien intente adivinar la contraseña).
- **Enviar los originales a la papelera tras comprobar el cifrado**: desactivada de fábrica.
- **Recordar la contraseña hasta cerrar zCommander**: desactivada de fábrica. Se recuerda solo en la memoria, nunca en el disco.

## Formato de los archivos .zcc

El formato `.zcc` está descrito en la [descripción técnica del formato .zcc](formato-zcc.md).
