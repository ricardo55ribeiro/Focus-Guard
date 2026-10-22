import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))


@unittest.skipUnless(sys.platform == "win32", "Windows desktop integration")
class WindowsSmokeTests(unittest.TestCase):
    def test_desktop_screens_with_synthetic_settings_and_history(self):
        import tkinter as tk
        import ui
        import install
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            settings = directory / "settings.json"
            settings.write_text(json.dumps(install.DEFAULT_SETTINGS))
            logs = directory / "logs"
            logs.mkdir()
            with patch.object(ui, "SETTINGS_PATH", settings), patch.object(ui, "LOGS_DIR", logs), patch.object(ui.autostart, "get_autostart", return_value=False), patch.object(ui.FocusGuardApp, "_maximize_window"):
                app = ui.FocusGuardApp(root)
                app.show_settings_screen()
                app.show_history_screen()
                events = [{"timestamp": "2026-01-01T12:00:00", "category": "productive", "url": "https://example.org", "page_title": "Study", "score": 90, "reason": "test", "blocked": False}]
                session = logs / "session_2026-01-01_12-00.json"
                session.write_text(json.dumps(events))
                app.show_history_screen()
                app.show_session_detail(ui._parse_session_file(session))
                root.update_idletasks()
                self.assertTrue(root.winfo_exists())

    def test_idle_single_instance_client_does_not_disable_activation(self):
        import single_instance
        event = threading.Event()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with patch.object(single_instance, "LOCK_PORT", port):
            self.assertTrue(single_instance.try_acquire(event.set))
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=4):
                    time.sleep(2.2)
                    with socket.create_connection(("127.0.0.1", port), timeout=4) as active:
                        active.sendall(b"show")
                    self.assertTrue(event.wait(2))
            finally:
                single_instance.release()


if __name__ == "__main__":
    unittest.main()
