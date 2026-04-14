from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QFrame,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calibration import CalibrationCameraQuality, CalibrationSampleHistoryEntry


class _CalibrationQualityRowWidget(QFrame):
    def __init__(self, source_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("calibrationQualityRow")

        self._title_label = QLabel(source_id)
        self._title_label.setObjectName("calibrationQualityTitle")
        self._score_bar = QProgressBar()
        self._score_bar.setObjectName("calibrationQualityProgress")
        self._score_bar.setRange(0, 100)
        self._score_bar.setTextVisible(True)
        self._score_bar.setFormat("%v/100")
        self._detail_label = QLabel("Waiting for calibration frames.")
        self._detail_label.setWordWrap(True)
        self._detail_label.setObjectName("calibrationQualityDetail")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._score_bar)
        layout.addWidget(self._detail_label)

    def set_quality(self, quality: CalibrationCameraQuality | None) -> None:
        if quality is None:
            self._title_label.setText("Source")
            self._score_bar.setValue(0)
            self._score_bar.setFormat("0/100")
            self._detail_label.setText("No calibration board detected.")
            return

        self._title_label.setText(quality.source_id)
        self._score_bar.setValue(int(round(quality.score)))
        self._score_bar.setFormat(f"{int(round(quality.score))}/100")
        self._detail_label.setText(quality.summary_text)


