from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import TeamCode, TicketCategory, TicketPriority


class AIAnalysisOutput(BaseModel):
    summary: str
    category: TicketCategory
    priority: TicketPriority
    priority_reason: str
    recommended_team: TeamCode
    suggested_response: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("summary", "priority_reason", "suggested_response")
    @classmethod
    def validate_non_whitespace(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be blank or whitespace-only.")
        return v


class AIAnalysisRunResponse(BaseModel):
    id: int
    ticket_id: int
    provider: str
    model: str
    summary: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    priority_reason: Optional[str] = None
    recommended_team: Optional[str] = None  # Populated from recommended_team_code
    suggested_response: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
