"""Shared dependencies for the API layer."""

from typing import AsyncContextManager

from psycopg import AsyncConnection

from infra.db import get_connection


def get_connection_manager() -> AsyncContextManager[AsyncConnection]:
    """Return the shared database connection context manager."""

    return get_connection()


__all__ = ["get_connection_manager"]
