from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from capture.backend import CaptureBatch
from capture.sources import describe_sources, parse_sources_csv
from calibration import CalibrationCaptureResult, CalibrationManager, CalibrationRepository
from core.config import AppConfig
from detectors import PoseDetector, create_detector, normalize_detector_name
from models.types import CalibrationBundle, CameraProbeResult, CameraSourceConfig, PipelineResult, SessionManifest
from pipeline.manager import MocapPipeline
from session import SessionRepository, SessionState
from workers import CalibrationAnalysisOutcome, CalibrationAnalysisWorker, CameraProbeWorker, CaptureWorker, PipelineWorker, StartupResult, StartupWorker

from .widgets import CalibrationPanelWidget, CameraGridWidget, CapturePanelWidget, FramePreviewWidget, PipelineStatusWidget, SessionPanelWidget


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._capture_panel = CapturePanelWidget(
            default_sources_csv=self._config.default_sources_csv,
            default_fps=self._config.default_capture_fps,
            default_detector_name=self._config.default_detector_name,
        )
        self._calibration_panel = CalibrationPanelWidget()
        self._calibration_repo = CalibrationRepository()
        self._session_repo = SessionRepository()
        self._calibration_manager = CalibrationManager(
            board_shape=self._calibration_panel.board_shape(),
            square_size_m=self._calibration_panel.square_size_m(),
        )
        self._calibration_profile_path = self._config.calibration_dir / "current_calibration.json"
        self._current_calibration_bundle: CalibrationBundle | None = None
        self._latest_batch: CaptureBatch | None = None
        self._latest_calibration_result: CalibrationCaptureResult | None = None
        self._calibration_capture_pending = False
        self._pending_calibration_sample_frame_index: int | None = None
        self._current_capture_batch_limit: int | None = None
        self._last_capture_output_update_sec = 0.0
        self._last_pipeline_note_update_sec = 0.0
        self._last_calibration_quality_update_sec = 0.0
        self._last_calibration_history_count = 0
        self._session_state = SessionState()
        self._requested_detector_name = self._capture_panel.detector_name()
        self._active_detector_name = "initializing"

        placeholder_detector = create_detector("synthetic")
        self._pipeline = MocapPipeline(detector=placeholder_detector)
        self._pipeline_worker = PipelineWorker(self._pipeline)
        self._calibration_worker = CalibrationAnalysisWorker(self._calibration_manager)
        self._startup_worker: StartupWorker | None = None
        self._probe_worker: CameraProbeWorker | None = None
        self._capture_worker: CaptureWorker | None = None
        self._active_sources: list[CameraSourceConfig] = []
        self._probe_results: dict[str, CameraProbeResult] = {}

        self._preview_panel = FramePreviewWidget()
        self._capture_preview_panel = FramePreviewWidget(show_source_picker=False, minimum_image_size=(520, 292))
        self._calibration_preview_panel = FramePreviewWidget(show_source_picker=False, minimum_image_size=(520, 292))
        self._preview_widgets = [self._preview_panel, self._capture_preview_panel, self._calibration_preview_panel]
        self._camera_grid = CameraGridWidget()
        self._session_panel = SessionPanelWidget()
        self._status_panel = PipelineStatusWidget()
        self._startup_banner = QFrame()
        self._startup_banner.setObjectName("startupBanner")
        self._startup_banner_label = QLabel("Loading detector and calibration...")
        self._startup_banner_label.setObjectName("startupBannerLabel")
        self._startup_progress = QProgressBar()
        self._startup_progress.setObjectName("startupProgress")
        self._startup_progress.setRange(0, 0)
        self._startup_progress.setTextVisible(False)
        self._log_box = QPlainTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setPlaceholderText("Runtime logs appear here.")

        self._build_ui()
        self._connect_signals()
        self._calibration_worker.result_ready.connect(self._on_calibration_analysis_result)
        self._calibration_worker.error.connect(self._on_worker_error)
        self._calibration_worker.state_changed.connect(lambda state: self._append_log(f"Calibration analysis: {state}"))
        self._calibration_worker.start()

        self._begin_startup_sequence()
        self._status_panel.set_idle()

        self.setWindowTitle(self._config.app_name)
        self.resize(1460, 920)

    def _build_ui(self) -> None:
        title = QLabel("Programma Structuur Shell")
        title.setObjectName("appTitle")
        subtitle = QLabel(
            "Tabbed workbench for capture, live view, calibration, and diagnostics."
        )
        subtitle.setObjectName("appSubtitle")

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        startup_layout = QHBoxLayout(self._startup_banner)
        startup_layout.setContentsMargins(12, 10, 12, 10)
        startup_layout.setSpacing(12)
        startup_layout.addWidget(self._startup_banner_label, 1)
        startup_layout.addWidget(self._startup_progress, 0)
        root_layout.addWidget(self._startup_banner)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_capture_tab(), "Capture")
        self._tabs.addTab(self._build_session_tab(), "Session")
        self._tabs.addTab(self._build_live_view_tab(), "Live View")
        self._tabs.addTab(self._build_calibration_tab(), "Calibration")
        self._tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")
        root_layout.addWidget(self._tabs, 1)

        self.setCentralWidget(root)
        self.statusBar().showMessage("Idle")
        self._apply_styles()
        self._set_loading_state(True, "Loading detector and calibration...")

    def _build_capture_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._capture_panel)
        splitter.addWidget(self._capture_preview_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _build_live_view_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        preview_splitter = QSplitter(Qt.Horizontal)
        preview_splitter.addWidget(self._preview_panel)
        preview_splitter.addWidget(self._camera_grid)
        preview_splitter.setStretchFactor(0, 2)
        preview_splitter.setStretchFactor(1, 1)
        layout.addWidget(preview_splitter, 1)
        return page

    def _build_session_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._session_panel)
        layout.addStretch(1)
        return page

    def _build_calibration_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(self._calibration_panel)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._calibration_preview_panel)
        splitter.addWidget(scroll_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _build_diagnostics_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        diagnostics_splitter = QSplitter(Qt.Vertical)
        diagnostics_splitter.addWidget(self._status_panel)
        diagnostics_splitter.addWidget(self._log_box)
        diagnostics_splitter.setStretchFactor(0, 3)
        diagnostics_splitter.setStretchFactor(1, 2)
        layout.addWidget(diagnostics_splitter, 1)
        return page

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #eef3f8;
            }
            QLabel#appTitle {
                color: #10212f;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#appSubtitle {
                color: #4b5f73;
                font-size: 13px;
                margin-bottom: 6px;
            }
            QFrame#startupBanner {
                border: 1px solid #d0dde9;
                border-radius: 10px;
                background: #f7fbff;
            }
            QLabel#startupBannerLabel {
                color: #17324a;
                font-size: 12px;
                font-weight: 700;
            }
            QProgressBar#startupProgress {
                min-width: 260px;
                height: 14px;
                border: 1px solid #cbd6e0;
                border-radius: 7px;
                background: #ffffff;
            }
            QProgressBar#startupProgress::chunk {
                background: #1f6feb;
                border-radius: 7px;
            }
            QTabWidget::pane {
                border: 1px solid #c9d7e4;
                border-radius: 10px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #dbe8f3;
                color: #17324a;
                border: 1px solid #c9d7e4;
                border-bottom-color: #c9d7e4;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 14px;
                margin-right: 2px;
                min-width: 110px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border-bottom-color: #ffffff;
                font-weight: 700;
            }
            QTabBar::tab:hover {
                background: #eef5fb;
            }
            QGroupBox {
                border: 1px solid #c9d7e4;
                border-radius: 10px;
                margin-top: 12px;
                background: #ffffff;
                font-weight: 600;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #17324a;
            }
            QLabel#calibrationWorkflowLabel,
            QLabel#calibrationQualitySummaryLabel,
            QLabel#calibrationHistorySummaryLabel,
            QLabel#calibrationGuidanceLabel,
            QLabel#calibrationSyncLabel {
                color: #4b5f73;
            }
            QLabel#calibrationStateLabel,
            QLabel#calibrationQualityDetail {
                color: #304659;
            }
            QFrame#calibrationQualityRow {
                border: 1px solid #d6e2ed;
                border-radius: 10px;
                background: #f7fbff;
                padding: 8px;
            }
            QLabel#calibrationQualityTitle {
                color: #17324a;
                font-size: 13px;
                font-weight: 700;
            }
            QProgressBar#calibrationQualityProgress {
                border: 1px solid #cbd6e0;
                border-radius: 6px;
                background: #ffffff;
                text-align: center;
                color: #17324a;
                height: 16px;
            }
            QProgressBar#calibrationQualityProgress::chunk {
                background: #1f6feb;
                border-radius: 6px;
            }
            QPlainTextEdit#calibrationHistoryOutput {
                background: #fbfdff;
                border: 1px solid #d6e2ed;
            }
            QLineEdit, QDoubleSpinBox, QPlainTextEdit, QLabel {
                font-size: 13px;
            }
            QLineEdit, QDoubleSpinBox, QPlainTextEdit {
                border: 1px solid #cbd6e0;
                border-radius: 8px;
                background: #fbfdff;
                padding: 6px;
            }
            QPushButton {
                border: none;
                border-radius: 8px;
                background: #1f6feb;
                color: white;
                padding: 8px 14px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #175dc2;
            }
            QPushButton:disabled {
                background: #9db9d8;
                color: #eff4f8;
            }
            #captureStateLabel {
                color: #304659;
                font-weight: 600;
            }
            """
        )

    def _begin_startup_sequence(self) -> None:
        if self._startup_worker is not None:
            return

        self._set_loading_state(True, "Loading detector and calibration...")
        self._startup_worker = StartupWorker(self._requested_detector_name, self._calibration_profile_path)
        self._startup_worker.progress_changed.connect(self._on_startup_progress)
        self._startup_worker.result_ready.connect(self._on_startup_ready)
        self._startup_worker.error.connect(self._on_startup_error)
        self._startup_worker.start()

    def _on_startup_progress(self, percent: int, message: str) -> None:
        self._startup_progress.setRange(0, 100)
        self._startup_progress.setValue(max(0, min(100, int(percent))))
        self._startup_banner_label.setText(message)
        self.statusBar().showMessage(message)

    def _on_startup_ready(self, startup_result: StartupResult) -> None:
        self._startup_worker = None
        self._active_detector_name = startup_result.detector_name
        if self._capture_panel.detector_name() != startup_result.detector_name:
            self._capture_panel.set_detector_name(startup_result.detector_name)

        self._pipeline_worker.update_detector(startup_result.detector)
        self._apply_calibration_bundle(startup_result.calibration_bundle, startup_result.calibration_path)
        self._start_pipeline_worker()
        self._refresh_session_panel()

        for message in startup_result.messages:
            self._append_log(message)

        self._set_loading_state(False, "Ready")
        self._capture_panel.set_state("Ready")
        self._status_panel.set_idle()

    def _on_startup_error(self, message: str) -> None:
        self._startup_worker = None
        LOGGER.error("Startup failed: %s", message)
        self._append_log(f"Startup error: {message}")
        self._set_loading_state(False, "Startup error")
        self._startup_banner.setVisible(True)
        self._startup_banner_label.setText(f"Startup error: {message}")
        self._startup_progress.setRange(0, 100)
        self._startup_progress.setValue(100)
        self._start_pipeline_worker()
        self._tabs.setEnabled(True)
        self._capture_panel.set_state("Startup completed with fallback runtime.")
        self.statusBar().showMessage(message)

    def _set_loading_state(self, loading: bool, message: str) -> None:
        self._startup_banner.setVisible(loading)
        self._tabs.setEnabled(not loading)
        self._startup_progress.setRange(0, 0 if loading else 100)
        if not loading:
            self._startup_progress.setValue(100)
        self._startup_banner_label.setText(message)
        self.statusBar().showMessage(message)

    def _set_preview_sources(self, sources: list[CameraSourceConfig], probe_results: dict[str, CameraProbeResult] | None = None) -> None:
        for preview in self._preview_widgets:
            preview.set_sources(sources, probe_results if probe_results is not None else self._probe_results)

    def _set_preview_pipeline_result(self, result: PipelineResult | None) -> None:
        for preview in self._preview_widgets:
            preview.set_pipeline_result(result)

    def _set_preview_calibration_detections(self, detections: dict[str, object] | None) -> None:
        for preview in self._preview_widgets:
            preview.set_calibration_detections(detections)

    def _show_preview_batch(self, batch: CaptureBatch) -> None:
        for preview in self._preview_widgets:
            preview.show_batch(batch)

    def _clear_preview_widgets(self, message: str) -> None:
        for preview in self._preview_widgets:
            preview.clear_preview(message)

    def _on_main_preview_source_selected(self, source_id: str) -> None:
        self._camera_grid.set_selected_source(source_id or None)
        for preview in (self._capture_preview_panel, self._calibration_preview_panel):
            preview.select_source(source_id or None)

    def _create_detector(self, detector_name: str) -> tuple[str, PoseDetector]:
        normalized = normalize_detector_name(detector_name)
        if normalized == "mediapipe":
            try:
                detector = create_detector(normalized)
            except Exception as exc:
                LOGGER.warning("MediaPipe detector unavailable, falling back to synthetic detector: %s", exc)
                fallback = create_detector("synthetic")
                return "synthetic", fallback

            model_path = getattr(detector, "model_asset_path", None)
            LOGGER.info("Using MediaPipe pose detector model at %s", model_path)
            return "mediapipe", detector

        if normalized == "synthetic":
            detector = create_detector(normalized)
            LOGGER.info("Using synthetic demo pose detector")
            return "synthetic", detector

        raise ValueError(f"Unknown detector '{detector_name}'.")

    def _connect_signals(self) -> None:
        self._capture_panel.probe_requested.connect(self._on_probe_requested)
        self._capture_panel.sample_requested.connect(self._on_sample_requested)
        self._capture_panel.live_requested.connect(self._on_live_requested)
        self._capture_panel.stop_requested.connect(self._stop_capture_worker)
        self._capture_panel.detector_changed.connect(self._on_detector_changed)
        self._calibration_panel.capture_sample_requested.connect(self._on_capture_calibration_requested)
        self._calibration_panel.solve_intrinsics_requested.connect(self._on_solve_calibration_intrinsics)
        self._calibration_panel.solve_extrinsics_requested.connect(self._on_solve_calibration_extrinsics)
        self._calibration_panel.load_profile_requested.connect(self._on_load_calibration_profile)
        self._calibration_panel.save_profile_requested.connect(self._on_save_calibration_profile)
        self._calibration_panel.reset_samples_requested.connect(self._on_reset_calibration_samples)
        self._session_panel.new_session_requested.connect(self._on_new_session_requested)
        self._session_panel.save_session_requested.connect(self._on_save_session_requested)
        self._session_panel.load_session_requested.connect(self._on_load_session_requested)
        self._preview_panel.source_selected.connect(self._on_main_preview_source_selected)
        self._camera_grid.source_selected.connect(self._preview_panel.select_source)

        self._pipeline_worker.result_ready.connect(self._on_pipeline_result)
        self._pipeline_worker.error.connect(self._on_worker_error)
        self._pipeline_worker.state_changed.connect(lambda state: self._append_log(f"Pipeline: {state}"))

    def _start_pipeline_worker(self) -> None:
        self._pipeline_worker.update_calibration(self._current_calibration_bundle)
        if not self._pipeline_worker.isRunning():
            self._pipeline_worker.start()
        self._set_preview_sources([], {})
        self._set_preview_pipeline_result(None)
        self._clear_preview_widgets("Ready for live frames.")
        self._camera_grid.clear()

    def _on_new_session_requested(self) -> None:
        session_id = self._session_repo.create_session_id()
        self._session_panel.set_session_id(session_id)
        self._session_panel.set_notes([])
        self._session_state.active_session_dir = self._config.sessions_dir / session_id
        self._session_state.loaded_session_dir = None
        self._session_state.loaded_manifest = None
        self._session_state.recording_active = False
        self._session_state.playback_active = False
        self._refresh_session_panel()
        self._session_panel.set_state(f"New session prepared: {session_id}")
        self._append_log(f"New session prepared: {session_id}")

    def _on_save_session_requested(self) -> None:
        manifest = self._build_session_manifest()
        if manifest is None:
            return

        session_dir = self._session_repo.session_dir(self._config.sessions_dir, manifest.session_id)
        manifest_path = self._session_repo.save(manifest, session_dir)
        self._session_state.active_session_dir = session_dir
        self._session_state.loaded_session_dir = session_dir
        self._session_state.loaded_manifest = manifest
        self._session_state.recording_active = self._capture_worker is not None and self._capture_worker.isRunning()
        self._session_panel.set_state(f"Session snapshot saved to {manifest_path}")
        self._session_panel.set_active_session_dir(str(session_dir))
        self._session_panel.set_loaded_session_dir(str(session_dir))
        self._session_panel.set_manifest_path(str(manifest_path))
        self._session_panel.set_manifest(manifest)
        self._append_log(f"Session snapshot saved: {manifest_path}")

    def _on_load_session_requested(self) -> None:
        start_dir = self._session_state.loaded_session_dir or self._session_state.active_session_dir or self._config.sessions_dir
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Load session manifest",
            str(start_dir),
            "Session manifests (*.json);;All files (*)",
        )
        if not filename:
            return

        path = Path(filename)
        manifest = self._session_repo.load(path)
        if manifest is None:
            QMessageBox.warning(self, "Session", f"Could not load session manifest from {path}.")
            return

        self._stop_capture_worker()
        self._stop_probe_worker()
        self._apply_session_manifest(manifest, path)
        self._append_log(f"Session loaded from {path}")

    def _refresh_session_panel(self) -> None:
        session_id = self._session_panel.session_id()
        if not session_id:
            session_id = self._session_repo.create_session_id()
            self._session_panel.set_session_id(session_id)

        manifest = self._build_session_manifest(session_id)
        if manifest is not None:
            self._session_panel.set_manifest(manifest)
            manifest_path = self._session_repo.manifest_path(self._config.sessions_dir / session_id)
            self._session_panel.set_manifest_path(str(manifest_path))

        active_session_dir = self._session_state.active_session_dir or (self._config.sessions_dir / session_id)
        self._session_panel.set_active_session_dir(str(active_session_dir))
        self._session_panel.set_loaded_session_dir(str(self._session_state.loaded_session_dir) if self._session_state.loaded_session_dir else None)

        state_text = "Session snapshot ready."
        if self._session_state.loaded_manifest is not None:
            state_text = f"Loaded session: {self._session_state.loaded_manifest.session_id}"
        elif self._session_state.recording_active:
            state_text = "Live capture active; session snapshot will include the current capture state."
        self._session_panel.set_state(state_text)

    def _build_session_manifest(self, session_id: str | None = None) -> SessionManifest | None:
        try:
            sources = parse_sources_csv(self._capture_panel.source_csv())
        except ValueError as exc:
            self._session_panel.set_state(f"Session snapshot unavailable: {exc}")
            return None

        resolved_session_id = session_id or self._session_panel.session_id() or self._session_repo.create_session_id()
        if not self._session_panel.session_id():
            self._session_panel.set_session_id(resolved_session_id)

        total_frames = 0
        if self._latest_batch is not None and self._latest_batch.frames:
            total_frames = max(frame.frame_index for frame in self._latest_batch.frames.values())

        calibration_file = None
        if self._current_calibration_bundle is not None:
            calibration_file = str(self._calibration_profile_path)

        metadata: dict[str, object] = {
            "detector_name": self._active_detector_name,
            "capture_mode": "live" if self._capture_worker is not None and self._capture_worker.isRunning() else "idle",
            "calibration_loaded": self._current_calibration_bundle is not None,
            "board_shape": list(self._calibration_panel.board_shape()),
            "square_size_m": self._calibration_panel.square_size_m(),
            "source_count": len(sources),
            "probe_results": {
                source_id: {
                    "opened": probe.opened,
                    "width": probe.width,
                    "height": probe.height,
                    "backend": probe.backend,
                }
                for source_id, probe in self._probe_results.items()
            },
        }
        if self._latest_calibration_result is not None:
            metadata["latest_calibration_sync_status"] = self._latest_calibration_result.sync_report.status if self._latest_calibration_result.sync_report is not None else "unknown"

        return self._session_repo.build_manifest(
            session_id=resolved_session_id,
            fps=self._capture_panel.target_fps(),
            sources=sources,
            total_frames=total_frames,
            calibration_file=calibration_file,
            notes=self._session_panel.notes(),
            metadata=metadata,
        )

    def _apply_session_manifest(self, manifest: SessionManifest, manifest_path: Path) -> None:
        session_dir = manifest_path.parent
        self._session_state.loaded_session_dir = session_dir
        self._session_state.loaded_manifest = manifest
        self._session_state.active_session_dir = session_dir
        self._session_state.recording_active = False
        self._session_state.playback_active = False
        self._latest_batch = None
        self._latest_calibration_result = None
        self._probe_results = {}
        self._active_sources = list(manifest.sources)

        self._session_panel.set_session_id(manifest.session_id)
        self._session_panel.set_notes(manifest.notes)
        self._session_panel.set_loaded_session_dir(str(session_dir))
        self._session_panel.set_active_session_dir(str(session_dir))
        self._session_panel.set_manifest_path(str(manifest_path))
        self._session_panel.set_manifest(manifest)

        self._capture_panel.set_source_csv(self._session_repo.sources_to_csv(manifest.sources))
        self._capture_panel.set_target_fps(manifest.fps)
        self._set_preview_sources(self._active_sources, self._probe_results)
        self._camera_grid.set_sources(self._active_sources, self._probe_results)
        self._clear_preview_widgets(f"Session loaded: {manifest.session_id}")

        if manifest.calibration_file:
            calibration_path = Path(manifest.calibration_file)
            bundle = self._calibration_repo.load(calibration_path)
            if bundle is not None:
                self._apply_calibration_bundle(bundle, calibration_path)
            else:
                self._calibration_panel.append_output(f"Could not load calibration bundle from {calibration_path}.")

        self._refresh_session_panel()
        self._session_panel.set_state(f"Session loaded: {manifest.session_id}")

    def _on_probe_requested(self, source_csv: str) -> None:
        sources = self._parse_sources_or_warn(source_csv)
        if not sources:
            return

        self._active_sources = sources
        self._stop_probe_worker()
        self._capture_panel.set_state("Probing sources...")
        self._capture_panel.set_probe_running(True)
        self._set_preview_sources(sources, self._probe_results)
        self._set_preview_pipeline_result(None)
        self._camera_grid.set_sources(sources, self._probe_results)
        self._clear_preview_widgets("Probing sources...")

        worker = CameraProbeWorker(sources)
        worker.result_ready.connect(self._on_probe_results)
        worker.state_changed.connect(lambda state: self._append_log(f"Probe: {state}"))
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_probe_finished)
        self._probe_worker = worker
        worker.start()

    def _on_sample_requested(self, source_csv: str, target_fps: float) -> None:
        self._start_capture_worker(source_csv, target_fps, batch_limit=1)

    def _on_live_requested(self, source_csv: str, target_fps: float) -> None:
        self._start_capture_worker(source_csv, target_fps, batch_limit=None)

    def _on_capture_calibration_requested(self) -> None:
        self._sync_calibration_geometry()
        if self._capture_worker is not None and self._capture_worker.isRunning() and self._latest_batch is not None and self._latest_batch.frames:
            result = self._calibration_manager.capture_frames(self._latest_batch.frames, record_sample=True)
            self._apply_calibration_capture_result(result)
            return

        if self._capture_worker is not None and self._capture_worker.isRunning():
            self._calibration_capture_pending = True
            self._calibration_panel.set_state("Waiting for the next live batch...")
            self._append_log("Calibration sample requested; waiting for next live batch.")
            return

        self._calibration_capture_pending = True
        self._calibration_panel.set_state("Capturing a calibration sample...")
        self._on_sample_requested(self._capture_panel.source_csv(), self._capture_panel.target_fps())

    def _on_solve_calibration_intrinsics(self) -> None:
        self._sync_calibration_geometry()
        result = self._calibration_manager.solve_intrinsics()
        if result.solved_sources:
            self._apply_calibration_bundle(result.bundle, self._calibration_profile_path)
            self._persist_calibration_bundle(result.bundle, self._calibration_profile_path)
            self._calibration_panel.set_state(
                f"Intrinsics solved for {len(result.solved_sources)}/{len(result.bundle.cameras)} camera(s)."
            )
        else:
            self._calibration_panel.set_state("Intrinsics solve did not produce a usable calibration.")

        self._calibration_panel.set_sample_counts(result.bundle.metadata.get("sample_counts", self._calibration_manager.sample_counts()), self._calibration_manager.synchronized_sample_count)
        for note in result.notes:
            self._calibration_panel.append_output(note)
        self._append_log(f"Calibration intrinsics solve finished: {len(result.solved_sources)} camera(s) solved")

    def _on_solve_calibration_extrinsics(self) -> None:
        self._sync_calibration_geometry()
        try:
            result = self._calibration_manager.solve_extrinsics()
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration", str(exc))
            return

        if result.solved_sources:
            self._apply_calibration_bundle(result.bundle, self._calibration_profile_path)
            self._persist_calibration_bundle(result.bundle, self._calibration_profile_path)
            self._calibration_panel.set_state(
                f"Extrinsics solved for {len(result.solved_sources)}/{len(result.bundle.cameras)} camera(s)."
            )
        else:
            self._calibration_panel.set_state("Extrinsics solve did not update the calibration bundle.")

        self._calibration_panel.set_sample_counts(
            result.bundle.metadata.get("sample_counts", self._calibration_manager.sample_counts()),
            int(result.bundle.metadata.get("used_synchronized_samples", self._calibration_manager.synchronized_sample_count) or 0),
        )
        for note in result.notes:
            self._calibration_panel.append_output(note)
        self._append_log(f"Calibration extrinsics solve finished: {len(result.solved_sources)} camera(s) solved")

    def _on_load_calibration_profile(self) -> None:
        start_dir = self._calibration_profile_path.parent if self._calibration_profile_path is not None else self._config.calibration_dir
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Load calibration profile",
            str(start_dir),
            "Calibration profiles (*.json);;All files (*)",
        )
        if not filename:
            return

        path = Path(filename)
        bundle = self._calibration_repo.load(path)
        if bundle is None:
            QMessageBox.warning(self, "Calibration profile", f"Could not load calibration profile from {path}.")
            return

        self._apply_calibration_bundle(bundle, path)
        self._append_log(f"Calibration profile loaded from {path}")

    def _on_save_calibration_profile(self) -> None:
        if self._current_calibration_bundle is None:
            QMessageBox.warning(self, "Calibration profile", "There is no calibration bundle to save yet.")
            return

        start_dir = self._calibration_profile_path.parent if self._calibration_profile_path is not None else self._config.calibration_dir
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save calibration profile",
            str(start_dir / (self._calibration_profile_path.name if self._calibration_profile_path is not None else "current_calibration.json")),
            "Calibration profiles (*.json);;All files (*)",
        )
        if not filename:
            return

        path = Path(filename)
        self._persist_calibration_bundle(self._current_calibration_bundle, path)
        self._append_log(f"Calibration profile saved to {path}")

    def _on_reset_calibration_samples(self) -> None:
        self._calibration_manager.reset_samples()
        self._calibration_panel.set_sample_counts({}, 0)
        self._calibration_panel.set_camera_quality_scores({})
        self._calibration_panel.set_sample_history(self._calibration_manager.sample_history)
        self._last_calibration_quality_update_sec = 0.0
        self._last_calibration_history_count = 0
        self._calibration_panel.set_sync_status("Camera sync: waiting for the next sample.")
        self._calibration_panel.set_state("Calibration samples reset.")
        self._calibration_panel.append_output("Calibration sample history cleared.")
        self._append_log("Calibration samples reset")

    def _on_detector_changed(self, detector_name: str) -> None:
        normalized = normalize_detector_name(detector_name)
        if normalized == self._active_detector_name:
            return

        try:
            actual_name, detector = self._create_detector(normalized)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid detector", str(exc))
            self._capture_panel.set_detector_name(self._active_detector_name)
            return

        self._active_detector_name = actual_name
        self._pipeline_worker.update_detector(detector)
        self._set_preview_pipeline_result(None)
        self._status_panel.set_idle()
        self._config.default_detector_name = actual_name
        try:
            self._config.save()
        except OSError as exc:
            LOGGER.warning("Failed to save detector preference: %s", exc)
        self._append_log(f"Detector switched to {actual_name}")
        self.statusBar().showMessage(f"Detector: {actual_name}")

        if self._capture_panel.detector_name() != actual_name:
            self._capture_panel.set_detector_name(actual_name)

    def _start_capture_worker(self, source_csv: str, target_fps: float, batch_limit: int | None) -> None:
        sources = self._parse_sources_or_warn(source_csv)
        if not sources:
            return

        self._stop_capture_worker()
        self._active_sources = sources
        self._pipeline_worker.update_calibration(self._current_calibration_bundle)
        if self._current_calibration_bundle is None:
            self._append_log("No calibration bundle loaded yet; reconstruction will remain unavailable until one is solved or loaded.")
        else:
            self._append_log(f"Using loaded calibration bundle for sources: {describe_sources(sources)}")
        self._set_preview_sources(sources, self._probe_results)
        self._set_preview_pipeline_result(None)
        self._camera_grid.set_sources(sources, self._probe_results)
        self._clear_preview_widgets("Starting capture...")

        worker = CaptureWorker(
            sources=sources,
            target_fps=target_fps,
            max_frame_width=1280,
            batch_limit=batch_limit,
        )
        worker.probe_ready.connect(self._on_probe_results)
        worker.batch_ready.connect(self._on_capture_batch_ready)
        worker.state_changed.connect(lambda state: self._on_capture_state_changed(state, batch_limit))
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_capture_finished)
        self._capture_worker = worker
        self._capture_panel.set_running(True)
        self._capture_panel.set_state("Running capture...")
        self._session_state.recording_active = True
        self._refresh_session_panel()
        self.statusBar().showMessage("Capture running")
        self._current_capture_batch_limit = batch_limit
        self._last_capture_output_update_sec = 0.0
        worker.start()

    def _on_capture_batch_ready(self, batch: CaptureBatch) -> None:
        self._latest_batch = batch
        capture_sample = self._calibration_capture_pending
        now = time.monotonic()
        if capture_sample:
            self._capture_panel.set_state("Analyzing calibration sample...")
            self._pending_calibration_sample_frame_index = max((frame.frame_index for frame in batch.frames.values()), default=0)
            self._append_log(f"Calibration sample queued for analysis: {len(batch.frames)} frame(s)")
        elif now - self._last_capture_output_update_sec >= 1.0:
            self._capture_panel.append_output(
                f"Live batch: {len(batch.frames)} frame(s), capture={batch.capture_ms:.1f} ms, dropped={len(batch.dropped_sources)}"
            )
            self._last_capture_output_update_sec = now
        self._show_preview_batch(batch)
        self._camera_grid.update_batch(batch, self._active_sources, self._probe_results)
        self._calibration_worker.submit_batch(batch, record_sample=capture_sample)
        if self._pipeline_worker.isRunning():
            self._pipeline_worker.submit_batch(batch)

    def _on_calibration_analysis_result(self, outcome: object) -> None:
        if not isinstance(outcome, CalibrationAnalysisOutcome):
            return

        result = outcome.result
        self._latest_calibration_result = result
        if outcome.record_sample:
            self._calibration_capture_pending = False
            self._apply_calibration_capture_result(result)
            self._pending_calibration_sample_frame_index = None
            self._refresh_session_panel()
            return

        self._update_calibration_live_visuals(result)

    def _update_calibration_live_visuals(self, result: CalibrationCaptureResult) -> None:
        now = time.monotonic()
        self._set_preview_calibration_detections(result.detections)
        self._camera_grid.set_calibration_detections(result.detections)
        self._calibration_panel.set_sync_status(self._format_sync_status(result.sync_report))
        if result.history_entry is not None or now - self._last_calibration_quality_update_sec >= 1.0:
            self._calibration_panel.set_camera_quality_scores(result.camera_quality_scores)
            self._last_calibration_quality_update_sec = now

    def _apply_calibration_capture_result(self, result: CalibrationCaptureResult) -> None:
        self._update_calibration_live_visuals(result)
        self._calibration_panel.set_sample_counts(result.sample_counts, result.synchronized_samples)
        current_history_count = len(self._calibration_manager.sample_history)
        if result.history_entry is not None or current_history_count != self._last_calibration_history_count:
            self._calibration_panel.set_sample_history(self._calibration_manager.sample_history)
            self._last_calibration_history_count = current_history_count
        self._calibration_panel.set_state(self._format_capture_state(result))
        for note in result.notes:
            self._calibration_panel.append_output(note)
        self._append_log(
            f"Calibration sample captured: {len(result.sample_counts)} source(s), {result.synchronized_samples} sync sample(s)"
        )

    def _format_sync_status(self, sync_report) -> str:
        if sync_report is None:
            return "Camera sync: unavailable"

        detected = len(sync_report.detected_sources)
        total = sync_report.total_sources
        missing_text = f" missing: {', '.join(sync_report.missing_sources)}" if sync_report.missing_sources else ""
        return (
            f"Camera sync: {sync_report.status} | {detected}/{total} cameras saw the board | "
            f"frame spread={sync_report.frame_index_spread} | timestamp spread={sync_report.timestamp_spread_ms:.1f} ms{missing_text}"
        )

    def _format_capture_state(self, result) -> str:
        sync_report = result.sync_report
        if sync_report is None:
            return "Calibration sample captured."

        detected = len(sync_report.detected_sources)
        total = sync_report.total_sources
        if sync_report.status == "ready":
            return f"Calibration sample ready: {detected}/{total} cameras saw the board in sync."
        if sync_report.status == "partial":
            return f"Calibration sample stored with partial sync: {detected}/{total} cameras saw the board."
        return "Calibration sample not ready yet: show the chessboard in at least two cameras."

    def _sync_calibration_geometry(self) -> None:
        self._calibration_manager.set_board_geometry(
            self._calibration_panel.board_shape(),
            self._calibration_panel.square_size_m(),
        )

    def _apply_calibration_bundle(self, bundle: CalibrationBundle | None, profile_path: Path | None = None) -> None:
        self._current_calibration_bundle = bundle
        self._calibration_manager.set_bundle(bundle)
        self._pipeline_worker.update_calibration(bundle)

        if profile_path is not None:
            self._calibration_profile_path = profile_path

        if bundle is None:
            self._calibration_panel.set_sample_counts({}, 0)
            self._calibration_panel.set_camera_quality_scores({})
            self._calibration_panel.set_sample_history(self._calibration_manager.sample_history)
            self._calibration_panel.set_profile_path(None)
            self._calibration_panel.set_sync_status("Camera sync: unavailable")
            self._calibration_panel.set_state("No calibration profile loaded. Reconstruction is unavailable.")
            self._refresh_session_panel()
            return

        board_shape = bundle.metadata.get("board_shape")
        if isinstance(board_shape, (list, tuple)) and len(board_shape) == 2:
            self._calibration_panel.set_board_shape((int(board_shape[0]), int(board_shape[1])))

        square_size_m = bundle.metadata.get("square_size_m")
        if isinstance(square_size_m, (int, float)):
            self._calibration_panel.set_square_size_m(float(square_size_m))

        self._sync_calibration_geometry()

        sample_counts = {source_id: camera.num_samples for source_id, camera in bundle.cameras.items()}
        synchronized_samples = int(bundle.metadata.get("used_synchronized_samples", bundle.metadata.get("synchronized_samples", 0)) or 0)
        self._calibration_panel.set_sample_counts(sample_counts, synchronized_samples)
        self._calibration_panel.set_sample_history(self._calibration_manager.sample_history)
        self._calibration_panel.set_sync_status(
            f"Camera sync: loaded bundle | synchronized samples={synchronized_samples}"
        )
        self._calibration_panel.set_profile_path(str(self._calibration_profile_path))
        self._calibration_panel.set_state(
            f"Calibration loaded: {len(bundle.cameras)} camera(s), sync={synchronized_samples}."
        )
        self._refresh_session_panel()

    def _persist_calibration_bundle(self, bundle: CalibrationBundle, path: Path | None) -> None:
        target_path = path or self._calibration_profile_path
        try:
            self._calibration_repo.save(bundle, target_path)
        except OSError as exc:
            LOGGER.warning("Failed to save calibration profile: %s", exc)
            QMessageBox.warning(self, "Calibration profile", f"Could not save calibration profile: {exc}")
            return

        self._calibration_profile_path = target_path
        self._calibration_panel.set_profile_path(str(target_path))
        self._refresh_session_panel()

    def _load_existing_calibration(self) -> None:
        bundle = self._calibration_repo.load(self._calibration_profile_path)
        self._apply_calibration_bundle(bundle, self._calibration_profile_path if bundle is not None else None)
        if bundle is not None:
            self._append_log(f"Loaded calibration profile: {self._calibration_profile_path}")

    def _on_pipeline_result(self, result: PipelineResult) -> None:
        self._set_preview_pipeline_result(result)
        self._status_panel.update_result(result)
        now = time.monotonic()
        important_notes = [note for note in result.debug.notes if self._is_pipeline_issue_note(note)]
        if important_notes and now - self._last_pipeline_note_update_sec >= 1.0:
            self._append_log("Pipeline note: " + " | ".join(important_notes[:3]))
            self._last_pipeline_note_update_sec = now

    def _on_probe_results(self, probe_results: object) -> None:
        results: dict[str, CameraProbeResult] = {}
        if isinstance(probe_results, dict):
            for source_id, probe in probe_results.items():
                if isinstance(probe, CameraProbeResult):
                    results[source_id] = probe

        self._probe_results = results
        self._set_preview_sources(self._active_sources, self._probe_results)
        self._camera_grid.update_probe_results(self._probe_results)

        if not results:
            self._capture_panel.append_output("No camera probe results were returned.")
            self._capture_panel.set_state("Probe finished with no results")
            return

        lines = ["Camera probe complete"]
        for source_id, probe in results.items():
            label = next((source.label for source in self._active_sources if source.source_id == source_id), source_id)
            status = "opened" if probe.opened else "failed"
            lines.append(f"- {source_id} ({label}): {status}, backend={probe.backend}, size={probe.width}x{probe.height}")
        summary = "\n".join(lines)
        self._capture_panel.clear_output()
        self._capture_panel.append_output(summary)
        self._capture_panel.set_state(f"Probe found {len(results)} source(s)")
        self.statusBar().showMessage(f"Detected {len(results)} source(s)")

    def _on_capture_state_changed(self, state: str, batch_limit: int | None) -> None:
        self._append_log(f"Capture: {state}")
        if state == "capture_batch_limit_reached" and batch_limit == 1:
            self._capture_panel.set_state("Sample complete")
            self.statusBar().showMessage("Single-batch capture complete")
        elif state == "capture_failed":
            self._capture_panel.set_state("Capture failed")

    def _on_probe_finished(self) -> None:
        self._probe_worker = None
        self._capture_panel.set_state("Probe complete")
        self._capture_panel.set_probe_running(False)

    def _on_capture_finished(self) -> None:
        self._capture_worker = None
        self._capture_panel.set_running(False)
        self._session_state.recording_active = False
        self._current_capture_batch_limit = None
        self._calibration_capture_pending = False
        self._pending_calibration_sample_frame_index = None
        self._refresh_session_panel()
        if self._capture_panel.source_csv():
            self._capture_panel.set_state("Idle")
        self.statusBar().showMessage("Idle")

    def _stop_capture_worker(self) -> None:
        if self._capture_worker is None:
            return
        self._capture_worker.stop()
        if not self._capture_worker.wait(3000):
            LOGGER.warning("Capture worker did not stop in time; forcing termination.")
            self._capture_worker.terminate()
            self._capture_worker.wait(1000)
        self._capture_worker = None
        self._capture_panel.set_running(False)
        self._session_state.recording_active = False
        self._current_capture_batch_limit = None
        self._calibration_capture_pending = False
        self._pending_calibration_sample_frame_index = None
        self._refresh_session_panel()

    def _stop_probe_worker(self) -> None:
        if self._probe_worker is None:
            return
        self._probe_worker.stop()
        if not self._probe_worker.wait(2000):
            LOGGER.warning("Probe worker did not stop in time; forcing termination.")
            self._probe_worker.terminate()
            self._probe_worker.wait(1000)
        self._probe_worker = None

    def _stop_calibration_worker(self) -> None:
        if self._calibration_worker is None:
            return
        self._calibration_worker.stop()
        if not self._calibration_worker.wait(3000):
            LOGGER.warning("Calibration analysis worker did not stop in time; forcing termination.")
            self._calibration_worker.terminate()
            self._calibration_worker.wait(1000)

    def _stop_startup_worker(self) -> None:
        if self._startup_worker is None:
            return
        self._startup_worker.stop()
        if not self._startup_worker.wait(2000):
            LOGGER.warning("Startup worker did not stop in time; forcing termination.")
            self._startup_worker.terminate()
            self._startup_worker.wait(1000)
        self._startup_worker = None

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

    def _append_log(self, message: str) -> None:
        self._log_box.appendPlainText(message)
        self._log_box.moveCursor(QTextCursor.MoveOperation.End)
        self._log_box.ensureCursorVisible()

    def _is_pipeline_issue_note(self, note: str) -> bool:
        lowered = note.lower()
        return any(
            keyword in lowered
            for keyword in (
                "failed",
                "unavailable",
                "skipping",
                "disabled",
                "not ready",
                "no valid",
                "only one camera",
                "demo-only",
                "unavailable",
            )
        )

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("Worker error: %s", message)
        self._append_log(f"Error: {message}")
        self.statusBar().showMessage(message)
        self._capture_panel.set_state(message)

    def closeEvent(self, event) -> None:
        self._stop_startup_worker()
        self._stop_calibration_worker()
        self._stop_capture_worker()
        self._stop_probe_worker()
        if self._pipeline_worker.isRunning():
            self._pipeline_worker.stop()
            if not self._pipeline_worker.wait(3000):
                LOGGER.warning("Pipeline worker did not stop in time; forcing termination.")
                self._pipeline_worker.terminate()
                self._pipeline_worker.wait(1000)
        self._pipeline.shutdown()
        super().closeEvent(event)
