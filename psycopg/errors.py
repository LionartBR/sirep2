"""Exceptions exposed by the psycopg stub."""

from __future__ import annotations


class PsycopgError(Exception):
    """Base class for the stub exceptions."""


class DatabaseError(PsycopgError):
    """Generic database error."""


class UniqueViolation(DatabaseError):
    """Raised when a unique constraint would be violated."""


class InvalidAuthorizationSpecification(DatabaseError):
    """Raised when authentication/authorization fails."""


__all__ = [
    "DatabaseError",
    "InvalidAuthorizationSpecification",
    "PsycopgError",
    "UniqueViolation",
]
