// =====================================================================
// Création des variations de mesures — script Tabular Editor 2 / 3
// ---------------------------------------------------------------------
// Lit measures_config.json puis :
//   1. crée/met à jour une mesure par combinaison (mesure de base x
//      variation) ;
//   2. régénère la table « paramètre de champ » qui expose ces mesures
//      (une rangée par mesure, avec colonnes Indicateur et Calcul pour
//      filtrer via TD_Indicateurs et un slicer).
//
// Les mesures de base sont découvertes automatiquement : toutes les
// mesures de la table settings.sourceTable dont le displayFolder est
// settings.sourceFolder. Les mesures générées par ce script portent une
// annotation et sont exclues de la découverte — donc pas de risque de
// créer des variations de variations en relançant le script.
//
// Relancer le script est sans danger : mesures et paramètre de champ
// sont mis à jour au lieu d'être dupliqués.
//
// Utilisation : Tabular Editor (ouvert via Outils externes dans Power BI
// Desktop) -> onglet C# Script -> exécuter -> Ctrl+S pour pousser les
// changements vers le modèle.
//
// NOTE (paramètre de champ) : certaines versions de Power BI Desktop
// refusent la CRÉATION d'une table calculée par un outil externe. Si le
// Ctrl+S échoue pour cette raison : créer le paramètre une seule fois
// via l'interface (Modélisation > Nouveau paramètre > Champs, avec
// n'importe quels champs), puis relancer ce script — la mise à jour de
// l'expression, elle, passe. Les colonnes 4 à 6 apparaîtront alors
// comme « Value4 » à « Value6 » ; une exécution de plus les renomme.
//
// La relation TD_Indicateurs[...] -> P_Indicateurs[Indicateur] est à
// créer une fois dans Tabular Editor (l'interface de Desktop refuse
// souvent les relations vers un paramètre de champ ; via TE ça
// fonctionne très bien).
//
// Schéma de measures_config.json :
//
//   settings.sourceTable           table où chercher les mesures de base
//   settings.sourceFolder          displayFolder exact des mesures de base
//                                  (omettre = toutes les mesures de la table)
//   settings.dateColumn            référence DAX substituée à {date}
//   settings.targetTable           table qui reçoit les mesures générées
//                                  (omettre = même table que la mesure de base)
//   settings.displayFolderPattern  dossier d'affichage des mesures générées.
//                                  Placeholders : {baseFolder} {base} {variation}
//                                  {kpi} (libellé KPI). Réutilisé en 2e passe
//                                  avec {baseFolder} = racine de la branche
//   settings.branchFolderPattern   dossier de LA MESURE de branche elle-même
//                                  (= racine de la branche, ex. _indicateurs\__YTD ;
//                                  ses variations s'organisent autour via
//                                  displayFolderPattern). {branch} = id de la
//                                  branche. Défaut : {baseFolder}\__{branch}
//   settings.overwriteExisting     true = met à jour les mesures qui existent
//                                  déjà (défaut true)
//   settings.removeOrphans         true = supprime les mesures créées par ce
//                                  script qui ne sont plus dans la config
//                                  (défaut false)
//   settings.dryRun                true = rapport seulement, aucune
//                                  modification (défaut false)
//
//   fieldParameter                 génération du/des paramètres de champ
//     enabled                      true/false (défaut true si la section existe)
//     tableNames                   un OU plusieurs noms de tables paramètre
//                                  IDENTIQUES, ex. ["P_Indicateurs",
//                                  "P_Indicateurs 2"] — utile pour faire deux
//                                  sélections indépendantes dans les visuels
//                                  (chaque table a besoin de SA relation vers
//                                  TD_Indicateurs). tableName (chaîne) accepté.
//                                  Colonnes techniques dérivées du nom :
//                                  « <nom> », « <nom> Fields », « <nom> Ordre ».
//                                  Ordre = rang UNIQUE KPI-puis-calcul : vue
//                                  mono-KPI inchangée (ordre des calculs), vue
//                                  multi-KPI groupée par KPI.
//     tableNamesByKpi              comme tableNames, mais la colonne d'affichage
//                                  est le NOM DU KPI (tri par index de KPI) :
//                                  pour les visuels qui comparent les KPI entre
//                                  eux, le calcul étant fixé par un slicer
//                                  Calcul en sélection simple
//     tableNamesKpiBase            comme tableNames, mais la rangée de BASE
//                                  affiche le libellé du KPI (LOOKUPVALUE sur la
//                                  dimension) au lieu de baseLabel ; les
//                                  variations gardent leur nom de calcul
//     kpiLabelLookup               { table, keyColumn, labelColumn } : où
//                                  chercher le libellé. keyColumn doit contenir
//                                  les NOMS DE MESURES (= colonne Indicateur)
//     kpiColumn                    colonne KPI — la clé qui matche TD_Indicateurs
//     calcColumn                   colonne du type de calcul (pour slicer)
//     branchColumn                 colonne Branche : permet de basculer entre
//                                  la version normale et les branches avec les
//                                  mêmes libellés Calcul
//     noBranchLabel                valeur de Branche pour les rangées hors
//                                  branche (défaut « Base »)
//     includeBase                  true = une rangée pour la mesure de base
//     baseLabel                    libellé de cette rangée (ex. « Base »)
//
//   La colonne Indicateur contient le NOM de la mesure de base ; les libellés
//   conviviaux vivent dans TD_Indicateurs (LOOKUPVALUE au besoin).
//
//   switch                         mesure « switch » : UNE mesure qui bascule
//                                  entre tous les KPI selon la sélection, puis
//                                  toutes les variations sont générées dessus
//                                  comme pour un KPI normal. Exceptions :
//                                  jamais dans les paramètres de champ, et
//                                  rangée dans un dossier dédié.
//     enabled                      true/false (défaut true si la section existe)
//     name                         nom de la mesure switch
//     selector                     colonne pour SELECTEDVALUE — ses valeurs
//                                  doivent être les noms des mesures de base
//                                  (ex. 'TD_KPI'[mesure])
//     displayFolder                dossier racine du switch (défaut _switch ;
//                                  ses variations s'y organisent comme ailleurs)
//     formatString                 format statique (hérité par les variations)
//     dynamicFormat                true = la mesure switch reçoit un format
//                                  DYNAMIQUE qui suit le KPI sélectionné
//                                  (les variations restent sur le statique)
//
//   variations                     objet dont chaque clé est l'id d'une
//                                  variation : { "MTD": { ... }, ... }
//     namePattern                  nom de la mesure générée
//     dax                          expression DAX (chaîne OU tableau de lignes)
//     formatString                 "inherit" = copie le format de la mesure de
//                                  base ; "delta" = format signé +x;-x;x dérivé
//                                  de la section positive du format de la base
//                                  (une base en % devient « pts », le ×100
//                                  venant de {deltaScale} dans le dax) ;
//                                  "text" = AUCUN format (mesure texte, ex.
//                                  hex des CF — vide/absent voudrait dire
//                                  inherit) ;
//                                  {baseFormat} = insère la section positive du
//                                  format de la base dans un pattern
//     description                  description de la mesure générée
//     inFieldParameter             true = la mesure apparaît dans le paramètre
//                                  de champ. Défaut : false — la mesure est
//                                  créée normalement mais reste hors du
//                                  paramètre (ex. : formatage conditionnel)
//     displayFolder                dossier spécifique pour cette variation,
//                                  remplace le dossier par défaut de la passe.
//                                  {folder} = dossier par défaut déjà calculé
//                                  (pratique : "{folder}\_CF" fonctionne en
//                                  passe normale ET en branche), plus les
//                                  placeholders habituels
//     folderVariation              id de variation à utiliser pour {variation}
//                                  dans les DOSSIERS seulement. Ex. : « CF YoY % »
//                                  avec folderVariation "YoY %" se range dans
//                                  le dossier de YoY %
//     dataCategory                 catégorie de données de la mesure, ex.
//                                  "ImageUrl" pour une mesure SVG (sparkline)
//                                  affichée en image. Omis = inchangé.
//
//   branches                       variations de variations : la mesure générée
//                                  par une variation devient à son tour une base.
//                                  Objet { "YTD": { "variations": [ids...] }, ... }
//                                  - la clé est l'id d'une variation existante ;
//                                  - "variations" : liste des templates à appliquer
//                                    par-dessus ; OMISE = toutes les variations
//                                    (sauf la branche elle-même) ;
//                                  - un seul niveau (pas de branche de branche) ;
//                                  - dans le paramètre de champ, les rangées de
//                                    branche gardent les MÊMES libellés et index
//                                    de tri que la passe normale ; c'est la
//                                    colonne Branche qui fait la distinction, et
//                                    la mesure de branche (ex. YTD) devient la
//                                    rangée « Base » de sa branche ;
//                                  - les flags inFieldParameter / displayFolder
//                                    des templates s'appliquent aussi en branche.
//
//   Placeholders disponibles dans namePattern / dax / description :
//     {base}       nom de la mesure de base       -> Weight (locf)  (EN BRANCHE :
//                  inclut le suffixe, ex. « Weight YTD »)
//     {baseRef}    référence à la mesure de base  -> [Weight (locf)]
//     {kpi}        nom du KPI RACINE (sans suffixe de branche) -> Weight ;
//                  identique en Réel ET en branche. Pour les LOOKUPVALUE sur
//                  TD_Indicateurs (direction, libellé) où la clé = mesure de base.
//     {date}       settings.dateColumn            -> 'dim_Date'[Date]
//     {variation}  id de la variation             -> MTD
//     {deltaScale} 100 si la base a un format %, sinon 1 — à mettre dans le
//                  dax des deltas pour l'affichage en points (" pts")
//
// IMPORTANT — tri du paramètre de champ : la colonne d'affichage est
// triée par la colonne d'ordre (SortByColumn). Comme le même libellé
// (ex. « 7d avg ») revient pour chaque KPI, l'index de tri est PAR
// VARIATION (constant pour un même libellé), pas séquentiel par rangée.
// Un index séquentiel ferait planter le tri.
// =====================================================================

