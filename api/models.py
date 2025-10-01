from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

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

    model_config = {"from_attributes": True}

    @classmethod
    def from_state(cls, state: PipelineState) -> "PipelineStateResponse":
        """Build response model from a domain state object."""

        return cls.model_validate(state)


class PlanSummaryResponse(BaseModel):
    """Represents a single row shown in the plans dashboard."""

    number: str
    document: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
    days_overdue: Optional[int] = None
    balance: Optional[Decimal] = None
    status_date: Optional[date] = None


class PlansResponse(BaseModel):
    """Container returned by the plans listing endpoint."""

    items: list[PlanSummaryResponse]
    total: int
