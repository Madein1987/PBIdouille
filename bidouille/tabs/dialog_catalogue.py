# -*- coding: utf-8 -*-
"""Bibliothèque de variations — un fichier GLOBAL où l'on pioche.

Le measures_config.json d'un rapport reste AUTONOME : ce qu'il contient est
exactement ce qui sera généré. La bibliothèque, elle, vit hors projet et garde
toutes les variations qu'on réutilise d'un rapport à l'autre.

  · Importer  : copie la variation de la bibliothèque VERS le rapport ;
  · Publier   : l'inverse, pour partager une variation qu'on vient d'écrire.

Rien à cocher ni à retenir projet par projet : une fois importée, la variation
appartient au rapport.
"""

from __future__ import annotations

import json
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

import generate_measures as gm

try:
    from core.theme import TEXT_DIM
except ImportError:                                  # copie isolée
    TEXT_DIM = "#9aa0a6"


class CatalogueDialog(QDialog):
    """Deux listes face à face : la bibliothèque et le rapport."""

    def __init__(self, config: dict, chemin_biblio, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Bibliothèque de variations")
        self.resize(820, 520)
        self.modifie = False          # le config du rapport a-t-il changé ?

        lay = QVBoxLayout(self)

        # --- fichier de la bibliothèque ---
        haut = QHBoxLayout()
        self.ed_path = QLineEdit(str(chemin_biblio or ""))
        self.ed_path.setPlaceholderText(
            "chemin du fichier de bibliothèque (partageable sur un lecteur réseau)")
        self.ed_path.editingFinished.connect(self.reload)
        b_parcourir = QPushButton("Parcourir…")
        b_parcourir.clicked.connect(self._choisir)
        haut.addWidget(QLabel("Bibliothèque :"))
        haut.addWidget(self.ed_path, 1)
        haut.addWidget(b_parcourir)
        lay.addLayout(haut)

        note = QLabel(
            "Importer copie la variation DANS le config de ce rapport — il "
            "reste autonome, et c'est exactement ce qu'il générera. Publier "
            "fait l'inverse, pour réutiliser ailleurs une variation écrite ici.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_DIM};")
        lay.addWidget(note)

        # --- les deux listes ---
        milieu = QHBoxLayout()

        gauche = QVBoxLayout()
        gauche.addWidget(QLabel("Dans la bibliothèque"))
        self.lst_biblio = QListWidget()
        self.lst_biblio.setSelectionMode(QListWidget.ExtendedSelection)
        gauche.addWidget(self.lst_biblio, 1)
        self.lbl_biblio = QLabel("")
        self.lbl_biblio.setStyleSheet(f"color:{TEXT_DIM};")
        gauche.addWidget(self.lbl_biblio)
        milieu.addLayout(gauche, 1)

        fleches = QVBoxLayout()
        fleches.addStretch()
        self.b_importer = QPushButton("Importer  →")
        self.b_importer.setToolTip(
            "Copie les variations choisies dans le config de ce rapport.\n"
            "Une variation qui sert de branche amène son entrée de branche.")
        self.b_importer.clicked.connect(self._importer)
        self.b_publier = QPushButton("←  Publier")
        self.b_publier.setToolTip(
            "Envoie les variations choisies du rapport vers la bibliothèque,\n"
            "pour les réutiliser dans un autre rapport.")
        self.b_publier.clicked.connect(self._publier)
        fleches.addWidget(self.b_importer)
        fleches.addWidget(self.b_publier)
        fleches.addStretch()
        milieu.addLayout(fleches)

        droite = QVBoxLayout()
        droite.addWidget(QLabel("Dans ce rapport"))
        self.lst_rapport = QListWidget()
        self.lst_rapport.setSelectionMode(QListWidget.ExtendedSelection)
        droite.addWidget(self.lst_rapport, 1)
        self.lbl_rapport = QLabel("")
        self.lbl_rapport.setStyleSheet(f"color:{TEXT_DIM};")
        droite.addWidget(self.lbl_rapport)
        milieu.addLayout(droite, 1)

        lay.addLayout(milieu, 1)

        bas = QHBoxLayout()
        bas.addStretch()
        b_fermer = QPushButton("Fermer")
        b_fermer.clicked.connect(self.accept)
        bas.addWidget(b_fermer)
        lay.addLayout(bas)

        self.reload()

    # ---- données -------------------------------------------------------------

    def chemin(self) -> str:
        return self.ed_path.text().strip()

    def reload(self):
        self.biblio = gm.read_biblio(self.chemin())
        au_rapport = set(self.config.get("variations") or {})

        self.lst_biblio.clear()
        for vid in self.biblio["variations"]:
            it = QListWidgetItem(vid + ("   (déjà dans ce rapport)"
                                        if vid in au_rapport else ""))
            it.setData(Qt.UserRole, vid)
            if vid in au_rapport:
                it.setForeground(Qt.gray)
            self.lst_biblio.addItem(it)

        self.lst_rapport.clear()
        dans_biblio = set(self.biblio["variations"])
        for vid in au_rapport:
            it = QListWidgetItem(vid + ("" if vid in dans_biblio
                                        else "   (pas encore publiée)"))
            it.setData(Qt.UserRole, vid)
            self.lst_rapport.addItem(it)

        n = len(self.biblio["variations"])
        p = Path(self.chemin()) if self.chemin() else None
        if p and not p.exists():
            self.lbl_biblio.setText("fichier absent — « Publier » le créera")
        else:
            self.lbl_biblio.setText(f"{n} variation(s)")
        self.lbl_rapport.setText(f"{len(au_rapport)} variation(s)")
        self.b_importer.setEnabled(n > 0)

    @staticmethod
    def _choisis(liste) -> list:
        return [i.data(Qt.UserRole) for i in liste.selectedItems()]

    # ---- actions -------------------------------------------------------------

    def _choisir(self):
        depart = self.chemin() or str(Path.home())
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Fichier de bibliothèque", depart, "JSON (*.json)",
            options=QFileDialog.DontConfirmOverwrite)
        if chemin:
            self.ed_path.setText(chemin)
            self.reload()

    def _importer(self):
        ids = self._choisis(self.lst_biblio)
        if not ids:
            QMessageBox.information(self, "Importer",
                                    "Choisis au moins une variation à gauche.")
            return
        deja = [v for v in ids if v in (self.config.get("variations") or {})]
        if deja and QMessageBox.question(
            self, "Écraser ?",
            "Ce rapport a déjà : " + ", ".join(deja)
            + "\n\nLes importer les REMPLACERA par la version de la "
              "bibliothèque. Continuer ?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        faits = gm.import_variations(self.config, self.biblio, ids,
                                     lambda *_: None)
        if faits:
            self.modifie = True
            QMessageBox.information(
                self, "Importé",
                f"{len(faits)} variation(s) ajoutée(s) au rapport :\n"
                + ", ".join(faits)
                + "\n\nPense à enregistrer le config.")
        self.reload()

    def _publier(self):
        ids = self._choisis(self.lst_rapport)
        if not ids:
            QMessageBox.information(self, "Publier",
                                    "Choisis au moins une variation à droite.")
            return
        if not self.chemin():
            QMessageBox.warning(self, "Publier",
                                "Indique d'abord un fichier de bibliothèque.")
            return
        faits = gm.export_variations(self.config, self.biblio, ids)
        gm.write_biblio(self.chemin(), self.biblio["variations"],
                        self.biblio.get("branches"))
        QMessageBox.information(
            self, "Publié",
            f"{len(faits)} variation(s) envoyée(s) dans la bibliothèque.")
        self.reload()
