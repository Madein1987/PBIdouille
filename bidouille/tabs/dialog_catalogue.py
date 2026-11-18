# -*- coding: utf-8 -*-
"""Bibliothèque de variations — un fichier GLOBAL où l'on pioche.

Le measures_config.json d'un rapport reste AUTONOME : ce qu'il contient est
exactement ce qui sera généré. La bibliothèque, elle, vit hors projet et garde
toutes les variations qu'on réutilise d'un rapport à l'autre.

  · Importer  : copie la variation de la bibliothèque VERS le rapport ;
  · Publier   : l'inverse, pour partager une variation qu'on vient d'écrire.

Rien à cocher ni à retenir projet par projet : une fois importée, la variation
appartient au rapport.

L'ORDRE de la bibliothèque est celui de son fichier : c'est celui dans
lequel on la parcourt, et dans lequel on importe. ↑ / ↓ / A → Z le
changent et l'écrivent aussitôt (comme « Publier »).
"""

from __future__ import annotations

import json
import unicodedata
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


def cle_alpha(nom: str) -> str:
    """Clé de tri A → Z : sans majuscules ni accents (« écart » se range
    avec les « e »). Un Δ n'a pas d'équivalent latin : il reste après."""
    return "".join(c for c in unicodedata.normalize("NFD", str(nom))
                   if unicodedata.category(c) != "Mn").casefold()


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
            "Importer copie la variation DANS le config de ce rapport, il "
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
        ordre = QHBoxLayout()
        self.b_monter = QPushButton("↑ Monter")
        self.b_monter.setToolTip("Monte la sélection d'un cran (un bloc sélectionné\n"
                                 "se déplace d'un seul tenant). L'ordre est écrit\n"
                                 "dans le fichier de bibliothèque.")
        self.b_monter.clicked.connect(lambda: self._deplacer(-1))
        self.b_descendre = QPushButton("↓ Descendre")
        self.b_descendre.setToolTip("Descend la sélection d'un cran. L'ordre est\n"
                                    "écrit dans le fichier de bibliothèque.")
        self.b_descendre.clicked.connect(lambda: self._deplacer(1))
        self.b_trier = QPushButton("Trier A → Z")
        self.b_trier.setToolTip("Trie toute la bibliothèque par nom, sans tenir\n"
                                "compte des majuscules ni des accents.\n"
                                "Remplace l'ordre actuel (on confirme).")
        self.b_trier.clicked.connect(self._trier)
        # les trois ensemble, sous la liste qu'ils ordonnent : tout au bout de
        # la rangée, le tri passait inaperçu
        ordre.addWidget(self.b_monter)
        ordre.addWidget(self.b_descendre)
        ordre.addWidget(self.b_trier)
        ordre.addStretch()
        gauche.addLayout(ordre)
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
        # l'ordre du CONFIG (celui des calculs dans le paramètre de champ) —
        # cette liste parcourait un set, donc un ordre quelconque
        for vid in (self.config.get("variations") or {}):
            it = QListWidgetItem(vid + ("" if vid in dans_biblio
                                        else "   (pas encore publiée)"))
            it.setData(Qt.UserRole, vid)
            self.lst_rapport.addItem(it)

        n = len(self.biblio["variations"])
        p = Path(self.chemin()) if self.chemin() else None
        if p and not p.exists():
            self.lbl_biblio.setText("fichier absent, « Publier » le créera")
        else:
            self.lbl_biblio.setText(f"{n} variation(s)")
        self.lbl_rapport.setText(f"{len(au_rapport)} variation(s)")
        self.b_importer.setEnabled(n > 0)
        for b in (self.b_monter, self.b_descendre, self.b_trier):
            b.setEnabled(n > 1 and bool(self.chemin()))

    @staticmethod
    def _choisis(liste) -> list:
        # dans l'ordre de la LISTE, pas celui des clics : on importe donc
        # dans l'ordre de la bibliothèque
        return [i.data(Qt.UserRole)
                for i in sorted(liste.selectedItems(), key=liste.row)]

    # ---- ordre de la bibliothèque -----------------------------------------

    def _deplacer(self, sens: int):
        """Monte (-1) ou descend (+1) la sélection d'un cran. Un bloc
        sélectionné se déplace d'un seul tenant et s'arrête au bord ; une
        sélection éparse avance chaque morceau d'un cran."""
        ordre = list(self.biblio["variations"])
        choisis = set(self._choisis(self.lst_biblio))
        if not choisis:
            return
        indices = (range(1, len(ordre)) if sens < 0
                   else range(len(ordre) - 2, -1, -1))
        for i in indices:
            j = i + sens
            if ordre[i] in choisis and ordre[j] not in choisis:
                ordre[i], ordre[j] = ordre[j], ordre[i]
        self._ordonner(ordre, choisis)

    def _trier(self):
        ordre = sorted(self.biblio["variations"], key=cle_alpha)
        if ordre == list(self.biblio["variations"]):
            return
        if QMessageBox.question(
            self, "Trier la bibliothèque",
            "Trier toutes les variations de A à Z ?\n\n"
            "L'ordre actuel sera remplacé, pour tout le monde, si la "
            "bibliothèque est partagée.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        self._ordonner(ordre, set(self._choisis(self.lst_biblio)))

    def _ordonner(self, ordre: list, choisis=()):
        """Écrit la bibliothèque dans `ordre`, puis la RELIT : ce qui
        s'affiche est ce qui est sur le disque. La sélection est gardée."""
        variations = self.biblio["variations"]
        if ordre == list(variations):
            return
        self.biblio["variations"] = {vid: variations[vid] for vid in ordre}
        try:
            gm.write_biblio(self.chemin(), self.biblio["variations"],
                            self.biblio.get("branches"))
        except OSError as e:
            QMessageBox.warning(self, "Bibliothèque",
                                f"Ordre NON enregistré : {e}")
        self.reload()
        premier = None
        for i in range(self.lst_biblio.count()):
            it = self.lst_biblio.item(i)
            if it.data(Qt.UserRole) in choisis:
                it.setSelected(True)
                premier = premier or it
        if premier is not None:
            self.lst_biblio.scrollToItem(premier)

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
                                    "Choisir au moins une variation à gauche.")
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
                + "\n\nPenser à enregistrer le config.")
        self.reload()

    def _publier(self):
        ids = self._choisis(self.lst_rapport)
        if not ids:
            QMessageBox.information(self, "Publier",
                                    "Choisir au moins une variation à droite.")
            return
        if not self.chemin():
            QMessageBox.warning(self, "Publier",
                                "Indiquer d'abord un fichier de bibliothèque.")
            return
        faits = gm.export_variations(self.config, self.biblio, ids)
        gm.write_biblio(self.chemin(), self.biblio["variations"],
                        self.biblio.get("branches"))
        QMessageBox.information(
            self, "Publié",
            f"{len(faits)} variation(s) envoyée(s) dans la bibliothèque.")
        self.reload()
