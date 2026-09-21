# SubScript starter identity

## Destination formats

Every destination uses the same tile grid. Enable a tile to choose its output format. YouTube offers vertical Shorts or standard landscape video; Facebook, X, and Rumble offer vertical or landscape; TikTok and Instagram currently offer vertical presets. These are the presets implemented here, not an exhaustive list of formats accepted by each service. Save settings before approving a clip.

The publisher selects the matching export file. Landscape YouTube posts do not receive an automatic Shorts hashtag or Shorts URL. Enabled captions are now applied to landscape as well as vertical output using the same SRT. Existing clips must be rebuilt to add landscape captions. Standard YouTube video uses the selected clip range; it does not imply uploading an entire VOD. YouTube and TikTok can use direct upload when their connectors are configured; other destinations produce format-specific manual upload packs. Live platform acceptance still needs real-account validation.

## Platform post writing

Publish > Post writing controls local draft generation for new clips. Set a game/topic, creator name, and voice, then save publishing settings. Each new clip stores separate YouTube, TikTok, Instagram, Facebook, X, and Rumble titles, descriptions, and tags. Review clips expose editable drafts; save each edited platform before approving. Trimming regenerates drafts for the new cut and replaces earlier edits.

The generator uses deterministic templates and real SRT text from the existing caption pipeline. Demo captions are excluded. If transcription is disabled or unavailable, the copy uses only creator settings and is labeled accordingly. This version does not infer visual events, consult trends, scrape platforms, or call an AI service. Voice affects conversational prompts; tags come from the game/topic and general gaming labels.

YouTube uses the saved draft during upload. Manual platform folders include POST_COPY.txt, and the parent export pack includes post-copy.json. Automatic publishing uses generated drafts without review. Existing clips without drafts retain their previous publishing behavior. Disabling generation applies to new clips only.

The studio uses warm white (#f3f4ec), ink green (#101714), and lime (#b9f36b), with system sans-serif typography. Keep lime for primary actions and helpful emphasis.

- `subscript/static/brand-mark.svg`: scalable studio icon and favicon.
- `assets/logo.png`: transparent SubScript wordmark for video watermarking.
- `subscript/default_brand.py`: bundled PNG for packaged installs. Upgrades only the exact legacy placeholder; custom logos are preserved.

Choose a VOD to automatically analyze its strongest audio highlight and render a landscape and vertical preview with saved style settings. Disable automatic start before choosing a file to adjust the range first. Local paths require Create previews. An empty highlight result falls back to the final configured clip duration.

Review and approval remain required before publishing. YouTube and TikTok can use live uploads after their account connections and developer permissions are configured; the other current destinations create manual upload packs. Real speech captions require faster-whisper; without it the current caption pipeline uses demo text. Background music is optional and requires an uploaded audio file.

## Optional automatic publishing

In **Publish > Publishing mode**, select **Automatic - publish without review** and save publishing settings. Review first remains the default. New VOD and app live-hotkey clips use this setting; existing pending clips still require approval. Automatic mode saves the local pack without opening Explorer, then runs enabled publishers using saved visibility and connection settings. YouTube and configured TikTok can upload; other current destinations create manual packs. The dry-run environment override still disables live YouTube uploads.

Each automatically processed pack includes `publishing-results.json`. Failed deliveries with no successful upload remain in review. Clips already uploaded are marked uploaded to avoid offering a blanket retry that could duplicate a successful post. OBS must still save replay footage; this setting does not add OBS buffer capture integration. CLI dry-run commands remain dry runs.
