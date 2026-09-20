# sub-script

Hotkey / VOD clip -> brand -> **review gate** -> YouTube Shorts.

Nothing uploads until you **Approve as-is**, **Trim & approve**, or **Reject**.

## For users (no terminal)

1. One-time setup (ask a friend if needed): install **Python 3.11+**, **ffmpeg** (`winget install ffmpeg`), then in this folder:
   ```bat
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   copy config.example.yaml config.yaml
   ```
2. **Double-click `run-app.bat`**.
3. Your browser opens to **http://127.0.0.1:8787**.
4. Drop a VOD (or Choose file) -> leave **Last 30 seconds** (or pick custom start + length) -> **Make clip**.
5. Preview the clip -> **Approve as-is** / **Trim & approve** / **Reject**.

**Branding (on the same home page):** upload a PNG logo, pick a corner + opacity, hit **Save**. That writes `assets/logo.png` and updates `config.yaml` so every future Make clip auto-brands - no folder hunting.

Leave the black `run-app.bat` window open while you work. Close it (or Ctrl+C) when you're done.

> Later this launcher becomes a single `.exe`. For now, `run-app.bat` is the one-click start.

## What Approve does now

Hitting **Approve as-is** (or approving after a trim) builds a **social export pack** under `out\approved\<id>\`:

| File | Purpose |
|------|---------|
| `horizontal.mp4` | 16:9 landscape |
| `vertical.mp4` | 9:16 Shorts / TikTok / Reels |
| `vertical_captioned.mp4` | Same vertical with burned-in demo captions (`Clip | SUB`) when `captions.enabled` is true |
| `PLATFORMS.txt` | Checklist: YouTube Shorts, TikTok, IG Reels, Facebook, X, Rumble |
| `manifest.json` | Metadata for future upload hooks |

The folder opens automatically so you can drag files into each app. Captions use ffmpeg + a generated SRT (no Whisper) so Windows / Python 3.14 stays reliable. Toggle with `captions.enabled` in `config.yaml`.

**YouTube:** if `youtube.enabled` is `true` in `config.yaml`, Approve also uploads `vertical_captioned.mp4` (falls back to `vertical.mp4`) as a Short and shows the YouTube link on the success banner. If `youtube.enabled` is `false` (default), Approve only saves the local pack — safe for testing.

Smoke test:

```bat
python scripts\smoke_captions.py
```

## Connect YouTube (optional)

Do this once when you want Approve to publish Shorts for real. Leave `youtube.enabled: false` until the steps below work.

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create (or pick) a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - If asked, set the OAuth consent screen (External is fine for personal use; add your Google account as a test user).
   - Application type: **Desktop app**. Download the JSON.
4. Save that file in this project folder as **`credentials.json`** (same folder as `config.yaml`).  
   Or put it elsewhere and set `youtube.client_secrets_file` / `YOUTUBE_CLIENT_SECRETS` in `.env`.
5. In `config.yaml`:
   ```yaml
   youtube:
     enabled: true
     privacy: "unlisted"   # or private / public
     client_secrets_file: "credentials.json"
   ```
6. Restart the app (`run-app.bat`). Make a clip → **Approve**.  
   The first time, your browser opens a Google login — allow access. sub-script saves **`token.json`** (gitignored) so you are not asked again.
7. After a successful upload, the home page banner shows the YouTube URL (and still opens `out\approved\<id>\`).

If secrets are missing, Approve still saves the local pack and shows a clear error (no silent failure).

Never commit `credentials.json`, `token.json`, or `.env`.

## Product shape

| Mode | What it does |
|------|----------------|
| **App** | Drop a VOD in the browser -> clip -> same review queue |
| **Live** | Hotkey grabs the last ~30s from a buffer/export -> brand -> review queue |
| **Review** | Local UI: watch clip, approve, quick trim, or reject |

## Builder / CLI (optional)

Same engine; use when you prefer the terminal.

Produce a clip into the review queue (last 30 seconds by default):

```bat
python -m subscript --source test-clips\\your.mp4
```

Clip a specific highlight (`--start` + `--duration`; seconds or `HH:MM:SS`):

```bat
python -m subscript --source test-clips\\vod.mp4 --start 3720 --duration 45
```

```bat
python -m subscript --source test-clips\\vod.mp4 --start 1:02:00 --duration 00:00:45
```

Open the app / review UI without the bat file:

```bat
python -m subscript --app
```

(`--review` is the same as `--app`.)

Hotkey watch:

```bat
python -m subscript --watch --source path\\to\\buffer-export.mp4
```

## Setup details (Windows-friendly)

1. Install **ffmpeg** on your PATH (restart the terminal afterward):

   ```bat
   winget install ffmpeg
   ```

   Or with Chocolatey: `choco install ffmpeg`. Confirm with `ffmpeg -version`.

2. Python 3.11+ in a venv:

   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   copy config.example.yaml config.yaml
   ```

   On macOS/Linux, activate with `source .venv/bin/activate` and use `cp` instead of `copy`.

3. Sample VODs can live in **`test-clips/`** (gitignored) or you can drop any local file in the app.

## First-run tips

| Problem | What to do |
|---------|------------|
| `ffmpeg not found` | Install via winget/choco, reopen the terminal |
| `config.yaml not found` | `copy config.example.yaml config.yaml` (or just run `run-app.bat`) |
| `Source video not found` | Choose a real file in the app, or pass a path under `test-clips\\` |
| Empty review list | Use **Make clip** above the list, then wait for the page to reload |
| Browser didn't open | Visit http://127.0.0.1:8787 while `run-app.bat` is running |
| YouTube secrets missing | Follow **Connect YouTube**; put OAuth JSON at `credentials.json` |
| YouTube login every time | Ensure `token.json` is writable in the project folder (not deleted) |

## Roadmap

1. Hotkey / file clip + brand + review gate (approve / trim / reject)
2. Desktop app home: drop VOD -> clip -> review *(shipped)*
3. Next: real OBS/replay rolling buffer
4. Next: VOD auto chapter/cut suggestions
5. Captions burn-in on vertical (demo SRT) + social export pack on Approve *(shipped)*
6. YouTube Shorts upload on Approve (OAuth) *(this PR)*
7. Later: Whisper / real transcript captions; music bed
8. Later: Warzone kill-feed OCR for fully hands-off detection
9. Later: package as `.exe` (PyInstaller) from `run-app.bat`

## License

Private - SensoredRooster.
