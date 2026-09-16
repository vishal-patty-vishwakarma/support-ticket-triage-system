from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import AssigneeUserResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[AssigneeUserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve active users suitable for assignment, ordered by name ASC."""
    return user_service.list_assignees(db)
