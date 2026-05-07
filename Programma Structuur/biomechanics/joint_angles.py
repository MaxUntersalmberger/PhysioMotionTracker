from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from models.types import Pose3D, Pose3DKeypoint
from motion import MotionTake


JOINT_ANGLE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class JointAngleDefinition:
    name: str
    proximal_keypoint: str
    center_keypoint: str
    distal_keypoint: str


@dataclass(slots=True)
class JointAngleSample:
    frame_index: int
    timestamp_sec: float
    joint_name: str
    angle_deg: float
    confidence: float


@dataclass(slots=True)
class JointAngleSummary:
    joint_name: str
    sample_count: int
    mean_deg: float
    min_deg: float
    max_deg: float


@dataclass(slots=True)
class JointAngleAnalysis:
    schema_version: int
    take_id: str
    session_id: str
    generated_at_iso: str
    source_take_file: str | None
    definitions: dict[str, tuple[str, str, str]]
    samples: list[JointAngleSample] = field(default_factory=list)
    summaries: dict[str, JointAngleSummary] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class JointAngleAnalysisReport:
    analysis: JointAngleAnalysis
    output_path: Path | None
    frames_with_pose3d: int
    notes: list[str] = field(default_factory=list)


JOINT_ANGLE_DEFINITIONS: tuple[JointAngleDefinition, ...] = (
    JointAngleDefinition("left_elbow_flexion", "left_shoulder", "left_elbow", "left_wrist"),
    JointAngleDefinition("right_elbow_flexion", "right_shoulder", "right_elbow", "right_wrist"),
    JointAngleDefinition("left_knee_flexion", "left_hip", "left_knee", "left_ankle"),
    JointAngleDefinition("right_knee_flexion", "right_hip", "right_knee", "right_ankle"),
    JointAngleDefinition("left_hip_angle", "left_shoulder", "left_hip", "left_knee"),
    JointAngleDefinition("right_hip_angle", "right_shoulder", "right_hip", "right_knee"),
    JointAngleDefinition("left_shoulder_angle", "left_hip", "left_shoulder", "left_elbow"),
    JointAngleDefinition("right_shoulder_angle", "right_hip", "right_shoulder", "right_elbow"),
)


