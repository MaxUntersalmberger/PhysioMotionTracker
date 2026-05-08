"""Standalone calibration-only application."""

from .legacy_bridge import ensure_legacy_path

ensure_legacy_path()

__all__ = ["ensure_legacy_path"]
