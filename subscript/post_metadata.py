"""Local, deterministic platform copy. No scraping, network, or invented events."""
from html import escape
from pathlib import Path
import re

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


def generate_posts(cfg, srt: Path | None = None):
    settings = cfg.get("post_copy") or {}
    if settings.get("enabled", True) is False:
        return {}
    game = str(settings.get("game") or "Gameplay").strip()[:60]
    creator = str(settings.get("creator") or "").strip()[:60]
    tone = settings.get("tone", "casual")
    speech = transcript_text(srt)
    excerpt = speech[:110].rsplit(" ", 1)[0] if len(speech) > 110 else speech
    hook = f'“{excerpt}”' if excerpt else f"{game} highlight"
    credit = f"\nFrom {creator}." if creator else ""
    question = "What would you do here?" if tone == "casual" else "Watch the play." if tone == "direct" else "Your turn: how would you play this?"
    tags = list(dict.fromkeys(filter(None, [re.sub(r"[^\w]", "", game), "Gaming", "Gameplay"])))
    hashes = " ".join("#" + tag for tag in tags)
    gameplay_label = "Gameplay" if game.lower() == "gameplay" else f"{game} gameplay"
    drafts = {
        "youtube": (f"{game}: {hook}" if speech else hook, f"{hook}\n{gameplay_label}.{credit}\n{hashes} #Shorts"),
        "tiktok": (hook, f"{hook}\n{question}{credit}\n{hashes}"),
        "instagram": (hook, f"{hook}\n\n{question}{credit}\n\n{hashes} #GamingClips"),
        "facebook": (gameplay_label, f"{hook}\n{question}{credit}\n#{tags[0]}"),
        "twitter": (hook, f"{hook}\n#{tags[0]}"),
        "rumble": (f"{game} | {hook}" if speech else hook, f"{gameplay_label} highlight.\n{hook}{credit}\n{hashes}"),
    }
    return {key: {"title": title[:95], "description": description[:260] if key == "twitter" else description[:1800],
                  "tags": tags, "basis": "Transcript excerpt + creator settings" if speech else "Creator settings only; no transcript available"}
            for key, (title, description) in drafts.items()}


def editor_html(item):
    generate = (f'<form method="post" action="/items/{escape(item.id, quote=True)}/generate-post-copy">'
                '<button type="submit">Generate post drafts for this clip</button>'
                '<p class="meta">Creates missing drafts for YouTube, TikTok, Instagram, Facebook, X and Rumble. Keeps existing drafts and your edits. Does not publish.</p></form>')
    if not item.post_metadata:
        return generate
    rows = []
    for key, name in PLATFORMS.items():
        draft = item.post_metadata.get(key)
        if not draft:
            continue
        esc = lambda value: escape(str(value), quote=True)
        rows.append(f'<details class="advanced"><summary>{name}</summary>'
                    f'<form method="post" action="/items/{esc(item.id)}/post-copy" class="form-grid">'
                    f'<input type="hidden" name="platform" value="{key}">'
                    f'<p class="meta">{esc(draft.get("basis", "Edited draft"))}</p>'
                    f'<label>Title<input name="title" type="text" maxlength="95" value="{esc(draft["title"])}" required></label>'
                    f'<label>Description / caption<textarea name="description" maxlength="{260 if key == "twitter" else 1800}">{esc(draft["description"])}</textarea></label>'
                    f'<label>Tags (comma separated)<input name="tags" type="text" value="{esc(", ".join(draft["tags"]))}"></label>'
                    '<button type="submit">Save this draft</button></form></details>')
    return generate + '<details class="advanced" open><summary>Titles, captions &amp; tags by platform</summary><p class="meta">Local templates use available transcript text and your creator settings. Save edits before approving. Trimming regenerates drafts for the new cut.</p>' + "".join(rows) + '</details>'
