"""
models/ticket.py

SQLAlchemy ORM models for Customer Support module tables:
  1. SupportTeam         (`support_teams`)
  2. SupportCategory     (`support_categories`)
  3. KnowledgeDocument   (`knowledge_documents`)
  4. KnowledgeChunk      (`knowledge_chunks`)
  5. ChatSession         (`chat_sessions`)
  6. ChatMessage         (`chat_messages`)
  7. SupportTicket       (`support_tickets`)
  8. TicketMessage       (`ticket_messages`)

Compatible with MySQL / MariaDB and SQLAlchemy 2.x.
Reuses existing `User` model for submitter/agent relationships.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT, SMALLINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


# =============================================================================
# 1. SUPPORT TEAM
# =============================================================================

class SupportTeam(Base):
    """
    Represents an enterprise team responsible for handling escalated support tickets.
    Examples: Frontend Team, Backend Team, Database Team, Billing / Finance Team,
              Account & Authentication Support Team, General Customer Support Team.
    """

    __tablename__ = "support_teams"

    id = Column(
        SMALLINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    name = Column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Display name of the team, e.g. 'Billing / Finance Team'",
    )
    code = Column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Machine-readable code for routing, e.g. 'billing_finance'",
    )
    description = Column(
        String(255),
        nullable=True,
        comment="Responsibilities and scope of the team",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether tickets can currently be routed to this team",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    categories = relationship("SupportCategory", back_populates="default_team")
    tickets    = relationship("SupportTicket",   back_populates="team")

    def __repr__(self) -> str:
        return f"<SupportTeam id={self.id} code={self.code!r} name={self.name!r}>"


# =============================================================================
# 2. SUPPORT CATEGORY
# =============================================================================

class SupportCategory(Base):
    """
    Represents a classification category for customer support issues.
    Maps customer query topics to default resolution teams.
    Examples: Billing & Payments, Frontend & UI, Backend & APIs,
              Database & Data Integrity, Authentication & Accounts, General Inquiry.
    """

    __tablename__ = "support_categories"

    id = Column(
        SMALLINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    name = Column(
        String(80),
        nullable=False,
        unique=True,
        index=True,
        comment="Category display name, e.g. 'Billing & Payments'",
    )
    description = Column(
        String(255),
        nullable=True,
        comment="Summary of issues that belong in this category",
    )
    default_team_id = Column(
        SMALLINT(unsigned=True),
        ForeignKey("support_teams.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Default team to which tickets in this category are routed",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    default_team = relationship("SupportTeam",       back_populates="categories")
    documents    = relationship("KnowledgeDocument", back_populates="category")
    tickets      = relationship("SupportTicket",     back_populates="category")

    def __repr__(self) -> str:
        return f"<SupportCategory id={self.id} name={self.name!r}>"


# =============================================================================
# 3. KNOWLEDGE BASE DOCUMENTS
# =============================================================================

class KnowledgeDocument(Base):
    """
    Represents a verified enterprise knowledge document, FAQ, or policy.
    Used by the RAG retrieval engine to supply ground truth context to the AI chatbot.
    """

    __tablename__ = "knowledge_documents"

    id = Column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    title = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Title or headline of the knowledge document/article",
    )
    category_id = Column(
        SMALLINT(unsigned=True),
        ForeignKey("support_categories.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Support category this document is associated with",
    )
    doc_type = Column(
        Enum(
            "faq",
            "product_guide",
            "billing_policy",
            "troubleshooting",
            "auth_procedure",
            "general_policy",
        ),
        nullable=False,
        default="faq",
        comment="Type of enterprise document",
    )
    content = Column(
        Text,
        nullable=False,
        comment="Full verified plain-text or markdown content of the document",
    )
    is_published = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Only published documents are searchable by the AI chatbot",
    )
    created_by = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User/Admin who created or authored this document",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    category = relationship("SupportCategory", back_populates="documents")
    creator  = relationship("User",            foreign_keys=[created_by])
    chunks   = relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index.asc()",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument id={self.id} title={self.title!r} type={self.doc_type!r}>"


# =============================================================================
# 4. KNOWLEDGE CHUNKS (FOR RAG RETRIEVAL)
# =============================================================================

class KnowledgeChunk(Base):
    """
    Searchable text chunk extracted from a parent KnowledgeDocument.
    Enables granular semantic/lexical matching during customer query retrieval.
    """

    __tablename__ = "knowledge_chunks"

    id = Column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    document_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("knowledge_documents.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent document from which this chunk was extracted",
    )
    chunk_index = Column(
        Integer,
        nullable=False,
        comment="Sequential index of this chunk within the parent document",
    )
    chunk_text = Column(
        Text,
        nullable=False,
        comment="Cleaned plain-text chunk indexed for search/retrieval",
    )
    keywords = Column(
        String(255),
        nullable=True,
        comment="Extracted topical keywords to boost lexical retrieval accuracy",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document = relationship("KnowledgeDocument", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<KnowledgeChunk id={self.id} doc_id={self.document_id} idx={self.chunk_index}>"


# =============================================================================
# 5. CHAT SESSIONS
# =============================================================================

class ChatSession(Base):
    """
    Represents an ongoing or completed customer support chatbot conversation.
    Preserves context across multiple dialogue turns.
    """

    __tablename__ = "chat_sessions"

    id = Column(
        String(64),
        primary_key=True,
        comment="Unique session UUID string generated by the client or server",
    )
    user_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK -> users.id if customer is logged in; NULL for anonymous/guest sessions",
    )
    customer_name = Column(
        String(120),
        nullable=True,
        comment="Customer display name (provided in chat or extracted from User)",
    )
    customer_email = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Customer contact email for notification and escalation",
    )
    status = Column(
        Enum("active", "resolved", "escalated"),
        nullable=False,
        default="active",
        index=True,
        comment="Current conversation lifecycle status",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user     = relationship("User", foreign_keys=[user_id])
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )
    tickets  = relationship("SupportTicket", back_populates="session")

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id!r} status={self.status!r}>"


# =============================================================================
# 6. CHAT MESSAGES
# =============================================================================

class ChatMessage(Base):
    """
    Represents a single message turn in a customer support conversation.
    Records sender type, text, grounded context, confidence, and escalation state.
    """

    __tablename__ = "chat_messages"

    id = Column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Chat session to which this message belongs",
    )
    sender_type = Column(
        Enum("customer", "ai", "agent"),
        nullable=False,
        comment="'customer' for user queries, 'ai' for bot replies, 'agent' for live support",
    )
    sender_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User ID of sender if authenticated (NULL for AI bot)",
    )
    message = Column(
        Text,
        nullable=False,
        comment="Message content text",
    )
    retrieved_context = Column(
        Text,
        nullable=True,
        comment="JSON string containing citations/knowledge chunks used to answer (internal audit)",
    )
    confidence_score = Column(
        Float,
        nullable=True,
        comment="AI answer confidence score (0.00 to 1.00); NULL for human messages",
    )
    is_escalated = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this message triggered or marks ticket escalation",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    sender  = relationship("User",        foreign_keys=[sender_id])

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} session={self.session_id!r} sender={self.sender_type!r}>"


# =============================================================================
# 7. SUPPORT TICKETS (EXTENDED / REUSED)
# =============================================================================

class SupportTicket(Base):
    """
    Represents an escalated or submitted customer support ticket.
    Reuses the existing `support_tickets` table while enriching it with
    session linking, categorization, team routing, and AI triage metadata.
    """

    __tablename__ = "support_tickets"

    id = Column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Originating chat session if created via AI chatbot escalation",
    )
    category_id = Column(
        SMALLINT(unsigned=True),
        ForeignKey("support_categories.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Detected or assigned issue category",
    )
    team_id = Column(
        SMALLINT(unsigned=True),
        ForeignKey("support_teams.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Enterprise team currently assigned to resolve this ticket",
    )
    submitted_by = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="User account who owns/submitted this ticket",
    )
    assigned_to = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Specific support agent/engineer assigned to this ticket",
    )
    customer_name = Column(
        String(120),
        nullable=True,
        comment="Contact name of the customer",
    )
    customer_email = Column(
        String(255),
        nullable=True,
        index=True,
        comment="Contact email of the customer",
    )
    subject = Column(
        String(255),
        nullable=False,
        comment="Short summary / headline of the customer issue",
    )
    description = Column(
        Text,
        nullable=False,
        comment="Detailed customer description or AI-generated issue synopsis",
    )
    priority = Column(
        Enum("low", "medium", "high", "critical"),
        nullable=False,
        default="medium",
        index=True,
        comment="Severity / urgency priority level",
    )
    status = Column(
        Enum(
            "open",
            "assigned",
            "in_progress",
            "waiting_for_customer",
            "resolved",
            "closed",
            "escalated",
        ),
        nullable=False,
        default="open",
        index=True,
        comment="Current lifecycle status of the ticket",
    )
    channel = Column(
        Enum("web", "email", "chat", "api"),
        nullable=False,
        default="chat",
        comment="Intake channel through which the ticket originated",
    )
    escalation_reason = Column(
        String(255),
        nullable=True,
        comment="Explanation why the AI or customer escalated this ticket",
    )
    ai_summary = Column(
        Text,
        nullable=True,
        comment="AI-generated synopsis of conversation history and customer intent",
    )
    resolved_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when ticket was marked resolved",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    submitter = relationship("User", foreign_keys=[submitted_by])
    agent     = relationship("User", foreign_keys=[assigned_to])
    category  = relationship("SupportCategory", back_populates="tickets")
    team      = relationship("SupportTeam",     back_populates="tickets")
    session   = relationship("ChatSession",     back_populates="tickets")
    messages  = relationship(
        "TicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketMessage.created_at.asc()",
    )

    def __repr__(self) -> str:
        return f"<SupportTicket id={self.id} subject={self.subject!r} status={self.status!r}>"


# =============================================================================
# 8. TICKET MESSAGES (REUSED / EXTENDED)
# =============================================================================

class TicketMessage(Base):
    """
    Represents follow-up dialogue messages exchanged on an active ticket thread
    between customer, support agents, or automated system notices.
    """

    __tablename__ = "ticket_messages"

    id = Column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )
    ticket_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("support_tickets.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Ticket thread to which this message belongs",
    )
    sender_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User ID of sender (NULL for AI/system notices)",
    )
    message = Column(
        Text,
        nullable=False,
        comment="Message body",
    )
    is_ai = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if message was auto-generated by the AI system",
    )
    ai_model = Column(
        String(60),
        nullable=True,
        comment="AI model identifier used if is_ai is True",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User",          foreign_keys=[sender_id])

    def __repr__(self) -> str:
        return f"<TicketMessage id={self.id} ticket_id={self.ticket_id} is_ai={self.is_ai}>"
