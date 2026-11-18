# -*- coding: utf-8 -*-
"""Mesures → Variations, « Jetons disponibles » : ce que vaut chaque jeton.

On choisit un KPI ou une cible, et une branche ; la liste montre la valeur de
chaque {jeton}, de chaque <<attribut>> de TD_Indicateurs et des jetons de
portée (les tables du KPI). Double-clic : le jeton part dans l'éditeur DAX.

Les valeurs viennent de generate_measures.apercu_jetons, donc de la génération
elle-même. Les couleurs sont celles de l'éditeur : {…} en bleu, <<…>> en vert.
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.theme import ACCENT, BLUE, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW, police_code

COL_JETON, COL_VALEUR, COL_ROLE = 0, 1, 2

ROLES = {
    "{base}": "nom de la mesure traitée",
    "{baseRef}": "la même, en référence DAX",
    "{kpi}": "le KPI racine : ni branche, ni cible",
    "{kpiRef}": "la mesure du KPI, dans la branche courante",
    "{branch}": "la branche (rien en Réel, espace compris)",
    "{variation}": "l'id de la variation ouverte",
    "{date}": "la colonne de dates du modèle",
    "{deltaScale}": "100 si le format de la base est un %, sinon 1",
    "{baseFormatString}": "le format de la base, en chaîne DAX",
    "<<tables>>": "les tables du KPI, en liste",
    "<<allTables>>": "ALL() sur chaque table du KPI",
    "<<removeFilters>>": "REMOVEFILTERS() sur chaque table du KPI",
    "<<each ALLSELECTED({table})>>": "ta fonction, répétée pour chaque table",
}


class ExplorateurJetons(QWidget):
    besoin = Signal()           # le panneau s'affiche : il lui faut ses données
    inserer = Signal(str)       # double-clic sur un jeton

    def __init__(self, parent=None):
        super().__init__(parent)
        self._donnees: dict = {}
        self._variation = ""

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        haut = QHBoxLayout()
        haut.addWidget(QLabel("KPI ou cible :"))
        self.cmb_base = QComboBox()
        self.cmb_base.setToolTip("Les KPI, et sous chacun ses cibles.")
        haut.addWidget(self.cmb_base, 1)
        haut.addWidget(QLabel("branche :"))
        self.cmb_branche = QComboBox()
        haut.addWidget(self.cmb_branche)
        v.addLayout(haut)

        self.lbl_note = QLabel("")
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"color:{TEXT_DIM};")
        v.addWidget(self.lbl_note)

        self.arbre = QTreeWidget()
        self.arbre.setColumnCount(3)
        self.arbre.setHeaderLabels(["Jeton", "Vaut ici", "Ce que c'est"])
        self.arbre.setRootIsDecorated(False)
        self.arbre.setUniformRowHeights(True)
        self.arbre.setMinimumHeight(190)
        self.arbre.setToolTip("Double-clic : insère le jeton dans le DAX.")
        h = self.arbre.header()
        h.setSectionResizeMode(COL_JETON, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_VALEUR, QHeaderView.Interactive)
        h.setSectionResizeMode(COL_ROLE, QHeaderView.Stretch)
        self.arbre.setColumnWidth(COL_VALEUR, 230)
        police_code(self.arbre, petit=True)
        self.arbre.itemDoubleClicked.connect(self._on_double_clic)
        v.addWidget(self.arbre, 1)

        self.cmb_base.currentIndexChanged.connect(self._remplir)
        self.cmb_branche.currentIndexChanged.connect(self._remplir)

    # ---- API ---------------------------------------------------------------

    def afficher(self, donnees, libelle_reel="Réel") -> None:
        """`donnees` : generate_measures.apercu_jetons. Garde le choix en cours."""
        self._donnees = donnees or {}
        bases = self._donnees.get("bases") or []
        base, branche = self.choix()
        kpis: list = []
        for b in bases:
            if b["kpi"] not in kpis:
                kpis.append(b["kpi"])
        racines = {b["nom"]: b for b in bases if not b["branche"]}
        # chaque cible juste sous son KPI
        ordre = sorted(racines.values(), key=lambda b: (kpis.index(b["kpi"]), b["cible"], b["nom"]))
        branches = list(dict.fromkeys(b["branche"] for b in bases if b["branche"]))

        for cmb in (self.cmb_base, self.cmb_branche):
            cmb.blockSignals(True)
            cmb.clear()
        for b in ordre:
            self.cmb_base.addItem(("    " if b["cible"] else "") + b["nom"], b["nom"])
        self.cmb_branche.addItem(libelle_reel or "Réel", "")
        for b in branches:
            self.cmb_branche.addItem(b, b)
        self.cmb_base.setCurrentIndex(max(0, self.cmb_base.findData(base)))
        self.cmb_branche.setCurrentIndex(max(0, self.cmb_branche.findData(branche)))
        for cmb in (self.cmb_base, self.cmb_branche):
            cmb.blockSignals(False)
        self._remplir()

    def erreur(self, texte: str) -> None:
        self._donnees = {}
        self.cmb_base.clear()
        self.cmb_branche.clear()
        self.arbre.clear()
        self.lbl_note.setText(texte)

    def set_variation(self, vid: str) -> None:
        self._variation = vid or ""
        self._remplir()

    def choix(self) -> tuple:
        return self.cmb_base.currentData() or "", self.cmb_branche.currentData() or ""

    def choisir(self, base: str, branche: str = "") -> bool:
        i, j = self.cmb_base.findData(base), self.cmb_branche.findData(branche)
        if i < 0 or j < 0:
            return False
        self.cmb_base.setCurrentIndex(i)
        self.cmb_branche.setCurrentIndex(j)
        return True

    def valeur(self, jeton: str):
        """Ce que vaut `jeton` pour le choix en cours (tests)."""
        b = self._courante()
        return b["valeurs"].get(jeton) if b else None

    # ---- affichage ---------------------------------------------------------

    def showEvent(self, ev):
        super().showEvent(ev)
        self.besoin.emit()

    def _courante(self):
        base, branche = self.choix()
        return next((b for b in self._donnees.get("bases") or []
                     if b["nom"] == base and b["branche"] == branche), None)

    def _groupe(self, titre) -> QTreeWidgetItem:
        g = QTreeWidgetItem([titre])
        f = QFont(g.font(0))
        f.setBold(True)
        g.setFont(COL_JETON, f)
        g.setForeground(COL_JETON, QBrush(QColor(TEXT_DIM)))
        g.setFlags(Qt.ItemIsEnabled)
        self.arbre.addTopLevelItem(g)
        g.setFirstColumnSpanned(True)
        return g

    def _ligne(self, jeton, valeur, role, couleur, vide="", attenue=False):
        it = QTreeWidgetItem([jeton, valeur if valeur is not None else vide, role])
        it.setData(COL_JETON, Qt.UserRole, jeton)
        it.setForeground(COL_JETON, QBrush(QColor(TEXT_MUTED if attenue else couleur)))
        it.setForeground(COL_VALEUR, QBrush(QColor(
            YELLOW if valeur is None else (TEXT_MUTED if attenue else TEXT))))
        it.setForeground(COL_ROLE, QBrush(QColor(TEXT_MUTED)))
        it.setToolTip(COL_VALEUR, valeur if valeur is not None else vide)
        self.arbre.addTopLevelItem(it)
        return it

    def _remplir(self, *_) -> None:
        self.arbre.clear()
        b = self._courante()
        if b is None:
            base, branche = self.choix()
            self.lbl_note.setText(f"« {base} » n'a pas de mesure dans la branche {branche}."
                                  if base else "")
            return
        self.lbl_note.setText(self._note(b))
        val = b["valeurs"]
        self._groupe("{…}  toujours disponibles")
        for j, role in ROLES.items():
            if j.startswith("{"):
                v = self._variation if j == "{variation}" else val.get(j)
                self._ligne(j, v if v is not None else "", role, BLUE)

        attributs = self._donnees.get("attributs") or []
        self._groupe("<<…>>  n'importe quelle colonne de TD_Indicateurs")
        for a in attributs:
            role = f"colonne {a['colonne']}"
            if not a["declare"]:
                role += " : à déclarer dans ⚙ Réglages"
            self._ligne(a["jeton"], val.get(a["jeton"]), role, ACCENT,
                        vide="vide : pas de mesure pour ce KPI",
                        attenue=not a["declare"])

        self._groupe("<<…>>  les tables du KPI (portée)")
        for j in self._donnees.get("portee") or []:
            self._ligne(j, val.get(j), ROLES.get(j, ""), ACCENT,
                        vide="aucune table déclarée pour ce KPI")

    @staticmethod
    def _note(b) -> str:
        if b["cible"]:
            return (f"Cible : {{base}} et {{baseRef}} visent « {b['mesure']} », {{kpi}} et "
                    f"{{kpiRef}} visent son KPI. {{kpiRef}} - {{baseRef}} donne l'écart "
                    "réel moins cible. Ses <<attributs>> sont ceux de son KPI.")
        if b["branche"]:
            return ("En branche, {base} et {kpiRef} suivent la branche ; "
                    "{kpi} reste le KPI racine.")
        return "Pour un KPI en Réel, {base} et {kpi} sont le même nom."

    def _on_double_clic(self, it, _col=0) -> None:
        jeton = it.data(COL_JETON, Qt.UserRole)
        if jeton:
            self.inserer.emit(jeton)
