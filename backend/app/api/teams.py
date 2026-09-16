from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.team import TeamResponse
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("", response_model=List[TeamResponse])
def get_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all seeded teams ordered by name ASC."""
    return team_service.list_teams(db)
