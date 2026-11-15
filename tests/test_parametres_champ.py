# -*- coding: utf-8 -*-
"""Tables paramètre de champ : autant qu'on veut, chacune avec SES réglages.

    py tests\\test_parametres_champ.py

Autrefois trois familles figées (tableNames, tableNamesByKpi,
tableNamesKpiBase) aux options communes. Maintenant `fieldParameter.tables`
est une liste : chaque table dit ce qu'affichent ses rangées (le calcul ou le
KPI), ce qu'affiche sa rangée de base, si le KPI paraît sous son libellé, si
elle garde la base et les cibles, et quels KPI / variations / branches elle
écarte.

Vérifie :
  1. l'ancien format se relit en trois cas particuliers de la liste ;
  2. un config ancien format génère les mêmes tables qu'avant (forme des
     rangées de chaque famille) ;
  3. chaque réglage d'une table nouvelle forme fait ce qu'il dit ;
  4. une table vidée par ses filtres n'est pas écrite (« {} » serait un DAX
     invalide) ;
  5. la forme compacte écrite dans le config se relit à l'identique ;
  6. l'onglet Rapport cherche ses KPI dans les tables de la liste.

Travaille sur des COPIES du projet de démonstration.
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
# les projets Power BI vivent HORS de l'outil (cf. moteurs/chemins.py)
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, ajouter_cibles, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")

import generate_measures as gm                      # noqa: E402

PROJ = PROJET_DEMO
_ok = True
ROW_RE = re.compile(
    r'^\t{4}    \((LOOKUPVALUE\([^\n]*?\)|"(?:[^"]|"")*"), NAMEOF\(\[(.*?)\]\), '
    r'(\d+), "((?:[^"]|"")*)", "((?:[^"]|"")*)", "((?:[^"]|"")*)"\)', re.M)


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
    shutil.copytree(PBI / (PROJ + ".SemanticModel"), c / (PROJ + ".SemanticModel"))
    return c


def tables_dir(c):
    return c / (PROJ + ".SemanticModel") / "definition" / "tables"


def rangees(c, table):
    """[(affichage, mesure, ordre, KPI, calcul, branche)] d'une table."""
    p = tables_dir(c) / (table + ".tmdl")
    if not p.exists():
        return None
    return [(m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5), m.group(6))
            for m in ROW_RE.finditer(p.read_text(encoding="utf-8"))]


base_conf = json.loads((PBI / "measures_config.json").read_text(encoding="utf-8"))
REEL = base_conf["fieldParameter"].get("baseLabel") or "Base"

# ---------------------------------------------------------------------------
print("1. l'ancien format se relit en trois cas particuliers")
specs = gm.fp_table_specs(base_conf["fieldParameter"])
par_nom = {s["name"]: s for s in specs}
check("les 4 tables du config, dans l'ordre calcul, base=KPI, par KPI",
      [s["name"] for s in specs] == ["P_Indicateurs_parCalcul", "P_Indicateurs_parCalcul_2",
                                     "P_Indicateurs_parCalcul_baseKPI", "P_Indicateurs_parKPI"])
check("tableNames -> rangées « calcul », base « calcul »",
      par_nom["P_Indicateurs_parCalcul"]["rows"] == "calcul"
      and par_nom["P_Indicateurs_parCalcul"]["baseRow"] == "calcul")
check("tableNamesKpiBase -> base « kpi », par son libellé",
      par_nom["P_Indicateurs_parCalcul_baseKPI"]["baseRow"] == "kpi"
      and par_nom["P_Indicateurs_parCalcul_baseKPI"]["kpiLabel"])
check("tableNamesByKpi -> rangées « kpi »",
      par_nom["P_Indicateurs_parKPI"]["rows"] == "kpi")
check("includeBase commun recopié sur chaque table",
      all(s["includeBase"] == base_conf["fieldParameter"].get("includeBase", True)
          for s in specs))
