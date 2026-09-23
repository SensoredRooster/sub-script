# Cloudflare Support Collector Deployment

## Current production deployment

- Worker: `https://subscript-support.sensoredrooster-com.workers.dev`
- Upload endpoint: `https://subscript-support.sensoredrooster-com.workers.dev/upload`
- Health endpoint: `https://subscript-support.sensoredrooster-com.workers.dev/health`
- Private R2 bucket: `subscript-support-logs`

The Worker is live. This document remains the deployment/maintenance reference for future redeploys.

This repository contains a dedicated Cloudflare Worker for tester diagnostics.

The collector is isolated to this product. Do not point another application at this Worker or its storage bucket.

## Required GitHub Actions secrets

Add these repository secrets:

- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`

The API token needs permission to create/deploy Workers and create/write R2 buckets.

Optional:

- the product-specific support admin token used by this repository's deployment workflow

The upload endpoint itself is intentionally unauthenticated so tester builds do not contain a reusable private credential. Uploads are ZIP-only, size-limited, and rate-limited by client IP. Bundle listing/download endpoints remain admin-protected when the optional admin secret is configured.

## Deploy

In GitHub:

1. Open **Actions**.
2. Choose **Deploy Cloudflare Support Collector**.
3. Choose **Run workflow**.
4. Wait for the deploy job to finish.
5. Copy the generated `*.workers.dev` URL from the Wrangler deploy output.

The workflow creates the product-specific R2 bucket automatically if it does not already exist.

After the Worker URL is known, configure the desktop application's support upload URL to:

~~~text
https://<worker-host>/upload
~~~

The health endpoint is:

~~~text
https://<worker-host>/health
~~~

## Privacy and separation

The Worker stores only this product's support bundles in its dedicated R2 bucket. It does not share storage with the other SensoredRooster application.

Cloudflare Workers/R2 free-tier limits are suitable for low-volume tester diagnostics, but retention should still be managed periodically.
