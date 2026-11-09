# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Genera los anexos del diseño y la lista de teclas a partir del código.

- ``docs/ordenes.md``: todas las órdenes del catálogo (id, etiqueta, teclas,
  ámbito, bloque, manejador) agrupadas por menú.
- ``docs/configuracion.md``: todas las claves de configuración con tipo, valor
  por defecto y regla.
- ``data/docs/teclas.md``: lista de teclas para la persona usuaria, con un
  apartado por cada complemento de serie (2.0).
- ``data/docs/sonidos.md``: mapa de sonidos (2.0, 4.9).
- ``docs/componentes.md``: componentes de ``data/bin`` (2.0, desde ``linea_base.json``).
- ``app/plugins/serie.py``: lista de los complementos de serie con su versión (2.0, 3.2).

Las órdenes, claves, teclas y sonidos de los complementos de serie se leen de
sus manifiestos con ``registro.registrar_serie()``, sin importar su código.

Uso: ``python tools/generar_anexos.py`` (y ``--comprobar`` para fallar si los
archivos no están al día; lo usan las pruebas).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import json  # noqa: E402

from app.core import configuracion, descripciones_config  # noqa: E402
from app.plugins import config_plugins, registro  # noqa: E402
from app.services import teclas  # noqa: E402
from app.services.sonidos import catalogo as catalogo_sonidos  # noqa: E402
from app.ui import ordenes  # noqa: E402

if not registro.complementos():
	registro.registrar_serie()


# Teclas propias de ventanas que no salen de un menú ni del catálogo (las atienden a mano en
# EVT_CHAR_HOOK o son de listas): las dejaron los bloques en docs/revision/peticiones-*.md.
# comprobar_teclas.py compara cada sección con todo el código de app/; las que tienen teclas que solo
# existen en el código de un complemento van en su SECCIONES_SIN_COMPROBAR.
TECLAS_VENTANAS_NUCLEO: tuple[tuple[str, tuple[str, ...]], ...] = (
	("En la paleta de órdenes", (
		"Ctrl+D: Marca o desmarca la orden elegida como favorita.",
	)),
	("En la barra de botones", (
		"Izquierda y Derecha: Recorren los botones.",
		"Inicio y Fin: Van al primer botón y al último.",
		"Intro o Espacio: Ejecutan el botón.",
		"Escape o Tab: Vuelven al panel.",
	)),
	("En el diálogo de Preferencias", (
		"Ctrl+Tab y Ctrl+Mayús+Tab: Cambian de página, también desde los controles.",
		"Abajo: En «Buscar una opción», pasa a la lista de opciones que coinciden.",
		"Intro: En «Buscar una opción», lleva a la primera opción que coincide.",
	)),
	("En la página Sonidos de Preferencias", (
		"Espacio: Activa o desactiva el sonido elegido.",
		"Intro: Prueba el sonido elegido aunque esté desactivado.",
		"Ctrl+A: Activa todos los sonidos de la categoría visible.",
		"Ctrl+Mayús+A: Desactiva todos los sonidos de la categoría visible.",
	)),
	("En el mapa de sonidos", (
		"Intro: Reproduce el sonido elegido aunque esté desactivado.",
	)),
	("En los paquetes de sonidos", (
		"Intro: Usa el paquete elegido (en la lista de paquetes) o prueba el sonido elegido (en el paso Sonidos del asistente).",
	)),
)

