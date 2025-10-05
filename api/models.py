from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Optional, cast
from uuid import UUID

import pydantic

from domain.pipeline import PipelineState, PipelineStatus

BaseModel = pydantic.BaseModel
_HAS_MODEL_VALIDATE = hasattr(BaseModel, "model_validate")

_CONFIG_DICT_FACTORY = getattr(pydantic, "ConfigDict", None)

if _HAS_MODEL_VALIDATE:
    if _CONFIG_DICT_FACTORY is not None:
        _PIPELINE_MODEL_CONFIG: Any = _CONFIG_DICT_FACTORY(from_attributes=True)
    else:  # pragma: no cover - fallback when ConfigDict missing
        _PIPELINE_MODEL_CONFIG = {"from_attributes": True}
else:
    _PIPELINE_MODEL_CONFIG = None


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

    if _PIPELINE_MODEL_CONFIG is not None:
        model_config: ClassVar[Any] = _PIPELINE_MODEL_CONFIG
    else:  # pragma: no cover - exercised when running with Pydantic v1

        class Config:
            orm_mode = True

    @classmethod
    def from_state(cls, state: PipelineState) -> "PipelineStateResponse":
        """Build response model from a domain state object."""

        if _HAS_MODEL_VALIDATE:
            return cls.model_validate(state)
        return cast("PipelineStateResponse", cls.from_orm(state))


class PlanQueueStatusResponse(BaseModel):
    """Metadata about treatment queues referencing a plan."""

    enqueued: bool
    filas: Optional[int] = None
    users: Optional[int] = None
    lotes: Optional[int] = None


class PlanSummaryResponse(BaseModel):
    """Represents a single row shown in the plans dashboard."""

    plan_id: Optional[str] = None
    number: str
    document: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
    days_overdue: Optional[int] = None
    balance: Optional[Decimal] = None
    status_date: Optional[date] = None
    treatment_queue: Optional[PlanQueueStatusResponse] = None
    in_treatment: bool = False
    blocked: bool = False
    blocked_at: Optional[datetime] = None
    unlocked_at: Optional[datetime] = None
    block_reason: Optional[str] = None


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
    saldo_key: str | None = None
    saldo_min: int | None = None
    dt_sit_range: str | None = None


class PlansResponse(BaseModel):
    """Container returned by the plans listing endpoint."""

    items: list[PlanSummaryResponse]
    total: int
    paging: PlansPaging | None = None
    filters: PlansFilters | None = None


class PlanBlockRequest(BaseModel):
    """Payload to block an individual plan."""

    plano_id: UUID
    motivo: Optional[str] = None
    expires_at: Optional[datetime] = None


class PlanBlockResponse(BaseModel):
    """Response returned after attempting to block a plan."""

    plano_id: UUID
    blocked: bool
    message: Optional[str] = None


class PlanUnblockRequest(BaseModel):
    """Payload to unblock an individual plan."""

    plano_id: UUID


class PlanUnblockResponse(BaseModel):
    """Response returned after attempting to unblock a plan."""

    plano_id: UUID
    blocked: bool


class TreatmentTotalsResponse(BaseModel):
    """Aggregated counts for a treatment batch."""

    pending: int
    processed: int
    skipped: int


class TreatmentStateResponse(BaseModel):
    """High-level status for the treatment workflow."""

    has_open: bool
    lote_id: UUID | None = None
    totals: TreatmentTotalsResponse


class TreatmentMigrationResponse(BaseModel):
    """Payload returned after requesting a treatment snapshot."""

    lote_id: UUID
    affected: int
    created: bool | None = None


class TreatmentItemResponse(BaseModel):
    """Single item inside a treatment batch."""

    lote_id: UUID
    plano_id: UUID
    number: str
    document: Optional[str] = None
    company_name: Optional[str] = None
    balance: Optional[Decimal] = None
    status_date: Optional[date] = None
    status: str
    situacao_codigo: Optional[str] = None


class TreatmentPagingResponse(BaseModel):
    """Keyset paging metadata for treatment items."""

    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_more: bool
    page_size: int


class TreatmentItemsResponse(BaseModel):
    """Response structure for the treatment items endpoint."""

    items: list[TreatmentItemResponse]
    paging: TreatmentPagingResponse


class TreatmentMigrateRequest(BaseModel):
    """Payload accepted by the treatment migration endpoint."""

    grid: str = "PLANOS_P_RESCISAO"
    filters: dict[str, Any] | None = None


class TreatmentRescindRequest(BaseModel):
    """Payload for plan rescission within a batch."""

    lote_id: UUID
    plano_id: UUID
    data_rescisao: datetime


class TreatmentSkipRequest(BaseModel):
    """Payload to mark an item as skipped."""

    lote_id: UUID
    plano_id: UUID


class TreatmentCloseRequest(BaseModel):
    """Payload for closing a treatment batch."""

    lote_id: UUID


class PipelineStatusViewResponse(BaseModel):
    """Status information for the last pipeline run, per tenant/job."""

    job_name: str
    status: str
    last_update_at: Optional[datetime] = None
    duration_text: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