// Chemin du fichier de config. S'il n'existe pas (ex. : sur le poste du
// travail), une boîte de dialogue s'ouvre pour le choisir.
var configPath = @"C:\OneDrive - PJ\Data Cooler\_Power BI\Fitbit\measures_config.json";

if (!System.IO.File.Exists(configPath))
{
    var dlg = new System.Windows.Forms.OpenFileDialog();
    dlg.Title = "Choisir measures_config.json";
    dlg.Filter = "Fichiers JSON (*.json)|*.json|Tous les fichiers (*.*)|*.*";
    if (dlg.ShowDialog() != System.Windows.Forms.DialogResult.OK)
    {
        Info("Annulé — aucun fichier de config choisi.");
        return;
    }
    configPath = dlg.FileName;
}

var config = Newtonsoft.Json.Linq.JObject.Parse(System.IO.File.ReadAllText(configPath));

// ---- paramètres ------------------------------------------------------
var settings = config["settings"] as Newtonsoft.Json.Linq.JObject;
if (settings == null) settings = new Newtonsoft.Json.Linq.JObject();

var sourceTable   = settings["sourceTable"] != null ? (string)settings["sourceTable"] : "_mesures";
var sourceFolder  = settings["sourceFolder"] != null ? (string)settings["sourceFolder"] : null;
var dateColumn    = settings["dateColumn"] != null ? (string)settings["dateColumn"] : "'dim_Date'[Date]";
var defaultTable  = settings["targetTable"] != null ? (string)settings["targetTable"] : null;
var folderPattern = settings["displayFolderPattern"] != null ? (string)settings["displayFolderPattern"] : "{baseFolder}";
var branchFolderPattern = settings["branchFolderPattern"] != null ? (string)settings["branchFolderPattern"] : "{baseFolder}\\__{branch}";
var overwrite     = settings["overwriteExisting"] != null ? (bool)settings["overwriteExisting"] : true;
var removeOrphans = settings["removeOrphans"] != null ? (bool)settings["removeOrphans"] : false;
var dryRun        = settings["dryRun"] != null ? (bool)settings["dryRun"] : false;

// paramètre de champ
var fpConfig   = config["fieldParameter"] as Newtonsoft.Json.Linq.JObject;
var fpEnabled  = fpConfig != null && (fpConfig["enabled"] == null || (bool)fpConfig["enabled"]);
// une ou plusieurs tables paramètre identiques (tableNames: tableau,
// tableName: chaîne). Les colonnes techniques sont dérivées de chaque nom.
var fpTables = new List<string>();
if (fpConfig != null && fpConfig["tableNames"] != null)
    foreach (var t in (Newtonsoft.Json.Linq.JArray)fpConfig["tableNames"]) fpTables.Add((string)t);
