from __future__ import annotations

import argparse
import base64
import json
import platform
import sys
import threading
import time
from typing import Any

import cv2


CAMERA_CONTROL_PROPS = {
    "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast": cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue": cv2.CAP_PROP_HUE,
    "gain": cv2.CAP_PROP_GAIN,
    "sharpness": cv2.CAP_PROP_SHARPNESS,
    "gamma": cv2.CAP_PROP_GAMMA,
    "temperature": cv2.CAP_PROP_TEMPERATURE,
    "backlight": cv2.CAP_PROP_BACKLIGHT,
    "auto_wb": cv2.CAP_PROP_AUTO_WB,
    "wb_temperature": cv2.CAP_PROP_WB_TEMPERATURE,
    "autofocus": cv2.CAP_PROP_AUTOFOCUS,
    "focus": cv2.CAP_PROP_FOCUS,
    "zoom": cv2.CAP_PROP_ZOOM,
    "pan": cv2.CAP_PROP_PAN,
    "tilt": cv2.CAP_PROP_TILT,
    "roll": cv2.CAP_PROP_ROLL,
    "iris": cv2.CAP_PROP_IRIS,
    "trigger": cv2.CAP_PROP_TRIGGER,
    "trigger_delay": cv2.CAP_PROP_TRIGGER_DELAY,
    "aperture": cv2.CAP_PROP_APERTURE,
    "exposure_program": cv2.CAP_PROP_EXPOSUREPROGRAM,
}


