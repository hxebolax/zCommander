# Anexo: catálogo de órdenes

Generado con `python tools/generar_anexos.py` a partir de `app/ui/ordenes.py`. No lo edite a mano.

Hay 348 órdenes. Cada una indica sus teclas de fábrica, dónde funcionan, qué bloque la programa y su manejador (`app/ui/acciones/<módulo>.py`).

## Menús Izquierdo y Derecho

### Vista completa (`vista_completa`)

- Muestra todas las columnas elegidas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.vista`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «completa».

### Vista breve (`vista_breve`)

- Muestra solo los nombres.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.vista`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «breve».

### Información (`vista_informacion`)

- Muestra en este lado la información del elemento del otro panel.
- Teclas: Ctrl+L; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.vista`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «informacion».

### Árbol (`vista_arbol`)

- Muestra en este lado el árbol de carpetas; el otro panel sigue la carpeta elegida.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.vista`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «arbol».

### Vista rápida (`vista_rapida`)

- Muestra en este lado el contenido del archivo del cursor del otro panel.
- Teclas: Ctrl+Q; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.vista`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «rapida».

### Ordenar por nombre (`ordenar_nombre`)

- Ordena por nombre; otra vez invierte el orden.
- Teclas: Ctrl+F3; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «nombre».

### Ordenar por extensión (`ordenar_extension`)

- Ordena por extensión; otra vez invierte el orden.
- Teclas: Ctrl+F4; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «extension».

### Ordenar por fecha (`ordenar_fecha`)

- Ordena por fecha de modificación; otra vez invierte el orden.
- Teclas: Ctrl+F5; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «fecha».

### Ordenar por tamaño (`ordenar_tamano`)

- Ordena por tamaño; otra vez invierte el orden.
- Teclas: Ctrl+F6; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «tamano».

### Ordenar por tipo (`ordenar_tipo`)

- Ordena por tipo de archivo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «tipo».

### Sin ordenar (`sin_ordenar`)

- Muestra los elementos en el orden del disco.
- Teclas: Ctrl+F7; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.ordenar`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla; parámetro «sin_orden».

### Orden inverso (`orden_inverso`)

- Invierte el orden actual.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.orden_inverso`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla.

### Agrupar las carpetas al principio (`carpetas_primero`)

- Muestra las carpetas antes que los archivos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.carpetas_primero`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla.

### Filtro (`filtro`)

- Elige qué archivos se muestran con un patrón (*.mp3;*.flac).
- Teclas: Ctrl+F12; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.filtro`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Quitar el filtro (`quitar_filtro`)

- Vuelve a mostrar todos los elementos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.quitar_filtro`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Columnas (`columnas`)

- Elige qué columnas se ven en este lado, su orden y su ancho.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.columnas`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Columnas y vista de esta carpeta (`columnas_carpeta`)

- Conjunto de columnas y vista que se aplica a esta carpeta o a carpetas parecidas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.columnas_carpeta`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Volver a leer (`volver_a_leer`)

- Vuelve a leer la carpeta conservando cursor y marcas.
- Teclas: Ctrl+R; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.volver_a_leer`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Unidad (`unidad`)

- Elige unidad o carpeta especial para este lado.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.unidad`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Pestaña nueva (`pestana_nueva`)

- Abre una pestaña con la misma carpeta.
- Teclas: Ctrl+T; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_nueva`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Cerrar pestaña (`pestana_cerrar`)

- Cierra la pestaña actual (la última no se cierra).
- Teclas: Ctrl+W; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_cerrar`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Cerrar las demás pestañas (`pestana_cerrar_otras`)

- Cierra todas las pestañas de este lado salvo la actual.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_cerrar_otras`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Pestaña siguiente (`pestana_siguiente`)

- Pasa a la pestaña siguiente del lado activo.
- Teclas: Ctrl+Tab; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_mover`.
- En los menús izquierdo y derecho, actúa sobre ese lado; parámetro «1».

### Pestaña anterior (`pestana_anterior`)

- Pasa a la pestaña anterior del lado activo.
- Teclas: Ctrl+Mayús+Tab; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_mover`.
- En los menús izquierdo y derecho, actúa sobre ese lado; parámetro «-1».

### Bloquear o desbloquear la pestaña (`pestana_bloquear`)

- Una pestaña bloqueada no cambia de carpeta: al entrar en otra se abre una pestaña nueva.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_bloquear`.
- En los menús izquierdo y derecho, actúa sobre ese lado; casilla.

### Lista de pestañas (`lista_pestanas`)

- Elige una pestaña de este lado en una lista.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.lista_pestanas`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

### Mostrar u ocultar este lado (`mostrar_lado`)

- Oculta o muestra este lado de la ventana.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.mostrar_lado`.
- En los menús izquierdo y derecho, actúa sobre ese lado.

## Menú Archivos

### Abrir (`abrir`)

- Entra en la carpeta o el comprimido, o abre el archivo con su programa.
- Teclas: Intro; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.abrir`.

### Ver (`ver`)

- Abre el archivo en el visor.
- Teclas: F3; en toda la ventana principal.
- Bloque: A, visor y editor. Manejador: `visor.ver`.

### Ver con el visor externo (`ver_externo`)

- Abre el archivo con el visor externo configurado.
- Teclas: Alt+F3; en toda la ventana principal.
- Bloque: A, visor y editor. Manejador: `visor.ver_externo`.

### Editar (`editar`)

- Abre el archivo en el editor.
- Teclas: F4; en toda la ventana principal.
- Bloque: A, visor y editor. Manejador: `visor.editar`.

### Abrir con otro programa (`abrir_con`)

- Elige el programa con el que abrir el archivo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: G, integración con Windows. Manejador: `windows_g.abrir_con`.

### Copiar (`copiar`)

- Copia los elementos de trabajo al otro panel.
- Teclas: F5; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.copiar`.

### Renombrar o mover (`mover`)

- Mueve los elementos de trabajo al otro panel, o los renombra.
- Teclas: F6; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.mover`.

### Copiar aquí con otro nombre (`duplicar`)

- Copia el elemento en la misma carpeta con otro nombre.
- Teclas: Mayús+F5; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.duplicar`.

### Renombrar en el sitio (`renombrar`)

- Cambia el nombre del elemento del cursor.
- Teclas: Mayús+F6; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.renombrar`.

### Crear carpeta (`crear_carpeta`)

- Crea una carpeta en el panel activo.
- Teclas: F7; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.crear_carpeta`.

### Crear archivo nuevo (`crear_archivo`)

- Pide un nombre, crea el archivo vacío y lo abre en el editor.
- Teclas: Mayús+F4; en toda la ventana principal.
- Bloque: A, visor y editor. Manejador: `visor.crear_archivo`.

### Eliminar (`eliminar`)

- Envía los elementos de trabajo a la papelera.
- Teclas: F8, Supr; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.eliminar`.

### Eliminar definitivamente (`eliminar_definitivo`)

- Elimina sin pasar por la papelera.
- Teclas: Mayús+F8, Mayús+Supr; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.eliminar_definitivo`.

### Deshacer (`deshacer`)

- Deshace la última operación que lo admite (renombrar, mover, crear carpeta, copiar).
- Teclas: Ctrl+Z; con el foco en un panel.
- Bloque: Núcleo. Manejador: `archivos.deshacer`.

### Atributos y fechas (`atributos`)

- Cambia atributos y fechas de los elementos de trabajo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: E, renombrado y atributos. Manejador: `edicion_e.atributos`.

### Propiedades (`propiedades`)

- Abre las propiedades de Windows.
- Teclas: Alt+Intro; en toda la ventana principal.
- Bloque: G, integración con Windows. Manejador: `windows_g.propiedades`.

### Menú contextual de Windows (`menu_windows`)

