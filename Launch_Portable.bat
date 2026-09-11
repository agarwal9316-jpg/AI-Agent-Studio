@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Portable launcher — starts packaged build (no system Python needed)

set "EXE=%~dp0dist\AI-Agent-Studio\AI-Agent-Studio.exe"

if not exist "%EXE%" (
  echo.
  echo Portable build not found:
  echo   %EXE%
  echo.
  echo To create it, run in this folder:
  echo   build_portable.ps1
  echo.
  echo For development, use Launch.bat instead.
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0data" mkdir "%~dp0data"
if not exist "%~dp0browsers" mkdir "%~dp0browsers"
if not exist "%~dp0dist\AI-Agent-Studio\browsers" (
  if exist "%~dp0browsers\chromium-1228" (
    echo Copying portable Chromium next to exe...
    xcopy /E /I /Y /Q "%~dp0browsers" "%~dp0dist\AI-Agent-Studio\browsers\" >nul
  )
)

REM Chromium lives next to the exe for portable mode
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0dist\AI-Agent-Studio\browsers"
if not exist "%PLAYWRIGHT_BROWSERS_PATH%" set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"

echo Starting portable AI Agent Studio...
start "" "%EXE%"
exit /b 0
