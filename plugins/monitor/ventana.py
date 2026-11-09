# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogos del monitor de carpetas (diseño 2.0, 11.18). Con wx: se importa al abrirlos.

- «Monitor de carpetas»: carpetas vigiladas y reglas en orden (la primera
  regla activa que coincide es la que se aplica), con Simular sobre lo que ya
  hay. Los cambios se guardan al pulsar Aceptar.
- «Regla del monitor»: condiciones y acción; solo se habilitan los campos que
  usa la acción elegida.
- «Registro del monitor»: lo hecho, con deshacer la última acción.
"""

from __future__ import annotations

import os
import time

import wx

from app.plugins import api

from . import reglas


def _boton(padre: wx.Window, etiqueta: str, ayuda: str, sizer: wx.Sizer, al_pulsar=None, id_boton: int = wx.ID_ANY) -> wx.Button:
	boton = wx.Button(padre, id_boton, etiqueta)
	boton.SetHelpText(ayuda)
	if al_pulsar is not None:
		boton.Bind(wx.EVT_BUTTON, lambda _e: al_pulsar())
	sizer.Add(boton, 0, wx.ALL, 4)
	return boton


class DialogoRegla(wx.Dialog):
	"""Crea o cambia una regla. ``regla()`` devuelve la regla con lo escrito."""

	_ACCIONES = list(reglas.ACCIONES)
	_CAMPOS = {
		reglas.MOVER: ("destino",), reglas.COPIAR: ("destino",), reglas.EXTRAER: ("destino",),
		reglas.RENOMBRAR: ("mascara",), reglas.ETIQUETAR: ("etiqueta",), reglas.ORDEN: ("orden",),
	}

	def __init__(self, zc: api.Anfitrion, padre: wx.Window | None, regla: reglas.Regla, carpetas: list[str]) -> None:
		super().__init__(padre, title="Regla del monitor", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.zc = zc
		self._carpetas = list(carpetas)
		ui = zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.nombre = ui.crear_campo(self, "&Nombre:", wx.TextCtrl, sizer=cuerpo, value=regla.nombre,
			ayuda="Nombre de la regla; se dice al aplicarla y queda en el registro.")
		_, self.patron = ui.crear_campo(self, "&Patrón de nombre (por ejemplo *.pdf;*.docx):", wx.TextCtrl, sizer=cuerpo,
			value=regla.patron, ayuda="Archivos a los que se aplica la regla. Varios patrones, separados por punto y coma.")
		opciones = ["Cualquier carpeta vigilada", *self._carpetas]
		_, self.carpeta = ui.crear_campo(self, "Carpeta &vigilada:", wx.Choice, sizer=cuerpo, choices=opciones,
			ayuda="La regla solo se aplica a lo que llega a esta carpeta, o a cualquiera.")
		indice = next((i + 1 for i, c in enumerate(self._carpetas) if os.path.normcase(c) == os.path.normcase(regla.carpeta)), 0)
		self.carpeta.SetSelection(indice)
		_, self.minimo = ui.crear_campo(self, "Tamaño &mínimo en KB, 0 sin límite:", wx.SpinCtrl, sizer=cuerpo, min=0,
			max=100_000_000, initial=regla.tamano_min_kb, ayuda="Solo archivos de al menos este tamaño, en kilobytes.")
		_, self.maximo = ui.crear_campo(self, "Tamaño má&ximo en KB, 0 sin límite:", wx.SpinCtrl, sizer=cuerpo, min=0,
			max=100_000_000, initial=regla.tamano_max_kb, ayuda="Solo archivos de como mucho este tamaño, en kilobytes.")
		_, self.antiguedad = ui.crear_campo(self, "Antigüedad mínima en &días, 0 cualquiera:", wx.SpinCtrl, sizer=cuerpo, min=0,
			max=36500, initial=regla.antiguedad_dias,
			ayuda="Solo archivos modificados hace al menos estos días; sirve sobre todo al simular o desde el programador.")
		_, self.accion = ui.crear_campo(self, "&Qué hacer:", wx.Choice, sizer=cuerpo,
			choices=[reglas.ACCIONES[a] for a in self._ACCIONES], ayuda="La acción de la regla.")
		self.accion.SetSelection(self._ACCIONES.index(regla.accion))
		_, self.destino = ui.crear_campo(self, "Carpeta de des&tino:", wx.TextCtrl, sizer=cuerpo, value=regla.destino,
			ayuda="Adónde se mueve o se copia el archivo, o dónde se extrae (vacío al extraer: junto al comprimido).")
		_, self.mascara = ui.crear_campo(self, "Má&scara del nombre nuevo:", wx.TextCtrl, sizer=cuerpo, value=regla.mascara,
			ayuda="Como en el renombrado múltiple: [N] nombre, [E] extensión, [Y]-[M]-[D] fecha... y las de los complementos.")
		_, self.etiqueta = ui.crear_campo(self, "&Etiqueta:", wx.TextCtrl, sizer=cuerpo, value=regla.etiqueta,
			ayuda="Etiqueta que se pone con el complemento Notas, comentarios y etiquetas.")
		_, self.orden = ui.crear_campo(self, "&Orden o macro:", wx.TextCtrl, sizer=cuerpo, value=regla.orden,
			ayuda="Id de la orden (zc.reproductor:reproducir) o macro:<nombre>; recibe el archivo como argumento.")
		self.activa = wx.CheckBox(self, label="Regla act&iva")
		self.activa.SetValue(regla.activa)
		self.activa.SetHelpText("Una regla desactivada se conserva pero no se aplica.")
		cuerpo.Add(self.activa, 0, wx.ALL, 5)
		cuerpo.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizerAndFit(cuerpo)
		self.accion.Bind(wx.EVT_CHOICE, lambda _e: self._habilitar())
		self.Bind(wx.EVT_BUTTON, self._al_aceptar, id=wx.ID_OK)
		self._habilitar()
		ui.preparar_dialogo(self, foco_inicial=self.nombre)

	def _habilitar(self) -> None:
		usados = self._CAMPOS[self._ACCIONES[max(0, self.accion.GetSelection())]]
		for campo in ("destino", "mascara", "etiqueta", "orden"):
			getattr(self, campo).Enable(campo in usados)

	def regla(self) -> reglas.Regla:
		indice = self.carpeta.GetSelection()
		return reglas.Regla(nombre=self.nombre.GetValue().strip(), patron=self.patron.GetValue().strip() or "*",
			carpeta=self._carpetas[indice - 1] if indice > 0 else "", tamano_min_kb=self.minimo.GetValue(),
			tamano_max_kb=self.maximo.GetValue(), antiguedad_dias=self.antiguedad.GetValue(),
			accion=self._ACCIONES[max(0, self.accion.GetSelection())], destino=self.destino.GetValue().strip(),
			mascara=self.mascara.GetValue().strip(), etiqueta=self.etiqueta.GetValue().strip(),
			orden=self.orden.GetValue().strip(), activa=self.activa.GetValue())

	def _al_aceptar(self, evento: wx.CommandEvent) -> None:
		problema = self.regla().error()
		if problema:
			self.zc.ui.mostrar_error(problema, "Regla del monitor", self)
			return
		evento.Skip()


class DialogoMonitor(wx.Dialog):
	"""Carpetas vigiladas y reglas. ``valores()`` da (carpetas, reglas) al aceptar."""

	def __init__(self, complemento, padre: wx.Window | None, propuesta: str = "") -> None:
		super().__init__(padre, title="Monitor de carpetas", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(760, 560))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		self.propuesta = propuesta
		self.carpetas: list[str] = complemento.carpetas()
		self.lista_reglas: list[reglas.Regla] = complemento.reglas()
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		_, self.lista_carpetas = ui.crear_campo(self, "Carpetas vi&giladas:", wx.ListBox, sizer=cuerpo, choices=self.carpetas,
			size=(-1, 90), ayuda="Carpetas en las que se avisa de lo que llega y se aplican las reglas.")
		fila = wx.BoxSizer(wx.HORIZONTAL)
		_boton(self, "Aña&dir carpeta...", "Elige una carpeta para vigilarla.", fila, self.anadir_carpeta)
		self.boton_quitar = _boton(self, "&Quitar carpeta", "Deja de vigilar la carpeta elegida.", fila, self.quitar_carpeta)
		cuerpo.Add(fila, 0)
		etiqueta = wx.StaticText(self, label="&Reglas, en orden (se aplica la primera que coincide):")
		self.tabla = ui.ListaAccesible(self, "Reglas, en orden", [("Nombre", 140), ("Si", 230), ("Entonces", 250), ("Activa", 70)])
		self.tabla.SetHelpText("Reglas del monitor. Intro edita la regla; Supr la borra.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.tabla, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.WrapSizer(wx.HORIZONTAL)
		_boton(self, "&Nueva regla...", "Crea una regla al final de la lista.", botones, self.nueva)
		self.boton_editar = _boton(self, "&Editar regla...", "Cambia la regla elegida.", botones, self.editar)
		self.boton_borrar = _boton(self, "&Borrar regla", "Quita la regla elegida.", botones, self.borrar)
		self.boton_subir = _boton(self, "S&ubir", "Sube la regla: se mira antes que las de debajo.", botones, lambda: self.mover(-1))
		self.boton_bajar = _boton(self, "Ba&jar", "Baja la regla.", botones, lambda: self.mover(1))
		self.boton_activar = _boton(self, "Act&ivar o desactivar", "Activa o desactiva la regla elegida sin borrarla.", botones,
			self.alternar)
		self.boton_simular = _boton(self, "&Simular", "Dice qué harían las reglas con lo que ya hay en las carpetas, sin tocar nada.",
			botones, self.simular)
		cuerpo.Add(botones, 0, wx.EXPAND | wx.ALL, 5)
		cuerpo.Add(ui.crear_botonera(self, wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizer(cuerpo)
		self.tabla.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda _e: self.editar())
		self.tabla.Bind(wx.EVT_KEY_DOWN, self._al_tecla_tabla)
		self.lista_carpetas.Bind(wx.EVT_KEY_DOWN, self._al_tecla_carpetas)
		ui.preparar_dialogo(self, foco_inicial=self.lista_carpetas)
		self._refrescar()

	def valores(self) -> tuple[list[str], list[reglas.Regla]]:
		return list(self.carpetas), list(self.lista_reglas)

	def _refrescar(self, fila: int | None = None) -> None:
		self.lista_carpetas.Set(self.carpetas)
		if self.carpetas and self.lista_carpetas.GetSelection() == wx.NOT_FOUND:
			self.lista_carpetas.SetSelection(0)
		self.tabla.reemplazar_filas([[r.nombre, r.condicion(), r.efecto(), "Sí" if r.activa else "No"] for r in self.lista_reglas],
			conservar_foco=fila is None)
		if fila is not None and self.lista_reglas:
			self.tabla.enfocar_fila(max(0, min(fila, len(self.lista_reglas) - 1)), anunciar=False)
		hay = bool(self.lista_reglas)
		for boton in (self.boton_editar, self.boton_borrar, self.boton_subir, self.boton_bajar, self.boton_activar):
			boton.Enable(hay)
		self.boton_quitar.Enable(bool(self.carpetas))
		self.boton_simular.Enable(bool(self.carpetas) and hay)

	# ── Carpetas ─────────────────────────────────────────────────────────────

	def anadir_carpeta(self) -> None:
		dialogo = wx.DirDialog(self, "Carpeta que se vigila", defaultPath=self.propuesta, style=wx.DD_DIR_MUST_EXIST)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return
			self.agregar_carpeta(dialogo.GetPath())
		finally:
			dialogo.Destroy()

	def agregar_carpeta(self, carpeta: str) -> bool:
		if not carpeta or any(os.path.normcase(c) == os.path.normcase(carpeta) for c in self.carpetas):
			return False
		self.carpetas.append(carpeta)
		self._refrescar()
		self.lista_carpetas.SetSelection(len(self.carpetas) - 1)
		self.zc.anunciar(f"Carpeta añadida: {carpeta}", api.RESULTADO)
		return True

	def quitar_carpeta(self) -> None:
		indice = self.lista_carpetas.GetSelection()
		if 0 <= indice < len(self.carpetas):
			carpeta = self.carpetas.pop(indice)
			self._refrescar()
			if self.carpetas:
				self.lista_carpetas.SetSelection(min(indice, len(self.carpetas) - 1))
			self.zc.anunciar(f"Carpeta quitada: {carpeta}", api.RESULTADO)

	# ── Reglas ───────────────────────────────────────────────────────────────

	def _fila(self) -> int:
		fila = self.tabla.fila_actual()
		return fila if 0 <= fila < len(self.lista_reglas) else -1

	def _editar(self, regla: reglas.Regla) -> reglas.Regla | None:
		dialogo = DialogoRegla(self.zc, self, regla, self.carpetas)
		try:
			if self.zc.ui.mostrar_modal(dialogo) != wx.ID_OK:
				return None
			return dialogo.regla()
		finally:
			dialogo.Destroy()

	def nueva(self) -> None:
		regla = self._editar(reglas.Regla(f"Regla {len(self.lista_reglas) + 1}"))
		if regla is not None:
			self.lista_reglas.append(regla)
			self._refrescar(len(self.lista_reglas) - 1)

	def editar(self) -> None:
		fila = self._fila()
		if fila < 0:
			return
		regla = self._editar(self.lista_reglas[fila])
		if regla is not None:
			self.lista_reglas[fila] = regla
			self._refrescar(fila)

	def borrar(self) -> None:
		fila = self._fila()
		if fila < 0:
			return
		regla = self.lista_reglas.pop(fila)
		self._refrescar(fila)
		self.zc.anunciar(f"Regla borrada: {regla.nombre}", api.RESULTADO)

	def mover(self, desplazamiento: int) -> None:
		fila = self._fila()
		destino = fila + desplazamiento
		if fila < 0 or not 0 <= destino < len(self.lista_reglas):
			return
		self.lista_reglas[fila], self.lista_reglas[destino] = self.lista_reglas[destino], self.lista_reglas[fila]
		self._refrescar(destino)
		self.zc.anunciar(f"{self.lista_reglas[destino].nombre}: posición {destino + 1} de {len(self.lista_reglas)}", api.RESULTADO)

	def alternar(self) -> None:
		fila = self._fila()
		if fila < 0:
			return
		regla = self.lista_reglas[fila]
		regla.activa = not regla.activa
		self._refrescar(fila)
		self.zc.anunciar(f"{regla.nombre}: {'activa' if regla.activa else 'desactivada'}", api.RESULTADO)

	def simular(self) -> None:
		carpetas, lista = list(self.carpetas), list(self.lista_reglas)
		self.zc.anunciar("Simulando las reglas...", api.NORMAL)
		self.zc.tareas.enviar(lambda _t: self.complemento.simular_texto(carpetas, lista),
			al_terminar=lambda texto: self.zc.ui.mostrar_texto("Simulación de las reglas", texto),
			al_fallar=lambda error: self.zc.anunciar(f"No se pudo simular: {error}", api.ESENCIAL), nombre="monitor_simular")

	def _al_tecla_tabla(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.borrar()
			return
		evento.Skip()

	def _al_tecla_carpetas(self, evento: wx.KeyEvent) -> None:
		if evento.GetKeyCode() == wx.WXK_DELETE and not evento.HasAnyModifiers():
			self.quitar_carpeta()
			return
		evento.Skip()


class DialogoRegistro(wx.Dialog):
	"""Lo que ha hecho el monitor, del más reciente al más antiguo."""

	def __init__(self, complemento, padre: wx.Window | None) -> None:
		super().__init__(padre, title="Registro del monitor", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER, size=(780, 440))
		self.complemento = complemento
		self.zc: api.Anfitrion = complemento.zc
		ui = self.zc.ui
		cuerpo = wx.BoxSizer(wx.VERTICAL)
		etiqueta = wx.StaticText(self, label="&Registro:")
		self.lista = ui.ListaAccesible(self, "Registro", [("Fecha", 130), ("Archivo", 200), ("Regla", 120), ("Resultado", 260),
			("Deshecho", 80)])
		self.lista.SetHelpText("Lo que ha hecho el monitor, lo más reciente primero.")
		cuerpo.Add(etiqueta, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
		cuerpo.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)
		botones = wx.BoxSizer(wx.HORIZONTAL)
		self.boton_deshacer = _boton(self, "&Deshacer la última acción", "Devuelve el último archivo movido o renombrado a su sitio, "
			"o manda a la papelera la última copia.", botones, self.deshacer)
		self.boton_vaciar = _boton(self, "&Vaciar el registro", "Borra todos los apuntes (no toca ningún archivo).", botones,
			self.vaciar)
		cerrar = _boton(self, "&Cerrar", "Cierra la ventana (también con Escape).", botones, id_boton=wx.ID_CLOSE)
		cerrar.Bind(wx.EVT_BUTTON, lambda _e: self.EndModal(wx.ID_CLOSE) if self.IsModal() else self.Destroy())
		cuerpo.Add(botones, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
		self.SetSizer(cuerpo)
		ui.preparar_dialogo(self, id_escape=wx.ID_CLOSE, foco_inicial=self.lista)
		self.recargar()

	def recargar(self) -> None:
		apuntes = list(reversed(self.complemento.registro.apuntes))
		self.lista.reemplazar_filas([[time.strftime("%d/%m/%Y %H:%M", time.localtime(a.fecha)), os.path.basename(a.archivo),
			a.regla, a.texto if a.ok else f"Error: {a.texto}", "Sí" if a.deshecho else ""] for a in apuntes], conservar_foco=False)
		self.boton_deshacer.Enable(self.complemento.registro.ultimo_deshacible() is not None)
		self.boton_vaciar.Enable(bool(apuntes))

	def deshacer(self) -> None:
		self.complemento.deshacer_ultimo()
		self.recargar()

	def vaciar(self) -> None:
		if self.zc.ui.confirmar("¿Vaciar el registro del monitor? No se toca ningún archivo, pero ya no se podrá deshacer.",
				"Vaciar el registro", self, peligroso=True):
			self.complemento.registro.vaciar()
			self.recargar()
