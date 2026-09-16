from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import UserRole

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.comment import Comment
    from app.models.ticket import Ticket


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default=UserRole.AGENT.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tickets_created: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        foreign_keys="[Ticket.created_by]",
        back_populates="creator"
    )
    tickets_assigned: Mapped[List["Ticket"]] = relationship(
        "Ticket",
        foreign_keys="[Ticket.assigned_user_id]",
        back_populates="assigned_user"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment",
        back_populates="author"
    )
    activities: Mapped[List["Activity"]] = relationship(
        "Activity",
        back_populates="actor"
    )
