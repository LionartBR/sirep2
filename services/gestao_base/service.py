from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from domain.enums import Step
from infra.config import settings
from infra.runtime_credentials import (
    get_gestao_base_password,
    set_gestao_base_password,
)
from services.base import (
    ServiceResult,
    StepJobContext,
    StepJobOutcome,
    run_step_job,
)

from .audit import GestaoBaseAuditManager
from .collectors import DryRunCollector, GestaoBaseCollector, TerminalCollector
from .models import ProgressCallback
from .persistence import format_summary, persist_rows
from .portal import portal_po_provider

logger = logging.getLogger(__name__)


class GestaoBaseService:
    """Executa as etapas 1–4 da Gestão da Base utilizando a lógica da E555/E527."""

    def __init__(
        self, portal_provider: Optional[Callable[[], List[dict]]] = None
    ) -> None:
        self.portal_provider = portal_provider or (
            portal_po_provider if not settings.DRY_RUN else None
        )

    def _collector(self, senha: Optional[str]) -> Optional[GestaoBaseCollector]:
        if settings.DRY_RUN:
            return DryRunCollector()

        provided = (senha or "").strip()
        if provided:
            set_gestao_base_password(provided)
            resolved = provided
        else:
            resolved = get_gestao_base_password()

        if not resolved:
            logger.warning(
                "Senha da Gestão da Base não disponível; execução será interrompida."
            )
            return None

        return TerminalCollector(resolved, self.portal_provider)

    def execute(
        self,
        matricula: Optional[str] = None,
        senha: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ServiceResult:
        """Executa a captura de Gestão da Base e persiste os registros."""

        def _run(context: StepJobContext) -> StepJobOutcome:
            collector = self._collector(senha)
            if collector is None:
                return StepJobOutcome(
                    data={"error": "Senha da Gestão da Base não configurada."},
                    status="FAILED",
                    info_update={"summary": "Execução bloqueada por falta de senha"},
                )

            if progress_callback:
                progress_callback(12.0, None, "Captura real da Gestão da Base iniciada")

            audit_manager = GestaoBaseAuditManager(context)
            start_payload: Optional[dict[str, Any]] = None
            if matricula:
                start_payload = {"matricula": matricula}
            audit_manager.pipeline_started(start_payload)

            hooks = audit_manager.create_stage_hooks()

            try:
                data = collector.collect(
                    progress_callback,
                    audit_hooks=hooks,
                )
                resultado = persist_rows(context, data, progress_callback)
            except Exception as exc:
                context.db.rollback()
                audit_manager.pipeline_failed(exc)
                raise

            summary = format_summary(resultado)
            audit_manager.pipeline_finished(resultado)
            return StepJobOutcome(data=resultado, info_update={"summary": summary})

        return run_step_job(
            step=Step.ETAPA_1,
            job_name="gestao_base",
            callback=_run,
            user_id=matricula,
        )


class GestaoBaseNoOpService:
    """Serviço auxiliar para etapas 2-4 que já são cobertas pela captura consolidada."""

    def __init__(self, step: Step) -> None:
        self.step = step

    def execute(self) -> ServiceResult:
        def _run(_: StepJobContext) -> StepJobOutcome:
            return StepJobOutcome(
                data={"mensagem": "Etapa contemplada na captura consolidada"},
                info_update={"summary": "Nenhuma ação necessária"},
            )

        return run_step_job(step=self.step, job_name=self.step, callback=_run)
