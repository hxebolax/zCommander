# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Cifrado de archivos (``zc.cifrado``, diseño 2.0, 11.13; bloque P4).

- «Cifrar...»: los elementos de trabajo, cada uno en su ``.zcc`` (AES-256-GCM
  con clave scrypt; las carpetas, antes a un ZIP) o en un 7z con AES-256.
- «Descifrar...»: los ``.zcc`` elegidos (o el de ``ctx.argumento``, que es como
  llega Intro con la asociación «Abrir» ``zc:zc.cifrado:descifrar``).
- Visor de ``.zcc``: muestra el contenido descifrado en memoria (nunca en disco).

La contraseña solo vive en memoria; con ``recordar_en_sesion`` se recuerda la
última que funcionó hasta cerrar zCommander.
"""

from __future__ import annotations

import logging
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_cifrado")

#: Lo más grande que el visor descifra en memoria.
MAX_VISOR = 16 * 1024 * 1024


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		self.zc = zc
		self._recordada = ""
		zc.ordenes.manejador("cifrar", self.cifrar)
		zc.ordenes.manejador("descifrar", self.descifrar)
		zc.visores.visor("ver", self.ver)

	def desactivar(self) -> None:
		self._recordada = ""

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			self.zc.ui.crear_campo  # noqa: B018 - comprueba que hay interfaz (sin ella, NoAdmitido)
		except api.NoAdmitido:
			return []
		from . import dialogos

		return [dialogos.DialogoCifrar(padre, self.zc, "informe.txt")]

	def _contrasena_recordada(self) -> str:
		"""La contraseña de la sesión si ``recordar_en_sesion`` sigue activa; si no, se olvida.

		Se mira al usarla (y no con una suscripción en ``activar``): así activar no
		abre la configuración del complemento.
		"""
		if not self.zc.config.obtener("recordar_en_sesion", False):
			self._recordada = ""
		return self._recordada

	# ── Órdenes ─────────────────────────────────────────────────────────────

	def cifrar(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		entradas = [e for e in panel.elementos_trabajo() if not e.es_superior]
		if not entradas:
			self.zc.anunciar(_("No hay nada que cifrar: elija archivos o carpetas"), api.RESULTADO)
			return
		from . import dialogos, operaciones

		que = entradas[0].nombre if len(entradas) == 1 else _n("{n} elemento", "{n} elementos", len(entradas)).format(n=len(entradas))
		opciones = dialogos.pedir_opciones(self.zc, que)
		if opciones is None:
			return
		self.zc.config.establecer_varias({"formato": opciones.formato, "borrar_originales": opciones.borrar_originales})
		operacion = operaciones.OperacionCifrar(panel.proveedor, entradas, opciones.contrasena, formato=opciones.formato,
			coste=str(self.zc.config.obtener("coste_scrypt", "normal")), borrar_originales=opciones.borrar_originales)
		self.zc.lanzar(operacion, al_terminar=lambda _op: panel.refrescar())

	def descifrar(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		if ctx.argumento:
			try:
				entradas = [panel.proveedor.info(str(ctx.argumento))]
			except api.ErrorArchivos as error:
				self.zc.anunciar(error.mensaje, api.ESENCIAL)
				return
		else:
			entradas = [e for e in panel.elementos_trabajo() if not e.es_carpeta and e.nombre.casefold().endswith(".zcc")]
		if not entradas:
			self.zc.anunciar(_("No hay archivos cifrados (.zcc) que descifrar"), api.RESULTADO)
			return
		from . import operaciones

		contrasena = self._contrasena_recordada()
		if not contrasena:
			contrasena = self.zc.ui.pedir_texto(_("Contra&seña:"), _("Descifrar"), "", contrasena=True,
				ayuda=_("La contraseña con la que se cifró."))
			if not contrasena:
				return
		operacion = operaciones.OperacionDescifrar(panel.proveedor, entradas, contrasena, pedir=self._pedir_en_hilo)

		def al_terminar(op: Any) -> None:
			if op.contrasena_valida and self.zc.config.obtener("recordar_en_sesion", False):
				self._recordada = op.contrasena_valida
			panel.refrescar()

		self.zc.lanzar(operacion, al_terminar=al_terminar)

	def _pedir_en_hilo(self, titulo: str, texto: str) -> str | None:
		"""Desde el hilo de la operación se pregunta con el ``Decisor`` (nunca con ``zc.ui``)."""
		return self.zc.decisor.pedir_texto(titulo, texto, "", oculto=True) or None

	# ── Visor ───────────────────────────────────────────────────────────────

	def ver(self, proveedor: api.Proveedor, ruta: str, cancelacion: Any) -> api.Documento:
		"""Descifra en memoria (sin escribir nada en disco) y devuelve el texto como ``Documento`` [trabajo].

		Una contraseña cancelada o equivocada devuelve un documento con el aviso, no
		una excepción: cada excepción de un visor cuenta como fallo del complemento (3.8).
		"""
		import io

		from . import zcc

		nombre = ruta.replace("/", "\\").rsplit("\\", 1)[-1]
		try:
			with proveedor.abrir_lectura(ruta) as origen:
				cabecera = zcc.leer_cabecera(origen)
				nombre = cabecera.nombre
				if cabecera.tamano > MAX_VISOR:
					return _aviso(nombre, _("Es demasiado grande para verlo aquí; descífrelo para abrirlo."))
				contrasena = self._contrasena_recordada()
				if not contrasena:
					contrasena = self._pedir_en_hilo(_("Ver un archivo cifrado"), _("Contraseña de {n}:").format(n=nombre)) or ""
				if not contrasena:
					return _aviso(nombre, _("No se escribió la contraseña."))
				memoria = io.BytesIO()
				zcc.descifrar(origen, memoria, contrasena, cabecera=cabecera,
					comprobar=lambda: api.comprobar(cancelacion) if cancelacion is not None else None)
		except zcc.ErrorZcc as error:
			return _aviso(nombre, error.mensaje)
		if self.zc.config.obtener("recordar_en_sesion", False):
			self._recordada = contrasena
		datos = memoria.getvalue()
		if cabecera.carpeta:
			import zipfile

			with zipfile.ZipFile(io.BytesIO(datos)) as paquete:
				texto = "\n".join(paquete.namelist())
			return api.Documento(nombre, (api.Seccion(_("Contenido de la carpeta cifrada"), 1, texto),))
		texto = _texto(datos)
		if texto is None:
			return _aviso(nombre, _("No es un texto: descífrelo para abrirlo con su programa."))
		return api.Documento(nombre, (api.Seccion(nombre, 1, texto),))


def _aviso(nombre: str, texto: str) -> api.Documento:
	return api.Documento(nombre, (api.Seccion(nombre, 1, texto),), aviso=texto)

def _texto(datos: bytes) -> str | None:
	"""Texto si lo parece (UTF-8, UTF-16 con marca o ANSI sin caracteres de control raros); ``None`` si es binario."""
	if datos.startswith((b"\xff\xfe", b"\xfe\xff")):
		return datos.decode("utf-16", errors="replace")
	if b"\x00" in datos[:4096]:
		return None
	try:
		return datos.decode("utf-8-sig")
	except UnicodeDecodeError:
		texto = datos.decode("cp1252", errors="replace")
		raros = sum(1 for c in texto[:4096] if ord(c) < 32 and c not in "\r\n\t\f")
		return None if raros > 10 else texto
