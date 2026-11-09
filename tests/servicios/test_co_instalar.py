# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Actualizar, volver atrás y restaurar componentes (diseño 2.0, 6.6 y 18.2), con un servidor local y programas falsos."""

from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path

import pytest

from app.services.componentes import estado, fichas, fuentes, instalar, integrar
from app.services.componentes.fuentes import Paquete, VersionNueva
from app.services.vfs.base import NoAdmitido
from tests.servicios import apoyo_co
from tests.servicios.apoyo_co import ServidorPrueba, sha


@pytest.fixture
def servidor():
	servidor = ServidorPrueba()
	yield servidor
	servidor.cerrar()


@pytest.fixture
def entorno(tmp_path):
	return apoyo_co.crear_entorno(tmp_path / "data")


def _nueva(servidor: ServidorPrueba, version: str = "1.1.0", contenido: str | None = None, suma: str | None = None) -> VersionNueva:
	paquete = apoyo_co.zip_de({f"demo-v{version}/demo.exe": contenido if contenido is not None else f"demo v{version}"})
	url = servidor.poner(f"/demo-v{version}.zip", paquete)
	return VersionNueva("demo", version, version, [Paquete(url, f"demo-v{version}.zip", suma or sha(paquete), len(paquete),
		{f"demo-v{version}/demo.exe": "demo.exe"})])


def _sumas(carpeta: Path) -> dict[str, str]:
	return fichas.mapa_sumas(fichas.sumas_de_carpeta(carpeta))


def test_actualiza_respalda_y_deja_la_ficha(servidor, entorno):
	antes = _sumas(entorno.bin / "demo")
	fases = []
	resultado = apoyo_co.gestor(entorno, al_fase=fases.append).instalador().actualizar(_nueva(servidor))
	assert resultado.estado == instalar.ACTUALIZADO, resultado.mensaje
	assert resultado.mensaje == "Demo actualizado a 1.1.0" and resultado.sonido == "comp.actualizado"
	assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
	assert (entorno.bin / "demo" / "LICENCIA.txt").is_file(), "lo nuevo va encima de una copia de lo activo"
	ficha = estado.ficha_instalada("demo", entorno)
	assert ficha["version"] == "1.1.0" and fichas.mapa_sumas(ficha["archivos"]) == _sumas(entorno.bin / "demo")
	assert _sumas(entorno.respaldo / "demo" / "1.0.0" / "archivos") == antes
	assert not entorno.diario.exists() and not (entorno.bin / "demo.nueva").exists() and not (entorno.bin / "demo.vieja").exists()
	assert not (entorno.temporal / "demo").exists()
	assert any(f.startswith("Descargando") for f in fases) and any(f.startswith("Probando") for f in fases)
	assert estado.origen_de("demo", entorno) == "Actualizada"


def test_suma_distinta_se_rechaza_sin_tocar_nada(servidor, entorno):
	antes = _sumas(entorno.bin / "demo")
	ficha_antes = entorno.instalados.read_text(encoding="utf-8")
	resultado = apoyo_co.gestor(entorno).instalador().actualizar(_nueva(servidor, suma="0" * 64))
	assert resultado.estado == instalar.FALLIDO and "suma" in resultado.mensaje
	assert _sumas(entorno.bin / "demo") == antes and entorno.instalados.read_text(encoding="utf-8") == ficha_antes
	assert not (entorno.respaldo / "demo").exists()


def test_prueba_que_falla_antes_de_instalar_no_toca_nada(servidor, entorno):
	antes = _sumas(entorno.bin / "demo")
	resultado = apoyo_co.gestor(entorno).instalador().actualizar(_nueva(servidor, contenido="FALLA"))
	assert resultado.estado == instalar.FALLIDO and "no pasó la prueba" in resultado.mensaje
	assert _sumas(entorno.bin / "demo") == antes


