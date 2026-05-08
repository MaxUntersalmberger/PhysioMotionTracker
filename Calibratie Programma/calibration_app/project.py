from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_SCHEMA_VERSION = 1


@dataclass(slots=True)
class CalibrationProject:
    name: str
    root_dir: Path
    created_at_iso: str
    updated_at_iso: str
    sources_csv: str = "0"
    target_fps: float = 20.0
    calibration_profile_path: Path | None = None
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def project_file(self) -> Path:
        return self.root_dir / "calibration_project.json"

    @property
    def calibration_dir(self) -> Path:
        return self.root_dir / "calibration"

    @property
    def exports_dir(self) -> Path:
        return self.root_dir / "exports"

    @property
    def default_profile_path(self) -> Path:
        return self.calibration_dir / "current_calibration.json"


class CalibrationProjectRepository:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def create(self, name: str, sources_csv: str = "0", target_fps: float = 20.0) -> CalibrationProject:
        now = datetime.now().isoformat(timespec="seconds")
        project_dir = self._unique_project_dir(_safe_filename(name) or "calibration_project")
        project = CalibrationProject(
            name=name.strip() or "Calibration Project",
            root_dir=project_dir,
            created_at_iso=now,
            updated_at_iso=now,
            sources_csv=sources_csv.strip() or "0",
            target_fps=max(1.0, float(target_fps)),
            calibration_profile_path=project_dir / "calibration" / "current_calibration.json",
        )
        self.save(project)
        return project

    def load(self, project_dir: Path) -> CalibrationProject:
        root_dir = project_dir.resolve()
        path = root_dir / "calibration_project.json"
        if not path.exists():
            raise FileNotFoundError(f"No calibration_project.json found in {root_dir}.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid calibration project manifest: {path}")
        notes = payload.get("notes")
        metadata = payload.get("metadata")
        created = str(payload.get("created_at_iso") or datetime.now().isoformat(timespec="seconds"))
        return CalibrationProject(
            name=str(payload.get("name") or root_dir.name),
            root_dir=root_dir,
            created_at_iso=created,
            updated_at_iso=str(payload.get("updated_at_iso") or created),
            sources_csv=str(payload.get("sources_csv") or "0"),
            target_fps=float(payload.get("target_fps") or 20.0),
            calibration_profile_path=_parse_optional_path(payload.get("calibration_profile_path"), root_dir),
            notes=[str(item) for item in notes] if isinstance(notes, list) else [],
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def save(self, project: CalibrationProject) -> Path:
        project.root_dir.mkdir(parents=True, exist_ok=True)
        project.calibration_dir.mkdir(parents=True, exist_ok=True)
        project.exports_dir.mkdir(parents=True, exist_ok=True)
        project.updated_at_iso = datetime.now().isoformat(timespec="seconds")
        payload = {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": project.name,
            "created_at_iso": project.created_at_iso,
            "updated_at_iso": project.updated_at_iso,
            "sources_csv": project.sources_csv,
            "target_fps": project.target_fps,
            "calibration_profile_path": _serialize_path(project.calibration_profile_path, project.root_dir),
            "notes": list(project.notes),
            "metadata": dict(project.metadata),
        }
        project.project_file.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return project.project_file

    def _unique_project_dir(self, safe_name: str) -> Path:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = self._base_dir / f"{safe_name}_{stamp}"
        suffix = 1
        while candidate.exists():
            suffix += 1
            candidate = self._base_dir / f"{safe_name}_{stamp}_{suffix}"
        return candidate


def _safe_filename(value: str) -> str:
    cleaned = [character if character.isalnum() or character in {"-", "_"} else "_" for character in value.strip()]
    return "".join(cleaned).strip("._")


def _parse_optional_path(value: Any, root_dir: Path) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else root_dir / path


def _serialize_path(path: Path | None, root_dir: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(root_dir.resolve()))
    except ValueError:
        return str(path)
