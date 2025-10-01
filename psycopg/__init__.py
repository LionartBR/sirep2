"""Lightweight psycopg stub used for tests.

This module provides minimal classes and exceptions so that the rest of the
codebase can be imported without the optional ``psycopg`` dependency.  The real
project installs ``psycopg`` in production, but for unit tests we only need the
interfaces to exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import errors as errors
from .errors import (  # re-export for compatibility
    InvalidAuthorizationSpecification,
    UniqueViolation,
)


@dataclass
class Connection:  # pragma: no cover - simple data container
    """Very small stand-in for :class:`psycopg.Connection`.

    The object only records the statements executed.  Tests patch the
    connection methods with fakes, but having a usable default helps when the
    stub is used outside of tests.
    """

    executed_statements: list[tuple[str, tuple[Any, ...] | None]] = field(
        default_factory=list
    )

    def cursor(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - guard
        raise RuntimeError("psycopg stub connections do not provide cursors")

    def commit(self) -> None:  # pragma: no cover - guard
        return None

    def rollback(self) -> None:  # pragma: no cover - guard
        return None

    def close(self) -> None:  # pragma: no cover - guard
        return None


class AsyncConnection:  # pragma: no cover - thin façade
    """Minimal asynchronous connection stub used by ``infra.db``."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> None:
        self.executed.append((sql, tuple(params) if params is not None else None))

    def cursor(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - guard
        raise RuntimeError("psycopg async stub does not provide cursors")


def connect(*_args: Any, **_kwargs: Any) -> Connection:
    """Return a stubbed connection object."""

    return Connection()


__all__ = [
    "AsyncConnection",
    "Connection",
    "InvalidAuthorizationSpecification",
    "UniqueViolation",
    "connect",
    "errors",
]
