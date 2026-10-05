# -*- coding: utf-8 -*-
"""Propagation par GROUPES : chaque famille de KPI a son propre gabarit.

    py tests\\test_groupes_propagation.py

Aucun KPI ne porte tous les attributs du rapport : il y a plusieurs familles,
chacune avec son jeu. Le gabarit d'un groupe EST la declaration de son jeu, donc
il suffit de lancer la propagation une fois par groupe.

Ce qui rend ca possible, et que ce fichier verifie :

  · ISOLATION — une passe de groupe ne lit ni n'efface les entrees des autres
    groupes, MEME dans le meme visuel. C'est `targets` qui borne le perimetre
    d'ecriture (`_portee` dans process_visual) ;
  · le DECOUPAGE des noms reste global. `_managed` doit contenir TOUS les KPI,
    sinon un KPI d'un autre groupe dont le nom commence par celui du gabarit
    (« Total Steps Goal » face a « Total Steps ») serait pris pour une
    declinaison du gabarit, et ses clones redeviendraient des sources : les
    entrees doublent a chaque passe.

Les deux se contredisent si on les confond dans un seul ensemble — c'est
exactement le piege que la section 3 traque.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

FIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO)

import backup_restore as br                       # noqa: E402
import propagate_cf as pc                         # noqa: E402

PROJ = PROJET_DEMO
ENT = "_mesures"
FP = "P_Indicateurs_parCalcul"
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def copie(nom):
    c = Path(tempfile.gettempdir()) / ("pbid_groupes_" + nom)
    rmtree(c)
    c.mkdir(parents=True)
    for s in (".Report", ".SemanticModel"):
        shutil.copytree(FIT / (PROJ + s), c / (PROJ + s))
    return c


def kpis_de(c):
    return pc.kpis_from_parameter(c / (PROJ + ".SemanticModel"), FP)


# ===================================================================== 1
print("1. lecture et validation du fichier de groupes")
tmp = Path(tempfile.gettempdir()) / "pbid_groupes_fichier"
rmtree(tmp)
tmp.mkdir(parents=True)

check("fichier absent = aucun groupe (on retombe sur le gabarit unique)",
      pc.read_groupes(tmp / "pas_la.json") == [])
check("chemin vide = idem", pc.read_groupes("") == [])
(tmp / "casse.json").write_text("pas du json", encoding="utf-8")
check("JSON casse = aucun groupe, pas d'exception",
      pc.read_groupes(tmp / "casse.json") == [])
(tmp / "ok.json").write_text(json.dumps({"groupes": [
    {"nom": "Standard", "gabarit": "A"},
    {"gabarit": "C", "kpis": ["C", "D"]},
    {"nom": "sans gabarit", "kpis": ["E"]},
]}, ensure_ascii=False), encoding="utf-8")
lus = pc.read_groupes(tmp / "ok.json")
check("les groupes valides sont lus", len(lus) == 2)
check("kpis absent = liste vide (groupe par defaut)", lus[0]["kpis"] == [])
check("nom absent = le gabarit sert de nom", lus[1]["nom"] == "C")
check("un groupe sans gabarit est ignore",
      all(g["gabarit"] for g in lus))

CONNUS = ["A", "B", "C", "D", "Total Steps", "Total Steps Goal"]
resolus = pc.resoudre_groupes(
    [{"nom": "Std", "gabarit": "A", "kpis": []},
     {"nom": "Autre", "gabarit": "C", "kpis": ["C", "D"]}], CONNUS, lambda *_: None)
par_nom = {g["nom"]: g for g in resolus}
check("le groupe explicite garde ses KPI", par_nom["Autre"]["kpis"] == ["C", "D"])
check("le groupe par defaut ramasse le reste",
      par_nom["Std"]["kpis"] == ["A", "B", "Total Steps", "Total Steps Goal"])
resolus = pc.resoudre_groupes(
    [{"nom": "G", "gabarit": "C", "kpis": ["D"]}], CONNUS, lambda *_: None)
check("le gabarit est ajoute d'office a son groupe",
      "C" in resolus[0]["kpis"])

journal: list = []
pc.resoudre_groupes([{"nom": "G", "gabarit": "A", "kpis": ["A", "ZZZ"]}],
                    CONNUS, journal.append)
check("un KPI inconnu est signale et ignore",
      any("ZZZ" in l for l in journal))
journal = []
pc.resoudre_groupes([{"nom": "G", "gabarit": "A", "kpis": ["A", "B"]}],
                    CONNUS, journal.append)
check("les KPI dans aucun groupe sont signales",
      any("aucun groupe" in l and "C" in l for l in journal))

for mauvais, quoi, mot in (
    ([{"nom": "X", "gabarit": "ZZZ", "kpis": []}],
     "gabarit inconnu", "introuvable"),
    ([{"nom": "X", "gabarit": "A", "kpis": []},
      {"nom": "Y", "gabarit": "B", "kpis": []}],
     "deux groupes par defaut", "défaut"),
    ([{"nom": "X", "gabarit": "A", "kpis": ["A", "C"]},
      {"nom": "Y", "gabarit": "B", "kpis": ["B", "C"]}],
     "KPI revendique deux fois", "deux groupes"),
):
    try:
        pc.resoudre_groupes(mauvais, CONNUS, lambda *_: None)
        check(quoi + " : refuse", False)
    except SystemExit as e:
        check(quoi + " : refuse avec un message clair", mot in str(e))
rmtree(tmp)

# ===================================================================== 2
print("2. ISOLATION : une passe de groupe ne touche pas aux autres")
c = copie("isolation")
R = c / (PROJ + ".Report")
KPIS = kpis_de(c)
print("   KPI du modele :", KPIS)
GA, GB = KPIS[0], KPIS[1]                  # les deux gabarits
AUTRE_A, AUTRE_B = KPIS[2], KPIS[3]        # un KPI de plus dans chaque groupe
GROUPES = [{"nom": "A", "gabarit": GA, "kpis": [GA, AUTRE_A]},
           {"nom": "B", "gabarit": GB, "kpis": [GB, AUTRE_B]}]
check("deux groupes disjoints, gabarits distincts", GA != GB)


def entree_marqueur(kpi, marqueur):
    """Une entree reconnaissable : son nom de propriete sert de marqueur, donc
    on voit d'un coup d'oeil de quel gabarit un attribut vient."""
    return {
        "properties": {marqueur: {"expr": {"Literal": {"Value": "1D"}}}},
        "selector": {"metadata": ENT + "." + kpi,
                     "data": [{"dataViewWildcard": {"matchingOption": 0}}]},
    }


def poser(kpi, marqueur):
    """Pose l'entree dans le 1er visuel qui porte deja des entrees de ce KPI."""
    for vj in sorted(R.glob("definition/pages/*/visuals/*/visual.json")):
        data = json.loads(vj.read_text(encoding="utf-8"))
        objets = (data.get("visual") or {}).get("objects")
        if not isinstance(objets, dict):
            continue
        for cle, liste in objets.items():
            if not isinstance(liste, list):
                continue
            if not any((pc.entry_metadata(e) or "").startswith(ENT + "." + kpi)
                       for e in liste):
                continue
            liste.append(entree_marqueur(kpi, marqueur))
            vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
            return vj, cle
    return None, None


