from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from calibration.repository import CalibrationRepository
from detectors import PoseDetector, create_detector, normalize_detector_name
from models.types import CalibrationBundle


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StartupResult:
    detector_name: str
    detector: PoseDetector
    calibration_bundle: CalibrationBundle | None
    calibration_path: Path
    messages: list[str] = field(default_factory=list)


class StartupWorker(QThread):
    progress_changed = Signal(int, str)
    result_ready = Signal(object)
    error = Signal(str)

    def __init__(self, requested_detector_name: str, calibration_path: Path) -> None:
        super().__init__()
        self._requested_detector_name = normalize_detector_name(requested_detector_name)
        self._calibration_path = calibration_path
        self._calibration_repo = CalibrationRepository()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self.progress_changed.emit(10, "Loading detector...")
            detector_name = self._requested_detector_name
            detector = self._create_detector_with_fallback(detector_name)

            if self._stop_event.is_set():
                return

            self.progress_changed.emit(60, "Loading calibration profile...")
            calibration_bundle = self._calibration_repo.load(self._calibration_path)

            if self._stop_event.is_set():
                return

            self.progress_changed.emit(90, "Finalizing startup...")
            messages = [f"Detector ready: {detector_name}"]
            if calibration_bundle is None:
                messages.append(f"No calibration profile found at {self._calibration_path}.")
            else:
                messages.append(f"Calibration profile loaded from {self._calibration_path}.")

            self.result_ready.emit(
                StartupResult(
                    detector_name=detector_name,
                    detector=detector,
                    calibration_bundle=calibration_bundle,
                    calibration_path=self._calibration_path,
                    messages=messages,
                )
            )
            self.progress_changed.emit(100, "Startup complete")
        except Exception as exc:  # pragma: no cover - startup surface area
            LOGGER.exception("Startup worker failed.")
            self.error.emit(str(exc))

    def _create_detector_with_fallback(self, detector_name: str) -> PoseDetector:
        try:
            return create_detector(detector_name)
        except Exception as exc:
            LOGGER.warning("Detector '%s' failed during startup, falling back to synthetic: %s", detector_name, exc)
            fallback = create_detector("synthetic")
            self._requested_detector_name = "synthetic"
            return fallback
