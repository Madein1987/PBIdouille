# -*- coding: utf-8 -*-
"""Construit le zip PARTAGEABLE de PBIdouille (édition production).

    py empaqueter.py              -> dist\\PBIdouille_<version>_<date>.zip
    py empaqueter.py --verifier   -> les vérifications seules, sans zip

Ce qui part dans le zip : les fichiers SUIVIS PAR GIT (donc jamais un projet,
une sauvegarde, un Excel ou une bibliothèque personnelle — le dossier de
travail en est plein) moins les tests et les outils de dev, plus le guide
utilisateur de docs\\ s'il existe.

Ce qui est vérifié AVANT d'écrire quoi que ce soit — un échec n'écrit rien :
  · pas de fichier .dev dans le paquet (il donnerait l'édition dev) ;
  · chaque module se lit comme du Python 3.8 (la version la plus ancienne
    qu'on puisse croiser au travail) et porte « from __future__ import
    annotations », sans quoi une annotation « str | None » plante en 3.8 ;
  · aucune méthode ou fonction apparue après 3.8 (removeprefix, …) ;
  · le paquet, extrait ailleurs, se déclare bien en PRODUCTION.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DIST = RACINE / "dist"
# suivis par git, mais pas pour l'usager
EXCLUS = ("tests/", ".gitignore", "empaqueter.py")
DOCS = RACINE / "docs"
# apparus après Python 3.8 : appelés comme méthode ou attribut
APRES_38 = {"removeprefix": "3.9", "removesuffix": "3.9", "lcm": "3.9",
            "cache": "3.9 (functools.cache)", "is_relative_to": "3.9",
            "with_stem": "3.9", "readlink": "3.9", "bit_count": "3.10",
            "pairwise": "3.10", "zip_strict": "3.10"}


def fichiers_suivis() -> list:
    sortie = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True,
                            text=True, encoding="utf-8", check=True).stdout
    noms = [n for n in sortie.splitlines() if n.strip()]
    return [n for n in noms if not any(n == e or n.startswith(e) for e in EXCLUS)]


def verifier_python(chemins) -> list:
    erreurs = []
    for rel in chemins:
        if not rel.endswith(".py"):
            continue
        src = (RACINE / rel).read_text(encoding="utf-8")
        try:
            arbre = ast.parse(src, filename=rel, feature_version=(3, 8))
        except SyntaxError as e:
            erreurs.append(f"{rel}:{e.lineno} : syntaxe absente de Python 3.8 ({e.msg})")
            continue
        vide = not any(isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Assign))
                       for n in arbre.body)
        futur = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                    and any(a.name == "annotations" for a in n.names)
                    for n in arbre.body)
        if not futur and not vide:
            erreurs.append(f"{rel} : « from __future__ import annotations » manque")
        for n in ast.walk(arbre):
            if isinstance(n, ast.Attribute) and n.attr in APRES_38:
                erreurs.append(f"{rel}:{n.lineno} : .{n.attr} n'existe qu'à partir "
                               f"de Python {APRES_38[n.attr]}")
    return erreurs


def construire(verifier_seulement: bool) -> int:
    noms = fichiers_suivis()
    erreurs = []
    if any(Path(n).name == ".dev" for n in noms):
        erreurs.append(".dev est suivi par git : il donnerait l'édition dev")
    erreurs += verifier_python(noms)
    guide = sorted(DOCS.glob("*.pptx")) + sorted(DOCS.glob("*.pdf")) if DOCS.exists() else []

    # le paquet, extrait ailleurs, doit démarrer en production
    with tempfile.TemporaryDirectory(prefix="pbid_paquet_") as tmp:
        t = Path(tmp)
        for n in noms:
            (t / n).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(RACINE / n, t / n)
        env = dict(os.environ)
        env.pop("PBIDOUILLE_DEV", None)
        r = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, r'%s');"
                            "from core import edition;"
                            "print('production' if edition.production() else 'dev')"
                            % (t / "bidouille")],
                           capture_output=True, text=True, env=env)
        if r.stdout.strip() != "production":
            erreurs.append("le paquet extrait ne démarre pas en production : "
                           + (r.stdout + r.stderr).strip())

    print(f"{len(noms)} fichiers de l'application, {len(guide)} document(s) du guide")
    if erreurs:
        print("\nÉCHEC — rien n'a été écrit :")
        for e in erreurs:
            print("  ✗ " + e)
        return 1
    print("✓ Python 3.8, édition production, aucun fichier de dev")
    if verifier_seulement:
        return 0

    sys.path.insert(0, str(RACINE / "bidouille"))
    from core.edition import VERSION
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / f"PBIdouille_{VERSION}_{datetime.date.today():%Y%m%d}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in noms:
            z.write(RACINE / n, "PBIdouille/" + n)
        for g in guide:
            z.write(g, "PBIdouille/" + g.name)
    print(f"✓ {zip_path}  ({zip_path.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true",
                    help="vérifier seulement, sans écrire de zip")
    sys.exit(construire(ap.parse_args().verifier))
