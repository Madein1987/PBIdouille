# -*- coding: utf-8 -*-
"""Diagnostic de l'environnement Python pour la boîte à outils Power BI.
Lance : python env_check.py"""

import sys

print("Python :", sys.version)
print("Exe    :", sys.executable)
print()

# UI ChopChop : qtpy + UN binding (PySide6/PyQt5/...) ; export xlsx : pandas OU openpyxl
for lib in ["qtpy", "PySide6", "PyQt5", "PyQt6", "PySide2", "pandas", "openpyxl", "xlsxwriter", "qdarkstyle"]:
    try:
        mod = __import__(lib)
        print(f"  OK      {lib} {getattr(mod, '__version__', '')}")
    except ImportError:
        print(f"  absent  {lib}")
