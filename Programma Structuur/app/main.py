from __future__ import annotations

import argparse
from pathlib import Path

from app.bootstrap import build_context
from app.demo import format_demo_result, run_pipeline_demo
from app.ui import run_ui
from biomechanics import JointAngleRepository, analyze_motion_take_joint_angles, format_joint_angle_report
from capture.backend import OpenCVCaptureSession, describe_capture_batch
from capture.sources import parse_sources_csv
from core.logging import configure_logging
from exporters import export_session_poses, format_pose_export_report
from motion import MotionTakeRepository, format_motion_take_report, process_session_to_motion_take
from session import format_reprocess_report, reprocess_session, summarize_session_playback


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Programma Structuur motion capture app")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--smoke-test",
        action="store_true",
        help="Initialize the runtime, print the configured paths, and exit.",
    )
    mode.add_argument(
        "--demo-pipeline",
        action="store_true",
        help="Run a synthetic end-to-end capture, detection, and reconstruction demo.",
    )
    mode.add_argument(
        "--capture-sample",
        action="store_true",
        help="Open the configured sources with OpenCV and capture one real batch.",
    )
    mode.add_argument(
        "--ui",
        action="store_true",
        help="Launch the Qt shell and connect the capture/pipeline workers.",
    )
    mode.add_argument(
        "--session-summary",
        metavar="PATH",
        help="Load a recorded session manifest/directory and print playback diagnostics.",
    )
    mode.add_argument(
        "--reprocess-session",
        metavar="PATH",
        help="Replay a recorded session through the mocap pipeline and print diagnostics.",
    )
    mode.add_argument(
        "--process-session",
        metavar="PATH",
        help="Replay a recorded session and save an internal processed motion take.",
    )
    mode.add_argument(
        "--analyze-take",
        metavar="PATH",
        help="Analyze an internal processed motion take and save joint-angle results.",
    )
    mode.add_argument(
        "--export-session",
        metavar="PATH",
        help="Replay a recorded session and export 2D/3D pose data.",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="Comma-separated sources for the demo or capture sample. Defaults to the app setting.",
    )
    parser.add_argument(
        "--frame-index",
        type=int,
        default=24,
        help="Synthetic frame index to use for the demo pipeline.",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=3,
        help="Maximum recorded batches to preview/process for session commands. Use 0 for all.",
    )
    parser.add_argument(
        "--detector",
        default="synthetic",
        help="Detector to use for reprocess/process/export commands: synthetic, mediapipe, or none.",
    )
    parser.add_argument(
        "--export-formats",
        default="json,csv",
        help="Comma-separated export formats for --export-session. Supported: json,csv.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for session processing/export commands.",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    context = build_context()
    log_path = configure_logging(context.config.logs_dir)

    if args.smoke_test:
        print(f"{context.config.app_name}: smoke test OK")
        print(f"Logs: {log_path}")
        print(f"Root: {context.config.app_root}")
        return 0

    if args.demo_pipeline:
        source_csv = args.sources or "0,1"
        result, sources = run_pipeline_demo(source_csv, frame_index=max(0, int(args.frame_index)))
        print(format_demo_result(result, sources))
        return 0

    if args.capture_sample:
        source_csv = args.sources or context.config.default_sources_csv
        sources = parse_sources_csv(source_csv)
        session = OpenCVCaptureSession(
            sources=sources,
            target_fps=context.config.default_capture_fps,
            max_frame_width=1280,
        )
        try:
            session.open()
            batch = session.read_batch()
            print(describe_capture_batch(batch, sources))
        except Exception as exc:
            print(f"Capture sample failed: {exc}")
            return 1
        finally:
            session.close()
        return 0

    if args.ui:
        return run_ui(context.config, argv=argv)

    if args.session_summary:
        try:
            print(summarize_session_playback(Path(args.session_summary), max_batches=_batch_limit(args.max_batches)))
        except Exception as exc:
            print(f"Session summary failed: {exc}")
            return 1
        return 0

    if args.reprocess_session:
        try:
            report = reprocess_session(
                Path(args.reprocess_session),
                detector_name=args.detector,
                max_batches=_batch_limit(args.max_batches),
            )
            print(format_reprocess_report(report))
        except Exception as exc:
            print(f"Session reprocess failed: {exc}")
            return 1
        return 0

    if args.process_session:
        try:
            output_path = None
            if args.output_dir:
                output_path = Path(args.output_dir) / "motion_take.json"
            report = process_session_to_motion_take(
                Path(args.process_session),
                detector_name=args.detector,
                output_path=output_path,
                max_batches=_batch_limit(args.max_batches),
            )
            print(format_motion_take_report(report))
        except Exception as exc:
            print(f"Session processing failed: {exc}")
            return 1
        return 0

    if args.analyze_take:
        try:
            take_path = Path(args.analyze_take)
            take = MotionTakeRepository().load(take_path)
            output_path = Path(args.output_dir) / "joint_angles.json" if args.output_dir else None
            report = analyze_motion_take_joint_angles(
                take,
                source_take_path=take_path,
                output_path=output_path or JointAngleRepository().default_path(take_path),
            )
            print(format_joint_angle_report(report))
        except Exception as exc:
            print(f"Motion take analysis failed: {exc}")
            return 1
        return 0

    if args.export_session:
        try:
            report = export_session_poses(
                Path(args.export_session),
                detector_name=args.detector,
                output_dir=Path(args.output_dir) if args.output_dir else None,
                formats=_parse_export_formats(args.export_formats),
                max_batches=_batch_limit(args.max_batches),
            )
            print(format_pose_export_report(report))
        except Exception as exc:
            print(f"Session export failed: {exc}")
            return 1
        return 0

    print(f"{context.config.app_name} initialized")
    print(f"Root: {context.config.app_root}")
    print(f"Sessions: {context.config.sessions_dir}")
    print(f"Calibration: {context.config.calibration_dir}")
    print(f"Logs: {log_path}")
    return 0


def _batch_limit(value: int) -> int | None:
    limit = int(value)
    if limit <= 0:
        return None
    return limit


def _parse_export_formats(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
