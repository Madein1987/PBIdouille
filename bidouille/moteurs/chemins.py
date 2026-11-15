# -*- coding: utf-8 -*-
"""Où vivent les choses : l'outil d'un côté, les projets Power BI de l'autre.

    <dossier de travail>\\
        PBIdouille\\     l'outil (ce dépôt) : app.py, bidouille\\, tests\\, docs\\
        PowerBI\\        les projets .pbip, TD_Indicateurs.xlsx,
                         measures_config.json, propagation.json, les sauvegardes

Les deux sont frères : l'outil ne range plus rien à côté de lui, et un dossier
de projets ne contient plus de code. Ce module est le SEUL endroit qui connaît
cette disposition — l'app (projet ouvert par défaut, point de départ des
boîtes de dialogue), les lignes de commande des moteurs et les tests passent
tous par lui.

PBIDOUILLE_PROJETS (variable d'environnement) désigne un autre dossier de
projets, pour un poste où ils ne sont pas à côté de l'outil.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTIL = Path(__file__).resolve().parents[2]
PROJETS = Path(os.environ.get("PBIDOUILLE_PROJETS", "").strip()
               or OUTIL.parent / "PowerBI")
# le projet ouvert à défaut d'en avoir mémorisé un, et celui des tests
PROJET_DEMO = "Fitbit for random devs"
