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


def is_authorized_login(row: Any) -> bool:
    """Return ``True`` when the login result indicates a valid user."""

    return any(value not in (None, "", False) for value in _iter_login_values(row))


__all__ = ["is_authorized_login"]
