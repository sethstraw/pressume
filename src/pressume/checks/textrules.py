"""Shared character and punctuation rules used by several check modules."""

from __future__ import annotations

import unicodedata

# One source of truth for month-name alternations: three date-regex families
# are built from these, and a month present in one list but not another is
# exactly how a date slips past the mixed-style check.
LONG_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
# Sept is not a real abbreviation either; people write it anyway. It must
# precede Sep so the alternation prefers the longer match.
SHORT_MONTH_NAMES = "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"

# Written as escapes so this file itself stays pure ASCII.
SMART_PUNCTUATION = {
    "\u2013": "en dash",
    "\u2014": "em dash",
    "\u2018": "left smart apostrophe",
    "\u2019": "right smart apostrophe",
    "\u201c": "left smart quote",
    "\u201d": "right smart quote",
}


def describe_character(character: str) -> str:
    """Human-readable description of a character, e.g. `U+2014 (em dash)`."""
    if character in SMART_PUNCTUATION:
        name = SMART_PUNCTUATION[character]
    else:
        name = unicodedata.name(character, "unknown character").lower()
    return f"U+{ord(character):04X} ({name})"


def unexpected_non_ascii(text: str, allowed: set[str]) -> list[str]:
    """Characters above ASCII that are not explicitly allowed."""
    return sorted({c for c in text if ord(c) > 127 and c not in allowed})


def smart_punctuation_found(text: str) -> list[str]:
    """Return the distinct smart-punctuation characters in ``text``."""
    return sorted({c for c in text if c in SMART_PUNCTUATION})
