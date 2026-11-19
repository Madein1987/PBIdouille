# Mesures › JSON brut

[Documentation](../README.md) › Mesures › **JSON brut** · voir aussi [Variations](variations.md), [Paramètres de champ](parametres-champ.md)

L'onglet **JSON brut** montre tout le `measures_config.json` du rapport, et permet de
le modifier directement. Il sert pour une modification en série, pour copier un bloc
d'un rapport à l'autre, ou pour un réglage qui n'a pas de champ dans l'app.

Pour un changement courant, **Variations** et **⚙ Réglages** sont plus sûrs : leurs
champs guident la saisie.

![L'onglet JSON brut](../images/json_brut.png)

## Modifier le config

1. Ouvrir **JSON brut**. Le texte reflète le config en mémoire, y compris ce qui a été
   changé dans les autres onglets sans être sauvegardé.
2. Modifier le texte. **Tab**, **Maj+Tab** et **Début** agissent comme dans l'éditeur DAX.
3. Cliquer **Valider le JSON** pour contrôler la syntaxe.
4. Cliquer **Sauvegarder**.

La sauvegarde écrit `measures_config.json` et garde la version précédente dans
`measures_config.json.bak`.

## Si le JSON est invalide

| Geste | Résultat |
|---|---|
| **Valider le JSON** | Un message indique l'erreur et sa position |
| Changer d'onglet | Le changement est refusé, et l'onglet reste ouvert sur le texte à corriger |
| **Sauvegarder** | Rien n'est écrit, et un message indique l'erreur |

**Valider le JSON** contrôle seulement la syntaxe. Une clé mal orthographiée passe la
validation, et elle sera ignorée ou signalée à la génération. L'onglet
[Arbre des mesures](arbre.md) permet de vérifier le résultat avant d'écrire.

## Les grands blocs

| Clé | Contenu | Où le modifier autrement |
|---|---|---|
| `settings` | Tables, dossiers, colonne de dates, rangement | [⚙ Réglages → Génération](../reglages.md#génération) |
| `variations` | Les recettes de mesures | [Variations](variations.md) |
| `branches` | Les branches, comme YTD | [⚙ Réglages → Branches](../reglages.md#branches) |
| `fieldParameter` | Les tables paramètre de champ | [Paramètres de champ](parametres-champ.md) |
| `kpiMeasureFolders` | Les dossiers de cibles | [⚙ Réglages → Mesures cibles](../reglages.md#mesures-cibles) |
| `indicateursXlsx` | Le fichier TD_Indicateurs et ses colonnes | [⚙ Réglages → Excel des indicateurs](../reglages.md#excel-des-indicateurs) |
| `hardcodedAttributes` | Les attributs `<<…>>` | [Fenêtre des jetons](jetons.md#créer-et-modifier-un-attribut) |

La référence complète de chaque clé se trouve dans le
[README technique](../../README.md#4-measures_configjson--référence).
