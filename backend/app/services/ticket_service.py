from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import ActivityType, TicketStatus
from app.models.team import Team
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketCreate
from app.services import activity_service


def create_ticket(db: Session, ticket_in: TicketCreate, created_by_id: int) -> Ticket:
    """Create a new customer ticket and TICKET_CREATED activity in a single atomic transaction."""
    try:
        ticket = Ticket(
            customer_name=ticket_in.customer_name,
            customer_email=ticket_in.customer_email,
            subject=ticket_in.subject,
            description_original=ticket_in.description,
            product_module=ticket_in.product_module,
            attachment_link=ticket_in.attachment_link,
            status=TicketStatus.OPEN.value,
            created_by=created_by_id,
        )
        db.add(ticket)
        db.flush()

        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.TICKET_CREATED,
            description="Ticket created",
            actor_id=created_by_id,
        )

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise


def get_ticket(db: Session, ticket_id: int) -> Optional[Ticket]:
    """Retrieve a single ticket by primary key ID using SQLAlchemy 2.x db.get()."""
    return db.get(Ticket, ticket_id)


def list_tickets(db: Session) -> List[Ticket]:
    """List all tickets ordered newest first (created_at DESC, id DESC)."""
    stmt = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc())
    return list(db.scalars(stmt).all())


def update_assignment(
    db: Session,
    ticket_id: int,
    fields_set: Set[str],
    team_id: Optional[int],
    user_id: Optional[int],
    actor_id: int,
) -> Optional[Ticket]:
    """Perform partial assignment update on a ticket with atomic audit logging."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        return None

    # Validation: at least one of team_id or user_id must be supplied in request
    if not fields_set or ("team_id" not in fields_set and "user_id" not in fields_set):
        raise ValueError("At least one of team_id or user_id must be provided.")

    # Validate team if supplied
    target_team: Optional[Team] = None
    if "team_id" in fields_set:
        if team_id is None:
            raise ValueError("Explicit null value for team_id is not supported.")
        target_team = db.get(Team, team_id)
        if target_team is None:
            raise ValueError("Invalid team")

    # Validate user if supplied
    target_user: Optional[User] = None
    if "user_id" in fields_set:
        if user_id is None:
            raise ValueError("Explicit null value for user_id is not supported.")
        target_user = db.get(User, user_id)
        if target_user is None:
            raise ValueError("Invalid user")
        if not target_user.is_active:
            raise ValueError("Selected user is inactive")

    try:
        team_changed = False
        user_changed = False

        if "team_id" in fields_set and team_id != ticket.assigned_team_id:
            ticket.assigned_team_id = team_id
            activity_service.create_activity(
                db=db,
                ticket_id=ticket.id,
                activity_type=ActivityType.TEAM_ASSIGNED,
                description=f"Team assigned: {target_team.name}",
                actor_id=actor_id,
            )
            team_changed = True

        if "user_id" in fields_set and user_id != ticket.assigned_user_id:
            ticket.assigned_user_id = user_id
            activity_service.create_activity(
                db=db,
                ticket_id=ticket.id,
                activity_type=ActivityType.USER_ASSIGNED,
                description=f"User assigned: {target_user.name}",
                actor_id=actor_id,
            )
            user_changed = True

        # Automatic status transition from Open -> Assigned
        if ticket.status == TicketStatus.OPEN.value and (team_changed or user_changed):
            old_status = ticket.status
            ticket.status = TicketStatus.ASSIGNED.value
            activity_service.create_activity(
                db=db,
                ticket_id=ticket.id,
                activity_type=ActivityType.STATUS_CHANGED,
                description=f"Status changed from {old_status} to {TicketStatus.ASSIGNED.value}",
                actor_id=actor_id,
            )

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise


def update_status(
    db: Session,
    ticket_id: int,
    new_status: str,
    actor_id: int,
) -> Optional[Ticket]:
    """Update ticket workflow status with atomic audit logging."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        return None

    # If status is identical, do not create duplicate activity or modify database
    if ticket.status == new_status:
        return ticket

    try:
        old_status = ticket.status
        ticket.status = new_status

        # Primary STATUS_CHANGED activity
        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.STATUS_CHANGED,
            description=f"Status changed from {old_status} to {new_status}",
            actor_id=actor_id,
        )

        # Additional activity for Resolved or Closed
        if new_status == TicketStatus.RESOLVED.value:
            activity_service.create_activity(
                db=db,
                ticket_id=ticket.id,
                activity_type=ActivityType.TICKET_RESOLVED,
                description="Ticket resolved",
                actor_id=actor_id,
            )
        elif new_status == TicketStatus.CLOSED.value:
            activity_service.create_activity(
                db=db,
                ticket_id=ticket.id,
                activity_type=ActivityType.TICKET_CLOSED,
                description="Ticket closed",
                actor_id=actor_id,
            )

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise
