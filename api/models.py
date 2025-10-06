from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import pydantic

from domain.pipeline import PipelineState, PipelineStatus

BaseModel = pydantic.BaseModel
ConfigDict = getattr(pydantic, "ConfigDict", dict)
_HAS_MODEL_VALIDATE = hasattr(BaseModel, "model_validate")


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


class PlanQueueStatusResponse(BaseModel):
    """Metadata about treatment queues referencing a plan."""

    enqueued: bool
    filas: Optional[int] = None
    users: Optional[int] = None
    lotes: Optional[int] = None


class PlanSummaryResponse(BaseModel):
    """Represents a single row shown in the plans dashboard."""

    plan_id: Optional[UUID] = None
    number: str
    document: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = None
    days_overdue: Optional[int] = None
    balance: Optional[Decimal] = None
    status_date: Optional[date] = None
    em_tratamento: bool = False
    treatment_queue: Optional[PlanQueueStatusResponse] = None
    blocked: bool = False
    blocked_at: Optional[datetime] = None
    unblocked_at: Optional[datetime] = None
    block_reason: Optional[str] = None


class PlanDetailResponse(BaseModel):
    """Full set of fields shown in the plan details pane."""

    plan_id: UUID
    numero_plano: str
    razao_social: Optional[str] = None
    documento: Optional[str] = None
    tipo_doc: Optional[str] = None
    tipo_plano: Optional[str] = None
    resolucao: Optional[str] = None
    situacao: Optional[str] = None
    competencia_ini: Optional[date] = None
    competencia_fim: Optional[date] = None
    atraso_desde: Optional[date] = None
    dias_em_atraso: Optional[int] = None
    saldo_total: Optional[Decimal] = None
    last_update_at: Optional[datetime] = None
    em_tratamento: bool = False
    bloqueado: bool = False
    rescisao_comunicada: bool = False


class PlanBlockRequest(BaseModel):
    """Payload accepted to block one or more plans."""

    plano_ids: list[UUID]
    motivo: Optional[str] = None
    expires_at: Optional[datetime] = None


class PlanBlockResponse(BaseModel):
    """Response after attempting to block plans."""

    ok: bool
    blocked_count: int


class PlanUnblockRequest(BaseModel):
    """Payload accepted to unblock plans."""

    plano_ids: list[UUID]


class PlanUnblockResponse(BaseModel):
    """Response after attempting to unblock plans."""

    ok: bool
    unblocked_count: int


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
    items_seeded: int
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
