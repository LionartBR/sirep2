import asyncio
import sys
from pathlib import Path

import pytest
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.enums import Step
from services.base import ServiceResult, StepJobOutcome
from domain.pipeline import PipelineStatus
from services.gestao_base import service as gestao_module
from services.orchestrator import PipelineOrchestrator


class _DummyService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def execute(self, matricula, senha):
        self.calls.append((matricula, senha))
        return ServiceResult(step=Step.ETAPA_1, outcome=StepJobOutcome())


class _ConfiguredService:
    def __init__(self, *, status: str = "SUCCESS", info_update: Optional[dict] = None):
        self.outcome = StepJobOutcome(status=status, info_update=info_update)

    def execute(self, *_args, **_kwargs):
        return ServiceResult(step=Step.ETAPA_1, outcome=self.outcome)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_orchestrator_forwards_matricula_and_senha(monkeypatch):
    dummy = _DummyService()
    orchestrator = PipelineOrchestrator(service=dummy)

    async def immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate_to_thread)

    task = orchestrator._task
    assert task is None

    state = await orchestrator.start(matricula="abc123", senha="secreta")
    assert state.status.value == "running"

    task = orchestrator._task
    assert task is not None
    await task

    assert dummy.calls == [("abc123", "secreta")]
    assert orchestrator.get_state().status.value == "succeeded"


@pytest.mark.anyio
async def test_orchestrator_reports_failure_status(monkeypatch):
    service = _ConfiguredService(status="ERROR")
    orchestrator = PipelineOrchestrator(service=service)

    async def immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate_to_thread)

    await orchestrator.start()
    task = orchestrator._task
    assert task is not None
    await task

    state = orchestrator.get_state()
    assert state.status is PipelineStatus.FAILED
    assert state.message == "Pipeline finalizada com erro."


@pytest.mark.anyio
async def test_orchestrator_uses_summary_on_success(monkeypatch):
    service = _ConfiguredService(
        status="SKIPPED", info_update={"summary": "Sem novidades"}
    )
    orchestrator = PipelineOrchestrator(service=service)

    async def immediate_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", immediate_to_thread)

    await orchestrator.start()
    task = orchestrator._task
    assert task is not None
    await task

    state = orchestrator.get_state()
    assert state.status is PipelineStatus.SUCCEEDED
    assert state.message == "Sem novidades"


def test_service_passes_matricula_to_run_step_job(monkeypatch):
    captured = {}

    def fake_run_step_job(*, step, job_name, callback, user_id=None, **kwargs):
        captured["step"] = step
        captured["job_name"] = job_name
        captured["user_id"] = user_id
        return ServiceResult(step=step, outcome=StepJobOutcome())

    monkeypatch.setattr(gestao_module, "run_step_job", fake_run_step_job)

    original_dry_run = gestao_module.settings.DRY_RUN
    gestao_module.settings.DRY_RUN = True
    try:
        service = gestao_module.GestaoBaseService()
        service.execute(matricula="abc123")
    finally:
        gestao_module.settings.DRY_RUN = original_dry_run

    assert captured["user_id"] == "abc123"
    assert captured["job_name"] == Step.ETAPA_1
