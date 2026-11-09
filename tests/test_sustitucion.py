# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sustitución REAL con el ``.bat`` sobre una instalación falsa en una carpeta temporal (diseño 2.0, 5.2, 5.3 y 18.2).

De la plantilla del agente «actualizador», con la salud en dos fases de zCommander.
Solo en Windows y con la marca ``lento`` (esperas reales del script). Cada caso:

1. Crea una «instalación» 1.0.0 en una carpeta con espacios, tilde, eñe y apóstrofo:
   un ``ZCommander.exe`` falso, ``lib/`` (con una ``lib/paquete/data`` que NO es la
   data de la persona), ``app_falsa.py`` (el programa que se relanza, que usa el
   actualizador real), un componente activo en ``data/bin`` y datos de la persona.
2. Publica la 1.1.0 firmada en un servidor HTTP local. Su ZIP trae además un
   ``data/config/ajustes.json`` que NUNCA debe llegar y un ``data/bin`` que solo
   puede llegar a ``data/bin/.entrante``.
3. Recorre el flujo real: comprobar → descargar y preparar → lanzar el .bat.
   Un proceso aparte hace de «aplicación en ejecución» que el .bat espera.
4. La versión nueva arranca bien, tarda, se cuelga antes o después de «iniciado»,
   muere o falla; se comprueba la sustitución, la vuelta atrás o el «salud sin
   confirmar», y que los datos de la persona siguen intactos byte a byte.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.skipif(sys.platform != "win32", reason="El script de sustitución es un .bat de Windows"),
	pytest.mark.lento]
pytest.importorskip("cryptography")

from tests.apoyo_actualizador import RAIZ, Servidor, cargar_firmador, publicar  # noqa: E402

from app.services import actualizador  # noqa: E402

# pythonw evita que se abran ventanas de consola al relanzar el programa falso.
PYTHON_SIN_VENTANA = (
	str(Path(sys.executable).with_name("pythonw.exe")) if Path(sys.executable).with_name("pythonw.exe").is_file() else sys.executable
)

APP_FALSA = '''"""Programa falso que hace de zCommander instalado (versión {version})."""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
VERSION = "{version}"
COMPORTAMIENTO = "{comportamiento}"


def main():
	logs = RAIZ / "data" / "logs"
	logs.mkdir(parents=True, exist_ok=True)
	with open(logs / "arranques.txt", "a", encoding="utf-8") as registro:
		registro.write(VERSION + " " + " ".join(sys.argv[1:]) + "\\n")
	from app.services import actualizador
	config = actualizador.Configuracion(version_actual=VERSION, carpeta_app=RAIZ, comando=[])
	if "--segunda-copia" in sys.argv:
		# La copia que la persona abre a mano: sin --tras-actualizar.
		time.sleep(2)
		if COMPORTAMIENTO == "otra_copia":
			actualizador.escribir_inicio(config)
			time.sleep(1)
			actualizador.confirmar_arranque(config)
			time.sleep(3)
		else:
			time.sleep(600)
		return 0
	if "--tras-actualizar" not in sys.argv:
		return 0
	if COMPORTAMIENTO in ("otra_copia", "otra_copia_rota"):
		# Como al abrir la aplicación a mano a la vez: la copia lanzada ve «otra
		# instancia» y se cierra sin marcas; la otra sigue abierta.
		import subprocess
		subprocess.Popen([sys.executable, __file__, "--segunda-copia"], creationflags=0x00000008 | 0x00000200)
		return 0
	if COMPORTAMIENTO == "falla":
		return 3
	if COMPORTAMIENTO == "cuelga":
		time.sleep(600)
		return 0
	actualizador.escribir_inicio(config, True)
	if COMPORTAMIENTO == "sin_ok":
		time.sleep(600)
		return 0
	if COMPORTAMIENTO == "muere_tras_inicio":
		time.sleep(1)
		return 4
	time.sleep({espera_ok})
	actualizador.confirmar_arranque(config, tras_actualizar=True)
	time.sleep(2)
	return 0


sys.exit(main())
'''


def _codigo_app() -> dict[str, bytes]:
	"""El actualizador real va dentro de la instalación: lo usa la versión nueva (con red y descargas de N2)."""
	return {
		"app/__init__.py": b"",
		"app/core/__init__.py": b"",
		"app/core/red.py": (RAIZ / "app" / "core" / "red.py").read_bytes(),
		"app/core/descargas.py": (RAIZ / "app" / "core" / "descargas.py").read_bytes(),
		"app/services/__init__.py": b"",
		"app/services/actualizador.py": (RAIZ / "app" / "services" / "actualizador.py").read_bytes(),
	}


