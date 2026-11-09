# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Paquetes de sonidos: herencia, asistente, .zcsonidos y migración de la 1.x (diseño 2.0, 4.5 a 4.7 y 18.2)."""

from __future__ import annotations

import json
import zipfile
from array import array
from pathlib import Path

import pytest

from app.services.sonidos import catalogo, paquetes, wav


def _wav(ruta: Path, n: int = 800) -> Path:
	wav.escribir(ruta, array("h", [1000] * n), 8000)
	return ruta


def ev(id_evento: str) -> catalogo.EventoSonido:
	evento = catalogo.evento(id_evento)
	assert evento is not None
	return evento


@pytest.fixture
def carpetas(tmp_path, monkeypatch):
	serie, propios = tmp_path / "sounds", tmp_path / "sounds_usuario"
	for id_paquete, archivos in (("clasico", ["op_fin.wav", "nav_entrar.wav", "op_progreso.wav"]), ("suave", ["op_fin.wav"])):
		carpeta = serie / id_paquete
		carpeta.mkdir(parents=True)
		for nombre in archivos:
			_wav(carpeta / nombre)
		paquetes.escribir_manifiesto(paquetes.Paquete(id=id_paquete, nombre=id_paquete.capitalize(), carpeta=carpeta, de_serie=True,
			hereda=None if id_paquete == "clasico" else "clasico"))
	propios.mkdir()
	monkeypatch.setattr(paquetes, "carpeta_serie", lambda: serie)
	monkeypatch.setattr(paquetes, "carpeta_propios", lambda: propios)
	return serie, propios


def _propio(propios: Path, id_paquete: str, wavs: list[str], hereda: str = "suave", **extra) -> paquetes.Paquete:
	carpeta = propios / id_paquete
	carpeta.mkdir(parents=True)
	for nombre in wavs:
		(carpeta / nombre).parent.mkdir(parents=True, exist_ok=True)
		_wav(carpeta / nombre)
	paquete = paquetes.Paquete(id=id_paquete, nombre="Mi paquete", carpeta=carpeta, de_serie=False, hereda=hereda, **extra)
	paquetes.escribir_manifiesto(paquete)
	return paquete


# ── Instalados y herencia ────────────────────────────────────────────────────

def test_listar_pone_primero_los_de_serie_y_da_su_etiqueta(carpetas):
	_serie, propios = carpetas
	_propio(propios, "mio", [])
	lista = paquetes.listar()
	assert [p.id for p in lista] == ["clasico", "suave", "mio"]
	assert lista[0].etiqueta == "Clasico, de serie"
	assert lista[2].etiqueta == "Mi paquete, propio"


def test_la_herencia_resuelve_lo_que_falta_en_un_propio_al_clasico(carpetas):
	_serie, propios = carpetas
	_propio(propios, "mio", ["op_fin.wav"])
	assert paquetes.resolver(ev("op.fin"), "", "mio") == propios / "mio" / "op_fin.wav"
	assert paquetes.resolver(ev("nav.entrar"), "", "mio") == paquetes.carpeta_serie() / "clasico" / "nav_entrar.wav"
	assert paquetes.resolver(ev("aviso.error"), "", "mio") is None
	assert [p.id for p in paquetes.cadena("mio")] == ["mio", "suave", "clasico"]
	assert paquetes.origen(ev("op.fin"), "mio") == "Propio"
	assert paquetes.origen(ev("nav.entrar"), "mio") == "Heredado de Clasico"
	assert paquetes.origen(ev("aviso.error"), "mio") == "Sin sonido"
	# Un paquete que no existe suena como el clásico.
	assert paquetes.resolver(ev("op.fin"), "", "no_existe") == paquetes.carpeta_serie() / "clasico" / "op_fin.wav"


def test_herencia_circular_no_se_cuelga(carpetas):
	_serie, propios = carpetas
	_propio(propios, "uno", [], hereda="dos")
	_propio(propios, "dos", [], hereda="uno")
	assert [p.id for p in paquetes.cadena("uno")] == ["uno", "dos", "clasico"]


def test_campo_archivos_da_otro_nombre_a_un_evento(carpetas):
	_serie, propios = carpetas
	_propio(propios, "mio", ["terminado.wav"], archivos={"op.fin": "terminado.wav"})
	assert paquetes.resolver(ev("op.fin"), "", "mio").name == "terminado.wav"


def test_sonido_de_complemento_sale_de_su_paquete_si_ningun_paquete_lo_tiene(carpetas):
	from app.plugins import registro

	evento = ev("zc.nubes:conectar")
	carpeta = Path(registro.complemento("zc.nubes").carpeta)
	assert paquetes.resolver(evento, "", "clasico") == carpeta / "sonidos" / "conectar.wav"
	assert paquetes.origen(evento, "clasico") == "Del complemento"


