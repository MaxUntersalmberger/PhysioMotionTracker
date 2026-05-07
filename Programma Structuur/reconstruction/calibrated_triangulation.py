from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import cv2
import numpy as np

from models.types import CalibrationBundle, CameraCalibration, FramePacket, Pose2DKeypoint, Pose3D, Pose3DKeypoint

from pipeline.contracts import PoseTriangulator, TriangulationResult


@dataclass(slots=True)
class _CameraProjection:
    source_id: str
    camera_matrix: np.ndarray
    distortion: np.ndarray
    rotation_matrix: np.ndarray
    translation_vector: np.ndarray
    image_size: tuple[int, int]

    def normalized_projection_matrix(self) -> np.ndarray:
        return np.hstack([self.rotation_matrix, self.translation_vector.reshape(3, 1)])

    def projection_matrix(self) -> np.ndarray:
        return self.camera_matrix @ self.normalized_projection_matrix()

    def rvec(self) -> np.ndarray:
        rotation_vector, _ = cv2.Rodrigues(self.rotation_matrix)
        return rotation_vector


@dataclass(slots=True)
class _PreparedObservation:
    projection: _CameraProjection
    image_point_px: np.ndarray
    keypoint: Pose2DKeypoint


@dataclass(slots=True)
class _RobustJointResult:
    point_3d: np.ndarray
    observations: list[_PreparedObservation]
    reprojections_px: dict[str, tuple[float, float]]
    mean_error_px: float
    confidence: float
    excluded_sources: list[str] = field(default_factory=list)