TECLAS_VENTANAS_COMPLEMENTOS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
	"zc.procesos": (
		("En la ventana Procesos", (
			"Supr: En la lista, termina el proceso elegido.",
			"F5: Actualiza la lista.",
		)),
	),
	"zc.duplicados": (
		("En la lista de duplicados", (
			"Espacio: Marca o desmarca la copia para quitarla.",
			"F1: Ayuda del complemento.",
			"Escape: Cierra la lista.",
		)),
	),
	"zc.busqueda_instantanea": (
		("En la ventana de búsqueda instantánea", (
			"Intro: En «Buscar», va al primer resultado; en la lista, va al archivo.",
			"Escape: Cierra la ventana.",
			"F1: Ayuda del complemento.",
			"Ctrl+H: Ayuda del control.",
		)),
	),
	"zc.tablas": (
		("En el visor de tabla", (
			"Izquierda y Derecha: Columna anterior y siguiente.",
			"Ctrl+1 a Ctrl+0: Leen la columna 1 a 10.",
			"Ctrl+F: Filtrar.",
			"Ctrl+G: Ir a la fila.",
			"Ctrl+O: Ordenar por la columna actual.",
			"Ctrl+E: Exportar a CSV.",
			"F5: Consulta SQL (solo bases SQLite).",
			"Ctrl+T: Estructura de la tabla.",
			"Escape: Cerrar.",
			"F1: Ayuda del complemento.",
		)),
		("En el diálogo Consulta SQL", (
			"Ctrl+Intro: Ejecutar la consulta.",
		)),
	),
	"zc.hexadecimal": (
		("En la ventana del editor hexadecimal", (
			"Izquierda y Derecha: Un byte.",
			"Arriba y Abajo: Una línea.",
			"Inicio y Fin: Principio y fin de la línea.",
			"Ctrl+Inicio y Ctrl+Fin: Principio y fin del archivo.",
			"Re Pág y Av Pág: Una pantalla.",
			"Mayús con las teclas de movimiento: Seleccionar.",
			"Tab: Cambiar entre la columna hexadecimal y la de texto.",
			"Insert: Insertar o sobrescribir (con NVDA, Insert dos veces).",
			"Supr y Retroceso: Borrar en modo insertar.",
			"Ctrl+S y F2: Guardar.",
			"Mayús+F2: Guardar como.",
			"Ctrl+Z: Deshacer.",
			"Ctrl+Y: Rehacer.",
			"Ctrl+C: Copiar como hexadecimal.",
			"Ctrl+Mayús+C: Copiar como texto.",
			"Ctrl+V: Pegar.",
			"Ctrl+F: Buscar.",
			"F3: Buscar siguiente.",
			"Mayús+F3: Buscar anterior.",
			"Ctrl+R: Reemplazar.",
			"Ctrl+G: Ir a un desplazamiento.",
			"Ctrl+I: Inspector.",
			"Ctrl+Mayús+I: Decir la barra de estado.",
			"Ctrl+E: Cambiar el orden de bytes.",
			"Escape: Cerrar.",
			"F1: Ayuda del complemento.",
		)),
	),
	"zc.git": (
		("En el diálogo Historial de Git", (
			"Intro: En la lista, muestra los cambios de la confirmación.",
		)),
	),
	"zc.portapapeles": (
		("En el diálogo Historial del portapapeles", (
			"Supr: En la lista, borra el elemento elegido.",
			"Intro: En la lista, lo vuelve a poner en el portapapeles.",
		)),
	),
	"zc.imagenes": (
		("En el visor de imágenes", (
			"Más y Menos: Amplían o reducen la imagen.",
			"Av Pág y Re Pág: Imagen siguiente o anterior de la carpeta.",
			"Flechas: Desplazan la imagen ampliada (con el foco en la imagen).",
		)),
	),
	"zc.monitor": (
		("En la lista de reglas del monitor", (
			"Intro: Edita la regla elegida.",
			"Supr: Borra la regla elegida.",
		)),
		("En la lista de carpetas vigiladas", (
			"Supr: Quita la carpeta elegida.",
		)),
	),
	"zc.synology": (
		("En la ventana del NAS", (
			"F6: Pasa de la lista de áreas a la de elementos y al revés.",
			"Ctrl+R: Vuelve a leer el área.",
			"Ctrl+Mayús+T: Dice el uso del procesador, la memoria, la red y los discos.",
			"Aplicaciones o Mayús+F10: En la lista de elementos, menú con las acciones del área.",
			"Escape: Cierra la ventana del NAS (la conexión sigue abierta).",
			"F1: Ayuda del complemento.",
		)),
	),
	"zc.notas": (
		("En el diálogo de etiquetas", (
			"Espacio: Pone o quita la etiqueta.",
			"Ctrl+A: Marca todas.",
			"Ctrl+Mayús+A: Desmarca todas.",
			"F1: Ayuda del complemento.",
		)),
	),
	"zc.nubes": (
		("En la ventana Cuentas de nube", (
			"Intro: Abre la cuenta elegida en el panel activo.",
			"Supr: Elimina la cuenta elegida (con confirmación).",
		)),
		("En la ventana Unidades montadas", (
			"Supr: Desmonta la unidad elegida.",
		)),
		("En la ventana Carpetas compartidas por zCommander", (
			"Supr: Deja de compartir lo elegido.",
		)),
		("En todas las ventanas de Nubes", (
			"Escape: Cierra o cancela.",
			"Ctrl+H: Explica el control.",
			"F1: Ayuda de Nubes.",
		)),
	),
	"zc.ocupacion": (
		("En la lista de archivos grandes y antiguos", (
			"Intro: Lleva el otro panel al archivo.",
			"F1: Ayuda del complemento.",
			"Escape: Cierra la lista.",
		)),
	),
	"zc.organizador": (
		("En el diálogo del organizador", (
			"F1: Ayuda del complemento.",
			"Escape: Cancela.",
		)),
	),
	"zc.papelera": (
		("En el panel de la papelera", (
			"Supr: Elimina definitivamente.",
			"F5: Copia al otro panel.",
		)),
	),
	"zc.programador": (
		("En la lista de tareas programadas", (
			"Intro: Edita la tarea elegida.",
			"Supr: Borra la tarea elegida.",
		)),
	),
	"zc.proyectos": (
		("En el salto rápido", (
			"Abajo: Pasa de «Ir a» a la lista.",
			"Intro: Abre la carpeta elegida.",
		)),
		("En la lista de proyectos", (
			"Intro: Abre el proyecto elegido.",
			"Supr: Borra el proyecto elegido.",
		)),
	),
	"zc.reproductor": (
		("En la ventana del reproductor", (
			"Espacio: Pausa o continúa.",
			"Izquierda y Derecha: Retrocede o avanza un salto corto.",
			"Ctrl+Izquierda y Ctrl+Derecha: Retrocede o avanza un salto medio.",
			"Re Pág y Av Pág: Retrocede o avanza un salto largo.",
			"Más y Menos: Sube o baja el volumen.",
			"Ctrl+Más y Ctrl+Menos: Sube o baja la velocidad.",
			"P: Dice la posición.",
			"G: Ir a un tiempo o a un porcentaje.",
			"M: Añade un marcador.",
			"Ctrl+M: Lista de marcadores.",
			"R: Cambia el modo de repetir.",
			"A: Activa o quita el orden aleatorio.",
			"Supr: Quita de la cola la pista elegida.",
			"Intro: Reproduce la pista elegida de la cola.",
		)),
	),
	"zc.sincronizacion": (
		("En la lista de tareas de sincronización", (
			"Intro: Edita la tarea elegida.",
			"Supr: Borra la tarea elegida.",
		)),
	),
}


