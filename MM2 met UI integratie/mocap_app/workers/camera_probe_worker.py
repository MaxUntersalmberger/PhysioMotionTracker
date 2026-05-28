from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from mocap_app.models.types import CameraProbeResult


LOGGER = logging.getLogger(__name__)


class CameraProbeWorker(QThread):
    """Detect cameras through the same Python interpreter as the app."""

    result_ready = Signal(object)
    error = Signal(str)
    state_changed = Signal(str)

    def __init__(self, max_index: int = 10) -> None:
        super().__init__()
        self._max_index = max(0, int(max_index))
        self._stop_event = threading.Event()
        self._process: subprocess.Popen[str] | None = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()

    def run(self) -> None:
        try:
            self.state_changed.emit("skellycam_camera_probe_started")
            bridge_path = Path(__file__).with_name("skellycam_native_bridge.py")
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            self._process = subprocess.Popen(
                [
                    sys.executable,
                    str(bridge_path),
                    "detect",
                    "--max-index",
                    str(self._max_index),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            stdout, stderr = self._process.communicate(timeout=30)
            if stderr.strip():
                LOGGER.debug("SkellyCam detect stderr: %s", stderr.strip())
            if self._process.returncode not in (0, None):
                detail = _bridge_error_detail(stdout, stderr)
                raise RuntimeError(
                    f"Camera detect failed with exit code {self._process.returncode}.{detail}"
                )
            cameras: list[str] = []
            for line in stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                payload = json.loads(line)
                if payload.get("type") == "detect":
                    cameras = [str(camera_id) for camera_id in payload.get("cameras", [])]
                    break
            results = []
            for camera_id in cameras:
                try:
                    index = int(camera_id)
                except ValueError:
                    continue
                if index <= self._max_index:
                    results.append(
                        CameraProbeResult(
                            index=index,
                            opened=True,
                            width=0,
                            height=0,
                            backend="OpenCV",
                        )
                    )
            if self._stop_event.is_set():
                self.state_changed.emit("skellycam_camera_probe_stopped")
                return
            self.result_ready.emit(results)
            self.state_changed.emit("skellycam_camera_probe_finished")
        except Exception as exc:  # pragma: no cover
            LOGGER.exception("SkellyCam native camera probe failed.")
            self.error.emit(str(exc))
            self.state_changed.emit("skellycam_camera_probe_failed")


def _bridge_error_detail(stdout: str, stderr: str) -> str:
    messages: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "error" and payload.get("message"):
            messages.append(str(payload["message"]))
    if stderr.strip():
        messages.append(stderr.strip().splitlines()[-1])
    if not messages:
        return ""
    return f" {' '.join(messages)}"
