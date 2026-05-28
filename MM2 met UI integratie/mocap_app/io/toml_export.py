from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from typing import Any

from mocap_app.models.types import CalibrationBundle


_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def calibration_bundle_to_toml(bundle: CalibrationBundle) -> str:
    """Serialize a calibration bundle to a readable TOML document."""
    lines: list[str] = []
    metadata = dict(bundle.metadata)
    metadata.setdefault("app", "PhysioMotionTracker")

    _append_mapping(lines, ["metadata"], metadata)
    if lines and lines[-1] != "":
        lines.append("")

    if bundle.notes:
        lines.append("[notes]")
        lines.append("items = " + _format_value(bundle.notes))
        lines.append("")

    for source_id, camera in bundle.cameras.items():
        lines.append(_table_header(["camera", source_id]))
        camera_data = asdict(camera)
        camera_data.pop("source_id", None)
        for key, value in camera_data.items():
            if value is None or value == []:
                continue
            lines.append(f"{_format_key(key)} = {_format_value(value)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _append_mapping(lines: list[str], path: list[str], mapping: dict[str, Any]) -> None:
    scalar_items: list[tuple[str, Any]] = []
    nested_items: list[tuple[str, dict[str, Any]]] = []

    for key, value in mapping.items():
        if value is None:
            continue
        if isinstance(value, dict):
            nested_items.append((str(key), value))
        else:
            scalar_items.append((str(key), value))

    if scalar_items:
        lines.append(_table_header(path))
        for key, value in scalar_items:
            lines.append(f"{_format_key(key)} = {_format_value(value)}")
        lines.append("")

    for key, value in nested_items:
        _append_mapping(lines, [*path, key], value)


def _table_header(path: list[str]) -> str:
    return "[" + ".".join(_format_key(part) for part in path) + "]"


def _format_key(key: str) -> str:
    return key if _BARE_KEY_RE.match(key) else json.dumps(key)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return f"{value:.10g}"
        return json.dumps(str(value))
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    return json.dumps(str(value))
