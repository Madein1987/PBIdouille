# -*- coding: utf-8 -*-
"""Le journal de l'app : UNE colonne, à droite, sur toute la hauteur.

Avant, chaque onglet avait sa bande de log en bas : deux journaux (Rapport,
Générer) plus celui de ChopChop, tous larges et bas, à 4 ou 5 lignes visibles.
Il fallait donc savoir DANS QUEL onglet regarder, et les journaux les plus
bavards (propagation verbeuse) défilaient dans un hublot.

Un seul journal, vertical, à droite : l'endroit où regarder ne dépend plus de
l'onglet, et la hauteur est celle de la fenêtre.

LE PLUS RÉCENT EN HAUT — par ENTRÉE, pas par ligne. Une entrée est un run
(bannière « ▶ heure titre » puis la sortie du moteur) ou un groupe de
messages. Les entrées s'empilent du plus récent au plus ancien ; DANS une
entrée, les lignes restent dans l'ordre où on les lit — sinon un run se lirait
de bas en haut, son « Terminé » au-dessus de sa bannière. Le verdict et la
durée s'inscrivent SUR la bannière : l'issue d'un run se lit sans descendre,
même quand sa sortie dépasse la hauteur de la colonne.

Un TRAIT sépare un run de ses voisins. Les messages isolés (un déplacement
dans le wireframe, un rechargement) restent groupés sans trait : une rafale de
déplacements deviendrait sinon une échelle.

Le reste :

  · l'HEURE du début du dernier lancement, dans l'entête et sur la bannière ;
  · une COULEUR par nature de ligne (cf. `classer`), tirée du vocabulaire que
    les moteurs écrivent réellement (⚠, +, ~, -, ∅, ***, …) ;
  · l'ESPACEMENT : retrait à gauche selon la profondeur (une ligne qui revient
    à la ligne reste alignée sous elle-même), et les lignes vides des moteurs
    deviennent de la marge au lieu de trous.

Qui est en haut y reste et voit arriver le neuf ; qui est descendu lire plus
bas garde SA ligne sous les yeux — le neuf s'insère au-dessus sans la pousser.
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from datetime import datetime

from qtpy.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from qtpy.QtGui import (QBrush, QColor, QFont, QTextBlockFormat,
                        QTextCharFormat, QTextCursor, QTextFormat,
                        QTextOption)
from qtpy.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTextEdit,
                            QVBoxLayout, QWidget)

from core.theme import (ACCENT, ACCENT_DIM, BLUE, GREEN, ORANGE, RED, TEXT,
                        TEXT_DIM, TEXT_MUTED, TITRE_POLICE, TITRE_PT, TRAIT,
                        YELLOW)

# retrait (px) par niveau d'indentation du texte source
RETRAIT = 10
# marges verticales (px) : détail collé à son titre, paragraphe, section
# (ligne vide d'un moteur), tête d'un groupe de messages, et de part et
# d'autre d'un trait
MARGE_DETAIL, MARGE_LIGNE, MARGE_SECTION = 1, 3, 11
MARGE_MESSAGE, MARGE_REGLE = 5, 8
# largeur (px) de la colonne des CLÉS du tableau, et au-delà de combien
# d'éléments une énumération reste sur une ligne (repliée dans la colonne
# des valeurs) plutôt qu'une valeur par rangée
COL_CLE, MAX_RANGEES = 136, 12
# TIROIRS : un run terminé qui a écrit plus de PLI_SEUIL lignes se replie
# sur sa bannière ; la flèche de tête dit l'état, un clic le change.
PLI_SEUIL = 6
# ▶ / ▼ plutôt que les petits ▸ / ▾ : à la taille du texte, le triangle
# se voit, et il dit qu'on peut cliquer
FLECHE_OUVERT, FLECHE_REPLIE = "▼", "▶"
# étiquettes posées sur les blocs (propriétés de format) : la bannière
# d'un run, le trait entre deux entrées, l'état replié d'une bannière
ROLE, REPLIE = QTextFormat.UserProperty + 1, QTextFormat.UserProperty + 2
# le trait entre deux entrées : le même que celui des poignées de volets
REGLE = TRAIT


def niveau(ligne: str) -> int:
    """Profondeur d'une ligne, d'après ses espaces de tête (2 par cran — c'est
    le pas des moteurs). Rendue en RETRAIT plutôt qu'en espaces : une ligne
    trop longue revient à la ligne en restant alignée sous elle-même."""
    return (len(ligne) - len(ligne.lstrip(" "))) // 2


# « clé : valeur » : une clé courte, qui ne commence pas par un marqueur
# (⚠, +, ~, ∅, ·, —…), puis « : » suivi d'une valeur. La PREMIÈRE « : »
# sépare : « Paramètre : P_x : 80 rangées » a pour valeur « P_x : 80… ».
CLE_VALEUR = re.compile(
    r"^(?P<cle>[^\s:⚠✔✖*=~+∅·•(—▶<\-][^:]{0,40}?)\s*:\s+(?P<val>\S.*)$")
_OUVRANTS, _FERMANTS = "([«{", ")]»}"


def cle_valeur(ligne: str):
    """(clé, [valeurs]) si la ligne se lit « clé : valeur », sinon None.

    Une énumération « A, B, C » donne une valeur par élément — coupée aux
    virgules de PREMIER niveau seulement : « 3 KPI (sans valeur, placés à
    la fin) » reste d'un bloc. Au-delà de MAX_RANGEES éléments, la liste
    reste entière (repliée dans la colonne des valeurs) : 42 mesures en
    42 rangées noieraient le journal."""
    m = CLE_VALEUR.match(ligne.strip())
    if not m:
        return None
    val = m.group("val")
    items, prof, debut = [], 0, 0
    for i, ch in enumerate(val):
        if ch in _OUVRANTS:
            prof += 1
        elif ch in _FERMANTS:
            prof = max(0, prof - 1)
        elif ch == "," and prof == 0 and val[i + 1:i + 2] == " ":
            items.append(val[debut:i].strip())
            debut = i + 1
    items.append(val[debut:].strip())
    items = [x for x in items if x]
    if not 2 <= len(items) <= MAX_RANGEES:
        items = [val]
    return m.group("cle").strip(), items


def classer(ligne: str) -> tuple:
    """(couleur, gras) d'une ligne de journal.

    Les motifs ne sont pas inventés : ce sont ceux que les moteurs écrivent
    (cf. propagate_cf, generate_measures, color_matrix_by_kpi). L'ordre compte
    — l'échec et l'avertissement passent AVANT les règles de forme, sinon
    « ⚠ … » indenté serait lu comme un simple détail."""
    t = ligne.strip()
    if not t:
        return TEXT, False
    if t.startswith(("ERREUR", "✖", "Traceback")):
        return RED, True
    if t.startswith("⚠"):
        return YELLOW, False
    if t.startswith("===") or t.startswith("▶"):
        return ACCENT, True
    if t.startswith("---") or t.startswith("—"):
        return ACCENT_DIM, True
    if t.startswith("***"):                      # *** DRY_RUN : … ***
        return BLUE, True
    if t.startswith(("✔", "Terminé", "Écrit :", "restauré", "💾", "📦", "📤",
                     "📥")):
        return GREEN, True
    if t.startswith(("+ ", "effacé")):           # créé / disparu
        return GREEN if t.startswith("+") else ORANGE, False
    if t.startswith("- "):                       # retiré d'une cible
        return ORANGE, False
    if t.startswith("~ "):                       # mis à jour
        return BLUE, False
    if t.startswith(("= ", "∅ ")):               # inchangé / sans équivalent
        return TEXT_MUTED, False
    if t.startswith(("* ", "· ", "• ", "(")):    # commentaire, précision
        return TEXT_DIM, False
    if t.startswith("Aucun") or t.startswith("Aucune"):
        return TEXT_DIM, False
    # le texte courant en TEXT_DIM, pas en blanc : le blanc vif réservé à
    # rien, ce sont les COULEURS qui doivent sortir (⚠, +, ✔…)
    return TEXT_DIM, False


def _tabulation(position: float):
    """Un taquet de tabulation à gauche, placé à `position` px du début de
    la ligne (0 serait ignoré par Qt : c'est la position réelle qu'il faut)."""
    try:
        return QTextOption.Tab(float(position), QTextOption.LeftTab)
    except TypeError:                         # liaison sans ce constructeur
        tab = QTextOption.Tab()
        tab.position = float(position)
        tab.type = QTextOption.LeftTab
        return tab


class Journal(QWidget):
    """La colonne de droite. Les onglets n'écrivent QUE par ses méthodes —
    aucun n'a plus de zone de log à lui.

    Un onglet construit hors application (tests, fenêtre autonome) s'en crée
    un pour lui seul : les appels marchent sans parent ni fenêtre, donc aucun
    appelant n'a à se demander si le journal existe."""

    # un run commence : la fenêtre remontre la colonne si elle est masquée.
    # Un outil qui écrit dans les fichiers pendant qu'on ne voit rien de ce
    # qu'il fait, c'est le seul cas où l'on s'autorise à défaire un choix
    # de l'usager — et seulement pour un RUN, pas pour un simple message.
    demarre = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = None          # horloge du run en cours (time.monotonic)
        self._entete = ""        # « Dernier lancement : hh:mm:ss · titre »
        self._espace_avant = False   # une ligne vide attend d'être rendue
        # curseurs SUIVIS par le document : ils glissent tout seuls quand on
        # insère au-dessus d'eux, donc une entrée ouverte se complète au bon
        # endroit même si d'autres sont venues s'empiler en haut entre-temps
        self._banniere = None    # début de la bannière du run en cours
        self._fin_run = None     # fin de l'entrée du run en cours
        self._fin_message = None # fin du groupe de messages ouvert
        self._haut_est_run = False   # nature de l'entrée du haut (cf. trait)
        self._avert = 0              # ⚠ écrits par le run en cours

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        haut = QHBoxLayout()
        titre = QLabel("Journal")
        titre.setStyleSheet(f"color:{ACCENT}; font-family:\"{TITRE_POLICE}\"; "
                            f"font-size:{TITRE_PT}pt;")
        sens = QLabel("· le plus récent en haut")
        sens.setStyleSheet(f"color:{TEXT_MUTED};")
        self.btn_vider = QPushButton("Vider")
        self.btn_vider.setToolTip("Efface le journal affiché (rien sur le disque).")
        self.btn_vider.clicked.connect(self.vider)
        haut.addWidget(titre)
        haut.addWidget(sens)
        haut.addStretch()
        haut.addWidget(self.btn_vider)
        lay.addLayout(haut)

        # l'entête garde l'heure du dernier lancement même quand on est
        # descendu loin : la question « ça date de quand ? » a une réponse fixe
        self.lbl_run = QLabel("Dernier lancement : —")
        self.lbl_run.setWordWrap(True)
        self.lbl_run.setStyleSheet(f"color:{TEXT_DIM};")
        lay.addWidget(self.lbl_run)

        # des ACTIONS peuvent se poser entre l'entête et le fil (cf.
        # poser_actions) : leur sortie arrive juste en dessous, puisque le
        # plus récent est en haut
        self._actions = QVBoxLayout()
        self._actions.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._actions)

        self.vue = QTextEdit()
        self.vue.setReadOnly(True)
        # police PROPORTIONNELLE, volontairement (pas police_code) : dans
        # une colonne étroite elle loge un tiers de texte de plus par ligne,
        # donc bien moins de retours à la ligne. Seul le mode verbeux aligne
        # des colonnes, et il sert au diagnostic.
        self.vue.setLineWrapMode(QTextEdit.WidgetWidth)
        self.vue.setTextInteractionFlags(Qt.TextSelectableByMouse
                                        | Qt.TextSelectableByKeyboard)
        lay.addWidget(self.vue, 1)
        # un clic sur une bannière ouvre ou referme son tiroir ; la main
        # au survol dit qu'elle se clique
        self.vue.viewport().installEventFilter(self)
        self.vue.viewport().setMouseTracking(True)

    def poser_actions(self, widget) -> None:
        """Pose `widget` (des boutons qui lancent des runs) entre l'entête et
        le fil. Son propriétaire le montre ou le cache selon qu'il a du sens
        (le bouton « Générer » n'en a que dans l'onglet Mesures)."""
        self._actions.addWidget(widget)

    # ---- écriture -------------------------------------------------------------

    def lancement(self, titre: str, apercu: bool = False) -> None:
        """Début d'un run : horodate, ouvre une entrée EN HAUT (sa bannière),
        arme le chrono."""
        self._t0 = time.monotonic()
        libelle = titre + (" (aperçu)" if apercu else "")
        heure = datetime.now().strftime("%H:%M:%S")
        self._entete = "Dernier lancement : " + heure + " · " + libelle
        self.lbl_run.setText(self._entete + " · en cours…")
        self.lbl_run.setStyleSheet(f"color:{ACCENT};")
        self._fin_message = None        # un run ferme le groupe de messages
        self._espace_avant = False
        self._avert = 0
        self._fin_run = self._nouvelle_entree(
            FLECHE_OUVERT + " " + heure + "  " + libelle, ACCENT, gras=True,
            est_run=True)
        self._banniere = QTextCursor(self._fin_run.block())
        self._etiqueter(self._fin_run.block(), ROLE, "banniere")
        self.demarre.emit()

    def fin(self, resume: str = "", echec: bool = False) -> None:
        """Fin d'un run : le verdict et la durée s'inscrivent SUR la bannière
        — en haut, là où l'œil arrive — et dans l'entête. Sans `lancement`
        préalable, on n'invente pas de durée."""
        duree = ""
        if self._t0 is not None:
            secondes = time.monotonic() - self._t0
            duree = (" en %.1f s" % secondes).replace(".", ",")
        verdict = ("✖ échec" if echec else "✔ terminé") + duree
        if resume:
            verdict += " — " + resume
        couleur = RED if echec else GREEN
        if self._banniere is not None:
            banniere = self._banniere.block()
            details = self._details(banniere)
            with self._lecture_preservee():
                c = QTextCursor(self._banniere)
                c.movePosition(QTextCursor.EndOfBlock)
                c.insertText("   " + verdict, self._format(couleur, True))
                # un run BAVARD se replie : sa bannière suffit — elle dit
                # combien de lignes elle cache, et s'il y a des ⚠ dedans.
                # Un échec reste ouvert : il faut le lire.
                if len(details) > PLI_SEUIL and not echec:
                    c.insertText(f"   {len(details)} lignes",
                                 self._format(TEXT_MUTED))
                    if self._avert:
                        c.insertText(f"   ⚠ {self._avert}",
                                     self._format(YELLOW, True))
            if len(details) > PLI_SEUIL and not echec:
                self._replier(banniere, True)
        else:                            # vidé en plein run, ou fin orpheline
            self._dans_un_message(verdict, couleur, gras=True)
        if self._entete:
            self.lbl_run.setText(self._entete + " · "
                                 + ("échec" if echec else "terminé") + duree)
        self.lbl_run.setStyleSheet(f"color:{RED if echec else TEXT_DIM};")
        self._t0 = None
        self._banniere = self._fin_run = None
        self._espace_avant = False

    def ligne(self, texte) -> None:
        """Une ligne (ou plusieurs) d'un moteur, colorée selon `classer`.

        Pendant un run, elle complète SON entrée, dans l'ordre de lecture.
        Hors run, c'est un message (cf. `info`).

        Une ligne vide ne crée pas de trou : elle devient la marge de la
        suivante. Les moteurs s'en servent comme séparateur, et l'espacement
        des blocs fait déjà ce travail."""
        if self._t0 is None:
            self.info(texte)
            return
        for brute in str(texte).split("\n"):
            if not brute.strip():
                self._espace_avant = True
                continue
            couleur, gras = classer(brute)
            if couleur == YELLOW:
                self._avert += 1
            marge = MARGE_DETAIL if niveau(brute) else MARGE_LIGNE
            if self._espace_avant:
                marge = MARGE_SECTION
                self._espace_avant = False
            # « clé : valeur » : en tableau, clé grisée, valeurs alignées.
            # Seulement pour le texte COURANT : un ⚠, un ✔, un + gardent
            # leur ligne et leur couleur.
            cv = cle_valeur(brute) if couleur == TEXT_DIM and not gras else None
            if (cv and self._fin_run is not None and
                    self.vue.fontMetrics().horizontalAdvance(cv[0])
                    <= COL_CLE - 10):
                self._ajouter_tableau(self._fin_run, niveau(brute), cv[0],
                                      cv[1], marge)
                continue
            self._dans_le_run(brute, couleur, gras, marge)

    def erreur(self, texte) -> None:
        """Un échec : TOUT en rouge, y compris le corps d'une trace — dont les
        lignes, indentées, passeraient sinon pour du détail anodin."""
        lignes = [l for l in str(texte).rstrip().split("\n") if l.strip()]
        for i, l in enumerate(lignes):
            t = ("ERREUR : " if i == 0 and not l.startswith("ERREUR")
                 else "") + l
            if self._t0 is not None:
                self._dans_le_run(t, RED, i == 0,
                                  MARGE_LIGNE if i == 0 else MARGE_DETAIL)
            else:
                self._dans_un_message(t, RED, gras=(i == 0))

    def info(self, texte) -> None:
        """Un évènement hors run (rechargement, sauvegarde, message d'onglet).

        Tout ce qui s'écrit dans le MÊME tour de la boucle d'évènements forme
        UNE entrée — un clic = un groupe, lu dans l'ordre, horodaté sur sa
        première ligne. Le tour suivant en ouvrira une autre, au-dessus."""
        for brute in str(texte).split("\n"):
            if not brute.strip():
                continue
            couleur, gras = classer(brute)
            self._dans_un_message(brute, couleur, gras=gras)

    def vider(self) -> None:
        self.vue.clear()
        # un run en cours repartira d'une entrée neuve en haut (cf.
        # _dans_le_run) : ses curseurs pointeraient dans un document effacé
        self._banniere = self._fin_run = self._fin_message = None
        self._haut_est_run = False
        self._espace_avant = False

    def texte(self) -> str:
        """Le journal en texte brut (pour les tests, et pour un copier-coller
        au clavier)."""
        return self.vue.toPlainText()

    # ---- tiroirs -----------------------------------------------------------------

    def _details(self, banniere) -> list:
        """Les blocs du tiroir d'une bannière : tout ce qui suit, jusqu'au
        trait qui la sépare de l'entrée plus ancienne (ou la fin)."""
        blocs, b = [], banniere.next()
        while b.isValid() and b.blockFormat().property(ROLE) not in (
                "trait", "banniere"):
            blocs.append(b)
            b = b.next()
        return blocs

    def est_replie(self, banniere) -> bool:
        return bool(banniere.blockFormat().property(REPLIE))

    def basculer(self, banniere) -> None:
        """Ouvre ou referme le tiroir de `banniere` — sauf celui du run EN
        COURS, dont les lignes arrivent encore."""
        if (self._banniere is not None
                and self._banniere.block().position() == banniere.position()):
            return
        self._replier(banniere, not self.est_replie(banniere))

    def _replier(self, banniere, replie: bool) -> None:
        details = self._details(banniere)
        barre = self.vue.verticalScrollBar()
        mise = self.vue.document().documentLayout()
        haut = barre.value()
        for b in details:
            b.setVisible(not replie)
        self._etiqueter(banniere, REPLIE, replie)
        # la flèche de tête dit l'état (même longueur : aucun curseur suivi
        # ne se décale)
        c = QTextCursor(banniere)
        c.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
        fmt = c.charFormat()
        c.insertText(FLECHE_REPLIE if replie else FLECHE_OUVERT, fmt)
        if details:
            debut = details[0].position()
            fin = details[-1].position() + details[-1].length()
            self.vue.document().markContentsDirty(debut, fin - debut)
        # replier ce qu'on lisait : la bannière vient sous les yeux, plutôt
        # qu'un saut vers une entrée sans rapport
        if replie and haut > mise.blockBoundingRect(banniere).top():
            barre.setValue(int(mise.blockBoundingRect(banniere).top()))

    @staticmethod
    def _etiqueter(bloc, cle, valeur) -> None:
        bf = QTextBlockFormat()
        bf.setProperty(cle, valeur)
        QTextCursor(bloc).mergeBlockFormat(bf)

    def _banniere_sous(self, pos):
        """La bannière sous ce point de la vue, ou None — seulement si le
        point est SUR elle (pas dans le vide sous la dernière ligne)."""
        bloc = self.vue.cursorForPosition(pos).block()
        if bloc.blockFormat().property(ROLE) != "banniere":
            return None
        r = self.vue.document().documentLayout().blockBoundingRect(bloc)
        y = pos.y() + self.vue.verticalScrollBar().value()
        return bloc if r.top() <= y <= r.bottom() else None

    def eventFilter(self, obj, ev):
        if obj is self.vue.viewport():
            t = ev.type()
            if t in (QEvent.MouseMove, QEvent.MouseButtonRelease):
                pos = (ev.position().toPoint() if hasattr(ev, "position")
                       else ev.pos())
                bloc = self._banniere_sous(pos)
                if t == QEvent.MouseMove:
                    obj.setCursor(Qt.PointingHandCursor if bloc is not None
                                  else Qt.IBeamCursor)
                elif (bloc is not None and ev.button() == Qt.LeftButton
                      and not self.vue.textCursor().hasSelection()):
                    self.basculer(bloc)
                    return True
        return super().eventFilter(obj, ev)

    # ---- entrées ---------------------------------------------------------------

    def _dans_le_run(self, texte, couleur, gras, marge) -> None:
        if self._fin_run is None:        # vidé en plein run : on repart en haut
            self._fin_run = self._nouvelle_entree(texte, couleur, gras,
                                                  est_run=True)
        else:
            self._ajouter(self._fin_run, texte, couleur, gras, marge)

    def _dans_un_message(self, texte, couleur, gras=False) -> None:
        if self._fin_message is None:
            self._fin_message = self._nouvelle_entree(
                texte, couleur, gras, est_run=False,
                heure=datetime.now().strftime("%H:%M:%S"))
            # le groupe se referme au tour suivant de la boucle d'évènements
            QTimer.singleShot(0, self._fermer_message)
        else:
            self._ajouter(self._fin_message, texte, couleur, gras, MARGE_LIGNE)

    def _fermer_message(self) -> None:
        self._fin_message = None

    def _nouvelle_entree(self, texte, couleur, gras, est_run,
                         heure="") -> QTextCursor:
        """Ouvre une entrée EN HAUT du document, et rend le curseur de sa fin.

        Un trait la sépare de l'ancienne tête si l'une des deux est un run."""
        with self._lecture_preservee():
            doc = self.vue.document()
            c = QTextCursor(doc)
            c.movePosition(QTextCursor.Start)
            if not doc.isEmpty():
                trait = est_run or self._haut_est_run
                c.insertBlock()             # la ligne de la nouvelle entrée…
                if trait:
                    c.insertBlock()         # … puis le trait, sur l'ancienne tête
                    self._tracer(QTextCursor(c.block().previous()))
                c.movePosition(QTextCursor.Start)
            self._remplir(c, texte, couleur, gras,
                          MARGE_LIGNE if est_run else MARGE_MESSAGE, heure)
        self._haut_est_run = est_run
        return c

    def _ajouter(self, fin, texte, couleur, gras, marge) -> None:
        """Complète une entrée ouverte, sous sa dernière ligne. `fin` est un
        curseur suivi : il reste à la fin de l'entrée."""
        with self._lecture_preservee():
            fin.insertBlock()
            self._remplir(fin, texte, couleur, gras, marge)

    def _ajouter_tableau(self, fin, niv, cle, valeurs, marge) -> None:
        """Rangées d'un tableau à deux colonnes, sans vraie table : la clé
        (grisée) puis une tabulation vers la colonne des valeurs, placée à
        COL_CLE ; un retrait négatif (« hanging indent ») fait que la valeur
        qui déborde revient à la ligne DANS sa colonne, et chaque élément
        suivant d'une énumération y commence sa propre rangée."""
        base = niv * RETRAIT
        with self._lecture_preservee():
            for i, valeur in enumerate(valeurs):
                fin.insertBlock()
                bf = QTextBlockFormat()
                bf.setLeftMargin(base + COL_CLE)
                bf.setTopMargin(marge if i == 0 else 0)
                if i == 0:
                    bf.setTextIndent(-COL_CLE)
                    bf.setTabPositions([_tabulation(COL_CLE)])
                fin.setBlockFormat(bf)
                fin.setBlockCharFormat(QTextCharFormat())
                if i == 0:
                    fin.insertText(cle + "\t", self._format(TEXT_MUTED))
                fin.insertText(valeur, self._format(TEXT_DIM))

    # ---- rendu ----------------------------------------------------------------

    def _remplir(self, c, texte, couleur, gras, marge, heure="") -> None:
        """Pose le format du bloc courant et son texte. Le retrait de tête
        devient une marge gauche : le texte garde son alignement interne (les
        colonnes du mode verbeux) et un retour à la ligne reste aligné sous le
        début du texte."""
        bf = QTextBlockFormat()
        bf.setTopMargin(marge)
        bf.setLeftMargin(niveau(texte) * RETRAIT)
        c.setBlockFormat(bf)
        c.setBlockCharFormat(QTextCharFormat())
        if heure:
            c.insertText(heure + "  ", self._format(TEXT_MUTED))
        c.insertText(texte.lstrip(" "), self._format(couleur, gras))

    @staticmethod
    def _tracer(c) -> None:
        """Fait du bloc (vide) de `c` un trait horizontal.

        QTextEdit n'a pas de bordure de bloc portable, et la couleur d'un
        <hr> ne vient pas du même endroit en Qt5 et en Qt6. Ici : un bloc
        vide dont la police fait 1 px — sa hauteur de ligne — et dont le FOND
        est coloré. Rendu identique partout."""
        bf = QTextBlockFormat()
        bf.setTopMargin(MARGE_REGLE)
        bf.setBottomMargin(MARGE_REGLE)
        bf.setBackground(QBrush(QColor(REGLE)))
        bf.setProperty(ROLE, "trait")
        c.setBlockFormat(bf)
        cf = QTextCharFormat()
        police = QFont("Consolas")
        police.setPixelSize(1)
        cf.setFont(police)
        c.setBlockCharFormat(cf)

    @contextmanager
    def _lecture_preservee(self):
        """Le neuf arrive EN HAUT. Qui est en haut y reste et le voit
        arriver ; qui est descendu lire plus bas garde SA ligne sous les yeux
        — sinon chaque nouvelle entrée la pousserait vers le bas."""
        barre = self.vue.verticalScrollBar()
        mise = self.vue.document().documentLayout()
        repere = None
        if barre.value() > 0:
            bloc = self.vue.cursorForPosition(QPoint(0, 0)).block()
            repere = (bloc, mise.blockBoundingRect(bloc).top() - barre.value())
        yield
        if repere is not None:
            bloc, decalage = repere
            barre.setValue(int(round(mise.blockBoundingRect(bloc).top()
                                     - decalage)))

    @staticmethod
    def _format(couleur: str, gras: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(couleur))
        if gras:
            f.setFontWeight(QFont.Bold)
        return f
