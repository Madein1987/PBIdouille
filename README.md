# Boîte à outils Power BI — variations, paramètres de champ et automatisation PBIP

Documentation des outils du dossier. Tout est conçu pour fonctionner **sans
dépendance externe** : Tabular Editor 2 ou 3 pour le modèle, Python 3.8+ pour
la couche rapport (fichiers PBIP/PBIR — `from __future__ import annotations`
assure la compatibilité avec les Python d'entreprise plus vieux). Aucun module
Python à installer, sauf qtpy/pyside6 pour les interfaces (ChopChopRapport et
**PBIdouille** 🔧, cockpit unique — voir section 13).

---

## 1. Vue d'ensemble

```
TD_KPI (Excel)                    mesures de base (_mesures\_indicateurs)
  indicateur, mesure,                     Weight, Total Steps, ...
  libelle_indicateur, direction                  │
        │                                        ▼
        │                          create_measure_variations.csx  ◄── measures_config.json
        │                                        │
        │            ┌───────────────┬───────────┴────────────┬──────────────┐
        │            ▼               ▼                        ▼              ▼
        │      variations      branches (YTD ...)      mesure Switch    mesures CF
        │      7d avg, PY...   YTD PY, YTD Δ 30d...    + ses variations (couleurs)
        │            │               │                        │
        │            └───────┬───────┘                        │
        │                    ▼                                ▼
        │      paramètres de champ (3 tables)          dossier _switch
        │      P_Indicateurs_parCalcul (+_2)           (jamais dans les paramètres)
        │      P_Indicateurs_parKPI
        │                    │
        └──── relations ─────┤
                             ▼
                       RAPPORT (.pbip)
                             │
        propagate_cf.py ─────┤ (formatage conditionnel par KPI)
        unused_measures.py ──┤ (ménage)
        scan_lineage.py ─────┘ (inventaire des sources)
```

Principe directeur : **une seule source de vérité par chose**. Les calculs
vivent dans `measures_config.json`, les libellés métier dans `TD_KPI`, le
style CF de référence dans UN visuel template. Les scripts matérialisent le
reste et sont **idempotents** : relancer met à jour, jamais de doublon.

---

## 2. Les fichiers

| Fichier | Couche | Rôle |
|---|---|---|
| `measures_config.json` | config | définit variations, branches, paramètres, switch |
| `generate_measures.py` | modèle | **générateur natif** : mesures + paramètres + switch, écrit le TMDL (Desktop fermé) |
| `create_measure_variations.csx` | modèle (TE) | même génération via Tabular Editor — **solution de secours** |
| `propagate_cf.py` | rapport | propage le formatage conditionnel d'un KPI template |
| `color_matrix_by_kpi.py` | rapport | colore les colonnes d'une matrice par KPI (couleurs dans TD) |
| `unused_measures.py` | modèle + rapport | détecte les mesures inutilisées |
| `unused_measures_ui.py` | modèle + rapport | UI (qtpy) : voir et supprimer les inutilisées |
| `backup_restore.py` | transverse | sauvegardes horodatées **＋ restauration** (manifeste : d'où vient chaque copie) |
| `scan_lineage.py` | parc | inventorie les sources de tous les PBIP d'un répertoire |
| `bidouille\` | UI | cockpit unique (qtpy) qui pilote les outils du rapport (section 13) |
| `delete_unused_measures.csx` | généré | « bouton » de suppression (sortie de unused_measures) |
| `unused_measures.csv`, `pbi_lineage.csv` | générés | audits |

---

## 3. Générer les mesures — natif (generate_measures.py) ou Tabular Editor (csx)

**Chemin principal : `generate_measures.py`** — le même travail que le csx,
sans TE ni Desktop ouvert : il écrit directement les fichiers TMDL.

```
py generate_measures.py        (ou « Générer les mesures », en tête du journal de PBIdouille)
```

⚠ Desktop FERMÉ pour l'écriture réelle ; backup automatique sous
`_backupsPBIdouille\_tmdl_backups\` ; rouvrir le `.pbip` ensuite. `settings.dryRun` (ou la case
« Aperçu ») pour tout lister sans rien écrire. Validé par « golden master » :
il reproduit à l'identique les mesures et les tables paramètre produites par
le csx (idempotent : relancer sans changement = 0 écriture). Les lineageTags
existants sont préservés ; une table paramètre créée est ajoutée aux
`ref table` de model.tmdl (penser à la relation TD → Indicateur ensuite).

**Collisions de nom** : les noms de mesures sont uniques dans le modèle. Si une
variation a un `namePattern` invariant par branche (utilise `{kpi}` au lieu de
`{base}` — ex. une mesure « direction »), la passe de base et la passe de
branche visent le même nom : la 1re (la base) est gardée, les suivantes sont
ignorées avec un avertissement (le csx écrasait silencieusement la même mesure ;
l'écriture TMDL doit dédupliquer sinon Power BI refuse de charger). Pour éviter
carrément l'essai en branche, restreindre : `"branches": {"YTD": {"variations":
[…sans la variation en {kpi}…]}}`.

Le csx reste la **solution de secours** quand seul Tabular Editor est
disponible (il fait la même chose côté modèle) :

### Utilisation (csx / Tabular Editor)

1. Ouvrir Power BI Desktop avec le projet → Outils externes → Tabular Editor.
2. Onglet **C# Script** → ouvrir le fichier (⚠ TE ne recharge PAS un .csx
   modifié sur disque : le rouvrir après chaque changement).
3. Exécuter → vérifier la grille de sortie → **Ctrl+S** pour pousser au modèle.
4. Enregistrer le PBIP dans Desktop.

Le chemin du `measures_config.json` est codé en dur en tête de script ; s'il
n'existe pas (poste du travail), une boîte de dialogue s'ouvre.

### Ce qu'il fait, dans l'ordre

1. **Découverte** : toutes les mesures de `settings.sourceTable` dont le
   displayFolder est `settings.sourceFolder` deviennent des « mesures de
   base ». Les mesures générées (annotation `MeasureVariation`) sont exclues —
   pas de variations de variations accidentelles. Elles sont triées **comme
   Power BI trie** (`sort_key_pbi`, réplique du comparateur culturel `.OrderBy`
   du csx). C'est l'ordre d'écriture dans le TMDL, et **le repli** de la
   colonne **Ordre** des paramètres de champ quand aucune colonne d'ordre
   n'est configurée (`indicateursXlsx.orderColumn`, plus bas) : dès qu'il
   diverge, l'ordre du paramètre ne colle plus à l'ordre alphabétique affiché
   par le rapport.

   Un tri ordinal Python diverge de **trois** façons — majuscules toutes
   devant (`Weight` avant `avg`), accentués rejetés après le Z (`Écart` après
   `Zone`), et apostrophes remontées en tête (`Nombre d'unités` avant `Nombre
   de jours`). `sort_key_pbi` reproduit donc les quatre niveaux de .NET, dans
   l'ordre : **lettres nues → accents → casse** (minuscule d'abord) **→
   ponctuation de liaison**. Cette dernière (`'`, `ʼ`, `-`, `­`, `–`, `—`,
   ensemble vérifié un à un contre `StringComparer`) est *ignorée* au premier
   niveau : `Nombre d'unités` se range entre `Nombre de jours` et `Nombre dz`,
   exactement comme dans le rapport. À radical égal, la variante ponctuée
   passe après (`Nombre dunites` < `Nombre d'unites`). ⚠ L'apostrophe
   TYPOGRAPHIQUE `'` (U+2019), elle, est significative pour .NET — elle n'est
   volontairement pas dans l'ensemble.
2. **Variations** (1re passe) : une mesure par (base × template).
3. **Switch** : une mesure `SWITCH(SELECTEDVALUE(selector), "KPI", [KPI], ...)`
   sur toutes les bases, puis toutes les variations dessus.
4. **Branches** (2e passe) : les variations déclarées comme branches (ex. YTD)
   deviennent des bases à leur tour.
5. **Cibles** (bases supplémentaires d'un dossier dédié, déclinées comme les
   KPI) : voir ci-dessous.
6. **Nettoyage** : si `removeOrphans`, supprime les mesures générées qui ne
   correspondent plus à la config.
7. **Paramètres de champ** : régénère l'expression complète des tables
   déclarées (voir §5).
7. **Rapport** : grille triable (Action / Objet) — créées, mises à jour,
   ignorées, orphelines supprimées, statut des paramètres.

### Mesures « cibles » (bases supplémentaires d'un dossier dédié)

Les **cibles/objectifs** d'un KPI ont une DAX de **base** spécifique (value-at-
close avec `LASTDATE`, source une table de cibles verticale filtrée par le nom
du KPI…) : impossible à générer par gabarit. Tu crées donc **à la main** la
cible **RACINE** par KPI (ex. `Weight cible`), toutes dans un **dossier dédié**.
Le générateur la traite comme une **base supplémentaire** et la **décline** —
chaque variation enveloppe `[Weight cible]`.

```json
"kpiMeasureFolders": [
  { "folder": "_cibles", "calcul": "Cible" }
]
```

**Portée par variation** (contrôlée dans l'UI, cases **Aux KPI** / **Aux
cibles** de l'éditeur de variations) : chaque variation décide si elle est
déclinée pour les KPI, les cibles, ou les deux. Une cible ne reçoit **que** ce
qui est coché « aux cibles » — typiquement pas la 7d avg ni la sparkline, mais
le YTD et surtout l'**écart réel−cible**. Défauts : Aux KPI **coché**, Aux
cibles **décoché** (comportement KPI inchangé ; les cibles ne prennent que ce
que tu choisis).

**Écart réel−cible** via le jeton **`{kpiRef}`** = la mesure du KPI dans la
même branche (`[Weight]` en Réel, `[Weight YTD]` en YTD) — à côté de `{baseRef}`
= la cible (`[Weight cible]`). Tu écris deux variations « aux cibles » seulement
(Aux KPI décoché, sinon elles vaudraient 0) :

| Variation | DAX | Donne |
|---|---|---|
| `écart` | `{kpiRef} - {baseRef}` | `[Weight] - [Weight cible]` |
| `écart %` | `DIVIDE({kpiRef} - {baseRef}, {baseRef})` | (réel − cible) / cible |

En branche YTD, l'écart devient automatiquement `[Weight YTD] - [Weight cible
YTD]` (le `{kpiRef}` suit la branche).

⚠ **N'écris pas `[{kpi}] - {baseRef}`** : `{kpi}` est le KPI *racine*, sans
branche, donc en YTD tu obtiendrais `[Weight] - [Weight cible YTD]` — le réel
courant comparé à la cible de l'année à date. Les deux côtés doivent être dans
la même branche : c'est `{kpiRef}` qu'il faut. (Voir le tableau des
placeholders §4 ; l'aide-mémoire est aussi affiché sous la zone DAX de
l'onglet Mesures.)

Au **paramètre de champ**, pour éviter toute collision avec les calculs du KPI
(même Indicateur = paramètre ambigu que Power BI refuse) :
- **Indicateur** = le KPI, retrouvé par le **préfixe du nom** (`Weight cible` →
  base `Weight`, préfixe le plus long) — c'est ce qui te donne le bon filtre ;
- **Calcul** = **« Cible »** pour la racine, **« Cible écart »**, **« Cible
  écart % »**… pour les variations (préfixé par le libellé configuré) ;
- **Branche** = gérée normalement (`Weight cible YTD` → Branche `YTD`, Calcul
  « Cible »).

Règles : ne mets que la cible **racine** dans le dossier — une mesure qui
ressemble déjà à une variation/branche (`… YTD`, `… 7d avg`) est **ignorée**
avec un avertissement (le générateur crée le reste). Une racine dont le préfixe
ne correspond à **aucun** KPI est ignorée. Le dossier doit être **différent**
de `sourceFolder` ; un dossier **imbriqué** (`_indicateurs\_cibles`) matche la
config `_cibles` par son **nom de feuille**.

Ça se configure dans la fenêtre **⚙ Réglages → « Mesures cibles
(dossier dédié) »** (tableau Dossier / Calcul, boutons Ajouter/Retirer) — pas
besoin d'éditer le JSON à la main. Le journal de la génération indique combien de
cibles racine ont été déclinées (ou, si 0, liste les dossiers présents pour
diagnostiquer).

### Idempotence et traçabilité

Chaque mesure générée porte l'annotation `MeasureVariation = "base|variation"`.
C'est ce qui permet : mise à jour en place, exclusion de la découverte, et
nettoyage des orphelines. `"dryRun": true` = rapport sans modification —
recommandé pour la première exécution sur un nouveau modèle.

---

## 4. measures_config.json — référence

### settings

| Clé | Rôle | Exemple |
|---|---|---|
| `sourceTable` / `sourceFolder` | où découvrir les bases | `_mesures` / `_indicateurs` |
| `dateColumn` | remplace `{date}` dans les DAX | `'dim_Date'[Date]` |
| `targetTable` | où créer les mesures (omis = table de la base) | `_mesures` |
| `displayFolderPattern` | dossier des variations | `{baseFolder}\_{variation}` |
| `branchFolderPattern` | dossier de la MESURE de branche (racine) | `{baseFolder}\__{branch}` |
| `overwriteExisting` | maj des mesures existantes | `true` |
| `removeOrphans` | supprime les générées hors config | `true` |
| `dryRun` | rapport seulement | `false` |

### variations (objet indexé par id)

```json
"Δ 30d": {
  "namePattern": "{base} Δ 30d",
  "inFieldParameter": true,
  "dax": ["VAR Cur = {baseRef}", "..."],
  "formatString": "delta",
  "description": "Variation de {base} vs 30 jours plus tôt"
}
```

| Clé | Rôle |
|---|---|
| `namePattern` | nom de la mesure générée |
| `dax` | chaîne OU tableau de lignes |
| `formatString` | voir « Formats » ci-dessous |
| `description` | description de la mesure |
| `inFieldParameter` | **opt-in** : `true` = entre dans les paramètres (défaut `false`) |
| `displayFolder` | dossier spécifique ; `{folder}` = dossier par défaut calculé |
| `folderVariation` | utilise le dossier d'une AUTRE variation (ex. les CF se rangent sous la variation qu'elles colorent, dans `{folder}\_CF`) |

### Placeholders (namePattern / dax / description)

Exemple de lecture : cible `Weight cible`, branche `YTD`.

| Placeholder | Valeur | Suit la branche ? |
|---|---|---|
| `{base}` | nom de la base traitée → `Weight cible YTD` | oui |
| `{baseRef}` | ↳ en référence DAX → `[Weight cible YTD]` | oui |
| `{kpi}` | **KPI racine, SANS branche** → `Weight` (un libellé, pas une réf) | **non — voulu** |
| `{kpiRef}` | ↳ la mesure du KPI **dans la branche** → `[Weight YTD]` (= `{baseRef}` pour un KPI ; ≠ pour une cible → écart réel−cible) | oui |
| `{branch}` | branche courante → `YTD` (vide en Réel) | — |
| `{date}` | `settings.dateColumn` | — |
| `{variation}` | id du template | — |
| `{deltaScale}` | `100` si la base a un format `%`, sinon `1` — deltas en points | — |

Dossiers seulement : `{baseFolder}` (dossier de la base — en 2e passe, racine
de la branche), `{folder}`.

> ⚠ **Le piège `{kpi}` / `{kpiRef}`.** Pour un écart réel−cible, écrire
> `[{kpi}] - {baseRef}` donne `[Weight] - [Weight cible YTD]` en branche YTD :
> le réel **courant** comparé à la cible **YTD**, deux périodes différentes.
> Utiliser `{kpiRef} - {baseRef}` → `[Weight YTD] - [Weight cible YTD]`. Les
> deux jetons existent exprès : `{kpi}` reste la racine (utile pour nommer ou
> pour un `LOOKUPVALUE` sur le KPI), `{kpiRef}` suit la branche.
>
> `{kpiRef}` prend le nom **réellement généré** pour la branche (via son
> `namePattern`), pas un suffixe supposé : une branche `Cumul` nommée
> `{base} cumul annuel` donne bien `[Weight cumul annuel]`.

### Formats

| Valeur | Comportement |
|---|---|
| `"inherit"` (ou omis) | copie le format de la base |
| `"delta"` | format **signé** à trois sections `+x;-x;x`, dérivé de la section positive de la base ; une base en `%` devient `pts` (le ×100 vient de `{deltaScale}` dans le dax) — voir « Symboles » ci-dessous |
| `"text"` | **AUCUN format** (FormatString null) — pour les mesures qui retournent du texte, ex. les hex des CF (vide/omis ≠ text : c'est inherit) |
| contient `{baseFormat}` | insère la section positive du format de la base |
| littéral | utilisé tel quel (ex. `"+#,0.0%;-#,0.0%;#,0.0%"`) |

#### Symboles d'un format « delta »

Power BI **n'ajoute jamais de signe tout seul** : dans un format multi-sections,
même le `-` du négatif doit être écrit, sinon la valeur s'affiche nue. D'où les
trois sections. Les symboles se règlent dans **⚙ Réglages** (un
aperçu montre le rendu en direct) :

```json
"settings": {
  "deltaSymbols": { "positive": "+", "negative": "-", "zero": "" },
  "deltaFallbackFormat": "#,##0.##"
}
```

| Réglage | Effet |
|---|---|
| `+` / `-` / (vide) | `+1 234` · `-1 234` · `0` — défaut |
| `▲ ` / `▼ ` / (vide) | `▲ 1 234` · `▼ 1 234` · `0` |

Avec une flèche, ne mets **pas** de `-` : la section négative affiche la valeur
en absolu, la flèche porte le sens. Tout symbole autre que `+` / `-` est
automatiquement mis entre guillemets pour ne pas être lu comme un code de
format (`#`, `0`, `.`, `,`, `%`, `E`…).

