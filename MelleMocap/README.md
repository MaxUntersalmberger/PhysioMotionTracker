# Mocap Studio (PySide6) - Honest MVP

Serious desktop MVP for multi-camera markerless mocap workflows:
- live multi-camera capture
- calibration (checkerboard + Charuco when available)
- reconstruction diagnostics
- session recording and playback

This README is intentionally explicit about what is trustworthy today and what is not.

## What Is Truly Usable Now

1. Live preview from 1-4 camera sources with responsive UI.
2. Capture/Calibration/Reconstruction/Analysis tabs with focused workflows.
3. Runtime workload controls:
   - capture FPS
   - preview FPS
   - preview max width
   - calibration detection frequency
   - overlays on/off
   - detection on/off per workspace mode
4. Calibration sample capture with quality gating:
   - coverage and quality checks
   - image-size consistency checks
   - sample novelty checks (reject near-duplicates)
5. Intrinsics solve with reprojection error reporting:
   - checkerboard via `cv2.calibrateCamera`
   - Charuco via `cv2.aruco.calibrateCameraCharuco` (if available)
6. Undistortion preview per camera.
7. Synchronized multi-camera extrinsics solve relative to a reference camera.
8. Analysis workspace with session summaries, kinematic metric plots, and JSON report export.
9. Reconstruction status that is explicit about trustworthiness.
10. Performance diagnostics panel with timings and queue-drop metrics.

## What Is Not Yet Production-Ready

1. Placeholder 2D detector is still present as a fallback when MediaPipe is not installed.
2. No non-linear bundle adjustment/refinement yet.
3. No robust multi-person identity tracking yet.
4. Analysis exports are currently JSON-only (no BVH/C3D yet).

The app will now report these limitations instead of silently faking reliable 3D.

## Installation

```bash
pip install -r requirements.txt
```

Optional:
- install MediaPipe for real 2D landmarks
- install `opencv-contrib-python` for full Charuco support (`cv2.aruco`)

### MediaPipe on Newer Python/Packages

Recent `mediapipe` builds can expose only the Tasks API (without `mp.solutions`).
This app supports both:
- legacy `mediapipe.solutions.pose`
- newer `mediapipe.tasks` Pose Landmarker

When Tasks mode is used, the app now first looks in the project itself:
- `CoDeX6_MEGA/models/pose_landmarker_full.task`
- `CoDeX6_MEGA/models/pose_landmarker_lite.task`

Or set environment variable:
- `MOCAP_POSE_MODEL_PATH=<absolute-path-to-task-model>`

If no local `.task` file is found, the app will automatically download a Pose Landmarker model into the project's `models` folder.

## Run

```bash
python run.py
```

## Recommended Workflow

### 1) Capture
1. Open `Capture` tab.
2. Set camera sources (`0,1` etc.).
3. Start with conservative settings:
   - preview width `1280` or `960`
   - capture FPS `20`
   - preview FPS `20-30`
4. Press `Start Live`.

### 2) Calibration
1. Open `Calibration` tab.
2. Choose `Chessboard` or `Charuco` pattern.
3. Move board through diverse positions/angles/depths.
4. Press `Capture Valid Sample(s)` repeatedly.
5. Solve intrinsics and inspect per-camera reprojection errors.
6. Save profile JSON.
7. Run `Solve Extrinsics` after you have several synchronized shared-board captures.

### 3) Reconstruction
1. Open `Reconstruction` tab.
2. Ensure diagnostics show:
   - calibration loaded
   - detector active (prefer real detector, not placeholder)
   - reconstruction mode `real_calibrated` only when extrinsics are valid
3. If extrinsics are missing, expect `unavailable` status (by design).

### 4) Analysis
1. Load a recorded session.
2. Play/pause/step and scrub timeline.
3. Inspect kinematic summaries and metric plots.
4. Export a JSON report when needed.

## Trust States (Important)

Use diagnostics + status panel as source of truth:
- `unavailable`: real 3D cannot be trusted/produced (typically missing calibration/extrinsics)
- `disabled`: detection intentionally off for this workspace mode
- `real_calibrated`: triangulation attempted with calibration
- `placeholder_fallback`: debug-only synthetic fallback (should not be treated as real mocap)

Also verify detector:
- `mediapipe_pose`: real landmark detector
- `mediapipe_tasks_pose`: real landmark detector
- `placeholder_pose`: synthetic/debug detector only

## Architecture Overview

- `mocap_app/core`: config and logging
- `mocap_app/models`: typed shared data contracts
- `mocap_app/io`: calibration/session persistence
- `mocap_app/pipeline`: detection, matching, triangulation, smoothing
- `mocap_app/workers`: capture, playback, async pipeline worker
- `mocap_app/ui`: tabbed workflow UI + diagnostics/logging widgets

## Current TODO Hooks

1. Bundle-adjustment / non-linear refinement.
2. Better calibration diagnostics (coverage heatmaps, epipolar residual plots).
3. Export pipeline (CSV/BVH/C3D) and richer analysis plots.
