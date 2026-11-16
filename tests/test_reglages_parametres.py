# -*- coding: utf-8 -*-
"""⚙ Réglages → Paramètres de champ : la liste de tables, chacune ses réglages.

    py tests\\test_reglages_parametres.py

Vérifie, dans la vraie fenêtre (hors écran) :
  1. un config à l'ancien format s'ouvre en liste de tables, chacune avec les
     réglages de sa famille ;
  2. les filtres proposent les KPI du modèle, les variations au paramètre et
     les branches ;
  3. une table « par KPI » grise le choix de la rangée de base ;
  4. ajouter, dupliquer, retirer, renommer, filtrer ;
  5. Enregistrer écrit la liste sous forme compacte, sans les anciennes clés,
     et la génération suit ce qui a été réglé ;
  6. une exclusion hors vocabulaire (KPI renommé) survit à une édition ;
  7. Annuler n'écrit rien ;
  8. la barre latérale : une page par sujet, ouverture sur une page donnée,
     et la page vue en dernier est celle qui revient.

Travaille sur une COPIE du projet de démonstration, magasin de réglages jetable.
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
reglages_jetables("parametres")

from qtpy.QtCore import Qt                                       # noqa: E402
from qtpy.QtWidgets import QApplication, QDialog, QMessageBox     # noqa: E402

app = QApplication.instance() or QApplication([])

import generate_measures as gm                                   # noqa: E402
import tabs.fp_tables as fpt                                     # noqa: E402
import tabs.tab_config as tc                                     # noqa: E402
from core.project import Project                                 # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


copie = Path(tempfile.gettempdir()) / "pbid_reglages_parametres"
rmtree(copie)
copie.mkdir(parents=True)
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), copie / (PROJ + s))
for f in (PROJ + ".pbip", "measures_config.json", "TD_Indicateurs.xlsx"):
    if (PBI / f).exists():
        shutil.copy2(PBI / f, copie / f)

ct = tc.ConfigTab()
ct.set_project(Project(copie / (PROJ + ".pbip")))
dlg = ct._dlg_reglages
ed = ct.g_fp_tables


def fenetre(reponse, geste=None):
    def faux_exec():
        if geste:
            geste()
        return reponse
    dlg.exec_ = faux_exec
    dlg.exec = faux_exec


def sur_disque():
    return json.loads((copie / "measures_config.json").read_text(encoding="utf-8"))


def cocher(cmb, texte, on):
    m = cmb.model()
    for i in range(m.rowCount()):
        if m.item(i).text() == texte:
            if (m.item(i).checkState() == Qt.Checked) != on:
                cmb._toggle(m.index(i, 0))
            return True
    return False


def choisir(nom):
    for i in range(ed.liste.count()):
        if ed.liste.item(i).text() == nom:
            ed.liste.setCurrentRow(i)
            return True
    return False


# ---------------------------------------------------------------------------
print("1. l'ancien format s'ouvre en liste de tables")
ancien = sur_disque()["fieldParameter"]
noms_avant = gm.fp_table_names(ancien)
ct._load_global()
check("la liste montre les tables du config",
      [ed.liste.item(i).text() for i in range(ed.liste.count())] == noms_avant)
check("la première est choisie et affichée", ed.ed_nom.text() == noms_avant[0])
check("les anciens champs multilignes ont disparu",
      not hasattr(ct, "g_fp_tableNames") and not hasattr(ct, "g_fp_includeBase"))

print("2. les filtres proposent le vocabulaire du rapport")
_, bases = gm.read_measures(copie / (PROJ + ".SemanticModel"), ct._config)
check(f"KPI du modèle ({len(bases)})",
      [ed.cmb_kpis.model().item(i).text() for i in range(ed.cmb_kpis.model().rowCount())] == bases)
items_b = [ed.cmb_branches.model().item(i).text()
           for i in range(ed.cmb_branches.model().rowCount())]
check("branches : (hors branche) puis celles du config",
      items_b[0] == fpt.HORS_BRANCHE and "YTD" in items_b)
check("tout est coché : « tous »", ed.cmb_kpis.lineEdit().text() == "tous")

print("3. une table « par KPI » grise le choix de la rangée de base")
choisir("P_Indicateurs_parKPI")
check("rangées = le KPI", ed.cmb_rows.currentData() == "kpi")
check("… la rangée de base est grisée", not ed.cmb_base.isEnabled())
choisir("P_Indicateurs_parCalcul_baseKPI")
check("base = KPI pour la table mixte",
      ed.cmb_base.currentData() == "kpi" and ed.cmb_base.isEnabled())
choisir("P_Indicateurs_parCalcul")
check("table par calcul : la case libellé est grisée (rien n'affiche le KPI)",
      not ed.chk_libelle.isEnabled())

print("4. ajouter, dupliquer, retirer, renommer, filtrer")
reponses = iter(["P_seul_YTD", "P_Indicateurs_parKPI_copie"])
fpt.QInputDialog.getText = staticmethod(lambda *a, **k: (next(reponses), True))
fpt.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)


def gestes():
    ed._ajouter()
    check("Ajouter : la nouvelle table est choisie", ed.ed_nom.text() == "P_seul_YTD")
    check("… aux réglages par défaut", ed.cmb_rows.currentData() == "calcul"
          and ed.chk_base.isChecked() and ed.chk_cibles.isChecked())
    cocher(ed.cmb_branches, fpt.HORS_BRANCHE, False)
    check("décocher (hors branche) se lit à l'écran",
          fpt.HORS_BRANCHE not in ed.cmb_branches.lineEdit().text())
    choisir("P_Indicateurs_parKPI")
    ed._dupliquer()
    check("Dupliquer : copie insérée juste après, avec les mêmes réglages",
          ed.ed_nom.text() == "P_Indicateurs_parKPI_copie"
          and ed.cmb_rows.currentData() == "kpi")
    cocher(ed.cmb_kpis, bases[0], False)
    ed.chk_libelle.setChecked(False)
    choisir("P_Indicateurs_parCalcul_2")
    ed._retirer()
    choisir("P_Indicateurs_parCalcul")
    ed.chk_base.setChecked(False)
    ed.ed_nom.setText("P_Indicateurs_parCalcul_sansBase")
    ed._renommer()


fenetre(QDialog.Accepted, gestes)
check("Enregistrer écrit le config", ct.ouvrir_reglages() is True)

print("5. le config écrit : la liste, compacte, sans les anciennes clés")
fp = sur_disque()["fieldParameter"]
check("plus aucune ancienne clé",
      not any(k in fp for k in ("tableNames", "tableNamesByKpi", "tableNamesKpiBase",
                                "includeBase", "byKpiUsesLabel")))
noms = [t["name"] for t in fp.get("tables", [])]
check("les tables, dans l'ordre de la liste",
      noms == ["P_Indicateurs_parCalcul_sansBase", "P_Indicateurs_parCalcul_baseKPI",
               "P_Indicateurs_parKPI", "P_Indicateurs_parKPI_copie", "P_seul_YTD"])
t = {x["name"]: x for x in fp["tables"]}
check("une table n'écrit que ce qui s'écarte des défauts",
      t["P_Indicateurs_parCalcul_sansBase"] == {"name": "P_Indicateurs_parCalcul_sansBase",
                                                "includeBase": False}
      and t["P_seul_YTD"] == {"name": "P_seul_YTD", "excludeBranches": [""]})
check("la copie garde « par KPI » et ajoute ses propres filtres",
      t["P_Indicateurs_parKPI_copie"] == {"name": "P_Indicateurs_parKPI_copie",
                                          "rows": "kpi", "kpiLabel": False,
                                          "excludeKpis": [bases[0]]})
check("les réglages communs restent", fp.get("baseLabel") == ancien.get("baseLabel")
      and fp.get("kpiLabelLookup") == ancien.get("kpiLabelLookup"))

logs = []
gm.generate(copie / (PROJ + ".SemanticModel"), sur_disque(), dry_run=False,
            remove_orphans=True, log=logs.append)
tdir = copie / (PROJ + ".SemanticModel") / "definition" / "tables"


def lignes(nom):
    return re.findall(r'NAMEOF\(\[.*?\]\), \d+, "(.*?)", "(.*?)", "(.*?)"\)',
                      (tdir / (nom + ".tmdl")).read_text(encoding="utf-8"))


ytd = lignes("P_seul_YTD")
check("la génération suit : P_seul_YTD n'a que des branches",
      ytd and all(b != ancien.get("noBranchLabel", "Base") for _, _, b in ytd))
cop = lignes("P_Indicateurs_parKPI_copie")
check(f"… la copie par KPI écarte {bases[0]}",
      cop and all(k != bases[0] for k, _, _ in cop))
check("… et la sans-base n'a plus de rangée de base hors branche",
      not any(c == ancien.get("baseLabel") and b == ancien.get("noBranchLabel")
              for _, c, b in lignes("P_Indicateurs_parCalcul_sansBase")))

print("6. une exclusion hors vocabulaire survit à une édition")
conf = sur_disque()
conf["fieldParameter"]["tables"][0]["excludeKpis"] = ["KPI renommé depuis"]
(copie / "measures_config.json").write_text(json.dumps(conf, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
ct.set_project(Project(copie / (PROJ + ".pbip")))


def editer():
    choisir(conf["fieldParameter"]["tables"][0]["name"])
    cocher(ed.cmb_kpis, bases[1], False)


fenetre(QDialog.Accepted, editer)
ct.ouvrir_reglages()
ex = sur_disque()["fieldParameter"]["tables"][0].get("excludeKpis")
check("l'exclusion inconnue est gardée, la nouvelle ajoutée",
      ex is not None and set(ex) == {"KPI renommé depuis", bases[1]})

print("7. Annuler n'écrit rien")
avant = (copie / "measures_config.json").read_bytes()
fenetre(QDialog.Rejected, lambda: ed.chk_cibles.setChecked(False))
check("Annuler rend False", ct.ouvrir_reglages() is False)
check("… et le fichier n'a pas bougé", (copie / "measures_config.json").read_bytes() == avant)

print("8. la barre latérale")
from qtpy.QtWidgets import QGroupBox                             # noqa: E402
nav, pages = ct.reglages_nav, ct.reglages_pages
cles = [nav.item(i).data(tc.Qt.UserRole) for i in range(nav.count())]
check(f"une entrée par page ({len(cles)})",
      cles == [c for c, _ in tc.ConfigTab.PAGES_REGLAGES] and pages.count() == len(cles))
def groupes_de(i):
    pg = pages.widget(i).widget()
    return [g.title() for g in pg.findChildren(QGroupBox) if g.parent() is pg]


check("chaque page porte ses groupes (un seul, sauf l'Excel)",
      all(len(groupes_de(i)) == len(tc.ConfigTab.GROUPES_PAGE.get(c, (c,)))
          for i, c in enumerate(cles)))
excel = groupes_de(cles.index("excel"))
check(f"la page Excel porte aussi les attributs et la portée ({len(excel)} groupes)",
      excel[0].startswith("Excel des indicateurs")
      and any(t.startswith("Attributs codés en dur") for t in excel)
      and any(t.startswith("Portée par KPI") for t in excel))
check("plus de page à part pour les attributs ni la portée",
      "attributs" not in cles and "portee" not in cles)


def groupe_montre():
    return groupes_de(pages.currentIndex())[0]


check("aller_reglages('excel') montre l'Excel",
      ct.aller_reglages("excel") and groupe_montre().startswith("Excel des indicateurs"))
ct.aller_reglages("branches")
ct._dlg_reglages.resize(1040, 700)
ct._dlg_reglages.show()
app.processEvents()
check(f"la page Branches donne de la hauteur à ses listes "
      f"({ct.g_branches.height()} / {ct.g_branch_restrict.height()} px)",
      ct.g_branches.height() >= 300 and ct.g_branch_restrict.height() >= 250)
ct._dlg_reglages.hide()
check("cliquer dans la barre change la page",
      (nav.setCurrentRow(cles.index("branches")), groupe_montre())[1].startswith("Branches"))
check("une clé inconnue ne change rien",
      ct.aller_reglages("nulle_part") is False and groupe_montre().startswith("Branches"))
vu = []
fenetre(QDialog.Rejected, lambda: vu.append(groupe_montre()))
ct.ouvrir_reglages(page="parametres")
check("ouvrir_reglages(page=…) ouvre sur cette page", vu == ["Paramètres de champ"])
ct.ouvrir_reglages()
check("… et sans page, on retrouve la dernière vue", vu[-1] == "Paramètres de champ")

ct.deleteLater()
rmtree(copie)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
