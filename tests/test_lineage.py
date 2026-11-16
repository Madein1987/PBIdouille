# -*- coding: utf-8 -*-
"""Onglet « Sources de données » : le lineage du rapport ouvert.

    py tests\\test_lineage.py

Vérifie :
  1. la lecture M (moteurs/lineage.py) : connecteurs imbriqués fusionnés,
     arguments de premier niveau, options [..] et null ignorés, paramètres M
     résolus depuis expressions.tmdl ;
  2. le projet de démonstration : ses sources (Excel, ODBC, CSV), ses tables
     calculées, et que rien n'est écrit dans le projet ;
  3. une connexion live et un fichier local disparu ;
  4. l'onglet : regroupement par source / par table, filtre, ⚠ fichier
     introuvable, export CSV.

Travaille sur une COPIE du projet de démonstration.
"""

from __future__ import annotations

import csv
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

exiger_projet(PBI, PROJET_DEMO)
reglages_jetables("lineage")

import lineage as lg                                             # noqa: E402

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
print("1. la lecture M")
check("Excel.Workbook(File.Contents(…)) : UNE source, avec le chemin",
      lg.connectors_in('Excel.Workbook(File.Contents("C:\\\\d\\\\x.xlsx"), null, true)')
      == [("Excel.Workbook", "C:\\\\d\\\\x.xlsx", "")])
check("les options [Delimiter=\";\"] ne passent pas pour un détail",
      lg.connectors_in('Csv.Document(File.Contents("a.csv"),[Delimiter=";"])')
      == [("Csv.Document", "a.csv", "")])
check("serveur et base, une requête SQL en option ignorée",
      lg.connectors_in('Sql.Database("srv", "db", [Query="SELECT f(1,2)"])')
      == [("Sql.Database", "srv", "db")])
check("un paramètre suivi d'un littéral garde son rang",
      lg.connectors_in('Sql.Database(Serveur, "db")') == [("Sql.Database", "Serveur", "db")])
check("#\"Nom\" est un nom, pas une valeur",
      lg.connectors_in('Sql.Database(#"Mon serveur", #"Base")')
      == [("Sql.Database", "Mon serveur", "Base")])
check("ce qui n'est pas un connecteur est ignoré",
      lg.connectors_in('Table.TransformColumnTypes(Source, {{"a", type text}})') == [])
check("famille lisible", lg.famille("Odbc.DataSource") == "ODBC"
      and lg.famille("Excel.Workbook") == "Excel")
check("paramètres M de expressions.tmdl",
      lg.parametres_m('expression Serveur = "srv01" meta [IsParameterQuery=true, '
                      'Type="Text"]\n\tlineageTag: x\n\nexpression \'Ma Base\' = "db" '
                      'meta [IsParameterQuery=true]\n')
      == {"Serveur": "srv01", "Ma Base": "db"})

# ---------------------------------------------------------------------------
copie = Path(tempfile.gettempdir()) / "pbid_lineage"
rmtree(copie)
copie.mkdir(parents=True)
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
shutil.copy2(PBI / (PROJ + ".pbip"), copie / (PROJ + ".pbip"))
MODELE = copie / (PROJ + ".SemanticModel")
PBIP = copie / (PROJ + ".pbip")

print("2. le projet de démonstration")
mtimes = {p: p.stat().st_mtime_ns for p in copie.rglob("*") if p.is_file()}
res = lg.scan_projet(PBIP)
check("pas d'erreur, modèle local", not res["erreur"] and not res["live"]
      and res["modele"] == PROJ + ".SemanticModel")
tables_tmdl = len(list((MODELE / "definition" / "tables").glob("*.tmdl")))
tables_vues = {l["table"] for l in res["lignes"]}
check(f"chaque table du modèle est vue ({len(tables_vues)} / {tables_tmdl})",
      len(tables_vues) == tables_tmdl)
srcs = lg.sources(res["lignes"])
familles = {s["famille"] for s in srcs}
check(f"des sources lues : {sorted(familles)}", familles and None not in familles)
calc = [l for l in res["lignes"] if l["genre"] == lg.CALCULEE]
check(f"les tables calculées sont reconnues ({len(calc)})",
      calc and all(l["connecteur"].startswith("DAX") for l in calc))
check("une source = une clé (connecteur, détails) distincte",
      len({(s["connecteur"], s["detail1"], s["detail2"]) for s in srcs}) == len(srcs))
check("lecture seule : rien n'a bougé dans le projet",
      {p: p.stat().st_mtime_ns for p in copie.rglob("*") if p.is_file()} == mtimes)

