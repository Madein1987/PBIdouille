# -*- coding: utf-8 -*-
"""Branches : on DÉCOCHE ce qu'une branche n'applique pas, on ne coche pas ce
qu'elle applique.

    py tests\\test_branches_exclusions.py

Vérifie :
  1. la règle (generate_measures.variations_de_branche) : toutes sauf
     elle-même, moins `excludeVariations` ; l'ancienne liste blanche
     `variations` encore lue telle quelle ;
  2. la génération : une variation exclue n'a pas de mesure en branche, une
     variation AJOUTÉE après coup en a une sans rien toucher à la branche ;
  3. ⚙ Réglages → Branches : l'ancien format s'affiche coché comme avant et
     se réécrit en exclusions ; une variation ajoutée arrive cochée ; décocher
     écrit une exclusion ; une branche sans exclusion n'écrit rien.

Travaille sur une COPIE du projet de démonstration, magasin de réglages jetable.
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
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")
reglages_jetables("branches_exclusions")

import generate_measures as gm                                   # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


# ---------------------------------------------------------------------------
print("1. la règle")
V = {"7d avg": {}, "PY": {}, "YTD": {}, "écart": {}}
check("sans rien : toutes sauf elle-même",
      gm.variations_de_branche("YTD", {}, V) == ["7d avg", "PY", "écart"])
check("une branche ne s'applique jamais à elle-même (casse comprise)",
      "YTD" not in gm.variations_de_branche("ytd", None, V))
check("excludeVariations retire ce qu'elle liste, dans l'ordre du config",
      gm.variations_de_branche("YTD", {"excludeVariations": ["PY"]}, V)
      == ["7d avg", "écart"])
check("… et une variation inconnue n'y change rien",
      gm.variations_de_branche("YTD", {"excludeVariations": ["fantôme"]}, V)
      == ["7d avg", "PY", "écart"])
check("l'ancienne liste blanche est encore lue telle quelle",
      gm.variations_de_branche("YTD", {"variations": ["PY"]}, V) == ["PY"])
V2 = dict(V, nouvelle={})
check("une variation ajoutée entre d'office (exclusions)",
      "nouvelle" in gm.variations_de_branche("YTD", {"excludeVariations": ["PY"]}, V2))

# ---------------------------------------------------------------------------
copie = Path(tempfile.gettempdir()) / "pbid_branches_exclusions"
rmtree(copie)
copie.mkdir(parents=True)
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
for f in (PROJ + ".pbip", "TD_Indicateurs.xlsx"):
    if (PBI / f).exists():
        shutil.copy2(PBI / f, copie / f)
MODELE = copie / (PROJ + ".SemanticModel")
conf = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))
B = list((conf.get("branches") or {}).keys())[0]
autres = [v for v in conf["variations"] if v != B]
EXCLUE, GARDEE = autres[0], autres[1]

print("2. la génération")


def en_branche(c) -> set:
    st = gm.generate(MODELE, json.loads(json.dumps(c)), dry_run=True, log=lambda *a: None)
    return {n["variation"] for n in st["arbre"]
            if n.get("branche") == B and n["type"] == "variation"}


c = json.loads(json.dumps(conf))
c["branches"] = {B: {"excludeVariations": [EXCLUE]}}
vus = en_branche(c)
check(f"« {EXCLUE} » exclue : aucune mesure en branche {B}", EXCLUE not in vus)
check(f"« {GARDEE} » non exclue : bien générée en branche", GARDEE in vus)
NOUVELLE = "maison test"
c["variations"][NOUVELLE] = dict(c["variations"][GARDEE])
c["variations"][NOUVELLE]["namePattern"] = "{base} maison test"
check("une variation ajoutée après coup est générée en branche, sans toucher "
      "à la branche", NOUVELLE in en_branche(c))

# ---------------------------------------------------------------------------
print("3. ⚙ Réglages → Branches")
from qtpy.QtCore import Qt                                       # noqa: E402
from qtpy.QtWidgets import QApplication                          # noqa: E402
app = QApplication.instance() or QApplication([])
import tabs.tab_config as tc                                     # noqa: E402
from core.project import Project                                 # noqa: E402

ancien = json.loads(json.dumps(conf))
ancien["branches"] = {B: {"variations": [GARDEE]}}               # liste blanche
(copie / "measures_config.json").write_text(json.dumps(ancien, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
ct = tc.ConfigTab()
ct.set_project(Project(copie / (PROJ + ".pbip")))
ct._load_global()
app.processEvents()


def coches() -> dict:
    lst = ct.g_branch_restrict
    return {lst.item(i).text(): lst.item(i).checkState() == Qt.Checked
            for i in range(lst.count())}


check(f"l'ancien format s'affiche comme avant : seule « {GARDEE} » cochée",
      coches().get(GARDEE) is True
      and not any(v for k, v in coches().items() if k != GARDEE))
ct._commit_global()
bdef = ct._config["branches"][B]
check("… et se réécrit en exclusions (plus de clé « variations »)",
      "variations" not in bdef
      and set(bdef.get("excludeVariations", [])) == set(autres) - {GARDEE})
check("la génération lit pareil avant et après la réécriture",
      gm.variations_de_branche(B, ancien["branches"][B], conf["variations"])
      == gm.variations_de_branche(B, bdef, conf["variations"]))

print("   une variation ajoutée arrive cochée")
ct._config["branches"] = {B: {"excludeVariations": [EXCLUE]}}
ct._load_global()
ct._config["variations"][NOUVELLE] = dict(ct._config["variations"][GARDEE])
# « Sauvegarder » sans rouvrir les réglages : les listes affichées datent
# d'AVANT la nouvelle variation — c'est là que l'ancienne liste blanche
# l'excluait sans qu'on le voie
ct._commit_global()
check("enregistrée sans rouvrir ⚙ Réglages : elle n'est pas exclue",
      NOUVELLE not in ct._config["branches"][B].get("excludeVariations", [])
      and NOUVELLE in gm.variations_de_branche(B, ct._config["branches"][B],
                                               ct._config["variations"]))
ct._load_global()
check("en rouvrant ⚙ Réglages, elle est cochée", coches().get(NOUVELLE) is True)
check(f"… et « {EXCLUE} » reste décochée", coches().get(EXCLUE) is False)

print("   décocher écrit une exclusion, tout cocher n'écrit rien")
lst = ct.g_branch_restrict
for i in range(lst.count()):
    if lst.item(i).text() == GARDEE:
        lst.item(i).setCheckState(Qt.Unchecked)
ct._commit_global()
check(f"« {GARDEE} » décochée -> exclue",
      GARDEE in ct._config["branches"][B]["excludeVariations"])
for i in range(lst.count()):
    lst.item(i).setCheckState(Qt.Checked)
ct._commit_global()
check("tout coché : la branche n'a plus que {} (rien à exclure)",
      "excludeVariations" not in ct._config["branches"][B]
      and "variations" not in ct._config["branches"][B])

ct.deleteLater()
rmtree(copie)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
