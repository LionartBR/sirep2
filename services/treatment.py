from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional
from uuid import UUID

from psycopg import AsyncConnection

from domain.treatment import (
    TreatmentItem,
    TreatmentMigrationResult,
    TreatmentState,
    TreatmentTotals,
)
from infra.audit import log_event_async
from infra.repositories.treatment import (
    CloseBatchOutcome,
    TreatmentRepository,
    encode_cursor,
)

_GRID_PLANOS_P_RESCISAO = "PLANOS_P_RESCISAO"
_DEFAULT_PAGE_SIZE = 10
_MAX_PAGE_SIZE = 50


class TreatmentServiceError(RuntimeError):
    """Base error for treatment operations."""


class TreatmentNotFoundError(TreatmentServiceError):
    """Raised when the requested batch or item cannot be found."""


class TreatmentConflictError(TreatmentServiceError):
    """Raised when an operation cannot proceed due to a conflicting state."""


@dataclass(slots=True)
class ItemsPage:
    """Keyset-aware page returned by the service layer."""

    items: list[TreatmentItem]
    next_cursor: Optional[str]
    prev_cursor: Optional[str]
    has_more: bool
    page_size: int


@dataclass(slots=True)
class TreatmentCloseResult:
    """Outcome returned after attempting to close a treatment batch."""

    lote_id: UUID
    pending_to_skipped: int
    closed: bool


class TreatmentService:
    """High-level orchestration for treatment batch workflows."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._repo = TreatmentRepository(connection)

    async def get_state(self, grid: str = _GRID_PLANOS_P_RESCISAO) -> TreatmentState:
        batch = await self._repo.fetch_open_batch(grid)
        if not batch:
            return TreatmentState(
                has_open=False, lote_id=None, totals=TreatmentTotals()
            )
        totals = await self._repo.fetch_totals(batch.id)
        return TreatmentState(has_open=True, lote_id=batch.id, totals=totals)

    async def migrate(
        self,
        *,
        grid: str = _GRID_PLANOS_P_RESCISAO,
        filters: Optional[Mapping[str, Any]] = None,
    ) -> TreatmentMigrationResult:
        return await self._repo.create_batch_and_snapshot(grid=grid, filters=filters)

    async def list_items(
        self,
        *,
        lote_id: UUID,
        status: str = "pending",
        page_size: int = _DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        direction: str = "next",
    ) -> ItemsPage:
        normalized_status = (status or "").strip().lower() or "pending"
        normalized_direction = "prev" if direction == "prev" else "next"
        effective_page_size = max(1, min(page_size, _MAX_PAGE_SIZE))

        items, has_more = await self._repo.list_items_keyset(
            lote_id=lote_id,
            status=normalized_status,
            page_size=effective_page_size,
            cursor=cursor,
            direction=normalized_direction,
        )

        next_cursor = None
        prev_cursor = None
        if items:
            first = items[0]
            last = items[-1]
            prev_cursor = encode_cursor(first.saldo or 0, first.numero_plano)
            next_cursor = encode_cursor(last.saldo or 0, last.numero_plano)

        return ItemsPage(
            items=items,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_more=has_more,
            page_size=effective_page_size,
        )

    async def rescind(
        self,
        *,
        lote_id: UUID,
        plano_id: UUID,
        effective_dt_iso: str,
    ) -> None:
        async with self._connection.cursor() as cur:
            await cur.execute("BEGIN")
        try:
            success = await self._repo.rescind_item_via_function(
                lote_id=lote_id,
                plano_id=plano_id,
                effective_ts=effective_dt_iso,
            )
            if not success:
                raise TreatmentNotFoundError("Item de tratamento não encontrado.")

            await log_event_async(
                self._connection,
                entity="tratamento_item",
                entity_id=str(plano_id),
                event_type="TRATAMENTO_RESCINDIR",
                severity="info",
                data={
                    "lote_id": str(lote_id),
                    "plano_id": str(plano_id),
                    "effective_dt": effective_dt_iso,
                },
            )
            async with self._connection.cursor() as cur:
                await cur.execute("COMMIT")
        except Exception:
            async with self._connection.cursor() as cur:
                await cur.execute("ROLLBACK")
            raise

    async def skip(self, *, lote_id: UUID, plano_id: UUID) -> None:
        async with self._connection.cursor() as cur:
            await cur.execute("BEGIN")
        try:
            updated_item = await self._repo.update_item_status(
                lote_id=lote_id,
                plano_id=plano_id,
                status="skipped",
                expected_statuses=("pending",),
            )
            if updated_item == 0:
                raise TreatmentNotFoundError("Item de tratamento não encontrado.")

            await log_event_async(
                self._connection,
                entity="tratamento_item",
                entity_id=str(plano_id),
                event_type="TRATAMENTO_SKIP",
                severity="info",
                data={
                    "lote_id": str(lote_id),
                    "plano_id": str(plano_id),
                },
            )
            async with self._connection.cursor() as cur:
                await cur.execute("COMMIT")
        except Exception:
            async with self._connection.cursor() as cur:
                await cur.execute("ROLLBACK")
            raise

    async def close(self, *, lote_id: UUID) -> TreatmentCloseResult:
        async with self._connection.cursor() as cur:
            await cur.execute("BEGIN")
        try:
            outcome: CloseBatchOutcome = await self._repo.close_batch(lote_id)
            closed = outcome.closed_rows > 0

            await log_event_async(
                self._connection,
                entity="tratamento_lote",
                entity_id=str(lote_id),
                event_type="TRATAMENTO_CLOSE",
                severity="info",
                data={
                    "lote_id": str(lote_id),
                    "pending_to_skipped": outcome.pending_to_skipped,
                    "closed": closed,
                },
            )
            async with self._connection.cursor() as cur:
                await cur.execute("COMMIT")
        except Exception:
            async with self._connection.cursor() as cur:
                await cur.execute("ROLLBACK")
            raise

        return TreatmentCloseResult(
            lote_id=lote_id,
            pending_to_skipped=outcome.pending_to_skipped,
            closed=closed,
        )

    async def repair_closed_pending_items(self) -> int:
        async with self._connection.cursor() as cur:
            await cur.execute("BEGIN")
        try:
            fixed = await self._repo.repair_closed_pending_items()
            await log_event_async(
                self._connection,
                entity="tratamento_lote",
                entity_id="*",
                event_type="TRATAMENTO_REPAIR_PENDING",
                severity="info",
                data={"fixed": fixed},
            )
            async with self._connection.cursor() as cur:
                await cur.execute("COMMIT")
        except Exception:
            async with self._connection.cursor() as cur:
                await cur.execute("ROLLBACK")
            raise

        return fixed


__all__ = [
    "ItemsPage",
    "TreatmentCloseResult",
    "TreatmentConflictError",
    "TreatmentNotFoundError",
    "TreatmentService",
    "TreatmentServiceError",
]
