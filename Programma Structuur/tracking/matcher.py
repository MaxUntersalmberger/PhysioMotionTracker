from __future__ import annotations

from collections import defaultdict

from models.types import Pose2D, Pose2DKeypoint

from pipeline.contracts import PoseMatcher


class SemanticKeypointMatcher(PoseMatcher):
    name = "semantic_keypoint_matcher"

    def __init__(self, min_confidence: float = 0.25) -> None:
        self._min_confidence = max(0.0, float(min_confidence))

    def match(self, poses_by_camera: dict[str, Pose2D]) -> dict[str, dict[str, Pose2DKeypoint]]:
        grouped: dict[str, dict[str, Pose2DKeypoint]] = defaultdict(dict)
        for source_id, pose in poses_by_camera.items():
            for keypoint in pose.keypoints:
                if keypoint.confidence < self._min_confidence:
                    continue
                grouped[keypoint.name][source_id] = keypoint
        return dict(grouped)
