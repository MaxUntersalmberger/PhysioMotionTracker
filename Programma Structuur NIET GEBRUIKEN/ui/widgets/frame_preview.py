from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QSizePolicy, QVBoxLayout, QWidget

from calibration import CalibrationViewDetection
from capture.backend import CaptureBatch
from models.types import CameraProbeResult, CameraSourceConfig, FramePacket, PipelineResult


_POSE_CONNECTIONS: tuple[tuple[str, str], ...] = (
    ("nose", "left_shoulder"),
    ("nose", "right_shoulder"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)


class FramePreviewWidget(QWidget):
    source_selected = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        show_source_picker: bool = True,
        minimum_image_size: tuple[int, int] = (640, 360),
    ) -> None:
        super().__init__(parent)
        self._show_source_picker = bool(show_source_picker)
        self._source_combo = QComboBox()
        self._source_combo.currentIndexChanged.connect(self._render_current_selection)

        self._image_label = QLabel("No frame yet")
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setMinimumSize(int(minimum_image_size[0]), int(minimum_image_size[1]))
        self._image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image_label.setObjectName("framePreviewImage")

        self._source_label = QLabel("Auto")
        self._source_label.setObjectName("framePreviewSource")
        self._status_label = QLabel("Waiting for probe or capture data.")
        self._status_label.setWordWrap(True)
        self._status_label.setObjectName("framePreviewStatus")

        form = QFormLayout()
        form.addRow("Selected source", self._source_combo)
        form.addRow("Rendered source", self._source_label)

        controls_group = QGroupBox("Preview Selection")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.addLayout(form)
        controls_group.setVisible(self._show_source_picker)

        preview_group = QGroupBox("Live Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self._image_label, 1)
        preview_layout.addWidget(self._status_label)

        root = QVBoxLayout(self)
        root.addWidget(controls_group)
        root.addWidget(preview_group, 1)

        self._latest_batch: CaptureBatch | None = None
        self._latest_sources: list[CameraSourceConfig] = []
        self._latest_probe_results: dict[str, CameraProbeResult] = {}
        self._latest_pipeline_result: PipelineResult | None = None
        self._latest_calibration_detections: dict[str, CalibrationViewDetection] = {}
        self._current_pixmap: QPixmap | None = None
        self._last_emitted_source_id: str | None = None
        self._source_combo.addItem("Auto", "")

    def selected_source_id(self) -> str | None:
        data = self._source_combo.currentData()
        if isinstance(data, str) and data:
            return data
        return None

    def select_source(self, source_id: str | None) -> None:
        self._source_combo.blockSignals(True)
        if source_id:
            index = self._source_combo.findData(source_id)
            if index >= 0:
                self._source_combo.setCurrentIndex(index)
            else:
                self._source_combo.setCurrentIndex(0)
        else:
            self._source_combo.setCurrentIndex(0)
        self._source_combo.blockSignals(False)
        self._render_current_selection()

    def set_sources(
        self,
        sources: Sequence[CameraSourceConfig],
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        previous_selection = self.selected_source_id()
        self._latest_sources = list(sources)
        self._latest_probe_results = dict(probe_results or {})

        self._source_combo.blockSignals(True)
        self._source_combo.clear()
        self._source_combo.addItem("Auto", "")
        for source in self._latest_sources:
            self._source_combo.addItem(self._format_source_label(source), source.source_id)

        if previous_selection:
            index = self._source_combo.findData(previous_selection)
            if index >= 0:
                self._source_combo.setCurrentIndex(index)
        self._source_combo.blockSignals(False)
        self._render_current_selection()

    def show_batch(
        self,
        batch: CaptureBatch,
        sources: Sequence[CameraSourceConfig] | None = None,
        probe_results: dict[str, CameraProbeResult] | None = None,
    ) -> None:
        self._latest_batch = batch
        if sources is not None or probe_results is not None:
            self.set_sources(sources or [], probe_results)
        else:
            self._render_current_selection()

    def set_pipeline_result(self, result: PipelineResult | None) -> None:
        self._latest_pipeline_result = result
        if self._latest_batch is not None:
            self._render_current_selection()

    def set_calibration_detections(self, detections: dict[str, CalibrationViewDetection] | None) -> None:
        self._latest_calibration_detections = dict(detections or {})
        if self._latest_batch is not None:
            self._render_current_selection()

    def clear_preview(self, message: str = "No frame yet") -> None:
        self._latest_batch = None
        self._latest_pipeline_result = None
        self._latest_calibration_detections = {}
        self._current_pixmap = None
        self._last_emitted_source_id = None
        self._image_label.setPixmap(QPixmap())
        self._image_label.setText(message)
        self._source_label.setText("Auto")
        self._status_label.setText(message)

    def _render_current_selection(self) -> None:
        selected_source_id = self.selected_source_id()
        if self._latest_batch is None or not self._latest_batch.frames:
            self.clear_preview("Waiting for capture frames...")
            return

        frame = self._pick_frame(selected_source_id)
        if frame is None:
            self.clear_preview("No frame available for the current selection.")
            return

        source = next((item for item in self._latest_sources if item.source_id == frame.source_id), None)
        source_label = source.label if source and source.label else frame.source_id
        probe = self._latest_probe_results.get(frame.source_id)
        status_bits = [f"{frame.frame_index} @ {frame.timestamp_sec:.3f}s"]
        if probe is not None:
            status_bits.append(f"{probe.backend} {probe.width}x{probe.height}")
            status_bits.append("opened" if probe.opened else "failed")
        if selected_source_id and selected_source_id != frame.source_id:
            status_bits.append(f"fallback from {selected_source_id}")

        overlay_bits = self._overlay_status_bits(frame)
        if overlay_bits:
            status_bits.extend(overlay_bits)

        self._source_label.setText(f"{frame.source_id} | {source_label}")
        self._status_label.setText(" | ".join(status_bits))
        self._render_frame(frame)
        if frame.source_id != self._last_emitted_source_id:
            self._last_emitted_source_id = frame.source_id
            self.source_selected.emit(frame.source_id)

    def _pick_frame(self, selected_source_id: str | None) -> FramePacket | None:
        if self._latest_batch is None or not self._latest_batch.frames:
            return None
        if selected_source_id and selected_source_id in self._latest_batch.frames:
            return self._latest_batch.frames[selected_source_id]
        return next(iter(self._latest_batch.frames.values()))

    def _render_frame(self, frame: FramePacket) -> None:
        pixmap = self._frame_to_pixmap(frame.frame_data)
        if pixmap is None:
            self.clear_preview(f"Unsupported frame payload for {frame.source_id}.")
            return

        self._current_pixmap = self._apply_overlay(pixmap, frame)
        self._refresh_pixmap()

    def _apply_overlay(self, pixmap: QPixmap, frame: FramePacket) -> QPixmap:
        if not self._has_overlay_for_frame(frame):
            return pixmap

        overlay = pixmap.copy()
        painter = QPainter(overlay)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_pose_overlay(painter, frame, overlay.width(), overlay.height())
        finally:
            painter.end()
        return overlay

    def _refresh_pixmap(self) -> None:
        if self._current_pixmap is None:
            return
        scaled = self._current_pixmap.scaled(
            self._image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        self._image_label.setText("")

    def _frame_to_pixmap(self, frame_data: Any) -> QPixmap | None:
        if frame_data is None or not hasattr(frame_data, "shape"):
            return None

        shape = frame_data.shape
        if len(shape) == 2:
            height, width = shape
            grayscale = frame_data.copy()
            bytes_per_line = width
            qimage = QImage(grayscale.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
            return QPixmap.fromImage(qimage.copy())

        if len(shape) < 3:
            return None

        height, width = shape[:2]
        channel_count = shape[2]
        if channel_count == 3:
            rgb_frame = frame_data[:, :, ::-1].copy()
            bytes_per_line = 3 * width
            qimage = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            return QPixmap.fromImage(qimage.copy())

        if channel_count >= 4:
            rgb_frame = frame_data[:, :, :3][:, :, ::-1].copy()
            bytes_per_line = 3 * width
            qimage = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            return QPixmap.fromImage(qimage.copy())

        return None

    def _has_overlay_for_frame(self, frame: FramePacket) -> bool:
        result = self._latest_pipeline_result
        if result is not None and result.frame_index == frame.frame_index:
            if frame.source_id in result.poses_2d or frame.source_id in result.reprojected_keypoints_px:
                return True

        calibration = self._latest_calibration_detections.get(frame.source_id)
        if calibration is not None and calibration.frame_index == frame.frame_index:
            return True

        return False

    def _overlay_status_bits(self, frame: FramePacket) -> list[str]:
        bits: list[str] = []

        result = self._latest_pipeline_result
        if result is not None and result.frame_index == frame.frame_index:
            pose = result.poses_2d.get(frame.source_id)
            if pose is not None:
                bits.append(f"overlay={len(pose.keypoints)} kp")

            reprojected = result.reprojected_keypoints_px.get(frame.source_id)
            if reprojected:
                bits.append(f"reproj={len(reprojected)}")

        calibration = self._latest_calibration_detections.get(frame.source_id)
        if calibration is not None and calibration.frame_index == frame.frame_index:
            bits.append(f"calib={calibration.corner_count} corners")

        return bits

    def _draw_pose_overlay(self, painter: QPainter, frame: FramePacket, width: int, height: int) -> None:
        result = self._latest_pipeline_result
        pose_drawn = False
        if result is not None and result.frame_index == frame.frame_index:
            pose = result.poses_2d.get(frame.source_id)
            if pose is not None and pose.keypoints:
                keypoints_by_name = pose.keypoints_by_name()
                radius = max(4, int(min(width, height) * 0.012))
                line_width = max(2, int(radius * 0.35))

                line_pen = QPen(QColor(52, 214, 194, 210), line_width)
                line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(line_pen)
                for start_name, end_name in _POSE_CONNECTIONS:
                    start = keypoints_by_name.get(start_name)
                    end = keypoints_by_name.get(end_name)
                    if start is None or end is None:
                        continue
                    if start.confidence < 0.18 or end.confidence < 0.18:
                        continue
                    painter.drawLine(
                        QPointF(start.x * width, start.y * height),
                        QPointF(end.x * width, end.y * height),
                    )

                for keypoint in pose.keypoints:
                    if keypoint.confidence < 0.1:
                        continue
                    center_x = keypoint.x * width
                    center_y = keypoint.y * height
                    outer_color = QColor(255, 255, 255, 220)
                    inner_color = QColor(31, 111, 235, int(105 + (110 * keypoint.confidence)))
                    painter.setPen(QPen(outer_color, max(2, line_width)))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(center_x, center_y), radius + 1, radius + 1)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(inner_color)
                    painter.drawEllipse(QPointF(center_x, center_y), radius, radius)
                pose_drawn = True

            self._draw_reprojected_overlay(painter, result, frame)

        self._draw_calibration_overlay(painter, frame, width, height)
        if not pose_drawn and result is None:
            return

    def _draw_calibration_overlay(self, painter: QPainter, frame: FramePacket, width: int, height: int) -> None:
        detection = self._latest_calibration_detections.get(frame.source_id)
        if detection is None or detection.frame_index != frame.frame_index or not detection.corner_points_px:
            return

        scale_x = width / detection.image_size[0] if detection.image_size[0] else 1.0
        scale_y = height / detection.image_size[1] if detection.image_size[1] else 1.0
        points = [QPointF(point_x * scale_x, point_y * scale_y) for point_x, point_y in detection.corner_points_px]

        if not points:
            return

        border_pen = QPen(QColor(94, 234, 212, 220), 2)
        border_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        border_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        columns, rows = detection.board_shape
        if columns > 1 and rows > 1 and len(points) >= columns * rows:
            for row_index in range(rows):
                row_start = row_index * columns
                for column_index in range(columns - 1):
                    start = points[row_start + column_index]
                    end = points[row_start + column_index + 1]
                    painter.drawLine(start, end)
            for row_index in range(rows - 1):
                row_start = row_index * columns
                next_row_start = (row_index + 1) * columns
                for column_index in range(columns):
                    painter.drawLine(points[row_start + column_index], points[next_row_start + column_index])

        radius = max(3, int(min(width, height) * 0.008))
        outer_pen = QPen(QColor(11, 31, 56, 220), 2)
        painter.setPen(outer_pen)
        painter.setBrush(QColor(94, 234, 212, 210))
        for point in points:
            painter.drawEllipse(point, radius, radius)

    def _draw_reprojected_overlay(self, painter: QPainter, result: PipelineResult, frame: FramePacket) -> None:
        reprojected_points = result.reprojected_keypoints_px.get(frame.source_id)
        if not reprojected_points:
            return

        line_width = 2
        radius = 5
        cross_pen = QPen(QColor(255, 163, 0, 225), line_width)
        cross_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(cross_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for point_x, point_y in reprojected_points.values():
            painter.drawLine(QPointF(point_x - radius, point_y), QPointF(point_x + radius, point_y))
            painter.drawLine(QPointF(point_x, point_y - radius), QPointF(point_x, point_y + radius))

    def _format_source_label(self, source: CameraSourceConfig) -> str:
        probe = self._latest_probe_results.get(source.source_id)
        base_label = source.label or source.source_id
        if probe is None:
            return f"{source.source_id} | {base_label} | pending"
        status = "opened" if probe.opened else "failed"
        return f"{source.source_id} | {base_label} | {status} {probe.width}x{probe.height}"

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()