vjA, cleA = poser(GA, "marqueurA")
vjB, cleB = poser(GB, "marqueurB")
check("les deux marqueurs sont poses", vjA is not None and vjB is not None)
check("… et dans le MEME visuel (c'est tout l'enjeu)", vjA == vjB)


def poser_dans(vj, cle, kpi, marqueur):
    """Pose l'entree dans un visuel et un objet PRECIS — pour un KPI tout neuf,
    qui n'a encore aucune entree nulle part."""
    data = json.loads(vj.read_text(encoding="utf-8"))
    ((data.get("visual") or {}).get("objects") or {})[cle].append(
        entree_marqueur(kpi, marqueur))
    vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                  encoding="utf-8")


def porteurs(marqueur) -> set:
    """Les KPI (selector.metadata) des entrees portant ce marqueur."""
    out = set()
    for vj in R.glob("definition/pages/*/visuals/*/visual.json"):
        objets = (json.loads(vj.read_text(encoding="utf-8")).get("visual")
                  or {}).get("objects") or {}
        for liste in objets.values():
            if isinstance(liste, list):
                for e in liste:
                    props = e.get("properties") if isinstance(e, dict) else None
                    if isinstance(props, dict) and marqueur in props:
                        out.add(pc.entry_metadata(e))
    return out


