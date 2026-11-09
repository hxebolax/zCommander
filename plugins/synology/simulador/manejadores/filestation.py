# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""File Station (synology.md 4.3) sobre el árbol en memoria, con tareas en segundo plano que avanzan con el tiempo."""

from __future__ import annotations

import fnmatch
import io
import secrets
import time
import zipfile
from typing import Any

from ..comun import ErrorSim, Peticion, RespuestaBinaria, trozos
from ..estado import Nodo, TareaFondo, normalizar, partes

#: Por debajo de este total, comprimir crea un ZIP de verdad (y extraerlo devuelve sus archivos).
ZIP_REAL_HASTA = 20 * 1024 * 1024
API_TAREAS = ("SYNO.FileStation.CopyMove", "SYNO.FileStation.Delete", "SYNO.FileStation.Compress", "SYNO.FileStation.Extract")


# ── Utilidades ───────────────────────────────────────────────────────────────


def _usuario(pet: Peticion) -> str:
	return pet.sesion.usuario if pet.sesion is not None else ""


def _permiso(pet: Peticion, ruta: str, escribir: bool = False) -> None:
	"""Los usuarios sin privilegios solo ven y cambian lo que les permiten los permisos de la carpeta compartida."""
	if pet.sesion is None or pet.sesion.administrador:
		return
	trozos_ruta = partes(ruta)
	if not trozos_ruta:
		return
	permisos = pet.estado.datos.get("permisos", {}).get(trozos_ruta[0], [])
	propio = next((p for p in permisos if p["name"] == pet.sesion.usuario), None)
	if propio is None or propio["is_deny"] or (escribir and not propio["is_writable"]):
		raise ErrorSim(407, [{"code": 407, "path": ruta}])


def _tipo(nombre: str, es_carpeta: bool) -> str:
	if es_carpeta or "." not in nombre:
		return ""
	return nombre.rsplit(".", 1)[1].upper()


def _entrada(pet: Peticion, ruta: str, nodo: Nodo, adicional: list[str]) -> dict[str, Any]:
	fila: dict[str, Any] = {"isdir": nodo.es_carpeta, "name": nodo.nombre, "path": ruta}
	if adicional:
		extra: dict[str, Any] = {}
		if "real_path" in adicional:
			extra["real_path"] = "/volume1" + ruta
		if "size" in adicional:
			extra["size"] = 4096 if nodo.es_carpeta else nodo.tamano
		if "owner" in adicional:
			extra["owner"] = {"user": nodo.propietario, "group": "users", "uid": 1026, "gid": 100}
		if "time" in adicional:
			extra["time"] = {"atime": int(nodo.modificado), "mtime": int(nodo.modificado), "ctime": int(nodo.modificado),
				"crtime": int(nodo.creado)}
		if "perm" in adicional:
			extra["perm"] = {"posix": 777, "is_acl_mode": True, "acl": {"append": True, "del": True, "exec": True, "read": True,
				"write": True}}
		if "type" in adicional:
			extra["type"] = _tipo(nodo.nombre, nodo.es_carpeta)
		if "mount_point_type" in adicional:
			extra["mount_point_type"] = ""
		if "volume_status" in adicional:
			libre, total = pet.estado.espacio()
			extra["volume_status"] = {"freespace": libre, "totalspace": total, "readonly": False}
		fila["additional"] = extra
	return fila


def _adicional(pet: Peticion) -> list[str]:
	return [str(a) for a in pet.lista("additional")]


def _rutas(pet: Peticion, nombre: str = "path") -> list[str]:
	return [normalizar(str(r)) for r in pet.lista(nombre)]


def _coincide(nombre: str, patron: str) -> bool:
	if not patron:
		return True
	for trozo in patron.split(","):
		trozo = trozo.strip()
		if not trozo:
			continue
		if not any(c in trozo for c in "*?["):
			trozo = f"*{trozo}*"
		if fnmatch.fnmatch(nombre.casefold(), trozo.casefold()):
			return True
	return False


def _nueva_tarea(pet: Peticion, total: int, al_terminar: Any = None, **extra: Any) -> TareaFondo:
	tarea = TareaFondo(pet.estado.nuevo_id(), pet.api, dict(pet.params), time.monotonic(), pet.estado.ritmo_tareas, max(1, total),
		pet.aplicar, al_terminar, usuario=_usuario(pet))
	tarea.resultado.update(extra)
	pet.estado.tareas[tarea.taskid] = tarea
	return tarea


