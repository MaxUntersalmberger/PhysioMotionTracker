from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import threading

import cv2
import numpy as np

from capture.backend import CaptureBatch
from calibration.diagnostics import acceptance_report_to_metadata, evaluate_calibration_bundle
from models.types import CalibrationBundle, CameraCalibration, FramePacket

CALIBRATION_MODE_INTRINSICS = "intrinsics"
CALIBRATION_MODE_EXTRINSICS = "sync_extrinsics"


@dataclass(slots=True)
class CalibrationCaptureResult:
    sample_counts: dict[str, int]
    synchronized_samples: int
    capture_mode: str = CALIBRATION_MODE_INTRINSICS
    sync_report: "CalibrationSyncReport" | None = None
    detections: dict[str, "CalibrationViewDetection"] = field(default_factory=dict)
    camera_quality_scores: dict[str, CalibrationCameraQuality] = field(default_factory=dict)
    history_entry: CalibrationSampleHistoryEntry | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CalibrationSolveResult:
    bundle: CalibrationBundle
    solved_sources: list[str]
    failed_sources: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CalibrationWorkflowReadiness:
    sample_counts: dict[str, int]
    synchronized_samples: int
    intrinsics_ready_sources: list[str]
    extrinsics_ready_sources: list[str]
    can_solve_intrinsics: bool
    can_solve_extrinsics: bool
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CalibrationCameraQuality:
    source_id: str
    score: float
    visible: bool
    corner_count: int
    expected_corners: int
    coverage_ratio: float
    quality_label: str
    notes: list[str] = field(default_factory=list)

    @property
    def score_text(self) -> str:
        return f"{self.score:.0f}/100"

    @property
    def summary_text(self) -> str:
        visibility_text = "visible" if self.visible else "missing"
        note_text = f" | {'; '.join(self.notes)}" if self.notes else ""
        return (
            f"{visibility_text} | {self.quality_label} | {self.score_text} | "
            f"coverage={self.coverage_ratio:.0%} | corners={self.corner_count}/{self.expected_corners}{note_text}"
        )


@dataclass(slots=True)
class CalibrationSampleHistoryEntry:
    sample_index: int
    recorded_at_iso: str
    frame_index: int
    timestamp_sec: float
    capture_mode: str
    sync_status: str
    detected_sources: list[str]
    missing_sources: list[str]
    camera_scores: dict[str, CalibrationCameraQuality]
    notes: list[str] = field(default_factory=list)

    @property
    def average_score(self) -> float:
        visible_scores = [quality.score for quality in self.camera_scores.values() if quality.visible]
        if not visible_scores:
            return 0.0
        return float(sum(visible_scores) / len(visible_scores))

    @property
    def overall_score(self) -> float:
        sync_multiplier = {
            "ready": 1.0,
            "partial": 0.85,
            "insufficient": 0.65,
        }.get(self.sync_status, 0.6)
        return float(self.average_score * sync_multiplier)

    @property
    def summary_text(self) -> str:
        detected_text = ", ".join(self.detected_sources) if self.detected_sources else "none"
        missing_text = ", ".join(self.missing_sources) if self.missing_sources else "none"
        camera_text = ", ".join(
            f"{source_id} {quality.score:.0f}" for source_id, quality in sorted(self.camera_scores.items())
        )
        return (
            f"#{self.sample_index:02d} {self.recorded_at_iso} | {self.capture_mode} | {self.sync_status} | "
            f"score={self.overall_score:.0f}/100 | seen={detected_text} | missing={missing_text} | {camera_text}"
        )


@dataclass(slots=True)
class CalibrationViewDetection:
    source_id: str
    frame_index: int
    timestamp_sec: float
    image_size: tuple[int, int]
    board_shape: tuple[int, int]
    corner_points_px: list[tuple[float, float]]
    coverage_ratio: float
    visible: bool = True

    @property
    def corner_count(self) -> int:
        return len(self.corner_points_px)


@dataclass(slots=True)
class CalibrationSyncReport:
    total_sources: int
    detected_sources: list[str]
    missing_sources: list[str]
    timestamp_spread_ms: float
    frame_index_spread: int
    status: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _CalibrationDetection:
    source_id: str
    frame_index: int
    timestamp_sec: float
    image_size: tuple[int, int]
    object_points: np.ndarray
    image_points: np.ndarray
    coverage_ratio: float
    pattern_type: str = "chessboard"


@dataclass(slots=True)
class _CalibrationSyncSample:
    frame_index: int
    timestamp_sec: float
    detections: dict[str, _CalibrationDetection]


