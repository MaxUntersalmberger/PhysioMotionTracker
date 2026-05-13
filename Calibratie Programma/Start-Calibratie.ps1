param(
    [switch]$SmokeTest,
    [switch]$SkipInstall,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $Root "requirements.txt"
$RequirementsStamp = Join-Path $VenvDir ".requirements.stamp"
$RunPy = Join-Path $Root "run.py"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Find-PythonLauncher {
    $launchers = @(
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )

    foreach ($launcher in $launchers) {
        $exe = [string]$launcher.Exe
        $args = [string[]]$launcher.Args
        try {
            & $exe @args -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" | Out-Null
            return @{ Exe = $exe; Args = $args }
        } catch {
            continue
        }
    }

    throw "Geen geschikte Python gevonden. Installeer Python 3.10 of nieuwer en vink tijdens installatie 'Add Python to PATH' aan."
}

Set-Location $Root

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Step "Lokale Python omgeving maken"
    $launcher = Find-PythonLauncher
    & $launcher.Exe @($launcher.Args) -m venv $VenvDir
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "De lokale Python omgeving is niet goed aangemaakt: $VenvPython"
}

if (-not $SkipInstall) {
    $needsInstall = -not (Test-Path -LiteralPath $RequirementsStamp)
    if (-not $needsInstall -and (Test-Path -LiteralPath $Requirements)) {
        $needsInstall = (Get-Item -LiteralPath $Requirements).LastWriteTimeUtc -gt (Get-Item -LiteralPath $RequirementsStamp).LastWriteTimeUtc
    }

    if ($needsInstall) {
        Write-Step "Benodigde packages installeren"
        & $VenvPython -m pip uninstall -y opencv-python opencv-python-headless | Out-Null
        & $VenvPython -m pip install -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            throw "Installeren van packages is mislukt."
        }
        New-Item -ItemType File -Path $RequirementsStamp -Force | Out-Null
    }
}

if ($ExtraArgs.Count -gt 0) {
    $AppArgs = $ExtraArgs
} elseif ($SmokeTest) {
    $AppArgs = @("--smoke-test")
} else {
    $AppArgs = @("--ui")
}

Write-Step "PhysioMotion Calibratie starten"
& $VenvPython $RunPy @AppArgs
exit $LASTEXITCODE
