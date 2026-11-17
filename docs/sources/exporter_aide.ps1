# Exporte les schémas du guide en images pour l'aide intégrée à l'app
# (bidouille\aide\*.png, lus par bidouille\tabs\dialog_guide.py).
#
#     powershell -ExecutionPolicy Bypass -File docs\sources\exporter_aide.ps1
#
# À relancer après chaque changement de build_deck.py touchant ces diapos.
# Les diapos sont retrouvées par leur TITRE, pas par leur numéro : en ajouter
# une au guide ne décale rien ici. Il faut PowerPoint (rendu fidèle aux
# polices du guide).

$ErrorActionPreference = "Stop"
$ici = Split-Path -Parent $MyInvocation.MyCommand.Path
$outil = (Resolve-Path (Join-Path $ici "..\..")).Path
$deck = Join-Path $outil "docs\PBIdouille - Guide de demarrage rapide.pptx"
$sortie = Join-Path $outil "bidouille\aide"
New-Item -ItemType Directory -Force -Path $sortie | Out-Null

# fichier -> titre de la diapo (même table que PAGES dans dialog_guide.py)
$pages = [ordered]@{
    "variations.png"       = "Comment les variations se ramifient"
    "parametres_champ.png" = "Ce que reçoivent les paramètres de champ"
    "jetons.png"           = "Les jetons à connaître"
    "propagation.png"      = "Comment le formatage se propage"
    "propagation_carte.png" = "La carte se propage aussi"
    "gabarits.png"         = "Qui copie qui : gabarits et groupes"
    "regles.png"           = "Qui l'emporte, variation par variation"
}

$pp = New-Object -ComObject PowerPoint.Application
try {
    $pres = $pp.Presentations.Open($deck, $true, $false, $false)
    foreach ($f in $pages.Keys) {
        $titre = $pages[$f]
        $trouvee = $null
        foreach ($s in $pres.Slides) {
            foreach ($sh in $s.Shapes) {
                if ($sh.HasTextFrame -and $sh.TextFrame.HasText -and
                    $sh.TextFrame.TextRange.Text.Trim() -eq $titre) { $trouvee = $s; break }
            }
            if ($trouvee) { break }
        }
        if (-not $trouvee) { throw "diapo introuvable : $titre" }
        $trouvee.Export((Join-Path $sortie $f), "PNG", 1600, 900)
        "  $f  <-  diapo $($trouvee.SlideIndex) : $titre"
    }
    $pres.Close()
} finally {
    $pp.Quit()
}
