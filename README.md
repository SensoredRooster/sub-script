# sub-script

Hotkey / VOD clip → brand → **review gate** → YouTube Shorts.

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
4. Drop a VOD (or Choose file) → leave **Last 30 seconds** (or pick custom start + length) → **Make clip**.
5. Preview the clip → **Approve as-is** / **Trim & approve** / **Reject**.

Leave the black `run-app.bat` window open while you work. Close it (or Ctrl+C) when you’re done.

> Later this launcher becomes a single `.exe`. For now, `run-app.bat` is the one-click start.

## Product shape

| Mode | What it does |
|------|----------------|
| **App** | Drop a VOD in the browser → clip → same review queue |
| **Live** | Hotkey grabs the last ~30s from a buffer/export → brand → review queue |
| **Review** | Local UI: watch clip, approve, quick trim, or reject |

## Builder / CLI (optional)

Same engine; use when you prefer the terminal.

Produce a clip into the review queue (last 30 seconds by default):

```bat
python -m subscript --source test-clips\your.mp4
```

Clip a specific highlight (`--start` + `--duration`; seconds or `HH:MM:SS`):

```bat
python -m subscript --source test-clips\vod.mp4 --start 3720 --duration 45
```

```bat
python -m subscript --source test-clips\vod.mp4 --start 1:02:00 --duration 00:00:45
```

Open the app / review UI without the bat file:

```bat
python -m subscript --app
```

(`--review` is the same as `--app`.)

Hotkey watch:

```bat
python -m subscript --watch --source path\to\buffer-export.mp4
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
| `Source video not found` | Choose a real file in the app, or pass a path under `test-clips\` |
| Empty review list | Use **Make clip** above the list, then wait for the page to reload |
| Browser didn’t open | Visit http://127.0.0.1:8787 while `run-app.bat` is running |

## Roadmap

1. Hotkey / file clip + brand + review gate (approve / trim / reject)
2. Desktop app home: drop VOD → clip → review *(this PR)*
3. Next: real OBS/replay rolling buffer
4. Next: VOD auto chapter/cut suggestions
5. Later: music bed + captions on the review item
6. Later: Warzone kill-feed OCR for fully hands-off detection
7. Later: package as `.exe` (PyInstaller) from `run-app.bat`

## License

Private — SensoredRooster.
