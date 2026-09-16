import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth_router, teams_router, tickets_router, users_router
from app.config import get_settings

# Read frontend URL from settings if JWT_SECRET is set, else default fallback for health check
try:
    frontend_url = get_settings().frontend_url
except Exception:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

app = FastAPI(
    title="Support Ticket Triage System API",
    description="AI-assisted customer-support ticket management backend",
    version="0.1.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(users_router)
app.include_router(tickets_router)


@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
