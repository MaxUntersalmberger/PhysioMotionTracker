from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from calibration.repository import CalibrationRepository
from detectors import create_detector, normalize_detector_name
from models.types import CalibrationBundle, PipelineResult
from pipeline.manager import MocapPipeline
from session.playback import SessionPlaybackReader

from .take import (
    MOTION_TAKE_SCHEMA_VERSION,
    MotionTake,
    MotionTakeFrame,
    MotionTakeRepository,
    build_motion_take_summary,
)


@dataclass(slots=True)
class MotionTakeReport:
    take: MotionTake
    output_path: Path
    batches_processed: int
    calibration_loaded: bool
    notes: list[str] = field(default_factory=list)


def process_session_to_motion_take(
    path: Path,
    detector_name: str = "synthetic",
    output_path: Path | None = None,
    max_batches: int | None = None,
    repository: MotionTakeRepository | None = None,
) -> MotionTakeReport:
    reader = SessionPlaybackReader(path)
    manifest = reader.manifest
    detector = create_detector(normalize_detector_name(detector_name))
    pipeline = MocapPipeline(detector=detector)
    calibration = _load_calibration(manifest.calibration_file, reader.session_dir)
    pipeline.update_calibration(calibration)

    frames: list[MotionTakeFrame] = []
    notes: list[str] = []
    try:
        for batch_number, batch in enumerate(reader.iter_batches(max_batches=max_batches), start=1):
            result = pipeline.process(batch.frames, run_detection=True)
            frames.append(_frame_from_pipeline_result(batch_number, result))
            for note in result.debug.notes:
                if note not in notes:
                    notes.append(note)
    finally:
        pipeline.shutdown()

    if not frames:
        notes.append("No recorded batches were processed into a motion take.")
    if calibration is None:
        notes.append("No calibration bundle was loaded; the take may contain only 2D pose data.")

    take = MotionTake(
        schema_version=MOTION_TAKE_SCHEMA_VERSION,
        take_id=f"{manifest.session_id}_take",
        session_id=manifest.session_id,
        created_at_iso=datetime.now().astimezone().isoformat(timespec="seconds"),
        source_session_dir=str(reader.session_dir),
        detector_name=pipeline.detector_name,
        calibration_loaded=calibration is not None,
        calibration_file=manifest.calibration_file,
        stages=_stage_statuses(pipeline, calibration is not None),
        summary=build_motion_take_summary(frames, source_count=len(manifest.sources)),
        frames=frames,
        metadata={
            "source_fps": manifest.fps,
            "source_total_frames": manifest.total_frames,
            "source_count": len(manifest.sources),
        },
    )

    take_repository = repository or MotionTakeRepository()
    resolved_output_path = output_path or take_repository.default_path(reader.session_dir)
    take_repository.save(take, resolved_output_path)
    return MotionTakeReport(
        take=take,
        output_path=resolved_output_path,
        batches_processed=len(frames),
        calibration_loaded=calibration is not None,
        notes=notes,
    )


def format_motion_take_report(report: MotionTakeReport) -> str:
    take = report.take
    modes = ", ".join(
        f"{mode}={count}" for mode, count in sorted(take.summary.reconstruction_modes.items())
    )
    lines = [
        "Motion take summary",
        f"Session: {take.session_id}",
        f"Take file: {report.output_path}",
        f"Detector: {take.detector_name}",
        f"Calibration loaded: {'yes' if take.calibration_loaded else 'no'}",
        f"Frames processed: {take.summary.frame_count}",
        f"2D pose frames: {take.summary.pose2d_frames}",
        f"3D pose frames: {take.summary.pose3d_frames}",
        f"2D keypoints: {take.summary.pose2d_keypoints}",
        f"3D keypoints: {take.summary.pose3d_keypoints}",
    ]
    if modes:
        lines.append(f"Reconstruction modes: {modes}")
    lines.append("Pipeline stages:")
    lines.extend(f"- {name}: {status}" for name, status in take.stages.items())
    if report.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in report.notes[:8])
    return "\n".join(lines)


def _frame_from_pipeline_result(batch_index: int, result: PipelineResult) -> MotionTakeFrame:
    return MotionTakeFrame(
        batch_index=batch_index,
        frame_index=result.frame_index,
        timestamp_sec=result.timestamp_sec,
        poses_2d=dict(result.poses_2d),
        pose_3d=result.pose_3d,
        reconstruction_mode=result.debug.reconstruction_mode,
        reconstruction_trust_score=result.debug.reconstruction_trust_score,
        reconstruction_trust_state=result.debug.reconstruction_trust_state,
        mean_reprojection_error_px=result.debug.mean_reprojection_error_px,
        per_joint_reprojection_error_px=dict(result.debug.per_joint_reprojection_error_px),
        per_joint_view_count=dict(result.debug.per_joint_view_count),
        per_joint_confidence=dict(result.debug.per_joint_confidence),
        notes=list(result.debug.notes),
    )


def _stage_statuses(pipeline: MocapPipeline, calibration_loaded: bool) -> dict[str, str]:
    return {
        "camera_capture": "recorded_session",
        "calibration": "loaded" if calibration_loaded else "missing",
        "pose_2d": pipeline.detector_name,
        "tracking": pipeline.matcher_name,
        "triangulation": pipeline.triangulator_name,
        "filtering": "exponential_pose_smoothing",
        "inverse_kinematics": "pending",
        "joint_angles": "pending",
    }


def _load_calibration(calibration_file: str | None, session_dir: Path) -> CalibrationBundle | None:
    if not calibration_file:
        return None
    path = Path(calibration_file)
    if not path.is_absolute():
        path = session_dir / path
    return CalibrationRepository().load(path)
