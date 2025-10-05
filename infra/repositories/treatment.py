from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from domain.treatment import (
    TreatmentBatch,
    TreatmentItem,
    TreatmentMigrationResult,
    TreatmentTotals,
)
from infra.audit import log_event_async
from shared.text import normalize_document


_CURSOR_SENTINEL = "{}"


@dataclass(slots=True)
class KeysetPayload:
    saldo: Decimal
    numero: str
    provided: bool


def encode_cursor(saldo: Any, numero: Any) -> str:
    payload = {
        "s": None if saldo is None else str(saldo),
        "n": None if numero is None else str(numero),
    }
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return urlsafe_b64encode(data).decode("ascii")


def decode_cursor(token: str | None) -> KeysetPayload | None:
    if not token:
        return None
    try:
        raw = urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:  # pragma: no cover - defensive
        return None

    saldo_raw = payload.get("s")
    numero_raw = payload.get("n")
    provided = saldo_raw is not None or numero_raw is not None
    try:
        saldo_val = Decimal(str(saldo_raw)) if saldo_raw is not None else Decimal(0)
    except Exception:  # pragma: no cover - defensive
        saldo_val = Decimal(0)
    numero_val = "" if numero_raw is None else str(numero_raw)
    return KeysetPayload(saldo=saldo_val, numero=numero_val, provided=provided)


@dataclass(slots=True)
class CloseBatchOutcome:
    pending_to_skipped: int
    closed_rows: int