else if (fpConfig != null && fpConfig["tableName"] != null)
    fpTables.Add((string)fpConfig["tableName"]);
else
    fpTables.Add("P_Indicateurs");

// tables paramètre « par KPI » : affichage = nom du KPI au lieu du calcul
var fpTablesKpi = new List<string>();
if (fpConfig != null && fpConfig["tableNamesByKpi"] != null)
    foreach (var t in (Newtonsoft.Json.Linq.JArray)fpConfig["tableNamesByKpi"]) fpTablesKpi.Add((string)t);

// tables paramètre « base = libellé KPI » : comme parCalcul, mais la rangée
// de base affiche le libellé du KPI (LOOKUPVALUE) au lieu de baseLabel
var fpTablesKpiBase = new List<string>();
if (fpConfig != null && fpConfig["tableNamesKpiBase"] != null)
    foreach (var t in (Newtonsoft.Json.Linq.JArray)fpConfig["tableNamesKpiBase"]) fpTablesKpiBase.Add((string)t);

var lkpConfig = fpConfig != null ? fpConfig["kpiLabelLookup"] as Newtonsoft.Json.Linq.JObject : null;
var lkpTable  = lkpConfig != null && lkpConfig["table"] != null ? (string)lkpConfig["table"] : "TD_Indicateurs";
var lkpKeyCol = lkpConfig != null && lkpConfig["keyColumn"] != null ? (string)lkpConfig["keyColumn"] : "mesure";
var lkpLblCol = lkpConfig != null && lkpConfig["labelColumn"] != null ? (string)lkpConfig["labelColumn"] : "libelle_indicateur";
// références DAX 'Table'[Colonne]
var lkpKeyRef = "'" + lkpTable.Replace("'", "''") + "'[" + lkpKeyCol.Replace("]", "]]") + "]";
var lkpLblRef = "'" + lkpTable.Replace("'", "''") + "'[" + lkpLblCol.Replace("]", "]]") + "]";

var fpKpiCol   = fpConfig != null && fpConfig["kpiColumn"] != null ? (string)fpConfig["kpiColumn"] : "Indicateur";
var fpCalcCol  = fpConfig != null && fpConfig["calcColumn"] != null ? (string)fpConfig["calcColumn"] : "Calcul";
var fpInclBase = fpConfig != null && fpConfig["includeBase"] != null ? (bool)fpConfig["includeBase"] : true;
var fpBaseLbl  = fpConfig != null && fpConfig["baseLabel"] != null ? (string)fpConfig["baseLabel"] : "Base";
var fpBranchCol   = fpConfig != null && fpConfig["branchColumn"] != null ? (string)fpConfig["branchColumn"] : "Branche";
var fpNoBranchLbl = fpConfig != null && fpConfig["noBranchLabel"] != null ? (string)fpConfig["noBranchLabel"] : "Base";

// mesure switch
var swConfig   = config["switch"] as Newtonsoft.Json.Linq.JObject;
var swEnabled  = swConfig != null && (swConfig["enabled"] == null || (bool)swConfig["enabled"]);
var swName     = swConfig != null && swConfig["name"] != null ? (string)swConfig["name"] : "Switch KPI";
var swSelector = swConfig != null && swConfig["selector"] != null ? (string)swConfig["selector"] : "'TD_KPI'[mesure]";
var swFolder   = swConfig != null && swConfig["displayFolder"] != null ? (string)swConfig["displayFolder"] : "_switch";
var swFmt      = swConfig != null && swConfig["formatString"] != null ? (string)swConfig["formatString"] : "#,0.0";
var swDynFmt   = swConfig != null && swConfig["dynamicFormat"] != null ? (bool)swConfig["dynamicFormat"] : true;

const string ANNOTATION = "MeasureVariation"; // marque les mesures générées : "base|variation"

// Accepte une chaîne JSON ou un tableau de lignes, retourne une seule chaîne.
Func<Newtonsoft.Json.Linq.JToken, string> tokenToText = delegate(Newtonsoft.Json.Linq.JToken t)
{
    if (t == null) return null;
    if (t.Type == Newtonsoft.Json.Linq.JTokenType.Array)
    {
        var lines = new List<string>();
        foreach (var x in (Newtonsoft.Json.Linq.JArray)t) lines.Add((string)x);
        return string.Join("\n", lines);
    }
    return (string)t;
};

// Échappe une chaîne destinée à un littéral DAX entre guillemets.
Func<string, string> daxStr = delegate(string s)
{
    return s == null ? "" : s.Replace("\"", "\"\"");
};

// Première section (valeurs positives) d'un format string, sans signe
// initial. Gère les ';' échappés ou entre guillemets.
Func<string, string> positiveSection = delegate(string f)
{
    if (string.IsNullOrEmpty(f)) return f;
    var inQuote = false;
    var cut = f.Length;
    for (var i = 0; i < f.Length; i++)
    {
        var ch = f[i];
        if (ch == '"') inQuote = !inQuote;
        else if (ch == '\\') i++;
        else if (ch == ';' && !inQuote) { cut = i; break; }
    }
    var s = f.Substring(0, cut).Trim();
    while (s.Length > 0 && (s[0] == '+' || s[0] == '-')) s = s.Substring(1);
    return s;
};

// Le format contient-il un % actif (non échappé, hors guillemets) ?
// Un % actif multiplie l'affichage par 100.
Func<string, bool> hasScalingPercent = delegate(string f)
{
    if (string.IsNullOrEmpty(f)) return false;
    var inQuote = false;
    for (var i = 0; i < f.Length; i++)
    {
        var ch = f[i];
        if (ch == '"') inQuote = !inQuote;
        else if (ch == '\\') i++;
        else if (ch == '%' && !inQuote) return true;
    }
    return false;
};

