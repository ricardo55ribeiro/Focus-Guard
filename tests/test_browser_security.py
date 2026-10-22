"""Real loopback HTTP tests; never read or modify the user's settings."""
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from capture import browser
from classifier import rules


class BrowserServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), browser._Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / "settings.json"
        self.settings.write_text('{"always_allow_domains": [], "keep": true}')
        self.patch = patch.object(browser, "SETTINGS_PATH", self.settings)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.runtime = patch.object(rules, "SETTINGS", {"always_allow_domains": []})
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        browser.clear_block_action()
        with browser._data_lock:
            browser.latest_browser_data.update(url="", title="")

    def request(self, path="/", body=None, headers=None, method="POST"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        try:
            data = json.dumps(body if body is not None else {"url": "https://example.org", "title": "Study"})
            merged = {"Content-Type": "application/json"}
            merged.update(headers or {})
            conn.request(method, path, data, merged)
            response = conn.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            conn.close()

    def test_extension_requests_and_one_time_block_delivery(self):
        browser.set_block_action("Focus")
        status, body, headers = self.request(headers={"Origin": "moz-extension://test-id"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"action": "block", "reason": "Focus"})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(browser.get_browser_data()["title"], "Study")
        status, body, _ = self.request(headers={"Origin": "chrome-extension://test-id"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["action"], "none")

    def test_originless_extension_request_is_supported(self):
        self.assertEqual(self.request()[0], 200)

    def test_website_and_opaque_origins_cannot_change_state(self):
        for origin in ("https://example.org", "http://localhost:9001", "null", "file://", "moz-extension:"):
            with self.subTest(origin=origin):
                browser.set_block_action("pending")
                self.assertEqual(self.request(headers={"Origin": origin})[0], 403)
                self.assertEqual(browser.get_browser_data()["url"], "")
                self.assertEqual(browser._pending_action["action"], "block")
                self.assertEqual(self.request("/allow", {"url": "https://example.org"}, {"Origin": origin})[0], 403)
        self.assertEqual(json.loads(self.settings.read_text())["always_allow_domains"], [])

    def test_dns_rebinding_host_is_rejected(self):
        self.assertEqual(self.request(headers={"Host": f"attacker.example:{self.port}"})[0], 403)

    def test_simple_form_posts_are_rejected(self):
        for content_type in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            with self.subTest(content_type=content_type):
                self.assertEqual(self.request(headers={"Content-Type": content_type})[0], 415)

    def test_no_cors_preflight(self):
        status, _, headers = self.request(method="OPTIONS", headers={"Origin": "https://example.org"})
        self.assertEqual(status, 501)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_oversized_input_is_rejected(self):
        self.assertEqual(self.request(body={"title": "a" * 8193})[0], 413)
        self.assertEqual(self.request(body={"url": "a" * 32769})[0], 413)
        self.assertEqual(self.request(headers={"Content-Length": str(browser.MAX_BODY_BYTES + 1)})[0], 413)

    def test_invalid_types_are_rejected(self):
        for body in ([1], {"url": 7}, {"title": []}):
            self.assertEqual(self.request(body=body)[0], 400)

    def test_invalid_framing_is_rejected(self):
        for length in ("-1", "nonsense"):
            self.assertEqual(self.request(headers={"Content-Length": length})[0], 400)
        self.assertEqual(self.request(headers={"Transfer-Encoding": "chunked"})[0], 400)

    def test_duplicate_headers_are_rejected(self):
        for extra in (b"Host: attacker.example\r\n", b"Content-Length: 2\r\n", b"Origin: null\r\nOrigin: moz-extension://test\r\n"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=4) as conn:
                request = f"POST / HTTP/1.0\r\nHost: localhost:{self.port}\r\nContent-Type: application/json\r\nContent-Length: 2\r\n".encode()
                conn.sendall(request + extra + b"\r\n{}")
                status = conn.recv(1024).split(b"\r\n", 1)[0]
                self.assertNotIn(b"200", status)

    def test_allow_updates_disk_and_runtime_and_keeps_other_settings(self):
        for _ in range(2):
            self.assertEqual(self.request("/allow", {"url": "https://www.example.org/path?q=1"})[0], 200)
        self.assertEqual(json.loads(self.settings.read_text()), {"always_allow_domains": ["example.org"], "keep": True})
        self.assertEqual(rules.SETTINGS["always_allow_domains"], ["example.org"])

    def test_allow_creates_missing_list(self):
        self.settings.write_text('{}')
        self.assertEqual(self.request("/allow", {"url": "https://example.org"})[0], 200)
        self.assertEqual(json.loads(self.settings.read_text())["always_allow_domains"], ["example.org"])

    def test_allow_rejects_non_web_urls(self):
        for url in ("", "file:///private.txt", "javascript:alert(1)", "not a url", "https://"):
            self.assertEqual(self.request("/allow", {"url": url})[0], 400)

    def test_failed_atomic_write_preserves_original(self):
        before = self.settings.read_bytes()
        with patch.object(browser.os, "replace", side_effect=OSError("test")):
            self.assertEqual(self.request("/allow", {"url": "https://example.org"})[0], 500)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(list(self.settings.parent.iterdir()), [self.settings])

    def test_unknown_endpoint(self):
        self.assertEqual(self.request("/missing")[0], 404)


if __name__ == "__main__":
    unittest.main()
