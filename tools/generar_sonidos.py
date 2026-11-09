# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Genera los 5 paquetes de sonidos de serie por síntesis (diseño 2.0, 4.6 y 4.8).

Uso::

	python tools/generar_sonidos.py [--paquete <id>] [--complementos] [--comprobar] [--destino <carpeta>]

- Escribe ``data/sounds/<id>/`` con un WAV por evento del catálogo del núcleo
  (también las variantes de ``op.progreso``) y de los complementos de serie
  (``plugins/<id del complemento>/<nombre>.wav``), su ``paquete.json`` y
  ``LICENCIA.txt`` (CC0-1.0).
- ``--complementos`` escribe además la carpeta ``sonidos/`` de cada
  complemento de serie (``plugins/<carpeta>/sonidos/<nombre>.wav``) con el
  estilo del paquete ``clasico``.
- ``--comprobar`` regenera en una carpeta temporal y falla (código 1) si algún
  archivo difiere de lo guardado o falta o sobra alguno.

**Determinista**: solo biblioteca estándar (``math``, ``array``, ``wave`` y
``random.Random`` con una semilla fija por paquete y evento): misma entrada,
mismos bytes. WAV mono de 16 bits a 44 100 Hz.

Cada evento tiene su **receta** (``RECETAS``): familia de sonido, registro y
una secuencia de notas (semitonos y milisegundos) cuya dirección (sube, baja,
plano) sale de las notas. Las reglas que la persona oye en todos los paquetes:

- Los pares opuestos van en direcciones opuestas (marcar sube y desmarcar
  baja; entrar sube y subir de carpeta baja; conectar sube y desconectar baja;
  abrir sube y cerrar baja; reanudar sube y pausa baja).
- Los errores son graves y descendentes; los éxitos, ascendentes (terminar
  sube una tercera mayor; error baja una cuarta).
- La navegación es corta (150 ms como mucho) y aguda; los resultados duran
  600 ms como mucho y solo el arranque llega a 1,2 s.
- El progreso sube de tono con el porcentaje (10 % grave, 90 % agudo).
- Los sonidos de los complementos empiezan con un adorno agudo muy corto.

Cada paquete aplica su **estilo** a las mismas recetas (forma de onda,
envolvente, filtro, reverberación y transposición): ``clasico`` (triangular,
intervalos claros), ``suave`` (senos lentos y filtrados, 6 dB por debajo),
``retro`` (cuadradas y arpegios de 8 bits), ``minimalista`` (clics y golpes
de 5 a 40 ms) y ``cristal`` (campanas FM con una cola corta de reverberación).
Al final, cada sonido se iguala en sonoridad dentro de su paquete (RMS de
ventana de 30 ms) con el pico a −3 dBFS como máximo.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import math
import random
import shutil
import sys
import tempfile
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

from app.plugins import registro  # noqa: E402
from app.services.sonidos import catalogo, paquetes, wav  # noqa: E402
from app.services.sonidos.catalogo import BAJA, EventoSonido  # noqa: E402

VERSION = "1.0"
FRECUENCIA = 44100
PICO_MAXIMO = 10 ** (-3 / 20)
VENTANA_RMS_S = 0.03
AUTOR = "Proyecto zCommander"
DOS_PI = 2 * math.pi


def limite_ms(evento: EventoSonido) -> int:
	"""Duración máxima del evento (4.1): 150 ms los de prioridad baja, 1,2 s el arranque, 600 ms el resto."""
	if evento.id == "app.arranque":
		return 1200
	return 150 if evento.prioridad == BAJA else 600


# ── Recetas ──────────────────────────────────────────────────────────────────

TONO, RUIDO, GOLPE, PULSO = "tono", "ruido", "golpe", "pulso"


@dataclass(frozen=True)
class Nota:
	"""``semitono`` relativo al registro de la receta (``None`` es un silencio) y duración en ms."""

	semitono: float | None
	ms: float
	volumen: float = 1.0


@dataclass(frozen=True)
class Receta:
	familia: str
	registro: float
	notas: tuple[Nota, ...]
	adorno: bool = False

	@property
	def direccion(self) -> str:
		"""«sube», «baja» o «plano», de la primera a la última nota con tono."""
		tonos = [n.semitono for n in self.notas if n.semitono is not None]
		if len(tonos) < 2 or tonos[0] == tonos[-1]:
			return "plano"
		return "sube" if tonos[-1] > tonos[0] else "baja"

	@property
	def ms(self) -> float:
		return sum(n.ms for n in self.notas)


def R(familia: str, registro: float, notas: str, adorno: bool = False) -> Receta:  # noqa: N802 - constructor breve de la tabla
	"""``R(TONO, 12, "0/40 7/60 -/20 12/80*0.5")``: semitono/ms, «-» es silencio y ``*v`` el volumen."""
	resultado = []
	for ficha in notas.split():
		cuerpo, _asterisco, volumen = ficha.partition("*")
		tono, _barra, ms = cuerpo.partition("/")
		resultado.append(Nota(None if tono == "-" else float(tono), float(ms), float(volumen or 1)))
	return Receta(familia, registro, tuple(resultado), adorno)


#: Semitono de cada variante de ``op.progreso``: sube con el porcentaje y nunca se repite.
TONOS_PROGRESO = {"10": 0, "20": 2, "25": 3, "30": 4, "40": 5, "50": 7, "60": 9, "70": 11, "75": 12, "80": 14, "90": 16}

