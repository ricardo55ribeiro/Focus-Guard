import json
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse


SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.json"


def _load_settings() -> Dict[str, Any]:
    default_settings = {
        "always_block_domains": [],
        "always_allow_domains": [],
        "always_block_processes": [],
    }

    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except Exception:
        return default_settings

    return {
        "always_block_domains": [
            str(domain).lower() for domain in settings.get("always_block_domains", [])
        ],
        "always_allow_domains": [
            str(domain).lower() for domain in settings.get("always_allow_domains", [])
        ],
        "always_block_processes": [
            str(process).lower() for process in settings.get("always_block_processes", [])
        ],
    }


SETTINGS = _load_settings()


def _extract_domain(url: str) -> str:
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        domain = (parsed.netloc or parsed.path or "").lower()
        domain = domain.rsplit("@", 1)[-1]
        domain = domain.split(":", 1)[0]

        if domain.startswith("www."):
            domain = domain[4:]

        return domain
    except Exception:
        return ""


def check_rules(process_name: str, url: str) -> str:
    normalized_process_name = (process_name or "").lower()
    domain = _extract_domain(url)

    if normalized_process_name in SETTINGS["always_block_processes"]:
        return "block"

    if domain in SETTINGS["always_block_domains"]:
        return "block"

    if domain in SETTINGS["always_allow_domains"]:
        return "allow"

    return "ambiguous"
