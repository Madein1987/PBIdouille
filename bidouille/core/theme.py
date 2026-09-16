# -*- coding: utf-8 -*-
"""Thème partagé des outils — palette « Dark Teal Pro », le thème néon des
rapports Power BI (Fitbit ...Report\\StaticResources\\RegisteredResources\\
Dark_Teal_Pro*.json) : vert néon sur fonds bleu nuit.

Le QSS est AUTONOME (aucune dépendance qdarkstyle) → rendu identique à la
maison (PySide6/Qt6) et au travail (PyQt5/Qt5). ChopChopRapport importe ce
module ; BIdouille aussi. Icône émoji et identité Windows incluses."""

from __future__ import annotations

import tempfile
from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

# ---- palette Dark Teal Pro (mêmes hex que le thème Power BI) ---------------
BG_WINDOW   = "#0F1629"   # fond de fenêtre (= fond de page du rapport)
BG_DARKEST  = "#090D1A"   # wallpaper (zones creuses : éditeurs, journaux)
SURFACE     = "#162032"   # surfaces : groupbox, champs, cartes
SURFACE_ALT = "#1A2640"   # lignes alternées / éléments discrets
BORDER      = "#1E2D3D"   # bordures, survols, entêtes
ACCENT      = "#56C596"   # vert néon — couleur principale
ACCENT_DIM  = "#3D8F6D"   # vert atténué (pressed / bordures actives)
TEXT        = "#E2E8F0"   # texte principal
TEXT_DIM    = "#C8D4E0"   # texte secondaire
TEXT_MUTED  = "#7F898A"   # texte désactivé / grisé
RED         = "#E8604E"   # sémantique « bad »
YELLOW      = "#D4AE28"   # sémantique « neutral »
BLUE        = "#38BDF8"   # sémantique secondaire
GREEN       = ACCENT      # sémantique « good » = l'accent

# rétro-compatibilité (ancien accent rose de ChopChopRapport)
HOT_PINK = ACCENT


def emoji_icon(emoji: str) -> QIcon:
    """Icône d'app à partir d'un émoji (Segoe UI Emoji, couleur native
    Windows) — aucun fichier .ico à trimballer."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        f = QFont("Segoe UI Emoji")
        f.setPixelSize(int(size * 0.82))
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
        p.end()
        icon.addPixmap(pm)
    return icon


def _write_indicator_icons() -> tuple:
    """Peint la coche et le tiret VERT NÉON en PNG dans le dossier temp et
    retourne leurs chemins (les stylesheets Qt exigent des fichiers). PNG
    plutôt que SVG : PyQt5 (poste du travail) n'a pas toujours le plugin SVG
    et l'échec serait silencieux."""
    d = Path(tempfile.gettempdir())
    check_path = d / "bidouille_check.png"
    dash_path = d / "bidouille_dash.png"

    pen = QPen(QColor(ACCENT))
    pen.setWidthF(2.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)

    for path, kind in ((check_path, "check"), (dash_path, "dash")):
        pm = QPixmap(15, 15)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(pen)
        if kind == "check":
            p.drawLine(3, 8, 6, 11)
            p.drawLine(6, 11, 12, 4)
        else:
            p.drawLine(4, 7, 11, 7)
        p.end()
        pm.save(str(path), "PNG")

    return check_path.as_posix(), dash_path.as_posix()


def _indicator_qss(scopes: str) -> str:
    """Règles d'indicateur (case à cocher) pour les sélecteurs donnés :
    carré sombre, bord vert au survol, coche/tiret verts. `scopes` est une
    liste de sélecteurs « X::indicator » séparés par des virgules."""
    check, dash = _write_indicator_icons()

    def variant(state: str) -> str:
        return ", ".join(s.strip() + state for s in scopes.split(","))

    return f"""
{scopes} {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {SURFACE_ALT};
}}
{variant(":hover")} {{ border-color: {ACCENT}; }}
{variant(":checked")} {{
    image: url("{check}");
    border-color: {ACCENT};
}}
{variant(":indeterminate")} {{
    image: url("{dash}");
    border-color: {ACCENT};
}}
"""


