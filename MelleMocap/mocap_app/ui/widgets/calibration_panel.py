from __future__ import annotations

from typing import Any, Literal

import cv2
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from mocap_app.io.calibration_io import ChessboardDetectionResult
from mocap_app.models.types import CalibrationBundle, CameraCalibration


class CalibrationPreviewTile(QFrame):
    """Single camera tile used by the calibration panel."""

    undistort_toggled = Signal(str, bool)

    def __init__(self, source_id: str) -> None:
        super().__init__()
        self._source_id = source_id
        self._title = QLabel(source_id)
        self._title.setStyleSheet("font-weight: 600; color: #1f2937;")
        self._undistort_checkbox = QCheckBox("Undistort")
        self._undistort_checkbox.toggled.connect(
            lambda checked: self.undistort_toggled.emit(self._source_id, checked)
        )
        self._image = QLabel("No Frame")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(280, 190)
        self._image.setStyleSheet("background: #f8fafc; border: 1px solid #cbd5e1; color: #64748b;")
        self._status = QLabel("Awaiting detections")
        self._status.setStyleSheet("color: #475569;")
        self._last_pixmap: QPixmap | None = None

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._undistort_checkbox)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)
        root.addLayout(header)
        root.addWidget(self._image, stretch=1)
        root.addWidget(self._status)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame { background: #ffffff; border: 1px solid #d4dde8; border-radius: 4px; }")

    @property
    def source_id(self) -> str:
        return self._source_id

    def undistort_enabled(self) -> bool:
        return self._undistort_checkbox.isChecked()

    def set_frame(self, frame_bgr, status_message: str) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        image = QImage(rgb.data, w, h, c * w, QImage.Format.Format_RGB888).copy()
        self._last_pixmap = QPixmap.fromImage(image)
        self._render()
        self._status.setText(status_message)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._render()
        super().resizeEvent(event)

    def _render(self) -> None:
        if self._last_pixmap is None:
            return
        self._image.setPixmap(
            self._last_pixmap.scaled(
                self._image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CalibrationPanelWidget(QWidget):
    """Dedicated calibration workflow panel with previews and diagnostics."""

    capture_requested = Signal()
    solve_requested = Signal()
    solve_extrinsics_requested = Signal()
    reset_requested = Signal()
    save_profile_requested = Signal()
    load_profile_requested = Signal()
    undistort_toggled = Signal(str, bool)
    pattern_changed = Signal(str)
    sync_thresholds_changed = Signal(float, float)
    workflow_mode_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._tiles: dict[str, CalibrationPreviewTile] = {}
        self._source_order: list[str] = []

        self._capture_button = QPushButton("Capture Valid Sample(s)")
        self._solve_button = QPushButton("Solve Intrinsics")
        self._solve_extrinsics_button = QPushButton("Solve Extrinsics")
        self._reset_button = QPushButton("Reset Samples")
        self._save_button = QPushButton("Save Profile")
        self._load_button = QPushButton("Load Profile")
        self._workflow_mode_combo = QComboBox()
        self._workflow_mode_combo.addItem("Intrinsics", "intrinsics")
        self._workflow_mode_combo.addItem("Sync / Extrinsics", "sync_extrinsics")
        self._pattern_combo = QComboBox()
        self._pattern_combo.addItem("Chessboard", "chessboard")
        self._auto_capture_checkbox = QCheckBox("Auto Capture Valid Samples")
        self._auto_capture_checkbox.setChecked(False)
        self._relaxed_sync_checkbox = QCheckBox("Relax Sync Thresholds")
        self._relaxed_sync_checkbox.setChecked(True)
        self._auto_capture_cooldown_spin = QDoubleSpinBox()
        self._auto_capture_cooldown_spin.setRange(0.3, 10.0)
        self._auto_capture_cooldown_spin.setDecimals(1)
        self._auto_capture_cooldown_spin.setSingleStep(0.1)
        self._auto_capture_cooldown_spin.setValue(1.0)
        self._sync_quality_spin = QDoubleSpinBox()
        self._sync_quality_spin.setRange(0.0, 1.0)
        self._sync_quality_spin.setDecimals(2)
        self._sync_quality_spin.setSingleStep(0.05)
        self._sync_quality_spin.setValue(0.20)
        self._sync_coverage_spin = QDoubleSpinBox()
        self._sync_coverage_spin.setRange(0.0, 25.0)
        self._sync_coverage_spin.setDecimals(1)
        self._sync_coverage_spin.setSingleStep(0.2)
        self._sync_coverage_spin.setSuffix(" %")
        self._sync_coverage_spin.setValue(1.8)
        self._auto_status = QLabel("Auto capture off.")
        self._auto_status.setStyleSheet("color: #475569;")

        for button in [
            self._capture_button,
            self._solve_button,
            self._solve_extrinsics_button,
            self._reset_button,
            self._save_button,
            self._load_button,
        ]:
            button.setMinimumHeight(34)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("Workflow"))
        toolbar.addWidget(self._workflow_mode_combo)
        toolbar.addWidget(QLabel("Pattern"))
        toolbar.addWidget(self._pattern_combo)
        toolbar.addWidget(self._capture_button)
        toolbar.addWidget(self._solve_button)
        toolbar.addWidget(self._solve_extrinsics_button)
        toolbar.addWidget(self._reset_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self._save_button)
        toolbar.addWidget(self._load_button)

        auto_toolbar = QHBoxLayout()
        auto_toolbar.setSpacing(8)
        auto_toolbar.addWidget(self._auto_capture_checkbox)
        auto_toolbar.addWidget(QLabel("Cooldown (s)"))
        auto_toolbar.addWidget(self._auto_capture_cooldown_spin)
        auto_toolbar.addWidget(self._relaxed_sync_checkbox)
        auto_toolbar.addWidget(QLabel("Sync Min Quality"))
        auto_toolbar.addWidget(self._sync_quality_spin)
        auto_toolbar.addWidget(QLabel("Sync Min Coverage"))
        auto_toolbar.addWidget(self._sync_coverage_spin)
        auto_toolbar.addWidget(self._auto_status, stretch=1)
        auto_toolbar.addStretch(1)

        self._preview_container = QWidget()
        self._preview_layout = QGridLayout(self._preview_container)
        self._preview_layout.setContentsMargins(4, 4, 4, 4)
        self._preview_layout.setSpacing(6)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Camera", "Intrinsics / Total", "Intrinsics Status", "Reproj Error", "Image Size", "Diagnostics"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        self._feedback = QLabel("Calibration feedback will appear here.")
        self._feedback.setWordWrap(True)
        self._feedback.setStyleSheet("color: #1f2937;")

        self._warnings = QTextEdit()
        self._warnings.setReadOnly(True)
        self._warnings.setPlaceholderText("Diagnostics warnings and TODO hooks...")

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self._table, stretch=2)
        right_layout.addWidget(self._feedback)
        right_layout.addWidget(self._warnings, stretch=1)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._preview_container)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([1100, 650])

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addLayout(toolbar)
        root.addLayout(auto_toolbar)
        root.addWidget(split, stretch=1)

        self._capture_button.clicked.connect(self.capture_requested)
        self._solve_button.clicked.connect(self.solve_requested)
        self._solve_extrinsics_button.clicked.connect(self.solve_extrinsics_requested)
        self._reset_button.clicked.connect(self.reset_requested)
        self._save_button.clicked.connect(self.save_profile_requested)
        self._load_button.clicked.connect(self.load_profile_requested)
        self._pattern_combo.currentIndexChanged.connect(self._emit_pattern_changed)
        self._workflow_mode_combo.currentIndexChanged.connect(self._emit_workflow_mode_changed)
        self._sync_quality_spin.valueChanged.connect(self._emit_sync_thresholds_changed)
        self._sync_coverage_spin.valueChanged.connect(self._emit_sync_thresholds_changed)
        self._apply_workflow_mode_ui()

        self.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                color: #1f2937;
                border: 1px solid #d4dde8;
                gridline-color: #d8e0ea;
            }
            QHeaderView::section {
                background: #eef3f9;
                color: #1f2937;
                border: 1px solid #d4dde8;
                padding: 5px;
            }
            QTextEdit {
                background: #ffffff;
                color: #1f2937;
                border: 1px solid #d4dde8;
            }
            """
        )

    def set_sources(self, source_ids: list[str]) -> None:
        source_ids = source_ids[:4]
        existing = set(self._tiles.keys())
        requested = set(source_ids)
        if source_ids == self._source_order and existing == requested:
            return

        for source_id in sorted(existing - requested):
            tile = self._tiles.pop(source_id)
            self._preview_layout.removeWidget(tile)
            tile.deleteLater()

        for source_id in source_ids:
            if source_id in self._tiles:
                continue
            tile = CalibrationPreviewTile(source_id)
            tile.undistort_toggled.connect(self.undistort_toggled)
            self._tiles[source_id] = tile

        self._source_order = list(source_ids)
        self._rebuild_preview_layout()

    def undistort_enabled_for(self, source_id: str) -> bool:
        tile = self._tiles.get(source_id)
        return tile.undistort_enabled() if tile else False

    def current_pattern(self) -> str:
        data = self._pattern_combo.currentData()
        return str(data if data is not None else "chessboard").lower()

    def current_workflow_mode(self) -> Literal["intrinsics", "sync_extrinsics"]:
        data = self._workflow_mode_combo.currentData()
        mode = str(data if data is not None else "intrinsics").lower().strip()
        if mode == "sync_extrinsics":
            return "sync_extrinsics"
        return "intrinsics"

    def set_workflow_mode(self, mode: str) -> None:
        target = mode.lower().strip()
        index = self._workflow_mode_combo.findData(target)
        self._workflow_mode_combo.blockSignals(True)
        self._workflow_mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self._workflow_mode_combo.blockSignals(False)
        self._apply_workflow_mode_ui()

    def auto_capture_enabled(self) -> bool:
        return self._auto_capture_checkbox.isChecked()

    def auto_capture_cooldown_sec(self) -> float:
        return float(self._auto_capture_cooldown_spin.value())

    def relaxed_sync_enabled(self) -> bool:
        return self._relaxed_sync_checkbox.isChecked()

    def set_auto_capture_status(self, message: str) -> None:
        self._auto_status.setText(message)

    def set_sync_threshold_values(self, min_quality: float, min_coverage_ratio: float) -> None:
        self._sync_quality_spin.blockSignals(True)
        self._sync_coverage_spin.blockSignals(True)
        self._sync_quality_spin.setValue(min_quality)
        self._sync_coverage_spin.setValue(min_coverage_ratio * 100.0)
        self._sync_quality_spin.blockSignals(False)
        self._sync_coverage_spin.blockSignals(False)

    def sync_threshold_values(self) -> tuple[float, float]:
        return float(self._sync_quality_spin.value()), float(self._sync_coverage_spin.value()) / 100.0

    def set_pattern_options(self, pattern_names: list[str], selected: str) -> None:
        current = self.current_pattern()
        self._pattern_combo.blockSignals(True)
        self._pattern_combo.clear()
        for name in pattern_names:
            key = name.lower().strip()
            label = "Charuco" if key == "charuco" else "Chessboard"
            self._pattern_combo.addItem(label, key)
        if self._pattern_combo.count() == 0:
            self._pattern_combo.addItem("Chessboard", "chessboard")
        target = selected.lower().strip() if selected else current
        index = self._pattern_combo.findData(target)
        self._pattern_combo.setCurrentIndex(index if index >= 0 else 0)
        self._pattern_combo.blockSignals(False)
        self._emit_pattern_changed()

    def update_previews(
        self,
        preview_frames: dict[str, Any],
        detections: dict[str, ChessboardDetectionResult],
        sample_counts: dict[str, int],
    ) -> None:
        for source_id, frame_bgr in preview_frames.items():
            tile = self._tiles.get(source_id)
            if tile is None:
                continue
            detection = detections.get(source_id)
            count = sample_counts.get(source_id, 0)
            status = f"Intrinsics={count}"
            if detection is not None and detection.found:
                status += (
                    f" | {detection.pattern_type}"
                    f" | corners={detection.detected_corners}"
                    f" | q={detection.quality_score:.2f}"
                    f" | cov={detection.coverage_ratio * 100:.1f}%"
                )
            elif detection is not None:
                status += f" | {detection.pattern_type} not found"
            tile.set_frame(frame_bgr, status)

    def update_camera_status_table(
        self,
        source_ids: list[str],
        sample_counts: dict[str, int],
        sample_breakdown: dict[str, dict[str, int]],
        bundle: CalibrationBundle | None,
        live_detection: dict[str, ChessboardDetectionResult] | None = None,
    ) -> None:
        self._table.setRowCount(len(source_ids))
        for row, source_id in enumerate(source_ids):
            camera = bundle.cameras.get(source_id) if bundle else None
            breakdown = sample_breakdown.get(source_id, {})
            diagnostics = []
            if camera and camera.diagnostics:
                diagnostics.extend(camera.diagnostics)
            if live_detection and source_id in live_detection:
                diagnostics.extend(live_detection[source_id].diagnostics)
            sync_only = int(breakdown.get("sync_only", 0))
            synchronized = int(breakdown.get("synchronized", 0))
            if sync_only > 0:
                diagnostics.append(f"{sync_only} sync-only sample(s) stored with relaxed thresholds.")
            elif synchronized > 0:
                diagnostics.append(f"{synchronized} synchronized sample(s) stored.")

            self._table.setItem(row, 0, QTableWidgetItem(source_id))
            self._table.setItem(
                row,
                1,
                QTableWidgetItem(
                    f"{sample_counts.get(source_id, 0)} / {int(breakdown.get('total', sample_counts.get(source_id, 0)))}"
                ),
            )
            self._table.setItem(row, 2, QTableWidgetItem(self._status_text(camera)))
            self._table.setItem(
                row,
                3,
                QTableWidgetItem(
                    f"{camera.reprojection_error:.4f}px"
                    if camera and camera.reprojection_error is not None
                    else "-"
                ),
            )
            self._table.setItem(
                row,
                4,
                QTableWidgetItem(
                    f"{camera.image_size[0]}x{camera.image_size[1]}"
                    if camera and camera.image_size
                    else "-"
                ),
            )
            self._table.setItem(row, 5, QTableWidgetItem("; ".join(dict.fromkeys(diagnostics)) or "-"))

    def show_feedback(self, message: str, success: bool) -> None:
        color = "#8df0b0" if success else "#ffd37e"
        self._feedback.setStyleSheet(f"color: {color};")
        self._feedback.setText(message)

    def show_warnings(self, lines: list[str]) -> None:
        self._warnings.setPlainText("\n".join(lines))

    def _status_text(self, camera: CameraCalibration | None) -> str:
        if camera is None:
            return "unsolved"
        return camera.status

    def _rebuild_preview_layout(self) -> None:
        while self._preview_layout.count():
            item = self._preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        if not self._source_order:
            return

        columns = 1 if len(self._source_order) == 1 else 2
        rows = (len(self._source_order) + columns - 1) // columns

        for col in range(columns):
            self._preview_layout.setColumnStretch(col, 1)
        for row in range(rows):
            self._preview_layout.setRowStretch(row, 1)

        for idx, source_id in enumerate(self._source_order):
            row = idx // columns
            col = idx % columns
            self._preview_layout.addWidget(self._tiles[source_id], row, col)

    def _emit_pattern_changed(self) -> None:
        self.pattern_changed.emit(self.current_pattern())

    def _emit_sync_thresholds_changed(self) -> None:
        quality, coverage_ratio = self.sync_threshold_values()
        self.sync_thresholds_changed.emit(quality, coverage_ratio)

    def _emit_workflow_mode_changed(self) -> None:
        self._apply_workflow_mode_ui()
        self.workflow_mode_changed.emit(self.current_workflow_mode())

    def _apply_workflow_mode_ui(self) -> None:
        mode = self.current_workflow_mode()
        sync_controls_enabled = mode == "sync_extrinsics"
        self._relaxed_sync_checkbox.setEnabled(sync_controls_enabled)
        self._sync_quality_spin.setEnabled(sync_controls_enabled)
        self._sync_coverage_spin.setEnabled(sync_controls_enabled)

        if mode == "sync_extrinsics":
            self._capture_button.setText("Capture Sync Set(s)")
        else:
            self._capture_button.setText("Capture Intrinsics Sample(s)")
