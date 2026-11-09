# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Valida un complemento de zCommander antes de publicarlo (diseño 2.0, 3.12 y 15.3).

Uso::

	python tools/validar_plugin.py <carpeta o paquete .zcplugin> [--sin-pruebas]

Comprueba, en este orden:

1. El paquete (si es un ``.zcplugin``): ZIP seguro con las reglas de la instalación.
2. El manifiesto (``app.plugins.manifiesto``): campos, id, versiones, licencia SPDX,
   órdenes con etiqueta y ayuda, letras sin repetir en su menú, teclas canónicas,
   configuración, máscaras, ``codigos_windows``, ``prueba`` y nombres de ``lib/``.
3. ``LICENSE``, la ayuda (``doc/es/leeme.md``) y los sonidos declarados.
4. Letras de acceso de cada página de Preferencias (sin repetir y sin chocar con
   Aceptar, Cancelar, Aplicar y Valores de fábrica), con el nombre de la clave.
5. Teclas contra el catálogo del núcleo y de los complementos de serie, y teclas reservadas.
6. Importaciones de ``app.`` fuera de ``app.plugins.api`` («usa partes internas», aviso)
   y diálogos dentro de ``activar()`` (aviso).
7. En un proceso limpio: importa el complemento, llama a ``activar`` con un
   anfitrión de prueba, comprueba que cada orden tiene manejador (no provisional)
   y pasa ``revisar_teclado`` a las ventanas de ``ventanas_para_revisar``, con una
   interfaz mínima fijada (``InterfazSinVentana``, cuyo ``modulo_ui`` es
   ``app.ui.api_ui``) para que el complemento las construya con ``zc.ui``.
8. Sus pruebas con pytest: carpeta ``pruebas/`` o ``tests/`` del complemento y,
   para uno de ``<raíz>/plugins/`` sin ellas, ``tests/plugins/<carpeta>/`` y
   ``tests/plugins/test_*_<carpeta>.py`` (donde están las de los de serie, 11.0).

Devuelve 0 si no hay errores (los avisos no cuentan) y 1 si hay alguno.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

#: Letras de los botones y del buscador del diálogo de Preferencias (las de ``app/ui/dialogos/pl_preferencias.py``).
LETRAS_PREFERENCIAS = frozenset({"a", "c", "p", "v", "r", "u"})
DIALOGOS_UI = frozenset({"mostrar_modal", "mostrar_mensaje", "mostrar_error", "confirmar", "elegir_opcion", "pedir_texto",
	"mostrar_texto", "mostrar_documento"})


class Informe:
	def __init__(self) -> None:
		self.errores: list[str] = []
		self.avisos: list[str] = []

	def error(self, texto: str) -> None:
		self.errores.append(texto)

	def aviso(self, texto: str) -> None:
		self.avisos.append(texto)

	def texto(self) -> str:
		lineas = []
		if self.errores:
			lineas.append(f"Errores: {len(self.errores)}.")
			lineas.extend(f"- {e}" for e in self.errores)
		if self.avisos:
			lineas.append(f"Avisos: {len(self.avisos)}.")
			lineas.extend(f"- {a}" for a in self.avisos)
		lineas.append("Resultado: " + ("no válido." if self.errores else "válido."))
		return "\n".join(lineas)


def _letra(etiqueta: str) -> str | None:
	from app.plugins.manifiesto import _letra as letra

	return letra(etiqueta)


def revisar_letras_preferencias(datos, informe: Informe) -> None:
	"""Letras de cada página: sin repetir entre claves ni con los botones del diálogo de Preferencias (3.6)."""
	paginas_declaradas = {str(p.get("id")) for p in datos.tabla("paginas")}
	por_pagina: dict[str, dict[str, str]] = {}
	for declaracion in datos.tabla("configuracion"):
		if declaracion.get("interna"):
			continue
		clave = str(declaracion.get("clave"))
		etiqueta = str(declaracion.get("etiqueta", ""))
		if not etiqueta:
			informe.aviso(f"La clave {clave} no tiene etiqueta: en Preferencias se verá su nombre interno")
			continue
		letra = _letra(etiqueta)
		if letra is None:
			informe.error(f"La etiqueta de la clave {clave} no tiene letra de acceso (&)")
			continue
		pagina = str(declaracion.get("pagina", "") or "")
		if pagina and pagina not in paginas_declaradas:
			informe.aviso(f"La clave {clave} nombra la página «{pagina}», que no está en [[paginas]]: irá a la del complemento")
			pagina = ""
		if letra in LETRAS_PREFERENCIAS:
			informe.error(f"La clave {clave} usa la letra {letra.upper()}, que ya usa un botón del diálogo de Preferencias")
		ocupadas = por_pagina.setdefault(pagina, {})
		if letra in ocupadas:
			informe.error(f"La clave {clave} usa la letra {letra.upper()}, que ya usa la clave {ocupadas[letra]} en la misma página")
		ocupadas.setdefault(letra, clave)


