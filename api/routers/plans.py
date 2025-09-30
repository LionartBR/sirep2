from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
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


PLAN_DEFAULT_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo_total,
        dt_situacao,
        valor_atrasado
      FROM app.vw_planos_busca
     ORDER BY valor_atrasado DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NUMBER_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo_total,
        dt_situacao,
        valor_atrasado
      FROM app.vw_planos_busca
     WHERE numero_plano = %(number)s
        OR numero_plano LIKE %(number)s || '%'
     ORDER BY valor_atrasado DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NAME_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo_total,
        dt_situacao,
        valor_atrasado
      FROM app.vw_planos_busca
     WHERE razao_social ILIKE '%%' || %(term)s || '%%'
     ORDER BY valor_atrasado DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_DOCUMENT_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo_total,
        dt_situacao,
        valor_atrasado
      FROM app.vw_planos_busca
     WHERE documento = %(document)s
       AND tipo_doc IN ('CNPJ', 'CEI')
     ORDER BY valor_atrasado DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


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
    document = _normalize_document(
        row.get("numero_inscricao")
        or row.get("documento")
        or row.get("document")
    )
    company_name_raw = row.get("razao_social") or row.get("razao")
    company_name = str(company_name_raw).strip() or None if company_name_raw else None
    status_raw = row.get("situacao") or row.get("status")
    status = str(status_raw).strip() or None if status_raw else None
    days_overdue = _normalize_days(
        row.get("dias_em_atraso")
        or row.get("dias_atraso")
        or row.get("dias_atrasados")
    )
    balance = _normalize_balance(
        row.get("saldo_total")
        or row.get("saldo")
        or row.get("valor_atrasado")
    )
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


async def _fetch_plan_rows(
    connection: AsyncConnection,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Execute the SQL query returning plans for the dashboard."""

    normalized_search = (search or "").strip()
    digits = only_digits(normalized_search)

    if digits and len(digits) in (11, 14):
        query = PLAN_SEARCH_BY_DOCUMENT_QUERY
        params = {"document": digits, "limit": limit, "offset": offset}
    elif normalized_search.isdigit() and normalized_search:
        query = PLAN_SEARCH_BY_NUMBER_QUERY
        params = {"number": normalized_search, "limit": limit, "offset": offset}
    elif normalized_search:
        query = PLAN_SEARCH_BY_NAME_QUERY
        params = {"term": normalized_search, "limit": limit, "offset": offset}
    else:
        query = PLAN_DEFAULT_QUERY
        params = {"limit": limit, "offset": offset}

    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        rows = await cursor.fetchall()
    return list(rows)


@router.get("", response_model=PlansResponse)
async def list_plans(
    q: str | None = Query(None, max_length=255, description="Termo de busca"),
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Quantidade de itens por página",
    ),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação"),
) -> PlansResponse:
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
            rows = await _fetch_plan_rows(
                connection,
                search=q,
                limit=limit,
                offset=offset,
            )
    except Exception as exc:  # pragma: no cover - defensive programming
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]
    return PlansResponse(items=items, total=len(items))


__all__ = ["router", "list_plans"]