check("sans aucune liste : le défaut historique P_Indicateurs",
      gm.fp_table_names({"enabled": True}) == ["P_Indicateurs"])
check("`tables` vide = aucune table (il fait foi dès qu'il existe)",
      gm.fp_table_names({"tables": [], "tableNames": ["X"]}) == [])
check("un nom en double n'est gardé qu'une fois",
      gm.fp_table_names({"tables": ["A", {"name": "a"}, "B"]}) == ["A", "B"])

# ---------------------------------------------------------------------------
print("2. ancien format : la forme de chaque famille est celle d'avant")
c = copie("pbid_fp_ancien")
gm.generate(c / (PROJ + ".SemanticModel"), base_conf, dry_run=False,
            remove_orphans=True, log=lambda *a: None)
calc = rangees(c, "P_Indicateurs_parCalcul")
basek = rangees(c, "P_Indicateurs_parCalcul_baseKPI")
park = rangees(c, "P_Indicateurs_parKPI")
check("les trois familles ont les mêmes mesures, dans le même ordre",
      calc and [r[1] for r in calc] == [r[1] for r in basek] == [r[1] for r in park])
check("par calcul : la base affiche « %s »" % REEL,
      all(r[0] == '"%s"' % REEL for r in calc if r[4] == REEL))
check("base = KPI : la base affiche le libellé (LOOKUPVALUE), les variations le calcul",
      all(r[0].startswith("LOOKUPVALUE") for r in basek if r[4] == REEL)
      and all(r[0] == '"%s"' % r[4] for r in basek if r[4] != REEL))
check("par KPI : toutes les rangées affichent le libellé, rangées au rang du KPI",
      all(r[0].startswith("LOOKUPVALUE") for r in park)
      and len({(r[3], r[2]) for r in park}) == len({r[3] for r in park}))
kpis = sorted({r[3] for r in calc})
branches = sorted({r[5] for r in calc})
calculs = sorted({r[4] for r in calc})
check(f"la démo a plusieurs KPI ({len(kpis)}) et branches ({', '.join(branches)})",
      len(kpis) > 2 and len(branches) > 1)

# ---------------------------------------------------------------------------
print("3. nouvelle forme : chaque table avec ses réglages")
c2 = copie("pbid_fp_nouveau")
ajouter_cibles(c2 / (PROJ + ".SemanticModel"), [kpis[0]])
conf = json.loads(json.dumps(base_conf))
conf["kpiMeasureFolders"] = [{"folder": "_cibles", "calcul": "Cible"}]
nb = "YTD" if "YTD" in branches else [b for b in branches if b != REEL][0]
une_var = next(v for v in conf["variations"]
               if conf["variations"][v].get("inFieldParameter") and v not in conf.get("branches", {}))
conf["fieldParameter"] = {
    "enabled": True, "baseLabel": REEL, "noBranchLabel": REEL,
    "kpiLabelLookup": base_conf["fieldParameter"].get("kpiLabelLookup"),
    "tables": [
        {"name": "P_test_complet"},
        {"name": "P_test_branche", "excludeBranches": [""]},
        {"name": "P_test_sans_base", "includeBase": False},
        {"name": "P_test_sans_cible", "includeTargets": False},
        {"name": "P_test_un_kpi", "rows": "kpi", "kpiLabel": False,
         "excludeKpis": kpis[1:]},
        {"name": "P_test_sans_var", "excludeVariations": [une_var]},
        {"name": "P_test_base_brute", "baseRow": "kpi", "kpiLabel": False},
        {"name": "P_test_vide", "includeBase": False,
         "excludeKpis": kpis},
    ]}
logs = []
gm.generate(c2 / (PROJ + ".SemanticModel"), conf, dry_run=False,
            remove_orphans=True, log=logs.append)
complet = rangees(c2, "P_test_complet")
check("table créée, avec ses 6 colonnes",
      complet and "column Branche" in (tables_dir(c2) / "P_test_complet.tmdl")
      .read_text(encoding="utf-8"))
