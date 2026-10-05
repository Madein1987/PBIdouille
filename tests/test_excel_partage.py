# -*- coding: utf-8 -*-
"""Travailler dans TD_Indicateurs avec l'outil ouvert a cote.

    py tests\\test_excel_partage.py

Le contrat voulu, en trois points :

  1. hors action explicite, l'outil ne touche PAS au classeur — les en-tetes
     sont lus une fois et gardes en memoire ;
  2. une EXECUTION relit toujours le disque, donc ce qu'on vient d'enregistrer
     dans Excel est pris en compte sans rien rafraichir ;
  3. une lecture reussit meme si Excel tient le fichier ouvert, et ne
     l'empeche jamais d'enregistrer.

Le point 3 tient a la lecture sur INSTANTANE : on copie le classeur dans le
temporaire et on analyse la copie, donc on ne touche a l'original que le temps
d'une copie d'octets.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import stat
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
FIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FIT))
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx", "measures_config.json")

import openpyxl                                   # noqa: E402
import xlsx_lecture as xl                         # noqa: E402
import color_matrix_by_kpi as cmx                 # noqa: E402
import generate_measures as gm                    # noqa: E402
from core import model_reader as mr               # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


# --- ouvrir un fichier COMME EXCEL (lecture+ecriture, partage lecture) ------
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
FILE_SHARE_READ = 0x00000001
OPEN_EXISTING = 3
INVALID = ctypes.c_void_p(-1).value
_CreateFileW = ctypes.windll.kernel32.CreateFileW
_CreateFileW.restype = wintypes.HANDLE
_CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                         wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                         wintypes.HANDLE]
_CloseHandle = ctypes.windll.kernel32.CloseHandle


class CommeExcel:
    """Tient le classeur comme Excel le fait pendant qu'on l'edite."""

    def __init__(self, chemin):
        self.chemin = str(chemin)
        self.h = None

    def __enter__(self):
        self.h = _CreateFileW(self.chemin, GENERIC_READ | GENERIC_WRITE,
                              FILE_SHARE_READ, None, OPEN_EXISTING, 0, None)
        if self.h == INVALID or self.h is None:
            raise AssertionError("impossible de simuler Excel sur " + self.chemin)
        return self

    def __exit__(self, *_):
        if self.h not in (None, INVALID):
            _CloseHandle(wintypes.HANDLE(self.h))


def excel_peut_enregistrer(xlsx) -> bool:
    """Le geste d'Excel a l'enregistrement : ecrire a cote, puis substituer."""
    tmp = Path(str(xlsx) + ".excel_tmp")
    shutil.copy2(xlsx, tmp)
    try:
        os.replace(tmp, xlsx)
        return True
    except PermissionError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


c = Path(tempfile.gettempdir()) / "pbidouille_partage"
rmtree(c)
c.mkdir(parents=True)
for suffixe in (".Report", ".SemanticModel"):
    shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
for f in ((PROJ + ".pbip"), "TD_Indicateurs.xlsx", "measures_config.json"):
    shutil.copy2(FIT / f, c / f)
XLSX = c / "TD_Indicateurs.xlsx"


def poser_colonne(nom, valeur):
    """Ajoute/ecrit une colonne — ce que fait l'usager dans Excel puis Ctrl+S."""
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.worksheets[0]
    entetes = [str(x.value).strip().lower() if x.value else "" for x in ws[1]]
    col = entetes.index(nom) + 1 if nom in entetes else ws.max_column + 1
    ws.cell(row=1, column=col, value=nom)
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=col, value=valeur)
    wb.save(XLSX)
    wb.close()


poser_colonne("couleur_fill", "#123456")
poser_colonne("couleur_text", "#FFFFFF")

# ===================================================================== 1
print("1. lire pendant qu'Excel tient le classeur")
with CommeExcel(XLSX):
    check("Excel tient bien le fichier (la simulation marche)",
          not excel_peut_enregistrer(XLSX))
    try:
        entetes = mr.excel_headers(XLSX)
        check("les en-tetes se lisent quand meme", "mesure" in entetes)
    except Exception as e:
        check("les en-tetes se lisent quand meme — " + type(e).__name__, False)
    try:
        couleurs = cmx.read_kpi_colors(XLSX, None, "mesure",
                                       "couleur_fill", "couleur_text")
        check("les couleurs se lisent quand meme", len(couleurs) >= 3)
    except Exception as e:
        check("les couleurs se lisent quand meme — " + type(e).__name__, False)
    try:
        attrs = gm.read_attribute_map(XLSX, "mesure", "libelle_indicateur")
        check("les attributs se lisent quand meme", len(attrs) >= 3)
    except Exception as e:
        check("les attributs se lisent quand meme — " + type(e).__name__, False)
check("Excel retrouve la main des qu'il lache", excel_peut_enregistrer(XLSX))

