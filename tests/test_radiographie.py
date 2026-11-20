# -*- coding: utf-8 -*-
"""Onglet « Radiographie 🩻 » : les KPI, les variations et les visuels d'un
rapport qu'on n'a pas fait.

    py tests\\test_radiographie.py

Vérifie :
  1. la lecture du DAX : commentaires et chaînes ignorés, crochets gardés ;
  2. les familles par le nom : tige commune, casse, premier mot générique ;
  3. le projet de démonstration, PRIVÉ de ce que PBIdouille y met
     (annotations MeasureVariation, measures_config.json) : les six KPI et
     leurs variations se retrouvent quand même, par le DAX seul ;
  4. les visuels : leurs champs lus par la liaison et non par un queryRef
     périmé, une mesure « affichée » via un paramètre de champ et « choisie »
     par un segment, ce qui filtre chaque visuel (filtres du volet, de page,
     segments, interactions coupées), à quoi mène une mesure, les colonnes
     utilisées et où, un champ absent du modèle ;
  5. l'onglet : ses trois vues, filtre, fiches, navigation par les liens ;
  6. rien n'est écrit dans le projet.

Travaille sur une COPIE du projet de démonstration.
"""

from __future__ import annotations

import hashlib
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
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO)
reglages_jetables("radiographie")

import radiographie as rg                                        # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def empreinte(dossier: Path) -> str:
    h = hashlib.sha1()
    for f in sorted(dossier.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(dossier)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
print("1. la lecture du DAX")
code = rg.code_dax('CALCULATE([A], "[B]") // [C]\n-- [D]\n/* [E] */ + [Taux -- net]')
check("une mesure dans une chaîne ou un commentaire ne compte pas",
      "[a]" in code.lower() and not any(x in code for x in ("[B]", "[C]", "[D]", "[E]")))
check("un nom de mesure qui contient -- survit", "[Taux -- net]" in code)
check("patron : le KPI devient « … », en mot entier",
      rg.patron("Weight YTD 7d avg", "Weight YTD") == "… 7d avg"
      and rg.patron("Weighted", "Weight") == "Weighted")
check("patron : sans tenir compte de la casse",
      rg.patron("lean mass avg", "Lean Mass", "…") == "… avg")

# ---------------------------------------------------------------------------
print("2. les familles par le nom")
f = rg._familles_nom(["Lean Mass (Current)", "lean mass avg", "Lean Mass Δ (1M)",
                      "Lean Mass Δ (12M)", "Recomp rate", "Recomp (1D)",
                      "Total Sales", "Total Cost", "Seule"])
check("« Lean Mass » regroupe les quatre, Δ compris", sorted(f.get("Lean Mass", [])) ==
      sorted(["Lean Mass (Current)", "lean mass avg", "Lean Mass Δ (1M)", "Lean Mass Δ (12M)"]))
check("la casse la plus fréquente l'emporte", "Lean Mass" in f and "lean mass" not in f)
check("« Recomp » : deux mesures suffisent", sorted(f.get("Recomp", [])) ==
      ["Recomp (1D)", "Recomp rate"])
check("« Total » seul ne fait pas une famille",
      not any("Total Sales" in m for m in f.values()))
check("une mesure sans parente reste seule", not any("Seule" in m for m in f.values()))

# ---------------------------------------------------------------------------
print("3. le projet de démonstration, sans ce que PBIdouille y met")
TMP = Path(tempfile.mkdtemp(prefix="pbid_radio_"))
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), TMP / (PROJ + s),
                    ignore=shutil.ignore_patterns(".pbi", "cache.abf"))
shutil.copy2(PBI / (PROJ + ".pbip"), TMP / (PROJ + ".pbip"))
retirees = 0
for t in (TMP / (PROJ + ".SemanticModel") / "definition" / "tables").glob("*.tmdl"):
    texte = t.read_text(encoding="utf-8")
    net, n = re.subn(r"^\t\tannotation MeasureVariation = .*\n", "", texte, flags=re.M)
    if n:
        t.write_text(net, encoding="utf-8")
        retirees += n
check("la copie n'a plus d'annotation PBIdouille, ni de config",
      retirees > 50 and not (TMP / "measures_config.json").exists())

avant = empreinte(TMP)
r = rg.analyser(TMP / (PROJ + ".pbip"))
kpis = {k["kpi"]: k for k in r["kpis"]}
attendus = {"Weight", "Body Fat %", "Average Steps", "Total Steps", "Average Sleep Duration"}
check("les cinq KPI du rapport sont des familles DAX",
      attendus <= {k for k, f in kpis.items() if f["genre"] == rg.DAX})
