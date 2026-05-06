from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSlider, QVBoxLayout, QWidget

from session import SessionPlaybackInfo


class SessionReviewWidget(QWidget):
    load_loaded_session_requested = Signal()
    open_manifest_requested = Signal()
    frame_requested = Signal(int)
    process_current_requested = Signal()
    clear_overlays_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating_slider = False
        self._batch_count = 0

        self._state_label = QLabel("No session loaded for review.")
        self._state_label.setWordWrap(True)
        self._position_label = QLabel("Frame: -")
        self._position_label.setObjectName("reviewPositionLabel")
        self._summary_output = QPlainTextEdit()
        self._summary_output.setReadOnly(True)
        self._summary_output.setPlaceholderText("Loaded session review summary appears here.")

        self._load_loaded_button = QPushButton("Load Loaded Session")
        self._open_manifest_button = QPushButton("Open Manifest")
        self._previous_button = QPushButton("Previous")
        self._next_button = QPushButton("Next")
        self._process_current_button = QPushButton("Process Current Frame")
        self._clear_overlays_button = QPushButton("Clear Overlays")
        self._previous_button.setEnabled(False)
        self._next_button.setEnabled(False)
        self._process_current_button.setEnabled(False)
        self._clear_overlays_button.setEnabled(False)

        self._frame_slider = QSlider(Qt.Orientation.Horizontal)
        self._frame_slider.setMinimum(1)
        self._frame_slider.setMaximum(1)
        self._frame_slider.setValue(1)
        self._frame_slider.setEnabled(False)

        controls_box = QGroupBox("Review Controls")
        controls_layout = QVBoxLayout(controls_box)
        button_row = QHBoxLayout()
        button_row.addWidget(self._load_loaded_button)
        button_row.addWidget(self._open_manifest_button)
        button_row.addWidget(self._process_current_button)
        button_row.addWidget(self._clear_overlays_button)
        button_row.addStretch(1)
        button_row.addWidget(self._previous_button)
        button_row.addWidget(self._next_button)
        controls_layout.addLayout(button_row)
        controls_layout.addWidget(self._position_label)
        controls_layout.addWidget(self._frame_slider)
        controls_layout.addWidget(self._state_label)

        summary_box = QGroupBox("Review Summary")
        summary_layout = QVBoxLayout(summary_box)
        summary_layout.addWidget(self._summary_output)

        root = QVBoxLayout(self)
        root.addWidget(controls_box)
        root.addWidget(summary_box, 1)

        self._load_loaded_button.clicked.connect(self.load_loaded_session_requested.emit)
        self._open_manifest_button.clicked.connect(self.open_manifest_requested.emit)
        self._process_current_button.clicked.connect(self.process_current_requested.emit)
        self._clear_overlays_button.clicked.connect(self.clear_overlays_requested.emit)
        self._previous_button.clicked.connect(self._request_previous)
        self._next_button.clicked.connect(self._request_next)
        self._frame_slider.valueChanged.connect(self._on_slider_changed)

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_loaded_session(self, info: SessionPlaybackInfo) -> None:
        self._batch_count = max(0, info.frame_log_entries or info.manifest.total_frames)
        self._frame_slider.setEnabled(self._batch_count > 0)
        self._previous_button.setEnabled(self._batch_count > 1)
        self._next_button.setEnabled(self._batch_count > 1)
        self._process_current_button.setEnabled(self._batch_count > 0)
        self._clear_overlays_button.setEnabled(self._batch_count > 0)
        self._updating_slider = True
        self._frame_slider.setMinimum(1)
        self._frame_slider.setMaximum(max(1, self._batch_count))
        self._frame_slider.setValue(1)
        self._updating_slider = False
        self.set_current_frame(0)

        lines = [
            f"Session: {info.manifest.session_id}",
            f"Directory: {info.session_dir}",
            f"FPS: {info.manifest.fps:.1f}",
            f"Frames: {info.manifest.total_frames}",
            f"Timeline entries: {info.frame_log_entries}",
            f"Videos: {len(info.available_video_files)}/{len(info.manifest.video_files)}",
        ]
        if info.missing_video_sources:
            lines.append("Missing videos: " + ", ".join(info.missing_video_sources))
        if info.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in info.notes)
        self._summary_output.setPlainText("\n".join(lines))
        self.set_state("Session ready for review." if info.is_playable else "Session has playback warnings.")

    def set_current_frame(self, batch_index: int) -> None:
        if self._batch_count <= 0:
            self._position_label.setText("Frame: -")
            return
        value = max(1, min(self._batch_count, int(batch_index) + 1))
        self._updating_slider = True
        self._frame_slider.setValue(value)
        self._updating_slider = False
        self._position_label.setText(f"Frame: {value}/{self._batch_count}")

    def clear_review(self, message: str = "No session loaded for review.") -> None:
        self._batch_count = 0
        self._summary_output.setPlainText("")
        self._position_label.setText("Frame: -")
        self._frame_slider.setEnabled(False)
        self._previous_button.setEnabled(False)
        self._next_button.setEnabled(False)
        self._process_current_button.setEnabled(False)
        self._clear_overlays_button.setEnabled(False)
        self.set_state(message)

    def _request_previous(self) -> None:
        if self._batch_count <= 0:
            return
        target = max(0, self._frame_slider.value() - 2)
        self.frame_requested.emit(target)

    def _request_next(self) -> None:
        if self._batch_count <= 0:
            return
        target = min(self._batch_count - 1, self._frame_slider.value())
        self.frame_requested.emit(target)

    def _on_slider_changed(self, value: int) -> None:
        if self._updating_slider or self._batch_count <= 0:
            return
        self.frame_requested.emit(max(0, int(value) - 1))
