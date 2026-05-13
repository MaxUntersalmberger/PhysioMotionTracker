# GUI Koppeling Voor Qt Designer

Dit document is bedoeld voor de GUI-groep. De huidige placeholder-GUI staat in `calibration_app/main_window.py` en `calibration_app/widgets.py`. Jullie kunnen de Designer-UI hierop aansluiten door dezelfde signals/slots te gebruiken of door de functies in `CalibrationMainWindow` als referentie-controller te houden.

## Basis

Startpunt:

- `Start-Calibratie.bat` is de makkelijke starter voor teamgenoten; deze maakt automatisch een lokale `.venv` en start `run.py --ui`.
- `run.py` start `calibration_app.cli.run()`.
- `--ui` maakt `CalibrationMainWindow(CalibrationAppConfig.load())`.
- `CalibrationMainWindow` regelt project, camera-workers, calibratie-manager, preview en export.

Belangrijke backend-objecten:

- `CalibrationProjectRepository`: nieuw/open/save projectmanifest.
- `CalibrationRepository`: calibratieprofiel JSON laden/opslaan/exporteren.
- `CalibrationOnlyManager`: calibratie-instellingen, sample capture, intrinsics, extrinsics.
- `CameraProbeWorker`: camera's testen zonder live capture.
- `CaptureWorker`: camera/video live batches lezen.
- `CalibrationAnalysisWorker`: live frames analyseren voor board-detectie en auto-capture.

## Knoppen En Acties

| UI-knop / actie | Signal of slot in placeholder | Wat gebeurt er |
| --- | --- | --- |
| New Project | `HomeWidget.new_project_requested(name, sources_csv, fps)` -> `_on_new_project()` | Maakt projectmap + `calibration_project.json`, zet active project, gaat naar tab 2. |
| Open Project | `HomeWidget.open_project_requested` -> `_on_open_project()` | Laat map kiezen en laadt `calibration_project.json`. |
| Probe Sources | `CameraControlWidget.probe_requested(source_csv)` -> `_on_probe_requested()` | Parse bronnen en start `CameraProbeWorker`. Resultaat naar camera output/grid. |
| Capture Sample | `sample_requested(source_csv, fps)` -> `_on_sample_requested()` | Start `CaptureWorker` met `batch_limit=1`. |
| Start Live | `live_requested(source_csv, fps)` -> `_on_live_requested()` | Start doorlopende `CaptureWorker`. Frames gaan naar preview, grid en analysis worker. |
| Stop | `stop_requested` -> `_stop_capture_worker()` | Stopt live capture thread veilig. |
| Capture Intrinsics Sample / Extrinsics Sync Set | `capture_sample_requested` -> `_on_capture_calibration_requested()` | Neemt huidige of eerstvolgende batch en stuurt die naar `CalibrationAnalysisWorker(record_sample=True)`. |
| Solve Intrinsics | `solve_intrinsics_requested` -> `_on_solve_intrinsics()` | Checkt readiness en roept `CalibrationOnlyManager.solve_intrinsics()` aan. |
| Solve Extrinsics | `solve_extrinsics_requested` -> `_on_solve_extrinsics()` | Checkt readiness en roept `CalibrationOnlyManager.solve_extrinsics()` aan. |
| Load Profile | `load_profile_requested` -> `_on_load_profile()` | Opent JSON-profiel via `CalibrationRepository.load()`. |
| Save Profile | `save_profile_requested` -> `_on_save_profile()` | Slaat huidig profiel op via `CalibrationRepository.save()`. |
| Export Versioned Profile | `export_profile_requested` -> `_on_export_profile()` | Schrijft timestamped profiel naar project `exports/`. |
| Reset Samples | `reset_samples_requested` -> `_on_reset_samples()` | Leegt alleen sample history in de manager, niet het opgeslagen profiel. |

## Waarden Die De Designer-UI Moet Kunnen Leveren

Camera-controls:

- `sources_csv`: bijvoorbeeld `"0"` of `"0,1"` of videopad.
- `target_fps`
- optioneel: `requested_width`, `requested_height`, `requested_exposure`, `requested_gain`, `requested_white_balance`

Calibratie-controls:

- `calibration_object_type`: `"chessboard"` of `"charuco"`
- `calibration_detector_name`: `"auto"`, `"chessboard_sb"`, `"chessboard_classic"` of `"charuco"`
- `board_shape`: tuple `(columns, rows)`, standaard `(9, 6)`
- `square_size_m`: vakgrootte in meters, standaard `0.024`
- `capture_mode`: `"intrinsics"` of `"sync_extrinsics"`
- `auto_capture_enabled`
- `auto_capture_cooldown_sec`

Bij wijziging van object/detector/board/square size:

```python
_sync_calibration_settings()
_update_readiness()
```

## Resultaten Die De UI Moet Tonen

Live preview:

- `MultiCameraPreviewWidget.show_batch(batch, sources, probe_results)`
- `MultiCameraPreviewWidget.set_calibration_detections(result.detections)`
- `MultiCameraPreviewWidget.clear_preview(message)`
- `MultiCameraPreviewWidget.select_source(source_id)` selecteert alleen de highlight; alle actieve camera's blijven zichtbaar.

Camera grid:

- `CameraGridWidget.set_sources(sources, probe_results)`
- `CameraGridWidget.update_batch(batch, sources, probe_results)`
- `CameraGridWidget.set_calibration_detections(result.detections)`

Calibratie status:

- `result.sample_counts`
- `result.synchronized_samples`
- `result.camera_quality_scores`
- `manager.workflow_readiness()`
- `manager.sample_history`
- `result.notes`

Result/export tab:

- `CalibrationBundle` uit `_current_bundle`
- acceptance via `evaluate_calibration_bundle(bundle)`
- profielpad uit `_profile_path`

## Belangrijke Flow

1. Project openen of maken.
2. Bronnen invullen en `Probe Sources`.
3. `Start Live`.
4. Board zichtbaar maken; preview krijgt overlay via `CalibrationAnalysisWorker`.
5. Intrinsics samples capturen of auto-capture aanzetten.
6. `Solve Intrinsics`.
7. Switch naar `Sync / Extrinsics`, capture sync sets.
8. `Solve Extrinsics`.
9. Save/export profiel in `Results + Export`.

## Let Op

De methodes met `_` zijn nu controller-slots in de placeholder. Voor de uiteindelijke Designer-GUI mogen jullie dezelfde logica hergebruiken, of later nette publieke wrapper-methodes maken. Belangrijk is dat camera- en calibratiewerk in de worker-classes blijft en niet direct op de UI-thread draait.
