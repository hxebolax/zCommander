# Mapa de sonidos de zCommander

Generado con `python tools/generar_anexos.py` a partir de `app/services/sonidos/catalogo.py` y de los manifiestos de los complementos. Cada sonido se puede activar o desactivar en Preferencias, Sonidos; todo lo que suena se puede saber también de otra forma (anuncio, historial o consulta).

## Paquetes de serie

Se elige uno en Preferencias, Sonidos («Paquete:»). Todos tienen los mismos sonidos; cambia su carácter.

- Clásico: Tonos de onda triangular con intervalos claros: el éxito sube una tercera mayor y el error baja una cuarta. Es el paquete por defecto.
- Suave: Senos con ataque y caída lentos, filtrados y 6 dB por debajo: para quien usa sonidos todo el día.
- Retro 8 bits: Ondas cuadradas y arpegios rápidos cuantizados, al estilo de las consolas antiguas.
- Minimalista: Clics y golpes de 5 a 40 ms: lo mínimo para distinguir los eventos sin ocupar tiempo de voz.
- Cristal: Campanas por síntesis FM con parciales inarmónicos y una cola corta de reverberación.

## Sistema

- Arranque (`app.arranque`): Aparece la ventana principal. Activo por defecto: sí.
- Cierre (`app.cierre`): zCommander va a cerrarse. Activo por defecto: no.
- Modo seguro (`app.sin_complementos`): Arranca sin complementos. Activo por defecto: sí.

## Navegación

- Entrar en una carpeta (`nav.entrar`): Intro o Ctrl+Av Pág en una carpeta. Activo por defecto: no.
- Subir de carpeta (`nav.subir`): Retroceso, «..» o Alt+Arriba. Activo por defecto: no.
- Raíz (`nav.raiz`): Se llega a la raíz de la unidad. Activo por defecto: no.
- Carpeta vacía (`nav.carpeta_vacia`): La carpeta abierta no tiene elementos. Activo por defecto: sí.
- Lectura lenta (`nav.leyendo`): Leer la carpeta tarda más de lo normal. Activo por defecto: no.
- Historial (`nav.historial`): Atrás o Adelante. Activo por defecto: no.
- Cambio de unidad (`nav.unidad`): Se elige otra unidad u origen. Activo por defecto: no.
- Entrar en un comprimido (`nav.entrar_comprimido`): Se abre un comprimido como carpeta. Activo por defecto: sí.
- Salir de un comprimido (`nav.salir_comprimido`): Retroceso en la raíz del comprimido. Activo por defecto: no.
- Lista de resultados (`nav.lista_resultados`): El panel muestra una búsqueda, vista plana o cesta. Activo por defecto: sí.
- Principio o final (`nav.tope`): Arriba en la primera fila o Abajo en la última. Activo por defecto: no.
- Carpeta borrada (`nav.carpeta_desaparecida`): La carpeta abierta desapareció y el panel subió. Activo por defecto: sí.

## Cursor

- Carpeta (`cursor.carpeta`): El cursor llega a una carpeta. Activo por defecto: no.
- Archivo (`cursor.archivo`): El cursor llega a un archivo. Activo por defecto: no.
- Comprimido (`cursor.comprimido`): El cursor llega a un comprimido que se puede abrir como carpeta. Activo por defecto: no.
- Ejecutable (`cursor.ejecutable`): El cursor llega a un programa o guion. Activo por defecto: no.
- Enlace (`cursor.enlace`): El cursor llega a un enlace o unión. Activo por defecto: no.
- Oculto (`cursor.oculto`): El cursor llega a un elemento oculto o de sistema. Activo por defecto: no.
- Marcado (`cursor.marcado`): El cursor llega a un elemento marcado. Activo por defecto: no.
- Solo en la nube (`cursor.nube`): El cursor llega a un archivo no descargado. Activo por defecto: no.
- Fila «..» (`cursor.superior`): El cursor llega a la fila para subir. Activo por defecto: no.

## Marcas

