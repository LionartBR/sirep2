"""JSON helper provided by the psycopg stub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Json:
    """Mimic the behaviour of :class:`psycopg.types.json.Json` for tests."""

    obj: Any


__all__ = ["Json"]