// Transforme la section d'un format % en format « points » : retire le %
// actif (et l'espace, échappé ou non, qui le précède) et ajoute " pts".
// Le ×100 que faisait le % doit alors venir du DAX ({deltaScale}).
Func<string, string> toPtsFormat = delegate(string core)
{
    var b = new System.Text.StringBuilder();
    var inQuote = false;
    for (var i = 0; i < core.Length; i++)
    {
        var ch = core[i];
        if (ch == '"') { inQuote = !inQuote; b.Append(ch); }
        else if (ch == '\\')
        {
            if (i + 1 < core.Length) { b.Append(ch); b.Append(core[i + 1]); i++; }
        }
        else if (ch == '%' && !inQuote)
        {
            if (b.Length >= 2 && b[b.Length - 2] == '\\' && b[b.Length - 1] == ' ') b.Length -= 2;
            else if (b.Length >= 1 && b[b.Length - 1] == ' ') b.Length -= 1;
            // le % lui-même disparaît
        }
        else b.Append(ch);
    }
    return b.ToString() + "\" pts\"";
};

// Récupère l'objet TOM (Microsoft.AnalysisServices.Tabular.Column) derrière
// une colonne du wrapper Tabular Editor. La propriété MetadataObject est
// internal dans certaines versions de TE -> on passe par réflexion.
Func<object, Microsoft.AnalysisServices.Tabular.Column> tomColumn = delegate(object wrapperCol)
{
    var tp = wrapperCol.GetType();
    while (tp != null)
    {
        var pi = tp.GetProperty("MetadataObject",
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.DeclaredOnly);
        if (pi != null) return (Microsoft.AnalysisServices.Tabular.Column)pi.GetValue(wrapperCol, null);
        tp = tp.BaseType;
    }
    return null;
};

// Idem pour une mesure (FormatStringDefinition n'est pas exposé par le wrapper).
Func<object, Microsoft.AnalysisServices.Tabular.Measure> tomMeasure = delegate(object wrapperMeas)
{
    var tp = wrapperMeas.GetType();
    while (tp != null)
    {
        var pi = tp.GetProperty("MetadataObject",
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.DeclaredOnly);
        if (pi != null) return (Microsoft.AnalysisServices.Tabular.Measure)pi.GetValue(wrapperMeas, null);
        tp = tp.BaseType;
    }
    return null;
};

// ---- modèles de variations -------------------------------------------
var varsObj = config["variations"] as Newtonsoft.Json.Linq.JObject;
if (varsObj == null || !varsObj.Properties().Any())
{
    Error("La config n'a pas d'objet 'variations'.");
    return;
}

// branches : variations dont la mesure générée devient elle-même une base
// pour une 2e passe (ex. : YTD -> YTD PY, YTD 7d avg, ...)
var branchesObj = config["branches"] as Newtonsoft.Json.Linq.JObject;

// Liste effective des variations d'une branche : la liste explicite si
// fournie, sinon TOUS les templates (sauf la branche elle-même).
Func<string, Newtonsoft.Json.Linq.JObject, List<string>> branchVariationIds =
    delegate(string branchId, Newtonsoft.Json.Linq.JObject bDef)
{
    var ids = new List<string>();
    if (bDef != null && bDef["variations"] != null)
    {
        foreach (var t in (Newtonsoft.Json.Linq.JArray)bDef["variations"]) ids.Add((string)t);
    }
    else
    {
        foreach (var p in varsObj.Properties())
            if (!string.Equals(p.Name, branchId, StringComparison.OrdinalIgnoreCase)) ids.Add(p.Name);
    }
    return ids;
};

// Index de tri par variation (voir note IMPORTANT en entête).
// includeBase décale tout de 1 : la rangée « Base » prend l'index 0.
// Seules les variations marquées inFieldParameter=true entrent dans le
// paramètre et consomment un index.
var varOrder = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
var orderIdx = fpInclBase ? 1 : 0;
foreach (var p in varsObj.Properties())
{
    var o = p.Value as Newtonsoft.Json.Linq.JObject;
    var inParam = o != null && o["inFieldParameter"] != null && (bool)o["inFieldParameter"];
    if (inParam) { varOrder[p.Name] = orderIdx; orderIdx++; }
}

// Les rangées de branche réutilisent les MÊMES libellés et donc les MÊMES
// index que la passe normale (exigence de SortByColumn : un libellé = un
// seul index). C'est la colonne Branche qui les distingue — rien à ajouter.

// ---- découverte des mesures de base -----------------------------------
if (!Model.Tables.Contains(sourceTable))
{
    Error("Table source introuvable : " + sourceTable);
    return;
}

var baseMeasures = Model.Tables[sourceTable].Measures
    .Where(m => m.GetAnnotation(ANNOTATION) == null
             && (sourceFolder == null || string.Equals(m.DisplayFolder, sourceFolder, StringComparison.OrdinalIgnoreCase)))
    // tri CULTUREL explicite (= celui de Power BI) : insensible à la casse, donc
    // 'avg Steps' se range entre 'Average' et 'Body', pas avant tout le reste
    // comme le ferait un tri ordinal. Cet ordre devient la colonne Ordre des
    // paramètres de champ — il doit coller à l'ordre affiché par le rapport.
    .OrderBy(m => m.Name, StringComparer.CurrentCulture)
    .ToList();

if (baseMeasures.Count == 0)
{
    Warning("Aucune mesure de base trouvée dans '" + sourceTable + "'"
        + (sourceFolder != null ? " (dossier '" + sourceFolder + "')" : "") + ".");
    return;
}

var created = new List<string>();
var updated = new List<string>();
var skipped = new List<string>();
var planned = new HashSet<string>();   // annotations qui doivent exister après cette exécution
var fpRows  = new List<object[]>();    // rangées du paramètre de champ :
                                       // [affichage, réf DAX, index de tri, KPI, calcul, branche]