AMBITOS = {"panel": "con el foco en un panel", "global": "en toda la ventana principal", "linea": "en la línea de órdenes"}
BLOQUES = {
	"N": "Núcleo", "A": "A, visor y editor", "B": "B, búsqueda y comparación", "C": "C, comprimidos y utilidades",
	"D": "D, red", "E": "E, renombrado y atributos", "F": "F, diálogos y personalización", "G": "G, integración con Windows",
	# 2.0 (19)
	"PL": "PL, complementos", "SO": "SO, sonidos", "AC": "AC, actualizador", "CO": "CO, componentes", "CS": "CS, copia de seguridad",
	"CM": "CM, comprimidos", "RD": "RD, red", "PE": "PE, personalización", "NV": "NV, complemento de NVDA", "LI": "LI, licencias",
	"P1": "P1, multimedia", "P2": "P2, documentos y datos", "P3": "P3, orden y limpieza", "P4": "P4, sistema y seguridad",
	"P5": "P5, automatización", "NU": "NU, Nubes", "NS": "NS, NAS Synology", "COMPLEMENTO": "complemento de la persona",
}


def _limpio(etiqueta: str) -> str:
	return etiqueta.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip(".").strip()


def _teclas(orden: ordenes.Orden) -> str:
	return ", ".join(teclas.nombre_visible(teclas.normalizar(t)) for t in orden.teclas) or "sin tecla"


def _plana(elementos):
	for elemento in elementos:
		if isinstance(elemento, tuple):
			yield from _plana(elemento[1])
		elif elemento:
			yield elemento


