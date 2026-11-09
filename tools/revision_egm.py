# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Prepara revisiones con el Elephant-Goldfish Model (EGM) y resume sus informes en español.

EGM es un plugin para asistentes de IA: el «elefante» (la sesión principal, con
todo el contexto) redacta y decide; los «goldfish» son revisores que arrancan
SIN la conversación y solo leen el documento y lo que se les da. Así encuentran
lo que se da por supuesto.

Esta herramienta no revisa nada por sí misma (eso lo hacen los subagentes de
EGM). Hace lo mecánico, sin dependencias:

	python tools/revision_egm.py comprobar [--egm RUTA]
		Dónde está EGM instalado, su versión, revisores y estándares.

	python tools/revision_egm.py contexto DOCUMENTO [--raiz RAIZ]
		Lista de lectura para los goldfish: los archivos del proyecto que el
		documento cita (enlaces Markdown y rutas entre comillas invertidas).

	python tools/revision_egm.py orden DOCUMENTO --perfil PERFIL [--raiz RAIZ] [--egm RUTA] [--json]
		La configuración completa para /egm:egm-review-loop: documento, revisores,
		estándar de cada uno (los de EGM y los de docs/revision/estandares) y
		lista de lectura. Perfiles: manual, skill, diseno, plan, paridad, leeme.

	python tools/revision_egm.py resumen INFORME
		Resumen accesible (sin tablas) de goldfish_review_report.md: cuántos
		hallazgos hay de cada gravedad y cuáles son.

PLANTILLA del agente «revision-egm».
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

VARIABLE_EGM = "EGM_RAIZ"
INDICACIONES = (
	"Indicaciones para los goldfish: el documento está en español de España; escribid los hallazgos en español. "
	"Sus lectores usan lector de pantalla: valorad encabezados, listas y frases cortas."
)
CARPETA_ESTANDARES = Path("docs") / "revision" / "estandares"
EXTENSIONES_CONTEXTO = {
	".py", ".kt", ".kts", ".java", ".md", ".txt", ".json", ".toml", ".bat", ".ps1", ".xml", ".yaml", ".yml", ".cfg", ".ini",
}
CARPETAS_IGNORADAS = {".git", ".venv", "venv", "build", "dist", "__pycache__", "node_modules", ".gradle", "entorno"}
MAX_CONTEXTO = 40


@dataclass(frozen=True)
class Revisor:
	"""Un goldfish y el estándar contra el que revisa.

	``estandar``: nombre de un estándar de EGM (sin barra) o archivo propio de
	``docs/revision/estandares`` (con ``.md``). ``None``: solo su papel.
	"""

	nombre: str
	estandar: str | None = None


@dataclass(frozen=True)
class Perfil:
	descripcion: str
	revisores: tuple[Revisor, ...]
	# Documentos del proyecto que conviene dar siempre como contexto, si existen.
	contexto_fijo: tuple[str, ...] = field(default_factory=tuple)


