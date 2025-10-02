from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytest
from psycopg.errors import UniqueViolation

from domain.enums import Step
from services.base import ServiceResult, StepJobOutcome, run_step_job


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> None:  # pragma: no cover - compatibilidade com interface real
        return None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeConnection:
    def __init__(self) -> None:
        self.cursors: list[_FakeCursor] = []
        self.commits: int = 0
        self.rollbacks: int = 0
        self.closed: bool = False

    def cursor(
        self, *args, **kwargs
    ) -> _FakeCursor:  # pragma: no cover - simples encaminhamento
        cursor = _FakeCursor()
        self.cursors.append(cursor)
        return cursor

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def _run_step_env(monkeypatch):
    from services import base as base_module

    connection = _FakeConnection()

    monkeypatch.setattr(
        base_module.psycopg,
        "connect",
        lambda dsn, autocommit=False: connection,
    )

    class _Settings(SimpleNamespace):
        pass

    monkeypatch.setattr(
        base_module,
        "get_database_settings",
        lambda: _Settings(dsn="postgresql://fake"),
    )
    monkeypatch.setattr(
        base_module,
        "get_principal_settings",
        lambda: _Settings(
            tenant_id=None,
            matricula="svc-user",
            nome=None,
            email=None,
            perfil=None,
        ),
    )
    monkeypatch.setattr(base_module, "bind_session_by_matricula", lambda *_: None)
    monkeypatch.setattr(base_module, "_retry_backoff", lambda *_: None)

    handle_ref: dict[str, SimpleNamespace] = {}

    @contextmanager
    def fake_job_run(conn, job_name, payload=None):
        handle = SimpleNamespace(
            tenant_id="tenant",
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            id="job-id",
            status=None,
            error_message=None,
        )
        handle_ref["handle"] = handle
        yield handle

    monkeypatch.setattr(base_module, "job_run", fake_job_run)

    events = {"start": [], "finish": [], "error": []}

    def fake_start_job_step(
        conn, job, step_code, etapa_id=None, message=None, data=None
    ):
        events["start"].append(
            {
                "step_code": step_code,
                "message": message,
                "data": data,
            }
        )

    def fake_finish_job_step(conn, job, step_code, status, message=None, data=None):
        events["finish"].append(
            {
                "step_code": step_code,
                "status": status,
                "message": message,
                "data": data,
            }
        )

    def fake_finish_job_step_error(conn, job, step_code, message=None, data=None):
        events["error"].append(
            {
                "step_code": step_code,
                "message": message,
                "data": data,
            }
        )

    monkeypatch.setattr(base_module, "start_job_step", fake_start_job_step)
    monkeypatch.setattr(base_module, "finish_job_step", fake_finish_job_step)
    monkeypatch.setattr(
        base_module, "finish_job_step_error", fake_finish_job_step_error
    )

    return SimpleNamespace(connection=connection, events=events, handle_ref=handle_ref)


def test_run_step_job_logs_success(_run_step_env) -> None:
    env = _run_step_env

    def callback(context):
        return StepJobOutcome(
            status="skipped",
            data={"capturados": 5},
            info_update={"summary": "Concluído"},
        )

    result = run_step_job(
        step=Step.ETAPA_1,
        job_name=Step.ETAPA_1,
        callback=callback,
        user_id="user",
    )

    assert isinstance(result, ServiceResult)
    assert env.events["start"] == [
        {"step_code": "ETAPA_1", "message": None, "data": None}
    ]
    assert env.events["error"] == []

    assert len(env.events["finish"]) == 1
    finish_event = env.events["finish"][0]
    assert finish_event["status"] == "SKIPPED"
    assert finish_event["message"] == "Concluído"
    assert finish_event["data"] == {
        "capturados": 5,
        "info_update": {"summary": "Concluído"},
    }
    assert env.handle_ref["handle"].status == "SKIPPED"


def test_run_step_job_logs_failure(_run_step_env) -> None:
    env = _run_step_env

    def callback(_context):
        raise ValueError("Falhou geral")

    with pytest.raises(ValueError):
        run_step_job(
            step=Step.ETAPA_2,
            job_name=Step.ETAPA_2,
            callback=callback,
        )

    assert len(env.events["start"]) == 1
    assert env.events["finish"] == []
    assert len(env.events["error"]) == 1
    error_event = env.events["error"][0]
    assert error_event["message"] == "Falhou geral"
    assert error_event["data"]["attempt"] == 1
    assert env.handle_ref["handle"].status == "ERROR"


def test_run_step_job_retries_unique_violation(_run_step_env) -> None:
    env = _run_step_env
    attempts = {"count": 0}

    def callback(_context):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise UniqueViolation("dup")
        return StepJobOutcome(
            status="SUCCESS",
            data={"ok": True},
        )

    result = run_step_job(
        step=Step.ETAPA_3,
        job_name=Step.ETAPA_3,
        callback=callback,
    )

    assert isinstance(result, ServiceResult)
    assert attempts["count"] == 3
    assert len(env.events["start"]) == 3
    assert len(env.events["error"]) == 2
    assert env.events["error"][0]["data"]["attempt"] == 1
    assert env.events["error"][1]["data"]["attempt"] == 2
    assert len(env.events["finish"]) == 1
    assert env.events["finish"][0]["status"] == "SUCCESS"
    assert env.handle_ref["handle"].status == "SUCCESS"
