from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Json

from domain.enums import Step
from infra.repositories import EventsRepository, PlansRepository
from shared.config import get_database_settings

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
    tenant: Optional[str],
    usuario: Optional[str],
) -> None:
    """Configura o contexto de RLS e parâmetros locais da transação."""

    with connection.cursor() as cur:
        if tenant:
            cur.execute("SELECT app.set_tenant(%s)", (tenant,))
        if usuario:
            cur.execute("SELECT app.set_user(%s)", (usuario,))
        cur.execute("SET TIME ZONE 'America/Sao_Paulo'")
        cur.execute("SET LOCAL statement_timeout = '30s'")


def _insert_job_run(
    connection: psycopg.Connection,
    *,
    tenant: Optional[str],
    usuario: Optional[str],
    job_name: str,
    payload: Optional[dict[str, Any]] = None,
) -> tuple[str, datetime]:
    """Registra um novo job_run com status RUNNING e retorna os identificadores."""

    _configure_transaction(connection, tenant=tenant, usuario=usuario)
    with connection.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO audit.job_run (tenant_id, job_name, status, payload)
            VALUES (app.current_tenant_id(), %s, 'RUNNING', %s)
            RETURNING id, started_at
            """,
            (job_name, Json(payload or {})),
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError("Falha ao registrar job_run")

    connection.commit()
    return (str(row["id"]), row["started_at"])


def _finalize_job_run(
    connection: psycopg.Connection,
    *,
    tenant: Optional[str],
    usuario: Optional[str],
    job_run_id: str,
    started_at: datetime,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Atualiza o job_run com o status final e mensagem opcional."""

    _configure_transaction(connection, tenant=tenant, usuario=usuario)
    mensagem = (error_message or "").strip() or None
    if mensagem and len(mensagem) > 2000:
        mensagem = mensagem[:2000]

    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.job_run
               SET status = %s,
                   finished_at = now(),
                   error_msg = %s
             WHERE id = %s
               AND started_at = %s
            """,
            (status, mensagem, job_run_id, started_at),
        )


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
    tenant = tenant_id or os.getenv("TENANT_ID")
    usuario = user_id or os.getenv("APP_USER_ID") or os.getenv("USER_ID")

    connection = psycopg.connect(settings.dsn, autocommit=False)

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED"
            )

        job_run_id, started_at = _insert_job_run(
            connection,
            tenant=tenant,
            usuario=usuario,
            job_name=str(job_name),
            payload=job_payload,
        )

        attempt = 0
        while True:
            attempt += 1
            try:
                _configure_transaction(connection, tenant=tenant, usuario=usuario)
                context = _prepare_context(
                    connection, job_run_id=job_run_id, job_run_started_at=started_at
                )
                outcome = callback(context)
                final_status = outcome.status.upper() if outcome.status else "SUCCESS"
                if final_status not in {"SUCCESS", "ERROR"}:
                    final_status = "ERROR" if final_status.startswith("FAIL") else "SUCCESS"
                _finalize_job_run(
                    connection,
                    tenant=tenant,
                    usuario=usuario,
                    job_run_id=job_run_id,
                    started_at=started_at,
                    status=final_status,
                    error_message=None,
                )
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
                    _finalize_job_run(
                        connection,
                        tenant=tenant,
                        usuario=usuario,
                        job_run_id=job_run_id,
                        started_at=started_at,
                        status="ERROR",
                        error_message=str(exc),
                    )
                    connection.commit()
                    raise
                _retry_backoff(attempt)
                continue
            except Exception as exc:
                connection.rollback()
                _finalize_job_run(
                    connection,
                    tenant=tenant,
                    usuario=usuario,
                    job_run_id=job_run_id,
                    started_at=started_at,
                    status="ERROR",
                    error_message=str(exc),
                )
                connection.commit()
                raise
    finally:
        connection.close()


__all__ = [
    "ServiceResult",
    "StepJobContext",
    "StepJobOutcome",
    "run_step_job",
]
