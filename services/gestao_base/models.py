from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Protocol


@dataclass(frozen=True)
class PlanRow:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    nome: str


@dataclass(frozen=True)
class PlanRowEnriched:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    razao_social: str
    saldo_total: str
    cnpj: str
    parcelas_atraso: Optional[List[dict[str, Any]]] = None
    dias_atraso: Optional[int] = None


@dataclass(frozen=True)
class GestaoBaseData:
    rows: List[PlanRowEnriched]
    raw_lines: List[str]
    portal_po: List[dict]
    descartados_974: int


ProgressCallback = Callable[[float, Optional[int], Optional[str]], None]


class GestaoBaseCollector(Protocol):
    def collect(self, progress: Optional[ProgressCallback] = None) -> GestaoBaseData:
        ...
