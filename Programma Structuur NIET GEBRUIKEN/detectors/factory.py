from __future__ import annotations

from pathlib import Path
from typing import Final

from .contracts import PoseDetector
from .mediapipe_detector import MediaPipePoseDetector
from .placeholder import SyntheticPoseDetector


DEFAULT_DETECTOR_NAME: Final[str] = "mediapipe"
DETECTOR_CHOICES: Final[tuple[tuple[str, str, str], ...]] = (
    ("mediapipe", "MediaPipe", "Real 2D pose detector"),
    ("synthetic", "Synthetic demo", "Deterministic demo fallback"),
)

_DETECTOR_ALIASES: Final[dict[str, str]] = {
    "mediapipe": "mediapipe",
    "mediapipe_pose_detector": "mediapipe",
    "synthetic": "synthetic",
    "synthetic_demo": "synthetic",
    "synthetic_pose_detector": "synthetic",
    "demo": "synthetic",
}


def normalize_detector_name(detector_name: str) -> str:
    normalized = detector_name.strip().lower().replace(" ", "_")
    return _DETECTOR_ALIASES.get(normalized, normalized)


def create_detector(detector_name: str, model_asset_path: Path | None = None) -> PoseDetector:
    normalized = normalize_detector_name(detector_name)
    if normalized == "mediapipe":
        return MediaPipePoseDetector(model_asset_path=model_asset_path)
    if normalized == "synthetic":
        return SyntheticPoseDetector()
    raise ValueError(f"Unknown detector '{detector_name}'.")