def instantane() -> dict:
    return {str(vj): vj.read_text(encoding="utf-8")
            for vj in R.glob("definition/pages/*/visuals/*/visual.json")}


avant_b = porteurs("marqueurB")
check("au depart, marqueurB n'est que sur son gabarit",
      avant_b == {ENT + "." + GB})

# la passe du groupe A SEULE
pc.propagate(R, GA, branches=["YTD"], targets=[GA, AUTRE_A],
             log=lambda *_: None)
apres_b = porteurs("marqueurB")
check("la passe A n'a PAS propage marqueurB", apres_b == avant_b)
check("la passe A n'a pas efface l'entree du groupe B",
      (ENT + "." + GB) in apres_b)
porte_a = porteurs("marqueurA")
check("la passe A a bien servi SON groupe",
      {ENT + "." + GA, ENT + "." + AUTRE_A} <= porte_a)
check("… et n'a rien pose sur les KPI du groupe B",
      not any(m in porte_a for m in (ENT + "." + GB, ENT + "." + AUTRE_B)))

# puis la passe complete, par groupes
logs: list = []
pc.propagate_groupes(R, GROUPES, branches=["YTD"], log=logs.append)
pa, pb = porteurs("marqueurA"), porteurs("marqueurB")
check("groupe A : ses KPI ont marqueurA",
      {ENT + "." + GA, ENT + "." + AUTRE_A} <= pa)
check("groupe B : ses KPI ont marqueurB",
      {ENT + "." + GB, ENT + "." + AUTRE_B} <= pb)
check("groupe A n'a jamais recu marqueurB",
      not any(m in pb for m in (ENT + "." + GA, ENT + "." + AUTRE_A)))
check("groupe B n'a jamais recu marqueurA",
      not any(m in pa for m in (ENT + "." + GB, ENT + "." + AUTRE_B)))
check("le journal nomme les deux groupes",
      any("groupe « A »" in l for l in logs)
      and any("groupe « B »" in l for l in logs))

print("   idempotence de la passe par groupes")
etat = instantane()
n2 = pc.propagate_groupes(R, GROUPES, branches=["YTD"], log=lambda *_: None)
check("2e passe = 0 changement (obtenu " + str(n2) + ")", n2 == 0)
check("… et les fichiers sont identiques au caractere", instantane() == etat)
rmtree(c)

# ===================================================================== 3
print("3. LE PIEGE : un KPI d'un autre groupe prefixe le gabarit")
# Honnetement : cette section prouve la CONVERGENCE et la non-contamination
# mutuelle, pas la necessite de `kpis_connus`. Desactiver ce parametre ne la
# fait PAS tomber — le garde-fou `known` (une reference ne s'ecrit que vers une
# mesure qui existe) masque le degat, et le clone fautif retombe la ou le
# groupe voisin l'aurait mis de toute facon. On garde `kpis_connus` parce que
# classer « <gabarit> Goal » comme une declinaison de « <gabarit> » est
# simplement FAUX, et qu'un futur changement du garde-fou reouvrirait la porte.
c = copie("prefixe")
R = c / (PROJ + ".Report")
M = c / (PROJ + ".SemanticModel")
BASE = KPIS[0]
HOMONYME = BASE + " Goal"


