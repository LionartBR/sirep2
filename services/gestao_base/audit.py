from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from infra.audit import (
    JobRunHandle,
    finish_job_step_error,
    finish_job_step_ok,
    log_event,
    start_job_step,
)

from services.base import StepJobContext

from .models import PipelineAuditHooks


def _normalize_data(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not payload:
        return {}
    return dict(payload)


@dataclass(slots=True)
class GestaoBaseAuditManager:
    """Controla a integração das etapas da Gestão da Base com o audit."""

    context: StepJobContext
    pipeline_name: str = "gestao_base"
    _hooks: Optional["_GestaoBaseStageHooks"] = None

    @property
    def job(self) -> JobRunHandle:
        return self.context.job

    def create_stage_hooks(self) -> "_GestaoBaseStageHooks":
        if self._hooks is None:
            self._hooks = _GestaoBaseStageHooks(self)
        return self._hooks

    def log_event(
        self,
        event_type: str,
        message: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
        *,
        severity: str = "info",
    ) -> None:
        payload = _normalize_data(data)
        payload.setdefault("job_id", self.job.id)
        log_event(
            self.context.db,
            entity="pipeline",
            entity_id=self.job.id,
            event_type=event_type,
            severity=severity,
            message=message,
            data=payload,
        )
        self.context.db.commit()

    def stage_metrics(self) -> Dict[str, dict[str, Any]]:
        hooks = self.create_stage_hooks()
        return {code: dict(values) for code, values in hooks.metrics.items()}

    def combined_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for values in self.stage_metrics().values():
            metrics.update(values)
        return metrics

    def merge_metrics(self, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        merged = self.combined_metrics()
        if extra:
            merged.update(extra)
        return merged

    def pipeline_started(
        self,
        data: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        default_message = message or "Gestão da Base iniciada"
        self.log_event("PIPELINE_STARTED", default_message, data)

    def pipeline_finished(
        self,
        extra_metrics: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        payload = self.merge_metrics(extra_metrics)
        default_message = message or "Gestão da Base concluída"
        self.log_event("PIPELINE_FINISHED", default_message, payload)

    def pipeline_failed(
        self,
        error: BaseException,
        *,
        data: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        text = message or "Falha na Gestão da Base"
        payload = self.merge_metrics(data)
        err_text = str(error).strip() or error.__class__.__name__
        payload.setdefault("error", err_text)
        self.log_event("PIPELINE_FAILED", text, payload, severity="error")


@dataclass(slots=True)
class _GestaoBaseStageHooks(PipelineAuditHooks):
    """Implementa ``PipelineAuditHooks`` integrando com o audit do banco."""

    manager: GestaoBaseAuditManager
    metrics: Dict[str, dict[str, Any]] = field(default_factory=dict)
    _active_steps: set[str] = field(default_factory=set)

    def stage_started(
        self,
        step_code: str,
        message: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        start_job_step(
            self.manager.context.db,
            job=self.manager.job,
            step_code=step_code,
            message=message,
            data=data,
        )
        self._active_steps.add(step_code)
        event_message = message or f"Etapa {step_code} iniciada"
        self.manager.log_event(
            f"{step_code}_STARTED",
            event_message,
            data,
        )

    def stage_finished(
        self,
        step_code: str,
        message: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        finish_job_step_ok(
            self.manager.context.db,
            job=self.manager.job,
            step_code=step_code,
            message=message,
            data=data,
        )
        self.metrics[step_code] = _normalize_data(data)
        self._active_steps.discard(step_code)
        event_message = message or f"Etapa {step_code} concluída"
        self.manager.log_event(
            f"{step_code}_FINISHED",
            event_message,
            data,
        )

    def stage_failed(
        self,
        step_code: str,
        error: str,
        *,
        data: Optional[dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> None:
        finish_job_step_error(
            self.manager.context.db,
            job=self.manager.job,
            step_code=step_code,
            message=error,
            data=data,
        )
        self._active_steps.discard(step_code)
        payload = _normalize_data(data)
        payload.setdefault("error", error)
        event_message = message or f"Etapa {step_code} falhou"
        self.manager.log_event(
            f"{step_code}_FAILED",
            event_message,
            payload,
            severity="error",
        )


__all__ = ["GestaoBaseAuditManager"]

