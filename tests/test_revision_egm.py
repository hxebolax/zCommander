# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Pruebas de tools/revision_egm.py (PLANTILLA del agente «revision-egm»). Sin red ni EGM real: se simula."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("revision_egm", RAIZ / "tools" / "revision_egm.py")
revision_egm = importlib.util.module_from_spec(_spec)
sys.modules["revision_egm"] = revision_egm
_spec.loader.exec_module(revision_egm)

TODOS_LOS_REVISORES = (
	"comprehension", "style", "structural", "codebase_details", "implementation_readiness", "zoom_out", "design_critic",
)
ESTANDARES_EGM = ("feature-spec-standard", "implementation-readiness-standard", "re-implementation-standard", "zoom-out-standard")


def _egm_falso(carpeta: Path, version: str = "0.1.1") -> Path:
	(carpeta / "agents").mkdir(parents=True)
	(carpeta / "resources" / "document_standards").mkdir(parents=True)
	for nombre in TODOS_LOS_REVISORES:
		(carpeta / "agents" / f"{nombre}.md").write_text(f"---\nname: egm-{nombre.replace('_', '-')}\n---\n", encoding="utf-8")
	for nombre in ESTANDARES_EGM:
		(carpeta / "resources" / "document_standards" / f"{nombre}.md").write_text("# Estándar\n", encoding="utf-8")
	(carpeta / "plugin.json").write_text(json.dumps({"name": "egm", "version": version}), encoding="utf-8")
	return carpeta


def _proyecto(carpeta: Path) -> Path:
	(carpeta / "app").mkdir(parents=True)
	(carpeta / "app" / "ventana.py").write_text("x = 1\n", encoding="utf-8")
	(carpeta / "docs").mkdir()
	(carpeta / "docs" / "teclas.md").write_text("# Teclas\n", encoding="utf-8")
	(carpeta / "build").mkdir()
	(carpeta / "build" / "copia.py").write_text("", encoding="utf-8")
	(carpeta / "LEEME.md").write_text("# Leeme\n", encoding="utf-8")
	(carpeta / "docs" / "manual.md").write_text(
		"# Manual\n\nVer [teclas](teclas.md#ventana), el código en `app/ventana.py:10`, "
		"[la web](https://ejemplo.invalid/a.md), `build/copia.py` y `no/existe.py`.\n",
		encoding="utf-8",
	)
	estandares = carpeta / "docs" / "revision" / "estandares"
	estandares.mkdir(parents=True)
	for nombre in ("documentacion-accesible.md", "manual-usuario.md"):
		(estandares / nombre).write_text("# Estándar\n", encoding="utf-8")
	return carpeta


def test_localiza_egm_en_la_cache_de_claude_la_version_mas_nueva(tmp_path, monkeypatch):
	monkeypatch.delenv(revision_egm.VARIABLE_EGM, raising=False)
	cache = tmp_path / ".claude" / "plugins" / "cache" / "egm" / "egm"
	_egm_falso(cache / "0.1.1")
	_egm_falso(cache / "0.10.0")
	assert revision_egm.localizar_egm(casa=tmp_path) == (cache / "0.10.0").resolve()


def test_ruta_explicita_y_variable_de_entorno(tmp_path, monkeypatch):
	egm = _egm_falso(tmp_path / "clon")
	assert revision_egm.localizar_egm(egm, casa=tmp_path / "nada") == egm.resolve()
	monkeypatch.setenv(revision_egm.VARIABLE_EGM, str(egm))
	assert revision_egm.localizar_egm(casa=tmp_path / "nada") == egm.resolve()
	monkeypatch.setenv(revision_egm.VARIABLE_EGM, str(tmp_path / "no-es-egm"))
	assert revision_egm.localizar_egm(casa=tmp_path / "nada") is None


def test_inventario(tmp_path):
	inv = revision_egm.inventario(_egm_falso(tmp_path / "egm", "0.2.0"))
	assert inv.version == "0.2.0"
	assert inv.revisores["zoom_out"] == "egm-zoom-out"
	assert "feature-spec-standard" in inv.estandares


def test_contexto_cita_solo_archivos_del_proyecto(tmp_path):
	raiz = _proyecto(tmp_path / "p")
	lectura = revision_egm.contexto(raiz / "docs" / "manual.md", raiz, revision_egm.PERFILES["manual"])
	nombres = [p.relative_to(raiz).as_posix() for p in lectura]
	assert nombres == ["docs/teclas.md", "app/ventana.py", "LEEME.md"]


def test_orden_de_manual_usa_estandares_propios_y_de_egm(tmp_path):
	raiz = _proyecto(tmp_path / "p")
	inv = revision_egm.inventario(_egm_falso(tmp_path / "egm"))
	config = revision_egm.configurar(raiz / "docs" / "manual.md", "manual", raiz, inv)
	assert config.revisores == ["comprehension", "style", "structural", "codebase_details"]
	assert config.estandares["comprehension"].endswith("documentacion-accesible.md")
	assert config.estandares["structural"].endswith("manual-usuario.md")
	assert not config.avisos
	texto = config.como_texto()
	assert texto.startswith("/egm:egm-review-loop") and "español" in texto


