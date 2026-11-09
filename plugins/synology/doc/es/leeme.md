# NAS Synology

Este complemento controla un NAS Synology con DSM desde zCommander: el estado y la salud, los discos, las carpetas, los usuarios, los paquetes, los contenedores, los servicios, la seguridad y mucho más. Además, File Station se abre como una carpeta más en los paneles de zCommander.

## Lo más importante: solo lectura

Cada NAS empieza en **modo solo lectura**. En ese modo, zCommander puede ver todo, pero no puede cambiar nada: las acciones que cambian algo aparecen desactivadas y, si se intentan, zCommander las bloquea antes de enviar nada al NAS.

Para cambiar algo, active «Permitir cambios en el NAS» (en el menú Complementos, submenú «Nubes y NAS», submenú «NAS Synology») o la casilla «Permitir cambios en este NAS» de la ventana del NAS. zCommander le explica en «Qué se permite» lo que podrá hacer y le deja elegir:

- «Solo durante esta sesión» (lo recomendado): al cerrar zCommander o desconectar, el NAS vuelve a solo lectura.
- «Hasta que lo vuelva a activar».

Con los cambios permitidos, el título de la ventana empieza por «CAMBIOS PERMITIDOS» y cada acción pide confirmación diciendo exactamente qué va a hacer.

## Órdenes

Están en el menú Complementos, submenú «Nubes y NAS», submenú «NAS Synology», y en la paleta de órdenes. Solo «Estado del NAS» tiene tecla de fábrica; a las demás se les puede dar una en el mapa de teclas.

### Conexión y ventana

- **Estado del NAS** (Ctrl+Mayús+F9): abre la ventana del NAS en el área Estado, conectando si hace falta.
- **Conectar con un NAS...**: abre la lista de NAS guardados para conectar, dar de alta uno nuevo o arrancar el NAS de demostración.
- **Desconectar del NAS**: cierra la sesión con el NAS (y para el NAS de demostración si es ese).
- **Ir a un área del NAS...**: elige un área y abre la ventana en ella.
- **Permitir cambios en el NAS**: casilla que activa o desactiva el modo que permite cambiar cosas; activarlo pide confirmación.
- **NAS de demostración**: arranca un NAS simulado en este equipo para practicar.

### File Station

- **Abrir File Station en el panel**: abre las carpetas compartidas del NAS en el panel activo.
- **Tareas en segundo plano del NAS...**: muestra las tareas de File Station (copiar, mover, borrar, comprimir y extraer en el NAS).
- **Crear un enlace compartido...**: crea un enlace de los elementos elegidos en un panel del NAS y lo copia al portapapeles.
- **Comprimir en el NAS...**: comprime los elementos elegidos en el propio NAS, sin pasar los archivos por este equipo.
- **Extraer en el NAS...**: extrae el comprimido del cursor en el propio NAS.

### Administración

- **Herramientas avanzadas por SSH...**: herramientas para casos difíciles, desactivadas de fábrica.
- **Reiniciar el NAS...** y **Apagar el NAS...**: con doble confirmación.

## Practicar con el NAS de demostración

La orden «NAS de demostración» arranca un NAS simulado dentro de su equipo. Responde como un DS220+ con DSM 7.3.2 y tiene datos inventados: discos, carpetas, usuarios, paquetes y contenedores. Nada sale a la red y todo lo que cambie se pierde al cerrar zCommander. Es la forma segura de aprender el complemento.

También está en la lista de NAS («Conectar con un NAS...»), con el botón «NAS de demostración». Lo que hace el simulador cuando le pide un cambio se elige en Preferencias, Complementos, NAS Synology: aplicarlo en memoria, simularlo sin cambiar nada o rechazarlo.

## Dar de alta su NAS

