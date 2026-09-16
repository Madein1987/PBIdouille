// =====================================================================
// Création de mesures SVG autonomes — script Tabular Editor 2 / 3
// ---------------------------------------------------------------------
// Assemble des mesures SVG (sparklines, aires, etc.) à partir de :
//   - svg_measures_config.json : quelles mesures créer (nom, table,
//     recette, séries, colonnes de date, réglages) ;
//   - svg_recipes/<recette>.dax : le gabarit DAX de chaque recette,
//     avec des placeholders <<...>>.
//
// POURQUOI ce script : les mesures SVG font 100+ lignes de DAX. Plutôt
// que de les écrire à la main, on remplit un petit JSON et le script
// injecte les valeurs dans le gabarit. Les mesures générées sont
// AUTONOMES (aucune UDF) — donc elles se sauvegardent au travail, où
// Tabular Editor ne supporte pas les fonctions.
//
// Utilisation : Tabular Editor (via Outils externes) -> onglet C#
// Script -> exécuter -> Ctrl+S. Relancer est sans danger (les mesures
// existantes sont mises à jour, pas dupliquées).
//
// Placeholders : <<...>> (PAS {..}, réservé aux constructeurs DAX { }).
//   Réglages : <<W>> <<H>> <<Pad>> <<YPad>> <<Above>> <<Below>>
//              <<FillOp>> <<MA1W>> <<MA1Op>> <<MA2C>> <<MA2W>> <<MA2Dash>>
//   Séries/axe : <<ma1>> <<ma2>> <<binColumn>> <<anchorColumn>>
// Un réglage absent du JSON prend le défaut ci-dessous (defaults).
// =====================================================================

var configPath = @"C:\OneDrive - PJ\Data Cooler\_Power BI\Fitbit\svg_measures_config.json";

if (!System.IO.File.Exists(configPath))
{
    var dlg = new System.Windows.Forms.OpenFileDialog();
    dlg.Title = "Choisir svg_measures_config.json";
    dlg.Filter = "Fichiers JSON (*.json)|*.json|Tous les fichiers (*.*)|*.*";
    if (dlg.ShowDialog() != System.Windows.Forms.DialogResult.OK)
    {
        Info("Annulé — aucun fichier de config choisi.");
        return;
    }
    configPath = dlg.FileName;
}

var configDir = System.IO.Path.GetDirectoryName(configPath);
var config = Newtonsoft.Json.Linq.JObject.Parse(System.IO.File.ReadAllText(configPath));

// ---- paramètres ------------------------------------------------------
var settings = config["settings"] as Newtonsoft.Json.Linq.JObject;
if (settings == null) settings = new Newtonsoft.Json.Linq.JObject();

var recipesFolder = settings["recipesFolder"] != null ? (string)settings["recipesFolder"] : "svg_recipes";
var overwrite     = settings["overwriteExisting"] != null ? (bool)settings["overwriteExisting"] : true;
var dataCategory  = settings["dataCategory"] != null ? (string)settings["dataCategory"] : "ImageUrl";

// ---- défauts des réglages (utilisés si absents du JSON) --------------
var defaults = new Dictionary<string, string>();
defaults["W"] = "300";  defaults["H"] = "100";  defaults["Pad"] = "5";  defaults["YPad"] = "0.05";
defaults["Above"] = "#2E7D32";  defaults["Below"] = "#C62828";  defaults["FillOp"] = "0.25";
defaults["MA1W"] = "4";  defaults["MA1Op"] = "0.9";  defaults["MA2C"] = "#000000";  defaults["MA2W"] = "3";  defaults["MA2Dash"] = "4,4";

// JToken -> littéral (nombres en culture INVARIANTE : point décimal, pas
// virgule — sinon le DAX casse sur un poste en français).
Func<Newtonsoft.Json.Linq.JToken, string> lit = delegate(Newtonsoft.Json.Linq.JToken t)
{
    if (t == null) return "";
    if (t.Type == Newtonsoft.Json.Linq.JTokenType.Integer)
        return ((long)t).ToString(System.Globalization.CultureInfo.InvariantCulture);
    if (t.Type == Newtonsoft.Json.Linq.JTokenType.Float)
        return ((double)t).ToString(System.Globalization.CultureInfo.InvariantCulture);
    return (string)t;
};

