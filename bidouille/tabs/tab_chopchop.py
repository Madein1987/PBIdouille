# -*- coding: utf-8 -*-
"""Onglet « ChopChop 🪓 » : le panneau de ChopChopRapport embarqué dans
BIdouille — mesures et colonnes inutilisées, export, suppression TMDL.
Le projet vient de la barre partagée de l'app.

L'analyse (um.analyze) est DIFFÉRÉE : changer de projet dans BIdouille reste
instantané, ChopChop analyse quand son onglet devient visible."""

from __future__ import annotations

from qtpy.QtWidgets import QVBoxLayout, QWidget

# le panneau vit dans unused_measures_ui (racine Fitbit\, déjà sur sys.path) —
# même implémentation que la fenêtre autonome « py unused_measures_ui.py »
from unused_measures_ui import ChopChopPanel


class ChopChopTab(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.panel = ChopChopPanel()
        lay.addWidget(self.panel)
        self._pending = None   # .pbip à analyser à la prochaine visite de l'onglet

    def set_project(self, project):
        self._pending = str(project.pbip)
        if self.isVisible():
            self._apply()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._apply()

    def _apply(self):
        pbip, self._pending = self._pending, None
        self.panel.set_pbip(pbip)
