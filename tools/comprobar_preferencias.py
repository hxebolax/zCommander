# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprueba que las letras de acceso de cada página de Preferencias no se repiten.

Uso (desde la raíz del proyecto)::

	python tools/comprobar_preferencias.py             # informa y termina con 1 si hay choques
	python tools/comprobar_preferencias.py --corregir  # elige letras libres y reescribe descripciones_config.py

Cada página del diálogo tiene sus etiquetas (``app/core/descripciones_config.py``)
y los botones comunes del diálogo («&Valores de fábrica de esta página»,
«&Aceptar», «&Cancelar», «A&plicar»), así que sus letras están reservadas en
todas las páginas. Una letra repetida hace que Alt+letra vaya al primer control
y deje el segundo inaccesible por teclado.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
	sys.path.insert(0, str(RAIZ))

ARCHIVO = RAIZ / "app" / "core" / "descripciones_config.py"
# Letras de los botones comunes del diálogo (f_preferencias y la plantilla).
RESERVADAS = frozenset("vacp")


def letra(etiqueta: str) -> str | None:
	encontrada = re.search(r"&([^&\s])", etiqueta)
	return encontrada.group(1).casefold() if encontrada else None


def _base(caracter: str) -> str:
	return unicodedata.normalize("NFD", caracter)[0].casefold()


def problemas(descripciones: dict | None = None) -> list[str]:
	"""Textos legibles de cada choque, vacío si todo está bien."""
	if descripciones is None:
		from app.core.descripciones_config import DESCRIPCIONES as descripciones
	por_pagina: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
	resultado = []
	for clave, (etiqueta, _ayuda, pagina) in descripciones.items():
		if pagina is None:
			continue
		caracter = letra(etiqueta)
		if caracter is None:
			resultado.append(f"Página {pagina}: «{etiqueta}» ({clave}) no tiene letra de acceso.")
			continue
		por_pagina[pagina][caracter].append(etiqueta)
	for pagina, letras in por_pagina.items():
		for caracter, etiquetas in sorted(letras.items()):
			if caracter in RESERVADAS:
				resultado.append(f"Página {pagina}: la letra {caracter.upper()} de «{etiquetas[0]}» es de un botón del diálogo.")
			if len(etiquetas) > 1:
				resultado.append(f"Página {pagina}: la letra {caracter.upper()} se repite en " + ", ".join(f"«{e}»" for e in etiquetas) + ".")
	return resultado


def _candidatas(texto: str) -> list[int]:
	"""Posiciones posibles: primero los comienzos de palabra, después el resto de letras."""
	limpio = texto.replace("&", "")
	inicios = [i for i, c in enumerate(limpio) if c.isalpha() and (i == 0 or not limpio[i - 1].isalpha())]
	resto = [i for i, c in enumerate(limpio) if c.isalpha() and i not in inicios]
	return inicios + resto


def corregir(descripciones: dict) -> dict[str, str]:
	"""Etiqueta vieja → etiqueta nueva para cada una que haya que cambiar."""
	cambios: dict[str, str] = {}
	por_pagina: dict[str, list[tuple[str, str]]] = defaultdict(list)
	for clave, (etiqueta, _ayuda, pagina) in descripciones.items():
		if pagina is not None:
			por_pagina[pagina].append((clave, etiqueta))
	for elementos in por_pagina.values():
		usadas = set(RESERVADAS)
		pendientes = []
		for _clave, etiqueta in elementos:
			caracter = letra(etiqueta)
			if caracter is None or caracter in usadas:
				pendientes.append(etiqueta)
			else:
				usadas.add(caracter)
		for etiqueta in pendientes:
			limpio = etiqueta.replace("&", "")
			for posicion in _candidatas(limpio):
				caracter = _base(limpio[posicion])
				if caracter not in usadas and caracter.isascii():
					usadas.add(caracter)
					cambios[etiqueta] = limpio[:posicion] + "&" + limpio[posicion:]
					break
	return cambios


def main(argumentos: list[str] | None = None) -> int:
	analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	analizador.add_argument("--corregir", action="store_true", help="Reescribe las etiquetas con letras libres.")
	opciones = analizador.parse_args(argumentos)
	from app.core.descripciones_config import DESCRIPCIONES

	if opciones.corregir:
		texto = ARCHIVO.read_text(encoding="utf-8")
		for viejo, nuevo in corregir(DESCRIPCIONES).items():
			texto = texto.replace(f'N_("{viejo}")', f'N_("{nuevo}")', 1)
			print(f"«{viejo}» → «{nuevo}»")
		ARCHIVO.write_text(texto, encoding="utf-8", newline="\n")
		return 0
	encontrados = problemas(DESCRIPCIONES)
	for linea in encontrados:
		print(linea)
	print("Sin problemas." if not encontrados else f"{len(encontrados)} problemas.")
	return 1 if encontrados else 0


if __name__ == "__main__":
	sys.exit(main())
