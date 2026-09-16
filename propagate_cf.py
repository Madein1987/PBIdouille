# -*- coding: utf-8 -*-
"""
Propage les entrées de formatage conditionnel d'un KPI « template » vers les
autres KPI, dans les visual.json d'un rapport PBIP (format PBIR).

Contexte : avec un paramètre de champ, le selector d'un objet de formatage
vise une mesure précise (ex. _mesures.Total Steps YoY %). Quand le slicer
bascule sur un autre KPI, le selector ne matche plus et le formatage
disparaît. Ce script clone chaque entrée de formatage du KPI template pour
tous les autres KPI, en adaptant les noms de mesures (selector ET mesure CF).

Usage :
  1. FERMER Power BI Desktop (il ne relit les fichiers qu'à l'ouverture,
     et un enregistrement écraserait nos modifications) ;
  2. python propagate_cf.py
  3. rouvrir le .pbip.

MIROIR, pas simple recopie : le template est la seule source de vérité, donc
ce qu'il ne porte PLUS est RETIRÉ des KPI cibles (retirer l'image d'une carte
sur le KPI template la retire partout). Deux garde-fous : un visuel qui ne
porte aucune entrée du KPI template n'est jamais touché, et les couleurs
statiques « specific column » (color_matrix_by_kpi.py) sont hors périmètre.
Chaque visuel modifié est copié dans _propagate_backups\\<horodatage>\\ avant
écriture — un retrait involontaire se défait en recopiant le fichier.

Le template a autant de « faces » que de branches : sa face Réel irrigue tout,
une entrée présente UNIQUEMENT sur une branche (ex. le style des marqueurs de
la ligne YTD) ne descend que sur cette branche.

Idempotent : relancer remplace les clones existants. Pour changer le style,
modifie le CF du KPI template dans Desktop, enregistre, ferme, relance.

La liste des KPI est lue automatiquement dans P_Indicateurs.tmdl (colonne
Indicateur), donc elle suit le script Tabular Editor. TARGET_KPIS permet de
forcer une liste explicite au besoin.
"""

from __future__ import annotations  # annotations paresseuses : Python 3.8+

import json
import re
import sys
from datetime import datetime
from pathlib import Path

# backup_restore.py est le voisin de ce fichier (sauvegardes + manifeste)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_restore as br

# ---------------------------------------------------------------------------
REPORT_DIR      = Path(r"C:\OneDrive - PJ\Data Cooler\_Power BI\Fitbit\Fitbit for random devs.Report")
TEMPLATE_KPI    = "Total Steps"
TARGET_KPIS     = None            # None = auto via <FIELD_PARAMETER>.tmdl ; sinon ["Weight", ...]
ENTITY          = "_mesures"      # table qui héberge les mesures
FIELD_PARAMETER = "P_Indicateurs_parCalcul" # table paramètre où lire la liste des KPI

# Branches (suffixes de mesure) à propager EN PLUS du Réel. "" (Réel) est
# toujours inclus. À partir d'un attribut posé sur UNE branche, le script
# synthétise les autres (le suffixe s'insère juste après le KPI :
# « Weight PY » -> « Weight YTD PY »). Doit correspondre aux ids de `branches`
# dans measures_config.json. [] = pas de synthèse (échange de KPI seulement).
BRANCHES        = ["YTD"]

# --- diagnostic ---
# VERBOSE : liste, pour chaque visuel, TOUS les candidats CF qui visent le KPI
#   template, en marquant lesquels sont pris comme template et lesquels sont
#   IGNORÉS (pas de dataViewWildcard) + les entrées générées. Sert à voir
#   pourquoi une branche ne se propage pas.
# DRY_RUN : n'écrit RIEN (diagnostic pur). Mettre True pour inspecter d'abord.
VERBOSE = False
DRY_RUN = False
# ---------------------------------------------------------------------------


