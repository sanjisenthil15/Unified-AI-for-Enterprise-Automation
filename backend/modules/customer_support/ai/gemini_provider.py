"""
modules/customer_support/ai/gemini_provider.py

Pre-trained Google Gemini AI Provider for Grounded Enterprise Customer Support.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from config.settings import settings
from modules.customer_support.ai.base import BaseAIProvider
from modules.customer_support.schemas import (
    CitationItem,
    GroundedAIResponse,
    SearchResultItem,
    SourceItem,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI integration using pre-trained Gemini models."""

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name

    @property
    def provider_name(self) -> str:
        return f"Google Gemini ({self.model_name})"

    def is_available(self) -> bool:
        """Checks if GEMINI_API_KEY is configured."""
        key = getattr(settings, "GEMINI_API_KEY", "")
        return bool(key and key.strip() and key.strip() != "YOUR_GEMINI_API_KEY")

    def _build_prompt(
        self,
        query: str,
        history: List[Dict[str, str]],
        context_chunks: List[SearchResultItem],
        intent: Optional[object] = None,
    ) -> str:
        """Builds strict grounding prompt."""
        history_str = ""
        if history:
            history_str = "Conversation History (most recent turns):\n"
            for turn in history[-6:]:
                role = "Customer" if turn.get("role") == "customer" else "Assistant"
                history_str += f"- {role}: {turn.get('text', '')}\n"

        chunks_str = ""
        for idx, c in enumerate(context_chunks, 1):
            chunks_str += (
                f"[Verified Knowledge Source #{idx}]\n"
                f"Document Title: {c.document_title}\n"
                f"Category: {c.category_name or 'General'}\n"
                f"Excerpt: {c.chunk_text}\n\n"
            )

        intent_details = ""
        if intent:
            cat = getattr(intent, "detected_category", "General Support & SLA")
            team = getattr(intent, "assigned_team", "General Customer Support Team")
            itype = getattr(intent, "intent_type", "GENERAL_INQUIRY")
            intent_details = f"Detected Support Domain: {itype}\nTarget Support Category: {cat}\nAssigned Team: {team}\n"

        return f"""You are the Enterprise AI Customer Support Assistant for Unified AI Enterprise 2.0.
Your responsibility is to assist customers accurately, professionally, and strictly based on verified enterprise knowledge.

ZERO-HALLUCINATION POLICY & GROUNDING RULES:
1. ONLY state facts, policies, refund periods, SLAs, recharge/activation terms, and troubleshooting steps that are explicitly supported by the verified knowledge sources below.
2. NEVER fabricate or assume refund rules, pricing, SLAs, security policies, or account procedures.
3. The AI assistant must generate a natural, helpful, professional response and must NOT blindly copy-paste entire document blocks verbatim.
4. If the user question is out-of-scope (e.g. general trivia, weather, sports, unrelated topics), politely state:
   "I can assist with enterprise platform products, billing, account security, and technical support. This question is outside the supported knowledge base."
   Set answerable=false, confidence=0.10, escalation_recommended=false.
5. If the verified knowledge sources DO NOT contain sufficient information to answer the question, state that the verified knowledge base does not contain enough information, and offer to escalate to a specialist or create a ticket. Set answerable=false, escalation_recommended=true.
6. In multi-turn conversations, understand co-references (such as 'it', 'that issue', 'the money', 'my recharge') referring to previous turns.
7. Provide 2-3 helpful recommended action steps in `suggested_actions`.

{intent_details}
{history_str}
Verified Knowledge Sources:
{chunks_str if chunks_str else "No matching verified articles found in enterprise knowledge base."}

Customer Inquiry: "{query}"

Output strictly a valid JSON object matching this schema:
{{
  "answer": "string (formatted with professional markdown)",
  "answerable": boolean,
  "confidence": float (between 0.0 and 1.0),
  "detected_category": "string (Billing & Payments, Account & Security, Technical Support, Subscriptions & Invoicing, UI & Troubleshooting, General Support & SLA, Account & Profile Management, Products & Services, or Orders, Requests & Service Issues)",
  "assigned_team": "string (Billing & Finance Support Team, Account & Security Support Team, Backend & API Support Team, Subscription & Invoicing Team, Frontend & UI Support Team, General Customer Support Team, Account & Profile Operations Team, Product & Solutions Specialist Team, or Orders & Service Operations Team)",
  "escalation_recommended": boolean,
  "escalation_reason": "string or null",
  "suggested_actions": ["string"],
  "clarification_options": ["string"]
}}
"""

    def generate_response(
        self,
        query: str,
        history: List[Dict[str, str]],
        context_chunks: List[SearchResultItem],
        session_id: Optional[str] = None,
        intent: Optional[object] = None,
    ) -> Optional[GroundedAIResponse]:
        # 1. Handle Conversational Greeting & Thanks directly (Zero KB Retrieval)
        if intent and getattr(intent, "is_conversational", False):
            itype = getattr(intent, "intent_type", "")
            if itype == "GREETING":
                return GroundedAIResponse(
                    success=True,
                    answer="Hi! 👋 How can I help you today with your enterprise account, billing, recharge, API services, or support inquiries?",
                    confidence=0.99,
                    is_grounded=True,
                    is_escalated=False,
                    citations=[],
                    sources=[],
                    detected_category="General Support & SLA",
                    assigned_team="General Customer Support Team",
                    escalation_recommended=False,
                    escalation_reason=None,
                    suggested_actions=["Recharge / Plan Help", "Reset Account Password", "Troubleshoot 500 Error", "Service Status"],
                    clarification_options=[],
                    conversation_id=session_id,
                    ai_provider=self.provider_name,
                    response_type="CONVERSATIONAL",
                )
            elif itype == "THANKS":
                return GroundedAIResponse(
                    success=True,
                    answer="You're very welcome! 😊 Is there anything else I can help you with today? Feel free to ask about your services, billing, or open tickets.",
                    confidence=0.99,
                    is_grounded=True,
                    is_escalated=False,
                    citations=[],
                    sources=[],
                    detected_category="General Support & SLA",
                    assigned_team="General Customer Support Team",
                    escalation_recommended=False,
                    escalation_reason=None,
                    suggested_actions=["View My Tickets", "Browse Knowledge Base", "Service Status"],
                    clarification_options=[],
                    conversation_id=session_id,
                    ai_provider=self.provider_name,
                    response_type="CONVERSATIONAL",
                )
            elif itype == "GOODBYE" or itype == "CLOSING":
                return GroundedAIResponse(
                    success=True,
                    answer="Goodbye! 👋 Thank you for contacting Enterprise Customer Support. Have a wonderful day, and reach out anytime you need assistance!",
                    confidence=0.99,
                    is_grounded=True,
                    is_escalated=False,
                    citations=[],
                    sources=[],
                    detected_category="General Support & SLA",
                    assigned_team="General Customer Support Team",
                    escalation_recommended=False,
                    escalation_reason=None,
                    suggested_actions=["Open New Chat", "View Ticket Status"],
                    clarification_options=[],
                    conversation_id=session_id,
                    ai_provider=self.provider_name,
                    response_type="CONVERSATIONAL",
                )
            elif itype == "CASUAL_CONVERSATION":
                return GroundedAIResponse(
                    success=True,
                    answer="I'm doing well, thank you for asking! 😊 As your Enterprise AI Customer Support Assistant, I'm fully operational and ready to help you with account security, billing, plan activations, API troubleshooting, and service tracking. How can I assist you today?",
                    confidence=0.99,
                    is_grounded=True,
                    is_escalated=False,
                    citations=[],
                    sources=[],
                    detected_category="General Support & SLA",
                    assigned_team="General Customer Support Team",
                    escalation_recommended=False,
                    escalation_reason=None,
                    suggested_actions=["What can you help me with?", "What is the refund policy?", "Is the API down?"],
                    clarification_options=[],
                    conversation_id=session_id,
                    ai_provider=self.provider_name,
                    response_type="CONVERSATIONAL",
                )
            elif itype == "CAPABILITY":
                return GroundedAIResponse(
                    success=True,
                    answer=(
                        "I can assist you with a comprehensive range of enterprise customer services:\n\n"
                        "• **💳 Billing & Payments:** Refund eligibility & procedures, duplicate charges, payment reconciliation, and invoices.\n"
                        "• **🔐 Account & Security:** Password resets, 2FA/MFA setup, account lockout recovery, and active session management.\n"
                        "• **⚙️ Technical & APIs:** Diagnostic steps for HTTP 500/404/401 errors, rate limits, timeouts, and backend troubleshooting.\n"
                        "• **📦 Subscriptions & Plans:** Plan upgrades, renewals, ₹999 recharge activations, and feature tier entitlements.\n"
                        "• **🟢 Service Status & Incidents:** Real-time operational uptime telemetry and incident updates.\n"
                        "• **🎫 Support Requests & SLAs:** Guided multi-step request creation, duplicate checking, and human specialist escalation.\n\n"
                        "What topic would you like to explore?"
                    ),
                    confidence=0.99,
                    is_grounded=True,
                    is_escalated=False,
                    citations=[],
                    sources=[],
                    detected_category="General Support & SLA",
                    assigned_team="General Customer Support Team",
                    escalation_recommended=False,
                    escalation_reason=None,
                    suggested_actions=["What is the refund period?", "How do I reset my password?", "Is the API down?", "Report a payment issue"],
                    clarification_options=[],
                    conversation_id=session_id,
                    ai_provider=self.provider_name,
                    response_type="CONVERSATIONAL",
                )

        if not self.is_available():
            return None

        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY.strip())
            model = genai.GenerativeModel(self.model_name)
            prompt = self._build_prompt(query, history, context_chunks, intent=intent)
            resp = model.generate_content(prompt)
            raw_text = resp.text.strip()

            # Clean markdown code fences if wrapped in ```json ... ```
            cleaned_json = re.sub(r"^```[a-z]*\n?|```$", "", raw_text, flags=re.MULTILINE).strip()
            data = json.loads(cleaned_json)

            citations: List[CitationItem] = []
            sources: List[SourceItem] = []
            for c in context_chunks[:3]:
                citations.append(
                    CitationItem(
                        document_id=c.document_id,
                        document_title=c.document_title,
                        chunk_id=c.chunk_id,
                        excerpt=c.chunk_text[:300] + ("..." if len(c.chunk_text) > 300 else ""),
                    )
                )
                sources.append(
                    SourceItem(
                        document_id=str(c.document_id),
                        document_title=c.document_title,
                        chunk_id=str(c.chunk_id),
                        excerpt=c.chunk_text[:300] + ("..." if len(c.chunk_text) > 300 else ""),
                    )
                )

            is_ans = bool(data.get("answerable", True))
            confidence_val = float(data.get("confidence", 0.92))
            is_esc = bool(data.get("escalation_recommended", False))

            return GroundedAIResponse(
                success=True,
                answer=data.get("answer", ""),
                confidence=confidence_val,
                is_grounded=is_ans and len(context_chunks) > 0,
                is_escalated=is_esc,
                citations=citations if is_ans else [],
                sources=sources if is_ans else [],
                detected_category=data.get("detected_category", "General Support & SLA"),
                assigned_team=data.get("assigned_team", "General Customer Support Team"),
                escalation_recommended=is_esc,
                escalation_reason=data.get("escalation_reason"),
                suggested_actions=data.get("suggested_actions", []),
                clarification_options=data.get("clarification_options", []),
                conversation_id=session_id,
                ai_provider=self.provider_name,
            )
        except Exception as exc:
            logger.warning(f"GeminiProvider generation failed ({exc}), falling back to deterministic engine.")
            return None