- Marcar (`marca.marcar`): Se marca un elemento. Activo por defecto: sí.
- Desmarcar (`marca.desmarcar`): Se desmarca un elemento. Activo por defecto: sí.
- Marcar en grupo (`marca.grupo`): Marcar por patrón, todo o por extensión. Activo por defecto: sí.
- Desmarcar todo (`marca.quitar_todas`): Se quitan todas las marcas. Activo por defecto: sí.
- Invertir (`marca.invertir`): Se invierten las marcas. Activo por defecto: sí.
- Restaurar (`marca.restaurar`): Se restauran las marcas anteriores. Activo por defecto: no.

## Paneles

- Cambiar de panel (`panel.cambiar`): Tab. Activo por defecto: no.
- Otro panel oculto (`panel.oculto`): Tab con el otro lado oculto. Activo por defecto: sí.

## Pestañas

- Pestaña nueva (`pestana.nueva`): Se abre una pestaña. Activo por defecto: no.
- Cerrar pestaña (`pestana.cerrar`): Se cierra una pestaña. Activo por defecto: no.
- Cambiar de pestaña (`pestana.cambiar`): Se pasa a otra pestaña. Activo por defecto: no.

## Vistas

- Cambiar de vista (`vista.cambiar`): Completa, breve, Información, Árbol o Vista rápida. Activo por defecto: no.

## Filtros

- Filtro aplicado (`filtro.aplicar`): Se aplica un filtro o el filtro rápido. Activo por defecto: no.
- Filtro quitado (`filtro.quitar`): Se quita el filtro. Activo por defecto: no.

## Búsqueda rápida

- Sin coincidencias (`busqueda_rapida.sin_coincidencia`): La búsqueda rápida no encuentra nada. Activo por defecto: sí.
- Fin de la búsqueda rápida (`busqueda_rapida.fin`): Pasa el tiempo de la búsqueda rápida. Activo por defecto: no.

## Orden de la lista

- Cambio de orden (`orden.cambiar`): Ctrl+F3 a Ctrl+F7. Activo por defecto: no.

## Diálogos

- Abrir diálogo (`dialogo.abrir`): Se abre un diálogo de zCommander. Activo por defecto: no.
- Cerrar diálogo (`dialogo.cerrar`): Se cierra un diálogo. Activo por defecto: no.

## Menús

- Abrir menú (`menu.abrir`): F9, Alt o un menú contextual. Activo por defecto: no.
- Cerrar menú (`menu.cerrar`): Se cierra el menú sin elegir. Activo por defecto: no.

## Paleta de órdenes

- Paleta de órdenes (`paleta.abrir`): Ctrl+E. Activo por defecto: no.

## Ayuda de teclado

- Entrar en la ayuda de teclado (`ayuda_teclado.entrar`): Mayús+F12 activa el modo. Activo por defecto: sí.
- Salir de la ayuda de teclado (`ayuda_teclado.salir`): Escape o Mayús+F12 lo desactivan. Activo por defecto: sí.

## Salida de las órdenes

- Salida de las órdenes (`salida.mostrar`): Ctrl+O muestra la salida. Activo por defecto: no.

## Barra de botones

- Barra de botones (`barra_botones.entrar`): El foco entra en la barra de botones. Activo por defecto: no.

## Avisos

- Error (`aviso.error`): Se muestra o anuncia un error. Activo por defecto: sí.
- Advertencia (`aviso.advertencia`): Se muestra una advertencia. Activo por defecto: sí.
- Información (`aviso.informacion`): Se muestra un mensaje informativo. Activo por defecto: no.
- Pregunta (`aviso.pregunta`): Se abre una confirmación. Activo por defecto: sí.
- No disponible (`aviso.no_disponible`): Orden que no se puede usar aquí o «No hay elementos». Activo por defecto: sí.
- Sin permiso (`aviso.sin_permiso`): Windows niega el acceso. Activo por defecto: sí.

## Operaciones

