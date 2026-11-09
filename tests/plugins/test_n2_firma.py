# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Firma y confianza de complementos (diseño 2.0, 3.2, 3.9 y 18.2). Las claves son de prueba."""

from __future__ import annotations

import os
import shutil

import pytest

from app.plugins import cargador, firma, manifiesto, registro, serie
from app.plugins.estado import EstadoComplemento

from ..conftest import RAIZ

EJEMPLO = RAIZ / "tests" / "datos" / "plugins" / "ejemplo"


@pytest.fixture
def clave():
	privada = os.urandom(32)
	return privada, firma.clave_publica(privada)


@pytest.fixture
def firmado(tmp_path, clave):
	carpeta = tmp_path / "ejemplo"
	shutil.copytree(EJEMPLO, carpeta, ignore=shutil.ignore_patterns("__pycache__"))
	firma.firmar_complemento(carpeta, "prueba.ejemplo", "1.0.0", clave[0])
	return carpeta


def test_acepta_lo_firmado(firmado, clave):
	resultado = firma.verificar_complemento(firmado, [clave[1]], comprobar_sumas=True)
	assert resultado.valida and resultado.clave == clave[1]
	assert "manifiesto.toml" in resultado.archivos


def test_rechaza_un_byte_cambiado_con_sumas(firmado, clave):
	ruta = firmado / "__init__.py"
	ruta.write_bytes(ruta.read_bytes() + b"#")
	assert firma.verificar_complemento(firmado, [clave[1]], comprobar_sumas=False).valida, "sin leer los archivos no se nota"
	resultado = firma.verificar_complemento(firmado, [clave[1]], comprobar_sumas=True)
	assert not resultado.valida and "cambiado" in resultado.motivo


def test_rechaza_un_archivo_de_mas(firmado, clave):
	(firmado / "extra.py").write_text("x = 1\n", encoding="utf-8")
	resultado = firma.verificar_complemento(firmado, [clave[1]], comprobar_sumas=False)
	assert not resultado.valida and "extra.py" in resultado.motivo


def test_otra_clave_no_vale(firmado):
	otra = firma.clave_publica(os.urandom(32))
	assert not firma.verificar_complemento(firmado, [otra], comprobar_sumas=False).valida


def test_dominio_separado(firmado, clave):
	contenido = firma.contenido_firmado(firmado, "prueba.ejemplo", "1.0.0")
	assert contenido.startswith(b"zcommander-complemento-v1\n")
	assert len(firma.suma_paquete(firmado, "prueba.ejemplo", "1.0.0")) == 64


def _cargador(tmp_path, serie_carpeta=None, usuario=None, config=None):
	return cargador.Cargador(config, carpeta_serie=serie_carpeta or (tmp_path / "serie_vacia"), carpeta_usuario=usuario or (tmp_path / "usuario"),
		carpeta_centinelas=tmp_path / "cargando")


class _Config:
	def __init__(self, **valores) -> None:
		self.valores = {"complementos.inhabilitados": [], "complementos.confiados": {}, "complementos.permitir_sin_firma": True,
			"complementos.fallos_maximos": 3, "complementos.modo_desarrollo": False}
		self.valores.update({k.replace("__", "."): v for k, v in valores.items()})

	def obtener(self, clave):
		return self.valores[clave]


def test_zc_de_serie_es_oficial_y_uno_fuera_de_la_lista_no(registro_vacio, tmp_path, monkeypatch):
	carpeta_serie = tmp_path / "plugins"
	shutil.copytree(RAIZ / "plugins" / "notas", carpeta_serie / "notas")
	monkeypatch.setattr(serie, "SERIE", {"zc.notas": "1.0.0"})
	_cargador(tmp_path, carpeta_serie, config=_Config()).descubrir()
	assert registro.complemento("zc.notas").confianza == "Oficial"
	assert registro.estado("zc.notas") == EstadoComplemento.REGISTRADO
	registro_vacio.vaciar()
	monkeypatch.setattr(serie, "SERIE", {"zc.notas": "9.9.9"})  # otra versión: no es la de serie
	_cargador(tmp_path, carpeta_serie, config=_Config()).descubrir()
	assert registro.estado("zc.notas") == EstadoComplemento.ERROR_MANIFIESTO, "un zc.* sin la firma del proyecto se rechaza"


def test_sin_firma_en_data_plugins_queda_sin_aceptar_y_con_su_suma_se_carga(registro_vacio, tmp_path):
	usuario = tmp_path / "usuario"
	shutil.copytree(EJEMPLO, usuario / "ejemplo", ignore=shutil.ignore_patterns("__pycache__"))
	cargador_a = _cargador(tmp_path, usuario=usuario, config=_Config())
	cargador_a.descubrir()
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.SIN_ACEPTAR
	assert cargador_a.sin_aceptar == ["prueba.ejemplo"]
	suma = firma.suma_paquete(usuario / "ejemplo", "prueba.ejemplo", manifiesto.leer(usuario / "ejemplo").version)
	registro_vacio.vaciar()
	_cargador(tmp_path, usuario=usuario, config=_Config(complementos__confiados={"prueba.ejemplo": suma})).descubrir()
	assert registro.estado("prueba.ejemplo") == EstadoComplemento.REGISTRADO
	assert registro.complemento("prueba.ejemplo").confianza == "Sin firma"
