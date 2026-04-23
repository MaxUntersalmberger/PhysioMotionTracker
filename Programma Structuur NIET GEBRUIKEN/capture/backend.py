from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from models.types import CameraProbeResult, CameraSourceConfig, FramePacket


@dataclass(slots=True)
class CaptureBatch:
    frames: dict[str, FramePacket]
    capture_timestamp_sec: float
    capture_ms: float
    dropped_sources: list[str] = field(default_factory=list)
    probe_results: dict[str, CameraProbeResult] = field(default_factory=dict)


class OpenCVCaptureSession:
    def __init__(
        self,
        sources: Sequence[CameraSourceConfig],
        target_fps: float = 20.0,
        max_frame_width: int = 0,
        requested_width: int = 0,
        requested_height: int = 0,
        loop_video: bool = False,
    ) -> None:
        self._sources = [source for source in sources if source.enabled]
        self._target_fps = max(1.0, float(target_fps))
        self._max_frame_width = max(0, int(max_frame_width))
        self._requested_width = max(0, int(requested_width))
        self._requested_height = max(0, int(requested_height))
        self._loop_video = bool(loop_video)
        self._captures: dict[str, Any] = {}
        self._frame_indices: dict[str, int] = {source.source_id: 0 for source in self._sources}
        self._probe_results: dict[str, CameraProbeResult] = {}

    @property
    def is_open(self) -> bool:
        return bool(self._captures)

    @property
    def target_fps(self) -> float:
        return self._target_fps

    def open(self) -> dict[str, CameraProbeResult]:
        if self._captures:
            return dict(self._probe_results)

        try:
            for index, source in enumerate(self._sources):
                capture, probe = self._open_source(source, index)
                if not probe.opened:
                    capture.release()
                    raise RuntimeError(f"Could not open source '{source.source_id}' ({source.uri}).")
                self._captures[source.source_id] = capture
                self._probe_results[source.source_id] = probe
            return dict(self._probe_results)
        except Exception:
            self.close()
            raise

    def probe_sources(self) -> dict[str, CameraProbeResult]:
        if self._probe_results:
            return dict(self._probe_results)

        self._ensure_cv2()
        probe_results: dict[str, CameraProbeResult] = {}
        for index, source in enumerate(self._sources):
            capture, probe = self._open_source(source, index)
            probe_results[source.source_id] = probe
            capture.release()
        return probe_results

    def read_batch(self) -> CaptureBatch:
        if not self._captures:
            self.open()

        assert cv2 is not None
        batch_start = time.perf_counter()
        capture_timestamp_sec = time.time()
        frames: dict[str, FramePacket] = {}
        dropped_sources: list[str] = []

        for source in self._sources:
            capture = self._captures.get(source.source_id)
            if capture is None:
                dropped_sources.append(source.source_id)
                continue

            ok, frame = capture.read()
            if not ok and source.kind == "video" and self._loop_video:
                capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = capture.read()

            if not ok:
                dropped_sources.append(source.source_id)
                continue

            self._frame_indices[source.source_id] += 1
            resized_frame = self._resize_frame(frame)
            frames[source.source_id] = FramePacket(
                source_id=source.source_id,
                frame_index=self._frame_indices[source.source_id],
                timestamp_sec=capture_timestamp_sec,
                frame_data=resized_frame,
            )

        capture_ms = (time.perf_counter() - batch_start) * 1000.0
        return CaptureBatch(
            frames=frames,
            capture_timestamp_sec=capture_timestamp_sec,
            capture_ms=capture_ms,
            dropped_sources=dropped_sources,
            probe_results=dict(self._probe_results),
        )

    def close(self) -> None:
        for capture in self._captures.values():
            capture.release()
        self._captures.clear()

    def _open_source(self, source: CameraSourceConfig, index: int) -> tuple[Any, CameraProbeResult]:
        cv2_module = self._ensure_cv2()
        uri = self._resolve_uri(source)

        for backend_name, backend_flag in self._backend_candidates(source, cv2_module):
            capture = (
                cv2_module.VideoCapture(uri, backend_flag)
                if backend_flag is not None
                else cv2_module.VideoCapture(uri)
            )
            if capture.isOpened():
                self._apply_capture_settings(capture, cv2_module)
                return capture, self._build_probe_result(index, capture, backend_name, True, cv2_module)
            capture.release()

        fallback = cv2_module.VideoCapture(uri)
        probe = self._build_probe_result(index, fallback, "unavailable", fallback.isOpened(), cv2_module)
        return fallback, probe

    def _apply_capture_settings(self, capture: Any, cv2_module: Any) -> None:
        capture.set(cv2_module.CAP_PROP_BUFFERSIZE, 1)
        if self._requested_width > 0:
            capture.set(cv2_module.CAP_PROP_FRAME_WIDTH, float(self._requested_width))
        if self._requested_height > 0:
            capture.set(cv2_module.CAP_PROP_FRAME_HEIGHT, float(self._requested_height))

    def _build_probe_result(
        self,
        index: int,
        capture: Any,
        backend_name: str,
        opened: bool,
        cv2_module: Any,
    ) -> CameraProbeResult:
        if opened:
            width = int(capture.get(cv2_module.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2_module.CAP_PROP_FRAME_HEIGHT))
        else:
            width = 0
            height = 0
        return CameraProbeResult(index=index, opened=opened, width=width, height=height, backend=backend_name)

    def _resize_frame(self, frame: Any) -> Any:
        if self._max_frame_width <= 0:
            return frame

        height, width = frame.shape[:2]
        if width <= 0 or width <= self._max_frame_width:
            return frame

        cv2_module = self._ensure_cv2()
        scale = self._max_frame_width / float(width)
        return cv2_module.resize(
            frame,
            (self._max_frame_width, max(1, int(height * scale))),
            interpolation=cv2_module.INTER_AREA,
        )

    def _backend_candidates(
        self,
        source: CameraSourceConfig,
        cv2_module: Any,
    ) -> list[tuple[str, int | None]]:
        if source.kind != "webcam":
            return [("default", None)]

        candidates: list[tuple[str, int | None]] = []
        if os.name == "nt":
            if hasattr(cv2_module, "CAP_MSMF"):
                candidates.append(("MSMF", cv2_module.CAP_MSMF))
            if hasattr(cv2_module, "CAP_DSHOW"):
                candidates.append(("DSHOW", cv2_module.CAP_DSHOW))
        candidates.append(("default", None))
        return candidates

    def _resolve_uri(self, source: CameraSourceConfig) -> Any:
        if source.kind == "webcam":
            return int(source.uri)
        if isinstance(source.uri, Path):
            return str(source.uri)
        return source.uri

    def _ensure_cv2(self) -> Any:
        if cv2 is None:  # pragma: no cover - dependency guard
            raise RuntimeError("OpenCV is required for capture. Install opencv-python in this environment.")
        return cv2


