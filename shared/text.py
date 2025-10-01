from __future__ import annotations

from typing import Any

__all__ = ["only_digits"]


def only_digits(value: Any) -> str:
    """Return the digits extracted from ``value`` as a contiguous string."""

    return "".join(character for character in str(value or "") if character.isdigit())
