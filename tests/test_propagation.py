# -*- coding: utf-8 -*-
"""Tests de la propagation (propagate_cf) — à lancer Desktop fermé :

    py tests\\test_propagation.py

Travaille TOUJOURS sur une copie du projet dans %TEMP%, jamais sur le rapport
vivant. Sortie : une ligne par vérification, code de sortie 0 si tout passe.

Vit dans le dossier du projet (et non dans un dossier temporaire) pour survivre
aux purges et partir dans le zip de travail.
"""

from __future__ import annotations

import copy
import json
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
import propagate_cf as pc                                    # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(PBI)


PROJ = "Fitbit"
TPL = "Total Steps"

_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def projet_copie(nom):
    """Copie fraîche du .Report + .SemanticModel dans un dossier temporaire."""
    c = Path(tempfile.gettempdir()) / ("pbidouille_" + nom)
    rmtree(c)
    c.mkdir(parents=True)
    for suffixe in (".Report", ".SemanticModel"):
        shutil.copytree(PBI / (PROJ + suffixe), c / (PROJ + suffixe))
    return c


def entrees(report_dir):
    """Nombre total d'entrées de formatage dans tous les visual.json."""
    n = 0
    for vj in report_dir.glob("definition/pages/*/visuals/*/visual.json"):
        objs = (json.loads(vj.read_text(encoding="utf-8")).get("visual") or {}).get("objects") or {}
        n += sum(len(v) for v in objs.values() if isinstance(v, list))
    return n


def kpis(c):
    return pc.kpis_from_parameter(c / (PROJ + ".SemanticModel"), "P_Indicateurs_parCalcul")


def cloner_kpi(c, base_kpi, nouveau_kpi):
    """Donne au KPI `nouveau_kpi` les MESURES de `base_kpi` dans le modele.

    La propagation refuse (a raison) d'ecrire une reference vers une mesure qui
    n'existe pas : un KPI cible sans mesures n'est donc pas un cas realiste.
    Pour eprouver le KPI homonyme, il lui faut vraiment ses mesures — sinon le
    test ne prouverait rien, toutes les entrees etant ecartees en silence.
    """
    tmdl = (c / (PROJ + ".SemanticModel") / "definition" / "tables"
            / "_mesures.tmdl")
    texte = tmdl.read_text(encoding="utf-8")
    noms = {m.group(1) or m.group(2)
            for m in pc.MEASURE_NAME_RE.finditer(texte)}
    ajouts = []
    for n in sorted(x for x in noms if x):
        if n != base_kpi and not n.startswith(base_kpi + " "):
            continue
        neuf = nouveau_kpi + n[len(base_kpi):]
        if neuf not in noms:
            ajouts.append("\tmeasure '" + neuf.replace("'", "''") + "' = 0\n"
                          "\t\tlineageTag: test-" + str(len(ajouts)) + "\n")
    if not ajouts:
        return 0
    bloc = "\n".join(ajouts) + "\n"
    coupe = texte.find("\tpartition ")        # avant la partition : TMDL valide
    texte = (texte[:coupe] + bloc + texte[coupe:]) if coupe != -1 else texte + bloc
    tmdl.write_text(texte, encoding="utf-8")
    return len(ajouts)


# ===================================================================== 1
print("1. idempotence : une 2e propagation ne doit RIEN écrire")
c = projet_copie("idem")
R = c / (PROJ + ".Report")
n1 = pc.propagate(R, TPL, log=lambda *_: None)
t1 = entrees(R)
n2 = pc.propagate(R, TPL, log=lambda *_: None)
t2 = entrees(R)
n3 = pc.propagate(R, TPL, log=lambda *_: None)
check(f"2e passe = 0 changement (obtenu {n2})", n2 == 0)
check(f"3e passe = 0 changement (obtenu {n3})", n3 == 0)
check(f"le nombre d'entrées ne bouge plus ({t1} -> {t2})", t1 == t2)
rmtree(c)

# ===================================================================== 2
print("2. RÉGRESSION : un KPI dont le nom COMMENCE par celui du template")
# « Total Steps Goal » contient « Total Steps » : ses entrées propagées ne
# doivent PAS être reprises comme sources au run suivant, sinon le nombre
# d'entrées double à chaque passe et la propagation ne converge jamais.
c = projet_copie("prefixe")
R = c / (PROJ + ".Report")
n_ajout = cloner_kpi(c, TPL, TPL + " Goal")   # le KPI homonyme a ses mesures
check("le KPI homonyme a bien des mesures dans le modele", n_ajout > 0)
cibles = kpis(c) + [TPL + " Goal"]
suite = []
for _ in range(4):
    suite.append(pc.propagate(R, TPL, branches=["YTD"], targets=cibles,
                              log=lambda *_: None))
print("   changements par passe :", suite)
check("la propagation CONVERGE (passes 2+ à zéro)", suite[1:] == [0, 0, 0])
check("aucune explosion du nombre d'entrées", entrees(R) < 200)
rmtree(c)

