"""
modules/customer_support/search.py

Deterministic lexical and BM25-based search engine for enterprise Knowledge Documents.

Design Principles:
  1. No external vector databases or heavyweight NLP dependencies.
  2. Pure Python, deterministic, explainable relevance scoring.
  3. Query normalization (case, punctuation, technical token preservation).
  4. BM25 scoring with document length normalization and IDF weighting.
  5. Topical boost multipliers for parent document title and chunk keyword tags.
  6. Exact phrase match boosting.
  7. Strict publication and category filtering.
  8. Configurable minimum relevance score threshold to prevent hallucinations.
  9. Full citation traceability (document ID, title, chunk ID, index, text, score).
"""

import math
import re
from typing import Dict, List, Optional, Set, Tuple

from modules.customer_support.chunking import STOPWORDS
from modules.customer_support.intent import IntentResult, detect_query_intent
from modules.customer_support.schemas import SearchResultItem


# Default configuration constants
DEFAULT_MIN_SCORE_THRESHOLD: float = 0.15
DEFAULT_MAX_RESULTS: int = 5
BM25_K1: float = 1.5
BM25_B: float = 0.75
TITLE_BOOST: float = 1.40       # 40% boost for matches in document title
KEYWORD_BOOST: float = 1.25     # 25% boost for matches in chunk keyword tags
EXACT_PHRASE_BOOST: float = 1.35 # 35% boost for verbatim phrase match


