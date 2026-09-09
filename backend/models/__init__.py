"""
models/__init__.py

Imports all ORM models so that SQLAlchemy's metadata is fully populated
before Alembic autogenerate / Base.metadata.create_all() runs.

Import order matters for FK resolution:
  Role → User → JobPosting → Resume, then the remaining domain tables.
The Meeting Intelligence tables (models.meeting*) FK into users and employees.
"""

from models.role        import Role         # noqa: F401
from models.user        import User         # noqa: F401
from models.job_posting import JobPosting   # noqa: F401
from models.resume      import Resume       # noqa: F401
from models.employee    import Employee     # noqa: F401
from models.candidate   import Candidate    # noqa: F401
from models.ticket      import SupportTicket  # noqa: F401
from models.incident    import Incident     # noqa: F401

# --- Meeting Intelligence (feature/meeting-offline) --- #
from models.meeting                    import Meeting                    # noqa: F401
from models.meeting_participant        import MeetingParticipant         # noqa: F401
from models.meeting_speaker            import MeetingSpeaker             # noqa: F401
from models.meeting_transcript         import MeetingTranscript          # noqa: F401
from models.meeting_transcript_segment import MeetingTranscriptSegment   # noqa: F401
from models.meeting_analysis           import MeetingAnalysis            # noqa: F401
from models.meeting_action_item        import MeetingActionItem          # noqa: F401
