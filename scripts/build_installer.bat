@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo.
echo  === sub-script installer build (Inno Setup 6) ===
echo.

set "ISCC="
where ISCC.exe >nul 2>&1 && set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo ERROR: Inno Setup 6 ^(ISCC.exe^) not found.
  echo   Install it once:   winget install JRSoftware.InnoSetup
  echo   then run scripts\build_installer.bat again.
  exit /b 1
)

if not exist "dist\SubScript\SubScript.exe" (
  echo dist\SubScript\SubScript.exe not found - running scripts\build_windows.bat first ...
  call scripts\build_windows.bat
  if errorlevel 1 exit /b 1
)

if not exist "dist\SubScript\ffmpeg.exe" (
  echo.
  echo  WARNING: dist\SubScript\ffmpeg.exe is missing. The installer will still build,
  echo  but users must add ffmpeg.exe themselves ^(see scripts\FFMPEG_BESIDE_APP.txt^).
  echo.
)

set "SUBSCRIPT_VERSION="
if exist ".venv\Scripts\python.exe" (
  for /f "usebackq delims=" %%V in (`.venv\Scripts\python.exe -c "import subscript;print(subscript.__version__)"`) do set "SUBSCRIPT_VERSION=%%V"
)
if not defined SUBSCRIPT_VERSION set "SUBSCRIPT_VERSION=0.1.0"
echo  Version: %SUBSCRIPT_VERSION%
echo  Compiler: %ISCC%
echo.

"%ISCC%" /Qp "installer\SubScript.iss"
if errorlevel 1 (
  echo.
  echo ISCC failed. See messages above.
  exit /b 1
)

echo.
echo  ============================================================
echo   Built: %CD%\installer\Output\SubScript-Setup-%SUBSCRIPT_VERSION%.exe
echo   Share that single file. It installs per-user ^(no admin^) to
echo   %%LOCALAPPDATA%%\Programs\SubScript and adds a Start menu entry.
echo  ============================================================
echo.
exit /b 0
