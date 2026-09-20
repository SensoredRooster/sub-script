"""Global hotkey listener (pynput)."""

from __future__ import annotations

from typing import Callable

from pynput import keyboard


def parse_hotkey(spec: str) -> str:
    """Normalize config string for pynput.GlobalHotKeys.

    Example: ctrl+shift+c -> <ctrl>+<shift>+c
    """
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    mapped = []
    for p in parts:
        if p in {"ctrl", "control"}:
            mapped.append("<ctrl>")
        elif p in {"alt", "option"}:
            mapped.append("<alt>")
        elif p in {"shift"}:
            mapped.append("<shift>")
        elif p in {"cmd", "super", "win", "meta"}:
            mapped.append("<cmd>")
        else:
            mapped.append(p)
    return "+".join(mapped)


def listen(hotkey_spec: str, on_fire: Callable[[], None]) -> None:
    combo = parse_hotkey(hotkey_spec)
    print(f"Listening for {hotkey_spec!r} ({combo}). Ctrl+C to quit.")

    def _handler() -> None:
        try:
            on_fire()
        except Exception as exc:  # noqa: BLE001 — keep listener alive
            print(f"Pipeline error: {exc}")

    with keyboard.GlobalHotKeys({combo: _handler}) as h:
        h.join()
