"""Subset of constants from :mod:`psycopg.pq` required in tests."""

from __future__ import annotations

from enum import Enum, auto


class TransactionStatus(Enum):
    """Represent transaction states for the stub connection info."""

    IDLE = auto()
    ACTIVE = auto()
    INTRANS = auto()
    INERROR = auto()
    UNKNOWN = auto()


__all__ = ["TransactionStatus"]
