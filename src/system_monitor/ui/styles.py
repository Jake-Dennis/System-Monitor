"""QSS theme engine — dark and light themes with dynamic font scaling."""
from __future__ import annotations

# -- base (unscaled) font sizes --
BASE = {
    "HeaderTitle": 14,
    "HeaderSub": 10,
    "CardTitle": 10,
    "Value": 24,
    "ValueSmall": 16,
    "Secondary": 11,
    "Caption": 10,
    "IconButton": 14,
    "ProgressBarH": 6,
    "TimelineH": 40,
}

# -- shared accent colors --
ACCENT = "#00D4FF"
WARN = "#FFB454"
HOT = "#FF6B35"
CRIT = "#FF3838"

# -- theme palettes --
_DARK = {
    "BG_WINDOW": "#000000",
    "BG_CARD": "#0E0E0E",
    "BG_CARD_HOVER": "#1A1A1A",
    "BORDER": "#1F1F1F",
    "TEXT_PRIMARY": "#E6ECF5",
    "TEXT_MUTED": "#8A95AD",
    "TEXT_DIM": "#5C6678",
}

_LIGHT = {
    "BG_WINDOW": "#F0F0F0",
    "BG_CARD": "#FFFFFF",
    "BG_CARD_HOVER": "#E8E8E8",
    "BORDER": "#D0D0D0",
    "TEXT_PRIMARY": "#1A1A1A",
    "TEXT_MUTED": "#666666",
    "TEXT_DIM": "#999999",
}


def color_for_percent(p: float, *, hot_at: float = 70.0, crit_at: float = 90.0) -> str:
    """Return a hex color for a 0-100 utilization reading."""
    if p >= crit_at:
        return CRIT
    if p >= hot_at:
        return HOT
    if p >= hot_at * 0.7:
        return WARN
    return ACCENT


def _sz(name: str, scale: float) -> str:
    return f"{max(1, round(BASE[name] * scale))}px"


def qss(scale: float = 1.0, theme: str = "dark") -> str:
    """Generate the QSS stylesheet with scaled fonts and chosen theme.

    `theme`: "dark" (default) or "light"
    """
    S = lambda name: _sz(name, scale)  # noqa: E731
    h_bar = S("ProgressBarH")

    pal = _DARK if theme == "dark" else _LIGHT
    BG_W = pal["BG_WINDOW"]
    BG_C = pal["BG_CARD"]
    BG_CH = pal["BG_CARD_HOVER"]
    BDR = pal["BORDER"]
    TXT_P = pal["TEXT_PRIMARY"]
    TXT_M = pal["TEXT_MUTED"]
    TXT_D = pal["TEXT_DIM"]
    # Progress bar background — slightly transparent version of card bg
    if theme == "dark":
        PROGRESS_BG = "rgba(0, 0, 0, 80)"
    else:
        PROGRESS_BG = "rgba(0, 0, 0, 15)"

    return f"""
* {{ font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif; }}

QMainWindow, #PanelRoot {{
    background-color: {BG_W};
    border: 1px solid {BDR};
    border-radius: {_sz("CardTitle", scale)};
}}

QLabel#HeaderTitle {{
    color: {TXT_P};
    font-size: {S("HeaderTitle")};
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel#HeaderSub {{
    color: {TXT_M};
    font-size: {S("HeaderSub")};
}}
QLabel#CardTitle {{
    color: {TXT_M};
    font-size: {S("CardTitle")};
    font-weight: 600;
    letter-spacing: 1.0px;
    text-transform: uppercase;
}}
QLabel#Value {{
    color: {TXT_P};
    font-size: {S("Value")};
    font-weight: 300;
    letter-spacing: -0.5px;
}}
QLabel#ValueSmall {{
    color: {TXT_P};
    font-size: {S("ValueSmall")};
    font-weight: 300;
}}
QLabel#Secondary {{
    color: {TXT_M};
    font-size: {S("Secondary")};
}}
QLabel#Caption {{
    color: {TXT_D};
    font-size: {S("Caption")};
}}

QWidget#Card {{
    background-color: {BG_C};
    border: 1px solid {BDR};
    border-radius: 12px;
}}
QWidget#Card[hovered="true"] {{
    background-color: {BG_CH};
    border: 1px solid {ACCENT};
}}

QPushButton#IconButton {{
    background: transparent;
    border: none;
    color: {TXT_M};
    font-size: {S("IconButton")};
    padding: {_sz("Caption", scale)} {_sz("Secondary", scale)};
    border-radius: {_sz("Caption", scale)};
}}
QPushButton#IconButton:hover {{ color: {TXT_P}; background: {BG_CH}; }}

QProgressBar {{
    background: {PROGRESS_BG};
    border: none;
    height: {h_bar};
    border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{
    border-radius: 3px;
    background: {ACCENT};
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: {_sz("Caption", scale)}; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {BDR}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QMenu {{
    background: {BG_C};
    color: {TXT_P};
    border: 1px solid {BDR};
    border-radius: {_sz("Caption", scale)};
    padding: 4px;
}}
QMenu::item {{ padding: {_sz("Caption", scale)} {_sz("Secondary", scale)}; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG_CH}; }}
"""
