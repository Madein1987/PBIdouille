# -*- coding: utf-8 -*-
"""Enveloppe de branche : la branche ENTOURE la variation Reel — par defaut.

    py tests\\test_enveloppe_branche.py

Deux facons de deriver une variation en branche :

  ENVELOPPE (defaut) : la branche entoure la variation Reel —
      Weight YTD PY = CALCULATE([Weight PY], DATESYTD(dates))

  SUBSTITUTION : le DAX de la variation est recopie avec la mesure de branche
  a l'interieur —
      Weight YTD PY = CALCULATE([Weight YTD], SAMEPERIODLASTYEAR(dates))

Interet de l'enveloppe : toutes les mesures de la branche se lisent pareil,
donc un ecart se debogue dans la variation Reel — et un correctif apporte a
celle-ci se repercute SANS regenerer.

Le PATRON vient du DAX de la branche elle-meme : YTD =
CALCULATE({baseRef}, DATESYTD({date})), sa base devient {variationRef}. Il n'y
a donc rien a ecrire — c'est ce qui manquait : avant, il fallait cocher la
variation ET taper un patron dans la branche, et sans le patron la case ne
faisait rien.

Ce n'est PAS toujours equivalent (une variation qui EPINGLE une fenetre sur la
borne du contexte change de sens), d'ou deux portes de sortie : la branche
(`substitution`) ou la variation (`wrapInBranch: false`).
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
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")
reglages_jetables("enveloppe")

import generate_measures as gm                    # noqa: E402

PROJ = PROJET_DEMO
WRAP = "CALCULATE({variationRef}, DATESYTD({date}))"
DATES = "'dim_Date'[Date]"
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
    shutil.copy2(PBI / (PROJ + ".pbip"), c / (PROJ + ".pbip"))
    shutil.copy2(PBI / "measures_config.json", c / "measures_config.json")
    return c


def dax_de(modele, nom):
    """Le DAX d'une mesure, sur une seule ligne, tel qu'ecrit dans le TMDL."""
    txt = (modele / "definition" / "tables" / "_mesures.tmdl").read_text(
        encoding="utf-8")
    m = re.search(r"\tmeasure '" + re.escape(nom) + r"' =(.*?)(?=\n\t\t[a-zA-Z])",
                  txt, re.S)
    return " ".join(l.strip() for l in m.group(1).strip().splitlines()) if m else None


def generer(c, branche=None, sorties=(), retouche=None):
    """`branche` : la definition de YTD ({} par defaut) ; `sorties` : les
    variations qui refusent l'enveloppe."""
    conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
    conf["branches"]["YTD"] = dict(branche or {})
    for vid in sorties:
        conf["variations"][vid]["wrapInBranch"] = False
    if retouche:
        retouche(conf)
    logs: list = []
    gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=False, log=logs.append)
    return conf, logs


def enveloppe(vid):
    return f"CALCULATE([Weight {vid}], DATESYTD({DATES}))"


# ===================================================================== 0
print("0. le patron")
V = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))["variations"]
check("tire du DAX de la branche : sa base devient {variationRef}",
      gm.patron_enveloppe("YTD", {}, V) == WRAP)
check("[{base}] marche aussi",
      gm.patron_enveloppe("X", {}, {"X": {"dax": "TOTALYTD([{base}], {date})"}})
      == "TOTALYTD({variationRef}, {date})")
check("un patron ecrit l'emporte",
      gm.patron_enveloppe("YTD", {"wrap": "F({variationRef})"}, V) == "F({variationRef})")
check("substitution : pas de patron", gm.patron_enveloppe("YTD", {"substitution": True}, V) is None)
check("un DAX qui ne cite pas sa base ne peut pas envelopper",
      gm.patron_enveloppe("X", {}, {"X": {"dax": "BLANK()"}}) is None)
check("une variation s'enveloppe sauf si elle dit non",
      gm.enveloppable({}) and gm.enveloppable({"wrapInBranch": True})
      and not gm.enveloppable({"wrapInBranch": False}))
check("… ou si son DAX cite {branch} (ecrite POUR la branche) : recopiee",
      gm.enveloppable({"dax": "[{kpi} {branch} PY]"})
      and not gm.s_enveloppe({"dax": "[{kpi} {branch} PY]"})
      and gm.s_enveloppe({"dax": "CALCULATE({baseRef}, SAMEPERIODLASTYEAR({date}))"}))

# ===================================================================== 1
print("1. par defaut, sans rien ecrire : tout est enveloppe")
c = projet("defaut")
M = c / (PROJ + ".SemanticModel")
_, logs = generer(c)
check("le journal compte les mesures enveloppees", any("ENVELOPPENT" in l for l in logs))
for vid in ("PY", "YoY %", "7d avg", "Δ 7d"):
    obtenu = dax_de(M, "Weight YTD " + vid)
    check(f"« Weight YTD {vid} » enveloppe [Weight {vid}]", obtenu == enveloppe(vid))
    if obtenu != enveloppe(vid):
        print("      obtenu  :", obtenu)

print("   ce qui n'est PAS une variation de branche ne bouge pas")
check("la variation Reel elle-meme",
      dax_de(M, "Weight PY") == f"CALCULATE([Weight], SAMEPERIODLASTYEAR({DATES}))")
check("la base de branche", dax_de(M, "Weight YTD") == f"CALCULATE([Weight], DATESYTD({DATES}))")

print("   tout le reste de la mesure est inchange")
txt = (M / "definition" / "tables" / "_mesures.tmdl").read_text(encoding="utf-8")
bloc = re.search(r"\tmeasure 'Weight YTD PY' =.*?annotation MeasureVariation = (.*)",
                 txt, re.S)
