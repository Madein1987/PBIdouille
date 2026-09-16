# -*- coding: utf-8 -*-
"""
Scanne récursivement un répertoire pour tous les projets PBIP et inventorie
les sources de données de chaque rapport — la matière première d'un lineage
complet du parc Power BI.

Ce qui est extrait :
  - le lien rapport -> modèle : local (byPath) ou connexion live (byConnection)
    depuis <rapport>.Report/definition.pbir ;
  - par table du modèle : chaque partition, son mode (import, directQuery,
    calculated, directLake...) et les connecteurs M trouvés dans son source
    (Sql.Database, Excel.Workbook, File.Contents, Web.Contents, ...) avec
    leurs deux premiers arguments (serveur/BD, chemin, URL...) ;
  - expressions.tmdl (expressions partagées / paramètres M), souvent là où
    vivent les noms de serveurs.

Sortie : pbi_lineage.csv (une ligne par source) + résumé console.
Lecture seule — aucun fichier de projet n'est modifié.
"""

from __future__ import annotations  # annotations paresseuses : Python 3.8+

import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
ROOT     = Path(r"C:\OneDrive - PJ\Data Cooler\_Power BI\Fitbit")
CSV_PATH = ROOT / "pbi_lineage.csv"
# ---------------------------------------------------------------------------

# fonctions M considérées comme des sources de données (préfixes)
CONNECTOR_PREFIXES = (
    "Sql.", "Excel.", "Csv.", "Web.", "OData.", "SharePoint.", "Folder.",
    "File.", "AnalysisServices.", "PowerBI.", "PowerPlatform.", "Snowflake.",
    "Databricks.", "Odbc.", "OleDb.", "MySql.", "PostgreSQL.", "Oracle.",
    "Teradata.", "AzureStorage.", "AzureDataLake", "Lakehouse.", "Fabric.",
    "GoogleBigQuery.", "Dataverse", "Salesforce", "Parquet.", "Access.",
    "DeltaLake.", "Kusto", "AzureDataExplorer",
)

