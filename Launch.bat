@echo off
setlocal EnableExtensions
REM ============================================================
REM  AI Agent Studio — REQUIRED launcher for the GUI
REM  Double-click this file. Handles paths WITH SPACES.
REM  If native tools (Chromium/playwright) are missing, installs
REM  them into .\browsers then starts the app. No separate setup.
REM ============================================================

cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: Cannot cd to app folder.
  pause
  exit /b 1
)

if not exist "data" mkdir "data"
if not exist "browsers" mkdir "browsers"

REM Portable Chromium for LLM browser tool (next to app, not user profile)
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"

set "ERRLOG=%~dp0data\last_launch_error.txt"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "EXITCODE=0"
set "PY_CMD="

echo ========================================
echo  AI Agent Studio
echo  Folder: %CD%
echo ========================================
echo.

REM ---- Resolve Python (prefer .venv) ----
if exist "%VENV_PY%" (
  set "PY_CMD=%VENV_PY%"
  goto :have_python
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Creating .venv first run...
  py -3 -m venv .venv
  if exist "%VENV_PY%" (
    set "PY_CMD=%VENV_PY%"
    goto :have_python
  )
  set "PY_CMD=py -3"
  goto :have_python
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Creating .venv first run...
  python -m venv .venv
  if exist "%VENV_PY%" (
    set "PY_CMD=%VENV_PY%"
    goto :have_python
  )
  set "PY_CMD=python"
  goto :have_python
)

(
  echo [%DATE% %TIME%] No Python found.
  echo Install Python 3.11+ from https://www.python.org/downloads/
  echo Then double-click Launch.bat again.
) > "%ERRLOG%"

echo ERROR: Python was not found.
echo See: data\last_launch_error.txt
echo.
type "%ERRLOG%"
echo.
pause
exit /b 1

:have_python
echo Using: %PY_CMD%
echo.

REM ---- Native tools: skip if ready, else install then continue ----
REM Check: chrome.exe under browsers\  AND  import playwright
set "NEED_SETUP=0"
if not exist "%VENV_PY%" set "NEED_SETUP=1"

dir /s /b "browsers\chrome.exe" >nul 2>&1
if errorlevel 1 set "NEED_SETUP=1"

if "%NEED_SETUP%"=="0" (
  "%VENV_PY%" -c "import playwright,pypdf" >nul 2>&1
  if errorlevel 1 set "NEED_SETUP=1"
)

if "%NEED_SETUP%"=="1" (
  echo Native tools missing or incomplete — installing into this folder...
  echo This runs once; later launches skip setup.
  echo.
  if exist "%VENV_PY%" (
    "%VENV_PY%" -m pip install -q -r requirements.txt
    if errorlevel 1 (
      echo WARNING: pip install had issues — trying ensure_native...
    )
    "%VENV_PY%" -m app.tools.ensure_native
  ) else (
    %PY_CMD% -m pip install -q -r requirements.txt
    %PY_CMD% -m app.tools.ensure_native
  )
  echo.
) else (
  echo Native tools OK — launching.
  echo.
)

echo Starting GUI...
echo.

if exist "%VENV_PY%" (
  "%VENV_PY%" -m app
  set "EXITCODE=%ERRORLEVEL%"
) else (
  %PY_CMD% -m app
  set "EXITCODE=%ERRORLEVEL%"
)

goto :finish

:finish
if not "%EXITCODE%"=="0" (
  echo.
  echo ========================================
  echo  App exited with code %EXITCODE%
  echo  Log: data\last_launch_error.txt
  echo  Tip: close this window and run Launch.bat again
  echo       ^(it will re-check native tools automatically^)
  echo ========================================
  echo [%DATE% %TIME%] Exit code %EXITCODE% >> "%ERRLOG%"
  pause
  exit /b %EXITCODE%
)

exit /b 0
