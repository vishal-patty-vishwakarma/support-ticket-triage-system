from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.teams import router as teams_router
from app.api.tickets import router as tickets_router
from app.api.users import router as users_router

__all__ = ["auth_router", "dashboard_router", "teams_router", "tickets_router", "users_router"]