SYNONYMS: Dict[str, List[str]] = {
    # 1. Billing & Payments & Recharges
    "period": ["policy", "days", "window", "timeline", "timeframe", "cancellation", "refund", "eligibility"],
    "window": ["period", "policy", "days", "timeline", "refund", "30"],
    "timeframe": ["period", "days", "policy", "window"],
    "refund": ["reimbursement", "money", "back", "period", "policy", "cancellation", "cancel", "return", "claim"],
    "cancellation": ["refund", "period", "policy", "subscription", "cancel", "terminate"],
    "cancel": ["cancellation", "refund", "subscription", "policy", "billing", "stop"],
    "money": ["refund", "back", "payment", "reimbursement", "charge", "funds", "deducted", "recharge"],
    "return": ["refund", "money", "back", "payment", "reimbursement"],
    "twice": ["double", "duplicate", "charged", "billing", "invoice", "payment", "incorrectly"],
    "double": ["twice", "duplicate", "charged", "billing", "invoice", "payment"],
    "duplicate": ["twice", "double", "charged", "billing", "invoice", "payment"],
    "declined": ["failed", "payment", "rejected", "card", "bank", "billing"],
    "pending": ["clearing", "settled", "bank", "authorization", "payment", "transaction"],
    "receipt": ["invoice", "payment", "history", "download", "transaction", "billing"],
    "incorrectly": ["wrong", "twice", "double", "dispute", "charged", "billing"],
    "recharge": ["payment", "subscription", "plan", "scheme", "activation", "deducted", "paid", "billing", "invoice", "999", "tier", "pack"],
    "recharged": ["recharge", "payment", "subscription", "plan", "scheme", "activation", "deducted", "paid"],
    "scheme": ["plan", "subscription", "recharge", "tier", "pack", "activation"],
    "activate": ["activation", "activated", "active", "subscription", "plan", "scheme", "sync", "recharge"],
    "activated": ["activation", "activate", "active", "subscription", "plan", "scheme", "sync", "recharge"],
    "activation": ["activate", "activated", "active", "subscription", "plan", "scheme", "sync", "recharge", "webhook"],
    "deducted": ["deduct", "payment", "recharge", "charge", "subscription", "money", "billing", "invoice", "double", "twice"],
    "deduct": ["deducted", "payment", "recharge", "charge", "subscription", "money", "billing", "invoice"],
    "999": ["recharge", "payment", "plan", "scheme", "subscription", "amount", "deducted"],

    # 2. Account & Security
    "reset": ["forgot", "procedure", "link", "recovery", "password", "lockout", "login", "change"],
    "forgot": ["reset", "password", "recovery", "procedure", "login", "lost"],
    "login": ["password", "reset", "auth", "lockout", "2fa", "access", "credentials", "sign"],
    "locked": ["lockout", "password", "reset", "attempts", "auth", "login", "unlock"],
    "lockout": ["locked", "password", "reset", "attempts", "auth", "unlock"],
    "2fa": ["mfa", "authenticator", "backup", "codes", "security", "two-factor", "verification"],
    "mfa": ["2fa", "authenticator", "backup", "codes", "security", "two-factor"],
    "unauthorized": ["security", "access", "breach", "sessions", "compromised", "suspicious", "devices"],
    "sessions": ["devices", "devices", "active", "sign", "out", "security", "logged"],
    "devices": ["sessions", "active", "phones", "laptops", "sign", "out", "connected"],

    # 3. Technical Support
    "500": ["internal", "server", "error", "troubleshooting", "rate", "limit", "timeout", "api", "failing", "exception"],
    "404": ["not", "found", "endpoint", "url", "route", "missing", "api"],
    "401": ["unauthorized", "auth", "token", "bearer", "expired", "permission", "jwt"],
    "crash": ["500", "error", "server", "troubleshooting", "api", "failing"],
    "failing": ["500", "error", "server", "api", "troubleshooting", "timeout"],
    "timeout": ["latency", "slow", "500", "failing", "network", "gateway", "response"],
    "slow": ["latency", "timeout", "loading", "performance", "response", "delay"],
    "unavailable": ["outage", "down", "500", "maintenance", "service", "offline"],

    # 4. Subscriptions & Invoicing
    "subscription": ["plan", "tier", "license", "invoicing", "renew", "upgrade", "downgrade", "cancel", "recharge", "scheme"],
    "upgrade": ["subscription", "tier", "plan", "features", "higher", "enterprise", "recharge"],
    "downgrade": ["subscription", "tier", "plan", "lower", "starter"],
    "renew": ["renewal", "subscription", "annual", "monthly", "cycle", "billing", "recharge"],
    "renewal": ["renew", "subscription", "annual", "monthly", "cycle", "billing"],
    "inactive": ["subscription", "deducted", "payment", "billing", "license", "activation", "sync", "scheme", "plan"],
    "reactivate": ["reactivation", "restore", "subscription", "account", "resume"],

    # 5. UI & Troubleshooting
    "unresponsive": ["frozen", "troubleshooting", "cache", "refresh", "button", "frontend", "click", "dashboard", "disabled"],
    "frozen": ["unresponsive", "troubleshooting", "cache", "refresh", "button", "dashboard"],
    "cache": ["refresh", "storage", "browser", "ctrl", "f5", "troubleshooting", "cookies", "clear"],
    "cookies": ["cache", "storage", "clear", "browser", "session", "refresh"],
    "refresh": ["cache", "ctrl", "f5", "reload", "hard", "browser", "stale"],
    "browsers": ["chrome", "firefox", "edge", "safari", "compatibility", "supported"],

    # 6. General Support & SLA
    "hours": ["operating", "sla", "schedule", "support", "agreement", "contact", "coverage"],
    "sla": ["priority", "critical", "response", "resolution", "hours", "agreement", "target", "high"],
    "critical": ["sla", "outage", "priority", "hour", "urgent", "emergency", "24/7"],
    "escalate": ["escalation", "specialist", "agent", "human", "ticket", "priority", "tier-2"],
    "escalation": ["escalate", "specialist", "agent", "human", "ticket", "priority"],
    "contact": ["support", "procedure", "ticket", "hours", "email", "sla", "specialist", "agent"],
    "human": ["agent", "specialist", "handoff", "representative", "person", "support"],

    # 7. Account & Profile Management
    "profile": ["contact", "name", "email", "phone", "details", "company", "information", "account"],
    "notification": ["notifications", "preferences", "email", "sms", "alerts", "settings"],
    "permissions": ["roles", "admin", "viewer", "member", "access", "team"],
    "deactivate": ["deactivation", "delete", "close", "disable", "account", "privacy"],

    # 8. Products & Services
    "product": ["features", "modules", "services", "catalog", "capabilities", "tier", "plan"],
    "features": ["product", "included", "capabilities", "tier", "professional", "enterprise"],
    "configure": ["configuration", "setup", "integrations", "settings", "enable", "onboarding"],

    # 9. Orders, Requests & Service Issues
    "request": ["ticket", "service", "status", "track", "tracking", "issue", "submit", "lifecycle"],
    "tracking": ["track", "status", "check", "request", "ticket", "progress"],
    "track": ["tracking", "status", "check", "request", "ticket", "progress"],
}

