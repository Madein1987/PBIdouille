# -*- coding: utf-8 -*-
"""L'app tourne en Python 3.8, la version la plus ancienne qu'on croise au
travail, et se télécharge en ÉDITION PRODUCTION.

    py tests\\test_python38.py

Vérifie, sur les fichiers de l'app suivis par git (app.py, bidouille\\) :
  1. chaque module se lit comme du Python 3.8 ;
  2. chaque module qui définit quelque chose porte « from __future__ import
     annotations », sans quoi une annotation « str | None » plante en 3.8 ;
  3. aucune méthode ou fonction apparue après 3.8 (removeprefix, …) ;
  4. aucun fichier .dev n'est suivi : le zip de GitHub démarrerait en dev.

Ce test lit le code ; il ne touche à rien.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# apparus après Python 3.8 : appelés comme méthode ou attribut
APRES_38 = {"removeprefix": "3.9", "removesuffix": "3.9", "lcm": "3.9",
            "cache": "3.9 (functools.cache)", "is_relative_to": "3.9",
            "with_stem": "3.9", "readlink": "3.9", "bit_count": "3.10",
            "pairwise": "3.10", "zip_strict": "3.10"}

_ok = True


def check(label, cond, detail=()):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)
    if not cond:
        for d in list(detail)[:10]:
            print("         " + d)


r = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True,
                   text=True, encoding="utf-8")
if r.returncode != 0:
    print("IGNORE : pas de dépôt git ici")
    sys.exit(0)
suivis = [n for n in r.stdout.splitlines() if n.strip()]
app = [n for n in suivis if n.endswith(".py")
       and (n == "app.py" or n.startswith("bidouille/"))]

syntaxe, futur, recents = [], [], []
for rel in app:
    src = (RACINE / rel).read_text(encoding="utf-8")
    try:
        arbre = ast.parse(src, filename=rel, feature_version=(3, 8))
    except SyntaxError as e:
        syntaxe.append(f"{rel}:{e.lineno} : {e.msg}")
        continue
    vide = not any(isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Assign))
                   for n in arbre.body)
    a_futur = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                  and any(a.name == "annotations" for a in n.names)
                  for n in arbre.body)
    if not a_futur and not vide:
        futur.append(rel)
    for n in ast.walk(arbre):
        if isinstance(n, ast.Attribute) and n.attr in APRES_38:
            recents.append(f"{rel}:{n.lineno} : .{n.attr} (Python {APRES_38[n.attr]})")

print(f"{len(app)} modules de l'app")
check("1. tous se lisent comme du Python 3.8", not syntaxe, syntaxe)
check("2. tous portent « from __future__ import annotations »", not futur, futur)
check("3. rien d'apparu après 3.8", not recents, recents)
dev = [n for n in suivis if Path(n).name == ".dev"]
check("4. aucun .dev suivi : le zip de GitHub démarre en production", not dev, dev)

print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