- Abre el menú contextual del Explorador para los elementos de trabajo.
- Teclas: Ctrl+Aplicaciones, Alt+Mayús+F10; con el foco en un panel.
- Bloque: G, integración con Windows. Manejador: `windows_g.menu_windows`.

### Marcar por patrón (`marcar_patron`)

- Marca los elementos que coinciden con un patrón (*.txt;*.md, exclusiones con |).
- Teclas: Num +, Ctrl+Mayús+M; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_patron`.

### Desmarcar por patrón (`desmarcar_patron`)

- Desmarca los elementos que coinciden con un patrón.
- Teclas: Num -, Ctrl+Mayús+Q; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.desmarcar_patron`.

### Invertir las marcas (`invertir_marcas`)

- Marca lo no marcado y desmarca lo marcado (solo archivos).
- Teclas: Num *, Ctrl+Mayús+N; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.invertir`.

### Marcar todo (`marcar_todo`)

- Marca todos los elementos visibles.
- Teclas: Ctrl+A; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_todo`.

### Desmarcar todo (`desmarcar_todo`)

- Quita todas las marcas.
- Teclas: Ctrl+Mayús+A; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.desmarcar_todo`.

### Marcar la misma extensión (`marcar_extension`)

- Marca todos los archivos con la extensión del cursor.
- Teclas: Mayús+Num +; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.extension`.
- Parámetro «marcar».

### Desmarcar la misma extensión (`desmarcar_extension`)

- Desmarca todos los archivos con la extensión del cursor.
- Teclas: Mayús+Num -; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.extension`.
- Parámetro «desmarcar».

### Restaurar las marcas (`restaurar_marcas`)

- Vuelve a marcar lo que estaba marcado antes de la última operación.
- Teclas: Ctrl+Mayús+R; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.restaurar`.

### Guardar las marcas en un archivo (`guardar_marcas`)

- Guarda los nombres marcados en un archivo de texto.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.guardar`.

### Cargar las marcas desde un archivo (`cargar_marcas`)

- Marca los nombres que aparecen en un archivo de texto.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.cargar`.

### Copiar al portapapeles (`portapapeles_copiar`)

- Copia los elementos de trabajo al portapapeles (compatible con el Explorador).
- Teclas: Ctrl+C; con el foco en un panel.
- Bloque: G, integración con Windows. Manejador: `windows_g.portapapeles_copiar`.

### Cortar (`portapapeles_cortar`)

- Corta los elementos de trabajo para pegarlos en otro sitio.
- Teclas: Ctrl+X; con el foco en un panel.
- Bloque: G, integración con Windows. Manejador: `windows_g.portapapeles_cortar`.

### Pegar (`portapapeles_pegar`)

- Pega en la carpeta del panel activo los archivos del portapapeles.
- Teclas: Ctrl+V; con el foco en un panel.
- Bloque: G, integración con Windows. Manejador: `windows_g.portapapeles_pegar`.

### Copiar las rutas completas (`copiar_rutas`)

- Copia como texto las rutas completas de los elementos de trabajo.
- Teclas: Ctrl+Mayús+C; con el foco en un panel.
- Bloque: Núcleo. Manejador: `archivos.copiar_rutas`.

### Copiar los nombres (`copiar_nombres`)

- Copia como texto los nombres de los elementos de trabajo.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: Núcleo. Manejador: `archivos.copiar_nombres`.

### Copiar la ruta de la carpeta (`copiar_ruta_carpeta`)

- Copia como texto la ruta de la carpeta del panel activo.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: Núcleo. Manejador: `archivos.copiar_ruta_carpeta`.

### Copiar la ruta UNC (`copiar_ruta_unc`)

- Copia la ruta \\servidor\recurso de los elementos de una unidad de red.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: RD, red. Manejador: `red_rd.copiar_ruta_unc`.

### Menú de usuario (`menu_usuario`)

- Órdenes propias definidas en Opciones, Editar el menú de usuario.
- Teclas: F2; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.menu_usuario`.

### Reiniciar zCommander (`reiniciar`)

- Cierra zCommander y lo vuelve a abrir.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PL, complementos. Manejador: `complementos_pl.reiniciar`.

### Salir (`salir`)

- Cierra zCommander.
- Teclas: F10, Alt+X; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.salir`.

## Menú Comandos

### Ir a la carpeta (`ir_a_carpeta`)

- Escriba una ruta, una dirección ftp:// o sftp:// o una variable como %USERPROFILE%.
- Teclas: Ctrl+G; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.ir_a_carpeta`.

### Árbol de carpetas (`arbol_carpetas`)

- Elige una carpeta en un árbol de la unidad.
- Teclas: Alt+F10; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.arbol_carpetas`.

### Historial de carpetas (`historial_carpetas`)

- Lista de carpetas visitadas en este panel.
- Teclas: Alt+F12, Alt+Abajo; con el foco en un panel.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.historial_carpetas`.

### Favoritos (`favoritos`)

- Carpetas favoritas: ir, añadir, renombrar, ordenar y borrar.
- Teclas: Ctrl+D; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.favoritos`.

### Añadir a favoritos (`agregar_favorito`)

- Añade la carpeta actual a favoritos.
- Teclas: Ctrl+Mayús+D; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.agregar_favorito`.

### Historial de órdenes (`historial_ordenes`)

- Lista de las órdenes ejecutadas, con búsqueda.
- Teclas: Alt+F8; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.historial_ordenes`.

### Buscar archivos (`buscar_archivos`)

- Busca por nombre, contenido, tamaño, fecha y atributos.
- Teclas: Alt+F7; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.buscar_archivos`.

### Comparar carpetas (`comparar_carpetas`)

- Marca en cada panel lo que falta en el otro o es más reciente.
- Teclas: Ctrl+F10; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.comparar_carpetas`.

### Sincronizar carpetas (`sincronizar_carpetas`)

- Compara las carpetas de los dos paneles y copia o elimina para igualarlas.
- Teclas: Ctrl+Mayús+F10; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.sincronizar`.

### Comparar archivos por contenido (`comparar_archivos`)

- Compara el archivo del cursor de cada panel, o los dos marcados.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: A, visor y editor. Manejador: `visor.comparar_archivos`.

### Renombrado múltiple (`renombrado_multiple`)

- Renombra muchos archivos con máscaras, contador, buscar y reemplazar.
- Teclas: Ctrl+M; en toda la ventana principal.
- Bloque: E, renombrado y atributos. Manejador: `edicion_e.renombrado_multiple`.

### Intercambiar paneles (`intercambiar_paneles`)

- Intercambia el contenido de los paneles izquierdo y derecho.
- Teclas: Ctrl+U; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.intercambiar_paneles`.

### Igualar paneles (`igualar_paneles`)

- Lleva el otro panel a la misma carpeta que el activo.
- Teclas: Alt+Z; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.igualar_paneles`.

### Mostrar u ocultar los paneles (`mostrar_paneles`)

- Oculta los dos paneles y muestra la salida de las órdenes, o al revés.
- Teclas: Ctrl+O; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.mostrar_paneles`.

### Mostrar u ocultar el panel pasivo (`panel_pasivo`)

- Oculta o muestra el panel que no tiene el foco.
- Teclas: Ctrl+P; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.panel_pasivo`.

### Abrir en el lado izquierdo (`abrir_en_izquierdo`)

- Abre en el lado izquierdo la carpeta del cursor, o la actual.
- Teclas: Ctrl+Izquierda; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.abrir_en_lado`.
- Parámetro «izquierdo».

### Abrir en el lado derecho (`abrir_en_derecho`)