def revisar_teclas(datos, informe: Informe) -> None:
	"""Teclas del manifiesto contra el catálogo (núcleo y complementos de serie) y las reservadas (14.1.3)."""
	from app.plugins import registro
	from app.services import teclas
	from app.ui import ordenes

	if not any(r.origen == "serie" for r in registro.complementos()):
		registro.registrar_serie()
	ocupadas: dict[str, tuple[str, str]] = {}
	for orden in ordenes.catalogo():
		if orden.id.startswith(datos.id + ":"):
			continue
		for tecla in orden.teclas:
			ocupadas.setdefault(tecla, (orden.id, orden.ambito))
	for orden in datos.ordenes:
		for tecla in orden.teclas:
			if teclas.es_reservada(tecla):
				informe.error(f"La orden {orden.id} usa la tecla reservada {tecla}")
			elif tecla in ocupadas:
				otra, ambito = ocupadas[tecla]
				if ambito == orden.ambito or "global" in (ambito, orden.ambito):
					informe.error(f"La tecla {tecla} de la orden {orden.id} ya la usa {otra}: zCommander no se la dará")


def revisar_codigo(carpeta: Path, informe: Informe) -> None:
	from app.plugins import paquetes

	for linea in paquetes.partes_internas(carpeta):
		informe.aviso(f"Usa partes internas de zCommander (solo app.plugins.api está garantizado): {linea}")
	for archivo in sorted(carpeta.rglob("*.py")):
		if "lib" in archivo.relative_to(carpeta).parts[:1]:
			continue
		try:
			arbol = ast.parse(archivo.read_text(encoding="utf-8"))
		except (OSError, SyntaxError, ValueError) as error:
			informe.error(f"{archivo.relative_to(carpeta).as_posix()} no se puede leer como Python: {error}")
			continue
		for nodo in ast.walk(arbol):
			if isinstance(nodo, ast.FunctionDef) and nodo.name == "activar":
				for llamada in ast.walk(nodo):
					if isinstance(llamada, ast.Attribute) and llamada.attr in DIALOGOS_UI:
						informe.aviso(f"{archivo.relative_to(carpeta).as_posix()}:{llamada.lineno}: activar() no puede abrir diálogos "
							f"({llamada.attr}); aplácelo con zc.complemento_futuro(zc.id).add_done_callback(...)")
			if isinstance(nodo, ast.Attribute) and nodo.attr == "ShowModal":
				informe.aviso(f"{archivo.relative_to(carpeta).as_posix()}:{nodo.lineno}: use zc.ui.mostrar_modal en lugar de ShowModal")
			if isinstance(nodo, (ast.Import, ast.ImportFrom)):
				nombres = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else [nodo.module or ""]
				if any(n.startswith("accessible_output2") for n in nombres):
					informe.aviso(f"{archivo.relative_to(carpeta).as_posix()}:{nodo.lineno}: anuncie con zc.anunciar, no con accessible_output2")


