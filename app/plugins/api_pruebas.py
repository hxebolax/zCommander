# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Submódulo ``api.pruebas`` (diseño 2.0, 3.7): ayudas sin wx para probar complementos.

Se importa como ``from app.plugins.api import pruebas`` (o ``api.pruebas``).
Consolida el ``DecisorFalso`` que la 1.x repetía en varias pruebas; el
``PanelFalso`` de aquí es NUEVO e implementa ``PanelComplemento`` (el de
``tests/ui/g_comun.py`` imita el panel del núcleo y sigue para la 1.x).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.plugins import api, manifiesto
from app.plugins import registro as _registro
from app.services.operaciones.modelo import AccionError, Decisor


class PanelFalso:
	"""``PanelComplemento`` con entradas fijas: ``cursor`` es un índice y ``marcadas`` nombres."""

	def __init__(self, entradas: Sequence[Any] = (), cursor: int = 0, marcadas: Sequence[str] = (), ruta: str = "",
			proveedor: Any = None, lado: str = "izquierdo") -> None:
		self.entradas = list(entradas)
		self._cursor = cursor
		self._marcadas = set(marcadas)
		self._ruta = ruta
		self._proveedor = proveedor
		self.lado = lado
		self.refrescos = 0

	@property
	def proveedor(self) -> Any:
		if self._proveedor is None:
			from app.services.vfs import resolver

			return resolver.proveedor_local()
		return self._proveedor

	@property
	def ruta(self) -> str:
		return self._ruta

	def mostrar_ruta(self) -> str:
		return self._ruta

	def cursor(self) -> Any:
		return self.entradas[self._cursor] if 0 <= self._cursor < len(self.entradas) else None

	def marcadas(self) -> list[Any]:
		return [e for e in self.entradas if e.nombre in self._marcadas]

	def elementos_trabajo(self) -> list[Any]:
		marcadas = self.marcadas()
		if marcadas:
			return marcadas
		actual = self.cursor()
		return [actual] if actual is not None and not getattr(actual, "es_superior", False) else []

	def refrescar(self) -> None:
		self.refrescos += 1


class DecisorFalso:
	"""``Decisor`` que devuelve las ``respuestas`` en orden; ``preguntas`` guarda lo preguntado.

	Sin respuestas pendientes: conflictos → omitir, errores → omitir, elegir → 0, textos → ``None``.
	"""

	def __init__(self, respuestas: Sequence[Any] = ()) -> None:
		self.respuestas = list(respuestas)
		self.preguntas: list[tuple[str, Any]] = []

	def _siguiente(self, defecto: Any) -> Any:
		return self.respuestas.pop(0) if self.respuestas else defecto

	def resolver_conflictos(self, operacion: Any, conflictos: Sequence[Any]) -> Any:
		from app.services.operaciones.modelo import AccionConflicto, RespuestaConflicto

		self.preguntas.append(("conflictos", list(conflictos)))
		respuesta = self._siguiente(None)
		if respuesta is None:
			return [RespuestaConflicto(AccionConflicto.OMITIR) for _ in conflictos]
		return respuesta

	def preguntar_conflicto(self, operacion: Any, conflicto: Any) -> Any:
		from app.services.operaciones.modelo import AccionConflicto, RespuestaConflicto

		self.preguntas.append(("conflicto", conflicto))
		return self._siguiente(RespuestaConflicto(AccionConflicto.OMITIR))

	def preguntar_error(self, operacion: Any, pregunta: Any) -> AccionError:
		self.preguntas.append(("error", pregunta))
		return self._siguiente(AccionError.OMITIR)

	def elegir(self, titulo: str, texto: str, opciones: Sequence[str], predeterminada: int = 0, escape: int = -1,
			operacion: Any = None) -> int:
		self.preguntas.append(("elegir", titulo))
		return self._siguiente(0)

	def elegir_con_casilla(self, titulo: str, texto: str, opciones: Sequence[str], casilla: str, predeterminada: int = 0,
			escape: int = -1, operacion: Any = None) -> tuple[int, bool]:
		self.preguntas.append(("elegir_con_casilla", titulo))
		return self._siguiente((0, False))

	def pedir_texto(self, titulo: str, texto: str, valor: str = "", oculto: bool = False, operacion: Any = None) -> str | None:
		self.preguntas.append(("texto", titulo))
		return self._siguiente(None)

	def pedir_credenciales(self, titulo: str, texto: str, usuario: str = "", operacion: Any = None) -> tuple[str, str, bool] | None:
		self.preguntas.append(("credenciales", titulo))
		return self._siguiente(None)


class _SonidosFalsos(api.SonidosComplemento):
	def sonar(self, evento: str, variante: str = "", *, sustituye: bool = False) -> bool:
		self._zc.sonidos_pedidos.append(api._id_sonido(self._id, evento))
		return True