def _tarea(pet: Peticion) -> TareaFondo:
	taskid = pet.texto("taskid")
	tarea = pet.estado.tareas.get(taskid)
	if tarea is None:
		raise ErrorSim(599)
	return tarea


def _estado_tarea(tarea: TareaFondo) -> dict[str, Any]:
	tarea.avanzar()
	if tarea.terminada and tarea.error:
		raise ErrorSim(tarea.error if tarea.error < 1000 else tarea.error,
			[{"code": tarea.error, "path": str(tarea.params.get("path", ""))}])
	progreso = tarea.progreso()
	datos = {"finished": tarea.terminada or tarea.detenida, "progress": round(progreso, 3),
		"processed_size": int(tarea.total * progreso), "total": tarea.total}
	datos.update(tarea.resultado)
	return datos


def _parar(pet: Peticion) -> dict[str, Any]:
	tarea = _tarea(pet)
	tarea.detenida = True
	return {}


def _limpiar(pet: Peticion) -> dict[str, Any]:
	pet.estado.tareas.pop(pet.texto("taskid"), None)
	return {}


# ── Información y listados ───────────────────────────────────────────────────


def info(pet: Peticion) -> dict[str, Any]:
	return {"hostname": pet.estado.datos["red"]["hostname"], "is_manager": bool(pet.sesion and pet.sesion.administrador),
		"support_sharing": True, "support_virtual_protocol": ["cifs", "iso", "nfs"], "support_file_request": True, "uid": 1026,
		"system_codepage": "spn", "items": []}


def lista_carpetas(pet: Peticion) -> dict[str, Any]:
	adicional = _adicional(pet)
	compartidas = []
	for carpeta in pet.estado.datos["carpetas"]:
		if carpeta.get("hidden") or carpeta["name"] not in pet.estado.raiz.hijos:
			continue
		ruta = "/" + carpeta["name"]
		try:
			_permiso(pet, ruta)
		except ErrorSim:
			continue
		compartidas.append(_entrada(pet, ruta, pet.estado.raiz.hijos[carpeta["name"]], adicional))
	inicio, limite = pet.entero("offset", 0), pet.entero("limit", 0)
	trozo = compartidas[inicio:inicio + limite] if limite > 0 else compartidas[inicio:]
	return {"offset": inicio, "total": len(compartidas), "shares": trozo}


def listar(pet: Peticion) -> dict[str, Any]:
	pet.exigir("folder_path")
	carpeta = normalizar(pet.texto("folder_path"))
	_permiso(pet, carpeta)
	nodo = pet.estado.nodo(carpeta)
	if not nodo.es_carpeta:
		raise ErrorSim(408, [{"code": 408, "path": carpeta}])
	adicional = _adicional(pet)
	tipo = pet.texto("filetype", "all")
	patron = pet.texto("pattern")
	hijos = [h for h in nodo.hijos.values() if not h.nombre.startswith("#") and _coincide(h.nombre, patron)
		and (tipo == "all" or (tipo == "dir") == h.es_carpeta)]
	orden = pet.texto("sort_by", "name")
	claves = {"size": lambda h: h.tamano, "mtime": lambda h: h.modificado, "crtime": lambda h: h.creado,
		"type": lambda h: _tipo(h.nombre, h.es_carpeta)}
	hijos.sort(key=claves.get(orden, lambda h: h.nombre.casefold()), reverse=pet.texto("sort_direction", "asc") == "desc")
	inicio, limite = pet.entero("offset", 0), pet.entero("limit", 0)
	trozo = hijos[inicio:inicio + limite] if limite > 0 else hijos[inicio:]
	base = "" if carpeta == "/" else carpeta
	return {"offset": inicio, "total": len(hijos), "files": [_entrada(pet, f"{base}/{h.nombre}", h, adicional) for h in trozo]}


def obtener_info(pet: Peticion) -> dict[str, Any]:
	adicional = _adicional(pet)
	archivos = []
	for ruta in _rutas(pet):
		try:
			_permiso(pet, ruta)
			nodo = pet.estado.nodo(ruta)
		except ErrorSim:
			archivos.append({"code": 408, "path": ruta, "name": ruta.rsplit("/", 1)[-1]})
			continue
		archivos.append(_entrada(pet, ruta, nodo, adicional))
	return {"files": archivos}


# ── Búsqueda, tamaño de carpeta y MD5 ────────────────────────────────────────


