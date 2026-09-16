from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import TicketPriority, TicketStatus
from app.models.ticket import Ticket


def get_dashboard_stats(db: Session) -> dict:
    """Return ticket status and priority counts plus the 5 most recent tickets."""
    status_counts = {}
    for status in TicketStatus:
        count = db.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == status.value)
        )
        status_counts[status.value] = count or 0

    critical_count = db.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.priority == TicketPriority.CRITICAL.value)
    ) or 0

    total_count = db.scalar(select(func.count()).select_from(Ticket)) or 0

    recent_tickets_stmt = (
        select(Ticket)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(5)
    )
    recent_tickets = list(db.scalars(recent_tickets_stmt).all())

    return {
        "open_count": status_counts.get(TicketStatus.OPEN.value, 0),
        "assigned_count": status_counts.get(TicketStatus.ASSIGNED.value, 0),
        "in_progress_count": status_counts.get(TicketStatus.IN_PROGRESS.value, 0),
        "critical_count": critical_count,
        "resolved_count": status_counts.get(TicketStatus.RESOLVED.value, 0),
        "total_count": total_count,
        "recent_tickets": recent_tickets,
    }
