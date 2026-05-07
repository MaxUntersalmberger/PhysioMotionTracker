from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models.types import Pose2D, Pose2DKeypoint, Pose3D, Pose3DKeypoint


MOTION_TAKE_SCHEMA_VERSION = 1


@dataclass(slots=True)
class MotionTakeSummary:
    frame_count: int = 0
    source_count: int = 0
    pose2d_frames: int = 0
    pose3d_frames: int = 0
    pose2d_keypoints: int = 0
    pose3d_keypoints: int = 0
    reconstruction_modes: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class MotionTakeFrame:
    batch_index: int
    frame_index: int
    timestamp_sec: float
    poses_2d: dict[str, Pose2D]
    pose_3d: Pose3D | None
    reconstruction_mode: str
    reconstruction_trust_score: float = 0.0
    reconstruction_trust_state: str = "unavailable"
    mean_reprojection_error_px: float | None = None
    per_joint_reprojection_error_px: dict[str, float] = field(default_factory=dict)
    per_joint_view_count: dict[str, int] = field(default_factory=dict)
    per_joint_confidence: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MotionTake:
    schema_version: int
    take_id: str
    session_id: str
    created_at_iso: str
    source_session_dir: str
    detector_name: str
    calibration_loaded: bool
    calibration_file: str | None
    stages: dict[str, str]
    summary: MotionTakeSummary
    frames: list[MotionTakeFrame] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MotionTakeRepository:
    def default_path(self, session_dir: Path) -> Path:
        return session_dir / "processed" / "motion_take.json"

    def save(self, take: MotionTake, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(motion_take_to_payload(take), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        return path

    def load(self, path: Path) -> MotionTake:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Motion take payload at {path} is not an object.")
        return motion_take_from_payload(payload)


def build_motion_take_summary(frames: list[MotionTakeFrame], source_count: int) -> MotionTakeSummary:
    reconstruction_modes: Counter[str] = Counter()
    pose2d_frames = 0
    pose3d_frames = 0
    pose2d_keypoints = 0
    pose3d_keypoints = 0

    for frame in frames:
        reconstruction_modes[frame.reconstruction_mode] += 1
        if frame.poses_2d:
            pose2d_frames += 1
            pose2d_keypoints += sum(len(pose.keypoints) for pose in frame.poses_2d.values())
        if frame.pose_3d is not None:
            pose3d_frames += 1
            pose3d_keypoints += len(frame.pose_3d.keypoints)

    return MotionTakeSummary(
        frame_count=len(frames),
        source_count=source_count,
        pose2d_frames=pose2d_frames,
        pose3d_frames=pose3d_frames,
        pose2d_keypoints=pose2d_keypoints,
        pose3d_keypoints=pose3d_keypoints,
        reconstruction_modes=dict(sorted(reconstruction_modes.items())),
    )


def motion_take_to_payload(take: MotionTake) -> dict[str, Any]:
    return {
        "schema_version": take.schema_version,
        "take_id": take.take_id,
        "session_id": take.session_id,
        "created_at_iso": take.created_at_iso,
        "source_session_dir": take.source_session_dir,
        "detector_name": take.detector_name,
        "calibration_loaded": take.calibration_loaded,
        "calibration_file": take.calibration_file,
        "stages": dict(take.stages),
        "summary": {
            "frame_count": take.summary.frame_count,
            "source_count": take.summary.source_count,
            "pose2d_frames": take.summary.pose2d_frames,
            "pose3d_frames": take.summary.pose3d_frames,
            "pose2d_keypoints": take.summary.pose2d_keypoints,
            "pose3d_keypoints": take.summary.pose3d_keypoints,
            "reconstruction_modes": dict(take.summary.reconstruction_modes),
        },
        "frames": [_frame_to_payload(frame) for frame in take.frames],
        "metadata": dict(take.metadata),
    }


def motion_take_from_payload(payload: dict[str, Any]) -> MotionTake:
    summary_payload = payload.get("summary", {})
    frames_payload = payload.get("frames", [])
    if not isinstance(summary_payload, dict):
        summary_payload = {}
    if not isinstance(frames_payload, list):
        frames_payload = []

    return MotionTake(
        schema_version=int(payload.get("schema_version", MOTION_TAKE_SCHEMA_VERSION)),
        take_id=str(payload.get("take_id", "")),
        session_id=str(payload.get("session_id", "")),
        created_at_iso=str(payload.get("created_at_iso", "")),
        source_session_dir=str(payload.get("source_session_dir", "")),
        detector_name=str(payload.get("detector_name", "")),
        calibration_loaded=bool(payload.get("calibration_loaded", False)),
        calibration_file=str(payload["calibration_file"]) if payload.get("calibration_file") else None,
        stages={str(key): str(value) for key, value in dict(payload.get("stages", {})).items()},
        summary=MotionTakeSummary(
            frame_count=int(summary_payload.get("frame_count", 0)),
            source_count=int(summary_payload.get("source_count", 0)),
            pose2d_frames=int(summary_payload.get("pose2d_frames", 0)),
            pose3d_frames=int(summary_payload.get("pose3d_frames", 0)),
            pose2d_keypoints=int(summary_payload.get("pose2d_keypoints", 0)),
            pose3d_keypoints=int(summary_payload.get("pose3d_keypoints", 0)),
            reconstruction_modes={
                str(key): int(value)
                for key, value in dict(summary_payload.get("reconstruction_modes", {})).items()
            },
        ),
        frames=[_frame_from_payload(item) for item in frames_payload if isinstance(item, dict)],
        metadata=dict(payload.get("metadata", {})),
    )


def _frame_to_payload(frame: MotionTakeFrame) -> dict[str, Any]:
    return {
        "batch_index": frame.batch_index,
        "frame_index": frame.frame_index,
        "timestamp_sec": frame.timestamp_sec,
        "poses_2d": {
            source_id: {
                "frame_index": pose.frame_index,
                "timestamp_sec": pose.timestamp_sec,
                "keypoints": [_pose2d_keypoint_to_payload(keypoint) for keypoint in pose.keypoints],
            }
            for source_id, pose in sorted(frame.poses_2d.items())
        },
        "pose_3d": _pose3d_to_payload(frame.pose_3d),
        "reconstruction_mode": frame.reconstruction_mode,
        "reconstruction_trust_score": frame.reconstruction_trust_score,
        "reconstruction_trust_state": frame.reconstruction_trust_state,
        "mean_reprojection_error_px": frame.mean_reprojection_error_px,
        "per_joint_reprojection_error_px": dict(frame.per_joint_reprojection_error_px),
        "per_joint_view_count": dict(frame.per_joint_view_count),
        "per_joint_confidence": dict(frame.per_joint_confidence),
        "notes": list(frame.notes),
    }


def _frame_from_payload(payload: dict[str, Any]) -> MotionTakeFrame:
    poses_payload = payload.get("poses_2d", {})
    poses_2d: dict[str, Pose2D] = {}
    if isinstance(poses_payload, dict):
        for source_id, pose_payload in poses_payload.items():
            if isinstance(pose_payload, dict):
                poses_2d[str(source_id)] = _pose2d_from_payload(str(source_id), pose_payload)

    return MotionTakeFrame(
        batch_index=int(payload.get("batch_index", 0)),
        frame_index=int(payload.get("frame_index", 0)),
        timestamp_sec=float(payload.get("timestamp_sec", 0.0)),
        poses_2d=poses_2d,
        pose_3d=_pose3d_from_payload(payload.get("pose_3d")),
        reconstruction_mode=str(payload.get("reconstruction_mode", "unavailable")),
        reconstruction_trust_score=float(payload.get("reconstruction_trust_score", 0.0)),
        reconstruction_trust_state=str(payload.get("reconstruction_trust_state", "unavailable")),
        mean_reprojection_error_px=(
            float(payload["mean_reprojection_error_px"])
            if payload.get("mean_reprojection_error_px") is not None
            else None
        ),
        per_joint_reprojection_error_px={
            str(key): float(value)
            for key, value in dict(payload.get("per_joint_reprojection_error_px", {})).items()
        },
        per_joint_view_count={
            str(key): int(value)
            for key, value in dict(payload.get("per_joint_view_count", {})).items()
        },
        per_joint_confidence={
            str(key): float(value)
            for key, value in dict(payload.get("per_joint_confidence", {})).items()
        },
        notes=[str(note) for note in payload.get("notes", [])],
    )


def _pose2d_from_payload(source_id: str, payload: dict[str, Any]) -> Pose2D:
    keypoints_payload = payload.get("keypoints", [])
    return Pose2D(
        source_id=source_id,
        frame_index=int(payload.get("frame_index", 0)),
        timestamp_sec=float(payload.get("timestamp_sec", 0.0)),
        keypoints=[
            Pose2DKeypoint(
                name=str(item.get("name", "")),
                x=float(item.get("x", 0.0)),
                y=float(item.get("y", 0.0)),
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in keypoints_payload
            if isinstance(item, dict)
        ],
    )


def _pose3d_from_payload(payload: object) -> Pose3D | None:
    if not isinstance(payload, dict):
        return None
    keypoints_payload = payload.get("keypoints", [])
    return Pose3D(
        frame_index=int(payload.get("frame_index", 0)),
        timestamp_sec=float(payload.get("timestamp_sec", 0.0)),
        keypoints=[
            Pose3DKeypoint(
                name=str(item.get("name", "")),
                x=float(item.get("x", 0.0)),
                y=float(item.get("y", 0.0)),
                z=float(item.get("z", 0.0)),
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in keypoints_payload
            if isinstance(item, dict)
        ],
    )


def _pose2d_keypoint_to_payload(keypoint: Pose2DKeypoint) -> dict[str, float | str]:
    return {
        "name": keypoint.name,
        "x": keypoint.x,
        "y": keypoint.y,
        "confidence": keypoint.confidence,
    }


def _pose3d_to_payload(pose: Pose3D | None) -> dict[str, Any] | None:
    if pose is None:
        return None
    return {
        "frame_index": pose.frame_index,
        "timestamp_sec": pose.timestamp_sec,
        "keypoints": [
            {
                "name": keypoint.name,
                "x": keypoint.x,
                "y": keypoint.y,
                "z": keypoint.z,
                "confidence": keypoint.confidence,
            }
            for keypoint in pose.keypoints
        ],
    }
