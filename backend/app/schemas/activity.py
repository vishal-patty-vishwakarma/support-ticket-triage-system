from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ActivityResponse(BaseModel):
    id: int
    ticket_id: int
    type: str
    description: str
    actor_id: Optional[int] = None
    actor_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
