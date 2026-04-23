from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from capture.backend import CaptureBatch
from calibration.manager import CalibrationManager, CalibrationCaptureResult


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _CalibrationAnalysisJob:
    batch: CaptureBatch
    record_sample: bool


@dataclass(slots=True)
class CalibrationAnalysisOutcome:
    result: CalibrationCaptureResult
    record_sample: bool
    frame_index: int


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

    def submit_batch(self, batch: CaptureBatch, record_sample: bool = False) -> None:
        if not batch.frames:
            return

        job = _CalibrationAnalysisJob(batch=batch, record_sample=record_sample)
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
                    result = self._calibration_manager.capture_frames(job.batch.frames, record_sample=job.record_sample)
                    frame_index = max((frame.frame_index for frame in job.batch.frames.values()), default=0)
                    self.result_ready.emit(
                        CalibrationAnalysisOutcome(
                            result=result,
                            record_sample=job.record_sample,
                            frame_index=frame_index,
                        )
                    )
                except Exception as exc:  # pragma: no cover - UI surface area
                    LOGGER.exception("Calibration analysis worker failed.")
                    self.error.emit(str(exc))
        finally:
            self.state_changed.emit("calibration_analysis_stopped")