- Abre en el lado derecho la carpeta del cursor, o la actual.
- Teclas: Ctrl+Derecha; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.abrir_en_lado`.
- Parámetro «derecho».

### Espacios de trabajo (`espacios_trabajo`)

- Disposiciones de pestañas y paneles guardadas con nombre.
- Teclas: Ctrl+Mayús+W; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.espacios_trabajo`.

### Guardar el espacio de trabajo (`espacio_guardar`)

- Guarda la disposición actual como espacio de trabajo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.espacio_guardar`.

### Calcular el tamaño (`tamano_carpetas`)

- Calcula y anuncia el tamaño de las carpetas de trabajo.
- Teclas: Mayús+Espacio; con el foco en un panel.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.tamano`.
- Parámetro «trabajo».

### Calcular el tamaño de todas las carpetas (`tamano_todas`)

- Calcula el tamaño de todas las carpetas del panel.
- Teclas: Alt+Mayús+Intro; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.tamano`.
- Parámetro «todas».

### Vista plana (`vista_plana`)

- Muestra en una lista todos los archivos de la carpeta y sus subcarpetas.
- Teclas: Ctrl+B; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.vista_plana`.
- Casilla.

### Crear sumas de comprobación (`sumas_crear`)

- Calcula CRC32, MD5, SHA-1, SHA-256, SHA-512 o BLAKE2 y las guarda.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.sumas_crear`.

### Verificar sumas de comprobación (`sumas_verificar`)

- Comprueba los archivos con un archivo de sumas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.sumas_verificar`.

### Dividir archivo (`dividir`)

- Divide un archivo en partes de un tamaño dado.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.dividir`.

### Unir archivos (`unir`)

- Une las partes .001, .002... en el archivo original.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.unir`.

### Crear enlace (`crear_enlace`)

- Crea un enlace simbólico, una unión, un enlace duro o un acceso directo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: E, renombrado y atributos. Manejador: `edicion_e.crear_enlace`.

### Añadir a la cesta (`cesta_agregar`)

- Guarda los elementos de trabajo en la cesta, para operar después con archivos de varias carpetas.
- Teclas: Ctrl+Mayús+B; con el foco en un panel.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.cesta_agregar`.

### Abrir la cesta (`cesta_abrir`)

- Muestra la cesta como una lista en el panel activo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.cesta_abrir`.

### Vaciar la cesta (`cesta_vaciar`)

- Quita todos los elementos de la cesta.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: B, búsqueda y comparación. Manejador: `busqueda_b.cesta_vaciar`.

### Comprimir (`comprimir`)

- Crea un comprimido ZIP, 7z o TAR con los elementos de trabajo.
- Teclas: Alt+F5; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.comprimir`.

### Extraer (`extraer`)

- Extrae los comprimidos de trabajo al otro panel.
- Teclas: Alt+F6, Alt+F9; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.extraer`.

### Probar comprimido (`probar_comprimido`)

- Comprueba que el comprimido no está dañado.
- Teclas: Alt+Mayús+F9; en toda la ventana principal.
- Bloque: C, comprimidos y utilidades. Manejador: `comprimidos_c.probar`.

### Red (`red_raiz`)

- Muestra unidades de red, conexiones, servidores recientes y equipos de la red.
- Teclas: Ctrl+Mayús+K; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_raiz`.

### Buscar equipos en la red (`red_buscar_equipos`)

- Busca los equipos de la red local y los añade a la raíz Red.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_buscar_equipos`.

### Abrir un recurso compartido con otra cuenta (`red_conectar_recurso`)

- Abre una carpeta compartida con otro usuario y contraseña.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_conectar_recurso`.

### Volver a conectar la unidad (`red_reconectar`)

- Vuelve a conectar la unidad de red del panel.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: RD, red. Manejador: `red_rd.red_reconectar`.

### Información de la conexión (`red_info`)

- Servidor, usuario, protocolo y cifrado de la conexión del panel.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_info`.

### Contraseñas guardadas de servidores (`red_contrasenas`)

- Lista y borra las credenciales de servidores guardadas en Windows.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_contrasenas`.

### Sesiones y archivos abiertos por la red (`red_sesiones`)

- Quién tiene abiertos archivos de este equipo por la red (pide permisos de administrador).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_sesiones`.

### Conexiones FTP y SFTP (`conexiones`)

- Gestor de sitios FTP, FTPS y SFTP.
- Teclas: Ctrl+K; en toda la ventana principal.
- Bloque: D, red. Manejador: `red_d.conexiones`.

### Desconectar (`desconectar`)

- Cierra la conexión del panel activo y vuelve al disco local.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: D, red. Manejador: `red_d.desconectar`.

### Conectar unidad de red (`conectar_unidad_red`)

- Asigna una letra de unidad a un recurso compartido.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_d.conectar_unidad`.

### Desconectar unidad de red (`desconectar_unidad_red`)

- Quita una unidad de red asignada.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_d.desconectar_unidad`.

### Conectar con el cuadro de Windows (`red_cuadro_conectar`)

- Abre el cuadro de Windows para conectar una unidad de red.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_cuadro_conectar`.

### Desconectar con el cuadro de Windows (`red_cuadro_desconectar`)

- Abre el cuadro de Windows para desconectar una unidad de red.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: RD, red. Manejador: `red_rd.red_cuadro_desconectar`.

### Operaciones en curso (`operaciones`)

- Ventana con las copias, movimientos y demás operaciones, y las decisiones pendientes.
- Teclas: F12; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.operaciones`.

### Abrir consola aquí (`consola`)

- Abre la consola configurada en la carpeta del panel activo.
- Teclas: F11; en toda la ventana principal.
- Bloque: G, integración con Windows. Manejador: `windows_g.consola`.

### Abrir en el Explorador (`explorador`)

- Abre la carpeta actual en el Explorador de Windows.
- Teclas: Mayús+F3; en toda la ventana principal.
- Bloque: G, integración con Windows. Manejador: `windows_g.explorador`.

## Menú Complementos

### Gestor de complementos (`complementos`)

- Lista de complementos: habilitar, configurar, actualizar e instalar.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PL, complementos. Manejador: `complementos_pl.complementos`.

### Instalar un complemento desde un archivo (`complemento_instalar`)

- Instala un complemento .zcplugin tras mostrar su resumen, su firma y sus permisos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PL, complementos. Manejador: `complementos_pl.complemento_instalar`.

### Reiniciar sin complementos (`reiniciar_sin_complementos`)

- Reinicia zCommander en modo seguro, sin cargar ningún complemento.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PL, complementos. Manejador: `complementos_pl.reiniciar_sin_complementos`.

### Convertir audio o vídeo (`zc.ffmpeg:convertir`)

- Convierte los elementos de trabajo con un perfil de audio o vídeo.
- Teclas: Ctrl+Mayús+F6; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:convertir».

### Extraer el audio (`zc.ffmpeg:extraer_audio`)

- Extrae el audio de un vídeo, copiando el flujo si se puede.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:extraer_audio».

### Recortar (`zc.ffmpeg:recortar`)

- Recorta un archivo de audio o vídeo entre un inicio y un fin.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:recortar».

### Normalizar el volumen (`zc.ffmpeg:normalizar`)

- Normaliza el volumen con el filtro loudnorm de dos pasadas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:normalizar».

### Información técnica (`zc.ffmpeg:informacion`)

- Dice la duración, el contenedor y los flujos del archivo del cursor.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:informacion».

### Unir archivos de audio (`zc.ffmpeg:unir`)

- Une archivos de audio del mismo formato en uno solo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ffmpeg:unir».

### Describir la imagen (`zc.imagenes:describir`)

- Pide la descripción de la imagen del cursor al servicio configurado.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.imagenes:describir».

### Ver la imagen ampliada (`zc.imagenes:visor`)

- Abre la imagen del cursor en el visor ampliable.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.imagenes:visor».

