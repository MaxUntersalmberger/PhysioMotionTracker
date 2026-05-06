from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from calibration.diagnostics import evaluate_calibration_bundle
from capture.backend import CaptureBatch
from capture.profiles import (
    CameraControlSettings,
    assess_batch_synchronization,
    build_camera_profiles,
    capture_resource_snapshot,
)
from detectors import ConfidencePolicy, apply_confidence_policy, create_detector, detector_capabilities, normalize_detector_name
from models.types import CalibrationBundle, CameraCalibration, CameraProbeResult, CameraSourceConfig, FramePacket, Pose2D, Pose2DKeypoint


class ProfessionalCameraFoundationTests(unittest.TestCase):
    def test_camera_profiles_and_sync_assessment_capture_health_inputs(self) -> None:
        sources = [
            CameraSourceConfig(source_id="cam0", kind="webcam", uri=0),
            CameraSourceConfig(source_id="cam1", kind="webcam", uri=1),
        ]
        probes = {
            "cam0": CameraProbeResult(index=0, opened=True, width=1280, height=720, backend="test", fps=30.0),
            "cam1": CameraProbeResult(index=1, opened=True, width=1280, height=720, backend="test", fps=30.0),
        }
        profiles = build_camera_profiles(sources, probes, CameraControlSettings(width=1280, height=720, fps=30.0))
        batch = CaptureBatch(
            frames={
                "cam0": _frame("cam0", 10, 100.000),
                "cam1": _frame("cam1", 10, 100.012),
            },
            capture_timestamp_sec=100.0,
            capture_ms=4.0,
        )
        sync = assess_batch_synchronization(batch)

        self.assertEqual(set(profiles), {"cam0", "cam1"})
        self.assertTrue(profiles["cam0"].opened)
        self.assertEqual(profiles["cam1"].observed_fps, 30.0)
        self.assertEqual(sync.status, "ready")
        self.assertLess(sync.timestamp_spread_ms, 40.0)

    def test_resource_snapshot_reports_disk_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = capture_resource_snapshot(Path(temp_dir))
            self.assertGreater(snapshot.disk_total_gb, 0.0)
            self.assertGreaterEqual(snapshot.disk_free_gb, 0.0)
            self.assertGreaterEqual(snapshot.disk_used_percent, 0.0)


class ProfessionalCalibrationFoundationTests(unittest.TestCase):
    def test_acceptance_report_scores_solved_calibration(self) -> None:
        bundle = CalibrationBundle(
            cameras={
                "cam0": _camera("cam0", [0.0, 0.0, 0.0]),
                "cam1": _camera("cam1", [0.2, 0.0, 0.0]),
            },
            metadata={"used_synchronized_samples": 5},
        )

        report = evaluate_calibration_bundle(bundle)

        self.assertGreaterEqual(report.score, 80.0)
        self.assertIn(report.status, {"usable", "excellent"})
        self.assertEqual(len(report.pair_diagnostics), 1)
        self.assertTrue(report.pair_diagnostics[0].ready)
        self.assertAlmostEqual(report.pair_diagnostics[0].baseline_m or 0.0, 0.2)


class ProfessionalDetectorFoundationTests(unittest.TestCase):
    def test_detector_registry_and_confidence_policy_report_occlusion(self) -> None:
        self.assertEqual(normalize_detector_name("disabled"), "none")
        self.assertEqual(create_detector("none").name, "null_pose_detector")
        capabilities = detector_capabilities("mediapipe")
        self.assertIsNotNone(capabilities)
        self.assertIn("body", capabilities.modalities)

        pose = Pose2D(
            source_id="cam0",
            frame_index=1,
            timestamp_sec=1.0,
            keypoints=[
                Pose2DKeypoint("nose", 0.5, 0.2, 0.9),
                Pose2DKeypoint("left_shoulder", 0.4, 0.4, 0.1),
            ],
        )
        filtered, report = apply_confidence_policy(pose, ConfidencePolicy(min_confidence=0.25))

        self.assertEqual(len(filtered.keypoints), 1)
        self.assertIn("left_shoulder", report.low_confidence_keypoints)
        self.assertEqual(report.occlusion_status, "occluded")


def _frame(source_id: str, frame_index: int, timestamp: float) -> FramePacket:
    return FramePacket(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=timestamp,
        frame_data=np.zeros((8, 8, 3), dtype=np.uint8),
    )


def _camera(source_id: str, translation: list[float]) -> CameraCalibration:
    return CameraCalibration(
        source_id=source_id,
        intrinsics=[
            [900.0, 0.0, 640.0],
            [0.0, 900.0, 360.0],
            [0.0, 0.0, 1.0],
        ],
        distortion=[0.0, 0.0, 0.0, 0.0, 0.0],
        rotation=np.eye(3, dtype=np.float64).reshape(-1).tolist(),
        translation=translation,
        image_size=(1280, 720),
        reprojection_error_px=0.4,
        num_samples=12,
        status="solved",
    )


if __name__ == "__main__":
    unittest.main()
