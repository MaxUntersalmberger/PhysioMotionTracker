from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .contracts import PoseDetector


DetectorFactory = Callable[[Path | None], PoseDetector]


@dataclass(frozen=True, slots=True)
class DetectorCapabilities:
    modalities: tuple[str, ...] = ("body",)
    supports_multi_person: bool = False
    supports_confidence: bool = True
    supports_occlusion_reporting: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DetectorPluginSpec:
    name: str
    label: str
    description: str
    factory: DetectorFactory
    aliases: tuple[str, ...] = ()
    capabilities: DetectorCapabilities = field(default_factory=DetectorCapabilities)


class DetectorRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, DetectorPluginSpec] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: DetectorPluginSpec) -> None:
        normalized_name = normalize_detector_name(spec.name)
        self._plugins[normalized_name] = spec
        self._aliases[normalized_name] = normalized_name
        for alias in spec.aliases:
            self._aliases[normalize_detector_name(alias)] = normalized_name

    def normalize(self, detector_name: str) -> str:
        normalized = normalize_detector_name(detector_name)
        return self._aliases.get(normalized, normalized)

    def create(self, detector_name: str, model_asset_path: Path | None = None) -> PoseDetector:
        normalized = self.normalize(detector_name)
        spec = self._plugins.get(normalized)
        if spec is None:
            raise ValueError(f"Unknown detector '{detector_name}'.")
        return spec.factory(model_asset_path)

    def choices(self) -> tuple[tuple[str, str, str], ...]:
        return tuple((name, spec.label, spec.description) for name, spec in self._plugins.items())

    def capabilities(self, detector_name: str) -> DetectorCapabilities | None:
        spec = self._plugins.get(self.normalize(detector_name))
        return spec.capabilities if spec is not None else None


def normalize_detector_name(detector_name: str) -> str:
    return detector_name.strip().lower().replace(" ", "_").replace("-", "_")
