"""
schemas/ticket.py

Re-exports customer support schemas from modules/customer_support/schemas.py
for convenient top-level schema imports.
"""

from modules.customer_support.schemas import (  # noqa: F401
    SupportTeamBase,
    SupportTeamCreate,
    SupportTeamResponse,
    SupportCategoryBase,
    SupportCategoryCreate,
    SupportCategoryResponse,
    KnowledgeDocumentBase,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeDocumentListItem,
    KnowledgeDocumentResponse,
    KnowledgeChunkResponse,
    SearchResultItem,
    KnowledgeSearchResponse,
    KnowledgeIngestResponse,
    CreateChatSessionRequest,
    ChatSessionResponse,
    ChatSessionDetailResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    CitationItem,
    GroundedAIResponse,
    TicketCreateRequest,
    TicketUpdateRequest,
    TicketEscalateRequest,
    TicketListItem,
    TicketResponse,
    TicketDetailResponse,
    TicketMessageRequest,
    TicketMessageResponse,
    CustomerSupportStats,
)