#### Littéraux : une espace est une espace

Un format contient parfois du texte brut (une espace, `$`, `pts`). Trois
écritures circulent : `"X"` (guillemets), `\X` (échappement), ou **rien**.
Dans un format Power BI/VBA, ces caractères **s'affichent d'eux-mêmes** :

```
espace   +   -   $   (   )
```

Ils n'ont besoin d'aucune décoration : `#,0.00 $` s'écrit tel quel. Seules les
lettres et les symboles demandent un backslash (`pts` → `\p\t\s`), sans quoi
le moteur peut les lire comme des codes de format.

Le générateur ramène donc tout littéral à cette forme minimale
(`normalize_literals`), quelle que soit l'écriture de la base :

| Base | Delta généré |
|---|---|
| `#,0.00\ $` · `#,0.00" $"` · `#,0.00 $` | `+#,0.00 $;-#,0.00 $;#,0.00 $` |
| `0.0\ %` | `+0.0 \p\t\s;…` (pourcentage → points) |
| symboles `▲ ` / `▼ ` | `\▲ #,0;\▼ #,0;#,0` |

L'éditeur avertit si tu tapes des guillemets ou un `\` devant une espace. Le
format de la mesure de **base** n'est jamais réécrit : il reste tel que Power
BI l'a produit.

##### Le format lu est la VALEUR, pas la ligne TMDL

TMDL entoure de guillemets toute valeur de propriété qui en contient
elle-même, en **doublant** ceux du dedans. Un format « secondes » saisi dans
Desktop comme `#,0 "s"` arrive donc sur le disque entouré de guillemets, avec
ceux du dedans doublés — trois guillemets en fin de ligne.

Lire la ligne telle quelle prenait ce **quoting de TMDL** pour une partie du
format, et les deltas en sortaient doublement abîmés :

| | avant | après |
|---|---|---|
| `#,0 "s"` | `+\#\,\0 \s` — un backslash devant **chaque** caractère, le format ne formate plus rien | `+#,0 \s;-#,0 \s;#,0 \s` |
| `+#,0 "s";-#,0 "s";…` | `++\#\,\0 \s\;…` — le `+` de la base n'étant plus en tête, le signe du delta s'ajoutait **par-dessus** | `+#,0 \s;…` idem |

Une même cause pour les deux : la valeur entière passait pour un littéral, et
`positive_section` ne voyait plus le signe déjà présent (le guillemet était en
tête). `unquote_tmdl_value` / `quote_tmdl_value` encadrent désormais lecture et
écriture, et sont exactement inverses. Le quoting n'est ajouté à l'écriture que
s'il est **nécessaire** (valeur commençant par un guillemet) : les formats
`pts` déjà présents dans les modèles restent identiques au caractère.

Le backslash restant devant le `s` est, lui, **indispensable** : une lettre nue
dans un format se lit comme un code (`s` = secondes).

⚠ **Le JSON double les backslashes à l'affichage.** Le même format apparaît
`0.0\ %` en TMDL et dans le champ de l'UI, mais `0.0\\ %` dans l'onglet JSON
brut — c'est l'échappement JSON, il n'en stocke qu'un. En retaper deux dans le
champ produit un backslash **littéral** à l'écran : l'éditeur avertit aussi sur
`\\`.

⚠ `deltaFallbackFormat` : si la mesure de **base n'a aucun `formatString`**
(fréquent — Desktop n'en écrit un que si tu l'as réglé), le delta n'héritait de
rien et n'avait donc **aucun format, donc aucun signe** — quels que soient les
symboles. Le repli lui donne un format numérique pour que le signe apparaisse.
`""` rétablit l'ancien comportement.

### Bibliothèque de variations

Le `measures_config.json` d'un rapport est **autonome** : ce qu'il contient est
exactement ce qui sera généré. À côté, un fichier **global** garde les
variations qu'on réutilise d'un rapport à l'autre — et on y **pioche**.

```json
// catalogue_variations.json  (hors projet)
{ "variations": { "7d avg": {...}, "YTD": {...}, "% du total": {...} },
  "branches":   { "YTD": {} } }
```

**Mesures → Bibliothèque…** ouvre deux listes face à face :

| | |
|---|---|
| **Importer →** | copie la variation de la bibliothèque **dans** le config du rapport |
| **← Publier** | l'inverse : une variation écrite ici part dans la bibliothèque |

Une fois importée, la variation **appartient au rapport** — rien à cocher ni à
retenir projet par projet, et la génération ne lit jamais la bibliothèque.

Trois comportements :

- une variation qui sert de **branche** amène son entrée `branches`, sinon la
  2ᵉ passe irait chercher une branche inexistante ;
- importer une variation **déjà présente** la remplace par celle de la
  bibliothèque — c'est ce qu'on demande en important — avec confirmation ;
- la copie est **profonde** : retoucher la variation dans le rapport n'altère
  pas la bibliothèque, et réciproquement.

