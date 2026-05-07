from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from biomechanics import JointAngleAnalysisReport, format_joint_angle_report
from motion import MotionTake


class MotionAnalysisWidget(QWidget):
    load_review_take_requested = Signal()
    open_take_requested = Signal()
    analyze_joint_angles_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._state_label = QPlainTextEdit()
        self._state_label.setReadOnly(True)
        self._state_label.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._state_label.setMaximumHeight(72)
        self._state_label.setPlaceholderText("Analysis status appears here.")
        self._take_label = QPlainTextEdit()
        self._take_label.setReadOnly(True)
        self._take_label.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._take_label.setMaximumHeight(64)
        self._take_label.setPlaceholderText("Loaded motion take path appears here.")
        self._summary_output = QPlainTextEdit()
        self._summary_output.setReadOnly(True)
        self._summary_output.setPlaceholderText("Motion take and joint-angle summaries appear here.")
        self._detail_output = QPlainTextEdit()
        self._detail_output.setReadOnly(True)
        self._detail_output.setPlaceholderText("Per-frame reconstruction and joint-angle values appear here.")

        self._load_review_button = QPushButton("Load Review Take")
        self._open_take_button = QPushButton("Open Take")
        self._analyze_angles_button = QPushButton("Analyze Angles")
        self._analyze_angles_button.setEnabled(False)
        for button in (self._load_review_button, self._open_take_button, self._analyze_angles_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        controls_box = QGroupBox("Analysis Controls")
        controls_layout = QVBoxLayout(controls_box)
        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(8)
        button_grid.addWidget(self._load_review_button, 0, 0)
        button_grid.addWidget(self._open_take_button, 0, 1)
        button_grid.addWidget(self._analyze_angles_button, 0, 2)
        for column in range(3):
            button_grid.setColumnStretch(column, 1)
        controls_layout.addLayout(button_grid)
        controls_layout.addWidget(self._take_label)
        controls_layout.addWidget(self._state_label)

        summary_box = QGroupBox("Motion Analysis")
        summary_layout = QVBoxLayout(summary_box)
        summary_layout.addWidget(self._summary_output)

        detail_box = QGroupBox("Detailed Values")
        detail_layout = QVBoxLayout(detail_box)
        detail_layout.addWidget(self._detail_output)

        root = QVBoxLayout(self)
        root.addWidget(controls_box)
        root.addWidget(summary_box, 1)
        root.addWidget(detail_box, 2)

        self._load_review_button.clicked.connect(self.load_review_take_requested.emit)
        self._open_take_button.clicked.connect(self.open_take_requested.emit)
        self._analyze_angles_button.clicked.connect(self.analyze_joint_angles_requested.emit)

    def set_state(self, text: str) -> None:
        self._state_label.setPlainText(text)

    def set_motion_take(self, take: MotionTake, path: Path) -> None:
        self._take_label.setPlainText(f"Take: {path}")
        self._analyze_angles_button.setEnabled(True)
        modes = ", ".join(
            f"{mode}={count}" for mode, count in sorted(take.summary.reconstruction_modes.items())
        )
        lines = [
            f"Session: {take.session_id}",
            f"Take ID: {take.take_id}",
            f"Detector: {take.detector_name}",
            f"Calibration loaded: {'yes' if take.calibration_loaded else 'no'}",
            f"Frames: {take.summary.frame_count}",
            f"2D pose frames: {take.summary.pose2d_frames}",
            f"3D pose frames: {take.summary.pose3d_frames}",
            f"2D keypoints: {take.summary.pose2d_keypoints}",
            f"3D keypoints: {take.summary.pose3d_keypoints}",
        ]
        if modes:
            lines.append(f"Reconstruction modes: {modes}")
        lines.append("Pipeline stages:")
        lines.extend(f"- {name}: {status}" for name, status in take.stages.items())
        self._summary_output.setPlainText("\n".join(lines))
        self._detail_output.setPlainText(_motion_take_detail_text(take))
        self.set_state("Motion take loaded.")

    def set_joint_angle_report(self, report: JointAngleAnalysisReport) -> None:
        current_text = self._summary_output.toPlainText().rstrip()
        report_text = format_joint_angle_report(report)
        if current_text:
            self._summary_output.setPlainText(f"{current_text}\n\n{report_text}")
        else:
            self._summary_output.setPlainText(report_text)
        self._detail_output.setPlainText(_joint_angle_detail_text(report))
        if report.analysis.samples:
            self.set_state(f"Joint angles ready: {len(report.analysis.samples)} sample(s).")
        else:
            self.set_state("Joint-angle analysis finished without samples.")

    def clear_analysis(self, message: str = "No processed motion take loaded.") -> None:
        self._take_label.setPlainText("Take: none")
        self._summary_output.setPlainText("")
        self._detail_output.setPlainText("")
        self._analyze_angles_button.setEnabled(False)
        self.set_state(message)


def _motion_take_detail_text(take: MotionTake, max_frames: int = 80) -> str:
    if not take.frames:
        return "No processed frames are available in this motion take."

    lines = [
        "Reconstruction values",
        "Columns: frame | time | mode | trust | mean error | joints",
    ]
    for frame in take.frames[:max_frames]:
        error_text = (
            f"{frame.mean_reprojection_error_px:.3f}px"
            if frame.mean_reprojection_error_px is not None
            else "n/a"
        )
        joint_count = len(frame.pose_3d.keypoints) if frame.pose_3d is not None else 0
        lines.append(
            f"{frame.frame_index} | {frame.timestamp_sec:.3f}s | {frame.reconstruction_mode} | "
            f"{frame.reconstruction_trust_state} {frame.reconstruction_trust_score:.0f}/100 | "
            f"{error_text} | {joint_count}"
        )
        if frame.pose_3d is None:
            continue
        for keypoint in frame.pose_3d.keypoints[:24]:
            view_count = frame.per_joint_view_count.get(keypoint.name, 0)
            joint_confidence = frame.per_joint_confidence.get(keypoint.name, keypoint.confidence)
            joint_error = frame.per_joint_reprojection_error_px.get(keypoint.name)
            joint_error_text = f"{joint_error:.3f}px" if joint_error is not None else "n/a"
            lines.append(
                f"  {keypoint.name}: xyz=({keypoint.x:.4f}, {keypoint.y:.4f}, {keypoint.z:.4f}), "
                f"conf={joint_confidence:.2f}, views={view_count}, error={joint_error_text}"
            )

    if len(take.frames) > max_frames:
        lines.append(f"... {len(take.frames) - max_frames} more frame(s) not shown.")
    return "\n".join(lines)


def _joint_angle_detail_text(report: JointAngleAnalysisReport, max_samples: int = 240) -> str:
    samples = report.analysis.samples
    if not samples:
        return "\n".join(report.notes) if report.notes else "No joint-angle samples were computed."

    lines = [
        "Joint angle values",
        "Columns: frame | time | joint | angle | confidence",
    ]
    for sample in samples[:max_samples]:
        lines.append(
            f"{sample.frame_index} | {sample.timestamp_sec:.3f}s | {sample.joint_name} | "
            f"{sample.angle_deg:.2f} deg | {sample.confidence:.2f}"
        )
    if len(samples) > max_samples:
        lines.append(f"... {len(samples) - max_samples} more sample(s) not shown.")
    return "\n".join(lines)
