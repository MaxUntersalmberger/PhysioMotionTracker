from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def legacy_program_root() -> Path:
    return repo_root() / "Programma Structuur"


def ensure_legacy_path() -> Path:
    legacy_root = legacy_program_root()
    legacy_text = str(legacy_root)
    if legacy_text not in sys.path:
        sys.path.insert(0, legacy_text)
    return legacy_root
