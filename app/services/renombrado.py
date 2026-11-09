# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Motor del renombrado múltiple (Ctrl+M): máscaras, buscar y reemplazar, mayúsculas y vista previa.

Por qué es un módulo puro (sin wx y sin tocar el disco):

- La vista previa se recalcula cada vez que la persona deja de teclear y lo
  que ve tiene que ser EXACTAMENTE lo que luego se renombra: el diálogo y la
  orden usan las mismas funciones (``calcular`` y ``pares``).
- Las máscaras son las de Total Commander (``[N]``, ``[N2-5]``, ``[C10+5:3]``,
  ``[Y]``...), con reglas finas de tramos y contadores que hay que poder
  probar una a una sin abrir ventanas.

Orden de aplicación (sección 8.14 del diseño): máscaras, después buscar y
reemplazar, después mayúsculas. El renombrado en sí lo hace
``OperacionRenombrar`` del núcleo (cadenas y ciclos con temporales, deshacer).

Las plantillas (combinaciones de campos guardadas) viven en
``data/config/plantillas_renombrado.json`` con ``app.core.almacen_json``.
"""

from __future__ import annotations

import builtins
import logging
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields

from app.services import formato
from app.services.vfs import rutas

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Opciones ─────────────────────────────────────────────────────────────────

#: Modos de mayúsculas (identificador estable, se guarda en las plantillas).
MAYUSCULAS = ("sin_cambio", "minusculas", "mayusculas", "primera", "palabras")


def textos_mayusculas() -> list[str]:
	"""Etiquetas visibles de ``MAYUSCULAS``, en el mismo orden."""
	return [_("Sin cambio"), _("minúsculas"), _("MAYÚSCULAS"), _("Primera letra"), _("Cada Palabra")]


@dataclass(frozen=True)
class OpcionesRenombrado:
	"""Los campos del diálogo. Los nombres de los campos son también las claves de las plantillas."""

	mascara_nombre: str = "[N]"
	mascara_extension: str = "[E]"
	buscar: str = ""
	reemplazar: str = ""
	regex: bool = False
	distinguir_mayusculas: bool = False
	solo_primera: bool = False
	aplicar_extension: bool = False
	mayusculas_nombre: str = "sin_cambio"
	mayusculas_extension: str = "sin_cambio"
	contador_inicio: int = 1
	contador_paso: int = 1
	contador_digitos: int = 1

	def campos(self) -> dict:
		return asdict(self)

	@classmethod
	def desde_campos(cls, campos: Mapping) -> OpcionesRenombrado:
		"""Tolerante: ignora claves desconocidas y vuelve al valor por defecto si el tipo no cuadra.

		Por qué: una plantilla guardada a mano o por una versión anterior no debe
		impedir abrir el diálogo.
		"""
		por_defecto = cls()
		valores = {}
		for campo in fields(cls):
			if campo.name not in campos:
				continue
			valor = campos[campo.name]
			defecto = getattr(por_defecto, campo.name)
			if isinstance(defecto, bool):
				if isinstance(valor, bool):
					valores[campo.name] = valor
			elif isinstance(defecto, int):
				if isinstance(valor, int) and not isinstance(valor, bool):
					valores[campo.name] = valor
			elif isinstance(valor, str):
				if campo.name.startswith("mayusculas_") and valor not in MAYUSCULAS:
					continue
				valores[campo.name] = valor
		return cls(**valores)


class ErrorMascara(ValueError):
	"""Máscara o expresión regular que no se puede interpretar; el mensaje dice qué falla."""


# ── Elementos ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Elemento:
	"""Lo que el motor necesita saber de cada elemento (sin depender del proveedor).

	:param ruta: ruta completa en su proveedor (se devuelve en ``pares``).
	:param nombre: nombre actual con extensión.
	:param carpeta_ruta: carpeta que lo contiene (para detectar duplicados en la misma carpeta).
	:param carpeta: nombre de esa carpeta (``[P]``).
	:param superior: nombre de la carpeta de encima (``[G]``).
	:param modificado: fecha de modificación (``[Y]``, ``[M]``, ``[D]``...).
	"""

	ruta: str
	nombre: str
	es_carpeta: bool = False
	carpeta_ruta: str = ""
	carpeta: str = ""
	superior: str = ""
	modificado: float = 0.0
	#: 2.0 (3.5): la ``Entrada`` y su proveedor, para las máscaras de los complementos ([EXIF:fecha]...).
	entrada: object = field(default=None, compare=False)
	proveedor: object = field(default=None, compare=False)


def _partes_ruta(ruta: str) -> list[str]:
	return [p for p in re.split(r"[\\/]", ruta) if p]


def elementos_desde_entradas(entradas: Iterable, proveedor) -> list[Elemento]:
	"""Convierte las ``Entrada`` del panel en ``Elemento``.

	La carpeta se pide al proveedor; en listas de resultados (``padre`` da
	``None``) se usa ``ruta_real``, que es la carpeta real de cada archivo.
	"""
	resultado: list[Elemento] = []
	for entrada in entradas:
		if getattr(entrada, "es_superior", False):
			continue
		padre = proveedor.padre(entrada.ruta) if proveedor is not None else None
		if padre is None:
			padre = getattr(entrada, "ruta_real", "") or ""
		partes = _partes_ruta(padre)
		resultado.append(Elemento(
			ruta=entrada.ruta, nombre=entrada.nombre, es_carpeta=entrada.es_carpeta, carpeta_ruta=padre,
			carpeta=partes[-1] if partes else "", superior=partes[-2] if len(partes) > 1 else "",
			modificado=entrada.modificado, entrada=entrada, proveedor=proveedor,
		))
	return resultado


def partir(nombre: str, es_carpeta: bool = False) -> tuple[str, str]:
	"""(nombre sin extensión, extensión sin punto) conservando las mayúsculas originales.

	«.gitignore» no tiene extensión; las carpetas tampoco (como en la lista de archivos).
	"""
	if es_carpeta:
		return nombre, ""
	punto = nombre.rfind(".")
	if punto <= 0:
		return nombre, ""
	return nombre[:punto], nombre[punto + 1:]


def unir(nombre: str, extension: str) -> str:
	return f"{nombre}.{extension}" if extension else nombre


# ── Máscaras ─────────────────────────────────────────────────────────────────

_TRAMO = re.compile(r"^(-?\d+)?(?:(-)(-?\d+)?|,(\d+))?$")
_CONTADOR = re.compile(r"^(-?\d+)?(?:\+(-?\d+))?(?::(\d+))?$")
_FECHAS = {"Y", "y", "M", "D", "h", "m", "s", "d", "t"}
_CASOS = {"U": "mayusculas", "L": "minusculas", "F": "palabras", "n": "sin_cambio"}


@dataclass(frozen=True)
class _Tramo:
	desde: int | None = None
	guion: bool = False
	hasta: int | None = None
	cuantos: int | None = None

	def aplicar(self, texto: str) -> str:
		"""Posiciones desde 1; las negativas cuentan desde el final (−1 es el último carácter)."""
		if self.desde is None and not self.guion and self.cuantos is None:
			return texto
		n = len(texto)

		def indice(posicion: int) -> int:
			if posicion > 0:
				return posicion - 1
			if posicion < 0:
				return n + posicion
			return 0

		inicio = indice(self.desde) if self.desde is not None else 0
		if self.cuantos is not None:
			fin = inicio + self.cuantos
		elif self.guion:
			fin = n if self.hasta is None else indice(self.hasta) + 1
		else:
			fin = inicio + 1
		inicio, fin = max(0, inicio), min(n, fin)
		return texto[inicio:fin] if fin > inicio else ""


@dataclass(frozen=True)
class _Pieza:
	"""Un trozo de máscara ya interpretado."""

	clase: str  # texto, nombre, extension, carpeta, superior, contador, fecha, caso
	texto: str = ""
	tramo: _Tramo = _Tramo()
	inicio: int | None = None
	paso: int | None = None
	digitos: int | None = None


def _interpretar_tramo(resto: str, original: str) -> _Tramo:
	coincidencia = _TRAMO.match(resto)
	if not coincidencia:
		raise ErrorMascara(_("Tramo no válido en [{m}]: use por ejemplo [N2-5], [N2,5], [N-3,3] o [N3-].").format(m=original))
	desde, guion, hasta, cuantos = coincidencia.groups()
	return _Tramo(
		desde=int(desde) if desde is not None else None, guion=bool(guion),
		hasta=int(hasta) if hasta is not None else None, cuantos=int(cuantos) if cuantos is not None else None,
	)


_MASCARA_COMPLEMENTO = re.compile(r"^[A-Z][A-Z0-9_]+:[^\]\s]+$")
#: Lo que se muestra mientras el complemento de una máscara se activa (vista previa en la interfaz).
PENDIENTE = "…"


def _valor_complemento(marcador: str, elemento: Elemento) -> str:
	"""Valor de una máscara de complemento; activa el complemento si hace falta (3.4).

	En un hilo de trabajo espera su activación; en el hilo de la interfaz nunca
	bloquea: pide la activación y devuelve «…» hasta la siguiente vista previa.
	"""
	import threading

	from app.plugins import cargador, registro
	from app.plugins import estado as estado_complementos

	registrada = registro.funcion("mascara", marcador)
	if registrada is None:
		dueno = next((r.id for r in registro.complementos()
			if any(m.get("marcador") == marcador for m in r.manifiesto.tabla("mascaras"))), None)
		if dueno is None:
			raise ErrorMascara(_("Marcador desconocido: {m}.").format(m=marcador))
		futuro = cargador.asegurar_activo(dueno)
		if threading.current_thread() is threading.main_thread():
			return PENDIENTE
		try:
			futuro.result(cargador.TIEMPO_CARGA_S)
		except Exception:  # noqa: BLE001 - sin el complemento, la máscara queda vacía
			log.debug("No se activó %s para la máscara %s", dueno, marcador, exc_info=True)
		registrada = registro.funcion("mascara", marcador)
		if registrada is None:
			return ""
	id_complemento, funcion = registrada
	if elemento.entrada is None:
		return ""
	valor = estado_complementos.llamar_protegido(id_complemento, funcion, elemento.entrada, elemento.proveedor)
	return "" if valor is None else str(valor)


def _interpretar(contenido: str) -> _Pieza:
	if not contenido:
		raise ErrorMascara(_("Hay unos corchetes vacíos []. Para escribir un corchete use [[ o ]]."))
	if _MASCARA_COMPLEMENTO.match(contenido):
		# 2.0 (3.3, 3.5): marcador de un complemento con prefijo propio, como [EXIF:fecha] o [MP3:artista].
		return _Pieza("complemento", texto=f"[{contenido}]")
	letra, resto = contenido[0], contenido[1:]
	if letra in ("N", "E", "P", "G"):
		clase = {"N": "nombre", "E": "extension", "P": "carpeta", "G": "superior"}[letra]
		return _Pieza(clase, tramo=_interpretar_tramo(resto, contenido))
	if letra == "C":
		coincidencia = _CONTADOR.match(resto)
		if not coincidencia:
			raise ErrorMascara(_("Contador no válido en [{m}]: use por ejemplo [C], [C10+5:3] (inicio 10, paso 5, 3 cifras).").format(m=contenido))
		inicio, paso, digitos = coincidencia.groups()
		return _Pieza("contador", inicio=int(inicio) if inicio is not None else None,
			paso=int(paso) if paso is not None else None, digitos=int(digitos) if digitos is not None else None)
	if not resto and letra in _FECHAS:
		return _Pieza("fecha", texto=letra)
	if not resto and letra in _CASOS:
		return _Pieza("caso", texto=_CASOS[letra])
	raise ErrorMascara(_("Marcador desconocido: [{m}].").format(m=contenido))


def compilar(mascara: str) -> list[_Pieza]:
	"""Interpreta una máscara una sola vez (luego se evalúa para cada elemento).

	:raises ErrorMascara: con la explicación de lo que falla.
	"""
	piezas: list[_Pieza] = []
	literal: list[str] = []

	def volcar() -> None:
		if literal:
			piezas.append(_Pieza("texto", texto="".join(literal)))
			literal.clear()

	i = 0
	while i < len(mascara):
		caracter = mascara[i]
		if caracter == "[":
			if mascara.startswith("[[", i):
				literal.append("[")
				i += 2
				continue
			fin = mascara.find("]", i + 1)
			if fin < 0:
				raise ErrorMascara(_("Falta el corchete de cierre «]». Para escribir un corchete use [[."))
			volcar()
			piezas.append(_interpretar(mascara[i + 1:fin]))
			i = fin + 1
		elif caracter == "]":
			if mascara.startswith("]]", i):
				literal.append("]")
				i += 2
				continue
			raise ErrorMascara(_("Hay un «]» sin su «[». Para escribir un corchete use ]]."))
		else:
			literal.append(caracter)
			i += 1
	volcar()
	return piezas


def _fecha(letra: str, marca: float) -> str:
	try:
		t = time.localtime(marca if marca > 0 else 0)
	except (OverflowError, OSError, ValueError):
		log.debug("Fecha fuera de rango para la máscara: %s", marca, exc_info=True)
		t = time.localtime(0)
	return {
		"Y": f"{t.tm_year:04d}", "y": f"{t.tm_year % 100:02d}", "M": f"{t.tm_mon:02d}", "D": f"{t.tm_mday:02d}",
		"h": f"{t.tm_hour:02d}", "m": f"{t.tm_min:02d}", "s": f"{t.tm_sec:02d}",
		"d": f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}", "t": f"{t.tm_hour:02d}.{t.tm_min:02d}.{t.tm_sec:02d}",
	}[letra]


def _contador(valor: int, digitos: int) -> str:
	digitos = max(1, digitos)
	return f"-{abs(valor):0{digitos}d}" if valor < 0 else f"{valor:0{digitos}d}"


def cambiar_mayusculas(texto: str, modo: str) -> str:
	"""Aplica uno de los modos de ``MAYUSCULAS``."""
	if modo == "minusculas":
		return texto.lower()
	if modo == "mayusculas":
		return texto.upper()
	if modo == "primera":
		bajo = texto.lower()
		for i, caracter in enumerate(bajo):
			if caracter.isalpha():
				return bajo[:i] + caracter.upper() + bajo[i + 1:]
		return bajo
	if modo == "palabras":
		resultado = []
		anterior_alfanumerico = False
		for caracter in texto.lower():
			resultado.append(caracter.upper() if caracter.isalpha() and not anterior_alfanumerico else caracter)
			# Las comillas simples no cortan la palabra («l'arbre» → «L'arbre»).
			anterior_alfanumerico = caracter.isalnum() or (caracter == "'" and anterior_alfanumerico)
		return "".join(resultado)
	return texto


def evaluar(piezas: Sequence[_Pieza], elemento: Elemento, indice: int, opciones: OpcionesRenombrado) -> str:
	"""Texto que da la máscara para ``elemento`` (``indice`` es su posición en el lote, desde 0)."""
	nombre, extension = partir(elemento.nombre, elemento.es_carpeta)
	trozos: list[tuple[str, str]] = []  # (modo de mayúsculas, texto)
	modo = "sin_cambio"
	for pieza in piezas:
		if pieza.clase == "caso":
			modo = pieza.texto
			continue
		if pieza.clase == "texto":
			valor = pieza.texto
		elif pieza.clase == "nombre":
			valor = pieza.tramo.aplicar(nombre)
		elif pieza.clase == "extension":
			valor = pieza.tramo.aplicar(extension)
		elif pieza.clase == "carpeta":
			valor = pieza.tramo.aplicar(elemento.carpeta)
		elif pieza.clase == "superior":
			valor = pieza.tramo.aplicar(elemento.superior)
		elif pieza.clase == "complemento":
			valor = _valor_complemento(pieza.texto, elemento)
		elif pieza.clase == "contador":
			inicio = opciones.contador_inicio if pieza.inicio is None else pieza.inicio
			paso = opciones.contador_paso if pieza.paso is None else pieza.paso
			digitos = opciones.contador_digitos if pieza.digitos is None else pieza.digitos
			valor = _contador(inicio + indice * paso, digitos)
		else:
			valor = _fecha(pieza.texto, elemento.modificado)
		if trozos and trozos[-1][0] == modo:
			trozos[-1] = (modo, trozos[-1][1] + valor)
		else:
			trozos.append((modo, valor))
	return "".join(cambiar_mayusculas(texto, modo_trozo) for modo_trozo, texto in trozos)


# ── Buscar y reemplazar ──────────────────────────────────────────────────────


class _Reemplazo:
	"""Buscar y reemplazar compilado una vez para todo el lote."""

	def __init__(self, opciones: OpcionesRenombrado) -> None:
		self.activo = bool(opciones.buscar)
		self.cuenta = 1 if opciones.solo_primera else 0
		banderas = 0 if opciones.distinguir_mayusculas else re.IGNORECASE
		self._mapa: dict[str, str] = {}
		self._regex = opciones.regex
		if not self.activo:
			return
		if opciones.regex:
			try:
				self._patron = re.compile(opciones.buscar, banderas)
			except re.error as error:
				raise ErrorMascara(_("Expresión regular no válida: {e}").format(e=error)) from error
			# Se admite también la forma $1 de Total Commander.
			self._sustituto = re.sub(r"\$(\d+)", r"\\g<\1>", opciones.reemplazar)
			return
		# Varios pares con «|»: se sustituyen a la vez, así «a|b» por «b|a» los intercambia.
		buscados = opciones.buscar.split("|")
		reemplazos = opciones.reemplazar.split("|")
		pares: list[tuple[str, str]] = []
		for posicion, buscado in enumerate(buscados):
			if not buscado:
				continue
			if len(reemplazos) == 1:
				reemplazo = reemplazos[0]
			else:
				reemplazo = reemplazos[posicion] if posicion < len(reemplazos) else ""
			pares.append((buscado, reemplazo))
		if not pares:
			self.activo = False
			return
		self._distinguir = opciones.distinguir_mayusculas
		for buscado, reemplazo in pares:
			self._mapa.setdefault(buscado if self._distinguir else buscado.casefold(), reemplazo)
		# Los más largos primero para que «ab|a» no se quede en «a».
		ordenados = sorted({b for b, _r in pares}, key=len, reverse=True)
		self._patron = re.compile("|".join(re.escape(b) for b in ordenados), banderas)

	def aplicar(self, texto: str) -> str:
		if not self.activo:
			return texto
		if self._regex:
			try:
				return self._patron.sub(self._sustituto, texto, count=self.cuenta)
			except (re.error, IndexError) as error:
				raise ErrorMascara(_("El texto de reemplazo no es válido: {e}").format(e=error)) from error

		def sustituir(coincidencia: re.Match) -> str:
			clave = coincidencia.group(0) if self._distinguir else coincidencia.group(0).casefold()
			return self._mapa.get(clave, coincidencia.group(0))

		return self._patron.sub(sustituir, texto, count=self.cuenta)


# ── Cálculo de la vista previa ───────────────────────────────────────────────

SIN_CAMBIOS = "sin_cambios"
CORRECTO = "correcto"
DUPLICADO = "duplicado"
YA_EXISTE = "ya_existe"
NO_VALIDO = "no_valido"
ERROR = "error"
#: Estados que impiden renombrar el lote.
MALOS = frozenset({DUPLICADO, YA_EXISTE, NO_VALIDO, ERROR})


@dataclass(frozen=True)
class Resultado:
	"""Una fila de la vista previa."""

	ruta: str
	actual: str
	nuevo: str
	estado: str
	texto: str


@dataclass(frozen=True)
class Calculo:
	resultados: list[Resultado]
	error: str | None = None

	@property
	def hay_problemas(self) -> bool:
		return self.error is not None or any(r.estado in MALOS for r in self.resultados)

	def primera_mala(self) -> int:
		"""Índice de la primera fila que impide renombrar, o −1."""
		for indice, resultado in enumerate(self.resultados):
			if resultado.estado in MALOS:
				return indice
		return -1


def motivo_no_valido(nombre: str, validar_windows: bool = True) -> str | None:
	"""Texto corto para la columna Estado («Nombre no válido: carácter :»), o ``None`` si vale."""
	if validar_windows:
		for caracter in nombre:
			if caracter in rutas.CARACTERES_PROHIBIDOS:
				return _("Nombre no válido: carácter {c}").format(c=caracter)
		problema = rutas.problema_en_nombre(nombre)
	elif not nombre.strip():
		problema = _("El nombre no puede estar vacío.")
	elif "/" in nombre or "\\" in nombre:
		problema = _("El nombre no puede contener barras.")
	else:
		problema = None
	if problema is None:
		return None
	return _("Nombre no válido: {p}").format(p=problema.rstrip(".")[:1].lower() + problema.rstrip(".")[1:])


def nombre_nuevo(elemento: Elemento, indice: int, opciones: OpcionesRenombrado,
		piezas_nombre: Sequence[_Pieza], piezas_extension: Sequence[_Pieza], reemplazo: _Reemplazo) -> str:
	"""Nombre final de un elemento: máscaras, buscar y reemplazar, mayúsculas."""
	nombre = evaluar(piezas_nombre, elemento, indice, opciones)
	extension = evaluar(piezas_extension, elemento, indice, opciones)
	if opciones.aplicar_extension:
		completo = reemplazo.aplicar(unir(nombre, extension))
		punto = completo.rfind(".")
		nombre, extension = (completo[:punto], completo[punto + 1:]) if punto > 0 else (completo, "")
	else:
		nombre = reemplazo.aplicar(nombre)
	nombre = cambiar_mayusculas(nombre, opciones.mayusculas_nombre)
	extension = cambiar_mayusculas(extension, opciones.mayusculas_extension)
	return unir(nombre, extension)


def calcular(elementos: Sequence[Elemento], opciones: OpcionesRenombrado,
		existentes: Mapping[str, Iterable[str]] | None = None, validar_windows: bool = True) -> Calculo:
	"""Vista previa del lote: nombre nuevo y estado de cada elemento, en el mismo orden.

	:param existentes: nombres que ya hay en cada carpeta (clave: ``carpeta_ruta``
		de los elementos, sin distinguir mayúsculas). Un nombre nuevo que choca con
		uno de ellos que NO se renombra en el lote da «Ya existe».
	:param validar_windows: comprobar las reglas de nombres de Windows (disco
		local); en servidores y comprimidos solo se rechazan vacíos y barras.
	"""
	try:
		piezas_nombre = compilar(opciones.mascara_nombre)
		piezas_extension = compilar(opciones.mascara_extension)
		reemplazo = _Reemplazo(opciones)
		nuevos = [nombre_nuevo(e, i, opciones, piezas_nombre, piezas_extension, reemplazo) for i, e in enumerate(elementos)]
	except ErrorMascara as error:
		texto = _("Máscara no válida")
		return Calculo([Resultado(e.ruta, e.nombre, e.nombre, ERROR, texto) for e in elementos], str(error))

	# Nombres finales por carpeta (los que no cambian conservan el suyo) para detectar duplicados.
	cuenta: dict[tuple[str, str], int] = {}
	actuales: dict[str, set[str]] = {}
	for elemento, nuevo in zip(elementos, nuevos, strict=True):
		carpeta = elemento.carpeta_ruta.casefold()
		clave = (carpeta, nuevo.casefold())
		cuenta[clave] = cuenta.get(clave, 0) + 1
		actuales.setdefault(carpeta, set()).add(elemento.nombre.casefold())
	ocupados: dict[str, set[str]] = {}
	for carpeta, nombres in (existentes or {}).items():
		ocupados[carpeta.casefold()] = {n.casefold() for n in nombres}

	resultados: list[Resultado] = []
	for elemento, nuevo in zip(elementos, nuevos, strict=True):
		carpeta = elemento.carpeta_ruta.casefold()
		if nuevo == elemento.nombre:
			resultados.append(Resultado(elemento.ruta, elemento.nombre, nuevo, SIN_CAMBIOS, _("Sin cambios")))
			continue
		motivo = motivo_no_valido(nuevo, validar_windows)
		if motivo:
			resultados.append(Resultado(elemento.ruta, elemento.nombre, nuevo, NO_VALIDO, motivo))
		elif cuenta[(carpeta, nuevo.casefold())] > 1:
			resultados.append(Resultado(elemento.ruta, elemento.nombre, nuevo, DUPLICADO, _("Duplicado")))
		elif nuevo.casefold() in ocupados.get(carpeta, set()) and nuevo.casefold() not in actuales.get(carpeta, set()):
			resultados.append(Resultado(elemento.ruta, elemento.nombre, nuevo, YA_EXISTE, _("Ya existe en la carpeta")))
		else:
			resultados.append(Resultado(elemento.ruta, elemento.nombre, nuevo, CORRECTO, _("Correcto")))
	return Calculo(resultados)


def pares(calculo: Calculo) -> list[tuple[str, str]]:
	"""(ruta actual, nombre nuevo) de las filas «Correcto», para ``OperacionRenombrar``."""
	return [(r.ruta, r.nuevo) for r in calculo.resultados if r.estado == CORRECTO]


def resumen(calculo: Calculo) -> str:
	"""Una frase para el campo Resumen: «3 se renombran, 1 sin cambios, 1 duplicado»."""
	if calculo.error:
		return _("Máscara no válida: {e}").format(e=calculo.error)
	if not calculo.resultados:
		return _("No hay elementos")
	cuentas = {estado: 0 for estado in (CORRECTO, SIN_CAMBIOS, DUPLICADO, YA_EXISTE, NO_VALIDO)}
	for resultado in calculo.resultados:
		cuentas[resultado.estado] = cuentas.get(resultado.estado, 0) + 1
	partes = [formato.plural(cuentas[CORRECTO], _("{n} se renombra"), _("{n} se renombran"))]
	if cuentas[SIN_CAMBIOS]:
		partes.append(formato.plural(cuentas[SIN_CAMBIOS], _("{n} sin cambios"), _("{n} sin cambios")))
	if cuentas[DUPLICADO]:
		partes.append(formato.plural(cuentas[DUPLICADO], _("{n} duplicado"), _("{n} duplicados")))
	if cuentas[YA_EXISTE]:
		partes.append(formato.plural(cuentas[YA_EXISTE], _("{n} ya existe"), _("{n} ya existen")))
	if cuentas[NO_VALIDO]:
		partes.append(formato.plural(cuentas[NO_VALIDO], _("{n} nombre no válido"), _("{n} nombres no válidos")))
	return ", ".join(partes)


#: Marcadores que ofrece el botón «Insertar marcador» (texto, descripción).
def marcadores() -> list[tuple[str, str]]:
	return [
		("[N]", _("Nombre sin extensión")),
		("[N1]", _("Primer carácter del nombre")),
		("[N2-5]", _("Caracteres del 2 al 5 del nombre")),
		("[N2,5]", _("Cinco caracteres del nombre desde el 2")),
		("[N-3,3]", _("Tres caracteres del nombre desde el antepenúltimo")),
		("[N3-]", _("Nombre desde el carácter 3 hasta el final")),
		("[E]", _("Extensión")),
		("[P]", _("Carpeta que contiene el archivo")),
		("[G]", _("Carpeta de encima de esa")),
		("[C]", _("Contador con los valores de los campos")),
		("[C10+5:3]", _("Contador: inicio 10, paso 5, 3 cifras")),
		("[Y]", _("Año de cuatro cifras")),
		("[y]", _("Año de dos cifras")),
		("[M]", _("Mes")),
		("[D]", _("Día")),
		("[h]", _("Hora")),
		("[m]", _("Minutos")),
		("[s]", _("Segundos")),
		("[d]", _("Fecha AAAA-MM-DD")),
		("[t]", _("Hora hh.mm.ss")),
		("[U]", _("Lo que sigue en mayúsculas")),
		("[L]", _("Lo que sigue en minúsculas")),
		("[F]", _("Lo que sigue con la primera letra de cada palabra en mayúscula")),
		("[n]", _("Lo que sigue sin cambio de mayúsculas")),
		("[[", _("Corchete de apertura literal")),
		("]]", _("Corchete de cierre literal")),
		*marcadores_complementos(),
	]


def marcadores_complementos() -> list[tuple[str, str]]:
	"""Máscaras de los complementos (``[[mascaras]]`` de sus manifiestos, sin activarlos; 3.5)."""
	try:
		from app.plugins import registro

		return registro.mascaras_declaradas()
	except Exception:  # noqa: BLE001 - un manifiesto raro no deja sin el menú de marcadores
		log.warning("No se pudieron leer las máscaras de los complementos", exc_info=True)
		return []


# ── Plantillas ───────────────────────────────────────────────────────────────

ARCHIVO_PLANTILLAS = "plantillas_renombrado.json"


def leer_plantillas() -> list[dict]:
	"""Plantillas guardadas ``[{"nombre": ..., "campos": {...}}]``; las mal formadas se descartan."""
	from app.core import almacen_json

	datos = almacen_json.leer(ARCHIVO_PLANTILLAS, {"version": 1, "plantillas": []})
	plantillas = []
	for plantilla in datos.get("plantillas", []) if isinstance(datos, dict) else []:
		if isinstance(plantilla, dict) and isinstance(plantilla.get("nombre"), str) and isinstance(plantilla.get("campos"), dict):
			plantillas.append({"nombre": plantilla["nombre"], "campos": plantilla["campos"]})
		else:
			log.warning("Plantilla de renombrado descartada por mal formada: %r", plantilla)
	return plantillas


def _escribir_plantillas(plantillas: list[dict]) -> None:
	from app.core import almacen_json

	almacen_json.escribir(ARCHIVO_PLANTILLAS, {"version": 1, "plantillas": plantillas})


def guardar_plantilla(nombre: str, campos: Mapping) -> None:
	"""Guarda (o sustituye, sin distinguir mayúsculas) una plantilla. Lanza ``OSError`` si no puede escribir."""
	nombre = nombre.strip()
	if not nombre:
		raise ValueError(_("La plantilla necesita un nombre."))
	plantillas = [p for p in leer_plantillas() if p["nombre"].casefold() != nombre.casefold()]
	plantillas.append({"nombre": nombre, "campos": dict(campos)})
	plantillas.sort(key=lambda p: p["nombre"].casefold())
	_escribir_plantillas(plantillas)


def borrar_plantilla(nombre: str) -> bool:
	"""Borra la plantilla; devuelve ``False`` si no existía."""
	plantillas = leer_plantillas()
	restantes = [p for p in plantillas if p["nombre"].casefold() != nombre.casefold()]
	if len(restantes) == len(plantillas):
		return False
	_escribir_plantillas(restantes)
	return True


def recargar() -> None:
	"""Vuelve a leer su archivo tras restaurar una copia (2.0, 14.4): se lee en cada uso, así que solo avisa."""
	from app.services import recarga

	recarga.avisar(__name__)
