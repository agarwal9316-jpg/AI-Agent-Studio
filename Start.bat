@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================
REM  AI Agent Studio — Start (PC portable)
REM  Double-click this file to run.
REM  Delegates to Launch.bat (venv + native tools).
REM ============================================

title AI Agent Studio
echo ========================================
echo   AI Agent Studio
echo ========================================
echo.
echo Portable Windows GUI — multi-agent chat,
echo company workflows, tools, and local knowledge.
echo.
echo Tip: Optional OpenAI-compatible API key in Settings.
echo.

if exist "Launch.bat" (
  call "%~dp0Launch.bat"
  exit /b %ERRORLEVEL%
)

echo ERROR: Launch.bat not found next to Start.bat
pause
exit /b 1
