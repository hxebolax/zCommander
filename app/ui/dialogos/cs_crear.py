# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Diálogo «Crear una copia de seguridad» (diseño 2.0, 7.5; orden ``copia_crear``).

Pide dónde guardar, qué partes (casillas que anuncian su estado, con su
tamaño), si se incluyen las contraseñas cifradas con una contraseña de la copia
(que se escribe dos veces, con su fortaleza en texto) y una descripción. No
crea nada: devuelve ``OpcionesCrear`` y la orden lanza la operación.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from pathlib import Path

import wx

from app.services import formato as fmt
from app.services.copia import cifrado, crear, formato
from app.ui.accesibilidad.nombres import crear_campo
from app.ui.dialogos import cs_comun
from app.ui.dialogos.f_comun import mostrar


def _(texto: str) -> str:
	traducir = getattr(builtins, "_", None)
	return traducir(texto) if callable(traducir) else texto


@dataclass
class OpcionesCrear:
	destino: Path
	partes: list[str]
	modo_secretos: str
	contrasena: str | None
	descripcion: str


class DialogoCrearCopia(cs_comun.DialogoCS):
	def __init__(self, padre: wx.Window | None, carpeta: Path, partes_marcadas: list[str], tamanos: dict[str, int]) -> None:
		super().__init__(padre, _("Crear una copia de seguridad"))
		self.resultado: OpcionesCrear | None = None
		self.ids = list(formato.PARTES)
		sizer = self.sizer

		_texto, self.campo_destino = crear_campo(self.panel, _("&Guardar en:"), wx.TextCtrl,
			value=str(Path(carpeta) / crear.nombre_por_defecto()), ayuda=_("Archivo .zcbackup donde se guarda la copia."))
		self.boton_examinar = wx.Button(self.panel, label=_("E&xaminar..."))
		self.boton_examinar.SetHelpText(_("Abre un cuadro para elegir dónde guardar la copia."))
		self.boton_examinar.Bind(wx.EVT_BUTTON, lambda _e: self._examinar())
		sizer.Add(_texto, 0, wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		fila = wx.BoxSizer(wx.HORIZONTAL)
		fila.Add(self.campo_destino, 1, wx.EXPAND | wx.RIGHT, self.FromDIP(5))
		fila.Add(self.boton_examinar, 0)
		sizer.Add(fila, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(5))

		textos = [f"{_(p.nombre)} ({fmt.tamano_legible(tamanos.get(i, 0))})" for i, p in formato.PARTES.items()]
		self.lista_partes = self.lista_casillas(_("&Qué guardar:"), _("Qué guardar"), textos,
			_("Los registros solo sirven para pedir ayuda; no se restauran."), alto=150)
		for indice, id_parte in enumerate(self.ids):
			self.lista_partes.Check(indice, id_parte in partes_marcadas)

		sizer.Add(wx.StaticText(self.panel, label=_("Contraseñas guardadas (FTP, nubes, NAS, complementos):")), 0,
			wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(5))
		self.opcion_incluir = wx.RadioButton(self.panel, label=_("&Incluirlas cifradas con una contraseña"), style=wx.RB_GROUP)
		self.opcion_incluir.SetHelpText(_("Las contraseñas viajan cifradas con AES-256; para restaurarlas hará falta la "
			"contraseña de la copia. Sin ella no hay forma de recuperarlas."))
		self.opcion_excluir = wx.RadioButton(self.panel, label=_("&No incluirlas"))
		self.opcion_excluir.SetHelpText(_("Tras restaurar habrá que volver a escribir las contraseñas y añadir de nuevo "
			"las cuentas de nube."))
		self.opcion_incluir.SetValue(True)
		for opcion in (self.opcion_incluir, self.opcion_excluir):
			sizer.Add(opcion, 0, wx.LEFT | wx.RIGHT, self.FromDIP(10))
			opcion.Bind(wx.EVT_RADIOBUTTON, lambda _e: self._actualizar())

		_t, self.campo_contrasena = crear_campo(self.panel, _("Contrase&ña de la copia:"), wx.TextCtrl, style=wx.TE_PASSWORD,
			ayuda=_("Al menos {n} caracteres. No hay forma de recuperarla si se olvida.").format(n=cifrado.LONGITUD_MINIMA),
			sizer=sizer)
		_t, self.campo_repetir = crear_campo(self.panel, _("&Repita la contraseña:"), wx.TextCtrl, style=wx.TE_PASSWORD,
			ayuda=_("Escriba otra vez la misma contraseña."), sizer=sizer)
		_t, self.campo_fortaleza = crear_campo(self.panel, _("&Fortaleza:"), wx.TextCtrl, style=wx.TE_READONLY,
			value=cifrado.fortaleza(""), ayuda=_("Lo segura que es la contraseña escrita."), sizer=sizer)
		self.aviso = wx.StaticText(self.panel, label=_("Si olvida la contraseña de la copia, sus contraseñas no se podrán "
			"recuperar."))
		sizer.Add(self.aviso, 0, wx.ALL, self.FromDIP(5))
		self.campo_contrasena.Bind(wx.EVT_TEXT, lambda _e: self._actualizar())
		self.campo_repetir.Bind(wx.EVT_TEXT, lambda _e: self._actualizar())

		_t, self.campo_descripcion = crear_campo(self.panel, _("&Descripción:"), wx.TextCtrl,
			ayuda=_("Opcional: para reconocer la copia al restaurar, por ejemplo «Antes de cambiar de equipo»."), sizer=sizer)
		self.terminar_con_accion(_("Crear la co&pia"), _("Crea la copia con lo elegido."), self._aceptar,
			foco=self.lista_partes)
		self._actualizar()

	def _actualizar(self) -> None:
		incluir = self.opcion_incluir.GetValue()
		for control in (self.campo_contrasena, self.campo_repetir, self.campo_fortaleza):
			control.Enable(incluir)
		texto = cifrado.fortaleza(self.campo_contrasena.GetValue())
		if self.campo_repetir.GetValue() and self.campo_repetir.GetValue() != self.campo_contrasena.GetValue():
			texto += ". " + _("Las dos contraseñas no coinciden")
		if self.campo_fortaleza.GetValue() != texto:
			self.campo_fortaleza.ChangeValue(texto)

	def _examinar(self) -> None:
		ruta = cs_comun.elegir_archivo_guardar(self, _("Guardar la copia"), cs_comun.COMODIN_COPIA, self.campo_destino.GetValue())
		if ruta:
			self.campo_destino.SetValue(ruta if ruta.lower().endswith(formato.EXTENSION) else ruta + formato.EXTENSION)
		self.campo_destino.SetFocus()

	def partes_marcadas(self) -> list[str]:
		return cs_comun.marcados(self.lista_partes, self.ids)

	def _aceptar(self) -> None:
		destino = self.campo_destino.GetValue().strip()
		if not destino:
			cs_comun.avisar(self, _("Escriba dónde guardar la copia."))
			self.campo_destino.SetFocus()
			return
		ruta = Path(destino)
		if ruta.suffix.lower() != formato.EXTENSION:
			ruta = ruta.with_name(ruta.name + formato.EXTENSION)
		if not ruta.is_absolute():
			cs_comun.avisar(self, _("Escriba la ruta completa del archivo, con su unidad o carpeta compartida."))
			self.campo_destino.SetFocus()
			return
		partes = self.partes_marcadas()
		if not partes:
			cs_comun.avisar(self, _("Marque al menos una parte para guardar."))
			self.lista_partes.SetFocus()
			return
		contrasena = None
		modo = "excluidos"
		if self.opcion_incluir.GetValue():
			contrasena = self.campo_contrasena.GetValue()
			if not contrasena:
				cs_comun.avisar(self, _("Escriba la contraseña de la copia o elija «No incluirlas»."))
				self.campo_contrasena.SetFocus()
				return
			if contrasena != self.campo_repetir.GetValue():
				cs_comun.avisar(self, _("Las dos contraseñas no coinciden. Vuelva a escribirlas."))
				self.campo_repetir.SetFocus()
				return
			if len(contrasena) < cifrado.LONGITUD_MINIMA and not cs_comun.preguntar(self, _("La contraseña es débil: tiene "
					"menos de {n} caracteres. ¿Crear la copia de todos modos?").format(n=cifrado.LONGITUD_MINIMA)):
				self.campo_contrasena.SetFocus()
				return
			modo = "contrasena"
		if ruta.exists() and not cs_comun.preguntar(self, _("Ya existe {n}. ¿Sustituirlo?").format(n=ruta.name)):
			self.campo_destino.SetFocus()
			return
		self.resultado = OpcionesCrear(ruta, partes, modo, contrasena, self.campo_descripcion.GetValue().strip())
		self.cerrar(wx.ID_OK)


def pedir(padre: wx.Window | None, carpeta: Path, partes_marcadas: list[str], tamanos: dict[str, int]) -> OpcionesCrear | None:
	return mostrar(DialogoCrearCopia(padre, carpeta, partes_marcadas, tamanos), lambda d: d.resultado)
