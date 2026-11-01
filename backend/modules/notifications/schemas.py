"""
modules/notifications/schemas.py

Pydantic schemas for the Notifications module.
"""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    type: str
    category: str = "general"
    message: str
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    total: int
    by_category: Dict[str, int]
