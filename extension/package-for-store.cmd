@echo off
setlocal
cd /d "%~dp0"
echo Packaging extension from: %cd%
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0package-for-store.ps1"
if errorlevel 1 (
  echo.
  echo FAILED. If you see an error above, copy it when asking for help.
  pause
  exit /b 1
)
echo.
echo Done. Your zip is in the dist folder.
pause
