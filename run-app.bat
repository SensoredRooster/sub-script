@echo off
setlocal
cd /d "%~dp0"

REM Prefer built onedir exe when present (double-click product path)
if exist "dist\SubScript\SubScript.exe" (
  echo.
  echo  Starting SubScript.exe ...
  echo  Browser should open at http://127.0.0.1:8787
  echo  Leave this window open while you use the app.
  echo.
  if not exist "dist\SubScript\ffmpeg.exe" (
    if not exist "dist\SubScript\ffmpeg\bin\ffmpeg.exe" (
      if not exist "dist\SubScript\bin\ffmpeg.exe" (
        echo  NOTE: ffmpeg.exe not found beside the app yet.
        echo  Copy ffmpeg.exe into dist\SubScript\ — see scripts\FFMPEG_BESIDE_APP.txt
        echo.
      )
    )
  )
  "dist\SubScript\SubScript.exe"
  set EXITCODE=%ERRORLEVEL%
  if not "%EXITCODE%"=="0" (
    echo.
    echo  App exited with an error. See messages above.
    pause
  )
  exit /b %EXITCODE%
)

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  First-time setup needed:
  echo    1. Install Python 3.11+ from https://python.org
  echo    2. Install ffmpeg:  winget install ffmpeg
  echo       ^(for the .exe build, copy ffmpeg.exe beside SubScript.exe — see scripts\FFMPEG_BESIDE_APP.txt^)
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