RECETAS: dict[str, Receta] = {
	# Sistema
	"app.arranque": R(TONO, 0, "-12/150 0/150 4/150 7/150 12/500"),
	"app.cierre": R(TONO, 0, "7/150 0/150 -5/300"),
	"app.sin_complementos": R(TONO, 0, "7/100 -/30 7/100 0/250"),
	# Navegación
	"nav.entrar": R(TONO, 7, "0/50 7/80"),
	"nav.subir": R(TONO, 7, "7/50 0/80"),
	"nav.raiz": R(TONO, 5, "12/50 0/80"),
	"nav.carpeta_vacia": R(TONO, 0, "3/90 -/30 0/160*0.9"),
	"nav.leyendo": R(PULSO, 7, "0/25 -/25 0/25 -/25 0/25"),
	"nav.historial": R(TONO, 14, "0/35 5/35 0/50"),
	"nav.unidad": R(TONO, 12, "-5/40 7/90"),
	"nav.entrar_comprimido": R(TONO, 7, "0/50 4/50 7/50 11/100"),
	"nav.salir_comprimido": R(TONO, 7, "11/40 7/40 0/60"),
	"nav.lista_resultados": R(TONO, 7, "0/60 7/60 0/60 7/100"),
	"nav.tope": R(GOLPE, 0, "0/60"),
	"nav.carpeta_desaparecida": R(TONO, 0, "7/100 6/100 0/250"),
	# Cursor
	"cursor.carpeta": R(TONO, 12, "0/50"),
	"cursor.archivo": R(TONO, 19, "0/35"),
	"cursor.comprimido": R(TONO, 12, "0/30 7/40"),
	"cursor.ejecutable": R(TONO, 16, "0/25 -/15 0/30"),
	"cursor.enlace": R(TONO, 14, "0/25 12/35"),
	"cursor.oculto": R(RUIDO, 24, "0/40*0.8"),
	"cursor.marcado": R(TONO, 24, "0/30 5/30"),
	"cursor.nube": R(RUIDO, 19, "0/30 5/40"),
	"cursor.superior": R(TONO, 12, "5/30 0/40"),
	# Marcas
	"marca.marcar": R(TONO, 14, "0/30 12/60"),
	"marca.desmarcar": R(TONO, 14, "12/30 0/60"),
	"marca.grupo": R(TONO, 12, "0/25 4/25 7/25 12/60"),
	"marca.quitar_todas": R(TONO, 12, "12/25 7/25 4/25 0/60"),
	"marca.invertir": R(TONO, 12, "7/35 0/35 7/35 0/35"),
	"marca.restaurar": R(TONO, 12, "0/30 4/30 0/70"),
	# Paneles, pestañas y vistas
	"panel.cambiar": R(RUIDO, 12, "0/35 7/45"),
	"panel.oculto": R(GOLPE, 0, "0/80 -/40 0/80"),
	"pestana.nueva": R(TONO, 12, "0/40 9/60"),
	"pestana.cerrar": R(TONO, 12, "9/40 0/60"),
	"pestana.cambiar": R(TONO, 16, "0/35 4/60"),
	"vista.cambiar": R(TONO, 21, "0/30 -2/50"),
	"filtro.aplicar": R(TONO, 10, "0/30 3/30 7/60"),
	"filtro.quitar": R(TONO, 10, "7/30 3/30 0/60"),
	"busqueda_rapida.sin_coincidencia": R(GOLPE, 5, "0/60 -/30 -1/80"),
	"busqueda_rapida.fin": R(TONO, 12, "4/40 0/60*0.8"),
	"orden.cambiar": R(TONO, 14, "0/30 2/30 4/30 5/50"),
	# Ventanas, diálogos y menús
	"dialogo.abrir": R(RUIDO, 0, "0/40 12/70"),
	"dialogo.cerrar": R(RUIDO, 0, "12/40 0/70"),
	"menu.abrir": R(TONO, 17, "0/30 5/60"),
	"menu.cerrar": R(TONO, 17, "5/30 0/60"),
	"paleta.abrir": R(TONO, 12, "0/25 7/25 12/25 19/50"),
	"ayuda_teclado.entrar": R(TONO, 3, "0/70 5/70 10/140"),
	"ayuda_teclado.salir": R(TONO, 3, "10/70 5/70 0/140"),
	"salida.mostrar": R(TONO, 9, "0/40 -/20 7/60"),
	"barra_botones.entrar": R(TONO, 14, "0/40 4/40 0/50"),
	# Avisos
	"aviso.error": R(TONO, -5, "5/150 0/300"),
	"aviso.advertencia": R(TONO, 0, "0/140 -/50 0/200"),
	"aviso.informacion": R(TONO, 12, "0/250"),
	"aviso.pregunta": R(TONO, 4, "0/120 2/120 7/220"),
	"aviso.no_disponible": R(GOLPE, -7, "0/90 -/40 0/120"),
	"aviso.sin_permiso": R(TONO, -3, "6/120 0/120 -6/250"),
	# Operaciones
	"op.inicio": R(TONO, 0, "-5/60 0/60 7/140"),
	"op.progreso": R(PULSO, 7, "0/40 -/20 7/40"),
	"op.pausa": R(TONO, 3, "7/80 -/30 0/160"),
	"op.reanudar": R(TONO, 3, "0/80 -/30 7/160"),
	"op.decision": R(PULSO, 9, "0/80 -/50 0/80 -/50 0/80"),
	"op.fin": R(TONO, 0, "0/150 4/350"),
	"op.fin_errores": R(TONO, 0, "0/130 4/130 1/300"),
	"op.cancelada": R(TONO, 0, "7/100 4/100 0/220"),
	"op.fallida": R(TONO, -5, "0/150 -1/150 -6/280"),
	"op.en_cola": R(PULSO, 14, "0/40 -/30 0/40"),
	"op.conflictos": R(TONO, 0, "0/90 6/90 0/90 6/150"),
	"op.deshacer": R(TONO, 5, "7/60 5/60 4/60 2/60 0/120"),
	"op.papelera": R(RUIDO, 0, "7/120 -5/200"),
	"op.eliminado": R(GOLPE, -12, "0/200"),
	"op.carpeta_creada": R(TONO, 7, "0/70 7/70 12/150"),
	"op.renombrado": R(TONO, 9, "4/70 0/70 4/150"),
	# Portapapeles
	"portapapeles.copiar": R(TONO, 9, "0/70 0/70 7/140"),
	"portapapeles.cortar": R(RUIDO, 19, "0/40 -/30 0/60"),
	"portapapeles.pegar": R(TONO, 9, "7/70 7/70 0/140"),
	"portapapeles.texto": R(TONO, 16, "0/60 4/100"),
	# Búsqueda y comparación
	"busqueda.inicio": R(RUIDO, 7, "0/50 7/90"),
	"busqueda.primer_resultado": R(TONO, 16, "0/40 7/60"),
	"busqueda.fin": R(TONO, 4, "0/100 4/100 7/100 12/200"),
	"busqueda.sin_resultados": R(TONO, 4, "7/120 3/250"),
	"comparar.iguales": R(TONO, 7, "0/140 -/30 0/220"),
	"comparar.diferencias": R(TONO, 7, "0/140 -/30 6/220"),
	"tamano.calculado": R(TONO, 2, "0/60 2/60 4/60 7/180"),
	# Línea de órdenes
	"linea.ejecutar": R(TONO, 14, "0/30 0/30 12/60"),
	"linea.fin": R(TONO, 7, "0/100 7/250"),
	"linea.error": R(TONO, -2, "3/120 0/280"),
	# Comprimidos
	"comprimido.probado": R(TONO, 5, "0/80 4/80 7/80 11/80 12/160"),
	"comprimido.danado": R(TONO, -3, "6/100 5/100 0/250"),
	"comprimido.contrasena": R(TONO, 3, "0/90 3/90 7/90 10/200"),
	"comprimido.cifrado_sin_motor": R(TONO, 3, "10/90 7/90 3/90 -2/200"),
	# Red
	"red.conectar": R(TONO, 0, "0/80 5/80 12/200"),
	"red.desconectar": R(TONO, 0, "12/80 5/80 0/200"),
	"red.perdida": R(TONO, -2, "12/80 6/80 0/80 -6/220"),
	"red.reconectada": R(TONO, -2, "0/70 6/70 12/220"),
	"red.equipo": R(TONO, 19, "0/40 4/60"),
	"red.descubrir_fin": R(TONO, 2, "0/80 7/80 4/80 12/200"),
	"red.credenciales": R(TONO, 5, "0/100 4/100 9/240"),
	"red.huella": R(TONO, 0, "0/80 8/80 0/80 8/200"),
	# Actualizaciones y componentes
	"act.disponible": R(TONO, 7, "0/100 4/100 7/100 9/250"),
	"act.descargada": R(TONO, 0, "0/90 7/90 12/90 16/220"),
	"act.instalada": R(TONO, 0, "0/90 4/90 7/90 12/90 16/200"),
	"act.revertida": R(TONO, 0, "12/100 7/100 4/100 0/240"),
	"act.al_dia": R(TONO, 7, "4/100 0/200*0.8"),
	"comp.disponible": R(TONO, 9, "0/90 5/90 9/220"),
	"comp.actualizado": R(TONO, 9, "0/80 5/80 9/80 12/200"),
	"comp.revertido": R(TONO, 9, "12/80 9/80 5/80 0/200"),
	# Complementos (núcleo)
	"plugin.instalado": R(TONO, 2, "0/70 7/70 9/70 14/200"),
	"plugin.activado": R(TONO, 14, "0/40 9/70"),
	"plugin.inhabilitado": R(TONO, 14, "9/40 0/70"),
	"plugin.fallo": R(TONO, -4, "0/100 -1/100 -2/260"),
	"plugin.cargando": R(PULSO, 10, "0/30 -/25 4/30 -/25 7/30"),
	# Copias, macros, reglas y personalización
	"copia.creada": R(TONO, 4, "0/90 4/90 9/220"),
	"copia.restaurada": R(TONO, 4, "9/90 4/90 0/220"),
	"macro.grabar": R(PULSO, 0, "0/60 -/40 0/60 -/40 12/150"),
	"macro.parar": R(PULSO, 0, "12/60 -/40 12/60 -/40 0/150"),
	"macro.paso": R(TONO, 21, "0/30"),
	"macro.fin": R(TONO, 5, "0/80 7/80 12/80 7/200"),
	"regla.a": R(TONO, 7, "0/60 0/60"),
	"regla.b": R(TONO, 7, "0/60 4/60"),
	"regla.c": R(TONO, 7, "0/60 7/60"),
	"espacio.abierto": R(TONO, 0, "0/80 2/80 7/80 14/200"),
	"tecla_global.recibida": R(TONO, 7, "0/60 12/60 0/60 12/120"),
}

