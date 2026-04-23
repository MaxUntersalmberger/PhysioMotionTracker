from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import QThread, Signal

from capture.backend import CaptureBatch, OpenCVCaptureSession
from models.types import CameraProbeResult, CameraSourceConfig


LOGGER = logging.getLogger(__name__)


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
            loop_video=self._loop_video,
        )