class CalibrationManager:
    """Collects chessboard samples and solves intrinsics/extrinsics."""

    def __init__(
        self,
        board_shape: tuple[int, int] = (9, 6),
        square_size_m: float = 0.024,
        min_samples_per_camera: int = 6,
        min_synchronized_samples: int = 4,
        reference_source_id: str | None = None,
    ) -> None:
        self._board_shape = _normalize_board_shape(board_shape)
        self._square_size_m = max(1e-6, float(square_size_m))
        self._min_samples_per_camera = max(1, int(min_samples_per_camera))
        self._min_synchronized_samples = max(1, int(min_synchronized_samples))
        self._reference_source_id = reference_source_id
        self._samples_by_source: dict[str, list[_CalibrationDetection]] = {}
        self._sync_samples: list[_CalibrationSyncSample] = []
        self._history_entries: list[CalibrationSampleHistoryEntry] = []
        self._current_bundle: CalibrationBundle | None = None
        self._state_lock = threading.RLock()

    @property
    def board_shape(self) -> tuple[int, int]:
        return self._board_shape

    @property
    def square_size_m(self) -> float:
        return self._square_size_m

    @property
    def current_bundle(self) -> CalibrationBundle | None:
        with self._state_lock:
            return self._current_bundle

    @property
    def synchronized_sample_count(self) -> int:
        with self._state_lock:
            return len(self._sync_samples)

    @property
    def sample_history(self) -> list[CalibrationSampleHistoryEntry]:
        with self._state_lock:
            return list(self._history_entries)

    def sample_counts(self) -> dict[str, int]:
        with self._state_lock:
            return {source_id: len(samples) for source_id, samples in self._samples_by_source.items()}

    def workflow_readiness(self) -> CalibrationWorkflowReadiness:
        with self._state_lock:
            sample_counts = self.sample_counts()
            intrinsics_ready_sources = [
                source_id
                for source_id, count in sorted(sample_counts.items())
                if count >= self._min_samples_per_camera
            ]

            bundle = self._current_bundle
            extrinsics_ready_sources: list[str] = []
            if bundle is not None:
                extrinsics_ready_sources = [
                    source_id
                    for source_id, camera in sorted(bundle.cameras.items())
                    if _camera_has_intrinsics(camera)
                ]

            notes: list[str] = []
            if not sample_counts:
                notes.append("Capture intrinsics samples before solving.")
            for source_id, count in sorted(sample_counts.items()):
                remaining = max(0, self._min_samples_per_camera - count)
                if remaining:
                    notes.append(f"{source_id}: capture {remaining} more intrinsics sample(s).")
            if len(extrinsics_ready_sources) < 2:
                notes.append("Solve intrinsics for at least two cameras before extrinsics.")
            sync_remaining = max(0, self._min_synchronized_samples - len(self._sync_samples))
            if sync_remaining:
                notes.append(f"Capture {sync_remaining} more synchronized extrinsics set(s).")

            return CalibrationWorkflowReadiness(
                sample_counts=sample_counts,
                synchronized_samples=len(self._sync_samples),
                intrinsics_ready_sources=intrinsics_ready_sources,
                extrinsics_ready_sources=extrinsics_ready_sources,
                can_solve_intrinsics=bool(intrinsics_ready_sources),
                can_solve_extrinsics=len(extrinsics_ready_sources) >= 2
                and len(self._sync_samples) >= self._min_synchronized_samples,
                notes=notes,
            )

    def set_board_geometry(self, board_shape: tuple[int, int], square_size_m: float | None = None) -> None:
        with self._state_lock:
            normalized_shape = _normalize_board_shape(board_shape)
            normalized_square_size = self._square_size_m if square_size_m is None else max(1e-6, float(square_size_m))
            if normalized_shape != self._board_shape or normalized_square_size != self._square_size_m:
                self.reset_samples()
            self._board_shape = normalized_shape
            self._square_size_m = normalized_square_size

    def set_bundle(self, bundle: CalibrationBundle | None) -> None:
        with self._state_lock:
            self._current_bundle = bundle

    def reset_samples(self) -> None:
        with self._state_lock:
            self._samples_by_source.clear()
            self._sync_samples.clear()
            self._history_entries.clear()

    def capture_sample(self, batch: CaptureBatch, capture_mode: str = CALIBRATION_MODE_INTRINSICS) -> CalibrationCaptureResult:
        return self.capture_frames(batch.frames, record_sample=True, capture_mode=capture_mode)

    def inspect_frames(self, frames: dict[str, FramePacket]) -> CalibrationCaptureResult:
        return self.capture_frames(frames, record_sample=False)

    def capture_frames(
        self,
        frames: dict[str, FramePacket],
        record_sample: bool = True,
        capture_mode: str = CALIBRATION_MODE_INTRINSICS,
    ) -> CalibrationCaptureResult:
        with self._state_lock:
            normalized_mode = _normalize_calibration_mode(capture_mode)
            notes: list[str] = []
            synchronized: dict[str, _CalibrationDetection] = {}
            public_detections: dict[str, CalibrationViewDetection] = {}

            for source_id, frame in frames.items():
                detection = self._detect_calibration_board(source_id, frame)
                if detection is None:
                    notes.append(f"{source_id}: no calibration board detected.")
                    continue

                synchronized[source_id] = detection
                public_detections[source_id] = self._to_public_detection(detection)
                if record_sample and normalized_mode == CALIBRATION_MODE_INTRINSICS:
                    self._samples_by_source.setdefault(source_id, []).append(detection)
                if not record_sample:
                    action_text = "detected board"
                elif normalized_mode == CALIBRATION_MODE_INTRINSICS:
                    action_text = "stored intrinsics sample"
                else:
                    action_text = "detected extrinsics candidate"
                notes.append(
                    f"{source_id}: {action_text} with {detection.image_points.shape[0]} corners "
                    f"({detection.coverage_ratio:.0%} coverage)."
                )

            sync_report = self._build_sync_report(frames, synchronized)
            notes.extend(sync_report.notes)

            camera_quality_scores = self._build_camera_quality_scores(synchronized, sync_report, frames)
            history_entry: CalibrationSampleHistoryEntry | None = None
            if record_sample:
                history_entry = CalibrationSampleHistoryEntry(
                    sample_index=len(self._history_entries) + 1,
                    recorded_at_iso=datetime.now().isoformat(timespec="seconds"),
                    frame_index=max((frame.frame_index for frame in frames.values()), default=0),
                    timestamp_sec=max((frame.timestamp_sec for frame in frames.values()), default=0.0),
                    capture_mode=normalized_mode,
                    sync_status=sync_report.status,
                    detected_sources=list(sync_report.detected_sources),
                    missing_sources=list(sync_report.missing_sources),
                    camera_scores=dict(camera_quality_scores),
                    notes=list(sync_report.notes),
                )
                self._history_entries.append(history_entry)

            if record_sample and normalized_mode == CALIBRATION_MODE_EXTRINSICS and len(synchronized) >= 2:
                first_detection = next(iter(synchronized.values()))
                self._sync_samples.append(
                    _CalibrationSyncSample(
                        frame_index=first_detection.frame_index,
                        timestamp_sec=first_detection.timestamp_sec,
                        detections=dict(synchronized),
                    )
                )
                notes.append(f"Stored synchronized extrinsics sample for {len(synchronized)} cameras.")
            elif record_sample and normalized_mode == CALIBRATION_MODE_EXTRINSICS and synchronized:
                notes.append("Need at least two cameras seeing the board to store an extrinsics sample.")
            elif record_sample and normalized_mode == CALIBRATION_MODE_INTRINSICS and synchronized:
                notes.append("Stored intrinsics samples only; switch to Sync / Extrinsics for synchronized sets.")

            return CalibrationCaptureResult(
                sample_counts=self.sample_counts(),
                synchronized_samples=len(self._sync_samples),
                capture_mode=normalized_mode,
                sync_report=sync_report,
                detections=public_detections,
                camera_quality_scores=camera_quality_scores,
                history_entry=history_entry,
                notes=notes,
            )

    def solve_intrinsics(self) -> CalibrationSolveResult:
        with self._state_lock:
            notes: list[str] = []
            solved_sources: list[str] = []
            failed_sources: list[str] = []
            cameras: dict[str, CameraCalibration] = {}
            if self._current_bundle is not None:
                cameras = dict(self._current_bundle.cameras)

            for source_id, samples in sorted(self._samples_by_source.items()):
                source_notes, camera = self._solve_camera_intrinsics(source_id, samples)
                notes.extend(source_notes)
                if camera is None:
                    if source_id not in cameras:
                        failed_sources.append(source_id)
                    else:
                        notes.append(f"{source_id}: keeping the previously loaded calibration entry.")
                    continue
                solved_sources.append(source_id)
                cameras[source_id] = camera

            if not cameras:
                notes.append("No calibration samples were captured.")

            bundle = CalibrationBundle(
                cameras=cameras,
                notes=notes,
                metadata={
                    "board_shape": list(self._board_shape),
                    "square_size_m": self._square_size_m,
                    "min_samples_per_camera": self._min_samples_per_camera,
                    "min_synchronized_samples": self._min_synchronized_samples,
                    "intrinsics_solved_at_iso": datetime.now().isoformat(timespec="seconds"),
                    "sample_counts": self.sample_counts(),
                    "synchronized_samples": len(self._sync_samples),
                    "calibration_version": _calibration_version(),
                    "bundle_adjustment_status": "not_run",
                    "bundle_adjustment_notes": ["Bundle adjustment runs after synchronized extrinsics are solved."],
                },
            )
            bundle.metadata.update(acceptance_report_to_metadata(evaluate_calibration_bundle(bundle)))
            self._current_bundle = bundle
            return CalibrationSolveResult(
                bundle=bundle,
                solved_sources=solved_sources,
                failed_sources=failed_sources,
                notes=notes,
            )

    def solve_extrinsics(self) -> CalibrationSolveResult:
        with self._state_lock:
            bundle = self._current_bundle
            if bundle is None:
                raise RuntimeError("Solve intrinsics before solving extrinsics.")

            notes = list(bundle.notes)
            if len(bundle.cameras) < 2:
                notes.append("At least two calibrated cameras are required to solve extrinsics.")
                return CalibrationSolveResult(bundle=bundle, solved_sources=[], failed_sources=list(bundle.cameras), notes=notes)

            calibrated_sources = [source_id for source_id, camera in bundle.cameras.items() if _camera_has_intrinsics(camera)]
            if len(calibrated_sources) < 2:
                notes.append("At least two cameras need solved intrinsics before extrinsics can be computed.")
                return CalibrationSolveResult(bundle=bundle, solved_sources=[], failed_sources=list(bundle.cameras), notes=notes)

            reference_source_id = self._resolve_reference_source(bundle, calibrated_sources)
            if reference_source_id is None:
                notes.append("Could not determine a reference camera for extrinsics.")
                return CalibrationSolveResult(bundle=bundle, solved_sources=[], failed_sources=list(bundle.cameras), notes=notes)

            transforms_by_source: dict[str, list[np.ndarray]] = {reference_source_id: [np.eye(4, dtype=np.float64)]}
            useable_sync_samples = 0

            for sync_sample in self._sync_samples:
                usable_detections = {
                    source_id: detection
                    for source_id, detection in sync_sample.detections.items()
                    if source_id in calibrated_sources
                }
                if reference_source_id not in usable_detections or len(usable_detections) < 2:
                    continue

                reference_transform = self._solve_board_transform(
                    bundle.cameras[reference_source_id],
                    usable_detections[reference_source_id],
                )
                if reference_transform is None:
                    continue

                sample_success = 0
                for source_id, detection in usable_detections.items():
                    transform = self._solve_board_transform(bundle.cameras[source_id], detection)
                    if transform is None:
                        continue
                    relative_transform = transform @ np.linalg.inv(reference_transform)
                    transforms_by_source.setdefault(source_id, []).append(relative_transform)
                    sample_success += 1

                if sample_success >= 2:
                    useable_sync_samples += 1

            if useable_sync_samples < self._min_synchronized_samples:
                notes.append(
                    f"Need at least {self._min_synchronized_samples} synchronized calibration samples; "
                    f"only {useable_sync_samples} usable sample(s) were found."
                )
                return CalibrationSolveResult(bundle=bundle, solved_sources=[], failed_sources=list(bundle.cameras), notes=notes)

            updated_cameras: dict[str, CameraCalibration] = {}
            solved_sources: list[str] = []
            failed_sources: list[str] = []

            for source_id, camera in bundle.cameras.items():
                if source_id == reference_source_id:
                    updated_cameras[source_id] = CameraCalibration(
                        source_id=source_id,
                        status="solved",
                        num_samples=camera.num_samples,
                        image_size=camera.image_size,
                        intrinsics=camera.intrinsics,
                        distortion=camera.distortion,
                        rotation=np.eye(3, dtype=np.float64).reshape(-1).tolist(),
                        translation=[0.0, 0.0, 0.0],
                        reprojection_error_px=camera.reprojection_error_px,
                        diagnostics=list(camera.diagnostics)
                        + [f"Reference camera for extrinsics: {reference_source_id}."]
                        + [f"Used {useable_sync_samples} synchronized sample(s)."],
                        calibrated_at_iso=datetime.now().isoformat(timespec="seconds"),
                    )
                    solved_sources.append(source_id)
                    continue

                transforms = transforms_by_source.get(source_id)
                if not transforms:
                    updated_cameras[source_id] = CameraCalibration(
                        source_id=source_id,
                        status=camera.status,
                        num_samples=camera.num_samples,
                        image_size=camera.image_size,
                        intrinsics=camera.intrinsics,
                        distortion=camera.distortion,
                        rotation=camera.rotation,
                        translation=camera.translation,
                        reprojection_error_px=camera.reprojection_error_px,
                        diagnostics=list(camera.diagnostics) + ["Extrinsics not solved for this camera."],
                        calibrated_at_iso=camera.calibrated_at_iso,
                    )
                    failed_sources.append(source_id)
                    continue

                mean_transform = _average_transforms(transforms)
                updated_cameras[source_id] = CameraCalibration(
                    source_id=source_id,
                    status="solved",
                    num_samples=camera.num_samples,
                    image_size=camera.image_size,
                    intrinsics=camera.intrinsics,
                    distortion=camera.distortion,
                    rotation=mean_transform[:3, :3].reshape(-1).tolist(),
                    translation=mean_transform[:3, 3].reshape(-1).tolist(),
                    reprojection_error_px=camera.reprojection_error_px,
                    diagnostics=list(camera.diagnostics)
                    + [f"Extrinsics solved from {len(transforms)} synchronized sample(s)."],
                    calibrated_at_iso=datetime.now().isoformat(timespec="seconds"),
                )
                solved_sources.append(source_id)

            notes.append(f"Solved extrinsics using reference camera {reference_source_id}.")
            notes.append(f"Synchronized calibration samples used: {useable_sync_samples}.")

            updated_bundle = CalibrationBundle(
                cameras=updated_cameras,
                notes=notes,
                metadata={
                    **dict(bundle.metadata),
                    "reference_source_id": reference_source_id,
                    "extrinsics_solved_at_iso": datetime.now().isoformat(timespec="seconds"),
                    "used_synchronized_samples": useable_sync_samples,
                    "calibration_version": _calibration_version(),
                },
            )
            updated_bundle = self._refine_extrinsics_with_stereo_calibration(
                updated_bundle,
                reference_source_id,
                solved_sources,
            )
            updated_bundle.metadata.update(acceptance_report_to_metadata(evaluate_calibration_bundle(updated_bundle)))
            self._current_bundle = updated_bundle
            return CalibrationSolveResult(
                bundle=updated_bundle,
                solved_sources=solved_sources,
                failed_sources=failed_sources,
                notes=notes,
            )

    def _refine_extrinsics_with_stereo_calibration(
        self,
        bundle: CalibrationBundle,
        reference_source_id: str,
        solved_sources: list[str],
    ) -> CalibrationBundle:
        reference_camera = bundle.cameras.get(reference_source_id)
        if reference_camera is None or not _camera_has_intrinsics(reference_camera):
            return _bundle_with_adjustment_metadata(
                bundle,
                status="skipped",
                notes=["Bundle refinement skipped because the reference camera has no intrinsics."],
                pair_errors={},
            )

        updated_cameras = dict(bundle.cameras)
        adjustment_notes: list[str] = []
        pair_errors: dict[str, float] = {}

        for source_id in sorted(set(solved_sources)):
            if source_id == reference_source_id:
                continue
            camera = updated_cameras.get(source_id)
            if camera is None or not _camera_has_intrinsics(camera):
                adjustment_notes.append(f"{source_id}: skipped refinement because intrinsics are incomplete.")
                continue
            if camera.rotation is None or camera.translation is None:
                adjustment_notes.append(f"{source_id}: skipped refinement because initial extrinsics are missing.")
                continue

            observations = self._stereo_observations_for_pair(reference_source_id, source_id)
            if len(observations) < self._min_synchronized_samples:
                adjustment_notes.append(
                    f"{source_id}: skipped refinement; {len(observations)} usable stereo observation(s) available."
                )
                continue

            refined = self._run_pairwise_stereo_refinement(
                reference_camera=reference_camera,
                source_camera=camera,
                observations=observations,
            )
            if refined is None:
                adjustment_notes.append(f"{source_id}: OpenCV stereo refinement failed.")
                continue

            rms, rotation_matrix, translation_vector = refined
            pair_key = f"{reference_source_id}->{source_id}"
            pair_errors[pair_key] = rms
            updated_cameras[source_id] = CameraCalibration(
                source_id=source_id,
                status="solved",
                num_samples=camera.num_samples,
                image_size=camera.image_size,
                intrinsics=camera.intrinsics,
                distortion=camera.distortion,
                rotation=rotation_matrix.reshape(-1).tolist(),
                translation=translation_vector.reshape(-1).tolist(),
                reprojection_error_px=camera.reprojection_error_px,
                diagnostics=list(camera.diagnostics)
                + [f"Extrinsics refined with fixed-intrinsics stereo calibration; RMS={rms:.4f}px."],
                calibrated_at_iso=datetime.now().isoformat(timespec="seconds"),
            )
            adjustment_notes.append(f"{source_id}: refined against {reference_source_id}; RMS={rms:.4f}px.")

        status = "refined" if pair_errors else "skipped"
        if not adjustment_notes:
            adjustment_notes.append("No non-reference cameras were available for bundle refinement.")

        return _bundle_with_adjustment_metadata(
            CalibrationBundle(
                cameras=updated_cameras,
                notes=list(bundle.notes) + adjustment_notes,
                metadata=dict(bundle.metadata),
            ),
            status=status,
            notes=adjustment_notes,
            pair_errors=pair_errors,
        )

    def _stereo_observations_for_pair(
        self,
        reference_source_id: str,
        source_id: str,
    ) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]]:
        observations: list[tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]] = []
        for sync_sample in self._sync_samples:
            reference_detection = sync_sample.detections.get(reference_source_id)
            source_detection = sync_sample.detections.get(source_id)
            if reference_detection is None or source_detection is None:
                continue
            if reference_detection.image_size != source_detection.image_size:
                continue
            if reference_detection.object_points.shape != source_detection.object_points.shape:
                continue
            if not np.allclose(reference_detection.object_points, source_detection.object_points, atol=1e-6):
                continue

            observations.append(
                (
                    reference_detection.object_points.astype(np.float32).reshape(-1, 3),
                    reference_detection.image_points.astype(np.float32).reshape(-1, 1, 2),
                    source_detection.image_points.astype(np.float32).reshape(-1, 1, 2),
                    reference_detection.image_size,
                )
            )
        return observations

    def _run_pairwise_stereo_refinement(
        self,
        reference_camera: CameraCalibration,
        source_camera: CameraCalibration,
        observations: list[tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]],
    ) -> tuple[float, np.ndarray, np.ndarray] | None:
        object_points = [item[0] for item in observations]
        reference_points = [item[1] for item in observations]
        source_points = [item[2] for item in observations]
        image_size = observations[0][3]

        reference_matrix = _camera_matrix(reference_camera, image_size)
        source_matrix = _camera_matrix(source_camera, image_size)
        if reference_matrix is None or source_matrix is None:
            return None

        initial_rotation = _rotation_matrix_from_values(source_camera.rotation)
        initial_translation = _translation_vector_from_values(source_camera.translation)
        if initial_rotation is None or initial_translation is None:
            return None

        flags = cv2.CALIB_FIX_INTRINSIC
        if hasattr(cv2, "CALIB_USE_EXTRINSIC_GUESS"):
            flags |= cv2.CALIB_USE_EXTRINSIC_GUESS

        try:
            rms, _cm1, _dc1, _cm2, _dc2, rotation, translation, _essential, _fundamental = cv2.stereoCalibrate(
                object_points,
                reference_points,
                source_points,
                reference_matrix,
                _distortion_array(reference_camera),
                source_matrix,
                _distortion_array(source_camera),
                image_size,
                initial_rotation,
                initial_translation.reshape(3, 1),
                flags=flags,
                criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 80, 1e-6),
            )
        except Exception:
            return None

        return float(rms), np.asarray(rotation, dtype=np.float64).reshape(3, 3), np.asarray(translation, dtype=np.float64).reshape(3)

    def _solve_camera_intrinsics(
        self,
        source_id: str,
        samples: list[_CalibrationDetection],
    ) -> tuple[list[str], CameraCalibration | None]:
        notes: list[str] = []
        if len(samples) < self._min_samples_per_camera:
            notes.append(
                f"{source_id}: need at least {self._min_samples_per_camera} sample(s), got {len(samples)}."
            )
            return notes, None

        grouped_samples = [sample for sample in samples if sample.image_points.shape[0] >= 4]
        if len(grouped_samples) < self._min_samples_per_camera:
            notes.append(f"{source_id}: too few usable samples after filtering.")
            return notes, None

        image_size = self._most_common_image_size(grouped_samples)
        object_points = [sample.object_points for sample in grouped_samples if sample.image_size == image_size]
        image_points = [sample.image_points for sample in grouped_samples if sample.image_size == image_size]
        if len(object_points) < self._min_samples_per_camera:
            notes.append(
                f"{source_id}: insufficient samples with consistent image size {image_size[0]}x{image_size[1]}."
            )
            return notes, None

        try:
            rms, camera_matrix, dist_coeffs, _rvecs, _tvecs = cv2.calibrateCamera(
                object_points,
                image_points,
                image_size,
                None,
                None,
            )
        except Exception as exc:
            notes.append(f"{source_id}: intrinsics solve failed ({exc}).")
            return notes, None

        notes.append(
            f"{source_id}: intrinsics solved from {len(object_points)} sample(s) with reprojection error {float(rms):.3f}px."
        )
        return notes, CameraCalibration(
            source_id=source_id,
            status="intrinsics_solved",
            num_samples=len(object_points),
            image_size=image_size,
            intrinsics=camera_matrix.tolist(),
            distortion=dist_coeffs.reshape(-1).tolist(),
            rotation=None,
            translation=None,
            reprojection_error_px=float(rms),
            diagnostics=[
                f"Detected {len(object_points)} usable calibration frame(s).",
                f"Board shape: {self._board_shape[0]}x{self._board_shape[1]} inner corners.",
                f"Square size: {self._square_size_m:.4f} m.",
            ],
            calibrated_at_iso=datetime.now().isoformat(timespec="seconds"),
        )

    def _detect_calibration_board(self, source_id: str, frame: FramePacket) -> _CalibrationDetection | None:
        image = frame.frame_data
        if image is None or not hasattr(image, "shape"):
            return None

        array = np.asarray(image)
        if array.ndim == 2:
            gray = array
        elif array.ndim >= 3:
            gray = cv2.cvtColor(array[:, :, :3], cv2.COLOR_BGR2GRAY)
        else:
            return None

        corners = None
        found = False
        pattern_size = self._board_shape

        try:
            charuco_detection = self._detect_charuco_board(source_id, frame, gray)
            if charuco_detection is not None:
                return charuco_detection

            if hasattr(cv2, "findChessboardCornersSB"):
                found, corners = cv2.findChessboardCornersSB(
                    gray,
                    pattern_size,
                    flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_NORMALIZE_IMAGE,
                )

            if not found:
                found, corners = cv2.findChessboardCorners(
                    gray,
                    pattern_size,
                    flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
                )
                if not found:
                    return None
                corners = cv2.cornerSubPix(
                    gray,
                    corners,
                    winSize=(11, 11),
                    zeroZone=(-1, -1),
                    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
                )
        except cv2.error:
            return None

        if corners is None:
            return None

        image_height, image_width = gray.shape[:2]
        object_points = _board_object_points(pattern_size, self._square_size_m)
        image_points = corners.reshape(-1, 1, 2).astype(np.float32)
        coverage_ratio = _estimate_coverage_ratio(corners.reshape(-1, 2), image_width, image_height)
        return _CalibrationDetection(
            source_id=source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            image_size=(int(image_width), int(image_height)),
            object_points=object_points,
            image_points=image_points,
            coverage_ratio=coverage_ratio,
            pattern_type="chessboard",
        )

    def _detect_charuco_board(self, source_id: str, frame: FramePacket, gray: np.ndarray) -> _CalibrationDetection | None:
        aruco = getattr(cv2, "aruco", None)
        if aruco is None:
            return None
        required = ("getPredefinedDictionary", "detectMarkers", "interpolateCornersCharuco")
        if not all(hasattr(aruco, name) for name in required):
            return None

        try:
            dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
            board = _create_charuco_board(aruco, self._board_shape, self._square_size_m)
            if board is None:
                return None
            marker_corners, marker_ids, _rejected = aruco.detectMarkers(gray, dictionary)
            if marker_ids is None or len(marker_ids) == 0:
                return None
            _count, charuco_corners, charuco_ids = aruco.interpolateCornersCharuco(
                marker_corners,
                marker_ids,
                gray,
                board,
            )
        except Exception:
            return None

        if charuco_corners is None or charuco_ids is None or len(charuco_corners) < 4:
            return None

        object_points = _charuco_object_points(board, charuco_ids)
        if object_points is None or len(object_points) != len(charuco_corners):
            return None

        image_height, image_width = gray.shape[:2]
        image_points = np.asarray(charuco_corners, dtype=np.float32).reshape(-1, 1, 2)
        coverage_ratio = _estimate_coverage_ratio(image_points.reshape(-1, 2), image_width, image_height)
        return _CalibrationDetection(
            source_id=source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            image_size=(int(image_width), int(image_height)),
            object_points=np.asarray(object_points, dtype=np.float32).reshape(-1, 3),
            image_points=image_points,
            coverage_ratio=coverage_ratio,
            pattern_type="charuco",
        )

    def _solve_board_transform(
        self,
        camera: CameraCalibration,
        detection: _CalibrationDetection,
    ) -> np.ndarray | None:
        camera_matrix = _camera_matrix(camera, detection.image_size)
        if camera_matrix is None:
            return None

        dist_coeffs = _distortion_array(camera)
        success, rvec, tvec = cv2.solvePnP(
            detection.object_points,
            detection.image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return None

        rotation_matrix, _ = cv2.Rodrigues(rvec)
        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = rotation_matrix
        transform[:3, 3] = tvec.reshape(3)
        return transform

    def _resolve_reference_source(self, bundle: CalibrationBundle, calibrated_sources: list[str]) -> str | None:
        reference_source_id = bundle.metadata.get("reference_source_id")
        if isinstance(reference_source_id, str) and reference_source_id in calibrated_sources:
            return reference_source_id
        if self._reference_source_id and self._reference_source_id in calibrated_sources:
            return self._reference_source_id
        return calibrated_sources[0] if calibrated_sources else None

    def _most_common_image_size(self, samples: list[_CalibrationDetection]) -> tuple[int, int]:
        counts: dict[tuple[int, int], int] = {}
        for sample in samples:
            counts[sample.image_size] = counts.get(sample.image_size, 0) + 1
        return max(counts, key=counts.get)

    def _build_sync_report(
        self,
        frames: dict[str, FramePacket],
        synchronized: dict[str, _CalibrationDetection],
    ) -> CalibrationSyncReport:
        total_sources = len(frames)
        detected_sources = sorted(synchronized)
        missing_sources = [source_id for source_id in frames if source_id not in synchronized]
        timestamps = [frame.timestamp_sec for frame in frames.values()]
        frame_indices = [frame.frame_index for frame in frames.values()]

        timestamp_spread_ms = 0.0
        if timestamps:
            timestamp_spread_ms = (max(timestamps) - min(timestamps)) * 1000.0

        frame_index_spread = 0
        if frame_indices:
            frame_index_spread = max(frame_indices) - min(frame_indices)

        notes: list[str] = []
        if total_sources < 2:
            status = "insufficient"
            notes.append("Connect at least two cameras before solving calibration.")
        elif len(detected_sources) < 2:
            status = "insufficient"
            notes.append("The chessboard must be visible in at least two cameras for a usable sample.")
        else:
            status = "ready"
            if missing_sources:
                status = "partial"
                notes.append("Board not visible in: " + ", ".join(missing_sources) + ".")
            if frame_index_spread > 0:
                status = "partial"
                notes.append(f"Frame indices differ across cameras by {frame_index_spread}.")
            if timestamp_spread_ms > 40.0:
                status = "partial"
                notes.append(f"Batch timestamp spread is {timestamp_spread_ms:.1f} ms.")

        if status == "ready":
            notes.append("Camera sync check passed: all active cameras captured the same batch.")
        elif status == "partial" and len(detected_sources) >= 2:
            notes.append("Sample stored, but sync is partial. Re-capture with the board visible in every camera if possible.")

        return CalibrationSyncReport(
            total_sources=total_sources,
            detected_sources=detected_sources,
            missing_sources=missing_sources,
            timestamp_spread_ms=timestamp_spread_ms,
            frame_index_spread=frame_index_spread,
            status=status,
            notes=notes,
        )

    def _build_camera_quality_scores(
        self,
        synchronized: dict[str, _CalibrationDetection],
        sync_report: CalibrationSyncReport,
        frames: dict[str, FramePacket],
    ) -> dict[str, CalibrationCameraQuality]:
        expected_corners = max(1, self._board_shape[0] * self._board_shape[1])
        quality_scores: dict[str, CalibrationCameraQuality] = {}

        for source_id in frames:
            detection = synchronized.get(source_id)
            if detection is None:
                quality_scores[source_id] = CalibrationCameraQuality(
                    source_id=source_id,
                    score=0.0,
                    visible=False,
                    corner_count=0,
                    expected_corners=expected_corners,
                    coverage_ratio=0.0,
                    quality_label="missing",
                    notes=["No chessboard detected in this camera."],
                )
                continue

            coverage_score = float(np.clip(detection.coverage_ratio / 0.20, 0.0, 1.0))
            corner_score = float(np.clip(detection.image_points.shape[0] / float(expected_corners), 0.0, 1.0))
            score = 100.0 * ((0.85 * coverage_score) + (0.15 * corner_score))
            quality_scores[source_id] = CalibrationCameraQuality(
                source_id=source_id,
                score=float(np.clip(score, 0.0, 100.0)),
                visible=True,
                corner_count=int(detection.image_points.shape[0]),
                expected_corners=expected_corners,
                coverage_ratio=float(detection.coverage_ratio),
                quality_label=_quality_label(score),
                notes=self._quality_notes(detection, sync_report),
            )

        return quality_scores

    def _to_public_detection(self, detection: _CalibrationDetection) -> CalibrationViewDetection:
        corner_points_px = [tuple(map(float, point)) for point in detection.image_points.reshape(-1, 2)]
        return CalibrationViewDetection(
            source_id=detection.source_id,
            frame_index=detection.frame_index,
            timestamp_sec=detection.timestamp_sec,
            image_size=detection.image_size,
            board_shape=self._board_shape,
            corner_points_px=corner_points_px,
            coverage_ratio=detection.coverage_ratio,
            visible=True,
        )

    def _quality_notes(self, detection: _CalibrationDetection, sync_report: CalibrationSyncReport) -> list[str]:
        notes: list[str] = []
        if detection.coverage_ratio < 0.08:
            notes.append("Board is small in frame; move the camera closer or enlarge the board.")
        elif detection.coverage_ratio > 0.20:
            notes.append("Board fills the frame well.")
        else:
            notes.append("Board coverage looks usable.")

        if sync_report.status == "partial":
            notes.append("Sync is partial; capture again with the board visible in every camera.")
        elif sync_report.status == "insufficient":
            notes.append("Need at least two cameras with a visible board for a valid sample.")

        return notes


def _board_object_points(board_shape: tuple[int, int], square_size_m: float) -> np.ndarray:
    columns, rows = board_shape
    object_points = np.zeros((rows * columns, 3), dtype=np.float32)
    grid = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2)
    object_points[:, :2] = grid * float(square_size_m)
    return object_points


