# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""``.doc`` antiguo: Microsoft Word por COM (pywin32) lo guarda como DOCX en un temporal y se lee como DOCX.

Si Word no está instalado: «Para .doc hace falta Microsoft Word». Word se abre
invisible, sin macros ni alertas, el documento en solo lectura, y se cierra
siempre al terminar.
"""

from __future__ import annotations

import logging
import os
import tempfile

from .comun import ErrorDocumento, Opciones, _
from .ooxml import convertir_docx

log = logging.getLogger("zcplugins.zc.documentos")

_FORMATO_DOCX = 16  # wdFormatXMLDocument
_SIN_MACROS = 3  # msoAutomationSecurityForceDisable


def convertir_doc(ruta_local: str, nombre: str, opciones: Opciones, carpeta_temporal: str | None = None):
	"""``carpeta_temporal``: dónde deja Word el DOCX intermedio (la caché del complemento, dentro de ``data``)."""
	try:
		import pythoncom
		import win32com.client
	except ImportError as error:
		raise ErrorDocumento(_("Para .doc hace falta Microsoft Word")) from error
	pythoncom.CoInitialize()
	word = None
	try:
		try:
			word = win32com.client.DispatchEx("Word.Application")
		except Exception as error:  # noqa: BLE001 - pywintypes.com_error cuando Word no está
			raise ErrorDocumento(_("Para .doc hace falta Microsoft Word")) from error
		word.Visible = False
		word.DisplayAlerts = 0
		try:
			word.AutomationSecurity = _SIN_MACROS
		except Exception:  # noqa: BLE001 - versiones antiguas sin esta propiedad
			log.debug("Word sin AutomationSecurity", exc_info=True)
		with tempfile.TemporaryDirectory(prefix="zc-doc-", dir=carpeta_temporal) as carpeta:
			destino = os.path.join(carpeta, "documento.docx")
			try:
				documento = word.Documents.Open(os.path.abspath(ruta_local), False, True, False)
				documento.SaveAs2(destino, _FORMATO_DOCX)
				documento.Close(False)
			except Exception as error:  # noqa: BLE001 - errores COM de Word
				raise ErrorDocumento(_("Word no pudo abrir el documento: {e}").format(e=error)) from error
			with open(destino, "rb") as archivo:
				datos = archivo.read()
		return convertir_docx(datos, nombre, opciones)
	finally:
		if word is not None:
			try:
				word.Quit(False)
			except Exception:  # noqa: BLE001 - Word ya cerrado
				log.debug("Word ya estaba cerrado", exc_info=True)
		pythoncom.CoUninitialize()
