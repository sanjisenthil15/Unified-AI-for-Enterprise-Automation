"""
modules/notifications/schemas.py

Pydantic schemas for the Notifications module.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    type: str
    message: str
    link: Optional[str] = None
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
