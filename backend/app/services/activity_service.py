from typing import List, Optional, Union
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.enums import ActivityType
from app.models.activity import Activity


def create_activity(
    db: Session,
    ticket_id: int,
    activity_type: Union[ActivityType, str],
    description: str,
    actor_id: Optional[int] = None,
) -> Activity:
    """Create an activity audit record. Does NOT commit the transaction."""
    type_str = activity_type.value if isinstance(activity_type, ActivityType) else str(activity_type)
    activity = Activity(
        ticket_id=ticket_id,
        type=type_str,
        description=description,
        actor_id=actor_id,
    )
    db.add(activity)
    db.flush()
    return activity


def list_activities(db: Session, ticket_id: int) -> List[Activity]:
    """Retrieve audit timeline for a ticket ordered oldest first, eager-loading actor."""
    stmt = (
        select(Activity)
        .options(joinedload(Activity.actor))
        .where(Activity.ticket_id == ticket_id)
        .order_by(Activity.created_at.asc(), Activity.id.asc())
    )
    return list(db.scalars(stmt).all())
