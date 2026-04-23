from __future__ import annotations

from dataclasses import dataclass, field

from capture.state import CaptureState
from calibration.state import CalibrationState
from core.config import AppConfig
from reconstruction.state import ReconstructionState
from session.state import SessionState


@dataclass(slots=True)
class ApplicationContext:
    config: AppConfig
    capture_state: CaptureState = field(default_factory=CaptureState)
    calibration_state: CalibrationState = field(default_factory=CalibrationState)
    reconstruction_state: ReconstructionState = field(default_factory=ReconstructionState)
    session_state: SessionState = field(default_factory=SessionState)


def build_context(config: AppConfig | None = None) -> ApplicationContext:
    resolved_config = config or AppConfig.load()
    resolved_config.ensure_directories()
    return ApplicationContext(config=resolved_config)