w = {x["nom"]: x for x in kpis["Weight"]["membres"]}
check("Weight YTD 7d avg descend de Weight YTD, patron « … YTD 7d avg »",
      w["Weight YTD 7d avg"]["base"] == "Weight YTD"
      and w["Weight YTD 7d avg"]["patron"] == "… YTD 7d avg"
      and w["Weight YTD 7d avg"]["par"] == rg.DAX)
check("chaque patron courant est trouvé sur au moins cinq KPI",
      all(n >= 5 for p, n in r["patrons"]
          if p in ("… 7d avg", "… YTD", "… PY")))
check("les KPI sont triés par nombre de visuels",
      [k["visuels"] for k in r["kpis"]] == sorted((k["visuels"] for k in r["kpis"]),
                                                   reverse=True))
check("Weight YTD utilise [Weight], et [Weight] le sait",
      "Weight" in r["uses"]["Weight YTD"] and "Weight YTD" in r["used_by"]["Weight"])
check("le DAX est gardé tel qu'écrit, sur ses lignes",
      "\n" in r["mesures"]["Weight 7d avg"]["dax"])

# ---------------------------------------------------------------------------
print("4. paramètres de champ et visuels")
fp = r["parametres"].get("P_Indicateurs")
check("P_Indicateurs : sa colonne principale et les mesures qu'il propose",
      fp and fp["colonne"] == "P_Indicateurs" and "Weight" in fp["mesures"])
check("Weight se sait proposée par P_Indicateurs", "P_Indicateurs" in r["proposee_par"]["Weight"])
check("une agrégation implicite est lue",
      rg._champ_projection({"Aggregation": {"Expression": {"Column": {
          "Expression": {"SourceRef": {"Entity": "steps"}}, "Property": "value"}},
          "Function": 0}}, set(), {("steps", "value"): {}}, {})["agregat"] == "Somme")
check("un groupe de valeurs (GroupRef) est lu comme une colonne",
      rg.champ_de({"GroupRef": {"Expression": {"SourceRef": {"Entity": "dim_Date"}},
                                "Property": "1 month"}}) == ("dim_Date", "1 month", "Column"))
check("un filtre se lit : valeurs, exclusion, comparaisons",
      rg.decrire_requete({"Where": [{"Condition": {"In": {"Values": [
          [{"Literal": {"Value": "'YoY %'"}}], [{"Literal": {"Value": "2024L"}}]]}}}]})
      == "= YoY %, 2024"
      and rg.decrire_requete({"Where": [{"Condition": {"Not": {"Expression": {"In": {
          "Values": [[{"Literal": {"Value": "'x'"}}]]}}}}}]}) == "≠ x"
      and rg.decrire_requete({"Where": [{"Condition": {"And": {
          "Left": {"Comparison": {"ComparisonKind": 2, "Right": {"Literal": {
              "Value": "datetime'2024-01-01T00:00:00'"}}}},
          "Right": {"Comparison": {"ComparisonKind": 3, "Right": {"Literal": {
              "Value": "datetime'2025-01-01T00:00:00'"}}}}}}}]})
      == "≥ 2024-01-01 et < 2025-01-01")
check("Weight YTD 7d avg mène à Weight, qui lit 'Weight LOCF'[weight]",
      r["bases"]["Weight YTD 7d avg"] == ["Weight"]
      and ("Weight LOCF", "weight") in r["colonnes"]["Weight"]
      and r["bases"]["Weight"] == [])


