import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path


LOGS_DIR = Path(__file__).resolve().parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

SESSION_LOG_PATH = LOGS_DIR / f"session_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

_events = []
_session_start_time = time.time()


def log_debug(message: str) -> None:
    print(message)


def log_event(
    category: str,
    process_name: str,
    url: str,
    page_title: str,
    score: int,
    reason: str,
    blocked: bool = False,
) -> None:
    _events.append(
        {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "process_name": process_name,
            "url": url,
            "page_title": page_title,
            "score": score,
            "reason": reason,
            "blocked": blocked,
        }
    )


def _format_duration(seconds: float) -> str:
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    remaining_seconds = total_seconds % 60
    return f"{minutes:02d}:{remaining_seconds:02d}"


def save_and_summarize() -> None:
    with SESSION_LOG_PATH.open("w", encoding="utf-8") as log_file:
        json.dump(_events, log_file, indent=2)

    duration = _format_duration(time.time() - _session_start_time)
    total_checks = len(_events)
    category_counts = Counter(event["category"] for event in _events)
    blocks_triggered = sum(1 for event in _events if event.get("blocked"))
    productive_urls = Counter(
        event["url"]
        for event in _events
        if event.get("category") == "productive" and event.get("url")
    )

    log_debug("")
    log_debug("FocusGuard session summary")
    log_debug("--------------------------")
    log_debug(f"Total session duration: {duration}")

    for category in ("productive", "neutral", "distracted"):
        count = category_counts.get(category, 0)
        percent = (count / total_checks * 100) if total_checks else 0
        log_debug(f"{category.capitalize()} checks: {count} ({percent:.1f}%)")

    log_debug(f"Blocks triggered: {blocks_triggered}")
    log_debug("Top productive URLs:")

    top_urls = productive_urls.most_common(3)
    if top_urls:
        for index, (url, count) in enumerate(top_urls, start=1):
            log_debug(f"{index}. {url} ({count})")
    else:
        log_debug("None")

    log_debug(f"Log saved to: {SESSION_LOG_PATH}")
