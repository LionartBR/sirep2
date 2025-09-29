from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from psycopg import AsyncConnection
from psycopg.errors import InvalidAuthorizationSpecification

from infra.db import bind_session, get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    """Dados enviados para autenticação do usuário."""

    matricula: str
    senha: str


class LoginResponse(BaseModel):
    """Resposta retornada após autenticação bem-sucedida."""

    matricula: str


def _get_connection_manager() -> AbstractAsyncContextManager[AsyncConnection]:
    """Return the connection context manager used to authenticate."""

    return get_connection()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginPayload) -> LoginResponse:
    """Autentica o usuário verificando a matrícula no banco de dados."""

    connection_manager = _get_connection_manager()

    try:
        async with connection_manager as connection:
            await bind_session(connection, payload.matricula)
    except (InvalidAuthorizationSpecification, PermissionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não autorizado.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao autenticar usuário")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao autenticar usuário.",
        ) from exc

    return LoginResponse(matricula=payload.matricula)


__all__ = ["router"]
