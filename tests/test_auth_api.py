from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from psycopg.errors import InvalidAuthorizationSpecification

from api.routers import auth as auth_router


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _ConnectionManager:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _setup_auth(monkeypatch, side_effect=None):
    connection = object()
    manager = _ConnectionManager(connection)
    bind_mock = AsyncMock(side_effect=side_effect)

    monkeypatch.setattr(auth_router, "get_connection_manager", lambda: manager)
    monkeypatch.setattr(auth_router, "bind_session", bind_mock)

    return connection, bind_mock


@pytest.mark.anyio
async def test_login_success(monkeypatch):
    connection, bind_mock = _setup_auth(monkeypatch)

    payload = auth_router.LoginPayload(matricula="C012345", senha="secret")
    response = await auth_router.login(payload)

    assert response.matricula == "C012345"
    bind_mock.assert_awaited_once_with(connection, "C012345")


@pytest.mark.anyio
async def test_login_unauthorized_from_permission_error(monkeypatch):
    _, bind_mock = _setup_auth(
        monkeypatch, side_effect=PermissionError("Usuário não autorizado.")
    )

    payload = auth_router.LoginPayload(matricula="C000000", senha="1234")

    with pytest.raises(HTTPException) as excinfo:
        await auth_router.login(payload)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Usuário não autorizado."
    bind_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_login_unauthorized_from_database_error(monkeypatch):
    _, bind_mock = _setup_auth(
        monkeypatch, side_effect=InvalidAuthorizationSpecification("invalid")
    )

    payload = auth_router.LoginPayload(matricula="C999999", senha="1234")

    with pytest.raises(HTTPException) as excinfo:
        await auth_router.login(payload)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Usuário não autorizado."
    bind_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_login_unexpected_error_returns_500(monkeypatch):
    _, bind_mock = _setup_auth(monkeypatch, side_effect=RuntimeError("boom"))

    payload = auth_router.LoginPayload(matricula="C222222", senha="1234")

    with pytest.raises(HTTPException) as excinfo:
        await auth_router.login(payload)

    assert excinfo.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert excinfo.value.detail == "Erro ao autenticar usuário."
    bind_mock.assert_awaited_once()
