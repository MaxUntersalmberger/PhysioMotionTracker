from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from mocap_app.analysis.session_analysis import SessionAnalysisReport
from mocap_app.core.config import AppConfig
from mocap_app.io.calibration_io import CalibrationManager, CalibrationRepository, ChessboardDetectionResult
from mocap_app.io.session_io import SessionLoader, SessionRecorder
from mocap_app.models.types import (
    CalibrationBundle,
    CameraProbeResult,
    CameraSourceConfig,
    FramePacket,
    PipelineResult,
    RuntimeTuning,
    SessionManifest,
)
from mocap_app.pipeline.detection import create_pose_detector
from mocap_app.pipeline.manager import MocapPipeline
from mocap_app.ui.qt_logging import QtSignalLogHandler
from mocap_app.ui.widgets.analysis_workspace import AnalysisWorkspaceWidget
from mocap_app.ui.widgets.calibration_panel import CalibrationPanelWidget
from mocap_app.ui.widgets.capture_workspace import CaptureWorkspaceWidget
from mocap_app.ui.widgets.diagnostics_panel import DiagnosticsPanelWidget
from mocap_app.ui.widgets.reconstruction_workspace import ReconstructionWorkspaceWidget
from mocap_app.workers.capture_worker import LiveCaptureWorker
from mocap_app.workers.camera_probe_worker import CameraProbeWorker
from mocap_app.workers.pipeline_worker import PipelineWorker
from mocap_app.workers.playback_worker import SessionPlaybackWorker


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    TAB_CAPTURE = 0
    TAB_CALIBRATION = 1
    TAB_RECONSTRUCTION = 2
    TAB_ANALYSIS = 3
    TAB_DIAGNOSTICS = 4

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

        self._pipeline = self._build_pipeline(prefer_mediapipe=config.use_mediapipe_by_default)
        self._session_recorder = SessionRecorder()
        self._session_loader = SessionLoader()
        self._calibration_repo = CalibrationRepository()
        self._calibration_manager = CalibrationManager()
        self._calibration_path = self._config.calibration_dir / "current_calibration.json"
        self._current_calibration_bundle: CalibrationBundle | None = None
        self._calibration_loaded = False
        self._calibration_pattern = self._calibration_manager.default_pattern
        self._latest_calibration_detections: dict[str, ChessboardDetectionResult] = {}
        self._last_calibration_preview_at = 0.0
        self._calibration_preview_interval_sec = 0.25
        self._last_calibration_panel_refresh_at = 0.0
        self._calibration_panel_refresh_interval_sec = 0.35
        self._last_calibration_auto_capture_at = 0.0

        self._live_worker: LiveCaptureWorker | None = None
        self._camera_probe_worker: CameraProbeWorker | None = None
        self._playback_worker: SessionPlaybackWorker | None = None
        self._pipeline_worker: PipelineWorker | None = None
        self._loaded_session_dir: Path | None = None
        self._loaded_manifest: SessionManifest | None = None
        self._analysis_video_paths: dict[str, Path] = {}
        self._analysis_total_frames: int = 0
        self._analysis_current_frame_index: int = 0
        self._analysis_report: SessionAnalysisReport | None = None

        self._active_sources: list[CameraSourceConfig] = []
        self._runtime_tuning = RuntimeTuning()
        self._latest_frames: dict[str, FramePacket] = {}
        self._latest_pipeline_result: PipelineResult | None = None
        self._camera_timestamp_windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=90))
        self._frame_counter = 0
        self._fps_history: deque[float] = deque(maxlen=90)

        self._diag_cameras_active = 0
        self._diag_matched_keypoints = 0
        self._diag_triangulation_status = "Idle"
        self._diag_triangulator_engine = self._pipeline.triangulator_name
        self._diag_reconstruction_mode = "unavailable"
        self._diag_reconstructed_keypoints = 0
        self._diag_mean_reprojection_error_px: float | None = None
        self._diag_fps = 0.0
        self._diag_capture_latency_ms: float | None = None
        self._diag_detection_ms = 0.0
        self._diag_matching_ms = 0.0
        self._diag_triangulation_ms = 0.0
        self._diag_smoothing_ms = 0.0
        self._diag_pipeline_ms = 0.0
        self._diag_overlay_ms = 0.0
        self._diag_display_ms = 0.0
        self._diag_per_camera_fps: dict[str, float] = {}
        self._diag_dropped_input_batches = 0

        self._capture_workspace = CaptureWorkspaceWidget(
            default_camera_csv=self._config.default_camera_csv,
            default_fps=self._config.target_fps,
            default_use_mediapipe=self._config.use_mediapipe_by_default,
        )
        self._runtime_tuning = self._capture_workspace.runtime_tuning()
        self._calibration_preview_interval_sec = 1.0 / max(self._runtime_tuning.calibration_detection_hz, 0.1)
        self._calibration_panel = CalibrationPanelWidget()
        self._calibration_panel.set_pattern_options(
            pattern_names=self._calibration_manager.available_patterns(),
            selected=self._calibration_pattern,
        )
        self._calibration_panel.set_workflow_mode("intrinsics")
        self._calibration_panel.set_sync_threshold_values(
            min_quality=self._calibration_manager.sync_min_quality_score,
            min_coverage_ratio=self._calibration_manager.sync_min_coverage_ratio,
        )
        self._reconstruction_workspace = ReconstructionWorkspaceWidget()
        self._analysis_workspace = AnalysisWorkspaceWidget()
        self._diagnostics_panel = DiagnosticsPanelWidget()
        self._tabs = QTabWidget()
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._on_display_tick)

        self._qt_log_handler = QtSignalLogHandler()
        self._attach_logging_panel()
        self._setup_ui()
        self._apply_window_style()
        self._connect_signals()
        self._start_pipeline_worker()
        self._load_existing_calibration()
        self._seed_startup_source_slots()
        self._refresh_diagnostics()
        self._refresh_calibration_panel(force=True)
        self._set_display_timer_hz(self._runtime_tuning.preview_fps)

        self.setWindowTitle(self._config.app_name)
        self.resize(1840, 1020)
        self._set_status("Ready")

    def _attach_logging_panel(self) -> None:
        self._qt_log_handler.emitter.record_emitted.connect(self._diagnostics_panel.append_log_record)
        logging.getLogger().addHandler(self._qt_log_handler)

    def _setup_ui(self) -> None:
        self._tabs.addTab(self._capture_workspace, "Capture")
        self._tabs.addTab(self._calibration_panel, "Calibration")
        self._tabs.addTab(self._reconstruction_workspace, "Reconstruction")
        self._tabs.addTab(self._analysis_workspace, "Analysis")
        self._tabs.addTab(self._diagnostics_panel, "Diagnostics")
        self.setCentralWidget(self._tabs)
        self.statusBar().showMessage("Idle")

    def _apply_window_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f4f7fb;
            }
            QStatusBar {
                background-color: #e9eef5;
                color: #1f2937;
            }
            QTabWidget::pane {
                border: 1px solid #c8d3e1;
                top: -1px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #e8eff8;
                color: #1f2937;
                padding: 8px 14px;
                border: 1px solid #c8d3e1;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
            }
            """
        )

    def _connect_signals(self) -> None:
        self._capture_workspace.start_live_requested.connect(self._on_start_live)
        self._capture_workspace.stop_live_requested.connect(self._on_stop_live)
        self._capture_workspace.start_recording_requested.connect(self._on_start_recording)
        self._capture_workspace.stop_recording_requested.connect(self._on_stop_recording)
        self._capture_workspace.runtime_tuning_changed.connect(self._on_runtime_tuning_changed)
        self._capture_workspace.probe_cameras_requested.connect(self._on_probe_cameras)
        self._capture_workspace.ui_message.connect(self._show_warning)

        self._calibration_panel.capture_requested.connect(self._on_capture_calibration)
        self._calibration_panel.solve_requested.connect(self._on_solve_calibration)
        self._calibration_panel.solve_extrinsics_requested.connect(self._on_solve_extrinsics)
        self._calibration_panel.reset_requested.connect(self._on_reset_calibration_samples)
        self._calibration_panel.save_profile_requested.connect(self._on_save_calibration_profile)
        self._calibration_panel.load_profile_requested.connect(self._on_load_calibration_profile)
        self._calibration_panel.undistort_toggled.connect(self._on_undistort_toggle_changed)
        self._calibration_panel.pattern_changed.connect(self._on_calibration_pattern_changed)
        self._calibration_panel.sync_thresholds_changed.connect(self._on_sync_thresholds_changed)
        self._calibration_panel.workflow_mode_changed.connect(self._on_calibration_workflow_mode_changed)

        self._analysis_workspace.load_session_requested.connect(self._on_load_session)
        self._analysis_workspace.play_requested.connect(self._on_start_playback)
        self._analysis_workspace.pause_requested.connect(self._on_pause_playback)
        self._analysis_workspace.stop_requested.connect(self._on_stop_playback)
        self._analysis_workspace.step_backward_requested.connect(lambda: self._step_loaded_session_frame(-1))
        self._analysis_workspace.step_forward_requested.connect(lambda: self._step_loaded_session_frame(1))
        self._analysis_workspace.seek_requested.connect(self._seek_loaded_session_frame)
        self._analysis_workspace.export_report_requested.connect(self._on_export_analysis_report)

        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _build_pipeline(self, prefer_mediapipe: bool) -> MocapPipeline:
        detector = create_pose_detector(prefer_mediapipe=prefer_mediapipe)
        return MocapPipeline(detector=detector)

    def _start_pipeline_worker(self) -> None:
        self._stop_pipeline_worker()
        worker = PipelineWorker(self._pipeline)
        worker.result_ready.connect(self._on_pipeline_result)
        worker.state_changed.connect(lambda state: LOGGER.info("Pipeline worker state: %s", state))
        worker.error.connect(self._on_worker_error)
        self._pipeline_worker = worker
        worker.start()

    def _stop_pipeline_worker(self) -> None:
        if self._pipeline_worker is None:
            return
        self._pipeline_worker.stop()
        if not self._pipeline_worker.wait(2500):
            LOGGER.warning("Pipeline worker did not stop in time; forcing termination.")
            self._pipeline_worker.terminate()
            self._pipeline_worker.wait(1000)
        self._pipeline_worker = None

    def _stop_camera_probe_worker(self) -> None:
        if self._camera_probe_worker is None:
            return
        self._camera_probe_worker.stop()
        if not self._camera_probe_worker.wait(2500):
            LOGGER.warning("Camera probe worker did not stop in time; forcing termination.")
            self._camera_probe_worker.terminate()
            self._camera_probe_worker.wait(1000)
        self._camera_probe_worker = None
        self._capture_workspace.set_camera_probe_running(False)

    def _on_probe_cameras(self, max_index: int) -> None:
        self._stop_camera_probe_worker()
        worker = CameraProbeWorker(max_index=max_index)
        worker.result_ready.connect(self._on_camera_probe_result)
        worker.error.connect(self._on_worker_error)
        worker.state_changed.connect(lambda state: LOGGER.info("Camera probe state: %s", state))
        worker.finished.connect(self._on_camera_probe_finished)
        self._camera_probe_worker = worker
        self._capture_workspace.set_camera_probe_running(True)
        worker.start()
        self._set_status(f"Scanning cameras 0..{max_index} ...")

    def _on_camera_probe_result(self, payload: object) -> None:
        self._capture_workspace.set_camera_probe_running(False)
        cameras = payload if isinstance(payload, list) else []
        results: list[CameraProbeResult] = []
        for item in cameras:
            if isinstance(item, CameraProbeResult):
                results.append(item)
        self._capture_workspace.set_detected_cameras(results)
        if results:
            self._set_status(f"Detected {len(results)} camera(s).")
        else:
            self._set_status("No cameras detected in probed range.")

    def _on_camera_probe_finished(self) -> None:
        self._capture_workspace.set_camera_probe_running(False)
        self._camera_probe_worker = None

    def _set_display_timer_hz(self, hz: float) -> None:
        safe_hz = max(1.0, hz)
        interval_ms = max(8, int(1000.0 / safe_hz))
        self._display_timer.setInterval(interval_ms)
        if not self._display_timer.isActive():
            self._display_timer.start()

    def _on_runtime_tuning_changed(self, tuning_obj: object) -> None:
        if not isinstance(tuning_obj, RuntimeTuning):
            return
        self._runtime_tuning = tuning_obj
        self._set_display_timer_hz(tuning_obj.preview_fps)
        self._calibration_preview_interval_sec = 1.0 / max(tuning_obj.calibration_detection_hz, 0.1)

    def _should_run_detection_for_current_tab(self) -> bool:
        index = self._tabs.currentIndex()
        if index == self.TAB_CAPTURE:
            return self._runtime_tuning.detection_capture_enabled
        if index == self.TAB_RECONSTRUCTION:
            return self._runtime_tuning.detection_reconstruction_enabled
        if index == self.TAB_ANALYSIS:
            return self._runtime_tuning.detection_analysis_enabled
        return False

    def _compute_per_camera_fps(self) -> dict[str, float]:
        fps_map: dict[str, float] = {}
        for source_id, window in self._camera_timestamp_windows.items():
            if len(window) < 2:
                continue
            elapsed = window[-1] - window[0]
            if elapsed <= 0:
                continue
            fps_map[source_id] = (len(window) - 1) / elapsed
        return fps_map

    def _submit_pipeline_batch(self, frames: dict[str, FramePacket], force_detection: bool | None = None) -> None:
        if not frames:
            return
        run_detection = self._should_run_detection_for_current_tab() if force_detection is None else force_detection
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.submit_batch(frames=frames, run_detection=run_detection)
            return

        # Safety fallback path (should rarely execute).
        try:
            result = self._pipeline.process(frames, run_detection=run_detection)
            self._on_pipeline_result(result)
        except Exception as exc:
            LOGGER.exception("Fallback processing failed.")
            self._on_worker_error(str(exc))

    def _seed_startup_source_slots(self) -> None:
        try:
            sources = self._capture_workspace.current_sources()
        except ValueError:
            sources = []

        if not sources:
            sources = [
                CameraSourceConfig(source_id="cam0", kind="webcam", uri=0, label="Webcam 0"),
                CameraSourceConfig(source_id="cam1", kind="webcam", uri=1, label="Webcam 1"),
            ]

        self._active_sources = sources
        source_ids = [source.source_id for source in sources]
        self._capture_workspace.camera_grid.set_sources(source_ids)
        self._reconstruction_workspace.set_sources(source_ids)
        self._calibration_panel.set_sources(source_ids)
        self._refresh_capture_status()

    def _load_existing_calibration(self) -> None:
        bundle = self._calibration_repo.load(self._calibration_path)
        self._set_current_calibration_bundle(bundle)
        if bundle is not None:
            self._set_status(f"Loaded calibration: {self._calibration_path.name}")

    def _set_current_calibration_bundle(self, bundle: CalibrationBundle | None) -> None:
        self._current_calibration_bundle = bundle
        self._calibration_loaded = bundle is not None
        self._pipeline.update_calibration(bundle)
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.update_calibration(bundle)
        self._refresh_diagnostics()
        self._refresh_calibration_panel(force=True)

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Mocap Studio", message)

    def _show_error(self, message: str) -> None:
        LOGGER.error(message)
        QMessageBox.critical(self, "Mocap Studio", message)
        self._set_status(message)

    def _refresh_capture_status(self) -> None:
        live_active = self._live_worker is not None and self._live_worker.isRunning()
        self._capture_workspace.set_runtime_status(
            live_active=live_active,
            active_cameras=self._diag_cameras_active,
            detector_name=self._pipeline.detector_name,
            recording_active=self._session_recorder.active,
        )

    def _refresh_diagnostics(self) -> None:
        kwargs = dict(
            cameras_active=self._diag_cameras_active,
            detector_active=self._pipeline.detector_name,
            calibration_loaded=self._calibration_loaded,
            triangulator_engine=self._diag_triangulator_engine,
            reconstruction_mode=self._diag_reconstruction_mode,
            matched_keypoints=self._diag_matched_keypoints,
            reconstructed_keypoints=self._diag_reconstructed_keypoints,
            mean_reprojection_error_px=self._diag_mean_reprojection_error_px,
            triangulation_status=self._diag_triangulation_status,
            fps=self._diag_fps,
            capture_latency_ms=self._diag_capture_latency_ms,
            detection_ms=self._diag_detection_ms,
            matching_ms=self._diag_matching_ms,
            triangulation_ms=self._diag_triangulation_ms,
            smoothing_ms=self._diag_smoothing_ms,
            pipeline_ms=self._diag_pipeline_ms,
            overlay_ms=self._diag_overlay_ms,
            display_ms=self._diag_display_ms,
            per_camera_fps=self._diag_per_camera_fps,
            dropped_input_batches=self._diag_dropped_input_batches,
        )
        self._diagnostics_panel.update_pipeline_metrics(**kwargs)
        self._reconstruction_workspace.update_status_panel(**kwargs)
        self._reconstruction_workspace.set_reconstruction_metadata(
            mode=self._diag_reconstruction_mode,
            reconstructed_joints=self._diag_reconstructed_keypoints,
            mean_reprojection_error_px=self._diag_mean_reprojection_error_px,
            triangulation_status=self._diag_triangulation_status,
        )
        self._refresh_capture_status()

    def _reset_runtime_metrics(self) -> None:
        self._diag_matched_keypoints = 0
        self._diag_fps = 0.0
        self._diag_triangulation_status = "Idle"
        self._diag_reconstruction_mode = "unavailable"
        self._diag_reconstructed_keypoints = 0
        self._diag_mean_reprojection_error_px = None
        self._diag_capture_latency_ms = None
        self._diag_detection_ms = 0.0
        self._diag_matching_ms = 0.0
        self._diag_triangulation_ms = 0.0
        self._diag_smoothing_ms = 0.0
        self._diag_pipeline_ms = 0.0
        self._diag_overlay_ms = 0.0
        self._diag_display_ms = 0.0
        self._diag_per_camera_fps = {}
        self._diag_dropped_input_batches = 0
        self._latest_pipeline_result = None
        self._reconstruction_workspace.set_reconstruction_metadata(
            mode=self._diag_reconstruction_mode,
            reconstructed_joints=self._diag_reconstructed_keypoints,
            mean_reprojection_error_px=self._diag_mean_reprojection_error_px,
            triangulation_status=self._diag_triangulation_status,
        )
        self._fps_history.clear()
        self._refresh_diagnostics()

    def _active_source_ids(self) -> list[str]:
        if self._active_sources:
            return [source.source_id for source in self._active_sources]
        if self._latest_frames:
            return sorted(self._latest_frames.keys())
        if self._loaded_manifest:
            return sorted(self._loaded_manifest.video_files.keys())
        return []

    def _refresh_calibration_panel(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self._last_calibration_panel_refresh_at < self._calibration_panel_refresh_interval_sec:
            return

        source_ids = self._active_source_ids()
        self._calibration_panel.set_sources(source_ids)
        sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)
        sample_breakdown = self._calibration_manager.observations_breakdown_summary()
        self._calibration_panel.update_camera_status_table(
            source_ids=source_ids,
            sample_counts=sample_counts,
            sample_breakdown=sample_breakdown,
            bundle=self._current_calibration_bundle,
            live_detection=self._latest_calibration_detections,
        )

        mode = self._calibration_workflow_mode()
        warnings: list[str] = []
        for source_id in source_ids:
            if mode == "sync_extrinsics":
                sync_count_for_source = int(sample_breakdown.get(source_id, {}).get("synchronized", 0))
                if sync_count_for_source < 3:
                    warnings.append(
                        f"{source_id}: too few synchronized sets ({sync_count_for_source}/3). "
                        "Extrinsics may be unstable."
                    )
            else:
                count = sample_counts.get(source_id, 0)
                if count < self._calibration_manager.min_samples_per_camera:
                    warnings.append(
                        f"{source_id}: too few frames ({count}/{self._calibration_manager.min_samples_per_camera})."
                    )
        if self._current_calibration_bundle:
            warnings.extend(self._current_calibration_bundle.notes)
        if self._calibration_pattern == "charuco" and "charuco" not in self._calibration_manager.available_patterns():
            warnings.append("Charuco selected but cv2.aruco is unavailable in current OpenCV build.")
        sync_count = self._calibration_manager.synchronized_capture_count()
        if sync_count > 0:
            warnings.append(f"Synchronized capture sets stored: {sync_count}.")
        if mode == "sync_extrinsics":
            warnings.append(
                "Workflow mode: Sync / Extrinsics. Captures are stored only when >=2 cameras see a valid board."
            )
        else:
            warnings.append(
                "Workflow mode: Intrinsics. Captures are stored per camera using strict intrinsics thresholds."
            )
        warnings.append(
            "Synchronized capture thresholds: "
            f"quality >= {self._calibration_manager.sync_min_quality_score:.2f}, "
            f"coverage >= {self._calibration_manager.sync_min_coverage_ratio * 100.0:.1f}%."
        )
        self._calibration_panel.show_warnings(list(dict.fromkeys(warnings)))
        if self._calibration_panel.auto_capture_enabled():
            self._calibration_panel.set_auto_capture_status(self._auto_capture_idle_text())
        else:
            self._calibration_panel.set_auto_capture_status("Auto capture off.")
        self._last_calibration_panel_refresh_at = now

    def _calibration_workflow_mode(self) -> str:
        return self._calibration_panel.current_workflow_mode()

    def _auto_capture_idle_text(self) -> str:
        if self._calibration_workflow_mode() == "sync_extrinsics":
            return "Auto capture armed (sync mode). Hold the board visible in at least 2 cameras."
        return "Auto capture armed (intrinsics mode). Move the board through new per-camera poses."

    def _update_calibration_preview(self, force: bool = False) -> None:
        if not self._latest_frames:
            return
        if not force and self._tabs.currentIndex() != self.TAB_CALIBRATION:
            return
        now = time.perf_counter()
        if not force and now - self._last_calibration_preview_at < self._calibration_preview_interval_sec:
            return

        sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)
        previews: dict[str, Any] = {}
        detections: dict[str, ChessboardDetectionResult] = {}

        for source_id, frame in self._latest_frames.items():
            preview = frame.frame_bgr
            if self._calibration_panel.undistort_enabled_for(source_id):
                preview = self._calibration_manager.undistort_frame(
                    source_id=source_id,
                    frame_bgr=preview,
                    bundle=self._current_calibration_bundle,
                )
            detection = self._calibration_manager.detect_pattern(
                source_id=source_id,
                frame_bgr=preview,
                pattern=self._calibration_pattern,
            )
            detections[source_id] = detection
            previews[source_id] = self._calibration_manager.draw_detection_overlay(preview, detection=detection)

        self._latest_calibration_detections = detections
        if self._maybe_auto_capture_calibration(detections):
            self._last_calibration_preview_at = now
            return
        sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)
        self._calibration_panel.update_previews(previews, detections, sample_counts)
        self._refresh_calibration_panel()
        self._last_calibration_preview_at = now

    def _on_start_live(
        self,
        sources: list[CameraSourceConfig],
        target_fps: float,
        prefer_mediapipe: bool,
    ) -> None:
        self._on_stop_playback()
        self._on_stop_live()
        self._stop_camera_probe_worker()
        self._on_runtime_tuning_changed(self._capture_workspace.runtime_tuning())

        self._stop_pipeline_worker()
        self._pipeline.shutdown()
        self._pipeline = self._build_pipeline(prefer_mediapipe=prefer_mediapipe)
        self._pipeline.update_calibration(self._current_calibration_bundle)
        self._diag_triangulator_engine = self._pipeline.triangulator_name
        self._start_pipeline_worker()

        self._active_sources = sources
        self._latest_frames.clear()
        source_ids = [source.source_id for source in sources]
        self._capture_workspace.camera_grid.set_sources(source_ids)
        self._reconstruction_workspace.set_sources(source_ids)
        self._calibration_panel.set_sources(source_ids)

        self._diag_cameras_active = len(sources)
        self._reset_runtime_metrics()

        worker = LiveCaptureWorker(
            sources=sources,
            target_fps=self._runtime_tuning.capture_fps if self._runtime_tuning.capture_fps > 0 else target_fps,
            max_frame_width=self._runtime_tuning.preview_max_width,
            requested_width=self._runtime_tuning.capture_width,
            requested_height=self._runtime_tuning.capture_height,
        )
        worker.batch_ready.connect(self._on_frame_batch)
        worker.state_changed.connect(self._set_status)
        worker.error.connect(self._on_worker_error)
        self._live_worker = worker
        worker.start()
        self._refresh_capture_status()
        self._set_status(
            f"Starting live capture ({len(sources)} sources, "
            f"{self._runtime_tuning.capture_fps:.1f} FPS, "
            f"capture={self._runtime_tuning.capture_width or 'auto'}x{self._runtime_tuning.capture_height or 'auto'}, "
            f"preview<= {self._runtime_tuning.preview_max_width or 'auto'})..."
        )

    def _on_stop_live(self) -> None:
        if self._live_worker is None:
            return
        self._live_worker.stop()
        if not self._live_worker.wait(3000):
            LOGGER.warning("Live capture worker did not stop in time; forcing termination.")
            self._live_worker.terminate()
            self._live_worker.wait(1000)
        self._live_worker = None
        self._camera_timestamp_windows.clear()
        self._latest_frames.clear()
        self._latest_pipeline_result = None
        self._diag_cameras_active = 0
        self._reset_runtime_metrics()
        self._refresh_capture_status()
        self._set_status("Live capture stopped")

    def _on_start_recording(self) -> None:
        if self._session_recorder.active:
            self._set_status("Recording already active")
            return
        if self._live_worker is None:
            self._show_warning("Start live capture before recording.")
            return

        sources = self._active_sources or [
            CameraSourceConfig(source_id=source_id, kind="webcam", uri=source_id)
            for source_id in sorted(self._latest_frames.keys())
        ]
        session_dir = self._session_recorder.start_session(
            root_dir=self._config.sessions_dir,
            fps=self._capture_workspace.target_fps(),
            sources=sources,
            calibration_file=self._calibration_path.name if self._calibration_path.exists() else None,
        )
        self._refresh_capture_status()
        self._set_status(f"Recording to {session_dir.name}")

    def _on_stop_recording(self) -> None:
        session_dir = self._session_recorder.stop_session()
        self._refresh_capture_status()
        if session_dir is None:
            self._set_status("Recording is not active")
            return
        self._set_status(f"Recording saved: {session_dir}")

    def _on_load_session(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Session Directory",
            str(self._config.sessions_dir),
        )
        if not selected:
            return

        session_dir = Path(selected)
        try:
            manifest = self._session_loader.load_manifest(session_dir)
            video_paths = self._session_loader.resolve_video_paths(session_dir, manifest)
        except Exception as exc:
            self._show_error(str(exc))
            return

        self._loaded_session_dir = session_dir
        self._loaded_manifest = manifest
        self._analysis_video_paths = video_paths
        self._analysis_total_frames = self._compute_total_frames(video_paths, manifest.total_frames)
        self._analysis_current_frame_index = 0
        self._analysis_report = self._session_loader.load_analysis_report(session_dir, manifest)
        self._analysis_workspace.set_timeline_limits(self._analysis_total_frames)
        self._analysis_workspace.update_playback_progress(0, self._analysis_total_frames)
        self._analysis_workspace.set_analysis_report(self._analysis_report)

        source_ids = sorted(manifest.video_files.keys())
        self._capture_workspace.camera_grid.set_sources(source_ids)
        self._reconstruction_workspace.set_sources(source_ids)
        self._calibration_panel.set_sources(source_ids)
        self._diag_cameras_active = len(manifest.video_files)
        self._reset_runtime_metrics()
        self._refresh_calibration_panel(force=True)
        self._set_status(f"Loaded session: {manifest.session_id}")

    def _compute_total_frames(self, video_paths: dict[str, Path], hint_total: int) -> int:
        if hint_total > 0:
            return hint_total
        frame_counts: list[int] = []
        for path in video_paths.values():
            capture = cv2.VideoCapture(str(path))
            if capture.isOpened():
                frame_counts.append(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            capture.release()
        valid = [count for count in frame_counts if count > 0]
        return min(valid) if valid else 0

    def _on_start_playback(self) -> None:
        if self._playback_worker is not None and self._playback_worker.isRunning():
            self._playback_worker.resume()
            self._set_status("Playback resumed")
            return

        if self._loaded_session_dir is None or self._loaded_manifest is None:
            self._show_warning("Load a session first in the Analysis tab.")
            return

        self._on_stop_live()
        self._on_stop_playback()

        if not self._analysis_video_paths:
            try:
                self._analysis_video_paths = self._session_loader.resolve_video_paths(
                    self._loaded_session_dir,
                    self._loaded_manifest,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return

        self._diag_cameras_active = len(self._analysis_video_paths)
        self._reset_runtime_metrics()

        worker = SessionPlaybackWorker(
            video_paths=self._analysis_video_paths,
            fps=self._loaded_manifest.fps,
            loop=self._analysis_workspace.playback_loop_enabled(),
        )
        worker.batch_ready.connect(self._on_frame_batch)
        worker.progress.connect(self._on_playback_progress)
        worker.state_changed.connect(self._set_status)
        worker.error.connect(self._on_worker_error)
        self._playback_worker = worker
        worker.start()
        self._set_status("Playback started")

    def _on_playback_progress(self, frame_index: int, total_frames: int) -> None:
        self._analysis_current_frame_index = frame_index
        total = total_frames if total_frames > 0 else self._analysis_total_frames
        if total > 0:
            self._analysis_total_frames = total
        self._analysis_workspace.update_playback_progress(frame_index, self._analysis_total_frames)

    def _on_pause_playback(self) -> None:
        if self._playback_worker is None:
            return
        self._playback_worker.pause()
        self._set_status("Playback paused")

    def _on_stop_playback(self) -> None:
        if self._playback_worker is None:
            return
        self._playback_worker.stop()
        if not self._playback_worker.wait(2500):
            LOGGER.warning("Playback worker did not stop in time; forcing termination.")
            self._playback_worker.terminate()
            self._playback_worker.wait(1000)
        self._playback_worker = None
        self._camera_timestamp_windows.clear()
        self._latest_frames.clear()
        self._latest_pipeline_result = None
        self._diag_fps = 0.0
        self._diag_triangulation_status = "Idle"
        self._diag_reconstruction_mode = "unavailable"
        self._diag_reconstructed_keypoints = 0
        self._diag_mean_reprojection_error_px = None
        self._reconstruction_workspace.set_reconstruction_metadata(
            mode=self._diag_reconstruction_mode,
            reconstructed_joints=self._diag_reconstructed_keypoints,
            mean_reprojection_error_px=self._diag_mean_reprojection_error_px,
            triangulation_status=self._diag_triangulation_status,
        )
        self._refresh_diagnostics()
        self._set_status("Playback stopped")

    def _step_loaded_session_frame(self, delta: int) -> None:
        if self._playback_worker is not None and self._playback_worker.isRunning():
            self._show_warning("Pause/stop playback before manual frame stepping.")
            return
        target = self._analysis_current_frame_index + delta
        self._seek_loaded_session_frame(target)

    def _seek_loaded_session_frame(self, frame_index: int) -> None:
        if not self._analysis_video_paths:
            self._show_warning("Load a session first.")
            return

        if self._analysis_total_frames > 0:
            frame_index = max(0, min(frame_index, self._analysis_total_frames - 1))
        else:
            frame_index = max(0, frame_index)

        batch = self._read_session_frame_batch(frame_index)
        if batch is None:
            self._show_warning("Could not seek to requested frame.")
            return

        self._analysis_current_frame_index = frame_index
        self._process_pipeline_batch(batch)
        self._analysis_workspace.update_playback_progress(frame_index, self._analysis_total_frames)
        self._set_status(f"Seeked to frame {frame_index}")

    def _on_export_analysis_report(self) -> None:
        if self._analysis_report is None or self._loaded_session_dir is None:
            self._show_warning("Load a session with stored 3D pose data before exporting a report.")
            return

        suggested = self._loaded_session_dir / "analysis_report.json"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Analysis Report",
            str(suggested),
            "JSON (*.json)",
        )
        if not selected:
            return

        output_path = Path(selected)
        output_path.write_text(
            json.dumps(self._analysis_report.to_export_dict(), indent=2),
            encoding="utf-8",
        )
        self._set_status(f"Analysis report saved: {output_path.name}")

    def _read_session_frame_batch(self, frame_index: int) -> dict[str, FramePacket] | None:
        if not self._analysis_video_paths:
            return None

        timestamp_sec = time.time()
        batch: dict[str, FramePacket] = {}
        for source_id, path in self._analysis_video_paths.items():
            capture = cv2.VideoCapture(str(path))
            if not capture.isOpened():
                capture.release()
                return None

            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            capture.release()
            if not ok:
                return None

            batch[source_id] = FramePacket(
                source_id=source_id,
                frame_index=frame_index,
                timestamp_sec=timestamp_sec,
                frame_bgr=frame,
            )
        return batch

    def _build_calibration_preview_frame(
        self,
        source_id: str,
        frame_bgr: Any,
        detection: ChessboardDetectionResult,
        accepted: bool | None = None,
    ) -> Any:
        preview = frame_bgr
        if self._calibration_panel.undistort_enabled_for(source_id):
            preview = self._calibration_manager.undistort_frame(
                source_id=source_id,
                frame_bgr=preview,
                bundle=self._current_calibration_bundle,
            )
        return self._calibration_manager.draw_detection_overlay(
            preview,
            detection=detection,
            accepted=accepted,
        )

    def _apply_calibration_capture_feedback(
        self,
        feedback_by_source: dict[str, Any],
        before_sync_sets: int,
        after_sync_sets: int,
        auto_trigger: bool,
    ) -> bool:
        feedback_messages: list[str] = []
        accepted_total = 0
        preview_frames: dict[str, Any] = {}
        detections: dict[str, ChessboardDetectionResult] = {}
        sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)

        for source_id, frame in self._latest_frames.items():
            feedback = feedback_by_source.get(source_id)
            if feedback is not None:
                feedback_messages.append(feedback.message)
                if feedback.accepted:
                    accepted_total += 1
                detections[source_id] = feedback.detection
                preview_frames[source_id] = self._build_calibration_preview_frame(
                    source_id=source_id,
                    frame_bgr=frame.frame_bgr,
                    detection=feedback.detection,
                    accepted=feedback.accepted,
                )
                continue

            detection = self._latest_calibration_detections.get(source_id)
            if detection is None:
                continue
            detections[source_id] = detection
            preview_frames[source_id] = self._build_calibration_preview_frame(
                source_id=source_id,
                frame_bgr=frame.frame_bgr,
                detection=detection,
                accepted=None,
            )

        if detections:
            self._latest_calibration_detections = detections
        if preview_frames:
            self._calibration_panel.update_previews(preview_frames, detections, sample_counts)
        self._refresh_calibration_panel(force=True)

        if accepted_total > 0:
            sync_suffix = ""
            if after_sync_sets > before_sync_sets:
                sync_suffix = f" Created synchronized set #{after_sync_sets}."
            message = f"Accepted {accepted_total} sample(s). " + " | ".join(feedback_messages) + sync_suffix
            self._set_status(message)
            self._calibration_panel.show_feedback(message, success=True)
            if auto_trigger:
                self._calibration_panel.set_auto_capture_status(
                    f"Last auto capture stored {accepted_total} sample(s)."
                )
                self._last_calibration_auto_capture_at = time.perf_counter()
            return True

        if auto_trigger:
            self._calibration_panel.set_auto_capture_status(self._auto_capture_idle_text())
            return False

        message = "No valid calibration samples accepted. " + " | ".join(feedback_messages)
        self._set_status(message)
        self._calibration_panel.show_feedback(message, success=False)
        return False

    def _capture_calibration_samples(
        self,
        auto_trigger: bool,
        detections: dict[str, ChessboardDetectionResult] | None = None,
    ) -> bool:
        if not self._latest_frames:
            if not auto_trigger:
                self._show_warning("No frames available. Start live capture first.")
            return False

        workflow_mode = self._calibration_workflow_mode()
        before_sync_sets = self._calibration_manager.synchronized_capture_count()
        allow_relaxed_sync = (
            self._calibration_panel.relaxed_sync_enabled() if workflow_mode == "sync_extrinsics" else False
        )
        if workflow_mode == "sync_extrinsics" and len(self._latest_frames) < 2:
            if not auto_trigger:
                self._show_warning("Sync / Extrinsics mode requires at least 2 active camera feeds.")
            return False
        active_detections = (
            {
                source_id: detections[source_id]
                for source_id in self._latest_frames
                if detections is not None and source_id in detections
            }
            if detections
            else {}
        )
        if active_detections:
            feedback_by_source = self._calibration_manager.try_add_detection_set(
                detections_by_source=active_detections,
                pattern=self._calibration_pattern,
                allow_relaxed_sync=allow_relaxed_sync,
                workflow_mode=workflow_mode,
            )
        else:
            feedback_by_source = self._calibration_manager.try_add_observation_set(
                frames_by_source={source_id: frame.frame_bgr for source_id, frame in self._latest_frames.items()},
                pattern=self._calibration_pattern,
                allow_relaxed_sync=allow_relaxed_sync,
                workflow_mode=workflow_mode,
            )
        after_sync_sets = self._calibration_manager.synchronized_capture_count()
        return self._apply_calibration_capture_feedback(
            feedback_by_source=feedback_by_source,
            before_sync_sets=before_sync_sets,
            after_sync_sets=after_sync_sets,
            auto_trigger=auto_trigger,
        )

    def _maybe_auto_capture_calibration(
        self,
        detections: dict[str, ChessboardDetectionResult],
    ) -> bool:
        if not self._calibration_panel.auto_capture_enabled():
            return False
        now = time.perf_counter()
        if now - self._last_calibration_auto_capture_at < self._calibration_panel.auto_capture_cooldown_sec():
            return False
        return self._capture_calibration_samples(auto_trigger=True, detections=detections)

    def _on_capture_calibration(self) -> None:
        detections = self._latest_calibration_detections if self._latest_calibration_detections else None
        self._capture_calibration_samples(auto_trigger=False, detections=detections)

    def _on_solve_calibration(self) -> None:
        bundle = self._calibration_manager.solve_intrinsics()
        self._calibration_repo.save(bundle, self._calibration_path)
        self._set_current_calibration_bundle(bundle)

        solved = [camera for camera in bundle.cameras.values() if camera.status.startswith("solved")]
        mean_reproj = (
            sum(camera.reprojection_error or 0.0 for camera in solved) / len(solved)
            if solved
            else 0.0
        )
        message = (
            f"Calibration solved: {len(solved)}/{len(bundle.cameras)} cameras "
            f"(mean reproj={mean_reproj:.4f}px)."
        )
        self._set_status(message)
        self._calibration_panel.show_feedback(message, success=bool(solved))
        self._refresh_calibration_panel(force=True)
        for note in bundle.notes:
            LOGGER.info("Calibration note: %s", note)

    def _on_solve_extrinsics(self) -> None:
        base_bundle = self._current_calibration_bundle or self._calibration_manager.last_solution()
        if base_bundle is None:
            if not self._calibration_manager.sources():
                self._show_warning("Capture calibration samples first before solving extrinsics.")
                return
            base_bundle = self._calibration_manager.solve_intrinsics()

        reference_source_id = self._active_source_ids()[0] if self._active_source_ids() else None
        bundle = self._calibration_manager.solve_extrinsics(
            base_bundle=base_bundle,
            reference_source_id=reference_source_id,
        )
        self._calibration_repo.save(bundle, self._calibration_path)
        self._set_current_calibration_bundle(bundle)

        solved_sources = [
            source_id
            for source_id, camera in bundle.cameras.items()
            if camera.rotation is not None and camera.translation is not None
        ]
        reference_id = str(bundle.metadata.get("extrinsics_reference_source_id", reference_source_id or "-"))
        message = (
            f"Extrinsics solved for {len(solved_sources)}/{len(bundle.cameras)} camera(s) "
            f"with {reference_id} as reference."
        )
        success = len(solved_sources) >= 2
        self._set_status(message)
        self._calibration_panel.show_feedback(message, success=success)
        self._refresh_calibration_panel(force=True)
        for note in bundle.notes[-6:]:
            LOGGER.info("Extrinsics note: %s", note)

    def _on_reset_calibration_samples(self) -> None:
        self._calibration_manager.reset()
        self._latest_calibration_detections.clear()
        self._refresh_calibration_panel(force=True)
        self._calibration_panel.show_feedback("Calibration samples reset.", success=True)
        self._set_status("Calibration samples reset")

    def _on_save_calibration_profile(self) -> None:
        bundle = self._current_calibration_bundle or self._calibration_manager.last_solution()
        if bundle is None:
            self._show_warning("No solved calibration profile available to save.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save Calibration Profile",
            str(self._config.calibration_dir / "calibration_profile.json"),
            "Calibration JSON (*.json)",
        )
        if not selected:
            return
        path = Path(selected)
        self._calibration_repo.save(bundle, path)
        self._calibration_panel.show_feedback(f"Calibration profile saved to {path}", success=True)
        self._set_status(f"Calibration profile saved: {path.name}")

    def _on_load_calibration_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Load Calibration Profile",
            str(self._config.calibration_dir),
            "Calibration JSON (*.json)",
        )
        if not selected:
            return
        path = Path(selected)
        bundle = self._calibration_repo.load(path)
        if bundle is None:
            self._show_error(f"Could not load calibration profile: {path}")
            return
        self._calibration_path = path
        self._set_current_calibration_bundle(bundle)
        self._calibration_panel.show_feedback(f"Loaded calibration profile {path.name}.", success=True)
        self._set_status(f"Calibration profile loaded: {path.name}")

    def _on_undistort_toggle_changed(self, source_id: str, enabled: bool) -> None:
        if enabled and not self._calibration_loaded:
            self._calibration_panel.show_feedback(
                f"{source_id}: undistort enabled but no calibration profile is loaded.",
                success=False,
            )
        self._update_calibration_preview(force=True)

    def _on_calibration_pattern_changed(self, pattern: str) -> None:
        normalized = pattern.lower().strip()
        if normalized not in {"chessboard", "charuco"}:
            normalized = "chessboard"
        self._calibration_pattern = normalized
        self._calibration_panel.show_feedback(
            f"Calibration pattern set to {normalized}.", success=True
        )
        self._update_calibration_preview(force=True)

    def _on_calibration_workflow_mode_changed(self, mode: str) -> None:
        normalized = mode.lower().strip()
        if normalized not in {"intrinsics", "sync_extrinsics"}:
            normalized = "intrinsics"
        if normalized == "sync_extrinsics":
            message = (
                "Calibration workflow set to Sync / Extrinsics: only synchronized multi-camera sets are stored."
            )
        else:
            message = (
                "Calibration workflow set to Intrinsics: strict per-camera samples are stored for intrinsics solve."
            )
        self._calibration_panel.show_feedback(message, success=True)
        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)

    def _on_sync_thresholds_changed(self, min_quality: float, min_coverage_ratio: float) -> None:
        self._calibration_manager.set_sync_acceptance_thresholds(
            min_quality_score=min_quality,
            min_coverage_ratio=min_coverage_ratio,
        )
        message = (
            "Synchronized capture thresholds updated (used in Sync / Extrinsics mode): "
            f"quality >= {min_quality:.2f}, coverage >= {min_coverage_ratio * 100.0:.1f}%."
        )
        self._calibration_panel.show_feedback(message, success=True)
        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)

    def _on_tab_changed(self, index: int) -> None:
        if index == self.TAB_CALIBRATION:
            self._update_calibration_preview(force=True)
            self._refresh_calibration_panel(force=True)
        if self._latest_frames:
            self._submit_pipeline_batch(self._latest_frames)

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("Worker error: %s", message)
        self._set_status(f"Worker error: {message}")

    def _summarize_pipeline_note(self, notes: list[str]) -> str | None:
        ignore_prefixes = (
            "No valid 3D pose reconstructed",
            "2D detector is placeholder_pose",
        )
        for note in notes:
            normalized = note.strip()
            if not normalized:
                continue
            if normalized.startswith(ignore_prefixes):
                continue
            return normalized
        return None

    def _update_fps(self) -> None:
        now = time.perf_counter()
        self._fps_history.append(now)
        if len(self._fps_history) < 2:
            self._diag_fps = 0.0
            return
        elapsed = self._fps_history[-1] - self._fps_history[0]
        if elapsed <= 0:
            self._diag_fps = 0.0
            return
        self._diag_fps = (len(self._fps_history) - 1) / elapsed

    def _on_frame_batch(self, batch_obj: object) -> None:
        frames: dict[str, FramePacket] = dict(batch_obj)  # type: ignore[arg-type]
        if not frames:
            return
        incoming_ts = max(frame.timestamp_sec for frame in frames.values())
        if self._latest_frames:
            latest_ts = max(frame.timestamp_sec for frame in self._latest_frames.values())
            if incoming_ts < latest_ts:
                return
        self._latest_frames = frames
        now = time.perf_counter()
        for source_id in frames.keys():
            self._camera_timestamp_windows[source_id].append(now)
        self._diag_per_camera_fps = self._compute_per_camera_fps()
        self._submit_pipeline_batch(frames)

    def _process_pipeline_batch(self, frames: dict[str, FramePacket]) -> None:
        self._latest_frames = frames
        self._submit_pipeline_batch(frames)

    def _on_pipeline_result(self, result_obj: object) -> None:
        if not isinstance(result_obj, PipelineResult):
            return
        result = result_obj
        self._latest_pipeline_result = result

        if self._session_recorder.active:
            try:
                self._session_recorder.append_batch(result.frames, result)
            except Exception as exc:
                LOGGER.exception("Recording failed.")
                self._show_error(f"Recording failed: {exc}")
                self._on_stop_recording()

        self._update_fps()
        self._diag_cameras_active = len(result.frames)
        self._diag_matched_keypoints = result.debug.matched_keypoints
        self._diag_reconstruction_mode = result.debug.reconstruction_mode
        self._diag_reconstructed_keypoints = result.debug.reconstructed_keypoints
        self._diag_mean_reprojection_error_px = result.debug.mean_reprojection_error_px
        self._diag_capture_latency_ms = result.debug.capture_latency_ms
        self._diag_detection_ms = result.debug.detection_ms
        self._diag_matching_ms = result.debug.matching_ms
        self._diag_triangulation_ms = result.debug.triangulation_ms
        self._diag_smoothing_ms = result.debug.smoothing_ms
        self._diag_pipeline_ms = result.debug.pipeline_ms
        self._diag_dropped_input_batches = result.debug.dropped_input_batches
        if result.debug.reconstruction_mode == "placeholder_fallback":
            self._diag_triangulation_status = "Fallback 3D active (debug only, not trustworthy)"
        elif result.debug.detector_name == "placeholder_pose" and result.pose_3d is not None:
            self._diag_triangulation_status = "3D solved from placeholder detector (debug only)"
        elif result.debug.reconstruction_mode in {"unavailable", "disabled"}:
            detail = self._summarize_pipeline_note(result.debug.notes)
            self._diag_triangulation_status = (
                detail
                if detail
                else f"Triangulation unavailable ({result.debug.reconstruction_mode})"
            )
        elif result.pose_3d:
            self._diag_triangulation_status = f"3D pose solved ({result.debug.reconstruction_mode})"
        else:
            detail = self._summarize_pipeline_note(result.debug.notes)
            self._diag_triangulation_status = (
                detail
                if detail
                else f"No triangulated pose ({result.debug.reconstruction_mode})"
            )
        self._refresh_diagnostics()

        self._frame_counter += 1
        if self._frame_counter % 20 == 0:
            if result.debug.mean_reprojection_error_px is not None:
                status = (
                    f"Running | cams={result.debug.active_cameras} | matched={result.debug.matched_keypoints} "
                    f"| detector={result.debug.detector_name} | mode={result.debug.reconstruction_mode} "
                    f"| joints={result.debug.reconstructed_keypoints} "
                    f"| reproj={result.debug.mean_reprojection_error_px:.2f}px"
                )
            else:
                status = (
                    f"Running | cams={result.debug.active_cameras} | matched={result.debug.matched_keypoints} "
                    f"| detector={result.debug.detector_name} | mode={result.debug.reconstruction_mode} "
                    f"| joints={result.debug.reconstructed_keypoints}"
                )
            self._set_status(status)

    def _on_display_tick(self) -> None:
        if not self._latest_frames:
            return
        display_start = time.perf_counter()

        current_tab = self._tabs.currentIndex()
        if current_tab == self.TAB_CALIBRATION:
            self._update_calibration_preview()
            return

        result = self._latest_pipeline_result
        show_overlays = self._runtime_tuning.overlays_enabled
        if result is not None:
            latest_index = max(frame.frame_index for frame in self._latest_frames.values())
            if abs(latest_index - result.frame_index) > 3:
                show_overlays = False
        poses_2d = result.poses_2d if result is not None and show_overlays else {}
        pose_3d = result.pose_3d if result is not None else None
        reproj = result.reprojected_keypoints_px if result is not None and show_overlays else {}

        overlay_start = time.perf_counter()
        if current_tab == self.TAB_CAPTURE:
            self._capture_workspace.camera_grid.update_batch(
                frames=self._latest_frames,
                poses_2d=poses_2d,
                reprojected_points_px=reproj if show_overlays else {},
            )
        elif current_tab == self.TAB_RECONSTRUCTION:
            self._reconstruction_workspace.update_visuals(
                frames=self._latest_frames,
                poses_2d=poses_2d,
                pose_3d=pose_3d,
                reprojected_points_px=reproj,
            )
            if result is not None:
                self._reconstruction_workspace.set_reconstruction_metadata(
                    mode=result.debug.reconstruction_mode,
                    reconstructed_joints=result.debug.reconstructed_keypoints,
                    mean_reprojection_error_px=result.debug.mean_reprojection_error_px,
                    triangulation_status=self._diag_triangulation_status,
                )
        elif current_tab == self.TAB_ANALYSIS:
            # Analysis tab focuses on timeline controls; keep rendering lightweight.
            pass

        overlay_elapsed_ms = (time.perf_counter() - overlay_start) * 1000.0
        display_elapsed_ms = (time.perf_counter() - display_start) * 1000.0
        self._diag_overlay_ms = overlay_elapsed_ms
        self._diag_display_ms = display_elapsed_ms

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._on_stop_recording()
        self._on_stop_playback()
        self._on_stop_live()
        self._stop_camera_probe_worker()
        self._stop_pipeline_worker()
        self._pipeline.shutdown()
        logging.getLogger().removeHandler(self._qt_log_handler)
        super().closeEvent(event)
