# AI Agent Studio — optional PowerShell launcher
# Prefer Launch.bat (handles paths with spaces reliably).
# If native tools missing → install into ./browsers then launch (no separate setup).

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "========================================"
Write-Host " AI Agent Studio — Launch.ps1"
Write-Host "========================================"
Write-Host "Root: $PSScriptRoot"
Write-Host ""

$data = Join-Path -Path $PSScriptRoot -ChildPath "data"
if (-not (Test-Path -LiteralPath $data)) {
    New-Item -ItemType Directory -Path $data | Out-Null
}
$browsers = Join-Path -Path $PSScriptRoot -ChildPath "browsers"
if (-not (Test-Path -LiteralPath $browsers)) {
    New-Item -ItemType Directory -Path $browsers | Out-Null
}
$env:PLAYWRIGHT_BROWSERS_PATH = $browsers

$errLog = Join-Path -Path $data -ChildPath "last_launch_error.txt"
$venvPy = Join-Path -Path $PSScriptRoot -ChildPath ".venv\Scripts\python.exe"
$req = Join-Path -Path $PSScriptRoot -ChildPath "requirements.txt"

$pythonExe = $null
$pythonArgs = @("-m", "app")

if (Test-Path -LiteralPath $venvPy) {
    $pythonExe = $venvPy
    Write-Host "Using venv: $pythonExe"
} else {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        Write-Host "Creating .venv..."
        & $py.Source -3 -m venv (Join-Path $PSScriptRoot ".venv")
        if (Test-Path -LiteralPath $venvPy) {
            $pythonExe = $venvPy
        } else {
            $pythonExe = $py.Source
            $pythonArgs = @("-3", "-m", "app")
        }
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($python) {
            Write-Host "Creating .venv..."
            & $python.Source -m venv (Join-Path $PSScriptRoot ".venv")
            if (Test-Path -LiteralPath $venvPy) {
                $pythonExe = $venvPy
            } else {
                $pythonExe = $python.Source
            }
        }
    }
}

if (-not $pythonExe) {
    $msg = @"
No Python found. Install Python 3.11+, then double-click Launch.bat again.
"@
    Set-Content -LiteralPath $errLog -Value $msg
    Write-Host $msg -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# Prefer venv for ensure + app when available
$runPy = $pythonExe
if (Test-Path -LiteralPath $venvPy) { $runPy = $venvPy }

function Test-NativeReady {
    param([string]$Py, [string]$BrowsersPath)
    $chrome = Get-ChildItem -LiteralPath $BrowsersPath -Recurse -Filter "chrome.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $chrome) { return $false }
    & $Py -c "import playwright,pypdf" 2>$null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-NativeReady -Py $runPy -BrowsersPath $browsers)) {
    Write-Host "Native tools missing — installing into this folder (one-time)..."
    if (Test-Path -LiteralPath $req) {
        & $runPy -m pip install -q -r $req
    }
    & $runPy -m app.tools.ensure_native
} else {
    Write-Host "Native tools OK — launching."
}

Write-Host "Starting GUI..."
Write-Host ""

if (Test-Path -LiteralPath $venvPy) {
    & $venvPy -m app
} else {
    & $pythonExe @pythonArgs
}
$code = $LASTEXITCODE
if ($null -eq $code) { $code = 0 }

if ($code -ne 0) {
    $line = "$(Get-Date -Format o) Exit code $code"
    Add-Content -LiteralPath $errLog -Value $line
    Write-Host "App exited with code $code" -ForegroundColor Yellow
    Write-Host "Run Launch.bat again — it re-checks native tools automatically."
    Read-Host "Press Enter to close"
}

exit $code
