# Programador de tareas

Ejecuta tareas de zCommander a una hora o con una frecuencia, también con zCommander cerrado: tareas de sincronización, copias, las reglas del monitor, limpiezas (mandar a la papelera lo antiguo de una carpeta), macros, entradas del menú de usuario y órdenes.

## Órdenes

Están en el menú Complementos, submenú «Automatización», submenú «Programador de tareas», y en la paleta de órdenes. No tienen tecla de fábrica; se les puede dar una en el mapa de teclas.

- **Programador de tareas...**: abre la lista de tareas.
- **Registro de ejecuciones...**: muestra el resultado de cada ejecución.

## Cómo se ejecutan las tareas

Con la preferencia **Usar el Programador de tareas de Windows** (activada por defecto), cada tarea es también una tarea de Windows, en la carpeta «zCommander» del Programador de tareas, que abre zCommander con su tarea:

- Si zCommander está abierto, la tarea se ejecuta en esa ventana, como cualquier operación (la ventana de operaciones, F12, la sigue), sin traerla al frente.
- Si está cerrado, zCommander se abre minimizado, sin quitarle el foco a lo que esté haciendo y sin hablar (salvo los errores), ejecuta la tarea y se cierra solo al terminar si mientras tanto no lo ha usado.
- La tarea se ejecuta con su usuario y en su sesión; si a esa hora no había sesión iniciada, se ejecuta al iniciarla.

Sin el Programador de Windows, las tareas solo se ejecutan mientras zCommander está abierto: se comprueba cada 30 segundos qué toca, y las de «al iniciar sesión» se ejecutan al abrir zCommander.

Las tareas no preguntan: si un archivo ya existe en el destino o hay un error, usan la respuesta que se eligió en la tarea, y cada decisión queda en el registro de ejecuciones. Lo que no tiene respuesta automática (por ejemplo, una contraseña) se pregunta como siempre.

## La lista de tareas

- **Estado** (Alt+S): si se usan las tareas de Windows o solo con zCommander abierto.
- **Tareas programadas** (Alt+T): lista con Nombre, Qué hace, Cuándo, Última ejecución, Resultado y Activa. Intro edita la tarea y Supr la borra (pregunta antes).
- Botones: **Nueva...** (Alt+N), **Editar...** (Alt+E), **Borrar** (Alt+B), **Ejecutar ahora** (Alt+J), **Registro de ejecuciones...** (Alt+R) y **Cerrar** (Alt+C o Escape).

## El diálogo Tarea programada

- **Nombre** (Alt+N) y **Qué hace** (Alt+Q).
- **Objetivo** (Alt+O): su etiqueta dice qué escribir según lo que hace: el nombre de la tarea de sincronización, la carpeta o el archivo que se copia, la carpeta del monitor, la carpeta que se limpia, el nombre de la macro, el de la entrada del menú de usuario o el identificador de la orden.
- **Destino (solo al copiar)** (Alt+D): la carpeta adonde se copia (en una orden, el argumento que recibe).
- **Días de antigüedad (solo al limpiar)** (Alt+G): la limpieza manda a la papelera lo modificado hace más de esos días, también en las subcarpetas.
- **Frecuencia** (Alt+F): una vez, cada día, cada semana o al iniciar sesión en Windows.
- **Hora (HH:MM)** (Alt+H).
- **Fecha, una vez o primer día (AAAA-MM-DD)** (Alt+U).
- **Días de la semana** (Alt+M).
- **Si el destino existe** (Alt+X): omitirlo, sobrescribirlo, sobrescribirlo si es más antiguo o guardar la copia con otro nombre.
- **Ante un error** (Alt+E): omitir el elemento o cancelar la tarea.
- **Tarea activa** (Alt+I).

## Resultados y registro de ejecuciones

Al terminar una tarea con zCommander abierto se dice su resultado y suena «Tarea programada terminada». Al abrir zCommander se dice cuántas tareas se ejecutaron desde la última vez y cuántas con errores. Con la preferencia de notificaciones, además, Windows muestra una notificación.

El diálogo «Registro de ejecuciones» tiene:

- **Ejecuciones** (Alt+E): lista con Fecha, Tarea, Resultado (Bien, Con errores, No se pudo empezar) y Resumen.
- **Detalles** (Alt+D): las decisiones que se tomaron sin preguntar.
- **Vaciar el registro** (Alt+V) y **Cerrar** (Alt+C o Escape).

## Preferencias

En Preferencias, Complementos, Programador de tareas, General:

- **Usar el Programador de tareas de Windows (las tareas se ejecutan también con zCommander cerrado)**: activada por defecto.
- **Avisar del resultado con una notificación de Windows**: activada por defecto.

## Sonidos

- **Tarea programada terminada**: al terminar una tarea con zCommander abierto o, al abrirlo, si se ejecutaron tareas mientras estaba cerrado.
