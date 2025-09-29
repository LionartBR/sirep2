from __future__ import annotations

import importlib
import sys

from .base import ServiceResult, StepJobContext, StepJobOutcome, run_step_job

__all__ = ["ServiceResult", "StepJobContext", "StepJobOutcome", "run_step_job"]

# Expõe o pacote legado ``services.gestao_base`` sob o namespace atual.
_gestao_base = importlib.import_module("services.gestao_base")
sys.modules[__name__ + ".gestao_base"] = _gestao_base
