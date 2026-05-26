from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import cv2
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from mocap_app.core.config import AppConfig
from mocap_app.io.calibration_io import (
    CalibrationManager,
    CalibrationRepository,
    ChessboardDetectionResult,
)
from mocap_app.models.types import (
    CalibrationBoardSettings,
    CalibrationBundle,
    CameraProbeResult,
    CameraSourceConfig,
    FramePacket,
    RuntimeTuning,
)
from mocap_app.ui.widgets.calibration_panel import CalibrationPanelWidget
from mocap_app.workers.calibration_solve_worker import IntrinsicsSolveWorker
from mocap_app.workers.camera_probe_worker import CameraProbeWorker
from mocap_app.workers.capture_worker import LiveCaptureWorker


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Calibration-only application shell."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config

        self._calibration_repo = CalibrationRepository()
        self._calibration_manager = CalibrationManager()
        self._calibration_path = self._default_calibration_path()
        self._current_calibration_bundle: CalibrationBundle | None = None
        self._calibration_loaded = False
        self._calibration_pattern = self._calibration_manager.default_pattern
        self._latest_calibration_detections: dict[str, ChessboardDetectionResult] = {}
        self._last_calibration_detection_at = 0.0
        self._calibration_detection_interval_sec = 0.25
        self._last_calibration_panel_refresh_at = 0.0
        self._calibration_panel_refresh_interval_sec = 0.35
        self._last_calibration_auto_capture_at = 0.0
        self._last_live_status_refresh_at = 0.0

        self._live_worker: LiveCaptureWorker | None = None
        self._camera_probe_worker: CameraProbeWorker | None = None
        self._intrinsics_solve_worker: IntrinsicsSolveWorker | None = None
        self._active_sources: list[CameraSourceConfig] = []
        self._runtime_tuning = RuntimeTuning()
        self._latest_frames: dict[str, FramePacket] = {}
        self._last_rendered_frame_indices: dict[str, int] = {}
        self._active_camera_count = 0

        self._calibration_panel = self._create_calibration_panel(
            default_camera_csv=self._config.default_camera_csv,
            default_fps=self._config.target_fps,
        )
        self._runtime_tuning = self._calibration_panel.runtime_tuning()
        self._calibration_detection_interval_sec = 1.0 / max(
            self._runtime_tuning.calibration_detection_hz,
            0.1,
        )

        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._on_display_tick)

        self._setup_ui()
        self._apply_window_style()
        self._connect_signals()

        self._calibration_panel.set_pattern_options(
            pattern_names=self._calibration_manager.available_patterns(),
            selected=self._calibration_pattern,
        )
        self._calibration_panel.set_board_settings(self._calibration_manager.board_settings())
        self._calibration_panel.set_spatial_grid_values(*self._calibration_manager.spatial_grid_shape)
        self._calibration_panel.set_workflow_mode("intrinsics")
        self._refresh_threshold_controls_for_mode()

        self._load_existing_calibration()
        self._seed_startup_source_slots()
        self._refresh_live_status(force=True)
        self._refresh_calibration_panel(force=True)
        self._set_display_timer_hz(self._runtime_tuning.preview_fps)

        self.setWindowTitle(self._config.app_name)
        self._apply_initial_window_geometry()
        self._set_status("Ready for camera calibration")

    def _setup_ui(self) -> None:
        self.setCentralWidget(self._calibration_panel)
        self.statusBar().showMessage("Idle")

    def _create_calibration_panel(self, default_camera_csv: str, default_fps: float):
        return CalibrationPanelWidget(
            default_camera_csv=default_camera_csv,
            default_fps=default_fps,
        )

    def _apply_initial_window_geometry(self) -> None:
        self.resize(1500, 920)

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
            """
        )

    def _connect_signals(self) -> None:
        self._calibration_panel.start_live_requested.connect(self._on_start_live)
        self._calibration_panel.stop_live_requested.connect(self._on_stop_live)
        self._calibration_panel.runtime_tuning_changed.connect(self._on_runtime_tuning_changed)
        self._calibration_panel.probe_cameras_requested.connect(self._on_probe_cameras)
        self._calibration_panel.ui_message.connect(self._show_warning)
        self._calibration_panel.capture_requested.connect(self._on_capture_calibration)
        self._calibration_panel.solve_requested.connect(self._on_solve_calibration)
        self._calibration_panel.solve_extrinsics_requested.connect(self._on_solve_extrinsics)
        self._calibration_panel.reset_requested.connect(self._on_reset_calibration_samples)
        self._calibration_panel.new_project_requested.connect(self._on_new_project)
        self._calibration_panel.save_profile_requested.connect(self._on_save_calibration_profile)
        self._calibration_panel.load_profile_requested.connect(self._on_load_calibration_profile)
        self._calibration_panel.undistort_toggled.connect(self._on_undistort_toggle_changed)
        self._calibration_panel.auto_capture_start_requested.connect(self._on_start_auto_capture_from_preview)
        self._calibration_panel.pattern_changed.connect(self._on_calibration_pattern_changed)
        self._calibration_panel.board_settings_applied.connect(self._on_board_settings_applied)
        self._calibration_panel.acceptance_thresholds_changed.connect(self._on_acceptance_thresholds_changed)
        self._calibration_panel.workflow_mode_changed.connect(self._on_calibration_workflow_mode_changed)
        self._calibration_panel.spatial_grid_changed.connect(self._on_spatial_grid_changed)
        if hasattr(self._calibration_panel, "sources_changed"):
            self._calibration_panel.sources_changed.connect(self._on_panel_sources_changed)

    def _set_display_timer_hz(self, hz: float) -> None:
        safe_hz = max(1.0, hz)
        interval_ms = max(8, int(1000.0 / safe_hz))
        self._display_timer.setInterval(interval_ms)
        if not self._display_timer.isActive():
            self._display_timer.start()

    def _default_calibration_path(self) -> Path:
        return self._config.calibration_dir / "current_calibration.json"

    def _on_runtime_tuning_changed(self, tuning_obj: object) -> None:
        if not isinstance(tuning_obj, RuntimeTuning):
            return
        self._runtime_tuning = tuning_obj
        self._set_display_timer_hz(tuning_obj.preview_fps)
        self._calibration_detection_interval_sec = 1.0 / max(tuning_obj.calibration_detection_hz, 0.1)
        self._update_calibration_preview(force=True)

    def _stop_camera_probe_worker(self) -> None:
        if self._camera_probe_worker is None:
            return
        self._camera_probe_worker.stop()
        if not self._camera_probe_worker.wait(2500):
            LOGGER.warning("Camera probe worker did not stop in time; forcing termination.")
            self._camera_probe_worker.terminate()
            self._camera_probe_worker.wait(1000)
        self._camera_probe_worker = None
        self._calibration_panel.set_camera_probe_running(False)

    def _on_probe_cameras(self, max_index: int) -> None:
        self._stop_camera_probe_worker()
        worker = CameraProbeWorker(max_index=max_index)
        worker.result_ready.connect(self._on_camera_probe_result)
        worker.error.connect(self._on_worker_error)
        worker.state_changed.connect(lambda state: LOGGER.info("Camera probe state: %s", state))
        worker.finished.connect(self._on_camera_probe_finished)
        self._camera_probe_worker = worker
        self._calibration_panel.set_camera_probe_running(True)
        worker.start()
        self._set_status(f"Scanning cameras 0..{max_index} ...")

    def _on_camera_probe_result(self, payload: object) -> None:
        self._calibration_panel.set_camera_probe_running(False)
        cameras = payload if isinstance(payload, list) else []
        results: list[CameraProbeResult] = []
        for item in cameras:
            if isinstance(item, CameraProbeResult):
                results.append(item)
        self._calibration_panel.set_detected_cameras(results)
        if results:
            self._set_status(f"Detected {len(results)} camera(s).")
            self._seed_startup_source_slots()
        else:
            self._set_status("No cameras detected in probed range.")

    def _on_camera_probe_finished(self) -> None:
        self._calibration_panel.set_camera_probe_running(False)
        self._camera_probe_worker = None

    def _seed_startup_source_slots(self) -> None:
        try:
            sources = self._calibration_panel.current_sources()
        except ValueError:
            sources = [
                CameraSourceConfig(source_id="cam0", kind="webcam", uri=0, label="Webcam 0"),
                CameraSourceConfig(source_id="cam1", kind="webcam", uri=1, label="Webcam 1"),
            ]
        self._active_sources = sources
        self._calibration_panel.set_sources([source.source_id for source in sources])
        self._refresh_calibration_panel(force=True)

    def _load_existing_calibration(self) -> None:
        bundle = self._calibration_repo.load(self._calibration_path)
        if bundle is not None:
            self._apply_board_settings_from_bundle_metadata(bundle)
            self._apply_spatial_grid_from_bundle_metadata(bundle)
        self._set_current_calibration_bundle(bundle)
        if bundle is not None:
            self._set_status(f"Loaded calibration: {self._calibration_path.name}")

    def _set_current_calibration_bundle(self, bundle: CalibrationBundle | None) -> None:
        self._current_calibration_bundle = bundle
        self._calibration_loaded = bundle is not None
        self._refresh_calibration_panel(force=True)

    def _board_settings_from_metadata(self, metadata: dict[str, Any]) -> CalibrationBoardSettings | None:
        try:
            board = metadata.get("calibration_board")
            if isinstance(board, dict):
                active_type = str(board.get("type", "")).lower().strip()
                current = self._calibration_manager.board_settings()
                if active_type == "charuco":
                    squares = board.get("squares", [current.charuco_squares_x, current.charuco_squares_y])
                    return CalibrationBoardSettings(
                        chessboard_cols=current.chessboard_cols,
                        chessboard_rows=current.chessboard_rows,
                        chessboard_square_size_m=current.chessboard_square_size_m,
                        charuco_squares_x=int(squares[0]),
                        charuco_squares_y=int(squares[1]),
                        charuco_square_size_m=float(board.get("square_size_m", current.charuco_square_size_m)),
                        charuco_marker_size_m=float(board.get("marker_size_m", current.charuco_marker_size_m)),
                    )
                if active_type == "chessboard":
                    corners = board.get("inner_corners", [current.chessboard_cols, current.chessboard_rows])
                    return CalibrationBoardSettings(
                        chessboard_cols=int(corners[0]),
                        chessboard_rows=int(corners[1]),
                        chessboard_square_size_m=float(board.get("square_size_m", current.chessboard_square_size_m)),
                        charuco_squares_x=current.charuco_squares_x,
                        charuco_squares_y=current.charuco_squares_y,
                        charuco_square_size_m=current.charuco_square_size_m,
                        charuco_marker_size_m=current.charuco_marker_size_m,
                    )
                if active_type == "mixed":
                    chessboard = board.get("chessboard", {})
                    charuco = board.get("charuco", {})
                    corners = chessboard.get("inner_corners", [9, 6])
                    squares = charuco.get("squares", [5, 7])
                    return CalibrationBoardSettings(
                        chessboard_cols=int(corners[0]),
                        chessboard_rows=int(corners[1]),
                        chessboard_square_size_m=float(chessboard.get("square_size_m", 0.024)),
                        charuco_squares_x=int(squares[0]),
                        charuco_squares_y=int(squares[1]),
                        charuco_square_size_m=float(charuco.get("square_size_m", 0.077)),
                        charuco_marker_size_m=float(charuco.get("marker_size_m", 0.061)),
                    )

            board_shape = metadata.get("board_shape", [9, 6])
            return CalibrationBoardSettings(
                chessboard_cols=int(board_shape[0]),
                chessboard_rows=int(board_shape[1]),
                chessboard_square_size_m=float(metadata.get("square_size_m", 0.024)),
                charuco_squares_x=int(metadata.get("charuco_squares_x", 5)),
                charuco_squares_y=int(metadata.get("charuco_squares_y", 3)),
                charuco_square_size_m=float(metadata.get("charuco_square_size_m", 0.077)),
                charuco_marker_size_m=float(metadata.get("charuco_marker_size_m", 0.061)),
            )
        except (TypeError, ValueError, IndexError):
            return None

    def _apply_board_settings_from_bundle_metadata(self, bundle: CalibrationBundle) -> None:
        settings = self._board_settings_from_metadata(bundle.metadata)
        if settings is None:
            return
        self._calibration_manager.apply_board_settings(settings)
        self._calibration_panel.set_board_settings(self._calibration_manager.board_settings())
        self._calibration_panel.set_pattern_options(
            pattern_names=self._calibration_manager.available_patterns(),
            selected=self._calibration_pattern,
        )

    def _apply_spatial_grid_from_bundle_metadata(self, bundle: CalibrationBundle) -> None:
        try:
            spatial = bundle.metadata.get("spatial_coverage")
            if not isinstance(spatial, dict):
                return
            grid = spatial.get("grid")
            if not isinstance(grid, dict):
                return
            cols = int(grid.get("cols", self._calibration_manager.spatial_grid_shape[0]))
            rows = int(grid.get("rows", self._calibration_manager.spatial_grid_shape[1]))
        except (TypeError, ValueError):
            return
        self._calibration_manager.set_spatial_coverage_grid(cols=cols, rows=rows)
        self._calibration_panel.set_spatial_grid_values(cols, rows)

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Camera Calibration", message)

    def _show_error(self, message: str) -> None:
        LOGGER.error(message)
        QMessageBox.critical(self, "Camera Calibration", message)
        self._set_status(message)

    def _refresh_live_status(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self._last_live_status_refresh_at < 0.5:
            return
        live_active = self._live_worker is not None and self._live_worker.isRunning()
        self._calibration_panel.set_live_status(
            live_active=live_active,
            active_cameras=self._active_camera_count,
        )
        self._last_live_status_refresh_at = now

    def _active_source_ids(self) -> list[str]:
        live_active = self._live_worker is not None and self._live_worker.isRunning()
        if live_active and self._active_sources:
            return [source.source_id for source in self._active_sources]
        if self._latest_frames:
            return sorted(self._latest_frames.keys())
        try:
            return [source.source_id for source in self._calibration_panel.current_sources()]
        except ValueError:
            return []

    def _on_panel_sources_changed(self, sources_obj: object) -> None:
        sources = [source for source in sources_obj if isinstance(source, CameraSourceConfig)] if isinstance(sources_obj, list) else []
        live_active = self._live_worker is not None and self._live_worker.isRunning()
        if live_active:
            return
        self._active_sources = sources
        source_ids = {source.source_id for source in sources}
        self._latest_frames = {source_id: frame for source_id, frame in self._latest_frames.items() if source_id in source_ids}
        self._latest_calibration_detections = {
            source_id: detection
            for source_id, detection in self._latest_calibration_detections.items()
            if source_id in source_ids
        }
        self._last_rendered_frame_indices = {
            source_id: frame_index
            for source_id, frame_index in self._last_rendered_frame_indices.items()
            if source_id in source_ids
        }
        self._refresh_calibration_panel(force=True)

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
        if not source_ids:
            warnings.append("Configure at least one camera source before capturing calibration samples.")
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
                "Workflow mode: Intrinsics. Captures are stored per camera using the configured intrinsics thresholds."
            )
        warnings.append(
            "Intrinsics thresholds: "
            f"quality >= {self._calibration_manager.min_quality_score:.2f}, "
            f"coverage >= {self._calibration_manager.min_coverage_ratio * 100.0:.1f}%."
        )
        warnings.append(
            "Sync thresholds: "
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

    def _refresh_threshold_controls_for_mode(self) -> None:
        if self._calibration_workflow_mode() == "sync_extrinsics":
            self._calibration_panel.set_acceptance_threshold_values(
                min_quality=self._calibration_manager.sync_min_quality_score,
                min_coverage_ratio=self._calibration_manager.sync_min_coverage_ratio,
            )
            return
        self._calibration_panel.set_acceptance_threshold_values(
            min_quality=self._calibration_manager.min_quality_score,
            min_coverage_ratio=self._calibration_manager.min_coverage_ratio,
        )

    def _auto_capture_idle_text(self) -> str:
        limit = self._calibration_panel.auto_capture_max_samples()
        limit_text = f" Max {limit}." if limit > 0 else ""
        collection = self._calibration_manager.sample_collection_metadata()
        duration_sec = float(collection.get("duration_sec", 0.0) or 0.0)
        duration_text = f" Collected for {self._format_duration_sec(duration_sec)}." if duration_sec > 0 else ""
        if self._calibration_workflow_mode() == "sync_extrinsics":
            return (
                "Auto capture armed (sync mode). Hold the board visible in at least 2 cameras."
                + limit_text
                + duration_text
            )
        target_text = ""
        if limit > 0:
            target_text = f" Target {self._spatial_target_samples_per_cell()} sample(s) per grid cell."
        return (
            "Auto capture armed (intrinsics mode). Move the board through new per-camera poses."
            + limit_text
            + target_text
            + duration_text
        )

    def _format_duration_sec(self, duration_sec: float) -> str:
        total_sec = max(0, int(round(duration_sec)))
        minutes, seconds = divmod(total_sec, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"

    def _auto_capture_stop_message_if_limit_reached(self) -> str | None:
        limit = self._calibration_panel.auto_capture_max_samples()
        if limit <= 0:
            return None
        if self._calibration_workflow_mode() == "sync_extrinsics":
            sync_count = self._calibration_manager.synchronized_capture_count()
            if sync_count >= limit:
                return f"Auto capture stopped at {sync_count}/{limit} synchronized set(s)."
            return None

        source_ids = self._active_source_ids()
        if not source_ids:
            return None
        if all(self._source_spatial_grid_complete(source_id) for source_id in source_ids):
            target = self._spatial_target_samples_per_cell()
            coverage_text = ", ".join(
                f"{source_id}=complete"
                for source_id in source_ids
            )
            return (
                f"Auto capture stopped: all overlay grid cells reached "
                f"{target}/{target} ({coverage_text})."
            )
        return None

    def _stop_auto_capture_if_limit_reached(self) -> bool:
        message = self._auto_capture_stop_message_if_limit_reached()
        if message is None:
            return False
        self._calibration_panel.set_auto_capture_enabled(False)
        self._calibration_panel.set_auto_capture_status(message)
        self._calibration_panel.show_feedback(message, success=True)
        self._set_status(message)
        return True

    def _auto_capture_intrinsics_candidates(self, source_ids: list[str]) -> list[str]:
        limit = self._calibration_panel.auto_capture_max_samples()
        if limit <= 0 or self._calibration_workflow_mode() != "intrinsics":
            return list(source_ids)
        return [
            source_id
            for source_id in source_ids
            if not self._source_spatial_grid_complete(source_id)
        ]

    def _source_spatial_grid_complete(self, source_id: str) -> bool:
        if self._calibration_panel.auto_capture_max_samples() <= 0:
            return False
        target = self._spatial_target_samples_per_cell()
        summary = self._calibration_manager.spatial_coverage_summary(
            source_id,
            include_sync_only=False,
            include_sample_summaries=False,
            target_samples_per_cell=target,
        )
        hit_counts = summary.get("credited_cell_hit_counts", [])
        if not isinstance(hit_counts, list) or not hit_counts:
            return False
        for row_counts in hit_counts:
            if not isinstance(row_counts, list) or not row_counts:
                return False
            for hit_count in row_counts:
                if int(hit_count) < target:
                    return False
        return True

    def _update_calibration_preview(self, force: bool = False) -> None:
        if not self._latest_frames:
            return
        now = time.perf_counter()
        overlay_enabled = self._calibration_panel.overlay_enabled()
        detection_needed = overlay_enabled or self._calibration_panel.auto_capture_enabled()
        detection_due = detection_needed and (
            force or now - self._last_calibration_detection_at >= self._calibration_detection_interval_sec
        )
        frame_indices = {
            source_id: frame.frame_index
            for source_id, frame in self._latest_frames.items()
        }
        if not force and not detection_due and frame_indices == self._last_rendered_frame_indices:
            return

        sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)
        previews: dict[str, Any] = {
            source_id: self._prepare_calibration_preview_frame(source_id, frame.frame_bgr)
            for source_id, frame in self._latest_frames.items()
        }
        detections = dict(self._latest_calibration_detections)

        if detection_due:
            detections = {}
            for source_id, preview in previews.items():
                detection = self._calibration_manager.detect_pattern(
                    source_id=source_id,
                    frame_bgr=preview,
                    pattern=self._calibration_pattern,
                )
                detections[source_id] = detection
                if overlay_enabled:
                    previews[source_id] = self._draw_calibration_preview_overlay(
                        source_id=source_id,
                        frame_bgr=preview,
                        detection=detection,
                        sample_count=sample_counts.get(source_id, 0),
                    )

            self._latest_calibration_detections = detections
            self._last_calibration_detection_at = now
            if self._maybe_auto_capture_calibration(detections):
                return
            sample_counts = self._calibration_manager.observations_summary(include_sync_only=False)
        elif overlay_enabled:
            for source_id, preview in list(previews.items()):
                detection = detections.get(source_id)
                if detection is not None:
                    previews[source_id] = self._draw_calibration_preview_overlay(
                        source_id=source_id,
                        frame_bgr=preview,
                        detection=detection,
                        sample_count=sample_counts.get(source_id, 0),
                    )
        elif not detection_needed and self._latest_calibration_detections:
            self._latest_calibration_detections.clear()
            detections = {}
            self._refresh_calibration_panel(force=True)

        display_previews = self._finalize_calibration_preview_frames(previews, detections, overlay_enabled)
        self._calibration_panel.update_previews(display_previews, detections, sample_counts)
        self._last_rendered_frame_indices = frame_indices
        if detection_due or force:
            self._refresh_calibration_panel()

    def _prepare_calibration_preview_frame(self, source_id: str, frame_bgr: Any) -> Any:
        if not self._calibration_panel.undistort_enabled_for(source_id):
            return frame_bgr
        return self._calibration_manager.undistort_frame(
            source_id=source_id,
            frame_bgr=frame_bgr,
            bundle=self._current_calibration_bundle,
        )

    def _display_calibration_preview_frame(self, frame_bgr: Any) -> Any:
        if not self._calibration_panel.mirror_preview_enabled():
            return frame_bgr
        return cv2.flip(frame_bgr, 1)

    def _finalize_calibration_preview_frames(
        self,
        frames_by_source: dict[str, Any],
        detections: dict[str, ChessboardDetectionResult],
        overlay_enabled: bool,
    ) -> dict[str, Any]:
        if not self._calibration_panel.mirror_preview_enabled() and overlay_enabled:
            return frames_by_source
        if overlay_enabled:
            return {
                source_id: (
                    frame_bgr
                    if source_id in detections
                    else self._display_calibration_preview_frame(frame_bgr)
                )
                for source_id, frame_bgr in frames_by_source.items()
            }
        return {
            source_id: self._display_calibration_preview_frame(frame_bgr)
            for source_id, frame_bgr in frames_by_source.items()
        }

    def _draw_calibration_preview_overlay(
        self,
        source_id: str,
        frame_bgr: Any,
        detection: ChessboardDetectionResult,
        sample_count: int | None = None,
        accepted: bool | None = None,
    ) -> Any:
        mirror_preview = self._calibration_panel.mirror_preview_enabled()
        display_frame = self._display_calibration_preview_frame(frame_bgr)
        display_detection = self._mirror_detection_for_preview(detection, frame_bgr) if mirror_preview else detection
        return self._calibration_manager.draw_detection_overlay(
            display_frame,
            detection=display_detection,
            accepted=accepted,
            sample_count=sample_count,
            mirror_x=mirror_preview,
            spatial_target_samples_per_cell=self._spatial_target_samples_per_cell(),
        )

    def _spatial_target_samples_per_cell(self) -> int:
        max_samples = self._calibration_panel.auto_capture_max_samples()
        cols, rows = self._calibration_manager.spatial_grid_shape
        total_cells = max(1, int(cols) * int(rows))
        if max_samples <= 0:
            return 3
        return max(1, (int(max_samples) + total_cells - 1) // total_cells)

    def _detection_needs_spatial_cells(
        self,
        source_id: str,
        detection: ChessboardDetectionResult,
    ) -> bool:
        if self._calibration_panel.auto_capture_max_samples() <= 0:
            return True
        if not detection.found or detection.corners is None:
            return True

        target = self._spatial_target_samples_per_cell()
        cells = self._detection_spatial_cells(detection)
        if not cells:
            return True

        summary = self._calibration_manager.spatial_coverage_summary(
            source_id,
            include_sync_only=False,
            include_sample_summaries=False,
            target_samples_per_cell=target,
        )
        hit_counts = summary.get("credited_cell_hit_counts", [])
        try:
            return any(int(hit_counts[row][col]) < target for row, col in cells)  # type: ignore[index]
        except (TypeError, IndexError, ValueError):
            return True

    def _detection_spatial_cells(self, detection: ChessboardDetectionResult) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        if detection.corners is None:
            return cells

        points = detection.corners.reshape(-1, 2)
        for point in points:
            cells.add(
                self._point_to_spatial_grid_cell(
                    float(point[0]),
                    float(point[1]),
                    detection.image_size,
                )
            )

        bbox = detection.board_bbox_px
        if bbox is not None:
            bbox_x, bbox_y, bbox_w, bbox_h = bbox
            for point_x, point_y in (
                (bbox_x, bbox_y),
                (bbox_x + bbox_w, bbox_y),
                (bbox_x, bbox_y + bbox_h),
                (bbox_x + bbox_w, bbox_y + bbox_h),
            ):
                cells.add(
                    self._point_to_spatial_grid_cell(
                        float(point_x),
                        float(point_y),
                        detection.image_size,
                    )
                )

        center = detection.board_center_px
        if center is None and points.size:
            min_x = float(points[:, 0].min())
            max_x = float(points[:, 0].max())
            min_y = float(points[:, 1].min())
            max_y = float(points[:, 1].max())
            center = (min_x + (max_x - min_x) * 0.5, min_y + (max_y - min_y) * 0.5)
        if center is not None:
            cells.add(
                self._point_to_spatial_grid_cell(
                    float(center[0]),
                    float(center[1]),
                    detection.image_size,
                )
            )
        return cells

    def _detection_center_cell(self, detection: ChessboardDetectionResult) -> tuple[int, int] | None:
        if detection.corners is None:
            return None

        center = detection.board_center_px
        if center is None:
            points = detection.corners.reshape(-1, 2)
            if points.size:
                min_x = float(points[:, 0].min())
                max_x = float(points[:, 0].max())
                min_y = float(points[:, 1].min())
                max_y = float(points[:, 1].max())
                center = (min_x + (max_x - min_x) * 0.5, min_y + (max_y - min_y) * 0.5)
        if center is not None:
            return self._point_to_spatial_grid_cell(float(center[0]), float(center[1]), detection.image_size)
        return None

    def _point_to_spatial_grid_cell(
        self,
        x_px: float,
        y_px: float,
        image_size: tuple[int, int],
    ) -> tuple[int, int]:
        width, height = image_size
        cols, rows = self._calibration_manager.spatial_grid_shape
        safe_width = max(float(width), 1.0)
        safe_height = max(float(height), 1.0)
        col = min(max(int(x_px * cols / safe_width), 0), cols - 1)
        row = min(max(int(y_px * rows / safe_height), 0), rows - 1)
        return row, col

    def _mirror_detection_for_preview(
        self,
        detection: ChessboardDetectionResult,
        frame_bgr: Any,
    ) -> ChessboardDetectionResult:
        try:
            width = int(frame_bgr.shape[1])
        except (AttributeError, IndexError, TypeError):
            return detection

        corners = None
        if detection.corners is not None:
            corners = detection.corners.copy()
            corners[..., 0] = float(width - 1) - corners[..., 0]

        bbox = detection.board_bbox_px
        mirrored_bbox = None
        if bbox is not None:
            x_px, y_px, box_width, box_height = bbox
            mirrored_bbox = (
                max(0.0, float(width) - float(x_px) - float(box_width)),
                float(y_px),
                float(box_width),
                float(box_height),
            )

        center = detection.board_center_px
        mirrored_center = None
        if center is not None:
            mirrored_center = (float(width - 1) - float(center[0]), float(center[1]))

        return ChessboardDetectionResult(
            source_id=detection.source_id,
            found=detection.found,
            image_size=detection.image_size,
            pattern_type=detection.pattern_type,
            corners=corners,
            charuco_ids=detection.charuco_ids.copy() if detection.charuco_ids is not None else None,
            detected_corners=detection.detected_corners,
            quality_score=detection.quality_score,
            coverage_ratio=detection.coverage_ratio,
            sharpness_score=detection.sharpness_score,
            board_bbox_px=mirrored_bbox,
            board_center_px=mirrored_center,
            diagnostics=list(detection.diagnostics),
        )

    def _on_start_live(
        self,
        sources: list[CameraSourceConfig],
        target_fps: float,
    ) -> None:
        self._on_stop_live()
        self._stop_camera_probe_worker()
        self._on_runtime_tuning_changed(self._calibration_panel.runtime_tuning())

        self._active_sources = sources
        self._latest_frames.clear()
        self._latest_calibration_detections.clear()
        self._last_rendered_frame_indices.clear()
        self._last_calibration_detection_at = 0.0
        source_ids = [source.source_id for source in sources]
        self._calibration_panel.set_sources(source_ids)
        self._active_camera_count = len(sources)

        worker = LiveCaptureWorker(
            sources=sources,
            target_fps=self._runtime_tuning.capture_fps if self._runtime_tuning.capture_fps > 0 else target_fps,
            max_frame_width=self._runtime_tuning.preview_max_width,
            requested_width=self._runtime_tuning.capture_width,
            requested_height=self._runtime_tuning.capture_height,
        )
        worker.batch_ready.connect(self._on_frame_batch)
        worker.state_changed.connect(self._on_live_state_changed)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(self._on_live_finished)
        self._live_worker = worker
        worker.start()
        self._refresh_live_status(force=True)
        self._refresh_calibration_panel(force=True)
        self._set_status(
            f"Starting live capture ({len(sources)} sources, "
            f"{self._runtime_tuning.capture_fps:.1f} FPS, "
            f"capture={self._runtime_tuning.capture_width or 'auto'}x{self._runtime_tuning.capture_height or 'auto'}, "
            f"preview<= {self._runtime_tuning.preview_max_width or 'auto'})..."
        )

    def _on_live_state_changed(self, state: str) -> None:
        self._refresh_live_status(force=True)
        if state == "live_started":
            self._set_status("Live capture started")
        elif state == "live_stopped":
            self._set_status("Live capture stopped")
        else:
            self._set_status(state)

    def _on_live_finished(self) -> None:
        if self._live_worker is not None and not self._live_worker.isRunning():
            self._live_worker = None
        self._active_sources = []
        self._active_camera_count = 0
        self._refresh_live_status(force=True)

    def _on_stop_live(self) -> None:
        if self._live_worker is None:
            self._refresh_live_status(force=True)
            return
        self._live_worker.stop()
        if not self._live_worker.wait(3000):
            LOGGER.warning("Live capture worker did not stop in time; forcing termination.")
            self._live_worker.terminate()
            self._live_worker.wait(1000)
        self._live_worker = None
        self._active_sources = []
        self._latest_frames.clear()
        self._latest_calibration_detections.clear()
        self._last_rendered_frame_indices.clear()
        self._active_camera_count = 0
        self._refresh_live_status(force=True)
        self._refresh_calibration_panel(force=True)
        self._set_status("Live capture stopped")

    def _on_frame_batch(self, batch_obj: object) -> None:
        frames = dict(batch_obj)  # type: ignore[arg-type]
        if not frames:
            return
        incoming_ts = max(frame.timestamp_sec for frame in frames.values())
        if self._latest_frames:
            latest_ts = max(frame.timestamp_sec for frame in self._latest_frames.values())
            if incoming_ts < latest_ts:
                return
        self._latest_frames = frames
        self._active_camera_count = len(frames)
        self._refresh_live_status()

    def _build_calibration_preview_frame(
        self,
        source_id: str,
        frame_bgr: Any,
        detection: ChessboardDetectionResult,
        accepted: bool | None = None,
    ) -> Any:
        preview = self._prepare_calibration_preview_frame(source_id, frame_bgr)
        if not self._calibration_panel.overlay_enabled():
            return self._display_calibration_preview_frame(preview)
        return self._draw_calibration_preview_overlay(
            source_id=source_id,
            frame_bgr=preview,
            detection=detection,
            accepted=accepted,
            sample_count=self._calibration_manager.observation_count(source_id, include_sync_only=False),
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
        if auto_trigger and workflow_mode == "intrinsics":
            allowed_source_ids = set(self._auto_capture_intrinsics_candidates(list(self._latest_frames.keys())))
            if not allowed_source_ids:
                self._stop_auto_capture_if_limit_reached()
                return False
            if active_detections:
                active_detections = {
                    source_id: detection
                    for source_id, detection in active_detections.items()
                    if source_id in allowed_source_ids
                    and self._detection_needs_spatial_cells(source_id, detection)
                }
                if not active_detections:
                    self._calibration_panel.set_auto_capture_status(
                        "Auto capture waiting: current board position only touches grid cells already at target."
                    )
                    return False
        if active_detections:
            feedback_by_source = self._calibration_manager.try_add_detection_set(
                detections_by_source=active_detections,
                pattern=self._calibration_pattern,
                allow_relaxed_sync=allow_relaxed_sync,
                workflow_mode=workflow_mode,
            )
        else:
            frames_by_source = {
                source_id: frame.frame_bgr
                for source_id, frame in self._latest_frames.items()
            }
            if auto_trigger and workflow_mode == "intrinsics":
                allowed_source_ids = set(self._auto_capture_intrinsics_candidates(list(frames_by_source.keys())))
                frames_by_source = {
                    source_id: frame
                    for source_id, frame in frames_by_source.items()
                    if source_id in allowed_source_ids
                }
                if not frames_by_source:
                    self._stop_auto_capture_if_limit_reached()
                    return False
            feedback_by_source = self._calibration_manager.try_add_observation_set(
                frames_by_source=frames_by_source,
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
        if self._intrinsics_solve_worker is not None:
            return False
        if not self._calibration_panel.auto_capture_enabled():
            return False
        if self._stop_auto_capture_if_limit_reached():
            return False
        now = time.perf_counter()
        if now - self._last_calibration_auto_capture_at < self._calibration_panel.auto_capture_cooldown_sec():
            return False
        captured = self._capture_calibration_samples(auto_trigger=True, detections=detections)
        if captured:
            self._stop_auto_capture_if_limit_reached()
        return captured

    def _on_capture_calibration(self) -> None:
        if self._intrinsics_solve_worker is not None:
            self._calibration_panel.show_feedback(
                "Intrinsics solve is running; capture is paused until it finishes.",
                success=False,
            )
            return
        detections = self._latest_calibration_detections if self._latest_calibration_detections else None
        self._capture_calibration_samples(auto_trigger=False, detections=detections)

    def _on_start_auto_capture_from_preview(self) -> None:
        if self._intrinsics_solve_worker is not None:
            self._calibration_panel.show_feedback(
                "Wait for the intrinsics solve to finish before starting auto capture.",
                success=False,
            )
            self._calibration_panel.set_auto_capture_enabled(False)
            return
        if not self._latest_frames:
            self._calibration_panel.set_auto_capture_enabled(False)
            self._show_warning("No frames available. Start live capture first.")
            return
        if self._stop_auto_capture_if_limit_reached():
            return

        self._calibration_panel.set_auto_capture_enabled(True)
        self._last_calibration_auto_capture_at = 0.0
        message = self._auto_capture_idle_text()
        self._calibration_panel.set_auto_capture_status(message)
        self._calibration_panel.show_feedback("Auto capture started from preview.", success=True)
        self._set_status("Auto capture started")
        self._update_calibration_preview(force=True)

    def _on_solve_calibration(self) -> None:
        if self._intrinsics_solve_worker is not None:
            self._calibration_panel.show_feedback("Intrinsics solve is already running.", success=False)
            return

        worker = IntrinsicsSolveWorker(calibration_manager=self._calibration_manager)
        worker.result_ready.connect(self._on_intrinsics_solve_result)
        worker.error.connect(self._on_intrinsics_solve_error)
        worker.state_changed.connect(lambda state: LOGGER.info("Intrinsics solve state: %s", state))
        worker.finished.connect(self._on_intrinsics_solve_finished)
        self._intrinsics_solve_worker = worker
        total_samples = sum(self._calibration_manager.observations_summary(include_sync_only=False).values())
        progress_message = f"Solving intrinsics ({total_samples} samples)..."
        self._calibration_panel.set_intrinsics_solve_running(True, progress_message)
        self._calibration_panel.show_feedback(
            f"Solving intrinsics in the background ({total_samples} samples)...",
            success=True,
        )
        self._set_status("Solving intrinsics...")
        worker.start()

    def _on_intrinsics_solve_result(self, bundle_obj: object) -> None:
        if not isinstance(bundle_obj, CalibrationBundle):
            self._on_intrinsics_solve_error("Intrinsics solve returned an unexpected result.")
            return

        bundle = bundle_obj
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

    def _on_intrinsics_solve_error(self, message: str) -> None:
        LOGGER.error("Intrinsics solve error: %s", message)
        self._calibration_panel.show_feedback(f"Intrinsics solve failed: {message}", success=False)
        self._set_status(f"Intrinsics solve failed: {message}")

    def _on_intrinsics_solve_finished(self) -> None:
        worker = self._intrinsics_solve_worker
        self._intrinsics_solve_worker = None
        self._calibration_panel.set_intrinsics_solve_running(False)
        self._refresh_calibration_panel(force=True)
        if worker is not None:
            worker.deleteLater()

    def _on_solve_extrinsics(self) -> None:
        if self._intrinsics_solve_worker is not None:
            self._calibration_panel.show_feedback(
                "Wait for the intrinsics solve to finish before solving extrinsics.",
                success=False,
            )
            return
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

    def _on_new_project(self) -> None:
        reply = QMessageBox.question(
            self,
            "New Project",
            (
                "Start a new calibration project?\n\n"
                "This clears captured samples, unloads the active calibration, and prevents the previous "
                "auto-loaded calibration from coming back on restart. Saved profiles stay on disk."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._calibration_manager.reset_all()
        self._latest_calibration_detections.clear()
        self._last_rendered_frame_indices.clear()
        self._current_calibration_bundle = None
        self._calibration_loaded = False
        self._calibration_path = self._default_calibration_path()
        self._last_calibration_detection_at = 0.0

        try:
            if self._calibration_path.exists():
                self._calibration_path.unlink()
        except OSError as exc:
            LOGGER.warning("Could not remove current calibration file %s: %s", self._calibration_path, exc)
            self._calibration_panel.show_feedback(
                "New project started, but the current calibration file could not be removed.",
                success=False,
            )
            self._set_status("New project started; current calibration file still exists")
            self._refresh_calibration_panel(force=True)
            self._update_calibration_preview(force=True)
            return

        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)
        self._calibration_panel.show_feedback("New project started. Previous calibration is unloaded.", success=True)
        self._set_status("New calibration project started")

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
        self._apply_spatial_grid_from_bundle_metadata(bundle)
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
        self._calibration_panel.show_feedback(f"Calibration pattern set to {normalized}.", success=True)
        self._update_calibration_preview(force=True)

    def _on_board_settings_applied(self, settings_obj: object) -> None:
        if not isinstance(settings_obj, CalibrationBoardSettings):
            return
        if self._intrinsics_solve_worker is not None:
            self._calibration_panel.show_feedback(
                "Wait for the intrinsics solve to finish before changing board settings.",
                success=False,
            )
            return
        if settings_obj.charuco_marker_size_m >= settings_obj.charuco_square_size_m:
            self._show_warning("ChArUco marker size must be smaller than ChArUco square size.")
            return
        if settings_obj == self._calibration_manager.board_settings():
            self._calibration_panel.show_feedback("Board settings already active.", success=True)
            return

        has_existing_work = (
            bool(self._calibration_manager.sources())
            or self._calibration_manager.synchronized_capture_count() > 0
            or self._current_calibration_bundle is not None
        )
        if has_existing_work:
            reply = QMessageBox.question(
                self,
                "Apply Board Settings",
                (
                    "Changing board settings clears captured samples and unloads the active calibration. "
                    "Continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._calibration_panel.set_board_settings(self._calibration_manager.board_settings())
                return

        self._calibration_manager.apply_board_settings(settings_obj)
        active_settings = self._calibration_manager.board_settings()
        self._calibration_panel.set_board_settings(active_settings)
        self._calibration_panel.set_pattern_options(
            pattern_names=self._calibration_manager.available_patterns(),
            selected=self._calibration_pattern,
        )
        self._current_calibration_bundle = None
        self._calibration_loaded = False
        self._latest_calibration_detections.clear()
        self._last_rendered_frame_indices.clear()
        self._calibration_path = self._default_calibration_path()
        try:
            if self._calibration_path.exists():
                self._calibration_path.unlink()
        except OSError as exc:
            LOGGER.warning("Could not remove current calibration file %s: %s", self._calibration_path, exc)

        message = (
            "Board settings applied. Samples and active calibration were reset "
            f"(chessboard={active_settings.chessboard_cols}x{active_settings.chessboard_rows}, "
            f"square={active_settings.chessboard_square_size_m * 1000.0:.2f}mm; "
            f"charuco={active_settings.charuco_squares_x}x{active_settings.charuco_squares_y}, "
            f"square={active_settings.charuco_square_size_m * 1000.0:.2f}mm, "
            f"marker={active_settings.charuco_marker_size_m * 1000.0:.2f}mm)."
        )
        self._calibration_panel.show_feedback(message, success=True)
        self._set_status("Board settings applied")
        self._refresh_calibration_panel(force=True)
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
                "Calibration workflow set to Intrinsics: per-camera samples use the intrinsics thresholds."
            )
        self._refresh_threshold_controls_for_mode()
        self._calibration_panel.show_feedback(message, success=True)
        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)

    def _on_acceptance_thresholds_changed(self, min_quality: float, min_coverage_ratio: float) -> None:
        if self._calibration_workflow_mode() == "sync_extrinsics":
            self._calibration_manager.set_sync_acceptance_thresholds(
                min_quality_score=min_quality,
                min_coverage_ratio=min_coverage_ratio,
            )
            message = (
                "Sync thresholds updated: "
                f"quality >= {min_quality:.2f}, coverage >= {min_coverage_ratio * 100.0:.1f}%."
            )
        else:
            self._calibration_manager.set_intrinsics_acceptance_thresholds(
                min_quality_score=min_quality,
                min_coverage_ratio=min_coverage_ratio,
            )
            message = (
                "Intrinsics thresholds updated: "
                f"quality >= {min_quality:.2f}, coverage >= {min_coverage_ratio * 100.0:.1f}%."
            )
        self._calibration_panel.show_feedback(message, success=True)
        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)

    def _on_spatial_grid_changed(self, cols: int, rows: int) -> None:
        self._calibration_manager.set_spatial_coverage_grid(cols=cols, rows=rows)
        max_samples = self._calibration_panel.auto_capture_max_samples()
        target = self._spatial_target_samples_per_cell()
        target_text = (
            f"{target} sample(s) per cell"
            if max_samples > 0
            else "3 sample(s) per cell while Max is unlimited"
        )
        self._calibration_panel.show_feedback(
            f"Overlay grid set to {cols}x{rows}; target is {target_text}.",
            success=True,
        )
        self._refresh_calibration_panel(force=True)
        self._update_calibration_preview(force=True)

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("Worker error: %s", message)
        self._set_status(f"Worker error: {message}")

    def _on_display_tick(self) -> None:
        self._update_calibration_preview()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._intrinsics_solve_worker is not None and self._intrinsics_solve_worker.isRunning():
            QMessageBox.information(
                self,
                "Intrinsics Solve",
                "Intrinsics solve is still running. Wait until it finishes before closing the app.",
            )
            event.ignore()
            return
        self._on_stop_live()
        self._stop_camera_probe_worker()
        super().closeEvent(event)
