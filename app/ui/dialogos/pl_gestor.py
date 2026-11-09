# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Gestor de complementos (diseño 2.0, 3.10, 3.11 y 15.1; orden ``complementos``). Bloque PL.

Por qué está hecho así:

- **Lista nativa** (``ListaAccesible``) con Nombre, Versión, Estado, Origen,
  Confianza y Autor. El estado es TEXTO («Activo», «Sin cargar todavía»,
  «Inhabilitado, se desinstalará al reiniciar»...), nunca un icono ni un color.
- **Detalles** en un campo de solo lectura (descripción, permisos, licencia,
  web, componentes, tiempo de carga y último error): el lector lo recorre.
- **Teclado**: Intro en la lista configura, Supr desinstala (con confirmación)
  y Espacio habilita o inhabilita. Cada botón tiene su letra, sin repetir
  (``revisar_teclado`` lo comprueba en la prueba del bloque).
- **Nada bloquea la interfaz**: analizar e instalar un paquete y buscar
  actualizaciones van en hilos; el registro de marcadores, en el hilo de la
  interfaz (3.10).
- Las acciones destructivas preguntan con la opción segura por defecto
  (desinstalar, instalar sin firma, aceptar un complemento sin firma).
- Las preguntas y avisos pasan por funciones de este módulo (``preguntar``,
  ``avisar``, ``elegir_archivo``...) que las pruebas sustituyen.
