# Programma Structuur

Dit is het nieuwe startpunt voor de mocap-applicatie.

We beginnen opnieuw en bouwen hier een schone, modulaire codebasis op. De oude poging is geen basis om verder op door te bouwen.

## Richting

- Desktop-first motion capture applicatie.
- Modulaire architectuur met duidelijke grenzen tussen domein, verwerking, opslag en UI.
- Snel genoeg voor live gebruik, zonder verborgen queues of zware UI-logica.
- Expliciete trust states voor calibratie, detectie en reconstructie.

## Eerste Modulengroepen

- `app`: opstart, configuratie en workflow-orkestratie.
- `workers`: achtergrondthreads en queue-bridges voor capture en pipeline.
- `capture`: camera- en sensorinname.
- `calibration`: intrinsics, extrinsics en kalibratieprofielen.
- `detectors`: 2D-detectie via MediaPipe met synthetische fallback.
- `tracking`: temporele stabilisatie en identiteit over frames.
- `reconstruction`: 3D-reconstructie uit meerdere bronnen.
- `fitting`: model fitting en subject-specifieke aanpassing.
- `biomechanics`: biomechanische afgeleiden en metriek.
- `exporters`: export naar bestandsformaten en datasets.
- `batch`: offline verwerking van sessies en datasets.
- `plugins`: uitbreidbare detector-, exporter- en analyseplug-ins.
- `ui`: schermen, widgets, visualisatie, camera-selectie, detector-switch, live preview, keypoint overlays en camera grid.
- `ui`: schermen, widgets, visualisatie, camera-selectie, detector-switch, live preview, calibration workflow, keypoint overlays en camera grid.

## Principes

1. Geen businesslogica in de UI.
2. Geen camera- of bestandstoegang op de UI-thread.
3. Workers doen alleen threadwerk en data-overdracht.
4. Pipeline-stappen blijven los van Qt.
5. Alle belangrijke status moet zichtbaar en testbaar zijn.

## Volgorde Van Bouwen

1. Domeinmodellen en configuratie.
2. Capture en pipeline-kern.
3. Kalibratie en sessie-opslag.
4. Reconstructie en tracking.
5. Analyse en export.
6. UI-shell en polish.
7. Plugins en batchverwerking.

## Run

Install the desktop dependencies first:

```bash
py -m pip install -r requirements.txt
```

```bash
py run.py --smoke-test
py run.py --demo-pipeline
py run.py --capture-sample --sources 0
py run.py --ui
py run.py --session-summary sessions/session_YYYYMMDD_HHMMSS
py run.py --reprocess-session sessions/session_YYYYMMDD_HHMMSS --detector synthetic --max-batches 0
py run.py --process-session sessions/session_YYYYMMDD_HHMMSS --detector synthetic --max-batches 0
py run.py --analyze-take sessions/session_YYYYMMDD_HHMMSS/processed/motion_take.json
py run.py --export-session sessions/session_YYYYMMDD_HHMMSS --detector synthetic --export-formats json,csv --max-batches 0
```

`--smoke-test` controleert alleen of de basis opstart.
`--demo-pipeline` draait een synthetische capture/detectie/reconstructie-keten zonder echte camera.
`--capture-sample` opent echte bronnen met OpenCV en leest één batch in.
`--ui` start de Qt-shell met probe-, capture-, calibration-, live preview-, overlay-, camera-grid- en pipeline-koppeling.
`--session-summary` controleert of een opgenomen sessie terugleesbaar is.
`--reprocess-session` speelt een opgenomen sessie opnieuw door de pipeline; `--max-batches 0` verwerkt alles.
`--process-session` verwerkt een opgenomen sessie naar een interne `processed/motion_take.json`, bedoeld als werkobject voor review, analyse, IK en latere exports.
`--analyze-take` berekent de eerste interne joint-angle analyse vanuit een processed motion take en schrijft `processed/analysis/joint_angles.json`.
`--export-session` speelt een opgenomen sessie opnieuw door de pipeline en schrijft pose-data naar JSON en CSV.

De live UI gebruikt MediaPipe als 2D-pose-detector wanneer het modelbestand beschikbaar is.
In het capture-paneel kun je wisselen tussen MediaPipe, de synthetische demo-detector en een detectie-uit stand.

