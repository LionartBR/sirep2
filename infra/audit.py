from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Optional

from psycopg import AsyncConnection, Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from shared.auth import is_authorized_login


@dataclass(slots=True)
class JobRunHandle:
    """Dados de controle de um registro em ``audit.job_run``."""

    tenant_id: str
    started_at: datetime
    id: str
    status: Optional[str] = None
    error_message: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Retorna uma representação compatível com o contrato legado."""

        return {
            "tenant_id": self.tenant_id,
            "started_at": self.started_at,
            "id": self.id,
        }


@dataclass(slots=True)
class JobStepHandle:
    """Dados de controle de um registro em ``audit.job_step``."""

    tenant_id: str
    job_started_at: datetime
    job_id: str
    step_code: str
    etapa_id: Optional[str] = None
    status: str = "SUCCESS"
    message: Optional[str] = None
    data: Optional[dict[str, Any]] = None


_VALID_STEP_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "ERROR", "SKIPPED"}


def _normalize_step_status(value: Optional[str], default: str = "SUCCESS") -> str:
    """Normaliza o status informado para um dos valores aceitos."""

    if value is None:
        return default

    status = value.strip().upper()
    if not status:
        return default

    if status in _VALID_STEP_STATUSES:
        return status

    if status.startswith("SUCC"):
        return "SUCCESS"
    if status.startswith("ERR") or status.startswith("FAIL"):
        return "ERROR"
    if status.startswith("SKIP"):
        return "SKIPPED"
    if status.startswith("PEN"):
        return "PENDING"
    if status.startswith("RUN"):
        return "RUNNING"
    return default


def _normalize_message(message: Optional[str]) -> Optional[str]:
    """Limpa e limita mensagens para armazenamento em auditoria."""

    if message is None:
        return None

    cleaned = message.strip()
    if not cleaned:
        return None

    return cleaned[:2000]


def _json_or_none(data: Optional[dict[str, Any]]) -> Optional[Json]:
    """Converte o dicionário informado em JSON aceitável pelo banco."""

    if data is None:
        return None
    return Json(data)


def start_job_step(
    conn: Connection,
    *,
    job: JobRunHandle,
    step_code: str,
    etapa_id: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> JobStepHandle:
    """Registra o início (ou reinício) da execução de uma etapa."""

    normalized_message = _normalize_message(message)
    json_data = _json_or_none(data)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.job_step
              (tenant_id, job_started_at, job_id, step_code, etapa_id, status, started_at, message, data, user_id)
            VALUES
              (%s, %s, %s, %s, %s, 'RUNNING', now(), %s, %s, app.current_user_id())
            ON CONFLICT (tenant_id, job_started_at, job_id, step_code) DO UPDATE
               SET status = 'RUNNING',
                   started_at = now(),
                   finished_at = NULL,
                   etapa_id = COALESCE(EXCLUDED.etapa_id, audit.job_step.etapa_id),
                   message = COALESCE(EXCLUDED.message, audit.job_step.message),
                   data = COALESCE(EXCLUDED.data, audit.job_step.data),
                   user_id = app.current_user_id()
            """,
            (
                job.tenant_id,
                job.started_at,
                job.id,
                step_code,
                etapa_id,
                normalized_message,
                json_data,
            ),
        )

    return JobStepHandle(
        tenant_id=job.tenant_id,
        job_started_at=job.started_at,
        job_id=job.id,
        step_code=step_code,
        etapa_id=etapa_id,
        status="SUCCESS",
        message=normalized_message,
        data=data,
    )


def finish_job_step(
    conn: Connection,
    *,
    job: JobRunHandle,
    step_code: str,
    status: str,
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Atualiza o status final de uma etapa do job."""

    final_status = _normalize_step_status(status)
    normalized_message = _normalize_message(message)
    json_data = _json_or_none(data)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.job_step
               SET status = %s,
                   finished_at = now(),
                   message = COALESCE(%s, audit.job_step.message),
                   data = COALESCE(%s, audit.job_step.data),
                   user_id = app.current_user_id()
             WHERE tenant_id = %s
               AND job_started_at = %s
               AND job_id = %s
               AND step_code = %s
            """,
            (
                final_status,
                normalized_message,
                json_data,
                job.tenant_id,
                job.started_at,
                job.id,
                step_code,
            ),
        )


