# Git básico

Muestra el estado de un repositorio Git y hace las operaciones más comunes sin salir de zCommander.

Usa el Git instalado en el equipo (`git.exe`). Sin Git, se pueden ver el estado, el historial y las diferencias; el resto dice «Hace falta Git instalado». zCommander no instala Git.

## Órdenes

Están en el menú Complementos, submenú «Sistema y seguridad», submenú «Git básico», y en la paleta de órdenes. Solo «Estado de Git» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

- **Estado de Git** (Ctrl+Mayús+F11): dice la rama y los cambios, por ejemplo «Rama main, 3 cambios: 2 modificados, 1 sin seguimiento».
- **Añadir**: prepara para confirmar los elementos de trabajo.
- **Confirmar...**: confirma lo preparado con un mensaje. Si no hay nada preparado, ofrece confirmar todos los cambios de los archivos con seguimiento.
- **Diferencias**: diferencias del archivo del cursor con la última confirmación.
- **Historial...**: confirmaciones del archivo o carpeta del cursor en una lista.
- **Traer**: trae los cambios del repositorio remoto (`git pull`).
- **Enviar**: envía las confirmaciones (`git push`).
- **Cambiar de rama...**: elige otra rama o crea una nueva («Nombre de la rama nueva»).
- **Clonar...**: pide la «Dirección del repositorio» y clona el repositorio en la carpeta del panel; al terminar, el panel entra en él.
- **Descartar los cambios...**: devuelve los archivos elegidos a como estaban en la última confirmación, con confirmación (el botón predeterminado es «No»). Los archivos sin seguimiento no se tocan.

Traer, enviar y clonar son operaciones como copiar: salen en la ventana de operaciones (F12) y se pueden cancelar. Si el servidor pide usuario y contraseña, los pide el administrador de credenciales de Git en su propia ventana.

## El diálogo Confirmar

- **Mensaje de la confirmación** (Alt+M).
- **Lo que se confirma** (Alt+L): solo lectura.
- **Aceptar** y **Cancelar**.

## El diálogo Historial

- **Historial** (Alt+H): lista con las columnas Fecha, Autor, Mensaje e Identificador. Intro muestra el mensaje completo y los cambios de la confirmación elegida.
- **Ver los cambios** (Alt+V): lo mismo que Intro.
- **Copiar el identificador** (Alt+O).
- **Cerrar** (Alt+E o Escape).

## Línea de órdenes

`zc git <orden>` ejecuta Git en la carpeta del panel activo; la salida va a «Salida de órdenes». Por ejemplo: `zc git status`, `zc git log --oneline -5` o, para quitar un archivo del área de preparación sin perder sus cambios, `zc git reset -- archivo`.

## Columna Git y anuncio al entrar en un repositorio

- Columna **Git**: «modificado», «nuevo», «sin seguimiento», «ignorado», «eliminado», «renombrado», «en conflicto» o «con cambios» (carpetas).
- Al entrar en una carpeta de un repositorio, zCommander dice la rama y los cambios (solo con el «Detalle de los anuncios» en «Detallado») y suena «Repositorio Git». Moverse dentro del mismo repositorio no lo repite.

## Preferencias

En Preferencias, Complementos, Git básico, General:

- **Programa git.exe (vacío: buscar el instalado)**: vacío de fábrica.
- **Anunciar la rama y los cambios al entrar en un repositorio**: activada de fábrica.
- **Segundos que se reutiliza el estado para la columna Git**: 5 de fábrica.

## Sonidos

- **Repositorio Git**: al entrar en una carpeta de un repositorio.
