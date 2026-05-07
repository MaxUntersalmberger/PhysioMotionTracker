from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from biomechanics import JointAngleRepository, analyze_motion_take_joint_angles
from models.types import Pose3D, Pose3DKeypoint
from motion import MOTION_TAKE_SCHEMA_VERSION, MotionTake, MotionTakeFrame, MotionTakeSummary


class JointAngleAnalysisTests(unittest.TestCase):
    def test_analyzes_motion_take_joint_angles_from_3d_pose(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "joint_angles.json"
            take = _motion_take_with_pose3d()

            report = analyze_motion_take_joint_angles(take, output_path=output_path)
            loaded = JointAngleRepository().load(output_path)

            self.assertEqual(report.frames_with_pose3d, 1)
            self.assertTrue(output_path.exists())
            self.assertIn("left_knee_flexion", report.analysis.summaries)
            self.assertIn("right_knee_flexion", report.analysis.summaries)
            self.assertAlmostEqual(report.analysis.summaries["left_knee_flexion"].mean_deg, 90.0)
            self.assertAlmostEqual(report.analysis.summaries["right_knee_flexion"].mean_deg, 180.0)
            self.assertEqual(loaded.summaries["left_knee_flexion"].sample_count, 1)


def _motion_take_with_pose3d() -> MotionTake:
    pose = Pose3D(
        frame_index=1,
        timestamp_sec=1.0,
        keypoints=[
            Pose3DKeypoint("left_hip", 0.0, 1.0, 0.0, 0.9),
            Pose3DKeypoint("left_knee", 0.0, 0.0, 0.0, 0.9),
            Pose3DKeypoint("left_ankle", 1.0, 0.0, 0.0, 0.9),
            Pose3DKeypoint("right_hip", 2.0, 1.0, 0.0, 0.8),
            Pose3DKeypoint("right_knee", 2.0, 0.0, 0.0, 0.8),
            Pose3DKeypoint("right_ankle", 2.0, -1.0, 0.0, 0.8),
        ],
    )
    frame = MotionTakeFrame(
        batch_index=1,
        frame_index=1,
        timestamp_sec=1.0,
        poses_2d={},
        pose_3d=pose,
        reconstruction_mode="real_calibrated",
    )
    return MotionTake(
        schema_version=MOTION_TAKE_SCHEMA_VERSION,
        take_id="take_001",
        session_id="session_001",
        created_at_iso="2026-05-07T12:00:00+02:00",
        source_session_dir="sessions/session_001",
        detector_name="synthetic_pose_detector",
        calibration_loaded=True,
        calibration_file="calibration/current_calibration.json",
        stages={"inverse_kinematics": "pending", "joint_angles": "pending"},
        summary=MotionTakeSummary(frame_count=1, source_count=2, pose3d_frames=1),
        frames=[frame],
    )


if __name__ == "__main__":
    unittest.main()