def generar_ordenes() -> str:
	lineas = [
		"# Anexo: catálogo de órdenes",
		"",
		"Generado con `python tools/generar_anexos.py` a partir de `app/ui/ordenes.py`. No lo edite a mano.",
		"",
		f"Hay {len(ordenes.CATALOGO)} órdenes. Cada una indica sus teclas de fábrica, dónde funcionan, qué bloque la programa y su manejador (`app/ui/acciones/<módulo>.py`).",
		"",
	]
	vistas: set[str] = set()

	def bloque_orden(o: ordenes.Orden) -> list[str]:
		vistas.add(o.id)
		extra = []
		if o.por_lado:
			extra.append("en los menús Izquierdo y Derecho, actúa sobre ese lado")
		if o.tipo == "casilla":
			extra.append("casilla")
		if o.fija:
			extra.append("tecla fija")
		if o.param:
			extra.append(f"parámetro «{o.param}»")
		texto = [
			f"### {_limpio(o.etiqueta)} (`{o.id}`)",
			"",
			f"- {o.ayuda}",
			f"- Teclas: {_teclas(o)}; {AMBITOS[o.ambito]}.",
			f"- Bloque: {BLOQUES[o.bloque]}. Manejador: `{o.manejador}`.",
		]
		if extra:
			texto.append("- " + "; ".join(extra).capitalize() + ".")
		texto.append("")
		return texto

	for titulo, contenido in ordenes.menus():
		if contenido == ordenes.LADO:
			if "Izquierdo" not in titulo:
				continue
			lineas += ["## Menús Izquierdo y Derecho", ""]
			contenido = ordenes.MENU_LADO
		else:
			lineas += [f"## Menú {_limpio(titulo)}", ""]
		for id_ in _plana(contenido):
			if id_ not in vistas:
				lineas += bloque_orden(ordenes.POR_ID[id_])
	resto = [o for o in ordenes.CATALOGO if o.id not in vistas]
	if resto:
		lineas += ["## Órdenes solo de teclado", ""]
		for o in resto:
			lineas += bloque_orden(o)
	return "\n".join(lineas).rstrip() + "\n"


def generar_configuracion() -> str:
	lineas = [
		"# Anexo: claves de configuración",
		"",
		"Generado con `python tools/generar_anexos.py` a partir de `app/core/configuracion.py`. No lo edite a mano.",
		"",
		"Se guardan en `data/config/settings.json`. El formato de cada clave es `seccion.clave`; el tipo lo fija el valor por defecto. Los valores de fábrica son los del perfil Intermedio. Etiquetas y ayudas: `app/core/descripciones_config.py`.",
		"",
	]
	for seccion, claves in configuracion.VALORES_POR_DEFECTO.items():
		lineas += [f"## Sección {seccion}", ""]
		for clave, valor in claves.items():
			completa = f"{seccion}.{clave}"
			regla = configuracion.REGLAS.get(completa)
			detalle = ""
			if regla is not None:
				if regla.opciones:
					detalle = "; admite: " + ", ".join(map(str, regla.opciones))
				elif regla.minimo is not None or regla.maximo is not None:
					detalle = f"; de {regla.minimo:g} a {regla.maximo:g}"
			etiqueta, ayuda, pagina = descripciones_config.DESCRIPCIONES.get(completa, ("", "", None))
			paginas = dict(descripciones_config.PAGINAS)
			donde = f" Página «{paginas[pagina]}» de Preferencias." if pagina in paginas else " No aparece en Preferencias."
			lineas.append(f"- `{completa}`: {type(valor).__name__}, por defecto `{valor!r}`{detalle}. {ayuda}{donde}")
		lineas.append("")
	lineas += ["## Claves de los complementos de serie", "",
		"Cada complemento guarda las suyas en `data/config/plugins/<id>.json`; su nombre completo es `plugin.<id>.<clave>` (diseño 2.0, 3.6).", ""]
	claves = config_plugins.registro().claves()
	if not claves:
		lineas.append("Ningún complemento de serie declara todavía su configuración (la completa el bloque de cada uno).")
	for completa in claves:
		id_complemento, corta = config_plugins.separar_clave(completa)
		declaracion = next(d for d in config_plugins.registro().declaraciones(id_complemento) if d["clave"] == corta)
		lineas.append(f"- `{completa}`: {declaracion.get('tipo')}, por defecto `{declaracion.get('defecto')!r}`. {declaracion.get('ayuda', '')}")
	return "\n".join(lineas).rstrip() + "\n"


