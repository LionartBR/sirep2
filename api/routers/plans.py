from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from api.models import PlanSummaryResponse, PlansResponse
from infra.db import bind_session, get_connection
from infra.repositories._helpers import (
    extract_date_from_timestamp,
    only_digits,
    to_decimal,
)
from shared.config import get_principal_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["plans"])


PLAN_LIST_QUERY = """
    SELECT
        p.numero_plano AS numero_plano,
        emp.numero_inscricao AS numero_inscricao,
        emp.razao_social AS razao_social,
        sp.codigo AS situacao,
        CASE
            WHEN p.atraso_desde IS NULL THEN NULL
            ELSE GREATEST(0, CURRENT_DATE - p.atraso_desde)
        END AS dias_em_atraso,
        p.saldo_total AS saldo_total,
        hist.mudou_em AS dt_situacao
    FROM app.plano AS p
    LEFT JOIN app.empregador AS emp ON emp.id = p.empregador_id
    LEFT JOIN ref.situacao_plano AS sp ON sp.id = p.situacao_plano_id
    LEFT JOIN LATERAL (
        SELECT h.mudou_em
          FROM app.plano_situacao_hist AS h
         WHERE h.plano_id = p.id
         ORDER BY h.mudou_em DESC NULLS LAST
         LIMIT 1
    ) AS hist ON TRUE
    ORDER BY p.numero_plano
"""


def _get_connection_manager() -> AbstractAsyncContextManager[AsyncConnection]:
    """Return the connection manager used by this router.

    The indirection allows tests to patch the dependency easily.
    """

    return get_connection()


def _normalize_days(value: Any) -> int | None:
    """Convert the raw ``dias_em_atraso`` value to an integer."""

    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return max(days, 0)


def _normalize_balance(value: Any) -> Decimal | None:
    """Convert the raw balance to ``Decimal`` when possible."""

    decimal_value = to_decimal(value)
    if decimal_value is None:
        return None
    return decimal_value


def _normalize_document(value: Any) -> str | None:
    """Return a cleaned document identifier (digits only when available)."""

    if value is None:
        return None
    digits = only_digits(value)
    texto = str(value).strip()
    if digits:
        return digits
    return texto or None


def _row_to_plan_summary(row: dict[str, Any]) -> PlanSummaryResponse:
    """Transform a database row into the API response model."""

    number = str(row.get("numero_plano") or "").strip()
    document = _normalize_document(row.get("numero_inscricao"))
    company_name_raw = row.get("razao_social")
    company_name = str(company_name_raw).strip() or None if company_name_raw else None
    status_raw = row.get("situacao")
    status = str(status_raw).strip() or None if status_raw else None
    days_overdue = _normalize_days(row.get("dias_em_atraso"))
    balance = _normalize_balance(row.get("saldo_total"))
    status_date = extract_date_from_timestamp(row.get("dt_situacao"))

    return PlanSummaryResponse(
        number=number,
        document=document,
        company_name=company_name,
        status=status,
        days_overdue=days_overdue,
        balance=balance,
        status_date=status_date,
    )


async def _fetch_plan_rows(connection: AsyncConnection) -> list[dict[str, Any]]:
    """Execute the SQL query returning plans for the dashboard."""

    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(PLAN_LIST_QUERY)
        rows = await cursor.fetchall()
    return list(rows)


@router.get("", response_model=PlansResponse)
async def list_plans() -> PlansResponse:
    """Return the consolidated plans available for the dashboard."""

    principal = get_principal_settings()
    matricula = (principal.matricula or "").strip() if principal.matricula else None
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = _get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            rows = await _fetch_plan_rows(connection)
    except Exception as exc:  # pragma: no cover - defensive programming
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]
    return PlansResponse(items=items, total=len(items))


__all__ = ["router", "list_plans"]