def test_faltan_estandares_propios_avisa(tmp_path):
	raiz = _proyecto(tmp_path / "p")
	inv = revision_egm.inventario(_egm_falso(tmp_path / "egm"))
	config = revision_egm.configurar(raiz / "docs" / "manual.md", "plan", raiz, inv)
	assert "codebase_details" not in config.estandares
	assert any("plan-correccion.md" in a for a in config.avisos)
	assert config.estandares["implementation_readiness"] == "implementation-readiness-standard"


def test_revisor_que_no_existe_en_egm_se_omite(tmp_path):
	raiz = _proyecto(tmp_path / "p")
	egm = _egm_falso(tmp_path / "egm")
	(egm / "agents" / "style.md").unlink()
	config = revision_egm.configurar(raiz / "docs" / "manual.md", "manual", raiz, revision_egm.inventario(egm))
	assert "style" not in config.revisores
	assert any("style" in a for a in config.avisos)


def test_perfil_desconocido():
	with pytest.raises(ValueError):
		revision_egm.configurar(Path(__file__), "otro")


def test_resumen_del_informe():
	informe = """# Informe
| 🔴 | manual.md:3 | Falta la instalación |
- 🟡 Major: tecla sin explicar
- **Nit:** coma de más
- texto sin gravedad
"""
	hallazgos = revision_egm.leer_informe(informe)
	assert [h.gravedad for h in hallazgos] == ["🔴", "🟡", "🟢"]
	texto = revision_egm.resumen(hallazgos)
	assert texto.startswith("Hallazgos: 3 (1 bloqueante, 1 importante, 1 detalle).")
	assert "|" not in texto
	assert revision_egm.resumen([]).startswith("El informe no tiene")


INFORME_EGM = """# Goldfish Annotated Review Report

**Target:** `docs/manual.md` (`1-120`)

## Prioritized Findings & AI Suggestions

### [Issue 1] [`comprehension`] - Severity: Blocker
*   **Affected Scope:** [Lines 1-10](docs/manual.md#L1-L10) (Instalar)
*   **Discrepancy Description:** Falta cómo instalar.
*   **Rationale:** Sin eso no se puede empezar.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Es cierto.

### [Issue 2] [`style`] - Severity: Nit
*   **Discrepancy Description:** Coma de más.
*   ***AI Suggestion:*** CONTEST
"""


def test_resumen_del_informe_real_de_egm():
	hallazgos = revision_egm.leer_informe(INFORME_EGM)
	assert [(h.gravedad, h.revisor, h.texto) for h in hallazgos] == [("🔴", "comprehension", "Falta cómo instalar."), ("🟢", "style", "Coma de más.")]
	assert hallazgos[0].alcance == "Lines 1-10 (Instalar)" and hallazgos[0].sugerencia == "PROPOSE FIX"
	texto = revision_egm.resumen(hallazgos)
	assert texto.startswith("Hallazgos: 2 (1 bloqueante, 0 importantes, 1 detalle).")
	assert "revisor comprehension" in texto and "propuesta de EGM: CONTEST" in texto


def test_leyenda_y_secciones_por_gravedad():
	informe = "Leyenda: 🔴 bloqueante, 🟡 importante, 🟢 detalle\n### 🟡 Importantes\n- Falta un paso\n- Término sin explicar\nTexto suelto\n"
	hallazgos = revision_egm.leer_informe(informe)
	assert [(h.gravedad, h.texto) for h in hallazgos] == [("🟡", "Falta un paso"), ("🟡", "Término sin explicar")]


def test_rutas_con_barras_normales_y_carpeta_de_estandares(tmp_path):
	raiz = _proyecto(tmp_path / "p")
	otra = tmp_path / "agente" / "estandares"
	otra.mkdir(parents=True)
	(otra / "skill-agente.md").write_text("# Estándar\n", encoding="utf-8")
	inv = revision_egm.inventario(_egm_falso(tmp_path / "egm"))
	config = revision_egm.configurar(raiz / "docs" / "manual.md", "skill", raiz, inv, [tmp_path / "no-existe"], otra)
	assert config.estandares["structural"].endswith("/estandares/skill-agente.md")
	assert "\\" not in config.estandares["structural"]
	assert any("no-existe" in a for a in config.avisos)
	assert all("\\" not in x for x in config.como_dict()["GoldfishContext"])
	assert "español" in config.como_dict()["Indicaciones"]


def test_linea_de_ordenes(tmp_path, capsys, monkeypatch):
	monkeypatch.delenv(revision_egm.VARIABLE_EGM, raising=False)
	raiz = _proyecto(tmp_path / "p")
	egm = _egm_falso(tmp_path / "egm")
	assert revision_egm.main(["comprobar", "--egm", str(egm)]) == 0
	assert "EGM 0.1.1" in capsys.readouterr().out
	assert revision_egm.main(["orden", str(raiz / "docs" / "manual.md"), "--perfil", "manual", "--raiz", str(raiz), "--egm", str(egm), "--json"]) == 0
	datos = json.loads(capsys.readouterr().out)
	assert datos["SemanticTarget"] == "full file" and len(datos["GoldfishContext"]) == 3
	assert revision_egm.main(["perfiles"]) == 0
	assert "paridad" in capsys.readouterr().out
	assert revision_egm.main(["comprobar", "--egm", str(tmp_path / "nada")]) == 1
