# Setup checklist

The app home page shows a **Setup checklist** card with green / yellow / red rows so you can see at a glance what is ready:

1. ffmpeg (sidecar or PATH)
2. config.yaml present
3. logo present
4. live / hotkey source configured
5. YouTube enabled + secrets (or dry-run)
6. captions engine (demo vs Whisper)
7. music bed present
8. detect / OCR (optional)

Each row includes a one-line fix hint. Live JSON: `GET /setup/status`.

```bat
python scripts\smoke_setup_status.py
```
