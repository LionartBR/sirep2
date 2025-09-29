from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

import psycopg

from domain.enums import Step
from infra.repositories import EventsRepository, PlansRepository
from shared.config import get_database_settings


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


StepJobCallback = Callable[[StepJobContext], StepJobOutcome]


def _prepare_context(connection: psycopg.Connection) -> StepJobContext:
    """Inicializa o contexto com os repositórios necessários."""

    plans = PlansRepository(connection)
    events = EventsRepository(connection)
    return StepJobContext(db=connection, plans=plans, events=events)


def run_step_job(
    *,
    step: Step,
    job_name: str,
    callback: StepJobCallback,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
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
            if tenant:
                cur.execute("SELECT app.set_tenant(%s)", (tenant,))
            if usuario:
                cur.execute("SELECT app.set_user(%s)", (usuario,))

        context = _prepare_context(connection)
        outcome = callback(context)
        connection.commit()
        return ServiceResult(step=step, outcome=outcome)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = [
    "ServiceResult",
    "StepJobContext",
    "StepJobOutcome",
    "run_step_job",
]
