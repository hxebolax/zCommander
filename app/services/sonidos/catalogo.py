# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Catálogo de eventos de sonido: la ÚNICA fuente de verdad (diseño 2.0, 4.1 y 4.2).

De aquí salen la página Sonidos de Preferencias, el mapa de sonidos, el anexo
``data/docs/sonidos.md``, el generador de paquetes y las pruebas de que cada
paquete está completo. Los 122 eventos del núcleo están escritos aquí; los de
los complementos se añaden al registrar sus manifiestos (``registrar_complemento``),
con la categoría ``plugin:<id>``.

Sin wx: lo usan el servicio de sonidos, los hilos y las herramientas.
"""

from __future__ import annotations

import builtins
import threading
from dataclasses import dataclass


def N_(texto: str) -> str:  # noqa: N802 - convención de gettext
	return texto


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


ALTA, MEDIA, BAJA = "alta", "media", "baja"
PRIORIDADES = (ALTA, MEDIA, BAJA)

#: Variantes de ``op.progreso`` (cada 10 % y, para «cada 25 %», 25 y 75).
VARIANTES_PROGRESO = ("10", "20", "25", "30", "40", "50", "60", "70", "75", "80", "90")


@dataclass(frozen=True)
class EventoSonido:
	"""Algo que puede sonar.

	:param id: ``categoria.nombre`` en el núcleo; ``<id del complemento>:<nombre>`` en un complemento.
	:param prioridad: ``alta`` (errores, preguntas, fin), ``media`` (resultados) o ``baja`` (navegación).
	:param por_defecto: si suena con los valores de fábrica.
	:param sustituye_anuncio: su anuncio breve se puede omitir si suena (``sonidos.sustituir_anuncios``).
	:param archivo: solo complementos: ruta del ``.wav`` dentro del paquete del complemento.
	"""

	id: str
	nombre: str
	descripcion: str
	categoria: str
	prioridad: str
	por_defecto: bool
	variantes: tuple[str, ...] = ()
	sustituye_anuncio: bool = False
	archivo: str = ""

	@property
	def es_de_complemento(self) -> bool:
		return ":" in self.id

	def archivo_paquete(self, variante: str = "") -> str:
		"""Nombre del ``.wav`` dentro de un paquete de sonidos (4.2).

		Núcleo: el id con los puntos cambiados por guiones bajos (``nav_carpeta_vacia.wav``),
		con ``_<variante>`` si la hay. Complemento: ``plugins/<id del complemento>/<nombre>.wav``.
		"""
		if self.es_de_complemento:
			complemento, nombre = self.id.split(":", 1)
			return f"plugins/{complemento}/{nombre}.wav"
		base = self.id.replace(".", "_")
		return f"{base}_{variante}.wav" if variante else f"{base}.wav"


CATEGORIAS: dict[str, str] = {
	"app": N_("Sistema"),
	"nav": N_("Navegación"),
	"cursor": N_("Cursor"),
	"marca": N_("Marcas"),
	"panel": N_("Paneles"),
	"pestana": N_("Pestañas"),
	"vista": N_("Vistas"),
	"filtro": N_("Filtros"),
	"busqueda_rapida": N_("Búsqueda rápida"),
	"orden": N_("Orden de la lista"),
	"dialogo": N_("Diálogos"),
	"menu": N_("Menús"),
	"paleta": N_("Paleta de órdenes"),
	"ayuda_teclado": N_("Ayuda de teclado"),
	"salida": N_("Salida de las órdenes"),
	"barra_botones": N_("Barra de botones"),
	"aviso": N_("Avisos"),
	"op": N_("Operaciones"),
	"portapapeles": N_("Portapapeles"),
	"busqueda": N_("Búsqueda"),
	"comparar": N_("Comparación"),
	"tamano": N_("Tamaño de carpetas"),
	"linea": N_("Línea de órdenes"),
	"comprimido": N_("Comprimidos"),
	"red": N_("Red"),
	"act": N_("Actualizaciones"),
	"comp": N_("Componentes"),
	"plugin": N_("Complementos"),
	"copia": N_("Copias de seguridad"),
	"macro": N_("Macros"),
	"regla": N_("Reglas"),
	"espacio": N_("Espacios de trabajo"),
	"tecla_global": N_("Teclas globales"),
}

# (id, nombre, cuándo suena, prioridad, fábrica, sustituye). Las tablas de 4.2, en su orden.
_A, _M, _B = ALTA, MEDIA, BAJA
_TABLA: tuple[tuple[str, str, str, str, bool, bool], ...] = (
	# Sistema
	("app.arranque", N_("Arranque"), N_("Aparece la ventana principal"), _A, True, False),
	("app.cierre", N_("Cierre"), N_("zCommander va a cerrarse"), _A, False, False),
	("app.sin_complementos", N_("Modo seguro"), N_("Arranca sin complementos"), _A, True, False),
	# Navegación
	("nav.entrar", N_("Entrar en una carpeta"), N_("Intro o Ctrl+Av Pág en una carpeta"), _B, False, False),
	("nav.subir", N_("Subir de carpeta"), N_("Retroceso, «..» o Alt+Arriba"), _B, False, False),
	("nav.raiz", N_("Raíz"), N_("Se llega a la raíz de la unidad"), _B, False, False),
	("nav.carpeta_vacia", N_("Carpeta vacía"), N_("La carpeta abierta no tiene elementos"), _M, True, True),
	("nav.leyendo", N_("Lectura lenta"), N_("Leer la carpeta tarda más de lo normal"), _B, False, True),
	("nav.historial", N_("Historial"), N_("Atrás o Adelante"), _B, False, False),
	("nav.unidad", N_("Cambio de unidad"), N_("Se elige otra unidad u origen"), _B, False, False),
	("nav.entrar_comprimido", N_("Entrar en un comprimido"), N_("Se abre un comprimido como carpeta"), _M, True, False),
	("nav.salir_comprimido", N_("Salir de un comprimido"), N_("Retroceso en la raíz del comprimido"), _B, False, False),
	("nav.lista_resultados", N_("Lista de resultados"), N_("El panel muestra una búsqueda, vista plana o cesta"), _M, True, False),
	("nav.tope", N_("Principio o final"), N_("Arriba en la primera fila o Abajo en la última"), _B, False, False),
	("nav.carpeta_desaparecida", N_("Carpeta borrada"), N_("La carpeta abierta desapareció y el panel subió"), _A, True, False),
	# Cursor
	("cursor.carpeta", N_("Carpeta"), N_("El cursor llega a una carpeta"), _B, False, False),
	("cursor.archivo", N_("Archivo"), N_("El cursor llega a un archivo"), _B, False, False),
	("cursor.comprimido", N_("Comprimido"), N_("El cursor llega a un comprimido que se puede abrir como carpeta"), _B, False, False),
	("cursor.ejecutable", N_("Ejecutable"), N_("El cursor llega a un programa o guion"), _B, False, False),
	("cursor.enlace", N_("Enlace"), N_("El cursor llega a un enlace o unión"), _B, False, False),
	("cursor.oculto", N_("Oculto"), N_("El cursor llega a un elemento oculto o de sistema"), _B, False, False),
	("cursor.marcado", N_("Marcado"), N_("El cursor llega a un elemento marcado"), _B, False, False),
	("cursor.nube", N_("Solo en la nube"), N_("El cursor llega a un archivo no descargado"), _B, False, False),
	("cursor.superior", N_("Fila «..»"), N_("El cursor llega a la fila para subir"), _B, False, False),
	# Marcas
	("marca.marcar", N_("Marcar"), N_("Se marca un elemento"), _B, True, True),
	("marca.desmarcar", N_("Desmarcar"), N_("Se desmarca un elemento"), _B, True, True),
	("marca.grupo", N_("Marcar en grupo"), N_("Marcar por patrón, todo o por extensión"), _B, True, False),
	("marca.quitar_todas", N_("Desmarcar todo"), N_("Se quitan todas las marcas"), _B, True, True),
	("marca.invertir", N_("Invertir"), N_("Se invierten las marcas"), _B, True, False),
	("marca.restaurar", N_("Restaurar"), N_("Se restauran las marcas anteriores"), _B, False, False),
	# Paneles, pestañas y vistas
	("panel.cambiar", N_("Cambiar de panel"), N_("Tab"), _B, False, False),
	("panel.oculto", N_("Otro panel oculto"), N_("Tab con el otro lado oculto"), _M, True, True),
	("pestana.nueva", N_("Pestaña nueva"), N_("Se abre una pestaña"), _B, False, False),
	("pestana.cerrar", N_("Cerrar pestaña"), N_("Se cierra una pestaña"), _B, False, False),
	("pestana.cambiar", N_("Cambiar de pestaña"), N_("Se pasa a otra pestaña"), _B, False, True),
	("vista.cambiar", N_("Cambiar de vista"), N_("Completa, breve, Información, Árbol o Vista rápida"), _B, False, False),
	("filtro.aplicar", N_("Filtro aplicado"), N_("Se aplica un filtro o el filtro rápido"), _B, False, False),
	("filtro.quitar", N_("Filtro quitado"), N_("Se quita el filtro"), _B, False, True),
	("busqueda_rapida.sin_coincidencia", N_("Sin coincidencias"), N_("La búsqueda rápida no encuentra nada"), _M, True, False),
	("busqueda_rapida.fin", N_("Fin de la búsqueda rápida"), N_("Pasa el tiempo de la búsqueda rápida"), _B, False, False),
	("orden.cambiar", N_("Cambio de orden"), N_("Ctrl+F3 a Ctrl+F7"), _B, False, False),
	# Ventanas, diálogos y menús
	("dialogo.abrir", N_("Abrir diálogo"), N_("Se abre un diálogo de zCommander"), _B, False, False),
	("dialogo.cerrar", N_("Cerrar diálogo"), N_("Se cierra un diálogo"), _B, False, False),
	("menu.abrir", N_("Abrir menú"), N_("F9, Alt o un menú contextual"), _B, False, False),
	("menu.cerrar", N_("Cerrar menú"), N_("Se cierra el menú sin elegir"), _B, False, False),
	("paleta.abrir", N_("Paleta de órdenes"), N_("Ctrl+E"), _B, False, False),
	("ayuda_teclado.entrar", N_("Entrar en la ayuda de teclado"), N_("Mayús+F12 activa el modo"), _M, True, False),
	("ayuda_teclado.salir", N_("Salir de la ayuda de teclado"), N_("Escape o Mayús+F12 lo desactivan"), _M, True, False),
	("salida.mostrar", N_("Salida de las órdenes"), N_("Ctrl+O muestra la salida"), _B, False, False),
	("barra_botones.entrar", N_("Barra de botones"), N_("El foco entra en la barra de botones"), _B, False, False),
	# Avisos
	("aviso.error", N_("Error"), N_("Se muestra o anuncia un error"), _A, True, False),
	("aviso.advertencia", N_("Advertencia"), N_("Se muestra una advertencia"), _A, True, False),
	("aviso.informacion", N_("Información"), N_("Se muestra un mensaje informativo"), _A, False, False),
	("aviso.pregunta", N_("Pregunta"), N_("Se abre una confirmación"), _A, True, False),
	("aviso.no_disponible", N_("No disponible"), N_("Orden que no se puede usar aquí o «No hay elementos»"), _A, True, True),
	("aviso.sin_permiso", N_("Sin permiso"), N_("Windows niega el acceso"), _A, True, False),
	# Operaciones
	("op.inicio", N_("Empieza una operación"), N_("Una operación pasa a «En marcha»"), _M, True, True),
	("op.progreso", N_("Progreso"), N_("Cada 10 % o cada 25 % según el progreso elegido"), _B, True, False),
	("op.pausa", N_("Pausa"), N_("Una operación se pausa"), _M, True, True),
	("op.reanudar", N_("Reanudar"), N_("Una operación se reanuda"), _M, True, True),
	("op.decision", N_("Espera su decisión"), N_("Una operación espera una respuesta"), _A, True, False),
	("op.fin", N_("Terminada"), N_("Una operación termina bien"), _A, True, False),
	("op.fin_errores", N_("Terminada con errores"), N_("Termina con errores u omitidos"), _A, True, False),
	("op.cancelada", N_("Cancelada"), N_("Se cancela una operación"), _A, True, False),
	("op.fallida", N_("Fallida"), N_("Una operación falla por completo"), _A, True, False),
	("op.en_cola", N_("En cola"), N_("Una operación espera en la cola"), _B, False, True),
	("op.conflictos", N_("Conflictos"), N_("Se abre la lista de conflictos"), _A, True, False),
	("op.deshacer", N_("Deshacer"), N_("Se deshace una acción"), _M, True, False),
	("op.papelera", N_("A la papelera"), N_("Termina un envío a la papelera"), _M, False, False),
	("op.eliminado", N_("Eliminado"), N_("Termina una eliminación definitiva"), _M, False, False),
	("op.carpeta_creada", N_("Carpeta creada"), N_("Se crea una carpeta"), _M, False, True),
	("op.renombrado", N_("Renombrado"), N_("Se renombra un elemento"), _M, False, True),
	# Portapapeles
	("portapapeles.copiar", N_("Copiar al portapapeles"), N_("Ctrl+C con archivos"), _M, True, True),
	("portapapeles.cortar", N_("Cortar"), N_("Ctrl+X con archivos"), _M, True, True),
	("portapapeles.pegar", N_("Pegar"), N_("Ctrl+V lanza la copia"), _M, False, False),
	("portapapeles.texto", N_("Texto copiado"), N_("Se copian rutas, nombres o la ruta de la carpeta"), _M, False, True),
	# Búsqueda y comparación
	("busqueda.inicio", N_("Empieza la búsqueda"), N_("Buscar archivos empieza"), _B, False, False),
	("busqueda.primer_resultado", N_("Primer resultado"), N_("Aparece el primer resultado"), _B, False, False),
	("busqueda.fin", N_("Búsqueda terminada"), N_("Termina con resultados"), _M, True, False),
	("busqueda.sin_resultados", N_("Sin resultados"), N_("Termina sin resultados"), _M, True, False),
	("comparar.iguales", N_("Iguales"), N_("Comparar carpetas o archivos: son iguales"), _M, True, False),
	("comparar.diferencias", N_("Diferencias"), N_("Comparar carpetas o archivos: hay diferencias"), _M, True, False),
	("tamano.calculado", N_("Tamaño calculado"), N_("Termina el cálculo del tamaño de carpetas"), _M, False, False),
	# Línea de órdenes
	("linea.ejecutar", N_("Ejecutar"), N_("Intro en la línea de órdenes"), _B, False, False),
	("linea.fin", N_("Orden terminada"), N_("La orden termina con código 0"), _M, True, False),
	("linea.error", N_("Orden con error"), N_("La orden termina con otro código"), _A, True, False),
	# Comprimidos
	("comprimido.probado", N_("Comprimido correcto"), N_("Probar comprimido termina sin errores"), _M, True, False),
	("comprimido.danado", N_("Comprimido dañado"), N_("Probar o abrir encuentra daños"), _A, True, False),
	("comprimido.contrasena", N_("Pide contraseña"), N_("Un comprimido cifrado pide la contraseña"), _A, True, False),
	("comprimido.cifrado_sin_motor", N_("Cifrado no admitido"), N_("Un RAR o 7z cifrado sin 7-Zip instalado"), _A, True, False),
	# Red
	("red.conectar", N_("Conectado"), N_("Se conecta un servidor, una unidad o un recurso"), _M, True, False),
	("red.desconectar", N_("Desconectado"), N_("Se desconecta"), _M, True, False),
	("red.perdida", N_("Conexión perdida"), N_("Se pierde una conexión"), _A, True, False),
	("red.reconectada", N_("Reconectada"), N_("Una unidad o conexión vuelve"), _M, True, False),
	("red.equipo", N_("Equipo encontrado"), N_("El descubrimiento encuentra un equipo"), _B, False, False),
	("red.descubrir_fin", N_("Búsqueda de equipos terminada"), N_("Termina el descubrimiento"), _M, False, False),
	("red.credenciales", N_("Pide credenciales"), N_("Un servidor pide usuario y contraseña"), _A, True, False),
	("red.huella", N_("Huella nueva"), N_("Huella o certificado desconocido o cambiado"), _A, True, False),
	# Actualizaciones y componentes
	("act.disponible", N_("Actualización disponible"), N_("Hay una versión nueva de zCommander"), _A, True, False),
	("act.descargada", N_("Actualización descargada"), N_("Termina la descarga y se puede instalar"), _A, True, False),
	("act.instalada", N_("Actualización instalada"), N_("Primer arranque correcto de la versión nueva"), _A, True, False),
	("act.revertida", N_("Actualización revertida"), N_("Se volvió a la versión anterior"), _A, True, False),
	("act.al_dia", N_("Sin novedades"), N_("La comprobación manual no encuentra nada"), _M, False, False),
	("comp.disponible", N_("Componentes nuevos"), N_("Hay versiones nuevas de componentes"), _A, True, False),
	("comp.actualizado", N_("Componente actualizado"), N_("Un componente se actualizó y pasó su prueba"), _A, True, False),
	("comp.revertido", N_("Componente revertido"), N_("Un componente volvió a la versión anterior"), _A, True, False),
	# Complementos
	("plugin.instalado", N_("Complemento instalado"), N_("Se instala o actualiza un complemento"), _M, True, False),
	("plugin.activado", N_("Complemento activado"), N_("Se carga su código"), _B, False, False),
	("plugin.inhabilitado", N_("Complemento inhabilitado"), N_("La persona lo inhabilita en el gestor"), _B, False, False),
	("plugin.fallo", N_("Complemento con fallos"), N_("Un complemento falla o queda fuera de uso por errores"), _A, True, False),
	("plugin.cargando", N_("Cargando complemento"), N_("La carga tarda más de 300 ms"), _B, False, True),
	# Copias, macros, reglas y personalización
	("copia.creada", N_("Copia creada"), N_("Termina una copia de seguridad"), _M, True, False),
	("copia.restaurada", N_("Copia restaurada"), N_("Termina una restauración"), _M, True, False),
	("macro.grabar", N_("Grabación empezada"), N_("Empieza la grabación de una macro"), _M, True, True),
	("macro.parar", N_("Grabación terminada"), N_("Termina la grabación"), _M, True, True),
	("macro.paso", N_("Paso de macro"), N_("Se ejecuta cada paso"), _B, False, False),
	("macro.fin", N_("Macro terminada"), N_("Termina una macro"), _M, False, False),
	("regla.a", N_("Aviso de regla A"), N_("Lo eligen las reglas de anuncio, color y sonido"), _B, True, False),
	("regla.b", N_("Aviso de regla B"), N_("Lo eligen las reglas de anuncio, color y sonido"), _B, True, False),
	("regla.c", N_("Aviso de regla C"), N_("Lo eligen las reglas de anuncio, color y sonido"), _B, True, False),
	("espacio.abierto", N_("Espacio de trabajo"), N_("Se abre un espacio de trabajo"), _M, False, True),
	("tecla_global.recibida", N_("Tecla global"), N_("Llega una tecla global con zCommander en segundo plano"), _M, False, False),
)

EVENTOS_NUCLEO: tuple[EventoSonido, ...] = tuple(
	EventoSonido(
		id_, nombre, descripcion, id_.split(".", 1)[0], prioridad, fabrica,
		VARIANTES_PROGRESO if id_ == "op.progreso" else (), sustituye,
	)
	for id_, nombre, descripcion, prioridad, fabrica, sustituye in _TABLA
)

# ── Eventos de los complementos (se registran desde los manifiestos) ─────────

_candado = threading.RLock()
_de_complementos: dict[str, EventoSonido] = {}
_nombres_complementos: dict[str, str] = {}
_por_id: dict[str, EventoSonido] = {e.id: e for e in EVENTOS_NUCLEO}


def registrar_complemento(id_complemento: str, nombre_complemento: str, sonidos: list[dict]) -> list[EventoSonido]:
	"""Añade los ``[[sonidos]]`` de un manifiesto (ya validado) con sus valores por defecto de 3.3.

	:return: los eventos registrados.
	"""
	nuevos = []
	for datos in sonidos:
		corto = str(datos["id"])
		evento = EventoSonido(
			id=f"{id_complemento}:{corto}",
			nombre=str(datos.get("nombre") or corto),
			descripcion=str(datos.get("descripcion", "")),
			categoria=f"plugin:{id_complemento}",
			prioridad=str(datos.get("prioridad", MEDIA)),
			por_defecto=bool(datos.get("por_defecto", True)),
			archivo=str(datos.get("archivo") or f"sonidos/{corto}.wav"),
		)
		nuevos.append(evento)
	with _candado:
		quitar_complemento(id_complemento)
		_nombres_complementos[id_complemento] = nombre_complemento
		for evento in nuevos:
			_de_complementos[evento.id] = evento
			_por_id[evento.id] = evento
	return nuevos


def quitar_complemento(id_complemento: str) -> None:
	with _candado:
		for clave in [c for c, e in _de_complementos.items() if e.categoria == f"plugin:{id_complemento}"]:
			_de_complementos.pop(clave, None)
			_por_id.pop(clave, None)
		_nombres_complementos.pop(id_complemento, None)


def vaciar_complementos() -> None:
	"""Quita todos los eventos de complementos (solo pruebas, con ``registro.vaciar``)."""
	with _candado:
		for clave in list(_de_complementos):
			_por_id.pop(clave, None)
		_de_complementos.clear()
		_nombres_complementos.clear()


def evento(id_evento: str) -> EventoSonido | None:
	with _candado:
		return _por_id.get(id_evento)


def eventos() -> tuple[EventoSonido, ...]:
	"""Todos los eventos: los del núcleo en el orden de 4.2 y después los de complementos por id."""
	with _candado:
		return EVENTOS_NUCLEO + tuple(sorted(_de_complementos.values(), key=lambda e: e.id))


def eventos_de_complementos() -> tuple[EventoSonido, ...]:
	with _candado:
		return tuple(sorted(_de_complementos.values(), key=lambda e: e.id))


def nombre_categoria(categoria: str) -> str:
	"""Nombre visible de una categoría (para ``plugin:<id>``, el nombre del complemento)."""
	if categoria.startswith("plugin:"):
		with _candado:
			return _nombres_complementos.get(categoria.split(":", 1)[1], categoria.split(":", 1)[1])
	return _(CATEGORIAS.get(categoria, categoria))


def por_defecto() -> dict[str, bool]:
	"""``{id: activo de fábrica}`` de todos los eventos."""
	return {e.id: e.por_defecto for e in eventos()}