PERFILES: dict[str, Perfil] = {
	"manual": Perfil(
		"Manual, lista de teclas o novedades para personas que usan lector de pantalla.",
		(
			Revisor("comprehension", "documentacion-accesible.md"),
			Revisor("style", "documentacion-accesible.md"),
			Revisor("structural", "manual-usuario.md"),
			Revisor("codebase_details", "manual-usuario.md"),
		),
		("docs/teclas.md", "data/docs/teclas.md", "LEEME.md", "README.md"),
	),
	"skill": Perfil(
		"SKILL.md de un agente (formato Agent Skills): autonomía, carga progresiva y plantillas probadas.",
		(
			Revisor("structural", "skill-agente.md"),
			Revisor("comprehension", "skill-agente.md"),
			Revisor("implementation_readiness", "skill-agente.md"),
			Revisor("zoom_out", "zoom-out-standard"),
		),
		("compartido/perfil-desarrollador.md", "AGENTS.md"),
	),
	"diseno": Perfil(
		"Diseño de una función nueva antes de programarla.",
		(
			Revisor("design_critic", "feature-spec-standard"),
			Revisor("structural", "feature-spec-standard"),
			Revisor("comprehension", "documentacion-accesible.md"),
			Revisor("zoom_out", "zoom-out-standard"),
		),
		("AGENTS.md", "CLAUDE.md", "LEEME.md", "README.md"),
	),
	"plan": Perfil(
		"Plan de implementación o de corrección (por ejemplo, tras una auditoría).",
		(
			Revisor("implementation_readiness", "implementation-readiness-standard"),
			Revisor("codebase_details", "plan-correccion.md"),
			Revisor("zoom_out", "zoom-out-standard"),
		),
		("AGENTS.md", "CLAUDE.md"),
	),
	"paridad": Perfil(
		"Paridad entre plataformas: un clon o una adaptación (Android y Windows) cubre lo mismo que el original.",
		(
			Revisor("codebase_details", "paridad-plataformas.md"),
			Revisor("implementation_readiness", "paridad-plataformas.md"),
			Revisor("design_critic", "paridad-plataformas.md"),
		),
		("LEEME.md", "README.md", "NOVEDADES.txt", "CHANGELOG.md"),
	),
	"leeme": Perfil(
		"LEEME, AGENTS.md o CLAUDE.md del proyecto: que otra persona (o una IA nueva) pueda trabajar con él.",
		(
			Revisor("comprehension", "documentacion-accesible.md"),
			Revisor("codebase_details", "re-implementation-standard"),
			Revisor("structural", "documentacion-accesible.md"),
		),
		("pyproject.toml", "requirements.txt", "build.gradle.kts", "settings.gradle.kts"),
	),
}


# ── Localizar EGM ─────────────────────────────────────────────────────────────


def _es_raiz_egm(ruta: Path) -> bool:
	return (ruta / "agents").is_dir() and (ruta / "resources" / "document_standards").is_dir()


def _clave_version(nombre: str) -> tuple[int, ...]:
	return tuple(int(x) for x in re.findall(r"\d+", nombre)) or (0,)


def candidatos_egm(casa: Path | None = None) -> list[Path]:
	"""Sitios donde suele quedar EGM, del más probable al menos."""
	casa = casa or Path.home()
	salida: list[Path] = []
	cache = casa / ".claude" / "plugins" / "cache" / "egm" / "egm"
	if cache.is_dir():
		salida.extend(sorted((p for p in cache.iterdir() if p.is_dir()), key=lambda p: _clave_version(p.name), reverse=True))
	salida.append(casa / ".claude" / "plugins" / "marketplaces" / "egm")
	salida.append(casa / ".agents" / "plugins" / "egm")
	salida.append(casa / ".gemini" / "plugins" / "egm")
	return salida


def localizar_egm(explicita: str | Path | None = None, casa: Path | None = None) -> Path | None:
	"""La carpeta de EGM: la indicada, ``EGM_RAIZ`` o la del plugin instalado."""
	for opcion in (explicita, os.environ.get(VARIABLE_EGM, "").strip() or None):
		if opcion:
			ruta = Path(opcion).expanduser()
			return ruta.resolve() if _es_raiz_egm(ruta) else None
	return next((p.resolve() for p in candidatos_egm(casa) if _es_raiz_egm(p)), None)


@dataclass
class Inventario:
	raiz: Path
	version: str
	revisores: dict[str, str]
	estandares: list[str]


