from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
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
        filters_payload = Json(filters_dict) if filters_dict is not None else None
        async with self._connection.cursor(row_factory=dict_row) as cur:
            await cur.execute("BEGIN")
            try:
                await cur.execute(
                    """
                    INSERT INTO app.tratamento_lote (
                        tenant_id, user_id, grid, status, source_filter
                    )
                    VALUES (
                        app.current_tenant_id(),
                        app.current_user_id(),
                        %s,
                        'OPEN',
                        %s::jsonb
                    )
                    RETURNING id
                    """,
                    (grid, filters_payload),
                )
                lote_row = await cur.fetchone()
                if not lote_row:
                    raise RuntimeError("Falha ao criar lote de tratamento")
                lote_id = lote_row["id"]
                await cur.execute(
                    """
                    INSERT INTO app.tratamento_item (
                        tenant_id, lote_id, plano_id, numero_plano, documento,
                        razao_social, saldo, dt_situacao, situacao_codigo
                    )
                    SELECT
                        app.current_tenant_id(),
                        %s,
                        p.id,
                        p.numero_plano,
                        e.numero_inscricao,
                        e.razao_social,
                        p.saldo_total,
                        p.dt_situacao_atual::date,
                        sp.codigo
                      FROM app.plano AS p
                      JOIN app.empregador AS e ON e.id = p.empregador_id
                      JOIN ref.situacao_plano AS sp ON sp.id = p.situacao_plano_id
                     WHERE p.situacao_plano_id = sp.id
                       AND sp.codigo = 'P_RESCISAO'
                    """,
                    (lote_id,),
                )
                items_seeded = cur.rowcount or 0
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
                    },
                )
                await cur.execute("COMMIT")
                return TreatmentMigrationResult(
                    lote_id=lote_id,
                    items_seeded=items_seeded,
                    created=True,
                )
            except UniqueViolation:
                await cur.execute("ROLLBACK")
                existing = await self.fetch_open_batch(grid)
                if not existing:
                    raise
                return TreatmentMigrationResult(
                    lote_id=existing.id,
                    items_seeded=0,
                    created=False,
                )
            except Exception:
                await cur.execute("ROLLBACK")
                raise

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

    async def update_plan_to_rescinded(
        self, *, plano_id: UUID, effective_ts: str
    ) -> int:
        async with self._connection.cursor() as cur:
            await cur.execute(
                "SET LOCAL app.situacao_effective_ts = %s", (effective_ts,)
            )
            await cur.execute(
                """
                UPDATE app.plano
                   SET situacao_plano_id = (
                        SELECT id FROM ref.situacao_plano WHERE codigo = 'RESCINDIDO'
                   )
                 WHERE id = %s
                """,
                (plano_id,),
            )
            return cur.rowcount or 0

    async def close_batch(self, lote_id: UUID) -> int:
        async with self._connection.cursor() as cur:
            await cur.execute(
                """
                UPDATE app.tratamento_lote
                   SET status = 'CLOSED',
                       closed_at = now()
                 WHERE id = %s
                """,
                (lote_id,),
            )
            return cur.rowcount or 0


__all__ = [
    "KeysetPayload",
    "TreatmentRepository",
    "decode_cursor",
    "encode_cursor",
]
