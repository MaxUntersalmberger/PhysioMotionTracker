# Change Log

Dit bestand houdt de aanpassingen aan Programma Structuur bij.

## 2026-05-07

- Calibratie-readiness toegevoegd: intrinsics en extrinsics solve-acties melden nu wanneer samples, intrinsics of sync-sets nog ontbreken.
- Extrinsics-solve verfijnt opgeloste camera-paren nu met OpenCV `stereoCalibrate` en vaste intrinsics.
- Calibratiebundles krijgen bundle-adjustment metadata met status, methode, pair-RMS en refinement-notes.
- Calibratie-tab opgeschoond naar compacte capture-status plus readiness.
- Regressietests toegevoegd voor workflow-readiness en refinement metadata.
- Review-tab uitgebreid met `Export Poses`, zodat loaded recorded sessions vanuit de UI naar JSON/CSV kunnen worden geschreven.
- Pose-export draait via een achtergrondworker en schrijft standaard naar de `exports` map van de sessie.
- Interne motion-take laag toegevoegd: recorded sessions kunnen nu naar `processed/motion_take.json` worden verwerkt.
- Review-tab uitgebreid met `Process Session`, bedoeld als hoofdflow voor verdere analyse, inverse kinematics en latere exports.
- CLI-optie `--process-session` toegevoegd voor dezelfde interne processed-session stap.
- Regressietest toegevoegd voor motion-take roundtrip opslag.
- Analysis-tab toegevoegd voor processed motion takes.
- Eerste joint-angle analyse toegevoegd voor knie, heup, elleboog en schouder vanuit 3D keypoints.
- CLI-optie `--analyze-take` toegevoegd voor joint-angle analyse naar `processed/analysis/joint_angles.json`.
- Regressietest toegevoegd voor joint-angle berekening en opslag.
- Calibrated 3D reconstructie robuuster gemaakt met confidence-weighted DLT over meerdere views.
- Per-joint outlier rejection, missing-joint notes, view counts, confidence en reconstruction trust-score toegevoegd.
- Pipeline Status toont nu de 3D trust-state.
- Regressietest toegevoegd voor outlier rejection in calibrated triangulation.
- Analysis-tab toont nu ook detailwaarden uit `motion_take.json`: per-frame trust/error en per-joint xyz/confidence/view-count/reprojection-error.
- Joint-angle analyse toont nu naast summaries ook de onderliggende angle samples in de UI.
- Review- en Analysis-controls responsiever gemaakt: knoppen staan nu in grids en lange paden/statusregels staan in scrollbare tekstvakken.

## 2026-05-06

- Eerste headless pose-export toegevoegd:
  - `exporters/pose_export.py`
  - `--export-session` CLI met JSON/CSV-output
  - `pose_export.json`, `pose_2d.csv`, `pose_3d.csv` en `export_manifest.json`
- Regressietest toegevoegd voor recorded session export naar JSON/CSV.
- Backlog bijgewerkt: CSV/JSON pose export staat nu als eerste exportstap op done.
- Calibratie-capture gesplitst in `Intrinsics` en `Sync / Extrinsics`.
- Auto-capture toegevoegd voor calibratieframes die live voldoende kwaliteit/synchronisatie halen.
- Regressietest toegevoegd die controleert dat intrinsics samples en extrinsics sync-sets gescheiden worden opgeslagen.

## 2026-04-23

- Extrinsics-calibratie gefixt: camera's met opgeloste intrinsics worden nu correct meegenomen bij het oplossen van rotation/translation.
- Regressietest toegevoegd voor intrinsics-only calibration bundles in `tests/test_calibration_manager.py`.
- Session recording toegevoegd: live capture kan nu per camera naar video schrijven met een `frames.jsonl` tijdlijn en manifest-metadata.
- Recording-worker toegevoegd zodat video-opslag buiten de UI-thread gebeurt.
- Regressietest toegevoegd voor session recording zonder echte camera.
- Session playback toegevoegd: manifest + recorded videos + `frames.jsonl` kunnen terug naar `CaptureBatch` worden gelezen.
- CLI toegevoegd voor `--session-summary` en `--reprocess-session`.
- Regressietest toegevoegd voor playback en offline re-processing.
- Camera controls toegevoegd voor resolutie, FPS, exposure, gain en white balance waar OpenCV/backend dit ondersteunt.
- Camera profiles, sync assessment, camera health en resource snapshots toegevoegd.
- Calibratie acceptance score, epipolar readiness diagnostics en version metadata toegevoegd.
- Charuco-detectiepad toegevoegd wanneer `cv2.aruco` beschikbaar is.
- Detector registry, detector capabilities, confidence policy, null detector en occlusion reporting toegevoegd.
- Regressietest toegevoegd voor camera/calibration/detector foundation.
- Review-tab toegevoegd voor opgenomen sessies met frame-slider en recorded frame preview.
- Random-access playback toegevoegd aan de session playback reader.
- Review-tab kan nu de huidige recorded frame opnieuw door de pipeline halen en keypoint/reprojection overlays cachen per frame.
- Stateless review batch helper toegevoegd zodat recorded review geen smoothing-state uit de live pipeline overneemt.

