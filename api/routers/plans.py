from __future__ import annotations

import logging
import unicodedata
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg import AsyncConnection
from psycopg.errors import InvalidAuthorizationSpecification
from psycopg.rows import dict_row

from api.models import PlanSummaryResponse, PlansResponse
from api.dependencies import get_connection_manager
from infra.db import bind_session
from infra.repositories._helpers import (
    extract_date_from_timestamp,
    normalizar_situacao,
    only_digits,
    to_decimal,
)
from shared.config import get_principal_settings
from shared.text import normalize_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["plans"])


_STATUS_LABELS = {
    "P_RESCISAO": "P. RESCISAO",
    "SIT_ESPECIAL": "SIT. ESPECIAL",
    "GRDE_EMITIDA": "GRDE Emitida",
    "LIQUIDADO": "LIQUIDADO",
    "RESCINDIDO": "RESCINDIDO",
}


PLAN_DEFAULT_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo,
        dt_situacao,
        COUNT(*) OVER () AS total_count
      FROM app.vw_planos_busca
     ORDER BY saldo DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NUMBER_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo,
        dt_situacao,
        COUNT(*) OVER () AS total_count
      FROM app.vw_planos_busca
     WHERE numero_plano = %(number)s
        OR numero_plano LIKE %(number_prefix)s
     ORDER BY saldo DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NAME_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo,
        dt_situacao,
        COUNT(*) OVER () AS total_count
      FROM app.vw_planos_busca
     WHERE razao_social ILIKE %(name_pattern)s
     ORDER BY saldo DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_DOCUMENT_QUERY = """
    SELECT
        numero_plano,
        documento,
        razao_social,
        situacao,
        dias_em_atraso,
        saldo,
        dt_situacao,
        COUNT(*) OVER () AS total_count
      FROM app.vw_planos_busca
     WHERE documento = %(document)s
       AND tipo_doc IN ('CNPJ', 'CPF', 'CEI')
     ORDER BY saldo DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_REQUEST_PRINCIPAL_HEADER_CANDIDATES = (
    "x-user-registration",
    "x-user-id",
    "x-app-user-registration",
    "x-app-user-id",
)


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

    return normalize_document(value)


def _remove_accents(value: str) -> str:
    """Return the ASCII representation of ``value`` without diacritics."""

    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _format_status(value: Any) -> str | None:
    """Normalize status descriptions to the expected dashboard labels."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    ascii_text = _remove_accents(text)
    normalized = normalizar_situacao(ascii_text)
    label = _STATUS_LABELS.get(normalized)
    if label is not None:
        return label
    return text


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
    status = _format_status(status_raw)
    days_overdue = _normalize_days(
        row.get("dias_em_atraso")
        or row.get("dias_atraso")
        or row.get("dias_atrasados")
    )
    balance_raw = row.get("saldo")
    if balance_raw is None:
        balance_raw = row.get("saldo_total")
    if balance_raw is None:
        balance_raw = row.get("valor_atrasado")
    balance = _normalize_balance(balance_raw)
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


def _resolve_request_matricula(request: Request | None) -> str | None:
    """Retrieve the matricula provided by the caller or fallback to defaults."""

    if request is not None:
        for header in _REQUEST_PRINCIPAL_HEADER_CANDIDATES:
            value = request.headers.get(header)
            if value:
                candidate = value.split(",", 1)[0].strip()
                if candidate:
                    return candidate

    principal = get_principal_settings()
    matricula = (principal.matricula or "").strip() if principal.matricula else ""
    return matricula or None


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

    if digits and len(digits) in (11, 12, 14):
        query = PLAN_SEARCH_BY_DOCUMENT_QUERY
        params = {"document": digits, "limit": limit, "offset": offset}
    elif normalized_search.isdigit() and normalized_search:
        query = PLAN_SEARCH_BY_NUMBER_QUERY
        number_prefix = f"{normalized_search}%"
        params = {
            "number": normalized_search,
            "number_prefix": number_prefix,
            "limit": limit,
            "offset": offset,
        }
    elif normalized_search:
        query = PLAN_SEARCH_BY_NAME_QUERY
        name_pattern = f"%{normalized_search}%"
        params = {
            "name_pattern": name_pattern,
            "limit": limit,
            "offset": offset,
        }
    else:
        query = PLAN_DEFAULT_QUERY
        params = {"limit": limit, "offset": offset}

    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        rows = await cursor.fetchall()
    return list(rows)


@router.get("", response_model=PlansResponse)
async def list_plans(
    request: Request,
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

    matricula = _resolve_request_matricula(request)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            rows = await _fetch_plan_rows(
                connection,
                search=q,
                limit=limit,
                offset=offset,
            )
    except (PermissionError, InvalidAuthorizationSpecification) as exc:
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso inválidas.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive programming
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]
    if rows:
        total_raw = rows[0].get("total_count")
        total = int(total_raw) if total_raw is not None else len(rows)
    else:
        total = 0
    return PlansResponse(items=items, total=total)


__all__ = ["router", "list_plans"]