**L'ordre** de la bibliothèque est celui de son fichier : c'est celui dans
lequel on la parcourt, et **dans lequel on importe** (une sélection multiple
arrive dans l'ordre de la liste, pas des clics). Sous la liste :
**↑ Monter / ↓ Descendre** déplacent la sélection d'un cran — un bloc
sélectionné bouge d'un seul tenant et s'arrête au bord — et **Trier A → Z** trie
tout par nom, sans tenir compte des majuscules ni des accents (après
confirmation : l'ordre actuel est remplacé pour toute l'équipe si le fichier
est partagé). Chaque changement est **écrit aussitôt** dans le fichier, comme
« Publier », puis relu : ce qui s'affiche est ce qui est sur le disque. La
liste « Dans ce rapport » suit l'ordre du config.

Le chemin du fichier est retenu au niveau de **l'application**, pas du projet :
pose-le sur un lecteur partagé et toute l'équipe y puise. Fichier absent ou
illisible = bibliothèque vide, jamais une erreur ; « Publier » le crée.

### branches

```json
"branches": { "YTD": {} }
```

La mesure générée par la variation YTD devient une base : `Weight YTD PY`,
`Weight YTD Δ 30d`, etc. `"variations": [ids...]` restreint la liste ; omise =
toutes (sauf la branche elle-même). **Un seul niveau** (pas de branche de
branche). Dossiers : la mesure YTD vit à la racine `__YTD`, ses variations
autour (`__YTD\_7d avg`...). Dans les paramètres, les rangées de branche
gardent les MÊMES libellés/index — c'est la colonne `Branche` qui distingue,
et la mesure de branche devient la rangée « Réel » de sa branche.

#### Substitution ou ENVELOPPE

Deux façons de dériver une variation en branche.

**Substitution** (défaut) : le DAX de la variation est ré-émis avec la mesure de
branche à l'intérieur — `variation(branche(base))`.

```dax
Weight YTD PY = CALCULATE([Weight YTD], SAMEPERIODLASTYEAR('dim_Date'[Date]))
```

**Enveloppe** : la branche entoure la variation Réel — `branche(variation(base))`.

```json
"branches": { "YTD": { "wrap": "CALCULATE({variationRef}, DATESYTD({date}))" } }
```
```dax
Weight YTD PY = CALCULATE([Weight PY], DATESYTD('dim_Date'[Date]))
```

Jeton `{variationRef}` = la mesure **Réel** de la variation. Deux gains :
toutes les mesures de la branche se ressemblent, donc un écart se débogue
forcément dans la variation Réel ; et un correctif apporté à celle-ci se
répercute **sans régénérer**, puisque la mesure est référencée et non recopiée.

> ⚠ **Ce n'est pas toujours équivalent**, d'où l'activation variation par
> variation (`wrapInBranch`, case « enveloppable en branche » dans l'éditeur) :
>
> | le DAX de la variation… | enveloppe |
> |---|---|
> | **décale** le contexte (`SAMEPERIODLASTYEAR`) | équivalent — `PY`, `YoY %`, `MTD` |
> | **épingle** une fenêtre sur la borne du contexte (`MAX({date})`, `DATEADD`, `DATESINPERIOD`) | **change le sens** — `7d avg` enveloppé redevient le 7d avg ordinaire, `Δ 7d` compare deux plages décalées |
>
> C'est le DAX de la variation qui décide, donc le drapeau vit sur elle ; la
> branche ne fournit que le patron.

Le patron sans variation cochée, ou une variation cochée sans patron : rien ne
change, on reste en substitution. Noms, paramètres de champ, annotations,
formats et propagation sont **inchangés** dans les deux cas — seul le DAX généré
diffère, donc l'essai se fait et se défait par une régénération.

### switch

```json
"switch": {
  "enabled": true,
  "name": "Switch KPI",
  "selector": "'TD_KPI'[mesure]",
  "displayFolder": "_switch",
  "formatString": "#,0.0",
  "dynamicFormat": false
}
```

UNE mesure qui bascule entre tous les KPI selon la sélection (sélection
**simple** requise sur le slicer), plus toutes ses variations — jamais dans
les paramètres de champ, rangées sous `_switch`. `dynamicFormat: true` donne à
la mesure switch un format DAX qui suit le KPI sélectionné (statique et
dynamique sont exclusifs ; le script gère la bascule dans les deux sens).

### fieldParameter

```json
"fieldParameter": {
  "tableNames": ["P_Indicateurs_parCalcul", "P_Indicateurs_parCalcul_2"],
  "tableNamesByKpi": ["P_Indicateurs_parKPI"],
  "byKpiUsesLabel": true,
  "tableNamesKpiBase": ["P_Indicateurs_base"],
  "kpiLabelLookup": {
    "table": "TD_Indicateurs", "keyColumn": "mesure",
    "labelColumn": "libelle_indicateur"
  },
  "kpiColumn": "Indicateur", "calcColumn": "Calcul", "branchColumn": "Branche",
  "noBranchLabel": "Réel", "includeBase": true, "baseLabel": "Réel"
}
```

Trois familles de tables, qui diffèrent par ce qu'on y **affiche** :

| Clé | Ce qu'on y choisit | Affichage |
|---|---|---|
| `tableNames` | le **calcul** (Réel, PY, Cible, YTD…) | le libellé du calcul |
| `tableNamesByKpi` | le **KPI** | son libellé (`byKpiUsesLabel`, défaut `true`) sinon le nom brut de la mesure |
| `tableNamesKpiBase` | KPI **et** calculs mélangés | libellé du KPI sur la rangée de base, libellé du calcul sur les variations |

`byKpiUsesLabel` : dans une table « par KPI », c'est le KPI qu'on sélectionne —
autant y lire `Poids` que `Weight`. Coché (défaut), l'affichage vient de
`kpiLabelLookup.labelColumn` via un `LOOKUPVALUE` ; décoché, c'est la colonne
clé (le nom de la mesure). Case dans **⚙ Réglages**.

Si la table de `kpiLabelLookup` est **absente du modèle**, le `LOOKUPVALUE`
rendrait la table paramètre invalide : la génération retombe alors sur le nom
brut et l'écrit au journal, plutôt que d'émettre un DAX cassé.

Voir §5.

### appliesToFormats — limiter une variation à un TYPE de base

Une variation n'a pas toujours de sens sur toutes les bases : un « % du total »
sur une mesure **déjà en pourcentage** donne un pourcentage de pourcentage.
Plutôt que de la créer puis de la corriger, on ne la crée **pas**.

Le type se déduit du `formatString` de la base :

| formatString | Type |
|---|---|
| `0.0 %`, `+#,0.0%;-#,0.0%;#,0.0%` | `pourcentage` |
| `#,0.00 $`, `€#,0.00` | `devise` |
| `#,0`, `0.0`, *(aucun format)* | `nombre` |

Un `%` **entre guillemets** est un littéral, pas un pourcentage — `0.0" %"`
compte comme un nombre. Une base sans format compte comme un nombre : on
n'exclut pas une mesure faute d'information.

#### Ce qu'un format ne peut PAS dire : `excludeNameContains`

Un **ratio en décimal** (0,85) porte exactement le même `formatString` qu'un
nombre ordinaire — `0.00`. Aucune déduction ne peut les séparer.

Mais le **nom**, lui, le dit presque toujours : « Ratio … », « … / … »,
« Taux … ». On exclut donc par fragment de nom, sans attribut supplémentaire à
tenir à jour nulle part :

```json
"excludeNameContains": ["ratio", "/", "taux"]
```

Une base dont le nom contient l'un de ces fragments ne reçoit pas la variation.
Le nom complet d'un KPI y a sa place aussi, pour l'écarter entièrement :

```json
"excludeNameContains": ["Weight"]
```

- insensible à la **casse** et aux **accents** (`duree` attrape `Durée`) ;
- le nom du **KPI** est testé en plus de celui de la base, donc exclure
  `Weight` écarte aussi `Weight cible` ;
- les **branches** héritent de l'exclusion ;
- l'**aperçu** suit le filtre.

#### Rattraper nommément : `includeNameContains`

Une règle large finit toujours par attraper un cas qu'elle ne devrait pas.
Exclure tout ce qui contient `average`, **sauf** `Average Steps` — parce que
cette mesure est en réalité une somme malgré son nom :

```json
"excludeNameContains": ["average"],
"includeNameContains": ["Average Steps"]
```

Le rattrapage **prime sur tout** : sur l'exclusion par nom **et** sur le filtre
de type. C'est une décision nommée, prise KPI par KPI, alors que les deux
autres filtres sont des règles larges — l'ordre est donc :

| Priorité | Règle | Effet |
|---|---|---|
| 1 | `includeNameContains` | **gardée**, quoi qu'en disent les autres |
| 2 | `excludeNameContains` | écartée |
| 3 | `appliesToFormats` | selon le type déduit du format |

Une base rattrapée ne compte pas dans le résumé des écartées, et ses
**branches** suivent.

Les deux champs sont côte à côte sur une ligne de l'éditeur de variations :
`nom contient — exclure : [ average ]  mais garder : [ Average Steps ]`.
Fragments séparés par des virgules ; c'est propre au modèle courant, d'où un
réglage par variation plutôt qu'un attribut de plus dans TD_Indicateurs.

```json
"appliesToFormats": ["nombre", "devise"]
```

Sélecteur dans l'éditeur de variations, sur la ligne **Portée** :
`types de base : [nombre, devise ▾]` — une liste déroulante à cases, qui tient
sur une ligne. « tous » = aucun filtre, et rien n'est écrit dans le config. **L'aperçu suit le filtre** : les bases exclues
disparaissent de la liste, donc on voit avant de générer. Le journal résume :

```
« pct total » : 1 base(s) écartée(s) par le filtre de format (Body Fat %).
```

Le filtre s'applique aussi aux **branches** et à la mesure **switch**.

### kpiTables — variations à PORTÉE (ALL / REMOVEFILTERS)

Certaines variations doivent **retirer les filtres** des tables du KPI : part du
total, moyenne toutes catégories, indice base 100… Le problème : chaque KPI vit
sur des tables différentes — parfois une, parfois plusieurs — alors que le DAX
d'une variation s'écrit **une seule fois** pour tous les KPI.

La liste se déclare dans **TD_Indicateurs** — une colonne où chaque KPI liste
ses tables, séparées par des virgules :

| mesure | libelle_indicateur | tables |
|---|---|---|
| Weight | Poids | `weight obs` |
| Total Steps | Pas | `steps, dim_Date` |
| Body Fat % | Gras | *(vide)* |

et le config ne retient que le **nom de la colonne** :

```json
"kpiTables": { "column": "tables", "fromMeasureDax": false }
```

C'est le point important : `measures_config.json` **voyage d'un rapport à
l'autre**, alors que les noms de KPI, eux, changent. Mettre la portée dans le
config le rendrait faux dès sa réutilisation ; dans TD_Indicateurs, l'attribut
vit avec le rapport et le config reste générique. (Même principe que
`kpiLabelLookup` et `hardcodedAttributes`.)

Une seule ligne dans **⚙ Réglages → Portée par KPI** : le nom
de la colonne (le détail est derrière le ⓘ). Excel absent ou colonne inconnue ?
Avertissement au journal, génération poursuivie — jamais d'arrêt brutal.

#### Le jeton générique `<<each …>>`

C'est **toi** qui écris la fonction DAX ; l'outil ne fait que la **répéter une
fois par table**, séparée par des virgules :

```
CALCULATE({baseRef}, <<each ALLSELECTED({table})>>)
```

| Tables du KPI | Résultat |
|---|---|
| `weight obs` | `ALLSELECTED('weight obs')` |
| `steps, dim_Date` | `ALLSELECTED('steps'), ALLSELECTED('dim_Date')` |

N'importe quelle fonction passe — `ALL`, `ALLSELECTED`, `REMOVEFILTERS`,
`ALLEXCEPT`, `VALUES`, `CROSSFILTER`… — parce que rien n'est codé en dur côté
outil. Deux substitutions dans le fragment :

| Dans le fragment | Vaut |
|---|---|
| `{table}` | la référence DAX → `'steps'` |
| `{tableName}` | le nom nu → `steps` |

`{table}` peut revenir plusieurs fois dans le fragment :

```
<<each ALLEXCEPT({table}, {table}[Date])>>
  →  ALLEXCEPT('steps', 'steps'[Date]), ALLEXCEPT('dim_Date', 'dim_Date'[Date])
```

Plusieurs `<<each …>>` peuvent coexister dans un même DAX. Le fragment ne peut
pas contenir `>>` (fin du jeton).

**Raccourcis** pour les cas courants, si tu ne veux rien écrire :
`<<allTables>>` (= `<<each ALL({table})>>`), `<<removeFilters>>`, et
`<<tables>>` (la liste nue : `'steps', 'dim_Date'`).

#### Déduire la portée du DAX

Case **« déduire du DAX si la colonne ne dit rien »** : pour un KPI sans portée
déclarée, les tables sont lues dans le DAX de sa mesure de base —
`SUM('weight obs'[weight])` donne `weight obs`. Une référence de mesure
(`[Weight]`) n'est pas une table et n'est pas retenue.

La colonne n'est **jamais** écrasée : la déduction ne comble que les trous. Ce
qu'elle trouve part au journal, à vérifier :

```
Portée déduite du DAX (vérifie-la) : Average Steps -> steps · Weight -> Weight LOCF
```

⚠ Elle voit **toutes** les tables citées, y compris une table technique ou une
table de dates servant à un filtre — ce n'est pas toujours la portée voulue.
Pratique pour démarrer ou pour un modèle simple ; la colonne reste la référence
dès qu'on veut être précis.

Un KPI **sans** portée déclarée (cellule vide) ne reçoit tout simplement pas la
variation, et le journal dit lequel et pourquoi — pas de mesure à moitié
construite. Les
**cibles** héritent de la portée de leur KPI. La mesure **switch**, qui n'est
propre à aucun KPI, n'en a pas : une variation à portée la saute.

#### Recette complète : « % du total »

C'est le cas qui combine tout — portée par KPI, jeton générique, filtre de type.

| Réglage | Valeur |
|---|---|
| namePattern | `{base} % du total` |
| DAX | `DIVIDE({baseRef}, CALCULATE({baseRef}, <<each ALLSELECTED({table})>>))` |
| formatString | `#,0.0 %` |
| Portée | ☑ KPI |
| types de base | nombre, devise (pas `pourcentage`) |
| exclure si le nom contient | `ratio, /, taux` |
| mais garder | *(vide, ou les exceptions à rattraper)* |

`ALLSELECTED` (et non `ALL`) pour que le total suive les filtres du rapport —
le « total » est celui de la sélection en cours. Le résultat, par KPI :

```
Weight % du total       = DIVIDE([Weight], CALCULATE([Weight], ALLSELECTED('weight obs')))
Total Steps % du total  = DIVIDE([Total Steps], CALCULATE([Total Steps],
                                   ALLSELECTED('steps'), ALLSELECTED('dim_Date')))
```

et **rien** pour `Body Fat %`, qui est déjà un pourcentage.

> `hardcodedAttributes` lit d'autres colonnes du même Excel pour figer un
> attribut quelconque dans le DAX (jetons `<<label>>`). `kpiTables` réutilise
> son `xlsx` et son `keyColumn` par défaut : une seule source d'attributs.

### indicateursXlsx — l'Excel des indicateurs, défini UNE fois

`TD_Indicateurs.xlsx` décrit les KPI (libellé, direction, couleurs, portée,
type…). Il était configuré à **deux endroits** — dans ce fichier pour les
jetons `<<…>>`, et dans l'onglet Rapport pour les couleurs de matrice — deux
réglages qui pouvaient diverger sans prévenir. Une seule définition désormais :

```json
"indicateursXlsx": {
  "path": "TD_Indicateurs.xlsx",
  "keyColumn": "mesure",
  "fillColumn": "couleur_fill",
  "textColumn": "couleur_text",
  "orderColumn": "ordre"        // facultatif — vide = ordre alphabétique
}
```

Se règle dans **⚙ Réglages → Excel des indicateurs** (avec un
sélecteur de fichier et les colonnes proposées d'après les en-têtes réels).
Tout ce qui est au défaut n'est pas écrit — le config reste propre, et le bloc
disparaît entièrement si rien ne change.

#### Travailler dans l'Excel avec l'outil ouvert

Le contrat : **l'outil ne tient jamais le classeur**, sauf le temps d'une
action qu'on a lancée. On peut donc éditer dans Excel, enregistrer, puis
lancer une génération — sans jamais être mis dehors.

Trois règles, dans `moteurs/xlsx_lecture.py` et la couche UI :

| | |
|---|---|
| **lecture sur instantané** | le classeur est copié dans le temporaire, et c'est la copie qu'openpyxl analyse. On ne touche à l'original que le temps d'une copie d'octets, pas de toute l'analyse XML — et une lecture réussit même si Excel tient le fichier |
| **en-têtes en mémoire** | lus une fois au démarrage pour peupler les menus de colonnes ; se promener dans l'outil ne rouvre plus rien. Le bouton **↻** force la relecture (après avoir ajouté une colonne), et changer de chemin la déclenche tout seul |
| **exécutions toujours fraîches** | génération, couleurs, jetons `<<…>>`, ordre des KPI : chacune relit le disque. Ce qu'on vient d'enregistrer dans Excel est pris en compte sans rien rafraîchir |

> **Ce qui clochait.** openpyxl en mode `read_only` ne charge rien en mémoire :
> il garde le `.xlsx` **ouvert** et y lit à la demande. Un `close()` oublié
> (c'était le cas de l'option couleurs) laissait le fichier tenu par le
> processus, et Excel ne pouvait plus l'enregistrer — il écrit un temporaire
> puis le **substitue** au fichier, ce qu'un handle ouvert fait échouer. Le
> symptôme était **intermittent** : les objets openpyxl se référencent en
> cycle, donc seul un passage du ramasse-miettes libérait le fichier, quand il
> passait. Toute lecture passe désormais par un `finally`.

Seule exception, assumée : **« Couleurs des KPI » écrit** dans le classeur.
Cette écriture-là doit forcément prendre le fichier ; si Excel l'a ouvert, le
dialogue le dit (« ferme-le et réessaie ») au lieu d'échouer en silence.

Un chemin **relatif** est résolu depuis le dossier du `.pbip` ; le sélecteur
re-relativise automatiquement un fichier choisi dans le projet, pour que le
config reste transportable d'un rapport à l'autre.

Qui s'en sert :

| Usage | Colonnes |
|---|---|
| jetons `<<label>>` figés dans le DAX | `keyColumn` + celles de `hardcodedAttributes.tokens` |
| portée par KPI (`<<each …>>`) | `keyColumn` + celle de `kpiTables.column` |
| **couleurs des matrices** (onglet Rapport) | `keyColumn`, `fillColumn`, `textColumn` |
| **ordre des KPI** dans les tables paramètre | `keyColumn`, `orderColumn` |

#### orderColumn — choisir l'ordre des KPI

Par défaut les KPI sortent dans l'ordre **alphabétique** (`sort_key_pbi`,
section 6). `orderColumn` nomme une colonne de l'Excel qui prend la main : sa
valeur devient la colonne **Ordre** des tables paramètre, et donc l'ordre du
slicer (`sortByColumn`).

| | |
|---|---|
| valeurs numériques | comparées comme des **nombres** — `10` vient après `9`, pas entre `1` et `2`. Numérote par 10 pour pouvoir intercaler |
| valeur texte | acceptée, rangée **après** les nombres, alphabétiquement |
| KPI absent de la colonne, ou cellule vide | rangé **à la fin** (pas en tête : la place la plus visible ne doit pas revenir à la seule ligne dont personne n'a décidé) — et nommé dans le journal |
| deux ex æquo | départagés alphabétiquement, donc de façon **stable** : re-générer ne rebrasse pas la table |
| colonne introuvable | avertissement, repli sur l'alphabétique — jamais une génération qui échoue |

L'ordre vit dans l'Excel, **avec le rapport** : le config ne retient que le nom
de la colonne, donc il reste transportable. UI : **⚙ Réglages
→ Excel des indicateurs → « Ordre des KPI »** (vide = alphabétique).

L'onglet Rapport n'a plus de champs propres : il **affiche** ce que le config
dit (et signale en clair si le fichier est introuvable), relu à chaque usage —
un réglage enregistré dans l'onglet Mesures est donc pris en compte aussitôt.

> Compatibilité : un config plus ancien qui ne porte l'Excel que sous
> `hardcodedAttributes.xlsx` / `.keyColumn` reste lu. À la première
> sauvegarde, la définition migre vers `indicateursXlsx` et ces clés-là sont
> retirées.

### hardcodedAttributes (figer un attribut du KPI dans le DAX)

Au lieu d'un `LOOKUPVALUE(TD_Indicateurs[direction], …, "{kpi}")` coûteux à
l'exécution, on **fige** la valeur au moment de la génération.

```json
"hardcodedAttributes": {
  "tokens": { "direction": "direction" }   // label -> colonne d'attribut
}
```

Dans le DAX d'une variation, écris **`<<label>>`** (ex. `<<direction>>`). À la
génération, pour la mesure du KPI *X*, le jeton est remplacé par la valeur de la
colonne (ligne `mesure == X` dans l'Excel). Valeur **brute** : un entier donne
`1`/`-1` (pour du texte, quote toi-même : `"<<label>>"`). Un KPI absent de
l'Excel (ex. `Switch KPI`) → la mesure n'est **pas générée** (avertissement),
pour ne jamais écrire du DAX cassé. Re-générer après avoir modifié l'Excel met
les valeurs à jour. UI : **⚙ Réglages → « Attributs
codés en dur »** (colonne au menu déroulant, label à côté).

---

## 5. Les paramètres de champ — comment s'en servir

Trois tables, **mêmes rangées**, deux orientations. Colonnes : affichage,
champs (NAMEOF, cachée), ordre (cachée), `Indicateur` (= nom de la mesure,
clé vers TD_KPI), `Calcul`, `Branche`.

| Table | Affichage | Pour |
|---|---|---|
| `P_Indicateurs_parCalcul` | nom du calcul (`7d avg`, `PY`...) | **1 KPI × plusieurs calculs** : le KPI vient de TD_KPI, l'axe montre les calculs |
| `P_Indicateurs_parCalcul_2` | idem | copie indépendante — 2e sélection sur la même page |
| `P_Indicateurs_parKPI` | nom du KPI | **1 calcul × plusieurs KPIs** : slicer `Calcul` (sélection simple) + l'axe montre les KPIs |

**À faire une fois dans TE après création** : une relation
`TD_KPI[mesure] → P_xxx[Indicateur]` **par table** (l'interface de Desktop
refuse souvent ces relations ; via TE ça fonctionne).

Règles de tri (pourquoi les index se répètent) : la colonne d'affichage est
triée par la colonne d'ordre, et un même libellé doit pointer vers UN seul
index. Donc index par calcul dans les tables parCalcul, par KPI dans parKPI,
et les rangées de branche réutilisent l'index de leur calcul. Les trous dans
la séquence sont normaux.

Si Desktop refuse la **création** d'une table calculée par outil externe :
créer un paramètre bidon du même nom via l'interface (Modélisation > Nouveau
paramètre > Champs), relancer le script (la mise à jour passe), et l'exécution
suivante renomme les colonnes `Value4`-`Value6`.

---

## 6. Les trois façons de construire un visuel

1. **Paramètre parCalcul** — page « détail d'un KPI » : TD_KPI filtre le KPI,
   le visuel montre Base/7d avg/Δ.../PY..., slicer `Branche` pour basculer
   Réel ↔ YTD. Le formatage conditionnel exige des entrées par KPI → c'est le
   rôle de `propagate_cf.py`.
2. **Paramètre parKPI** — page « comparaison » : slicer `Calcul` en sélection
   simple, l'axe/la légende montre les KPIs.
3. **Mesures Switch** — un seul jeu de mesures (`Switch KPI`, `Switch KPI Δ
   30d`...) qui suit la sélection TD_KPI. Avantage décisif : le **CF est
   dynamique** (un seul binding, aucun script de propagation). Limites :
   sélection simple obligatoire, format statique sur les variations.

Règle pratique : Switch pour les tuiles/cartes pilotées par un slicer KPI ;
paramètres pour les tableaux/matrices et tout ce qui liste plusieurs champs.

---

## 7. propagate_cf.py (rapport)

**Problème résolu** : avec un paramètre de champ, le formatage conditionnel
est ancré à une mesure précise (`selector.metadata = "_mesures.Total Steps
YoY %"`). Quand le slicer change de KPI, le CF disparaît.

**Solution** : tu configures le CF UNE fois sur le KPI template dans Desktop ;
le script clone l'entrée pour chaque KPI (selector + mesure CF adaptés).
Plusieurs familles de KPI, des exceptions : c'est la **grille des sources**,
plus bas.

Ça couvre aussi les **étiquettes de référence** (carte) : valeur, **titre custom**
et détail. Subtilité : sur une carte à paramètre, chaque KPI est un *point de
donnée* du paramètre, et le **titre** a deux propriétés aux portées **opposées** :

- `titleContentType` (la bascule *source* : Custom vs Nom du champ) → doit rester
  au **niveau champ** (`{metadata, id}`, sans `dataViewWildcard`). Ajouter la
  portée point de donnée fait que Power BI l'**ignore** → le titre retombe sur
  « nom du champ ».
- `titleText` (le texte) → doit être au **niveau point de donnée**
  (`dataViewWildcard`, comme la valeur) pour suivre le paramètre sur chaque KPI.

Les deux ne peuvent donc pas cohabiter dans un même selector : le script
**scinde** chaque titre en une entrée *source* (niveau champ) et une entrée
*texte* (niveau point de donnée), pour le template comme pour les clones. Il
répare aussi les entrées combinées héritées. Résultat : un titre custom posé sur
le KPI template s'affiche, source ET texte, sur tous les KPI cibles.

Généralisation (display units, détail, etc.) : une propriété est « point de
donnée » si elle est **portée par une mesure** (`value`, `detailValue` du
détail, couleur CF…) ou connue littérale (`titleText`) — sinon elle reste au
**niveau champ** tel que Desktop l'écrit (titleContentType, `labelDisplayUnits`,
`show` du détail…). La règle « porte une Measure » évite de coder en dur chaque
nom : le détail à mesure (que Desktop nomme `detailValue`, pas `value`) est
reconnu automatiquement — lui
ajouter le wildcard ferait que Power BI l'ignore (retour au défaut, ex.
display units « Automatique ») **et Desktop PURGE l'entrée ignorée à la
sauvegarde suivante** (c'est comme ça que des réglages « disparaissent »).
La **scission** s'applique à toutes les entrées mixtes des clés
`referenceLabel*` — dont le **détail à mesure** ({show, value} : le `show`
part au niveau champ, la mesure d'écart au niveau point de donnée, permutée
par KPI×branche). Le script **répare** les entrées abîmées par une version
antérieure (wildcard pur retiré).

**Plusieurs étiquettes sur une même carte** : chaque étiquette de référence
porte un `selector.id` propre (« field-<uuid> »), et son titre/détail s'y
rattachent par cet id. La clé de déduplication inclut donc `id` **et** `order`
— sans ça, deux étiquettes du même KPI (même metadata, même propriété `value`)
collidaient et seule la dernière était propagée. Chaque étiquette est désormais
clonée séparément, avec son détail (ou son absence de détail). ⚠ Un réglage purgé par Desktop doit être
REPOSÉ dans Desktop avant de re-propager (le script ne peut pas ressusciter ce
qui n'est plus dans le fichier). Et le **Réel du template est MAÎTRE** : ses
entrées ne sont jamais réécrites par un clone, et une entrée de branche du
template (relique d'un run précédent) ne sert plus de source quand une entrée
Réel équivalente existe — modifier le Réel rafraîchit donc branches ET cibles,
sans jamais se faire écraser en retour.

```python
TEMPLATE_KPI    = "Total Steps"            # le KPI dont le CF fait foi
TARGET_KPIS     = None                     # None = auto via le tmdl du paramètre
FIELD_PARAMETER = "P_Indicateurs_parCalcul"
ENTITY          = "_mesures"
```

**Procédure** : configurer le CF sur le template → enregistrer le PBIP →
**fermer Desktop** → `py propagate_cf.py` → rouvrir. Idempotent : le template
est maître, les clones sont remplacés à chaque exécution. Le remplacement de
noms est borné au début des noms de mesures (pas de collision entre
« Average Steps » et « Average Sleep Duration »).

### Cibles : la branche via le paramètre de champ (pas via le nom)

Une mesure de KPI a la branche juste après le KPI (`Weight YTD PY`), mais une
**cible** l'a après « cible » (`Weight cible YTD`). Insérer bêtement la branche
après le KPI donnerait `Body Fat % YTD cible` — une mesure qui n'existe pas, et
la cible « ne se propage pas » sur les branches. Donc au lieu de parser le nom,
la propagation lit le **paramètre de champ** (`read_fp_maps`) : chaque mesure y
porte sa `(Indicateur, Calcul, Branche)`. Pour propager, on relit la
`(KPI, Calcul, Branche)` de la mesure source et on cherche la mesure cible
`(autre KPI, MÊME Calcul, autre branche)` — `Weight cible` (Cible/Réel) →
`Body Fat % cible YTD` (Cible/YTD), sans jamais toucher au nom.

**Les mesures dérivées hors paramètre suivent aussi**, par le **plus long
préfixe** connu. Beaucoup de mesures n'entrent pas dans le paramètre
(`inFieldParameter: false` — couleurs de formatage conditionnel, sparklines)
alors que leur *racine*, elle, y est. `Weight cible ecartCF` n'est pas mappée,
mais `Weight cible` l'est : on traduit la racine (→ `Body Fat % cible YTD`) et
on recolle le reste (`ecartCF`) → `Body Fat % cible YTD ecartCF`. Sans ça, ces
mesures-là retombaient sur le remplacement par le nom et produisaient
`Body Fat % YTD cible ecartCF`, **inexistant** — exactement le symptôme que la
correction par paramètre était censée supprimer, mais qui survivait pour les
couleurs CF, c'est-à-dire le cœur de métier de `propagate_cf`. Le préfixe ne
traverse jamais les KPI (on n'apparie qu'à l'intérieur du KPI source).
`detect_branch` applique la même règle : une dérivée hérite de la branche de sa
racine.

#### Mesures communes à plusieurs branches

Le plus long préfixe a sa limite : il suppose que la mesure dérivée **a** une
variante par branche. Un titre, un libellé, une unité — une mesure unique
partagée par le Réel et le YTD — n'en a pas. Elle se voyait quand même coller
le suffixe (`Total Steps titre` → `Total Steps YTD titre`), donc une référence
morte : le visuel perdait l'attribut.

La règle est désormais simple : **la propagation n'écrit jamais une référence
vers une mesure absente du modèle.** Elle lit les noms réellement présents
(`measures_of_model`) et descend une cascade d'intentions :

| | on essaie | cas visé |
|---|---|---|
| 1 | la variante de la branche visée — `Weight YTD` | la mesure a bien ses branches |
| 2 | le même KPI **sans** branche — `Weight titre` | un titre par KPI, commun à ses deux branches |
| 3 | la mesure d'origine, inchangée | un titre commun à tout le rapport |

Les candidats viennent de **deux** sources, et les deux sont tentées : le
paramètre de champ d'abord (fiable, aucun parsing), puis le nom. Ne s'arrêter
qu'aux premiers était un piège : un paramètre sans ligne « Réel » pour le KPI
visé (il n'a que sa ligne YTD) coupait la cascade avant le repli par le nom, et
le titre du KPI **template** restait sur les faces YTD de tous les autres.

Rien à déclarer dans le config : l'existence dans le modèle **est** la
déclaration. Le journal liste en fin de course les mesures gardées telles
quelles — si l'une d'elles devrait avoir une variante, c'est qu'elle manque au
modèle, et il suffit de la générer puis de relancer.

Modèle introuvable → la vérification se désactive d'elle-même (ancien
comportement) plutôt que de tout bloquer.

### La grille des sources : une base, des groupes, un gabarit par variation

De quel KPI chaque KPI copie-t-il le formatage de chaque variation ? Une
**grille** KPI × variation répond, case par case, et plusieurs **gabarits**
s'y partagent le travail :

- le **gabarit de base** sert à **tout le monde** : on le formate en entier
  dans Desktop, et ce qu'aucune règle plus précise ne décide vient de lui ;
- un **groupe** est une famille de KPI qui se propagent **entre eux** : son
  gabarit — un de ses membres — donne aux autres. Un KPI n'est que dans un
  groupe ; le gabarit de base, dans aucun ;
- la ligne **« Tous les KPI »** donne un **gabarit par variation**, pour tout
  le monde, **groupes compris** : le PY se formate une fois, sur un KPI, et
  vaut partout — c'était tout l'enjeu, chaque gabarit de groupe devait
  sinon porter le PY lui aussi ;
- une ligne de **groupe** peut aussi avoir un gabarit par variation (le YoY %
  de la famille Sommeil vient de Weight) ;
- une **case** peut avoir sa propre règle : copier un autre KPI, ou rester
  **« à la main »** — rien ne lui est copié, elle garde ce qui est formaté
  sur elle.

**Priorité** — pour une case, la première règle qui répond l'emporte :

| | règle | où la poser |
|---|---|---|
| 1 | la case elle-même (ce KPI, cette variation) | une case de KPI |
| 2 | son groupe, pour cette variation | la ligne du groupe |
| 3 | tous les KPI, pour cette variation | la ligne « Tous les KPI » |
| 4 | ce KPI, toutes ses variations | le fichier seulement |
| 5 | le gabarit de son groupe | menu Groupes |
| 6 | le gabarit de base | en haut de la fenêtre |

Une règle **pour une variation** passe donc avant une règle « toutes
variations », et à niveau égal, le plus étroit gagne (KPI > groupe > tous).

Dans Desktop, on formate la base **en entier**, chaque gabarit de groupe pour
ce qui fait sa famille, et un gabarit par variation pour ce qui vaut partout.
Contrepartie, voulue : ce qu'un KPI porte hors de ce que ses règles lui
laissent est remplacé à la prochaine propagation — c'est ce qui fait tenir le
tout. La sauvegarde de l'action défait tout.

Les colonnes sont les **variations**, lues dans les **noms des mesures** qui
existent — qu'elles soient dans le paramètre de champ ou non (sparkline,
couleurs CF…) : le Réel, les variations du KPI dans l'ordre du config, puis
chaque **cible** et ses variations, puis le reste. Une variation vit sur
**toutes ses branches** — la case « PY » couvre `Weight PY` et `Weight YTD PY`
—, donc une branche (YTD) n'est pas une colonne à elle : la colonne « Réel »
couvre `Weight` et `Weight YTD`.

**Sur une carte, une entrée appartient à la variation qu'elle MONTRE.**
D'ordinaire, le selector d'une entrée dit sa variation : la série
`Weight YTD PY` d'un graphique, la colonne `Weight PY` d'une matrice. Mais sur
une carte, toutes les entrées visent la mesure du KPI (`_mesures.Weight`) — la
variation est dedans : une **étiquette de référence** montre `Weight PY` en
valeur, son titre et son détail s'y rattachent par le même `selector.id`, et
l'**image** de la carte est `Weight sparkline`. Elles vont donc dans les
colonnes PY et sparkline ; seuls les réglages de la carte entière (sans id)
restent au Réel. Avant, tout tombait au Réel : sur une page de cartes, un
gabarit par variation n'avait rien à donner, et seul le gabarit de base
propageait.

Une **cible** est une base à part entière, déclinée comme un KPI : ses
variations ont leurs colonnes, au nom que le générateur leur donne au
paramètre de champ — `Weight cible` est dans « Cible », `Weight cible écart`
et `Weight cible YTD écart` dans « Cible écart ». Une cible se reconnaît à son
dossier dédié (`kpiMeasureFolders`), ou au paramètre de champ seul (un Calcul
qui n'est ni le Réel ni une variation). Un KPI qui a une cible a donc ses
variations de cible, même absentes du paramètre ; un KPI sans cible y lit
« pas de mesure ». Et quand une case copie un KPI qui n'a PAS la mesure — la
base, souvent, qui n'a pas de cible —, la case est en retrait et le verdict
le dit : rien ne lui serait copié, donne la colonne à un KPI qui a une cible
(ligne « Tous les KPI »).
Pour ranger une mesure dans sa colonne : le paramètre de champ d'abord (son
Calcul), sinon le suffixe d'une variation du config (le plus long d'abord :
`CF YoY %` n'est pas du `YoY %`), une cible (dossier dédié), et à défaut le
Réel du KPI. Une règle vaut dans **tous les visuels** (plus tard : par
visuel, pour les gros rapports — un champ de plus dans le fichier, sans rien
changer au reste).

```json
{ "version": 2,
  "base": "Average Steps",
  "colonnes": { "PY": "Average Steps" },
  "groupes": [
    { "nom": "Sommeil",
      "kpis": ["Average Sleep Duration", "Sleep Score"],
      "base": "Average Sleep Duration",
      "colonnes": { "YoY %": "Weight" } } ],
  "exceptions": [
    { "source": "Weight", "kpis": ["Body Fat %"], "variations": ["YoY %"] },
    { "source": "(manuel)", "kpis": ["Total Steps"], "variations": ["Réel"] } ] }
```

`"(manuel)"` = « à la main ». Une exception sans `"variations"` vaut pour
toutes (niveau 4). Le gabarit d'un groupe en est membre d'office.

**Une source est toujours sa propre source** pour ce qu'elle donne : Weight,
qui donne son YoY % à la famille Sommeil, le garde — c'est implicite, inutile
de l'écrire. C'est la seule contrainte, et elle tient tout : une **copie de
copie** (Body Fat % copie Weight, qui copie lui-même la base) ferait dépendre
le résultat de l'ordre des passes. Elle est **refusée**, coupable nommé, et
rien n'est écrit. Refusés aussi : une source inconnue, une case à deux
sources, un KPI dans deux groupes, le gabarit de base dans un groupe. Un KPI
absent du modèle est signalé et ignoré.

**Les pertes sont annoncées avant d'écrire.** Une case qui copie un KPI qui
n'a **rien** pour cette variation, dans un visuel que ce KPI pilote, perd son
formatage — le miroir : ce que la source ne porte plus est retiré. C'est voulu
quand on retire un réglage d'un gabarit ; sur une case qu'on croyait couverte,
c'est une perte. La grille la marque d'un **coin orange**, le journal la
chiffre avant la première passe. Cas typique : une cible que la base n'a pas →
donne-la à tous les KPI depuis un KPI qui l'a.

#### La fenêtre « Grille des sources… »

Onglet **Rapport** → **Grille des sources…**. En haut, le gabarit de base ;
puis une ligne **« Tous les KPI »**, chaque groupe (sa ligne, puis ses KPI),
et les KPI **sans groupe**. Tout est dit **en mots** — pas de symbole à
décoder :

| dans une case de KPI | |
|---|---|
| `Gabarit` | formaté à la main dans Desktop, et copié par d'autres (l'infobulle dit qui) |
| `À la main` | formaté à la main, rien n'y est copié |
| le nom d'un KPI | la case copie ce KPI — **en gras** si la règle est posée sur la case, en clair si elle hérite (d'un groupe, de « Tous les KPI », d'un gabarit) |
| `pas de mesure` | ce KPI n'a pas cette variation : rien à y écrire |
| `non propagé` | aucune règle ne s'y applique (pas de gabarit de base) |
| un coin orange | du formatage serait retiré (l'infobulle dit pourquoi) |

La couleur d'une case est celle de sa source — franche quand la règle est
posée là, pâlie quand elle hérite — et une légende nomme le KPI derrière
chaque couleur. Les lignes « Tous les KPI » et de groupe ne montrent que les
règles posées à leur niveau (vide = aucune). Les en-têtes nomment le gabarit
de base et les gabarits de groupe. L'ordre de priorité est rappelé en haut.

On sélectionne des cases (clic-glisser, ou un en-tête de ligne ou de colonne),
puis **Copier depuis [KPI] → Appliquer**, **À la main** ou **Retirer la
règle** (la case suit de nouveau la règle plus large) — aussi au clic droit.
Le bouton **Groupes** : nouveau groupe avec les KPI sélectionnés (son gabarit
est le premier, à changer ensuite), ajouter ou retirer des KPI, choisir le
gabarit d'un groupe (un membre, « à la main » pour chacun, ou aucun : ses KPI
suivent la base), renommer, supprimer.

La fenêtre **ne sait pas fabriquer** une grille incohérente :

- copier un KPI en fait le gabarit de cette variation ;
- repeindre un gabarit emmène ceux qui le copiaient — ceux-là seulement : un
  groupe qui suivait son propre gabarit ne bouge pas ;
- un KPI qui copie ailleurs **par ta règle** et que d'autres copient : ceux-là
  copient directement la même source, ta règle tient ;
- le **dernier** copieur parti, un gabarit redevient une case ordinaire ;
- **ce que tu poses reste posé**, même égal à ce qui serait hérité — un PY
  « pour tous » posé avant tout groupe tient quand un groupe apparaît.

Chaque action qui en entraîne d'autres le dit sous la grille. **Enregistrer**
écrit `propagation.json` ; fermer avec des changements demande confirmation.

L'onglet résume la grille (« Gabarit de base : Average Steps · 1 groupe ·
1 gabarit par variation »), dit quel fichier il lit, et **refuse de propager
sans grille** : choisir le gabarit à la place de l'usager réécrirait un
rapport entier depuis un KPI arbitraire. Un KPI tout neuf suit la base, sans
rien toucher.

#### L'ancien format

Un `propagation.json` d'avant (`{"groupes": [...]}` avec un gabarit par
groupe) marche **tel quel** : le groupe sans liste de KPI devient la base,
chaque autre groupe reste un **groupe** avec son gabarit, dans le même ordre
de passes — le résultat est **identique au caractère** à celui de l'ancien
moteur (vérifié sur quatre configurations, dont celle du rapport Fitbit). Un
KPI dans aucun groupe, sans groupe par défaut, reste non propagé.
Enregistrer la grille réécrit le fichier au format actuel.

**Un fichier par dossier**, à côté des `.pbip` : `propagation.json`. Toutes les
versions d'un rapport — noms un peu différents, même dossier — lisent la
**même** grille : les réglages de propagation ne changent pas d'une version
à l'autre. Pas dans `measures_config.json`, qui voyage d'un rapport à
l'autre : des noms de KPI n'y auraient pas leur place.

Contrepartie : deux rapports vraiment DIFFÉRENTS dans un même dossier
partageraient aussi leur grille. Un KPI absent d'un modèle y est ignoré
(avertissement), une source absente arrête la propagation en la nommant —
jamais une écriture fausse.

Avant, le fichier portait le nom du rapport (`<rapport>.propagation.json`).
Il reste **lu en repli** tant qu'il n'y a pas de `propagation.json` ; s'il est
**seul** dans le dossier, il est **renommé** en `propagation.json` à
l'ouverture du projet (le journal le dit). S'il y en a plusieurs, on ne
devine pas lequel partager : chaque rapport lit le sien jusqu'au premier
enregistrement de la grille, qui écrit `propagation.json`.

#### Ce qui rend le découpage sûr

`process_visual` travaille par **cases** : chaque passe — une par source —
reçoit les siennes, `(KPI, variation)`, et un classeur qui range chaque entrée
dans sa case. Trois ensembles, à ne pas confondre :

- **le périmètre d'écriture** : les cases de la passe. Le miroir ne retire
  **que** là — sans quoi la passe de la base emporterait le formatage des
  exceptions, dans le même visuel ;
- **ce que la source donne** : ses entrées dans SES cases. Weight, source du
  YoY % d'un groupe, ne donne pas son Réel : c'est la passe de la base qui
  s'en charge ;
- **le découpage des noms** (`_managed` = *tous* les KPI du rapport) : sert
  uniquement à savoir quel KPI une mesure vise. Restreint à une passe, un KPI
  voisin dont le nom commence par celui de la source (`Total Steps Goal` face
  à `Total Steps`) serait pris pour une déclinaison de la source.

**« Piloté », par les cases.** Le miroir ne touche qu'aux visuels que la
source pilote, et on en juge sur les entrées qu'elle porte **dans ses propres
cases** — celles qu'aucune autre passe n'écrit. Juger sur toutes ses entrées
ferait dépendre le résultat de l'ordre : la base pose des entrées sur Weight
dans un visuel où Weight n'avait rien, et la passe de Weight, venue après,
s'y croirait pilotée. Deux ordres de passes donnent le même rapport, au
caractère (testé).

**Une seule sauvegarde couvre l'action entière**, pas une par source : sinon
trois sources mangeraient trois des dix sauvegardes conservées. Au passage,
`BackupSession` ne copie plus deux fois le même fichier — une session décrit
l'état d'**avant** l'opération, donc c'est la première copie qui vaut. Sans ce
garde-fou, un visuel touché par deux passes y déposait l'état *intermédiaire*,
et « annuler » ne rendait que le milieu de l'opération.

#### Un KPI qui n'a pas l'attribut ne reçoit rien

Tous les KPI n'ont pas tout. Quatre indicateurs, deux seulement avec une
**cible** : les entrées de cible partaient quand même sur les deux autres, où
elles pointaient la mesure du KPI **template**. Les valeurs restaient justes,
mais Power BI affichait un avertissement sur le visuel.

C'est le **paramètre de champ** qui tranche, et il faut deux règles distinctes :

| le KPI visé… | conclusion |
|---|---|
| a une ligne pour ce **Calcul** (`Cible`) | il a l'attribut → on propage |
| est dans le paramètre mais **sans** ligne pour ce calcul | il ne l'a pas → **rien ne lui est écrit** |
| n'est pas du tout dans le paramètre | le paramètre n'en dit rien → on propage (cible explicite hors paramètre) |
| mesure sans racine connue (un titre commun) | ne dépend pas du KPI → on propage |

La distinction qui compte : « ce KPI n'a pas de cible » ≠ « cette mesure ne
dépend pas du KPI ». La première fait sauter l'entrée, la seconde la laisse
passer inchangée (section précédente).

##### Le dossier des cibles, quand le paramètre ne suffit pas

Le paramètre de champ ne connaît pas toujours les cibles — on ne les offre pas
forcément au slicer. Sans ligne, `racine_fp` rattache `Weight cible` à la mesure
de **base** : le Calcul devient « Réel », que tous les KPI possèdent, donc la
règle ci-dessus ne l'écarte pas. La cascade retombe alors sur « garde la mesure
d'origine » — et la cible du **gabarit** atterrissait sur les KPI qui n'en ont
pas.

D'où une **seconde règle, indépendante** : le `displayFolder`. Les cibles vivent
dans un dossier dédié, déjà déclaré dans `kpiMeasureFolders` (Mesures →
⚙ Réglages → « Mesures cibles »). Une mesure de ce dossier est **propre à
son KPI**, donc si le KPI visé n'a pas la sienne, rien ne lui est écrit. Le
dossier est reconnu par sa **feuille** : `_indicateurs\cible` répond à `cible`.

Les mesures dérivées suivent : `Weight cible ecartCF`, générée hors du dossier,
remonte à sa racine `Weight cible` (`racine_cible`). Une mesure partagée, la
base et ses branches ne sont jamais concernées — c'est l'autre moitié du besoin.

Aucun dossier déclaré, ou modèle illisible → la règle se désactive d'elle-même.

Le test porte sur **toute l'entrée**, pas seulement son `selector` : le cas
courant est une règle posée sur la mesure de **base** dont la couleur vient de
la cible (`Weight cible ecartCF`, enfouie dans les `properties`). Le selector
se traduisait très bien — c'est la couleur qui ne pouvait pas. Le journal liste
les KPI écartés et la mesure qui leur manque.

Là encore, un simple nouveau passage retire les entrées déjà écrites pour ces
KPI : elles ne sont plus attendues, donc le miroir les emporte.

**Les reliques sont nettoyées.** Un rapport propagé avant cette règle porte des
entrées mortes (`Total Steps YTD titre`). Le miroir les retirait déjà des KPI
cibles, mais pas du KPI **template**, dont les entrées sont maîtresses et
jamais réécrites. Une entrée qui vise une mesure inexistante ne décrit
pourtant rien : elle est maintenant retirée là aussi, en le disant au journal.
Garde-fou — on n'enlève que si le nom est préfixé par la **table des mesures**,
car un selector peut viser une **colonne**, et les colonnes ne sont pas dans
`known`. Un simple nouveau passage suffit donc à assainir le rapport.

Dernier repli (racine elle-même absente du paramètre) : l'ancien remplacement
par le nom. Résultat identique à l'ancien code sur les mesures de KPI — vérifié
octet pour octet sur le rapport réel, et le nombre d'entrées d'un `dry_run` est
le même avec et sans les tables du paramètre.

⚠ Limite connue : si le KPI **destination** n'a pas la cible correspondante
(pas de `Body Fat % cible` dans le modèle), il n'existe aucun équivalent à
propager ; le repli par nom s'applique et peut écrire un nom inexistant.
Génère les cibles de **tous** les KPI visés avant de propager.

### Miroir : les suppressions se propagent aussi

Le template est la source de vérité **dans les deux sens** : ce qu'il ne porte
plus est **retiré** des KPI cibles. Retirer l'image d'une carte sur le KPI
template la retire donc partout. Sans ça la propagation n'était qu'additive —
et pire, une relique de branche d'un run précédent finissait par **recréer** le
réglage sur le template lui-même.

Le template a autant de **faces** que de branches. Sa face **Réel** irrigue
tout (cibles × branches). Une entrée présente UNIQUEMENT sur une branche — le
style des marqueurs de la ligne YTD sur un graphique qui ne trace que des
mesures YTD — ne descend que sur **cette** branche, et ne remonte jamais sur
une face Réel. Conséquence pratique : pour faire disparaître un réglage
partout, le retirer sur la face Réel **et** sur les faces de branche du KPI
template (le journal liste chaque retrait, ligne `- <clé> / <mesure> : retiré`).

Trois garde-fous :

| Garde-fou | Effet |
|---|---|
| Visuel sans aucune entrée du KPI template | jamais touché (un visuel qui n'affiche pas le template n'est pas concerné) |
| Couleurs statiques de `columnFormatting` | hors périmètre (`color_matrix_by_kpi.py` en est propriétaire) |
| Selector sans `metadata` (`id: default`, règles globales) | hors périmètre |

### Qui possède les couleurs statiques

`color_matrix_by_kpi.py` n'écrit **que** dans `objects.columnFormatting` (les
matrices « specific column ») — c'est là, et là seulement, qu'une couleur est
choisie **par KPI** depuis l'Excel. Partout ailleurs — `dataPoint` (couleur
d'une série : la ligne PY en noir), `markers`, `labels`… — une couleur statique
est un attribut de style **uniforme** sans autre propriétaire : elle se propage
depuis le template comme le style de trait ou la taille des marqueurs.

