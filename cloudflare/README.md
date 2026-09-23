# Cloudflare Services

SubScript uses two production Cloudflare Workers and two separate private R2 buckets.

## 1. Support diagnostics

- Worker source: `cloudflare/support-worker/src/index.js`
- Wrangler config: `cloudflare/support-worker/wrangler.jsonc`
- Worker: `subscript-support`
- URL: `https://subscript-support.sensoredrooster-com.workers.dev`
- Health: `https://subscript-support.sensoredrooster-com.workers.dev/health`
- Upload: `https://subscript-support.sensoredrooster-com.workers.dev/upload`
- R2 bucket: `subscript-support-logs`
- Deploy workflow: `.github/workflows/deploy-support-worker.yml`

Purpose: receive redacted support ZIPs created by the application after explicit user confirmation.

## 2. Tester Share

- Worker source: `cloudflare/share-worker/src/index.js`
- Wrangler config: `cloudflare/share-worker/wrangler.jsonc`
- Worker: `subscript-share`
- URL: `https://subscript-share.sensoredrooster-com.workers.dev`
- Health: `https://subscript-share.sensoredrooster-com.workers.dev/health`
- R2 bucket: `subscript-share`
- Deploy workflow: `.github/workflows/deploy-share-portal.yml`
- Syntax check: `.github/workflows/share-portal-check.yml`

Purpose: authenticated file sharing between the developer and testers.

Portal folders:

- `Releases`
- `Tester Uploads`
- `VODs`
- `Screenshots`
- `Bug Reports`
- `Logs`
- `Archived`

Tester role can browse/download and upload only to tester-facing folders. Admin role additionally manages releases, the **Latest** pointer, deletes, and archived content.

## Separation rules

Do not reuse one project's Worker or bucket for another project.

Do not point the support Worker at the Tester Share bucket or vice versa.

Do not make the R2 buckets public. Browser access should always pass through the Worker.

## Credentials

Cloudflare deployment uses the repository Actions secret `CLOUDFLARE_API_TOKEN`.

Tester Share passwords are project-specific. Their plaintext values are distributed privately; Git contains only their SHA-256 hashes.

## Redeployment

Production deployment workflows are manual-only after initial verification. Use GitHub Actions when a Worker or Wrangler configuration changes, and confirm the workflow's post-deploy `/health` check passes.