def test_prueba_que_falla_tras_sustituir_vuelve_sola_al_respaldo(servidor, entorno):
	antes = _sumas(entorno.bin / "demo")
	ficha_antes = estado.ficha_instalada("demo", entorno)
	resultado = apoyo_co.gestor(entorno).instalador().actualizar(_nueva(servidor, contenido="demo v1.1.0 FALLA_EN_SU_SITIO"))
	assert resultado.estado == instalar.REVERTIDO and resultado.sonido == "comp.revertido"
	assert resultado.mensaje == "La versión 1.1.0 de Demo no funcionó y se ha vuelto a la 1.0.0. Detalles en el registro."
	assert _sumas(entorno.bin / "demo") == antes, "las sumas son las de antes"
	assert estado.ficha_instalada("demo", entorno)["version"] == ficha_antes["version"]
	assert not entorno.diario.exists() and not estado.en_mantenimiento("demo")


def test_volver_a_la_anterior_y_restaurar_los_originales(servidor, entorno):
	base = estado.ficha_base("demo", entorno)
	g = apoyo_co.gestor(entorno)
	assert g.instalador().actualizar(_nueva(servidor, "1.1.0")).estado == instalar.ACTUALIZADO
	assert g.instalador().actualizar(_nueva(servidor, "1.2.0")).estado == instalar.ACTUALIZADO
	fila = g.filas()[0]
	assert fila.puede_volver and fila.version_anterior == "1.1.0"
	resultado = g.instalador().volver_anterior("demo")
	assert resultado.estado == instalar.ACTUALIZADO and resultado.mensaje == "Demo ha vuelto a la versión 1.1.0"
	assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
	assert g.cambios_restaurar() == [("demo", "Demo", "1.1.0", "1.0.0")]
	resultado = g.instalador().restaurar_original("demo")
	assert resultado.estado == instalar.ACTUALIZADO, resultado.mensaje
	assert _sumas(entorno.bin / "demo") == fichas.mapa_sumas(base["archivos"]), "quedan las sumas de linea_base.json"
	assert g.cambios_restaurar() == []
	assert (entorno.respaldo / "demo" / "1.0.0").is_dir(), "el respaldo de la línea base se guarda siempre"
	assert len(g.instalador().respaldos("demo")) <= instalar.RESPALDOS_GUARDADOS + 1


def test_restaurar_sin_respaldo_descarga_el_paquete_exacto(servidor, entorno):
	paquete = apoyo_co.zip_de({"demo-v1.0.0/demo.exe": "demo v1.0.0"})
	url = servidor.poner("/exacto/demo-v1.0.0.zip", paquete)
	base = json.loads(entorno.linea_base.read_text(encoding="utf-8"))
	base["componentes"][0].update(url_paquete_exacta=url, sha256_paquete=sha(paquete))
	fichas.escribir(entorno.linea_base, base)
	(entorno.bin / "demo" / "demo.exe").write_text("demo v1.0.0 cambiado", encoding="utf-8")
	instalador = apoyo_co.gestor(entorno).instalador()
	assert instalador.necesita_descarga("demo")
	assert instalador.restaurar_original("demo").estado == instalar.FALLIDO, "sin permiso no se descarga"
	assert servidor.peticiones == []
	resultado = instalador.restaurar_original("demo", descargar=True)
	assert resultado.estado == instalar.ACTUALIZADO, resultado.mensaje
	assert _sumas(entorno.bin / "demo") == fichas.mapa_sumas(base["componentes"][0]["archivos"])


def test_en_uso_con_al_reiniciar_queda_pendiente_y_se_aplica_al_arrancar(servidor, tmp_path):
	ficha = apoyo_co.ficha_demo(en_uso={"procesos": [], "detener": False, "al_reiniciar": True})
	entorno = apoyo_co.crear_entorno(tmp_path / "data", [ficha])
	resultado = apoyo_co.gestor(entorno).instalador().actualizar(_nueva(servidor))
	assert resultado.estado == instalar.PENDIENTE and "se aplicará al reiniciar" in resultado.mensaje
	assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.0.0"
	assert (entorno.pendiente / "demo" / "archivos" / "demo.exe").is_file()
	assert estado.origen_de("demo", entorno) == "Pendiente de reiniciar"
	assert not estado.en_mantenimiento("demo")
	# Arranque simulado: main.py llama a aplicar_pendientes antes de cargar nada.
	mensajes = _aplicar_pendientes(tmp_path / "data")
	assert mensajes == ["Demo se actualizó a 1.1.0"]
	assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
	assert not (entorno.pendiente / "demo").exists()
	assert "comp.actualizado" in integrar.sonidos_pendientes()


