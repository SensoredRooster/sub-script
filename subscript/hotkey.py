"""Global hotkey listener (pynput) with fail-soft fires + optional notify."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

from pynput import keyboard

log = logging.getLogger("subscript.hotkey")


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


def notify_fired(message: str = "sub-script: hotkey fired — processing…") -> None:
    """Best-effort user feedback: Windows toast, else console beep + print."""
    print(message, flush=True)
    # Console beep (works on most terminals / Windows)
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass

    if sys.platform == "win32":
        try:
            # winsound beep as a reliable fallback
            import winsound

            winsound.MessageBeep(winsound.MB_OK)
        except Exception:  # noqa: BLE001
            pass
        try:
            # Optional win10toast if installed; never required
            from win10toast import ToastNotifier  # type: ignore

            ToastNotifier().show_toast(
                "sub-script",
                message,
                duration=3,
                threaded=True,
            )
        except Exception:  # noqa: BLE001
            pass


def listen(hotkey_spec: str, on_fire: Callable[[], None]) -> None:
    """Block the current thread listening for the hotkey (CLI --watch)."""
    combo = parse_hotkey(hotkey_spec)
    print(f"Listening for {hotkey_spec!r} ({combo}). Ctrl+C to quit.")

    def _handler() -> None:
        try:
            on_fire()
        except Exception as exc:  # noqa: BLE001 — keep listener alive
            log.exception("Hotkey pipeline error (listener stays armed)")
            print(f"Pipeline error (still listening): {exc}", flush=True)

    with keyboard.GlobalHotKeys({combo: _handler}) as h:
        h.join()


class HotkeyWatcher:
    """Background-thread hotkey watcher for the app UI.

    Fail-soft: any exception inside on_fire is logged; the listener keeps
    running. start()/stop() are idempotent.
    """

    def __init__(
        self,
        hotkey_spec: str,
        on_fire: Callable[[], None],
        *,
        notify: bool = True,
    ) -> None:
        self.hotkey_spec = hotkey_spec or "ctrl+shift+c"
        self._on_fire = on_fire
        self.notify = notify
        self._thread: threading.Thread | None = None
        self._listener: keyboard.GlobalHotKeys | None = None
        self._armed = False
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.last_ok: str | None = None
        self.fire_count = 0

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def combo_display(self) -> str:
        return self.hotkey_spec

    def _safe_fire(self) -> None:
        if self.notify:
            try:
                notify_fired()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._on_fire()
            self.fire_count += 1
            self.last_ok = "Queued for review"
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 — never kill the watcher
            self.last_error = str(exc)
            log.exception("Hotkey fire failed (watcher stays armed)")
            print(f"Hotkey fire failed (still armed): {exc}", flush=True)

    def start(self) -> None:
        with self._lock:
            if self._armed:
                return
            combo = parse_hotkey(self.hotkey_spec)

            def run() -> None:
                try:
                    self._listener = keyboard.GlobalHotKeys({combo: self._safe_fire})
                    self._listener.start()
                    self._armed = True
                    print(
                        f"Live hotkey armed: {self.hotkey_spec!r} ({combo})",
                        flush=True,
                    )
                    self._listener.join()
                except Exception as exc:  # noqa: BLE001
                    self.last_error = f"Watcher failed to start: {exc}"
                    log.exception("Hotkey watcher crashed")
                    print(self.last_error, flush=True)
                finally:
                    self._armed = False
                    self._listener = None

            self._thread = threading.Thread(
                target=run, name="subscript-hotkey", daemon=True
            )
            self._thread.start()
            # Brief wait so status reflects armed quickly
            for _ in range(20):
                if self._armed or self.last_error:
                    break
                threading.Event().wait(0.05)

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
            self._armed = False
        if listener is not None:
            try:
                listener.stop()
            except Exception:  # noqa: BLE001
                pass
        print("Live hotkey disarmed.", flush=True)

    def status(self) -> dict:
        return {
            "armed": self._armed,
            "hotkey": self.hotkey_spec,
            "combo": parse_hotkey(self.hotkey_spec),
            "notify": self.notify,
            "fire_count": self.fire_count,
            "last_error": self.last_error,
            "last_ok": self.last_ok,
        }