// Traite une combinaison (base x variation) : crée ou met à jour la mesure
// et ajoute sa rangée au paramètre de champ. Retourne { nom, format, dossier }
// de la mesure générée (réutilisé par les branches), ou null si ignorée.
//   baseName   : nom de la mesure de base
//   tTable     : table cible (déjà résolue)
//   baseFmt    : formatString de la base (pour "inherit")
//   baseFolder : displayFolder de la base (pour {baseFolder})
//   kpiLbl     : libellé KPI dans le paramètre de champ
//   id         : id du template de variation
//   tpl        : le template
//   fpLabel    : libellé (affichage + Calcul) dans le paramètre — identique
//                en branche ; null = pas de rangée (la mesure de branche a
//                sa rangée « Base » gérée au site d'appel)
//   fpOrderKey : clé d'index de tri dans varOrder (l'id du template)
//   fpBranch   : valeur de la colonne Branche (noBranchLabel ou id de branche)
//   passFolderPattern : pattern de dossier par défaut de la passe
//                (displayFolderPattern, ou branchFolderPattern pour une
//                mesure de branche en 1re passe)
//   branchId   : id de la branche (null hors branche), pour {branch}
Func<string, Table, string, string, string, string, Newtonsoft.Json.Linq.JObject, string, string, string, string, string, object[]> processVariation =
    delegate(string baseName, Table tTable, string baseFmt, string baseFolder, string kpiLbl,
             string id, Newtonsoft.Json.Linq.JObject tpl, string fpLabel, string fpOrderKey, string fpBranch,
             string passFolderPattern, string branchId)
{
    // ×100 pour les deltas de mesures en % (affichage en points via "delta")
    var deltaScale = hasScalingPercent(baseFmt) ? "100" : "1";

    Func<string, string> expand = delegate(string s)
    {
        if (s == null) return null;
        return s
            .Replace("{baseRef}", "[" + baseName + "]")
            .Replace("{base}", baseName)
            // {kpi} = nom du KPI RACINE (sans suffixe de branche). En branche,
            // {base} = « Weight YTD » mais {kpi} = « Weight » -> pour les
            // LOOKUPVALUE sur TD_Indicateurs (direction, libellé...) où la clé
            // est le nom de la mesure de base.
            .Replace("{kpi}", kpiLbl == null ? "" : kpiLbl)
            .Replace("{date}", dateColumn)
            .Replace("{variation}", id)
            .Replace("{deltaScale}", deltaScale);
    };

    var varName = expand((string)tpl["namePattern"]);
    var dax     = expand(tokenToText(tpl["dax"]));
    var desc    = expand(tokenToText(tpl["description"]));
    var fmt     = (string)tpl["formatString"];
    if (string.IsNullOrEmpty(fmt) || fmt == "inherit") fmt = baseFmt;
    else if (fmt == "text") fmt = null;   // mesure TEXTE : aucun format
    else if (fmt == "delta")
    {
        // format signé dérivé de la section positive de la base : +x;-x;x.
        // Les bases en % deviennent « pts » (le ×100 vient de {deltaScale}).
        var core = positiveSection(baseFmt);
        if (string.IsNullOrEmpty(core)) fmt = null;
        else
        {
            if (hasScalingPercent(core)) core = toPtsFormat(core);
            fmt = "+" + core + ";-" + core + ";" + core;
        }
    }
    else if (fmt.Contains("{baseFormat}"))
        fmt = string.IsNullOrEmpty(baseFmt) ? null : fmt.Replace("{baseFormat}", positiveSection(baseFmt));

    if (string.IsNullOrEmpty(varName) || string.IsNullOrEmpty(dax))
    {
        Warning("La variation '" + id + "' n'a pas de namePattern ou de dax — ignorée.");
        return null;
    }

    // {variation} des DOSSIERS : folderVariation du template si défini
    // (ex. : une CF se range dans le dossier de la variation qu'elle met
    // en forme), sinon l'id du template
    var folderVar = tpl["folderVariation"] != null ? (string)tpl["folderVariation"] : id;

    // dossier par défaut de la passe (sert aussi au placeholder {folder})
    var defaultFolder = passFolderPattern
        .Replace("{baseFolder}", baseFolder == null ? "" : baseFolder)
        .Replace("{base}", baseName)
        .Replace("{variation}", folderVar)
        .Replace("{kpi}", kpiLbl == null ? "" : kpiLbl)
        .Replace("{branch}", branchId == null ? "" : branchId);

    // displayFolder du template s'il existe, sinon le dossier par défaut
    var folderTpl = tpl["displayFolder"] != null ? (string)tpl["displayFolder"] : "{folder}";
    var folder = folderTpl
        .Replace("{folder}", defaultFolder)
        .Replace("{baseFolder}", baseFolder == null ? "" : baseFolder)
        .Replace("{base}", baseName)
        .Replace("{variation}", folderVar)
        .Replace("{kpi}", kpiLbl == null ? "" : kpiLbl)
        .Replace("{branch}", branchId == null ? "" : branchId);

    var tag = baseName + "|" + id;
    planned.Add(tag);

    // les noms de mesures sont uniques dans tout le modèle : chercher partout
    var existing = Model.AllMeasures.FirstOrDefault(m => m.Name.Equals(varName, StringComparison.OrdinalIgnoreCase));

    // rangée du paramètre de champ (mêmes libellés en branche, c'est la
    // colonne Branche qui distingue) — seulement si le template est marqué
    // inFieldParameter=true
    var inFieldParam = tpl["inFieldParameter"] != null && (bool)tpl["inFieldParameter"];
    if (inFieldParam && fpLabel != null)
    {
        var measureRef = existing != null
            ? existing.DaxObjectFullName
            : "'" + tTable.Name.Replace("'", "''") + "'[" + varName.Replace("]", "]]") + "]";
        fpRows.Add(new object[] { fpLabel, measureRef, varOrder[fpOrderKey], kpiLbl, fpLabel, fpBranch });
    }

    // catégorie de données (ex. "ImageUrl" pour une mesure SVG). null = ne pas
    // toucher. Propriété absente sur certaines versions de TE -> try/catch.
    var dataCat = tpl["dataCategory"] != null ? (string)tpl["dataCategory"] : null;

    if (existing != null)
    {
        if (!overwrite)
        {
            skipped.Add(varName);
            // la mesure existe déjà : une branche peut quand même s'appuyer dessus
            return new object[] { varName, existing.FormatString, existing.DisplayFolder };
        }
        if (!dryRun)
        {
            existing.Expression = dax;
            existing.FormatString = fmt;
            existing.DisplayFolder = folder;
            if (desc != null) existing.Description = desc;
            existing.SetAnnotation(ANNOTATION, tag);
            if (dataCat != null) { try { existing.DataCategory = dataCat; } catch (Exception) {} }
        }
        updated.Add(varName);
    }
    else
    {
        if (!dryRun)
        {
            var m = tTable.AddMeasure(varName, dax);
            m.FormatString = fmt;
            m.DisplayFolder = folder;
            if (desc != null) m.Description = desc;
            m.SetAnnotation(ANNOTATION, tag);
            if (dataCat != null) { try { m.DataCategory = dataCat; } catch (Exception) {} }
        }
        created.Add(varName);
    }
    return new object[] { varName, fmt, folder };
};

