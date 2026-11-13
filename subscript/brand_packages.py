"""Brand packages: named bundles of logo, captions, music, intro/outro.

The Branding page is a library of packages. The pipeline auto-selects one per
clip — pinned (always the same), rotate (round-robin), or, once YouTube stats
have been collected, performance-weighted toward what works.

Everything is fail-soft and stdlib-only. Legacy single-brand configs are
migrated into a "Default" package on first access, so old installs keep
working unchanged.
"""

from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

from subscript.config import DEFAULT_LOGO_REL
from subscript.config_polish import DEFAULT_MUSIC_REL

DEFAULT_PACKAGE_NAME = "Default"
_SELECTION_KEY = "brand_selection"
_PACKAGES_KEY = "brand_packages"
_STATE_FILE = "brand_state.json"

_BRAND_KEYS = ("logo_path", "position", "opacity", "margin_px", "intro_paths", "outro_paths")


def _default_brand(cfg: dict[str, Any]) -> dict[str, Any]:
    brand = dict(cfg.get("brand") or {})
    out = {k: brand.get(k) for k in _BRAND_KEYS if brand.get(k) not in (None, "", [])}
    out.setdefault("logo_path", DEFAULT_LOGO_REL)
    out.setdefault("position", "bottom_right")
    out.setdefault("opacity", 0.85)
    out.setdefault("margin_px", 24)
    return out


def _default_captions(cfg: dict[str, Any]) -> dict[str, Any]:
    caps = dict(cfg.get("captions") or {})
    return {"enabled": bool(caps.get("enabled", True)), "engine": str(caps.get("engine") or "auto")}


def _default_music(cfg: dict[str, Any]) -> dict[str, Any]:
    music = dict(cfg.get("music") or {})
    return {
        "enabled": bool(music.get("enabled", True)),
        "path": music.get("path") or DEFAULT_MUSIC_REL,
        "volume": float(music.get("volume") if music.get("volume") is not None else 0.10),
    }


