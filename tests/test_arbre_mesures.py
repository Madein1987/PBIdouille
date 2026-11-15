# -*- coding: utf-8 -*-
"""Mesures → « Arbre des mesures » : ce que la génération produira, en arbre.

    py tests\\test_arbre_mesures.py

Vérifie :
  1. le générateur rend l'arbre : base -> variations, base -> mesure de
     branche -> variations en branche, KPI -> cible racine -> ses variations ;
  2. le marqueur des paramètres de champ suit les tables ET leurs filtres ;
  3. l'état (nouvelle / modifiée / inchangée) est celui que « Générer »
     annoncerait, et l'aperçu n'écrit rien ;
  4. la vue : un KPI par racine, le marqueur ◆, le filtre texte, le filtre
     « ◆ seulement », et le config EN MÉMOIRE (sans enregistrer).

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
# les projets Power BI vivent HORS de l'outil (cf. moteurs/chemins.py)
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
reglages_jetables("arbre")

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


copie = Path(tempfile.gettempdir()) / "pbid_arbre_mesures"
rmtree(copie)
copie.mkdir(parents=True)
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
for f in (PROJ + ".pbip", "TD_Indicateurs.xlsx"):
    if (PBI / f).exists():
        shutil.copy2(PBI / f, copie / f)
MODELE = copie / (PROJ + ".SemanticModel")

conf = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))
_, bases = gm.read_measures(MODELE, conf)
K = bases[0]
ajouter_cibles(MODELE, [K])
conf["kpiMeasureFolders"] = [{"folder": "_cibles", "calcul": "Cible"}]
branches = list((conf.get("branches") or {}).keys())
B = branches[0]
vars_fp = [v for v, t in conf["variations"].items()
           if t.get("inFieldParameter") and v not in branches]
V = vars_fp[0]
# la démo n'applique aucune variation aux cibles : on en donne une
conf["variations"][V]["appliesToCibles"] = True
conf["fieldParameter"] = dict(conf["fieldParameter"])
conf["fieldParameter"]["tables"] = [
    {"name": "P_tout"},
    {"name": "P_sans_" + V.replace(" ", "_"), "excludeVariations": [V]},
]
for k in ("tableNames", "tableNamesByKpi", "tableNamesKpiBase"):
    conf["fieldParameter"].pop(k, None)
(copie / "measures_config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2),
                                            encoding="utf-8")

# ---------------------------------------------------------------------------
print("1. le générateur rend l'arbre")
mtimes = {p: p.stat().st_mtime_ns for p in MODELE.rglob("*") if p.is_file()}
st = gm.generate(MODELE, json.loads(json.dumps(conf)), dry_run=True, log=lambda *a: None)
check("l'aperçu n'a rien écrit dans le modèle",
      {p: p.stat().st_mtime_ns for p in MODELE.rglob("*") if p.is_file()} == mtimes)
arbre = {n["name"]: n for n in st["arbre"]}
racines = [n for n in st["arbre"] if n["parent"] is None]
check(f"une racine par KPI ({len(bases)})",
      sorted(n["name"] for n in racines) == sorted(bases)
      and all(n["type"] == "base" for n in racines))
var_k = [n for n in st["arbre"] if n["parent"] == K and n["type"] == "variation"]
check(f"{K} -> ses variations", var_k and all(n["variation"] for n in var_k))
br_k = [n for n in st["arbre"] if n["parent"] == K and n["type"] == "branche"]
check(f"{K} -> sa mesure de branche {B}", len(br_k) >= 1 and br_k[0]["branche"] == B)
sous_br = [n for n in st["arbre"] if n["parent"] == br_k[0]["name"]]
check(f"la mesure de branche -> ses variations en branche ({len(sous_br)})",
      sous_br and all(n["branche"] == B and n["type"] == "variation" for n in sous_br))
cible = [n for n in st["arbre"] if n["type"] == "cible"]
check(f"la cible racine est sous son KPI ({K})",
      len(cible) == 1 and cible[0]["parent"] == K)
check("… et les variations de la cible sont sous elle",
      any(n["parent"] == cible[0]["name"] for n in st["arbre"]))
check("chaque parent existe dans l'arbre",
      all(n["parent"] is None or n["parent"] in arbre for n in st["arbre"]))

print("2. le marqueur suit les tables et leurs filtres")
check("la base est dans les deux tables", arbre[K]["tables"] == ["P_tout", conf["fieldParameter"]["tables"][1]["name"]])
nv = next(n for n in var_k if n["variation"] == V)
check(f"« {nv['name']} » seulement dans P_tout (l'autre l'écarte)", nv["tables"] == ["P_tout"])
hors = [n for n in st["arbre"] if not n["tables"]]
check(f"sans table = variation hors paramètre ({len(hors)} : sparkline, CF…)",
      hors and all(n["type"] == "variation"
                   and not conf["variations"][n["variation"]].get("inFieldParameter")
                   for n in hors))

print("3. l'état est celui de « Générer »")
check("nouvelle / modifiée / inchangée, ou « à la main » pour les racines",
      {n["etat"] for n in st["arbre"]} <= {"nouvelle", "modifiée", "inchangée", "à la main"}
      and all(n["etat"] == "à la main" for n in st["arbre"] if n["type"] in ("base", "cible")))
check("les comptes collent à ceux du générateur",
      sum(n["etat"] == "nouvelle" for n in st["arbre"]) == len(st["created"])
      and sum(n["etat"] == "modifiée" for n in st["arbre"]) == len(st["updated"]))
gm.generate(MODELE, json.loads(json.dumps(conf)), dry_run=False, remove_orphans=True,
            log=lambda *a: None)
st2 = gm.generate(MODELE, json.loads(json.dumps(conf)), dry_run=True, log=lambda *a: None)
check("après une vraie génération, tout ce qui est généré est « inchangée »",
      all(n["etat"] == "inchangée" for n in st2["arbre"]
          if n["type"] in ("variation", "branche")))

# ---------------------------------------------------------------------------
print("4. la vue")
from qtpy.QtWidgets import QApplication                          # noqa: E402
app = QApplication.instance() or QApplication([])
import tabs.tab_config as tc                                     # noqa: E402
from tabs.arbre_mesures import MARQUEUR                          # noqa: E402
from core.project import Project                                 # noqa: E402

ct = tc.ConfigTab()
ct.set_project(Project(copie / (PROJ + ".pbip")))
ct.inner.setCurrentIndex(tc.IDX_ARBRE)
app.processEvents()
vue = ct.arbre_mesures
check("l'onglet s'appelle « Arbre des mesures »",
      ct.inner.tabText(tc.IDX_ARBRE) == "Arbre des mesures")
check(f"un KPI par racine ({vue.arbre.topLevelItemCount()})",
      vue.arbre.topLevelItemCount() == len(bases))
it_k = vue.element(K)
check("la base porte le marqueur ◆", it_k is not None and it_k.text(1).startswith(MARQUEUR))
check("… et l'infobulle dit dans quelles tables", "P_tout" in it_k.toolTip(1))
it_br = vue.element(br_k[0]["name"])
check("la mesure de branche est enfant de son KPI", it_br is not None and it_br.parent() is it_k)
check("le résumé compte les KPI", f"{len(bases)} KPI" in vue.lbl_resume.text())

vue.ed_filtre.setText(B)
visibles = [vue.element(n["name"]) for n in sous_br]
check(f"filtre « {B} » : les variations en branche restent visibles",
      all(not i.isHidden() for i in visibles))
check("… une variation hors branche est cachée",
      next(vue.element(n["name"]) for n in var_k).isHidden())
vue.ed_filtre.setText("")
vue.chk_param.setChecked(True)
check("« ◆ seulement » : plus aucune ligne visible sans marqueur",
      all(vue.element(n["name"]).isHidden() for n in hors) if hors else True)
check("… les mesures marquées restent visibles", not vue.element(nv["name"]).isHidden())
vue.chk_param.setChecked(False)

print("   le config en mémoire, sans enregistrer")
ct._config["variations"][V]["inFieldParameter"] = False
ct._rafraichir_vue()
app.processEvents()
check(f"« {nv['name']} » perd son marqueur aussitôt",
      vue.element(nv["name"]) is not None and vue.element(nv["name"]).text(1) == "")
check("rien n'a été enregistré",
      json.loads((copie / "measures_config.json").read_text(encoding="utf-8"))
      ["variations"][V].get("inFieldParameter") is True)

ct.deleteLater()
rmtree(copie)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
