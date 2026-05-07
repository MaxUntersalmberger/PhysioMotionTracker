from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - optional dependency guard
    cv2 = None  # type: ignore[assignment]

from exporters import export_session_poses
from models.types import CameraSourceConfig
from session.repository import SessionRepository


@unittest.skipIf(cv2 is None, "OpenCV is required for export tests.")
class PoseExportTests(unittest.TestCase):
    def test_exports_recorded_session_to_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "session_export"
            output_dir = session_dir / "exports"
            _write_recorded_session(session_dir)

            report = export_session_poses(
                session_dir,
                detector_name="synthetic",
                output_dir=output_dir,
                formats=("json", "csv"),
                max_batches=2,
            )

            self.assertEqual(report.session_id, "session_export")
            self.assertEqual(report.batches_processed, 2)
            self.assertEqual(report.frames_processed, 4)
            self.assertEqual(report.detector_name, "synthetic_pose_detector")
            self.assertFalse(report.calibration_loaded)
            self.assertGreater(report.pose2d_rows, 0)
            self.assertEqual(report.pose3d_rows, 0)
            self.assertEqual(report.reconstruction_modes["unavailable"], 2)

            json_payload = json.loads((output_dir / "pose_export.json").read_text(encoding="utf-8"))
            manifest_payload = json.loads((output_dir / "export_manifest.json").read_text(encoding="utf-8"))
            pose2d_rows = _read_csv(output_dir / "pose_2d.csv")
            pose3d_rows = _read_csv(output_dir / "pose_3d.csv")

            self.assertEqual(json_payload["schema_version"], 1)
            self.assertEqual(len(json_payload["batches"]), 2)
            self.assertIn("cam0", json_payload["batches"][0]["poses_2d"])
            self.assertEqual(manifest_payload["pose2d_rows"], report.pose2d_rows)
            self.assertEqual(len(pose2d_rows), report.pose2d_rows)
            self.assertEqual(len(pose3d_rows), 0)
            self.assertEqual(pose2d_rows[0]["session_id"], "session_export")


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
        session_id="session_export",
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


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