#: Recetas de los sonidos de los complementos de serie por el nombre corto (tras «:»).
#: El registro de cada complemento se desplaza un poco según su id, para que dos
#: complementos con el mismo nombre de sonido no suenen igual.
RECETAS_COMPLEMENTOS: dict[str, Receta] = {
	"conectar": R(TONO, 2, "0/80 5/80 12/180", True),
	"conectado": R(TONO, 2, "0/80 7/80 12/180", True),
	"desconectar": R(TONO, 2, "12/80 5/80 0/180", True),
	"desconectado": R(TONO, 2, "12/80 7/80 0/180", True),
	"oauth_espera": R(PULSO, 9, "0/60 -/60 0/60 -/60 0/60", True),
	"oauth_ok": R(TONO, 5, "0/90 4/90 7/200", True),
	"sincronizacion_fin": R(TONO, 2, "0/70 4/70 7/70 12/200", True),
	"montada": R(TONO, -2, "0/90 7/220", True),
	"motor_detenido": R(TONO, -2, "7/100 0/100 -5/220", True),
	"fin": R(TONO, 7, "0/100 4/100 7/220", True),
	"tarea_fin": R(TONO, 4, "0/90 5/90 9/200", True),
	"guardado": R(TONO, 9, "0/80 7/200", True),
	"repositorio": R(TONO, 7, "0/60 3/60 7/150", True),
	"no_valido": R(GOLPE, -5, "0/80 -/40 0/100", True),
	"descripcion": R(TONO, 12, "0/80 9/200", True),
	"archivo_nuevo": R(TONO, 12, "0/50 12/90", True),
	"regla_aplicada": R(TONO, 10, "0/60 4/60 7/60", True),
	"nota_carpeta": R(TONO, 16, "0/70 5/70", True),
	"copia_externa": R(TONO, 14, "0/60 0/60 7/100", True),
	"cerrado": R(TONO, 5, "7/80 0/150", True),
	"pista": R(TONO, 12, "0/50 7/60", True),
	"fin_lista": R(TONO, 5, "7/80 4/80 0/200", True),
	"marcador": R(TONO, 19, "0/40 12/60", True),
	"sin_firma": R(TONO, 0, "0/100 6/200", True),
	"amenaza": R(TONO, -5, "0/90 -1/90 0/90 -1/200", True),
	"aviso_salud": R(TONO, -2, "0/100 6/100 0/200", True),
	"cambios_permitidos": R(TONO, 0, "0/90 6/90 12/200", True),
	"demostracion_iniciada": R(TONO, 7, "0/70 4/70 7/70 9/150", True),
	"otp": R(PULSO, 12, "0/50 -/30 4/50 -/30 7/50", True),
}

