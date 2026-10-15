# SubScript Tester Share

Private tester file sharing is provided by a dedicated Cloudflare Worker backed by a dedicated R2 bucket.

- Portal: https://subscript-share.sensoredrooster-com.workers.dev
- R2 bucket: `subscript-share`
- Storage is separate from the project's support-diagnostics R2 bucket.
- The bucket itself remains private; downloads and uploads pass through the authenticated Worker.

## Roles

**Tester**
- Browse and download files.
- Upload to `Tester Uploads`, `VODs`, `Screenshots`, `Bug Reports`, and `Logs`.
- Cannot upload releases, archive files, delete files, or change the Latest build.

**Admin**
- All tester capabilities.
- Upload to every folder.
- Upload releases.
- Mark a release as **Latest**.
- Delete files and clear the Latest pointer when the selected file is removed.

## Folders

- `Releases`
- `Tester Uploads`
- `Screenshots`
- `Bug Reports`
- `Logs`
- `Archived`

R2 uses object keys rather than real directories; the portal presents these prefixes as folders.

## Security

The repository contains no passwords or password hashes. The Worker reads three secrets: `ADMIN_PASSWORD_HASH` and `TESTER_PASSWORD_HASH` (SHA-256 hex of each password) and `SESSION_SECRET` (random, at least 32 characters). After login the browser receives a Secure, HttpOnly, SameSite=Strict cookie containing only the role, an expiry (12 hours), and an HMAC-SHA256 signature; the password is never stored in the cookie. Changing a password hash or `SESSION_SECRET` immediately invalidates existing sessions. If any secret is missing the portal fails closed (HTTP 503).

Login attempts and uploads are rate limited. Files are limited to 75 MB per upload. The Worker sets no-store and common browser security headers.

To rotate a password, generate a new high-entropy password, update its hash with `wrangler secret put ADMIN_PASSWORD_HASH` (or `TESTER_PASSWORD_HASH`) from `cloudflare/share-worker`, and distribute the new password through a private channel. Secrets take effect without a code change.

## Deployment

The manual GitHub Actions workflow is:

`.github/workflows/deploy-share-portal.yml`

It creates the dedicated R2 bucket when needed, deploys the Worker, and verifies the public `/health` endpoint after deployment.

The syntax check workflow validates the Worker whenever share-portal code changes.
