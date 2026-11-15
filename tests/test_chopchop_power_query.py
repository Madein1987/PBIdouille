# -*- coding: utf-8 -*-
"""ChopChop et Power Query : ce qu'une AUTRE requête consomme reste intact.

    py tests\\test_chopchop_power_query.py

Une table qu'aucun visuel ne touche peut quand même nourrir une autre requête
— fusion, ajout, jointure —, chargée dans le modèle ou non (une requête « ne
pas charger » vit dans expressions.tmdl). Retirer cette table, ou l'une de
ses colonnes, casse l'actualisation de la requête qui s'en sert.

Le cas qui restait faux : les COLONNES d'une table consommée n'étaient
protégées que si le consommateur les NOMMAIT (clé de jointure, liste
d'expansion). Table.Join, Table.Combine ou une expansion par
Table.ColumnNames font traverser chaque colonne sans en nommer aucune : elles
passaient pour inutilisées. Désormais toute la table consommée est protégée.

Travaille sur une COPIE du projet de démonstration ; rien n'est supprimé, seule
l'analyse est testée.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

FIT = Path(__file__).resolve().parent.parent
# les projets Power BI vivent HORS de l'outil (cf. moteurs/chemins.py)
PBI = FIT.parent / "PowerBI"
if os.environ.get("PBIDOUILLE_PROJETS", "").strip():
    PBI = Path(os.environ["PBIDOUILLE_PROJETS"].strip())
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO)

import unused_measures as um                         # noqa: E402

PROJ = PROJET_DEMO
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


c = Path(tempfile.gettempdir()) / "pbid_chopchop_pq"
DEF = c / (PROJ + ".SemanticModel") / "definition"
STEPS = DEF / "tables" / "steps.tmdl"


def projet_neuf():
    rmtree(c)
    c.mkdir(parents=True)
    for s in (".Report", ".SemanticModel"):
        shutil.copytree(PBI / (PROJ + s), c / (PROJ + s))
    shutil.copy2(PBI / (PROJ + ".pbip"), c / (PROJ + ".pbip"))


def requete_non_chargee(m: str):
    """Une requête « ne pas charger » : elle vit dans expressions.tmdl."""
    corps = "\n".join("\t\t" + l for l in m.strip().splitlines())
    (DEF / "expressions.tmdl").write_text(
        "expression Fusion =\n" + corps + "\n\tlineageTag: 1234\n\n"
        "\tannotation PBI_ResultType = Table\n\n", encoding="utf-8")


def remplacer_m_de_steps(m: str):
    """Change la requête M de la table chargée « steps »."""
    t = STEPS.read_text(encoding="utf-8")
    debut = t.index("\t\tsource =\n") + len("\t\tsource =\n")
    fin = t.index("\n\n", debut)
    corps = "\n".join("\t\t\t\t" + l for l in m.strip().splitlines())
    STEPS.write_text(t[:debut] + corps + t[fin:], encoding="utf-8")


def analyse():
    um.set_project(c / (PROJ + ".pbip"))
    return um.analyze()


def colonnes_inutilisees(r, table):
    return [k for k in r["unused_columns"] + r["column_chained"]
            if k.startswith("'" + table + "'[")]


# ===================================================================== 1
print("1. référence : sans consommateur, pbi_lineage est morte")
projet_neuf()
r0 = analyse()
check("pbi_lineage est une table entièrement inutilisée", "pbi_lineage" in r0["dead_tables"])
base_steps = set(colonnes_inutilisees(r0, "steps"))

# ===================================================================== 2
print("2. consommée par une requête NON chargée (expressions.tmdl)")
for nom, m in (
        ("jointure à plat Table.Join",
         'let\n    Source = Table.Join(steps, "dateTime", pbi_lineage, "Table")\nin\n    Source'),
        ("ajout Table.Combine",
         'let\n    Source = Table.Combine({pbi_lineage, #"pbi_lineage"})\nin\n    Source'),
        ("fusion + expansion par Table.ColumnNames",
         'let\n    J = Table.NestedJoin(steps, {"dateTime"}, pbi_lineage, {"Table"}, "L", JoinKind.LeftOuter),\n'
         '    X = Table.ExpandTableColumn(J, "L", Table.ColumnNames(pbi_lineage))\nin\n    X')):
    projet_neuf()
    requete_non_chargee(m)
    r = analyse()
    check(f"{nom} : la table n'est plus « morte »", "pbi_lineage" not in r["dead_tables"])
    check(f"{nom} : AUCUNE de ses colonnes n'est proposée à la suppression",
          colonnes_inutilisees(r, "pbi_lineage") == [])

# ===================================================================== 3
print("3. consommée par une requête CHARGÉE (fusion dans « steps »)")
projet_neuf()
remplacer_m_de_steps(
    'let\n    Source = Odbc.DataSource("dsn=FitbitDB", [HierarchicalNavigation=true]),\n'
    '    steps_Table = Source{[Name="steps",Kind="Table"]}[Data],\n'
    '    J = Table.NestedJoin(steps_Table, {"dateTime"}, #"pbi_lineage", {"Table"}, "L", JoinKind.LeftOuter)\n'
    'in\n    J')
r = analyse()
check("la table consommée n'est plus « morte »", "pbi_lineage" not in r["dead_tables"])
check("la raison est donnée (la requête qui la consomme)",
      "steps" in r["spared_tables"].get("pbi_lineage", ""))
check("aucune de ses colonnes n'est proposée à la suppression",
      colonnes_inutilisees(r, "pbi_lineage") == [])

# ===================================================================== 4
print("4. pas de protection en trop")
projet_neuf()
remplacer_m_de_steps(
    'let\n    Source = Odbc.DataSource("dsn=FitbitDB", [HierarchicalNavigation=true]),\n'
    '    steps_Table = Source{[Name="pbi_lineage",Kind="Table"]}[Data]\nin\n    steps_Table')
r = analyse()
check("un NOM DE SOURCE entre guillemets n'est pas une requête : pbi_lineage reste morte",
      "pbi_lineage" in r["dead_tables"])
projet_neuf()
requete_non_chargee('let\n    Source = Table.Join(steps, "dateTime", pbi_lineage, "Table")\nin\n    Source')
r = analyse()
check("la table consommatrice garde ses colonnes inutilisées repérables "
      "(sa propre requête ne protège rien)",
      set(colonnes_inutilisees(r, "steps")) == base_steps)

rmtree(c)
print()
print("TOUT OK" if _ok else "DES ECHECS")
sys.exit(0 if _ok else 1)
