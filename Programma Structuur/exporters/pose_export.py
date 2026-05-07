from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from calibration.repository import CalibrationRepository
from detectors import create_detector, normalize_detector_name
from models.types import CalibrationBundle, PipelineResult, Pose2D, Pose3D
from pipeline.manager import MocapPipeline
from session.playback import SessionPlaybackReader


SUPPORTED_POSE_EXPORT_FORMATS = {"json", "csv"}


@dataclass(slots=True)
class PoseExportReport:
    session_id: str
    output_dir: Path
    detector_name: str
    calibration_loaded: bool
    formats: list[str]
    batches_processed: int = 0
    frames_processed: int = 0
    pose2d_rows: int = 0
    pose3d_rows: int = 0
    reconstruction_modes: Counter[str] = field(default_factory=Counter)
    output_files: dict[str, Path] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def export_session_poses(
    path: Path,
    detector_name: str = "synthetic",
    output_dir: Path | None = None,
    formats: Iterable[str] | None = None,
    max_batches: int | None = None,
) -> PoseExportReport:
    reader = SessionPlaybackReader(path)
    manifest = reader.manifest
    selected_formats = _normalize_formats(formats)
    resolved_output_dir = output_dir or (reader.session_dir / "exports")
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    detector = create_detector(normalize_detector_name(detector_name))
    pipeline = MocapPipeline(detector=detector)
    calibration = _load_calibration(manifest.calibration_file, reader.session_dir)
    pipeline.update_calibration(calibration)

    report = PoseExportReport(
        session_id=manifest.session_id,
        output_dir=resolved_output_dir,
        detector_name=pipeline.detector_name,
        calibration_loaded=calibration is not None,
        formats=selected_formats,
    )
    json_batches: list[dict[str, Any]] = []
    pose2d_rows: list[dict[str, object]] = []
    pose3d_rows: list[dict[str, object]] = []

    try:
        for batch_number, batch in enumerate(reader.iter_batches(max_batches=max_batches), start=1):
            result = pipeline.process(batch.frames, run_detection=True)
            report.batches_processed += 1
            report.frames_processed += len(result.frames)
            report.reconstruction_modes[result.debug.reconstruction_mode] += 1

            if "json" in selected_formats:
                json_batches.append(_result_to_json_batch(batch_number, result))
            if "csv" in selected_formats:
                new_pose2d_rows = _pose2d_csv_rows(manifest.session_id, batch_number, result)
                new_pose3d_rows = _pose3d_csv_rows(manifest.session_id, batch_number, result)
                pose2d_rows.extend(new_pose2d_rows)
                pose3d_rows.extend(new_pose3d_rows)
                report.pose2d_rows += len(new_pose2d_rows)
                report.pose3d_rows += len(new_pose3d_rows)

            for note in result.debug.notes:
                if note not in report.notes:
                    report.notes.append(note)
    finally:
        pipeline.shutdown()

    if report.batches_processed == 0:
        report.notes.append("No recorded batches were exported.")
    if not report.calibration_loaded:
        report.notes.append("No calibration bundle was loaded; exported 3D may be unavailable.")

    if "json" in selected_formats:
        path = resolved_output_dir / "pose_export.json"
        path.write_text(
            json.dumps(_json_payload(report, json_batches), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        report.output_files["json"] = path

    if "csv" in selected_formats:
        pose2d_path = resolved_output_dir / "pose_2d.csv"
        pose3d_path = resolved_output_dir / "pose_3d.csv"
        _write_csv(pose2d_path, _POSE2D_FIELDNAMES, pose2d_rows)
        _write_csv(pose3d_path, _POSE3D_FIELDNAMES, pose3d_rows)
        report.output_files["pose_2d_csv"] = pose2d_path
        report.output_files["pose_3d_csv"] = pose3d_path

    manifest_path = resolved_output_dir / "export_manifest.json"
    manifest_path.write_text(
        json.dumps(_export_manifest(report), indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    report.output_files["manifest"] = manifest_path
    return report


def format_pose_export_report(report: PoseExportReport) -> str:
    lines = [
        "Pose export summary",
        f"Session: {report.session_id}",
        f"Output directory: {report.output_dir}",
        f"Detector: {report.detector_name}",
        f"Calibration loaded: {'yes' if report.calibration_loaded else 'no'}",
        f"Formats: {', '.join(report.formats)}",
        f"Batches exported: {report.batches_processed}",
        f"Frames processed: {report.frames_processed}",
        f"2D rows: {report.pose2d_rows}",
        f"3D rows: {report.pose3d_rows}",
    ]
    if report.reconstruction_modes:
        modes = ", ".join(f"{mode}={count}" for mode, count in sorted(report.reconstruction_modes.items()))
        lines.append(f"Reconstruction modes: {modes}")
    if report.output_files:
        lines.append("Files:")
        lines.extend(f"- {label}: {path}" for label, path in sorted(report.output_files.items()))
    if report.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in report.notes[:8])
    return "\n".join(lines)


_POSE2D_FIELDNAMES = [
    "session_id",
    "batch_index",
    "frame_index",
    "timestamp_sec",
    "source_id",
    "keypoint",
    "x_norm",
    "y_norm",
    "confidence",
]
_POSE3D_FIELDNAMES = [
    "session_id",
    "batch_index",
    "frame_index",
    "timestamp_sec",
    "keypoint",
    "x",
    "y",
    "z",
    "confidence",
    "reconstruction_mode",
]


def _normalize_formats(formats: Iterable[str] | None) -> list[str]:
    values = list(formats or ("json", "csv"))
    normalized = sorted({value.strip().lower() for value in values if value.strip()})
    if not normalized:
        raise ValueError("At least one export format is required.")
    unsupported = [value for value in normalized if value not in SUPPORTED_POSE_EXPORT_FORMATS]
    if unsupported:
        raise ValueError("Unsupported pose export format(s): " + ", ".join(unsupported))
    return normalized


def _load_calibration(calibration_file: str | None, session_dir: Path) -> CalibrationBundle | None:
    if not calibration_file:
        return None
    path = Path(calibration_file)
    if not path.is_absolute():
        path = session_dir / path
    return CalibrationRepository().load(path)


def _result_to_json_batch(batch_index: int, result: PipelineResult) -> dict[str, Any]:
    return {
        "batch_index": batch_index,
        "frame_index": result.frame_index,
        "timestamp_sec": result.timestamp_sec,
        "source_frame_indices": {
            source_id: frame.frame_index for source_id, frame in sorted(result.frames.items())
        },
        "poses_2d": {
            source_id: _pose2d_to_dict(pose) for source_id, pose in sorted(result.poses_2d.items())
        },
        "pose_3d": _pose3d_to_dict(result.pose_3d),
        "debug": {
            "detector_name": result.debug.detector_name,
            "matcher_name": result.debug.matcher_name,
            "triangulator_name": result.debug.triangulator_name,
            "reconstruction_mode": result.debug.reconstruction_mode,
            "reconstructed_keypoints": result.debug.reconstructed_keypoints,
            "mean_reprojection_error_px": result.debug.mean_reprojection_error_px,
            "pipeline_ms": result.debug.pipeline_ms,
            "notes": list(result.debug.notes),
        },
    }


def _pose2d_to_dict(pose: Pose2D) -> dict[str, Any]:
    return {
        "source_id": pose.source_id,
        "frame_index": pose.frame_index,
        "timestamp_sec": pose.timestamp_sec,
        "keypoints": [
            {
                "name": keypoint.name,
                "x": keypoint.x,
                "y": keypoint.y,
                "confidence": keypoint.confidence,
            }
            for keypoint in pose.keypoints
        ],
    }


def _pose3d_to_dict(pose: Pose3D | None) -> dict[str, Any] | None:
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


def _pose2d_csv_rows(session_id: str, batch_index: int, result: PipelineResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source_id, pose in sorted(result.poses_2d.items()):
        for keypoint in pose.keypoints:
            rows.append(
                {
                    "session_id": session_id,
                    "batch_index": batch_index,
                    "frame_index": pose.frame_index,
                    "timestamp_sec": pose.timestamp_sec,
                    "source_id": source_id,
                    "keypoint": keypoint.name,
                    "x_norm": keypoint.x,
                    "y_norm": keypoint.y,
                    "confidence": keypoint.confidence,
                }
            )
    return rows


def _pose3d_csv_rows(session_id: str, batch_index: int, result: PipelineResult) -> list[dict[str, object]]:
    if result.pose_3d is None:
        return []

    return [
        {
            "session_id": session_id,
            "batch_index": batch_index,
            "frame_index": result.pose_3d.frame_index,
            "timestamp_sec": result.pose_3d.timestamp_sec,
            "keypoint": keypoint.name,
            "x": keypoint.x,
            "y": keypoint.y,
            "z": keypoint.z,
            "confidence": keypoint.confidence,
            "reconstruction_mode": result.debug.reconstruction_mode,
        }
        for keypoint in result.pose_3d.keypoints
    ]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _json_payload(report: PoseExportReport, batches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "exported_at_iso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": report.session_id,
        "detector_name": report.detector_name,
        "calibration_loaded": report.calibration_loaded,
        "batches_processed": report.batches_processed,
        "frames_processed": report.frames_processed,
        "reconstruction_modes": dict(report.reconstruction_modes),
        "batches": batches,
    }


def _export_manifest(report: PoseExportReport) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "exported_at_iso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": report.session_id,
        "detector_name": report.detector_name,
        "calibration_loaded": report.calibration_loaded,
        "formats": list(report.formats),
        "batches_processed": report.batches_processed,
        "frames_processed": report.frames_processed,
        "pose2d_rows": report.pose2d_rows,
        "pose3d_rows": report.pose3d_rows,
        "reconstruction_modes": dict(report.reconstruction_modes),
        "output_files": {label: str(path) for label, path in sorted(report.output_files.items())},
        "notes": list(report.notes),
    }
