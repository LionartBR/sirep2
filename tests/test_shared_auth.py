"""Tests for the authentication helpers module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from shared import auth


@pytest.mark.parametrize(
    "payload",
    [
        {"mensagem": "Usuário não autorizado."},
        {"mensagem": "Acesso negado ao usuário"},
        {"mensagem": "ACCESS DENIED"},
    ],
)
def test_is_authorized_login_handles_failure_messages(payload):
    """Failure messages without flags must not be considered authorised."""

    assert auth.is_authorized_login(payload) is False


def test_is_authorized_login_keeps_positive_values():
    """Positive, non-empty values should still be treated as affirmative."""

    assert auth.is_authorized_login({"resultado": "S"}) is True
