@echo off
setlocal
cd /d "%~dp0PAKPY"
py -3 main.py
if errorlevel 1 (
  echo.
  echo PAKPY konnte nicht gestartet werden. Installiere die Windows-Abhaengigkeiten mit install_windows_deps.bat.
  pause
)
