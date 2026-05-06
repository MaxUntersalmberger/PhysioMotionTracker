from __future__ import annotations

from pathlib import Path
from typing import Final

from .contracts import PoseDetector
from .mediapipe_detector import MediaPipePoseDetector
from .null_detector import NullPoseDetector
from .placeholder import SyntheticPoseDetector
from .registry import DetectorCapabilities, DetectorPluginSpec, DetectorRegistry


DEFAULT_DETECTOR_NAME: Final[str] = "mediapipe"
_REGISTRY = DetectorRegistry()
_REGISTRY.register(
    DetectorPluginSpec(
        name="mediapipe",
        label="MediaPipe",
        description="Real body pose detector",
        factory=lambda model_path: MediaPipePoseDetector(model_asset_path=model_path),
        aliases=("mediapipe_pose_detector",),
        capabilities=DetectorCapabilities(
            modalities=("body",),
            supports_multi_person=False,
            supports_confidence=True,
            notes=("Hands/face can be added as separate MediaPipe task plugins later.",),
        ),
    )
)
_REGISTRY.register(
    DetectorPluginSpec(
        name="synthetic",
        label="Synthetic demo",
        description="Deterministic demo fallback",
        factory=lambda _model_path: SyntheticPoseDetector(),
        aliases=("synthetic_demo", "synthetic_pose_detector", "demo"),
        capabilities=DetectorCapabilities(
            modalities=("body",),
            supports_multi_person=False,
            supports_confidence=True,
            notes=("Debug-only backend; not physically trustworthy.",),
        ),
    )
)
_REGISTRY.register(
    DetectorPluginSpec(
        name="none",
        label="No detector",
        description="Disable 2D detection backend",
        factory=lambda _model_path: NullPoseDetector(),
        aliases=("null", "disabled", "null_pose_detector"),
        capabilities=DetectorCapabilities(
            modalities=(),
            supports_confidence=False,
            notes=("Use for capture-only or detector benchmarking workflows.",),
        ),
    )
)

DETECTOR_CHOICES: Final[tuple[tuple[str, str, str], ...]] = _REGISTRY.choices()

_DETECTOR_ALIASES: Final[dict[str, str]] = {
    "mediapipe": "mediapipe",
    "mediapipe_pose_detector": "mediapipe",
    "synthetic": "synthetic",
    "synthetic_demo": "synthetic",
    "synthetic_pose_detector": "synthetic",
    "demo": "synthetic",
}


def normalize_detector_name(detector_name: str) -> str:
    return _REGISTRY.normalize(detector_name)


def create_detector(detector_name: str, model_asset_path: Path | None = None) -> PoseDetector:
    return _REGISTRY.create(detector_name, model_asset_path=model_asset_path)


def detector_capabilities(detector_name: str) -> DetectorCapabilities | None:
    return _REGISTRY.capabilities(detector_name)
