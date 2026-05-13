from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.types import CameraProbeResult, CameraSourceConfig

if TYPE_CHECKING:
    from capture.backend import CaptureBatch


@dataclass(slots=True)
class CameraControlSettings:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    fourcc: str | None = None
    exposure: float | None = None
    gain: float | None = None
    white_balance: float | None = None
    auto_exposure: float | None = None


@dataclass(slots=True)
class CameraProfile:
    source_id: str
    label: str
    kind: str
    uri: int | str
    requested: CameraControlSettings = field(default_factory=CameraControlSettings)
    observed_width: int = 0
    observed_height: int = 0
    observed_fps: float = 0.0
    backend: str = ""
    opened: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SynchronizationPolicy:
    max_timestamp_spread_ms: float = 40.0
    max_frame_index_spread: int = 0
    mode: str = "software_timestamp"


@dataclass(slots=True)
class SynchronizationAssessment:
    status: str
    timestamp_spread_ms: float
    frame_index_spread: int
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SystemResourceSnapshot:
    disk_total_gb: float
    disk_free_gb: float
    disk_used_percent: float
    memory_used_percent: float | None = None
    notes: list[str] = field(default_factory=list)


def build_camera_profiles(
    sources: list[CameraSourceConfig],
    probe_results: dict[str, CameraProbeResult],
    requested: CameraControlSettings | None = None,
) -> dict[str, CameraProfile]:
    requested_settings = requested or CameraControlSettings()
    profiles: dict[str, CameraProfile] = {}
    for source in sources:
        probe = probe_results.get(source.source_id)
        notes: list[str] = []
        if probe is None:
            notes.append("No probe result available yet.")
        elif not probe.opened:
            notes.append("Source did not open during probe.")
        elif requested_settings.width > 0 and probe.width != requested_settings.width:
            notes.append(f"Requested width {requested_settings.width}, camera reported {probe.width}.")
        elif requested_settings.height > 0 and probe.height != requested_settings.height:
            notes.append(f"Requested height {requested_settings.height}, camera reported {probe.height}.")

        profiles[source.source_id] = CameraProfile(
            source_id=source.source_id,
            label=source.label or source.source_id,
            kind=source.kind,
            uri=source.uri,
            requested=requested_settings,
            observed_width=probe.width if probe is not None else 0,
            observed_height=probe.height if probe is not None else 0,
            observed_fps=probe.fps if probe is not None else 0.0,
            backend=probe.backend if probe is not None else "",
            opened=probe.opened if probe is not None else False,
            notes=notes,
        )
    return profiles


def assess_batch_synchronization(
    batch: CaptureBatch,
    policy: SynchronizationPolicy | None = None,
) -> SynchronizationAssessment:
    active_policy = policy or SynchronizationPolicy()
    timestamps = [frame.timestamp_sec for frame in batch.frames.values()]
    frame_indices = [frame.frame_index for frame in batch.frames.values()]
    timestamp_spread_ms = (max(timestamps) - min(timestamps)) * 1000.0 if timestamps else 0.0
    frame_index_spread = max(frame_indices) - min(frame_indices) if frame_indices else 0
    notes: list[str] = []
    status = "ready"

    if len(batch.frames) < 2:
        status = "insufficient"
        notes.append("At least two active cameras are required for sync assessment.")
    if timestamp_spread_ms > active_policy.max_timestamp_spread_ms:
        status = "weak"
        notes.append(
            f"Timestamp spread {timestamp_spread_ms:.1f} ms exceeds policy "
            f"{active_policy.max_timestamp_spread_ms:.1f} ms."
        )
    if frame_index_spread > active_policy.max_frame_index_spread:
        status = "weak"
        notes.append(
            f"Frame index spread {frame_index_spread} exceeds policy {active_policy.max_frame_index_spread}."
        )
    if batch.dropped_sources:
        status = "weak"
        notes.append("Dropped sources: " + ", ".join(batch.dropped_sources))
    if not notes and status == "ready":
        notes.append(f"Sync policy passed using {active_policy.mode}.")

    return SynchronizationAssessment(
        status=status,
        timestamp_spread_ms=timestamp_spread_ms,
        frame_index_spread=frame_index_spread,
        notes=notes,
    )


