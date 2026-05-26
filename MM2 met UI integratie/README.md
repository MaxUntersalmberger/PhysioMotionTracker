# Camera Calibration

PySide6 desktopapp voor camera-kalibratie. De applicatie is bewust ingeperkt tot:

- live preview van 1-4 camera- of videobronnen
- live preview in losse grotere vensters per camera
- optionele detectie-overlay zodat live preview sneller kan blijven
- camera detectie/scannen
- checkerboard- en Charuco-detectie wanneer OpenCV dat ondersteunt
- expliciete board-instellingen voor chessboard en ChArUco
- intrinsics sample capture met kwaliteitscontrole
- instelbare quality- en coverage-thresholds voor intrinsics en sync capture
- intrinsics solve met reprojection error
- undistortion preview per camera
- gesynchroniseerde multi-camera extrinsics solve
- kalibratieprofielen laden en opslaan als JSON
- een nieuw project starten om alle actieve kalibratie te vergeten
- JSON-profielen bevatten units en validatiehints in `metadata.units` en `metadata.validation_guidance`
- JSON-profielen bevatten sample-verzameltijd in `metadata.sample_collection`

Opname, mocap-reconstructie, pose-detectie, sessie-playback en analyse zijn niet meer bereikbaar vanuit de app.

## Installatie

```bash
pip install -r requirements.txt
```

Optioneel:

- installeer `opencv-contrib-python` voor volledige Charuco-ondersteuning (`cv2.aruco`)

## Starten

```bash
python run.py
```

## Workflow

1. Vul `Sources (CSV)` in, bijvoorbeeld `0,1`.
2. Klik `Detect Cameras` als je de beschikbare webcams wilt zoeken.
3. Kies FPS, resolutie en detectiefrequentie.
4. Klik `Start Live`.
5. Kies `Chessboard` of `Charuco`.
6. Vul de echte board-instellingen in en klik `Apply Board Settings`.
7. Beweeg het kalibratiebord door verschillende posities, hoeken en afstanden.
8. Klik `Capture Intrinsics Sample(s)` of zet `Auto Capture Valid Samples` aan.
9. Je kunt auto-capture ook starten met `Start Auto` op een camera-preview of pop-out.
10. Stel eventueel `Max Samples` in om auto-capture vanzelf te laten stoppen.
11. Verlaag eventueel `Intrinsics Min Quality` of `Intrinsics Min Coverage` als captures te streng worden afgekeurd.
12. Klik `Solve Intrinsics`.
13. Gebruik `Sync / Extrinsics` en `Solve Extrinsics` voor multi-camera extrinsics.
14. Sla het profiel op met `Save Profile`.
15. Zet `Show Detection Overlay` uit als de live preview sneller moet blijven reageren.
16. Klik `Open Window` op een camera-preview als je de feed groter in een los venster wilt zien.
17. Klik `New Project` om samples, geladen kalibratie en de automatisch herlaadde huidige kalibratie te wissen.

## Projectstructuur

- `mocap_app/core`: configuratie en logging
- `mocap_app/io/calibration_io.py`: kalibratie detectie, solve en JSON-profielen
- `mocap_app/workers`: live capture en camera scan workers
- `mocap_app/ui`: kalibratie-only desktop UI
