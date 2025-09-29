import sys
from pathlib import Path
from unittest.mock import AsyncMock, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.db import bind_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_bind_session_executes_login_and_timezone():
    connection = AsyncMock()
    login_cursor = AsyncMock()
    login_cursor.fetchone = AsyncMock(return_value=(True,))
    timezone_cursor = AsyncMock()
    connection.execute = AsyncMock(side_effect=[login_cursor, timezone_cursor])

    await bind_session(connection, "abc123")

    assert connection.execute.await_args_list == [
        call("SELECT app.login_matricula(%s::citext)", ("abc123",)),
        call("SET TIME ZONE 'America/Sao_Paulo'")
    ]
    assert login_cursor.fetchone.await_count == 1


@pytest.mark.anyio
async def test_bind_session_rejects_unknown_matricula():
    connection = AsyncMock()
    login_cursor = AsyncMock()
    login_cursor.fetchone = AsyncMock(return_value=None)
    connection.execute = AsyncMock(side_effect=[login_cursor])

    with pytest.raises(PermissionError) as excinfo:
        await bind_session(connection, "abc123")

    assert str(excinfo.value) == "Usuário não autorizado."
    assert connection.execute.await_count == 1
    login_cursor.fetchone.assert_awaited()


@pytest.mark.anyio
async def test_bind_session_requires_matricula():
    connection = AsyncMock()

    with pytest.raises(ValueError):
        await bind_session(connection, "")

    assert connection.execute.await_count == 0