def kpis_from_parameter(semantic_dir: Path, field_parameter: str = FIELD_PARAMETER) -> list[str]:
    """Extrait les KPI distincts (colonne Indicateur, 4e valeur des tuples)
    de l'expression de la table paramètre `field_parameter`."""
    tmdl = semantic_dir / "definition" / "tables" / f"{field_parameter}.tmdl"
    if not tmdl.exists():
        raise SystemExit(
            f"Introuvable : {tmdl}\n"
            f"Enregistrer le PBIP après avoir créé {field_parameter}, ou définir "
            "TARGET_KPIS explicitement."
        )
    text = tmdl.read_text(encoding="utf-8")
    # NAMEOF\(.*?\) (et non [^)]*) pour gérer les parenthèses DANS les noms de
    # mesures, ex. NAMEOF([Weight (locf)]) : le non-greedy revient à la bonne
    # parenthèse fermante, ancrée par « ), <ordre>, "<KPI>" ». Le 4e élément
    # (Indicateur) est le nom du KPI.
    rows = re.findall(
        r'\(\s*"[^"]*"\s*,\s*NAMEOF\(.*?\)\s*,\s*\d+\s*,\s*"([^"]+)"', text
    )
    out: list[str] = []
    for kpi in rows:
        if kpi not in out:
            out.append(kpi)
    return out


def read_fp_maps(semantic_dir: Path, field_parameter: str = FIELD_PARAMETER):
    """Lit le paramètre de champ et renvoie deux tables :
      forward[(KPI, Calcul, Branche)] -> nom de mesure ;
      reverse[nom de mesure]          -> (KPI, Calcul, Branche).
    Source de vérité pour propager une mesure vers un autre KPI/branche SANS
    parser son nom : chaque rangée est « ("aff", NAMEOF([mesure]), ordre,
    "Indicateur", "Calcul", "Branche") ». Gère nativement les cibles dont la
    branche n'est PAS juste après le KPI (« Weight cible YTD »)."""
    tmdl = semantic_dir / "definition" / "tables" / f"{field_parameter}.tmdl"
    forward: dict = {}
    reverse: dict = {}
    if not tmdl.exists():
        return forward, reverse
    text = tmdl.read_text(encoding="utf-8")
    for m in re.finditer(
        r'\(\s*"[^"]*"\s*,\s*NAMEOF\(\s*\[([^\]]+)\]\s*\)\s*,\s*\d+\s*,'
        r'\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)', text):
        measure, kpi, calcul, branche = m.group(1), m.group(2), m.group(3), m.group(4)
        forward[(kpi, calcul, branche)] = measure
        reverse[measure] = (kpi, calcul, branche)
    return forward, reverse


def swap_kpi_branch(value: str, src_kpi: str, src_branch: str,
                    dst_kpi: str, dst_branch: str, entity: str = ENTITY,
                    fp_forward=None, fp_reverse=None) -> str:
    """Nom de la mesure équivalente pour (dst_kpi, dst_branch).

    Chemin ROBUSTE : si la mesure est connue du paramètre de champ (fp_reverse),
    on relit sa (KPI, Calcul, Branche) et on cherche la mesure cible (dst_kpi,
    MÊME Calcul, dst_branch) dans fp_forward — aucun parsing du nom, donc les
    cibles marchent quelle que soit la position de la branche.
    Repli (mesures hors paramètre : couleurs CF…) : ancien comportement, la
    branche s'insère juste après le KPI. branch = "" pour Réel. Prefix-safe."""
    if fp_reverse:
        for prefix in (f"{entity}.", ""):
            if not value.startswith(prefix):
                continue
            bare = value[len(prefix):]
            # Plus long PRÉFIXE connu du paramètre, pas seulement le nom exact.
            # Beaucoup de mesures dérivées n'entrent pas dans le paramètre
            # (couleurs de formatage conditionnel, sparklines : inFieldParameter
            # = false) alors que leur RACINE, elle, y est. « Weight cible
            # ecartCF » n'est pas mappée, mais « Weight cible » l'est : on
            # traduit la racine (-> « Body Fat % cible YTD ») et on recolle le
            # reste (« ecartCF »). La branche atterrit ainsi au bon endroit —
            # après la cible — au lieu du « Body Fat % YTD cible ecartCF »
            # inexistant que produisait le repli par nom.
            root = None
            for cand, (kpi_c, _calc, _br) in fp_reverse.items():
                if kpi_c != src_kpi:
                    continue                      # jamais traverser les KPI
                if bare == cand or bare.startswith(cand + " "):
                    if root is None or len(cand) > len(root):
                        root = cand
            if root is not None:
                _, calcul, _ = fp_reverse[root]
                tgt = (fp_forward or {}).get((dst_kpi, calcul, dst_branch))
                if tgt is not None:
                    return prefix + tgt + bare[len(root):]
                break   # racine connue mais sans équivalent -> repli ci-dessous
    src_head = src_kpi + ((" " + src_branch) if src_branch else "")
    dst_head = dst_kpi + ((" " + dst_branch) if dst_branch else "")
    for prefix in (f"{entity}.", ""):
        full = prefix + src_head
        if value == full:
            return prefix + dst_head
        if value.startswith(full + " "):
            return prefix + dst_head + value[len(full):]
    return value


