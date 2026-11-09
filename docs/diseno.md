# zCommander: documento de diseño

## 0. Cómo leer este documento

Este documento describe todo lo que tendrá zCommander 1.0, para revisarlo con ojos nuevos antes de programar y para que cualquier persona o agente pueda programar una parte sin adivinar. Se lee por encabezados.

### 0.1 Mapa del documento

- 1 a 3: problema, objetivos, alcance, personas usuarias y principios.
- 4 a 8: lo que ve y hace la persona usuaria (ventana, marcas, teclas, menús y cada función).
- 9 a 13: cómo se construye (arquitectura, configuración, accesibilidad, errores, rendimiento).
- 14 a 16: seguridad, compatibilidad y alternativas consideradas.
- 17 a 20: pruebas, compilación, documentación y plan de trabajo.
- 21: riesgos. 22: historial del documento.

### 0.2 Anexos y fuentes únicas

Lo que cambia a menudo no se copia aquí: vive en el código y se publica en anexos generados con `python tools/generar_anexos.py` (una prueba falla si no están al día).

- [ordenes.md](ordenes.md): las 181 órdenes con teclas, ámbito, menú, bloque dueño y manejador. Fuente: `app/ui/ordenes.py`.
- [configuracion.md](configuracion.md): todas las claves de configuración con tipo, valor y regla. Fuente: `app/core/configuracion.py`.
- `data/docs/teclas.md`: lista de teclas para la persona usuaria.
- Interfaces en código: `app/services/vfs/base.py` (proveedores y errores), `app/services/vfs/resolver.py` (registro de proveedores), `app/services/operaciones/modelo.py` (operaciones), `app/ui/contexto.py` (contexto de las órdenes y protocolo del panel), `app/ui/anuncios.py` (anuncios), `app/services/teclas.py` (teclas y mapa).
- Investigación: [investigacion/repositorios.md](investigacion/repositorios.md) y [investigacion/norton-commander.md](investigacion/norton-commander.md).
- Revisión: [revision/ronda-1.md](revision/ronda-1.md), [revision/ronda-2.md](revision/ronda-2.md) [revision/ronda-3.md](revision/ronda-3.md) y [revision/ronda-4.md](revision/ronda-4.md) (hallazgos de EGM y su resolución).

### 0.3 Dependencias externas

zCommander se generó con los agentes de `E:\Antigravity\Agentes\agentes` (convenciones comunes en `E:\Antigravity\Agentes\compartido\perfil-desarrollador.md`). Sus plantillas ya están copiadas en el proyecto; el proyecto no depende de esa carpeta para funcionar. Piezas reutilizadas:

- `app/core/configuracion.py` (agente configuracion): clase `Configuracion` con `obtener`, `establecer`, `establecer_varias`, `lote()`, `suscribir(funcion, prefijo)`, `guardar()` (lanza `ErrorConfiguracion`) y `guardar_pendiente()`.
- `app/core/secretos.py`: `AlmacenSecretos` (DPAPI).
- `app/core/tareas.py` (agente hilos-y-tareas): `GestorTareas(max_hilos, ...)` (los hilos se fijan al crearlo) y `enviar(funcion, *args, al_terminar, al_fallar, al_progresar, clave_unica, nombre, tiempo_maximo, duplicadas) -> Tarea | None`, que llama a `funcion(tarea, *args)` en un hilo con la `Tarea` como primer argumento y devuelve `None` si se rechaza o el gestor está cerrado; `clave_unica` unifica o rechaza duplicadas (no cancela la anterior); `TokenCancelacion`, `HitosProgreso`, `ejecutar_en_interfaz`; `apagar(espera)` cancela todo al instante.
- `app/ui/accesibilidad/` (agente accesibilidad-wx): `dialogos.py` (`preparar_dialogo`, `crear_botonera`, `mostrar_mensaje`, `mostrar_error`, `confirmar`, `elegir_opcion`, `pedir_texto`), `nombres.py` (`crear_campo`), `voz.py` (cola de voz con canales e historial, ampliada con la salida UIA de `uia.py`), `composicion.py` (texto del anuncio de una celda), `revision_teclado.py` (`revisar_teclado`, que devuelve la lista de problemas de letras y atajos de una ventana ya construida).
- `app/ui/dialogo_preferencias.py`: diálogo declarativo con `Pagina` y `Opcion`.
- `app/ui/visor_ayuda.py` y `app/core/documentacion.py` (agente documentacion-usuario): visor del manual con F1.
- `tools/revision_egm.py` (agente revision-egm).

### 0.4 Convenciones de escritura

- Teclas abreviadas como en Windows en español: Ctrl, Alt, Mayús, Intro, Supr, Retroceso, Re Pág, Av Pág, Num + (más del teclado numérico). El manual de usuario las escribe igual.
- «Menú, Elemento» indica una ruta de menú: «Opciones, Preferencias».
- Las secciones nombran órdenes por su etiqueta; las teclas exactas están en la sección 6 y en el anexo de órdenes. Si en la sección 8 se cita una tecla, es la de fábrica y solo como ayuda: manda el anexo.

### 0.5 Glosario

- **Panel**: cada mitad de la ventana. Muestra una carpeta del disco, un comprimido, un servidor o una lista de resultados. Cada lado puede tener varias pestañas; cada pestaña es un panel.
- **Panel activo** y **panel pasivo**: el que tiene el foco y el otro. Copiar lleva del activo al pasivo. Una vista (Información, Árbol, Vista rápida) nunca es panel activo: con el foco en ella, el activo sigue siendo la lista del otro lado.
- **Cursor**: el elemento en el que está la persona dentro del panel (el enfocado de la lista).
- **Marcar**: señalar varios elementos para operar con ellos a la vez. Las marcas son la selección nativa de Windows.
- **Elementos de trabajo**: los marcados; si no hay ninguno, el del cursor (nunca «..»).
- **Fila «..»**: primera fila de una carpeta que no es raíz; lleva a la carpeta superior.
- **Proveedor** (sistema de archivos virtual, VFS en inglés): código que sabe listar y operar en un tipo de origen.
- **Orden**: acción con identificador, etiqueta, ayuda y teclas. Menús, barra de teclas, mapa de teclas, paleta y lista de teclas salen del mismo catálogo.
- **Ámbito**: dónde funciona la tecla de una orden; hay tres, los del anexo: panel (foco en la lista de archivos), global (toda la ventana) y línea de órdenes.
- **Perfil**: conjunto de valores de preferencias para un tipo de persona: Novato, Intermedio o Avanzado. Los valores de fábrica son los del perfil Intermedio.
- **Anuncio**: texto que zCommander envía al lector además de lo que este lee solo.
- **Lista de conflictos**: lista con los archivos que ya existen en el destino, para decidir de una vez qué hacer con cada uno.
- **Cesta**: lista de elementos reunidos desde varias carpetas para operar con ellos juntos.
- **Bloque**: parte del plan de trabajo (núcleo y bloques A a H, sección 20).
- **Nivel de anuncio**: esencial, resultado, normal o detalle (sección 11).
- **Carril**: volumen (disco, recurso de red, servidor o comprimido) que usa una operación; dos operaciones que comparten carril van una detrás de otra (9.6).
- **Lista de resultados**: panel virtual con resultados de búsqueda, vista plana o cesta, con la columna Ruta.
- **MSAA** y **UIA**: las dos interfaces de accesibilidad de Windows por las que los lectores leen las ventanas (Microsoft Active Accessibility y UI Automation).
- **Notificación UIA**: mensaje que una aplicación pide leer al lector sin mover el foco; lo leen Narrador y NVDA.
- **DPAPI**: cifrado de Windows ligado a la cuenta de usuario; por eso las contraseñas guardadas no sirven en otro equipo.
- **UNC**: ruta de red `\\servidor\recurso`.
- **STA**: modo de hilos que exigen algunos objetos COM del shell de Windows.
- **GIL**: candado global de Python; mientras un hilo lo tiene, los demás esperan.
- **BOM**: marca al principio de un archivo de texto que indica su codificación.
- **CRC32, SFV, MD5, SHA**: tipos de sumas de comprobación; SFV es un formato de archivo con sumas CRC32.
- **SAPI**: voz sintética de Windows (sin lector de pantalla).
- **Marca de la Web** (MOTW): flujo `Zone.Identifier` que Windows añade a lo descargado de Internet para avisar antes de ejecutarlo.
- **Punto de análisis**: marca de Windows en enlaces simbólicos, uniones y archivos de OneDrive.
- **Distribución de escritorio y de portátil** de NVDA: dos juegos de teclas del lector; la de escritorio usa el teclado numérico para el cursor de revisión (leer la pantalla sin mover el foco).
- **Goldfish**: revisor de EGM (Elephant-Goldfish Model) que lee el documento sin conocer la conversación en que se escribió.

## 1. Problema, objetivos y alcance

### 1.1 Problema que resuelve

- Los gestores de doble panel más usados tienen listas sin nombre accesible o dibujadas a mano, que no exponen columnas, estado ni posición al lector de pantalla.
- Marcan los archivos solo con color: una persona ciega no sabe qué está marcado.
- No dicen en qué panel ni en qué carpeta se está al cambiar; el progreso de las copias es mudo o demasiado hablador; los diálogos de conflicto tienen campos sin etiqueta y el foco en sitios inesperados.
- Muchas personas ciegas dependen de complementos de NVDA para cosas básicas (decir el tamaño, copiar nombres).
- Detalles y fuentes: [investigacion/norton-commander.md](investigacion/norton-commander.md), sección 3.

### 1.2 Objetivos medibles

zCommander 1.0 se da por bueno si:

1. Cada tarea de la sección 8 se completa solo con teclado y con NVDA, JAWS y Narrador, siguiendo la lista de `docs/pruebas-manuales.md` (se escribe en el bloque H), sin mirar la pantalla.
2. Todas las órdenes del catálogo tienen manejador y tecla o menú; ninguna tecla de fábrica se repite en un mismo ámbito (prueba automática).
3. Cada ventana y diálogo pasa `revisar_teclado` sin problemas (prueba automática).
4. Las pruebas automáticas pasan y `ruff check` no da errores.
5. Una carpeta de 100 000 archivos se lista y muestra en menos de 2 s en un SSD; la ventana aparece en menos de 1,5 s (pruebas marcadas como lentas).
6. Copiar 1000 archivos pequeños y uno de 200 MB con verificación termina sin errores y la interfaz responde mientras tanto.
7. La compilación con cx_Freeze arranca en un Windows sin Python (`--comprobar-arranque` devuelve 0).

### 1.3 Qué incluye la versión 1.0

Todo lo que sigue; no hay fases posteriores.

1. Dos paneles con vistas completa, breve, información, árbol y vista rápida; pestañas; historial; favoritos; filtros; ordenación; archivos ocultos (secciones 4 y 8.1, 8.21).
2. Ver, editar, copiar, mover, renombrar, crear carpeta, eliminar a la papelera o definitivamente, crear archivo, duplicar, atributos y fechas, propiedades de Windows y enlaces (8.2 a 8.11).
3. Motor de copia con cola por volumen, pausa, cancelación, lista de conflictos, verificación, conservación de fechas y atributos, rutas largas (8.4 y 8.5).
4. Marcas por patrón, por extensión, todo, nada, invertir, guardar y restaurar; cesta (sección 5 y 8.25).
5. Búsqueda por nombre, contenido, tamaño, fecha y atributos con resultados en un panel (8.12).
6. Comparar y sincronizar carpetas (8.13).
7. Renombrado múltiple con máscaras, vista previa y deshacer (8.14).
8. Comprimidos ZIP, TAR y 7z como carpetas; comprimir, extraer, probar (8.15).
9. FTP, FTPS y SFTP con gestor de conexiones (8.16).
10. Sumas de comprobación, dividir, unir, comparar archivos y tamaño de carpetas (8.19 y 8.20).
11. Línea de órdenes, menú de usuario, asociaciones y salida de órdenes (8.17).
12. Visor de texto y hexadecimal; editor de texto (8.2 y 8.3).
13. Portapapeles compatible con el Explorador, arrastrar y soltar, menú contextual propio y de Windows (8.10 y 8.18).
14. Selector de unidades y unidades de red (8.1 y 8.22).
15. Preferencias, perfiles, asistente de primer arranque, mapa de teclas, columnas, temas, paleta de órdenes y ayuda de teclado (8.26 y 8.27; el número 8.24 se suprimió en la versión 1.2).
16. Accesibilidad: lectura por columnas, anuncios por niveles, teclas de consulta, historial de anuncios, Ctrl+H en todo (sección 11).
17. Manual, lista de teclas, novedades y ayuda F1 (sección 19).
18. Pruebas automáticas, compilación con cx_Freeze y ZIP de distribución (secciones 17 y 18).

### 1.4 Fuera de alcance (con motivo)

- Complementos de Total Commander (WCX, WFX, WLX, WDX): exigen DLL nativas y no aportan accesibilidad.
- Miniaturas y visor de imágenes: las imágenes se abren con su programa asociado.
- RAR: no hay biblioteca libre fiable; Intro lo abre con su programa.
- Escribir dentro de TAR y 7z como carpeta: se crean con Comprimir; solo ZIP admite escritura como carpeta.
- Columna Propietario y permisos NTFS: el diálogo de Propiedades de Windows ya los gestiona y es accesible.
- Límite de velocidad de copia y reanudar copias interrumpidas: complejidad sin uso claro en un gestor local.
- TAR con zst: Python 3.15 lo lee con `compression.zstd`, pero queda fuera para no ampliar las pruebas; se añadirá si se pide.
- Borrado seguro: en SSD no es fiable y da falsa seguridad.
- Deshacer eliminar: para eso está la papelera de Windows.
- Traducciones: las cadenas van marcadas con `_()`, pero solo se entrega el español.
- Bandeja del sistema y actualización automática por Internet.

## 2. Personas usuarias y perfiles

### 2.1 Quién lo usará

- **Persona ciega con lector de pantalla** (caso principal): solo teclado; necesita saber en qué panel y carpeta está, qué tiene el cursor, cuántos marcados hay y qué pasa con las operaciones, sin ruido.
- **Persona con baja visión**: letra grande, alto contraste, foco visible.
- **Persona vidente con teclado** que viene de Norton o Total Commander.
- **Persona con ratón**: doble clic, menús, arrastrar y soltar, barra de teclas.

### 2.2 Perfiles

Un perfil es un punto de partida: aplica unos valores que luego se cambian uno a uno. Elegir perfil pide confirmación. El perfil activo no se guarda: se calcula comparando la configuración con cada perfil; si no coincide con ninguno, se muestra «Personalizado». Valores exactos: `PERFILES` en `app/services/perfiles.py`.

| Preferencia (clave) | Novato | Intermedio | Avanzado |
|---|---|---|---|
| Teclear en un panel va a la línea de órdenes (`paneles.teclear_en_linea_ordenes`) | No | No | Sí |
| Línea de órdenes visible (`vista.linea_ordenes_visible`) | No | Sí | Sí |
| Confirmar eliminar a la papelera (`general.confirmar_eliminar`) | Sí | Sí | No |
| Confirmar salir (`general.confirmar_salida`) | Sí | Sí | No |
| Confirmar ejecutar programas con Intro (`general.confirmar_ejecutar`) | Sí | No | No |
| Mostrar ocultos y de sistema (`paneles.mostrar_ocultos`) | No | No | Sí |
| Detalle de los anuncios (`accesibilidad.detalle`) | detallado | normal | breve |
| Progreso por voz (`accesibilidad.progreso_voz`) | hitos | inicio_fin | final |
| Consejos al llegar a un sitio nuevo (`accesibilidad.consejos`) | Sí | No | No |
| Columnas (`paneles.columnas`) | nombre, tipo, tamaño, modificado | nombre, extensión, tamaño, modificado | nombre, extensión, tamaño, modificado, atributos |

Esta es la única tabla grande del documento. El borrado definitivo siempre se confirma (`general.confirmar_eliminar_definitivo`) y no depende del perfil. Los **consejos** son una frase con las teclas útiles al entrar por primera vez en la sesión en un comprimido, un servidor, una lista de resultados o un diálogo complejo (por ejemplo: «Comprimido. F5 extrae al otro panel; Retroceso en la raíz sale del comprimido»).

## 3. Principios

