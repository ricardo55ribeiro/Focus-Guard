import platform
import sys

if __name__ == "__main__" and platform.system() != "Windows":
    print("FocusGuard Installer is only supported on Windows.")
    sys.exit(1)

import json
import os
import queue
import re
import subprocess
import threading
import time
import tempfile
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk


ROOT_DIR = Path(__file__).resolve().parent
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
SETTINGS_FILE = ROOT_DIR / "agent" / "config" / "settings.json"
SHORTCUT_SCRIPT = ROOT_DIR / "create_shortcut.bat"
OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
# The download must not overwrite or execute a pre-existing repository file.
_installer_temp_dir = tempfile.TemporaryDirectory(prefix="focusguard-install-")
OLLAMA_INSTALLER_PATH = Path(_installer_temp_dir.name) / "OllamaSetup.exe"

BG = "#1a1a1a"
PANEL_BG = "#242424"
TEXT = "#ffffff"
MUTED = "#9e9e9e"
GREEN = "#4caf50"
RED = "#f44336"
BUTTON_GREY = "#3a3a3a"
ENTRY_BG = "#111111"

WINDOW_WIDTH = 680
WINDOW_HEIGHT = 640
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROGRESS_BLOCK_CHARS = ("\u2595", "\u258f")

DEFAULT_SETTINGS = {
    "session_check_interval_seconds": 20,
    "background_check_interval_seconds": 60,
    "warning_duration_seconds": 15,
    "background_instructions": [],
    "always_block_domains": [
        "twitter.com",
        "x.com",
        "reddit.com",
        "discord.com",
        "instagram.com",
        "facebook.com",
        "tiktok.com",
        "chess.com",
        "twitch.tv",
    ],
    "always_allow_domains": [
        "github.com",
        "stackoverflow.com",
        "docs.python.org",
    ],
    "always_block_processes": [
        "steam.exe",
        "epicgameslauncher.exe",
        "leagueclient.exe",
        "bluestacks.exe",
    ],
}


class InstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FocusGuard Installer")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.messages: queue.Queue = queue.Queue()
        self.install_thread: threading.Thread | None = None
        self.status_var = tk.StringVar(value="Ready to install")

        self.configure_window()
        self.configure_style()
        self.build_install_screen()
        self.root.after(150, self.poll_queue)

    def configure_window(self) -> None:
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - WINDOW_WIDTH) // 2)
        y = max(0, (screen_height - WINDOW_HEIGHT) // 2)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

    def configure_style(self) -> None:
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure(
            "Green.Horizontal.TProgressbar",
            troughcolor=ENTRY_BG,
            background=GREEN,
            bordercolor=ENTRY_BG,
            lightcolor=GREEN,
            darkcolor=GREEN,
        )

    def clear_screen(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def make_label(
        self,
        parent: tk.Widget,
        text: str = "",
        *,
        textvariable: tk.StringVar | None = None,
        size: int = 11,
        weight: str = "normal",
        fg: str = TEXT,
        bg: str = BG,
        wraplength: int | None = None,
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            bg=bg,
            fg=fg,
            font=("Segoe UI", size, weight),
            wraplength=wraplength,
            justify="center",
        )

    def make_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        bg: str,
        fg: str = TEXT,
        width: int = 22,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            disabledforeground=MUTED,
            bd=0,
            relief="flat",
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 11, "bold"),
            width=width,
            padx=12,
            pady=10,
        )

    def build_install_screen(self) -> None:
        self.clear_screen()
        self.root.configure(bg=BG)

        container = tk.Frame(self.root, bg=BG, padx=38, pady=24)
        container.pack(fill="both", expand=True)

        self.make_label(container, "FocusGuard", size=26, weight="bold").pack(pady=(0, 3))
        self.make_label(container, "One-time setup", size=12, fg=MUTED).pack(pady=(0, 18))

        self.make_label(
            container,
            textvariable=self.status_var,
            size=11,
            weight="bold",
        ).pack(pady=(0, 8))

        self.progress = ttk.Progressbar(
            container,
            style="Green.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress.pack(fill="x", pady=(0, 16))

        log_frame = tk.Frame(container, bg=BG)
        log_frame.pack(fill="both", expand=True, pady=(0, 16))

        scrollbar = tk.Scrollbar(
            log_frame,
            bg=BUTTON_GREY,
            troughcolor=ENTRY_BG,
            activebackground=GREEN,
            highlightthickness=0,
        )
        scrollbar.pack(side="right", fill="y")

        self.log_box = tk.Text(
            log_frame,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=GREEN,
            selectforeground=TEXT,
            font=("Consolas", 9),
            wrap="word",
            bd=0,
            padx=12,
            pady=10,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#333333",
            highlightcolor=GREEN,
            yscrollcommand=scrollbar.set,
        )
        self.log_box.tag_configure("error", foreground=RED)
        self.log_box.configure(state="disabled")
        self.log_box.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.log_box.yview)

        self.install_button = self.make_button(
            container,
            "Install FocusGuard",
            self.start_install,
            bg=GREEN,
        )
        self.install_button.pack(pady=(0, 10))

        self.make_label(
            container,
            "Model downloads are ~7-8 GB and may take 15-30 minutes.",
            size=9,
            fg=MUTED,
        ).pack()

    def append_log(self, text: str, tag: str | None = None) -> None:
        if not text:
            return
        if not text.endswith("\n"):
            text = f"{text}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text, tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start_install(self) -> None:
        if self.install_thread and self.install_thread.is_alive():
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.status_var.set("Starting installation")
        self.progress.configure(value=0)
        self.install_button.configure(state="disabled", bg=BUTTON_GREY, activebackground=BUTTON_GREY)

        self.install_thread = threading.Thread(
            target=run_install,
            args=(self.messages,),
            daemon=True,
        )
        self.install_thread.start()

    def poll_queue(self) -> None:
        try:
            while True:
                message = self.messages.get_nowait()
                if "log" in message:
                    self.append_log(str(message["log"]))
                if "progress" in message:
                    self.progress.configure(value=float(message["progress"]))
                if "status" in message:
                    self.status_var.set(str(message["status"]))
                if "error" in message:
                    self.append_log(str(message["error"]), "error")
                    self.status_var.set("Installation failed")
                    self.install_button.configure(state="normal", bg=GREEN, activebackground=GREEN)
                if message.get("done"):
                    self.show_completion_screen()
                    return
        except queue.Empty:
            pass

        self.root.after(150, self.poll_queue)

    def show_completion_screen(self) -> None:
        self.clear_screen()
        self.root.configure(bg=BG)

        container = tk.Frame(self.root, bg=BG, padx=52, pady=54)
        container.pack(fill="both", expand=True)

        self.make_label(
            container,
            "\u2713 Installation Complete",
            size=23,
            weight="bold",
            fg=GREEN,
        ).pack(pady=(0, 18))

        self.make_label(
            container,
            "FocusGuard is on your Desktop. Double-click to start.",
            size=12,
            wraplength=520,
        ).pack(pady=(0, 28))

        tk.Frame(container, bg="#333333", height=1).pack(fill="x", pady=(0, 28))

        self.make_label(
            container,
            "Last step: install the browser extension",
            size=13,
            weight="bold",
        ).pack(pady=(0, 10))

        self.make_label(
            container,
            "The extension lets FocusGuard see URLs, not just window titles.",
            size=11,
            fg=MUTED,
            wraplength=520,
        ).pack(pady=(0, 20))

        open_button = self.make_button(
            container,
            "Open Firefox Add-Ons Page",
            lambda: self.open_firefox_addons(open_button),
            bg=GREEN,
            width=26,
        )
        open_button.pack(pady=(0, 16))

        self.make_label(
            container,
            "Chrome users: load the extension/ folder unpacked via chrome://extensions",
            size=9,
            fg=MUTED,
            wraplength=520,
        ).pack(pady=(0, 34))

        self.make_button(
            container,
            "Close Installer",
            self.root.destroy,
            bg=BUTTON_GREY,
        ).pack()

    def open_firefox_addons(self, button: tk.Button) -> None:
        webbrowser.open("https://addons.mozilla.org/addon/focus_guard_ai/")
        button.configure(
            text="Opened \u2713",
            state="disabled",
            bg=BUTTON_GREY,
            activebackground=BUTTON_GREY,
        )


def put_log(messages: queue.Queue, text: str) -> None:
    if text:
        messages.put({"log": text})


def put_status(messages: queue.Queue, text: str) -> None:
    messages.put({"status": text})


def put_progress(messages: queue.Queue, value: float) -> None:
    messages.put({"progress": max(0.0, min(100.0, float(value)))})


