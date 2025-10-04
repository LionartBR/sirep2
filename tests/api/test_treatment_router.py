from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from api.models import (
    TreatmentCloseRequest,
    TreatmentMigrateRequest,
    TreatmentRescindRequest,
    TreatmentSkipRequest,
)
from api.routers import treatment
from domain.treatment import (
    TreatmentItem,
    TreatmentMigrationResult,
    TreatmentState,
    TreatmentTotals,
)
from services.treatment import ItemsPage, TreatmentNotFoundError
from shared.config import PrincipalSettings


class _DummyManager:
    """Minimal async context manager mimicking the connection manager."""

    def __init__(self) -> None:
        self.last_connection: object | None = None

    async def __aenter__(self) -> object:
        connection = object()
        self.last_connection = connection
        return connection

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # pragma: no cover - no cleanup
        return False


class _DummyHeaders:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def get(self, key: str, default: object | None = None) -> object | None:
        return self._headers.get(key.lower(), default)


class _DummyRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = _DummyHeaders(headers)


def _make_request(headers: dict[str, str] | None = None) -> _DummyRequest:
    return _DummyRequest(headers)


def _run(coro):
    return asyncio.run(coro)


async def _noop_bind(connection: object, matricula: str) -> None:
    return None


def test_get_treatment_state_returns_open_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)

    bind_calls: list[tuple[object, str]] = []

    async def _fake_bind(connection: object, matricula: str) -> None:
        bind_calls.append((connection, matricula))

    monkeypatch.setattr(treatment, "bind_session", _fake_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(
            tenant_id="tenant-x",
            matricula="fallback",
            nome=None,
            email=None,
            perfil=None,
        ),
    )

    lote_id = uuid4()
    state = TreatmentState(
        has_open=True,
        lote_id=lote_id,
        totals=TreatmentTotals(pending=5, processed=2, skipped=1),
    )

    class _StubService:
        created_with: list[object] = []
        calls: list[str] = []

        def __init__(self, connection: object) -> None:
            self.connection = connection
            _StubService.created_with.append(connection)

        async def get_state(self, *, grid: str) -> TreatmentState:
            _StubService.calls.append(grid)
            return state

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    request = _make_request({"x-user-registration": "abc123"})
    response = _run(treatment.get_treatment_state(request, grid=treatment.DEFAULT_GRID))

    assert response.has_open is True
    assert response.lote_id == lote_id
    assert response.totals.pending == 5
    assert bind_calls[0][0] is manager.last_connection
    assert bind_calls[0][1] == "abc123"
    assert _StubService.calls == [treatment.DEFAULT_GRID]


def test_get_treatment_state_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(treatment, "get_principal_settings", lambda: PrincipalSettings(None, None, None, None, None))

    request = _make_request({})
    with pytest.raises(treatment.HTTPException) as excinfo:
        _run(treatment.get_treatment_state(request, grid=treatment.DEFAULT_GRID))

    assert excinfo.value.status_code == treatment.status.HTTP_401_UNAUTHORIZED


def test_migrate_treatment_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "mat-001", None, None, None),
    )

    result = TreatmentMigrationResult(lote_id=uuid4(), items_seeded=12, created=True)

    class _StubService:
        payloads: list[tuple[str, dict[str, object] | None]] = []

        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def migrate(self, *, grid: str, filters: dict[str, object] | None) -> TreatmentMigrationResult:
            _StubService.payloads.append((grid, filters))
            return result

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    payload = TreatmentMigrateRequest(grid=treatment.DEFAULT_GRID, filters={"saldo_min": 1000})
    request = _make_request({"x-user-registration": "mat-001"})

    response = _run(treatment.migrate_treatment(request, payload))

    assert UUID(str(response.lote_id)) == result.lote_id
    assert response.items_seeded == 12
    assert response.created is True
    assert _StubService.payloads == [(treatment.DEFAULT_GRID, {"saldo_min": 1000})]


def test_migrate_treatment_rejects_unsupported_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(treatment, "get_principal_settings", lambda: PrincipalSettings(None, "mat", None, None, None))
    request = _make_request({"x-user-registration": "mat"})
    payload = TreatmentMigrateRequest(grid="OTHER", filters=None)

    with pytest.raises(treatment.HTTPException) as excinfo:
        _run(treatment.migrate_treatment(request, payload))

    assert excinfo.value.status_code == treatment.status.HTTP_400_BAD_REQUEST


