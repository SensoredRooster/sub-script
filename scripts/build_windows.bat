@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo.
echo  === sub-script Windows onedir build ===
echo  Output: dist\SubScript\SubScript.exe
echo.

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python not found on PATH. Install Python 3.11+ first.
    exit /b 1
  )
  set "PY=python"
) else (
  set "PY=py -3"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  %PY% -m venv .venv
  if errorlevel 1 exit /b 1
)

set "VPY=.venv\Scripts\python.exe"

echo Installing runtime + build deps ...
"%VPY%" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 exit /b 1

if not exist "config.yaml" (
  if exist "config.example.yaml" (
    copy /Y "config.example.yaml" "config.yaml" >nul
    echo Created config.yaml from example (for local smoke tests).
  )
)

echo.
echo Running PyInstaller (onedir) ...
"%VPY%" -m PyInstaller --noconfirm --clean SubScript.spec
if errorlevel 1 (
  echo.
  echo PyInstaller failed. See messages above.
  exit /b 1
)

set "DIST=dist\SubScript"

if exist "config.example.yaml" (
  copy /Y "config.example.yaml" "%DIST%\config.example.yaml" >nul
)
if not exist "%DIST%\config.yaml" (
  if exist "config.example.yaml" copy /Y "config.example.yaml" "%DIST%\config.yaml" >nul
)
if not exist "%DIST%\assets" mkdir "%DIST%\assets"
if exist "assets\.gitkeep" copy /Y "assets\.gitkeep" "%DIST%\assets\.gitkeep" >nul
copy /Y "scripts\FFMPEG_BESIDE_APP.txt" "%DIST%\FFMPEG_BESIDE_APP.txt" >nul

REM Copy ffmpeg.exe / ffprobe.exe beside the app when this PC has them on PATH.
for %%T in (ffmpeg ffprobe) do (
  if not exist "%DIST%\%%T.exe" (
    for /f "delims=" %%P in ('where %%T.exe 2^>nul') do (
      if not exist "%DIST%\%%T.exe" (
        copy /Y "%%P" "%DIST%\%%T.exe" >nul && echo   Copied %%T.exe beside the app from %%P
      )
    )
  )
)

echo.
echo  ============================================================
echo   Built:  %CD%\%DIST%\SubScript.exe
echo.
if exist "%DIST%\ffmpeg.exe" (
  echo   ffmpeg.exe is beside the app - the folder is ready to zip / install.
) else (
  echo   REQUIRED - place ffmpeg.exe ^(+ ffprobe.exe^) beside the app ^(not PATH-only^):
  echo     1. Download a Windows ffmpeg essentials zip
  echo     2. Copy bin\ffmpeg.exe and bin\ffprobe.exe into:
  echo          %CD%\%DIST%\
  echo     3. Double-click SubScript.exe
)
echo.
echo   See %DIST%\FFMPEG_BESIDE_APP.txt for details.
echo   Installer: scripts\build_installer.bat ^(needs Inno Setup 6^).
echo  ============================================================
echo.
exit /b 0
