from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from models.types import PipelineResult


class PipelineStatusWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._frame_value = QLabel("-")
        self._detector_value = QLabel("-")
        self._matcher_value = QLabel("-")
        self._triangulator_value = QLabel("-")
        self._mode_value = QLabel("-")
        self._active_cameras_value = QLabel("-")
        self._matched_value = QLabel("-")
        self._joints_value = QLabel("-")
        self._error_value = QLabel("-")
        self._capture_latency_value = QLabel("-")
        self._pipeline_latency_value = QLabel("-")
        self._last_notes_text = ""

        form = QFormLayout()
        form.addRow("Frame", self._frame_value)
        form.addRow("Detector", self._detector_value)
        form.addRow("Matcher", self._matcher_value)
        form.addRow("Triangulator", self._triangulator_value)
        form.addRow("Mode", self._mode_value)
        form.addRow("Active cameras", self._active_cameras_value)
        form.addRow("Matched keypoints", self._matched_value)
        form.addRow("Reconstructed joints", self._joints_value)
        form.addRow("Mean reprojection error", self._error_value)
        form.addRow("Capture latency", self._capture_latency_value)
        form.addRow("Pipeline latency", self._pipeline_latency_value)

        self._notes_box = QPlainTextEdit()
        self._notes_box.setReadOnly(True)
        self._notes_box.setPlaceholderText("Pipeline notes and warnings appear here.")

        status_group = QGroupBox("Pipeline Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.addLayout(form)

        notes_group = QGroupBox("Notes")
        notes_layout = QVBoxLayout(notes_group)
        notes_layout.addWidget(self._notes_box)

        root = QVBoxLayout(self)
        root.addWidget(status_group)
        root.addWidget(notes_group, 1)

    def set_idle(self) -> None:
        self._frame_value.setText("-")
        self._detector_value.setText("-")
        self._matcher_value.setText("-")
        self._triangulator_value.setText("-")
        self._mode_value.setText("-")
        self._active_cameras_value.setText("-")
        self._matched_value.setText("-")
        self._joints_value.setText("-")
        self._error_value.setText("-")
        self._capture_latency_value.setText("-")
        self._pipeline_latency_value.setText("-")
        self._notes_box.setPlainText("No pipeline result yet.")
        self._last_notes_text = "No pipeline result yet."

    def update_result(self, result: PipelineResult) -> None:
        debug = result.debug
        self._frame_value.setText(f"{result.frame_index} @ {result.timestamp_sec:.3f}s")
        self._detector_value.setText(debug.detector_name)
        self._matcher_value.setText(debug.matcher_name)
        self._triangulator_value.setText(debug.triangulator_name)
        self._mode_value.setText(debug.reconstruction_mode)
        self._active_cameras_value.setText(str(debug.active_cameras))
        self._matched_value.setText(str(debug.matched_keypoints))
        self._joints_value.setText(str(debug.reconstructed_keypoints))
        self._error_value.setText(
            f"{debug.mean_reprojection_error_px:.3f}px" if debug.mean_reprojection_error_px is not None else "n/a"
        )
        self._capture_latency_value.setText(
            f"{debug.capture_latency_ms:.2f} ms" if debug.capture_latency_ms is not None else "n/a"
        )
        self._pipeline_latency_value.setText(f"{debug.pipeline_ms:.2f} ms")
        notes_text = "\n".join(debug.notes) if debug.notes else "No additional notes."
        if notes_text != self._last_notes_text:
            self._notes_box.setPlainText(notes_text)
            self._last_notes_text = notes_text
