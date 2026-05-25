@echo off
setlocal
cd /d "%~dp0CONVERTERS"
py -3 cmdl_to_obj_gui.py
if errorlevel 1 (
  echo.
  echo Der CMDL-Konverter konnte nicht gestartet werden. Installiere die Windows-Abhaengigkeiten mit install_windows_deps.bat.
  pause
)