"""

from __future__ import annotations

import builtins
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from app.plugins import estado as estado_complementos
from app.plugins import gestor, paquetes, registro
from app.plugins.estado import EstadoComplemento
from app.ui import anuncios
from app.ui.accesibilidad import dialogos
from app.ui.accesibilidad.dialogos import preparar_dialogo
from app.ui.accesibilidad.lista import ListaAccesible
from app.ui.accesibilidad.nombres import crear_campo

log = logging.getLogger(__name__)


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


# ── Avisos y preguntas (sustituibles en las pruebas) ────────────────────────


def avisar(padre: wx.Window | None, texto: str, titulo: str = "") -> None:
	dialogos.mostrar_mensaje(padre, texto, titulo or _("Complementos"))


def preguntar(padre: wx.Window | None, texto: str, titulo: str = "", peligroso: bool = False) -> bool:
	with estado_complementos.pausa_modal():
		return dialogos.confirmar(padre, texto, titulo or _("Complementos"), peligroso=peligroso) == wx.ID_YES


def elegir(padre: wx.Window | None, texto: str, titulo: str, opciones: list[str]) -> int | None:
	with estado_complementos.pausa_modal():
		return dialogos.elegir_opcion(padre, texto, titulo, opciones)


def mostrar_texto(padre: wx.Window | None, titulo: str, texto: str) -> None:
	from app.ui import dialogo_texto

	with estado_complementos.pausa_modal():
		dialogo_texto.mostrar_texto(padre, titulo, _("&Texto:"), texto, copiable=True)


def elegir_archivo(padre: wx.Window | None) -> Path | None:
	"""Un ``.zcplugin`` elegido en el diálogo nativo de abrir, o ``None``."""
	dialogo = wx.FileDialog(padre, _("Instalar un complemento"), wildcard=_("Complementos de zCommander (*.zcplugin)|*.zcplugin"),
		style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
	try:
		with estado_complementos.pausa_modal():
			return Path(dialogo.GetPath()) if dialogo.ShowModal() == wx.ID_OK else None
	finally:
		dialogo.Destroy()


def abrir_carpeta(carpeta: Path) -> None:
	os.startfile(str(carpeta))  # noqa: S606 - abre el Explorador en la carpeta del complemento, a petición de la persona


def mostrar_documento(padre: wx.Window | None, titulo: str, ruta: Path) -> None:
	from app.ui import visor_ayuda

	visor_ayuda.mostrar_documento(padre, titulo, ruta.read_text(encoding="utf-8"))


def en_hilo(trabajo: Callable[[], Any], listo: Callable[[Any], None], fallo: Callable[[BaseException], None]) -> None:
	"""Ejecuta ``trabajo`` en un hilo y entrega el resultado (o el error) en el hilo de la interfaz."""

	def correr() -> None:
		try:
			resultado = trabajo()
		except BaseException as error:  # noqa: BLE001 - se entrega a quien lo pidió
			log.info("Fallo en un trabajo del gestor de complementos", exc_info=True)
			wx.CallAfter(fallo, error)
			return
		wx.CallAfter(listo, resultado)

	threading.Thread(target=correr, name="zc-gestor", daemon=True).start()


def _mensaje(error: BaseException) -> str:
	return getattr(error, "mensaje", None) or str(error) or error.__class__.__name__


def _sonar(evento: str) -> None:
	try:
		from app.services.sonidos import servicio

		servicio.sonar(evento)
	except Exception:  # noqa: BLE001 - un sonido nunca rompe el gestor
		log.debug("No se pudo pedir el sonido %s", evento, exc_info=True)


# ── Instalar ─────────────────────────────────────────────────────────────────


def registrar_instalado(carpeta: Path) -> registro.Registrado | None:
	"""Registra sin reiniciar un complemento recién instalado (en el hilo de la interfaz, 3.10)."""
	from app.plugins import cargador, manifiesto

	actual = cargador.actual()
	if actual is not None:
		return actual.registrar_carpeta(carpeta)
	try:
		datos = manifiesto.leer(carpeta)
	except manifiesto.ErrorManifiesto:
		log.warning("El complemento instalado en %s no tiene un manifiesto válido", carpeta, exc_info=True)
		return None
	return registro.registrar(datos, carpeta, "usuario")


def instalar_desde_archivo(padre: wx.Window | None, config: Any, ruta: Path, al_terminar: Callable[[bool], None] | None = None,
		al_reiniciar: Callable[[], None] | None = None) -> None:
	"""Instala un ``.zcplugin``: analizar (hilo), resumen, mover (hilo), ``al_instalar`` (hilo) y registrar (interfaz)."""
	terminar = al_terminar or (lambda _ok: None)
	anuncios.anunciar(_("Comprobando el paquete..."), anuncios.DETALLE)

	def fallo(error: BaseException) -> None:
		avisar(padre, _("No se pudo instalar el complemento: {e}").format(e=_mensaje(error)), _("Instalar un complemento"))
		terminar(False)

	def analizado(resumen: paquetes.Resumen) -> None:
		from app.ui.dialogos import pl_instalar

		if not pl_instalar.confirmar_instalacion(padre, resumen):
			paquetes.descartar(resumen)
			anuncios.anunciar(_("No se instaló nada"), anuncios.RESULTADO)
			terminar(False)
			return
		en_hilo(lambda: paquetes.instalar(resumen, config), lambda instalado: movido(resumen, instalado), fallo)

	def movido(resumen: paquetes.Resumen, instalado: paquetes.Instalado) -> None:
		datos = resumen.manifiesto
		if not instalado.directo:
			_sonar("plugin.instalado")
			texto = _("{n} {v} se instalará al reiniciar zCommander.").format(n=datos.nombre, v=datos.version)
			eleccion = elegir(padre, texto, _("Instalar un complemento"), [_("&Reiniciar ahora"), _("Más &tarde")])
			terminar(True)
			if eleccion == 0 and al_reiniciar is not None:
				al_reiniciar()
			return
		futuro = paquetes.ejecutar_gancho(instalado.carpeta, "al_instalar", datos.id, datos.permisos)

		def preparado(_f: Any) -> None:
			if not futuro.result():
				paquetes.deshacer_instalacion(instalado, config)
				avisar(padre, _("No se pudo instalar {n}: falló su preparación (al_instalar). Detalles en el registro.").format(
					n=datos.nombre), _("Instalar un complemento"))
				terminar(False)
				return
			registrar_instalado(instalado.carpeta)
			_sonar("plugin.instalado")
			anuncios.anunciar(_("{n} {v} instalado; ya puede usarlo.").format(n=datos.nombre, v=datos.version), anuncios.RESULTADO)
			terminar(True)

		futuro.add_done_callback(lambda f: wx.CallAfter(preparado, f))

	en_hilo(lambda: paquetes.preparar(Path(ruta), config), analizado, fallo)


# ── Diálogo ──────────────────────────────────────────────────────────────────


COLUMNAS = (("Nombre", 220), ("Versión", 70), ("Estado", 220), ("Origen", 110), ("Confianza", 200), ("Autor", 160))


class DialogoGestor(wx.Dialog):
	"""Gestor de complementos.

	:param config: la ``Configuracion`` de zCommander (``complementos.*``).
	:param al_reiniciar: cómo se reinicia zCommander («Reiniciar ahora»).
	:param ocupadas: tecla → orden de todo el catálogo (para decir qué teclas perdió un complemento de terceros).
	"""

	def __init__(self, padre: wx.Window | None, config: Any, al_reiniciar: Callable[[], None] | None = None,
			ocupadas: dict[str, str] | None = None, leer_preferencias: Callable | None = None) -> None:
		titulo = _("Gestor de complementos")
		super().__init__(padre, title=titulo, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, name=titulo)
		if wx.HelpProvider.Get() is None:
			wx.HelpProvider.Set(wx.SimpleHelpProvider())
		self.config = config
		self.al_reiniciar = al_reiniciar
		self.ocupadas = ocupadas or {}
		self.filas: list[gestor.Fila] = []
		panel = wx.Panel(self)
		self.panel = panel
		sizer = wx.BoxSizer(wx.VERTICAL)
		opciones = {"leer_preferencias": leer_preferencias} if leer_preferencias else {}
		_e, self.lista = crear_campo(panel, _("Co&mplementos instalados:"), lambda p, **k: ListaAccesible(
			p, _("Complementos instalados"), columnas=[(_(t), panel.FromDIP(a)) for t, a in COLUMNAS],
			accion_espacio=lambda _fila: self.alternar_habilitado(), **opciones), sizer=sizer,
			ayuda=_("Complementos instalados. Intro los configura, Supr los desinstala y Espacio los habilita o inhabilita."))
		self.lista.SetMinSize(panel.FromDIP(wx.Size(820, 220)))
		_e, self.detalles = crear_campo(panel, _("&Detalles:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
			size=panel.FromDIP(wx.Size(-1, 150)), sizer=sizer,
			ayuda=_("Descripción, permisos, licencia y estado del complemento elegido."))
		rejilla = wx.WrapSizer(wx.HORIZONTAL)
		b = self._boton
		self.boton_habilitar = b(rejilla, _("In&habilitar"), _("Habilita o inhabilita el complemento (también con Espacio en la lista)."),
			self.alternar_habilitado)
		self.boton_aceptar = b(rejilla, _("&Aceptar"), _("Acepta un complemento sin firma que no se instaló desde zCommander."),
			self.aceptar)
		self.boton_reintentar = b(rejilla, _("Volver a intentar&lo"), _("Vuelve a usar un complemento que quedó fuera de uso por errores."),
			self.reintentar)
		self.boton_confiar = b(rejilla, _("Confiar en este a&utor"),
			_("Añade la clave de su autor a las de confianza: sus otros complementos firmados se instalarán como de confianza."),
			self.confiar)
		self.boton_configurar = b(rejilla, _("Con&figurar"), _("Opciones del complemento (también con Intro en la lista)."),
			self.configurar)
		self.boton_ayuda = b(rejilla, _("A&yuda"), _("Abre la ayuda del complemento."), lambda: self.documento("ayuda"))
		self.boton_novedades = b(rejilla, _("&Novedades"), _("Abre las novedades del complemento."), lambda: self.documento("cambios"))
		self.boton_instalar = b(rejilla, _("&Instalar desde un archivo..."), _("Instala un complemento .zcplugin tras ver su resumen."),
			self.instalar)
		self.boton_buscar = b(rejilla, _("&Buscar actualizaciones"),
			_("Pregunta a cada complemento que lo admite si hay una versión nueva; nunca instala sin preguntar."),
			self.buscar_actualizaciones)
		self.boton_anterior = b(rejilla, _("Volver a la versión an&terior"),
			_("Vuelve, al reiniciar, a la versión que había antes de la última actualización."), self.volver_atras)
		self.boton_desinstalar = b(rejilla, _("D&esinstalar"), _("Desinstala el complemento al reiniciar (también con Supr)."),
			self.desinstalar)
		self.boton_carpeta = b(rejilla, _("Abrir su ca&rpeta"), _("Abre la carpeta del complemento en el Explorador."),
			self.abrir_carpeta)
		self.boton_registro = b(rejilla, _("Ver su re&gistro"), _("Líneas del registro de esta sesión sobre el complemento."),
			self.ver_registro)
		self.boton_permisos = b(rejilla, _("Ver los &permisos"), _("Qué permisos declara el complemento, en lenguaje claro."),
			self.ver_permisos)
		self.boton_reiniciar = b(rejilla, _("Reiniciar ah&ora"), _("Reinicia zCommander para aplicar los cambios pendientes."),
			self.reiniciar)
		self.boton_cerrar = wx.Button(panel, wx.ID_CANCEL, _("&Cerrar"))
		self.boton_cerrar.SetHelpText(_("Cierra el gestor (también con Escape)."))
		rejilla.Add(self.boton_cerrar, 0, wx.ALL, panel.FromDIP(3))
		sizer.Add(rejilla, 0, wx.EXPAND | wx.ALL, 4)
		panel.SetSizer(sizer)
		marco = wx.BoxSizer(wx.VERTICAL)
		marco.Add(panel, 1, wx.EXPAND)
		self.SetSizerAndFit(marco)
		self.lista.Bind(wx.EVT_LIST_ITEM_FOCUSED, lambda _e: self.actualizar_detalles())
		self.lista.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda _e: self.actualizar_detalles())
		self.lista.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.configurar())
		self.lista.Bind(wx.EVT_LIST_KEY_DOWN, self._al_tecla_lista)
		self.refrescar()
		preparar_dialogo(self, foco_inicial=self.lista)
		self.CentreOnParent()

	def _boton(self, sizer: wx.Sizer, etiqueta: str, ayuda: str, accion: Callable[[], Any]) -> wx.Button:
		boton = wx.Button(self.panel, label=etiqueta)
		boton.SetHelpText(ayuda)
		boton.Bind(wx.EVT_BUTTON, lambda _e: accion())
		sizer.Add(boton, 0, wx.ALL, self.panel.FromDIP(3))
		return boton

	def _al_tecla_lista(self, evento: wx.ListEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE:
			self.desinstalar()
			return
		evento.Skip()

	# ── Lista y detalles ─────────────────────────────────────────────────────

	def fila(self) -> gestor.Fila | None:
		indice = self.lista.fila_actual()
		return self.filas[indice] if 0 <= indice < len(self.filas) else None

	def refrescar(self) -> None:
		"""Rehace la lista conservando el complemento en el que está la persona."""
		elegido = self.fila()
		self.filas = gestor.filas()
		self.lista.reemplazar_filas([f.valores() for f in self.filas])
		if self.filas:
			destino = next((i for i, f in enumerate(self.filas) if elegido and f.id == elegido.id and f.carpeta == elegido.carpeta), 0)
			self.lista.enfocar_fila(destino, anunciar=False)
		self.actualizar_detalles()

	def actualizar_detalles(self) -> None:
		fila = self.fila()
		registrado = registro.complemento(fila.id) if fila and fila.id else None
		self.detalles.ChangeValue(gestor.detalles(fila.id, fila.carpeta, self.ocupadas) if fila else _("No hay complementos instalados."))
		inhabilitado = registrado is not None and registrado.estado == EstadoComplemento.INHABILITADO
		self.boton_habilitar.SetLabel(_("&Habilitar") if inhabilitado else _("In&habilitar"))
		utilizable = registrado is not None and registrado.estado not in (EstadoComplemento.ERROR_MANIFIESTO,)
		self.boton_habilitar.Enable(utilizable)
		self.boton_aceptar.Show(registrado is not None and registrado.estado == EstadoComplemento.SIN_ACEPTAR)
		self.boton_reintentar.Show(bool(fila and fila.id and gestor.puede_reintentar(fila.id)))
		self.boton_confiar.Show(bool(fila and fila.id and gestor.puede_confiar_en_autor(fila.id)))
		self.boton_configurar.Enable(utilizable)
		self.boton_ayuda.Enable(bool(fila and fila.id and gestor.ruta_documento(fila.id, "ayuda")))
		self.boton_novedades.Enable(bool(fila and fila.id and gestor.ruta_documento(fila.id, "cambios")))
		self.boton_anterior.Enable(bool(fila and fila.id and paquetes.anteriores(fila.id)))
		self.boton_desinstalar.Enable(bool(fila and fila.id and gestor.puede_desinstalar(fila.id)))
		self.boton_carpeta.Enable(fila is not None)
		self.boton_registro.Enable(registrado is not None)
		self.boton_permisos.Enable(registrado is not None)
		self.boton_reiniciar.Show(gestor.hay_pendientes())
		self.panel.Layout()

	def _registrado(self) -> registro.Registrado | None:
		fila = self.fila()
		return registro.complemento(fila.id) if fila and fila.id else None

	# ── Acciones ─────────────────────────────────────────────────────────────

	def alternar_habilitado(self) -> None:
		registrado = self._registrado()
		if registrado is None or registrado.estado == EstadoComplemento.ERROR_MANIFIESTO:
			anuncios.anunciar(_("Este complemento no se puede habilitar"), anuncios.RESULTADO)
			return
		if registrado.estado == EstadoComplemento.INHABILITADO:
			gestor.habilitar(self.config, registrado.id)
			anuncios.anunciar(_("{n} habilitado").format(n=registrado.nombre), anuncios.RESULTADO)
		else:
			activo = registrado.estado == EstadoComplemento.ACTIVO
			gestor.inhabilitar(self.config, registrado.id)
			_sonar("plugin.inhabilitado")
			texto = _("{n} inhabilitado").format(n=registrado.nombre)
			if activo:
				texto += ". " + _("Su código sigue cargado hasta que reinicie zCommander.")
			anuncios.anunciar(texto, anuncios.RESULTADO)
		self.refrescar()

	def aceptar(self) -> None:
		registrado = self._registrado()
		if registrado is None or registrado.estado != EstadoComplemento.SIN_ACEPTAR:
			return
		texto = _("{n}, de {a}, no está firmado y no se instaló desde zCommander. Ejecutará código con sus mismos permisos "
			"de Windows. ¿Aceptarlo?").format(n=registrado.nombre, a=registrado.manifiesto.autor)
		if preguntar(self, texto, _("Complemento sin firma"), peligroso=True):
			gestor.aceptar(self.config, registrado.id)
			anuncios.anunciar(_("{n} aceptado").format(n=registrado.nombre), anuncios.RESULTADO)
			self.refrescar()

	def reintentar(self) -> None:
		registrado = self._registrado()
		if registrado is not None and gestor.reintentar(registrado.id):
			anuncios.anunciar(_("{n} se volverá a cargar la próxima vez que se use").format(n=registrado.nombre), anuncios.RESULTADO)
			self.refrescar()

	def confiar(self) -> None:
		registrado = self._registrado()
		if registrado is None:
			return
		texto = _("Los complementos firmados por el autor de {n} ({a}) se instalarán como de confianza. ¿Confiar en este autor?").format(
			n=registrado.nombre, a=registrado.manifiesto.autor)
		if preguntar(self, texto, _("Confiar en este autor"), peligroso=True) and gestor.confiar_en_autor(registrado.id):
			anuncios.anunciar(_("Autor añadido a los de confianza"), anuncios.RESULTADO)
			self.refrescar()

	def configurar(self) -> None:
		registrado = self._registrado()
		if registrado is None:
			return
		from app.ui.dialogos import pl_preferencias

		if not pl_preferencias.abrir_dialogo(self, registrado.id):
			anuncios.anunciar(_("{n} no tiene opciones que configurar").format(n=registrado.nombre), anuncios.RESULTADO)

	def documento(self, cual: str) -> None:
		fila = self.fila()
		ruta = gestor.ruta_documento(fila.id, cual) if fila and fila.id else None
		if ruta is None:
			anuncios.anunciar(_("Este complemento no tiene ayuda") if cual == "ayuda" else _("Este complemento no tiene novedades"),
				anuncios.RESULTADO)
			return
		titulo = fila.nombre if cual == "ayuda" else _("Novedades de {n}").format(n=fila.nombre)
		mostrar_documento(self, titulo, ruta)

	def instalar(self, ruta: Path | None = None) -> None:
		ruta = ruta or elegir_archivo(self)
		if ruta is None:
			return
		instalar_desde_archivo(self, self.config, ruta, al_terminar=lambda _ok: self and self.refrescar(), al_reiniciar=self.reiniciar)

	def buscar_actualizaciones(self) -> None:
		anuncios.anunciar(_("Buscando actualizaciones de complementos..."), anuncios.RESULTADO)

		def listo(encontradas: list[paquetes.Actualizacion]) -> None:
			if not self:
				return
			if not encontradas:
				avisar(self, _("Todos los complementos están al día."), _("Buscar actualizaciones"))
				return
			for actualizacion in encontradas:
				texto = _("Hay una versión nueva de {n}: {v}.").format(n=actualizacion.nombre, v=actualizacion.version)
				if actualizacion.novedades:
					texto += "\n\n" + _("Novedades: {t}").format(t=actualizacion.novedades)
				if preguntar(self, texto + "\n\n" + _("¿Descargarla y ver su resumen para instalarla?"), _("Buscar actualizaciones")):
					self.descargar(actualizacion)

		en_hilo(paquetes.buscar_actualizaciones, listo,
			lambda error: avisar(self, _("No se pudieron buscar actualizaciones: {e}").format(e=_mensaje(error))))

	def descargar(self, actualizacion: paquetes.Actualizacion) -> None:
		anuncios.anunciar(_("Descargando {n}...").format(n=actualizacion.nombre), anuncios.RESULTADO)
		en_hilo(lambda: paquetes.descargar_actualizacion(actualizacion), lambda ruta: self.instalar(Path(ruta)),
			lambda error: avisar(self, _("No se pudo descargar {n}: {e}").format(n=actualizacion.nombre, e=_mensaje(error))))

	def volver_atras(self) -> None:
		registrado = self._registrado()
		if registrado is None:
			return
		disponibles = paquetes.anteriores(registrado.id)
		if not disponibles:
			anuncios.anunciar(_("No hay ninguna versión anterior guardada"), anuncios.RESULTADO)
			return
		texto = _("¿Volver a la versión {v} de {n} al reiniciar zCommander?").format(v=disponibles[0][0], n=registrado.nombre)
		if preguntar(self, texto, _("Volver a la versión anterior"), peligroso=True):
			version = gestor.volver_atras(registrado.id)
			anuncios.anunciar(_("{n} volverá a la versión {v} al reiniciar").format(n=registrado.nombre, v=version), anuncios.RESULTADO)
			self.refrescar()

	def desinstalar(self) -> None:
		fila = self.fila()
		if fila is None or not fila.id:
			return
		if not gestor.puede_desinstalar(fila.id):
			anuncios.anunciar(_("Los complementos de serie no se desinstalan: se pueden inhabilitar"), anuncios.RESULTADO)
			return
		if not preguntar(self, _("¿Desinstalar {n}? Se borrará al reiniciar zCommander.").format(n=fila.nombre), _("Desinstalar"),
				peligroso=True):
			return
		borrar = preguntar(self, _("¿Borrar también su configuración y sus datos?"), _("Desinstalar"), peligroso=True)
		gestor.desinstalar(fila.id, borrar)
		anuncios.anunciar(_("{n} se desinstalará al reiniciar").format(n=fila.nombre), anuncios.RESULTADO)
		self.refrescar()

	def abrir_carpeta(self) -> None:
		fila = self.fila()
		if fila is not None:
			try:
				abrir_carpeta(fila.carpeta)
			except OSError as error:
				avisar(self, _("No se pudo abrir la carpeta: {e}").format(e=error))

	def ver_registro(self) -> None:
		registrado = self._registrado()
		if registrado is None:
			return
		lineas = gestor.lineas_registro(registrado.id)
		texto = "\n".join(lineas) if lineas else _("No hay nada de este complemento en el registro de esta sesión.")
		mostrar_texto(self, _("Registro de {n}").format(n=registrado.nombre), texto)

	def ver_permisos(self) -> None:
		registrado = self._registrado()
		if registrado is None:
			return
		permisos = [paquetes.texto_permiso(p) for p in registrado.manifiesto.permisos]
		texto = "\n".join(permisos) if permisos else _("Este complemento no declara ningún permiso.")
		texto += "\n\n" + _("Los permisos no son una barrera técnica: un complemento se ejecuta con sus mismos permisos de Windows. "
			"zCommander solo le da la red, los secretos, los programas y las teclas globales si los declara.")
		mostrar_texto(self, _("Permisos de {n}").format(n=registrado.nombre), texto)

	def reiniciar(self) -> None:
		if self.al_reiniciar is None:
			anuncios.anunciar(_("Reinicie zCommander para aplicar los cambios"), anuncios.RESULTADO)
			return
		if self.IsModal():
			self.EndModal(wx.ID_CANCEL)
		wx.CallAfter(self.al_reiniciar)


def mostrar(padre: wx.Window | None, config: Any, al_reiniciar: Callable[[], None] | None = None,
		ocupadas: dict[str, str] | None = None, leer_preferencias: Callable | None = None) -> None:
	"""Abre el gestor de forma modal y devuelve el foco a donde estaba."""
	from app.ui.dialogos import f_comun

	dialogo = DialogoGestor(padre, config, al_reiniciar, ocupadas, leer_preferencias)
	with estado_complementos.pausa_modal():
		f_comun.mostrar(dialogo)
