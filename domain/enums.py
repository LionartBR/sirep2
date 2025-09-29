from __future__ import annotations

from enum import Enum


class Step(str, Enum):
    """Enumeração com as etapas suportadas pelo pipeline de captura."""

    ETAPA_1 = "ETAPA_1"
    ETAPA_2 = "ETAPA_2"
    ETAPA_3 = "ETAPA_3"
    ETAPA_4 = "ETAPA_4"


class PlanStatus(str, Enum):
    """Representa o status consolidado do plano na aplicação."""

    EM_DIA = "EM_DIA"
    PASSIVEL_RESC = "PASSIVEL_RESC"
    NAO_RESCINDIDO = "NAO_RESCINDIDO"
    RESCINDIDO = "RESCINDIDO"
    ESPECIAL = "ESPECIAL"
    LIQUIDADO = "LIQUIDADO"


__all__ = ["PlanStatus", "Step"]
