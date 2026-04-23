from __future__ import annotations

from pathlib import Path

from models.types import CameraSourceConfig


_VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".m4v", ".webm"}


def parse_sources_csv(raw_csv: str, max_sources: int = 4) -> list[CameraSourceConfig]:
    raw_csv = raw_csv.strip()
    if not raw_csv:
        raise ValueError("Camera sources CSV is empty.")

    tokens = [token.strip() for token in raw_csv.split(",") if token.strip()]
    if not tokens:
        raise ValueError("No camera sources were parsed.")
    if len(tokens) > max_sources:
        raise ValueError(f"Use up to {max_sources} sources.")

    sources: list[CameraSourceConfig] = []
    for index, token in enumerate(tokens):
        if _looks_like_integer(token):
            camera_index = int(token)
            sources.append(
                CameraSourceConfig(
                    source_id=f"cam{index}",
                    kind="webcam",
                    uri=camera_index,
                    label=f"Webcam {camera_index}",
                )
            )
            continue

        path = Path(token)
        source_kind = "video" if path.suffix.lower() in _VIDEO_SUFFIXES else "file"
        sources.append(
            CameraSourceConfig(
                source_id=f"cam{index}",
                kind=source_kind,
                uri=token,
                label=path.name or token,
            )
        )

    return sources


def describe_sources(sources: list[CameraSourceConfig]) -> str:
    parts: list[str] = []
    for source in sources:
        if source.kind == "webcam":
            descriptor = f"webcam:{source.uri}"
        else:
            descriptor = f"{source.kind}:{source.uri}"
        parts.append(f"{source.source_id}={descriptor}")
    return ", ".join(parts) if parts else "none"


def _looks_like_integer(token: str) -> bool:
    if token.startswith("-"):
        return token[1:].isdigit()
    return token.isdigit()
