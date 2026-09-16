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
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx", "measures_config.json")

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
from PySide6.QtCore import Qt                                # noqa: E402
from core.project import Project                             # noqa: E402
import tabs.tab_report as tr                                 # noqa: E402

app = QApplication.instance() or QApplication([])
projet = Project(c / (PROJ + ".pbip"))
onglet = tr.ReportTab()
onglet.set_project(projet)

depart = [onglet.cmb_template.itemText(i) for i in range(onglet.cmb_template.count())]
print("   KPI au chargement :", depart)
check("des KPI sont charges", len(depart) >= 3)

# --- on decoche une cible et on choisit un template, comme le ferait l'usager
onglet.cmb_template.setCurrentText(depart[1])
ecarte = depart[0]
for i in range(onglet.lst_targets.count()):
    if onglet.lst_targets.item(i).text() == ecarte:
        onglet.lst_targets.item(i).setCheckState(Qt.Unchecked)
check("une cible est decochee", ecarte not in onglet._checked(onglet.lst_targets))

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
check("mais l'onglet ne le voit PAS encore (liste peuplee une seule fois)",
      NOUVEAU not in [onglet.cmb_template.itemText(i)
                      for i in range(onglet.cmb_template.count())])

# --- le rafraichissement que declenche la fin de generation -----------------
onglet.refresh_model()
apres = [onglet.cmb_template.itemText(i) for i in range(onglet.cmb_template.count())]
print("   KPI apres refresh :", apres)
check("le nouveau KPI apparait dans le template", NOUVEAU in apres)
check("… et dans la liste des cibles",
      NOUVEAU in [onglet.lst_targets.item(i).text()
                  for i in range(onglet.lst_targets.count())])
check("il arrive COCHE (on veut propager vers lui)",
      NOUVEAU in onglet._checked(onglet.lst_targets))
check("le KPI template choisi est conserve",
      onglet.cmb_template.currentText() == depart[1])
check("la cible decochee le reste (les choix ne sont pas defaits)",
      ecarte not in onglet._checked(onglet.lst_targets))
check("le journal annonce la nouveaute",
      NOUVEAU in onglet.log.toPlainText())

# --- le cablage : ModelTab -> app -------------------------------------------
print("   cablage generation -> rafraichissement")
import tabs.tab_model as tm                                  # noqa: E402
check("ModelTab expose le signal", hasattr(tm.ModelTab, "modele_genere"))
import app as application                                    # noqa: E402
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