class CalibratedTriangulator(PoseTriangulator):
    name = "calibrated_multiview_triangulator"

    def __init__(
        self,
        min_views: int = 2,
        min_keypoint_confidence: float = 0.35,
        max_joint_reprojection_error_px: float = 25.0,
    ) -> None:
        self._min_views = max(2, int(min_views))
        self._min_keypoint_confidence = max(0.0, float(min_keypoint_confidence))
        self._max_joint_reprojection_error_px = max(1.0, float(max_joint_reprojection_error_px))
        self._calibration_bundle: CalibrationBundle | None = None

    def set_calibration(self, bundle: CalibrationBundle | None) -> None:
        self._calibration_bundle = bundle

    def triangulate(
        self,
        matched_keypoints: dict[str, dict[str, Pose2DKeypoint]],
        frames: dict[str, FramePacket],
        frame_index: int,
        timestamp_sec: float,
    ) -> TriangulationResult:
        camera_projections, setup_notes = self._build_camera_projection_map(frames)
        notes = list(setup_notes)

        if len(camera_projections) < self._min_views:
            notes.append(
                f"Calibrated triangulation requires >= {self._min_views} calibrated cameras with extrinsics."
            )
            return TriangulationResult(
                pose_3d=None,
                mode="unavailable",
                reconstructed_joints=0,
                notes=notes,
            )

        keypoints_3d: list[Pose3DKeypoint] = []
        reprojected_points_px: dict[str, dict[str, tuple[float, float]]] = {}
        per_joint_error_px: dict[str, float] = {}
        per_joint_view_count: dict[str, int] = {}
        per_joint_confidence: dict[str, float] = {}
        eligible_joint_count = 0
        skipped_low_view_count = 0
        rejected_observation_count = 0

        for keypoint_name, observations_map in matched_keypoints.items():
            prepared_observations = self._prepare_observations(observations_map, camera_projections)
            if len(prepared_observations) < self._min_views:
                skipped_low_view_count += 1
                continue
            eligible_joint_count += 1

            robust_joint = self._triangulate_joint_robust(prepared_observations)
            if robust_joint is None:
                notes.append(f"Skipping {keypoint_name}: robust triangulation did not find a valid inlier set.")
                continue
            rejected_observation_count += len(robust_joint.excluded_sources)

            keypoints_3d.append(
                Pose3DKeypoint(
                    name=keypoint_name,
                    x=float(robust_joint.point_3d[0]),
                    y=float(robust_joint.point_3d[1]),
                    z=float(robust_joint.point_3d[2]),
                    confidence=robust_joint.confidence,
                )
            )
            for source_id, point in robust_joint.reprojections_px.items():
                reprojected_points_px.setdefault(source_id, {})[keypoint_name] = point
            per_joint_error_px[keypoint_name] = robust_joint.mean_error_px
            per_joint_view_count[keypoint_name] = len(robust_joint.observations)
            per_joint_confidence[keypoint_name] = robust_joint.confidence

        if not keypoints_3d:
            notes.append("No valid 3D joints were reconstructed for this frame.")
            return TriangulationResult(
                pose_3d=None,
                reprojected_points_px=reprojected_points_px,
                per_joint_error_px=per_joint_error_px,
                per_joint_view_count=per_joint_view_count,
                per_joint_confidence=per_joint_confidence,
                trust_score=0.0,
                trust_state="unusable",
                mode="real_calibrated",
                reconstructed_joints=0,
                notes=notes,
            )

        trust_score, trust_state = _reconstruction_trust(
            reconstructed_count=len(keypoints_3d),
            eligible_count=eligible_joint_count,
            total_camera_count=len(camera_projections),
            per_joint_error_px=per_joint_error_px,
            per_joint_view_count=per_joint_view_count,
            per_joint_confidence=per_joint_confidence,
            max_error_px=self._max_joint_reprojection_error_px,
        )
        pose = Pose3D(frame_index=frame_index, timestamp_sec=timestamp_sec, keypoints=keypoints_3d)
        notes.append(f"Calibrated triangulation is active; trust={trust_state} ({trust_score:.0f}/100).")
        if skipped_low_view_count:
            notes.append(f"Skipped {skipped_low_view_count} joint(s) with too few calibrated observations.")
        if rejected_observation_count:
            notes.append(f"Rejected {rejected_observation_count} outlier 2D observation(s) during triangulation.")
        return TriangulationResult(
            pose_3d=pose,
            reprojected_points_px=reprojected_points_px,
            per_joint_error_px=per_joint_error_px,
            per_joint_view_count=per_joint_view_count,
            per_joint_confidence=per_joint_confidence,
            trust_score=trust_score,
            trust_state=trust_state,
            mode="real_calibrated",
            reconstructed_joints=len(keypoints_3d),
            notes=notes,
        )

    def _prepare_observations(
        self,
        observations_map: dict[str, Pose2DKeypoint],
        camera_projections: dict[str, _CameraProjection],
    ) -> list[_PreparedObservation]:
        prepared: list[_PreparedObservation] = []
        for source_id, keypoint in observations_map.items():
            if keypoint.confidence < self._min_keypoint_confidence:
                continue

            projection = camera_projections.get(source_id)
            if projection is None:
                continue

            image_point = np.array(
                [keypoint.x * projection.image_size[0], keypoint.y * projection.image_size[1]],
                dtype=np.float64,
            )
            prepared.append(_PreparedObservation(projection=projection, image_point_px=image_point, keypoint=keypoint))
        return prepared

    def _build_camera_projection_map(
        self,
        frames: dict[str, FramePacket],
    ) -> tuple[dict[str, _CameraProjection], list[str]]:
        bundle = self._calibration_bundle
        notes: list[str] = []
        projections: dict[str, _CameraProjection] = {}

        if bundle is None:
            notes.append("No calibration bundle is loaded yet.")
            return projections, notes

        for source_id, frame in frames.items():
            camera = bundle.cameras.get(source_id)
            if camera is None:
                notes.append(f"{source_id}: no calibration profile available.")
                continue

            projection = self._camera_projection_from_calibration(source_id, camera, frame)
            if projection is None:
                notes.append(f"{source_id}: calibration profile is incomplete.")
                continue

            projections[source_id] = projection

        return projections, notes

    def _camera_projection_from_calibration(
        self,
        source_id: str,
        camera: CameraCalibration,
        frame: FramePacket,
    ) -> _CameraProjection | None:
        camera_matrix = _camera_matrix(camera, frame)
        rotation_matrix = _rotation_matrix(camera.rotation)
        translation_vector = _translation_vector(camera.translation)
        if camera_matrix is None or rotation_matrix is None or translation_vector is None:
            return None

        return _CameraProjection(
            source_id=source_id,
            camera_matrix=camera_matrix,
            distortion=_distortion_array(camera),
            rotation_matrix=rotation_matrix,
            translation_vector=translation_vector,
            image_size=_frame_image_size(frame, camera.image_size),
        )

    def _triangulate_joint_robust(self, observations: list[_PreparedObservation]) -> _RobustJointResult | None:
        if len(observations) < self._min_views:
            return None

        seed_point = self._best_pair_candidate(observations)
        if seed_point is None:
            seed_point = self._triangulate_weighted_dlt(observations)
        if seed_point is None:
            return None

        seed_errors = self._reprojection_errors(seed_point, observations)
        sorted_indexes = sorted(range(len(observations)), key=lambda index: seed_errors[index])
        inlier_indexes = [
            index for index in sorted_indexes if seed_errors[index] <= self._max_joint_reprojection_error_px
        ]
        if len(inlier_indexes) < self._min_views:
            inlier_indexes = sorted_indexes[: self._min_views]

        inlier_observations = [observations[index] for index in inlier_indexes]
        point_3d = self._triangulate_weighted_dlt(inlier_observations)
        if point_3d is None:
            point_3d = self._best_pair_candidate(inlier_observations)
        if point_3d is None:
            return None

        inlier_errors = self._reprojection_errors(point_3d, inlier_observations)
        mean_error = float(np.mean(inlier_errors)) if inlier_errors else float("inf")
        if mean_error > self._max_joint_reprojection_error_px:
            return None

        reprojections = {
            observation.projection.source_id: _point_tuple(self._project_point(observation.projection, point_3d))
            for observation in inlier_observations
        }
        inlier_index_set = set(inlier_indexes)
        excluded_sources = [
            observations[index].projection.source_id
            for index in range(len(observations))
            if index not in inlier_index_set
        ]
        confidence = _joint_confidence(
            observations=inlier_observations,
            mean_error_px=mean_error,
            max_error_px=self._max_joint_reprojection_error_px,
        )
        return _RobustJointResult(
            point_3d=point_3d,
            observations=inlier_observations,
            reprojections_px=reprojections,
            mean_error_px=mean_error,
            confidence=confidence,
            excluded_sources=excluded_sources,
        )

    def _triangulate_point(self, observations: list[_PreparedObservation]) -> np.ndarray | None:
        if len(observations) < self._min_views:
            return None

        return self._best_pair_candidate(observations)

    def _best_pair_candidate(self, observations: list[_PreparedObservation]) -> np.ndarray | None:
        best_point: np.ndarray | None = None
        best_score: tuple[float, float] | None = None
        for first, second in combinations(observations, 2):
            candidate = self._triangulate_pair(first, second)
            if candidate is None:
                continue

            errors = self._reprojection_errors(candidate, observations)
            score = (float(np.median(errors)), float(np.mean(errors)))
            if best_score is None or score < best_score:
                best_score = score
                best_point = candidate

        return best_point

    def _triangulate_pair(
        self,
        first: _PreparedObservation,
        second: _PreparedObservation,
    ) -> np.ndarray | None:
        first_projection = first.projection
        second_projection = second.projection

        projection_matrix_a = first_projection.projection_matrix()
        projection_matrix_b = second_projection.projection_matrix()
        homogeneous_point = cv2.triangulatePoints(
            projection_matrix_a,
            projection_matrix_b,
            first.image_point_px.reshape(2, 1),
            second.image_point_px.reshape(2, 1),
        )
        homogeneous_point = homogeneous_point.reshape(-1)
        if abs(float(homogeneous_point[3])) <= 1e-8:
            return None

        homogeneous_point = homogeneous_point[:3] / homogeneous_point[3]
        point = homogeneous_point.reshape(3)
        if _positive_depth_count(point, [first, second]) < self._min_views:
            return None
        return point

    def _triangulate_weighted_dlt(self, observations: list[_PreparedObservation]) -> np.ndarray | None:
        if len(observations) < self._min_views:
            return None

        rows: list[np.ndarray] = []
        for observation in observations:
            projection_matrix = observation.projection.projection_matrix()
            x_px, y_px = observation.image_point_px
            weight = float(np.sqrt(max(self._min_keypoint_confidence, observation.keypoint.confidence)))
            rows.append(weight * ((x_px * projection_matrix[2, :]) - projection_matrix[0, :]))
            rows.append(weight * ((y_px * projection_matrix[2, :]) - projection_matrix[1, :]))

        design_matrix = np.asarray(rows, dtype=np.float64)
        try:
            _u, _s, vh = np.linalg.svd(design_matrix)
        except np.linalg.LinAlgError:
            return None

        homogeneous = vh[-1, :]
        if abs(float(homogeneous[3])) <= 1e-8:
            return None
        point = (homogeneous[:3] / homogeneous[3]).reshape(3)
        if _positive_depth_count(point, observations) < self._min_views:
            return None
        return point

    def _mean_reprojection_error(
        self,
        point_3d: np.ndarray,
        observations: list[_PreparedObservation],
    ) -> float:
        errors = self._reprojection_errors(point_3d, observations)
        return float(np.mean(errors)) if errors else float("inf")

    def _reprojection_errors(
        self,
        point_3d: np.ndarray,
        observations: list[_PreparedObservation],
    ) -> list[float]:
        errors: list[float] = []
        for observation in observations:
            projected_point = self._project_point(observation.projection, point_3d)
            errors.append(float(np.linalg.norm(projected_point - observation.image_point_px)))
        return errors

    def _project_point(self, projection: _CameraProjection, point_3d: np.ndarray) -> np.ndarray:
        point = np.asarray(point_3d, dtype=np.float64).reshape(1, 1, 3)
        projected, _ = cv2.projectPoints(point, projection.rvec(), projection.translation_vector, projection.camera_matrix, projection.distortion)
        return projected.reshape(2)


