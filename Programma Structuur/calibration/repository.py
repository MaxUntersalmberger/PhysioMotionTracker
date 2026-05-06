from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from models.types import CalibrationBundle, CameraCalibration


CALIBRATION_SCHEMA_VERSION = 2


class CalibrationRepository:
    """Reads and writes calibration profiles using a JSON schema."""

    def save(self, bundle: CalibrationBundle, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "saved_at_iso": datetime.now().isoformat(timespec="seconds"),
            "metadata": dict(bundle.metadata),
            "notes": list(bundle.notes),
            "cameras": {
                source_id: {
                    "source_id": camera.source_id,
                    "status": camera.status,
                    "num_samples": camera.num_samples,
                    "image_size": list(camera.image_size) if camera.image_size else None,
                    "intrinsics": camera.intrinsics,
                    "distortion": camera.distortion,
                    "rotation": camera.rotation,
                    "translation": camera.translation,
                    "reprojection_error_px": camera.reprojection_error_px,
                    "diagnostics": list(camera.diagnostics),
                    "calibrated_at_iso": camera.calibrated_at_iso,
                }
                for source_id, camera in bundle.cameras.items()
            },
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    def save_versioned(self, bundle: CalibrationBundle, directory: Path, setup_name: str = "default") -> Path:
        version = str(bundle.metadata.get("calibration_version") or datetime.now().strftime("%Y%m%d_%H%M%S"))
        safe_setup_name = _safe_filename(setup_name)
        path = directory / f"{safe_setup_name}_{version}.json"
        self.save(bundle, path)
        return path

    def load(self, path: Path) -> CalibrationBundle | None:
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
            return None

        cameras_payload = payload.get("cameras")
        if not isinstance(cameras_payload, dict):
            return None

        cameras: dict[str, CameraCalibration] = {}
        for source_id, camera_payload in cameras_payload.items():
            if not isinstance(camera_payload, dict):
                continue
            cameras[str(source_id)] = CameraCalibration(
                source_id=str(camera_payload.get("source_id", source_id)),
                status=str(camera_payload.get("status", "unsolved")),
                num_samples=int(camera_payload.get("num_samples", 0)),
                image_size=_parse_image_size(camera_payload.get("image_size")),
                intrinsics=_parse_matrix(camera_payload.get("intrinsics")),
                distortion=_parse_float_list(camera_payload.get("distortion")),
                rotation=_parse_float_list(camera_payload.get("rotation")),
                translation=_parse_float_list(camera_payload.get("translation")),
                reprojection_error_px=_parse_optional_float(
                    camera_payload.get("reprojection_error_px", camera_payload.get("reprojection_error"))
                ),
                diagnostics=_parse_string_list(camera_payload.get("diagnostics")),
                calibrated_at_iso=_parse_optional_str(camera_payload.get("calibrated_at_iso")),
            )

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        return CalibrationBundle(
            cameras=cameras,
            notes=_parse_string_list(payload.get("notes")),
            metadata=dict(metadata),
        )


def _parse_image_size(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        width = int(value[0])
        height = int(value[1])
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _parse_matrix(value: Any) -> list[list[float]] | None:
    if not isinstance(value, (list, tuple)):
        return None
    matrix: list[list[float]] = []
    for row in value:
        if not isinstance(row, (list, tuple)):
            return None
        try:
            matrix.append([float(item) for item in row])
        except (TypeError, ValueError):
            return None
    return matrix if matrix else None


def _parse_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _safe_filename(value: str) -> str:
    cleaned = [character if character.isalnum() or character in {"-", "_"} else "_" for character in value]
    filename = "".join(cleaned).strip("._")
    return filename or "calibration"
