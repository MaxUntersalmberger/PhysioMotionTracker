from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QGroupBox, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .legacy_bridge import ensure_legacy_path

ensure_legacy_path()

from calibration import CalibrationCameraQuality, CalibrationViewDetection  # noqa: E402
from capture.backend import CaptureBatch  # noqa: E402
from models.types import CameraProbeResult, CameraSourceConfig, FramePacket  # noqa: E402


class _PreviewTileWidget(QFrame):
    selected = Signal(str)

    def __init__(self, source: CameraSourceConfig, minimum_image_size: tuple[int, int]) -> None:
        super().__init__()
        self.setObjectName("previewTile")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._source = source
        self._frame: FramePacket | None = None
        self._probe: CameraProbeResult | None = None
        self._detection: CalibrationViewDetection | None = None
        self._quality: CalibrationCameraQuality | None = None
        self._sample_count = 0
        self._sync_sample_count = 0
        self._requested_resolution: tuple[int, int] = (0, 0)
        self._requested_resolution_label = "Auto"
        self._current_pixmap: QPixmap | None = None

        self._title_label = QLabel()
        self._title_label.setObjectName("previewTileTitle")
        self._status_label = QLabel("Waiting for capture frames...")
        self._status_label.setObjectName("previewTileStatus")
        self._status_label.setWordWrap(True)

        self._image_label = QLabel("No frame yet")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(int(minimum_image_size[0]), int(minimum_image_size[1]))
        self._image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image_label.setObjectName("previewTileImage")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._image_label, 1)
        layout.addWidget(self._status_label)

        self.set_source(source)
        self.set_selected(False)

    def source_id(self) -> str:
        return self._source.source_id

    def set_source(self, source: CameraSourceConfig) -> None:
        self._source = source
        label = source.label or source.source_id
        self._title_label.setText(f"{source.source_id} | {label}")

    def set_frame(self, frame: FramePacket | None, probe: CameraProbeResult | None) -> None:
        self._frame = frame
        self._probe = probe
        if frame is None:
            self._current_pixmap = None
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText("No frame yet")
            self._status_label.setText(self._format_status(None, probe))
            return

        pixmap = self._frame_to_pixmap(frame.frame_data)
        if pixmap is None:
            self._current_pixmap = None
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText("Unsupported frame")
            self._status_label.setText(self._format_status(frame, probe))
            return

        self._current_pixmap = pixmap
        self._status_label.setText(self._format_status(frame, probe))
        self._refresh_pixmap()

    def set_calibration_detection(self, detection: CalibrationViewDetection | None) -> None:
        self._detection = detection
        self.set_frame(self._frame, self._probe)

    def set_quality(self, quality: CalibrationCameraQuality | None) -> None:
        self._quality = quality
        self._status_label.setText(self._format_status(self._frame, self._probe))
        self._apply_style()
        self._refresh_pixmap()

    def set_sample_status(self, sample_count: int, sync_sample_count: int) -> None:
        self._sample_count = max(0, int(sample_count))
        self._sync_sample_count = max(0, int(sync_sample_count))
        self._status_label.setText(self._format_status(self._frame, self._probe))
        self._refresh_pixmap()

    def set_requested_resolution(self, width: int, height: int, label: str = "Auto") -> None:
        self._requested_resolution = max(0, int(width)), max(0, int(height))
        self._requested_resolution_label = label.strip() or "Auto"
        self._status_label.setText(self._format_status(self._frame, self._probe))
        self._refresh_pixmap()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def _apply_style(self) -> None:
        if getattr(self, "_selected", False):
            border = "2px solid #1f6feb"
            background = "#eef5ff"
        elif self._quality is not None and self._quality.visible:
            border = "2px solid #16a34a" if self._quality.score >= 70.0 else "2px solid #f59e0b"
            background = "#f7fff8" if self._quality.score >= 70.0 else "#fff9ec"
        else:
            border = "1px solid #c9d7e4"
            background = "#fbfdff"
        self.setStyleSheet(
            f"""
            QFrame#previewTile {{
                border: {border};
                border-radius: 8px;
                background: {background};
            }}
            QLabel#previewTileTitle {{
                color: #17324a;
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#previewTileStatus {{
                color: #3a4f63;
                font-size: 12px;
            }}
            QLabel#previewTileImage {{
                border: 1px solid #d5e0ea;
                border-radius: 6px;
                background: #111827;
                color: #dbeafe;
            }}
            """
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._source.source_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _format_status(self, frame: FramePacket | None, probe: CameraProbeResult | None) -> str:
        bits: list[str] = []
        if frame is None:
            bits.append("Waiting")
        else:
            bits.append(f"Frame #{frame.frame_index}")
            bits.append(f"{frame.timestamp_sec:.3f}s")
        if probe is not None:
            status = "opened" if probe.opened else "failed"
            bits.append(f"{status} camera={probe.width}x{probe.height}")
        frame_size = self._frame_size_text()
        if frame_size:
            bits.append(f"frame={frame_size}")
        if self._requested_resolution != (0, 0):
            bits.append(f"requested={self._requested_resolution_label}")
        if self._quality is not None:
            bits.append(
                f"{self._quality.quality_label} {self._quality.score:.0f}/100 | "
                f"{self._quality.corner_count}/{self._quality.expected_corners} corners | "
                f"{self._quality.coverage_ratio:.0%} coverage"
            )
        elif self._detection is not None and frame is not None and self._detection.frame_index == frame.frame_index:
            bits.append(f"calib={self._detection.corner_count} corners")
        bits.append(f"samples={self._sample_count} | sync={self._sync_sample_count}")
        return " | ".join(bits)

    def _refresh_pixmap(self) -> None:
        if self._current_pixmap is None:
            return
        scaled = self._current_pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._draw_current_calibration_overlay(scaled)
        self._draw_readable_overlay(scaled)
        self._image_label.setPixmap(scaled)
        self._image_label.setText("")

    def _draw_current_calibration_overlay(self, pixmap: QPixmap) -> None:
        if pixmap.isNull() or self._frame is None:
            return
        detection = self._detection
        if detection is None or detection.frame_index != self._frame.frame_index or not detection.corner_points_px:
            return

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_calibration_overlay(painter, detection, pixmap.width(), pixmap.height())
        finally:
            painter.end()

    def _draw_readable_overlay(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return

        lines = self._overlay_lines()
        if not lines:
            return

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            font = QFont()
            font.setPointSize(max(9, min(14, pixmap.height() // 26)))
            font.setBold(True)
            painter.setFont(font)
            metrics = QFontMetrics(font)

            margin = max(8, pixmap.width() // 80)
            padding_x = max(8, pixmap.width() // 70)
            padding_y = max(7, pixmap.height() // 70)
            line_height = metrics.height() + 3
            max_text_width = max(120, pixmap.width() - (2 * margin) - (2 * padding_x))
            display_lines = [metrics.elidedText(line, Qt.TextElideMode.ElideRight, max_text_width) for line in lines]
            text_width = max(metrics.horizontalAdvance(line) for line in display_lines)
            panel_width = min(max_text_width + (2 * padding_x), text_width + (2 * padding_x))
            panel_height = (line_height * len(display_lines)) + (2 * padding_y)
            panel = QRectF(float(margin), float(margin), float(panel_width), float(panel_height))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(11, 31, 56, 205))
            painter.drawRoundedRect(panel, 8, 8)

            painter.setPen(QColor(255, 255, 255, 240))
            text_x = margin + padding_x
            text_y = margin + padding_y + metrics.ascent()
            for line in display_lines:
                painter.drawText(text_x, text_y, line)
                text_y += line_height
        finally:
            painter.end()

    def _overlay_lines(self) -> list[str]:
        lines: list[str] = [self._source.source_id]
        if self._frame is not None:
            lines.append(f"Frame #{self._frame.frame_index} @ {self._frame.timestamp_sec:.3f}s")

        if self._quality is not None:
            lines.append(f"{self._quality.quality_label.upper()} {self._quality.score:.0f}/100")
            lines.append(f"Corners {self._quality.corner_count}/{self._quality.expected_corners} | coverage {self._quality.coverage_ratio:.0%}")
        elif self._detection is not None:
            lines.append(f"Detected {self._detection.corner_count} corners | coverage {self._detection.coverage_ratio:.0%}")
        else:
            lines.append("No board detected")
        if self._detection is not None and getattr(self._detection, "pattern_type", "") == "charuco":
            corner_ids = getattr(self._detection, "corner_ids", [])
            if corner_ids:
                lines.append(f"ChArUco IDs visible: {len(corner_ids)}")

        lines.append(f"Samples cam={self._sample_count} | sync={self._sync_sample_count}")
        if self._probe is not None:
            status = "opened" if self._probe.opened else "failed"
            lines.append(f"Camera {status}: {self._probe.width}x{self._probe.height}")
        frame_size = self._frame_size_text()
        if frame_size:
            lines.append(f"Frame data: {frame_size}")
        if self._requested_resolution != (0, 0):
            lines.append(f"Requested: {self._requested_resolution_label}")
            if self._resolution_mismatch():
                lines.append("Camera fallback: preset niet geaccepteerd")
        return lines

    def _frame_size_text(self) -> str:
        if self._frame is None or not hasattr(self._frame.frame_data, "shape"):
            return ""
        shape = self._frame.frame_data.shape
        if len(shape) < 2:
            return ""
        height, width = shape[:2]
        return f"{int(width)}x{int(height)}"

    def _resolution_mismatch(self) -> bool:
        requested_width, requested_height = self._requested_resolution
        if requested_width <= 0 or requested_height <= 0:
            return False
        if self._probe is not None and self._probe.width > 0 and self._probe.height > 0:
            return self._probe.width != requested_width or self._probe.height != requested_height
        if self._frame is not None and hasattr(self._frame.frame_data, "shape"):
            height, width = self._frame.frame_data.shape[:2]
            return int(width) != requested_width or int(height) != requested_height
        return False

    def _frame_to_pixmap(self, frame_data: Any) -> QPixmap | None:
        if frame_data is None or not hasattr(frame_data, "shape"):
            return None

        shape = frame_data.shape
        if len(shape) == 2:
            height, width = shape
            grayscale = frame_data.copy()
            qimage = QImage(grayscale.data, width, height, width, QImage.Format.Format_Grayscale8)
            return QPixmap.fromImage(qimage.copy())

        if len(shape) < 3:
            return None

        height, width = shape[:2]
        channel_count = shape[2]
        if channel_count == 3:
            rgb_frame = frame_data[:, :, ::-1].copy()
            qimage = QImage(rgb_frame.data, width, height, 3 * width, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimage.copy())

        if channel_count >= 4:
            rgb_frame = frame_data[:, :, :3][:, :, ::-1].copy()
            qimage = QImage(rgb_frame.data, width, height, 3 * width, QImage.Format.Format_RGB888)
            return QPixmap.fromImage(qimage.copy())

        return None

    def _apply_calibration_overlay(self, pixmap: QPixmap, frame: FramePacket) -> QPixmap:
        detection = self._detection
        if detection is None or detection.frame_index != frame.frame_index or not detection.corner_points_px:
            return pixmap

        overlay = pixmap.copy()
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_calibration_overlay(painter, detection, overlay.width(), overlay.height())
        finally:
            painter.end()
        return overlay

    def _draw_calibration_overlay(
        self,
        painter: QPainter,
        detection: CalibrationViewDetection,
        width: int,
        height: int,
    ) -> None:
        scale_x = width / detection.image_size[0] if detection.image_size[0] else 1.0
        scale_y = height / detection.image_size[1] if detection.image_size[1] else 1.0
        points = [QPointF(point_x * scale_x, point_y * scale_y) for point_x, point_y in detection.corner_points_px]
        if not points:
            return

        columns, rows = detection.board_shape
        pattern_type = getattr(detection, "pattern_type", "chessboard")
        corner_ids = [int(value) for value in getattr(detection, "corner_ids", [])]
        line_width = max(3, int(min(width, height) * 0.006))

        def draw_board_grid(pen: QPen) -> None:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for row_index in range(rows):
                row_start = row_index * columns
                for column_index in range(columns - 1):
                    painter.drawLine(points[row_start + column_index], points[row_start + column_index + 1])
            for row_index in range(rows - 1):
                row_start = row_index * columns
                next_row_start = (row_index + 1) * columns
                for column_index in range(columns):
                    painter.drawLine(points[row_start + column_index], points[next_row_start + column_index])

        if pattern_type != "charuco" and columns > 1 and rows > 1 and len(points) >= columns * rows:
            shadow_pen = QPen(QColor(2, 8, 23, 230), line_width + 4)
            shadow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            shadow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            highlight_pen = QPen(QColor(45, 255, 196, 245), line_width)
            highlight_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            highlight_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            draw_board_grid(shadow_pen)
            draw_board_grid(highlight_pen)

        radius = max(5, int(min(width, height) * 0.011))
        painter.setPen(QPen(QColor(2, 8, 23, 240), max(3, line_width)))
        painter.setBrush(QColor(250, 204, 21, 245) if pattern_type == "charuco" else QColor(45, 255, 196, 235))
        for point in points:
            painter.drawEllipse(point, radius + 2, radius + 2)

        painter.setPen(QPen(QColor(255, 255, 255, 245), max(1, line_width // 2)))
        painter.setBrush(QColor(250, 204, 21, 245) if pattern_type == "charuco" else QColor(45, 255, 196, 235))
        for point in points:
            painter.drawEllipse(point, radius, radius)

        if pattern_type == "charuco" and corner_ids:
            self._draw_charuco_id_labels(painter, points, corner_ids, radius, width, height)

    def _draw_charuco_id_labels(
        self,
        painter: QPainter,
        points: list[QPointF],
        corner_ids: list[int],
        radius: int,
        width: int,
        height: int,
    ) -> None:
        font = QFont()
        font.setPixelSize(max(11, min(22, int(min(width, height) * 0.045))))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        padding_x = max(4, radius // 2)
        padding_y = max(2, radius // 3)
        offset = max(7, radius + 4)

        for point, corner_id in zip(points, corner_ids):
            label = str(corner_id)
            text_width = metrics.horizontalAdvance(label)
            text_height = metrics.height()
            box_width = text_width + (2 * padding_x)
            box_height = text_height + (2 * padding_y)
            box_x = int(point.x() + offset)
            box_y = int(point.y() - box_height - offset // 2)
            box_x = max(2, min(box_x, max(2, width - box_width - 2)))
            box_y = max(2, min(box_y, max(2, height - box_height - 2)))
            label_box = QRectF(float(box_x), float(box_y), float(box_width), float(box_height))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(2, 8, 23, 225))
            painter.drawRoundedRect(label_box, 4, 4)
            painter.setPen(QColor(255, 255, 255, 245))
            painter.drawText(
                int(box_x + padding_x),
                int(box_y + padding_y + metrics.ascent()),
                label,
            )


class MultiCameraPreviewWidget(QWidget):
    source_selected = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        minimum_tile_size: tuple[int, int] = (300, 170),
    ) -> None:
        super().__init__(parent)
        self._minimum_tile_size = minimum_tile_size
        self._sources: list[CameraSourceConfig] = []
        self._probe_results: dict[str, CameraProbeResult] = {}
        self._detections: dict[str, CalibrationViewDetection] = {}
        self._quality_scores: dict[str, CalibrationCameraQuality] = {}
        self._sample_counts: dict[str, int] = {}
        self._sync_sample_count = 0
        self._requested_resolution: tuple[int, int] = (0, 0)
        self._requested_resolution_label = "Auto"
        self._latest_batch: CaptureBatch | None = None
        self._selected_source_id: str | None = None
        self._tiles: dict[str, _PreviewTileWidget] = {}

        self._summary_label = QLabel("No cameras configured.")
        self._summary_label.setObjectName("multiPreviewSummary")

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(10)

        self._empty_label = QLabel("Waiting for capture frames...")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("multiPreviewEmpty")
        self._grid_layout.addWidget(self._empty_label, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._grid_widget)

        group = QGroupBox("Camera Previews")
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(self._summary_label)
        group_layout.addWidget(scroll, 1)

        root = QVBoxLayout(self)
        root.addWidget(group, 1)

    def selected_source_id(self) -> str | None:
        return self._selected_source_id

    def select_source(self, source_id: str | None) -> None:
        self._selected_source_id = source_id or None
        for tile in self._tiles.values():
            tile.set_selected(tile.source_id() == self._selected_source_id)
        self._refresh_summary()

    def set_sources(
        self,
        sources: Sequence[CameraSourceConfig],
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        previous_selection = self._selected_source_id
        self._sources = list(sources)
        self._probe_results = dict(probe_results or {})
        self._rebuild_tiles()
        self.select_source(previous_selection if previous_selection in self._tiles else None)
        if self._latest_batch is not None:
            self._update_tiles_from_batch()
        self._refresh_summary()

    def show_batch(
        self,
        batch: CaptureBatch,
        sources: Sequence[CameraSourceConfig] | None = None,
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        self._latest_batch = batch
        if sources is not None:
            source_ids = [source.source_id for source in sources]
            current_ids = [source.source_id for source in self._sources]
            if source_ids != current_ids:
                self.set_sources(sources, probe_results or self._probe_results)
            else:
                self._sources = list(sources)
        if probe_results is not None:
            self._probe_results = dict(probe_results)
        if not self._sources:
            self._sources = [
                CameraSourceConfig(source_id=source_id, kind="webcam", uri=source_id)
                for source_id in batch.frames
            ]
            self._rebuild_tiles()
        self._update_tiles_from_batch()
        self._refresh_summary()

    def set_calibration_detections(self, detections: dict[str, CalibrationViewDetection] | None) -> None:
        self._detections = dict(detections or {})
        for source_id, tile in self._tiles.items():
            tile.set_calibration_detection(self._detections.get(source_id))
        self._refresh_summary()

    def set_camera_quality_scores(self, scores: dict[str, CalibrationCameraQuality] | None) -> None:
        self._quality_scores = dict(scores or {})
        for source_id, tile in self._tiles.items():
            tile.set_quality(self._quality_scores.get(source_id))
        self._refresh_summary()

    def set_sample_counts(self, sample_counts: dict[str, int] | None, synchronized_samples: int) -> None:
        self._sample_counts = {source_id: int(count) for source_id, count in dict(sample_counts or {}).items()}
        self._sync_sample_count = max(0, int(synchronized_samples))
        for source_id, tile in self._tiles.items():
            tile.set_sample_status(self._sample_counts.get(source_id, 0), self._sync_sample_count)
        self._refresh_summary()

    def set_requested_resolution(self, width: int, height: int, label: str = "Auto") -> None:
        self._requested_resolution = max(0, int(width)), max(0, int(height))
        self._requested_resolution_label = label.strip() or "Auto"
        for tile in self._tiles.values():
            tile.set_requested_resolution(*self._requested_resolution, self._requested_resolution_label)
        self._refresh_summary()

    def clear_preview(self, message: str = "No frame yet") -> None:
        self._latest_batch = None
        self._detections = {}
        self._quality_scores = {}
        self._sample_counts = {}
        self._sync_sample_count = 0
        for tile in self._tiles.values():
            tile.set_calibration_detection(None)
            tile.set_quality(None)
            tile.set_sample_status(0, 0)
            tile.set_frame(None, self._probe_results.get(tile.source_id()))
        self._summary_label.setText(message)

    def _rebuild_tiles(self) -> None:
        self._clear_layout()
        self._tiles.clear()
        if not self._sources:
            self._grid_layout.addWidget(self._empty_label, 0, 0)
            return

        columns = self._columns_for_count(len(self._sources))
        for index, source in enumerate(self._sources):
            tile = _PreviewTileWidget(source, self._minimum_tile_size)
            tile.selected.connect(self._on_tile_selected)
            tile.set_selected(source.source_id == self._selected_source_id)
            tile.set_calibration_detection(self._detections.get(source.source_id))
            tile.set_quality(self._quality_scores.get(source.source_id))
            tile.set_sample_status(self._sample_counts.get(source.source_id, 0), self._sync_sample_count)
            tile.set_requested_resolution(*self._requested_resolution, self._requested_resolution_label)
            self._tiles[source.source_id] = tile
            self._grid_layout.addWidget(tile, index // columns, index % columns)

    def _update_tiles_from_batch(self) -> None:
        if self._latest_batch is None:
            return
        for source_id, tile in self._tiles.items():
            tile.set_calibration_detection(self._detections.get(source_id))
            tile.set_quality(self._quality_scores.get(source_id))
            tile.set_sample_status(self._sample_counts.get(source_id, 0), self._sync_sample_count)
            tile.set_frame(self._latest_batch.frames.get(source_id), self._probe_results.get(source_id))

    def _clear_layout(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _columns_for_count(self, source_count: int) -> int:
        if source_count <= 1:
            return 1
        if source_count <= 4:
            return 2
        return 3

    def _on_tile_selected(self, source_id: str) -> None:
        self.select_source(source_id)
        self.source_selected.emit(source_id)

    def _refresh_summary(self) -> None:
        if not self._sources:
            self._summary_label.setText("No cameras configured.")
            return
        visible_count = len(self._detections)
        good_count = sum(1 for quality in self._quality_scores.values() if quality.visible and quality.score >= 70.0)
        selected_text = self._selected_source_id or "none"
        frame_count = len(self._latest_batch.frames) if self._latest_batch is not None else 0
        dropped_count = len(self._latest_batch.dropped_sources) if self._latest_batch is not None else 0
        sample_total = sum(self._sample_counts.values())
        self._summary_label.setText(
            f"{len(self._sources)} camera(s) | frames={frame_count} | calib_visible={visible_count}/{len(self._sources)} "
            f"| good={good_count}/{len(self._sources)} | samples={sample_total} | sync={self._sync_sample_count} "
            f"| selected={selected_text} | dropped={dropped_count}"
        )
