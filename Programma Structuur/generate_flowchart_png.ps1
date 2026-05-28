Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$ErrorActionPreference = "Stop"

function New-Color([string]$Hex) {
    return [System.Drawing.ColorTranslator]::FromHtml($Hex)
}

function New-RoundedPath([float]$X, [float]$Y, [float]$Width, [float]$Height, [float]$Radius) {
    $diameter = $Radius * 2
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
    $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
    $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return $path
}

function Draw-RoundedRectangle(
    [System.Drawing.Graphics]$Graphics,
    [float]$X,
    [float]$Y,
    [float]$Width,
    [float]$Height,
    [float]$Radius,
    [System.Drawing.Color]$FillColor,
    [System.Drawing.Color]$BorderColor,
    [float]$BorderWidth = 1.0
) {
    $path = New-RoundedPath -X $X -Y $Y -Width $Width -Height $Height -Radius $Radius
    $brush = New-Object System.Drawing.SolidBrush($FillColor)
    $pen = New-Object System.Drawing.Pen($BorderColor, $BorderWidth)
    $Graphics.FillPath($brush, $path)
    $Graphics.DrawPath($pen, $path)
    $pen.Dispose()
    $brush.Dispose()
    $path.Dispose()
}

function Draw-Lane(
    [System.Drawing.Graphics]$Graphics,
    [float]$X,
    [float]$Y,
    [float]$Width,
    [float]$Height,
    [string]$Title,
    [System.Drawing.Color]$FillColor,
    [System.Drawing.Color]$BorderColor,
    [System.Drawing.Font]$HeaderFont,
    [System.Drawing.Font]$CaptionFont,
    [System.Drawing.Color]$TextColor
) {
    Draw-RoundedRectangle -Graphics $Graphics -X $X -Y $Y -Width $Width -Height $Height -Radius 24 -FillColor $FillColor -BorderColor $BorderColor -BorderWidth 1.2

    $headerRect = [System.Drawing.RectangleF]::new([float]($X + 20), [float]($Y + 16), [float]($Width - 40), 28.0)
    $captionRect = [System.Drawing.RectangleF]::new([float]($X + 20), [float]($Y + 46), [float]($Width - 40), 18.0)
    $textBrush = New-Object System.Drawing.SolidBrush($TextColor)
    $Graphics.DrawString($Title, $HeaderFont, $textBrush, $headerRect)
    $Graphics.DrawString("Runtime lane", $CaptionFont, $textBrush, $captionRect)
    $textBrush.Dispose()
}

function Draw-Box(
    [System.Drawing.Graphics]$Graphics,
    [hashtable]$Box,
    [System.Drawing.Font]$TitleFont,
    [System.Drawing.Font]$BodyFont,
    [System.Drawing.Color]$TitleColor,
    [System.Drawing.Color]$BodyColor
) {
    Draw-RoundedRectangle -Graphics $Graphics -X $Box.x -Y $Box.y -Width $Box.w -Height $Box.h -Radius 18 -FillColor $Box.fill -BorderColor $Box.border -BorderWidth 1.4

    $titleBrush = New-Object System.Drawing.SolidBrush($TitleColor)
    $bodyBrush = New-Object System.Drawing.SolidBrush($BodyColor)
    $format = New-Object System.Drawing.StringFormat
    $format.Trimming = [System.Drawing.StringTrimming]::EllipsisWord

    $titleRect = [System.Drawing.RectangleF]::new([float]($Box.x + 18), [float]($Box.y + 14), [float]($Box.w - 36), 28.0)
    $bodyRect = [System.Drawing.RectangleF]::new([float]($Box.x + 18), [float]($Box.y + 46), [float]($Box.w - 36), [float]($Box.h - 58))

    $Graphics.DrawString([string]$Box.title, $TitleFont, $titleBrush, $titleRect, $format)
    $Graphics.DrawString([string]$Box.body, $BodyFont, $bodyBrush, $bodyRect, $format)

    $format.Dispose()
    $titleBrush.Dispose()
    $bodyBrush.Dispose()
}

