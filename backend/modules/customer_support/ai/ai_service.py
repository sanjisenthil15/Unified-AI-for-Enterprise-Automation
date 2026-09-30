"""
modules/customer_support/ai/ai_service.py

Modular AI Orchestration Service for Enterprise Customer Support.
Coordinates Primary (Gemini) and Secondary (Deterministic Fallback) AI Providers.
"""

import logging
import time
from typing import Dict, List, Optional

from modules.customer_support.ai.base import BaseAIProvider
from modules.customer_support.ai.deterministic_provider import DeterministicFallbackProvider
from modules.customer_support.ai.gemini_provider import GeminiProvider
from modules.customer_support.schemas import GroundedAIResponse, SearchResultItem

logger = logging.getLogger(__name__)


class AIService:
    """
    Central AI Manager for Customer Support.
    Provides a decoupled, resilient interface for generating grounded responses.
    """

    def __init__(
        self,
        primary_provider: Optional[BaseAIProvider] = None,
        fallback_provider: Optional[BaseAIProvider] = None,
    ):
        self.primary_provider = primary_provider or GeminiProvider()
        self.fallback_provider = fallback_provider or DeterministicFallbackProvider()

    def generate_grounded_response(
        self,
        query: str,
        history: List[Dict[str, str]],
        context_chunks: List[SearchResultItem],
        session_id: Optional[str] = None,
        intent: Optional[object] = None,
    ) -> GroundedAIResponse:
        """
        Generates a grounded response by trying the primary provider first,
        and falling back to the deterministic provider if unavailable or failed.
        """
        start_time = time.perf_counter()
        response: Optional[GroundedAIResponse] = None

        # 1. Attempt Primary Provider (e.g. Gemini)
        if self.primary_provider.is_available():
            try:
                logger.info(f"Dispatching query to primary AI provider: {self.primary_provider.provider_name}")
                response = self.primary_provider.generate_response(
                    query=query,
                    history=history,
                    context_chunks=context_chunks,
                    session_id=session_id,
                    intent=intent,
                )
            except Exception as exc:
                logger.warning(f"Primary AI provider failed with exception: {exc}")
                response = None

        # 2. Fallback to Deterministic Provider
        if not response:
            logger.info(f"Using fallback AI provider: {self.fallback_provider.provider_name}")
            response = self.fallback_provider.generate_response(
                query=query,
                history=history,
                context_chunks=context_chunks,
                session_id=session_id,
                intent=intent,
            )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        response.processing_time_ms = max(1, elapsed_ms)
        if session_id:
            response.conversation_id = session_id

        logger.info(
            f"[AI Service] Session: {session_id} | Provider: {response.ai_provider} | "
            f"Confidence: {int(response.confidence * 100)}% | Chunks: {len(context_chunks)} | "
            f"Elapsed: {elapsed_ms}ms"
        )
        return response


# Global singleton instance
ai_service = AIService()
