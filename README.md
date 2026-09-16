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
py generate_measures.py        (ou l'onglet « Mesures » → « Générer » de PBIdouille)
```

⚠ Desktop FERMÉ pour l'écriture réelle ; backup automatique sous
`_tmdl_backups\` ; rouvrir le `.pbip` ensuite. `settings.dryRun` (ou la case
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
   du csx). C'est cet ordre qui devient la colonne **Ordre** des paramètres de
   champ : dès qu'il diverge, l'ordre du paramètre ne colle plus à l'ordre
   alphabétique affiché par le rapport.

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
   TYPOGRAPHIQUE `’` (U+2019), elle, est significative pour .NET — elle n'est
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

Ça se configure dans l'**onglet Mesures → Réglages globaux → « Mesures cibles
(dossier dédié) »** (tableau Dossier / Calcul, boutons Ajouter/Retirer) — pas
besoin d'éditer le JSON à la main. Le journal du « Générer » indique combien de
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
trois sections. Les symboles se règlent dans **Mesures → Réglages globaux** (un
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

### Catalogue de variations et sélection par rapport

`measures_config.json` est un **catalogue** : il porte toutes les variations et
voyage d'un rapport à l'autre. Mais un rapport ne veut pas forcément les mêmes
que le précédent — la **sélection** est donc propre au projet, dans un petit
fichier posé à côté du `.pbip` :

```json
// pbidouille_variations.json
{ "actives": ["7d avg", "PY", "YTD"] }
```

Dans **Mesures → Variations**, chaque ligne de la liste porte une **case** :
cochée = générée dans CE rapport. Boutons *Tout* / *Aucune*, et un compteur
sous la liste (« 8 active(s) sur 11 dans CE rapport »). La variation affichée
dans le formulaire signale en jaune qu'elle est désactivée, le cas échéant.

| Où | Quoi | Voyage ? |
|---|---|---|
| `measures_config.json` | le catalogue complet | oui — partagé entre rapports |
| `pbidouille_variations.json` | les ids actifs ici | non — propre au projet |

Trois comportements à connaître :

- **Fichier absent = toutes actives.** Tout cocher le supprime : l'état par
  défaut ne laisse aucun fichier derrière lui, et les projets existants ne
  changent pas de comportement.
- **Décocher une variation qui sert de BRANCHE** retire aussi la branche — le
  journal le dit (`Branches désactivées avec leur variation : YTD`).
- **Décocher ne supprime pas** les mesures déjà générées : elles deviennent
  orphelines. Coche `removeOrphans` (Réglages globaux) pour qu'elles partent.

Le journal de génération résume :

```
Catalogue : 3 variation(s) active(s) sur 11 (sélection propre à ce rapport).
```

Sélection vide = erreur explicite plutôt qu'une génération silencieusement
vide. Un id inconnu du catalogue (variation renommée depuis) est signalé et
ignoré, sans bloquer.

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
clé (le nom de la mesure). Case dans **Mesures → Réglages globaux**.

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

Une seule ligne dans **Mesures → Réglages globaux → Portée par KPI** : le nom
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
  "textColumn": "couleur_text"
}
```

Se règle dans **Mesures → Réglages globaux → Excel des indicateurs** (avec un
sélecteur de fichier et les colonnes proposées d'après les en-têtes réels).
Tout ce qui est au défaut n'est pas écrit — le config reste propre, et le bloc
disparaît entièrement si rien ne change.

Un chemin **relatif** est résolu depuis le dossier du `.pbip` ; le sélecteur
re-relativise automatiquement un fichier choisi dans le projet, pour que le
config reste transportable d'un rapport à l'autre.

Qui s'en sert :

| Usage | Colonnes |
|---|---|
| jetons `<<label>>` figés dans le DAX | `keyColumn` + celles de `hardcodedAttributes.tokens` |
| portée par KPI (`<<each …>>`) | `keyColumn` + celle de `kpiTables.column` |
| **couleurs des matrices** (onglet Rapport) | `keyColumn`, `fillColumn`, `textColumn` |

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
les valeurs à jour. UI : onglet **Mesures → Réglages globaux → « Attributs
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
`_propagate_backups\<horodatage>\<page>_<visuel>.json` **avant** écriture —
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
`_tmdl_backups\<horodatage>\`, ré-analyse après coup).

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
un dossier horodaté : `_tmdl_backups\` (ChopChop), `_propagate_backups\`
(propagation), `_wireframe_backups\` (wireframe). Ces copies étaient « à
plat » : le nom du fichier ne disait pas **d'où** il venait, donc restaurer
voulait dire retrouver la bonne destination à la main.

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

### Lancement

```
py bidouille\app.py
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

### Architecture

```
bidouille\
  app.py            coquille : barre projet partagée + onglets + thème
  core\
    project.py      .pbip -> .Report / .SemanticModel + projets récents
    model_reader.py KPI, branches, entité (délègue à propagate_cf / color_matrix / config)
    runner.py       ToolRunner (QThread) : lance un outil, journal streamé
    theme.py        icône émoji, rose vif, cases à cocher, dark mode
  tabs\
    tab_report.py       onglet « Rapport » (phase 1)
    tab_wireframe.py    onglet « Wireframe » (plan des pages, niveaux actifs, gabarits)
    tab_config.py       onglet « Mesures » (éditeur config + sous-onglet Générer)
    tab_model.py        panneau « Générer » embarqué dans l'onglet Mesures (generate_measures.py)
    tab_chopchop.py     onglet « ChopChop 🪓 » (embarque le panneau de unused_measures_ui)
    dialog_couleurs.py  aperçu & édition des couleurs KPI (écrit dans l'Excel)
  core\report_reader.py    lecture pages/visuels (positions, types, champs) + write_positions
  core\template_import.py  modèles d'un PBIP gabarit -> import dans la page courante
```

Les scripts racine restent utilisables en CLI ; l'app **réutilise la même
implémentation** : `propagate_cf.propagate(...)` et
`color_matrix_by_kpi.colorize(...)` (leurs `main()` ne sont que ces fonctions
appelées avec les constantes de tête). Aucune logique dupliquée.

### Onglet « Rapport »

- **Propagation des attributs** : KPI gabarit, KPI cibles et branches cochables,
  `Aperçu (dry-run)` pour prévisualiser sans écrire, `Verbeux` pour le détail
  des candidats → bouton **Propager**.
- **Couleurs des matrices** : chemin de l'Excel + **menus déroulants des
  colonnes** (clé / fond / texte), chargés du fichier (bouton ↻ pour
  recharger ; on peut aussi taper un nom de colonne à créer) → bouton
  **Colorer**. Le bouton **« Aperçu & édition des couleurs… »** ouvre
  l'éditeur : chaque KPI avec ses pastilles fond/texte
  et un aperçu rendu ; clic = sélecteur de couleurs ; **Enregistrer réécrit
  l'Excel** (et CRÉE les colonnes `couleur_fill`/`couleur_text` si l'Excel n'a
  que l'ancienne colonne `couleur` — laquelle n'est pas touchée).
- **Propager puis colorer** enchaîne les deux dans le bon ordre.
- Une écriture réelle (dry-run décoché) demande confirmation ; **fermer Power BI
  Desktop** avant. Le journal commun reproduit la sortie CLI.

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
FERMÉ), backups + manifestes sous `_wireframe_backups\`.

**Annuler (Ctrl+Z) et enregistrement** : plus de popups de confirmation —
chaque action écrit directement (toujours backupée) et s'annule par
**Ctrl+Z** (ou le bouton « ⌫ Annuler ») : les gestes (déplacements,
redimensionnements — pile en mémoire, vidée au changement de page) comme les
actions fichiers (import, groupement, dégroupement, enregistrement — le undo
restaure les backups et supprime les fichiers créés). **« 💾 Enregistrer »**
écrit les positions modifiées ; le bouton **« 💾 Tout enregistrer »** de la
barre d'app sauvegarde tous les onglets d'un coup (wireframe + config des
mesures). Le bandeau vert sous le canevas raconte la dernière action.

Les changements s'accumulent à l'écran (indicateur « ● N modifié(s) »).
**Enregistrer les positions** écrit les `visual.json` concernés — uniquement le
bloc `position` (converti en coordonnées locales au groupe ; z/tabOrder
préservés), **Desktop FERMÉ**, backup sous `_wireframe_backups\<horodatage>\`,
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
`_wireframe_backups\<horodatage>\import_manifest.txt` (undo = supprimer les
dossiers listés). ⚠ Le modèle importé référence les tables/champs du modèle
sémantique du GABARIT — compatibilité à vérifier (même modèle ou champs
communs). Voir `core/template_import.py`.

### Onglet « Mesures »

Tout ce qui touche aux mesures au même endroit — quatre sous-onglets :
**Variations** (l'éditeur ci-dessous), **Réglages globaux**, **JSON brut** et
**Générer** (la génération native, plus bas). Éditeur de
`measures_config.json` — chaque variation s'édite dans un
formulaire complet avec tooltips explicatifs partout : namePattern,
description, **formatString en dropdown** (inherit / delta / **text** = aucun
format / formats usuels, saisie libre permise), displayFolder,
**folderVariation en dropdown** des autres variations (« dossier hôte » — ex.
CF Δ 30d vit dans le dossier de Δ 30d), **dataCategory en dropdown**
(ImageUrl/WebUrl), inFieldParameter, plus :

- **éditeur DAX en clair** : le format JSON array-of-lines devient invisible
  (colle ton bloc DAX, il est sérialisé en lignes à la sauvegarde ; round-trip
  fidèle, clés inconnues préservées) ;
- **lint des placeholders** : tout `{jeton}` serré inconnu est signalé
  (les constructeurs de table DAX `{ ad }` sont tolérés) ;
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
  l'aperçu ne peut donc pas diverger de ce qui sera écrit ;
- boutons Ajouter / Dupliquer / Renommer / Supprimer + **↑ Monter / ↓ Descendre**
  (réordonne les variations — l'ordre pilote celui des calculs dans le
  paramètre de champ et la génération) ;
- sous-onglet **Réglages globaux** : `settings`, `fieldParameter`, `switch` et
  `branches` en cases/champs (les listes de tables paramètre en multi-lignes ;
  les branches en cases à cocher sur les variations, **+ un éditeur de
  restriction** : pour chaque branche, cocher quelles variations elle applique —
  ex. exclure une cible autonome en {kpi} du fork YTD) — plus besoin d'éditer le
  JSON à la main pour les variables globales ;
- sous-onglet **JSON brut** (tout le fichier, validation avant de revenir) ;
- **Sauvegarder** : backup `measures_config.json.bak` puis écriture.

**Sous-onglet « Générer »** : le bouton **« Générer les mesures »** exécute
`generate_measures.py` sur le modèle du projet : mesures × variations ×
branches, tables paramètre de champ, mesure Switch — **sans Tabular Editor ni
Desktop ouvert**. Récap du config en tête ; « Aperçu (dry-run) » coché par
défaut (liste tout, n'écrit rien) ; case « Supprimer les orphelines » ;
l'écriture réelle demande confirmation (Desktop FERMÉ), sauvegarde sous
`_tmdl_backups\`, puis rouvrir le `.pbip`. Le générateur lit le fichier sur le
disque : un bandeau prévient si le config a des modifs non sauvegardées.
Workflow complet, tout dans l'onglet Mesures : éditer → **Sauvegarder** →
sous-onglet **Générer** → rouvrir Desktop.

### Onglet « ChopChop 🪓 »

Le panneau complet de ChopChopRapport (section 8) dans PBIdouille : mesures et
colonnes inutilisées, filtre par table, export, suppression TMDL + Power Query
— sur le projet de la barre partagée. L'analyse se déclenche à l'ouverture de
l'onglet (changer de projet reste instantané). La version autonome
`py unused_measures_ui.py` continue de fonctionner (même panneau).

### Feuille de route

- Wireframe : redimensionner un groupe (simulation ScaleMode), configurer les
  attributs d'un modèle importé (champs, titres) depuis l'UI.
