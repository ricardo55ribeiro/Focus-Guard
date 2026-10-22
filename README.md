# FocusGuard

**AI-powered focus enforcement for Windows.** FocusGuard monitors what you're doing on your PC during study sessions and intervenes when you get distracted, by using local AI to understand context, not just blocklists.

---

## What It Does

Most website blockers use static lists. FocusGuard is different: you set a study goal in plain English (e.g. "Learn pointers in C"), and FocusGuard uses a local AI model to classify whether what you're doing actually supports that goal. Watching a C tutorial on YouTube? Fine. Scrolling LinkedIn? Not fine.

When distraction is detected:
1. A soft **system notification** warns you first ("You seem distracted. Get back to work!")
2. If you keep procrastinating, a **fullscreen pledge popup** appears requiring you to type a commitment sentence before you can continue
3. The distracting **browser tab is redirected** to a block page

Activity classification runs locally through Ollama; no cloud API key is required. Setup downloads dependencies and models. See [Privacy](#privacy) for local storage and retention details.

---

## Features

- **Context-aware classification**: AI understands your study goal, not just the URL
- **Tiered distraction response**: soft warning first, hard block second
- **Browser extension**: captures real URLs and page titles for accurate classification
- **Always-block lists**: instant block for known distractions (social media, games) without AI overhead
- **Always-allow lists**: whitelisted domains never trigger classification
- **Background mode**: runs automatically on Windows startup, silently enforcing your always-block lists. Optionally add plain-English rules (e.g. "no adult content") for AI-backed enforcement — violations are silently blocked (tab redirected or app minimized) with a brief notification explaining what was blocked. No notifications fire for normal activity.
- **Auto-start on boot**: optional toggle in Settings to launch FocusGuard silently in background mode when Windows starts.
- **Pledge popup**: fullscreen intervention with a typed commitment before dismissal
- **Session history**: review past sessions with focus %, distraction %, blocks triggered
- **System tray icon**: green when focused, red when distracted, runs silently in background
- **Auto-manages Ollama**: starts and stops the local AI server automatically
- **Desktop shortcut launcher**: no terminal required, launches like a normal app
- **Hides during sessions**: disappears from screen and taskbar while monitoring, restore with a tray icon click

---

## System Requirements

- **OS:** Windows 10 or Windows 11 (64-bit)
- **Python:** 3.11 or newer
- **Browser:** Firefox, Chrome, Brave, or Microsoft Edge
- **RAM:** 8GB minimum (16GB recommended for running models smoothly alongside other apps)
- **Disk:** ~10GB free (for Ollama + two AI models)
- **Internet:** Only needed for initial setup (downloading Ollama and models)

---

## Installation

Follow these steps in order. Do not skip any.

### Step 1: Install Python

Download Python 3.11 or newer from [python.org](https://www.python.org/downloads/).

During installation, **check the box that says "Add Python to PATH"**.

Verify installation by opening a terminal and running:
```
python --version
```
You should see something like `Python 3.12.0`.

---

### Step 2: Clone or Download This Repository

If you have Git installed, copy this repository's HTTPS URL from GitHub's **Code** menu and substitute it for `<repository-url>`:
```
git clone <repository-url> focus-guard
cd focus-guard
```

Or download the ZIP from GitHub and extract it anywhere on your PC.

---

### Step 3: Run the Installer

Double-click `install.bat` at the project root. This will:

- Install all Python dependencies
- Download and install Ollama (if not already installed)
- Download the two AI models (~7-8 GB, takes 15-30 minutes)
- Create the Desktop shortcut

If you prefer to do this manually, see the steps below.

<details>
<summary>Manual installation</summary>

**Install Python dependencies:**
```
python -m pip install -r requirements.txt
```

**Install Ollama:**
Go to [ollama.com](https://ollama.com), download and run the installer.

**Download the AI models:**
```
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
```

**Create default settings (PowerShell, from the repository root):**
```powershell
New-Item -ItemType Directory -Force agent/config | Out-Null
if (-not (Test-Path agent/config/settings.json)) {
    Copy-Item settings.example.json agent/config/settings.json
}
```

**Create the Desktop shortcut:**
```
create_shortcut.bat
```

</details>

---

### Step 4: Install the Browser Extension

FocusGuard uses a browser extension to capture the real URL and page title of your active tab. Without it, classification is less accurate.

**Firefox:**
The existing signed release is available from the Firefox Add-Ons store. Store releases may lag this source; maintainers must submit updated extension packages separately. For source testing, use `about:debugging` → This Firefox → Load Temporary Add-on and select `extension/manifest.json`. Temporary installs are removed when Firefox restarts.

Signed release:
[addons.mozilla.org/addon/focus_guard_ai](https://addons.mozilla.org/addon/focus_guard_ai/)

**Chrome / Brave / Edge:**
1. Navigate to `chrome://extensions`
2. Enable **"Developer mode"** in the top right
3. Click **"Load unpacked"**
4. Select the `focus-guard/extension/` folder

---

## Usage

1. **Double-click the FocusGuard shortcut** on your Desktop (or run `python agent/main.py`)
2. **Enter your study goal**: be specific: "Learn pointers in C" works better than "Study"
3. **Click Start Session**: FocusGuard hides from your screen and taskbar, running silently in the background
4. Work normally: FocusGuard monitors from the system tray
5. When distracted, you'll receive a notification first, then a hard block if you stay distracted
6. **Left-click the tray icon** to bring FocusGuard back, or right-click → **Stop Session** when done
7. A session summary is saved showing your focus %, distraction %, and blocks triggered

---

## Configuration

Open **Settings** from the main screen to configure. Settings opens as a full in-app screen (use the ← Back button to discard changes or Save to apply them):

| Setting | Description | Default |
|---|---|---|
| Check interval | How often FocusGuard checks what you're doing (seconds) | 20 |
| Background check interval | How often background mode checks activity (seconds) — separate from the session check interval | 60 |
| Warning countdown | Seconds shown on the pledge popup countdown | 15 |
| Launch on Windows startup | Starts FocusGuard automatically in background mode when you log in | Off |
| Background mode rules | Plain-English rules for AI-backed background enforcement (e.g. 'no adult content') | Empty |
| Always block domains | Domains always blocked instantly, no AI needed | twitter.com, x.com, reddit.com, etc. |
| Always allow domains | Domains always allowed, never classified | github.com, stackoverflow.com, etc. |
| Always block processes | Desktop apps always blocked by process name | steam.exe, etc. |

Settings are saved to `agent/config/settings.json`. A reference copy with defaults is provided at `settings.example.json`.

---

## Project Structure

```
focus-guard/
├── install.py                      # Installer (tkinter GUI)
├── install.bat                     # Double-click to run installer
├── agent/                          # Python desktop app
│   ├── main.py                     # Entry point (with terminal)
│   ├── app.pyw                     # Entry point (no terminal, used by shortcut)
│   ├── ui.py                       # Desktop UI (tkinter)
│   ├── monitor.py                  # Main monitoring loop
│   ├── logger.py                   # Session logging
│   ├── tray.py                     # System tray icon
│   ├── ollama_manager.py           # Auto-start/stop Ollama
│   ├── icon.ico                    # App icon
│   ├── capture/
│   │   ├── browser.py              # HTTP server receiving URL from extension
│   │   └── window.py               # Active window/process detection (Windows API)
│   ├── classifier/
│   │   ├── ai.py                   # Ollama classification + heckler/pledge generation
│   │   └── rules.py                # Fast rule-based checks (no AI)
│   ├── blocker/
│   │   ├── blocker.py              # Blocking orchestration
│   │   └── popup.py                # Fullscreen pledge popup (tkinter)
│   ├── config/
│   │   └── settings.json           # User settings (gitignored)
│   ├── logs/                       # Session JSON logs (auto-created, gitignored)
│   └── debug/                      # Debug text logs (auto-created, gitignored)
├── extension/                      # Browser extension (Firefox + Chrome)
│   ├── manifest.json
│   ├── background.js               # Sends active tab URL to Python
│   ├── blocking.html               # Block page shown when tab is redirected
│   └── blocking.js
├── settings.example.json           # Reference settings with defaults
├── launch_focusguard.vbs           # Silent launcher (no terminal)
├── create_shortcut.bat             # Creates Desktop shortcut
└── README.md
```

---

## How Classification Works

FocusGuard uses a tiered approach to minimize AI usage and maximize speed:

**Tier 1: Instant rule check (no AI)**
Process name and URL are checked against your always-block and always-allow lists. If matched, the decision is instant.

**Tier 2: AI classification**
For everything else, FocusGuard sends the process name, window title, URL, and page title to `qwen2.5:3b` running locally via Ollama. The model scores the activity 0-100 based on your study goal. Results are cached so the same URL isn't re-classified until it changes.

**Background mode:**
Background mode always enforces your always-block domain/process lists silently, with no AI and no Ollama startup required. If you also add background mode rules in Settings, FocusGuard starts Ollama and checks unmatched activity against those rules. A violation is silently blocked (browser tab redirected or window minimized) and a brief notification explains what was blocked. Activity that does not violate a rule is left alone — no notification, no interruption. In background mode, unmatched local-file URLs skip AI classification; explicit process block rules still apply.

**Distraction response:**
- First distracted check → soft system notification
- After N consecutive distracted checks (N depends on your check interval, targeting ~60 seconds total) → hard block: browser tab redirected, pledge popup shown

---

## Troubleshooting

**App doesn't start / Python not found**
Make sure Python is in your PATH. Reinstall Python and check "Add to PATH" during installation.

**"Could not start Ollama" error**
Make sure Ollama is installed from [ollama.com](https://ollama.com). Run `ollama --version` in a terminal to verify.

**Models not found**
Run `ollama list` to see downloaded models. If `qwen2.5:3b` or `qwen2.5:7b` are missing, run the pull commands from Step 3 again.

**Classification shows url=n/a**
The browser extension is not loaded or not sending data. Reinstall it and make sure FocusGuard is running before you open the browser.

**Block page appears on wrong tabs**
Tab changes during a pending block can affect which active tab is redirected. Stop the session if needed and report a reproducible example with private URLs removed.

**High CPU usage**
Reduce the check interval in Settings (increase the number, e.g. from 15 to 30 seconds). The classification model runs on CPU and is the main source of load.

---

## Privacy

FocusGuard reads the foreground process name and window title, and the extension sends the active tab URL and title to the desktop app on loopback port 9001. The desktop app sends these signals and your goal/rules to local Ollama on port 11434. It takes no screenshots and has no analytics or telemetry.

**Local storage contains browsing data.** Session JSON files in `agent/logs/` include full URLs, titles, timestamps, process names, scores, reasons, and block events. URLs can contain private paths or access tokens. Settings and background rules live in `agent/config/settings.json`. Console output can contain goals, titles, and URLs; redirected output or debug logs may retain it. These files are not encrypted by FocusGuard and have no automatic expiry.

The extension stores the most recently blocked URL, title, and reason in `chrome.storage.local` so its block page can work. That record persists until replaced, cleared in the browser, or removed with the extension. The extension sends active-tab metadata while enabled, even outside a study session if the desktop server is running. Disable it when you do not want capture.

To erase desktop history, stop FocusGuard and delete the files in `agent/logs/` and any saved debug output. Delete `agent/config/settings.json` to erase settings, then rerun setup to recreate defaults. Clear extension data separately. Your OS, browser, backups, or independently configured Ollama server may retain additional data.

FocusGuard's AI client ignores remote `OLLAMA_HOST` and proxy environment settings. Setup still needs internet access to package/model distribution services; Firefox's add-on store and updates also use the network. See [Privacy Policy.txt](Privacy%20Policy.txt) and [SECURITY.md](SECURITY.md).

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

You may use, modify, and redistribute FocusGuard under the terms of that license. See the full license for source-distribution obligations and warranty limitations.

Ollama and the downloaded models have separate terms; see [THIRD_PARTY.md](THIRD_PARTY.md).

See the [LICENSE](LICENSE) file for the full license text, or read it at [gnu.org/licenses/gpl-3.0](https://www.gnu.org/licenses/gpl-3.0.html).

---

## Contributing

This project is currently in active personal development. If you find bugs, open an issue. If you want to contribute, open a PR. All are welcome. Please remove personal data from reports. See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and [SECURITY.md](SECURITY.md) for vulnerability reporting.