def revisar_archivos(carpeta: Path, datos, informe: Informe) -> None:
	if not (carpeta / "LICENSE").is_file():
		informe.error("Falta el archivo LICENSE")
	ayuda = carpeta / str(datos.datos.get("ayuda", "doc/es/leeme.md"))
	if not ayuda.is_file():
		informe.aviso(f"No hay ayuda ({ayuda.relative_to(carpeta).as_posix()}): F1 y el botón Ayuda del gestor no tendrán nada")
	for sonido in datos.sonidos:
		archivo = carpeta / str(sonido.get("archivo", f"sonidos/{sonido['id']}.wav"))
		if not archivo.is_file():
			informe.aviso(f"El sonido {sonido['id']} no tiene su archivo {archivo.relative_to(carpeta).as_posix()}")
	modulo = datos.entrada.split(":", 1)[0]
	if not ((carpeta / f"{modulo}.py").is_file() or (carpeta / modulo / "__init__.py").is_file() or modulo == "__init__"):
		informe.error(f"No existe el módulo de la entrada «{datos.entrada}»")


def _entorno(datos_temporales: Path) -> dict[str, str]:
	entorno = dict(os.environ)
	entorno["APP_DATA_DIR"] = str(datos_temporales)
	entorno["PYTHONPATH"] = str(RAIZ)
	entorno.pop("APP_DEPURACION", None)
	return entorno


def revisar_en_proceso_limpio(carpeta: Path, informe: Informe, datos_temporales: Path) -> None:
	"""Importa y activa el complemento en otro proceso (lo que deje cargado no afecta a nada)."""
	resultado = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--hijo", str(carpeta)], cwd=str(RAIZ),
		env=_entorno(datos_temporales), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
	try:
		datos = json.loads(resultado.stdout.strip().splitlines()[-1])
	except (IndexError, ValueError):
		informe.error("No se pudo importar el complemento en un proceso limpio:\n" + (resultado.stderr or resultado.stdout)[-2000:])
		return
	for texto in datos.get("errores", []):
		informe.error(texto)
	for texto in datos.get("avisos", []):
		informe.aviso(texto)


def _hijo(carpeta: Path) -> int:
	"""Proceso limpio: activa el complemento con un anfitrión de prueba y revisa sus ventanas."""
	salida: dict[str, list[str]] = {"errores": [], "avisos": []}
	try:
		from app.plugins import api, manifiesto, registro
		from app.plugins.api import pruebas

		datos = manifiesto.leer(carpeta)
		zc = pruebas.anfitrion_de_prueba(carpeta)
		zc.activar()
		for orden in datos.ordenes:
			funcion = registro.manejador(f"{datos.id}:{orden.id}")
			if funcion is None:
				salida["errores"].append(f"La orden {orden.id} no tiene manejador (zc.ordenes.manejador en activar)")
			elif getattr(funcion, "provisional", False):
				salida["errores"].append(f"La orden {orden.id} solo tiene un manejador provisional")
		instancia = zc.instancia
		if type(instancia).ventanas_para_revisar is not api.Complemento.ventanas_para_revisar:
			import wx

			from app.ui.accesibilidad.revision_teclado import informe as informe_teclado
			from app.ui.accesibilidad.revision_teclado import revisar_teclado

			from app.ui.interfaz_anfitrion import InterfazSinVentana

			aplicacion = wx.App.Get() or wx.App(False)
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
			# Sin interfaz, zc.ui lanza NoAdmitido y el complemento no podría construir sus ventanas.
			api.fijar_interfaz(InterfazSinVentana())
			padre = wx.Frame(None, title="Validar")
			for ventana in instancia.ventanas_para_revisar(padre) or []:
				problemas = [p for p in revisar_teclado(ventana) if not getattr(p, "aviso", False)]
				if problemas:
					salida["errores"].append(f"La ventana «{ventana.GetTitle()}» no pasa revisar_teclado:\n{informe_teclado(problemas)}")
				ventana.Destroy()
			padre.Destroy()
			del aplicacion
	except Exception as error:  # noqa: BLE001 - todo fallo del complemento se informa como error
		import traceback

		salida["errores"].append(f"El complemento falla al importarse o activarse: {error}\n{traceback.format_exc()[-1500:]}")
	print(json.dumps(salida, ensure_ascii=False))
	return 0