class PrototypeTriangulator(PoseTriangulator):
    name = "prototype_multiview_triangulator"

    def __init__(
        self,
        min_views: int = 2,
        min_keypoint_confidence: float = 0.35,
    ) -> None:
        self._min_views = max(2, int(min_views))
        self._min_keypoint_confidence = max(0.0, float(min_keypoint_confidence))
        self._calibration_bundle: CalibrationBundle | None = None

    def set_calibration(self, bundle: CalibrationBundle | None) -> None:
        self._calibration_bundle = bundle

    def triangulate(
        self,
        matched_keypoints: dict[str, dict[str, Pose2DKeypoint]],
        frames: dict[str, FramePacket],
        frame_index: int,
        timestamp_sec: float,
    ) -> TriangulationResult:
        notes: list[str] = []
        calibrated_sources = self._calibrated_source_ids()
        if len(frames) < self._min_views:
            notes.append(f"Need at least {self._min_views} active camera sources for reconstruction.")
            return TriangulationResult(pose_3d=None, mode="unavailable", notes=notes)
        if len(calibrated_sources) < self._min_views:
            notes.append("No calibrated multi-camera bundle available yet.")
            return TriangulationResult(pose_3d=None, mode="unavailable", notes=notes)

        keypoints_3d: list[Pose3DKeypoint] = []
        reprojected_points_px: dict[str, dict[str, tuple[float, float]]] = {}
        per_joint_error_px: dict[str, float] = {}

        for keypoint_name, observations_map in matched_keypoints.items():
            observations = [
                observation
                for observation in observations_map.values()
                if observation.confidence >= self._min_keypoint_confidence
            ]
            if len(observations) < self._min_views:
                continue

            xs = [observation.x for observation in observations]
            ys = [observation.y for observation in observations]
            confidences = [observation.confidence for observation in observations]
            mean_x = np.mean(xs)
            mean_y = np.mean(ys)
            spread_x = max(xs) - min(xs) if len(xs) > 1 else 0.0
            spread_y = max(ys) - min(ys) if len(ys) > 1 else 0.0
            spread = max(spread_x, spread_y)
            depth = _clamp(1.35 / (spread + 0.03), 0.25, 5.0)
            confidence = _clamp(np.mean(confidences) * min(1.0, 0.7 + (0.1 * len(observations))), 0.0, 1.0)

            keypoints_3d.append(
                Pose3DKeypoint(
                    name=keypoint_name,
                    x=(mean_x - 0.5) * 2.0,
                    y=(0.5 - mean_y) * 2.0,
                    z=depth,
                    confidence=confidence,
                )
            )
            per_joint_error_px[keypoint_name] = spread * 100.0

            for source_id, observation in observations_map.items():
                if observation.confidence < self._min_keypoint_confidence:
                    continue
                width, height = _image_size_for_source(self._calibration_bundle, source_id)
                reprojected_points_px.setdefault(source_id, {})[keypoint_name] = (
                    observation.x * width,
                    observation.y * height,
                )

        if not keypoints_3d:
            notes.append("Prototype triangulator could not reconstruct any joints.")
            return TriangulationResult(
                pose_3d=None,
                reprojected_points_px=reprojected_points_px,
                per_joint_error_px=per_joint_error_px,
                mode="placeholder_fallback",
                reconstructed_joints=0,
                notes=notes,
            )

        notes.append(
            "Prototype triangulation is demo-quality only and should be replaced with calibrated geometry later."
        )
        pose = Pose3D(frame_index=frame_index, timestamp_sec=timestamp_sec, keypoints=keypoints_3d)
        return TriangulationResult(
            pose_3d=pose,
            reprojected_points_px=reprojected_points_px,
            per_joint_error_px=per_joint_error_px,
            mode="placeholder_fallback",
            reconstructed_joints=len(keypoints_3d),
            notes=notes,
        )

    def _calibrated_source_ids(self) -> list[str]:
        bundle = self._calibration_bundle
        if bundle is None:
            return []

        source_ids: list[str] = []
        for source_id, camera in bundle.cameras.items():
            if _is_calibrated_camera(camera):
                source_ids.append(source_id)
        return source_ids