def buscar_inicio(pet: Peticion) -> dict[str, Any]:
	carpetas = _rutas(pet, "folder_path") or ["/"]
	patron, extension = pet.texto("pattern"), pet.texto("extension").lstrip(".").lower()
	tipo, recursiva = pet.texto("filetype", "all"), pet.booleano("recursive", True)
	encontrados: list[dict[str, Any]] = []

	def recorrer(ruta: str, nodo: Nodo, profundidad: int) -> None:
		for hijo in nodo.hijos.values():
			if hijo.nombre.startswith("#"):
				continue
			ruta_hijo = f"{'' if ruta == '/' else ruta}/{hijo.nombre}"
			valido = _coincide(hijo.nombre, patron) and (tipo == "all" or (tipo == "dir") == hijo.es_carpeta)
			if valido and extension and not hijo.nombre.lower().endswith("." + extension):
				valido = False
			if valido:
				encontrados.append(_entrada(pet, ruta_hijo, hijo, ["real_path", "size", "time", "type"]))
			if hijo.es_carpeta and recursiva:
				recorrer(ruta_hijo, hijo, profundidad + 1)

	for carpeta in carpetas:
		_permiso(pet, carpeta)
		recorrer(carpeta, pet.estado.nodo(carpeta), 0)
	tarea = _nueva_tarea(pet, len(encontrados) or 1)
	pet.estado.busquedas[tarea.taskid] = {"files": encontrados}
	return {"taskid": tarea.taskid, "has_not_index_share": False}


def buscar_lista(pet: Peticion) -> dict[str, Any]:
	tarea = _tarea(pet)
	tarea.avanzar()
	archivos = pet.estado.busquedas.get(tarea.taskid, {}).get("files", [])
	visibles = archivos if tarea.terminada else archivos[: int(len(archivos) * tarea.progreso())]
	inicio, limite = pet.entero("offset", 0), pet.entero("limit", 0)
	trozo = visibles[inicio:inicio + limite] if limite > 0 else visibles[inicio:]
	return {"finished": tarea.terminada or tarea.detenida, "offset": inicio, "total": len(visibles), "files": trozo}


def buscar_limpiar(pet: Peticion) -> dict[str, Any]:
	for taskid in [str(t) for t in pet.lista("taskid")] or [pet.texto("taskid")]:
		pet.estado.tareas.pop(taskid, None)
		pet.estado.busquedas.pop(taskid, None)
	return {}


def tamano_inicio(pet: Peticion) -> dict[str, Any]:
	carpetas = archivos = total = 0
	for ruta in _rutas(pet):
		_permiso(pet, ruta)
		c, a, t = pet.estado.tamano_total(pet.estado.nodo(ruta))
		carpetas, archivos, total = carpetas + c, archivos + a, total + t
	tarea = _nueva_tarea(pet, total, num_dir=carpetas, num_file=archivos, total_size=total)
	return {"taskid": tarea.taskid}


def md5_inicio(pet: Peticion) -> dict[str, Any]:
	pet.exigir("file_path")
	ruta = normalizar(pet.texto("file_path"))
	_permiso(pet, ruta)
	nodo = pet.estado.nodo(ruta)
	if nodo.es_carpeta:
		raise ErrorSim(400)
	tarea = _nueva_tarea(pet, nodo.tamano, md5=pet.estado.md5(nodo, ruta))
	return {"taskid": tarea.taskid}


def estado_generico(pet: Peticion) -> dict[str, Any]:
	return _estado_tarea(_tarea(pet))


def comprobar_permiso(pet: Peticion) -> dict[str, Any]:
	carpeta = normalizar(pet.texto("path"))
	_permiso(pet, carpeta, escribir=True)
	nodo = pet.estado.nodo(carpeta)
	if not nodo.es_carpeta:
		raise ErrorSim(408)
	nombre = pet.texto("filename")
	if nombre and nombre in nodo.hijos and not pet.booleano("overwrite"):
		raise ErrorSim(1805)
	return {"blSkip": False}


def comprobar_existe(pet: Peticion) -> dict[str, Any]:
	return {"exists": [pet.estado.existe(r) for r in _rutas(pet)]}


# ── Subir y descargar ────────────────────────────────────────────────────────


