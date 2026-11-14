# -*- coding: utf-8 -*-
"""La mesure Switch n'est plus générée — et ce qu'elle a laissé s'en va proprement.

    py tests\\test_sans_switch.py

La mesure Switch (SWITCH(SELECTEDVALUE(...)) sur tous les KPI) et ses
variations produisaient beaucoup d'erreurs et ne servaient pas : le générateur
ne les écrit plus. Un modèle qui les porte encore les voit comme des
orphelines — retirées si « Supprimer les orphelines » est coché, gardées
sinon — et le journal le dit en clair. Un bloc « switch » resté dans le
config est ignoré.

Travaille sur une COPIE du projet de démonstration (qui a encore ses mesures
Switch).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

FIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "measures_config.json")

import generate_measures as gm                      # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def copie(nom):
    c = Path(tempfile.gettempdir()) / nom
    rmtree(c)
    c.mkdir(parents=True)
    shutil.copytree(FIT / (PROJ + ".SemanticModel"), c / (PROJ + ".SemanticModel"))
    return c


def mesures_switch(c):
    t = (c / (PROJ + ".SemanticModel") / "definition" / "tables" / "_mesures.tmdl"
         ).read_text(encoding="utf-8")
    return re.findall(r"annotation MeasureVariation = (switch\|.*|Switch KPI[^\n]*)", t)


conf = json.loads((FIT / "measures_config.json").read_text(encoding="utf-8"))
# un config d'une version précédente, avec son bloc switch ACTIVÉ
conf["switch"] = {"enabled": True, "name": "Switch KPI",
                  "selector": "'TD_KPI'[mesure]", "displayFolder": "_switch"}

print("1. le modèle de démonstration a encore ses mesures Switch")
c = copie("pbid_sans_switch_garde")
avant = mesures_switch(c)
check(f"au départ : {len(avant)} mesure(s) Switch générées", len(avant) > 0)

print("2. orphelines GARDÉES : rien ne disparaît en douce")
logs = []
gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=False,
            remove_orphans=False, log=logs.append)
check("aucune mesure Switch générée de nouveau ni supprimée",
      mesures_switch(c) == avant)
avis = [l for l in logs if "Switch n'est plus générée" in l]
check("le journal le dit, avec le nombre", avis and str(len(avant)) in avis[0])
check("… et dit comment les retirer", avis and "Supprimer les orphelines" in avis[0])

print("3. orphelines SUPPRIMÉES : le modèle est nettoyé")
c2 = copie("pbid_sans_switch_retire")
logs = []
st = gm.generate(c2 / (PROJ + ".SemanticModel"), conf, dry_run=False,
                 remove_orphans=True, log=logs.append)
check("plus aucune mesure Switch dans le modèle", mesures_switch(c2) == [])
check("le journal annonce qu'elles partent",
      any("seront supprimées" in l for l in logs if "Switch" in l))
check("le bloc « switch » du config n'a rien recréé",
      not any("Switch KPI" in str(n) for n in (st or {}).get("created", [])))

print("4. un modèle sans Switch : pas d'avertissement inutile")
logs = []
gm.generate(c2 / (PROJ + ".SemanticModel"), conf, dry_run=True, log=logs.append)
check("silence quand il n'y a plus rien", not any("Switch" in l for l in logs))

rmtree(c)
rmtree(c2)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
