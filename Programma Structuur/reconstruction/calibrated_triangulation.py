from __future__ import annotations

from dataclasses import dataclass
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

        for keypoint_name, observations_map in matched_keypoints.items():
            prepared_observations: list[tuple[_CameraProjection, np.ndarray, Pose2DKeypoint]] = []
            for source_id, keypoint in observations_map.items():
                if keypoint.confidence < self._min_keypoint_confidence:
                    continue

                projection = camera_projections.get(source_id)
                if projection is None:
                    continue

                image_point = np.array(
                    [[keypoint.x * projection.image_size[0], keypoint.y * projection.image_size[1]]],
                    dtype=np.float64,
                ).reshape(1, 1, 2)
                prepared_observations.append((projection, image_point.reshape(2), keypoint))

            if len(prepared_observations) < self._min_views:
                continue

            point_3d = self._triangulate_point(prepared_observations)
            if point_3d is None:
                continue

            confidence = _clamp(
                float(np.mean([item[2].confidence for item in prepared_observations]))
                * min(1.0, 0.75 + (0.08 * len(prepared_observations))),
                0.0,
                1.0,
            )

            reprojection_errors: list[float] = []
            reprojections_for_joint: dict[str, tuple[float, float]] = {}
            for projection, _normalized_point, keypoint in prepared_observations:
                projected_point = self._project_point(projection, point_3d)
                reprojections_for_joint[projection.source_id] = (float(projected_point[0]), float(projected_point[1]))
                observed_point = np.array(
                    [keypoint.x * projection.image_size[0], keypoint.y * projection.image_size[1]],
                    dtype=np.float64,
                )
                reprojection_errors.append(float(np.linalg.norm(projected_point - observed_point)))

            mean_error = float(np.mean(reprojection_errors)) if reprojection_errors else None
            if mean_error is not None and mean_error > self._max_joint_reprojection_error_px:
                notes.append(
                    f"Skipping {keypoint_name}: reprojection error {mean_error:.2f}px exceeds "
                    f"{self._max_joint_reprojection_error_px:.2f}px."
                )
                continue

            keypoints_3d.append(
                Pose3DKeypoint(
                    name=keypoint_name,
                    x=float(point_3d[0]),
                    y=float(point_3d[1]),
                    z=float(point_3d[2]),
                    confidence=confidence,
                )
            )
            for source_id, point in reprojections_for_joint.items():
                reprojected_points_px.setdefault(source_id, {})[keypoint_name] = point
            if mean_error is not None:
                per_joint_error_px[keypoint_name] = mean_error

        if not keypoints_3d:
            notes.append("No valid 3D joints were reconstructed for this frame.")
            return TriangulationResult(
                pose_3d=None,
                reprojected_points_px=reprojected_points_px,
                per_joint_error_px=per_joint_error_px,
                mode="real_calibrated",
                reconstructed_joints=0,
                notes=notes,
            )

        pose = Pose3D(frame_index=frame_index, timestamp_sec=timestamp_sec, keypoints=keypoints_3d)
        notes.append("Calibrated triangulation is active.")
        return TriangulationResult(
            pose_3d=pose,
            reprojected_points_px=reprojected_points_px,
            per_joint_error_px=per_joint_error_px,
            mode="real_calibrated",
            reconstructed_joints=len(keypoints_3d),
            notes=notes,
        )

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

    def _triangulate_point(self, observations: list[tuple[_CameraProjection, np.ndarray, Pose2DKeypoint]]) -> np.ndarray | None:
        if len(observations) < self._min_views:
            return None

        best_point: np.ndarray | None = None
        best_error: float | None = None

        for first, second in combinations(observations, 2):
            candidate = self._triangulate_pair(first, second)
            if candidate is None:
                continue

            mean_error = self._mean_reprojection_error(candidate, observations)
            if best_error is None or mean_error < best_error:
                best_error = mean_error
                best_point = candidate

        return best_point

    def _triangulate_pair(
        self,
        first: tuple[_CameraProjection, np.ndarray, Pose2DKeypoint],
        second: tuple[_CameraProjection, np.ndarray, Pose2DKeypoint],
    ) -> np.ndarray | None:
        first_projection, first_point_px, _first_keypoint = first
        second_projection, second_point_px, _second_keypoint = second

        projection_matrix_a = first_projection.projection_matrix()
        projection_matrix_b = second_projection.projection_matrix()
        homogeneous_point = cv2.triangulatePoints(
            projection_matrix_a,
            projection_matrix_b,
            first_point_px.reshape(2, 1),
            second_point_px.reshape(2, 1),
        )
        homogeneous_point = homogeneous_point.reshape(-1)
        if abs(float(homogeneous_point[3])) <= 1e-8:
            return None

        homogeneous_point = homogeneous_point[:3] / homogeneous_point[3]
        return homogeneous_point.reshape(3)

    def _mean_reprojection_error(
        self,
        point_3d: np.ndarray,
        observations: list[tuple[_CameraProjection, np.ndarray, Pose2DKeypoint]],
    ) -> float:
        errors: list[float] = []
        for projection, image_point_px, _keypoint in observations:
            projected_point = self._project_point(projection, point_3d)
            errors.append(float(np.linalg.norm(projected_point - image_point_px)))
        return float(np.mean(errors)) if errors else float("inf")

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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))