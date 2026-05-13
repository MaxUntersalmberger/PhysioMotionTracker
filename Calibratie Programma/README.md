# Calibratie Programma

Nieuw, apart programma voor de aangepaste projectscope: camera's openen, calibratieframes verzamelen, intrinsics/extrinsics oplossen, resultaten beoordelen en calibratieprofielen exporteren. Dit programma stopt bij calibratie.

De bestaande map `Programma Structuur` wordt niet aangepast door deze app. Voor camera-IO, OpenCV-calibratie en gedeelde datamodellen gebruikt dit programma die bestaande code alleen als lokale bibliotheek.

## Tabbladen

1. Home
   - Nieuw calibratieproject maken.
   - Bestaand calibratieproject openen.

2. Cameras + Calibration
   - Camera's of videobronnen proben/starten.
   - Live preview met calibratie-overlay.
   - Calibratieobject, board-grootte, square size en detector kiezen.
   - Goede frames handmatig of automatisch capturen.
   - Intrinsics en extrinsics oplossen.

3. Results + Export
   - Calibratieprofiel laden/opslaan.
   - Acceptatiescore bekijken.
   - Versioned export maken.

Voor de Qt Designer-koppeling staat er een kort overzicht in [GUI_KOPPELING.md](GUI_KOPPELING.md).

## Run

Voor teamgenoten is dit de makkelijkste manier:

1. Open de map `Calibratie Programma`.
2. Dubbelklik op `Start-Calibratie.bat`.
3. De eerste keer maakt het script automatisch een lokale `.venv` aan en installeert het de benodigde packages.

Het script installeert `opencv-contrib-python`, omdat ChArUco-detectie `cv2.aruco` nodig heeft.

Voor een snelle test zonder GUI:

```powershell
.\Start-Calibratie.bat -SmokeTest
```

Handmatig kan ook nog steeds:

```bash
py -m pip install -r requirements.txt
py run.py --smoke-test
py run.py --ui
```

Andere nuttige checks:

```bash
py run.py --capture-sample --sources 0
py run.py --project-summary projects/<project>
py run.py --profile-summary projects/<project>/calibration/current_calibration.json
```
