from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from psycopg.rows import dict_row

from api.models import PlanSummaryResponse, PlansResponse
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
    """Map a row from vw_planos_busca to PlanSummaryResponse."""

    number = str(row.get("numero_plano") or "").strip()
    document = normalize_document(row.get("documento"))
    company_name_raw = row.get("razao_social") or row.get("razao")
    company_name = str(company_name_raw).strip() or None if company_name_raw else None
    balance_raw = row.get("saldo")
    status_date = extract_date_from_timestamp(row.get("dt_situacao"))

    return PlanSummaryResponse(
        number=number,
        document=document,
        company_name=company_name,
        status=None,
        days_overdue=None,
        balance=balance_raw,
        status_date=status_date,
    )


@router.get("/plans", response_model=PlansResponse)
async def list_treatment_plans(
    request: Request,
    page: int = Query(1, ge=1, description="Página atual (base 1)"),
    page_size: int = Query(50, ge=1, le=200, description="Itens por página"),
) -> PlansResponse:
    """Return plans currently eligible for treatment (P_RESCISAO)."""

    matricula = _resolve_request_matricula(request)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    offset = (page - 1) * page_size

    sql = (
        "SELECT numero_plano, documento, razao_social, saldo, dt_situacao,"
        " COUNT(*) OVER () AS total_count"
        "  FROM app.vw_planos_busca"
        " WHERE situacao_codigo = 'P_RESCISAO'"
        " ORDER BY saldo DESC NULLS LAST, dt_situacao DESC NULLS LAST, numero_plano"
        " LIMIT %(limit)s OFFSET %(offset)s"
    )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            async with connection.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, {"limit": page_size, "offset": offset})
                rows = await cur.fetchall()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao carregar planos para tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos para tratamento.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]
    total = int(rows[0].get("total_count") or 0) if rows else 0
    return PlansResponse(items=items, total=total, paging=None)


@router.post("/migrate", status_code=status.HTTP_204_NO_CONTENT)
async def migrate_plans(request: Request) -> None:
    """Synchronously 'migrate' all P_RESCISAO plans to the Treatment view.

    For now, migration is a no-op that validates access and returns 204,
    since the Treatment table reads directly from vw_planos_busca.
    """

    matricula = _resolve_request_matricula(request)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )
    # No operation required: the GET endpoint sources directly from the view.
    return None


__all__ = ["router"]

