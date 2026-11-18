# -*- coding: utf-8 -*-
"""Mesures → Variations, « Jetons disponibles… » : ce que vaut chaque jeton.

Une fenêtre non modale, à garder ouverte à côté du DAX. On choisit une mesure
(un KPI ou une cible) et une branche ; chaque jeton affiche ce qu'il deviendra,
et d'où il vient : quel réglage le change. Double-clic : le jeton part dans le
DAX, ou, pour une colonne pas encore déclarée, ⚙ Réglages s'ouvre pour la
déclarer.

Les valeurs viennent de generate_measures.apercu_jetons, donc de la génération
elle-même. Les couleurs sont celles de l'éditeur : {…} en bleu, <<…>> en vert.
"""

from __future__ import annotations

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.theme import ACCENT, BLUE, TEXT, TEXT_DIM, TEXT_MUTED, YELLOW

COL_JETON, COL_VALEUR, COL_ROLE, COL_OU = 0, 1, 2, 3
ROLE_COLONNE = Qt.UserRole + 1            # une colonne à déclarer
POLICE_CODE = QFont("Consolas", 9)

# où se règlent les choses : les noms exacts de ⚙ Réglages
R_GENERATION = "⚙ Réglages → Génération"
R_BRANCHES = "⚙ Réglages → Branches"
R_CIBLES = "⚙ Réglages → Mesures cibles"
R_ATTRIBUTS = "⚙ Réglages → Excel des indicateurs → Attributs codés en dur"

ROLES = {
    "{base}": "le nom de la mesure traitée",
    "{baseRef}": "la même mesure, en référence DAX",
    "{kpi}": "le nom du KPI, sans branche ni cible",
    "{kpiRef}": "la mesure du KPI, dans cette branche",
    "{branch}": "le nom de la branche (rien en Réel)",
    "{variation}": "l'identifiant de la variation ouverte",
    "{date}": "la colonne de dates",
    "{deltaScale}": "100 si la base est en %, sinon 1",
    "{baseFormatString}": "le format de la base, en texte DAX",
    "<<tables>>": "les tables du KPI, en liste",
    "<<allTables>>": "ALL() sur chaque table du KPI",
    "<<removeFilters>>": "REMOVEFILTERS() sur chaque table du KPI",
    "<<each ALLSELECTED({table})>>": "la fonction, répétée par table",
}


def ou_se_regle(jeton: str, b: dict) -> str:
    """Le réglage qui décide de ce jeton, pour cette mesure."""
    base = (R_CIBLES if b["cible"] else
            R_BRANCHES if b["branche"] else R_GENERATION + " → sourceFolder")
    return {
        "{base}": base,
        "{baseRef}": base,
        "{kpi}": R_GENERATION + " → sourceFolder",
        "{kpiRef}": R_BRANCHES if b["branche"] else R_GENERATION + " → sourceFolder",
        "{branch}": R_BRANCHES,
        "{variation}": "la liste des variations, à gauche",
        "{date}": R_GENERATION + " → dateColumn",
        "{deltaScale}": "le format de la mesure, dans Power BI",
        "{baseFormatString}": "le format de la mesure, dans Power BI",
    }.get(jeton, "")


