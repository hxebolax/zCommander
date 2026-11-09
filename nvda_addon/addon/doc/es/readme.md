# Complemento de zCommander para NVDA

Este complemento mejora la lectura de zCommander, el gestor de archivos accesible, con el lector de pantalla NVDA. Solo actúa mientras zCommander está en primer plano; en el resto de programas NVDA funciona como siempre. zCommander funciona igual sin el complemento: el complemento solo afina lo que NVDA no puede saber por sí mismo.

## Qué mejora

- **Texto completo en las listas.** NVDA corta cada columna de una lista a 511 caracteres. Con el complemento, en zCommander se lee entera: por ejemplo, la columna Ruta de las listas de resultados o un nombre de archivo muy largo.
- **Sin repeticiones.** Cuando zCommander recoloca el foco por su cuenta (al volver a leer la carpeta, al restaurar las marcas, al aplicar un filtro o al volver de un diálogo al mismo elemento), NVDA no vuelve a leer el elemento en el que ya estabas. Se puede desactivar en zCommander: Preferencias, página Accesibilidad, casilla «Movimientos del foco silenciosos con el complemento de NVDA».
- **Orden de lectura de las columnas.** Si en zCommander eliges qué columnas se leen al moverse por las filas y en qué orden, NVDA lee solo esas, en ese orden (como mucho 15). Sin esa elección, NVDA lee todas las columnas en el orden de la lista.
- **Leer la fila completa.** NVDA+Mayúsculas+J lee todas las columnas de la fila enfocada con su cabecera. Si lo pulsas dos veces seguidas, la fila se abre en una ventana donde puedes leerla con las flechas y copiarla.

## Teclas

- NVDA+Mayúsculas+J: leer la fila enfocada completa con sus cabeceras; dos pulsaciones, mostrarla en una ventana.

Puedes cambiar esta tecla en el menú de NVDA, Preferencias, Gestos de entrada, categoría «zCommander».

## Instalar y desinstalar

- Desde zCommander: Preferencias, página Accesibilidad, botón «Instalar el complemento de zCommander para NVDA...», o en el menú Ayuda. zCommander explica qué hace y, si aceptas, abre el archivo; NVDA te pedirá confirmación y se reiniciará.
- También puedes abrir el archivo `.nvda-addon` de la carpeta `data\bin\nvda` de zCommander desde el Explorador.
- Para desactivarlo o quitarlo: menú de NVDA, Herramientas, Tienda de complementos, pestaña «Complementos instalados».

## Requisitos

NVDA 2026.1 o posterior y la versión compilada de zCommander (`ZCommander.exe`). Desde el código fuente zCommander se ejecuta dentro de Python y el complemento no se aplica.

## Licencia

GPL-3.0-or-later, como zCommander.