⚠ Corollaire : sur un graphique, une couleur de série posée à la main sur un
KPI cible sera **remplacée** par celle du template (et retirée si le template
n'en a pas). Pour des couleurs différentes par KPI dans un graphique, ne pas
compter sur la propagation — le template y est uniforme par construction.

Sécurité : chaque visuel modifié est copié dans
`_backupsPBIdouille\_propagate_backups\<horodatage>\<page>_<visuel>.json` **avant** écriture —
défaire un retrait = recopier le fichier. Et l'**Aperçu (dry-run)** de
l'onglet Rapport, coché par défaut, liste les retraits sans rien changer.

---

## 7b. color_matrix_by_kpi.py (couleur par KPI dans une matrice)

Colore chaque colonne d'une matrice avec la couleur de **son KPI** (même
couleur pour toutes les variations), pour distinguer les KPI d'un coup d'œil.

- **Source des couleurs** : deux colonnes dans `TD_Indicateurs.xlsx` —
  `couleur_fill` (fond) et `couleur_text` (texte), code hex chacune, clé =
  colonne des noms de mesures de base. Source unique — tu recolores dans Excel.
  Combiner fond × texte donne beaucoup plus de combinaisons distinctes.
- **Approche template** (comme propagate_cf) : applique à la main sur UN KPI un
  **fond ET un texte** (Specific column → une série → Background color + Text
  color), enregistre. Le script lit ce gabarit, **détecte** ses propriétés de
  couleur (`backColor` = fond ; l'autre = texte, peu importe son nom) et le
  réplique sur **toutes** les mesures avec le fond/texte de chaque KPI. Si le
  gabarit n'a qu'un fond, seul le fond est appliqué (avertissement). Seules les
  matrices ayant déjà un gabarit sont traitées (opt-in).
- **Ne touche QUE `objects.columnFormatting`** (les couleurs « specific column »
  des matrices). Donc : les CF de propagate_cf (`objects.values`), les couleurs
  de séries des graphes en lignes (`objects.dataPoint`), les slicers, etc. sont
  **tous exclus automatiquement**. Le ciblage est naturel — aucune liste de GUID
  à gérer : tu « cibles » une matrice juste en y appliquant la couleur sur une
  colonne (le gabarit EST le marqueur). Pas de gabarit = matrice ignorée.
- **Ordre** : `propagate_cf.py` d'abord, puis ce script (il a le dernier mot
  sur les couleurs des matrices). Les deux ne se marchent pas dessus :
  propagate_cf ignore les couleurs statiques de `columnFormatting` — la clé
  exclusive de ce script — et rien d'autre.

