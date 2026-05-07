from __future__ import annotations

import unittest

import numpy as np

from calibration.manager import CalibrationManager, _CalibrationDetection, _CalibrationSyncSample
from models.types import CalibrationBundle, CameraCalibration, FramePacket


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
        self.assertIn(result.bundle.metadata["bundle_adjustment_status"], {"refined", "skipped"})
        self.assertEqual(result.bundle.metadata["bundle_adjustment_method"], "opencv_stereoCalibrate_fixed_intrinsics")


class CalibrationManagerCaptureModeTests(unittest.TestCase):
    def test_intrinsics_and_extrinsics_capture_modes_store_separate_sample_sets(self) -> None:
        manager = CalibrationManager()

        def detect(source_id: str, frame: FramePacket) -> _CalibrationDetection:
            return _detection(source_id, frame.frame_index)

        manager._detect_calibration_board = detect  # type: ignore[method-assign]
        frames = {
            "cam0": _frame("cam0", 1),
            "cam1": _frame("cam1", 1),
        }

        intrinsics_result = manager.capture_frames(frames, record_sample=True, capture_mode="intrinsics")
        extrinsics_result = manager.capture_frames(frames, record_sample=True, capture_mode="sync_extrinsics")

        self.assertEqual(intrinsics_result.capture_mode, "intrinsics")
        self.assertEqual(extrinsics_result.capture_mode, "sync_extrinsics")
        self.assertEqual(intrinsics_result.sample_counts, {"cam0": 1, "cam1": 1})
        self.assertEqual(extrinsics_result.sample_counts, {"cam0": 1, "cam1": 1})
        self.assertEqual(intrinsics_result.synchronized_samples, 0)
        self.assertEqual(extrinsics_result.synchronized_samples, 1)
        self.assertEqual([entry.capture_mode for entry in manager.sample_history], ["intrinsics", "sync_extrinsics"])

    def test_workflow_readiness_reports_missing_intrinsics_and_sync_sets(self) -> None:
        manager = CalibrationManager(min_samples_per_camera=2, min_synchronized_samples=2)

        def detect(source_id: str, frame: FramePacket) -> _CalibrationDetection:
            return _detection(source_id, frame.frame_index)

        manager._detect_calibration_board = detect  # type: ignore[method-assign]
        frames = {
            "cam0": _frame("cam0", 1),
            "cam1": _frame("cam1", 1),
        }

        initial = manager.workflow_readiness()
        manager.capture_frames(frames, record_sample=True, capture_mode="intrinsics")
        partial = manager.workflow_readiness()
        manager.capture_frames(frames, record_sample=True, capture_mode="intrinsics")
        ready = manager.workflow_readiness()

        self.assertFalse(initial.can_solve_intrinsics)
        self.assertFalse(partial.can_solve_intrinsics)
        self.assertTrue(ready.can_solve_intrinsics)
        self.assertEqual(set(ready.intrinsics_ready_sources), {"cam0", "cam1"})
        self.assertFalse(ready.can_solve_extrinsics)
        self.assertTrue(any("Solve intrinsics" in note for note in ready.notes))


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


def _frame(source_id: str, frame_index: int) -> FramePacket:
    return FramePacket(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=float(frame_index),
        frame_data=np.zeros((480, 640, 3), dtype=np.uint8),
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
