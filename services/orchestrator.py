from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from domain.pipeline import PipelineState, PipelineStatus
from services.gestao_base.service import GestaoBaseService

logger = logging.getLogger(__name__)


class PipelineAlreadyRunningError(RuntimeError):
    """Raised when attempting to start an already running pipeline."""


class PipelineOrchestrator:
    """Coordinates execution of the Gestão da Base pipeline."""

    def __init__(self, service: Optional[GestaoBaseService] = None) -> None:
        self._service = service or GestaoBaseService()
        self._state = PipelineState()
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task[None]] = None

    def get_state(self) -> PipelineState:
        """Return a snapshot of the current state."""

        return self._state.copy()

    async def start(
        self,
        matricula: Optional[str] = None,
        senha: Optional[str] = None,
    ) -> PipelineState:
        """Trigger pipeline execution if it is not running."""

        async with self._lock:
            if self._state.status == PipelineStatus.RUNNING:
                raise PipelineAlreadyRunningError("Pipeline já está em execução.")

            now = datetime.now(timezone.utc)
            self._state.status = PipelineStatus.RUNNING
            self._state.started_at = now
            self._state.finished_at = None
            self._state.message = "Execução iniciada"

            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._execute_pipeline(matricula, senha))
            return self._state.copy()

    async def _execute_pipeline(
        self,
        matricula: Optional[str],
        senha: Optional[str],
    ) -> None:
        try:
            result = await asyncio.to_thread(self._service.execute, matricula, senha)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Falha ao executar pipeline de Gestão da Base")
            await self._finalize(PipelineStatus.FAILED, "Erro ao executar pipeline.")
            return

        outcome = result.outcome
        status_value = (outcome.status or "").strip().upper()

        if status_value in {"FAILED", "FAIL", "ERROR"}:
            status = PipelineStatus.FAILED
        elif status_value in {"SUCCESS", "SUCCEEDED", "SKIPPED", ""}:
            status = PipelineStatus.SUCCEEDED
        elif status_value.startswith("FAIL") or status_value.startswith("ERR"):
            status = PipelineStatus.FAILED
        else:
            status = PipelineStatus.SUCCEEDED

        summary: Optional[str] = None
        if outcome.info_update:
            summary = outcome.info_update.get("summary") or outcome.info_update.get(
                "mensagem"
            )

        if status is PipelineStatus.FAILED:
            fallback_message = "Pipeline finalizada com erro."
        else:
            fallback_message = "Pipeline concluída com sucesso."

        message = summary or fallback_message
        await self._finalize(status, message)

    async def _finalize(self, status: PipelineStatus, message: Optional[str]) -> None:
        async with self._lock:
            self._state.status = status
            self._state.finished_at = datetime.now(timezone.utc)
            self._state.message = message
            self._task = None


__all__ = ["PipelineAlreadyRunningError", "PipelineOrchestrator"]
