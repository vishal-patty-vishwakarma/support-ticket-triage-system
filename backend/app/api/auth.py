from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user with email/password and return JWT bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # SQLAlchemy 2.x user lookup by email
    stmt = select(User).where(User.email == login_data.email)
    user = db.scalars(stmt).first()

    # Reject non-existent user, incorrect password, or inactive user with generic message
    if user is None:
        raise credentials_exception

    if not verify_password(login_data.password, user.password_hash):
        raise credentials_exception

    if not user.is_active:
        raise credentials_exception

    # Generate JWT access token
    access_token = create_access_token(subject=user.id)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return profile information for the authenticated current user."""
    return current_user
