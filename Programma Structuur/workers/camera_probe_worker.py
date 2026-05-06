from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QThread, Signal

from capture.backend import OpenCVCaptureSession
from models.types import CameraSourceConfig


LOGGER = logging.getLogger(__name__)


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
