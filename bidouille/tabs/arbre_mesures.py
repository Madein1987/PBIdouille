# -*- coding: utf-8 -*-
"""Onglet Mesures → « Arbre des mesures » : tout ce que la génération
produira, rangé comme cela se dérive.

    Weight                       (base, écrite à la main)
      Weight 7d avg              variation
      Weight YTD                 branche — devient une base
        Weight YTD 7d avg        variation en branche
      Weight cible               cible racine
        Weight cible écart       variation de la cible

L'arbre vient du générateur lui-même (generate_measures.generate en APERÇU,
qui n'écrit rien) : il ne peut pas montrer autre chose que ce que « Générer »
fera. Il suit le config EN MÉMOIRE — une variation ajoutée ou une table
paramètre filtrée s'y voit avant même d'enregistrer.

Le marqueur ◆ dit qu'une mesure est dans au moins une table paramètre de
champ ; l'infobulle dit lesquelles.
"""

from __future__ import annotations

from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.theme import ACCENT, BLUE, ORANGE, TEXT_DIM, YELLOW

COL_NOM, COL_PARAM, COL_ETAT = 0, 1, 2
MARQUEUR = "◆"
TYPES = {"base": "base — écrite à la main", "cible": "cible racine — écrite à la main",
         "variation": "variation", "branche": "branche — devient une base"}
COULEUR_ETAT = {"nouvelle": ACCENT, "modifiée": YELLOW}


