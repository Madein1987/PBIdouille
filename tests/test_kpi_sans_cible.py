# -*- coding: utf-8 -*-
"""Un KPI qui n'a pas l'attribut ne recoit RIEN pour cet attribut.

    py tests\\test_kpi_sans_cible.py

Cas rapporte : quatre KPI, seuls deux ont une mesure CIBLE. La propagation
ecrivait quand meme les entrees de cible sur les deux autres, ou elles
pointaient la mesure du KPI TEMPLATE : les valeurs restaient justes, mais Power
BI affichait un avertissement sur le visuel.

La distinction a tenir — et c'est tout l'enjeu :

  · « ce KPI n'a pas de cible »        -> on ne lui ecrit rien ;
  · « cette mesure ne depend pas du KPI » (un titre, un libelle commun)
                                        -> elle continue de se propager.

Le paramETRE de champ tranche : la mesure source se rattache a un CALCUL par sa
racine. Si le KPI vise n'a aucune ligne pour ce calcul, il n'a pas la mesure.
Une mesure generale, elle, n'a pas de racine propre au KPI — donc rien ne
change pour elle.
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
FP = "P_Indicateurs_parCalcul"
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


# ===================================================================== 1
print("1. la regle, cas par cas")
fp_rev = {}
for k in ("KPI un", "KPI deux", "KPI trois", "KPI quatre"):
    fp_rev[k] = (k, "Réel", "")
    fp_rev[k + " YTD"] = (k, "Réel", "YTD")
for k in ("KPI un", "KPI deux"):                 # seuls ces deux ont une cible
    fp_rev[k + " cible"] = (k, "Cible", "")
    fp_rev[k + " cible YTD"] = (k, "Cible", "YTD")
fp_fwd = {(k, c, b): m for m, (k, c, b) in fp_rev.items()}


def sans(md, dst):
    return pc.kpi_sans_equivalent(md, "KPI un", dst, ENT, fp_fwd, fp_rev)


check("le KPI qui A une cible la recoit",
      not sans(ENT + ".KPI un cible", "KPI deux"))
check("celui qui n'en a pas est ecarte",
      sans(ENT + ".KPI un cible", "KPI trois")
      and sans(ENT + ".KPI un cible", "KPI quatre"))
check("une couleur DERIVEE de la cible suit la meme regle",
      sans(ENT + ".KPI un cible ecartCF", "KPI trois")
      and not sans(ENT + ".KPI un cible ecartCF", "KPI deux"))
check("la mesure de BASE n'est jamais ecartee (tous l'ont)",
      not sans(ENT + ".KPI un", "KPI trois"))
check("une mesure GENERALE hors parametre n'est jamais ecartee",
      not sans(ENT + ".Titre commun", "KPI trois"))
check("… un titre nomme d'apres le KPI non plus (sa racine est la base)",
      not sans(ENT + ".KPI un titre", "KPI trois"))
check("sans parametre de champ, on n'ecarte rien",
      not pc.kpi_sans_equivalent(ENT + ".KPI un cible", "KPI un", "KPI trois",
                                 ENT, None, None))
check("un KPI ABSENT du parametre n'est pas ecarte non plus "
      "(le parametre n'en dit rien)",
      not sans(ENT + ".KPI un cible", "KPI cinq"))

# ===================================================================== 2
print("2. de bout en bout : une cible que seuls 2 KPI sur 5 possedent")
c = Path(tempfile.gettempdir()) / "pbid_sans_cible"
rmtree(c)
c.mkdir(parents=True)
for s in (".Report", ".SemanticModel"):
    shutil.copytree(PBI / (PROJ + s), c / (PROJ + s))
R = c / (PROJ + ".Report")
M = c / (PROJ + ".SemanticModel")
tables = M / "definition" / "tables"

kpis = pc.kpis_from_parameter(M, FP)
AVEC = kpis[:2]                      # ceux qui auront une cible
SANS = kpis[2:]
if TPL not in AVEC:                  # le template doit en avoir une
    AVEC = [TPL] + [k for k in kpis if k != TPL][:1]
    SANS = [k for k in kpis if k not in AVEC]
print("   avec cible :", AVEC)
print("   sans cible :", SANS)
check("le template a une cible et d'autres KPI n'en ont pas",
      TPL in AVEC and len(SANS) >= 2)


def ajouter_cibles(kpis_avec):
    """Cree les mesures de cible ET leurs lignes dans le parametre de champ."""
    p = tables / "_mesures.tmdl"
    texte = p.read_text(encoding="utf-8")
    bloc = ""
    for i, k in enumerate(kpis_avec):
        for suffixe in ("", " YTD"):
            bloc += ("\tmeasure '" + k + " cible" + suffixe + "' = 0\n"
                     "\t\tlineageTag: cible-" + str(i) + suffixe.strip() + "\n\n")
        # les couleurs DERIVEES de la cible, hors parametre de champ, une par
        # branche (c'est ce qu'un vrai modele porte)
        for suffixe in ("", " YTD"):
            bloc += ("\tmeasure '" + k + " cible" + suffixe
                     + " ecartCF' = \"#FF0000\"\n"
                     "\t\tlineageTag: cibleCF-" + str(i) + suffixe.strip() + "\n\n")
    coupe = texte.find("\tpartition ")
    p.write_text(texte[:coupe] + bloc + texte[coupe:], encoding="utf-8")

    fp = tables / (FP + ".tmdl")
    ftexte = fp.read_text(encoding="utf-8")
    lignes = []
    ordre = 900
    for k in kpis_avec:
        for suffixe, branche in (("", "Réel"), (" YTD", "YTD")):
            lignes.append('\t\t\t\t    ("Cible", NAMEOF([' + k + " cible"
                          + suffixe + ']), ' + str(ordre) + ', "' + k
                          + '", "Cible", "' + branche + '")')
            ordre += 1
    # inserer AVANT l'accolade fermante du bloc source
    m = list(re.finditer(r"^\t{4}\}\s*$", ftexte, re.M))[-1]
    ftexte = (ftexte[:m.start()] + ",\n" + ",\n".join(lignes) + "\n"
              + ftexte[m.start():])
    fp.write_text(ftexte, encoding="utf-8")


ajouter_cibles(AVEC)
fwd, rev = pc.read_fp_maps(M, FP)
check("les cibles sont dans le parametre de champ",
      (TPL + " cible") in rev and rev[TPL + " cible"][1] == "Cible")
check("les KPI sans cible n'y ont pas de ligne Cible",
      not any(k == SANS[0] and calc == "Cible" for (k, calc, _b) in fwd))
connues = pc.measures_of_model(M)
check("les mesures de cible existent dans le modele",
      (TPL + " cible") in connues and (SANS[0] + " cible") not in connues)


CF_CIBLE = TPL + " cible ecartCF"      # la mesure de couleur, tiree de la cible


def entree_cf(kpi_selector):
    """La forme REELLE d'un formatage conditionnel par mesure : la regle est
    posee sur la mesure de BASE, et sa couleur vient d'une AUTRE mesure — ici
    celle de l'ecart a la cible. C'est cette mesure enfouie dans `properties`
    qui n'a pas d'equivalent chez un KPI sans cible."""
    return {
        "properties": {
            "fontColor": {"solid": {"color": {"expr": {"Measure": {
                "Expression": {"SourceRef": {"Entity": ENT}},
                "Property": CF_CIBLE}}}}},
        },
        "selector": {
            "metadata": ENT + "." + kpi_selector,
            "data": [{"dataViewWildcard": {"matchingOption": 0}}],
        },
    }


def poser_cf():
    """Pose l'entree de formatage conditionnel dans un visuel du template."""
    for vj in sorted(R.glob("definition/pages/*/visuals/*/visual.json")):
        data = json.loads(vj.read_text(encoding="utf-8"))
        objects = (data.get("visual") or {}).get("objects")
        if not isinstance(objects, dict):
            continue
        for cle, liste in objects.items():
            if not isinstance(liste, list):
                continue
            if not any((pc.entry_metadata(e) or "").startswith(ENT + "." + TPL)
                       for e in liste):
                continue
            liste.append(entree_cf(TPL))
            vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
            return vj, cle
    return None, None