def _aplicar_pendientes(ruta_datos: Path) -> list[str]:
	"""``integrar.aplicar_pendientes`` con el lanzador falso de las pruebas."""
	original = instalar.Instalador.__init__

	def con_lanzador(self, *args, **kwargs):
		original(self, *args, **kwargs)
		self.lanzar = apoyo_co.lanzar_falso
		self.esperas = apoyo_co.ESPERAS_CORTAS

	instalar.Instalador.__init__ = con_lanzador
	try:
		return integrar.aplicar_pendientes(ruta_datos)
	finally:
		instalar.Instalador.__init__ = original


def test_esperar_s_espera_a_que_acabe_su_proceso(servidor, tmp_path):
	ficha = apoyo_co.ficha_demo(en_uso={"procesos": ["demo.exe"], "detener": False, "esperar_s": 5, "al_reiniciar": False})
	entorno = apoyo_co.crear_entorno(tmp_path / "data", [ficha])
	fin = time.monotonic() + 0.6
	fases = []
	g = apoyo_co.gestor(entorno, buscar_procesos=lambda nombre: [4321] if time.monotonic() < fin else [], al_fase=fases.append)
	resultado = g.instalador().actualizar(_nueva(servidor))
	assert resultado.estado == instalar.ACTUALIZADO
	assert "Esperando a que termine Demo" in fases
	assert time.monotonic() >= fin


def test_en_uso_sin_esperar_ni_detener_queda_pendiente_y_detener_lo_libera(servidor, tmp_path):
	ficha = apoyo_co.ficha_demo(en_uso={"procesos": ["demo.exe"], "detener": True, "esperar_s": 0, "al_reiniciar": False})
	entorno = apoyo_co.crear_entorno(tmp_path / "data", [ficha])
	vivos = [1]
	g = apoyo_co.gestor(entorno, buscar_procesos=lambda nombre: list(vivos))
	estado.registrar_al_detener("demo", lambda: False)
	assert g.instalador().actualizar(_nueva(servidor)).estado == instalar.PENDIENTE
	instalar._borrar(entorno.pendiente)

	def detener() -> bool:
		vivos.clear()
		return True

	estado.registrar_al_detener("demo", detener)
	assert g.instalador().actualizar(_nueva(servidor)).estado == instalar.ACTUALIZADO
	estado.registrar_al_detener("demo", lambda: True)


def test_mantenimiento_responde_falta_a_ruta(entorno, monkeypatch):
	monkeypatch.setattr(estado.Entorno, "actual", classmethod(lambda cls: entorno))
	assert estado.ruta("demo") == entorno.bin / "demo"
	with estado.mantenimiento("demo"):
		with pytest.raises(NoAdmitido) as error:
			estado.ruta("demo")
		assert "se está actualizando" in str(error.value)
		assert not estado.disponible("demo") and estado.estado_de("demo") == "En mantenimiento"
	assert estado.disponible("demo") and estado.estado_de("demo") == "Instalado"


def test_renombrado_que_falla_se_reintenta_y_si_sigue_queda_pendiente(servidor, entorno):
	abierto = (entorno.bin / "demo" / "LICENCIA.txt").open("rb")
	threading.Timer(0.15, abierto.close).start()
	resultado = apoyo_co.gestor(entorno, esperas=(0.1, 0.2, 0.4, 0.8)).instalador().actualizar(_nueva(servidor, "1.1.0"))
	assert resultado.estado == instalar.ACTUALIZADO, "el reintento lo consigue en cuanto se suelta la carpeta"
	with (entorno.bin / "demo" / "LICENCIA.txt").open("rb"):
		resultado = apoyo_co.gestor(entorno).instalador().actualizar(_nueva(servidor, "1.2.0"))
		assert resultado.estado == instalar.PENDIENTE
		assert (entorno.bin / "demo" / "demo.exe").read_text(encoding="utf-8") == "demo v1.1.0"
		assert not (entorno.bin / "demo.nueva").exists() and not (entorno.bin / "demo.vieja").exists()
		assert not entorno.diario.exists()
	assert _aplicar_pendientes(entorno.bin.parent) == ["Demo se actualizó a 1.2.0"]


