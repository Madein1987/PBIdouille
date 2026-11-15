# -*- coding: utf-8 -*-
"""Les reglages globaux survivent au changement de projet.

    py tests\\test_reglages.py

Le chemin de la bibliotheque de variations est un reglage de L'APPLICATION :
un fichier global, souvent sur un lecteur partage, qui ne bouge pas quand on
change de rapport. Il ne doit donc jamais etre a redonner projet par projet.

Deux choses le rendaient fragile :

  · il vivait dans un SECOND magasin QSettings (« PBIdouille/PBIdouille »)
    alors que tout le reste etait sous « ChopChop/BIdouille » — deux endroits
    ou chercher ;
  · refermer le dialogue sans rien choisir memorisait une valeur VIDE, ce qui
    faisait retomber sur le defaut : le reglage avait l'air de se reinitialiser
    tout seul.

Les tests ecrivent dans un magasin JETABLE (nom d'app de test), jamais dans
les reglages reels de l'usager.
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
# les projets Power BI vivent HORS de l'outil (cf. moteurs/chemins.py)
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")

from qtpy.QtCore import QSettings                 # noqa: E402
from core import project as prj                   # noqa: E402

# --- magasins JETABLES : on ne touche pas aux reglages reels -----------------
prj.ORG_REGLAGES = "ChopChop"
prj.APP_REGLAGES = "BIdouille_TEST"
prj._ANCIEN_MAGASIN = ("PBIdouille_TEST", "PBIdouille_TEST")
prj.reglages().clear()
QSettings(*prj._ANCIEN_MAGASIN).clear()

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


# ===================================================================== 1
print("1. un seul magasin, et il reprend ce qui etait dans l'ancien")
check("reglages() pointe le magasin unique",
      prj.reglages().value("temoin", "") == "")
prj.ecrire_reglage("temoin", "abc")
check("ecrit puis relu", prj.lire_reglage("temoin") == "abc")
check("… et c'est bien le magasin de reglages()",
      prj.reglages().value("temoin", "") == "abc")

QSettings(*prj._ANCIEN_MAGASIN).setValue("vieux_reglage", "valeur d'avant")
check("une cle laissee dans l'ANCIEN magasin est reprise",
      prj.lire_reglage("vieux_reglage") == "valeur d'avant")
check("… et rapatriee pour de bon",
      prj.reglages().value("vieux_reglage", "") == "valeur d'avant")

print("2. une valeur vide n'efface jamais un reglage")
prj.ecrire_reglage("garde_moi", r"G:\partage\catalogue_variations.json")
for vide in ("", None):
    prj.ecrire_reglage("garde_moi", vide)
check("refermer un dialogue sans rien choisir ne defait rien",
      prj.lire_reglage("garde_moi") == r"G:\partage\catalogue_variations.json")
check("un defaut sert quand RIEN n'a jamais ete choisi",
      prj.lire_reglage("jamais_vue", "defaut") == "defaut")

# ===================================================================== 3
print("3. la bibliotheque ne suit pas le projet")
c = Path(tempfile.gettempdir()) / "pbidouille_reglages"
rmtree(c)
(c / "projetA").mkdir(parents=True)
(c / "projetB").mkdir(parents=True)
for dossier in ("projetA", "projetB"):
    for suffixe in (".Report", ".SemanticModel"):
        shutil.copytree(PBI / (PROJ + suffixe), c / dossier / (PROJ + suffixe))
    for f in ((PROJ + ".pbip"), "measures_config.json"):
        shutil.copy2(PBI / f, c / dossier / f)

# une bibliotheque « globale », hors des deux projets
biblio = c / "quelque_part" / "catalogue_variations.json"
biblio.parent.mkdir(parents=True)
biblio.write_text('{"variations": {}, "branches": {}}', encoding="utf-8")

from qtpy.QtWidgets import QApplication                     # noqa: E402
from core.project import Project                            # noqa: E402
import tabs.tab_config as tc                                # noqa: E402

app = QApplication.instance() or QApplication([])
onglet = tc.ConfigTab()
check("l'etiquette est remplie AVANT tout projet (la biblio n'en depend pas)",
      "catalogue_variations.json" in onglet.lbl_biblio.text())

onglet.set_project(Project(c / "projetA" / (PROJ + ".pbip")))
defaut = onglet._chemin_biblio()
check("sans rien de memorise : celui du dossier des projets Power BI",
      Path(defaut).name == "catalogue_variations.json"
      and Path(defaut).parent == PBI)
check("le defaut n'est PAS dans le dossier du projet",
      Path(defaut).parent != (c / "projetA"))

onglet._memoriser_biblio(str(biblio))
check("choisi : c'est bien lui", onglet._chemin_biblio() == str(biblio))

onglet.set_project(Project(c / "projetB" / (PROJ + ".pbip")))
check("changer de projet ne le change pas",
      onglet._chemin_biblio() == str(biblio))
check("… ni ne le rend relatif au nouveau projet",
      str(c / "projetB") not in onglet._chemin_biblio())

# un onglet tout neuf (= relancer l'app) le retrouve
autre = tc.ConfigTab()
autre.set_project(Project(c / "projetB" / (PROJ + ".pbip")))
check("un nouveau lancement le retrouve", autre._chemin_biblio() == str(biblio))
autre.deleteLater()

print("4. le chemin retenu est VISIBLE")
onglet.set_project(Project(c / "projetA" / (PROJ + ".pbip")))
check("l'etiquette montre le fichier", str(biblio) in onglet.lbl_biblio.text())
check("… et dit qu'il est memorise pour tous les projets",
      "tous les projets" in onglet.lbl_biblio.text())
onglet._memoriser_biblio(str(c / "disparu.json"))
check("fichier introuvable : l'etiquette le DIT",
      "introuvable" in onglet.lbl_biblio.text())
check("… au lieu de retomber en silence sur le defaut",
      onglet._chemin_biblio() == str(c / "disparu.json"))

# ===================================================================== 5
print("5. le gabarit du wireframe : projet d'abord, global en repli")
import tabs.tab_wireframe as tw                             # noqa: E402

wf = tw.WireframeTab()
wf.settings = prj.reglages()          # le magasin jetable, pas le vrai
projA = Project(c / "projetA" / (PROJ + ".pbip"))
projB = Project(c / "projetB" / (PROJ + ".pbip"))

gabarit = str(c / "projetA" / (PROJ + ".pbip"))
wf.project = projA
wf.settings.setValue(wf._tpl_key(), gabarit)
prj.ecrire_reglage(wf.CLE_TPL_GLOBAL, gabarit)
wf._tpl_load_for_project()
check("le gabarit du projet A est charge", wf._tpl_project is not None)

wf.project = projB                    # projet B : aucun gabarit propre
check("B n'a pas de gabarit memorise",
      not wf.settings.value(wf._tpl_key(), ""))
wf._tpl_load_for_project()
check("il retombe sur le DERNIER gabarit choisi (repli global)",
      wf._tpl_project is not None
      and str(wf._tpl_project.pbip) == gabarit)

propre = str(c / "projetB" / (PROJ + ".pbip"))
wf.settings.setValue(wf._tpl_key(), propre)
wf._tpl_load_for_project()
check("un choix propre au projet reste prioritaire",
      str(wf._tpl_project.pbip) == propre)

wf.deleteLater()
onglet.deleteLater()
app.processEvents()

prj.reglages().clear()
QSettings(*prj._ANCIEN_MAGASIN).clear()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
