from __future__ import annotations

import base64
import json
import logging
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from mocap_app.models.types import CameraSourceConfig, FramePacket


LOGGER = logging.getLogger(__name__)


class LiveCaptureWorker(QThread):
    """Live capture worker using SkellyCam-style synchronized multi-camera frame events."""

    batch_ready = Signal(object)
    state_changed = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        sources: list[CameraSourceConfig],
        target_fps: float,
        max_frame_width: int = 0,
        max_frame_height: int = 0,
        requested_width: int = 0,
        requested_height: int = 0,
        exposure: int = -1,
        fourcc: str = "MJPG",
        camera_controls: dict[str, float] | None = None,
    ) -> None:
        super().__init__()
        self._sources = sources
        self._target_fps = max(1.0, float(target_fps))
        self._requested_width = max(0, int(requested_width)) or max(0, int(max_frame_width)) or 1280
        self._requested_height = max(0, int(requested_height)) or max(0, int(max_frame_height)) or 720
        self._exposure = int(exposure)
        self._fourcc = str(fourcc or "MJPG").upper()
        self._camera_controls = dict(camera_controls or {})
        self._stop_event = threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._stderr_lines: queue.Queue[str] = queue.Queue(maxsize=80)
        self._camera_id_to_source_id = {str(source.uri): source.source_id for source in self._sources}

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write("STOP\n")
                process.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
        threading.Thread(target=self._terminate_process_after_grace, args=(1.5,), daemon=True).start()

    def run(self) -> None:
        stderr_thread: threading.Thread | None = None
        try:
            self.state_changed.emit("skellycam_starting")
            command = self._bridge_command()
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
            stderr_thread.start()
            if self._process.stdout is None:
                raise RuntimeError("Could not read from SkellyCam native bridge.")

            for line in self._process.stdout:
                if self._stop_event.is_set():
                    break
                self._handle_bridge_line(line)

            return_code = self._process.wait(timeout=5)
            if not self._stop_event.is_set() and return_code not in (0, None):
                detail = self._stderr_detail()
                raise RuntimeError(f"Camera bridge stopped with exit code {return_code}.{detail}")
        except Exception as exc:  # pragma: no cover - UI surface area
            LOGGER.exception("SkellyCam native capture worker failed.")
            self.error.emit(str(exc))
        finally:
            self._stop_event.set()
            self._terminate_process()
            if stderr_thread is not None:
                stderr_thread.join(timeout=0.5)
            self.state_changed.emit("live_stopped")
            LOGGER.info("SkellyCam native live capture stopped.")

    def _bridge_command(self) -> list[str]:
        camera_ids = ",".join(str(source.uri) for source in self._sources if source.kind == "webcam")
        if not camera_ids:
            raise RuntimeError("SkellyCam native backend only supports webcam sources.")
        bridge_path = Path(__file__).with_name("skellycam_native_bridge.py")
        return [
            sys.executable,
            str(bridge_path),
            "stream",
            "--cameras",
            camera_ids,
            "--width",
            str(self._requested_width),
            "--height",
            str(self._requested_height),
            "--fps",
            str(int(round(self._target_fps))),
            "--exposure",
            str(self._exposure),
            "--fourcc",
            self._fourcc,
            "--camera-controls",
            json.dumps(self._camera_controls, separators=(",", ":")),
            "--output-fps",
            str(self._target_fps),
        ]

    def _handle_bridge_line(self, line: str) -> None:
        line = line.strip()
        if not line or not line.startswith("{"):
            if line:
                LOGGER.debug("SkellyCam bridge: %s", line)
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            LOGGER.debug("SkellyCam bridge non-json: %s", line)
            return
        message_type = payload.get("type")
        if message_type == "started":
            mode = str(payload.get("mode") or "")
            if mode:
                LOGGER.info("Live capture bridge started in %s mode.", mode)
            self.state_changed.emit("live_started")
            return
        if message_type == "warning":
            LOGGER.warning("SkellyCam bridge: %s", payload.get("message", ""))
            return
        if message_type == "camera_controls":
            LOGGER.info(
                "SkellyCam camera controls for %s: %s",
                payload.get("camera", ""),
                payload.get("actual", {}),
            )
            return
        if message_type == "stopped":
            self.state_changed.emit("live_stopped")
            return
        if message_type == "error":
            raise RuntimeError(str(payload.get("message", "SkellyCam native bridge failed.")))
        if message_type != "frames":
            return

        frames_payload = payload.get("frames", {})
        if not isinstance(frames_payload, dict):
            return
        timestamp_sec = time.time()
        batch: dict[str, FramePacket] = {}
        for camera_id, frame_payload in frames_payload.items():
            if not isinstance(frame_payload, dict):
                continue
            jpeg_b64 = frame_payload.get("jpeg_b64")
            if not isinstance(jpeg_b64, str):
                continue
            image_bytes = np.frombuffer(base64.b64decode(jpeg_b64), dtype=np.uint8)
            frame_bgr = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
            if frame_bgr is None:
                continue
            source_id = self._camera_id_to_source_id.get(str(camera_id), f"cam{camera_id}")
            batch[source_id] = FramePacket(
                source_id=source_id,
                frame_index=int(frame_payload.get("frame_index") or 0),
                timestamp_sec=float(frame_payload.get("timestamp_sec") or timestamp_sec),
                frame_bgr=frame_bgr,
            )
        if batch:
            self.batch_ready.emit(batch)

    def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            line = line.strip()
            if line:
                LOGGER.debug("SkellyCam bridge stderr: %s", line)
                try:
                    self._stderr_lines.put_nowait(line)
                except queue.Full:
                    try:
                        self._stderr_lines.get_nowait()
                    except queue.Empty:
                        pass
                    self._stderr_lines.put_nowait(line)

    def _terminate_process(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def _stderr_detail(self) -> str:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._stderr_lines.get_nowait())
            except queue.Empty:
                break
        if not lines:
            return ""
        return f" {lines[-1]}"

    def _terminate_process_after_grace(self, grace_sec: float) -> None:
        time.sleep(max(0.0, grace_sec))
        process = self._process
        if process is None or process.poll() is not None:
            return
        LOGGER.warning("SkellyCam bridge did not stop in time; terminating helper process.")
        try:
            process.terminate()
        except Exception:  # noqa: BLE001
            pass
