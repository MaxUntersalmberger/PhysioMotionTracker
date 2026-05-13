from __future__ import annotations

import argparse
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .config import CalibrationAppConfig
from .legacy_bridge import ensure_legacy_path
from .main_window import CalibrationMainWindow
from .project import CalibrationProjectRepository

ensure_legacy_path()

from calibration.diagnostics import evaluate_calibration_bundle  # noqa: E402
from calibration.repository import CalibrationRepository  # noqa: E402
from capture.backend import OpenCVCaptureSession, describe_capture_batch  # noqa: E402
from capture.sources import parse_sources_csv  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PhysioMotion calibratieprogramma")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke-test", action="store_true", help="Initialize the calibration program and exit.")
    mode.add_argument("--ui", action="store_true", help="Launch the calibration GUI.")
    mode.add_argument("--capture-sample", action="store_true", help="Capture one batch from the configured sources.")
    mode.add_argument("--project-summary", metavar="PATH", help="Print a calibration project manifest summary.")
    mode.add_argument("--profile-summary", metavar="PATH", help="Print a calibration profile summary.")
    parser.add_argument("--sources", default=None, help="Comma-separated sources for --capture-sample.")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = CalibrationAppConfig.load()
    _configure_logging(config)

    if args.smoke_test:
        print(f"{config.app_name}: smoke test OK")
        print(f"Root: {config.app_root}")
        print(f"Projects: {config.projects_dir}")
        print(f"Logs: {config.logs_dir}")
        return 0

    if args.ui:
        app = QApplication(argv or [])
        window = CalibrationMainWindow(config)
        window.show()
        return app.exec()

    if args.capture_sample:
        sources = parse_sources_csv(args.sources or config.default_sources_csv)
        session = OpenCVCaptureSession(sources=sources, target_fps=config.default_capture_fps, max_frame_width=0)
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

    if args.project_summary:
        try:
            project = CalibrationProjectRepository(config.projects_dir).load(Path(args.project_summary))
            print(_format_project_summary(project))
        except Exception as exc:
            print(f"Project summary failed: {exc}")
            return 1
        return 0

    if args.profile_summary:
        bundle = CalibrationRepository().load(Path(args.profile_summary))
        if bundle is None:
            print(f"Calibration profile could not be loaded: {args.profile_summary}")
            return 1
        print(_format_profile_summary(bundle, Path(args.profile_summary)))
        return 0

    print(f"{config.app_name} initialized")
    print(f"Root: {config.app_root}")
    print(f"Projects: {config.projects_dir}")
    return 0


def _configure_logging(config: CalibrationAppConfig) -> None:
    if config.logs_dir is None:
        return
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(config.logs_dir / "calibratie.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _format_project_summary(project) -> str:
    return "\n".join(
        [
            "Calibration project",
            f"Name: {project.name}",
            f"Root: {project.root_dir}",
            f"Sources: {project.sources_csv}",
            f"Target FPS: {project.target_fps:.1f}",
            f"Profile: {project.calibration_profile_path or project.default_profile_path}",
            f"Exports: {project.exports_dir}",
        ]
    )


def _format_profile_summary(bundle, path: Path) -> str:
    report = evaluate_calibration_bundle(bundle)
    solved = [source_id for source_id, camera in sorted(bundle.cameras.items()) if camera.status == "solved"]
    intrinsics = [
        source_id
        for source_id, camera in sorted(bundle.cameras.items())
        if camera.intrinsics is not None and camera.status != "solved"
    ]
    return "\n".join(
        [
            "Calibration profile",
            f"Path: {path}",
            f"Cameras: {len(bundle.cameras)}",
            f"Solved extrinsics: {', '.join(solved) if solved else 'none'}",
            f"Intrinsics-only: {', '.join(intrinsics) if intrinsics else 'none'}",
            f"Acceptance: {report.status} ({report.score:.0f}/100)",
        ]
    )
