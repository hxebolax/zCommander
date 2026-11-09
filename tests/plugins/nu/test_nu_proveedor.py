# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``ProveedorRclone`` con rclone real sobre remotos ``memory`` y ``local`` (diseño 2.0, 12.4 y 12.13)."""

from __future__ import annotations

import os
import threading

import pytest

from app.plugins import api
from app.plugins.api import pruebas
from app.services.operaciones.copiar import OpcionesCopia, OperacionCopiar
from app.services.operaciones.gestor import GestorOperaciones
from app.services.operaciones.modelo import AccionConflicto, Politica, RespuestaConflicto
from app.services.vfs import resolver
from tests.plugins.nu.comun import (
	crear_local,
	crear_memoria,
	modulo,
	requiere_rclone,
)

pytestmark = [pytest.mark.componentes, requiere_rclone]


@pytest.fixture
def memoria(nubes):
	nubes.cliente()
	return crear_memoria(nubes)


def test_operaciones_basicas_sobre_memory(nubes, memoria, tmp_path):
	proveedor, ruta = nubes.fabrica_nube("nube://mem/")
	assert ruta == "/" and proveedor.esquema == "nube" and proveedor.servidor == "nube:mem"
	assert proveedor.mostrar("/a/b.txt") == "Memoria:\\a\\b.txt"
	proveedor.crear_carpeta("/docs")
	with proveedor.abrir_escritura("/docs/hola.txt", 21) as flujo:
		flujo.write(b"hola mundo ")
		flujo.write(b"0123456789")
	nombres = {e.nombre: e for e in proveedor.listar("/docs")}
	assert nombres["hola.txt"].tamano == 21 and not nombres["hola.txt"].es_carpeta
	assert {e.nombre for e in proveedor.listar("/")} == {"docs"}
	with proveedor.abrir_lectura("/docs/hola.txt") as flujo:
		flujo.seek(5)
		assert flujo.read(5) == b"mundo"
		assert flujo.read() == b" 0123456789"
	proveedor.renombrar("/docs/hola.txt", "/docs/adios.txt")
	assert proveedor.info("/docs/adios.txt").tamano == 21
	with pytest.raises(api.NoEncontrado):
		proveedor.info("/docs/hola.txt")
	assert proveedor.suma("/docs/adios.txt", "md5")
	proveedor.eliminar("/docs/adios.txt")
	assert proveedor.listar("/docs") == []
	with pytest.raises(api.NoEncontrado):
		proveedor.listar("/no/existe")
	with pytest.raises(api.NoEncontrado):
		proveedor.eliminar("/nada.txt")


def test_abortar_una_subida_no_deja_un_objeto_a_medias(nubes, memoria):
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	with pytest.raises(RuntimeError), proveedor.abrir_escritura("/roto.bin", 1000) as flujo:
		flujo.write(b"x" * 100)
		raise RuntimeError("fallo a mitad")
	with pytest.raises(api.NoEncontrado):
		proveedor.info("/roto.bin")


def test_espacio_del_remoto_local(nubes, tmp_path):
	nubes.cliente()
	crear_local(nubes, tmp_path)
	proveedor, _ruta = nubes.fabrica_nube("nube://disco/")
	libre, total = proveedor.espacio_libre("/")
	assert 0 < libre <= total
	assert "libres" in nubes.espacio(nubes.cuenta("disco"))
	unidades = nubes.unidades()
	assert any(u.direccion == "nube://disco/" and "libres" in u.descripcion for u in unidades)


def test_copia_de_50_mb_con_progreso_y_cancelacion(nubes, memoria, tmp_path):
	grande = tmp_path / "grande.bin"
	with open(grande, "wb") as archivo:
		archivo.truncate(50 * 1024 * 1024)
	cuenta = nubes.cuenta("mem")
	cuenta.limite_subida_kib = cuenta.limite_bajada_kib = 4096   # 4 MiB/s por transferencia: da tiempo a ver el progreso
	nubes.cuentas.guardar(cuenta)
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	cancelacion = threading.Event()
	vistos: list[int] = []

	def progreso(hechos: int, total: int) -> None:
		vistos.append(hechos)
		if len([v for v in vistos if v > 0]) >= 3:
			cancelacion.set()

	local = resolver.proveedor_local()
	with pytest.raises(api.Cancelado):
		proveedor.transferir(local, str(grande), "/grande.bin", progreso, cancelacion)
	positivos = [v for v in vistos if v > 0]
	assert len(positivos) >= 3 and positivos[-1] > positivos[0], "el progreso debe avanzar"
	with pytest.raises(api.NoEncontrado):
		proveedor.info("/grande.bin")


