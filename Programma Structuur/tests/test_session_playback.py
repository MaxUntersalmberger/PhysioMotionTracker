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
from session.playback import SessionPlaybackReader, summarize_session_playback
from session.repository import SessionRepository
from session.reprocess import process_recorded_batch, reprocess_session
from detectors import create_detector


@unittest.skipIf(cv2 is None, "OpenCV is required for playback tests.")
class SessionPlaybackTests(unittest.TestCase):
    def test_reads_recorded_session_batches_and_reprocesses_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "session_playback"
            _write_recorded_session(session_dir)

            reader = SessionPlaybackReader(session_dir)
            info = reader.info()
            batches = list(reader.iter_batches(max_batches=2))
            third_batch = reader.read_batch_at(2)
            summary = summarize_session_playback(session_dir, max_batches=1)
            report = reprocess_session(session_dir, detector_name="synthetic", max_batches=2)
            review_result = process_recorded_batch(third_batch, create_detector("synthetic"))

            self.assertTrue(info.is_playable)
            self.assertEqual(info.frame_log_entries, 3)
            self.assertEqual(set(info.available_video_files), {"cam0", "cam1"})
            self.assertEqual(len(batches), 2)
            self.assertEqual(set(batches[0].frames), {"cam0", "cam1"})
            self.assertEqual(batches[0].frames["cam0"].frame_index, 1)
            self.assertEqual(batches[1].frames["cam1"].frame_index, 2)
            self.assertEqual(third_batch.frames["cam0"].frame_index, 3)
            self.assertEqual(third_batch.frames["cam1"].frame_index, 3)
            self.assertEqual(batches[0].frames["cam0"].frame_data.shape[:2], (12, 16))
            self.assertIn("Batch 1", summary)

            self.assertEqual(report.batches_processed, 2)
            self.assertEqual(report.frames_processed, 4)
            self.assertEqual(report.detector_name, "synthetic_pose_detector")
            self.assertFalse(report.calibration_loaded)
            self.assertGreaterEqual(report.reconstruction_modes["unavailable"], 1)
            self.assertEqual(review_result.frame_index, 3)
            self.assertEqual(review_result.debug.detector_name, "synthetic_pose_detector")
            self.assertEqual(set(review_result.frames), {"cam0", "cam1"})


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
        session_id="session_playback",
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
