"""Card registry: display names, widget attributes, config keys, ordering.

MainWindow used to own this as a module-level ``_CARD_DEFS`` plus a
``_card_attr()`` lookup, and the settings menu derived the config key by
string-munging the display name (``show_now_playing``). Both lived far from
each other, so a rename could silently write a key nothing reads. There is now
exactly one table, and every lookup goes through it.
"""
from __future__ import annotations

from typing import Any

# (display name, MainWindow attribute, config key)
CARD_DEFS: list[tuple[str, str, str]] = [
    ("CPU", "_cpu", "show_cpu"),
    ("GPU", "_gpu", "show_gpu"),
    ("Memory", "_ram", "show_memory"),
    ("Network", "_net", "show_network"),
    ("Now Playing", "_media", "show_now_playing"),
]

_BY_NAME: dict[str, tuple[str, str]] = {name: (attr, key) for name, attr, key in CARD_DEFS}


def card_attr(name: str) -> str:
    """Attribute name holding the widget for a display name, or ""."""
    entry = _BY_NAME.get(name)
    return entry[0] if entry else ""


def card_config_key(name: str) -> str:
    """Config key controlling a card's visibility, or ""."""
    entry = _BY_NAME.get(name)
    return entry[1] if entry else ""


def default_order() -> list[str]:
    return [name for name, _, _ in CARD_DEFS]


def resolve_order(config: dict[str, Any], extra: list[str] | None = None) -> list[str]:
    """Return the saved card order, falling back to the default.

    Saved orders can go stale: a disk label that is no longer present, or a
    name that no longer exists as a card. Stale entries are dropped and
    missing cards are appended in default order, so a hand-edited or
    out-of-date config can never hide a card or produce duplicates.
    """
    known = default_order()
    if extra:
        known = known + [label for label in extra if label not in known]
    known_set = set(known)

    saved = config.get("ui", {}).get("card_order") or []
    order: list[str] = []
    for name in saved:
        if name in known_set and name not in order:
            order.append(name)
    for name in known:
        if name not in order:
            order.append(name)
    return order