def test_list_treatment_items_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "oper", None, None, None),
    )

    lote_id = uuid4()
    plano_id = uuid4()
    item = TreatmentItem(
        lote_id=lote_id,
        plano_id=plano_id,
        numero_plano="12345",
        documento="12345678000190",
        razao_social="Empresa X",
        saldo=Decimal("2500.25"),
        dt_situacao=date(2024, 5, 10),
        situacao_codigo="P_RESCISAO",
        status="pending",
        processed_at=None,
    )
    page = ItemsPage(
        items=[item],
        next_cursor="next-token",
        prev_cursor="prev-token",
        has_more=True,
        page_size=5,
    )

    class _StubService:
        calls: list[dict[str, object]] = []

        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def list_items(
            self,
            *,
            lote_id: UUID,
            status: str,
            page_size: int,
            cursor: str | None,
            direction: str,
        ) -> ItemsPage:
            _StubService.calls.append(
                {
                    "lote_id": lote_id,
                    "status": status,
                    "page_size": page_size,
                    "cursor": cursor,
                    "direction": direction,
                }
            )
            return page

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    request = _make_request({"x-user-registration": "oper"})
    response = _run(
        treatment.list_treatment_items(
            request,
            lote_id=lote_id,
            status_value="pending",
            page_size=5,
            cursor=None,
            direction="next",
        )
    )

    assert len(response.items) == 1
    item_response = response.items[0]
    assert item_response.plano_id == plano_id
    assert item_response.number == "12345"
    assert item_response.document == "12345678000190"
    assert item_response.company_name == "Empresa X"
    assert item_response.balance == Decimal("2500.25")
    assert item_response.status_date == date(2024, 5, 10)
    assert response.paging.next_cursor == "next-token"
    assert response.paging.prev_cursor == "prev-token"
    assert response.paging.has_more is True
    assert response.paging.page_size == 5
    assert _StubService.calls == [
        {
            "lote_id": lote_id,
            "status": "pending",
            "page_size": 5,
            "cursor": None,
            "direction": "next",
        }
    ]


def test_rescind_treatment_item_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "oper", None, None, None),
    )

    calls: list[dict[str, object]] = []

    class _StubService:
        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def rescind(self, *, lote_id: UUID, plano_id: UUID, effective_dt_iso: str) -> None:
            calls.append(
                {
                    "lote_id": lote_id,
                    "plano_id": plano_id,
                    "effective_dt_iso": effective_dt_iso,
                }
            )

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    payload = TreatmentRescindRequest(
        lote_id=uuid4(),
        plano_id=uuid4(),
        data_rescisao=datetime(2024, 5, 4, 10, 30, tzinfo=timezone.utc),
    )
    request = _make_request({"x-user-registration": "oper"})

    response = _run(treatment.rescind_treatment_item(request, payload))

    assert response == {"ok": True}
    assert calls[0]["lote_id"] == payload.lote_id
    assert calls[0]["plano_id"] == payload.plano_id
    assert calls[0]["effective_dt_iso"] == payload.data_rescisao.isoformat()


def test_rescind_treatment_item_handles_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "oper", None, None, None),
    )

    class _StubService:
        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def rescind(self, *, lote_id: UUID, plano_id: UUID, effective_dt_iso: str) -> None:
            raise TreatmentNotFoundError("Item não encontrado")

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    payload = TreatmentRescindRequest(
        lote_id=uuid4(),
        plano_id=uuid4(),
        data_rescisao=datetime.now(timezone.utc),
    )
    request = _make_request({"x-user-registration": "oper"})

    with pytest.raises(treatment.HTTPException) as excinfo:
        _run(treatment.rescind_treatment_item(request, payload))

    assert excinfo.value.status_code == treatment.status.HTTP_404_NOT_FOUND


def test_skip_treatment_item_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "oper", None, None, None),
    )

    calls: list[tuple[UUID, UUID]] = []

    class _StubService:
        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def skip(self, *, lote_id: UUID, plano_id: UUID) -> None:
            calls.append((lote_id, plano_id))

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    payload = TreatmentSkipRequest(lote_id=uuid4(), plano_id=uuid4())
    request = _make_request({"x-user-registration": "oper"})

    response = _run(treatment.skip_treatment_item(request, payload))

    assert response == {"ok": True}
    assert calls == [(payload.lote_id, payload.plano_id)]


def test_close_treatment_batch_calls_service(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager()
    monkeypatch.setattr(treatment, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(treatment, "bind_session", _noop_bind)
    monkeypatch.setattr(
        treatment,
        "get_principal_settings",
        lambda: PrincipalSettings(None, "oper", None, None, None),
    )

    calls: list[UUID] = []

    class _StubService:
        def __init__(self, connection: object) -> None:
            self.connection = connection

        async def close(self, *, lote_id: UUID) -> None:
            calls.append(lote_id)

    monkeypatch.setattr(treatment, "TreatmentService", _StubService)

    payload = TreatmentCloseRequest(lote_id=uuid4())
    request = _make_request({"x-user-registration": "oper"})

    response = _run(treatment.close_treatment_batch(request, payload))

    assert response == {"ok": True}
    assert calls == [payload.lote_id]
