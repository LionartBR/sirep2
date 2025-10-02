from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import psycopg
from psycopg.errors import UniqueViolation

from domain.enums import Step
from infra.audit import (
    bind_session_by_matricula,
    JobRunHandle,
    finish_job_step,
    finish_job_step_error,
    job_run,
    start_job_step,
)
from infra.repositories import EventsRepository, PlansRepository
from shared.config import get_database_settings, get_principal_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StepJobOutcome:
    """Resultado produzido pelo callback de uma etapa do pipeline."""

    data: Optional[dict[str, Any]] = None
    status: str = "SUCCESS"
    info_update: Optional[dict[str, Any]] = None


@dataclass(slots=True)
class ServiceResult:
    """Representa o resultado final de uma execução de etapa."""

    step: Step
    outcome: StepJobOutcome


@dataclass(slots=True)
class StepJobContext:
    """Contêiner com dependências de persistência utilizadas nas etapas."""

    db: psycopg.Connection
    plans: PlansRepository
    events: EventsRepository
    job_run_id: str
    job_run_started_at: datetime
    job: JobRunHandle


StepJobCallback = Callable[[StepJobContext], StepJobOutcome]


@dataclass(slots=True)
class Principal:
    """Informações necessárias para definir o contexto da sessão no banco."""

    matricula: str


def _resolve_principal(
    tenant_override: Optional[str],
    user_override: Optional[str],
) -> Principal:
    """Determina o usuário do aplicativo a partir do ambiente."""

    settings = get_principal_settings()
    matricula = (user_override or settings.matricula or "").strip()

    if tenant_override:
        logger.debug(
            "Identificador de tenant ignorado (controlado pelo app.login_matricula)."
        )

    if not matricula:
        raise RuntimeError(
            "Usuário de aplicação não configurado. Informe 'APP_USER_REGISTRATION', "
            "'APP_USER_ID' ou 'USER_ID' no ambiente para executar a pipeline."
        )

    return Principal(matricula=matricula)


def _prepare_context(
    connection: psycopg.Connection,
    *,
    job: JobRunHandle,
) -> StepJobContext:
    """Inicializa o contexto com os repositórios necessários."""

    plans = PlansRepository(connection)
    events = EventsRepository(connection)
    return StepJobContext(
        db=connection,
        plans=plans,
        events=events,
        job_run_id=job.id,
        job_run_started_at=job.started_at,
        job=job,
    )


def _configure_transaction(
    connection: psycopg.Connection,
    *,
    principal: Principal,
) -> None:
    """Garante que a transação esteja autenticada e parametrizada."""

    bind_session_by_matricula(connection, principal.matricula)
    with connection.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '30s'")


def _retry_backoff(attempt: int) -> None:
    """Aguarda um pequeno intervalo exponencial antes de nova tentativa."""

    delay = min(2.0, 0.2 * (2 ** max(attempt - 1, 0)))
    logger.debug("Esperando %.2fs para nova tentativa após unique_violation", delay)
    time.sleep(delay)


def _normalize_job_status(status: Optional[str]) -> str:
    """Normaliza o status final do job para valores aceitos pelo audit."""

    if status is None:
        return "SUCCESS"

    normalized = status.strip().upper()
    if not normalized:
        return "SUCCESS"

    if normalized in {"SUCCESS", "ERROR", "SKIPPED"}:
        return normalized

    if normalized.startswith("S"):
        return "SUCCESS"
    if normalized.startswith("K"):
        return "SKIPPED"
    if normalized.startswith("E") or normalized.startswith("F"):
        return "ERROR"
    return "SUCCESS"


def _resolve_step_code(step: Step | str) -> str:
    """Extrai o código textual da etapa."""

    if isinstance(step, Step):
        return step.value
    return str(step)


def _summary_from_outcome(outcome: StepJobOutcome) -> Optional[str]:
    """Obtém um resumo amigável da execução da etapa."""

    info = outcome.info_update or {}
    if isinstance(info, dict):
        summary = info.get("summary")
        if summary is not None:
            return str(summary)
    return None


def _data_from_outcome(outcome: StepJobOutcome) -> Optional[dict[str, Any]]:
    """Compila os dados relevantes da etapa para auditoria."""

    payload: dict[str, Any] = {}
    if outcome.data:
        payload.update(outcome.data)
    if outcome.info_update:
        payload.setdefault("info_update", outcome.info_update)
    return payload or None


def run_step_job(
    *,
    step: Step,
    job_name: str,
    callback: StepJobCallback,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    job_payload: Optional[dict[str, Any]] = None,
    max_retries: int = 3,
) -> ServiceResult:
    """Executa o callback dentro de uma transação configurada com RLS."""

    settings = get_database_settings()
    principal = _resolve_principal(tenant_id, user_id)

    connection = psycopg.connect(settings.dsn, autocommit=False)

    service_result: Optional[ServiceResult] = None
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED"
            )

        bind_session_by_matricula(connection, principal.matricula)

        try:
            with job_run(
                connection,
                job_name=str(job_name),
                payload=job_payload,
            ) as job_handle:
                attempt = 0
                step_code = _resolve_step_code(step)
                while True:
                    attempt += 1
                    try:
                        start_job_step(
                            connection,
                            job=job_handle,
                            step_code=step_code,
                        )
                        connection.commit()
                        _configure_transaction(connection, principal=principal)
                        context = _prepare_context(connection, job=job_handle)
                        outcome = callback(context)
                        final_status = _normalize_job_status(outcome.status)
                        job_handle.status = final_status
                        job_handle.error_message = None
                        finish_job_step(
                            connection,
                            job=job_handle,
                            step_code=step_code,
                            status=final_status,
                            message=_summary_from_outcome(outcome),
                            data=_data_from_outcome(outcome),
                        )
                        connection.commit()
                        service_result = ServiceResult(step=step, outcome=outcome)
                        break
                    except UniqueViolation as exc:
                        logger.warning(
                            "Unique violation durante execução da etapa %s (tentativa %s/%s)",
                            step,
                            attempt,
                            max_retries,
                        )
                        connection.rollback()
                        finish_job_step_error(
                            connection,
                            job=job_handle,
                            step_code=step_code,
                            message=str(exc),
                            data={
                                "error": str(exc),
                                "exception_type": type(exc).__name__,
                                "attempt": attempt,
                            },
                        )
                        connection.commit()
                        if attempt >= max_retries:
                            job_handle.status = "ERROR"
                            job_handle.error_message = str(exc)
                            raise
                        _retry_backoff(attempt)
                        continue
                    except Exception as exc:
                        connection.rollback()
                        job_handle.status = "ERROR"
                        job_handle.error_message = str(exc)
                        finish_job_step_error(
                            connection,
                            job=job_handle,
                            step_code=step_code,
                            message=str(exc),
                            data={
                                "error": str(exc),
                                "exception_type": type(exc).__name__,
                                "attempt": attempt,
                            },
                        )
                        connection.commit()
                        raise
        except Exception:
            connection.commit()
            raise
        else:
            connection.commit()
            assert service_result is not None
            return service_result
    finally:
        connection.close()


__all__ = [
    "ServiceResult",
    "StepJobContext",
    "StepJobOutcome",
    "run_step_job",
]
