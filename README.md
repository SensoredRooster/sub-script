# sub-script

Hotkey / VOD clip -> brand -> **review gate** -> YouTube Shorts.

Nothing uploads until you **Approve as-is**, **Trim & approve**, or **Reject**.

## For users (no terminal)

1. One-time setup (ask a friend if needed): install **Python 3.11+**, **ffmpeg** (`winget install ffmpeg`), then in this folder:
   ```bat
   python -m venv .venv
   .venv\\Scripts\\pip install -r requirements.txt
   copy config.example.yaml config.yaml
   ```
2. **Double-click `run-app.bat`**.
3. Your browser opens to **http://127.0.0.1:8787**.
4. Drop a VOD (or Choose file) -> leave **Last 30 seconds** (or pick custom start + length) -> **Make clip**.
5. Preview the clip -> **Approve as-is** / **Trim & approve** / **Reject**.

**Branding (on the same home page):** upload a PNG logo, pick a corner + opacity, hit **Save**. That writes `assets/logo.png` and updates `config.yaml` so every future Make clip auto-brands - no folder hunting.

Leave the black `run-app.bat` window open while you work. Close it (or Ctrl+C) when you're done.

> Prefer a double-click `.exe`? See **[docs/WINDOWS_EXE.md](docs/WINDOWS_EXE.md)** — PyInstaller **onedir** `SubScript.exe` with **`ffmpeg.exe` beside it** (not PATH-only). `run-app.bat` prefers the exe when `dist\\SubScript\\SubScript.exe` exists.

## Live mode (hotkey while you stream)

One-screen setup for dummies:

1. In **OBS** → Settings → Output → Replay Buffer: turn it **On**. Set the replay length to at least your `buffer_seconds` (default **30**).
2. Note where OBS saves replays (Output path / Recording path). Either:
   - Save the **exact replay export `.mp4` path** into `config.yaml` as `live_source`, **or**
   - Put that folder path in `watch_folder` (sub-script grabs the **newest** video each time).
3. Confirm in `config.yaml`:
   ```yaml
   hotkey: "ctrl+shift+c"
   buffer_seconds: 30
   live_source: "C:\\Videos\\Replay.mp4"   # or leave empty
   watch_folder: "C:\\Videos\\OBS"        # or leave empty if live_source is set
   auto_enqueue: true
   notify: true
   ```
4. **Double-click `run-app.bat`**, open the home page, click **Start watcher** on the **Live hotkey** card (or run `python -m subscript --watch` in a second terminal).
5. While streaming, hit **Ctrl+Shift+C**. You should hear a beep / see a toast. sub-script clips the last N seconds → brand → H+V → captions → review queue.
6. In the app: preview → **Approve** (or Trim / Reject).

If one hotkey fire fails (missing file, ffmpeg hiccup), the app **keeps listening** — check the Live card / console for the error and try again.

CLI-only watch (no browser button):

```bat
python -m subscript --watch
```

Optional: `python -m subscript --watch --source path\\to\\replay.mp4`

## What Approve does now

Hitting **Approve as-is** (or approving after a trim) builds a **social export pack** under `out\\approved\\<id>\\`:

| File | Purpose |
|------|---------|
| `horizontal.mp4` | 16:9 landscape |
| `vertical.mp4` | 9:16 Shorts / TikTok / Reels |
| `vertical_captioned.mp4` | Same vertical with burned-in demo captions (`Clip | SUB`) when `captions.enabled` is true |
| `PLATFORMS.txt` | Checklist: YouTube Shorts, TikTok, IG Reels, Facebook, X, Rumble |
| `manifest.json` | Metadata for future upload hooks |

The folder opens automatically so you can drag files into each app. Captions use ffmpeg + a generated SRT (no Whisper) so Windows / Python 3.14 stays reliable. Toggle with `captions.enabled` in `config.yaml`.

**Platforms:** enabled entries under `platforms:` (and/or `youtube.enabled`) fan out on Approve — YouTube can live-upload; others build `for_<platform>/` packs. See **Platform checklist**. If `youtube.enabled` / `platforms.youtube.enabled` is `true`, Approve also uploads `vertical_captioned.mp4` (falls back to `vertical.mp4`) as a Short and shows the YouTube link on the success banner. If `youtube.enabled` is `false` (default), Approve only saves the local pack — safe for testing.

Smoke test:

```bat
python scripts\\smoke_captions.py
```

## Platform checklist

Approve can fan out to multiple platforms via `subscript/publish/`. **YouTube is the only live API by default.**

| Platform | Config flag | Default | What happens when enabled |
|----------|-------------|---------|---------------------------|
| **YouTube Shorts** | `youtube.enabled` **or** `platforms.youtube.enabled` | `false` | Live OAuth upload (see **Connect YouTube**) |
| **TikTok** | `platforms.tiktok.enabled` | `false` | Copies clip to `out/approved/<id>/for_tiktok/` + `POST_INSTRUCTIONS.txt` (`mode: manual`) |
| **Instagram** | `platforms.instagram.enabled` | `false` | Same pattern → `for_instagram/` |
| **Facebook** | `platforms.facebook.enabled` | `false` | Same pattern → `for_facebook/` |
| **X (Twitter)** | `platforms.twitter.enabled` | `false` | Same pattern → `for_twitter/` |
| **Rumble** | `platforms.rumble.enabled` | `false` | Same pattern → `for_rumble/` |

