# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Conectar nubes sin claves de API (zCommander 2.0.1, complemento Nubes 1.1.0).

- Carpetas de los programas oficiales (``locales.py``) con un registro, un
  ``info.json`` y unas variables de entorno FALSOS: nada depende de este equipo.
- Catálogo: método de cada ficha, identificadores propios en «avanzadas»,
  Jottacloud tradicional y el número de unidad de kDrive.
- Traducción de las preguntas habituales de rclone.
- ``Alta.responder`` reenvía los parámetros efímeros (``config_*``) en cada paso.
- Las carpetas salen en el selector de unidades como rutas locales.
- Las ventanas nuevas del asistente.
"""

from __future__ import annotations

import json
import os
import socket
import time

import pytest

from tests.plugins.nu.comun import modulo, requiere_rclone

SID = "S-1-5-21-1-2-3-1001"
OTRO_SID = "S-1-5-21-9-9-9-1002"
RAICES = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\SyncRootManager"


class RegistroFalso:
	"""{(raíz, ruta): {"valores": {...}, "subclaves": [...]}} con las funciones que espera ``locales.Fuentes``."""

	def __init__(self) -> None:
		self.claves: dict[tuple[str, str], dict] = {}

	def poner(self, raiz: str, ruta: str, **valores) -> None:
		clave = self.claves.setdefault((raiz, ruta), {"valores": {}, "subclaves": []})
		clave["valores"].update(valores)
		padre, _sep, nombre = ruta.rpartition("\\")
		if padre:
			hermano = self.claves.setdefault((raiz, padre), {"valores": {}, "subclaves": []})
			if nombre not in hermano["subclaves"]:
				hermano["subclaves"].append(nombre)
			if "\\" in padre:
				self.poner(raiz, padre)

	def subclaves(self, raiz: str, ruta: str) -> list[str]:
		return list(self.claves.get((raiz, ruta), {}).get("subclaves", []))

	def valores(self, raiz: str, ruta: str) -> dict:
		return dict(self.claves.get((raiz, ruta), {}).get("valores", {}))


def _fuentes(locales, registro: RegistroFalso, existentes: set[str], *, entorno=None, archivos=None, etiquetas=(), sid=SID,
		indirectas=None):
	existentes_normales = {locales.clave_ruta(r) for r in existentes}
	archivos = archivos or {}

	def leer(ruta: str) -> str:
		if ruta not in archivos:
			raise FileNotFoundError(ruta)
		return archivos[ruta]

	return locales.Fuentes(subclaves=registro.subclaves, valores=registro.valores, entorno=dict(entorno or {}),
		existe=lambda ruta: locales.clave_ruta(ruta) in existentes_normales, leer_texto=leer, etiquetas=lambda: list(etiquetas),
		sid=sid, indirecta=lambda texto: (indirectas or {}).get(texto, ""))


# ── Carpetas de los programas oficiales ─────────────────────────────────────


def test_raices_de_sincronizacion_solo_de_la_persona_actual_y_con_cadena_indirecta(zc):
	locales = modulo("locales")
	registro = RegistroFalso()
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{SID}!Personal|abc", DisplayNameResource="OneDrive - Personal")
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{SID}!Personal|abc\UserSyncRoots", **{SID: r"C:\Users\ana\OneDrive"})
	registro.poner("HKLM", rf"{RAICES}\ProtonDrive!{SID}!cuenta", DisplayNameResource="@C:\\Proton\\recursos.dll,-7")
	registro.poner("HKLM", rf"{RAICES}\ProtonDrive!{SID}!cuenta\UserSyncRoots", **{SID: r"C:\Users\ana\Proton Drive"})
	registro.poner("HKLM", rf"{RAICES}\SynologyDrive!{SID}!sesion", DisplayNameResource="@no.se.resuelve,-1")
	registro.poner("HKLM", rf"{RAICES}\SynologyDrive!{SID}!sesion\UserSyncRoots", **{SID: r"C:\Users\ana\SynologyDrive"})
	# De otra persona del equipo: no sale.
	registro.poner("HKLM", rf"{RAICES}\iCloudDrive!{OTRO_SID}!Personal", DisplayNameResource="iCloud Drive")
	registro.poner("HKLM", rf"{RAICES}\iCloudDrive!{OTRO_SID}!Personal\UserSyncRoots", **{OTRO_SID: r"C:\Users\pepe\iCloudDrive"})
	# Una raíz cuya carpeta ya no existe: no sale.
	registro.poner("HKLM", rf"{RAICES}\Dropbox!{SID}!viejo", DisplayNameResource="Dropbox")
	registro.poner("HKLM", rf"{RAICES}\Dropbox!{SID}!viejo\UserSyncRoots", **{SID: r"C:\Users\ana\Dropbox antiguo"})
	fuentes = _fuentes(locales, registro, {r"C:\Users\ana\OneDrive", r"C:\Users\ana\Proton Drive", r"C:\Users\ana\SynologyDrive",
		r"C:\Users\pepe\iCloudDrive"}, indirectas={"@C:\\Proton\\recursos.dll,-7": "Proton Drive - ana@proton.me"})
	carpetas = locales.carpetas_de_nube(fuentes)
	assert [(c.nombre, c.proveedor) for c in carpetas] == [("OneDrive - Personal", "OneDrive"),
		("Proton Drive - ana@proton.me", "Proton Drive"), ("Synology Drive", "Synology Drive")]
	assert all(c.origen == locales.ORIGEN_RAICES for c in carpetas)


def test_sin_sid_solo_las_rutas_del_perfil(zc):
	locales = modulo("locales")
	registro = RegistroFalso()
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{SID}!Personal", DisplayNameResource="OneDrive - Personal")
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{SID}!Personal\UserSyncRoots", **{SID: r"C:\Users\ana\OneDrive"})
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{OTRO_SID}!Personal", DisplayNameResource="OneDrive - Personal")
	registro.poner("HKLM", rf"{RAICES}\OneDrive!{OTRO_SID}!Personal\UserSyncRoots", **{OTRO_SID: r"C:\Users\pepe\OneDrive"})
	fuentes = _fuentes(locales, registro, {r"C:\Users\ana\OneDrive", r"C:\Users\pepe\OneDrive"}, sid="",
		entorno={"USERPROFILE": r"C:\Users\ana"})
	assert [c.ruta for c in locales.carpetas_de_nube(fuentes)] == [r"C:\Users\ana\OneDrive"]


def test_onedrive_por_registro_y_variables_sin_repetir(zc):
	locales = modulo("locales")
	registro = RegistroFalso()
	cuentas = r"Software\Microsoft\OneDrive\Accounts"
	registro.poner("HKCU", rf"{cuentas}\Personal", UserFolder=r"C:\Users\ana\OneDrive")
	registro.poner("HKCU", rf"{cuentas}\Business1", UserFolder=r"C:\Users\ana\OneDrive - Contoso", DisplayName="Contoso")
	registro.poner("HKCU", rf"{cuentas}\Business2")   # sin sesión: sin UserFolder
	registro.poner("HKCU", rf"{cuentas}\FileCoAuth", UserFolder=r"C:\no\es\una\cuenta")
	entorno = {"OneDrive": r"C:\Users\ana\OneDrive", "OneDriveConsumer": r"c:\users\ana\onedrive\\",
		"OneDriveCommercial": r"C:\Users\ana\OneDrive - Contoso"}
	fuentes = _fuentes(locales, registro, {r"C:\Users\ana\OneDrive", r"C:\Users\ana\OneDrive - Contoso", r"C:\no\es\una\cuenta"},
		entorno=entorno)
	carpetas = locales.carpetas_de_nube(fuentes)
	assert [(c.nombre, c.ruta) for c in carpetas] == [("OneDrive - Personal", r"C:\Users\ana\OneDrive"),
		("OneDrive - Contoso", r"C:\Users\ana\OneDrive - Contoso")]
	# Solo con la variable (sin registro de OneDrive).
	solo_variable = _fuentes(locales, RegistroFalso(), {r"D:\Nube"}, entorno={"OneDrive": r"D:\Nube"})
	assert [(c.nombre, c.origen) for c in locales.carpetas_de_nube(solo_variable)] == [("OneDrive", locales.ORIGEN_VARIABLE)]


def test_dropbox_por_info_json_personal_y_empresa_y_json_danado(zc):
	locales = modulo("locales")
	appdata, local = r"C:\Users\ana\AppData\Roaming", r"C:\Users\ana\AppData\Local"
	archivos = {os.path.join(local, "Dropbox", "info.json"): json.dumps({
		"personal": {"path": r"C:\Users\ana\Dropbox", "host": 1},
		"business": {"path": r"C:\Users\ana\Dropbox (Contoso)"}}),
		os.path.join(appdata, "Dropbox", "info.json"): "{esto no es json"}
	fuentes = _fuentes(locales, RegistroFalso(), {r"C:\Users\ana\Dropbox", r"C:\Users\ana\Dropbox (Contoso)"},
		entorno={"APPDATA": appdata, "LOCALAPPDATA": local}, archivos=archivos)
	assert [(c.nombre, c.proveedor, c.origen) for c in locales.carpetas_de_nube(fuentes)] == [
		("Dropbox", "Dropbox", locales.ORIGEN_DROPBOX), ("Dropbox (empresa)", "Dropbox", locales.ORIGEN_DROPBOX)]


def test_google_drive_por_drivefs_o_por_la_etiqueta_de_la_unidad(zc):
	locales = modulo("locales")
	registro = RegistroFalso()
	registro.poner("HKCU", r"Software\Google\DriveFS", DefaultMountPoint="G")
	fuentes = _fuentes(locales, registro, {"G:\\", r"G:\Mi unidad"})
	carpeta = locales.carpeta_google_drive(fuentes)
	assert carpeta is not None and carpeta.ruta == r"G:\Mi unidad" and carpeta.origen == locales.ORIGEN_DRIVEFS
	# Con directiva de la organización en HKLM y sin «Mi unidad»: la raíz.
	registro = RegistroFalso()
	registro.poner("HKLM", r"Software\Policies\Google\DriveFS", DefaultMountPoint="H:")
	assert locales.carpeta_google_drive(_fuentes(locales, registro, {"H:\\"})).ruta == "H:\\"
	# Sin registro: la unidad con la etiqueta «Google Drive».
	fuentes = _fuentes(locales, RegistroFalso(), {"K:\\", r"K:\My Drive"}, etiquetas=[("C:\\", "Sistema"), ("K:\\", "Google Drive")])
	carpeta = locales.carpeta_google_drive(fuentes)
	assert carpeta.ruta == r"K:\My Drive" and carpeta.origen == locales.ORIGEN_ETIQUETA
	assert locales.carpeta_google_drive(_fuentes(locales, RegistroFalso(), set())) is None


def test_icloud_box_y_pcloud_por_carpeta_conocida_y_etiqueta(zc):
	locales = modulo("locales")
	perfil, programas = r"C:\Users\ana", r"C:\Program Files"
	entorno = {"USERPROFILE": perfil, "ProgramFiles": programas}
	existentes = {rf"{perfil}\iCloudDrive", rf"{perfil}\Box", rf"{programas}\Box\Box", "P:\\"}
	fuentes = _fuentes(locales, RegistroFalso(), existentes, entorno=entorno, etiquetas=[("P:\\", "pCloud Drive")])
	assert [(c.nombre, c.proveedor) for c in locales.carpetas_de_nube(fuentes)] == [("iCloud Drive", "iCloud Drive"), ("Box", "Box"),
		("pCloud Drive", "pCloud")]
	# Una carpeta «Box» en el perfil sin Box Drive instalado no es Box Drive.
	sin_box_drive = _fuentes(locales, RegistroFalso(), existentes - {rf"{programas}\Box\Box"}, entorno=entorno)
	assert [c.nombre for c in locales.carpetas_de_nube(sin_box_drive)] == ["iCloud Drive"]
	# Nada instalado: lista vacía.
	assert locales.carpetas_de_nube(_fuentes(locales, RegistroFalso(), set(), entorno={"USERPROFILE": perfil})) == []


def test_la_raiz_de_sincronizacion_gana_y_no_se_repiten_rutas(zc):
	locales = modulo("locales")
	registro = RegistroFalso()
	registro.poner("HKLM", rf"{RAICES}\iCloudDrive!{SID}!Personal", DisplayNameResource="iCloud Drive")
	registro.poner("HKLM", rf"{RAICES}\iCloudDrive!{SID}!Personal\UserSyncRoots", **{SID: r"C:\Users\ana\iCloudDrive"})
	fuentes = _fuentes(locales, registro, {r"C:\Users\ana\iCloudDrive"}, entorno={"USERPROFILE": r"C:\Users\ana"})
	carpetas = locales.carpetas_de_nube(fuentes)
	assert len(carpetas) == 1 and carpetas[0].origen == locales.ORIGEN_RAICES


def test_una_fuente_rota_no_deja_sin_las_demas_y_nunca_lanza(zc):
	locales = modulo("locales")

	def rota(*_args):
		raise RuntimeError("registro roto")

	fuentes = _fuentes(locales, RegistroFalso(), {r"C:\Users\ana\Box", r"C:\Programas\Box\Box"},
		entorno={"USERPROFILE": r"C:\Users\ana", "ProgramFiles": r"C:\Programas"})
	fuentes.subclaves = rota
	fuentes.valores = rota
	fuentes.leer_texto = rota
	assert [c.nombre for c in locales.carpetas_de_nube(fuentes)] == ["Box"]

	def existe_roto(_ruta):
		raise OSError("unidad que no responde")

	fuentes.existe = existe_roto
	assert locales.carpetas_de_nube(fuentes) == []


def test_frase_con_y_o_e(zc):
	locales = modulo("locales")
	c = lambda n: locales.CarpetaNube(n, n, "C:\\" + n, "prueba")  # noqa: E731
	assert locales.nombres_para_frase([c("OneDrive")]) == "OneDrive"
	assert locales.nombres_para_frase([c("OneDrive"), c("iCloud Drive")]) == "OneDrive e iCloud Drive"
	assert locales.nombres_para_frase([c("OneDrive"), c("Box"), c("Dropbox")]) == "OneDrive, Box y Dropbox"


# ── Catálogo ─────────────────────────────────────────────────────────────────


def test_cada_ficha_dice_como_se_conecta_y_los_de_navegador_no_piden_claves(zc):
	cuentas = modulo("cuentas")
	catalogo = zc.instancia.nubes.catalogo
	for servicio in catalogo.lista(True):
		assert servicio.metodo in cuentas.METODOS, servicio.id
	por_metodo = {s.id: s.como_se_conecta for s in catalogo.lista(True)}
	for id_ in ("drive", "onedrive", "dropbox", "box", "pcloud", "yandex", "kdrive", "jottacloud", "hidrive"):
		assert por_metodo[id_] == "navegador", id_
		servicio = catalogo.servicio(id_)
		assert not any(c["clave"] in ("client_id", "client_secret") for c in servicio.campos), id_
	for id_ in ("drive", "onedrive", "dropbox", "box"):
		assert {c["clave"] for c in catalogo.servicio(id_).avanzadas_alta} == {"client_id", "client_secret"}
	for id_ in ("mega", "koofr", "mailru", "internxt", "webdav_nativo", "sftp"):
		assert por_metodo[id_] == "contrasena", id_
	for id_ in ("s3", "b2", "filen", "otro"):
		assert por_metodo[id_] == "avanzado", id_
	assert por_metodo["carpeta_local"] == "carpeta_local"
	assert catalogo.servicio("carpeta_local").es_carpeta_local and catalogo.servicio("carpeta_local").motor == "local"
	# La lista va agrupada: navegador, contraseña, carpeta, avanzado; «Otro servicio» al final.
	orden = [cuentas.METODOS.index(s.como_se_conecta) for s in catalogo.lista(False)]
	assert orden == sorted(orden) and catalogo.lista(False)[-1].id == "otro"
	assert cuentas.texto_metodo("navegador") == "Iniciar sesión en el navegador"
	assert cuentas.texto_metodo("avanzado") == "Avanzado (claves propias)"
	# Una ficha aportada sin «metodo» lo deduce de su autenticación.
	assert cuentas.Servicio(id="x", nombre="X", tipo="x", autenticacion="contrasena_2fa").como_se_conecta == "contrasena"


def test_jottacloud_tradicional_y_kdrive_con_numero_de_unidad(zc):
	catalogo = zc.instancia.nubes.catalogo
	jotta = catalogo.servicio("jottacloud")
	assert jotta.es_oauth and jotta.opciones["config_type"] == "traditional"
	kdrive = catalogo.servicio("kdrive")
	campo = kdrive.campo("drive_id")
	assert campo is not None and campo.get("obligatorio") and "drive/" in campo["ayuda"]
	servicio = modulo("servicio")
	assert servicio.numero_unidad_kdrive("https://ksuite.infomaniak.com/123/kdrive/app/drive/456789/files/7") == "456789"
	assert servicio.numero_unidad_kdrive(" 456789 ") == "456789"
	cuenta, parametros = zc.instancia.nubes.nueva_cuenta(kdrive, "Mi kDrive",
		{"drive_id": "https://ksuite.infomaniak.com/1/kdrive/app/drive/42/files"})
	assert parametros["drive_id"] == "42" and cuenta.opciones["drive_id"] == "42"


def test_mega_koofr_y_mailru_avisan_y_enlazan(zc):
	catalogo = zc.instancia.nubes.catalogo
	assert any("mega.nz" in a for a in catalogo.servicio("mega").avisos)
	for id_ in ("koofr", "mailru"):
		servicio = catalogo.servicio(id_)
		assert servicio.enlace["url"].startswith("https://") and any("contraseña de aplicación" in a for a in servicio.avisos)


def test_nueva_cuenta_drive_con_el_identificador_de_rclone_y_otro_equipo(zc):
	nubes = zc.instancia.nubes
	servicio = modulo("servicio")
	drive = nubes.catalogo.servicio("drive")
	cuenta, parametros = nubes.nueva_cuenta(drive, "Drive", {"config_shared_client_id": "true", "config_change_team_drive": "false"})
	assert parametros["config_shared_client_id"] == "true" and parametros["config_auth_no_browser"] == "true"
	assert not cuenta.client_id_propio and not any(k.startswith("config_") for k in cuenta.opciones)
	_cuenta, parametros = nubes.nueva_cuenta(nubes.catalogo.servicio("onedrive"), "OD", {servicio.OTRO_EQUIPO: "true"})
	assert parametros["config_is_local"] == "false" and "config_auth_no_browser" not in parametros
	assert servicio.OTRO_EQUIPO not in parametros


def test_reconectar_lleva_las_respuestas_fijas(zc):
	nubes = zc.instancia.nubes
	cuentas = modulo("cuentas")
	drive = nubes.reconectar(cuentas.Cuenta(id="d", nombre="D", servicio="drive"))
	assert drive.parametros["config_shared_client_id"] == "true" and drive.parametros["config_change_team_drive"] == "false"
	propia = nubes.reconectar(cuentas.Cuenta(id="d", nombre="D", servicio="drive", client_id_propio=True))
	assert "config_shared_client_id" not in propia.parametros
	jotta = nubes.reconectar(cuentas.Cuenta(id="j", nombre="J", servicio="jottacloud"))
	assert jotta.parametros["config_type"] == "traditional" and jotta.parametros["config_refresh_token"] == "true"


# ── Respuestas de rclone ──────────────────────────────────────────────────────


class _ClienteFalso:
	def __init__(self) -> None:
		self.llamadas: list[tuple[str, dict]] = []

	def llamar_asincrono(self, ruta, **parametros):
		self.llamadas.append((ruta, parametros))
		return 7

	def llamar(self, ruta, **_parametros):
		if ruta == "job/status":
			return {"finished": True, "success": True, "output": {}}
		return {}


def test_responder_reenvia_los_parametros_del_alta(zc, monkeypatch):
	servicio = modulo("servicio")
	nubes = zc.instancia.nubes
	cliente = _ClienteFalso()
	monkeypatch.setattr(nubes, "cliente", lambda: cliente)
	alta = servicio.Alta(nubes, "od", "onedrive", {"config_is_local": "true", "config_auth_no_browser": "true", "region": "global"})
	paso = alta.responder("onedrive", servicio.Paso("pregunta", opcion={"Name": "config_type"}, estado="choose_type_done"))
	assert paso.tipo == "fin"
	ruta, parametros = cliente.llamadas[-1]
	assert ruta == "config/update" and parametros["opt"]["continue"] and parametros["opt"]["result"] == "onedrive"
	assert parametros["parameters"] == {"config_is_local": "true", "config_auth_no_browser": "true", "region": "global"}


def _esperar_53682_libre(segundos: float = 15) -> None:
	limite = time.monotonic() + segundos
	while time.monotonic() < limite:
		with socket.socket() as enchufe:
			if enchufe.connect_ex(("127.0.0.1", 53682)) != 0:
				return
		time.sleep(0.2)


@pytest.mark.componentes
@requiere_rclone
def test_tras_una_pregunta_rclone_no_vuelve_a_preguntar_por_el_navegador(nubes):
	"""Con rclone real: Drive sin identificador pregunta por el compartido; al responder, sigue a la autorización.

	Antes, la respuesta se enviaba sin los parámetros y rclone preguntaba «¿usar el
	navegador?» (``config_is_local``) e intentaba abrirlo él. Sin red ni navegador:
	solo se pide la dirección de autorización y se cancela.
	"""
	servicio = modulo("servicio")
	_esperar_53682_libre()
	alta = servicio.Alta(nubes, "drive_sin_id", "drive", {"scope": "drive", "config_is_local": "true", "config_auth_no_browser": "true"})
	try:
		paso = alta.empezar()
		assert paso.tipo == "pregunta" and paso.nombre == "config_shared_client_id"
		paso = alta.responder("true", paso)
		assert paso.tipo == "oauth", f"rclone volvió a preguntar: {paso.nombre}"
		assert paso.url.startswith("http://127.0.0.1:53682/")
	finally:
		alta.cancelar()
		nubes.borrar_remoto("drive_sin_id")


def test_traduccion_de_las_preguntas_habituales(zc):
	preguntas = modulo("preguntas")
	texto, ejemplos, traducida = preguntas.traducir("config_type", "Type of connection",
		[("onedrive", "OneDrive Personal or Business"), ("sharepoint", "Root Sharepoint site"), ("nuevo", "Something new")])
	assert traducida and texto.startswith("Tipo de conexión")
	assert ejemplos == [("onedrive", "OneDrive personal o de empresa"), ("sharepoint", "Sitio raíz de SharePoint"), ("nuevo", "Something new")]
	texto, _e, _t = preguntas.traducir("config_type", "Type of authentication.", [("traditional", "Traditional")])
	assert texto == "Forma de iniciar sesión." and _e[0][1].startswith("Tradicional")
	texto, _e, _t = preguntas.traducir("config_drive_ok",
		'Drive OK?\n\nFound drive "OneDrive" of type "personal"\nURL: https://onedrive.live.com/x\n', [])
	assert "«OneDrive»" in texto and "personal" in texto and "https://onedrive.live.com/x" in texto and texto.endswith("¿Es la unidad correcta?")
	texto, _e, _t = preguntas.traducir("config_2fa_sms", "Enter the verification code sent to +34 ***-**-12", [])
	assert texto.endswith("+34 ***-**-12.")
	assert "sms" in preguntas.traducir("config_2fa", "Two-factor authentication: enter your 2FA code or type 'sms'", [])[0]
	assert "sms" not in preguntas.traducir("config_2fa", "Two-factor authentication code", [])[0]
	texto, _e, _t = preguntas.traducir("config_shared_client_id",
		"rclone's shared Google Drive client_id is being retired and will stop working during 2026.", [])
	assert "Google Drive" in texto and "2026" in texto
	for nombre in ("config_driveid", "config_change_team_drive", "config_team_drive", "config_2fa_phone", "config_is_local"):
		assert preguntas.traducir(nombre, "English", [])[2], nombre
	assert preguntas.traducir("chunk_size", "Upload chunk size.", [("8M", "8M")]) == ("Upload chunk size.", [("8M", "8M")], False)


# ── Selector de unidades y preferencias ────────────────────────────────────────


def _carpetas_falsas(nubes, monkeypatch, funcion) -> None:
	"""Sustituye la detección: espera a la búsqueda real que lanza la activación y olvida su resultado."""
	nubes.asegurar_deteccion().join(30)
	monkeypatch.setattr(modulo("locales"), "carpetas_de_nube", funcion)
	nubes.olvidar_carpetas()


def test_las_carpetas_salen_en_el_selector_como_rutas_locales(zc, monkeypatch, tmp_path):
	nubes = zc.instancia.nubes
	locales = modulo("locales")
	onedrive, icloud = tmp_path / "OneDrive", tmp_path / "iCloudDrive"
	carpetas = [locales.CarpetaNube("OneDrive - Personal", "OneDrive", str(onedrive), "prueba"),
		locales.CarpetaNube("iCloud Drive", "iCloud Drive", str(icloud), "prueba")]
	_carpetas_falsas(nubes, monkeypatch, lambda fuentes=None: list(carpetas))
	unidades = nubes.unidades()
	assert [(u.texto, u.direccion) for u in unidades] == [("OneDrive - Personal", str(onedrive)), ("iCloud Drive", str(icloud))]
	assert "://" not in unidades[0].direccion and str(onedrive) in unidades[0].descripcion
	# Lo que la persona desmarca no sale; con la opción desactivada no sale ninguna.
	assert nubes.carpetas_por_revisar(carpetas) == carpetas
	nubes.guardar_carpetas(carpetas, [carpetas[1]])
	assert [u.texto for u in nubes.unidades()] == ["iCloud Drive"]
	assert nubes.carpetas_por_revisar(carpetas) == []
	assert zc.config.obtener("carpetas_ocultas") == [carpetas[0].clave]
	zc.config.establecer("carpetas_programas", False)
	assert nubes.unidades() == []
	# Volver a marcarla la muestra y reactiva la opción.
	nubes.guardar_carpetas(carpetas, carpetas)
	assert zc.config.obtener("carpetas_programas") is True and len(nubes.unidades()) == 2


def test_un_fallo_de_la_deteccion_no_rompe_el_selector(zc, monkeypatch):
	def falla(fuentes=None):
		raise RuntimeError("inesperado")

	_carpetas_falsas(zc.instancia.nubes, monkeypatch, falla)
	assert zc.instancia.nubes.unidades() == []


def test_el_selector_abre_una_ruta_local_como_disco(tmp_path):
	"""El selector lleva el panel a ``UnidadVirtual.direccion``: una ruta local la abre el proveedor de disco, sin rclone."""
	from app.services.vfs import resolver

	proveedor, ruta, _nombre = resolver.abrir_ruta(str(tmp_path))
	assert getattr(proveedor, "esquema", "") == "local" and os.path.normcase(ruta) == os.path.normcase(str(tmp_path))


# ── Ventanas del asistente ──────────────────────────────────────────────────────


wx = pytest.importorskip("wx")


def test_dialogo_de_carpetas_anuncia_y_devuelve_las_marcadas(app_wx, zc):
	asistente = modulo("ui.asistente")
	locales = modulo("locales")
	carpetas = [locales.CarpetaNube("OneDrive - Personal", "OneDrive", r"C:\Users\ana\OneDrive", "prueba"),
		locales.CarpetaNube("iCloud Drive", "iCloud Drive", r"C:\Users\ana\iCloudDrive", "prueba")]
	dialogo = asistente.DialogoCarpetas(zc, None, carpetas, [True, False])
	try:
		assert "Este equipo ya tiene OneDrive - Personal e iCloud Drive. ¿Usar sus carpetas sin iniciar sesión?" in \
			dialogo.explicacion.GetValue()
		assert [c.nombre for c in dialogo.elegidas()] == ["OneDrive - Personal"]
		dialogo.lista.CheckItem(1, True)
		assert len(dialogo.elegidas()) == 2
	finally:
		dialogo.Destroy()


def test_datos_de_un_servicio_de_navegador_solo_piden_el_nombre(app_wx, zc):
	asistente = modulo("ui.asistente")
	servicio = modulo("servicio")
	catalogo = zc.instancia.nubes.catalogo
	for id_ in ("drive", "onedrive", "dropbox", "box", "pcloud"):
		dialogo = asistente.DialogoDatos(zc, None, catalogo.servicio(id_))
		try:
			assert dialogo.controles == {} and dialogo.boton_avanzadas is not None, id_
		finally:
			dialogo.Destroy()
	dialogo = asistente.DialogoDatos(zc, None, catalogo.servicio("mega"))
	try:
		assert dialogo.boton_avanzadas is None and set(dialogo.controles) == {"user", "pass", "2fa"}
	finally:
		dialogo.Destroy()
	avanzadas = asistente.DialogoAvanzadas(zc, None, catalogo.servicio("onedrive"))
	try:
		avanzadas.controles["client_id"].SetValue("mi-id")
		avanzadas.otro_equipo.SetValue(True)
		assert avanzadas.valores() == {"client_id": "mi-id", "client_secret": "", servicio.OTRO_EQUIPO: "true"}
	finally:
		avanzadas.Destroy()
	jotta = asistente.DialogoAvanzadas(zc, None, catalogo.servicio("jottacloud"))
	try:
		assert jotta.otro_equipo is None, "Jottacloud no se puede autorizar desde otro equipo"
	finally:
		jotta.Destroy()


def test_pregunta_traducida_en_el_dialogo(app_wx, zc):
	asistente = modulo("ui.asistente")
	servicio = modulo("servicio")
	paso = servicio.Paso("pregunta", opcion={"Name": "config_type", "Help": "Type of connection", "Exclusive": True,
		"DefaultStr": "onedrive", "Examples": [{"Value": "onedrive", "Help": "OneDrive Personal or Business"},
			{"Value": "sharepoint", "Help": "Root Sharepoint site"}]})
	dialogo = asistente.DialogoPregunta(zc, None, paso, "OneDrive")
	try:
		assert dialogo.pregunta.GetValue().startswith("OneDrive. Tipo de conexión")
		assert dialogo.control.GetString(0) == "OneDrive personal o de empresa (onedrive)"
		assert dialogo.respuesta() == "onedrive"
	finally:
		dialogo.Destroy()


# ── Correcciones de la revisión ─────────────────────────────────────────────────


def test_jottacloud_no_fija_la_marca_blanca_y_avisa_de_la_sesion_unica(zc):
	jotta = zc.instancia.nubes.catalogo.servicio("jottacloud")
	assert "config_traditional" not in jotta.opciones, "rclone pregunta el servicio (Jottacloud, Telia, Elgiganten...)"
	assert any("una sesión activa" in a for a in jotta.avisos)
	preguntas = modulo("preguntas")
	assert preguntas.traducir("config_traditional", "White-label service.", [])[2]


@pytest.mark.parametrize(("guardado", "esperado"), [
	({"type": "jottacloud", "token": "x"}, {"config_non_standard": "false"}),
	({"type": "jottacloud", "device": "Mi equipo", "mountpoint": "Copias"},
		{"config_non_standard": "true", "config_device": "Mi equipo", "config_mountpoint": "Copias"}),
	({"type": "jottacloud", "device": "Jotta", "mountpoint": "Sync"},
		{"config_non_standard": "true", "config_device": "Jotta", "config_mountpoint": "Sync"}),
])
def test_reconectar_jottacloud_conserva_dispositivo_y_punto_de_montaje(zc, monkeypatch, guardado, esperado):
	nubes = zc.instancia.nubes
	cuentas = modulo("cuentas")
	monkeypatch.setattr(nubes, "llamar", lambda ruta, **parametros: dict(guardado) if ruta == "config/get" else {})
	alta = nubes.reconectar(cuentas.Cuenta(id="j", nombre="J", servicio="jottacloud"))
	assert "config_traditional" not in alta.parametros and "config_non_standard" not in alta.parametros
	assert alta.parametros["config_type"] == "traditional"
	assert alta._preparar() == esperado


def test_el_alta_de_drive_con_el_identificador_de_rclone_deja_preguntar_por_las_unidades_compartidas(zc, monkeypatch):
	ordenes = modulo("ui.ordenes")
	comun = modulo("ui.comun")
	nubes = zc.instancia.nubes
	monkeypatch.setattr(nubes, "carpetas_en_cache", lambda: [])
	monkeypatch.setattr(comun, "opcion", lambda _zc, _texto, _titulo, opciones: next(
		i for i, o in enumerate(opciones) if "rclone" in o))
	valores = ordenes.Ordenes(zc, nubes)._drive_sin_identificador(None, nubes.catalogo.servicio("drive"), {})
	assert valores == {"config_shared_client_id": "true"}
	assert "unidades compartidas" in nubes.catalogo.servicio("drive").descripcion


def test_elegir_la_carpeta_de_google_drive_no_vuelve_a_mostrar_las_demas(zc, monkeypatch, tmp_path):
	nubes = zc.instancia.nubes
	locales = modulo("locales")
	drive = locales.CarpetaNube("Google Drive", "Google Drive", str(tmp_path / "G"), "prueba")
	otras = [locales.CarpetaNube("OneDrive - Personal", "OneDrive", str(tmp_path / "O"), "prueba"),
		locales.CarpetaNube("iCloud Drive", "iCloud Drive", str(tmp_path / "I"), "prueba")]
	detectadas = [*otras, drive]
	_carpetas_falsas(nubes, monkeypatch, lambda fuentes=None: list(detectadas))
	# La persona había desactivado todas: solo sale Google Drive.
	zc.config.establecer("carpetas_programas", False)
	nubes.mostrar_carpeta(drive, detectadas)
	assert [u.texto for u in nubes.unidades()] == ["Google Drive"]
	# Con la opción activada y OneDrive oculto a propósito: OneDrive sigue oculto.
	zc.config.establecer_varias({"carpetas_programas": True, "carpetas_ocultas": [otras[0].clave, drive.clave]})
	nubes.mostrar_carpeta(drive, detectadas)
	assert [u.texto for u in nubes.unidades()] == ["iCloud Drive", "Google Drive"]
	# Por el asistente (opción «carpeta»): igual, sin activar las demás.
	zc.config.establecer_varias({"carpetas_programas": False, "carpetas_ocultas": []})
	ordenes = modulo("ui.ordenes")
	comun = modulo("ui.comun")
	monkeypatch.setattr(comun, "opcion", lambda _zc, _texto, _titulo, opciones: 0)
	abiertas: list[str] = []
	monkeypatch.setattr(zc, "abrir_ruta", lambda ruta: abiertas.append(ruta), raising=False)
	assert ordenes.Ordenes(zc, nubes)._drive_sin_identificador(None, nubes.catalogo.servicio("drive"), {}) is None
	assert abiertas == [drive.ruta] and [u.texto for u in nubes.unidades()] == ["Google Drive"]


def test_la_deteccion_se_recuerda_y_no_hace_esperar_al_selector(zc, monkeypatch):
	import threading

	nubes = zc.instancia.nubes
	locales = modulo("locales")
	llamadas: list[int] = []
	soltar = threading.Event()

	def lenta(fuentes=None):
		llamadas.append(1)
		soltar.wait(10)
		return [locales.CarpetaNube("OneDrive", "OneDrive", "C:\\O", "prueba")]

	_carpetas_falsas(nubes, monkeypatch, lenta)
	inicio = time.monotonic()
	assert nubes.carpetas_locales(espera_s=0.2) == [], "una búsqueda lenta no retrasa el selector"
	assert time.monotonic() - inicio < 2
	soltar.set()
	nubes.asegurar_deteccion().join(10)
	assert [c.nombre for c in nubes.carpetas_locales()] == ["OneDrive"]
	assert [c.nombre for c in nubes.carpetas_locales()] == ["OneDrive"] and len(llamadas) == 1, "se recuerda"
	assert nubes.carpetas_en_cache() is not None


def test_una_ruta_que_no_responde_tiene_tope(zc):
	locales = modulo("locales")
	inicio = time.monotonic()
	assert locales.con_tope(lambda: time.sleep(5) or True, 0.2, False) is False
	assert time.monotonic() - inicio < 2
	assert locales.con_tope(lambda: "hecho", 1, None) == "hecho"
	with pytest.raises(ValueError):
		locales.con_tope(lambda: int("x"), 1, None)


def test_rutas_con_variables_relativas_o_no_textuales(zc, monkeypatch):
	locales = modulo("locales")
	monkeypatch.setenv("ZC_PERFIL_PRUEBA", r"C:\Users\ana")
	registro = RegistroFalso()
	cuentas = r"Software\Microsoft\OneDrive\Accounts"
	registro.poner("HKCU", rf"{cuentas}\Personal", UserFolder=r"%ZC_PERFIL_PRUEBA%\OneDrive")
	registro.poner("HKCU", rf"{cuentas}\Business1", UserFolder="OneDrive relativo")
	registro.poner("HKCU", rf"{cuentas}\Business2", UserFolder=12345)
	registro.poner("HKLM", rf"{RAICES}\Box!{SID}!x", DisplayNameResource="Box")
	registro.poner("HKLM", rf"{RAICES}\Box!{SID}!x\UserSyncRoots", **{SID: b"\x00\x01"})
	comprobadas: list[str] = []
	fuentes = _fuentes(locales, registro, {r"C:\Users\ana\OneDrive"})
	existe = fuentes.existe
	fuentes.existe = lambda ruta: comprobadas.append(ruta) or existe(ruta)
	assert [c.ruta for c in locales.carpetas_de_nube(fuentes)] == [r"C:\Users\ana\OneDrive"]
	assert all(os.path.isabs(r) for r in comprobadas), comprobadas


def test_las_etiquetas_de_las_unidades_se_leen_una_vez(zc):
	locales = modulo("locales")
	veces: list[int] = []

	def etiquetas():
		veces.append(1)
		return [("K:\\", "Google Drive"), ("P:\\", "pCloud Drive")]

	fuentes = _fuentes(locales, RegistroFalso(), {"K:\\", "P:\\"})
	fuentes.etiquetas = etiquetas
	assert {c.proveedor for c in locales.carpetas_de_nube(fuentes)} == {"Google Drive", "pCloud"}
	assert len(veces) == 1


def test_el_enlace_de_una_ficha_solo_puede_ser_https(zc):
	cuentas = modulo("cuentas")
	ficha = {"id": "x", "nombre": "X", "tipo": "x", "autenticacion": "contrasena", "enlace": {"url": "file:///C:/malo.exe", "texto": "T"}}
	assert cuentas._servicio_desde(ficha, "otro.complemento").enlace == {}
	ficha["enlace"] = {"url": "https://ejemplo.com/claves", "texto": "Abrir la página"}
	assert cuentas._servicio_desde(ficha, "otro.complemento").enlace["url"] == "https://ejemplo.com/claves"


def test_kdrive_exige_solo_cifras(zc):
	servicio = modulo("servicio")
	nubes = zc.instancia.nubes
	assert servicio.unidad_kdrive_valida("https://ksuite.infomaniak.com/1/kdrive/app/drive/42/files")
	assert not servicio.unidad_kdrive_valida("mi unidad") and not servicio.unidad_kdrive_valida("")
	from app.plugins import api

	with pytest.raises(api.ErrorArchivos):
		nubes.nueva_cuenta(nubes.catalogo.servicio("kdrive"), "K", {"drive_id": "abc"})


def test_carpeta_de_un_programa_sin_carpetas_vuelve_a_la_lista(zc, monkeypatch):
	ordenes = modulo("ui.ordenes")
	asistente = modulo("ui.asistente")
	comun = modulo("ui.comun")
	nubes = zc.instancia.nubes
	monkeypatch.setattr(nubes, "carpetas_en_cache", lambda: [])
	elegidos = [nubes.catalogo.servicio("carpeta_local"), None]
	abiertos: list[int] = []

	class ServicioFalso:
		def __init__(self, *_args, **_kwargs) -> None:
			abiertos.append(1)

		def elegido(self):
			return elegidos.pop(0)

		def Destroy(self) -> None:  # noqa: N802 - como wx
			pass

	monkeypatch.setattr(asistente, "DialogoServicio", ServicioFalso)
	monkeypatch.setattr(comun, "mostrar_modal", lambda _zc, _dialogo: wx.ID_OK)
	assert ordenes.Ordenes(zc, nubes).asistente(None) is None
	assert len(abiertos) == 2, "tras el aviso, la lista de servicios vuelve a salir"
	assert any("No se ha encontrado" in texto for texto, _nivel in zc.anuncios)


def test_pregunta_de_lista_abierta_muestra_el_texto_y_devuelve_el_valor(app_wx, zc):
	asistente = modulo("ui.asistente")
	servicio = modulo("servicio")
	paso = servicio.Paso("pregunta", opcion={"Name": "config_driveid", "Help": "Select drive you want to use",
		"DefaultStr": "b!AbC", "Examples": [{"Value": "b!AbC", "Help": "OneDrive (personal)"}, {"Value": "b!XyZ", "Help": "Documentos (business)"}]})
	dialogo = asistente.DialogoPregunta(zc, None, paso)
	try:
		assert dialogo.control.GetStrings() == ["OneDrive (personal) (b!AbC)", "Documentos (business) (b!XyZ)"]
		assert dialogo.control.GetValue() == "OneDrive (personal) (b!AbC)" and dialogo.respuesta() == "b!AbC"
		dialogo.control.SetValue("Documentos (business) (b!XyZ)")
		assert dialogo.respuesta() == "b!XyZ"
		dialogo.control.SetValue("otro-valor")
		assert dialogo.respuesta() == "otro-valor"
	finally:
		dialogo.Destroy()


def test_datos_de_kdrive_y_drive_y_ayuda_de_las_avanzadas(app_wx, zc):
	asistente = modulo("ui.asistente")
	catalogo = zc.instancia.nubes.catalogo
	dialogo = asistente.DialogoDatos(zc, None, catalogo.servicio("kdrive"))
	try:
		dialogo.controles["drive_id"].SetValue("mi unidad")
		dialogo._siguiente()
		assert any("solo cifras" in texto for texto, _nivel in zc.anuncios)
	finally:
		dialogo.Destroy()
	drive = asistente.DialogoDatos(zc, None, catalogo.servicio("drive"))
	try:
		avisos = [c for c in drive.panel.GetChildren() if isinstance(c, wx.TextCtrl) and "cómo quiere conectar" in c.GetValue()]
		assert avisos, "en Drive, Siguiente lleva a la pregunta de cómo conectar"
	finally:
		drive.Destroy()
	avanzadas = asistente.DialogoAvanzadas(zc, None, catalogo.servicio("onedrive"))
	try:
		assert avanzadas.explicacion.GetHelpText()
	finally:
		avanzadas.Destroy()