1. **Accesibilidad primero**: controles nativos de Windows, etiqueta creada justo antes de cada control, letras de acceso sin choques, Ctrl+H en todo, nada que solo se vea.
2. **La interfaz nunca se bloquea**: listar, copiar, buscar, calcular, conectar y leer comprimidos van en hilos.
3. **Portable**: todo en `data/` junto a `main.py` o al `.exe`; nada en `%APPDATA%`, `%TEMP%` ni el registro.
4. **Ningún error se pierde**: todo fallo queda en `data/logs` con archivo, línea, función, hilo y traza; la persona recibe un mensaje en español con qué pasó y qué hacer.
5. **Nunca se pierden datos**: copia a un temporal y renombrado final; al mover se borra el origen solo tras copiarlo (y verificarlo, si se pidió); papelera por defecto.
6. **Lógica sin wx** en `app/services`, probada sin ventanas.
7. **Una sola fuente de verdad**: el catálogo de órdenes y los valores por defecto en código; los documentos se generan de ahí.
8. **No repetir al lector** lo que ya lee solo.

## 4. La ventana principal

### 4.1 Disposición

1. **Barra de menús** nativa: Izquierdo, Archivos, Comandos, Opciones, Derecho, Ayuda. F9 la abre (`WM_SYSCOMMAND` con `SC_KEYMENU`).
2. **Zona central**, que muestra una de dos cosas:
	- los **paneles**: un `wx.SplitterWindow` vertical (u horizontal, preferencia) con el lado izquierdo y el derecho;
	- la **salida de las órdenes**: texto de solo lectura con todo lo que han escrito las órdenes de la sesión. «Mostrar u ocultar los paneles» alterna entre las dos, como el Ctrl+O de Norton. Al mostrar la salida, el foco va a su texto, al final de lo último escrito, y se anuncia «Salida de las órdenes» (nivel resultado); solo valen las órdenes globales y las teclas de lectura del texto; Tab va a la línea de órdenes si está visible; otra vez la misma orden vuelve a los paneles, con el foco en el panel y el elemento donde estaba.
3. **Línea de órdenes** (opcional): etiqueta con la carpeta del panel activo y un campo de texto.
4. **Barra de teclas** (opcional): diez botones F1 a F10 cuyo texto cambia al pulsar Mayús, Ctrl o Alt. Es para el ratón y queda fuera del orden de tabulación.
5. **Barra de estado**: último mensaje, operaciones en curso y espacio libre.

### 4.2 Cada lado

Un lado es un `LadoPaneles` con un `wx.Notebook` en el que cada pestaña es un `PanelArchivos`. Cada panel tiene, por orden de creación:

1. Etiqueta (`wx.StaticText`) con «Izquierdo: C:\Usuarios\Ana» y, si los hay, «, filtro *.mp3» o «, pestaña bloqueada». Es el nombre accesible de la lista: se actualiza al cambiar de carpeta para que el lector diga dónde está al volver al panel.
2. Un `wx.Simplebook` con las vistas: la lista de archivos (completa o breve), Información, Árbol y Vista rápida.
3. Línea de resumen (`wx.TextCtrl` de solo lectura, fuera del orden de tabulación): «12 carpetas y 40 archivos, 1,2 GB. Marcados: 3 archivos, 25 MB».
4. Campo de filtro rápido, oculto salvo cuando se usa.

### 4.3 La lista de archivos

- `ListaArchivos`: `wx.ListCtrl` virtual en modo informe, propia de zCommander. Formatea cada celda al pedirla (`OnGetItemText`) desde la lista de `Entrada`; no guarda cadenas por adelantado. Estilo `LVS_SHOWSELALWAYS` para ver las marcas en el panel pasivo.
- Columnas disponibles: nombre, extensión, tipo (descripción de Windows), tamaño, modificado, creado, atributos y ruta (solo en listas de resultados). Se eligen por lado en «Izquierdo, Columnas...» o «Derecho, Columnas...» y, para los paneles nuevos, en «Opciones, Columnas por defecto...».
- Carpetas antes que archivos (preferencia). En la columna Tamaño de una carpeta se lee «Carpeta» o, si se calculó, su tamaño.
- La fila «..» va primero en toda carpeta que no es raíz (preferencia).
- Iconos opcionales (desactivados por defecto), pedidos en un hilo y en caché por extensión.

### 4.4 Vistas

- **Completa** y **breve** (solo el nombre).
- **Información**: texto de solo lectura con los datos del elemento del cursor del otro panel (nombre, tipo, tamaño, fechas, atributos, destino del enlace, versión del ejecutable) y de su unidad (libre, total, sistema de archivos, etiqueta, número de serie). Se actualiza al mover el cursor en el otro panel, 300 ms después de la última tecla.
- **Árbol**: árbol de carpetas (`ArbolCarpetas`, el mismo componente que usa el diálogo del árbol) de la unidad del otro panel, cargado bajo demanda; tras una pausa (preferencia, 400 ms) el otro panel va a la carpeta elegida.
- **Vista rápida**: contenido del archivo del cursor del otro panel (texto con la codificación detectada o hexadecimal si es binario), hasta un límite de kilobytes (preferencia). No lee archivos que solo están en la nube ni rutas de red lentas sin que la persona lo pida (Intro en la vista).
- Con el teclado, Información (Ctrl+L) y Vista rápida (Ctrl+Q) se ponen en el **lado pasivo** (como Norton); Árbol, desde el menú o con una tecla asignada en el mapa. Desde el menú Izquierdo o Derecho, en ese lado. Otra pulsación vuelve a la vista anterior.
- Teclas dentro de las vistas: en Información y Vista rápida valen solo las órdenes globales y Tab; las flechas, Inicio, Fin, Re Pág, Av Pág, Ctrl+A y Ctrl+C son del texto. En Árbol, las flechas, Num +, Num - y Num * son del árbol (abrir y cerrar ramas), las letras buscan en el árbol e Intro lleva el otro panel a la carpeta elegida.

### 4.5 Pestañas

- Nueva pestaña con la misma carpeta, cerrar (la última no), siguiente, anterior, ir a la número 1 a 9, cerrar las demás, bloquear y lista de pestañas.
- El título es el nombre de la carpeta. Al cambiar de pestaña se anuncia (nivel resultado) «Pestaña 2 de 3, Documentos».
- Una pestaña bloqueada no cambia de carpeta: entrar en otra abre una pestaña nueva en ese lado. Retroceso y «..» también abren pestaña nueva.
- Las pestañas ocultas no se vigilan; al volver a una, se refresca.

### 4.6 Foco, Tab y lados ocultos

- Tab y Mayús+Tab pasan al otro panel (no recorren los controles). Al llegar, el lector lee el nombre de la lista (la ruta) y la fila; zCommander solo añade lo que el lector no puede saber: «3 marcados» o «filtro *.mp3» (nivel normal).
- Si el otro lado está oculto, Tab no hace nada y se anuncia «El otro panel está oculto».
- Si el lado pasivo muestra Información, Árbol o Vista rápida, el destino de copiar y mover es la carpeta de su pestaña; Tab lleva el foco a su vista. Con el foco en una vista, el panel activo sigue siendo la lista del otro lado: las órdenes globales (ver, copiar, eliminar...) actúan sobre sus elementos de trabajo y la carpeta de la vista es el destino.
- La línea de órdenes se alcanza con «Ir a la línea de órdenes» (la muestra si estaba oculta) o tecleando, si así está configurado. Escape la vacía; vacía, devuelve el foco al panel.
- Al cerrar cualquier diálogo, el foco vuelve al panel y al elemento donde estaba.

### 4.7 Estados del panel

- **Listo**: muestra su carpeta.
- **Leyendo**: lista en un hilo. Si tarda más de 300 ms (preferencia), la lista muestra una fila «Leyendo...» y se anuncia; Escape cancela y el panel vuelve a la carpeta anterior.
- **Error**: si la carpeta no se puede leer, el panel se queda en la anterior y avisa («No tiene permiso para abrir X»). Si no hay carpeta anterior (arranque o sesión restaurada), sube hasta la primera carpeta que exista; si ninguna, va a la carpeta personal.
- **Desconectado** (FTP, SFTP): si se pierde la conexión, se reintenta una vez; si falla, el panel pasa al disco local (carpeta personal) y avisa.
- La carpeta abierta desaparece (borrada desde fuera): el panel sube a la primera carpeta superior que exista y lo anuncia.
- Unidad que no responde: error tras el tiempo límite (preferencia, 10 s) sin congelar nada.

## 5. Cursor, marcas y elementos de trabajo

### 5.1 Un solo modelo, el de Norton

La **fuente de verdad de las marcas es el modelo del panel**: un conjunto de nombres marcados. La **selección nativa** de la lista solo lo refleja, para que el lector diga «seleccionado», y el cursor es el **elemento enfocado** de la lista. Los elementos de trabajo salen siempre del modelo, nunca de la selección nativa (así un refresco que cambia las filas de sitio no puede hacer que F8 borre otra cosa). La lista cambia de modo según haya marcas:

- **Sin marcas**: selección simple. Las flechas mueven el cursor de forma nativa y el elemento del cursor aparece seleccionado; el lector no dice «no seleccionado» porque las filas no se exponen como seleccionables en grupo.
- **Con marcas**: selección múltiple (se quita `LVS_SINGLESEL` en caliente). Las flechas, Re Pág, Av Pág, Inicio y Fin mueven solo el foco (las intercepta zCommander); el lector dice «seleccionado» o «no seleccionado» en cada fila. El cursor se dibuja con un color propio (`OnGetItemAttr`).
- Al quitar la última marca, la lista vuelve a selección simple con el cursor seleccionado.
- El cambio de modo se hace con `SetWindowStyleFlag` (wx guarda el estilo y no recrea la lista) y siempre antes de mover el foco, para que el lector lea el estado nuevo.
- Tras cada refresco, cambio de orden o de filtro, la selección nativa se reaplica desde el modelo de una vez (`LVM_SETITEMSTATE` para quitar todas y después solo las marcadas), en el mismo manejador y sin anuncios.
- Con ratón, en modo múltiple un clic simple solo mueve el cursor (no borra las marcas); Ctrl+clic marca o desmarca y Mayús+clic marca un rango.

Comprobado con MSAA el 8 de noviembre de 2026 (experimentos de [revision/ronda-1.md](revision/ronda-1.md)): mover solo el foco dispara el evento de foco; el estado «seleccionado» se informa; el cambio de estilo no recrea el control. Falta comprobarlo con NVDA, JAWS y Narrador reales (riesgo 21.1).

### 5.2 Marcar

- **Marcar y bajar** (Insert o Espacio): alterna la marca del cursor, anuncia «Marcado: nombre» o «Desmarcado: nombre» (sin interrumpir, porque al bajar el lector lee la fila siguiente) y baja (preferencia `paneles.mover_tras_marcar`).
- **Marcar sin mover** (Ctrl+Espacio, el gesto del Explorador).
- **Mayús+flechas, Re Pág, Av Pág, Inicio, Fin**: marcan desde el cursor hasta la nueva posición, sin quitar las marcas anteriores (lo hace zCommander).
- **Por patrón**, **desmarcar por patrón**, **invertir** (solo archivos), **marcar todo**, **desmarcar todo**, **por extensión del cursor**, **restaurar las de antes de la última operación**, **guardar en archivo** y **cargar desde archivo**.
- Con el filtro rápido activo, marcar todo marca solo lo visible; al quitar el filtro con Escape las marcas se conservan. Es la forma de marcar por patrón sin teclado numérico.
- Recuentos: tras marcar en grupo se anuncia (nivel resultado) «Marcados 12, 340 MB».
- Las marcas se pierden al salir de la carpeta (como en Norton) y se recuperan con Restaurar marcas mientras no se haga otra operación.

### 5.3 Patrones

- Comodines `*` y `?`; varios separados por `;`, `,` o espacio; exclusión tras `|` (`*.* | *.bak`). `*.*` coincide también con nombres sin extensión. Sin distinguir mayúsculas.
- Por defecto se aplican solo a archivos (preferencia para carpetas).
- Los diálogos recuerdan los últimos patrones.

### 5.4 Elementos de trabajo y alcance

- Una orden actúa sobre los marcados; si no hay, sobre el del cursor; nunca sobre «..». Si no queda nada, avisa «No hay elementos» y no hace nada.
- Toda orden que actúa sobre elementos sin abrir un diálogo (eliminar sin confirmación, pegar, añadir a la cesta) anuncia su alcance como aviso esencial: «3 marcados a la papelera» o «canción.mp3 a la papelera». Si abre un diálogo, el diálogo ya lo dice.
- Aunque las confirmaciones estén desactivadas, si hay marcas y el cursor no está sobre ninguna, se pregunta antes de eliminar o mover («Hay 3 marcados y el cursor está en otro elemento. ¿Actuar sobre los 3 marcados?»).

### 5.5 Búsqueda rápida y letras

- Por defecto, teclear letras en un panel es **búsqueda rápida**: el cursor va al primer elemento que empieza así (sin distinguir mayúsculas ni acentos); las letras se acumulan mientras no pase el tiempo de la preferencia (1 s). Un tono corto (si los sonidos están activos) indica que terminó.
- Espacio y Retroceso:
	- Con una búsqueda rápida viva (menos de 1 s desde la última letra), Espacio añade un espacio a lo buscado y Retroceso borra la última letra.
	- Sin búsqueda viva, Espacio marca y baja, y Retroceso sube de carpeta.
	- Con «Teclear va a la línea de órdenes», si la línea tiene texto, Espacio y Retroceso se escriben en ella; si está vacía, marcan y suben como siempre.
- Con la preferencia «Teclear va a la línea de órdenes» (perfil avanzado), las letras se escriben en la línea de órdenes, como en Norton.
- «Ir a la línea de órdenes» con una búsqueda viva pasa lo tecleado a la línea de órdenes.
- La búsqueda rápida explícita abre un campo con etiqueta «Buscar»; Intro o Escape lo cierran.

### 5.6 Al volver a leer una carpeta

Se conservan el cursor (por nombre; si desapareció, la fila que ocupaba) y las marcas (por nombre, desde el modelo; las de archivos que ya no existen se quitan). Si el elemento del cursor sigue en su sitio, el foco no se toca y el lector no dice nada. Los temporales de copia `~zc*.tmp` no se muestran.

### 5.7 Vigilancia de cambios

Con `wx.FileSystemWatcher` (creado cuando el bucle de eventos ya está en marcha), solo en la pestaña visible de cada lado y solo en discos internos y unidades de red. No se vigilan unidades extraíbles ni discos USB externos aunque Windows los declare fijos (se mira el tipo de bus con `IOCTL_STORAGE_QUERY_PROPERTY`), para no impedir expulsarlos: se refresca al volver al panel. Los cambios se agrupan (un refresco por segundo, que se espacia hasta 5 s si la carpeta cambia sin parar). Un aviso de desbordamiento provoca un refresco completo; un error deja de vigilar ese panel. Antes de renombrar, mover o eliminar una carpeta que contiene la vigilada, se suelta la vigilancia. Se puede desactivar (preferencia).

## 6. Teclas

La lista completa, con cada tecla y su ámbito, está en el anexo [ordenes.md](ordenes.md) y en `data/docs/teclas.md`, generados del catálogo. Aquí van las reglas y lo esencial.

### 6.1 Reglas del mapa de fábrica