def generar_teclas() -> str:
	lineas = [
		"# Lista de teclas de zCommander",
		"",
		"Estas son las teclas de fábrica, agrupadas por dónde funcionan.",
		"",
		"Las de la ventana principal y la línea de órdenes se pueden cambiar en Opciones, «Mapa de teclas», salvo "
		"Tab, Ctrl+H, F9, Mayús+F10 y Aplicaciones, que son fijas. Las de las demás ventanas y diálogos, y las de "
		"los complementos dentro de sus ventanas, son fijas.",
		"",
		"Si elige otro esquema de teclas (Opciones, Personalización, «Esquema de teclas»), algunas cambian. Los menús "
		"y la paleta de órdenes (Ctrl+E) dicen siempre la tecla que tiene cada orden ahora.",
		"",
	]
	grupos = {"panel": "Con el foco en un panel", "global": "En toda la ventana principal", "linea": "En la línea de órdenes"}
	for ambito, titulo in grupos.items():
		lineas += [f"## {titulo}", ""]
		for o in ordenes.CATALOGO:
			if o.ambito == ambito and o.teclas and o.manejador != "complementos_pl.ejecutar":
				lineas.append(f"- {_teclas(o)}: {_limpio(o.etiqueta)}. {o.ayuda}")
		lineas.append("")
	lineas += _teclas_de_ventanas()
	lineas += _teclas_de_complementos()
	return "\n".join(lineas).rstrip() + "\n"


# Ventanas con menús propios: sus teclas se leen del código (los menús con «\t»).
VENTANAS_CON_MENU = (
	("VentanaVisor", "En el visor (F3)"),
	("VentanaEditor", "En el editor (F4)"),
	("VisorAyuda", "En el visor de ayuda (F1)"),
)


def _visible(combinacion: str) -> str:
	return combinacion.replace("AvPág", "Av Pág").replace("RePág", "Re Pág")


def _teclas_de_ventanas() -> list[str]:
	"""Secciones de las ventanas y diálogos con teclas propias (no se cambian en el mapa de teclas)."""
	sys.path.insert(0, str(RAIZ / "tools"))
	import comprobar_teclas

	lineas: list[str] = []
	por_ventana: dict[str, dict[str, str]] = {}
	for atajo in comprobar_teclas.atajos_del_proyecto(RAIZ):
		por_ventana.setdefault(atajo.contexto, {}).setdefault(atajo.combinacion, atajo.descripcion)
	for clase, titulo in VENTANAS_CON_MENU:
		teclas_ventana = por_ventana.get(clase, {})
		if not teclas_ventana:
			continue
		lineas += [f"## {titulo}", ""]
		for combinacion, descripcion in sorted(teclas_ventana.items(), key=lambda par: _orden_tecla(par[0])):
			texto = _limpio(descripcion).rstrip(".").rstrip("…").rstrip(".")
			lineas.append(f"- {_visible(combinacion)}: {texto[:1].upper()}{texto[1:]}.")
		lineas.append("")
	from app.services.operaciones.modelo import AccionConflicto
	from app.ui.dialogos import conflictos

	nombres_conflicto = {
		AccionConflicto.SOBRESCRIBIR: "Sobrescribir", AccionConflicto.OMITIR: "Omitir",
		AccionConflicto.RENOMBRAR_COPIA: "Cambiar el nombre de la copia",
		AccionConflicto.RENOMBRAR_EXISTENTE: "Cambiar el nombre del que ya existe",
	}
	lineas += ["## En la lista de conflictos al copiar o mover", ""]
	for letra, accion in conflictos.TECLAS.items():
		lineas.append(f"- {letra}: {nombres_conflicto.get(accion, accion.name.capitalize())} en las filas elegidas.")
	lineas += ["", "## En el diálogo de copiar o mover (F5 y F6)", "",
		"- F2: En cola (la operación espera a que terminen las que usan las mismas unidades).", "",
		"## En la lista de sincronizar carpetas", "",
		"- D: Copiar a la derecha.", "- I: Copiar a la izquierda.", "- N: No hacer nada.",
		"- B: Borrar en el lado de destino (en los dos sentidos, borrar donde falta el otro).", ""]
	for titulo, lineas_ventana in TECLAS_VENTANAS_NUCLEO:
		lineas += [f"## {titulo}", "", *(f"- {linea}" for linea in lineas_ventana), ""]
	return lineas


