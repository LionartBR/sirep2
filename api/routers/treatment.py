from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg.rows import dict_row

from api.models import PlanSummaryResponse, PlansPaging, PlansResponse
from api.dependencies import get_connection_manager
from infra.db import bind_session
from infra.repositories._helpers import extract_date_from_timestamp
from shared.config import get_principal_settings
from shared.text import normalize_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/treatment", tags=["treatment"])

_REQUEST_PRINCIPAL_HEADER_CANDIDATES = (
    "x-user-registration",
    "x-user-id",
    "x-app-user-registration",
    "x-app-user-id",
)


def _resolve_request_matricula(request: Request | None) -> str | None:
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


def _row_to_plan_summary(row: dict[str, Any]) -> PlanSummaryResponse:
    """Map a treatment table row joined with vw_planos_busca into the response model."""

    number = str(row.get("numero_plano") or "").strip()
    document = normalize_document(row.get("documento"))
    company_name_raw = row.get("razao_social") or row.get("razao")
    company_name = str(company_name_raw).strip() or None if company_name_raw else None
    status_raw = row.get("situacao")
    status = str(status_raw).strip() or None if status_raw else None
    days_overdue_raw = row.get("dias_em_atraso")
    try:
        days_overdue = int(days_overdue_raw) if days_overdue_raw is not None else None
    except (TypeError, ValueError):
        days_overdue = None
    balance_raw = row.get("saldo")
    status_date = extract_date_from_timestamp(row.get("dt_situacao"))

    return PlanSummaryResponse(
        number=number,
        document=document,
        company_name=company_name,
        status=status,
        days_overdue=days_overdue,
        balance=balance_raw,
        status_date=status_date,
    )


@router.get("/plans", response_model=PlansResponse)
async def list_treatment_plans(
    request: Request,
    page: int = Query(1, ge=1, description="Página atual (base 1)"),
    page_size: int = Query(10, ge=1, le=10, description="Itens por página (máx. 10)"),
) -> PlansResponse:
    """Return plans currently eligible for treatment (P_RESCISAO)."""

    matricula = _resolve_request_matricula(request)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    effective_page_size = max(1, min(page_size, 10))
    offset = (page - 1) * effective_page_size

    sql = (
        "SELECT v.numero_plano, v.documento, v.razao_social, v.situacao,"
        "       v.dias_em_atraso, v.saldo, v.dt_situacao,"
        "       COUNT(*) OVER () AS total_count"
        "  FROM app.vw_planos_busca AS v"
        " WHERE v.situacao_codigo = 'P_RESCISAO'"
        " ORDER BY v.saldo DESC NULLS LAST, v.dt_situacao DESC NULLS LAST, v.numero_plano"
        " LIMIT %(limit)s OFFSET %(offset)s"
    )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            async with connection.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, {"limit": effective_page_size, "offset": offset})
                rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao carregar planos para tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos para tratamento.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]
    total = int(rows[0].get("total_count") or 0) if rows else 0

    showing_from = offset + 1 if rows else 0
    showing_to = offset + len(rows) if rows else 0
    total_pages = math.ceil(total / effective_page_size) if total else 0
    has_more = offset + len(rows) < total

    paging = PlansPaging(
        page=page,
        page_size=effective_page_size,
        has_more=has_more,
        next_cursor=None,
        prev_cursor=None,
        showing_from=showing_from,
        showing_to=showing_to,
        total_count=total,
        total_pages=total_pages,
    )

    return PlansResponse(items=items, total=total, paging=paging)


@router.post("/migrate", status_code=status.HTTP_204_NO_CONTENT)
async def migrate_plans(request: Request) -> None:
    """Trigger a refresh of treatment data without persisting duplicates."""

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
            async with connection.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM app.vw_planos_busca"
                    " WHERE situacao_codigo = 'P_RESCISAO'"
                )
                await cur.fetchone()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao migrar planos para tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível migrar os planos para tratamento.",
        ) from exc


__all__ = ["router"]
