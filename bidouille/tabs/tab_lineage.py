# -*- coding: utf-8 -*-
"""Onglet « Sources de données » : d'où vient chaque table du rapport ouvert.

Deux regroupements :
  · PAR SOURCE (défaut) — une ligne par source distincte (l'Excel des
    indicateurs, la base ODBC, un CSV…) et, dessous, les tables qui la lisent.
    C'est la question qu'on se pose en premier : « de quoi ce rapport
    dépend-il ? » ;
  · PAR TABLE — chaque table et ce qu'elle lit.

Les tables calculées (DAX : paramètres de champ, calendrier…) ne lisent rien
de l'extérieur : elles sont rangées à part, repliées.

Un fichier LOCAL cité par une source qui n'existe plus est signalé ⚠ : c'est
ce qui casse une actualisation sur un autre poste. Lecture seule — l'onglet
lit les .tmdl du modèle (moteurs/lineage.py) et n'écrit rien dans le projet ;
« Exporter CSV… » écrit seulement là où on le lui dit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QFont, QGuiApplication
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import lineage as lg
from core.journal import Journal
from core.theme import BLUE, TEXT_DIM, TEXT_MUTED, YELLOW

COL_NOM, COL_MODE, COL_DETAIL, COL_CONNECTEUR = 0, 1, 2, 3
PAR_SOURCE, PAR_TABLE = "source", "table"
CALCULEES = "Tables calculées (DAX)"


def _fichier_manquant(detail: str) -> bool:
    p = lg.chemin_local(detail)
    return p is not None and not p.exists()


class LineageTab(QWidget):
    def __init__(self, journal=None):
        super().__init__()
        self.journal = journal or Journal()
        self._pbip = None
        self._pending = False           # analyse à faire à la prochaine visite
        self._res: dict = {}

        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        self.ed_filtre = QLineEdit()
        self.ed_filtre.setPlaceholderText("Filtrer (table, chemin, serveur, connecteur…)")
        self.ed_filtre.setClearButtonEnabled(True)
        self.ed_filtre.textChanged.connect(self._filtrer)
        self.cmb_vue = QComboBox()
        self.cmb_vue.addItem("Regrouper par source", PAR_SOURCE)
        self.cmb_vue.addItem("Regrouper par table", PAR_TABLE)
        self.cmb_vue.currentIndexChanged.connect(lambda *_: self._construire())
        self.btn_export = QPushButton("Exporter CSV…")
        self.btn_export.setToolTip("Une ligne par partition et par connecteur "
                                   "(séparateur ;), comme scan_lineage.py.")
        self.btn_export.clicked.connect(self._exporter)
        b_relire = QPushButton("↻ Relire")
        b_relire.setToolTip("Relit les fichiers du modèle.")
        b_relire.clicked.connect(self.reload)
        haut.addWidget(self.ed_filtre, 1)
        haut.addWidget(self.cmb_vue)
        haut.addWidget(self.btn_export)
        haut.addWidget(b_relire)
        v.addLayout(haut)

        self.lbl_resume = QLabel("")
        self.lbl_resume.setWordWrap(True)
        self.lbl_resume.setStyleSheet(f"color:{TEXT_DIM};")
        self.lbl_resume.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_resume)

        self.arbre = QTreeWidget()
        self.arbre.setColumnCount(4)
        self.arbre.setHeaderLabels(["Source / table", "Mode", "Détail", "Connecteur M"])
        self.arbre.setUniformRowHeights(True)
        h = self.arbre.header()
        h.setSectionResizeMode(COL_NOM, QHeaderView.Interactive)
        h.setSectionResizeMode(COL_MODE, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(COL_DETAIL, QHeaderView.Stretch)
        h.setSectionResizeMode(COL_CONNECTEUR, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        self.arbre.setColumnWidth(COL_NOM, 300)
        self.arbre.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbre.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.arbre, 1)

        self.lbl_avis = QLabel("")
        self.lbl_avis.setWordWrap(True)
        self.lbl_avis.setStyleSheet(f"color:{YELLOW};")
        self.lbl_avis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_avis.hide()
        v.addWidget(self.lbl_avis)

    # ---- projet (différé comme ChopChop : changer de projet reste instantané) --

    def set_project(self, project):
        self._pbip = str(project.pbip)
        self._pending = True
        if self.isVisible():
            self._analyser()

    def reload(self):
        if not self._pbip:
            return
        self._pending = True
        if self.isVisible():
            self._analyser()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._analyser()

    def _analyser(self):
        self._pending = False
        try:
            self._res = lg.scan_projet(self._pbip)
        except (OSError, UnicodeDecodeError) as e:
            self._res = {"lignes": [], "erreur": f"lecture impossible : {e}"}
        self._construire()

    # ---- construction ----------------------------------------------------------

    def lignes(self) -> list:
        return list(self._res.get("lignes") or [])

    def _item(self, textes, donnees=None) -> QTreeWidgetItem:
        it = QTreeWidgetItem([str(t) for t in textes])
        it.setData(COL_NOM, Qt.UserRole, donnees)
        for c, t in enumerate(textes):
            if t:
                it.setToolTip(c, str(t))
        return it

    def _marquer_manquant(self, it, detail) -> bool:
        if _fichier_manquant(detail):
            it.setText(COL_DETAIL, "⚠ " + detail)
            it.setForeground(COL_DETAIL, QBrush(QColor(YELLOW)))
            it.setToolTip(COL_DETAIL, detail + "\n\n⚠ Fichier introuvable sur ce poste : "
                          "l'actualisation échouera ici.")
            return True
        return False

    def _construire(self):
        self.arbre.setUpdatesEnabled(False)
        self.arbre.clear()
        lignes = self.lignes()
        gras = QFont(self.arbre.font())
        gras.setBold(True)
        manquants = 0
        calculees = [l for l in lignes if l["genre"] in (lg.CALCULEE, lg.AUCUN)]

        if self.cmb_vue.currentData() == PAR_TABLE:
            par_table: dict = {}
            for l in lignes:
                if l["genre"] in (lg.SOURCE, lg.LIVE):
                    par_table.setdefault(l["table"] or "(rapport)", []).append(l)
            for table in sorted(par_table, key=str.lower):
                ls = par_table[table]
                modes = sorted({l["mode"] for l in ls if l["mode"]})
                top = self._item([table, ", ".join(modes), "", ""], table)
                top.setFont(COL_NOM, gras)
                for l in ls:
                    detail = " · ".join(d for d in (l["detail1"], l["detail2"]) if d)
                    it = self._item([l["famille"] or l["connecteur"], "", detail,
                                     l["connecteur"]], detail)
                    if l["table"] == lg.EXPRESSIONS:
                        it.setText(COL_NOM, f'{l["famille"]}  ({l["partition"]})')
                    manquants += self._marquer_manquant(it, l["detail1"])
                    top.addChild(it)
                self.arbre.addTopLevelItem(top)
                top.setExpanded(True)
        else:
            for s in lg.sources(lignes):
                tables = sorted({l["table"] for l in s["lignes"] if l["table"]}, key=str.lower)
                detail = " · ".join(d for d in (s["detail1"], s["detail2"]) if d)
                n = len(tables)
                titre = s["famille"] or s["connecteur"]
                if n:
                    titre += f"  —  {n} table{'s' if n > 1 else ''}"
                top = self._item([titre, "", detail, s["connecteur"]], detail)
                top.setFont(COL_NOM, gras)
                top.setForeground(COL_NOM, QBrush(QColor(BLUE)))
                manquants += self._marquer_manquant(top, s["detail1"])
                for l in sorted(s["lignes"], key=lambda l: l["table"].lower()):
                    nom = l["table"]
                    if l["partition"] and l["partition"] != l["table"]:
                        nom += f"  ({l['partition']})"
                    top.addChild(self._item([nom, l["mode"], "", ""], l["table"]))
                self.arbre.addTopLevelItem(top)
                top.setExpanded(True)

        if calculees:
            top = self._item([CALCULEES + f"  —  {len(calculees)}", "", "", ""])
            top.setToolTip(COL_NOM, "Paramètres de champ, calendrier, tables de mesures…\n"
                                    "Calculées par le modèle : elles ne lisent rien de "
                                    "l'extérieur.")
            top.setForeground(COL_NOM, QBrush(QColor(TEXT_MUTED)))
            for l in sorted(calculees, key=lambda l: l["table"].lower()):
                it = self._item([l["table"], l["mode"], "", l["connecteur"]], l["table"])
                it.setForeground(COL_NOM, QBrush(QColor(TEXT_MUTED)))
                top.addChild(it)
            self.arbre.addTopLevelItem(top)
            top.setExpanded(False)

        self.arbre.setUpdatesEnabled(True)
        self._resumer(manquants)
        self._filtrer()

    def _resumer(self, manquants: int):
        res = self._res
        lignes = self.lignes()
        if res.get("erreur"):
            self.lbl_resume.setText("")
            self.lbl_avis.setText(res["erreur"])
            self.lbl_avis.show()
            return
        if res.get("live"):
            self.lbl_resume.setText(f"Connexion LIVE au modèle « {res.get('modele')} » — "
                                    "ses sources sont dans le modèle publié, pas dans ce projet.")
        else:
            n_src = len(lg.sources(lignes))
            tables = {l["table"] for l in lignes if l["table"] and l["table"] != lg.EXPRESSIONS}
            calc = {l["table"] for l in lignes if l["genre"] in (lg.CALCULEE, lg.AUCUN)}
            morceaux = [f"Modèle local : {res.get('modele')}",
                        f"{n_src} source{'s' if n_src > 1 else ''}",
                        f"{len(tables)} tables dont {len(calc)} calculées"]
            params = res.get("parametres") or {}
            if params:
                morceaux.append(f"{len(params)} paramètre{'s' if len(params) > 1 else ''} M")
            self.lbl_resume.setText(" · ".join(morceaux) + " — lecture seule.")
        avis = []
        if manquants:
            avis.append(f"⚠ {manquants} fichiers locaux introuvables sur ce poste"
                        if manquants > 1 else "⚠ 1 fichier local introuvable sur ce poste")
            avis[-1] += " : l'actualisation échouera ici (survol du chemin pour le détail)."
        self.lbl_avis.setText("\n".join(avis))
        self.lbl_avis.setVisible(bool(avis))

    # ---- filtre ----------------------------------------------------------------

    def _filtrer(self, *_):
        txt = self.ed_filtre.text().strip().lower()

        def texte(it) -> str:
            return " ".join(it.text(c) for c in range(self.arbre.columnCount())).lower()

        for i in range(self.arbre.topLevelItemCount()):
            top = self.arbre.topLevelItem(i)
            moi = not txt or txt in texte(top)
            n_vis = 0
            for j in range(top.childCount()):
                enfant = top.child(j)
                vis = moi or txt in texte(enfant)
                enfant.setHidden(not vis)
                n_vis += vis
            top.setHidden(not (moi or n_vis))

    # ---- actions ---------------------------------------------------------------

    def _menu(self, pos):
        it = self.arbre.itemAt(pos)
        if it is None:
            return
        valeur = it.data(COL_NOM, Qt.UserRole) or it.text(COL_NOM)
        menu = QMenu(self)
        a_copier = menu.addAction("Copier « " + str(valeur)[:60] + " »")
        a_dossier = None
        p = lg.chemin_local(str(valeur).split(" · ")[0])
        if p is not None and p.exists():
            a_dossier = menu.addAction("Afficher dans l'Explorateur")
        choix = menu.exec_(self.arbre.viewport().mapToGlobal(pos)) if hasattr(menu, "exec_") \
            else menu.exec(self.arbre.viewport().mapToGlobal(pos))
        if choix is a_copier:
            QGuiApplication.clipboard().setText(str(valeur))
        elif a_dossier is not None and choix is a_dossier:
            subprocess.Popen(["explorer", "/select,", str(p)])

    def _exporter(self):
        if not self._pbip:
            return
        defaut = str(Path(self._pbip).with_name(Path(self._pbip).stem + "_lineage.csv"))
        chemin, _ = QFileDialog.getSaveFileName(self, "Exporter le lineage", defaut,
                                                "CSV (*.csv)")
        if not chemin:
            return
        try:
            lg.ecrire_csv(self.lignes(), chemin)
        except OSError as e:
            self.journal.erreur(f"Sources de données : export impossible — {e}")
            return
        self.journal.info(f"Sources de données : {len(self.lignes())} lignes exportées "
                          f"vers {chemin}")
