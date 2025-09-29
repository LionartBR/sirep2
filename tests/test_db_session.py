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

    await bind_session(connection, "abc123")

    assert connection.execute.await_args_list == [
        call("SELECT app.login_matricula(%s::citext)", ("abc123",)),
        call("SET TIME ZONE 'America/Sao_Paulo'")
    ]


@pytest.mark.anyio
async def test_bind_session_requires_matricula():
    connection = AsyncMock()

    with pytest.raises(ValueError):
        await bind_session(connection, "")

    assert connection.execute.await_count == 0