class AnfitrionFalso(api.Anfitrion):
	"""``Anfitrion`` para pruebas: apunta anuncios, sonidos y operaciones en lugar de usar la ventana."""

	def __init__(self, id: str, carpeta: Path, *, permisos: Sequence[str] = (), decisor: Decisor | None = None) -> None:
		super().__init__(id, carpeta, permisos=permisos, decisor=decisor or DecisorFalso())
		self.anuncios: list[tuple[str, str]] = []
		self.sonidos_pedidos: list[str] = []
		self.operaciones_lanzadas: list[Any] = []
		self.instancia: Any = None
		self.sonidos = _SonidosFalsos(self)

	def anunciar(self, texto: str, nivel: str = api.NORMAL, completo: str = "", interrumpir: bool | None = None) -> None:
		self.anuncios.append((texto, nivel))

	def lanzar(self, operacion: Any, en_cola: bool = False, al_terminar: Any = None) -> None:
		if not getattr(operacion, "orden_origen", ""):
			operacion.orden_origen = api._orden_en_curso.get(self.id, "")
		self.operaciones_lanzadas.append(operacion)

	def activar(self) -> None:
		"""Importa la clase de entrada (sin verificar sumas) y llama a ``activar(self)`` si aún no se hizo."""
		if self.instancia is not None:
			return
		datos = manifiesto.leer(self.carpeta)
		from app.plugins.cargador import Cargador, _paquete_raiz  # noqa: F401 - prepara el paquete raíz

		registrado = _registro.complemento(datos.id)
		if registrado is None:
			registrado = _registro.registrar(datos, self.carpeta, "prueba")
		registrado.sumas = None
		_paquete_raiz()
		cargador = Cargador.__new__(Cargador)
		cargador._buscadores = []
		clase = Cargador._importar(cargador, registrado)
		self.instancia = clase()
		self.instancia.id = datos.id
		self.instancia.carpeta = self.carpeta
		self.instancia.activar(self)

	def ejecutar(self, id_corto: str, contexto: api.ContextoComplemento | None = None) -> None:
		self.activar()
		contexto = contexto or contexto_de_prueba()
		contexto.orden = f"{self.id}:{id_corto}"
		manejador = _registro.manejador(contexto.orden)
		if manejador is None:
			raise KeyError(contexto.orden)
		api._orden_en_curso[self.id] = contexto.orden
		try:
			manejador(contexto)
		finally:
			api._orden_en_curso.pop(self.id, None)

	def columna(self, id_corto: str, entrada: Any, proveedor: Any = None) -> str | None:
		self.activar()
		funcion = _registro.funcion("columna", f"{self.id}:{id_corto}")
		if funcion is None:
			raise KeyError(id_corto)
		from app.services.vfs import resolver
		from app.services.vfs.base import Cancelacion

		return funcion(entrada, proveedor or resolver.proveedor_local(), Cancelacion())

	def visor(self, id_corto: str, ruta: str, proveedor: Any = None) -> api.Documento:
		self.activar()
		funcion = _registro.funcion("visor", f"{self.id}:{id_corto}")
		if funcion is None:
			raise KeyError(id_corto)
		from app.services.vfs import resolver
		from app.services.vfs.base import Cancelacion

		return funcion(proveedor or resolver.proveedor_local(), ruta, Cancelacion())

	def emitir(self, evento: str, **datos: Any) -> None:
		from app.services import eventos

		self.activar()
		eventos.bus().emitir(evento, **datos)


def anfitrion_de_prueba(carpeta: Path, config: dict | None = None, permisos: Sequence[str] = ()) -> AnfitrionFalso:
	"""Un ``AnfitrionFalso`` para el complemento de ``carpeta``; ``config`` fija valores de su configuración."""
	datos = manifiesto.leer(Path(carpeta))
	if _registro.complemento(datos.id) is None:
		_registro.registrar(datos, Path(carpeta), "prueba")
	anfitrion = AnfitrionFalso(datos.id, Path(carpeta), permisos=permisos or datos.permisos)
	for clave, valor in (config or {}).items():
		anfitrion.config.establecer(clave, valor)
	return anfitrion


@dataclass
class ContextoPrueba(api.ContextoComplemento):
	"""``ContextoComplemento`` cuyos anuncios van a ``anfitrion.anuncios`` (si se le da un ``AnfitrionFalso``)."""

	anfitrion: Any = None

	def anunciar(self, texto: str, nivel: str = api.NORMAL, completo: str = "", interrumpir: bool | None = None) -> None:
		if self.anfitrion is not None and hasattr(self.anfitrion, "anuncios"):
			self.anfitrion.anuncios.append((texto, nivel))
			return
		super().anunciar(texto, nivel, completo, interrumpir)


def contexto_de_prueba(activo: PanelFalso | None = None, pasivo: PanelFalso | None = None, argumento: Any = None,
		anfitrion: AnfitrionFalso | None = None) -> api.ContextoComplemento:
	"""Contexto de una orden con paneles falsos; con ``anfitrion``, ``ctx.anunciar`` apunta en ``anfitrion.anuncios`` (1.1)."""
	return ContextoPrueba(orden="", activo=activo or PanelFalso(), pasivo=pasivo or PanelFalso(lado="derecho"),
		argumento=argumento, anfitrion=anfitrion)
