import json
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"
DEFAULT_COUNTDOWN_SECONDS = 15


def _load_countdown_seconds() -> int:
    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as f:
            settings = json.load(f)
        return max(0, int(settings.get("warning_duration_seconds", DEFAULT_COUNTDOWN_SECONDS)))
    except Exception:
        return DEFAULT_COUNTDOWN_SECONDS


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            current_row.append(min(
                previous_row[j + 1] + 1,
                current_row[j] + 1,
                previous_row[j] + (c1 != c2),
            ))
        previous_row = current_row
    return previous_row[-1]


def show_pledge_popup(heckler_message: str, pledge_text: str) -> None:
    countdown_seconds = _load_countdown_seconds()

    root = tk.Tk()
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    root.configure(bg="white")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    root.title("FocusGuard")

    screen_width = root.winfo_screenwidth()
    wrap_width = max(screen_width - 160, 400)

    message_font = ("Arial", 22)
    pledge_font = ("Arial", 12, "bold")
    label_font = tkfont.Font(size=14)
    error_font = tkfont.Font(size=12)

    countdown_var = tk.StringVar(value=f"{countdown_seconds}s")
    error_var = tk.StringVar(value="")
    _after_id = [None]
    _destroyed = [False]

    countdown_label = tk.Label(
        root, textvariable=countdown_var,
        bg="white", fg="#333333", font=label_font,
    )
    countdown_label.place(relx=1.0, x=-40, y=30, anchor="ne")

    content = tk.Frame(root, bg="white", padx=80, pady=60)
    content.pack(fill="both", expand=True)

    message_label = tk.Label(
        content,
        text=heckler_message or "Hey! Get back to work.",
        bg="white", fg="#111111", font=message_font,
        wraplength=wrap_width, justify="center",
    )
    message_label.pack(expand=True)

    bottom = tk.Frame(content, bg="white")
    bottom.pack(fill="x", pady=(20, 40))

    tk.Label(
        bottom,
        text=pledge_text or "I will stop procrastinating and focus on my work.",
        bg="white", fg="#111111", font=pledge_font,
        wraplength=wrap_width, justify="center",
    ).pack(pady=(0, 16))

    entry = tk.Text(
        bottom,
        font=("Arial", 16),
        width=80,
        height=5,
        relief="solid",
        bd=1,
        wrap="word",
    )
    entry.pack(ipady=12)

    tk.Label(
        bottom, textvariable=error_var,
        bg="white", fg="#c62828", font=error_font,
    ).pack(pady=(12, 0))

    def on_submit(event=None) -> str:
        expected = pledge_text or "I will stop procrastinating and focus on my work."
        typed = entry.get("1.0", tk.END).strip()
        if _levenshtein(typed, expected) <= 5:
            _destroyed[0] = True
            if _after_id[0] is not None:
                try:
                    root.after_cancel(_after_id[0])
                except Exception:
                    pass
            root.destroy()
            return "break"
        error_var.set(f"Close enough? Not quite. Try again. ({_levenshtein(typed, expected)} edits away)")
        entry.delete("1.0", tk.END)
        return "break"

    root.bind("<Return>", on_submit)
    root.bind("<Escape>", lambda e: "break")

    def tick() -> None:
        nonlocal countdown_seconds
        if _destroyed[0]:
            return
        try:
            if not root.winfo_exists():
                _destroyed[0] = True
                return
            if countdown_seconds > 0:
                countdown_seconds -= 1
                countdown_var.set(f"{countdown_seconds}s")
                _after_id[0] = root.after(1000, tick)
            else:
                countdown_var.set("0s")
        except Exception:
            _destroyed[0] = True

    _after_id[0] = root.after(1000, tick)
    root.after(100, entry.focus_force)
    root.lift()
    root.mainloop()
