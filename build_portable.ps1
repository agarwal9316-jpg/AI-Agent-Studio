# Build portable onedir with PyInstaller
# Safe with spaces in path (use -LiteralPath / quoted paths).
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "========================================"
Write-Host " Building portable AI Agent Studio"
Write-Host " Root: $PSScriptRoot"
Write-Host "========================================"

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Creating .venv ..."
    py -3 -m venv .venv
    if (-not (Test-Path -LiteralPath $venvPy)) {
        throw "Failed to create venv at $venvPy"
    }
}

Write-Host "Installing build dependencies..."
& $venvPy -m pip install -q -r (Join-Path $PSScriptRoot "requirements.txt")
& $venvPy -m pip install -q "pyinstaller>=6.0"

$dist = Join-Path $PSScriptRoot "dist"
$work = Join-Path $PSScriptRoot "build"
$entry = Join-Path $PSScriptRoot "entry.py"
$name = "AI-Agent-Studio"

Write-Host "Running PyInstaller (onedir, windowed)..."
& $venvPy -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name $name `
    --paths $PSScriptRoot `
    --distpath $dist `
    --workpath $work `
    --specpath $PSScriptRoot `
    --collect-all customtkinter `
    --hidden-import app `
    --hidden-import app.main `
    --hidden-import app.ui.app_window `
    --hidden-import app.services.storage `
    --hidden-import app.services.runner `
    --hidden-import app.services.llm `
    --hidden-import app.services.chat `
    --hidden-import app.services.attachments `
    --hidden-import app.services.terminal_tool `
    --hidden-import app.services.skills_registry `
    --hidden-import app.services.mcp_client `
    --hidden-import app.services.capability_manual `
    --hidden-import app.services.mcp_marketplace `
    --hidden-import app.services.default_prompts `
    --hidden-import app.services.laptop_control `
    --hidden-import app.services.chat_store `
    --hidden-import app.services.memory_store `
    --hidden-import app.services.project_store `
    --hidden-import app.services.company_store `
    --hidden-import app.services.orchestrator `
    --hidden-import app.ui.mgmt_pages `
    --hidden-import app.services.workflow_graph `
    --hidden-import app.ui.org_page `
    --hidden-import app.services.providers `
    --hidden-import app.services.org_tools `
    --hidden-import app.services.package_auto `
    --hidden-import app.services.activity_log `
    --hidden-import app.services.chat_export `
    --hidden-import app.services.tts_service `
    --hidden-import app.services.media_chat `
    --hidden-import app.services.agent_tracker `
    --hidden-import app.services.themes `
    --hidden-import pyautogui `
    --collect-all pyautogui `
    $entry

$exe = Join-Path $dist "$name\$name.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Build failed: exe not found at $exe"
}

# Copy portable Chromium next to the exe so LLM browser tool works offline-ready
$browsersSrc = Join-Path $PSScriptRoot "browsers"
$browsersDst = Join-Path $dist "$name\browsers"
if (Test-Path -LiteralPath $browsersSrc) {
    Write-Host "Copying portable Chromium browsers → dist ..."
    if (Test-Path -LiteralPath $browsersDst) {
        Remove-Item -LiteralPath $browsersDst -Recurse -Force
    }
    Copy-Item -LiteralPath $browsersSrc -Destination $browsersDst -Recurse -Force
    Write-Host "Browsers copied."
} else {
    Write-Host "NOTE: No ./browsers folder. Launch.bat will auto-install Chromium on first run."
}

# Version stamp for About / update check (Task #10)
$distRoot = Join-Path $dist $name
foreach ($vf in @("VERSION", "version_manifest.json")) {
    $src = Join-Path $PSScriptRoot $vf
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $distRoot $vf) -Force
        Write-Host "Copied $vf → dist"
    }
}
# Refresh VERSION from app.version if present
try {
    $verPy = & $venvPy -c "from app.version import __version__; print(__version__)"
    if ($verPy) {
        Set-Content -LiteralPath (Join-Path $distRoot "VERSION") -Value $verPy.Trim() -Encoding utf8
        Write-Host "VERSION file set to $verPy"
    }
} catch {
    Write-Host "NOTE: could not stamp VERSION from app.version"
}


# Code signing (optional) — see docs/CODE_SIGNING.md
# Uses AAS_SIGN_CERT / AAS_SIGN_PASSWORD when set; skips gracefully otherwise.
$signScript = Join-Path $PSScriptRoot "scripts\sign_portable.ps1"
if (Test-Path -LiteralPath $signScript) {
    Write-Host ""
    Write-Host "Optional Authenticode sign (scripts\sign_portable.ps1)..."
    try {
        & $signScript
    } catch {
        Write-Host "NOTE: sign script error (build still OK): $($_.Exception.Message)"
    }
} else {
    Write-Host "NOTE: scripts\sign_portable.ps1 missing — skip signing."
}

# Copy launch helper next to dist folder for convenience
$portableBat = Join-Path $PSScriptRoot "Launch_Portable.bat"
Write-Host ""
Write-Host "BUILD OK"
Write-Host "  Exe: $exe"
Write-Host "  Start: $portableBat"
Write-Host "  Or double-click the .exe inside dist\$name\"
Write-Host ""

