"""Trend-aware hashtag/keyword suggestions for post drafts.

Offline seeds (``subscript/data/trend_seeds.yaml``) always work. Online sources are
opt-in (``trends.enabled``) and only use official APIs; TikTok Creative Center and
Google Trends are never scraped (a manual link is offered instead).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
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


YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
CACHE_TTL_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT_SECONDS = 5
GAMING_CATEGORY_ID = "20"


def _http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"Accept": "application/json", "User-Agent": "SubScript"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode("utf-8"))


def fetch_youtube_trends(game: str, api_key: str, region: str = "US") -> dict[str, list[str]]:
    """Official YouTube Data API v3: most-viewed Gaming videos for this game in the last 7 days.

    Costs ~101 quota units (search.list 100 + videos.list 1); cached for 24h per game/region.
    """
    after = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    search = _http_get_json(f"{YOUTUBE_API}/search", {
        "part": "snippet", "type": "video", "q": game or "gaming", "order": "viewCount",
        "publishedAfter": after, "videoCategoryId": GAMING_CATEGORY_ID, "maxResults": 25,
        "regionCode": region, "relevanceLanguage": "en", "safeSearch": "strict", "key": api_key,
    })
    ids = [i.get("id", {}).get("videoId") for i in search.get("items") or []]
    ids = [i for i in ids if i]
    if not ids:
        return {"hashtags": [], "keywords": []}
    videos = _http_get_json(f"{YOUTUBE_API}/videos", {"part": "snippet", "id": ",".join(ids[:50]), "key": api_key})
    hashtag_counts: Counter[str] = Counter()
    keyword_counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for video in videos.get("items") or []:
        snip = video.get("snippet") or {}
        text = f"{snip.get('title', '')} {snip.get('description', '')}"
        per_video: dict[str, str] = {}
        for raw in re.findall(r"#(\w{2,30})", text):
            tag = clean_hashtag(raw)
            if tag:
                per_video.setdefault(tag.lower(), tag)
        for low, tag in per_video.items():
            hashtag_counts[low] += 1
            display.setdefault(low, tag)
        for kw in {str(k).strip().lower() for k in snip.get("tags") or []}:
            if 2 <= len(kw) <= 40 and not any(b in kw for b in BLOCKLIST):
                keyword_counts[kw] += 1
    # Require at least two videos to share a term, so one-off spam doesn't leak in.
    hashtags = [display[t] for t, n in hashtag_counts.most_common(30) if n >= 2 and t not in {"shorts", "short"}]
    keywords = [k for k, n in keyword_counts.most_common(30) if n >= 2]
    return {"hashtags": hashtags[:15], "keywords": keywords[:15]}


def _cache_path(cfg: dict[str, Any]) -> Path:
    from subscript.config import ROOT

    out = (cfg.get("output") or {}).get("dir") or "out"
    path = Path(out)
    return (path if path.is_absolute() else ROOT / path) / "trends-cache.json"


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _age_label(seconds: float) -> str:
    hours = int(seconds // 3600)
    return "just now" if hours < 1 else f"{hours}h ago"


def get_suggestions(cfg: dict[str, Any] | None, game: str) -> Suggestions:
    """Return suggestions for a game. Never raises; falls back to offline seeds."""
    cfg = cfg or {}
    seeds = seed_suggestions(game)
    settings = cfg.get("trends") or {}
    if not settings.get("enabled", False) or "youtube" not in (settings.get("sources") or ["seeds", "youtube"]):
        return seeds
    try:
        from subscript.config import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    api_key = str(os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        seeds.basis += " (add YOUTUBE_API_KEY for YouTube trends)"
        return seeds
    region = str(settings.get("region") or "US").strip().upper()[:2] or "US"
    key = f"youtube:{(game or 'gaming').strip().lower()}:{region}"
    path = _cache_path(cfg)
    cache = _read_cache(path)
    entry = cache.get(key) if isinstance(cache.get(key), dict) else None
    now = time.time()
    status = ""
    if not entry or now - float(entry.get("fetched_at", 0)) > CACHE_TTL_SECONDS:
        try:
            fresh = fetch_youtube_trends(game, api_key, region)
            entry = {"fetched_at": now, **fresh}
            cache[key] = entry
            _write_cache(path, cache)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            status = " (refresh failed; using cached)" if entry else ""
            if not entry:
                seeds.basis += f" (YouTube trends unavailable: {type(exc).__name__})"
                return seeds
    trend_tags = [clean_hashtag(t) for t in entry.get("hashtags") or []]
    if not any(trend_tags) and not entry.get("keywords"):
        seeds.basis += " (no YouTube trends found)"
        return seeds
    return Suggestions(
        hashtags=_dedupe([*filter(None, trend_tags), *seeds.hashtags], 20),
        keywords=_dedupe([*(entry.get("keywords") or []), *seeds.keywords], 20),
        emojis=seeds.emojis,
        basis=f"Trend-assisted: YouTube {region}, updated {_age_label(now - float(entry.get('fetched_at', now)))}{status} + {seeds.basis.lower()}",
    )
