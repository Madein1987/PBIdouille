# -*- coding: utf-8 -*-
"""Onglet « Radiographie 🩻 » : comprendre vite un rapport qu'on n'a pas fait.

À gauche, trois vues du même rapport :
  · PAR PAGE : la carte : chaque page, ses visuels, ce que chacun affiche, à
    quoi mène chaque mesure (ses mesures de base) et ce qui filtre le visuel
    (filtres du volet, de la page, du rapport, segments de la page) ;
  · PAR KPI : les familles de mesures (un KPI et ses variations), de la plus
    affichée à la moins affichée, puis les briques (les mesures que d'autres
    reprennent), les mesures jamais affichées, et les variations repérées ;
  · PAR COLONNE : chaque colonne utilisée, et où : segments, filtres,
    visuels, mesures. Ce qu'il faut regarder quand un chiffre est faux.
À droite, la fiche de ce qui est choisi : mesure, visuel, page, colonne ou
paramètre de champ, avec des liens pour passer de l'un à l'autre.

Rien n'y dépend de PBIdouille : ni config, ni TD_Indicateurs, ni annotation.
Tout se déduit du DAX, des noms et des visual.json (moteurs/radiographie.py).
Lecture seule.
"""

from __future__ import annotations

import html

from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import radiographie as rg
from core.journal import Journal
from core.theme import ACCENT, BLUE, ORANGE, TEXT_DIM, TEXT_MUTED, YELLOW

C_NOM, C_VAR, C_VUS, C_TABLE = 0, 1, 2, 3
ROLE = Qt.UserRole
GROUPE_BRIQUES = "Briques"
GROUPE_JAMAIS = "Jamais affichées"
GROUPE_PATRONS = "Variations repérées"
MAX_LISTE = 40          # au-delà, une liste de la fiche se résume


def _e(s) -> str:
    return html.escape(str(s))


def _vus(n_vis: int, n_pages: int | None = None) -> str:
    if not n_vis:
        return "·"
    s = f"{n_vis} visuel" + ("s" if n_vis > 1 else "")
    if n_pages is not None:
        s += f" · {n_pages} page" + ("s" if n_pages > 1 else "")
    return s


