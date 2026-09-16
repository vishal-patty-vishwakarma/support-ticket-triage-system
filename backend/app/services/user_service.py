from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def list_assignees(db: Session) -> List[User]:
    """Retrieve active users suitable for assignment, ordered by name ASC."""
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.name.asc())
    return list(db.scalars(stmt).all())
