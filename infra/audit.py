from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

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
    "JobRunAsync",
    "bind_session_by_matricula",
    "bind_session_by_matricula_async",
    "job_run",
    "log_event",
    "log_event_async",
]
