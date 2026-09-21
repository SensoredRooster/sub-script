# SubScript Installation Guide for Testers

This guide is for **Windows testers** and uses **PowerShell**.

You do not need to know Python or Git to follow it.

## 1. Install Git

Open **PowerShell** and run:

```powershell
winget install --id Git.Git -e
```

When installation finishes, close PowerShell and open it again.

Verify Git is installed:

```powershell
git --version
```

## 2. Install Python

SubScript currently uses Python 3.11.

Run:

```powershell
winget install --id Python.Python.3.11 -e
```

Close and reopen PowerShell after installation.

Verify Python:

```powershell
python --version
```

You should see something similar to:

```text
Python 3.11.x
```

## 3. Install FFmpeg

SubScript uses FFmpeg for video processing.

Run:

```powershell
winget install --id Gyan.FFmpeg -e
```

Close and reopen PowerShell after installation.

Verify FFmpeg:

```powershell
ffmpeg -version
```

If FFmpeg prints version information, it is installed correctly.

## 4. Download SubScript

Choose a folder where you want SubScript installed.

For example, to install it in your Documents folder:

```powershell
cd $HOME\Documents
```

Clone SubScript:

```powershell
git clone https://github.com/SensoredRooster/sub-script.git
```

Enter the SubScript folder:

```powershell
cd sub-script
```

## 5. Create the Python Environment

Run:

```powershell
python -m venv .venv
```

Then activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

You should now see something similar to this at the beginning of the PowerShell line:

```text
(.venv)
```

That means the SubScript Python environment is active.

### If PowerShell Blocks Activation

If you receive an error saying scripts cannot be executed, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then try again:

```powershell
.\.venv\Scripts\Activate.ps1
```

This change only applies to the current PowerShell window.

## 6. Install SubScript Dependencies

With the virtual environment active, run:

```powershell
python -m pip install --upgrade pip
```

Then install the SubScript dependencies:

```powershell
pip install -r requirements.txt
```

Allow the installation to finish completely.

## 7. Create Your Configuration File

Run:

```powershell
Copy-Item config.example.yaml config.yaml
```

This creates your personal SubScript configuration file.

Do not commit personal credentials, OAuth secrets, access tokens, or private configuration back to GitHub.

## 8. Start SubScript

Run:

```powershell
.\run-app.bat
```

SubScript should start and open in your web browser.

If it does not open automatically, visit:

```text
http://127.0.0.1:8787
```

Keep the SubScript PowerShell/server window open while using the application.

# Updating SubScript

Once SubScript is installed, you do **not** need to clone it again when a new version is available.

Open PowerShell and go to your SubScript folder:

```powershell
cd $HOME\Documents\sub-script
```

Download the newest changes:

```powershell
git pull origin main
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Update dependencies in case anything changed:

```powershell
pip install -r requirements.txt
```

Then launch SubScript:

```powershell
.\run-app.bat
```

That gives you the newest version currently pushed to the SubScript repository.

## Recommended Update Routine

Whenever you are told a new SubScript build or fix has been pushed, use:

```powershell
cd $HOME\Documents\sub-script
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run-app.bat
```

# Stopping SubScript

If SubScript is running in a PowerShell window, press:

```text
Ctrl + C
```

to stop the local server.

You can then close PowerShell normally.

# Troubleshooting

## `git` is not recognized

Close PowerShell and reopen it after installing Git.

Then try:

```powershell
git --version
```

## `python` is not recognized

Close and reopen PowerShell.

Then try:

```powershell
python --version
```

If that still fails, restart Windows.

## `ffmpeg` is not recognized

Close and reopen PowerShell after installing FFmpeg.

Try:

```powershell
ffmpeg -version
```

If necessary, restart Windows so the updated PATH is loaded.

## PowerShell says scripts are disabled

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate SubScript again:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Port 8787 is already in use

SubScript normally runs at:

```text
http://127.0.0.1:8787
```

If SubScript is already running, do not start another copy.

Check your browser first and try:

```text
http://127.0.0.1:8787
```

If the existing SubScript instance is running correctly, continue using it.

## Something broke after an update

From the SubScript folder, run:

```powershell
git status
```

Then copy the output along with any error message you see and send it to the SubScript developer.

Please also include:

- what you were doing when the issue occurred
- which screen you were on
- the source video format/resolution if the issue involved video
- any error visible in PowerShell
- a screenshot when useful

Do not post OAuth tokens, passwords, secrets, or private account credentials in bug reports.

# Tester Notes

SubScript is actively being developed.

New features and fixes may be pushed frequently.

The easiest way to stay current is:

```powershell
git pull origin main
```

before starting a new testing session.

Your feedback is valuable. Please report anything that feels confusing, broken, unexpectedly slow, visually incorrect, or difficult to understand — even if it technically works.
