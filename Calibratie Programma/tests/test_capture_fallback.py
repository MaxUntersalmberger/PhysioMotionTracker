from __future__ import annotations

import unittest

from calibration_app.legacy_bridge import ensure_legacy_path

ensure_legacy_path()

import capture.backend as capture_backend  # noqa: E402
from models.types import CameraSourceConfig  # noqa: E402


class CaptureFallbackTests(unittest.TestCase):
    def test_webcam_falls_back_to_raw_open_when_requested_resolution_has_no_frames(self) -> None:
        original_cv2 = capture_backend.cv2
        capture_backend.cv2 = _FakeCv2()
        try:
            session = capture_backend.OpenCVCaptureSession(
                [CameraSourceConfig(source_id="cam0", kind="webcam", uri=0)],
                requested_width=1920,
                requested_height=1080,
                requested_fps=30.0,
            )

            probes = session.open()
            batch = session.read_batch()

            self.assertTrue(probes["cam0"].opened)
            self.assertEqual((probes["cam0"].width, probes["cam0"].height), (640, 480))
            self.assertTrue(probes["cam0"].backend.endswith("auto-fallback"))
            self.assertEqual(tuple(batch.frames["cam0"].frame_data.shape), (480, 640, 3))
        finally:
            session.close()
            capture_backend.cv2 = original_cv2

    def test_capture_continues_when_one_selected_webcam_is_unavailable(self) -> None:
        original_cv2 = capture_backend.cv2
        capture_backend.cv2 = _FakeCv2(failed_uris={1})
        try:
            session = capture_backend.OpenCVCaptureSession(
                [
                    CameraSourceConfig(source_id="cam0", kind="webcam", uri=0),
                    CameraSourceConfig(source_id="cam1", kind="webcam", uri=1),
                ],
                requested_fps=30.0,
            )

            probes = session.open()
            batch = session.read_batch()

            self.assertTrue(probes["cam0"].opened)
            self.assertFalse(probes["cam1"].opened)
            self.assertIn("cam0", batch.frames)
            self.assertEqual(batch.dropped_sources, ["cam1"])
        finally:
            session.close()
            capture_backend.cv2 = original_cv2

    def test_capture_fails_when_no_selected_webcam_opens(self) -> None:
        original_cv2 = capture_backend.cv2
        capture_backend.cv2 = _FakeCv2(failed_uris={0, 1})
        try:
            session = capture_backend.OpenCVCaptureSession(
                [
                    CameraSourceConfig(source_id="cam0", kind="webcam", uri=0),
                    CameraSourceConfig(source_id="cam1", kind="webcam", uri=1),
                ],
                requested_fps=30.0,
            )

            with self.assertRaisesRegex(RuntimeError, "Could not open any capture source"):
                session.open()
        finally:
            session.close()
            capture_backend.cv2 = original_cv2


class _FakeFrame:
    shape = (480, 640, 3)


class _FakeCapture:
    def __init__(self, opened: bool = True) -> None:
        self._opened = opened
        self._released = False
        self._requested_size = False

    def isOpened(self) -> bool:
        return self._opened and not self._released

    def set(self, property_id: int, value: float) -> bool:
        if property_id in {_FakeCv2.CAP_PROP_FRAME_WIDTH, _FakeCv2.CAP_PROP_FRAME_HEIGHT} and value > 0:
            self._requested_size = True
        return True

    def get(self, property_id: int) -> float:
        values = {
            _FakeCv2.CAP_PROP_FRAME_WIDTH: 640.0,
            _FakeCv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            _FakeCv2.CAP_PROP_FPS: 30.0,
        }
        return values.get(property_id, 0.0)

    def read(self):
        if self._requested_size:
            return False, None
        return True, _FakeFrame()

    def release(self) -> None:
        self._released = True


class _FakeCv2:
    CAP_DSHOW = 700
    CAP_MSMF = 1400
    CAP_PROP_BUFFERSIZE = 38
    CAP_PROP_FOURCC = 6
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    INTER_AREA = 3

    def __init__(self, failed_uris: set[int] | None = None) -> None:
        self._failed_uris = set(failed_uris or set())

    def VideoCapture(self, uri, _backend=None) -> _FakeCapture:
        return _FakeCapture(opened=uri not in self._failed_uris)

    def VideoWriter_fourcc(self, *_codec: str) -> int:
        return 1234


if __name__ == "__main__":
    unittest.main()
