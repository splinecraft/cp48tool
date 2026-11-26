@echo off
rem Launch the cp48tool editor. The venv lives outside OneDrive on purpose.
set VENV=%LOCALAPPDATA%\cp48tool\venv
if not exist "%VENV%\Scripts\pythonw.exe" (
  echo Creating environment in %VENV% ...
  python -m venv "%VENV%" || exit /b 1
  "%VENV%\Scripts\python.exe" -m pip install -q PySide6 || exit /b 1
)
cd /d "%~dp0"
start "" "%VENV%\Scripts\pythonw.exe" -m cp48tool gui %*
