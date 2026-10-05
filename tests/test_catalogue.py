# -*- coding: utf-8 -*-
"""Bibliotheque GLOBALE de variations, dans laquelle chaque rapport pioche.

    py tests\\test_catalogue.py

Le measures_config.json d'un rapport est AUTONOME : ce qu'il contient est
exactement ce qui sera genere. La bibliotheque vit hors projet ; importer copie
une variation DEDANS. Plus rien a cocher ni a retenir projet par projet.
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
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx", "measures_config.json")

import generate_measures as gm                     # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


c = Path(tempfile.gettempdir()) / "pbidouille_biblio"
rmtree(c)
c.mkdir(parents=True)
for suffixe in (".Report", ".SemanticModel"):
    shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
for f in ((PROJ + ".pbip"), "TD_Indicateurs.xlsx"):
    shutil.copy2(FIT / f, c / f)

complet = json.loads((FIT / "measures_config.json").read_text(encoding="utf-8"))
BIBLIO = c / "biblio" / "catalogue_variations.json"

# ===================================================================== 1
print("1. lecture / ecriture de la bibliotheque")
check("fichier absent = bibliotheque vide, pas une erreur",
      gm.read_biblio(BIBLIO) == {"variations": {}, "branches": {}})
check("chemin vide = idem", gm.read_biblio("") == {"variations": {}, "branches": {}})
gm.write_biblio(BIBLIO, complet["variations"], complet["branches"])
check("ecrite (dossier cree au besoin)", BIBLIO.exists())
b = gm.read_biblio(BIBLIO)
check("relue entiere", set(b["variations"]) == set(complet["variations"]))
check("les branches suivent", set(b["branches"]) == set(complet["branches"]))
BIBLIO.write_text("pas du json", encoding="utf-8")
check("fichier illisible = vide, pas une erreur",
      gm.read_biblio(BIBLIO)["variations"] == {})
gm.write_biblio(BIBLIO, complet["variations"], complet["branches"])

# ===================================================================== 2
print("2. importer : la variation entre DANS le config du rapport")
rapport = {"settings": complet["settings"], "variations": {}}
b = gm.read_biblio(BIBLIO)
faits = gm.import_variations(rapport, b, ["7d avg", "PY", "YTD"], lambda *_: None)
check("trois importees", faits == ["7d avg", "PY", "YTD"])
check("le config du rapport les contient",
      set(rapport["variations"]) == {"7d avg", "PY", "YTD"})
check("YTD amene son entree de BRANCHE", "YTD" in (rapport.get("branches") or {}))
check("7d avg n'en amene pas", "7d avg" not in (rapport.get("branches") or {}))
journal = []
gm.import_variations(rapport, b, ["inexistante"], journal.append)
check("un id inconnu est signale, pas fatal",
      any("inexistante" in l for l in journal))
check("la bibliotheque n'a pas bouge",
      len(gm.read_biblio(BIBLIO)["variations"]) == len(complet["variations"]))

# une copie PROFONDE : modifier le rapport ne touche pas la bibliotheque
rapport["variations"]["PY"]["namePattern"] = "{base} MODIFIE"
check("copie profonde (le rapport n'altere pas la bibliotheque)",
      gm.read_biblio(BIBLIO)["variations"]["PY"]["namePattern"] != "{base} MODIFIE")

# ===================================================================== 3
print("3. generation : le rapport ne genere QUE ce qu'il contient")
(c / "measures_config.json").write_text(
    json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
rapport["variations"]["PY"]["namePattern"] = "{base} PY"       # on remet
(c / "measures_config.json").write_text(
    json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8")
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
logs = []
st = gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=True, log=logs.append)
noms = set(st["created"]) | set(st["updated"]) | set(st["unchanged"])
check("les 7d avg sont generees", any(n.endswith(" 7d avg") for n in noms))
check("les PY aussi", any(n.endswith(" PY") for n in noms))
check("sparkline JAMAIS importee = jamais generee",
      not any(n.endswith(" sparkline") for n in noms))
check("MTD non importee = non generee", not any(n.endswith(" MTD") for n in noms))
check("la branche YTD fonctionne", any(" YTD" in n for n in noms))
check("aucune mention de selection dans le journal",
      not any("active(s) sur" in l for l in logs))

vide = {"settings": complet["settings"], "variations": {}}
try:
    gm.generate(c / (PROJ + ".SemanticModel"), vide, dry_run=True, log=lambda *_: None)
    check("config sans variation = erreur actionnable", False)
except SystemExit as e:
    check("config sans variation = erreur actionnable", "bibliothèque" in str(e))

# ===================================================================== 4
print("4. publier : du rapport VERS la bibliotheque")
maison = {"namePattern": "{base} maison", "dax": "{baseRef}",
          "inFieldParameter": False}
rapport["variations"]["maison"] = maison
b = gm.read_biblio(BIBLIO)
avant = len(b["variations"])
faits = gm.export_variations(rapport, b, ["maison"])
gm.write_biblio(BIBLIO, b["variations"], b["branches"])
check("publiee", faits == ["maison"])
relu = gm.read_biblio(BIBLIO)
check("la bibliotheque l'a gagnee", "maison" in relu["variations"])
check("et n'a rien perdu", len(relu["variations"]) == avant + 1)
check("contenu fidele",
      relu["variations"]["maison"]["namePattern"] == "{base} maison")

# ===================================================================== 5
print("5. UI : le dialogue et le bouton")
from PySide6.QtWidgets import QApplication, QPushButton     # noqa: E402
from core.project import Project                            # noqa: E402
import tabs.tab_config as tc                                # noqa: E402
from tabs.dialog_catalogue import CatalogueDialog           # noqa: E402

app = QApplication.instance() or QApplication([])
onglet = tc.ConfigTab()
onglet.set_project(Project(c / (PROJ + ".pbip")))
onglet._config = json.loads(json.dumps(rapport))
onglet._populate_list()
check("le bouton Bibliotheque existe",
      any(b.text() == "Bibliothèque…" for b in onglet.findChildren(QPushButton)))
from PySide6.QtCore import Qt as _Qt                          # noqa: E402
# une case ne se DESSINE que si le role CheckState est pose (le drapeau
# ItemIsUserCheckable, lui, fait partie des valeurs par defaut de Qt)
check("plus aucune case a cocher dans la liste",
      all(onglet.lst.item(i).data(_Qt.CheckStateRole) is None
          for i in range(onglet.lst.count())))
check("etiquette centree sur le rapport",
      "dans ce rapport" in onglet.lbl_catalogue.text())

dlg = CatalogueDialog(onglet._config, str(BIBLIO), onglet)
check("la bibliotheque est listee", dlg.lst_biblio.count() == len(relu["variations"]))
check("le rapport est liste", dlg.lst_rapport.count() == len(rapport["variations"]))
deja = [dlg.lst_biblio.item(i).text() for i in range(dlg.lst_biblio.count())
        if "déjà dans ce rapport" in dlg.lst_biblio.item(i).text()]
check("les variations deja presentes sont signalees", bool(deja))
dlg.lst_biblio.clearSelection()
for i in range(dlg.lst_biblio.count()):
    if dlg.lst_biblio.item(i).data(_Qt.UserRole) == "sparkline":
        dlg.lst_biblio.item(i).setSelected(True)
import tabs.dialog_catalogue as dc                           # noqa: E402
dc.QMessageBox.question = staticmethod(lambda *a, **k: dc.QMessageBox.Yes)
dc.QMessageBox.information = staticmethod(lambda *a, **k: None)
dlg._importer()
check("importer depuis le dialogue ajoute au config",
      "sparkline" in onglet._config["variations"])
check("le dialogue signale la modification", dlg.modifie is True)

print("6. l'ORDRE de la bibliotheque : il se change, et s'ecrit dans le fichier")


def ordre_liste():
    return [dlg.lst_biblio.item(i).data(_Qt.UserRole)
            for i in range(dlg.lst_biblio.count())]


def ordre_fichier():
    return list(json.loads(BIBLIO.read_text(encoding="utf-8"))["variations"])


def choisir(*ids):
    dlg.lst_biblio.clearSelection()
    for i in range(dlg.lst_biblio.count()):
        if dlg.lst_biblio.item(i).data(_Qt.UserRole) in ids:
            dlg.lst_biblio.item(i).setSelected(True)


depart = ordre_liste()
check("il y a de quoi ordonner", len(depart) >= 4)
check("la liste suit l'ordre du FICHIER", depart == ordre_fichier())

choisir(depart[2])
dlg._deplacer(-1)
check("↑ monte la selection d'un cran",
      ordre_liste()[1] == depart[2] and ordre_liste()[2] == depart[1])
check("… et c'est ECRIT dans le fichier", ordre_fichier() == ordre_liste())
check("… la selection suit l'element deplace",
      dlg._choisis(dlg.lst_biblio) == [depart[2]])

choisir(depart[2], depart[1])          # un bloc (dans le desordre des clics)
dlg._deplacer(-1)
check("un bloc monte d'un seul tenant, dans son ordre",
      ordre_liste()[:3] == [depart[2], depart[1], depart[0]])
dlg._deplacer(-1)
check("… et arrive au bord, il s'arrete — sans se retourner",
      ordre_liste()[:3] == [depart[2], depart[1], depart[0]])
choisir(depart[2], depart[1])
dlg._deplacer(1)
check("↓ redescend le bloc, toujours ensemble",
      ordre_liste()[1:3] == [depart[2], depart[1]]
      and ordre_fichier() == ordre_liste())

print("   A -> Z")
from qtpy.QtWidgets import QHBoxLayout as _QHB                    # noqa: E402
ordre_boutons = [lay for lay in dlg.findChildren(_QHB)
                 if lay.indexOf(dlg.b_trier) >= 0]
check("le tri s'appelle « Trier A → Z » et suit ↑ ↓ (plus au bout de la rangee)",
      dlg.b_trier.text() == "Trier A → Z" and ordre_boutons
      and ordre_boutons[0].indexOf(dlg.b_trier)
      == ordre_boutons[0].indexOf(dlg.b_descendre) + 1)
import unicodedata                                            # noqa: E402
cle = dc.cle_alpha
check("la cle de tri ignore majuscules et accents",
      cle("Écart") == cle("ecart") and sorted(["b", "Écart", "a"], key=cle)
      == ["a", "b", "Écart"])
avant = ordre_liste()
check("(elle n'etait PAS deja triee — sinon ce qui suit ne prouve rien)",
      avant != sorted(avant, key=cle))
dc.QMessageBox.question = staticmethod(lambda *a, **k: dc.QMessageBox.Cancel)
dlg._trier()
check("A -> Z annule : rien ne bouge", ordre_liste() == avant == ordre_fichier())
dc.QMessageBox.question = staticmethod(lambda *a, **k: dc.QMessageBox.Yes)
dlg._trier()
check("A -> Z confirme : la bibliotheque est triee, sur le disque aussi",
      ordre_liste() == sorted(avant, key=cle) == ordre_fichier())

print("   on importe dans l'ordre de la bibliotheque")
liste = ordre_liste()
dlg.lst_biblio.clearSelection()
dlg.lst_biblio.item(3).setSelected(True)     # clic sur le 4e…
dlg.lst_biblio.item(1).setSelected(True)     # … puis sur le 2e
check("la selection se lit dans l'ordre de la LISTE, pas des clics",
      dlg._choisis(dlg.lst_biblio) == [liste[1], liste[3]])

print("   la liste du rapport suit l'ordre du config")
check("(assez de variations pour qu'un ordre de set tombe faux)",
      len(onglet._config["variations"]) >= 5)
check("… et pas celui d'un set (quelconque)",
      [dlg.lst_rapport.item(i).data(_Qt.UserRole)
       for i in range(dlg.lst_rapport.count())]
      == list(onglet._config["variations"]))

dlg.deleteLater()
onglet.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