def _create_charuco_board(aruco, board_shape: tuple[int, int], square_size_m: float):
    columns, rows = board_shape
    marker_size = float(square_size_m) * 0.72
    try:
        if hasattr(aruco, "CharucoBoard"):
            dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
            return aruco.CharucoBoard((columns + 1, rows + 1), float(square_size_m), marker_size, dictionary)
        if hasattr(aruco, "CharucoBoard_create"):
            dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
            return aruco.CharucoBoard_create(columns + 1, rows + 1, float(square_size_m), marker_size, dictionary)
    except Exception:
        return None
    return None


def _charuco_object_points(board, charuco_ids: np.ndarray) -> np.ndarray | None:
    try:
        corners = board.getChessboardCorners()
    except Exception:
        corners = getattr(board, "chessboardCorners", None)
    if corners is None:
        return None
    all_corners = np.asarray(corners, dtype=np.float32).reshape(-1, 3)
    ids = np.asarray(charuco_ids, dtype=np.int32).reshape(-1)
    if ids.size == 0 or np.max(ids) >= len(all_corners):
        return None
    return all_corners[ids]


def _calibration_version() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def _normalize_board_shape(board_shape: tuple[int, int]) -> tuple[int, int]:
    columns = max(2, int(board_shape[0]))
    rows = max(2, int(board_shape[1]))
    return columns, rows


