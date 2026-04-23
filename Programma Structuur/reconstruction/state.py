from __future__ import annotations

from dataclasses import dataclass

from models.types import CalibrationBundle, PipelineResult


@dataclass(slots=True)
class ReconstructionState:
    detector_name: str = "placeholder_pose"
    matcher_name: str = "semantic_name_matcher"
    triangulator_name: str = "calibrated_multiview_triangulator"
    trust_state: str = "unavailable"
    calibration_bundle: CalibrationBundle | None = None
    latest_result: PipelineResult | None = None