function Get-Anchor([hashtable]$Box, [string]$Side) {
    switch ($Side) {
        "left" { return [System.Drawing.PointF]::new([float]$Box.x, [float]($Box.y + ($Box.h / 2.0))) }
        "right" { return [System.Drawing.PointF]::new([float]($Box.x + $Box.w), [float]($Box.y + ($Box.h / 2.0))) }
        "top" { return [System.Drawing.PointF]::new([float]($Box.x + ($Box.w / 2.0)), [float]$Box.y) }
        "bottom" { return [System.Drawing.PointF]::new([float]($Box.x + ($Box.w / 2.0)), [float]($Box.y + $Box.h)) }
        default { throw "Unsupported anchor side '$Side'." }
    }
}

function Draw-ArrowHead(
    [System.Drawing.Graphics]$Graphics,
    [System.Drawing.PointF]$Tip,
    [float]$AngleRadians,
    [System.Drawing.Color]$Color
) {
    $size = 9.0
    $left = [System.Drawing.PointF]::new(
        [float]($Tip.X - ($size * [Math]::Cos($AngleRadians - 0.55))),
        [float]($Tip.Y - ($size * [Math]::Sin($AngleRadians - 0.55)))
    )
    $right = [System.Drawing.PointF]::new(
        [float]($Tip.X - ($size * [Math]::Cos($AngleRadians + 0.55))),
        [float]($Tip.Y - ($size * [Math]::Sin($AngleRadians + 0.55)))
    )

    $brush = New-Object System.Drawing.SolidBrush($Color)
    $points = [System.Drawing.PointF[]]@($Tip, $left, $right)
    $Graphics.FillPolygon($brush, $points)
    $brush.Dispose()
}

function Draw-Connector(
    [System.Drawing.Graphics]$Graphics,
    [System.Drawing.PointF]$From,
    [System.Drawing.PointF]$To,
    [System.Drawing.Color]$Color,
    [string]$Label,
    [System.Drawing.Font]$LabelFont
) {
    $pen = New-Object System.Drawing.Pen($Color, 2.0)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    $midX = [float](($From.X + $To.X) / 2.0)
    $points = [System.Drawing.PointF[]]@(
        [System.Drawing.PointF]::new($From.X, $From.Y),
        [System.Drawing.PointF]::new($midX, $From.Y),
        [System.Drawing.PointF]::new($midX, $To.Y),
        [System.Drawing.PointF]::new($To.X, $To.Y)
    )
    $Graphics.DrawLines($pen, $points)

    if ([string]::IsNullOrWhiteSpace($Label) -eq $false) {
        $labelBrush = New-Object System.Drawing.SolidBrush((New-Color "#41566D"))
        $labelRect = [System.Drawing.RectangleF]::new([float]($midX - 80), [float](([Math]::Min($From.Y, $To.Y) + [Math]::Abs($From.Y - $To.Y) / 2.0) - 10), 160.0, 20.0)
        $format = New-Object System.Drawing.StringFormat
        $format.Alignment = [System.Drawing.StringAlignment]::Center
        $Graphics.FillRectangle((New-Object System.Drawing.SolidBrush((New-Color "#FFFFFF"))), $labelRect)
        $Graphics.DrawString($Label, $LabelFont, $labelBrush, $labelRect, $format)
        $format.Dispose()
        $labelBrush.Dispose()
    }

    $tail = $points[$points.Length - 2]
    $tip = $points[$points.Length - 1]
    $angle = [Math]::Atan2(($tip.Y - $tail.Y), ($tip.X - $tail.X))
    Draw-ArrowHead -Graphics $Graphics -Tip $tip -AngleRadians $angle -Color $Color

    $pen.Dispose()
}

