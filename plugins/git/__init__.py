# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Git básico (``zc.git``, diseño 2.0, 11.21; bloque P4).

- Columna «Git» (modificado, nuevo, sin seguimiento, ignorado...).
- Al entrar en un repositorio: «Rama main, 3 cambios» (detalle) y el sonido
  ``zc.git:repositorio``, si ``anunciar_al_entrar`` está activa.
- Añadir, confirmar, diferencias, historial, traer, enviar, cambiar
  de rama, clonar y descartar cambios (con confirmación).
- Orden interna de la línea de órdenes: ``zc git <subórdenes>``.

Usa ``git.exe`` si está instalado (``ruta_git`` o el que se encuentre); sin
él, estado, historial y diferencias se leen en Python puro (``lector.py``) y
el resto dice «Hace falta Git instalado».
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.plugins import api

log = logging.getLogger(__name__)
_, _n = api.traduccion("zc_git")


class OperacionGit(api.Operacion):
	"""Traer, enviar o clonar: orden de Git larga y con red, como operación del motor (F12, cancelar)."""

	tipo = "git"
	admite_pausa = False

	def __init__(self, git: Any, carpeta: str, argumentos: list[str], descripcion: str, que: str) -> None:
		super().__init__()
		self.git = git
		self.carpeta = carpeta
		self.argumentos = argumentos
		self._descripcion = descripcion
		self.que = que
		self.salida = ""

	def descripcion(self) -> str:
		return self._descripcion

	def ejecutar(self, ctx: api.ContextoEjecucion) -> None:
		self.cambiar_estado(api.Estado.EJECUTANDO)
		self.progresar(actual=self._descripcion, archivos_total=1)
		try:
			resultado = self.git.ejecutar(self.carpeta, *self.argumentos, tiempo_s=6 * 3600, cancelacion=ctx.cancelado)
			self.salida = self.git.comprobar(resultado, self.que)
			self.sumar(archivos_hechos=1)
		except api.Cancelado:
			raise
		except api.ErrorArchivos as error:
			self.anotar_error(self.carpeta, error.mensaje)
		finally:
			self.git.olvidar(self.carpeta)


def _carpeta(panel: api.PanelComplemento) -> str | None:
	proveedor = panel.proveedor
	return proveedor.ruta_local(panel.ruta) if proveedor is not None else panel.ruta


def _rutas(panel: api.PanelComplemento) -> list[str]:
	proveedor = panel.proveedor
	rutas = []
	for entrada in panel.elementos_trabajo():
		ruta = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if ruta:
			rutas.append(ruta)
	return rutas


def nombre_de_clon(url: str) -> str:
	"""Carpeta que crea ``git clone``: el último tramo de la dirección sin «.git»."""
	ultimo = re.split(r"[/\\:]", url.rstrip("/\\"))[-1]
	return re.sub(r"\.git$", "", ultimo) or "repositorio"


