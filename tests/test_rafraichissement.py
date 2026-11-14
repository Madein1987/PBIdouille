# -*- coding: utf-8 -*-
"""Apres une generation, les KPI tout neufs apparaissent SANS rechargement.

    py tests\\test_rafraichissement.py

Symptome corrige : on generait les variations d'un nouveau KPI, on passait a
l'onglet Rapport pour propager, et le KPI n'y etait pas — il fallait recharger
le rapport a la main. L'onglet Rapport peuplait ses listes une seule fois, au
chargement du projet.
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
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, reglages_jetables, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx", "measures_config.json")
reglages_jetables('rafraichissement')   # jamais les reglages reels

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


c = Path(tempfile.gettempdir()) / "pbidouille_refresh"
rmtree(c)
c.mkdir(parents=True)
for suffixe in (".Report", ".SemanticModel"):
    shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
for f in ((PROJ + ".pbip"), "TD_Indicateurs.xlsx", "measures_config.json"):
    shutil.copy2(FIT / f, c / f)

from PySide6.QtWidgets import QApplication                   # noqa: E402
from core.project import Project                             # noqa: E402
import tabs.tab_report as tr                                 # noqa: E402

app = QApplication.instance() or QApplication([])
projet = Project(c / (PROJ + ".pbip"))
onglet = tr.ReportTab()
onglet.set_project(projet)

depart = list(onglet._kpis)
print("   KPI au chargement :", depart)
check("des KPI sont charges", len(depart) >= 3)

# --- une grille des sources, comme l'usager l'aurait posee ------------------
import propagate_cf as pc                                    # noqa: E402
pc.ecrire_regles(c / "propagation.json", {"version": 2, "base": depart[1]})
onglet._refresh_sources_label()
check("l'onglet resume la grille", depart[1] in onglet.lbl_sources.text())

# --- un KPI apparait dans le modele (ce que fait une generation) -------------
NOUVEAU = "Nouveau KPI"
fp = c / (PROJ + ".SemanticModel") / "definition" / "tables" / "P_Indicateurs_parCalcul.tmdl"
t = fp.read_text(encoding="utf-8")
modele_ligne = next(l for l in t.splitlines() if "NAMEOF(" in l)
ajout = modele_ligne.rstrip().rstrip(",")
for avant, apres in (('"' + depart[0] + '"', '"' + NOUVEAU + '"'),):
    ajout = ajout.replace(avant, apres)
t = t.replace(modele_ligne, modele_ligne.rstrip() + "\n" + ajout + ",", 1) \
    if not modele_ligne.rstrip().endswith(",") else \
    t.replace(modele_ligne, modele_ligne + "\n" + ajout + ",", 1)
fp.write_text(t, encoding="utf-8")

import core.model_reader as mr                               # noqa: E402
check("le modele contient bien le nouveau KPI",
      NOUVEAU in mr.kpis(projet))
check("mais l'onglet ne le voit PAS encore (liste lue une seule fois)",
      NOUVEAU not in onglet._kpis)

# --- le rafraichissement que declenche la fin de generation -----------------
onglet.refresh_model()
apres = list(onglet._kpis)
print("   KPI apres refresh :", apres)
check("le nouveau KPI est connu de l'onglet", NOUVEAU in apres)
grille = pc.Sources.depuis_regles(
    pc.lire_regles(c / "propagation.json"), apres, ["Réel"])
check("… et, sans rien toucher, il suit la base de la grille",
      grille.source(NOUVEAU, "Réel") == depart[1])
check("la grille n'a pas ete reecrite pour autant",
      pc.lire_regles(c / "propagation.json") == {"base": depart[1],
                                                  "colonnes": {},
                                                  "groupes": [],
                                                  "exceptions": []})
check("le journal annonce la nouveaute, et qu'elle suit la base",
      NOUVEAU in onglet.journal.texte()
      and "suivent la base" in onglet.journal.texte())

# --- le cablage : ModelTab -> app -------------------------------------------
print("   cablage generation -> rafraichissement")
import tabs.tab_model as tm                                  # noqa: E402
check("ModelTab expose le signal", hasattr(tm.ModelTab, "modele_genere"))
import app as application                                    # noqa: E402
# la fenetre charge le vrai projet, et l'ouvrir range/nettoie ses
# sauvegardes : une suite de tests n'a pas a y toucher (cf. test_sauvegardes)
application.br.migrate_legacy = lambda *a, **k: []
import propagate_cf as _pcf_isole                          # noqa: E402
# ouvrir un projet renomme son ancien <rapport>.propagation.json : sur le VRAI
# dossier, ce serait a l'usager de le declencher, pas a une suite de tests
_pcf_isole.migrer_groupes = lambda *a, **k: None
application.br.prune_all = lambda *a, **k: []
fen = application.BidouilleWindow()
check("l'app a un gestionnaire", hasattr(fen, "_apres_generation"))
recu = []
fen.tab_report.refresh_model = lambda: recu.append(True)
fen.tab_config.model_panel._ecriture = True
fen.tab_config.model_panel._apres_succes(None)
app.processEvents()
check("emettre le signal rafraichit l'onglet Rapport", recu == [True])
recu.clear()
fen.tab_config.model_panel._ecriture = False       # aperçu (dry-run)
fen.tab_config.model_panel._apres_succes(None)
app.processEvents()
check("un simple apercu ne declenche RIEN", recu == [])

fen.deleteLater()
onglet.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
