from typing import Dict

try:
    import psutil
    import win32gui
    import win32process
except Exception:
    psutil = None
    win32gui = None
    win32process = None


def get_active_window() -> Dict[str, str]:
    result = {"process_name": "", "window_title": ""}

    if psutil is None or win32gui is None or win32process is None:
        return result

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return result

        try:
            window_title = win32gui.GetWindowText(hwnd) or ""
        except Exception:
            window_title = ""

        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(process_id).name().lower()
        except Exception:
            process_name = ""

        return {
            "process_name": process_name,
            "window_title": window_title,
        }
    except Exception:
        return result
