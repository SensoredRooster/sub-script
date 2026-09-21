# SubScript

SubScript turns gameplay recordings and replay-buffer clips into polished, branded videos.

It can:

- find a strong moment in a VOD;
- trim a clip without changing the original recording;
- add a watermark, captions, intro, outro, and optional music;
- render both landscape 16:9 and vertical 9:16 versions;
- show both previews before anything is published;
- save a local social export pack; and
- optionally publish through supported platform connectors.

SubScript is a local Windows-first desktop tool. Your videos, configuration, and saved OAuth tokens stay on your computer unless you deliberately publish through a connected platform.

## The important idea

When the browser opens, SubScript starts with only two choices:

1. **Create & Publish a Clip** — make one clip right now.
2. **Put My Content on Autopilot** — create a saved workflow that watches one replay folder.

The app intentionally keeps these paths separate so a first-time user does not have to understand every setting before making a clip.

## Quick start for an absolute beginner

### First-time setup

Ask for help with this one-time setup if you are not comfortable with Python or Windows terminals.

1. Install Python 3.11 or newer.
2. Install FFmpeg. The easiest Windows command is:

   ~~~bat
   winget install ffmpeg
   ~~~

3. Open this repository folder.
4. Create the virtual environment and install the app:

   ~~~bat
   python -m venv .venv
   .venv\\Scripts\\pip install -r requirements.txt
   copy config.example.yaml config.yaml
   ~~~

5. Double-click [run-app.bat](run-app.bat).
6. The browser should open to http://127.0.0.1:8787.

For the packaged version, use [docs/WINDOWS_EXE.md](docs/WINDOWS_EXE.md). The packaged app is an onedir build and requires ffmpeg.exe beside SubScript.exe.

### Make your first clip

1. Click **Create & Publish a Clip**.
2. Drop a video into **Bring in your footage**, or click **Browse files**.
3. Leave **Start automatically** checked if you are unsure.
4. Click **Make my clip**.
5. Wait for the **Review** section to appear.
6. Watch both previews:
   - **Horizontal 16:9** for regular video;
   - **Vertical 9:16** for TikTok, Shorts, and Reels.
7. Choose one:
   - **Approve as-is & save**;
   - **Trim & preview again**; or
   - **Discard clip**.

Nothing is published until you approve the clip. With the default settings, approval saves a local export pack and does not upload anything.

## The screen-by-screen flow

### 1. Start screen

URL: /.

The start screen is the app’s entry point. It does not show the full editor, OAuth settings, or advanced controls. It asks what you want to do today and sends you to the correct workspace.

The **Settings** link is for returning users who want to jump directly to publishing connections, autopilot profiles, or brand style.

### 2. One-off clip workspace

URL: /clip.

The clip workspace is the complete manual workflow:

Source → Clip → Style → Review → Publish

The left menu provides shortcuts to those sections. You can use the defaults from top to bottom, or jump to a section when you already know what you want.

#### Source

Choose one of these inputs:

- drag-and-drop or browse for a video;
- paste a file path from this computer; or
- use the live replay-buffer card when a replay source is configured.

Supported video extensions include .mp4, .mov, .mkv, .webm, .avi, and .m4v.

#### Clip

The easiest choice is **Auto highlights**. SubScript analyzes audio loudness and suggests moments that may be worth clipping. If analysis cannot run, it falls back to the configured buffer length.

You can also choose:

- **Last 30 seconds** or the configured buffer length;
- **Custom start and duration**; or
- a suggested highlight chip that fills in the custom values for you.

The original source file is not overwritten.

#### Style

Style settings apply to new clips:

- watermark/logo and corner position;
- opacity and margin;
- captions on or off;
- caption engine: automatic, demo, or optional Whisper fallback;
- background music and volume;
- multiple intro clips; and
- multiple outro clips.

Intro and outro files are optional. When several are uploaded, SubScript rotates through them. If a bumper render fails, the main gameplay render can still complete.

#### Review

The review card shows the actual generated media. The vertical preview is a real 9:16 video, not a square crop or a stretched presentation frame.

Review actions:

- **Approve as-is & save** keeps the full selected clip;
- **Trim & preview again** trims the master, rebuilds both formats, and lets you review again;
- **Discard clip** removes the clip from the pending review queue.

The trim fields use seconds. For example, start 12.5 and end 27 keeps the section from 12.5 seconds through 27 seconds.

#### Publish

Publishing is optional. Review-first mode is the default and is recommended while testing.

The Publish section lets you:

- choose review-first or automatic delivery;
- enable or disable destinations;
- generate sample titles, descriptions, and tags;
- edit the copy for each platform; and
- connect supported accounts.

Manual export packs work without any account connection.

### 3. Autopilot management

URL: /automation.

