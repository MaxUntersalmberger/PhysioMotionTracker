from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class AppConfig:
    app_name: str = "Mocap Studio MVP"
    app_root: Path = field(default_factory=_app_root)
    target_fps: float = 20.0
    default_camera_csv: str = "0,1"
    sessions_dir: Path = field(default_factory=lambda: _app_root() / "sessions")
    calibration_dir: Path = field(default_factory=lambda: _app_root() / "calibration")
    logs_dir: Path = field(default_factory=lambda: _app_root() / "logs")
    models_dir: Path = field(default_factory=lambda: _app_root() / "models")
    use_mediapipe_by_default: bool = True

    def ensure_directories(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
