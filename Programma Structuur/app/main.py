from __future__ import annotations

import argparse
from pathlib import Path

from app.bootstrap import build_context
from app.demo import format_demo_result, run_pipeline_demo
from app.ui import run_ui
from capture.backend import OpenCVCaptureSession, describe_capture_batch
from capture.sources import parse_sources_csv
from core.logging import configure_logging
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
        help="Detector to use for reprocess-session: synthetic, mediapipe, or none.",
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
