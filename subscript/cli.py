"""CLI entry: dry-run or hotkey watch."""

from __future__ import annotations

import argparse
from pathlib import Path

from subscript.config import load_config
from subscript.hotkey import listen
from subscript.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sub-script", description="Hotkey clip → brand → YouTube")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--source", type=Path, help="Input video (recording / replay export)")
    parser.add_argument("--dry-run", action="store_true", help="Skip YouTube; write mock metadata")
    parser.add_argument("--watch", action="store_true", help="Listen for hotkey and run pipeline")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)

    if args.watch:
        if not args.source:
            raise SystemExit("--watch requires --source pointing at the buffer/export file")

        def fire() -> None:
            print("Hotkey fired — running pipeline…")
            run_pipeline(args.source, cfg, dry_run=True)

        listen(cfg.get("hotkey") or "ctrl+shift+c", fire)
        return

    if not args.source:
        raise SystemExit("Provide --source path/to/video.mp4 (or use --watch)")

    run_pipeline(args.source, cfg, dry_run=args.dry_run or True)


if __name__ == "__main__":
    main()
