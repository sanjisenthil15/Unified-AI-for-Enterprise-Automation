"""
backend/tests/test_intelligence_foundation.py

Focused test suite for Submodule 3.1: AI Intelligence Foundation.
Tests:
  - Gemini client initialization
  - Missing API key handling
  - JSON parsing and Markdown fence removal
  - Pydantic validation failures
  - Retryable vs non-retryable error detection
  - Mocked Gemini API execution & retry backoff
  - Fast failure for daily quota exhaustion
  - Cache hit, miss, expiration, invalidation
  - Concurrent cache access protection (single evaluation)
  - Refresh throttling
"""

import time
import threading
from unittest.mock import MagicMock, patch
import pytest

from modules.intelligence.ai_client import (
    AIClientError,
    AIConfigError,
    AIParseError,
    AIQuotaError,
    AIValidationError,
    GeminiClient,
    is_daily_quota_exhausted,
    is_retryable_error,
    strip_markdown_fences,
)
from modules.intelligence.cache import IntelligenceCache
from modules.intelligence.schemas import (
    BottleneckSeverity,
    DelayStatus,
    ExecutiveRecommendationItem,
    ProjectRiskExplanationItem,
    RecommendationCategory,
    RiskLevel,
    UrgencyLevel,
    WorkloadBottleneckItem,
)


# --------------------------------------------------------------------------- #
# 1. AI Client Initialization & Configuration Tests
# --------------------------------------------------------------------------- #

def test_gemini_client_initialization():
    client = GeminiClient(api_key="valid_dummy_key", model_name="gemini-flash-lite-latest")
    assert client.model_name == "gemini-flash-lite-latest"
    assert client.is_configured is True


def test_missing_api_key_raises_config_error():
    client_empty = GeminiClient(api_key="")
    assert client_empty.is_configured is False
    with pytest.raises(AIConfigError, match="GEMINI_API_KEY is not configured"):
        client_empty.generate_structured("test prompt", ExecutiveRecommendationItem)

    client_placeholder = GeminiClient(api_key="your_gemini_api_key_here")
    assert client_placeholder.is_configured is False
    with pytest.raises(AIConfigError, match="GEMINI_API_KEY is not configured"):
        client_placeholder.generate_structured("test prompt", ExecutiveRecommendationItem)


# --------------------------------------------------------------------------- #
# 2. Markdown Fence Stripping & JSON Parsing Tests
# --------------------------------------------------------------------------- #

def test_markdown_fence_stripping():
    # Plain JSON
    raw = '{"key": "value"}'
    assert strip_markdown_fences(raw) == '{"key": "value"}'

    # Fenced JSON with language tag
    fenced_json = '```json\n{"key": "value"}\n```'
    assert strip_markdown_fences(fenced_json) == '{"key": "value"}'

    # Fenced without language tag
    fenced_plain = '```\n{"key": "value"}\n```'
    assert strip_markdown_fences(fenced_plain) == '{"key": "value"}'

    # Fences with surrounding spaces
    fenced_spaces = '   ```json  \n  {"key": "value"}  \n  ```   '
    assert strip_markdown_fences(fenced_spaces) == '{"key": "value"}'

    # Empty string
    assert strip_markdown_fences("") == ""


# --------------------------------------------------------------------------- #
# 3. Pydantic Schema Validation Tests
# --------------------------------------------------------------------------- #

def test_pydantic_validation_success():
    valid_data = {
        "id": "rec-1",
        "category": "project",
        "title": "Mitigate Apollo Sprint Delay",
        "observation": "Project Apollo velocity is 30% below historical baseline.",
        "why_it_matters": "Risk of missing critical milestone deadline in 5 days.",
        "potential_consequence": "Downstream release dependencies will be delayed.",
        "recommended_preventive_action": "Reallocate two engineers from completed sprint.",
        "urgency": "high",
        "requires_human_approval": True,
    }
    item = ExecutiveRecommendationItem.model_validate(valid_data)
    assert item.id == "rec-1"
    assert item.category == RecommendationCategory.PROJECT
    assert item.urgency == UrgencyLevel.HIGH
    assert item.requires_human_approval is True


def test_pydantic_validation_failure():
    # Missing required observation field
    invalid_data = {
        "id": "rec-2",
        "category": "invalid_category",
        "title": "Invalid Recommendation",
    }
    with pytest.raises(Exception):
        ExecutiveRecommendationItem.model_validate(invalid_data)


def test_deterministic_project_risk_schema_enforcement():
    # Valid deterministic risk item
    data = {
        "project_id": 1,
        "project_name": "Project Titan",
        "deterministic_risk_level": "medium",
        "deterministic_risk_score": 55.5,
        "primary_risk_factors": ["2 overdue tasks", "Upcoming sprint boundary"],
        "risk_explanation": "Titan is experiencing slight task drag due to dependency waits.",
        "potential_consequences": "Sprint may slip by 2 days.",
        "recommended_actions": ["Unblock dependency with Database team."],
    }
    item = ProjectRiskExplanationItem.model_validate(data)
    assert item.deterministic_risk_score == 55.5
    assert item.deterministic_risk_level == RiskLevel.MEDIUM

    # Risk score > 100 must fail validation
    with pytest.raises(Exception):
        bad_score = dict(data, deterministic_risk_score=105.0)
        ProjectRiskExplanationItem.model_validate(bad_score)


# --------------------------------------------------------------------------- #
# 4. Error Retryability & Daily Quota Detection Tests
# --------------------------------------------------------------------------- #

