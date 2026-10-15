"""Local, deterministic platform copy. No scraping, network, or invented events."""
from html import escape
from pathlib import Path
import re
from subscript.output_formats import selected_format

PLATFORMS = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram",
             "facebook": "Facebook", "twitter": "X / Twitter", "rumble": "Rumble"}


def transcript_text(srt: Path | None) -> str:
    if not srt or not srt.is_file():
        return ""
    lines = []
    for line in srt.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"<[^>]+>", "", line).strip()
        if not line or line.isdigit() or "-->" in line or line == "Clip | SUB":
            continue
        if not lines or lines[-1] != line:
            lines.append(line)
    return " ".join(lines)[:1000]


# Per-platform limits applied to generated drafts and to the review editor.
# hashtags = generated hashtags in the caption (fixed extras like #Shorts not counted);
# tags = max entries in the tags field. Titles/descriptions stay within what the editor accepts.
PLATFORM_LIMITS = {
    "youtube": {"title": 95, "description": 1800, "hashtags": 3, "tags": 15, "tag_chars": 350},
    "tiktok": {"title": 95, "description": 1800, "hashtags": 5, "tags": 5, "tag_chars": 350},
    "instagram": {"title": 95, "description": 1800, "hashtags": 15, "tags": 15, "tag_chars": 350},
    "facebook": {"title": 95, "description": 1800, "hashtags": 2, "tags": 2, "tag_chars": 350},
    "twitter": {"title": 95, "description": 260, "hashtags": 2, "tags": 2, "tag_chars": 350},
    "rumble": {"title": 95, "description": 1800, "hashtags": 5, "tags": 10, "tag_chars": 350},
}
EDITED_BASIS = "Edited by you"


def _fit_tags(tags, limit: int, char_limit: int) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if len(out) >= limit or sum(len(t) for t in out) + len(tag) > char_limit:
            break
        out.append(tag)
    return out


def generate_posts(cfg, srt: Path | None = None):
    from subscript.trends import clean_hashtag, get_suggestions

    settings = cfg.get("post_copy") or {}
    if settings.get("enabled", True) is False:
        return {}
    game = str(settings.get("game") or "Gameplay").strip()[:60]
    creator = str(settings.get("creator") or "").strip()[:60]
    tone = settings.get("tone", "casual")
    speech = transcript_text(srt)
    excerpt = speech[:110].rsplit(" ", 1)[0] if len(speech) > 110 else speech
    hook = f'"{excerpt}"' if excerpt else f"{game} highlight"
    credit = f"\nFrom {creator}." if creator else ""
    question = "What would you do here?" if tone == "casual" else "Watch the play." if tone == "direct" else "Your turn: how would you play this?"
    trend = get_suggestions(cfg, game)
    base = [clean_hashtag(game) or re.sub(r"[^\w]", "", game), *trend.hashtags[:4], "Gaming", "Gameplay"]
    pool = list(dict.fromkeys(t for t in base if t))
    lower_seen: set[str] = set()
    pool = [t for t in pool if not (t.lower() in lower_seen or lower_seen.add(t.lower()))]

    def hashes(key: str) -> list[str]:
        return pool[:PLATFORM_LIMITS[key]["hashtags"]]

    def line(key: str) -> str:
        return " ".join("#" + t for t in hashes(key))

    gameplay_label = "Gameplay" if game.lower() == "gameplay" else f"{game} gameplay"
    drafts = {
        "youtube": (f"{game}: {hook}" if speech else hook, f"{hook}\n{gameplay_label}.{credit}\n{line('youtube')} #Shorts"),
        "tiktok": (hook, f"{hook}\n{question}{credit}\n{line('tiktok')}"),
        "instagram": (hook, f"{hook}\n\n{question}{credit}\n\n{line('instagram')} #GamingClips"),
        "facebook": (gameplay_label, f"{hook}\n{question}{credit}\n{line('facebook')}"),
        "twitter": (hook, f"{hook}\n{line('twitter')}"),
        "rumble": (f"{game} | {hook}" if speech else hook, f"{gameplay_label} highlight.\n{hook}{credit}\n{line('rumble')}"),
    }
    if selected_format(cfg, "youtube") == "horizontal":
        title, description = drafts["youtube"]
        drafts["youtube"] = (title, description.replace(" #Shorts", ""))
    result = {}
    platform_settings = cfg.get("platforms") or {}
    for key, (title, description) in drafts.items():
        limits = PLATFORM_LIMITS[key]
        if key == "youtube":
            # YouTube tags are hidden search keywords; captions elsewhere use hashtags.
            tags = list(dict.fromkeys([re.sub(r"[^\w]", "", game) or "Gameplay", *trend.keywords, "Gaming", "Gameplay"]))
        else:
            tags = hashes(key)
        override = platform_settings.get(key) or {}
        title_template = str(override.get("title_template") or "").strip()
        if title_template:
            replacements = {"game": game, "creator": creator, "hook": hook, "timestamp": ""}
            for placeholder, value in replacements.items():
                title_template = title_template.replace("{" + placeholder + "}", value)
            title = title_template
        if str(override.get("description") or "").strip():
            description = str(override["description"]).strip()
        raw_override_tags = override.get("tags")
        if isinstance(raw_override_tags, str):
            raw_override_tags = raw_override_tags.split(",")
        if raw_override_tags:
            tags = [str(tag).strip().lstrip("#") for tag in raw_override_tags if str(tag).strip().lstrip("#")]
        tags = _fit_tags(tags, limits["tags"], limits["tag_chars"])
        basis = "Saved platform defaults" if title_template or override.get("description") or override.get("tags") else ("Transcript excerpt + creator settings" if speech else "Creator settings only; no transcript available")
        used = {t.lower() for t in tags} | {t.lower() for t in hashes(key)}
        result[key] = {"title": title[:limits["title"]], "description": description[:limits["description"]],
                       "tags": tags, "basis": f"{basis} · {trend.basis}",
                       "suggestions": {"hashtags": [t for t in trend.hashtags if t.lower() not in used][:10], "emojis": trend.emojis[:12]}}
    return result