This page lists saved automated profiles. Each profile displays:

- profile name;
- current state: Running, Ready to start, or Paused;
- the folder it watches;
- the hotkey and clip length;
- selected destinations; and
- Edit, Start watching, or Stop watching controls.

Use **Build a workflow** to create another profile. Profiles remain separate because each one owns a different replay/VOD folder.

### 4. Guided automation builder

URL: /automation/new.

Editing an existing profile uses /automation/<profile-id>/edit.

The builder is deliberately a slideshow-style workflow. Only the current step is shown, and **Next** stays disabled until that step is valid.

#### Step 1 — Name + VOD folder

Enter:

- a recognizable profile name, such as Main stream or Ranked clips;
- the real folder where this profile’s replay files will be saved.

The folder must already exist. Two profiles cannot use the same folder.

#### Step 2 — Trigger

Choose:

- the SubScript shortcut, such as ctrl+shift+c; and
- the clip length from 5 to 300 seconds.

Do not use the same shortcut as the recorder’s Save Replay shortcut. The intended order is:

1. the recorder finishes writing a replay;
2. you press the SubScript shortcut;
3. SubScript finds the newest video in that profile’s folder;
4. SubScript creates the clip and continues through the saved workflow.

#### Step 3 — Delivery mode

Choose one:

- **Review first** — generate the clip and wait for approval;
- **Automatic** — continue through the saved delivery plan without waiting for manual approval.

Review-first mode is safest for a first test.

#### Step 4 — Destinations

Choose the destinations for this profile and optionally set each destination’s format and post copy.

Automatic mode requires at least one selected destination. Review-first mode can be saved without a destination so you can use the profile as a local clip watcher.

#### Step 5 — Test + save

Before saving, confirm the trigger order shown on screen. The available actions are:

- **Create safe test preview** — uses the newest replay in the folder, forces review mode, and publishes nothing;
- **Save profile** — saves the profile without arming its watcher;
- **Save & start profile** — saves the profile and starts watching immediately.

After saving, SubScript returns to the start screen with a confirmation. Use **Put My Content on Autopilot** again to see and manage the saved profile.

## Live streaming setup

### OBS replay buffer

1. In OBS, open **Settings → Output**.
2. Turn **Replay Buffer** on.
3. Set the replay length to at least the profile’s clip length, normally 30 seconds.
4. Confirm where OBS saves replay files.
5. Create an autopilot profile using that folder.
6. Save a replay, wait until OBS finishes writing it, then press the profile’s SubScript shortcut.

SubScript watches for a completed video file. It does not read a half-written file while OBS is still saving it.

The older global live configuration is still supported for compatibility, but new users should use the profile builder because it keeps multiple stream setups separate.

## What happens to a video

The rendering pipeline is:

source → master → brand → landscape + vertical → captions/music → review → approval → export/publish

Every approved pack normally contains:

| File | Purpose |
|---|---|
| master.mp4 | The selected or trimmed master video |
| horizontal.mp4 | Landscape 16:9 export |
| vertical.mp4 | Vertical 9:16 export without burned-in captions |
| vertical_captioned.mp4 | Vertical 9:16 export with captions when enabled |
| PLATFORMS.txt | Human-readable destination checklist |
| manifest.json | Export metadata |
| for_<platform>/ | Platform-specific manual pack and instructions |

Approved output is saved under:

~~~text
out\\approved\\<clip-id>\\
~~~

The app opens that folder after approval when Windows allows it.

### Video dimensions

The target output dimensions come from the output configuration. The aspect ratios are always maintained:

- landscape: width-to-height ratio 16:9;
- vertical: width-to-height ratio 9:16;
- sample production output: 1920x1080 and 1080x1920;
- small test output: 320x180 and 270x480.

SubScript also forces square pixels (1:1 sample aspect ratio) so players and platforms do not interpret the video as distorted.

## Branding and editing details

### Watermark

Upload a PNG from **Style → Watermark**. The saved brand settings are written to assets/ and config.yaml and apply to future clips.

### Intro and outro rotation

Upload multiple short clips in **Intro & outro clips**. SubScript stores them under:

~~~text
assets\\intros\\
assets\\outros\\
~~~

The pipeline rotates through the available files. Keep bumpers short and use compatible video/audio formats for the smoothest render.

### Captions

Caption behavior is controlled by captions.engine:

| Value | Behavior |
|---|---|
| auto | Use faster-whisper when installed; otherwise use the safe demo fallback |
| demo | Always use the demo SRT |
| whisper | Prefer speech-to-text and fall back safely if unavailable |

Whisper is optional:

~~~bat
.venv\\Scripts\\pip install -r requirements-whisper.txt
~~~

Without Whisper, the app still renders and the UI clearly indicates that the fallback caption engine is being used.