def _diario_a_medias(entorno, instalador, completa: bool) -> dict:
	"""Simula un corte de luz durante el paso 7: diario escrito, ``.nueva`` copiada (entera o no) y ``demo`` ya renombrada."""
	carpeta = entorno.bin / "demo"
	nueva = entorno.bin / "demo.nueva"
	import shutil

	shutil.copytree(carpeta, nueva)
	(nueva / "demo.exe").write_text("demo v1.1.0", encoding="utf-8")
	sumas = {a["ruta"]: a["sha256"] for a in fichas.sumas_de_carpeta(nueva)}
	if not completa:
		(nueva / "demo.exe").write_text("demo v1.1", encoding="utf-8")
	ficha_nueva = dict(estado.ficha_instalada("demo", entorno), version="1.1.0")
	fichas.escribir(entorno.diario, {"id": "demo", "carpeta": "demo", "version_anterior": "1.0.0", "version_nueva": "1.1.0",
		"paso": "renombrando", "sumas_nueva": sumas, "ficha_nueva": ficha_nueva, "ficha_anterior": estado.ficha_instalada("demo", entorno)})
	carpeta.rename(entorno.bin / "demo.vieja")
	return sumas


@pytest.mark.parametrize("completa", [True, False])
def test_diario_a_medias_se_termina_o_se_deshace(entorno, completa):
	antes = _sumas(entorno.bin / "demo")
	instalador = apoyo_co.gestor(entorno).instalador()
	sumas = _diario_a_medias(entorno, instalador, completa)
	mensaje = instalador.recuperar_diario()
	carpeta = entorno.bin / "demo"
	if completa:
		assert "Se terminó de instalar Demo 1.1.0" in mensaje
		assert _sumas(carpeta) == {k.casefold(): v for k, v in sumas.items()}
		assert estado.ficha_instalada("demo", entorno)["version"] == "1.1.0"
	else:
		assert "Se deshizo" in mensaje
		assert _sumas(carpeta) == antes
		assert estado.ficha_instalada("demo", entorno)["version"] == "1.0.0"
	assert not (entorno.bin / "demo.nueva").exists() and not (entorno.bin / "demo.vieja").exists() and not entorno.diario.exists()


def test_extrae_7z_y_pkg_tar_zst_sin_libarchive(tmp_path):
	destino = tmp_path / "nuevo"
	siete = tmp_path / "x.7z"
	siete.write_bytes(apoyo_co.siete_z_de({"x64/7za.exe": "7-Zip (a) 26.07", "x64/otro.txt": "no"}, tmp_path))
	instalar.extraer_paquete(siete, {"x64/7za.exe": "7za.exe"}, destino)
	paquete = tmp_path / "mingw-w64-ucrt-x86_64-libarchive-3.8.12-1-any.pkg.tar.zst"
	paquete.write_bytes(apoyo_co.tar_zst_de({"ucrt64/bin/libarchive-13.dll": "dll", ".PKGINFO": "x"}))
	instalar.extraer_paquete(paquete, {"ucrt64/bin/libarchive-13.dll": "libarchive-13.dll"}, destino)
	assert sorted(p.name for p in destino.iterdir()) == ["7za.exe", "libarchive-13.dll"]
	codigo = Path(instalar.__file__).read_text(encoding="utf-8")
	importados = {getattr(n, "module", None) or n.names[0].name for n in ast.walk(ast.parse(codigo)) if isinstance(n, (ast.Import, ast.ImportFrom))}
	assert not any("libarchive" in (m or "") for m in importados), "la extracción no depende de libarchive (6.6)"


