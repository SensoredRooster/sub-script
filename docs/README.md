# SubScript Documentation Index

This folder contains the maintained operational documentation for SubScript.

## Current cloud services

Diagnostics and tester file sharing are intentionally isolated:

| Service | Worker | Private R2 bucket |
|---|---|---|
| Support diagnostics | `subscript-support` | `subscript-support-logs` |
| Tester Share | `subscript-share` | `subscript-share` |

- Support: `https://subscript-support.sensoredrooster-com.workers.dev`
- Tester Share: `https://subscript-share.sensoredrooster-com.workers.dev`

The diagnostics bucket is only for redacted support bundles. The Tester Share bucket is only for project files exchanged with testers. They must not be pointed at the same bucket.

## Documentation map

- [README.md](README.md) — Main project overview and user/developer setup.
- [CLOUDFLARE_SUPPORT.md](CLOUDFLARE_SUPPORT.md) — Production diagnostics Worker/R2 deployment and maintenance.
- [SUPPORT_COLLECTOR.md](SUPPORT_COLLECTOR.md) — Legacy/local Python collector fallback; not the production path.
- [TESTER_SHARE.md](TESTER_SHARE.md) — Authenticated tester/admin file portal behavior and maintenance.
- [WINDOWS_EXE.md](WINDOWS_EXE.md) — Packaged Windows build instructions.
- [GITHUB_PAGES.md](GITHUB_PAGES.md) — Public static pages deployment notes.

## Deployment workflows

- `.github/workflows/deploy-support-worker.yml` — manual production diagnostics deployment.
- `.github/workflows/deploy-share-portal.yml` — manual Tester Share deployment.
- `.github/workflows/share-portal-check.yml` — syntax validation for the Tester Share Worker.

Normal app pushes do not redeploy the production Workers. Deployment workflows are intentionally manual after verification.

## Security notes

- Cloudflare API credentials live only in GitHub Actions secrets.
- R2 buckets are private.
- Support uploads happen only after explicit user confirmation.
- Tester Share plaintext passwords are not committed; only SHA-256 password hashes live in the Worker source.
- Rotate any exposed tester/admin password by replacing its hash and redeploying the share Worker.
