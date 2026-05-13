from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Sequence

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from capture.profiles import CameraControlSettings, apply_camera_controls
from models.types import CameraProbeResult, CameraSourceConfig, FramePacket


@dataclass(slots=True)
class CaptureBatch:
    frames: dict[str, FramePacket]
    capture_timestamp_sec: float
    capture_ms: float
    dropped_sources: list[str] = field(default_factory=list)
    probe_results: dict[str, CameraProbeResult] = field(default_factory=dict)


@dataclass(slots=True)
class _OpenCandidate:
    backend_name: str
    backend_flag: int | None
    fourcc: str | None = None
    use_requested_controls: bool = True


class OpenCVCaptureSession:
    def __init__(
        self,
        sources: Sequence[CameraSourceConfig],
        target_fps: float = 20.0,
        max_frame_width: int = 0,
        requested_width: int = 0,
        requested_height: int = 0,
        requested_fps: float = 0.0,
        exposure: float | None = None,
        gain: float | None = None,
        white_balance: float | None = None,
        auto_exposure: float | None = None,
        loop_video: bool = False,
    ) -> None:
        self._sources = [source for source in sources if source.enabled]
        self._target_fps = max(1.0, float(target_fps))
        self._max_frame_width = max(0, int(max_frame_width))
        self._control_settings = CameraControlSettings(
            width=max(0, int(requested_width)),
            height=max(0, int(requested_height)),
            fps=max(0.0, float(requested_fps or target_fps or 0.0)),
            exposure=exposure,
            gain=gain,
            white_balance=white_balance,
            auto_exposure=auto_exposure,
        )
        self._loop_video = bool(loop_video)
        self._captures: dict[str, Any] = {}
        self._control_status: dict[str, dict[str, bool]] = {}
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
        best_candidate: _OpenCandidate | None = None
        best_probe: CameraProbeResult | None = None

        for candidate in self._open_candidates(source, cv2_module):
            capture, probe = self._open_candidate(source, index, uri, candidate, cv2_module)
            if probe.opened and self._probe_matches_requested_resolution(probe):
                return capture, probe
            if probe.opened and (
                best_probe is None or self._probe_resolution_score(probe) > self._probe_resolution_score(best_probe)
            ):
                best_candidate = candidate
                best_probe = probe
            capture.release()

        if best_candidate is not None:
            capture, probe = self._open_candidate(source, index, uri, best_candidate, cv2_module)
            if probe.opened:
                return capture, probe
            capture.release()

        fallback = cv2_module.VideoCapture(uri)
        fallback_frame_size = self._read_probe_frame_size(source, fallback, force=True)
        fallback_usable = fallback.isOpened() and self._capture_has_usable_probe_frame(source, fallback_frame_size)
        probe = self._build_probe_result(
            source.source_id,
            index,
            fallback,
            "unavailable",
            fallback_usable,
            cv2_module,
            observed_frame_size=fallback_frame_size,
        )
        return fallback, probe

    def _open_candidates(self, source: CameraSourceConfig, cv2_module: Any) -> list[_OpenCandidate]:
        candidates: list[_OpenCandidate] = []
        for backend_name, backend_flag in self._backend_candidates(source, cv2_module):
            for fourcc in self._fourcc_candidates(source):
                candidates.append(_OpenCandidate(backend_name, backend_flag, fourcc, True))
        for backend_name, backend_flag in self._fallback_backend_candidates(source, cv2_module):
            candidates.append(_OpenCandidate(backend_name, backend_flag, None, False))
        return candidates

    def _open_candidate(
        self,
        source: CameraSourceConfig,
        index: int,
        uri: Any,
        candidate: _OpenCandidate,
        cv2_module: Any,
    ) -> tuple[Any, CameraProbeResult]:
        capture = (
            cv2_module.VideoCapture(uri, candidate.backend_flag)
            if candidate.backend_flag is not None
            else cv2_module.VideoCapture(uri)
        )
        if not capture.isOpened():
            probe = self._build_probe_result(
                source.source_id,
                index,
                capture,
                self._candidate_label(candidate),
                False,
                cv2_module,
            )
            return capture, probe

        if candidate.use_requested_controls:
            self._apply_capture_settings(source.source_id, capture, cv2_module, fourcc=candidate.fourcc)
        else:
            self._control_status[source.source_id] = apply_camera_controls(
                capture,
                cv2_module,
                CameraControlSettings(),
            )
        frame_size = self._read_probe_frame_size(source, capture, force=True)
        usable = self._capture_has_usable_probe_frame(source, frame_size)
        probe = self._build_probe_result(
            source.source_id,
            index,
            capture,
            self._candidate_label(candidate),
            usable,
            cv2_module,
            observed_frame_size=frame_size,
        )
        return capture, probe

    def _apply_capture_settings(self, source_id: str, capture: Any, cv2_module: Any, fourcc: str | None = None) -> None:
        settings = replace(self._control_settings, fourcc=fourcc)
        self._control_status[source_id] = apply_camera_controls(capture, cv2_module, settings)

    def _build_probe_result(
        self,
        source_id: str,
        index: int,
        capture: Any,
        backend_name: str,
        opened: bool,
        cv2_module: Any,
        observed_frame_size: tuple[int, int] | None = None,
    ) -> CameraProbeResult:
        if opened:
            width = int(capture.get(cv2_module.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2_module.CAP_PROP_FRAME_HEIGHT))
            if observed_frame_size is not None:
                width, height = observed_frame_size
            fps = float(capture.get(cv2_module.CAP_PROP_FPS)) if hasattr(cv2_module, "CAP_PROP_FPS") else 0.0
            exposure = _read_capture_property(capture, cv2_module, "CAP_PROP_EXPOSURE")
            gain = _read_capture_property(capture, cv2_module, "CAP_PROP_GAIN")
            white_balance = _read_capture_property(capture, cv2_module, "CAP_PROP_WB_TEMPERATURE")
        else:
            width = 0
            height = 0
            fps = 0.0
            exposure = None
            gain = None
            white_balance = None
        return CameraProbeResult(
            index=index,
            opened=opened,
            width=width,
            height=height,
            backend=backend_name,
            fps=fps,
            exposure=exposure,
            gain=gain,
            white_balance=white_balance,
            control_status=dict(self._control_status.get(source_id, {})),
        )

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
            if self._control_settings.width > 0 and self._control_settings.height > 0 and hasattr(cv2_module, "CAP_DSHOW"):
                candidates.append(("DSHOW", cv2_module.CAP_DSHOW))
            if hasattr(cv2_module, "CAP_MSMF"):
                candidates.append(("MSMF", cv2_module.CAP_MSMF))
            if not any(name == "DSHOW" for name, _flag in candidates) and hasattr(cv2_module, "CAP_DSHOW"):
                candidates.append(("DSHOW", cv2_module.CAP_DSHOW))
        candidates.append(("default", None))
        return candidates

    def _fourcc_candidates(self, source: CameraSourceConfig) -> list[str | None]:
        if source.kind != "webcam":
            return [None]
        if self._control_settings.width <= 0 and self._control_settings.height <= 0:
            return [None]
        return ["MJPG", "YUY2", ""]

    def _fallback_backend_candidates(
        self,
        source: CameraSourceConfig,
        cv2_module: Any,
    ) -> list[tuple[str, int | None]]:
        if source.kind != "webcam":
            return []
        candidates: list[tuple[str, int | None]] = []
        if os.name == "nt":
            if hasattr(cv2_module, "CAP_MSMF"):
                candidates.append(("MSMF", cv2_module.CAP_MSMF))
            if hasattr(cv2_module, "CAP_DSHOW"):
                candidates.append(("DSHOW", cv2_module.CAP_DSHOW))
        candidates.append(("default", None))
        return candidates

    def _format_backend_name(self, backend_name: str, fourcc: str | None) -> str:
        if fourcc is None:
            return backend_name
        return f"{backend_name}/{fourcc or 'default'}"

    def _candidate_label(self, candidate: _OpenCandidate) -> str:
        if not candidate.use_requested_controls:
            return f"{candidate.backend_name}/auto-fallback"
        return self._format_backend_name(candidate.backend_name, candidate.fourcc)

    def _read_probe_frame_size(self, source: CameraSourceConfig, capture: Any, force: bool = False) -> tuple[int, int] | None:
        if source.kind != "webcam":
            return None
        if not force and self._control_settings.width <= 0 and self._control_settings.height <= 0:
            return None
        for attempt in range(8):
            ok, frame = capture.read()
            if ok and hasattr(frame, "shape") and len(frame.shape) >= 2:
                height, width = frame.shape[:2]
                return int(width), int(height)
            if attempt < 7:
                time.sleep(0.03)
        return None

    def _capture_has_usable_probe_frame(
        self,
        source: CameraSourceConfig,
        observed_frame_size: tuple[int, int] | None,
    ) -> bool:
        if source.kind != "webcam":
            return True
        return observed_frame_size is not None

    def _probe_matches_requested_resolution(self, probe: CameraProbeResult) -> bool:
        requested_width = self._control_settings.width
        requested_height = self._control_settings.height
        if requested_width <= 0 or requested_height <= 0:
            return True
        return probe.opened and probe.width == requested_width and probe.height == requested_height

    def _probe_resolution_score(self, probe: CameraProbeResult) -> int:
        if not probe.opened:
            return -1
        requested_width = self._control_settings.width
        requested_height = self._control_settings.height
        exact_bonus = 10_000_000 if probe.width == requested_width and probe.height == requested_height else 0
        return exact_bonus + max(0, probe.width) * max(0, probe.height)

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
            fps_text = f", fps={probe.fps:.1f}" if probe.fps > 0 else ""
            lines.append(
                f"- {source_id} ({label}): {status}, backend={probe.backend}, size={probe.width}x{probe.height}{fps_text}"
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


def _read_capture_property(capture: Any, cv2_module: Any, property_name: str) -> float | None:
    if not hasattr(cv2_module, property_name):
        return None
    try:
        value = float(capture.get(getattr(cv2_module, property_name)))
    except Exception:
        return None
    return value