CALL_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*)\s*\(")
# deux premiers arguments : littéral "..." (avec "" échappés) ou expression simple
ARGS_RE = re.compile(
    r'\(\s*("(?:[^"]|"")*"|[#\w][\w\. ]*)?\s*(?:,\s*("(?:[^"]|"")*"|[#\w][\w\. ]*))?'
)
# les noms TMDL entre apostrophes échappent l'apostrophe en la doublant ('')
PARTITION_RE = re.compile(r"^\tpartition\s+(?:'((?:[^']|'')+)'|(\S+))", re.M)
TABLE_RE     = re.compile(r"^table\s+(?:'((?:[^']|'')+)'|(\S+))", re.M)
MODE_RE      = re.compile(r"\bmode:\s*(\w+)")


def _tmdl_name(match) -> str:
    """Nom capturé, apostrophes dé-échappées."""
    if match.group(1) is not None:
        return match.group(1).replace("''", "'")
    return match.group(2)


def clean_arg(arg: str | None) -> str:
    if not arg:
        return ""
    arg = arg.strip()
    if arg.startswith('"') and arg.endswith('"'):
        arg = arg[1:-1].replace('""', '"')
    return arg


STRING_RE = re.compile(r'"(?:[^"]|"")*"')


def call_span(text: str, open_paren: int) -> int:
    """Position juste après la parenthèse fermante correspondante, en
    respectant les littéraux M ("" = guillemet échappé)."""
    depth = 0
    i = open_paren
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            i += 1
            while i < n:
                if text[i] == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        i += 2
                        continue
                    break
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def connectors_in(m_text: str):
    """[(connecteur, arg1, arg2)] pour chaque appel M ressemblant à une source.

    Les appels imbriqués dans un autre connecteur sont fusionnés : pour
    Excel.Workbook(File.Contents("x.xlsx")), on garde UNE ligne Excel.Workbook
    avec le chemin de File.Contents comme argument."""
    calls = []
    for call in CALL_RE.finditer(m_text):
        fn = call.group(1)
        if not fn.startswith(CONNECTOR_PREFIXES):
            continue
        open_paren = call.end() - 1
        calls.append((call.start(), open_paren, call_span(m_text, open_paren), fn))

    found = []
    for start, open_paren, end, fn in calls:
        # appel imbriqué dans un autre connecteur ? l'englobant s'en charge
        if any(s2 < start and end <= e2 for s2, _, e2, _ in calls if s2 != start):
            continue
        # littéraux de tout le span (récupère le chemin/URL des appels internes)
        literals = STRING_RE.findall(m_text[open_paren:end])
        if literals:
            a1 = clean_arg(literals[0])
            a2 = clean_arg(literals[1]) if len(literals) > 1 else ""
        else:
            # pas de littéral : arguments identifiants (ex. paramètre #"Serveur")
            am = ARGS_RE.match(m_text, open_paren)
            a1 = clean_arg(am.group(1)) if am else ""
            a2 = clean_arg(am.group(2)) if am else ""
        found.append((fn, a1, a2))
    return found


def split_partitions(text: str):
    """[(nom, bloc)] des partitions d'un fichier table TMDL."""
    matches = list(PARTITION_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((_tmdl_name(m), text[m.start():end]))
    return out


def scan_model(model_dir: Path, pbip_name: str, model_label: str, rows: list):
    """Inventorie les partitions + expressions partagées d'un modèle."""
    definition = model_dir / "definition"

    for tmdl in sorted((definition / "tables").glob("*.tmdl")) if (definition / "tables").exists() else []:
        text = tmdl.read_text(encoding="utf-8")
        tm = TABLE_RE.search(text)
        table = _tmdl_name(tm) if tm else tmdl.stem
        for part_name, block in split_partitions(text):
            mode_m = MODE_RE.search(block)
            mode = mode_m.group(1) if mode_m else ""
            conns = connectors_in(block)
            if conns:
                for fn, a1, a2 in conns:
                    rows.append([pbip_name, model_label, table, part_name, mode, fn, a1, a2])
            else:
                # partition sans connecteur reconnu (table calculée, etc.)
                kind = "calculated" if "= calculated" in block.splitlines()[0] else (mode or "?")
                rows.append([pbip_name, model_label, table, part_name, mode, f"(aucun connecteur — {kind})", "", ""])

    expressions = definition / "expressions.tmdl"
    if expressions.exists():
        text = expressions.read_text(encoding="utf-8")
        for fn, a1, a2 in connectors_in(text):
            rows.append([pbip_name, model_label, "(expressions partagées)", "", "", fn, a1, a2])


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    rows: list[list[str]] = []
    pbips = sorted(ROOT.rglob("*.pbip"))
    print(f"{len(pbips)} projet(s) PBIP sous {ROOT}\n")

    for pbip in pbips:
        name = pbip.stem
        base = pbip.parent

        # le .pbip pointe vers le dossier rapport
        report_dir = None
        try:
            meta = json.loads(pbip.read_text(encoding="utf-8"))
            for art in meta.get("artifacts", []):
                if "report" in art:
                    report_dir = base / art["report"]["path"]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        if report_dir is None:
            report_dir = base / f"{name}.Report"

        # rapport -> modèle : local ou live
        pbir = report_dir / "definition.pbir"
        model_dir = None
        model_label = ""
        if pbir.exists():
            ref = json.loads(pbir.read_text(encoding="utf-8")).get("datasetReference", {})
            if "byPath" in ref and ref["byPath"]:
                model_dir = (report_dir / ref["byPath"]["path"]).resolve()
                model_label = model_dir.name
            elif "byConnection" in ref and ref["byConnection"]:
                conn = ref["byConnection"]
                model_label = conn.get("pbiModelDatabaseName") or conn.get("connectionString", "?")
                rows.append([name, model_label, "", "", "", "ConnexionLive",
                             conn.get("connectionString", ""), ""])

        if model_dir and model_dir.exists():
            scan_model(model_dir, name, model_label, rows)
        elif not model_label:
            rows.append([name, "(modèle introuvable)", "", "", "", "", "", ""])

    # ---- CSV -----------------------------------------------------------------
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["PBIP", "Modèle", "Table", "Partition", "Mode", "Connecteur", "Détail 1", "Détail 2"])
        w.writerows(rows)
    print(f"Lineage écrit : {CSV_PATH}\n")

    # ---- résumé console : connecteurs distincts par projet --------------------
    by_pbip: dict[str, set] = {}
    for r in rows:
        if r[5] and not r[5].startswith("(aucun"):
            by_pbip.setdefault(r[0], set()).add(f"{r[5]}({r[6]})" if r[6] else r[5])
    for pbip_name in sorted(by_pbip):
        print(f"{pbip_name} :")
        for s in sorted(by_pbip[pbip_name]):
            print(f"    {s}")


if __name__ == "__main__":
    main()
