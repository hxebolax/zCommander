# Proyectos y salto rápido

Lleva a cualquier carpeta que use a menudo escribiendo solo parte de su nombre, y guarda proyectos: la ventana tal como está (pestañas y vistas, con los espacios de trabajo de zCommander), una nota y unas carpetas propias.

## Órdenes

Están en el menú Complementos, submenú «Automatización», submenú «Proyectos y salto rápido», y en la paleta de órdenes.

- **Salto rápido...** (Ctrl+Mayús+J): abre el diálogo «Salto rápido» con el campo «Ir a».
- **Proyectos...**: abre la lista de proyectos. No tiene tecla de fábrica; se le puede dar una en el mapa de teclas.

## El salto rápido

zCommander cuenta, desde que arranca, cada carpeta del disco o de la red de Windows en la que entra. Al escribir en **Ir a** (Alt+I), por ejemplo «fact», la **Lista de carpetas** (Alt+L) propone al momento las carpetas cuya ruta contiene lo escrito, primero las que más usa y las que ha usado hace menos (las que tienen lo escrito en su propio nombre van delante). Puede escribir varios trozos separados por espacios: «trab fact».

- Flecha abajo pasa del campo a la lista.
- Intro, en el campo o en la lista, lleva el panel activo a la carpeta (la primera, si no ha bajado a la lista). El botón **Abrir en el panel** (Alt+A) hace lo mismo.
- La lista tiene las columnas Carpeta, Origen (Frecuente o Reciente de Windows) y Visitas. Las carpetas recientes de Windows (las de los últimos archivos que abrió en cualquier programa) se añaden detrás de las frecuentes al abrir el diálogo.
- **Olvidar esta carpeta** (Alt+O) la quita de las frecuentes.
- **Cancelar** (Alt+C o Escape) cierra sin cambiar de carpeta.

## La lista de proyectos

La lista **Proyectos** (Alt+P) tiene las columnas Nombre, Nota, Carpetas y Creado. Intro abre el proyecto y Supr lo quita de la lista (pregunta antes; no se borra ningún archivo).

- **Abrir** (Alt+A): abre el espacio de trabajo del proyecto (pestañas y vistas de los dos paneles). Si ya no existe, lleva el panel a la primera carpeta del proyecto.
- **Guardar la ventana actual como proyecto...** (Alt+G): pide el «Nombre del proyecto» y una «Nota del proyecto (opcional)», guarda la ventana como espacio de trabajo y apunta como carpetas del proyecto las de los dos paneles.
- **Editar...** (Alt+E): cambia la «Nota» y las «Carpetas del proyecto (una por línea)».
- **Borrar** (Alt+B): quita el proyecto de la lista.
- **Ir a una carpeta del proyecto...** (Alt+R).
- **Cerrar** (Alt+C o Escape).

## Preferencias

En Preferencias, Complementos, Proyectos y salto rápido, General:

- **Máximo de carpetas recordadas**: 1000 por defecto.
- **Peso de la frecuencia**: 1 por defecto; 0 solo cuenta lo reciente y más de 1 da más peso a las carpetas que más visita.
- **Media vida, en días**: 14 por defecto; una carpeta que no visita desde hace ese tiempo pesa la mitad.
- **Carpetas excluidas**: `C:\Windows` por defecto; nunca se cuentan ni se proponen.
