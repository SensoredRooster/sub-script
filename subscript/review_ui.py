"""Local app UI: drop a VOD -> clip -> approve / trim / reject (+ live hotkey)."""

from __future__ import annotations

from subscript.live_app import create_app, main

__all__ = ["create_app", "main"]

if __name__ == "__main__":
    main()