- Empieza una operación (`op.inicio`): Una operación pasa a «En marcha». Activo por defecto: sí.
- Progreso (`op.progreso`): Cada 10 % o cada 25 % según el progreso elegido. Activo por defecto: sí.
- Pausa (`op.pausa`): Una operación se pausa. Activo por defecto: sí.
- Reanudar (`op.reanudar`): Una operación se reanuda. Activo por defecto: sí.
- Espera su decisión (`op.decision`): Una operación espera una respuesta. Activo por defecto: sí.
- Terminada (`op.fin`): Una operación termina bien. Activo por defecto: sí.
- Terminada con errores (`op.fin_errores`): Termina con errores u omitidos. Activo por defecto: sí.
- Cancelada (`op.cancelada`): Se cancela una operación. Activo por defecto: sí.
- Fallida (`op.fallida`): Una operación falla por completo. Activo por defecto: sí.
- En cola (`op.en_cola`): Una operación espera en la cola. Activo por defecto: no.
- Conflictos (`op.conflictos`): Se abre la lista de conflictos. Activo por defecto: sí.
- Deshacer (`op.deshacer`): Se deshace una acción. Activo por defecto: sí.
- A la papelera (`op.papelera`): Termina un envío a la papelera. Activo por defecto: no.
- Eliminado (`op.eliminado`): Termina una eliminación definitiva. Activo por defecto: no.
- Carpeta creada (`op.carpeta_creada`): Se crea una carpeta. Activo por defecto: no.
- Renombrado (`op.renombrado`): Se renombra un elemento. Activo por defecto: no.

## Portapapeles

- Copiar al portapapeles (`portapapeles.copiar`): Ctrl+C con archivos. Activo por defecto: sí.
- Cortar (`portapapeles.cortar`): Ctrl+X con archivos. Activo por defecto: sí.
- Pegar (`portapapeles.pegar`): Ctrl+V lanza la copia. Activo por defecto: no.
- Texto copiado (`portapapeles.texto`): Se copian rutas, nombres o la ruta de la carpeta. Activo por defecto: no.

## Búsqueda

- Empieza la búsqueda (`busqueda.inicio`): Buscar archivos empieza. Activo por defecto: no.
- Primer resultado (`busqueda.primer_resultado`): Aparece el primer resultado. Activo por defecto: no.
- Búsqueda terminada (`busqueda.fin`): Termina con resultados. Activo por defecto: sí.
- Sin resultados (`busqueda.sin_resultados`): Termina sin resultados. Activo por defecto: sí.

## Comparación

- Iguales (`comparar.iguales`): Comparar carpetas o archivos: son iguales. Activo por defecto: sí.
- Diferencias (`comparar.diferencias`): Comparar carpetas o archivos: hay diferencias. Activo por defecto: sí.

## Tamaño de carpetas

- Tamaño calculado (`tamano.calculado`): Termina el cálculo del tamaño de carpetas. Activo por defecto: no.

## Línea de órdenes

- Ejecutar (`linea.ejecutar`): Intro en la línea de órdenes. Activo por defecto: no.
- Orden terminada (`linea.fin`): La orden termina con código 0. Activo por defecto: sí.
- Orden con error (`linea.error`): La orden termina con otro código. Activo por defecto: sí.

## Comprimidos

- Comprimido correcto (`comprimido.probado`): Probar comprimido termina sin errores. Activo por defecto: sí.
- Comprimido dañado (`comprimido.danado`): Probar o abrir encuentra daños. Activo por defecto: sí.
- Pide contraseña (`comprimido.contrasena`): Un comprimido cifrado pide la contraseña. Activo por defecto: sí.
- Cifrado no admitido (`comprimido.cifrado_sin_motor`): Un RAR o 7z cifrado sin 7-Zip instalado. Activo por defecto: sí.

## Red

- Conectado (`red.conectar`): Se conecta un servidor, una unidad o un recurso. Activo por defecto: sí.
- Desconectado (`red.desconectar`): Se desconecta. Activo por defecto: sí.
- Conexión perdida (`red.perdida`): Se pierde una conexión. Activo por defecto: sí.
- Reconectada (`red.reconectada`): Una unidad o conexión vuelve. Activo por defecto: sí.
- Equipo encontrado (`red.equipo`): El descubrimiento encuentra un equipo. Activo por defecto: no.
- Búsqueda de equipos terminada (`red.descubrir_fin`): Termina el descubrimiento. Activo por defecto: no.
- Pide credenciales (`red.credenciales`): Un servidor pide usuario y contraseña. Activo por defecto: sí.
- Huella nueva (`red.huella`): Huella o certificado desconocido o cambiado. Activo por defecto: sí.