def swap_tree_branch(node, src_kpi, src_branch, dst_kpi, dst_branch,
                     entity: str = ENTITY, fp_forward=None, fp_reverse=None):
    """Copie profonde d'un sous-arbre JSON, noms de mesures adaptés (KPI+branche)."""
    if isinstance(node, dict):
        return {k: swap_tree_branch(v, src_kpi, src_branch, dst_kpi, dst_branch,
                                    entity, fp_forward, fp_reverse)
                for k, v in node.items()}
    if isinstance(node, list):
        return [swap_tree_branch(x, src_kpi, src_branch, dst_kpi, dst_branch,
                                 entity, fp_forward, fp_reverse) for x in node]
    if isinstance(node, str):
        return swap_kpi_branch(node, src_kpi, src_branch, dst_kpi, dst_branch,
                               entity, fp_forward, fp_reverse)
    return node


def detect_branch(metadata, kpi, branches=BRANCHES, entity: str = ENTITY,
                  fp_reverse=None):
    """Branche de l'entrée template. Si la mesure est connue du paramètre de
    champ, on lit sa colonne Branche directement (robuste aux cibles) ; sinon
    on cherche le suffixe (parmi `branches`) qui suit le KPI dans le nom."""
    if metadata and fp_reverse:
        # même logique que swap_kpi_branch : plus long PRÉFIXE connu, pour que
        # les mesures dérivées hors paramètre (couleurs CF, sparklines) héritent
        # de la branche de leur racine — « Weight cible YTD ecartCF » est en
        # YTD parce que « Weight cible YTD » l'est.
        for prefix in (f"{entity}.", ""):
            if not metadata.startswith(prefix):
                continue
            bare = metadata[len(prefix):]
            root = None
            for cand, (kpi_c, _calc, _br) in fp_reverse.items():
                if kpi_c != kpi:
                    continue
                if bare == cand or bare.startswith(cand + " "):
                    if root is None or len(cand) > len(root):
                        root = cand
            if root is not None:
                branche = fp_reverse[root][2]
                return branche if branche in branches else ""
    if not metadata:
        return ""
    for prefix in (f"{entity}.", ""):
        head = prefix + kpi
        if metadata.startswith(head + " "):
            remainder = metadata[len(head) + 1:]
            for b in branches:
                if remainder == b or remainder.startswith(b + " "):
                    return b
            return ""
    return ""


def entry_metadata(entry) -> str | None:
    if not isinstance(entry, dict):
        return None
    selector = entry.get("selector")
    if not isinstance(selector, dict):
        return None
    return selector.get("metadata")


def is_static_color(entry) -> bool:
    """Entrée de couleur STATIQUE « specific column » (gérée par
    color_matrix_by_kpi.py, PAS par ici) : selector avec metadata SANS 'data',
    et une propriété couleur qui n'est PAS une mesure (ThemeDataColor/Literal).
    Tout le reste (CF à base de mesure, reference labels, display units...) se
    propage. Même logique que color_matrix_by_kpi.is_static_color_entry."""
    if not isinstance(entry, dict):
        return False
    sel = entry.get("selector")
    if not isinstance(sel, dict) or "metadata" not in sel or "data" in sel:
        return False
    for v in (entry.get("properties") or {}).values():
        if isinstance(v, dict) and isinstance(v.get("solid"), dict) and "color" in v["solid"]:
            if "Measure" not in v["solid"]["color"].get("expr", {}):
                return True
    return False


