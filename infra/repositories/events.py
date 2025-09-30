from __future__ import annotations

from psycopg import Connection

from domain.enums import Step
from infra.audit import log_event


class EventsRepository:
    """Persiste eventos de auditoria associados a planos."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def log(self, entity_id: str, step: Step | str, message: str) -> None:
        event_type = step.value if isinstance(step, Step) else str(step)
        log_event(
            self._conn,
            entity="plano",
            entity_id=entity_id,
            event_type=event_type,
            severity="info",
            message=message,
            data={},
        )


__all__ = ["EventsRepository"]
