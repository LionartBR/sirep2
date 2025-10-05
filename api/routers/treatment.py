from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.dependencies import get_connection_manager
from api.models import (
    TreatmentCloseRequest,
    TreatmentItemsResponse,
    TreatmentItemResponse,
    TreatmentMigrateRequest,
    TreatmentMigrationResponse,
    TreatmentPagingResponse,
    TreatmentRescindRequest,
    TreatmentSkipRequest,
    TreatmentStateResponse,
    TreatmentTotalsResponse,
)
from domain.treatment import TreatmentItem, TreatmentState, TreatmentTotals
from infra.db import bind_session
from services.treatment import (
    TreatmentConflictError,
    TreatmentNotFoundError,
    TreatmentService,
)
from api.security import resolve_request_matricula, role_required

try:  # pragma: no cover - allow monkeypatching in tests without config module
    from shared.config import get_principal_settings  # type: ignore
except Exception:  # pragma: no cover - fallback stub when config missing

    def get_principal_settings():
        class _Principal:
            matricula: str | None = None

        return _Principal()

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/treatment",
    tags=["treatment"],
    dependencies=[Depends(role_required("GESTOR", "RESCISAO"))],
)

DEFAULT_GRID = "PLANOS_P_RESCISAO"


def _to_totals_response(totals: TreatmentTotals) -> TreatmentTotalsResponse:
    return TreatmentTotalsResponse(
        pending=totals.pending,
        processed=totals.processed,
        skipped=totals.skipped,
    )


def _to_state_response(state: TreatmentState) -> TreatmentStateResponse:
    return TreatmentStateResponse(
        has_open=state.has_open,
        lote_id=state.lote_id,
        totals=_to_totals_response(state.totals),
    )


def _to_item_response(item: TreatmentItem) -> TreatmentItemResponse:
    company = (item.razao_social or "").strip() or None
    return TreatmentItemResponse(
        lote_id=item.lote_id,
        plano_id=item.plano_id,
        number=item.numero_plano,
        document=item.documento,
        company_name=company,
        balance=item.saldo,
        status_date=item.dt_situacao,
        status=item.status,
        situacao_codigo=item.situacao_codigo,
    )


@router.get("/state", response_model=TreatmentStateResponse)
async def get_treatment_state(
    request: Request,
    grid: str = Query(DEFAULT_GRID, alias="grid"),
) -> TreatmentStateResponse:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            state = await service.get_state(grid=grid)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao carregar estado do tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar o estado do tratamento.",
        ) from exc

    return _to_state_response(state)


@router.post("/migrate", response_model=TreatmentMigrationResponse)
async def migrate_treatment(
    request: Request,
    payload: TreatmentMigrateRequest,
) -> TreatmentMigrationResponse:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    grid = (payload.grid or DEFAULT_GRID).strip().upper() or DEFAULT_GRID
    if grid != DEFAULT_GRID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grid de tratamento não suportada.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            result = await service.migrate(grid=grid, filters=payload.filters)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao migrar planos para tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível migrar os planos para tratamento.",
        ) from exc

    return TreatmentMigrationResponse(
        lote_id=result.lote_id,
        items_seeded=result.items_seeded,
        created=result.created,
    )


@router.get("/items", response_model=TreatmentItemsResponse)
async def list_treatment_items(
    request: Request,
    lote_id: UUID,
    status_value: str = Query("pending", alias="status"),
    page_size: int = Query(10, ge=1, le=50),
    cursor: str | None = Query(None),
    direction: str = Query("next", regex="^(next|prev)$"),
) -> TreatmentItemsResponse:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            page = await service.list_items(
                lote_id=lote_id,
                status=status_value,
                page_size=page_size,
                cursor=cursor,
                direction=direction,
            )
    except TreatmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Item não encontrado.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao carregar itens do tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os itens do tratamento.",
        ) from exc

    items = [_to_item_response(item) for item in page.items]
    paging = TreatmentPagingResponse(
        next_cursor=page.next_cursor,
        prev_cursor=page.prev_cursor,
        has_more=page.has_more,
        page_size=page.page_size,
    )
    return TreatmentItemsResponse(items=items, paging=paging)


@router.post("/rescind")
async def rescind_treatment_item(
    request: Request,
    payload: TreatmentRescindRequest,
) -> dict[str, bool]:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    effective_iso = payload.data_rescisao.isoformat()
    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            await service.rescind(
                lote_id=payload.lote_id,
                plano_id=payload.plano_id,
                effective_dt_iso=effective_iso,
            )
    except TreatmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Item não encontrado.",
        ) from exc
    except TreatmentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc) or "Operação não permitida no estado atual.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao rescindir plano do tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível rescindir o plano selecionado.",
        ) from exc

    return {"ok": True}


@router.post("/skip")
async def skip_treatment_item(
    request: Request,
    payload: TreatmentSkipRequest,
) -> dict[str, bool]:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            await service.skip(lote_id=payload.lote_id, plano_id=payload.plano_id)
    except TreatmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc) or "Item não encontrado.",
        ) from exc
    except TreatmentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc) or "Operação não permitida no estado atual.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao pular item do tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível marcar o item como ignorado.",
        ) from exc

    return {"ok": True}


@router.post("/close")
async def close_treatment_batch(
    request: Request,
    payload: TreatmentCloseRequest,
) -> dict[str, object]:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            service = TreatmentService(connection)
            result = await service.close(lote_id=payload.lote_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao encerrar lote de tratamento")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível encerrar o lote.",
        ) from exc

    return {
        "ok": True,
        "lote_id": str(result.lote_id),
        "pending_to_skipped": result.pending_to_skipped,
        "closed": result.closed,
    }


__all__ = ["router"]
