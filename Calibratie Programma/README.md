# Calibratie Programma

Nieuw, apart programma voor de aangepaste projectscope: camera's openen, calibratieframes verzamelen, intrinsics/extrinsics oplossen, resultaten beoordelen en calibratieprofielen exporteren. Dit programma stopt bij calibratie.

De bestaande map `Programma Structuur` wordt niet aangepast door deze app. Voor camera-IO, OpenCV-calibratie en preview-widgets gebruikt dit programma die bestaande code alleen als lokale bibliotheek.

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

<<<<<<< HEAD
Voor de Qt Designer-koppeling staat er een kort overzicht in [GUI_KOPPELING.md](GUI_KOPPELING.md).

=======
>>>>>>> 83e68c4 (Add standalone calibration program)
## Run

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