def _is_calibrated_camera(camera: CameraCalibration) -> bool:
    if camera.status.lower() in {"solved", "ready", "calibrated"}:
        return True
    return camera.intrinsics is not None and camera.translation is not None


def _camera_matrix(camera: CameraCalibration, frame: FramePacket) -> np.ndarray | None:
    if camera.intrinsics is None:
        return None

    matrix = np.asarray(camera.intrinsics, dtype=np.float64)
    if matrix.shape != (3, 3):
        return None

    frame_width, frame_height = _frame_size(frame)
    source_width, source_height = camera.image_size or (frame_width, frame_height)
    if source_width > 0 and source_height > 0 and (source_width != frame_width or source_height != frame_height):
        scale_x = frame_width / float(source_width)
        scale_y = frame_height / float(source_height)
        matrix = matrix.copy()
        matrix[0, 0] *= scale_x
        matrix[1, 1] *= scale_y
        matrix[0, 2] *= scale_x
        matrix[1, 2] *= scale_y
    return matrix


def _rotation_matrix(rotation: list[float] | None) -> np.ndarray | None:
    if rotation is None:
        return None

    values = np.asarray(rotation, dtype=np.float64)
    if values.size == 9:
        return values.reshape(3, 3)
    if values.size == 3:
        matrix, _ = cv2.Rodrigues(values.reshape(3, 1))
        return matrix
    return None


