from __future__ import annotations

import math
from dataclasses import dataclass

from models.types import FramePacket, Pose2D, Pose2DKeypoint

from .contracts import PoseDetector


@dataclass(frozen=True, slots=True)
class _TemplatePoint:
    name: str
    x_offset: float
    y_offset: float
    base_confidence: float


_POSE_TEMPLATE = [
    _TemplatePoint("nose", 0.0, -0.22, 0.72),
    _TemplatePoint("left_shoulder", -0.11, -0.12, 0.76),
    _TemplatePoint("right_shoulder", 0.11, -0.12, 0.76),
    _TemplatePoint("left_elbow", -0.18, 0.02, 0.70),
    _TemplatePoint("right_elbow", 0.18, 0.02, 0.70),
    _TemplatePoint("left_wrist", -0.22, 0.18, 0.66),
    _TemplatePoint("right_wrist", 0.22, 0.18, 0.66),
    _TemplatePoint("left_hip", -0.08, 0.12, 0.78),
    _TemplatePoint("right_hip", 0.08, 0.12, 0.78),
    _TemplatePoint("left_knee", -0.10, 0.30, 0.74),
    _TemplatePoint("right_knee", 0.10, 0.30, 0.74),
    _TemplatePoint("left_ankle", -0.12, 0.46, 0.68),
    _TemplatePoint("right_ankle", 0.12, 0.46, 0.68),
]


class SyntheticPoseDetector(PoseDetector):
    name = "synthetic_pose_detector"

    def detect(self, frame: FramePacket) -> Pose2D:
        seed = _stable_seed(frame.source_id)
        phase = (frame.frame_index * 0.17) + (seed * 0.003)
        source_phase = (seed % 17) * 0.11

        sway = 0.05 * math.sin(phase + source_phase)
        bob = 0.03 * math.cos((phase * 0.7) + source_phase)
        scale = 1.0 + 0.03 * math.sin((phase * 0.37) + 0.4)

        keypoints: list[Pose2DKeypoint] = []
        for index, template in enumerate(_POSE_TEMPLATE):
            wobble_x = 0.008 * math.sin(phase + (index * 0.61) + source_phase)
            wobble_y = 0.008 * math.cos((phase * 0.8) + (index * 0.49) + source_phase)
            x = _clamp(0.5 + sway + (template.x_offset * scale) + wobble_x, 0.02, 0.98)
            y = _clamp(0.56 + bob + (template.y_offset * scale) + wobble_y, 0.02, 0.98)
            confidence = _clamp(template.base_confidence - (0.02 * abs(wobble_x + wobble_y)), 0.0, 1.0)
            keypoints.append(
                Pose2DKeypoint(
                    name=template.name,
                    x=x,
                    y=y,
                    confidence=confidence,
                )
            )

        return Pose2D(
            source_id=frame.source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            keypoints=keypoints,
        )


def _stable_seed(source_id: str) -> float:
    total = 0
    for index, character in enumerate(source_id):
        total += (index + 1) * ord(character)
    return float(total)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