### Music

Upload an MP3 in the Style section or place one at assets/music.mp3. Keep the bed volume low so gameplay remains understandable. Missing music or a failed mix does not stop the main clip workflow.

## Publishing and OAuth

SubScript keeps local account authentication separate from social publishing permissions. The local /login boundary is only a compatibility boundary for future account authentication; it does not pretend that TikTok, YouTube, or another social provider is the SubScript account system.

### Current destination behavior

| Destination | Current behavior | Credentials needed for local packs? |
|---|---|---:|
| YouTube Shorts | OAuth upload when enabled; otherwise local pack | No |
| TikTok | Local pack, TikTok draft, or direct posting depending on approval/configuration | No for local pack |
| Instagram | Local upload pack | No |
| Facebook | Local upload pack | No |
| X / Twitter | Local upload pack | No |
| Rumble | Local upload pack | No |

The application is intentionally fail-soft: if one enabled destination fails, the approved local pack is still saved and the banner reports the per-platform result.

Do not request or select a social product/scope until that connector is actually implemented and demonstrated. Unused products and scopes can delay platform review.

### TikTok connector

TikTok is a separate publishing connection. It is not the same thing as opening SubScript.

1. In TikTok for Developers, add the products required by the chosen delivery mode:
   - Login Kit;
   - Content Posting API.
2. Request only the scope you need:
   - video.publish for Direct post;
   - video.upload for sending a draft to TikTok.
3. Register this exact redirect URI:

   ~~~text
   http://127.0.0.1:8787/connections/tiktok/callback
   ~~~

4. Put the private values in .env:

   ~~~text
   TIKTOK_CLIENT_KEY=your_client_key
   TIKTOK_CLIENT_SECRET=your_client_secret
   TIKTOK_REDIRECT_URI=http://127.0.0.1:8787/connections/tiktok/callback
   ~~~

5. Restart SubScript.
6. Open /clip, go to **Publish**, enable TikTok, and choose the delivery mode.
7. Click **Connect TikTok**.
8. Finish authorization in the browser and return to SubScript.

Tokens are saved locally in the configured token file and are gitignored. Keep TikTok privacy set to **Private** while testing. TikTok may restrict unaudited applications to private posting until review is complete.

If direct posting is not approved yet, use **Local upload pack** or **Send to TikTok drafts**. Those paths still let you demonstrate the generated video without claiming the direct-post connector is ready.

### YouTube connector

1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project.
3. Enable **YouTube Data API v3**.
4. Create an OAuth client ID for a desktop application.
5. Download the JSON file and save it as credentials.json, or configure another path through .env/config.yaml.
6. Keep this safe while testing:

   ~~~yaml
   youtube:
     enabled: false
     privacy: "unlisted"
     client_secrets_file: "credentials.json"
   ~~~

7. Restart the app, make a clip, and approve it.
8. When Google sign-in opens, grant access.
9. Only after a successful private/unlisted test should you set youtube.enabled: true.

YouTube upload authorization requires OAuth. API keys alone are not sufficient for uploading or changing user-owned content. The token is stored locally and must never be committed.

## Configuration basics

The normal files are:

| File | Purpose |
|---|---|
| config.example.yaml | Safe template copied to config.yaml |
| config.yaml | Your local settings; do not commit private values |
| .env | Private OAuth and environment overrides; do not commit |
| out/ | Generated clips, review queue, approved packs, and uploads |
| assets/ | Logo, intro/outro, and music files |
| test-clips/ | Optional local sample videos |

Useful settings include:

~~~yaml
buffer_seconds: 30
hotkey: "ctrl+shift+c"

review:
  require_approval: true

output:
  dir: "out"
  landscape_width: 1920
  landscape_height: 1080
  shorts_width: 1080
  shorts_height: 1920
~~~

For beginners, change settings in the browser whenever a UI control exists. Edit YAML only for advanced configuration or troubleshooting.

## Local server and port 8787

The browser app runs on:

~~~text
http://127.0.0.1:8787
~~~

The port stays open only while the SubScript process is running. It does not expose the app publicly by itself.

The same port matters for TikTok because the registered callback is:

~~~text
http://127.0.0.1:8787/connections/tiktok/callback
~~~

If you see:

~~~text
[WinError 10048] only one usage of each socket address is normally permitted
~~~

another SubScript process is already using port 8787. Usually this means the app is already running. Open http://127.0.0.1:8787 instead of launching a second copy.

If the existing copy is stuck, close its black terminal window. As a last resort, find the process using the port:

~~~powershell
Get-NetTCPConnection -LocalPort 8787 | Select-Object OwningProcess
Get-Process -Id <PID>
Stop-Process -Id <PID>
~~~

