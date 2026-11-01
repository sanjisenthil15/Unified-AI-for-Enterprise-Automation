"""
modules/intelligence/__init__.py

AI-Powered Enterprise Intelligence Module.
Exports:
  - Gemini AI Client & Exception Hierarchy
  - Thread-Safe In-Memory TTL Cache
  - Foundational Response Schemas
  - Submodule 3.2 Intelligence Services & Deterministic Calculation Engines
"""

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
from modules.intelligence.cache import (
    DEFAULT_TTL_SECONDS,
    IntelligenceCache,
    intelligence_cache,
)
from modules.intelligence.schemas import (
    AIMetadata,
    BottleneckSeverity,
    DelayStatus,
    ExecutiveRecommendationItem,
    ExecutiveSummaryResponse,
    OperationsInsightsResponse,
    ProjectRiskExplanationItem,
    ProjectRiskIntelligenceResponse,
    RecommendationCategory,
    RefreshRequest,
    RefreshResponse,
    RiskLevel,
    SprintDelayExplanationItem,
    SprintDelayIntelligenceResponse,
    UrgencyLevel,
    WorkloadBottleneckItem,
    WorkloadIntelligenceResponse,
)
from modules.intelligence.router import router
from modules.intelligence.service import (
    anonymize_workload_records,
    classify_sprint_delay,
    compute_deterministic_project_risk,
    get_executive_recommendations,
    get_incident_insights,
    get_operations_insights,
    get_project_risk_insights,
    get_sprint_delay_insights,
    get_support_insights,
    get_workload_bottleneck_insights,
    sanitize_incident_data_for_ai,
    sanitize_support_data_for_ai,
)

__all__ = [
    # AI Client
    "AIClientError",
    "AIConfigError",
    "AIParseError",
    "AIQuotaError",
    "AIValidationError",
    "GeminiClient",
    "is_daily_quota_exhausted",
    "is_retryable_error",
    "strip_markdown_fences",
    # Cache
    "DEFAULT_TTL_SECONDS",
    "IntelligenceCache",
    "intelligence_cache",
    # Schemas
    "AIMetadata",
    "BottleneckSeverity",
    "DelayStatus",
    "ExecutiveRecommendationItem",
    "ExecutiveSummaryResponse",
    "OperationsInsightsResponse",
    "ProjectRiskExplanationItem",
    "ProjectRiskIntelligenceResponse",
    "RecommendationCategory",
    "RiskLevel",
    "SprintDelayExplanationItem",
    "SprintDelayIntelligenceResponse",
    "UrgencyLevel",
    "WorkloadBottleneckItem",
    "WorkloadIntelligenceResponse",
    # Service Functions
    "anonymize_workload_records",
    "classify_sprint_delay",
    "compute_deterministic_project_risk",
    "get_executive_recommendations",
    "get_incident_insights",
    "get_operations_insights",
    "get_project_risk_insights",
    "get_sprint_delay_insights",
    "get_support_insights",
    "get_workload_bottleneck_insights",
    "sanitize_incident_data_for_ai",
    "sanitize_support_data_for_ai",
]
