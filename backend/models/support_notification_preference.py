"""
models/support_notification_preference.py

Per-user Customer Support notification preferences. One row per user,
created on first save; a user without a row gets the defaults (all on).
Replaces a single in-memory dict that every user shared and could
overwrite for everyone.
"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, text
from sqlalchemy.sql import func

from config.database import Base

SUPPORT_PREFERENCE_FIELDS = ("email_notifications", "ticket_updates", "sla_alerts", "incident_alerts", "agent_replies")


class SupportNotificationPreference(Base):
    __tablename__ = "support_notification_preferences"

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        primary_key=True,
    )
    email_notifications = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    ticket_updates = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    sla_alerts = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    incident_alerts = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    agent_replies = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