def ensure_packages(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Migrate legacy single-brand config into a Default package (in place)."""
    pkgs = cfg.get(_PACKAGES_KEY)
    if isinstance(pkgs, list) and pkgs:
        return pkgs
    pkg = {
        "id": "default",
        "name": DEFAULT_PACKAGE_NAME,
        "created": time.time(),
        "brand": _default_brand(cfg),
        "captions": _default_captions(cfg),
        "music": _default_music(cfg),
    }
    cfg[_PACKAGES_KEY] = [pkg]
    return cfg[_PACKAGES_KEY]


def get_packages(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return ensure_packages(cfg)


def get_package(cfg: dict[str, Any], package_id: str) -> dict[str, Any] | None:
    for pkg in ensure_packages(cfg):
        if pkg.get("id") == package_id:
            return pkg
    return None


def save_package(cfg: dict[str, Any], pkg: dict[str, Any]) -> dict[str, Any]:
    """Upsert a package by id. Returns the stored package."""
    pkgs = ensure_packages(cfg)
    if not pkg.get("id"):
        pkg["id"] = uuid.uuid4().hex[:8]
        pkg.setdefault("created", time.time())
    for i, existing in enumerate(pkgs):
        if existing.get("id") == pkg["id"]:
            pkg.setdefault("created", existing.get("created", time.time()))
            pkgs[i] = pkg
            return pkg
    pkgs.append(pkg)
    return pkg


def delete_package(cfg: dict[str, Any], package_id: str) -> None:
    """Delete a package. Always keeps at least one."""
    pkgs = ensure_packages(cfg)
    if len(pkgs) <= 1:
        raise ValueError("Keep at least one brand package.")
    remaining = [p for p in pkgs if p.get("id") != package_id]
    if len(remaining) == len(pkgs):
        raise KeyError(package_id)
    cfg[_PACKAGES_KEY] = remaining
    sel = get_selection(cfg)
    if sel.get("pinned_id") == package_id:
        set_selection(cfg, sel.get("mode") or "pinned", remaining[0]["id"])


def get_selection(cfg: dict[str, Any]) -> dict[str, Any]:
    sel = cfg.get(_SELECTION_KEY)
    if not isinstance(sel, dict):
        sel = {}
    pkgs = ensure_packages(cfg)
    mode = str(sel.get("mode") or "pinned")
    if mode not in ("pinned", "auto"):
        mode = "pinned"
    pinned = str(sel.get("pinned_id") or pkgs[0]["id"])
    if not any(p.get("id") == pinned for p in pkgs):
        pinned = pkgs[0]["id"]
    return {"mode": mode, "pinned_id": pinned}


def set_selection(cfg: dict[str, Any], mode: str, pinned_id: str | None = None) -> None:
    pkgs = ensure_packages(cfg)
    mode = str(mode or "pinned").strip().lower()
    if mode not in ("pinned", "auto"):
        raise ValueError("Selection mode must be pinned or auto.")
    pinned = str(pinned_id or "").strip() or pkgs[0]["id"]
    if not any(p.get("id") == pinned for p in pkgs):
        raise ValueError("Unknown package: " + pinned)
    cfg[_SELECTION_KEY] = {"mode": mode, "pinned_id": pinned}


def _state_path(out_dir: Path | None) -> Path | None:
    if out_dir is None:
        return None
    return Path(out_dir) / _STATE_FILE


def _load_state(out_dir: Path | None) -> dict[str, Any]:
    path = _state_path(out_dir)
    if not path or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(out_dir: Path | None, state: dict[str, Any]) -> None:
    path = _state_path(out_dir)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass  # rotation state is best-effort


def select_package(
    cfg: dict[str, Any],
    *,
    out_dir: Path | None = None,
    perf: dict[str, dict[str, Any]] | None = None,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Pick the brand package for the next clip.

    pinned → always the pinned package. auto → round-robin until performance
    data exists (any package with >= 3 measured clips), then weighted by
    average views with a 25% exploration floor so every package keeps getting
    chances.
    """
    pkgs = ensure_packages(cfg)
    sel = get_selection(cfg)
    rng = rng or random.Random()

    if sel["mode"] == "pinned" or len(pkgs) == 1:
        chosen = get_package(cfg, sel["pinned_id"]) or pkgs[0]
    else:
        state = _load_state(out_dir)
        measured = {
            p["id"]: (perf or {}).get(p["id"])
            for p in pkgs
            if (perf or {}).get(p["id"], {}).get("clips", 0) >= 3
        }
        if measured:
            # Performance-weighted with exploration floor.
            avgs = {pid: max(0.0, float(d.get("avg_views", 0.0))) for pid, d in measured.items()}
            floor_share = 0.25
            floor = floor_share / len(pkgs)
            total = sum(avgs.values())
            weights = []
            for p in pkgs:
                if p["id"] in avgs and total > 0:
                    exploit = (1.0 - floor_share) * (avgs[p["id"]] / total)
                    weights.append(exploit + floor)
                else:
                    weights.append(floor)
            chosen = rng.choices(pkgs, weights=weights, k=1)[0]
        else:
            idx = int(state.get("rr_index", 0)) % len(pkgs)
            chosen = pkgs[idx]
            state["rr_index"] = idx + 1
            _save_state(out_dir, state)

    state = _load_state(out_dir)
    state["last_used"] = chosen["id"]
    _save_state(out_dir, state)
    return chosen


def package_overlay(cfg: dict[str, Any], pkg: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of cfg with brand/captions/music from the package."""
    out = dict(cfg)
    brand = dict(cfg.get("brand") or {})
    brand.update(pkg.get("brand") or {})
    out["brand"] = brand
    out["captions"] = dict(pkg.get("captions") or _default_captions(cfg))
    out["music"] = dict(pkg.get("music") or _default_music(cfg))
    return out


def package_summary(pkg: dict[str, Any]) -> str:
    """One-line human summary of what a package contains."""
    bits = []
    brand = pkg.get("brand") or {}
    caps = pkg.get("captions") or {}
    music = pkg.get("music") or {}
    bits.append("logo" if (brand.get("logo_path") or "").strip() else "no logo")
    intros = brand.get("intro_paths") or []
    outros = brand.get("outro_paths") or []
    if intros:
        bits.append(f"{len(intros)} intro" + ("s" if len(intros) != 1 else ""))
    if outros:
        bits.append(f"{len(outros)} outro" + ("s" if len(outros) != 1 else ""))
    if caps.get("enabled", True):
        bits.append("captions: " + str(caps.get("engine") or "auto"))
    else:
        bits.append("captions off")
    if music.get("enabled", True) and (music.get("path") or "").strip():
        bits.append("music bed")
    return " · ".join(bits)
