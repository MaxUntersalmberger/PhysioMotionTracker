from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from mocap_app.core.config import AppConfig
from mocap_app.io.calibration_io import (
    CalibrationManager,
    CalibrationRepository,
    ChessboardDetectionResult,
)
from mocap_app.models.types import (
    CalibrationBundle,
    CameraProbeResult,
    CameraSourceConfig,
    FramePacket,
    RuntimeTuning,
)
from mocap_app.ui.widgets.calibration_panel import CalibrationPanelWidget
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
        self._active_sources: list[CameraSourceConfig] = []
        self._runtime_tuning = RuntimeTuning()
        self._latest_frames: dict[str, FramePacket] = {}
        self._last_rendered_frame_indices: dict[str, int] = {}
        self._active_camera_count = 0

        self._calibration_panel = CalibrationPanelWidget(
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
        self._calibration_panel.set_workflow_mode("intrinsics")
        self._calibration_panel.set_sync_threshold_values(
            min_quality=self._calibration_manager.sync_min_quality_score,
            min_coverage_ratio=self._calibration_manager.sync_min_coverage_ratio,
        )

        self._load_existing_calibration()
        self._seed_startup_source_slots()
        self._refresh_live_status(force=True)
        self._refresh_calibration_panel(force=True)
        self._set_display_timer_hz(self._runtime_tuning.preview_fps)

        self.setWindowTitle(self._config.app_name)
        self.resize(1500, 920)
        self._set_status("Ready for camera calibration")

    def _setup_ui(self) -> None:
        self.setCentralWidget(self._calibration_panel)
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
        self._calibration_panel.pattern_changed.connect(self._on_calibration_pattern_changed)
        self._calibration_panel.sync_thresholds_changed.connect(self._on_sync_thresholds_changed)
        self._calibration_panel.workflow_mode_changed.connect(self._on_calibration_workflow_mode_changed)

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
        self._set_current_calibration_bundle(bundle)
        if bundle is not None:
            self._set_status(f"Loaded calibration: {self._calibration_path.name}")

    def _set_current_calibration_bundle(self, bundle: CalibrationBundle | None) -> None:
        self._current_calibration_bundle = bundle
        self._calibration_loaded = bundle is not None
        self._refresh_calibration_panel(force=True)

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
        if self._active_sources:
            return [source.source_id for source in self._active_sources]
        if self._latest_frames:
            return sorted(self._latest_frames.keys())
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
                    previews[source_id] = self._calibration_manager.draw_detection_overlay(
                        preview,
                        detection=detection,
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
                    previews[source_id] = self._calibration_manager.draw_detection_overlay(
                        preview,
                        detection=detection,
                    )
        elif not detection_needed and self._latest_calibration_detections:
            self._latest_calibration_detections.clear()
            detections = {}
            self._refresh_calibration_panel(force=True)

        self._calibration_panel.update_previews(previews, detections, sample_counts)
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
            return preview
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

    def _on_worker_error(self, message: str) -> None:
        LOGGER.error("Worker error: %s", message)
        self._set_status(f"Worker error: {message}")

    def _on_display_tick(self) -> None:
        self._update_calibration_preview()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._on_stop_live()
        self._stop_camera_probe_worker()
        super().closeEvent(event)
