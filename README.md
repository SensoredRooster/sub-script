# sub-script

Hotkey / VOD clip → brand → **review gate** → YouTube Shorts.

Nothing uploads until you **Approve as-is**, **Trim & approve**, or **Reject**.

## Product shape

| Mode | What it does |
|------|----------------|
| **Live** | Hotkey grabs the last ~30s from a buffer/export → brand → review queue |
| **VOD** *(next)* | Upload a full recording → auto-cut → music/subs → same review queue |
| **Review** | Local UI: watch clip, approve, quick trim, or reject |

## Setup (Windows-friendly)

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

3. Drop sample VODs / replay exports into **`test-clips/`** on your machine. Video files are gitignored — they stay local and are **not** pushed to GitHub.

## Run

Produce a clip into the review queue (last 30 seconds by default):

```bat
python -m subscript --source test-clips\your.mp4
```

Clip a specific highlight from a longer VOD (`--start` + `--duration`; times can be seconds or `HH:MM:SS`):

```bat
python -m subscript --source test-clips\vod.mp4 --start 3720 --duration 45
```

```bat
python -m subscript --source test-clips\vod.mp4 --start 1:02:00 --duration 00:00:45
```

Open the review UI (prints **http://127.0.0.1:8787** in the terminal):

```bat
python -m subscript --review
```

If the queue is empty, enqueue a clip first, then refresh the page.

Hotkey watch (same queue):

```bat
python -m subscript --watch --source path\to\buffer-export.mp4
```

## First-run tips

| Problem | What to do |
|---------|------------|
| `ffmpeg not found` | Install via winget/choco, reopen the terminal |
| `config.yaml not found` | `copy config.example.yaml config.yaml` |
| `Source video not found` | Pass a real file under `test-clips\` |
| Empty review UI | Run `--source` once, then refresh |

## Roadmap

1. Hotkey / file clip + brand + review gate (approve / trim / reject)
2. Next: real OBS/replay rolling buffer
3. Next: VOD upload + auto chapter/cut suggestions
4. Later: music bed + captions on the review item
5. Later: Warzone kill-feed OCR for fully hands-off detection

## License

Private — SensoredRooster.
