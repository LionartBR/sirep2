from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from types import ModuleType
import importlib
import sys
from uuid import UUID

import pytest

from api.models import PlanBlockRequest, PlanUnblockRequest
from domain.plan_block import PlanBlockResult, PlanUnblockResult

def _ensure_psycopg_stub() -> None:
    required_modules = [
        "psycopg",
        "psycopg.errors",
        "psycopg.rows",
        "psycopg.types",
        "psycopg.types.json",
        "psycopg.pq",
        "psycopg_pool",
    ]

    missing_modules: set[str] = set()
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing_modules.add(module_name)

    if not missing_modules:
        return

    def _build_errors_module() -> ModuleType:
        errors_module = ModuleType("psycopg.errors")

        class InvalidAuthorizationSpecification(Exception):
            """Stub exception mirroring psycopg.errors.InvalidAuthorizationSpecification."""

            ...

        class UniqueViolation(Exception):
            """Stub exception mirroring psycopg.errors.UniqueViolation."""

            ...

        errors_module.InvalidAuthorizationSpecification = (
            InvalidAuthorizationSpecification
        )
        errors_module.UniqueViolation = UniqueViolation
        return errors_module

    def _build_rows_module() -> ModuleType:
        rows_module = ModuleType("psycopg.rows")

        def dict_row(row: Any) -> Any:  # noqa: D401 - stub function
            """Return the row unchanged, mimicking psycopg.rows.dict_row behavior."""

            return row

        rows_module.dict_row = dict_row
        return rows_module

    def _build_types_modules() -> tuple[ModuleType, ModuleType]:
        types_module = ModuleType("psycopg.types")
        json_module = ModuleType("psycopg.types.json")

        class Json:  # noqa: D401 - stub class
            """Stub for psycopg.types.json.Json wrapper."""

            def __init__(self, value: Any) -> None:
                self.value = value

        json_module.Json = Json
        types_module.json = json_module
        return types_module, json_module

    def _build_pq_module() -> ModuleType:
        pq_module = ModuleType("psycopg.pq")

        class TransactionStatus:
            IDLE = "IDLE"
            INTRANS = "INTRANS"
            INERROR = "INERROR"
            UNKNOWN = "UNKNOWN"

        pq_module.TransactionStatus = TransactionStatus
        return pq_module

    def _build_pool_module() -> ModuleType:
        psycopg_pool_module = ModuleType("psycopg_pool")

        class AsyncConnectionPool:  # noqa: D401 - stub class
            """Stub for psycopg_pool.AsyncConnectionPool."""

            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.args = args
                self.kwargs = kwargs

            async def close(self) -> None:  # pragma: no cover - unused
                return None

        psycopg_pool_module.AsyncConnectionPool = AsyncConnectionPool
        return psycopg_pool_module

    if "psycopg" in missing_modules or "psycopg" not in sys.modules:
        psycopg_module = ModuleType("psycopg")

        class AsyncConnection:  # noqa: D401 - stub class
            """Stub for psycopg.AsyncConnection used in type hints."""

            ...

        class Connection:  # noqa: D401 - stub class
            """Stub for psycopg.Connection used in type hints."""

            ...

        psycopg_module.AsyncConnection = AsyncConnection
        psycopg_module.Connection = Connection
        sys.modules["psycopg"] = psycopg_module
    else:
        psycopg_module = sys.modules["psycopg"]

    if "psycopg.errors" in missing_modules:
        errors_module = _build_errors_module()
        sys.modules["psycopg.errors"] = errors_module
        setattr(psycopg_module, "errors", errors_module)

    if "psycopg.rows" in missing_modules:
        rows_module = _build_rows_module()
        sys.modules["psycopg.rows"] = rows_module
        setattr(psycopg_module, "rows", rows_module)

    if "psycopg.types" in missing_modules or "psycopg.types.json" in missing_modules:
        types_module, json_module = _build_types_modules()
        if "psycopg.types" in missing_modules:
            sys.modules["psycopg.types"] = types_module
            setattr(psycopg_module, "types", types_module)
        if "psycopg.types.json" in missing_modules:
            sys.modules["psycopg.types.json"] = json_module
            # Ensure the parent module reference is present even if it originally existed.
            types_parent = sys.modules.get("psycopg.types")
            if types_parent is None:
                types_parent = types_module
                sys.modules["psycopg.types"] = types_parent
                setattr(psycopg_module, "types", types_parent)
            types_parent.json = json_module

    if "psycopg.pq" in missing_modules:
        pq_module = _build_pq_module()
        sys.modules["psycopg.pq"] = pq_module
        setattr(psycopg_module, "pq", pq_module)

    if "psycopg_pool" in missing_modules:
        sys.modules["psycopg_pool"] = _build_pool_module()


