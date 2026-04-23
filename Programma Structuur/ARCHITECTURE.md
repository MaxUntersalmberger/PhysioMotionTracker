# Programma Structuur Architecture Brief

This document defines the clean starting point for the new motion capture project.

The goal is to build one maintainable desktop application, not a monolith with hidden coupling and not a service mesh. Keep the first version in a single process, but separate responsibilities aggressively.

## Target Architecture

Use these layers consistently:

1. Domain
   - Core data contracts and value objects.
   - No Qt, no OpenCV, no filesystem access.

2. Application
   - Workflow controllers and use cases.
   - Example responsibilities: start capture, solve calibration, manage sessions, run analysis.
   - Must be testable without the UI.

3. Infrastructure
   - Camera IO, serialization, video codecs, external model adapters, file handling.
   - This is where OpenCV, NumPy, JSON, and external SDKs live.

4. Presentation
   - UI shell, widgets, visualization, and user interaction.
   - Only render state and emit user intent.

5. Runtime
   - Thread workers, scheduling, backpressure, and batching policy.
   - No business rules here.

## Folder Responsibilities

### `app`

- Application bootstrap
- Dependency wiring
- Controller orchestration
- App-wide configuration and logging

### `workers`

- Background threads
- Capture to pipeline handoff
- Bounded queues and latest-frame policy
- UI-safe signal emission

### `capture`

- Camera discovery
- Live capture
- Frame normalization
- Batch submission to the pipeline

### `calibration`

- Chessboard and Charuco workflows
- Intrinsics solving
- Extrinsics solving
- Calibration profile persistence

### `detectors`

- 2D detector interfaces
- Pose landmark extraction
- Detector adapters for different backends

### `tracking`

- Temporal smoothing
- Identity persistence across frames
- Trajectory cleanup and state estimation

### `reconstruction`

- Multi-camera triangulation
- Calibration-aware trust states
- Reprojection diagnostics

### `fitting`

- Subject-specific model fitting
- Constraints and optimization hooks

### `biomechanics`

- Joint angles
- Segment metrics
- Movement summaries

### `exporters`

- BVH, C3D, CSV, JSON, and future formats
- Session export pipelines

### `batch`

- Offline processing of recordings and datasets
- Headless workflows for repeatable jobs

### `plugins`

- Discovery and registration of extensions
- Detector, exporter, and analysis plugin contracts

### `ui`

- Main window shell
- Workspaces and panels
- Visualization only

## Non-Negotiable Performance Rules

- Never block the UI thread with capture, detection, or export work.
- Keep queues bounded and prefer latest-frame processing over backlog accumulation.
- Minimize frame copies.
- Measure latency at every stage.
- Make drops, fallbacks, and degraded modes explicit in the UI.

## What To Build First

The first implementation should focus on the smallest useful slice:

1. Shared data contracts.
   - Frame packet
   - Pose 2D and Pose 3D
   - Calibration bundle
   - Session manifest

2. Config and logging.
   - App settings
   - Paths
   - Diagnostics logging

3. Capture pipeline.
   - Multi-camera frame acquisition
   - Bounded worker thread
   - Clear shutdown behavior

4. Detector and reconstruction pipeline.
   - Detector interface
   - Matching
   - Triangulation
   - Smoothing

5. Session persistence.
   - Recording
   - Loading
   - Playback metadata

6. UI shell.
   - Tabs or workspaces
   - Status panels
   - Visualization widgets

## What Not To Do Yet

- Do not put logic in the main window that belongs in controllers.
- Do not add plugins before the core workflows are stable.
- Do not introduce a web backend until the desktop core is reliable.
- Do not grow a single class into a second god object.

## Good First Milestone

The first milestone is reached when:

- live capture works with at least one camera source
- a detector can produce stable 2D landmarks
- a reconstruction path exists even if it starts simple
- calibration can be saved and loaded
- the UI shows clear trust states and timing metrics

That gives you a solid base for everything else.