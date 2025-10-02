"""Compatibility layer exposing the current project under the ``sirep`` namespace."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Iterable


def _ensure(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _alias(base: str, targets: Iterable[str]) -> None:
    root = _ensure(base)
    for target in targets:
        module = importlib.import_module(target)
        alias_name = f"{base}.{target}"
        sys.modules[alias_name] = module

        parent = root
        prefix = base
        parts = target.split(".")
        for part in parts[:-1]:
            prefix = f"{prefix}.{part}"
            parent = _ensure(prefix)
        setattr(parent, parts[-1], module)


_alias(
    __name__,
    (
        "app",
        "app.api",
        "api",
        "api.app",
        "api.models",
        "api.routers",
        "api.routers.pipeline",
        "api.routers.plans",
        "domain",
        "domain.enums",
        "domain.pipeline",
        "infra",
        "infra.config",
        "infra.repositories",
        "infra.runtime_credentials",
        "services",
        "services.base",
        "services.orchestrator",
        "services.pw3270",
        "services.gestao_base",
        "services.gestao_base.collectors",
        "services.gestao_base.models",
        "services.gestao_base.parcelas",
        "services.gestao_base.persistence",
        "services.gestao_base.pipeline",
        "services.gestao_base.portal",
        "services.gestao_base.service",
        "services.gestao_base.terminal",
        "services.gestao_base.utils",
    ),
)

__all__ = [
    "app",
    "api",
    "domain",
    "infra",
    "services",
]
