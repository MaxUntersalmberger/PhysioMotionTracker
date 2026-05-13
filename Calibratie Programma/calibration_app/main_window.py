from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFileDialog, QDockWidget, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from .calibration_manager import CalibrationOnlyManager
from .camera_grid import CameraGridWidget
from .config import CalibrationAppConfig
from .legacy_bridge import ensure_legacy_path
from .multi_camera_preview import MultiCameraPreviewWidget
from .project import CalibrationProject, CalibrationProjectRepository
from .qt_workers import CalibrationAnalysisOutcome, CalibrationAnalysisWorker, CameraProbeWorker, CaptureWorker
from .widgets import CalibrationSettingsWidget, CameraControlWidget, HomeWidget, ResultsWidget

ensure_legacy_path()

from calibration.manager import CalibrationCaptureResult  # noqa: E402
from calibration.repository import CalibrationRepository  # noqa: E402
from capture.backend import CaptureBatch  # noqa: E402
from capture.sources import parse_sources_csv  # noqa: E402
from models.types import CalibrationBundle, CameraProbeResult, CameraSourceConfig  # noqa: E402


LOGGER = logging.getLogger(__name__)


class CalibrationMainWindow(QMainWindow):
    def __init__(self, config: CalibrationAppConfig) -> None:
        super().__init__()
        self._config = config
        self._project_repo = CalibrationProjectRepository(self._config.projects_dir)
        self._profile_repo = CalibrationRepository()
        self._manager = CalibrationOnlyManager()
        self._current_project: CalibrationProject | None = None
        self._profile_path = self._config.app_root / "calibration" / "current_calibration.json"
        self._current_bundle: CalibrationBundle | None = None
        self._latest_batch: CaptureBatch | None = None
        self._latest_result: CalibrationCaptureResult | None = None
        self._capture_pending = False
        self._auto_pending = False
        self._last_auto_capture_sec = 0.0
        self._last_capture_output_sec = 0.0
        self._last_quality_update_sec = 0.0
        self._last_history_count = 0
        self._active_sources: list[CameraSourceConfig] = []
        self._probe_results: dict[str, CameraProbeResult] = {}
        self._probe_worker: CameraProbeWorker | None = None
        self._capture_worker: CaptureWorker | None = None
        self._dock_widgets: list[QDockWidget] = []

        self._home = HomeWidget(self._config.default_sources_csv, self._config.default_capture_fps)
        self._camera_controls = CameraControlWidget(self._config.default_sources_csv, self._config.default_capture_fps)
        self._calibration_controls = CalibrationSettingsWidget()
        self._results = ResultsWidget()
        self._preview = MultiCameraPreviewWidget(minimum_tile_size=(320, 180))
        self._camera_grid = CameraGridWidget()
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._analysis_worker = CalibrationAnalysisWorker(self._manager)

        self._build_ui()
        self._connect_signals()
        self._sync_calibration_settings()
        self._analysis_worker.start()
        self._apply_bundle(None, self._profile_path)
        self.setWindowTitle(self._config.app_name)
        self.resize(1480, 920)

    def _build_ui(self) -> None:
        title = QLabel("PhysioMotion Calibratie")
        title.setObjectName("appTitle")
        subtitle = QLabel("Nieuw programma voor camera-calibratie, resultaten en export.")
        subtitle.setObjectName("appSubtitle")

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._home, "Home")
        self._tabs.addTab(self._build_calibration_tab(), "Cameras + Calibration")
        self._tabs.addTab(self._build_results_tab(), "Results + Export")
        root_layout.addWidget(self._tabs, 1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")
        self._apply_styles()

    def _build_calibration_tab(self) -> QWidget:
        workspace = QMainWindow()
        workspace.setObjectName("dockWorkspace")
        workspace.setDockNestingEnabled(True)
        workspace.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.South)
        workspace.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
            | QMainWindow.DockOption.AnimatedDocks
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._calibration_controls)

        camera_dock = self._build_dock("Camera Controls", self._camera_controls)
        calibration_dock = self._build_dock("Calibration Settings", scroll)
        preview_dock = self._build_dock("Live Preview", self._preview)
        grid_dock = self._build_dock("Camera Grid", self._camera_grid)

        workspace.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, calibration_dock)
        workspace.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, camera_dock)
        workspace.tabifyDockWidget(calibration_dock, camera_dock)
        calibration_dock.raise_()

        workspace.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, preview_dock)
        workspace.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, grid_dock)
        workspace.tabifyDockWidget(preview_dock, grid_dock)
        preview_dock.raise_()

        workspace.resizeDocks([calibration_dock, preview_dock], [720, 720], Qt.Orientation.Horizontal)
        return workspace

    def _build_dock(self, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setWidget(widget)
        self._dock_widgets.append(dock)
        return dock

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._results)
        splitter.addWidget(self._log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #eef3f8; }
            QMainWindow#dockWorkspace { background: #eef3f8; }
            QLabel#appTitle { color: #10212f; font-size: 26px; font-weight: 700; }
            QLabel#appSubtitle { color: #4b5f73; font-size: 13px; margin-bottom: 6px; }
            QTabWidget::pane { border: 1px solid #c9d7e4; border-radius: 8px; background: #ffffff; top: -1px; }
            QTabBar::tab {
                background: #dbe8f3; color: #17324a; border: 1px solid #c9d7e4;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                padding: 8px 14px; margin-right: 2px; min-width: 150px;
            }
            QTabBar::tab:selected { background: #ffffff; border-bottom-color: #ffffff; font-weight: 700; }
            QDockWidget {
                border: 1px solid #c9d7e4;
                border-radius: 6px;
            }
            QDockWidget::title {
                background: #dbe8f3;
                color: #17324a;
                padding: 7px 10px;
                font-weight: 700;
            }
            QGroupBox {
                border: 1px solid #c9d7e4; border-radius: 8px; margin-top: 12px;
                background: #ffffff; font-weight: 600; font-size: 13px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #17324a; }
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit {
                border: 1px solid #cbd6e0; border-radius: 6px; background: #fbfdff; padding: 6px;
            }
            QPushButton {
                border: none; border-radius: 6px; background: #1f6feb; color: white;
                padding: 8px 14px; font-weight: 600; font-size: 13px;
            }
            QPushButton:hover { background: #175dc2; }
            QPushButton:disabled { background: #9db9d8; color: #eff4f8; }
            """
        )

    def _connect_signals(self) -> None:
        self._home.new_project_requested.connect(self._on_new_project)
        self._home.open_project_requested.connect(self._on_open_project)
        self._camera_controls.probe_requested.connect(self._on_probe_requested)
        self._camera_controls.sample_requested.connect(self._on_sample_requested)
        self._camera_controls.live_requested.connect(self._on_live_requested)
        self._camera_controls.stop_requested.connect(self._stop_capture_worker)
        self._calibration_controls.capture_sample_requested.connect(self._on_capture_calibration_requested)
        self._calibration_controls.solve_intrinsics_requested.connect(self._on_solve_intrinsics)
        self._calibration_controls.solve_extrinsics_requested.connect(self._on_solve_extrinsics)
        self._calibration_controls.load_profile_requested.connect(self._on_load_profile)
        self._calibration_controls.save_profile_requested.connect(self._on_save_profile)
        self._calibration_controls.reset_samples_requested.connect(self._on_reset_samples)
        self._calibration_controls.settings_changed.connect(self._on_calibration_settings_changed)
        self._results.load_profile_requested.connect(self._on_load_profile)
        self._results.save_profile_requested.connect(self._on_save_profile)
        self._results.export_profile_requested.connect(self._on_export_profile)
        self._preview.source_selected.connect(self._camera_grid.set_selected_source)
        self._camera_grid.source_selected.connect(self._preview.select_source)
        self._analysis_worker.result_ready.connect(self._on_analysis_result)
        self._analysis_worker.error.connect(self._on_worker_error)
        self._analysis_worker.state_changed.connect(lambda state: self._append_log(f"Calibration analysis: {state}"))

    def _on_new_project(self, name: str, sources_csv: str, target_fps: float) -> None:
        project = self._project_repo.create(name, sources_csv=sources_csv, target_fps=target_fps)
        self._set_project(project)
        self._append_log(f"New project created: {project.root_dir}")
        self._tabs.setCurrentIndex(1)

    def _on_open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open calibration project", str(self._project_repo.base_dir))
        if not directory:
            return
        try:
            project = self._project_repo.load(Path(directory))
        except (OSError, ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Calibration project", str(exc))
            return
        self._set_project(project)
        self._append_log(f"Project opened: {project.root_dir}")
        self._tabs.setCurrentIndex(1)

    def _set_project(self, project: CalibrationProject) -> None:
        self._current_project = project
        self._profile_path = project.calibration_profile_path or project.default_profile_path
        self._home.set_project(project)
        self._results.set_project(project)
        self._camera_controls.set_sources_csv(project.sources_csv)
        self._camera_controls.set_target_fps(project.target_fps)
        bundle = self._profile_repo.load(self._profile_path)
        self._apply_bundle(bundle, self._profile_path)

    def _sync_project_settings(self) -> None:
        if self._current_project is None:
            self._config.default_sources_csv = self._camera_controls.sources_csv()
            self._config.default_capture_fps = self._camera_controls.target_fps()
            self._config.save()
            return
        self._current_project.sources_csv = self._camera_controls.sources_csv()
        self._current_project.target_fps = self._camera_controls.target_fps()
        self._project_repo.save(self._current_project)
        self._home.set_project(self._current_project)

    def _on_probe_requested(self, source_csv: str) -> None:
        sources = self._parse_sources_or_warn(source_csv)
        if not sources:
            return
        self._sync_project_settings()
        self._active_sources = sources
        self._stop_probe_worker()
        self._camera_controls.set_state("Probing sources...")
        self._camera_controls.set_probe_running(True)
        self._preview.set_sources(sources, self._probe_results)
        self._preview.clear_preview("Probing sources...")
        self._camera_grid.set_sources(sources, self._probe_results)
        worker = CameraProbeWorker(
            sources,
            requested_width=self._camera_controls.requested_width(),
            requested_height=self._camera_controls.requested_height(),
            requested_fps=self._camera_controls.target_fps(),
            exposure=self._camera_controls.requested_exposure(),
            gain=self._camera_controls.requested_gain(),
            white_balance=self._camera_controls.requested_white_balance(),
        )
        worker.result_ready.connect(self._on_probe_results)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_probe_finished)
        self._probe_worker = worker
        worker.start()

    def _on_sample_requested(self, source_csv: str, target_fps: float) -> None:
        self._start_capture(source_csv, target_fps, batch_limit=1)

    def _on_live_requested(self, source_csv: str, target_fps: float) -> None:
        self._start_capture(source_csv, target_fps, batch_limit=None)

    def _start_capture(self, source_csv: str, target_fps: float, batch_limit: int | None) -> None:
        sources = self._parse_sources_or_warn(source_csv)
        if not sources:
            return
        self._sync_project_settings()
        self._sync_calibration_settings()
        self._stop_capture_worker()
        self._active_sources = sources
        self._preview.set_sources(sources, self._probe_results)
        self._camera_grid.set_sources(sources, self._probe_results)
        worker = CaptureWorker(
            sources=sources,
            target_fps=target_fps,
            max_frame_width=1280,
            requested_width=self._camera_controls.requested_width(),
            requested_height=self._camera_controls.requested_height(),
            requested_fps=target_fps,
            exposure=self._camera_controls.requested_exposure(),
            gain=self._camera_controls.requested_gain(),
            white_balance=self._camera_controls.requested_white_balance(),
            batch_limit=batch_limit,
        )
        worker.probe_ready.connect(self._on_probe_results)
        worker.batch_ready.connect(self._on_capture_batch)
        worker.state_changed.connect(lambda state: self._on_capture_state(state, batch_limit))
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_capture_finished)
        self._capture_worker = worker
        self._camera_controls.set_running(True)
        self._camera_controls.set_state("Running capture...")
        worker.start()

    def _on_capture_calibration_requested(self) -> None:
        self._sync_calibration_settings()
        if self._latest_batch is not None and self._latest_batch.frames:
            self._analysis_worker.submit_batch(
                self._latest_batch,
                record_sample=True,
                capture_mode=self._calibration_controls.capture_mode(),
            )
            self._calibration_controls.set_state("Analyzing current calibration frame...")
            return
        if self._capture_worker is not None and self._capture_worker.isRunning():
            self._capture_pending = True
            self._calibration_controls.set_state("Waiting for the next live batch...")
            return
        self._capture_pending = True
        self._start_capture(self._camera_controls.sources_csv(), self._camera_controls.target_fps(), batch_limit=1)

    def _on_capture_batch(self, batch: CaptureBatch) -> None:
        self._latest_batch = batch
        capture_sample = self._capture_pending
        now = time.monotonic()
        if capture_sample:
            self._append_log(f"Calibration sample queued: {len(batch.frames)} frame(s)")
            self._capture_pending = False
        elif now - self._last_capture_output_sec >= 1.0:
            self._camera_controls.append_output(
                f"Live batch: {len(batch.frames)} frame(s), capture={batch.capture_ms:.1f} ms, dropped={len(batch.dropped_sources)}"
            )
            self._last_capture_output_sec = now
        self._preview.show_batch(batch, self._active_sources, self._probe_results)
        self._camera_grid.update_batch(batch, self._active_sources, self._probe_results)
        self._analysis_worker.submit_batch(
            batch,
            record_sample=capture_sample,
            capture_mode=self._calibration_controls.capture_mode(),
        )

    def _on_analysis_result(self, outcome: object) -> None:
        if not isinstance(outcome, CalibrationAnalysisOutcome):
            return
        result = outcome.result
        self._latest_result = result
        if outcome.record_sample:
            self._auto_pending = False
            self._apply_capture_result(result)
            return
        self._update_live_calibration(result)
        self._maybe_auto_capture(result)

    def _on_solve_intrinsics(self) -> None:
        self._sync_calibration_settings()
        readiness = self._manager.workflow_readiness()
        self._calibration_controls.set_workflow_readiness(readiness)
        if not readiness.can_solve_intrinsics:
            self._write_calibration_message("Intrinsics are not ready yet. " + " ".join(readiness.notes[:3]))
            return
        result = self._manager.solve_intrinsics()
        self._apply_bundle(result.bundle, self._profile_path)
        self._persist_bundle(result.bundle, self._profile_path)
        self._write_result_notes(result.notes)
        self._calibration_controls.set_state(f"Intrinsics solved for {len(result.solved_sources)} camera(s).")

    def _on_solve_extrinsics(self) -> None:
        self._sync_calibration_settings()
        readiness = self._manager.workflow_readiness()
        self._calibration_controls.set_workflow_readiness(readiness)
        if not readiness.can_solve_extrinsics:
            self._write_calibration_message("Extrinsics are not ready yet. " + " ".join(readiness.notes[:3]))
            return
        try:
            result = self._manager.solve_extrinsics()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration", str(exc))
            return
        self._apply_bundle(result.bundle, self._profile_path)
        self._persist_bundle(result.bundle, self._profile_path)
        self._write_result_notes(result.notes)
        self._calibration_controls.set_state(f"Extrinsics solved for {len(result.solved_sources)} camera(s).")

    def _on_load_profile(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Load calibration profile",
            str(self._profile_path.parent),
            "Calibration profiles (*.json);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        bundle = self._profile_repo.load(path)
        if bundle is None:
            QMessageBox.warning(self, "Calibration profile", f"Could not load calibration profile from {path}.")
            return
        self._apply_bundle(bundle, path)
        self._append_log(f"Profile loaded: {path}")

    def _on_save_profile(self) -> None:
        if self._current_bundle is None:
            QMessageBox.warning(self, "Calibration profile", "There is no calibration bundle to save yet.")
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save calibration profile",
            str(self._profile_path),
            "Calibration profiles (*.json);;All files (*)",
        )
        if filename:
            self._persist_bundle(self._current_bundle, Path(filename))

    def _on_export_profile(self) -> None:
        if self._current_bundle is None:
            QMessageBox.warning(self, "Calibration export", "There is no calibration bundle to export yet.")
            return
        export_dir = self._current_project.exports_dir if self._current_project else self._config.app_root / "exports"
        setup_name = self._current_project.name if self._current_project else "calibration"
        path = self._profile_repo.save_versioned(self._current_bundle, export_dir, setup_name=setup_name)
        self._results.append_output(f"Exported versioned profile to {path}")
        self._append_log(f"Exported versioned profile: {path}")

    def _on_reset_samples(self) -> None:
        self._manager.reset_samples()
        self._calibration_controls.set_sample_counts({}, 0)
        self._preview.set_sample_counts({}, 0)
        self._calibration_controls.set_camera_quality_scores({})
        self._preview.set_camera_quality_scores({})
        self._calibration_controls.set_sample_history(self._manager.sample_history)
        self._calibration_controls.set_auto_capture_status("Auto capture off.")
        self._update_readiness()

    def _on_calibration_settings_changed(self) -> None:
        self._sync_calibration_settings()
        self._update_readiness()

    def _sync_calibration_settings(self) -> None:
        self._manager.set_board_geometry(self._calibration_controls.board_shape(), self._calibration_controls.square_size_m())
        self._manager.set_detection_preferences(
            self._calibration_controls.calibration_object_type(),
            self._calibration_controls.calibration_detector_name(),
        )

    def _apply_capture_result(self, result: CalibrationCaptureResult) -> None:
        self._update_live_calibration(result)
        self._calibration_controls.set_sample_counts(result.sample_counts, result.synchronized_samples)
        history_count = len(self._manager.sample_history)
        if result.history_entry is not None or history_count != self._last_history_count:
            self._calibration_controls.set_sample_history(self._manager.sample_history)
            self._last_history_count = history_count
        self._update_readiness()
        self._calibration_controls.set_state(self._format_capture_state(result))
        for note in result.notes:
            self._calibration_controls.append_output(note)

    def _update_live_calibration(self, result: CalibrationCaptureResult) -> None:
        now = time.monotonic()
        self._preview.set_calibration_detections(result.detections)
        self._camera_grid.set_calibration_detections(result.detections)
        self._preview.set_sample_counts(result.sample_counts, result.synchronized_samples)
        self._calibration_controls.set_sync_status(self._format_sync_status(result.sync_report))
        if result.history_entry is not None or now - self._last_quality_update_sec >= 1.0:
            self._preview.set_camera_quality_scores(result.camera_quality_scores)
            self._calibration_controls.set_camera_quality_scores(result.camera_quality_scores)
            self._last_quality_update_sec = now

    def _maybe_auto_capture(self, result: CalibrationCaptureResult) -> None:
        if not self._calibration_controls.auto_capture_enabled():
            self._calibration_controls.set_auto_capture_status("Auto capture off.")
            return
        if self._auto_pending or self._latest_batch is None:
            self._calibration_controls.set_auto_capture_status("Auto capture waiting.")
            return
        now = time.monotonic()
        cooldown = self._calibration_controls.auto_capture_cooldown_sec()
        if now - self._last_auto_capture_sec < cooldown:
            self._calibration_controls.set_auto_capture_status("Auto capture cooling down.")
            return
        ready, reason = self._auto_ready(result, self._calibration_controls.capture_mode())
        if not ready:
            self._calibration_controls.set_auto_capture_status(f"Auto waiting: {reason}")
            return
        self._auto_pending = True
        self._last_auto_capture_sec = now
        self._analysis_worker.submit_batch(
            self._latest_batch,
            record_sample=True,
            capture_mode=self._calibration_controls.capture_mode(),
        )

    def _auto_ready(self, result: CalibrationCaptureResult, capture_mode: str) -> tuple[bool, str]:
        visible = [quality for quality in result.camera_quality_scores.values() if quality.visible]
        if capture_mode == "sync_extrinsics":
            sync = result.sync_report
            if sync is None or sync.status != "ready":
                return False, "sync set is not ready."
            if len(sync.detected_sources) < 2:
                return False, "need two cameras with visible board."
            weakest = min((result.camera_quality_scores[source].score for source in sync.detected_sources), default=0.0)
            if weakest < 55.0:
                return False, f"sync quality too low ({weakest:.0f}/100)."
            return True, "sync set ready."
        strong = [quality for quality in visible if quality.score >= 70.0]
        if not strong:
            return False, "intrinsics quality below 70/100."
        return True, f"{len(strong)} strong intrinsics detection(s)."

    def _apply_bundle(self, bundle: CalibrationBundle | None, profile_path: Path | None = None) -> None:
        self._current_bundle = bundle
        if profile_path is not None:
            self._profile_path = profile_path
        self._manager.set_bundle(bundle)
        if bundle is None:
            self._calibration_controls.set_profile_path(str(self._profile_path))
            self._calibration_controls.set_sample_counts({}, 0)
            self._preview.set_sample_counts({}, 0)
            self._preview.set_camera_quality_scores({})
            self._calibration_controls.set_state("No calibration profile loaded.")
            self._results.set_profile_path(str(self._profile_path))
            self._results.set_bundle(None)
            self._update_readiness()
            return
        shape = bundle.metadata.get("board_shape")
        if isinstance(shape, (list, tuple)) and len(shape) == 2:
            self._calibration_controls.set_board_shape((int(shape[0]), int(shape[1])))
        square_size = bundle.metadata.get("square_size_m")
        if isinstance(square_size, (int, float)):
            self._calibration_controls.set_square_size_m(float(square_size))
        object_type = str(bundle.metadata.get("calibration_object_type") or "chessboard")
        detector_name = str(bundle.metadata.get("calibration_detector_name") or "auto")
        self._calibration_controls.set_detection_preferences(object_type, detector_name)
        sample_counts = {source_id: camera.num_samples for source_id, camera in bundle.cameras.items()}
        sync_count = int(bundle.metadata.get("used_synchronized_samples", bundle.metadata.get("synchronized_samples", 0)) or 0)
        self._calibration_controls.set_sample_counts(sample_counts, sync_count)
        self._preview.set_sample_counts(sample_counts, sync_count)
        self._calibration_controls.set_profile_path(str(self._profile_path))
        self._calibration_controls.set_state(f"Calibration loaded: {len(bundle.cameras)} camera(s).")
        self._results.set_profile_path(str(self._profile_path))
        self._results.set_bundle(bundle)
        self._update_readiness()

    def _persist_bundle(self, bundle: CalibrationBundle, path: Path) -> None:
        self._profile_repo.save(bundle, path)
        self._profile_path = path
        self._apply_bundle(bundle, path)
        if self._current_project is not None:
            self._current_project.calibration_profile_path = path
            self._project_repo.save(self._current_project)
            self._home.set_project(self._current_project)
            self._results.set_project(self._current_project)
        self._append_log(f"Profile saved: {path}")

    def _update_readiness(self) -> None:
        self._calibration_controls.set_workflow_readiness(self._manager.workflow_readiness())

    def _write_result_notes(self, notes: list[str]) -> None:
        for note in notes:
            self._calibration_controls.append_output(note)
            self._results.append_output(note)

    def _write_calibration_message(self, message: str) -> None:
        self._calibration_controls.set_state(message)
        self._calibration_controls.append_output(message)
        self._results.append_output(message)

    def _on_probe_results(self, probe_results: object) -> None:
        results = {source_id: probe for source_id, probe in dict(probe_results).items() if isinstance(probe, CameraProbeResult)}
        self._probe_results = results
        self._preview.set_sources(self._active_sources, self._probe_results)
        self._camera_grid.update_probe_results(self._probe_results)
        lines = ["Camera probe complete"]
        for source_id, probe in results.items():
            status = "opened" if probe.opened else "failed"
            fps_text = f", fps={probe.fps:.1f}" if probe.fps > 0 else ""
            lines.append(f"- {source_id}: {status}, backend={probe.backend}, size={probe.width}x{probe.height}{fps_text}")
        self._camera_controls.clear_output()
        self._camera_controls.append_output("\n".join(lines))
        self._camera_controls.set_state(f"Probe found {len(results)} source(s)")

    def _on_capture_state(self, state: str, batch_limit: int | None) -> None:
        self._append_log(f"Capture: {state}")
        if state == "capture_batch_limit_reached" and batch_limit == 1:
            self._camera_controls.set_state("Sample complete")
        elif state == "capture_failed":
            self._camera_controls.set_state("Capture failed")

    def _on_probe_finished(self) -> None:
        self._probe_worker = None
        self._camera_controls.set_probe_running(False)
        self._camera_controls.set_state("Probe complete")

    def _on_capture_finished(self) -> None:
        self._capture_worker = None
        self._camera_controls.set_running(False)
        self._camera_controls.set_state("Idle")
        self._capture_pending = False
        self._auto_pending = False

    def _stop_capture_worker(self) -> None:
        if self._capture_worker is None:
            return
        self._capture_worker.stop()
        if not self._capture_worker.wait(3000):
            self._capture_worker.terminate()
            self._capture_worker.wait(1000)
        self._capture_worker = None
        self._camera_controls.set_running(False)

    def _stop_probe_worker(self) -> None:
        if self._probe_worker is None:
            return
        self._probe_worker.stop()
        if not self._probe_worker.wait(2000):
            self._probe_worker.terminate()
            self._probe_worker.wait(1000)
        self._probe_worker = None

    def _parse_sources_or_warn(self, source_csv: str) -> list[CameraSourceConfig]:
        try:
            sources = parse_sources_csv(source_csv)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid sources", str(exc))
            return []
        if not sources:
            QMessageBox.warning(self, "Invalid sources", "No capture sources were parsed.")
            return []
        return sources

    def _format_sync_status(self, sync_report) -> str:
        if sync_report is None:
            return "Camera sync: unavailable"
        missing = f" missing: {', '.join(sync_report.missing_sources)}" if sync_report.missing_sources else ""
        return (
            f"Camera sync: {sync_report.status} | {len(sync_report.detected_sources)}/{sync_report.total_sources} "
            f"cameras saw the board | frame spread={sync_report.frame_index_spread} | "
            f"timestamp spread={sync_report.timestamp_spread_ms:.1f} ms{missing}"
        )

    def _format_capture_state(self, result: CalibrationCaptureResult) -> str:
        sync = result.sync_report
        if sync is None:
            return "Calibration sample captured."
        if result.capture_mode == "intrinsics":
            return f"Intrinsics sample stored for {len(sync.detected_sources)}/{sync.total_sources} visible camera(s)."
        if sync.status == "ready":
            return f"Extrinsics sync set ready: {len(sync.detected_sources)}/{sync.total_sources} cameras."
        return f"Extrinsics candidate {sync.status}: {len(sync.detected_sources)}/{sync.total_sources} cameras."

    def _append_log(self, message: str) -> None:
        self._log.appendPlainText(message)
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.ensureCursorVisible()

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("Worker error: %s", message)
        self._append_log(f"Error: {message}")
        self.statusBar().showMessage(message)

    def closeEvent(self, event) -> None:
        self._stop_capture_worker()
        self._stop_probe_worker()
        self._analysis_worker.stop()
        if not self._analysis_worker.wait(3000):
            self._analysis_worker.terminate()
            self._analysis_worker.wait(1000)
        super().closeEvent(event)
