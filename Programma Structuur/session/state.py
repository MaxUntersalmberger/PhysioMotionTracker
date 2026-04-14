from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from models.types import SessionManifest


@dataclass(slots=True)
class SessionState:
    recording_active: bool = False
    active_session_dir: Path | None = None
    loaded_session_dir: Path | None = None
    loaded_manifest: SessionManifest | None = None
    playback_active: bool = False
