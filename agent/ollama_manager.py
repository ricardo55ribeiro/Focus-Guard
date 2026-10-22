import subprocess
import os
import time
import urllib.request
import urllib.error

_process = None
_we_started_it = False


def _is_running() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:11434/api/tags", timeout=2):
            pass
        return True
    except Exception:
        return False


def ensure_running() -> bool:
    global _process, _we_started_it

    if _is_running():
        _we_started_it = False
        return True

    try:
        _process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"},
        )
        _we_started_it = True
    except Exception:
        return False

    for _ in range(20):
        time.sleep(1)
        if _is_running():
            return True

    return False


def shutdown_if_started() -> None:
    global _process, _we_started_it

    if _we_started_it and _process is not None:
        _process.terminate()
        _process = None
        _we_started_it = False