check("les cibles sont au paramètre complet",
      any(r[4].startswith("Cible") for r in complet))

br = rangees(c2, "P_test_branche")
check(f"excludeBranches [\"\"] : ne reste que les branches ({len(br)} rangées)",
      br and all(r[5] != REEL for r in br) and {r[5] for r in br} <= set(branches))
check("… mais toutes les branches y sont",
      {r[5] for r in br} == {r[5] for r in complet} - {REEL})

sb = rangees(c2, "P_test_sans_base")
check("includeBase false : plus de rangée de base hors branche",
      sb and not any(r[4] == REEL and r[5] == REEL for r in sb)
      and len(sb) == len(complet) - sum(1 for r in complet
                                        if r[4] in (REEL, "Cible") and r[5] == REEL))

sc = rangees(c2, "P_test_sans_cible")
check("includeTargets false : plus aucune rangée de cible",
      sc and not any(r[4].startswith("Cible") for r in sc)
      and len(sc) == len(complet) - sum(1 for r in complet if r[4].startswith("Cible")))

uk = rangees(c2, "P_test_un_kpi")
check(f"excludeKpis : un seul KPI ({kpis[0]})", uk and {r[3] for r in uk} == {kpis[0]})
check("rows kpi + kpiLabel false : le NOM de la mesure, sans LOOKUPVALUE",
      all(r[0] == '"%s"' % kpis[0] for r in uk))

sv = rangees(c2, "P_test_sans_var")
check(f"excludeVariations [{une_var}] : la variation disparaît, branches comprises",
      sv and not any(r[4] == une_var for r in sv)
      and any(r[4] == une_var for r in complet))

bb = rangees(c2, "P_test_base_brute")
check("baseRow kpi + kpiLabel false : la base affiche le nom du KPI",
      bb and all(r[0] == '"%s"' % r[3] for r in bb if r[4] == REEL))

check("même rang de tri d'une table à l'autre pour une même mesure",
      all({r[1]: r[2] for r in complet}[r[1]] == r[2] for t in (br, sb, sc, sv)
          for r in t))

# ---------------------------------------------------------------------------
print("4. une table vidée par ses filtres n'est pas écrite")
check("P_test_vide n'existe pas", rangees(c2, "P_test_vide") is None)
check("le journal le dit", any("P_test_vide" in l and "aucune rangée" in l for l in logs))

# ---------------------------------------------------------------------------
print("5. la forme compacte se relit à l'identique")
for s in gm.fp_table_specs(conf["fieldParameter"]):
    compacte = gm.fp_spec_compacte(s)
    relu = gm.fp_table_specs({"tables": [compacte]})[0]
    if relu != s:
        check(f"{s['name']} relu à l'identique", False)
check("chaque table relue à l'identique depuis sa forme compacte", True)
check("une table aux défauts s'écrit avec son seul nom",
      gm.fp_spec_compacte(gm.fp_table_specs({"tables": ["X"]})[0]) == {"name": "X"})

# ---------------------------------------------------------------------------
print("6. l'onglet Rapport cherche ses KPI dans les tables de la liste")
from core import model_reader                       # noqa: E402


class _Projet:
    def __init__(self, cfg_path):
        self.config_json = cfg_path


cfgp = c2 / "measures_config.json"
cfgp.write_text(json.dumps(conf), encoding="utf-8")
check("candidate_parameters suit fieldParameter.tables",
      model_reader.candidate_parameters(_Projet(cfgp))[:3]
      == ["P_test_complet", "P_test_branche", "P_test_sans_base"])
cfgp.write_text(json.dumps({"fieldParameter": {}}), encoding="utf-8")
check("sans table au config : le défaut de l'onglet Rapport",
      model_reader.candidate_parameters(_Projet(cfgp)) == [model_reader.DEFAULT_FIELD_PARAMETER])

rmtree(c)
rmtree(c2)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
