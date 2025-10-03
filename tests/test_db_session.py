from unittest.mock import AsyncMock, MagicMock, call

import pytest

from infra.db import bind_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_bind_session_executes_login_and_timezone():
    connection = AsyncMock()
    cursor_cm = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"ok": True})
    cursor_cm.__aenter__.return_value = cursor
    connection.cursor = MagicMock(return_value=cursor_cm)

    await bind_session(connection, "abc123")

    connection.cursor.assert_called_once()
    assert cursor.execute.await_args_list == [
        call("SELECT app.login_matricula(%s::citext)", ("abc123",)),
        call("SET TIME ZONE 'America/Sao_Paulo'"),
    ]
    cursor.fetchone.assert_awaited_once()


@pytest.mark.anyio
async def test_bind_session_rejects_unknown_matricula():
    connection = AsyncMock()
    cursor_cm = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=None)
    cursor_cm.__aenter__.return_value = cursor
    connection.cursor = MagicMock(return_value=cursor_cm)

    with pytest.raises(PermissionError) as excinfo:
        await bind_session(connection, "abc123")

    assert str(excinfo.value) == "Usuário não autorizado."
    connection.cursor.assert_called_once()
    cursor.fetchone.assert_awaited()


@pytest.mark.anyio
async def test_bind_session_rejects_falsey_string_response():
    connection = AsyncMock()
    cursor_cm = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value={"ok": "f"})
    cursor_cm.__aenter__.return_value = cursor
    connection.cursor = MagicMock(return_value=cursor_cm)

    with pytest.raises(PermissionError) as excinfo:
        await bind_session(connection, "abc123")

    assert str(excinfo.value) == "Usuário não autorizado."
    connection.cursor.assert_called_once()
    cursor.fetchone.assert_awaited()


@pytest.mark.anyio
async def test_bind_session_rejects_falsey_flag_with_message():
    connection = AsyncMock()
    cursor_cm = AsyncMock()
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(
        return_value={"ok": False, "mensagem": "Usuário não autorizado."}
    )
    cursor_cm.__aenter__.return_value = cursor
    connection.cursor = MagicMock(return_value=cursor_cm)

    with pytest.raises(PermissionError) as excinfo:
        await bind_session(connection, "abc123")

    assert str(excinfo.value) == "Usuário não autorizado."
    connection.cursor.assert_called_once()
    cursor.fetchone.assert_awaited()


@pytest.mark.anyio
async def test_bind_session_requires_matricula():
    connection = AsyncMock()

    with pytest.raises(ValueError):
        await bind_session(connection, "")

    connection.cursor.assert_not_called()