try:
    from psycopg.rows import dict_row
except ModuleNotFoundError:
    _ensure_psycopg_stub()
    from psycopg.rows import dict_row


def _ensure_fastapi_stub() -> None:
    try:
        importlib.import_module("fastapi")
        importlib.import_module("fastapi.responses")
        importlib.import_module("fastapi.staticfiles")
        importlib.import_module("fastapi.status")
        return
    except ModuleNotFoundError:
        if "fastapi" in sys.modules:
            return

    fastapi_module = ModuleType("fastapi")
    responses_module = ModuleType("fastapi.responses")
    staticfiles_module = ModuleType("fastapi.staticfiles")

    class Response:
        def __init__(
            self,
            content: Any | None = None,
            status_code: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}

    class RedirectResponse(Response):
        def __init__(self, url: str, status_code: int = 307) -> None:
            super().__init__(status_code=status_code, headers={"location": url})
            self.url = url

    class StaticFiles:
        def __init__(self, *, directory: Any, html: bool = False) -> None:
            self.directory = directory
            self.html = html

        async def get_response(
            self, path: str, scope: Any
        ) -> Response:  # pragma: no cover - unused in tests
            return Response()

    class HTTPException(Exception):
        def __init__(self, *, status_code: int, detail: str) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Query(default: Any, **_: Any) -> Any:
        return default

    class Request:
        def __init__(self, headers: dict[str, str] | None = None) -> None:
            self.headers = headers or {}

    def Depends(dependency: Any) -> Any:  # pragma: no cover - unused in tests
        return dependency

    class APIRouter:
        def __init__(self, prefix: str = "", tags: list[str] | None = None) -> None:
            self.prefix = prefix
            self.tags = tags or []
            self.routes: list[tuple[str, Any]] = []

        def get(self, path: str, **_: Any) -> Any:
            def decorator(func: Any) -> Any:
                self.routes.append((path, func))
                return func

            return decorator

        def post(self, path: str, **_: Any) -> Any:
            return self.get(path)

    class _StatusModule(ModuleType):
        HTTP_202_ACCEPTED = 202
        HTTP_401_UNAUTHORIZED = 401
        HTTP_409_CONFLICT = 409
        HTTP_500_INTERNAL_SERVER_ERROR = 500

    status_module = _StatusModule("fastapi.status")

    class FastAPI:
        def __init__(self, *, title: str, version: str) -> None:
            self.title = title
            self.version = version
            self._routes: list[tuple[str, Any]] = []
            self.state = type("_State", (), {})()

        def include_router(self, router: APIRouter, prefix: str = "") -> None:
            base = prefix.rstrip("/")
            router_prefix = router.prefix.rstrip("/")
            for path, handler in router.routes:
                segments = [
                    segment for segment in (base, router_prefix, path) if segment
                ]
                full_path = "/" + "/".join(segment.strip("/") for segment in segments)
                self._routes.append((full_path or "/", handler))

        def mount(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def get(self, _path: str, **_kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                return func

            return decorator

    fastapi_module.FastAPI = FastAPI
    fastapi_module.APIRouter = APIRouter
    fastapi_module.HTTPException = HTTPException
    fastapi_module.Query = Query
    fastapi_module.Request = Request
    fastapi_module.status = status_module
    fastapi_module.responses = responses_module
    fastapi_module.staticfiles = staticfiles_module
    fastapi_module.Depends = Depends

    responses_module.Response = Response
    responses_module.RedirectResponse = RedirectResponse
    staticfiles_module.StaticFiles = StaticFiles

    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = responses_module
    sys.modules["fastapi.staticfiles"] = staticfiles_module
    sys.modules["fastapi.status"] = status_module


_ensure_fastapi_stub()


def _ensure_pydantic_stub() -> None:
    try:
        importlib.import_module("pydantic")
        return
    except ModuleNotFoundError:
        if "pydantic" in sys.modules:
            return

    pydantic_module = ModuleType("pydantic")

    class BaseModel:
        def __init_subclass__(
            cls, **kwargs: Any
        ) -> None:  # pragma: no cover - configuration hook
            super().__init_subclass__(**kwargs)
            annotations = getattr(cls, "__annotations__", {})
            for name, value in annotations.items():
                if not hasattr(cls, name):
                    setattr(cls, name, None)

        def __init__(self, **data: Any) -> None:
            annotations = getattr(self, "__annotations__", {})
            for field in annotations:
                if field in data:
                    value = data[field]
                else:
                    value = getattr(self, field, None)
                setattr(self, field, value)
            for key, value in data.items():
                if key not in annotations:
                    setattr(self, key, value)

        @classmethod
        def model_validate(cls, obj: Any) -> "BaseModel":
            if isinstance(obj, cls):
                return obj
            if isinstance(obj, dict):
                return cls(**obj)
            data = {
                field: getattr(obj, field, None)
                for field in getattr(cls, "__annotations__", {})
            }
            return cls(**data)

        def model_dump(self) -> dict[str, Any]:
            return {
                field: getattr(self, field, None)
                for field in getattr(self, "__annotations__", {})
            }

        def dict(self) -> dict[str, Any]:  # pragma: no cover - compatibility alias
            return self.model_dump()

    class ValidationError(Exception): ...

    def Field(
        default: Any = None, **_: Any
    ) -> Any:  # pragma: no cover - unused in tests
        return default

    ConfigDict = dict

    pydantic_module.BaseModel = BaseModel
    pydantic_module.ValidationError = ValidationError
    pydantic_module.Field = Field
    pydantic_module.ConfigDict = ConfigDict

    sys.modules["pydantic"] = pydantic_module


try:  # noqa: F401 - ensure pydantic is importable for downstream modules
    import pydantic  # type: ignore[attr-defined]  # noqa: F401
except (
    ModuleNotFoundError
):  # pragma: no cover - exercised on environments without pydantic
    _ensure_pydantic_stub()


from api.models import PlansFilters, PlansResponse  # noqa: E402
from api.routers import plans  # noqa: E402
from shared.config import PrincipalSettings  # noqa: E402


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Passivel de Rescisao", "P. RESCISAO"),
        ("Passível de Rescisão", "P. RESCISAO"),
        ("Situacao especial", "SIT. ESPECIAL"),
        ("Situação especial", "SIT. ESPECIAL"),
        ("GRDE emitida", "GRDE Emitida"),
        ("Liquidado", "LIQUIDADO"),
        ("Rescindido", "RESCINDIDO"),
        ("EM_ATRASO", "EM ATRASO"),
        ("Em atraso", "EM ATRASO"),
        ("EM_DIA", "EM DIA"),
        ("Em Dia", "EM DIA"),
        ("Em dia", "EM DIA"),
    ],
)
def test_row_to_plan_summary_formats_status(raw: str, expected: str) -> None:
    summary = plans._row_to_plan_summary({"numero_plano": "42", "situacao": raw})

    assert summary.status == expected
    assert summary.treatment_queue is not None
    assert summary.treatment_queue.enqueued is False