def _ejecutar(operacion, decisor) -> None:
	from app.core.tareas import ejecutor_directo

	gestor = GestorOperaciones(decisor, max_paralelas=1, ejecutor_interfaz=ejecutor_directo)
	gestor.lanzar(operacion)
	assert gestor.esperar(120)
	gestor.apagar(1)


def test_transferir_lote_de_200_archivos_en_un_solo_trabajo_y_respeta_los_conflictos(nubes, memoria, tmp_path):
	origen = tmp_path / "origen"
	(origen / "sub").mkdir(parents=True)
	for indice in range(200):
		carpeta = origen / "sub" if indice % 2 else origen
		(carpeta / f"f{indice:03}.txt").write_text(f"contenido {indice}", encoding="utf-8")
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	proveedor.crear_carpeta("/destino")
	# Dos archivos ya existen en el destino: el análisis pregunta y se responde OMITIR para los dos.
	for nombre in ("f000.txt", "f002.txt"):
		with proveedor.abrir_escritura(f"/destino/{nombre}", 8) as flujo:
			flujo.write(b"original")
	local = resolver.proveedor_local()
	entradas = [local.info(str(p)) for p in sorted(origen.iterdir())]
	antes = nubes.cliente().trabajos_lanzados
	decisor = pruebas.DecisorFalso([[RespuestaConflicto(AccionConflicto.OMITIR) for _ in range(2)]])
	operacion = OperacionCopiar(local, entradas, proveedor, "/destino", OpcionesCopia(politica=Politica.PREGUNTAR))
	_ejecutar(operacion, decisor)
	assert nubes.cliente().trabajos_lanzados - antes == 1, "los 198 archivos deben ir en un solo trabajo"
	proveedor.invalidar()
	en_destino = {e.nombre for e in proveedor.listar("/destino")} | {e.nombre for e in proveedor.listar("/destino/sub")}
	assert len(en_destino - {"sub"}) == 200
	with proveedor.abrir_lectura("/destino/f000.txt") as flujo:
		assert flujo.read() == b"original"
	with proveedor.abrir_lectura("/destino/sub/f199.txt") as flujo:
		assert flujo.read() == b"contenido 199"
	assert len(operacion.pares_hechos()) == 198


def test_mover_dentro_de_la_misma_cuenta_es_en_el_servidor(nubes, memoria):
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	for carpeta in ("/a", "/b"):
		proveedor.crear_carpeta(carpeta)
	with proveedor.abrir_escritura("/a/uno.txt", 3) as flujo:
		flujo.write(b"uno")
	operacion = OperacionCopiar(proveedor, [proveedor.info("/a/uno.txt")], proveedor, "/b",
		OpcionesCopia(politica=Politica.SOBRESCRIBIR), mover=True)
	_ejecutar(operacion, pruebas.DecisorFalso())
	proveedor.invalidar()
	assert [e.nombre for e in proveedor.listar("/b")] == ["uno.txt"]
	assert proveedor.listar("/a") == []


def test_cifrada_sobre_memory_nombres_cifrados_abajo_y_en_claro_arriba(nubes, memoria):
	base = nubes.cuenta("mem")
	cifrada = nubes.crear_cifrada(base, "/secreto", "Cifrada", "contraseña larga", "sal distinta")
	proveedor, _ruta = nubes.fabrica_nube(f"nube://{cifrada.id}/")
	with proveedor.abrir_escritura("/informe confidencial.txt", 6) as flujo:
		flujo.write(b"oculto")
	assert [e.nombre for e in proveedor.listar("/")] == ["informe confidencial.txt"]
	debajo, _r = nubes.fabrica_nube("nube://mem/")
	nombres = [e.nombre for e in debajo.listar("/secreto")]
	assert len(nombres) == 1 and "informe" not in nombres[0]
	with proveedor.abrir_lectura("/informe confidencial.txt") as flujo:
		assert flujo.read() == b"oculto"