Procédure : configurer le gabarit + la colonne `couleur` → **fermer Desktop**
→ `py color_matrix_by_kpi.py` → rouvrir. Idempotent.

## 8. unused_measures.py (ménage)

Détecte les mesures ET les colonnes inutiles : ni référencées dans le rapport
(visuels, filtres, tris, CF, signets), ni par le modèle, directement ou via
une chaîne de mesures.

**Mesures** :
- Racines = références rapport + références structure du modèle ;
- propagation transitive (une mesure référencée par une mesure utilisée est
  utilisée) ;
- le reste : « aucune référence » ou « **used by unused** » (référencée
  seulement par des inutilisées — la chaîne est montrée, tout part ensemble).

**Colonnes** (analysées ET supprimables — voir §ChopChop pour les trois
catégories calc/import/structural). Une colonne est utilisée si référencée par :
- le rapport (champs de visuels/slicers/filtres, appariés **table + colonne**) ;
- du DAX qualifié `'Table'[Col]` n'importe où, ou `[Col]` non qualifié dans sa
  propre table (conservateur : mieux vaut un faux « utilisée ») ;
- une relation, un `sortByColumn`, un `groupByColumn` (mécanique des
  paramètres de champ), un niveau de hiérarchie ;
- **une AUTRE requête Power Query** : si la requête B consomme celle de la
  table (fusion, ajout, jointure) et nomme la colonne — clé de jointure,
  colonne développée ou sélectionnée —, la retirer casserait l'actualisation
  de B. Elle est donc marquée utilisée (« Power Query (requête « B ») »).
  ⚠ Une mention **à l'intérieur de sa propre requête** (typage, renommage,
  colonne dérivée) ne protège **rien** : l'étape `Table.RemoveColumns` posée
  par ChopChop est la **dernière** de la requête, donc tout ce qui précède a
  déjà produit son résultat. Exemple : dans `sleep`, retirer `datetime` laisse
  intactes `date` et `time`, que `DuplicateColumn` a créées **avant** l'étape
  de retrait. *(Corrigé — la règle inverse, « toute mention dans le M
  protège », déclarait utilisée quasiment chaque colonne importée : un simple
  « Type modifié » les cite toutes, et la catégorie « used by unused » restait
  désespérément vide.)* ;
