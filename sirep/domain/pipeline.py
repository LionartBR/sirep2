from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PipelineStatus(str, Enum):
    """Possible lifecycle stages for the ingestion pipeline."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class PipelineState:
    """State snapshot produced by the orchestrator."""

    status: PipelineStatus = PipelineStatus.IDLE
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    message: Optional[str] = None

    def copy(self) -> "PipelineState":
        """Return an immutable copy of the current state."""

        return PipelineState(
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            message=self.message,
        )


__all__ = ["PipelineState", "PipelineStatus"]