def inventario(raiz: Path) -> Inventario:
	"""Revisores (archivo → nombre de subagente) y estándares de una instalación de EGM."""
	revisores: dict[str, str] = {}
	for archivo in sorted((raiz / "agents").glob("*.md")):
		texto = archivo.read_text(encoding="utf-8", errors="replace")
		m = re.search(r"^name:\s*(\S+)", texto, re.MULTILINE)
		revisores[archivo.stem] = m.group(1) if m else f"egm-{archivo.stem.replace('_', '-')}"
	estandares = sorted(p.stem for p in (raiz / "resources" / "document_standards").glob("*.md"))
	version = ""
	for nombre in ("plugin.json", ".claude-plugin/plugin.json"):
		try:
			version = str(json.loads((raiz / nombre).read_text(encoding="utf-8")).get("version", ""))
			break
		except (OSError, ValueError):
			continue
	if not version and re.fullmatch(r"[\d.]+", raiz.name):
		version = raiz.name
	return Inventario(raiz, version or "desconocida", revisores, estandares)


# ── Lista de lectura ──────────────────────────────────────────────────────────

_ENLACE = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
_CODIGO = re.compile(r"`([^`\s]+\.[A-Za-z0-9]{1,5})(?::\d+)?`")


def _ignorada(ruta: Path, raiz: Path) -> bool:
	try:
		partes = ruta.relative_to(raiz).parts
	except ValueError:
		return True
	return any(p in CARPETAS_IGNORADAS for p in partes)


def contexto(documento: Path, raiz: Path | None = None, perfil: Perfil | None = None) -> list[Path]:
	"""Archivos del proyecto que el documento cita, más los fijos del perfil, sin repetir."""
	documento = documento.resolve()
	raiz = (raiz or documento.parent).resolve()
	texto = documento.read_text(encoding="utf-8", errors="replace")
	vistos: list[Path] = []

	def anadir(ruta: Path) -> None:
		ruta = ruta.resolve()
		if (
			ruta.is_file() and ruta != documento and ruta not in vistos and not _ignorada(ruta, raiz)
			and ruta.suffix.lower() in EXTENSIONES_CONTEXTO
		):
			vistos.append(ruta)

	for patron in (_ENLACE, _CODIGO):
		for m in patron.finditer(texto):
			citado = m.group(1).strip()
			if "://" in citado or citado.startswith("mailto:"):
				continue
			for base in (documento.parent, raiz):
				candidato = base / citado
				if candidato.exists():
					anadir(candidato)
					break
	for fijo in (perfil.contexto_fijo if perfil else ()):
		anadir(raiz / fijo)
	return vistos[:MAX_CONTEXTO]


# ── Configuración de la revisión ──────────────────────────────────────────────


@dataclass
class Configuracion:
	documento: Path
	perfil: str
	revisores: list[str]
	estandares: dict[str, str]
	lectura: list[Path]
	avisos: list[str]

	def como_dict(self) -> dict:
		return {
			"TargetFile": self.documento.as_posix(),
			"SemanticTarget": "full file",
			"Reviewers": self.revisores,
			"Standards": self.estandares,
			"GoldfishContext": [p.as_posix() for p in self.lectura],
			"Indicaciones": INDICACIONES,
			"Perfil": self.perfil,
			"Avisos": self.avisos,
		}

	def como_texto(self) -> str:
		lineas = [
			"/egm:egm-review-loop",
			f"TargetFile: {self.documento.as_posix()}",
			"SemanticTarget: full file",
			"Reviewers: " + ", ".join(self.revisores),
			"Standards:",
		]
		lineas += [f"- {r}: {e}" for r, e in self.estandares.items()]
		lineas.append("GoldfishContext:" + ("" if self.lectura else " (vacía)"))
		lineas += [f"- {p.as_posix()}" for p in self.lectura]
		lineas.append(INDICACIONES)
		return "\n".join(lineas)


