from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from models.types import CameraSourceConfig
from motion import MotionTakeRepository, process_session_to_motion_take
from session.repository import SessionRepository


@unittest.skipIf(cv2 is None, "OpenCV is required for motion-take tests.")
class MotionTakeTests(unittest.TestCase):
    def test_processes_recorded_session_to_internal_motion_take(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "session_motion_take"
            _write_recorded_session(session_dir)

            report = process_session_to_motion_take(session_dir, detector_name="synthetic", max_batches=2)
            payload = json.loads(report.output_path.read_text(encoding="utf-8"))
            loaded_take = MotionTakeRepository().load(report.output_path)

            self.assertEqual(report.take.session_id, "session_motion_take")
            self.assertEqual(report.take.summary.frame_count, 2)
            self.assertEqual(report.take.summary.pose2d_frames, 2)
            self.assertGreater(report.take.summary.pose2d_keypoints, 0)
            self.assertEqual(report.take.summary.pose3d_frames, 0)
            self.assertEqual(report.take.stages["pose_2d"], "synthetic_pose_detector")
            self.assertEqual(report.take.stages["inverse_kinematics"], "pending")
            self.assertEqual(report.output_path.name, "motion_take.json")
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(len(payload["frames"]), 2)
            self.assertEqual(loaded_take.summary.frame_count, 2)


def _write_recorded_session(session_dir: Path) -> None:
    assert cv2 is not None
    video_dir = session_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    _write_video(video_dir / "cam0.avi", seed=20)
    _write_video(video_dir / "cam1.avi", seed=80)

    frame_log = []
    for index in range(1, 4):
        frame_log.append(
            {
                "batch_index": index,
                "capture_timestamp_sec": 1000.0 + index,
                "capture_ms": 2.5,
                "frame_indices": {"cam0": index, "cam1": index},
                "frame_timestamps_sec": {"cam0": 1000.0 + index, "cam1": 1000.0 + index},
                "dropped_sources": [],
            }
        )
    (session_dir / "frames.jsonl").write_text(
        "\n".join(json.dumps(entry, ensure_ascii=True, sort_keys=True) for entry in frame_log) + "\n",
        encoding="utf-8",
    )

    repository = SessionRepository()
    manifest = repository.build_manifest(
        session_id="session_motion_take",
        fps=30.0,
        sources=[
            CameraSourceConfig(source_id="cam0", kind="video", uri="video/cam0.avi"),
            CameraSourceConfig(source_id="cam1", kind="video", uri="video/cam1.avi"),
        ],
        total_frames=3,
        video_files={"cam0": "video/cam0.avi", "cam1": "video/cam1.avi"},
        metadata={"recording": {"frame_log_file": "frames.jsonl"}},
    )
    repository.save(manifest, session_dir)


def _write_video(path: Path, seed: int) -> None:
    assert cv2 is not None
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, (16, 12))
    if not writer.isOpened():
        raise RuntimeError(f"Could not create test video at {path}.")
    try:
        for index in range(3):
            frame = np.full((12, 16, 3), fill_value=seed + index, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


if __name__ == "__main__":
    unittest.main()
