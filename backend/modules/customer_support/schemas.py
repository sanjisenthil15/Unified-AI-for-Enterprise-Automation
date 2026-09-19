"""
modules/customer_support/schemas.py

Pydantic schemas for the Customer Support AI module.

Categories:
  1. Support Team schemas
  2. Support Category schemas
  3. Knowledge Base & Chunk schemas
  4. Chat Session & Message schemas
  5. Grounded AI Response schemas
  6. Support Ticket & Escalation schemas
  7. Ticket Message schemas
  8. Customer Support Statistics schema

Follows Pydantic v2 conventions with comprehensive input validation.
No business logic is defined in these schemas.
"""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# =============================================================================
# 1. SUPPORT TEAM SCHEMAS
# =============================================================================

class SupportTeamBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Display name of the team")
    code: str = Field(..., min_length=2, max_length=50, description="Unique routing code, e.g. 'billing_finance'")
    description: Optional[str] = Field(None, max_length=255, description="Team scope and responsibility")
    is_active: bool = Field(True, description="Whether team is active for ticket routing")

    @field_validator("name", "code")
    @classmethod
    def clean_strings(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be blank or whitespace-only")
        return v


class SupportTeamCreate(SupportTeamBase):
    pass


class SupportTeamResponse(SupportTeamBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 2. SUPPORT CATEGORY SCHEMAS
# =============================================================================

class SupportCategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=80, description="Category name, e.g. 'Billing & Payments'")
    description: Optional[str] = Field(None, max_length=255, description="Category description")
    default_team_id: Optional[int] = Field(None, description="FK to default SupportTeam")

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Category name cannot be blank")
        return v


class SupportCategoryCreate(SupportCategoryBase):
    pass


class SupportCategoryResponse(SupportCategoryBase):
    id: int
    created_at: datetime
    default_team: Optional[SupportTeamResponse] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 3. KNOWLEDGE BASE & CHUNK SCHEMAS
# =============================================================================

DocumentType = Literal[
    "faq",
    "product_guide",
    "billing_policy",
    "troubleshooting",
    "auth_procedure",
    "general_policy",
]


class KnowledgeChunkResponse(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    keywords: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=255, description="Document headline or title")
    category_id: Optional[int] = Field(None, description="Associated support category ID")
    doc_type: DocumentType = Field("faq", description="Document classification")
    content: str = Field(..., min_length=10, max_length=50000, description="Full verified knowledge text")
    is_published: bool = Field(True, description="Publish status for RAG indexing")

    @field_validator("title", "content")
    @classmethod
    def clean_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Text content cannot be blank")
        return v


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    pass


class KnowledgeDocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    category_id: Optional[int] = None
    doc_type: Optional[DocumentType] = None
    content: Optional[str] = Field(None, min_length=10, max_length=50000)
    is_published: Optional[bool] = None

    @field_validator("title", "content")
    @classmethod
    def clean_optional_text(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Updated text cannot be blank")
        return v


class KnowledgeDocumentListItem(BaseModel):
    id: int
    title: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    doc_type: str
    is_published: bool
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentResponse(KnowledgeDocumentBase):
    id: int
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    category: Optional[SupportCategoryResponse] = None
    chunks: List[KnowledgeChunkResponse] = []

    model_config = ConfigDict(from_attributes=True)


class SearchResultItem(BaseModel):
    """
    Search retrieval result representing a matched KnowledgeChunk
    with its parent KnowledgeDocument metadata and deterministic relevance score.
    """
    document_id: int
    chunk_id: int
    document_title: str
    doc_type: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    chunk_index: int
    chunk_text: str
    relevance_score: float
    keywords: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSearchResponse(BaseModel):
    """Response payload for knowledge base search queries."""
    query: str
    total_results: int
    min_score_applied: float
    results: List[SearchResultItem] = []


class KnowledgeIngestResponse(BaseModel):
    """Statistics and status returned after ingesting/chunking a KnowledgeDocument."""
    document_id: int
    title: str
    chunks_created: int
    status: str = "success"
    message: Optional[str] = None


# =============================================================================
# 4. CHAT SESSION & MESSAGE SCHEMAS
# =============================================================================

class CitationItem(BaseModel):
    """Source citation from verified enterprise knowledge base."""
    document_id: int
    document_title: str
    chunk_id: Optional[int] = None
    excerpt: str = Field(..., max_length=500, description="Relevant text excerpt snippet")


class SourceItem(BaseModel):
    """Source item schema conforming to enterprise structured RAG response."""
    document_id: str
    document_title: str
    chunk_id: Optional[str] = None
    excerpt: str = Field(..., description="Relevant chunk text excerpt")


class CreateChatSessionRequest(BaseModel):
    customer_name: Optional[str] = Field(None, max_length=120)
    customer_email: Optional[EmailStr] = Field(None, max_length=255)
    initial_message: Optional[str] = Field(None, max_length=4000)

    @field_validator("customer_name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else None


class ChatMessageRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, description="Target chat session UUID")
    message: str = Field(..., min_length=1, max_length=4000, description="Customer query text")
    customer_name: Optional[str] = Field(None, max_length=120)
    customer_email: Optional[EmailStr] = Field(None, max_length=255)

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty or whitespace-only")
        return v


class ChatMessageResponse(BaseModel):
    id: int
    session_id: str
    sender_type: Literal["customer", "ai", "agent"]
    sender_id: Optional[int] = None
    message: str
    confidence_score: Optional[float] = None
    is_escalated: bool = False
    citations: Optional[List[CitationItem]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionResponse(BaseModel):
    id: str
    user_id: Optional[int] = None
    title: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    status: Literal["active", "resolved", "escalated"]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    ticket_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: List[ChatMessageResponse] = []


# =============================================================================
# 5. GROUNDED AI RESPONSE SCHEMA
# =============================================================================

class GroundedAIResponse(BaseModel):
    """
    Structured response payload returned by the AI customer support chatbot.
    Contains grounded answer, confidence score, source citations, and escalation status.
    """
    success: bool = Field(True, description="Whether the request succeeded")
    answer: str = Field(..., description="Grounded response or polite escalation notification")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from 0.00 to 1.00")
    is_grounded: bool = Field(True, description="Whether answer is grounded in verified knowledge")
    is_escalated: bool = Field(False, description="Whether escalation was triggered")
    answerable: bool = Field(True, description="Whether query could be factually answered from KB")
    detected_category: Optional[str] = Field(None, description="Detected issue category")
    escalation_recommended: bool = Field(False, description="Whether escalation was triggered")
    escalation_reason: Optional[str] = Field(None, description="Reason for escalation if triggered")
    citations: List[CitationItem] = Field(default_factory=list, description="Verified KB citations used")
    sources: List[SourceItem] = Field(default_factory=list, description="Verified source documents & chunk snippets")
    ticket_id: Optional[int] = Field(None, description="Created support ticket ID if escalated")
    assigned_team: Optional[str] = Field(None, description="Team routed to if escalated")
    suggested_actions: Optional[List[str]] = Field(default_factory=list, description="Follow-up suggested quick actions")
    clarification_options: Optional[List[str]] = Field(default_factory=list, description="Quick choice clarification options if query is ambiguous")
    conversation_id: Optional[str] = Field(None, description="Active chat session conversation UUID")
    processing_time_ms: Optional[int] = Field(None, description="Time taken to process and synthesize in milliseconds")
    ai_provider: Optional[str] = Field(None, description="AI engine/provider utilized (e.g. Gemini 1.5 Flash, Deterministic)")
    response_type: Optional[str] = Field("NORMAL_ANSWER", description="NORMAL_ANSWER, CONVERSATIONAL, SERVICE_STATUS, TICKET_ACTION, ESCALATION, CLARIFICATION")
    service_status_data: Optional[dict] = Field(None, description="Structured service status and active incidents if applicable")



# =============================================================================
# 6. SUPPORT TICKET SCHEMAS
# =============================================================================

TicketPriority = Literal["low", "medium", "high", "critical"]
TicketStatus = Literal[
    "open",
    "assigned",
    "in_progress",
    "waiting_for_customer",
    "resolved",
    "closed",
    "escalated",
]
TicketChannel = Literal["web", "email", "chat", "api"]


class TicketCreateRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=255, description="Brief summary of issue")
    description: str = Field(..., min_length=5, max_length=5000, description="Detailed problem description")
    category_id: Optional[int] = Field(None, description="Support category ID")
    team_id: Optional[int] = Field(None, description="Target support team ID")
    priority: TicketPriority = Field("medium", description="Urgency priority")
    channel: TicketChannel = Field("chat", description="Submission channel")
    session_id: Optional[str] = Field(None, max_length=64, description="Originating chat session ID")
    customer_name: Optional[str] = Field(None, max_length=120)
    customer_email: Optional[EmailStr] = Field(None, max_length=255)

    @field_validator("subject", "description")
    @classmethod
    def clean_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be blank")
        return v


class TicketUpdateRequest(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_to: Optional[int] = Field(None, description="Agent user ID")
    category_id: Optional[int] = None
    team_id: Optional[int] = None


class TicketEscalateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, description="Chat session to escalate")
    reason: Optional[str] = Field(None, max_length=255, description="Escalation explanation")
    customer_name: Optional[str] = Field(None, max_length=120)
    customer_email: Optional[EmailStr] = Field(None, max_length=255)
    priority: Optional[TicketPriority] = Field("medium")
    category_id: Optional[int] = None


class TicketListItem(BaseModel):
    id: int
    subject: str
    priority: TicketPriority
    status: TicketStatus
    channel: TicketChannel
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    sla_status: Optional[str] = "on_track"
    sla_time_remaining: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketResponse(BaseModel):
    id: int
    session_id: Optional[str] = None
    category_id: Optional[int] = None
    team_id: Optional[int] = None
    submitted_by: int
    assigned_to: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    subject: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    channel: TicketChannel
    escalation_reason: Optional[str] = None
    ai_summary: Optional[str] = None
    sla_status: Optional[str] = "on_track"
    sla_time_remaining: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 7. TICKET MESSAGE SCHEMAS
# =============================================================================

class TicketMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Message text")
    is_ai: bool = Field(False, description="Whether message was auto-generated")

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be blank")
        return v


class TicketMessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    message: str
    is_ai: bool = False
    ai_model: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketDetailResponse(TicketResponse):
    category: Optional[SupportCategoryResponse] = None
    team: Optional[SupportTeamResponse] = None
    messages: List[TicketMessageResponse] = []
    chat_transcript: Optional[List[ChatMessageResponse]] = None


# =============================================================================
# 8. CUSTOMER SUPPORT STATS SCHEMA
# =============================================================================

class CustomerSupportStats(BaseModel):
    total_tickets: int = 0
    open_tickets: int = 0
    escalated_tickets: int = 0
    resolved_tickets: int = 0
    ai_resolved_sessions: int = 0
    active_sessions: int = 0
    total_knowledge_docs: int = 0


# =============================================================================
# 9. FEEDBACK & AGENT HANDOFF SCHEMAS
# =============================================================================

class ChatFeedbackRequest(BaseModel):
    rating: Literal["helpful", "not_helpful"]
    comment: Optional[str] = Field(None, max_length=500)


class AgentHandoffResponse(BaseModel):
    session_id: str
    issue_summary: str
    attempted_steps: List[str] = []
    relevant_articles: List[str] = []
    recommended_team: str
    detected_category: str
    recommended_priority: TicketPriority = "medium"
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    ticket_id: Optional[int] = None


# =============================================================================
# 10. GLOBAL SEARCH SCHEMAS
# =============================================================================

class GlobalSearchItem(BaseModel):
    id: str
    title: str
    type: Literal["knowledge", "ticket", "category"]
    snippet: Optional[str] = None
    status: Optional[str] = None
    category_name: Optional[str] = None
    score: Optional[float] = None
    url: Optional[str] = None


class GlobalSearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[GlobalSearchItem] = []


# =============================================================================
# 11. ENTERPRISE SERVICE STATUS & INCIDENT SCHEMAS
# =============================================================================

ServiceOperationalStatus = Literal[
    "operational",
    "degraded",
    "maintenance",
    "partially_available",
    "outage",
]

IncidentSeverity = Literal["critical", "major", "minor"]
IncidentStatus = Literal["investigating", "identified", "monitoring", "resolved"]


class EnterpriseServiceStatusItem(BaseModel):
    id: str
    name: str
    status: ServiceOperationalStatus = "operational"
    uptime_pct: float = 99.98
    latency_ms: int = 45
    description: str
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)


class IncidentUpdateItem(BaseModel):
    id: int
    timestamp: datetime
    status: IncidentStatus
    message: str


class ServiceIncidentItem(BaseModel):
    id: str
    title: str
    affected_service: str
    severity: IncidentSeverity = "minor"
    status: IncidentStatus = "resolved"
    started_at: datetime
    resolved_at: Optional[datetime] = None
    impact: str
    latest_update: str
    timeline: List[IncidentUpdateItem] = []


class ServiceStatusOverviewResponse(BaseModel):
    overall_status: str = "All Systems Operational"
    services: List[EnterpriseServiceStatusItem] = []
    active_incidents: List[ServiceIncidentItem] = []
    past_incidents: List[ServiceIncidentItem] = []
    is_live_data: bool = False
    data_mode: str = "DEMO / DEVELOPMENT STATUS"


# =============================================================================
# 12. GUIDED SUPPORT REQUEST & DUPLICATE DETECTION SCHEMAS
# =============================================================================

class SupportRequestAnalysisRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5, max_length=5000)
    category_id: Optional[int] = None
    customer_email: Optional[EmailStr] = None


