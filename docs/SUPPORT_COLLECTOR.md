# SubScript Support Collector

## Production status

The production desktop app is already wired to the dedicated Cloudflare collector at `https://subscript-support.sensoredrooster-com.workers.dev/upload`, backed by the private `subscript-support-logs` R2 bucket. The Python collector documented below is retained for local development, offline testing, or custom self-hosting; it is not the normal production path.

SubScript can keep diagnostics completely local, or testers can explicitly send a Support Bundle to a collector that you control.

The repository includes an optional collector at:

~~~text
tools/support_collector.py
~~~

It is **not** started by SubScript and is not required for normal use.

## What it does

The collector:

- accepts application/zip Support Bundles from SubScript;
- requires a bearer token;
- rejects empty, non-ZIP, and oversized uploads;
- stores bundles in a dedicated support inbox;
- writes sidecar JSON metadata with session/version/size/timestamp;
- provides authenticated list and download endpoints.

## 1. Choose a strong collector token

Set a long random secret on the server:

~~~powershell
$env:SUBSCRIPT_SUPPORT_COLLECTOR_TOKEN="replace-with-a-long-random-secret"
~~~

Optionally choose another inbox:

~~~powershell
$env:SUBSCRIPT_SUPPORT_INBOX="D:\SubScriptSupport\inbox"
~~~

The default is support-inbox/.

## 2. Start the collector

From the repository:

~~~powershell
.\.venv\Scripts\Activate.ps1
uvicorn tools.support_collector:app --host 0.0.0.0 --port 8790
~~~

For internet-facing use, put the collector behind HTTPS/reverse proxy and normal server security controls. Do not expose an unencrypted HTTP collector to the public internet.

Health endpoint:

~~~text
GET /health
~~~

Upload endpoint:

~~~text
POST /upload
Content-Type: application/zip
Authorization: Bearer <collector-token>
X-SubScript-Session: <session-id>
X-SubScript-Version: <version>
X-SubScript-Filename: <bundle-name>
~~~

## 3. Configure tester builds

On a tester machine/build:

~~~text
SUBSCRIPT_SUPPORT_UPLOAD_URL=https://support.example.com/upload
SUBSCRIPT_SUPPORT_UPLOAD_TOKEN=<collector-token>
~~~

Or put only the URL in local config:

~~~yaml
support:
  upload_url: "https://support.example.com/upload"
~~~

Keep the bearer token in the environment, not in Git.

When the URL is configured, **Support → Send Diagnostics to Developer** appears.

The tester must click the button and confirm the upload. SubScript does not silently upload telemetry.

## 4. Retrieve bundles

List received bundles:

~~~powershell
$headers = @{ Authorization = "Bearer $env:SUBSCRIPT_SUPPORT_COLLECTOR_TOKEN" }
Invoke-RestMethod -Headers $headers https://support.example.com/bundles
~~~

Download one:

~~~powershell
Invoke-WebRequest -Headers $headers https://support.example.com/bundles/<bundle-name>.zip -OutFile .\tester-support.zip
~~~

## Privacy model

The client attempts to redact known secrets, tokens, OAuth query values, cookies/password-shaped configuration keys, and bearer credentials.

Support bundles may still include:

- filenames;
- local directory paths;
- error messages;
- system/runtime metadata.

Those details are often necessary for diagnosing media and watcher failures. Testers are told to review a bundle before sharing if local names or paths are sensitive.

The collector should be treated as sensitive support infrastructure. Protect it with HTTPS, a strong token, restricted network access where possible, retention limits, and normal server backups/access controls.
