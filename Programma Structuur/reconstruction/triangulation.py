from __future__ import annotations

from datetime import datetime
from statistics import mean

from models.types import CalibrationBundle, CameraCalibration, FramePacket, Pose2DKeypoint, Pose3D, Pose3DKeypoint

from pipeline.contracts import PoseTriangulator, TriangulationResult


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
            mean_x = mean(xs)
            mean_y = mean(ys)
            spread_x = max(xs) - min(xs) if len(xs) > 1 else 0.0
            spread_y = max(ys) - min(ys) if len(ys) > 1 else 0.0
            spread = max(spread_x, spread_y)
            depth = _clamp(1.35 / (spread + 0.03), 0.25, 5.0)
            confidence = _clamp(mean(confidences) * min(1.0, 0.7 + (0.1 * len(observations))), 0.0, 1.0)

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
