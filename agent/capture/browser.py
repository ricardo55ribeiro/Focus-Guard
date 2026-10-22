import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

latest_browser_data = {"url": "", "title": ""}
_data_lock = threading.Lock()
_pending_action = {"action": "none", "reason": ""}
_action_lock = threading.Lock()

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"
MAX_BODY_BYTES = 64 * 1024


class RequestError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def get_browser_data() -> Dict[str, str]:
    with _data_lock:
        return dict(latest_browser_data)


def set_block_action(reason: str) -> None:
    with _action_lock:
        _pending_action["action"] = "block"
        _pending_action["reason"] = str(reason or "")


def clear_block_action() -> None:
    with _action_lock:
        _pending_action["action"] = "none"
        _pending_action["reason"] = ""


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, object]:
    if handler.headers.get("Transfer-Encoding"):
        raise RequestError(400, "Transfer encoding is not supported.")
    lengths = handler.headers.get_all("Content-Length", [])
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
        raise RequestError(400, "A single Content-Length is required.")
    length = int(lengths[0])
    if not 0 < length <= MAX_BODY_BYTES:
        raise RequestError(413, "Request body is too large or empty.")
    body = handler.rfile.read(length)
    if len(body) != length:
        raise RequestError(400, "Incomplete request body.")
    payload = json.loads(body)
    if isinstance(payload, dict):
        return payload
    raise ValueError("Request body must be a JSON object.")


def _extract_domain(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("A web URL is required.")
    domain = parsed.hostname.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _append_allowed_domain(domain: str) -> None:
    with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)

    allowed_domains = settings.get("always_allow_domains", [])
    if not isinstance(allowed_domains, list):
        allowed_domains = []
    settings["always_allow_domains"] = allowed_domains

    if domain not in allowed_domains:
        allowed_domains.append(domain)

    # Replace only a complete file so a failed write cannot truncate settings.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=SETTINGS_PATH.parent, delete=False
        ) as settings_file:
            temp_path = settings_file.name
            json.dump(settings, settings_file, indent=2)
            settings_file.write("\n")
        os.replace(temp_path, SETTINGS_PATH)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    try:
        from classifier import rules

        runtime_allowed_domains = rules.SETTINGS.setdefault("always_allow_domains", [])
        if domain not in runtime_allowed_domains:
            runtime_allowed_domains.append(domain)
    except Exception:
        pass


class _Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def _validate_request(self) -> None:
        # Loopback binding alone does not stop CSRF or DNS rebinding. Browser
        # pages cannot send JSON cross-origin without a successful preflight.
        # Do not add permissive CORS headers or accept form/text POSTs here.
        port = self.server.server_port
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0].lower() not in {
            f"localhost:{port}", f"127.0.0.1:{port}"
        }:
            raise RequestError(403, "Invalid host.")
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1:
            raise RequestError(403, "Invalid origin.")
        if origins:
            origin = urlparse(origins[0])
            if origin.scheme not in {"moz-extension", "chrome-extension"} or not origin.netloc:
                raise RequestError(403, "Only browser extensions may send requests.")
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            raise RequestError(415, "JSON content type required.")

    def _write_json_response(self, status_code: int, payload: Dict[str, str]) -> None:
        response_body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(response_body)

    def do_POST(self):
        try:
            self._validate_request()
            path = urlparse(self.path or "").path

            if path in ("", "/"):
                payload = _read_json_body(self)
                url = payload.get("url", "")
                title = payload.get("title", "")
                if not isinstance(url, str) or not isinstance(title, str):
                    raise ValueError("URL and title must be strings.")
                if len(url) > 32768 or len(title) > 8192:
                    raise RequestError(413, "URL or title is too large.")

                with _data_lock:
                    latest_browser_data["url"] = url
                    latest_browser_data["title"] = title

                with _action_lock:
                    action_payload = dict(_pending_action)
                    if _pending_action["action"] == "block":
                        _pending_action["action"] = "none"
                        _pending_action["reason"] = ""

                self._write_json_response(200, action_payload)
                return

            if path == "/allow":
                payload = _read_json_body(self)
                url = payload.get("url", "")
                if not isinstance(url, str):
                    raise ValueError("URL must be a string.")

                domain = _extract_domain(url)
                if not domain:
                    raise ValueError("Missing domain.")

                _append_allowed_domain(domain)
                self._write_json_response(200, {"status": "allowed"})
                return

            self._write_json_response(404, {"error": "Unknown endpoint."})
        except RequestError as exc:
            self._write_json_response(exc.status, {"error": str(exc)})
        except (ValueError, UnicodeError, RecursionError):
            self._write_json_response(400, {"error": "Invalid request."})
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except OSError:
            self._write_json_response(500, {"error": "Could not save settings."})

    def log_message(self, format, *args):
        pass


def start_server() -> None:
    server = HTTPServer(("127.0.0.1", 9001), _Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="focusguard-browser-server",
        daemon=True,
    )
    thread.start()