class ArbreMesures(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._noeuds: list = []
        self._replies: set = set()      # mesures repliées par l'usager

        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        self.ed_filtre = QLineEdit()
        self.ed_filtre.setPlaceholderText("Filtrer (nom, variation, branche…)")
        self.ed_filtre.setClearButtonEnabled(True)
        self.ed_filtre.textChanged.connect(self._filtrer)
        self.chk_param = QCheckBox(MARQUEUR + " seulement")
        self.chk_param.setToolTip("Ne montrer que les mesures présentes dans au moins "
                                  "une table paramètre de champ.")
        self.chk_param.stateChanged.connect(self._filtrer)
        b_deplier = QPushButton("Tout déplier")
        b_deplier.clicked.connect(lambda: self._tout(True))
        b_replier = QPushButton("Tout replier")
        b_replier.clicked.connect(lambda: self._tout(False))
        haut.addWidget(self.ed_filtre, 1)
        haut.addWidget(self.chk_param)
        haut.addWidget(b_deplier)
        haut.addWidget(b_replier)
        v.addLayout(haut)

        self.lbl_resume = QLabel("")
        self.lbl_resume.setWordWrap(True)
        self.lbl_resume.setStyleSheet(f"color:{TEXT_DIM};")
        v.addWidget(self.lbl_resume)

        self.arbre = QTreeWidget()
        self.arbre.setColumnCount(3)
        self.arbre.setHeaderLabels(["Mesure", "Paramètres", "À la génération"])
        self.arbre.setUniformRowHeights(True)
        self.arbre.setAlternatingRowColors(False)
        h = self.arbre.header()
        h.setSectionResizeMode(COL_NOM, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_PARAM, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_ETAT, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        self.arbre.itemCollapsed.connect(lambda it: self._replies.add(it.data(0, Qt.UserRole)))
        self.arbre.itemExpanded.connect(lambda it: self._replies.discard(it.data(0, Qt.UserRole)))
        v.addWidget(self.arbre, 1)

        self.lbl_avis = QLabel("")
        self.lbl_avis.setWordWrap(True)
        self.lbl_avis.setStyleSheet(f"color:{YELLOW};")
        self.lbl_avis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_avis)

    # ---- API ---------------------------------------------------------------

    def afficher(self, noeuds, avis=None) -> None:
        """`noeuds` : stats["arbre"] du générateur. `avis` : ses ⚠ éventuels."""
        self._noeuds = list(noeuds or [])
        self._construire()
        avis = [a for a in (avis or []) if a]
        self.lbl_avis.setText("\n".join(avis[:6]) + ("\n…" if len(avis) > 6 else ""))
        self.lbl_avis.setVisible(bool(avis))

    def erreur(self, texte: str) -> None:
        self._noeuds = []
        self.arbre.clear()
        self.lbl_resume.setText("")
        self.lbl_avis.setText(texte)
        self.lbl_avis.setVisible(True)

    def element(self, nom):
        """L'élément de l'arbre d'une mesure (tests, navigation)."""
        trouves = self.arbre.findItems(nom, Qt.MatchExactly | Qt.MatchRecursive, COL_NOM)
        return trouves[0] if trouves else None

    # ---- construction ----------------------------------------------------------

    def _construire(self) -> None:
        self.arbre.setUpdatesEnabled(False)
        self.arbre.clear()
        enfants: dict = {}
        noms = {n["name"] for n in self._noeuds}
        for n in self._noeuds:
            parent = n.get("parent")
            enfants.setdefault(parent if parent in noms else None, []).append(n)

        def ajouter(parent_item, n):
            it = QTreeWidgetItem([n["name"], "", n.get("etat") or ""])
            it.setData(0, Qt.UserRole, n["name"])
            typ = n.get("type")
            details = [TYPES.get(typ, typ or "")]
            if n.get("variation") and typ != "branche":
                details.append("variation : " + n["variation"])
            if n.get("branche"):
                details.append("branche : " + n["branche"])
            if n.get("cible") and typ != "cible":
                details.append("de la cible")
            tables = n.get("tables") or []
            if tables:
                it.setText(COL_PARAM, MARQUEUR + (f" {len(tables)}" if len(tables) > 1 else ""))
                it.setForeground(COL_PARAM, QBrush(QColor(ACCENT)))
                it.setToolTip(COL_PARAM, "Dans les tables paramètre :\n  "
                              + "\n  ".join(tables))
                details.append("paramètres : " + ", ".join(tables))
            else:
                it.setToolTip(COL_PARAM, "Dans aucune table paramètre de champ.")
            it.setToolTip(COL_NOM, n["name"] + "\n" + "\n".join(details))
            if typ in ("base", "cible"):
                f = QFont(it.font(COL_NOM))
                f.setBold(True)
                it.setFont(COL_NOM, f)
            if typ == "branche":
                it.setForeground(COL_NOM, QBrush(QColor(BLUE)))
            elif typ == "cible":
                it.setForeground(COL_NOM, QBrush(QColor(ORANGE)))
            couleur = COULEUR_ETAT.get(n.get("etat"))
            it.setForeground(COL_ETAT, QBrush(QColor(couleur or TEXT_DIM)))
            if parent_item is None:
                self.arbre.addTopLevelItem(it)
            else:
                parent_item.addChild(it)
            for e in enfants.get(n["name"], []):
                ajouter(it, e)
            it.setExpanded(n["name"] not in self._replies)

        for n in enfants.get(None, []):
            ajouter(None, n)
        self.arbre.setUpdatesEnabled(True)
        self._filtrer()
        self._resumer()

    def _resumer(self) -> None:
        ns = self._noeuds
        bases = sum(1 for n in ns if n.get("type") == "base")
        gen = [n for n in ns if n.get("type") in ("variation", "branche")]
        par = {}
        for n in gen:
            par[n.get("etat")] = par.get(n.get("etat"), 0) + 1
        dans = sum(1 for n in ns if n.get("tables"))
        morceaux = [f"{bases} KPI", f"{len(gen)} mesures générées"]
        detail = ", ".join(f"{par[k]} {k}{'s' if par[k] > 1 else ''}"
                           for k in ("nouvelle", "modifiée", "inchangée") if par.get(k))
        if detail:
            morceaux[-1] += f" ({detail})"
        morceaux.append(f"{dans} dans les paramètres de champ ({MARQUEUR})")
        self.lbl_resume.setText(" · ".join(morceaux)
                                + " — aperçu du config en mémoire, rien n'est écrit.")

    # ---- filtre / pliage -------------------------------------------------------

    def _filtrer(self, *_) -> None:
        txt = self.ed_filtre.text().strip().lower()
        seul_param = self.chk_param.isChecked()

        def visite(it) -> bool:
            n_vis = 0
            for i in range(it.childCount()):
                n_vis += visite(it.child(i))
            nom = it.text(COL_NOM).lower()
            texte = (nom + " " + it.toolTip(COL_NOM).lower()) if txt else ""
            moi = ((not txt or txt in texte)
                   and (not seul_param or bool(it.text(COL_PARAM))))
            visible = moi or n_vis > 0
            it.setHidden(not visible)
            return visible

        for i in range(self.arbre.topLevelItemCount()):
            visite(self.arbre.topLevelItem(i))

    def _tout(self, ouvrir: bool) -> None:
        if ouvrir:
            self._replies.clear()
            self.arbre.expandAll()
        else:
            self.arbre.collapseAll()
            self._replies = {n["name"] for n in self._noeuds}
