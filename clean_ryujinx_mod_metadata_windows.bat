@echo off
setlocal

set "MOD_ROOT=%APPDATA%\Ryujinx\mods\contents"
if not "%~1"=="" set "MOD_ROOT=%~1"

echo Cleaning macOS metadata below:
echo %MOD_ROOT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%MOD_ROOT%' -Recurse -Force -File -Include '.DS_Store','._*' | Remove-Item -Force"

echo Done.
pause
