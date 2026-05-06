from __future__ import annotations

from dataclasses import dataclass, field

from models.types import Pose2D, Pose2DKeypoint


BODY_KEYPOINTS = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)


@dataclass(slots=True)
class ConfidencePolicy:
    min_confidence: float = 0.25
    expected_keypoints: tuple[str, ...] = BODY_KEYPOINTS
    max_missing_ratio: float = 0.45


@dataclass(slots=True)
class PoseQualityReport:
    source_id: str
    raw_keypoints: int
    kept_keypoints: int
    missing_keypoints: list[str] = field(default_factory=list)
    low_confidence_keypoints: list[str] = field(default_factory=list)
    occlusion_status: str = "unknown"
    notes: list[str] = field(default_factory=list)


def apply_confidence_policy(pose: Pose2D, policy: ConfidencePolicy) -> tuple[Pose2D, PoseQualityReport]:
    kept: list[Pose2DKeypoint] = []
    low_confidence: list[str] = []
    for keypoint in pose.keypoints:
        if keypoint.confidence >= policy.min_confidence:
            kept.append(keypoint)
        else:
            low_confidence.append(keypoint.name)

    kept_names = {keypoint.name for keypoint in kept}
    missing = [name for name in policy.expected_keypoints if name not in kept_names]
    missing_ratio = len(missing) / max(1, len(policy.expected_keypoints))
    status = "clear"
    notes: list[str] = []
    if missing_ratio > 0:
        status = "partial"
    if missing_ratio >= policy.max_missing_ratio:
        status = "occluded"
        notes.append(
            f"{len(missing)}/{len(policy.expected_keypoints)} expected body keypoints are missing or low confidence."
        )
    if low_confidence:
        notes.append(f"Low-confidence keypoints filtered: {', '.join(low_confidence[:8])}.")

    filtered_pose = Pose2D(
        source_id=pose.source_id,
        frame_index=pose.frame_index,
        timestamp_sec=pose.timestamp_sec,
        keypoints=kept,
    )
    report = PoseQualityReport(
        source_id=pose.source_id,
        raw_keypoints=len(pose.keypoints),
        kept_keypoints=len(kept),
        missing_keypoints=missing,
        low_confidence_keypoints=low_confidence,
        occlusion_status=status,
        notes=notes,
    )
    return filtered_pose, report
