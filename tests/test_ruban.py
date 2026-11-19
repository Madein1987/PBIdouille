# -*- coding: utf-8 -*-
"""Le ruban de l'app : le bouton du rapport et le bouton de restauration.

    py tests\\test_ruban.py

  1. une seule ligne : le rapport et son config à gauche, l'outil à droite ;
  2. le bouton du rapport : son menu propose les récents (celui qui est ouvert
     est coché, deux homonymes se distinguent par leur dossier), en ouvre un
     autre, ou ouvre un .pbip choisi ;
  3. « Restaurer une sauvegarde… » est au ruban, pour le rapport ouvert, et
     une restauration fait relire les onglets ; ChopChop n'a plus le sien,
     sauf dans sa fenêtre autonome ;
  4. les deux niveaux d'onglets ont chacun leur style.

Travaille sur une COPIE du projet de démonstration (deux fois, la seconde
dans un sous-dossier), avec un magasin de réglages jetable.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FIT = Path(__file__).resolve().parent.parent
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO)
PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def copier_projet(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for s in (".SemanticModel", ".Report"):
        shutil.copytree(PBI / (PROJ + s), dest / (PROJ + s),
                        ignore=shutil.ignore_patterns(".pbi", "cache.abf"))
    for f in (PROJ + ".pbip", "measures_config.json", "TD_Indicateurs.xlsx"):
        if (PBI / f).exists():
            shutil.copy2(PBI / f, dest / f)
    return dest / (PROJ + ".pbip")


c = Path(tempfile.mkdtemp(prefix="pbid_ruban_"))
UN = copier_projet(c)
DEUX = copier_projet(c / "v2")
# l'app cherche son projet par défaut dans le dossier des projets : la copie
os.environ["PBIDOUILLE_PROJETS"] = str(c)
reglages_jetables("ruban")

from qtpy.QtWidgets import QApplication, QFileDialog, QTabWidget   # noqa: E402

qapp = QApplication.instance() or QApplication([])

from core.project import push_recent, reglages                    # noqa: E402
from core.theme import neon_stylesheet                            # noqa: E402

qapp.setStyleSheet(neon_stylesheet())
push_recent(reglages(), str(DEUX))
push_recent(reglages(), str(UN))
reglages().setValue("last_pbip", str(UN))

import app as application                                         # noqa: E402

fen = application.BidouilleWindow()
fen.resize(1500, 860)
fen.show()
qapp.processEvents()

print("1. une seule ligne")
check("le rapport ouvert est la copie", fen.project and fen.project.pbip == UN)
check("ni étiquette ni liste « Récents » à part",
      not hasattr(fen, "project_label") and not hasattr(fen, "cmb_recents"))
check("le bouton nomme le rapport", PROJ in fen.btn_projet.text())
check("le chemin complet est en infobulle", str(UN) in fen.btn_projet.toolTip())
check("le config est sur la même ligne que le rapport",
      abs(fen.btn_config.geometry().center().y()
          - fen.btn_projet.geometry().center().y()) <= 4)
check("à côté du .pbip, le config montre son nom seul",
      fen.btn_config.text() == "📄 measures_config.json")
ordre = [fen.btn_projet, fen.btn_config, fen.btn_sauvegardes, fen.btn_journal]
check("de gauche à droite : rapport, config, …, restaurer, lancements",
      [b.x() for b in ordre] == sorted(b.x() for b in ordre))

print("2. le menu du rapport")
fen.menu_projet.aboutToShow.emit()
actions = [a for a in fen.menu_projet.actions() if not a.isSeparator()]
textes = [a.text() for a in actions]
recents = [a for a in actions if a.isCheckable()]
check("il liste les deux récents", len(recents) == 2)
check("deux homonymes se distinguent par leur dossier",
      any("v2" in a.text() for a in recents) and len(set(a.text() for a in recents)) == 2)
check("le rapport ouvert est coché, et lui seul",
      [a.toolTip() for a in recents if a.isChecked()] == [str(UN)])
check("il propose d'ouvrir un autre rapport", "Ouvrir un autre rapport…" in textes)

autre = next(a for a in recents if a.toolTip() == str(DEUX))
autre.trigger()
qapp.processEvents()
check("choisir un récent l'ouvre", fen.project.pbip == DEUX
      and fen.windowTitle().endswith(PROJ))
fen.menu_projet.aboutToShow.emit()
check("… et c'est lui qui est coché ensuite",
      [a.toolTip() for a in fen.menu_projet.actions()
       if a.isCheckable() and a.isChecked()] == [str(DEUX)])

vrai_dialogue = QFileDialog.getOpenFileName
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(UN), ""))
next(a for a in fen.menu_projet.actions() if a.text() == "Ouvrir un autre rapport…").trigger()
QFileDialog.getOpenFileName = vrai_dialogue
qapp.processEvents()
check("« Ouvrir un autre rapport… » ouvre le .pbip choisi", fen.project.pbip == UN)

print("3. restaurer une sauvegarde")
check("le bouton dit qu'il restaure", "Restaurer" in fen.btn_sauvegardes.text()
      and "💾" not in fen.btn_sauvegardes.text())
check("il est actif avec un rapport ouvert", fen.btn_sauvegardes.isEnabled())
vu: dict = {}


class FauxDialogue:
    def __init__(self, racine, parent=None, on_restored=None):
        vu["racine"] = Path(racine)
        self.on_restored = on_restored

    def exec_(self):
        self.on_restored({"restaurés": ["a", "b"], "sauvegarde_avant": str(c / "x")})

    exec = exec_


import tabs.dialog_backups as db                                  # noqa: E402

vrai, db.BackupsDialog = db.BackupsDialog, FauxDialogue
rechargements = []
vrai_reload = fen._reload_all
fen._reload_all = lambda: rechargements.append(1)
fen.btn_sauvegardes.click()
db.BackupsDialog, fen._reload_all = vrai, vrai_reload
check("la fenêtre porte sur le rapport ouvert", vu.get("racine") == UN.parent)
check("une restauration fait relire les onglets", rechargements == [1])
check("… et le journal le dit", "Restauré : 2 fichier(s)" in fen.journal.texte())

check("ChopChop n'a plus son bouton dans l'app",
      fen.tab_chopchop.panel.btn_backups.isHidden())
from unused_measures_ui import ChopChopPanel                      # noqa: E402

autonome = ChopChopPanel()
check("… mais la fenêtre autonome le garde", not autonome.btn_backups.isHidden())

print("4. deux niveaux d'onglets")
check("les onglets de l'app ont leur nom de style",
      fen.tabs.objectName() == "ongletsPrincipaux")
check("les sous-onglets de Mesures aussi",
      fen.tab_config.inner.objectName() == "sousOnglets"
      and isinstance(fen.tab_config.inner, QTabWidget))
qss = neon_stylesheet()
check("le thème les distingue", "#ongletsPrincipaux > QTabBar::tab" in qss
      and "#sousOnglets > QTabBar::tab" in qss)

fen.tab_config._set_dirty(False)
fen.close()
shutil.rmtree(c, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
