from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from motion import MotionTakeReport, process_session_to_motion_take


LOGGER = logging.getLogger(__name__)


class MotionTakeWorker(QThread):
    result_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        session_path: Path,
        detector_name: str,
        output_path: Path | None = None,
        max_batches: int | None = None,
    ) -> None:
        super().__init__()
        self._session_path = session_path
        self._detector_name = detector_name
        self._output_path = output_path
        self._max_batches = max_batches

    def run(self) -> None:
        self.state_changed.emit("motion_take_started")
        try:
            report: MotionTakeReport = process_session_to_motion_take(
                self._session_path,
                detector_name=self._detector_name,
                output_path=self._output_path,
                max_batches=self._max_batches,
            )
            self.result_ready.emit(report)
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Motion take worker failed.")
            self.error.emit(str(exc))
        finally:
            self.state_changed.emit("motion_take_stopped")
