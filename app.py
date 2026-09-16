# -*- coding: utf-8 -*-
"""PBIdouille — cockpit unique des outils Power BI du pipeline Fitbit.

Lancement   : py bidouille\\app.py
Dépendances : qtpy + (PySide6 à la maison / PyQt5 au travail) ; openpyxl ou
              pandas pour les couleurs. Les scripts racine (propagate_cf,
              color_matrix_by_kpi) restent utilisables en CLI comme avant."""

from __future__ import annotations

import sys
from pathlib import Path

# app.py est au 1er niveau ; le reste du code vit dans bidouille\ :
#   bidouille\          -> core, tabs
#   bidouille\moteurs\  -> les moteurs d'écriture PBIP
# Les deux sur le path, quel que soit le répertoire de lancement.
_RACINE = Path(__file__).resolve().parent
_APP_DIR = _RACINE / "bidouille"
_MOTEURS = _APP_DIR / "moteurs"
# point de départ des boîtes de dialogue, et endroit où l'on cherche un projet
# à défaut d'en avoir mémorisé un
_DOSSIER_PARENT = _RACINE
for _p in (str(_APP_DIR), str(_MOTEURS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from qtpy.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qtpy.QtCore import QSettings  # noqa: E402

from core.project import Project, load_recents, push_recent  # noqa: E402
from core.theme import apply_app_theme  # noqa: E402
from tabs.tab_report import ReportTab  # noqa: E402
from tabs.tab_wireframe import WireframeTab  # noqa: E402
from tabs.tab_config import ConfigTab  # noqa: E402
from tabs.tab_chopchop import ChopChopTab  # noqa: E402

APP_NAME = "PBIdouille"          # PBI + bidouille ; réglages QSettings gardés sous « BIdouille »
APP_EMOJI = "🔧"
DEFAULT_PBIP = "Fitbit for random devs.pbip"


class BidouilleWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ChopChop", "BIdouille")
        self.project = None
        self.resize(1000, 800)

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)

        # ---- barre projet (partagée par tous les onglets) ----
        bar = QHBoxLayout()
        self.project_label = QLabel("Aucun projet")
        self.cmb_recents = QComboBox()
        self.cmb_recents.setMinimumWidth(230)
        self.cmb_recents.activated.connect(self._pick_recent)
        btn_change = QPushButton("Changer de rapport…")
        btn_change.clicked.connect(self._choose_project)
        btn_save_all = QPushButton("💾 Tout enregistrer")
        btn_save_all.setToolTip("Écrit toutes les modifications en attente "
                                "(positions du wireframe, config des mesures) — "
                                "backups automatiques.")
        btn_save_all.clicked.connect(self._save_all)
        bar.addWidget(self.project_label, 1)
        bar.addWidget(self.cmb_recents)
        bar.addWidget(btn_change)
        bar.addWidget(btn_save_all)
        v.addLayout(bar)

        # ---- barre config : measures_config.json utilisé (chemin explicite,
        # choisissable — au travail il ne vit pas forcément à côté du .pbip) ----
        cfg_bar = QHBoxLayout()
        self.config_label = QLabel("")
        self.config_label.setWordWrap(True)
        btn_config = QPushButton("Config…")
        btn_config.setToolTip("Choisir le measures_config.json de ce rapport\n"
                              "(par défaut : celui à côté du .pbip). Mémorisé par projet.")
        btn_config.clicked.connect(self._choose_config)
        cfg_bar.addWidget(self.config_label, 1)
        cfg_bar.addWidget(btn_config)
        v.addLayout(cfg_bar)

        warn = QLabel("⚠ Ferme Power BI Desktop avant toute écriture "
                      "(il relit les fichiers à l'ouverture et écraserait les changements).")
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#ffd246;")
        v.addWidget(warn)

        # ---- onglets ----
        self.tabs = QTabWidget()
        self.tab_report = ReportTab()
        self.tabs.addTab(self.tab_report, "Rapport")
        self.tab_wireframe = WireframeTab()
        self.tabs.addTab(self.tab_wireframe, "Wireframe")
        self.tab_config = ConfigTab()          # « Mesures » : config + génération
        self.tabs.addTab(self.tab_config, "Mesures")
        self.tab_chopchop = ChopChopTab()
        self.tabs.addTab(self.tab_chopchop, "ChopChop 🪓")
        v.addWidget(self.tabs, 1)

        # une generation qui ecrit change le modele : les onglets qui le
        # lisent doivent revoir la liste des KPI, sans rechargement manuel
        self.tab_config.model_panel.modele_genere.connect(self._apres_generation)

        self._tabs = [self.tab_report, self.tab_wireframe, self.tab_config,
                      self.tab_chopchop]
        self._reload_recents()
        self._load_initial_project()

    def _save_all(self):
        """Bouton « 💾 Tout enregistrer » : chaque onglet qui a des
        modifications en attente les écrit (backups automatiques)."""
        for t in self._tabs:
            fn = getattr(t, "save_all", None)
            if fn:
                fn()

    # ---- projet ---------------------------------------------------------------

    def _apres_generation(self):
        """Une generation vient d'ECRIRE dans le modele. Les onglets qui le
        lisent doivent revoir la liste des KPI — sinon propager juste apres
        travaillait sur une liste perimee, et il fallait recharger le rapport
        a la main pour voir un KPI tout neuf.

        On ne rappelle PAS set_project : ca reinitialiserait les choix en cours
        (KPI template, cases cochees) et, pour l'onglet Mesures, ca ecraserait
        un config pas encore enregistre."""
        if not self.project:
            return
        self.tab_report.refresh_model()
        self.tab_chopchop.set_project(self.project)   # reanalyse differee

    def _set_project(self, pbip):
        project = Project(pbip)
        # config mémorisé pour CE projet (si toujours présent sur le disque)
        override = self.settings.value("config::" + str(project.pbip), "")
        if override and Path(override).exists():
            project.config_override = Path(override)
        self.project = project
        push_recent(self.settings, pbip)
        self.settings.setValue("last_pbip", str(pbip))
        self.project_label.setText("Projet : " + str(project.pbip))
        self.setWindowTitle(APP_NAME + " — " + project.name)
        self._update_config_label()
        for t in self._tabs:
            t.set_project(project)
        self._reload_recents()

    def _choose_config(self):
        """Choisit le measures_config.json du projet courant (mémorisé)."""
        if not self.project:
            return
        start = str(self.project.config_json.parent if self.project.config_json.exists()
                    else self.project.folder)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir le measures_config.json", start, "Config JSON (*.json)")
        if not path:
            return
        self.project.config_override = Path(path)
        self.settings.setValue("config::" + str(self.project.pbip), path)
        self._update_config_label()
        for t in self._tabs:            # re-peuple KPI/branches/éditeur
            t.set_project(self.project)

    def _update_config_label(self):
        p = self.project.config_json
        if p.exists():
            self.config_label.setText("Config : " + str(p))
            self.config_label.setStyleSheet("")
        else:
            self.config_label.setText(
                "Config : introuvable — attendu " + str(p)
                + "  (clique « Config… » pour choisir celui de ce rapport)")
            self.config_label.setStyleSheet("color:#ffd246;")

    def _load_initial_project(self):
        last = self.settings.value("last_pbip", "")
        default = _DOSSIER_PARENT / DEFAULT_PBIP
        for cand in (last, str(default)):
            if cand and Path(cand).exists():
                self._set_project(cand)
                return
        self.project_label.setText("Aucun projet — clique « Changer de rapport… ».")

    def _choose_project(self):
        start = str(self.project.folder) if self.project else str(_DOSSIER_PARENT)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un projet Power BI", start, "Projet Power BI (*.pbip)")
        if path:
            self._set_project(path)

    def _reload_recents(self):
        self.cmb_recents.blockSignals(True)
        self.cmb_recents.clear()
        recents = load_recents(self.settings)
        if recents:
            self.cmb_recents.addItem("Récents…", "")
            for p in recents:
                self.cmb_recents.addItem(Path(p).stem, p)
        else:
            self.cmb_recents.addItem("(aucun récent)", "")
        self.cmb_recents.blockSignals(False)

    def _pick_recent(self, index):
        path = self.cmb_recents.itemData(index)
        if path:
            self._set_project(path)


def main():
    app = QApplication(sys.argv)
    apply_app_theme(app, APP_EMOJI, "ChopChop.BIdouille")
    win = BidouilleWindow()
    win.show()
    # exec_ (PyQt5) / exec (PySide6/Qt6)
    sys.exit(app.exec_() if hasattr(app, "exec_") else app.exec())


if __name__ == "__main__":
    main()