def test_row_to_plan_summary_handles_missing_status() -> None:
    summary = plans._row_to_plan_summary({"numero_plano": "42"})

    assert summary.status is None
    assert summary.treatment_queue is not None
    assert summary.treatment_queue.enqueued is False


class _DummyCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executed_sql: str | None = None
        self.executed_params: dict[str, Any] | None = None
        self._position = 0

    async def __aenter__(self) -> "_DummyCursor":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def execute(self, sql: str, *args: Any, **kwargs: Any) -> None:
        normalized = sql.strip().upper()
        if normalized not in {"BEGIN", "COMMIT"} and not normalized.startswith("SET "):
            self.executed_sql = sql
            if args:
                self.executed_params = args[0]
            else:
                params = kwargs.get("params")
                if params is not None:
                    self.executed_params = params

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    async def fetchone(self) -> dict[str, Any] | None:
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row


class _DummyConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.last_cursor: _DummyCursor | None = None

    def cursor(self, *, row_factory):
        assert row_factory is dict_row
        cursor = _DummyCursor(self._rows)
        self.last_cursor = cursor
        return cursor


class _DummyManager:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.last_connection: _DummyConnection | None = None

    async def __aenter__(self) -> _DummyConnection:
        connection = _DummyConnection(self._rows)
        self.last_connection = connection
        return connection

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _DummyHeaders:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}

    def get(self, key: str, default: Any = None) -> Any:
        return self._headers.get(key.lower(), default)