Do not change the port while completing TikTok setup unless you also update the TikTok redirect URI and .env value to exactly match.

## Troubleshooting for beginners

| Symptom | What it means | Fix |
|---|---|---|
| Browser did not open | The server may still be running | Visit http://127.0.0.1:8787 manually |
| Port 8787 is already in use | Another copy is already running | Use the existing browser window or close the old process |
| FFmpeg not found | The video processor is missing | Install FFmpeg or place ffmpeg.exe beside the packaged app |
| Make my clip is disabled | A video has not been selected | Drop a video or use Browse files |
| Auto highlights failed | Audio analysis could not run | SubScript uses the configured last-N-seconds fallback |
| Review is empty | No clip has been generated yet | Return to Source and click Make my clip |
| TikTok Connect is greyed out | Client credentials or redirect setup is missing | Check .env, the exact callback URL, and restart SubScript |
| TikTok returns an incomplete response | Authorization did not finish or the redirect did not match | Start Connect TikTok again and finish the browser flow |
| Direct post is unavailable | TikTok has not approved the required product/scope | Use Local upload pack or TikTok drafts while waiting |
| YouTube asks to sign in every time | The token cannot be saved | Check that token.json is writable and not being deleted |
| Video looks wrong | The preview or output settings are not being read | Confirm the generated file is the vertical 9:16 variant and restart the app after config changes |
| An automated profile finds the wrong replay | Two profiles share a folder | Give every profile its own replay folder |
| Automation does nothing | The watcher is not running or the replay is still being written | Use Start watching, wait for OBS to finish saving, then press the profile hotkey |

## Command-line options

The browser is the recommended interface. These commands use the same pipeline when needed:

Create a clip from a sample file:

~~~bat
python -m subscript --source test-clips\\your.mp4
~~~

Create a custom section:

~~~bat
python -m subscript --source test-clips\\vod.mp4 --start 3720 --duration 45
python -m subscript --source test-clips\\vod.mp4 --start 1:02:00 --duration 00:00:45
~~~

Open the browser app:

~~~bat
python -m subscript --app
~~~

Run the legacy/global live watcher:

~~~bat
python -m subscript --watch
python -m subscript --watch --source path\\to\\buffer-export.mp4
~~~

## Developer workflow

Install development dependencies:

~~~bat
.venv\\Scripts\\pip install -r requirements-dev.txt
~~~

Run the full test suite:

~~~bat
.venv\\Scripts\\pytest.exe -q
~~~

Run Python compilation checks:

~~~bat
.venv\\Scripts\\python.exe -m compileall -q subscript
~~~

The test suite covers the entry router, clip workspace, automation slideshow validation, profile separation, start/stop controls, publishing redirects, OAuth callback preservation, review actions, intro/outro uploads, and video dimensions when FFmpeg is available.

Before committing:

~~~bat
git diff --check
git status --short --branch
git log -1 --oneline
~~~

Then commit and push:

~~~bat
git add README.md docs subscript tests
git commit -m "docs: document the redesigned SubScript flow"
git push origin main
~~~

Confirm alignment:

~~~bat
git fetch origin
git status --short --branch
~~~

The expected result is a clean working tree showing main...origin/main with no ahead/behind count.

## Public website and legal pages

The public static site for developer review is in [docs/](docs/). It includes the public homepage, [Terms of Service](docs/terms/), and [Privacy Policy](docs/privacy/). See [docs/GITHUB_PAGES.md](docs/GITHUB_PAGES.md) for the GitHub Pages setup and expected Website, Terms, and Privacy URLs.

## Repository map

| Location | Role |
|---|---|
| subscript/live_app.py | Main FastAPI app and clip workspace route |
| subscript/automation_profiles.py | Automation management, builder, and profile persistence |
| subscript/live_ui.py | Live watcher and profile watcher helpers |
| subscript/pipeline.py | Main render pipeline |
| subscript/reframe.py | Landscape and vertical rendering |
| subscript/publishing_routes.py | Publishing settings and OAuth callback routes |
| subscript/publish/ | Platform publishing adapters and local export packs |
| subscript/static/snippets/ | HTML screen templates |
| subscript/static/review.css | Shared visual styling |
| subscript/static/app.js | Clip controls and automation slideshow behavior |
| tests/ | Automated regression tests |
| docs/ | Public site and setup documentation |

## Safety rules

- Do not commit .env, config.yaml, credentials.json, token.json, or TikTok token files.
- Keep TikTok privacy set to Private while testing.
- Keep YouTube disabled until a private or unlisted test succeeds.
- Use Review first until the generated clips and copy are reliable.
- Use a different folder for every automated profile.
- Do not select platform products/scopes that the app does not actually use.
- Keep the local server terminal open while using the browser app.

## License

Private — SensoredRooster.
