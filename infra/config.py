from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Configurações globais de execução."""

    DRY_RUN: bool = False
    debug: bool = True


def _str_to_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    texto = raw.strip().lower()
    if texto in {"1", "true", "t", "yes", "y"}:
        return True
    if texto in {"0", "false", "f", "no", "n"}:
        return False
    return default


settings = Settings(
    DRY_RUN=_str_to_bool(os.getenv("DRY_RUN"), default=False),
    debug=_str_to_bool(os.getenv("DEBUG"), default=True),
)


__all__ = ["Settings", "settings"]
