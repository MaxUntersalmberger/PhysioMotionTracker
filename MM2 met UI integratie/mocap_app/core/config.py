from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_settings_path() -> Path:
    return _app_root() / "calibration" / "app_settings.json"


def _path_relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def _portable_path(path: Path, saved_root: Path | None, current_root: Path) -> Path:
    if not path.is_absolute():
        return current_root / path
    if saved_root is None:
        return path
    relative = _path_relative_to(path, saved_root)
    if relative is None:
        return path
    return current_root / relative


@dataclass(slots=True)
class AppConfig:
    app_name: str = "PhysioMotionTracker"
    app_root: Path = field(default_factory=_app_root)
    target_fps: float = 30.0
    default_camera_csv: str = "0"
    calibration_dir: Path = field(default_factory=lambda: _app_root() / "calibration")
    logs_dir: Path = field(default_factory=lambda: _app_root() / "logs")
    sessions_dir: Path = field(default_factory=lambda: _app_root() / "sessions")
    default_sessions_dir: Path = field(default_factory=lambda: _app_root() / "sessions")
    ui_scale: float = 0.70
    camera_labels: dict[str, str] = field(default_factory=dict)

    def ensure_directories(self) -> None:
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        settings_path = path or _default_settings_path()
        config = cls()
        if not settings_path.exists():
            return config
        try:
            data: dict[str, Any] = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read settings %s: %s", settings_path, exc)
            return config

        current_root = _app_root()
        saved_root_value = data.get("app_root")
        saved_root = Path(saved_root_value) if isinstance(saved_root_value, str) else None

        for key, value in data.items():
            if not hasattr(config, key):
                continue
            current = getattr(config, key)
            if isinstance(current, Path) and isinstance(value, str):
                if key == "app_root":
                    setattr(config, key, current_root)
                else:
                    setattr(config, key, _portable_path(Path(value), saved_root, current_root))
            else:
                setattr(config, key, value)
        config.app_root = current_root
        return config

    def save(self, path: Path | None = None) -> None:
        settings_path = path or _default_settings_path()
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        for key, value in asdict(self).items():
            if isinstance(value, Path):
                data[key] = str(value)
            else:
                data[key] = value
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