def test_manifiesto_malo_da_mensajes_en_espanol():
	problemas = paquetes.validar_manifiesto({"formato": 2, "id": "Mal Id", "nombre": "", "archivos": {"op.fin": "../x.wav"}})
	texto = " ".join(problemas)
	assert "Formato" in texto and "identificador" in texto and "nombre" in texto and "op.fin" in texto


# ── Asistente (borrador) ─────────────────────────────────────────────────────

def test_proponer_id_y_problemas_del_id(carpetas):
	assert paquetes.proponer_id("Mis Sonidos de Ñandú 2") == "mis_sonidos_de_nandu_2"
	assert paquetes.problema_id("clasico") is not None
	assert paquetes.problema_id("Con Espacios") is not None
	assert paquetes.problema_id("nuevo") is None


def test_nuevo_a_partir_de_uno_de_serie_hereda_de_el_y_guarda_lo_cambiado(carpetas, tmp_path):
	_serie, propios = carpetas
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("suave"))
	borrador.nombre, borrador.id, borrador.autor = "Mío", "mio", "Ana"
	assert borrador.hereda == "suave"
	assert borrador.origen(ev("op.fin")) == "Heredado de Suave"
	nuevo_wav = _wav(tmp_path / "otro.wav")
	borrador.sustituir(ev("nav.entrar"), "", nuevo_wav)
	assert borrador.origen(ev("nav.entrar")) == "Propio"
	assert borrador.ruta(ev("nav.entrar")) == nuevo_wav
	assert borrador.heredado(ev("nav.entrar")).parent.name == "clasico"
	with pytest.raises(wav.WavNoValido):
		borrador.sustituir(ev("op.fin"), "", tmp_path / "no_existe.wav")
	propios_, heredados = borrador.contar()
	assert propios_ == 1 and heredados == len(paquetes.eventos_con_variantes()) - 1
	paquete = paquetes.guardar(borrador)
	assert (propios / "mio" / "nav_entrar.wav").read_bytes() == nuevo_wav.read_bytes()
	datos = json.loads((propios / "mio" / "paquete.json").read_text(encoding="utf-8"))
	assert datos["hereda"] == "suave" and datos["autor"] == "Ana" and datos["formato"] == 1
	assert paquete.de_serie is False


def test_editar_y_volver_al_heredado_borra_el_propio(carpetas):
	_serie, propios = carpetas
	mio = _propio(propios, "mio", ["op_fin.wav", "nav_entrar.wav"])
	borrador = paquetes.Borrador.editar(paquetes.obtener("mio"))
	assert borrador.origen(ev("op.fin")) == "Propio"
	borrador.volver_al_heredado(ev("op.fin"))
	assert borrador.origen(ev("op.fin")) == "Heredado de Suave"
	paquetes.guardar(borrador)
	assert not (mio.carpeta / "op_fin.wav").exists()
	assert (mio.carpeta / "nav_entrar.wav").exists()


def test_nuevo_a_partir_de_un_propio_copia_sus_sonidos(carpetas):
	_serie, propios = carpetas
	_propio(propios, "mio", ["op_fin.wav", "plugins/zc.nubes/conectar.wav"])
	borrador = paquetes.Borrador.nuevo(paquetes.obtener("mio"))
	borrador.nombre, borrador.id = "Copia", "copia"
	assert borrador.hereda == "suave"
	paquetes.guardar(borrador)
	assert (propios / "copia" / "op_fin.wav").is_file()
	assert (propios / "copia" / "plugins" / "zc.nubes" / "conectar.wav").is_file()


def test_eliminar_solo_los_propios(carpetas):
	_serie, propios = carpetas
	_propio(propios, "mio", [])
	with pytest.raises(paquetes.ErrorPaquete):
		paquetes.eliminar("clasico")
	paquetes.eliminar("mio")
	assert not (propios / "mio").exists()


# ── .zcsonidos ───────────────────────────────────────────────────────────────

def _zcsonidos(ruta: Path, miembros: dict[str, bytes], manifiesto: dict | None = None) -> Path:
	datos = manifiesto or {"formato": 1, "id": "importado", "nombre": "Importado", "autor": "Ana", "hereda": "clasico"}
	with zipfile.ZipFile(ruta, "w") as zip_:
		zip_.writestr("paquete.json", json.dumps(datos))
		for nombre, contenido in miembros.items():
			zip_.writestr(nombre, contenido)
	return ruta


def test_importar_un_zcsonidos_con_un_exe_se_rechaza_sin_escribir_nada(carpetas, tmp_path):
	_serie, propios = carpetas
	ruta = _zcsonidos(tmp_path / "malo.zcsonidos", {"op_fin.wav": _wav(tmp_path / "a.wav").read_bytes(), "virus.exe": b"MZ"})
	with pytest.raises(paquetes.ErrorPaquete, match="virus.exe"):
		paquetes.importar(ruta)
	assert list(propios.iterdir()) == []