### Convertir o redimensionar imágenes (`zc.imagenes:convertir`)

- Convierte, redimensiona o gira por lotes los elementos de trabajo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.imagenes:convertir».

### Quitar la ubicación (GPS) (`zc.imagenes:quitar_gps`)

- Quita los metadatos de ubicación de las fotos JPEG elegidas sin recomprimirlas.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.imagenes:quitar_gps».

### Leer en voz alta o pausar (`zc.voz:leer`)

- Lee en voz alta el archivo del cursor o pausa la lectura.
- Teclas: Ctrl+F9; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:leer».

### Detener la lectura (`zc.voz:detener`)

- Detiene la lectura en voz alta y recuerda dónde iba.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:detener».

### Convertir a audio (`zc.voz:exportar`)

- Convierte uno o varios archivos de texto o documentos en audio.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:exportar».

### Frase siguiente (`zc.voz:frase_siguiente`)

- Pasa a la frase siguiente de la lectura.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:frase_siguiente».

### Frase anterior (`zc.voz:frase_anterior`)

- Vuelve a la frase anterior de la lectura.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:frase_anterior».

### Párrafo siguiente (`zc.voz:parrafo_siguiente`)

- Pasa al párrafo siguiente de la lectura.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:parrafo_siguiente».

### Párrafo anterior (`zc.voz:parrafo_anterior`)

- Vuelve al principio del párrafo o al párrafo anterior.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.voz:parrafo_anterior».

### Editar las etiquetas (`zc.metadatos:editar`)

- Edita las etiquetas del archivo del cursor o de los marcados.
- Teclas: Ctrl+Mayús+F2; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:editar».

### Etiquetas desde el nombre (`zc.metadatos:desde_nombre`)

- Rellena las etiquetas a partir del nombre del archivo con una máscara.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:desde_nombre».

### Numerar las pistas (`zc.metadatos:numerar`)

- Numera las pistas marcadas en el orden del panel.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:numerar».

### Quitar las etiquetas (`zc.metadatos:quitar`)

- Quita las etiquetas y la portada de los archivos elegidos.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:quitar».

### Portada (`zc.metadatos:portada`)

- Añade, extrae o quita la portada de los archivos de audio.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:portada».

### Exportar la lista de pistas (`zc.metadatos:exportar`)

- Exporta la lista de pistas a texto o CSV.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.metadatos:exportar».

### Reproducir (`zc.reproductor:reproducir`)

- Reproduce el archivo del cursor, los marcados o la carpeta.
- Teclas: Ctrl+Mayús+F5; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:reproducir».

### Mostrar el reproductor (`zc.reproductor:ventana`)

- Abre la ventana del reproductor con la cola de reproducción.
- Teclas: Alt+Mayús+F2; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:ventana».

### Pausa o continuar (`zc.reproductor:pausa`)

- Pausa la reproducción o la continúa donde se quedó.
- Teclas: Alt+Mayús+F5; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:pausa».

### Detener (`zc.reproductor:detener`)

- Detiene la reproducción.
- Teclas: Alt+Mayús+F6; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:detener».

### Retroceder (`zc.reproductor:retroceder`)

- Retrocede un salto corto en la pista actual.
- Teclas: Alt+Mayús+F7; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:retroceder».

### Avanzar (`zc.reproductor:avanzar`)

- Avanza un salto corto en la pista actual.
- Teclas: Alt+Mayús+F8; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:avanzar».

### Decir la posición (`zc.reproductor:posicion`)

- Dice la posición, la duración y el porcentaje de la pista actual.
- Teclas: Alt+Mayús+F3; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:posicion».

### Siguiente pista (`zc.reproductor:siguiente`)

- Pasa a la siguiente pista de la cola.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:siguiente».

### Pista anterior (`zc.reproductor:anterior`)

- Vuelve al principio de la pista o a la anterior de la cola.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:anterior».

### Añadir a la cola (`zc.reproductor:anadir_cola`)

- Añade el archivo del cursor o los marcados a la cola de reproducción.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:anadir_cola».

### Guardar la cola como M3U (`zc.reproductor:guardar_lista`)

- Guarda la cola de reproducción como una lista M3U con rutas relativas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:guardar_lista».

### Temporizador de apagado (`zc.reproductor:temporizador`)

- Detiene la reproducción cuando pasa el tiempo elegido.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P1, multimedia. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.reproductor:temporizador».

### Convertir la codificación y los fines de línea (`zc.texto:convertir`)

- Convierte los marcados a UTF-8 y al fin de línea elegido con vista previa.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.texto:convertir».

### Informe de caracteres no válidos (`zc.texto:informe`)

- Informa de los caracteres no válidos de los archivos elegidos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.texto:informe».

### Ver como tabla (`zc.tablas:ver_tabla`)

- Abre el CSV o la tabla del cursor en el visor de tabla.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.tablas:ver_tabla».

### Consulta SQL (`zc.tablas:consulta`)

- Ejecuta una consulta SQL sobre una base SQLite.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.tablas:consulta».

### Ver y editar en hexadecimal (`zc.hexadecimal:editar`)

- Abre el archivo del cursor en el editor hexadecimal.
- Teclas: Ctrl+Mayús+F4; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.hexadecimal:editar».

### Convertir a texto (`zc.documentos:convertir`)

- Guarda el documento del cursor o los marcados como texto o Markdown.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.documentos:convertir».

### Propiedades del documento (`zc.documentos:propiedades`)

- Dice el título, el autor, las páginas y la fecha del documento.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.documentos:propiedades».

### Reconocer el texto (`zc.ocr:reconocer`)

- Reconoce el texto del archivo del cursor y lo muestra en el visor.
- Teclas: Ctrl+Mayús+F3; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocr:reconocer».

### Reconocer los marcados a archivos de texto (`zc.ocr:lotes`)

- Reconoce los marcados y guarda un archivo de texto junto a cada uno.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocr:lotes».

### Reconocer la imagen del portapapeles (`zc.ocr:portapapeles`)

- Reconoce el texto de la imagen que hay en el portapapeles.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocr:portapapeles».

### Reconocer la ventana en primer plano (`zc.ocr:ventana`)

- Reconoce el texto de la ventana en primer plano, útil en programas inaccesibles.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P2, documentos y datos. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocr:ventana».

### Buscar duplicados (`zc.duplicados:buscar`)

- Busca archivos iguales en las carpetas elegidas.
- Teclas: Mayús+F7; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.duplicados:buscar».

### Comentario o nota (`zc.notas:comentario`)

- Edita el comentario del elemento del cursor o, en «..», la nota de la carpeta.
- Teclas: Ctrl+N; con el foco en un panel.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.notas:comentario».

### Leer la nota de la carpeta (`zc.notas:leer_nota`)

- Lee la nota de la carpeta actual.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.notas:leer_nota».

### Etiquetas (`zc.notas:etiquetas`)

- Pone o quita etiquetas a los elementos de trabajo.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.notas:etiquetas».

### Buscar por etiqueta o comentario (`zc.notas:buscar`)

- Busca los archivos que tienen una etiqueta o un comentario.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.notas:buscar».

### Analizar la ocupación (`zc.ocupacion:analizar`)

- Analiza qué ocupa el espacio de una unidad o carpeta.
- Teclas: Ctrl+Mayús+F7; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocupacion:analizar».

### Los 100 archivos más grandes (`zc.ocupacion:mayores`)

- Muestra los 100 archivos más grandes del último análisis.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocupacion:mayores».

### Ocupación por extensión (`zc.ocupacion:extensiones`)

- Muestra cuánto ocupa cada extensión en el último análisis.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocupacion:extensiones».

### Ir a esta carpeta en el disco (`zc.ocupacion:ir`)

- Lleva el otro panel a la carpeta real del elemento del análisis.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.ocupacion:ir».

