from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from psycopg.errors import InvalidAuthorizationSpecification

from api.dependencies import get_connection_manager
from infra.db import bind_session
from infra.runtime_credentials import set_gestao_base_password
from api.security import require_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    """Dados enviados para autenticação do usuário."""

    matricula: str
    senha: str


class LoginResponse(BaseModel):
    """Resposta retornada após autenticação bem-sucedida."""

    matricula: str


class AuthProfileResponse(BaseModel):
    """Representa o perfil ativo do usuário autenticado."""

    perfil: str


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginPayload) -> LoginResponse:
    """Autentica o usuário verificando a matrícula no banco de dados."""

    connection_manager = get_connection_manager()

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

    senha = (payload.senha or "").strip()
    set_gestao_base_password(senha or None)

    return LoginResponse(matricula=payload.matricula)


@router.get("/me", response_model=AuthProfileResponse)
async def get_profile(request: Request) -> AuthProfileResponse:
    """Retorna o perfil atribuído ao usuário autenticado."""

    perfil = await require_roles(request, ("GESTOR", "RESCISAO"))
    return AuthProfileResponse(perfil=perfil)


__all__ = ["router"]
