# -*- coding: utf-8 -*-
"""Onglet « Config mesures » : édite measures_config.json en trois vues du
MÊME config en mémoire :
  - « Variations » : un formulaire par variation (nom, options, DAX en clair) —
    le format JSON array-of-lines devient invisible ;
  - « Réglages globaux » : settings, fieldParameter, switch et branches
    (cases/champs plutôt que du JSON à la main) ;
  - « JSON brut » : tout le fichier, pour les cas non couverts.

Synchronisation : à chaque changement de sous-onglet, celui qu'on QUITTE est
committé dans le config en mémoire, celui qu'on OUVRE est rechargé depuis lui
(le JSON brut invalide bloque le changement). Sauvegarder : backup
measures_config.json.bak puis écriture indent=2.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont, QStandardItem, QStandardItemModel
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import model_reader
from core.theme import YELLOW, TEXT_DIM, checkable_list_stylesheet
from tabs.tab_model import ModelTab

import generate_measures as gm   # scan_cibles : mêmes règles que la génération

# index des sous-onglets de l'onglet « Mesures »
IDX_VARIATIONS, IDX_GLOBAL, IDX_RAW, IDX_GENERATE = 0, 1, 2, 3

# placeholders compris par le générateur (generate_measures.py / csx) ; tout autre {jeton}
# serré (sans espaces) est probablement une faute de frappe. « { ad } » avec
# espaces = constructeur de table DAX, jamais signalé.
KNOWN_PLACEHOLDERS = {
    "base", "baseRef", "date", "variation", "deltaScale",
    "kpi", "kpiRef", "folder", "baseFolder", "baseFormat", "branch",
}

# aide-mémoire affiché sous le DAX : ce que vaut chaque jeton, avec l'exemple
# qui compte — la DIFFÉRENCE entre {kpi} (racine, sans branche) et {kpiRef}
# (mesure du KPI DANS la branche courante). C'est le piège de l'écart
# réel−cible : en branche YTD, [{kpi}] compare le réel COURANT à la cible YTD.
TOKENS_HELP = (
    "Jetons — exemple : cible « Weight cible », branche YTD\n"
    "  {base}     nom de la base traitée .......... Weight cible YTD\n"
    "  {baseRef}  ↳ en référence DAX .............. [Weight cible YTD]\n"
    "  {kpi}      KPI racine, SANS branche ........ Weight\n"
    "  {kpiRef}   ↳ le KPI DANS la branche ........ [Weight YTD]\n"
    "  {branch}   branche courante ................ YTD\n"
    "  {variation} id de la variation · {date} colonne de dates\n"
    "  {deltaScale} 100 si le format est un %, sinon 1"
)
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

# gabarit d'une nouvelle variation
NEW_VARIATION = {
    "namePattern": "{base} X",
    "inFieldParameter": False,
    "dax": "",
    "formatString": "inherit",
    "description": "",
}


def dax_to_text(dax) -> str:
    """dax du JSON (str ou liste de lignes) -> texte éditable."""
    if isinstance(dax, list):
        return "\n".join(str(x) for x in dax)
    return str(dax) if dax is not None else ""


def text_to_dax(text: str):
    """Texte de l'éditeur -> valeur JSON : liste de lignes si multiligne,
    chaîne sinon (round-trip fidèle des deux formes du config)."""
    text = text.rstrip("\n")
    if "\n" in text:
        return text.split("\n")
    return text


def lines_to_list(text: str) -> list:
    """Zone multiligne -> liste (une entrée par ligne non vide)."""
    return [l.strip() for l in text.splitlines() if l.strip()]


def list_to_lines(value) -> str:
    """Liste JSON -> zone multiligne (une entrée par ligne)."""
    return "\n".join(str(x) for x in value) if isinstance(value, list) else ""


class CheckCombo(QComboBox):
    """Liste déroulante à cases : multi-choix, mais UNE seule ligne à l'écran
    qui affiche la sélection. Remplace une rangée de cases quand le vocabulaire
    peut s'allonger (les types de mesure viennent en partie d'une colonne
    Excel, donc leur nombre n'est pas connu d'avance)."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.view().pressed.connect(self._toggle)

    def set_items(self, items, checked=None):
        """`checked=None` = tout coché (= aucun filtre)."""
        m = self.model()
        m.clear()
        for nom in items:
            it = QStandardItem(nom)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            coche = Qt.Checked if (checked is None or nom in checked) else Qt.Unchecked
            it.setData(coche, Qt.CheckStateRole)
            m.appendRow(it)
        self._refresh_text()

    def checked(self) -> list:
        m = self.model()
        return [m.item(i).text() for i in range(m.rowCount())
                if m.item(i).checkState() == Qt.Checked]

    def all_checked(self) -> bool:
        return len(self.checked()) == self.model().rowCount()

    def _toggle(self, index):
        it = self.model().itemFromIndex(index)
        it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self._refresh_text()
        self.changed.emit()

    def _refresh_text(self):
        coches = self.checked()
        if self.all_checked():
            self.lineEdit().setText("tous")
        else:
            self.lineEdit().setText(", ".join(coches) or "aucun !")


