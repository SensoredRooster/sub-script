## Windows .exe (onedir)

For-dummies product path: **double-click `SubScript.exe`**, browser opens — no Python install for end users.

### End users

1. Get the `SubScript` folder (from a builder).
2. **Copy `ffmpeg.exe` into that folder** (same place as `SubScript.exe`).  
   See `scripts/FFMPEG_BESIDE_APP.txt`. This is the supported install — do **not** rely on PATH alone.
3. Double-click **`SubScript.exe`** (or `run-app.bat`, which prefers the exe when `dist\\SubScript\\SubScript.exe` exists).
4. Browser → **http://127.0.0.1:8787** → choose **Create & Publish a Clip** → drop a VOD → Make clip → Approve / Trim / Reject. Choose **Put My Content on Autopilot** for the guided folder-based workflow builder.

### Builders (Windows PC with Python)

```bat
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt -r requirements-dev.txt
scripts\\build_windows.bat
```

Output: **`dist\\SubScript\\SubScript.exe`** (PyInstaller **onedir**, not one-file — so ffmpeg can sit beside the app).

| File | Role |
|------|------|
| `SubScript.spec` | onedir PyInstaller spec |
| `scripts\\build_windows.bat` | one-click Windows build |
| `scripts\\run_exe.py` | frozen entry → `--app` + browser |
| `requirements-dev.txt` | `pyinstaller` (builders only) |
| `scripts\\FFMPEG_BESIDE_APP.txt` | ship ffmpeg beside the exe |

After build, copy `ffmpeg.exe` into `dist\\SubScript\\`, then zip/share that folder.

Smoke (any OS; does **not** run Windows PyInstaller):

```bat
python scripts\\smoke_windows_packaging.py
```

Inno Setup installer: optional later — bat + onedir folder is enough for now.

**Note:** Scripts/spec are for a Windows builder to run locally. This PR does not claim a Windows PyInstaller run was executed in CI/agent.

## Code signing (Azure Artifact Signing)

`scripts\build_installer.bat --sign` (or `set SUBSCRIPT_SIGN=1`) signs `dist\SubScript\SubScript.exe` before Inno Setup packs it, then signs `installer\Output\SubScript-Setup-<version>.exe`. Without the flag, builds are unsigned as before.

- Prerequisites: `winget install Microsoft.Azure.ArtifactSigningClientTools` (signtool x64 + `Azure.CodeSigning.Dlib.dll`), `winget install Microsoft.AzureCLI`, then `az login` as an account with the **Artifact Signing Certificate Profile Signer** role.
- Settings: `scripts\signing\metadata.json` (endpoint `https://eus.codesigning.azure.net`, account `SensoredRooster`, profile `Sensoredrooster`; publisher **Branden Nail**).
- `scripts\sign_windows.ps1 -Files <exe>` runs `signtool sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib <dll> /dmdf metadata.json` and then `signtool verify /pa /v`. Override with `-SignToolPath`, `-DlibPath`, `-MetadataPath` or `SUBSCRIPT_SIGNTOOL` / `SUBSCRIPT_SIGN_DLIB`.
