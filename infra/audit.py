from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
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
    """Dados de controle da execução de uma etapa do ``audit.job_run``."""

    tenant_id: str
    job_started_at: datetime
    job_id: str
    step_code: str
    etapa_id: Optional[str] = None
    status: str = "SUCCESS"
    message: Optional[str] = None
    data: Optional[dict[str, Any]] = None


_VALID_STEP_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "ERROR", "SKIPPED"}


_UNSET = object()


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


def _utcnow_iso() -> str:
    """Retorna o timestamp atual em formato ISO 8601 no fuso UTC."""

    return datetime.now(timezone.utc).isoformat()


def _sanitize_payload(value: Any) -> Any:
    """Normaliza estruturas para garantir serialização JSON segura."""

    if isinstance(value, dict):
        return {str(key): _sanitize_payload(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return value


def _load_job_payload(conn: Connection, job: JobRunHandle) -> dict[str, Any]:
    """Obtém e prepara o payload atual associado ao job informado."""

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT payload
              FROM audit.job_run
             WHERE tenant_id = %s
               AND started_at = %s
               AND id = %s
             FOR UPDATE
            """,
            (job.tenant_id, job.started_at, job.id),
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError("Registro de job_run não encontrado para atualizar etapas.")

    payload = row.get("payload") or {}
    if not isinstance(payload, dict):
        return {}
    return dict(payload)


def _persist_job_payload(
    conn: Connection,
    job: JobRunHandle,
    payload: dict[str, Any],
    *,
    status: Optional[str] = _UNSET,
    error_message: Optional[str] = _UNSET,
) -> None:
    """Atualiza o payload do job (e, opcionalmente, status e erro)."""

    update_columns = ["payload = %s"]
    params: list[Any] = [Json(_sanitize_payload(payload))]

    if status is not _UNSET:
        update_columns.append("status = %s")
        params.append(status)

    if error_message is not _UNSET:
        update_columns.append("error_msg = %s")
        params.append(error_message)

    params.extend([job.tenant_id, job.started_at, job.id])

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audit.job_run
               SET {set_clause}
             WHERE tenant_id = %s
               AND started_at = %s
               AND id = %s
            """.format(set_clause=", ".join(update_columns)),
            tuple(params),
        )


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
    payload = _load_job_payload(conn, job)

    steps = payload.setdefault("steps", {})
    step_entry = steps.get(step_code, {})
    step_entry.update(
        {
            "status": "RUNNING",
            "started_at": _utcnow_iso(),
        }
    )
    if normalized_message is not None:
        step_entry["message"] = normalized_message
    elif "message" in step_entry:
        step_entry.pop("message")

    if data is not None:
        step_entry["data"] = data
    elif "data" in step_entry:
        step_entry.pop("data")
    if etapa_id is not None:
        step_entry["etapa_id"] = etapa_id
    step_entry.pop("finished_at", None)
    step_entry.pop("error", None)
    steps[step_code] = step_entry
    payload["current_step"] = step_code

    _persist_job_payload(conn, job, payload, status="RUNNING", error_message=None)

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
    payload = _load_job_payload(conn, job)

    steps = payload.setdefault("steps", {})
    step_entry = steps.get(step_code, {})
    step_entry["status"] = final_status
    step_entry["finished_at"] = _utcnow_iso()
    if normalized_message is not None:
        step_entry["message"] = normalized_message
    if data is not None:
        step_entry["data"] = data
    elif "data" in step_entry and data is None:
        step_entry.pop("data")

    if final_status == "ERROR" and normalized_message:
        step_entry["error"] = normalized_message
    elif "error" in step_entry and final_status != "ERROR":
        step_entry.pop("error")

    steps[step_code] = step_entry

    error_message = normalized_message if final_status == "ERROR" else None
    _persist_job_payload(conn, job, payload, error_message=error_message)


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
    """Context manager que registra início e fim da etapa dentro do ``job_run``."""

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