print("3. paramètres, fichier disparu, connexion live")
expr = MODELE / "definition" / "expressions.tmdl"
expr.write_text('expression Serveur = "srv-prod" meta [IsParameterQuery=true, Type="Text", '
                'IsParameterQueryRequired=true]\n\tlineageTag: a\n\n'
                'expression Partagee =\n\t\tlet\n\t\t    Source = Sql.Database(Serveur, "ventes")\n'
                '\t\tin\n\t\t    Source\n\tlineageTag: b\n', encoding="utf-8")
manquant = str(copie / "disparu.xlsx")
t = MODELE / "definition" / "tables" / "zz_test.tmdl"
t.write_text("table zz_test\n\tlineageTag: z\n\n\tpartition zz_test = m\n\t\tmode: import\n"
             "\t\tsource =\n\t\t\t\tlet\n\t\t\t\t    Source = Excel.Workbook(File.Contents(\""
             + manquant + "\"), null, true)\n\t\t\t\tin\n\t\t\t\t    Source\n", encoding="utf-8")
res = lg.scan_projet(PBIP)
check("le paramètre M est lu", res["parametres"] == {"Serveur": "srv-prod"})
part = [l for l in res["lignes"] if l["table"] == lg.EXPRESSIONS]
check("une requête partagée montre la valeur de son paramètre",
      part and part[0]["detail1"] == "Serveur = srv-prod" and part[0]["detail2"] == "ventes")
check("le paramètre lui-même n'est pas une source",
      not any(l["partition"] == "Serveur" for l in res["lignes"]))
check("un fichier local disparu est repéré",
      any(l["detail1"] == manquant for l in res["lignes"])
      and lg.chemin_local(manquant) is not None and not Path(manquant).exists())
check("un chemin réseau n'est pas testé", lg.chemin_local("\\\\srv\\partage\\x.xlsx") is None)

live = copie / "live"
(live / "Live.Report").mkdir(parents=True)
(live / "Live.pbip").write_text(json.dumps({"artifacts": [{"report": {"path": "Live.Report"}}]}),
                                encoding="utf-8")
(live / "Live.Report" / "definition.pbir").write_text(json.dumps({"datasetReference": {
    "byConnection": {"connectionString": "Data Source=powerbi://api/x;Initial Catalog=Ventes",
                     "pbiModelDatabaseName": "Ventes"}}}), encoding="utf-8")
rl = lg.scan_projet(live / "Live.pbip")
check("connexion live : dite, avec sa chaîne",
      rl["live"].startswith("Data Source=") and rl["modele"] == "Ventes"
      and rl["lignes"][0]["genre"] == lg.LIVE)

# ---------------------------------------------------------------------------
print("4. l'onglet")
from qtpy.QtWidgets import QApplication, QFileDialog              # noqa: E402
app = QApplication.instance() or QApplication([])
from core.project import Project                                 # noqa: E402
import tabs.tab_lineage as tl                                    # noqa: E402

tab = tl.LineageTab()
tab.set_project(Project(PBIP))
check("analyse différée tant que l'onglet n'est pas visible", tab.arbre.topLevelItemCount() == 0)
tab.show()
app.processEvents()
n_src = len(lg.sources(tab.lignes()))
tops = [tab.arbre.topLevelItem(i) for i in range(tab.arbre.topLevelItemCount())]
check(f"par source : une ligne par source + les tables calculées ({len(tops)})",
      len(tops) == n_src + 1 and tops[-1].text(0).startswith("Tables calculées"))
check("… les tables calculées sont repliées", not tops[-1].isExpanded())
check("la source disparue est marquée ⚠", any(t.text(2).startswith("⚠") for t in tops)
      and "introuvable" in tab.lbl_avis.text() and not tab.lbl_avis.isHidden())
check("le résumé compte sources et tables",
      f"{n_src} sources" in tab.lbl_resume.text() and "calculées" in tab.lbl_resume.text())

tab.cmb_vue.setCurrentIndex(1)
tops_t = [tab.arbre.topLevelItem(i).text(0) for i in range(tab.arbre.topLevelItemCount())]
check("par table : zz_test et les expressions partagées ont leur ligne",
      "zz_test" in tops_t and lg.EXPRESSIONS in tops_t)
tab.cmb_vue.setCurrentIndex(0)

tab.ed_filtre.setText("disparu")
visibles = [tab.arbre.topLevelItem(i) for i in range(tab.arbre.topLevelItemCount())
            if not tab.arbre.topLevelItem(i).isHidden()]
check(f"filtre « disparu » : une seule source visible ({len(visibles)})", len(visibles) == 1)
tab.ed_filtre.setText("")

sortie = copie / "export.csv"
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(sortie), ""))
tab._exporter()
with sortie.open(encoding="utf-8-sig") as f:
    rangs = list(csv.reader(f, delimiter=";"))
check("export CSV : l'en-tête et une ligne par partition / connecteur",
      rangs[0] == lg.COLONNES_CSV and len(rangs) == len(tab.lignes()) + 1)

tab.deleteLater()
rmtree(copie)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
