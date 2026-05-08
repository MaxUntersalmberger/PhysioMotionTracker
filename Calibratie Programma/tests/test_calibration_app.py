from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from calibration_app.calibration_manager import CALIBRATION_OBJECT_CHARUCO, CalibrationOnlyManager
from calibration_app.project import CalibrationProjectRepository
from models.types import FramePacket


class CalibrationOnlyManagerTests(unittest.TestCase):
    def test_detection_preferences_reset_incompatible_samples(self) -> None:
        manager = CalibrationOnlyManager()

        def detect(source_id: str, frame: FramePacket):
            return _detection(manager, source_id, frame.frame_index)

        manager._detect_calibration_board = detect  # type: ignore[method-assign]
        manager.capture_frames({"cam0": _frame("cam0", 1)}, record_sample=True, capture_mode="intrinsics")

        manager.set_detection_preferences("charuco", "auto")

        self.assertEqual(manager.calibration_object_type, CALIBRATION_OBJECT_CHARUCO)
        self.assertEqual(manager.sample_counts(), {})


class CalibrationProjectRepositoryTests(unittest.TestCase):
    def test_project_manifest_round_trips_gui_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = CalibrationProjectRepository(Path(temp_dir))
            project = repository.create("Lab Setup", sources_csv="0,1", target_fps=30.0)
            project.calibration_profile_path = project.default_profile_path
            repository.save(project)

            loaded = repository.load(project.root_dir)

            self.assertEqual(loaded.name, "Lab Setup")
            self.assertEqual(loaded.sources_csv, "0,1")
            self.assertEqual(loaded.target_fps, 30.0)
            self.assertEqual(loaded.calibration_profile_path, loaded.default_profile_path)


def _frame(source_id: str, frame_index: int) -> FramePacket:
    return FramePacket(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=float(frame_index),
        frame_data=np.zeros((480, 640, 3), dtype=np.uint8),
    )


def _detection(manager: CalibrationOnlyManager, source_id: str, frame_index: int):
    from calibration.manager import _CalibrationDetection, _board_object_points

    object_points = _board_object_points(manager.board_shape, manager.square_size_m)
    image_points = np.array(
        [[[100.0, 100.0]], [[120.0, 100.0]], [[100.0, 120.0]], [[120.0, 120.0]]],
        dtype=np.float32,
    )
    return _CalibrationDetection(
        source_id=source_id,
        frame_index=frame_index,
        timestamp_sec=float(frame_index),
        image_size=(640, 480),
        object_points=object_points[:4],
        image_points=image_points,
        coverage_ratio=0.2,
    )


if __name__ == "__main__":
    unittest.main()
