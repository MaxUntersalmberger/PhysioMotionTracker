from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from models.types import CalibrationBundle, FramePacket, Pose2D, Pose2DKeypoint, Pose3D


@dataclass(slots=True)
class TriangulationResult:
    pose_3d: Pose3D | None
    reprojected_points_px: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)
    per_joint_error_px: dict[str, float] = field(default_factory=dict)
    per_joint_view_count: dict[str, int] = field(default_factory=dict)
    per_joint_confidence: dict[str, float] = field(default_factory=dict)
    trust_score: float = 0.0
    trust_state: str = "unavailable"
    mode: str = "unavailable"
    reconstructed_joints: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def mean_reprojection_error_px(self) -> float | None:
        if not self.per_joint_error_px:
            return None
        values = list(self.per_joint_error_px.values())
        return float(sum(values) / len(values))


class PoseDetector(Protocol):
    name: str

    def detect(self, frame: FramePacket) -> Pose2D:
        ...


class PoseMatcher(Protocol):
    name: str

    def match(self, poses_by_camera: dict[str, Pose2D]) -> dict[str, dict[str, Pose2DKeypoint]]:
        ...


class PoseTriangulator(Protocol):
    name: str

    def set_calibration(self, bundle: CalibrationBundle | None) -> None:
        ...

    def triangulate(
        self,
        matched_keypoints: dict[str, dict[str, Pose2DKeypoint]],
        frames: dict[str, FramePacket],
        frame_index: int,
        timestamp_sec: float,
    ) -> TriangulationResult:
        ...


class PoseSmoother(Protocol):
    def reset(self) -> None:
        ...

    def apply(self, pose: Pose3D) -> Pose3D:
        ...