def configurar(
	documento: Path, perfil: str, raiz: Path | None = None, egm: Inventario | None = None, extra: list[Path] | None = None,
	estandares_propios: Path | None = None,
) -> Configuracion:
	"""Configuración de egm-review-loop.

	Las rutas van con barras normales («/»): EGM toma un estándar sin barra por uno
	de los suyos, y en Windows una ruta solo con barras invertidas lo confundiría.
	``estandares_propios``: carpeta de los estándares en español (por defecto,
	``docs/revision/estandares`` del proyecto; en un repositorio de agentes, la de
	las plantillas de este agente).
	"""
	if perfil not in PERFILES:
		raise ValueError(f"Perfil desconocido: {perfil}. Use uno de: {', '.join(PERFILES)}.")
	p = PERFILES[perfil]
	raiz = (raiz or documento.resolve().parent).resolve()
	carpeta_propia = (estandares_propios or raiz / CARPETA_ESTANDARES).resolve()
	avisos: list[str] = []
	estandares: dict[str, str] = {}
	revisores: list[str] = []
	for r in p.revisores:
		if egm is not None and r.nombre not in egm.revisores:
			avisos.append(f"La instalación de EGM no tiene el revisor {r.nombre}; se omite.")
			continue
		revisores.append(r.nombre)
		if r.estandar is None:
			continue
		if r.estandar.endswith(".md"):
			propio = carpeta_propia / r.estandar
			if propio.is_file():
				estandares[r.nombre] = propio.as_posix()
			else:
				avisos.append(
					f"Falta {r.estandar} en {carpeta_propia.as_posix()}: copie los estándares del agente o indique su carpeta "
					f"con --estandares. {r.nombre} revisará solo con su papel."
				)
		elif egm is not None and r.estandar not in egm.estandares:
			avisos.append(f"La instalación de EGM no tiene el estándar {r.estandar}; {r.nombre} revisará solo con su papel.")
		else:
			estandares[r.nombre] = r.estandar
	lectura = contexto(documento, raiz, p)
	for ruta in extra or []:
		ruta = ruta.resolve()
		if not ruta.exists():
			avisos.append(f"No existe {ruta.as_posix()}: no se añade a la lista de lectura.")
		elif ruta not in lectura:
			lectura.append(ruta)
	return Configuracion(documento.resolve(), perfil, revisores, estandares, lectura, avisos)


# ── Resumen del informe ───────────────────────────────────────────────────────

GRAVEDADES = (("🔴", "bloqueante"), ("🟡", "importante"), ("🟢", "detalle"))
_TEXTO_GRAVEDAD = {
	"blocker": "🔴", "bloqueante": "🔴", "major": "🟡", "mayor": "🟡", "importante": "🟡", "nit": "🟢", "menor": "🟢", "detalle": "🟢",
}


_EMOJIS = "🔴🟡🟢"
_PALABRA = "blocker|major|nit|bloqueante|mayor|importante|menor|detalle"
# Formato de egm-resolve (EGM 0.1.1): «### [Issue 1] [`style`] - Severity: Major».
_CABECERA_EGM = re.compile(
	r"^#{2,6}\s.*?(?:\[`?(?P<revisor>[\w-]+)`?\]\s*-\s*)?Severity:\s*(?P<gravedad>" + _PALABRA + r")", re.IGNORECASE
)
# Sus campos: «*   **Discrepancy Description:** ...», «*   ***AI Suggestion:*** ...».
_CAMPO_EGM = re.compile(r"^[-*]\s*\*{2,3}(?P<campo>[^*:]+):?\*{2,3}:?\s*(?P<valor>.*)$")


@dataclass
class Hallazgo:
	gravedad: str
	texto: str
	revisor: str = ""
	alcance: str = ""
	sugerencia: str = ""


def _gravedad_de(linea: str) -> str | None:
	"""Gravedad de una línea suelta: un único emoji o una palabra al principio."""
	emojis = [e for e in _EMOJIS if e in linea]
	if len(emojis) > 1:
		return None  # una leyenda («🔴 bloqueante, 🟡 importante...»), no un hallazgo
	if emojis:
		return emojis[0]
	m = re.match(r"\**\[?(" + _PALABRA + r")\]?\**[:\s]", linea, re.IGNORECASE)
	return _TEXTO_GRAVEDAD[m.group(1).lower()] if m else None


