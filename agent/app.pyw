import ctypes


def _set_process_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _set_app_user_model_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FocusGuard.App.1")
    except Exception:
        pass


def _register_for_notifications() -> None:
    try:
        import winreg
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Classes\AppUserModelId\FocusGuard.App.1",
        ) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "FocusGuard")
    except Exception:
        pass


_set_process_dpi_awareness()
_set_app_user_model_id()
_register_for_notifications()

import signal
import sys
from pathlib import Path
import tkinter as tk

from ui import FocusGuardApp


def _maximize_startup_window(root: tk.Tk) -> None:
    def maximize() -> None:
        try:
            root.state("zoomed")
        except tk.TclError:
            pass

    root.update_idletasks()
    try:
        root.deiconify()
    except tk.TclError:
        pass

    maximize()
    try:
        root.after_idle(maximize)
    except tk.TclError:
        pass


if __name__ == "__main__":
    import single_instance

    _show_cb = [None]
    if not single_instance.try_acquire(lambda: _show_cb[0] and _show_cb[0]()):
        sys.exit(0)

    root = tk.Tk()
    try:
        icon_path = Path(__file__).resolve().parent / "icon.ico"
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
    except Exception:
        pass

    background_mode = "--background" in sys.argv[1:]
    app = FocusGuardApp(root, background_mode=background_mode)
    _show_cb[0] = app._show_and_focus
    if not background_mode:
        _maximize_startup_window(root)

    def _handle_sigint(*args):
        app.on_close()
        try:
            single_instance.release()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_close()
        try:
            single_instance.release()
        except Exception:
            pass
