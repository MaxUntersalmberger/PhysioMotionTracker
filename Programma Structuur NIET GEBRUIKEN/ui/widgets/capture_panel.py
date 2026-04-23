from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
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

from detectors import DEFAULT_DETECTOR_NAME, DETECTOR_CHOICES, normalize_detector_name


class CapturePanelWidget(QWidget):
    probe_requested = Signal(str)
    sample_requested = Signal(str, float)
    live_requested = Signal(str, float)
    stop_requested = Signal()
    detector_changed = Signal(str)

    def __init__(
        self,
        default_sources_csv: str = "0",
        default_fps: float = 20.0,
        default_detector_name: str = DEFAULT_DETECTOR_NAME,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_edit = QLineEdit(default_sources_csv)
        self._source_edit.setPlaceholderText("0,1 or path/to/video.mp4")

        self._detector_combo = QComboBox()
        for detector_name, label, description in DETECTOR_CHOICES:
            self._detector_combo.addItem(label, detector_name)
            index = self._detector_combo.count() - 1
            self._detector_combo.setItemData(index, description, Qt.ItemDataRole.ToolTipRole)
        self._set_detector_name(default_detector_name)
        self._detector_combo.currentIndexChanged.connect(self._emit_detector_changed)

        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.setSingleStep(1.0)
        self._fps_spin.setValue(float(default_fps))
        self._fps_spin.setSuffix(" fps")

        self._probe_button = QPushButton("Probe Sources")
        self._sample_button = QPushButton("Capture Sample")
        self._live_button = QPushButton("Start Live")
        self._stop_button = QPushButton("Stop")
        self._stop_button.setEnabled(False)

        self._state_label = QLabel("Idle")
        self._state_label.setObjectName("captureStateLabel")
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setPlaceholderText("Probe results, capture batch summaries, and runtime status appear here.")

        form = QFormLayout()
        form.addRow("Sources", self._source_edit)
        form.addRow("Detector", self._detector_combo)
        form.addRow("Target FPS", self._fps_spin)

        button_row = QHBoxLayout()
        button_row.addWidget(self._probe_button)
        button_row.addWidget(self._sample_button)
        button_row.addWidget(self._live_button)
        button_row.addWidget(self._stop_button)

        control_box = QGroupBox("Capture Controls")
        control_layout = QVBoxLayout(control_box)
        control_layout.addLayout(form)
        control_layout.addLayout(button_row)
        control_layout.addWidget(self._state_label)

        activity_box = QGroupBox("Capture Output")
        activity_layout = QVBoxLayout(activity_box)
        activity_layout.addWidget(self._output)

        root = QVBoxLayout(self)
        root.addWidget(control_box)
        root.addWidget(activity_box, 1)

        self._probe_button.clicked.connect(lambda: self.probe_requested.emit(self.source_csv()))
        self._sample_button.clicked.connect(lambda: self.sample_requested.emit(self.source_csv(), self.target_fps()))
        self._live_button.clicked.connect(lambda: self.live_requested.emit(self.source_csv(), self.target_fps()))
        self._stop_button.clicked.connect(self.stop_requested.emit)

    def source_csv(self) -> str:
        return self._source_edit.text().strip()

    def set_source_csv(self, source_csv: str) -> None:
        self._source_edit.setText(source_csv.strip())

    def detector_name(self) -> str:
        data = self._detector_combo.currentData()
        if isinstance(data, str) and data:
            return normalize_detector_name(data)
        return DEFAULT_DETECTOR_NAME

    def set_detector_name(self, detector_name: str) -> None:
        self._set_detector_name(detector_name)

    def _set_detector_name(self, detector_name: str) -> None:
        normalized = normalize_detector_name(detector_name)
        self._detector_combo.blockSignals(True)
        index = self._detector_combo.findData(normalized)
        if index < 0:
            index = self._detector_combo.findData(DEFAULT_DETECTOR_NAME)
        self._detector_combo.setCurrentIndex(max(0, index))
        self._detector_combo.blockSignals(False)

    def _emit_detector_changed(self, *_args: object) -> None:
        self.detector_changed.emit(self.detector_name())

    def target_fps(self) -> float:
        return float(self._fps_spin.value())

    def set_target_fps(self, target_fps: float) -> None:
        self._fps_spin.setValue(float(target_fps))

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_running(self, running: bool) -> None:
        self._source_edit.setEnabled(not running)
        self._fps_spin.setEnabled(not running)
        self._probe_button.setEnabled(not running)
        self._sample_button.setEnabled(not running)
        self._live_button.setEnabled(not running)
        self._stop_button.setEnabled(running)

    def set_probe_running(self, running: bool) -> None:
        self._source_edit.setEnabled(not running)
        self._fps_spin.setEnabled(not running)
        self._probe_button.setEnabled(not running)
        self._sample_button.setEnabled(not running)
        self._live_button.setEnabled(not running)
        self._stop_button.setEnabled(False)

    def append_output(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.moveCursor(QTextCursor.MoveOperation.End)
        self._output.ensureCursorVisible()

    def clear_output(self) -> None:
        self._output.clear()