def _translation_vector(translation: list[float] | None) -> np.ndarray | None:
    if translation is None:
        return None

    values = np.asarray(translation, dtype=np.float64).reshape(-1)
    if values.size != 3:
        return None
    return values.reshape(3, 1)


def _distortion_array(camera: CameraCalibration) -> np.ndarray:
    if camera.distortion is None:
        return np.zeros((5, 1), dtype=np.float64)
    return np.asarray(camera.distortion, dtype=np.float64).reshape(-1, 1)


def _frame_size(frame: FramePacket) -> tuple[int, int]:
    frame_data = frame.frame_data
    if frame_data is None or not hasattr(frame_data, "shape"):
        return 1280, 720
    shape = frame_data.shape
    if len(shape) < 2:
        return 1280, 720
    return int(shape[1]), int(shape[0])


def _frame_image_size(frame: FramePacket, fallback: tuple[int, int] | None) -> tuple[int, int]:
    width, height = _frame_size(frame)
    if width > 0 and height > 0:
        return width, height
    if fallback is not None:
        return fallback
    return 1280, 720


def _image_size_for_source(bundle: CalibrationBundle | None, source_id: str) -> tuple[int, int]:
    default_size = (1280, 720)
    if bundle is None:
        return default_size
    camera = bundle.cameras.get(source_id)
    if camera is None or camera.image_size is None:
        return default_size
    width, height = camera.image_size
    if width <= 0 or height <= 0:
        return default_size
    return int(width), int(height)


