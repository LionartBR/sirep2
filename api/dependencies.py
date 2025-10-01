"""Shared dependencies for the API layer."""

from contextlib import AbstractAsyncContextManager

from psycopg.connection import AsyncConnection

from infra.db import get_connection


def get_connection_manager() -> AbstractAsyncContextManager[AsyncConnection]:
    """Return the shared database connection context manager."""

    return get_connection()


__all__ = ["get_connection_manager"]
