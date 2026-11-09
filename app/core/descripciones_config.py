# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Etiqueta, ayuda y página de Preferencias de cada clave de configuración.

``DESCRIPCIONES[clave] = (etiqueta con &, ayuda para Ctrl+H, página)``. Página
``None``: la clave no aparece en Preferencias (se cambia desde otro sitio o es
interna). El diálogo de Preferencias (bloque F) se construye desde aquí y el
anexo ``docs/configuracion.md`` las publica. Las letras de acceso se asignan
por página; ``tools/comprobar_preferencias.py`` (bloque F) comprueba que no se repiten.
"""

from __future__ import annotations


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


GENERAL, PANELES, VISTA, ACCESIBILIDAD, OPERACIONES, VISOR, BUSQUEDA, RED = (
	"general", "paneles", "vista", "accesibilidad", "operaciones", "visor", "busqueda", "red",
)
# Páginas nuevas de la 2.0 (diseño 2.0, 14.3 y 10.18). «Sonidos» y «Confirmaciones»
# son páginas propias en el diálogo 2.0 (app/ui/paginas_propias.py); aquí siguen
# siendo el sitio de sus claves para el anexo y para el diálogo de la 1.x.
SONIDOS, COMPRIMIDOS, ACTUALIZACIONES, PERSONALIZACION, CONFIRMACIONES, COMPLEMENTOS = (
	"sonidos", "comprimidos", "actualizaciones", "personalizacion", "confirmaciones", "complementos",
)
PAGINAS = (
	(GENERAL, N_("General")), (PANELES, N_("Paneles")), (VISTA, N_("Vista")), (ACCESIBILIDAD, N_("Accesibilidad")),
	(SONIDOS, N_("Sonidos")), (OPERACIONES, N_("Operaciones")), (VISOR, N_("Visor y editor")), (BUSQUEDA, N_("Búsqueda")),
	(RED, N_("Red")), (COMPRIMIDOS, N_("Comprimidos")), (ACTUALIZACIONES, N_("Actualizaciones")),
	(PERSONALIZACION, N_("Personalización")), (COMPLEMENTOS, N_("Complementos")),
)
# «Confirmaciones» es una página propia (lista con casillas de app/services/confirmaciones.py),
# sin claves declarativas: no está en PAGINAS.

#: Claves del núcleo cuyo valor es un programa o una orden que zCommander ejecuta
#: (diseño 2.0, 7.2): una copia de seguridad no las restaura sin que la persona
#: las marque una a una. Quien añada una clave así la añade aquí.
#: 2.0.1: también las que deciden de dónde se descargan e instalan las actualizaciones
#: (``actualizaciones.fuente`` y ``actualizaciones.url_personalizada``): un perfil o una
#: copia ajenos podrían apuntar a un servidor que no es el de zCommander.
EJECUTA: frozenset[str] = frozenset({
	"editor.usar_externo", "editor.externo", "visor.externo", "general.diferencias_externo", "comprimidos.ruta_7zip",
	"actualizaciones.fuente", "actualizaciones.url_personalizada",
})

DESCRIPCIONES: dict[str, tuple[str, str, str | None]] = {
	# General
	"general.confirmar_salida": (N_("Confirmar antes de &salir"), N_("Pregunta antes de cerrar zCommander con F10 o Alt+X."), GENERAL),
	"general.confirmar_eliminar": (N_("Confirmar al &eliminar a la papelera"), N_("Pregunta antes de enviar a la papelera."), GENERAL),
	"general.confirmar_eliminar_definitivo": (N_("Confirmar al eliminar &definitivamente"), N_("Pregunta antes de eliminar sin papelera. Muy recomendable."), GENERAL),
	"general.confirmar_ejecutar": (N_("Confirmar antes de e&jecutar programas con Intro"), N_("Pregunta antes de ejecutar .exe, .bat, .cmd, .msi y accesos directos. Los .ps1, .vbs y .js siempre preguntan."), GENERAL),
	"general.usar_papelera": (N_("Eliminar envía a &la papelera"), N_("Si se desactiva, Eliminar actúa como Eliminar definitivamente y pide su confirmación."), GENERAL),
	"general.consola": (N_("C&onsola:"), N_("Programa que abre «Abrir consola aquí» y las órdenes en consola: cmd, PowerShell o Windows Terminal."), GENERAL),
	"general.ejecutar_siempre_en_consola": (N_("Ejecutar las órdenes siempre en una consola &nueva"), N_("La línea de órdenes abre una consola que queda abierta en lugar de capturar la salida."), GENERAL),
	"general.restaurar_sesion": (N_("&Restaurar carpetas y pestañas al arrancar"), N_("Vuelve a abrir las carpetas, pestañas y vistas de la última vez."), GENERAL),
	"general.tiempo_unidad_s": (N_("&Tiempo máximo de espera de una unidad (segundos):"), N_("Si una unidad o carpeta de red no responde en este tiempo, se da por no disponible."), GENERAL),
	"general.aviso_lectura_ms": (N_("Anunciar «Le&yendo» tras (milisegundos):"), N_("Si leer una carpeta tarda más, se anuncia «Leyendo».") , GENERAL),
	"general.tamano_historial": (N_("Tamaño del &historial de carpetas:"), N_("Cuántas carpetas recuerda cada panel."), GENERAL),
	"general.tamano_historial_ordenes": (N_("Ta&maño del historial de órdenes:"), N_("Cuántas órdenes recuerda la línea de órdenes."), GENERAL),
	"general.pegar_ruta_del_portapapeles": (N_("Pegar una r&uta del portapapeles lleva a ella"), N_("Si el portapapeles tiene texto con una ruta, Pegar va a esa carpeta en lugar de pegar archivos."), GENERAL),
	"general.diferencias_externo": (N_("Programa externo de &diferencias:"), N_("Orden para comparar dos archivos (%P y %T). Vacío: la comparación interna."), VISOR),
	"general.asistente_hecho": (N_("Asistente hecho"), N_("Interno: el asistente de primer arranque ya se mostró."), None),
	# Paneles
	"paneles.teclear_en_linea_ordenes": (N_("Al teclear en un panel, escribir en la &línea de órdenes"), N_("Como en Norton Commander. Si se desactiva, teclear hace búsqueda rápida."), PANELES),
	"paneles.mostrar_ocultos": (N_("Mostrar archivos &ocultos y de sistema"), N_("También con Ctrl+punto."), PANELES),
	"paneles.carpetas_primero": (N_("A&grupar las carpetas al principio"), N_("Las carpetas se muestran antes que los archivos."), PANELES),
	"paneles.orden_natural": (N_("Orden &natural de los números"), N_("«archivo2» va antes que «archivo10»."), PANELES),
	"paneles.fila_superior": (N_("Mostrar la fila «..» para &subir"), N_("Primera fila de cada carpeta que lleva a la carpeta superior."), PANELES),
	"paneles.entrar_en_comprimidos": (N_("Intro &entra en los comprimidos"), N_("ZIP, TAR y 7z se abren como carpetas. Si se desactiva, Intro los abre con su programa."), PANELES),
	"paneles.columnas": (N_("Columnas"), N_("Se eligen en Opciones, Columnas por defecto."), None),
	"paneles.anchos": (N_("Anchos"), N_("Interno: anchos de las columnas."), None),
	"paneles.formato_fecha": (N_("&Formato de las fechas:"), N_("Corta (8/11/2026 14:05), larga (con segundos) o ISO (2026-11-08 14:05)."), PANELES),
	"paneles.formato_tamano": (N_("Formato de los &tamaños:"), N_("Legible (1,2 MB), en bytes (1.234.567) o mixto (bytes hasta 1 MB)."), PANELES),
	"paneles.iconos": (N_("Mostrar &iconos"), N_("Iconos de Windows junto a los nombres."), PANELES),
	"paneles.vigilar_cambios": (N_("Actualizar solo al cambiar los arc&hivos"), N_("El panel se actualiza solo cuando cambian los archivos (no en unidades extraíbles)."), PANELES),
	"paneles.tiempo_busqueda_rapida_ms": (N_("Duración de la &búsqueda rápida (milisegundos):"), N_("Tiempo durante el que las letras tecleadas se suman a la búsqueda."), PANELES),
	"paneles.retardo_arbol_ms": (N_("Espera del á&rbol antes de cambiar el otro panel (milisegundos):"), N_("Pausa al moverse por la vista Árbol antes de ir a la carpeta."), PANELES),
	"paneles.orientacion": (N_("&Disposición de los paneles:"), N_("Lado a lado (vertical) o uno encima de otro (horizontal)."), PANELES),
	"paneles.seleccionar_sin_extension": (N_("Al renombrar, seleccionar el nombre sin la e&xtensión"), N_("En Renombrar en el sitio, solo queda seleccionado el nombre."), PANELES),
	"paneles.patrones_en_carpetas": (N_("Marcar por patrón incl&uye las carpetas"), N_("Marcar por patrón y filtros incluyen carpetas."), PANELES),
	"paneles.mover_tras_marcar": (N_("Bajar al siguiente al &marcar con Insert o Espacio"), N_("Como en Norton Commander."), PANELES),
	# Vista
	"vista.linea_ordenes_visible": (N_("Mostrar la &línea de órdenes"), N_("Campo para escribir órdenes de Windows debajo de los paneles."), VISTA),
	"vista.barra_teclas_visible": (N_("Mostrar la barra de &teclas F1 a F10"), N_("Botones con la acción de cada tecla F (para el ratón)."), VISTA),
	"vista.barra_estado_visible": (N_("Mostrar la barra de &estado"), N_("Mensajes, operaciones en curso y espacio libre."), VISTA),
	"vista.tema": (N_("Te&ma:"), N_("Sistema (colores de Windows), Norton clásico (azul y cian) o alto contraste."), VISTA),
	"vista.fuente": (N_("Tipo &de letra:"), N_("Vacío: el de Windows."), VISTA),
	"vista.tamano_fuente": (N_("Tama&ño de la letra (puntos):"), N_("De 8 a 40. Se aplica al momento a las listas de los paneles. El visor y el editor tienen su propio tamaño en la página «Visor y editor»."), VISTA),
	"vista.vista_rapida_kb": (N_("Límite de la vista &rápida (kilobytes):"), N_("Cuánto se lee de cada archivo en la vista rápida."), VISTA),
	# Accesibilidad
	"accesibilidad.anuncios": (N_("Anuncios por &el lector de pantalla"), N_("Si se desactiva, zCommander no dice nada por su cuenta salvo errores y preguntas."), ACCESIBILIDAD),
	"accesibilidad.detalle": (N_("&Detalle de los anuncios:"), N_("Breve: solo lo esencial y la respuesta a lo que pide. Normal: también cambios de carpeta y marcas. Detallado: también consejos y recuentos."), ACCESIBILIDAD),
	"accesibilidad.progreso_voz": (N_("Progreso de &las operaciones por voz:"), N_("Cada 25 %, al empezar y al terminar, o solo al terminar."), ACCESIBILIDAD),
	"accesibilidad.consejos": (N_("Conse&jos al llegar a sitios nuevos"), N_("Una frase con las teclas útiles al entrar en un comprimido, un servidor o una lista de resultados, y al arrancar."), ACCESIBILIDAD),
	"accesibilidad.leer_numero_fila": (N_("Lectura de columnas: decir el &número de fila"), N_("Al leer columnas con Izquierda, Derecha o Ctrl+número."), ACCESIBILIDAD),
	"accesibilidad.leer_cabecera": (N_("Lectura de columnas: decir el nombre de la col&umna"), N_("Al leer columnas con Izquierda, Derecha o Ctrl+número."), ACCESIBILIDAD),
	"accesibilidad.leer_contenido": (N_("Lectura de columnas: decir el c&ontenido"), N_("Si se desactivan las tres, se dice el contenido."), ACCESIBILIDAD),
	"paneles.marcas_como": (N_("Cómo se muestran las &marcas:"), N_(
		"Como selección de la lista: lo marcado queda seleccionado y el lector dice «seleccionado» al final de la fila "
		"(y, con varias marcas, «no seleccionado» en las demás). En la columna Marca: lo marcado dice «Marcado» en una "
		"columna que puede colocar donde quiera con Columnas y Orden de lectura (si la pone la primera, se oye antes "
		"del nombre); la lista no usa la selección para las marcas, así que ningún lector lo dice dos veces. Al elegirla, "
		"la columna Marca se añade la primera en las pestañas que no la tienen y no se puede quitar mientras siga elegida. "
		"Con NVDA leyendo las cabeceras de tabla, si la Marca va la primera NVDA dice «Nombre:» delante de cada fila sin "
		"marcar; para evitarlo, instale el complemento de zCommander para NVDA, ponga la Marca detrás del Nombre con "
		"Columnas u Orden de lectura, o desactive en NVDA la lectura de cabeceras de tabla."), ACCESIBILIDAD),
	"accesibilidad.retardo_voz_ms": (N_("&Retardo de los anuncios (milisegundos):"), N_("Espera antes de hablar para no pisar lo que el lector dice al mover el foco."), ACCESIBILIDAD),
	"accesibilidad.salida_voz": (N_("&Salida de los anuncios:"), N_("Automática (NVDA o JAWS directamente; Narrador y otros por notificaciones de Windows), siempre por el lector, siempre por notificaciones, o ninguna."), ACCESIBILIDAD),
	"accesibilidad.sapi_sin_lector": (N_("&Hablar con la voz de Windows si no hay lector"), N_("Sin lector de pantalla, los anuncios se dicen con SAPI."), ACCESIBILIDAD),
	"accesibilidad.silencio_nvda": (N_("Movimientos del &foco silenciosos con el complemento de NVDA"), N_("Cuando zCommander mueve el foco por su cuenta (al volver a leer, al aplicar un filtro), el complemento de zCommander para NVDA no lo anuncia."), ACCESIBILIDAD),
	"accesibilidad.complemento_nvda_ofrecido": (N_("Complemento de NVDA ofrecido"), N_("Interno: ya se ofreció instalar el complemento de zCommander para NVDA."), None),
	# Operaciones
	"operaciones.politica_conflicto": (N_("&Si el archivo ya existe:"), N_("Qué hacer por defecto al copiar o mover sobre un archivo que ya existe. Se puede cambiar en cada copia."), OPERACIONES),
	"operaciones.verificar": (N_("Verificar &después de copiar"), N_("Relee origen y copia y compara sus sumas SHA-256. Más lento."), OPERACIONES),
	"operaciones.conservar_fechas": (N_("Conservar &fechas y atributos"), N_("La copia mantiene la fecha de modificación y los atributos del original."), OPERACIONES),
	"operaciones.copiar_enlaces": (N_("Copiar los &enlaces como enlaces"), N_("Si se desactiva, los enlaces y uniones se omiten (nunca se sigue lo que apuntan)."), OPERACIONES),
	"operaciones.copiar_carpetas_vacias": (N_("Copiar &también las carpetas vacías"), N_("Crea en el destino las carpetas sin archivos."), OPERACIONES),
	"operaciones.max_paralelas": (N_("&Operaciones a la vez:"), N_("Cuántas operaciones en discos distintos pueden ir en paralelo. Se aplica al reiniciar."), OPERACIONES),
	"operaciones.tamano_bloque_kb": (N_("Tamaño de &bloque para comprimidos y red (kilobytes):"), N_("Trozo con el que se copia cuando no es disco local."), OPERACIONES),
	"operaciones.lista_conflictos": (N_("Mostrar la &lista de conflictos antes de copiar"), N_("Con varios archivos que ya existen, una sola lista para decidir. Si se desactiva, se pregunta de uno en uno."), OPERACIONES),
	# Visor y editor
	"visor.externo": (N_("V&isor externo:"), N_("Orden para Alt+F3, con %P para el archivo. Las asociaciones tienen prioridad."), VISOR),
	"visor.ajuste_linea": (N_("Ajuste de &línea en el visor"), N_("Las líneas largas continúan debajo. También con F2 en el visor."), VISOR),
	"visor.codificacion": (N_("C&odificación del visor:"), N_("Automática o una fija."), VISOR),
	"visor.limite_mb": (N_("Cargar &enteros los archivos de hasta (MB):"), N_("Los mayores se ven por bloques."), VISOR),
	"visor.tamano_fuente": (N_("&Tamaño de letra del visor:"), N_("En puntos."), VISOR),
	"editor.usar_externo": (N_("Usar un editor e&xterno con F4"), N_("Si se activa, F4 abre el editor externo en lugar del interno."), VISOR),
	"editor.externo": (N_("Edito&r externo:"), N_("Orden con %P para el archivo, por ejemplo notepad.exe %P."), VISOR),
	"editor.copia_seguridad": (N_("Guardar una copia .&bak al editar"), N_("Antes de guardar, el editor deja la versión anterior con extensión .bak."), VISOR),
	"editor.tamano_fuente": (N_("Ta&maño de letra del editor:"), N_("En puntos."), VISOR),
	# Búsqueda
	"busqueda.subcarpetas": (N_("Buscar en &subcarpetas por defecto"), N_("Valor inicial de la casilla en Buscar archivos."), BUSQUEDA),
	"busqueda.ocultos": (N_("Incluir archivos &ocultos por defecto"), N_("Valor inicial en Buscar archivos."), BUSQUEDA),
	"busqueda.max_resultados": (N_("&Máximo de resultados:"), N_("La búsqueda se detiene al llegar a este número."), BUSQUEDA),
	# Red
	"ftp.tiempo_espera_s": (N_("&Tiempo de espera de FTP y SFTP (segundos):"), N_("Si el servidor no responde en este tiempo, se da error."), RED),
	"ftp.pasivo": (N_("&Modo pasivo de FTP por defecto"), N_("Recomendado detrás de un router."), RED),
	"red.descubrir_al_entrar": (N_("&Buscar equipos al entrar en la raíz «Red»"), N_("Al abrir la raíz Red se buscan los equipos de la red local en segundo plano."), RED),
	"red.descubrir_mdns": (N_("Buscar &equipos también por mDNS"), N_("Encuentra NAS, impresoras y equipos que se anuncian por mDNS (Bonjour)."), RED),
	"red.descubrir_dominio": (N_("Buscar equipos también en el &dominio"), N_("Si el equipo está en un dominio, consulta sus equipos."), RED),
	"red.tiempo_descubrir_s": (N_("Tiempo máximo de &la búsqueda de equipos (segundos):"), N_("La búsqueda de equipos se detiene pasado este tiempo."), RED),
	"red.reconectar_al_entrar": (N_("Volver a conectar las &unidades de red al entrar"), N_("Si una unidad de red está desconectada, se intenta volver a conectar al entrar en ella."), RED),
	"red.exigir_cifrado": (N_("E&xigir conexiones cifradas"), N_("No se conecta a servidores que no admiten cifrado."), RED),
	"red.mostrar_otros_proveedores": (N_("Mostrar &otros proveedores de red (WebDAV, NFS)"), N_("La raíz Red muestra también las conexiones de otros proveedores de Windows."), RED),
	# ── 2.0 (diseño 2.0, 14.3) ───────────────────────────────────────────
	# General
	"general.arrancar_con_windows": (N_("Arrancar &zCommander al iniciar sesión en Windows"), N_("Solo en la versión compilada: añade zCommander al inicio de Windows. Es la única escritura en el Registro de Windows."), GENERAL),
	"general.no_preguntar": (N_("Confirmaciones &silenciadas"), N_("Confirmaciones que ya no se preguntan; se recuperan en la página Confirmaciones."), None),
	"copia.carpeta": (N_("Carpeta de las cop&ias de seguridad:"), N_("Dónde se guardan las copias de seguridad. Vacío: la carpeta backups de data."), GENERAL),
	"copia.conservar_automaticas": (N_("Copias automáticas &que se conservan:"), N_("Las copias automáticas previas a una restauración más antiguas se borran."), GENERAL),
	"copia.partes": (N_("Partes de la copia"), N_("Interno: partes que se eligieron la última vez."), None),
	# Paneles y vista
	"paneles.lectura": (N_("Orden de lectura de las columnas"), N_("Se elige en Opciones, Personalización, Orden de lectura de las columnas."), None),
	"vista.barra_botones_visible": (N_("Mostrar la &barra de botones"), N_("Barra de botones configurable debajo de los paneles. Alt+Mayús+F11 lleva a ella."), VISTA),
	"vista.teclas_en_menus": (N_("M&ostrar las teclas en los menús"), N_("Cada elemento de menú dice su tecla."), VISTA),
	"vista.menus_por_nivel": (N_("&Menús según el nivel del perfil"), N_("Los menús muestran solo las órdenes del nivel del perfil; al final de cada menú, Mostrar todas las órdenes."), PERSONALIZACION),
	"vista.columnas_por_carpeta": (N_("Columnas &y vista por carpeta"), N_("Al entrar en una carpeta se aplica el conjunto de columnas de su regla."), PERSONALIZACION),
	"vista.recordar_vista_por_carpeta": (N_("&Recordar el orden y la vista de cada carpeta"), N_("El orden, la vista y el filtro que cambie en una carpeta se recuerdan al volver."), PERSONALIZACION),
	# Sonidos
	"sonidos.activos": (N_("Activar &los sonidos"), N_("Sonidos que acompañan a lo que pasa en zCommander. También con Ctrl+F11."), SONIDOS),
	"sonidos.volumen": (N_("V&olumen:"), N_("De 0 a 100."), SONIDOS),
	"sonidos.paquete": (N_("Pa&quete:"), N_("Paquete de sonidos elegido."), SONIDOS),
	"sonidos.eventos": (N_("Sonidos"), N_("Qué eventos suenan (solo lo cambiado respecto a los valores de fábrica)."), None),
	"sonidos.progreso": (N_("Progreso &de las operaciones:"), N_("No, cada 25 % o cada 10 %."), SONIDOS),
	"sonidos.sustituir_anuncios": (N_("Los &sonidos sustituyen a algunos anuncios"), N_("Si un evento tiene sonido activo, no se dice su anuncio breve (por ejemplo, Marcado). Los errores y las preguntas se dicen siempre."), SONIDOS),
	"sonidos.intervalo_navegacion_ms": (N_("&Intervalo mínimo de los sonidos de navegación (milisegundos):"), N_("Como mucho un sonido de navegación en este tiempo."), SONIDOS),
	"sonidos.aviso_inicial_mostrado": (N_("Aviso de sonidos mostrado"), N_("Interno: ya se dijo que los sonidos están activados."), None),
	# Comprimidos
	"comprimidos.usar_libarchive": (N_("&Usar libarchive para leer RAR, CAB, ISO y otros"), N_("libarchive abre muchos formatos de comprimido como carpetas."), COMPRIMIDOS),
	"comprimidos.usar_7za": (N_("Usar 7&za para crear 7z con contraseña"), N_("El 7za que trae zCommander crea y lee 7z cifrados."), COMPRIMIDOS),
	"comprimidos.usar_7zip_instalado": (N_("Usar &el 7-Zip instalado si lo hay"), N_("Para RAR y 7z cifrados, si 7-Zip está instalado en el equipo."), COMPRIMIDOS),
	"comprimidos.ruta_7zip": (N_("Carpeta &de 7-Zip:"), N_("Vacío: se busca sola."), COMPRIMIDOS),
	"comprimidos.metodo_zip": (N_("&Método de compresión ZIP:"), N_("Deflate (el más compatible), Zstandard o almacenar sin comprimir."), COMPRIMIDOS),
	"comprimidos.flujos_como_carpeta": (N_("Abrir &los .gz, .bz2, .xz y .zst sueltos como carpeta"), N_("Un archivo comprimido suelto se ve como una carpeta con un archivo dentro."), COMPRIMIDOS),
	# Actualizaciones
	"actualizaciones.comprobar": (N_("&Buscar actualizaciones de zCommander"), N_("Comprueba de vez en cuando si hay una versión nueva. Nunca instala sin preguntar."), ACTUALIZACIONES),
	"actualizaciones.intervalo_horas": (N_("Cada cuántas &horas:"), N_("Intervalo entre comprobaciones de la aplicación."), ACTUALIZACIONES),
	"actualizaciones.fuente": (N_("&Origen de las actualizaciones:"), N_(
		"De dónde se busca la versión nueva de zCommander. Servidor de zCommander: xebolax.synology.me, el de siempre. "
		"GitHub: las versiones publicadas en el repositorio hxebolax/zCommander. Las dos: se consultan ambas y se ofrece "
		"la versión más nueva; si una no responde, se usa la otra sin avisar, y la descarga prueba la otra si falla. "
		"Una dirección personalizada: la que escriba en el campo siguiente (por ejemplo, una copia en su red). "
		"Con cualquier origen se exige la firma de zCommander: una versión sin firma o firmada por otro nunca se instala. "
		"Se aplica en la siguiente búsqueda, sin reiniciar. Los componentes y los complementos tienen su propio origen."),
		ACTUALIZACIONES),
	"actualizaciones.url_personalizada": (N_("Dirección per&sonalizada del archivo version.json:"), N_(
		"Solo se usa con el origen «Una dirección personalizada», y solo está disponible al elegirlo; con ese origen es "
		"obligatoria. Escriba la dirección completa del archivo version.json, que tiene que empezar por https:// y no "
		"puede llevar usuario ni contraseña. El archivo tiene que estar "
		"firmado por zCommander; el paquete se descarga de la misma carpeta o de las direcciones que indique el archivo."),
		ACTUALIZACIONES),
	"actualizaciones.componentes_comprobar": (N_("Buscar versiones &nuevas de los componentes"), N_("rclone, libarchive, 7za y FFmpeg."), ACTUALIZACIONES),
	"actualizaciones.componentes_intervalo_dias": (N_("Cada cuántos &días los componentes:"), N_("Intervalo entre comprobaciones de los componentes."), ACTUALIZACIONES),
	"actualizaciones.complementos_comprobar": (N_("Buscar actualizaciones de &los complementos"), N_("Para los complementos que publican sus actualizaciones."), ACTUALIZACIONES),
	# Personalización
	"teclado.esquema": (N_("&Esquema de teclas:"), N_("Norton (el de fábrica), Total Commander, Far o Explorador."), PERSONALIZACION),
	"teclado.globales": (N_("Teclas globales"), N_("Se eligen con el botón Teclas globales."), None),
	"teclado.globales_activas": (N_("Activar &las teclas globales"), N_("Teclas que funcionan con zCommander en segundo plano."), PERSONALIZACION),
	"linea.alias_activos": (N_("Alias en la línea &de órdenes"), N_("Los alias se expanden al ejecutar."), PERSONALIZACION),
	"linea.autocompletar": (N_("Autocompletar en la línea de &órdenes con Ctrl+Espacio"), N_("Completa rutas, alias y órdenes internas."), PERSONALIZACION),
	"macros.anunciar_pasos": (N_("A&nunciar cada paso de las macros"), N_("Dice cada paso al ejecutarse (nivel detalle)."), PERSONALIZACION),
	"macros.pausa_ms": (N_("Pa&usa entre los pasos de las macros (milisegundos):"), N_("De 0 a 5000."), PERSONALIZACION),
	"macros.detener_en_error": (N_("Detener la macro &si un paso falla"), N_("Un paso que falla detiene la macro y lo dice."), PERSONALIZACION),
	"reglas.activas": (N_("Apl&icar las reglas de anuncio, color y sonido"), N_("Enciende o apaga todas las reglas."), PERSONALIZACION),
	# Complementos
	"complementos.inhabilitados": (N_("Complementos inhabilitados"), N_("Se cambian en el gestor de complementos."), None),
	"complementos.permitir_sin_firma": (N_("Permitir complementos &sin firma"), N_("Si se desactiva, no se instalan ni cargan complementos sin firma."), COMPLEMENTOS),
	"complementos.fallos_maximos": (N_("&Fallos antes de dejar de usar un complemento:"), N_("Tras estos fallos en una sesión, el complemento deja de usarse hasta reiniciar."), COMPLEMENTOS),
	"complementos.modo_desarrollo": (N_("&Modo desarrollo de complementos"), N_("Para autores: permite recargar un complemento y anuncia sus avisos de tiempo y accesibilidad."), COMPLEMENTOS),
	"complementos.auditoria": (N_("&Registrar conexiones y programas de los complementos"), N_("Apunta en el registro las conexiones y procesos de los complementos sin el permiso correspondiente."), COMPLEMENTOS),
	"complementos.confiados": (N_("Complementos sin firma aceptados"), N_("Interno: suma de cada complemento sin firma que aceptó."), None),
	# Internas
	"teclado.personalizadas": (N_("Teclas"), N_("Se cambian en Opciones, Mapa de teclas."), None),
	"registro.nivel": (N_("Nivel del registro"), N_("DEBUG, INFO, WARNING o ERROR."), None),
	"ventana.x": ("x", "", None), "ventana.y": ("y", "", None), "ventana.ancho": ("ancho", "", None),
	"ventana.alto": ("alto", "", None), "ventana.maximizada": ("maximizada", "", None), "ventana.division": ("división", "", None),
	"seguridad.menus_locales_confiados": (N_("Menús locales de confianza"), N_("Carpetas cuyo zcommander.menu.json se ha aceptado (ruta y suma)."), None),
}
