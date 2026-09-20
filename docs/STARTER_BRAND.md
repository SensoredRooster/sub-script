# SubScript starter identity

The studio uses warm white (#f3f4ec), ink green (#101714), and lime (#b9f36b), with system sans-serif typography. Keep lime for primary actions and helpful emphasis.

- `subscript/static/brand-mark.svg`: scalable studio icon and favicon.
- `assets/logo.png`: transparent SubScript wordmark for video watermarking.
- `subscript/default_brand.py`: bundled PNG for packaged installs. Upgrades only the exact legacy placeholder; custom logos are preserved.

Choose a VOD to automatically analyze its strongest audio highlight and render a landscape and vertical preview with saved style settings. Disable automatic start before choosing a file to adjust the range first. Local paths require Create previews. An empty highlight result falls back to the final configured clip duration.

Review and approval remain required before publishing. YouTube needs OAuth setup and live uploads enabled; the other current destinations create manual upload packs. Real speech captions require faster-whisper; without it the current caption pipeline uses demo text. Background music is optional and requires an uploaded audio file.

## Optional automatic publishing

In **Publish > Publishing mode**, select **Automatic - publish without review** and save publishing settings. Review first remains the default. New VOD and app live-hotkey clips use this setting; existing pending clips still require approval. Automatic mode saves the local pack without opening Explorer, then runs enabled publishers using saved visibility and connection settings. YouTube can upload; other current destinations create manual packs. The dry-run environment override still disables live YouTube uploads.

Each automatically processed pack includes `publishing-results.json`. Failed deliveries with no successful upload remain in review. Clips already uploaded are marked uploaded to avoid offering a blanket retry that could duplicate a successful post. OBS must still save replay footage; this setting does not add OBS buffer capture integration. CLI dry-run commands remain dry runs.
