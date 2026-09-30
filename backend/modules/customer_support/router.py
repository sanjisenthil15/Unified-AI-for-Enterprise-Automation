"""
modules/customer_support/router.py

FastAPI router for the Enterprise Customer Support AI module.

Endpoints:
  - Module Health & Stats:
      GET    /customer-support/health
      GET    /customer-support/stats
      GET    /customer-support/global-search

  - Knowledge Base & Retrieval:
      POST   /customer-support/knowledge
      GET    /customer-support/knowledge
      GET    /customer-support/knowledge/search
      GET    /customer-support/knowledge/{doc_id}
      PUT    /customer-support/knowledge/{doc_id}
      DELETE /customer-support/knowledge/{doc_id}
      POST   /customer-support/knowledge/{doc_id}/publish
      POST   /customer-support/knowledge/{doc_id}/unpublish
      POST   /customer-support/knowledge/{doc_id}/reindex

  - Categories & Teams:
      GET    /customer-support/categories
      POST   /customer-support/categories
      GET    /customer-support/teams
      POST   /customer-support/teams

  - AI Chat Sessions & Grounded Chatbot:
      POST   /customer-support/chat/sessions
      GET    /customer-support/chat/sessions
      GET    /customer-support/chat/sessions/{session_id}
      DELETE /customer-support/chat/sessions/{session_id}
      POST   /customer-support/chat/message
      POST   /customer-support/chat/messages/{message_id}/feedback
      POST   /customer-support/chat/handoff

  - Support Ticket Management:
      POST   /customer-support/tickets
      GET    /customer-support/tickets
      GET    /customer-support/tickets/{ticket_id}
      PUT    /customer-support/tickets/{ticket_id}
      POST   /customer-support/tickets/{ticket_id}/messages
      POST   /customer-support/tickets/escalate
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_user
from models.role import Role
from models.user import User
from modules.customer_support import service
from modules.customer_support.schemas import (
    AgentHandoffResponse,
    ChatFeedbackRequest,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
    CustomerSupportStats,
    GlobalSearchResponse,
    GroundedAIResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentListItem,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
    KnowledgeIngestResponse,
    KnowledgeSearchResponse,
    NotificationListResponse,
    NotificationPreferences,
    ServiceIncidentItem,
    ServiceStatusOverviewResponse,
    SupportCategoryCreate,
    SupportCategoryResponse,
    SupportNotificationItem,
    SupportRequestAnalysisRequest,
    SupportRequestAnalysisResponse,
    SupportTeamCreate,
    SupportTeamResponse,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketEscalateRequest,
    TicketListItem,
    TicketMessageRequest,
    TicketMessageResponse,
    TicketResponse,
    TicketUpdateRequest,
)

# -----------------------------------------------------------------------------
# Development Authentication Helper
# -----------------------------------------------------------------------------
_optional_bearer = HTTPBearer(auto_error=False)


def get_dev_or_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Returns user from token, or default dev admin in development."""
    if credentials and credentials.credentials:
        try:
            return get_current_user(credentials=credentials, db=db)
        except Exception:
            pass
    dev_role = Role(id=1, name="admin", description="Development Administrator")
    return User(
        id=1,
        full_name="Dev Admin",
        email="admin@enterprise.ai",
        is_active=True,
        role=dev_role,
    )


def require_roles_dev(allowed_roles: List[str]):
    def _check(current_user: User = Depends(get_dev_or_current_user)) -> User:
        user_role_name = current_user.role.name if (current_user and current_user.role) else "admin"
        if user_role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}. Your role: {user_role_name}.",
            )
        return current_user
    return _check


router = APIRouter(prefix="/customer-support", tags=["Customer Support AI Platform"])


# =============================================================================
# 0. MODULE HEALTH & STATS & GLOBAL SEARCH
# =============================================================================

@router.get("/health", summary="Customer support module health check")
def customer_support_health() -> dict:
    return {
        "status": "ok",
        "module": "customer_support",
        "version": "2.0.0",
        "message": "Enterprise Customer Support AI Engine is operational",
    }


@router.get("/stats", response_model=CustomerSupportStats, summary="Customer support operational statistics")
def customer_support_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_customer_support_stats(db=db)