class _DummyRequest:
    def __init__(
        self,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> None:
        self.headers = _DummyHeaders(headers)
        self.query_params = query_params or {}


def _make_request(
    headers: dict[str, str] | None = None,
    query_params: dict[str, Any] | None = None,
) -> _DummyRequest:
    return _DummyRequest(headers, query_params)


def _run(coro: asyncio.Future[Any]) -> Any:
    return asyncio.run(coro)


def test_list_plans_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "plano_id": UUID("12345678-1234-5678-1234-567812345678"),
            "numero_plano": "12345",
            "numero_inscricao": "12.345.678/0001-90",
            "razao_social": "Empresa Teste",
            "situacao": "EM_DIA",
            "dias_em_atraso": 12,
            "saldo_total": Decimal("1500.50"),
            "dt_situacao": datetime(2024, 5, 1, tzinfo=timezone.utc),
            "total_count": 120,
            "em_tratamento": False,
            "bloqueado": True,
            "bloqueado_em": datetime(2024, 5, 2, tzinfo=timezone.utc),
            "desbloqueado_em": None,
            "motivo_bloqueio": "Processo judicial",
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

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

    async def _exercise() -> None:
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
        assert response.items[0].status == "EM DIA"
        assert response.items[0].days_overdue == 12
        assert response.items[0].balance == Decimal("1500.50")
        assert response.items[0].status_date == date(2024, 5, 1)
        assert response.items[0].plan_id == UUID("12345678-1234-5678-1234-567812345678")
        assert response.items[0].em_tratamento is False
        assert response.items[0].blocked is True
        assert response.items[0].blocked_at == datetime(2024, 5, 2, tzinfo=timezone.utc)
        assert response.items[0].unblocked_at is None
        assert response.items[0].block_reason == "Processo judicial"
        assert response.filters is None
        assert len(bind_calls) == 1
        connection, matricula = bind_calls[0]
        assert isinstance(connection, _DummyConnection)
        assert matricula == "abc123"

    _run(_exercise())


def test_get_plan_detail_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    plan_id = UUID("12345678-1234-5678-1234-567812345678")
    row = {
        "id": plan_id,
        "numero_plano": "12345",
        "razao_social": "Empresa Teste",
        "documento": "12.345.678/0001-90",
        "tipo_doc": "CNPJ",
        "tipo_plano": "Coletivo",
        "resolucao": "RS-01",
        "situacao": "EM_ATRASO",
        "competencia_ini": date(2024, 1, 1),
        "competencia_fim": date(2024, 2, 1),
        "atraso_desde": date(2024, 3, 1),
        "dias_em_atraso": 30,
        "saldo_total": Decimal("1000.00"),
        "last_update_at": datetime(2024, 5, 1, tzinfo=timezone.utc),
        "em_tratamento": True,
        "bloqueado": False,
        "rescisao_comunicada": True,
    }

    manager = _DummyManager([row])
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    bind_calls: list[tuple[Any, str]] = []

    async def _fake_bind(connection: Any, matricula: str) -> None:
        bind_calls.append((connection, matricula))

    monkeypatch.setattr(plans, "bind_session", _fake_bind)

    request = _make_request(headers={"x-user-registration": "abc123"})

    result = _run(plans.get_plan_detail(str(plan_id), request))

    assert result.plan_id == plan_id
    assert result.numero_plano == "12345"
    assert result.documento == "12345678000190"
    assert result.tipo_doc == "CNPJ"
    assert result.situacao == "EM ATRASO"
    assert result.last_update_at == row["last_update_at"]
    assert result.competencia_ini == date(2024, 1, 1)
    assert result.rescisao_comunicada is True

    assert len(bind_calls) == 1
    assert bind_calls[0][1] == "abc123"

    assert manager.last_connection is not None
    cursor = manager.last_connection.last_cursor
    assert cursor is not None
    assert "p.id = %(plano_id)s::uuid" in (cursor.executed_sql or "")
    assert cursor.executed_params == {"plano_id": plan_id}


def test_get_plan_detail_by_number(monkeypatch: pytest.MonkeyPatch) -> None:
    row = {
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "numero_plano": "98765",
        "razao_social": "Empresa X",
        "documento": "12345678000190",
        "tipo_doc": "CNPJ",
        "situacao": "EM_DIA",
        "dias_em_atraso": 0,
        "saldo_total": Decimal("0"),
        "last_update_at": datetime(2024, 5, 10, tzinfo=timezone.utc),
        "em_tratamento": False,
        "bloqueado": False,
        "rescisao_comunicada": False,
    }

    manager = _DummyManager([row])
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(connection: Any, matricula: str) -> None:
        return None

    monkeypatch.setattr(plans, "bind_session", _fake_bind)

    request = _make_request(headers={"x-user-registration": "user"})

    result = _run(plans.get_plan_detail("98765", request))

    assert result.numero_plano == "98765"
    assert result.situacao == "EM DIA"
    assert manager.last_connection is not None
    cursor = manager.last_connection.last_cursor
    assert cursor is not None
    assert "p.numero_plano = %(numero_plano)s" in (cursor.executed_sql or "")
    assert cursor.executed_params == {"numero_plano": "98765"}


def test_get_plan_detail_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager([])
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(connection: Any, matricula: str) -> None:
        return None

    monkeypatch.setattr(plans, "bind_session", _fake_bind)

    request = _make_request(headers={"x-user-registration": "abc123"})

    with pytest.raises(plans.HTTPException) as excinfo:
        _run(plans.get_plan_detail("00000", request))

    assert excinfo.value.status_code == plans.status.HTTP_404_NOT_FOUND


def test_list_plans_marks_em_tratamento(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "plano_id": UUID("aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"),
            "numero_plano": "98765",
            "numero_inscricao": "98.765.432/0001-10",
            "razao_social": "Empresa Em Tratamento",
            "situacao": "PENDENTE",
            "dias_em_atraso": 5,
            "saldo_total": Decimal("100.00"),
            "dt_situacao": datetime(2024, 6, 1, tzinfo=timezone.utc),
            "total_count": 1,
            "em_tratamento": True,
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(connection: Any, matricula: str) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(),
            q=None,
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 1
        assert response.items[0].em_tratamento is True

    _run(_exercise())


def test_block_plans_endpoint_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager([])
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    captured: dict[str, Any] = {}

    class _FakeBlockingService:
        def __init__(self, connection: Any) -> None:
            captured["connection"] = connection

        async def block_plans(
            self,
            *,
            plano_ids: Any,
            motivo: str | None = None,
            expires_at: Any = None,
        ) -> PlanBlockResult:
            captured["ids"] = list(plano_ids)
            captured["motivo"] = motivo
            captured["expires_at"] = expires_at
            return PlanBlockResult(blocked_count=5)

    monkeypatch.setattr(plans, "PlanBlockingService", _FakeBlockingService)

    payload = PlanBlockRequest(
        plano_ids=[UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"), UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")],
        motivo="manutenção",
    )

    async def _exercise() -> None:
        response = await plans.block_plans_endpoint(
            request=_make_request({"X-User-Registration": "abc123"}),
            payload=payload,
        )

        assert response.ok is True
        assert response.blocked_count == 5
        assert captured["ids"] == list(payload.plano_ids)
        assert captured["motivo"] == "manutenção"
        assert captured["connection"] is manager.last_connection

    _run(_exercise())


def test_unblock_plans_endpoint_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DummyManager([])
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    captured: dict[str, Any] = {}

    class _FakeBlockingService:
        def __init__(self, connection: Any) -> None:
            captured["connection"] = connection

        async def unblock_plans(self, *, plano_ids: Any) -> PlanUnblockResult:
            captured["ids"] = list(plano_ids)
            return PlanUnblockResult(unblocked_count=7)

    monkeypatch.setattr(plans, "PlanBlockingService", _FakeBlockingService)

    payload = PlanUnblockRequest(plano_ids=[UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")])

    async def _exercise() -> None:
        response = await plans.unblock_plans_endpoint(
            request=_make_request(),
            payload=payload,
        )

        assert response.ok is True
        assert response.unblocked_count == 7
        assert captured["ids"] == list(payload.plano_ids)
        assert captured["connection"] is manager.last_connection

    _run(_exercise())


def test_list_plans_search_by_number_builds_like(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(),
            q="12345",
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 0
        assert response.items == []
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_params is not None
        assert cursor.executed_params["number"] == "12345"
        assert cursor.executed_params["number_prefix"] == "12345%"

    _run(_exercise())


def test_build_filters_document_prefix_when_tipo_doc() -> None:
    where_sql, params = plans._build_filters(
        "12.345",
        tipo_doc="CNPJ",
        occurrences_only=False,
        situacoes=None,
        dias_range=None,
        saldo_min=None,
        dt_sit_range=None,
        table_alias=None,
    )

    assert "documento LIKE %(document_prefix)s" in where_sql
    assert "tipo_doc = %(tipo_doc)s" in where_sql
    assert params["document_prefix"] == "12345%"
    assert params["tipo_doc"] == "CNPJ"
    assert "number" not in params
    assert "razao_social ILIKE" not in where_sql
    assert "name_pattern" not in params


def test_build_filters_document_exact_when_tipo_doc() -> None:
    where_sql, params = plans._build_filters(
        "12345678000190",
        tipo_doc="CNPJ",
        occurrences_only=False,
        situacoes=None,
        dias_range=None,
        saldo_min=None,
        dt_sit_range=None,
        table_alias=None,
    )

    assert "documento = %(document)s" in where_sql
    assert "LIKE %(document_prefix)s" not in where_sql
    assert params["document"] == "12345678000190"
    assert params["tipo_doc"] == "CNPJ"
    assert "razao_social ILIKE" not in where_sql
    assert "name_pattern" not in params


def test_build_filters_document_exact_without_tipo_doc() -> None:
    where_sql, params = plans._build_filters(
        "12345678000190",
        tipo_doc=None,
        occurrences_only=False,
        situacoes=None,
        dias_range=None,
        saldo_min=None,
        dt_sit_range=None,
        table_alias=None,
    )

    assert "documento = %(document)s" in where_sql
    assert "tipo_doc IN" in where_sql
    assert params["document"] == "12345678000190"
    assert "razao_social ILIKE" not in where_sql
    assert "name_pattern" not in params


def test_list_plans_keyset_uses_document_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params={"q": "123456", "tipo_doc": "CNPJ"},
            ),
            q="123456",
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
            cursor=None,
            direction=None,
            tipo_doc="CNPJ",
            occurrences_only=False,
            situacao=None,
            dias_range=None,
            saldo_min=None,
            dt_sit_range=None,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 0
        assert response.items == []
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_sql is not None
        assert "documento LIKE %(document_prefix)s" in cursor.executed_sql
        assert cursor.executed_params is not None
        assert cursor.executed_params["document_prefix"] == "123456%"
        assert cursor.executed_params["tipo_doc"] == "CNPJ"

    _run(_exercise())


def test_list_plans_search_by_name_builds_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(),
            q="Acme",
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 0
        assert response.items == []
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_params is not None
        assert cursor.executed_params["name_pattern"] == "%Acme%"

    _run(_exercise())


def test_get_plans_search_by_number_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "numero_plano": "12345",
            "numero_inscricao": "12.345.678/0001-90",
            "razao_social": "Empresa Teste",
            "situacao": "EM_DIA",
            "dias_em_atraso": 0,
            "saldo": Decimal("0"),
            "dt_situacao": datetime(2024, 5, 1, tzinfo=timezone.utc),
            "total_count": 1,
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request({"X-User-Registration": "abc123"}),
            q="12345",
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 1
        assert response.items[0].number == "12345"
        assert response.items[0].treatment_queue is not None
        assert response.items[0].treatment_queue.enqueued is False
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_params is not None
        assert cursor.executed_params["number"] == "12345"
        assert cursor.executed_params["number_prefix"] == "12345%"

    _run(_exercise())


def test_get_plans_search_by_number_prefix_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "numero_plano": "12345",
            "numero_inscricao": "12.345.678/0001-90",
            "razao_social": "Empresa Teste",
            "situacao": "EM_DIA",
            "dias_em_atraso": 0,
            "saldo": Decimal("0"),
            "dt_situacao": datetime(2024, 5, 1, tzinfo=timezone.utc),
            "total_count": 1,
        }
    ]

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request({"X-User-Registration": "abc123"}),
            q="123",
            limit=plans.DEFAULT_LIMIT,
            offset=0,
        )

        assert isinstance(response, PlansResponse)
        assert response.total == 1
        assert response.items[0].number == "12345"
        assert response.items[0].treatment_queue is not None
        assert response.items[0].treatment_queue.enqueued is False
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_params is not None
        assert cursor.executed_params["number"] == "123"
        assert cursor.executed_params["number_prefix"] == "123%"

    _run(_exercise())


