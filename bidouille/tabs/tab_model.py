# -*- coding: utf-8 -*-
"""Onglet « Modèle » : génère les mesures/variations/branches, les tables
paramètre de champ et la mesure Switch DIRECTEMENT dans les fichiers TMDL —
sans Tabular Editor ni Power BI ouvert (generate_measures.py, le remplaçant
natif du csx). Desktop doit être FERMÉ pour une écriture réelle ; backup
automatique ; rouvrir le .pbip ensuite."""

from __future__ import annotations

import json

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import model_reader
from core.runner import ToolRunner
from core.theme import TEXT_DIM, YELLOW

import generate_measures


class ModelTab(QWidget):
    # emis apres une generation qui a REELLEMENT ecrit : les onglets qui
    # lisent le modele doivent relire la liste des KPI
    modele_genere = Signal()

    def __init__(self):
        super().__init__()
        self.project = None
        self._runner = None

        root = QVBoxLayout(self)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(f"color:{YELLOW};")
        self.lbl_hint.hide()
        root.addWidget(self.lbl_hint)

        # affiché par l'onglet Mesures quand le config a des modifs non sauvées
        self.lbl_unsaved = QLabel("⚠ Config modifiée non sauvegardée — clique « Sauvegarder » "
                                  "avant de générer (le générateur lit le fichier sur le disque).")
        self.lbl_unsaved.setWordWrap(True)
        self.lbl_unsaved.setStyleSheet(f"color:{YELLOW};")
        self.lbl_unsaved.hide()
        root.addWidget(self.lbl_unsaved)

        box = QGroupBox("Génération des mesures (écrit directement le modèle)")
        grid = QGridLayout(box)
        self.lbl_recap = QLabel("")
        self.lbl_recap.setWordWrap(True)
        self.lbl_recap.setStyleSheet(f"color:{TEXT_DIM};")
        grid.addWidget(self.lbl_recap, 0, 0, 1, 2)

        opts = QHBoxLayout()
        self.chk_dry = QCheckBox("Aperçu (dry-run)")
        self.chk_dry.setChecked(True)
        self.chk_dry.setToolTip("Calcule et liste tout sans RIEN écrire.")
        opts.addWidget(self.chk_dry)
        self.chk_orphans = QCheckBox("Supprimer les orphelines (removeOrphans)")
        self.chk_orphans.setToolTip("Mesures générées qui ne correspondent plus à la config\n"
                                    "(variation retirée...) : supprimées du modèle.")
        opts.addWidget(self.chk_orphans)
        opts.addStretch()
        self.btn_generate = QPushButton("Générer les mesures")
        self.btn_generate.clicked.connect(self._run)
        opts.addWidget(self.btn_generate)
        grid.addLayout(opts, 1, 0, 1, 2)
        root.addWidget(box)

        root.addWidget(QLabel("Journal :"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        root.addWidget(self.log, 1)

    # ---- projet ----------------------------------------------------------------

    def set_project(self, project):
        self.project = project
        cfg_path = project.config_json
        if not cfg_path.exists():
            self.lbl_hint.setText(
                "Aucun measures_config.json chargé — attendu : " + str(cfg_path)
                + "\nClique « Config… » dans la barre du haut pour choisir celui de CE rapport.")
            self.lbl_hint.show()
            self.btn_generate.setEnabled(False)
            self.lbl_recap.setText("")
            return
        self.lbl_hint.hide()
        self.btn_generate.setEnabled(project.model_dir.exists())

        cfg = model_reader.read_config(project)
        settings = cfg.get("settings") or {}
        variations = cfg.get("variations") or {}
        branches = list((cfg.get("branches") or {}).keys())
        fp = cfg.get("fieldParameter") or {}
        tables = ((fp.get("tableNames") or []) + (fp.get("tableNamesByKpi") or [])
                  + (fp.get("tableNamesKpiBase") or []))
        sw = cfg.get("switch") or {}
        self.chk_orphans.setChecked(bool(settings.get("removeOrphans", False)))
        self.lbl_recap.setText(
            f"Config : {cfg_path.name} — bases = mesures de "
            f"'{settings.get('sourceTable', '_mesures')}' "
            f"(dossier '{settings.get('sourceFolder', '')}') · "
            f"{len(variations)} variation(s) · branches : {', '.join(branches) or '—'} · "
            f"tables paramètre : {', '.join(tables) or '—'} · "
            f"switch : {sw.get('name') if sw.get('enabled', bool(sw)) else 'désactivé'}\n"
            f"⚠ Écriture réelle : Power BI Desktop FERMÉ, backup automatique sous "
            f"_tmdl_backups\\, puis rouvrir le .pbip.")

    # ---- exécution ---------------------------------------------------------------

    def _run(self):
        if self._runner is not None or not self.project:
            return
        dry = self.chk_dry.isChecked()
        if not dry:
            if QMessageBox.question(
                self, "Écriture réelle",
                "Les fichiers TMDL du modèle vont être MODIFIÉS.\n"
                "⚠ Power BI Desktop doit être FERMÉ (sinon il écrasera tout).\n\n"
                "Un backup sera créé sous _tmdl_backups\\. Continuer ?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
            ) != QMessageBox.Yes:
                return

        try:
            config = json.loads(self.project.config_json.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            self.log.appendPlainText("Config illisible : " + str(e))
            return

        self.log.appendPlainText("\n=== Génération des mesures" + (" (aperçu)" if dry else "") + " ===")
        r = ToolRunner(generate_measures.generate,
                       model_dir=str(self.project.model_dir),
                       config=config,
                       dry_run=dry,
                       remove_orphans=self.chk_orphans.isChecked())
        r.line.connect(self.log.appendPlainText)
        r.fail.connect(lambda m: self.log.appendPlainText("ERREUR : " + m))
        r.ok.connect(self._apres_succes)
        r.finished.connect(self._done)
        self._ecriture = not dry
        self._runner = r
        self.btn_generate.setEnabled(False)
        r.start()

    def _apres_succes(self, _resultat):
        """Génération terminée SANS erreur. Si elle a réellement écrit, le
        modèle a changé : on prévient l'application pour que les onglets qui
        lisent le modèle revoient la liste des KPI. Sans ça, propager juste
        après générait sur une liste périmée — il fallait recharger le rapport
        à la main pour voir un KPI tout neuf."""
        if getattr(self, "_ecriture", False):
            self.modele_genere.emit()

    def _done(self):
        self._runner = None
        self.btn_generate.setEnabled(True)

    def set_unsaved(self, unsaved: bool):
        """L'onglet Mesures signale ici que le config a des modifs non sauvées."""
        self.lbl_unsaved.setVisible(bool(unsaved))
