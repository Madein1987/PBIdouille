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
sys.path.insert(0, str(FIT / "bidouille"))
sys.path.insert(0, str(FIT / "bidouille" / "moteurs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fixture import exiger_projet, PROJET_DEMO   # noqa: E402

exiger_projet(FIT, PROJET_DEMO, "measures_config.json")

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
    shutil.copytree(FIT / (PROJ + suffixe), c / (PROJ + suffixe))
for f in ((PROJ + ".pbip"), "measures_config.json"):
    shutil.copy2(FIT / f, c / f)

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

rmtree(c)
print("\n" + ("TOUT OK" if _ok else "*** DES ECHECS ***"))
sys.exit(0 if _ok else 1)