class TreatmentRepository:
    """Async persistence helpers for treatment batches and items."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def fetch_open_batch(self, grid: str) -> Optional[TreatmentBatch]:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, grid, status, source_filter, created_at, closed_at
                  FROM app.tratamento_lote
                 WHERE grid = %s
                   AND status = 'OPEN'
                   AND user_id = app.current_user_id()
                   AND tenant_id = app.current_tenant_id()
                 ORDER BY created_at DESC
                 LIMIT 1
                """,
                (grid,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return TreatmentBatch(
            id=row["id"],
            grid=row["grid"],
            status=row["status"],
            source_filter=row.get("source_filter"),
            created_at=row["created_at"],
            closed_at=row.get("closed_at"),
        )

    async def fetch_batch_by_id(self, lote_id: UUID) -> Optional[TreatmentBatch]:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, grid, status, source_filter, created_at, closed_at
                  FROM app.tratamento_lote
                 WHERE id = %s
                   AND user_id = app.current_user_id()
                   AND tenant_id = app.current_tenant_id()
                """,
                (lote_id,),
            )
            row = await cur.fetchone()
        if not row:
            return None
        return TreatmentBatch(
            id=row["id"],
            grid=row["grid"],
            status=row["status"],
            source_filter=row.get("source_filter"),
            created_at=row["created_at"],
            closed_at=row.get("closed_at"),
        )

    async def fetch_totals(self, lote_id: UUID) -> TreatmentTotals:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT LOWER(status) AS status_key, COUNT(*) AS total
                  FROM app.tratamento_item
                 WHERE lote_id = %s
                 GROUP BY status_key
                """,
                (lote_id,),
            )
            rows = await cur.fetchall()
        mapping: dict[str, int] = {}
        for row in rows:
            status_key = (
                str(row.get("status_key") or "").strip().lower() or _CURSOR_SENTINEL
            )
            mapping[status_key] = int(row.get("total") or 0)
        return TreatmentTotals(
            pending=mapping.get("pending", 0),
            processed=mapping.get("processed", 0),
            skipped=mapping.get("skipped", 0),
        )

    async def create_batch_and_snapshot(
        self,
        *,
        grid: str,
        filters: Optional[Mapping[str, Any]],
    ) -> TreatmentMigrationResult:
        filters_dict = dict(filters) if filters is not None else None
        payload = Json(filters_dict) if filters_dict is not None else None
        existing_batch = await self.fetch_open_batch(grid)

        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT app.tratamento_migrar_planos_global(%s::jsonb) AS result",
                (payload,),
            )
            result_row = await cur.fetchone()

        lote_id, created_flag, items_seeded = self._parse_migration_result(result_row)

        if lote_id is None:
            batch_after = await self.fetch_open_batch(grid)
            if not batch_after:
                raise RuntimeError("Falha ao localizar lote aberto de tratamento")
            lote_id = batch_after.id
        created = (
            bool(created_flag)
            if created_flag is not None
            else not existing_batch or existing_batch.id != lote_id
        )

        if items_seeded is None:
            items_seeded = await self._count_items_for_lote(lote_id) if created else 0

        await log_event_async(
            self._connection,
            entity="tratamento_lote",
            entity_id=str(lote_id),
            event_type="TRATAMENTO_MIGRAR",
            severity="info",
            data={
                "grid": grid,
                "filters": filters_dict or {},
                "items": items_seeded,
                "created": created,
            },
        )

        return TreatmentMigrationResult(
            lote_id=lote_id,
            items_seeded=items_seeded,
            created=created,
        )

    @staticmethod
    def _coerce_uuid(value: Any) -> Optional[UUID]:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:  # pragma: no cover - defensive
                return None
        return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

    def _parse_migration_result(
        self, row: Optional[Mapping[str, Any]]
    ) -> tuple[Optional[UUID], Optional[bool], Optional[int]]:
        if not row:
            return None, None, None

        candidate: Any
        if len(row) == 1:
            candidate = next(iter(row.values()))
        else:
            candidate = row

        lote_id: Optional[UUID] = None
        created_flag: Optional[bool] = None
        items_seeded: Optional[int] = None

        if isinstance(candidate, Mapping):
            lote_id = self._coerce_uuid(
                candidate.get("lote_id")
                or candidate.get("id")
                or candidate.get("lote")
                or candidate.get("batch_id")
            )
            items_seeded = self._coerce_int(
                candidate.get("items_seeded")
                or candidate.get("items")
                or candidate.get("inserted")
                or candidate.get("count")
            )
            if "created" in candidate:
                created_flag = bool(candidate.get("created"))
        elif isinstance(candidate, (list, tuple)) and candidate:
            lote_id = self._coerce_uuid(candidate[0])
            if len(candidate) > 1:
                items_seeded = self._coerce_int(candidate[1])
            if len(candidate) > 2:
                created_flag = bool(candidate[2])
        else:
            lote_id = self._coerce_uuid(candidate)

        if lote_id is None:
            lote_id = self._coerce_uuid(row.get("lote_id"))
        if items_seeded is None:
            items_seeded = self._coerce_int(row.get("items_seeded") or row.get("items"))
        if created_flag is None and "created" in row:
            created_flag = bool(row.get("created"))

        return lote_id, created_flag, items_seeded

    async def _count_items_for_lote(self, lote_id: UUID) -> int:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT COUNT(*) AS total FROM app.tratamento_item WHERE lote_id = %s",
                (lote_id,),
            )
            row = await cur.fetchone()
        total = row.get("total") if row else 0
        try:
            return int(total)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return 0

    async def list_items_keyset(
        self,
        *,
        lote_id: UUID,
        status: str,
        page_size: int,
        cursor: str | None,
        direction: str,
    ) -> tuple[list[TreatmentItem], bool]:
        status = status.strip().lower()
        if status not in {"pending", "processed", "skipped"}:
            status = "pending"
        payload = decode_cursor(cursor)
        conditions = ["lote_id = %s", "LOWER(status) = %s"]
        params: list[Any] = [lote_id, status]
        if payload and payload.provided:
            if direction == "prev":
                conditions.append(
                    "(COALESCE(saldo, 0) > %s OR (COALESCE(saldo, 0) = %s AND numero_plano < %s))"
                )
            else:
                conditions.append(
                    "(COALESCE(saldo, 0) < %s OR (COALESCE(saldo, 0) = %s AND numero_plano > %s))"
                )
            params.extend([payload.saldo, payload.saldo, payload.numero])
        where_clause = " WHERE " + " AND ".join(conditions)
        order_clause = (
            " ORDER BY COALESCE(saldo,0) ASC, numero_plano DESC"
            if direction == "prev"
            else " ORDER BY COALESCE(saldo,0) DESC, numero_plano ASC"
        )
        limit_clause = " LIMIT %s"
        params.append(page_size + 1)

        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT
                    lote_id,
                    plano_id,
                    numero_plano,
                    documento,
                    razao_social,
                    saldo,
                    dt_situacao,
                    situacao_codigo,
                    status,
                    processed_at
                  FROM app.tratamento_item
                {where_clause}
                {order_clause}
                {limit_clause}
                """,
                tuple(params),
            )
            rows = await cur.fetchall()

        has_more = len(rows) > page_size
        if direction == "prev":
            rows = rows[:page_size]
            rows.reverse()
        else:
            rows = rows[:page_size]

        items: list[TreatmentItem] = []
        for row in rows:
            numero_plano = str(row.get("numero_plano") or "").strip()
            documento = normalize_document(row.get("documento"), allow_empty=True)
            items.append(
                TreatmentItem(
                    lote_id=row["lote_id"],
                    plano_id=row["plano_id"],
                    numero_plano=numero_plano,
                    documento=documento if documento else None,
                    razao_social=(row.get("razao_social") or None),
                    saldo=row.get("saldo"),
                    dt_situacao=row.get("dt_situacao"),
                    situacao_codigo=row.get("situacao_codigo"),
                    status=str(row.get("status") or "pending"),
                    processed_at=row.get("processed_at"),
                )
            )
        return items, has_more

    async def update_item_status(
        self,
        *,
        lote_id: UUID,
        plano_id: UUID,
        status: str,
        expected_statuses: Optional[Sequence[str]] = None,
    ) -> int:
        expected_clause = ""
        params: list[Any] = [status, status, lote_id, plano_id]
        if expected_statuses:
            expected_clause = " AND LOWER(status) = ANY(%s)"
            normalized = [str(value).strip().lower() for value in expected_statuses]
            params.append(normalized)

        async with self._connection.cursor() as cur:
            await cur.execute(
                f"""
                UPDATE app.tratamento_item
                   SET status = %s,
                       processed_at = CASE WHEN %s <> 'pending' THEN now() ELSE NULL END
                 WHERE lote_id = %s
                   AND plano_id = %s{expected_clause}
                """,
                tuple(params),
            )
            return cur.rowcount or 0

    async def rescind_item_via_function(
        self, *, lote_id: UUID, plano_id: UUID, effective_ts: str
    ) -> bool:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT app.tratamento_rescindir_plano(%s::uuid, %s::uuid, %s::timestamptz)
                  AS result
                """,
                (lote_id, plano_id, effective_ts),
            )
            row = await cur.fetchone()

        if not row:
            return True

        value = row.get("result")
        if value is None and len(row) == 1:
            value = next(iter(row.values()))
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value > 0
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"t", "true", "ok", "1"}:
                return True
            if lowered in {"f", "false", "0"}:
                return False
        return True

    async def close_batch(self, lote_id: UUID) -> CloseBatchOutcome:
        async with self._connection.cursor() as cur:
            await cur.execute(
                """
                UPDATE app.tratamento_item
                   SET status = 'skipped',
                       processed_at = now()
                 WHERE lote_id = %s
                   AND tenant_id = app.current_tenant_id()
                   AND status = 'pending'
                """,
                (lote_id,),
            )
            pending_to_skipped = cur.rowcount or 0

            await cur.execute(
                """
                UPDATE app.tratamento_lote
                   SET status = 'CLOSED',
                       closed_at = now()
                 WHERE id = %s
                   AND tenant_id = app.current_tenant_id()
                   AND user_id = app.current_user_id()
                   AND status = 'OPEN'
                """,
                (lote_id,),
            )
            closed_rows = cur.rowcount or 0

        return CloseBatchOutcome(
            pending_to_skipped=pending_to_skipped,
            closed_rows=closed_rows,
        )

    async def repair_closed_pending_items(self) -> int:
        async with self._connection.cursor() as cur:
            await cur.execute(
                """
                UPDATE app.tratamento_item AS item
                   SET status = 'skipped',
                       processed_at = now()
                 WHERE item.status = 'pending'
                   AND item.lote_id IN (
                       SELECT lote.id
                         FROM app.tratamento_lote AS lote
                        WHERE lote.status = 'CLOSED'
                          AND lote.tenant_id = app.current_tenant_id()
                          AND lote.user_id = app.current_user_id()
                   )
                """
            )
            return cur.rowcount or 0

    async def fetch_queue_metadata(self, plano_id: UUID) -> dict[str, Any]:
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT filas,
                       users_enfileirando,
                       lotes
                  FROM app.vw_tratamento_enfileirado
                 WHERE plano_id = %s
                 LIMIT 1
                """,
                (plano_id,),
            )
            row = await cur.fetchone()

        if not row:
            return {"enqueued": False, "filas": 0, "users": 0, "lotes": 0}

        def _to_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                return 0

        filas = _to_int(row.get("filas"))
        users = _to_int(row.get("users_enfileirando") or row.get("users"))
        lotes = _to_int(row.get("lotes"))
        return {
            "enqueued": any(v > 0 for v in (filas, users, lotes)),
            "filas": filas,
            "users": users,
            "lotes": lotes,
        }


__all__ = [
    "KeysetPayload",
    "CloseBatchOutcome",
    "TreatmentRepository",
    "decode_cursor",
    "encode_cursor",
]
