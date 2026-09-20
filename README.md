# sub-script

Hotkey clip buffer → brand → YouTube Shorts for stream highlights.

## v1 scope

Press a hotkey → cut the **previous ~30 seconds** from a rolling buffer → stamp brand overlay → upload (or dry-run) to **YouTube Shorts**.

Later (not in this scaffold): Warzone/CoD kill-feed OCR for fully automatic clips.

## Why Python

ffmpeg via subprocess, a simple hotkey listener, and the YouTube Data API all fit cleanly in one small package with fewer moving parts than a Node stack for local desktop capture.

## Architecture

```
[capture buffer] --hotkey--> [clip] --> [brand] --> [upload]
     rolling ring              ffmpeg      overlay     YouTube API
```

| Module | Role |
|--------|------|
| `subscript/buffer.py` | Rolling ring buffer (placeholder: file/path or ffmpeg segmenter) |
| `subscript/clip.py` | Export last N seconds with ffmpeg |
| `subscript/brand.py` | Logo / text watermark from config |
| `subscript/upload.py` | YouTube Shorts upload + dry-run mock |
| `subscript/hotkey.py` | Global hotkey → trigger pipeline |
| `subscript/config.py` | Load `config.yaml` + env |

## Setup

1. Install [ffmpeg](https://ffmpeg.org/) on your PATH.
2. Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
# drop a logo at assets/logo.png (optional)
```

3. Dry-run (no YouTube credentials):

```bash
python -m subscript.cli --dry-run --source path/to/sample.mp4
```

This cuts the last `buffer_seconds` from the source, applies branding if a logo exists, and writes under `out/` without uploading.

4. Live hotkey mode (after config):

```bash
python -m subscript.cli --watch
```

## Config knobs

See `config.example.yaml`:

- `hotkey` — e.g. `ctrl+shift+c`
- `buffer_seconds` — default `30`
- `brand.logo_path`, `brand.opacity`, corner placement
- `youtube.privacy`, category, title template
- `stream.resolution` — lock crop assumptions early (1080 vs 1440)

## Roadmap

1. **Now:** hotkey + buffer + brand + YouTube dry-run / upload stubs
2. **Next:** real rolling capture from game/OBS source
3. **Later:** kill-feed OCR (exact in-game name + resolution-locked crop)

## License

Private — SensoredRooster.