vj, cle = poser_cf()
check("une entree de formatage par mesure a ete posee", vj is not None)


def metadatas():
    vus = set()
    for v in R.glob("definition/pages/*/visuals/*/visual.json"):
        objs = (json.loads(v.read_text(encoding="utf-8")).get("visual")
                or {}).get("objects") or {}
        for liste in objs.values():
            if isinstance(liste, list):
                for e in liste:
                    md = pc.entry_metadata(e)
                    if md:
                        vus.add(md)
    return vus


def chaines_du_rapport() -> set:
    """Toutes les chaines de toutes les entrees du rapport."""
    out: set = set()
    for v in R.glob("definition/pages/*/visuals/*/visual.json"):
        objs = (json.loads(v.read_text(encoding="utf-8")).get("visual")
                or {}).get("objects") or {}
        for liste in objs.values():
            if isinstance(liste, list):
                for e in liste:
                    out |= set(pc._chaines(e))
    return out


def entrees_citant(mesure) -> list:
    """Les KPI (selector.metadata) des entrees qui CITENT cette mesure, ou
    qu'elle soit dans l'entree — selector compris."""
    out = []
    for v in R.glob("definition/pages/*/visuals/*/visual.json"):
        objs = (json.loads(v.read_text(encoding="utf-8")).get("visual")
                or {}).get("objects") or {}
        for liste in objs.values():
            if isinstance(liste, list):
                for e in liste:
                    if any(mesure == s for s in pc._chaines(e)):
                        out.append(pc.entry_metadata(e))
    return out


