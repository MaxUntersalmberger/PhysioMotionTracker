from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import cv2
from PySide6.QtCore import QThread, Signal

from mocap_app.models.types import CameraSourceConfig, FramePacket


LOGGER = logging.getLogger(__name__)


class LiveCaptureWorker(QThread):
    batch_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        sources: list[CameraSourceConfig],
        target_fps: float,
        max_frame_width: int = 0,
        requested_width: int = 0,
        requested_height: int = 0,
    ) -> None:
        super().__init__()
        self._sources = sources
        self._target_fps = max(1.0, target_fps)
        self._max_frame_width = max(0, int(max_frame_width))
        self._requested_width = max(0, int(requested_width))
        self._requested_height = max(0, int(requested_height))
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        captures: dict[str, cv2.VideoCapture] = {}
        source_by_id: dict[str, CameraSourceConfig] = {source.source_id: source for source in self._sources}
        frame_indices: dict[str, int] = {source.source_id: 0 for source in self._sources}
        frame_interval = 1.0 / self._target_fps

        try:
            for source in self._sources:
                uri: Any = source.uri
                if source.kind == "webcam" and isinstance(uri, str) and uri.isdigit():
                    uri = int(uri)

                capture = self._open_capture(uri=uri, kind=source.kind)
                if not capture.isOpened():
                    raise RuntimeError(f"Could not open source '{source.source_id}' ({source.uri}).")
                self._configure_capture(capture=capture, kind=source.kind)
                captures[source.source_id] = capture

            self.state_changed.emit("live_started")
            LOGGER.info("Live capture started with %d source(s).", len(captures))

            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                timestamp_sec = time.time()
                batch: dict[str, FramePacket] = {}

                for source_id, capture in captures.items():
                    ok, frame = capture.read()
                    if not ok:
                        source = source_by_id[source_id]
                        if source.kind == "video":
                            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            continue
                        self.error.emit(f"Capture read failed for source '{source_id}'.")
                        continue

                    frame_indices[source_id] += 1
                    frame = self._maybe_resize(frame)
                    batch[source_id] = FramePacket(
                        source_id=source_id,
                        frame_index=frame_indices[source_id],
                        timestamp_sec=timestamp_sec,
                        frame_bgr=frame,
                    )

                if batch:
                    self.batch_ready.emit(batch)

                elapsed = time.perf_counter() - loop_start
                delay = frame_interval - elapsed
                if delay > 0:
                    time.sleep(delay)
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("Live capture worker failed.")
            self.error.emit(str(exc))
        finally:
            for capture in captures.values():
                capture.release()
            self.state_changed.emit("live_stopped")
            LOGGER.info("Live capture stopped.")

    def _open_capture(self, uri: Any, kind: str):
        if kind != "webcam" or not isinstance(uri, int):
            return cv2.VideoCapture(uri)

        backends: list[int | None] = []
        if os.name == "nt":
            if hasattr(cv2, "CAP_DSHOW"):
                backends.append(cv2.CAP_DSHOW)
            if hasattr(cv2, "CAP_MSMF"):
                backends.append(cv2.CAP_MSMF)
        backends.append(None)

        for backend in backends:
            capture = cv2.VideoCapture(uri, backend) if backend is not None else cv2.VideoCapture(uri)
            if capture.isOpened():
                return capture
            capture.release()
        return cv2.VideoCapture(uri)

    def _configure_capture(self, capture: cv2.VideoCapture, kind: str) -> None:
        if kind == "webcam" and hasattr(cv2, "VideoWriter_fourcc"):
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        if self._requested_width > 0:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._requested_width))
        if self._requested_height > 0:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._requested_height))
        capture.set(cv2.CAP_PROP_FPS, float(self._target_fps))
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _maybe_resize(self, frame):
        if self._max_frame_width <= 0:
            return frame
        height, width = frame.shape[:2]
        if width <= self._max_frame_width or width <= 0:
            return frame
        scale = self._max_frame_width / float(width)
        resized = cv2.resize(
            frame,
            (self._max_frame_width, max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        return resized
