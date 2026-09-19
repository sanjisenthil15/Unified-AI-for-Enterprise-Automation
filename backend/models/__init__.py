"""
models/__init__.py

Imports all ORM models so that SQLAlchemy's metadata is fully populated
before Base.metadata.create_all() runs on startup.

Import order matters for FK resolution:
  Role → User → JobPosting → Resume → SupportTeam → SupportCategory →
  KnowledgeDocument → KnowledgeChunk → ChatSession → SupportTicket →
  ChatMessage → TicketMessage
"""

from models.role        import Role        # noqa: F401
from models.user        import User        # noqa: F401
from models.job_posting import JobPosting  # noqa: F401
from models.resume      import Resume      # noqa: F401

# Customer Support models
from models.ticket import (                # noqa: F401
    SupportTeam,
    SupportCategory,
    KnowledgeDocument,
    KnowledgeChunk,
    ChatSession,
    ChatMessage,
    SupportTicket,
    TicketMessage,
)
