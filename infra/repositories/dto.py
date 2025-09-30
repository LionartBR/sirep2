from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class PlanDTO:
    """Representação simplificada de um plano utilizado no pipeline."""

    id: str
    numero_plano: str
    situacao_atual: Optional[str] = None


__all__ = ["PlanDTO"]
