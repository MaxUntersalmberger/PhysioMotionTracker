from __future__ import annotations

import unittest

import cv2
import numpy as np

from models.types import CalibrationBundle, CameraCalibration, FramePacket, Pose2DKeypoint
from reconstruction import CalibratedTriangulator


class RobustReconstructionTests(unittest.TestCase):
    def test_calibrated_triangulation_rejects_outlier_view_and_reports_trust(self) -> None:
        image_size = (640, 480)
        cameras = {
            "cam0": _camera("cam0", [0.0, 0.0, 0.0], image_size),
            "cam1": _camera("cam1", [-0.25, 0.0, 0.0], image_size),
            "cam2": _camera("cam2", [0.25, 0.0, 0.0], image_size),
        }
        world_point = np.array([0.02, -0.01, 2.0], dtype=np.float64)
        projected = {
            source_id: _project(camera, world_point)
            for source_id, camera in cameras.items()
        }
        projected["cam2"] = projected["cam2"] + np.array([140.0, 70.0], dtype=np.float64)

        triangulator = CalibratedTriangulator(max_joint_reprojection_error_px=8.0)
        triangulator.set_calibration(CalibrationBundle(cameras=cameras))
        frames = {source_id: _frame(source_id, image_size) for source_id in cameras}
        matched = {
            "left_knee": {
                source_id: _keypoint("left_knee", image_point, image_size)
                for source_id, image_point in projected.items()
            },
            "right_knee": {
                "cam0": _keypoint("right_knee", projected["cam0"], image_size),
            },
        }

        result = triangulator.triangulate(matched, frames, frame_index=1, timestamp_sec=1.0)

        self.assertIsNotNone(result.pose_3d)
        pose = result.pose_3d
        assert pose is not None
        keypoints = pose.keypoints_by_name()
        self.assertIn("left_knee", keypoints)
        self.assertNotIn("right_knee", keypoints)
        self.assertEqual(result.per_joint_view_count["left_knee"], 2)
        self.assertLess(result.per_joint_error_px["left_knee"], 1.0)
        self.assertGreater(result.trust_score, 50.0)
        self.assertIn(result.trust_state, {"weak", "usable", "excellent"})
        self.assertTrue(any("Rejected 1 outlier" in note for note in result.notes))
        self.assertTrue(any("too few calibrated observations" in note for note in result.notes))
        self.assertAlmostEqual(keypoints["left_knee"].x, world_point[0], places=3)
        self.assertAlmostEqual(keypoints["left_knee"].y, world_point[1], places=3)
        self.assertAlmostEqual(keypoints["left_knee"].z, world_point[2], places=3)


def _camera(source_id: str, translation: list[float], image_size: tuple[int, int]) -> CameraCalibration:
    return CameraCalibration(
        source_id=source_id,
        intrinsics=[
            [800.0, 0.0, image_size[0] / 2.0],
            [0.0, 800.0, image_size[1] / 2.0],
            [0.0, 0.0, 1.0],
        ],
        distortion=[0.0, 0.0, 0.0, 0.0, 0.0],
        rotation=np.eye(3, dtype=np.float64).reshape(-1).tolist(),
        translation=translation,
        image_size=image_size,
        status="solved",
        num_samples=8,
    )


def _project(camera: CameraCalibration, point: np.ndarray) -> np.ndarray:
    assert camera.intrinsics is not None
    assert camera.rotation is not None
    assert camera.translation is not None
    projected, _ = cv2.projectPoints(
        point.reshape(1, 1, 3),
        np.zeros((3, 1), dtype=np.float64),
        np.asarray(camera.translation, dtype=np.float64).reshape(3, 1),
        np.asarray(camera.intrinsics, dtype=np.float64),
        np.zeros((5, 1), dtype=np.float64),
    )
    return projected.reshape(2)


def _keypoint(name: str, image_point: np.ndarray, image_size: tuple[int, int]) -> Pose2DKeypoint:
    return Pose2DKeypoint(
        name=name,
        x=float(image_point[0] / image_size[0]),
        y=float(image_point[1] / image_size[1]),
        confidence=0.9,
    )


def _frame(source_id: str, image_size: tuple[int, int]) -> FramePacket:
    width, height = image_size
    return FramePacket(
        source_id=source_id,
        frame_index=1,
        timestamp_sec=1.0,
        frame_data=np.zeros((height, width, 3), dtype=np.uint8),
    )


if __name__ == "__main__":
    unittest.main()
