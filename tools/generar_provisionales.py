# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crea los módulos provisionales de los bloques en ``app/ui/acciones`` (solo los que no existen).

Cada función del catálogo de un bloque se define como ``provisional(etiqueta)``;
el bloque sustituye después el módulo entero por su implementación.

2.0 (diseño 2.0, 14.1.1): registra antes los complementos de serie con
``registrar_serie()``; salta las órdenes cuyo manejador es de complementos o
de macros (``complementos_pl.ejecutar``, ``complementos_pl.estado`` y
``personalizar_pe.ejecutar_macro``, que N2 escribe a mano) y añade de ``EXTRA``
la función ``instalar`` de cada módulo de acciones de bloque (14.9), marcada
como provisional.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.plugins import registro  # noqa: E402
from app.ui import ordenes  # noqa: E402

EXTRA = {
	"windows_g": ["instalar", "instalar_panel"], "complementos_pl": ["instalar"], "sonidos_so": ["instalar"],
	"componentes_co": ["instalar"], "actualizar_ac": ["instalar"], "copia_cs": ["instalar"], "red_rd": ["instalar"],
	"personalizar_pe": ["instalar", "ejecutar_macro"], "nvda_nv": ["instalar"],
}
#: Manejadores que N2 escribe a mano (los dos primeros reales, el tercero provisional de PE).
A_MANO = frozenset({"complementos_pl.ejecutar", "complementos_pl.estado", "personalizar_pe.ejecutar_macro"})


def main() -> int:
	if not registro.complementos():
		registro.registrar_serie()
	modulos: dict[str, dict[str, str]] = {}
	for orden in ordenes.CATALOGO:
		if orden.bloque == "N" or orden.manejador in A_MANO:
			continue
		modulo, funcion = orden.manejador.rsplit(".", 1)
		modulos.setdefault(modulo, {})[funcion] = orden.etiqueta.replace("&", "")
		if orden.estado and orden.estado not in A_MANO:
			m, f = orden.estado.rsplit(".", 1)
			modulos.setdefault(m, {})[f] = "@estado"
	for modulo, funciones in modulos.items():
		ruta = RAIZ / "app" / "ui" / "acciones" / f"{modulo}.py"
		if ruta.exists():
			print(f"Ya existe {ruta.name}; no se toca")
			continue
		bloque = next(o.bloque for o in ordenes.CATALOGO if o.manejador.startswith(modulo + ".") and o.manejador not in A_MANO)
		lineas = [
			"# SPDX-License-Identifier: GPL-3.0-or-later",
			"# Copyright (C) 2026 hxebolax y colaboradores",
			f'"""Órdenes del bloque {bloque}: PROVISIONAL del núcleo (el bloque sustituye este módulo entero)."""',
			"",
			"from __future__ import annotations",
			"",
			"from app.ui.acciones import estado_provisional, provisional",
			"",
		]
		for funcion, etiqueta in sorted(funciones.items()):
			if etiqueta == "@estado":
				lineas.append(f"{funcion} = estado_provisional")
			else:
				lineas.append(f"{funcion} = provisional({etiqueta!r})")
		for funcion in EXTRA.get(modulo, []):
			if funcion == "ejecutar_macro":
				lineas += ["", "# Manejador de las órdenes «macro:<nombre>» del catálogo vivo (14.1.1).",
					f"{funcion} = provisional('Ejecutar una macro')"]
				continue
			lineas += ["", "", f"def {funcion}(objeto) -> None:", '\t"""Enganche del bloque al arrancar (14.9; provisional: no hace nada)."""',
				"", "", f"{funcion}.provisional = True  # type: ignore[attr-defined]"]
		ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
		print(f"Creado {ruta.name}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
