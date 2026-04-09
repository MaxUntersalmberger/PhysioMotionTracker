# Programma Structuur

Dit is de eerste opzet van de modulaire mocap-softwarestructuur.

- `app`: kern van de applicatie, opstart en algemene orkestratie.
- `ui`: gebruikersinterface en schermen voor alle workflows.
- `capture`: inname van camera- en sensordata.
- `calibration`: kalibratieprocessen voor camera's en systeeminstellingen.
- `detectors`: detectiecomponenten voor lichaamspunten en features.
- `tracking`: trackinglogica over tijd voor stabiele bewegingsreeksen.
- `reconstruction`: reconstructie van 3D-gegevens uit meerdere bronnen.
- `fitting`: model fitting en afstemming op subjectspecifieke data.
- `biomechanics`: biomechanische analyses en afgeleide metrieken.
- `exporters`: exportlogica naar ondersteunde formaten.
- `batch`: batchverwerking voor meerdere opnames of datasets.
- `plugins`: uitbreidbaar pluginsysteem voor detector-, exporter- en analysemodules.
