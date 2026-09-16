# -*- coding: utf-8 -*-
"""Catalogue de variations + selection par rapport.

    py _tests\\test_catalogue.py

Le measures_config.json porte TOUTES les variations et voyage d'un rapport a
l'autre ; chaque rapport choisit les siennes dans pbidouille_variations.json,
pose a cote du .pbip. Ce test verifie que la selection filtre bien la
generation, sans jamais toucher au catalogue partage.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
import generate_measures as gm                               # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx",
              "measures_config.json")


PROJ = "Fitbit for random devs"
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def projet():
    c = Path(tempfile.gettempdir()) / "pbidouille_cat"
    rmtree(c)
    c.mkdir(parents=True)
    for suffixe in (".Report", ".SemanticModel"):
        shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
    shutil.copy2(FIT / (PROJ + ".pbip"), c / (PROJ + ".pbip"))
    shutil.copy2(FIT / "TD_Indicateurs.xlsx", c / "TD_Indicateurs.xlsx")
    return c


# ===================================================================== 1
print("1. lecture / ecriture de la selection")
c = projet()
check("aucun fichier = aucun choix (toutes actives)", gm.read_selection(c) is None)
gm.write_selection(c, ["7d avg", "PY"], ["7d avg", "PY", "YTD"])
check("fichier ecrit", (c / gm.SELECTION_FILE).exists())
check("relu tel quel", gm.read_selection(c) == ["7d avg", "PY"])
gm.write_selection(c, ["7d avg", "PY", "YTD"], ["7d avg", "PY", "YTD"])
check("tout coche = le fichier disparait (etat par defaut)",
      not (c / gm.SELECTION_FILE).exists() and gm.read_selection(c) is None)
(c / gm.SELECTION_FILE).write_text("pas du json", encoding="utf-8")
check("fichier illisible = on retombe sur « toutes »", gm.read_selection(c) is None)
(c / gm.SELECTION_FILE).unlink()

# ===================================================================== 2
print("2. apply_selection : variations et branches")
cfg = json.loads((FIT / "measures_config.json").read_text(encoding="utf-8"))
V, B = cfg["variations"], cfg["branches"]
v, b = gm.apply_selection(dict(V), dict(B), ["7d avg", "YTD", "PY"], lambda *_: None)
check("seules les actives restent", set(v) == {"7d avg", "YTD", "PY"})
check("la branche YTD survit car sa variation est active", list(b) == ["YTD"])
v, b = gm.apply_selection(dict(V), dict(B), ["7d avg", "PY"], lambda *_: None)
check("desactiver YTD retire aussi la BRANCHE YTD", list(b) == [])
journal = []
gm.apply_selection(dict(V), dict(B), ["7d avg", "inexistante"], journal.append)
check("un id inconnu est signale, pas fatal",
      any("inexistante" in l for l in journal))
v, b = gm.apply_selection(dict(V), dict(B), None, lambda *_: None)
check("None = catalogue complet", len(v) == len(V))

# ===================================================================== 3
print("3. generation reelle : le rapport ne recoit QUE sa selection")
shutil.copy2(FIT / "measures_config.json", c / "measures_config.json")
SM = c / (PROJ + ".SemanticModel")


def genere():
    conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
    logs = []
    st = gm.generate(SM, conf, dry_run=True, log=logs.append)
    return set(st["created"]) | set(st["updated"]) | set(st["unchanged"]), logs


tout, _ = genere()
check("sans selection : les 7d avg sont generees",
      any(n.endswith(" 7d avg") for n in tout))
check("… et les sparkline aussi", any(n.endswith(" sparkline") for n in tout))

gm.write_selection(c, ["7d avg", "PY", "YTD"], list(cfg["variations"]))
part, logs = genere()
check("avec selection : 7d avg toujours la",
      any(n.endswith(" 7d avg") for n in part))
check("sparkline DESACTIVEE : plus aucune",
      not any(n.endswith(" sparkline") for n in part))
check("MTD desactivee : plus aucune", not any(n.endswith(" MTD") for n in part))
check("la branche YTD fonctionne encore",
      any(" YTD " in n or n.endswith(" YTD") for n in part))
check("moins de mesures qu'avec tout le catalogue", len(part) < len(tout))
check("le journal annonce la selection",
      any("Catalogue :" in l and "active(s)" in l for l in logs))
print("   " + next(l for l in logs if "Catalogue :" in l))

check("le CATALOGUE partage n'a pas bouge",
      json.loads((c / "measures_config.json").read_text(encoding="utf-8"))["variations"].keys()
      == cfg["variations"].keys())

gm.write_selection(c, [], list(cfg["variations"]))
try:
    genere()
    check("selection vide = erreur actionnable", False)
except SystemExit as e:
    check("selection vide = erreur actionnable", "Aucune variation active" in str(e))

# ===================================================================== 4
print("4. UI : cases a cocher et fichier de selection")
from PySide6.QtWidgets import QApplication                   # noqa: E402
from PySide6.QtCore import Qt                                # noqa: E402
from core.project import Project                             # noqa: E402
import tabs.tab_config as tc                                 # noqa: E402

(c / gm.SELECTION_FILE).unlink(missing_ok=True)
app = QApplication.instance() or QApplication([])
tab = tc.ConfigTab()
tab.set_project(Project(c / (PROJ + ".pbip")))
tab._config = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
tab._populate_list()
check("toutes cochees au depart", len(tab._cochees()) == len(tab._variations()))
check("aucun fichier cree tant qu'on ne touche a rien",
      not (c / gm.SELECTION_FILE).exists())
check("etiquette « toutes actives »", "toutes actives" in tab.lbl_catalogue.text())

for i in range(tab.lst.count()):
    if tab.lst.item(i).text() in ("sparkline", "MTD"):
        tab.lst.item(i).setCheckState(Qt.Unchecked)
check("le fichier de selection est ecrit aussitot",
      (c / gm.SELECTION_FILE).exists())
check("il contient les actives, pas les desactivees",
      "sparkline" not in gm.read_selection(c) and "7d avg" in gm.read_selection(c))
check("etiquette mise a jour", "sur" in tab.lbl_catalogue.text())
check("le config en memoire garde TOUT le catalogue",
      len(tab._variations()) == len(cfg["variations"]))

tab._tout_cocher(True)
check("« Tout » remet le defaut et retire le fichier",
      not (c / gm.SELECTION_FILE).exists())
tab._tout_cocher(False)
check("« Aucune » est possible (l'erreur vient a la generation)",
      gm.read_selection(c) == [])

tab.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
