# -*- coding: utf-8 -*-
"""Lecture de la couche rapport (PBIR) pour le wireframe : pages (ordre, nom,
dimensions) et visuels (position, type, titre, champs utilisés). Réutilise
color_matrix_by_kpi.visual_title / is_static_color_entry — mêmes définitions
que les outils de coloration."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path


def rmtree_force(path) -> None:
    """shutil.rmtree qui lève l'attribut lecture-seule avant de réessayer —
    nécessaire sous Windows/OneDrive (les dossiers du rapport héritent
    d'attributs qui font échouer rmtree en « Accès refusé »)."""
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(str(path), onerror=onerror)

# moteurs importables quel que soit le lanceur (core\ et moteurs\ sont
# deux dossiers frères sous bidouille\).
_FITBIT_DIR = Path(__file__).resolve().parent.parent / "moteurs"
if str(_FITBIT_DIR) not in sys.path:
    sys.path.insert(0, str(_FITBIT_DIR))

import color_matrix_by_kpi as _cmx   # noqa: E402
import backup_restore as _br         # noqa: E402  (sauvegardes + manifeste)


def pages(report_dir) -> list:
    """[{id, display, width, height}] dans l'ordre du rapport (pages.json ;
    les dossiers non listés sont ajoutés à la fin)."""
    pages_dir = Path(report_dir) / "definition" / "pages"
    if not pages_dir.exists():
        return []

    order: list = []
    meta = pages_dir / "pages.json"
    if meta.exists():
        try:
            order = json.loads(meta.read_text(encoding="utf-8")).get("pageOrder") or []
        except (ValueError, OSError):
            order = []
    ids = [p.name for p in sorted(pages_dir.iterdir()) if p.is_dir()]
    ordered = [i for i in order if i in ids] + [i for i in ids if i not in order]

    out = []
    for pid in ordered:
        display, w, h = pid, 1280, 720
        pj = pages_dir / pid / "page.json"
        if pj.exists():
            try:
                d = json.loads(pj.read_text(encoding="utf-8"))
                display = d.get("displayName") or pid
                w = d.get("width") or w
                h = d.get("height") or h
            except (ValueError, OSError):
                pass
        out.append({"id": pid, "display": display, "width": float(w), "height": float(h)})
    return out


def _query_refs(node, out: list) -> None:
    """Collecte toutes les chaînes queryRef (« Table.Champ ») d'un sous-arbre."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "queryRef" and isinstance(v, str):
                if v not in out:
                    out.append(v)
            else:
                _query_refs(v, out)
    elif isinstance(node, list):
        for x in node:
            _query_refs(x, out)


def visuals(report_dir, page_id: str) -> list:
    """[{id, type, is_group, group_name, group_mode, title, x, y, z, w, h,
    hidden, parent, parent_name, child_count, fields, objects_keys,
    has_color_template, path}] pour une page.

    GROUPES : un visuel-groupe porte `visualGroup{displayName, groupMode}` ; ses
    membres portent `parentGroupName` = l'id du groupe. Les positions du JSON
    sont RELATIVES au groupe parent (un enfant à x=0 est au coin du groupe, pas
    de la page) — `x`/`y` retournés ici sont les positions ABSOLUES, obtenues en
    cumulant les offsets des groupes ancêtres (translation ; le ScaleMode n'est
    pas simulé, suffisant pour un schéma). `has_color_template` = gabarit de
    couleur « specific column » (opt-in de color_matrix_by_kpi)."""
    vis_dir = Path(report_dir) / "definition" / "pages" / page_id / "visuals"
    if not vis_dir.exists():
        return []

    raw = {}
    order = []
    for vj in sorted(vis_dir.glob("*/visual.json")):
        try:
            data = json.loads(vj.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        pos = data.get("position") or {}
        vis = data.get("visual") or {}
        vgroup = data.get("visualGroup")
        is_group = isinstance(vgroup, dict)
        fields: list = []
        _query_refs(vis.get("query"), fields)
        objects = vis.get("objects") or {}
        has_template = any(
            _cmx.is_static_color_entry(e)
            for e in (objects.get("columnFormatting") or [])
            if isinstance(e, dict)
        )
        vid = data.get("name") or vj.parent.name
        raw[vid] = {
            "id": vid,
            "is_group": is_group,
            "group_name": vgroup.get("displayName") if is_group else None,
            "group_mode": vgroup.get("groupMode") if is_group else None,
            "type": "groupe" if is_group else (vis.get("visualType") or "?"),
            "title": "" if is_group else _cmx.visual_title(data),
            "lx": float(pos.get("x") or 0),      # positions LOCALES (relatives au parent)
            "ly": float(pos.get("y") or 0),
            "z": float(pos.get("z") or 0),
            "w": float(pos.get("width") or 0),
            "h": float(pos.get("height") or 0),
            "hidden": bool(data.get("isHidden")),
            "parent": data.get("parentGroupName"),
            "fields": fields,
            "objects_keys": sorted(objects.keys()),
            "has_color_template": has_template,
            "path": str(vj),
        }
        order.append(vid)

    def absolute(vid, seen):
        it = raw[vid]
        p = it["parent"]
        if p and p in raw and vid not in seen:
            px, py = absolute(p, seen | {vid})
            return px + it["lx"], py + it["ly"]
        return it["lx"], it["ly"]

    def depth(vid, seen):
        p = raw[vid]["parent"]
        if p and p in raw and vid not in seen:
            return 1 + depth(p, seen | {vid})
        return 0

    out = []
    for vid in order:
        it = raw[vid]
        it["x"], it["y"] = absolute(vid, set())
        it["depth"] = depth(vid, set())    # niveau d'imbrication (0 = racine)
        # origine absolue du parent : pour reconvertir absolu -> local à l'écriture
        it["parent_x"] = it["x"] - it["lx"]
        it["parent_y"] = it["y"] - it["ly"]
        it["parent_name"] = raw[it["parent"]]["group_name"] if it["parent"] in raw else None
        it["child_count"] = sum(1 for o in raw.values() if o["parent"] == vid)
        out.append(it)
    return out


def write_positions(updates, backup_root) -> tuple:
    """Écrit de nouvelles positions LOCALES dans des visual.json.
    `updates` = {chemin_visual_json: (lx, ly, w, h)}. Sauvegarde d'abord chaque
    fichier sous backup_root/<horodatage>/ ; ne modifie QUE le bloc `position`
    (x/y/width/height ; z/tabOrder préservés). Retourne (nb écrits, dossier backup).
    ⚠ Power BI Desktop doit être FERMÉ (il relit à l'ouverture)."""
    session = _br.BackupSession(backup_root, "Wireframe (positions)",
                                _br.project_of(backup_root))
    written = 0
    for path, (lx, ly, w, h) in updates.items():
        vj = Path(path)
        if not vj.exists():
            continue
        data = json.loads(vj.read_text(encoding="utf-8"))
        pos = data.setdefault("position", {})
        pos["x"], pos["y"], pos["width"], pos["height"] = lx, ly, w, h
        # nom historique <id>_visual.json : le Ctrl+Z de l'onglet le reconstruit
        # par convention. Le manifeste ajoute le chemin d'origine (restauration).
        session.save(vj, name=vj.parent.name + "_visual.json")
        vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written += 1
    session.close(f"{written} position(s)")
    return written, session.dir


def create_group(report_dir, page_id, member_ids, display_name, backup_root) -> tuple:
    """Crée un visualGroup PBIR contenant les éléments donnés (visuels OU
    groupes), qui doivent être frères d'un même parent (groupe commun ou racine
    de page). Écrit un nouveau visual.json de groupe (position = boîte
    englobante des membres dans le repère du parent ; groupMode ScaleMode,
    convention Desktop) et réécrit chaque membre : parentGroupName = nouveau
    groupe + position RELATIVE au groupe. Les enfants des membres-groupes sont
    intacts (relatifs à leur propre parent). Backup des membres + manifeste
    (undo = supprimer le dossier du groupe créé et restaurer les backups) sous
    backup_root/<horodatage>/. Retourne (id_du_groupe, dossier_backup).
    ⚠ Power BI Desktop doit être FERMÉ."""
    report_dir = Path(report_dir)
    vis_dir = report_dir / "definition" / "pages" / page_id / "visuals"
    datas = {}
    for vid in member_ids:
        vj = vis_dir / vid / "visual.json"
        if not vj.exists():
            raise ValueError(f"visuel introuvable : {vid}")
        text = vj.read_text(encoding="utf-8")
        datas[vid] = (vj, text, json.loads(text))
    parents = {d.get("parentGroupName") for _, _, d in datas.values()}
    if len(parents) != 1:
        raise ValueError("les éléments à grouper doivent partager le même parent")
    parent = parents.pop()

    # boîte englobante dans le repère du parent commun (positions déjà relatives)
    def pos(d):
        p = d.get("position") or {}
        return (float(p.get("x") or 0), float(p.get("y") or 0),
                float(p.get("width") or 0), float(p.get("height") or 0))
    x0 = min(pos(d)[0] for _, _, d in datas.values())
    y0 = min(pos(d)[1] for _, _, d in datas.values())
    x1 = max(pos(d)[0] + pos(d)[2] for _, _, d in datas.values())
    y1 = max(pos(d)[1] + pos(d)[3] for _, _, d in datas.values())
    z_max = max(float((d.get("position") or {}).get("z") or 0) for _, _, d in datas.values())
    tab_max = max(float((d.get("position") or {}).get("tabOrder") or 0) for _, _, d in datas.values())

    # id 20 hex unique dans TOUT le rapport (invariant : dossier == champ name)
    used = {p.name for p in report_dir.glob("definition/pages/*/visuals/*")}
    gid = None
    for _ in range(1000):
        cand = secrets.token_hex(10)
        if cand not in used:
            gid = cand
            break
    if gid is None:
        raise ValueError("impossible de générer un id de groupe unique")

    schema = next(iter(datas.values()))[2].get(
        "$schema",
        "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json")
    group = {
        "$schema": schema,
        "name": gid,
        "position": {"x": x0, "y": y0, "z": z_max + 1,
                     "height": y1 - y0, "width": x1 - x0, "tabOrder": tab_max},
        "visualGroup": {"displayName": display_name, "groupMode": "ScaleMode"},
    }
    if parent:
        group["parentGroupName"] = parent

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = _br.BackupSession(backup_root, "Wireframe (groupement)",
                                _br.project_of(backup_root))
    backup_dir = session.dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    group_path = vis_dir / gid / "visual.json"
    for vid, (vj, text, d) in datas.items():
        session.save(vj, name=vid + "_visual.json")
        d["parentGroupName"] = gid
        p = d.setdefault("position", {})
        p["x"] = float(p.get("x") or 0) - x0
        p["y"] = float(p.get("y") or 0) - y0
        vj.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # le visual.json du groupe n'existait PAS : on le note, sans quoi restaurer
    # cette session laisserait le groupe créé en place (état hybride)
    session.mark_absent(group_path)
    group_path.parent.mkdir(parents=True, exist_ok=True)
    group_path.write_text(json.dumps(group, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (backup_dir / "group_manifest.txt").write_text(
        "# Groupement · " + stamp + "\n"
        f"# groupe créé : {group_path}\n"
        "# membres modifiés (backups ci-contre) :\n"
        + "\n".join(str(vj) for vj, _, _ in datas.values()) + "\n"
        "# undo : supprimer le dossier du groupe et restaurer les backups\n",
        encoding="utf-8")
    session.close(f"groupe « {display_name} » ({len(datas)} membre(s))")
    return gid, backup_dir


def ungroup(report_dir, page_id, group_id, backup_root) -> tuple:
    """Dissout un visualGroup : ses enfants DIRECTS remontent au parent du
    groupe (positions rebasées dans le repère de ce parent — à l'écran rien ne
    bouge), le visual.json du groupe est SUPPRIMÉ. Les sous-groupes membres
    gardent leur contenu intact. Backup du groupe + des membres sous
    backup_root/<horodatage>/. Retourne (nb_enfants, dossier_backup).
    ⚠ Power BI Desktop doit être FERMÉ."""
    vis_dir = Path(report_dir) / "definition" / "pages" / page_id / "visuals"
    gj = vis_dir / group_id / "visual.json"
    if not gj.exists():
        raise ValueError(f"groupe introuvable : {group_id}")
    gtext = gj.read_text(encoding="utf-8")
    g = json.loads(gtext)
    if not isinstance(g.get("visualGroup"), dict):
        raise ValueError(f"{group_id} n'est pas un groupe")
    gpos = g.get("position") or {}
    gx, gy = float(gpos.get("x") or 0), float(gpos.get("y") or 0)
    gparent = g.get("parentGroupName")

    session = _br.BackupSession(backup_root, "Wireframe (dégroupement)",
                                _br.project_of(backup_root))
    backup_dir = session.dir
    # le visual.json du groupe est SUPPRIMÉ plus bas -> action=supprimé pour
    # que la restauration le recrée
    session.save(gj, action=_br.DELETED, name=group_id + "_visual.json")

    n = 0
    members = []
    for vj in sorted(vis_dir.glob("*/visual.json")):
        text = vj.read_text(encoding="utf-8")
        d = json.loads(text)
        if d.get("parentGroupName") != group_id:
            continue
        session.save(vj, name=vj.parent.name + "_visual.json")
        if gparent:
            d["parentGroupName"] = gparent
        else:
            d.pop("parentGroupName", None)
        p = d.setdefault("position", {})
        p["x"] = float(p.get("x") or 0) + gx
        p["y"] = float(p.get("y") or 0) + gy
        vj.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        members.append(str(vj))
        n += 1
    rmtree_force(gj.parent)
    (backup_dir / "ungroup_manifest.txt").write_text(
        "# Dégroupement · " + backup_dir.name + "\n"
        f"# groupe supprimé : {gj} (backup ci-contre)\n"
        "# membres rebasés :\n" + "\n".join(members) + "\n"
        "# undo : restaurer les backups (groupe inclus)\n",
        encoding="utf-8")
    session.close(f"dégroupement de {group_id} ({n} enfant(s) remonté(s))")
    return n, backup_dir