function Draw-Note(
    [System.Drawing.Graphics]$Graphics,
    [float]$X,
    [float]$Y,
    [float]$Width,
    [float]$Height,
    [string]$Text,
    [System.Drawing.Font]$Font
) {
    Draw-RoundedRectangle -Graphics $Graphics -X $X -Y $Y -Width $Width -Height $Height -Radius 14 -FillColor (New-Color "#FFF7E8") -BorderColor (New-Color "#E5C98B") -BorderWidth 1.2
    $brush = New-Object System.Drawing.SolidBrush((New-Color "#6A5322"))
    $rect = [System.Drawing.RectangleF]::new([float]($X + 14), [float]($Y + 10), [float]($Width - 28), [float]($Height - 20))
    $Graphics.DrawString($Text, $Font, $brush, $rect)
    $brush.Dispose()
}

$outputPath = Join-Path $PSScriptRoot "FLOWCHART.png"

$baseWidth = 2600
$baseHeight = 1720
$renderScale = 1.45
$width = [int]([Math]::Ceiling($baseWidth * $renderScale))
$height = [int]([Math]::Ceiling($baseHeight * $renderScale))

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
$graphics.Clear((New-Color "#F4F7FB"))
$graphics.ScaleTransform([float]$renderScale, [float]$renderScale)

$titleFont = New-Object System.Drawing.Font("Segoe UI", 28, [System.Drawing.FontStyle]::Bold)
$subtitleFont = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Regular)
$laneFont = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$laneCaptionFont = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
$boxTitleFont = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$boxBodyFont = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Regular)
$smallFont = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
$noteFont = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)

$darkText = New-Color "#163047"
$bodyText = New-Color "#41566D"
$lineColor = New-Color "#56718A"

$titleBrush = New-Object System.Drawing.SolidBrush($darkText)
$graphics.DrawString("Programma Structuur Mocap", $titleFont, $titleBrush, 62, 34)
$graphics.DrawString(
    "Software flowchart for engineers: entrypoints, UI orchestration, workers, processing pipeline, calibration, persistence, and runtime contracts.",
    $subtitleFont,
    (New-Object System.Drawing.SolidBrush($bodyText)),
    ([System.Drawing.RectangleF]::new(64.0, 82.0, 2400.0, 22.0))
)
$titleBrush.Dispose()

$laneTop = 128
$laneHeight = 1310
$laneWidth = 565
$laneGap = 30

$lane1X = 60
$lane2X = $lane1X + $laneWidth + $laneGap
$lane3X = $lane2X + $laneWidth + $laneGap
$lane4X = $lane3X + $laneWidth + $laneGap

Draw-Lane -Graphics $graphics -X $lane1X -Y $laneTop -Width $laneWidth -Height $laneHeight -Title "Entry & UI Orchestration" -FillColor (New-Color "#EEF5FF") -BorderColor (New-Color "#C5D8F0") -HeaderFont $laneFont -CaptionFont $laneCaptionFont -TextColor $darkText
Draw-Lane -Graphics $graphics -X $lane2X -Y $laneTop -Width $laneWidth -Height $laneHeight -Title "Runtime Workers" -FillColor (New-Color "#EFFBF5") -BorderColor (New-Color "#C9E7D6") -HeaderFont $laneFont -CaptionFont $laneCaptionFont -TextColor $darkText
Draw-Lane -Graphics $graphics -X $lane3X -Y $laneTop -Width $laneWidth -Height $laneHeight -Title "Processing & Algorithms" -FillColor (New-Color "#FFF5EE") -BorderColor (New-Color "#ECD3BE") -HeaderFont $laneFont -CaptionFont $laneCaptionFont -TextColor $darkText
Draw-Lane -Graphics $graphics -X $lane4X -Y $laneTop -Width $laneWidth -Height $laneHeight -Title "Persistence & Shared Contracts" -FillColor (New-Color "#F7F3FF") -BorderColor (New-Color "#DACDF4") -HeaderFont $laneFont -CaptionFont $laneCaptionFont -TextColor $darkText