def subir(pet: Peticion) -> dict[str, Any]:
	if pet.archivo is None or not pet.nombre_archivo:
		raise ErrorSim(1802)
	carpeta = normalizar(pet.texto("path"))
	_permiso(pet, carpeta, escribir=True)
	if not pet.estado.existe(carpeta):
		if not pet.booleano("create_parents"):
			raise ErrorSim(408, [{"code": 408, "path": carpeta}])
		if pet.aplicar:
			pet.estado._asegurar_carpeta(carpeta)
	sobrescribir = pet.texto("overwrite")
	permite = sobrescribir in ("overwrite", "true")
	nombre = pet.nombre_archivo.replace("\\", "/").rsplit("/", 1)[-1]
	destino = f"{'' if carpeta == '/' else carpeta}/{nombre}"
	if pet.estado.existe(destino) and not permite:
		if sobrescribir == "skip":
			return {"blSkip": True, "file": nombre, "pid": 0, "progress": 100}
		raise ErrorSim(1805)
	if pet.aplicar:
		padre = pet.estado.nodo(carpeta)
		anterior = padre.hijos.get(nombre)
		marca = pet.entero("mtime", 0) / 1000 or time.time()
		padre.hijos[nombre] = Nodo(nombre, False, len(pet.archivo), marca, time.time(), pet.archivo, _usuario(pet))
		pet.estado.sumar_uso(len(pet.archivo) - (anterior.tamano if anterior is not None else 0))
	return {"blSkip": False, "file": nombre, "pid": 0, "progress": 100}


def descargar(pet: Peticion) -> RespuestaBinaria:
	rutas = _rutas(pet)
	if not rutas:
		raise ErrorSim(114)
	for ruta in rutas:
		_permiso(pet, ruta)
	nodos = [(r, pet.estado.nodo(r)) for r in rutas]
	if len(nodos) == 1 and not nodos[0][1].es_carpeta:
		ruta, nodo = nodos[0]
		return RespuestaBinaria(nodo.nombre, nodo.tamano, pet.estado.contenido(nodo, ruta))
	memoria = io.BytesIO()
	with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zip_:
		for ruta, nodo in nodos:
			_al_zip(pet, zip_, ruta, nodo, nodo.nombre)
	datos = memoria.getvalue()
	nombre = (nodos[0][1].nombre if len(nodos) == 1 else "descarga") + ".zip"
	return RespuestaBinaria(nombre, len(datos), trozos(datos))


def _al_zip(pet: Peticion, zip_: zipfile.ZipFile, ruta: str, nodo: Nodo, interior: str) -> None:
	if nodo.es_carpeta:
		zip_.writestr(interior + "/", b"")
		for hijo in nodo.hijos.values():
			_al_zip(pet, zip_, f"{ruta}/{hijo.nombre}", hijo, f"{interior}/{hijo.nombre}")
		return
	if nodo.tamano > ZIP_REAL_HASTA and nodo.contenido is None:
		raise ErrorSim(401)
	zip_.writestr(interior, b"".join(pet.estado.contenido(nodo, ruta)))


# ── Copiar, mover, borrar, crear y renombrar ─────────────────────────────────


def _copiar_nodo(pet: Peticion, origen: str, carpeta_destino: str, mover: bool, sobrescribir: bool) -> None:
	nodo = pet.estado.nodo(origen)
	destino = pet.estado.nodo(carpeta_destino)
	if not destino.es_carpeta:
		raise ErrorSim(1002)
	if (carpeta_destino + "/").startswith(origen + "/"):
		raise ErrorSim(1002)
	existente = destino.hijos.get(nodo.nombre)
	if existente is not None and existente is not nodo:
		if not sobrescribir:
			raise ErrorSim(1003)
		if existente.es_carpeta != nodo.es_carpeta:
			raise ErrorSim(1004)
	if mover:
		padre, nombre = pet.estado.padre_de(origen)
		del padre.hijos[nombre]
		destino.hijos[nodo.nombre] = nodo
	else:
		copia = nodo.clonar()
		destino.hijos[nodo.nombre] = copia
		pet.estado.sumar_uso(pet.estado.tamano_total(copia)[2])


