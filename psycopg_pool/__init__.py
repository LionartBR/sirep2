"""Minimal psycopg_pool stub used in tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from psycopg import AsyncConnection


class AsyncConnectionPool:  # pragma: no cover - simple utility
    """Very small stand-in for :class:`psycopg_pool.AsyncConnectionPool`."""

    def __init__(
        self,
        *,
        conninfo: str,
        min_size: int = 1,
        max_size: int = 10,
        timeout: Optional[float] = None,
        open: bool = True,
    ) -> None:
        self.conninfo = conninfo
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout
        self._open = open

    async def open(self) -> None:
        self._open = True

    async def close(self) -> None:
        self._open = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        if not self._open:
            raise RuntimeError("Connection pool is closed")
        yield AsyncConnection()


__all__ = ["AsyncConnectionPool"]
