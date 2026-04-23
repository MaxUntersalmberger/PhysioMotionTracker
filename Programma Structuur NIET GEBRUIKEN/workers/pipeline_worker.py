from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from capture.backend import CaptureBatch
from detectors.contracts import PoseDetector
from models.types import CalibrationBundle, PipelineResult
from pipeline.manager import MocapPipeline


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _PipelineJob:
    batch: CaptureBatch
    run_detection: bool


class PipelineWorker(QThread):
    result_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(self, pipeline: MocapPipeline) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._condition = threading.Condition()
        self._pipeline_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._latest_job: _PipelineJob | None = None
        self._dropped_input_batches = 0

    def stop(self) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()

    def submit_batch(self, batch: CaptureBatch, run_detection: bool = True) -> None:
        if not batch.frames:
            return

        job = _PipelineJob(batch=batch, run_detection=run_detection)
        with self._condition:
            if self._latest_job is not None:
                self._dropped_input_batches += 1
            self._latest_job = job
            self._condition.notify()

    def update_calibration(self, bundle: CalibrationBundle | None) -> None:
        with self._pipeline_lock:
            self._pipeline.update_calibration(bundle)

    def update_detector(self, detector: PoseDetector) -> None:
        with self._pipeline_lock:
            self._pipeline.update_detector(detector)
        self.state_changed.emit(f"detector_updated:{detector.name}")

    def process_once(self, batch: CaptureBatch, run_detection: bool = True) -> PipelineResult:
        return self._process_batch(batch=batch, run_detection=run_detection)

    def run(self) -> None:
        self.state_changed.emit("pipeline_started")
        try:
            while not self._stop_event.is_set():
                with self._condition:
                    while self._latest_job is None and not self._stop_event.is_set():
                        self._condition.wait(timeout=0.2)
                    if self._stop_event.is_set():
                        break
                    job = self._latest_job
                    self._latest_job = None

                if job is None:
                    continue

                try:
                    result = self._process_batch(batch=job.batch, run_detection=job.run_detection)
                    result.debug.dropped_input_batches = self._dropped_input_batches
                    self.result_ready.emit(result)
                except Exception as exc:  # pragma: no cover - UI surface area
                    LOGGER.exception("Pipeline worker failed.")
                    self.error.emit(str(exc))
        finally:
            self.state_changed.emit("pipeline_stopped")

    def _process_batch(self, batch: CaptureBatch, run_detection: bool) -> PipelineResult:
        if not batch.frames:
            raise ValueError("Cannot process an empty capture batch.")

        with self._pipeline_lock:
            result = self._pipeline.process(batch.frames, run_detection=run_detection)

        result.debug.capture_latency_ms = max(0.0, (time.time() - batch.capture_timestamp_sec) * 1000.0)
        return result
