# -*- coding: utf-8 -*-
"""Enveloppe de branche : la branche ENTOURE la variation Reel.

    py tests\\test_enveloppe_branche.py

Deux facons de deriver une variation en branche :

  SUBSTITUTION (d'origine) : le DAX de la variation est re-emis avec la mesure
  de branche a l'interieur —
      Weight YTD PY = CALCULATE([Weight YTD], SAMEPERIODLASTYEAR(dates))

  ENVELOPPE (nouveau) : la branche entoure la variation Reel —
      Weight YTD PY = CALCULATE([Weight PY], DATESYTD(dates))

Interet : toutes les mesures de la branche se ressemblent, donc un ecart se
debogue forcement dans la variation Reel — et un correctif apporte a celle-ci se
repercute SANS regenerer, puisque la mesure est REFERENCEE et non recopiee.

Mais ce n'est PAS toujours equivalent, et c'est tout l'enjeu de ce fichier :

  · equivalent quand la variation DECALE le contexte (SAMEPERIODLASTYEAR) ;
  · faux quand elle EPINGLE une fenetre sur la borne du contexte
    (MAX({date}), DATEADD) — « 7d avg » enveloppe redevient le 7d avg ordinaire.

D'ou l'activation par variation (`wrapInBranch`), la branche ne fournissant que
le patron (`wrap`).
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

import generate_measures as gm                    # noqa: E402

PROJ = PROJET_DEMO
WRAP = "CALCULATE({variationRef}, DATESYTD({date}))"
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def projet(nom):
    c = Path(tempfile.gettempdir()) / ("pbid_env_" + nom)
    rmtree(c)
    c.mkdir(parents=True)
    for s in (".Report", ".SemanticModel"):
        shutil.copytree(PBI / (PROJ + s), c / (PROJ + s))
    shutil.copy2(PBI / "measures_config.json", c / "measures_config.json")
    return c


def dax_de(modele, nom):
    """Le DAX d'une mesure, sur une seule ligne, tel qu'ecrit dans le TMDL."""
    txt = (modele / "definition" / "tables" / "_mesures.tmdl").read_text(
        encoding="utf-8")
    m = re.search(r"\tmeasure '" + re.escape(nom) + r"' =(.*?)(?=\n\t\t[a-zA-Z])",
                  txt, re.S)
    return " ".join(l.strip() for l in m.group(1).strip().splitlines()) if m else None


def generer(c, wrap=None, enveloppables=()):
    conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
    conf["branches"]["YTD"] = {"wrap": wrap} if wrap else {}
    for vid in enveloppables:
        conf["variations"][vid]["wrapInBranch"] = True
    logs: list = []
    gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=False,
                log=logs.append)
    return conf, logs


# ===================================================================== 1
print("1. sans enveloppe declaree : rien ne change")
c = projet("sans")
M = c / (PROJ + ".SemanticModel")
_, logs = generer(c, wrap=None, enveloppables=("PY", "YoY %"))
check("aucune mesure enveloppee", not any("ENVELOPPENT" in l for l in logs))
check("substitution, comme avant",
      dax_de(M, "Weight YTD PY")
      == "CALCULATE([Weight YTD], SAMEPERIODLASTYEAR('dim_Date'[Date]))")
temoin_substitution = {n: dax_de(M, n) for n in
                       ("Weight YTD PY", "Weight YTD YoY %",
                        "Weight YTD 7d avg", "Weight YTD Δ 7d")}
rmtree(c)

# ===================================================================== 2
print("2. enveloppe declaree, mais AUCUNE variation cochee")
c = projet("aucune")
M = c / (PROJ + ".SemanticModel")
_, logs = generer(c, wrap=WRAP, enveloppables=())
check("le patron seul ne suffit pas",
      not any("ENVELOPPENT" in l for l in logs))
check("les mesures sont identiques au cas 1",
      {n: dax_de(M, n) for n in temoin_substitution} == temoin_substitution)
rmtree(c)

# ===================================================================== 3
print("3. enveloppe active sur les variations de DECALAGE")
c = projet("decalage")
M = c / (PROJ + ".SemanticModel")
_, logs = generer(c, wrap=WRAP, enveloppables=("PY", "YoY %"))
check("le journal compte les mesures enveloppees",
      any("ENVELOPPENT" in l for l in logs))

for vid in ("PY", "YoY %"):
    obtenu = dax_de(M, "Weight YTD " + vid)
    attendu = "CALCULATE([Weight " + vid + "], DATESYTD('dim_Date'[Date]))"
    check(f"« Weight YTD {vid} » enveloppe la mesure Reel", obtenu == attendu)
    if obtenu != attendu:
        print("      obtenu  :", obtenu)

print("   les NON cochees restent en substitution")
for n in ("Weight YTD 7d avg", "Weight YTD Δ 7d"):
    check("inchangee : " + n, dax_de(M, n) == temoin_substitution[n])

print("   ce qui n'est PAS une branche ne bouge pas")
check("la variation Reel elle-meme",
      dax_de(M, "Weight PY")
      == "CALCULATE([Weight], SAMEPERIODLASTYEAR('dim_Date'[Date]))")
check("la base de branche",
      dax_de(M, "Weight YTD")
      == "CALCULATE([Weight], DATESYTD('dim_Date'[Date]))")

print("   tout le reste de la mesure est inchange")
txt = (M / "definition" / "tables" / "_mesures.tmdl").read_text(encoding="utf-8")
bloc = re.search(r"\tmeasure 'Weight YTD PY' =.*?annotation MeasureVariation = (.*)",
                 txt, re.S)
check("l'annotation reste « base de branche|variation »",
      bloc and bloc.group(1).splitlines()[0].strip() == "Weight YTD|PY")
check("la mesure existe dans le parametre de champ",
      "NAMEOF([Weight YTD PY])" in
      (M / "definition" / "tables" / "P_Indicateurs_parCalcul.tmdl")
      .read_text(encoding="utf-8"))

print("   idempotence")
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
conf["branches"]["YTD"] = {"wrap": WRAP}
for vid in ("PY", "YoY %"):
    conf["variations"][vid]["wrapInBranch"] = True
st = gm.generate(M, conf, dry_run=True, log=lambda *_: None)
check("2e passe : rien a creer ni a mettre a jour",
      not st["created"] and not st["updated"])
rmtree(c)

# ===================================================================== 4
print("4. garde-fous")
c = projet("garde")
M = c / (PROJ + ".SemanticModel")
# Une variation enveloppable qui ne s'applique PAS aux KPI n'est generee ni en
# Reel ni en branche : la 2e passe l'ecarte AVANT l'enveloppe (allowed_set).
# C'est le bon comportement — et ca montre que le repli « mesure Reel absente »
# du moteur est un filet defensif, sans chemin atteignable par le config : les
# deux passes appliquent les MEMES filtres, donc si la Reel est ecartee la
# branche l'est aussi.
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
conf["branches"]["YTD"] = {"wrap": WRAP}
conf["variations"]["PY"]["wrapInBranch"] = True
conf["variations"]["PY"]["appliesToKpi"] = False
logs = []
gm.generate(M, conf, dry_run=False, log=logs.append)
check("variation hors KPI : ni Reel ni branche",
      dax_de(M, "Weight PY") is None and dax_de(M, "Weight YTD PY") is None)
check("… et aucun repli n'a eu a etre annonce",
      not any("repli sur la substitution" in l for l in logs))
check("les autres variations sont intactes",
      dax_de(M, "Weight YTD Δ 7d") is not None)

# enveloppable coche mais la branche ne declare PAS de patron -> substitution
c2 = projet("garde2")
M2 = c2 / (PROJ + ".SemanticModel")
generer(c2, wrap=None, enveloppables=("PY",))
check("coche sans patron de branche = substitution",
      dax_de(M2, "Weight YTD PY")
      == "CALCULATE([Weight YTD], SAMEPERIODLASTYEAR('dim_Date'[Date]))")
rmtree(c2)
rmtree(c)

# ===================================================================== 5
print("5. l'UI : patron par branche, case par variation")
from qtpy.QtWidgets import QApplication                     # noqa: E402
from core.project import Project                            # noqa: E402
import tabs.tab_config as tc                                # noqa: E402

app = QApplication.instance() or QApplication([])
c = projet("ui")
onglet = tc.ConfigTab()
onglet.set_project(Project(c / (PROJ + ".pbip")))
onglet._load_global()
check("le champ « Enveloppe » existe", hasattr(onglet, "g_branch_wrap"))
check("la case « enveloppable » existe", hasattr(onglet, "chk_wrap"))
check("vide au depart (substitution)", onglet.g_branch_wrap.text().strip() == "")

onglet.g_branch_wrap.setText(WRAP)
onglet._commit_global()
check("le patron est ecrit sur la branche",
      (onglet._config["branches"]["YTD"] or {}).get("wrap") == WRAP)
onglet._load_global()
check("… et relu a l'affichage", onglet.g_branch_wrap.text() == WRAP)
onglet.g_branch_wrap.setText("")
onglet._commit_global()
check("vider retire la cle (retour a la substitution)",
      "wrap" not in (onglet._config["branches"]["YTD"] or {}))

onglet._populate_list(select="PY")
onglet.chk_wrap.setChecked(True)
onglet._commit_form()
check("cocher ecrit wrapInBranch",
      onglet._config["variations"]["PY"].get("wrapInBranch") is True)
onglet.chk_wrap.setChecked(False)
onglet._commit_form()
check("decocher retire la cle (on n'ecrit que le non-defaut)",
      "wrapInBranch" not in onglet._config["variations"]["PY"])
check("le jeton {variationRef} est connu du lint",
      "variationRef" in tc.KNOWN_PLACEHOLDERS)

onglet.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
