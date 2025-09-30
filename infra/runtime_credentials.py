from __future__ import annotations

from typing import Optional


_password: Optional[str] = None


def set_gestao_base_password(password: str) -> None:
    """Armazena em memória a senha utilizada para login."""

    global _password
    _password = password or None


def get_gestao_base_password() -> Optional[str]:
    """Recupera a senha armazenada, se houver."""

    return _password


__all__ = ["get_gestao_base_password", "set_gestao_base_password"]