def _teclas_de_complementos() -> list[str]:
	"""Un apartado por complemento de serie con las teclas de su manifiesto (2.0, 19.1)."""
	lineas: list[str] = []
	ambitos = {"panel": "con el foco en un panel", "global": "en toda la ventana principal"}
	for registrado in registro.complementos():
		con_tecla = [o for o in registro.ordenes() if o.complemento == registrado.id and o.teclas]
		ventanas = TECLAS_VENTANAS_COMPLEMENTOS.get(registrado.id, ())
		if not con_tecla and not ventanas:
			continue
		lineas += [f"## Complemento {registrado.nombre}", ""]
		for orden in con_tecla:
			visibles = ", ".join(teclas.nombre_visible(teclas.normalizar(t)) for t in orden.teclas)
			lineas.append(f"- {visibles}: {_limpio(orden.etiqueta)} ({ambitos.get(orden.ambito, orden.ambito)}). {orden.ayuda}")
		if not con_tecla:
			lineas.append("Sus órdenes no tienen tecla de fábrica: están en los menús y en la paleta de órdenes (Ctrl+E), "
				"y se les puede dar una en el mapa de teclas.")
		lineas.append("")
		for titulo, lineas_ventana in ventanas:
			lineas += [f"### {titulo}", "", *(f"- {linea}" for linea in lineas_ventana), ""]
	return lineas


def generar_sonidos() -> str:
	"""Mapa de sonidos (4.9): un apartado por categoría y los de cada complemento de serie."""
	lineas = [
		"# Mapa de sonidos de zCommander",
		"",
		"Generado con `python tools/generar_anexos.py` a partir de `app/services/sonidos/catalogo.py` y de los manifiestos "
		"de los complementos. Cada sonido se puede activar o desactivar en Preferencias, Sonidos; todo lo que suena se "
		"puede saber también de otra forma (anuncio, historial o consulta).",
		"",
	]
	from app.services.sonidos import paquetes as paquetes_sonidos

	lineas += ["## Paquetes de serie", "",
		"Se elige uno en Preferencias, Sonidos («Paquete:»). Todos tienen los mismos sonidos; cambia su carácter.", ""]
	for id_paquete in paquetes_sonidos.SERIE:
		try:
			datos = json.loads((RAIZ / "data" / "sounds" / id_paquete / "paquete.json").read_text(encoding="utf-8"))
		except (OSError, ValueError):
			datos = {}
		defecto = " Es el paquete por defecto." if id_paquete == paquetes_sonidos.BASE else ""
		lineas.append(f"- {datos.get('nombre', id_paquete)}: {str(datos.get('descripcion', '')).rstrip('.')}.{defecto}")
	lineas.append("")
	categorias: dict[str, list] = {}
	for evento in catalogo_sonidos.eventos():
		categorias.setdefault(evento.categoria, []).append(evento)
	for categoria, eventos in categorias.items():
		nombre = catalogo_sonidos.nombre_categoria(categoria)
		titulo = f"Complemento {nombre}" if categoria.startswith("plugin:") else nombre
		lineas += [f"## {titulo}", ""]
		for evento in eventos:
			cuando = evento.descripcion or "lo decide el complemento"
			defecto = "sí" if evento.por_defecto else "no"
			lineas.append(f"- {evento.nombre} (`{evento.id}`): {cuando.rstrip('.')}. Activo por defecto: {defecto}.")
		lineas.append("")
	return "\n".join(lineas).rstrip() + "\n"


