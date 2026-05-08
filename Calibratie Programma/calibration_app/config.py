from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .legacy_bridge import app_root


@dataclass(slots=True)
class CalibrationAppConfig:
    app_name: str = "PhysioMotion Calibratie"
    app_root: Path = field(default_factory=app_root)
    config_path: Path | None = None
    projects_dir: Path | None = None
    logs_dir: Path | None = None
    default_sources_csv: str = "0"
    default_capture_fps: float = 20.0

    def __post_init__(self) -> None:
        if self.config_path is None:
            self.config_path = self.app_root / "calibratie.config.json"
        if self.projects_dir is None:
            self.projects_dir = self.app_root / "projects"
        if self.logs_dir is None:
            self.logs_dir = self.app_root / "logs"

    @classmethod
    def load(cls, config_path: Path | None = None) -> "CalibrationAppConfig":
        config = cls(config_path=config_path)
        config.load_preferences()
        config.ensure_directories()
        return config

    def load_preferences(self) -> None:
        path = self.config_path
        if path is None or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        sources_csv = payload.get("default_sources_csv")
        if isinstance(sources_csv, str) and sources_csv.strip():
            self.default_sources_csv = sources_csv.strip()
        capture_fps = payload.get("default_capture_fps")
        if isinstance(capture_fps, (int, float)):
            self.default_capture_fps = max(1.0, float(capture_fps))

    def save(self) -> None:
        path = self.config_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "default_sources_csv": self.default_sources_csv,
            "default_capture_fps": self.default_capture_fps,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def ensure_directories(self) -> None:
        for directory in (self.projects_dir, self.logs_dir):
            if directory is not None:
                directory.mkdir(parents=True, exist_ok=True)