## 2026-04-14

- Nieuwe projectbasis opgezet in Programma Structuur.
- `README.md` herschreven als nieuw startpunt.
- `ARCHITECTURE.md` toegevoegd met modulegrenzen en bouwvolgorde.
- Eerste Python-skeleton toegevoegd:
  - `run.py`
  - `app/main.py`
  - `app/bootstrap.py`
- Configuratie en logging toegevoegd:
  - `core/config.py`
  - `core/logging.py`
- Eerste domeinmodellen toegevoegd:
  - `models/types.py`
  - `models/__init__.py`
- Eerste workflow-state objecten toegevoegd:
  - `capture/state.py`
  - `calibration/state.py`
  - `session/state.py`
  - `reconstruction/state.py`
- Eerste pipeline-contracten toegevoegd:
  - `pipeline/contracts.py`
  - `pipeline/__init__.py`
- Eerste UI package stub toegevoegd:
  - `ui/__init__.py`
- Smoke test uitgevoerd met succes via `run.py`.



- Capture sources parser toegevoegd:
  - `capture/sources.py`
- Eerste detector- en trackinglaag toegevoegd:
  - `detectors/contracts.py`
  - `detectors/placeholder.py`
  - `tracking/matcher.py`
  - `tracking/smoother.py`
- Eerste reconstructielaag toegevoegd:
  - `reconstruction/triangulation.py`
  - `reconstruction/__init__.py`
- Eerste pipeline manager en demo-run toegevoegd:
  - `pipeline/manager.py`
  - `app/demo.py`
  - `--demo-pipeline` CLI flag in `app/main.py`
- Demo pipeline uitgevoerd met succes via `run.py --demo-pipeline`.





- Root `.gitignore` toegevoegd voor Python caches en runtime output:
  - `__pycache__/`
  - `*.pyc`
  - `logs/`, `sessions/`, `exports/`
- Real OpenCV capture layer toegevoegd:
  - `capture/backend.py`
  - `CaptureBatch` en `OpenCVCaptureSession`
  - `describe_capture_batch()` voor CLI-output
- Capture sample CLI toegevoegd:
  - `--capture-sample` in `app/main.py`
- Eigen dependency-lijst toegevoegd:
  - `requirements.txt`
- Runtime workers toegevoegd voor streaming:
  - `workers/capture_worker.py`
  - `workers/pipeline_worker.py`
  - `workers/__init__.py`

  

- Qt-shell toegevoegd:
  - `ui/main_window.py`
  - `ui/widgets/capture_panel.py`
  - `ui/widgets/pipeline_status.py`
  - `ui/widgets/frame_preview.py`
  - `ui/widgets/camera_grid.py`
  - `ui/widgets/__init__.py`
  - `app/ui.py`
  - `workers/camera_probe_worker.py`
- `--ui` CLI flag toegevoegd in `app/main.py`.



- Live preview viewport en per-camera bronselectie toegevoegd in de Qt shell.
- Camera grid toegevoegd naast de live preview.
- 2D keypoint overlays toegevoegd op de live preview.
- MediaPipe pose detector toegevoegd als live 2D backend.
- Live UI schakelt standaard naar MediaPipe met synthetische fallback.
- Detector-switch toegevoegd in het capture-paneel om tussen MediaPipe en de synthetische demo te wisselen.
- Detectorvoorkeur wordt nu opgeslagen in `programmastructuur.config.json` en hersteld bij opstart.
- Scrollarea toegevoegd rond de shell zodat de onderste UI bereikbaar is op kleinere schermen.
- Output- en logvelden scrollen nu automatisch naar de nieuwste regel.
- Calibratiepaneel toegevoegd voor chessboard-samples, intrinsics, extrinsics en profielopslag.
- Guided sample capture toegevoegd met camera-sync checks en zichtbaarheidfeedback voor het chessboard.
- Live preview tekent nu gedetecteerde chessboard-corners per camera, en de camera grid toont welke views de board op dat moment zien.
- Calibratieprofielen worden geladen en opgeslagen via `calibration/current_calibration.json` of via de profielknoppen.
- Een bestaand calibratieprofiel wordt nu automatisch geladen bij opstart.
- Live reconstructie gebruikt nu een echte calibrated triangulator wanneer een geldige calibratiebundle aanwezig is.
- De demo-pipeline blijft synthetisch voor smoke tests en voorbeeldruns.


- Calibratiepaneel is verder uitgewerkt tot een wizard met per-camera quality scores en sample history.
- De wizard laadt de standaard calibratiebundle nu bij opstart en toont live kwaliteit/historie vanuit de actuele batches.
- De GUI is nu opgedeeld in tabbladen voor Capture, Live View, Calibration en Diagnostics.
- Session persistence is toegevoegd met een JSON session repository en een nieuwe Session-tab om sessies op te slaan en te laden.
- Capture en Calibration tonen nu ook een compacte live preview, zodat de live view en calibratie-overlay in de workflow-tabs zelf zichtbaar zijn.









