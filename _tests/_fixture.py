# -*- coding: utf-8 -*-
"""Projet de démonstration exigé par les tests.

Les suites travaillent sur une COPIE d'un vrai projet PBIP — c'est ce qui leur
donne leur valeur : elles lisent du TMDL et des visual.json authentiques plutôt
que des fixtures inventées. Ce projet n'est PAS versionné (le dépôt ne contient
que l'outil), donc un clone frais ne l'a pas.

Plutôt que de planter avec une trace illisible, les tests s'arrêtent alors
proprement en disant ce qui manque et comment le fournir.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJET_DEMO = "Fitbit for random devs"


def exiger_projet(racine, nom: str = PROJET_DEMO, xlsx: str | None = None):
    """Vérifie que le projet de démo est là ; sinon, sort en code 0 (test
    ignoré, pas échoué) avec un message actionnable."""
    racine = Path(racine)
    manque = [nom + s for s in (".pbip", ".Report", ".SemanticModel")
              if not (racine / (nom + s)).exists()]
    if xlsx and not (racine / xlsx).exists():
        manque.append(xlsx)
    if not manque:
        return True
    print("IGNORE : le projet de demonstration est absent de " + str(racine))
    print("   manque : " + ", ".join(manque))
    print("   Ces suites travaillent sur une COPIE d'un projet PBIP reel ; il")
    print("   n'est pas versionne (le depot ne porte que l'outil). Pose un")
    print("   projet PBIP a la racine et nomme-le « " + nom + " »,")
    print("   ou lance les tests depuis ton dossier de travail.")
    sys.exit(0)