def generar_componentes() -> str:
	"""Componentes de ``data/bin`` desde ``linea_base.json`` (2.0, 0.2)."""
	datos = json.loads((RAIZ / "data" / "bin" / "linea_base.json").read_text(encoding="utf-8"))
	lineas = [
		"# Anexo: componentes de data/bin",
		"",
		"Generado con `python tools/generar_anexos.py` a partir de `data/bin/linea_base.json`. No lo edite a mano.",
		"",
	]
	for ficha in datos.get("componentes", []):
		lineas += [f"## {ficha['nombre']} (`{ficha['id']}`)", "",
			f"- Versión de la línea base: {ficha['version']}. Licencia: {ficha['licencia']}. Lo usa: {ficha['dueno']}.",
			f"- Carpeta: `data/bin/{ficha['carpeta']}`. Actualizable: {'sí' if ficha.get('actualizable', True) else 'no'}."]
		if ficha.get("url_paquete_exacta"):
			lineas.append(f"- Origen: {ficha['url_paquete_exacta']} (SHA-256 `{ficha.get('sha256_paquete', '')}`).")
		for archivo in ficha.get("archivos", []):
			lineas.append(f"- `{archivo['ruta']}`: {archivo['tamano']} bytes, SHA-256 `{archivo['sha256']}`.")
		lineas.append("")
	return "\n".join(lineas).rstrip() + "\n"


def generar_serie() -> str:
	"""``app/plugins/serie.py``: id → versión de los complementos de serie (3.2)."""
	serie = {r.id: r.manifiesto.version for r in sorted(registro.complementos(), key=lambda r: r.id) if r.origen == "serie"}
	cuerpo = "".join(f'\t"{i}": "{v}",\n' for i, v in serie.items())
	return (
		"# SPDX-License-Identifier: GPL-3.0-or-later\n# Copyright (C) 2026 hxebolax y colaboradores\n"
		'"""Lista de los complementos de serie (diseño 2.0, 3.2). Sin wx.\n\n'
		"``SERIE`` lo GENERA ``tools/generar_anexos.py`` desde los manifiestos de\n"
		"``plugins/`` (no se edita a mano; ``test_anexos_al_dia`` comprueba que está al\n"
		"día). Un complemento de ``<raíz>/plugins/`` es «Oficial» sin firma solo si su\n"
		"id y su versión están aquí. ``SUMAS`` solo existe en la versión compilada\n"
		"(``serie_sumas.py``, que genera ``setup_cx.py``); desde el código fuente vale\n"
		"``None`` y los de serie no se comprueban.\n"
		'"""\n\n'
		"from __future__ import annotations\n\n"
		f"SERIE: dict[str, str] = {{\n{cuerpo}}}\n\n"
		"try:\n"
		"\tfrom app.plugins.serie_sumas import SUMAS  # type: ignore[import-not-found]\n"
		"except ImportError:\n"
		"\tSUMAS: dict[str, dict[str, str]] | None = None\n"
	)


def _orden_tecla(combinacion: str) -> tuple:
	"""F1 a F12 en su orden numérico; después el resto por orden alfabético."""
	ultima = combinacion.split("+")[-1]
	numero = int(ultima[1:]) if ultima.startswith("F") and ultima[1:].isdigit() else 99
	return (combinacion.count("+"), numero, combinacion)


SALIDAS = {
	RAIZ / "docs" / "ordenes.md": generar_ordenes,
	RAIZ / "docs" / "configuracion.md": generar_configuracion,
	RAIZ / "data" / "docs" / "teclas.md": generar_teclas,
	RAIZ / "data" / "docs" / "sonidos.md": generar_sonidos,
	RAIZ / "docs" / "componentes.md": generar_componentes,
	RAIZ / "app" / "plugins" / "serie.py": generar_serie,
}


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--comprobar", action="store_true", help="Falla si algún archivo no está al día.")
	opciones = analizador.parse_args(argumentos)
	desfasados = []
	for ruta, generar in SALIDAS.items():
		texto = generar()
		actual = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
		if actual != texto:
			if opciones.comprobar:
				desfasados.append(ruta)
			else:
				ruta.parent.mkdir(parents=True, exist_ok=True)
				ruta.write_text(texto, encoding="utf-8", newline="\n")
				print(f"Escrito {ruta.relative_to(RAIZ)}")
	if desfasados:
		print("Sin actualizar: " + ", ".join(str(r.relative_to(RAIZ)) for r in desfasados))
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