# Seule clé d'objet que color_matrix_by_kpi.py écrit (matrices « specific
# column ») — cf. son process_visual : « ne touche QUE objects.columnFormatting
# -> jamais les graphes (dataPoint), slicers, cartes ». Les couleurs statiques
# des AUTRES clés n'ont donc aucun autre propriétaire : la ligne PY en noir
# (dataPoint), la bordure des marqueurs… sont des attributs de style uniformes
# sur tous les KPI, et se propagent ici comme le reste.
COLUMN_FORMATTING_KEY = "columnFormatting"


def owned_by_color_matrix(key, entry) -> bool:
    """L'entrée appartient-elle à color_matrix_by_kpi.py (couleur STATIQUE dans
    la clé qu'il gère) ? Lui seul y attribue une couleur PAR KPI depuis
    l'Excel ; hors de cette clé, la couleur suit le template."""
    return key == COLUMN_FORMATTING_KEY and is_static_color(entry)


def _selector_id_order(entry):
    """(selector.id, selector.order) d'une entrée — les deux discriminants qui
    distinguent DEUX étiquettes de référence sur le MÊME KPI : chaque étiquette
    porte un id « field-<uuid> » propre (et un order 0/1 sur sa valeur), et son
    titre/détail se rattachent à elle par ce même id."""
    sel = entry.get("selector") if isinstance(entry, dict) else None
    if not isinstance(sel, dict):
        return (None, None)
    return (sel.get("id"), sel.get("order"))


def entry_key(entry):
    """Identité d'une entrée pour la déduplication : (metadata, id, order,
    propriétés). Deux entrées de même metadata mais de propriétés DIFFÉRENTES
    (« backColor » CF vs « labelDisplayUnits ») doivent COEXISTER ; et DEUX
    étiquettes de référence sur le même KPI se distinguent par leur selector.id
    (un field-<uuid> par étiquette) et leur order — sans eux, la 2e écrase la
    1re au clonage (bug : « seule la dernière étiquette est propagée »)."""
    md = entry_metadata(entry)
    sid, order = _selector_id_order(entry)
    props = ()
    if isinstance(entry, dict) and isinstance(entry.get("properties"), dict):
        props = tuple(sorted(entry["properties"].keys()))
    return (md, sid, order, props)


# Propriétés d'étiquette de référence PROUVÉES « point de donnée » : sur une
# carte à paramètre de champ, chaque KPI est un POINT DE DONNÉE du paramètre,
# et ces propriétés n'atteignent les KPI « virtuels » que si leur selector
# porte data:[dataViewWildcard] (la VALEUR l'a nativement ; le TEXTE du titre
# en a besoin — vérifié dans Desktop). TOUT LE RESTE (titleContentType, show du
# détail, labelDisplayUnits/labelPrecision de la valeur, etc.) est au niveau
# CHAMP : {metadata, id} SANS wildcard — leur ajouter la portée point de donnée
# fait que Power BI les IGNORE et le réglage retombe au défaut (titre -> « nom
# du champ », display units -> « Automatique »). Liste BLANCHE volontairement :
# une propriété inconnue garde la portée écrite par Desktop.
POINT_SCOPED_PROPS = {"value", "titleText", "detailValue"}


def _expr_has_measure(node) -> bool:
    """Le sous-arbre référence-t-il une MESURE (clé « Measure ») ?"""
    if isinstance(node, dict):
        return "Measure" in node or any(_expr_has_measure(v) for v in node.values())
    if isinstance(node, list):
        return any(_expr_has_measure(x) for x in node)
    return False


def _prop_point_scoped(name, val) -> bool:
    """Propriété d'étiquette « point de donnée » : nom connu
    (POINT_SCOPED_PROPS) OU valeur portée par une MESURE — elle doit se
    résoudre par KPI du paramètre (value, detailValue, couleur CF…), donc
    exige data:[dataViewWildcard]. Les bascules/formats littéraux (show,
    titleContentType, labelDisplayUnits…) restent niveau champ."""
    return name in POINT_SCOPED_PROPS or (isinstance(val, dict) and _expr_has_measure(val))


def _is_point_scoped_only(entry) -> bool:
    """L'entrée ne porte QUE des propriétés « point de donnée » ?"""
    props = entry.get("properties") if isinstance(entry, dict) else None
    return bool(props) and all(_prop_point_scoped(k, v) for k, v in props.items())