def _write(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def _detect(max_index: int) -> int:
    camera_ids: list[str] = []
    for index in range(max(0, int(max_index)) + 1):
        capture = cv2.VideoCapture(index, _opencv_backend())
        try:
            if capture.isOpened():
                camera_ids.append(str(index))
        finally:
            capture.release()
    _write({"type": "detect", "cameras": camera_ids, "backend": "OpenCV"})
    return 0


def _parse_camera_controls(raw: str) -> dict[str, float]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        _write({"type": "warning", "message": "Camera controls JSON could not be parsed."})
        return {}
    if not isinstance(payload, dict):
        return {}
    controls: dict[str, float] = {}
    for key, value in payload.items():
        if key not in CAMERA_CONTROL_PROPS:
            continue
        try:
            controls[key] = float(value)
        except (TypeError, ValueError):
            continue
    return controls


def _apply_camera_controls(camera: Any, controls: dict[str, float]) -> None:
    if not controls:
        return
    capture_thread = getattr(camera, "_capture_thread", None)
    capture = getattr(capture_thread, "_cv2_video_capture", None)
    if capture is None:
        _write({"type": "warning", "message": f"{camera.camera_id}: camera controls unavailable."})
        return
    failed: list[str] = []
    actual: dict[str, float] = {}
    for key, value in controls.items():
        prop_id = CAMERA_CONTROL_PROPS[key]
        try:
            ok = bool(capture.set(prop_id, value))
            actual[key] = float(capture.get(prop_id))
        except Exception:
            ok = False
        if not ok:
            failed.append(key)
    if failed:
        _write(
            {
                "type": "warning",
                "message": f"{camera.camera_id}: unsupported camera control(s): {', '.join(failed)}.",
            }
        )
    _write({"type": "camera_controls", "camera": str(camera.camera_id), "actual": actual})


def _opencv_backend() -> int:
    if platform.system().lower().startswith("win"):
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY


def _fourcc_int(fourcc: str) -> int:
    safe = (fourcc or "MJPG").upper()[:4].ljust(4)
    return cv2.VideoWriter_fourcc(*safe)


def _open_cv2_camera(camera_id: str, args: argparse.Namespace, controls: dict[str, float]) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(int(camera_id), _opencv_backend())
    if not capture.isOpened():
        raise RuntimeError(f"Camera {camera_id} could not be opened.")

    width = int(args.width)
    height = int(args.height)
    fps = float(args.fps)
    if width > 0:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height > 0:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps > 0:
        capture.set(cv2.CAP_PROP_FPS, fps)
    if args.fourcc:
        capture.set(cv2.CAP_PROP_FOURCC, _fourcc_int(args.fourcc))
    if int(args.exposure) != -1:
        capture.set(cv2.CAP_PROP_EXPOSURE, int(args.exposure))

    actual: dict[str, float] = {
        "width": float(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": float(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": float(capture.get(cv2.CAP_PROP_FPS)),
        "exposure": float(capture.get(cv2.CAP_PROP_EXPOSURE)),
    }
    failed: list[str] = []
    for key, value in controls.items():
        prop_id = CAMERA_CONTROL_PROPS[key]
        try:
            ok = bool(capture.set(prop_id, value))
            actual[key] = float(capture.get(prop_id))
        except Exception:
            ok = False
        if not ok:
            failed.append(key)
    if failed:
        _write(
            {
                "type": "warning",
                "message": f"{camera_id}: unsupported camera control(s): {', '.join(failed)}.",
            }
        )
    _write({"type": "camera_controls", "camera": str(camera_id), "actual": actual})

    # Warm up enough for UVC auto controls to settle a little and to verify the stream.
    ok = False
    for _ in range(8):
        ok, frame = capture.read()
        if ok and frame is not None:
            break
        time.sleep(0.03)
    if not ok:
        capture.release()
        raise RuntimeError(f"Camera {camera_id} opened but did not return frames.")
    return capture


def _stream_synchronized_cv2(args: argparse.Namespace, camera_ids: list[str], stop_event: threading.Event) -> int:
    controls = _parse_camera_controls(args.camera_controls)
    captures: dict[str, cv2.VideoCapture] = {}
    frame_number = 0
    try:
        for camera_id in camera_ids:
            if stop_event.is_set():
                break
            captures[camera_id] = _open_cv2_camera(camera_id, args, controls)
        if not captures:
            _write({"type": "error", "message": "No cameras could be started."})
            return 1

        _write({"type": "started", "cameras": list(captures), "mode": "synchronized_cv2"})
        output_fps = float(args.output_fps or args.fps or 30.0)
        frame_interval_sec = 1.0 / max(1.0, output_fps)
        jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)]
        next_frame_at = time.perf_counter()

        while captures and not stop_event.is_set():
            now = time.perf_counter()
            if now < next_frame_at:
                time.sleep(min(0.002, next_frame_at - now))
                continue

            grab_timestamp_sec = time.perf_counter_ns() / 1_000_000_000.0
            grabbed: dict[str, bool] = {}
            for camera_id, capture in captures.items():
                grabbed[camera_id] = bool(capture.grab())

            batch: dict[str, dict[str, Any]] = {}
            all_ok = True
            for camera_id, capture in captures.items():
                if not grabbed.get(camera_id, False):
                    all_ok = False
                    break
                ok, image = capture.retrieve()
                if not ok or image is None:
                    all_ok = False
                    break
                ok, encoded = cv2.imencode(".jpg", image, jpeg_params)
                if not ok:
                    all_ok = False
                    break
                batch[camera_id] = {
                    "frame_index": frame_number,
                    "timestamp_sec": grab_timestamp_sec,
                    "jpeg_b64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                }

            if all_ok and len(batch) == len(captures):
                _write({"type": "frames", "frames": batch, "frame_index": frame_number})
                frame_number += 1
            else:
                _write({"type": "warning", "message": "Dropped incomplete synchronized camera frame."})
            next_frame_at = max(next_frame_at + frame_interval_sec, time.perf_counter())
    except Exception as exc:
        _write({"type": "error", "message": str(exc)})
        return 1
    finally:
        for capture in captures.values():
            try:
                capture.release()
            except Exception:
                pass
        _write({"type": "stopped"})
    return 0


def _stream(args: argparse.Namespace) -> int:
    camera_ids = [token.strip() for token in args.cameras.split(",") if token.strip()]
    if not camera_ids:
        _write({"type": "error", "message": "No camera ids were provided."})
        return 2

    stop_event = threading.Event()

    def _watch_stdin() -> None:
        for line in sys.stdin:
            if line.strip().upper() == "STOP":
                stop_event.set()
                break

    threading.Thread(target=_watch_stdin, daemon=True).start()

    if args.capture_mode == "synchronized_cv2":
        return _stream_synchronized_cv2(args=args, camera_ids=camera_ids, stop_event=stop_event)

    from skellycam import Camera, CameraConfig

    cameras: dict[str, Camera] = {}
    camera_controls = _parse_camera_controls(args.camera_controls)
    try:
        for camera_id in camera_ids:
            if stop_event.is_set():
                break
            config = CameraConfig(
                camera_id=camera_id,
                exposure=int(args.exposure),
                resolution_width=int(args.width),
                resolution_height=int(args.height),
                framerate=int(args.fps),
                fourcc=args.fourcc,
                rotate_video_cv2_code=-1,
                use_this_camera=True,
            )
            camera = Camera(config)
            camera.connect()
            _apply_camera_controls(camera, camera_controls)
            cameras[camera_id] = camera
        if not cameras:
            _write({"type": "error", "message": "No SkellyCam cameras could be started."})
            return 1
        _write({"type": "started", "cameras": list(cameras)})
        last_frame_numbers_seen: dict[str, int] = {}
        last_frame_numbers_sent: dict[str, int] = {}
        latest_payloads: dict[str, Any] = {}
        send_interval_sec = 1.0 / max(1.0, float(args.output_fps or args.fps))
        next_send_at = time.perf_counter()
        jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)]
        while cameras and not stop_event.is_set():
            for camera_id, camera in list(cameras.items()):
                if not camera.is_capturing_frames:
                    cameras.pop(camera_id, None)
                    continue
                if not camera.new_frame_ready:
                    continue
                payload = camera.latest_frame
                if payload is None or not payload.success or payload.image is None:
                    continue
                frame_index = int(payload.number_of_frames_received or 0)
                if last_frame_numbers_seen.get(camera_id) == frame_index:
                    continue
                last_frame_numbers_seen[camera_id] = frame_index
                latest_payloads[camera_id] = payload

            now = time.perf_counter()
            if now < next_send_at:
                time.sleep(0.002)
                continue

            batch: dict[str, dict[str, Any]] = {}
            for camera_id, payload in list(latest_payloads.items()):
                frame_index = int(payload.number_of_frames_received or 0)
                if last_frame_numbers_sent.get(camera_id) == frame_index:
                    continue
                ok, encoded = cv2.imencode(".jpg", payload.image, jpeg_params)
                if not ok:
                    continue
                last_frame_numbers_sent[camera_id] = frame_index
                batch[str(camera_id)] = {
                    "frame_index": frame_index,
                    "timestamp_sec": float(payload.timestamp_ns or time.time_ns()) / 1_000_000_000.0,
                    "jpeg_b64": base64.b64encode(encoded.tobytes()).decode("ascii"),
                }
            if batch:
                _write({"type": "frames", "frames": batch})
            next_send_at = now + send_interval_sec
    except Exception as exc:  # pragma: no cover - helper process surface area
        _write({"type": "error", "message": str(exc)})
        return 1
    finally:
        for camera in cameras.values():
            try:
                camera.close()
            except Exception:
                pass
        _write({"type": "stopped"})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SkellyCam native bridge for PhysioMotionTracker.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    detect_parser = subparsers.add_parser("detect")
    detect_parser.add_argument("--max-index", type=int, default=10)
    stream_parser = subparsers.add_parser("stream")
    stream_parser.add_argument("--cameras", required=True)
    stream_parser.add_argument("--width", type=int, default=1280)
    stream_parser.add_argument("--height", type=int, default=720)
    stream_parser.add_argument("--fps", type=int, default=30)
    stream_parser.add_argument("--fourcc", default="MJPG")
    stream_parser.add_argument("--exposure", type=int, default=-1)
    stream_parser.add_argument("--camera-controls", default="{}")
    stream_parser.add_argument("--output-fps", type=float, default=0.0)
    stream_parser.add_argument("--jpeg-quality", type=int, default=90)
    stream_parser.add_argument(
        "--capture-mode",
        choices=["synchronized_cv2", "legacy_skellycam_camera"],
        default="synchronized_cv2",
    )
    args = parser.parse_args()
    if args.command == "detect":
        return _detect(args.max_index)
    if args.command == "stream":
        return _stream(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
