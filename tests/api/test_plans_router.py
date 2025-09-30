from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
import sys

import pytest
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.models import PlansResponse
from api.routers import plans


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _DummyCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executed_sql: str | None = None

    async def __aenter__(self) -> "_DummyCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def execute(self, sql: str) -> None:
        self.executed_sql = sql

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _DummyConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def cursor(self, *, row_factory):
        assert row_factory is dict_row
        return _DummyCursor(self._rows)


class _DummyManager:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _DummyConnection:
        return _DummyConnection(self._rows)

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.anyio
async def test_list_plans_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "numero_plano": "12345",
            "numero_inscricao": "12.345.678/0001-90",
            "razao_social": "Empresa Teste",
            "situacao": "EM_DIA",
            "dias_em_atraso": 12,
            "saldo_total": Decimal("1500.50"),
            "dt_situacao": datetime(2024, 5, 1, tzinfo=timezone.utc),
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "_get_connection_manager", lambda: manager)

    response = await plans.list_plans()

    assert isinstance(response, PlansResponse)
    assert response.total == 1
    assert response.items[0].number == "12345"
    assert response.items[0].document == "12345678000190"
    assert response.items[0].company_name == "Empresa Teste"
    assert response.items[0].status == "EM_DIA"
    assert response.items[0].days_overdue == 12
    assert response.items[0].balance == Decimal("1500.50")
    assert response.items[0].status_date == date(2024, 5, 1)
