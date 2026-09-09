"""
models/__init__.py

Imports all ORM models so that SQLAlchemy's metadata is fully populated
before Alembic autogenerate / Base.metadata.create_all() runs.

Import order matters for FK resolution:
  Role → User → JobPosting → Resume, then the remaining domain tables.

NOTE: models/meeting.py is deliberately NOT imported here. The Meeting
Intelligence module replaces it with a full multi-table schema via its
own Alembic migration on the feature/meeting-offline branch.
"""

from models.role        import Role         # noqa: F401
from models.user        import User         # noqa: F401
from models.job_posting import JobPosting   # noqa: F401
from models.resume      import Resume       # noqa: F401
from models.employee    import Employee     # noqa: F401
from models.candidate   import Candidate    # noqa: F401
from models.ticket      import SupportTicket  # noqa: F401
from models.incident    import Incident     # noqa: F401
