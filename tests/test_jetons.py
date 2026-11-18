# -*- coding: utf-8 -*-
"""Les jetons : ce qu'ils valent, et l'explorateur de Mesures → Variations.

    py tests\\test_jetons.py

Vérifie :
  1. apercu_jetons rend, pour un KPI et pour une cible, en Réel et en branche,
     ce que la génération écrirait, sans toucher au config ni au modèle ;
  2. toutes les colonnes de TD_Indicateurs sont des <<attributs>> possibles,
     déclarés ou non ; une cellule vide n'a pas de valeur ;
  3. les jetons de portée suivent les tables du KPI ;
  4. un attribut sert de nom de variable DAX, et une cellule peut porter du
     DAX, jetons compris ;
  5. renommer l'id d'une variation ne laisse pas deux mesures du même nom ;
  6. l'explorateur : KPI et cibles au choix, valeurs, insertion dans le DAX.

Travaille sur une COPIE du projet de démonstration, magasin de réglages jetable.
"""

from __future__ import annotations

import copy
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
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import (exiger_projet, ajouter_cibles, reglages_jetables,   # noqa: E402
                      PROJET_DEMO)

exiger_projet(PBI, PROJET_DEMO, "measures_config.json", "TD_Indicateurs.xlsx")
reglages_jetables("jetons")

import openpyxl                                                  # noqa: E402
import generate_measures as gm                                   # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


copie = Path(tempfile.mkdtemp(prefix="pbid_jetons_"))
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
shutil.copy2(PBI / (PROJ + ".pbip"), copie / (PROJ + ".pbip"))
shutil.copy2(PBI / "TD_Indicateurs.xlsx", copie / "TD_Indicateurs.xlsx")
MODELE = copie / (PROJ + ".SemanticModel")
TMDL = MODELE / "definition" / "tables" / "_mesures.tmdl"

wb = openpyxl.load_workbook(copie / "TD_Indicateurs.xlsx")
ws = wb.worksheets[0]
entetes = [c.value for c in ws[1]]
AJOUTS = {
    "unite": {"Weight": "kg", "Total Steps": "pas"},
    "var_nom": {"Weight": "_poids", "Total Steps": "_pas"},
    "calcul": {"Weight": "AVERAGEX(VALUES({date}), {baseRef})",
               "Total Steps": "SUMX(VALUES({date}), {baseRef})"},
    "tables": {"Weight": "Weight LOCF", "Total Steps": "steps, dim_Date"},
}
for j, (col, vals) in enumerate(AJOUTS.items()):
    k = len(entetes) + 1 + j
    ws.cell(1, k, col)
    for r in range(2, ws.max_row + 1):
        v = vals.get(ws.cell(r, entetes.index("mesure") + 1).value)
        if v is not None:
            ws.cell(r, k, v)
wb.save(copie / "TD_Indicateurs.xlsx")
wb.close()

conf = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))
ajouter_cibles(MODELE, ["Weight"], variations=(), branches=())
conf["kpiMeasureFolders"] = [{"folder": "_cibles", "calcul": "Cible"}]
conf["variations"]["YTD"]["appliesToCibles"] = True      # la cible a son YTD
conf["hardcodedAttributes"] = {"tokens": {"unite": "unite", "var_nom": "var_nom",
                                          "calcul": "calcul"}}
conf["kpiTables"] = {"column": "tables"}
(copie / "measures_config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2),
                                            encoding="utf-8")

# ---------------------------------------------------------------------------
print("1. ce que valent les jetons")
fichiers = {p: p.stat().st_mtime_ns for p in MODELE.rglob("*") if p.is_file()}
avant = copy.deepcopy(conf)
ap = gm.apercu_jetons(MODELE, conf, "PY")
check("le config n'a pas bougé", conf == avant)
check("le modèle n'a pas été écrit",
      {p: p.stat().st_mtime_ns for p in MODELE.rglob("*") if p.is_file()} == fichiers)
par = {(b["nom"], b["branche"]): b for b in ap["bases"]}