- sinon : « used by unused » si seules des mesures inutilisées la référencent,
  ou « aucune référence ».

**Sorties** : `unused_measures.csv` (audit complet mesures + colonnes, colonne
`Type`, avec la raison d'utilisation de chacune) et
`delete_unused_measures.csx` — le « bouton » (mesures seulement) : ouvrir dans
TE, **relire la liste**, exécuter, Ctrl+S.

⚠ Pour les mesures marquées « générée » : les supprimer ne sert à rien (le
script TE les recrée). Retirer plutôt la variation/branche de
`measures_config.json` — `removeOrphans` fera le ménage au prochain run.

### ChopChopRapport — l'interface graphique (unused_measures_ui.py)

Deux façons de l'ouvrir, même implémentation (`ChopChopPanel`) :
**l'onglet « ChopChop 🪓 » de PBIdouille** (le projet vient de la barre
partagée ; l'analyse se fait à l'ouverture de l'onglet) ou en autonome :
`py unused_measures_ui.py` (dépendances : `py -m pip install qtpy pyside6`).
En autonome, « Changer de rapport… » ouvre un sélecteur de `.pbip` — le
dernier projet est mémorisé d'une session à l'autre. « Exporter… » écrit l'audit complet (utilisées comprises, avec
sommaire et détail des référenceurs) en CSV (zéro dépendance, s'ouvre dans
Excel) ou en `.xlsx` (via pandas si présent, sinon openpyxl).
Arbre par famille — une **icône** par type (🗑 tables, 📏 mesures, 🔢 colonnes) ;
la première colonne (« Objet ») porte tables, mesures et colonnes. Affordance :
les groupes **supprimables gardent la couleur normale** (on peut cliquer sans
danger) et seul le groupe **Utilisées** (référence, non supprimable) est
**atténué en gris** — le rouge/jaune de sévérité vit sur les **puces des lignes
enfants** (colonne « Référencé par ») : 🟥 aucune référence, 🟨 used by unused.
Côté MESURES comme côté COLONNES, les groupes non atténués sont cochables et
supprimables (sauf les colonnes de table calculée, voir plus bas). La case d'un
groupe **coche/décoche tous les enfants sélectionnables** (les colonnes de table
calculée, grisées, sont ignorées) — et se limite à la table filtrée si un filtre
est actif ; l'en-tête affiche plein / partiel / vide selon la vue. La colonne
« Référencé par » donne un
sommaire (« rapport (3 fichiers), 2 mesures, 1 table calculée ») et chaque
élément se déplie pour voir les référenceurs un à un. Thème : néon partagé
avec PBIdouille (vert `#56C596` sur bleu nuit — fallback autonome si le dossier
`bidouille\` n'est pas à côté).

**Filtre par table** (combo en haut) : masque l'affichage pour se concentrer
sur une table ; **les cases cochées d'autres tables restent vivantes** (le
compteur du bouton indique toujours le total réel, filtre compris).

**Supprimer la sélection** — un seul bouton, mesures **et** colonnes ensemble
(⚠ **Desktop fermé**, backup de chaque fichier touché sous
`_backupsPBIdouille\_tmdl_backups\<horodatage>\`, ré-analyse après coup).

Trois façons de supprimer une colonne selon sa **catégorie** (suffixe dans
l'arbre) :

| Catégorie | Suffixe | Suppression |
|---|---|---|
| **calculée** (DAX inline) | `[calculée]` | retrait du bloc TMDL |
| **importée** (requête M) | `[importée]` | bloc TMDL **＋** étape `Table.RemoveColumns` ajoutée en fin de la requête Power Query (sinon Power BI continue de charger la colonne) |
| **table calculée** (paramètre de champ, sortie DAX) | `[table calc.]` | **non cochable** — édite l'expression DAX de la table dans Desktop |

L'étape Power Query s'appelle `Colonnes retirées (ChopChop)` ; relancer la
fusionne (une seule étape, liste cumulée). Elle est posée avec
**`MissingField.Ignore`** : si le nom n'existe plus dans la sortie finale
(colonne renommée en cours de requête, ou déjà retirée par une étape
« Colonnes supprimées » antérieure), `Table.RemoveColumns` lèverait
« La colonne X est introuvable » et **casserait l'actualisation**.
La confirmation liste les tables qui recevront une étape M. Si une requête n'est pas reconnue (`let…in` exotique),
la colonne est retirée du modèle et un avertissement invite à éditer Power
Query à la main — l'import continue sinon.

### Tables entièrement inutilisées

Quand **rien d'externe** ne dépend d'une table — aucune relation, aucun visuel,
aucune mesure utilisée —, elle apparaît dans le groupe **🗑 Tables entièrement
inutilisées** (en tête, cochable comme les autres). La cocher supprime la table
**entière** : son fichier `<table>.tmdl` **＋** sa ligne `ref table` dans
`model.tmdl` (une table morte n'a par définition aucune relation à nettoyer).

C'est le bon outil pour les **paramètres de champ abandonnés** : l'analyse par
colonne ne peut pas les déclarer morts (leurs colonnes techniques *Fields*/
*Order* s'auto-référencent), mais au niveau table le vrai test est « ce
paramètre est-il utilisé dans un visuel ? » — les auto-références internes sont
ignorées. Cocher une table subsume ses mesures/colonnes (elles partent avec).
Backup du `.tmdl` **et** de `model.tmdl` avant écriture.

**Une table consommée par une autre requête n'est JAMAIS proposée ici.** Si la
requête d'une table sert de source à une autre (`Table.NestedJoin`,
`Table.Combine`, `Table.SelectColumns`…), son `.tmdl` porte cette requête :
la supprimer casse l'actualisation du consommateur. ChopChop lit donc le
**graphe des requêtes** — références `#"nom avec espaces"` et identifiants nus,
les littéraux de chaîne étant ignorés pour que le `"clients"` de
`Source{[Name="clients"]}` (une table de la **source** ODBC/SQL) ne passe pas
pour la requête `clients` du modèle. Les tables ainsi épargnées sont listées
dans le **journal** avec leur raison (« consommée par la requête Power Query :
ventes_jointes ») — sans quoi leur absence de la liste ressemblerait à un bug.
Même garde côté moteur : `delete_objects` refuse une table consommée, même
appelée directement.

Sont aussi épargnées les tables citées par une requête du rapport (`Entity`)
ou référencées **en entier** en DAX (`COUNTROWS(T)`, `ALL(T)`, `SUMMARIZE(T,…)`)
— des usages qu'aucune référence de colonne ne trahit.

Garde-fous : supprimer une mesure (ou une colonne référencée par des mesures)
« used by unused » inclut d'office les mesures qui en dépendent (sinon leur DAX
casserait) ; les mesures générées sont grisées avec rappel qu'elles
reviendront tant que la config les définit. Rouvrir le `.pbip` ensuite.

---

## 8b. backup_restore.py — sauvegardes et restauration

Chaque outil qui écrit dans un projet copie d'abord les fichiers touchés dans
un dossier horodaté, sous **un seul dossier parent** à la racine du projet :

```
<projet>\_backupsPBIdouille\
    _tmdl_backups\<horodatage>\        ChopChop, génération des mesures
    _propagate_backups\<horodatage>\   propagation
    _wireframe_backups\<horodatage>\   wireframe (positions, groupes, imports)
```

Ces copies étaient « à plat » : le nom du fichier ne disait pas **d'où** il
venait, donc restaurer voulait dire retrouver la bonne destination à la main.

Deux règles de ménage, pour que le dossier du projet reste lisible :

