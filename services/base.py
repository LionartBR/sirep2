from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import psycopg
from psycopg.errors import UniqueViolation

from domain.enums import Step
from infra.audit import bind_session_by_matricula, job_run
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
    job_run_id: str,
    job_run_started_at: datetime,
) -> StepJobContext:
    """Inicializa o contexto com os repositórios necessários."""

    plans = PlansRepository(connection)
    events = EventsRepository(connection)
    return StepJobContext(
        db=connection,
        plans=plans,
        events=events,
        job_run_id=job_run_id,
        job_run_started_at=job_run_started_at,
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

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED"
            )

        bind_session_by_matricula(connection, principal.matricula)

        with job_run(
            connection,
            job_name=str(job_name),
            payload=job_payload,
        ) as job_handle:
            attempt = 0
            while True:
                attempt += 1
                try:
                    _configure_transaction(connection, principal=principal)
                    context = _prepare_context(
                        connection,
                        job_run_id=job_handle.id,
                        job_run_started_at=job_handle.started_at,
                    )
                    outcome = callback(context)
                    final_status = outcome.status.upper() if outcome.status else "SUCCESS"
                    if final_status not in {"SUCCESS", "ERROR", "SKIPPED"}:
                        final_status = (
                            "ERROR" if final_status.startswith("FAIL") else "SUCCESS"
                        )
                    job_handle.status = final_status
                    job_handle.error_message = None
                    connection.commit()
                    return ServiceResult(step=step, outcome=outcome)
                except UniqueViolation as exc:
                    logger.warning(
                        "Unique violation durante execução da etapa %s (tentativa %s/%s)",
                        step,
                        attempt,
                        max_retries,
                    )
                    connection.rollback()
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
                    raise
    finally:
        connection.close()


__all__ = [
    "ServiceResult",
    "StepJobContext",
    "StepJobOutcome",
    "run_step_job",
]
