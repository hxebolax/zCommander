# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paquetes de sonidos (diseño 2.0, 4.5 a 4.7). Sin wx.

Un **paquete de sonidos** es una carpeta con un ``paquete.json`` (el manifiesto
de 4.6) y un ``.wav`` por evento, con el nombre que da
``EventoSonido.archivo_paquete`` (``nav_carpeta_vacia.wav``,
``op_progreso_30.wav``, ``plugins/zc.nubes/conectar.wav``):

- **De serie**: ``data/sounds/<id>/`` (los genera ``tools/generar_sonidos.py``,
  viajan con zCommander y los actualiza el actualizador de la aplicación).
- **Propios**: ``data/sounds_usuario/<id>/`` (de la persona; nunca se
  distribuyen ni se tocan al actualizar).

Un sonido que falta en un paquete sale de su cadena ``hereda``, después de
``clasico`` y, si es de un complemento, del ``sonidos/`` de su paquete de
complemento (4.4). Aquí están también la exportación e importación de
``.zcsonidos`` (un ZIP con el contenido de la carpeta en la raíz), el borrador
con el que trabaja el asistente (``Borrador``), la migración de los WAV
sueltos de la 1.x (``migrar_1x``) y las líneas de «Información para soporte».
"""

from __future__ import annotations

import builtins
import json
import logging
import os
import re
import shutil
import stat
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.sonidos import catalogo, wav
from app.services.sonidos.catalogo import EventoSonido

log = logging.getLogger(__name__)

#: Los 5 paquetes de serie, en el orden en que se ofrecen (4.6).
SERIE: tuple[str, ...] = ("clasico", "suave", "retro", "minimalista", "cristal")
#: Paquete por defecto y base de toda herencia.
BASE = "clasico"
FORMATO = 1
MANIFIESTO = "paquete.json"
LICENCIA = "LICENCIA.txt"
#: Licencias que ofrece el asistente (además de «Otra»).
LICENCIAS: tuple[str, ...] = ("CC0-1.0", "CC-BY-4.0", "GPL-3.0-or-later")
EXTENSION = ".zcsonidos"
#: Límites de un ``.zcsonidos`` (4.6).
MAX_EXPANDIDO = 50 * 1024 * 1024
MAX_MIEMBROS = 2000
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9_]{0,39}$")
#: Los WAV sueltos de la 1.x y los eventos a los que pasan (4.5).
WAV_1X: dict[str, tuple[str, ...]] = {
	"operacion_terminada.wav": ("op.fin",),
	"operacion_error.wav": ("op.fin_errores", "op.fallida"),
	"carpeta_vacia.wav": ("nav.carpeta_vacia",),
}
ID_1X = "mis_sonidos_1x"


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


class ErrorPaquete(Exception):
	"""Paquete no válido o imposible de guardar; ``mensaje`` lo explica en español."""

	def __init__(self, mensaje: str) -> None:
		super().__init__(mensaje)
		self.mensaje = mensaje


class PaqueteExiste(ErrorPaquete):
	"""Al importar: ya hay un paquete propio con ese id (la interfaz pregunta si se sustituye)."""

	def __init__(self, id_paquete: str, nombre: str) -> None:
		super().__init__(_("Ya tiene un paquete propio llamado «{n}» ({i}).").format(n=nombre, i=id_paquete))
		self.id = id_paquete
		self.nombre = nombre


# ── Carpetas (las pruebas las sustituyen) ────────────────────────────────────


def carpeta_serie() -> Path:
	"""``data/sounds``: paquetes de serie."""
	from app.core import paths

	return paths.ruta_sonidos()


def carpeta_propios() -> Path:
	"""``data/sounds_usuario``: paquetes propios."""
	from app.core import paths

	return paths.ruta_sonidos_usuario()


# ── Manifiesto ───────────────────────────────────────────────────────────────


@dataclass
class Paquete:
	"""Un paquete de sonidos instalado (lo que dice su ``paquete.json`` y dónde está)."""

	id: str
	nombre: str
	carpeta: Path
	de_serie: bool
	autor: str = ""
	licencia: str = ""
	version: str = "1.0.0"
	descripcion: str = ""
	hereda: str | None = BASE
	generado_por: str = ""
	archivos: dict[str, str] = field(default_factory=dict)

	@property
	def etiqueta(self) -> str:
		"""Texto del desplegable: «Clásico, de serie» o «Mi paquete, propio»."""
		return (_("{n}, de serie") if self.de_serie else _("{n}, propio")).format(n=self.nombre)

	def nombre_archivo(self, evento: EventoSonido, variante: str = "") -> str:
		"""Nombre relativo del ``.wav`` del evento en ESTE paquete (respeta ``archivos``)."""
		if not variante and evento.id in self.archivos:
			return self.archivos[evento.id]
		return evento.archivo_paquete(variante)

	def archivo_propio(self, evento: EventoSonido, variante: str = "") -> Path | None:
		"""El ``.wav`` del evento si este paquete lo trae (sin herencia)."""
		ruta = self.carpeta / self.nombre_archivo(evento, variante)
		return ruta if ruta.is_file() else None

	def a_dict(self) -> dict[str, Any]:
		datos: dict[str, Any] = {
			"formato": FORMATO, "id": self.id, "nombre": self.nombre, "autor": self.autor, "licencia": self.licencia,
			"version": self.version, "descripcion": self.descripcion, "hereda": self.hereda,
		}
		if self.generado_por:
			datos["generado_por"] = self.generado_por
		datos["archivos"] = dict(sorted(self.archivos.items()))
		return datos


def problema_en_archivo(nombre: str) -> str | None:
	"""Nombre relativo de un ``.wav`` dentro de un paquete: ``x.wav`` o ``plugins/<id>/x.wav``."""
	from app.services.vfs import rutas

	partes = PurePosixPath(nombre.replace("\\", "/")).parts
	if not partes or not nombre.lower().endswith(".wav"):
		return _("«{n}» no es un archivo .wav.").format(n=nombre)
	if len(partes) not in (1, 3) or (len(partes) == 3 and partes[0] != "plugins"):
		return _("«{n}» no está en la raíz del paquete ni en plugins/<complemento>/.").format(n=nombre)
	for parte in partes:
		motivo = rutas.problema_en_nombre(parte)
		if motivo:
			return motivo
	return None


def validar_manifiesto(datos: Any) -> list[str]:
	"""Problemas de un ``paquete.json`` (vacía si vale), en español."""
	if not isinstance(datos, dict):
		return [_("El paquete.json no es un objeto JSON.")]
	problemas = []
	if datos.get("formato") != FORMATO:
		problemas.append(_("Formato de paquete no admitido: {f}.").format(f=datos.get("formato")))
	if not isinstance(datos.get("id"), str) or not _ID_VALIDO.match(datos["id"]):
		problemas.append(_("El identificador debe tener de 1 a 40 letras minúsculas sin tilde, números o guiones bajos."))
	if not isinstance(datos.get("nombre"), str) or not datos["nombre"].strip():
		problemas.append(_("Falta el nombre del paquete."))
	for clave in ("autor", "licencia", "version", "descripcion", "generado_por"):
		if clave in datos and not isinstance(datos[clave], str):
			problemas.append(_("El campo «{c}» debe ser un texto.").format(c=clave))
	hereda = datos.get("hereda")
	if hereda is not None and (not isinstance(hereda, str) or not _ID_VALIDO.match(hereda)):
		problemas.append(_("El campo «hereda» no es un identificador de paquete."))
	archivos = datos.get("archivos", {})
	if not isinstance(archivos, dict):
		problemas.append(_("El campo «archivos» debe ser un objeto."))
	else:
		for clave, valor in archivos.items():
			motivo = problema_en_archivo(valor) if isinstance(valor, str) else _("no es un texto")
			if motivo:
				problemas.append(_("Archivo de «{e}»: {m}").format(e=clave, m=motivo))
	return problemas


def leer(carpeta: Path, de_serie: bool) -> Paquete:
	"""Lee el ``paquete.json`` de ``carpeta``. Lanza ``ErrorPaquete`` si no vale."""
	ruta = Path(carpeta) / MANIFIESTO
	try:
		datos = json.loads(ruta.read_text(encoding="utf-8"))
	except FileNotFoundError:
		raise ErrorPaquete(_("La carpeta {c} no tiene paquete.json.").format(c=carpeta)) from None
	except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
		raise ErrorPaquete(_("No se puede leer {r}: {e}").format(r=ruta, e=error)) from None
	problemas = validar_manifiesto(datos)
	if problemas:
		raise ErrorPaquete("; ".join(problemas))
	hereda = datos.get("hereda", None if datos["id"] == BASE else BASE)
	return Paquete(
		id=datos["id"], nombre=datos["nombre"].strip(), carpeta=Path(carpeta), de_serie=de_serie,
		autor=datos.get("autor", ""), licencia=datos.get("licencia", ""), version=datos.get("version", "1.0.0"),
		descripcion=datos.get("descripcion", ""), hereda=None if hereda == datos["id"] else hereda,
		generado_por=datos.get("generado_por", ""), archivos=dict(datos.get("archivos", {})),
	)


def escribir_manifiesto(paquete: Paquete) -> None:
	"""Escribe ``paquete.json`` de forma atómica (temporal y ``os.replace``)."""
	paquete.carpeta.mkdir(parents=True, exist_ok=True)
	destino = paquete.carpeta / MANIFIESTO
	temporal = destino.with_suffix(".json.tmp")
	temporal.write_text(json.dumps(paquete.a_dict(), ensure_ascii=False, indent="\t") + "\n", encoding="utf-8")
	os.replace(temporal, destino)


# ── Paquetes instalados y herencia ───────────────────────────────────────────


def _leer_carpeta(raiz: Path, de_serie: bool) -> list[Paquete]:
	paquetes = []
	try:
		hijas = sorted(p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith("."))
	except OSError:
		return []
	for carpeta in hijas:
		try:
			paquete = leer(carpeta, de_serie)
		except ErrorPaquete as error:
			log.warning("Paquete de sonidos no válido en %s: %s", carpeta, error.mensaje)
			continue
		if paquete.id != carpeta.name:
			log.warning("El paquete de %s dice ser «%s»; se usa el nombre de la carpeta", carpeta, paquete.id)
			paquete.id = carpeta.name
		paquetes.append(paquete)
	return paquetes


def listar() -> list[Paquete]:
	"""Paquetes instalados: los de serie (en el orden de ``SERIE``) y después los propios por nombre.

	Un propio con el id de uno de serie no se lista (no podría elegirse).
	"""
	serie = _leer_carpeta(carpeta_serie(), True)
	orden = {id_: i for i, id_ in enumerate(SERIE)}
	serie.sort(key=lambda p: (orden.get(p.id, len(orden)), p.nombre.casefold()))
	ids_serie = {p.id for p in serie} | set(SERIE)
	propios = [p for p in _leer_carpeta(carpeta_propios(), False) if p.id not in ids_serie]
	propios.sort(key=lambda p: p.nombre.casefold())
	return serie + propios


def obtener(id_paquete: str) -> Paquete | None:
	"""El paquete instalado con ese id (los de serie mandan sobre los propios)."""
	if not id_paquete or not _ID_VALIDO.match(id_paquete):
		return None
	for raiz, de_serie in ((carpeta_serie(), True), (carpeta_propios(), False)):
		carpeta = raiz / id_paquete
		if (carpeta / MANIFIESTO).is_file():
			try:
				paquete = leer(carpeta, de_serie)
			except ErrorPaquete as error:
				log.warning("Paquete de sonidos no válido en %s: %s", carpeta, error.mensaje)
				continue
			paquete.id = id_paquete
			return paquete
		if de_serie and id_paquete in SERIE:
			# Un id de serie nunca se busca entre los propios.
			return None
	return None


def cadena(id_paquete: str) -> list[Paquete]:
	"""El paquete, su cadena ``hereda`` y ``clasico`` al final, sin repetir ni ciclos."""
	resultado: list[Paquete] = []
	vistos: set[str] = set()
	siguiente: str | None = id_paquete
	while siguiente and siguiente not in vistos and len(resultado) < 12:
		vistos.add(siguiente)
		paquete = obtener(siguiente)
		if paquete is None:
			break
		resultado.append(paquete)
		siguiente = paquete.hereda
	if BASE not in vistos:
		base = obtener(BASE)
		if base is not None:
			resultado.append(base)
	return resultado


def archivo_de_complemento(evento: EventoSonido) -> Path | None:
	"""El ``.wav`` que trae el paquete del propio complemento (``sonidos/<nombre>.wav`` o su ``archivo``)."""
	if not evento.es_de_complemento:
		return None
	try:
		from app.plugins import registro

		registrado = registro.complemento(evento.id.split(":", 1)[0])
	except Exception:  # noqa: BLE001 - sin registro de complementos no hay sonido del complemento
		log.debug("No se pudo consultar el complemento de %s", evento.id, exc_info=True)
		return None
	if registrado is None:
		return None
	ruta = Path(registrado.carpeta) / (evento.archivo or f"sonidos/{evento.id.split(':', 1)[1]}.wav")
	return ruta if ruta.is_file() else None


def resolver_en(paquetes: list[Paquete], evento: EventoSonido, variante: str = "") -> Path | None:
	"""Primer archivo del evento en la lista de paquetes (la variante y, si falta, el evento sin variante)."""
	for intento in ((variante, "") if variante else ("",)):
		for paquete in paquetes:
			ruta = paquete.archivo_propio(evento, intento)
			if ruta is not None:
				return ruta
	return archivo_de_complemento(evento)


def resolver(evento: EventoSonido, variante: str = "", id_paquete: str = BASE) -> Path | None:
	"""Archivo que suena para ``evento`` con el paquete elegido (4.4): paquete → hereda → clásico → complemento."""
	return resolver_en(cadena(id_paquete), evento, variante)


def origen(evento: EventoSonido, id_paquete: str, variante: str = "") -> str:
	"""«Propio», «Heredado de Clásico», «Del complemento» o «Sin sonido» (columna Origen del asistente)."""
	paquetes = cadena(id_paquete)
	return describir_origen(paquetes[0] if paquetes and paquetes[0].id == id_paquete else None, paquetes, evento, variante)


def describir_origen(propio: Paquete | None, paquetes: list[Paquete], evento: EventoSonido, variante: str = "") -> str:
	if propio is not None and propio.archivo_propio(evento, variante) is not None:
		return _("Propio")
	for paquete in paquetes:
		if paquete is not propio and paquete.archivo_propio(evento, variante) is not None:
			return _("Heredado de {n}").format(n=paquete.nombre)
	if archivo_de_complemento(evento) is not None:
		return _("Del complemento")
	return _("Sin sonido")


def eventos_con_variantes() -> list[tuple[EventoSonido, str]]:
	"""Cada archivo que puede tener un paquete: (evento, variante); ``op.progreso`` con y sin variante."""
	resultado = []
	for evento in catalogo.eventos():
		resultado.append((evento, ""))
		resultado.extend((evento, v) for v in evento.variantes)
	return resultado


def contar(paquete: Paquete) -> tuple[int, int]:
	"""(sonidos propios, sonidos heredados) del paquete sobre el catálogo actual."""
	propios = heredados = 0
	for evento, variante in eventos_con_variantes():
		if paquete.archivo_propio(evento, variante) is not None:
			propios += 1
		else:
			heredados += 1
	return propios, heredados


# ── Identificadores ──────────────────────────────────────────────────────────


def proponer_id(nombre: str) -> str:
	"""Identificador propuesto desde el nombre: «Mis Sonidos 1» → ``mis_sonidos_1``."""
	sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii").lower()
	base = re.sub(r"[^a-z0-9]+", "_", sin_tildes).strip("_")[:40] or "mi_paquete"
	if not base[0].isalnum():
		base = "p" + base
	return base


def problema_id(id_paquete: str, editando: str | None = None) -> str | None:
	"""Por qué un id no vale para un paquete propio nuevo (o ``None``)."""
	if not _ID_VALIDO.match(id_paquete or ""):
		return _("El identificador debe tener de 1 a 40 letras minúsculas sin tilde, números o guiones bajos, y empezar por letra o número.")
	if id_paquete in SERIE or (carpeta_serie() / id_paquete / MANIFIESTO).is_file():
		return _("«{i}» es el identificador de un paquete de serie; elija otro.").format(i=id_paquete)
	if id_paquete != editando and (carpeta_propios() / id_paquete).exists():
		return _("Ya hay un paquete propio con el identificador «{i}».").format(i=id_paquete)
	return None


# ── Borrador del asistente (4.7) ─────────────────────────────────────────────


@dataclass
class Borrador:
	"""Lo que el asistente va preparando; nada se escribe hasta ``guardar``.

	:param base: paquete del que parte (paso 1).
	:param editando: el paquete propio que se edita (``None`` si es nuevo).
	:param cambios: archivo relativo → WAV nuevo (``Path``) o ``None`` (volver al heredado).
	"""

	base: Paquete
	editando: Paquete | None = None
	id: str = ""
	nombre: str = ""
	autor: str = ""
	licencia: str = "CC0-1.0"
	descripcion: str = ""
	cambios: dict[str, Path | None] = field(default_factory=dict)

	@classmethod
	def nuevo(cls, base: Paquete) -> Borrador:
		return cls(base=base, nombre=_("Mi paquete"), id=proponer_id(_("Mi paquete")), licencia=base.licencia or "CC0-1.0")

	@classmethod
	def editar(cls, paquete: Paquete) -> Borrador:
		return cls(base=paquete, editando=paquete, id=paquete.id, nombre=paquete.nombre, autor=paquete.autor,
			licencia=paquete.licencia, descripcion=paquete.descripcion)

	@property
	def hereda(self) -> str:
		"""De dónde sale lo que falta: el ``hereda`` del que se edita o se copia; el propio base si es de serie."""
		if self.editando is not None:
			return self.editando.hereda or BASE
		return self.base.id if self.base.de_serie else (self.base.hereda or BASE)

	@property
	def copia(self) -> Paquete | None:
		"""Paquete propio cuyos archivos se copian al guardar (nuevo a partir de un propio)."""
		if self.editando is not None:
			return self.editando
		return None if self.base.de_serie else self.base

	def _herencia(self) -> list[Paquete]:
		return cadena(self.hereda)

	def propio(self, evento: EventoSonido, variante: str = "") -> Path | None:
		"""WAV propio del borrador para el evento (cambiado, o del paquete que se edita o se copia)."""
		copia = self.copia
		nombre = copia.nombre_archivo(evento, variante) if copia else evento.archivo_paquete(variante)
		if nombre in self.cambios:
			return self.cambios[nombre]
		if evento.archivo_paquete(variante) in self.cambios:
			return self.cambios[evento.archivo_paquete(variante)]
		return copia.archivo_propio(evento, variante) if copia else None

	def ruta(self, evento: EventoSonido, variante: str = "") -> Path | None:
		"""Lo que sonaría con el borrador (botón «Probar»)."""
		return self.propio(evento, variante) or self.heredado(evento, variante)

	def heredado(self, evento: EventoSonido, variante: str = "") -> Path | None:
		"""Lo que sonaría sin el sonido propio (botón «Probar el original»)."""
		return resolver_en(self._herencia(), evento, variante)

	def origen(self, evento: EventoSonido, variante: str = "") -> str:
		if self.propio(evento, variante) is not None:
			return _("Propio")
		return describir_origen(None, self._herencia(), evento, variante)

	def sustituir(self, evento: EventoSonido, variante: str, ruta_wav: Path) -> None:
		"""Usa ``ruta_wav`` para el evento. Lanza ``wav.WavNoValido`` si el archivo no vale."""
		wav.leer(Path(ruta_wav))
		self.cambios[evento.archivo_paquete(variante)] = Path(ruta_wav)

	def volver_al_heredado(self, evento: EventoSonido, variante: str = "") -> None:
		copia = self.copia
		self.cambios[evento.archivo_paquete(variante)] = None
		if copia is not None and copia.nombre_archivo(evento, variante) != evento.archivo_paquete(variante):
			self.cambios[copia.nombre_archivo(evento, variante)] = None

	def contar(self) -> tuple[int, int]:
		"""(propios, heredados) con los cambios del borrador."""
		propios = sum(1 for e, v in eventos_con_variantes() if self.propio(e, v) is not None)
		return propios, len(eventos_con_variantes()) - propios

	def problemas(self) -> list[str]:
		problemas = []
		if not self.nombre.strip():
			problemas.append(_("Escriba un nombre para el paquete."))
		motivo = problema_id(self.id, self.editando.id if self.editando else None)
		if motivo:
			problemas.append(motivo)
		return problemas


def guardar(borrador: Borrador) -> Paquete:
	"""Crea o actualiza el paquete propio del borrador en ``data/sounds_usuario/<id>/``."""
	problemas = borrador.problemas()
	if problemas:
		raise ErrorPaquete(" ".join(problemas))
	destino = carpeta_propios() / borrador.id
	copia = borrador.copia
	archivos: dict[str, str] = {}
	try:
		destino.mkdir(parents=True, exist_ok=True)
		if copia is not None and copia.carpeta.resolve() != destino.resolve():
			for origen_wav in sorted(copia.carpeta.rglob("*.wav")):
				relativo = origen_wav.relative_to(copia.carpeta)
				(destino / relativo).parent.mkdir(parents=True, exist_ok=True)
				shutil.copyfile(origen_wav, destino / relativo)
		if copia is not None:
			archivos = dict(copia.archivos)
		for relativo, nuevo in sorted(borrador.cambios.items(), key=lambda par: par[0]):
			objetivo = destino / relativo
			for evento_id in [e for e, a in archivos.items() if a == relativo]:
				archivos.pop(evento_id)
			if nuevo is None:
				if objetivo.is_file() and not any(a == relativo for a in archivos.values()):
					objetivo.unlink()
			else:
				objetivo.parent.mkdir(parents=True, exist_ok=True)
				if Path(nuevo).resolve() != objetivo.resolve():
					shutil.copyfile(nuevo, objetivo)
		paquete = Paquete(
			id=borrador.id, nombre=borrador.nombre.strip(), carpeta=destino, de_serie=False, autor=borrador.autor.strip(),
			licencia=borrador.licencia.strip(), version=borrador.editando.version if borrador.editando else "1.0.0",
			descripcion=borrador.descripcion.strip(), hereda=borrador.hereda, archivos=archivos,
		)
		escribir_manifiesto(paquete)
	except OSError as error:
		raise ErrorPaquete(_("No se pudo guardar el paquete: {e}").format(e=error.strerror or error)) from None
	log.info("Paquete de sonidos guardado: %s (%s)", paquete.nombre, paquete.id)
	return paquete


def eliminar(id_paquete: str) -> None:
	"""Borra un paquete propio (los de serie no se pueden borrar)."""
	paquete = obtener(id_paquete)
	if paquete is None or paquete.de_serie:
		raise ErrorPaquete(_("Solo se pueden eliminar los paquetes propios."))
	try:
		shutil.rmtree(paquete.carpeta)
	except OSError as error:
		raise ErrorPaquete(_("No se pudo eliminar el paquete: {e}").format(e=error.strerror or error)) from None
	log.info("Paquete de sonidos eliminado: %s", id_paquete)


# ── Exportar e importar .zcsonidos ───────────────────────────────────────────


def exportar(id_paquete: str, destino: Path) -> Path:
	"""Crea un ``.zcsonidos`` con el contenido de la carpeta del paquete (solo lo admitido)."""
	paquete = obtener(id_paquete)
	if paquete is None:
		raise ErrorPaquete(_("No existe el paquete «{i}».").format(i=id_paquete))
	destino = Path(destino)
	if destino.suffix.lower() != EXTENSION:
		destino = destino.with_name(destino.name + EXTENSION)
	temporal = destino.with_name(destino.name + ".parcial")
	miembros = [MANIFIESTO]
	if (paquete.carpeta / LICENCIA).is_file():
		miembros.append(LICENCIA)
	for ruta in sorted(paquete.carpeta.rglob("*.wav")):
		relativo = ruta.relative_to(paquete.carpeta).as_posix()
		if problema_en_archivo(relativo) is None:
			miembros.append(relativo)
	try:
		with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zip_:
			for miembro in miembros:
				zip_.write(paquete.carpeta / miembro, miembro)
		os.replace(temporal, destino)
	except OSError as error:
		temporal.unlink(missing_ok=True)
		raise ErrorPaquete(_("No se pudo exportar el paquete: {e}").format(e=error.strerror or error)) from None
	return destino


def _validar_miembro(info: zipfile.ZipInfo, nombres: set[str]) -> str | None:
	"""Motivo por el que una entrada de un ``.zcsonidos`` no vale (o ``None``)."""
	from app.services.vfs import rutas

	nombre = info.filename
	if "\\" in nombre or nombre.startswith("/") or ":" in nombre or re.match(r"^[A-Za-z]:", nombre):
		return _("ruta no permitida")
	partes = PurePosixPath(nombre).parts
	if any(p in ("", ".", "..") for p in partes):
		return _("ruta no permitida")
	if stat.S_ISLNK(info.external_attr >> 16):
		return _("es un enlace")
	if info.flag_bits & 0x1:
		return _("está cifrado")
	clave = nombre.rstrip("/").casefold()
	if clave in nombres:
		return _("está repetido")
	nombres.add(clave)
	if info.is_dir():
		if partes[0] == "plugins" and len(partes) <= 2:
			return rutas.problema_en_nombre(partes[-1])
		return _("carpeta no permitida")
	if nombre in (MANIFIESTO, LICENCIA):
		return None
	return problema_en_archivo(nombre)


def leer_zcsonidos(ruta: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
	"""Valida un ``.zcsonidos`` entero (sin escribir nada) y devuelve su manifiesto y sus archivos."""
	try:
		zip_ = zipfile.ZipFile(ruta)
	except (OSError, zipfile.BadZipFile) as error:
		raise ErrorPaquete(_("No es un paquete de sonidos válido: {e}").format(e=error)) from None
	with zip_:
		infos = zip_.infolist()
		if len(infos) > MAX_MIEMBROS:
			raise ErrorPaquete(_("El paquete tiene demasiados archivos ({n}).").format(n=len(infos)))
		if sum(i.file_size for i in infos) > MAX_EXPANDIDO:
			raise ErrorPaquete(_("El paquete ocupa más de 50 MB descomprimido."))
		vistos: set[str] = set()
		for info in infos:
			motivo = _validar_miembro(info, vistos)
			if motivo:
				raise ErrorPaquete(_("El paquete contiene «{n}», que no se admite: {m}.").format(n=info.filename, m=motivo.rstrip(".")))
		archivos: dict[str, bytes] = {}
		total = 0
		for info in infos:
			if info.is_dir():
				continue
			try:
				with zip_.open(info) as entrada:
					datos = entrada.read(MAX_EXPANDIDO - total + 1)
			except (OSError, zipfile.BadZipFile, RuntimeError) as error:
				raise ErrorPaquete(_("No se puede leer «{n}» del paquete: {e}").format(n=info.filename, e=error)) from None
			total += len(datos)
			if total > MAX_EXPANDIDO:
				raise ErrorPaquete(_("El paquete ocupa más de 50 MB descomprimido."))
			archivos[info.filename] = datos
	if MANIFIESTO not in archivos:
		raise ErrorPaquete(_("El paquete no tiene paquete.json."))
	try:
		manifiesto = json.loads(archivos[MANIFIESTO].decode("utf-8"))
	except (UnicodeDecodeError, json.JSONDecodeError) as error:
		raise ErrorPaquete(_("El paquete.json no se puede leer: {e}").format(e=error)) from None
	problemas = validar_manifiesto(manifiesto)
	if problemas:
		raise ErrorPaquete("; ".join(problemas))
	if manifiesto["id"] in SERIE or (carpeta_serie() / manifiesto["id"] / MANIFIESTO).is_file():
		raise ErrorPaquete(_("El paquete usa el identificador «{i}», que es de un paquete de serie.").format(i=manifiesto["id"]))
	for nombre, datos in archivos.items():
		if nombre.lower().endswith(".wav"):
			motivo = wav.problema(datos)
			if motivo:
				raise ErrorPaquete(_("El sonido «{n}» no vale: {m}").format(n=nombre, m=motivo))
	return manifiesto, archivos


def importar(ruta: Path, *, sustituir: bool = False) -> Paquete:
	"""Instala un ``.zcsonidos`` como paquete propio.

	Lanza ``PaqueteExiste`` si ya hay uno propio con ese id y no se pide
	``sustituir``; ``ErrorPaquete`` si algo no vale (sin haber escrito nada).
	"""
	manifiesto, archivos = leer_zcsonidos(Path(ruta))
	id_paquete = manifiesto["id"]
	destino = carpeta_propios() / id_paquete
	if destino.exists() and not sustituir:
		existente = obtener(id_paquete)
		raise PaqueteExiste(id_paquete, existente.nombre if existente else id_paquete)
	temporal = carpeta_propios() / f".importando-{id_paquete}"
	try:
		shutil.rmtree(temporal, ignore_errors=True)
		for nombre, datos in archivos.items():
			objetivo = temporal / nombre
			objetivo.parent.mkdir(parents=True, exist_ok=True)
			objetivo.write_bytes(datos)
		if destino.exists():
			shutil.rmtree(destino)
		os.replace(temporal, destino)
	except OSError as error:
		shutil.rmtree(temporal, ignore_errors=True)
		raise ErrorPaquete(_("No se pudo instalar el paquete: {e}").format(e=error.strerror or error)) from None
	paquete = leer(destino, False)
	paquete.id = id_paquete
	log.info("Paquete de sonidos importado: %s (%s)", paquete.nombre, id_paquete)
	return paquete


# ── Migración de la 1.x y soporte ────────────────────────────────────────────


def migrar_1x(ruta_datos: Path, config: Any) -> bool:
	"""Lleva los WAV sueltos de la 1.x de ``data/sounds`` a «Mis sonidos 1.x» y lo elige (4.5).

	Idempotente: los WAV se MUEVEN, así que la segunda vez no hay nada que hacer.
	:return: verdadero si creó el paquete.
	"""
	origen_wav = Path(ruta_datos) / "sounds"
	presentes = [nombre for nombre in WAV_1X if (origen_wav / nombre).is_file()]
	if not presentes:
		return False
	destino = Path(ruta_datos) / "sounds_usuario" / ID_1X
	if (destino / MANIFIESTO).is_file():
		log.info("«Mis sonidos 1.x» ya existe; los WAV sueltos de la 1.x se dejan donde están")
		return False
	archivos = {}
	try:
		destino.mkdir(parents=True, exist_ok=True)
		for nombre in presentes:
			shutil.move(str(origen_wav / nombre), str(destino / nombre))
			for id_evento in WAV_1X[nombre]:
				archivos[id_evento] = nombre
		paquete = Paquete(id=ID_1X, nombre=_("Mis sonidos 1.x"), carpeta=destino, de_serie=False,
			descripcion=_("Los sonidos propios que tenía en zCommander 1.x."), hereda=BASE, archivos=archivos)
		escribir_manifiesto(paquete)
	except OSError:
		log.exception("No se pudieron llevar los sonidos de la 1.x a %s", destino)
		return False
	try:
		config.establecer("sonidos.paquete", ID_1X)
	except Exception:  # noqa: BLE001 - el paquete queda creado y se puede elegir a mano
		log.warning("No se pudo elegir el paquete «Mis sonidos 1.x»", exc_info=True)
	log.info("Sonidos de la 1.x migrados a %s: %s", destino, ", ".join(presentes))
	return True


def lineas_soporte() -> list[str]:
	"""Líneas de los sonidos para «Información para soporte» (14.9)."""
	from app.services.sonidos import servicio

	config = getattr(servicio.reproductor(), "config", None)
	lineas = []
	instalados = listar()
	if config is not None:
		try:
			elegido = str(config.obtener("sonidos.paquete"))
			activos = bool(config.obtener("sonidos.activos"))
			volumen = int(config.obtener("sonidos.volumen"))
		except Exception:  # noqa: BLE001 - el informe de soporte nunca falla por los sonidos
			log.debug("No se pudo leer la configuración de sonidos para soporte", exc_info=True)
		else:
			paquete = next((p for p in instalados if p.id == elegido), None)
			descripcion = f"{paquete.etiqueta} ({elegido})" if paquete else _("{i} (no instalado; suena el clásico)").format(i=elegido)
			lineas.append(_("Paquete elegido: {p}").format(p=descripcion))
			lineas.append(_("Sonidos activos: {a}; volumen: {v}").format(a=_("sí") if activos else _("no"), v=volumen))
	serie = sum(1 for p in instalados if p.de_serie)
	lineas.append(_("Paquetes instalados: {s} de serie y {p} propios").format(s=serie, p=len(instalados) - serie))
	return lineas
