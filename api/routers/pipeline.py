from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..models import PipelineStartPayload, PipelineStateResponse
from services.orchestrator import (
    PipelineAlreadyRunningError,
    PipelineOrchestrator,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def get_orchestrator(request: Request) -> PipelineOrchestrator:
    """Retrieve the orchestrator stored on the FastAPI app."""

    orchestrator = getattr(request.app.state, "pipeline_orchestrator", None)
    if orchestrator is None:
        orchestrator = PipelineOrchestrator()
        request.app.state.pipeline_orchestrator = orchestrator
    return orchestrator


@router.post("/start", response_model=PipelineStateResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_pipeline(
    payload: PipelineStartPayload | None = None,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> PipelineStateResponse:
    """Accept a request to trigger the Gestão da Base pipeline."""

    payload = payload or PipelineStartPayload()
    try:
        state = await orchestrator.start(matricula=payload.matricula, senha=payload.senha)
    except PipelineAlreadyRunningError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PipelineStateResponse.from_state(state)


@router.get("/state", response_model=PipelineStateResponse)
async def get_pipeline_state(
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> PipelineStateResponse:
    """Return the current state of the pipeline."""

    state = orchestrator.get_state()
    return PipelineStateResponse.from_state(state)
