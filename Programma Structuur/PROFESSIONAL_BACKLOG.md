# Professional Mocap Backlog

Dit document houdt de product-backlog bij voor het doel: een professioneel motion capture programma dat van setup tot export betrouwbaar werkt.

## Status

- Done: session recording basis met per-camera video, `frames.jsonl`, manifest-metadata en recording-worker.
- Done: extrinsics-fix zodat intrinsics-only bundles naar rotation/translation kunnen doorgroeien.
- Done: session playback en offline re-processing basis via CLI.
- Done: camera controls, camera profiles, camera health inputs, resource snapshots, calibration acceptance diagnostics en detector policy/registry basis.
- Done: UI-playback review-tab met random-access frame stepping.
- Done: review-tab kan recorded frames nu opnieuw door de pipeline halen met cached overlays.
- Done: eerste headless CSV/JSON pose export voor recorded sessions.
- Done: calibratie-workflow gesplitst in intrinsics samples en synchronized extrinsics sets met auto-capture gating.
- Done: eerste echte fixed-intrinsics stereo refinement na extrinsics solve.
- Done: Review-tab exporteert recorded sessions naar JSON/CSV.
- Done: interne `motion_take.json` als processed session werkobject voor review/analyse/IK.
- Done: eerste Analysis-tab met joint-angle analyse vanuit processed motion takes.
- Done: robuustere calibrated 3D reconstructie met weighted DLT, outlier rejection en trust-score.
- Next: inverse kinematics, globale multi-camera bundle adjustment, uitgebreidere detector backends en exportformaten.

## 1. Professionele Camera-Inname

- [x] Live multi-camera capture basis.
- [x] Per-camera video-opname vanuit live capture.
- [x] Dropped-source registratie per batch.
- [x] Camera discovery uitbreiden met device-profielen.
- [x] Resolutie, FPS, exposure, gain en white balance controls via OpenCV waar ondersteund.
- [x] Software timestamp synchronisatiebeleid.
- [x] Capture health metrics per camera.
- [x] Disk/resource snapshots tijdens recording.
- [ ] Per-camera profiel-editor in UI.
- [ ] Hardware-trigger synchronisatie.

## 2. Robuuste Calibratie

- [x] Chessboard sample capture.
- [x] Gesplitste intrinsics/extrinsics capture workflow.
- [x] Auto-capture voor geldige calibratieframes met live overlay/quality gating.
- [x] Intrinsics en extrinsics solve basis.
- [x] Fix voor extrinsics vanuit intrinsics-only bundles.
- [x] Charuco-detectiepad wanneer `cv2.aruco` beschikbaar is.
- [ ] AprilTag support.
- [x] Fixed-intrinsics pairwise stereo refinement via OpenCV `stereoCalibrate`.
- [x] Reprojection en epipolar diagnostics.
- [x] Calibration acceptance score.
- [x] Calibration profile versioning metadata.
- [ ] Globale multi-camera bundle adjustment solver.

## 3. 2D Detectie

- [x] Synthetic detector fallback.
- [x] MediaPipe detector basis.
- [x] Detector-plugin registry basis.
- [x] Confidence filtering policies.
- [x] Occlusion/missing-keypoint reporting.
- [x] Backend capabilities voor body/hands/face/full-body opties.
- [ ] Alternatieve detector backends.
- [ ] Hand/face/full-body detector implementaties.

## 4. Tracking En Identiteit

- [x] Semantische keypoint matching basis.
- [x] Exponential smoothing basis.
- [ ] Multi-person tracking.
- [ ] Person ID persistence.
- [ ] Occlusion recovery.
- [ ] Outlier rejection.

## 5. 3D-Reconstructie

- [x] Calibrated triangulation basis.
- [x] Reprojection error gating per joint.
- [x] Confidence-weighted triangulatie.
- [ ] Epipolar matching.
- [x] Missing-joint handling.
- [x] Trust-state scoring per frame.

## 6. Skeleton Fitting

- [ ] Body skeleton model.
- [ ] Subject calibration.
- [ ] Inverse kinematics.
- [ ] Joint limits.
- [ ] Foot/contact constraints.

## 7. Biomechanica En Analyse

- [x] Intern processed motion-take bestand als analyse-ingang.
- [x] Eerste 3D joint-angle analyse voor knie/heup/elleboog/schouder.
- [ ] Velocity en acceleration.
- [ ] Range of motion.
- [ ] Asymmetrie-metrieken.
- [ ] Rapportage en grafieken.

## 8. Session Management

- [x] JSON manifest repository.
- [x] Session tab met new/save/load.
- [x] Recording lifecycle start/stop.
- [x] Per-camera video files gekoppeld aan manifest.
- [x] Session playback.
- [x] Offline re-processing.
- [x] Processed motion take opslag onder recorded session.
- [x] UI review-tab voor opgenomen sessies.
- [ ] Subject metadata.
- [ ] Session browser.

## 9. Exports

- [x] CSV/JSON pose export.
- [x] UI-koppeling voor CSV/JSON pose export vanuit Review.
- [ ] BVH export.
- [ ] C3D export.
- [ ] glTF/FBX route.
- [ ] Coordinate-system conversion.

## 10. Workflow-UX

- [x] Capture, Session, Live View, Calibration en Diagnostics tabs.
- [x] Review-tab met frame slider en recorded session preview.
- [x] Review-overlay processing voor de huidige recorded frame.
- [x] Review-tab kan een volledige session verwerken naar interne motion take.
- [x] Analysis-tab voor processed motion takes en joint-angle summaries.
- [ ] Setup wizard.
- [ ] Camera health panel.
- [ ] Calibration acceptance checklist.
- [x] Eerste record-review-export operator flow.

## 11. Performance En Betrouwbaarheid

- [x] Capture worker buiten UI-thread.
- [x] Pipeline worker buiten UI-thread.
- [x] Recording worker buiten UI-thread.
- [x] Bounded recording queue met drop-signalering.
- [x] Disk usage monitoring tijdens recording.
- [ ] Latency dashboard uitbreiden.
- [ ] Volledige memory monitoring zonder optionele `psutil` afhankelijkheid.
- [ ] Crash recovery.

## 12. Validatie En Tests

- [x] Calibration regressietest.
- [x] Session recorder regressietest.
- [x] Session playback/reprocess regressietest.
- [x] Professional foundations regressietest voor camera/calibration/detector basis.
- [x] Export roundtrip test voor recorded session naar JSON/CSV.
- [x] Motion-take roundtrip test voor processed recorded session.
- [x] Joint-angle analyse regressietest.
- [ ] Synthetic fixture dataset.
- [ ] Reconstruction benchmarks.
- [ ] UI smoke tests.

## 13. Packaging

- [ ] Windows build.
- [ ] Dependency bundling.
- [ ] Modelbestand bundling.
- [ ] Settings migraties.
- [ ] Gebruikersdocumentatie.
