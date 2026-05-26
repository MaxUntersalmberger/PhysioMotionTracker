from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class AppConfig:
    app_name: str = "Camera Calibration"
    app_root: Path = field(default_factory=_app_root)
    target_fps: float = 30.0
    default_camera_csv: str = "0"
    calibration_dir: Path = field(default_factory=lambda: _app_root() / "calibration")
    logs_dir: Path = field(default_factory=lambda: _app_root() / "logs")

    def ensure_directories(self) -> None:
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
