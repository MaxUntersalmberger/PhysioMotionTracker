from __future__ import annotations

from models.types import FramePacket, Pose2D

from .contracts import PoseDetector


class NullPoseDetector(PoseDetector):
    name = "null_pose_detector"

    def detect(self, frame: FramePacket) -> Pose2D:
        return Pose2D(
            source_id=frame.source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            keypoints=[],
        )
