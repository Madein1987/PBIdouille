# -*- coding: utf-8 -*-
"""Une mesure COMMUNE aux branches ne doit pas se voir coller un suffixe.

    py tests\\test_mesure_commune.py

Cas rapporte : un titre commun au Reel et au YTD — une seule mesure, sans
variante « … YTD ». La propagation lui collait quand meme le suffixe de la
branche et ecrivait « Total Steps YTD titre », qui n'existe pas : le visuel
perdait l'attribut.

La regle posee : la propagation n'ecrit JAMAIS une reference vers une mesure
absente du modele. Elle descend une cascade d'intentions —

  1. la variante de la branche visee (« Weight YTD ») ;
  2. la mesure du MEME KPI sans branche (« Weight titre ») : un titre par KPI,
     commun a ses deux branches ;
  3. la mesure d'origine, inchangee : un titre commun a tout le rapport.

Sans modele lisible, l'ancien comportement est conserve — on ne bloque pas.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(PBI, PROJET_DEMO)

import propagate_cf as pc                          # noqa: E402

PROJ = PROJET_DEMO
TPL = "Total Steps"
ENT = "_mesures"
TITRE = TPL + " titre"                             # commune : pas de « … YTD »
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def projet_copie(nom):
    c = Path(tempfile.gettempdir()) / ("pbid_commune_" + nom)
    rmtree(c)
    c.mkdir(parents=True)
    for suffixe in (".Report", ".SemanticModel"):
        shutil.copytree(PBI / (PROJ + suffixe), c / (PROJ + suffixe))
    return c


def tmdl_mesures(c):
    return (c / (PROJ + ".SemanticModel") / "definition" / "tables"
            / "_mesures.tmdl")


def ajouter_mesures(c, *noms):
    """Cree des mesures dans le modele (avant la partition : TMDL valide)."""
    p = tmdl_mesures(c)
    texte = p.read_text(encoding="utf-8")
    bloc = "".join("\tmeasure '" + n.replace("'", "''") + "' = 0\n"
                   "\t\tlineageTag: commune-" + str(i) + "\n\n"
                   for i, n in enumerate(noms))
    coupe = texte.find("\tpartition ")
    p.write_text(texte[:coupe] + bloc + texte[coupe:] if coupe != -1
                 else texte + bloc, encoding="utf-8")


def poser_entree_titre(report_dir) -> int:
    """Ajoute, dans les visuels qui portent deja du template, une entree dont
    la mesure visee est le TITRE commun. C'est le geste de l'usager : il pose
    la meme mesure sur les deux faces."""
    poses = 0
    for vj in sorted(report_dir.glob("definition/pages/*/visuals/*/visual.json")):
        data = json.loads(vj.read_text(encoding="utf-8"))
        objects = (data.get("visual") or {}).get("objects")
        if not isinstance(objects, dict):
            continue
        touche = False
        for liste in objects.values():
            if not isinstance(liste, list):
                continue
            modele = next(
                (e for e in liste
                 if (pc.entry_metadata(e) or "").startswith(ENT + "." + TPL)
                 and not pc.is_static_color(e)), None)
            if modele is None:
                continue
            neuf = copy.deepcopy(modele)
            neuf["selector"]["metadata"] = ENT + "." + TITRE
            liste.append(neuf)
            touche = True
            break
        if touche:
            vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
            poses += 1
    return poses


def metadatas(report_dir) -> set:
    vus = set()
    for vj in report_dir.glob("definition/pages/*/visuals/*/visual.json"):
        objs = (json.loads(vj.read_text(encoding="utf-8")).get("visual")
                or {}).get("objects") or {}
        for liste in objs.values():
            if isinstance(liste, list):
                for e in liste:
                    md = pc.entry_metadata(e)
                    if md:
                        vus.add(md)
    return vus


# ===================================================================== 1
print("1. la cascade d'intentions, mesure par mesure")
fp_rev = {"Total Steps": ("Total Steps", "Réel", ""),
          "Total Steps YTD": ("Total Steps", "Réel", "YTD"),
          "Weight": ("Weight", "Réel", ""),
          "Weight YTD": ("Weight", "Réel", "YTD")}
fp_fwd = {(k, calc, b): m for m, (k, calc, b) in fp_rev.items()}


def swap(modele, valeur, dst_kpi, dst_branch, communes=None):
    return pc.swap_kpi_branch(valeur, TPL, "", dst_kpi, dst_branch, ENT,
                              fp_fwd, fp_rev, modele, communes)


par_kpi = set(fp_rev) | {TITRE, "Weight titre"}
check("titre par KPI : le YTD du meme KPI garde la mesure commune",
      swap(par_kpi, ENT + "." + TITRE, TPL, "YTD") == ENT + "." + TITRE)
check("titre par KPI : un autre KPI prend SON titre (Reel)",
      swap(par_kpi, ENT + "." + TITRE, "Weight", "") == ENT + ".Weight titre")
check("titre par KPI : … et le meme en YTD (pas de « Weight YTD titre »)",
      swap(par_kpi, ENT + "." + TITRE, "Weight", "YTD") == ENT + ".Weight titre")
check("la mesure de BASE, elle, prend bien la branche",
      swap(par_kpi, ENT + "." + TPL, "Weight", "YTD") == ENT + ".Weight YTD")

global_seul = set(fp_rev) | {TITRE}
com: set = set()
check("titre unique pour tout : garde tel quel sur un autre KPI",
      swap(global_seul, ENT + "." + TITRE, "Weight", "YTD", com)
      == ENT + "." + TITRE)
check("… et c'est signale comme commune", com == {ENT + "." + TITRE})
check("sans modele connu : ancien comportement (aucune verification)",
      swap(None, ENT + "." + TITRE, TPL, "YTD") == ENT + "." + TPL + " YTD titre")

# Cas rapporte : le parametre de champ n'a PAS de ligne « Reel » pour le KPI
# vise sous ce Calcul, mais il a bien sa ligne YTD. La cascade s'arretait alors
# aux seuls candidats issus du parametre, sans jamais tenter le repli par le
# NOM — et le titre du KPI TEMPLATE restait sur les faces YTD de tous les
# autres KPI. Les deux familles de candidats sont desormais tentees.
fp_rev2 = {"KPI un": ("KPI un", "Réel", ""),
           "KPI un YTD": ("KPI un", "Réel", "YTD"),
           "KPI deux YTD": ("KPI deux", "Réel", "YTD")}     # pas de ligne Réel
fp_fwd2 = {(k, calc, b): m for m, (k, calc, b) in fp_rev2.items()}
modele2 = set(fp_rev2) | {"KPI un titre", "KPI deux titre", "KPI deux"}


def swap2(valeur, dst_kpi, dst_branch):
    return pc.swap_kpi_branch(valeur, "KPI un", "", dst_kpi, dst_branch, ENT,
                              fp_fwd2, fp_rev2, modele2, None)


for dst, br in (("KPI deux", ""), ("KPI deux", "YTD"), ("KPI un", "YTD")):
    obtenu = swap2(ENT + ".KPI un titre", dst, br)
    check(f"parametre incomplet — {dst} / {br or 'Réel'} prend SON titre",
          obtenu == ENT + "." + dst + " titre")
check("… et la mesure de base garde bien sa branche",
      swap2(ENT + ".KPI un", "KPI deux", "YTD") == ENT + ".KPI deux YTD")

# ===================================================================== 2
print("2. de bout en bout : un titre commun a TOUT le rapport")
c = projet_copie("global")
R = c / (PROJ + ".Report")
ajouter_mesures(c, TITRE)                    # une seule, sans variante
connues = pc.measures_of_model(c / (PROJ + ".SemanticModel"))
check("la mesure commune est dans le modele", TITRE in connues)
check("… et sa variante YTD n'existe PAS", TPL + " YTD titre" not in connues)
poses = poser_entree_titre(R)
check("des entrees de titre ont ete posees dans le rapport", poses > 0)

logs: list = []
pc.propagate(R, TPL, branches=["YTD"], log=logs.append)
vus = metadatas(R)
inventees = sorted(m for m in vus if m.endswith(" titre")
                   and m[len(ENT) + 1:] not in connues)
check("AUCUNE mesure de titre inventee", not inventees)
if inventees:
    print("      inventees :", inventees[:5])
check("le titre commun est bien present", ENT + "." + TITRE in vus)
check("le journal signale les mesures communes",
      any("COMMUNES" in l for l in logs))
check("… et nomme celle-ci", any(TITRE in l for l in logs))

print("   la propagation reste idempotente")
n2 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("2e passe = 0 changement (obtenu " + str(n2) + ")", n2 == 0)
rmtree(c)

# ===================================================================== 3
print("3. de bout en bout : un titre PAR KPI, commun a ses deux branches")
c = projet_copie("parkpi")
R = c / (PROJ + ".Report")
autres = [k for k in pc.kpis_from_parameter(c / (PROJ + ".SemanticModel"),
                                            "P_Indicateurs_parCalcul")
          if k != TPL]
check("le modele de demo a d'autres KPI", bool(autres))
ajouter_mesures(c, TITRE, *[k + " titre" for k in autres])
connues = pc.measures_of_model(c / (PROJ + ".SemanticModel"))
poser_entree_titre(R)
pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
vus = metadatas(R)

inventees = sorted(m for m in vus if m.endswith(" titre")
                   and m[len(ENT) + 1:] not in connues)
check("AUCUNE mesure de titre inventee", not inventees)
if inventees:
    print("      inventees :", inventees[:5])
attendu = {ENT + "." + k + " titre" for k in autres} | {ENT + "." + TITRE}
check("chaque KPI a recu SON titre", attendu <= vus)
check("jamais de « <KPI> YTD titre »",
      not any(" YTD titre" in m for m in vus))
n2 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("idempotent (2e passe = 0, obtenu " + str(n2) + ")", n2 == 0)
rmtree(c)

# ===================================================================== 4
print("4. les entrees MORTES d'un run precedent sont-elles nettoyees ?")
# c'est la situation reelle : le rapport porte deja des « … YTD titre »
# inventes avant la correction. Relancer doit les retirer (miroir).
c = projet_copie("nettoyage")
R = c / (PROJ + ".Report")
ajouter_mesures(c, TITRE)
poser_entree_titre(R)

import propagate_cf as _pc_sale                    # noqa: E402
vrai = _pc_sale.measures_of_model
_pc_sale.measures_of_model = lambda *a, **k: set()   # l'ANCIEN comportement
pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
_pc_sale.measures_of_model = vrai

connues = pc.measures_of_model(c / (PROJ + ".SemanticModel"))
mortes_avant = sorted(m for m in metadatas(R) if m.endswith(" titre")
                      and m[len(ENT) + 1:] not in connues)
check("des entrees mortes ont bien ete fabriquees (etat d'avant)",
      bool(mortes_avant))
print("      exemple :", mortes_avant[:2])

pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
mortes_apres = sorted(m for m in metadatas(R) if m.endswith(" titre")
                      and m[len(ENT) + 1:] not in connues)
check("relancer les RETIRE toutes (miroir)", not mortes_apres)
if mortes_apres:
    print("      restantes :", mortes_apres[:5])
check("et le titre commun est toujours la", ENT + "." + TITRE in metadatas(R))
n2 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("puis c'est stable (0 changement, obtenu " + str(n2) + ")", n2 == 0)
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
