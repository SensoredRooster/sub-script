@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  First-time setup needed:
  echo    1. Install Python 3.11+ from https://python.org
  echo    2. Install ffmpeg:  winget install ffmpeg
  echo    3. In this folder, run:
  echo         python -m venv .venv
  echo         .venv\Scripts\pip install -r requirements.txt
  echo    4. Double-click run-app.bat again
  echo.
  pause
  exit /b 1
)

if not exist "config.yaml" (
  if exist "config.example.yaml" (
    copy /Y "config.example.yaml" "config.yaml" >nul
    echo Created config.yaml from example.
  )
)

echo.
echo  Starting sub-script…
echo  A browser window should open at http://127.0.0.1:8787
echo  Leave this window open while you use the app.
echo  Press Ctrl+C here to quit.
echo.

".venv\Scripts\python.exe" -m subscript --app
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo  App exited with an error. See messages above.
  pause
)
exit /b %EXITCODE%