def test_union_de_dos_carpetas_locales(nubes, tmp_path):
	nubes.cliente()
	(tmp_path / "a").mkdir()
	(tmp_path / "b").mkdir()
	(tmp_path / "a" / "de_a.txt").write_text("a")
	(tmp_path / "b" / "de_b.txt").write_text("b")
	uno = crear_local(nubes, tmp_path / "a", "uno")
	dos = crear_local(nubes, tmp_path / "b", "dos")
	union = nubes.crear_union("Todo", [uno, dos])
	proveedor, _ruta = nubes.fabrica_nube(f"nube://{union.id}/")
	assert {e.nombre for e in proveedor.listar("/")} == {"de_a.txt", "de_b.txt"}
	combinada = nubes.crear_union("Combinada", [uno, dos], tipo="combine")
	proveedor, _ruta = nubes.fabrica_nube(f"nube://{combinada.id}/")
	assert {e.nombre for e in proveedor.listar("/")} == {"uno", "dos"}


def test_sincronizar_simula_y_despues_hace_igual_el_destino(nubes, memoria, tmp_path):
	origen = tmp_path / "origen"
	origen.mkdir()
	(origen / "nuevo.txt").write_text("nuevo")
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	proveedor.crear_carpeta("/copia")
	with proveedor.abrir_escritura("/copia/sobra.txt", 5) as flujo:
		flujo.write(b"sobra")
	operaciones = modulo("operaciones")
	parametros = {"srcFs": nubes.fs_de(str(origen)), "dstFs": nubes.fs_de("nube://mem/copia"), "combined": True}
	simulacion = nubes.ejecutar("sync/sync", _config={"DryRun": True}, **parametros)
	grupos = operaciones.resumen_informe(simulacion)
	assert grupos["+"] == ["nuevo.txt"] and grupos["-"] == ["sobra.txt"]
	proveedor.invalidar()
	assert {e.nombre for e in proveedor.listar("/copia")} == {"sobra.txt"}, "la simulación no cambia nada"
	operacion = operaciones.OperacionRclone(nubes, "Sincronizar", "sync/sync", parametros, sonido_fin="sincronizacion_fin")
	_ejecutar(operacion, pruebas.DecisorFalso())
	proveedor.invalidar()
	assert {e.nombre for e in proveedor.listar("/copia")} == {"nuevo.txt"}
	assert "zc.nubes:sincronizacion_fin" in nubes.zc.sonidos_pedidos


def test_comprobar_da_las_diferencias(nubes, memoria, tmp_path):
	origen = tmp_path / "o"
	origen.mkdir()
	(origen / "igual.txt").write_text("igual")
	(origen / "solo_aqui.txt").write_text("x")
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	proveedor.crear_carpeta("/c")
	with proveedor.abrir_escritura("/c/igual.txt", 5) as flujo:
		flujo.write(b"igual")
	operaciones = modulo("operaciones")
	operacion = operaciones.OperacionRclone(nubes, "Comprobar", "operations/check", {"srcFs": nubes.fs_de(str(origen)),
		"dstFs": nubes.fs_de("nube://mem/c"), "combined": True, "match": True})
	operacion.aceptar_diferencias = True
	_ejecutar(operacion, pruebas.DecisorFalso())
	grupos = operaciones.resumen_informe(operacion.salida)
	assert grupos["+"] == ["solo_aqui.txt"] and grupos["="] == ["igual.txt"]


def test_bisync_inicial_en_dos_sentidos(nubes, memoria, tmp_path):
	uno = tmp_path / "uno"
	uno.mkdir()
	(uno / "de_uno.txt").write_text("1")
	proveedor, _ruta = nubes.fabrica_nube("nube://mem/")
	proveedor.crear_carpeta("/dos")
	with proveedor.abrir_escritura("/dos/de_dos.txt", 1) as flujo:
		flujo.write(b"2")
	nubes.rutas.bisync.mkdir(parents=True, exist_ok=True)
	parametros = {"path1": nubes.fs_de(str(uno)), "path2": nubes.fs_de("nube://mem/dos"), "workdir": str(nubes.rutas.bisync),
		"resync": True, "maxDelete": 50}
	nubes.ejecutar("sync/bisync", dryRun=True, **parametros)
	assert not (uno / "de_dos.txt").exists()
	nubes.ejecutar("sync/bisync", **parametros)
	assert (uno / "de_dos.txt").read_text() == "2"
	proveedor.invalidar()
	assert {e.nombre for e in proveedor.listar("/dos")} == {"de_uno.txt", "de_dos.txt"}
	assert str(nubes.rutas.bisync).startswith(str(nubes.rutas.cache)), "bisync trabaja dentro de data"
	assert any(nubes.rutas.bisync.iterdir())