$boxes = [ordered]@{
    entry = @{
        x = 92; y = 188; w = 500; h = 112
        title = "run.py -> app.main.run()"
        body = "Parses CLI modes via parse_args(). Builds context, configures logging, and dispatches to smoke test, synthetic demo, capture sample, or Qt UI."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C5D8F0")
    }
    mainWindow = @{
        x = 92; y = 332; w = 500; h = 196
        title = "ui.main_window.MainWindow"
        body = "Central orchestration shell. Builds tabs, wires widgets, starts startup/calibration workers, reacts to probe/sample/live requests, routes batches, manages calibration/session state, updates previews, and shuts workers down cleanly."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C5D8F0")
    }
    widgets = @{
        x = 92; y = 560; w = 500; h = 176
        title = "UI widgets"
        body = "CapturePanelWidget, CalibrationPanelWidget, FramePreviewWidget, CameraGridWidget, SessionPanelWidget, PipelineStatusWidget. Render state and emit user intent only."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C5D8F0")
    }
    uiActions = @{
        x = 92; y = 768; w = 500; h = 150
        title = "Main UI actions"
        body = "_begin_startup_sequence(), _start_capture_worker(), _on_capture_batch_ready(), _on_solve_calibration_intrinsics(), _on_solve_calibration_extrinsics(), _on_save_session_requested()"
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C5D8F0")
    }
    shutdown = @{
        x = 92; y = 950; w = 500; h = 146
        title = "Shutdown path"
        body = "closeEvent() stops startup, calibration, capture, probe, and pipeline workers. Then MocapPipeline.shutdown() closes detector resources and resets smoothing state."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C5D8F0")
    }

    startupWorker = @{
        x = 687; y = 188; w = 500; h = 136
        title = "StartupWorker.run()"
        body = "Loads detector with fallback, loads current calibration profile, emits StartupResult(detector, bundle, path, messages)."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C9E7D6")
    }
    probeWorker = @{
        x = 687; y = 356; w = 500; h = 130
        title = "CameraProbeWorker.run()"
        body = "Uses OpenCVCaptureSession.probe_sources() and returns CameraProbeResult per enabled source."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C9E7D6")
    }
    captureWorker = @{
        x = 687; y = 518; w = 500; h = 186
        title = "CaptureWorker.run()"
        body = "Opens sources, emits probe_ready once, then loops over read_batch(). Emits batch_ready for each CaptureBatch. Stops on batch limit, source exhaustion, explicit stop, or worker failure."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C9E7D6")
    }
    calibWorker = @{
        x = 687; y = 736; w = 500; h = 170
        title = "CalibrationAnalysisWorker.run()"
        body = "Keeps one priority job for explicit calibration samples and one latest-live job for overlay feedback. Runs CalibrationManager.capture_frames() and emits CalibrationAnalysisOutcome."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C9E7D6")
    }
    pipeWorker = @{
        x = 687; y = 938; w = 500; h = 178
        title = "PipelineWorker.run()"
        body = "Latest-frame worker. submit_batch() overwrites older pending jobs, increments dropped_input_batches, locks pipeline state, processes batch, and emits PipelineResult with capture latency."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#C9E7D6")
    }

    openCv = @{
        x = 1282; y = 188; w = 500; h = 172
        title = "capture.backend.OpenCVCaptureSession"
        body = "open(), probe_sources(), read_batch(), close(). Normalizes webcam/video sources, selects Windows backends, caps queue depth via CAP_PROP_BUFFERSIZE=1, and returns CaptureBatch with FramePacket payloads."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#ECD3BE")
    }
    detectors = @{
        x = 1282; y = 392; w = 500; h = 156
        title = "detectors.factory + PoseDetector"
        body = "create_detector() resolves MediaPipePoseDetector or SyntheticPoseDetector. detect(frame) produces Pose2D per camera. Detector switches reset smoothing and close prior detector resources."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#ECD3BE")
    }
    pipeline = @{
        x = 1282; y = 580; w = 500; h = 230
        title = "pipeline.manager.MocapPipeline.process()"
        body = "Per batch: detect 2D poses -> semantic keypoint matching -> calibrated triangulation -> exponential smoothing -> PipelineResult. Adds notes for missing calibration, one-camera mode, detector failures, and empty 3D reconstruction."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#ECD3BE")
    }
    calibration = @{
        x = 1282; y = 842; w = 500; h = 238
        title = "calibration.manager.CalibrationManager"
        body = "capture_frames() detects chessboard corners, builds sync report, scores camera quality, stores sample history, and records synchronized multi-camera samples. solve_intrinsics() calibrates per camera. solve_extrinsics() resolves reference camera and averages transforms across synchronized samples."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#ECD3BE")
    }
    substeps = @{
        x = 1282; y = 1112; w = 500; h = 168
        title = "Core algorithm modules"
        body = "tracking.matcher.SemanticKeypointMatcher.match() groups 2D keypoints by semantic name. reconstruction.calibrated_triangulation.CalibratedTriangulator.triangulate() uses calibration-aware reprojection checks. tracking.smoother.ExponentialPoseSmoother.apply() stabilizes 3D output over time."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#ECD3BE")
    }

    config = @{
        x = 1877; y = 188; w = 500; h = 132
        title = "core.config.AppConfig + logging"
        body = "Loads preferences, ensures directories, persists detector/source/FPS defaults, and configures logs under Programma Structuur/logs."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#DACDF4")
    }
    calibRepo = @{
        x = 1877; y = 352; w = 500; h = 142
        title = "CalibrationRepository"
        body = "load(path) and save(bundle, path) for CalibrationBundle JSON persistence, including intrinsics, extrinsics, metadata, diagnostics, and sample counts."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#DACDF4")
    }
    sessionRepo = @{
        x = 1877; y = 526; w = 500; h = 162
        title = "SessionRepository"
        body = "create_session_id(), build_manifest(), save(), load(), sources_to_csv(), manifest_summary(). Persists SessionManifest snapshots for live runtime state and restore flows."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#DACDF4")
    }
    contracts = @{
        x = 1877; y = 720; w = 500; h = 214
        title = "models.types shared runtime contracts"
        body = "CameraSourceConfig, FramePacket, CaptureBatch payloads, Pose2D, Pose3D, CameraCalibration, CalibrationBundle, SessionManifest, CameraProbeResult, PipelineDebugInfo, and PipelineResult travel between UI, workers, processing, and storage."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#DACDF4")
    }
    placeholders = @{
        x = 1877; y = 966; w = 500; h = 158
        title = "Planned extension zones"
        body = "batch/, biomechanics/, exporters/, fitting/, plugins/, and several UI subfolders already exist as scaffolding but do not yet own active Python runtime flows."
        fill = (New-Color "#FFFFFF"); border = (New-Color "#DACDF4")
    }
}

