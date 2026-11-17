# -*- coding: utf-8 -*-
"""Les schémas du guide, dans l'app : comment les variations se ramifient,
comment le formatage se propage…

Les images (bidouille\\aide\\*.png) sont les diapos du guide PowerPoint,
exportées par docs\\sources\\exporter_aide.ps1 : une seule source, le guide et
l'app montrent le même dessin. La fenêtre n'est PAS modale — on la garde
ouverte à côté pendant qu'on travaille — et il n'y en a qu'une : la rouvrir
depuis un autre bouton la ramène devant, sur la bonne page.
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QPixmap
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from core.theme import TEXT_DIM

AIDE = Path(__file__).resolve().parent.parent / "aide"

# (clé, titre dans la liste, image) — même table que docs\sources\exporter_aide.ps1
PAGES = [
    ("variations", "Les variations se ramifient", "variations.png"),
    ("parametres", "Les paramètres de champ", "parametres_champ.png"),
    ("jetons", "Les jetons du DAX", "jetons.png"),
    ("propagation", "Le formatage se propage", "propagation.png"),
    ("propagation_carte", "La carte se propage aussi", "propagation_carte.png"),
    ("gabarits", "Qui copie qui : gabarits et groupes", "gabarits.png"),
]


class _Image(QLabel):
    """L'image à la taille de la fenêtre, proportions gardées."""

    def __init__(self):
        super().__init__()
        self._pix = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def montrer(self, chemin: Path) -> None:
        pix = QPixmap(str(chemin)) if chemin.exists() else QPixmap()
        if pix.isNull():
            self._pix = None
            self.setPixmap(QPixmap())
            self.setText("Image absente : " + chemin.name + "\n"
                         "(docs\\sources\\exporter_aide.ps1 la régénère depuis le guide)")
            return
        self._pix = pix
        self._ajuster()

    def _ajuster(self) -> None:
        if self._pix is not None:
            self.setPixmap(self._pix.scaled(self.size(), Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._ajuster()


class GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guide · comment ça marche")
        self.setModal(False)
        self.resize(1180, 640)
        h = QHBoxLayout(self)
        gauche = QVBoxLayout()
        self.liste = QListWidget()
        self.liste.setMaximumWidth(230)
        for _, titre, _ in PAGES:
            self.liste.addItem(titre)
        self.liste.currentRowChanged.connect(self._page)
        gauche.addWidget(self.liste, 1)
        note = QLabel("Les mêmes schémas que le guide PowerPoint (docs\\).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_DIM};")
        gauche.addWidget(note)
        h.addLayout(gauche)
        self.image = _Image()
        h.addWidget(self.image, 1)
        self.liste.setCurrentRow(0)

    def aller(self, cle: str) -> None:
        for i, (c, _, _) in enumerate(PAGES):
            if c == cle:
                self.liste.setCurrentRow(i)
                return

    def _page(self, i) -> None:
        if 0 <= i < len(PAGES):
            self.image.montrer(AIDE / PAGES[i][2])


def ouvrir_guide(parent, cle: str = "") -> GuideDialog:
    """Ouvre (ou ramène devant) LA fenêtre du guide de la fenêtre principale,
    sur la page `cle` si elle est donnée."""
    hote = parent.window() if parent is not None else None
    dlg = getattr(hote, "_guide_dialog", None)
    if dlg is None:
        dlg = GuideDialog(hote)
        if hote is not None:
            hote._guide_dialog = dlg
    if cle:
        dlg.aller(cle)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg


def bouton_schema(parent, cle: str, texte: str = "Schéma") -> QToolButton:
    """Petit lien « ▣ Schéma » posé à côté d'une fonction : ouvre le guide sur
    le dessin qui l'explique."""
    titre = next((t for c, t, _ in PAGES if c == cle), "")
    b = QToolButton(parent)
    b.setText("▣ " + texte)
    b.setAutoRaise(True)
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip("Ouvre le schéma « " + titre + " » du guide.")
    b.clicked.connect(lambda: ouvrir_guide(b, cle))
    return b
