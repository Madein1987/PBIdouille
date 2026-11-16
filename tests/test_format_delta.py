# -*- coding: utf-8 -*-
"""Un delta batî sur un format personnalisé ne doit rien massacrer.

    py tests\\test_format_delta.py

Symptomes corriges, tous deux de la MEME cause :

  1. un backslash devant chaque caractere — « #,0 "s" » donnait
     « +\\#\\,\\0 \\s », qui ne formate plus rien ;
  2. un signe en double — une base qui porte deja « + » donnait « ++… ».

Cause : TMDL entoure de guillemets toute valeur qui en contient, en DOUBLANT
ceux du dedans. Le format « #,0 "s" » s'ecrit donc sur le disque entoure de
guillemets, ceux du dedans doubles -- soit trois guillemets a la fin de ligne
(la forme exacte est construite par `desktop_ecrit` plus bas ; l'ecrire ici
refermerait ce commentaire).

On lisait ce quoting comme s'il faisait partie du format. La valeur entiere
passait alors pour un litteral (d'ou un backslash partout), et le « + » de tete
n'etait plus en tete (d'ou le signe ajoute par-dessus).
"""

from __future__ import annotations

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

exiger_projet(PBI, PROJET_DEMO, "measures_config.json")

import generate_measures as gm                    # noqa: E402

PROJ = PROJET_DEMO
Q = chr(34)
B = chr(92)
_ok = True


def check(label, cond):
    global _ok
    _ok = _ok and bool(cond)
    print(("  ok   " if cond else "  ECHEC ") + label)


def rmtree(p):
    if p.exists():
        shutil.rmtree(p, onerror=lambda f, path, e: (os.chmod(path, stat.S_IWRITE), f(path)))


def desktop_ecrit(valeur):
    """Ce que Desktop pose dans le .tmdl : quote des qu'il y a un guillemet."""
    return Q + valeur.replace(Q, Q + Q) + Q if Q in valeur else valeur


SECONDES = "#,0 " + Q + "s" + Q                    # #,0 "s"
SECONDES_SIGNE = ("+#,0 " + Q + "s" + Q + ";-#,0 " + Q + "s" + Q
                  + ";#,0 " + Q + "s" + Q)         # deja signe

# ===================================================================== 1
print("1. lire la valeur, pas le quoting de TMDL")
check("la ligne TMDL est bien celle qu'on croit",
      desktop_ecrit(SECONDES) == Q + "#,0 " + Q + Q + "s" + Q + Q + Q)
check("relue fidelement",
      gm.unquote_tmdl_value(desktop_ecrit(SECONDES)) == SECONDES)
check("une valeur non quotee n'est pas touchee",
      gm.unquote_tmdl_value("#,0") == "#,0")
check("… meme si elle contient des guillemets sans etre quotee par TMDL",
      gm.unquote_tmdl_value('+0.0" pts";-0.0" pts";0.0" pts"')
      == '+0.0" pts";-0.0" pts";0.0" pts"')
check("un guillemet SOLITAIRE dedans : on ne devine pas",
      gm.unquote_tmdl_value('"a"b"') == '"a"b"')
check("une valeur vide ou courte passe sans casser",
      gm.unquote_tmdl_value("") == "" and gm.unquote_tmdl_value(Q) == Q)

print("   aller-retour ecriture -> lecture")
for v in (SECONDES, SECONDES_SIGNE, '"TRUE";"TRUE";"FALSE"', "#,##0.00",
          "0.0 %", "Long Date", "+#,0 " + B + "s;-#,0 " + B + "s",
          '+0.0" pts";-0.0" pts";0.0" pts"'):
    relu = gm.unquote_tmdl_value(gm.quote_tmdl_value(v))
    check("aller-retour fidele : " + repr(v), relu == v)
check("les formats « pts » deja ecrits ne sont PAS requotes (zero churn)",
      gm.quote_tmdl_value('+0.0" pts";-0.0" pts";0.0" pts"')
      == '+0.0" pts";-0.0" pts";0.0" pts"')
