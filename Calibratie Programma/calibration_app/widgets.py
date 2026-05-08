from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .calibration_manager import (
    CALIBRATION_DETECTOR_AUTO,
    CALIBRATION_DETECTOR_CHOICES,
    CALIBRATION_OBJECT_CHESSBOARD,
    CALIBRATION_OBJECT_CHOICES,
    normalize_calibration_detector_name,
    normalize_calibration_object_type,
)
from .legacy_bridge import ensure_legacy_path
from .project import CalibrationProject

ensure_legacy_path()

from calibration.diagnostics import evaluate_calibration_bundle  # noqa: E402
from calibration.manager import CalibrationCameraQuality, CalibrationSampleHistoryEntry, CalibrationWorkflowReadiness  # noqa: E402
from models.types import CalibrationBundle  # noqa: E402


class HomeWidget(QWidget):
    new_project_requested = Signal(str, str, float)
    open_project_requested = Signal()

    def __init__(self, default_sources_csv: str = "0", default_fps: float = 20.0) -> None:
        super().__init__()
        self._name_edit = QLineEdit("Calibratie Project")
        self._sources_edit = QLineEdit(default_sources_csv)
        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.setValue(float(default_fps))
        self._fps_spin.setSuffix(" fps")
        self._new_button = QPushButton("New Project")
        self._open_button = QPushButton("Open Project")
        self._state_label = QLabel("No project loaded.")
        self._path_label = QLabel("Project: none")
        self._path_label.setWordWrap(True)
        self._profile_label = QLabel("Profile: none")
        self._profile_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Project name", self._name_edit)
        form.addRow("Camera sources", self._sources_edit)
        form.addRow("Target FPS", self._fps_spin)

        buttons = QHBoxLayout()
        buttons.addWidget(self._new_button)
        buttons.addWidget(self._open_button)
        buttons.addStretch(1)

        project_box = QGroupBox("Project")
        project_layout = QVBoxLayout(project_box)
        project_layout.addLayout(form)
        project_layout.addLayout(buttons)

        status_box = QGroupBox("Current Project")
        status_layout = QVBoxLayout(status_box)
        status_layout.addWidget(self._state_label)
        status_layout.addWidget(self._path_label)
        status_layout.addWidget(self._profile_label)

        root = QVBoxLayout(self)
        root.addWidget(project_box)
        root.addWidget(status_box)
        root.addStretch(1)

        self._new_button.clicked.connect(
            lambda: self.new_project_requested.emit(self.project_name(), self.sources_csv(), self.target_fps())
        )
        self._open_button.clicked.connect(self.open_project_requested.emit)

    def project_name(self) -> str:
        return self._name_edit.text().strip() or "Calibratie Project"

    def sources_csv(self) -> str:
        return self._sources_edit.text().strip() or "0"

    def set_sources_csv(self, sources_csv: str) -> None:
        self._sources_edit.setText(sources_csv.strip() or "0")

    def target_fps(self) -> float:
        return float(self._fps_spin.value())

    def set_target_fps(self, target_fps: float) -> None:
        self._fps_spin.setValue(float(target_fps))

    def set_project(self, project: CalibrationProject | None) -> None:
        if project is None:
            self._state_label.setText("No project loaded.")
            self._path_label.setText("Project: none")
            self._profile_label.setText("Profile: none")
            return
        self._name_edit.setText(project.name)
        self.set_sources_csv(project.sources_csv)
        self.set_target_fps(project.target_fps)
        self._state_label.setText(f"Loaded: {project.name}")
        self._path_label.setText(f"Project: {project.root_dir}")
        self._profile_label.setText(f"Profile: {project.calibration_profile_path or project.default_profile_path}")


