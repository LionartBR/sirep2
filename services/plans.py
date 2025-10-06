from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from domain.plan_block import PlanBlockResult, PlanUnblockResult
from infra.repositories.plan_block import PlanBlockRepository


class PlanBlockingService:
    """Orquestra operações de bloqueio e desbloqueio de planos."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._repository = PlanBlockRepository(connection)

    async def block_plans(
        self,
        *,
        plano_ids: Sequence[str | UUID],
        motivo: str | None = None,
        expires_at: datetime | None = None,
    ) -> PlanBlockResult:
        normalized_ids = self._normalize_ids(plano_ids)
        if not normalized_ids:
            return PlanBlockResult(blocked_count=0)

        cleaned_reason = self._clean_reason(motivo)

        await self._begin()
        try:
            blocked = await self._repository.block_many(
                normalized_ids,
                motivo=cleaned_reason,
                expires_at=expires_at,
            )
            await self._commit()
            return PlanBlockResult(blocked_count=blocked)
        except UniqueViolation:
            await self._rollback()
            return PlanBlockResult(blocked_count=0)
        except Exception:
            await self._rollback()
            raise

    async def unblock_plans(self, *, plano_ids: Sequence[str | UUID]) -> PlanUnblockResult:
        normalized_ids = self._normalize_ids(plano_ids)
        if not normalized_ids:
            return PlanUnblockResult(unblocked_count=0)

        await self._begin()
        try:
            unblocked = await self._repository.unblock_many(normalized_ids)
            await self._commit()
            return PlanUnblockResult(unblocked_count=unblocked)
        except Exception:
            await self._rollback()
            raise

    async def _begin(self) -> None:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute("BEGIN")
            await cur.execute("SET LOCAL statement_timeout = '5s'")

    async def _commit(self) -> None:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute("COMMIT")

    async def _rollback(self) -> None:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute("ROLLBACK")

    @staticmethod
    def _normalize_ids(plano_ids: Sequence[str | UUID]) -> tuple[str, ...]:
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in plano_ids:
            if raw is None:
                continue
            value = str(raw).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return tuple(normalized)

    @staticmethod
    def _clean_reason(reason: str | None) -> str | None:
        if reason is None:
            return None
        cleaned = reason.strip()
        return cleaned or None


__all__ = ["PlanBlockingService"]