check("une valeur qui COMMENCE par un guillemet est quotee (sinon illisible)",
      gm.quote_tmdl_value('"TRUE";"FALSE"') == '"""TRUE"";""FALSE"""')

print("   measure_info dequote le formatString")
chunk = ("\tmeasure 'Temps' = SUM(t[s])\n"
         "\t\tformatString: " + desktop_ecrit(SECONDES) + "\n"
         "\t\tdisplayFolder: _indicateurs\n"
         "\t\tlineageTag: abc\n")
check("measure_info rend le format REEL",
      gm.measure_info(chunk)["format"] == SECONDES)

# ===================================================================== 2
print("2. symptome 1 : plus de backslash devant les caracteres de format")
lu = gm.unquote_tmdl_value(desktop_ecrit(SECONDES))
delta = gm.resolve_format("delta", lu)
print("   " + repr(delta))
check("les placeholders sont intacts", B + "#" not in delta
      and B + "," not in delta and B + "0" not in delta)
check("la lettre littérale reste echappee (s = un code de format sinon)",
      B + "s" in delta)
check("le format attendu, au caractere",
      delta == "+#,0 " + B + "s;-#,0 " + B + "s;#,0 " + B + "s")
check("trois sections", delta.count(";") == 2)

print("3. symptome 2 : un seul signe, meme si la base en porte deja un")
lu2 = gm.unquote_tmdl_value(desktop_ecrit(SECONDES_SIGNE))
delta2 = gm.resolve_format("delta", lu2)
print("   " + repr(delta2))
check("pas de « ++ »", "++" not in delta2)
check("la section positive commence par UN « + »",
      delta2.split(";")[0].startswith("+")
      and not delta2.split(";")[0].startswith("++"))
check("le signe de la base est bien ignore, pas empile", delta2 == delta)

print("4. le cas du modele de demo : un format entierement litteral")
vrai = '"TRUE";"TRUE";"FALSE"'
lu3 = gm.unquote_tmdl_value(desktop_ecrit(vrai))
check("relu fidelement", lu3 == vrai)
check("le delta n'empile pas les sections de la base",
      gm.resolve_format("delta", lu3).count(";") == 2)

print("5. les formats deja corrects ne changent pas")
for base, attendu in (
    ("#,0", "+#,0;-#,0;#,0"),
    ("0.0", "+0.0;-0.0;0.0"),
    ("+#,0;-#,0;#,0", "+#,0;-#,0;#,0"),
    ("#,0.0%", "+#,0.0 " + B + "p" + B + "t" + B + "s;"
               "-#,0.0 " + B + "p" + B + "t" + B + "s;"
               "#,0.0 " + B + "p" + B + "t" + B + "s"),
):
    obtenu = gm.resolve_format("delta", base)
    check(f"{base!r} -> {obtenu!r}", obtenu == attendu)

# ===================================================================== 6
print("6. de bout en bout : ce que la generation ECRIT dans le .tmdl")
c = Path(tempfile.gettempdir()) / "pbidouille_fmt"
rmtree(c)
c.mkdir(parents=True)
for suffixe in (".Report", ".SemanticModel"):
    shutil.copytree(PBI / (PROJ + suffixe), c / (PROJ + suffixe))
for f in ((PROJ + ".pbip"), "measures_config.json"):
    shutil.copy2(PBI / f, c / f)

modele = c / (PROJ + ".SemanticModel")
mesures = modele / "definition" / "tables" / "_mesures.tmdl"
texte = mesures.read_text(encoding="utf-8")


def ref_mesure(mesure):
    """TMDL n'entoure de quotes que les noms qui en ont besoin : « measure
    Weight = » mais « measure 'Total Steps' = ». On accepte les deux."""
    quote = re.escape("'" + mesure.replace("'", "''") + "'")
    return "(?:" + quote + "|" + re.escape(mesure) + r"(?=\s*=))"