#: Desplazamiento de registro de cada complemento de serie (los que comparten nombres de sonido
#: quedan separados); un complemento que no está aquí lo saca de su id.
DESPLAZAMIENTO_COMPLEMENTO: dict[str, int] = {
	"zc.ocr": -2, "zc.voz": 3, "zc.programador": -1, "zc.synology": 2, "zc.nubes": 0,
}

#: Pares opuestos que deben ir en direcciones opuestas (los comprueban las pruebas).
PARES_OPUESTOS: tuple[tuple[str, str], ...] = (
	("marca.marcar", "marca.desmarcar"), ("marca.grupo", "marca.quitar_todas"), ("nav.entrar", "nav.subir"),
	("nav.entrar_comprimido", "nav.salir_comprimido"), ("red.conectar", "red.desconectar"),
	("dialogo.abrir", "dialogo.cerrar"), ("menu.abrir", "menu.cerrar"), ("pestana.nueva", "pestana.cerrar"),
	("op.reanudar", "op.pausa"), ("filtro.aplicar", "filtro.quitar"), ("ayuda_teclado.entrar", "ayuda_teclado.salir"),
	("plugin.activado", "plugin.inhabilitado"), ("comp.actualizado", "comp.revertido"), ("macro.grabar", "macro.parar"),
	("portapapeles.copiar", "portapapeles.pegar"), ("copia.creada", "copia.restaurada"),
	("comprimido.contrasena", "comprimido.cifrado_sin_motor"),
)


def _semilla(*partes: str) -> int:
	"""Entero estable (no depende de ``hash()`` ni del orden de generación)."""
	return int.from_bytes(hashlib.sha256("\0".join(partes).encode("utf-8")).digest()[:8], "big")


def receta(evento: EventoSonido, variante: str = "") -> Receta:
	"""La receta de un evento (con variante para ``op.progreso``)."""
	if evento.id == "op.progreso" and variante:
		return R(PULSO, 7, f"{TONOS_PROGRESO.get(variante, 0)}/60")
	if evento.id in RECETAS:
		return RECETAS[evento.id]
	if evento.es_de_complemento:
		complemento, nombre = evento.id.split(":", 1)
		desplazamiento = DESPLAZAMIENTO_COMPLEMENTO.get(complemento, _semilla(complemento) % 5 - 2)
		base = RECETAS_COMPLEMENTOS.get(nombre)
		if base is None:
			# Sonido nuevo de un complemento sin receta: dos o tres notas de una pentatónica, estables por su id.
			rng = random.Random(_semilla(evento.id))
			escala = (0, 2, 4, 7, 9, 12, 14)
			notas = " ".join(f"{rng.choice(escala)}/{rng.choice((70, 90, 110))}" for _ in range(rng.choice((2, 3))))
			base = R(TONO, rng.choice((0, 5, 7, 12)), notas, True)
		return Receta(base.familia, base.registro + desplazamiento, base.notas, True)
	raise KeyError(f"El evento {evento.id} no tiene receta en RECETAS")