foreach ($box in $boxes.Values) {
    Draw-Box -Graphics $graphics -Box $box -TitleFont $boxTitleFont -BodyFont $boxBodyFont -TitleColor $darkText -BodyColor $bodyText
}

$connectors = @(
    @{ from = "entry"; fromSide = "right"; to = "config"; toSide = "left"; label = "build context + logging" }
    @{ from = "entry"; fromSide = "bottom"; to = "mainWindow"; toSide = "top"; label = "launch --ui" }
    @{ from = "mainWindow"; fromSide = "bottom"; to = "widgets"; toSide = "top"; label = "render + signals" }
    @{ from = "mainWindow"; fromSide = "right"; to = "startupWorker"; toSide = "left"; label = "startup sequence" }
    @{ from = "startupWorker"; fromSide = "right"; to = "detectors"; toSide = "left"; label = "load detector" }
    @{ from = "startupWorker"; fromSide = "right"; to = "calibRepo"; toSide = "left"; label = "load bundle" }
    @{ from = "startupWorker"; fromSide = "left"; to = "mainWindow"; toSide = "right"; label = "StartupResult" }
    @{ from = "mainWindow"; fromSide = "right"; to = "probeWorker"; toSide = "left"; label = "probe sources" }
    @{ from = "probeWorker"; fromSide = "right"; to = "openCv"; toSide = "left"; label = "probe_sources()" }
    @{ from = "openCv"; fromSide = "left"; to = "mainWindow"; toSide = "right"; label = "CameraProbeResult" }
    @{ from = "uiActions"; fromSide = "right"; to = "captureWorker"; toSide = "left"; label = "sample/live request" }
    @{ from = "captureWorker"; fromSide = "right"; to = "openCv"; toSide = "left"; label = "open + read_batch()" }
    @{ from = "captureWorker"; fromSide = "left"; to = "mainWindow"; toSide = "right"; label = "CaptureBatch" }
    @{ from = "mainWindow"; fromSide = "right"; to = "calibWorker"; toSide = "left"; label = "submit_batch()" }
    @{ from = "calibWorker"; fromSide = "right"; to = "calibration"; toSide = "left"; label = "capture_frames()" }
    @{ from = "calibration"; fromSide = "right"; to = "calibRepo"; toSide = "left"; label = "save/load profile" }
    @{ from = "mainWindow"; fromSide = "right"; to = "pipeWorker"; toSide = "left"; label = "latest batch" }
    @{ from = "pipeWorker"; fromSide = "right"; to = "pipeline"; toSide = "left"; label = "process()" }
    @{ from = "pipeline"; fromSide = "top"; to = "detectors"; toSide = "bottom"; label = "detect()" }
    @{ from = "pipeline"; fromSide = "bottom"; to = "substeps"; toSide = "top"; label = "match + triangulate + smooth" }
    @{ from = "pipeline"; fromSide = "right"; to = "contracts"; toSide = "left"; label = "PipelineResult" }
    @{ from = "calibration"; fromSide = "right"; to = "contracts"; toSide = "left"; label = "CalibrationBundle" }
    @{ from = "mainWindow"; fromSide = "right"; to = "sessionRepo"; toSide = "left"; label = "session save/load" }
    @{ from = "sessionRepo"; fromSide = "bottom"; to = "contracts"; toSide = "top"; label = "SessionManifest" }
    @{ from = "shutdown"; fromSide = "right"; to = "pipeWorker"; toSide = "left"; label = "stop/terminate" }
)

