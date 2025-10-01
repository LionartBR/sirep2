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
from shared.config import PrincipalSettings


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

    async def execute(self, sql: str, *args: Any, **kwargs: Any) -> None:
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


class _DummyHeaders:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def get(self, key: str, default: Any = None) -> Any:
        return self._headers.get(key.lower(), default)


class _DummyRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = _DummyHeaders(headers)


def _make_request(headers: dict[str, str] | None = None) -> _DummyRequest:
    return _DummyRequest(headers)


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
            "total_count": 120,
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "_get_connection_manager", lambda: manager)

    bind_calls: list[tuple[Any, str]] = []

    async def _fake_bind(connection: Any, matricula: str) -> None:
        bind_calls.append((connection, matricula))

    monkeypatch.setattr(plans, "bind_session", _fake_bind)
    monkeypatch.setattr(
        plans,
        "get_principal_settings",
        lambda: PrincipalSettings(
            tenant_id="tenant-x",
            matricula="abc123",
            nome="Usuário",
            email="user@example.com",
            perfil="admin",
        ),
    )

    response = await plans.list_plans(
        request=_make_request(),
        q=None,
        limit=plans.DEFAULT_LIMIT,
        offset=0,
    )

    assert isinstance(response, PlansResponse)
    assert response.total == 120
    assert response.items[0].number == "12345"
    assert response.items[0].document == "12345678000190"
    assert response.items[0].company_name == "Empresa Teste"
    assert response.items[0].status == "EM_DIA"
    assert response.items[0].days_overdue == 12
    assert response.items[0].balance == Decimal("1500.50")
    assert response.items[0].status_date == date(2024, 5, 1)
    assert len(bind_calls) == 1
    connection, matricula = bind_calls[0]
    assert isinstance(connection, _DummyConnection)
    assert matricula == "abc123"


@pytest.mark.anyio
async def test_list_plans_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_manager() -> _DummyManager:
        raise AssertionError("Connection should not be requested when credentials are missing")

    monkeypatch.setattr(plans, "_get_connection_manager", _unexpected_manager)

    async def _unexpected_bind(*_: Any) -> None:
        raise AssertionError("bind_session should not be called when credentials are missing")

    monkeypatch.setattr(plans, "bind_session", _unexpected_bind)
    monkeypatch.setattr(
        plans,
        "get_principal_settings",
        lambda: PrincipalSettings(
            tenant_id="tenant-x",
            matricula=None,
            nome="Usuário",
            email="user@example.com",
            perfil="admin",
        ),
    )

    with pytest.raises(plans.HTTPException) as excinfo:
        await plans.list_plans(request=_make_request())

    assert excinfo.value.status_code == plans.status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Credenciais de acesso ausentes."


@pytest.mark.anyio
async def test_list_plans_accepts_header_override(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "_get_connection_manager", lambda: manager)

    bind_calls: list[tuple[Any, str]] = []

    async def _fake_bind(connection: Any, matricula: str) -> None:
        bind_calls.append((connection, matricula))

    monkeypatch.setattr(plans, "bind_session", _fake_bind)
    monkeypatch.setattr(
        plans,
        "get_principal_settings",
        lambda: PrincipalSettings(
            tenant_id="tenant-x",
            matricula=None,
            nome="Usuário",
            email="user@example.com",
            perfil="admin",
        ),
    )

    response = await plans.list_plans(
        request=_make_request({"X-User-Registration": "  789xyz  "}),
        q=None,
        limit=plans.DEFAULT_LIMIT,
        offset=10,
    )

    assert isinstance(response, PlansResponse)
    assert response.total == 0
    assert response.items == []
    assert len(bind_calls) == 1
    _, matricula = bind_calls[0]
    assert matricula == "789xyz"


@pytest.mark.anyio
async def test_list_plans_returns_unauthorized_when_binding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "_get_connection_manager", lambda: manager)

    async def _raise_permission(*_: Any) -> None:
        raise PermissionError("Access denied")

    monkeypatch.setattr(plans, "bind_session", _raise_permission)
    monkeypatch.setattr(
        plans,
        "get_principal_settings",
        lambda: PrincipalSettings(
            tenant_id="tenant-x",
            matricula="abc123",
            nome="Usuário",
            email="user@example.com",
            perfil="admin",
        ),
    )

    with pytest.raises(plans.HTTPException) as excinfo:
        await plans.list_plans(
            request=_make_request(),
            q=None,
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

    assert excinfo.value.status_code == plans.status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Credenciais de acesso inválidas."
