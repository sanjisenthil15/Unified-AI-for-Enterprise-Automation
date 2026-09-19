"""
modules/customer_support/intent.py

Enterprise Intent Classification & Domain Routing Engine.
Determines customer inquiry domain, identifies conversational intents (greetings, thanks,
closings, casual talk, capability queries), handles multi-turn conversational context propagation,
and enforces strict category routing boundaries for verified enterprise RAG.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class IntentResult:
    intent_type: str
    detected_category: str
    assigned_team: str
    is_conversational: bool
    is_out_of_scope: bool
    preferred_categories: List[str] = field(default_factory=list)
    forbidden_categories: List[str] = field(default_factory=list)
    boost_terms: List[str] = field(default_factory=list)
    confidence: float = 0.90
    suggested_response_type: str = "NORMAL_ANSWER"  # CONVERSATIONAL, SERVICE_STATUS, TICKET_ACTION, NORMAL_ANSWER, ESCALATION, CLARIFICATION


# =============================================================================
# 1. CONVERSATIONAL PATTERNS (STRICT ZERO KB RETRIEVAL)
# =============================================================================

GREETING_TOKENS = r"(hi|hello|hey|heya|howdy|hola|greetings|good\s+(morning|afternoon|evening|day))"

GREETING_PATTERNS = [
    rf"^({GREETING_TOKENS}(\s+there|\s+bot|\s+assistant|\s+support|\s+team|[!.,\s]*)+)$",
    rf"^{GREETING_TOKENS}([!.,\s]+{GREETING_TOKENS})*([!.,\s]+(there|bot|assistant|support|team))?[\s!?.]*$",
    rf"^{GREETING_TOKENS}(\s+there)?[!.,\s]+(how\s+are\s+you|how\s+are\s+you\s+doing|hope\s+you\s+are\s+well|how['’]?s\s+it\s+going|what['’]?s\s+up)(\s+today)?[\s!?.]*$",
]

THANKS_PATTERNS = [
    r"^(thanks|thank\s+you|thx|many\s+thanks|great\s+thanks|appreciate\s+it|much\s+appreciated|you['’]?re\s+(very\s+)?helpful|you\s+are\s+(so\s+)?helpful)(\s+(so\s+much|very\s+much|a\s+lot|a\s+ton|kindly))?(\s+for\s+(all\s+)?(the\s+)?(help|support|assistance|everything|answering|clarifying))?[\s!?.]*$",
]

CLOSING_PATTERNS = [
    r"^(bye|goodbye|see\s+you|cya|have\s+a\s+nice\s+day|have\s+a\s+good\s+one|take\s+care|good\s+night)(\s+for\s+now)?[\s!?.]*$",
]

CASUAL_CONVERSATION_PATTERNS = [
    r"^(how\s+are\s+you|how\s+are\s+you\s+doing|how\s+is\s+it\s+going|how['’]?s\s+it\s+going|what['’]?s\s+up|what\s+is\s+up|who\s+are\s+you|what\s+is\s+your\s+name|are\s+you\s+(an\s+)?ai|are\s+you\s+(a\s+)?bot|nice\s+to\s+meet\s+you|tell\s+me\s+about\s+yourself)(\s+today)?[\s!?.]*$",
]

CAPABILITY_PATTERNS = [
    r"^(what\s+can\s+you\s+help\s+(me\s+)?with|what\s+can\s+you\s+do|what\s+are\s+your\s+capabilities|can\s+you\s+help\s+me|how\s+can\s+you\s+help\s+me|what\s+support\s+do\s+you\s+provide|what\s+services\s+do\s+you\s+support|help\s+me|i\s+need\s+help|what\s+are\s+your\s+features)[\s!?.]*$",
]

# Out-of-Scope Keywords (General non-enterprise trivia)
OUT_OF_SCOPE_TERMS = [
    "weather", "forecast", "tomorrow", "sports", "football", "cricket",
    "movie", "president", "who won", "recipe", "capital of", "joke", "song", "lyrics"
]

ENTERPRISE_SIGNALS = [
    "refund", "payment", "recharge", "subscription", "plan", "scheme", "api", "ticket",
    "sla", "password", "login", "auth", "2fa", "billing", "server", "500", "404", "401",
    "dashboard", "cache", "token", "invoice", "receipt", "account", "service", "support",
    "outage", "status", "incident", "down", "operational", "latency", "mfa"
]


def detect_query_intent(query: str, history: Optional[List[Dict[str, str]]] = None) -> IntentResult:
    """
    Classifies the user query into a primary support domain with high precision.
    Enforces a strict RAG Gate: Conversational messages bypass KB retrieval entirely.
    Incorporates conversational context for multi-turn pronoun/concept resolution.
    """
    cleaned = query.lower().strip()
    
    # -------------------------------------------------------------------------
    # 1. CONVERSATIONAL GREETINGS (Zero KB Retrieval)
    # -------------------------------------------------------------------------
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return IntentResult(
                intent_type="GREETING",
                detected_category="General Support & SLA",
                assigned_team="General Customer Support Team",
                is_conversational=True,
                is_out_of_scope=False,
                preferred_categories=[],
                forbidden_categories=[],
                boost_terms=[],
                confidence=0.99,
                suggested_response_type="CONVERSATIONAL",
            )

    # -------------------------------------------------------------------------
    # 2. CONVERSATIONAL THANKS (Zero KB Retrieval)
    # -------------------------------------------------------------------------
    for pattern in THANKS_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return IntentResult(
                intent_type="THANKS",
                detected_category="General Support & SLA",
                assigned_team="General Customer Support Team",
                is_conversational=True,
                is_out_of_scope=False,
                preferred_categories=[],
                forbidden_categories=[],
                boost_terms=[],
                confidence=0.99,
                suggested_response_type="CONVERSATIONAL",
            )

    # -------------------------------------------------------------------------
    # 3. CONVERSATIONAL CLOSINGS / GOODBYE (Zero KB Retrieval)
    # -------------------------------------------------------------------------
    for pattern in CLOSING_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return IntentResult(
                intent_type="GOODBYE",
                detected_category="General Support & SLA",
                assigned_team="General Customer Support Team",
                is_conversational=True,
                is_out_of_scope=False,
                preferred_categories=[],
                forbidden_categories=[],
                boost_terms=[],
                confidence=0.99,
                suggested_response_type="CONVERSATIONAL",
            )

    # -------------------------------------------------------------------------
    # 4. CASUAL CONVERSATION (Zero KB Retrieval)
    # -------------------------------------------------------------------------
    for pattern in CASUAL_CONVERSATION_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return IntentResult(
                intent_type="CASUAL_CONVERSATION",
                detected_category="General Support & SLA",
                assigned_team="General Customer Support Team",
                is_conversational=True,
                is_out_of_scope=False,
                preferred_categories=[],
                forbidden_categories=[],
                boost_terms=[],
                confidence=0.98,
                suggested_response_type="CONVERSATIONAL",
            )

    # -------------------------------------------------------------------------
    # 5. CAPABILITY QUERY (Zero KB Retrieval)
    # -------------------------------------------------------------------------
    for pattern in CAPABILITY_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return IntentResult(
                intent_type="CAPABILITY",
                detected_category="General Support & SLA",
                assigned_team="General Customer Support Team",
                is_conversational=True,
                is_out_of_scope=False,
                preferred_categories=[],
                forbidden_categories=[],
                boost_terms=[],
                confidence=0.98,
                suggested_response_type="CONVERSATIONAL",
            )

    # -------------------------------------------------------------------------
    # 6. OUT-OF-SCOPE TRIVIA CHECK
    # -------------------------------------------------------------------------
    if any(term in cleaned for term in OUT_OF_SCOPE_TERMS) and not any(sig in cleaned for sig in ENTERPRISE_SIGNALS):
        return IntentResult(
            intent_type="OUT_OF_SCOPE",
            detected_category="General Support & SLA",
            assigned_team="General Customer Support Team",
            is_conversational=False,
            is_out_of_scope=True,
            preferred_categories=[],
            forbidden_categories=[],
            boost_terms=[],
            confidence=0.95,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # Extract historical context for multi-turn co-reference
    # -------------------------------------------------------------------------
    prev_cust_context = ""
    if history:
        for turn in history[-4:]:
            role = turn.get("role") or turn.get("sender_type") or ""
            text = (turn.get("text") or turn.get("message") or turn.get("content") or "").lower()
            if role in ["customer", "user"]:
                prev_cust_context += " " + text

    has_prev_recharge = any(k in prev_cust_context for k in ["recharge", "recharged", "999", "plan", "scheme", "data"])
    has_prev_refund = any(k in prev_cust_context for k in ["refund", "return", "cancellation", "purchased", "bought"])
    has_prev_api = any(k in prev_cust_context for k in ["500", "api", "backend", "endpoint", "404", "401"])
    has_prev_status = any(k in prev_cust_context for k in ["status", "down", "outage", "incident", "operational", "server down"])

    # -------------------------------------------------------------------------
    # 7. SERVICE STATUS & OUTAGE / INCIDENT INQUIRIES
    # -------------------------------------------------------------------------
    status_triggers = [
        "is the api down", "is api down", "is the server down", "is server down",
        "are payments working", "are payments down", "is billing unavailable", "is billing down",
        "is there an outage", "service outage", "current outage", "is system down",
        "is authentication down", "auth down", "is customer portal down", "service status",
        "system status", "server status", "any incident", "incident report", "active incidents",
        "are services operational", "operational status", "system health", "is anything down",
        "payment gateway down", "gateway down", "gateway operational", "payment gateway operational",
        "is the system down", "system or payment", "are servers down", "is platform down"
    ]
    is_status_query = any(t in cleaned for t in status_triggers) or (
        any(s in cleaned for s in ["api", "server", "system", "payment gateway", "gateway", "platform", "service", "billing", "database"])
        and any(w in cleaned for w in ["down", "outage", "operational", "status", "offline", "degraded", "slow", "incident", "up and running"])
    ) or (
        any(k in cleaned for k in ["is it down", "still down", "any outage", "is it working"]) and has_prev_status
    )
    if is_status_query:
        return IntentResult(
            intent_type="SERVICE_STATUS",
            detected_category="Technical Support",
            assigned_team="Backend & API Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Technical Support", "General Support & SLA"],
            forbidden_categories=["Frontend & UI", "Account & Profile Management"],
            boost_terms=["status", "operational", "outage", "incident", "api", "billing", "auth", "health"],
            confidence=0.98,
            suggested_response_type="SERVICE_STATUS",
        )

    # -------------------------------------------------------------------------
    # 8. SUPPORT REQUEST CREATION / TICKET WORKFLOW TRIGGER
    # -------------------------------------------------------------------------
    ticket_creation_triggers = [
        "i want to report a payment problem", "report a payment issue", "report a payment problem",
        "report an issue", "report a bug", "create a support request", "submit a support request",
        "create a ticket", "open a ticket", "i want to create a ticket", "raise a ticket",
        "submit a ticket", "open a new request", "create a new request", "file a complaint",
        "file a ticket", "request human agent handoff", "talk to human agent", "talk to agent"
    ]
    if any(t in cleaned for t in ticket_creation_triggers):
        return IntentResult(
            intent_type="SUPPORT_REQUEST",
            detected_category="Orders, Requests & Service Issues",
            assigned_team="Orders & Service Operations Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Orders, Requests & Service Issues", "General Support & SLA"],
            forbidden_categories=[],
            boost_terms=["request", "ticket", "create", "support", "agent", "escalation"],
            confidence=0.97,
            suggested_response_type="TICKET_ACTION",
        )

    # -------------------------------------------------------------------------
    # 9. RECHARGE / DATA SCHEME / PLAN ACTIVATION DISPUTE
    # -------------------------------------------------------------------------
    recharge_triggers = [
        "recharge", "recharged", "data scheme", "data plan", "scheme", "not activated", "was not activated",
        "hasn't activated", "has not activated", "didn't happen", "did not happen", "money deducted", "amount deducted",
        "money got deducted", "payment deducted", "paid 999", "999", "payment went through", "service is not active",
        "service not active", "service not activated", "plan not activated", "pack not active", "charged twice",
        "charged 2 times", "double charge", "duplicate charge", "payment declined", "payment pending", "inactive after payment",
        "subscription inactive", "deducted but", "paid but", "charged but", "plan is not active", "plan is still not active"
    ]
    is_recharge_query = any(t in cleaned for t in recharge_triggers) or (
        any(k in cleaned for k in ["money", "deducted", "deduct", "paid", "amount", "plan", "active"]) and has_prev_recharge
    )
    if is_recharge_query:
        return IntentResult(
            intent_type="RECHARGE",
            detected_category="Subscriptions & Invoicing" if any(w in cleaned for w in ["subscription", "plan", "scheme", "activated", "inactive", "recharge", "active"]) else "Billing & Payments",
            assigned_team="Subscription & Invoicing Team" if any(w in cleaned for w in ["subscription", "plan", "scheme", "activated", "inactive", "recharge", "active"]) else "Billing & Finance Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Subscriptions & Invoicing", "Billing & Payments"],
            forbidden_categories=["Frontend & UI", "Account & Security", "Technical Support", "Account & Profile Management"],
            boost_terms=["recharge", "activation", "activated", "scheme", "plan", "deducted", "subscription", "payment", "reconciliation", "webhook", "999"],
            confidence=0.98,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 10. REFUND & CANCELLATION
    # -------------------------------------------------------------------------
    refund_triggers = [
        "refund", "refund period", "refund policy", "return policy", "money back", "get my money back",
        "cancellation", "cancel subscription", "cancel payment", "return payment", "reimbursement",
        "eligible refund", "refund after"
    ]
    is_refund_query = any(t in cleaned for t in refund_triggers) or (
        any(w in cleaned for w in ["10 days", "15 days", "20 days", "30 days", "bought it", "purchased it"]) and has_prev_refund
    )
    if is_refund_query:
        return IntentResult(
            intent_type="REFUND",
            detected_category="Billing & Payments",
            assigned_team="Billing & Finance Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Billing & Payments"],
            forbidden_categories=["Frontend & UI", "Technical Support", "Account & Security"],
            boost_terms=["refund", "policy", "cancellation", "30", "days", "reimbursement", "eligibility"],
            confidence=0.98,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 11. BILLING & PAYMENT GENERAL
    # -------------------------------------------------------------------------
    billing_triggers = [
        "payment failed", "payment declined", "pending payment", "payment method", "update billing",
        "invoice download", "download invoice", "view invoices", "payment receipt", "receipt download",
        "charged incorrectly", "invoice amount"
    ]
    if any(t in cleaned for t in billing_triggers):
        return IntentResult(
            intent_type="BILLING_PAYMENT",
            detected_category="Billing & Payments",
            assigned_team="Billing & Finance Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Billing & Payments", "Subscriptions & Invoicing"],
            forbidden_categories=["Frontend & UI", "Technical Support", "Account & Security"],
            boost_terms=["billing", "payment", "invoice", "receipt", "charge", "card", "declined", "pending"],
            confidence=0.96,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 12. PASSWORD & ACCOUNT ACCESS
    # -------------------------------------------------------------------------
    password_triggers = [
        "password", "reset password", "forgot password", "change password", "account is locked",
        "account locked", "lockout", "how do i reset my password", "can't login", "cannot login"
    ]
    if any(t in cleaned for t in password_triggers):
        return IntentResult(
            intent_type="PASSWORD",
            detected_category="Account & Security",
            assigned_team="Account & Security Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Account & Security"],
            forbidden_categories=["Billing & Payments", "Frontend & UI", "Technical Support", "Subscriptions & Invoicing"],
            boost_terms=["password", "reset", "forgot", "lockout", "login", "recovery", "link"],
            confidence=0.98,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 13. SECURITY & 2FA / SESSIONS
    # -------------------------------------------------------------------------
    security_triggers = [
        "2fa", "mfa", "two-factor", "authenticator", "backup code", "backup codes",
        "unauthorized access", "active sessions", "sign out from other devices", "connected devices",
        "security settings"
    ]
    if any(t in cleaned for t in security_triggers):
        return IntentResult(
            intent_type="SECURITY",
            detected_category="Account & Security",
            assigned_team="Account & Security Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Account & Security"],
            forbidden_categories=["Billing & Payments", "Frontend & UI", "Technical Support"],
            boost_terms=["2fa", "mfa", "authenticator", "security", "sessions", "devices", "backup"],
            confidence=0.97,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 14. TECHNICAL SUPPORT & BACKEND APIS
    # -------------------------------------------------------------------------
    technical_triggers = [
        "500", "500 error", "http 500", "404", "http 404", "401", "http 401", "unauthorized error",
        "internal server error", "api failing", "api error", "backend error", "server error",
        "api request failing", "api timeout", "failed request", "api returning", "rate limit",
        "rest api", "endpoint", "slow loading", "service unavailable", "application loading slowly"
    ]
    if any(t in cleaned for t in technical_triggers) or (
        any(k in cleaned for k in ["timeout", "server", "failing", "error"]) and has_prev_api
    ):
        return IntentResult(
            intent_type="TECHNICAL_API",
            detected_category="Technical Support",
            assigned_team="Backend & API Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Technical Support"],
            forbidden_categories=["Billing & Payments", "Subscriptions & Invoicing", "Account & Profile Management"],
            boost_terms=["500", "api", "404", "401", "timeout", "request", "error", "server", "rate", "limit"],
            confidence=0.97,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 15. FRONTEND UI & DASHBOARD TROUBLESHOOTING
    # -------------------------------------------------------------------------
    ui_triggers = [
        "dashboard button", "dashboard buttons", "buttons are not responding", "button not responding",
        "clear browser cache", "clear cache", "browser cache", "hard refresh", "ctrl + f5", "ctrl f5",
        "page not loading", "buttons disabled", "interface displaying incorrectly", "browsers are supported",
        "supported browsers", "logged out unexpectedly", "unresponsive dashboard", "dashboard is not responding"
    ]
    if any(t in cleaned for t in ui_triggers):
        return IntentResult(
            intent_type="FRONTEND_UI",
            detected_category="UI & Troubleshooting",
            assigned_team="Frontend & UI Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["UI & Troubleshooting"],
            forbidden_categories=["Billing & Payments", "Subscriptions & Invoicing", "Account & Security", "Technical Support"],
            boost_terms=["dashboard", "button", "cache", "refresh", "browser", "unresponsive", "cookies", "chrome"],
            confidence=0.97,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 16. GENERAL SUPPORT & SLA
    # -------------------------------------------------------------------------
    sla_triggers = [
        "support hours", "operating hours", "what is the sla", "sla for critical", "sla for high",
        "priority support", "escalate a support issue", "ticket status", "support priorities",
        "sla commitment", "response time"
    ]
    if any(t in cleaned for t in sla_triggers):
        return IntentResult(
            intent_type="SLA",
            detected_category="General Support & SLA",
            assigned_team="General Customer Support Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["General Support & SLA"],
            forbidden_categories=[],
            boost_terms=["hours", "sla", "critical", "priority", "escalation", "support", "agreement"],
            confidence=0.96,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 17. SUBSCRIPTION MANAGEMENT
    # -------------------------------------------------------------------------
    sub_triggers = [
        "upgrade subscription", "downgrade subscription", "cancel subscription",
        "renew subscription", "when will my subscription renew", "reactivate subscription"
    ]
    if any(t in cleaned for t in sub_triggers):
        return IntentResult(
            intent_type="SUBSCRIPTION",
            detected_category="Subscriptions & Invoicing",
            assigned_team="Subscription & Invoicing Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Subscriptions & Invoicing"],
            forbidden_categories=["Frontend & UI", "Account & Security"],
            boost_terms=["subscription", "upgrade", "downgrade", "renew", "plan", "license"],
            confidence=0.96,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 18. ACCOUNT & PROFILE MANAGEMENT
    # -------------------------------------------------------------------------
    profile_triggers = [
        "update my profile", "update profile", "change my account information", "update my contact details",
        "change my company information", "notification preferences", "manage account permissions",
        "account status", "deactivate my account", "reactivate my account"
    ]
    if any(t in cleaned for t in profile_triggers):
        return IntentResult(
            intent_type="ACCOUNT",
            detected_category="Account & Profile Management",
            assigned_team="Account & Profile Operations Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Account & Profile Management"],
            forbidden_categories=["Billing & Payments", "Technical Support", "UI & Troubleshooting"],
            boost_terms=["profile", "contact", "company", "notifications", "permissions", "deactivation"],
            confidence=0.95,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 19. PRODUCTS & SERVICES
    # -------------------------------------------------------------------------
    product_triggers = [
        "products and services", "features are included in my plan", "features included",
        "get started with a product", "configure a product", "enable a feature", "feature unavailable",
        "request a new feature", "learn more about a service", "product is not working", "product support team"
    ]
    if any(t in cleaned for t in product_triggers):
        return IntentResult(
            intent_type="PRODUCT_SERVICE",
            detected_category="Products & Services",
            assigned_team="Product & Solutions Specialist Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Products & Services"],
            forbidden_categories=["Frontend & UI", "Account & Security"],
            boost_terms=["product", "features", "tier", "starter", "professional", "enterprise", "configure"],
            confidence=0.94,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 20. ORDERS, REQUESTS & SERVICE ISSUES
    # -------------------------------------------------------------------------
    order_triggers = [
        "check the status of my request", "update an existing request",
        "cancel a request", "track my support request", "information should i provide",
        "unresolved request", "ticket lifecycle"
    ]
    if any(t in cleaned for t in order_triggers):
        return IntentResult(
            intent_type="ORDER_TRANSACTION",
            detected_category="Orders, Requests & Service Issues",
            assigned_team="Orders & Service Operations Team",
            is_conversational=False,
            is_out_of_scope=False,
            preferred_categories=["Orders, Requests & Service Issues"],
            forbidden_categories=[],
            boost_terms=["request", "tracking", "status", "ticket", "issue", "service", "escalate"],
            confidence=0.95,
            suggested_response_type="NORMAL_ANSWER",
        )

    # -------------------------------------------------------------------------
    # 21. Default General Enterprise Inquiry
    # -------------------------------------------------------------------------
    return IntentResult(
        intent_type="GENERAL_ENTERPRISE",
        detected_category="General Support & SLA",
        assigned_team="General Customer Support Team",
        is_conversational=False,
        is_out_of_scope=False,
        preferred_categories=[],
        forbidden_categories=[],
        boost_terms=[],
        confidence=0.75,
        suggested_response_type="NORMAL_ANSWER",
    )


# Export alias for convenience
detect_intent = detect_query_intent

