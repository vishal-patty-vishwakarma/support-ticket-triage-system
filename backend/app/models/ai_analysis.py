from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import AIAnalysisStatus

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class AIAnalysisRun(Base):
    __tablename__ = "ai_analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    priority_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_team_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    suggested_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=AIAnalysisStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationship
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="ai_analysis_runs")

    @property
    def recommended_team(self) -> Optional[str]:
        return self.recommended_team_code

    # Composite indexes for fast queries when fetching latest AI analysis attempt per ticket
    __table_args__ = (
        Index("ix_ai_analysis_runs_ticket_created", "ticket_id", "created_at"),
        Index("ix_ai_analysis_runs_ticket_id_id", "ticket_id", "id"),
    )
