from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.team import Team


def list_teams(db: Session) -> List[Team]:
    """Retrieve all teams ordered by name ASC."""
    stmt = select(Team).order_by(Team.name.asc())
    return list(db.scalars(stmt).all())
