# -*- coding: utf-8 -*-
"""L'Excel des indicateurs est défini UNE fois, dans measures_config.json.

    py tests\\test_indicateurs_xlsx.py

Vérifie que le générateur (jetons <<…>>, portée par KPI) ET l'onglet Rapport
(couleurs des matrices) lisent la MÊME définition — c'était auparavant deux
réglages séparés qui pouvaient diverger.
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
import generate_measures as gm                               # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "TD_Indicateurs.xlsx",
              "measures_config.json")


PROJ = "Fitbit for random devs"
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


# ===================================================================== 1
print("1. resolution du bloc unique")
d = gm.indicateurs_xlsx({})
check("defauts", d == {"path": "TD_Indicateurs.xlsx", "keyColumn": "mesure",
                       "fillColumn": "couleur_fill", "textColumn": "couleur_text"})
d = gm.indicateurs_xlsx({"indicateursXlsx": {"path": "Refs.xlsx", "fillColumn": "bg"}})
check("le bloc surcharge ce qu'il precise", d["path"] == "Refs.xlsx" and d["fillColumn"] == "bg")
check("et laisse le reste au defaut", d["keyColumn"] == "mesure")
d = gm.indicateurs_xlsx({"hardcodedAttributes": {"xlsx": "Vieux.xlsx", "keyColumn": "cle"}})
check("compat : un ancien config sans bloc reste lu",
      d["path"] == "Vieux.xlsx" and d["keyColumn"] == "cle")
d = gm.indicateurs_xlsx({"indicateursXlsx": {"path": "A.xlsx"},
                         "hardcodedAttributes": {"xlsx": "B.xlsx"}})
check("le bloc unique gagne sur l'ancienne cle", d["path"] == "A.xlsx")
d = gm.indicateurs_xlsx({}, Path("C:/projet"))
check("chemin relatif resolu contre le dossier du projet",
      Path(d["path"]) == Path("C:/projet/TD_Indicateurs.xlsx"))
d = gm.indicateurs_xlsx({"indicateursXlsx": {"path": r"D:\ailleurs\X.xlsx"}}, Path("C:/projet"))
check("chemin absolu laisse tel quel", Path(d["path"]) == Path(r"D:\ailleurs\X.xlsx"))

# ===================================================================== 2
print("2. les deux onglets lisent la MEME definition")
c = Path(tempfile.gettempdir()) / "pbidouille_td"
rmtree(c)
c.mkdir(parents=True)
for suffixe in (".Report", ".SemanticModel"):
    shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
shutil.copy2(FIT / (PROJ + ".pbip"), c / (PROJ + ".pbip"))
shutil.copy2(FIT / "TD_Indicateurs.xlsx", c / "Indicateurs perso.xlsx")

cfg = json.loads((FIT / "measures_config.json").read_text(encoding="utf-8"))
cfg["indicateursXlsx"] = {"path": "Indicateurs perso.xlsx", "keyColumn": "mesure",
                          "fillColumn": "teinte", "textColumn": "encre"}
(c / "measures_config.json").write_text(
    json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

from PySide6.QtWidgets import QApplication                   # noqa: E402
from core.project import Project                             # noqa: E402
import tabs.tab_report as tr                                 # noqa: E402
import tabs.tab_config as tc                                 # noqa: E402

app = QApplication.instance() or QApplication([])
projet = Project(c / (PROJ + ".pbip"))

onglet_rapport = tr.ReportTab()
onglet_rapport.set_project(projet)
vu_rapport = onglet_rapport._td_spec()
kw = onglet_rapport._colorize_step()[1]

vu_generateur = gm.indicateurs_xlsx(cfg, c)

check("l'onglet Rapport lit le fichier du config",
      Path(vu_rapport["path"]).name == "Indicateurs perso.xlsx")
check("… et ses colonnes de couleur",
      vu_rapport["fillColumn"] == "teinte" and vu_rapport["textColumn"] == "encre")
check("l'etape « Colorer » utilise exactement ca",
      Path(kw["xlsx"]).name == "Indicateurs perso.xlsx"
      and kw["fill_col"] == "teinte" and kw["text_col"] == "encre")
check("generateur et onglet Rapport voient la MEME chose",
      Path(vu_generateur["path"]) == Path(vu_rapport["path"])
      and vu_generateur["keyColumn"] == vu_rapport["keyColumn"])
check("le rappel affiche le bon fichier",
      "Indicateurs perso.xlsx" in onglet_rapport.lbl_td.text())

# ===================================================================== 3
print("3. l'onglet Mesures ecrit ce bloc, et lui seul")
onglet_config = tc.ConfigTab()
onglet_config.set_project(projet)
onglet_config._config = json.loads(json.dumps(cfg))
onglet_config._load_global()
check("chemin charge", onglet_config.g_td_path.text() == "Indicateurs perso.xlsx")
check("colonnes chargees",
      onglet_config.g_td_fill.currentText() == "teinte"
      and onglet_config.g_td_text.currentText() == "encre")
onglet_config.g_td_fill.setCurrentText("couleur_fill")
onglet_config._commit_global()
bloc = onglet_config._config.get("indicateursXlsx")
check("bloc reecrit", bloc.get("fillColumn") is None and bloc.get("textColumn") == "encre")
check("aucune trace dans hardcodedAttributes",
      "xlsx" not in (onglet_config._config.get("hardcodedAttributes") or {})
      and "keyColumn" not in (onglet_config._config.get("hardcodedAttributes") or {}))

# tout remettre au defaut -> la cle disparait du config
onglet_config.g_td_path.setText("TD_Indicateurs.xlsx")
onglet_config.g_td_key.setCurrentText("mesure")
onglet_config.g_td_fill.setCurrentText("couleur_fill")
onglet_config.g_td_text.setCurrentText("couleur_text")
onglet_config._commit_global()
check("tout au defaut = aucune cle ecrite (config propre)",
      "indicateursXlsx" not in onglet_config._config)

onglet_rapport.deleteLater()
onglet_config.deleteLater()
app.processEvents()
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
