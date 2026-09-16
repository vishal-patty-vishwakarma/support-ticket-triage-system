from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import TicketStatus

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.ai_analysis import AIAnalysisRun
    from app.models.comment import Comment
    from app.models.team import Team
    from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Original intake fields (description_original is immutable customer content)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description_original: Mapped[str] = mapped_column(Text, nullable=False)
    product_module: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Human-controlled triage values
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    priority_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )

    # Assignment
    assigned_team_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    assigned_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Customer response
    initial_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Workflow
    status: Mapped[str] = mapped_column(
        String(50), default=TicketStatus.OPEN.value, nullable=False
    )

    # Metadata
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by], back_populates="tickets_created"
    )
    recommended_team: Mapped[Optional["Team"]] = relationship(
        "Team", foreign_keys=[recommended_team_id], back_populates="recommended_tickets"
    )
    assigned_team: Mapped[Optional["Team"]] = relationship(
        "Team", foreign_keys=[assigned_team_id], back_populates="assigned_tickets"
    )
    assigned_user: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_user_id], back_populates="tickets_assigned"
    )

    comments: Mapped[List["Comment"]] = relationship(
        "Comment", back_populates="ticket", cascade="all, delete-orphan"
    )
    activities: Mapped[List["Activity"]] = relationship(
        "Activity", back_populates="ticket", cascade="all, delete-orphan"
    )
    ai_analysis_runs: Mapped[List["AIAnalysisRun"]] = relationship(
        "AIAnalysisRun", back_populates="ticket", cascade="all, delete-orphan"
    )