class CalibrationPanelWidget(QWidget):
    capture_sample_requested = Signal()
    solve_intrinsics_requested = Signal()
    solve_extrinsics_requested = Signal()
    load_profile_requested = Signal()
    save_profile_requested = Signal()
    reset_samples_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._columns_spin = QSpinBox()
        self._columns_spin.setRange(4, 20)
        self._columns_spin.setValue(9)
        self._columns_spin.setSuffix(" cols")

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(4, 20)
        self._rows_spin.setValue(6)
        self._rows_spin.setSuffix(" rows")

        self._square_size_spin = QDoubleSpinBox()
        self._square_size_spin.setRange(0.001, 0.2)
        self._square_size_spin.setDecimals(3)
        self._square_size_spin.setSingleStep(0.001)
        self._square_size_spin.setValue(0.024)
        self._square_size_spin.setSuffix(" m")

        self._guidance_label = QLabel(
            "Guidance: probe 2+ cameras, watch the per-camera quality bars, keep the chessboard visible in every view, then capture a sample when sync is ready."
        )
        self._guidance_label.setWordWrap(True)
        self._guidance_label.setObjectName("calibrationGuidanceLabel")

        self._workflow_label = QLabel(
            "Wizard flow: probe sources -> align the board -> capture sample -> review history -> solve intrinsics -> solve extrinsics."
        )
        self._workflow_label.setWordWrap(True)
        self._workflow_label.setObjectName("calibrationWorkflowLabel")

        self._sync_label = QLabel("Camera sync: waiting for the next sample.")
        self._sync_label.setWordWrap(True)
        self._sync_label.setObjectName("calibrationSyncLabel")

        self._state_label = QLabel("No calibration profile loaded.")
        self._state_label.setObjectName("calibrationStateLabel")
        self._sample_counts_label = QLabel("Samples: none")
        self._profile_label = QLabel("Profile: not loaded")

        self._quality_summary_label = QLabel("Quality scores will appear after the first live batch.")
        self._quality_summary_label.setWordWrap(True)
        self._quality_summary_label.setObjectName("calibrationQualitySummaryLabel")
        self._quality_rows_widget = QWidget()
        self._quality_rows_layout = QVBoxLayout(self._quality_rows_widget)
        self._quality_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._quality_rows_layout.setSpacing(8)
        self._quality_empty_label = QLabel("No per-camera quality data yet.")
        self._quality_empty_label.setWordWrap(True)
        self._quality_empty_label.setObjectName("calibrationQualityEmptyLabel")
        self._quality_rows_layout.addWidget(self._quality_empty_label)

        self._history_summary_label = QLabel("Sample history will list each stored calibration attempt.")
        self._history_summary_label.setWordWrap(True)
        self._history_summary_label.setObjectName("calibrationHistorySummaryLabel")
        self._history_output = QPlainTextEdit()
        self._history_output.setObjectName("calibrationHistoryOutput")
        self._history_output.setReadOnly(True)
        self._history_output.setPlaceholderText("Stored calibration samples appear here.")

        self._capture_button = QPushButton("Capture Calibration Sample")
        self._solve_intrinsics_button = QPushButton("Solve Intrinsics")
        self._solve_extrinsics_button = QPushButton("Solve Extrinsics")
        self._load_button = QPushButton("Load Profile")
        self._save_button = QPushButton("Save Profile")
        self._reset_button = QPushButton("Reset Samples")
        for button in (self._capture_button, self._solve_intrinsics_button, self._solve_extrinsics_button, self._load_button, self._save_button, self._reset_button):
            button.setMinimumWidth(170)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Calibration capture, solve, and profile messages appear here.")
        self._output.setMinimumHeight(120)

        form = QFormLayout()
        form.addRow("Board columns", self._columns_spin)
        form.addRow("Board rows", self._rows_spin)
        form.addRow("Square size", self._square_size_spin)

        button_row = QHBoxLayout()
        button_row.addWidget(self._capture_button)
        button_row.addWidget(self._solve_intrinsics_button)
        button_row.addWidget(self._solve_extrinsics_button)

        file_row = QHBoxLayout()
        file_row.addWidget(self._load_button)
        file_row.addWidget(self._save_button)
        file_row.addWidget(self._reset_button)

        instruction_box = QGroupBox("Instructions")
        instruction_layout = QVBoxLayout(instruction_box)
        instruction_layout.addWidget(self._guidance_label)
        instruction_layout.addWidget(self._workflow_label)
        instruction_layout.addWidget(self._sync_label)

        settings_box = QGroupBox("Capture Settings")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addLayout(form)
        settings_layout.addLayout(button_row)
        settings_layout.addLayout(file_row)
        settings_layout.addWidget(self._state_label)
        settings_layout.addWidget(self._sample_counts_label)
        settings_layout.addWidget(self._profile_label)

        top_row = QHBoxLayout()
        top_row.addWidget(instruction_box, 2)
        top_row.addWidget(settings_box, 3)

        quality_box = QGroupBox("Per-Camera Quality")
        quality_layout = QVBoxLayout(quality_box)
        quality_layout.addWidget(self._quality_summary_label)
        quality_layout.addWidget(self._quality_rows_widget)

        history_box = QGroupBox("Sample History")
        history_layout = QVBoxLayout(history_box)
        history_layout.addWidget(self._history_summary_label)
        history_layout.addWidget(self._history_output)

        output_box = QGroupBox("Calibration Output")
        output_layout = QVBoxLayout(output_box)
        output_layout.addWidget(self._output)

        root = QVBoxLayout(self)
        root.addLayout(top_row)
        root.addWidget(quality_box)
        root.addWidget(history_box)
        root.addWidget(output_box, 1)

        self._capture_button.clicked.connect(self.capture_sample_requested.emit)
        self._solve_intrinsics_button.clicked.connect(self.solve_intrinsics_requested.emit)
        self._solve_extrinsics_button.clicked.connect(self.solve_extrinsics_requested.emit)
        self._load_button.clicked.connect(self.load_profile_requested.emit)
        self._save_button.clicked.connect(self.save_profile_requested.emit)
        self._reset_button.clicked.connect(self.reset_samples_requested.emit)

    def board_shape(self) -> tuple[int, int]:
        return int(self._columns_spin.value()), int(self._rows_spin.value())

    def square_size_m(self) -> float:
        return float(self._square_size_spin.value())

    def set_board_shape(self, board_shape: tuple[int, int]) -> None:
        columns, rows = board_shape
        self._columns_spin.setValue(int(columns))
        self._rows_spin.setValue(int(rows))

    def set_square_size_m(self, square_size_m: float) -> None:
        self._square_size_spin.setValue(float(square_size_m))

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_sync_status(self, text: str) -> None:
        self._sync_label.setText(text)

    def set_sample_counts(self, sample_counts: dict[str, int], synchronized_samples: int) -> None:
        if not sample_counts:
            self._sample_counts_label.setText("Samples: none")
            return
        parts = [f"{source_id}={count}" for source_id, count in sorted(sample_counts.items())]
        parts.append(f"sync={synchronized_samples}")
        self._sample_counts_label.setText("Samples: " + ", ".join(parts))

    def set_camera_quality_scores(self, quality_scores: dict[str, CalibrationCameraQuality]) -> None:
        self._clear_layout(self._quality_rows_layout)
        if not quality_scores:
            self._quality_summary_label.setText("Quality scores will appear after the first live batch.")
            self._quality_rows_layout.addWidget(self._quality_empty_label)
            return

        self._quality_summary_label.setText(f"Board quality tracked for {len(quality_scores)} camera(s).")
        for source_id, quality in sorted(quality_scores.items()):
            row = _CalibrationQualityRowWidget(source_id)
            row.set_quality(quality)
            self._quality_rows_layout.addWidget(row)
        self._quality_rows_layout.addStretch(1)

    def set_sample_history(self, entries: Sequence[CalibrationSampleHistoryEntry]) -> None:
        history_entries = list(entries)
        if not history_entries:
            self._history_summary_label.setText("Sample history will list each stored calibration attempt.")
            self._history_output.setPlainText("No stored calibration samples yet.")
            return

        visible_entries = history_entries[-10:]
        lines = [f"Showing last {len(visible_entries)} of {len(history_entries)} stored sample(s)."]
        for entry in visible_entries:
            lines.append(entry.summary_text)
            if entry.notes:
                lines.append("  " + " | ".join(entry.notes[:2]))

        self._history_summary_label.setText(f"Stored samples: {len(history_entries)}")
        self._history_output.setPlainText("\n".join(lines))

    def set_profile_path(self, path_text: str | None) -> None:
        self._profile_label.setText(f"Profile: {path_text}" if path_text else "Profile: not loaded")

    def append_output(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.moveCursor(QTextCursor.MoveOperation.End)
        self._output.ensureCursorVisible()

    def clear_output(self) -> None:
        self._output.clear()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)