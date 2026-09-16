from pydantic import BaseModel, ConfigDict

from app.schemas.ticket import TicketResponse


class DashboardStats(BaseModel):
    open_count: int
    assigned_count: int
    in_progress_count: int
    critical_count: int
    resolved_count: int
    total_count: int
    recent_tickets: list[TicketResponse]

    model_config = ConfigDict(from_attributes=True)
