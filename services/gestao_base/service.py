from __future__ import annotations

import logging
from typing import Callable, List, Optional

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

            data = collector.collect(progress_callback)
            resultado = persist_rows(context, data, progress_callback)
            summary = format_summary(resultado)
            return StepJobOutcome(data=resultado, info_update={"summary": summary})

        return run_step_job(
            step=Step.ETAPA_1,
            job_name=Step.ETAPA_1,
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