def _archivos_version(version: str, comportamiento: str, espera_ok: float = 1) -> dict[str, bytes]:
	archivos = {
		"ZCommander.exe": f"EXE {version}".encode(),
		"lib/modulo.txt": f"modulo {version}".encode(),
		f"lib/solo_{version}.txt": b"solo en esta version",
		"lib/paquete/data/interno.txt": f"interno {version}".encode(),
		"plugins/zc.ejemplo/manifiesto.toml": f"complemento de serie {version}".encode(),
		"app_falsa.py": APP_FALSA.format(version=version, comportamiento=comportamiento, espera_ok=espera_ok).encode("utf-8"),
		"data/sounds/aviso.wav": f"sonido {version}".encode(),
	}
	archivos.update(_codigo_app())
	return archivos


COMPONENTE_ACTIVO = b"rclone 1.80.0, actualizado por la persona"


def _crear_instalacion(carpeta: Path) -> None:
	for nombre, contenido in _archivos_version("1.0.0", "sana").items():
		ruta = carpeta / nombre
		ruta.parent.mkdir(parents=True, exist_ok=True)
		ruta.write_bytes(contenido)
	usuario = {
		"data/config/ajustes.json": '{"tema": "oscuro", "voz": true}'.encode(),
		"data/plugins/ana.util/manifiesto.toml": b"complemento de la persona",
		"data/notas/nota ñ.txt": "Mis notas personales".encode(),
		"data/backups/copia.zcbackup": os.urandom(4096),
		"data/bin/rclone/rclone.exe": COMPONENTE_ACTIVO,
	}
	for nombre, contenido in usuario.items():
		ruta = carpeta / nombre
		ruta.parent.mkdir(parents=True, exist_ok=True)
		ruta.write_bytes(contenido)


def _datos_usuario(datos: Path) -> dict[str, bytes]:
	"""Todo data/ salvo lo que el propio proceso escribe (registros, temporales, estado del
	actualizador), los recursos que una versión puede refrescar y la carpeta de entrada."""
	resultado = {}
	for ruta in datos.rglob("*"):
		relativa = ruta.relative_to(datos)
		if (
			ruta.is_file()
			and relativa.parts[0] not in ("logs", "temp", "sounds")
			and relativa.parts[:2] != ("bin", ".entrante")
			and ruta.name != "actualizaciones.json"
		):
			resultado[relativa.as_posix()] = ruta.read_bytes()
	return resultado


def _esperar(condicion, segundos: float) -> bool:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		if condicion():
			return True
		time.sleep(0.25)
	return condicion()


def _powershell(orden: str) -> subprocess.CompletedProcess:
	return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", orden], capture_output=True, text=True,
		timeout=60, check=False)


def _procesos_vivos(carpeta: Path) -> int:
	"""Cuántos procesos (salvo cmd y PowerShell) ejecutan algo de la instalación de prueba."""
	filtro = str(carpeta).replace("'", "''")
	salida = _powershell("@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('"
		+ filtro + "') -and $_.Name -notmatch '^(cmd|powershell)' }).Count")
	return int(salida.stdout.strip() or 0)


def _terminar_restos(carpeta: Path) -> None:
	"""Mata cualquier proceso que siga ejecutando algo de la instalación de prueba."""
	filtro = str(carpeta).replace("'", "''")
	_powershell("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('" + filtro
		+ "') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")


@pytest.fixture
def entorno(tmp_path, monkeypatch):
	firmador = cargar_firmador()
	monkeypatch.delenv(firmador.VARIABLE_CONTRASENA, raising=False)
	clave = tmp_path / "claves" / "firma.key"
	publica = firmador.generar(clave)
	servidor = Servidor(tmp_path / "servidor")
	instalacion = tmp_path / "Programas d'prueba ñ" / "Mi App"
	_crear_instalacion(instalacion)
	procesos: list[subprocess.Popen] = []
	yield {"clave": clave, "publica": publica, "servidor": servidor, "instalacion": instalacion, "procesos": procesos}
	servidor.cerrar()
	for proceso in procesos:
		if proceso.poll() is None:
			proceso.kill()
	_terminar_restos(instalacion)


def _reintentar(funcion, veces: int = 40):
	"""El bucle local de este equipo corta a veces las conexiones (ronda 2-4): la descarga se reanuda."""
	for _intento in range(veces - 1):
		try:
			return funcion()
		except actualizador.ErrorRed:
			time.sleep(0.2)
	return funcion()