def checkable_list_stylesheet() -> str:
    """Style des cases à cocher pour QListWidget/QTreeWidget (utile seul si le
    QSS global n'est pas appliqué ; sinon redondant et inoffensif)."""
    return ("QListWidget::item, QTreeWidget::item { padding: 1px 2px; }"
            + _indicator_qss("QListWidget::indicator, QTreeWidget::indicator"))


def neon_stylesheet() -> str:
    """QSS complet de l'app : Dark Teal Pro — fonds bleu nuit, accent vert."""
    return f"""
/* ---- base -------------------------------------------------------------- */
QWidget {{
    background: {BG_WINDOW};
    color: {TEXT};
    font-family: "Segoe UI";
    font-size: 9pt;
}}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QToolTip {{
    background: {BORDER};
    color: {TEXT};
    border: 1px solid {ACCENT_DIM};
    padding: 3px 6px;
}}

/* ---- groupes ------------------------------------------------------------ */
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 9px;
    padding: 8px 6px 6px 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {ACCENT};
    background: transparent;
}}

/* ---- boutons ------------------------------------------------------------ */
QPushButton {{
    background: {SURFACE_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; color: {ACCENT}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; border-color: {SURFACE_ALT}; }}
QPushButton:default {{ border-color: {ACCENT_DIM}; }}

/* ---- champs ------------------------------------------------------------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 3px 6px;
    selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {TEXT_MUTED}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
    margin-right: 5px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT};
    outline: none;
}}

/* ---- éditeurs / journaux -------------------------------------------------*/
QPlainTextEdit, QTextEdit {{
    background: {BG_DARKEST};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT};
}}

/* ---- listes / arbres / tables -------------------------------------------*/
QListWidget, QTreeWidget, QTreeView, QTableView, QListView {{
    background: {SURFACE};
    alternate-background-color: {SURFACE_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{ padding: 1px 2px; }}
QListWidget::item:selected, QTreeWidget::item:selected,
QTreeView::item:selected, QListView::item:selected {{
    background: {ACCENT_DIM};
    color: {TEXT};
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {SURFACE_ALT}; }}
QHeaderView::section {{
    background: {BORDER};
    color: {ACCENT};
    border: none;
    border-right: 1px solid {SURFACE};
    padding: 4px 6px;
}}

/* ---- onglets ------------------------------------------------------------ */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: {SURFACE_ALT};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 5px 16px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {ACCENT};
    border-color: {ACCENT_DIM};
}}
QTabBar::tab:hover:!selected {{ color: {ACCENT}; }}

/* ---- cases à cocher ------------------------------------------------------*/
{_indicator_qss("QCheckBox::indicator, QListWidget::indicator, QTreeWidget::indicator")}

/* ---- barres de défilement ------------------------------------------------*/
QScrollBar:vertical {{
    background: {BG_WINDOW}; width: 11px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar:horizontal {{
    background: {BG_WINDOW}; height: 11px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER}; border-radius: 5px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---- divers --------------------------------------------------------------*/
QSplitter::handle {{ background: {BORDER}; }}
QStatusBar {{ background: {SURFACE}; color: {TEXT_DIM}; }}
QMenu {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER};
}}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
QMessageBox {{ background: {SURFACE}; }}
"""


def apply_app_theme(app, emoji: str, app_id: str) -> None:
    """Applique le thème néon et l'identité Windows sur le QApplication (une
    fois). Le QSS étant autonome, le rendu est le même avec PyQt5 (travail)
    et PySide6 (maison). Pose aussi l'icône de fenêtre."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
    app.setStyleSheet(neon_stylesheet())
    app.setWindowIcon(emoji_icon(emoji))
