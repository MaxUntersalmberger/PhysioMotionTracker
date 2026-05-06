from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from models.types import CalibrationBundle, CameraCalibration


@dataclass(slots=True)
class CalibrationPairDiagnostic:
    first_source_id: str
    second_source_id: str
    ready: bool
    baseline_m: float | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CalibrationAcceptanceReport:
    score: float
    status: str
    pair_diagnostics: list[CalibrationPairDiagnostic] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def evaluate_calibration_bundle(bundle: CalibrationBundle) -> CalibrationAcceptanceReport:
    notes: list[str] = []
    cameras = list(bundle.cameras.values())
    if not cameras:
        return CalibrationAcceptanceReport(score=0.0, status="unavailable", notes=["No cameras in calibration bundle."])

    intrinsics_ready = [camera for camera in cameras if _has_intrinsics(camera)]
    extrinsics_ready = [camera for camera in cameras if _has_extrinsics(camera)]
    reprojection_scores = [_reprojection_score(camera) for camera in intrinsics_ready]
    sample_scores = [_sample_score(camera) for camera in intrinsics_ready]

    intrinsics_score = 100.0 * (len(intrinsics_ready) / max(1, len(cameras)))
    extrinsics_score = 100.0 * (len(extrinsics_ready) / max(1, len(cameras)))
    reprojection_score = float(np.mean(reprojection_scores)) if reprojection_scores else 0.0
    sample_score = float(np.mean(sample_scores)) if sample_scores else 0.0
    sync_samples = int(bundle.metadata.get("used_synchronized_samples", bundle.metadata.get("synchronized_samples", 0)) or 0)
    sync_score = min(100.0, sync_samples * 20.0)

    score = (
        intrinsics_score * 0.22
        + extrinsics_score * 0.28
        + reprojection_score * 0.25
        + sample_score * 0.15
        + sync_score * 0.10
    )
    pair_diagnostics = build_epipolar_pair_diagnostics(bundle)
    if not pair_diagnostics and len(cameras) >= 2:
        notes.append("No calibrated camera pairs are ready for epipolar diagnostics.")
    if len(intrinsics_ready) < len(cameras):
        notes.append("Some cameras do not have solved intrinsics.")
    if len(extrinsics_ready) < 2:
        notes.append("At least two cameras need extrinsics for trustworthy multi-view 3D.")
    if sync_samples < 4:
        notes.append("Capture more synchronized calibration samples for stronger extrinsics.")

    status = "excellent"
    if score < 85.0:
        status = "usable"
    if score < 65.0:
        status = "weak"
    if score < 40.0:
        status = "unusable"

    return CalibrationAcceptanceReport(
        score=float(max(0.0, min(100.0, score))),
        status=status,
        pair_diagnostics=pair_diagnostics,
        notes=notes,
    )


def build_epipolar_pair_diagnostics(bundle: CalibrationBundle) -> list[CalibrationPairDiagnostic]:
    diagnostics: list[CalibrationPairDiagnostic] = []
    for first_id, second_id in combinations(sorted(bundle.cameras), 2):
        first = bundle.cameras[first_id]
        second = bundle.cameras[second_id]
        notes: list[str] = []
        ready = True
        if not _has_intrinsics(first) or not _has_intrinsics(second):
            ready = False
            notes.append("Missing intrinsics.")
        if not _has_extrinsics(first) or not _has_extrinsics(second):
            ready = False
            notes.append("Missing extrinsics.")
        baseline = _baseline(first, second) if ready else None
        if baseline is not None and baseline < 0.02:
            notes.append("Very small baseline; depth accuracy may be weak.")
        if ready and not notes:
            notes.append("Camera pair ready for epipolar checks.")

        diagnostics.append(
            CalibrationPairDiagnostic(
                first_source_id=first_id,
                second_source_id=second_id,
                ready=ready,
                baseline_m=baseline,
                notes=notes,
            )
        )
    return diagnostics


def acceptance_report_to_metadata(report: CalibrationAcceptanceReport) -> dict[str, object]:
    return {
        "acceptance_score": report.score,
        "acceptance_status": report.status,
        "acceptance_notes": list(report.notes),
        "epipolar_pairs": [
            {
                "first_source_id": pair.first_source_id,
                "second_source_id": pair.second_source_id,
                "ready": pair.ready,
                "baseline_m": pair.baseline_m,
                "notes": list(pair.notes),
            }
            for pair in report.pair_diagnostics
        ],
        "bundle_adjustment_status": "not_run",
        "bundle_adjustment_notes": [
            "Non-linear bundle adjustment is not implemented yet; extrinsics currently use solvePnP plus transform averaging."
        ],
    }


def _has_intrinsics(camera: CameraCalibration) -> bool:
    if camera.intrinsics is None:
        return False
    try:
        return np.asarray(camera.intrinsics, dtype=np.float64).shape == (3, 3)
    except (TypeError, ValueError):
        return False


def _has_extrinsics(camera: CameraCalibration) -> bool:
    return _rotation_matrix(camera) is not None and _translation(camera) is not None


def _rotation_matrix(camera: CameraCalibration) -> np.ndarray | None:
    if camera.rotation is None:
        return None
    try:
        values = np.asarray(camera.rotation, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if values.size == 9:
        return values.reshape(3, 3)
    if values.size == 3:
        return values.reshape(3, 1)
    return None


def _translation(camera: CameraCalibration) -> np.ndarray | None:
    if camera.translation is None:
        return None
    try:
        values = np.asarray(camera.translation, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if values.size != 3:
        return None
    return values


def _baseline(first: CameraCalibration, second: CameraCalibration) -> float | None:
    first_translation = _translation(first)
    second_translation = _translation(second)
    if first_translation is None or second_translation is None:
        return None
    return float(np.linalg.norm(second_translation - first_translation))


def _reprojection_score(camera: CameraCalibration) -> float:
    error = camera.reprojection_error_px
    if error is None:
        return 45.0
    return float(max(0.0, min(100.0, 100.0 - (error * 20.0))))


def _sample_score(camera: CameraCalibration) -> float:
    return float(max(0.0, min(100.0, (camera.num_samples / 12.0) * 100.0)))