avant = entrees_citant(CF_CIBLE)
check("au depart, seule l'entree du template cite la cible : " + str(avant),
      avant == [ENT + "." + TPL])

logs: list = []
pc.propagate(R, TPL, branches=["YTD"], log=logs.append)
vus = metadatas()
citants = entrees_citant(CF_CIBLE)

for k in AVEC:
    check(f"« {k} » a une cible -> SA mesure d'ecart est utilisee",
          (k + " cible ecartCF") in chaines_du_rapport())
    check(f"… portee par une entree posee sur « {k} »",
          (ENT + "." + k) in entrees_citant(k + " cible ecartCF"))

for k in SANS:
    check(f"« {k} » n'a pas de cible -> aucune entree chez lui ne la cite",
          ENT + "." + k not in citants)
check("la cible du template n'est citee que par le template "
      "(" + str(sorted(set(citants))) + ")",
      set(citants) == {ENT + "." + TPL})
check("le journal nomme les KPI ecartes",
      any("sans équivalent" in l for l in logs)
      and any(SANS[0] in l for l in logs))
check("les entrees ordinaires se propagent toujours a TOUS les KPI",
      all(any(m.startswith(ENT + "." + k) for m in vus) for k in kpis))

print("   la propagation reste idempotente")
n2 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("2e passe = 0 changement (obtenu " + str(n2) + ")", n2 == 0)

# ===================================================================== 3
print("3. les entrees deja ecrites pour ces KPI sont RETIREES")
# l'etat d'avant : une entree posee sur un KPI SANS cible, qui cite quand meme
# la mesure d'ecart du template — exactement ce que l'ancienne propagation
# ecrivait, et ce qui faisait rouspeter Power BI
data = json.loads(vj.read_text(encoding="utf-8"))
liste = ((data.get("visual") or {}).get("objects") or {})[cle]
liste.append(entree_cf(SANS[0]))
vj.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
              encoding="utf-8")
check("l'entree parasite est en place",
      (ENT + "." + SANS[0]) in entrees_citant(CF_CIBLE))

pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("relancer la retire",
      (ENT + "." + SANS[0]) not in entrees_citant(CF_CIBLE))
check("et les cibles legitimes sont toujours la",
      (ENT + "." + AVEC[0]) in entrees_citant(AVEC[0] + " cible ecartCF"))
n2 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None)
check("puis c'est stable (0 changement, obtenu " + str(n2) + ")", n2 == 0)

rmtree(c)

# ===================================================================== 4
print("4. cibles ABSENTES du parametre de champ : le dossier tranche")
# C'est le trou que la section 1 ne voyait pas. Sans ligne dans le parametre,
# `racine_fp` rattache « KPI un cible » a la mesure de BASE : le Calcul devient
# « Reel », que tous les KPI possedent, donc la regle du parametre ne l'ecarte
# pas — et la cascade retombe sur « garde la mesure d'origine », c'est-a-dire la
# cible du GABARIT posee sur un KPI qui n'en a pas.
KP = ["KPI un", "KPI deux", "KPI trois"]
rev4 = {}
for k in KP:
    rev4[k] = (k, "Réel", "")
    rev4[k + " YTD"] = (k, "Réel", "YTD")
fwd4 = {(k, calc, b): m for m, (k, calc, b) in rev4.items()}
CIBLES = {k + " cible" for k in KP[:2]}          # dossier dedie, pas le parametre
modele4 = set(rev4) | CIBLES | {"KPI un cible ecartCF", "KPI deux cible ecartCF",
                                "Titre commun"}

check("le parametre ne connait PAS les cibles",
      not any(calc == "Cible" for (_k, calc, _b) in fwd4))