def champ_col(table, prop, genre="Column"):
    return {genre: {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def lire(vj):
    return json.loads(vj.read_text(encoding="utf-8"))


def ecrire(vj, d):
    vj.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def projections_de(d):
    qs = ((d.get("visual") or {}).get("query") or {}).get("queryState") or {}
    return [p for b in qs.values() for p in b.get("projections") or []]


pages_dir = TMP / (PROJ + ".Report") / "definition" / "pages"
vjs = sorted(pages_dir.glob("*/visuals/*/visual.json"))

# 1. un visuel passe par le paramètre de champ, en GARDANT son ancien queryRef :
#    c'est le field qui compte, comme après un renommage dans Desktop
def mesures_projetees(vj):
    # des mesures qui EXISTENT : le visuel au champ cassé doit rester cassé
    return [p for p in projections_de(lire(vj)) if "Measure" in p["field"]
            and p["field"]["Measure"]["Property"] in r["mesures"]]


def a_un_segment(vj):
    return any(lire(x).get("visual", {}).get("visualType") == "slicer"
               for x in vj.parent.parent.glob("*/visual.json"))


cible = next(v for v in vjs if mesures_projetees(v) and a_un_segment(v))
d = lire(cible)
p0 = next(p for p in projections_de(d) if "Measure" in p["field"]
          and p["field"]["Measure"]["Property"] in r["mesures"])
ancien_ref = p0.get("queryRef")
p0["field"] = champ_col("P_Indicateurs", "P_Indicateurs")
p0["queryRef"] = ancien_ref                 # l'ancien queryRef reste, comme dans Desktop
ecrire(cible, d)

# 2. un segment sur le paramètre, avec une sélection
seg = next(v for v in vjs if lire(v).get("visual", {}).get("visualType") == "slicer"
           and v.parent.parent == cible.parent.parent)
d = lire(seg)
projections_de(d)[0]["field"] = champ_col("P_Indicateurs", "P_Indicateurs")
d["visual"].setdefault("objects", {})["general"] = [{"properties": {"filter": {"filter": {
    "Version": 2, "From": [{"Name": "p", "Entity": "P_Indicateurs", "Type": 0}],
    "Where": [{"Condition": {"In": {"Expressions": [], "Values": [
        [{"Literal": {"Value": "'Total Steps'"}}]]}}}]}}}}]
ecrire(seg, d)

# 3. sur cette page : un filtre de page, et l'interaction du segment coupée
#    vers UN autre visuel
page_json = cible.parent.parent.parent / "page.json"
pj = lire(page_json)
autre = next(v for v in sorted((cible.parent.parent).glob("*/visual.json"))
             if v not in (cible, seg) and projections_de(lire(v))
             and lire(v)["visual"].get("visualType") != "slicer")
pj["filterConfig"] = {"filters": [{"name": "f1", "field": champ_col("dim_Date", "Date"),
                                   "type": "Advanced", "filter": {"Version": 2, "Where": [
    {"Condition": {"Comparison": {"ComparisonKind": 2, "Right": {"Literal": {
        "Value": "datetime'2024-01-01T00:00:00'"}}}}}]}}]}
pj["visualInteractions"] = [{"source": lire(seg)["name"], "target": lire(autre)["name"],
                             "type": "NoFilter"}]
ecrire(page_json, pj)

avant = empreinte(TMP)
r = rg.analyser(TMP / (PROJ + ".pbip"))
vis = {(v["page_id"], v["id"]): v for v in r["visuels"]}


def v_de(vj):
    return vis[(vj.parent.parent.parent.name, lire(vj)["name"])]


via = [x for _v, x in r["affichee"]["Total Steps"]]
check("Total Steps est affichée VIA P_Indicateurs, malgré l'ancien queryRef",
      "P_Indicateurs" in via)
check("… et choisie par le segment, sans compter comme affichée par lui",
      any(v["segment"] for v, _ in r["choisie"]["Total Steps"])
      and not any(v["segment"] for v, _ in r["affichee"]["Total Steps"]))
check("la sélection du segment est lue", v_de(seg)["selection"] == "= Total Steps")
check("le segment filtre les visuels de sa page…",
      any(s is v_de(seg) for s in v_de(cible)["segments"]))
check("… sauf celui dont l'interaction est coupée",
      not any(s is v_de(seg) for s in v_de(autre)["segments"]))
filtres_page = next(p for p in r["pages"] if p["id"] == cible.parent.parent.parent.name)["filtres"]
check("le filtre de page est lu",
      [(f["nom"], f["texte"], f["actif"]) for f in filtres_page]
      == [("Date", "avancé : ≥ 2024-01-01", True)])
check("un filtre de visuel est lu (Calcul = YoY %)",
      any(f["actif"] and f["texte"] == "= YoY %" for v in r["visuels"] for f in v["filtres"]))
casses = [(v["libelle"], c["ref"]) for v in r["visuels"] for c in v["champs"]
          if c["genre"] == "colonne" and not c["connue"]]
check("le champ absent du modèle (weight obs.lean mass avg) est signalé, et lui seul",
      [ref for _l, ref in casses] == ["weight obs.lean mass avg"])
check("un visuel sans titre est nommé par son premier champ",
      any(v["libelle"].startswith("Segment · ") for v in r["visuels"]))

cols = {(c["table"], c["nom"]): c for c in r["colonnes_utilisees"]}
date = cols.get(("dim_Date", "Date"))
check("Par colonne : 'dim_Date'[Date] sert au filtre de page, avec sa valeur",
      date and any(u["genre"] == "filtre de page" and "2024-01-01" in u["texte"]
                   for u in date["usages"]))
check("… et aux mesures qui la lisent",
      date and any(u["genre"] == "mesure" for u in date["usages"]))
p_ind = cols.get(("P_Indicateurs", "P_Indicateurs"))
check("la colonne du segment porte sa sélection",
      p_ind and any(u["genre"] == "segment" and u["texte"] == "= Total Steps"
                    for u in p_ind["usages"]))
check("la casse du DAX est ramenée à celle du modèle",
      not any(t == "Weight LOCF" and c == "date" for t, c in cols))
check("la colonne absente du modèle est signalée",
      cols.get(("weight obs", "lean mass avg")) is None
      or not cols[("weight obs", "lean mass avg")]["connue"])

# ---------------------------------------------------------------------------
print("5. l'onglet")
from qtpy.QtWidgets import QApplication                          # noqa: E402
from tabs.tab_radiographie import RadiographieTab                # noqa: E402
from core.project import Project                                 # noqa: E402

qa = QApplication.instance() or QApplication([])
tab = RadiographieTab()
tab.set_project(Project(TMP / (PROJ + ".pbip")))
check("l'analyse attend que l'onglet soit visible", not tab.res)
tab.resize(1200, 700)
tab.show()
qa.processEvents()
a = tab.arbre_kpi
tops = [a.topLevelItem(i).text(0) for i in range(a.topLevelItemCount())]
check("vue Par KPI : les familles, puis briques, jamais affichées et patrons",
      "Weight" in tops and any(t.startswith("Briques") for t in tops)
      and any(t.startswith("Variations repérées") for t in tops))
tab.aller_a("mesure", "Weight YTD")
cur = a.currentItem()
check("aller à une mesure la sélectionne dans sa famille",
      cur is not None and cur.text(0) == "Weight YTD" and cur.parent().text(0) == "Weight")
fiche = tab.fiche.toPlainText()
check("sa fiche : variation de Weight, ce qu'elle utilise, son DAX",
      "Variation de Weight" in fiche and "Utilise" in fiche and "DATESYTD" in fiche)
n_liens = len(tab._liens)
from qtpy.QtCore import QUrl                                      # noqa: E402
i_weight = next(i for i, l in enumerate(tab._liens) if l == ("mesure", "Weight"))
tab._lien(QUrl(f"#{i_weight}"))
check("un lien de la fiche mène à la mesure", a.currentItem().text(0) == "Weight"
      and n_liens > 0)
tab.ed_filtre.setText("sleep duration ytd 7d")
visibles = []


def parcourir(it):
    if not it.isHidden():
        visibles.append(it.text(0))
    for i in range(it.childCount()):
        parcourir(it.child(i))


for i in range(a.topLevelItemCount()):
    parcourir(a.topLevelItem(i))
check("le filtre ne garde que ce qui correspond, et ses parents",
      "Average Sleep Duration YTD 7d avg" in visibles and "Weight" not in visibles)
tab.ed_filtre.clear()
p = tab.arbre_pages
check("vue Par page : une ligne par page", p.topLevelItemCount() == len(r["pages"]))
ac = tab.arbre_cols
tables_vues = [ac.topLevelItem(i).text(0) for i in range(ac.topLevelItemCount())]
check("vue Par colonne : une ligne par table utilisée",
      tables_vues == sorted({c["table"] for c in r["colonnes_utilisees"]}, key=str.lower))
dim = ac.topLevelItem(tables_vues.index("dim_Date"))
ligne_date = next(dim.child(i) for i in range(dim.childCount()) if dim.child(i).text(0) == "Date")
ac.setCurrentItem(ligne_date)
check("la fiche d'une colonne liste ses segments, filtres et mesures",
      all(x in tab.fiche.toPlainText() for x in ("Filtres de page", "Mesures qui la lisent")))
page_lien = next((i for i, l in enumerate(tab._liens) if l[0] == "page"), None)
from qtpy.QtCore import QUrl as _QUrl                              # noqa: E402
if page_lien is not None:
    tab._lien(_QUrl(f"#{page_lien}"))
check("un lien vers une page ouvre sa fiche", "KPI affichés" in tab.fiche.toPlainText())
visuel = next(v for v in r["visuels"] if any(c["genre"] == "parametre" for c in v["champs"]))
tab.aller_a("visuel", (visuel["page_id"], visuel["id"]))
check("la fiche d'un visuel nomme son paramètre de champ",
      "paramètre de champ" in tab.fiche.toPlainText() and tab.vues.currentWidget() is p)
tab.close()

# ---------------------------------------------------------------------------
print("6. lecture seule")
check("rien n'a été écrit dans le projet", empreinte(TMP) == avant)

rmtree(TMP)
print("\nTOUT OK" if _ok else "\nDES ECHECS")
sys.exit(0 if _ok else 1)
