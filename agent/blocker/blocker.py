import threading

import psutil
import win32con
import win32gui

from blocker.popup import show_pledge_popup
from capture.browser import clear_block_action, set_block_action
from classifier.ai import generate_heckler, generate_pledge

BROWSER_PROCESSES = {
    "firefox.exe",
    "chrome.exe",
    "brave.exe",
    "msedge.exe",
}

_block_lock = threading.Lock()
_block_in_progress = False
_state_lock = threading.Lock()


def is_blocking() -> bool:
    with _state_lock:
        return _block_in_progress


def minimize_active_window() -> None:
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception:
        pass


def trigger_block(
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
    study_goal: str,
) -> None:
    global _block_in_progress

    if not _block_lock.acquire(blocking=False):
        return

    with _state_lock:
        _block_in_progress = True

    try:
        normalized = (process_name or "").strip().lower()
        is_browser = normalized in BROWSER_PROCESSES

        heckler_message = generate_heckler(study_goal, normalized, window_title, url, page_title)
        pledge_text = generate_pledge(study_goal, normalized, window_title, url, page_title)

        if is_browser:
            set_block_action(reason=page_title or window_title)

        show_pledge_popup(heckler_message, pledge_text)

        clear_block_action()

        if not is_browser:
            minimize_active_window()

    finally:
        with _state_lock:
            _block_in_progress = False
        _block_lock.release()