def test_retryable_vs_non_retryable_errors():
    # 503 is retryable
    assert is_retryable_error("503 Service Unavailable") is True
    assert is_retryable_error("The server is temporarily UNAVAILABLE") is True

    # Transient 429 is retryable
    assert is_retryable_error("429 Too Many Requests, retry in 3.0s") is True

    # Daily cap 429 is NOT retryable
    assert is_retryable_error("429 ResourceExhausted: quota exceeded PerDay") is False
    assert is_retryable_error("Daily quota exceeded for model") is False

    # Detection of hard daily exhaustion
    assert is_daily_quota_exhausted("ResourceExhausted: quota exceeded PerDay") is True
    assert is_daily_quota_exhausted("429 Too Many Requests") is False


# --------------------------------------------------------------------------- #
# 5. Mocked Gemini Execution, Retries, and Fast Quota Failure
# --------------------------------------------------------------------------- #

def test_gemini_client_mock_successful_generation():
    client = GeminiClient(api_key="test_api_key_123")

    mock_response = MagicMock()
    mock_response.text = '''```json
    {
      "id": "rec-mock-1",
      "category": "workload",
      "title": "Rebalance Team Workload",
      "observation": "Team Alpha has 12 tasks while Team Beta has 2.",
      "why_it_matters": "Alpha developers are at capacity.",
      "potential_consequence": "Burnout and delayed sprint deliverables.",
      "recommended_preventive_action": "Shift 3 tasks to Team Beta.",
      "urgency": "medium",
      "requires_human_approval": true
    }
    ```'''

    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.return_value = mock_response

    with patch.object(client, "_get_sdk_client", return_value=mock_sdk):
        result = client.generate_structured("Test prompt", ExecutiveRecommendationItem)
        assert result.id == "rec-mock-1"
        assert result.category == RecommendationCategory.WORKLOAD
        assert result.urgency == UrgencyLevel.MEDIUM


def test_gemini_client_retries_transient_error(monkeypatch):
    client = GeminiClient(api_key="test_api_key_123", max_retries=2)

    # First call raises 503, second succeeds
    fail_exc = Exception("503 Service Unavailable retry in 0.1s")
    success_resp = MagicMock()
    success_resp.text = '{"team_or_project": "Alpha", "bottleneck_severity": "low", "observation": "Balanced", "affected_roles": ["Dev"], "suggested_balancing_action": "Maintain"}'

    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.side_effect = [fail_exc, success_resp]

    # Speed up sleep in test
    monkeypatch.setattr(time, "sleep", lambda x: None)

    with patch.object(client, "_get_sdk_client", return_value=mock_sdk):
        res = client.generate_structured("Test prompt", WorkloadBottleneckItem)
        assert res.team_or_project == "Alpha"
        assert mock_sdk.models.generate_content.call_count == 2


def test_gemini_client_daily_quota_fails_fast():
    client = GeminiClient(api_key="test_api_key_123", max_retries=2)

    quota_exc = Exception("429 ResourceExhausted: quota exceeded PerDay")
    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.side_effect = quota_exc

    with patch.object(client, "_get_sdk_client", return_value=mock_sdk):
        with pytest.raises(AIQuotaError, match="daily quota exhausted"):
            client.generate_structured("Test prompt", WorkloadBottleneckItem)
        # Verify it failed fast on attempt 1 without retrying
        assert mock_sdk.models.generate_content.call_count == 1


# --------------------------------------------------------------------------- #
# 6. In-Memory Cache Tests (Hit, Miss, Expiration, Invalidation, Concurrency)
# --------------------------------------------------------------------------- #

def test_cache_hit_and_miss():
    cache = IntelligenceCache(default_ttl=60)
    assert cache.get("test_key") is None

    cache.set("test_key", {"status": "ok"})
    cached = cache.get("test_key")
    assert cached == {"status": "ok"}


def test_cache_expiration():
    cache = IntelligenceCache(default_ttl=1)  # 1 second TTL
    cache.set("short_key", "value_123", ttl=1)

    assert cache.get("short_key") == "value_123"
    time.sleep(1.05)
    assert cache.get("short_key") is None


def test_cache_invalidation():
    cache = IntelligenceCache(default_ttl=60)
    cache.set("proj:1", "p1")
    cache.set("proj:2", "p2")
    cache.set("other:key", "o1")

    # Invalidate single key
    cache.invalidate("proj:1")
    assert cache.get("proj:1") is None
    assert cache.get("proj:2") == "p2"

    # Invalidate scope prefix
    cache.invalidate_scope("proj:")
    assert cache.get("proj:2") is None
    assert cache.get("other:key") == "o1"

    # Clear all
    cache.clear()
    assert cache.get("other:key") is None


def test_cache_concurrent_duplicate_protection():
    cache = IntelligenceCache(default_ttl=60)
    eval_call_count = 0
    lock = threading.Lock()

    def expensive_evaluator():
        nonlocal eval_call_count
        with lock:
            eval_call_count += 1
        time.sleep(0.05)
        return {"result": 42}

    results = []

    def worker():
        res, is_cached = cache.get_or_evaluate("concurrent_key", expensive_evaluator)
        results.append((res, is_cached))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Evaluator must have executed strictly ONCE
    assert eval_call_count == 1
    assert len(results) == 5
    for res, _ in results:
        assert res == {"result": 42}


def test_cache_refresh_throttling():
    cache = IntelligenceCache(default_ttl=60)
    cache.set("throttle_key", "data")

    allowed, remaining = cache.check_refresh_throttle("throttle_key")
    assert allowed is False
    assert remaining > 0

    # Key that has never been evaluated can refresh
    allowed_new, rem_new = cache.check_refresh_throttle("never_seen_key")
    assert allowed_new is True
    assert rem_new == 0.0
