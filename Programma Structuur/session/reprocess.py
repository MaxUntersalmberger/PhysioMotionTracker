from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from capture.backend import CaptureBatch
from calibration.repository import CalibrationRepository
from detectors.contracts import PoseDetector
from detectors import create_detector, normalize_detector_name
from models.types import CalibrationBundle, PipelineResult
from pipeline.manager import MocapPipeline
from session.playback import SessionPlaybackReader


@dataclass(slots=True)
class SessionReprocessReport:
    session_id: str
    batches_processed: int = 0
    frames_processed: int = 0
    reconstructed_batches: int = 0
    reconstructed_keypoints: int = 0
    reconstruction_modes: Counter[str] = field(default_factory=Counter)
    detector_name: str = ""
    calibration_loaded: bool = False
    mean_pipeline_ms: float = 0.0
    notes: list[str] = field(default_factory=list)


def reprocess_session(
    path: Path,
    detector_name: str = "synthetic",
    max_batches: int | None = None,
) -> SessionReprocessReport:
    reader = SessionPlaybackReader(path)
    manifest = reader.manifest
    detector = create_detector(normalize_detector_name(detector_name))
    pipeline = MocapPipeline(detector=detector)
    calibration = load_session_calibration(manifest.calibration_file)
    pipeline.update_calibration(calibration)

    report = SessionReprocessReport(
        session_id=manifest.session_id,
        detector_name=pipeline.detector_name,
        calibration_loaded=calibration is not None,
    )
    pipeline_times: list[float] = []

    try:
        for batch in reader.iter_batches(max_batches=max_batches):
            result = pipeline.process(batch.frames, run_detection=True)
            _update_report(report, result)
            pipeline_times.append(result.debug.pipeline_ms)
    finally:
        pipeline.shutdown()

    if pipeline_times:
        report.mean_pipeline_ms = sum(pipeline_times) / len(pipeline_times)
    if report.batches_processed == 0:
        report.notes.append("No recorded batches were processed.")
    if not report.calibration_loaded:
        report.notes.append("No calibration bundle was loaded; real calibrated 3D may be unavailable.")
    return report


def process_recorded_batch(
    batch: CaptureBatch,
    detector: PoseDetector,
    calibration: CalibrationBundle | None = None,
) -> PipelineResult:
    pipeline = MocapPipeline(detector=detector)
    pipeline.update_calibration(calibration)
    try:
        return pipeline.process(batch.frames, run_detection=True)
    finally:
        pipeline.shutdown()


def format_reprocess_report(report: SessionReprocessReport) -> str:
    lines = [
        "Session reprocess summary",
        f"Session: {report.session_id}",
        f"Detector: {report.detector_name}",
        f"Calibration loaded: {'yes' if report.calibration_loaded else 'no'}",
        f"Batches processed: {report.batches_processed}",
        f"Frames processed: {report.frames_processed}",
        f"Reconstructed batches: {report.reconstructed_batches}",
        f"Reconstructed keypoints: {report.reconstructed_keypoints}",
        f"Mean pipeline time: {report.mean_pipeline_ms:.2f} ms",
    ]
    if report.reconstruction_modes:
        modes = ", ".join(f"{mode}={count}" for mode, count in sorted(report.reconstruction_modes.items()))
        lines.append(f"Reconstruction modes: {modes}")
    if report.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in report.notes[:8])
    return "\n".join(lines)


def _update_report(report: SessionReprocessReport, result: PipelineResult) -> None:
    report.batches_processed += 1
    report.frames_processed += len(result.frames)
    report.reconstruction_modes[result.debug.reconstruction_mode] += 1
    report.reconstructed_keypoints += result.debug.reconstructed_keypoints
    if result.pose_3d is not None and result.debug.reconstructed_keypoints > 0:
        report.reconstructed_batches += 1

    for note in result.debug.notes:
        if note not in report.notes:
            report.notes.append(note)


def load_session_calibration(calibration_file: str | None) -> CalibrationBundle | None:
    if not calibration_file:
        return None
    return CalibrationRepository().load(Path(calibration_file))
