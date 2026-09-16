# -*- coding: utf-8 -*-
"""Résolution d'un projet Power BI (.pbip) et mémoire des projets récents.

Un dossier PBIP contient « <nom>.pbip », « <nom>.Report\\ » et
« <nom>.SemanticModel\\ » ; les fichiers partagés du pipeline
(measures_config.json, TD_Indicateurs.xlsx) sont à la racine du dossier."""

from __future__ import annotations

from pathlib import Path


class Project:
    """Chemins dérivés d'un .pbip. Ne touche pas au disque (sauf `valid`)."""

    def __init__(self, pbip_path, config_override=None):
        self.pbip = Path(pbip_path)
        self.folder = self.pbip.parent
        self.name = self.pbip.stem
        # measures_config.json choisi explicitement (bouton « Config… ») —
        # None = convention : <dossier du .pbip>\measures_config.json
        self.config_override = Path(config_override) if config_override else None

    @property
    def report_dir(self) -> Path:
        return self.folder / (self.name + ".Report")

    @property
    def model_dir(self) -> Path:
        return self.folder / (self.name + ".SemanticModel")

    @property
    def config_json(self) -> Path:
        if self.config_override:
            return self.config_override
        return self.folder / "measures_config.json"

    @property
    def td_xlsx(self) -> Path:
        return self.folder / "TD_Indicateurs.xlsx"

    @property
    def valid(self) -> bool:
        return self.report_dir.is_dir() and self.model_dir.is_dir()

    def __str__(self) -> str:
        return str(self.pbip)


# --- projets récents (QSettings) -------------------------------------------
RECENTS_KEY = "recent_pbips"
MAX_RECENTS = 8


def load_recents(settings) -> list:
    """Liste des .pbip récents encore présents sur le disque (plus récent
    d'abord)."""
    raw = settings.value(RECENTS_KEY, [])
    if isinstance(raw, str):          # QSettings peut aplatir une liste d'un seul
        raw = [raw]
    return [p for p in (raw or []) if Path(p).exists()]


def push_recent(settings, pbip_path) -> None:
    """Place ce .pbip en tête des récents (dédupliqué, tronqué)."""
    pbip_path = str(pbip_path)
    recents = [p for p in load_recents(settings) if p != pbip_path]
    recents.insert(0, pbip_path)
    settings.setValue(RECENTS_KEY, recents[:MAX_RECENTS])
