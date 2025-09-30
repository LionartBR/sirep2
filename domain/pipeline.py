from __future__ import annotations

from dataclasses import dataclass, replace
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

        return replace(self)


__all__ = ["PipelineState", "PipelineStatus"]
