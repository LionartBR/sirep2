"""Row factories provided by the psycopg stub."""

from __future__ import annotations

from typing import Any, Mapping


class _DictRowFactory:
    """Callable used as ``row_factory`` argument in tests."""

    def __call__(self, cursor: Any) -> Mapping[str, Any]:  # pragma: no cover - guard
        raise RuntimeError("dict_row factory from stub cannot be invoked directly")


# Expose a single instance matching the interface used in the codebase.
dict_row = _DictRowFactory()

__all__ = ["dict_row"]