def v(nom, branche, jeton):
    return par[(nom, branche)]["valeurs"].get(jeton)


check("KPI en Réel : {base} = {kpi} = Weight",
      v("Weight", "", "{base}") == "Weight" == v("Weight", "", "{kpi}"))
check("… {baseRef} = {kpiRef} = [Weight]",
      v("Weight", "", "{baseRef}") == "[Weight]" == v("Weight", "", "{kpiRef}"))
check("… {branch} est vide, {variation} est la variation ouverte",
      v("Weight", "", "{branch}") == "" and v("Weight", "", "{variation}") == "PY")
check("KPI en YTD : {base} suit la branche, {kpi} non",
      v("Weight", "YTD", "{base}") == "Weight YTD" and v("Weight", "YTD", "{kpi}") == "Weight")
check("… {kpiRef} = [Weight YTD], {branch} = YTD",
      v("Weight", "YTD", "{kpiRef}") == "[Weight YTD]" and v("Weight", "YTD", "{branch}") == "YTD")
check("la cible est une entrée à part, rattachée à son KPI",
      par[("Weight cible", "")]["cible"] and par[("Weight cible", "")]["kpi"] == "Weight")
check("cible en Réel : {base} = Weight cible, {kpi} = Weight",
      v("Weight cible", "", "{base}") == "Weight cible"
      and v("Weight cible", "", "{kpi}") == "Weight")
check("… {baseRef} = [Weight cible], {kpiRef} = [Weight]",
      v("Weight cible", "", "{baseRef}") == "[Weight cible]"
      and v("Weight cible", "", "{kpiRef}") == "[Weight]")
check("cible en YTD : {baseRef} = [Weight cible YTD], {kpiRef} = [Weight YTD]",
      v("Weight cible", "YTD", "{baseRef}") == "[Weight cible YTD]"
      and v("Weight cible", "YTD", "{kpiRef}") == "[Weight YTD]")
check("{date} est la colonne du config",
      v("Weight", "", "{date}") == conf["settings"]["dateColumn"])

print("2. n'importe quelle colonne de TD_Indicateurs")
attr = {a["jeton"]: a for a in ap["attributs"]}
check("les colonnes déclarées sont marquées", attr["<<unite>>"]["declare"])
check("les autres sont listées, non déclarées",
      "<<direction>>" in attr and not attr["<<direction>>"]["declare"])
check("… avec ce qu'elles vaudraient", v("Weight", "", "<<direction>>") == "1")
check("une valeur par KPI", v("Weight", "", "<<unite>>") == "kg"
      and v("Total Steps", "", "<<unite>>") == "pas")
check("une cible lit la ligne de son KPI", v("Weight cible", "", "<<unite>>") == "kg")
check("cellule vide : pas de valeur", v("Body Fat %", "", "<<unite>>") is None)

print("3. les tables du KPI")
check("<<tables>> : une table", v("Weight", "", "<<tables>>") == "'Weight LOCF'")
check("<<allTables>> : un ALL par table",
      v("Total Steps", "", "<<allTables>>") == "ALL('steps'), ALL('dim_Date')")
check("<<each …>> répète ta fonction",
      v("Total Steps", "", "<<each ALLSELECTED({table})>>")
      == "ALLSELECTED('steps'), ALLSELECTED('dim_Date')")
check("sans table déclarée : pas de valeur", v("Body Fat %", "", "<<tables>>") is None)

print("4. un attribut dans le DAX")
c2 = copy.deepcopy(conf)
c2["variations"]["Essai"] = {
    "namePattern": "{base} essai <<unite>>", "formatString": "inherit",
    "description": "En <<unite>>",
    "dax": ["VAR <<var_nom>> = <<calcul>>", "RETURN <<var_nom>>"]}
logs: list = []
st = gm.generate(MODELE, copy.deepcopy(c2), dry_run=True, remove_orphans=False, log=logs.append)
noeuds = {n["name"]: n for n in st["arbre"]}
n = noeuds.get("Weight essai kg")
check("le nom et la description prennent l'attribut",
      n is not None and n["description"] == "En kg")
