"""
modules/customer_support/ai/base.py

Abstract Base Class for Customer Support AI Provider implementations.
All providers (Gemini, Deterministic Fallback, future LLMs) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from modules.customer_support.schemas import GroundedAIResponse, SearchResultItem


class BaseAIProvider(ABC):
    """Abstract interface defining the AI model provider contract."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable identifier of the AI provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is configured and reachable."""
        pass

    @abstractmethod
    def generate_response(
        self,
        query: str,
        history: List[Dict[str, str]],
        context_chunks: List[SearchResultItem],
        session_id: Optional[str] = None,
        intent: Optional[object] = None,
    ) -> Optional[GroundedAIResponse]:
        """
        Generates a grounded, factual response based on retrieved enterprise knowledge.

        Args:
            query: The customer inquiry text.
            history: Previous conversation turns [{"role": "customer"|"ai", "text": "..."}].
            context_chunks: Ranked list of retrieved knowledge base chunks from BM25.
            session_id: Optional chat session ID.
            intent: Optional detected query IntentResult.

        Returns:
            GroundedAIResponse object if successful, or None if generation failed.
        """
        pass
