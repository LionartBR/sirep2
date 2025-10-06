from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Iterable

from psycopg import AsyncConnection
from psycopg.rows import dict_row


class PlanBlockRepository:
    """Persistência para bloqueio e desbloqueio de planos."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def block_many(
        self,
        plano_ids: Sequence[str],
        *,
        motivo: str | None = None,
        expires_at: datetime | None = None,
    ) -> int:
        if not plano_ids:
            return 0

        params = {
            "plan_ids": list(plano_ids),
            "motivo": motivo,
            "expires_at": expires_at,
        }

        sql = """
            SELECT app.plano_bloquear(pid, %(motivo)s, %(expires_at)s) AS bloqueado
              FROM UNNEST(%(plan_ids)s::uuid[]) AS pid
        """

        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()

        return _count_truthy(rows, key="bloqueado")

    async def unblock_many(self, plano_ids: Sequence[str]) -> int:
        if not plano_ids:
            return 0

        params = {"plan_ids": list(plano_ids)}
        sql = """
            SELECT app.plano_desbloquear(pid) AS desbloqueado
              FROM UNNEST(%(plan_ids)s::uuid[]) AS pid
        """

        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()

        return _count_truthy(rows, key="desbloqueado")


def _count_truthy(rows: Iterable[dict[str, object]], *, key: str) -> int:
    total = 0
    for row in rows:
        value = row.get(key)
        if bool(value):
            total += 1
    return total


__all__ = ["PlanBlockRepository"]