var measArray = config["measures"] as Newtonsoft.Json.Linq.JArray;
if (measArray == null || measArray.Count == 0) { Error("La config n'a pas de tableau 'measures'."); return; }

// cache des gabarits déjà lus (une lecture disque par recette)
var templates = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

var created = new List<string>();
var updated = new List<string>();
var warnings = new List<string>();

foreach (Newtonsoft.Json.Linq.JObject m in measArray)
{
    var name  = (string)m["name"];
    var table = (string)m["table"];
    var recipe = (string)m["recipe"];
    if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(table) || string.IsNullOrEmpty(recipe))
    {
        warnings.Add("Mesure ignorée : name / table / recipe manquant.");
        continue;
    }
    if (!Model.Tables.Contains(table))
    {
        warnings.Add("Table '" + table + "' introuvable — mesure '" + name + "' ignorée.");
        continue;
    }

    // gabarit de la recette (lu une fois, mis en cache)
    string template;
    if (!templates.TryGetValue(recipe, out template))
    {
        var recipePath = System.IO.Path.Combine(configDir, recipesFolder, recipe + ".dax");
        if (!System.IO.File.Exists(recipePath))
        {
            warnings.Add("Gabarit introuvable : " + recipePath + " — mesure '" + name + "' ignorée.");
            continue;
        }
        template = System.IO.File.ReadAllText(recipePath);
        templates[recipe] = template;
    }

    var dax = template;

    // séries & colonnes d'axe
    dax = dax.Replace("<<ma1>>", (string)m["ma1"]);
    dax = dax.Replace("<<ma2>>", (string)m["ma2"]);
    dax = dax.Replace("<<binColumn>>", (string)m["binColumn"]);
    dax = dax.Replace("<<anchorColumn>>", (string)m["anchorColumn"]);

    // réglages : valeur du JSON sinon défaut
    var mSettings = m["settings"] as Newtonsoft.Json.Linq.JObject;
    foreach (var kv in defaults)
    {
        var val = (mSettings != null && mSettings[kv.Key] != null) ? lit(mSettings[kv.Key]) : kv.Value;
        dax = dax.Replace("<<" + kv.Key + ">>", val);
    }

    // filet de sécurité : un placeholder oublié = DAX cassé
    var stray = System.Text.RegularExpressions.Regex.Match(dax, "<<[^>]+>>");
    if (stray.Success)
    {
        warnings.Add("Mesure '" + name + "' : placeholder non remplacé " + stray.Value + " — mesure ignorée.");
        continue;
    }

    var displayFolder = m["displayFolder"] != null ? (string)m["displayFolder"] : null;
    var t = Model.Tables[table];

    var existing = Model.AllMeasures.FirstOrDefault(x => x.Name.Equals(name, StringComparison.OrdinalIgnoreCase));
    Measure meas;
    if (existing != null)
    {
        if (!overwrite) { warnings.Add("'" + name + "' existe déjà (overwriteExisting=false) — ignorée."); continue; }
        existing.Expression = dax;
        meas = existing;
        updated.Add(name);
    }
    else
    {
        meas = t.AddMeasure(name, dax);
        created.Add(name);
    }

    if (displayFolder != null) meas.DisplayFolder = displayFolder;

    // catégorie de données (ImageUrl) — pour que la mesure s'affiche en image.
    // Propriété absente sur certaines versions de TE -> try/catch.
    try { meas.DataCategory = dataCategory; }
    catch (Exception ex) { warnings.Add("'" + name + "' : DataCategory non appliquée (" + ex.Message + ") — à mettre à la main."); }
}

// ---- résumé ----------------------------------------------------------
var dt = new System.Data.DataTable();
dt.Columns.Add("Action", typeof(string));
dt.Columns.Add("Objet", typeof(string));
dt.Rows.Add("Résumé", created.Count + " créée(s), " + updated.Count + " mise(s) à jour, " + warnings.Count + " avertissement(s)");
foreach (var n in created) dt.Rows.Add("Créée", n);
foreach (var n in updated) dt.Rows.Add("Mise à jour", n);
foreach (var w in warnings) dt.Rows.Add("⚠ Avertissement", w);
dt.Output();