# ===================================================================== 3
print("3. le KPI homonyme reste une CIBLE normale")
c = projet_copie("homonyme")
R = c / (PROJ + ".Report")
cloner_kpi(c, TPL, TPL + " Goal")
cibles = kpis(c) + [TPL + " Goal"]
pc.propagate(R, TPL, branches=["YTD"], targets=cibles, log=lambda *_: None)
mds = set()
for vj in R.glob("definition/pages/*/visuals/*/visual.json"):
    objs = (json.loads(vj.read_text(encoding="utf-8")).get("visual") or {}).get("objects") or {}
    for v in objs.values():
        if isinstance(v, list):
            for e in v:
                md = pc.entry_metadata(e)
                if md:
                    mds.add(md)
check("des entrées ont bien été créées pour « Total Steps Goal »",
      any(m.startswith("_mesures." + TPL + " Goal") for m in mds))
check("et pour les autres KPI", any(m.startswith("_mesures.Weight") for m in mds))
rmtree(c)

# ===================================================================== 4
print("4. miroir : ce que le template ne porte plus est retiré des cibles")
c = projet_copie("miroir")
R = c / (PROJ + ".Report")
pc.propagate(R, TPL, log=lambda *_: None)          # état stable
# on injecte des entrées bidon sur des KPI gérés, comme en produirait un
# emballement : elles doivent disparaître à la propagation suivante
pilote = None
for vj in sorted(R.glob("definition/pages/*/visuals/*/visual.json")):
    d = json.loads(vj.read_text(encoding="utf-8"))
    objs = (d.get("visual") or {}).get("objects") or {}
    for k, lst in objs.items():
        if not isinstance(lst, list):
            continue
        for e in lst:
            md = pc.entry_metadata(e)
            if md and md.startswith("_mesures." + TPL) and not pc.owned_by_color_matrix(k, e):
                pilote, cle, modele, data = vj, k, e, d
                break
        if pilote:
            break
    if pilote:
        break
avant = entrees(R)
for faux in ["_mesures.Weight Bidon", "_mesures.Body Fat % Bidon"]:
    junk = copy.deepcopy(modele)
    junk.setdefault("selector", {})["metadata"] = faux
    data["visual"]["objects"][cle].append(junk)
pilote.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
check("les fausses entrées sont bien en place", entrees(R) == avant + 2)
pc.propagate(R, TPL, log=lambda *_: None)
check("le miroir les a retirées", entrees(R) == avant)
rmtree(c)

# ===================================================================== 5
print("5. cibles : la branche se place via le paramètre de champ")
fwd, rev = pc.read_fp_maps(PBI / (PROJ + ".SemanticModel"), "P_Indicateurs_parCalcul")
check("le paramètre de champ est lisible", len(rev) > 0)


def swap(v, dk, db):
    return pc.swap_kpi_branch(v, "Weight", "", dk, db, "_mesures", fwd, rev)


faux_fwd = dict(fwd)
faux_rev = dict(rev)
for k in ("Weight", "Body Fat %"):
    faux_fwd[(k, "Cible", "Réel")] = k + " cible"
    faux_fwd[(k, "Cible", "YTD")] = k + " cible YTD"
    faux_rev[k + " cible"] = (k, "Cible", "Réel")
    faux_rev[k + " cible YTD"] = (k, "Cible", "YTD")
got = pc.swap_kpi_branch("_mesures.Weight cible", "Weight", "", "Body Fat %", "YTD",
                         "_mesures", faux_fwd, faux_rev)
check("Weight cible -> Body Fat % cible YTD (branche APRÈS « cible »)",
      got == "_mesures.Body Fat % cible YTD")
check("PAS le nom cassé « Body Fat % YTD cible »", "YTD cible" not in got)
check("un KPI ordinaire reste correct",
      swap("_mesures.Weight PY", "Body Fat %", "YTD") == "_mesures.Body Fat % YTD PY")

# ===================================================================== 6
print("6. garde-fou : un visuel SANS entrée du template n'est pas touché")
c = projet_copie("garde")
R = c / (PROJ + ".Report")
pc.propagate(R, TPL, log=lambda *_: None)
sans_tpl = []
for vj in sorted(R.glob("definition/pages/*/visuals/*/visual.json")):
    objs = (json.loads(vj.read_text(encoding="utf-8")).get("visual") or {}).get("objects") or {}
    a_tpl = any(
        (pc.entry_metadata(e) or "").startswith("_mesures." + TPL)
        for v in objs.values() if isinstance(v, list) for e in v)
    n = sum(len(v) for v in objs.values() if isinstance(v, list))
    if not a_tpl and n:
        sans_tpl.append((vj, vj.read_bytes()))
check("des visuels sans entrée du template existent", bool(sans_tpl))
pc.propagate(R, TPL, log=lambda *_: None)
check("ils sont restés identiques octet pour octet",
      all(vj.read_bytes() == avant_octets for vj, avant_octets in sans_tpl))
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
