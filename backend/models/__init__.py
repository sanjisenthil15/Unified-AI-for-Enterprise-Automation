"""
models/__init__.py

Imports all ORM models so that SQLAlchemy's metadata is fully populated
before Alembic autogenerate / Base.metadata.create_all() runs.

Import order matters for FK resolution:
  Role → User → JobPosting → Resume → Department → Employee →
  Attendance/Sprint/Chat/Notifications → SupportTeam → SupportCategory →
  KnowledgeDocument → KnowledgeChunk → ChatSession → SupportTicket →
  ChatMessage → TicketMessage
"""

from models.role        import Role         # noqa: F401
from models.user        import User         # noqa: F401
from models.job_posting import JobPosting   # noqa: F401
from models.resume      import Resume       # noqa: F401
from models.department  import Department   # noqa: F401
from models.project      import Project     # noqa: F401
from models.employee    import Employee     # noqa: F401
from models.candidate   import Candidate    # noqa: F401
from models.incident    import Incident, IncidentTimeline, IncidentAITriage  # noqa: F401

# Attendance, Sprints, Manager Chat & Notifications (feature/workforce-tracking)
from models.attendance             import Attendance            # noqa: F401
from models.sprint                 import Sprint                # noqa: F401
from models.sprint_task            import SprintTask             # noqa: F401
from models.sprint_task_snapshot   import SprintTaskSnapshot     # noqa: F401
from models.manager_chat_thread    import ManagerChatThread      # noqa: F401
from models.manager_chat_message   import ManagerChatMessage     # noqa: F401
from models.notification           import Notification           # noqa: F401

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

# --- Meeting Intelligence (feature/meeting-offline) --- #
from models.meeting                    import Meeting                    # noqa: F401
from models.meeting_participant        import MeetingParticipant         # noqa: F401
from models.meeting_speaker            import MeetingSpeaker             # noqa: F401
from models.meeting_transcript         import MeetingTranscript          # noqa: F401
from models.meeting_transcript_segment import MeetingTranscriptSegment   # noqa: F401
from models.meeting_analysis           import MeetingAnalysis            # noqa: F401
from models.meeting_action_item        import MeetingActionItem          # noqa: F401