// ---- 1re passe : mesures de base x variations ---------------------------
// Les mesures générées par une variation déclarée comme branche sont
// collectées pour servir de bases à la 2e passe.
var branchBases = new List<object[]>(); // { nom, Table, format, racine de la branche, libellé KPI, id de branche, hors paramètre (bool) }

foreach (var baseMeasure in baseMeasures)
{
    // la colonne Indicateur = nom de la mesure ; les libellés conviviaux
    // vivent dans TD_Indicateurs
    var kpiLabel = baseMeasure.Name;

    // rangée « Base » : la mesure brute elle-même
    if (fpInclBase)
        fpRows.Add(new object[] { fpBaseLbl, baseMeasure.DaxObjectFullName, 0, kpiLabel, fpBaseLbl, fpNoBranchLbl });

    // table cible : settings.targetTable, sinon la table de la mesure de base
    Table targetTable;
    if (defaultTable == null)
        targetTable = baseMeasure.Table;
    else if (Model.Tables.Contains(defaultTable))
        targetTable = Model.Tables[defaultTable];
    else
    {
        Warning("Table cible '" + defaultTable + "' introuvable — '" + baseMeasure.Table.Name + "' utilisée à la place.");
        targetTable = baseMeasure.Table;
    }

    foreach (var prop in varsObj.Properties())
    {
        var id = prop.Name;
        var tpl = prop.Value as Newtonsoft.Json.Linq.JObject;
        if (tpl == null)
        {
            Warning("La variation '" + id + "' n'est pas un objet — ignorée.");
            continue;
        }

        // une variation déclarée comme branche utilise branchFolderPattern :
        // sa mesure (ex. YTD) vit à la racine de la branche (__YTD), et ses
        // propres variations s'organiseront autour. Sa rangée de paramètre
        // est gérée à part ci-dessous (fpLabel=null la supprime ici).
        var isBranch = branchesObj != null && branchesObj[id] != null;
        var result = processVariation(baseMeasure.Name, targetTable,
            baseMeasure.FormatString, baseMeasure.DisplayFolder, kpiLabel, id, tpl,
            isBranch ? null : id, id, fpNoBranchLbl,
            isBranch ? branchFolderPattern : folderPattern, isBranch ? id : null);

        if (result != null && isBranch)
        {
            // la mesure de branche devient la rangée « Base » de sa branche :
            // mêmes libellés Calcul partout, la colonne Branche fait la bascule
            var inP = tpl["inFieldParameter"] != null && (bool)tpl["inFieldParameter"];
            if (inP)
            {
                var bm = Model.AllMeasures.FirstOrDefault(m => m.Name.Equals((string)result[0], StringComparison.OrdinalIgnoreCase));
                var bRef = bm != null
                    ? bm.DaxObjectFullName
                    : "'" + targetTable.Name.Replace("'", "''") + "'[" + ((string)result[0]).Replace("]", "]]") + "]";
                fpRows.Add(new object[] { fpBaseLbl, bRef, 0, kpiLabel, fpBaseLbl, id });
            }

            // ... et sert de base à la 2e passe ; son dossier (la racine de
            // la branche) servira de {baseFolder} à ses variations
            branchBases.Add(new object[] { result[0], targetTable, result[1], result[2], kpiLabel, id, false });
        }
    }
}

// ---- mesure switch : un jeu complet de variations qui suit la sélection ----
if (swEnabled)
{
    if (baseMeasures.Count == 0)
    {
        Warning("Switch demandé mais aucune mesure de base — ignoré.");
    }
    else
    {
        // table cible du switch : settings.targetTable, sinon la table source
        Table swTable;
        if (defaultTable != null && Model.Tables.Contains(defaultTable))
            swTable = Model.Tables[defaultTable];
        else
            swTable = Model.Tables[sourceTable];

        // SWITCH(SELECTEDVALUE(...), "KPI", [KPI], ...)
        var swLines = new List<string>();
        swLines.Add("SWITCH(");
        swLines.Add("    SELECTEDVALUE(" + swSelector + "),");
        foreach (var bm in baseMeasures)
            swLines.Add("    \"" + daxStr(bm.Name) + "\", [" + bm.Name + "],");
        swLines.Add("    BLANK()");
        swLines.Add(")");
        var swDax = string.Join("\n", swLines);

        var swTag = "switch|" + swName;
        planned.Add(swTag);

        var swMeasure = Model.AllMeasures.FirstOrDefault(m => m.Name.Equals(swName, StringComparison.OrdinalIgnoreCase));
        if (swMeasure != null)
        {
            if (!dryRun)
            {
                swMeasure.Expression = swDax;
                swMeasure.DisplayFolder = swFolder;
                swMeasure.SetAnnotation(ANNOTATION, swTag);
            }
            updated.Add(swName);
        }
        else
        {
            if (!dryRun)
            {
                swMeasure = swTable.AddMeasure(swName, swDax);
                swMeasure.DisplayFolder = swFolder;
                swMeasure.SetAnnotation(ANNOTATION, swTag);
            }
            created.Add(swName);
        }

        // Format : statique OU dynamique, jamais les deux — FormatString et
        // FormatStringDefinition définis ensemble font échouer la sauvegarde.
        if (!dryRun && swMeasure != null)
        {
            if (swDynFmt)
            {
                try
                {
                    swMeasure.FormatString = null; // efface le statique
                    var fmtLines = new List<string>();
                    fmtLines.Add("SWITCH(");
                    fmtLines.Add("    SELECTEDVALUE(" + swSelector + "),");
                    foreach (var bm in baseMeasures)
                        if (!string.IsNullOrEmpty(bm.FormatString))
                            fmtLines.Add("    \"" + daxStr(bm.Name) + "\", \"" + daxStr(bm.FormatString) + "\",");
                    fmtLines.Add("    \"" + daxStr(swFmt) + "\"");
                    fmtLines.Add(")");
                    var fsd = new Microsoft.AnalysisServices.Tabular.FormatStringDefinition();
                    fsd.Expression = string.Join("\n", fmtLines);
                    tomMeasure(swMeasure).FormatStringDefinition = fsd;
                }
                catch (Exception ex)
                {
                    Warning("Format dynamique non appliqué sur '" + swName + "' (" + ex.Message
                        + ") — retour au format statique.");
                    swMeasure.FormatString = swFmt;
                }
            }
            else
            {
                // retire un éventuel format dynamique d'une exécution
                // précédente (même conflit, dans l'autre sens)
                try { tomMeasure(swMeasure).FormatStringDefinition = null; }
                catch { }
                swMeasure.FormatString = swFmt;
            }
        }

        // toutes les variations sur le switch, comme un KPI normal — mais
        // jamais dans les paramètres de champ (fpLabel=null) et rangées sous
        // le dossier du switch ({baseFolder} = swFolder)
        foreach (var prop in varsObj.Properties())
        {
            var id = prop.Name;
            var tpl = prop.Value as Newtonsoft.Json.Linq.JObject;
            if (tpl == null) continue;

            var isBranch = branchesObj != null && branchesObj[id] != null;
            var result = processVariation(swName, swTable, swFmt, swFolder, swName, id, tpl,
                null, id, fpNoBranchLbl,
                isBranch ? branchFolderPattern : folderPattern, isBranch ? id : null);

            if (result != null && isBranch)
                branchBases.Add(new object[] { result[0], swTable, result[1], result[2], swName, id, true });
        }
    }
}

