"""Helpers related to authentication and authorisation."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any


def _iter_login_values(row: Any) -> Iterable[Any]:
    if row is None:
        return ()

    if isinstance(row, dict):
        return row.values()

    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        return row

    return (row,)


_FALSEY_STRINGS = {"", "0", "false", "f", "no", "não", "nao"}


def _is_truthy(value: Any) -> bool:
    """Return ``True`` when ``value`` should be considered an affirmative flag."""

    if value is None:
        return False

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized not in _FALSEY_STRINGS

    return True


def is_authorized_login(row: Any) -> bool:
    """Return ``True`` when the login result indicates a valid user."""

    return any(_is_truthy(value) for value in _iter_login_values(row))


__all__ = ["is_authorized_login"]
