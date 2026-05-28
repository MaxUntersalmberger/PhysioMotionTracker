from __future__ import annotations

import io
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import cv2
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFileIconProvider,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mocap_app.io.calibration_io import ChessboardDetectionResult
from mocap_app.io.toml_export import calibration_bundle_to_toml
from mocap_app.models.types import (
    CalibrationBoardSettings,
    CalibrationBundle,
    CameraCalibration,
    CameraProbeResult,
    CameraSourceConfig,
    RuntimeTuning,
)
from mocap_app.ui.main_window import MainWindow as FunctionalMainWindow
from ui.gui import Ui_MainWindow
from ui.guiStyle import apply_styles


class ConsoleStream(io.StringIO):
    def __init__(self, console_widget: QPlainTextEdit) -> None:
        super().__init__()
        self._console_widget = console_widget

    def write(self, text: str) -> int:
        if text.strip():
            self._console_widget.appendPlainText(text.rstrip())
        return len(text)

    def flush(self) -> None:
        return None


class DesignedPreviewPopout(QDialog):
    rename_requested = Signal()
    auto_capture_toggled = Signal(bool)
    overlay_toggled = Signal(bool)
    mirror_toggled = Signal(bool)
    undistort_toggled = Signal(bool)
    remove_requested = Signal()

    def __init__(self, title: str, display_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last_pixmap: QPixmap | None = None
        self.setWindowTitle(title)
        self.resize(900, 620)

        self._title_button = QPushButton(display_name)
        self._title_button.setToolTip("Rename camera")
        self._title_button.setMinimumWidth(110)
        self._auto_button = QPushButton("Auto")
        self._auto_button.setCheckable(True)
        self._auto_button.setToolTip("Start auto capture")
        self._overlay_button = QPushButton("Overlay")
        self._overlay_button.setCheckable(True)
        self._overlay_button.setToolTip("Toggle detection overlay for this camera")
        self._mirror_button = QPushButton("Mirror")
        self._mirror_button.setCheckable(True)
        self._mirror_button.setToolTip("Mirror this camera preview")
        self._undistort_button = QPushButton("Undistort")
        self._undistort_button.setCheckable(True)
        self._undistort_button.setToolTip("Toggle undistortion preview")
        self._delete_button = QPushButton("X")
        self._delete_button.setToolTip("Remove this source from the source list")
        self._delete_button.setFixedWidth(42)

        controls = QHBoxLayout()
        controls.setContentsMargins(6, 6, 6, 0)
        controls.setSpacing(8)
        controls.addWidget(self._title_button, stretch=1)
        controls.addWidget(self._auto_button)
        controls.addWidget(self._overlay_button)
        controls.addWidget(self._mirror_button)
        controls.addWidget(self._undistort_button)
        controls.addWidget(self._delete_button)

        self._image = QLabel("No frame")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(1, 1)
        self._image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image.setStyleSheet("background-color: black; color: white;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(controls)
        layout.addWidget(self._image)

        self._title_button.clicked.connect(self.rename_requested)
        self._auto_button.toggled.connect(self.auto_capture_toggled)
        self._overlay_button.toggled.connect(self.overlay_toggled)
        self._mirror_button.toggled.connect(self.mirror_toggled)
        self._undistort_button.toggled.connect(self.undistort_toggled)
        self._delete_button.clicked.connect(self.remove_requested)

    def set_display_name(self, name: str) -> None:
        self._title_button.setText(name)
        self._title_button.setToolTip(f"Rename camera: {name}")

    def set_auto_active(self, active: bool) -> None:
        self._auto_button.blockSignals(True)
        self._auto_button.setChecked(active)
        self._auto_button.blockSignals(False)

    def set_overlay_active(self, active: bool) -> None:
        self._overlay_button.blockSignals(True)
        self._overlay_button.setChecked(active)
        self._overlay_button.blockSignals(False)

    def set_mirror_active(self, active: bool) -> None:
        self._mirror_button.blockSignals(True)
        self._mirror_button.setChecked(active)
        self._mirror_button.blockSignals(False)

    def set_undistort_active(self, active: bool) -> None:
        self._undistort_button.blockSignals(True)
        self._undistort_button.setChecked(active)
        self._undistort_button.blockSignals(False)

    def set_frame(self, pixmap: QPixmap) -> None:
        self._last_pixmap = pixmap
        self._render()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._render()
        super().resizeEvent(event)

    def _render(self) -> None:
        if self._last_pixmap is None:
            return
        target_size = self._image.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        self._image.setPixmap(
            self._last_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class DesignedPreviewTile(QFrame):
    undistort_toggled = Signal(str, bool)
    auto_capture_requested = Signal()
    auto_capture_toggled = Signal(bool)
    preview_options_changed = Signal()
    remove_requested = Signal(str)
    name_changed = Signal(str, str)

    def __init__(self, source_id: str) -> None:
        super().__init__()
        self._source_id = source_id
        self._last_pixmap: QPixmap | None = None
        self._popout: DesignedPreviewPopout | None = None

        self._display_name = source_id
        self._title_button = QPushButton(source_id)
        self._title_button.setToolTip("Rename camera")
        self._title_button.setMinimumWidth(72)
        self._open_button = QPushButton("Open")
        self._open_button.setToolTip("Open camera feed in a separate window")
        self._open_button.setMinimumWidth(58)
        self._open_button.setCheckable(True)
        self._auto_button = QPushButton("Auto")
        self._auto_button.setToolTip("Start auto capture")
        self._auto_button.setMinimumWidth(58)
        self._auto_button.setCheckable(True)
        self._overlay_button = QPushButton("Overlay")
        self._overlay_button.setToolTip("Toggle detection overlay for this camera")
        self._overlay_button.setMinimumWidth(70)
        self._overlay_button.setCheckable(True)
        self._overlay_button.setChecked(True)
        self._mirror_button = QPushButton("Mirror")
        self._mirror_button.setToolTip("Mirror this camera preview")
        self._mirror_button.setMinimumWidth(62)
        self._mirror_button.setCheckable(True)
        self._undistort = QPushButton("Undistort")
        self._undistort.setToolTip("Toggle undistortion preview")
        self._undistort.setMinimumWidth(82)
        self._undistort.setCheckable(True)
        self._delete_button = QPushButton("X")
        self._delete_button.setToolTip("Remove this source from the source list")
        self._delete_button.setFixedWidth(42)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(self._title_button, stretch=1)
        controls.addWidget(self._open_button)
        controls.addWidget(self._auto_button)
        controls.addWidget(self._overlay_button)
        controls.addWidget(self._mirror_button)
        controls.addWidget(self._undistort)
        controls.addWidget(self._delete_button)

        self._image = QLabel("No frame")
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(320, 220)
        self._image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._image.setStyleSheet("background-color: black; color: white;")

        self._status = QLabel("Waiting for live feed")
        self._status.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress.setFormat("0/100")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        layout.addLayout(controls)
        layout.addWidget(self._image, stretch=1)
        layout.addWidget(self._status)
        layout.addWidget(self._progress)

        self.setFrameShape(QFrame.Shape.Box)
        self.setMinimumSize(500, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._title_button.clicked.connect(self._rename_camera)
        self._open_button.clicked.connect(self._toggle_popout)
        self._auto_button.clicked.connect(self._toggle_auto_capture)
        self._delete_button.clicked.connect(lambda: self.remove_requested.emit(self._source_id))
        self._overlay_button.toggled.connect(self._toggle_overlay)
        self._mirror_button.toggled.connect(self._toggle_mirror)
        self._undistort.toggled.connect(self._toggle_undistort)

    @property
    def source_id(self) -> str:
        return self._source_id

    def undistort_enabled(self) -> bool:
        return self._undistort.isChecked()

    def overlay_enabled(self) -> bool:
        return self._overlay_button.isChecked()

    def mirror_enabled(self) -> bool:
        return self._mirror_button.isChecked()

    def display_name(self) -> str:
        return self._display_name.strip() or self._source_id

    def set_display_name(self, name: str) -> None:
        self._display_name = name.strip() or self._source_id
        self._title_button.setText(self._display_name)
        self._title_button.setToolTip(f"Rename camera: {self._display_name}")
        if self._popout is not None:
            self._popout.setWindowTitle(f"Live Feed - {self._display_name}")
            self._popout.set_display_name(self._display_name)

    def _emit_name_changed(self) -> None:
        self.name_changed.emit(self._source_id, self.display_name())

    def _rename_camera(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Rename camera",
            "Camera name:",
            text=self.display_name(),
        )
        if not accepted:
            return
        self.set_display_name(name)
        self._emit_name_changed()

    def set_auto_active(self, active: bool) -> None:
        self._auto_button.blockSignals(True)
        self._auto_button.setChecked(active)
        self._auto_button.blockSignals(False)
        if self._popout is not None:
            self._popout.set_auto_active(active)

    def set_overlay_active(self, active: bool) -> None:
        self._overlay_button.blockSignals(True)
        self._overlay_button.setChecked(active)
        self._overlay_button.blockSignals(False)
        if self._popout is not None:
            self._popout.set_overlay_active(active)
        self.preview_options_changed.emit()

    def set_mirror_active(self, active: bool) -> None:
        self._mirror_button.blockSignals(True)
        self._mirror_button.setChecked(active)
        self._mirror_button.blockSignals(False)
        if self._popout is not None:
            self._popout.set_mirror_active(active)
        self.preview_options_changed.emit()

    def set_progress(self, current: int, maximum: int, label: str | None = None) -> None:
        current = max(0, int(current))
        maximum = max(0, int(maximum))
        if maximum <= 0:
            self._progress.setRange(0, 100)
            self._progress.setValue(0)
            self._progress.setFormat(label or f"{current} / No limit")
            return
        self._progress.setRange(0, 100)
        percent = int(round(min(current, maximum) * 100.0 / maximum))
        self._progress.setValue(max(0, min(100, percent)))
        self._progress.setFormat(label or f"{current}/{maximum}")

    def set_sample_count(self, count: int) -> None:
        self.set_progress(count, 100, f"{int(count)}/100")

    def set_frame(
        self,
        frame_bgr: Any,
        status: str,
        progress_current: int,
        progress_maximum: int,
        progress_label: str | None = None,
    ) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()
        self._last_pixmap = QPixmap.fromImage(image)
        self._status.setText(status)
        self.set_progress(progress_current, progress_maximum, progress_label)
        self._render()
        if self._popout is not None:
            self._popout.set_frame(self._last_pixmap)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self._render()
        super().resizeEvent(event)

    def _toggle_popout(self, checked: bool) -> None:
        if checked:
            self._open_popout()
        elif self._popout is not None:
            self._popout.close()

    def _toggle_auto_capture(self, checked: bool) -> None:
        self._auto_button.blockSignals(True)
        self._auto_button.setChecked(checked)
        self._auto_button.blockSignals(False)
        if self._popout is not None:
            self._popout.set_auto_active(checked)
        self.auto_capture_toggled.emit(checked)
        if checked:
            self.auto_capture_requested.emit()

    def _toggle_undistort(self, checked: bool) -> None:
        if self._popout is not None:
            self._popout.set_undistort_active(checked)
        self.undistort_toggled.emit(self._source_id, checked)
        self.preview_options_changed.emit()

    def _toggle_overlay(self, checked: bool) -> None:
        if self._popout is not None:
            self._popout.set_overlay_active(checked)
        self.preview_options_changed.emit()

    def _toggle_mirror(self, checked: bool) -> None:
        if self._popout is not None:
            self._popout.set_mirror_active(checked)
        self.preview_options_changed.emit()

    def _set_undistort_from_popout(self, checked: bool) -> None:
        self._undistort.blockSignals(True)
        self._undistort.setChecked(checked)
        self._undistort.blockSignals(False)
        self.undistort_toggled.emit(self._source_id, checked)
        self.preview_options_changed.emit()

    def _set_overlay_from_popout(self, checked: bool) -> None:
        self._overlay_button.blockSignals(True)
        self._overlay_button.setChecked(checked)
        self._overlay_button.blockSignals(False)
        self.preview_options_changed.emit()

    def _set_mirror_from_popout(self, checked: bool) -> None:
        self._mirror_button.blockSignals(True)
        self._mirror_button.setChecked(checked)
        self._mirror_button.blockSignals(False)
        self.preview_options_changed.emit()

    def close_popout(self) -> None:
        if self._popout is not None:
            self._popout.close()

    def _open_popout(self) -> None:
        if self._popout is None:
            self._popout = DesignedPreviewPopout(f"Live Feed - {self.display_name()}", self.display_name(), self)
            self._popout.rename_requested.connect(self._rename_camera)
            self._popout.auto_capture_toggled.connect(self._toggle_auto_capture)
            self._popout.overlay_toggled.connect(self._set_overlay_from_popout)
            self._popout.mirror_toggled.connect(self._set_mirror_from_popout)
            self._popout.undistort_toggled.connect(self._set_undistort_from_popout)
            self._popout.remove_requested.connect(lambda: self.remove_requested.emit(self._source_id))
            self._popout.finished.connect(self._on_popout_closed)
            self._popout.set_auto_active(self._auto_button.isChecked())
            self._popout.set_overlay_active(self._overlay_button.isChecked())
            self._popout.set_mirror_active(self._mirror_button.isChecked())
            self._popout.set_undistort_active(self._undistort.isChecked())
        if self._last_pixmap is not None:
            self._popout.set_frame(self._last_pixmap)
        self._popout.show()
        self._popout.raise_()
        self._popout.activateWindow()
        self._open_button.blockSignals(True)
        self._open_button.setChecked(True)
        self._open_button.blockSignals(False)

    def _on_popout_closed(self) -> None:
        self._popout = None
        self._open_button.blockSignals(True)
        self._open_button.setChecked(False)
        self._open_button.blockSignals(False)

    def _render(self) -> None:
        if self._last_pixmap is None:
            return
        target_size = self._image.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        self._image.setPixmap(
            self._last_pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class DesignedCalibrationPanel(QtCore.QObject):
    new_project_requested = Signal()
    start_live_requested = Signal(object, float)
    stop_live_requested = Signal()
    runtime_tuning_changed = Signal(object)
    probe_cameras_requested = Signal(int)
    ui_message = Signal(str)
    capture_requested = Signal()
    solve_requested = Signal()
    solve_extrinsics_requested = Signal()
    reset_requested = Signal()
    save_profile_requested = Signal()
    load_profile_requested = Signal()
    undistort_toggled = Signal(str, bool)
    auto_capture_start_requested = Signal()
    pattern_changed = Signal(str)
    board_settings_applied = Signal(object)
    acceptance_thresholds_changed = Signal(float, float)
    workflow_mode_changed = Signal(str)
    spatial_grid_changed = Signal(int, int)
    sources_changed = Signal(object)
    preview_options_changed = Signal()

    def __init__(self, window: "DesignedMainWindow", default_camera_csv: str, default_fps: float) -> None:
        super().__init__(window)
        self.window = window
        self._tiles: dict[str, DesignedPreviewTile] = {}
        self._source_order: list[str] = []
        self._last_camera_grid_columns = 0
        self._live_active = False
        self._active_cameras = 0
        self._sync_progress_count = 0
        self._project_root = Path.cwd()
        self._icon_provider = QFileIconProvider()
        self._camera_names = dict(getattr(self.window._config, "camera_labels", {}) or {})
        self._wheel_guarded_widgets: list[QtCore.QObject] = []
        self._last_results_bundle: CalibrationBundle | None = None

        self._setup_navigation()
        self._setup_console()
        self._setup_camera_page(default_camera_csv, default_fps)
        self._setup_results_page()
        self._setup_directory_page()
        self._setup_diagnostics_page()
        self._setup_advanced_page(default_camera_csv, default_fps)
        self._connect_designed_actions()
        self.switch_page(0)

    def _setup_navigation(self) -> None:
        self._nav_buttons = [
            self.window.btn_home,
            self.window.btn_cameras,
            self.window.btn_results,
            self.window.btn_directory,
            self.window.btn_diagnostics,
            self.window.btn_advanced_settings,
        ]
        for index, button in enumerate(self._nav_buttons):
            button.clicked.connect(lambda _checked=False, page=index: self.switch_page(page))

    def _setup_console(self) -> None:
        self.window.plaintextedit_console.setReadOnly(True)
        self.window.lineedit_console_input.returnPressed.connect(self._handle_console_input)
        sys.stdout = ConsoleStream(self.window.plaintextedit_console)
        sys.stderr = ConsoleStream(self.window.plaintextedit_console)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            hasattr(self, "_camera_scroll")
            and watched is self._camera_scroll.viewport()
            and event.type() == QtCore.QEvent.Type.Resize
        ):
            QtCore.QTimer.singleShot(0, self._rebuild_camera_grid_if_columns_changed)
        if (
            event.type() == QtCore.QEvent.Type.Wheel
            and watched in self._wheel_guarded_widgets
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _block_wheel_changes(self, *widgets: QWidget) -> None:
        for widget in widgets:
            if widget in self._wheel_guarded_widgets:
                continue
            widget.installEventFilter(self)
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._wheel_guarded_widgets.append(widget)

    def _prepare_settings_container(self, root: QWidget) -> None:
        root.setMaximumWidth(760)
        root.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        for widget in root.findChildren(QSpinBox):
            widget.setMaximumWidth(145)
            self._block_wheel_changes(widget)
        for widget in root.findChildren(QDoubleSpinBox):
            widget.setMaximumWidth(165)
            self._block_wheel_changes(widget)
        for widget in root.findChildren(QComboBox):
            widget.setMaximumWidth(240)
            self._block_wheel_changes(widget)
        for widget in root.findChildren(QLineEdit):
            widget.setMaximumWidth(360)

    def _setup_camera_page(self, default_camera_csv: str, default_fps: float) -> None:
        self._setup_camera_splitter()
        self.window.spin_cap_fps.setRange(1, 120)
        self.window.spin_cap_fps.setValue(max(1, int(round(default_fps))))
        self.window.btn_cap_intrinsics_start.setCheckable(True)
        self.window.btn_cap_extrinsics_start.setCheckable(True)
        self.window.btn_cap_intrinsics_start.setText("Intrinsics Mode")
        self.window.btn_cap_extrinsics_start.setText("Extrinsics Mode")

        self.window.combo_cap_pattern.blockSignals(True)
        self.window.combo_cap_pattern.clear()
        self.window.combo_cap_pattern.addItem("Chessboard", "chessboard")
        self.window.combo_cap_pattern.addItem("Charuco", "charuco")
        self.window.combo_cap_pattern.blockSignals(False)
        self._block_wheel_changes(self.window.spin_cap_fps, self.window.combo_cap_pattern)

        self.window.btn_camera_detect.clicked.connect(
            lambda: self.probe_cameras_requested.emit(int(self._probe_max_spin.value()))
        )
        self.window.btn_camera_start_live.clicked.connect(self._emit_start_live)
        self.window.btn_camera_stop_live.clicked.connect(self.stop_live_requested)

        self._camera_scroll = QScrollArea()
        self._camera_scroll.setWidgetResizable(True)
        self._camera_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._camera_scroll_content = QWidget()
        self._camera_scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._camera_grid = QGridLayout(self._camera_scroll_content)
        self._camera_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._camera_grid.setContentsMargins(4, 4, 4, 4)
        self._camera_grid.setSpacing(8)
        for col in range(2):
            self._camera_grid.setColumnStretch(col, 1)
        self._camera_scroll.setWidget(self._camera_scroll_content)
        self._camera_scroll.viewport().installEventFilter(self)
        self.window.gridLayout_6.addWidget(self._camera_scroll)

        self._add_camera_button = QPushButton("+ Camera Toevoegen")
        self._add_camera_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._add_camera_button.clicked.connect(self._append_camera_source)
        self._source_csv = default_camera_csv
        self.set_sources(self._source_ids_for_csv(default_camera_csv))

    def _setup_camera_splitter(self) -> None:
        page_layout = self.window.page_cameras.layout()
        if page_layout is None or getattr(self.window, "_camera_splitter", None) is not None:
            return

        page_layout.removeWidget(self.window.frame)
        page_layout.removeWidget(self.window.frame_cam)

        splitter = QSplitter(Qt.Orientation.Vertical, self.window.page_cameras)
        splitter.setObjectName("splitter_camera_page")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.window.frame)
        splitter.addWidget(self.window.frame_cam)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 650])
        page_layout.addWidget(splitter, stretch=1)
        self.window._camera_splitter = splitter

    def _setup_results_page(self) -> None:
        self._intrinsics_text = self._plain_text_in_frame(self.window.frame_res_intrinsic_results)
        self._extrinsics_text = self._plain_text_in_frame(self.window.frame_res_extrinsics_results)
        self._frames_text = self._plain_text_in_frame(self.window.frame_res_aantal_frames)
        self._camera_info_text = self._plain_text_in_frame(self.window.frame_res_camera_info)
        self._error_text = self._plain_text_in_frame(self.window.frame_res_error)
        for text in [
            self._intrinsics_text,
            self._extrinsics_text,
            self._frames_text,
            self._camera_info_text,
            self._error_text,
        ]:
            text.setMinimumHeight(96)

        existing_preview = self.window.frame_res_preview_tmol.findChild(QPlainTextEdit)
        self._tmol_preview = existing_preview or QPlainTextEdit()
        self._tmol_preview.setReadOnly(True)
        self._tmol_preview.setPlainText("No export preview available yet.")
        if existing_preview is None:
            preview_layout = self.window.frame_res_preview_tmol.layout()
            if preview_layout is None:
                preview_layout = QVBoxLayout(self.window.frame_res_preview_tmol)
                preview_layout.setContentsMargins(4, 4, 4, 4)
            preview_layout.addWidget(self._tmol_preview)

        self.window.btn_res_show_tmol.clicked.connect(self._preview_toml)
        self.window.pushButton.clicked.connect(lambda: self.window.stackedWidget_2.setCurrentIndex(0))
        self.window.export_toml.clicked.connect(self._export_toml_file)

    def _setup_directory_page(self) -> None:
        layout = QVBoxLayout(self.window.frame_directory)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self._directory_up_button = QPushButton("Up")
        self._directory_down_button = QPushButton("Down")
        self._directory_path = QLineEdit(str(self._project_root))
        self._directory_path.setReadOnly(True)
        self._directory_refresh_button = QPushButton("Refresh")
        self._directory_browse_button = QPushButton("Browse...")
        toolbar.addWidget(self._directory_up_button)
        toolbar.addWidget(self._directory_down_button)
        toolbar.addWidget(QLabel("Startpad:"))
        toolbar.addWidget(self._directory_path, stretch=1)
        toolbar.addWidget(self._directory_refresh_button)
        toolbar.addWidget(self._directory_browse_button)

        self._directory_tree = QTreeWidget()
        self._directory_tree.setHeaderLabels(["Naam", "Type", "Gewijzigd"])
        self._directory_tree.setColumnCount(3)
        self._directory_tree.itemExpanded.connect(self._on_directory_item_expanded)
        self._directory_tree.itemDoubleClicked.connect(lambda item, _column: self._go_down_directory(item))

        layout.addLayout(toolbar)
        layout.addWidget(self._directory_tree)

        self._directory_up_button.clicked.connect(self._go_up_directory)
        self._directory_down_button.clicked.connect(self._go_down_directory)
        self._directory_refresh_button.clicked.connect(lambda: self.load_root_directory(self._project_root))
        self._directory_browse_button.clicked.connect(self._browse_directory)
        self.load_root_directory(self._project_root)

    def _setup_diagnostics_page(self) -> None:
        for widget in [
            self.window.text_diag_current_fps,
            self.window.text_diag_dropped_frames,
            self.window.text_diag_used_cams,
            self.window.text_diag_Intrinsics_time,
            self.window.text_diag_extrinsics_time,
            self.window.text_diag_total_time,
        ]:
            widget.setReadOnly(True)
        self.window.text_diag_current_fps.setPlainText(str(self.window.spin_cap_fps.value()))
        self.window.text_diag_dropped_frames.setPlainText("0")
        self.window.text_diag_used_cams.setPlainText("0")
        self.window.text_diag_Intrinsics_time.setPlainText("-")
        self.window.text_diag_extrinsics_time.setPlainText("-")
        self.window.text_diag_total_time.setPlainText("-")

    def _setup_advanced_page(self, default_camera_csv: str, default_fps: float) -> None:
        self.window.doubleSpinBox.setRange(1.0, 500.0)
        self.window.doubleSpinBox.setDecimals(2)
        self.window.doubleSpinBox.setSingleStep(0.5)
        self.window.doubleSpinBox.setValue(24.0)

        self._sources_input = QLineEdit(default_camera_csv)
        self._preview_fps_spin = self._double_spin(1.0, 120.0, min(default_fps, 30.0), 1.0, 1)
        self._detect_hz_spin = self._double_spin(0.5, 20.0, 4.0, 0.5, 1)
        self._capture_resolution_combo = QComboBox()
        self._capture_resolution_combo.addItem("Auto", (0, 0))
        self._capture_resolution_combo.addItem("640 x 480", (640, 480))
        self._capture_resolution_combo.addItem("960 x 540", (960, 540))
        self._capture_resolution_combo.addItem("1280 x 720", (1280, 720))
        self._capture_resolution_combo.addItem("1920 x 1080", (1920, 1080))
        self._capture_resolution_combo.setCurrentIndex(3)
        self._preview_resolution_combo = QComboBox()
        self._preview_resolution_combo.addItem("Auto", (0, 0))
        self._preview_resolution_combo.addItem("640 x 480", (640, 480))
        self._preview_resolution_combo.addItem("960 x 540", (960, 540))
        self._preview_resolution_combo.addItem("1280 x 720", (1280, 720))
        self._preview_resolution_combo.addItem("1920 x 1080", (1920, 1080))
        self._preview_resolution_combo.setCurrentIndex(3)
        self._camera_exposure_spin = self._spin(-13, 0, -1)
        self._camera_exposure_spin.setSpecialValueText("Auto")
        self._camera_fourcc_combo = QComboBox()
        self._camera_fourcc_combo.addItem("MJPG", "MJPG")
        self._camera_fourcc_combo.addItem("YUY2", "YUY2")
        self._camera_auto_exposure_combo = self._camera_mode_combo(
            [("Auto", 0.75), ("Manual", 0.25)]
        )
        self._camera_auto_wb_combo = self._camera_mode_combo([("On", 1.0), ("Off", 0.0)])
        self._camera_autofocus_combo = self._camera_mode_combo([("On", 1.0), ("Off", 0.0)])
        self._camera_control_spins: dict[str, QDoubleSpinBox] = {
            "brightness": self._camera_control_spin(),
            "contrast": self._camera_control_spin(),
            "saturation": self._camera_control_spin(),
            "hue": self._camera_control_spin(),
            "gain": self._camera_control_spin(),
            "sharpness": self._camera_control_spin(),
            "gamma": self._camera_control_spin(),
            "temperature": self._camera_control_spin(maximum=20000.0),
            "backlight": self._camera_control_spin(),
            "wb_temperature": self._camera_control_spin(maximum=20000.0),
            "focus": self._camera_control_spin(maximum=20000.0),
            "zoom": self._camera_control_spin(maximum=20000.0),
            "pan": self._camera_control_spin(),
            "tilt": self._camera_control_spin(),
            "roll": self._camera_control_spin(),
            "iris": self._camera_control_spin(maximum=20000.0),
            "trigger": self._camera_control_spin(),
            "trigger_delay": self._camera_control_spin(),
            "aperture": self._camera_control_spin(maximum=20000.0),
            "exposure_program": self._camera_control_spin(),
        }
        self._probe_max_spin = self._spin(1, 20, 10)

        self._chess_cols_spin = self._spin(2, 30, 9)
        self._chess_rows_spin = self._spin(2, 30, 6)
        self._charuco_x_spin = self._spin(2, 30, 5)
        self._charuco_y_spin = self._spin(2, 30, 3)
        self._charuco_square_spin = self._double_spin(1.0, 500.0, 77.0, 0.5, 2)
        self._charuco_marker_spin = self._double_spin(1.0, 500.0, 61.0, 0.5, 2)
        self._charuco_square_spin.setSuffix(" mm")
        self._charuco_marker_spin.setSuffix(" mm")

        self._workflow_combo = QComboBox()
        self._workflow_combo.addItem("Intrinsics", "intrinsics")
        self._workflow_combo.addItem("Sync / Extrinsics", "sync_extrinsics")
        self._overlay_checkbox = QCheckBox("Show Detection Overlay")
        self._overlay_checkbox.setChecked(True)
        self._mirror_checkbox = QCheckBox("Mirror Preview")
        self._auto_capture_checkbox = QCheckBox("Auto Capture Valid Samples")
        self._auto_cooldown_spin = self._double_spin(0.1, 10.0, 0.33, 0.01, 2)
        self._intrinsics_max_spin = self._spin(0, 1000, 60)
        self._intrinsics_max_spin.setSpecialValueText("No limit")
        self._intrinsics_max_spin.setSuffix(" samples")
        self._extrinsics_max_spin = self._spin(0, 1000, 30)
        self._extrinsics_max_spin.setSpecialValueText("No limit")
        self._extrinsics_max_spin.setSuffix(" sync sets")
        self._intrinsics_quality_spin = self._double_spin(0.0, 1.0, 0.25, 0.05, 2)
        self._intrinsics_coverage_spin = self._double_spin(0.0, 25.0, 1.8, 0.2, 1)
        self._intrinsics_coverage_spin.setSuffix(" %")
        self._extrinsics_quality_spin = self._double_spin(0.0, 1.0, 0.15, 0.05, 2)
        self._extrinsics_coverage_spin = self._double_spin(0.0, 25.0, 1.0, 0.2, 1)
        self._extrinsics_coverage_spin.setSuffix(" %")
        self._grid_cols_spin = self._spin(1, 20, 6)
        self._grid_rows_spin = self._spin(1, 20, 4)

        self._auto_status = QLabel("Auto capture off.")
        self._probe_status = QLabel("Camera scan: not run yet.")
        self._probe_status.setWordWrap(True)
        self._feedback = QLabel("Ready.")
        self._feedback.setWordWrap(True)
        self._warnings = QPlainTextEdit()
        self._warnings.setReadOnly(True)
        self._warnings.setMinimumHeight(92)

        self._start_live_button = QPushButton("Start Live")
        self._stop_live_button = QPushButton("Stop Live")
        self._probe_button = QPushButton("Detect Cameras")
        self._capture_button = QPushButton("Capture Intrinsics Sample(s)")
        self._capture_sync_button = QPushButton("Capture Sync Set(s)")
        self._start_auto_button = QPushButton("Start Auto Capture")
        self._apply_live_settings_button = QPushButton("Apply Live Source Settings")
        self._apply_camera_controls_button = QPushButton("Apply Camera Image Controls")
        self._reset_camera_controls_button = QPushButton("Reset to Defaults")
        self._apply_chessboard_button = QPushButton("Apply Chessboard Settings")
        self._apply_charuco_button = QPushButton("Apply ChArUco Settings")
        self._apply_workflow_button = QPushButton("Apply Workflow Settings")
        self._save_profile_button = QPushButton("Save Profile")
        self._load_profile_button = QPushButton("Load Profile")
        self._reset_samples_button = QPushButton("Reset Samples")

        advanced_root = QWidget()
        advanced_layout = QVBoxLayout(advanced_root)
        advanced_layout.setContentsMargins(4, 4, 4, 4)
        advanced_layout.setSpacing(8)
        advanced_layout.addWidget(self._section("Live source settings", self._live_settings_form()))
        advanced_layout.addWidget(self._section("Camera image controls", self._camera_controls_form()))
        advanced_layout.addWidget(self._section("Chessboard settings", self._chessboard_settings_form()))
        advanced_layout.addWidget(self._section("ChArUco settings", self._charuco_settings_form()))
        advanced_layout.addWidget(self._section("Workflow and thresholds", self._workflow_settings_form()))
        advanced_layout.addWidget(self._section("Advanced actions", self._advanced_actions_widget()))
        advanced_layout.addWidget(self._section("Status and warnings", self._status_widget()))
        advanced_layout.addStretch(1)
        self._prepare_settings_container(advanced_root)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(advanced_root)
        page_layout = self.window.page_advanced_settings.layout()
        if page_layout is None:
            page_layout = QVBoxLayout(self.window.page_advanced_settings)
            page_layout.setContentsMargins(0, 0, 0, 0)
        else:
            self._clear_layout(page_layout)
        page_layout.addWidget(scroll)

        self._connect_advanced_controls()
        self._set_mode_button_state(self.current_workflow_mode())
        for tile in self._tiles.values():
            tile.set_progress(0, self.active_progress_maximum(), self.active_progress_label(0))

    def _connect_designed_actions(self) -> None:
        self.window.btn_newproject.clicked.connect(self.new_project_requested)
        self.window.btn_loadproject.clicked.connect(self._browse_directory)
        self.window.actionNew_project.triggered.connect(self.new_project_requested)
        self.window.actionOpen_project.triggered.connect(self._browse_directory)
        self.window.actionQuit.triggered.connect(self.window.close)
        self.window.actionOpen_documentation.triggered.connect(self._open_documentation)

        self.window.btn_cap_intrinsics_start.clicked.connect(self._activate_intrinsics_mode)
        self.window.btn_cap_extrinsics_start.clicked.connect(self._activate_extrinsics_mode)
        self.window.btn_cap_calculate_intrinsics.clicked.connect(self.solve_requested)
        self.window.btn_cap_calculate_extrinsics.clicked.connect(self._emit_solve_extrinsics)
        self.window.btn_cap_reset_calibration.clicked.connect(self._emit_reset)
        self.window.combo_cap_pattern.currentIndexChanged.connect(self._emit_pattern_changed)
        self.window.spin_cap_fps.valueChanged.connect(self._emit_runtime_tuning_changed)

    def _connect_advanced_controls(self) -> None:
        self._start_live_button.clicked.connect(self._emit_start_live)
        self._stop_live_button.clicked.connect(self.stop_live_requested)
        self._probe_button.clicked.connect(lambda: self.probe_cameras_requested.emit(int(self._probe_max_spin.value())))
        self._capture_button.clicked.connect(self._capture_intrinsics_sample)
        self._capture_sync_button.clicked.connect(self._capture_sync_sample)
        self._start_auto_button.clicked.connect(self.auto_capture_start_requested)
        self._apply_live_settings_button.clicked.connect(self._apply_live_settings)
        self._apply_camera_controls_button.clicked.connect(self._apply_camera_controls)
        self._reset_camera_controls_button.clicked.connect(self._reset_camera_image_controls)
        self._apply_chessboard_button.clicked.connect(lambda: self._apply_board_settings("Chessboard settings applied."))
        self._apply_charuco_button.clicked.connect(lambda: self._apply_board_settings("ChArUco settings applied."))
        self._apply_workflow_button.clicked.connect(self._apply_workflow_settings)
        self._save_profile_button.clicked.connect(self.save_profile_requested)
        self._load_profile_button.clicked.connect(self.load_profile_requested)
        self._reset_samples_button.clicked.connect(self._emit_reset)
        self.window.doubleSpinBox.valueChanged.connect(lambda _value: None)

    def _plain_text_in_frame(self, frame: QFrame) -> QPlainTextEdit:
        existing = frame.findChild(QPlainTextEdit)
        if existing is not None:
            existing.setReadOnly(True)
            existing.setPlainText("-")
            return existing
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText("-")
        layout = frame.layout()
        if layout is None:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(text)
        return text

    def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _double_spin(
        self,
        minimum: float,
        maximum: float,
        value: float,
        step: float,
        decimals: int,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def _camera_mode_combo(self, choices: list[tuple[str, float]]) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Auto", None)
        for label, value in choices:
            combo.addItem(label, value)
        return combo

    def _camera_control_spin(
        self,
        minimum: float = -10000.0,
        maximum: float = 10000.0,
        step: float = 1.0,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(step)
        spin.setValue(minimum)
        spin.setSpecialValueText("Auto")
        return spin

    def _section(self, title: str, content: QWidget) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        header = QLabel(title)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        layout.addWidget(content)
        return frame

    def _live_settings_form(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("Sources (CSV)", self._sources_input)
        form.addRow("Capture FPS", QLabel("Use the FPS field on the Camera page"))
        form.addRow("Capture Resolution", self._capture_resolution_combo)
        form.addRow("Camera Exposure", self._camera_exposure_spin)
        form.addRow("Pixel Format", self._camera_fourcc_combo)
        form.addRow("Preview FPS", self._preview_fps_spin)
        form.addRow("Preview Resolution", self._preview_resolution_combo)
        form.addRow("Calibration Detect Hz", self._detect_hz_spin)
        form.addRow("Probe Max Index", self._probe_max_spin)
        form.addRow("", self._probe_status)
        form.addRow("", self._apply_live_settings_button)
        return form_widget

    def _camera_controls_form(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        note = QLabel("Auto = laat de camera-driver de waarde kiezen of laat de property ongemoeid.")
        note.setWordWrap(True)
        form.addRow("", note)
        form.addRow("Auto Exposure Mode", self._camera_auto_exposure_combo)
        form.addRow("Brightness", self._camera_control_spins["brightness"])
        form.addRow("Contrast", self._camera_control_spins["contrast"])
        form.addRow("Saturation", self._camera_control_spins["saturation"])
        form.addRow("Hue", self._camera_control_spins["hue"])
        form.addRow("Gain", self._camera_control_spins["gain"])
        form.addRow("Sharpness", self._camera_control_spins["sharpness"])
        form.addRow("Gamma", self._camera_control_spins["gamma"])
        form.addRow("Temperature", self._camera_control_spins["temperature"])
        form.addRow("Backlight", self._camera_control_spins["backlight"])
        form.addRow("Auto White Balance", self._camera_auto_wb_combo)
        form.addRow("White Balance Temperature", self._camera_control_spins["wb_temperature"])
        form.addRow("Autofocus", self._camera_autofocus_combo)
        form.addRow("Focus", self._camera_control_spins["focus"])
        form.addRow("Zoom", self._camera_control_spins["zoom"])
        form.addRow("Pan", self._camera_control_spins["pan"])
        form.addRow("Tilt", self._camera_control_spins["tilt"])
        form.addRow("Roll", self._camera_control_spins["roll"])
        form.addRow("Iris", self._camera_control_spins["iris"])
        form.addRow("Trigger", self._camera_control_spins["trigger"])
        form.addRow("Trigger Delay", self._camera_control_spins["trigger_delay"])
        form.addRow("Aperture", self._camera_control_spins["aperture"])
        form.addRow("Exposure Program", self._camera_control_spins["exposure_program"])
        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self._reset_camera_controls_button)
        actions_layout.addWidget(self._apply_camera_controls_button)
        form.addRow("", actions)
        return form_widget

    def _chessboard_settings_form(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("Columns", self._chess_cols_spin)
        form.addRow("Rows", self._chess_rows_spin)
        form.addRow("Square", self.window.doubleSpinBox)
        form.addRow("", self._apply_chessboard_button)
        return form_widget

    def _charuco_settings_form(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("ChArUco Squares X", self._charuco_x_spin)
        form.addRow("ChArUco Squares Y", self._charuco_y_spin)
        form.addRow("ChArUco Square", self._charuco_square_spin)
        form.addRow("ChArUco Marker", self._charuco_marker_spin)
        form.addRow("", self._apply_charuco_button)
        return form_widget

    def _workflow_settings_form(self) -> QWidget:
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.addRow("Workflow", self._workflow_combo)
        form.addRow("Pattern", QLabel("Use the Pattern field on the Camera page"))
        form.addRow("Overlay", self._overlay_checkbox)
        form.addRow("Mirror", self._mirror_checkbox)
        form.addRow("Auto Capture", self._auto_capture_checkbox)
        form.addRow("Cooldown", self._auto_cooldown_spin)
        form.addRow("Intrinsics Max Samples", self._intrinsics_max_spin)
        form.addRow("Extrinsics Max Sync Sets", self._extrinsics_max_spin)
        form.addRow("Intrinsics Min Quality", self._intrinsics_quality_spin)
        form.addRow("Intrinsics Min Coverage", self._intrinsics_coverage_spin)
        form.addRow("Extrinsics Min Quality", self._extrinsics_quality_spin)
        form.addRow("Extrinsics Min Coverage", self._extrinsics_coverage_spin)
        grid = QWidget()
        grid_layout = QHBoxLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._grid_cols_spin)
        grid_layout.addWidget(QLabel("x"))
        grid_layout.addWidget(self._grid_rows_spin)
        grid_layout.addStretch(1)
        form.addRow("Spatial Grid", grid)
        form.addRow("", self._apply_workflow_button)
        return form_widget

    def _advanced_actions_widget(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        buttons = [
            self._probe_button,
            self._start_live_button,
            self._stop_live_button,
            self._capture_button,
            self._capture_sync_button,
            self._start_auto_button,
            self._save_profile_button,
            self._load_profile_button,
            self._reset_samples_button,
        ]
        for index, button in enumerate(buttons):
            button.setMinimumHeight(30)
            layout.addWidget(button, index // 2, index % 2)
        return widget

    def _status_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._feedback)
        layout.addWidget(self._auto_status)
        layout.addWidget(self._warnings)
        return widget

    def switch_page(self, index: int) -> None:
        self.window.stackedWidget.setCurrentIndex(index)
        active_style = "background-color: #0078D4; color: white; font-weight: bold; border: 1px solid #005A9E;"
        normal_style = "background-color: #2D2D2D; color: white; border: 1px solid #444;"
        for button_index, button in enumerate(self._nav_buttons):
            button.setStyleSheet(active_style if button_index == index else normal_style)

    def _handle_console_input(self) -> None:
        text = self.window.lineedit_console_input.text().strip()
        self.window.lineedit_console_input.clear()
        if not text:
            return
        self._log(f"> {text}", with_timestamp=False)
        command = text.lower()
        if command in {"help", "?", "commands"}:
            self._show_console_help()
        elif command == "home":
            self.switch_page(0)
        elif command in {"cameras", "camera", "kalibratie"}:
            self.switch_page(1)
        elif command == "results":
            self.switch_page(2)
        elif command == "directory":
            self.switch_page(3)
        elif command == "diagnostics":
            self.switch_page(4)
        elif command in {"settings", "advanced"}:
            self.switch_page(5)
        elif command == "start live":
            self._emit_start_live()
        elif command == "stop live":
            self.stop_live_requested.emit()
        elif command.startswith("capture intrinsics"):
            self._capture_intrinsics_sample()
        elif command.startswith("capture extrinsics"):
            self._capture_sync_sample()
        elif command == "solve intrinsics":
            self.solve_requested.emit()
        elif command == "solve extrinsics":
            self._emit_solve_extrinsics()
        else:
            self._log(f"Unknown command: {text}")

    def _log(self, text: str, with_timestamp: bool = True) -> None:
        prefix = datetime.now().strftime("[%H:%M:%S] ") if with_timestamp else ""
        self.window.plaintextedit_console.appendPlainText(f"{prefix}{text}")
        scrollbar = self.window.plaintextedit_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_console_help(self) -> None:
        self._log(
            "Commands: help | home | cameras | results | directory | diagnostics | settings | "
            "start live | stop live | capture intrinsics | capture extrinsics | solve intrinsics | solve extrinsics",
            with_timestamp=False,
        )

    def _open_documentation(self) -> None:
        webbrowser.open("https://github.com/MaxUntersalmberger/PhysioMotionTracker")
        self._log("Documentation opened in web browser.")

    def _apply_live_settings(self) -> None:
        self._sync_source_input_preview()
        self._emit_runtime_tuning_changed()
        self.show_feedback("Live source settings applied.", success=True)

    def _apply_camera_controls(self, message: str = "Camera image controls applied.") -> None:
        self._emit_runtime_tuning_changed()
        self.show_feedback(message, success=True)

    def _reset_camera_image_controls(self) -> None:
        defaults = RuntimeTuning()
        self._camera_exposure_spin.setValue(defaults.camera_exposure)
        fourcc_index = self._camera_fourcc_combo.findData(defaults.camera_fourcc)
        self._camera_fourcc_combo.setCurrentIndex(fourcc_index if fourcc_index >= 0 else 0)

        for combo in [
            self._camera_auto_exposure_combo,
            self._camera_auto_wb_combo,
            self._camera_autofocus_combo,
        ]:
            combo.setCurrentIndex(0)

        for spin in self._camera_control_spins.values():
            spin.setValue(spin.minimum())

        self._apply_camera_controls("Camera image controls reset to defaults.")

    def _apply_workflow_settings(self) -> None:
        self._emit_runtime_tuning_changed()
        self._emit_acceptance_thresholds_changed()
        self._emit_spatial_grid_changed()
        self._emit_workflow_mode_changed()
        self.show_feedback("Workflow settings applied.", success=True)

    def _apply_board_settings(self, message: str) -> None:
        self.board_settings_applied.emit(self.board_settings())
        self.show_feedback(message, success=True)

    def _current_toml_bundle(self) -> CalibrationBundle | None:
        bundle = self._last_results_bundle or getattr(self.window, "_current_calibration_bundle", None)
        if bundle is not None:
            return bundle
        manager = getattr(self.window, "_calibration_manager", None)
        if manager is None:
            return None
        return manager.last_solution()

    def _preview_toml(self) -> None:
        bundle = self._current_toml_bundle()
        if bundle is None:
            self._tmol_preview.setPlainText("Nog geen kalibratie om te exporteren. Solve eerst.")
        else:
            self._tmol_preview.setPlainText(calibration_bundle_to_toml(bundle))
        self.window.stackedWidget_2.setCurrentIndex(1)

    def _export_toml_file(self) -> None:
        bundle = self._current_toml_bundle()
        if bundle is None:
            QMessageBox.information(
                self.window,
                "Export",
                "Er is nog geen kalibratie om te exporteren. Solve eerst.",
            )
            return

        default_path = self.window._config.calibration_dir / "calibration.toml"
        selected, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export calibration as TOML",
            str(default_path),
            "TOML files (*.toml);;All files (*.*)",
        )
        if not selected:
            return

        toml_text = calibration_bundle_to_toml(bundle)
        try:
            Path(selected).write_text(toml_text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self.window, "Export mislukt", str(exc))
            return

        self._tmol_preview.setPlainText(toml_text)
        self.show_feedback(f"TOML geexporteerd naar {selected}", success=True)

    def _emit_start_live(self) -> None:
        try:
            sources = self.current_sources()
        except ValueError as exc:
            self.ui_message.emit(str(exc))
            return
        self.start_live_requested.emit(sources, self.target_fps())

    def _set_mode_button_state(self, mode: str) -> None:
        intrinsics_active = mode == "intrinsics"
        extrinsics_active = mode == "sync_extrinsics"
        active_style = "background-color: #0078d7; color: white; font-weight: bold;"
        for button, active in (
            (self.window.btn_cap_intrinsics_start, intrinsics_active),
            (self.window.btn_cap_extrinsics_start, extrinsics_active),
        ):
            button.blockSignals(True)
            button.setChecked(active)
            button.setStyleSheet(active_style if active else "")
            button.blockSignals(False)
        self.window.btn_cap_intrinsics_start.setText("Intrinsics Mode")
        self.window.btn_cap_extrinsics_start.setText("Extrinsics Mode")

    def _activate_intrinsics_mode(self, _checked: bool = True) -> None:
        self.set_workflow_mode("intrinsics")
        self.workflow_mode_changed.emit("intrinsics")

    def _activate_extrinsics_mode(self, _checked: bool = True) -> None:
        self.set_workflow_mode("sync_extrinsics")
        self.workflow_mode_changed.emit("sync_extrinsics")

    def _emit_solve_extrinsics(self) -> None:
        self.set_workflow_mode("sync_extrinsics")
        self.workflow_mode_changed.emit("sync_extrinsics")
        self.solve_extrinsics_requested.emit()

    def _emit_reset(self) -> None:
        self._sync_progress_count = 0
        self._set_mode_button_state(self.current_workflow_mode())
        for tile in self._tiles.values():
            tile.set_progress(0, self.active_progress_maximum(), self.active_progress_label(0))
        self.reset_requested.emit()

    def _capture_intrinsics_sample(self) -> None:
        self.set_workflow_mode("intrinsics")
        self.workflow_mode_changed.emit("intrinsics")
        self.capture_requested.emit()

    def _capture_sync_sample(self) -> None:
        self.set_workflow_mode("sync_extrinsics")
        self.workflow_mode_changed.emit("sync_extrinsics")
        self.capture_requested.emit()

    def _emit_pattern_changed(self) -> None:
        self.pattern_changed.emit(self.current_pattern())

    def _emit_workflow_mode_changed(self) -> None:
        mode = self.current_workflow_mode()
        self.set_workflow_mode(mode)
        self.workflow_mode_changed.emit(mode)

    def _emit_acceptance_thresholds_changed(self) -> None:
        quality, coverage = self.acceptance_threshold_values()
        self.acceptance_thresholds_changed.emit(quality, coverage)

    def _emit_spatial_grid_changed(self) -> None:
        cols, rows = self.spatial_grid_values()
        self.spatial_grid_changed.emit(cols, rows)

    def _emit_runtime_tuning_changed(self) -> None:
        self.runtime_tuning_changed.emit(self.runtime_tuning())
        self.window.text_diag_current_fps.setPlainText(str(self.window.spin_cap_fps.value()))

    def _sync_source_input_preview(self) -> None:
        self._source_csv = self._sources_input.text().strip()
        self.set_sources(self._source_ids_for_csv(self._source_csv))
        self._emit_sources_changed()

    def _append_camera_source(self) -> None:
        tokens = [token.strip() for token in self._sources_input.text().split(",") if token.strip()]
        numeric_tokens = {int(token) for token in tokens if token.isdigit()}
        next_index = 0
        while next_index in numeric_tokens:
            next_index += 1
        if len(tokens) >= 4:
            self.ui_message.emit("Use up to 4 sources for calibration.")
            return
        tokens.append(str(next_index))
        self._sources_input.setText(",".join(tokens))
        self._sync_source_input_preview()

    def _remove_source(self, source_id: str) -> None:
        try:
            index = self._source_order.index(source_id)
        except ValueError:
            return
        tile = self._tiles.get(source_id)
        if tile is not None:
            tile.close_popout()
        tokens = [token.strip() for token in self._sources_input.text().split(",") if token.strip()]
        if 0 <= index < len(tokens):
            del tokens[index]
        self._sources_input.setText(",".join(tokens))
        self._sync_source_input_preview()

    def _source_ids_for_csv(self, csv: str) -> list[str]:
        tokens = [token.strip() for token in csv.split(",") if token.strip()]
        return [self._source_id_for_token(token, index) for index, token in enumerate(tokens[:4])]

    def _source_id_for_token(self, token: str, index: int) -> str:
        return f"cam{int(token)}" if token.isdigit() else f"cam{index}"

    def _emit_sources_changed(self) -> None:
        try:
            sources = self.current_sources()
        except ValueError:
            sources = []
        self.sources_changed.emit(sources)

    def current_sources(self) -> list[CameraSourceConfig]:
        raw = self._sources_input.text().strip()
        if not raw:
            raise ValueError("Camera CSV is empty. Provide at least one source.")
        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        if not tokens:
            raise ValueError("No valid camera sources parsed.")
        if len(tokens) > 4:
            raise ValueError("Use up to 4 sources for calibration.")
        sources: list[CameraSourceConfig] = []
        for index, token in enumerate(tokens):
            source_id = self._source_id_for_token(token, index)
            label = self._camera_names.get(source_id)
            if token.isdigit():
                sources.append(
                    CameraSourceConfig(
                        source_id=source_id,
                        kind="webcam",
                        uri=int(token),
                        label=label or f"Webcam {token}",
                    )
                )
            else:
                sources.append(
                    CameraSourceConfig(
                        source_id=source_id,
                        kind="video",
                        uri=token,
                        label=label or token,
                    )
                )
        return sources

    def target_fps(self) -> float:
        return float(self.window.spin_cap_fps.value())

    def _camera_controls(self) -> dict[str, float]:
        controls: dict[str, float] = {}
        for key, combo in (
            ("auto_exposure", self._camera_auto_exposure_combo),
            ("auto_wb", self._camera_auto_wb_combo),
            ("autofocus", self._camera_autofocus_combo),
        ):
            value = combo.currentData()
            if value is not None:
                controls[key] = float(value)
        for key, spin in self._camera_control_spins.items():
            if float(spin.value()) > float(spin.minimum()):
                controls[key] = float(spin.value())
        return controls

    def runtime_tuning(self) -> RuntimeTuning:
        capture_size = self._capture_resolution_combo.currentData()
        if not isinstance(capture_size, tuple) or len(capture_size) != 2:
            capture_size = (0, 0)
        preview_size = self._preview_resolution_combo.currentData()
        if not isinstance(preview_size, tuple) or len(preview_size) != 2:
            preview_size = (0, 0)
        return RuntimeTuning(
            capture_fps=float(self.window.spin_cap_fps.value()),
            capture_width=int(capture_size[0]),
            capture_height=int(capture_size[1]),
            preview_fps=float(self._preview_fps_spin.value()),
            preview_max_width=int(preview_size[0]),
            preview_max_height=int(preview_size[1]),
            calibration_detection_hz=float(self._detect_hz_spin.value()),
            camera_exposure=int(self._camera_exposure_spin.value()),
            camera_fourcc=str(self._camera_fourcc_combo.currentData() or "MJPG"),
            camera_controls=self._camera_controls(),
            overlays_enabled=self._overlay_checkbox.isChecked(),
            detection_capture_enabled=False,
            detection_reconstruction_enabled=False,
            detection_analysis_enabled=False,
        )

    def set_sources(self, source_ids: list[str]) -> None:
        source_ids = source_ids[:4]
        existing = set(self._tiles)
        requested = set(source_ids)

        for source_id in sorted(existing - requested):
            tile = self._tiles.pop(source_id)
            self._camera_grid.removeWidget(tile)
            tile.close_popout()
            tile.deleteLater()

        for source_id in source_ids:
            if source_id in self._tiles:
                continue
            tile = DesignedPreviewTile(source_id)
            tile.set_display_name(self._camera_names.get(source_id, source_id))
            tile.undistort_toggled.connect(self.undistort_toggled)
            tile.auto_capture_toggled.connect(self._on_tile_auto_capture_toggled)
            tile.preview_options_changed.connect(self.preview_options_changed)
            tile.remove_requested.connect(self._remove_source)
            tile.name_changed.connect(self._on_camera_name_changed)
            if hasattr(self, "_intrinsics_max_spin"):
                tile.set_progress(0, self.active_progress_maximum(), self.active_progress_label(0))
            self._tiles[source_id] = tile

        self._source_order = list(source_ids)
        self._rebuild_camera_grid()

    def _rebuild_camera_grid(self) -> None:
        while self._camera_grid.count():
            item = self._camera_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        columns = self._camera_grid_columns()
        self._last_camera_grid_columns = columns
        for col in range(3):
            self._camera_grid.setColumnStretch(col, 1 if col < columns else 0)

        for index, source_id in enumerate(self._source_order):
            self._camera_grid.addWidget(self._tiles[source_id], index // columns, index % columns)
        self._camera_grid.addWidget(
            self._add_camera_button,
            len(self._source_order) // columns,
            len(self._source_order) % columns,
        )

    def _camera_grid_columns(self) -> int:
        viewport_width = self._camera_scroll.viewport().width() if hasattr(self, "_camera_scroll") else 0
        minimum_tile_width = 520
        minimum_gap = self._camera_grid.spacing()
        if viewport_width >= (minimum_tile_width * 2 + minimum_gap):
            return 2
        return 1

    def _rebuild_camera_grid_if_columns_changed(self) -> None:
        if not hasattr(self, "_camera_grid"):
            return
        columns = self._camera_grid_columns()
        if columns != self._last_camera_grid_columns:
            self._rebuild_camera_grid()

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
            count = int(sample_counts.get(source_id, 0))
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
            if self.current_workflow_mode() == "sync_extrinsics":
                progress_current = self._sync_progress_count
                progress_maximum = self.extrinsics_max_sync_sets()
                progress_label = self.active_progress_label(progress_current)
            else:
                progress_current = count
                progress_maximum = self.intrinsics_max_samples()
                progress_label = self.active_progress_label(progress_current)
            tile.set_frame(frame_bgr, status, progress_current, progress_maximum, progress_label)

    def set_sync_progress_count(self, count: int) -> None:
        self._sync_progress_count = max(0, int(count))

    def _display_name(self, source_id: str) -> str:
        tile = self._tiles.get(source_id)
        if tile is not None:
            return tile.display_name()
        return self._camera_names.get(source_id, source_id)

    def _on_camera_name_changed(self, source_id: str, name: str) -> None:
        clean_name = name.strip() or source_id
        self._camera_names[source_id] = clean_name
        if hasattr(self.window._config, "camera_labels"):
            self.window._config.camera_labels = dict(self._camera_names)
            try:
                self.window._config.save()
            except Exception:  # noqa: BLE001
                pass
        self._log(f"Camera renamed: {source_id} -> {clean_name}")

    def _on_tile_auto_capture_toggled(self, enabled: bool) -> None:
        self.set_auto_capture_enabled(enabled)
        if enabled:
            self.auto_capture_start_requested.emit()

    def update_camera_status_table(
        self,
        source_ids: list[str],
        sample_counts: dict[str, int],
        sample_breakdown: dict[str, dict[str, int]],
        bundle: CalibrationBundle | None,
        live_detection: dict[str, ChessboardDetectionResult] | None = None,
    ) -> None:
        self._last_results_bundle = bundle
        intrinsics: list[str] = []
        extrinsics: list[str] = []
        frames: list[str] = []
        camera_info: list[str] = []
        errors: list[str] = []

        for source_id in source_ids:
            display_name = self._display_name(source_id)
            camera = bundle.cameras.get(source_id) if bundle else None
            breakdown = sample_breakdown.get(source_id, {})
            count = int(sample_counts.get(source_id, 0))
            total = int(breakdown.get("total", count))
            status = self._camera_status_text(camera)
            reproj = f"{camera.reprojection_error:.4f}px" if camera and camera.reprojection_error is not None else "-"
            intrinsics.append(f"{display_name} ({source_id}): {status}, samples {count}/{total}, reprojection {reproj}")
            if camera and camera.rotation is not None and camera.translation is not None:
                extrinsics.append(f"{display_name} ({source_id}): solved")
            else:
                extrinsics.append(f"{display_name} ({source_id}): unsolved")
            frames.append(f"{display_name} ({source_id}): intrinsics={count}, sync={int(breakdown.get('synchronized', 0))}")
            image_size = f"{camera.image_size[0]}x{camera.image_size[1]}" if camera and camera.image_size else "-"
            camera_info.append(f"{display_name} ({source_id}): image={image_size}")
            diagnostics = []
            if camera:
                diagnostics.extend(camera.diagnostics)
            if live_detection and source_id in live_detection:
                diagnostics.extend(live_detection[source_id].diagnostics)
            if diagnostics:
                errors.append(f"{display_name} ({source_id}): " + "; ".join(dict.fromkeys(diagnostics)))

        if bundle and bundle.notes:
            errors.extend(bundle.notes[-8:])

        self._intrinsics_text.setPlainText("\n".join(intrinsics) or "-")
        self._extrinsics_text.setPlainText("\n".join(extrinsics) or "-")
        self._frames_text.setPlainText("\n".join(frames) or "-")
        self._camera_info_text.setPlainText("\n".join(camera_info) or "-")
        self._error_text.setPlainText("\n".join(dict.fromkeys(errors)) or "-")

    def _camera_status_text(self, camera: CameraCalibration | None) -> str:
        return camera.status if camera else "unsolved"

    def show_feedback(self, message: str, success: bool) -> None:
        color = "#0f7b0f" if success else "#9a6700"
        self._feedback.setStyleSheet(f"color: {color};")
        self._feedback.setText(message)
        self._log(message)

    def show_warnings(self, lines: list[str]) -> None:
        self._warnings.setPlainText("\n".join(lines))

    def set_live_status(
        self,
        live_active: bool,
        active_cameras: int,
        per_camera_fps: dict[str, float] | None = None,
    ) -> None:
        self._live_active = live_active
        self._active_cameras = active_cameras
        self.window.btn_camera_start_live.setEnabled(not live_active)
        self.window.btn_camera_stop_live.setEnabled(live_active)
        self.window.text_diag_used_cams.setPlainText(str(active_cameras))
        state = "On" if live_active else "Off"
        fps_text = ""
        if per_camera_fps:
            fps_text = " | FPS: " + ", ".join(
                f"{self._display_name(source_id)} {fps:.1f}"
                for source_id, fps in sorted(per_camera_fps.items())
            )
        self._feedback.setText(f"Live: {state} | Cameras: {active_cameras}{fps_text}")
        if not live_active:
            for button in [self.window.btn_cap_intrinsics_start, self.window.btn_cap_extrinsics_start]:
                button.blockSignals(True)
                button.setText("Intrinsics Mode" if button is self.window.btn_cap_intrinsics_start else "Extrinsics Mode")
                button.blockSignals(False)

    def set_camera_probe_running(self, running: bool) -> None:
        self._probe_button.setEnabled(not running)
        self.window.btn_camera_detect.setEnabled(not running)
        self._probe_max_spin.setEnabled(not running)
        self._probe_button.setText("Scanning..." if running else "Detect Cameras")
        self.window.btn_camera_detect.setText("Scanning..." if running else "Detect Cameras")

    def set_detected_cameras(self, cameras: list[CameraProbeResult]) -> None:
        if not cameras:
            self._probe_status.setText("Camera scan: no cameras found.")
            self._log("Camera scan: no cameras found.")
            return
        found = sorted(cameras, key=lambda camera: camera.index)
        parts = []
        for camera in found:
            resolution = f"{camera.width}x{camera.height}" if camera.width > 0 and camera.height > 0 else "unknown res"
            backend = f" ({camera.backend})" if camera.backend else ""
            parts.append(f"{camera.index}: {resolution}{backend}")
        text = "Camera scan: " + " | ".join(parts)
        self._probe_status.setText(text)
        self._log(text)
        csv = ",".join(str(camera.index) for camera in found[:4])
        if csv:
            self._sources_input.setText(csv)
            self._sync_source_input_preview()

    def set_intrinsics_solve_running(self, running: bool, message: str = "Solving intrinsics...") -> None:
        for button in [
            self.window.btn_cap_calculate_intrinsics,
            self.window.btn_cap_calculate_extrinsics,
            self._capture_button,
            self._capture_sync_button,
            self._reset_samples_button,
            self._load_profile_button,
            self._apply_live_settings_button,
            self._apply_camera_controls_button,
            self._reset_camera_controls_button,
            self._apply_chessboard_button,
            self._apply_charuco_button,
            self._apply_workflow_button,
        ]:
            button.setEnabled(not running)
        if running:
            self._feedback.setText(message)

    def current_pattern(self) -> str:
        data = self.window.combo_cap_pattern.currentData()
        return str(data if data is not None else "chessboard").lower().strip()

    def set_pattern_options(self, pattern_names: list[str], selected: str) -> None:
        self.window.combo_cap_pattern.blockSignals(True)
        self.window.combo_cap_pattern.clear()
        for name in pattern_names:
            key = name.lower().strip()
            self.window.combo_cap_pattern.addItem("Charuco" if key == "charuco" else "Chessboard", key)
        if self.window.combo_cap_pattern.count() == 0:
            self.window.combo_cap_pattern.addItem("Chessboard", "chessboard")
        index = self.window.combo_cap_pattern.findData(selected.lower().strip())
        self.window.combo_cap_pattern.setCurrentIndex(index if index >= 0 else 0)
        self.window.combo_cap_pattern.blockSignals(False)
        self._emit_pattern_changed()

    def board_settings(self) -> CalibrationBoardSettings:
        return CalibrationBoardSettings(
            chessboard_cols=int(self._chess_cols_spin.value()),
            chessboard_rows=int(self._chess_rows_spin.value()),
            chessboard_square_size_m=float(self.window.doubleSpinBox.value()) / 1000.0,
            charuco_squares_x=int(self._charuco_x_spin.value()),
            charuco_squares_y=int(self._charuco_y_spin.value()),
            charuco_square_size_m=float(self._charuco_square_spin.value()) / 1000.0,
            charuco_marker_size_m=float(self._charuco_marker_spin.value()) / 1000.0,
        )

    def set_board_settings(self, settings: CalibrationBoardSettings) -> None:
        self._chess_cols_spin.setValue(int(settings.chessboard_cols))
        self._chess_rows_spin.setValue(int(settings.chessboard_rows))
        self.window.doubleSpinBox.setValue(float(settings.chessboard_square_size_m) * 1000.0)
        self._charuco_x_spin.setValue(int(settings.charuco_squares_x))
        self._charuco_y_spin.setValue(int(settings.charuco_squares_y))
        self._charuco_square_spin.setValue(float(settings.charuco_square_size_m) * 1000.0)
        self._charuco_marker_spin.setValue(float(settings.charuco_marker_size_m) * 1000.0)

    def current_workflow_mode(self) -> Literal["intrinsics", "sync_extrinsics"]:
        data = self._workflow_combo.currentData()
        mode = str(data if data is not None else "intrinsics").lower().strip()
        return "sync_extrinsics" if mode == "sync_extrinsics" else "intrinsics"

    def set_workflow_mode(self, mode: str) -> None:
        normalized = "sync_extrinsics" if mode.lower().strip() == "sync_extrinsics" else "intrinsics"
        index = self._workflow_combo.findData(normalized)
        self._workflow_combo.blockSignals(True)
        self._workflow_combo.setCurrentIndex(index if index >= 0 else 0)
        self._workflow_combo.blockSignals(False)
        self._set_mode_button_state(normalized)
        if normalized == "sync_extrinsics":
            self.enable_all_overlays()
            self._capture_button.setText("Capture Intrinsics Sample(s)")
            self._capture_sync_button.setEnabled(True)
        else:
            self._capture_sync_button.setEnabled(True)

    def enable_all_overlays(self) -> None:
        self._overlay_checkbox.blockSignals(True)
        self._overlay_checkbox.setChecked(True)
        self._overlay_checkbox.blockSignals(False)
        for tile in self._tiles.values():
            tile.set_overlay_active(True)
        self.preview_options_changed.emit()

    def auto_capture_enabled(self) -> bool:
        return self._auto_capture_checkbox.isChecked()

    def set_auto_capture_enabled(self, enabled: bool) -> None:
        self._auto_capture_checkbox.setChecked(enabled)
        for tile in self._tiles.values():
            tile.set_auto_active(enabled)

    def auto_capture_cooldown_sec(self) -> float:
        return float(self._auto_cooldown_spin.value())

    def intrinsics_max_samples(self) -> int:
        return int(self._intrinsics_max_spin.value())

    def extrinsics_max_sync_sets(self) -> int:
        return int(self._extrinsics_max_spin.value())

    def auto_capture_max_samples(self) -> int:
        if self.current_workflow_mode() == "sync_extrinsics":
            return self.extrinsics_max_sync_sets()
        return self.intrinsics_max_samples()

    def active_progress_maximum(self) -> int:
        return self.auto_capture_max_samples()

    def active_progress_label(self, current: int) -> str:
        maximum = self.active_progress_maximum()
        if maximum <= 0:
            return f"{int(current)} / No limit"
        suffix = " sync" if self.current_workflow_mode() == "sync_extrinsics" else ""
        return f"{int(current)}/{maximum}{suffix}"

    def set_auto_capture_status(self, message: str) -> None:
        self._auto_status.setText(message)

    def relaxed_sync_enabled(self) -> bool:
        return True

    def overlay_enabled(self) -> bool:
        if not self._tiles:
            return self._overlay_checkbox.isChecked()
        return any(tile.overlay_enabled() for tile in self._tiles.values())

    def overlay_enabled_for(self, source_id: str) -> bool:
        tile = self._tiles.get(source_id)
        return tile.overlay_enabled() if tile else self._overlay_checkbox.isChecked()

    def mirror_preview_enabled(self) -> bool:
        return self._mirror_checkbox.isChecked()

    def mirror_preview_enabled_for(self, source_id: str) -> bool:
        tile = self._tiles.get(source_id)
        return self._mirror_checkbox.isChecked() or (tile.mirror_enabled() if tile else False)

    def undistort_enabled_for(self, source_id: str) -> bool:
        tile = self._tiles.get(source_id)
        return tile.undistort_enabled() if tile else False

    def spatial_grid_values(self) -> tuple[int, int]:
        return int(self._grid_cols_spin.value()), int(self._grid_rows_spin.value())

    def set_spatial_grid_values(self, cols: int, rows: int) -> None:
        self._grid_cols_spin.blockSignals(True)
        self._grid_rows_spin.blockSignals(True)
        self._grid_cols_spin.setValue(max(1, int(cols)))
        self._grid_rows_spin.setValue(max(1, int(rows)))
        self._grid_cols_spin.blockSignals(False)
        self._grid_rows_spin.blockSignals(False)

    def set_acceptance_threshold_values(self, min_quality: float, min_coverage_ratio: float) -> None:
        if self.current_workflow_mode() == "sync_extrinsics":
            quality_spin = self._extrinsics_quality_spin
            coverage_spin = self._extrinsics_coverage_spin
        else:
            quality_spin = self._intrinsics_quality_spin
            coverage_spin = self._intrinsics_coverage_spin
        quality_spin.blockSignals(True)
        coverage_spin.blockSignals(True)
        quality_spin.setValue(float(min_quality))
        coverage_spin.setValue(float(min_coverage_ratio) * 100.0)
        quality_spin.blockSignals(False)
        coverage_spin.blockSignals(False)

    def acceptance_threshold_values(self) -> tuple[float, float]:
        if self.current_workflow_mode() == "sync_extrinsics":
            return self.extrinsics_threshold_values()
        return self.intrinsics_threshold_values()

    def intrinsics_threshold_values(self) -> tuple[float, float]:
        return (
            float(self._intrinsics_quality_spin.value()),
            float(self._intrinsics_coverage_spin.value()) / 100.0,
        )

    def extrinsics_threshold_values(self) -> tuple[float, float]:
        return (
            float(self._extrinsics_quality_spin.value()),
            float(self._extrinsics_coverage_spin.value()) / 100.0,
        )

    def load_root_directory(self, directory_path: Path | str) -> None:
        path = Path(directory_path)
        if not path.exists() or not path.is_dir():
            self._log(f"Directory not found: {path}")
            return
        self._project_root = path
        self._directory_path.setText(str(path))
        self._directory_tree.clear()
        root = QTreeWidgetItem(self._directory_tree)
        root.setText(0, path.name or str(path))
        root.setText(1, "Map")
        root.setData(0, Qt.ItemDataRole.UserRole, str(path))
        root.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
        self._populate_directory_item(root, path, 1)
        root.setExpanded(True)

    def _populate_directory_item(self, parent: QTreeWidgetItem, path: Path, depth: int) -> None:
        while parent.childCount() > 0:
            parent.removeChild(parent.child(0))
        try:
            items = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError:
            return
        for item_path in items:
            if item_path.name.startswith("."):
                continue
            item = QTreeWidgetItem(parent)
            item.setText(0, item_path.name)
            item.setData(0, Qt.ItemDataRole.UserRole, str(item_path))
            if item_path.is_dir():
                item.setText(1, "Map")
                item.setIcon(0, self._icon_provider.icon(QFileIconProvider.IconType.Folder))
                if depth < 10:
                    dummy = QTreeWidgetItem(item)
                    dummy.setText(0, "Loading...")
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
            else:
                item.setText(1, "Bestand")
                item.setIcon(0, self._icon_provider.icon(QtCore.QFileInfo(str(item_path))))
            try:
                modified = datetime.fromtimestamp(item_path.stat().st_mtime).strftime("%d-%m-%Y %H:%M")
            except OSError:
                modified = "-"
            item.setText(2, modified)

    def _on_directory_item_expanded(self, item: QTreeWidgetItem) -> None:
        if item.data(0, Qt.ItemDataRole.UserRole + 1) is False:
            path = Path(str(item.data(0, Qt.ItemDataRole.UserRole)))
            self._populate_directory_item(item, path, self._directory_depth(item) + 1)

    def _directory_depth(self, item: QTreeWidgetItem) -> int:
        depth = 0
        current = item
        while current.parent() is not None:
            depth += 1
            current = current.parent()
        return depth

    def _go_up_directory(self) -> None:
        parent = self._project_root.parent
        if parent != self._project_root:
            self.load_root_directory(parent)

    def _go_down_directory(self, item: QTreeWidgetItem | None = None) -> None:
        target_item = item or self._directory_tree.currentItem()
        if target_item is None:
            self._log("Select a folder first.")
            return
        path_data = target_item.data(0, Qt.ItemDataRole.UserRole)
        if path_data is None:
            return
        path = Path(str(path_data))
        if path.is_dir():
            self.load_root_directory(path)
            return
        self._log(f"Not a folder: {path.name}")

    def _browse_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self.window, "Selecteer een project map", str(self._project_root))
        if not selected:
            return
        self.load_root_directory(Path(selected))
        self.switch_page(3)
        self._log(f"Project folder loaded: {selected}")


class DesignedMainWindow(FunctionalMainWindow, Ui_MainWindow):
    def _create_calibration_panel(self, default_camera_csv: str, default_fps: float):
        if not hasattr(QtCore.Qt, "QFrame"):
            QtCore.Qt.QFrame = QtWidgets.QFrame
        if not hasattr(QtWidgets, "QAction"):
            QtWidgets.QAction = QtGui.QAction
        self.setupUi(self)
        self._compact_camera_controls()
        self._setup_resizable_shell()
        self._setup_settings_menu()
        return DesignedCalibrationPanel(
            window=self,
            default_camera_csv=default_camera_csv,
            default_fps=default_fps,
        )

    def _compact_camera_controls(self) -> None:
        self.btn_camera_detect = QPushButton("Detect Cameras", self.frame)
        self.btn_camera_detect.setObjectName("btn_camera_detect")
        self.btn_camera_start_live = QPushButton("Start Live", self.frame)
        self.btn_camera_start_live.setObjectName("btn_camera_start_live")
        self.btn_camera_start_live.setProperty("accent", True)
        self.btn_camera_stop_live = QPushButton("Stop Live", self.frame)
        self.btn_camera_stop_live.setObjectName("btn_camera_stop_live")
        self.btn_camera_stop_live.setEnabled(False)

        live_actions = QWidget(self.frame)
        live_actions_layout = QHBoxLayout(live_actions)
        live_actions_layout.setContentsMargins(0, 0, 0, 0)
        live_actions_layout.setSpacing(6)
        live_actions_layout.addWidget(self.btn_camera_detect)
        live_actions_layout.addWidget(self.btn_camera_start_live)
        live_actions_layout.addWidget(self.btn_camera_stop_live)

        top_layout = self.frame.layout()
        if isinstance(top_layout, QGridLayout):
            top_layout.setContentsMargins(10, 8, 10, 8)
            top_layout.setHorizontalSpacing(8)
            top_layout.setVerticalSpacing(6)
            top_layout.addWidget(self.lab_cap_fps, 0, 0)
            top_layout.addWidget(self.spin_cap_fps, 0, 1)
            top_layout.addWidget(self.lab_cap_pattern, 1, 0)
            top_layout.addWidget(self.combo_cap_pattern, 1, 1)
            top_layout.addWidget(live_actions, 2, 0, 1, 2)
            top_layout.addWidget(self.frame_2, 0, 2, 3, 1)
            top_layout.addWidget(self.frame_3, 0, 3, 3, 1)
            top_layout.addWidget(
                self.btn_cap_reset_calibration,
                0,
                4,
                1,
                1,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            )
            top_layout.setColumnStretch(0, 0)
            top_layout.setColumnStretch(1, 1)
            top_layout.setColumnStretch(2, 1)
            top_layout.setColumnStretch(3, 1)
            top_layout.setColumnStretch(4, 0)

        for widget in [self.spin_cap_fps, self.combo_cap_pattern]:
            widget.setMaximumWidth(420)

        for panel in [self.frame_2, self.frame_3]:
            layout = panel.layout()
            if isinstance(layout, QVBoxLayout):
                layout.setContentsMargins(8, 6, 8, 6)
                layout.setSpacing(5)

        for button in [
            self.btn_cap_intrinsics_start,
            self.btn_cap_calculate_intrinsics,
            self.btn_cap_extrinsics_start,
            self.btn_cap_calculate_extrinsics,
            self.btn_camera_detect,
            self.btn_camera_start_live,
            self.btn_camera_stop_live,
        ]:
            button.setMinimumHeight(28)

        self.btn_cap_reset_calibration.setText("")
        self.btn_cap_reset_calibration.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.btn_cap_reset_calibration.setToolTip("Reset calibration")
        self.btn_cap_reset_calibration.setFixedSize(36, 36)
        self.btn_cap_reset_calibration.setProperty("danger", True)
        self.frame.setMinimumHeight(130)

    def _setup_resizable_shell(self) -> None:
        central_layout = self.centralwidget.layout()
        if central_layout is None or getattr(self, "_main_splitter", None) is not None:
            return

        for widget in [self.frame_menu, self.frame_pages, self.frame_console]:
            central_layout.removeWidget(widget)

        while central_layout.count():
            item = central_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self.frame_menu.setMinimumWidth(120)
        self.frame_menu.setMaximumWidth(360)
        self.frame_pages.setMinimumWidth(420)
        self.frame_console.setMinimumHeight(125)

        self._right_splitter = QSplitter(Qt.Orientation.Vertical, self.centralwidget)
        self._right_splitter.setObjectName("splitter_content_console")
        self._right_splitter.setChildrenCollapsible(False)
        self._right_splitter.addWidget(self.frame_pages)
        self._right_splitter.addWidget(self.frame_console)
        self._right_splitter.setStretchFactor(0, 5)
        self._right_splitter.setStretchFactor(1, 2)
        self._right_splitter.setSizes([760, 150])

        self._main_splitter = QSplitter(Qt.Orientation.Horizontal, self.centralwidget)
        self._main_splitter.setObjectName("splitter_main")
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self.frame_menu)
        self._main_splitter.addWidget(self._right_splitter)
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.setSizes([190, 1330])

        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self._main_splitter, 0, 0, 1, 1)

    def _setup_settings_menu(self) -> None:
        if getattr(self, "menuSettings", None) is not None:
            return

        self.menuSettings = QtWidgets.QMenu(self.menuBar)
        self.menuSettings.setObjectName("menuSettings")
        self.menuSettings.setTitle("Settings")

        self.menuUiScale = QtWidgets.QMenu(self.menuSettings)
        self.menuUiScale.setObjectName("menuUiScale")
        self.menuUiScale.setTitle("UI scale")
        self._ui_scale_actions: list[QtGui.QAction] = []
        self._ui_scale_group = QtGui.QActionGroup(self)
        self._ui_scale_group.setExclusive(True)

        for label, value in [
            ("30%", 0.30),
            ("40%", 0.40),
            ("50%", 0.50),
            ("60%", 0.60),
            ("70%", 0.70),
            ("80%", 0.80),
            ("90%", 0.90),
            ("100%", 1.00),
            ("110%", 1.10),
            ("125%", 1.25),
            ("150%", 1.50),
        ]:
            action = QtGui.QAction(label, self)
            action.setCheckable(True)
            action.setData(value)
            action.triggered.connect(
                lambda checked=False, scale=value: self._apply_ui_scale(scale, persist=True)
            )
            self._ui_scale_group.addAction(action)
            self.menuUiScale.addAction(action)
            self._ui_scale_actions.append(action)

        self.menuSettings.addMenu(self.menuUiScale)
        self.menuBar.insertMenu(self.menuHelp.menuAction(), self.menuSettings)
        self._sync_ui_scale_menu()

    def _setup_ui(self) -> None:
        self._designed_status_bar().showMessage("Idle")

    def _designed_status_bar(self):
        status_bar = getattr(self, "statusBar", None)
        return status_bar() if callable(status_bar) else status_bar

    def _set_status(self, message: str) -> None:
        status_bar = self._designed_status_bar()
        if status_bar is not None:
            status_bar.showMessage(message)

    def _apply_window_style(self) -> None:
        self._apply_ui_scale(self._configured_ui_scale(), persist=False)

    def _configured_ui_scale(self) -> float:
        try:
            value = float(getattr(self._config, "ui_scale", 0.70))
        except (TypeError, ValueError):
            value = 0.70
        return max(0.30, min(1.6, value))

    def _apply_ui_scale(self, scale: float, persist: bool) -> None:
        scale = max(0.30, min(1.6, float(scale)))
        self._current_ui_scale = scale

        app = QtWidgets.QApplication.instance()
        if app is not None:
            if not hasattr(self, "_base_app_font_point_size"):
                point_size = app.font().pointSizeF()
                self._base_app_font_point_size = point_size if point_size > 0 else 9.0
            font = app.font()
            font.setPointSizeF(max(7.0, self._base_app_font_point_size * scale))
            app.setFont(font)

        apply_styles(self, scale=scale)
        self._sync_ui_scale_menu()

        if persist:
            self._config.ui_scale = scale
            try:
                self._config.save()
            except Exception:  # noqa: BLE001
                pass

    def _sync_ui_scale_menu(self) -> None:
        actions = getattr(self, "_ui_scale_actions", [])
        if not actions:
            return
        current = getattr(self, "_current_ui_scale", self._configured_ui_scale())
        for action in actions:
            action.blockSignals(True)
            action.setChecked(abs(float(action.data()) - current) < 0.001)
            action.blockSignals(False)

    def _apply_initial_window_geometry(self) -> None:
        self.resize(1280, 800)