def capture_resource_snapshot(path: Path) -> SystemResourceSnapshot:
    disk_usage = shutil.disk_usage(path)
    total = max(1, disk_usage.total)
    notes: list[str] = []
    memory_used_percent = _memory_percent()
    if memory_used_percent is None:
        notes.append("Memory usage unavailable without psutil or platform API.")

    return SystemResourceSnapshot(
        disk_total_gb=disk_usage.total / (1024**3),
        disk_free_gb=disk_usage.free / (1024**3),
        disk_used_percent=(disk_usage.used / total) * 100.0,
        memory_used_percent=memory_used_percent,
        notes=notes,
    )


def _memory_percent() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return float(psutil.virtual_memory().percent)
    except Exception:
        return None


def apply_camera_controls(capture: Any, cv2_module: Any, settings: CameraControlSettings) -> dict[str, bool]:
    applied: dict[str, bool] = {}
    _set_capture_property(applied, capture, cv2_module, "buffersize", "CAP_PROP_BUFFERSIZE", 1)
    if settings.fourcc:
        _set_capture_fourcc(applied, capture, cv2_module, settings.fourcc)
    elif settings.fourcc is None and (settings.width > 0 or settings.height > 0):
        _set_capture_fourcc(applied, capture, cv2_module, "MJPG")
    if settings.width > 0:
        _set_capture_property(applied, capture, cv2_module, "width", "CAP_PROP_FRAME_WIDTH", settings.width)
    if settings.height > 0:
        _set_capture_property(applied, capture, cv2_module, "height", "CAP_PROP_FRAME_HEIGHT", settings.height)
    if settings.fps > 0:
        _set_capture_property(applied, capture, cv2_module, "fps", "CAP_PROP_FPS", settings.fps)
    if settings.width > 0:
        _set_capture_property(applied, capture, cv2_module, "width", "CAP_PROP_FRAME_WIDTH", settings.width)
    if settings.height > 0:
        _set_capture_property(applied, capture, cv2_module, "height", "CAP_PROP_FRAME_HEIGHT", settings.height)
    if settings.exposure is not None:
        _set_capture_property(applied, capture, cv2_module, "exposure", "CAP_PROP_EXPOSURE", settings.exposure)
    if settings.gain is not None:
        _set_capture_property(applied, capture, cv2_module, "gain", "CAP_PROP_GAIN", settings.gain)
    if settings.white_balance is not None:
        _set_capture_property(
            applied,
            capture,
            cv2_module,
            "white_balance",
            "CAP_PROP_WB_TEMPERATURE",
            settings.white_balance,
        )
    if settings.auto_exposure is not None:
        _set_capture_property(applied, capture, cv2_module, "auto_exposure", "CAP_PROP_AUTO_EXPOSURE", settings.auto_exposure)
    return applied


def _set_capture_fourcc(applied: dict[str, bool], capture: Any, cv2_module: Any, codec: str) -> None:
    if not hasattr(cv2_module, "CAP_PROP_FOURCC") or not hasattr(cv2_module, "VideoWriter_fourcc"):
        applied["fourcc"] = False
        return
    try:
        fourcc = cv2_module.VideoWriter_fourcc(*codec)
        applied["fourcc"] = bool(capture.set(cv2_module.CAP_PROP_FOURCC, fourcc))
    except Exception:
        applied["fourcc"] = False


def _set_capture_property(
    applied: dict[str, bool],
    capture: Any,
    cv2_module: Any,
    label: str,
    property_name: str,
    value: float,
) -> None:
    if not hasattr(cv2_module, property_name):
        applied[label] = False
        return
    property_id = getattr(cv2_module, property_name)
    try:
        applied[label] = bool(capture.set(property_id, float(value)))
    except Exception:
        applied[label] = False