### Organizar por metadatos (`zc.organizador:organizar`)

- Mueve o copia los elementos a carpetas según una plantilla de metadatos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.organizador:organizar».

### Abrir la papelera (`zc.papelera:abrir`)

- Abre la papelera de reciclaje en el panel activo.
- Teclas: Ctrl+F8; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.papelera:abrir».

### Restaurar a su sitio (`zc.papelera:restaurar`)

- Devuelve los elementos elegidos de la papelera a su ubicación original.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.papelera:restaurar».

### Vaciar la papelera (`zc.papelera:vaciar`)

- Elimina definitivamente todo lo que hay en la papelera.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P3, orden y limpieza. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.papelera:vaciar».

### ¿Quién usa este archivo? (`zc.procesos:quien_usa`)

- Dice qué programa tiene abierto el archivo del cursor o los marcados.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.procesos:quien_usa».

### Procesos (`zc.procesos:lista`)

- Abre la lista de procesos con su memoria, CPU y ruta.
- Teclas: Ctrl+Mayús+F12; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.procesos:lista».

### Cifrar (`zc.cifrado:cifrar`)

- Cifra los elementos de trabajo con una contraseña.
- Teclas: Ctrl+Mayús+F8; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.cifrado:cifrar».

### Descifrar (`zc.cifrado:descifrar`)

- Descifra los archivos cifrados elegidos (.zcc).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.cifrado:descifrar».

### Estado de Git (`zc.git:estado`)

- Dice la rama y los cambios del repositorio actual.
- Teclas: Ctrl+Mayús+F11; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:estado».

### Añadir (`zc.git:anadir`)

- Añade los elementos de trabajo al área de preparación.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:anadir».

### Confirmar (`zc.git:confirmar`)

- Confirma los cambios preparados con un mensaje.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:confirmar».

### Diferencias (`zc.git:diferencias`)

- Muestra las diferencias del archivo del cursor con la última confirmación.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:diferencias».

### Historial (`zc.git:historial`)

- Muestra el historial del archivo o la carpeta en una lista.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:historial».

### Traer (`zc.git:traer`)

- Trae los cambios del repositorio remoto.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:traer».

### Enviar (`zc.git:enviar`)

- Envía las confirmaciones al repositorio remoto.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:enviar».

### Cambiar de rama (`zc.git:rama`)

- Cambia a otra rama del repositorio o crea una nueva.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:rama».

### Clonar (`zc.git:clonar`)

- Clona un repositorio en la carpeta del panel.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:clonar».

### Descartar los cambios (`zc.git:descartar`)

- Deshace los cambios de los archivos elegidos, con confirmación.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.git:descartar».

### Historial del portapapeles (`zc.portapapeles:historial`)

- Abre el historial de lo copiado para volver a pegarlo.
- Teclas: Ctrl+Mayús+V; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.portapapeles:historial».

### Comprobar la firma digital (`zc.seguridad:firma`)

- Comprueba la firma Authenticode del archivo del cursor.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.seguridad:firma».

### Comparar la suma con el portapapeles (`zc.seguridad:comparar_suma`)

- Compara la suma del archivo con la que hay en el portapapeles.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.seguridad:comparar_suma».

### Analizar con Defender (`zc.seguridad:defender`)

- Analiza los elementos de trabajo con Microsoft Defender.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.seguridad:defender».

### Buscar en VirusTotal (`zc.seguridad:virustotal`)

- Busca el hash del archivo en VirusTotal sin enviar el archivo.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.seguridad:virustotal».

### Quitar la marca de la Web (`zc.seguridad:quitar_marca`)

- Quita la marca de la Web de los archivos elegidos.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: P4, sistema y seguridad. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.seguridad:quitar_marca».

### Búsqueda instantánea con Everything (`zc.busqueda_instantanea:abrir`)

- Abre la ventana de búsqueda instantánea en todo el equipo.
- Teclas: Ctrl+Mayús+F; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.busqueda_instantanea:abrir».

### Monitor de carpetas (`zc.monitor:reglas`)

- Elige las carpetas vigiladas y edita sus reglas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.monitor:reglas».

### Pausar o reanudar el monitor (`zc.monitor:pausar`)

- Pausa o reanuda la vigilancia de todas las carpetas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Casilla; parámetro «zc.monitor:pausar».

### Registro del monitor (`zc.monitor:registro`)

- Muestra lo que ha hecho el monitor y permite deshacer la última acción.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.monitor:registro».

### Programador de tareas (`zc.programador:tareas`)

- Crea, edita y ejecuta las tareas programadas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.programador:tareas».

### Registro de ejecuciones (`zc.programador:registro`)

- Muestra el resultado de las tareas programadas ejecutadas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.programador:registro».

### Salto rápido (`zc.proyectos:salto`)

- Lleva el panel a una carpeta frecuente escribiendo parte de su nombre.
- Teclas: Ctrl+Mayús+J; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.proyectos:salto».

### Proyectos (`zc.proyectos:proyectos`)

- Lista, guarda y abre los proyectos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.proyectos:proyectos».

### Tareas de sincronización (`zc.sincronizacion:perfiles`)

- Crea, edita y ejecuta las tareas de sincronización con nombre.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.sincronizacion:perfiles».

### Ejecutar todas las tareas (`zc.sincronizacion:ejecutar_todas`)

- Ejecuta todas las tareas de sincronización guardadas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: P5, automatización. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.sincronizacion:ejecutar_todas».

### Estado del NAS (`zc.synology:estado`)

- Abre la ventana del NAS en el área Estado, conectando si hace falta.
- Teclas: Ctrl+Mayús+F9; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:estado».

### Conectar con un NAS (`zc.synology:conectar`)

- Abre la lista de NAS guardados para conectar, dar de alta uno nuevo o arrancar el NAS de demostración.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:conectar».

### Desconectar del NAS (`zc.synology:desconectar`)

- Cierra la sesión con el NAS (y para el NAS de demostración si es ese).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:desconectar».

### Abrir File Station en el panel (`zc.synology:abrir_archivos`)

