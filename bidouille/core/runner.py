# -*- coding: utf-8 -*-
"""Exécuteur générique d'un outil dans un thread de travail, avec log streamé
vers l'UI. Garde l'interface réactive et sérialise naturellement les runs."""

from __future__ import annotations

import traceback

from qtpy.QtCore import QThread, Signal


class ToolRunner(QThread):
    """Lance func(log=..., **kwargs) dans un thread. `func` doit accepter un
    paramètre `log` (chaque ligne y est envoyée) et retourner un résultat.

    Signals : `line(str)` par ligne de log, `ok(object)` avec le résultat au
    succès, `fail(str)` avec le message/trace sinon. Les émissions traversent
    les threads via des connexions en file d'attente (thread-safe)."""

    line = Signal(str)
    ok = Signal(object)
    fail = Signal(str)

    def __init__(self, func, **kwargs):
        super().__init__()
        self._func = func
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(log=self.line.emit, **self._kwargs)
            self.ok.emit(result)
        except SystemExit as e:   # nos scripts lèvent SystemExit sur erreur attendue
            self.fail.emit(str(e))
        except Exception:
            self.fail.emit(traceback.format_exc())
