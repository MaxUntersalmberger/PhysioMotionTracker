from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from capture.backend import CaptureBatch
from capture.profiles import SystemResourceSnapshot, capture_resource_snapshot
from models.types import CameraSourceConfig


class VideoWriterLike(Protocol):
    def write(self, frame: Any) -> None:
        ...

    def release(self) -> None:
        ...


class VideoWriterFactory(Protocol):
    def __call__(self, path: Path, fps: float, frame_size: tuple[int, int]) -> VideoWriterLike:
        ...


@dataclass(slots=True)
class SessionRecordingStats:
    session_dir: Path
    started_at_iso: str
    stopped_at_iso: str | None = None
    batches_written: int = 0
    dropped_batches: int = 0
    frames_written_by_source: dict[str, int] = field(default_factory=dict)
    dropped_sources: dict[str, int] = field(default_factory=dict)
    video_files: dict[str, str] = field(default_factory=dict)
    frame_log_file: str = "frames.jsonl"
    resource_snapshots: dict[str, SystemResourceSnapshot] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def total_frames(self) -> int:
        if not self.frames_written_by_source:
            return 0
        return max(self.frames_written_by_source.values())


class SessionRecorder:
    """Records synchronized capture batches into a session directory."""

    def __init__(
        self,
        session_dir: Path,
        sources: Sequence[CameraSourceConfig],
        fps: float,
        writer_factory: VideoWriterFactory | None = None,
    ) -> None:
        self._session_dir = session_dir
        self._sources = [source for source in sources if source.enabled]
        self._fps = max(1.0, float(fps))
        self._writer_factory = writer_factory or _create_opencv_video_writer
        self._writers: dict[str, VideoWriterLike] = {}
        self._writer_sizes: dict[str, tuple[int, int]] = {}
        self._frame_log_handle: Any | None = None
        self._is_recording = False
        self._stats = SessionRecordingStats(
            session_dir=session_dir,
            started_at_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start(self) -> SessionRecordingStats:
        if self._is_recording:
            return self.stats()
        if not self._sources:
            raise ValueError("SessionRecorder requires at least one enabled source.")

        self._session_dir.mkdir(parents=True, exist_ok=True)
        (self._session_dir / "video").mkdir(parents=True, exist_ok=True)
        frame_log_path = self._session_dir / self._stats.frame_log_file
        self._frame_log_handle = frame_log_path.open("w", encoding="utf-8")
        self._is_recording = True
        self._stats.resource_snapshots["start"] = capture_resource_snapshot(self._session_dir)
        self._stats.notes.append("Recording started.")
        return self.stats()

    def write_batch(self, batch: CaptureBatch) -> SessionRecordingStats:
        if not self._is_recording:
            raise RuntimeError("Cannot write a capture batch before recording has started.")

        if not batch.frames:
            self._stats.dropped_batches += 1
            return self.stats()

        self._stats.batches_written += 1
        for source_id in batch.dropped_sources:
            self._stats.dropped_sources[source_id] = self._stats.dropped_sources.get(source_id, 0) + 1

        written_frame_indices: dict[str, int] = {}
        written_timestamps: dict[str, float] = {}
        for source_id, frame in batch.frames.items():
            prepared_frame = self._prepare_frame(frame.frame_data)
            writer = self._ensure_writer(source_id, prepared_frame)
            target_size = self._writer_sizes[source_id]
            prepared_frame = self._resize_if_needed(prepared_frame, target_size)
            writer.write(prepared_frame)
            self._stats.frames_written_by_source[source_id] = self._stats.frames_written_by_source.get(source_id, 0) + 1
            written_frame_indices[source_id] = int(frame.frame_index)
            written_timestamps[source_id] = float(frame.timestamp_sec)

        self._write_frame_log(batch, written_frame_indices, written_timestamps)
        return self.stats()

    def add_dropped_batches(self, count: int) -> None:
        self._stats.dropped_batches += max(0, int(count))

    def stop(self) -> SessionRecordingStats:
        if not self._is_recording and self._stats.stopped_at_iso is not None:
            return self.stats()

        for writer in self._writers.values():
            writer.release()
        self._writers.clear()
        self._writer_sizes.clear()

        if self._frame_log_handle is not None:
            self._frame_log_handle.close()
            self._frame_log_handle = None

        self._is_recording = False
        self._stats.stopped_at_iso = datetime.now().astimezone().isoformat(timespec="seconds")
        self._stats.resource_snapshots["stop"] = capture_resource_snapshot(self._session_dir)
        self._stats.notes.append("Recording stopped.")
        return self.stats()

    def stats(self) -> SessionRecordingStats:
        return SessionRecordingStats(
            session_dir=self._stats.session_dir,
            started_at_iso=self._stats.started_at_iso,
            stopped_at_iso=self._stats.stopped_at_iso,
            batches_written=self._stats.batches_written,
            dropped_batches=self._stats.dropped_batches,
            frames_written_by_source=dict(self._stats.frames_written_by_source),
            dropped_sources=dict(self._stats.dropped_sources),
            video_files=dict(self._stats.video_files),
            frame_log_file=self._stats.frame_log_file,
            resource_snapshots=dict(self._stats.resource_snapshots),
            notes=list(self._stats.notes),
        )

    def _ensure_writer(self, source_id: str, frame: np.ndarray) -> VideoWriterLike:
        writer = self._writers.get(source_id)
        if writer is not None:
            return writer

        height, width = frame.shape[:2]
        frame_size = (int(width), int(height))
        filename = f"{_safe_source_id(source_id)}.avi"
        relative_path = Path("video") / filename
        writer = self._writer_factory(self._session_dir / relative_path, self._fps, frame_size)
        self._writers[source_id] = writer
        self._writer_sizes[source_id] = frame_size
        self._stats.video_files[source_id] = relative_path.as_posix()
        return writer

    def _prepare_frame(self, frame_data: Any) -> np.ndarray:
        if frame_data is None or not hasattr(frame_data, "shape"):
            raise ValueError("Cannot record a frame without array-like image data.")

        frame = np.asarray(frame_data)
        if frame.ndim == 2:
            frame = np.stack([frame, frame, frame], axis=2)
        elif frame.ndim == 3 and frame.shape[2] == 1:
            frame = np.repeat(frame, 3, axis=2)
        elif frame.ndim == 3 and frame.shape[2] >= 3:
            frame = frame[:, :, :3]
        else:
            raise ValueError(f"Unsupported frame shape for recording: {frame.shape!r}.")

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        return frame

    def _resize_if_needed(self, frame: np.ndarray, frame_size: tuple[int, int]) -> np.ndarray:
        width, height = frame_size
        current_height, current_width = frame.shape[:2]
        if (current_width, current_height) == frame_size:
            return frame
        if cv2 is None:  # pragma: no cover - dependency guard
            raise RuntimeError("OpenCV is required to resize frames during recording.")
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

    def _write_frame_log(
        self,
        batch: CaptureBatch,
        written_frame_indices: dict[str, int],
        written_timestamps: dict[str, float],
    ) -> None:
        if self._frame_log_handle is None:
            return

        payload = {
            "batch_index": self._stats.batches_written,
            "capture_timestamp_sec": float(batch.capture_timestamp_sec),
            "capture_ms": float(batch.capture_ms),
            "frame_indices": written_frame_indices,
            "frame_timestamps_sec": written_timestamps,
            "dropped_sources": list(batch.dropped_sources),
        }
        self._frame_log_handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        self._frame_log_handle.flush()


def _create_opencv_video_writer(path: Path, fps: float, frame_size: tuple[int, int]) -> VideoWriterLike:
    if cv2 is None:  # pragma: no cover - dependency guard
        raise RuntimeError("OpenCV is required for session recording. Install opencv-python in this environment.")

    path.parent.mkdir(parents=True, exist_ok=True)
    for codec in ("MJPG", "XVID", "mp4v"):
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(str(path), fourcc, float(fps), frame_size)
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError(f"Could not open video writer for {path}.")


def _safe_source_id(source_id: str) -> str:
    cleaned = [character if character.isalnum() or character in {"-", "_"} else "_" for character in source_id]
    filename = "".join(cleaned).strip("._")
    return filename or "source"
