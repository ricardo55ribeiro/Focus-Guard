import base64
import os
import subprocess
import threading

import pystray
import PIL.Image
import PIL.ImageDraw

import logger


_tray_icon = None
_current_category = "neutral"
_show_window_callback = None
_tray_starting = False
_tray_background_mode = False
_tray_lock = threading.RLock()
_MAX_TRAY_TITLE_LENGTH = 127


def _make_icon(color: str) -> PIL.Image.Image:
    size = 256
    image = PIL.Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(image)
    margin = 20
    draw.ellipse((margin, margin, size - margin, size - margin), fill=color)
    return image.resize((64, 64), PIL.Image.Resampling.LANCZOS)


def _make_title(study_goal: str) -> str:
    if not study_goal:
        return "FocusGuard"

    title = f"FocusGuard - {study_goal}"
    if len(title) <= _MAX_TRAY_TITLE_LENGTH:
        return title
    return title[: _MAX_TRAY_TITLE_LENGTH - 3].rstrip() + "..."


def update_tray(category: str) -> None:
    global _current_category

    with _tray_lock:
        icon = _tray_icon
        background_mode = _tray_background_mode

    if background_mode:
        category = "neutral"

    _current_category = category
    if icon is not None:
        try:
            icon.icon = _make_icon(
                "#4caf50" if category != "distracted" else "#f44336"
            )
        except Exception:
            pass


def _on_stop(icon, item) -> None:
    icon.stop()
    logger.save_and_summarize()
    os._exit(0)


def _on_quit_background(icon, item) -> None:
    icon.stop()
    os._exit(0)


def _on_summary(icon, item) -> None:
    logger.save_and_summarize()


def _on_tray_click(icon, item) -> None:
    if _show_window_callback is not None:
        try:
            _show_window_callback()
        except Exception:
            pass


def _is_icon_alive(icon) -> bool:
    return bool(getattr(icon, "visible", False))


def _run_tray_icon(icon) -> None:
    def setup(running_icon) -> None:
        global _tray_starting

        try:
            running_icon.visible = True
            logger.log_debug("[TRAY] Tray icon is visible.")
        except Exception as exc:
            logger.log_debug(f"[TRAY] Failed to show tray icon: {exc!r}")
        finally:
            with _tray_lock:
                if _tray_icon is running_icon:
                    _tray_starting = False

    try:
        icon.run(setup)
    except Exception as exc:
        logger.log_debug(f"[TRAY] Tray icon thread failed: {exc!r}")
    finally:
        global _tray_icon, _tray_starting
        with _tray_lock:
            if _tray_icon is icon:
                _tray_icon = None
                _tray_starting = False
                logger.log_debug("[TRAY] Tray icon stopped; state cleared.")


def start_tray(study_goal: str, on_show_window=None, background_mode: bool = False) -> None:
    global _tray_icon, _show_window_callback, _tray_starting, _tray_background_mode

    stale_icon = None
    with _tray_lock:
        if on_show_window is not None:
            _show_window_callback = on_show_window

        if _tray_icon is not None:
            if (_tray_starting or _is_icon_alive(_tray_icon)) and _tray_background_mode == background_mode:
                try:
                    _tray_icon.title = _make_title(study_goal)
                except Exception:
                    pass
                logger.log_debug("[TRAY] Reusing existing tray icon.")
                return

            stale_icon = _tray_icon
            _tray_icon = None
            _tray_starting = False
            logger.log_debug("[TRAY] Existing tray icon was stale; recreating.")

    if stale_icon is not None:
        try:
            stale_icon.stop()
        except Exception:
            pass

    if background_mode:
        menu = pystray.Menu(
            pystray.MenuItem("Open FocusGuard", _on_tray_click, default=True),
            pystray.MenuItem("Quit FocusGuard", _on_quit_background),
        )
    else:
        menu = pystray.Menu(
            pystray.MenuItem("Show Window", _on_tray_click, default=True),
            pystray.MenuItem("Stop Session", _on_stop),
            pystray.MenuItem("View Summary", _on_summary),
        )

    icon = pystray.Icon(
        "FocusGuard",
        _make_icon("#4caf50"),
        title=_make_title(study_goal),
        menu=menu,
    )
    with _tray_lock:
        _tray_icon = icon
        _tray_starting = True
        _tray_background_mode = bool(background_mode)
    logger.log_debug("[TRAY] Starting tray icon.")
    threading.Thread(target=_run_tray_icon, args=(icon,), daemon=True).start()


def stop_tray() -> None:
    global _tray_icon, _current_category, _show_window_callback, _tray_starting, _tray_background_mode

    with _tray_lock:
        icon = _tray_icon
        _tray_icon = None
        _tray_starting = False
        _tray_background_mode = False
        _current_category = "neutral"
        _show_window_callback = None

    if icon is None:
        return

    try:
        icon.stop()
        logger.log_debug("[TRAY] Tray icon stop requested.")
    except Exception:
        pass


def show_notification(title: str, message: str) -> None:
    def _xml_esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;")
        )

    t = _xml_esc(title)
    m = _xml_esc(message)

    ps = "\n".join([
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null",
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null",
        "$doc = [Windows.Data.Xml.Dom.XmlDocument]::new()",
        f"$doc.LoadXml('<toast><visual><binding template=\"ToastText02\"><text id=\"1\">{t}</text><text id=\"2\">{m}</text></binding></visual></toast>')",
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($doc)",
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('FocusGuard.App.1').Show($toast)",
    ])

    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        subprocess.Popen(
            [
                "powershell",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-EncodedCommand", encoded,
            ],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        logger.log_debug(f"[NOTIFICATION] Failed to show toast: {exc}")
