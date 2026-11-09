# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Copia de seguridad y perfiles (bloque CS, diseño 2.0, 7, 10.2 y 18.2). Sin wx.

Cada prueba trabaja con dos carpetas ``data``: la de origen (``origen``, donde
se crea la copia) y la de destino (la ``data`` temporal del ``conftest``, el
«otro ordenador»). Nunca se toca la ``data`` real. Los secretos usan DPAPI real.
"""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from app.core import paths
from app.core.configuracion import Configuracion
from app.core.secretos import AlmacenSecretos
from app.services import eventos, favoritos, recarga
from app.services.copia import cifrado, combinar, crear, ejecutables, formato, pendiente, perfil, restaurar
from app.services.copia.formato import CopiaAbierta, ErrorContrasena, ErrorCopia

CONTRASENA = "una contraseña bien larga"
RAIZ = Path(__file__).resolve().parents[2]


# ── Ayudas ────────────────────────────────────────────────────────────────────

def escribir_json(carpeta: Path, relativa: str, datos) -> Path:
	ruta = carpeta / relativa
	ruta.parent.mkdir(parents=True, exist_ok=True)
	ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
	return ruta


def leer_json(carpeta: Path, relativa: str):
	return json.loads((carpeta / relativa).read_text(encoding="utf-8"))


def secretos(carpeta: Path) -> AlmacenSecretos:
	return AlmacenSecretos(carpeta / "config" / "secretos.dat")


@pytest.fixture
def origen(tmp_path) -> Path:
	"""Un ``data`` con un poco de todo."""
	carpeta = tmp_path / "origen"
	escribir_json(carpeta, "config/settings.json", {
		"version_esquema": 2,
		"vista": {"tamano_fuente": 14},
		"editor": {"externo": "malo.exe %P", "usar_externo": True},
		"comprimidos": {"ruta_7zip": "\\\\otro\\recurso\\7z"},
		"teclado": {"personalizadas": {"copiar": ["Ctrl+K"]}},
		"ventana": {"ancho": 800},
		"seguridad": {"menus_locales_confiados": {"C:\\x": "abc"}},
		"complementos": {"permitir_sin_firma": False, "confiados": {"x": "y"}, "inhabilitados": ["zc.git"]},
	})
	escribir_json(carpeta, "config/favoritos.json", {"version": 1, "favoritos": [{"nombre": "Fotos", "ruta": "D:\\Fotos"}]})
	escribir_json(carpeta, "config/menu_usuario.json", {"version": 1, "entradas": [
		{"etiqueta": "Compilar", "ordenes": ["cmd /c make %P"]}]})
	escribir_json(carpeta, "config/alias.json", {"version": 1, "alias": [{"nombre": "ll", "orden": "dir /a %1"}]})
	escribir_json(carpeta, "config/macros.json", {"version": 1, "macros": [
		{"nombre": "Limpiar", "pasos": [{"orden": "ejecutar_linea", "argumento": "del /q %P"}]}]})
	escribir_json(carpeta, "config/conexiones.json", {"version": 1, "sitios": [{"id": "s1", "nombre": "Servidor"}]})
	(carpeta / "plantillas").mkdir(parents=True)
	(carpeta / "plantillas" / "nota.txt").write_bytes(b"Hola\r\nmundo\x00binario")
	(carpeta / "sounds_usuario" / "mio").mkdir(parents=True)
	(carpeta / "sounds_usuario" / "mio" / "op.fin.wav").write_bytes(os.urandom(2048))
	(carpeta / "logs").mkdir()
	(carpeta / "logs" / "zcommander.log").write_text("registro", encoding="utf-8")
	secretos(carpeta).guardar_varios({"ftp:s1:contrasena": "secreta", "plugin:prueba.x:token": "t", "otro:cosa": "no"})
	return carpeta


@pytest.fixture
def destino(datos_temporales) -> Path:
	datos_temporales.mkdir(parents=True, exist_ok=True)
	return datos_temporales


def crear_copia(origen: Path, ruta: Path, partes=formato.PARTES_POR_DEFECTO, modo="contrasena", tipo="copia") -> Path:
	return crear.crear_copia(ruta, partes, tipo, modo, CONTRASENA if modo == "contrasena" else None, "Prueba",
		ruta_datos=origen)


def plan_todo(copia: CopiaAbierta, destino: Path, modo="combinar", marcar_todo=True, **extra) -> restaurar.PlanRestauracion:
	analisis = ejecutables.analizar(copia, None, destino, restaurar.secretos_de_copia(copia, CONTRASENA))
	return restaurar.PlanRestauracion(partes=[p for p in copia.partes if p != "registros"], modo=modo,
		ejecutables=analisis.ids, marcados=analisis.ids if marcar_todo else set(), **extra)


def fabricar(ruta: Path, partes: dict[str, dict[str, bytes]], **manifiesto) -> Path:
	"""Una copia «ajena» hecha a mano, con sus sumas correctas."""
	datos = {"formato": 1, "tipo": "copia", "app": "zCommander", "version_app": "2.0.0", "version_esquema": 2,
		"fecha": "2026-11-20T18:30:00", "descripcion": "Ajena", "partes": {}, "secretos": {"modo": "excluidos"}}
	datos.update(manifiesto)
	with zipfile.ZipFile(ruta, "w") as zf:
		for parte, archivos in partes.items():
			filas = []
			for relativa, contenido in archivos.items():
				zf.writestr(f"partes/{parte}/{relativa}", contenido)
				filas.append({"ruta": relativa, "sha256": hashlib.sha256(contenido).hexdigest(), "tamano": len(contenido)})
			datos["partes"][parte] = {"archivos": filas}
		zf.writestr("manifiesto.json", json.dumps(datos))
	return ruta


def js(datos) -> bytes:
	return json.dumps(datos).encode("utf-8")


# ── Crear y restaurar ─────────────────────────────────────────────────────────

def test_crear_y_restaurar_en_un_data_vacio_reproduce_los_archivos(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup")
	with CopiaAbierta(ruta) as copia:
		assert not copia.danadas
		resultado = restaurar.aplicar(copia, plan_todo(copia, destino), restaurar.secretos_de_copia(copia, CONTRASENA), destino)
	assert "conexiones" in resultado.partes
	for relativa in ("config/favoritos.json", "config/menu_usuario.json", "config/alias.json", "config/macros.json",
			"config/conexiones.json", "plantillas/nota.txt", "sounds_usuario/mio/op.fin.wav"):
		assert (destino / relativa).read_bytes() == (origen / relativa).read_bytes(), relativa
	# Los registros no se restauran nunca; las contraseñas de las partes elegidas sí.
	assert not (destino / "logs" / "zcommander.log").exists()
	assert secretos(destino).obtener("ftp:s1:contrasena") == "secreta"
	assert secretos(destino).obtener("plugin:prueba.x:token") == "t"
	assert secretos(destino).obtener("otro:cosa") is None
	config = Configuracion(destino / "config" / "settings.json")
	assert config.obtener("vista.tamano_fuente") == 14
	assert config.obtener("teclado.personalizadas") == {"copiar": ["Ctrl+K"]}
	assert config.obtener("complementos.inhabilitados") == ["zc.git"]
	assert config.obtener("ventana.ancho") != 800


def test_registros_se_extraen_a_una_carpeta(origen, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["registros"], modo="excluidos")
	assert restaurar.extraer_registros(ruta, tmp_path / "soporte") == 1
	assert (tmp_path / "soporte" / "zcommander.log").read_text(encoding="utf-8") == "registro"


def test_secretos_con_la_contrasena_y_una_mala_no_restaura_nada(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup")
	with zipfile.ZipFile(ruta) as zf:
		assert b"secreta" not in zf.read("secretos.bin")
		manifiesto = json.loads(zf.read("manifiesto.json"))
	assert manifiesto["secretos"]["kdf"]["n"] == 2 ** 17 and manifiesto["secretos"]["cifrado"] == "AES-256-GCM"
	with CopiaAbierta(ruta) as copia:
		assert restaurar.secretos_de_copia(copia, CONTRASENA)["ftp:s1:contrasena"] == "secreta"
		with pytest.raises(ErrorContrasena) as error:
			restaurar.secretos_de_copia(copia, "otra contraseña")
	assert error.value.mensaje == "La contraseña no es correcta o la copia está dañada."
	antes = sorted(p for p in destino.rglob("*"))
	plan = restaurar.PlanRestauracion(partes=["personalizacion", "conexiones"])
	with pytest.raises(ErrorContrasena):
		restaurar.restaurar_ahora(ruta, plan, "otra contraseña", destino)
	assert sorted(p for p in destino.rglob("*")) == antes


def test_secretos_de_otra_copia_no_se_pueden_mezclar(origen, tmp_path):
	"""Los datos asociados (SHA-256 del manifiesto canónico) impiden usar el secretos.bin de otra copia."""
	una = crear_copia(origen, tmp_path / "una.zcbackup", partes=["conexiones"])
	otra = crear_copia(origen, tmp_path / "otra.zcbackup", partes=["conexiones"])
	with zipfile.ZipFile(otra) as zf:
		ajeno = zf.read("secretos.bin")
	with zipfile.ZipFile(una) as zf:
		manifiesto = json.loads(zf.read("manifiesto.json"))
	with pytest.raises(ErrorContrasena):
		cifrado.descifrar(ajeno, CONTRASENA, manifiesto)


def test_manifiesto_canonico_no_depende_del_orden_de_las_claves():
	a = {"formato": 1, "tipo": "copia", "partes": {"b": 1, "a": 2}, "secretos": {"modo": "contrasena", "nombres": ["x"]}}
	b = {"secretos": {"nombres": ["y", "z"], "modo": "contrasena"}, "partes": {"a": 2, "b": 1}, "tipo": "copia", "formato": 1}
	assert formato.manifiesto_canonico(a) == formato.manifiesto_canonico(b)
	assert b"nombres" not in formato.manifiesto_canonico(a)
	assert cifrado.datos_asociados(a) == cifrado.datos_asociados(b)


def test_scrypt_usa_maxmem_suficiente():
	kdf = cifrado.parametros_kdf()
	assert cifrado.maxmem(kdf["n"], kdf["r"]) == 128 * 8 * (2 ** 17 + 2) + 64 * 1024 * 1024
	assert len(cifrado.derivar_clave("x", kdf)) == 32
	with pytest.raises(ErrorCopia):
		cifrado.derivar_clave("x", dict(kdf, n=2 ** 30))


def test_fortaleza_en_texto():
	assert cifrado.fortaleza("corta").startswith("Débil: menos de 12 caracteres")
	assert cifrado.fortaleza("Una-Contraseña-Larga-2026") == "Fuerte"


def test_copia_de_formato_99_se_rechaza(tmp_path):
	ruta = fabricar(tmp_path / "nueva.zcbackup", {}, formato=99)
	with pytest.raises(ErrorCopia) as error:
		formato.leer_manifiesto(ruta)
	assert "versión más nueva" in error.value.mensaje
	ruta = fabricar(tmp_path / "version.zcbackup", {}, version_app="9.0.0", version_esquema=7)
	assert formato.leer_manifiesto(ruta).avisos


def test_suma_que_no_coincide_anula_su_parte(origen, destino, tmp_path):
	ruta = fabricar(tmp_path / "danada.zcbackup", {"personalizacion": {"config/favoritos.json": js({"favoritos": []})},
		"macros": {"config/macros.json": js({"macros": []})}})
	with zipfile.ZipFile(ruta, "a") as zf, pytest.warns(UserWarning):
		zf.writestr("partes/macros/config/macros.json", b"otro contenido")
	with CopiaAbierta(ruta) as copia:
		assert "macros" in copia.danadas and "personalizacion" not in copia.danadas
		resultado = restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["personalizacion", "macros"]), None, destino)
	assert resultado.partes == ["personalizacion"]
	assert any("dañada" in a for a in resultado.avisos)
	assert not (destino / "config" / "macros.json").exists()


def test_rutas_peligrosas_de_una_copia_ajena_se_ignoran(destino, tmp_path):
	ruta = fabricar(tmp_path / "ajena.zcbackup", {"complementos": {
		"config/plugins/claves.json": b'{"claves": {}}',
		"../../malo.py": b"print(1)",
		"config/plugins/../../plugins/x/__init__.py": b"print(1)",
		"config/plugins/zc.prueba.json": js({"ajustes": {"a": 1}}),
	}})
	with CopiaAbierta(ruta) as copia:
		assert [a.ruta for a in copia.archivos("complementos")] == ["config/plugins/zc.prueba.json"]
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["complementos"]), None, destino)
	assert not (destino / "config" / "plugins" / "claves.json").exists()
	assert not (destino.parent / "malo.py").exists() and not (destino / "plugins").exists()
	assert (destino / "config" / "plugins" / "zc.prueba.json").exists()


# ── Combinar y sustituir ──────────────────────────────────────────────────────

def test_combinar_favoritos_anade_los_nuevos_y_conserva_los_actuales(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["personalizacion"], modo="excluidos")
	escribir_json(destino, "config/favoritos.json", {"version": 1, "favoritos": [
		{"nombre": "Mis fotos", "ruta": "d:\\fotos\\"}, {"nombre": "Música", "ruta": "E:\\Música"}]})
	with CopiaAbierta(ruta) as copia:
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["personalizacion"]), None, destino)
	nombres = [f["nombre"] for f in leer_json(destino, "config/favoritos.json")["favoritos"]]
	assert nombres == ["Mis fotos", "Música"]
	escribir_json(origen, "config/favoritos.json", {"version": 1, "favoritos": [{"nombre": "Nuevo", "ruta": "F:\\Nuevo"}]})
	ruta = crear_copia(origen, tmp_path / "c2.zcbackup", partes=["personalizacion"], modo="excluidos")
	with CopiaAbierta(ruta) as copia:
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["personalizacion"]), None, destino)
	nombres = [f["nombre"] for f in leer_json(destino, "config/favoritos.json")["favoritos"]]
	assert nombres == ["Mis fotos", "Música", "Nuevo"]


def test_sustituir_deja_la_parte_igual_que_en_la_copia(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["personalizacion"], modo="excluidos")
	escribir_json(destino, "config/favoritos.json", {"version": 1, "favoritos": [{"nombre": "Música", "ruta": "E:\\Música"}]})
	escribir_json(destino, "config/busquedas.json", {"version": 1, "busquedas": []})
	(destino / "plantillas").mkdir()
	(destino / "plantillas" / "otra.txt").write_text("x", encoding="utf-8")
	with CopiaAbierta(ruta) as copia:
		restaurar.aplicar(copia, plan_todo(copia, destino, modo="sustituir"), None, destino)
	assert (destino / "config" / "favoritos.json").read_bytes() == (origen / "config" / "favoritos.json").read_bytes()
	assert not (destino / "config" / "busquedas.json").exists()
	assert not (destino / "plantillas" / "otra.txt").exists()
	locales = sorted(r for r, _ in crear.archivos_de_parte("personalizacion", destino))
	assert locales == sorted(r for r, _ in crear.archivos_de_parte("personalizacion", origen))


def test_copia_automatica_previa_y_restaurarla_deja_el_estado_anterior(origen, destino, tmp_path):
	escribir_json(destino, "config/favoritos.json", {"version": 1, "favoritos": [{"nombre": "Antes", "ruta": "C:\\Antes"}]})
	antes = (destino / "config" / "favoritos.json").read_bytes()
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["personalizacion"], modo="excluidos")
	plan = restaurar.PlanRestauracion(partes=["personalizacion"], modo="sustituir")
	resultado = restaurar.restaurar_ahora(ruta, plan, None, destino)
	assert resultado.ok and resultado.copia_previa is not None and resultado.copia_previa.is_file()
	assert resultado.copia_previa.parent == destino / "backups" / "automaticas"
	assert formato.leer_manifiesto(resultado.copia_previa).tipo == "automatica"
	assert (destino / "config" / "favoritos.json").read_bytes() != antes
	restaurar.volver_atras(resultado.copia_previa, ["personalizacion"], destino)
	assert (destino / "config" / "favoritos.json").read_bytes() == antes


def test_las_automaticas_se_podan(destino):
	escribir_json(destino, "config/settings.json", {"copia": {"conservar_automaticas": 2}})
	for _vez in range(4):
		crear.crear_automatica(["macros"], destino)
	assert len(list((destino / "backups" / "automaticas").glob("*.zcbackup"))) == 2


def test_un_fallo_a_medias_vuelve_a_la_copia_previa(origen, destino, tmp_path, monkeypatch):
	escribir_json(destino, "config/favoritos.json", {"version": 1, "favoritos": []})
	antes = (destino / "config" / "favoritos.json").read_bytes()
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["personalizacion"], modo="excluidos")
	original = restaurar._Aplicador._archivo
	llamadas = []

	def fallar(self, parte, relativa, local):
		llamadas.append(relativa)
		original(self, parte, relativa, local)
		if len(llamadas) == 2 and not self.plan.sustituir:
			raise OSError("disco lleno")

	monkeypatch.setattr(restaurar._Aplicador, "_archivo", fallar)
	resultado = restaurar.restaurar_ahora(ruta, restaurar.PlanRestauracion(partes=["personalizacion"]), None, destino)
	assert not resultado.ok and "estado anterior" in resultado.mensaje
	assert (destino / "config" / "favoritos.json").read_bytes() == antes


# ── En el momento y bus ───────────────────────────────────────────────────────

def test_parte_en_el_momento_emite_al_restaurar_y_el_servicio_vuelve_a_leer(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["personalizacion"], modo="excluidos")
	recibidos, recargas = [], []
	bus = eventos.bus()
	bus.suscribir(eventos.AL_RESTAURAR, lambda partes=(), **_d: recibidos.append(list(partes)))
	cancelaciones = recarga.suscribir_restauracion(bus)
	cancelar = recarga.al_recargar("app.services.favoritos", lambda: recargas.append([f.nombre for f in favoritos.cargar()]))
	try:
		assert restaurar.es_inmediata(["personalizacion", "macros", "sonidos"])
		resultado = restaurar.restaurar_ahora(ruta, restaurar.PlanRestauracion(partes=["personalizacion"]), None, destino)
	finally:
		cancelar()
		for funcion in cancelaciones:
			funcion()
	assert resultado.ok
	assert recibidos == [["personalizacion"]]
	assert recargas == [["Fotos"]]


# ── Restauración pendiente ────────────────────────────────────────────────────

def _preparar(origen: Path, destino: Path, tmp_path: Path, reiniciar_ahora=False, partes=("preferencias", "conexiones")):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=list(partes))
	with CopiaAbierta(ruta) as copia:
		plan = plan_todo(copia, destino)
		secretos_copia = restaurar.secretos_de_copia(copia, CONTRASENA)
	return pendiente.preparar_pendiente(ruta, plan, secretos_copia, destino, "Antes de cambiar de equipo", reiniciar_ahora)


def test_pendiente_se_aplica_antes_de_cargar_la_configuracion(origen, destino, tmp_path):
	_preparar(origen, destino, tmp_path, reiniciar_ahora=True)
	assert not (destino / "config" / "settings.json").exists()
	resultado = pendiente.aplicar_pendiente(destino, None)
	assert resultado is not None and resultado.ok, resultado
	assert not pendiente.carpeta_pendiente(destino).exists()
	config = Configuracion(destino / "config" / "settings.json")
	assert config.obtener("vista.tamano_fuente") == 14
	assert secretos(destino).obtener("ftp:s1:contrasena") == "secreta"
	# main.py la llama antes de crear la configuración (14.8, paso 5 antes del 7).
	texto = (RAIZ / "main.py").read_text(encoding="utf-8")
	principal = texto[texto.index("def _principal("):]
	assert principal.index("aplicar_pendiente(") < principal.index("Configuracion()")


def test_pendiente_con_mas_tarde_pregunta_y_descartar_borra_la_carpeta(origen, destino, tmp_path):
	_preparar(origen, destino, tmp_path)
	preguntas = []
	assert pendiente.aplicar_pendiente(destino, None) is None  # modo tarea: se deja
	assert pendiente.aplicar_pendiente(destino, lambda info: preguntas.append(info) or "despues") is None
	assert pendiente.carpeta_pendiente(destino).is_dir()
	info = preguntas[0]
	assert info.descripcion == "Antes de cambiar de equipo" and info.partes == ["preferencias", "conexiones"]
	assert pendiente.consultar_pendiente(destino) == info
	resultado = pendiente.aplicar_pendiente(destino, lambda info: "descartar")
	assert resultado is not None and resultado.ok
	assert not pendiente.carpeta_pendiente(destino).exists()
	assert not (destino / "config" / "settings.json").exists()


def test_decidir_pendiente_aplicar_y_descartar(origen, destino, tmp_path):
	_preparar(origen, destino, tmp_path)
	pendiente.decidir_pendiente(destino, "aplicar")
	assert pendiente.aplicar_pendiente(destino, lambda info: pytest.fail("no debe preguntar")).ok
	_preparar(origen, destino, tmp_path)
	pendiente.decidir_pendiente(destino, "descartar")
	assert pendiente.consultar_pendiente(destino) is None


def test_la_copia_previa_de_una_pendiente_se_crea_al_aplicarla(origen, destino, tmp_path):
	automaticas = destino / "backups" / "automaticas"
	escribir_json(destino, "config/settings.json", {"vista": {"tamano_fuente": 9}})
	_preparar(origen, destino, tmp_path)
	assert not automaticas.exists() or not list(automaticas.iterdir())
	# Lo que la persona cambia después de prepararla es lo que guarda la copia previa.
	escribir_json(destino, "config/settings.json", {"vista": {"tamano_fuente": 11}})
	resultado = pendiente.aplicar_pendiente(destino, lambda info: "aplicar")
	assert resultado.ok and resultado.copia_previa.parent == automaticas
	with CopiaAbierta(resultado.copia_previa) as previa:
		assert previa.valores("preferencias")["vista.tamano_fuente"] == 11


def test_pendiente_danada_se_descarta_sin_lanzar(destino):
	carpeta = pendiente.carpeta_pendiente(destino)
	carpeta.mkdir(parents=True)
	(carpeta / "restaurar.json").write_text("{roto", encoding="utf-8")
	resultado = pendiente.aplicar_pendiente(destino, None)
	assert resultado is not None and not resultado.ok
	assert not carpeta.exists()


# ── Lo que hace ejecutar algo ─────────────────────────────────────────────────

def test_menu_alias_y_7zip_no_se_restauran_sin_marcarlos(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["preferencias", "personalizacion", "macros"],
		modo="excluidos")
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		textos = {e.id: e.texto for e in analisis.elementos}
		assert textos["menu_usuario:Compilar"] == "Menú de usuario: Compilar → cmd /c make %P"
		assert textos["alias:ll"] == "Alias ll: dir /a %1"
		assert textos["clave:comprimidos.ruta_7zip"] == "Carpeta de 7-Zip: \\\\otro\\recurso\\7z"
		assert textos["clave:editor.externo"] == "Editor externo: malo.exe %P"
		assert "macros:Limpiar" in textos
		plan = restaurar.PlanRestauracion(partes=copia.partes, ejecutables=analisis.ids, marcados={"alias:ll"})
		restaurar.aplicar(copia, plan, None, destino)
	config = Configuracion(destino / "config" / "settings.json")
	assert config.obtener("comprimidos.ruta_7zip") == ""
	assert config.obtener("editor.externo") == "notepad.exe %P"
	assert config.obtener("vista.tamano_fuente") == 14
	assert not (destino / "config" / "menu_usuario.json").exists()
	assert not (destino / "config" / "macros.json").exists()
	assert leer_json(destino, "config/alias.json")["alias"] == [{"nombre": "ll", "orden": "dir /a %1"}]


def test_sustituir_conserva_lo_actual_de_lo_no_marcado(destino, tmp_path):
	escribir_json(destino, "config/menu_usuario.json", {"version": 1, "entradas": [{"etiqueta": "Compilar", "ordenes": ["mio"]}]})
	ruta = fabricar(tmp_path / "ajena.zcbackup", {"personalizacion": {"config/menu_usuario.json": js({"version": 1, "entradas": [
		{"etiqueta": "Compilar", "ordenes": ["malo"]}, {"etiqueta": "Otra", "ordenes": ["otro"]}]})}})
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		plan = restaurar.PlanRestauracion(partes=["personalizacion"], modo="sustituir", ejecutables=analisis.ids,
			marcados={"menu_usuario:Otra"})
		restaurar.aplicar(copia, plan, None, destino)
	entradas = leer_json(destino, "config/menu_usuario.json")["entradas"]
	assert {e["etiqueta"]: e["ordenes"] for e in entradas} == {"Compilar": ["mio"], "Otra": ["otro"]}


def test_la_copia_no_lleva_ni_restaura_claves_de_confianza(origen, destino, tmp_path):
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", modo="excluidos")
	with CopiaAbierta(ruta) as copia:
		todas = {k for p in ("preferencias", "teclas", "complementos") for k in copia.valores(p)}
	assert not any(k.startswith("seguridad.") for k in todas)
	assert not todas & formato.CLAVES_CONFIANZA
	assert "complementos.inhabilitados" in todas and not any(k.startswith("ventana.") for k in todas)
	ajena = fabricar(tmp_path / "ajena.zcbackup", {
		"preferencias": {"valores.json": js({"seguridad.menus_locales_confiados": {"C:\\malo": "x"}, "vista.tamano_fuente": 20})},
		"complementos": {"valores.json": js({"complementos.permitir_sin_firma": True, "complementos.confiados": {"malo": "x"},
			"complementos.modo_desarrollo": True})},
	})
	escribir_json(destino, "config/settings.json", {"complementos": {"permitir_sin_firma": False}})
	with CopiaAbierta(ajena) as copia:
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["preferencias", "complementos"], modo="sustituir"),
			None, destino)
	config = Configuracion(destino / "config" / "settings.json")
	assert config.obtener("vista.tamano_fuente") == 20
	assert config.obtener("complementos.permitir_sin_firma") is False
	assert config.obtener("complementos.confiados") == {}
	assert config.obtener("complementos.modo_desarrollo") is False
	assert config.obtener("seguridad.menus_locales_confiados") == {}


def _complemento(carpeta: Path, id_complemento: str, ejecuta: bool = True) -> None:
	plugin = carpeta / "plugins" / id_complemento
	plugin.mkdir(parents=True)
	(plugin / "manifiesto.toml").write_text(
		f'formato = 1\nid = "{id_complemento}"\nversion = "1.2.0"\n'
		f'[[configuracion]]\nclave = "ruta_git"\ntipo = "texto"\ndefecto = ""\nejecuta = {str(ejecuta).lower()}\n'
		'[[configuracion]]\nclave = "colores"\ntipo = "bool"\ndefecto = false\n', encoding="utf-8")
	(plugin / "__init__.py").write_text("class Complemento: pass\n", encoding="utf-8")
	(plugin / "firma.ed25519").write_bytes(b"firma")
	(plugin / "__pycache__").mkdir()
	(plugin / "__pycache__" / "x.pyc").write_bytes(b"x")
	escribir_json(carpeta, f"config/plugins/{id_complemento}.json",
		{"version_esquema": 1, "ajustes": {"ruta_git": "C:\\malo\\git.exe", "colores": True}})


def test_parte_complementos_ofrece_los_paquetes_y_no_escribe_en_plugins(origen, destino, tmp_path):
	_complemento(origen, "prueba.git")
	escribir_json(origen, "config/plugins/claves.json", {"claves": {"autor": "clave"}})
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["complementos"], modo="excluidos")
	with zipfile.ZipFile(ruta) as zf:
		nombres = zf.namelist()
		paquete = zipfile.ZipFile(__import__("io").BytesIO(zf.read("partes/complementos/paquetes/prueba.git.zcplugin")))
	assert not any("claves.json" in n for n in nombres)
	assert sorted(paquete.namelist()) == ["__init__.py", "firma.ed25519", "manifiesto.toml"]
	with CopiaAbierta(ruta) as copia:
		lista = copia.leer_json("complementos", "lista.json")
		assert {"id": "prueba.git", "version": "1.2.0", "serie": False} in lista["instalados"]
		assert "complementos.confiados" not in copia.valores("complementos")
		resultado = restaurar.aplicar(copia, plan_todo(copia, destino), None, destino)
	assert resultado.por_instalar == ["prueba.git"]
	assert not (destino / "plugins").exists()
	assert not (destino / "config" / "plugins" / "claves.json").exists()
	assert [p["id"] for p in restaurar.leer_por_instalar(destino)] == ["prueba.git"]
	assert (restaurar.carpeta_por_instalar(destino) / "prueba.git.zcplugin").is_file()
	restaurar.quitar_por_instalar({"prueba.git"}, destino, borrar_archivos=True)
	assert restaurar.leer_por_instalar(destino) == []


def test_clave_de_complemento_con_ejecuta_no_se_restaura_sin_marcarla(origen, destino, tmp_path):
	_complemento(origen, "prueba.git")
	ruta = crear_copia(origen, tmp_path / "c.zcbackup", partes=["complementos"], modo="excluidos")
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		assert "plugin:prueba.git:ruta_git" in analisis.ids and "plugin:prueba.git:colores" not in analisis.ids
		plan = restaurar.PlanRestauracion(partes=["complementos"], ejecutables=analisis.ids, marcados=set(),
			ofrecer_complementos=False)
		restaurar.aplicar(copia, plan, None, destino)
	assert leer_json(destino, "config/plugins/prueba.git.json")["ajustes"] == {"colores": True}
	with CopiaAbierta(ruta) as copia:
		plan.marcados = {"plugin:prueba.git:ruta_git"}
		restaurar.aplicar(copia, plan, None, destino)
	assert leer_json(destino, "config/plugins/prueba.git.json")["ajustes"]["ruta_git"] == "C:\\malo\\git.exe"


def test_configuracion_de_un_complemento_desconocido_es_un_solo_elemento(destino, tmp_path):
	ruta = fabricar(tmp_path / "ajena.zcbackup", {"complementos": {
		"config/plugins/ajeno.raro.json": js({"ajustes": {"programa": "malo.exe"}})}})
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		assert analisis.ids == {"plugin:ajeno.raro:*"}
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["complementos"], ejecutables=analisis.ids), None, destino)
	assert not (destino / "config" / "plugins" / "ajeno.raro.json").exists()


def test_reglas_del_monitor_y_tareas_del_programador_piden_marcarlas(destino, tmp_path):
	ruta = fabricar(tmp_path / "ajena.zcbackup", {"complementos": {
		"config/plugins/zc.monitor.json": js({"ajustes": {"reglas": [{"accion": "macro", "macro": "Limpiar"}]}}),
		"config/plugins/zc.programador/tareas.json": js({"tareas": [{"nombre": "Borrar"}]}),
	}})
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		assert {"plugin:zc.monitor:reglas", "programador:*"} <= analisis.ids
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["complementos"], ejecutables=analisis.ids), None, destino)
	assert not (destino / "config" / "plugins" / "zc.programador" / "tareas.json").exists()
	assert "reglas" not in leer_json(destino, "config/plugins/zc.monitor.json")["ajustes"]


# ── Huellas ───────────────────────────────────────────────────────────────────

CLAVE_A = "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
CLAVE_B = "AAAAC3NzaC1lZDI1NTE5AAAAIEbP8ZAzLyrBt3m7y8hjo9uQKmxBQ2mo6R5W6hyIqvUq"


def test_al_combinar_una_huella_nueva_no_se_anade_sin_confirmarla(destino, tmp_path):
	(destino / "config").mkdir(exist_ok=True)
	(destino / "config" / "known_hosts").write_text(f"conocido.es ssh-ed25519 {CLAVE_A}\n", encoding="utf-8")
	known = f"conocido.es ssh-ed25519 {CLAVE_A}\nsftp.ejemplo.com ssh-ed25519 {CLAVE_B}\n[otro.es]:2222 ssh-ed25519 {CLAVE_B}\n"
	tls = {"version": 1, "huellas": {"ftp.ejemplo.com:21": "SHA256:abc"}}
	ruta = fabricar(tmp_path / "ajena.zcbackup", {"conexiones": {"config/known_hosts": known.encode(),
		"config/hosts_conocidos.json": js(tls)}})
	with CopiaAbierta(ruta) as copia:
		huellas = combinar.huellas_ssh(copia.leer("conexiones", "config/known_hosts"),
			(destino / "config" / "known_hosts").read_bytes())
		huellas += combinar.huellas_tls(copia.leer_json("conexiones", "config/hosts_conocidos.json"), None)
		assert [(h.servidor, h.puerto) for h in huellas] == [("sftp.ejemplo.com", 22), ("otro.es", 2222), ("ftp.ejemplo.com", 21)]
		assert "sftp.ejemplo.com, puerto 22 (ssh-ed25519 SHA256:" in huellas[0].pregunta()
		plan = restaurar.PlanRestauracion(partes=["conexiones"], huellas_aceptadas={huellas[1].id})
		restaurar.aplicar(copia, plan, None, destino)
	texto = (destino / "config" / "known_hosts").read_text(encoding="utf-8")
	assert "conocido.es" in texto and "[otro.es]:2222" in texto and "sftp.ejemplo.com" not in texto
	assert leer_json(destino, "config/hosts_conocidos.json")["huellas"] == {}


def test_sustituir_cambia_todas_las_huellas(destino, tmp_path):
	(destino / "config").mkdir(exist_ok=True)
	(destino / "config" / "known_hosts").write_text(f"local.es ssh-ed25519 {CLAVE_A}\n", encoding="utf-8")
	ruta = fabricar(tmp_path / "c.zcbackup", {"conexiones": {"config/known_hosts": f"copia.es ssh-ed25519 {CLAVE_B}\n".encode()}})
	with CopiaAbierta(ruta) as copia:
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["conexiones"], modo="sustituir"), None, destino)
	assert (destino / "config" / "known_hosts").read_text(encoding="utf-8") == f"copia.es ssh-ed25519 {CLAVE_B}\n"


# ── rclone ────────────────────────────────────────────────────────────────────

RCLONE_CLARO = (b"[trabajo]\ntype = webdav\nurl = https://dav.ejemplo.com\nbearer_token_command = obtener-token.cmd\n\n"
	b"[fotos]\ntype = drive\nscope = drive\n")


def _copia_nubes(tmp_path: Path, contenido: bytes, secretos_bin: dict | None = None) -> Path:
	return fabricar(tmp_path / "nubes.zcbackup", {"conexiones": {
		"config/rclone.conf": contenido,
		"config/plugins/zc.nubes/cuentas.json": js({"version": 1, "cuentas": [
			{"id": "trabajo", "nombre": "Trabajo"}, {"id": "fotos", "nombre": "Fotos"}]}),
	}})


def test_remoto_de_rclone_que_ejecuta_se_lista_sin_marcar_y_no_se_restaura(destino, tmp_path):
	ruta = _copia_nubes(tmp_path, RCLONE_CLARO)
	with CopiaAbierta(ruta) as copia:
		analisis = ejecutables.analizar(copia, None, destino)
		assert [e.texto for e in analisis.elementos] == [
			"Cuenta de nube Trabajo (WEBDAV): ejecuta obtener-token.cmd para conectarse (bearer_token_command)"]
		plan = restaurar.PlanRestauracion(partes=["conexiones"], ejecutables=analisis.ids)
		resultado = restaurar.aplicar(copia, plan, None, destino)
	conf = (destino / "config" / "rclone.conf").read_text(encoding="utf-8")
	assert "[fotos]" in conf and "trabajo" not in conf and "obtener-token" not in conf
	cuentas = leer_json(destino, "config/plugins/zc.nubes/cuentas.json")["cuentas"]
	assert cuentas[0].get("volver_a_configurar") is True and "volver_a_configurar" not in cuentas[1]
	assert any("trabajo" in a for a in resultado.avisos)


def test_combinar_conserva_las_cuentas_de_nube_que_ya_hay(destino, tmp_path):
	escribir_json(destino, "config/plugins/zc.nubes/cuentas.json", {"version": 1, "cuentas": [{"id": "mia"}]})
	ruta = _copia_nubes(tmp_path, RCLONE_CLARO)
	with CopiaAbierta(ruta) as copia:
		resultado = restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["conexiones"]), None, destino)
	assert not (destino / "config" / "rclone.conf").exists()
	assert leer_json(destino, "config/plugins/zc.nubes/cuentas.json")["cuentas"] == [{"id": "mia"}]
	assert any("hay que añadirlas de nuevo" in a for a in resultado.avisos)


def _rclone() -> Path:
	return RAIZ / "data" / "bin" / "rclone" / "rclone.exe"


@pytest.mark.skipif(not (RAIZ / "data" / "bin" / "rclone" / "rclone.exe").is_file(), reason="Sin rclone en data/bin")
def test_rclone_cifrado_se_lee_y_se_edita_con_rclone(destino, tmp_path):
	from app.core import procesos

	conf = tmp_path / "rclone.conf"
	conf.write_bytes(b"")
	clave = "clave-de-prueba-rclone"
	resultado = procesos.lanzar([str(_rclone()), "config", "encryption", "set", "--config", str(conf)],
		entrada=f"{clave}\n{clave}\n".encode(), tiempo_s=60)
	assert resultado.codigo == 0, resultado.errores
	entorno = {"RCLONE_CONFIG_PASS": clave}
	for argumentos in (["trabajo", "webdav", "url=https://dav.ejemplo.com", "bearer_token_command=obtener-token.cmd"],
			["fotos", "local"]):
		hecho = procesos.lanzar([str(_rclone()), "config", "create", *argumentos, "--config", str(conf), "--non-interactive",
			"--ask-password=false"], entorno=entorno, tiempo_s=60)
		assert hecho.codigo == 0, hecho.errores
	contenido = conf.read_bytes()
	assert rclone.cifrado(contenido) and b"obtener-token" not in contenido
	ruta = _copia_nubes(tmp_path, contenido)
	secretos_copia = {"plugin:zc.nubes:rclone_config_pass": clave}
	with CopiaAbierta(ruta) as copia:
		sin = ejecutables.analizar(copia, None, destino)
		assert sin.rclone_sin_revisar and not sin.elementos
		analisis = ejecutables.analizar(copia, None, destino, secretos_copia, _rclone())
		assert analisis.ids == {"rclone:trabajo"}
		plan = restaurar.PlanRestauracion(partes=["conexiones"], ejecutables=analisis.ids)
		restaurar.aplicar(copia, plan, secretos_copia, destino, ejecutable_rclone=_rclone())
	restaurado = (destino / "config" / "rclone.conf").read_bytes()
	assert rclone.cifrado(restaurado)
	remotos = rclone.remotos(restaurado, clave, tmp_path, _rclone())
	assert set(remotos) == {"fotos"}
	assert secretos(destino).obtener("plugin:zc.nubes:rclone_config_pass") == clave


from app.services.copia import rclone  # noqa: E402


# ── Migración ─────────────────────────────────────────────────────────────────

def test_copia_de_una_version_anterior_se_migra_al_restaurar(destino, tmp_path):
	ruta = fabricar(tmp_path / "vieja.zcbackup", {"preferencias": {"valores.json": js({
		"accesibilidad.tonos_progreso": True, "ftp.avisar_sin_cifrar": False, "vista.tamano_fuente": 16})}},
		version_esquema=1, version_app="0.9.0")
	with CopiaAbierta(ruta) as copia:
		assert not copia.manifiesto.avisos
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["preferencias"]), None, destino)
	config = Configuracion(destino / "config" / "settings.json")
	assert config.obtener("sonidos.progreso") == "cada_10"
	assert "ftp_sin_cifrar" in config.obtener("general.no_preguntar")
	assert config.obtener("vista.tamano_fuente") == 16
	assert "tonos_progreso" not in leer_json(destino, "config/settings.json").get("accesibilidad", {})


def test_claves_de_una_version_mas_nueva_se_conservan(destino, tmp_path):
	ruta = fabricar(tmp_path / "nueva.zcbackup", {"preferencias": {"valores.json": js({"vista.algo_futuro": 3})}},
		version_esquema=9, version_app="3.0.0")
	with CopiaAbierta(ruta) as copia:
		assert copia.manifiesto.avisos
		restaurar.aplicar(copia, restaurar.PlanRestauracion(partes=["preferencias"]), None, destino)
	Configuracion(destino / "config" / "settings.json")
	assert leer_json(destino, "config/settings.json")["vista"]["algo_futuro"] == 3


# ── Perfiles ──────────────────────────────────────────────────────────────────

def test_zcperfil_nunca_lleva_secretos_ni_conexiones(origen, tmp_path):
	ruta = perfil.exportar(tmp_path / "curso.zcperfil", incluir_sonidos=True, ruta_datos=origen)
	with zipfile.ZipFile(ruta) as zf:
		nombres = zf.namelist()
		manifiesto = json.loads(zf.read("manifiesto.json"))
	assert "secretos.bin" not in nombres and not any(n.startswith("partes/conexiones/") for n in nombres)
	assert manifiesto["tipo"] == "perfil" and manifiesto["secretos"] == {"modo": "excluidos"}
	assert set(manifiesto["partes"]) == {"preferencias", "teclas", "personalizacion", "macros", "sonidos"}
	# Aunque se pida, crear un perfil quita conexiones y secretos.
	otra = crear.crear_copia(tmp_path / "p2.zcperfil", formato.PARTES_POR_DEFECTO, "perfil", "contrasena", "x", "",
		ruta_datos=origen)
	with zipfile.ZipFile(otra) as zf:
		assert "secretos.bin" not in zf.namelist()
		assert "conexiones" not in json.loads(zf.read("manifiesto.json"))["partes"]


def test_vista_previa_del_perfil_y_lo_ejecutable_aparte(origen, destino, tmp_path):
	ruta = perfil.exportar(tmp_path / "curso.zcperfil", ruta_datos=origen)
	config = Configuracion(destino / "config" / "settings.json")
	with CopiaAbierta(ruta) as copia:
		vista = perfil.vista_previa(copia, config, destino)
	filas = {f.id: f for f in vista.filas}
	assert filas["valor:vista.tamano_fuente"].actual == "10" and filas["valor:vista.tamano_fuente"].nuevo == "14"
	assert "valor:editor.externo" not in filas and "archivo:config/favoritos.json" in filas
	assert "grupo:plantillas" in filas
	ids = {e.id for e in vista.ejecutables}
	assert {"alias:ll", "macros:Limpiar", "menu_usuario:Compilar", "clave:editor.externo"} <= ids


def test_importar_perfil_aplica_solo_lo_marcado(origen, destino, tmp_path):
	ruta = perfil.exportar(tmp_path / "curso.zcperfil", ruta_datos=origen)
	config = Configuracion(destino / "config" / "settings.json")
	recibidos = []
	eventos.bus().suscribir(eventos.AL_RESTAURAR, lambda partes=(), **_d: recibidos.append(list(partes)))
	resultado = perfil.importar(ruta, config, ["valor:vista.tamano_fuente", "archivo:config/favoritos.json"],
		["macros:Limpiar"], destino)
	assert resultado.ok, resultado.mensaje
	assert "No se aplicaron" in resultado.mensaje
	assert config.obtener("vista.tamano_fuente") == 14
	assert config.obtener("teclado.personalizadas") == {}
	assert config.obtener("editor.externo") == "notepad.exe %P"
	assert [f["nombre"] for f in leer_json(destino, "config/favoritos.json")["favoritos"]] == ["Fotos"]
	assert [m["nombre"] for m in leer_json(destino, "config/macros.json")["macros"]] == ["Limpiar"]
	assert not (destino / "config" / "alias.json").exists() and not (destino / "plantillas").exists()
	assert recibidos and "personalizacion" in recibidos[0]
	assert list((destino / "backups" / "automaticas").glob("*.zcbackup"))


def test_perfil_no_cambia_el_origen_de_las_actualizaciones_sin_marcarlo(origen, destino, tmp_path):
	"""2.0.1: ``actualizaciones.fuente`` y ``url_personalizada`` se tratan como las claves que ejecutan algo."""
	ajustes = leer_json(origen, "config/settings.json")
	ajustes["actualizaciones"] = {"fuente": "personalizada", "url_personalizada": "https://malo.example/version.json"}
	escribir_json(origen, "config/settings.json", ajustes)
	ruta = perfil.exportar(tmp_path / "curso.zcperfil", ruta_datos=origen)
	config = Configuracion(destino / "config" / "settings.json")
	fuente_antes = config.obtener("actualizaciones.fuente")
	with CopiaAbierta(ruta) as copia:
		vista = perfil.vista_previa(copia, config, destino)
	filas = {f.id for f in vista.filas}
	assert "valor:actualizaciones.fuente" not in filas and "valor:actualizaciones.url_personalizada" not in filas
	ids = {e.id for e in vista.ejecutables}
	assert {"clave:actualizaciones.fuente", "clave:actualizaciones.url_personalizada"} <= ids
	# Sin marcarlas no se aplican, aunque se marquen todas las preferencias.
	resultado = perfil.importar(ruta, config, [f"valor:{c}" for c in ("vista.tamano_fuente",)], [], destino)
	assert resultado.ok, resultado.mensaje
	assert config.obtener("actualizaciones.fuente") == fuente_antes
	assert config.obtener("actualizaciones.url_personalizada") == ""
	# Marcadas una a una, sí.
	resultado = perfil.importar(ruta, config, [], ["clave:actualizaciones.fuente", "clave:actualizaciones.url_personalizada"], destino)
	assert resultado.ok, resultado.mensaje
	assert config.obtener("actualizaciones.fuente") == "personalizada"
	assert config.obtener("actualizaciones.url_personalizada") == "https://malo.example/version.json"


def test_tamanos_y_partes(origen):
	tamanos = crear.tamano_partes(origen)
	assert set(tamanos) == set(formato.PARTES)
	assert tamanos["sonidos"] == 2048 and tamanos["registros"] > 0
	assert paths.ruta_datos() != origen
