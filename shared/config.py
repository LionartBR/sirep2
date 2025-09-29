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
    password: str
    database: str
    application_name: str
    ssl_mode: Optional[str] = None
    pool_min_size: int = 1
    pool_max_size: int = 10
    timeout: float = 30.0

    @property
    def dsn(self) -> str:
        """Return a ready-to-use DSN for psycopg or SQLAlchemy engines."""
        user = quote_plus(self.user)
        password = quote_plus(self.password)
        application_name = quote_plus(self.application_name)
        base = (
            f"postgresql://{user}:{password}@{self.host}:{self.port}/"
            f"{self.database}"
        )
        params = [f"application_name={application_name}"]
        if self.ssl_mode:
            params.insert(0, f"sslmode={quote_plus(self.ssl_mode)}")
        return f"{base}?{'&'.join(params)}"


@lru_cache(maxsize=1)
def get_database_settings() -> DatabaseSettings:
    """Load settings from environment variables with sane defaults."""

    return DatabaseSettings(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "Por@m9815"),
        database=os.getenv("DB_NAME", "sirep_db"),
        application_name=os.getenv("DB_APP_NAME", "Sirep 2.0"),
        ssl_mode=os.getenv("DB_SSL_MODE") or None,
        pool_min_size=int(os.getenv("DB_POOL_MIN", "1")),
        pool_max_size=int(os.getenv("DB_POOL_MAX", "10")),
        timeout=float(os.getenv("DB_POOL_TIMEOUT", "30")),
    )


__all__ = ["DatabaseSettings", "get_database_settings"]
