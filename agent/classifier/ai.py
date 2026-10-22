import json
import logging
logging.getLogger("websockets").setLevel(logging.CRITICAL)
from typing import Dict

import logger

try:
    from ollama import Client

    # Activity metadata must stay on this computer, even when the user's
    # environment configures a remote Ollama host or an HTTP proxy.
    ollama = Client(
        host="http://127.0.0.1:11434",
        trust_env=False,
        follow_redirects=False,
        timeout=120,
    )
except Exception:
    ollama = None


DEFAULT_RESULT = {
    "score": 50,
    "category": "neutral",
    "reason": "classification failed",
}


def _extract_json_text(response_text: str) -> str:
    cleaned = (response_text or "").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in response.")

    return cleaned[start : end + 1]


def _clean_response(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = cleaned.replace("\t", " ")
    cleaned = cleaned.replace("|", "")
    cleaned = cleaned.replace("\r", " ")
    cleaned = cleaned.replace("\n", " ")
    return " ".join(cleaned.split())



def _build_prompt(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
    background_instructions: list[str] = [],
    time_context: str = "",
) -> str:
    background_instructions = [
        str(rule).strip() for rule in background_instructions if str(rule).strip()
    ]
    if background_instructions:
        rules_text = "\n".join(f"- {r}" for r in background_instructions)
        time_context_block = f"\nTime context: {time_context}" if time_context else ""
        if study_goal:
            context = (
                f"User's background mode rules:\n{rules_text}\n\n"
                f"Current session goal: {study_goal}"
            )
            task = (
                "Classify whether the user's current activity follows their rules "
                "and supports their current session goal."
            )

            return f"""
You are a focus assistant. {task} Be accurate, not lenient.

{context}

Observed signals:
- Process: {process_name or "Unknown"}
- Window title: {window_title or "Unknown"}
- Browser URL: {url or "None"}
- Page title: {page_title or "None"}
{time_context_block}

Scoring:
- 0-35 = clearly distracted (violates the rules, entertainment/social media, or content unrelated to the allowed context)
- 36-65 = neutral (terminals, ambiguous tools, search pages, unclear intent)
- 66-100 = productive (clearly follows the rules and, if provided, supports the session goal)

Critical rules - apply these strictly:
- The page title and video title are PRIMARY signals. Trust them above all else.
- If a rule limits a site or activity to educational/work use, unrelated entertainment on that site = score 0-20, distracted.
- A YouTube video title unrelated to the rules or current session goal = score 0-20, distracted.
- A YouTube channel page or homepage without a specific video = score 20-35, distracted.
- Only score YouTube productive if the video title clearly follows the rules and, if provided, supports the session goal.
- Terminals and command prompts = score 50, neutral. Always.
- AI assistants (ChatGPT, Claude) = score 50, neutral. User may or may not be studying.
- If URL and page title are both present and clearly relevant to the rules, score 75+.
- Never let charitable assumptions override clear evidence in the title or URL.

Return ONLY valid JSON:
{{
  "score": 0,
  "category": "productive",
  "reason": "one short sentence"
}}
No markdown, no extra text.
""".strip()

        context = f"User's background mode rules:\n{rules_text}"
        task = (
            "Classify whether the user's current activity follows their "
            "background mode rules."
        )

        return f"""
You are a focus assistant. {task} Be accurate, not lenient.

{context}

Observed signals:
- Process: {process_name or "Unknown"}
- Window title: {window_title or "Unknown"}
- Browser URL: {url or "None"}
- Page title: {page_title or "None"}
{time_context_block}

Scoring:
- 0-35 = distracted (the current activity clearly and explicitly violates one of the user's stated rules above - not merely unproductive, but an actual rule violation)
- 36-65 = neutral (activity does not violate any rule; includes general browsing, AI assistants, writing tools, research, communication, entertainment not covered by rules)
- 66-100 = productive (activity clearly and positively follows the spirit of the rules, e.g. educational content, work tools)

Critical rules - apply these strictly:
- Score distracted ONLY if the activity clearly violates a stated rule. If no rule covers it, score neutral (50) or higher. Never penalise activities the rules do not mention.
- When in doubt, score neutral. Default to permissive, not restrictive.
- AI assistants (ChatGPT, Claude, Gemini) = score 50, neutral. Always.
- Writing tools (Overleaf, Word, Google Docs, Notion) = score 70, productive. Always.
- Research and study tools (YouTube educational content, Wikipedia, documentation) = score 60-75, neutral to productive.
- YouTube: only score distracted if the specific video title or content clearly matches a prohibited category in the rules. If YouTube is not mentioned in the rules, or if the video is not one of the prohibited types, score neutral or productive.
- Terminals and code editors = score 50, neutral. Always.
- General browsing, news, communication tools = score 50, neutral, unless a rule explicitly prohibits them.
- Do not infer restrictions that are not stated. If the rules say "no adult content", that does not mean all entertainment is banned - only adult content is.

Return ONLY valid JSON:
{{
  "score": 0,
  "category": "productive",
  "reason": "one short sentence"
}}
No markdown, no extra text.
""".strip()

    return f"""
You are a focus assistant. Classify whether the user's current activity supports their study goal. Be accurate, not lenient.

Study goal: {study_goal or "Not provided"}

Observed signals:
- Process: {process_name or "Unknown"}
- Window title: {window_title or "Unknown"}
- Browser URL: {url or "None"}
- Page title: {page_title or "None"}

Scoring:
- 0-35 = clearly distracted (entertainment, social media, or content unrelated to the goal)
- 36-65 = neutral (terminals, ambiguous tools, search pages, unclear intent)
- 66-100 = productive (clearly supports the study goal)

Critical rules — apply these strictly:
- The page title and video title are PRIMARY signals. Trust them above all else.
- A YouTube video title unrelated to the study goal = score 0-20, distracted. Always.
- A YouTube channel page or homepage without a specific video = score 20-35, distracted.
- Only score YouTube productive if the video title is clearly related to the study goal.
- Terminals and command prompts = score 50, neutral. Always.
- AI assistants (ChatGPT, Claude) = score 50, neutral. User may or may not be studying.
- If URL and page title are both present and clearly relevant to the goal, score 75+.
- Never let charitable assumptions override clear evidence in the title or URL.
- Topics related to the study domain count as productive. E.g. if studying C programming, data structures, algorithms, memory management, and compilers are all productive.

Return ONLY valid JSON:
{{
  "score": 0,
  "category": "productive",
  "reason": "one short sentence"
}}
No markdown, no extra text.
""".strip()


def classify(
    study_goal: str = "",
    process_name: str = "",
    window_title: str = "",
    url: str = "",
    page_title: str = "",
    background_instructions: list[str] = [],
    time_context: str = "",
) -> Dict[str, object]:
    if ollama is None:
        return dict(DEFAULT_RESULT)

    try:
        prompt = _build_prompt(
            study_goal,
            process_name,
            window_title,
            url,
            page_title,
            background_instructions,
            time_context,
        )
        response = ollama.chat(
            model="qwen2.5:3b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            format="json",
        )

        response_text = response.message.content or ""
        parsed = json.loads(_extract_json_text(response_text))

        score_val = int(parsed["score"])
        score_val = max(0, min(100, score_val))
        if score_val >= 66:
            category = "productive"
        elif score_val <= 35:
            category = "distracted"
        else:
            category = "neutral"
        score = score_val

        reason = str(parsed["reason"]).strip()
        if not reason:
            raise ValueError("Missing reason returned.")

        return {
            "score": score,
            "category": category,
            "reason": reason,
        }
    except Exception as e:
        logger.log_debug(f"[AI ERROR] {e}")
        return dict(DEFAULT_RESULT)


def classify_background(
    background_instructions: list[str],
    process_name: str = "",
    window_title: str = "",
    url: str = "",
    page_title: str = "",
) -> Dict[str, object]:
    """
    Binary violation check for background mode. Asks the model whether the
    current activity violates any of the user's rules. Returns distracted only
    on a clear rule violation. Defaults to neutral when uncertain.
    """
    if ollama is None:
        return {"score": 50, "category": "neutral", "reason": "ollama unavailable"}

    rules_text = "\n".join(
        f"- {r}" for r in background_instructions if str(r).strip()
    )
    if not rules_text:
        return {"score": 50, "category": "neutral", "reason": "no rules defined"}

    prompt = (
        f"You enforce these rules:\n{rules_text}\n\n"
        f"Current activity:\n"
        f"- Process: {process_name or 'Unknown'}\n"
        f"- Window title: {window_title or 'Unknown'}\n"
        f"- URL: {url or 'None'}\n"
        f"- Page title: {page_title or 'None'}\n\n"
        "Does this activity clearly and obviously violate ANY of the rules above?\n\n"
        "These are NEVER violations regardless of what the rules say: PDF files, "
        "academic documents, exam papers, lecture notes, research papers, "
        "spreadsheets, and any local file on disk.\n\n"
        "A file name or document title is NOT evidence of a rule violation. "
        "Evaluate what the content clearly is, not what it might theoretically be.\n"
        "When uncertain, ALWAYS answer OK.\n\n"
        "Reply with ONLY one of these two formats:\n"
        "VIOLATION: one short phrase explaining which rule is violated (max 80 characters)\n"
        "OK: one short phrase describing the activity (max 80 characters)\n\n"
        "Only answer VIOLATION for obvious violations. Default to OK."
    )

    try:
        response = ollama.chat(
            model="qwen2.5:3b",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _clean_response(response.message.content or "")
        upper = raw.upper()
        if upper.startswith("VIOLATION"):
            colon = raw.find(":")
            reason = raw[colon + 1:].strip() if colon != -1 else "rule violation detected"
            return {"score": 15, "category": "distracted", "reason": reason[:200]}
        else:
            colon = raw.find(":")
            reason = raw[colon + 1:].strip() if colon != -1 else "no rule violation"
            return {"score": 50, "category": "neutral", "reason": reason[:200]}
    except Exception as exc:
        logger.log_debug(f"[BG CLASSIFY ERROR] {exc}")
        return {"score": 50, "category": "neutral", "reason": "classification error"}


def generate_heckler(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> str:
    if ollama is None:
        return "Hey! Get back to work."

    prompt = (
        "You are a snarky but caring productivity coach. "
        f"The user was caught procrastinating. Their study goal is {study_goal}. "
        f"They were on: process={process_name}, window={window_title}, url={url}, page={page_title}. "
        "Write a short (2-3 sentence) personalized snarky message calling them out. "
        "Be specific about what they were doing. No quotes around the message. "
        "Do not use tabs, bullet points, newlines, pipe characters ('|'), or em dashes ('—') in your response."
    )

    try:
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        return _clean_response(response.message.content or "") or "Hey! Get back to work."
    except Exception:
        return "Hey! Get back to work."


def generate_pledge(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> str:
    if ollama is None:
        return "I will stop procrastinating and focus on my work."

    prompt = (
        "Write a single short sentence pledge the user must type to acknowledge they "
        f"were procrastinating and commit to returning to their goal of {study_goal}. "
        f"They were distracted by: {page_title or window_title}. "
        'The pledge should start with "I will". Keep it to 20 words maximum. Return ONLY the pledge sentence, '
        "no quotes, no extra text. "
        "Do not use pipe characters (|) or em dashes (—) in your response. Return a single plain sentence only."
    )

    try:
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        return (
            _clean_response(response.message.content or "")
            or "I will stop procrastinating and focus on my work."
        )
    except Exception:
        return "I will stop procrastinating and focus on my work."


def generate_background_nudge(
    background_instructions: list[str],
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> str:
    fallback = "You seem distracted. Take a moment to refocus."
    if ollama is None:
        return fallback

    rules_text = "\n".join(f"- {r}" for r in background_instructions)
    prompt = f"""
You are a direct, slightly witty focus assistant.

User's background mode rules:
{rules_text}

Current activity:
- Process: {process_name or "Unknown"}
- Window title: {window_title or "Unknown"}
- Browser URL: {url or "None"}
- Page title: {page_title or "None"}

Write one short, direct sentence calling out what they are doing relative to their rules.
Do not be preachy.
Reply with one sentence only. Maximum 120 characters. No emojis.
""".strip()

    try:
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        nudge = _clean_response(response.message.content or "")
        if not nudge:
            return fallback
        return nudge[:120].rstrip()
    except Exception:
        return fallback


def generate_session_nudge(
    study_goal: str,
    process_name: str,
    window_title: str,
    url: str,
    page_title: str,
) -> str:
    fallback = _clean_response(
        f"Hey! That doesn't look like {study_goal}. Get back to work."
    )[:120].rstrip()
    if ollama is None:
        return fallback

    caught_doing = page_title or window_title or process_name
    prompt = (
        f"The user's study goal is {study_goal}. "
        f"They were caught doing {caught_doing}. "
        "Write one short direct sentence calling it out. "
        "Be specific and slightly snarky. No emojis. "
        "No pipe characters. No tabs. One sentence only. Maximum 120 characters."
    )

    try:
        response = ollama.chat(
            model="qwen2.5:7b",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )
        nudge = _clean_response(response.message.content or "")
        if not nudge:
            return fallback
        return nudge[:120].rstrip()
    except Exception:
        return fallback