def test_list_plans_applies_filters_keyset(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params={"situacao": "P_RESCISAO", "dias_range": "60-90"},
            ),
            q=None,
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
            cursor=None,
            direction=None,
            tipo_doc=None,
            occurrences_only=False,
            situacao=["P_RESCISAO", "RESCINDIDO"],
            dias_range="60-90",
            saldo_min=50000,
            dt_sit_range="THIS_MONTH",
        )

        assert isinstance(response, PlansResponse)
        assert response.filters is not None
        expected_filters = PlansFilters(
            situacao=["P_RESCISAO", "RESCINDIDO"],
            dias_range="60-90",
            dias_min=60,
            saldo_min=50000,
            dt_sit_range="THIS_MONTH",
        )
        assert response.filters.model_dump() == expected_filters.model_dump()

        assert manager.last_connection is not None
        cursor_obj = manager.last_connection.last_cursor
        assert cursor_obj is not None
        assert cursor_obj.executed_sql is not None
        sql = cursor_obj.executed_sql
        assert "planos.situacao_codigo = ANY" in sql
        assert "faixa_dias_em_atraso" in sql
        assert "COALESCE(planos.saldo, 0) >= %(saldo_min)s" in sql
        assert "planos.dt_situacao >= date_trunc('month', CURRENT_DATE)" in sql
        params = cursor_obj.executed_params
        assert params is not None
        assert list(params["situacoes"]) == ["P_RESCISAO", "RESCINDIDO"]
        assert params["dias_range"] == "60-90"
        assert params["saldo_min"] == 50000

    _run(_exercise())