def _positive_depth_count(point_3d: np.ndarray, observations: list[_PreparedObservation]) -> int:
    point = np.asarray(point_3d, dtype=np.float64).reshape(3)
    count = 0
    for observation in observations:
        camera_point = observation.projection.rotation_matrix @ point + observation.projection.translation_vector.reshape(3)
        if float(camera_point[2]) > 1e-6:
            count += 1
    return count


def _point_tuple(point: np.ndarray) -> tuple[float, float]:
    values = np.asarray(point, dtype=np.float64).reshape(2)
    return float(values[0]), float(values[1])


def _joint_confidence(
    observations: list[_PreparedObservation],
    mean_error_px: float,
    max_error_px: float,
) -> float:
    if not observations:
        return 0.0
    mean_observation_confidence = float(np.mean([observation.keypoint.confidence for observation in observations]))
    view_factor = min(1.0, 0.65 + (0.12 * len(observations)))
    error_factor = _clamp(1.0 - (mean_error_px / max(1e-6, max_error_px)), 0.0, 1.0)
    return _clamp(mean_observation_confidence * view_factor * (0.55 + (0.45 * error_factor)), 0.0, 1.0)


def _reconstruction_trust(
    reconstructed_count: int,
    eligible_count: int,
    total_camera_count: int,
    per_joint_error_px: dict[str, float],
    per_joint_view_count: dict[str, int],
    per_joint_confidence: dict[str, float],
    max_error_px: float,
) -> tuple[float, str]:
    if reconstructed_count <= 0 or eligible_count <= 0:
        return 0.0, "unusable"

    coverage_score = reconstructed_count / max(1, eligible_count)
    mean_confidence = float(np.mean(list(per_joint_confidence.values()))) if per_joint_confidence else 0.0
    mean_view_count = float(np.mean(list(per_joint_view_count.values()))) if per_joint_view_count else 0.0
    view_score = _clamp(mean_view_count / max(2.0, min(4.0, float(total_camera_count))), 0.0, 1.0)
    mean_error = float(np.mean(list(per_joint_error_px.values()))) if per_joint_error_px else max_error_px
    error_score = _clamp(1.0 - (mean_error / max(1e-6, max_error_px)), 0.0, 1.0)
    trust_score = 100.0 * (
        (0.40 * coverage_score)
        + (0.25 * mean_confidence)
        + (0.20 * view_score)
        + (0.15 * error_score)
    )
    return trust_score, _trust_state(trust_score)


def _trust_state(score: float) -> str:
    if score >= 85.0:
        return "excellent"
    if score >= 65.0:
        return "usable"
    if score >= 40.0:
        return "weak"
    return "unusable"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