def _resultado(config) -> dict[str, str]:
	resultado = {}
	if config.archivo_resultado.is_file():
		for linea in config.archivo_resultado.read_text(encoding="utf-8").splitlines():
			clave, _sep, valor = linea.partition("=")
			resultado[clave] = valor
	return resultado


def _ejecutar(entorno, comportamiento: str, *, espera_salud: int = 20, espera_salud_total: int = 60, espera_cierre: int = 30,
		vida_app: float = 3, espera_ok: float = 1, **opciones):
	"""Publica la 1.1.0, prepara el script, lo lanza y espera a que termine."""
	instalacion: Path = entorno["instalacion"]
	publicar(
		entorno["servidor"].carpeta,
		"1.1.0",
		{**_archivos_version("1.1.0", comportamiento, espera_ok), "data/config/ajustes.json": b'{"sobrescrito": 1}',
			"data/bin/rclone/rclone.exe": b"rclone 1.77.0 de la base nueva", "data/bin/linea_base.json": b'{"version": 2}'},
		entorno["clave"],
	)
	app_en_marcha = subprocess.Popen([PYTHON_SIN_VENTANA, "-c", f"import time; time.sleep({vida_app})"])
	entorno["procesos"].append(app_en_marcha)
	config = actualizador.Configuracion(
		version_actual="1.0.0",
		carpeta_app=instalacion,
		url_manifiesto=entorno["servidor"].url("version.json"),
		claves_publicas=(entorno["publica"],),
		comando=[PYTHON_SIN_VENTANA, str(instalacion / "app_falsa.py")],
		permitir_desde_codigo=True,
		espera_salud=espera_salud,
		espera_salud_total=espera_salud_total,
		espera_cierre=espera_cierre,
		pid_a_esperar=app_en_marcha.pid,
		**opciones,
	)
	info = _reintentar(lambda: actualizador.comprobar(config))
	assert info is not None and info.version == "1.1.0"
	ruta_bat = _reintentar(lambda: actualizador.descargar_y_preparar(config, info))
	script = actualizador.lanzar_sustitucion(ruta_bat)
	entorno["procesos"].append(script)
	script.wait(timeout=espera_cierre + espera_salud_total + 120)
	return config, ruta_bat, _resultado(config)


def _leer(ruta: Path) -> bytes:
	return ruta.read_bytes()


def _registro(config) -> str:
	return config.registro_script.read_text(encoding="utf-8", errors="replace")


def test_actualizacion_correcta(entorno):
	instalacion = entorno["instalacion"]
	antes = _datos_usuario(instalacion / "data")
	# «ok» unos segundos después de «iniciado»: así el script ve las dos fases aunque el equipo vaya cargado.
	config, ruta_bat, resultado = _ejecutar(entorno, "sana", espera_ok=5)
	assert resultado.get("estado") == "correcta", _registro(config)
	assert "iniciada con PID" in _registro(config)
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.1.0"
	assert _leer(instalacion / "lib" / "modulo.txt") == b"modulo 1.1.0"
	assert (instalacion / "lib" / "solo_1.1.0.txt").is_file()
	assert (instalacion / "lib" / "solo_1.0.0.txt").is_file()  # sin /MIR: los sobrantes quedan
	assert _leer(instalacion / "lib" / "paquete" / "data" / "interno.txt") == b"interno 1.1.0"
	assert _leer(instalacion / "plugins" / "zc.ejemplo" / "manifiesto.toml") == b"complemento de serie 1.1.0"
	assert _leer(instalacion / "data" / "sounds" / "aviso.wav") == b"sonido 1.1.0"  # recurso actualizable
	# 5.3: el componente activo no se toca; lo del paquete espera en data/bin/.entrante.
	assert _leer(instalacion / "data" / "bin" / "rclone" / "rclone.exe") == COMPONENTE_ACTIVO
	entrante = instalacion / "data" / "bin" / ".entrante"
	assert _leer(entrante / "rclone" / "rclone.exe") == b"rclone 1.77.0 de la base nueva"
	assert (entrante / "linea_base.json").is_file()
	assert _datos_usuario(instalacion / "data") == antes  # datos de la persona intactos
	assert actualizador.leer_estado(config)["version_confirmada"] == "1.1.0"  # anti-retroceso
	assert not config.carpeta_respaldo.exists()
	assert not (config.carpeta_trabajo / "nueva").exists()
	assert not config.marca_inicio.exists() and not config.marca_sin_confirmar.exists()
	assert _esperar(lambda: not ruta_bat.exists(), 5)  # el .bat se borra solo
	assert "1.1.0 --tras-actualizar" in (instalacion / "data" / "logs" / "arranques.txt").read_text(encoding="utf-8")


