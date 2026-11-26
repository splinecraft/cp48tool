@echo off
rem Launch the cp48tool editor. The venv lives outside OneDrive on purpose.
set VENV=%LOCALAPPDATA%\cp48tool\venv
if not exist "%VENV%\Scripts\pythonw.exe" (
  rem Prefer the py launcher: on many PCs "python" is only the Microsoft Store stub.
  set PY=
  where py >nul 2>nul && set PY=py
  if not defined PY ( where python >nul 2>nul && set PY=python )
  if not defined PY (
    echo Python not found. Install it from python.org ^(with the py launcher^) and try again.
    pause & exit /b 1
  )
  echo Creating environment in %VENV% ...
  call %%PY%% -m venv "%VENV%" || (pause & exit /b 1)
  "%VENV%\Scripts\python.exe" -m pip install -q PySide6 || (pause & exit /b 1)
)
cd /d "%~dp0"
start "" "%VENV%\Scripts\pythonw.exe" -m cp48tool gui %*
