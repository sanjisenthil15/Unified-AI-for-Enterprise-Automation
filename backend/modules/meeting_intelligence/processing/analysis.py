"""
processing/analysis.py — Phase 7.

Turn a (diarized) meeting transcript into structured information:
    summary, key discussion points, decisions, action items.

Provider-abstracted:

    AnalysisProvider (ABC)
      └─ GeminiAnalysisProvider   google-genai, same call/parse pattern as
                                  modules/recruitment/service.py
      (an Ollama / local-LLM provider can be added here later)

`get_analysis_provider()` picks the backend from MeetingSettings.

IMPORTANT: the AI only *extracts* action items. It records the assignee it
heard as free text (`assignee_name_raw`); it does NOT resolve that to a
user/employee. Assignment is manual (Phase 2 schema, done via the API).
No hard-coded AI responses.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config.settings import settings
from modules.meeting_intelligence.config import meeting_settings

_VALID_SENTIMENT = {"positive", "neutral", "negative", "mixed"}
_VALID_PRIORITY = {"low", "medium", "high"}


class AnalysisError(Exception):
    """Analysis could not be produced. `kind` steers the HTTP status."""

    def __init__(self, message: str, *, kind: str = "api") -> None:
        super().__init__(message)
        self.kind = kind  # "config" | "api" | "parse"


@dataclass(frozen=True)
class ExtractedActionItem:
    description: str
    assignee_name_raw: str | None = None
    priority: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class AnalysisResult:
    summary: str
    key_points: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    action_items: list[ExtractedActionItem] = field(default_factory=list)
    sentiment: str | None = None
    model_provider: str = "gemini"
    model_name: str = ""
    raw_response: dict | None = None


# --------------------------------------------------------------------------- #
# prompt + response parsing (shared by any JSON-returning provider)
# --------------------------------------------------------------------------- #
_PROMPT = """You are a meeting-analysis assistant. Read the transcript and return ONLY a
JSON object — no markdown, no commentary.

TRANSCRIPT:
{transcript}

Return EXACTLY this shape:
{{
  "summary": "<3-6 sentence neutral summary of what the meeting covered>",
  "key_points": ["<important discussion point>", "..."],
  "decisions": ["<explicit decision the group made>", "..."],
  "sentiment": "<one of: positive | neutral | negative | mixed>",
  "action_items": [
    {{
      "description": "<the task, self-contained; include any deadline that was mentioned>",
      "assignee": "<who it was given to, exactly as referenced (e.g. 'Speaker 2' or a name), or null>",
      "priority": "<one of: low | medium | high, or null>",
      "confidence": <number 0-1 for how clearly this was an action item>
    }}
  ]
}}
Use empty arrays when there are no decisions or action items. Do not invent assignees."""


def build_prompt(transcript_text: str) -> str:
    return _PROMPT.format(transcript=transcript_text)


def parse_json_response(raw_text: str) -> dict:
    clean = re.sub(r"^```[a-zA-Z]*\n?|```$", "", (raw_text or "").strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"Model returned non-JSON: {raw_text[:200]}", kind="parse") from exc
    if not isinstance(data, dict):
        raise AnalysisError("Model response was not a JSON object.", kind="parse")
    return data


def _str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [s for s in (_str(v) for v in value) if s]


def result_from_dict(data: dict, *, provider: str, model: str) -> AnalysisResult:
    summary = _str(data.get("summary"))
    if not summary:
        raise AnalysisError("Model response had no summary.", kind="parse")

    sentiment = data.get("sentiment")
    sentiment = sentiment if sentiment in _VALID_SENTIMENT else None

    items: list[ExtractedActionItem] = []
    for entry in data.get("action_items") or []:
        if not isinstance(entry, dict):
            continue
        description = _str(entry.get("description"))
        if not description:
            continue
        priority = entry.get("priority")
        priority = priority if priority in _VALID_PRIORITY else None
        raw_conf = entry.get("confidence")
        confidence = float(raw_conf) if isinstance(raw_conf, (int, float)) and 0 <= raw_conf <= 1 else None
        items.append(ExtractedActionItem(
            description=description,
            assignee_name_raw=_str(entry.get("assignee")) or None,
            priority=priority,
            confidence=confidence,
        ))

    return AnalysisResult(
        summary=summary,
        key_points=_str_list(data.get("key_points")),
        decisions=_str_list(data.get("decisions")),
        action_items=items,
        sentiment=sentiment,
        model_provider=provider,
        model_name=model,
        raw_response=data,
    )


# --------------------------------------------------------------------------- #
# providers
# --------------------------------------------------------------------------- #
class AnalysisProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def analyze(self, transcript_text: str) -> AnalysisResult:
        ...


_RETRY_DELAY_RE = re.compile(r"retry(?:Delay|\s+in)['\":\s]+([0-9.]+)s", re.IGNORECASE)


def _is_retryable(message: str) -> bool:
    if "503" in message or "UNAVAILABLE" in message:
        return True
    # 429 is retryable only when it's a short per-minute throttle, not the daily cap.
    return "429" in message and "PerDay" not in message and "per day" not in message.lower()


class GeminiAnalysisProvider(AnalysisProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        self.model = model or meeting_settings.gemini_model
        self.max_retries = (
            meeting_settings.gemini_max_retries if max_retries is None else max_retries
        )

    def analyze(self, transcript_text: str) -> AnalysisResult:
        if not self.api_key or not self.api_key.strip():
            raise AnalysisError("GEMINI_API_KEY is not configured.", kind="config")

        prompt = build_prompt(transcript_text)
        attempt = 0
        while True:
            try:
                from google import genai

                client = genai.Client(api_key=self.api_key)
                response = client.models.generate_content(model=self.model, contents=prompt)
                raw = (getattr(response, "text", "") or "").strip()
                break
            except AnalysisError:
                raise
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if attempt < self.max_retries and _is_retryable(message):
                    attempt += 1
                    m = _RETRY_DELAY_RE.search(message)
                    delay = min(float(m.group(1)) if m else 5.0, 20.0)
                    time.sleep(delay)
                    continue
                if "429" in message or "RESOURCE_EXHAUSTED" in message:
                    raise AnalysisError(
                        f"Gemini quota / rate limit exceeded for model '{self.model}'. "
                        f"Retry later, or set MEETING_GEMINI_MODEL to a model with "
                        f"remaining quota (e.g. gemini-3.7-flash).",
                        kind="api",
                    ) from exc
                raise AnalysisError(f"Gemini API error: {exc}", kind="api") from exc

        data = parse_json_response(raw)
        return result_from_dict(data, provider=self.name, model=self.model)


def get_analysis_provider(provider: str | None = None) -> AnalysisProvider:
    provider = (provider or meeting_settings.ai_provider or "gemini").lower()
    if provider == "gemini":
        return GeminiAnalysisProvider()
    raise AnalysisError(
        f"Unknown analysis provider {provider!r} (only 'gemini' is implemented).",
        kind="config",
    )
