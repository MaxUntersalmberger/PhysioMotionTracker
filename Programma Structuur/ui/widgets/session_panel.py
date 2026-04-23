from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.types import SessionManifest


class SessionPanelWidget(QWidget):
    new_session_requested = Signal()
    save_session_requested = Signal()
    load_session_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._session_id_edit = QLineEdit()
        self._session_id_edit.setPlaceholderText("session_YYYYMMDD_HHMMSS")

        self._active_dir_label = QLabel("Active session: none")
        self._loaded_dir_label = QLabel("Loaded session: none")
        self._manifest_label = QLabel("Manifest: none")
        self._state_label = QLabel("Session state: idle")
        self._summary_output = QPlainTextEdit()
        self._summary_output.setReadOnly(True)
        self._summary_output.setPlaceholderText("Session manifest summary will appear here.")
        self._summary_output.setObjectName("sessionSummaryOutput")

        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlaceholderText("Optional session notes, task description, subject details, or reminders.")
        self._notes_edit.setObjectName("sessionNotesInput")

        self._new_button = QPushButton("New Session")
        self._save_button = QPushButton("Save Snapshot")
        self._load_button = QPushButton("Load Session")

        controls_box = QGroupBox("Session Controls")
        controls_layout = QVBoxLayout(controls_box)
        form = QFormLayout()
        form.addRow("Session ID", self._session_id_edit)
        controls_layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addWidget(self._new_button)
        button_row.addWidget(self._save_button)
        button_row.addWidget(self._load_button)
        controls_layout.addLayout(button_row)
        controls_layout.addWidget(self._state_label)
        controls_layout.addWidget(self._active_dir_label)
        controls_layout.addWidget(self._loaded_dir_label)
        controls_layout.addWidget(self._manifest_label)

        notes_box = QGroupBox("Session Notes")
        notes_layout = QVBoxLayout(notes_box)
        notes_layout.addWidget(self._notes_edit)

        summary_box = QGroupBox("Session Summary")
        summary_layout = QVBoxLayout(summary_box)
        summary_layout.addWidget(self._summary_output)

        root = QVBoxLayout(self)
        root.addWidget(controls_box)
        root.addWidget(notes_box)
        root.addWidget(summary_box, 1)

        self._new_button.clicked.connect(self.new_session_requested.emit)
        self._save_button.clicked.connect(self.save_session_requested.emit)
        self._load_button.clicked.connect(self.load_session_requested.emit)

    def session_id(self) -> str:
        return self._session_id_edit.text().strip()

    def set_session_id(self, session_id: str) -> None:
        self._session_id_edit.setText(session_id)

    def notes(self) -> list[str]:
        return [line.strip() for line in self._notes_edit.toPlainText().splitlines() if line.strip()]

    def set_notes(self, notes: list[str]) -> None:
        self._notes_edit.setPlainText("\n".join(notes))

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_active_session_dir(self, path_text: str | None) -> None:
        self._active_dir_label.setText(f"Active session: {path_text}" if path_text else "Active session: none")

    def set_loaded_session_dir(self, path_text: str | None) -> None:
        self._loaded_dir_label.setText(f"Loaded session: {path_text}" if path_text else "Loaded session: none")

    def set_manifest_path(self, path_text: str | None) -> None:
        self._manifest_label.setText(f"Manifest: {path_text}" if path_text else "Manifest: none")

    def set_summary_lines(self, lines: list[str]) -> None:
        if not lines:
            self._summary_output.setPlainText("No session data yet.")
            return

        self._summary_output.setPlainText("\n".join(lines))

    def set_manifest(self, manifest: SessionManifest | None) -> None:
        if manifest is None:
            self.set_summary_lines([])
            return

        lines = [
            f"Session ID: {manifest.session_id}",
            f"Created: {manifest.created_at_iso}",
            f"FPS: {manifest.fps:.1f}",
            f"Sources: {len(manifest.sources)}",
            f"Total frames: {manifest.total_frames}",
        ]
        if manifest.calibration_file:
            lines.append(f"Calibration: {manifest.calibration_file}")
        if manifest.pose_file:
            lines.append(f"Pose file: {manifest.pose_file}")
        if manifest.notes:
            lines.append("Notes: " + " | ".join(manifest.notes[:3]))
        self.set_summary_lines(lines)

    def append_summary_line(self, text: str) -> None:
        current = self._summary_output.toPlainText().strip()
        new_text = f"{current}\n{text}" if current else text
        self._summary_output.setPlainText(new_text)
        self._summary_output.moveCursor(QTextCursor.MoveOperation.End)
        self._summary_output.ensureCursorVisible()