def test_con_iniciado_espera_mas_que_la_primera_fase(entorno):
	"""Con «iniciado», el script espera «ok» más allá de ESPERA_SALUD (integración lenta desde un pendrive)."""
	inicio = time.monotonic()
	config, _ruta, resultado = _ejecutar(entorno, "lenta", espera_salud=4, espera_salud_total=40, espera_ok=9)
	assert resultado.get("estado") == "correcta", _registro(config)
	assert time.monotonic() - inicio > 9
	assert _leer(entorno["instalacion"] / "ZCommander.exe") == b"EXE 1.1.0"


def test_sin_ok_con_el_proceso_vivo_no_vuelve_atras(entorno):
	"""Agotada la espera total con el proceso vivo: «salud sin confirmar», sin vuelta atrás y con el respaldo.

	Después, el arranque siguiente de la 1.1.0 (otro proceso) lo ve y la persona pide volver:
	el ``.bat`` en modo «volver» restaura la 1.0.0 y borra ``data/bin/.entrante``.
	"""
	instalacion = entorno["instalacion"]
	antes = _datos_usuario(instalacion / "data")
	config, _ruta, resultado = _ejecutar(entorno, "sin_ok", espera_salud=4, espera_salud_total=10)
	assert resultado.get("estado") == "sin_confirmar", _registro(config)
	assert resultado.get("motivo") == "salud_sin_confirmar"
	assert "no se vuelve atras" in _registro(config)
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.1.0"
	assert (config.carpeta_respaldo / "programa" / "ZCommander.exe").read_bytes() == b"EXE 1.0.0"
	marca = actualizador.leer_sin_confirmar(config)
	assert marca is not None and (marca.version, marca.anterior) == ("1.1.0", "1.0.0")
	assert _procesos_vivos(instalacion) >= 1, "el proceso nuevo sigue vivo: nunca se mata"

	# Arranque siguiente de la 1.1.0 en otro proceso: se pregunta en lugar de confirmar.
	nueva = actualizador.Configuracion(version_actual="1.1.0", carpeta_app=instalacion, comando=config.comando,
		permitir_desde_codigo=True, espera_cierre=30)
	pendiente = actualizador.procesar_arranque(nueva, False)
	assert pendiente.sin_confirmar == marca and pendiente.instalada is None
	assert actualizador.leer_estado(nueva).get("version_confirmada") != "1.1.0"

	# «Volver a la versión anterior».
	app_en_marcha = subprocess.Popen([PYTHON_SIN_VENTANA, "-c", "import time; time.sleep(2)"])
	entorno["procesos"].append(app_en_marcha)
	nueva.pid_a_esperar = app_en_marcha.pid
	script = actualizador.lanzar_sustitucion(actualizador.preparar_vuelta_atras(nueva))
	entorno["procesos"].append(script)
	script.wait(timeout=120)
	final = _resultado(nueva)
	assert final.get("estado") == "revertida", _registro(nueva)
	assert final.get("motivo") == "a_peticion"
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.0.0"
	assert not (instalacion / "lib" / "solo_1.1.0.txt").exists()
	assert not (instalacion / "data" / "bin" / ".entrante").exists()
	assert _leer(instalacion / "data" / "bin" / "rclone" / "rclone.exe") == COMPONENTE_ACTIVO
	assert _datos_usuario(instalacion / "data") == antes
	assert not nueva.marca_sin_confirmar.exists()
	anterior = actualizador.Configuracion(version_actual="1.0.0", carpeta_app=instalacion, comando=[])
	assert "como pidió" in actualizador.leer_resultado_anterior(anterior)