def _leer_formato_egm(lineas: list[str]) -> list[Hallazgo]:
	salida: list[Hallazgo] = []
	actual: Hallazgo | None = None
	for linea in lineas:
		bruta = linea.strip()
		cabecera = _CABECERA_EGM.match(bruta)
		if cabecera:
			actual = Hallazgo(_TEXTO_GRAVEDAD[cabecera.group("gravedad").lower()], "", cabecera.group("revisor") or "")
			salida.append(actual)
			continue
		if bruta.startswith("#"):
			actual = None
			continue
		campo = _CAMPO_EGM.match(bruta)
		if actual is None or not campo:
			continue
		nombre, valor = campo.group("campo").strip().lower(), campo.group("valor").strip()
		if nombre.startswith("discrepancy") and not actual.texto:
			actual.texto = valor
		elif nombre.startswith("affected scope"):
			actual.alcance = re.sub(r"\]\([^)]*\)", "", valor).replace("[", "").strip()
		elif nombre.startswith("ai suggestion"):
			actual.sugerencia = valor
	return [h for h in salida if h.texto]


def leer_informe(texto: str) -> list[Hallazgo]:
	"""Hallazgos del informe de egm-resolve (cabeceras «Severity:») o de una lista con gravedades.

	En una lista, una cabecera con una sola gravedad («### 🔴 Bloqueantes») marca
	las viñetas que siguen; una línea con varias gravedades es una leyenda.
	"""
	lineas = texto.splitlines()
	if any(_CABECERA_EGM.match(x.strip()) for x in lineas):
		return _leer_formato_egm(lineas)
	salida: list[Hallazgo] = []
	de_seccion: str | None = None
	for linea in lineas:
		bruta = linea.strip()
		if not bruta:
			continue
		if bruta.startswith("#"):
			de_seccion = _gravedad_de(bruta.lstrip("# "))
			continue
		limpia = bruta.lstrip("-*|> ").strip()
		marca = _gravedad_de(limpia)
		es_vineta = bruta[:1] in "-*" or re.match(r"\d+\.", bruta) is not None
		if marca is None and de_seccion and es_vineta:
			marca = de_seccion
		if marca is None:
			continue
		texto_limpio = re.sub("[" + _EMOJIS + "]", "", limpia).replace("|", " ").strip(" :-*")
		texto_limpio = re.sub(r"^\**\[?(" + _PALABRA + r")\]?\**:?\s*", "", texto_limpio, flags=re.IGNORECASE)
		texto_limpio = re.sub(r"\s{2,}", " ", texto_limpio)
		if texto_limpio:
			salida.append(Hallazgo(marca, texto_limpio))
	return salida


def resumen(hallazgos: list[Hallazgo]) -> str:
	if not hallazgos:
		return "El informe no tiene hallazgos con gravedad marcada."
	partes = []
	for emoji, nombre in GRAVEDADES:
		n = sum(1 for h in hallazgos if h.gravedad == emoji)
		partes.append(f"{n} {nombre}{'s' if n != 1 else ''}")
	lineas = [f"Hallazgos: {len(hallazgos)} ({', '.join(partes)})."]
	for emoji, nombre in GRAVEDADES:
		de_esta = [h for h in hallazgos if h.gravedad == emoji]
		if de_esta:
			lineas.append("")
			lineas.append(f"{nombre.capitalize()}s:")
			for h in de_esta:
				detalles = [x for x in (h.revisor and f"revisor {h.revisor}", h.alcance, h.sugerencia and f"propuesta de EGM: {h.sugerencia}") if x]
				lineas.append(f"- {h.texto}" + (f" ({'; '.join(detalles)})" if detalles else ""))
	return "\n".join(lineas)


# ── Línea de órdenes ──────────────────────────────────────────────────────────


