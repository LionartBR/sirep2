from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Optional
from uuid import UUID


@dataclass(frozen=True)
class TreatmentTotals:
    """Aggregated counts of treatment items per status."""

    pending: int = 0
    processed: int = 0
    skipped: int = 0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "TreatmentTotals":
        pending = int(values.get("pending") or 0)
        processed = int(values.get("processed") or 0)
        skipped = int(values.get("skipped") or 0)
        return cls(pending=pending, processed=processed, skipped=skipped)


@dataclass(frozen=True)
class TreatmentBatch:
    """Snapshot batch created for a treatment grid."""

    id: UUID
    grid: str
    status: str
    source_filter: Optional[dict[str, Any]]
    created_at: datetime
    closed_at: Optional[datetime] = None


@dataclass(frozen=True)
class TreatmentState:
    """State representation for the treatment UI."""

    has_open: bool
    lote_id: Optional[UUID]
    totals: TreatmentTotals


@dataclass(frozen=True)
class TreatmentItem:
    """Snapshot entry for a treatment batch."""

    lote_id: UUID
    plano_id: UUID
    numero_plano: str
    documento: Optional[str]
    razao_social: Optional[str]
    saldo: Optional[Decimal]
    dt_situacao: Optional[date]
    situacao_codigo: Optional[str]
    status: str
    processed_at: Optional[datetime]


@dataclass(frozen=True)
class TreatmentMigrationResult:
    """Outcome produced after attempting to seed a treatment batch."""

    lote_id: UUID
    items_seeded: int
    created: bool


__all__ = [
    "TreatmentBatch",
    "TreatmentItem",
    "TreatmentMigrationResult",
    "TreatmentState",
    "TreatmentTotals",
]