## Actualizaciones

- Actualización disponible (`act.disponible`): Hay una versión nueva de zCommander. Activo por defecto: sí.
- Actualización descargada (`act.descargada`): Termina la descarga y se puede instalar. Activo por defecto: sí.
- Actualización instalada (`act.instalada`): Primer arranque correcto de la versión nueva. Activo por defecto: sí.
- Actualización revertida (`act.revertida`): Se volvió a la versión anterior. Activo por defecto: sí.
- Sin novedades (`act.al_dia`): La comprobación manual no encuentra nada. Activo por defecto: no.

## Componentes

- Componentes nuevos (`comp.disponible`): Hay versiones nuevas de componentes. Activo por defecto: sí.
- Componente actualizado (`comp.actualizado`): Un componente se actualizó y pasó su prueba. Activo por defecto: sí.
- Componente revertido (`comp.revertido`): Un componente volvió a la versión anterior. Activo por defecto: sí.

## Complementos

- Complemento instalado (`plugin.instalado`): Se instala o actualiza un complemento. Activo por defecto: sí.
- Complemento activado (`plugin.activado`): Se carga su código. Activo por defecto: no.
- Complemento inhabilitado (`plugin.inhabilitado`): La persona lo inhabilita en el gestor. Activo por defecto: no.
- Complemento con fallos (`plugin.fallo`): Un complemento falla o queda fuera de uso por errores. Activo por defecto: sí.
- Cargando complemento (`plugin.cargando`): La carga tarda más de 300 ms. Activo por defecto: no.

## Copias de seguridad

- Copia creada (`copia.creada`): Termina una copia de seguridad. Activo por defecto: sí.
- Copia restaurada (`copia.restaurada`): Termina una restauración. Activo por defecto: sí.

## Macros

- Grabación empezada (`macro.grabar`): Empieza la grabación de una macro. Activo por defecto: sí.
- Grabación terminada (`macro.parar`): Termina la grabación. Activo por defecto: sí.
- Paso de macro (`macro.paso`): Se ejecuta cada paso. Activo por defecto: no.
- Macro terminada (`macro.fin`): Termina una macro. Activo por defecto: no.

## Reglas

- Aviso de regla A (`regla.a`): Lo eligen las reglas de anuncio, color y sonido. Activo por defecto: sí.
- Aviso de regla B (`regla.b`): Lo eligen las reglas de anuncio, color y sonido. Activo por defecto: sí.
- Aviso de regla C (`regla.c`): Lo eligen las reglas de anuncio, color y sonido. Activo por defecto: sí.

## Espacios de trabajo

- Espacio de trabajo (`espacio.abierto`): Se abre un espacio de trabajo. Activo por defecto: no.

## Teclas globales

- Tecla global (`tecla_global.recibida`): Llega una tecla global con zCommander en segundo plano. Activo por defecto: no.

## Complemento Git básico

- Repositorio Git (`zc.git:repositorio`): Suena al entrar en una carpeta de un repositorio Git. Activo por defecto: sí.

## Complemento Editor hexadecimal accesible

- Tecla no válida en el editor hexadecimal (`zc.hexadecimal:no_valido`): Se pulsó algo que no es un dígito hexadecimal en la columna hexadecimal. Activo por defecto: sí.

## Complemento Imágenes: información, descripción y visor

- Descripción recibida (`zc.imagenes:descripcion`): Llega la descripción de una imagen. Activo por defecto: sí.

## Complemento Metadatos y etiquetas de audio

- Etiquetas guardadas (`zc.metadatos:guardado`): Termina de guardarse un cambio de etiquetas. Activo por defecto: sí.

## Complemento Monitor de carpetas y reglas automáticas

- Archivo nuevo en una carpeta vigilada (`zc.monitor:archivo_nuevo`): Suena cuando termina de llegar un archivo a una carpeta vigilada. Activo por defecto: sí.
- Regla del monitor aplicada (`zc.monitor:regla_aplicada`): Suena cuando una regla mueve, copia, renombra, extrae o etiqueta un archivo. Activo por defecto: sí.

## Complemento Notas, comentarios y etiquetas

