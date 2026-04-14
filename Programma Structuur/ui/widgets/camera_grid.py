from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from calibration import CalibrationViewDetection
from capture.backend import CaptureBatch
from models.types import CameraProbeResult, CameraSourceConfig, FramePacket


class _CameraCardWidget(QFrame):
    select_requested = Signal(str)

    def __init__(self, source: CameraSourceConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cameraCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._source_id = source.source_id
        self._title_label = QLabel()
        self._kind_label = QLabel()
        self._probe_label = QLabel()
        self._frame_label = QLabel()
        self._calibration_label = QLabel()
        self._status_label = QLabel()
        self._view_button = QPushButton("View")
        self._view_button.clicked.connect(lambda: self.select_requested.emit(self._source_id))

        self._title_label.setObjectName("cameraCardTitle")
        self._kind_label.setObjectName("cameraCardKind")
        self._probe_label.setObjectName("cameraCardProbe")
        self._frame_label.setObjectName("cameraCardFrame")
        self._calibration_label.setObjectName("cameraCardCalibration")
        self._status_label.setObjectName("cameraCardStatus")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._kind_label)
        layout.addWidget(self._probe_label)
        layout.addWidget(self._frame_label)
        layout.addWidget(self._calibration_label)
        layout.addWidget(self._status_label)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(self._view_button)
        layout.addLayout(button_row)

        self.set_source(source)
        self.set_probe_result(None)
        self.set_frame_packet(None)
        self.set_calibration_detection(None)
        self.set_selected(False)

    def source_id(self) -> str:
        return self._source_id

    def set_source(self, source: CameraSourceConfig) -> None:
        self._source_id = source.source_id
        title = source.label or source.source_id
        self._title_label.setText(f"{source.source_id} | {title}")
        self._kind_label.setText(f"Kind: {source.kind} | URI: {source.uri}")

    def set_probe_result(self, probe: CameraProbeResult | None) -> None:
        if probe is None:
            self._probe_label.setText("Probe: pending")
            self._status_label.setText("Status: waiting")
            return

        status = "opened" if probe.opened else "failed"
        self._probe_label.setText(f"Probe: {status} | backend={probe.backend} | {probe.width}x{probe.height}")
        self._status_label.setText(f"Status: {status}")

    def set_frame_packet(self, frame: FramePacket | None) -> None:
        if frame is None:
            self._frame_label.setText("Last frame: none")
            return
        self._frame_label.setText(f"Last frame: #{frame.frame_index} @ {frame.timestamp_sec:.3f}s")

    def set_calibration_detection(self, detection: CalibrationViewDetection | None) -> None:
        if detection is None:
            self._calibration_label.setText("Calib: not visible")
            return

        self._calibration_label.setText(
            f"Calib: visible | {detection.corner_count} corners | {detection.coverage_ratio:.0%} coverage"
        )

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(
                """
                QFrame#cameraCard {
                    border: 2px solid #1f6feb;
                    border-radius: 12px;
                    background: #eef5ff;
                }
                QLabel#cameraCardTitle {
                    color: #103a67;
                    font-size: 14px;
                    font-weight: 700;
                }
                QLabel#cameraCardKind,
                QLabel#cameraCardProbe,
                QLabel#cameraCardFrame,
                QLabel#cameraCardCalibration,
                QLabel#cameraCardStatus {
                    color: #27405a;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QFrame#cameraCard {
                    border: 1px solid #c9d7e4;
                    border-radius: 12px;
                    background: #fbfdff;
                }
                QLabel#cameraCardTitle {
                    color: #17324a;
                    font-size: 14px;
                    font-weight: 700;
                }
                QLabel#cameraCardKind,
                QLabel#cameraCardProbe,
                QLabel#cameraCardFrame,
                QLabel#cameraCardCalibration,
                QLabel#cameraCardStatus {
                    color: #3a4f63;
                }
                """
            )


