from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from models.types import CalibrationBundle


@dataclass(slots=True)
class CalibrationState:
    pattern: str = "chessboard"
    board_shape: tuple[int, int] = (9, 6)
    square_size_m: float = 0.024
    workflow_mode: str = "intrinsics"
    sample_counts: dict[str, int] = field(default_factory=dict)
    bundle: CalibrationBundle | None = None
    profile_path: Path | None = None
    trust_state: str = "unavailable"
