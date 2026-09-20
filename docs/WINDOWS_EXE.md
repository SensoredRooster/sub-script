## Windows .exe (onedir)

For-dummies product path: **double-click `SubScript.exe`**, browser opens — no Python install for end users.

### End users

1. Get the `SubScript` folder (from a builder).
2. **Copy `ffmpeg.exe` into that folder** (same place as `SubScript.exe`).  
   See `scripts/FFMPEG_BESIDE_APP.txt`. This is the supported install — do **not** rely on PATH alone.
3. Double-click **`SubScript.exe`** (or `run-app.bat`, which prefers the exe when `dist\\SubScript\\SubScript.exe` exists).
4. Browser → **http://127.0.0.1:8787** → drop a VOD → Make clip → Approve / Trim / Reject.

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
