# Change Log

Dit bestand houdt de aanpassingen aan Programma Structuur bij.

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