class ConfigTab(QWidget):
    def __init__(self):
        super().__init__()
        self.project = None
        self._config: dict = {}
        self._current: str | None = None   # id de la variation affichée
        self._loading = False              # évite les signaux pendant le peuplement
        self._dirty = False
        self._branch_restrict: dict = {}   # branche -> set des variations qu'elle applique
        self._branch_pick_current = None   # branche affichée dans l'éditeur de restriction

        root = QVBoxLayout(self)

        # affiché quand aucun measures_config.json n'est résolu pour le projet
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(f"color:{YELLOW};")
        self.lbl_hint.hide()
        root.addWidget(self.lbl_hint)

        self._inner_prev = IDX_VARIATIONS
        self.inner = QTabWidget()
        self.inner.addTab(self._build_variations_tab(), "Variations")
        self.inner.addTab(self._build_global_tab(), "Réglages globaux")
        self.inner.addTab(self._build_raw_tab(), "JSON brut")
        self.model_panel = ModelTab()          # génération embarquée (onglet Mesures)
        self.inner.addTab(self.model_panel, "Générer")
        self.inner.currentChanged.connect(self._on_view_switch)
        root.addWidget(self.inner, 1)

        bottom = QHBoxLayout()
        self.lbl_dirty = QLabel("")
        self.lbl_dirty.setStyleSheet(f"color:{YELLOW};")
        bottom.addWidget(self.lbl_dirty, 1)
        self.btn_reload = QPushButton("Recharger (annule)")
        self.btn_reload.clicked.connect(self._reload)
        self.btn_save = QPushButton("Sauvegarder (backup .bak)")
        self.btn_save.clicked.connect(self._save)
        bottom.addWidget(self.btn_reload)
        bottom.addWidget(self.btn_save)
        root.addLayout(bottom)

    # ---- construction ----------------------------------------------------------

    def _build_variations_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        # -- gauche : liste + boutons --
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.lst = QListWidget()
        self.lst.currentTextChanged.connect(self._on_select)
        self.lst.itemChanged.connect(self._on_variation_checked)
        lv.addWidget(self.lst, 1)
        self.lbl_catalogue = QLabel("")
        self.lbl_catalogue.setWordWrap(True)
        self.lbl_catalogue.setStyleSheet(f"color:{TEXT_DIM};")
        lv.addWidget(self.lbl_catalogue)
        sel = QHBoxLayout()
        b_tout = QPushButton("Tout")
        b_tout.setToolTip("Activer toutes les variations du catalogue\n"
                          "dans ce rapport.")
        b_tout.clicked.connect(lambda: self._tout_cocher(True))
        b_rien = QPushButton("Aucune")
        b_rien.clicked.connect(lambda: self._tout_cocher(False))
        sel.addWidget(QLabel("Actives :"))
        sel.addWidget(b_tout)
        sel.addWidget(b_rien)
        sel.addWidget(self._help("Catalogue et sélection", (
            "La liste ci-dessus est un CATALOGUE : le measures_config.json\n"
            "les porte toutes et voyage d'un rapport à l'autre.\n\n"
            "La CASE de chaque ligne dit si la variation est générée dans\n"
            "CE rapport-ci. Ce choix est écrit dans un petit fichier posé\n"
            "à côté du .pbip (pbidouille_variations.json), jamais dans le\n"
            "config — un autre rapport qui réutilise le même catalogue\n"
            "garde donc sa propre sélection.\n\n"
            "Décocher une variation ne SUPPRIME pas les mesures déjà\n"
            "générées : elles deviennent orphelines. Coche « removeOrphans »\n"
            "(Réglages globaux) si tu veux qu'elles soient retirées.\n\n"
            "Décocher une variation qui sert de BRANCHE retire aussi la\n"
            "branche — le journal le dit.\n\n"
            "Tout coché = aucun fichier de sélection (état par défaut).")))
        sel.addStretch()
        lv.addLayout(sel)
        row1 = QHBoxLayout()
        for label, slot in (("Ajouter", self._add), ("Dupliquer", self._duplicate)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row1.addWidget(b)
        lv.addLayout(row1)
        row2 = QHBoxLayout()
        for label, slot in (("Renommer", self._rename), ("Supprimer", self._delete)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row2.addWidget(b)
        lv.addLayout(row2)
        row3 = QHBoxLayout()
        for label, delta in (("↑ Monter", -1), ("↓ Descendre", 1)):
            b = QPushButton(label)
            b.setToolTip("Réordonne les variations. L'ordre pilote l'ordre des\n"
                         "calculs dans le paramètre de champ (et la génération).")
            b.clicked.connect(lambda _=False, d=delta: self._move(d))
            row3.addWidget(b)
        lv.addLayout(row3)
        split.addWidget(left)

        # -- droite : formulaire --
        right = QWidget()
        grid = QGridLayout(right)
        r = 0

        def add_row(label, widget, tip=None, help_text=None):
            nonlocal r
            lbl = QLabel(label)
            tip = tip or help_text
            if tip:
                lbl.setToolTip(tip)
                widget.setToolTip(tip)
            grid.addWidget(lbl, r, 0)
            if help_text:            # ⓘ collé au champ : aucune ligne en plus
                box = QHBoxLayout()
                box.setContentsMargins(0, 0, 0, 0)
                box.addWidget(widget, 1)
                box.addWidget(self._help(label.rstrip(" :"), help_text))
                holder = QWidget()
                holder.setLayout(box)
                grid.addWidget(holder, r, 1)
            else:
                grid.addWidget(widget, r, 1)
            r += 1

        self.ed_name = QLineEdit()
        add_row("namePattern :", self.ed_name,
                "Nom de la mesure générée.\n{base} = mesure de base (branche incluse), "
                "{kpi} = KPI racine, {variation} = id de la variation.")
        self.ed_desc = QLineEdit()
        add_row("description :", self.ed_desc,
                "Description de la mesure générée (placeholders permis).")
        self.cmb_format = QComboBox()
        self.cmb_format.setEditable(True)   # presets + saisie libre
        self.cmb_format.addItems(["inherit", "delta", "text", "#,0", "#,0.0",
                                  "#,0.00", "0.0%", "+#,0.0%;-#,0.0%;#,0.0%"])
        add_row("formatString :", self.cmb_format, help_text=(
            "inherit = format de la mesure de base.\n"
            "delta = format signé ± dérivé de la base (une base en % donne des pts).\n"
            "text = AUCUN format — pour une mesure texte (ex. les hex des CF).\n"
            "Sinon : un format explicite ; {baseFormat} = section positive de la base.\n\n"
            "Littéraux : une espace est une espace. Espace, + - $ ( ) s'affichent\n"
            "d'eux-mêmes ; seules les lettres demandent un backslash (pts donne \n\np\n\nt\n\ns)."))
        self.ed_folder = QLineEdit()
        self.ed_folder.setPlaceholderText("vide = displayFolderPattern des settings")
        add_row("displayFolder :", self.ed_folder,
                "Dossier d'affichage des mesures générées.\n"
                "Vide = le displayFolderPattern des settings. Placeholders : "
                "{folder} {baseFolder} {variation} {kpi} {branch}.")
        self.cmb_folder_var = QComboBox()   # non éditable : ids existants
        add_row("folderVariation (dossier hôte) :", self.cmb_folder_var,
                "Range les mesures générées dans le DOSSIER d'une AUTRE variation.\n"
                "Ex. « CF Δ 30d » vit dans le dossier de « Δ 30d » (la couleur à côté\n"
                "de la mesure qu'elle met en forme). Vide = son propre dossier.")
        self.cmb_datacat = QComboBox()
        self.cmb_datacat.setEditable(True)
        self.cmb_datacat.addItems(["", "ImageUrl", "WebUrl"])
        add_row("dataCategory :", self.cmb_datacat,
                "Catégorie de données de la mesure.\n"
                "ImageUrl = la mesure retourne une image (SVG en data-URI) ;\n"
                "WebUrl = un lien ; vide = mesure normale.")
        self.chk_infp = QCheckBox("dans les paramètres de champ (inFieldParameter)")
        self.chk_infp.setToolTip("Coché : la mesure générée entre dans les tables\n"
                                 "paramètre de champ (P_Indicateurs_*).")
        grid.addWidget(self.chk_infp, r, 1)
        r += 1

        # portée : cette variation est-elle déclinée pour les KPI, les cibles ?
        scope = QHBoxLayout()
        self.chk_kpi = QCheckBox("générer pour les KPI")
        self.chk_kpi.setToolTip("Décline cette variation sur les mesures de BASE (KPI).\n"
                                "Défaut : coché.")
        self.chk_cible = QCheckBox("générer pour les cibles")
        self.chk_cible.setToolTip(
            "Décline cette variation sur les mesures CIBLES (dossier dédié).\n"
            "Utile surtout pour l'écart réel−cible, via le jeton {kpiRef} :\n"
            "   {kpiRef} - {baseRef}\n"
            "     Réel →  [Weight]      - [Weight cible]\n"
            "     YTD  →  [Weight YTD]  - [Weight cible YTD]\n"
            "\n"
            "⚠ N'écris PAS « [{kpi}] - {baseRef} » : {kpi} est le KPI RACINE,\n"
            "sans branche, donc en YTD tu comparerais le réel COURANT à la\n"
            "cible YTD. {kpiRef} suit la branche, {kpi} non — c'est voulu.\n"
            "\n"
            "Une variation « écart » se coche ici mais se DÉCOCHE côté KPI\n"
            "(elle vaudrait 0). Défaut : décoché.")
        # types de base acceptés : une combo à cases (le vocabulaire
        # s'allonge avec la colonne « type » de TD_Indicateurs)
        self.cmb_kinds = CheckCombo()
        self.cmb_kinds.setMinimumWidth(190)
        self.cmb_kinds.changed.connect(self._on_edit)
        scope.addWidget(QLabel("Portée :"))
        scope.addWidget(self.chk_kpi)
        scope.addWidget(self.chk_cible)
        scope.addSpacing(14)
        scope.addWidget(QLabel("types de base :"))
        scope.addWidget(self.cmb_kinds)
        scope.addWidget(self._help("Types de base acceptés", (
            "Limite la variation aux bases d'un certain TYPE. « tous » = aucun\n"
            "filtre. Une base écartée ne reçoit PAS la mesure : elle n'est pas\n"
            "créée du tout, plutôt que créée puis fausse.\n\n"
            "DÉDUITS du formatString :\n"
            "   0.0 %       donne  pourcentage\n"
            "   #,0.00 $    donne  devise\n"
            "   #,0 ou vide donne  nombre\n\n"
            "DÉCLARÉS dans TD_Indicateurs (colonne « type » — Réglages\n"
            "globaux) : ratio, durée, indice, ou ce que tu veux. Un format ne\n"
            "peut PAS les deviner — un ratio décimal (0,85) s'écrit comme un\n"
            "nombre. La déclaration prime toujours sur la déduction.\n\n"
            "Exemple : un « % du total » n'a de sens ni sur un pourcentage ni\n"
            "sur un ratio — coche nombre et devise seulement.\n\n"
            "Le journal résume ce qui a été écarté, et l'aperçu suit le filtre.")))
        scope.addStretch()
        grid.addLayout(scope, r, 0, 1, 2)
        r += 1

        # exclure large / rattraper nommément : deux champs, UNE ligne
        self.ed_exclude = QLineEdit()
        self.ed_exclude.setPlaceholderText("ex. : ratio, /, average")
        self.ed_exclude.textChanged.connect(self._on_edit)
        self.ed_include = QLineEdit()
        self.ed_include.setPlaceholderText("ex. : Average Steps")
        self.ed_include.textChanged.connect(self._on_edit)
        filt = QHBoxLayout()
        filt.setContentsMargins(0, 0, 0, 0)
        filt.addWidget(QLabel("nom contient — exclure :"))
        filt.addWidget(self.ed_exclude, 1)
        filt.addWidget(QLabel("mais garder :"))
        filt.addWidget(self.ed_include, 1)
        filt.addWidget(self._help("Filtres par nom", (
            "Fragments séparés par des virgules. Une base écartée ne reçoit\n"
            "PAS la mesure : elle n'est pas créée du tout.\n\n"
            "EXCLURE — sert à ce que le formatString ne dit pas : un ratio en\n"
            "décimal (0,85) s'écrit comme un nombre, mais son NOM le trahit\n"
            "souvent (« Ratio … », « … / … », « Taux … »). Le nom complet d'un\n"
            "KPI y a sa place aussi, pour l'écarter entièrement.\n\n"
            "MAIS GARDER — le rattrapage nommé, qui PRIME sur tout : sur\n"
            "l'exclusion ci-contre ET sur le filtre de type.\n"
            "   exclure : average    mais garder : Average Steps\n"
            "écarte toutes les moyennes sauf celle-là — utile quand une\n"
            "mesure porte « average » dans son nom mais est en fait une somme.\n\n"
            "Insensible à la casse ET aux accents (« duree » attrape « Durée »).\n"
            "Le nom du KPI est testé en plus de celui de la base, donc exclure\n"
            "« Weight » écarte aussi « Weight cible ». Les branches héritent.\n\n"
            "L'aperçu ci-dessous suit ces filtres.")))
        holder_f = QWidget()
        holder_f.setLayout(filt)
        grid.addWidget(holder_f, r, 0, 1, 2)
        r += 1
        grid.addWidget(QLabel("DAX (en clair — sérialisé en lignes JSON à la sauvegarde) :"), r, 0, 1, 2)
        r += 1
        self.ed_dax = QPlainTextEdit()
        self.ed_dax.setFont(QFont("Consolas", 9))
        self.ed_dax.setTabChangesFocus(False)
        grid.addWidget(self.ed_dax, r, 0, 1, 2)
        grid.setRowStretch(r, 3)
        r += 1

        self.lbl_lint = QLabel("")
        self.lbl_lint.setWordWrap(True)
        self.lbl_lint.setStyleSheet(f"color:{YELLOW};")
        grid.addWidget(self.lbl_lint, r, 0, 1, 2)
        r += 1

        # aide-mémoire des jetons : REPLIÉ par défaut (il sert à l'écriture du
        # DAX, pas en permanence) — c'est là qu'est expliqué le piège
        # {kpi} / {kpiRef} de l'écart réel−cible en branche
        lbl_tokens = QLabel(TOKENS_HELP)
        lbl_tokens.setFont(QFont("Consolas", 8))
        lbl_tokens.setStyleSheet(f"color:{TEXT_DIM};")
        lbl_tokens.setTextInteractionFlags(Qt.TextSelectableByMouse)
        grid.addWidget(self._collapsible("Jetons disponibles", lbl_tokens),
                       r, 0, 1, 2)
        r += 1
        grid.addWidget(lbl_tokens, r, 0, 1, 2)
        r += 1

        grid.addWidget(QLabel("Aperçu des noms générés (bases × branches, selon la PORTÉE cochée) :"), r, 0, 1, 2)
        r += 1
        self.ed_preview = QPlainTextEdit()
        self.ed_preview.setReadOnly(True)
        self.ed_preview.setFont(QFont("Consolas", 9))
        self.ed_preview.setMaximumHeight(110)
        self.ed_preview.setStyleSheet(f"color:{TEXT_DIM};")
        grid.addWidget(self.ed_preview, r, 0, 1, 2)

        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        # tout changement du formulaire marque « modifié » + relint + aperçu
        for sig in (self.ed_name.textChanged, self.ed_desc.textChanged,
                    self.cmb_format.currentTextChanged, self.ed_folder.textChanged,
                    self.cmb_folder_var.currentIndexChanged,
                    self.cmb_datacat.currentTextChanged,
                    self.ed_dax.textChanged):
            sig.connect(self._on_edit)
        self.chk_infp.stateChanged.connect(self._on_edit)
        self.chk_kpi.stateChanged.connect(self._on_edit)
        self.chk_cible.stateChanged.connect(self._on_edit)
        return w

    def _build_raw_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ed_raw = QPlainTextEdit()
        self.ed_raw.setFont(QFont("Consolas", 9))
        self.ed_raw.textChanged.connect(self._on_edit)
        lay.addWidget(self.ed_raw, 1)
        bar = QHBoxLayout()
        btn_check = QPushButton("Valider le JSON")
        btn_check.clicked.connect(self._validate_raw)
        bar.addStretch()
        bar.addWidget(btn_check)
        lay.addLayout(bar)
        return w

    # ---- sous-onglet « Réglages globaux » ---------------------------------------

    def _help(self, titre, texte) -> QToolButton:
        """Petit « ⓘ » : survol = infobulle, clic = fenêtre. L'explication
        reste accessible sans occuper l'écran en permanence."""
        b = QToolButton()
        b.setText("ⓘ")
        b.setAutoRaise(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(texte)
        b.clicked.connect(lambda: QMessageBox.information(self, titre, texte))
        return b

    def _collapsible(self, titre, inner) -> QToolButton:
        """Bouton-flèche qui montre/cache `inner`, replié au départ. Pour les
        aide-mémoire qu'on consulte ponctuellement sans vouloir les garder à
        l'écran."""
        btn = QToolButton()
        btn.setText(titre)
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setArrowType(Qt.RightArrow)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setStyleSheet(f"QToolButton {{ border: none; color: {TEXT_DIM}; }}")
        inner.setVisible(False)

        def toggle(on):
            btn.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
            inner.setVisible(on)

        btn.toggled.connect(toggle)
        return btn

    def _form_group(self, title: str, rows) -> QGroupBox:
        """Groupe formulaire : rows = [(libellé|None, widget, tip|None)].
        libellé None = le widget occupe les deux colonnes (cases à cocher)."""
        gb = QGroupBox(title)
        grid = QGridLayout(gb)
        for i, (label, widget, tip) in enumerate(rows):
            if label is None:
                grid.addWidget(widget, i, 0, 1, 2)
            else:
                lbl = QLabel(label)
                if tip:
                    lbl.setToolTip(tip)
                grid.addWidget(lbl, i, 0)
                grid.addWidget(widget, i, 1)
        grid.setColumnStretch(1, 1)
        return gb

    def _build_global_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        outer = QVBoxLayout(content)

        def line(tip=None):
            e = QLineEdit()
            if tip:
                e.setToolTip(tip)
            e.textChanged.connect(self._mark_dirty)
            return e

        def check(text, tip=None):
            c = QCheckBox(text)
            if tip:
                c.setToolTip(tip)
            c.stateChanged.connect(self._mark_dirty)
            return c

        def multiline(tip=None):
            t = QPlainTextEdit()
            t.setMaximumHeight(66)
            t.setFont(QFont("Consolas", 9))
            if tip:
                t.setToolTip(tip)
            t.textChanged.connect(self._mark_dirty)
            return t

        # -- settings --
        self.g_sourceTable = line("Table des mesures de base (défaut _mesures).")
        self.g_sourceFolder = line("displayFolder des mesures de BASE à décliner (ex. _indicateurs). Vide = toutes.")
        self.g_dateColumn = line("Colonne de date pour {date} (ex. 'dim_Date'[Date]).")
        self.g_targetTable = line("Table où créer les mesures (vide = même table que la base).")
        self.g_folderPattern = line("Dossier des variations. {baseFolder} {base} {variation} {kpi} {branch}.")
        self.g_branchFolderPattern = line("Dossier racine d'une branche (ex. {baseFolder}\\__{branch}).")
        self.g_overwrite = check("overwriteExisting — réécrit les mesures générées existantes")
        self.g_removeOrphans = check("removeOrphans — supprime les mesures générées absentes du config")
        self.g_dryRun = check("dryRun — aperçu (l'onglet Modèle a aussi sa propre case)")

        # symboles des formats « delta » : les 3 sur UNE ligne, le pourquoi
        # derrière le ⓘ du groupe plutôt qu'en paragraphe permanent
        self.g_delta_pos = line()
        self.g_delta_neg = line()
        self.g_delta_zero = line()
        self.g_delta_fallback = line()
        self.lbl_delta_preview = QLabel("")
        self.lbl_delta_preview.setFont(QFont("Consolas", 8))
        self.lbl_delta_preview.setStyleSheet(f"color:{TEXT_DIM};")
        for w in (self.g_delta_pos, self.g_delta_neg, self.g_delta_zero,
                  self.g_delta_fallback):
            w.textChanged.connect(self._refresh_delta_preview)
        # -- Excel des indicateurs : LA définition, utilisée partout --
        gb_td = QGroupBox("Excel des indicateurs (TD_Indicateurs)")
        tdv = QVBoxLayout(gb_td)
        ligne1 = QHBoxLayout()
        self.g_td_path = QLineEdit()
        self.g_td_path.setPlaceholderText(
            "TD_Indicateurs.xlsx — relatif au dossier du .pbip")
        self.g_td_path.textChanged.connect(self._mark_dirty)
        self.g_td_path.editingFinished.connect(self._td_reload_columns)
        b_td = QPushButton("Parcourir…")
        b_td.clicked.connect(self._td_browse)
        b_td_rel = QPushButton("↻")
        b_td_rel.setMaximumWidth(32)
        b_td_rel.setToolTip("Recharger la liste des colonnes depuis l'Excel.")
        b_td_rel.clicked.connect(self._td_reload_columns)
        ligne1.addWidget(QLabel("Fichier :"))
        ligne1.addWidget(self.g_td_path, 1)
        ligne1.addWidget(b_td)
        ligne1.addWidget(b_td_rel)
        ligne1.addWidget(self._help("Excel des indicateurs", (
            "Le classeur qui décrit tes KPI, une ligne par mesure de base.\n"
            "Défini ICI une seule fois, et utilisé par TOUT l'outil :\n\n"
            "  · jetons <<label>> figés dans le DAX (colonnes ci-dessous) ;\n"
            "  · portée par KPI (<<allTables>>, <<each …>>) ;\n"
            "  · couleurs des matrices par KPI (onglet Rapport).\n\n"
            "L'onglet Rapport lit ce réglage au lieu d'avoir le sien :\n"
            "un seul endroit à tenir à jour, et plus de divergence possible.\n\n"
            "Chemin relatif = résolu depuis le dossier du .pbip, ce qui garde\n"
            "le config transportable d'un rapport à l'autre.")))
        tdv.addLayout(ligne1)
        ligne2 = QHBoxLayout()
        ligne2.addWidget(QLabel("Colonnes — clé :"))
        self.g_td_key = self._td_combo("mesure")
        ligne2.addWidget(self.g_td_key)
        ligne2.addWidget(QLabel("couleur de fond :"))
        self.g_td_fill = self._td_combo("couleur_fill")
        ligne2.addWidget(self.g_td_fill)
        ligne2.addWidget(QLabel("couleur de texte :"))
        self.g_td_text = self._td_combo("couleur_text")
        ligne2.addWidget(self.g_td_text)
        ligne2.addStretch()
        tdv.addLayout(ligne2)
        outer.addWidget(gb_td)

        outer.addWidget(self._form_group("Génération (settings)", [
            ("sourceTable :", self.g_sourceTable, None),
            ("sourceFolder :", self.g_sourceFolder, None),
            ("dateColumn :", self.g_dateColumn, None),
            ("targetTable :", self.g_targetTable, None),
            ("displayFolderPattern :", self.g_folderPattern, None),
            ("branchFolderPattern :", self.g_branchFolderPattern, None),
            (None, self.g_overwrite, None),
            (None, self.g_removeOrphans, None),
            (None, self.g_dryRun, None),
        ]))

        gb_d = QGroupBox("Formats « delta »")
        dv = QVBoxLayout(gb_d)
        drow = QHBoxLayout()
        drow.addWidget(QLabel("symboles :"))
        for lbl, w in (("positif", self.g_delta_pos), ("négatif", self.g_delta_neg),
                       ("zéro", self.g_delta_zero)):
            drow.addWidget(QLabel(lbl))
            w.setMaximumWidth(70)
            drow.addWidget(w)
        drow.addSpacing(12)
        drow.addWidget(QLabel("repli sans format :"))
        drow.addWidget(self.g_delta_fallback, 1)
        drow.addWidget(self._help("Formats « delta »", (
            "S'applique aux variations dont formatString = delta.\n\n"
            "SYMBOLES — placés devant la valeur, par section du format.\n"
            "Power BI n'ajoute aucun signe tout seul : même le « - » du négatif\n"
            "doit être écrit ici, sinon la valeur s'affiche nue.\n"
            "   +  /  -  /  (vide)      donne  +12,3   -12,3   0\n"
            "   ▲  /  ▼  /  (vide)      donne  ▲ 12,3  ▼ 12,3  0\n"
            "Avec une flèche, ne mets PAS de « - » : la flèche porte le sens et\n"
            "la valeur s'affiche en absolu.\n\n"
            "REPLI — format utilisé quand la mesure de BASE n'a aucun\n"
            "formatString. Sans lui le delta n'hérite de rien, n'a donc aucun\n"
            "format, et AUCUN signe n'apparaît quels que soient les symboles.\n"
            "Vide = ancien comportement (pas de format).")))
        dv.addLayout(drow)
        dv.addWidget(self.lbl_delta_preview)
        outer.addWidget(gb_d)

        # -- fieldParameter --
        self.g_fp_enabled = check("fieldParameter activé — générer les tables paramètre de champ")
        self.g_fp_tableNames = multiline("Tables « par calcul » (une par ligne) — copies identiques pour sélections indépendantes.")
        self.g_fp_tableNamesByKpi = multiline("Tables « par KPI » — une par ligne. C'est le KPI qu'on y choisit ;\nl'affichage suit la case « libellé » ci-dessous.")
        self.g_fp_byKpiUsesLabel = check(
            "byKpiUsesLabel — tables « par KPI » : afficher le LIBELLÉ du KPI")
        self.g_fp_byKpiUsesLabel.setToolTip(
            "Coché : l'affichage vient de la colonne « lookup — labelColumn »\n"
            "(LOOKUPVALUE sur la table de correspondance) — un libellé lisible.\n"
            "Décoché : le nom brut de la mesure (la colonne clé).\n"
            "Sans la table de correspondance dans le modèle, on retombe\n"
            "automatiquement sur le nom brut (avertissement au journal).")
        self.g_fp_tableNamesKpiBase = multiline("Tables « base = libellé KPI » (LOOKUPVALUE). Une par ligne.")
        self.g_fp_kpiColumn = line("Colonne KPI (défaut Indicateur).")
        self.g_fp_calcColumn = line("Colonne Calcul (défaut Calcul).")
        self.g_fp_branchColumn = line("Colonne Branche (défaut Branche).")
        self.g_fp_baseLabel = line("Libellé de la rangée « base » (ex. Réel).")
        self.g_fp_noBranchLabel = line("Valeur Branche hors branche (ex. Réel).")
        self.g_fp_includeBase = check("includeBase — inclure la mesure de base comme rangée")
        self.g_lkp_table = line("Table du LOOKUPVALUE des libellés (ex. TD_Indicateurs).")
        self.g_lkp_key = line("Colonne clé = nom de la mesure (ex. mesure).")
        self.g_lkp_label = line("Colonne du libellé affiché (ex. libelle_indicateur).")
        outer.addWidget(self._form_group("Paramètres de champ (fieldParameter)", [
            (None, self.g_fp_enabled, None),
            ("tableNames :", self.g_fp_tableNames, None),
            ("tableNamesByKpi :", self.g_fp_tableNamesByKpi, None),
            (None, self.g_fp_byKpiUsesLabel, None),
            ("tableNamesKpiBase :", self.g_fp_tableNamesKpiBase, None),
            ("kpiColumn :", self.g_fp_kpiColumn, None),
            ("calcColumn :", self.g_fp_calcColumn, None),
            ("branchColumn :", self.g_fp_branchColumn, None),
            ("baseLabel :", self.g_fp_baseLabel, None),
            ("noBranchLabel :", self.g_fp_noBranchLabel, None),
            (None, self.g_fp_includeBase, None),
            ("lookup — table :", self.g_lkp_table, None),
            ("lookup — keyColumn :", self.g_lkp_key, None),
            ("lookup — labelColumn :", self.g_lkp_label, None),
        ]))

        # -- mesures cibles (dossier dédié : bases supplémentaires) --
        gb_c = QGroupBox("Mesures cibles (dossier dédié)")
        cv = QVBoxLayout(gb_c)
        note_c = QLabel("Crée À LA MAIN la cible RACINE par KPI (ex. « Weight cible ») dans "
                        "un dossier dédié : le générateur la décline en TOUTES les variations "
                        "(comme un KPI, enveloppant [Weight cible]). Au paramètre : Indicateur "
                        "= le KPI (préfixe du nom), Calcul = « Cible » / « Cible 7d avg »… "
                        "(préfixé par le libellé ci-dessous), Branche normale. Ne mets que la "
                        "racine ; le dossier doit différer de sourceFolder (imbriqué = OK, "
                        "matché par sa feuille).")
        note_c.setWordWrap(True)
        note_c.setStyleSheet(f"color:{TEXT_DIM};")
        cv.addWidget(note_c)
        self.g_cible_table = QTableWidget(0, 2)
        self.g_cible_table.setHorizontalHeaderLabels(["Dossier (displayFolder)", "Calcul (libellé)"])
        self.g_cible_table.verticalHeader().setVisible(False)
        self.g_cible_table.setMaximumHeight(120)
        ch = self.g_cible_table.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.Stretch)
        ch.setSectionResizeMode(1, QHeaderView.Stretch)
        self.g_cible_table.itemChanged.connect(self._mark_dirty)
        cv.addWidget(self.g_cible_table)
        c_btns = QHBoxLayout()
        b_c_add = QPushButton("Ajouter")
        b_c_add.clicked.connect(lambda: self._cible_add_row("", "Cible"))
        b_c_del = QPushButton("Retirer")
        b_c_del.clicked.connect(self._cible_del_row)
        c_btns.addStretch()
        c_btns.addWidget(b_c_add)
        c_btns.addWidget(b_c_del)
        cv.addLayout(c_btns)
        outer.addWidget(gb_c)

        # -- portée par KPI --
        # une ligne : colonne + déduction. Le mode d'emploi est derrière le ⓘ.
        gb_t = QGroupBox("Portée par KPI")
        tv = QHBoxLayout(gb_t)
        self.g_kpitables_col = QLineEdit()
        self.g_kpitables_col.setPlaceholderText("vide = aucune portée déclarée")
        self.g_kpitables_col.textChanged.connect(self._mark_dirty)
        self.g_kpitables_auto = QCheckBox("déduire du DAX si la colonne ne dit rien")
        self.g_kpitables_auto.setToolTip(
            "Pour un KPI sans portée déclarée, lit les tables citées par le DAX\n"
            "de sa mesure de base : SUM('weight obs'[weight]) donne « weight obs ».\n"
            "Ce qui est déduit est écrit au journal — à vérifier : la déduction\n"
            "voit TOUTES les tables citées, y compris une table de dates servant\n"
            "à un filtre, ce qui n'est pas toujours la portée voulue.\n"
            "La colonne, elle, n'est jamais écrasée.")
        self.g_kpitables_auto.stateChanged.connect(self._mark_dirty)
        tv.addWidget(QLabel("Colonne de TD_Indicateurs :"))
        tv.addWidget(self.g_kpitables_col, 1)
        tv.addWidget(self.g_kpitables_auto)
        tv.addWidget(self._help("Portée par KPI", (
            "Donne à chaque KPI la liste de SES tables, pour les variations qui\n"
            "manipulent les filtres (part du total, moyenne toutes catégories…).\n\n"
            "SOURCE — une colonne de TD_Indicateurs où chaque KPI liste ses\n"
            "tables séparées par des virgules : « steps, dim_Date ». L'attribut\n"
            "vit ainsi avec LE RAPPORT, alors que ce measures_config.json voyage\n"
            "d'un rapport à l'autre. Faute de colonne, coche « déduire du DAX ».\n\n"
            "DANS LE DAX D'UNE VARIATION — le jeton générique :\n"
            "   <<each ALLSELECTED({table})>>\n"
            "répète TON fragment une fois par table, séparé par des virgules :\n"
            "   1 table  -> ALLSELECTED('steps')\n"
            "   2 tables -> ALLSELECTED('steps'), ALLSELECTED('dim_Date')\n"
            "La fonction vient de toi : ALL, ALLSELECTED, REMOVEFILTERS,\n"
            "ALLEXCEPT, VALUES, CROSSFILTER… {table} = 'steps' (référence DAX),\n"
            "{tableName} = steps (nom nu). {table} peut revenir plusieurs fois :\n"
            "   <<each ALLEXCEPT({table}, {table}[Date])>>\n\n"
            "Raccourcis, si tu ne veux rien écrire : <<allTables>>,\n"
            "<<removeFilters>>, <<tables>> (la liste nue).\n\n"
            "Cellule vide et déduction inactive = ce KPI n'a pas la variation\n"
            "(le journal le nomme). La mesure Switch n'en a jamais : elle\n"
            "agrège tous les KPI, aucune portée unique ne lui convient.")))
        outer.addWidget(gb_t)

        # -- switch --
        self.g_sw_enabled = check("switch activé — mesure Switch KPI + ses variations")
        self.g_sw_name = line("Nom de la mesure switch (ex. Switch KPI).")
        self.g_sw_selector = line("Colonne sélectrice (ex. 'TD_KPI'[mesure]).")
        self.g_sw_folder = line("Dossier de la mesure switch (ex. _switch).")
        self.g_sw_format = line("Format statique du switch (ex. #,0.0).")
        self.g_sw_dynamicFormat = check("dynamicFormat — le format suit le KPI sélectionné (à valider)")
        outer.addWidget(self._form_group("Mesure Switch (switch)", [
            (None, self.g_sw_enabled, None),
            ("name :", self.g_sw_name, None),
            ("selector :", self.g_sw_selector, None),
            ("displayFolder :", self.g_sw_folder, None),
            ("formatString :", self.g_sw_format, None),
            (None, self.g_sw_dynamicFormat, None),
        ]))

        # -- attributs codés en dur (au lieu de LOOKUPVALUE) --
        gb_hc = QGroupBox("Attributs codés en dur (au lieu de LOOKUPVALUE)")
        hcv = QVBoxLayout(gb_hc)
        note_hc = QLabel("Dans le DAX d'une variation, écris « <<label>> » : à la génération il "
                         "est remplacé par la valeur de la colonne pour le KPI (lue dans l'Excel), "
                         "au lieu d'un LOOKUPVALUE coûteux. Ex. <<direction>> → 1 / -1 "
                         "(texte : quote toi-même « \"<<label>>\" »).")
        note_hc.setWordWrap(True)
        note_hc.setStyleSheet(f"color:{TEXT_DIM};")
        hcv.addWidget(note_hc)
        self.g_hc_table = QTableWidget(0, 2)
        self.g_hc_table.setHorizontalHeaderLabels(["Label (jeton <<…>>)", "Colonne"])
        self.g_hc_table.verticalHeader().setVisible(False)
        self.g_hc_table.setMaximumHeight(130)
        hh = self.g_hc_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.g_hc_table.itemChanged.connect(self._mark_dirty)
        hcv.addWidget(self.g_hc_table)
        hc_btns = QHBoxLayout()
        b_hc_add = QPushButton("Ajouter")
        b_hc_add.clicked.connect(lambda: self._hc_add_row("", ""))
        b_hc_del = QPushButton("Retirer")
        b_hc_del.clicked.connect(self._hc_del_row)
        hc_btns.addStretch()
        hc_btns.addWidget(b_hc_add)
        hc_btns.addWidget(b_hc_del)
        hcv.addLayout(hc_btns)
        outer.addWidget(gb_hc)

        # -- branches --
        gb_b = QGroupBox("Branches (variations-de-variations)")
        vb = QVBoxLayout(gb_b)
        note = QLabel("Coche une variation pour qu'elle devienne une BRANCHE : ses mesures sont "
                      "redéclinées (ex. YTD → YTD PY, YTD 7d avg…).")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_DIM};")
        vb.addWidget(note)
        self.g_branches = QListWidget()
        self.g_branches.setStyleSheet(checkable_list_stylesheet())
        self.g_branches.setMaximumHeight(110)
        self.g_branches.itemChanged.connect(self._on_branch_toggle)
        vb.addWidget(self.g_branches)

        # restriction : quelles variations la branche APPLIQUE
        pick = QHBoxLayout()
        pick.addWidget(QLabel("Restreindre la branche :"))
        self.g_branch_pick = QComboBox()
        self.g_branch_pick.currentIndexChanged.connect(self._on_branch_pick)
        pick.addWidget(self.g_branch_pick, 1)
        vb.addLayout(pick)
        note2 = QLabel("Coche les variations que cette branche applique (toutes par défaut). "
                       "Décoche pour exclure — ex. une cible autonome en {kpi} qui n'a pas à "
                       "être re-forkée.")
        note2.setWordWrap(True)
        note2.setStyleSheet(f"color:{TEXT_DIM};")
        vb.addWidget(note2)
        self.g_branch_restrict = QListWidget()
        self.g_branch_restrict.setStyleSheet(checkable_list_stylesheet())
        self.g_branch_restrict.setMaximumHeight(120)
        self.g_branch_restrict.itemChanged.connect(self._on_branch_restrict_changed)
        vb.addWidget(self.g_branch_restrict)
        outer.addWidget(gb_b)

        outer.addStretch()
        scroll.setWidget(content)
        return scroll

    def _load_global(self):
        """Peuple les widgets globaux depuis le config (à l'ouverture de l'onglet)."""
        self._loading = True
        s = self._config.get("settings") or {}
        self.g_sourceTable.setText(s.get("sourceTable", "") or "")
        self.g_sourceFolder.setText(s.get("sourceFolder", "") or "")
        self.g_dateColumn.setText(s.get("dateColumn", "") or "")
        self.g_targetTable.setText(s.get("targetTable", "") or "")
        self.g_folderPattern.setText(s.get("displayFolderPattern", "") or "")
        self.g_branchFolderPattern.setText(s.get("branchFolderPattern", "") or "")
        self.g_overwrite.setChecked(bool(s.get("overwriteExisting", True)))
        sym = s.get("deltaSymbols") or {}
        self.g_delta_pos.setText(sym.get("positive", gm.DELTA_SYMBOLS["positive"]))
        self.g_delta_neg.setText(sym.get("negative", gm.DELTA_SYMBOLS["negative"]))
        self.g_delta_zero.setText(sym.get("zero", gm.DELTA_SYMBOLS["zero"]))
        self.g_delta_fallback.setText(
            s.get("deltaFallbackFormat", gm.DELTA_FALLBACK) or "")
        self._refresh_delta_preview()
        self.g_removeOrphans.setChecked(bool(s.get("removeOrphans", False)))
        self.g_dryRun.setChecked(bool(s.get("dryRun", False)))

        fp = self._config.get("fieldParameter") or {}
        # bloc absent = désactivé (comme le csx : fpConfig null -> off)
        self.g_fp_enabled.setChecked(bool(fp.get("enabled", True)) if "fieldParameter" in self._config else False)
        self.g_fp_tableNames.setPlainText(list_to_lines(fp.get("tableNames")))
        self.g_fp_tableNamesByKpi.setPlainText(list_to_lines(fp.get("tableNamesByKpi")))
        self.g_fp_byKpiUsesLabel.setChecked(bool(fp.get("byKpiUsesLabel", True)))
        self.g_fp_tableNamesKpiBase.setPlainText(list_to_lines(fp.get("tableNamesKpiBase")))
        self.g_fp_kpiColumn.setText(fp.get("kpiColumn", "") or "")
        self.g_fp_calcColumn.setText(fp.get("calcColumn", "") or "")
        self.g_fp_branchColumn.setText(fp.get("branchColumn", "") or "")
        self.g_fp_baseLabel.setText(fp.get("baseLabel", "") or "")
        self.g_fp_noBranchLabel.setText(fp.get("noBranchLabel", "") or "")
        self.g_fp_includeBase.setChecked(bool(fp.get("includeBase", True)))
        lkp = fp.get("kpiLabelLookup") or {}
        self.g_lkp_table.setText(lkp.get("table", "") or "")
        self.g_lkp_key.setText(lkp.get("keyColumn", "") or "")
        self.g_lkp_label.setText(lkp.get("labelColumn", "") or "")

        sw = self._config.get("switch") or {}
        self.g_sw_enabled.setChecked(bool(sw.get("enabled", True)) if "switch" in self._config else False)
        self.g_sw_name.setText(sw.get("name", "") or "")
        self.g_sw_selector.setText(sw.get("selector", "") or "")
        self.g_sw_folder.setText(sw.get("displayFolder", "") or "")
        self.g_sw_format.setText(sw.get("formatString", "") or "")
        self.g_sw_dynamicFormat.setChecked(bool(sw.get("dynamicFormat", True)))

        hc = self._config.get("hardcodedAttributes") or {}
        td = gm.indicateurs_xlsx(self._config)
        self.g_td_path.setText(td["path"])
        self.g_td_key.setCurrentText(td["keyColumn"])
        self.g_td_fill.setCurrentText(td["fillColumn"])
        self.g_td_text.setCurrentText(td["textColumn"])
        self._td_reload_columns()
        self.g_hc_table.setRowCount(0)
        for label, col in (hc.get("tokens") or {}).items():
            self._hc_add_row(label, col)

        _kt = self._config.get("kpiTables") or {}
        self.g_kpitables_col.setText(_kt.get("column", "") or "")
        self.g_kpitables_auto.setChecked(bool(_kt.get("fromMeasureDax")))

        self.g_cible_table.setRowCount(0)
        for spec in (self._config.get("kpiMeasureFolders") or []):
            if isinstance(spec, dict):
                self._cible_add_row(spec.get("folder", "") or "",
                                    spec.get("calcul", "") or "Cible")

        self._load_branches()
        self._loading = False

    def _load_branches(self):
        """Liste cochable des variations (cochée = branche) + état des
        restrictions par branche, puis peuple l'éditeur de restriction."""
        self.g_branches.clear()
        branches = self._config.get("branches") or {}
        seen = set()
        for vid in self._variations():
            seen.add(vid)
            item = QListWidgetItem(vid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if vid in branches else Qt.Unchecked)
            item.setData(Qt.UserRole, vid)
            self.g_branches.addItem(item)
        for vid in branches:            # clés orphelines (id absent des variations)
            if vid not in seen:
                item = QListWidgetItem(vid + "  (⚠ variation absente)")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, vid)
                self.g_branches.addItem(item)

        # état des restrictions : branche -> set des variations appliquées
        self._branch_restrict = {}
        for b, bval in branches.items():
            applicable = set(self._applicable_vars(b))
            if isinstance(bval, dict) and isinstance(bval.get("variations"), list):
                self._branch_restrict[b] = set(bval["variations"]) & applicable
            else:
                self._branch_restrict[b] = applicable   # pas de restriction = toutes
        self._branch_pick_current = None
        self._reload_branch_pick(list(branches.keys()))

    # ---- restriction d'une branche (quelles variations elle applique) ----------

    def _applicable_vars(self, branch_id) -> list:
        """Variations qu'une branche PEUT appliquer (toutes sauf elle-même),
        dans l'ordre du config."""
        return [v for v in self._variations() if v != branch_id]

    def _checked_branch_ids(self) -> list:
        return [self.g_branches.item(i).data(Qt.UserRole)
                for i in range(self.g_branches.count())
                if self.g_branches.item(i).checkState() == Qt.Checked]

    def _on_branch_toggle(self, *_):
        """Une variation vient d'être (dé)cochée comme branche."""
        if self._loading:
            return
        self._set_dirty(True)
        self._save_branch_restrict()
        branch_ids = self._checked_branch_ids()
        for b in branch_ids:                        # nouvelles : toutes par défaut
            if b not in self._branch_restrict:
                self._branch_restrict[b] = set(self._applicable_vars(b))
        for b in list(self._branch_restrict):       # retirées
            if b not in branch_ids:
                del self._branch_restrict[b]
        self._reload_branch_pick(branch_ids)

    def _reload_branch_pick(self, branch_ids):
        self.g_branch_pick.blockSignals(True)
        self.g_branch_pick.clear()
        self.g_branch_pick.addItems(list(branch_ids))
        self.g_branch_pick.blockSignals(False)
        self._branch_pick_current = None
        if branch_ids:
            self._show_branch_restrict(branch_ids[0])
        else:
            self.g_branch_restrict.blockSignals(True)
            self.g_branch_restrict.clear()
            self.g_branch_restrict.blockSignals(False)

    def _show_branch_restrict(self, branch_id):
        self._branch_pick_current = branch_id
        included = self._branch_restrict.get(branch_id, set(self._applicable_vars(branch_id)))
        self.g_branch_restrict.blockSignals(True)
        self.g_branch_restrict.clear()
        for v in self._applicable_vars(branch_id):
            it = QListWidgetItem(v)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if v in included else Qt.Unchecked)
            self.g_branch_restrict.addItem(it)
        self.g_branch_restrict.blockSignals(False)
        idx = self.g_branch_pick.findText(branch_id)
        if idx >= 0 and self.g_branch_pick.currentIndex() != idx:
            self.g_branch_pick.blockSignals(True)
            self.g_branch_pick.setCurrentIndex(idx)
            self.g_branch_pick.blockSignals(False)

    def _save_branch_restrict(self):
        """Persiste la restriction affichée dans self._branch_restrict."""
        b = self._branch_pick_current
        if not b:
            return
        self._branch_restrict[b] = {
            self.g_branch_restrict.item(i).text()
            for i in range(self.g_branch_restrict.count())
            if self.g_branch_restrict.item(i).checkState() == Qt.Checked
        }

    def _on_branch_pick(self, index):
        if self._loading or index < 0:
            return
        self._save_branch_restrict()
        self._show_branch_restrict(self.g_branch_pick.itemText(index))

    def _on_branch_restrict_changed(self, *_):
        if self._loading:
            return
        self._set_dirty(True)
        self._save_branch_restrict()

    def _commit_global(self):
        """Reporte les widgets globaux dans le config (clés vides retirées ;
        blocs fieldParameter/switch absents non matérialisés s'ils restent
        désactivés — préserve « absent = off »)."""
        s = self._config.setdefault("settings", {})

        def sset(key, val):
            if val:
                s[key] = val
            else:
                s.pop(key, None)

        sset("sourceTable", self.g_sourceTable.text().strip())
        sset("sourceFolder", self.g_sourceFolder.text().strip())
        sset("dateColumn", self.g_dateColumn.text().strip())
        sset("targetTable", self.g_targetTable.text().strip())
        sset("displayFolderPattern", self.g_folderPattern.text().strip())
        sset("branchFolderPattern", self.g_branchFolderPattern.text().strip())
        # Excel des indicateurs : bloc unique (on n'écrit que le non-défaut)
        td = {"path": self.g_td_path.text().strip(),
              "keyColumn": self.g_td_key.currentText().strip(),
              "fillColumn": self.g_td_fill.currentText().strip(),
              "textColumn": self.g_td_text.currentText().strip()}
        if self.project:                    # re-relativiser si possible
            try:
                td["path"] = str(Path(td["path"]).relative_to(self.project.folder))
            except ValueError:
                pass
        td = {k: v for k, v in td.items()
              if v and v != gm.INDICATEURS_DEFAUT.get(k)}
        if td:
            self._config["indicateursXlsx"] = td
        else:
            self._config.pop("indicateursXlsx", None)
        # les anciennes surcharges locales ne sont plus écrites
        for bloc, cle in (("hardcodedAttributes", "xlsx"),
                          ("hardcodedAttributes", "keyColumn"),
                          ("kpiTables", "xlsx"), ("kpiTables", "keyColumn")):
            if isinstance(self._config.get(bloc), dict):
                self._config[bloc].pop(cle, None)
        s["overwriteExisting"] = self.g_overwrite.isChecked()
        s["removeOrphans"] = self.g_removeOrphans.isChecked()
        s["dryRun"] = self.g_dryRun.isChecked()
        # symboles delta : on n'écrit le bloc que s'il s'écarte des défauts
        # (sinon on laisse le config propre). Un symbole VIDE est significatif
        # (« pas de signe »), donc on ne peut pas se contenter d'un `if val`.
        sym = {"positive": self.g_delta_pos.text(),
               "negative": self.g_delta_neg.text(),
               "zero": self.g_delta_zero.text()}
        if sym != gm.DELTA_SYMBOLS:
            s["deltaSymbols"] = sym
        else:
            s.pop("deltaSymbols", None)
        fb = self.g_delta_fallback.text()
        if fb != gm.DELTA_FALLBACK:
            s["deltaFallbackFormat"] = fb
        else:
            s.pop("deltaFallbackFormat", None)

        fp_on = self.g_fp_enabled.isChecked()
        if fp_on or "fieldParameter" in self._config:
            fp = self._config.setdefault("fieldParameter", {})
            fp["enabled"] = fp_on

            def fset(key, val):
                if val:
                    fp[key] = val
                else:
                    fp.pop(key, None)

            def fset_list(key, text):
                lst = lines_to_list(text)
                if lst:
                    fp[key] = lst
                else:
                    fp.pop(key, None)

            fset_list("tableNames", self.g_fp_tableNames.toPlainText())
            fset_list("tableNamesByKpi", self.g_fp_tableNamesByKpi.toPlainText())
            fp["byKpiUsesLabel"] = self.g_fp_byKpiUsesLabel.isChecked()
            fset_list("tableNamesKpiBase", self.g_fp_tableNamesKpiBase.toPlainText())
            fset("kpiColumn", self.g_fp_kpiColumn.text().strip())
            fset("calcColumn", self.g_fp_calcColumn.text().strip())
            fset("branchColumn", self.g_fp_branchColumn.text().strip())
            fset("baseLabel", self.g_fp_baseLabel.text().strip())
            fset("noBranchLabel", self.g_fp_noBranchLabel.text().strip())
            fp["includeBase"] = self.g_fp_includeBase.isChecked()
            lkp = {}
            for key, w in (("table", self.g_lkp_table), ("keyColumn", self.g_lkp_key),
                           ("labelColumn", self.g_lkp_label)):
                if w.text().strip():
                    lkp[key] = w.text().strip()
            if lkp:
                fp["kpiLabelLookup"] = lkp
            else:
                fp.pop("kpiLabelLookup", None)

        sw_on = self.g_sw_enabled.isChecked()
        if sw_on or "switch" in self._config:
            sw = self._config.setdefault("switch", {})
            sw["enabled"] = sw_on

            def swset(key, val):
                if val:
                    sw[key] = val
                else:
                    sw.pop(key, None)

            swset("name", self.g_sw_name.text().strip())
            swset("selector", self.g_sw_selector.text().strip())
            swset("displayFolder", self.g_sw_folder.text().strip())
            swset("formatString", self.g_sw_format.text().strip())
            sw["dynamicFormat"] = self.g_sw_dynamicFormat.isChecked()

        # attributs codés en dur
        tokens = {}
        for r in range(self.g_hc_table.rowCount()):
            item = self.g_hc_table.item(r, 0)
            combo = self.g_hc_table.cellWidget(r, 1)
            label = item.text().strip() if item else ""
            col = combo.currentText().strip() if combo else ""
            if label and col:
                tokens[label] = col
        if tokens or "hardcodedAttributes" in self._config:
            hcd = self._config.setdefault("hardcodedAttributes", {})
            if tokens:
                hcd["tokens"] = tokens
            else:
                hcd.pop("tokens", None)
            if not hcd:                              # tout vide -> pas de bloc
                self._config.pop("hardcodedAttributes", None)

        # portée par KPI : nom de colonne + déduction (le reste de la spec —
        # xlsx, keyColumn — est préservé s'il existe)
        col = self.g_kpitables_col.text().strip()
        auto = self.g_kpitables_auto.isChecked()
        if col or auto:
            spec = dict(self._config.get("kpiTables") or {})
            if col:
                spec["column"] = col
            else:
                spec.pop("column", None)
            if auto:
                spec["fromMeasureDax"] = True
            else:
                spec.pop("fromMeasureDax", None)
            self._config["kpiTables"] = spec
        else:
            self._config.pop("kpiTables", None)

        # mesures cibles (dossier dédié)
        cibles = []
        for r in range(self.g_cible_table.rowCount()):
            fi = self.g_cible_table.item(r, 0)
            ci = self.g_cible_table.item(r, 1)
            folder = fi.text().strip() if fi else ""
            calcul = ci.text().strip() if ci else ""
            if folder:                               # dossier vide -> rangée ignorée
                cibles.append({"folder": folder, "calcul": calcul or "Cible"})
        if cibles:
            self._config["kpiMeasureFolders"] = cibles
        else:
            self._config.pop("kpiMeasureFolders", None)

        self._save_branch_restrict()                 # persiste la restriction affichée
        old = self._config.get("branches") or {}
        new_branches = {}
        for i in range(self.g_branches.count()):
            item = self.g_branches.item(i)
            if item.checkState() != Qt.Checked:
                continue
            b = item.data(Qt.UserRole)
            value = dict(old.get(b) or {}) if isinstance(old.get(b), dict) else {}
            applicable = self._applicable_vars(b)    # ordre du config
            included = self._branch_restrict.get(b, set(applicable))
            if set(included) >= set(applicable):     # toutes appliquées -> pas de restriction
                value.pop("variations", None)
            else:
                value["variations"] = [v for v in applicable if v in included]
            new_branches[b] = value
        if new_branches:
            self._config["branches"] = new_branches
        else:
            self._config.pop("branches", None)

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self._set_dirty(True)

    # ---- attributs codés en dur (table label/colonne) --------------------------

    def _hc_xlsx_path(self) -> Path:
        raw = str(self._td_path_resolu()) or "TD_Indicateurs.xlsx"
        p = Path(raw)
        if not p.is_absolute() and self.project:
            p = self.project.folder / p
        return p

    def _hc_columns(self) -> list:
        return model_reader.excel_headers(self._hc_xlsx_path())

    def _hc_make_combo(self, current):
        c = QComboBox()
        c.setEditable(True)
        c.setInsertPolicy(QComboBox.NoInsert)
        items = list(self._hc_columns())
        if current and current not in items:
            items.append(current)
        c.addItems(items)
        c.setCurrentText(current or "")
        c.currentTextChanged.connect(self._mark_dirty)
        return c

    def _hc_add_row(self, label, column):
        r = self.g_hc_table.rowCount()
        self.g_hc_table.insertRow(r)
        self.g_hc_table.setItem(r, 0, QTableWidgetItem(label))
        self.g_hc_table.setCellWidget(r, 1, self._hc_make_combo(column))
        self._mark_dirty()

    def _hc_del_row(self):
        r = self.g_hc_table.currentRow()
        if r >= 0:
            self.g_hc_table.removeRow(r)
            self._mark_dirty()




    def _cible_add_row(self, folder, calcul):
        r = self.g_cible_table.rowCount()
        self.g_cible_table.insertRow(r)
        self.g_cible_table.setItem(r, 0, QTableWidgetItem(folder or ""))
        self.g_cible_table.setItem(r, 1, QTableWidgetItem(calcul or "Cible"))
        self._mark_dirty()

    def _cible_del_row(self):
        r = self.g_cible_table.currentRow()
        if r >= 0:
            self.g_cible_table.removeRow(r)
            self._mark_dirty()

    def _hc_reload_columns(self):
        cols = list(self._hc_columns())
        for r in range(self.g_hc_table.rowCount()):
            combo = self.g_hc_table.cellWidget(r, 1)
            if combo is None:
                continue
            cur = combo.currentText().strip()
            items = list(cols)
            if cur and cur not in items:
                items.append(cur)
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            combo.setCurrentText(cur)
            combo.blockSignals(False)

    # ---- projet ------------------------------------------------------------

    def set_project(self, project):
        self.project = project
        self.model_panel.set_project(project)   # sous-onglet « Générer »
        path = project.config_json
        if not path.exists():
            self._config = {}
            self._current = None
            self.lst.clear()
            self.ed_raw.blockSignals(True)
            self.ed_raw.setPlainText("")
            self.ed_raw.blockSignals(False)
            self.lbl_hint.setText(
                "Aucun measures_config.json chargé — attendu : " + str(path)
                + "\nClique « Config… » dans la barre du haut pour choisir celui de "
                  "CE rapport (au travail il peut vivre dans un autre dossier).")
            self.lbl_hint.show()
            for w in (self.inner, self.btn_save, self.btn_reload):
                w.setEnabled(False)
            self._set_dirty(False)
            return
        self.lbl_hint.hide()
        for w in (self.inner, self.btn_save, self.btn_reload):
            w.setEnabled(True)
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            self._config = json.loads(self.project.config_json.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            QMessageBox.critical(self, "measures_config.json",
                                 f"Illisible : {e}\nCorrige-le dans le sous-onglet JSON brut.")
            self._config = {}
        self._populate_list()
        self.ed_raw.blockSignals(True)
        self.ed_raw.setPlainText(json.dumps(self._config, indent=2, ensure_ascii=False))
        self.ed_raw.blockSignals(False)
        # revient toujours à « Variations » après un (re)chargement : les widgets
        # globaux se rechargeront à la prochaine ouverture de leur onglet
        self.inner.blockSignals(True)
        self.inner.setCurrentIndex(IDX_VARIATIONS)
        self.inner.blockSignals(False)
        self._inner_prev = IDX_VARIATIONS
        self._set_dirty(False)

    def _reload(self):
        if self.project:
            self._load_from_disk()

    # ---- liste des variations -----------------------------------------------

    def _selection_actives(self):
        """Ids actifs DANS CE RAPPORT, ou None si aucun choix n'a été fait
        (= toutes, comme avant). Lu dans le fichier posé à côté du .pbip,
        jamais dans le config : celui-ci est le catalogue partagé."""
        if not self.project:
            return None
        return gm.read_selection(self.project.folder)

    def _cochees(self) -> list:
        return [self.lst.item(i).text() for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.Checked]

    def _on_variation_checked(self, item):
        """Une case a bougé : on écrit la sélection du rapport tout de
        suite. Elle ne passe PAS par le config — donc aucun risque de la
        propager au prochain rapport qui réutilisera ce catalogue."""
        if self._loading or not self.project:
            return
        gm.write_selection(self.project.folder, self._cochees(),
                           list(self._variations()))
        self._refresh_catalogue_label()

    def _refresh_catalogue_label(self):
        total = len(self._variations())
        actifs = len(self._cochees()) if self.lst.count() else total
        if not self.project:
            self.lbl_catalogue.setText("")
        elif actifs == total:
            self.lbl_catalogue.setText(
                f"{total} variation(s) — toutes actives dans ce rapport")
        else:
            self.lbl_catalogue.setText(
                f"{actifs} active(s) sur {total} dans CE rapport")

    def _tout_cocher(self, etat):
        self._loading = True
        for i in range(self.lst.count()):
            self.lst.item(i).setCheckState(Qt.Checked if etat else Qt.Unchecked)
        self._loading = False
        self._on_variation_checked(None)

    def _variations(self) -> dict:
        return self._config.setdefault("variations", {})

    def _populate_list(self, select: str | None = None):
        self._loading = True
        self._current = None
        self.lst.clear()
        actives = self._selection_actives()
        for vid in self._variations():
            it = QListWidgetItem(vid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if (actives is None or vid in actives)
                             else Qt.Unchecked)
            self.lst.addItem(it)
        self._loading = False
        self._refresh_catalogue_label()
        if self.lst.count():
            names = [self.lst.item(i).text() for i in range(self.lst.count())]
            target = select if select in names else names[0]
            self.lst.setCurrentRow(names.index(target))

    def _on_select(self, vid: str):
        if self._loading:
            return
        self._commit_form()          # garde les édits de la variation quittée
        self._current = vid or None
        self._load_form()

    # ---- formulaire <-> config ------------------------------------------------

    def _rebuild_folder_var(self, selected: str):
        """Choix du dossier hôte : « son propre dossier » + les AUTRES
        variations ; une valeur orpheline (id disparu) est gardée, marquée."""
        self.cmb_folder_var.clear()
        self.cmb_folder_var.addItem("(son propre dossier)", "")
        for vid in self._variations():
            if vid != self._current:
                self.cmb_folder_var.addItem(vid, vid)
        idx = self.cmb_folder_var.findData(selected)
        if idx < 0 and selected:
            self.cmb_folder_var.addItem(selected + "  (⚠ variation absente)", selected)
            idx = self.cmb_folder_var.count() - 1
        self.cmb_folder_var.setCurrentIndex(max(idx, 0))

    def _load_form(self):
        v = self._variations().get(self._current)
        self._loading = True
        if v is None:
            for ed in (self.ed_name, self.ed_desc, self.ed_folder):
                ed.setText("")
            self.cmb_format.setCurrentText("")
            self._rebuild_folder_var("")
            self.cmb_datacat.setCurrentText("")
            self.chk_infp.setChecked(False)
            self.chk_kpi.setChecked(True)
            self.chk_cible.setChecked(False)
            self.ed_dax.setPlainText("")
        else:
            self.ed_name.setText(v.get("namePattern", ""))
            self.ed_desc.setText(v.get("description", ""))
            self.cmb_format.setCurrentText(v.get("formatString", ""))
            self.ed_folder.setText(v.get("displayFolder", ""))
            self._rebuild_folder_var(v.get("folderVariation", ""))
            self.cmb_datacat.setCurrentText(v.get("dataCategory", ""))
            self.chk_infp.setChecked(bool(v.get("inFieldParameter", False)))
            self.chk_kpi.setChecked(bool(v.get("appliesToKpi", True)))
            self.chk_cible.setChecked(bool(v.get("appliesToCibles", False)))
            self._refresh_kind_items(v.get("appliesToFormats") or None)
            self.ed_exclude.setText(
                ", ".join(v.get("excludeNameContains") or []))
            self.ed_include.setText(
                ", ".join(v.get("includeNameContains") or []))
            self.ed_dax.setPlainText(dax_to_text(v.get("dax")))
        self._loading = False
        self._refresh_lint_preview()

    def _commit_form(self):
        """Reporte le formulaire dans le config (variation affichée). Les clés
        vides optionnelles sont retirées ; les clés inconnues sont préservées."""
        v = self._variations().get(self._current)
        if v is None:
            return

        def put(key, value, keep_empty=False):
            if value or keep_empty:
                v[key] = value
            else:
                v.pop(key, None)

        put("namePattern", self.ed_name.text(), keep_empty=True)
        put("description", self.ed_desc.text())
        put("formatString", self.cmb_format.currentText().strip())
        put("displayFolder", self.ed_folder.text())
        put("folderVariation", self.cmb_folder_var.currentData() or "")
        put("dataCategory", self.cmb_datacat.currentText().strip())
        v["inFieldParameter"] = self.chk_infp.isChecked()
        # portée : on n'écrit que le NON-défaut (appliesToKpi défaut True,
        # appliesToCibles défaut False) — garde les configs existantes propres
        if self.chk_kpi.isChecked():
            v.pop("appliesToKpi", None)
        else:
            v["appliesToKpi"] = False
        if self.chk_cible.isChecked():
            v["appliesToCibles"] = True
        else:
            v.pop("appliesToCibles", None)
        # « tous » = aucun filtre : rien n'est alors écrit dans le config
        if self.cmb_kinds.all_checked():
            v.pop("appliesToFormats", None)
        else:
            v["appliesToFormats"] = self.cmb_kinds.checked()
        motifs = [x.strip() for x in self.ed_exclude.text().split(",") if x.strip()]
        if motifs:
            v["excludeNameContains"] = motifs
        else:
            v.pop("excludeNameContains", None)
        gardes = [x.strip() for x in self.ed_include.text().split(",") if x.strip()]
        if gardes:
            v["includeNameContains"] = gardes
        else:
            v.pop("includeNameContains", None)
        v["dax"] = text_to_dax(self.ed_dax.toPlainText())

    # ---- boutons variations ----------------------------------------------------

    def _ask_id(self, title: str, default: str = "") -> str | None:
        vid, ok = QInputDialog.getText(self, title, "Identifiant de la variation :",
                                       text=default)
        vid = (vid or "").strip()
        if not ok or not vid:
            return None
        if vid in self._variations():
            QMessageBox.warning(self, title, f"« {vid} » existe déjà.")
            return None
        return vid

    def _add(self):
        vid = self._ask_id("Ajouter une variation")
        if vid:
            self._variations()[vid] = dict(NEW_VARIATION)
            self._set_dirty(True)
            self._populate_list(select=vid)

    def _duplicate(self):
        if not self._current:
            return
        self._commit_form()
        vid = self._ask_id("Dupliquer la variation", self._current + " copie")
        if vid:
            self._variations()[vid] = json.loads(
                json.dumps(self._variations()[self._current]))
            self._set_dirty(True)
            self._populate_list(select=vid)

    def _rename(self):
        if not self._current:
            return
        self._commit_form()
        vid = self._ask_id("Renommer la variation", self._current)
        if vid:
            old = self._current
            # reconstruit le dict en conservant l'ordre des variations
            self._config["variations"] = {
                (vid if k == old else k): v for k, v in self._variations().items()
            }
            self._current = vid
            self._set_dirty(True)
            self._populate_list(select=vid)

    def _move(self, delta: int):
        """Déplace la variation courante d'un cran (l'ordre du dict = l'ordre
        de génération et de tri dans le paramètre de champ)."""
        if not self._current:
            return
        self._commit_form()
        old = self._variations()
        vids = list(old.keys())
        i = vids.index(self._current)
        j = i + delta
        if j < 0 or j >= len(vids):
            return
        vids[i], vids[j] = vids[j], vids[i]
        self._config["variations"] = {v: old[v] for v in vids}
        self._set_dirty(True)
        self._populate_list(select=self._current)

    def _delete(self):
        if not self._current:
            return
        if QMessageBox.question(
            self, "Supprimer",
            f"Supprimer la variation « {self._current} » du config ?\n"
            "(À la prochaine génération, removeOrphans supprimera ses mesures.)",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        self._variations().pop(self._current, None)
        self._current = None
        self._set_dirty(True)
        self._populate_list()

    # ---- lint + aperçu ----------------------------------------------------------

    def _refresh_lint_preview(self):
        texts = [self.ed_name.text(), self.ed_folder.text(),
                 self.ed_desc.text(), self.ed_dax.toPlainText()]
        unknown = sorted({
            m for t in texts for m in PLACEHOLDER_RE.findall(t)
            if m not in KNOWN_PLACEHOLDERS
        })
        avertissements = []
        if unknown:
            avertissements.append(
                "⚠ Placeholder(s) inconnu(s) : " + ", ".join("{%s}" % u for u in unknown)
                + " — connus : " + ", ".join(sorted(KNOWN_PLACEHOLDERS)))
        # Double backslash dans un format : presque toujours une correction de
        # trop. Le JSON brut AFFICHE « \\ » là où le format n'en contient qu'un
        # (échappement JSON) ; en retaper deux ici donne un backslash LITTÉRAL
        # à l'écran dans Power BI, et le format « ne marche plus ».
        fmt_txt = self.cmb_format.currentText()
        if "\\\\" in fmt_txt:
            avertissements.append(
                "⚠ formatString : « \\\\ » (double backslash) affichera un vrai "
                "backslash. Un seul suffit pour échapper un caractère — et le "
                "JSON brut en montre toujours deux, c'est normal.")
        if '"' in fmt_txt or "\\ " in fmt_txt:
            avertissements.append(
                "⚠ formatString : une espace n'a besoin de RIEN — ni "
                "guillemets, ni backslash. Écris « #,0.00 $ ». "
                "(espace, + - $ ( ) s'affichent d'eux-mêmes ; seules les "
                "lettres et symboles demandent un backslash, ex. \\p\\t\\s.)")
        if self._current and self.lst.count():
            if self._current not in self._cochees():
                avertissements.append(
                    "Variation DESACTIVEE dans ce rapport (case decochee a "
                    "gauche) : elle ne sera pas generee ici.")
        self.lbl_lint.setText("\n".join(avertissements))

        # aperçu des noms générés : reproduit l'expansion du générateur —
        # {base} = la base traitée + suffixe de branche, {kpi} = KPI racine
        # (sans branche), {variation} = id de la variation, {branch} = branche.
        # L'aperçu suit la PORTÉE cochée : une variation « aux cibles » seulement
        # doit montrer les cibles (« Weight cible »), pas les KPI.
        pattern = self.ed_name.text() or "{base}"
        vid = self._current or ""
        roots: list = []                 # (base racine, KPI racine, portée)
        notes: list = []
        kinds = None if self.cmb_kinds.all_checked() else self.cmb_kinds.checked()
        # l'aperçu applique le MÊME arbitrage que la génération
        tpl_ex = {
            "excludeNameContains": [x.strip() for x in
                                    self.ed_exclude.text().split(",") if x.strip()],
            "includeNameContains": [x.strip() for x in
                                    self.ed_include.text().split(",") if x.strip()],
        }
        if self.chk_kpi.isChecked():
            roots += [(k, k, "KPI") for k in self._preview_kpis(kinds, tpl_ex)
                      if not gm.name_excluded(tpl_ex, k)
                      or gm.name_included(tpl_ex, k)]
        if self.chk_cible.isChecked():
            cibles = self._preview_cibles()
            roots += [(c, k, "cible") for c, k in cibles
                      if not gm.name_excluded(tpl_ex, c, k)
                      or gm.name_included(tpl_ex, c, k)]
            if not cibles:
                notes.append("(aucune cible trouvée — vérifie le dossier des "
                             "cibles dans « Réglages globaux »)")
        if not roots:
            self.ed_preview.setPlainText(
                "Portée vide : coche « générer pour les KPI » et/ou « générer "
                "pour les cibles »,\nsinon cette variation n'est générée nulle part."
                + ("\n" + "\n".join(notes) if notes else ""))
            return

        variations = self._config.get("variations") or {}
        branches = list((self._config.get("branches") or {}).keys())
        lines = []
        for b in [""] + branches:
            for root, kpi, scope in roots:
                if b:
                    # nom de la base EN BRANCHE : via le namePattern réel de la
                    # branche (« {base} YTD »…), pas un suffixe supposé
                    bpat = ((variations.get(b) or {}).get("namePattern")
                            or ("{base} " + b))
                    base = (bpat.replace("{base}", root).replace("{kpi}", kpi)
                                .replace("{variation}", b).replace("{branch}", b))
                else:
                    base = root
                name = (pattern.replace("{base}", base)
                               .replace("{kpi}", kpi)
                               .replace("{variation}", vid)
                               .replace("{branch}", b))
                lines.append(f"[{'Réel' if not b else b} · {scope}] " + name)
        self.ed_preview.setPlainText("\n".join(lines + notes))

    def _refresh_delta_preview(self):
        """Aperçu sur UNE ligne : ce que « delta » donnera à l'écran pour les
        trois cas qui comptent — base chiffrée, base en %, base sans format."""
        sym = {"positive": self.g_delta_pos.text(),
               "negative": self.g_delta_neg.text(),
               "zero": self.g_delta_zero.text()}
        fb = self.g_delta_fallback.text()

        def montre(section, val):
            """Rendu approximatif d'une section. Un littéral s'écrit
            « "X" » ou « \\X » : les DEUX doivent rendre X, sinon l'aperçu
            afficherait un backslash là où Power BI met une espace."""
            out, i = [], 0
            while i < len(section):
                c = section[i]
                if c == "\\" and i + 1 < len(section):
                    out.append(section[i + 1])       # \X -> X
                    i += 2
                else:
                    if c != chr(34):                 # "X" -> X
                        out.append(c)
                    i += 1
            txt = "".join(out)
            # le 1er groupe de codes numériques devient la valeur d'exemple
            a = 0
            while a < len(txt) and txt[a] not in "#0":
                a += 1
            b = a
            while b < len(txt) and txt[b] in "#0.,":
                b += 1
            return txt[:a] + val + txt[b:] if a < len(txt) else txt

        lignes = []
        for base_fmt, label in ((r"#,0", "#,0"),
                                ("0.0" + chr(92) + " %", "%"),
                                (None, "sans format")):
            f = gm.resolve_format("delta", base_fmt, sym, fb)
            if not f:
                lignes.append(label + " → aucun format")
                continue
            pos, neg, zero = (f.split(";") + ["", ""])[:3]
            lignes.append(label + " → " + montre(pos, "12,3")
                          + " / " + montre(neg, "12,3")
                          + " / " + montre(zero, "0"))
        self.lbl_delta_preview.setText("   ·   ".join(lignes))

    def _td_combo(self, defaut):
        """Combo éditable de colonnes de l'Excel (saisie libre permise)."""
        c = QComboBox()
        c.setEditable(True)
        c.setMinimumWidth(150)
        c.setCurrentText(defaut)
        c.currentTextChanged.connect(self._mark_dirty)
        return c

    def _td_path_resolu(self):
        """Chemin absolu de l'Excel, tel que le générateur le résoudra."""
        p = Path(self.g_td_path.text().strip() or "TD_Indicateurs.xlsx")
        if not p.is_absolute() and self.project:
            p = self.project.folder / p
        return p

    def _td_browse(self):
        depart = str(self._td_path_resolu().parent if self.project
                     else Path.home())
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir l'Excel des indicateurs", depart, "Excel (*.xlsx)")
        if not chemin:
            return
        p = Path(chemin)
        # on garde un chemin RELATIF quand c'est possible : le config
        # voyage alors d'un rapport à l'autre sans retouche
        if self.project:
            try:
                p = p.relative_to(self.project.folder)
            except ValueError:
                pass
        self.g_td_path.setText(str(p))
        self._td_reload_columns()

    def _td_reload_columns(self):
        """Peuple les 3 combos avec les en-têtes du classeur."""
        entetes = model_reader.excel_headers(self._td_path_resolu())
        if not entetes:
            return
        for combo in (self.g_td_key, self.g_td_fill, self.g_td_text):
            courant = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(entetes)
            combo.setCurrentText(courant)
            combo.blockSignals(False)

    def _kind_vocabulary(self) -> list:
        """Types proposés : ceux que le formatString permet de déduire."""
        return list(gm.FORMAT_KINDS)

    def _refresh_kind_items(self, checked=None):
        self.cmb_kinds.blockSignals(True)
        self.cmb_kinds.set_items(self._kind_vocabulary(), checked)
        self.cmb_kinds.blockSignals(False)

    def _preview_kpis(self, kinds=None, tpl_ex=None) -> list:
        """KPI du modèle, filtrés par TYPE de format si `kinds` est donné :
        l'aperçu montre alors exactement les bases qui recevront la
        variation, et aucune autre."""
        if not self.project:
            return ["KPI"]
        try:
            noms = model_reader.kpis(self.project)
        except Exception:
            return ["KPI"]
        if kinds:
            try:
                ex, _ = gm.read_measures(self.project.model_dir, self._config)
                noms = [n for n in noms
                        if gm.format_kind((ex.get(n) or {}).get("format")) in kinds
                        or gm.name_included(tpl_ex or {}, n)]
            except Exception:
                pass
        return noms[:6]

    def _preview_cibles(self) -> list:
        """[(cible racine, KPI)] — via generate_measures.scan_cibles, donc
        exactement ce que la génération déclinera."""
        if not self.project:
            return [("KPI cible", "KPI")]
        try:
            return gm.scan_cibles(self.project.model_dir, self._config)[:6]
        except Exception:
            return []

    # ---- synchronisation des deux vues ------------------------------------------

    def _on_view_switch(self, index: int):
        # 1) committer / valider l'onglet que l'on QUITTE
        prev = self._inner_prev
        if prev == IDX_VARIATIONS:
            self._commit_form()
        elif prev == IDX_GLOBAL:
            self._commit_global()
        elif prev == IDX_RAW:
            try:
                self._config = json.loads(self.ed_raw.toPlainText())
            except ValueError as e:
                QMessageBox.warning(self, "JSON invalide",
                                    f"{e}\n\nCorrige le JSON brut avant de changer de vue.")
                self.inner.blockSignals(True)
                self.inner.setCurrentIndex(IDX_RAW)
                self.inner.blockSignals(False)
                self._inner_prev = IDX_RAW
                return
        # 2) charger l'onglet que l'on OUVRE (depuis le config en mémoire)
        if index == IDX_VARIATIONS:
            self._populate_list(select=self._current)
        elif index == IDX_GLOBAL:
            self._load_global()
        elif index == IDX_RAW:
            self.ed_raw.blockSignals(True)
            self.ed_raw.setPlainText(json.dumps(self._config, indent=2, ensure_ascii=False))
            self.ed_raw.blockSignals(False)
        elif index == IDX_GENERATE:
            # le générateur lit le fichier sur le disque : prévenir si non sauvé
            self.model_panel.set_unsaved(self._dirty)
        self._inner_prev = index

    def _validate_raw(self):
        try:
            json.loads(self.ed_raw.toPlainText())
        except ValueError as e:
            QMessageBox.warning(self, "JSON invalide", str(e))
            return
        QMessageBox.information(self, "JSON", "JSON valide. ✔")

    # ---- état / sauvegarde --------------------------------------------------------

    def _on_edit(self, *args):
        if self._loading:
            return
        self._set_dirty(True)
        self._refresh_lint_preview()

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self.lbl_dirty.setText("● modifications non sauvegardées" if dirty else "")

    def save_all(self):
        """Bouton « 💾 Tout enregistrer » de l'app : écrit si nécessaire."""
        if self._dirty:
            self._save()

    def _save(self, *_):
        if not self.project:
            return
        path = self.project.config_json
        idx = self.inner.currentIndex()
        if idx == IDX_RAW:                   # vue JSON brut : parser d'abord
            try:
                self._config = json.loads(self.ed_raw.toPlainText())
            except ValueError as e:
                QMessageBox.critical(self, "JSON invalide", f"Rien écrit : {e}")
                return
        elif idx == IDX_GLOBAL:
            self._commit_global()
        elif idx == IDX_VARIATIONS:
            self._commit_form()
        # IDX_GENERATE : rien à committer (le config est déjà à jour)

        try:
            if path.exists():
                shutil.copy2(str(path), str(path) + ".bak")
            path.write_text(json.dumps(self._config, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Erreur d'écriture", str(e))
            return
        self._set_dirty(False)
        self.model_panel.set_project(self.project)   # récap « Générer » à jour depuis le disque
        self.model_panel.set_unsaved(False)
        # pas de popup : confirmation dans le bandeau d'état
        self.lbl_dirty.setText(f"✔ {path.name} écrit (backup .bak) — "
                               "sous-onglet « Générer » pour créer les mesures")