def finish_job_step_ok(
    conn: Connection,
    *,
    job: JobRunHandle,
    step_code: str,
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Convenience wrapper para etapas finalizadas com sucesso."""

    finish_job_step(
        conn,
        job=job,
        step_code=step_code,
        status="SUCCESS",
        message=message,
        data=data,
    )


def finish_job_step_error(
    conn: Connection,
    *,
    job: JobRunHandle,
    step_code: str,
    message: Optional[str],
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Convenience wrapper para etapas finalizadas com erro."""

    finish_job_step(
        conn,
        job=job,
        step_code=step_code,
        status="ERROR",
        message=message,
        data=data,
    )


@contextmanager
def job_step(
    conn: Connection,
    *,
    job: JobRunHandle,
    step_code: str,
    etapa_id: Optional[str] = None,
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> Iterator[JobStepHandle]:
    """Context manager para controlar ``audit.job_step`` automaticamente."""

    handle = start_job_step(
        conn,
        job=job,
        step_code=step_code,
        etapa_id=etapa_id,
        message=message,
        data=data,
    )

    try:
        yield handle
    except Exception as exc:  # pragma: no cover - tratado em testes específicos
        err = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        finish_job_step_error(
            conn,
            job=job,
            step_code=step_code,
            message=err,
            data=handle.data,
        )
        raise
    else:
        finish_job_step(
            conn,
            job=job,
            step_code=step_code,
            status=handle.status,
            message=handle.message,
            data=handle.data,
        )


def bind_session_by_matricula(conn: Connection, matricula: str) -> None:
    """Configura a sessão autenticando a matrícula informada."""

    matricula = (matricula or "").strip()
    if not matricula:
        raise ValueError("A matrícula do usuário é obrigatória para vincular a sessão.")

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT app.login_matricula(%s::citext)", (matricula,))
        row = cur.fetchone()
        if not is_authorized_login(row):
            raise PermissionError("Usuário não autorizado.")
        cur.execute("SET TIME ZONE 'America/Sao_Paulo'")


@contextmanager
def job_run(
    conn: Connection,
    job_name: str,
    payload: Optional[dict[str, Any]] = None,
) -> JobRunHandle:
    """Registra o início e o término de um ``audit.job_run``."""

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO audit.job_run (tenant_id, job_name, status, payload, user_id)
            VALUES (app.current_tenant_id(), %s, 'RUNNING', %s, app.current_user_id())
            RETURNING tenant_id, started_at, id
            """,
            (job_name, Json(payload or {})),
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError("Não foi possível registrar a execução do job.")

    handle = JobRunHandle(
        tenant_id=str(row["tenant_id"]),
        started_at=row["started_at"],
        id=str(row["id"]),
    )

    try:
        yield handle
        final_status = (handle.status or "SUCCESS").strip().upper() or "SUCCESS"
        if final_status not in {"SUCCESS", "ERROR", "SKIPPED"}:
            final_status = "SUCCESS" if final_status.startswith("S") else "ERROR"

        mensagem = (handle.error_message or "").strip() or None
        if mensagem and len(mensagem) > 2000:
            mensagem = mensagem[:2000]

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audit.job_run
                   SET status = %s,
                       finished_at = now(),
                       error_msg = %s
                 WHERE tenant_id = %s
                   AND started_at = %s
                   AND id = %s
                """,
                (final_status, mensagem, handle.tenant_id, handle.started_at, handle.id),
            )
    except Exception as exc:  # pragma: no cover - fluxo de erro exercitado em testes
        err = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE audit.job_run
                   SET status = 'ERROR',
                       finished_at = now(),
                       error_msg = %s
                 WHERE tenant_id = %s
                   AND started_at = %s
                   AND id = %s
                """,
                (err, handle.tenant_id, handle.started_at, handle.id),
            )
        raise


def log_event(
    conn: Connection,
    *,
    entity: Optional[str],
    entity_id: Optional[str],
    event_type: str,
    severity: str = "info",
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Insere um registro de auditoria na tabela ``audit.evento``."""

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit.evento
              (tenant_id, event_time, entity, entity_id, event_type, severity, message, data, user_id)
            VALUES
              (app.current_tenant_id(), now(), %s, %s, %s, %s, %s, %s, app.current_user_id())
            """,
            (entity, entity_id, event_type, severity, message, Json(data or {})),
        )


async def bind_session_by_matricula_async(aconn: AsyncConnection, matricula: str) -> None:
    """Versão assíncrona de :func:`bind_session_by_matricula`."""

    matricula = (matricula or "").strip()
    if not matricula:
        raise ValueError("A matrícula do usuário é obrigatória para vincular a sessão.")

    async with aconn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT app.login_matricula(%s::citext)", (matricula,))
        row = await cur.fetchone()
        if not is_authorized_login(row):
            raise PermissionError("Usuário não autorizado.")
        await cur.execute("SET TIME ZONE 'America/Sao_Paulo'")


class JobRunAsync:
    """Context manager assíncrono para controle de ``audit.job_run``."""

    def __init__(self, aconn: AsyncConnection, job_name: str, payload: Optional[dict[str, Any]] = None) -> None:
        self.conn = aconn
        self.job_name = job_name
        self.payload = payload or {}
        self.handle: Optional[JobRunHandle] = None

    async def __aenter__(self) -> JobRunHandle:
        async with self.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO audit.job_run (tenant_id, job_name, status, payload, user_id)
                VALUES (app.current_tenant_id(), %s, 'RUNNING', %s, app.current_user_id())
                RETURNING tenant_id, started_at, id
                """,
                (self.job_name, Json(self.payload)),
            )
            row = await cur.fetchone()

        if not row:
            raise RuntimeError("Não foi possível registrar a execução do job.")

        self.handle = JobRunHandle(
            tenant_id=str(row["tenant_id"]),
            started_at=row["started_at"],
            id=row["id"],
        )
        return self.handle

    async def __aexit__(self, exc_type, exc, tb) -> Optional[bool]:
        assert self.handle is not None
        tenant_id, started_at, job_id = (
            self.handle.tenant_id,
            self.handle.started_at,
            self.handle.id,
        )

        if exc is not None:
            err = "".join(traceback.format_exception_only(exc_type, exc)).strip()
            async with self.conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE audit.job_run
                       SET status = 'ERROR', finished_at = now(), error_msg = %s
                     WHERE tenant_id = %s AND started_at = %s AND id = %s
                    """,
                    (err, tenant_id, started_at, job_id),
                )
            return None

        final_status = (self.handle.status or "SUCCESS").strip().upper() or "SUCCESS"
        if final_status not in {"SUCCESS", "ERROR", "SKIPPED"}:
            final_status = "SUCCESS" if final_status.startswith("S") else "ERROR"

        mensagem = (self.handle.error_message or "").strip() or None
        if mensagem and len(mensagem) > 2000:
            mensagem = mensagem[:2000]

        async with self.conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE audit.job_run
                   SET status = %s, finished_at = now(), error_msg = %s
                 WHERE tenant_id = %s AND started_at = %s AND id = %s
                """,
                (final_status, mensagem, tenant_id, started_at, job_id),
            )
        return None


async def log_event_async(
    aconn: AsyncConnection,
    *,
    entity: Optional[str],
    entity_id: Optional[str],
    event_type: str,
    severity: str = "info",
    message: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
) -> None:
    """Versão assíncrona de :func:`log_event`."""

    async with aconn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO audit.evento
              (tenant_id, event_time, entity, entity_id, event_type, severity, message, data, user_id)
            VALUES
              (app.current_tenant_id(), now(), %s, %s, %s, %s, %s, %s, app.current_user_id())
            """,
            (entity, entity_id, event_type, severity, message, Json(data or {})),
        )


__all__ = [
    "JobRunHandle",
    "JobStepHandle",
    "JobRunAsync",
    "bind_session_by_matricula",
    "bind_session_by_matricula_async",
    "finish_job_step",
    "finish_job_step_error",
    "finish_job_step_ok",
    "job_run",
    "job_step",
    "log_event",
    "log_event_async",
    "start_job_step",
]
