"""Security helpers and role enforcement for API endpoints."""

from __future__ import annotations

import logging
from functools import lru_cache
from collections.abc import Callable
from typing import Any, Iterable, Literal

from fastapi import HTTPException, Request, status
from psycopg import AsyncConnection

from api.dependencies import get_connection_manager
from infra.db import bind_session

logger = logging.getLogger(__name__)

RequestRole = Literal["GESTOR", "RESCISAO"]

_REQUEST_PRINCIPAL_HEADER_CANDIDATES: tuple[str, ...] = (
    "x-user-registration",
    "x-user-id",
    "x-app-user-registration",
    "x-app-user-id",
)

_LEGACY_ROLE_MAP = {
    "ADMIN": "GESTOR",
    "WORKER": "RESCISAO",
}


@lru_cache(maxsize=4)
def _normalized_role(role: str) -> RequestRole | None:
    candidate = (role or "").strip().upper()
    if not candidate:
        return None
    mapped = _LEGACY_ROLE_MAP.get(candidate, candidate)
    if mapped in ("GESTOR", "RESCISAO"):
        return mapped  # type: ignore[return-value]
    return None


def resolve_request_matricula(
    request: Request | None,
    fallback: Callable[[], Any] | None = None,
) -> str | None:
    """Extract the matricula from request headers or fallback settings."""

    if request is not None:
        for header in _REQUEST_PRINCIPAL_HEADER_CANDIDATES:
            value = request.headers.get(header)
            if value:
                candidate = value.split(",", 1)[0].strip()
                if candidate:
                    return candidate

    provider: Callable[[], Any] | None = fallback
    if provider is None:
        try:  # late import to avoid circular dependency during startup/tests
            from shared.config import get_principal_settings as provider  # type: ignore
        except Exception:  # pragma: no cover - defensive fallback
            provider = None

    if provider is None:
        return None

    try:
        principal = provider()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Fallback principal provider falhou", exc_info=True)
        return None

    matricula = getattr(principal, "matricula", None)
    if matricula is None and isinstance(principal, dict):
        matricula = principal.get("matricula")
    candidate = str(matricula or "").strip()
    return candidate or None


async def _fetch_current_profile(connection: AsyncConnection) -> RequestRole | None:
    async with connection.cursor() as cur:
        await cur.execute("SELECT app.current_user_perfil()")
        row = await cur.fetchone()
    if not row:
        return None
    perfil = (
        row[0]
        if isinstance(row, (list, tuple))
        else getattr(row, "current_user_perfil", None)
    )
    return _normalized_role(str(perfil or ""))


async def require_roles(
    request: Request, allowed_roles: Iterable[RequestRole]
) -> RequestRole:
    """Ensure the current session user matches one of the allowed roles."""

    matricula = resolve_request_matricula(request)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    allowed = {_normalized_role(role) for role in allowed_roles}
    allowed.discard(None)
    if not allowed:
        raise HTTPException(  # pragma: no cover - misconfiguration
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuração de acesso inválida.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            profile = await _fetch_current_profile(connection)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Erro ao validar perfil do usuário")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível validar as permissões do usuário.",
        ) from exc

    if profile not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para acessar este recurso.",
        )

    return profile


def role_required(*roles: RequestRole):
    """Create a dependency enforcing the given roles."""

    async def dependency(request: Request) -> RequestRole:
        return await require_roles(request, roles)

    return dependency


__all__ = [
    "RequestRole",
    "resolve_request_matricula",
    "role_required",
    "require_roles",
]
