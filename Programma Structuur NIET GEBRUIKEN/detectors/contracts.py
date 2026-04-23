from __future__ import annotations

from typing import Protocol

from models.types import FramePacket, Pose2D


class PoseDetector(Protocol):
    name: str

    def detect(self, frame: FramePacket) -> Pose2D:
        ...
