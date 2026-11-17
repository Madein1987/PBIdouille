"""Capture de ⚙ Réglages → Paramètres de champ, sur une copie (magasin jetable)."""
import os, sys, shutil, tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
OUTIL = Path(__file__).resolve().parents[2]          # PBIdouille/
SRC = OUTIL.parent / "PowerBI"                        # les projets
OUT = Path(__file__).resolve().parent / "png"
OUT.mkdir(exist_ok=True)
NOM = "Fitbit for random devs"
TMP = Path(tempfile.gettempdir()) / "pbid_capture_fp"
shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True)
for s in (".Report", ".SemanticModel"):
    shutil.copytree(SRC / (NOM + s), TMP / (NOM + s))
for f in (NOM + ".pbip", "measures_config.json", "TD_Indicateurs.xlsx"):
    if (SRC / f).exists():
        shutil.copy2(SRC / f, TMP / f)
sys.path[:0] = [str(OUTIL), str(OUTIL / "bidouille"), str(OUTIL / "bidouille" / "moteurs"),
                str(OUTIL / "tests")]
from _fixture import reglages_jetables
reglages_jetables("capture_fp")
from qtpy.QtWidgets import QApplication, QDialog, QGroupBox
qapp = QApplication.instance() or QApplication(sys.argv)
import app as appmod
from core.theme import apply_app_theme
apply_app_theme(qapp, appmod.APP_EMOJI, "ChopChop.BIdouille.Captures")
import tabs.tab_config as tc
from core.project import Project

ct = tc.ConfigTab()
ct.set_project(Project(TMP / (NOM + ".pbip")))
ct._load_global()
dlg = ct._dlg_reglages
dlg.resize(1100, 900)
dlg.show()
gb = next(g for g in dlg.findChildren(QGroupBox) if g.title() == "Paramètres de champ")
ed = ct.g_fp_tables
for i in range(ed.liste.count()):
    if ed.liste.item(i).text() == sys.argv[1] if len(sys.argv) > 1 else False:
        ed.liste.setCurrentRow(i)
import time
end = time.time() + 1
while time.time() < end:
    qapp.processEvents()
scroll = dlg.findChildren(tc.QScrollArea)[0]
scroll.ensureWidgetVisible(gb, 0, 0)
scroll.verticalScrollBar().setValue(gb.y())
end = time.time() + 0.5
while time.time() < end:
    qapp.processEvents()
gb.grab().save(str(OUT / "reglages_fp.png"))
print("ok", gb.size().width(), gb.size().height())
dlg.hide()
shutil.rmtree(TMP, ignore_errors=True)