@router.get("/global-search", response_model=GlobalSearchResponse, summary="Cross-entity customer support search")
def global_customer_support_search(
    q: str = Query(..., min_length=1, description="Query text to search across KB, tickets, categories"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.global_customer_support_search(db=db, query=q, limit=limit)


# =============================================================================
# 1. KNOWLEDGE BASE MANAGEMENT ENDPOINTS
# =============================================================================

@router.post(
    "/knowledge",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create knowledge document with deterministic chunking",
)
def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.create_knowledge_document(db=db, payload=payload, created_by_id=current_user.id)


@router.get(
    "/knowledge",
    response_model=List[KnowledgeDocumentListItem],
    summary="List knowledge documents with filtering and pagination",
)
def list_knowledge_documents(
    category_id: Optional[int] = Query(None),
    doc_type: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_knowledge_documents(
        db=db,
        category_id=category_id,
        doc_type=doc_type,
        is_published=is_published,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/knowledge/search",
    response_model=KnowledgeSearchResponse,
    summary="BM25 Lexical search over verified knowledge base chunks",
)
def search_knowledge_base(
    q: str = Query(..., min_length=1, description="Search query"),
    category_id: Optional[int] = Query(None),
    doc_type: Optional[str] = Query(None),
    min_score: float = Query(0.15, ge=0.0, le=1.0),
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.search_knowledge_base(
        db=db,
        query=q,
        category_id=category_id,
        doc_type=doc_type,
        min_score=min_score,
        limit=limit,
    )


@router.get(
    "/knowledge/{document_id}",
    response_model=KnowledgeDocumentResponse,
    summary="Get single knowledge document with its chunks",
)
def get_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_knowledge_document(db=db, document_id=document_id)


@router.put(
    "/knowledge/{document_id}",
    response_model=KnowledgeDocumentResponse,
    summary="Update knowledge document & atomically re-chunk",
)
def update_knowledge_document(
    document_id: int,
    payload: KnowledgeDocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.update_knowledge_document(db=db, document_id=document_id, payload=payload)


@router.delete(
    "/knowledge/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete knowledge document and chunks",
)
def delete_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    service.delete_knowledge_document(db=db, document_id=document_id)


@router.post(
    "/knowledge/{document_id}/publish",
    response_model=KnowledgeDocumentResponse,
    summary="Publish document for search indexing",
)
def publish_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.set_document_publication(db=db, document_id=document_id, is_published=True)


@router.post(
    "/knowledge/{document_id}/unpublish",
    response_model=KnowledgeDocumentResponse,
    summary="Unpublish document from search",
)
def unpublish_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.set_document_publication(db=db, document_id=document_id, is_published=False)


@router.post(
    "/knowledge/{document_id}/reindex",
    response_model=KnowledgeIngestResponse,
    summary="Force re-chunking and re-indexing",
)
def reindex_knowledge_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.reindex_knowledge_document(db=db, document_id=document_id)


# =============================================================================
# 2. CATEGORIES & TEAMS ENDPOINTS
# =============================================================================

@router.get("/categories", response_model=List[SupportCategoryResponse], summary="List support issue categories")
def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_support_categories(db=db)


@router.post("/categories", response_model=SupportCategoryResponse, status_code=status.HTTP_201_CREATED, summary="Create support category")
def create_category(
    payload: SupportCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.create_support_category(db=db, payload=payload)


@router.get("/teams", response_model=List[SupportTeamResponse], summary="List support resolution teams")
def list_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_support_teams(db=db)


@router.post("/teams", response_model=SupportTeamResponse, status_code=status.HTTP_201_CREATED, summary="Create support team")
def create_team(
    payload: SupportTeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles_dev(["admin", "support_agent"])),
):
    return service.create_support_team(db=db, payload=payload)


# =============================================================================
# 3. AI CHAT SESSIONS & GROUNDED CHATBOT
# =============================================================================

@router.post("/chat/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED, summary="Create a new chat conversation session")
def create_chat_session(
    payload: Optional[CreateChatSessionRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.create_chat_session(db=db, payload=payload, user_id=current_user.id)


@router.get("/chat/sessions", response_model=List[ChatSessionResponse], summary="List conversation history")
def list_chat_sessions(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_chat_sessions(db=db, user_id=current_user.id, limit=limit)


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse, summary="Get full conversation transcript")
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_chat_session(db=db, session_id=session_id)


@router.delete("/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete conversation session")
def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    service.delete_chat_session(db=db, session_id=session_id)


@router.post("/chat/message", response_model=GroundedAIResponse, summary="Send message to AI assistant & get grounded answer")
def send_chat_message(
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.send_chat_message(db=db, payload=payload, user_id=current_user.id)


@router.post("/chat/messages/{message_id}/feedback", summary="Rate AI answer (Helpful / Not Helpful)")
def submit_chat_feedback(
    message_id: int,
    payload: ChatFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.submit_chat_feedback(db=db, message_id=message_id, payload=payload)


@router.post("/chat/handoff", response_model=AgentHandoffResponse, summary="Generate human agent handoff brief")
def generate_agent_handoff(
    session_id: str = Query(..., description="Chat session ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.generate_agent_handoff(db=db, session_id=session_id)


# =============================================================================
# 4. SUPPORT TICKET MANAGEMENT ENDPOINTS
# =============================================================================

@router.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED, summary="Create a new support ticket")
def create_support_ticket(
    payload: TicketCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.create_support_ticket(db=db, payload=payload, submitted_by_id=current_user.id)


@router.get("/tickets", response_model=List[TicketListItem], summary="List support tickets with filters")
def list_support_tickets(
    status: Optional[str] = Query(None, description="Filter by status (open, in_progress, escalated, resolved, closed)"),
    priority: Optional[str] = Query(None, description="Filter by priority (low, medium, high, critical)"),
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_support_tickets(
        db=db,
        status_filter=status,
        priority_filter=priority,
        category_id=category_id,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse, summary="Get ticket detail with messages & chat history")
def get_support_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_support_ticket(db=db, ticket_id=ticket_id)


@router.put("/tickets/{ticket_id}", response_model=TicketDetailResponse, summary="Update ticket status / priority / assignee")
def update_support_ticket(
    ticket_id: int,
    payload: TicketUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.update_support_ticket(db=db, ticket_id=ticket_id, payload=payload)


@router.post("/tickets/{ticket_id}/messages", response_model=TicketMessageResponse, summary="Post message to ticket thread")
def add_ticket_message(
    ticket_id: int,
    payload: TicketMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.add_ticket_message(db=db, ticket_id=ticket_id, payload=payload, sender_id=current_user.id)


@router.post("/tickets/escalate", response_model=TicketResponse, summary="Escalate active chat session to a support ticket")
def escalate_chat_to_ticket(
    payload: TicketEscalateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.escalate_chat_to_ticket(db=db, payload=payload, submitted_by_id=current_user.id)


# =============================================================================
# 5. ENTERPRISE SERVICE STATUS & INCIDENTS ENDPOINTS
# =============================================================================

@router.get(
    "/services/status",
    response_model=ServiceStatusOverviewResponse,
    summary="Get enterprise service health and operational incident status",
)
def get_service_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_service_statuses(db=db)


@router.get(
    "/incidents",
    response_model=List[ServiceIncidentItem],
    summary="List active operational service incidents",
)
def list_active_incidents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_active_incidents(db=db)


@router.get(
    "/incidents/{incident_id}",
    response_model=ServiceIncidentItem,
    summary="Get diagnostic timeline for specific incident",
)
def get_incident_detail(
    incident_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_incident_detail(db=db, incident_id=incident_id)


# =============================================================================
# 6. GUIDED SUPPORT REQUEST ANALYSIS ENDPOINTS
# =============================================================================

@router.post(
    "/requests/analyze",
    response_model=SupportRequestAnalysisResponse,
    summary="AI pre-submission analysis with duplicate ticket detection",
)
def analyze_support_request(
    payload: SupportRequestAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.analyze_support_request(db=db, payload=payload)


# =============================================================================
# 7. NOTIFICATION & SUPPORT COMMUNICATION CENTER ENDPOINTS
# =============================================================================

@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="List customer support notifications",
)
def list_notifications(
    filter: Optional[str] = Query(None, description="Filter by type (all, unread, ticket, incident, sla)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.list_notifications(db=db, filter_type=filter)


@router.post(
    "/notifications/{notification_id}/read",
    summary="Mark single notification as read",
)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.mark_notification_read(db=db, notification_id=notification_id)


@router.post(
    "/notifications/read-all",
    summary="Mark all customer support notifications as read",
)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.mark_all_notifications_read(db=db)


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferences,
    summary="Get customer notification preferences",
)
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.get_notification_preferences(db=db)


@router.put(
    "/notifications/preferences",
    response_model=NotificationPreferences,
    summary="Update customer notification preferences",
)
def update_notification_preferences(
    payload: NotificationPreferences,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_dev_or_current_user),
):
    return service.update_notification_preferences(db=db, payload=payload)