- Las teclas F y sus combinaciones son las de Norton Commander (F3 ver, F5 copiar, F6 mover, F7 carpeta, F8 eliminar, F9 menús, F10 salir; Alt+F1 y Alt+F2 unidades; Alt+F7 buscar; Ctrl+F3 a Ctrl+F7 ordenar; Ctrl+L información; Ctrl+Q vista rápida; Ctrl+O paneles; Ctrl+P panel pasivo; Ctrl+U intercambiar; Ctrl+R volver a leer). Lo que Norton no tenía sigue a Double Commander o Total Commander (Ctrl+T y Ctrl+W pestañas, Ctrl+D favoritos, Ctrl+M renombrado múltiple, Ctrl+B vista plana, Alt+Izquierda y Alt+Derecha historial).
- Alias de Windows sin choque: Retroceso y Alt+Arriba suben de carpeta; Ctrl+Espacio marca sin mover; Supr elimina; Alt+Intro propiedades; Ctrl+C, Ctrl+X y Ctrl+V portapapeles.
- No se usan Ctrl+Alt+letra (en teclado español es AltGr). Signos de puntuación solo en Ctrl+punto (ocultos) y Ctrl+coma (preferencias), que están también en los menús. La raíz es Ctrl+Retroceso porque la barra invertida necesita AltGr.
- Alt+letra queda para los menús (I, A, C, O, D, U), salvo Alt+X (salir), Alt+Z (igualar paneles) y Alt+1 a Alt+9 (pestañas), que no son letras de ningún menú.
- Reservadas por Windows: Alt+F4, Alt+Espacio, Alt+Tab, Ctrl+Escape, Ctrl+Mayús+Escape. Fijas (no se pueden cambiar): Tab (cambiar de panel), Ctrl+H (ayuda del control), F9 (barra de menús), Mayús+F10 y Aplicaciones (menú contextual).
- Escape en un panel cancela la lectura o el cálculo en curso, o quita el filtro rápido, en ese orden (orden «Cancelar o quitar»).
- Teclado numérico (Num +, Num -, Num *): NVDA y JAWS lo usan en su distribución de escritorio; por eso marcar por patrón, desmarcar e invertir tienen también Ctrl+Mayús+M, Ctrl+Mayús+Q y Ctrl+Mayús+N.
- Insert: es la tecla modificadora de NVDA, JAWS y Narrador; por eso Espacio también marca. Con NVDA, pulsar Insert dos veces seguidas la deja pasar.
- Dos órdenes pueden compartir tecla si sus ámbitos no se solapan (Intro abre en el panel y ejecuta en la línea de órdenes). Lo comprueba `MapaTeclas` y una prueba.

### 6.2 Ámbitos

- **Panel**: solo con el foco en la lista de archivos de un panel (navegación, marcas, portapapeles, lectura de columnas).
- **Global**: con el foco en cualquier control de la ventana principal, incluida la línea de órdenes y las vistas (teclas F, consulta, menús de ventana). En un campo de texto, las teclas de edición (letras, Espacio, Retroceso, Supr, flechas izquierda y derecha, Inicio, Fin, Re Pág, Av Pág, Ctrl+C, X, V, A, Z, Y y sus combinaciones con Mayús y Ctrl) son del campo, salvo las que el ámbito «línea» asigna a la línea de órdenes.
- **Línea de órdenes**: solo con el foco en ella. Intro ejecuta, Ctrl+Intro en consola, Arriba y Abajo historial, Escape vaciar, Tab volver al panel: estas se consultan ANTES de dar las teclas al campo.
- El filtro rápido y las vistas no son ámbitos del mapa de teclas, son reglas de esos controles: en el filtro rápido, Abajo e Intro vuelven a la lista conservando el filtro y Escape lo quita; las vistas Información, Vista rápida y Árbol admiten las órdenes globales y Tab, el resto de teclas son del control, y la Vista rápida atiende además Intro (leer el archivo que no se leyó solo).

### 6.3 Despachador

`VentanaPrincipal` atiende `EVT_CHAR_HOOK`:

1. Convierte el evento en tecla canónica (`app/ui/teclado_eventos.tecla_de_evento`).
2. Si el modo de ayuda de teclado está activo, anuncia qué haría la tecla y no hace nada (Escape sale).
3. Si el foco está en la lista de un panel y la tecla es Espacio o Retroceso con una búsqueda viva (o con la línea de órdenes con texto y la preferencia «teclear va a la línea de órdenes»), se aplica la regla de 5.5. Las letras, dígitos y signos NO se atienden aquí: `EVT_CHAR_HOOK` da la tecla física (sin Mayús, AltGr ni acentos), así que el paso 8 los deja pasar y la lista los recibe ya traducidos en `EVT_CHAR`, donde empiezan o siguen la búsqueda rápida o se escriben en la línea de órdenes (con AltGr, que llega como Ctrl+Alt, también). Las teclas con orden en el mapa (Num +, Num -, Num *, Mayús+Num +, Mayús+Num -) siguen al paso 7.
4. Calcula los ámbitos activos según el foco: lista de un panel, panel y global; vista Información, Vista rápida o Árbol, solo global (y Tab); línea de órdenes, línea y global; otro campo de texto de la ventana, solo global; cualquier otro control, global.
5. Si el foco está en la línea de órdenes y la tecla tiene orden en el ámbito «línea», la ejecuta.
6. Si el foco está en un campo de texto o en un árbol y la tecla es de edición o de movimiento, llama a `evento.DoAllowNextEvent()` y vuelve: el control la recibe y ningún atajo de menú la roba.
7. Si la tecla está en el mapa para un ámbito activo, ejecuta la orden y consume el evento.
8. Si no, `evento.Skip()` (la lista hace lo nativo; su búsqueda por letras propia está desactivada).

Los menús llevan el atajo real tras `\t` (el lector lo anuncia), pero el despachador consume antes esas teclas, así que nunca se ejecutan dos veces. F10 se consume (salir) y no activa la barra de menús; F9 la abre. En los menús Izquierdo y Derecho solo el del lado activo muestra atajos (se actualizan al cambiar de panel), para no anunciar la misma tecla en dos sitios.

### 6.4 Teclas de consulta

Dicen información sin mover el foco y la guardan en el historial de anuncios: ruta del panel activo (Ctrl+Mayús+P) y del otro (Ctrl+Mayús+O), resumen de la carpeta y las marcas (Ctrl+Mayús+S), información del elemento (Ctrl+Mayús+I), espacio libre (Ctrl+Mayús+E), estado de las operaciones y decisiones pendientes (Ctrl+Mayús+T), repetir el último anuncio (Ctrl+Mayús+U; dos veces, la versión completa), historial de anuncios (Ctrl+Mayús+H), leer la columna 1 a 10 de la fila del cursor (Ctrl+1 a Ctrl+0) y la anterior o siguiente (Izquierda y Derecha).

### 6.5 Ayuda para aprender las teclas

- **Paleta de órdenes** (Ctrl+E): campo con etiqueta y lista nativa; al escribir («copiar») se filtran las órdenes por etiqueta y ayuda; Intro ejecuta la elegida y anuncia su atajo («Atajo: F5») para aprenderlo.
- **Modo de ayuda de teclado** (Mayús+F12): cada tecla dice el nombre y la ayuda de su orden sin ejecutarla; se anuncia al entrar y al salir (Escape o Mayús+F12).

## 7. Menús

La barra de menús es nativa y contiene todas las órdenes salvo las de la sección «Órdenes solo de teclado» del anexo, que también están en la paleta. La estructura exacta es `MENUS`, `MENU_LADO` y `MENU_CONTEXTUAL` de `app/ui/ordenes.py`; el anexo la refleja.

- **Izquierdo y Derecho**: vistas, ordenación, filtro, columnas, volver a leer, unidad, pestañas, mostrar u ocultar el lado. Actúan sobre su lado.
- **Archivos**: menú de usuario, ver, editar, copiar, mover, crear carpeta, eliminar; crear archivo, duplicar, renombrar, deshacer; atributos, propiedades; abrir, abrir con, menú de Windows; submenús Marcas y Portapapeles; salir.
- **Comandos**: buscar, historiales, árbol, favoritos, ir a la carpeta; submenú Paneles; comparar, sincronizar, comparar archivos y renombrado múltiple; submenús Herramientas (tamaño, vista plana, sumas, dividir, unir, enlaces), Cesta, Comprimidos y Red; consola, Explorador y operaciones.
- **Opciones**: preferencias, perfil, mapa de teclas, columnas por defecto, menú de usuario, asociaciones, ocultos, asistente, guardar sesión, valores de fábrica, carpetas de datos y registros.
- **Ayuda**: manual, lista de teclas, novedades, ayuda del control, historial de anuncios; paleta de órdenes y modo de ayuda de teclado; información para soporte, acerca de.
- En el menú del lado activo se muestran también las teclas de unidad (Alt+F1 o Alt+F2) y de mostrar u ocultar el lado (Ctrl+F1 o Ctrl+F2).
- **Menú contextual** (Mayús+F10, Aplicaciones o clic derecho): abrir, ver, editar, copiar, mover, renombrar, eliminar, portapapeles, copiar rutas, comprimir, extraer, cesta, propiedades y menú de Windows, con etiquetas propias (`ETIQUETAS_CONTEXTUAL`) para que sus letras no se repitan. Se abre junto al cursor.
- Las letras de acceso no se repiten dentro de cada menú ni con la barra: lo comprueba `tools/comprobar_menus.py` sobre el catálogo (prueba automática) y `revisar_teclado` sobre la barra construida.

## 8. Funciones en detalle

Cada función indica qué hace, sus opciones, qué se anuncia y cómo trata los errores. Todas las operaciones largas usan el gestor de tareas y el motor de operaciones (sección 9.6). Las teclas están en el anexo de órdenes.

### 8.1 Navegar

- Intro en una carpeta entra; en «..» sube y deja el cursor en la carpeta de la que se salió; en un comprimido admitido entra (si la preferencia «Entrar en comprimidos con Intro» está activa; si no, lo abre con su programa); en un archivo aplica su **asociación** (8.17) y, si no hay, lo abre con el programa predeterminado de Windows (`os.startfile`); en un ejecutable lo ejecuta en su carpeta, con la confirmación de la sección 14. Abrir con el programa asociado se hace en un hilo de trabajo para no congelar la interfaz con rutas de red.
- Al entrar en una carpeta se anuncia su nombre (nivel normal) y, con detalle «detallado», el número de elementos. Carpeta vacía: «Carpeta vacía» (nivel resultado). Sin permiso: mensaje «No tiene permiso para abrir X» y el panel se queda donde estaba.
- Listar es asíncrono (estados del panel en 4.7).
- Ir a una carpeta (Ctrl+G): campo con la ruta actual seleccionada y autocompletado; acepta rutas relativas, variables de entorno (`%USERPROFILE%`), `~`, rutas UNC (`\\servidor\recurso`) y direcciones `ftp://` y `sftp://` (abre la conexión). Si la ruta es un archivo, va a su carpeta con el cursor en él.
- Historial por panel (hasta 100 carpetas): Alt+Izquierda y Alt+Derecha; Alt+F12 abre la lista para elegir.
- Favoritos (Ctrl+D): lista con nombre y ruta; Intro va; desde el diálogo se añaden, renombran, ordenan y borran; Ctrl+Mayús+D añade la carpeta actual pidiendo el nombre. Se guardan en `data/config/favoritos.json`.
- Árbol de carpetas (Alt+F10): diálogo con el árbol de la unidad actual (carga bajo demanda), búsqueda tecleando y botones Ir, Crear carpeta, Renombrar y Eliminar.
- Selector de unidades (Alt+F1 y Alt+F2): lista «C:, Disco local, NTFS, 120 GB libres de 476 GB»; incluye unidades de red, extraíbles y ópticas (las vacías como «sin disco») y, debajo, favoritos y carpetas especiales (Escritorio, Documentos, Descargas, carpeta personal). Teclear la letra va a esa unidad. La información de cada unidad se pide en hilos con tiempo límite.
- Cada panel recuerda la última carpeta visitada de cada unidad (al volver a «D:» se va a la carpeta en la que se estaba).

### 8.2 Ver (F3) y visor interno

- Ventana propia (no modal; se pueden abrir varias) con un `wx.TextCtrl` multilínea de solo lectura, que el lector recorre por líneas, palabras y caracteres.
- Modos: texto y hexadecimal (F4 alterna). Codificaciones: detección automática (BOM; UTF-8 válido; UTF-16 sin BOM por el patrón de ceros; si no, Windows-1252) y elección manual (F8 abre la lista: UTF-8, UTF-16 LE y BE, Windows-1252, ISO-8859-1, OEM 850, OEM 437).
- Teclas del visor (propias de su ventana): F2 ajuste de línea, F4 texto o hexadecimal, F8 codificación, F7 o Ctrl+F buscar (distinguir mayúsculas, palabra completa, expresión regular), F3 o Mayús+F7 buscar siguiente, Mayús+F3 anterior, Ctrl+G ir a línea (en hexadecimal, a un desplazamiento), Ctrl+C copiar, Ctrl+A seleccionar todo, Ctrl+Mayús+I decir la barra de estado, Escape o F10 cerrar. Norton salía también con F3; aquí F3 repite la búsqueda como en el resto de Windows. Tamaño de letra desde el menú del visor.
- Archivos grandes: hasta 16 MB (configurable) se cargan enteros en un hilo con aviso «Cargando...»; si son mayores, el visor trabaja por bloques de 1 MB: Ctrl+AvPág y Ctrl+RePág cambian de bloque y la barra de estado dice «Bloque 3 de 120». La búsqueda recorre todos los bloques en un hilo.
- Barra de estado del visor: línea y columna, codificación, modo y tamaño.
- Si el archivo está en un comprimido o en FTP, se extrae primero a `data/temp/extraidos` y se borra al cerrar el visor. Si se abrió con un programa externo (Intro con asociación, visor o editor externos), el temporal se vigila con `temporales.vigilados` (N): cuando la ventana principal recupera el foco y su fecha cambió, se ofrece actualizarlo en el comprimido o el servidor; esos temporales se borran al salir y al arrancar.
- Archivos que solo están en la nube: se pregunta antes de descargarlos.
- F3 abre la asociación del tipo de archivo para «ver» (8.17) o, si no hay, el visor interno. «Ver con el visor externo» abre siempre el programa de `visor.externo` con `%P` como archivo; si está vacío, avisa «No hay visor externo configurado». F4 sigue otra regla: la asociación para «editar»; si no hay, `editor.externo` si `editor.usar_externo` está activo; si no, el editor interno.

### 8.3 Editar (F4) y editor interno

- Ventana propia con `wx.TextCtrl` multilínea editable (estilo `TE_RICH2` para archivos grandes, sin formato).
- Archivo: Guardar (F2 o Ctrl+S), Guardar como (Mayús+F2), Volver a cargar, Cerrar (Escape o F10; si hay cambios pregunta Guardar, No guardar o Cancelar).
- Edición (teclas del editor): deshacer (Ctrl+Z), rehacer (Ctrl+Y), cortar, copiar, pegar, seleccionar todo, buscar (F7 o Ctrl+F), buscar siguiente (F3 o Mayús+F7), reemplazar (Ctrl+R), ir a línea (Ctrl+G), insertar fecha y hora (F5), contar líneas, palabras y caracteres (menú Herramientas del editor).
- Formato del archivo: se conservan la codificación, el fin de línea (CRLF, LF o CR) y el BOM del archivo; se pueden cambiar al guardar como.
- Guardado seguro: escribe a un temporal en la misma carpeta y lo renombra; si el archivo cambió en disco mientras se editaba, avisa antes de sobrescribir. Opción de copia de seguridad `.bak`.
- Editor externo: si `editor.usar_externo` está activo (por defecto, el interno), F4 abre el programa de `editor.externo` (por ejemplo `notepad.exe %P`).
- Mayús+F4: pide un nombre, crea el archivo vacío en la carpeta del panel y lo abre en el editor.
- Archivos en comprimidos: se abren de solo lectura y al guardar se ofrece «Guardar como» en una carpeta local. En FTP se descarga a `data/temp` y al guardar se sube, con confirmación.

### 8.4 Copiar (F5) y mover (F6)

#### Diálogo

