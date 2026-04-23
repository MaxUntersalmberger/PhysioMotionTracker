from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_DETECTOR_NAME = "mediapipe"
_DETECTOR_NAME_ALIASES = {
    "mediapipe": "mediapipe",
    "mediapipe_pose_detector": "mediapipe",
    "synthetic": "synthetic",
    "synthetic_demo": "synthetic",
    "synthetic_pose_detector": "synthetic",
    "demo": "synthetic",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class AppConfig:
    app_name: str = "Programma Structuur Mocap"
    app_root: Path = field(default_factory=_project_root)
    config_path: Path | None = None
    sessions_dir: Path | None = None
    calibration_dir: Path | None = None
    logs_dir: Path | None = None
    exports_dir: Path | None = None
    models_dir: Path | None = None
    default_sources_csv: str = "0"
    default_capture_fps: float = 20.0
    default_preview_fps: float = 30.0
    default_detector_name: str = DEFAULT_DETECTOR_NAME

    def __post_init__(self) -> None:
        if self.config_path is None:
            self.config_path = self.app_root / "programmastructuur.config.json"
        if self.sessions_dir is None:
            self.sessions_dir = self.app_root / "sessions"
        if self.calibration_dir is None:
            self.calibration_dir = self.app_root / "calibration"
        if self.logs_dir is None:
            self.logs_dir = self.app_root / "logs"
        if self.exports_dir is None:
            self.exports_dir = self.app_root / "exports"
        if self.models_dir is None:
            self.models_dir = self.app_root / "models"
        self.default_detector_name = _normalize_detector_name(self.default_detector_name)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "AppConfig":
        config = cls(config_path=config_path)
        config.load_preferences()
        return config

    def load_preferences(self) -> None:
        path = self.config_path
        if path is None or not path.exists():
            return

        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(raw_data, dict):
            return

        detector_name = raw_data.get("default_detector_name")
        if isinstance(detector_name, str) and detector_name.strip():
            self.default_detector_name = _normalize_detector_name(detector_name)

        sources_csv = raw_data.get("default_sources_csv")
        if isinstance(sources_csv, str) and sources_csv.strip():
            self.default_sources_csv = sources_csv.strip()

        capture_fps = raw_data.get("default_capture_fps")
        if isinstance(capture_fps, (int, float)):
            self.default_capture_fps = float(capture_fps)

        preview_fps = raw_data.get("default_preview_fps")
        if isinstance(preview_fps, (int, float)):
            self.default_preview_fps = float(preview_fps)

    def save(self) -> None:
        path = self.config_path
        if path is None:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "default_detector_name": self.default_detector_name,
            "default_sources_csv": self.default_sources_csv,
            "default_capture_fps": self.default_capture_fps,
            "default_preview_fps": self.default_preview_fps,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def ensure_directories(self) -> None:
        for directory in [
            self.sessions_dir,
            self.calibration_dir,
            self.logs_dir,
            self.exports_dir,
            self.models_dir,
        ]:
            if directory is not None:
                directory.mkdir(parents=True, exist_ok=True)


def _normalize_detector_name(detector_name: str) -> str:
    normalized = detector_name.strip().lower().replace(" ", "_")
    if normalized in {"mediapipe", "synthetic"}:
        return normalized
    return _DETECTOR_NAME_ALIASES.get(normalized, DEFAULT_DETECTOR_NAME)
