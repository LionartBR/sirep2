from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.pipeline import PipelineState, PipelineStatus


@dataclass(slots=True)
class ExtendedPipelineState(PipelineState):
    """Specialised pipeline state with extra diagnostic information."""

    details: str | None = None


def test_copy_preserves_subclass_and_payload() -> None:
    started_at = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    finished_at = datetime(2024, 1, 1, 12, 5, tzinfo=timezone.utc)
    state = ExtendedPipelineState(
        status=PipelineStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=finished_at,
        message="Done",
        details="extra",
    )

    cloned = state.copy()

    assert cloned is not state
    assert isinstance(cloned, ExtendedPipelineState)
    assert cloned == state

    cloned.message = "Updated"
    cloned.details = "changed"

    assert state.message == "Done"
    assert state.details == "extra"