def test_extraccion_segura(tmp_path):
	destino = tmp_path / "nuevo"
	malo = tmp_path / "malo.zip"
	malo.write_bytes(apoyo_co.zip_de({"../fuera.exe": "x"}))
	with pytest.raises(instalar.ErrorComponente):
		instalar.extraer_paquete(malo, {"*.exe": "."}, destino)
	falta = tmp_path / "falta.zip"
	falta.write_bytes(apoyo_co.zip_de({"a/b.txt": "x"}))
	with pytest.raises(instalar.ErrorComponente) as error:
		instalar.extraer_paquete(falta, {"a/c.exe": "c.exe"}, destino)
	assert "no trae" in error.value.mensaje
	with pytest.raises(instalar.ErrorComponente):
		instalar.extraer_paquete(falta, {"a/b.txt": "../fuera.txt"}, destino)
	assert not (tmp_path / "fuera.exe").exists() and not (tmp_path / "fuera.txt").exists()


def test_7z_con_filtro_que_py7zr_no_admite_usa_7_zip(tmp_path, monkeypatch):
	import py7zr

	siete = tmp_path / "x.7z"
	siete.write_bytes(apoyo_co.siete_z_de({"x64/7za.exe": "nuevo"}, tmp_path))

	def no_admite(self, targets=None):
		raise py7zr.exceptions.UnsupportedCompressionMethodError(b"BCJ2", "BCJ2")

	monkeypatch.setattr(py7zr.SevenZipFile, "read", no_admite)
	with pytest.raises(instalar.ErrorComponente) as error:
		instalar.extraer_paquete(siete, {"x64/7za.exe": "7za.exe"}, tmp_path / "n1", siete_zip=lambda: None)
	assert "7-Zip" in error.value.mensaje
	llamadas = []

	def lanzar(argumentos, **_opciones):
		llamadas.append(argumentos)
		salida = Path(next(a[2:] for a in argumentos if a.startswith("-o")))
		(salida / "x64").mkdir(parents=True)
		(salida / "x64" / "7za.exe").write_text("nuevo", encoding="utf-8")
		from app.core import procesos

		return procesos.ResultadoPrograma(0, b"", b"", False)

	instalar.extraer_paquete(siete, {"x64/7za.exe": "7za.exe"}, tmp_path / "n2", siete_zip=lambda: tmp_path / "7z.exe", lanzar=lanzar)
	assert (tmp_path / "n2" / "7za.exe").read_text(encoding="utf-8") == "nuevo"
	assert llamadas[0][1] == "x" and "--" in llamadas[0]


def test_integridad_marca_danado(entorno, monkeypatch):
	monkeypatch.setattr(estado.Entorno, "actual", classmethod(lambda cls: entorno))
	(entorno.bin / "demo" / "LICENCIA.txt").unlink()
	assert estado.comprobar_integridad() == ["demo"]
	with pytest.raises(NoAdmitido) as error:
		estado.ruta("demo")
	assert "Falta el componente demo: Opciones, Componentes externos, Restaurar" in str(error.value)
	assert estado.estado_de("demo") == "Dañado"
	estado.marcar_danados([])


def test_operacion_del_motor(servidor, entorno):
	from app.core.tareas import TokenCancelacion
	from app.services.operaciones.modelo import ContextoEjecucion, Estado

	g = apoyo_co.gestor(entorno)
	recibidos = []
	nueva = _nueva(servidor)
	operacion = instalar.OperacionComponente("Actualizar Demo", [("demo", lambda inst: inst.actualizar(nueva))],
		g.instalador, al_resultado=recibidos.append)
	contexto = ContextoEjecucion(TokenCancelacion(), None)
	operacion.contexto = contexto
	operacion.ejecutar(contexto)
	assert operacion.estado == Estado.TERMINADA
	assert [r.estado for r in recibidos] == [instalar.ACTUALIZADO]
	assert operacion.resumen() == "Demo actualizado a 1.1.0"


def test_fuentes_de_base(entorno):
	base = estado.ficha_base("demo", entorno)
	with pytest.raises(fuentes.ErrorFuente):
		fuentes.paquetes_de_base(base)