class CameraGridWidget(QWidget):
    source_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sources: list[CameraSourceConfig] = []
        self._probe_results: dict[str, CameraProbeResult] = {}
        self._calibration_detections: dict[str, CalibrationViewDetection] = {}
        self._selected_source_id: str | None = None
        self._cards: dict[str, _CameraCardWidget] = {}
        self._last_capture_ms: float | None = None
        self._last_summary_text = ""

        self._summary_label = QLabel("No cameras configured.")
        self._summary_label.setObjectName("cameraGridSummary")

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(10)

        self._empty_label = QLabel("Probe sources to populate the camera grid.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setObjectName("cameraGridEmpty")
        self._grid_layout.addWidget(self._empty_label, 0, 0)

        group = QGroupBox("Camera Grid")
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(self._summary_label)
        group_layout.addWidget(self._grid_widget, 1)

        root = QVBoxLayout(self)
        root.addWidget(group, 1)

    def set_sources(
        self,
        sources: Sequence[CameraSourceConfig],
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        previous_selection = self._selected_source_id
        self._sources = list(sources)
        self._probe_results = dict(probe_results or {})
        self._rebuild_cards()
        if previous_selection is not None and previous_selection in self._cards:
            self.set_selected_source(previous_selection)
        else:
            self.set_selected_source(None)
        self._refresh_summary()

    def update_probe_results(self, probe_results: dict[str, CameraProbeResult]) -> None:
        self._probe_results = dict(probe_results)
        for source_id, card in self._cards.items():
            card.set_probe_result(self._probe_results.get(source_id))
        self._refresh_summary()

    def set_calibration_detections(self, detections: dict[str, CalibrationViewDetection] | None) -> None:
        self._calibration_detections = dict(detections or {})
        for source_id, card in self._cards.items():
            card.set_calibration_detection(self._calibration_detections.get(source_id))
        self._refresh_summary()

    def update_batch(
        self,
        batch: CaptureBatch,
        sources: Sequence[CameraSourceConfig] | None = None,
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        if sources is not None:
            source_ids = [source.source_id for source in sources]
            current_ids = [source.source_id for source in self._sources]
            if source_ids != current_ids:
                self.set_sources(sources, probe_results or self._probe_results)
            else:
                self._sources = list(sources)

        if probe_results is not None:
            self._probe_results = dict(probe_results)

        self._last_capture_ms = batch.capture_ms
        for source_id, card in self._cards.items():
            card.set_frame_packet(batch.frames.get(source_id))
            if source_id in self._probe_results:
                card.set_probe_result(self._probe_results[source_id])
            card.set_calibration_detection(self._calibration_detections.get(source_id))
        self._refresh_summary()

    def set_selected_source(self, source_id: str | None) -> None:
        self._selected_source_id = source_id or None
        for card in self._cards.values():
            card.set_selected(card.source_id() == self._selected_source_id)
        self._refresh_summary()

    def clear(self, message: str = "No cameras configured.") -> None:
        self._sources = []
        self._probe_results = {}
        self._calibration_detections = {}
        self._selected_source_id = None
        self._last_capture_ms = None
        self._cards.clear()
        self._last_summary_text = ""
        self._clear_layout()
        self._grid_layout.addWidget(self._empty_label, 0, 0)
        self._summary_label.setText(message)

    def _rebuild_cards(self) -> None:
        self._clear_layout()
        self._cards.clear()

        if not self._sources:
            self._grid_layout.addWidget(self._empty_label, 0, 0)
            return

        columns = 2 if len(self._sources) > 1 else 1
        for index, source in enumerate(self._sources):
            card = _CameraCardWidget(source)
            card.select_requested.connect(self._on_card_selected)
            card.set_probe_result(self._probe_results.get(source.source_id))
            card.set_frame_packet(None)
            card.set_calibration_detection(self._calibration_detections.get(source.source_id))
            card.set_selected(source.source_id == self._selected_source_id)
            self._cards[source.source_id] = card
            row = index // columns
            column = index % columns
            self._grid_layout.addWidget(card, row, column)

    def _clear_layout(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _on_card_selected(self, source_id: str) -> None:
        self.set_selected_source(source_id)
        self.source_selected.emit(source_id)

    def _refresh_summary(self) -> None:
        if not self._sources:
            if self._last_summary_text != "No cameras configured.":
                self._summary_label.setText("No cameras configured.")
                self._last_summary_text = "No cameras configured."
            return

        opened_count = sum(1 for probe in self._probe_results.values() if probe.opened)
        selected_text = self._selected_source_id or "auto"
        parts = [f"{len(self._sources)} source(s)", f"selected={selected_text}"]
        if self._probe_results:
            parts.append(f"opened={opened_count}")
        parts.append(f"calib_visible={len(self._calibration_detections)}/{len(self._sources)}")
        if self._last_capture_ms is not None:
            parts.append(f"batch={self._last_capture_ms:.2f} ms")
        summary_text = " | ".join(parts)
        if summary_text != self._last_summary_text:
            self._summary_label.setText(summary_text)
            self._last_summary_text = summary_text
