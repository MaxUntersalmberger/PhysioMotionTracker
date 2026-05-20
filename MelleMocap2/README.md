# Camera Calibration

PySide6 desktopapp voor camera-kalibratie. De applicatie is bewust ingeperkt tot:

- live preview van 1-4 camera- of videobronnen
- live preview in losse grotere vensters per camera
- optionele detectie-overlay zodat live preview sneller kan blijven
- camera detectie/scannen
- checkerboard- en Charuco-detectie wanneer OpenCV dat ondersteunt
- intrinsics sample capture met kwaliteitscontrole
- instelbare quality- en coverage-thresholds voor intrinsics en sync capture
- intrinsics solve met reprojection error
- undistortion preview per camera
- gesynchroniseerde multi-camera extrinsics solve
- kalibratieprofielen laden en opslaan als JSON
- een nieuw project starten om alle actieve kalibratie te vergeten

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
6. Beweeg het kalibratiebord door verschillende posities, hoeken en afstanden.
7. Klik `Capture Intrinsics Sample(s)` of zet `Auto Capture Valid Samples` aan.
8. Verlaag eventueel `Intrinsics Min Quality` of `Intrinsics Min Coverage` als captures te streng worden afgekeurd.
9. Klik `Solve Intrinsics`.
10. Gebruik `Sync / Extrinsics` en `Solve Extrinsics` voor multi-camera extrinsics.
11. Sla het profiel op met `Save Profile`.
12. Zet `Show Detection Overlay` uit als de live preview sneller moet blijven reageren.
13. Klik `Open Window` op een camera-preview als je de feed groter in een los venster wilt zien.
14. Klik `New Project` om samples, geladen kalibratie en de automatisch herlaadde huidige kalibratie te wissen.

## Projectstructuur

- `mocap_app/core`: configuratie en logging
- `mocap_app/io/calibration_io.py`: kalibratie detectie, solve en JSON-profielen
- `mocap_app/workers`: live capture en camera scan workers
- `mocap_app/ui`: kalibratie-only desktop UI
