# -*- coding: utf-8 -*-
"""Sauvegardes horodatées ET restauration, partagées par tous les outils.

Chaque outil qui écrit dans un projet PBIP copie d'abord les fichiers touchés
dans `<projet>\\_<outil>_backups\\<horodatage>\\`. Ces copies étaient jusqu'ici
« à plat » : le nom du fichier ne disait pas d'où il venait, donc restaurer
voulait dire retrouver la bonne destination à la main.

Ce module ajoute un **manifeste** (`manifeste.json`) à côté des copies : pour
chaque fichier, son chemin d'origine RELATIF au projet et ce qui lui est
arrivé (modifié / supprimé). Restaurer devient alors mécanique.

  - BackupSession : à utiliser côté outil (save() puis close()) ;
  - list_sessions() : toutes les sauvegardes d'un projet, la plus récente
    d'abord, tous outils confondus ;
  - restore_session() : remet les fichiers en place — en sauvegardant D'ABORD
    l'état courant, pour qu'une restauration soit elle-même annulable.

Les noms de fichiers de sauvegarde restent ceux que chaque outil utilisait
(`save(..., name=...)`) : les anciens dossiers restent lisibles, et le
wireframe continue de retrouver ses copies par convention pour son Ctrl+Z.

Les sauvegardes ANTÉRIEURES à ce module n'ont pas de manifeste : leur cible
est alors retrouvée en recalculant, pour chaque fichier candidat du projet, le
nom aplati qu'il aurait eu (déterministe — aucune devinette), avec repli sur
`definition\\tables\\` pour un .tmdl dont la table a été supprimée.

Aucune dépendance Qt : utilisable depuis les scripts en ligne de commande
comme depuis PBIdouille.
"""

from __future__ import annotations  # annotations paresseuses : Python 3.8+

import json
import shutil
from datetime import datetime
from pathlib import Path

MANIFEST = "manifeste.json"

# dossier de sauvegarde -> outil qui l'alimente (ordre = ordre d'affichage)
BACKUP_ROOTS = {
    "_tmdl_backups": "ChopChop",
    "_propagate_backups": "Propagation",
    "_wireframe_backups": "Wireframe",
}

MODIFIED = "modifié"   # le fichier existait : la copie le remet tel qu'il était
DELETED = "supprimé"   # l'opération l'a effacé : restaurer le RECRÉE
# le fichier n'existait PAS au moment de la sauvegarde : restaurer doit donc
# l'EFFACER. Sans cette troisième valeur, annuler une restauration qui a
# recréé un fichier serait impossible (rien à copier pour exprimer « absent »).
ABSENT = "absent"


