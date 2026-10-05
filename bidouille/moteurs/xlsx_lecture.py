# -*- coding: utf-8 -*-
"""Lecture d'un classeur Excel qui RELÂCHE toujours le fichier.

openpyxl en mode `read_only` ne charge pas le classeur en mémoire : il garde
le .xlsx OUVERT et y lit à la demande. Tant que `close()` n'a pas été appelé,
le fichier reste tenu par le processus — et sous Windows, enregistrer depuis
Excel revient à écrire un temporaire puis à le SUBSTITUER au fichier, ce qu'un
handle ouvert fait échouer. D'où le « je ne peux plus enregistrer
TD_Indicateurs ».

Le symptôme était intermittent, et c'est le plus traître : les objets openpyxl
se référencent en cycle (classeur ↔ feuille), donc le compteur de références
ne les libère pas. Il faut attendre un passage du ramasse-miettes, qui arrive
quand il arrive — parfois tout de suite, parfois bien après. Le verrou
semblait donc aléatoire alors qu'il était systématique.

Une seule porte d'entrée ici, avec un `finally` : on ne peut plus oublier de
refermer, ni sur le chemin normal ni sur une erreur en cours de lecture.

Et comme la lecture se fait sur un INSTANTANÉ copié dans le temporaire, le
temps pendant lequel on touche au classeur de l'usager tombe à une copie
d'octets : on peut garder Excel ouvert dessus et l'enregistrer sans se cogner
à l'outil. Les appelants, eux, ne gardent RIEN en cache ici — c'est à la
couche UI de décider quand relire (au démarrage, puis à chaque exécution).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def lire_lignes(xlsx, sheet=None, max_rows=None) -> list:
    """Lignes d'une feuille (tuples de valeurs), fichier RENDU au retour.

    `sheet` : nom de la feuille, None pour la première.
    `max_rows` : s'arrêter après N lignes (l'en-tête seul, par exemple) —
    inutile de streamer tout un classeur pour lire sa première ligne.

    On lit un INSTANTANÉ : le classeur est copié dans le dossier temporaire,
    puis c'est la copie qu'openpyxl analyse. La fenêtre pendant laquelle on
    touche au fichier de l'usager se réduit ainsi à une copie d'octets
    (quelques millisecondes) au lieu de toute la durée de l'analyse XML — et
    Excel peut enregistrer par-dessus sans se heurter à nous. Le classeur fait
    quelques dizaines de Ko : la copie ne coûte rien.

    Lève ImportError si openpyxl manque : les appelants retombent alors sur
    pandas, qui, lui, referme tout seul."""
    import openpyxl

    source = Path(xlsx)
    dossier = tempfile.mkdtemp(prefix="pbidouille_xlsx_")
    copie = Path(dossier) / source.name
    try:
        shutil.copy2(source, copie)          # seul moment où l'on tient l'original
        wb = openpyxl.load_workbook(copie, read_only=True, data_only=True)
        try:
            ws = wb[sheet] if sheet else wb.worksheets[0]
            return list(ws.iter_rows(max_row=max_rows, values_only=True))
        finally:
            wb.close()
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