def put_error(messages: queue.Queue, text: str) -> None:
    messages.put({"error": text})


def run_install(messages: queue.Queue) -> None:
    try:
        if not check_python_version(messages):
            return
        if not install_requirements(messages):
            return
        if not ensure_ollama_installed(messages):
            return
        if not ensure_ollama_running(messages):
            return
        if not pull_model(messages, "qwen2.5:3b", 25.0, 57.0, "Step 5 - Pulling qwen2.5:3b"):
            return
        if not pull_model(messages, "qwen2.5:7b", 57.0, 91.0, "Step 6 - Pulling qwen2.5:7b"):
            return
        create_desktop_shortcut(messages)
        create_settings_if_missing(messages)

        put_status(messages, "Step 9 - Done")
        put_progress(messages, 100)
        put_log(messages, "Installation complete.")
        messages.put({"done": True})
    except Exception as exc:
        put_error(messages, f"Unexpected installer error: {exc}")


def check_python_version(messages: queue.Queue) -> bool:
    put_status(messages, "Step 1 - Checking Python version")
    put_progress(messages, 2)
    version = ".".join(str(part) for part in sys.version_info[:3])
    put_log(messages, f"Python {version} detected.")
    if sys.version_info < (3, 11):
        put_error(messages, "Python 3.11+ is required. Please upgrade Python and run the installer again.")
        return False
    return True


