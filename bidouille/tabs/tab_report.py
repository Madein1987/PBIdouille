# -*- coding: utf-8 -*-
"""Onglet « Rapport » : lance la propagation du formatage conditionnel et la
coloration des matrices par KPI, avec plus d'options que les scripts en CLI.
Chaque outil tourne dans un thread (core.runner) ; le journal est commun."""

from __future__ import annotations

import json
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import model_reader
from core.runner import ToolRunner
from core.theme import TEXT_DIM, checkable_list_stylesheet

import propagate_cf
import color_matrix_by_kpi
import generate_measures



class ReportTab(QWidget):
    def __init__(self):
        super().__init__()
        self.project = None
        self._runner = None
        self._queue = []
        self._failed = False

        root = QVBoxLayout(self)
        root.addWidget(self._build_propagation_group())
        root.addWidget(self._build_colors_group())

        chain_bar = QHBoxLayout()
        self.btn_chain = QPushButton("Propager puis colorer")
        self.btn_chain.clicked.connect(self._run_chain)
        chain_bar.addStretch()
        chain_bar.addWidget(self.btn_chain)
        root.addLayout(chain_bar)

        root.addWidget(QLabel("Journal :"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        root.addWidget(self.log, 1)

        log_bar = QHBoxLayout()
        btn_clear = QPushButton("Vider le journal")
        btn_clear.clicked.connect(self.log.clear)
        log_bar.addStretch()
        log_bar.addWidget(btn_clear)
        root.addLayout(log_bar)

        self._action_buttons = [self.btn_propagate, self.btn_colorize, self.btn_chain]
        self._set_enabled(False)

    # ---- construction de l'UI -------------------------------------------------

    def _build_propagation_group(self) -> QGroupBox:
        box = QGroupBox("Propagation des attributs (formatage conditionnel)")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("KPI gabarit :"), 0, 0)
        self.cmb_template = QComboBox()
        grid.addWidget(self.cmb_template, 0, 1)

        grid.addWidget(QLabel("KPI cibles :"), 1, 0, Qt.AlignTop)
        self.lst_targets = QListWidget()
        self.lst_targets.setStyleSheet(checkable_list_stylesheet())
        self.lst_targets.setMaximumHeight(120)
        grid.addWidget(self.lst_targets, 1, 1)

        grid.addWidget(QLabel("Branches :"), 2, 0, Qt.AlignTop)
        self.lst_branches = QListWidget()
        self.lst_branches.setStyleSheet(checkable_list_stylesheet())
        self.lst_branches.setMaximumHeight(70)
        grid.addWidget(self.lst_branches, 2, 1)

        opts = QHBoxLayout()
        self.chk_prop_dry = QCheckBox("Aperçu (dry-run)")
        self.chk_prop_dry.setChecked(True)
        self.chk_prop_verbose = QCheckBox("Verbeux")
        opts.addWidget(self.chk_prop_dry)
        opts.addWidget(self.chk_prop_verbose)
        opts.addStretch()
        self.btn_propagate = QPushButton("Propager")
        self.btn_propagate.setToolTip(
            "Aligne les KPI cibles sur le KPI gabarit : ce que le gabarit porte "
            "est recopié, ce qu'il ne porte PLUS est retiré des cibles.\n"
            "Chaque visuel modifié est copié dans _propagate_backups\\ avant "
            "écriture. Laisser « Aperçu » coché pour voir le détail sans rien "
            "changer.")
        self.btn_propagate.clicked.connect(self._run_propagate)
        opts.addWidget(self.btn_propagate)
        grid.addLayout(opts, 3, 0, 1, 2)
        return box

    def _build_colors_group(self) -> QGroupBox:
        box = QGroupBox("Couleurs des matrices par KPI")
        grid = QGridLayout(box)

        # L'Excel des indicateurs est défini UNE fois, dans le config
        # (Mesures -> Réglages globaux). Cet onglet ne fait que le lire :
        # deux champs séparés finissaient par diverger.
        self.lbl_td = QLabel("")
        self.lbl_td.setWordWrap(True)
        self.lbl_td.setStyleSheet(f"color:{TEXT_DIM};")
        grid.addWidget(self.lbl_td, 0, 0, 1, 3)

        opts = QHBoxLayout()
        self.chk_col_dry = QCheckBox("Aperçu (dry-run)")
        self.chk_col_dry.setChecked(True)
        opts.addWidget(self.chk_col_dry)
        btn_palette = QPushButton("Aperçu && édition des couleurs…")
        btn_palette.setToolTip("Voir chaque KPI avec ses couleurs fond/texte, les\n"
                               "éditer au sélecteur de couleurs, et réécrire l'Excel\n"
                               "(les colonnes manquantes sont créées).")
        btn_palette.clicked.connect(self._open_colors_dialog)
        opts.addWidget(btn_palette)
        opts.addStretch()
        self.btn_colorize = QPushButton("Colorer")
        self.btn_colorize.clicked.connect(self._run_colorize)
        opts.addWidget(self.btn_colorize)
        grid.addLayout(opts, 2, 0, 1, 3)
        return box

    def _td_spec(self) -> dict:
        """Définition de l'Excel des indicateurs, lue dans le config du
        projet — même source que le générateur. Relue à chaque usage :
        une modification enregistrée dans l'onglet Mesures est donc prise
        en compte sans relancer l'app."""
        cfg = {}
        if self.project:
            try:
                cfg = json.loads(
                    self.project.config_json.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cfg = {}
        return generate_measures.indicateurs_xlsx(
            cfg, self.project.folder if self.project else None)

    def _refresh_td_label(self):
        """Rappelle, dans l'onglet Rapport, ce que le config a décidé."""
        td = self._td_spec()
        existe = Path(td["path"]).exists()
        self.lbl_td.setText(
            ("Excel : " if existe else "\u26a0 Excel INTROUVABLE : ")
            + td["path"] + "\n"
            + "colonnes \u2014 cl\u00e9 : " + td["keyColumn"]
            + "  \u00b7  fond : " + td["fillColumn"]
            + "  \u00b7  texte : " + td["textColumn"] + "\n"
            + "(se r\u00e8gle dans Mesures \u2192 R\u00e9glages globaux \u2192 Excel des indicateurs)")

    def _open_colors_dialog(self):
        from tabs.dialog_couleurs import CouleursDialog
        if not self.project:
            return
        try:
            kpis = model_reader.kpis(self.project)
        except Exception:
            kpis = []
        td = self._td_spec()
        dlg = CouleursDialog(
            td["path"],
            key_col=td["keyColumn"],
            fill_col=td["fillColumn"],
            text_col=td["textColumn"],
            model_kpis=kpis,
            parent=self,
        )
        dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        self._refresh_td_label()

    # ---- projet ---------------------------------------------------------------

    def set_project(self, project):
        """Repeuple l'onglet pour un nouveau projet (appelé par app.py)."""
        self.project = project
        self._refresh_td_label()

        try:
            kpis = model_reader.kpis(project)
        except Exception as e:  # RuntimeError (tmdl absent) ou autre
            kpis = []
            self.log.appendPlainText("KPI illisibles : " + str(e))

        self.cmb_template.clear()
        self.cmb_template.addItems(kpis)
        if "Total Steps" in kpis:
            self.cmb_template.setCurrentText("Total Steps")
        self._fill_checklist(self.lst_targets, kpis, checked=True)
        self._fill_checklist(self.lst_branches, model_reader.branches(project), checked=True)

        self._set_enabled(project.valid)
        if not project.valid:
            self.log.appendPlainText("Projet invalide : dossiers .Report/.SemanticModel introuvables.")

    # ---- helpers listes cochables --------------------------------------------

    @staticmethod
    def _fill_checklist(widget, items, checked=True):
        widget.clear()
        for it in items:
            item = QListWidgetItem(it)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            widget.addItem(item)

    @staticmethod
    def _checked(widget):
        return [widget.item(i).text() for i in range(widget.count())
                if widget.item(i).checkState() == Qt.Checked]

    def _propagate_step(self):
        dry = self.chk_prop_dry.isChecked()
        targets = self._checked(self.lst_targets) or None  # aucun coché = tous
        kwargs = dict(
            report_dir=str(self.project.report_dir),
            template_kpi=self.cmb_template.currentText(),
            branches=self._checked(self.lst_branches),
            targets=targets,
            entity=model_reader.entity(self.project),
            field_parameter=model_reader.field_parameter(self.project),
            dry_run=dry,
            verbose=self.chk_prop_verbose.isChecked(),
        )
        return (propagate_cf.propagate, kwargs, not dry, "Propagation des attributs")

    def _colorize_step(self):
        dry = self.chk_col_dry.isChecked()
        td = self._td_spec()          # relu au moment de l'exécution
        kwargs = dict(
            report_dir=str(self.project.report_dir),
            model_dir=str(self.project.model_dir),
            xlsx=td["path"],
            key_col=td["keyColumn"],
            fill_col=td["fillColumn"],
            text_col=td["textColumn"],
            entity=model_reader.entity(self.project),
            dry_run=dry,
        )
        return (color_matrix_by_kpi.colorize, kwargs, not dry, "Couleurs des matrices")

    # ---- lancement (file d'attente d'étapes) ---------------------------------

    def _run_propagate(self):
        if self.cmb_template.currentText():
            self._enqueue([self._propagate_step()])
        else:
            self.log.appendPlainText("Aucun KPI gabarit sélectionné.")

    def _run_colorize(self):
        self._enqueue([self._colorize_step()])

    def _run_chain(self):
        if not self.cmb_template.currentText():
            self.log.appendPlainText("Aucun KPI gabarit sélectionné.")
            return
        self._enqueue([self._propagate_step(), self._colorize_step()])

    def _enqueue(self, steps):
        if self._runner is not None:
            return  # un run à la fois
        writes = any(w for _, _, w, _ in steps)
        if writes and not self._confirm_write():
            return
        self._queue = list(steps)
        self._failed = False
        self._set_busy(True)
        self._start_next()

    def _start_next(self):
        if self._failed or not self._queue:
            self._queue = []
            self._runner = None
            self._set_busy(False)
            return
        func, kwargs, writes, title = self._queue.pop(0)
        self.log.appendPlainText("\n=== " + title + ("" if writes else " (aperçu)") + " ===")
        r = ToolRunner(func, **kwargs)
        r.line.connect(self._log)
        r.fail.connect(self._on_fail)
        r.finished.connect(self._on_step_finished)
        self._runner = r
        r.start()

    def _confirm_write(self) -> bool:
        return QMessageBox.question(
            self, "Confirmer l'écriture",
            "Des fichiers du rapport vont être modifiés.\n"
            "⚠ Power BI Desktop doit être FERMÉ (sinon les changements seront écrasés).\n\n"
            "Continuer ?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        ) == QMessageBox.Yes

    def _log(self, line):
        self.log.appendPlainText(line)

    def _on_fail(self, msg):
        self._failed = True
        self.log.appendPlainText("ERREUR : " + msg)

    def _on_step_finished(self):
        self._runner = None
        if self._failed or not self._queue:
            self._queue = []
            self._set_busy(False)
        else:
            self._start_next()

    # ---- état des boutons -----------------------------------------------------

    def _set_busy(self, busy):
        self._busy = busy
        for b in self._action_buttons:
            b.setEnabled(not busy)

    def _set_enabled(self, enabled):
        for b in self._action_buttons:
            b.setEnabled(enabled)