_WILDCARD_ONLY = [{"dataViewWildcard": {"matchingOption": 0}}]


def ensure_datapoint_scope(entry) -> bool:
    """Normalise la PORTÉE du selector d'une entrée liée à un emplacement
    (selector.id). Mutation en place ; renvoie True si modifiée.

    - propriétés toutes « point de donnée » (POINT_SCOPED_PROPS) : ajoute
      data:[dataViewWildcard] si absent — sinon elles ne suivent pas le
      paramètre de champ ;
    - sinon (propriétés niveau champ, ex. titleContentType, labelDisplayUnits) :
      RETIRE un wildcard pur posé par une version précédente du script — sinon
      Power BI ignore l'entrée et le réglage retombe au défaut. On ne retire
      jamais un `data` plus riche (entrée VALEUR native : wildcard + order) ni
      celui d'une règle CF liée aux données."""
    if not isinstance(entry, dict):
        return False
    sel = entry.get("selector")
    if not isinstance(sel, dict) or "id" not in sel:
        return False
    if _is_point_scoped_only(entry):
        if "data" not in sel:
            sel["data"] = [{"dataViewWildcard": {"matchingOption": 0}}]
            return True
        return False
    if sel.get("data") == _WILDCARD_ONLY and "order" not in sel:
        del sel["data"]                     # réparation (portée champ restaurée)
        return True
    return False


def split_entry_scopes(entry):
    """Sépare une entrée MIXTE d'étiquette de référence selon la portée de ses
    propriétés : les bascules/formats niveau CHAMP (titleContentType, show du
    détail, labelDisplayUnits… — selector {metadata, id} sans wildcard) d'un
    côté, les valeurs POINT DE DONNÉE (POINT_SCOPED_PROPS : titleText, value —
    avec dataViewWildcard) de l'autre. Renvoie 1 ou 2 entrées.

    Nécessaire car Power BI ignore une bascule scopée point de donnée (retour
    au défaut — titre « nom du champ », units « Automatique »… et à la
    SAUVEGARDE suivante Desktop PURGE l'entrée ignorée du fichier, d'où des
    réglages qui « disparaissent ») MAIS ignore une valeur qui n'est PAS scopée
    point de donnée (elle ne suit pas le paramètre de champ). Les deux familles
    ne peuvent donc pas cohabiter dans un même selector. Cas typiques : le
    TITRE {titleContentType, titleText} et le DÉTAIL {show, value} (une mesure
    d'écart en détail). Idempotent : une entrée « pure » est renvoyée telle
    quelle."""
    if not isinstance(entry, dict):
        return [entry]
    props = entry.get("properties")
    sel = entry.get("selector")
    if not isinstance(props, dict) or not isinstance(sel, dict) or "id" not in sel:
        return [entry]
    field_props = {k: v for k, v in props.items() if not _prop_point_scoped(k, v)}
    point_props = {k: v for k, v in props.items() if _prop_point_scoped(k, v)}
    if not field_props or not point_props:
        return [entry]  # déjà pure ; la portée est gérée par ensure_datapoint_scope
    base_sel = {k: v for k, v in sel.items() if k != "data"}
    field_entry = {"properties": field_props, "selector": dict(base_sel)}
    point_sel = dict(base_sel)
    point_sel["data"] = [{"dataViewWildcard": {"matchingOption": 0}}]
    point_entry = {"properties": point_props, "selector": point_sel}
    return [field_entry, point_entry]


