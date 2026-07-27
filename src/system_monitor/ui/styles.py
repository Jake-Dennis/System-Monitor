"""QSS theme + small color utilities for the dark Rainmeter-style look."""

import math

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

ACCENT = "#00D4FF"
WARN = "#FFB454"
HOT = "#FF6B35"
CRIT = "#FF3838"
BG_WINDOW = "#000000"
BG_CARD = "#0E0E0E"
BG_CARD_HOVER = "#1A1A1A"
BORDER = "#1F1F1F"
TEXT_PRIMARY = "#E6ECF5"
TEXT_MUTED = "#8A95AD"
TEXT_DIM = "#5C6678"


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


def qss(scale: float = 1.0) -> str:
    """Generate the QSS stylesheet with fonts/scaled by `scale`."""
    S = lambda name: _sz(name, scale)  # noqa: E731
    h_bar = S("ProgressBarH")
    return f"""
* {{ font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif; }}

QMainWindow, #PanelRoot {{
    background-color: {BG_WINDOW};
    border: 1px solid {BORDER};
    border-radius: {_sz("CardTitle", scale)};
}}

QLabel#HeaderTitle {{
    color: {TEXT_PRIMARY};
    font-size: {S("HeaderTitle")};
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel#HeaderSub {{
    color: {TEXT_MUTED};
    font-size: {S("HeaderSub")};
}}
QLabel#CardTitle {{
    color: {TEXT_MUTED};
    font-size: {S("CardTitle")};
    font-weight: 600;
    letter-spacing: 1.0px;
    text-transform: uppercase;
}}
QLabel#Value {{
    color: {TEXT_PRIMARY};
    font-size: {S("Value")};
    font-weight: 300;
    letter-spacing: -0.5px;
}}
QLabel#ValueSmall {{
    color: {TEXT_PRIMARY};
    font-size: {S("ValueSmall")};
    font-weight: 300;
}}
QLabel#Secondary {{
    color: {TEXT_MUTED};
    font-size: {S("Secondary")};
}}
QLabel#Caption {{
    color: {TEXT_DIM};
    font-size: {S("Caption")};
}}

QWidget#Card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QWidget#Card[hovered="true"] {{
    background-color: {BG_CARD_HOVER};
    border: 1px solid {ACCENT};
}}

QPushButton#IconButton {{
    background: transparent;
    border: none;
    color: {TEXT_MUTED};
    font-size: {S("IconButton")};
    padding: {_sz("Caption", scale)} {_sz("Secondary", scale)};
    border-radius: {_sz("Caption", scale)};
}}
QPushButton#IconButton:hover {{ color: {TEXT_PRIMARY}; background: {BG_CARD_HOVER}; }}

QProgressBar {{
    background: rgba(0, 0, 0, 80);
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
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QMenu {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {_sz("Caption", scale)};
    padding: 4px;
}}
QMenu::item {{ padding: {_sz("Caption", scale)} {_sz("Secondary", scale)}; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG_CARD_HOVER}; }}
"""
