from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from shared.auth import is_authorized_login
from shared.config import DatabaseSettings, get_database_settings

_pool: Optional[AsyncConnectionPool] = None
_pool_lock = asyncio.Lock()


async def init_pool(settings: Optional[DatabaseSettings] = None) -> AsyncConnectionPool:
    """Initialise (or return) the global connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        settings = settings or get_database_settings()
        _pool = AsyncConnectionPool(
            conninfo=settings.dsn,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            timeout=settings.timeout,
        )
        return _pool


async def close_pool() -> None:
    """Close the existing pool, if any."""
    global _pool
    if _pool is None:
        return

    async with _pool_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Yield a database connection from the pool."""
    pool = await init_pool()
    async with pool.connection() as connection:
        yield connection


async def bind_session(connection: AsyncConnection, matricula: str) -> None:
    """Inicializa a sessão com o usuário informado.

    A função ``app.login_matricula`` configura o tenant, usuário e perfil
    correntes para a conexão. Ela deve ser invocada sempre que uma nova conexão
    é obtida do pool antes de executar qualquer ``SELECT`` ou ``INSERT``.
    """

    matricula = (matricula or "").strip()
    if not matricula:
        raise ValueError("A matrícula do usuário é obrigatória para vincular a sessão.")

    cursor = await connection.execute(
        "SELECT app.login_matricula(%s::citext)",
        (matricula,),
    )

    row = await cursor.fetchone() if cursor is not None else None
    if not is_authorized_login(row):
        raise PermissionError("Usuário não autorizado.")

    await connection.execute("SET TIME ZONE 'America/Sao_Paulo'")


async def ping() -> None:
    """Verify that the database connection is reachable."""
    async with get_connection() as connection:
        await connection.execute("SELECT 1")


__all__ = ["init_pool", "close_pool", "get_connection", "bind_session", "ping"]
