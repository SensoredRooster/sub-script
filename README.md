# sub-script

Hotkey / VOD clip → brand → **review gate** → YouTube Shorts.

Nothing uploads until you **Approve as-is**, **Trim & approve**, or **Reject**.

## Product shape

| Mode | What it does |
|------|----------------|
| **Live** | Hotkey grabs the last ~30s from a buffer/export → brand → review queue |
| **VOD** *(next)* | Upload a full recording → auto-cut → music/subs → same review queue |
| **Review** | Local UI: watch clip, approve, quick trim, or reject |

## Setup

1. Install [ffmpeg](https://ffmpeg.org/) on your PATH.
2. Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
```

## Run

Produce a clip into the review queue:

```bash
python -m subscript --source path/to/vod-or-replay.mp4
```

Open the review UI (http://127.0.0.1:8787):

```bash
python -m subscript --review
# or: python -m subscript.review_ui
```

Hotkey watch (same queue):

```bash
python -m subscript --watch --source path/to/buffer-export.mp4
```

## Roadmap

1. Hotkey / file clip + brand + review gate (approve / trim / reject)
2. Next: real OBS/replay rolling buffer
3. Next: VOD upload + auto chapter/cut suggestions
4. Later: music bed + captions on the review item
5. Later: Warzone kill-feed OCR for fully hands-off detection

## License

Private — SensoredRooster.