def _normalize_calibration_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"extrinsics", "sync", "sync_extrinsics", "synchronized", "synchronised"}:
        return CALIBRATION_MODE_EXTRINSICS
    return CALIBRATION_MODE_INTRINSICS


def _estimate_coverage_ratio(corners: np.ndarray, image_width: int, image_height: int) -> float:
    if image_width <= 0 or image_height <= 0 or corners.size == 0:
        return 0.0
    min_x = float(np.min(corners[:, 0]))
    max_x = float(np.max(corners[:, 0]))
    min_y = float(np.min(corners[:, 1]))
    max_y = float(np.max(corners[:, 1]))
    area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
    total = float(image_width * image_height)
    return float(np.clip(area / total, 0.0, 1.0))


def _quality_label(score: float) -> str:
    if score >= 80.0:
        return "strong"
    if score >= 55.0:
        return "usable"
    if score >= 25.0:
        return "weak"
    return "poor"


def _camera_has_intrinsics(camera: CameraCalibration) -> bool:
    if camera.intrinsics is None:
        return False

    try:
        matrix = np.asarray(camera.intrinsics, dtype=np.float64)
    except (TypeError, ValueError):
        return False

    return matrix.shape == (3, 3)


def _camera_matrix(camera: CameraCalibration, target_image_size: tuple[int, int]) -> np.ndarray | None:
    if camera.intrinsics is None:
        return None

    matrix = np.asarray(camera.intrinsics, dtype=np.float64)
    if matrix.shape != (3, 3):
        return None

    source_image_size = camera.image_size or target_image_size
    if source_image_size != target_image_size and source_image_size[0] > 0 and source_image_size[1] > 0:
        scale_x = target_image_size[0] / float(source_image_size[0])
        scale_y = target_image_size[1] / float(source_image_size[1])
        scaled = matrix.copy()
        scaled[0, 0] *= scale_x
        scaled[1, 1] *= scale_y
        scaled[0, 2] *= scale_x
        scaled[1, 2] *= scale_y
        return scaled

    return matrix


