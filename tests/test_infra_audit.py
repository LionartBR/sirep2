from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from infra.audit import (
    JobRunHandle,
    job_step,
    start_job_step,
    finish_job_step,
)


def _make_cursor() -> tuple[MagicMock, MagicMock]:
    cursor = MagicMock()
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = None
    return cursor_cm, cursor


def _make_connection(*cursors: MagicMock) -> MagicMock:
    conn = MagicMock()
    conn.cursor.side_effect = list(cursors)
    return conn


def _job_handle() -> JobRunHandle:
    return JobRunHandle(
        tenant_id="tenant",
        started_at=datetime(2024, 1, 1, 12, 0, 0),
        id="job-id",
    )


def test_start_job_step_inserts_record() -> None:
    cursor_cm, cursor = _make_cursor()
    conn = _make_connection(cursor_cm)
    handle = _job_handle()

    step_handle = start_job_step(
        conn,
        job=handle,
        step_code="ETAPA_1",
        message="  Captura inicial  ",
        data={"total": 3},
    )

    conn.cursor.assert_called_once()
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO audit.job_step" in sql
    assert params[0] == handle.tenant_id
    assert params[3] == "ETAPA_1"
    assert params[5] == "Captura inicial"
    assert params[6].obj == {"total": 3}

    assert step_handle.step_code == "ETAPA_1"
    assert step_handle.message == "Captura inicial"
    assert step_handle.data == {"total": 3}


def test_finish_job_step_updates_status_and_message() -> None:
    cursor_cm, cursor = _make_cursor()
    conn = _make_connection(cursor_cm)
    handle = _job_handle()

    finish_job_step(
        conn,
        job=handle,
        step_code="ETAPA_2",
        status="skipped",
        message="  Nada a fazer  ",
        data=None,
    )

    conn.cursor.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE audit.job_step" in sql
    assert params[0] == "SKIPPED"
    assert params[1] == "Nada a fazer"
    assert params[2] is None


def test_job_step_context_manager_marks_error() -> None:
    start_cm, start_cursor = _make_cursor()
    finish_cm, finish_cursor = _make_cursor()
    conn = _make_connection(start_cm, finish_cm)
    handle = _job_handle()

    with pytest.raises(RuntimeError):
        with job_step(conn, job=handle, step_code="ETAPA_3"):
            raise RuntimeError("falhou")

    # Segunda chamada corresponde à atualização de erro
    assert conn.cursor.call_count == 2
    sql, params = finish_cursor.execute.call_args[0]
    assert "UPDATE audit.job_step" in sql
    assert params[0] == "ERROR"
    assert params[1] == "RuntimeError: falhou"
