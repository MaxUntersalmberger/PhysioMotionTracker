from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from models.types import CameraSourceConfig, SessionManifest


class SessionRepository:
    def __init__(self, manifest_filename: str = "manifest.json") -> None:
        self._manifest_filename = manifest_filename

    def create_session_id(self, prefix: str = "session") -> str:
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}"

    def session_dir(self, base_dir: Path, session_id: str) -> Path:
        return base_dir / session_id

    def manifest_path(self, session_dir: Path) -> Path:
        return session_dir / self._manifest_filename

    def build_manifest(
        self,
        session_id: str,
        fps: float,
        sources: list[CameraSourceConfig],
        total_frames: int = 0,
        pose_file: str | None = None,
        calibration_file: str | None = None,
        notes: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        video_files: dict[str, str] | None = None,
        created_at_iso: str | None = None,
    ) -> SessionManifest:
        return SessionManifest(
            version=1,
            session_id=session_id,
            created_at_iso=created_at_iso or datetime.now().astimezone().isoformat(timespec="seconds"),
            fps=float(fps),
            sources=list(sources),
            video_files=dict(video_files or {}),
            total_frames=max(0, int(total_frames)),
            pose_file=pose_file,
            calibration_file=calibration_file,
            notes=list(notes or []),
            metadata=dict(metadata or {}),
        )

    def save(self, manifest: SessionManifest, session_dir: Path) -> Path:
        session_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.manifest_path(session_dir)
        payload = self._manifest_to_dict(manifest)
        manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
        return manifest_path

    def load(self, path: Path) -> SessionManifest | None:
        manifest_path = self._resolve_manifest_path(path)
        if manifest_path is None or not manifest_path.exists():
            return None

        try:
            raw_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(raw_data, dict):
            return None

        return self._manifest_from_dict(raw_data)

    def sources_to_csv(self, sources: list[CameraSourceConfig]) -> str:
        return ",".join(str(source.uri) for source in sources)

    def manifest_summary(self, manifest: SessionManifest) -> list[str]:
        lines = [
            f"Session: {manifest.session_id}",
            f"Created: {manifest.created_at_iso}",
            f"FPS: {manifest.fps:.1f}",
            f"Sources: {len(manifest.sources)}",
            f"Total frames: {manifest.total_frames}",
        ]
        if manifest.calibration_file:
            lines.append(f"Calibration: {manifest.calibration_file}")
        if manifest.pose_file:
            lines.append(f"Pose file: {manifest.pose_file}")
        if manifest.notes:
            lines.append("Notes: " + " | ".join(manifest.notes[:3]))
        return lines

    def _resolve_manifest_path(self, path: Path) -> Path | None:
        if path.is_dir():
            candidate = path / self._manifest_filename
            return candidate
        return path

    def _manifest_to_dict(self, manifest: SessionManifest) -> dict[str, object]:
        return {
            "version": manifest.version,
            "session_id": manifest.session_id,
            "created_at_iso": manifest.created_at_iso,
            "fps": manifest.fps,
            "sources": [self._source_to_dict(source) for source in manifest.sources],
            "video_files": dict(manifest.video_files),
            "total_frames": manifest.total_frames,
            "pose_file": manifest.pose_file,
            "calibration_file": manifest.calibration_file,
            "notes": list(manifest.notes),
            "metadata": self._json_safe_value(manifest.metadata),
        }

    def _manifest_from_dict(self, raw_data: dict[str, object]) -> SessionManifest:
        sources_data = raw_data.get("sources", [])
        sources: list[CameraSourceConfig] = []
        if isinstance(sources_data, list):
            for entry in sources_data:
                source = self._source_from_dict(entry)
                if source is not None:
                    sources.append(source)

        notes_data = raw_data.get("notes", [])
        notes = [str(note) for note in notes_data] if isinstance(notes_data, list) else []

        metadata_data = raw_data.get("metadata", {})
        metadata = metadata_data if isinstance(metadata_data, dict) else {}

        video_files_data = raw_data.get("video_files", {})
        video_files = {str(key): str(value) for key, value in video_files_data.items()} if isinstance(video_files_data, dict) else {}

        return SessionManifest(
            version=int(raw_data.get("version", 1) or 1),
            session_id=str(raw_data.get("session_id", "session_unknown")),
            created_at_iso=str(raw_data.get("created_at_iso", datetime.now().astimezone().isoformat(timespec="seconds"))),
            fps=float(raw_data.get("fps", 0.0) or 0.0),
            sources=sources,
            video_files=video_files,
            total_frames=int(raw_data.get("total_frames", 0) or 0),
            pose_file=self._optional_string(raw_data.get("pose_file")),
            calibration_file=self._optional_string(raw_data.get("calibration_file")),
            notes=notes,
            metadata=metadata,
        )

    def _source_to_dict(self, source: CameraSourceConfig) -> dict[str, object]:
        return asdict(source)

    def _source_from_dict(self, raw_entry: object) -> CameraSourceConfig | None:
        if not isinstance(raw_entry, dict):
            return None

        source_id = str(raw_entry.get("source_id", ""))
        kind = str(raw_entry.get("kind", "webcam"))
        uri = raw_entry.get("uri", 0)
        label = str(raw_entry.get("label", ""))
        enabled = bool(raw_entry.get("enabled", True))
        if not source_id:
            return None

        return CameraSourceConfig(source_id=source_id, kind=kind, uri=uri, label=label, enabled=enabled)

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _json_safe_value(self, value: object) -> object:
        if isinstance(value, dict):
            return {str(key): self._json_safe_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe_value(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        return value