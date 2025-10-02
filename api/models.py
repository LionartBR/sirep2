from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import pydantic

BaseModel = pydantic.BaseModel
ConfigDict = getattr(pydantic, "ConfigDict", dict)
_HAS_MODEL_VALIDATE = hasattr(BaseModel, "model_validate")
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

    if _HAS_MODEL_VALIDATE:
        model_config = ConfigDict(from_attributes=True)
    else:  # pragma: no cover - exercised when running with Pydantic v1

        class Config:  # type: ignore[no-redef]
            orm_mode = True

    @classmethod
    def from_state(cls, state: PipelineState) -> "PipelineStateResponse":
        """Build response model from a domain state object."""

        if _HAS_MODEL_VALIDATE:
            return cls.model_validate(state)
        return cls.from_orm(state)  # type: ignore[return-value]


class PlanSummaryResponse(BaseModel):
    """Represents a single row shown in the plans dashboard."""

    number: str
    document: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
    days_overdue: Optional[int] = None
    balance: Optional[Decimal] = None
    status_date: Optional[date] = None


class PlansPaging(BaseModel):
    """Pagination metadata for the plans listing.

    Designed for keyset navigation while remaining backward compatible
    with existing consumers.
    """

    page: int | None = None
    page_size: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None
    prev_cursor: str | None = None
    showing_from: int | None = None
    showing_to: int | None = None
    total_count: int | None = None
    total_pages: int | None = None


class PlansFilters(BaseModel):
    """Echoes the filters applied to the plans listing."""

    situacao: list[str] | None = None
    dias_min: int | None = None
    saldo_min: int | None = None
    dt_sit_range: str | None = None


class PlansResponse(BaseModel):
    """Container returned by the plans listing endpoint."""

    items: list[PlanSummaryResponse]
    total: int
    paging: PlansPaging | None = None
    filters: PlansFilters | None = None


class PipelineStatusViewResponse(BaseModel):
    """Status information for the last pipeline run, per tenant/job."""

    job_name: str
    status: str
    last_update_at: Optional[datetime] = None
    duration_text: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
