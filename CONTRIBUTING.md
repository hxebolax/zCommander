# Cómo contribuir a zCommander

Gracias por querer mejorar zCommander. Esta guía explica cómo informar de un fallo, proponer una idea y enviar cambios de código. zCommander lo usan sobre todo personas ciegas, así que **cada cambio tiene que ser accesible con NVDA, JAWS y el Narrador**: es un requisito, no un extra.

## Informar de un fallo

Abra una [incidencia](https://github.com/hxebolax/zCommander/issues) con:

- La versión de zCommander (menú Ayuda, «Acerca de») y de Windows.
- El lector de pantalla y su versión, si usa uno.
- Qué hacía, qué esperaba que pasara y qué pasó, paso a paso.
- Si puede, el registro más reciente de la carpeta `data\logs`. No guarda contraseñas, pero revíselo antes por si contiene rutas o nombres que no quiera compartir.

## Proponer una idea

Abra una incidencia que explique el problema que resolvería y para quién. Si afecta a cómo se oye algo, describa qué debería anunciar el lector y en qué orden.

## Enviar cambios

1. Prepare el entorno como explica el [README](README.md#para-programadores): `entorno.bat crear` y `entorno.bat descargar`.
2. Cree una rama a partir de `main` con un nombre descriptivo.
3. Haga el cambio, con sus pruebas y su documentación (apartados siguientes).
4. Compruebe que todo pasa:
   - `entorno.bat pruebas`
   - `.venv\Scripts\ruff check .`
   - `.venv\Scripts\python tools\generar_anexos.py --comprobar`
   - `.venv\Scripts\python tools\comprobar_teclas.py --teclas data\docs\teclas.md`
   - `.venv\Scripts\python tools\comprobar_menus.py` y `.venv\Scripts\python tools\comprobar_preferencias.py`
   - `.venv\Scripts\python main.py --comprobar-arranque`
5. Abra una propuesta de cambio (pull request) que explique qué cambia, por qué, y cómo lo ha probado. Diga con qué lectores de pantalla lo ha oído, o si no ha podido.

## Convenciones del código

- **Español** en la interfaz, los mensajes, los registros, los comentarios y las docstrings. Solo los identificadores técnicos que ya lo estén se quedan en inglés.
- **Tabulaciones** para sangrar, nunca espacios. Con un lector de pantalla, cada nivel se oye como una sola tabulación. `ruff format` usa tabulaciones en este proyecto (`pyproject.toml`), aunque `ruff check` no lo comprueba.
- Cada archivo de código empieza con estas dos líneas; `tools/comprobar_licencias.py` falla si falta alguna:

  ```python
  # SPDX-License-Identifier: GPL-3.0-or-later
  # Copyright (C) 2026 hxebolax y colaboradores
  ```

- Los textos que ve la persona van con `_()`, o con `N_()` en las tablas que se traducen más tarde.
- **Regla de capas**: `app/ui` usa `app/services`, `app/plugins` y `app/core`. `app/services` y `app/plugins` nunca importan wx ni `app/ui`. Los complementos solo importan `app.plugins.api`.
- **La interfaz nunca se bloquea**: el trabajo pesado va en hilos, y los controles solo se tocan desde el hilo principal con `wx.CallAfter`.
- **Ningún error se pierde**: nada de `except: pass` sin, como mínimo, `log.debug(..., exc_info=True)` y un comentario que diga por qué.
- **Todo es portable**: lo que la aplicación guarda va en `data`, nunca en `%APPDATA%`, `%TEMP%` ni en el registro de Windows (la única excepción es el arranque con Windows, que la persona activa a propósito).
- Las órdenes se declaran en el catálogo `app/ui/ordenes.py`, del que salen los menús, las teclas, la paleta y la lista de teclas. Las opciones de configuración se declaran en `app/core/configuracion.py`, y su etiqueta y su ayuda en `app/core/descripciones_config.py`.

## Lista de comprobación de accesibilidad

Antes de enviar un cambio en la interfaz, compruebe que:

- Cada control tiene una etiqueta creada justo antes que él, para que el lector la asocie.
- Cada pantalla tiene letras de acceso sin repetir, que no chocan con las de los menús.
- Cada control tiene su ayuda con Ctrl+H.
- El foco empieza en el control lógico y vuelve a su sitio al cerrar un diálogo.
- Escape cancela, e Intro acepta solo cuando es seguro.
- Nada se anuncia dos veces, ni con NVDA, ni con JAWS, ni con el Narrador.
- Las operaciones largas anuncian su progreso y se pueden cancelar.

## Pruebas

- Van con pytest en `tests/`. `tests/servicios` no usa wx, `tests/ui` crea ventanas reales sin mostrarlas y `tests/plugins` prueba los complementos.
- Nunca tocan la carpeta `data` real ni Internet: usan `APP_DATA_DIR` o `tmp_path` y simulan la red.
- Un fallo que se corrige lleva una prueba que fallaba antes del arreglo.

## Documentación

- Si cambia lo que ve o lo que oye la persona, actualice el [manual](data/docs/manual.md).
- Añada una línea a la entrada de la próxima versión en el [registro de cambios](data/docs/changelog.md).
- Si cambia el catálogo de órdenes o la configuración, regenere los anexos con `.venv\Scripts\python tools\generar_anexos.py`.
- Escriba pensando en quien lee con un lector de pantalla: encabezados claros, listas cortas y nada de arte ASCII.

## Complementos

Para crear un complemento, siga la [guía de complementos](docs/complementos/guia.md). Las herramientas `tools/crear_plugin.py`, `tools/validar_plugin.py` y `tools/empaquetar_plugin.py` le ayudan a crearlo, validarlo y empaquetarlo. Los complementos que se distribuyan con zCommander deben tener una licencia compatible con la GPL-3.

## Licencia de las contribuciones

zCommander es software libre con licencia GPL-3.0-or-later. Al enviar una contribución, acepta publicarla con esa misma licencia.