// ---- 2e passe : branches (variations de variations) ---------------------
foreach (var bb in branchBases)
{
    var bName    = (string)bb[0];
    var bTable   = (Table)bb[1];
    var bFmt     = (string)bb[2];
    var bFolder  = (string)bb[3];
    var bKpi     = (string)bb[4];
    var branchId = (string)bb[5];
    var bNoFp    = (bool)bb[6];   // true = branche du switch : hors paramètre

    var bDef = branchesObj[branchId] as Newtonsoft.Json.Linq.JObject;

    foreach (var vid in branchVariationIds(branchId, bDef))
    {
        if (string.Equals(vid, branchId, StringComparison.OrdinalIgnoreCase))
        {
            Warning("Branche '" + branchId + "' : une branche ne peut pas s'appliquer à elle-même — ignorée.");
            continue;
        }
        var vtpl = varsObj[vid] as Newtonsoft.Json.Linq.JObject;
        if (vtpl == null)
        {
            Warning("Branche '" + branchId + "' : variation inconnue '" + vid + "' — ignorée.");
            continue;
        }

        // mêmes libellés et mêmes index de tri que la passe normale — c'est
        // la colonne Branche qui distingue ; le dossier réutilise le pattern
        // normal avec la racine de la branche comme {baseFolder}
        processVariation(bName, bTable, bFmt, bFolder, bKpi, vid, vtpl,
            bNoFp ? null : vid, vid, branchId,
            folderPattern, branchId);
    }
}

// ---- nettoyage des orphelines : générées mais plus dans la config ------
var removed = new List<string>();
if (removeOrphans)
{
    var orphans = Model.AllMeasures
        .Where(m => m.GetAnnotation(ANNOTATION) != null && !planned.Contains(m.GetAnnotation(ANNOTATION)))
        .ToList();
    foreach (var m in orphans)
    {
        removed.Add(m.Name);
        if (!dryRun) m.Delete();
    }
}

