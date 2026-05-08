from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from .legacy_bridge import ensure_legacy_path

ensure_legacy_path()

from calibration.manager import (  # noqa: E402
    CALIBRATION_MODE_EXTRINSICS,
    CALIBRATION_MODE_INTRINSICS,
    CalibrationManager,
    CalibrationSolveResult,
    _CalibrationDetection,
    _board_object_points,
    _estimate_coverage_ratio,
)


CALIBRATION_OBJECT_CHESSBOARD = "chessboard"
CALIBRATION_OBJECT_CHARUCO = "charuco"
CALIBRATION_DETECTOR_AUTO = "auto"
CALIBRATION_DETECTOR_CHESSBOARD_SB = "chessboard_sb"
CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC = "chessboard_classic"
CALIBRATION_DETECTOR_CHARUCO = "charuco"

CALIBRATION_OBJECT_CHOICES: tuple[tuple[str, str, str], ...] = (
    (CALIBRATION_OBJECT_CHESSBOARD, "Chessboard", "Regular inner-corner chessboard pattern."),
    (CALIBRATION_OBJECT_CHARUCO, "ChArUco", "ChArUco board using OpenCV ArUco markers."),
)
CALIBRATION_DETECTOR_CHOICES: tuple[tuple[str, str, str], ...] = (
    (CALIBRATION_DETECTOR_AUTO, "Auto", "Use the best detector for the selected object."),
    (CALIBRATION_DETECTOR_CHESSBOARD_SB, "Chessboard SB", "Use OpenCV findChessboardCornersSB."),
    (CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC, "Classic chessboard", "Use OpenCV findChessboardCorners."),
    (CALIBRATION_DETECTOR_CHARUCO, "ChArUco", "Use OpenCV ArUco/ChArUco detection."),
)