def poser_format(txt, mesure, valeur_reelle):
    """Remplace le formatString d'une mesure par ce que Desktop y ecrirait."""
    # [^\n]* et non (.*)$ : avec re.S, « . » avale les sauts de ligne et le
    # groupe irait jusqu'a la FIN DU FICHIER
    m = re.search(r"(\tmeasure " + ref_mesure(mesure) + r" =.*?\n)"
                  r"(\t\tformatString: )([^\n]*)", txt, re.S)
    assert m, mesure + " introuvable"
    return txt[:m.start(3)] + desktop_ecrit(valeur_reelle) + txt[m.end(3):]


texte = poser_format(texte, "Total Steps", SECONDES)
texte = poser_format(texte, "Weight", SECONDES_SIGNE)
mesures.write_text(texte, encoding="utf-8")
check("le modele porte bien la ligne quotee de TMDL",
      'formatString: "#,0 ""s"""' in mesures.read_text(encoding="utf-8"))

conf = json.loads((c / "measures_config.json").read_text(encoding="utf-8"))
gm.generate(modele, conf, dry_run=False, log=lambda *_: None)
ecrit = mesures.read_text(encoding="utf-8")


def format_de(txt, mesure):
    """Le formatString REEL d'une mesure, tel qu'on le relirait."""
    m = re.search(r"\tmeasure " + ref_mesure(mesure) + r" =.*?\n"
                  r"\t\tformatString: ([^\n]*)", txt, re.S)
    return gm.unquote_tmdl_value(m.group(1)) if m else None


for mesure in ("Total Steps Δ 7d", "Total Steps Δ 30d"):
    obtenu = format_de(ecrit, mesure)
    print("   " + mesure + " -> " + repr(obtenu))
    check(mesure + " : format sain",
          obtenu == "+#,0 " + B + "s;-#,0 " + B + "s;#,0 " + B + "s")

obtenu = format_de(ecrit, "Weight Δ 7d")
print("   Weight Δ 7d -> " + repr(obtenu))
check("Weight Δ 7d : un seul signe malgre la base signee",
      obtenu == "+#,0 " + B + "s;-#,0 " + B + "s;#,0 " + B + "s")

check("une variation « inherit » recopie le format tel quel",
      format_de(ecrit, "Total Steps 7d avg") == SECONDES)
check("aucun backslash parasite dans tout le fichier ecrit",
      B + "#" not in ecrit and B + "," not in ecrit)

print("   la generation reste idempotente")
st = gm.generate(modele, conf, dry_run=True, log=lambda *_: None)
check("2e passe : rien a creer ni a mettre a jour",
      not st["created"] and not st["updated"])
avant = ecrit
gm.generate(modele, conf, dry_run=False, log=lambda *_: None)
check("… et le fichier est identique au caractere",
      mesures.read_text(encoding="utf-8") == avant)

# ===================================================================== 7
print("7. {baseFormatString} : le format de la base, ecrit en dur dans le DAX")
check("une chaine DAX : entre guillemets, ceux du dedans doubles",
      gm.chaine_dax(SECONDES) == Q + "#,0 " + Q + Q + "s" + Q + Q + Q
      and gm.chaine_dax("#,0") == Q + "#,0" + Q
      and gm.chaine_dax(None) == Q + Q)
# une base SANS format : le jeton rend "" et le journal le dit
texte = mesures.read_text(encoding="utf-8")
m = re.search(r"(\tmeasure " + ref_mesure("Body Fat %") + r" =.*?\n)"
              r"(\t\tformatString: [^\n]*\n)", texte, re.S)
assert m, "Body Fat % introuvable"
mesures.write_text(texte[:m.start(2)] + texte[m.end(2):], encoding="utf-8")
conf["variations"]["étiquette"] = {
    "namePattern": "{base} étiquette",
    "dax": "FORMAT({baseRef}, {baseFormatString}) & " + Q + " pas" + Q,
    "formatString": "text", "inFieldParameter": False,
    # ce qu'on verifie en branche, c'est le DAX RECOPIE (le format de la base
    # de branche) : pas d'enveloppe, qui est le defaut
    "wrapInBranch": False}
journal: list = []
gm.generate(modele, conf, dry_run=False, log=journal.append)
existantes, _bases = gm.read_measures(modele, conf)