def install_requirements(messages: queue.Queue) -> bool:
    put_status(messages, "Step 2 - Installing Python packages")
    put_progress(messages, 10)
    put_log(messages, "Installing requirements.txt...")

    if not REQUIREMENTS_FILE.exists():
        put_error(messages, f"Missing requirements file: {REQUIREMENTS_FILE}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        put_error(messages, f"pip install failed to start: {exc}")
        return False

    log_process_output(messages, result.stdout, result.stderr)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "No error output was captured."
        put_error(messages, f"pip install failed:\n{detail}")
        return False

    put_log(messages, "Python packages are installed.")
    return True


def ensure_ollama_installed(messages: queue.Queue) -> bool:
    put_status(messages, "Step 3 - Checking Ollama")
    put_progress(messages, 12)

    check = run_quiet(["ollama", "--version"])
    if check and check.returncode == 0:
        version_text = (check.stdout or check.stderr).strip()
        put_log(messages, "Ollama already installed.")
        if version_text:
            put_log(messages, version_text)
        put_progress(messages, 22)
        return True

    put_log(messages, "Ollama was not found. Downloading OllamaSetup.exe...")
    if not download_ollama_installer(messages):
        return False

    put_status(messages, "Step 3b - Installing Ollama")
    put_progress(messages, 22)
    put_log(messages, "Launching Ollama installer. Follow any on-screen prompts.")

    try:
        result = subprocess.run([str(OLLAMA_INSTALLER_PATH)], timeout=300)
    except subprocess.TimeoutExpired:
        put_error(messages, "Ollama installer timed out after 5 minutes.")
        return False
    except Exception as exc:
        put_error(messages, f"Ollama installer failed to start: {exc}")
        return False
    finally:
        cleanup_ollama_installer(messages)

    if result.returncode not in (0, 3010):
        put_error(messages, f"Ollama installer exited with code {result.returncode}.")
        return False

    if result.returncode == 3010:
        put_log(messages, "Ollama installer finished. Windows may ask for a reboot later.")
    else:
        put_log(messages, "Ollama installer finished.")
    return True


def run_quiet(args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            args,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return None


def download_ollama_installer(messages: queue.Queue) -> bool:
    put_status(messages, "Step 3a - Downloading Ollama")
    last_logged_bucket = {"value": -1}

    def reporthook(block_count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        downloaded = min(block_count * block_size, total_size)
        percent = int(downloaded * 100 / total_size)
        mapped = 12 + (percent / 100) * 6
        put_progress(messages, mapped)

        bucket = percent // 10
        while bucket > last_logged_bucket["value"]:
            last_logged_bucket["value"] += 1
            put_log(messages, f"Ollama download {min(last_logged_bucket['value'] * 10, 100)}%")

    try:
        if OLLAMA_INSTALLER_PATH.exists():
            OLLAMA_INSTALLER_PATH.unlink()
        urllib.request.urlretrieve(
            OLLAMA_INSTALLER_URL,
            OLLAMA_INSTALLER_PATH,
            reporthook=reporthook,
        )
    except Exception as exc:
        put_error(messages, f"Failed to download Ollama: {exc}")
        return False

    put_progress(messages, 18)
    put_log(messages, "Ollama download complete.")
    return True


def cleanup_ollama_installer(messages: queue.Queue) -> None:
    try:
        if OLLAMA_INSTALLER_PATH.exists():
            OLLAMA_INSTALLER_PATH.unlink()
    except Exception as exc:
        put_log(messages, f"Warning: could not delete OllamaSetup.exe: {exc}")


def ensure_ollama_running(messages: queue.Queue) -> bool:
    put_status(messages, "Step 4 - Starting Ollama")
    put_progress(messages, 25)

    if ollama_api_available():
        put_log(messages, "Ollama API is already running.")
        return True

    put_log(messages, "Starting Ollama server...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        )
    except Exception as exc:
        put_error(messages, f"Could not start Ollama: {exc}")
        return False

    deadline = time.time() + 60
    while time.time() < deadline:
        time.sleep(2)
        if ollama_api_available():
            put_log(messages, "Ollama is running.")
            return True

    put_error(messages, "Ollama did not respond within 60 seconds.")
    return False


def ollama_api_available() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:11434/api/tags", timeout=2):
            pass
        return True
    except Exception:
        return False


def pull_model(
    messages: queue.Queue,
    model_name: str,
    start_progress: float,
    end_progress: float,
    status: str,
) -> bool:
    put_status(messages, status)
    put_progress(messages, start_progress)
    put_log(messages, f"Pulling {model_name}. This may take a while...")

    try:
        process = subprocess.Popen(
            ["ollama", "pull", model_name],
            cwd=ROOT_DIR,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        )
    except Exception as exc:
        put_error(messages, f"Could not start ollama pull for {model_name}: {exc}")
        return False

    last_progress = start_progress
    if process.stdout is not None:
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            percent_match = re.search(r"(\d+)%", line)
            if percent_match:
                percent = max(0, min(100, int(percent_match.group(1))))
                mapped = start_progress + ((end_progress - start_progress) * percent / 100)
                if mapped > last_progress:
                    last_progress = mapped
                    put_progress(messages, mapped)

            if any(char in line for char in PROGRESS_BLOCK_CHARS):
                continue
            if not percent_match:
                put_log(messages, line)

    returncode = process.wait()
    if returncode != 0:
        put_error(messages, f"ollama pull {model_name} failed with exit code {returncode}.")
        return False

    put_progress(messages, end_progress)
    put_log(messages, f"{model_name} is ready.")
    return True


def create_desktop_shortcut(messages: queue.Queue) -> None:
    put_status(messages, "Step 7 - Creating desktop shortcut")
    put_progress(messages, 94)

    if not SHORTCUT_SCRIPT.exists():
        put_log(messages, f"Warning: shortcut script is missing: {SHORTCUT_SCRIPT}")
        return

    put_log(messages, "Creating Desktop shortcut...")
    try:
        result = subprocess.run(
            ["cmd.exe", "/c", f'"{SHORTCUT_SCRIPT}"'],
            cwd=ROOT_DIR,
            input="\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        put_log(messages, "Warning: shortcut creation timed out.")
        return
    except Exception as exc:
        put_log(messages, f"Warning: shortcut creation failed to start: {exc}")
        return

    log_process_output(messages, result.stdout, result.stderr)
    if result.returncode != 0:
        put_log(messages, f"Warning: shortcut creation exited with code {result.returncode}.")
    else:
        put_log(messages, "Desktop shortcut created.")


def create_settings_if_missing(messages: queue.Queue) -> None:
    put_status(messages, "Step 8 - Preparing settings")
    put_progress(messages, 96)

    if SETTINGS_FILE.exists():
        put_log(messages, "settings.json already exists \u2014 leaving untouched.")
        return

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_FILE.open("w", encoding="utf-8") as settings_file:
        json.dump(DEFAULT_SETTINGS, settings_file, indent=2)
        settings_file.write("\n")
    put_log(messages, "Created agent/config/settings.json.")


def log_process_output(messages: queue.Queue, stdout: str, stderr: str) -> None:
    for output in (stdout, stderr):
        for line in output.splitlines():
            if line.strip():
                put_log(messages, line)


def main() -> None:
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
