from __future__ import annotations

from datetime import datetime

from capture.sources import describe_sources, parse_sources_csv
from detectors.placeholder import SyntheticPoseDetector
from models.types import CalibrationBundle, CameraCalibration, CameraSourceConfig, FramePacket, PipelineResult
from pipeline.manager import MocapPipeline
from reconstruction import PrototypeTriangulator
from tracking.matcher import SemanticKeypointMatcher
from tracking.smoother import ExponentialPoseSmoother


_DEMO_IMAGE_SIZE = (1280, 720)


def run_pipeline_demo(source_csv: str, frame_index: int = 24) -> tuple[PipelineResult, list[CameraSourceConfig]]:
    sources = parse_sources_csv(source_csv)
    frames = _build_demo_frames(sources, frame_index)

    pipeline = MocapPipeline(
        detector=SyntheticPoseDetector(),
        matcher=SemanticKeypointMatcher(),
        triangulator=PrototypeTriangulator(),
        smoother=ExponentialPoseSmoother(),
    )
    pipeline.update_calibration(_build_demo_calibration_bundle(sources))
    result = pipeline.process(frames, run_detection=True)
    return result, sources


def build_demo_calibration_bundle(sources: list[CameraSourceConfig]) -> CalibrationBundle:
    return _build_demo_calibration_bundle(sources)


def format_demo_result(result: PipelineResult, sources: list[CameraSourceConfig]) -> str:
    debug = result.debug
    lines = [
        "Demo pipeline run complete",
        f"Active sources: {debug.active_cameras}",
        f"Frame batch: {result.frame_index} @ {result.timestamp_sec:.3f}s",
        f"Detector: {debug.detector_name}",
        f"Matcher: {debug.matcher_name}",
        f"Triangulator: {debug.triangulator_name}",
        f"Reconstruction mode: {debug.reconstruction_mode}",
        f"Reconstructed joints: {debug.reconstructed_keypoints}",
        (
            f"Mean reprojection error: {debug.mean_reprojection_error_px:.3f}px"
            if debug.mean_reprojection_error_px is not None
            else "Mean reprojection error: n/a"
        ),
        f"Detection time: {debug.detection_ms:.2f} ms",
        f"Matching time: {debug.matching_ms:.2f} ms",
        f"Triangulation time: {debug.triangulation_ms:.2f} ms",
        f"Smoothing time: {debug.smoothing_ms:.2f} ms",
        f"Pipeline time: {debug.pipeline_ms:.2f} ms",
        f"Sources: {describe_sources(sources)}",
    ]
    if debug.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in debug.notes)
    return "\n".join(lines)


def _build_demo_frames(sources, frame_index: int) -> dict[str, FramePacket]:
    timestamp_sec = frame_index / 30.0
    frames: dict[str, FramePacket] = {}
    for index, source in enumerate(sources):
        frames[source.source_id] = FramePacket(
            source_id=source.source_id,
            frame_index=frame_index,
            timestamp_sec=timestamp_sec + (index * 0.001),
            frame_data={
                "source_kind": source.kind,
                "source_label": source.label,
                "demo_frame": True,
                "image_size": _DEMO_IMAGE_SIZE,
            },
        )
    return frames


def _build_demo_calibration_bundle(sources) -> CalibrationBundle:
    cameras: dict[str, CameraCalibration] = {}
    now_iso = datetime.now().isoformat(timespec="seconds")
    for index, source in enumerate(sources):
        cameras[source.source_id] = CameraCalibration(
            source_id=source.source_id,
            intrinsics=[
                [1200.0, 0.0, 640.0],
                [0.0, 1200.0, 360.0],
                [0.0, 0.0, 1.0],
            ],
            distortion=[0.0, 0.0, 0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            translation=[float(index) * 0.15, 0.0, 0.0],
            image_size=_DEMO_IMAGE_SIZE,
            reprojection_error_px=0.0,
            num_samples=12,
            status="solved",
            calibrated_at_iso=now_iso,
        )
    return CalibrationBundle(
        cameras=cameras,
        notes=["Demo calibration bundle generated at startup."],
        metadata={"mode": "demo"},
    )


