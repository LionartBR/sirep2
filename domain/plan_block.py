from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanBlockResult:
    """Outcome summary after attempting to block plans."""

    blocked_count: int = 0


@dataclass(frozen=True)
class PlanUnblockResult:
    """Outcome summary after attempting to unblock plans."""

    unblocked_count: int = 0


__all__ = ["PlanBlockResult", "PlanUnblockResult"]