1. Abra «Conectar con un NAS...» y pulse «Nuevo...».
2. Escriba un «Nombre» (por ejemplo, NAS de casa), la «Dirección (nombre o IP)» del NAS y su «Usuario» de DSM. Deje marcada «Usar HTTPS (recomendado)» y el «Puerto» 5001.
3. La primera vez, zCommander le mostrará la huella del certificado del NAS, leída por grupos de cuatro cifras. Compárela con la de DSM (Panel de control, Seguridad, Certificado) y pulse «Aceptar y recordar». Si un día cambia, zCommander le avisará antes de enviar la contraseña.
4. Si su cuenta tiene verificación en dos pasos, escriba en «Código de verificación» el código de su aplicación. Con «Recordar este equipo», DSM no se lo volverá a pedir.

La contraseña se guarda cifrada en este equipo solo si marca «Recordar la contraseña». zCommander nunca envía la contraseña sin cifrar por la red, y solo prueba la contraseña una vez por cada vez que usted conecta: así nunca provoca el bloqueo automático de DSM.

Las cuentas que no son del grupo administrators pueden usar File Station; las áreas de administración dirán «Sin permiso con esta cuenta».

## La ventana del NAS

Se abre con «Estado del NAS» (Ctrl+Mayús+F9) o al conectar.

- **Conexión** (Alt+C): el NAS, su modelo y versión, la cuenta y el modo.
- **Áreas** (Alt+R): las que tiene su NAS. Intro abre la elegida; si se queda en una, se abre sola tras un momento.
- **Sección** (Alt+S): aparece cuando el área tiene varias partes (por ejemplo, contenedores, proyectos e imágenes).
- **Elementos** (Alt+E): la lista del área. Flecha izquierda y Flecha derecha leen las columnas; Intro hace la acción principal.
- **Detalle** (Alt+D): todo lo que se sabe del elemento elegido.
- Botones de las **acciones** del área, «Volver a leer» (Alt+V), «Acciones...» (Alt+I; un menú con todas, también las desactivadas), la casilla «Permitir cambios en este NAS» (Alt+M) y «Cerrar» (Alt+A).

### Teclas de la ventana del NAS

- F6: pasa de las áreas a los elementos y al revés.
- Ctrl+R: vuelve a leer el área.
- Ctrl+Mayús+T: dice el uso del procesador, la memoria, la red y los discos.
- Aplicaciones o Mayús+F10 en la lista de elementos: menú de acciones.
- Ctrl+H: explica el control enfocado (también por qué una acción está desactivada).
- F1: abre esta ayuda.
- Escape: cierra la ventana (la conexión sigue abierta).

La ventana se vuelve a leer sola cada pocos segundos mientras se ve, sin mover el foco. Cuando aparece un aviso de salud nuevo (un disco con sectores dañados, un contenedor con problemas, un certificado que caduca, la falta de la actualización de seguridad de DSM), zCommander lo dice una sola vez.

## Áreas

- **Estado y salud**: modelo, procesador, memoria, versión de DSM y si tiene la corrección de seguridad del boletín Synology-SA-26:06, temperatura, uso, volúmenes y avisos. Acción: copiar el resumen.
- **Almacenamiento y discos**: volúmenes, grupos y discos con su S.M.A.R.T. Acciones: ver los atributos S.M.A.R.T.; con cambios permitidos, pruebas S.M.A.R.T. y limpieza de datos.
- **File Station**: carpetas compartidas (Intro las abre en el panel), búsqueda en todo el NAS, tareas en segundo plano y enlaces compartidos.
- **Carpetas compartidas**: cifrado, papelera, cuota y permisos de cada usuario; con cambios permitidos, cambiar un permiso.
- **Usuarios y grupos**: activar, desactivar y cambiar la contraseña (DSM pide antes la suya).
- **Paquetes**: iniciar, parar y actualizar.
- **Container Manager**: contenedores con su salud, registro (las últimas 200 líneas) y uso de recursos; iniciar, parar y reiniciar contenedores y proyectos; imágenes.
- **Synology Drive** y **Synology Photos**: estado, equipos conectados y volver a indexar las fotos.
- **Tareas programadas**: ejecutar ahora, activar y desactivar.
- **Registros y conexiones**: sucesos (filtrar y exportar a texto) y conexiones actuales (cerrar una).
- **Notificaciones**, **Red** (interfaces, DDNS, QuickConnect) y **Seguridad** (Asesor de seguridad, inicios de sesión, direcciones bloqueadas con desbloqueo y certificados con su caducidad).
- **Servicios**: SMB, SSH, WebDAV, NFS, FTP y SFTP; activar o desactivar avisando de la consecuencia.
- **Monitor de recursos**, **Actualizaciones** de DSM (comprobar; instalar con doble confirmación) y **Apagar y reiniciar**.

