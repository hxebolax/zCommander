# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Comprueba las letras de acceso de los menús del catálogo sin abrir ventanas.

Para cada menú (y submenú) del catálogo: toda etiqueta tiene «&» y ninguna
letra se repite. Lo usan las pruebas y se puede ejecutar a mano.

En la 2.0 se comprueban los menús que construye la ventana, ``ordenes.menus()``
y ``ordenes.menu_contextual()``, sobre el catálogo completo: el núcleo y los
complementos de serie (``registro.registrar_serie()`` si aún no se registraron),
con sus submenús de Complementos, «Mis órdenes» y las anclas de 14.2.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.plugins import registro  # noqa: E402
from app.ui import ordenes  # noqa: E402


def letra(etiqueta: str) -> str | None:
	i = 0
	while True:
		i = etiqueta.find("&", i)
		if i < 0 or i + 1 >= len(etiqueta):
			return None
		if etiqueta[i + 1] == "&":
			i += 2
			continue
		return etiqueta[i + 1].lower()


def problemas() -> list[str]:
	encontrados: list[str] = []

	def revisar(nombre: str, elementos) -> None:
		usadas: dict[str, str] = {}
		for elemento in elementos:
			if elemento is None:
				continue
			if isinstance(elemento, tuple):
				etiqueta, hijos = elemento
				revisar(f"{nombre} > {etiqueta}", hijos)
			else:
				etiqueta = (ordenes.ETIQUETAS_CONTEXTUAL.get(elemento) if nombre == "Contextual" else None) or ordenes.POR_ID[elemento].etiqueta
			l = letra(etiqueta)
			if l is None:
				encontrados.append(f"{nombre}: «{etiqueta}» no tiene letra de acceso")
				continue
			if l in usadas:
				encontrados.append(f"{nombre}: la letra «{l}» se repite en «{usadas[l]}» y «{etiqueta}»")
			else:
				usadas[l] = etiqueta

	barra: dict[str, str] = {}
	if not registro.complementos():
		registro.registrar_serie()
	for titulo, contenido in ordenes.menus():
		l = letra(titulo)
		if l in barra:
			encontrados.append(f"Barra: «{l}» se repite en {barra[l]} y {titulo}")
		barra[l] = titulo
		revisar(titulo, ordenes.MENU_LADO if contenido == ordenes.LADO else contenido)
	revisar("Contextual", ordenes.menu_contextual())
	return encontrados


if __name__ == "__main__":
	lista = problemas()
	print("\n".join(lista) or "Sin problemas")
	sys.exit(1 if lista else 0)