De gekozen detector wordt opgeslagen in `programmastructuur.config.json` en bij de volgende start hersteld.
Het capture-paneel kan nu resolutie, FPS, exposure, gain en white balance aanvragen; OpenCV rapporteert per probe welke controls zijn toegepast.
De camera grid toont per-camera health met FPS-indicatie en drop counts.

De calibratie-workflow in de live UI werkt met chessboard-samples: capture samples, solve intrinsics, solve extrinsics, en sla de bundle op als `calibration/current_calibration.json`.
Als dat bestand aanwezig is, wordt het bij opstart automatisch geladen.
Tijdens sample capture controleert de UI of de board in meerdere camera's zichtbaar is en of de batch synchroon genoeg is om als calibratiesample te gebruiken.
De live preview tekent de gedetecteerde chessboard-corners per camera en de camera grid laat zien welke bronnen de board op dat moment zien.
De calibratie-tab splitst de workflow nu expliciet in `Intrinsics` en `Sync / Extrinsics`: intrinsics slaat per-camera lenssamples op, extrinsics slaat alleen gesynchroniseerde multi-camera board-sets op.
Auto-capture kan geldige frames automatisch opslaan wanneer de live kwaliteit en synchronisatie voldoende zijn, met een instelbare cooldown.
De solve-acties gebruiken readiness gates: intrinsics vraagt genoeg per-camera samples, extrinsics vraagt opgeloste intrinsics plus genoeg gesynchroniseerde sets.
Na het oplossen van extrinsics verfijnt OpenCV `stereoCalibrate` de camera-paren met vaste intrinsics en schrijft pair-RMS en bundle-adjustment metadata in de calibratiebundle.
Wanneer een calibratiebundle met geldige intrinsics én extrinsics aanwezig is, schakelt de live reconstructie over naar echte multi-view triangulatie.
Zonder zo'n bundle blijft reconstructie bewust unavailable in plaats van een nep-3D resultaat te tonen.
De calibrated triangulator gebruikt nu confidence-weighted multi-view DLT, per-joint outlier rejection, missing-joint rapportage en een 3D trust-score voor de pipeline status.
Calibratiebundles krijgen nu acceptance metadata, epipolar pair readiness en versie-informatie; Charuco-detectie wordt gebruikt wanneer de OpenCV build `cv2.aruco` ondersteunt.

De Session-tab ondersteunt nu een eerste echte recording lifecycle: start recording, stop recording, per-camera video-opslag, een `frames.jsonl` tijdlijn en manifest-metadata voor reproduceerbare offline verwerking. Opgenomen sessies kunnen headless worden teruggelezen en opnieuw door de pipeline worden verwerkt.
De Review-tab kan een opgenomen sessie laden, met een frame-slider door de recorded batches stappen, de huidige recorded frame direct opnieuw door de pipeline halen voor 2D/3D overlays en de volledige sessie verwerken naar een interne motion take.
Tijdens recording worden disk/resource snapshots opgeslagen in het session manifest.
Verwerkte sessies worden opgeslagen als `processed/motion_take.json`; dat bestand bevat 2D pose, 3D pose wanneer calibratie beschikbaar is, pipeline metadata en placeholders voor inverse kinematics en joint angles.
De Analysis-tab kan een processed take laden, per-frame/per-joint reconstructiewaarden tonen en joint-angle curves samenvatten voor knieën, heupen, ellebogen en schouders wanneer 3D keypoints beschikbaar zijn.
Opgenomen sessies kunnen via CLI of Review-tab worden geexporteerd naar `pose_export.json`, `pose_2d.csv`, `pose_3d.csv` en een `export_manifest.json`.

Zie [ARCHITECTURE.md](ARCHITECTURE.md) voor de concrete modulegrenzen en de aanbevolen eerste implementatiestappen.
Zie [PROFESSIONAL_BACKLOG.md](PROFESSIONAL_BACKLOG.md) voor de volledige professionele product-backlog en status.

Wijzigingen worden bijgehouden in [CHANGELOG.md](CHANGELOG.md).
