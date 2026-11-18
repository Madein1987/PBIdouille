# -*- coding: utf-8 -*-
"""Les jetons : ce qu'ils valent, et l'explorateur de Mesures → Variations.

    py tests\\test_jetons.py

Vérifie :
  1. apercu_jetons rend, pour un KPI et pour une cible, en Réel et en branche,
     ce que la génération écrirait, sans toucher au config ni au modèle ;
  2. les attributs proposés : les déclarés, plus direction ; une cellule vide
     n'a pas de valeur ; seules les vraies cibles sont listées ;
  3. les filtres par KPI passent par un attribut ; un ancien kpiTables reste lu ;
  4. un attribut sert de nom de variable DAX, et une cellule peut porter du
     DAX, jetons compris ;
  5. renommer l'id d'une variation ne laisse pas deux mesures du même nom ;
  6. l'explorateur : KPI et cibles au choix, valeurs, où chaque jeton se
     règle, insertion dans le DAX ;
  7. les attributs modifiés dans la fenêtre, synchronisés avec ⚙ Réglages ;
  8. l'écriture de l'Excel : tableau agrandi, fichier ouvert dans Excel.

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
    "filtres": {"Weight": "ALLSELECTED('Weight LOCF')",
                "Total Steps": "ALLSELECTED('steps'), ALLSELECTED('dim_Date')"},
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
                                          "calcul": "calcul", "filtres": "filtres"}}
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

print("2. les attributs proposés")
attr = {a["jeton"]: a for a in ap["attributs"]}
check("les colonnes déclarées sont marquées", attr["<<unite>>"]["declare"])
check("direction est proposée, même non déclarée",
      "<<direction>>" in attr and not attr["<<direction>>"]["declare"])
check("les autres colonnes ne sont plus listées",
      not {"<<couleur>>", "<<mesure>>", "<<indicateur>>", "<<libelle_indicateur>>",
           "<<tables>>"} & set(attr))
check("… avec ce qu'elles vaudraient", v("Weight", "", "<<direction>>") == "1")
check("une valeur par KPI", v("Weight", "", "<<unite>>") == "kg"
      and v("Total Steps", "", "<<unite>>") == "pas")
check("une cible lit la ligne de son KPI", v("Weight cible", "", "<<unite>>") == "kg")
check("cellule vide : pas de valeur", v("Body Fat %", "", "<<unite>>") is None)

sans_cible = copy.deepcopy(conf)
del sans_cible["kpiMeasureFolders"]
check("rapport sans cible : aucune cible inventée",
      not any(b["cible"] for b in gm.apercu_jetons(MODELE, sans_cible)["bases"]))
inactive = copy.deepcopy(conf)
del inactive["variations"]["YTD"]["appliesToCibles"]
ex1 = {(b["nom"], b["branche"]) for b in gm.apercu_jetons(MODELE, inactive)["bases"]}
check("branche non activée pour les cibles : pas de ligne",
      ("Weight cible", "") in ex1 and ("Weight cible", "YTD") not in ex1)
wb2 = openpyxl.load_workbook(copie / "TD_Indicateurs.xlsx")
wb2.worksheets[0].cell(1, entetes.index("direction") + 1, "sens")
wb2.save(copie / "sans_direction.xlsx")
wb2.close()
sans_dir = copy.deepcopy(conf)
sans_dir["indicateursXlsx"] = {"path": "sans_direction.xlsx"}
a_dir = {a["jeton"]: a for a in gm.apercu_jetons(MODELE, sans_dir)["attributs"]}
check("direction absente de l'Excel : proposée à créer", a_dir["<<direction>>"]["absente"])

print("3. les filtres par KPI")
check("sans kpiTables, pas de jetons de portée", ap["portee"] == [])
cp = copy.deepcopy(conf)
cp["variations"]["Part"] = {"namePattern": "{base} part", "formatString": "0.0 %",
                            "dax": "DIVIDE({baseRef}, CALCULATE({baseRef}, <<filtres>>))"}
part = {n["name"]: n for n in gm.generate(MODELE, cp, dry_run=True, remove_orphans=False,
                                          log=lambda *a: None)["arbre"]}
check("<<filtres>> donne ses filtres à chaque KPI",
      "ALLSELECTED('steps'), ALLSELECTED('dim_Date')" in part["Total Steps part"]["dax"]
      and "ALLSELECTED('Weight LOCF')" in part["Weight part"]["dax"])
check("KPI sans filtres : pas de mesure", "Body Fat % part" not in part)
ancien = copy.deepcopy(conf)
ancien["kpiTables"] = {"column": "tables"}
ap2 = gm.apercu_jetons(MODELE, ancien, "PY")
p2 = {(b["nom"], b["branche"]): b["valeurs"] for b in ap2["bases"]}
check("un ancien kpiTables reste lu : <<allTables>>",
      p2[("Total Steps", "")]["<<allTables>>"] == "ALL('steps'), ALL('dim_Date')")
check("… et <<each …>>", p2[("Total Steps", "")]["<<each ALLSELECTED({table})>>"]
      == "ALLSELECTED('steps'), ALLSELECTED('dim_Date')")

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
from tabs.explorateur_jetons import (A_ACTION, A_COLONNE, A_INSERER,  # noqa: E402
                                     A_JETON, A_VALEUR, COL_JETON, COL_OU, COL_VALEUR)
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
check("la note explique la cible", "est une cible" in ex.lbl_note.text())
check("{date} dit où il se règle", "dateColumn" in L["{date}"].text(COL_OU))
check("{base} d'une cible renvoie aux Mesures cibles", "Mesures cibles" in L["{base}"].text(COL_OU))
check("{branch} renvoie aux Branches", "Branches" in L["{branch}"].text(COL_OU))
ct.ed_dax.setPlainText("")
ex._on_double_clic(L["{baseRef}"])
check("double-clic : le jeton part dans le DAX", ct.ed_dax.toPlainText() == "{baseRef}")
check("le bouton ouvre une fenêtre non modale",
      not ct.fenetre_jetons.isModal() and ct.btn_jetons.text().startswith("Jetons disponibles"))
check("la portée n'a plus de réglage", not hasattr(ct, "g_kpitables_col"))
ct._config["kpiTables"] = {"column": "tables"}
ct._load_global()
ct._commit_global()
check("… mais un kpiTables existant survit à un passage dans les Réglages",
      ct._config.get("kpiTables") == {"column": "tables"})
ct._config.pop("kpiTables", None)
ct._set_dirty(False)

print("7. les attributs se modifient dans la fenêtre")
import xlsx_lecture as xl                                        # noqa: E402
XLSX = copie / "TD_Indicateurs.xlsx"


def tourne():
    for _ in range(4):
        app.processEvents()


def rangees():
    t = ex.table
    return {t.item(r, A_JETON).text().strip("<>"): r for r in range(t.rowCount())}


def cellule(colonne, kpi):
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.worksheets[0]
    h = [c.value for c in ws[1]]
    i, k = h.index(colonne) + 1, h.index("mesure") + 1
    out = next((ws.cell(r, i).value for r in range(2, ws.max_row + 1)
                if ws.cell(r, k).value == kpi), None)
    wb.close()
    return out


def disque():
    return json.loads((copie / "measures_config.json").read_text(encoding="utf-8"))


def jetons_config():
    return ct._config["hardcodedAttributes"]["tokens"]


ct._rafraichir_jetons()
ex.choisir("Weight", "")
R = rangees()
check("une seule section : déclarés et direction",
      "unite" in R and "direction" in R and "couleur" not in R)
check("chaque jeton s'affiche comme il s'écrit dans le DAX",
      ex.table.item(R["unite"], A_JETON).text() == "<<unite>>"
      and ex.table.item(R["direction"], A_JETON).text() == "<<direction>>")
ex.table.item(R["unite"], A_JETON).setText("unite")
tourne()
check("retaper le même nom sans chevrons : rien ne change, ils reviennent",
      ex.table.item(rangees()["unite"], A_JETON).text() == "<<unite>>"
      and "unite" in jetons_config())
check("l'en-tête dit de quel KPI est la valeur",
      ex.table.horizontalHeaderItem(A_VALEUR).text() == "Valeur pour Weight")
check("la case montre la cellule BRUTE, jetons compris",
      ex.table.item(R["calcul"], A_VALEUR).text() == AJOUTS["calcul"]["Weight"])
check("direction non déclarée : grisée, avec un ＋",
      ex.table.cellWidget(R["direction"], A_ACTION).text() == "＋"
      and not ex.table.cellWidget(R["direction"], A_COLONNE).isEnabled())

ex.table.item(rangees()["unite"], A_VALEUR).setText("lbs")
tourne()
check("écrire dans une case écrit l'Excel", cellule("unite", "Weight") == "lbs")
check("… et la fenêtre suit", ex.valeur("<<unite>>") == "lbs")
check("… avec une sauvegarde",
      list((copie / "_backupsPBIdouille" / "_indicateurs_backups").glob("*/manifeste.json")))
ex.choisir("Weight cible", "")
ex.table.item(rangees()["unite"], A_VALEUR).setText("kg")
tourne()
check("sur une cible, c'est la ligne de son KPI qui change", cellule("unite", "Weight") == "kg")
ex.choisir("Weight", "")
ex.table.item(rangees()["unite"], A_VALEUR).setText("")
tourne()
check("vider une case vide la cellule", cellule("unite", "Weight") is None)
check("… et le jeton n'a plus de valeur pour ce KPI", ex.valeur("<<unite>>") is None)
ex.table.item(rangees()["unite"], A_VALEUR).setText("kg")
tourne()
check("… puis elle se remplit de nouveau", cellule("unite", "Weight") == "kg")

ex.ed_jeton.setText("<<objectif>>")
ex.ed_valeur.setText("180")
ex.btn_ajouter.click()
tourne()
check("Ajouter : colonne absente, créée dans l'Excel", cellule("objectif", "Weight") == 180)
check("… jeton déclaré et config enregistré", jetons_config()["objectif"] == "objectif"
      and disque()["hardcodedAttributes"]["tokens"]["objectif"] == "objectif" and not ct._dirty)
check("… ligne de saisie vidée", ex.ed_jeton.text() == "" and ex.ed_valeur.text() == "")
ct._load_global()
lignes_r = {ct.g_hc_table.item(r, 0).text() for r in range(ct.g_hc_table.rowCount())}
check("… et ⚙ Réglages voit le même jeton, avec ses chevrons", "<<objectif>>" in lignes_r)
ct._commit_global()
check("… sans que les chevrons entrent dans le config",
      "objectif" in jetons_config() and not any("<" in k for k in jetons_config()))
ct._set_dirty(False)
c7 = copy.deepcopy(ct._config)
c7["variations"]["Reste"] = {"namePattern": "{base} reste", "formatString": "inherit",
                             "dax": "{baseRef} - <<objectif>>"}
n7 = {n["name"]: n for n in gm.generate(MODELE, c7, dry_run=True, remove_orphans=False,
                                        log=lambda *a: None)["arbre"]}
check("la génération s'en sert : [Weight] - 180", n7["Weight reste"]["dax"] == "[Weight] - 180")

ex.table.cellWidget(rangees()["direction"], A_ACTION).click()
tourne()
check("＋ déclare direction, sans autre fenêtre", jetons_config().get("direction") == "direction")
ex.table.item(rangees()["objectif"], A_JETON).setText("<<cible_poids>>")
tourne()
check("renommer un jeton dans sa case",
      "cible_poids" in jetons_config() and "objectif" not in jetons_config()
      and ex.table.item(rangees()["cible_poids"], A_JETON).text() == "<<cible_poids>>")
ex.table.item(rangees()["cible_poids"], A_JETON).setText("unite")
tourne()
check("un nom déjà pris est refusé, la case revient",
      "cible_poids" in rangees() and "déjà pris" in ex.lbl_aide.text())
c = ex.table.cellWidget(rangees()["cible_poids"], A_COLONNE)
c.setCurrentText("unite")
c.lineEdit().editingFinished.emit()
tourne()
check("changer la colonne dans sa case", jetons_config()["cible_poids"] == "unite")
ct.ed_dax.setPlainText("")
ex.table.cellWidget(rangees()["cible_poids"], A_INSERER).click()
tourne()
check("Insérer met le jeton dans le DAX", ct.ed_dax.toPlainText() == "<<cible_poids>>")
ct._set_dirty(False)
ex.table.cellWidget(rangees()["cible_poids"], A_ACTION).click()
tourne()
check("✕ retire le jeton, pas la colonne",
      "cible_poids" not in jetons_config() and cellule("objectif", "Weight") == 180)
ct._set_dirty(True)
ex.ed_jeton.setText("seuil")
ex.btn_ajouter.click()
tourne()
check("config déjà modifié : rien n'est enregistré à ta place",
      ct._dirty and "seuil" in jetons_config()
      and "seuil" not in disque()["hardcodedAttributes"]["tokens"])
ct._set_dirty(False)

print("8. l'écriture de l'Excel")
neuf = copie / "tableau.xlsx"
shutil.copy2(PBI / "TD_Indicateurs.xlsx", neuf)
wb3 = openpyxl.load_workbook(neuf)
tableau = [t.ref for t in wb3.worksheets[0].tables.values()]
wb3.close()
xl.ajouter_colonne(neuf, "mesure", "objectif", {"Weight": 180})
wb3 = openpyxl.load_workbook(neuf)
if tableau:
    t3 = next(iter(wb3.worksheets[0].tables.values()))
    check("le tableau Excel s'agrandit", t3.ref == "A1:F6"
          and [c.name for c in t3.tableColumns][-1] == "objectif")
wb3.close()
avant_xlsx = XLSX.read_bytes()
reel_replace = xl.os.replace


def verrou(*a):
    raise PermissionError("verrouillé")


xl.os.replace = verrou
ex.table.item(rangees()["unite"], A_VALEUR).setText("stone")
tourne()
xl.os.replace = reel_replace
check("Excel ouvert : le fichier est intact, et la fenêtre le dit",
      XLSX.read_bytes() == avant_xlsx and "ouvert dans Excel" in ex.lbl_aide.text())
check("… la case revient à la vraie valeur",
      ex.table.item(rangees()["unite"], A_VALEUR).text() == "kg")
check("… sans temporaire ni sauvegarde vide", not list(copie.glob("~pbidouille_*")))
ct._set_dirty(False)
ct.deleteLater()

shutil.rmtree(copie, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