def process_visual(path: Path, template: str, targets: list[str], *,
                   entity: str = ENTITY, branches=BRANCHES,
                   verbose: bool = False, dry_run: bool = False, log=print,
                   backup_dir=None, fp_forward=None, fp_reverse=None) -> int:
    """Aligne, dans chaque liste de visual.objects, les KPI cibles sur le KPI
    template : les entrées visant le template sont clonées vers chaque cible,
    et celles que le template ne porte PLUS sont retirées des cibles (miroir).
    Retourne le nombre d'entrées ajoutées, mises à jour ou retirées."""
    data = json.loads(path.read_text(encoding="utf-8"))
    objects = (data.get("visual") or {}).get("objects")
    if not isinstance(objects, dict):
        return 0

    changes = 0

    # KPI gérés, du plus long au plus court : « Average Steps » ne doit pas
    # capter « Average Steps YTD » avant que « Average Steps YTD » (s'il était
    # lui-même une cible) n'ait sa chance. Prefix-safe par construction.
    _managed = sorted(set(targets) | {template}, key=len, reverse=True)

    def _managed_kpi(md):
        """KPI géré visé par ce metadata (Réel ou branche), sinon None."""
        if not md:
            return None
        for kpi in _managed:
            for prefix in (f"{entity}.", ""):
                head = prefix + kpi
                if md == head or md.startswith(head + " "):
                    return kpi
        return None

    def _targets_template(entry) -> bool:
        """L'entrée vise-t-elle une mesure DU KPI template ?

        Le test doit passer par _managed_kpi (plus long KPI géré d'abord), et
        NON par un préfixe de chaîne : si un autre KPI s'appelle « Total Steps
        Goal », « _mesures.Total Steps Goal PY » commence bel et bien par
        « _mesures.Total Steps » — il serait pris pour une déclinaison du
        template. Ses clones, écrits au run précédent, redeviendraient alors
        des SOURCES au run suivant : le nombre d'entrées double à chaque
        passe, et la propagation ne converge jamais."""
        return _managed_kpi(entry_metadata(entry)) == template

    # Le MIROIR (retrait de ce que le template ne porte plus) ne s'applique
    # qu'aux visuels PILOTÉS par le template, c'est-à-dire portant au moins une
    # entrée visant le KPI template. Un visuel qui n'affiche pas le template
    # n'est pas concerné : on n'y touche à rien (garde-fou anti-effacement).
    driven_by_template = any(
        _targets_template(e)
        for entries in objects.values() if isinstance(entries, list)
        for e in entries
    )

    for key, entries in objects.items():
        if not isinstance(entries, list):
            continue

        # Entrées MIXTES des ÉTIQUETTES DE RÉFÉRENCE (titre {titleContentType,
        # titleText}, détail {show, value-mesure}, …) : scinder chaque entrée
        # en une part « champ » et une part « point de donnée » AVANT de
        # propager — les deux portées s'annulent dans un même selector (et
        # Desktop PURGE les entrées à la mauvaise portée à la sauvegarde
        # suivante, d'où des réglages qui « disparaissent »). Restreint aux
        # clés referenceLabel* : ailleurs (referenceLine d'axe…), `value` n'est
        # PAS une propriété point-de-donnée. Idempotent (entrée pure =
        # inchangée) ; répare aussi les entrées combinées héritées.
        if key.startswith("referenceLabel"):
            rebuilt = []
            for e in entries:
                rebuilt.extend(split_entry_scopes(e))
            if rebuilt != entries:
                changes += len(rebuilt) - len(entries) or 1
                entries[:] = rebuilt

        # candidats = toute entrée dont le selector.metadata vise le KPI template
        candidates = [e for e in entries if _targets_template(e)]
        # templates = candidats qui visent une mesure du KPI template, SAUF les
        # couleurs statiques de columnFormatting (gérées par color_matrix_by_kpi).
        # -> inclut CF à base de mesure, reference labels (titre, détail), display
        #    units, couleurs de série d'un graphique (dataPoint, markers…) —
        #    tout ce qui a un selector.metadata.
        template_entries = [
            e for e in candidates
            if not owned_by_color_matrix(key, e)
        ]

        if verbose and candidates:
            log("  [{0} / objects.{1}]".format(path.parent.name, key))
            for e in candidates:
                mark = ("-> IGNORÉ (couleur statique columnFormatting)"
                        if owned_by_color_matrix(key, e) else "-> propagé")
                log("      candidat  {0:<48} {1}".format(entry_metadata(e), mark))

        # normalisation de portée EN PLACE de toutes les entrées du template
        # (ajout du wildcard aux propriétés point-de-donnée, RETRAIT d'un
        # wildcard erroné posé par une version antérieure sur les propriétés
        # niveau champ — ex. labelDisplayUnits, que Power BI ignorait alors)
        for e in template_entries:
            if ensure_datapoint_scope(e):
                changes += 1
                if verbose:
                    log("        * portée normalisée {0}".format(entry_metadata(e)))

        # Le RÉEL (sans branche) du template est MAÎTRE :
        # - ses entrées ne sont JAMAIS réécrites par un clone (sinon une entrée
        #   de branche périmée d'un run précédent écrase la modif fraîche de
        #   l'utilisateur — vu avec les display units) ;
        # - une entrée de BRANCHE du template ne sert de source QUE si aucune
        #   entrée Réel n'a la même signature (branche seule formatée).
        def _reel_key(e):
            # même forme que entry_key (metadata ramené au Réel + id + order +
            # props) — sinon la comparaison `_reel_key not in reel_keys` porte
            # sur des tuples de tailles différentes et ne matche jamais
            md = entry_metadata(e)
            b = detect_branch(md, template, branches, entity, fp_reverse)
            base_md = swap_kpi_branch(md, template, b, template, "", entity,
                                      fp_forward, fp_reverse)
            sid, order = _selector_id_order(e)
            props = ()
            if isinstance(e, dict) and isinstance(e.get("properties"), dict):
                props = tuple(sorted(e["properties"].keys()))
            return (base_md, sid, order, props)

        reel_keys = {entry_key(e) for e in template_entries
                     if not detect_branch(entry_metadata(e), template, branches, entity, fp_reverse)}
        sources = [e for e in template_entries
                   if not detect_branch(entry_metadata(e), template, branches, entity, fp_reverse)
                   or _reel_key(e) not in reel_keys]

        # signatures que le visuel DOIT porter à la fin : celles du template
        # (il garde tout ce qu'il porte) + tous les clones générés ci-dessous.
        # Tout le reste, sur un KPI géré, est une relique -> retiré (miroir).
        expected = {entry_key(e) for e in template_entries}

        for tpl_entry in sources:
            # branche de l'entrée template (ex. Réel ou YTD)
            src_branch = detect_branch(entry_metadata(tpl_entry), template, branches, entity, fp_reverse)
            # Une source RÉEL irrigue toutes les branches. Une source « branche
            # seule » (aucune entrée Réel de même signature — ex. le style des
            # marqueurs de la ligne YTD sur un graphique qui ne trace QUE des
            # mesures YTD) décrit un état propre à cette branche : elle reste
            # DANS SA BRANCHE. Sans ça, elle recréerait des entrées sur les
            # faces Réel — dont celle du template qu'on vient de supprimer.
            dst_branches = ([""] + list(branches)) if not src_branch else [src_branch]
            # on génère pour chaque KPI cible ET chaque branche visée,
            # en sautant l'entrée template elle-même (même KPI + même branche)
            for kpi in targets:
                for dst_branch in dst_branches:
                    if kpi == template and dst_branch == src_branch:
                        continue
                    clone = swap_tree_branch(tpl_entry, template, src_branch, kpi, dst_branch,
                                             entity, fp_forward, fp_reverse)
                    ensure_datapoint_scope(clone)  # même portée que la source normalisée
                    clone_md = entry_metadata(clone)
                    clone_key = entry_key(clone)
                    expected.add(clone_key)
                    if kpi == template and clone_key in reel_keys:
                        continue       # le Réel du template n'est jamais réécrit

                    # dédup par (metadata + propriétés) : une entrée CF et une
                    # entrée display-units sur la MÊME mesure coexistent
                    existing = next(
                        (i for i, e in enumerate(entries)
                         if entry_key(e) == clone_key),
                        None,
                    )
                    if existing is None:
                        entries.append(clone)
                        changes += 1
                        if verbose: log("        + {0}".format(clone_md))
                    elif entries[existing] != clone:
                        entries[existing] = clone
                        changes += 1
                        if verbose: log("        ~ {0}".format(clone_md))

        # ---- MIROIR : retirer des cibles ce que le template ne porte plus ---
        # Sans ça la propagation n'était qu'additive : supprimer un réglage sur
        # le KPI template (retirer l'image d'une carte, par exemple) le laissait
        # en place sur tous les autres KPI — et une relique de branche finissait
        # même par le RECRÉER sur le template. On ne touche qu'aux entrées
        # visant un KPI géré ; les couleurs statiques (color_matrix_by_kpi) et
        # tout selector sans metadata (« default », règles globales) sont hors
        # jeu, comme à la propagation.
        if driven_by_template:
            stale = [e for e in entries
                     if not owned_by_color_matrix(key, e)
                     and _managed_kpi(entry_metadata(e)) is not None
                     and entry_key(e) not in expected]
            if stale:
                for e in stale:
                    log("      - {0} / {1} : retiré (absent du template)".format(
                        key, entry_metadata(e)))
                stale_ids = {id(e) for e in stale}
                entries[:] = [e for e in entries if id(e) not in stale_ids]
                changes += len(stale)

    if changes and not dry_run:
        if backup_dir is not None:
            # nom historique <page>_<visuel>.json conservé ; le manifeste de la
            # session note le chemin d'origine, ce qui rend la restauration
            # mécanique (cf. backup_restore.py)
            backup_dir.save(
                path, name=f"{path.parents[2].name}_{path.parent.name}.json")
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return changes