def _salir(texto: str, codigo: int = 1) -> int:
	print(texto)
	return codigo


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description="Prepara revisiones con el Elephant-Goldfish Model.")
	ordenes = analizador.add_subparsers(dest="orden", required=True)
	o = ordenes.add_parser("comprobar", help="Dónde está EGM y qué revisores y estándares trae.")
	o.add_argument("--egm")
	o = ordenes.add_parser("contexto", help="Lista de lectura para los goldfish.")
	o.add_argument("documento")
	o.add_argument("--raiz")
	o.add_argument("--perfil", choices=list(PERFILES))
	o = ordenes.add_parser("orden", help="Configuración para /egm:egm-review-loop.")
	o.add_argument("documento")
	o.add_argument("--perfil", required=True, choices=list(PERFILES))
	o.add_argument("--raiz")
	o.add_argument("--egm")
	o.add_argument("--extra", nargs="*", default=[], help="Más archivos o carpetas para la lista de lectura.")
	o.add_argument("--estandares", help="Carpeta de los estándares en español (por defecto, docs/revision/estandares del proyecto).")
	o.add_argument("--json", action="store_true")
	o = ordenes.add_parser("resumen", help="Resumen accesible de goldfish_review_report.md.")
	o.add_argument("informe")
	ordenes.add_parser("perfiles", help="Perfiles de revisión disponibles.")
	a = analizador.parse_args(argumentos)

	if a.orden == "perfiles":
		for nombre, p in PERFILES.items():
			print(f"{nombre}: {p.descripcion} Revisores: {', '.join(r.nombre for r in p.revisores)}.")
		return 0
	if a.orden == "comprobar":
		raiz = localizar_egm(a.egm)
		if raiz is None:
			return _salir(
				"No se encuentra EGM. Instálelo como plugin (Claude Code: claude plugin marketplace add "
				"google/elephant-goldfish-model y claude plugin install egm@egm; Codex: codex plugin marketplace add "
				"google/elephant-goldfish-model y codex plugin add egm@egm) o indique su carpeta con --egm "
				f"o con la variable {VARIABLE_EGM}."
			)
		inv = inventario(raiz)
		print(f"EGM {inv.version} en {inv.raiz}")
		print("Revisores: " + ", ".join(f"{k} ({v})" for k, v in inv.revisores.items()))
		print("Estándares: " + ", ".join(inv.estandares))
		return 0
	if a.orden == "contexto":
		documento = Path(a.documento)
		if not documento.is_file():
			return _salir(f"No existe {documento}.")
		perfil = PERFILES.get(a.perfil) if a.perfil else None
		for ruta in contexto(documento, Path(a.raiz) if a.raiz else None, perfil):
			print(ruta)
		return 0
	if a.orden == "orden":
		documento = Path(a.documento)
		if not documento.is_file():
			return _salir(f"No existe {documento}.")
		raiz_egm = localizar_egm(a.egm)
		inv = inventario(raiz_egm) if raiz_egm else None
		config = configurar(
			documento, a.perfil, Path(a.raiz) if a.raiz else None, inv, [Path(x) for x in a.extra],
			Path(a.estandares) if a.estandares else None,
		)
		if inv is None:
			config.avisos.insert(0, "No se encuentra EGM instalado: la configuración no se ha podido contrastar con él.")
		if a.json:
			print(json.dumps(config.como_dict(), ensure_ascii=False, indent=1))
		else:
			print(config.como_texto())
			# Los avisos van por la salida de errores: la salida normal se pega tal cual en egm-review-loop.
			for aviso in config.avisos:
				print(f"[AVISO] {aviso}", file=sys.stderr)
		return 0
	if a.orden == "resumen":
		informe = Path(a.informe)
		if not informe.is_file():
			return _salir(f"No existe {informe}.")
		print(resumen(leer_informe(informe.read_text(encoding="utf-8", errors="replace"))))
		return 0
	return 1


if __name__ == "__main__":
	sys.exit(main())
