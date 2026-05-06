from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from capture.backend import CaptureBatch
from models.types import FramePacket, SessionManifest
from session.repository import SessionRepository


@dataclass(slots=True)
class SessionFrameLogEntry:
    batch_index: int
    capture_timestamp_sec: float
    capture_ms: float
    frame_indices: dict[str, int] = field(default_factory=dict)
    frame_timestamps_sec: dict[str, float] = field(default_factory=dict)
    dropped_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SessionPlaybackInfo:
    session_dir: Path
    manifest: SessionManifest
    frame_log_entries: int
    available_video_files: dict[str, Path]
    missing_video_sources: list[str]
    notes: list[str] = field(default_factory=list)

    @property
    def is_playable(self) -> bool:
        return bool(self.available_video_files) and not self.missing_video_sources


class SessionPlaybackReader:
    def __init__(
        self,
        manifest_path: Path,
        repository: SessionRepository | None = None,
    ) -> None:
        self._repository = repository or SessionRepository()
        self._manifest_path = self._resolve_manifest_path(manifest_path)
        self._session_dir = self._manifest_path.parent
        manifest = self._repository.load(self._manifest_path)
        if manifest is None:
            raise ValueError(f"Could not load session manifest from {self._manifest_path}.")
        self._manifest = manifest
        self._frame_log_entries = self._load_frame_log_entries()

    @property
    def manifest(self) -> SessionManifest:
        return self._manifest

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def batch_count(self) -> int:
        if self._frame_log_entries:
            return len(self._frame_log_entries)
        return max(0, int(self._manifest.total_frames))

    def info(self) -> SessionPlaybackInfo:
        available_video_files: dict[str, Path] = {}
        missing_video_sources: list[str] = []
        for source_id, relative_path in self._manifest.video_files.items():
            path = self._session_dir / relative_path
            if path.exists():
                available_video_files[source_id] = path
            else:
                missing_video_sources.append(source_id)

        notes: list[str] = []
        if not self._manifest.video_files:
            notes.append("Session manifest does not list recorded video files.")
        if not self._frame_log_entries:
            notes.append("Session does not contain a frame timeline.")
        if missing_video_sources:
            notes.append("Missing video files for: " + ", ".join(missing_video_sources))

        return SessionPlaybackInfo(
            session_dir=self._session_dir,
            manifest=self._manifest,
            frame_log_entries=len(self._frame_log_entries),
            available_video_files=available_video_files,
            missing_video_sources=missing_video_sources,
            notes=notes,
        )

    def iter_batches(self, max_batches: int | None = None) -> Iterator[CaptureBatch]:
        if cv2 is None:  # pragma: no cover - dependency guard
            raise RuntimeError("OpenCV is required for session playback. Install opencv-python in this environment.")

        captures: dict[str, Any] = {}
        try:
            for source_id, relative_path in self._manifest.video_files.items():
                path = self._session_dir / relative_path
                capture = cv2.VideoCapture(str(path))
                if not capture.isOpened():
                    capture.release()
                    raise RuntimeError(f"Could not open recorded video for {source_id}: {path}")
                captures[source_id] = capture

            entries = self._frame_log_entries
            if not entries:
                entries = self._build_fallback_entries(captures)

            yielded = 0
            for entry in entries:
                if max_batches is not None and yielded >= max(0, int(max_batches)):
                    break

                frames: dict[str, FramePacket] = {}
                dropped_sources = list(entry.dropped_sources)
                for source_id, capture in captures.items():
                    ok, frame_data = capture.read()
                    if not ok:
                        dropped_sources.append(source_id)
                        continue

                    frames[source_id] = FramePacket(
                        source_id=source_id,
                        frame_index=int(entry.frame_indices.get(source_id, entry.batch_index)),
                        timestamp_sec=float(entry.frame_timestamps_sec.get(source_id, entry.capture_timestamp_sec)),
                        frame_data=frame_data,
                    )

                if not frames:
                    break

                yielded += 1
                yield CaptureBatch(
                    frames=frames,
                    capture_timestamp_sec=float(entry.capture_timestamp_sec),
                    capture_ms=float(entry.capture_ms),
                    dropped_sources=sorted(set(dropped_sources)),
                )
        finally:
            for capture in captures.values():
                capture.release()

    def read_batch_at(self, batch_index: int) -> CaptureBatch:
        if cv2 is None:  # pragma: no cover - dependency guard
            raise RuntimeError("OpenCV is required for session playback. Install opencv-python in this environment.")

        index = max(0, int(batch_index))
        if self.batch_count and index >= self.batch_count:
            raise IndexError(f"Batch index {index} is outside the recorded session.")

        captures: dict[str, Any] = {}
        try:
            for source_id, relative_path in self._manifest.video_files.items():
                path = self._session_dir / relative_path
                capture = cv2.VideoCapture(str(path))
                if not capture.isOpened():
                    capture.release()
                    raise RuntimeError(f"Could not open recorded video for {source_id}: {path}")
                capture.set(cv2.CAP_PROP_POS_FRAMES, float(index))
                captures[source_id] = capture

            entry = self._entry_at(index, captures)
            frames: dict[str, FramePacket] = {}
            dropped_sources = list(entry.dropped_sources)
            for source_id, capture in captures.items():
                ok, frame_data = capture.read()
                if not ok:
                    dropped_sources.append(source_id)
                    continue
                frames[source_id] = FramePacket(
                    source_id=source_id,
                    frame_index=int(entry.frame_indices.get(source_id, entry.batch_index)),
                    timestamp_sec=float(entry.frame_timestamps_sec.get(source_id, entry.capture_timestamp_sec)),
                    frame_data=frame_data,
                )

            if not frames:
                raise RuntimeError(f"No frames could be read at batch index {index}.")

            return CaptureBatch(
                frames=frames,
                capture_timestamp_sec=float(entry.capture_timestamp_sec),
                capture_ms=float(entry.capture_ms),
                dropped_sources=sorted(set(dropped_sources)),
            )
        finally:
            for capture in captures.values():
                capture.release()

    def _resolve_manifest_path(self, path: Path) -> Path:
        if path.is_dir():
            return self._repository.manifest_path(path)
        return path

    def _load_frame_log_entries(self) -> list[SessionFrameLogEntry]:
        frame_log_file = _frame_log_file_from_manifest(self._manifest)
        path = self._session_dir / frame_log_file
        if not path.exists():
            return []

        entries: list[SessionFrameLogEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(_frame_log_entry_from_payload(payload))
        return entries

    def _build_fallback_entries(self, captures: dict[str, Any]) -> list[SessionFrameLogEntry]:
        fps = self._manifest.fps if self._manifest.fps > 0 else 30.0
        frame_counts: list[int] = []
        for capture in captures.values():
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if cv2 is not None else 0
            if frame_count > 0:
                frame_counts.append(frame_count)

        total_frames = self._manifest.total_frames
        if frame_counts:
            total_frames = max(total_frames, min(frame_counts))

        entries: list[SessionFrameLogEntry] = []
        for index in range(max(0, int(total_frames))):
            batch_index = index + 1
            timestamp_sec = index / fps
            entries.append(
                SessionFrameLogEntry(
                    batch_index=batch_index,
                    capture_timestamp_sec=timestamp_sec,
                    capture_ms=0.0,
                    frame_indices={source_id: batch_index for source_id in captures},
                    frame_timestamps_sec={source_id: timestamp_sec for source_id in captures},
                )
            )
        return entries

    def _entry_at(self, index: int, captures: dict[str, Any]) -> SessionFrameLogEntry:
        if 0 <= index < len(self._frame_log_entries):
            return self._frame_log_entries[index]

        fallback_entries = self._build_fallback_entries(captures)
        if 0 <= index < len(fallback_entries):
            return fallback_entries[index]

        fps = self._manifest.fps if self._manifest.fps > 0 else 30.0
        batch_index = index + 1
        timestamp_sec = index / fps
        return SessionFrameLogEntry(
            batch_index=batch_index,
            capture_timestamp_sec=timestamp_sec,
            capture_ms=0.0,
            frame_indices={source_id: batch_index for source_id in self._manifest.video_files},
            frame_timestamps_sec={source_id: timestamp_sec for source_id in self._manifest.video_files},
        )


def summarize_session_playback(path: Path, max_batches: int | None = 3) -> str:
    reader = SessionPlaybackReader(path)
    info = reader.info()
    lines = [
        "Session playback summary",
        f"Session: {info.manifest.session_id}",
        f"Directory: {info.session_dir}",
        f"FPS: {info.manifest.fps:.1f}",
        f"Manifest frames: {info.manifest.total_frames}",
        f"Frame log entries: {info.frame_log_entries}",
        f"Video files: {len(info.available_video_files)}/{len(info.manifest.video_files)}",
    ]
    if info.missing_video_sources:
        lines.append("Missing video sources: " + ", ".join(info.missing_video_sources))
    if info.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in info.notes)

    preview_count = 0
    for batch in reader.iter_batches(max_batches=max_batches):
        preview_count += 1
        frame_text = ", ".join(
            f"{source_id}#{frame.frame_index}" for source_id, frame in sorted(batch.frames.items())
        )
        lines.append(f"Batch {preview_count}: {len(batch.frames)} frame(s) | {frame_text}")
        if batch.dropped_sources:
            lines.append("  Dropped: " + ", ".join(batch.dropped_sources))

    lines.append(f"Previewed batches: {preview_count}")
    return "\n".join(lines)


def _frame_log_file_from_manifest(manifest: SessionManifest) -> str:
    recording = manifest.metadata.get("recording")
    if isinstance(recording, dict):
        frame_log_file = recording.get("frame_log_file")
        if isinstance(frame_log_file, str) and frame_log_file.strip():
            return frame_log_file
    return "frames.jsonl"


def _frame_log_entry_from_payload(payload: dict[str, object]) -> SessionFrameLogEntry:
    return SessionFrameLogEntry(
        batch_index=int(payload.get("batch_index", 0) or 0),
        capture_timestamp_sec=float(payload.get("capture_timestamp_sec", 0.0) or 0.0),
        capture_ms=float(payload.get("capture_ms", 0.0) or 0.0),
        frame_indices=_parse_int_map(payload.get("frame_indices")),
        frame_timestamps_sec=_parse_float_map(payload.get("frame_timestamps_sec")),
        dropped_sources=_parse_string_list(payload.get("dropped_sources")),
    )


def _parse_int_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, int] = {}
    for key, item in value.items():
        try:
            parsed[str(key)] = int(item)
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_float_map(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, float] = {}
    for key, item in value.items():
        try:
            parsed[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return parsed


def _parse_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
