# FocusGuard

FocusGuard is a Windows app that helps you stay on task using local AI. Give it a goal, such as "learn pointers in C", and it checks whether your current activity fits. A programming tutorial and an unrelated video might be on the same website, so blocking the whole site isn't always useful.

It uses the active window title and browser tab to make that decision. If you drift off, it sends a notification. Keep going and you'll get a fullscreen prompt asking you to type a short pledge before returning to work. Browser tabs can also be redirected to a block page.

Built with Python, Tkinter, a JavaScript browser extension and [Ollama](https://ollama.com). Classification runs on your PC, without an API key.

## Setup

You'll need **Windows 10 or 11 (64-bit)** and **Python 3.11+**. Allow about **10 GB of free disk space** for Ollama and the models. **16 GB of RAM** is recommended.

1. Install [Python](https://www.python.org/downloads/) and tick **Add Python to PATH**.
2. Download and extract this repository, or clone it:

   ```powershell
   git clone https://github.com/ricardo55ribeiro/focus-guard.git
   cd focus-guard
   ```

3. Double-click **install.bat**. It installs the Python packages, sets up Ollama, downloads the models and creates a desktop shortcut. Follow any Ollama installer prompts; the downloads can take a while.
4. Install the browser extension:
   - **Firefox:** use the [Firefox add-on](https://addons.mozilla.org/addon/focus_guard_ai/). To try the version in this repository, open `about:debugging`, choose **This Firefox → Load Temporary Add-on**, and select `extension/manifest.json`. Temporary add-ons disappear when Firefox restarts.
   - **Chrome, Brave or Edge:** open your browser's extensions page, enable **Developer mode**, select **Load unpacked**, and choose the `extension` folder.

## Using it

Once installed, open FocusGuard from the desktop shortcut, enter a specific goal and click **Start Session**. The window hides while monitoring runs. Click the tray icon to bring it back, or right-click it to stop the session.

In **Settings**, you can block particular sites or apps, allow trusted domains, and adjust how often activity is checked. There's also a background mode for enforcing your lists and optional rules outside a study session, with an option to launch it when Windows starts. **View History** shows past sessions and their focus statistics.

The AI can get things wrong. The block page has an **I was actually studying this** button to add a site's domain to your allow list; explicit block rules still take priority.

Session history saves full URLs and page titles locally. The extension also keeps the latest blocked page. Avoid sharing these files in bug reports. Details and deletion instructions are in the [privacy policy](Privacy%20Policy.txt).

## If something doesn't work

Run `python agent/main.py` from the project folder to see errors in a terminal. If Ollama won't start, check that `ollama --version` works. If models are missing, run:

```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
```

If browser activity isn't showing up, check that the extension is enabled and has permission to access localhost.

## Working on the code

The desktop app is in `agent/`, the browser extension in `extension/`, and setup is handled by `install.py`. Explicit block/allow rules are checked first; other activity goes to Qwen2.5 3B, while the 7B model writes the reminders and pledges.

After installing the dependencies, run the tests from the project folder (the extension tests need Node.js):

```powershell
python -m unittest discover -s tests -v
node --test tests/extension.test.js
```