- Texto de solo lectura con el resumen: «Copiar 3 archivos y 1 carpeta (45 MB) a:».
- Campo «Destino» con la carpeta del otro panel (si hay un solo elemento, la ruta acaba en su nombre para poder copiar con otro nombre). Si el destino termina en `\` o es una carpeta existente, los elementos van dentro; si no existe y hay un solo elemento, es el nombre nuevo; si no existe y hay varios, se crea la carpeta.
- Campo «Solo los que coinciden con» (patrón, por defecto `*`).
- Desplegable «Si el archivo ya existe»: Preguntar, Sobrescribir, Omitir, Sobrescribir si es más antiguo, Sobrescribir si cambia el tamaño, Renombrar la copia automáticamente, Renombrar el existente automáticamente.
- Casillas: Conservar fechas y atributos (sí), Verificar después de copiar (no), Copiar los enlaces como enlaces (sí), Copiar también las carpetas vacías (sí).
- Botones: Copiar o Mover (predeterminado: Intro copia al momento), En cola (espera a que terminen las demás operaciones puestas en cola), Cancelar. F2 en el diálogo equivale a En cola. El diálogo siempre aparece (como en Norton); el foco empieza en el destino.

#### Motor (sección 9.6)

- Primero analiza (lista todo lo que se copiará, suma bytes y detecta conflictos); después copia. Durante el análisis la barra es indeterminada y se anuncia «Analizando...».
- Copia cada archivo a un temporal corto `~zc<8 hex>.tmp` en la carpeta de destino y lo coloca con su nombre al terminar: nunca queda un archivo a medias con el nombre bueno. Si sustituye a otro, usa `ReplaceFileW` (conserva los permisos del destino); si falla por acceso denegado o porque el sistema de archivos no lo admite, usa `MoveFileExW` con reemplazo y lo deja en el registro. Las fechas y los atributos se aplican después de colocarlo. Si se cancela, el temporal se borra. Los temporales que queden de un cierre brusco no se muestran en los paneles y el análisis de una copia nueva borra los de más de una hora en su destino.
- Archivos locales: `CopyFileExW` con rutina de progreso (cancelar y pausar dentro del archivo; conserva flujos alternativos y atributos). Otros proveedores (comprimidos, FTP): copia por bloques con progreso.
- Mover dentro del mismo volumen: renombrado (`MoveFileExW`), instantáneo. Entre volúmenes: cada origen se borra después de copiar (y verificar, si se pidió) el suyo; si algo falla, ese origen se conserva.
- Copiar una carpeta dentro de sí misma o un elemento sobre sí mismo se rechaza con un mensaje claro antes de empezar.
- Comprueba el espacio libre antes de copiar y avisa si no cabe (Continuar de todos modos, Cancelar), con `Decisor.elegir`.
- Rutas largas: sección 15.
- Las uniones y los enlaces simbólicos a carpetas nunca se recorren al copiar o mover (se recrean como enlace o se omiten, según la casilla).
- Tras la operación, los dos paneles se refrescan y se quitan las marcas de los elementos copiados (se pueden restaurar con Ctrl+Mayús+R).

#### Conflictos

- Con «Preguntar», si el análisis encuentra archivos que ya existen, antes de copiar nada se abre la **lista de conflictos** (`dialogos/conflictos.py`): una fila por conflicto con Nombre relativo, Origen (tamaño y fecha), Acción y Destino (tamaño y fecha); el mismo diseño que la lista de sincronizar (columnas, menú contextual, selección múltiple nativa con Ctrl+Espacio y Mayús+flechas) con sus propias letras: S sobrescribir, O omitir, C renombrar la copia, E renombrar el existente, sobre las filas seleccionadas o la del cursor; cada cambio se anuncia (nivel resultado: «Sobrescribir: 12 filas»); un desplegable para ver solo «destino más reciente»; botones Comparar (abre la comparación de los dos archivos), Aplicar a todos (pone en todas las filas la acción de la fila del cursor), Continuar y Cancelar la operación. Acción inicial de cada fila: Omitir. El botón «Sobrescribir los más antiguos» resuelve de una vez. Cada fila guarda el tamaño y la fecha del destino; si al copiar ya no coinciden, ese archivo pasa a «conflicto tardío».
- Los **conflictos tardíos** (el destino apareció o cambió después del análisis) y los **errores** no paran la copia: se apartan y la operación sigue con lo demás. Al final, si hay conflictos tardíos, se abre de nuevo la lista de conflictos solo con ellos; si hubo errores, la ventana de operaciones ofrece «Reintentar los que fallaron» (lanza una copia nueva solo con ellos). Con `operaciones.lista_conflictos` desactivada, en lugar de la lista se pregunta de uno en uno (pregunta individual: texto de solo lectura con nombre, tamaño y fecha de origen y destino y botones Sobrescribir, Sobrescribir todos, Omitir, Omitir todos, Sobrescribir los más antiguos, Renombrar..., Renombrar todos automáticamente, Comparar y Cancelar la operación; el foco empieza en Omitir y Escape equivale a Omitir).
- El renombrado automático añade « (2)», « (3)»... antes de la extensión.
- Una carpeta que ya existe se fusiona sin preguntar; los archivos de dentro siguen la política de conflictos.
- Archivos de solo lectura, ocultos o de sistema en el destino: se pregunta igual; si se elige sobrescribir, se quita el atributo antes.

#### Errores

- Un error en un archivo (en uso, sin permiso) se anota y la copia sigue (ver conflictos tardíos y errores, arriba). Un error que afecta a todo (disco lleno, unidad desconectada) para la operación con la pregunta Reintentar o Cancelar.
- Al terminar: resumen anunciado y en la ventana de operaciones: «Copia terminada: 400 archivos, 2,1 GB, 2 omitidos, 1 error, 1 min 20 s». Los errores se ven en el detalle de la operación (lista copiable).

### 8.5 Operaciones en curso (F12)

- Ventana no modal con la lista de operaciones (estados de `Estado` en `modelo.py`: En cola, Analizando, Espera su decisión, En marcha, Verificando, En pausa, Terminada, Terminada con errores, Cancelada, Fallida) y, para la elegida: origen, destino, archivo actual, porcentaje del archivo y total, bytes, velocidad y tiempo restante, en un texto de solo lectura que se actualiza como mucho 4 veces por segundo y nunca roba el foco.
- Botones: Atender la decisión pendiente (si la hay), Pausar o Reanudar, Cancelar, Detalles (errores, copiables), Limpiar terminadas.
- Las operaciones lanzadas con el botón principal empiezan enseguida, salvo que otra operación use ya el mismo volumen de origen o de destino (carril, 9.6) o se haya llegado a `operaciones.max_paralelas`; las lanzadas con «En cola» esperan en una única cola y se ejecutan de una en una.
- Progreso por voz según la preferencia: cada 25 % (novato), al empezar y al terminar (intermedio) o solo al terminar (avanzado). Ctrl+Mayús+T lo consulta en cualquier momento. Los errores y las preguntas siempre se anuncian.
- Si una operación espera una decisión, se anuncia «La copia espera su decisión» y se atiende como dice la sección 9.6.
- Al salir con operaciones en marcha se pregunta: Esperar y salir, Cancelar las operaciones y salir, No salir.

### 8.6 Crear carpeta (F7)

- Pide el nombre (se admiten varios niveles: `a\b\c`). Valida nombres reservados y caracteres prohibidos con un mensaje que dice qué falla. Tras crearla, el cursor va a la carpeta nueva y se anuncia «Carpeta creada: nombre». Casilla «Entrar en ella».

### 8.7 Eliminar (F8, Supr, Mayús+F8, Mayús+Supr)

- Confirmación (según preferencias): «¿Enviar a la papelera 3 archivos y 1 carpeta (45 MB)?» con botones Eliminar y Cancelar. En el borrado definitivo el foco empieza en Cancelar.
- A la papelera con Send2Trash (que usa `IFileOperation`) en un hilo con COM en modo STA. Si la unidad no tiene papelera (red, extraíble) o la ruta es larga, se avisa: «Esta unidad no tiene papelera: los archivos se eliminarán definitivamente» (Eliminar definitivamente, Cancelar).
- Definitivo: borrado propio recursivo con progreso; no sigue uniones ni enlaces; con archivos de solo lectura pregunta (Eliminar, Eliminar todos, Omitir, Cancelar).
- Tras eliminar, el cursor queda en el elemento siguiente.

### 8.8 Renombrar en el sitio, duplicar y crear archivo

- Mayús+F6: diálogo con el nombre actual y el nombre sin extensión seleccionado (preferencia: todo o sin extensión). Valida el nombre. Renombrar solo cambiando mayúsculas funciona.
- Mayús+F5: copia en la misma carpeta pidiendo el nombre (propone «nombre (copia).ext»).
- Mayús+F4: ver 8.3.

### 8.9 Atributos y fechas

- Diálogo con casillas Solo lectura, Oculto, Sistema, Archivo y No indexar; con varios elementos cada casilla tiene tres estados (sin cambio, sí, no). Campos de fecha y hora de modificación y de creación (con «Sin cambio» marcado por defecto y botón «Ahora»). Casilla «Aplicar también a las subcarpetas y su contenido». Se aplica en un hilo con resumen.

### 8.10 Propiedades, Abrir con y menú contextual de Windows

- Alt+Intro: diálogo de propiedades de Windows (`SHObjectProperties`; con varios elementos, `SHMultiFileProperties`).
- Abrir con: diálogo «Abrir con» de Windows (`SHOpenWithDialog`).
- Menú contextual de Windows: el del Explorador (`IContextMenu`, `IContextMenu2` y `IContextMenu3` con pywin32 y una ventana auxiliar oculta cuyo procedimiento de ventana reenvía `WM_INITMENUPOPUP`, `WM_DRAWITEM`, `WM_MEASUREITEM` y `WM_MENUCHAR` para que se llenen los submenús «Enviar a» y «Abrir con»), nativo y accesible, junto al cursor. Sus verbos (eliminar, pegar...) los hace el shell: no pasan por el motor ni por deshacer, y el panel se refresca al cerrarlo. Si falla, se avisa y se registra.

### 8.11 Enlaces

- Diálogo: tipo (simbólico, unión de carpeta, enlace duro, acceso directo `.lnk`), destino y nombre del enlace (por defecto en el otro panel). Si crear un simbólico exige privilegios, se explica cómo activar el modo de desarrollador y se ofrece crear una unión (carpetas) o un acceso directo.
- En la lista, el tipo de un enlace dice «Enlace a C:\...» y la información muestra su destino.

### 8.12 Buscar archivos (Alt+F7)

- Página General: Nombres (patrones como en la sección 5, o expresión regular con la casilla), Buscar en (carpeta actual por defecto; varias separadas por `;`; botón Examinar; casilla «En todas las unidades fijas»), Subcarpetas (casilla y profundidad máxima), Texto contenido (con Distinguir mayúsculas, Palabra completa, Expresión regular, Codificación: automática, UTF-8, UTF-16 o ANSI; y casilla «Que NO contenga el texto»).
- Página Avanzado: tamaño mínimo y máximo con unidad, fecha de modificación desde y hasta (o «últimos N días»), incluir ocultos y de sistema, qué buscar (archivos, carpetas o ambos), buscar dentro de comprimidos ZIP y TAR.
- Resultados: lista virtual con Nombre, Carpeta, Tamaño y Fecha; se llena mientras busca sin mover el cursor del lector; el recuento está en la línea de estado del diálogo y al terminar se anuncia «Búsqueda terminada: 120 resultados en 4 s». Buscar dentro de comprimidos y servidores usa el mismo recorrido (`recorrido.py`). No se lee el contenido de archivos que solo están en la nube salvo que se marque «Incluir archivos en la nube».
- Botones: Buscar o Detener (Escape detiene; un segundo Escape cierra), Nueva búsqueda, Ver (F3), Editar (F4), Ir al archivo (Intro en la lista: cierra y lleva el panel activo a su carpeta con el cursor en él), Enviar al panel (abre en el panel activo una lista de resultados, sección 9.3, sobre la que funcionan todas las operaciones) y Guardar resultados en un archivo de texto.
- Búsquedas guardadas: Guardar como... y desplegable con las guardadas.

### 8.13 Comparar y sincronizar carpetas

- Comparar carpetas (Ctrl+F10): pregunta el criterio (nombre; nombre y fecha; nombre, fecha y tamaño; contenido) y marca en cada panel los archivos que no existen en el otro o que son más recientes (como Norton). Anuncia «Diferencias: 5 a la izquierda, 2 a la derecha» o «Las carpetas son iguales».
- Sincronizar carpetas (Ctrl+Mayús+F10): diálogo con las dos carpetas (las de los paneles), dirección (izquierda a derecha, derecha a izquierda, en los dos sentidos), criterio (fecha, tamaño, contenido), subcarpetas, patrón, «ignorar diferencias de fecha de hasta 2 s» (por FAT) y «eliminar en el destino lo que no está en el origen» (solo en un sentido; desactivado por defecto).
	- Botón Comparar: llena una lista con una fila por diferencia: Nombre relativo, Izquierda (tamaño y fecha), Acción, Derecha (tamaño y fecha). La acción se lee como texto: «Copiar a la derecha», «Copiar a la izquierda», «Eliminar a la derecha», «Eliminar a la izquierda», «Nada» o «Conflicto: cambiaron los dos».
	- En la lista (selección múltiple nativa), el menú contextual y las teclas D (copiar a la derecha), I (copiar a la izquierda), N (nada) y B (borrar en el lado de destino según la dirección elegida; en los dos sentidos, borrar donde falta el otro) cambian la acción de las filas seleccionadas o de la del cursor y se anuncia el cambio; la búsqueda por letra nativa de la lista está desactivada para que esas letras no salten de fila; un desplegable filtra por tipo de acción; el botón Comparar contenido abre la comparación de los dos archivos de la fila.
	- Comparar y sincronizar usan el mismo cálculo (`diferencias_carpetas.py`).
	- Botón Sincronizar: ejecuta las acciones como una operación del motor (con progreso, cola y resumen).

### 8.14 Renombrado múltiple (Ctrl+M)

- Campos: Máscara del nombre (por defecto `[N]`), Máscara de la extensión (por defecto `[E]`), Buscar, Reemplazar (varios pares con `|`), casillas Expresión regular, Distinguir mayúsculas, Solo la primera coincidencia y Aplicar también a la extensión; Mayúsculas del nombre y de la extensión (Sin cambio, minúsculas, MAYÚSCULAS, Primera letra, Cada Palabra); Contador: inicio, paso y dígitos.
- Máscaras (compatibles con Total Commander):
	- `[N]` nombre sin extensión; `[N1]` el primer carácter; `[N2-5]` del 2 al 5; `[N2,5]` cinco caracteres desde el 2; `[N-3,3]` tres caracteres desde el antepenúltimo; `[N3-]` desde el 3 hasta el final.
	- `[E]` extensión, con los mismos tramos.
	- `[P]` carpeta que contiene el archivo; `[G]` la carpeta de encima de esa.
	- `[C]` contador con los valores de los campos; `[C10+5:3]` inicio 10, paso 5, 3 dígitos.
	- `[Y]` año de cuatro cifras, `[y]` de dos, `[M]` mes, `[D]` día, `[h]` hora, `[m]` minutos, `[s]` segundos (de la fecha de modificación); `[d]` fecha `AAAA-MM-DD`; `[t]` hora `hh.mm.ss`.
	- `[U]`, `[L]`, `[F]`, `[n]`: lo que sigue en mayúsculas, en minúsculas, con la primera letra de cada palabra en mayúscula, o sin cambio.
	- `[[` y `]]` escriben corchetes literales.
- Orden de aplicación: máscaras, después buscar y reemplazar, después mayúsculas.
- Vista previa en lista: Nombre actual, Nombre nuevo y Estado («Sin cambios», «Duplicado», «Nombre no válido: carácter :», «Correcto»). Se actualiza al escribir tras 300 ms sin teclear.
- Renombrar: se rechaza si hay duplicados o nombres no válidos (el foco va a la primera fila mala). Las cadenas (a pasa a b y b pasa a c) se resuelven con nombres temporales. El lote se registra para deshacer (8.23).
- Plantillas: guardar, cargar y borrar combinaciones de máscaras.

### 8.15 Comprimidos

- Navegar: Intro (o Ctrl+AvPág) en un `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz` o `.7z` lo abre como carpeta (ruta mostrada `C:\datos\copia.zip\carpeta`). Se puede ver (F3), copiar al otro panel (extraer), buscar y comparar. Retroceso en la raíz del comprimido vuelve a la carpeta que lo contiene.
- Escribir dentro (copiar al comprimido, eliminar, crear carpeta) se admite en ZIP en una transacción: se acumulan los cambios y se reconstruye el archivo una sola vez al terminar la operación (se avisa la primera vez de que en comprimidos grandes es lento). TAR y 7z son de solo lectura como carpeta; para añadir a ellos se usa Comprimir.
- Nombres en ZIP sin la marca UTF-8 (los del Explorador antiguo): se leen como cp850.
- Ver un archivo de un 7z sólido obliga a descomprimir su bloque: se avisa con «Descomprimiendo...» y progreso. El índice del comprimido se guarda mientras el panel está dentro.
- Comprimir (Alt+F5): nombre del archivo (por defecto en el otro panel, con el nombre de la carpeta o del elemento), formato (ZIP, 7z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ), nivel (sin compresión, rápido, normal, máximo), contraseña (solo 7z, con AES; `zipfile` no cifra), «un comprimido por cada elemento» y «mover al comprimido» (borra los originales tras terminar y probar el comprimido).
- Extraer: destino (otro panel), «cada comprimido en su propia carpeta», política de conflictos (como en copiar), patrón de archivos, contraseña si hace falta. Extraer es copiar desde el proveedor del comprimido con el motor de copia (lista de conflictos incluida). Extracción segura: el proveedor rechaza toda entrada con ruta absoluta, unidad o `..`; TAR usa `filter='data'`; los archivos extraídos heredan la marca de la Web del comprimido (sección 14).
- Probar (Alt+Mayús+F9): lee todo el comprimido verificando CRC y da un resumen.
- RAR no se admite (no hay biblioteca libre fiable): Intro lo abre con el programa asociado.

### 8.16 FTP, FTPS y SFTP

- Gestor de conexiones (Ctrl+K): lista de sitios con Conectar, Nuevo, Editar, Duplicar y Eliminar. Cada sitio: nombre, protocolo (FTP, FTP con TLS explícito, SFTP), servidor, puerto, usuario (vacío = anónimo), contraseña (cifrada con DPAPI en `data/config/secretos.dat`, o «preguntar cada vez»), carpeta remota inicial, modo pasivo, codificación de los nombres (UTF-8 o Latin-1), tiempo de espera (30 s) y clave privada (SFTP).
- Conexión rápida: escribir `ftp://usuario@servidor/carpeta` o `sftp://...` en Ir a la carpeta (Ctrl+G).
- Al conectar, el panel activo muestra la carpeta remota y su etiqueta dice «Izquierdo: ftp://servidor/carpeta». Se puede listar, entrar, ver, editar, copiar en los dos sentidos (con el motor y sus conflictos), mover, renombrar, eliminar, crear carpeta y, en SFTP, cambiar permisos (campo octal).
- Cada conexión usa su propio objeto `ftplib` o `paramiko` protegido por un candado (no son seguros entre hilos); las transferencias abren una conexión aparte para no bloquear la navegación.
- Certificados (FTPS) y claves de servidor (SFTP): la primera vez se muestra la huella y se pregunta Aceptar y recordar, Aceptar solo esta vez o Cancelar; FTPS en `data/config/hosts_conocidos.json` y SFTP en `data/config/known_hosts` (formato OpenSSH con `paramiko.HostKeys`). Si la huella cambia, se avisa claramente y se pide confirmación.
- FTP sin TLS: aviso la primera vez por sitio de que la contraseña viaja en claro.
- Las descargas reciben la marca de la Web.
- Desconectar desde Comandos, o yendo a una unidad local. Al salir se cierran todas.
- Errores de red con mensajes claros: «El servidor no responde», «Usuario o contraseña incorrectos», «Se perdió la conexión; se reintenta una vez».