def copiar_inicio(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	pet.exigir("dest_folder_path")
	destino = normalizar(pet.texto("dest_folder_path"))
	mover = pet.booleano("remove_src")
	indicado = "overwrite" in pet.params
	sobrescribir = pet.booleano("overwrite")
	_permiso(pet, destino, escribir=True)
	total = 0
	conflicto = 0
	carpeta = pet.estado.nodo(destino)
	for ruta in rutas:
		_permiso(pet, ruta, escribir=mover)
		nodo = pet.estado.nodo(ruta)
		total += pet.estado.tamano_total(nodo)[2]
		if nodo.nombre in carpeta.hijos and carpeta.hijos[nodo.nombre] is not nodo and not sobrescribir:
			conflicto = 1003 if not indicado else 0

	def terminar() -> dict[str, Any]:
		omitidos = 0
		for ruta in rutas:
			try:
				_copiar_nodo(pet, ruta, destino, mover, sobrescribir)
			except ErrorSim as error:
				if error.codigo == 1003 and indicado:
					omitidos += 1
					continue
				raise
		accion = "movido" if mover else "copiado"
		pet.estado.anotar_registro("info", f"Se han {accion} {len(rutas) - omitidos} elementos a [{destino}] con File Station.",
			_usuario(pet))
		return {}

	tarea = _nueva_tarea(pet, total, terminar, dest_folder_path=destino, path=rutas[0] if rutas else "")
	tarea.error = conflicto
	if conflicto:
		tarea.al_terminar = None
	return {"taskid": tarea.taskid}


def _a_papelera(pet: Peticion, ruta: str) -> bool:
	trozos_ruta = partes(ruta)
	compartida = pet.estado.es_compartida(trozos_ruta[0]) if trozos_ruta else None
	if compartida is None or not compartida.get("recyclebin") or len(trozos_ruta) < 2:
		return False
	papelera = pet.estado._asegurar_carpeta(f"/{trozos_ruta[0]}/#recycle")
	padre, nombre = pet.estado.padre_de(ruta)
	nodo = padre.hijos.pop(nombre)
	destino = nombre
	while destino in papelera.hijos:
		destino = f"{nombre}.{secrets.token_hex(2)}"
	nodo.nombre = destino
	papelera.hijos[destino] = nodo
	return True


def _borrar(pet: Peticion, rutas: list[str]) -> None:
	for ruta in rutas:
		if len(partes(ruta)) < 2:
			raise ErrorSim(900, [{"code": 407, "path": ruta}])
		if _a_papelera(pet, ruta):
			continue
		padre, nombre = pet.estado.padre_de(ruta)
		nodo = padre.hijos.pop(nombre)
		pet.estado.sumar_uso(-pet.estado.tamano_total(nodo)[2])


def borrar_inicio(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	if not rutas:
		raise ErrorSim(114)
	total = 0
	for ruta in rutas:
		_permiso(pet, ruta, escribir=True)
		total += pet.estado.tamano_total(pet.estado.nodo(ruta))[1]

	def terminar() -> dict[str, Any]:
		_borrar(pet, rutas)
		return {}

	tarea = _nueva_tarea(pet, total, terminar, path=rutas[0])
	return {"taskid": tarea.taskid}


def borrar_ya(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	for ruta in rutas:
		_permiso(pet, ruta, escribir=True)
		pet.estado.nodo(ruta)
	if pet.aplicar:
		_borrar(pet, rutas)
	return {}


def crear_carpeta(pet: Peticion) -> dict[str, Any]:
	carpetas = _rutas(pet, "folder_path")
	nombres = [str(n) for n in pet.lista("name")]
	if not carpetas or len(carpetas) != len(nombres):
		raise ErrorSim(114)
	creadas = []
	for carpeta, nombre in zip(carpetas, nombres, strict=True):
		if not nombre or "/" in nombre or nombre in (".", ".."):
			raise ErrorSim(1100, [{"code": 418, "path": carpeta}])
		_permiso(pet, carpeta, escribir=True)
		if not pet.estado.existe(carpeta):
			if not pet.booleano("force_parent"):
				raise ErrorSim(1100, [{"code": 408, "path": carpeta}])
			if pet.aplicar:
				pet.estado._asegurar_carpeta(carpeta)
		ruta = f"{'' if carpeta == '/' else carpeta}/{nombre}"
		if pet.estado.existe(ruta):
			raise ErrorSim(1100, [{"code": 414, "path": ruta}])
		if pet.aplicar:
			ahora = time.time()
			pet.estado.nodo(carpeta).hijos[nombre] = Nodo(nombre, True, modificado=ahora, creado=ahora, propietario=_usuario(pet))
		creadas.append({"isdir": True, "name": nombre, "path": ruta})
	return {"folders": creadas}


def renombrar(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	nombres = [str(n) for n in pet.lista("name")]
	if not rutas or len(rutas) != len(nombres):
		raise ErrorSim(114)
	resultado = []
	for ruta, nombre in zip(rutas, nombres, strict=True):
		if not nombre or "/" in nombre:
			raise ErrorSim(1200, [{"code": 418, "path": ruta}])
		_permiso(pet, ruta, escribir=True)
		padre, actual = pet.estado.padre_de(ruta)
		if actual not in padre.hijos:
			raise ErrorSim(1200, [{"code": 408, "path": ruta}])
		nueva = ruta.rsplit("/", 1)[0] + "/" + nombre
		if nombre != actual and nombre in padre.hijos:
			raise ErrorSim(1200, [{"code": 414, "path": nueva}])
		if pet.aplicar:
			nodo = padre.hijos.pop(actual)
			nodo.nombre = nombre
			padre.hijos[nombre] = nodo
		resultado.append({"isdir": padre.hijos.get(nombre, padre.hijos.get(actual)).es_carpeta, "name": nombre, "path": nueva})
	return {"files": resultado}


# ── Comprimir y extraer ──────────────────────────────────────────────────────


def comprimir_inicio(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	pet.exigir("dest_file_path")
	destino = normalizar(pet.texto("dest_file_path"))
	formato = pet.texto("format", "zip")
	if formato not in ("zip", "7z"):
		raise ErrorSim(400)
	padre_destino = destino.rsplit("/", 1)[0] or "/"
	_permiso(pet, padre_destino, escribir=True)
	pet.estado.nodo(padre_destino)
	total = 0
	for ruta in rutas:
		_permiso(pet, ruta)
		total += pet.estado.tamano_total(pet.estado.nodo(ruta))[2]

	def terminar() -> dict[str, Any]:
		padre, nombre = pet.estado.padre_de(destino)
		contenido = None
		if formato == "zip" and total <= ZIP_REAL_HASTA:
			memoria = io.BytesIO()
			with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zip_:
				for ruta in rutas:
					nodo = pet.estado.nodo(ruta)
					_al_zip(pet, zip_, ruta, nodo, nodo.nombre)
			contenido = memoria.getvalue()
		tamano = len(contenido) if contenido is not None else max(1, int(total * 0.62))
		ahora = time.time()
		padre.hijos[nombre] = Nodo(nombre, False, tamano, ahora, ahora, contenido, _usuario(pet))
		pet.estado.sumar_uso(tamano)
		return {"dest_file_path": destino}

	tarea = _nueva_tarea(pet, total, terminar, dest_file_path=destino)
	return {"taskid": tarea.taskid}


def _zip_de(pet: Peticion, ruta: str) -> zipfile.ZipFile | None:
	nodo = pet.estado.nodo(ruta)
	if nodo.es_carpeta:
		raise ErrorSim(1401)
	if nodo.contenido is None:
		return None
	try:
		return zipfile.ZipFile(io.BytesIO(nodo.contenido))
	except zipfile.BadZipFile as error:
		raise ErrorSim(1401) from error


def extraer_lista(pet: Peticion) -> dict[str, Any]:
	pet.exigir("file_path")
	ruta = normalizar(pet.texto("file_path"))
	_permiso(pet, ruta)
	zip_ = _zip_de(pet, ruta)
	if zip_ is None:
		elementos = [{"item_id": 0, "name": "contenido de ejemplo.txt", "path": "contenido de ejemplo.txt", "size": 1024,
			"pack_size": 512, "is_dir": False, "mtime": "2026-11-01 10:00:00"}]
	else:
		elementos = [{"item_id": i, "name": z.filename.rstrip("/").rsplit("/", 1)[-1], "path": z.filename.rstrip("/"),
			"size": z.file_size, "pack_size": z.compress_size, "is_dir": z.is_dir(), "mtime": "%04d-%02d-%02d %02d:%02d:%02d" % z.date_time}
			for i, z in enumerate(zip_.infolist())]
	return {"items": elementos, "total": len(elementos)}


def extraer_inicio(pet: Peticion) -> dict[str, Any]:
	pet.exigir("file_path", "dest_folder_path")
	ruta = normalizar(pet.texto("file_path"))
	destino = normalizar(pet.texto("dest_folder_path"))
	_permiso(pet, ruta)
	_permiso(pet, destino, escribir=True)
	nodo = pet.estado.nodo(ruta)
	pet.estado.nodo(destino)
	sobrescribir = pet.booleano("overwrite")
	subcarpeta = pet.booleano("create_subfolder")

	def terminar() -> dict[str, Any]:
		base = destino
		if subcarpeta:
			nombre = nodo.nombre.rsplit(".", 1)[0]
			base = f"{'' if destino == '/' else destino}/{nombre}"
			pet.estado._asegurar_carpeta(base)
		zip_ = _zip_de(pet, ruta)
		if zip_ is None:
			carpeta = pet.estado.nodo(base)
			texto = f"Contenido de ejemplo extraído de {nodo.nombre} en el NAS de demostración.\n".encode()
			ahora = time.time()
			carpeta.hijos["contenido de ejemplo.txt"] = Nodo("contenido de ejemplo.txt", False, len(texto), ahora, ahora, texto)
			return {}
		for info_zip in zip_.infolist():
			interior = info_zip.filename.rstrip("/")
			destino_interior = f"{'' if base == '/' else base}/{interior}"
			if info_zip.is_dir():
				pet.estado._asegurar_carpeta(destino_interior)
				continue
			carpeta_padre = destino_interior.rsplit("/", 1)[0] or "/"
			carpeta = pet.estado._asegurar_carpeta(carpeta_padre)
			nombre = interior.rsplit("/", 1)[-1]
			if nombre in carpeta.hijos and not sobrescribir:
				continue
			datos = zip_.read(info_zip)
			ahora = time.time()
			carpeta.hijos[nombre] = Nodo(nombre, False, len(datos), ahora, ahora, datos, _usuario(pet))
			pet.estado.sumar_uso(len(datos))
		return {}

	tarea = _nueva_tarea(pet, nodo.tamano, terminar, dest_folder_path=destino)
	return {"taskid": tarea.taskid}


# ── Enlaces compartidos ──────────────────────────────────────────────────────


def _enlace_publico(enlace: dict[str, Any]) -> dict[str, Any]:
	return {k: v for k, v in enlace.items() if k != "password"}


def enlaces_lista(pet: Peticion) -> dict[str, Any]:
	enlaces = [_enlace_publico(e) for e in pet.estado.enlaces.values()]
	return {"links": enlaces, "offset": 0, "total": len(enlaces)}


def enlace_info(pet: Peticion) -> dict[str, Any]:
	enlace = pet.estado.enlaces.get(pet.texto("id"))
	if enlace is None:
		raise ErrorSim(2000)
	return _enlace_publico(enlace)


def enlace_crear(pet: Peticion) -> dict[str, Any]:
	rutas = _rutas(pet)
	if not rutas:
		raise ErrorSim(114)
	contrasena = pet.texto("password")
	if len(contrasena) > 16:
		raise ErrorSim(400)
	enlaces = []
	for ruta in rutas:
		_permiso(pet, ruta)
		nodo = pet.estado.nodo(ruta)
		identificador = secrets.token_urlsafe(9)
		alias = pet.estado.datos["red"]["quickconnect"]["server_alias"]
		enlace = {"id": identificador, "url": f"https://{alias}.quickconnect.to/sharing/{identificador}",
			"qrcode": "", "path": ruta, "name": nodo.nombre, "isFolder": nodo.es_carpeta, "link_owner": _usuario(pet),
			"has_password": bool(contrasena), "password": contrasena, "date_expired": pet.texto("date_expired"),
			"date_available": pet.texto("date_available"), "status": "valid"}
		if pet.aplicar:
			pet.estado.enlaces[identificador] = enlace
		enlaces.append(_enlace_publico(enlace))
	return {"links": enlaces}


def enlace_editar(pet: Peticion) -> dict[str, Any]:
	for identificador in [str(i) for i in pet.lista("id")]:
		enlace = pet.estado.enlaces.get(identificador)
		if enlace is None:
			raise ErrorSim(2000)
		if pet.aplicar:
			for clave in ("date_expired", "date_available"):
				if clave in pet.params:
					enlace[clave] = pet.texto(clave)
			if "password" in pet.params:
				enlace["password"] = pet.texto("password")
				enlace["has_password"] = bool(enlace["password"])
	return {}


def enlace_borrar(pet: Peticion) -> dict[str, Any]:
	for identificador in [str(i) for i in pet.lista("id")]:
		if identificador not in pet.estado.enlaces:
			raise ErrorSim(2000)
		if pet.aplicar:
			del pet.estado.enlaces[identificador]
	return {}


def enlaces_limpiar(pet: Peticion) -> dict[str, Any]:
	if pet.aplicar:
		for identificador in [i for i, e in pet.estado.enlaces.items() if not pet.estado.existe(e["path"])]:
			del pet.estado.enlaces[identificador]
	return {}


# ── Tareas en segundo plano ──────────────────────────────────────────────────


def tareas_lista(pet: Peticion) -> dict[str, Any]:
	filas = []
	for tarea in pet.estado.tareas.values():
		if tarea.api not in API_TAREAS:
			continue
		tarea.avanzar()
		progreso = tarea.progreso()
		filas.append({"api": tarea.api, "method": "start", "version": 1, "taskid": tarea.taskid,
			"finished": tarea.terminada or tarea.detenida, "progress": round(progreso, 3), "processed_size": int(tarea.total * progreso),
			"total": tarea.total, "status": "stopped" if tarea.detenida else ("error" if tarea.error else ""),
			"params": {k: v for k, v in tarea.params.items() if k in ("path", "dest_folder_path", "dest_file_path", "file_path",
				"remove_src")}})
	inicio, limite = pet.entero("offset", 0), pet.entero("limit", 0)
	trozo = filas[inicio:inicio + limite] if limite > 0 else filas[inicio:]
	return {"tasks": trozo, "total": len(filas), "offset": inicio}


def tareas_limpiar(pet: Peticion) -> dict[str, Any]:
	if pet.aplicar:
		for taskid in [t.taskid for t in pet.estado.tareas.values() if t.api in API_TAREAS and (t.terminada or t.detenida)]:
			del pet.estado.tareas[taskid]
	return {}


MANEJADORES = {
	("SYNO.FileStation.Info", "get"): info,
	("SYNO.FileStation.List", "list_share"): lista_carpetas,
	("SYNO.FileStation.List", "list"): listar,
	("SYNO.FileStation.List", "getinfo"): obtener_info,
	("SYNO.FileStation.Search", "start"): buscar_inicio,
	("SYNO.FileStation.Search", "list"): buscar_lista,
	("SYNO.FileStation.Search", "stop"): _parar,
	("SYNO.FileStation.Search", "clean"): buscar_limpiar,
	("SYNO.FileStation.DirSize", "start"): tamano_inicio,
	("SYNO.FileStation.DirSize", "status"): estado_generico,
	("SYNO.FileStation.DirSize", "stop"): _parar,
	("SYNO.FileStation.MD5", "start"): md5_inicio,
	("SYNO.FileStation.MD5", "status"): estado_generico,
	("SYNO.FileStation.MD5", "stop"): _parar,
	("SYNO.FileStation.CheckPermission", "write"): comprobar_permiso,
	("SYNO.FileStation.CheckExist", "check"): comprobar_existe,
	("SYNO.FileStation.Upload", "upload"): subir,
	("SYNO.FileStation.Download", "download"): descargar,
	("SYNO.FileStation.CopyMove", "start"): copiar_inicio,
	("SYNO.FileStation.CopyMove", "status"): estado_generico,
	("SYNO.FileStation.CopyMove", "stop"): _parar,
	("SYNO.FileStation.Delete", "start"): borrar_inicio,
	("SYNO.FileStation.Delete", "status"): estado_generico,
	("SYNO.FileStation.Delete", "stop"): _parar,
	("SYNO.FileStation.Delete", "delete"): borrar_ya,
	("SYNO.FileStation.CreateFolder", "create"): crear_carpeta,
	("SYNO.FileStation.Rename", "rename"): renombrar,
	("SYNO.FileStation.Compress", "start"): comprimir_inicio,
	("SYNO.FileStation.Compress", "status"): estado_generico,
	("SYNO.FileStation.Compress", "stop"): _parar,
	("SYNO.FileStation.Extract", "list"): extraer_lista,
	("SYNO.FileStation.Extract", "start"): extraer_inicio,
	("SYNO.FileStation.Extract", "status"): estado_generico,
	("SYNO.FileStation.Extract", "stop"): _parar,
	("SYNO.FileStation.Sharing", "list"): enlaces_lista,
	("SYNO.FileStation.Sharing", "getinfo"): enlace_info,
	("SYNO.FileStation.Sharing", "create"): enlace_crear,
	("SYNO.FileStation.Sharing", "edit"): enlace_editar,
	("SYNO.FileStation.Sharing", "delete"): enlace_borrar,
	("SYNO.FileStation.Sharing", "clear_invalid"): enlaces_limpiar,
	("SYNO.FileStation.BackgroundTask", "list"): tareas_lista,
	("SYNO.FileStation.BackgroundTask", "clear_finished"): tareas_limpiar,
}
