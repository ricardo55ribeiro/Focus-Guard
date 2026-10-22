import json
import queue
import threading
import time
import tkinter as tk
from collections import Counter
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext
from typing import Any, Dict, List, Optional

import autostart
import logger
import monitor
from tray import show_notification, stop_tray
from blocker.popup import show_pledge_popup
from classifier import rules as _rules


SETTINGS_PATH = Path(__file__).resolve().parent / "config" / "settings.json"
LOGS_DIR = Path(__file__).resolve().parent / "logs"

BG = "#1a1a1a"
PANEL_BG = "#242424"
TEXT = "#ffffff"
MUTED = "#9e9e9e"
GREEN = "#4caf50"
RED = "#f44336"
YELLOW = "#ffc107"
BUTTON_GREY = "#3a3a3a"
ENTRY_BG = "#111111"


def _format_history_duration(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def _format_history_date(value: datetime) -> str:
    return f"{value.strftime('%b')} {value.day}, {value.year} {value.strftime('%H:%M')}"


def _parse_session_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as session_file:
            events = json.load(session_file)

        if not isinstance(events, list):
            return None
        if not all(isinstance(event, dict) for event in events):
            return None

        if events:
            session_datetime = datetime.fromisoformat(str(events[0].get("timestamp", "")))
        else:
            timestamp_text = path.stem.replace("session_", "", 1)
            session_datetime = datetime.strptime(timestamp_text, "%Y-%m-%d_%H-%M")

        if len(events) > 1:
            first_timestamp = datetime.fromisoformat(str(events[0].get("timestamp", "")))
            last_timestamp = datetime.fromisoformat(str(events[-1].get("timestamp", "")))
            duration_seconds = max(0, int((last_timestamp - first_timestamp).total_seconds()))
        else:
            duration_seconds = 0

        total_checks = len(events)
        category_counts = Counter(str(event.get("category", "")) for event in events)
        productive_urls = Counter(
            str(event.get("url", ""))
            for event in events
            if event.get("category") == "productive" and event.get("url")
        )

        def pct(category: str) -> float:
            return (category_counts.get(category, 0) / total_checks * 100) if total_checks else 0.0

        return {
            "filename": path.name,
            "date": _format_history_date(session_datetime),
            "duration_seconds": duration_seconds,
            "duration_str": _format_history_duration(duration_seconds),
            "total_checks": total_checks,
            "productive_pct": pct("productive"),
            "neutral_pct": pct("neutral"),
            "distracted_pct": pct("distracted"),
            "blocks_triggered": sum(1 for event in events if event.get("blocked")),
            "top_urls": [url for url, _count in productive_urls.most_common(3)],
            "events": events,
        }
    except Exception:
        return None


class FocusGuardApp:
    def __init__(self, root: tk.Tk, background_mode: bool = False) -> None:
        self.root = root
        self.root.title("FocusGuard")
        self.root.resizable(True, True)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.background_mode = background_mode
        self.status_queue: Optional[queue.Queue] = None
        self.stop_event: Optional[threading.Event] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.background_stop_event: Optional[threading.Event] = None
        self.background_monitor_thread: Optional[threading.Thread] = None
        self.session_started_at = 0.0
        self.running = False
        self.goal_placeholder_active = True
        self.log_entries: List[Dict[str, str]] = []

        self.timer_var = tk.StringVar(value="00:00:00")
        self.status_var = tk.StringVar(value="Focused")
        self.process_var = tk.StringVar(value="Process: waiting for first check")
        self.page_var = tk.StringVar(value="Page: waiting for first check")
        self.error_var = tk.StringVar(value="")

        self.status_canvas: Optional[tk.Canvas] = None
        self.status_circle: Optional[int] = None
        self.log_box: Optional[scrolledtext.ScrolledText] = None
        self.stop_button: Optional[tk.Button] = None
        self.startup_label: Optional[tk.Label] = None

        self.show_setup_screen()
        if self.background_mode:
            self._start_background_mode()

    def _maximize_window(self, win: tk.Wm) -> None:
        try:
            win.update_idletasks()
            win.state("zoomed")
        except Exception:
            pass

    def _show_main_window(self) -> None:
        try:
            self.root.deiconify()
            self._maximize_window(self.root)
            self.root.lift()
            self.root.focus_force()
            self.root.after_idle(lambda: self._maximize_window(self.root))
        except Exception:
            pass

    def _show_and_focus(self) -> None:
        """Called when a second instance signals us to show the window."""
        try:
            self.root.after(0, self._show_main_window)
        except Exception:
            pass

    def _request_show_main_window(self) -> None:
        try:
            self.root.after(0, self._show_main_window)
        except Exception:
            pass

    def _queue_show_main_window(self) -> None:
        try:
            if self.status_queue is not None:
                self.status_queue.put({"action": "show_window"})
                return
        except Exception:
            pass
        self._request_show_main_window()

    def _hide_main_window(self) -> None:
        try:
            self.root.update_idletasks()
            self.root.withdraw()
        except Exception:
            pass

    def _background_monitor_is_alive(self) -> bool:
        return (
            self.background_monitor_thread is not None
            and self.background_monitor_thread.is_alive()
        )

    def _start_background_mode(self) -> None:
        self._hide_main_window()

        import tray as _tray_module

        _tray_module.start_tray(
            "",
            on_show_window=self._request_show_main_window,
            background_mode=True,
        )

        if self._background_monitor_is_alive():
            return

        self.background_stop_event = threading.Event()
        self.background_monitor_thread = threading.Thread(
            target=monitor.run_monitor,
            args=(None, None, self.background_stop_event),
            kwargs={"background_mode": True},
            name="focusguard-background-monitor",
            daemon=True,
        )
        self.background_monitor_thread.start()

    def _stop_background_mode(self, *, stop_tray_icon: bool = False) -> None:
        if self.background_stop_event is not None:
            self.background_stop_event.set()

        if self.background_monitor_thread is not None:
            self.background_monitor_thread.join(timeout=3)

        self.background_stop_event = None
        self.background_monitor_thread = None

        if stop_tray_icon:
            stop_tray()

    def clear_screen(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def make_label(
        self,
        parent: tk.Widget,
        text: str = "",
        *,
        textvariable: Optional[tk.StringVar] = None,
        size: int = 11,
        weight: str = "normal",
        fg: str = TEXT,
        bg: str = BG,
    ) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            textvariable=textvariable,
            bg=bg,
            fg=fg,
            font=("Segoe UI", size, weight),
        )

    def make_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        bg: str,
        fg: str = TEXT,
        width: int = 18,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
            bd=0,
            relief="flat",
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 11, "bold"),
            width=width,
            padx=12,
            pady=10,
        )

    def show_setup_screen(self, _show: bool = True) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.running = False
        self.clear_screen()
        self.root.configure(bg=BG)
        self.error_var.set("")

        container = tk.Frame(self.root, bg=BG, padx=48, pady=16)
        container.pack(fill="both", expand=True)

        self.make_label(container, "FocusGuard", size=24, weight="bold").pack(pady=(8, 4))
        self.make_label(
            container,
            "Stay focused. Get things done.",
            size=11,
            fg=MUTED,
        ).pack(pady=(0, 16))

        form = tk.Frame(container, bg=BG)
        form.pack(fill="x")

        self.make_label(
            form,
            "What is your study goal for this session?",
            size=11,
            fg=TEXT,
        ).pack(anchor="w", pady=(0, 8))

        self.goal_text = tk.Text(
            form,
            height=3,
            bg=ENTRY_BG,
            fg=MUTED,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#333333",
            highlightcolor=GREEN,
            font=("Segoe UI", 11),
            wrap="word",
            padx=10,
            pady=8,
        )
        self.goal_text.pack(fill="x")
        self.goal_placeholder_active = True
        self.goal_text.configure(fg=MUTED)
        self.goal_text.delete("1.0", tk.END)
        self.goal_text.insert("1.0", "e.g. Learn pointers in C")
        self.goal_text.bind("<FocusIn>", self.clear_goal_placeholder)
        self.goal_text.bind("<FocusOut>", self.restore_goal_placeholder)

        self.make_label(
            form,
            textvariable=self.error_var,
            size=10,
            fg=RED,
        ).pack(anchor="w", pady=(8, 0))

        buttons = tk.Frame(container, bg=BG)
        buttons.pack(pady=(12, 0))

        self.make_button(
            buttons,
            "Start Session",
            self.handle_start_click,
            bg=GREEN,
            width=20,
        ).pack(pady=(0, 12))

        self.make_button(
            buttons,
            "Settings",
            self.show_settings_screen,
            bg=BUTTON_GREY,
            fg=TEXT,
            width=20,
        ).pack()

        self.make_button(
            buttons,
            "View History",
            self.show_history_screen,
            bg=BUTTON_GREY,
            fg=TEXT,
            width=20,
        ).pack(pady=(8, 0))

        bottom = tk.Frame(container, bg=BG)
        bottom.pack(side="bottom", fill="x")
        self.make_label(
            bottom,
            "Session logs saved to agent/logs/",
            size=9,
            fg=MUTED,
        ).pack(pady=(0, 4))

        self.root.update_idletasks()
        if _show:
            self._maximize_window(self.root)

    def clear_goal_placeholder(self, _event=None) -> None:
        if self.goal_placeholder_active:
            self.goal_text.delete("1.0", tk.END)
            self.goal_text.configure(fg=TEXT)
            self.goal_placeholder_active = False

    def restore_goal_placeholder(self, _event=None) -> None:
        if not self.goal_text.get("1.0", tk.END).strip():
            self.goal_text.configure(fg=MUTED)
            self.goal_text.delete("1.0", tk.END)
            self.goal_text.insert("1.0", "e.g. Learn pointers in C")
            self.goal_placeholder_active = True

    def handle_start_click(self) -> None:
        study_goal = self.goal_text.get("1.0", tk.END).strip()
        if self.goal_placeholder_active:
            study_goal = ""

        if not study_goal:
            self.error_var.set("Please enter a study goal before starting.")
            return

        self.start_session(study_goal)

    def show_running_screen(self) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.clear_screen()
        self.root.configure(bg=BG)
        self.log_entries = []

        container = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=BG)
        header.pack(fill="x")
        self.make_label(header, "FocusGuard", size=18, weight="bold").pack(side="left")
        self.make_label(
            header,
            textvariable=self.timer_var,
            size=12,
            weight="bold",
            fg=MUTED,
        ).pack(side="right")

        self.startup_label = self.make_label(
            container,
            "Starting up — please wait...",
            size=9,
            fg=MUTED,
        )
        self.startup_label.pack(anchor="w", pady=(0, 4))

        center = tk.Frame(container, bg=BG)
        center.pack(fill="x", pady=(28, 12))

        self.status_canvas = tk.Canvas(
            center,
            width=80,
            height=80,
            bg=BG,
            highlightthickness=0,
        )
        self.status_canvas.pack()
        self.status_circle = self.status_canvas.create_oval(
            10,
            10,
            70,
            70,
            fill=GREEN,
            outline=GREEN,
        )
        self.make_label(
            center,
            textvariable=self.status_var,
            size=16,
            weight="bold",
        ).pack(pady=(10, 0))

        details = tk.Frame(container, bg=BG)
        details.pack(fill="x", pady=(4, 14))
        self.make_label(
            details,
            textvariable=self.process_var,
            size=9,
            fg=MUTED,
        ).pack(anchor="w")
        self.make_label(
            details,
            textvariable=self.page_var,
            size=9,
            fg=MUTED,
        ).pack(anchor="w", pady=(3, 0))

        self.log_box = scrolledtext.ScrolledText(
            container,
            height=9,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#333333",
            font=("Consolas", 10),
            wrap="word",
            state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("productive", foreground=GREEN)
        self.log_box.tag_config("neutral", foreground=YELLOW)
        self.log_box.tag_config("distracted", foreground=RED)
        self.log_box.vbar.configure(
            bg=BUTTON_GREY,
            troughcolor=BG,
            activebackground=GREEN,
            relief="flat",
        )

        self.stop_button = self.make_button(
            container,
            "Stop Session",
            self.stop_session,
            bg=RED,
            width=20,
        )
        self.stop_button.pack(pady=(18, 0))

        self.root.update_idletasks()
        self._maximize_window(self.root)

    def show_history_screen(self) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.clear_screen()
        self.root.configure(bg=BG)

        container = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=BG)
        header.pack(fill="x", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)

        self.make_button(
            header,
            "← Back",
            self.show_setup_screen,
            bg=BUTTON_GREY,
            fg=TEXT,
            width=10,
        ).grid(row=0, column=0, sticky="w")
        self.make_label(header, "Session History", size=18, weight="bold").grid(
            row=0,
            column=1,
        )
        tk.Frame(header, bg=BG).grid(row=0, column=2, sticky="e")

        sessions = []
        try:
            for session_path in LOGS_DIR.glob("*.json"):
                session_data = _parse_session_file(session_path)
                if session_data is not None:
                    sessions.append(session_data)
            sessions.sort(key=lambda session: session["filename"], reverse=True)
        except Exception:
            sessions = []

        if not sessions:
            empty = tk.Frame(container, bg=BG)
            empty.pack(fill="both", expand=True)
            self.make_label(
                empty,
                "No sessions recorded yet.",
                size=11,
                fg=MUTED,
            ).pack(expand=True)
            self.root.update_idletasks()
            self._maximize_window(self.root)
            return

        outer = tk.Frame(container, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        def bind_session_click(widget: tk.Widget, session_data: dict) -> None:
            widget.bind(
                "<Button-1>",
                lambda _event, data=session_data: self.show_session_detail(data),
            )
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass
            for child in widget.winfo_children():
                bind_session_click(child, session_data)

        for session in sessions:
            focused_pct = min(
                100.0,
                float(session["productive_pct"]) + float(session["neutral_pct"]),
            )

            card = tk.Frame(
                inner,
                bg=PANEL_BG,
                padx=14,
                pady=12,
                highlightthickness=1,
                highlightbackground="#333333",
                highlightcolor="#333333",
            )
            card.pack(fill="x", pady=(0, 10), padx=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            card.grid_columnconfigure(1, weight=0)

            left = tk.Frame(card, bg=PANEL_BG)
            left.grid(row=0, column=0, sticky="w")
            self.make_label(
                left,
                session["date"],
                size=12,
                weight="bold",
                bg=PANEL_BG,
            ).pack(anchor="w")
            self.make_label(
                left,
                f"Duration {session['duration_str']}",
                size=10,
                fg=MUTED,
                bg=PANEL_BG,
            ).pack(anchor="w", pady=(4, 0))

            right = tk.Frame(card, bg=PANEL_BG)
            right.grid(row=0, column=1, sticky="e")

            for label_text, color in (
                (f"●  {focused_pct:.0f}% focused", GREEN),
                (f"●  {float(session['distracted_pct']):.0f}% distracted", RED),
                (f"🚫 {int(session['blocks_triggered'])} blocks", "#ff9800"),
            ):
                tk.Label(
                    right,
                    text=label_text,
                    bg=color,
                    fg=TEXT,
                    font=("Segoe UI", 9, "bold"),
                    padx=8,
                    pady=3,
                ).pack(side="left", padx=(8, 0))

            bind_session_click(card, session)

        self.root.update_idletasks()
        self._maximize_window(self.root)

    def show_session_detail(self, session: dict) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.clear_screen()
        self.root.configure(bg=BG)

        container = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=BG)
        header.pack(fill="x", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)

        self.make_button(
            header,
            "← Back",
            self.show_history_screen,
            bg=BUTTON_GREY,
            fg=TEXT,
            width=10,
        ).grid(row=0, column=0, sticky="w")
        self.make_label(header, str(session.get("date", "")), size=16, weight="bold").grid(
            row=0,
            column=1,
        )
        tk.Frame(header, bg=BG).grid(row=0, column=2, sticky="e")

        focused_pct = min(
            100.0,
            float(session.get("productive_pct", 0.0)) + float(session.get("neutral_pct", 0.0)),
        )

        stats_bar = tk.Frame(
            container,
            bg=PANEL_BG,
            padx=10,
            pady=10,
            highlightthickness=1,
            highlightbackground="#333333",
            highlightcolor="#333333",
        )
        stats_bar.pack(fill="x")

        for column in range(4):
            stats_bar.grid_columnconfigure(column, weight=1, uniform="history_stats")

        stat_items = (
            ("⏱ Duration: ", str(session.get("duration_str", "00:00:00"))),
            ("✅ Focused: ", f"{focused_pct:.0f}%"),
            ("❌ Distracted: ", f"{float(session.get('distracted_pct', 0.0)):.0f}%"),
            ("🚫 Blocks: ", str(session.get("blocks_triggered", 0))),
        )
        for column, (label_text, value_text) in enumerate(stat_items):
            stat = tk.Frame(stats_bar, bg=PANEL_BG)
            stat.grid(row=0, column=column, sticky="ew")
            stat_line = tk.Frame(stat, bg=PANEL_BG)
            stat_line.pack(anchor="center")
            self.make_label(
                stat_line,
                label_text,
                size=10,
                fg=MUTED,
                bg=PANEL_BG,
            ).pack(side="left")
            self.make_label(
                stat_line,
                value_text,
                size=10,
                weight="bold",
                fg=TEXT,
                bg=PANEL_BG,
            ).pack(side="left")

        top_urls = tk.Frame(container, bg=BG)
        top_urls.pack(fill="x", pady=(14, 0))
        self.make_label(
            top_urls,
            "TOP PRODUCTIVE URLS",
            size=9,
            fg=MUTED,
        ).pack(anchor="w")

        urls = session.get("top_urls", [])
        if urls:
            for url in urls[:3]:
                url_text = str(url)
                if len(url_text) > 60:
                    url_text = url_text[:57] + "..."
                self.make_label(
                    top_urls,
                    url_text,
                    size=9,
                    fg=GREEN,
                ).pack(anchor="w", pady=(4, 0))
        else:
            self.make_label(
                top_urls,
                "None",
                size=9,
                fg=MUTED,
            ).pack(anchor="w", pady=(4, 0))

        tk.Frame(container, bg="#333333", height=1).pack(fill="x", pady=(8, 8))

        event_log = scrolledtext.ScrolledText(
            container,
            height=14,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#333333",
            font=("Consolas", 10),
            wrap="word",
            state="normal",
        )
        event_log.pack(fill="both", expand=True)
        event_log.tag_config("productive", foreground=GREEN)
        event_log.tag_config("neutral", foreground=YELLOW)
        event_log.tag_config("distracted", foreground=RED)
        event_log.vbar.configure(
            bg=BUTTON_GREY,
            troughcolor=BG,
            activebackground=GREEN,
            relief="flat",
        )

        for event in session.get("events", []):
            if not isinstance(event, dict):
                continue

            timestamp = str(event.get("timestamp", ""))
            try:
                timestamp_text = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
            except Exception:
                if "T" in timestamp:
                    timestamp_text = timestamp.split("T", 1)[1][:8]
                else:
                    timestamp_text = "--:--:--"

            category = str(event.get("category", "neutral"))
            if category not in ("productive", "neutral", "distracted"):
                category = "neutral"

            score = str(event.get("score", ""))
            title_for_log = (
                str(event.get("page_title", "") or "")
                or str(event.get("url", "") or "")
                or str(event.get("process_name", "") or "")
                or "Unknown"
            )
            reason = str(event.get("reason", "") or "")
            line = f"[{timestamp_text}] score={score} | {title_for_log} | {reason}"
            event_log.insert(tk.END, line + "\n", category)

        event_log.see(tk.END)
        event_log.configure(state="disabled")

        self.root.update_idletasks()
        self._maximize_window(self.root)

    def start_session(self, study_goal: str) -> None:
        if self._background_monitor_is_alive():
            self._stop_background_mode(stop_tray_icon=True)

        self.status_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.session_started_at = time.time()
        self.running = True
        self.timer_var.set("00:00:00")
        self.status_var.set("Focused")
        self.process_var.set("Process: waiting for first check")
        self.page_var.set("Page: waiting for first check")

        self.show_running_screen()

        import tray as _tray_module
        _tray_module.start_tray(
            study_goal,
            on_show_window=self._queue_show_main_window,
            background_mode=False,
        )

        self.monitor_thread = threading.Thread(
            target=monitor.run_monitor,
            args=(study_goal, self.status_queue, self.stop_event),
            name="focusguard-monitor",
            daemon=True,
        )
        self.monitor_thread.start()

        self.poll_queue()
        self.update_timer()

    def poll_queue(self) -> None:
        if not self.running:
            return
        sq = self.status_queue
        if sq is None:
            return
        try:
            while True:
                payload = sq.get_nowait()
                if payload.get("action") == "show_window":
                    self._show_main_window()
                elif payload.get("action") == "session_ready":
                    self._on_session_ready()
                elif payload.get("action") == "show_popup":
                    self.handle_popup_action(payload)
                else:
                    self.apply_status_update(payload)
        except queue.Empty:
            pass
        if self.running and self.status_queue is not None:
            self.root.after(500, self.poll_queue)

    def _on_session_ready(self) -> None:
        try:
            if self.startup_label is not None:
                self.startup_label.destroy()
                self.startup_label = None
        except Exception:
            pass
        self._hide_main_window()

    def handle_popup_action(self, payload: Dict[str, Any]) -> None:
        done_event = payload.get("done_event")
        was_visible = True
        try:
            was_visible = self.root.state() != "withdrawn"
        except Exception:
            pass
        try:
            self._hide_main_window()
            show_pledge_popup(
                payload.get("heckler", ""),
                payload.get("pledge", ""),
            )
        finally:
            if was_visible:
                self._show_main_window()
            if isinstance(done_event, threading.Event):
                done_event.set()

    def apply_status_update(self, payload: Dict[str, Any]) -> None:
        category = str(payload.get("category", "neutral"))
        process_name = str(payload.get("process_name", "") or "unknown")
        url = str(payload.get("url", "") or "")
        page_title = str(payload.get("page_title", "") or "")
        score = str(payload.get("score", ""))
        reason = str(payload.get("reason", "") or "")
        timestamp = str(payload.get("timestamp", ""))

        focused = category in ("productive", "neutral")
        color = GREEN if focused else RED
        status = "Focused" if focused else "Distracted"

        self.status_var.set(status)
        if self.status_canvas is not None and self.status_circle is not None:
            self.status_canvas.itemconfig(self.status_circle, fill=color, outline=color)

        self.process_var.set(f"Process: {process_name}")
        self.page_var.set(f"Page: {url or page_title or 'n/a'}")

        title_for_log = page_title or url or process_name or "Unknown"
        line = f"[{timestamp}] score={score} | {title_for_log} | {reason}"
        self.log_entries.append({"category": category, "line": line})
        self.log_entries = self.log_entries[-20:]
        self.redraw_log()

    def redraw_log(self) -> None:
        if self.log_box is None:
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        for entry in self.log_entries:
            self.log_box.insert(tk.END, entry["line"] + "\n", entry["category"])
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def update_timer(self) -> None:
        if not self.running:
            return
        try:
            if not self.root.winfo_exists():
                return
            elapsed = int(time.time() - self.session_started_at)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            self.timer_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            self.root.after(1000, self.update_timer)
        except tk.TclError:
            pass

    def stop_session(self) -> None:
        if self.stop_button is not None:
            self.stop_button.configure(text="Stopping...", state="disabled")
        self.root.update_idletasks()
        self._maximize_window(self.root)

        if self.stop_event is not None:
            self.stop_event.set()

        if self.monitor_thread is not None:
            self.monitor_thread.join(timeout=3)

        self.running = False
        self.status_queue = None
        self.stop_event = None
        self.monitor_thread = None
        stop_tray()
        import ollama_manager

        ollama_manager.shutdown_if_started()

        if self.background_mode:
            self.root.withdraw()
            self.show_setup_screen(_show=False)
            self._start_background_mode()
        else:
            self._show_main_window()
            self.show_setup_screen()

    def show_settings_screen(self) -> None:
        try:
            self.root.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.clear_screen()
        self.root.configure(bg=BG)

        settings = self.load_settings()
        widgets = {}

        container = tk.Frame(self.root, bg=BG, padx=28, pady=22)
        container.pack(fill="both", expand=True)

        def write_settings() -> None:
            autostart.set_autostart(bool(widgets["autostart"].get()))
            settings["session_check_interval_seconds"] = int(widgets["interval"].get())
            settings["background_check_interval_seconds"] = int(
                widgets["background_check_interval_seconds"].get()
            )
            settings["warning_duration_seconds"] = int(widgets["countdown"].get())
            settings["background_instructions"] = self.text_lines(
                widgets["background_instructions"]
            )
            settings["always_block_domains"] = self.text_lines(widgets["block_domains"])
            settings["always_allow_domains"] = self.text_lines(widgets["allow_domains"])
            settings["always_block_processes"] = self.text_lines(widgets["block_processes"])

            with SETTINGS_PATH.open("w", encoding="utf-8") as settings_file:
                json.dump(settings, settings_file, indent=2)
                settings_file.write("\n")

            try:
                _rules.SETTINGS = _rules._load_settings()
            except Exception:
                pass

        def save_settings() -> None:
            write_settings()
            self.show_setup_screen()

        def start_or_restart_background_mode() -> None:
            write_settings()

            if self._background_monitor_is_alive():
                self._stop_background_mode(stop_tray_icon=True)

            self.root.withdraw()
            self.show_setup_screen(_show=False)
            self.background_mode = True
            self._start_background_mode()

        header = tk.Frame(container, bg=BG)
        header.pack(fill="x", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)
        header.grid_columnconfigure(2, weight=1)

        self.make_button(
            header,
            "← Back",
            self.show_setup_screen,
            bg=BUTTON_GREY,
            fg=TEXT,
            width=10,
        ).grid(row=0, column=0, sticky="w")
        self.make_label(header, "Settings", size=18, weight="bold").grid(
            row=0,
            column=1,
        )
        self.make_button(
            header,
            "Save",
            save_settings,
            bg=GREEN,
            fg=TEXT,
            width=10,
        ).grid(row=0, column=2, sticky="e")

        tk.Frame(container, bg="#333333", height=1).pack(fill="x", pady=(0, 12))

        outer = tk.Frame(container, bg=BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        def make_auto_text_field(parent: tk.Widget, label: str, values: list, min_height: int) -> tk.Text:
            if isinstance(values, str):
                values = [values] if values.strip() else []

            frame = tk.Frame(parent, bg=BG)
            frame.pack(fill="x", pady=(0, 10))
            self.make_label(frame, label, size=10, fg=MUTED).pack(anchor="w", pady=(0, 4))

            line_count = max(min_height, len(values) + 1)

            text_widget = tk.Text(
                frame,
                height=line_count,
                bg=ENTRY_BG,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground="#333333",
                highlightcolor=GREEN,
                font=("Consolas", 10),
                wrap="none",
                padx=8,
                pady=6,
            )
            text_widget.pack(fill="x")

            if values:
                text_widget.insert("1.0", "\n".join(str(v) for v in values))

            def on_key_release(_event=None):
                current_lines = int(text_widget.index("end-1c").split(".")[0])
                new_height = max(min_height, current_lines + 1)
                text_widget.configure(height=new_height)

            text_widget.bind("<KeyRelease>", on_key_release)
            return text_widget

        widgets["autostart"] = tk.BooleanVar(value=autostart.get_autostart())
        autostart_frame = tk.Frame(inner, bg=BG)
        autostart_frame.pack(fill="x", pady=(0, 10))
        tk.Checkbutton(
            autostart_frame,
            text="Launch FocusGuard on Windows startup",
            variable=widgets["autostart"],
            bg=BG,
            fg=TEXT,
            selectcolor=ENTRY_BG,
            activebackground=BG,
            activeforeground=TEXT,
            font=("Segoe UI", 10),
            anchor="w",
            cursor="hand2",
        ).pack(anchor="w")

        widgets["background_instructions"] = make_auto_text_field(
            inner,
            "Background mode rules (one per line)",
            settings.get("background_instructions", []),
            4,
        )
        background_mode_button_label = (
            "Restart Background Mode"
            if self.background_mode and self._background_monitor_is_alive()
            else "Start Background Mode"
        )
        background_mode_button_bg = BUTTON_GREY if self.running else GREEN
        background_mode_button_state = tk.DISABLED if self.running else tk.NORMAL
        background_mode_button_frame = tk.Frame(inner, bg=BG)
        background_mode_button_frame.pack(fill="x", pady=(0, 10))
        tk.Button(
            background_mode_button_frame,
            text=background_mode_button_label,
            command=start_or_restart_background_mode,
            bg=background_mode_button_bg,
            fg=TEXT,
            activebackground=background_mode_button_bg,
            activeforeground=TEXT,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=6,
            bd=0,
            relief="flat",
            cursor="hand2",
            state=background_mode_button_state,
        ).pack(anchor="w")
        widgets["interval"] = self.make_spinbox(
            inner,
            "Check interval",
            settings.get("session_check_interval_seconds", 20),
            5,
            60,
            suffix="(seconds)",
        )
        widgets["background_check_interval_seconds"] = self.make_spinbox(
            inner,
            "Background check interval",
            settings.get("background_check_interval_seconds", 60),
            30,
            300,
            increment=10,
            suffix="(seconds)",
        )
        widgets["countdown"] = self.make_spinbox(
            inner,
            "Warning countdown (seconds)",
            settings.get("warning_duration_seconds", 15),
            5,
            60,
        )
        widgets["block_domains"] = make_auto_text_field(
            inner,
            "Always block domains",
            settings.get("always_block_domains", []),
            2,
        )
        widgets["allow_domains"] = make_auto_text_field(
            inner,
            "Always allow domains",
            settings.get("always_allow_domains", []),
            2,
        )
        widgets["block_processes"] = make_auto_text_field(
            inner,
            "Always block processes",
            settings.get("always_block_processes", []),
            2,
        )

        self.root.update_idletasks()
        self._maximize_window(self.root)

    def make_spinbox(
        self,
        parent: tk.Widget,
        label: str,
        value: Any,
        from_value: int,
        to_value: int,
        increment: int = 1,
        suffix: str = "",
    ) -> tk.Spinbox:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(0, 10))
        self.make_label(frame, label, size=10, fg=MUTED).pack(anchor="w", pady=(0, 4))

        input_row = tk.Frame(frame, bg=BG)
        input_row.pack(anchor="w")

        spinbox = tk.Spinbox(
            input_row,
            from_=from_value,
            to=to_value,
            increment=increment,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            buttonbackground=BUTTON_GREY,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#333333",
            font=("Segoe UI", 10),
            width=10,
        )
        spinbox.delete(0, tk.END)
        spinbox.insert(0, str(value))
        spinbox.pack(side="left")
        if suffix:
            self.make_label(input_row, suffix, size=10, fg=MUTED).pack(
                side="left",
                padx=(8, 0),
            )
        return spinbox

    def make_text_field(
        self,
        parent: tk.Widget,
        label: str,
        values: Any,
        height: int,
    ) -> tk.Text:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(0, 10))
        self.make_label(frame, label, size=10, fg=MUTED).pack(anchor="w", pady=(0, 4))

        text_widget = tk.Text(
            frame,
            height=height,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#333333",
            highlightcolor=GREEN,
            font=("Consolas", 10),
            wrap="none",
            padx=8,
            pady=6,
        )
        text_widget.pack(fill="x")

        if isinstance(values, list):
            text_widget.insert("1.0", "\n".join(str(value) for value in values))

        return text_widget

    def text_lines(self, text_widget: tk.Text) -> List[str]:
        return [
            line.strip()
            for line in text_widget.get("1.0", tk.END).splitlines()
            if line.strip()
        ]

    def load_settings(self) -> Dict[str, Any]:
        with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
            return json.load(settings_file)

    def on_close(self) -> None:
        if self.running:
            self._hide_main_window()
            return
        if self.background_mode:
            self._hide_main_window()
            return
        try:
            self.status_queue = None
            self._stop_background_mode(stop_tray_icon=False)
            stop_tray()
            import ollama_manager

            ollama_manager.shutdown_if_started()
        except Exception:
            pass
        finally:
            try:
                import single_instance
                single_instance.release()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass
