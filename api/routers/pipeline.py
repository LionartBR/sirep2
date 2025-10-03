from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from ..models import (
    PipelineStartPayload,
    PipelineStateResponse,
    PipelineStatusViewResponse,
)
from api.dependencies import get_connection_manager
from infra.db import bind_session
from shared.config import get_principal_settings
from services.orchestrator import (
    PipelineAlreadyRunningError,
    PipelineOrchestrator,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = logging.getLogger(__name__)

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


def _format_duration(
    started_at: Optional[datetime], finished_at: Optional[datetime]
) -> Optional[str]:
    if not started_at or not finished_at:
        return None
    delta = finished_at - started_at
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


async def _fetch_latest_job_run(
    connection: AsyncConnection,
    job_name: str,
) -> dict[str, Any] | None:
    async with connection.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            (
                "SELECT status, started_at, finished_at"
                "  FROM audit.job_run"
                " WHERE tenant_id = app.current_tenant_id()"
                "   AND job_name = %(job_name)s"
                " ORDER BY COALESCE(finished_at, started_at) DESC"
                " LIMIT 1"
            ),
            {"job_name": job_name},
        )
        return await cur.fetchone()


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    """Retrieve the orchestrator stored on the FastAPI app."""

    orchestrator = getattr(request.app.state, "pipeline_orchestrator", None)
    if orchestrator is None:
        orchestrator = PipelineOrchestrator()
        request.app.state.pipeline_orchestrator = orchestrator
    return orchestrator


@router.post(
    "/start", response_model=PipelineStateResponse, status_code=status.HTTP_202_ACCEPTED
)
async def start_pipeline(
    payload: PipelineStartPayload | None = None,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> PipelineStateResponse:
    """Accept a request to trigger the Gestão da Base pipeline."""

    payload = payload or PipelineStartPayload()
    try:
        state = await orchestrator.start(
            matricula=payload.matricula, senha=payload.senha
        )
    except PipelineAlreadyRunningError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return PipelineStateResponse.from_state(state)


@router.get("/state", response_model=PipelineStateResponse)
async def get_pipeline_state(
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> PipelineStateResponse:
    """Return the current state of the pipeline."""

    state = orchestrator.get_state()
    return PipelineStateResponse.from_state(state)


@router.get("/status", response_model=PipelineStatusViewResponse)
async def get_pipeline_status(
    request: Request,
    job_name: str = Query("gestao_base", description="Nome do job monitorado"),
) -> PipelineStatusViewResponse:
    """Return last update information for the given job from app.vw_pipeline_status.

    Binds the session using app.login_matricula and preserves RLS.
    """

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
            async with connection.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    (
                        "SELECT job_name, status, last_update_at, duration_text"
                        "  FROM app.vw_pipeline_status"
                        " WHERE job_name = %(job_name)s"
                        " LIMIT 1"
                    ),
                    {"job_name": job_name},
                )
                row: dict[str, Any] | None = await cur.fetchone()
            job_run_row = await _fetch_latest_job_run(connection, job_name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao consultar vw_pipeline_status")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível consultar o status da pipeline.",
        ) from exc

    if not row and not job_run_row:
        return PipelineStatusViewResponse(
            job_name=job_name,
            status="N/A",
            last_update_at=None,
            duration_text=None,
            started_at=None,
            finished_at=None,
        )

    last_update_at = row.get("last_update_at") if row else None
    duration_text = (row.get("duration_text") or None) if row else None
    status_value = str(row.get("status") or "N/A") if row else "N/A"
    job_name_value = str(row.get("job_name") or job_name) if row else job_name
    started_at = job_run_row.get("started_at") if job_run_row else None
    finished_at = job_run_row.get("finished_at") if job_run_row else None

    if not last_update_at and row:
        last_update_at = row.get("last_update_at")
    if not last_update_at:
        last_update_at = finished_at or started_at
    if not duration_text:
        duration_text = _format_duration(started_at, finished_at)
    if row and row.get("duration_text"):
        duration_text = row.get("duration_text") or duration_text
    if (not status_value or status_value == "N/A") and job_run_row:
        run_status = job_run_row.get("status")
        if run_status:
            status_value = str(run_status)

    return PipelineStatusViewResponse(
        job_name=job_name_value,
        status=status_value or "N/A",
        last_update_at=last_update_at,
        duration_text=duration_text,
        started_at=started_at,
        finished_at=finished_at,
    )