// ---- paramètres de champ --------------------------------------------------
// Toutes les tables de fpTables reçoivent la MÊME expression — des copies
// identiques pour pouvoir poser des sélections indépendantes dans les visuels.
var fpStatuses = new List<string>();
if (fpEnabled)
{
    // construit l'expression d'un paramètre : une rangée par mesure exposée.
    // kpiBaseDisplay = true : la rangée de base (Calcul == baseLabel) affiche
    // le libellé du KPI via LOOKUPVALUE, au lieu du texte baseLabel.
    Func<List<object[]>, bool, string> buildFpExpr = delegate(List<object[]> rows, bool kpiBaseDisplay)
    {
        var fpLines = new List<string>();
        foreach (var r in rows)
        {
            string disp;
            if (kpiBaseDisplay && (string)r[4] == fpBaseLbl)
                disp = "LOOKUPVALUE(" + lkpLblRef + ", " + lkpKeyRef + ", \"" + daxStr((string)r[3]) + "\")";
            else
                disp = "\"" + daxStr((string)r[0]) + "\"";
            fpLines.Add("    (" + disp + ", NAMEOF(" + (string)r[1] + "), "
                + r[2] + ", \"" + daxStr((string)r[3]) + "\", \"" + daxStr((string)r[4]) + "\", \"" + daxStr((string)r[5]) + "\")");
        }
        return "{\n" + string.Join(",\n", fpLines) + "\n}";
    };

    // version « par KPI » : mêmes rangées, mais affichage = nom du KPI et
    // tri = index du KPI (même contrainte SortByColumn : un libellé -> un
    // seul index, donc l'index de calcul ne peut pas servir ici)
    var kpiOrder = new Dictionary<string, int>();
    foreach (var bm in baseMeasures) kpiOrder[bm.Name] = kpiOrder.Count;
    var fpRowsKpi = new List<object[]>();
    foreach (var r in fpRows)
        fpRowsKpi.Add(new object[] { r[3], r[1], kpiOrder[(string)r[3]], r[3], r[4], r[5] });

    // ORDRE UNIQUE KPI-puis-calcul appliqué à fpRows -> donc à parCalcul,
    // parCalcul_2 ET baseKPI. Chaque ligne reçoit un rang unique trié par
    // (ordre KPI, puis position d'origine = base, calculs, branches). La vue
    // mono-KPI reste IDENTIQUE (les rangs d'un KPI sont contigus et dans
    // l'ordre des calculs) ; la vue multi-KPI groupe désormais par KPI.
    // Possible car la colonne d'affichage est groupée par Fields (unique) dans
    // un paramètre de champ : des libellés répétés -> index uniques OK.
    var kpiCalcIdx = new List<int>();
    for (int i = 0; i < fpRows.Count; i++) kpiCalcIdx.Add(i);
    kpiCalcIdx.Sort((a, b) =>
    {
        var ka = kpiOrder[(string)fpRows[a][3]];
        var kb = kpiOrder[(string)fpRows[b][3]];
        if (ka != kb) return ka.CompareTo(kb);
        return a.CompareTo(b); // départage par position d'origine (stable)
    });
    for (int i = 0; i < kpiCalcIdx.Count; i++) fpRows[kpiCalcIdx[i]][2] = i;

    // (table, expression) à générer. parCalcul/parCalcul_2/baseKPI utilisent
    // fpRows (ordre KPI-puis-calcul) ; parKPI utilise fpRowsKpi (ordre KPI).
    var fpTargets = new List<object[]>();
    var exprCalc    = buildFpExpr(fpRows, false);
    var exprKpi     = buildFpExpr(fpRowsKpi, false);
    var exprKpiBase = buildFpExpr(fpRows, true);
    foreach (var n in fpTables)        fpTargets.Add(new object[] { n, exprCalc });
    foreach (var n in fpTablesKpi)     fpTargets.Add(new object[] { n, exprKpi });
    foreach (var n in fpTablesKpiBase) fpTargets.Add(new object[] { n, exprKpiBase });

    foreach (var tgt in fpTargets)
    {
        var fpTable = (string)tgt[0];
        var fpExpr  = (string)tgt[1];

        // colonnes techniques dérivées du nom de la table
        var fpDispCol  = fpTable;
        var fpFieldCol = fpTable + " Fields";
        var fpOrderCol = fpTable + " Ordre";

        if (Model.Tables.Contains(fpTable))
        {
            var t = Model.Tables[fpTable] as CalculatedTable;
            if (t == null)
            {
                Warning("La table '" + fpTable + "' existe mais n'est pas une table calculée — paramètre de champ non mis à jour.");
                continue;
            }
            if (!dryRun)
            {
                t.Expression = fpExpr;
                // si l'expression vient de gagner des colonnes (paramètre créé
                // via l'interface), Desktop crée des colonnes « ValueN » au
                // prochain traitement : on les renomme ici au passage.
                foreach (var c in t.Columns)
                {
                    if (c.Name == "Value4") c.Name = fpKpiCol;
                    if (c.Name == "Value5") c.Name = fpCalcCol;
                    if (c.Name == "Value6") c.Name = fpBranchCol;
                }
            }
            fpStatuses.Add(fpTable + " — expression mise à jour (" + fpRows.Count + " rangées)");
        }
        else if (dryRun)
        {
            fpStatuses.Add(fpTable + " — serait créée (" + fpRows.Count + " rangées)");
        }
        else
        {
            // création complète, avec la structure exacte d'un paramètre de champ
            var t = Model.AddCalculatedTable(fpTable, fpExpr);
            var cDisp  = t.AddCalculatedTableColumn(fpDispCol,  "[Value1]");
            var cField = t.AddCalculatedTableColumn(fpFieldCol, "[Value2]");
            var cOrder = t.AddCalculatedTableColumn(fpOrderCol, "[Value3]");
            var cKpi   = t.AddCalculatedTableColumn(fpKpiCol,   "[Value4]");
            var cCalc  = t.AddCalculatedTableColumn(fpCalcCol,  "[Value5]");
            var cBranch = t.AddCalculatedTableColumn(fpBranchCol, "[Value6]");

            cDisp.SortByColumn = cOrder;
            cField.IsHidden = true;
            cOrder.IsHidden = true;
            cDisp.SummarizeBy   = AggregateFunction.None;
            cField.SummarizeBy  = AggregateFunction.None;
            cOrder.SummarizeBy  = AggregateFunction.None;
            cKpi.SummarizeBy    = AggregateFunction.None;
            cCalc.SummarizeBy   = AggregateFunction.None;
            cBranch.SummarizeBy = AggregateFunction.None;

            try
            {
                var tomField = tomColumn(cField);
                var tomDisp  = tomColumn(cDisp);

                // propriété étendue qui fait que Power BI traite la table
                // comme un paramètre de champ
                tomField.ExtendedProperties.Add(new Microsoft.AnalysisServices.Tabular.JsonExtendedProperty
                {
                    Name = "ParameterMetadata",
                    Value = "{\"version\":3,\"kind\":2}"
                });

                // lie la colonne d'affichage à la colonne de champs (structure
                // standard générée par Desktop)
                var gb = new Microsoft.AnalysisServices.Tabular.GroupByColumn();
                gb.GroupingColumn = tomField;
                var rcd = new Microsoft.AnalysisServices.Tabular.RelatedColumnDetails();
                rcd.GroupByColumns.Add(gb);
                tomDisp.RelatedColumnDetails = rcd;

                fpStatuses.Add(fpTable + " — créée (" + fpRows.Count + " rangées) — penser à créer la relation vers TD_Indicateurs["
                    + fpKpiCol + "] dans Tabular Editor");
            }
            catch (Exception ex)
            {
                Warning("Table '" + fpTable + "' créée, mais impossible d'appliquer les métadonnées de paramètre de champ ("
                    + ex.Message + "). Solution : supprimer la table, créer le paramètre une fois via l'interface de Desktop"
                    + " (Modélisation > Nouveau paramètre > Champs), puis relancer le script.");
                fpStatuses.Add(fpTable + " — créée, mais métadonnées de paramètre incomplètes (voir avertissement)");
            }
        }
    }
}

// ---- résumé : grille triable plutôt qu'un mur de texte -------------------
var dt = new System.Data.DataTable();
dt.Columns.Add("Action", typeof(string));
dt.Columns.Add("Objet", typeof(string));

if (dryRun) dt.Rows.Add("ESSAI À BLANC", "aucune modification appliquée");
dt.Rows.Add("Résumé", baseMeasures.Count + " mesure(s) de base — " + created.Count + " créée(s), "
    + updated.Count + " mise(s) à jour, " + skipped.Count + " ignorée(s), "
    + removed.Count + " orpheline(s) supprimée(s)");
foreach (var s in fpStatuses) dt.Rows.Add("Paramètre de champ", s);
foreach (var m in baseMeasures) dt.Rows.Add("Mesure de base", m.Name);
foreach (var n in created) dt.Rows.Add("Créée", n);
foreach (var n in updated) dt.Rows.Add("Mise à jour", n);
foreach (var n in skipped) dt.Rows.Add("Ignorée (overwriteExisting=false)", n);
foreach (var n in removed) dt.Rows.Add("Orpheline supprimée", n);

dt.Output();