class CalibrationOnlyManager(CalibrationManager):
    def __init__(
        self,
        board_shape: tuple[int, int] = (9, 6),
        square_size_m: float = 0.024,
        calibration_object_type: str = CALIBRATION_OBJECT_CHESSBOARD,
        calibration_detector_name: str = CALIBRATION_DETECTOR_AUTO,
        min_samples_per_camera: int = 6,
        min_synchronized_samples: int = 4,
    ) -> None:
        super().__init__(
            board_shape=board_shape,
            square_size_m=square_size_m,
            min_samples_per_camera=min_samples_per_camera,
            min_synchronized_samples=min_synchronized_samples,
        )
        self._calibration_object_type = normalize_calibration_object_type(calibration_object_type)
        self._calibration_detector_name = normalize_calibration_detector_name(calibration_detector_name)
        if self._calibration_detector_name == CALIBRATION_DETECTOR_CHARUCO:
            self._calibration_object_type = CALIBRATION_OBJECT_CHARUCO

    @property
    def calibration_object_type(self) -> str:
        return self._calibration_object_type

    @property
    def calibration_detector_name(self) -> str:
        return self._calibration_detector_name

    def set_detection_preferences(self, calibration_object_type: str, calibration_detector_name: str) -> None:
        object_type = normalize_calibration_object_type(calibration_object_type)
        detector_name = normalize_calibration_detector_name(calibration_detector_name)
        if detector_name == CALIBRATION_DETECTOR_CHARUCO:
            object_type = CALIBRATION_OBJECT_CHARUCO
        elif object_type == CALIBRATION_OBJECT_CHARUCO and detector_name not in {
            CALIBRATION_DETECTOR_AUTO,
            CALIBRATION_DETECTOR_CHARUCO,
        }:
            detector_name = CALIBRATION_DETECTOR_CHARUCO

        if object_type != self._calibration_object_type:
            self.reset_samples()
        self._calibration_object_type = object_type
        self._calibration_detector_name = detector_name

    def solve_intrinsics(self) -> CalibrationSolveResult:
        return self._with_metadata(super().solve_intrinsics())

    def solve_extrinsics(self) -> CalibrationSolveResult:
        return self._with_metadata(super().solve_extrinsics())

    def _with_metadata(self, result: CalibrationSolveResult) -> CalibrationSolveResult:
        metadata = dict(result.bundle.metadata)
        metadata.update(
            {
                "calibration_object_type": self._calibration_object_type,
                "calibration_detector_name": self._calibration_detector_name,
            }
        )
        result.bundle.metadata.clear()
        result.bundle.metadata.update(metadata)
        self.set_bundle(result.bundle)
        return result

    def _detect_calibration_board(self, source_id, frame) -> _CalibrationDetection | None:
        image = frame.frame_data
        if image is None or not hasattr(image, "shape"):
            return None
        array = np.asarray(image)
        if array.ndim == 2:
            gray = array
        elif array.ndim >= 3:
            gray = cv2.cvtColor(array[:, :, :3], cv2.COLOR_BGR2GRAY)
        else:
            return None

        if self._calibration_object_type == CALIBRATION_OBJECT_CHARUCO:
            return self._detect_charuco_board(source_id, frame, gray)
        if self._calibration_detector_name == CALIBRATION_DETECTOR_CHARUCO:
            return self._detect_charuco_board(source_id, frame, gray)

        use_sb = self._calibration_detector_name in {
            CALIBRATION_DETECTOR_AUTO,
            CALIBRATION_DETECTOR_CHESSBOARD_SB,
        }
        use_classic = self._calibration_detector_name in {
            CALIBRATION_DETECTOR_AUTO,
            CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC,
        }
        return self._detect_chessboard(source_id, frame, gray, use_sb=use_sb, use_classic=use_classic)

    def _detect_chessboard(
        self,
        source_id: str,
        frame,
        gray: np.ndarray,
        use_sb: bool,
        use_classic: bool,
    ) -> _CalibrationDetection | None:
        corners = None
        found = False
        try:
            if use_sb and hasattr(cv2, "findChessboardCornersSB"):
                found, corners = cv2.findChessboardCornersSB(
                    gray,
                    self.board_shape,
                    flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_NORMALIZE_IMAGE,
                )
            if not found and use_classic:
                found, corners = cv2.findChessboardCorners(
                    gray,
                    self.board_shape,
                    flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
                )
                if found:
                    corners = cv2.cornerSubPix(
                        gray,
                        corners,
                        winSize=(11, 11),
                        zeroZone=(-1, -1),
                        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
                    )
        except cv2.error:
            return None

        if not found or corners is None:
            return None

        image_height, image_width = gray.shape[:2]
        image_points = corners.reshape(-1, 1, 2).astype(np.float32)
        return _CalibrationDetection(
            source_id=source_id,
            frame_index=frame.frame_index,
            timestamp_sec=frame.timestamp_sec,
            image_size=(int(image_width), int(image_height)),
            object_points=_board_object_points(self.board_shape, self.square_size_m),
            image_points=image_points,
            coverage_ratio=_estimate_coverage_ratio(image_points.reshape(-1, 2), image_width, image_height),
            pattern_type="chessboard",
        )


def normalize_calibration_object_type(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"charuco", "ch_aruco", "aruco_charuco"}:
        return CALIBRATION_OBJECT_CHARUCO
    return CALIBRATION_OBJECT_CHESSBOARD


def normalize_calibration_detector_name(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "": CALIBRATION_DETECTOR_AUTO,
        "auto": CALIBRATION_DETECTOR_AUTO,
        "automatic": CALIBRATION_DETECTOR_AUTO,
        "sb": CALIBRATION_DETECTOR_CHESSBOARD_SB,
        "chessboard_sb": CALIBRATION_DETECTOR_CHESSBOARD_SB,
        "classic": CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC,
        "chessboard_classic": CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC,
        "findchessboardcorners": CALIBRATION_DETECTOR_CHESSBOARD_CLASSIC,
        "charuco": CALIBRATION_DETECTOR_CHARUCO,
        "aruco": CALIBRATION_DETECTOR_CHARUCO,
    }
    return aliases.get(normalized, CALIBRATION_DETECTOR_AUTO)