class ExplorateurJetons(QWidget):
    besoin = Signal()           # le panneau s'affiche : il lui faut ses données
    inserer = Signal(str)       # double-clic sur un jeton
    declarer = Signal(str)      # déclarer une colonne ("" : ouvrir la page)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._donnees: dict = {}
        self._variation = ""

        v = QVBoxLayout(self)
        intro = QLabel("Choisis une mesure : chaque jeton affiche ce qu'il deviendra "
                       "dans le DAX, et le réglage qui le décide.")
        intro.setWordWrap(True)
        v.addWidget(intro)

        haut = QHBoxLayout()
        haut.addWidget(QLabel("Mesure :"))
        self.cmb_base = QComboBox()
        self.cmb_base.setToolTip("Les KPI, et sous chacun ses cibles.")
        haut.addWidget(self.cmb_base, 1)
        haut.addWidget(QLabel("Branche :"))
        self.cmb_branche = QComboBox()
        self.cmb_branche.setMinimumWidth(110)
        haut.addWidget(self.cmb_branche)
        v.addLayout(haut)

        self.lbl_note = QLabel("")
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"color:{TEXT_DIM};")
        v.addWidget(self.lbl_note)

        self.arbre = QTreeWidget()
        self.arbre.setColumnCount(4)
        self.arbre.setHeaderLabels(["Jeton", "Valeur ici", "Ce que c'est", "Où ça se règle"])
        self.arbre.setRootIsDecorated(False)
        self.arbre.setUniformRowHeights(True)
        h = self.arbre.header()
        h.setSectionResizeMode(COL_JETON, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_VALEUR, QHeaderView.Interactive)
        h.setSectionResizeMode(COL_ROLE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_OU, QHeaderView.Stretch)
        self.arbre.setColumnWidth(COL_VALEUR, 250)
        self.arbre.itemDoubleClicked.connect(self._on_double_clic)
        v.addWidget(self.arbre, 1)

        bas = QHBoxLayout()
        aide = QLabel("Double-clic : insère le jeton dans le DAX.")
        aide.setStyleSheet(f"color:{TEXT_DIM};")
        bas.addWidget(aide, 1)
        self.btn_declarer = QPushButton("⚙ Déclarer un attribut…")
        self.btn_declarer.setToolTip(R_ATTRIBUTS)
        self.btn_declarer.clicked.connect(lambda: self.declarer.emit(""))
        bas.addWidget(self.btn_declarer)
        v.addLayout(bas)

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

    def _ligne(self, jeton, valeur, role, ou, couleur, vide="", attenue=False):
        it = QTreeWidgetItem([jeton, valeur if valeur is not None else vide, role, ou])
        it.setFont(COL_JETON, POLICE_CODE)
        it.setFont(COL_VALEUR, POLICE_CODE)
        it.setForeground(COL_JETON, QBrush(QColor(TEXT_MUTED if attenue else couleur)))
        it.setForeground(COL_VALEUR, QBrush(QColor(
            YELLOW if valeur is None else (TEXT_MUTED if attenue else TEXT))))
        it.setForeground(COL_ROLE, QBrush(QColor(TEXT_DIM)))
        it.setForeground(COL_OU, QBrush(QColor(TEXT_MUTED)))
        it.setToolTip(COL_VALEUR, valeur if valeur is not None else vide)
        it.setToolTip(COL_OU, ou)
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
        self._groupe("{…}  Toujours disponibles")
        for j, role in ROLES.items():
            if j.startswith("{"):
                v = self._variation if j == "{variation}" else val.get(j)
                it = self._ligne(j, v if v is not None else "", role, ou_se_regle(j, b), BLUE)
                it.setData(COL_JETON, Qt.UserRole, j)

        attributs = self._donnees.get("attributs") or []
        declares = [a for a in attributs if a["declare"]]
        libres = [a for a in attributs if not a["declare"]]
        self._groupe("<<…>>  Attributs de TD_Indicateurs, prêts à utiliser")
        if not declares:
            self._ligne("", "", "aucun pour l'instant", R_ATTRIBUTS, ACCENT)
        for a in declares:
            it = self._ligne(a["jeton"], val.get(a["jeton"]), f"la colonne {a['colonne']}",
                             R_ATTRIBUTS, ACCENT, vide="cellule vide : pas de mesure")
            it.setData(COL_JETON, Qt.UserRole, a["jeton"])
        if libres:
            self._groupe("Colonnes de TD_Indicateurs pas encore déclarées")
            for a in libres:
                it = self._ligne(a["jeton"], val.get(a["jeton"]), f"la colonne {a['colonne']}",
                                 "double-clic pour la déclarer", ACCENT,
                                 vide="cellule vide", attenue=True)
                it.setData(COL_JETON, ROLE_COLONNE, a["colonne"])

        portee = self._donnees.get("portee") or []
        if portee:                  # un ancien config (kpiTables) les utilise encore
            self._groupe("<<…>>  Tables du KPI (ancien réglage kpiTables du config)")
            for j in portee:
                it = self._ligne(j, val.get(j), ROLES.get(j, ""), "JSON brut → kpiTables",
                                 ACCENT, vide="aucune table pour ce KPI")
                it.setData(COL_JETON, Qt.UserRole, j)
        self.arbre.resizeColumnToContents(COL_JETON)

    @staticmethod
    def _note(b) -> str:
        if b["cible"]:
            return (f"« {b['nom']} » est une cible : {{base}} et {{baseRef}} la désignent, "
                    f"{{kpi}} et {{kpiRef}} désignent son KPI, {b['kpi']}. "
                    "Ses attributs sont ceux de la ligne de ce KPI.")
        if b["branche"]:
            return (f"En {b['branche']} : {{base}} et {{kpiRef}} suivent la branche, "
                    "{kpi} reste le KPI.")
        return f"« {b['nom']} » est un KPI : {{base}} et {{kpi}} donnent le même nom."

    def _on_double_clic(self, it, _col=0) -> None:
        colonne = it.data(COL_JETON, ROLE_COLONNE)
        if colonne:
            self.declarer.emit(colonne)
            return
        jeton = it.data(COL_JETON, Qt.UserRole)
        if jeton:
            self.inserer.emit(jeton)


class FenetreJetons(QDialog):
    """La fenêtre de l'explorateur : non modale, on écrit le DAX à côté."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jetons disponibles")
        self.setModal(False)
        self.resize(1080, 680)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.explorateur = ExplorateurJetons(self)
        v.addWidget(self.explorateur)

    def montrer(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