# ── Síntesis ─────────────────────────────────────────────────────────────────


def frecuencia(semitono: float) -> float:
	return 440.0 * 2 ** (semitono / 12)


def _triangular(fase: float) -> float:
	return 1.0 - 4.0 * abs(fase - 0.5)


def _envolvente(i: int, total: int, ataque: int, liberacion: int, caida: float) -> float:
	"""Ataque lineal, caída exponencial (``caida`` = constante de tiempo en muestras) y liberación lineal."""
	if i < ataque:
		nivel = i / max(1, ataque)
	else:
		nivel = math.exp(-(i - ataque) / caida) if caida > 0 else 1.0
	resto = total - i
	if resto < liberacion:
		nivel *= resto / max(1, liberacion)
	return nivel


def _paso_bajo(muestras: list[float], corte: float) -> list[float]:
	"""Filtro de un polo (determinista)."""
	a = 1 - math.exp(-DOS_PI * corte / FRECUENCIA)
	salida, y = [], 0.0
	for x in muestras:
		y += a * (x - y)
		salida.append(y)
	return salida


def _paso_banda(muestras: list[float], centro: float, q: float = 2.0) -> list[float]:
	"""Filtro de variables de estado (salida de banda) para dar tono al ruido."""
	f = 2 * math.sin(math.pi * min(centro, FRECUENCIA / 6) / FRECUENCIA)
	amortiguamiento = 1 / q
	bajo = banda = 0.0
	salida = []
	for x in muestras:
		alto = x - bajo - amortiguamiento * banda
		banda += f * alto
		bajo += f * banda
		salida.append(banda)
	return salida