def dax_de(nom):
    return " ".join((existantes.get(nom) or {}).get("dax", "").split())


print("   " + dax_de("Total Steps étiquette"))
check("la valeur mise en texte AU FORMAT de sa base",
      dax_de("Total Steps étiquette")
      == "FORMAT([Total Steps], " + gm.chaine_dax(SECONDES) + ") & " + Q + " pas" + Q)
check("chaque KPI avec SON format (une base signee garde ses trois sections)",
      gm.chaine_dax(SECONDES_SIGNE) in dax_de("Weight étiquette"))
check("en branche, le format de la base de branche",
      dax_de("Total Steps YTD étiquette")
      == "FORMAT([Total Steps YTD], " + gm.chaine_dax(SECONDES) + ") & " + Q + " pas" + Q)
check("une base sans format : \"\" (le nombre brut)…",
      "FORMAT([Body Fat %], " + Q + Q + ")" in dax_de("Body Fat % étiquette"))
check("… et le journal le dit, en nommant la base",
      any("Body Fat %" in l and "baseFormatString" in l for l in journal))
check("aucun jeton n'est reste dans le DAX ecrit",
      "{baseFormatString}" not in mesures.read_text(encoding="utf-8"))
check("la variation rend du texte : pas de format a elle",
      (existantes.get("Total Steps étiquette") or {}).get("format") is None)
st = gm.generate(modele, conf, dry_run=True, log=lambda *_: None)
check("regenerer ne change rien (idempotent)",
      not st["created"] and not st["updated"])

# ===================================================================== 8
print("8. {branch} : la branche courante — en Reel, rien, ni son espace")
check("au milieu : l'espace d'AVANT part avec lui",
      gm.remplacer_branche("[{kpi} {branch} PY]", None) == "[{kpi} PY]"
      and gm.remplacer_branche("[{kpi} {branch} PY]", "YTD") == "[{kpi} YTD PY]")
check("a la fin : idem", gm.remplacer_branche("[{kpi} cible {branch}]", "")
      == "[{kpi} cible]")
check("au debut : l'espace d'APRES", gm.remplacer_branche("[{branch} {kpi}]", None)
      == "[{kpi}]")
check("seul dans une chaine : la chaine vide",
      gm.remplacer_branche(Q + "{branch}" + Q, None) == Q + Q)
conf["variations"]["cbr"] = {
    "namePattern": "{base} cbr",
    "dax": "[{kpi} {branch} PY] + [{kpi} cible {branch}] + LEN("
           + Q + "{branch}" + Q + ")",
    "description": "{kpi} {branch} : essai",
    "formatString": "inherit", "inFieldParameter": False}
gm.generate(modele, conf, dry_run=False, log=lambda *_: None)
existantes, _bases = gm.read_measures(modele, conf)
print("   " + dax_de("Weight cbr"))
print("   " + dax_de("Weight YTD cbr"))
check("dans le DAX, en Reel : [Weight PY] et [Weight cible] — pas d'espace "
      "en trop", dax_de("Weight cbr") == "[Weight PY] + [Weight cible] + LEN("
      + Q + Q + ")")
check("… en branche : [Weight YTD PY] et [Weight cible YTD]",
      dax_de("Weight YTD cbr") == "[Weight YTD PY] + [Weight cible YTD] + LEN("
      + Q + "YTD" + Q + ")")
check("aucun {branch} n'est reste dans le fichier ecrit",
      "{branch}" not in mesures.read_text(encoding="utf-8"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tabs.tab_config as tc                                      # noqa: E402
segs = tc.segments_nom("{kpi} {branch} cbr", [("Weight", "r")],
                       {"kpi": ("Weight", "r"), "branch": ("", "b")}, "v")
segs_b = tc.segments_nom("{kpi} {branch} cbr", [("Weight", "r")],
                         {"kpi": ("Weight", "r"), "branch": ("YTD", "b")}, "v")
check("l'apercu des noms dit la meme chose que la generation",
      "".join(t for t, _ in segs) == "Weight cbr"
      and "".join(t for t, _ in segs_b) == "Weight YTD cbr")

rmtree(c)
print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