def cloner_kpi(base_kpi, nouveau):
    """Donne ses mesures ET ses lignes de parametre de champ a un KPI."""
    tmdl = M / "definition" / "tables" / "_mesures.tmdl"
    texte = tmdl.read_text(encoding="utf-8")
    noms = {m.group(1) or m.group(2)
            for m in pc.MEASURE_NAME_RE.finditer(texte)}
    ajouts, lignes, ordre = [], [], 900
    fwd, rev = pc.read_fp_maps(M, FP)
    for n in sorted(x for x in noms if x):
        if n != base_kpi and not n.startswith(base_kpi + " "):
            continue
        neuf = nouveau + n[len(base_kpi):]
        if neuf in noms:
            continue
        ajouts.append("\tmeasure '" + neuf.replace("'", "''") + "' = 0\n"
                      "\t\tlineageTag: goal-" + str(len(ajouts)) + "\n\n")
        if n in rev:                     # meme (Calcul, Branche) que l'original
            _k, calcul, branche = rev[n]
            lignes.append('\t\t\t\t    ("' + calcul + '", NAMEOF([' + neuf
                          + ']), ' + str(ordre) + ', "' + nouveau + '", "'
                          + calcul + '", "' + branche + '")')
            ordre += 1
    coupe = texte.find("\tpartition ")
    tmdl.write_text(texte[:coupe] + "".join(ajouts) + texte[coupe:],
                    encoding="utf-8")
    fp = M / "definition" / "tables" / (FP + ".tmdl")
    ftexte = fp.read_text(encoding="utf-8")
    m = list(re.finditer(r"^\t{4}\}\s*$", ftexte, re.M))[-1]
    fp.write_text(ftexte[:m.start()] + ",\n" + ",\n".join(lignes) + "\n"
                  + ftexte[m.start():], encoding="utf-8")


VOISIN = KPIS[1]
HOMONYME2 = VOISIN + " Goal"
# Le groupe B a DEUX KPI, tous deux homonymes de ceux du groupe A. C'est
# necessaire pour que la breche soit atteignable : si B n'avait qu'un KPI, le
# clone fautif retomberait sur sa propre source (le garde-fou `known` refuse
# d'inventer « <voisin> Goal ») et le degat resterait invisible.
cloner_kpi(BASE, HOMONYME)
cloner_kpi(VOISIN, HOMONYME2)
check("les homonymes sont des KPI a part entiere",
      HOMONYME in kpis_de(c) and HOMONYME2 in kpis_de(c))
check("… et leurs noms commencent par ceux du groupe A",
      HOMONYME.startswith(BASE + " ") and HOMONYME2.startswith(VOISIN + " "))

GROUPES_P = [{"nom": "A", "gabarit": BASE, "kpis": [BASE, VOISIN]},
             {"nom": "B", "gabarit": HOMONYME, "kpis": [HOMONYME, HOMONYME2]}]

# Il faut que CHAQUE gabarit porte quelque chose, sinon son groupe n'a aucune
# source et le piege ne se declenche jamais : c'est l'entree de l'homonyme que
# la passe A risque de prendre pour une declinaison de SON gabarit.
vjP, cleP = poser(BASE, "marqueurA")
poser_dans(vjP, cleP, HOMONYME, "marqueurGoal")   # KPI neuf : placement force
check("les deux gabarits portent une entree, dans le MEME visuel",
      porteurs("marqueurA") == {ENT + "." + BASE}
      and porteurs("marqueurGoal") == {ENT + "." + HOMONYME})


def n_entrees():
    n = 0
    for vj in R.glob("definition/pages/*/visuals/*/visual.json"):
        objets = (json.loads(vj.read_text(encoding="utf-8")).get("visual")
                  or {}).get("objects") or {}
        for liste in objets.values():
            if isinstance(liste, list):
                n += len(liste)
    return n


suite = [pc.propagate_groupes(R, GROUPES_P, branches=["YTD"],
                              log=lambda *_: None) for _ in range(4)]
