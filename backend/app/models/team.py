from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    recommended_tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        foreign_keys="[Ticket.recommended_team_id]",
        back_populates="recommended_team"
    )
    assigned_tickets: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        foreign_keys="[Ticket.assigned_team_id]",
        back_populates="assigned_team"
    )