- Abre las carpetas compartidas del NAS en el panel activo (dirección synology://).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:abrir_archivos».

### Ir a un área del NAS (`zc.synology:area`)

- Elige un área del NAS y abre la ventana en ella.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:area».

### Tareas en segundo plano del NAS (`zc.synology:tareas_fondo`)

- Muestra las tareas en segundo plano de File Station (copiar, mover, borrar, comprimir y extraer en el NAS).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:tareas_fondo».

### Crear un enlace compartido (`zc.synology:enlace`)

- Crea un enlace compartido de los elementos elegidos en un panel del NAS y lo copia al portapapeles.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:enlace».

### Comprimir en el NAS (`zc.synology:comprimir`)

- Comprime los elementos elegidos en el propio NAS, sin pasar los archivos por este equipo.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:comprimir».

### Extraer en el NAS (`zc.synology:extraer`)

- Extrae el comprimido del cursor en el propio NAS.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:extraer».

### Permitir cambios en el NAS (`zc.synology:modo_escritura`)

- Activa o desactiva el modo que permite cambiar cosas en el NAS; activarlo pide confirmación.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Casilla; parámetro «zc.synology:modo_escritura».

### NAS de demostración (`zc.synology:demostracion`)

- Arranca un NAS simulado en este equipo para practicar sin riesgo: nada sale a la red y los cambios se pierden al cerrar.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:demostracion».

### Herramientas avanzadas por SSH (`zc.synology:ssh`)

- S.M.A.R.T. en bruto, registros largos y estadísticas de contenedores, compose y rescate de paquetes por SSH (desactivadas de fábrica).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:ssh».

### Reiniciar el NAS (`zc.synology:reiniciar`)

- Reinicia el NAS con doble confirmación: la segunda pide escribir su nombre.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:reiniciar».

### Apagar el NAS (`zc.synology:apagar`)

- Apaga el NAS con doble confirmación: la segunda pide escribir su nombre.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NS, NAS Synology. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.synology:apagar».

### Cuentas de nube (`zc.nubes:cuentas`)

- Abre la ventana con las cuentas de nube y su estado.
- Teclas: Alt+F11; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:cuentas».

### Añadir una cuenta de nube (`zc.nubes:anadir`)

- Abre el asistente para añadir una cuenta de nube.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:anadir».

### Conectar Nextcloud u ownCloud (`zc.nubes:nextcloud`)

- Conecta un servidor Nextcloud u ownCloud con Login Flow v2.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:nextcloud».

### Copiar un enlace para compartir (`zc.nubes:enlace`)

- Crea un enlace para compartir el elemento del cursor y lo copia.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:enlace».

### Quitar el enlace compartido (`zc.nubes:quitar_enlace`)

- Quita el enlace compartido del elemento del cursor.
- Teclas: sin tecla; con el foco en un panel.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:quitar_enlace».

### Vaciar la papelera de la nube (`zc.nubes:vaciar_papelera`)

- Vacía la papelera de la cuenta de nube, con confirmación.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:vaciar_papelera».

### Espacio de la nube (`zc.nubes:espacio`)

- Dice el espacio usado, el libre y el de la papelera de la cuenta.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:espacio».

### Sincronizar con la nube (`zc.nubes:sincronizar`)

- Sincroniza una carpeta con la nube tras mostrar una simulación.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:sincronizar».

### Emparejar carpetas (en los dos sentidos) (`zc.nubes:emparejar`)

- Mantiene dos carpetas iguales en los dos sentidos con un asistente.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:emparejar».

### Comprobar carpetas (`zc.nubes:comprobar`)

- Compara dos carpetas por tamaño y suma y muestra las diferencias.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:comprobar».

### Buscar nombres duplicados (`zc.nubes:duplicados`)

- Busca y resuelve los nombres duplicados de una cuenta, con simulación.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:duplicados».

### Crear una carpeta cifrada en la nube (`zc.nubes:cifrada`)

- Crea una carpeta cifrada sobre una carpeta de una cuenta.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:cifrada».

### Unir varias cuentas en una unidad (`zc.nubes:union`)

- Une varias cuentas en una sola unidad.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:union».

### Montar como letra de unidad (`zc.nubes:montar`)

- Monta una cuenta como letra de unidad con WinFsp.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:montar».

### Unidades montadas (`zc.nubes:montajes`)

- Lista las unidades de nube montadas y permite desmontarlas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:montajes».

### Compartir en la red (`zc.nubes:servir`)

- Comparte una carpeta por WebDAV, SFTP, HTTP o DLNA.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:servir».

### Carpetas compartidas por zCommander (`zc.nubes:servicios_activos`)

- Lista las carpetas que comparte zCommander y permite dejar de compartirlas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:servicios_activos».

### Pausar o reanudar los límites de velocidad (`zc.nubes:limites`)

- Quita o vuelve a poner los límites de velocidad de la configuración.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:limites».

### Volver a autorizar la cuenta (`zc.nubes:reconectar`)

- Vuelve a autorizar una cuenta cuyo acceso caducó.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:reconectar».

### Guía para conectar Google Drive (`zc.nubes:guia_google`)

- Abre la guía paso a paso para conectar Google Drive.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NU, Nubes. Manejador: `complementos_pl.ejecutar`.
- Parámetro «zc.nubes:guia_google».

## Menú Opciones

### Preferencias (`preferencias`)

- Todas las opciones de zCommander.
- Teclas: Ctrl+coma; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.preferencias`.

### Perfil de usuario (`perfil`)

- Aplica los valores pensados para personas novatas, intermedias o avanzadas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.perfil`.

### Guardar la configuración como perfil (`perfil_guardar_propio`)

- Guarda las preferencias y teclas actuales como un perfil con nombre.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.perfil_guardar_propio`.

### Exportar un perfil (`perfil_exportar`)

- Guarda preferencias, teclas, personalización y macros en un .zcperfil, sin contraseñas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: CS, copia de seguridad. Manejador: `copia_cs.perfil_exportar`.

### Importar un perfil (`perfil_importar`)

- Aplica un .zcperfil eligiendo qué se aplica.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: CS, copia de seguridad. Manejador: `copia_cs.perfil_importar`.

### Esquema de teclas (`esquema_teclas`)

- Teclas como Norton Commander, Total Commander, Far o el Explorador.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.esquema_teclas`.

### Mapa de teclas (`mapa_teclas`)

- Cambia las teclas de cada orden.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.mapa_teclas`.

### Personalizar menús y barras (`personalizar_menus`)

- Oculta elementos de menú, llena Mis órdenes, la barra de botones y la barra de teclas.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.personalizar_menus`.

### Mostrar la barra de botones (`barra_botones`)

- Muestra u oculta la barra de botones configurable.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.barra_botones`.
- Casilla.

### Ver todas las órdenes en los menús (`todas_las_ordenes`)

- Con los menús según el nivel, muestra también las órdenes de los otros niveles.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.todas_las_ordenes`.
- Casilla.

### Columnas por defecto (`columnas_defecto`)

- Columnas de los paneles nuevos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.columnas_defecto`.

### Orden de lectura de las columnas (`orden_lectura`)

- Qué columnas se leen al moverse por las filas y en qué orden.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.orden_lectura`.

### Reglas de anuncio, color y sonido (`reglas`)

- Reglas que marcan con color, texto, sonido o anuncio los elementos que cumplen una condición.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.reglas`.

### Alias de la línea de órdenes (`alias`)

- Nombres cortos para órdenes largas de la línea de órdenes.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.alias`.

### Plantillas de archivo nuevo (`plantillas_archivo`)

- Abre la carpeta de las plantillas de Crear archivo nuevo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.plantillas_archivo`.

### Grabar una macro (`macro_grabar`)

- Empieza o termina la grabación de una macro con las órdenes que ejecute.
- Teclas: Ctrl+Mayús+G; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.macro_grabar`.
- Casilla.

### Ejecutar la última macro (`macro_ultima`)

- Repite la última macro ejecutada.
- Teclas: Ctrl+Mayús+L; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.macro_ultima`.

### Macros (`macros`)

- Crea, edita, ejecuta, exporta e importa macros.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.macros`.

### Silenciar los sonidos (`sonidos_silenciar`)

- Activa o desactiva todos los sonidos de zCommander.
- Teclas: Ctrl+F11; en toda la ventana principal.
- Bloque: SO, sonidos. Manejador: `sonidos_so.sonidos_silenciar`.
- Casilla.

### Subir el volumen de los sonidos (`sonidos_volumen_subir`)

- Sube 10 el volumen de los sonidos y lo anuncia.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: SO, sonidos. Manejador: `sonidos_so.sonidos_volumen_subir`.

### Bajar el volumen de los sonidos (`sonidos_volumen_bajar`)

- Baja 10 el volumen de los sonidos y lo anuncia.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: SO, sonidos. Manejador: `sonidos_so.sonidos_volumen_bajar`.

### Paquetes de sonidos (`sonidos_paquetes`)

- Crea, edita, exporta e importa paquetes de sonidos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: SO, sonidos. Manejador: `sonidos_so.sonidos_paquetes`.

### Editar el menú de usuario (`editar_menu_usuario`)

- Crea y cambia las entradas del menú de usuario (F2).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.editar_menu_usuario`.

### Editar las asociaciones (`editar_asociaciones`)

- Qué programa abre, ve o edita cada tipo de archivo.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.editar_asociaciones`.

### Mostrar archivos ocultos y de sistema (`mostrar_ocultos`)

- Muestra u oculta los archivos ocultos y de sistema.
- Teclas: Ctrl+punto; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.mostrar_ocultos`.
- Casilla.

### Componentes externos (`componentes`)

- rclone, libarchive, 7za y FFmpeg: versiones, actualizaciones y restaurar los originales.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: CO, componentes. Manejador: `componentes_co.componentes`.

### Crear una copia de seguridad (`copia_crear`)

- Guarda en un archivo .zcbackup la configuración que elija.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: CS, copia de seguridad. Manejador: `copia_cs.copia_crear`.

### Restaurar una copia de seguridad (`copia_restaurar`)

- Restaura una copia .zcbackup eligiendo qué partes.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: CS, copia de seguridad. Manejador: `copia_cs.copia_restaurar`.

### Asistente de primer arranque (`asistente`)

- Vuelve a elegir perfil, lector de pantalla y tema.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.asistente`.

### Guardar la sesión ahora (`guardar_sesion`)

- Guarda carpetas, pestañas y configuración.
- Teclas: Mayús+F9; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `archivos.guardar_sesion`.

### Restablecer los valores de fábrica (`restablecer_fabrica`)

- Vuelve a las preferencias de fábrica (pide confirmación).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.restablecer_fabrica`.

### Abrir la carpeta de datos (`carpeta_datos`)

- Abre en el Explorador la carpeta data de zCommander.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.carpeta_datos`.

### Abrir la carpeta de registros (`carpeta_registros`)

- Abre en el Explorador la carpeta de registros.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.carpeta_registros`.

## Menú Ayuda

### Manual de usuario (`manual`)

- Abre el manual.
- Teclas: F1; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.manual`.

### Lista de teclas (`lista_teclas`)

- Muestra todas las teclas de zCommander.
- Teclas: Mayús+F1; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.lista_teclas`.

### Novedades de la versión (`novedades`)

- Muestra los cambios de cada versión.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.novedades`.

### Ayuda del control enfocado (`ayuda_contextual`)

- Explica para qué sirve el control que tiene el foco.
- Teclas: Ctrl+H; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.ayuda_contextual`.
- Tecla fija.

### Paleta de órdenes (`paleta_ordenes`)

- Escriba lo que quiere hacer y elija la orden; se anuncia su atajo para aprenderlo.
- Teclas: Ctrl+E; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.paleta_ordenes`.

### Modo de ayuda de teclado (`ayuda_teclado`)

- Mientras está activo, cada tecla dice qué haría sin hacerlo. Escape sale.
- Teclas: Mayús+F12; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.ayuda_teclado`.

### Historial de anuncios (`historial_anuncios`)

- Lista de los anuncios de la sesión, con hora; se puede copiar.
- Teclas: Ctrl+Mayús+H; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.historial_anuncios`.

### Mapa de sonidos (`mapa_sonidos`)

- Lista de todos los sonidos con cuándo suenan; se pueden escuchar.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: SO, sonidos. Manejador: `sonidos_so.mapa_sonidos`.

### Buscar actualizaciones (`buscar_actualizaciones`)

- Comprueba si hay una versión nueva de zCommander.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: AC, actualizador. Manejador: `actualizar_ac.buscar_actualizaciones`.

### Instalar el complemento de zCommander para NVDA (`complemento_nvda`)

- Explica qué hace el complemento de NVDA y lo instala si lo acepta.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: NV, complemento de NVDA. Manejador: `nvda_nv.complemento_nvda`.

### Información para soporte (`info_soporte`)

- Copia al portapapeles la versión, el sistema y las últimas líneas del registro.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.info_soporte`.

### Acerca de zCommander (`acerca_de`)

- Versión y datos técnicos.
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `ayuda.acerca_de`.

## Órdenes solo de teclado

### Carpeta superior (`subir`)

- Va a la carpeta que contiene la actual.
- Teclas: Retroceso, Ctrl+Re Pág, Alt+Arriba; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.subir`.

### Entrar (`entrar`)

- Entra en la carpeta o el comprimido del cursor.
- Teclas: Ctrl+Av Pág; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.entrar`.

### Raíz de la unidad (`raiz`)

- Va a la carpeta raíz de la unidad actual.
- Teclas: Ctrl+Retroceso; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.raiz`.

### Carpeta personal (`carpeta_personal`)

- Va a su carpeta de usuario.
- Teclas: Ctrl+Mayús+Inicio; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.carpeta_personal`.

### Atrás (`atras`)

- Vuelve a la carpeta anterior del historial del panel.
- Teclas: Alt+Izquierda; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.atras`.

### Adelante (`adelante`)

- Avanza a la carpeta siguiente del historial del panel.
- Teclas: Alt+Derecha; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.adelante`.

### Cambiar de panel (`cambiar_panel`)

- Pasa al otro panel.
- Teclas: Tab, Mayús+Tab; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.cambiar_panel`.
- Tecla fija.

### Cancelar o quitar (`cancelar`)

- Hace lo primero que se pueda: detener la macro en curso; cancelar la lectura, el cálculo o la búsqueda de equipos del panel; quitar el filtro rápido; detener la orden lanzada desde la línea de órdenes.
- Teclas: Escape; con el foco en un panel.
- Bloque: Núcleo. Manejador: `navegacion.cancelar`.

### Abrir la barra de menús (`abrir_menus`)

- Abre la barra de menús, como en Norton Commander (Alt también la abre).
- Teclas: F9; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.abrir_menus`.
- Tecla fija.

### Ir a la línea de órdenes (`ir_linea_ordenes`)

- Muestra la línea de órdenes y pone el foco en ella. Con búsqueda rápida activa, le pasa lo tecleado.
- Teclas: Mayús+F2; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `navegacion.ir_linea_ordenes`.

### Unidad del lado izquierdo (`unidad_izquierda`)

- Elige unidad o carpeta especial para el lado izquierdo.
- Teclas: Alt+F1; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.unidad`.
- Parámetro «izquierdo».

### Unidad del lado derecho (`unidad_derecha`)

- Elige unidad o carpeta especial para el lado derecho.
- Teclas: Alt+F2; en toda la ventana principal.
- Bloque: F, diálogos y personalización. Manejador: `dialogos_f.unidad`.
- Parámetro «derecho».

### Filtro rápido (`filtro_rapido`)

- Escriba para quedarse solo con los elementos que contienen el texto. Escape lo quita.
- Teclas: Ctrl+F; con el foco en un panel.
- Bloque: Núcleo. Manejador: `vista.filtro_rapido`.

### Búsqueda rápida (`busqueda_rapida`)

- Escriba el principio de un nombre para llevar el cursor a él.
- Teclas: Ctrl+S; con el foco en un panel.
- Bloque: Núcleo. Manejador: `vista.busqueda_rapida`.

### Mostrar u ocultar el lado izquierdo (`mostrar_izquierdo`)

- Oculta o muestra el lado izquierdo.
- Teclas: Ctrl+F1; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.mostrar_lado`.
- Parámetro «izquierdo».

### Mostrar u ocultar el lado derecho (`mostrar_derecho`)

- Oculta o muestra el lado derecho.
- Teclas: Ctrl+F2; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.mostrar_lado`.
- Parámetro «derecho».

### Pestaña 1 (`pestana_1`)

- Va a la pestaña con ese número.
- Teclas: Alt+1; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «1».

### Pestaña 2 (`pestana_2`)

- Va a la pestaña con ese número.
- Teclas: Alt+2; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «2».

### Pestaña 3 (`pestana_3`)

- Va a la pestaña con ese número.
- Teclas: Alt+3; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «3».

### Pestaña 4 (`pestana_4`)

- Va a la pestaña con ese número.
- Teclas: Alt+4; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «4».

### Pestaña 5 (`pestana_5`)

- Va a la pestaña con ese número.
- Teclas: Alt+5; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «5».

### Pestaña 6 (`pestana_6`)

- Va a la pestaña con ese número.
- Teclas: Alt+6; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «6».

### Pestaña 7 (`pestana_7`)

- Va a la pestaña con ese número.
- Teclas: Alt+7; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «7».

### Pestaña 8 (`pestana_8`)

- Va a la pestaña con ese número.
- Teclas: Alt+8; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «8».

### Pestaña 9 (`pestana_9`)

- Va a la pestaña con ese número.
- Teclas: Alt+9; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `vista.pestana_numero`.
- Parámetro «9».

### Menú contextual (`menu_contextual`)

- Abre el menú contextual de zCommander.
- Teclas: Mayús+F10, Aplicaciones; con el foco en un panel.
- Bloque: Núcleo. Manejador: `archivos.menu_contextual`.
- Tecla fija.

### Marcar y bajar (`marcar`)

- Marca o desmarca el elemento del cursor y baja al siguiente.
- Teclas: Insert, Espacio; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar`.

### Marcar sin mover (`marcar_sin_mover`)

- Marca o desmarca el elemento del cursor sin moverse.
- Teclas: Ctrl+Espacio; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_sin_mover`.

### Extender la marca hacia arriba (`marcar_subir`)

- Marca el elemento del cursor y sube.
- Teclas: Mayús+Arriba; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «-1».

### Extender la marca hacia abajo (`marcar_bajar`)

- Marca el elemento del cursor y baja.
- Teclas: Mayús+Abajo; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «1».

### Marcar una página hacia arriba (`marcar_pagina_arriba`)

- Marca desde el cursor una página hacia arriba.
- Teclas: Mayús+Re Pág; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «-pagina».

### Marcar una página hacia abajo (`marcar_pagina_abajo`)

- Marca desde el cursor una página hacia abajo.
- Teclas: Mayús+Av Pág; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «pagina».

### Marcar hasta el principio (`marcar_hasta_inicio`)

- Marca desde el cursor hasta el primer elemento.
- Teclas: Mayús+Inicio; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «inicio».

### Marcar hasta el final (`marcar_hasta_fin`)

- Marca desde el cursor hasta el último elemento.
- Teclas: Mayús+Fin; con el foco en un panel.
- Bloque: Núcleo. Manejador: `marcas.marcar_rango`.
- Parámetro «fin».

### Añadir el nombre a la línea de órdenes (`insertar_nombre`)

- Escribe el nombre del cursor en la línea de órdenes.
- Teclas: Ctrl+Intro; con el foco en un panel.
- Bloque: Núcleo. Manejador: `linea.insertar_nombre`.

### Añadir la ruta completa a la línea de órdenes (`insertar_ruta`)

- Escribe la ruta completa del cursor en la línea de órdenes.
- Teclas: Ctrl+Mayús+Intro; con el foco en un panel.
- Bloque: Núcleo. Manejador: `linea.insertar_ruta`.

### Ejecutar la orden (`ejecutar_linea`)

- Ejecuta la orden escrita en la carpeta del panel activo.
- Teclas: Intro; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.ejecutar`.

### Ejecutar en una consola (`ejecutar_en_consola`)

- Ejecuta la orden en una consola nueva que queda abierta.
- Teclas: Ctrl+Intro; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.ejecutar_en_consola`.

### Orden anterior (`linea_anterior`)

- Recupera la orden anterior del historial.
- Teclas: Arriba; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.historial_mover`.
- Parámetro «-1».

### Orden siguiente (`linea_siguiente`)

- Recupera la orden siguiente del historial.
- Teclas: Abajo; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.historial_mover`.
- Parámetro «1».

### Vaciar la línea de órdenes (`linea_vaciar`)

- Borra lo escrito; si ya está vacía, detiene la orden en curso o, si no hay ninguna, vuelve al panel.
- Teclas: Escape; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.vaciar`.

### Volver al panel (`linea_al_panel`)

- Devuelve el foco al panel activo.
- Teclas: Tab, Mayús+Tab; en la línea de órdenes.
- Bloque: Núcleo. Manejador: `linea.al_panel`.
- Tecla fija.

### Decir la ruta del panel activo (`decir_ruta`)

- Anuncia la carpeta del panel activo.
- Teclas: Ctrl+Mayús+P; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_ruta`.
- Parámetro «activo».

### Decir la ruta del otro panel (`decir_ruta_otro`)

- Anuncia la carpeta del otro panel.
- Teclas: Ctrl+Mayús+O; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_ruta`.
- Parámetro «pasivo».

### Decir el resumen de la carpeta (`decir_resumen`)

- Carpetas, archivos, tamaño, marcas y filtro del panel activo.
- Teclas: Ctrl+Mayús+S; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_resumen`.

### Decir la información del elemento (`decir_info`)

- Tipo, tamaño, fechas y atributos del elemento del cursor.
- Teclas: Ctrl+Mayús+I; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_info`.

### Decir el espacio libre (`decir_espacio`)

- Espacio libre y total de la unidad del panel activo.
- Teclas: Ctrl+Mayús+E; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_espacio`.

### Decir el estado de las operaciones (`decir_operaciones`)

- Porcentaje, velocidad, tiempo restante y decisiones pendientes.
- Teclas: Ctrl+Mayús+T; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.decir_operaciones`.

### Repetir el último anuncio (`repetir_anuncio`)

- Repite el último anuncio; pulsado dos veces seguidas, dice su versión completa.
- Teclas: Ctrl+Mayús+U; en toda la ventana principal.
- Bloque: Núcleo. Manejador: `consulta.repetir_anuncio`.

### Leer la columna 1 (`leer_columna_1`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+1; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «1».

### Leer la columna 2 (`leer_columna_2`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+2; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «2».

### Leer la columna 3 (`leer_columna_3`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+3; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «3».

### Leer la columna 4 (`leer_columna_4`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+4; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «4».

### Leer la columna 5 (`leer_columna_5`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+5; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «5».

### Leer la columna 6 (`leer_columna_6`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+6; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «6».

### Leer la columna 7 (`leer_columna_7`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+7; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «7».

### Leer la columna 8 (`leer_columna_8`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+8; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «8».

### Leer la columna 9 (`leer_columna_9`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+9; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «9».

### Leer la columna 10 (`leer_columna_10`)

- Lee esa columna de la fila del cursor sin moverse.
- Teclas: Ctrl+0; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.leer_columna`.
- Parámetro «10».

### Leer la columna anterior (`columna_anterior`)

- Lee la columna anterior de la fila del cursor.
- Teclas: Izquierda; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.mover_columna`.
- Parámetro «-1».

### Leer la columna siguiente (`columna_siguiente`)

- Lee la columna siguiente de la fila del cursor.
- Teclas: Derecha; con el foco en un panel.
- Bloque: Núcleo. Manejador: `consulta.mover_columna`.
- Parámetro «1».

### Ir a la barra de botones (`ir_barra_botones`)

- Pone el foco en la barra de botones; Escape vuelve al panel.
- Teclas: Alt+Mayús+F11; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.ir_barra_botones`.

### Autocompletar (`linea_autocompletar`)

- Completa rutas, alias y órdenes internas en la línea de órdenes.
- Teclas: Ctrl+Espacio; en la línea de órdenes.
- Bloque: PE, personalización. Manejador: `personalizar_pe.linea_autocompletar`.

### Traer zCommander al frente (`traer_al_frente`)

- Restaura y activa la ventana de zCommander (solo como tecla global).
- Teclas: sin tecla; en toda la ventana principal.
- Bloque: PE, personalización. Manejador: `personalizar_pe.traer_al_frente`.
