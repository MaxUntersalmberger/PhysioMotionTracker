"""Detector implementations for the mocap pipeline."""

from .factory import DEFAULT_DETECTOR_NAME, DETECTOR_CHOICES, create_detector, detector_capabilities, normalize_detector_name
from .contracts import PoseDetector
from .mediapipe_detector import MediaPipePoseDetector
from .null_detector import NullPoseDetector
from .policies import ConfidencePolicy, PoseQualityReport, apply_confidence_policy
from .placeholder import SyntheticPoseDetector
from .registry import DetectorCapabilities, DetectorPluginSpec, DetectorRegistry

__all__ = [
	"DEFAULT_DETECTOR_NAME",
	"DETECTOR_CHOICES",
	"MediaPipePoseDetector",
	"NullPoseDetector",
	"PoseDetector",
	"ConfidencePolicy",
	"DetectorCapabilities",
	"DetectorPluginSpec",
	"DetectorRegistry",
	"PoseQualityReport",
	"SyntheticPoseDetector",
	"apply_confidence_policy",
	"create_detector",
	"detector_capabilities",
	"normalize_detector_name",
]
