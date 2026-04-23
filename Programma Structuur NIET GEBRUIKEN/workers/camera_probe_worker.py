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

    def __init__(self, sources: list[CameraSourceConfig]) -> None:
        super().__init__()
        self._sources = [source for source in sources if source.enabled]
        if not self._sources:
            raise ValueError("CameraProbeWorker requires at least one enabled source.")
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        session = OpenCVCaptureSession(self._sources)
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