@pytest.mark.parametrize("nombre", ["../fuera.wav", "/absoluto.wav", "C:/x.wav", "carpeta/x.wav", "CON.wav", "op_fin.wav:flujo"])
def test_importar_rechaza_nombres_peligrosos(carpetas, tmp_path, nombre):
	ruta = _zcsonidos(tmp_path / "malo.zcsonidos", {nombre: _wav(tmp_path / "a.wav").read_bytes()})
	with pytest.raises(paquetes.ErrorPaquete):
		paquetes.importar(ruta)


def test_importar_rechaza_wav_no_validos_e_id_de_serie(carpetas, tmp_path):
	ruta = _zcsonidos(tmp_path / "malo.zcsonidos", {"op_fin.wav": b"RIFF....WAVEroto"})
	with pytest.raises(paquetes.ErrorPaquete, match="op_fin.wav"):
		paquetes.importar(ruta)
	ruta = _zcsonidos(tmp_path / "serie.zcsonidos", {}, {"formato": 1, "id": "clasico", "nombre": "Falso"})
	with pytest.raises(paquetes.ErrorPaquete, match="serie"):
		paquetes.importar(ruta)


def test_exportar_e_importar_ida_y_vuelta_y_pregunta_si_ya_existe(carpetas, tmp_path):
	_serie, propios = carpetas
	_propio(propios, "mio", ["op_fin.wav", "plugins/zc.nubes/conectar.wav"])
	(propios / "mio" / "LICENCIA.txt").write_text("CC0", encoding="utf-8")
	(propios / "mio" / "notas.txt").write_text("no viaja", encoding="utf-8")
	archivo = paquetes.exportar("mio", tmp_path / "copia")
	assert archivo.name == "copia.zcsonidos"
	with zipfile.ZipFile(archivo) as zip_:
		assert sorted(zip_.namelist()) == ["LICENCIA.txt", "op_fin.wav", "paquete.json", "plugins/zc.nubes/conectar.wav"]
	with pytest.raises(paquetes.PaqueteExiste) as existe:
		paquetes.importar(archivo)
	assert existe.value.id == "mio"
	paquete = paquetes.importar(archivo, sustituir=True)
	assert paquete.id == "mio" and not (propios / "mio" / "notas.txt").exists()
	assert (propios / "mio" / "plugins" / "zc.nubes" / "conectar.wav").is_file()


# ── Migración de la 1.x y soporte ────────────────────────────────────────────

class ConfigFalsa:
	def __init__(self) -> None:
		self.valores = {"sonidos.paquete": "clasico", "sonidos.activos": True, "sonidos.volumen": 70}

	def obtener(self, clave):
		return self.valores[clave]

	def establecer(self, clave, valor):
		self.valores[clave] = valor
		return True


def test_migrar_1x_crea_mis_sonidos_y_lo_elige_y_la_segunda_vez_no_hace_nada(tmp_path):
	datos = tmp_path / "data"
	(datos / "sounds").mkdir(parents=True)
	_wav(datos / "sounds" / "operacion_terminada.wav")
	config = ConfigFalsa()
	assert paquetes.migrar_1x(datos, config) is True
	carpeta = datos / "sounds_usuario" / "mis_sonidos_1x"
	paquete = paquetes.leer(carpeta, False)
	assert paquete.nombre == "Mis sonidos 1.x" and paquete.hereda == "clasico"
	assert paquete.archivos == {"op.fin": "operacion_terminada.wav"}
	assert paquete.archivo_propio(ev("op.fin")) == carpeta / "operacion_terminada.wav"
	assert not (datos / "sounds" / "operacion_terminada.wav").exists()
	assert config.valores["sonidos.paquete"] == "mis_sonidos_1x"
	config.valores["sonidos.paquete"] = "suave"
	assert paquetes.migrar_1x(datos, config) is False
	assert config.valores["sonidos.paquete"] == "suave"


def test_migrar_1x_sin_wav_sueltos_no_hace_nada(tmp_path):
	(tmp_path / "sounds" / "clasico").mkdir(parents=True)
	assert paquetes.migrar_1x(tmp_path, ConfigFalsa()) is False
	assert not (tmp_path / "sounds_usuario").exists()


def test_lineas_de_soporte(carpetas):
	from app.services.sonidos import servicio
	from app.services.sonidos.motor import Motor

	config = ConfigFalsa()
	motor = Motor(config, precargar=False)
	servicio.iniciar(config, motor)
	try:
		lineas = paquetes.lineas_soporte()
	finally:
		servicio.cerrar()
	assert lineas[0] == "Paquete elegido: Clasico, de serie (clasico)"
	assert lineas[1] == "Sonidos activos: sí; volumen: 70"
	assert lineas[2] == "Paquetes instalados: 2 de serie y 0 propios"