def propagate(report_dir, template_kpi, *, branches=BRANCHES, targets=None,
              entity: str = ENTITY, field_parameter: str = FIELD_PARAMETER,
              dry_run: bool = False, verbose: bool = False, log=print) -> int:
    """Propage le formatage conditionnel du KPI template vers tous les KPI (et
    toutes les branches) dans les visual.json du rapport. Retourne le nombre
    total d'entrées écrites. Point d'entrée commun CLI (main) et UI (Atelier) :
    `log` reçoit chaque ligne (print par défaut, redirigé vers la console UI)."""
    report_dir = Path(report_dir)
    branches = list(branches)
    semantic_dir = Path(str(report_dir).replace(".Report", ".SemanticModel"))
    if not targets:
        targets = kpis_from_parameter(semantic_dir, field_parameter)

    # tables (KPI, Calcul, Branche) <-> mesure, lues du paramètre de champ :
    # permettent de propager une CIBLE vers un autre KPI/branche sans parser son
    # nom (« Weight cible YTD » -> « Body Fat % cible YTD », pas « … YTD cible »).
    fp_forward, fp_reverse = read_fp_maps(semantic_dir, field_parameter)
    if fp_reverse:
        log(f"Paramètre de champ : {len(fp_reverse)} mesure(s) mappée(s) "
            f"(KPI/Calcul/Branche).")

    log(f"KPI template : {template_kpi}")
    log(f"KPI cibles   : {', '.join(k for k in targets if k != template_kpi)}")
    if dry_run:
        log("*** DRY_RUN : aucun fichier modifié (diagnostic seulement) ***")

    # la propagation RETIRE maintenant ce que le template ne porte plus :
    # copie de chaque visual.json modifié avant écriture (undo = le recopier)
    backup_dir = None
    if not dry_run:
        backup_dir = br.BackupSession(report_dir.parent / "_propagate_backups",
                                      "Propagation", report_dir.parent)
        log(f"Sauvegardes  : {backup_dir.dir} (visuels modifiés seulement)")

    total = 0
    n_visuals = 0
    for visual_json in sorted(report_dir.glob("definition/pages/*/visuals/*/visual.json")):
        n = process_visual(visual_json, template_kpi, targets, entity=entity,
                           branches=branches, verbose=verbose, dry_run=dry_run, log=log,
                           backup_dir=backup_dir, fp_forward=fp_forward, fp_reverse=fp_reverse)
        if n:
            page = visual_json.parents[2].name
            log(f"  page {page} / visuel {visual_json.parent.name} : {n} entrée(s)")
            total += n
            n_visuals += 1

    if backup_dir is not None:
        # manifeste : d'où venait chaque copie -> restauration en un clic
        backup_dir.close(f"{total} entrée(s) sur {n_visuals} visuel(s), "
                         f"template {template_kpi}")

    log("Aucun changement." if total == 0 else f"Terminé : {total} entrée(s) écrites.")
    return total


def main() -> None:
    propagate(REPORT_DIR, TEMPLATE_KPI, branches=BRANCHES, targets=TARGET_KPIS,
              entity=ENTITY, field_parameter=FIELD_PARAMETER,
              dry_run=DRY_RUN, verbose=VERBOSE)


if __name__ == "__main__":
    main()
