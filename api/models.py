from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from domain.pipeline import PipelineState, PipelineStatus


class PipelineStartPayload(BaseModel):
    """Payload accepted by the pipeline start endpoint."""

    matricula: Optional[str] = None
    senha: Optional[str] = None


class PipelineStateResponse(BaseModel):
    """Serialised representation of the pipeline state."""

    status: PipelineStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_state(cls, state: PipelineState) -> "PipelineStateResponse":
        """Build response model from a domain state object."""

        return cls.model_validate(state)