### 8.17 Línea de órdenes, menú de usuario y asociaciones

- **Línea de órdenes**: ejecuta en la carpeta del panel activo (si es local) con `cwd=`. `cd ruta`, `cd ..`, `cd \` y `X:` cambian la carpeta del panel sin lanzar un proceso. El resto se ejecuta con `cmd /c` en un hilo; su salida (estándar y de error, decodificada con la página de códigos OEM de la consola, o UTF-8 si la orden empieza por `chcp 65001`) se añade a la zona de salida de las órdenes (sección 4.1), que se ve con «Mostrar u ocultar los paneles»; al terminar se anuncia «Orden terminada, código 0» y se refrescan los paneles. Botón Detener (termina el proceso y sus hijos). Ctrl+Intro en la línea de órdenes, o la preferencia «Ejecutar siempre en consola», la ejecuta en una consola nueva que queda abierta (`cmd /k`), necesario para programas interactivos. Historial de 200 órdenes guardado en la sesión; Alt+F8 abre la lista con búsqueda.
- **Menú de usuario** (F2): lista de entradas con su tecla rápida («A: Comprimir con 7-Zip»); Intro o la tecla ejecuta. Cada entrada tiene etiqueta, tecla, una o varias órdenes y opciones (ejecutar en consola, refrescar paneles al terminar). Admite submenús. Si existe `zcommander.menu.json` en la carpeta actual y la persona confía en esa carpeta (sección 14), sus entradas aparecen primero (como el NC.MNU local de Norton). Editor en Opciones. Formato en la sección 10.
- **Variables** (valen en el menú de usuario, las asociaciones y los programas externos; una sola sintaxis):
	- `%N` nombre con extensión, `%B` nombre sin extensión, `%E` extensión, `%P` ruta completa del cursor, `%D` carpeta del panel activo, `%O` carpeta del otro panel, `%T` ruta completa del cursor del otro panel, `%M` rutas de los elementos de trabajo, `%L` ruta de un archivo temporal con los elementos de trabajo (una ruta por línea, UTF-8), `%?Título?valor%` pide un dato en un diálogo, `%%` signo «%».
	- Cómo se pasan a `cmd` sin riesgo de inyección: sección 14.
- **Asociaciones**: reglas en orden «patrón → orden para Abrir (Intro), Ver (F3), Editar (F4)»; la primera que coincide gana; campo vacío = comportamiento por defecto. Editor en Opciones con Subir, Bajar, Nueva, Editar y Eliminar.

### 8.18 Portapapeles y arrastrar y soltar

- Copiar y cortar al portapapeles ponen los archivos (formato del Explorador con «Preferred DropEffect» copiar o mover) y anuncian «3 elementos copiados al portapapeles». Pegar los lleva a la carpeta del panel activo con el motor (copiar o mover según el efecto), también lo copiado en el Explorador. Si `general.pegar_ruta_del_portapapeles` está activo y el portapapeles tiene una ruta de texto, Pegar va a esa ruta.
- Ctrl+Mayús+C copia las rutas completas como texto; «Copiar nombres» y «Copiar la ruta de la carpeta», desde el menú.
- Arrastrar desde un panel al otro o al Explorador copia (con Mayús, mueve). Soltar desde el Explorador en un panel copia a su carpeta (con Mayús, mueve), con el motor y su diálogo de conflictos.

### 8.19 Sumas de comprobación, dividir, unir y comparar archivos

- Crear sumas: algoritmo (CRC32 en formato SFV, MD5, SHA-1, SHA-256, SHA-512, BLAKE2b), un archivo de sumas por archivo o uno para todos (`.sha256` con líneas `hash *nombre`, compatible con `sha256sum`) y dónde guardarlo. Con un solo archivo, opción «Copiar la suma al portapapeles y anunciarla».
- Verificar: con el archivo de sumas del cursor (o eligiéndolo) muestra una lista Nombre y Resultado («Correcto», «Distinto», «No encontrado», «Error de lectura») y anuncia el resumen.
- Dividir: tamaño de cada parte (1,44 MB, 100 MB, 650 MB, 700 MB, 4095 MB, 4,7 GB o personalizado con unidad) y carpeta de destino; crea `nombre.001`, `.002`... y `nombre.crc` con el nombre original, el tamaño y el CRC32.
- Unir: desde `nombre.001` junta las partes en orden, comprueba con el `.crc` si existe y pide el destino.
- Comparar archivos por contenido: dos archivos (el del cursor de cada panel, o los dos marcados de un panel). Si son texto, informe de diferencias por líneas (`difflib`) en una ventana accesible con una lista de diferencias («Línea 12: cambiada») y, para la elegida, las dos versiones en textos de solo lectura; botones Siguiente y Anterior. Si son binarios: «Iguales» o «Distintos a partir del byte 4096». Programa externo de diferencias opcional.

### 8.20 Tamaño de carpetas

- Calcula en un hilo el tamaño de las carpetas de trabajo o de todas las del panel; el resultado aparece en la columna Tamaño y se anuncia («Documentos: 1,2 GB, 3400 archivos, 210 carpetas»). No sigue uniones ni enlaces ni descarga archivos de la nube. Escape cancela. Los tamaños se olvidan al salir de la carpeta.

### 8.21 Filtros y vista plana

- Filtro (Ctrl+F12): patrón de lo que se muestra (`*.mp3;*.flac`), con exclusiones; casilla «aplicar también a carpetas». El filtro activo se dice en la etiqueta del panel («Izquierdo: D:\Música, filtro *.mp3») y en el resumen.
- Filtro rápido (Ctrl+F): campo con etiqueta que aparece sobre la lista; al escribir, la lista se queda con lo que contiene el texto (sin distinguir mayúsculas ni acentos); Intro o Abajo vuelven a la lista conservando el filtro; Escape lo quita.
- Vista plana (Ctrl+B): todos los archivos de la carpeta y sus subcarpetas en una lista con la columna Ruta; se pueden marcar y operar. Se calcula en un hilo; Escape cancela.

### 8.22 Unidades de red y consola

- Conectar unidad de red: diálogo de Windows (`WNetConnectionDialog`); desconectar: `WNetDisconnectDialog`.
- Rutas UNC: se navega por `\\servidor\recurso`; `\\servidor` lista sus recursos compartidos (`NetShareEnum` con pywin32).
- Abrir consola aquí (F11): `cmd.exe`, PowerShell o Windows Terminal (preferencia) en la carpeta del panel activo.

### 8.23 Deshacer (Ctrl+Z)

- Admiten deshacer: renombrar (individual y múltiple), mover, crear carpeta (si sigue vacía) y copiar (envía a la papelera las copias que no han cambiado desde entonces). No se deshace eliminar (para eso está la papelera de Windows) ni nada en FTP o comprimidos.
- Deshacer dice qué se deshará («Deshacer: renombrar 12 archivos en D:\Fotos») y pide confirmación. Se recuerdan las 20 últimas acciones de la sesión, solo en memoria.

### 8.25 Cesta

- Añadir a la cesta guarda los elementos de trabajo (rutas locales absolutas) en una lista de la sesión y anuncia «3 añadidos; la cesta tiene 12». Abrir la cesta la muestra en el panel activo como lista de resultados (columna Ruta), sobre la que funcionan todas las operaciones. Vaciar la cesta pide confirmación. Al operar, las rutas que ya no existen se omiten y se anuncian.

### 8.26 Preferencias, perfiles, mapa de teclas, columnas y temas

- **Preferencias** (Ctrl+coma): diálogo declarativo (`Pagina` y `Opcion`) con una página por sección: General, Paneles, Vista, Accesibilidad, Operaciones, Visor y editor, Búsqueda, Red. Aceptar, Cancelar, Aplicar y Valores de fábrica de la página. Los cambios se aplican al momento en las ventanas abiertas (suscripciones). Las listas (columnas) y diccionarios (teclas) tienen sus diálogos propios.
- **Perfil**: lista de perfiles con su descripción; muestra el actual (o «Personalizado»); Aplicar pide confirmación y dice cuántas preferencias cambiarán.
- **Mapa de teclas**: lista de órdenes (Orden, Teclas, Ámbito) con búsqueda; Cambiar abre un campo que captura la siguiente tecla pulsada y avisa de choques («Ctrl+R ya es Volver a leer: ¿quitársela?»), Quitar, Restablecer esta y Restablecer todas. Las fijas no se pueden cambiar. Se guarda en `teclado.personalizadas`.
- **Columnas**: lista con casillas de las columnas, Subir y Bajar, y ancho; por lado o por defecto.
- **Temas**: Sistema (colores de Windows, por defecto), Norton clásico (fondo azul, texto cian, marcados en amarillo, cursor en fondo cian; comprobado que el cursor sobre una fila marcada se distingue) y Alto contraste (los del sistema en ese modo). Tamaño y tipo de letra para listas, visor y editor.

### 8.27 Asistente de primer arranque y sesión

- **Asistente** (primer arranque o desde Opciones): páginas con Atrás, Siguiente y Terminar: qué es un gestor de doble panel (dos frases), perfil, si se usa lector de pantalla (activa los anuncios y la salida automática), tema; al terminar ofrece abrir el manual.
- **Sesión** (`data/config/sesion.json`): carpetas, pestañas, vistas, orden, filtros y columnas de cada lado, lado activo, historial de carpetas, historial de órdenes y cesta. Se guarda al salir, con «Guardar la sesión ahora» y cada 5 minutos si cambió. Al restaurar, una carpeta que ya no existe se sustituye por la primera superior que exista; un panel de FTP o de comprimido se restaura en la carpeta local que lo contenía.
- Si `accesibilidad.consejos` está activo, al arrancar se anuncia «Panel izquierdo. Tab cambia de panel, F1 abre la ayuda». El asistente propone el perfil Intermedio.
- Argumentos de línea de órdenes: una ruta de carpeta abre el panel izquierdo en ella; una de archivo, su carpeta con el cursor en él. Si zCommander ya está abierto, la segunda instancia le pasa la ruta y se cierra (instancia única de la plantilla).

## 9. Arquitectura

### 9.1 Capas

1. `app/core`: infraestructura (rutas, versión, configuración, almacén JSON, registro, tareas, instancia única, secretos, documentación).
2. `app/services`: lógica de archivos sin wx, probada sin ventanas.
3. `app/ui`: ventanas, diálogos y controles; llama a servicios, tareas y operaciones.

Regla: `ui` → `services` → `core`; `services` no importa `ui` ni `wx` (lo comprueba `tests/test_capas.py` con `ast`).

### 9.2 Punto de partida: el esqueleto

El esqueleto generado con las plantillas se adapta así antes de empezar el núcleo:

- **Eliminar**: `app/core/config.py` (sustituido por `configuracion.py`), `app/core/voz.py` (sustituido por `ui/accesibilidad/voz.py`), `app/ui/dialogo_opciones.py` (sustituido por `dialogo_preferencias.py`), `app/ui/bandeja.py` (bandeja fuera de alcance), `app/ui/dialogo_error.py` (depende de un registro que no tenemos) y las pruebas del esqueleto que los usan (`test_config.py`, `test_ventana.py`, `test_dialogos.py`).
- **Reescribir**: `app/ui/ventana_principal.py`.
- **Adaptar**: `main.py` (configuración nueva, voz de accesibilidad con `uia.fijar_ventana` al crear la ventana, conciencia de DPI, `unidades.evitar_errores_criticos()`, limpieza de `data/temp/extraidos`, rutas de los argumentos convertidas en absolutas antes de pasarlas a la otra instancia, mensajes con `accesibilidad.dialogos`, sin bandeja ni `general.anunciar_arranque`; guarda la ruta del registro de la sesión para «Información para soporte»), `tests/conftest.py` (silenciar `ui/accesibilidad/voz` y `ui/anuncios`), `tests/test_configuracion.py` y `tests/test_dialogo_preferencias.py` (claves de zCommander), `app/ui/dialogo_texto.py` (sin `core.voz`), `app/core/registro.py` (filtro que redacta `usuario:clave@` y contraseñas, con prueba), `app/ui/accesibilidad/revision_teclado.py` (parámetro `permitidas` para las teclas propias de la ventana principal: F10, Insert, Ctrl+Tab, Ctrl+número; nombres de Num +, Num -, Num *, Aplicaciones y Supr), `data/docs/novedades.md` se renombra a `changelog.md` (el nombre que usa el visor de ayuda), `app/core/configuracion.py` (valores de zCommander, esquema 1 sin migraciones de ejemplo, ya hecho), `app/core/secretos.py` (entropía propia), `setup_cx.py` (paquetes y manifiesto), `requirements*.txt` (versiones fijadas), `app/ui/accesibilidad/dialogos.py` (`elegir_opcion` con botón predeterminado y de Escape), `tools/comprobar_teclas.py` (leer el catálogo), `app/ui/accesibilidad/voz.py` (salida UIA y sin SAPI por defecto, ya hecho).
- **Conservar**: el resto de plantillas (`paths.py`, `registro.py`, `instancia_unica.py`, `tareas.py`, `medicion_arranque.py`, `secretos.py`, `documentacion.py`, `visor_ayuda.py`, `acerca_de.py`, `dialogo_texto.py` solo por `copiar_al_portapapeles`, `dialogo_preferencias.py`, `ui/accesibilidad/*`, `tools/*`).
- Mensajes: un único módulo, `app/ui/accesibilidad/dialogos.py`.

### 9.3 Módulos

Cada línea: módulo y responsabilidad. Entre paréntesis, el bloque dueño (N núcleo; A a H, sección 20).

- `main.py`: arranque (N).
- `app/core/`:
	- `paths.py`, `version.py`, `registro.py`, `instancia_unica.py`, `tareas.py`, `medicion_arranque.py`, `secretos.py`, `documentacion.py`: plantillas (N).
	- `configuracion.py`: preferencias (N). `descripciones_config.py`: etiqueta, ayuda y página de cada clave (N). `almacen_json.py`: lectura tolerante y escritura atómica de los JSON auxiliares (N).
- `app/services/`:
	- `formato.py`, `seleccion.py`, `ordenacion.py`, `errores.py`, `teclas.py`, `perfiles.py`, `sesion.py`, `historial.py`, `recorrido.py`, `codificacion.py`, `variables.py`, `linea_ordenes.py`, `cesta.py` (N); `busqueda.py`, `diferencias_carpetas.py`, `tamano_carpetas.py` (B); `comprimir.py`, `sumas.py`, `dividir.py` (C); `conexiones.py` (D); `renombrado.py` (E); `menu_usuario.py`, `asociaciones.py`, `favoritos.py` (F); `comparar_archivos.py` (A).
	- `vfs/`: `base.py`, `rutas.py`, `local.py`, `resolver.py`, `temporales.py`, `resultados.py` (N); `zip.py`, `tar.py`, `siete_z.py` (C); `ftp.py`, `sftp.py` (D); `registro_proveedores.py`, que importa los de C y D para registrarlos (N crea el archivo con importaciones protegidas; C y D no lo tocan).
	- `windows/`: `atributos.py`, `unidades.py`, `copia_nativa.py`, `papelera.py`, `shell_basico.py` (abrir con el programa asociado en un hilo, Explorador, consola), `marca_web.py` (N); `enlaces.py` (E); `red.py` (D); `menu_contextual.py`, `portapapeles.py`, `iconos.py` (G).
	- `operaciones/`: `modelo.py`, `gestor.py`, `copiar.py`, `eliminar.py`, `renombrar.py`, `deshacer.py`, `nombres.py` (N); `atributos.py` (E); `comprimir.py` (C); `sincronizar.py` (B). Crear carpeta es una tarea corta del panel, no una operación.
- `app/ui/`:
	- `ventana_principal.py`, `ordenes.py`, `contexto.py`, `teclado_eventos.py`, `anuncios.py`, `lado_paneles.py`, `panel_archivos.py`, `lista_archivos.py`, `vistas.py`, `arbol_carpetas.py`, `linea_ordenes.py`, `barra_teclas.py`, `salida_ordenes.py`, `tema.py`, `decisiones.py` (cola única de decisiones) (N).
	- `acciones/`: un módulo por dueño, para que nadie toque el de otro: `navegacion.py`, `vista.py`, `archivos.py`, `marcas.py`, `linea.py`, `consulta.py`, `ayuda.py` (N); `visor.py` (A); `busqueda_b.py` (B); `comprimidos_c.py` (C); `red_d.py` (D); `edicion_e.py` (E); `dialogos_f.py` (F); `windows_g.py` (G). El núcleo crea los de los bloques con funciones provisionales que anuncian «Todavía no disponible»; cada bloque sustituye solo el suyo.
	- `dialogos/`: un módulo por diálogo, con prefijo del bloque cuando no es del núcleo (`dialogos/copiar.py`, `dialogos/conflictos.py`, `dialogos/b_buscar.py`, `dialogos/f_favoritos.py`...).
	- `ventanas/`: `operaciones.py` (N); `visor.py`, `editor.py`, `diferencias.py` (A).
	- `accesibilidad/`: plantillas del agente de accesibilidad más `uia.py` (N).
- `tools/`: `generar_anexos.py`, `comprobar_menus.py` (letras de acceso del catálogo), `comprobar_teclas.py`, `revision_egm.py`, `notas_version.py` (N).
- `tests/servicios/`, `tests/ui/`: un archivo por módulo, con prefijo del bloque en las de los bloques.

### 9.4 Sistema de archivos virtual

Fuente: `app/services/vfs/base.py` (clase `Proveedor`, `Entrada`, `Capacidades`, `Ubicacion` y errores) y `resolver.py`.

- Rutas: en local, rutas de Windows; dentro de comprimidos, rutas internas con `/` y la raíz es la cadena vacía; en FTP y SFTP, rutas remotas con `/` y la raíz es `/`. Fuera del proveedor las rutas son texto opaco y se combinan con `unir`, `padre`, `raiz` y `nombre`.
- La fila «..» no la da el proveedor: la añade el panel (`entrada_superior`).
- Cancelación: los métodos largos aceptan un objeto con `is_set()` (`TokenCancelacion`, `threading.Event` o `Cancelacion`) y lanzan `Cancelado`. Las tareas de `GestorTareas` convierten `Cancelado` en su propia cancelación.
- Errores: cada método lanza solo subclases de `ErrorArchivos` con mensaje en español (`errores.convertir` traduce los `OSError`).
- Hilos: `ProveedorLocal` es seguro entre hilos; los remotos protegen su conexión con un candado y `clonar()` da otra conexión para transferencias.
- Escrituras agrupadas: las operaciones del núcleo (copiar, mover, eliminar, renombrar) envuelven todo su `ejecutar` en `with proveedor.transaccion():` (destino y, al mover, también origen). En un ZIP, dentro de la transacción `info`, `existe` y `listar` muestran los cambios pendientes; al salir sin error se reconstruye el comprimido una sola vez; si se cancela o falla, se descarta lo pendiente y no se escribe nada (el resumen lo dice). Se puede anidar (cuenta la más externa).
- Conexiones propias: las operaciones usan `p = proveedor.clonar()` al empezar y lo cierran al terminar si es distinto del del panel; así una descarga larga no bloquea la navegación y desconectar el panel no corta la copia.
- `abrir_ruta` puede leer el disco o el comprimido: se llama siempre desde un hilo de trabajo (nunca desde el de la interfaz); los proveedores de C cargan su índice de forma perezosa en cualquier método.
- Registro de proveedores: `resolver.registrar_comprimido(extensiones, fabrica)` y `resolver.registrar_esquema(prefijo, fabrica)`; cada módulo de C y D se registra al importarse, y `registro_proveedores.py` solo los importa. Las fábricas no hacen E/S: devuelven un proveedor sin conectar; la conexión ocurre en el primer `listar()`, en el hilo de listado. `abrir_ruta(texto, actual=None) -> (proveedor, carpeta, nombre_para_el_cursor)` y `abrir_comprimido(contenedor, ruta)`; quien llama decide si entra en un comprimido (preferencia `paneles.entrar_en_comprimidos`).
- `Entrada.en_nube` marca los archivos de OneDrive no descargados; `Entrada.es_enlace` solo es verdadero en enlaces simbólicos y uniones (no en los puntos de análisis de la nube), y `Entrada.permisos` lleva los permisos Unix de SFTP (`Proveedor.fijar_permisos`).
- `Cancelado` hereda también de `TareaCancelada`: el gestor de tareas lo trata como cancelación.
- Servicios para los proveedores: `resolver.fijar_servicios(decisor, secretos, config)` lo llama `main.py`; un proveedor que necesita preguntar (huella o contraseña de un servidor, contraseña de un 7z) usa `resolver.servicios().decisor` desde su hilo y `servicios().secretos` para las contraseñas guardadas. Los proveedores remotos exponen `servidor` («servidor:puerto»), que usa `clave_carril`.
- Comprimidos: el proveedor valida cada nombre (sin rutas absolutas, unidades ni `..`) y es el único sitio donde se hace; extraer es copiar desde él.

### 9.5 Órdenes, contexto y mapa de teclas

- Catálogo: `app/ui/ordenes.py` (`Orden`, `CATALOGO`, `MENUS`, `MENU_LADO`, `MENU_CONTEXTUAL`, `BARRA_TECLAS`, `SOLO_TECLA`).
- Contexto: `app/ui/contexto.py` (`ContextoOrden` y `PanelProtocolo`). Un manejador recibe el contexto, usa `ctx.objetivo` (el panel del lado del menú o el activo), `ctx.activo` y `ctx.pasivo`, `ctx.config`, `ctx.tareas`, `ctx.lanzar(operacion, en_cola, al_terminar)`, `ctx.anunciar(texto, nivel, completo, interrumpir)`, `ctx.ejecutar_orden(id)`, `ctx.modo_ayuda_teclado` y `ctx.servicio(nombre)` («sesion», «cesta», «deshacer», «secretos», «decisiones», «salida»). Las funciones `estado` de las órdenes casilla reciben el contexto y devuelven `bool`.
- El panel ofrece además (protocolo): `es_lista()`, `cerrar_lista()`, `vincular_tarea(tarea, descripcion)` (Escape la cancela), `historial()`, `ir_historial(ruta)`, `ultima_carpeta(unidad)`, `columnas` y `aplicar_columnas(columnas, anchos)` (por pestaña, como se guardan en la sesión), y `lista()` con los puntos de enganche de G: `fijar_iconos(funcion, imagenes)`, `al_empezar_arrastre(funcion)` y `fijar_destino_soltar(objeto)`. El bloque G instala lo suyo con `windows_g.instalar(ventana)`, que la ventana llama al arrancar.
- Más servicios de la ventana: `ctx.mapa_teclas` (el `MapaTeclas` vigente, solo lectura; la ventana se suscribe a `teclado.` y reconstruye despachador, menús y barra de teclas cuando F guarda `teclado.personalizadas`); `ctx.servicio("linea")` con `historial() -> list[str]`, `poner(texto)` y `ejecutar(expansion, consola=False, refrescar=True)` (usa `linea_cmd`, pasa el entorno de la expansión y escribe en la salida); `ctx.servicio("salida")` con `escribir(texto)` y `mostrar()`.
- `ArbolCarpetas(padre, nombre, proveedor, raiz, al_elegir: Callable[[str], None])` (`app/ui/arbol_carpetas.py`, N): árbol cargado bajo demanda con búsqueda tecleando; métodos `ir_a(ruta)`, `ruta_elegida()`, `refrescar(ruta)`; F lo usa en el diálogo del árbol añadiendo sus botones.
- Enganches de G con tipos: `fijar_iconos(indice_de: Callable[[Entrada], int | None], imagenes: wx.ImageList)`, `al_empezar_arrastre(funcion: Callable[[list[Entrada]], None])`, `fijar_destino_soltar(objeto: wx.DropTarget)`, todos en el hilo de la interfaz. La ventana llama a `windows_g.instalar(ventana)` al arrancar y a `windows_g.instalar_panel(panel)` por cada panel que crea (también pestañas nuevas y restauradas).
- Stubs con firma fija que deja el núcleo para que los bloques trabajen en paralelo: `app/ui/ventanas/diferencias.abrir(padre, (proveedor, ruta), (proveedor, ruta))` (lo rellena A); `app/services/asociaciones.orden_para(nombre, accion)` (lo implementa ya el núcleo; F hace el editor); `app/services/windows/marca_web.leer(ruta)` y `escribir(ruta, contenido)` (núcleo: `OperacionCopiar` la calcula sola si `opciones.marca_web` es `None`: «Internet» si el origen es ftp o sftp, la del comprimido si viene de uno marcado); `app/ui/acciones/archivos.ofrecer_actualizar_desde(ventana)` (núcleo: el `al_cambiar` de los temporales vigilados, que pregunta y sube con `OperacionCopiar` y política Sobrescribir; A lo usa para visor y editor externos).
- `app/services/windows/iconos.py` (G) ofrece `descripcion_tipo(nombre_o_extension) -> str | None` (descripción de Windows del tipo, para la columna Tipo y la vista Información).
- Mapa de teclas: `app/services/teclas.py` (`normalizar`, `nombre_visible`, `MapaTeclas` con ámbitos, fijas y choques).

### 9.6 Motor de operaciones

Fuente: `app/services/operaciones/modelo.py`.

- `Operacion` (clase base con estado, progreso, errores y deshacer), `Estado` y la tabla de transiciones, `Politica`, `AccionConflicto` y `RespuestaConflicto`, `AccionError`, `Conflicto`, `PreguntaError`, `Progreso`, `ContextoEjecucion` (cancelación y pausa) y el protocolo `Decisor`.
- **GestorOperaciones** (`gestor.py`): capa de modelo sobre `GestorTareas`. Cada operación declara sus **carriles** (`clave_carril(proveedor, ruta)` del origen y del destino: raíz de la unidad, recurso UNC, servidor o archivo comprimido); arranca en orden de llegada cuando ninguno de sus carriles está ocupado, hasta `operaciones.max_paralelas` a la vez (se aplica al reiniciar). «En cola» añade un carril compartido: esas van de una en una y además respetan los de volumen. Las operaciones de metadatos (crear carpeta, renombrar) no declaran carriles y no esperan. `lanzar(operacion, en_cola=False, al_terminar=None)`, `operaciones()`, `cancelar(op)`, `cancelar_todas()`, `esperar(segundos)` («Esperar y salir»), `apagar(espera)`. La ventana se suscribe: al terminar cada operación anuncia `resumen()` (esencial) y refresca los paneles que muestran `rutas_afectadas()`. La interfaz consulta el progreso con un temporizador (4 veces por segundo como mucho). Limitación conocida: dos letras del mismo disco físico cuentan como carriles distintos.
- **Suboperaciones**: una operación que usa otra (sincronizar copia y borra; mover al comprimido comprime, prueba y borra) la ejecuta en su mismo hilo con `self.ejecutar_sub(sub, ctx)`, nunca con `lanzar` (se bloquearía con sus propios carriles; `lanzar` desde un hilo de operación da error). `ejecutar_sub` pone `sub.padre`, suma el progreso de la sub al del padre mientras dura, y al terminar pasa al padre sus errores, `fallidos` y pasos de deshacer; las preguntas se hacen en nombre de `operacion.raiz()`. Sincronizar crea una `OperacionCopiar` por carpeta de destino con política Sobrescribir (las acciones ya se decidieron en la lista) y una `OperacionEliminar` para los borrados.
- **Destinos repetidos**: si dos elementos de la misma operación van al mismo destino (cesta, vista plana), el segundo se renombra («nombre (2).ext») y la operación nunca sobrescribe lo que ella misma ha creado.
- **Sustitución segura**: `ReplaceFileW` con archivo de respaldo; si falla a medias, se recupera el original o se coloca la copia desde el respaldo; si el nombre de destino ha quedado libre, el temporal se coloca en lugar de borrarse; en proveedores no locales, el destino se aparta como respaldo antes de colocar la copia y se devuelve si algo falla; el solo lectura del destino se quita antes de sustituir. Un enlace omitido no se borra del origen al mover.
- **Renombrar** (`operaciones/renombrar.py`, núcleo): `OperacionRenombrar(proveedor, pares: list[tuple[str, str]], descripcion="")` resuelve cadenas y ciclos con temporales, deja los pasos de deshacer y declara su carril. E solo calcula los pares y hace el diálogo. «Reintentar los que fallaron» lanza desde la interfaz una operación nueva.
- **Carriles de comprimidos y listas**: en un comprimido, el carril es el propio archivo comprimido más el volumen que lo contiene (`claves_carril`); en listas de resultados y la cesta, el conjunto de las raíces de todas las entradas. Las operaciones de metadatos solo van sin carril en disco local; en comprimidos y servidores declaran el carril de su contenedor.
- **Pausa sin carreras**: la interfaz solo pide pausar o reanudar; el hilo de la operación aplica la pausa en `ctx.comprobar()` y vuelve al estado que tenía. Las esperas de decisiones van en `with ctx.esperando():`. El tiempo en pausa o esperando no cuenta para la velocidad.
- **Decisiones** (`ui/decisiones.py`): implementa `Decisor` (`resolver_conflictos`, `preguntar_conflicto`, `preguntar_error`, `elegir`, `pedir_texto`) con una única cola en la interfaz; es también `ctx.servicio("decisiones")` para preguntas desde hilos fuera de operaciones (contraseña o huella de un servidor). Los métodos bloquean el hilo que llama y nunca se llaman desde el de la interfaz. Solo se muestran enseguida las preguntas que nacen de una orden recién pedida (la operación se lanzó hace menos de 3 s, es la última lanzada, el foco sigue en la ventana principal y no hay diálogo ni menú abiertos: típicamente la lista de conflictos tras F5). Las de operaciones que ya iban en segundo plano se anuncian («La copia espera su decisión», esencial), esperan en la ventana de operaciones y se recuerdan cada 60 s. Todo diálogo de decisión ignora las teclas durante sus primeros 300 ms, para que una pulsación dirigida al panel no pulse un botón. Al salir, todas las esperas reciben «cancelar». Mientras espera, la operación ocupa su hilo (limitación aceptada: las listas de conflictos se responden en segundos).
- **Copiar** (`copiar.py`): `OperacionCopiar(origen: Proveedor, entradas: list[Entrada], destino: Proveedor, carpeta_destino: str, opciones: OpcionesCopia, mover: bool = False, nombre_nuevo: str = "")`, con `OpcionesCopia` (patrón, política, verificar, conservar fechas, copiar enlaces, carpetas vacías, un subdirectorio por elemento para extraer, marca de la Web). La usan el núcleo (F5, F6, duplicar), C (extraer), G (pegar y soltar) y B (sincronizar). Pasos: análisis (recorrido único, bytes, conflictos), lista de conflictos si los hay, copia de cada archivo a `~zc<8 hex>.tmp` en la carpeta de destino (sin solo lectura) con `CopyFileExW` si los dos lados son locales o por bloques si no, verificación opcional (SHA-256 releyendo origen y destino; puede leer de la caché del sistema y así lo dice la ayuda), sustitución con `ReplaceFileW` si el destino existe (conserva sus permisos) o renombrado si no, fechas y atributos, y en mover el borrado de ese origen. El conflicto se vuelve a comprobar justo antes de copiar cada archivo. Mover en el mismo volumen local es `MoveFileExW`.
- **Deshacer** (`deshacer.py`): en memoria durante la sesión, las 20 últimas acciones. `AccionDeshacer(descripcion, pasos)` con `Paso(tipo, despues, antes="", tamano=-1, modificado=0)` y `tipo` «renombrar», «quitar_carpeta» o «a_papelera»; `RegistroDeshacer.registrar(accion)`, `ultima()`, `sacar_ultima()` y `deshacer(accion) -> Resultado` (hechos y omitidos; los renombrados se deshacen por temporales, así también los ciclos). Las operaciones solo rellenan `self.deshacer`; la ventana lo registra al terminar. Los bloques nunca llaman a `registrar`.

### 9.7 Hilos

- Listar: cada panel guarda su tarea en curso y un número de petición; al pedir otra carpeta cancela la anterior y descarta resultados con número antiguo.
- Unidades y rutas de red: consultas en hilos desechables (fuera del grupo de `GestorTareas`) con tiempo límite y `SetErrorMode(SEM_FAILCRITICALERRORS)`, para que una unidad muerta no agote los hilos.
- Abrir con el programa asociado (`os.startfile` y `ShellExecuteEx`) en un hilo de trabajo con COM iniciado.
- Papelera (Send2Trash, que usa `IFileOperation`) en un hilo con COM en modo STA.
- Menú contextual de Windows y diálogos de propiedades: en el hilo de la interfaz (los exige el shell), solo sobre rutas locales.
- `sys.setswitchinterval(0.001)` para que la interfaz recupere el GIL enseguida.

## 10. Configuración y datos

- Preferencias: `data/config/settings.json` con la clase `Configuracion`. Todas las claves en el anexo [configuracion.md](configuracion.md).
- Archivos auxiliares en `data/config`, todos con `"version": 1` y leídos y escritos con `app/core/almacen_json.py` (`leer(nombre, por_defecto)` nunca lanza por el contenido; `escribir(nombre, datos)` lanza `OSError` si no puede):
	- `sesion.json` (N): `{"version": 1, "activo": "izquierdo", "lados": {"izquierdo": {"pestanas": [{"ruta": "C:\\", "vista": "completa", "orden": "nombre", "inverso": false, "filtro": "", "bloqueada": false, "columnas": [...]}], "actual": 0}, "derecho": {...}}, "historial_carpetas": {"izquierdo": [...], "derecho": [...]}, "historial_ordenes": [...], "cesta": [...]}`.
	- `favoritos.json` (F): `{"version": 1, "favoritos": [{"nombre": "Fotos", "ruta": "D:\\Fotos"}]}`.
	- `menu_usuario.json` (F) y el local `zcommander.menu.json`: `{"version": 1, "entradas": [{"etiqueta": "Comprimir con 7-Zip", "tecla": "A", "ordenes": ["7z a %O\\%N.7z %M"], "consola": false, "refrescar": true, "submenu": []}]}`.
	- `asociaciones.json` (F): `{"version": 1, "reglas": [{"patron": "*.txt;*.md", "abrir": "", "ver": "", "editar": "notepad++.exe %P"}]}`.
	- `conexiones.json` (D): `{"version": 1, "sitios": [{"id": "uuid", "nombre": "...", "protocolo": "ftp|ftps|sftp", "servidor": "...", "puerto": 21, "usuario": "", "guardar_contrasena": true, "carpeta": "/", "pasivo": true, "codificacion": "utf-8", "tiempo_espera_s": 30, "clave_privada": ""}]}`. Las contraseñas van en `secretos.dat` como `ftp:<id>:contrasena` y `ftp:<id>:frase`; al eliminar un sitio se borran sus secretos.
	- `hosts_conocidos.json` (D): `{"version": 1, "huellas": {"servidor:puerto": "SHA256:..."}}` para certificados FTPS; `known_hosts` (D): claves SFTP en formato OpenSSH con `paramiko.HostKeys`. En `conexiones.json` cada sitio lleva además `"aviso_sin_cifrar_mostrado": false`.
	- `busquedas.json` (B): `{"version": 1, "busquedas": [{"nombre": "...", "campos": {...}}]}` y `plantillas_renombrado.json` (E): `{"version": 1, "plantillas": [{"nombre": "...", "campos": {...}}]}`; `campos` son los controles de su diálogo por nombre.
	- En `menu_usuario.json`, una entrada con `submenu` no vacío es un submenú y su campo `ordenes` se ignora.
- Perfiles: `app/services/perfiles.py` (`PERFILES`, `aplicar_perfil(config, nombre)` con `establecer_varias`, `perfil_actual(config)` por comparación).

## 11. Accesibilidad

- **Semántica nativa primero**: nombre accesible de cada lista por su etiqueta; filas nativas con estado de selección; `wx.Gauge` para el progreso; textos largos en `TextCtrl` de solo lectura.
- **Qué se dice**, en este orden: (1) los esenciales siempre, aunque los anuncios estén desactivados o el lector en «no molestar» de zCommander; (2) con `accesibilidad.anuncios` desactivado, nada más; (3) si no, `accesibilidad.detalle` decide: breve (esencial y resultado), normal (y además normal), detallado (y además detalle); (4) los consejos se dicen si `accesibilidad.consejos` está activo, sea cual sea el detalle.
- **Anuncios** (`app/ui/anuncios.py`): niveles esencial (errores, preguntas, fin de operaciones; nunca interrumpen), resultado (respuesta a lo que se acaba de pedir), normal (cambios de carpeta, alcance de órdenes, marcas) y detalle (consejos y datos extra). La preferencia `accesibilidad.detalle` (breve, normal, detallado) decide hasta qué nivel se dice; esenciales y resultados siempre. `accesibilidad.progreso_voz` decide aparte cuándo se dice el progreso: cada 25 % (hitos), al empezar y al terminar, o solo al terminar.
- **Salida**: `app/ui/accesibilidad/voz.py` (cola única, coalescencia, canales navegación, avisos y esencial, historial). Elige automáticamente NVDA o JAWS (accessible_output2) o notificaciones UIA si el lector es Narrador u otro que accessible_output2 no conoce; se puede forzar en `accesibilidad.salida_voz`. Sin lector no habla por SAPI salvo que se active `accesibilidad.sapi_sin_lector`. Las notificaciones UIA usan una actividad por canal (`zCommander.navegacion`, `zCommander.esencial`) para que la navegación no borre un error pendiente: los esenciales van como «todas» (no interrumpen ni se descartan) y la navegación como «la más reciente». Lo que se anuncia antes de tener ventana se guarda y se dice al crearla. El canal esencial no se puede desactivar.
- **Nunca doble lectura**: no se anuncia lo que el lector ya lee al mover el foco.
- **Lectura por columnas**: Izquierda y Derecha y Ctrl+1 a Ctrl+0 son órdenes del catálogo (se pueden cambiar); el texto se compone con `componer_anuncio_celda` (agente de accesibilidad) según las preferencias de número de fila, cabecera y contenido.
- **Tonos de progreso** opcionales (`accesibilidad.tonos_progreso`): tono creciente cada 10 % y otro para «espera su decisión», con `winsound` en un hilo.
- **Ctrl+H** en cualquier control y el historial de anuncios.
- **Diálogos**: `preparar_dialogo`, `crear_botonera`, foco inicial útil y en la opción segura cuando la acción es destructiva; cada diálogo pasa `revisar_teclado` en una prueba (con las teclas propias de la ventana principal declaradas: F10, Insert, Ctrl+Tab, Ctrl+número).
- **Baja visión**: temas, letra de 8 a 40 puntos, `FromDIP`, conciencia de DPI al arrancar.

## 12. Errores y registro

- Registro por sesión en `data/logs` (plantilla) con archivo, línea, función, hilo y traza; avisos de excepciones no controladas (como mucho uno cada 30 s).
- Excepciones propias (`ErrorArchivos` y subclases) con mensaje en español; `errores.mensaje_para_usuario` y `errores.convertir` traducen los `OSError` de Windows.
- Nada de `except: pass`; lo que se ignora a propósito se registra con `log.debug(..., exc_info=True)` y un comentario con el porqué.
- Información para soporte: versión, Windows, Python, wxPython, carpeta de datos y las últimas 50 líneas del registro de la sesión, copiadas al portapapeles.

## 13. Rendimiento

- Lista virtual con formateo bajo demanda; `os.scandir` sin `stat` extra; orden con claves precalculadas.
- Tipo de archivo en caché por extensión, pedido en un hilo.
- La interfaz consulta el progreso como mucho 4 veces por segundo.
- Arranque: ventana visible antes de leer carpetas; paramiko, py7zr y el shell de pywin32 se importan al usarse por primera vez.
- Objetivos medibles en la sección 1.2.

## 14. Seguridad y privacidad

- **Inyección en órdenes**: las variables (`%P`, `%M`...) se sustituyen por referencias a variables de entorno del proceso hijo (`%ZC_1%`) y la orden se ejecuta con `cmd.exe /d /v:off /s /c "orden"` (sin AutoRun ni expansión retardada, así `!` no actúa); `cmd` expande una sola vez y dentro de comillas `& | < > ^` no actúan. Reglas de comillas: una palabra con variables fuera de comillas se entrecomilla entera y una sola vez (`%O\%N.7z` da `"%ZC_1%\%ZC_2%.7z"`); dentro de comillas que escribió la persona (`"%P"`) la variable va sin comillas propias; `%M` va sola y da una referencia entrecomillada por elemento; las carpetas nunca acaban en barra (la raíz es `D:\.`). Si la orden pasa de 8000 caracteres se avisa «use %L». Los programas externos sin `cmd` (visor y editor) se lanzan con `CreateProcess` y argumentos entrecomillados según `CommandLineToArgvW`. Pruebas con `a&calc.txt`, `100%PATH%.txt`, `a&b!c!.txt`, `"%P"`, `%O\%N.7z` y la raíz de una unidad.
- **Menú de usuario local**: `zcommander.menu.json` de una carpeta solo se usa si la persona confía en ella; se guarda la ruta y el SHA-256 del archivo en `seguridad.menus_locales_confiados` y se vuelve a preguntar si cambia.
- **Ejecutables**: Intro sobre `.exe`, `.bat`, `.cmd`, `.com`, `.ps1`, `.vbs`, `.js`, `.msi` y `.lnk` pide confirmación según `general.confirmar_ejecutar` (los `.ps1`, `.vbs` y `.js` siempre).
- **Marca de la Web**: al extraer de un comprimido que la tiene se copia su `Zone.Identifier` a cada archivo; las descargas de FTP y SFTP reciben `ZoneId=3`.
- **Recorrido de rutas en comprimidos**: validación de nombres en el proveedor; py7zr 0.11.3 (la que hay para Python 3.15) se usa solo leyendo miembro a miembro, nunca con su extracción en bloque.
- **FTP sin cifrar**: aviso la primera vez por sitio (`ftp.avisar_sin_cifrar`) de que usuario y contraseña viajan en claro.
- **Huellas** de servidores FTPS y SFTP: se preguntan la primera vez y se avisa claramente si cambian.
- **Contraseñas**: solo en `secretos.dat` (DPAPI), nunca en JSON ni en el registro (el registro redacta rutas `ftp://usuario:clave@`).
- **Temporales**: en `data/temp/extraidos`, borrados al cerrar cada visor y al arrancar.

## 15. Compatibilidad y requisitos

- Windows 10 1809 o posterior y Windows 11, de 64 bits (las notificaciones UIA necesitan 1709 o posterior).
- Python 3.15 y wxPython 4.3.2 (comprobados en el equipo de desarrollo); dependencias con versiones fijadas en `requirements.txt`: pywin32 312, Send2Trash 2.1.0, paramiko 5.1.0, py7zr 0.11.3, accessible_output2 0.17, Markdown 3.11. Desarrollo: pytest, ruff, cx_Freeze 8.7, comtypes (pruebas MSAA), pyftpdlib (pruebas FTP).
- Lectores: NVDA 2025 o posterior (las dos distribuciones de teclado), JAWS 2025 o posterior, Narrador de Windows 11.
- Rutas largas: con prefijo `\\?\` en las llamadas Win32 de `ProveedorLocal` a partir de 247 caracteres; el ejecutable declara `longPathAware`. No admiten rutas largas y avisan: papelera, menú contextual de Windows, propiedades, abrir con el programa asociado, iconos.
- Configuración: esquema 1.

## 16. Alternativas consideradas

- **Lista**: `wx.ListCtrl` virtual nativo (elegida) frente a `wx.dataview` o `wx.grid` (genéricos, peor con lectores) y a una lista no virtual (no escala a 100 000 elementos).
- **Marcas**: selección nativa con cambio de modo simple o múltiple (elegida) frente a casillas por fila (en listas virtuales su estado no llega bien a MSAA) y a marcas propias con prefijo en el nombre (sin semántica; el lector leería el prefijo).
- **Teclado**: despachador en `EVT_CHAR_HOOK` con atajos visibles en los menús (elegida) frente a solo aceleradores de wx (roban teclas a los campos de texto y no permiten ámbitos).
- **Copia**: `CopyFileExW` con rutina de progreso (elegida: progreso y cancelación dentro del archivo, conserva atributos y flujos) frente a `IFileOperation` (muestra su propio diálogo de conflictos, no accesible), robocopy (proceso externo sin conflictos interactivos) y `shutil` (sin progreso).
- **Concurrencia**: carriles por volumen sobre `GestorTareas` (elegida) frente a todo en paralelo (machaca discos duros e invalida conflictos) y a una sola cola (bloquea copias independientes).
- **Conflictos**: lista única tras el análisis más pregunta individual para los tardíos (elegida) frente a solo preguntas individuales (cientos de diálogos) o solo «para todos» (sin control).
- **Hilos o procesos** para trabajo pesado: hilos (elegida; `hashlib` y `zlib` liberan el GIL, la búsqueda trabaja por bloques) frente a procesos (más memoria y complejidad con cx_Freeze).
- **Voz**: accessible_output2 más notificaciones UIA (elegida) frente a solo accessible_output2 (Narrador quedaría mudo) y solo UIA (JAWS las trata peor).
- **7z**: py7zr (elegida, la única de Python con ruedas) frente a incluir `7z.exe` (habría que descargarlo y distribuirlo).
- **Vigilancia**: `wx.FileSystemWatcher` (elegida; entrega los avisos en el hilo de la interfaz) frente a `ReadDirectoryChangesW` propio en hilos.
- **Compilación**: cx_Freeze (la convención del autor) frente a PyInstaller y Nuitka.

## 17. Pruebas

- **Servicios** (`tests/servicios/`, sin wx): formato, selección, orden, rutas y nombres, proveedor local, resolver, almacén JSON, teclas y mapa, perfiles, sesión, recorrido, codificación, variables (con nombres peligrosos), línea de órdenes, cesta, deshacer, motor de copia (cada política, renombrado automático, verificación, cancelación, pausa, mover en el mismo volumen y entre volúmenes, errores simulados, rutas largas, carriles), eliminar definitivo; y las de cada bloque: búsqueda, diferencias de carpetas, sincronizar, tamaño de carpetas, renombrado múltiple (cada máscara con su ejemplo: `[N2-5]` sobre «abcdef» da «bcde»), atributos, enlaces, ZIP, TAR y 7z generados en la prueba (con nombres maliciosos), comprimir, sumas, dividir y unir, comparar archivos, menú de usuario, asociaciones, favoritos, conexiones.
- **FTP**: servidor local con pyftpdlib (dependencia de desarrollo instalada); SFTP con un servidor falso en memoria.
- **Interfaz** (`tests/ui/`, con `wx.App` de sesión, `APP_DATA_DIR` temporal y diálogos modales simulados por el `conftest`): la ventana se construye; cada orden tiene manejador importable; ningún choque en el mapa; los menús y cada diálogo pasan `revisar_teclado`; el despachador respeta los campos de texto; marcar conserva marcas al mover el cursor y cambia el modo de selección; navegar y volver con «..»; copiar con el diálogo simulado; el nombre accesible de la lista cambia con la carpeta (MSAA); el foco sin selección dispara el evento de foco (gancho de eventos, la prueba del experimento).
- **Anexos al día**: `tools/generar_anexos.py --comprobar`.
- **Capas**, **arranque** (`--comprobar-arranque`) y **ruff**.
- **Rendimiento** (marca `lento`): 100 000 archivos y la copia de humo de la sección 1.2.
- **Manual con lectores reales**: `docs/pruebas-manuales.md` con NVDA, JAWS y Narrador (pendiente explícito, no automatizable).
- **Provisionales**: `tests/ui/test_provisionales.py` falla, parametrizado por bloque, si algún manejador de ese bloque sigue siendo el provisional.

### 17.1 Pruebas de cada bloque (mínimo)

- **A** (`tests/servicios/test_a_comparar_archivos.py`, `tests/ui/test_a_visor.py`, `tests/ui/test_a_editor.py`): el visor abre un UTF-16 con BOM y muestra el texto; F4 alterna a hexadecimal («00000000  48 6F...»); buscar «hola» en un archivo de 3 MB por bloques lo encuentra; el editor guarda conservando CRLF y la codificación; dos textos que difieren en la línea 12 dan «Línea 12: cambiada».
- **B** (`tests/servicios/test_b_busqueda.py`, `test_b_diferencias.py`, `tests/ui/test_b_buscar.py`): `*.txt` con «hola» dentro encuentra 2 de 5 archivos; tamaño mínimo 1 KB excluye los pequeños; la búsqueda se cancela; comparar carpetas con un archivo más reciente a la izquierda lo marca solo a la izquierda; sincronizar izquierda a derecha produce «Copiar a la derecha» en las filas que faltan.
- **C** (`tests/servicios/test_c_zip.py`, `test_c_tar.py`, `test_c_7z.py`, `test_c_sumas.py`, `test_c_dividir.py`): un ZIP con una entrada `../malo.txt` se lista sin ella y no la extrae; un ZIP sin bit UTF-8 con «Año.txt» en cp850 muestra «Año.txt»; copiar dos archivos al ZIP reconstruye una sola vez; SHA-256 de «abc» es `ba7816bf...`; dividir 2,5 MB en partes de 1 MB da `.001`, `.002`, `.003` y `.crc` y unir devuelve el original.
- **D** (`tests/servicios/test_d_ftp.py`, `test_d_sftp.py`): con pyftpdlib local, listar, subir, bajar (con marca de la Web), renombrar y borrar; contraseña incorrecta da «Usuario o contraseña incorrectos»; SFTP con un servidor falso lista y cambia permisos a 644.
- **E** (`tests/servicios/test_e_renombrado.py`, `test_e_enlaces.py`): `[N2-5]` sobre «abcdef» da «bcde»; `[N-3,3]` sobre «abcdef» da «def»; `[C10+5:3]` da 010, 015, 020; `[Y]-[M]-[D]` usa la fecha de modificación; a→b y b→a se renombran con temporales; dos nombres iguales dan «Duplicado»; deshacer devuelve los nombres.
- **F** (`tests/ui/test_f_dialogos.py` y `tests/servicios/test_f_menu_usuario.py`): cada diálogo pasa `revisar_teclado`; la paleta filtra «copiar» y ejecuta la orden; el mapa de teclas rechaza Ctrl+R para otra orden avisando del choque; desde los valores de fábrica, `aplicar_perfil(config, "avanzado")` devuelve 7; el menú de usuario local no se usa sin confianza.
- **G** (`tests/ui/test_g_portapapeles.py`, `tests/servicios/test_g_menu_contextual.py`): copiar al portapapeles deja `CF_HDROP` con «Preferred DropEffect» 1; cortar, 2; pegar desde un `CF_HDROP` lanza una `OperacionCopiar`; el menú contextual de Windows se construye para un archivo local sin errores.
- **H**: `tools/comprobar_teclas.py` sin teclas sin documentar; cada sección 8.x tiene su apartado en el manual.

### 17.2 Dependencias entre bloques

- A usa `services/codificacion.py` (N) y rellena `ui/ventanas/diferencias.py`, que llaman N (conflictos) y B (sincronizar).
- B usa `recorrido.py`, `vfs/resultados.py`, `cesta.py` y `PanelProtocolo.abrir_lista`, `fijar_tamano`, `vincular_tarea` (N); lanza `OperacionCopiar` (N) para sincronizar.
- C registra sus proveedores en `resolver` (N); extraer lanza `OperacionCopiar` (N) con la marca de la Web; pide contraseñas con `Decisor.pedir_texto` (N).
- D registra sus esquemas en `resolver` (N); usa `AlmacenSecretos` y `Decisor.elegir` y `pedir_texto` (N); la marca de la Web la pone el motor de copia (N) al copiar desde ftp o sftp.
- E registra deshacer con `AccionDeshacer` (N) y usa `Proveedor.fijar_atributos` y `fijar_permisos`.
- F usa `asociaciones.py` (N), `descripciones_config.py` (N), `MapaTeclas` (N), `PanelProtocolo.historial`, `aplicar_columnas`, `ultima_carpeta` y `ctx.ejecutar_orden`, `ctx.modo_ayuda_teclado` (N).
- G usa `ListaArchivos.fijar_iconos`, `al_empezar_arrastre`, `fijar_destino_soltar` (N) y lanza `OperacionCopiar` (N); envuelve `windows/shell_basico.py` (N).
- H depende de todos y va al final.
- Ningún bloque edita `ordenes.py`, `configuracion.py`, `descripciones_config.py` ni archivos de otro; si necesita un cambio, lo pide.

## 18. Compilación y distribución

- `setup_cx.py` con `include_msvcr`, paquetes `wx`, `app`, `accessible_output2`, `paramiko`, `py7zr`, `send2trash`, `win32com`, `markdown`; manifiesto con `longPathAware` y DPI por monitor; `data/` distribuible (docs, sounds, icons) sin `config`, `logs`, `temp`.
- `entorno.bat` con Python 3.15 (crear, instalar, ejecutar, pruebas, compilar, comprobar, limpiar).
- ZIP `zCommander-1.0.0-win64.zip`.

## 19. Documentación

- `data/docs/manual.md`: manual completo por encabezados (primeros pasos, ventana, navegar, marcar, cada función de la sección 8, configuración y perfiles, accesibilidad con cada lector, preguntas frecuentes, solución de problemas). Se abre con F1 en el visor de ayuda.
- `data/docs/teclas.md` (generado), `data/docs/changelog.md` (novedades, el nombre que usa el visor de ayuda) y `LEEME.md`.
- `docs/pruebas-manuales.md`: recorrido de comprobación con cada lector.

## 20. Plan de trabajo

### 20.1 Núcleo (primero)

1. Adaptar el esqueleto (9.2); catálogo completo, configuración, anexos (hecho en parte).
2. VFS base, local, resolver, resultados; formato, orden, selección, recorrido, codificación.
3. Ventana, lados, paneles, lista, despachador, navegación, marcas, vistas, línea de órdenes y salida, barra de teclas, anuncios, consulta, sesión, ayuda.
4. Motor de operaciones (modelo, gestor, copiar, mover, eliminar, crear, deshacer), decisiones, diálogos de copiar, conflictos, eliminar y nombres, ventana de operaciones.
5. Módulos provisionales de los bloques en `app/ui/acciones/` y `registro_proveedores.py`.

**Criterio de salida del núcleo**: catálogo completo con manejadores (reales o provisionales); `test_capas` y `generar_anexos --comprobar` en verde; la ventana arranca, lista una carpeta, navega, marca y copia con la prueba de humo; pruebas del núcleo en verde.

### 20.2 Bloques (en paralelo tras el núcleo)

Cada bloque escribe solo sus archivos (9.3) y su módulo de `acciones`. Si necesita algo del núcleo que no está en las interfaces, lo pide en vez de tocarlo.

- **A, visor y editor**: 8.2, 8.3, comparar archivos (8.19, parte), crear archivo. Usa `services/codificacion.py` (N).
- **B, búsqueda y comparación**: 8.12, 8.13, 8.20, vista plana (8.21), cesta (8.25). Usa `recorrido.py` y `vfs/resultados.py` (N). «Enviar al panel», la vista plana y la cesta solo trabajan con rutas del disco local: con resultados de comprimidos o servidores, «Enviar al panel» se desactiva y dice «Solo se pueden enviar resultados del disco»; la vista plana fuera del disco local avisa y no hace nada.
- **C, comprimidos y utilidades**: 8.15, sumas, dividir y unir (8.19). Registra sus proveedores en `resolver`.
- **D, red**: 8.16 y 8.22. Registra `ftp`, `ftps` y `sftp` en `resolver`.
- **E, renombrado y atributos**: 8.9, 8.11, 8.14 (usa `OperacionRenombrar` del núcleo).
- **F, diálogos y personalización**: menú de usuario y asociaciones (8.17, parte), favoritos, historiales, árbol, unidades (8.1, parte), columnas, preferencias, perfil, mapa de teclas, temas, paleta y ayuda de teclado, asistente (8.26 y 8.27, parte), valores de fábrica.
- **G, integración con Windows**: propiedades, abrir con y menú de Windows (8.10), portapapeles y arrastrar (8.18), consola y Explorador (8.22), iconos y descripción de tipos (`windows/iconos.py`).
- **H, documentación** (al final): manual, novedades, LEEME, pruebas manuales.

### 20.3 Definición de terminado (cada bloque)

- Todas sus funciones de la sección 8 programadas, sin «pendiente» ni `NotImplementedError` ni el aviso provisional.
- Sus pruebas (las de la sección 17 de su parte) pasan y no rompen las demás; `ruff check` limpio.
- Sus diálogos y ventanas pasan `revisar_teclado`.

## 21. Riesgos

1. **Lectores reales**: el modelo de marcas y el cambio de modo de selección solo están comprobados con MSAA. Impacto alto. Mitigación: probarlo con NVDA, JAWS y Narrador nada más terminar el núcleo; alternativa preparada: anunciar siempre la marca y dejar la lista en selección múltiple. Señal: el lector no dice «seleccionado» o repite filas.
2. **Shell de Windows desde Python** (menú contextual, propiedades): extensiones de terceros pueden colgar el proceso. Mitigación: solo bajo petición, en rutas locales, con registro; el menú propio siempre está.
3. **Unidades de red muertas**: mitigado con hilos desechables y tiempos límite.
4. **py7zr antigua**: mitigado con lectura miembro a miembro y validación propia; si un 7z no se lee, se ofrece abrirlo con su programa.
5. **Escritura en ZIP grandes**: lenta; se avisa la primera vez y se hace en una transacción con progreso.
6. **Rendimiento con 100 000 archivos**: medido; si no se alcanza, se ordena en un hilo con «Ordenando...».
7. **comtypes en Python 3.15**: avisa de compatibilidad; solo se usa en pruebas.
8. **Alcance**: la versión es grande; las interfaces fijadas en código y los anexos generados permiten repartirla en bloques sin pisarse.
9. **Notificaciones UIA con Narrador**: solo probadas con la llamada (devuelve correcto); falta oírlas con Narrador. Señal: Narrador no dice los anuncios. Mitigación: probarlo al terminar el núcleo; alternativa, SAPI con aviso.
10. **Vigilancia de carpetas**: puede bloquear renombrados de carpetas superiores o la expulsión de discos. Señal: «la carpeta está en uso». Mitigación: no vigilar discos USB, soltar antes de operar, desactivable.
11. **ReplaceFileW**: falla en algunos NAS o con permisos restrictivos. Mitigación: alternativa con `MoveFileExW` registrada.
12. **Carriles**: dos letras del mismo disco físico van en paralelo. Impacto bajo; se documenta.
13. **Esperas de decisiones**: una operación que espera ocupa un hilo. Mitigación: los conflictos tardíos y errores se apartan y se resuelven al final.

## 22. Historial del documento

- 1.0 (8 de noviembre de 2026): primera versión, revisada con EGM (siete revisores).
- 1.1 (8 de noviembre de 2026): incorpora la resolución de la ronda 1 ([revision/ronda-1.md](revision/ronda-1.md)): un solo modelo de marcas con cambio de modo de selección, lista de conflictos, cola de decisiones, carriles por volumen, Narrador por UIA, seguridad, compatibilidad, alternativas, anexos generados e interfaces en código.
- 1.2 (8 de noviembre de 2026): incorpora la resolución de la ronda 2 ([revision/ronda-2.md](revision/ronda-2.md)): marcas con el modelo como fuente de verdad, entrecomillado por palabras, pausa sin carreras, carriles de origen y destino, conflictos tardíos al final, ámbitos de las vistas y de la línea de órdenes, contratos para los bloques, pruebas y dependencias por bloque.
- 1.3 (8 de noviembre de 2026): incorpora la resolución de la ronda 3 ([revision/ronda-3.md](revision/ronda-3.md)): panel activo con el foco en una vista, ámbitos solo de los tres del anexo, primera letra en `EVT_CHAR`, regla de F3 y del visor externo, servicios para los proveedores, suboperaciones, carriles de comprimidos y listas, preguntas que solo se muestran tras una orden recién pedida, esenciales que siempre se dicen, salida de órdenes, temporales vigilados.
- 1.4 (8 de noviembre de 2026): incorpora la resolución de la ronda 4 ([revision/ronda-4.md](revision/ronda-4.md)): transacciones y conexiones propias en las operaciones, marca de la Web automática, suboperaciones con `ejecutar_sub`, destinos repetidos, sustitución segura, renombrar en el núcleo, firmas reales de deshacer, `abrir_ruta` en hilos.
- 1.5 (8 de noviembre de 2026): estado al terminar la versión 1.0.0. Diferencias del código respecto a este documento, todas a favor de la accesibilidad o de la seguridad: Buscar archivos tiene tres pestañas (General, Contenido y Avanzado) para que las letras de acceso no se repitan; Eliminar pregunta con «Eliminar» y «Cancelar» (en la eliminación definitiva, Intro pulsa Cancelar); Preferencias reparte sus letras de acceso por página sin chocar con los botones (`tools/comprobar_preferencias.py`); `Decisor.elegir` y `pedir_texto` reciben `operacion` y, sin operación, la pregunta se muestra enseguida (contraseñas y huellas al entrar en un servidor); la primera lectura de un servidor sin conectar no tiene tiempo máximo; `revisar_teclado` admite `permitidas` para el F10 del visor y del editor; la lista de teclas incluye las ventanas con teclas propias y `tools/comprobar_teclas.py` lee el catálogo; `tools/empaquetar.py` crea el ZIP portable.