def _distortion_array(camera: CameraCalibration) -> np.ndarray:
    if camera.distortion is None:
        return np.zeros((5, 1), dtype=np.float64)
    return np.asarray(camera.distortion, dtype=np.float64).reshape(-1, 1)


def _rotation_matrix_from_values(values: list[float] | None) -> np.ndarray | None:
    if values is None:
        return None
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if array.size == 9:
        return array.reshape(3, 3)
    if array.size == 3:
        rotation, _jacobian = cv2.Rodrigues(array.reshape(3, 1))
        return rotation
    return None


def _translation_vector_from_values(values: list[float] | None) -> np.ndarray | None:
    if values is None:
        return None
    try:
        array = np.asarray(values, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size != 3:
        return None
    return array


def _bundle_with_adjustment_metadata(
    bundle: CalibrationBundle,
    status: str,
    notes: list[str],
    pair_errors: dict[str, float],
) -> CalibrationBundle:
    metadata = dict(bundle.metadata)
    metadata.update(
        {
            "bundle_adjustment_status": status,
            "bundle_adjustment_method": "opencv_stereoCalibrate_fixed_intrinsics",
            "bundle_adjustment_pair_rms_px": dict(pair_errors),
            "bundle_adjustment_notes": list(notes),
            "bundle_adjustment_updated_at_iso": datetime.now().isoformat(timespec="seconds"),
        }
    )
    return CalibrationBundle(cameras=dict(bundle.cameras), notes=list(bundle.notes), metadata=metadata)


def _average_transforms(transforms: list[np.ndarray]) -> np.ndarray:
    if not transforms:
        return np.eye(4, dtype=np.float64)

    rotations = np.stack([transform[:3, :3] for transform in transforms], axis=0)
    translations = np.stack([transform[:3, 3] for transform in transforms], axis=0)
    mean_rotation = rotations.mean(axis=0)
    u_matrix, _singular_values, vt_matrix = np.linalg.svd(mean_rotation)
    rotation = u_matrix @ vt_matrix
    if np.linalg.det(rotation) < 0:
        u_matrix[:, -1] *= -1
        rotation = u_matrix @ vt_matrix

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = rotation
    transform[:3, 3] = translations.mean(axis=0)
    return transform