def test_list_plans_legacy_dias_min_maps_to_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params={"dias_min": "120"},
            ),
            q=None,
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
            cursor=None,
            direction=None,
            tipo_doc=None,
            occurrences_only=False,
            dias_min=120,
        )

        assert isinstance(response, PlansResponse)
        assert response.filters is not None
        assert response.filters.dias_range == "120+"
        assert response.filters.dias_min == 120
        assert manager.last_connection is not None
        cursor_obj = manager.last_connection.last_cursor
        assert cursor_obj is not None
        params = cursor_obj.executed_params
        assert params is not None
        assert params["dias_range"] == "120+"

    _run(_exercise())


def test_list_plans_occurrences_only_enforces_allowed_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

    async def _fake_bind(*_: Any) -> None:
        return None

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

    async def _exercise() -> None:
        request_params = {
            "page": "1",
            "page_size": str(plans.KEYSET_DEFAULT_PAGE_SIZE),
        }
        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params=request_params,
            ),
            occurrences_only=True,
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
        )

        assert isinstance(response, PlansResponse)
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        assert cursor.executed_sql is not None
        assert "planos.situacao_codigo = ANY" in cursor.executed_sql
        params = cursor.executed_params
        assert params is not None
        assert list(params["situacoes"]) == ["SIT_ESPECIAL", "GRDE_EMITIDA"]

        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params={
                    "page": "1",
                    "page_size": str(plans.KEYSET_DEFAULT_PAGE_SIZE),
                    "situacao": "SIT_ESPECIAL",
                },
            ),
            occurrences_only=True,
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
            situacao=["SIT_ESPECIAL", "RESCINDIDO"],
        )

        assert isinstance(response, PlansResponse)
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        params = cursor.executed_params
        assert params is not None
        assert list(params["situacoes"]) == ["SIT_ESPECIAL"]

        response = await plans.list_plans(
            request=_make_request(
                headers={"X-User-Registration": "abc123"},
                query_params={
                    "page": "1",
                    "page_size": str(plans.KEYSET_DEFAULT_PAGE_SIZE),
                    "situacao": "RESCINDIDO",
                },
            ),
            occurrences_only=True,
            page=1,
            page_size=plans.KEYSET_DEFAULT_PAGE_SIZE,
            situacao=["RESCINDIDO"],
        )

        assert isinstance(response, PlansResponse)
        assert manager.last_connection is not None
        cursor = manager.last_connection.last_cursor
        assert cursor is not None
        params = cursor.executed_params
        assert params is not None
        assert list(params["situacoes"]) == ["SIT_ESPECIAL", "GRDE_EMITIDA"]

    _run(_exercise())