Las áreas que su NAS no tiene (por ejemplo, Hyper Backup o Download Station si no están instalados) no aparecen.

## Apagar, reiniciar e instalar DSM

Piden dos confirmaciones. La primera explica las consecuencias (conexiones que se cortarán y tareas en curso) con el foco en la opción segura. La segunda le pide escribir el nombre del NAS.

## File Station en el panel

«Abrir File Station en el panel» muestra las carpetas compartidas en el panel activo, con direcciones como synology://nas_de_casa/Documentos. También aparece en el selector de unidades. Se puede copiar, mover, renombrar, crear carpetas y borrar como en cualquier carpeta (si el NAS tiene los cambios permitidos). Copiar o mover dentro del mismo NAS lo hace el propio NAS, sin pasar los archivos por su equipo.

En un panel del NAS también puede crear un enlace compartido (se copia al portapapeles), comprimir y extraer en el propio NAS. Estas tareas muestran su progreso como cualquier operación de zCommander y se pueden cancelar.

## Herramientas avanzadas por SSH

Están desactivadas de fábrica y se activan en Preferencias («Permitir las herramientas avanzadas por SSH»). Sirven para ver los atributos S.M.A.R.T. en bruto, registros largos y estadísticas de los contenedores, actualizar un proyecto Compose o rescatar un paquete cuando la interfaz web no responde. Usan la clave pública del agente de OpenSSH de Windows. La contraseña de sudo se pide cada vez y nunca se guarda.

## Preferencias

En Preferencias, Complementos, NAS Synology:

- **Tiempo para conectar con el NAS (segundos)**: 10 por defecto.
- **Espera máxima de cada orden al NAS (segundos)**: 30 por defecto.
- **Intervalo de refresco de la ventana del NAS (segundos)**: 10 por defecto.
- **Anunciar los avisos de salud del NAS**: activada por defecto.
- **Temperatura del sistema que da aviso (grados)**: 55 por defecto.
- **Permitir las herramientas avanzadas por SSH**: desactivada por defecto.
- **Registro detallado de las peticiones al NAS**: desactivada por defecto. Nunca guarda contraseñas ni sesiones.
- **Modo del NAS de demostración**: los cambios se aplican en memoria (por defecto), se simulan o se rechazan.
- **Hasta cuándo dura el permiso de cambios (opción propuesta)**: solo durante la sesión (por defecto) o hasta que lo vuelva a activar.

El botón «Abrir la configuración avanzada...» abre la lista de NAS.

## Sonidos

- **NAS conectado**: se ha iniciado la sesión con un NAS.
- **NAS desconectado**: se ha cerrado la sesión con un NAS.
- **Aviso de salud del NAS**: un disco, un volumen, un contenedor o un certificado necesita atención.
- **Tarea del NAS terminada**: ha terminado una tarea en segundo plano (comprimir, extraer).
- **Cambios permitidos en el NAS**: el NAS ha salido del modo solo lectura.
- **NAS de demostración en marcha**: se ha arrancado el NAS simulado.
- **Código de verificación del NAS**: el NAS pide el código de la verificación en dos pasos.
