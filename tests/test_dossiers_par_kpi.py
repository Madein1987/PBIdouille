# -*- coding: utf-8 -*-
"""Rangement des dossiers : par VARIATION (défaut) ou par KPI.

    py tests\\test_dossiers_par_kpi.py

Vérifie :
  1. les motifs de chaque rangement (generate_measures.motifs_dossiers) ;
  2. une vraie génération par KPI : la base reste dans son dossier, ses
     variations dans <dossier>\\<KPI>, la branche et ses variations dans
     <dossier>\\<KPI>\\<branche> — cibles comprises ;
  3. basculer d'un rangement à l'autre DÉPLACE les mesures (modifiées, pas
     recréées), les bases restent des bases, et le retour rend les dossiers
     d'avant ;
  4. ⚙ Réglages → Génération : la liste « Dossiers », les motifs grisés par
     KPI, et la clé `folderLayout` écrite seulement pour « kpi ».

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
from _fixture import (exiger_projet, ajouter_cibles, reglages_jetables,   # noqa: E402
                      PROJET_DEMO)

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")
reglages_jetables("dossiers_par_kpi")

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
print("1. les motifs")
check("défaut : ceux des settings, la variation en branche comme les autres",
      gm.motifs_dossiers({"displayFolderPattern": "{baseFolder}\\_{variation}",
                          "branchFolderPattern": "{baseFolder}\\__{branch}"})
      == ("{baseFolder}\\_{variation}", "{baseFolder}\\__{branch}",
          "{baseFolder}\\_{variation}"))
check("par KPI : les motifs des settings sont ignorés",
      gm.motifs_dossiers({"folderLayout": "kpi", "displayFolderPattern": "x"})
      == ("{baseFolder}\\{kpi}", "{baseFolder}\\{kpi}\\{branch}", "{baseFolder}"))
check("valeur inconnue = par variation", gm.motifs_dossiers({"folderLayout": "?"})[0]
      == "{baseFolder}")

# ---------------------------------------------------------------------------
copie = Path(tempfile.gettempdir()) / "pbid_dossiers_par_kpi"
rmtree(copie)
copie.mkdir(parents=True)
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
for f in (PROJ + ".pbip", "TD_Indicateurs.xlsx"):
    if (PBI / f).exists():
        shutil.copy2(PBI / f, copie / f)
MODELE = copie / (PROJ + ".SemanticModel")

conf = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))
SRC = conf["settings"]["sourceFolder"]
_, bases = gm.read_measures(MODELE, conf)
K = bases[0]
ajouter_cibles(MODELE, [K])
conf["kpiMeasureFolders"] = [{"folder": "_cibles", "calcul": "Cible"}]
B = list((conf.get("branches") or {}).keys())[0]
# la démo n'applique aucune variation aux cibles : on en donne une
VC = next(v for v, t in conf["variations"].items()
          if v != B and not t.get("displayFolder"))
conf["variations"][VC]["appliesToCibles"] = True


def impose(n, arbre) -> bool:
    """La variation de cette mesure impose-t-elle son propre dossier ?"""
    return bool((conf["variations"].get(arbre[n]["variation"]) or {}).get("displayFolder"))


def generer(layout):
    c = json.loads(json.dumps(conf))
    if layout:
        c["settings"]["folderLayout"] = layout
    st = gm.generate(MODELE, c, dry_run=False, remove_orphans=True, log=lambda *a: None)
    mesures, b = gm.read_measures(MODELE, c)
    arbre = {n["name"]: n for n in st["arbre"]}
    return st, {n: e["folder"] for n, e in mesures.items()}, b, arbre


print("2. une génération par KPI")
gm.generate(MODELE, json.loads(json.dumps(conf)), dry_run=False, remove_orphans=True,
            log=lambda *a: None)
_, avant, _, _ = generer(None)
st, dossiers, bases_kpi, arbre = generer("kpi")
var_k = [n for n, x in arbre.items() if x["parent"] == K and x["type"] == "variation"]
br = next(n for n, x in arbre.items() if x["parent"] == K and x["type"] == "branche")
sous_br = [n for n, x in arbre.items() if x["parent"] == br]
check(f"la base « {K} » reste dans {SRC}", dossiers[K] == SRC)
check(f"ses variations dans {SRC}\\{K} ({len(var_k)})",
      var_k and all(dossiers[n] == f"{SRC}\\{K}" for n in var_k if not impose(n, arbre)))
check(f"la mesure de branche « {br} » dans {SRC}\\{K}\\{B}",
      dossiers[br] == f"{SRC}\\{K}\\{B}")
check(f"… et ses variations avec elle, pas un cran plus bas ({len(sous_br)})",
      sous_br and all(dossiers[n] == f"{SRC}\\{K}\\{B}" for n in sous_br
                      if not impose(n, arbre)))
imp = [n for n in var_k if impose(n, arbre)]
imp_br = [n for n in sous_br if impose(n, arbre)]
check(f"un dossier IMPOSÉ ({{baseFolder}}\\_SVG, {{folder}}\\_CF) reste dans le "
      f"dossier du KPI : {sorted({dossiers[n] for n in imp})}",
      imp and all(dossiers[n].startswith(f"{SRC}\\{K}\\") for n in imp))
check("… et dans celui de la branche en branche",
      imp_br and all(dossiers[n].startswith(f"{SRC}\\{K}\\{B}\\") for n in imp_br))
cible = next(n for n, x in arbre.items() if x["type"] == "cible")
var_c = [n for n, x in arbre.items() if x["parent"] == cible and x["type"] == "variation"]
check(f"la cible reste dans _cibles, ses variations dans _cibles\\{K}",
      dossiers[cible] == "_cibles" and var_c
      and all(dossiers[n] == f"_cibles\\{K}" for n in var_c))
check("un dossier par KPI : chaque KPI a le sien",
      all(dossiers[n] == f"{SRC}\\{arbre[n]['kpi']}"
          for n, x in arbre.items() if x["type"] == "variation" and x["parent"] in bases
          and not impose(n, arbre)))

print("3. basculer déplace, ne recrée pas")
check("le passage par KPI n'a rien créé : tout est « modifié »",
      not st["created"] and len(st["updated"]) > 0)
check("les bases restent les bases", bases_kpi == bases)
st2, retour, _, _ = generer(None)
check("le retour par variation rend exactement les dossiers d'avant",
      retour == avant and not st2["created"])
check(f"(par variation, la variation en branche est sous {SRC}\\__{B}\\…)",
      retour[sous_br[0]].startswith(f"{SRC}\\__{B}\\"))

# ---------------------------------------------------------------------------
print("4. ⚙ Réglages → Génération")
from qtpy.QtWidgets import QApplication                          # noqa: E402
app = QApplication.instance() or QApplication([])
import tabs.tab_config as tc                                     # noqa: E402
from core.project import Project                                 # noqa: E402

(copie / "measures_config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
ct = tc.ConfigTab()
ct.set_project(Project(copie / (PROJ + ".pbip")))
ct._load_global()
check("par défaut : « par variation », motifs modifiables",
      ct.g_folderLayout.currentData() == "variation" and ct.g_folderPattern.isEnabled())
check("charger ne salit pas le config", not ct._dirty)
ct.g_folderLayout.setCurrentIndex(ct.g_folderLayout.findData("kpi"))
check("par KPI : les deux motifs sont grisés, et le config est à enregistrer",
      not ct.g_folderPattern.isEnabled() and not ct.g_branchFolderPattern.isEnabled()
      and ct._dirty)
ct._commit_global()
check("folderLayout = kpi écrit, les motifs gardés pour le retour",
      ct._config["settings"].get("folderLayout") == "kpi"
      and ct._config["settings"].get("displayFolderPattern") == "{baseFolder}\\_{variation}")
ct.g_folderLayout.setCurrentIndex(ct.g_folderLayout.findData("variation"))
ct._commit_global()
check("par variation : la clé disparaît (c'est le défaut)",
      "folderLayout" not in ct._config["settings"])
ct._config["settings"]["folderLayout"] = "kpi"
ct._load_global()
check("un config par KPI se rouvre par KPI", ct.g_folderLayout.currentData() == "kpi")

ct.deleteLater()
rmtree(copie)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