def test_list_plans_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_manager() -> _DummyManager:
        raise AssertionError(
            "Connection should not be requested when credentials are missing"
        )

    monkeypatch.setattr(plans, "get_connection_manager", _unexpected_manager)

    async def _unexpected_bind(*_: Any) -> None:
        raise AssertionError(
            "bind_session should not be called when credentials are missing"
        )

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

    async def _exercise() -> None:
        with pytest.raises(plans.HTTPException) as excinfo:
            await plans.list_plans(request=_make_request())

        assert excinfo.value.status_code == plans.status.HTTP_401_UNAUTHORIZED
        assert excinfo.value.detail == "Credenciais de acesso ausentes."

    _run(_exercise())


def test_list_plans_accepts_header_override(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

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

    async def _exercise() -> None:
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

    _run(_exercise())


def test_list_plans_returns_unauthorized_when_binding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, Any]] = []

    manager = _DummyManager(rows)
    monkeypatch.setattr(plans, "get_connection_manager", lambda: manager)

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

    async def _exercise() -> None:
        with pytest.raises(plans.HTTPException) as excinfo:
            await plans.list_plans(
                request=_make_request(),
                q=None,
                limit=plans.DEFAULT_LIMIT,
                offset=0,
            )

        assert excinfo.value.status_code == plans.status.HTTP_401_UNAUTHORIZED
        assert excinfo.value.detail == "Credenciais de acesso inválidas."

    _run(_exercise())
