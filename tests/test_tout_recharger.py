# -*- coding: utf-8 -*-
"""« ↻ Tout recharger » : voir les changements du disque sans relancer l'app.

    py tests\\test_tout_recharger.py

Symptome corrige : on genere des mesures, on ajoute une colonne dans
TD_Indicateurs, on retouche le modele dans Desktop — et l'outil continuait de
travailler sur des donnees perimees. Il fallait le fermer et le rouvrir.

Chaque onglet sait relire CE QUI LUI APPARTIENT, en gardant les choix en cours.
L'app orchestre, et previent d'abord de ce qui n'est pas encore ecrit : recharger
relit le disque, donc les modifications en attente sont perdues.
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
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx", "measures_config.json")
reglages_jetables('tout_recharger')   # jamais les reglages reels

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


c = Path(tempfile.gettempdir()) / "pbid_recharger"
rmtree(c)
c.mkdir(parents=True)
for s in (".Report", ".SemanticModel"):
    shutil.copytree(FIT / (PROJ + s), c / (PROJ + s))
for f in ((PROJ + ".pbip"), "TD_Indicateurs.xlsx", "measures_config.json"):
    shutil.copy2(FIT / f, c / f)

from qtpy.QtWidgets import QApplication, QPushButton       # noqa: E402
import app as application                                  # noqa: E402

# l'app ne doit pas ranger/nettoyer les sauvegardes du VRAI projet au demarrage
application.br.migrate_legacy = lambda *a, **k: []
import propagate_cf as _pcf_isole                          # noqa: E402
# ouvrir un projet renomme son ancien <rapport>.propagation.json : sur le VRAI
# dossier, ce serait a l'usager de le declencher, pas a une suite de tests
_pcf_isole.migrer_groupes = lambda *a, **k: None
application.br.prune_all = lambda *a, **k: []
qapp = QApplication.instance() or QApplication([])
fen = application.BidouilleWindow()
fen._set_project(str(c / (PROJ + ".pbip")))
qapp.processEvents()

tc, tr, tw, tk = (fen.tab_config, fen.tab_report, fen.tab_wireframe,
                  fen.tab_chopchop)

# ===================================================================== 1
print("1. le bouton, et un reload par onglet")
check("le bouton « Tout recharger » existe",
      any(b.text() == "↻ Tout recharger" for b in fen.findChildren(QPushButton)))
check("les quatre onglets savent se recharger",
      all(callable(getattr(t, "reload", None)) for t in fen._tabs))
check("rien n'est en attente au depart", fen._en_attente() == [])

# ===================================================================== 2
print("2. un KPI apparu dans le modele est vu SANS relancer l'app")
NOUVEAU = "KPI tout neuf"
fp = (c / (PROJ + ".SemanticModel") / "definition" / "tables"
      / "P_Indicateurs_parCalcul.tmdl")
texte = fp.read_text(encoding="utf-8")
ligne = next(l for l in texte.splitlines() if "NAMEOF(" in l)
ajout = ligne.rstrip().rstrip(",")
premier = re.search(r'"([^"]+)"\s*\)\s*,?\s*$', ajout)
ajout = ajout.replace('"' + premier.group(1) + '"', '"' + premier.group(1) + '"') \
    if premier else ajout
# on remplace le nom d'indicateur (4e element) par le nouveau
ajout = re.sub(r'(\)\s*,\s*\d+\s*,\s*)"[^"]*"', r'\1"' + NOUVEAU + '"', ajout, count=1)
fp.write_text(texte.replace(ligne, ligne.rstrip().rstrip(",") + ",\n" + ajout + ",", 1),
              encoding="utf-8")

avant = list(tr._kpis)
check("l'onglet Rapport ne le voit pas encore", NOUVEAU not in avant)
fen._reload_all()
qapp.processEvents()
apres = list(tr._kpis)
check("apres rechargement, le nouveau KPI est la", NOUVEAU in apres)

# ===================================================================== 3
print("3. une colonne ajoutee dans TD_Indicateurs est vue")
import openpyxl                                            # noqa: E402

tc._load_global()                     # peuple les combos (1re lecture)
avant_cols = [tc.g_td_order.itemText(i) for i in range(tc.g_td_order.count())]
check("la colonne n'existe pas encore", "ordre_neuf" not in avant_cols)
wb = openpyxl.load_workbook(c / "TD_Indicateurs.xlsx")
ws = wb.worksheets[0]
ws.cell(row=1, column=ws.max_column + 1, value="ordre_neuf")
wb.save(c / "TD_Indicateurs.xlsx")
wb.close()
check("sans rechargement, le cache tient bon (l'Excel n'est pas retouche)",
      "ordre_neuf" not in tc._td_entetes())
fen._reload_all()
qapp.processEvents()
tc._load_global()
check("apres rechargement, la colonne est proposee",
      "ordre_neuf" in [tc.g_td_order.itemText(i)
                       for i in range(tc.g_td_order.count())])

# ===================================================================== 4
print("4. le config et la grille des sources sont relus")
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
conf["variations"]["depuis le disque"] = {"namePattern": "{base} X",
                                          "dax": "{baseRef}",
                                          "inFieldParameter": False}
(c / "measures_config.json").write_text(
    json.dumps(conf, indent=2, ensure_ascii=False), encoding="utf-8")
check("l'onglet Mesures ne la voit pas encore",
      "depuis le disque" not in (tc._config.get("variations") or {}))
import propagate_cf as pc                                   # noqa: E402
check("la grille n'existe pas encore", "Aucune" in tr.lbl_sources.text())
pc.ecrire_regles(pc.groupes_path(c / (PROJ + ".Report")),
                 {"version": 2, "base": apres[0]})
fen._reload_all()
qapp.processEvents()
check("apres rechargement, la variation du disque est la",
      "depuis le disque" in (tc._config.get("variations") or {}))
check("… et la grille des sources aussi", apres[0] in tr.lbl_sources.text())

# ===================================================================== 5
print("5. les modifications en attente sont SIGNALEES, pas perdues en silence")
tc._set_dirty(True)
attente = fen._en_attente()
check("un config modifie est signale",
      any("Mesures" in a for a in attente))
vid = next(iter(tw._data), None)
if vid:
    tw._mark_dirty(vid)
    check("un wireframe modifie aussi",
          any("Wireframe" in a for a in fen._en_attente()))

import app as _app                                          # noqa: E402
vus: list = []


class FausseBoite:
    """Repond « Annuler » : le rechargement doit alors ne RIEN faire."""

    Accept, Destructive, Reject = object(), object(), object()

    def __init__(self, *a, **k):
        vus.append("boite affichee")

    def setWindowTitle(self, *a):
        pass

    def setText(self, t):
        vus.append(t)

    def addButton(self, texte, role):
        return texte

    def setDefaultButton(self, *a):
        pass

    def exec_(self):
        return 0

    def clickedButton(self):
        return "Annuler"


vrai_box = _app.QMessageBox
_app.QMessageBox = type("QMB", (FausseBoite,), {
    "AcceptRole": 0, "DestructiveRole": 1, "RejectRole": 2})
config_avant = json.dumps(tc._config, sort_keys=True)
fen._reload_all()
check("la boite a bien ete montree", any("boite affichee" in v for v in vus))
check("elle nomme ce qui serait perdu",
      any("non enregistr" in v for v in vus))
check("« Annuler » ne recharge RIEN",
      json.dumps(tc._config, sort_keys=True) == config_avant
      and tc._dirty is True)
_app.QMessageBox = vrai_box

tc.reload()
check("recharger pour de vrai releve le drapeau « modifie »",
      tc._dirty is False)
check("… et la variation du disque est toujours la (on a bien relu)",
      "depuis le disque" in (tc._config.get("variations") or {}))

fen.deleteLater()
qapp.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
