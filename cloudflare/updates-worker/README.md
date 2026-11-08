# subscript-updates worker

Public release host for SubScript in-app updates. The Windows app reads
`https://subscript-updates.sensoredrooster-com.workers.dev/latest.json` and downloads
`releases/SubScript-Setup-<version>.exe` from the same host. Reads are public;
writes need `Authorization: Bearer $UPLOAD_TOKEN`.

## One-time deploy

```bat
cd cloudflare\updates-worker
npx wrangler r2 bucket create subscript-releases
npx wrangler secret put UPLOAD_TOKEN
npx wrangler deploy
```

Use the same UPLOAD_TOKEN value you store in GitHub (if a release workflow ever
publishes installers automatically, reference it there as a repository secret).

## Publishing an update

1. Bump `__version__` in `subscript/__init__.py`.
2. Build the installer (`scripts\build_installer.bat`) →
   `installer\Output\SubScript-Setup-<version>.exe`.
3. Hash it:

   ```bat
   certutil -hashfile installer\Output\SubScript-Setup-<version>.exe SHA256
   ```

4. Write `latest.json`:

   ```json
   {
     "version": "<version>",
     "url": "https://subscript-updates.sensoredrooster-com.workers.dev/releases/SubScript-Setup-<version>.exe",
     "sha256": "<lowercase hex from step 3>",
     "notes": "What changed."
   }
   ```

5. Upload both (installer first, feed last so clients never see a feed entry
   whose file is missing):

   ```bat
   curl -X PUT -H "Authorization: Bearer %UPLOAD_TOKEN%" --data-binary @installer\Output\SubScript-Setup-<version>.exe https://subscript-updates.sensoredrooster-com.workers.dev/releases/SubScript-Setup-<version>.exe
   curl -X PUT -H "Authorization: Bearer %UPLOAD_TOKEN%" -H "Content-Type: application/json" --data-binary @latest.json https://subscript-updates.sensoredrooster-com.workers.dev/latest.json
   ```

The app verifies the sha256 before running anything, refuses redirects, and only
accepts installers named `SubScript-Setup-<version>.exe` from this host.
