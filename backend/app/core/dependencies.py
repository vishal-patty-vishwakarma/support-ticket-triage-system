from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User
from app.services.ai.base import AIProvider
from app.services.ai.ollama_provider import OllamaProvider

# HTTPBearer scheme extracts Bearer credentials from Authorization header
security_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency that decodes Bearer token and returns the current active User model."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    # SQLAlchemy 2.x user lookup
    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception

    # Reject inactive users
    if not user.is_active:
        raise credentials_exception

    return user


def get_ai_provider() -> AIProvider:
    """Dependency factory returning configured AIProvider instance (overridable in tests)."""
    return OllamaProvider()