class Estilo:
	"""Cómo suena una receta en un paquete. Las subclases cambian la síntesis de cada familia."""

	id = ""
	nombre = ""
	descripcion = ""
	transponer = 0.0
	escala_tiempo = 1.0
	#: Sonoridad objetivo (RMS de ventana de 30 ms) en dBFS.
	objetivo_db = -18.0
	hueco_ms = 4.0

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		raise NotImplementedError  # cada estilo la define

	def posproceso(self, muestras: list[float], rng: random.Random) -> list[float]:
		return muestras

	def avance(self, ms: float) -> float:
		return ms * self.escala_tiempo

	def adorno(self, rng: random.Random) -> list[float]:
		"""Marca de complemento: un destello agudo de 18 ms."""
		return self.nota(TONO, frecuencia(31 + self.transponer), int(0.018 * FRECUENCIA), rng, False)

	def renderizar(self, receta_: Receta, limite: int, rng: random.Random) -> list[float]:
		eventos: list[tuple[int, list[float]]] = []
		cursor = 0.0
		if receta_.adorno:
			eventos.append((0, [m * 0.5 for m in self.adorno(rng)]))
			cursor += self.avance(24)
		con_tono = [i for i, n in enumerate(receta_.notas) if n.semitono is not None]
		for indice, nota in enumerate(receta_.notas):
			ms = self.avance(nota.ms)
			if nota.semitono is not None:
				f = frecuencia(receta_.registro + nota.semitono + self.transponer)
				n = int((ms - self.hueco_ms if ms > 2 * self.hueco_ms else ms) * FRECUENCIA / 1000)
				ultima = indice == con_tono[-1]
				muestras = [m * nota.volumen for m in self.nota(receta_.familia, f, n, rng, ultima)]
				eventos.append((int(cursor * FRECUENCIA / 1000), muestras))
			cursor += ms
		largo = max((inicio + len(m) for inicio, m in eventos), default=0)
		largo = min(largo, int(limite * FRECUENCIA / 1000))
		mezcla = [0.0] * largo
		for inicio, muestras in eventos:
			for i, valor in enumerate(muestras[: max(0, largo - inicio)]):
				mezcla[inicio + i] += valor
		mezcla = self.posproceso(mezcla, rng)[:largo]
		# Final sin chasquido: desvanecimiento de 6 ms (o menos en los muy cortos) y entrada de 0,3 ms.
		fundido = min(len(mezcla) // 4, int(0.006 * FRECUENCIA))
		for i in range(fundido):
			mezcla[-1 - i] *= i / fundido
		entrada = min(len(mezcla), int(0.0003 * FRECUENCIA))
		for i in range(entrada):
			mezcla[i] *= i / max(1, entrada)
		return mezcla


class Clasico(Estilo):
	id = "clasico"
	nombre = "Clásico"
	descripcion = "Tonos de onda triangular con intervalos claros: el éxito sube una tercera mayor y el error baja una cuarta."

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		if familia == RUIDO:
			ruido = [rng.uniform(-1, 1) for _ in range(n)]
			filtrado = _paso_banda(ruido, f * 2, 3.0)
			return [v * 2.2 * _envolvente(i, n, int(0.008 * FRECUENCIA), int(0.02 * FRECUENCIA), n * 0.6) for i, v in enumerate(filtrado)]
		if familia == GOLPE:
			n = max(n, int(0.05 * FRECUENCIA))
			salida, fase = [], 0.0
			for i in range(n):
				fase += f * (1 + 1.5 * math.exp(-i / (0.006 * FRECUENCIA))) / FRECUENCIA
				salida.append(math.sin(DOS_PI * fase) * _envolvente(i, n, 40, 200, 0.03 * FRECUENCIA))
			return salida
		ataque = int(0.004 * FRECUENCIA)
		caida = (0.25 if familia == PULSO else 0.9) * n if not ultima else 1.6 * n
		liberacion = int(min(0.02, n / FRECUENCIA / 3) * FRECUENCIA)
		paso = f / FRECUENCIA
		return [_triangular((i * paso) % 1.0) * _envolvente(i, n, ataque, liberacion, caida) for i in range(n)]


class Suave(Estilo):
	id = "suave"
	nombre = "Suave"
	descripcion = "Senos con ataque y caída lentos, filtrados y 6 dB por debajo: para quien usa sonidos todo el día."
	transponer = -5.0
	escala_tiempo = 1.1
	objetivo_db = -24.0
	hueco_ms = 0.0

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		cola = int(0.06 * FRECUENCIA)
		total = n + cola
		ataque = min(int(0.02 * FRECUENCIA), total // 3)
		liberacion = cola + n // 3
		if familia == RUIDO:
			ruido = _paso_bajo([rng.uniform(-1, 1) for _ in range(total)], f * 1.5)
			return [v * 3.0 * _envolvente(i, total, ataque, liberacion, 0) for i, v in enumerate(ruido)]
		paso = f / FRECUENCIA
		# Los graves llevan algo más de segundo armónico para oírse también en altavoces pequeños.
		armonico = 0.12 + 0.25 * min(1.0, max(0.0, (400 - f) / 200))
		salida = []
		for i in range(total):
			fase = DOS_PI * i * paso
			valor = math.sin(fase) + armonico * math.sin(2 * fase)
			salida.append(valor * _envolvente(i, total, ataque, liberacion, 0))
		return salida

	def posproceso(self, muestras: list[float], rng: random.Random) -> list[float]:
		return _paso_bajo(_paso_bajo(muestras, 2400), 2400)


class Retro(Estilo):
	id = "retro"
	nombre = "Retro 8 bits"
	descripcion = "Ondas cuadradas y arpegios rápidos cuantizados, al estilo de las consolas antiguas."
	objetivo_db = -20.0
	hueco_ms = 0.0
	TRAMA_MS = 1000 / 60

	def avance(self, ms: float) -> float:
		# Duraciones cuantizadas a tramas de 1/60 s, como las consolas de 8 bits.
		return max(1, round(ms / self.TRAMA_MS)) * self.TRAMA_MS

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		trama = int(self.TRAMA_MS * FRECUENCIA / 1000)
		salida = []
		if familia == RUIDO:
			# Ruido de registro de desplazamiento con muestra y retención (más agudo cuanto más alta la nota).
			retener = max(1, int(FRECUENCIA / (f * 4)))
			valor = 1.0
			for i in range(n):
				if i % retener == 0:
					valor = 1.0 if rng.random() < 0.5 else -1.0
				salida.append(valor * 0.6 * (1 - (i // trama) / max(1, n // trama + 1)))
			return salida
		ciclo = 0.25 if familia == PULSO else 0.5
		tramas = max(1, n // trama)
		fase = 0.0
		for i in range(n):
			t = i // trama
			if familia == GOLPE:
				actual = f * (2.0 if t == 0 else 1.0)
			else:
				# Arpegio rápido: en las notas largas, la octava en una trama de cada tres.
				actual = f * 2 if tramas >= 4 and t % 3 == 2 else f
			fase = (fase + actual / FRECUENCIA) % 1.0
			nivel = max(0.0, 1.0 - 0.6 * t / tramas) if not ultima else max(0.0, 1.0 - 0.8 * t / tramas)
			nivel = round(nivel * 15) / 15  # volumen en 16 escalones
			salida.append((0.5 if fase < ciclo else -0.5) * nivel)
		return salida

	def posproceso(self, muestras: list[float], rng: random.Random) -> list[float]:
		# Resolución reducida (6 bits) para el grano de 8 bits.
		return [round(m * 32) / 32 for m in muestras]


class Minimalista(Estilo):
	id = "minimalista"
	nombre = "Minimalista"
	descripcion = "Clics y golpes de 5 a 40 ms: lo mínimo para distinguir los eventos sin ocupar tiempo de voz."
	escala_tiempo = 0.45
	objetivo_db = -18.0
	hueco_ms = 0.0

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		largo = max(int(0.005 * FRECUENCIA), min(int(0.04 * FRECUENCIA), int(n * 0.8)))
		salida = []
		if familia in (RUIDO, PULSO):
			ruido = [rng.uniform(-1, 1) for _ in range(largo)]
			filtrado = _paso_banda(ruido, f * (2 if familia == RUIDO else 3), 4.0)
			tau = (0.004 if familia == RUIDO else 0.007) * FRECUENCIA
			return [v * 3.0 * math.exp(-i / tau) for i, v in enumerate(filtrado)]
		fase = 0.0
		tau = (0.008 if familia == GOLPE else 0.006) * FRECUENCIA
		for i in range(largo):
			caida = 1 + (1.2 if familia == GOLPE else 0.15) * math.exp(-i / (0.002 * FRECUENCIA))
			fase += f * caida / FRECUENCIA
			salida.append(math.sin(DOS_PI * fase) * math.exp(-i / tau))
		return salida

	def adorno(self, rng: random.Random) -> list[float]:
		return self.nota(TONO, frecuencia(31), int(0.006 * FRECUENCIA), rng, False)


class Cristal(Estilo):
	id = "cristal"
	nombre = "Cristal"
	descripcion = "Campanas por síntesis FM con parciales inarmónicos y una cola corta de reverberación."
	transponer = 5.0
	escala_tiempo = 0.9
	hueco_ms = 0.0

	def nota(self, familia: str, f: float, n: int, rng: random.Random, ultima: bool) -> list[float]:
		cola = int((0.25 if ultima else 0.12) * FRECUENCIA)
		total = n + cola
		salida = []
		if familia == RUIDO:
			ruido = _paso_banda([rng.uniform(-1, 1) for _ in range(total)], f * 2.5, 6.0)
			for i, v in enumerate(ruido):
				brillo = 0.5 + 0.5 * math.sin(DOS_PI * f * 1.5 * i / FRECUENCIA)
				salida.append(v * 2.5 * brillo * _envolvente(i, total, int(0.01 * FRECUENCIA), cola, total * 0.4))
			return salida
		razon = 3.5 if familia == GOLPE else 1.4
		tau = (0.05 if familia == GOLPE else 0.12 if familia == PULSO else 0.22) * FRECUENCIA
		for i in range(total):
			t = i / FRECUENCIA
			indice = 0.4 + 2.6 * math.exp(-i / (0.04 * FRECUENCIA))
			moduladora = math.sin(DOS_PI * f * razon * t)
			valor = math.sin(DOS_PI * f * t + indice * moduladora) + 0.25 * math.sin(DOS_PI * f * 2.76 * t) * math.exp(-i / (tau * 0.4))
			salida.append(valor * _envolvente(i, total, 60, int(0.01 * FRECUENCIA), tau))
		return salida

	def posproceso(self, muestras: list[float], rng: random.Random) -> list[float]:
		# Reverberación corta: tres filtros peine en paralelo y un paso todo.
		cola = int(0.12 * FRECUENCIA)
		entrada = muestras + [0.0] * cola
		humedo = [0.0] * len(entrada)
		for retardo_ms, realimentacion in ((23.0, 0.45), (29.7, 0.42), (37.1, 0.40)):
			d = int(retardo_ms * FRECUENCIA / 1000)
			buffer = [0.0] * len(entrada)
			for i, x in enumerate(entrada):
				buffer[i] = x + (realimentacion * buffer[i - d] if i >= d else 0.0)
				humedo[i] += buffer[i] / 3
		d = int(5.0 * FRECUENCIA / 1000)
		g = 0.5
		paso_todo = [0.0] * len(humedo)
		for i, x in enumerate(humedo):
			previo_x = humedo[i - d] if i >= d else 0.0
			previo_y = paso_todo[i - d] if i >= d else 0.0
			paso_todo[i] = -g * x + previo_x + g * previo_y
		return [seco + 0.3 * mojado for seco, mojado in zip(entrada, paso_todo, strict=True)]


ESTILOS: dict[str, Estilo] = {e.id: e for e in (Clasico(), Suave(), Retro(), Minimalista(), Cristal())}


# ── Sonoridad ────────────────────────────────────────────────────────────────


def sonoridad(muestras: list[float] | array) -> float:
	"""RMS máximo en ventanas de 30 ms (escala lineal, muestras en ±1 o en enteros de 16 bits)."""
	if not muestras:
		return 0.0
	ventana = min(len(muestras), int(VENTANA_RMS_S * FRECUENCIA))
	acumulado = [0.0]
	for m in muestras:
		acumulado.append(acumulado[-1] + float(m) * float(m))
	paso = max(1, int(0.005 * FRECUENCIA))
	mejor = 0.0
	for inicio in range(0, len(muestras) - ventana + 1, paso):
		mejor = max(mejor, acumulado[inicio + ventana] - acumulado[inicio])
	return math.sqrt(mejor / ventana)


def normalizar(muestras: list[float], objetivo_db: float) -> array:
	"""Iguala la sonoridad al objetivo con el pico a −3 dBFS como máximo y pasa a 16 bits."""
	pico = max((abs(m) for m in muestras), default=0.0)
	rms = sonoridad(muestras)
	if pico <= 0 or rms <= 0:
		return array("h", [0] * len(muestras))
	factor = min(10 ** (objetivo_db / 20) / rms, PICO_MAXIMO / pico)
	return array("h", (max(-32767, min(32767, round(m * factor * 32767))) for m in muestras))


# ── Generación ───────────────────────────────────────────────────────────────


def sintetizar(estilo: Estilo, evento: EventoSonido, variante: str = "") -> array:
	"""Muestras de 16 bits del evento en el estilo (deterministas)."""
	rng = random.Random(_semilla(estilo.id, evento.id, variante))
	muestras = estilo.renderizar(receta(evento, variante), limite_ms(evento), rng)
	return normalizar(muestras, estilo.objetivo_db)


def archivos_del_paquete() -> list[tuple[EventoSonido, str]]:
	"""Cada archivo de un paquete completo: los eventos del catálogo y las variantes de ``op.progreso``."""
	return paquetes.eventos_con_variantes()


def manifiesto(estilo: Estilo) -> dict:
	return {
		"formato": paquetes.FORMATO, "id": estilo.id, "nombre": estilo.nombre, "autor": AUTOR, "licencia": "CC0-1.0",
		"version": "1.0.0", "descripcion": estilo.descripcion, "hereda": None if estilo.id == paquetes.BASE else paquetes.BASE,
		"generado_por": f"tools/generar_sonidos.py {VERSION}", "archivos": {},
	}


TEXTO_LICENCIA = """Paquete de sonidos de zCommander: {nombre}

Generado por síntesis con tools/generar_sonidos.py {version} (Proyecto zCommander).

En la medida en que lo permite la ley, el Proyecto zCommander renuncia a todos
sus derechos de autor y derechos conexos sobre estos sonidos y los dedica al
dominio público con la licencia Creative Commons Zero 1.0 Universal (CC0-1.0):
puede copiarlos, modificarlos, distribuirlos y usarlos, también con fines
comerciales, sin pedir permiso.

Texto legal: https://creativecommons.org/publicdomain/zero/1.0/legalcode
"""


def generar_paquete(estilo: Estilo, destino: Path, avisar: Callable[[str], None] = print) -> int:
	"""Escribe el paquete completo del estilo en ``destino/<id>/``. Devuelve cuántos WAV escribió."""
	carpeta = destino / estilo.id
	if carpeta.exists():
		shutil.rmtree(carpeta)
	carpeta.mkdir(parents=True)
	contador = 0
	for evento, variante in archivos_del_paquete():
		wav.escribir(carpeta / evento.archivo_paquete(variante), sintetizar(estilo, evento, variante), FRECUENCIA)
		contador += 1
	(carpeta / paquetes.MANIFIESTO).write_text(json.dumps(manifiesto(estilo), ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")
	(carpeta / paquetes.LICENCIA).write_text(TEXTO_LICENCIA.format(nombre=estilo.nombre, version=VERSION), encoding="utf-8")
	avisar(f"{estilo.nombre}: {contador} sonidos en {carpeta}")
	return contador


def carpetas_complementos() -> dict[str, Path]:
	"""Carpeta de cada complemento de serie con sonidos (id → carpeta)."""
	return {r.id: Path(r.carpeta) for r in registro.complementos() if r.origen == "serie"}


def generar_complementos(raiz_plugins: Path | None = None, avisar: Callable[[str], None] = print) -> int:
	"""Escribe ``sonidos/`` de cada complemento de serie con el estilo clásico. Devuelve cuántos WAV."""
	carpetas = carpetas_complementos()
	estilo = ESTILOS[paquetes.BASE]
	contador = 0
	for evento in catalogo.eventos_de_complementos():
		complemento = evento.id.split(":", 1)[0]
		carpeta = carpetas.get(complemento)
		if carpeta is None:
			continue
		if raiz_plugins is not None:
			carpeta = raiz_plugins / carpeta.name
		wav.escribir(carpeta / (evento.archivo or f"sonidos/{evento.id.split(':', 1)[1]}.wav"), sintetizar(estilo, evento), FRECUENCIA)
		contador += 1
	avisar(f"Complementos de serie: {contador} sonidos")
	return contador


def _comparar(guardado: Path, nuevo: Path) -> list[str]:
	"""Diferencias entre dos carpetas (archivos que faltan, sobran o cambian)."""
	problemas = []
	viejos = {p.relative_to(guardado).as_posix() for p in guardado.rglob("*") if p.is_file()} if guardado.is_dir() else set()
	nuevos = {p.relative_to(nuevo).as_posix() for p in nuevo.rglob("*") if p.is_file()}
	problemas += [f"falta {guardado / r}" for r in sorted(nuevos - viejos)]
	problemas += [f"sobra {guardado / r}" for r in sorted(viejos - nuevos)]
	problemas += [f"cambia {guardado / r}" for r in sorted(nuevos & viejos) if not filecmp.cmp(guardado / r, nuevo / r, shallow=False)]
	return problemas


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--paquete", choices=sorted(ESTILOS), help="Genera solo este paquete.")
	analizador.add_argument("--complementos", action="store_true", help="Escribe también la carpeta sonidos/ de cada complemento de serie.")
	analizador.add_argument("--comprobar", action="store_true", help="Falla si algún archivo guardado no coincide con lo que se generaría.")
	analizador.add_argument("--destino", type=Path, default=RAIZ / "data" / "sounds", help="Carpeta de los paquetes (por defecto data/sounds).")
	opciones = analizador.parse_args(argumentos)
	if not registro.complementos():
		registro.registrar_serie(RAIZ / "plugins")
	elegidos = [ESTILOS[opciones.paquete]] if opciones.paquete else list(ESTILOS.values())
	if not opciones.comprobar:
		for estilo in elegidos:
			generar_paquete(estilo, opciones.destino)
		if opciones.complementos:
			generar_complementos()
		return 0
	problemas: list[str] = []
	with tempfile.TemporaryDirectory(prefix="zc-sonidos-") as temporal:
		temporal_ruta = Path(temporal)
		for estilo in elegidos:
			generar_paquete(estilo, temporal_ruta / "sounds", avisar=lambda _t: None)
			problemas += _comparar(opciones.destino / estilo.id, temporal_ruta / "sounds" / estilo.id)
		if opciones.complementos:
			generar_complementos(temporal_ruta / "plugins", avisar=lambda _t: None)
			for carpeta in sorted(carpetas_complementos().values()):
				if (temporal_ruta / "plugins" / carpeta.name / "sonidos").is_dir():
					problemas += _comparar(carpeta / "sonidos", temporal_ruta / "plugins" / carpeta.name / "sonidos")
	for problema in problemas:
		print(problema)
	print("Sonidos al día." if not problemas else f"{len(problemas)} diferencias: ejecute python tools/generar_sonidos.py")
	return 1 if problemas else 0


if __name__ == "__main__":
	sys.exit(main())