class JointAngleRepository:
    def default_path(self, take_path: Path) -> Path:
        return take_path.parent / "analysis" / "joint_angles.json"

    def save(self, analysis: JointAngleAnalysis, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(joint_angle_analysis_to_payload(analysis), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return path

    def load(self, path: Path) -> JointAngleAnalysis:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Joint-angle analysis at {path} is not an object.")
        return joint_angle_analysis_from_payload(payload)


def analyze_motion_take_joint_angles(
    take: MotionTake,
    source_take_path: Path | None = None,
    output_path: Path | None = None,
    repository: JointAngleRepository | None = None,
) -> JointAngleAnalysisReport:
    samples: list[JointAngleSample] = []
    frames_with_pose3d = 0

    for frame in take.frames:
        if frame.pose_3d is None:
            continue
        frames_with_pose3d += 1
        samples.extend(_samples_from_pose(frame.pose_3d))

    notes: list[str] = []
    if frames_with_pose3d == 0:
        notes.append("No 3D pose frames are available; joint-angle analysis needs reconstructed 3D keypoints.")
    if not samples:
        notes.append("No joint angles could be computed from the available keypoints.")

    analysis = JointAngleAnalysis(
        schema_version=JOINT_ANGLE_SCHEMA_VERSION,
        take_id=take.take_id,
        session_id=take.session_id,
        generated_at_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
        source_take_file=str(source_take_path) if source_take_path is not None else None,
        definitions={
            definition.name: (
                definition.proximal_keypoint,
                definition.center_keypoint,
                definition.distal_keypoint,
            )
            for definition in JOINT_ANGLE_DEFINITIONS
        },
        samples=samples,
        summaries=_summaries_from_samples(samples),
        notes=notes,
    )

    saved_path: Path | None = None
    if output_path is not None or source_take_path is not None:
        joint_repository = repository or JointAngleRepository()
        saved_path = output_path or joint_repository.default_path(source_take_path)  # type: ignore[arg-type]
        joint_repository.save(analysis, saved_path)

    return JointAngleAnalysisReport(
        analysis=analysis,
        output_path=saved_path,
        frames_with_pose3d=frames_with_pose3d,
        notes=notes,
    )


def format_joint_angle_report(report: JointAngleAnalysisReport) -> str:
    analysis = report.analysis
    lines = [
        "Joint angle analysis",
        f"Session: {analysis.session_id}",
        f"Take: {analysis.take_id}",
        f"Output: {report.output_path}" if report.output_path is not None else "Output: not saved",
        f"3D frames: {report.frames_with_pose3d}",
        f"Angle samples: {len(analysis.samples)}",
    ]
    if analysis.summaries:
        lines.append("Joint summaries:")
        for summary in analysis.summaries.values():
            lines.append(
                f"- {summary.joint_name}: n={summary.sample_count}, "
                f"mean={summary.mean_deg:.1f} deg, range={summary.min_deg:.1f}-{summary.max_deg:.1f} deg"
            )
    if report.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in report.notes[:8])
    return "\n".join(lines)


def joint_angle_analysis_to_payload(analysis: JointAngleAnalysis) -> dict[str, Any]:
    return {
        "schema_version": analysis.schema_version,
        "take_id": analysis.take_id,
        "session_id": analysis.session_id,
        "generated_at_iso": analysis.generated_at_iso,
        "source_take_file": analysis.source_take_file,
        "definitions": {
            name: {
                "proximal_keypoint": values[0],
                "center_keypoint": values[1],
                "distal_keypoint": values[2],
            }
            for name, values in analysis.definitions.items()
        },
        "samples": [
            {
                "frame_index": sample.frame_index,
                "timestamp_sec": sample.timestamp_sec,
                "joint_name": sample.joint_name,
                "angle_deg": sample.angle_deg,
                "confidence": sample.confidence,
            }
            for sample in analysis.samples
        ],
        "summaries": {
            joint_name: {
                "sample_count": summary.sample_count,
                "mean_deg": summary.mean_deg,
                "min_deg": summary.min_deg,
                "max_deg": summary.max_deg,
            }
            for joint_name, summary in analysis.summaries.items()
        },
        "notes": list(analysis.notes),
    }


def joint_angle_analysis_from_payload(payload: dict[str, Any]) -> JointAngleAnalysis:
    definitions_payload = payload.get("definitions", {})
    samples_payload = payload.get("samples", [])
    summaries_payload = payload.get("summaries", {})

    definitions: dict[str, tuple[str, str, str]] = {}
    if isinstance(definitions_payload, dict):
        for name, definition_payload in definitions_payload.items():
            if isinstance(definition_payload, dict):
                definitions[str(name)] = (
                    str(definition_payload.get("proximal_keypoint", "")),
                    str(definition_payload.get("center_keypoint", "")),
                    str(definition_payload.get("distal_keypoint", "")),
                )

    samples = [
        JointAngleSample(
            frame_index=int(item.get("frame_index", 0)),
            timestamp_sec=float(item.get("timestamp_sec", 0.0)),
            joint_name=str(item.get("joint_name", "")),
            angle_deg=float(item.get("angle_deg", 0.0)),
            confidence=float(item.get("confidence", 0.0)),
        )
        for item in samples_payload
        if isinstance(item, dict)
    ]

    summaries: dict[str, JointAngleSummary] = {}
    if isinstance(summaries_payload, dict):
        for joint_name, summary_payload in summaries_payload.items():
            if isinstance(summary_payload, dict):
                summaries[str(joint_name)] = JointAngleSummary(
                    joint_name=str(joint_name),
                    sample_count=int(summary_payload.get("sample_count", 0)),
                    mean_deg=float(summary_payload.get("mean_deg", 0.0)),
                    min_deg=float(summary_payload.get("min_deg", 0.0)),
                    max_deg=float(summary_payload.get("max_deg", 0.0)),
                )

    return JointAngleAnalysis(
        schema_version=int(payload.get("schema_version", JOINT_ANGLE_SCHEMA_VERSION)),
        take_id=str(payload.get("take_id", "")),
        session_id=str(payload.get("session_id", "")),
        generated_at_iso=str(payload.get("generated_at_iso", "")),
        source_take_file=str(payload["source_take_file"]) if payload.get("source_take_file") else None,
        definitions=definitions,
        samples=samples,
        summaries=summaries,
        notes=[str(note) for note in payload.get("notes", [])],
    )


def _samples_from_pose(pose: Pose3D) -> list[JointAngleSample]:
    keypoints = pose.keypoints_by_name()
    samples: list[JointAngleSample] = []
    for definition in JOINT_ANGLE_DEFINITIONS:
        proximal = keypoints.get(definition.proximal_keypoint)
        center = keypoints.get(definition.center_keypoint)
        distal = keypoints.get(definition.distal_keypoint)
        if proximal is None or center is None or distal is None:
            continue

        angle = _angle_between_segments(proximal, center, distal)
        if angle is None:
            continue
        samples.append(
            JointAngleSample(
                frame_index=pose.frame_index,
                timestamp_sec=pose.timestamp_sec,
                joint_name=definition.name,
                angle_deg=angle,
                confidence=min(proximal.confidence, center.confidence, distal.confidence),
            )
        )
    return samples


def _summaries_from_samples(samples: list[JointAngleSample]) -> dict[str, JointAngleSummary]:
    grouped: dict[str, list[JointAngleSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.joint_name, []).append(sample)

    summaries: dict[str, JointAngleSummary] = {}
    for joint_name, joint_samples in sorted(grouped.items()):
        values = [sample.angle_deg for sample in joint_samples]
        summaries[joint_name] = JointAngleSummary(
            joint_name=joint_name,
            sample_count=len(values),
            mean_deg=sum(values) / len(values),
            min_deg=min(values),
            max_deg=max(values),
        )
    return summaries


def _angle_between_segments(
    proximal: Pose3DKeypoint,
    center: Pose3DKeypoint,
    distal: Pose3DKeypoint,
) -> float | None:
    first = (proximal.x - center.x, proximal.y - center.y, proximal.z - center.z)
    second = (distal.x - center.x, distal.y - center.y, distal.z - center.z)
    first_norm = _norm(first)
    second_norm = _norm(second)
    if first_norm <= 1e-9 or second_norm <= 1e-9:
        return None

    dot = sum(a * b for a, b in zip(first, second))
    cosine = max(-1.0, min(1.0, dot / (first_norm * second_norm)))
    return math.degrees(math.acos(cosine))


def _norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(value * value for value in vector))
