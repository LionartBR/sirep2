from __future__ import annotations

import re
from typing import Any

__all__ = ["only_digits", "normalize_document"]


def only_digits(value: Any) -> str:
    """Return only the numeric characters found in ``value``."""

    return re.sub(r"\D", "", str(value or ""))


def normalize_document(value: Any, *, allow_empty: bool = False) -> str | None:
    """Normalize document identifiers removing extra characters and whitespace.

    When ``allow_empty`` is ``True`` an empty string is returned instead of
    ``None`` when no meaningful content is found.
    """

    text = str(value or "").strip()
    digits = only_digits(value)

    if digits:
        return digits

    if text:
        return text

    if allow_empty:
        return ""

    return None

def only_digits(value: Any) -> str:
    """Return the digits extracted from ``value`` as a contiguous string."""

    return "".join(character for character in str(value or "") if character.isdigit())
