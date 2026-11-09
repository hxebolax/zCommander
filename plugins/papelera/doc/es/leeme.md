# Papelera de reciclaje como panel

Muestra la papelera de Windows en un panel, con la ubicación original y la fecha de eliminación de cada elemento.

## Órdenes

Están en el menú Complementos, submenú «Orden y limpieza del disco», submenú «Papelera de reciclaje como panel», y en la paleta de órdenes.

- **Abrir la papelera** (Ctrl+F8): la abre en el panel activo y dice el resumen («312 elementos, 4,2 GB»). También está en el selector de unidades como «Papelera», con su resumen.
- **Restaurar a su sitio**: devuelve los elementos elegidos a su carpeta original.
- **Vaciar la papelera...**: elimina definitivamente todo lo de la papelera.

Solo «Abrir la papelera» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

## La papelera en el panel

Cada elemento tiene su nombre original. La columna Ruta (o la columna «Ubicación original» del complemento) dice de qué carpeta se eliminó; la columna Modificado (o «Fecha de eliminación») dice cuándo. Lo último eliminado sale primero mientras no elija otro orden.

Se puede entrar en una carpeta eliminada para ver lo que tiene, copiar elementos al otro panel (F5) y usar el filtro y la búsqueda como en cualquier carpeta.

## Restaurar, eliminar y vaciar

- **Restaurar a su sitio** devuelve los elementos elegidos a su carpeta original (la crea si ya no está). Si allí ya hay algo con el mismo nombre, pregunta: «Restaurar con otro nombre» («informe (2).txt»), «Otro nombre para todos», «Omitir» o «Cancelar».
- **Supr** en la papelera elimina definitivamente los elementos elegidos, con confirmación.
- **Vaciar la papelera...** elimina definitivamente todo (o solo lo de la unidad que se está viendo, con `papelera://D:/`). El diálogo tiene los botones «Vaciar la papelera» y «Cancelar»; el foco empieza en «Cancelar». Al terminar suena el sonido de eliminar.

Lo eliminado definitivamente no se puede recuperar.

## Preferencias

En Preferencias, Complementos, Papelera de reciclaje como panel, General:

- **Unidades cuya papelera se muestra (vacía, todas)**: vacía por defecto, que significa todas las unidades fijas.
