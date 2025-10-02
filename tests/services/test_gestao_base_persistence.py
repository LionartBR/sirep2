from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gestao_base import persistence
from services.gestao_base.models import GestaoBaseData, PlanRowEnriched


@pytest.mark.parametrize(
    "situacao",
    [
        "P.RESC",
        "Passível Rescisão",
        "Passivel de Rescisao",
        "PASSIVELDERESCISAO",
        "Passível de Rescisão Deferida",
        "Passivel Rescisao Em Analise",
    ],
)
def test_should_not_register_occurrence_for_passivel_variations(situacao: str) -> None:
    assert persistence._should_register_occurrence(situacao) is False


@pytest.mark.parametrize(
    "situacao",
    [
        "RESCINDIDO",
        "LIQUIDADO",
        "GRDE",
        "P.RESC.LIQ",
    ],
)
def test_should_register_occurrence_for_non_passivel_status(situacao: str) -> None:
    assert persistence._should_register_occurrence(situacao) is True


class _DummyPlansRepository:
    def __init__(self) -> None:
        self._store: dict[str, SimpleNamespace] = {}
        self._counter = 0

    def get_by_numero(self, numero: str) -> SimpleNamespace | None:
        return self._store.get(numero)

    def upsert(self, numero_plano: str, existing=None, **kwargs):
        if existing is None:
            self._counter += 1
            plan = SimpleNamespace(
                id=str(self._counter), numero_plano=numero_plano, **kwargs
            )
            self._store[numero_plano] = plan
            return plan

        existing.__dict__.update(kwargs)
        self._store[numero_plano] = existing
        return existing


class _DummyEventsRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def log(self, plan_id, step, message):
        self.calls.append((plan_id, step, message))


def test_persist_rows_registers_occurrences_for_non_passivel(monkeypatch):
    captured: list[dict[str, object]] = []

    class _RecorderOccurrenceRepository:
        def __init__(self, _db) -> None:  # pragma: no cover - interface compatibility
            self._db = _db

        def add(self, **payload):
            captured.append(payload)

    monkeypatch.setattr(
        persistence, "OccurrenceRepository", _RecorderOccurrenceRepository
    )
    monkeypatch.setattr(persistence.settings, "DRY_RUN", False)

    context = SimpleNamespace(
        db=object(),
        plans=_DummyPlansRepository(),
        events=_DummyEventsRepository(),
    )

    rows = [
        PlanRowEnriched(
            numero="0000001",
            dt_propost="01/01/2024",
            tipo="Tipo A",
            situac="P.RESC",
            resoluc="R1",
            razao_social="Empresa 1",
            saldo_total="100,00",
            cnpj="12.345.678/0001-90",
        ),
        PlanRowEnriched(
            numero="0000002",
            dt_propost="01/01/2024",
            tipo="Tipo B",
            situac="RESCINDIDO",
            resoluc="R2",
            razao_social="Empresa 2",
            saldo_total="200,00",
            cnpj="98.765.432/0001-10",
        ),
        PlanRowEnriched(
            numero="0000003",
            dt_propost="01/01/2024",
            tipo="Tipo C",
            situac="LIQUIDADO",
            resoluc="R3",
            razao_social="Empresa 3",
            saldo_total="300,00",
            cnpj="11.222.333/0001-44",
        ),
    ]

    data = GestaoBaseData(rows=rows, raw_lines=[], portal_po=[], descartados_974=0)

    result = persistence.persist_rows(context, data)

    assert result["importados"] == 3
    assert {item["numero_plano"] for item in captured} == {"0000002", "0000003"}
    assert all(item["situacao"] in {"RESCINDIDO", "LIQUIDADO"} for item in captured)
