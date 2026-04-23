from __future__ import annotations

from dataclasses import dataclass, field

from models.types import CameraSourceConfig, RuntimeTuning


@dataclass(slots=True)
class CaptureState:
    sources: list[CameraSourceConfig] = field(default_factory=list)
    live_active: bool = False
    recording_active: bool = False
    runtime_tuning: RuntimeTuning = field(default_factory=RuntimeTuning)
    last_error: str | None = None
