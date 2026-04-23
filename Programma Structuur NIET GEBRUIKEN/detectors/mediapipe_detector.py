from __future__ import annotations

from pathlib import Path
from typing import Any

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision import pose_landmarker
from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode

from models.types import FramePacket, Pose2D, Pose2DKeypoint

from .contracts import PoseDetector


_POSE_LANDMARK_NAMES = tuple(landmark.name.lower() for landmark in pose_landmarker.PoseLandmark)


class MediaPipePoseDetector(PoseDetector):
    name = "mediapipe_pose_detector"

    def __init__(
        self,
        model_asset_path: Path | str | None = None,
        num_poses: int = 1,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._model_asset_path = self._resolve_model_asset_path(model_asset_path)
        self._options = pose_landmarker.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self._model_asset_path)),
            running_mode=VisionTaskRunningMode.IMAGE,
            num_poses=max(1, int(num_poses)),
            min_pose_detection_confidence=float(min_detection_confidence),
            min_pose_presence_confidence=float(min_presence_confidence),
            min_tracking_confidence=float(min_tracking_confidence),
        )
        self._landmarker = pose_landmarker.PoseLandmarker.create_from_options(self._options)

    @property
    def model_asset_path(self) -> Path:
        return self._model_asset_path

    def detect(self, frame: FramePacket) -> Pose2D:
        rgb_frame = self._frame_to_rgb_array(frame.frame_data)
        if rgb_frame is None:
            raise ValueError("MediaPipePoseDetector expects an image-like numpy frame.")

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect(image)
        return self._result_to_pose(frame, result)

    def close(self) -> None:
        close = getattr(self._landmarker, "close", None)
        if callable(close):
            close()

    def _result_to_pose(self, frame: FramePacket, result: Any) -> Pose2D:
        if not getattr(result, "pose_landmarks", None):
            return Pose2D(
                source_id=frame.source_id,
                frame_index=frame.frame_index,
                timestamp_sec=frame.timestamp_sec,
                keypoints=[],
            )

        landmarks = result.pose_landmarks[0]
        keypoints: list[Pose2DKeypoint] = []
        for index, landmark in enumerate(landmarks):
            name = _POSE_LANDMARK_NAMES[index] if index < len(_POSE_LANDMARK_NAMES) else f"landmark_{index}"
            confidence = max(
                0.0,
                float(getattr(landmark, "visibility", 0.0) or 0.0),
                float(getattr(landmark, "presence", 0.0) or 0.0),
            )
            keypoints.append(
                Pose2DKeypoint(
                    name=name,
                    x=float(landmark.x),
                    y=float(landmark.y),
                    confidence=confidence,
                )
            )

        return Pose2D(
            source_id=frame.source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            keypoints=keypoints,
        )

    def _frame_to_rgb_array(self, frame_data: Any) -> np.ndarray | None:
        if frame_data is None or not hasattr(frame_data, "shape"):
            return None

        array = np.asarray(frame_data)
        if array.ndim == 2:
            rgb_frame = np.repeat(array[:, :, None], 3, axis=2)
        elif array.ndim >= 3 and array.shape[2] >= 3:
            rgb_frame = array[:, :, :3][:, :, ::-1]
        else:
            return None

        return np.ascontiguousarray(rgb_frame, dtype=np.uint8)

    def _resolve_model_asset_path(self, model_asset_path: Path | str | None) -> Path:
        if model_asset_path is None:
            model_asset_path = Path(__file__).resolve().parents[1] / "models" / "pose_landmarker_full.task"

        path = Path(model_asset_path)
        if not path.exists():
            raise FileNotFoundError(f"MediaPipe pose landmarker model not found: {path}")
        return path
