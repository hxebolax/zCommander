# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Crear una carpeta cifrada en la nube (diseño 2.0, 12.6; rclone.md 4.10).

``crypt`` cifra en este equipo, antes de subir, el contenido y los nombres de
una carpeta de otra cuenta. El resultado es otra unidad que se navega en claro.
Sin la contraseña y la sal NO hay forma de recuperar los archivos: el diálogo
lo dice y ofrece «&Generar» (valores aleatorios) y «Mo&strar».
"""

from __future__ import annotations

import secrets
from typing import Any

import wx

from app.plugins import api

from . import comun

_ = api.traduccion("zc_nubes")[0]

CIFRADO_NOMBRES = [("standard", _("Cifrar los nombres (recomendado)")), ("obfuscate", _("Ocultar los nombres (poco seguro)")),
	("off", _("No cifrar los nombres"))]


class DialogoCifrada(comun.DialogoNubes):
	def __init__(self, zc: Any, padre: wx.Window | None, cuentas: list[tuple[str, str]], cuenta: str = "") -> None:
		super().__init__(zc, padre, _("Crear una carpeta cifrada en la nube"))
		comun.texto_solo_lectura(zc, self.panel, _("A&viso:"), _("Sin la contraseña y la sal no hay manera de recuperar los "
			"archivos cifrados: apúntelas en un lugar seguro. zCommander las guarda cifradas en este equipo, pero si lo pierde, "
			"las pierde con él."), sizer=self.sizer, alto=70)
		self.cuenta = comun.elegir(zc, self.panel, _("C&uenta donde se guardan los datos:"), cuentas, cuenta, sizer=self.sizer,
			ayuda=_("La cuenta de nube que guardará los archivos ya cifrados."))
		self.carpeta = comun.campo(zc, self.panel, _("Ca&rpeta de esa cuenta:"), wx.TextCtrl, "/Cifrado", sizer=self.sizer,
			ayuda=_("Carpeta de la cuenta para los archivos cifrados; se crea si no existe."))
		self.nombre = comun.campo(zc, self.panel, _("&Nombre visible:"), wx.TextCtrl, _("Carpeta cifrada"), sizer=self.sizer,
			ayuda=_("Cómo se verá la nueva unidad en el selector."))
		self.contrasena = comun.campo(zc, self.panel, _("Con&traseña:"), wx.TextCtrl, sizer=self.sizer,
			ayuda=_("Contraseña del cifrado. Larga y difícil de adivinar."))
		self.sal = comun.campo(zc, self.panel, _("Sa&l (segunda contraseña, recomendada):"), wx.TextCtrl, sizer=self.sizer,
			ayuda=_("Una segunda contraseña distinta que refuerza el cifrado."))
		self.nombres = comun.elegir(zc, self.panel, _("Cifrado de los nombres de archiv&o:"), CIFRADO_NOMBRES, "standard",
			sizer=self.sizer, ayuda=_("Con «Cifrar los nombres» nadie ve en la nube cómo se llaman sus archivos."))
		comun.boton(self.panel, _("&Generar contraseña y sal"), _("Escribe en los campos una contraseña y una sal aleatorias."),
			self.generar, sizer=self.sizer)
		self.botones(wx.OK | wx.CANCEL)
		self.Bind(wx.EVT_BUTTON, self._aceptar, id=wx.ID_OK)
		self.terminar(self.cuenta)

	def generar(self) -> None:
		self.contrasena.SetValue(secrets.token_urlsafe(24))
		self.sal.SetValue(secrets.token_urlsafe(24))
		self.zc.anunciar(_("Contraseña y sal generadas; están escritas en sus campos para que las copie"), api.RESULTADO)
		self.contrasena.SetFocus()

	def _aceptar(self, evento: wx.CommandEvent) -> None:
		if not self.contrasena.GetValue().strip() or not self.nombre.GetValue().strip() or not comun.valor_elegido(self.cuenta):
			comun.error(self.zc, _("Faltan la cuenta, el nombre visible o la contraseña."))
			return
		evento.Skip()

	def datos(self) -> dict[str, str]:
		return {"cuenta": comun.valor_elegido(self.cuenta), "carpeta": self.carpeta.GetValue().strip(), "nombre": self.nombre.GetValue().strip(),
			"contrasena": self.contrasena.GetValue().strip(), "sal": self.sal.GetValue().strip(), "nombres": comun.valor_elegido(self.nombres)}