**Fail-soft:** if one platform errors, Approve still finishes and the banner lists per-platform status (`uploaded` / `manual` / `error` / `not_configured`).

**API stubs:** set `platforms.<name>.mode: api` to exercise the live-API path early — it raises `NotConfiguredError` with enablement steps until credentials are wired.

Example — manual TikTok + IG packs on every Approve (YouTube still off):

```yaml
platforms:
  youtube:
    enabled: false
  tiktok:
    enabled: true
    mode: manual
  instagram:
    enabled: true
    mode: manual
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
7. After a successful upload, the home page banner shows the YouTube URL (and still opens `out\\approved\\<id>\\`).

If secrets are missing, Approve still saves the local pack and shows a clear error (no silent failure).

Never commit `credentials.json`, `token.json`, or `.env`.

## Product shape

| Mode | What it does |
|------|----------------|
| **App** | Drop a VOD in the browser -> clip -> same review queue |
| **Live** | Hotkey grabs the last ~30s from a buffer/export -> brand -> H+V -> captions -> review queue |
| **Review** | Local UI: watch clip, approve, quick trim, or reject |

## Builder / CLI (optional)

Same engine; use when you prefer the terminal.

Produce a clip into the review queue (last 30 seconds by default):

```bat
python -m subscript --source test-clips\\\\your.mp4
```

Clip a specific highlight (`--start` + `--duration`; seconds or `HH:MM:SS`):

```bat
python -m subscript --source test-clips\\\\vod.mp4 --start 3720 --duration 45
```

```bat
python -m subscript --source test-clips\\\\vod.mp4 --start 1:02:00 --duration 00:00:45
```

Open the app / review UI without the bat file:

```bat
python -m subscript --app
```

(`--review` is the same as `--app`.)

Hotkey watch (uses `live_source` / `watch_folder` from config, or `--source`):

```bat
python -m subscript --watch
```

```bat
python -m subscript --watch --source path\\\\to\\\\buffer-export.mp4
```

## Setup details (Windows-friendly)

1. Install **ffmpeg** (for the shipped `.exe`, copy `ffmpeg.exe` **beside** `SubScript.exe` — see `scripts/FFMPEG_BESIDE_APP.txt`. For source/PATH installs):

   ```bat
   winget install ffmpeg
   ```

   Or with Chocolatey: `choco install ffmpeg`. Confirm with `ffmpeg -version`.

2. Python 3.11+ in a venv:

   ```bat
   python -m venv .venv
   .venv\\Scripts\\activate
   pip install -r requirements.txt
   copy .env.example .env
   copy config.example.yaml config.yaml
   ```

   On macOS/Linux, activate with `source .venv/bin/activate` and use `cp` instead of `copy`.

3. Sample VODs can live in **`test-clips/`** (gitignored) or you can drop any local file in the app.

## First-run tips

| Problem | What to do |
|---------|------------|
| `ffmpeg not found` | Copy `ffmpeg.exe` next to `SubScript.exe`, **or** install via winget/choco and reopen the terminal |
| `config.yaml not found` | `copy config.example.yaml config.yaml` (or just run `run-app.bat`) |
| `Source video not found` | Choose a real file in the app, or pass a path under `test-clips\\\\` |
| Live hotkey: no source | Set `live_source` or `watch_folder` in `config.yaml` |
| Live hotkey did nothing | Click **Start watcher** on the Live card; leave `run-app.bat` open |
| Empty review list | Use **Make clip** or fire the live hotkey, then wait for reload |
| Browser didn't open | Visit http://127.0.0.1:8787 while `run-app.bat` is running |
| YouTube secrets missing | Follow **Connect YouTube**; put OAuth JSON at `credentials.json` |
| YouTube login every time | Ensure `token.json` is writable in the project folder (not deleted) |

## Roadmap

1. Hotkey / file clip + brand + review gate (approve / trim / reject)
2. Desktop app home: drop VOD -> clip -> review *(shipped)*
3. Live hotkey → OBS replay / watch folder → auto enqueue *(shipped)*
4. Next: VOD auto chapter/cut suggestions
5. Captions burn-in on vertical (demo SRT) + social export pack on Approve *(shipped)*
6. YouTube Shorts upload on Approve (OAuth) *(shipped)*
7. Multi-platform publish stubs (TikTok / IG / FB / X / Rumble) on Approve *(shipped)*
8. Later: Whisper / real transcript captions; music bed
9. Later: Warzone kill-feed OCR for fully hands-off detection
10. Windows `.exe` onedir + ffmpeg-beside-app packaging *(this PR)* — see [docs/WINDOWS_EXE.md](docs/WINDOWS_EXE.md)
11. Later: Inno Setup installer wrapping `dist\\SubScript\\`

## License

Private - SensoredRooster.