def merge_drafts(existing, generated):
    """Replace generated drafts with fresh ones; never touch drafts the user edited."""
    merged = dict(generated)
    for key, draft in (existing or {}).items():
        if isinstance(draft, dict) and draft.get("basis") == EDITED_BASIS:
            merged[key] = draft
        elif key not in merged:
            merged[key] = draft
    return merged


def _chips_html(draft) -> str:
    sugg = draft.get("suggestions") or {}
    tags = [str(t) for t in sugg.get("hashtags") or []][:10]
    emojis = [str(e) for e in sugg.get("emojis") or []][:12]
    if not tags and not emojis:
        return ""
    chip = lambda text: (f'<button type="button" class="chip" data-insert="{escape(text, quote=True)}" '
                         f'title="Add to caption">{escape(text)}</button>')
    parts = ['<div class="chips" aria-label="Suggestions"><span class="meta">Suggestions (click to add):</span>']
    parts += [chip("#" + t) for t in tags] + [chip(e) for e in emojis]
    parts.append("</div>")
    return "".join(parts)


def editor_html(item):
    from subscript.trends import TIKTOK_CREATIVE_CENTER_URL

    item_id = escape(item.id, quote=True)
    generate = (f'<form method="post" action="/items/{item_id}/generate-post-copy">'
                '<button type="submit">Generate post drafts for this clip</button>'
                '<p class="meta">Creates missing drafts for YouTube, TikTok, Instagram, Facebook, X and Rumble. Keeps existing drafts and your edits. Does not publish.</p></form>')
    if not item.post_metadata:
        return generate
    refresh = (f'<form method="post" action="/items/{item_id}/refresh-post-copy">'
               '<button type="submit" class="quiet-button">Refresh suggestions</button>'
               '<p class="meta">Rebuilds generated drafts with the latest hashtag suggestions. Drafts marked &ldquo;Edited by you&rdquo; are never changed.</p></form>')
    rows = []
    for key, name in PLATFORMS.items():
        draft = item.post_metadata.get(key)
        if not draft:
            continue
        limits = PLATFORM_LIMITS[key]
        esc = lambda value: escape(str(value), quote=True)
        extra = (f'<p class="meta"><a href="{TIKTOK_CREATIVE_CENTER_URL}" target="_blank" rel="noopener">Open TikTok Creative Center</a> '
                 'to browse trending hashtags, then paste any you like.</p>') if key == "tiktok" else ""
        rows.append(f'<details class="advanced"><summary>{name}</summary>'
                    f'<form method="post" action="/items/{esc(item.id)}/post-copy" class="form-grid post-copy-form">'
                    f'<input type="hidden" name="platform" value="{key}">'
                    f'<p class="meta">{esc(draft.get("basis", "Edited draft"))}</p>'
                    f'<label>Title<input name="title" type="text" maxlength="{limits["title"]}" value="{esc(draft["title"])}" required></label>'
                    f'<label>Description / caption<textarea name="description" maxlength="{limits["description"]}">{esc(draft["description"])}</textarea></label>'
                    + _chips_html(draft) + extra +
                    f'<label>Tags (comma separated, up to {limits["tags"]})<input name="tags" type="text" value="{esc(", ".join(draft["tags"]))}"></label>'
                    '<button type="submit">Save this draft</button></form></details>')
    return generate + refresh + '<details class="advanced" open><summary>Titles, captions &amp; tags by platform</summary><p class="meta">Local templates use available transcript text, your creator settings, and hashtag suggestions. Nothing is posted until you approve. Trimming regenerates drafts you have not edited.</p>' + "".join(rows) + '</details>'
