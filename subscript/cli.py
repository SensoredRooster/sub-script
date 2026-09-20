"""CLI entry: dry-run, hotkey watch, app / review UI."""

from __future__ import annotations

import argparse
from pathlib import Path

from subscript.config import load_config
from subscript.hotkey import listen
from subscript.pipeline import run_pipeline


def parse_time(value: str) -> float:
    """Parse seconds or HH:MM:SS / MM:SS into a float second offset."""
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("time value must not be empty")
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}; use seconds or HH:MM:SS"
        ) from exc
    raise argparse.ArgumentTypeError(
        f"invalid time {value!r}; use seconds or HH:MM:SS"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sub-script",
        description="Hotkey clip \u2192 brand \u2192 review \u2192 YouTube",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--source", type=Path, help="Input video (recording / replay export)")
    parser.add_argument(
        "--start",
        type=parse_time,
        default=None,
        metavar="SECONDS",
        help="Clip start offset in seconds or HH:MM:SS (omit to take last N seconds)",
    )
    parser.add_argument(
        "--duration",
        type=parse_time,
        default=None,
        metavar="SECONDS",
        help="Clip length in seconds or HH:MM:SS (default: buffer_seconds / 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Produce clip and queue for review (no live YouTube)",
    )
    parser.add_argument("--watch", action="store_true", help="Listen for hotkey and run pipeline")
    parser.add_argument(
        "--app",
        action="store_true",
        help="Open desktop app UI (drop VOD \u2192 clip \u2192 review)",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Same as --app (local review / clip UI)",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    if args.app or args.review:
        from subscript.review_ui import main as review_main

        review_main()
        return

    if args.watch:
        if not args.source:
            raise SystemExit(
                "--watch requires --source pointing at the buffer/export file.\n"
                "  Example: python -m subscript --watch --source test-clips\\replay.mp4"
            )
        if not args.source.exists():
            raise SystemExit(_missing_source_message(args.source))

        def fire() -> None:
            print("Hotkey fired \u2014 running pipeline\u2026")
            try:
                run_pipeline(args.source, cfg, dry_run=True)
            except RuntimeError as exc:
                print(exc)

        listen(cfg.get("hotkey") or "ctrl+shift+c", fire)
        return

    if not args.source:
        raise SystemExit(
            "Missing --source.\n"
            "  Desktop app (no terminal needed after launch):\n"
            "    Double-click run-app.bat   or   python -m subscript --app\n"
            "  CLI clip: python -m subscript --source test-clips\\your.mp4\n"
            "  Hotkey:   python -m subscript --watch --source path\\to\\export.mp4"
        )

    if not args.source.exists():
        raise SystemExit(_missing_source_message(args.source))

    try:
        run_pipeline(
            args.source,
            cfg,
            dry_run=args.dry_run or True,
            start=args.start,
            duration=args.duration,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


def _missing_source_message(path: Path) -> str:
    return (
        f"Source video not found: {path}\n"
        "  Drop a VOD / replay export under test-clips\\ (local only \u2014 not on GitHub),\n"
        "  then pass that path, e.g.:\n"
        "    python -m subscript --source test-clips\\your.mp4\n"
        "  Or use the desktop app: double-click run-app.bat"
    )


if __name__ == "__main__":
    main()
