"""Detector implementations for the mocap pipeline."""

from .factory import DEFAULT_DETECTOR_NAME, DETECTOR_CHOICES, create_detector, normalize_detector_name
from .contracts import PoseDetector
from .mediapipe_detector import MediaPipePoseDetector
from .placeholder import SyntheticPoseDetector

__all__ = [
	"DEFAULT_DETECTOR_NAME",
	"DETECTOR_CHOICES",
	"MediaPipePoseDetector",
	"PoseDetector",
	"SyntheticPoseDetector",
	"create_detector",
	"normalize_detector_name",
]