check("… donc l'ancienne regle ne les ecarte pas (le trou)",
      not pc.kpi_sans_equivalent(ENT + ".KPI un cible", "KPI un", "KPI trois",
                                 ENT, fwd4, rev4))

for nom in (ENT + ".KPI un cible", ENT + ".KPI un cible ecartCF"):
    check(f"{nom.split('.')[1]} : le KPI QUI A une cible la recoit",
          not pc.cible_sans_equivalent(nom, "KPI un", "KPI deux", ENT,
                                       CIBLES, modele4))
    check("… et celui qui n'en a pas est ecarte",
          pc.cible_sans_equivalent(nom, "KPI un", "KPI trois", ENT,
                                   CIBLES, modele4))

print("   une mesure PARTAGEE continue de passer (c'est la moitie du besoin)")
for nom in (ENT + ".Titre commun", ENT + ".KPI un", ENT + ".KPI un YTD"):
    check("passe : " + nom,
          not pc.cible_sans_equivalent(nom, "KPI un", "KPI trois", ENT,
                                       CIBLES, modele4))

check("la racine d'une derivee remonte a la cible",
      pc.racine_cible(ENT + ".KPI un cible ecartCF", "KPI un", ENT, CIBLES)
      == "KPI un cible")
check("aucun dossier declare = regle desactivee (comportement d'avant)",
      not pc.cible_sans_equivalent(ENT + ".KPI un cible", "KPI un", "KPI trois",
                                   ENT, set(), modele4))
check("modele illisible = on ne decide rien",
      not pc.cible_sans_equivalent(ENT + ".KPI un cible", "KPI un", "KPI trois",
                                   ENT, CIBLES, set()))

# ===================================================================== 5
print("5. de bout en bout, cibles hors parametre : lecture du dossier")
c = Path(tempfile.gettempdir()) / "pbid_sans_cible_dossier"
rmtree(c)
c.mkdir(parents=True)
for s in (".Report", ".SemanticModel"):
    shutil.copytree(PBI / (PROJ + s), c / (PROJ + s))
R = c / (PROJ + ".Report")
M = c / (PROJ + ".SemanticModel")
kpis5 = pc.kpis_from_parameter(M, FP)
AVEC5, SANS5 = kpis5[:2], kpis5[2:]
if TPL not in AVEC5:
    AVEC5 = [TPL] + [k for k in kpis5 if k != TPL][:1]
    SANS5 = [k for k in kpis5 if k not in AVEC5]

# cibles ecrites a la main, dans un sous-dossier dedie, SANS ligne au parametre
tmdl = M / "definition" / "tables" / "_mesures.tmdl"
texte = tmdl.read_text(encoding="utf-8")
bloc = ""
for i, k in enumerate(AVEC5):
    for suffixe in ("", " ecartCF"):
        bloc += ("\tmeasure '" + k + " cible" + suffixe + "' = 0\n"
                 "\t\tdisplayFolder: _indicateurs\\cible\n"
                 "\t\tlineageTag: dossier-" + str(i) + suffixe.strip() + "\n\n")
coupe = texte.find("\tpartition ")
tmdl.write_text(texte[:coupe] + bloc + texte[coupe:], encoding="utf-8")

trouvees = pc.cibles_of_model(M, ["cible"])
check("les cibles sont reconnues par leur dossier (feuille du chemin)",
      {k + " cible" for k in AVEC5} <= trouvees)
check("le parametre, lui, ne les connait pas",
      not any(calc == "Cible"
              for (_k, calc, _b) in pc.read_fp_maps(M, FP)[0]))

vj, cle = poser_cf()          # entree sur la base, couleur tiree de la cible
check("l'entree de formatage est posee", vj is not None)
avant5 = entrees_citant(CF_CIBLE)
logs5: list = []
pc.propagate(R, TPL, branches=["YTD"], log=logs5.append,
             cible_folders=["cible"])
citants5 = entrees_citant(CF_CIBLE)
for k in SANS5:
    check(f"« {k} » n'a pas de cible -> il ne cite pas celle du gabarit",
          (ENT + "." + k) not in citants5)
check("la cible du gabarit n'est citee que chez lui "
      "(" + str(sorted(set(citants5))) + ")",
      all(m.startswith(ENT + "." + TPL) for m in citants5))
check("le journal annonce les cibles trouvees",
      any("Cibles" in l for l in logs5))
n5 = pc.propagate(R, TPL, branches=["YTD"], log=lambda *_: None,
                  cible_folders=["cible"])
check("idempotent (2e passe = 0, obtenu " + str(n5) + ")", n5 == 0)
rmtree(c)

print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
