from __future__ import annotations

import unittest

import numpy as np

from calibration.manager import CalibrationManager, _CalibrationDetection, _CalibrationSyncSample
from models.types import CalibrationBundle, CameraCalibration


class CalibrationManagerExtrinsicsTests(unittest.TestCase):
    def test_extrinsics_can_be_solved_from_intrinsics_only_bundle(self) -> None:
        manager = CalibrationManager(min_synchronized_samples=2)
        manager.set_bundle(
            CalibrationBundle(
                cameras={
                    "cam0": _intrinsics_only_camera("cam0"),
                    "cam1": _intrinsics_only_camera("cam1"),
                }
            )
        )
        manager._sync_samples = [  # type: ignore[attr-defined]
            _sync_sample(frame_index=1),
            _sync_sample(frame_index=2),
        ]

        def solve_board_transform(_camera: CameraCalibration, detection: _CalibrationDetection) -> np.ndarray:
            transform = np.eye(4, dtype=np.float64)
            if detection.source_id == "cam1":
                transform[:3, 3] = [1.0, 0.0, 0.0]
            return transform

        manager._solve_board_transform = solve_board_transform  # type: ignore[method-assign]

        result = manager.solve_extrinsics()

        self.assertEqual(set(result.solved_sources), {"cam0", "cam1"})
        self.assertEqual(result.failed_sources, [])
        self.assertEqual(result.bundle.cameras["cam0"].translation, [0.0, 0.0, 0.0])
        self.assertEqual(result.bundle.cameras["cam0"].status, "solved")
        self.assertEqual(result.bundle.cameras["cam1"].status, "solved")
        self.assertIsNotNone(result.bundle.cameras["cam1"].rotation)
        self.assertIsNotNone(result.bundle.cameras["cam1"].translation)
        self.assertAlmostEqual(result.bundle.cameras["cam1"].translation[0], 1.0)
        self.assertEqual(result.bundle.metadata["used_synchronized_samples"], 2)


def _intrinsics_only_camera(source_id: str) -> CameraCalibration:
    return CameraCalibration(
        source_id=source_id,
        status="intrinsics_solved",
        intrinsics=[
            [800.0, 0.0, 320.0],
            [0.0, 800.0, 240.0],
            [0.0, 0.0, 1.0],
        ],
        distortion=[0.0, 0.0, 0.0, 0.0, 0.0],
        rotation=None,
        translation=None,
        image_size=(640, 480),
        num_samples=6,
    )


def _sync_sample(frame_index: int) -> _CalibrationSyncSample:
    return _CalibrationSyncSample(
        frame_index=frame_index,
        timestamp_sec=float(frame_index),
        detections={
            "cam0": _detection("cam0", frame_index),
            "cam1": _detection("cam1", frame_index),
        },
    )


def _detection(source_id: str, frame_index: int) -> _CalibrationDetection:
    object_points = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    image_points = np.array(
        [
            [[100.0, 100.0]],
            [[120.0, 100.0]],
            [[100.0, 120.0]],
            [[120.0, 120.0]],
        ],
        dtype=np.float32,
    )
    return _CalibrationDetection(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=float(frame_index),
        image_size=(640, 480),
        object_points=object_points,
        image_points=image_points,
        coverage_ratio=0.2,
    )


if __name__ == "__main__":
    unittest.main()
