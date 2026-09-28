"""QSS theme engine — dark and light themes with dynamic font scaling."""
from __future__ import annotations

import re

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

# Runtime accent. `ACCENT` is the compiled-in default; this is the value the
# user has actually chosen (config `ui.accent`). Widgets call
# color_for_percent() without passing it, so it has to live here rather than
# be threaded through every card.
_current_accent = ACCENT

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_accent(value: object) -> str:
    """Return a valid #RGB/#RRGGBB string, or the default accent.

    `ui.accent` is user-editable, so a typo would otherwise produce an
    invalid stylesheet and (in Qt's case) a silently unstyled panel.
    """
    if isinstance(value, str) and _HEX_RE.match(value.strip()):
        return value.strip()
    return ACCENT


def set_accent(value: object) -> str:
    """Set the runtime accent color. Returns the value actually applied."""
    global _current_accent
    _current_accent = normalize_accent(value)
    return _current_accent


def current_accent() -> str:
    """The accent currently in effect."""
    return _current_accent

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


def color_for_percent(
    p: float, *, hot_at: float = 70.0, crit_at: float = 90.0, accent: str | None = None
) -> str:
    """Return a hex color for a 0-100 utilization reading.

    `accent` overrides the runtime accent for this call only; omit it to use
    the theme's current accent.
    """
    base = normalize_accent(accent) if accent is not None else _current_accent
    if p >= crit_at:
        return CRIT
    if p >= hot_at:
        return HOT
    if p >= hot_at * 0.7:
        return WARN
    return base


def _sz(name: str, scale: float) -> int:
    """Return a scaled pixel size for a named base size (see `BASE`)."""
    return max(1, round(BASE[name] * scale))


def qss(scale: float = 1.0, theme: str = "dark", accent: str | None = None) -> str:
    """Generate the QSS stylesheet with scaled fonts and chosen theme.

    `theme`: "dark" (default) or "light"
    `accent`: overrides the runtime accent for this stylesheet only.
    """
    accent_color = normalize_accent(accent) if accent is not None else _current_accent
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

    # Alert border colors (warn = orange, crit = red)
    if theme == "dark":
        ALERT_WARN = "#FFB454"
        ALERT_CRIT = "#FF3838"
    else:
        ALERT_WARN = "#CC8800"
        ALERT_CRIT = "#CC2222"

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
    border: 1px solid {accent_color};
}}
QWidget#Card[alert="warn"] {{
    border: 2px solid {ALERT_WARN};
}}
QWidget#Card[alert="crit"] {{
    border: 2px solid {ALERT_CRIT};
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
    color: {TXT_P};
}}
QProgressBar::chunk {{
    border-radius: 3px;
    background: {accent_color};
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
