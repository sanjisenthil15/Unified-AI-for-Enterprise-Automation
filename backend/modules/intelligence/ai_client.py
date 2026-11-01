"""
modules/intelligence/ai_client.py

Centralized Google Gemini AI client for the Enterprise Intelligence layer.
Features:
  - Reuses google-genai==1.20.0 and settings.GEMINI_API_KEY
  - Bounded exponential retries for transient 429 / 503 errors
  - Fail-fast mechanism for exhausted daily quotas (RESOURCE_EXHAUSTED / PerDay)
  - Safe Markdown fence stripping and Pydantic validation
  - Privacy safeguards: never logs API keys or raw prompts containing sensitive metrics
"""

import json
import logging
import re
import time
from typing import Any, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Regex to detect suggested retry delay in error strings (e.g., 'retryDelay: 4.5s')
_RETRY_DELAY_RE = re.compile(r"retry(?:Delay|\s+in)['\":\s]+([0-9.]+)s", re.IGNORECASE)

DEFAULT_MODEL = "gemini-flash-lite-latest"
DEFAULT_MAX_RETRIES = 2
DEFAULT_TIMEOUT_SECONDS = 30.0


# --------------------------------------------------------------------------- #
# Custom Exceptions
# --------------------------------------------------------------------------- #

class AIClientError(Exception):
    """Base exception for AI client failures."""
    def __init__(self, message: str, *, kind: str = "general") -> None:
        super().__init__(message)
        self.kind = kind  # 'config', 'quota', 'api', 'parse', 'validation'


class AIConfigError(AIClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="config")


class AIQuotaError(AIClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="quota")


class AIParseError(AIClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="parse")


class AIValidationError(AIClientError):
    def __init__(self, message: str) -> None:
        super().__init__(message, kind="validation")


# --------------------------------------------------------------------------- #
# Helper Functions
# --------------------------------------------------------------------------- #

def strip_markdown_fences(raw_text: str) -> str:
    """Safely strips ```json ... ``` or ``` ... ``` markdown fences from model text."""
    if not raw_text:
        return ""
    # Remove leading ```json or ``` and trailing ```
    cleaned = re.sub(r"^```(?:json)?\s*\n?|\n?```\s*$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return cleaned


def is_retryable_error(message: str) -> bool:
    """Determines if a Gemini error is a transient throttle or temporary outage."""
    msg = message.lower()
    if "503" in msg or "unavailable" in msg or "bad gateway" in msg:
        return True
    # 429 is retryable ONLY if it is a transient per-minute burst, not the daily cap
    if "429" in msg or "too many requests" in msg:
        if "perday" in msg or "per day" in msg or "daily" in msg or "quota exceeded" in msg:
            return False
        return True
    return False


def is_daily_quota_exhausted(message: str) -> bool:
    """Detects hard daily quota exhaustion."""
    msg = message.lower()
    return (
        "perday" in msg
        or "per day" in msg
        or "resource_exhausted" in msg
        or "quota exceeded" in msg
    )


# --------------------------------------------------------------------------- #
# Gemini Client
# --------------------------------------------------------------------------- #

class GeminiClient:
    """Wrapper around google-genai SDK for structured intelligence extraction."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key if api_key is not None else getattr(settings, "GEMINI_API_KEY", "")
        self.model_name = model_name
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        """Returns True if a non-placeholder API key is available."""
        key = (self._api_key or "").strip()
        return bool(key and key.lower() not in {"your_gemini_api_key_here", "changeme", "none", ""})

    def _get_sdk_client(self) -> Any:
        if not self.is_configured:
            raise AIConfigError("GEMINI_API_KEY is not configured or is a placeholder.")
        try:
            from google import genai
            return genai.Client(api_key=self._api_key)
        except ImportError as exc:
            raise AIConfigError("google-genai package is not installed.") from exc

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Executes prompt against Gemini, cleans fences, parses JSON, and validates
        against the given Pydantic schema."""

        client = self._get_sdk_client()

        # Sanitize prompt length for safety logs without leaking content
        logger.info(
            "Invoking Gemini model '%s' (prompt size: %d chars, schema: %s)",
            self.model_name,
            len(prompt),
            response_schema.__name__,
        )

        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction.strip()}\n\n{prompt.strip()}"

        attempt = 0
        raw_text = ""

        while True:
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=full_prompt,
                )
                raw_text = (getattr(response, "text", "") or "").strip()
                break
            except Exception as exc:  # noqa: BLE001
                err_msg = str(exc)

                # Check for hard daily quota
                if is_daily_quota_exhausted(err_msg):
                    logger.warning("Gemini daily quota exhausted for model '%s'. Failing fast.", self.model_name)
                    raise AIQuotaError(
                        f"Gemini daily quota exhausted for model '{self.model_name}'. System falling back to deterministic analysis."
                    ) from exc

                # Check if retryable transient error
                if attempt < self.max_retries and is_retryable_error(err_msg):
                    attempt += 1
                    delay_match = _RETRY_DELAY_RE.search(err_msg)
                    delay = min(float(delay_match.group(1)) if delay_match else (2.0 * attempt), 10.0)
                    logger.warning(
                        "Transient Gemini error (attempt %d/%d). Retrying in %.1fs: %s",
                        attempt,
                        self.max_retries,
                        delay,
                        err_msg[:120],
                    )
                    time.sleep(delay)
                    continue

                logger.error("Gemini API call failed after %d attempts: %s", attempt, err_msg[:200])
                raise AIClientError(f"Gemini API request failed: {err_msg[:200]}", kind="api") from exc

        # Clean markdown formatting
        cleaned_json = strip_markdown_fences(raw_text)
        if not cleaned_json:
            raise AIParseError("Gemini returned an empty response.")

        try:
            parsed_data = json.loads(cleaned_json)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini response as JSON: %s", cleaned_json[:200])
            raise AIParseError(f"Gemini response could not be decoded as JSON: {exc}") from exc

        if not isinstance(parsed_data, dict):
            raise AIParseError("Gemini JSON response was not a top-level dictionary object.")

        # Validate with Pydantic
        try:
            validated = response_schema.model_validate(parsed_data)
            return validated
        except ValidationError as val_exc:
            logger.error("Pydantic validation failed for schema %s: %s", response_schema.__name__, val_exc)
            raise AIValidationError(
                f"Gemini response schema validation failed for {response_schema.__name__}: {val_exc.errors()[:3]}"
            ) from val_exc
