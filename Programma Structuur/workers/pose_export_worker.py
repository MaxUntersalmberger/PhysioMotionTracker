from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from exporters import PoseExportReport, export_session_poses


LOGGER = logging.getLogger(__name__)


class PoseExportWorker(QThread):
    result_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        session_path: Path,
        detector_name: str,
        output_dir: Path | None = None,
        formats: list[str] | None = None,
        max_batches: int | None = None,
    ) -> None:
        super().__init__()
        self._session_path = session_path
        self._detector_name = detector_name
        self._output_dir = output_dir
        self._formats = list(formats or ["json", "csv"])
        self._max_batches = max_batches

    def run(self) -> None:
        self.state_changed.emit("pose_export_started")
        try:
            report: PoseExportReport = export_session_poses(
                self._session_path,
                detector_name=self._detector_name,
                output_dir=self._output_dir,
                formats=self._formats,
                max_batches=self._max_batches,
            )
            self.result_ready.emit(report)
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Pose export worker failed.")
            self.error.emit(str(exc))
        finally:
            self.state_changed.emit("pose_export_stopped")