@pytest.mark.parametrize(
	("comportamiento", "motivo", "espera_salud"),
	[
		("cuelga", "sin_marcador_de_salud", 6),  # sin «iniciado»: vuelve atrás al agotar la primera fase
		("falla", "se_cerro_sin_confirmar", 30),  # se cierra sin marcas: se detecta sin agotar la espera
		("muere_tras_inicio", "se_cerro_sin_confirmar", 30),  # «iniciado» y muere sin «ok»
	],
)
def test_vuelta_atras(entorno, comportamiento, motivo, espera_salud):
	instalacion = entorno["instalacion"]
	antes = _datos_usuario(instalacion / "data")
	inicio = time.monotonic()
	config, _ruta, resultado = _ejecutar(entorno, comportamiento, espera_salud=espera_salud, espera_salud_total=60)
	duracion = time.monotonic() - inicio
	assert resultado.get("estado") == "revertida", _registro(config)
	assert resultado.get("motivo") == motivo
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.0.0"
	assert _leer(instalacion / "lib" / "modulo.txt") == b"modulo 1.0.0"
	assert not (instalacion / "lib" / "solo_1.1.0.txt").exists()  # la restauración quita lo nuevo
	assert (instalacion / "lib" / "solo_1.0.0.txt").is_file()
	assert _leer(instalacion / "lib" / "paquete" / "data" / "interno.txt") == b"interno 1.0.0"
	assert _leer(instalacion / "data" / "sounds" / "aviso.wav") == b"sonido 1.0.0"
	assert not (instalacion / "data" / "bin" / ".entrante").exists()  # lo de la nueva no se queda
	assert _leer(instalacion / "data" / "bin" / "rclone" / "rclone.exe") == COMPONENTE_ACTIVO
	assert _datos_usuario(instalacion / "data") == antes
	assert (config.carpeta_respaldo / "programa" / "ZCommander.exe").is_file()  # se conserva para diagnosticar
	if comportamiento != "cuelga":
		assert duracion < 28, "un cierre sin confirmar se detecta sin agotar la espera"
	# La versión anterior se relanza (sin --tras-actualizar) y la persona recibe el aviso.
	arranques = instalacion / "data" / "logs" / "arranques.txt"
	assert _esperar(lambda: "1.0.0 \n" in arranques.read_text(encoding="utf-8"), 20)
	assert _esperar(lambda: _procesos_vivos(instalacion) == 0, 20)
	mensaje = actualizador.leer_resultado_anterior(config)
	assert mensaje and "1.1.0" in mensaje
	assert actualizador.leer_estado(config)["version_omitida"] == "1.1.0"


def test_si_la_aplicacion_no_se_cierra_no_se_toca_nada(entorno):
	instalacion = entorno["instalacion"]
	config, _ruta, resultado = _ejecutar(entorno, "sana", espera_cierre=3, vida_app=120)
	assert resultado.get("estado") == "no_aplicada"
	assert resultado.get("motivo") == "la_aplicacion_no_se_cerro"
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.0.0"
	assert not config.carpeta_respaldo.exists()
	assert not (config.carpeta_trabajo / "nueva").exists()
	assert not (instalacion / "data" / "bin" / ".entrante").exists()


def test_otra_copia_abierta_a_mano_confirma_la_version(entorno):
	"""La persona abre la aplicación a la vez que el script la lanza: la copia lanzada se cierra
	sin marcas y la otra, sin --tras-actualizar, escribe «iniciado» y «ok»; no se vuelve atrás."""
	instalacion = entorno["instalacion"]
	antes = _datos_usuario(instalacion / "data")
	config, _ruta, resultado = _ejecutar(entorno, "otra_copia", espera_salud=30)
	registro = _registro(config)
	assert resultado.get("estado") == "correcta", registro
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.1.0"
	assert _datos_usuario(instalacion / "data") == antes
	assert not config.aviso_espera_salud.exists()


def test_vuelta_atras_cierra_antes_las_copias_abiertas(entorno):
	"""Si hay que volver atrás con otra copia abierta, se cierra antes de restaurar."""
	instalacion = entorno["instalacion"]
	antes = _datos_usuario(instalacion / "data")
	config, _ruta, resultado = _ejecutar(entorno, "otra_copia_rota", espera_salud=8)
	registro = _registro(config)
	assert resultado.get("estado") == "revertida", registro
	assert "se cierran antes de restaurar" in registro
	assert _leer(instalacion / "ZCommander.exe") == b"EXE 1.0.0"
	assert not (instalacion / "lib" / "solo_1.1.0.txt").exists()
	assert _datos_usuario(instalacion / "data") == antes
	assert _esperar(lambda: _procesos_vivos(instalacion) == 0, 20)


def test_confirma_sin_argumento_si_el_script_espera_esta_version(tmp_path):
	config = actualizador.Configuracion(version_actual="1.1.0", carpeta_app=tmp_path, comando=[])
	actualizador.confirmar_arranque(config, tras_actualizar=False)
	assert not config.marcador_salud.exists(), "sin aviso del script no se escribe nada"
	config.carpeta_trabajo.mkdir(parents=True, exist_ok=True)
	config.aviso_espera_salud.write_text("1.0.9\n", encoding="utf-8")
	actualizador.confirmar_arranque(config, tras_actualizar=False)
	assert not config.marcador_salud.exists(), "solo confirma la versión que se espera"
	config.aviso_espera_salud.write_text("1.1.0\n", encoding="utf-8")
	actualizador.confirmar_arranque(config, tras_actualizar=False)
	assert config.marcador_salud.read_text(encoding="utf-8").strip() == "ok 1.1.0"