STEM_MAPPINGS: Dict[str, str] = {
    "refunds": "refund",
    "refunded": "refund",
    "refunding": "refund",
    "payments": "payment",
    "paid": "payment",
    "paying": "payment",
    "charges": "charge",
    "charged": "charge",
    "charging": "charge",
    "invoices": "invoice",
    "invoiced": "invoice",
    "invoicing": "invoice",
    "recharges": "recharg",
    "recharged": "recharg",
    "recharging": "recharg",
    "recharge": "recharg",
    "activated": "activat",
    "activating": "activat",
    "activation": "activat",
    "activates": "activat",
    "activate": "activat",
    "schemes": "scheme",
    "scheme": "scheme",
    "deducted": "deduct",
    "deducting": "deduct",
    "deducts": "deduct",
    "deduction": "deduct",
    "plans": "plan",
    "passwords": "password",
    "buttons": "button",
    "errors": "error",
    "servers": "server",
    "requests": "request",
    "requesting": "request",
    "requested": "request",
    "accounts": "account",
    "subscriptions": "subscription",
    "subscribing": "subscription",
    "procedures": "procedure",
    "policies": "policy",
    "browsers": "browser",
    "guides": "guide",
    "responses": "response",
    "hours": "hour",
    "codes": "code",
    "claims": "claim",
    "tickets": "ticket",
    "devices": "device",
    "sessions": "session",
    "features": "feature",
    "products": "product",
    "services": "service",
    "issues": "issue",
    "orders": "order",
    "profiles": "profile",
    "settings": "setting",
    "preferences": "preference",
    "permissions": "permission",
    "notifications": "notification",
    "upgrades": "upgrade",
    "upgraded": "upgrade",
    "downgrades": "downgrade",
    "downgraded": "downgrade",
    "renewals": "renewal",
    "renewed": "renew",
}


def stem_word(w: str) -> str:
    """Performs lightweight deterministic stemming for common support vocabulary."""
    clean = w.lower().strip(".-_")
    if clean in STEM_MAPPINGS:
        return STEM_MAPPINGS[clean]
    if clean.endswith("ies") and len(clean) > 4:
        return clean[:-3] + "y"
    if clean.endswith("es") and len(clean) > 4 and not clean.endswith("ses"):
        return clean[:-2]
    if clean.endswith("s") and len(clean) > 3 and not clean.endswith("ss"):
        return clean[:-1]
    if clean.endswith("ing") and len(clean) > 5:
        return clean[:-3]
    if clean.endswith("ed") and len(clean) > 4:
        return clean[:-2]
    return clean


def tokenize_query(query: str, expand_synonyms: bool = True) -> List[str]:
    """
    Tokenizes and normalizes a search query.
    Converts to lowercase, removes excess punctuation, preserves technical codes
    (e.g., '500', '2fa', '404', 'api', 'oauth'), stems words, and filters standard stopwords.
    Optionally expands relevant enterprise support synonyms.
    """
    if not query:
        return []

    # Clean punctuation except hyphens/dots inside words
    cleaned = query.lower().strip()
    raw_tokens = re.findall(r"[a-z0-9_\-\.]{2,}", cleaned)

    tokens: List[str] = []
    seen: Set[str] = set()

    for t in raw_tokens:
        clean_t = stem_word(t)
        if not clean_t or clean_t in STOPWORDS or len(clean_t) < 2:
            continue
        if clean_t not in seen:
            seen.add(clean_t)
            tokens.append(clean_t)

        if expand_synonyms and clean_t in SYNONYMS:
            for syn in SYNONYMS[clean_t]:
                syn_stem = stem_word(syn)
                if syn_stem not in seen and syn_stem not in STOPWORDS:
                    seen.add(syn_stem)
                    tokens.append(syn_stem)

    return tokens


def tokenize_corpus_text(text: str) -> List[str]:
    """
    Tokenizes document or chunk body text into a list of normalized and stemmed terms.
    """
    if not text:
        return []
    cleaned = text.lower()
    raw_tokens = re.findall(r"[a-z0-9_\-\.]{2,}", cleaned)
    tokens: List[str] = []
    for t in raw_tokens:
        clean_t = stem_word(t)
        if clean_t and clean_t not in STOPWORDS and len(clean_t) >= 2:
            tokens.append(clean_t)
    return tokens


