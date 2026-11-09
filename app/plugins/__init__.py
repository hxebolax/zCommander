# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 hxebolax y colaboradores
"""Sistema de complementos de zCommander 2.0 (diseño 2.0, sección 3).

Regla de capas SIN excepciones: ningún módulo de ``app/plugins`` importa wx
ni ``app.ui``, ni siquiera de forma perezosa. La interfaz llega por una sola
inyección, ``api.fijar_interfaz`` (protocolo ``interfaz.InterfazAnfitrion``).
"""