- Nota de carpeta (`zc.notas:nota_carpeta`): Suena al entrar en una carpeta que tiene una nota. Activo por defecto: sí.

## Complemento Nubes

- Cuenta de nube conectada (`zc.nubes:conectar`): Suena al añadir una cuenta de nube y comprobarla. Activo por defecto: sí.
- Cuenta de nube eliminada (`zc.nubes:desconectar`): Suena al eliminar una cuenta de nube. Activo por defecto: sí.
- Unidad de nube montada (`zc.nubes:montada`): Suena al montar una cuenta como letra de unidad. Activo por defecto: sí.
- Motor de nubes detenido (`zc.nubes:motor_detenido`): Suena si el motor de nubes (rclone) se detiene sin que se le pida. Activo por defecto: sí.
- Esperando la autorización (`zc.nubes:oauth_espera`): Suena al empezar a esperar la autorización en el navegador. Activo por defecto: sí.
- Autorización recibida (`zc.nubes:oauth_ok`): Suena al llegar la autorización del navegador. Activo por defecto: sí.
- Sincronización terminada (`zc.nubes:sincronizacion_fin`): Suena al terminar de sincronizar o de emparejar carpetas. Activo por defecto: sí.

## Complemento Reconocimiento de texto, OCR

- Reconocimiento de texto terminado (`zc.ocr:fin`): Termina un reconocimiento de texto (del archivo, del portapapeles, de la ventana o de un lote). Activo por defecto: sí.

## Complemento Historial del portapapeles

- Copia en otro programa (`zc.portapapeles:copia_externa`): Suena cuando otro programa copia algo al portapapeles (si está activado el anuncio de las copias externas). Activo por defecto: sí.

## Complemento Archivos en uso y procesos

- Programa cerrado (`zc.procesos:cerrado`): Suena cuando un programa o proceso se cierra a petición de la persona. Activo por defecto: sí.

## Complemento Programador de tareas

- Tarea programada terminada (`zc.programador:tarea_fin`): Suena al terminar una tarea programada con zCommander abierto o, al abrirlo, si se ejecutaron tareas mientras estaba cerrado. Activo por defecto: sí.

## Complemento Reproductor multimedia

- Fin de la cola (`zc.reproductor:fin_lista`): Termina la última pista de la cola del reproductor. Activo por defecto: sí.
- Marcador guardado (`zc.reproductor:marcador`): Se guarda un marcador en la pista que suena. Activo por defecto: sí.
- Cambio de pista (`zc.reproductor:pista`): Empieza otra pista de la cola del reproductor. Activo por defecto: sí.

## Complemento Seguridad de descargas e integridad

- Amenaza (`zc.seguridad:amenaza`): Suena cuando Defender o VirusTotal encuentran algo, o la suma no coincide. Activo por defecto: sí.
- Sin firma (`zc.seguridad:sin_firma`): Suena al comprobar un ejecutable sin firma o con una firma no válida. Activo por defecto: sí.

## Complemento NAS Synology

- Aviso de salud del NAS (`zc.synology:aviso_salud`): Un disco, un volumen, un contenedor o un certificado del NAS necesita atención. Activo por defecto: sí.
- Cambios permitidos en el NAS (`zc.synology:cambios_permitidos`): El NAS ha salido del modo solo lectura. Activo por defecto: sí.
- NAS conectado (`zc.synology:conectado`): Se ha iniciado la sesión con un NAS Synology. Activo por defecto: sí.
- NAS de demostración en marcha (`zc.synology:demostracion_iniciada`): Se ha arrancado el NAS simulado para practicar. Activo por defecto: sí.
- NAS desconectado (`zc.synology:desconectado`): Se ha cerrado la sesión con un NAS Synology. Activo por defecto: sí.
- Código de verificación del NAS (`zc.synology:otp`): El NAS pide el código de la verificación en dos pasos. Activo por defecto: sí.
- Tarea del NAS terminada (`zc.synology:tarea_fin`): Ha terminado una tarea en segundo plano del NAS (comprimir, extraer). Activo por defecto: sí.

## Complemento Lectura en voz y audiolibros

- Fin de la lectura (`zc.voz:fin`): Termina de leerse en voz alta un archivo. Activo por defecto: sí.