print("   changements par passe :", suite)
check("la propagation CONVERGE (passes 2+ a zero)", suite[1:] == [0, 0, 0])
check("aucune explosion du nombre d'entrees", n_entrees() < 400)
pa, pg = porteurs("marqueurA"), porteurs("marqueurGoal")
check("le groupe A n'a rien pose sur les KPI du groupe B",
      not any(m in pa for m in (ENT + "." + HOMONYME, ENT + "." + HOMONYME2)))
check("le groupe B n'a rien pose sur les KPI du groupe A",
      not any(m in pg for m in (ENT + "." + BASE, ENT + "." + VOISIN)))
check("chaque groupe a bien servi le SIEN",
      {ENT + "." + BASE, ENT + "." + VOISIN} <= pa
      and {ENT + "." + HOMONYME, ENT + "." + HOMONYME2} <= pg)
rmtree(c)

# ===================================================================== 4
print("4. groupe par defaut, et equivalence avec le gabarit unique")
c = copie("defaut")
R = c / (PROJ + ".Report")
seul = [{"nom": "tout", "gabarit": KPIS[0], "kpis": []}]
n_groupes = pc.propagate_groupes(R, seul, branches=["YTD"], log=lambda *_: None)
etat_groupes = {str(p.relative_to(R)): p.read_text(encoding="utf-8")
                for p in R.glob("definition/pages/*/visuals/*/visual.json")}
rmtree(c)

c2 = copie("classique")
R2 = c2 / (PROJ + ".Report")
n_simple = pc.propagate(R2, KPIS[0], branches=["YTD"], log=lambda *_: None)
etat_simple = {str(p.relative_to(R2)): p.read_text(encoding="utf-8")
               for p in R2.glob("definition/pages/*/visuals/*/visual.json")}
check("un seul groupe par defaut = autant de changements qu'un propagate "
      f"classique ({n_groupes} vs {n_simple})", n_groupes == n_simple)
check("… et le MEME resultat, octet pour octet", etat_groupes == etat_simple)
rmtree(c)
rmtree(c2)

# ===================================================================== 5
print("5. une seule sauvegarde pour toute l'action")
c = copie("sauvegarde")
R = c / (PROJ + ".Report")
trois = [{"nom": "un", "gabarit": KPIS[0], "kpis": [KPIS[0], KPIS[1]]},
         {"nom": "deux", "gabarit": KPIS[2], "kpis": [KPIS[2]]},
         {"nom": "trois", "gabarit": KPIS[3], "kpis": [KPIS[3], KPIS[4]]}]
# Chaque gabarit porte un marqueur, pour que les trois passes ecrivent
# VRAIMENT — et dans le meme visuel. Sans ca, aucun fichier n'est touche deux
# fois et le controle du manifeste ne prouverait rien.
vj1, cle1 = poser(KPIS[0], "m1")
poser_dans(vj1, cle1, KPIS[2], "m2")
poser_dans(vj1, cle1, KPIS[3], "m3")
check("les trois gabarits portent un marqueur dans le meme visuel",
      vj1 is not None)
avant = {str(p.relative_to(R)): p.read_text(encoding="utf-8")
         for p in R.glob("definition/pages/*/visuals/*/visual.json")}
pc.propagate_groupes(R, trois, branches=["YTD"], log=lambda *_: None)
racine = br.backup_root(c, "_propagate_backups")
sessions = br.sessions_of(racine)
check("3 groupes -> UNE seule session de sauvegarde (obtenu "
      + str(len(sessions)) + ")", len(sessions) == 1)
info = br.session_info(sessions[0], c)
check("elle porte un manifeste", info["manifeste"])
check("son resume nomme les trois gabarits",
      all(k in info["resume"] for k in (KPIS[0], KPIS[2], KPIS[3])))
br.restore_session(sessions[0], c)
apres = {str(p.relative_to(R)): p.read_text(encoding="utf-8")
         for p in R.glob("definition/pages/*/visuals/*/visual.json")}
check("la restaurer annule l'action ENTIERE, tous groupes confondus",
      apres == avant)