class RadiographieTab(QWidget):
    def __init__(self, journal=None):
        super().__init__()
        self.journal = journal or Journal()
        self._pbip = None
        self._pending = False
        self.res: dict = {}
        self._item_mesure: dict = {}     # nom -> item de la vue Par KPI
        self._item_visuel: dict = {}     # (page_id, id) -> item de la vue Par page
        self._liens: list = []           # cible des liens de la fiche

        v = QVBoxLayout(self)
        haut = QHBoxLayout()
        self.ed_filtre = QLineEdit()
        self.ed_filtre.setPlaceholderText("Filtrer (mesure, page, visuel…)")
        self.ed_filtre.setClearButtonEnabled(True)
        self.ed_filtre.textChanged.connect(self._filtrer)
        b_relire = QPushButton("↻ Relire")
        b_relire.setToolTip("Relit le modèle et les pages du rapport.")
        b_relire.clicked.connect(self.reload)
        haut.addWidget(self.ed_filtre, 1)
        haut.addWidget(b_relire)
        v.addLayout(haut)

        self.lbl_resume = QLabel("")
        self.lbl_resume.setWordWrap(True)
        self.lbl_resume.setStyleSheet(f"color:{TEXT_DIM};")
        self.lbl_resume.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.lbl_resume)

        split = QSplitter(Qt.Horizontal)
        self.vues = QTabWidget()
        self.vues.setObjectName("sousOnglets")
        self.arbre_kpi = self._arbre(["Mesure", "Variation", "Affichée", "Table"])
        self.arbre_pages = self._arbre(["Page / visuel / champ", "Mène à", "Détail", "Table"])
        # la carte du rapport d'abord : page, visuel, ce qu'il affiche, à quoi
        # ça mène et ce qui le filtre
        self.arbre_cols = self._arbre(["Table / colonne / usage", "Utilisée par", "Détail", ""])
        self.arbre_cols.setColumnHidden(C_TABLE, True)
        self.vues.addTab(self.arbre_pages, "Par page")
        self.vues.addTab(self.arbre_kpi, "Par KPI")
        self.vues.addTab(self.arbre_cols, "Par colonne")
        split.addWidget(self.vues)

        self.fiche = QTextBrowser()
        self.fiche.setOpenLinks(False)
        self.fiche.anchorClicked.connect(self._lien)
        split.addWidget(self.fiche)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        v.addWidget(split, 1)
        self._vider_fiche()

    def _arbre(self, entetes) -> QTreeWidget:
        a = QTreeWidget()
        a.setColumnCount(len(entetes))
        a.setHeaderLabels(entetes)
        a.setUniformRowHeights(True)
        h = a.header()
        h.setSectionResizeMode(C_NOM, QHeaderView.Interactive)
        for c in (C_VAR, C_VUS, C_TABLE):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setStretchLastSection(False)
        a.setColumnWidth(C_NOM, 320)
        a.currentItemChanged.connect(lambda cur, _prev: self._montrer(cur))
        return a

    # ---- projet (différé : changer de projet reste instantané) ----------------

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
            self.res = rg.analyser(self._pbip)
        except (OSError, UnicodeDecodeError, ValueError, SystemExit) as e:
            self.res = {}
            self.arbre_kpi.clear()
            self.arbre_pages.clear()
            self.lbl_resume.setText(f"Lecture impossible : {e}")
            self.journal.erreur(f"Radiographie : lecture impossible ({e})")
            return
        self._construire()

    # ---- construction --------------------------------------------------------

    @staticmethod
    def _item(textes, donnee=None) -> QTreeWidgetItem:
        it = QTreeWidgetItem([str(t) for t in textes])
        it.setData(C_NOM, ROLE, donnee)
        for c, t in enumerate(textes):
            if t:
                it.setToolTip(c, str(t))
        return it

    @staticmethod
    def _teinter(it, couleur, colonnes=(C_NOM, C_VAR, C_VUS, C_TABLE)):
        for c in colonnes:
            it.setForeground(c, QBrush(QColor(couleur)))

    def _construire(self):
        r = self.res
        nv = len(r["visuels"])
        n_fam = sum(1 for f in r["kpis"] if f["membres"])
        self.lbl_resume.setText(
            f"{len(r['mesures'])} mesures · {len(r['kpis'])} KPI, dont {n_fam} avec des "
            f"variations · {nv} visuels sur {len(r['pages'])} page(s) · "
            f"{len(r['parametres'])} paramètre(s) de champ · {len(r['briques'])} brique(s) · "
            f"{len(r['colonnes_utilisees'])} colonne(s) utilisée(s)")
        self._construire_kpi()
        self._construire_pages()
        self._construire_colonnes()
        self._filtrer(self.ed_filtre.text())
        self._vider_fiche()

    def _feuille_mesure(self, nom, variation="", par=None) -> QTreeWidgetItem:
        r = self.res
        m = r["mesures"][nom]
        n = len({(v["page_id"], v["id"]) for v, _ in r["affichee"][nom]})
        it = self._item([nom, variation, _vus(n), m["table"]], ("mesure", nom))
        if par == rg.NOM:
            it.setToolTip(C_VAR, f"{variation}\n\nRapprochée par le NOM seulement : "
                                 "elle ne référence pas la mesure de base.")
            it.setForeground(C_VAR, QBrush(QColor(YELLOW)))
        if not n:
            self._teinter(it, TEXT_MUTED, (C_NOM, C_VUS))
        self._item_mesure.setdefault(nom, it)
        return it

    def _construire_kpi(self):
        r = self.res
        a = self.arbre_kpi
        a.setUpdatesEnabled(False)
        a.clear()
        self._item_mesure = {}
        gras = QFont(a.font())
        gras.setBold(True)
        italique = QFont(gras)
        italique.setItalic(True)

        for f in r["kpis"]:
            n_var = len(f["membres"])
            var = f"{n_var} variation" + ("s" if n_var > 1 else "") if n_var else ""
            if f["reel"]:
                top = self._feuille_mesure(f["kpi"], var)
                top.setText(C_VUS, _vus(f["visuels"], f["pages"]))
                top.setToolTip(C_VUS, f"Le KPI et ses variations : {_vus(f['visuels'], f['pages'])}"
                                      f"\nLe KPI lui-même : {_vus(f['visuels_kpi'])}")
            else:
                top = self._item([f["kpi"] + " …", var, _vus(f["visuels"], f["pages"]), ""],
                                 ("famille", f["kpi"]))
                top.setToolTip(C_NOM, "Famille rapprochée par le NOM : ces mesures commencent "
                                      "par les mêmes mots, mais aucune ne référence l'autre.")
            top.setFont(C_NOM, italique if f["genre"] == rg.NOM else gras)
            if f["genre"] == rg.NOM:
                self._teinter(top, YELLOW, (C_VAR,))
            if not f["visuels"]:
                self._teinter(top, TEXT_MUTED, (C_NOM, C_VUS))
            for x in f["membres"]:
                top.addChild(self._feuille_mesure(x["nom"], x["patron"], x["par"]))
            a.addTopLevelItem(top)

        def groupe(titre, aide, enfants):
            g = self._item([f"{titre} ({len(enfants)})", "", "", ""], ("groupe", titre))
            g.setFont(C_NOM, gras)
            g.setToolTip(C_NOM, aide)
            self._teinter(g, BLUE, (C_NOM,))
            for e in enfants:
                g.addChild(e)
            a.addTopLevelItem(g)
            return g

        briques = []
        for b in r["briques"]:
            it = self._feuille_mesure(b["nom"])
            it.setText(C_VAR, f"utilisée par {len(b['utilisateurs'])}")
            it.setToolTip(C_VAR, "Utilisée par :\n" + "\n".join(b["utilisateurs"][:MAX_LISTE]))
            briques.append(it)
        groupe(GROUPE_BRIQUES, "Mesures que d'autres mesures reprennent, hors de leur "
                               "propre famille : souvent invisibles dans les visuels, et "
                               "ce qu'il faut lire en premier.", briques)
        groupe(GROUPE_JAMAIS, "Ni affichées par un visuel, ni dans une famille, ni "
                              "reprises par d'autres mesures. ChopChop dit si on peut "
                              "les supprimer.",
               [self._feuille_mesure(n) for n in r["jamais"]])
        patrons = []
        for p, n in r["patrons"]:
            it = self._item([p, f"{n} KPI", "", ""], ("patron", p))
            patrons.append(it)
        g = groupe(GROUPE_PATRONS, "Les variations écrites pour plusieurs KPI : le nom de "
                                   "la variation, son KPI remplacé par « … ».", patrons)
        g.setExpanded(False)
        a.setUpdatesEnabled(True)

    def _mene_a(self, nom) -> tuple:
        """(texte court, infobulle) de ce à quoi mène une mesure : ses mesures
        de base, ou, si elle en est une, les colonnes qu'elle lit."""
        r = self.res
        bases = r["bases"][nom]
        if bases:
            cols = [c for b in bases for c in r["colonnes"][b]]
            tip = ("Mesures de base :\n" + "\n".join(f"[{b}]" for b in bases)
                   + ("\n\nColonnes lues :\n" + "\n".join(f"'{t}'[{c}]" for t, c in cols)
                      if cols else ""))
            return ", ".join(bases), tip
        cols = r["colonnes"][nom]
        if cols:
            return ("lit " + ", ".join(f"'{t}'[{c}]" for t, c in cols),
                    "Mesure de base : elle lit directement ces colonnes.")
        return "", ""

    @staticmethod
    def texte_filtre(f) -> str:
        champ = (f"[{f['nom']}]" if f["genre"] == "Measure"
                 else f"'{f['table']}'[{f['nom']}]" if f["table"] else f["nom"])
        return f"{champ} {f['texte']}" if f["actif"] else f"{champ} (aucune valeur choisie)"

    def _noeud_filtres(self, titre, filtres, segments=()) -> QTreeWidgetItem | None:
        """« Filtré par » : filtres (visuel, page, rapport) et segments de la
        page qui ont une sélection. Les filtres sans valeur sont grisés."""
        actifs = [f for f in filtres if f["actif"]] + list(segments)
        if not filtres and not segments:
            return None
        g = self._item([f"{titre} ({len(actifs)})", "", "", ""], ("filtres", None))
        self._teinter(g, BLUE, (C_NOM,))
        for f in filtres:
            it = self._item([self.texte_filtre(f), "", f"filtre de {f['niveau']}", f["table"]],
                            ("filtre", None))
            if not f["actif"]:
                self._teinter(it, TEXT_MUTED)
            g.addChild(it)
        for s in segments:
            it = self._item([f"{s['libelle']} {s['selection']}", "", "segment de la page", ""],
                            ("visuel", (s["page_id"], s["id"])))
            g.addChild(it)
        return g

    def _construire_pages(self):
        r = self.res
        a = self.arbre_pages
        a.setUpdatesEnabled(False)
        a.clear()
        self._item_visuel = {}
        gras = QFont(a.font())
        gras.setBold(True)
        g = self._noeud_filtres("Filtres du rapport", r["filtres_rapport"])
        if g is not None:
            g.setFont(C_NOM, gras)
            a.addTopLevelItem(g)
        for p in r["pages"]:
            vis = p["visuels"]
            top = self._item([p["nom"], "", f"{len(vis)} visuel" + ("s" if len(vis) > 1 else ""),
                              ""], ("page", p["id"]))
            top.setFont(C_NOM, gras)
            g = self._noeud_filtres("Filtres de la page", p["filtres"])
            if g is not None:
                top.addChild(g)
            for v in vis:
                n_mes = sum(1 for c in v["champs"] if c["genre"] != "colonne")
                n_flt = (sum(1 for f in v["filtres"] if f["actif"]) + len(v["segments"])
                         + sum(1 for f in p["filtres"] + r["filtres_rapport"] if f["actif"]))
                casses = sum(1 for c in v["champs"] if c["genre"] == "colonne"
                             and not c["connue"])
                lib = (("⚠ " if casses else "") + v["libelle"]
                       + ("  (masqué)" if v["masque"] else ""))
                if v["segment"]:
                    detail = v["selection"] or "aucune sélection"
                else:
                    detail = " · ".join(x for x in (
                        f"{n_mes} mesure(s)" if n_mes else "",
                        f"{n_flt} filtre(s)" if n_flt else "") if x)
                it = self._item([lib, "", detail, ""], ("visuel", (v["page_id"], v["id"])))
                if v["segment"] or v["masque"]:
                    self._teinter(it, TEXT_MUTED)
                if casses:
                    self._teinter(it, YELLOW, (C_NOM,))
                    it.setToolTip(C_NOM, f"{casses} champ(s) introuvable(s) dans le modèle")
                for c in v["champs"]:
                    it.addChild(self._feuille_champ(c))
                if not v["segment"]:
                    g = self._noeud_filtres("Filtré par", v["filtres"], v["segments"])
                    if g is not None:
                        it.addChild(g)
                self._item_visuel[(v["page_id"], v["id"])] = it
                top.addChild(it)
            a.addTopLevelItem(top)
            top.setExpanded(True)
        a.setUpdatesEnabled(True)

    def _role(self, nom) -> str:
        """« KPI », « variation de X » ou rien : la place d'une mesure dans
        les familles."""
        kpi = self.res["famille_de"].get(nom)
        if not kpi:
            return ""
        if kpi == nom:
            return "KPI"
        f = self._famille(kpi)
        return f"variation de {kpi}" if f and f["reel"] else f"famille {kpi} … (par le nom)"

    def _feuille_champ(self, c) -> QTreeWidgetItem:
        r = self.res
        if c["genre"] == "mesure":
            mene, tip = self._mene_a(c["nom"])
            it = self._item([f'[{c["nom"]}]', mene, self._role(c["nom"]),
                             r["mesures"][c["nom"]]["table"]], ("mesure", c["nom"]))
            if tip:
                it.setToolTip(C_VAR, tip)
            self._teinter(it, ACCENT, (C_NOM,))
            return it
        if c["genre"] == "parametre":
            n = len(c["mesures"])
            it = self._item([f'{c["table"]}  (paramètre de champ)', "",
                             f"{n} mesure" + ("s" if n > 1 else "") + " au choix", c["table"]],
                            ("parametre", c["table"]))
            self._teinter(it, ORANGE, (C_NOM,))
            for m in c["mesures"]:
                mene, tip = self._mene_a(m)
                sub = self._item([f"[{m}]", mene, self._role(m), r["mesures"][m]["table"]],
                                 ("mesure", m))
                if tip:
                    sub.setToolTip(C_VAR, tip)
                it.addChild(sub)
            return it
        nom = f"[{c['nom']}]" if c.get("mesure") else f"'{c['table']}'[{c['nom']}]"
        if c.get("agregat"):
            nom = f"{c['agregat']} de {nom}"
        if not c["connue"]:
            it = self._item(["⚠ " + nom, "", "introuvable", c["table"]], ("colonne", c["ref"]))
            it.setToolTip(C_NOM, nom + "\n\nCe champ n'existe pas dans le modèle (renommé ou "
                                 "supprimé) : le visuel s'affiche en erreur.")
            self._teinter(it, YELLOW, (C_NOM, C_VUS))
            return it
        it = self._item([nom, "", "", c["table"]], ("colonne", c["ref"]))
        self._teinter(it, TEXT_DIM, (C_NOM,))
        return it

    # ---- filtre --------------------------------------------------------------

    def _filtrer(self, texte):
        t = (texte or "").strip().lower()
        for a in (self.arbre_kpi, self.arbre_pages, self.arbre_cols):
            for i in range(a.topLevelItemCount()):
                self._filtrer_item(a.topLevelItem(i), t)

    def _filtrer_item(self, it, t) -> bool:
        """Visible si lui ou un descendant contient le texte. Un parent qui
        correspond garde tous ses enfants."""
        moi = not t or t in it.text(C_NOM).lower()
        enfant = False
        for i in range(it.childCount()):
            c = it.child(i)
            if moi:
                self._montrer_tout(c)
                enfant = True
            else:
                enfant = self._filtrer_item(c, t) or enfant
        it.setHidden(not (moi or enfant))
        if t and enfant and not moi:
            it.setExpanded(True)
        return moi or enfant

    def _montrer_tout(self, it):
        it.setHidden(False)
        for i in range(it.childCount()):
            self._montrer_tout(it.child(i))

    # ---- fiche ---------------------------------------------------------------

    def _vider_fiche(self):
        self.fiche.setHtml(f"<p style='color:{TEXT_MUTED}'>Choisir une mesure, une page ou "
                           "un visuel pour voir sa fiche.</p>")

    def _a(self, texte, cible) -> str:
        self._liens.append(cible)
        return f"<a href='#{len(self._liens) - 1}' style='color:{ACCENT}'>{_e(texte)}</a>"

    def _liste(self, items) -> str:
        if not items:
            return f"<p style='color:{TEXT_MUTED}'>aucun</p>"
        reste = len(items) - MAX_LISTE
        lignes = "".join(f"<li>{x}</li>" for x in items[:MAX_LISTE])
        if reste > 0:
            lignes += f"<li style='color:{TEXT_MUTED}'>… et {reste} autres</li>"
        return f"<ul style='margin-top:2px'>{lignes}</ul>"

    def _ou(self, v, via=None) -> str:
        return (f"{_e(v['page'])} › " + self._a(v["libelle"], ("visuel", (v["page_id"], v["id"])))
                + (f" <span style='color:{TEXT_MUTED}'>via {_e(via)}</span>" if via else ""))

    def _montrer(self, it):
        if it is None:
            return
        donnee = it.data(C_NOM, ROLE)
        if not donnee:
            return
        genre, cle = donnee
        self._liens = []
        if genre == "mesure":
            self.fiche.setHtml(self._fiche_mesure(cle))
        elif genre == "visuel":
            self.fiche.setHtml(self._fiche_visuel(cle))
        elif genre == "page":
            self.fiche.setHtml(self._fiche_page(cle))
        elif genre == "famille":
            self.fiche.setHtml(self._fiche_famille(cle))
        elif genre == "parametre":
            self.fiche.setHtml(self._fiche_parametre(cle))
        elif genre == "colonne_rapport":
            self.fiche.setHtml(self._fiche_colonne(cle))

    def _famille(self, kpi):
        return next((f for f in self.res["kpis"] if f["kpi"] == kpi), None)

    def _fiche_mesure(self, nom) -> str:
        r = self.res
        m = r["mesures"][nom]
        out = [f"<h3>{_e(nom)}</h3>"]
        kpi = r["famille_de"].get(nom)
        f = self._famille(kpi) if kpi else None
        if f and kpi == nom:
            n = len(f["membres"])
            out.append(f"<p><b>KPI</b>" + (f", {n} variation(s)" if n else "") + "</p>")
        elif f:
            x = next(x for x in f["membres"] if x["nom"] == nom)
            if f["reel"]:
                base = x["base"] or kpi
                par = ("par le DAX" if x["par"] == rg.DAX else
                       f"<span style='color:{YELLOW}'>par le nom seulement</span>")
                out.append(f"<p>Variation de {self._a(base, ('mesure', base))} : "
                           f"<b>{_e(x['patron'])}</b> ({par})</p>")
            else:
                out.append(f"<p>Dans la famille <b>{_e(kpi)} …</b>, "
                           f"<span style='color:{YELLOW}'>rapprochée par le nom "
                           "seulement</span> : aucune mesure de base commune.</p>")
        details = [f"table <b>{_e(m['table'])}</b>"]
        if m["dossier"]:
            details.append(f"dossier {_e(m['dossier'])}")
        if m["format"]:
            details.append(f"format {_e(m['format'])}")
        out.append(f"<p style='color:{TEXT_DIM}'>" + " · ".join(details) + "</p>")

        out.append("<h4>Affichée dans</h4>" + self._liste(
            [self._ou(v, via) for v, via in r["affichee"][nom]]))
        if r["choisie"][nom]:
            out.append("<h4>Proposée par un segment</h4>" + self._liste(
                [self._ou(v, via) for v, via in r["choisie"][nom]]))
        if r["proposee_par"][nom]:
            out.append("<h4>Dans les paramètres de champ</h4>" + self._liste(
                [self._a(t, ("parametre", t)) for t in r["proposee_par"][nom]]))
        out.append("<h4>Mène à</h4>" + self._liste([self._champ_mesure(nom)]))
        out.append("<h4>Utilise</h4>" + self._liste(
            [self._a(u, ("mesure", u)) for u in r["uses"][nom]]))
        out.append("<h4>Utilisée par</h4>" + self._liste(
            [self._a(u, ("mesure", u)) for u in r["used_by"][nom]]))
        out.append("<h4>DAX</h4><pre style='font-family:Consolas,monospace'>"
                   + _e(m["dax"] or "(vide)") + "</pre>")
        return "".join(out)

    def _fiche_famille(self, kpi) -> str:
        f = self._famille(kpi)
        out = [f"<h3>{_e(kpi)} …</h3>",
               f"<p style='color:{YELLOW}'>Famille rapprochée par le nom : ces mesures "
               "commencent par les mêmes mots, mais aucune ne référence l'autre. À "
               "vérifier.</p>", f"<p>{_vus(f['visuels'], f['pages'])}</p>"]
        out.append(self._liste([self._a(x["nom"], ("mesure", x["nom"])) for x in f["membres"]]))
        return "".join(out)

    def _visuel(self, cle):
        return next(v for v in self.res["visuels"] if (v["page_id"], v["id"]) == cle)

    def _fiche_visuel(self, cle) -> str:
        v = self._visuel(cle)
        out = [f"<h3>{_e(v['libelle'])}</h3>",
               f"<p style='color:{TEXT_DIM}'>page <b>{_e(v['page'])}</b> · type "
               f"{_e(v['type'])}" + (" · masqué" if v["masque"] else "") + "</p>"]
        if v["segment"]:
            out.append("<p>Un segment : il <b>choisit</b> ce que les autres visuels "
                       "affichent.</p>")
        champs = []
        for c in v["champs"]:
            if c["genre"] == "mesure":
                champs.append(self._champ_mesure(c["nom"]))
            elif c["genre"] == "parametre":
                champs.append(self._a(c["table"], ("parametre", c["table"]))
                              + f" <span style='color:{TEXT_MUTED}'>· paramètre de champ, "
                                f"{len(c['mesures'])} mesure(s) au choix</span>")
            else:
                nom = (f"[{c['nom']}]" if c.get("mesure")
                       else f"'{c['table']}'[{c['nom']}]")
                txt = _e((c["agregat"] + " de " if c.get("agregat") else "") + nom)
                if not c["connue"]:
                    txt = (f"<span style='color:{YELLOW}'>⚠ {txt} : introuvable dans le "
                           "modèle</span>")
                champs.append(txt)
        out.append("<h4>Champs</h4>" + self._liste(champs))
        if not v["segment"]:
            p = next(p for p in self.res["pages"] if p["id"] == v["page_id"])
            filtres = ([_e(self.texte_filtre(f)) for f in v["filtres"] if f["actif"]]
                       + [_e(self.texte_filtre(f)) + f" <span style='color:{TEXT_MUTED}'>"
                          "· page</span>" for f in p["filtres"] if f["actif"]]
                       + [_e(self.texte_filtre(f)) + f" <span style='color:{TEXT_MUTED}'>"
                          "· rapport</span>" for f in self.res["filtres_rapport"] if f["actif"]]
                       + [self._a(s["libelle"], ("visuel", (s["page_id"], s["id"])))
                          + f" {_e(s['selection'])}" for s in v["segments"]])
            out.append("<h4>Filtré par</h4>" + self._liste(filtres))
            vides = [f for f in v["filtres"] if not f["actif"]]
            if vides:
                out.append(f"<p style='color:{TEXT_MUTED}'>Dans le volet des filtres, sans "
                           "valeur choisie : " + ", ".join(_e(self.texte_filtre(f).split(" (")[0])
                                                            for f in vides) + "</p>")
        else:
            out.append("<h4>Sélection</h4>" + self._liste(
                [_e(v["selection"])] if v["selection"] else []))
        return "".join(out)

    def _champ_mesure(self, nom) -> str:
        """[mesure] · son rôle → ses mesures de base → les colonnes lues."""
        r = self.res
        txt = self._a(f"[{nom}]", ("mesure", nom))
        role = self._role(nom)
        if role:
            txt += f" <span style='color:{TEXT_MUTED}'>· {_e(role)}</span>"
        bases = r["bases"][nom]
        if bases:
            txt += " → " + ", ".join(self._a(b, ("mesure", b)) for b in bases)
        cols = [c for b in (bases or [nom]) for c in r["colonnes"][b]]
        if cols:
            txt += (f"<br><span style='color:{TEXT_MUTED}'>lit "
                    + ", ".join(_e(f"'{t}'[{c}]") for t, c in dict.fromkeys(cols))
                    + "</span>")
        return txt

    def _fiche_page(self, pid) -> str:
        p = next(p for p in self.res["pages"] if p["id"] == pid)
        kpis = []
        for v in p["visuels"]:
            if v["segment"]:
                continue
            for c in v["champs"]:
                noms = [c["nom"]] if c["genre"] == "mesure" else c.get("mesures") or []
                for n in noms:
                    k = self.res["famille_de"].get(n, n)
                    if k not in kpis:
                        kpis.append(k)
        out = [f"<h3>{_e(p['nom'])}</h3>", f"<p>{len(p['visuels'])} visuel(s)</p>",
               "<h4>KPI affichés</h4>",
               self._liste([self._a(k, ("mesure", k)) if k in self.res["mesures"] else _e(k)
                            for k in kpis]),
               "<h4>Visuels</h4>",
               self._liste([self._ou(v) for v in p["visuels"]])]
        return "".join(out)

    def _fiche_parametre(self, table) -> str:
        fp = self.res["parametres"][table]
        vis = [v for v in self.res["visuels"]
               if any(c["genre"] == "parametre" and c["table"] == table for c in v["champs"])]
        out = [f"<h3>{_e(table)}</h3>",
               "<p>Paramètre de champ : un segment choisit laquelle de ces mesures les "
               "visuels affichent.</p>",
               "<h4>Utilisé par</h4>", self._liste([self._ou(v) for v in vis]),
               f"<h4>Mesures proposées ({len(fp['mesures'])})</h4>",
               self._liste([self._a(m, ("mesure", m)) for m in fp["mesures"]])]
        return "".join(out)

    # genre d'usage -> libellé au pluriel, dans l'ordre où on les cherche
    # quand un chiffre est faux
    GENRES_USAGE = (("segment", "segment"), ("filtre de rapport", "filtre de rapport"),
                    ("filtre de page", "filtre de page"), ("filtre de visuel", "filtre de visuel"),
                    ("visuel", "visuel"), ("mesure", "mesure"))

    def _resume_usages(self, usages) -> str:
        parts = []
        for genre, mot in self.GENRES_USAGE:
            n = sum(1 for u in usages if u["genre"] == genre)
            if n:
                parts.append(f"{n} {mot}" + ("s" if n > 1 and not mot.endswith("s") else ""))
        return " · ".join(parts)

    def _construire_colonnes(self):
        """Par colonne : chaque table, ses colonnes utilisées, et pour chacune
        où elle sert (segment, filtre, visuel, mesure)."""
        r = self.res
        a = self.arbre_cols
        a.setUpdatesEnabled(False)
        a.clear()
        gras = QFont(a.font())
        gras.setBold(True)
        ordre = {g: i for i, (g, _m) in enumerate(self.GENRES_USAGE)}
        par_table: dict = {}
        for i, c in enumerate(r["colonnes_utilisees"]):
            par_table.setdefault(c["table"], []).append((i, c))
        for table in sorted(par_table, key=str.lower):
            cols = par_table[table]
            top = self._item([table, f"{len(cols)} colonne(s)", "", ""], ("table", table))
            top.setFont(C_NOM, gras)
            for i, c in cols:
                nom = ("⚠ " if not c["connue"] else "") + c["nom"]
                it = self._item([nom, self._resume_usages(c["usages"]), "", ""],
                                ("colonne_rapport", i))
                if not c["connue"]:
                    self._teinter(it, YELLOW, (C_NOM,))
                    it.setToolTip(C_NOM, "Introuvable dans le modèle : renommée ou supprimée.")
                for u in sorted(c["usages"], key=lambda u: (ordre.get(u["genre"], 9),
                                                           u["ou"].lower())):
                    sub = self._item([u["ou"], u["genre"], u["texte"], ""], u["cible"])
                    if u["genre"] == "mesure":
                        self._teinter(sub, ACCENT, (C_NOM,))
                    elif u["texte"] == "sans valeur choisie":
                        self._teinter(sub, TEXT_MUTED)
                    it.addChild(sub)
                top.addChild(it)
            a.addTopLevelItem(top)
            top.setExpanded(True)
        a.setUpdatesEnabled(True)

    def _fiche_colonne(self, i) -> str:
        c = self.res["colonnes_utilisees"][i]
        ordre = {g: k for k, (g, _m) in enumerate(self.GENRES_USAGE)}
        out = [f"<h3>{_e(chr(39) + c['table'] + chr(39) + '[' + c['nom'] + ']')}</h3>"]
        if not c["connue"]:
            out.append(f"<p style='color:{YELLOW}'>⚠ Introuvable dans le modèle : renommée "
                       "ou supprimée. Les visuels qui l'utilisent s'affichent en erreur.</p>")
        out.append(f"<p style='color:{TEXT_DIM}'>{_e(self._resume_usages(c['usages']))}</p>")
        for genre, mot in self.GENRES_USAGE:
            us = [u for u in c["usages"] if u["genre"] == genre]
            if not us:
                continue
            lignes = []
            for u in sorted(us, key=lambda u: u["ou"].lower()):
                lien = self._a(u["ou"], u["cible"]) if u["cible"] else _e(u["ou"])
                lignes.append(lien + (f" <span style='color:{TEXT_MUTED}'>{_e(u['texte'])}</span>"
                                      if u["texte"] else ""))
            titre = {"segment": "Segments", "filtre de rapport": "Filtres du rapport",
                     "filtre de page": "Filtres de page", "filtre de visuel": "Filtres de visuel",
                     "visuel": "Visuels", "mesure": "Mesures qui la lisent"}[genre]
            out.append(f"<h4>{titre}</h4>" + self._liste(lignes))
        return "".join(out)

    # ---- navigation ----------------------------------------------------------

    def _lien(self, url):
        try:
            genre, cle = self._liens[int(url.fragment() or url.toString().lstrip("#"))]
        except (ValueError, IndexError):
            return
        self.aller_a(genre, cle)

    def aller_a(self, genre, cle) -> None:
        """Sélectionne une mesure (vue Par KPI) ou un visuel (vue Par page)."""
        if genre == "mesure":
            it, arbre = self._item_mesure.get(cle), self.arbre_kpi
        elif genre == "visuel":
            it, arbre = self._item_visuel.get(cle), self.arbre_pages
        else:
            fiches = {"parametre": self._fiche_parametre, "page": self._fiche_page}
            if genre in fiches:
                self._liens = []
                self.fiche.setHtml(fiches[genre](cle))
            return
        if it is None:
            return
        if self.ed_filtre.text() and it.isHidden():
            self.ed_filtre.clear()
        self.vues.setCurrentWidget(arbre)
        p = it.parent()
        while p is not None:
            p.setExpanded(True)
            p = p.parent()
        arbre.setCurrentItem(it)
        arbre.scrollToItem(it)