def describe_capture_batch(batch: CaptureBatch, sources: Sequence[CameraSourceConfig] | None = None) -> str:
    source_lookup = {source.source_id: source for source in sources or []}
    lines = [
        "Capture sample run complete",
        f"Active sources: {len(batch.frames)}",
        f"Capture timestamp: {batch.capture_timestamp_sec:.3f}s",
        f"Capture latency: {batch.capture_ms:.2f} ms",
    ]

    if batch.dropped_sources:
        lines.append("Dropped sources: " + ", ".join(batch.dropped_sources))

    if batch.probe_results:
        lines.append("Probes:")
        for source_id, probe in batch.probe_results.items():
            source = source_lookup.get(source_id)
            label = source.label if source and source.label else source_id
            status = "opened" if probe.opened else "failed"
            lines.append(
                f"- {source_id} ({label}): {status}, backend={probe.backend}, size={probe.width}x{probe.height}"
            )

    if batch.frames:
        lines.append("Frames:")
        for source_id, frame in batch.frames.items():
            source = source_lookup.get(source_id)
            label = source.label if source and source.label else source_id
            payload = frame.frame_data
            shape = getattr(payload, "shape", None)
            dtype = getattr(payload, "dtype", None)
            shape_text = f", shape={tuple(shape)}" if shape is not None else ""
            dtype_text = f", dtype={dtype}" if dtype is not None else ""
            lines.append(
                f"- {source_id} ({label}): frame_index={frame.frame_index}{shape_text}{dtype_text}"
            )

    return "\n".join(lines)
