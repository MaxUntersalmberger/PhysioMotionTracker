from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from .legacy_bridge import ensure_legacy_path

ensure_legacy_path()

from calibration.manager import CalibrationCaptureResult, CalibrationManager  # noqa: E402
from capture.backend import CaptureBatch, OpenCVCaptureSession  # noqa: E402
from models.types import CameraProbeResult, CameraSourceConfig  # noqa: E402


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _CalibrationAnalysisJob:
    batch: CaptureBatch
    record_sample: bool
    capture_mode: str


@dataclass(slots=True)
class CalibrationAnalysisOutcome:
    result: CalibrationCaptureResult
    record_sample: bool
    frame_index: int
    capture_mode: str


class CalibrationAnalysisWorker(QThread):
    result_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(self, calibration_manager: CalibrationManager) -> None:
        super().__init__()
        self._calibration_manager = calibration_manager
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._priority_job: _CalibrationAnalysisJob | None = None
        self._latest_live_job: _CalibrationAnalysisJob | None = None

    def stop(self) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()

    def submit_batch(self, batch: CaptureBatch, record_sample: bool = False, capture_mode: str = "intrinsics") -> None:
        if not batch.frames:
            return

        job = _CalibrationAnalysisJob(batch=batch, record_sample=record_sample, capture_mode=capture_mode)
        with self._condition:
            if record_sample:
                self._priority_job = job
            else:
                self._latest_live_job = job
            self._condition.notify()

    def run(self) -> None:
        self.state_changed.emit("calibration_analysis_started")
        try:
            while not self._stop_event.is_set():
                with self._condition:
                    while self._priority_job is None and self._latest_live_job is None and not self._stop_event.is_set():
                        self._condition.wait(timeout=0.2)
                    if self._stop_event.is_set():
                        break
                    job = self._priority_job or self._latest_live_job
                    if self._priority_job is not None:
                        self._priority_job = None
                    else:
                        self._latest_live_job = None

                if job is None:
                    continue

                try:
                    result = self._calibration_manager.capture_frames(
                        job.batch.frames,
                        record_sample=job.record_sample,
                        capture_mode=job.capture_mode,
                    )
                    frame_index = max((frame.frame_index for frame in job.batch.frames.values()), default=0)
                    self.result_ready.emit(
                        CalibrationAnalysisOutcome(
                            result=result,
                            record_sample=job.record_sample,
                            frame_index=frame_index,
                            capture_mode=job.capture_mode,
                        )
                    )
                except Exception as exc:  # pragma: no cover - UI surface area
                    LOGGER.exception("Calibration analysis worker failed.")
                    self.error.emit(str(exc))
        finally:
            self.state_changed.emit("calibration_analysis_stopped")


class CameraProbeWorker(QThread):
    result_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        sources: list[CameraSourceConfig],
        requested_width: int = 0,
        requested_height: int = 0,
        requested_fps: float = 0.0,
        exposure: float | None = None,
        gain: float | None = None,
        white_balance: float | None = None,
    ) -> None:
        super().__init__()
        self._sources = [source for source in sources if source.enabled]
        if not self._sources:
            raise ValueError("CameraProbeWorker requires at least one enabled source.")
        self._requested_width = max(0, int(requested_width))
        self._requested_height = max(0, int(requested_height))
        self._requested_fps = max(0.0, float(requested_fps))
        self._exposure = exposure
        self._gain = gain
        self._white_balance = white_balance
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        session = OpenCVCaptureSession(
            self._sources,
            requested_width=self._requested_width,
            requested_height=self._requested_height,
            requested_fps=self._requested_fps,
            exposure=self._exposure,
            gain=self._gain,
            white_balance=self._white_balance,
        )
        try:
            self.state_changed.emit("camera_probe_started")
            probe_results = session.probe_sources()
            if self._stop_event.is_set():
                self.state_changed.emit("camera_probe_stopped")
                return
            self.result_ready.emit(probe_results)
            self.state_changed.emit("camera_probe_finished")
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Camera probe worker failed.")
            self.error.emit(str(exc))
            self.state_changed.emit("camera_probe_failed")
        finally:
            session.close()


@dataclass(slots=True)
class CaptureWorkerSample:
    probe_results: dict[str, CameraProbeResult]
    batch: CaptureBatch


class CaptureWorker(QThread):
    batch_ready = Signal(object)
    probe_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        sources: Sequence[CameraSourceConfig],
        target_fps: float,
        max_frame_width: int = 0,
        requested_width: int = 0,
        requested_height: int = 0,
        requested_fps: float = 0.0,
        exposure: float | None = None,
        gain: float | None = None,
        white_balance: float | None = None,
        auto_exposure: float | None = None,
        loop_video: bool = False,
        batch_limit: int | None = None,
    ) -> None:
        super().__init__()
        self._sources = [source for source in sources if source.enabled]
        if not self._sources:
            raise ValueError("CaptureWorker requires at least one enabled source.")

        self._target_fps = max(1.0, float(target_fps))
        self._max_frame_width = max(0, int(max_frame_width))
        self._requested_width = max(0, int(requested_width))
        self._requested_height = max(0, int(requested_height))
        self._requested_fps = max(0.0, float(requested_fps))
        self._exposure = exposure
        self._gain = gain
        self._white_balance = white_balance
        self._auto_exposure = auto_exposure
        self._loop_video = bool(loop_video)
        self._batch_limit = None if batch_limit is None else max(1, int(batch_limit))
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def capture_once(self) -> CaptureWorkerSample:
        session = self._build_session()
        try:
            probes = session.open()
            batch = session.read_batch()
            return CaptureWorkerSample(probe_results=probes, batch=batch)
        finally:
            session.close()

    def run(self) -> None:
        session = self._build_session()
        batch_count = 0

        try:
            probes = session.open()
            self.state_changed.emit("capture_started")
            self.probe_ready.emit(probes)
            self.state_changed.emit("capture_streaming")

            frame_interval = 1.0 / self._target_fps
            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                batch = session.read_batch()

                if batch.frames:
                    self.batch_ready.emit(batch)
                    batch_count += 1
                elif len(batch.dropped_sources) >= len(self._sources):
                    self.state_changed.emit("capture_exhausted")
                    break

                if self._batch_limit is not None and batch_count >= self._batch_limit:
                    self.state_changed.emit("capture_batch_limit_reached")
                    break

                elapsed = time.perf_counter() - loop_start
                delay = frame_interval - elapsed
                if delay > 0:
                    time.sleep(delay)
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Capture worker failed.")
            self.error.emit(str(exc))
            self.state_changed.emit("capture_failed")
        finally:
            session.close()
            self.state_changed.emit("capture_stopped")

    def _build_session(self) -> OpenCVCaptureSession:
        return OpenCVCaptureSession(
            sources=self._sources,
            target_fps=self._target_fps,
            max_frame_width=self._max_frame_width,
            requested_width=self._requested_width,
            requested_height=self._requested_height,
            requested_fps=self._requested_fps,
            exposure=self._exposure,
            gain=self._gain,
            white_balance=self._white_balance,
            auto_exposure=self._auto_exposure,
            loop_video=self._loop_video,
        )
