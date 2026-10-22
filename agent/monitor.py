from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import logger
from capture.browser import (
    clear_block_action,
    get_browser_data,
    set_block_action,
    start_server,
)
from capture.window import get_active_window
from classifier import rules as _rules
from classifier.rules import check_rules
from tray import start_tray, update_tray, show_notification


SETTINGS_PATH = Path(__file__).resolve().parent / "config" / "settings.json"
BROWSER_PROCESSES = {
    "firefox.exe",
    "chrome.exe",
    "brave.exe",
    "msedge.exe",
}
_BG_CACHE_EXPIRY = 3

_browser_server_started = False
_browser_server_lock = threading.Lock()


def _load_settings() -> Dict[str, Any]:
    with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
        return json.load(settings_file)


def _refresh_rule_settings() -> None:
    try:
        _rules.SETTINGS = _rules._load_settings()
    except Exception:
        pass


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _extract_domain(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    domain = (parsed.netloc or parsed.path or "").lower()
    domain = domain.rsplit("@", 1)[-1]
    domain = domain.split(":", 1)[0]

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def _rule_reason(settings: Dict[str, Any], process_name: str, url: str, result: str) -> str:
    normalized_process = (process_name or "").lower()
    domain = _extract_domain(url)
    blocked_processes = {
        str(process).lower() for process in settings.get("always_block_processes", [])
    }
    blocked_domains = {
        str(blocked_domain).lower()
        for blocked_domain in settings.get("always_block_domains", [])
    }
    allowed_domains = {
        str(allowed_domain).lower()
        for allowed_domain in settings.get("always_allow_domains", [])
    }

    if result == "block":
        if normalized_process in blocked_processes:
            return f"process '{normalized_process}' is in always_block_processes"
        if domain in blocked_domains:
            return f"domain '{domain}' is in always_block_domains"
        return "matched a block rule"

    if result == "allow":
        if domain in allowed_domains:
            return f"domain '{domain}' is in always_allow_domains"
        return "matched an allow rule"

    return "no explicit rule matched"


def _ensure_browser_server_started() -> None:
    global _browser_server_started

    with _browser_server_lock:
        if _browser_server_started:
            return

        start_server()
        _browser_server_started = True


def _is_session_block_in_progress() -> bool:
    try:
        from blocker import blocker as _blocker

        return _blocker.is_blocking()
    except Exception:
        return False


def _minimize_active_window() -> None:
    try:
        import win32con
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception:
        pass


def _apply_silent_block(process_name: str, window_title: str, page_title: str) -> None:
    normalized = (process_name or "").strip().lower()
    if normalized in BROWSER_PROCESSES:
        set_block_action(reason=page_title or window_title)
        return

    _minimize_active_window()


def _queue_background_nudge(
    background_instructions: list[str],
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> None:
    def worker(
        instructions: list[str],
        process: str,
        window: str,
        current_url: str,
        title: str,
    ) -> None:
        try:
            from classifier.ai import generate_background_nudge

            nudge = generate_background_nudge(
                instructions,
                process,
                window,
                current_url,
                title,
            )
            show_notification("FocusGuard", nudge)
        except Exception as exc:
            logger.log_debug(f"[BACKGROUND NUDGE ERROR] {exc}")

    threading.Thread(
        target=worker,
        args=(
            list(background_instructions),
            process_name,
            window_title,
            url,
            page_title,
        ),
        name="focusguard-background-nudge",
        daemon=True,
    ).start()


def _queue_session_nudge(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> None:
    def worker(
        goal: str,
        process: str,
        window: str,
        current_url: str,
        title: str,
    ) -> None:
        try:
            from classifier.ai import generate_session_nudge

            nudge = generate_session_nudge(
                goal,
                process,
                window,
                current_url,
                title,
            )
            show_notification("FocusGuard", nudge)
        except Exception as exc:
            logger.log_debug(f"[SESSION NUDGE ERROR] {exc}")

    threading.Thread(
        target=worker,
        args=(
            study_goal,
            process_name,
            window_title,
            url,
            page_title,
        ),
        name="focusguard-session-nudge",
        daemon=True,
    ).start()


def _push_status(
    status_queue: Optional[queue.Queue],
    category: str,
    process_name: str,
    url: str,
    page_title: str,
    score: int,
    reason: str,
    blocked: bool,
) -> None:
    if status_queue is None:
        return

    status_queue.put(
        {
            "category": category,
            "process_name": process_name,
            "url": url,
            "page_title": page_title,
            "score": int(score),
            "reason": reason,
            "blocked": blocked,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    )


def _queue_block_popup(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
    status_queue: queue.Queue,
    stop_event: threading.Event,
    use_ai: bool = True,
) -> None:
    from blocker import blocker as _blocker

    if not _blocker._block_lock.acquire(blocking=False):
        return

    with _blocker._state_lock:
        _blocker._block_in_progress = True

    normalized = (process_name or "").strip().lower()
    is_browser = normalized in BROWSER_PROCESSES
    popup_done = threading.Event()

    try:
        if use_ai:
            from classifier.ai import generate_heckler, generate_pledge

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_heckler = executor.submit(generate_heckler, study_goal, normalized, window_title, url, page_title)
                future_pledge = executor.submit(generate_pledge, study_goal, normalized, window_title, url, page_title)
                heckler_message = future_heckler.result()
                pledge_text = future_pledge.result()
        else:
            site = url or page_title or window_title or "that site"
            heckler_message = f"You just opened {site}, which is on your blocked list. Get back to work."
            pledge_text = f"I will close this and return to my goal of {study_goal}."

        if stop_event.is_set():
            return

        if is_browser:
            set_block_action(reason=page_title or window_title)

        status_queue.put(
            {
                "action": "show_popup",
                "heckler": heckler_message,
                "pledge": pledge_text,
                "done_event": popup_done,
            }
        )

        while not stop_event.is_set():
            if popup_done.wait(0.5):
                break

        if not is_browser:
            _minimize_active_window()
    finally:
        clear_block_action()
        with _blocker._state_lock:
            _blocker._block_in_progress = False
        _blocker._block_lock.release()


def run_monitor(
    study_goal: Optional[str],
    status_queue: Optional[queue.Queue],
    stop_event: threading.Event,
    background_mode: bool = False,
) -> None:
    should_save_summary = False
    try:
        settings = _load_settings()
        background_instructions = settings.get("background_instructions", [])
        if isinstance(background_instructions, str):
            background_instructions = (
                [background_instructions] if background_instructions.strip() else []
            )
        elif isinstance(background_instructions, list):
            background_instructions = [
                str(instruction).strip()
                for instruction in background_instructions
                if str(instruction).strip()
            ]
        else:
            background_instructions = []

        _refresh_rule_settings()

        if background_mode:
            study_goal = None
            if background_instructions:
                import ollama_manager

                if not ollama_manager.ensure_running():
                    logger.log_debug(
                        "ERROR: Could not start Ollama for background rules. "
                        "Falling back to Phase 1 rules-only background mode."
                    )
                    background_instructions = []
                else:
                    logger.log_debug(f"[{_timestamp()}] Ollama is running.")

            if background_instructions:
                logger.log_debug(
                    f"[{_timestamp()}] Background AI rule monitor started."
                )
            else:
                logger.log_debug(f"[{_timestamp()}] Background rule monitor started.")
        else:
            import ollama_manager

            if not ollama_manager.ensure_running():
                logger.log_debug("ERROR: Could not start Ollama. Make sure it is installed.")
                return
            logger.log_debug(f"[{_timestamp()}] Ollama is running.")
            should_save_summary = True
            logger.log_debug(f"[{_timestamp()}] Study goal: {study_goal or '(empty)'}")
        _ensure_browser_server_started()
        logger.log_debug(
            f"[{_timestamp()}] Browser signal server started on http://localhost:9001"
        )
        if stop_event.is_set():
            return

        start_tray(study_goal or "", on_show_window=None, background_mode=background_mode)
        if not background_mode and status_queue is not None:
            status_queue.put({"action": "session_ready"})

        if background_mode:
            interval_seconds = int(settings.get("background_check_interval_seconds", 60))
        else:
            interval_seconds = int(settings.get("session_check_interval_seconds", 20))
        _window_size = max(5, int(300 / interval_seconds))
        if interval_seconds >= 60:
            _distracted_threshold = 2
        elif interval_seconds >= 31:
            _distracted_threshold = 2
        elif interval_seconds >= 16:
            _distracted_threshold = 3
        else:
            _distracted_threshold = 4

        _consecutive_distracted = 0
        _last_classified_key = ""
        _last_ai_result = None
        _background_cache_shots: int = 0
        _last_known_url = ""
        _warning_shown = False
        _current_domain: str = ""
        _domain_shot_history: dict = {}

        while not stop_event.is_set():
            if not background_mode and _is_session_block_in_progress():
                stop_event.wait(interval_seconds)
                continue

            active_window = get_active_window()
            process_name = active_window.get("process_name", "")
            window_title = active_window.get("window_title", "")
            url = ""
            page_title = ""

            rule_result = check_rules(process_name, "")

            if rule_result != "block" and process_name in BROWSER_PROCESSES:
                browser_data = get_browser_data()
                url = browser_data.get("url", "")
                page_title = browser_data.get("title", "")
                if url and url != _last_known_url:
                    _consecutive_distracted = 0
                    _warning_shown = False
                    _last_known_url = url
                elif url:
                    _last_known_url = url
                rule_result = check_rules(process_name, url)

            if rule_result == "block":
                _consecutive_distracted = 0
                if not background_mode:
                    _warning_shown = False
                _current_domain = ""
                reason = _rule_reason(settings, process_name, url, rule_result)
                logger.log_debug(
                    f"[{_timestamp()}] [BLOCK] {reason} | "
                    f"process={process_name or 'unknown'} | "
                    f"window_title={window_title or 'n/a'} | url={url or 'n/a'}"
                )
                if background_mode:
                    if not _warning_shown:
                        _warning_shown = True
                        _apply_silent_block(process_name, window_title, page_title)
                        block_msg = reason if len(reason) <= 100 else reason[:100].rsplit(" ", 1)[0]
                        show_notification("FocusGuard", f"Blocked: {block_msg}")
                else:
                    logger.log_event(
                        category="distracted",
                        process_name=process_name,
                        url=url,
                        page_title=page_title,
                        score=0,
                        reason=reason,
                        blocked=True,
                    )
                    update_tray("distracted")
                    _push_status(
                        status_queue=status_queue,
                        category="distracted",
                        process_name=process_name,
                        url=url,
                        page_title=page_title,
                        score=0,
                        reason=reason,
                        blocked=True,
                    )
                    if not _is_session_block_in_progress():
                        _queue_block_popup(
                            study_goal=study_goal or "",
                            process_name=process_name,
                            window_title=window_title,
                            url=url,
                            page_title=page_title,
                            status_queue=status_queue,
                            stop_event=stop_event,
                            use_ai=False,
                        )
            elif rule_result == "allow":
                _consecutive_distracted = 0
                _warning_shown = False
                reason = _rule_reason(settings, process_name, url, rule_result)
                logger.log_debug(
                    f"[{_timestamp()}] [ALLOW] {reason} | "
                    f"process={process_name or 'unknown'} | "
                    f"window_title={window_title or 'n/a'} | url={url or 'n/a'}"
                )
                if not background_mode:
                    logger.log_event(
                        category="productive",
                        process_name=process_name,
                        url=url,
                        page_title=page_title,
                        score=100,
                        reason=reason,
                        blocked=False,
                    )
                    update_tray("productive")
                    _push_status(
                        status_queue=status_queue,
                        category="productive",
                        process_name=process_name,
                        url=url,
                        page_title=page_title,
                        score=100,
                        reason=reason,
                        blocked=False,
                    )
            else:
                if background_mode and not background_instructions:
                    stop_event.wait(interval_seconds)
                    continue

                if background_mode and url.startswith("file:///"):
                    stop_event.wait(interval_seconds)
                    continue

                from classifier.ai import classify

                time_context = ""
                if background_mode:
                    domain = _extract_domain(url) if url else (process_name or "")
                    if domain != _current_domain:
                        _current_domain = domain
                    # Per-domain sliding window — history persists across domain switches
                    history = _domain_shot_history.setdefault(
                        _current_domain, deque(maxlen=_window_size)
                    ) if _current_domain else deque()
                    n = len(history)
                    if n > 0 and _current_domain:
                        distracted_count = history.count("distracted")
                        neutral_count    = history.count("neutral")
                        productive_count = history.count("productive")
                        approx_minutes   = round(n * interval_seconds / 60, 1)
                        time_context = (
                            f"In the last {n} shot(s) on {_current_domain} "
                            f"(approximately {approx_minutes} minute(s) at {interval_seconds}s interval): "
                            f"{distracted_count} distracted, {neutral_count} neutral, "
                            f"{productive_count} productive."
                        )

                _cache_key = f"{process_name}|{_last_known_url or window_title}"
                cache_hit = (
                    _cache_key == _last_classified_key
                    and _last_ai_result is not None
                )

                if background_mode:
                    if cache_hit and _background_cache_shots < _BG_CACHE_EXPIRY:
                        ai_result = dict(_last_ai_result)
                        _background_cache_shots += 1
                    else:
                        from classifier.ai import classify_background

                        _background_cache_shots = 0
                        ai_result = classify_background(
                            background_instructions=background_instructions,
                            process_name=process_name,
                            window_title=window_title,
                            url=url,
                            page_title=page_title,
                        )
                        _last_classified_key = _cache_key
                        _last_ai_result = ai_result
                else:
                    if cache_hit:
                        ai_result = dict(_last_ai_result)
                    else:
                        ai_result = classify(
                            study_goal=study_goal,
                            process_name=process_name,
                            window_title=window_title,
                            url=url,
                            page_title=page_title,
                            background_instructions=background_instructions,
                        )
                        _last_classified_key = _cache_key
                        _last_ai_result = ai_result

                if background_mode and _current_domain:
                    _domain_shot_history.setdefault(
                        _current_domain, deque(maxlen=_window_size)
                    ).append(ai_result["category"])

                if background_mode:
                    if ai_result["category"] == "distracted":
                        if not _warning_shown:
                            _warning_shown = True
                            _apply_silent_block(process_name, window_title, page_title)
                            _raw_reason = ai_result.get("reason", "rule violation")
                            block_reason = _raw_reason if len(_raw_reason) <= 100 else _raw_reason[:100].rsplit(" ", 1)[0]
                            show_notification("FocusGuard", f"Blocked: {block_reason}")
                    else:
                        _warning_shown = False

                    stop_event.wait(interval_seconds)
                    continue

                if ai_result["category"] == "distracted":
                    _consecutive_distracted += 1

                    if _consecutive_distracted == 1 and not _warning_shown:
                        _warning_shown = True
                        site = page_title or url or window_title or "something unrelated"
                        _queue_session_nudge(
                            study_goal or "",
                            process_name,
                            window_title,
                            url,
                            page_title,
                        )
                        logger.log_debug(
                            f"[{_timestamp()}] [WARNING] Soft warning shown — "
                            f"distracted by: {site}"
                        )
                else:
                    _consecutive_distracted = 0
                    _warning_shown = False

                blocked = False
                if _consecutive_distracted >= _distracted_threshold:
                    _consecutive_distracted = 0
                    _warning_shown = False
                    blocked = True
                    logger.log_debug(
                        f"[{_timestamp()}] [BLOCKING] "
                        f"Triggering block after {_distracted_threshold} consecutive distracted checks"
                    )

                _push_status(
                    status_queue=status_queue,
                    category=ai_result["category"],
                    process_name=process_name,
                    url=url,
                    page_title=page_title,
                    score=ai_result["score"],
                    reason=ai_result["reason"],
                    blocked=blocked,
                )

                if blocked:
                    _queue_block_popup(
                        study_goal=study_goal,
                        process_name=process_name,
                        window_title=window_title,
                        url=url,
                        page_title=page_title,
                        status_queue=status_queue,
                        stop_event=stop_event,
                    )

                logger.log_debug(
                    f"[{_timestamp()}] [AI] process={process_name or 'unknown'} | "
                    f"window_title={window_title or 'n/a'} | url={url or 'n/a'} | "
                    f"page_title={page_title or 'n/a'} | score={ai_result['score']} | "
                    f"category={ai_result['category']} | reason={ai_result['reason']}"
                )
                logger.log_event(
                    category=ai_result["category"],
                    process_name=process_name,
                    url=url,
                    page_title=page_title,
                    score=ai_result["score"],
                    reason=ai_result["reason"],
                    blocked=blocked,
                )
                update_tray(ai_result["category"])

            stop_event.wait(interval_seconds)
    finally:
        if not background_mode and should_save_summary:
            logger.save_and_summarize()