- **un seul endroit où chercher** — au chargement d'un projet, les dossiers
  restés à la racine (disposition d'avant) sont rangés sous le parent. Rien
  n'est fusionné de force ni supprimé : une session dont l'horodatage existe
  déjà de l'autre côté est laissée où elle est, et les deux dispositions
  restent listables et restaurables de toute façon ;
- **10 sauvegardes par outil** (`MAX_SESSIONS`) : au-delà, la plus vieille
  s'efface toute seule, à l'écriture suivante comme à l'ouverture du projet.
  Le compte est **par outil** : une propagation ne doit pas faire disparaître
  l'historique du wireframe, dont le Ctrl+Z s'appuie dessus. Un dossier qui
  n'est pas une sauvegarde (nom non horodaté, pas de manifeste) n'est jamais
  touché. Si le Ctrl+Z du wireframe remonte plus loin que ce qui reste, il le
  **dit** au lieu de ne rien faire.

Chaque dossier contient désormais un **`manifeste.json`** : pour chaque
fichier, son chemin d'origine relatif au projet et ce qui lui est arrivé.
Trois cas, et il faut les trois pour qu'un aller-retour soit exact :

| Action | Sens | À la restauration |
|---|---|---|
| `modifié` | le fichier existait, il a été réécrit | la copie le remet tel qu'il était |
| `supprimé` | l'outil l'a effacé (table morte, groupe dissous) | le fichier est **recréé** |
| `absent` | le fichier **n'existait pas** encore (groupe créé) | le fichier est **effacé** |

Sans `absent`, restaurer un groupement laisserait le groupe créé en place, et
annuler une restauration ne saurait pas re-supprimer ce qu'elle a recréé.

**« Sauvegardes… »** (bouton dans ChopChop) ouvre la liste, tous outils
confondus, la plus récente en haut ; chaque ligne se déplie pour voir quel
fichier retourne où. Restaurer réécrit les fichiers **après avoir sauvegardé
l'état courant** dans une session « Restauration » : on peut donc faire
l'aller-retour autant de fois qu'on veut. ⚠ Desktop fermé, puis rouvrir le
`.pbip`.

Les noms de copies restent ceux de chaque outil (`<id>_visual.json`…) : les
anciens dossiers restent lisibles et le Ctrl+Z du wireframe, qui les
reconstruit par convention, continue de fonctionner. Une sauvegarde
**antérieure** au manifeste reste restaurable : sa destination est retrouvée
en recalculant, pour chaque fichier candidat du projet, le nom aplati qu'il
aurait porté — aucune devinette ; ces sessions sont marquées `[ancienne]`, et
un fichier dont la cible reste inconnue est listé et **jamais** écrit au
hasard.

---

## 9. scan_lineage.py (inventaire du parc)

Scanne récursivement `ROOT` pour tous les `.pbip` et produit
`pbi_lineage.csv` : une ligne par partition avec table, mode
(import/directQuery/calculated), connecteur M et ses arguments (serveur/BD,
chemin, URL). Gère : connexions live (`byConnection`), `expressions.tmdl`
(paramètres serveur), connecteurs imbriqués (`Excel.Workbook(File.Contents(x))`
= une seule ligne avec le chemin). Lecture seule.

Le CSV se charge dans Power BI → rapport de lineage du parc. Au travail :
pointer `ROOT` vers le répertoire des projets.

---

## 10. Recettes

**Ajouter un KPI** : créer la mesure de base dans `_mesures` (dossier
`_indicateurs`) + sa ligne dans TD_Indicateurs.xlsx → actualiser TD_KPI →
relancer le `.csx` (variations, paramètres et switch suivent tout seuls) →
si visuels à CF par paramètre : `py propagate_cf.py` (Desktop fermé).

**Ajouter une variation** : nouveau bloc dans `variations` (penser à
`inFieldParameter: true` si elle doit être sélectionnable) → relancer le `.csx`.

**Retirer une variation** : la supprimer du JSON → relancer (`removeOrphans`
nettoie le modèle ET le paramètre, puisque l'expression est régénérée).

**Renommer un libellé de KPI** : changer `libelle_indicateur` dans l'Excel —
rien d'autre (le modèle est indexé sur les noms de mesures).

**Grand ménage** : `py unused_measures.py` → lire le CSV → exécuter
`delete_unused_measures.csx` dans TE pour les manuelles ; ajuster le JSON pour
les générées.

**Cartographier le parc** : `py scan_lineage.py` → `pbi_lineage.csv`.

---

## 11. Règles d'or

1. **Un seul écrivain à la fois.** Modèle : TE via Outils externes + Ctrl+S,
   puis enregistrer depuis Desktop. Fichiers PBIP (scripts Python) : Desktop
   **fermé** (il ne relit qu'à l'ouverture et écrase à l'enregistrement).
2. **TE ne recharge pas un `.csx` modifié** — le rouvrir après chaque édition.
3. **`py`, pas `python`** (sur certaines machines, `python` est le faux alias
   Microsoft Store qui ne fait rien).
4. Première exécution sur un nouveau modèle : `"dryRun": true`.
5. Les relations TD_KPI → paramètres se créent dans TE, une par table.
6. Sélection **simple** sur les slicers qui pilotent SELECTEDVALUE (switch)
   et sur `Calcul` pour la table parKPI.

---

## 12. Checklist de migration au travail

**Fichiers à copier** (tout dans UN dossier, idéalement celui du `.pbip` —
la structure est obligatoire : `bidouille\` importe les scripts de son dossier
parent, et ChopChop cherche le thème dans `bidouille\` à côté de lui) :

```
propagate_cf.py            color_matrix_by_kpi.py     unused_measures.py
unused_measures_ui.py      scan_lineage.py            generate_measures.py
create_measure_variations.csx (secours TE)            measures_config.json
ShadedBetween_overlay.dax  README.md
bidouille\app.py
bidouille\core\  (__init__, project, model_reader, report_reader, runner, theme)
bidouille\tabs\  (__init__, tab_report, tab_wireframe, tab_config, tab_model, dialog_couleurs)
```

⚠ Jamais depuis `codes\` (snapshot périmé) ; pas de `__pycache__` (bytecode
d'un autre Python). Un zip prêt à l'emploi peut être régénéré depuis la
racine (voir la liste ci-dessus).

- [ ] `measures_config.json` : `dateColumn`, `sourceTable`/`sourceFolder`,
      noms des tables paramètre, `switch.selector`, libellés (`Réel`...)
- [ ] `.csx` : le chemin codé en dur (ou laisser la boîte de dialogue)
- [ ] `propagate_cf.py` : `REPORT_DIR`, `TEMPLATE_KPI`, `FIELD_PARAMETER`
- [ ] `unused_measures.py` : `PBIP_DIR`, `PROJECT`
- [ ] `scan_lineage.py` : `ROOT`
- [ ] La table dimension (équivalent TD_KPI) avec une colonne = noms de mesures
- [ ] Vérifier que Python 3.8+ est disponible (`py --version` ou `python --version`)
- [ ] Pour les UIs seulement : `qtpy` + un binding Qt — PyQt5 (déjà au
      travail) ou PySide6 (`py -m pip install qtpy pyside6` à la maison) ;
      qdarkstyle n'est PLUS requis (thème néon autonome)
- [ ] Relations TD → P_xxx[Indicateur] dans TE après la première exécution

---

## 13. PBIdouille 🔧 — cockpit des outils (UI)

*(anciennement « BIdouille » ; réglages QSettings conservés sous ce nom interne)*

`bidouille\` regroupe les outils du rapport dans une seule app qtpy. But :
tout piloter sans éditer les constantes en tête des scripts, avec plus
d'options. Thème : « **Dark Teal Pro** », le thème néon des rapports (vert
`#56C596` sur fonds bleu nuit `#0F1629`/`#162032`) — QSS autonome dans
`core\theme.py`, partagé avec ChopChopRapport, rendu identique PyQt5/PySide6.
Les **titres de groupe** sont **dans** le cadre (à cheval sur la bordure, le
trait les barrait), dans leur propre police : **Bahnschrift SemiBold** 11 pt,
la DIN de Windows 10/11 — le reste du texte ne s'en distinguait que par la
couleur. Qt ignore toute police posée sur `QGroupBox::title` : le titre prend
celle du groupe, dont les enfants directs repartent en poids normal. La
**coche** des cases est fine (1,6 px), à angle vif et plus petite, dans une
case moins arrondie ; elle existe aussi en `@2x` pour les écrans à 150/200 %,
où l'image simple, agrandie, redevenait floue — donc ronde.

### Lancement

```
py app.py
```

Dépendances : `qtpy` + PySide6 (maison) ou PyQt5 (travail). L'app rouvre le
dernier projet utilisé (mémorisé), sinon « Fitbit for random devs.pbip ».

**measures_config.json** : par défaut, celui à côté du `.pbip` ; sinon le
bouton **« Config… »** de la barre permet d'en choisir un autre (mémorisé PAR
projet — utile au travail si le config ne vit pas avec le rapport). La table
paramètre des KPI est résolue dans l'ordre : celles du config
(`fieldParameter.tableNames`, puis `KpiBase`, puis `ByKpi`) → la première qui
existe dans le modèle → sinon **scan du modèle** (première table contenant
`NAMEOF` + `parameterMetadata` avec des KPI extractibles). Sans config, seul
l'onglet « Mesures » est inactif (bandeau explicatif) — l'onglet
Rapport fonctionne via le scan.

#### « ↻ Tout recharger » — voir le disque sans relancer l'app

Générer des mesures, ajouter une colonne dans TD_Indicateurs, retoucher le
modèle dans Desktop : l'outil continuait de travailler sur des données
périmées, et il fallait le fermer puis le rouvrir. Le bouton de la barre projet
relit tout :

| source | relue par |
|---|---|
| modèle : KPI, branches, paramètres de champ | onglet Rapport (`refresh_model`) |
| `measures_config.json` | onglet Mesures |
| `TD_Indicateurs.xlsx`, **colonnes comprises** | onglet Mesures (le cache d'en-têtes est invalidé) |
| grille des sources (`propagation.json`) | onglet Rapport |
| pages et visuels | Wireframe (reste sur la page courante) |
| mesures inutilisées | ChopChop (différé : à la prochaine visite de l'onglet) |

Chaque onglet expose un `reload()` et **garde les choix en cours** — les
branches décochées, par exemple. L'app n'appelle donc pas
`_set_project`, qui repousserait le projet dans les récents, relancerait le
rangement des sauvegardes et remettrait les listes à zéro.

Recharger relit le **disque** : ce qui n'est pas écrit est perdu. L'app liste
donc d'abord ce qui est en attente (config modifié, éléments déplacés) et
propose **Enregistrer puis recharger** / **Recharger quand même** / **Annuler**
— jamais de perte silencieuse.

#### Ce qui est mémorisé, et à quelle portée

Un **seul** magasin de réglages (`core/project.py` → `reglages()`, registre
Windows via QSettings). Il y en avait deux, dont un rien que pour la
bibliothèque : deux endroits où chercher, et un réglage qui semblait se perdre.
Ce qui traînait dans l'ancien est **rapatrié** à la première lecture.

| Réglage | Portée |
|---|---|
| projet ouvert, projets récents | application |
| **bibliothèque de variations** (`biblio_path`) | **application** — un fichier global, souvent sur un lecteur partagé ; il ne bouge pas quand on change de rapport |
| `measures_config.json` choisi (`Config…`) | **par projet** — chaque rapport a le sien |
| PBIP gabarit du wireframe | **par projet**, avec repli sur le **dernier choisi** où que ce soit |

Le registre plutôt qu'un fichier posé à côté de `app.py` : dézipper une mise à
jour ailleurs ne fait alors rien perdre.

Deux garde-fous, tirés d'un réglage qui avait l'air de se réinitialiser seul :
une valeur **vide** n'écrase jamais un réglage (refermer une boîte de dialogue
sans rien choisir ne défait rien), et le chemin de la bibliothèque est
**affiché** sous son bouton — avec un avertissement si le fichier a disparu,
plutôt qu'un repli silencieux sur le défaut.

#### Le journal — une colonne à droite, le plus récent en haut

Chaque onglet avait sa bande de log en bas : deux journaux (Rapport,
Générer) plus celui de ChopChop, larges et bas, quatre ou cinq lignes
visibles. Il fallait savoir **dans quel onglet** regarder, et une propagation
verbeuse défilait dans un hublot.

Désormais **un seul** journal (`core\journal.py`), en colonne à droite, sur
toute la hauteur de la fenêtre. Tous les onglets y écrivent — y compris
ChopChop, dont la zone est relayée (le panneau reste partagé avec la fenêtre
autonome, qui garde la sienne).

**Le plus récent en haut — par entrée, pas par ligne.** Une entrée est un run
(bannière puis sortie du moteur) ou un groupe de messages. Les entrées
s'empilent du plus récent au plus ancien, mais **dans** un run les lignes
restent dans l'ordre de lecture — inversées ligne à ligne, un run se lirait
de bas en haut, son « Terminé » au-dessus de sa bannière.

| ce qu'on voit | pourquoi |
|---|---|
| `▶ 14:32:07  Propagation des attributs (aperçu)   ✔ terminé en 2,4 s` | l'**heure de début**, puis le **verdict et la durée écrits SUR la bannière** : l'issue d'un run se lit sans descendre, même quand sa sortie dépasse la hauteur de la colonne |
| un **trait** autour de chaque run | sépare les entrées ; les messages isolés (déplacements du wireframe, rechargements) restent groupés **sans** trait, sinon une rafale deviendrait une échelle |
| `14:33:02  ↻ Tout rechargé …` | un message est horodaté ; ce qu'un clic écrit d'un coup (un rapport de suppression ChopChop) forme **une** entrée, lue dans l'ordre |
| des **couleurs** par nature de ligne | le vocabulaire des moteurs : `⚠` jaune, `ERREUR` rouge, `+` vert, `~` bleu, `-` orange, `=`/`∅` grisés, `***` bleu, `---` sous-titre ; le texte courant est gris clair, pas blanc — ce sont les couleurs qui doivent sortir |
| un **tableau** pour les « clé : valeur » | `KPI cibles : A, B, C` devient une rangée : la clé grisée dans une colonne, les valeurs alignées dans la suivante, **une par rangée** (au-delà de 12, la liste reste d'un bloc, repliée dans sa colonne). Seul le texte courant s'y range : un `⚠` ou un `Terminé` garde sa ligne et sa couleur |
| des **marges** plutôt que des trous | les lignes vides des moteurs deviennent l'espace avant le bloc suivant |
| un **retrait à gauche** par niveau | une ligne longue revient à la ligne **alignée sous elle-même** |

Un message qui arrive **pendant** un run se place au-dessus (il est plus récent
que le début du run), et la suite du run continue **sous sa bannière** : les
entrées ouvertes sont suivies par des curseurs que le document fait glisser
quand on insère au-dessus d'eux.

Qui est **en haut** y reste et voit arriver le neuf. Qui est **descendu lire**
plus bas garde **sa** ligne sous les yeux : la vue suit ce qui s'insère
au-dessus, au lieu de la pousser vers le bas à chaque message.

La police du journal est **proportionnelle**, volontairement : dans une colonne
étroite, elle loge un tiers de texte de plus par ligne. Le code, lui, est en
chasse fixe (cf. onglet « Mesures »). Le tableau n'est pas une vraie table :
chaque rangée est un paragraphe à **taquet de tabulation** et **retrait
suspendu** — ce qui s'insère sans casser le « plus récent en haut ».

La colonne fait **440 px** par défaut (340 avant) ; une largeur retenue plus
étroite a été élargie une fois, puis celle qu'on règle à la poignée est
respectée. La barre projet n'affiche plus que le **nom** du projet (le chemin
est en infobulle) : elle imposait à elle seule ~1 600 px de fenêtre.

**Dans l'onglet Mesures, le journal porte la génération** : le panneau
**« Génération des mesures »** (aperçu, orphelines, bouton **Générer les
mesures**) se pose entre son entête et le fil — le run lancé s'affiche juste
en dessous, puisque le plus récent est en haut. Ailleurs, le panneau
s'efface et le journal reste un journal.

**La colonne cède sa place à l'éditeur de variations.** Dans *Mesures →
Variations*, la colonne de droite accueille le DAX et l'aperçu des noms ; le
journal y est replié par défaut. Le bouton **« ◂ 🚀 Lancements »** l'y rouvre — avec
le bouton de génération — et il **reste ouvert dans Variations** tant que tu
ne l'y refermes pas.

**Les runs bavards se rangent dans des tiroirs.** Un run terminé qui a écrit
plus de 6 lignes se **replie** sur sa bannière — `▶ 09:57:48  Propagation
des attributs   ✔ terminé en 0,1 s   25 lignes   ⚠ 1` : combien de lignes elle
cache, et s'il y a des avertissements dedans. **Un clic** sur la bannière
l'ouvre (▼), un autre la referme ; la main au survol dit qu'elle se clique.
Un **échec** reste ouvert — il faut le lire —, un run court aussi (rien à
cacher), et le run **en cours** ne se replie pas : ses lignes arrivent
encore. Le texte replié reste dans le document : copier ou chercher le
trouve. (Les lignes sont masquées, pas retirées : Qt sait sauter un
paragraphe invisible dans la mise en page.)

Le bouton **« 🚀 Lancements ▸ »** est donc **ton** choix, retenu **par vue** (dans
*Variations* / ailleurs) d'une session à l'autre, avec la largeur de la
colonne. Un **run qui démarre remontre** la colonne sans toucher à ce choix —
un outil qui écrit dans les fichiers sans qu'on voie ce qu'il fait, non ; un
simple message, lui, ne force pas la main.

Les **poignées** entre volets (ici, dans *Variations*) sont un trait d'un
pixel au milieu d'une bande de 13 px : les groupes ne butent plus sur une
barre, et la prise reste facile à attraper (`theme.Separateur` — dessinée à
la main : pour une poignée stylée, Qt lit la règle `:vertical` même pour un
splitter horizontal).

La place a été prise **sur la largeur imposée**, pas sur le travail : la
rangée « Portée » de l'éditeur de variations réclamait 1424 px à elle seule et
le libellé du projet 984 (chemin complet, désormais en infobulle) — la
fenêtre descend de ~2300 px de large à ~1860, journal compris.

### Architecture

```
app.py              coquille : barre projet partagée + onglets + thème
bidouille\
  core\
    project.py      .pbip -> .Report / .SemanticModel + projets récents
    model_reader.py KPI, branches, entité (délègue à propagate_cf / color_matrix / config)
    journal.py      LE journal (colonne de droite) : horodatage, couleurs, marges
    runner.py       ToolRunner (QThread) : lance un outil, ligne à ligne vers le journal
    theme.py        palette, QSS, icône émoji ; police_code (chasse fixe du
                    code) et rangee_transparente (rangées dans un groupe)
  tabs\                 (dans l'ordre des onglets)
    tab_config.py       onglet « Mesures » (Variations, JSON brut) + la fenêtre ⚙ Réglages
    tab_model.py        panneau « Génération des mesures », posé en tête du journal (generate_measures.py)
    tab_report.py       onglet « Rapport » (propagation, couleurs des matrices)
    dialog_sources.py   la grille des sources du formatage (propagation.json)
    tab_wireframe.py    onglet « Wireframe » (plan des pages, niveaux actifs, gabarits)
    tab_chopchop.py     onglet « ChopChop 🪓 » (embarque le panneau de unused_measures_ui)
    dialog_couleurs.py  aperçu & édition des couleurs KPI (écrit dans l'Excel)
  core\report_reader.py    lecture pages/visuels (positions, types, champs) + write_positions
  core\template_import.py  modèles d'un PBIP gabarit -> import dans la page courante
```

Les scripts racine restent utilisables en CLI ; l'app **réutilise la même
implémentation** : `propagate_cf.propagate_regles(...)` (la grille ;
`propagate(...)` pour un gabarit seul) et
`color_matrix_by_kpi.colorize(...)` (leurs `main()` ne sont que ces fonctions
appelées avec les constantes de tête). Aucune logique dupliquée.

### Onglet « Rapport »

- **Propagation des attributs** : la **grille des sources** — un résumé, et
  le bouton qui l'ouvre (cf. §7) —, les branches cochables, `Aperçu
  (dry-run)` pour prévisualiser sans écrire, `Verbeux` pour le détail des
  candidats → bouton **Propager**. Sans grille, pas de propagation.
- **Couleurs des matrices** : une **fiche** rappelle l'Excel des indicateurs
  — son nom (chemin complet en infobulle, ⚠ s'il est introuvable) et les
  colonnes lues (clé · fond · texte), libellés grisés, valeurs en clair — et
  un lien **« Se règle dans ⚙ Réglages »** ouvre la fenêtre : l'Excel
  n'est défini qu'une fois, dans le config → bouton **Colorer**. Le bouton **« Aperçu & édition des couleurs… »** ouvre
  l'éditeur : chaque KPI avec ses pastilles fond/texte
  et un aperçu rendu ; clic = sélecteur de couleurs ; **Enregistrer réécrit
  l'Excel** (et CRÉE les colonnes `couleur_fill`/`couleur_text` si l'Excel n'a
  que l'ancienne colonne `couleur` — laquelle n'est pas touchée).
- **Propager puis colorer** enchaîne les deux dans le bon ordre.
- Une écriture réelle (dry-run décoché) demande confirmation ; **fermer Power BI
  Desktop** avant. La sortie CLI arrive telle quelle dans la **colonne
  journal** à droite, horodatée et colorée (ci-dessus) ; « Propager puis
  colorer » donne **deux** bannières et **deux** durées, une par étape.

### Onglet « Wireframe »

Plan de chaque page du rapport : les visuels sont dessinés à leur position et
taille réelles (lues dans les visual.json), type + titre affichés, ordre z
respecté, visuels cachés en pointillé. 🎨 = le visuel porte un gabarit de
couleur « specific column » (l'opt-in de Colorer).

**Groupes** : les positions du PBIR sont RELATIVES au groupe parent (un enfant
à x=0 est au coin du groupe) ; `report_reader` cumule les offsets des groupes
ancêtres pour obtenir l'absolu, donc les membres s'affichent au bon endroit
DANS leur groupe. Un **arbre de hiérarchie** à droite reflète la structure
groupes → visuels (imbrication comprise) et se **synchronise avec le canevas**
dans les deux sens. Clic sur un visuel → détails : id, type, position, groupe
parent, **champs utilisés** (queryRef), clés de formatage, « Ouvrir
visual.json » ; clic sur un groupe → nom, mode, nombre de membres.

**Niveau actif (« scope »)** : on agit toujours sur les enfants DIRECTS d'un
conteneur — la page, ou un groupe dans lequel on est entré. **Double-clic sur
un groupe** (canevas ou arbre, ou bouton « Entrer dans le groupe ») = on entre
dedans : ses enfants deviennent manipulables, le conteneur prend un léger voile
vert, **tout le reste est grisé et inerte** ; **Échap** (ou double-clic sur le
fond) remonte d'un niveau ; le **fil d'Ariane** au-dessus du canevas
(« Page ▸ Groupe 4 ▸ Groupe 2 ») montre où l'on est et ses segments sont
cliquables. Le niveau survit à Recharger/Annuler tant que le groupe existe.

**Édition (positions)** — au niveau actif, deux comportements au lâcher :
- **lâché SUR un voisin** (chevauchement net) : l'élément **s'insère** à côté
  de lui — dans la **chaîne d'éléments collés** du même axe (rangée ou
  colonne, choisie par le décalage des centres). La chaîne se recolle bord à
  bord ancrée à son début ; **rien d'autre sur la page ne bouge** ;
- **lâché ailleurs** : placement **libre aimanté** (rayon 10 px) — collage
  bord à bord au voisin d'en face (poser un visuel juste dessous / juste à
  côté = il se colle), alignement de bords façon guides (même à distance),
  bords de la page. Au-delà du rayon : position exacte du lâcher (le
  chevauchement reste permis, comme dans Power BI).

Un **groupe se déplace en bloc** : tout son sous-arbre suit à l'écran, mais
seule SA position est réécrite (les enfants sont relatifs au parent).
**Glisser une bordure verte** = faire glisser une **ligne-frontière**. Une
arête partagée par plusieurs éléments (le bas d'un groupe qui touche à la fois
pivotTable ET lineChart) est **une seule poignée** couvrant toute la ligne :
la glisser déplace l'arête de TOUS les éléments qui la bordent d'un coup (les
« avant » ajustent leur bord droit/bas, les « après » leur bord gauche/haut),
donc la ligne reste **droite** — plus de bordure en escalier quand on
redimensionne un seul visuel. Groupes bordants = contenu rééchelonné
(ScaleMode). Bords extérieurs fixes ; les autres poignées se recalent en
direct, tout est reconstruit au relâchement.

**Aimantation transversale** : glisser une bordure verte ou un bord d'élément
s'aimante (10 px) à **toute arête visible du niveau** — y compris celles à
l'INTÉRIEUR des groupes voisins (les bords des slicers d'un groupe au-dessus,
le bord d'un areaChart à côté) et les bords de la page. On aligne ainsi la
frontière d'un bloc sur la structure d'un autre bloc, pas seulement sur les
frères directs.

**Bornage à la page** : les éléments ne peuvent plus sortir de la page —
clamp **pendant** le drag (l'élément suit la souris mais bute sur les bords),
au lâcher, au redimensionnement par bord (bords bornés à 0..largeur/hauteur),
sur les bordures vertes, et dans « Répartir » (la zone est intersectée avec la
page — répartir **ramène donc dans la page** ce qui débordait). Seule
exception : l'import de gabarit « à la position d'origine » peut déborder
(averti dans le statut).
**Redimensionner librement** : presser dans la **bande de bord** d'un élément
actif (8 px, curseurs ↔/↕/⤡ au survol) déplace ce(s) bord(s) — du premier
geste, même non sélectionné ; bords aimantés (10 px) aux voisins du niveau et
à la page, taille min 20 ; les petites poignées vertes de la sélection sont
de simples indicateurs. **Redimensionner un GROUPE rééchelonne tout son
contenu proportionnellement** (simulation ScaleMode — même sémantique que
Desktop) : chaque descendant est réécrit (position/taille relatives ×
facteur), donc tout le sous-arbre passe en « modifié ».

**Répartir également** : bouton « ⬍⬌ Répartir » — range les éléments en
**grille dans leur zone**. La cible, par priorité : la **sélection multiple**
(Ctrl+clic, zone = sa boîte) ; **UN GROUPE sélectionné** → répartit **ses
enfants dans sa boîte** (rien d'autre ne bouge — ex. égaliser les slicers du
groupe-slicers sans toucher les voisins) ; sinon les enfants du **niveau
actif** (zone = la boîte du groupe-scope si on est dans un groupe, sinon la
boîte des éléments ∩ page). Les **rangées sont détectées** (chevauchement
vertical > 50 %) et empilées bord à bord, hauteurs ∝ **hauteur max** de chaque
rangée ; chaque rangée est découpée en **cellules égales pleine largeur** (une
rangée d'un seul élément — ex. une bande de slicers — prend toute la largeur).
Une seule rangée/colonne = simple partage égal. Un groupe posé dans une
cellule rééchelonne son contenu. Annulable (Ctrl+Z). NB : pense « grille » —
un élément qui chevauche deux rangées (barre latérale) fusionne les rangées ;
sélectionne alors ce que tu veux répartir. Le **nom d'un groupe** se replace
en haut-droite quand on le redimensionne.

**Grouper / Dégrouper** : Ctrl+clic (ou lasso depuis le fond) pour
sélectionner ≥ 2 éléments du niveau actif → **« Grouper »** (nom demandé) :
crée le `visualGroup` PBIR (position = boîte englobante, ScaleMode,
imbrication respectée — grouper dans un groupe donne un sous-groupe) et
réécrit les membres (parentGroupName + position relative ; rien ne bouge à
l'écran). **« Dégrouper »** (groupe sélectionné) fait l'inverse : les enfants
remontent d'un niveau, le groupe est supprimé. Écriture immédiate (Desktop
FERMÉ), backups + manifestes sous `_backupsPBIdouille\_wireframe_backups\`.

**Annuler (Ctrl+Z) et enregistrement** : plus de popups de confirmation —
chaque action écrit directement (toujours backupée) et s'annule par
**Ctrl+Z** (ou le bouton « ⌫ Annuler ») : les gestes (déplacements,
redimensionnements — pile en mémoire, vidée au changement de page) comme les
actions fichiers (import, groupement, dégroupement, enregistrement — le undo
restaure les backups et supprime les fichiers créés). **« 💾 Enregistrer »**
écrit les positions modifiées et s'allume en orange tant qu'il en reste. Il
n'y a plus de « Tout enregistrer » dans la barre d'app : il doublait ce
bouton et le « Sauvegarder » des Mesures, qui s'allument, eux. Le bandeau
vert sous le canevas raconte la dernière action.

Les changements s'accumulent à l'écran : le bouton **« 💾 Enregistrer (N) »**
porte le compte et **s'allume en orange** tant qu'il reste quelque chose à
écrire — l'état se lit là où on va cliquer pour le résoudre, plutôt que dans
un voyant posé à côté.
**Enregistrer les positions** écrit les `visual.json` concernés — uniquement le
bloc `position` (converti en coordonnées locales au groupe ; z/tabOrder
préservés), **Desktop FERMÉ**, backup sous `_backupsPBIdouille\_wireframe_backups\<horodatage>\`,
puis rouvrir le `.pbip`. **Annuler** relit le disque et jette les changements
non sauvés.

**Panneau « Gabarits »** (colonne droite, repliable) : choisis un **PBIP
gabarit** (mémorisé par projet) — chaque **groupe racine** de ses pages est un
modèle nommé (le nom = displayName du groupe, posé dans le volet Sélection de
Desktop), les visuels racine isolés sont aussi proposés — leur nom = le
**titre du visuel** (`visualContainerObjects.title`, celui que Desktop écrit
quand tu titres le visuel ; ex. « Slicer_range », « Slicer_dropdown »), sinon
le type. **« Importer dans la
page courante »** copie le sous-arbre complet dans le rapport : nouveaux ids
20 hex, `parentGroupName` remappés, ids de filtres régénérés, **z/tabOrder
renumérotés au-dessus du max de la page**, géométrie conservée à l'identique
(la racine garde sa **position d'origine** du gabarit — pensé pour les
en-têtes/pieds de page standard, rangées de slicers, grilles). Écriture
immédiate (Desktop FERMÉ) + **manifeste d'undo** sous
`_backupsPBIdouille\_wireframe_backups\<horodatage>\import_manifest.txt` (undo = supprimer les
dossiers listés). ⚠ Le modèle importé référence les tables/champs du modèle
sémantique du GABARIT — compatibilité à vérifier (même modèle ou champs
communs). Voir `core/template_import.py`.

### Onglet « Mesures »

Deux sous-onglets : **Variations** (l'éditeur ci-dessous) et **JSON brut**.
Les réglages globaux du config ont leur **fenêtre**, ouverte par **⚙ Réglages**
dans la barre du haut : ils servent aussi à l'onglet Rapport (l'Excel des
indicateurs, par exemple), ils n'avaient rien à faire sous les Mesures.
**Enregistrer** y écrit le config, comme « Sauvegarder » — avec tout ce qui
est en attente, variations comprises ; **Annuler** oublie ce qui a été
touché dans la fenêtre, y compris l'orange qu'il avait allumé.
La génération n'a plus d'onglet : son bouton est **en tête du journal** (plus
bas).

*Variations* est en **trois volets** : la liste à gauche ; au milieu la
définition, en deux groupes — **Mesure générée** (nom, format, dossier…) et
**Portée** (KPI / cibles, enveloppe de branche, types de base, filtres par
nom) ; à droite, sur toute la hauteur, le **DAX** au-dessus de l'**aperçu des
noms générés**, une poignée entre les deux. C'est la place du journal, qui
n'a rien à dire dans cette vue et la lui cède. Éditeur de
`measures_config.json` — chaque variation s'édite dans un
formulaire complet avec tooltips explicatifs partout : namePattern,
description, **formatString en dropdown** (inherit / delta / **text** = aucun
format / formats usuels, saisie libre permise), displayFolder,
**folderVariation en dropdown** des autres variations (« dossier hôte » — ex.
CF Δ 30d vit dans le dossier de Δ 30d), **dataCategory en dropdown**
(ImageUrl/WebUrl), inFieldParameter, plus :

- **éditeur DAX en clair** : le format JSON array-of-lines devient invisible
  (colle ton bloc DAX, il est sérialisé en lignes à la sauvegarde ; round-trip
  fidèle, clés inconnues préservées). Les gestes d'un éditeur de code, aussi
  dans le **JSON brut** :
  - **TAB pose une tabulation**, large de **4 caractères** (Qt en donnait
    80 px, une dizaine) ; Maj+TAB la reprend — et défait aussi, 4 par 4, un
    retrait en espaces des variations écrites avant. Une tabulation passe
    telle quelle dans le TMDL, sous son propre retrait, et la génération
    suivante n'y voit aucun changement ;
  - **Début** va au premier caractère après le retrait (un 2e appui : colonne
    0), donc **Maj+Début** depuis la fin d'une ligne sélectionne le code sans
    embarquer le retrait ; Ctrl+Début garde son sens ;
  - **chasse fixe pour de vrai** : le QSS d'app fixe `font-family` sur tous
    les widgets, ce qui écrasait les `setFont(Consolas)` — l'éditeur DAX
    était en Segoe UI depuis toujours (4 espaces = 12 px) et l'aide-mémoire
    des jetons perdait ses colonnes. `theme.police_code()` marque le widget
    et une règle de thème plus précise reprend la main ;
- **jetons surlignés à la frappe** : `{connus}` en bleu, `<<attributs>>`
  connus en vert, **inconnus en rouge souligné**. Sont connus les jetons du
  générateur, ceux de la portée par KPI (`<<tables>>`, `<<allTables>>`,
  `<<removeFilters>>`, et `{table}` **dans** un `<<each …>>`) et les
  `<<labels>>` déclarés dans **⚙ Réglages → Attributs codés en dur** —
  une déclaration fraîche compte tout de suite, sans enregistrer. Les
  constructeurs de table DAX `{ ad }` (avec espaces) ne sont pas des jetons ;
- **lint** sous l'éditeur, fondé sur le **même** repérage que la couleur : ce
  qui est rouge est exactement ce qu'il signale — `{jeton}` inconnu, et
  maintenant `<<attribut>>` non déclaré (la génération sauterait la mesure).
  `{table}` dans un `<<each …>>` n'y est plus signalé à tort ;
- **aide-mémoire des jetons** sous la zone DAX, **replié** par défaut (un clic
  sur « Jetons disponibles ») : il sert à l'écriture du DAX, pas en permanence.
  Il porte l'opposition qui compte : `{kpi}` = KPI racine **sans** branche,
  `{kpiRef}` = le KPI **dans** la branche courante (le piège de l'écart
  réel−cible). Ailleurs, les explications longues vivent derrière un **ⓘ**
  (survol = infobulle, clic = fenêtre) plutôt qu'en paragraphes permanents ;
- **aperçu des mesures générées** sans toucher au modèle — il suit la **portée
  cochée** : une variation « aux cibles » seulement montre les cibles réelles du
  modèle (`Weight cible`, `Weight cible YTD`…) et non les KPI ; portée vide = un
  message le dit au lieu d'une liste trompeuse. Les cibles sont lues par
  `generate_measures.scan_cibles()`, la **même** fonction que la génération —
  l'aperçu ne peut donc pas diverger de ce qui sera écrit. Chaque nom est
  **en couleur** selon ce qui l'a produit : la racine (KPI ou cible) telle
  quelle, ce que la **branche** ajoute en bleu (` YTD`), ce que la
  **variation** ajoute en vert (` Δ 7d`) — la légende est au-dessus. Les
  branches y sont appliquées avec la **règle de la génération** : jamais à
  elles-mêmes (l'aperçu montrait `Weight YTD YTD`, jamais généré) et, pour
  une branche restreinte, aux seules variations qu'elle liste. Un test
  vérifie, variation par variation, que chaque nom affiché figure dans le
  plan d'une génération à blanc ;
- boutons Ajouter / Dupliquer / Renommer / Supprimer + **↑ Monter / ↓ Descendre**
  (réordonne les variations — l'ordre pilote celui des calculs dans le
  paramètre de champ et la génération) ;
- fenêtre **⚙ Réglages** — chaque groupe s'ouvre sur une phrase qui
  dit à quoi il sert, et chaque réglage a son **ⓘ** (survol = infobulle,
  clic = fenêtre) : ce qu'il fait, un exemple, sa valeur par défaut. Les
  paramètres de champ, par exemple, y expliquent les trois familles de tables
  (par calcul, par KPI, mixtes), le rôle des colonnes Indicateur / Calcul /
  Branche et de la table de correspondance des libellés — `settings`,
  `fieldParameter`, `switch` et
  `branches` en cases/champs (les listes de tables paramètre en multi-lignes ;
  les branches en cases à cocher sur les variations, **+ un éditeur de
  restriction** : pour chaque branche, cocher quelles variations elle applique —
  ex. exclure une cible autonome en {kpi} du fork YTD) — plus besoin d'éditer le
  JSON à la main pour les variables globales ;
- sous-onglet **JSON brut** (tout le fichier, validation avant de revenir) ;
- **Sauvegarder** : backup `measures_config.json.bak` puis écriture.

**Génération** — en tête du journal, visible dans l'onglet Mesures : le bouton
**« Générer les mesures »** exécute
`generate_measures.py` sur le modèle du projet : mesures × variations ×
branches, tables paramètre de champ, mesure Switch — **sans Tabular Editor ni
Desktop ouvert**. Récap du config en une ligne (le détail en infobulle) ;
« Aperçu (dry-run) » coché par
défaut (liste tout, n'écrit rien) ; case « Supprimer les orphelines » ;
l'écriture réelle demande confirmation (Desktop FERMÉ), sauvegarde sous
`_backupsPBIdouille\_tmdl_backups\`, puis rouvrir le `.pbip`.

Le générateur lit le **fichier**, pas l'éditeur. Le bouton étant désormais à
côté de l'éditeur (plus d'onglet à traverser, qui enregistrait la vue au
passage), l'oubli est devenu facile : le panneau le signale en continu, et
générer avec un config non enregistré propose **Enregistrer puis générer** /
**Générer l'ancienne version** / **Annuler** plutôt que de générer l'ancien
en silence. Workflow : éditer → **Générer les mesures** (qui enregistre si
besoin) → rouvrir Desktop. Le bouton **« Sauvegarder »** s'allume en
**orange** dès que le config a des modifications en attente.

### Onglet « ChopChop 🪓 »

Le panneau complet de ChopChopRapport (section 8) dans PBIdouille : mesures et
colonnes inutilisées, filtre par table, export, suppression TMDL + Power Query
— sur le projet de la barre partagée. L'analyse se déclenche à l'ouverture de
l'onglet (changer de projet reste instantané). La version autonome
`py unused_measures_ui.py` continue de fonctionner (même panneau).

### Feuille de route

- Wireframe : redimensionner un groupe (simulation ScaleMode), configurer les
  attributs d'un modèle importé (champs, titres) depuis l'UI.
