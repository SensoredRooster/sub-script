"""Explicit supported delivery presets; file encoding is MP4/H.264/AAC."""
FORMATS = {
    "youtube": {"vertical": "YouTube Shorts · vertical 9:16", "horizontal": "YouTube video · landscape 16:9"},
    "tiktok": {"vertical": "Vertical video · 9:16"},
    "instagram": {"vertical": "Instagram Reel · 9:16"},
    "facebook": {"vertical": "Facebook Reel · 9:16", "horizontal": "Landscape video · 16:9"},
    "twitter": {"vertical": "Vertical video · 9:16", "horizontal": "Landscape video · 16:9"},
    "rumble": {"horizontal": "Landscape video · 16:9", "vertical": "Vertical video · 9:16"},
}


def selected_format(cfg, platform):
    return ((cfg.get("platforms") or {}).get(platform) or {}).get("format", "vertical")