def pruebas_de(carpeta: Path) -> tuple[list[Path], Path] | None:
	"""Pruebas del complemento y la raíz de pytest con la que se ejecutan, o ``None`` si no tiene.

	Primero las suyas (``pruebas/`` o ``tests/``, con la carpeta del complemento como raíz).
	Un complemento de ``<raíz>/plugins/`` (los de serie) tiene las suyas en
	``tests/plugins/<carpeta>/`` o en ``tests/plugins/test_*_<carpeta>.py`` (11.0); esas se
	ejecutan con la raíz del proyecto, para que valga su ``conftest.py``.
	"""
	for nombre in ("pruebas", "tests"):
		if (carpeta / nombre).is_dir():
			return [carpeta / nombre], carpeta
	try:
		de_serie = carpeta.resolve().parent == (RAIZ / "plugins").resolve()
	except OSError:
		de_serie = False
	if de_serie:
		pruebas_raiz = RAIZ / "tests" / "plugins"
		encontradas = [pruebas_raiz / carpeta.name] if (pruebas_raiz / carpeta.name).is_dir() else []
		encontradas += sorted(pruebas_raiz.glob(f"test_*_{carpeta.name}.py"))
		if encontradas:
			return encontradas, RAIZ
	return None


def ejecutar_pruebas(carpeta: Path, informe: Informe, datos_temporales: Path) -> None:
	encontradas = pruebas_de(carpeta)
	if encontradas is None:
		informe.aviso("No tiene pruebas (carpeta pruebas/ con pytest y api.pruebas)")
		return
	rutas, raiz = encontradas
	resultado = subprocess.run([sys.executable, "-m", "pytest", *(str(r) for r in rutas), "-q", "-p", "no:cacheprovider",
		"-o", "addopts=", "--rootdir", str(raiz)], cwd=str(RAIZ), env=_entorno(datos_temporales), capture_output=True, text=True,
		encoding="utf-8", errors="replace", timeout=900)
	if resultado.returncode not in (0, 5):
		informe.error(f"Sus pruebas fallan:\n{resultado.stdout[-2000:]}")


def validar(objetivo: Path, pruebas: bool = True) -> Informe:
	from app.core import paths
	from app.plugins import manifiesto, paquetes

	informe = Informe()
	objetivo = Path(objetivo)
	temporal = paths.ruta_temporales() / f"validar-plugin-{uuid.uuid4().hex[:8]}"
	try:
		carpeta = objetivo
		if objetivo.is_file():
			try:
				with zipfile.ZipFile(objetivo) as paquete:
					archivos = paquetes.validar_zip(paquete)
					carpeta = temporal / "paquete"
					carpeta.mkdir(parents=True)
					paquetes._extraer(paquete, archivos, carpeta)  # noqa: SLF001 - mismas reglas que la instalación
			except (zipfile.BadZipFile, paquetes.ErrorPaquete) as error:
				informe.error(f"El paquete no se puede instalar: {error}")
				return informe
		if not carpeta.is_dir():
			informe.error(f"No existe {carpeta}")
			return informe
		try:
			datos = manifiesto.leer(carpeta)
		except manifiesto.ErrorManifiesto as error:
			for problema in error.problemas:
				informe.error(problema)
			if not (carpeta / "LICENSE").is_file():
				informe.error("Falta el archivo LICENSE")
			return informe
		revisar_archivos(carpeta, datos, informe)
		revisar_letras_preferencias(datos, informe)
		revisar_teclas(datos, informe)
		revisar_codigo(carpeta, informe)
		if informe.errores:
			return informe
		datos_temporales = temporal / "data"
		datos_temporales.mkdir(parents=True, exist_ok=True)
		revisar_en_proceso_limpio(carpeta, informe, datos_temporales)
		if pruebas and not informe.errores:
			ejecutar_pruebas(carpeta, informe, datos_temporales)
		return informe
	finally:
		shutil.rmtree(temporal, ignore_errors=True)


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description="Valida un complemento de zCommander.")
	analizador.add_argument("objetivo", help="Carpeta del complemento o paquete .zcplugin")
	analizador.add_argument("--sin-pruebas", action="store_true", help="No ejecuta las pruebas del complemento")
	analizador.add_argument("--hijo", action="store_true", help=argparse.SUPPRESS)
	opciones = analizador.parse_args(argumentos)
	if opciones.hijo:
		return _hijo(Path(opciones.objetivo))
	informe = validar(Path(opciones.objetivo), pruebas=not opciones.sin_pruebas)
	print(informe.texto())
	return 1 if informe.errores else 0


if __name__ == "__main__":
	sys.exit(main())