check("il sert de nom de variable", n and n["dax"].startswith("VAR _poids = "))
check("la cellule porte du DAX, et SES jetons sont remplacés",
      n and "AVERAGEX(VALUES('dim_Date'[Date]), [Weight])" in n["dax"] and "{" not in n["dax"])
check("… chaque KPI a son DAX",
      "SUMX(VALUES('dim_Date'[Date]), [Total Steps])" in noeuds["Total Steps essai pas"]["dax"])
check("… une cible y a sa propre référence",
      "[Weight cible]" in noeuds["Weight cible essai kg"]["dax"]
      if "Weight cible essai kg" in noeuds else True)
check("KPI sans valeur : pas de mesure, et le journal le dit",
      not any(k.startswith("Body Fat % essai") for k in noeuds)
      and any("Body Fat %" in str(x) and "non générée" in str(x) for x in logs))

print("5. renommer l'id d'une variation")
gm.generate(MODELE, copy.deepcopy(conf), dry_run=False, remove_orphans=True, log=lambda *a: None)
c3 = copy.deepcopy(conf)
c3["variations"]["Annee"] = c3["variations"].pop("PY")
gm.generate(MODELE, c3, dry_run=False, remove_orphans=False, log=lambda *a: None)
texte = TMDL.read_text(encoding="utf-8")
check("une seule mesure de ce nom, même sans supprimer les orphelines",
      len(re.findall(r"^\tmeasure 'Weight PY'", texte, re.M)) == 1)
check("… et elle porte le nouvel id", "annotation MeasureVariation = Weight|Annee" in texte
      and "annotation MeasureVariation = Weight|PY" not in texte)
gm.generate(MODELE, copy.deepcopy(conf), dry_run=False, remove_orphans=True, log=lambda *a: None)

print("6. l'explorateur")
from qtpy.QtWidgets import QApplication                          # noqa: E402
app = QApplication.instance() or QApplication([])
import tabs.tab_config as tc                                     # noqa: E402
from tabs.explorateur_jetons import COL_JETON, COL_VALEUR        # noqa: E402
from core.project import Project                                 # noqa: E402

ct = tc.ConfigTab()
ct.set_project(Project(copie / (PROJ + ".pbip")))
ct._populate_list(select="PY")
ct._rafraichir_jetons()
ex = ct.explorateur_jetons
choix = [ex.cmb_base.itemData(i) for i in range(ex.cmb_base.count())]
check("les KPI sont au choix", "Weight" in choix and "Total Steps" in choix)
check("… et la cible, juste sous son KPI",
      choix.index("Weight cible") == choix.index("Weight") + 1)
check("les branches aussi", [ex.cmb_branche.itemData(i) for i in range(ex.cmb_branche.count())]
      == [""] + list(conf["branches"]))


def lignes():
    return {ex.arbre.topLevelItem(i).text(COL_JETON): ex.arbre.topLevelItem(i)
            for i in range(ex.arbre.topLevelItemCount())}


check("choisir la cible en YTD", ex.choisir("Weight cible", "YTD"))
L = lignes()
check("la liste suit : {base} et {kpi} diffèrent",
      L["{base}"].text(COL_VALEUR) == "Weight cible YTD"
      and L["{kpi}"].text(COL_VALEUR) == "Weight")
check("… {kpiRef} vise le KPI dans la branche", L["{kpiRef}"].text(COL_VALEUR) == "[Weight YTD]")
check("la note explique la cible", "Cible" in ex.lbl_note.text())
check("un attribut non déclaré le dit", "à déclarer" in L["<<direction>>"].text(2))
ex.choisir("Body Fat %", "")
check("une cellule vide le dit", "vide" in lignes()["<<unite>>"].text(COL_VALEUR))
ct.ed_dax.setPlainText("")
ex._on_double_clic(lignes()["{baseRef}"])
check("double-clic : le jeton part dans le DAX", ct.ed_dax.toPlainText() == "{baseRef}")
ct._set_dirty(False)
ct.deleteLater()

shutil.rmtree(copie, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
