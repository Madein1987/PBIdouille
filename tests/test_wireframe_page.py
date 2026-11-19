# -*- coding: utf-8 -*-
"""Wireframe : quitter une page avec des déplacements non enregistrés.

    py tests\\test_wireframe_page.py

Changer de page redessine depuis les fichiers : sans question, les positions
non écrites disparaissaient. Vérifie les trois réponses (enregistrer,
abandonner, rester), un enregistrement qui échoue, et « Recharger ».

Travaille sur une COPIE du projet de démonstration, avec un magasin de
réglages jetable.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PBIDOUILLE_DEV"] = "1"          # l'onglet n'écrit qu'en édition dev
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
reglages_jetables("wireframe_page")

from qtpy.QtWidgets import QApplication, QMessageBox                  # noqa: E402

qapp = QApplication.instance() or QApplication([])

from core import report_reader                                        # noqa: E402
from core.project import Project                                      # noqa: E402
from tabs.tab_wireframe import WireframeTab                           # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


c = Path(tempfile.mkdtemp(prefix="pbid_wf_page_"))
for s in (".SemanticModel", ".Report"):
    shutil.copytree(PBI / (PROJ + s), c / (PROJ + s),
                    ignore=shutil.ignore_patterns(".pbi", "cache.abf"))
shutil.copy2(PBI / (PROJ + ".pbip"), c / (PROJ + ".pbip"))
RAPPORT = c / (PROJ + ".Report")


def fichiers() -> dict:
    return {f: f.read_bytes() for f in RAPPORT.rglob("visual.json")}


w = WireframeTab()
w.set_project(Project(c / (PROJ + ".pbip")))
qapp.processEvents()
reponses: list = []


def demander(geste):
    reponses.append(geste)
    return reponse[0]


reponse = ["rester"]
w._demander_non_ecrits = demander

# une page qui a un groupe : « Répartir » y déplace vraiment quelque chose
for i in range(w.cmb_pages.count()):
    w.cmb_pages.setCurrentIndex(i)
    qapp.processEvents()
    groupe = next((v for v, d in w._data.items() if d["is_group"]), None)
    if groupe:
        break
PAGE = w.cmb_pages.currentIndex()
AUTRE = (PAGE + 1) % w.cmb_pages.count()
check("le rapport a plusieurs pages, dont une avec un groupe",
      groupe and w.cmb_pages.count() > 1)
check("sans déplacement, changer de page ne demande rien", not reponses)
DEPART = fichiers()


def deplacer():
    w._select(groupe, False)
    w._distribute()
    qapp.processEvents()


def changer_de_page(index):
    w.cmb_pages.setCurrentIndex(index)
    qapp.processEvents()


print("1. rester")
deplacer()
n = len(w._dirty)
check(f"répartir laisse des éléments à écrire ({n})", n > 0)
positions = {v: (d["x"], d["y"], d["w"], d["h"]) for v, d in w._data.items()}
changer_de_page(AUTRE)
check("la question est posée", reponses == ["Changer de page"])
check("la liste revient sur la page affichée", w.cmb_pages.currentIndex() == PAGE)
check("rien n'est perdu", len(w._dirty) == n and positions == {
    v: (d["x"], d["y"], d["w"], d["h"]) for v, d in w._data.items()})
check("rien n'est écrit", fichiers() == DEPART)

print("2. un enregistrement qui échoue")
reponse[0] = "enregistrer"
ecrire, critique = report_reader.write_positions, QMessageBox.critical
report_reader.write_positions = lambda *a, **k: (_ for _ in ()).throw(OSError("verrouillé"))
QMessageBox.critical = staticmethod(lambda *a, **k: None)
changer_de_page(AUTRE)
report_reader.write_positions, QMessageBox.critical = ecrire, critique
check("on reste sur la page, avec les déplacements",
      w.cmb_pages.currentIndex() == PAGE and len(w._dirty) == n)

print("3. enregistrer")
changer_de_page(AUTRE)
apres = fichiers()
check("la nouvelle page s'affiche", w.cmb_pages.currentIndex() == AUTRE and not w._dirty)
check(f"les positions sont écrites ({n})",
      sum(apres[f] != DEPART[f] for f in DEPART) == n)
w._undo_last()
qapp.processEvents()
check("Ctrl+Z remet les fichiers", fichiers() == DEPART)

print("4. abandonner")
w.cmb_pages.setCurrentIndex(PAGE)
qapp.processEvents()
deplacer()
reponse[0] = "abandonner"
changer_de_page(AUTRE)
check("la nouvelle page s'affiche, sans rien à écrire",
      w.cmb_pages.currentIndex() == AUTRE and not w._dirty)
check("les fichiers n'ont pas bougé", fichiers() == DEPART)

print("5. Recharger")
w.cmb_pages.setCurrentIndex(PAGE)
qapp.processEvents()
deplacer()
reponse[0] = "rester"
reponses.clear()
w._recharger()
check("« Rester ici » garde les déplacements",
      reponses == ["Recharger"] and w._dirty and w.cmb_pages.currentIndex() == PAGE)
reponse[0] = "abandonner"
w._recharger()
check("« Abandonner » relit les fichiers", not w._dirty and fichiers() == DEPART)

w.close()
shutil.rmtree(c, onerror=lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)))
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
