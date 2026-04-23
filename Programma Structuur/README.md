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
```

`--smoke-test` controleert alleen of de basis opstart.
`--demo-pipeline` draait een synthetische capture/detectie/reconstructie-keten zonder echte camera.
`--capture-sample` opent echte bronnen met OpenCV en leest één batch in.
`--ui` start de Qt-shell met probe-, capture-, calibration-, live preview-, overlay-, camera-grid- en pipeline-koppeling.

De live UI gebruikt MediaPipe als 2D-pose-detector wanneer het modelbestand beschikbaar is.
In het capture-paneel kun je wisselen tussen MediaPipe en de synthetische demo-detector.

De gekozen detector wordt opgeslagen in `programmastructuur.config.json` en bij de volgende start hersteld.

De calibratie-workflow in de live UI werkt met chessboard-samples: capture samples, solve intrinsics, solve extrinsics, en sla de bundle op als `calibration/current_calibration.json`.
Als dat bestand aanwezig is, wordt het bij opstart automatisch geladen.
Tijdens sample capture controleert de UI of de board in meerdere camera's zichtbaar is en of de batch synchroon genoeg is om als calibratiesample te gebruiken.
De live preview tekent de gedetecteerde chessboard-corners per camera en de camera grid laat zien welke bronnen de board op dat moment zien.
Wanneer een calibratiebundle met geldige intrinsics én extrinsics aanwezig is, schakelt de live reconstructie over naar echte multi-view triangulatie.
Zonder zo'n bundle blijft reconstructie bewust unavailable in plaats van een nep-3D resultaat te tonen.

Zie [ARCHITECTURE.md](ARCHITECTURE.md) voor de concrete modulegrenzen en de aanbevolen eerste implementatiestappen.

Wijzigingen worden bijgehouden in [CHANGELOG.md](CHANGELOG.md).