cibles = [e["cible"] for e in info["fichiers"]]
check("chaque visuel touche n'apparait qu'UNE fois au manifeste "
      "(sinon la 2e copie serait l'etat intermediaire)",
      len(cibles) == len(set(cibles)))
rmtree(c)

# ===================================================================== 6
print("6. le fichier de groupes, PARTAGE par les rapports du dossier")
c = copie("fichier")
R = c / (PROJ + ".Report")
check("il s'appelle propagation.json, a cote des .pbip",
      pc.groupes_path(R) == c / "propagation.json")
check("toutes les versions du rapport lisent LE MEME fichier",
      pc.groupes_path(c / "Fitbit v2 test.Report") == pc.groupes_path(R))

print("   l'ancien fichier propre au rapport : lu en repli, migre s'il est seul")
ancien = pc.groupes_path_ancien(R)
check("l'ancien nom portait celui du rapport",
      ancien.name == PROJ + ".propagation.json")
ancien.write_text(json.dumps({"groupes": [
    {"nom": "ancien", "gabarit": KPIS[0], "kpis": []}]}, ensure_ascii=False),
    encoding="utf-8")
check("sans propagation.json, c'est l'ancien fichier qu'on lit",
      pc.groupes_a_lire(R) == ancien)
logs = []
pc.propagate_groupes(R, branches=["YTD"], dry_run=True, log=logs.append)
check("… et la propagation s'en sert", any("ancien" in l for l in logs))

deuxieme = c / "Fitbit v2 test.propagation.json"
deuxieme.write_text(ancien.read_text(encoding="utf-8"), encoding="utf-8")
check("DEUX anciens fichiers : pas de partage devine",
      pc.migrer_groupes(c, log=lambda *_: None) is None
      and ancien.exists() and deuxieme.exists()
      and not (c / "propagation.json").exists())
deuxieme.unlink()
contenu = ancien.read_text(encoding="utf-8")
annonces = []
check("UN seul ancien fichier : il devient propagation.json",
      pc.migrer_groupes(c, log=annonces.append) == c / "propagation.json"
      and (c / "propagation.json").read_text(encoding="utf-8") == contenu
      and not ancien.exists())
check("… et le journal le dit", any("propagation.json" in a for a in annonces))
check("migrer une 2e fois ne fait rien",
      pc.migrer_groupes(c, log=lambda *_: None) is None)
check("desormais, toutes les versions lisent propagation.json",
      pc.groupes_a_lire(R) == c / "propagation.json"
      == pc.groupes_a_lire(c / "Fitbit v2 test.Report"))

pc.groupes_path(R).write_text(json.dumps({"groupes": [
    {"nom": "depuis le fichier", "gabarit": KPIS[0], "kpis": []}]},
    ensure_ascii=False), encoding="utf-8")
logs = []
pc.propagate_groupes(R, branches=["YTD"], log=logs.append)   # groupes=None
check("sans argument, les groupes sont lus DANS le fichier partage",
      any("depuis le fichier" in l for l in logs))

pc.groupes_path(R).write_text("{}", encoding="utf-8")
try:
    pc.propagate_groupes(R, branches=["YTD"], log=lambda *_: None)
    check("fichier sans groupe = erreur actionnable", False)
except SystemExit as e:
    check("fichier sans groupe = erreur actionnable nommant le fichier",
          "propagation.json" in str(e))

# l'invariant qui protege du pire : `propagate` traite targets=[] comme « tous
# les KPI », donc resoudre_groupes ne doit JAMAIS rendre un groupe vide
for cas in ([{"nom": "A", "gabarit": KPIS[0], "kpis": []}],
            [{"nom": "A", "gabarit": KPIS[0], "kpis": [KPIS[0]]},
             {"nom": "B", "gabarit": KPIS[1], "kpis": [KPIS[1]]}]):
    resolus = pc.resoudre_groupes(cas, KPIS, lambda *_: None)
    check("aucun groupe resolu n'a une liste de KPI vide",
          all(g["kpis"] for g in resolus))
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