def test_duplicados_por_core_command_usa_la_configuracion_portable(nubes, memoria):
	salida = nubes.duplicados(nubes.cuenta("mem"), "/", "list")
	assert "rclone.conf\" not found" not in salida
	simulada = nubes.duplicados(nubes.cuenta("mem"), "/", "newest", simular=True, por_contenido=True)
	assert "CRITICAL" not in simulada


def test_enlace_y_papelera_no_admitidos_en_memory_dan_mensaje_claro(nubes, memoria):
	with pytest.raises(api.NoAdmitido):
		nubes.enlace(nubes.cuenta("mem"), "/x")


def test_direccion_de_cuenta_inexistente(nubes):
	with pytest.raises(api.NoEncontrado):
		nubes.fabrica_nube("nube://no_existe/")


def test_cuenta_por_volver_a_configurar(nubes):
	cuentas = modulo("cuentas")
	nubes.cuentas.guardar(cuentas.Cuenta(id="restaurada", nombre="Restaurada", servicio="drive", volver_a_configurar=True))
	assert nubes.estado(nubes.cuenta("restaurada")) == "Volver a configurar"
	with pytest.raises(api.ErrorAcceso):
		nubes.fabrica_nube("nube://restaurada/")


def test_montar_sin_winfsp_explica_que_falta(nubes, memoria):
	servicio = modulo("servicio")
	if servicio.winfsp_instalado():
		pytest.skip("WinFsp está instalado en este equipo")
	with pytest.raises(api.NoAdmitido) as error:
		nubes.montar(nubes.cuenta("mem"))
	assert "WinFsp" in error.value.mensaje


def test_primer_montaje_con_winfsp_activa_el_aviso_de_acerca_de(nubes, monkeypatch):
	"""LI (2.5): «Acerca de» muestra el aviso de WinFsp en cuanto Nubes monta una unidad con él."""
	from app.plugins import config_plugins
	from app.ui import acerca_de

	# La configuración abierta de zc.nubes puede venir de otra prueba (otra data temporal): se vuelve a abrir aquí.
	config_plugins.registro().declarar("zc.nubes", config_plugins.registro().declaraciones("zc.nubes"))
	servicio = modulo("servicio")
	monkeypatch.setattr(servicio, "winfsp_instalado", lambda: True)
	llamadas: list[str] = []
	monkeypatch.setattr(nubes, "llamar", lambda orden, **_p: llamadas.append(orden) or {"mountPoint": "X:"})
	assert not acerca_de.nubes_uso_winfsp()
	assert nubes.montar(modulo("cuentas").Cuenta(id="mem", nombre="Memoria", servicio="memory")) == "X:"
	assert llamadas == ["mount/mount"]
	assert nubes.opcion("aviso_winfsp_mostrado") is True
	assert acerca_de.nubes_uso_winfsp(), "«Acerca de» lee la clave de zc.nubes.json sin activar el complemento"
	assert "WinFsp - Windows File System Proxy" in acerca_de.texto_acerca_de()


@pytest.mark.skipif(not os.path.isfile(os.path.join(os.environ.get("ProgramFiles(x86)", ""), "WinFsp", "bin", "winfsp-x64.dll")),
	reason="WinFsp no está instalado")
def test_montar_con_winfsp(nubes, memoria):
	punto = nubes.montar(nubes.cuenta("mem"))
	try:
		with open(os.path.join(punto + "\\", "montado.txt"), "w", encoding="utf-8") as archivo:
			archivo.write("hola")
		assert any(m["punto"] == punto for m in nubes.montajes())
	finally:
		nubes.desmontar(punto)


def test_servir_por_webdav_solo_en_local_y_dejar_de_servir(nubes, memoria):
	resultado = nubes.servir("webdav", "mem:", usuario="zc", contrasena="clave")
	assert resultado["addr"].startswith("127.0.0.1:")
	activos = nubes.servicios_activos()
	assert any(s["id"] == resultado["id"] and s["tipo"] == "webdav" for s in activos)
	nubes.dejar_de_servir(resultado["id"])
	assert not any(s["id"] == resultado["id"] for s in nubes.servicios_activos())


def test_limites_se_pausan_y_reanudan(nubes):
	nubes.zc.config.establecer("limite_subida_kib", 512)
	nubes.cliente()
	assert nubes.alternar_limites() is True
	assert nubes.llamar("core/bwlimit").get("rate") == "off"
	assert nubes.alternar_limites() is False
	assert nubes.llamar("core/bwlimit").get("rate") != "off"
