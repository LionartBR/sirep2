from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus


@dataclass(slots=True)
class DatabaseSettings:
    """Configuration parameters required to connect to PostgreSQL."""

    host: str
    port: int
    user: str
    database: str
    application_name: str    
    password: Optional[str] = None
    ssl_mode: Optional[str] = None
    pool_min_size: int = 1
    pool_max_size: int = 10
    timeout: float = 30.0

    @property
    def dsn(self) -> str:
        """Return a ready-to-use DSN for psycopg or SQLAlchemy engines."""
        # Monta a URL omitindo a senha quando não houver (permite .pgpass)
        user_enc = quote_plus(self.user)
        app_enc = quote_plus(self.application_name)
        base_auth = f"{user_enc}" if self.password in (None, "") else f"{user_enc}:{quote_plus(self.password)}"
        base = f"postgresql://{base_auth}@{self.host}:{self.port}/{self.database}"

        params = [f"application_name={app_enc}"]
        if self.ssl_mode:
            params.insert(0, f"sslmode={quote_plus(self.ssl_mode)}")

        return f"{base}?{'&'.join(params)}"


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """carregando configs básicas do banco."""

    return DatabaseSettings(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD") or None,
        database=os.getenv("DB_NAME", "sirep_db"),
        application_name=os.getenv("DB_APP_NAME", "Sirep 2.0"),
        ssl_mode=os.getenv("DB_SSL_MODE") or None,
        pool_min_size=int(os.getenv("DB_POOL_MIN", "1")),
        pool_max_size=int(os.getenv("DB_POOL_MAX", "10")),
        timeout=float(os.getenv("DB_POOL_TIMEOUT", "30")),
    )



@dataclass(slots=True)
class PrincipalSettings:
    """Informações de contexto necessárias para inicializar a sessão no banco."""

    tenant_id: Optional[str]
    matricula: Optional[str]
    nome: Optional[str]
    email: Optional[str]
    perfil: Optional[str]


@lru_cache(maxsize=1)
def get_principal_settings() -> PrincipalSettings:
    """Carrega as credenciais do usuário de aplicação a partir do ambiente."""

    tenant_id = os.getenv("APP_TENANT_ID") or os.getenv("TENANT_ID")
    matricula = (
        os.getenv("APP_USER_REGISTRATION")
        or os.getenv("APP_USER_ID")
        or os.getenv("USER_ID")
    )
    nome = os.getenv("APP_USER_NAME") or os.getenv("USER_NAME")
    email = os.getenv("APP_USER_EMAIL") or os.getenv("USER_EMAIL")
    perfil = os.getenv("APP_USER_PROFILE") or os.getenv("USER_PROFILE")
    return PrincipalSettings(
        tenant_id=tenant_id or None,
        matricula=matricula or None,
        nome=nome or None,
        email=email or None,
        perfil=perfil or None,
    )


__all__ = [
    "DatabaseSettings",
    "PrincipalSettings",
    "get_database_settings",
    "get_principal_settings",
]