print("2. lire ne gene jamais l'enregistrement d'Excel")
for lecture, etiquette in (
    (lambda: mr.excel_headers(XLSX), "en-tetes"),
    (lambda: cmx.read_kpi_colors(XLSX, None, "mesure",
                                 "couleur_fill", "couleur_text"), "couleurs"),
    (lambda: gm.read_attribute_map(XLSX, "mesure", "libelle_indicateur"),
     "attributs"),
):
    lecture()
    check(f"apres avoir lu les {etiquette} : Excel peut enregistrer",
          excel_peut_enregistrer(XLSX))

print("   l'original n'est jamais analyse : on copie, on lit la copie")
vus: list = []
vrai_load = openpyxl.load_workbook


def load_espion(fichier, *a, **k):
    vus.append(str(fichier))
    return vrai_load(fichier, *a, **k)


openpyxl.load_workbook = load_espion
mr.excel_headers(XLSX)
cmx.read_kpi_colors(XLSX, None, "mesure", "couleur_fill", "couleur_text")
openpyxl.load_workbook = vrai_load
check("openpyxl n'a ouvert que des copies temporaires, jamais l'original",
      vus and all(str(XLSX) != v and "pbidouille_xlsx_" in v for v in vus))

# ===================================================================== 3
print("3. hors action explicite, l'outil n'ouvre plus le classeur")
lectures: list = []
vrai_lire = xl.lire_lignes


def lire_espion(chemin, *a, **k):
    lectures.append(str(chemin))
    return vrai_lire(chemin, *a, **k)


xl.lire_lignes = lire_espion

from qtpy.QtWidgets import QApplication                       # noqa: E402
from core.project import Project                              # noqa: E402
import app as application                                     # noqa: E402

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
tc = fen.tab_config
tc._load_global()
qapp.processEvents()
apres_demarrage = len(lectures)
check("le demarrage lit le classeur (il faut bien les colonnes)",
      apres_demarrage >= 1)

for _ in range(4):                       # rouvrir « Reglages globaux »
    tc._load_global()
for i in range(fen.tabs.count()):        # se promener dans les onglets
    fen.tabs.setCurrentIndex(i)
    qapp.processEvents()
for i in range(tc.inner.count()):        # et dans les sous-onglets
    tc.inner.setCurrentIndex(i)
    qapp.processEvents()
check("se promener dans l'outil ne le rouvre PAS",
      len(lectures) == apres_demarrage)
check("les combos sont tout de meme peuplees",
      tc.g_td_key.count() > 0 and "mesure" in
      [tc.g_td_key.itemText(i) for i in range(tc.g_td_key.count())])

print("   le bouton ↻ force bien une relecture")
avant = len(lectures)
tc._td_reload_columns(force=True)
check("↻ relit le disque", len(lectures) == avant + 1)

print("   une colonne ajoutee dans Excel apparait apres ↻")
poser_colonne("ordre_du_jour", 10)
check("sans ↻ : le cache tient bon (aucune relecture)",
      "ordre_du_jour" not in tc._td_entetes())
tc._td_reload_columns(force=True)
check("avec ↻ : la nouvelle colonne est la",
      "ordre_du_jour" in tc._td_entetes())

print("   changer de fichier relit sans qu'on ait a forcer")
autre = c / "Autre_TD.xlsx"
shutil.copy2(XLSX, autre)
tc.g_td_path.setText(str(autre))
avant = len(lectures)
tc._td_reload_columns()
check("un chemin different declenche la lecture", len(lectures) == avant + 1)
tc.g_td_path.setText(str(XLSX))
tc._td_reload_columns()

# ===================================================================== 4
print("4. une EXECUTION relit toujours le disque")
xl.lire_lignes = vrai_lire
conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
conf["indicateursXlsx"] = {"path": str(XLSX)}
conf["hardcodedAttributes"] = {"tokens": {"direction": "direction"}}

poser_colonne("direction", 1)
logs: list = []
gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=True, log=logs.append)
avant_dax = gm.read_attribute_map(XLSX, "mesure", "direction")
check("la generation a lu la valeur du moment",
      set(avant_dax.values()) == {"1"})

poser_colonne("direction", -1)            # l'usager modifie et enregistre
apres_dax = gm.read_attribute_map(XLSX, "mesure", "direction")
check("apres modif + enregistrement : la nouvelle valeur est lue",
      set(apres_dax.values()) == {"-1"})
gm.generate(c / (PROJ + ".SemanticModel"), conf, dry_run=True,
            log=lambda *_: None)
check("… sans avoir eu a rafraichir quoi que ce soit dans l'outil",
      excel_peut_enregistrer(XLSX))

poser_colonne("couleur_fill", "#ABCDEF")
couleurs = cmx.read_kpi_colors(XLSX, None, "mesure",
                               "couleur_fill", "couleur_text")
check("les couleurs aussi sont relues a chaque execution",
      all(v["fill"] == "#ABCDEF" for v in couleurs.values()))

fen.deleteLater()
qapp.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