class DuplicateTicketAlert(BaseModel):
    ticket_id: int
    subject: str
    status: str
    priority: str
    assigned_team: Optional[str] = None
    created_at: datetime
    similarity_reason: str


class SupportRequestAnalysisResponse(BaseModel):
    detected_issue: str
    detected_category: str
    category_id: int
    recommended_team: str
    suggested_priority: TicketPriority = "medium"
    ai_summary: str
    relevant_knowledge_title: Optional[str] = None
    relevant_knowledge_excerpt: Optional[str] = None
    duplicate_alert: Optional[DuplicateTicketAlert] = None


# =============================================================================
# 13. NOTIFICATION & COMMUNICATION CENTER SCHEMAS
# =============================================================================

NotificationType = Literal[
    "ticket_update",
    "agent_reply",
    "sla_warning",
    "escalation",
    "resolution",
    "incident_update",
    "maintenance",
    "system",
]


class SupportNotificationItem(BaseModel):
    id: str
    type: NotificationType
    title: str
    message: str
    target_type: Literal["ticket", "incident", "kb_doc", "service_status", "system"] = "ticket"
    target_id: Optional[str] = None
    is_read: bool = False
    created_at: datetime
    priority: Literal["low", "normal", "high", "critical"] = "normal"


class NotificationListResponse(BaseModel):
    notifications: List[SupportNotificationItem] = []
    unread_count: int = 0
    is_live_data: bool = False


class NotificationPreferences(BaseModel):
    email_notifications: bool = True
    ticket_updates: bool = True
    sla_alerts: bool = True
    incident_alerts: bool = True
    agent_replies: bool = True