check("l'annotation reste « base de branche|variation »",
      bloc and bloc.group(1).splitlines()[0].strip() == "Weight YTD|PY")
check("la mesure existe dans le parametre de champ",
      "NAMEOF([Weight YTD PY])" in
      (M / "definition" / "tables" / "P_Indicateurs_parCalcul.tmdl").read_text(encoding="utf-8"))

print("   idempotence")
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
conf["branches"]["YTD"] = {}
st = gm.generate(M, conf, dry_run=True, log=lambda *_: None)
check("2e passe : rien a creer ni a mettre a jour", not st["created"] and not st["updated"])
rmtree(c)

# ===================================================================== 2
print("2. les portes de sortie")
c = projet("sorties")
M = c / (PROJ + ".SemanticModel")
_, logs = generer(c, branche={"substitution": True})
check("branche en substitution : tout est recopie, comme avant",
      dax_de(M, "Weight YTD PY")
      == f"CALCULATE([Weight YTD], SAMEPERIODLASTYEAR({DATES}))"
      and not any("ENVELOPPENT" in l for l in logs))
temoin = {n: dax_de(M, n) for n in ("Weight YTD 7d avg", "Weight YTD Δ 7d")}
generer(c, sorties=("7d avg", "Δ 7d"))
check("une variation qui dit non est recopiee, elle seule",
      {n: dax_de(M, n) for n in temoin} == temoin
      and dax_de(M, "Weight YTD PY") == enveloppe("PY"))
generer(c, branche={"wrap": "TOTALYTD({variationRef}, {date})"})
check("un patron ecrit sur la branche est utilise",
      dax_de(M, "Weight YTD PY") == f"TOTALYTD([Weight PY], {DATES})")


def ytd_sans_base(conf):
    conf["variations"]["YTD"]["dax"] = "CALCULATE([Weight], DATESYTD({date}))"


_, logs = generer(c, retouche=ytd_sans_base)
check("une branche dont le DAX ne cite pas sa base : substitution, dite UNE fois",
      dax_de(M, "Weight YTD PY") == f"CALCULATE([Weight YTD], SAMEPERIODLASTYEAR({DATES}))"
      and sum("ne cite pas sa base" in l for l in logs) == 1)
rmtree(c)

# ===================================================================== 3
print("3. garde-fou")
c = projet("garde")
M = c / (PROJ + ".SemanticModel")
# une variation qui ne s'applique PAS aux KPI n'est generee ni en Reel ni en
# branche : la 2e passe l'ecarte AVANT l'enveloppe (allowed_set)


def py_hors_kpi(conf):
    conf["variations"]["PY"]["appliesToKpi"] = False


_, logs = generer(c, retouche=py_hors_kpi)
check("variation hors KPI : ni Reel ni branche",
      dax_de(M, "Weight PY") is None and dax_de(M, "Weight YTD PY") is None)
check("… et aucun repli n'a eu a etre annonce",
      not any("repli sur la substitution" in l for l in logs))
rmtree(c)

# ===================================================================== 4
print("4. l'UI : case par branche, case par variation")
from qtpy.QtWidgets import QApplication                     # noqa: E402
from core.project import Project                            # noqa: E402
import tabs.tab_config as tc                                # noqa: E402

app = QApplication.instance() or QApplication([])
c = projet("ui")
onglet = tc.ConfigTab()
onglet.set_project(Project(c / (PROJ + ".pbip")))
onglet._config["branches"]["YTD"] = {}
onglet._load_global()
check("« Envelopper » coche par defaut", onglet.g_branch_envelopper.isChecked())
check("le patron est vide, et dit ce qu'il tire du DAX de YTD",
      onglet.g_branch_wrap.text() == "" and WRAP in onglet.g_branch_wrap.placeholderText())
onglet._commit_global()
check("rien n'est ecrit pour le defaut", onglet._config["branches"]["YTD"] == {})

onglet.g_branch_envelopper.setChecked(False)
check("decocher grise le patron", not onglet.g_branch_wrap.isEnabled())
onglet._commit_global()
check("… et ecrit « substitution »", onglet._config["branches"]["YTD"].get("substitution") is True)
onglet._load_global()
check("… relu decoche", not onglet.g_branch_envelopper.isChecked())
onglet.g_branch_envelopper.setChecked(True)
onglet.g_branch_wrap.setText("TOTALYTD({variationRef}, {date})")
onglet._commit_global()
check("recocher retire la cle, un patron ecrit est garde",
      onglet._config["branches"]["YTD"] == {"wrap": "TOTALYTD({variationRef}, {date})"})

onglet._populate_list(select="PY")
check("« envelopper en branche » coche par defaut", onglet.chk_wrap.isChecked())
onglet.chk_wrap.setChecked(False)
onglet._commit_form()
check("decocher ecrit wrapInBranch: false",
      onglet._config["variations"]["PY"].get("wrapInBranch") is False)
onglet.chk_wrap.setChecked(True)
onglet._commit_form()
check("recocher retire la cle (on n'ecrit que le non-defaut)",
      "wrapInBranch" not in onglet._config["variations"]["PY"])
onglet._config["variations"]["PY"]["wrapInBranch"] = True     # ancien format
onglet._populate_list(select="PY")
check("l'ancien « wrapInBranch: true » s'affiche coche", onglet.chk_wrap.isChecked())
check("le jeton {variationRef} est connu du lint", "variationRef" in tc.KNOWN_PLACEHOLDERS)

onglet.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
