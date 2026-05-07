from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget

from biomechanics import JointAngleRepository, analyze_motion_take_joint_angles
from capture.backend import CaptureBatch
from capture.profiles import CameraControlSettings, assess_batch_synchronization, build_camera_profiles
from capture.sources import describe_sources, parse_sources_csv
from calibration import CalibrationCaptureResult, CalibrationManager, CalibrationRepository
from core.config import AppConfig
from detectors import PoseDetector, create_detector, normalize_detector_name
from exporters import PoseExportReport, format_pose_export_report
from motion import MotionTake, MotionTakeReport, MotionTakeRepository, format_motion_take_report
from models.types import CalibrationBundle, CameraProbeResult, CameraSourceConfig, PipelineResult, SessionManifest
from pipeline.manager import MocapPipeline
from session import SessionPlaybackReader, SessionRecorder, SessionRecordingStats, SessionRepository, SessionState, load_session_calibration, process_recorded_batch
from workers import CalibrationAnalysisOutcome, CalibrationAnalysisWorker, CameraProbeWorker, CaptureWorker, MotionTakeWorker, PipelineWorker, PoseExportWorker, RecordingWorker, StartupResult, StartupWorker

from .widgets import CalibrationPanelWidget, CameraGridWidget, CapturePanelWidget, FramePreviewWidget, MotionAnalysisWidget, PipelineStatusWidget, SessionPanelWidget, SessionReviewWidget


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
        self._last_auto_calibration_capture_sec = 0.0
        self._auto_calibration_capture_pending = False
        self._session_state = SessionState()
        self._recording_worker: RecordingWorker | None = None
        self._latest_recording_stats: SessionRecordingStats | None = None
        self._review_reader: SessionPlaybackReader | None = None
        self._review_manifest_path: Path | None = None
        self._review_current_batch_index = 0
        self._review_calibration_bundle: CalibrationBundle | None = None
        self._review_overlay_cache: dict[int, PipelineResult] = {}
        self._current_motion_take: MotionTake | None = None
        self._current_motion_take_path: Path | None = None
        self._motion_take_worker: MotionTakeWorker | None = None
        self._pose_export_worker: PoseExportWorker | None = None
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
        self._review_preview_panel = FramePreviewWidget(minimum_image_size=(520, 292))
        self._preview_widgets = [self._preview_panel, self._capture_preview_panel, self._calibration_preview_panel]
        self._camera_grid = CameraGridWidget()
        self._session_panel = SessionPanelWidget()
        self._session_review_panel = SessionReviewWidget()
        self._motion_analysis_panel = MotionAnalysisWidget()
        self._status_panel = PipelineStatusWidget()
        self._analysis_tab_page: QWidget | None = None
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
        self._update_calibration_readiness_panel()

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
        self._tabs.addTab(self._build_review_tab(), "Review")
        self._tabs.addTab(self._build_analysis_tab(), "Analysis")
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

    def _build_review_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._session_review_panel)
        splitter.addWidget(self._review_preview_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _build_analysis_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._motion_analysis_panel)
        self._analysis_tab_page = page
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

        if normalized in {"synthetic", "none"}:
            detector = create_detector(normalized)
            LOGGER.info("Using %s pose detector", normalized)
            return normalized, detector

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
        self._session_panel.start_recording_requested.connect(self._on_start_recording_requested)
        self._session_panel.stop_recording_requested.connect(self._on_stop_recording_requested)
        self._session_panel.save_session_requested.connect(self._on_save_session_requested)
        self._session_panel.load_session_requested.connect(self._on_load_session_requested)
        self._session_review_panel.load_loaded_session_requested.connect(self._on_review_load_loaded_session)
        self._session_review_panel.open_manifest_requested.connect(self._on_review_open_manifest)
        self._session_review_panel.frame_requested.connect(self._on_review_frame_requested)
        self._session_review_panel.process_current_requested.connect(self._on_review_process_current_requested)
        self._session_review_panel.process_session_requested.connect(self._on_review_process_session_requested)
        self._session_review_panel.clear_overlays_requested.connect(self._on_review_clear_overlays_requested)
        self._session_review_panel.export_requested.connect(self._on_review_export_requested)
        self._motion_analysis_panel.load_review_take_requested.connect(self._on_analysis_load_review_take)
        self._motion_analysis_panel.open_take_requested.connect(self._on_analysis_open_take)
        self._motion_analysis_panel.analyze_joint_angles_requested.connect(self._on_analysis_joint_angles_requested)
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
        if self._is_recording_active():
            QMessageBox.warning(self, "Session", "Stop the active recording before preparing a new session.")
            return

        session_id = self._session_repo.create_session_id()
        self._session_panel.set_session_id(session_id)
        self._session_panel.set_notes([])
        self._session_state.active_session_dir = self._config.sessions_dir / session_id
        self._session_state.loaded_session_dir = None
        self._session_state.loaded_manifest = None
        self._session_state.recording_active = False
        self._session_state.playback_active = False
        self._latest_recording_stats = None
        self._refresh_session_panel()
        self._session_panel.set_state(f"New session prepared: {session_id}")
        self._append_log(f"New session prepared: {session_id}")

    def _on_save_session_requested(self) -> None:
        self._save_current_session_manifest("Session snapshot saved")

    def _save_current_session_manifest(self, state_message: str) -> Path | None:
        manifest = self._build_session_manifest()
        if manifest is None:
            return None

        session_dir = self._session_repo.session_dir(self._config.sessions_dir, manifest.session_id)
        manifest_path = self._session_repo.save(manifest, session_dir)
        self._session_state.active_session_dir = session_dir
        self._session_state.loaded_session_dir = session_dir
        self._session_state.loaded_manifest = manifest
        self._session_state.recording_active = self._is_recording_active()
        self._session_panel.set_state(f"{state_message} to {manifest_path}")
        self._session_panel.set_active_session_dir(str(session_dir))
        self._session_panel.set_loaded_session_dir(str(session_dir))
        self._session_panel.set_manifest_path(str(manifest_path))
        self._session_panel.set_manifest(manifest)
        self._append_log(f"{state_message}: {manifest_path}")
        return manifest_path

    def _on_start_recording_requested(self) -> None:
        if self._is_recording_active():
            self._session_panel.set_state("Recording is already active.")
            return

        source_csv = self._capture_panel.source_csv()
        sources = self._parse_sources_or_warn(source_csv)
        if not sources:
            return

        session_id = self._session_panel.session_id() or self._session_repo.create_session_id()
        self._session_panel.set_session_id(session_id)
        session_dir = self._session_repo.session_dir(self._config.sessions_dir, session_id)
        recorder = SessionRecorder(
            session_dir=session_dir,
            sources=sources,
            fps=self._capture_panel.target_fps(),
        )
        worker = RecordingWorker(recorder)
        worker.stats_ready.connect(self._on_recording_stats_ready)
        worker.state_changed.connect(self._on_recording_state_changed)
        worker.error.connect(self._on_recording_error)
        self._recording_worker = worker
        self._session_state.active_session_dir = session_dir
        self._session_state.loaded_session_dir = None
        self._session_state.loaded_manifest = None
        self._session_state.recording_active = True
        self._session_panel.set_recording_active(True)
        self._session_panel.set_state(f"Recording session: {session_id}")
        self._append_log(f"Session recording started: {session_dir}")
        worker.start()

        if self._capture_worker is None or not self._capture_worker.isRunning():
            self._start_capture_worker(source_csv, self._capture_panel.target_fps(), batch_limit=None)
        else:
            self._refresh_session_panel()

    def _on_stop_recording_requested(self) -> None:
        self._stop_recording_worker(save_manifest=True, state_message="Session recording saved")

    def _on_recording_stats_ready(self, stats: object) -> None:
        if not isinstance(stats, SessionRecordingStats):
            return
        self._latest_recording_stats = stats
        self._refresh_session_panel()

    def _on_recording_state_changed(self, state: str) -> None:
        self._append_log(f"Recording: {state}")
        if state == "recording_queue_full":
            self._session_panel.set_state("Recording queue is full; frames may be dropped.")
        elif state == "recording_stopped" and self._recording_worker is not None and not self._recording_worker.isRunning():
            if self._recording_worker.latest_stats is not None:
                self._latest_recording_stats = self._recording_worker.latest_stats
            self._recording_worker = None
            self._session_state.recording_active = False
            self._session_panel.set_recording_active(False)
            self._save_current_session_manifest("Session recording saved")

    def _on_recording_error(self, message: str) -> None:
        LOGGER.error("Recording error: %s", message)
        self._append_log(f"Recording error: {message}")
        self._session_panel.set_state(f"Recording error: {message}")
        self.statusBar().showMessage(message)

    def _is_recording_active(self) -> bool:
        return self._recording_worker is not None

    def _stop_recording_worker(self, save_manifest: bool, state_message: str = "Session recording saved") -> None:
        worker = self._recording_worker
        if worker is None:
            self._session_state.recording_active = False
            self._session_panel.set_recording_active(False)
            return

        self._recording_worker = None
        worker.stop()
        if not worker.wait(8000):
            LOGGER.warning("Recording worker did not stop in time; forcing termination.")
            worker.terminate()
            worker.wait(1000)

        if worker.latest_stats is not None:
            self._latest_recording_stats = worker.latest_stats

        self._session_state.recording_active = False
        self._session_panel.set_recording_active(False)
        if save_manifest:
            self._save_current_session_manifest(state_message)
        else:
            self._refresh_session_panel()

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

        self._stop_recording_worker(save_manifest=True, state_message="Session recording saved before loading another session")
        self._stop_capture_worker()
        self._stop_probe_worker()
        self._apply_session_manifest(manifest, path)
        self._load_review_session(path)
        self._append_log(f"Session loaded from {path}")

    def _on_review_load_loaded_session(self) -> None:
        manifest_path = self._current_session_manifest_path()
        if manifest_path is None:
            QMessageBox.warning(self, "Review", "No saved or loaded session manifest is available yet.")
            return
        self._load_review_session(manifest_path)

    def _on_review_open_manifest(self) -> None:
        start_dir = self._session_state.loaded_session_dir or self._session_state.active_session_dir or self._config.sessions_dir
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Open session for review",
            str(start_dir),
            "Session manifests (*.json);;All files (*)",
        )
        if not filename:
            return
        self._load_review_session(Path(filename))

    def _on_review_frame_requested(self, batch_index: int) -> None:
        self._show_review_batch(batch_index)

    def _on_review_process_current_requested(self) -> None:
        self._process_review_batch(self._review_current_batch_index)

    def _on_review_clear_overlays_requested(self) -> None:
        self._review_overlay_cache.clear()
        self._review_preview_panel.set_pipeline_result(None)
        if self._review_reader is None or self._review_reader.batch_count <= 0:
            self._session_review_panel.set_state("Review overlays cleared.")
            return
        self._session_review_panel.set_state(
            f"Reviewing frame {self._review_current_batch_index + 1}/{self._review_reader.batch_count}. Overlay cleared."
        )
        self._append_log("Review overlays cleared")

    def _on_review_process_session_requested(self) -> None:
        if self._motion_take_worker is not None and self._motion_take_worker.isRunning():
            self._session_review_panel.set_state("Session processing is already running.")
            return
        if self._review_reader is None or self._review_manifest_path is None:
            QMessageBox.warning(self, "Process Session", "Load a recorded session in Review before processing it.")
            return
        if self._review_reader.batch_count <= 0:
            self._session_review_panel.set_state("Loaded review session has no frames to process.")
            return

        output_path = self._review_reader.session_dir / "processed" / "motion_take.json"
        detector_name = self._capture_panel.detector_name()
        worker = MotionTakeWorker(
            session_path=self._review_manifest_path,
            detector_name=detector_name,
            output_path=output_path,
        )
        worker.result_ready.connect(self._on_motion_take_ready)
        worker.error.connect(self._on_motion_take_error)
        worker.state_changed.connect(lambda state: self._append_log(f"Motion take: {state}"))
        worker.finished.connect(self._on_motion_take_finished)
        self._motion_take_worker = worker
        self._session_review_panel.set_session_processing_running(True)
        self._session_review_panel.set_state(f"Processing recorded session into a motion take with {detector_name}...")
        self._append_log(f"Motion take processing started: {self._review_manifest_path} -> {output_path}")
        worker.start()

    def _on_motion_take_ready(self, report: object) -> None:
        if not isinstance(report, MotionTakeReport):
            self._session_review_panel.set_state("Session processing finished with an unexpected report.")
            return
        summary = format_motion_take_report(report)
        self._session_review_panel.append_summary(summary)
        self._load_motion_take(report.output_path, activate=True)
        self._session_review_panel.set_state(
            f"Motion take ready: {report.take.summary.frame_count} frame(s) at {report.output_path}."
        )
        self.statusBar().showMessage(f"Motion take ready: {report.output_path}")
        self._append_log(
            f"Motion take ready: session={report.take.session_id}, frames={report.take.summary.frame_count}, "
            f"2d_keypoints={report.take.summary.pose2d_keypoints}, 3d_keypoints={report.take.summary.pose3d_keypoints}"
        )

    def _on_motion_take_error(self, message: str) -> None:
        self._session_review_panel.set_state(f"Session processing failed: {message}")
        self._append_log(f"Motion take error: {message}")
        self.statusBar().showMessage(f"Session processing failed: {message}")

    def _on_motion_take_finished(self) -> None:
        self._session_review_panel.set_session_processing_running(False)
        self._motion_take_worker = None

    def _on_analysis_load_review_take(self) -> None:
        if self._review_reader is None:
            QMessageBox.warning(self, "Analysis", "Load a recorded session in Review before loading its processed take.")
            return
        take_path = self._review_reader.session_dir / "processed" / "motion_take.json"
        if not take_path.exists():
            self._motion_analysis_panel.set_state(f"No processed take found at {take_path}.")
            return
        self._load_motion_take(take_path, activate=True)

    def _on_analysis_open_take(self) -> None:
        start_dir = self._current_motion_take_path.parent if self._current_motion_take_path is not None else self._config.sessions_dir
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Open processed motion take",
            str(start_dir),
            "Motion takes (*.json);;All files (*)",
        )
        if not filename:
            return
        self._load_motion_take(Path(filename), activate=True)

    def _on_analysis_joint_angles_requested(self) -> None:
        if self._current_motion_take is None or self._current_motion_take_path is None:
            self._motion_analysis_panel.set_state("Load a processed motion take before analyzing joint angles.")
            return

        output_path = JointAngleRepository().default_path(self._current_motion_take_path)
        try:
            report = analyze_motion_take_joint_angles(
                self._current_motion_take,
                source_take_path=self._current_motion_take_path,
                output_path=output_path,
            )
        except Exception as exc:
            self._motion_analysis_panel.set_state(f"Joint-angle analysis failed: {exc}")
            self._append_log(f"Joint-angle analysis error: {exc}")
            return

        self._motion_analysis_panel.set_joint_angle_report(report)
        self._append_log(
            f"Joint-angle analysis complete: session={report.analysis.session_id}, "
            f"samples={len(report.analysis.samples)}, output={report.output_path}"
        )

    def _load_motion_take(self, path: Path, activate: bool = False) -> None:
        try:
            take = MotionTakeRepository().load(path)
        except Exception as exc:
            self._motion_analysis_panel.set_state(f"Could not load motion take: {exc}")
            self._append_log(f"Motion take load error: {exc}")
            return

        self._current_motion_take = take
        self._current_motion_take_path = path
        self._motion_analysis_panel.set_motion_take(take, path)
        self._append_log(f"Motion take loaded: {path}")
        if activate and self._analysis_tab_page is not None:
            self._tabs.setCurrentWidget(self._analysis_tab_page)

    def _on_review_export_requested(self) -> None:
        if self._pose_export_worker is not None and self._pose_export_worker.isRunning():
            self._session_review_panel.set_state("Pose export is already running.")
            return
        if self._review_reader is None or self._review_manifest_path is None:
            QMessageBox.warning(self, "Export", "Load a recorded session in Review before exporting poses.")
            return
        if self._review_reader.batch_count <= 0:
            self._session_review_panel.set_state("Loaded review session has no frames to export.")
            return

        output_dir = self._review_reader.session_dir / "exports"
        detector_name = self._capture_panel.detector_name()
        worker = PoseExportWorker(
            session_path=self._review_manifest_path,
            detector_name=detector_name,
            output_dir=output_dir,
            formats=["json", "csv"],
        )
        worker.result_ready.connect(self._on_pose_export_ready)
        worker.error.connect(self._on_pose_export_error)
        worker.state_changed.connect(lambda state: self._append_log(f"Pose export: {state}"))
        worker.finished.connect(self._on_pose_export_finished)
        self._pose_export_worker = worker
        self._session_review_panel.set_export_running(True)
        self._session_review_panel.set_state(f"Exporting recorded poses with {detector_name}...")
        self._append_log(f"Pose export started: {self._review_manifest_path} -> {output_dir}")
        worker.start()

    def _on_pose_export_ready(self, report: object) -> None:
        if not isinstance(report, PoseExportReport):
            self._session_review_panel.set_state("Pose export finished with an unexpected report.")
            return
        summary = format_pose_export_report(report)
        self._session_review_panel.append_summary(summary)
        self._session_review_panel.set_state(
            f"Pose export complete: {report.batches_processed} batch(es) to {report.output_dir}."
        )
        self.statusBar().showMessage(f"Pose export complete: {report.output_dir}")
        self._append_log(
            f"Pose export complete: session={report.session_id}, batches={report.batches_processed}, "
            f"2d_rows={report.pose2d_rows}, 3d_rows={report.pose3d_rows}"
        )

    def _on_pose_export_error(self, message: str) -> None:
        self._session_review_panel.set_state(f"Pose export failed: {message}")
        self._append_log(f"Pose export error: {message}")
        self.statusBar().showMessage(f"Pose export failed: {message}")

    def _on_pose_export_finished(self) -> None:
        self._session_review_panel.set_export_running(False)
        self._pose_export_worker = None

    def _load_review_session(self, manifest_path: Path) -> None:
        try:
            reader = SessionPlaybackReader(manifest_path)
            info = reader.info()
        except Exception as exc:
            self._review_reader = None
            self._review_manifest_path = None
            self._review_calibration_bundle = None
            self._review_overlay_cache.clear()
            self._session_review_panel.clear_review(f"Could not load review session: {exc}")
            self._review_preview_panel.clear_preview("Could not load review session.")
            QMessageBox.warning(self, "Review", f"Could not load session for review: {exc}")
            return

        self._review_reader = reader
        self._review_manifest_path = manifest_path
        self._review_current_batch_index = 0
        self._review_overlay_cache.clear()
        self._review_calibration_bundle = load_session_calibration(info.manifest.calibration_file)
        self._session_review_panel.set_loaded_session(info)
        self._review_preview_panel.set_sources(info.manifest.sources, {})
        if info.is_playable and reader.batch_count > 0:
            self._show_review_batch(0)
        else:
            self._review_preview_panel.clear_preview("Session has no playable frames.")
        self._tabs.setCurrentWidget(self._tabs.widget(2))
        self._append_log(f"Session review loaded: {manifest_path}")

    def _show_review_batch(self, batch_index: int) -> None:
        if self._review_reader is None:
            self._session_review_panel.set_state("No review session loaded.")
            return

        index = max(0, min(max(0, self._review_reader.batch_count - 1), int(batch_index)))
        try:
            batch = self._review_reader.read_batch_at(index)
        except Exception as exc:
            self._session_review_panel.set_state(f"Could not read frame: {exc}")
            self._append_log(f"Review frame error: {exc}")
            return

        self._review_current_batch_index = index
        self._session_review_panel.set_current_frame(index)
        self._review_preview_panel.show_batch(batch, self._review_reader.manifest.sources, {})
        review_result = self._review_overlay_cache.get(index)
        self._review_preview_panel.set_pipeline_result(review_result)
        if review_result is None:
            self._session_review_panel.set_state(f"Reviewing frame {index + 1}/{self._review_reader.batch_count}. Overlay idle.")
            return
        self._session_review_panel.set_state(
            f"Reviewing frame {index + 1}/{self._review_reader.batch_count}. "
            f"Overlay ready via {review_result.debug.detector_name} ({review_result.debug.reconstruction_mode})."
        )

    def _process_review_batch(self, batch_index: int) -> None:
        if self._review_reader is None:
            self._session_review_panel.set_state("No review session loaded.")
            return

        index = max(0, min(max(0, self._review_reader.batch_count - 1), int(batch_index)))
        cached_result = self._review_overlay_cache.get(index)
        if cached_result is not None:
            self._review_preview_panel.set_pipeline_result(cached_result)
            self._session_review_panel.set_state(
                f"Reviewing frame {index + 1}/{self._review_reader.batch_count}. "
                f"Cached overlay via {cached_result.debug.detector_name} ({cached_result.debug.reconstruction_mode})."
            )
            return

        try:
            batch = self._review_reader.read_batch_at(index)
            actual_name, detector = self._create_detector(self._capture_panel.detector_name())
            result = process_recorded_batch(batch, detector, self._review_calibration_bundle)
        except Exception as exc:
            self._session_review_panel.set_state(f"Could not process review frame: {exc}")
            self._append_log(f"Review processing error: {exc}")
            return

        self._review_current_batch_index = index
        self._review_overlay_cache[index] = result
        self._review_preview_panel.show_batch(batch, self._review_reader.manifest.sources, {})
        self._review_preview_panel.set_pipeline_result(result)
        self._session_review_panel.set_current_frame(index)
        self._session_review_panel.set_state(
            f"Reviewing frame {index + 1}/{self._review_reader.batch_count}. "
            f"Processed with {actual_name} in {result.debug.pipeline_ms:.1f} ms ({result.debug.reconstruction_mode})."
        )
        self._append_log(
            f"Review frame processed: frame={index + 1}/{self._review_reader.batch_count}, "
            f"detector={actual_name}, mode={result.debug.reconstruction_mode}, pipeline={result.debug.pipeline_ms:.1f} ms"
        )

    def _current_session_manifest_path(self) -> Path | None:
        if self._session_state.loaded_session_dir is not None:
            return self._session_repo.manifest_path(self._session_state.loaded_session_dir)
        if self._session_state.active_session_dir is not None:
            return self._session_repo.manifest_path(self._session_state.active_session_dir)
        session_id = self._session_panel.session_id()
        if session_id:
            return self._session_repo.manifest_path(self._config.sessions_dir / session_id)
        return None

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
        elif self._is_recording_active():
            frame_count = self._latest_recording_stats.total_frames if self._latest_recording_stats is not None else 0
            state_text = f"Recording active; {frame_count} frame(s) written."
        elif self._capture_worker is not None and self._capture_worker.isRunning():
            state_text = "Live capture active; recording is not running."
        self._session_panel.set_recording_active(self._is_recording_active())
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

        recording_stats = self._latest_recording_stats
        total_frames = recording_stats.total_frames if recording_stats is not None else 0
        if self._latest_batch is not None and self._latest_batch.frames:
            total_frames = max(total_frames, max(frame.frame_index for frame in self._latest_batch.frames.values()))

        calibration_file = None
        if self._current_calibration_bundle is not None:
            calibration_file = str(self._calibration_profile_path)

        metadata: dict[str, object] = {
            "detector_name": self._active_detector_name,
            "capture_mode": "live" if self._capture_worker is not None and self._capture_worker.isRunning() else "idle",
            "recording_active": self._is_recording_active(),
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
        profiles = build_camera_profiles(
            sources,
            self._probe_results,
            requested=CameraControlSettings(
                width=self._capture_panel.requested_width(),
                height=self._capture_panel.requested_height(),
                fps=self._capture_panel.target_fps(),
                exposure=self._capture_panel.requested_exposure(),
                gain=self._capture_panel.requested_gain(),
                white_balance=self._capture_panel.requested_white_balance(),
            ),
        )
        metadata["camera_profiles"] = {
            source_id: {
                "label": profile.label,
                "kind": profile.kind,
                "uri": profile.uri,
                "requested": {
                    "width": profile.requested.width,
                    "height": profile.requested.height,
                    "fps": profile.requested.fps,
                    "exposure": profile.requested.exposure,
                    "gain": profile.requested.gain,
                    "white_balance": profile.requested.white_balance,
                    "auto_exposure": profile.requested.auto_exposure,
                },
                "observed_width": profile.observed_width,
                "observed_height": profile.observed_height,
                "observed_fps": profile.observed_fps,
                "backend": profile.backend,
                "opened": profile.opened,
                "notes": list(profile.notes),
            }
            for source_id, profile in profiles.items()
        }
        if self._latest_batch is not None:
            sync = assess_batch_synchronization(self._latest_batch)
            metadata["synchronization"] = {
                "policy": "software_timestamp",
                "status": sync.status,
                "timestamp_spread_ms": sync.timestamp_spread_ms,
                "frame_index_spread": sync.frame_index_spread,
                "notes": list(sync.notes),
            }
        video_files: dict[str, str] = {}
        if recording_stats is not None:
            video_files = dict(recording_stats.video_files)
            metadata["recording"] = {
                "started_at_iso": recording_stats.started_at_iso,
                "stopped_at_iso": recording_stats.stopped_at_iso,
                "batches_written": recording_stats.batches_written,
                "dropped_batches": recording_stats.dropped_batches,
                "frames_written_by_source": dict(recording_stats.frames_written_by_source),
                "dropped_sources": dict(recording_stats.dropped_sources),
                "frame_log_file": recording_stats.frame_log_file,
                "resource_snapshots": {
                    label: {
                        "disk_total_gb": snapshot.disk_total_gb,
                        "disk_free_gb": snapshot.disk_free_gb,
                        "disk_used_percent": snapshot.disk_used_percent,
                        "memory_used_percent": snapshot.memory_used_percent,
                        "notes": list(snapshot.notes),
                    }
                    for label, snapshot in recording_stats.resource_snapshots.items()
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
            video_files=video_files,
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
        self._latest_recording_stats = None
        self._probe_results = {}
        self._active_sources = list(manifest.sources)

        self._session_panel.set_session_id(manifest.session_id)
        self._session_panel.set_notes(manifest.notes)
        self._session_panel.set_loaded_session_dir(str(session_dir))
        self._session_panel.set_active_session_dir(str(session_dir))
        self._session_panel.set_manifest_path(str(manifest_path))
        self._session_panel.set_manifest(manifest)
        self._session_panel.set_recording_active(False)

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

        worker = CameraProbeWorker(
            sources,
            requested_width=self._capture_panel.requested_width(),
            requested_height=self._capture_panel.requested_height(),
            requested_fps=self._capture_panel.target_fps(),
            exposure=self._capture_panel.requested_exposure(),
            gain=self._capture_panel.requested_gain(),
            white_balance=self._capture_panel.requested_white_balance(),
        )
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
        capture_mode = self._calibration_panel.capture_mode()
        if self._capture_worker is not None and self._capture_worker.isRunning() and self._latest_batch is not None and self._latest_batch.frames:
            result = self._calibration_manager.capture_frames(
                self._latest_batch.frames,
                record_sample=True,
                capture_mode=capture_mode,
            )
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
        readiness = self._calibration_manager.workflow_readiness()
        self._calibration_panel.set_workflow_readiness(readiness)
        if not readiness.can_solve_intrinsics:
            message = "Intrinsics are not ready to solve yet. " + " ".join(readiness.notes[:3])
            self._calibration_panel.set_state(message)
            self._calibration_panel.append_output(message)
            return

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
        self._update_calibration_readiness_panel()
        self._append_log(f"Calibration intrinsics solve finished: {len(result.solved_sources)} camera(s) solved")

    def _on_solve_calibration_extrinsics(self) -> None:
        self._sync_calibration_geometry()
        readiness = self._calibration_manager.workflow_readiness()
        self._calibration_panel.set_workflow_readiness(readiness)
        if not readiness.can_solve_extrinsics:
            message = "Extrinsics are not ready to solve yet. " + " ".join(readiness.notes[:3])
            self._calibration_panel.set_state(message)
            self._calibration_panel.append_output(message)
            return

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
        self._update_calibration_readiness_panel()
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
        self._last_auto_calibration_capture_sec = 0.0
        self._auto_calibration_capture_pending = False
        self._calibration_panel.set_auto_capture_status("Auto capture off.")
        self._calibration_panel.set_sync_status("Camera sync: waiting for the next sample.")
        self._update_calibration_readiness_panel()
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
        self._review_overlay_cache.clear()
        self._review_preview_panel.set_pipeline_result(None)
        self._status_panel.set_idle()
        self._config.default_detector_name = actual_name
        try:
            self._config.save()
        except OSError as exc:
            LOGGER.warning("Failed to save detector preference: %s", exc)
        self._append_log(f"Detector switched to {actual_name}")
        self.statusBar().showMessage(f"Detector: {actual_name}")
        if self._review_reader is not None:
            self._session_review_panel.set_state(
                f"Detector switched to {actual_name}. Review overlays were cleared for reproducible reprocessing."
            )

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
            requested_width=self._capture_panel.requested_width(),
            requested_height=self._capture_panel.requested_height(),
            requested_fps=target_fps,
            exposure=self._capture_panel.requested_exposure(),
            gain=self._capture_panel.requested_gain(),
            white_balance=self._capture_panel.requested_white_balance(),
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
        self._session_state.recording_active = self._is_recording_active()
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
        if self._recording_worker is not None:
            self._recording_worker.submit_batch(batch)
        self._calibration_worker.submit_batch(
            batch,
            record_sample=capture_sample,
            capture_mode=self._calibration_panel.capture_mode(),
        )
        if self._pipeline_worker.isRunning():
            self._pipeline_worker.submit_batch(batch)

    def _on_calibration_analysis_result(self, outcome: object) -> None:
        if not isinstance(outcome, CalibrationAnalysisOutcome):
            return

        result = outcome.result
        self._latest_calibration_result = result
        if outcome.record_sample:
            self._calibration_capture_pending = False
            self._auto_calibration_capture_pending = False
            self._apply_calibration_capture_result(result)
            self._pending_calibration_sample_frame_index = None
            self._refresh_session_panel()
            return

        self._update_calibration_live_visuals(result)
        self._maybe_auto_capture_calibration_sample(result)

    def _update_calibration_live_visuals(self, result: CalibrationCaptureResult) -> None:
        now = time.monotonic()
        self._set_preview_calibration_detections(result.detections)
        self._camera_grid.set_calibration_detections(result.detections)
        self._calibration_panel.set_sync_status(self._format_sync_status(result.sync_report))
        if result.history_entry is not None or now - self._last_calibration_quality_update_sec >= 1.0:
            self._calibration_panel.set_camera_quality_scores(result.camera_quality_scores)
            self._last_calibration_quality_update_sec = now

    def _maybe_auto_capture_calibration_sample(self, result: CalibrationCaptureResult) -> None:
        if not self._calibration_panel.auto_capture_enabled():
            self._calibration_panel.set_auto_capture_status("Auto capture off.")
            return
        if self._calibration_capture_pending:
            self._calibration_panel.set_auto_capture_status("Auto capture waiting for queued sample.")
            return
        if self._auto_calibration_capture_pending:
            self._calibration_panel.set_auto_capture_status("Auto capture writing accepted sample.")
            return
        if self._latest_batch is None or not self._latest_batch.frames:
            self._calibration_panel.set_auto_capture_status("Auto capture waiting for live frames.")
            return

        now = time.monotonic()
        cooldown = self._calibration_panel.auto_capture_cooldown_sec()
        elapsed = now - self._last_auto_calibration_capture_sec
        if elapsed < cooldown:
            self._calibration_panel.set_auto_capture_status(
                f"Auto capture cooling down ({cooldown - elapsed:.1f}s)."
            )
            return

        capture_mode = self._calibration_panel.capture_mode()
        ready, reason = self._auto_calibration_ready(result, capture_mode)
        if not ready:
            self._calibration_panel.set_auto_capture_status(f"Auto waiting: {reason}")
            return

        self._auto_calibration_capture_pending = True
        self._pending_calibration_sample_frame_index = max(
            (frame.frame_index for frame in self._latest_batch.frames.values()),
            default=0,
        )
        self._last_auto_calibration_capture_sec = now
        self._calibration_worker.submit_batch(
            self._latest_batch,
            record_sample=True,
            capture_mode=capture_mode,
        )
        label = "extrinsics sync set" if capture_mode == "sync_extrinsics" else "intrinsics sample"
        self._calibration_panel.set_auto_capture_status(f"Auto queued {label}.")
        self._append_log(f"Auto calibration capture queued: {label}")

    def _auto_calibration_ready(self, result: CalibrationCaptureResult, capture_mode: str) -> tuple[bool, str]:
        visible_qualities = [quality for quality in result.camera_quality_scores.values() if quality.visible]
        if capture_mode == "sync_extrinsics":
            sync_report = result.sync_report
            if sync_report is None:
                return False, "camera sync is unavailable."
            if sync_report.status != "ready":
                return False, "show the board in at least two synchronized cameras."
            detected_qualities = [
                result.camera_quality_scores[source_id]
                for source_id in sync_report.detected_sources
                if source_id in result.camera_quality_scores and result.camera_quality_scores[source_id].visible
            ]
            if len(detected_qualities) < 2:
                return False, "need two visible board detections."
            weakest_score = min(quality.score for quality in detected_qualities)
            if weakest_score < 55.0:
                return False, f"sync quality too low ({weakest_score:.0f}/100)."
            return True, "sync set is ready."

        strong_qualities = [quality for quality in visible_qualities if quality.score >= 70.0]
        if not strong_qualities:
            return False, "intrinsics needs at least one camera with board quality >= 70/100."
        return True, f"{len(strong_qualities)} camera(s) have strong intrinsics samples."

    def _apply_calibration_capture_result(self, result: CalibrationCaptureResult) -> None:
        self._update_calibration_live_visuals(result)
        self._calibration_panel.set_sample_counts(result.sample_counts, result.synchronized_samples)
        current_history_count = len(self._calibration_manager.sample_history)
        if result.history_entry is not None or current_history_count != self._last_calibration_history_count:
            self._calibration_panel.set_sample_history(self._calibration_manager.sample_history)
            self._last_calibration_history_count = current_history_count
        self._update_calibration_readiness_panel()
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
        if result.capture_mode == "intrinsics":
            if detected:
                return f"Intrinsics sample stored for {detected}/{total} visible camera(s)."
            return "Intrinsics sample not stored: no calibration board visible."

        if sync_report.status == "ready":
            return f"Extrinsics sync set ready: {detected}/{total} cameras saw the board in sync."
        if sync_report.status == "partial":
            return f"Extrinsics candidate partial: {detected}/{total} cameras saw the board."
        return "Extrinsics sample not ready yet: show the chessboard in at least two cameras."

    def _sync_calibration_geometry(self) -> None:
        self._calibration_manager.set_board_geometry(
            self._calibration_panel.board_shape(),
            self._calibration_panel.square_size_m(),
        )

    def _update_calibration_readiness_panel(self) -> None:
        self._calibration_panel.set_workflow_readiness(self._calibration_manager.workflow_readiness())

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
            self._update_calibration_readiness_panel()
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
        self._update_calibration_readiness_panel()
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
            fps_text = f", fps={probe.fps:.1f}" if probe.fps > 0 else ""
            controls = ", ".join(name for name, applied in probe.control_status.items() if applied)
            control_text = f", controls={controls}" if controls else ""
            lines.append(
                f"- {source_id} ({label}): {status}, backend={probe.backend}, "
                f"size={probe.width}x{probe.height}{fps_text}{control_text}"
            )
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
        if self._is_recording_active():
            self._stop_recording_worker(save_manifest=True, state_message="Session recording saved")
        self._capture_worker = None
        self._capture_panel.set_running(False)
        self._session_state.recording_active = False
        self._current_capture_batch_limit = None
        self._calibration_capture_pending = False
        self._auto_calibration_capture_pending = False
        self._pending_calibration_sample_frame_index = None
        self._refresh_session_panel()
        if self._capture_panel.source_csv():
            self._capture_panel.set_state("Idle")
        self.statusBar().showMessage("Idle")

    def _stop_capture_worker(self) -> None:
        if self._capture_worker is None:
            return
        if self._is_recording_active():
            self._stop_recording_worker(save_manifest=True, state_message="Session recording saved")
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
        self._auto_calibration_capture_pending = False
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

    def _stop_motion_take_worker(self) -> None:
        if self._motion_take_worker is None:
            return
        if not self._motion_take_worker.wait(1000):
            LOGGER.warning("Motion take worker did not stop in time; forcing termination.")
            self._motion_take_worker.terminate()
            self._motion_take_worker.wait(1000)
        self._motion_take_worker = None
        self._session_review_panel.set_session_processing_running(False)

    def _stop_pose_export_worker(self) -> None:
        if self._pose_export_worker is None:
            return
        if not self._pose_export_worker.wait(1000):
            LOGGER.warning("Pose export worker did not stop in time; forcing termination.")
            self._pose_export_worker.terminate()
            self._pose_export_worker.wait(1000)
        self._pose_export_worker = None
        self._session_review_panel.set_export_running(False)

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
        self._stop_recording_worker(save_manifest=True, state_message="Session recording saved on shutdown")
        self._stop_motion_take_worker()
        self._stop_pose_export_worker()
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