foreach ($edge in $connectors) {
    $fromPoint = Get-Anchor -Box $boxes[$edge.from] -Side $edge.fromSide
    $toPoint = Get-Anchor -Box $boxes[$edge.to] -Side $edge.toSide
    Draw-Connector -Graphics $graphics -From $fromPoint -To $toPoint -Color $lineColor -Label $edge.label -LabelFont $smallFont
}

Draw-Note -Graphics $graphics -X 64 -Y 1472 -Width 790 -Height 90 -Text "Backpressure policy: PipelineWorker keeps only the newest pending batch. Capture stays live even when processing falls behind." -Font $noteFont
Draw-Note -Graphics $graphics -X 905 -Y 1472 -Width 790 -Height 90 -Text "3D trust policy: CalibratedTriangulator only reconstructs when CalibrationBundle contains usable intrinsics and extrinsics for multiple cameras." -Font $noteFont
Draw-Note -Graphics $graphics -X 1746 -Y 1472 -Width 790 -Height 90 -Text "Architecture reality check: MainWindow is still the runtime orchestrator, while domain contracts and infrastructure boundaries are already emerging underneath." -Font $noteFont

$footerBrush = New-Object System.Drawing.SolidBrush((New-Color "#6B7E91"))
$graphics.DrawString(
    "Generated from the current Programma Structuur implementation on disk. Source documentation: FLOWCHART.md",
    $smallFont,
    $footerBrush,
    66,
    1632
)
$footerBrush.Dispose()

$bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)

$graphics.Dispose()
$bitmap.Dispose()
$titleFont.Dispose()
$subtitleFont.Dispose()
$laneFont.Dispose()
$laneCaptionFont.Dispose()
$boxTitleFont.Dispose()
$boxBodyFont.Dispose()
$smallFont.Dispose()
$noteFont.Dispose()

Write-Output "Generated $outputPath"