class Complemento(api.Complemento):
	def activar(self, zc: api.Anfitrion) -> None:
		from . import motor

		self.zc = zc
		self.git = motor.Git(zc.ejecutar_programa, lambda: str(zc.config.obtener("ruta_git", "") or ""))
		self._carpetas: dict[str, str] = {}
		self._raices: dict[str, str | None] = {}
		self._lado_activo = "izquierdo"
		for orden in ("estado", "anadir", "confirmar", "diferencias", "historial", "traer", "enviar", "rama", "clonar",
				"descartar"):
			zc.ordenes.manejador(orden, getattr(self, orden))
		zc.ordenes.interna("git", self.interna)
		zc.columnas.extractor("estado", self.columna)
		zc.eventos.suscribir("al_cambiar_carpeta", self._al_cambiar_carpeta)
		zc.eventos.suscribir("al_activar_panel", self._al_activar_panel)

	def ventanas_para_revisar(self, padre: Any) -> list[Any]:
		try:
			self.zc.ui.crear_campo  # noqa: B018 - comprueba que hay interfaz (sin ella, NoAdmitido)
		except api.NoAdmitido:
			return []
		from . import lector, ventanas

		ejemplo = lector.Confirmacion("0" * 40, "Ana", 1700000000, "+0100", "Primera confirmación")
		return [ventanas.DialogoConfirmar(padre, self.zc, "main", ["modificado: a.txt"]),
			ventanas.DialogoHistorial(padre, self.zc, _("Historial de a.txt"), [ejemplo], lambda c: None)]

	# ── Utilidades ──────────────────────────────────────────────────────────

	def _en_hilo(self, trabajo, listo, nombre: str) -> None:
		def fallo(error: BaseException) -> None:
			if isinstance(error, api.Cancelado):
				return
			mensaje = error.mensaje if isinstance(error, api.ErrorArchivos) else str(error)
			self.zc.anunciar(mensaje, api.ESENCIAL)

		self.zc.tareas.enviar(lambda _t: trabajo(), al_terminar=listo, al_fallar=fallo, nombre=f"zc.git:{nombre}")

	def _exigir_git(self) -> bool:
		if self.git.exe:
			return True
		from . import motor

		self.zc.anunciar(_(motor.HACE_FALTA_GIT), api.ESENCIAL)
		return False

	def _repo(self, carpeta: str | None) -> str | None:
		if not carpeta:
			self.zc.anunciar(_("Git solo funciona con carpetas del disco"), api.RESULTADO)
			return None
		raiz = self.git.raiz(carpeta)
		if raiz is None:
			self.zc.anunciar(_("Esta carpeta no está en un repositorio Git"), api.RESULTADO)
		return raiz

	def _relativas(self, raiz: str, rutas: list[str]) -> list[str]:
		from . import motor

		return [motor.relativa_a(raiz, r) or "." for r in rutas]

	def _refrescar(self, ctx: api.ContextoComplemento) -> None:
		self.git.olvidar()
		ctx.objetivo.refrescar()

	# ── Órdenes ─────────────────────────────────────────────────────────────

	def estado(self, ctx: api.ContextoComplemento) -> None:
		carpeta = _carpeta(ctx.activo)
		if self._repo(carpeta) is None:
			return

		def listo(estado: Any) -> None:
			texto = estado.resumen()
			self.zc.anunciar(texto, api.RESULTADO, completo=texto)

		self._en_hilo(lambda: self.git.estado(carpeta), listo, "estado")

	def _sobre_elementos(self, ctx: api.ContextoComplemento, argumentos: list[str], que: str, hecho: str) -> None:
		rutas = _rutas(ctx.objetivo)
		raiz = self._repo(_carpeta(ctx.objetivo))
		if raiz is None or not self._exigir_git():
			return
		if not rutas:
			self.zc.anunciar(_("Elija archivos o carpetas"), api.RESULTADO)
			return
		relativas = self._relativas(raiz, rutas)

		def trabajo() -> int:
			self.git.comprobar(self.git.ejecutar(raiz, *argumentos, "--", *relativas), que)
			return len(relativas)

		def listo(cuantos: int) -> None:
			self._refrescar(ctx)
			self.zc.anunciar(hecho.format(n=cuantos), api.RESULTADO)

		self._en_hilo(trabajo, listo, argumentos[0])

	def anadir(self, ctx: api.ContextoComplemento) -> None:
		self._sobre_elementos(ctx, ["add"], _("añadir"), _("Preparados para confirmar: {n}"))

	def confirmar(self, ctx: api.ContextoComplemento) -> None:
		raiz = self._repo(_carpeta(ctx.activo))
		if raiz is None or not self._exigir_git():
			return

		def preparados() -> tuple[str, list[str], bool]:
			rama = self.git.ejecutar(raiz, "branch", "--show-current").salida.decode("utf-8", errors="replace").strip()
			lista = self.git.comprobar(self.git.ejecutar(raiz, "diff", "--cached", "--name-status"), _("leer lo preparado"))
			pendientes = self.git.comprobar(self.git.ejecutar(raiz, "diff", "--name-status"), _("leer los cambios"))
			return rama, [linea for linea in lista.splitlines() if linea.strip()], bool(pendientes.strip())

		self._en_hilo(preparados, lambda datos: self._dialogo_confirmar(ctx, raiz, *datos), "preparados")

	def _dialogo_confirmar(self, ctx: api.ContextoComplemento, raiz: str, rama: str, lista: list[str], hay_pendientes: bool) -> None:
		from . import ventanas

		todos = False
		if not lista:
			if not hay_pendientes:
				self.zc.anunciar(_("No hay cambios que confirmar"), api.RESULTADO)
				return
			if not self.zc.ui.confirmar(_("No hay nada preparado. ¿Confirmar todos los cambios de los archivos que ya tienen "
					"seguimiento?"), _("Confirmar")):
				return
			todos = True
			lista = [_("Todos los archivos con seguimiento que han cambiado")]
		dialogo = ventanas.DialogoConfirmar(None, self.zc, rama, lista)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != _id_ok():
				return
			mensaje = dialogo.mensaje.GetValue().strip()
		finally:
			dialogo.Destroy()

		def confirmar() -> str:
			argumentos = ["commit", "-F", "-"] + (["-a"] if todos else [])
			resultado = self.git.ejecutar(raiz, *argumentos, entrada=mensaje.encode("utf-8"))
			return self.git.comprobar(resultado, _("confirmar"))

		def listo(_salida: str) -> None:
			self._refrescar(ctx)
			self.zc.anunciar(_("Confirmado en la rama {r}").format(r=rama) if rama else _("Confirmado"), api.RESULTADO)

		self._en_hilo(confirmar, listo, "confirmar")

	def diferencias(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		entrada = panel.cursor()
		ruta = panel.proveedor.ruta_local(entrada.ruta) if entrada is not None and panel.proveedor is not None else None
		if entrada is None or entrada.es_carpeta or not ruta:
			self.zc.anunciar(_("Elija un archivo del disco"), api.RESULTADO)
			return
		if self._repo(os.path.dirname(ruta)) is None:
			return
		from . import motor

		def calcular() -> tuple[bytes | None, bytes]:
			with open(ruta, "rb") as archivo:
				return self.git.contenido_confirmado(ruta), archivo.read()

		def listo(contenidos: tuple[bytes | None, bytes]) -> None:
			antes, despues = contenidos
			if antes is None:
				self.zc.anunciar(_("{n} no está en la última confirmación: es nuevo").format(n=entrada.nombre), api.RESULTADO)
				return
			if antes == despues or antes == despues.replace(b"\r\n", b"\n"):
				self.zc.anunciar(_("{n} no tiene cambios").format(n=entrada.nombre), api.RESULTADO)
				return
			ventana = getattr(self.zc.ui, "mostrar_diferencias", None)
			if callable(ventana):
				nombre, punto, extension = entrada.nombre.rpartition(".")
				copia = self.zc.cache / (f"{nombre} (confirmado){punto}{extension}" if punto else f"{entrada.nombre} (confirmado)")
				copia.write_bytes(antes)
				ventana(str(copia), ruta)
				return
			self.zc.ui.mostrar_texto(_("Diferencias de {n}").format(n=entrada.nombre), motor.diferencias_texto(antes, despues, entrada.nombre))

		self._en_hilo(calcular, listo, "diferencias")

	def historial(self, ctx: api.ContextoComplemento) -> None:
		panel = ctx.objetivo
		entrada = panel.cursor()
		if entrada is not None and panel.proveedor is not None:
			ruta = panel.proveedor.ruta_local(entrada.ruta)
		else:
			ruta = _carpeta(panel)
		if self._repo(ruta if ruta and os.path.isdir(ruta) else (os.path.dirname(ruta) if ruta else None)) is None:
			return
		nombre = os.path.basename(ruta) or ruta

		def listo(confirmaciones: list) -> None:
			if not confirmaciones:
				self.zc.anunciar(_("{n} no tiene confirmaciones").format(n=nombre), api.RESULTADO)
				return
			from . import ventanas

			dialogo = ventanas.DialogoHistorial(None, self.zc, _("Historial de {n}").format(n=nombre), confirmaciones,
				lambda c: self._ver_confirmacion(ruta, c))
			try:
				self.zc.ui.mostrar_modal(dialogo)
			finally:
				dialogo.Destroy()

		self._en_hilo(lambda: self.git.historial(ruta), listo, "historial")

	def _ver_confirmacion(self, ruta: str, confirmacion: Any) -> None:
		from . import motor

		def leer() -> str:
			cabecera = _("Confirmación {s}\nAutor: {a}\n\n{m}").format(s=confirmacion.sha, a=confirmacion.autor,
				m=confirmacion.mensaje.strip())
			if not self.git.exe:
				return cabecera + "\n\n" + _("Sin Git instalado no se pueden mostrar los cambios de cada confirmación.")
			raiz = self.git.raiz(ruta if os.path.isdir(ruta) else os.path.dirname(ruta))
			relativa = motor.relativa_a(raiz, ruta)
			argumentos = ["show", "--format=", "--stat", "--patch", confirmacion.sha] + (["--", relativa] if relativa else [])
			return cabecera + "\n\n" + self.git.comprobar(self.git.ejecutar(raiz, *argumentos), _("mostrar la confirmación"))

		self._en_hilo(leer, lambda texto: self.zc.ui.mostrar_texto(confirmacion.resumen or confirmacion.sha[:10], texto), "ver")

	def _lanzar(self, ctx: api.ContextoComplemento, carpeta: str, argumentos: list[str], descripcion: str, que: str,
			al_terminar=None) -> None:
		operacion = OperacionGit(self.git, carpeta, argumentos, descripcion, que)

		def terminada(op: OperacionGit) -> None:
			self.git.olvidar()
			ctx.objetivo.refrescar()
			if not op.errores and op.salida:
				self.zc.anunciar(op.salida.strip().splitlines()[-1], api.DETALLE)
			if al_terminar is not None and not op.errores:
				al_terminar(op)

		self.zc.lanzar(operacion, al_terminar=terminada)

	def traer(self, ctx: api.ContextoComplemento) -> None:
		raiz = self._repo(_carpeta(ctx.activo))
		if raiz is None or not self._exigir_git():
			return
		self._lanzar(ctx, raiz, ["pull", "--no-edit"], _("Traer los cambios de {r}").format(r=os.path.basename(raiz)), _("traer"))

	def enviar(self, ctx: api.ContextoComplemento) -> None:
		raiz = self._repo(_carpeta(ctx.activo))
		if raiz is None or not self._exigir_git():
			return
		self._lanzar(ctx, raiz, ["push"], _("Enviar las confirmaciones de {r}").format(r=os.path.basename(raiz)), _("enviar"))

	def rama(self, ctx: api.ContextoComplemento) -> None:
		raiz = self._repo(_carpeta(ctx.activo))
		if raiz is None or not self._exigir_git():
			return

		def leer() -> tuple[str, list[str]]:
			actual = self.git.ejecutar(raiz, "branch", "--show-current").salida.decode("utf-8", errors="replace").strip()
			return actual, self.git.ramas(raiz)

		self._en_hilo(leer, lambda datos: self._elegir_rama(ctx, raiz, *datos), "ramas")

	def _elegir_rama(self, ctx: api.ContextoComplemento, raiz: str, actual: str, ramas: list[str]) -> None:
		otras = [r for r in ramas if r != actual]
		opciones = [*otras, _("Crear una rama nueva...")]
		indice = self.zc.ui.elegir_opcion(_("Rama actual: {r}. ¿A qué rama cambiar?").format(r=actual or _("ninguna")),
			_("Cambiar de rama"), opciones)
		if indice is None:
			return
		if indice < len(otras):
			argumentos = ["switch", otras[indice]]
			destino = otras[indice]
		else:
			nombre = self.zc.ui.pedir_texto(_("&Nombre de la rama nueva:"), _("Crear una rama"), "")
			if not nombre or not nombre.strip():
				return
			destino = nombre.strip()
			argumentos = ["switch", "-c", destino]

		def cambiar() -> str:
			return self.git.comprobar(self.git.ejecutar(raiz, *argumentos), _("cambiar de rama"))

		def listo(_salida: str) -> None:
			self._refrescar(ctx)
			self.zc.anunciar(_("Rama {r}").format(r=destino), api.RESULTADO)

		self._en_hilo(cambiar, listo, "cambiar_rama")

	def clonar(self, ctx: api.ContextoComplemento) -> None:
		carpeta = _carpeta(ctx.objetivo)
		if not carpeta:
			self.zc.anunciar(_("Git solo funciona con carpetas del disco"), api.RESULTADO)
			return
		if not self._exigir_git():
			return
		url = ctx.argumento if isinstance(ctx.argumento, str) and ctx.argumento else self.zc.ui.pedir_texto(
			_("&Dirección del repositorio:"), _("Clonar un repositorio"), "")
		if not url or not url.strip():
			return
		url = url.strip()
		nombre = nombre_de_clon(url)
		if os.path.exists(os.path.join(carpeta, nombre)):
			self.zc.anunciar(_("Ya existe {n} en esta carpeta").format(n=nombre), api.ESENCIAL)
			return
		destino = os.path.join(carpeta, nombre)
		self._lanzar(ctx, carpeta, ["clone", "--", url, nombre], _("Clonar {n}").format(n=nombre), _("clonar"),
			al_terminar=lambda _op: self.zc.abrir_ruta(destino))

	def descartar(self, ctx: api.ContextoComplemento) -> None:
		rutas = _rutas(ctx.objetivo)
		raiz = self._repo(_carpeta(ctx.objetivo))
		if raiz is None or not self._exigir_git():
			return
		if not rutas:
			self.zc.anunciar(_("Elija archivos o carpetas"), api.RESULTADO)
			return
		relativas = self._relativas(raiz, rutas)
		que = os.path.basename(rutas[0]) if len(rutas) == 1 else _n("{n} elemento", "{n} elementos", len(rutas)).format(n=len(rutas))
		if not self.zc.ui.confirmar(_("¿Descartar los cambios de {q}? Volverán a como estaban en la última confirmación y lo "
				"cambiado se perderá. Los archivos sin seguimiento no se tocan.").format(q=que), _("Descartar los cambios"), peligroso=True):
			return

		def descartar() -> str:
			resultado = self.git.ejecutar(raiz, "restore", "--source=HEAD", "--staged", "--worktree", "--", *relativas)
			return self.git.comprobar(resultado, _("descartar los cambios"))

		def listo(_salida: str) -> None:
			self._refrescar(ctx)
			self.zc.anunciar(_("Cambios descartados en {q}").format(q=que), api.RESULTADO)

		self._en_hilo(descartar, listo, "descartar")

	# ── Columna y anuncio al entrar ─────────────────────────────────────────

	def columna(self, entrada: api.Entrada, proveedor: api.Proveedor, cancelacion: Any) -> str | None:
		from . import motor

		if entrada.es_superior:
			return ""
		ruta = proveedor.ruta_local(entrada.ruta) if proveedor is not None else entrada.ruta
		if not ruta:
			return None
		estado = self.git.estado(os.path.dirname(ruta), maximo_s=float(self.zc.config.obtener("refresco_s", 5)))
		if estado is None:
			return ""
		return estado.de(motor.relativa_a(estado.raiz, ruta), entrada.es_carpeta)

	def _al_activar_panel(self, lado: str = "", **_datos: Any) -> None:
		if lado:
			self._lado_activo = lado

	def _al_cambiar_carpeta(self, panel: Any = None, proveedor: Any = None, ruta: str = "", **_datos: Any) -> None:
		lado = str(getattr(panel, "lado", "") or "izquierdo")
		local = proveedor.ruta_local(ruta) if proveedor is not None and ruta else None
		self._carpetas[lado] = local or ""
		if not local:
			self._raices[lado] = None
			return
		anunciar = bool(self.zc.config.obtener("anunciar_al_entrar", True))

		def comprobar() -> Any:
			raiz = self.git.raiz(local)
			anterior = self._raices.get(lado)
			self._raices[lado] = raiz
			if raiz is None or raiz == anterior or not anunciar:
				return None
			return self.git.estado(raiz)

		def listo(estado: Any) -> None:
			if estado is not None:
				self.zc.sonidos.sonar("repositorio")
				self.zc.anunciar(estado.resumen(), api.DETALLE)

		self.zc.tareas.enviar(lambda _t: comprobar(), al_terminar=listo, al_fallar=lambda e: log.debug("Sin estado de Git: %s", e),
			clave_unica=f"zc.git:entrar:{lado}", nombre="zc.git:entrar")

	# ── zc git ... ──────────────────────────────────────────────────────────

	def interna(self, argumentos: list[str], escribir: Any, cancelacion: Any) -> int:
		"""``zc git <subórdenes>`` en la carpeta del panel activo; la salida va a «Salida de órdenes» [trabajo]."""
		from . import motor

		carpeta = self._carpetas.get(self._lado_activo) or os.getcwd()
		if not argumentos:
			escribir(_("Uso: zc git <orden de git>, por ejemplo zc git status"))
			return 2
		if not self.git.exe:
			if argumentos[0] == "status":
				estado = self.git.estado(carpeta)
				if estado is None:
					escribir(_("Esta carpeta no está en un repositorio Git"))
					return 1
				escribir(estado.resumen())
				for ruta, codigo in sorted(estado.pendientes.items()):
					escribir(f"{_(codigo)}: {ruta}")
				return 0
			escribir(_(motor.HACE_FALTA_GIT))
			return 1
		resultado = self.git.ejecutar(carpeta, *argumentos, tiempo_s=3600, cancelacion=getattr(cancelacion, "token", cancelacion))
		for linea in (resultado.salida + resultado.errores).decode("utf-8", errors="replace").splitlines():
			escribir(linea)
		self.git.olvidar(carpeta)
		return 1 if resultado.cancelado else int(resultado.codigo)


def _id_ok() -> int:
	"""``wx.ID_OK`` leído al usarlo: activar() no importa wx."""
	import wx

	return wx.ID_OK
