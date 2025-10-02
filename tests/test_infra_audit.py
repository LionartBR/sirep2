from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import ANY, MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.audit import JobRunHandle, finish_job_step, job_step, start_job_step


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


def test_start_job_step_updates_job_run_payload() -> None:
    select_cm, select_cursor = _make_cursor()
    update_cm, update_cursor = _make_cursor()
    select_cursor.fetchone.return_value = {"payload": {}}
    conn = _make_connection(select_cm, update_cm)
    handle = _job_handle()

    step_handle = start_job_step(
        conn,
        job=handle,
        step_code="ETAPA_1",
        message="  Captura inicial  ",
        data={"total": 3},
    )

    assert conn.cursor.call_args_list[0].kwargs == {"row_factory": ANY}
    assert conn.cursor.call_args_list[1] == call()
    update_sql, params = update_cursor.execute.call_args[0]
    assert "UPDATE audit.job_run" in update_sql
    payload = params[0].obj
    assert payload["current_step"] == "ETAPA_1"
    step_info = payload["steps"]["ETAPA_1"]
    assert step_info["status"] == "RUNNING"
    assert step_info["message"] == "Captura inicial"
    assert step_info["data"] == {"total": 3}
    assert "started_at" in step_info
    assert params[1] == "RUNNING"
    assert params[2] is None
    assert params[-3:] == (handle.tenant_id, handle.started_at, handle.id)

    assert step_handle.step_code == "ETAPA_1"
    assert step_handle.message == "Captura inicial"
    assert step_handle.data == {"total": 3}


def test_finish_job_step_updates_status_and_message() -> None:
    select_cm, select_cursor = _make_cursor()
    update_cm, update_cursor = _make_cursor()
    select_cursor.fetchone.return_value = {
        "payload": {
            "steps": {
                "ETAPA_2": {"status": "RUNNING", "started_at": "2024-01-01T12:00:00Z"}
            }
        }
    }
    conn = _make_connection(select_cm, update_cm)
    handle = _job_handle()

    finish_job_step(
        conn,
        job=handle,
        step_code="ETAPA_2",
        status="skipped",
        message="  Nada a fazer  ",
        data=None,
    )

    assert conn.cursor.call_args_list[0].kwargs == {"row_factory": ANY}
    assert conn.cursor.call_args_list[1] == call()
    update_sql, params = update_cursor.execute.call_args[0]
    assert "UPDATE audit.job_run" in update_sql
    payload = params[0].obj
    step_info = payload["steps"]["ETAPA_2"]
    assert step_info["status"] == "SKIPPED"
    assert step_info["message"] == "Nada a fazer"
    assert "data" not in step_info
    assert "finished_at" in step_info
    assert params[1] is None
    assert params[-3:] == (handle.tenant_id, handle.started_at, handle.id)


def test_job_step_context_manager_marks_error() -> None:
    start_select_cm, start_select_cursor = _make_cursor()
    start_update_cm, start_update_cursor = _make_cursor()
    finish_select_cm, finish_select_cursor = _make_cursor()
    finish_update_cm, finish_update_cursor = _make_cursor()

    start_select_cursor.fetchone.return_value = {"payload": {}}
    finish_select_cursor.fetchone.return_value = {
        "payload": {
            "steps": {
                "ETAPA_3": {"status": "RUNNING", "started_at": "2024-01-01T12:00:00Z"}
            }
        }
    }

    conn = _make_connection(
        start_select_cm,
        start_update_cm,
        finish_select_cm,
        finish_update_cm,
    )
    handle = _job_handle()

    with pytest.raises(RuntimeError):
        with job_step(conn, job=handle, step_code="ETAPA_3"):
            raise RuntimeError("falhou")

    assert conn.cursor.call_count == 4
    update_sql, params = finish_update_cursor.execute.call_args[0]
    assert "UPDATE audit.job_run" in update_sql
    payload = params[0].obj
    step_info = payload["steps"]["ETAPA_3"]
    assert step_info["status"] == "ERROR"
    assert step_info["error"] == "RuntimeError: falhou"
    assert params[1] == "RuntimeError: falhou"
    assert params[-3:] == (handle.tenant_id, handle.started_at, handle.id)
