# -*- coding: utf-8 -*-
"""Onglet « ChopChop 🪓 » : le panneau de ChopChopRapport embarqué dans
BIdouille — mesures et colonnes inutilisées, export, suppression TMDL.
Le projet vient de la barre partagée de l'app.

L'analyse (um.analyze) est DIFFÉRÉE : changer de projet dans BIdouille reste
instantané, ChopChop analyse quand son onglet devient visible."""

from __future__ import annotations

from qtpy.QtWidgets import QVBoxLayout, QWidget

from core.journal import Journal

# le panneau vit dans unused_measures_ui (racine Fitbit\, déjà sur sys.path) —
# même implémentation que la fenêtre autonome « py unused_measures_ui.py »
from unused_measures_ui import ChopChopPanel


class _Relais:
    """Fait passer pour le QPlainTextEdit du panneau, et renvoie tout au
    journal de l'app.

    Le panneau est PARTAGÉ avec la fenêtre autonome (« py
    unused_measures_ui.py »), qui n'a pas de colonne journal : on ne touche
    donc pas à son code. Il n'appelle que `appendPlainText` sur son log — le
    remplacer par ce relais suffit, et sa zone est masquée juste après."""

    def __init__(self, journal):
        self._journal = journal

    def appendPlainText(self, texte):
        # des ÉVÈNEMENTS (analyse, suppression), pas les lignes d'un run :
        # ce qu'un clic écrit d'un coup forme une seule entrée horodatée
        self._journal.info(texte)

    def clear(self):
        pass        # vider le journal de l'app est au bouton du journal


class ChopChopTab(QWidget):
    def __init__(self, journal=None):
        super().__init__()
        self.journal = journal or Journal()
        lay = QVBoxLayout(self)
        self.panel = ChopChopPanel()
        lay.addWidget(self.panel)
        # sa bande de log en bas laisse la place à la colonne de droite : le
        # détail des suppressions y est bien plus lisible qu'en 110 px de haut
        self.panel.log.hide()
        self.panel.log = _Relais(self.journal)
        self._pending = None   # .pbip à analyser à la prochaine visite de l'onglet
        self._pbip = None      # le dernier projet reçu, pour pouvoir le relire

    def set_project(self, project):
        self._pbip = str(project.pbip)
        self._pending = self._pbip
        if self.isVisible():
            self._apply()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._apply()

    def reload(self):
        """« ↻ Tout recharger » : re-analyse le modèle. Différée comme le reste
        — si l'onglet n'est pas visible, elle attend sa prochaine visite."""
        if not self._pbip:
            return
        self._pending = self._pbip
        if self.isVisible():
            self._apply()

    def _apply(self):
        pbip, self._pending = self._pending, None
        self.panel.set_pbip(pbip)
