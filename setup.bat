@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo  SubScript setup
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  Python is not on PATH.
  echo  Trying winget install Python 3.11 ...
  winget install --id Python.Python.3.11 -e --accept-package-agreements --accept-source-agreements
  echo.
  echo  Close this window, open a new Command Prompt, then run setup.bat again.
  pause
  exit /b 1
)

python --version

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo  FFmpeg is not on PATH. Trying winget install ...
  winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
  echo  If ffmpeg is still missing after this, close CMD and open a new one.
)

if not exist ".venv\Scripts\python.exe" (
  echo  Creating .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo  Could not create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo  .venv already exists.
)

echo  Installing dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt
if errorlevel 1 (
  echo  pip install failed.
  pause
  exit /b 1
)

if not exist "config.yaml" (
  if exist "config.example.yaml" (
    copy /Y "config.example.yaml" "config.yaml" >nul
    echo  Created config.yaml
  )
)

echo.
echo  Setup finished. Double-click run-app.bat to start SubScript.
echo.
pause
exit /b 0