class KnowledgeChunkSearchCandidate:
    """Internal lightweight data container for candidate chunk scoring."""
    def __init__(
        self,
        chunk_id: int,
        document_id: int,
        document_title: str,
        doc_type: str,
        category_id: Optional[int],
        category_name: Optional[str],
        chunk_index: int,
        chunk_text: str,
        keywords: Optional[str],
        is_published: bool,
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.document_title = document_title
        self.doc_type = doc_type
        self.category_id = category_id
        self.category_name = category_name
        self.chunk_index = chunk_index
        self.chunk_text = chunk_text
        self.keywords = keywords or ""
        self.is_published = is_published

        # Pre-tokenize for BM25
        self.chunk_tokens = tokenize_corpus_text(chunk_text)
        self.title_tokens = set(tokenize_corpus_text(document_title))
        self.keyword_tokens = set(tokenize_corpus_text(self.keywords))
        self.doc_len = len(self.chunk_tokens)


class KnowledgeSearchEngine:
    """
    In-memory deterministic BM25 search engine for active knowledge base chunks.
    """

    def __init__(self, candidates: List[KnowledgeChunkSearchCandidate]):
        # Filter strictly to published candidates
        self.candidates: List[KnowledgeChunkSearchCandidate] = [
            c for c in candidates if c.is_published
        ]
        self.num_docs: int = len(self.candidates)
        self.avg_doc_len: float = (
            sum(c.doc_len for c in self.candidates) / self.num_docs
            if self.num_docs > 0
            else 1.0
        )
        # Compute Document Frequency (DF) for each unique token in the corpus
        self.df: Dict[str, int] = {}
        for c in self.candidates:
            seen_tokens: Set[str] = set(c.chunk_tokens) | c.title_tokens | c.keyword_tokens
            for token in seen_tokens:
                self.df[token] = self.df.get(token, 0) + 1

    def _compute_idf(self, term: str) -> float:
        """Computes standard BM25 smoothed inverse document frequency."""
        df_t = self.df.get(term, 0)
        if df_t == 0:
            # Term not seen in general corpus, assign baseline IDF
            return math.log(1.0 + (self.num_docs + 1.0) / 0.5)
        return math.log(1.0 + (self.num_docs - df_t + 0.5) / (df_t + 0.5))

    def score_candidate(
        self,
        candidate: KnowledgeChunkSearchCandidate,
        query_tokens: List[str],
        raw_query: str,
        intent: Optional[IntentResult] = None,
    ) -> float:
        """
        Calculates the composite relevance score of a candidate chunk against a query.
        Combines BM25 term frequency, title boost, keyword boost, exact phrase bonus,
        and category-aware domain constraints.
        """
        if not query_tokens or candidate.doc_len == 0:
            return 0.0

        # Category constraint enforcement
        if intent:
            # 1. Strict forbidden category filtering
            if candidate.category_name and candidate.category_name in intent.forbidden_categories:
                return 0.0
            if candidate.doc_type and any(fc.lower() in candidate.doc_type.lower() for fc in intent.forbidden_categories):
                return 0.0

        # 1. Term frequencies in candidate chunk text
        tf_dict: Dict[str, int] = {}
        for token in candidate.chunk_tokens:
            tf_dict[token] = tf_dict.get(token, 0) + 1

        bm25_score: float = 0.0
        matched_tokens_count: int = 0

        for term in query_tokens:
            tf = tf_dict.get(term, 0)
            in_title = term in candidate.title_tokens
            in_keywords = term in candidate.keyword_tokens

            # Even if term is not in chunk text, matching title or keywords is informative
            if tf > 0 or in_title or in_keywords:
                matched_tokens_count += 1

            idf = self._compute_idf(term)

            # BM25 TF component
            numerator = tf * (BM25_K1 + 1.0)
            denominator = tf + BM25_K1 * (
                1.0 - BM25_B + BM25_B * (candidate.doc_len / (self.avg_doc_len or 1.0))
            )
            tf_component = (numerator / denominator) if denominator > 0 else 0.0

            # Title and keyword boost multipliers
            term_multiplier = 1.0
            if in_title:
                term_multiplier *= TITLE_BOOST
                # If term is in title, give a baseline credit even if tf == 0
                if tf_component == 0.0:
                    tf_component = 0.5
            if in_keywords:
                term_multiplier *= KEYWORD_BOOST
                if tf_component == 0.0:
                    tf_component = 0.3

            bm25_score += idf * tf_component * term_multiplier

        # If zero query tokens matched, score is 0
        if matched_tokens_count == 0:
            return 0.0

        # Query coverage ratio (penalty if only a small fraction of query terms matched)
        coverage_ratio = matched_tokens_count / len(query_tokens)
        if len(query_tokens) >= 3 and coverage_ratio < 0.30:
            bm25_score *= (coverage_ratio ** 1.5)
        else:
            bm25_score *= coverage_ratio

        # Exact phrase match bonus
        cleaned_raw_query = raw_query.strip().lower()
        if len(cleaned_raw_query) >= 4:
            # Check if cleaned phrase appears in chunk text or title
            if cleaned_raw_query in candidate.chunk_text.lower():
                bm25_score *= EXACT_PHRASE_BOOST
            elif cleaned_raw_query in candidate.document_title.lower():
                bm25_score *= EXACT_PHRASE_BOOST

        # Intent-driven category boost & boost terms
        if intent:
            if candidate.category_name and candidate.category_name in intent.preferred_categories:
                bm25_score *= 1.60
            if intent.boost_terms:
                matched_boost_terms = sum(
                    1 for bt in intent.boost_terms
                    if stem_word(bt) in candidate.chunk_tokens or stem_word(bt) in candidate.title_tokens
                )
                if matched_boost_terms > 0:
                    bm25_score *= (1.0 + 0.15 * min(matched_boost_terms, 4))

        # Normalization function to map raw BM25 score smoothly to [0.0, 1.0].
        # Uses standard soft-saturation scaling: score / (score + 0.6)
        # Guarantees 0.0 for zero matches, ~0.20-0.45 for single weak matches,
        # and 0.70-0.95 for multi-term / title / exact phrase matches.
        normalized_score = bm25_score / (bm25_score + 0.6)
        return round(float(normalized_score), 4)

    def search(
        self,
        query: str,
        category_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        min_score: float = DEFAULT_MIN_SCORE_THRESHOLD,
        limit: int = DEFAULT_MAX_RESULTS,
        intent: Optional[IntentResult] = None,
    ) -> List[SearchResultItem]:
        """
        Executes query retrieval across candidate knowledge chunks.

        Filters:
          - is_published == True (enforced at initialization)
          - category_id match (if category_id is provided)
          - doc_type match (if doc_type is provided)
          - score >= min_score

        Returns:
          Ordered list of SearchResultItem, highest score first.
        """
        if not query:
            return []

        # If intent is conversational (greeting/thanks) or out-of-scope, return 0 KB retrieval
        if intent and (intent.is_conversational or intent.is_out_of_scope):
            return []

        query_tokens = tokenize_query(query)
        if not query_tokens:
            return []

        scored_candidates: List[Tuple[KnowledgeChunkSearchCandidate, float]] = []

        for candidate in self.candidates:
            # Category filter
            if category_id is not None and candidate.category_id != category_id:
                continue

            # Doc type filter
            if doc_type is not None and candidate.doc_type != doc_type:
                continue

            score = self.score_candidate(candidate, query_tokens, query, intent=intent)
            if score >= min_score:
                scored_candidates.append((candidate, score))

        # Sort by relevance score descending, then by chunk index ascending
        scored_candidates.sort(key=lambda x: (-x[1], x[0].chunk_index))

        # Slice to requested limit
        top_candidates = scored_candidates[:limit]

        # Build response schema objects
        results: List[SearchResultItem] = []
        for cand, score in top_candidates:
            results.append(
                SearchResultItem(
                    document_id=cand.document_id,
                    chunk_id=cand.chunk_id,
                    document_title=cand.document_title,
                    doc_type=cand.doc_type,
                    category_id=cand.category_id,
                    category_name=cand.category_name,
                    chunk_index=cand.chunk_index,
                    chunk_text=cand.chunk_text,
                    relevance_score=score,
                    keywords=cand.keywords if cand.keywords else None,
                )
            )

        return results
