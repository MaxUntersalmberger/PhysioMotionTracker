from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from capture.backend import CaptureBatch
from models.types import CameraSourceConfig, FramePacket
from session.recorder import SessionRecorder


class FakeVideoWriter:
    def __init__(self, path: Path, fps: float, frame_size: tuple[int, int]) -> None:
        self.path = path
        self.fps = fps
        self.frame_size = frame_size
        self.frames: list[np.ndarray] = []
        self.released = False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-video")

    def write(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())

    def release(self) -> None:
        self.released = True


class FakeVideoWriterFactory:
    def __init__(self) -> None:
        self.writers: dict[str, FakeVideoWriter] = {}

    def __call__(self, path: Path, fps: float, frame_size: tuple[int, int]) -> FakeVideoWriter:
        writer = FakeVideoWriter(path, fps, frame_size)
        self.writers[path.name] = writer
        return writer


class SessionRecorderTests(unittest.TestCase):
    def test_records_batches_to_per_camera_videos_and_frame_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir) / "session_001"
            writer_factory = FakeVideoWriterFactory()
            recorder = SessionRecorder(
                session_dir=session_dir,
                sources=[
                    CameraSourceConfig(source_id="cam0", kind="webcam", uri=0),
                    CameraSourceConfig(source_id="cam1", kind="webcam", uri=1),
                ],
                fps=30.0,
                writer_factory=writer_factory,
            )

            recorder.start()
            stats = recorder.write_batch(_batch(frame_index=1))
            stats = recorder.write_batch(_batch(frame_index=2, dropped_sources=["cam1"]))
            stats = recorder.stop()

            self.assertEqual(stats.batches_written, 2)
            self.assertEqual(stats.total_frames, 2)
            self.assertEqual(stats.frames_written_by_source, {"cam0": 2, "cam1": 2})
            self.assertEqual(stats.dropped_sources, {"cam1": 1})
            self.assertEqual(stats.video_files, {"cam0": "video/cam0.avi", "cam1": "video/cam1.avi"})
            self.assertTrue((session_dir / "video" / "cam0.avi").exists())
            self.assertTrue((session_dir / "video" / "cam1.avi").exists())
            self.assertTrue(writer_factory.writers["cam0.avi"].released)
            self.assertTrue(writer_factory.writers["cam1.avi"].released)

            frame_log_lines = (session_dir / "frames.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(frame_log_lines), 2)
            first_log = json.loads(frame_log_lines[0])
            second_log = json.loads(frame_log_lines[1])
            self.assertEqual(first_log["frame_indices"], {"cam0": 1, "cam1": 1})
            self.assertEqual(second_log["dropped_sources"], ["cam1"])


def _batch(frame_index: int, dropped_sources: list[str] | None = None) -> CaptureBatch:
    timestamp = 1000.0 + frame_index
    return CaptureBatch(
        frames={
            "cam0": _frame("cam0", frame_index, timestamp),
            "cam1": _frame("cam1", frame_index, timestamp),
        },
        capture_timestamp_sec=timestamp,
        capture_ms=3.5,
        dropped_sources=list(dropped_sources or []),
    )


def _frame(source_id: str, frame_index: int, timestamp: float) -> FramePacket:
    image = np.full((8, 10, 3), fill_value=frame_index, dtype=np.uint8)
    return FramePacket(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=timestamp,
        frame_data=image,
    )


if __name__ == "__main__":
    unittest.main()