def _stamp() -> str:
    """Horodatage à la microseconde : deux opérations rapprochées ne peuvent
    pas partager (ni écraser) un même dossier."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


class BackupSession:
    """Une opération = un dossier horodaté + son manifeste.

        s = BackupSession(racine, "ChopChop", projet)
        s.save(chemin)                       # avant d'écrire
        s.save(chemin, action=DELETED)       # avant de supprimer
        s.close("3 mesures, 1 table")        # écrit le manifeste

    Rien n'est créé sur le disque tant qu'aucun fichier n'est sauvegardé."""

    def __init__(self, root, tool: str, project_root, stamp: str | None = None):
        self.dir = Path(root) / (stamp or _stamp())
        self.tool = tool
        self.project_root = Path(project_root)
        self.entries: list[dict] = []
        self._used: set = set()

    # -- écriture -----------------------------------------------------------

    def _rel(self, path: Path) -> str:
        """Chemin relatif au projet (le manifeste reste valide si le dossier
        est déplacé/renommé) ; absolu en secours si le fichier est hors projet."""
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def _unique(self, name: str, path: Path) -> str:
        """Nom de copie libre. Deux fichiers homonymes dans des dossiers
        différents ne doivent pas s'écraser (le manifeste, lui, garde le vrai
        chemin) : on préfixe alors par le dossier parent, puis on numérote."""
        if name not in self._used:
            return name
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate = f"{path.parent.name}_{stem}{suffix}"
        i = 2
        while candidate in self._used:
            candidate = f"{path.parent.name}_{stem}_{i}{suffix}"
            i += 1
        return candidate

    def save(self, path, *, action: str = MODIFIED, name: str | None = None):
        """Copie `path` dans la session et enregistre son origine. `name` force
        le nom de la copie (conventions historiques des outils). Retourne le
        chemin de la copie, ou None si la source n'existe pas."""
        path = Path(path)
        if not path.exists():
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        name = self._unique(name or path.name, path)
        self._used.add(name)
        shutil.copy2(path, self.dir / name)   # octet pour octet, date conservée
        self.entries.append({"sauvegarde": name, "cible": self._rel(path),
                             "action": action})
        return self.dir / name

    def mark_absent(self, path):
        """Note qu'à cet instant `path` n'existe PAS. Restaurer la session
        effacera donc ce fichier. Aucune copie n'est faite (il n'y a rien à
        copier) — c'est la seule façon d'exprimer « ce fichier ne doit pas
        exister », et donc de rendre annulable une restauration qui recrée."""
        path = Path(path)
        self.entries.append({"sauvegarde": "", "cible": self._rel(path),
                             "action": ABSENT})

    def close(self, summary: str = ""):
        """Écrit le manifeste. Sans entrée : ne crée rien et retourne None
        (pas de dossier vide qui pollue la liste)."""
        if not self.entries:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)   # session « absent » seule
        (self.dir / MANIFEST).write_text(json.dumps({
            "outil": self.tool,
            "horodatage": self.dir.name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "racine": str(self.project_root),
            "resume": summary,
            "fichiers": self.entries,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.dir


# ---------------------------------------------------------------- lecture

def _infer_entries(session_dir: Path, project_root: Path) -> list[dict]:
    """Cibles d'une sauvegarde SANS manifeste (antérieure à ce module).

    Aucune devinette : on recalcule, pour chaque fichier candidat du projet, le
    nom aplati qu'il aurait porté, et on compare. Seul cas non résolu par cet
    index : un fichier que l'opération a SUPPRIMÉ (il n'existe plus, donc
    n'est plus candidat) — un .tmdl retombe alors sur `definition\\tables\\`,
    l'emplacement de toute table, et est marqué « deviné »."""
    index: dict = {}
    for vj in project_root.glob("*.Report/definition/pages/*/visuals/*/visual.json"):
        index.setdefault(f"{vj.parents[2].name}_{vj.parent.name}.json", vj)  # propagation
        index.setdefault(f"{vj.parent.name}_visual.json", vj)                # wireframe
    for tm in project_root.glob("*.SemanticModel/definition/**/*.tmdl"):
        index.setdefault(tm.name, tm)

    tables_dirs = sorted(project_root.glob("*.SemanticModel/definition/tables"))
    out: list[dict] = []
    for f in sorted(session_dir.iterdir()):
        if f.is_dir() or f.name == MANIFEST:
            continue
        target = index.get(f.name)
        if target is not None:
            out.append({"sauvegarde": f.name,
                        "cible": target.relative_to(project_root).as_posix(),
                        "action": MODIFIED})
        elif f.suffix.lower() == ".tmdl" and tables_dirs:
            out.append({"sauvegarde": f.name,
                        "cible": (tables_dirs[0] / f.name)
                                 .relative_to(project_root).as_posix(),
                        "action": DELETED, "devine": True})
        else:
            out.append({"sauvegarde": f.name, "cible": None, "action": MODIFIED})
    return out


def session_info(session_dir, project_root=None) -> dict:
    """Décrit une sauvegarde : outil, date, résumé, fichiers (avec leur cible).
    Lit le manifeste s'il existe, sinon reconstitue (cf. _infer_entries)."""
    session_dir = Path(session_dir)
    root_dir = session_dir.parent
    project_root = Path(project_root) if project_root else root_dir.parent
    man = session_dir / MANIFEST
    info = {}
    if man.exists():
        try:
            info = json.loads(man.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            info = {}
    if info.get("fichiers"):
        info["manifeste"] = True
        info.setdefault("racine", str(project_root))
    else:
        info = {"outil": BACKUP_ROOTS.get(root_dir.name, root_dir.name.strip("_")),
                "horodatage": session_dir.name,
                "date": _pretty_stamp(session_dir),
                "racine": str(project_root),
                "resume": "",
                "fichiers": _infer_entries(session_dir, project_root),
                "manifeste": False}
    info["dossier"] = str(session_dir)
    info["n_fichiers"] = len(info["fichiers"])
    info["n_orphelins"] = sum(1 for e in info["fichiers"] if not e.get("cible"))
    return info


def _pretty_stamp(session_dir: Path) -> str:
    """« 2026-07-28 14:30:00 » depuis le nom du dossier, sinon depuis sa date
    de modification."""
    name = session_dir.name
    try:
        return datetime.strptime(name[:15], "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.fromtimestamp(session_dir.stat().st_mtime) \
                       .strftime("%Y-%m-%d %H:%M:%S")


def list_sessions(project_root, roots=None) -> list[dict]:
    """Toutes les sauvegardes d'un projet, la PLUS RÉCENTE d'abord, tous
    outils confondus. `roots` restreint aux dossiers voulus."""
    project_root = Path(project_root)
    out: list[dict] = []
    for folder in (roots or BACKUP_ROOTS):
        base = project_root / folder
        if not base.is_dir():
            continue
        for session in base.iterdir():
            if session.is_dir():
                out.append(session_info(session, project_root))
    out.sort(key=lambda i: i["horodatage"], reverse=True)
    return out


# ------------------------------------------------------------ restauration

def restore_session(session_dir, project_root=None, *, dry_run: bool = False,
                    log=None) -> dict:
    """Remet en place les fichiers d'une sauvegarde.

    L'état COURANT de chaque fichier touché est d'abord copié dans une
    nouvelle session « Restauration » : revenir en arrière sur une
    restauration se fait donc comme n'importe quelle autre annulation.

    Un fichier supprimé par l'opération est recréé (dossiers parents compris).
    Un fichier dont la cible est inconnue (vieille sauvegarde, index muet) est
    ignoré et listé dans `ignorés` — jamais écrit au hasard.

    ⚠ Power BI Desktop doit être FERMÉ : il ne relit les fichiers qu'à
    l'ouverture et les réécrirait à l'enregistrement."""
    log = log or (lambda *_: None)
    session_dir = Path(session_dir)
    info = session_info(session_dir, project_root)
    root = Path(info["racine"])

    plan, skipped = [], []
    for entry in info["fichiers"]:
        action = entry.get("action", MODIFIED)
        if not entry.get("cible"):
            skipped.append(entry.get("sauvegarde") or "?")
            continue
        if action == ABSENT:                    # à EFFACER, rien à copier
            plan.append((None, root / entry["cible"], ABSENT))
            continue
        src = session_dir / entry["sauvegarde"]
        if not src.exists():
            skipped.append(entry["sauvegarde"])
            continue
        plan.append((src, root / entry["cible"], action))

    report = {"restaurés": [], "supprimés": [], "ignorés": skipped,
              "sauvegarde_avant": None, "dossier": str(session_dir),
              "outil": info.get("outil", "")}
    if dry_run or not plan:
        report["restaurés"] = [str(d.relative_to(root)) for _s, d, a in plan
                               if a != ABSENT]
        report["supprimés"] = [str(d.relative_to(root)) for _s, d, a in plan
                               if a == ABSENT]
        return report

    # filet : l'état courant part dans sa propre session avant d'être écrasé.
    # Un fichier actuellement ABSENT est noté comme tel — sinon annuler cette
    # restauration ne saurait pas qu'il faut le ré-effacer.
    undo = BackupSession(session_dir.parent, "Restauration", root)
    for _src, dest, _action in plan:
        if dest.exists():
            undo.save(dest)
        else:
            undo.mark_absent(dest)
    undo_dir = undo.close(f"état avant restauration de {session_dir.name}")
    if undo_dir:
        report["sauvegarde_avant"] = str(undo_dir)

    for src, dest, action in plan:
        if action == ABSENT:
            if dest.exists():
                dest.unlink()
                # dossier de visuel PBIR devenu vide : le laisser traînerait un
                # répertoire fantôme dans le rapport
                try:
                    if dest.parent.is_dir() and not any(dest.parent.iterdir()):
                        dest.parent.rmdir()
                except OSError:
                    pass
                report["supprimés"].append(str(dest.relative_to(root)))
                log(f"effacé : {dest.relative_to(root)}  (absent à la sauvegarde)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        report["restaurés"].append(str(dest.relative_to(root)))
        log(f"restauré : {dest.relative_to(root)}"
            + ("  (fichier recréé)" if action == DELETED else ""))
    return report