class CameraControlWidget(QWidget):
    probe_requested = Signal(str)
    sample_requested = Signal(str, float)
    live_requested = Signal(str, float)
    stop_requested = Signal()

    def __init__(self, default_sources_csv: str = "0", default_fps: float = 20.0) -> None:
        super().__init__()
        self._sources_edit = QLineEdit(default_sources_csv)
        self._sources_edit.setPlaceholderText("0,1 or path/to/video.mp4")
        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 240.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.setValue(float(default_fps))
        self._fps_spin.setSuffix(" fps")
        self._width_spin = _auto_spin(7680.0, " px")
        self._height_spin = _auto_spin(4320.0, " px")
        self._exposure_spin = _auto_spin(10000.0, "")
        self._exposure_spin.setRange(-20.0, 10000.0)
        self._gain_spin = _auto_spin(10000.0, "")
        self._white_balance_spin = _auto_spin(12000.0, " K")
        self._probe_button = QPushButton("Probe Sources")
        self._sample_button = QPushButton("Capture Sample")
        self._live_button = QPushButton("Start Live")
        self._stop_button = QPushButton("Stop")
        self._stop_button.setEnabled(False)
        self._state_label = QLabel("Idle")
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Sources", self._sources_edit)
        form.addRow("Target FPS", self._fps_spin)
        form.addRow("Width", self._width_spin)
        form.addRow("Height", self._height_spin)
        form.addRow("Exposure", self._exposure_spin)
        form.addRow("Gain", self._gain_spin)
        form.addRow("White balance", self._white_balance_spin)

        buttons = QHBoxLayout()
        buttons.addWidget(self._probe_button)
        buttons.addWidget(self._sample_button)
        buttons.addWidget(self._live_button)
        buttons.addWidget(self._stop_button)

        box = QGroupBox("Camera Controls")
        box_layout = QVBoxLayout(box)
        box_layout.addLayout(form)
        box_layout.addLayout(buttons)
        box_layout.addWidget(self._state_label)

        output_box = QGroupBox("Camera Output")
        output_layout = QVBoxLayout(output_box)
        output_layout.addWidget(self._output)

        root = QVBoxLayout(self)
        root.addWidget(box)
        root.addWidget(output_box, 1)

        self._probe_button.clicked.connect(lambda: self.probe_requested.emit(self.sources_csv()))
        self._sample_button.clicked.connect(lambda: self.sample_requested.emit(self.sources_csv(), self.target_fps()))
        self._live_button.clicked.connect(lambda: self.live_requested.emit(self.sources_csv(), self.target_fps()))
        self._stop_button.clicked.connect(self.stop_requested.emit)

    def sources_csv(self) -> str:
        return self._sources_edit.text().strip() or "0"

    def set_sources_csv(self, sources_csv: str) -> None:
        self._sources_edit.setText(sources_csv.strip() or "0")

    def target_fps(self) -> float:
        return float(self._fps_spin.value())

    def set_target_fps(self, fps: float) -> None:
        self._fps_spin.setValue(float(fps))

    def requested_width(self) -> int:
        return int(self._width_spin.value())

    def requested_height(self) -> int:
        return int(self._height_spin.value())

    def requested_exposure(self) -> float | None:
        return _optional_spin_value(self._exposure_spin)

    def requested_gain(self) -> float | None:
        return _optional_spin_value(self._gain_spin)

    def requested_white_balance(self) -> float | None:
        return _optional_spin_value(self._white_balance_spin)

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_running(self, running: bool) -> None:
        for widget in (
            self._sources_edit,
            self._fps_spin,
            self._width_spin,
            self._height_spin,
            self._exposure_spin,
            self._gain_spin,
            self._white_balance_spin,
            self._probe_button,
            self._sample_button,
            self._live_button,
        ):
            widget.setEnabled(not running)
        self._stop_button.setEnabled(running)

    def set_probe_running(self, running: bool) -> None:
        self.set_running(running)
        self._stop_button.setEnabled(False)

    def append_output(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.moveCursor(QTextCursor.MoveOperation.End)
        self._output.ensureCursorVisible()

    def clear_output(self) -> None:
        self._output.clear()


class CalibrationSettingsWidget(QWidget):
    capture_sample_requested = Signal()
    solve_intrinsics_requested = Signal()
    solve_extrinsics_requested = Signal()
    load_profile_requested = Signal()
    save_profile_requested = Signal()
    reset_samples_requested = Signal()
    settings_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._object_combo = QComboBox()
        for name, label, description in CALIBRATION_OBJECT_CHOICES:
            self._object_combo.addItem(label, name)
            self._object_combo.setItemData(self._object_combo.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        self._detector_combo = QComboBox()
        for name, label, description in CALIBRATION_DETECTOR_CHOICES:
            self._detector_combo.addItem(label, name)
            self._detector_combo.setItemData(self._detector_combo.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        self._workflow_combo = QComboBox()
        self._workflow_combo.addItem("Intrinsics", "intrinsics")
        self._workflow_combo.addItem("Sync / Extrinsics", "sync_extrinsics")
        self._columns_spin = QSpinBox()
        self._columns_spin.setRange(4, 20)
        self._columns_spin.setValue(9)
        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(4, 20)
        self._rows_spin.setValue(6)
        self._square_size_spin = QDoubleSpinBox()
        self._square_size_spin.setRange(0.001, 0.2)
        self._square_size_spin.setDecimals(3)
        self._square_size_spin.setSingleStep(0.001)
        self._square_size_spin.setValue(0.024)
        self._square_size_spin.setSuffix(" m")
        self._auto_checkbox = QCheckBox("Auto Capture Valid Frames")
        self._cooldown_spin = QDoubleSpinBox()
        self._cooldown_spin.setRange(0.5, 10.0)
        self._cooldown_spin.setDecimals(1)
        self._cooldown_spin.setValue(1.5)
        self._cooldown_spin.setSuffix(" s")
        self._capture_button = QPushButton("Capture Intrinsics Sample")
        self._solve_intrinsics_button = QPushButton("Solve Intrinsics")
        self._solve_extrinsics_button = QPushButton("Solve Extrinsics")
        self._load_button = QPushButton("Load Profile")
        self._save_button = QPushButton("Save Profile")
        self._reset_button = QPushButton("Reset Samples")
        self._state_label = QLabel("No calibration profile loaded.")
        self._state_label.setWordWrap(True)
        self._auto_label = QLabel("Auto capture off.")
        self._auto_label.setWordWrap(True)
        self._sync_label = QLabel("Camera sync: waiting for frames.")
        self._sync_label.setWordWrap(True)
        self._sample_label = QLabel("Samples: none")
        self._readiness_label = QLabel("Readiness: capture intrinsics samples to begin.")
        self._readiness_label.setWordWrap(True)
        self._profile_label = QLabel("Profile: none")
        self._profile_label.setWordWrap(True)
        self._quality_output = QPlainTextEdit()
        self._quality_output.setReadOnly(True)
        self._history_output = QPlainTextEdit()
        self._history_output.setReadOnly(True)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Calibration object", self._object_combo)
        form.addRow("Object detector", self._detector_combo)
        form.addRow("Calibration step", self._workflow_combo)
        form.addRow("Board columns", self._columns_spin)
        form.addRow("Board rows", self._rows_spin)
        form.addRow("Square size", self._square_size_spin)

        auto_row = QHBoxLayout()
        auto_row.addWidget(self._auto_checkbox)
        auto_row.addWidget(QLabel("Cooldown"))
        auto_row.addWidget(self._cooldown_spin)
        auto_row.addStretch(1)

        solve_row = QHBoxLayout()
        solve_row.addWidget(self._capture_button)
        solve_row.addWidget(self._solve_intrinsics_button)
        solve_row.addWidget(self._solve_extrinsics_button)

        file_row = QHBoxLayout()
        file_row.addWidget(self._load_button)
        file_row.addWidget(self._save_button)
        file_row.addWidget(self._reset_button)

        settings_box = QGroupBox("Calibration Settings")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addLayout(form)
        settings_layout.addLayout(auto_row)
        settings_layout.addLayout(solve_row)
        settings_layout.addLayout(file_row)
        settings_layout.addWidget(self._auto_label)
        settings_layout.addWidget(self._sync_label)
        settings_layout.addWidget(self._state_label)
        settings_layout.addWidget(self._sample_label)
        settings_layout.addWidget(self._readiness_label)
        settings_layout.addWidget(self._profile_label)

        quality_box = QGroupBox("Per-Camera Quality")
        quality_layout = QVBoxLayout(quality_box)
        quality_layout.addWidget(self._quality_output)

        history_box = QGroupBox("Sample History")
        history_layout = QVBoxLayout(history_box)
        history_layout.addWidget(self._history_output)

        output_box = QGroupBox("Calibration Output")
        output_layout = QVBoxLayout(output_box)
        output_layout.addWidget(self._output)

        root = QVBoxLayout(self)
        root.addWidget(settings_box)
        root.addWidget(quality_box)
        root.addWidget(history_box)
        root.addWidget(output_box, 1)

        self._capture_button.clicked.connect(self.capture_sample_requested.emit)
        self._solve_intrinsics_button.clicked.connect(self.solve_intrinsics_requested.emit)
        self._solve_extrinsics_button.clicked.connect(self.solve_extrinsics_requested.emit)
        self._load_button.clicked.connect(self.load_profile_requested.emit)
        self._save_button.clicked.connect(self.save_profile_requested.emit)
        self._reset_button.clicked.connect(self.reset_samples_requested.emit)
        self._workflow_combo.currentIndexChanged.connect(self._update_mode_ui)
        self._object_combo.currentIndexChanged.connect(self._on_settings_changed)
        self._detector_combo.currentIndexChanged.connect(self._on_settings_changed)
        self._columns_spin.valueChanged.connect(lambda *_args: self.settings_changed.emit())
        self._rows_spin.valueChanged.connect(lambda *_args: self.settings_changed.emit())
        self._square_size_spin.valueChanged.connect(lambda *_args: self.settings_changed.emit())
        self._update_mode_ui()

    def calibration_object_type(self) -> str:
        data = self._object_combo.currentData()
        return normalize_calibration_object_type(data if isinstance(data, str) else CALIBRATION_OBJECT_CHESSBOARD)

    def calibration_detector_name(self) -> str:
        data = self._detector_combo.currentData()
        return normalize_calibration_detector_name(data if isinstance(data, str) else CALIBRATION_DETECTOR_AUTO)

    def board_shape(self) -> tuple[int, int]:
        return int(self._columns_spin.value()), int(self._rows_spin.value())

    def square_size_m(self) -> float:
        return float(self._square_size_spin.value())

    def capture_mode(self) -> str:
        data = self._workflow_combo.currentData()
        return "sync_extrinsics" if data == "sync_extrinsics" else "intrinsics"

    def auto_capture_enabled(self) -> bool:
        return self._auto_checkbox.isChecked()

    def auto_capture_cooldown_sec(self) -> float:
        return float(self._cooldown_spin.value())

    def set_detection_preferences(self, object_type: str, detector_name: str) -> None:
        self._object_combo.setCurrentIndex(max(0, self._object_combo.findData(normalize_calibration_object_type(object_type))))
        self._detector_combo.setCurrentIndex(max(0, self._detector_combo.findData(normalize_calibration_detector_name(detector_name))))

    def set_board_shape(self, board_shape: tuple[int, int]) -> None:
        self._columns_spin.setValue(int(board_shape[0]))
        self._rows_spin.setValue(int(board_shape[1]))

    def set_square_size_m(self, square_size_m: float) -> None:
        self._square_size_spin.setValue(float(square_size_m))

    def set_auto_capture_status(self, text: str) -> None:
        self._auto_label.setText(text)

    def set_state(self, text: str) -> None:
        self._state_label.setText(text)

    def set_sync_status(self, text: str) -> None:
        self._sync_label.setText(text)

    def set_profile_path(self, path_text: str | None) -> None:
        self._profile_label.setText(f"Profile: {path_text}" if path_text else "Profile: none")

    def set_sample_counts(self, sample_counts: dict[str, int], synchronized_samples: int) -> None:
        if not sample_counts:
            self._sample_label.setText("Samples: none")
            return
        parts = [f"{source_id}={count}" for source_id, count in sorted(sample_counts.items())]
        parts.append(f"sync={synchronized_samples}")
        self._sample_label.setText("Samples: " + ", ".join(parts))

    def set_workflow_readiness(self, readiness: CalibrationWorkflowReadiness) -> None:
        note_text = " | ".join(readiness.notes[:3]) if readiness.notes else "Ready gates look good."
        self._readiness_label.setText(
            f"Readiness: intrinsics={'ready' if readiness.can_solve_intrinsics else 'waiting'} | "
            f"extrinsics={'ready' if readiness.can_solve_extrinsics else 'waiting'} | "
            f"sync sets={readiness.synchronized_samples}. {note_text}"
        )

    def set_camera_quality_scores(self, scores: dict[str, CalibrationCameraQuality]) -> None:
        if not scores:
            self._quality_output.setPlainText("No per-camera quality data yet.")
            return
        self._quality_output.setPlainText("\n".join(score.summary_text for _source_id, score in sorted(scores.items())))

    def set_sample_history(self, entries: Sequence[CalibrationSampleHistoryEntry]) -> None:
        history = list(entries)
        if not history:
            self._history_output.setPlainText("No stored calibration samples yet.")
            return
        self._history_output.setPlainText("\n".join(entry.summary_text for entry in history[-10:]))

    def append_output(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.moveCursor(QTextCursor.MoveOperation.End)
        self._output.ensureCursorVisible()

    def _update_mode_ui(self, *_args: object) -> None:
        if self.capture_mode() == "sync_extrinsics":
            self._capture_button.setText("Capture Extrinsics Sync Set")
        else:
            self._capture_button.setText("Capture Intrinsics Sample")

    def _on_settings_changed(self, *_args: object) -> None:
        if self.calibration_detector_name() == "charuco" and self.calibration_object_type() != "charuco":
            self.set_detection_preferences("charuco", "charuco")
        elif self.calibration_object_type() == "charuco" and self.calibration_detector_name() not in {"auto", "charuco"}:
            self.set_detection_preferences("charuco", "charuco")
        self.settings_changed.emit()


class ResultsWidget(QWidget):
    load_profile_requested = Signal()
    save_profile_requested = Signal()
    export_profile_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._project_label = QLabel("Project: none")
        self._project_label.setWordWrap(True)
        self._profile_label = QLabel("Profile: none")
        self._profile_label.setWordWrap(True)
        self._summary_label = QLabel("No calibration results yet.")
        self._summary_label.setWordWrap(True)
        self._acceptance_label = QLabel("Acceptance: not evaluated")
        self._acceptance_label.setWordWrap(True)
        self._load_button = QPushButton("Load Profile")
        self._save_button = QPushButton("Save Profile As")
        self._export_button = QPushButton("Export Versioned Profile")
        self._save_button.setEnabled(False)
        self._export_button.setEnabled(False)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._load_button)
        buttons.addWidget(self._save_button)
        buttons.addWidget(self._export_button)
        buttons.addStretch(1)

        box = QGroupBox("Results + Export")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(self._project_label)
        box_layout.addWidget(self._profile_label)
        box_layout.addWidget(self._summary_label)
        box_layout.addWidget(self._acceptance_label)
        box_layout.addLayout(buttons)

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout(output_box)
        output_layout.addWidget(self._output)

        root = QVBoxLayout(self)
        root.addWidget(box)
        root.addWidget(output_box, 1)

        self._load_button.clicked.connect(self.load_profile_requested.emit)
        self._save_button.clicked.connect(self.save_profile_requested.emit)
        self._export_button.clicked.connect(self.export_profile_requested.emit)

    def set_project(self, project: CalibrationProject | None) -> None:
        self._project_label.setText("Project: none" if project is None else f"Project: {project.name} | {project.root_dir}")

    def set_profile_path(self, path_text: str | None) -> None:
        self._profile_label.setText(f"Profile: {path_text}" if path_text else "Profile: none")

    def set_bundle(self, bundle: CalibrationBundle | None) -> None:
        self._save_button.setEnabled(bundle is not None)
        self._export_button.setEnabled(bundle is not None)
        if bundle is None:
            self._summary_label.setText("No calibration results yet.")
            self._acceptance_label.setText("Acceptance: not evaluated")
            return
        report = evaluate_calibration_bundle(bundle)
        solved = [source_id for source_id, camera in sorted(bundle.cameras.items()) if camera.status == "solved"]
        self._summary_label.setText(f"Cameras={len(bundle.cameras)} | solved extrinsics={len(solved)}")
        self._acceptance_label.setText(f"Acceptance: {report.status} | score={report.score:.0f}/100")

    def append_output(self, text: str) -> None:
        self._output.appendPlainText(text)
        self._output.moveCursor(QTextCursor.MoveOperation.End)
        self._output.ensureCursorVisible()


def _auto_spin(maximum: float, suffix: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, maximum)
    spin.setDecimals(0)
    spin.setSpecialValueText("Auto")
    spin.setSuffix(suffix)
    return spin


def _optional_spin_value(spin: QDoubleSpinBox) -> float | None:
    value = float(spin.value())
    if value <= float(spin.minimum()):
        return None
    return value
