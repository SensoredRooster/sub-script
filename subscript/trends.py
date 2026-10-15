"""Trend-aware hashtag/keyword suggestions for post drafts.

Offline seeds (``subscript/data/trend_seeds.yaml``) always work. Online sources are
opt-in (``trends.enabled``) and only use official APIs; TikTok Creative Center and
Google Trends are never scraped (a manual link is offered instead).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SEEDS_PATH = Path(__file__).resolve().parent / "data" / "trend_seeds.yaml"
TIKTOK_CREATIVE_CENTER_URL = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"
_HASHTAG_OK = re.compile(r"^[A-Za-z0-9_]{2,30}$")
BLOCKLIST = {"nsfw", "porn", "sex", "onlyfans", "nude", "gore", "fyp4you"}


@dataclass
class Suggestions:
    hashtags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    emojis: list[str] = field(default_factory=list)
    basis: str = "Offline game seeds"


@lru_cache(maxsize=1)
def load_seeds() -> dict[str, Any]:
    try:
        data = yaml.safe_load(SEEDS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return data if isinstance(data, dict) else {}


def clean_hashtag(value: Any) -> str:
    tag = re.sub(r"[^\w]", "", str(value or "").strip().lstrip("#"))
    if not _HASHTAG_OK.match(tag) or tag.lower() in BLOCKLIST:
        return ""
    return tag


def _dedupe(values, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def game_seed(game: str) -> dict[str, Any]:
    seeds = load_seeds()
    needle = str(game or "").strip().lower()
    for entry in (seeds.get("games") or {}).values():
        aliases = [str(a).lower() for a in (entry or {}).get("aliases") or []]
        if needle and needle in aliases:
            return entry
    return {}


def seed_suggestions(game: str) -> Suggestions:
    seeds = load_seeds()
    entry = game_seed(game)
    default = seeds.get("default") or {}
    hashtags = [clean_hashtag(t) for t in list(entry.get("hashtags") or []) + list(default.get("hashtags") or [])]
    keywords = list(entry.get("keywords") or []) + list(default.get("keywords") or [])
    emojis = [e for group in (seeds.get("emojis") or {}).values() for e in (group or [])]
    basis = "Offline game seeds" if entry else "Offline gaming seeds"
    return Suggestions(_dedupe(filter(None, hashtags), 20), _dedupe(keywords, 20), _dedupe(emojis, 16), basis)


def get_suggestions(cfg: dict[str, Any] | None, game: str) -> Suggestions:
    """Return suggestions for a game. Never raises; falls back to offline seeds."""
    return seed_suggestions(game)
