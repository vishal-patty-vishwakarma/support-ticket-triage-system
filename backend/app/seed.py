import sys
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import SessionLocal
from app.enums import UserRole
from app.models.team import Team
from app.models.user import User

# Development demo password (never stored as plaintext)
DEMO_PASSWORD = "DemoPass123!"

SEED_TEAMS = [
    {
        "code": "PLATFORM_ENGINEERING",
        "name": "Platform Engineering",
        "description": "Core platform services, APIs, and infrastructure support.",
    },
    {
        "code": "APPLICATION_ENGINEERING",
        "name": "Application Engineering",
        "description": "Application codebase, feature bugs, and frontend/backend logic.",
    },
    {
        "code": "SECURITY",
        "name": "Security",
        "description": "Security vulnerabilities, authentication policies, and compliance.",
    },
    {
        "code": "DEVOPS",
        "name": "DevOps",
        "description": "CI/CD pipelines, container management, and cloud deployments.",
    },
    {
        "code": "DATABASE",
        "name": "Database Team",
        "description": "Database administration, migrations, and performance tuning.",
    },
    {
        "code": "BILLING",
        "name": "Billing Team",
        "description": "Customer subscriptions, invoicing, payments, and refunds.",
    },
    {
        "code": "CUSTOMER_SUPPORT",
        "name": "Customer Support",
        "description": "General customer inquiries and account administration.",
    },
    {
        "code": "PRODUCT",
        "name": "Product Team",
        "description": "Product roadmap feedback, feature requests, and UX recommendations.",
    },
]

SEED_USERS = [
    {
        "email": "demo@support.local",
        "name": "Demo Support Agent",
        "role": UserRole.AGENT.value,
        "is_active": True,
    },
    {
        "email": "alice.platform@support.local",
        "name": "Alice Platform",
        "role": UserRole.AGENT.value,
        "is_active": True,
    },
    {
        "email": "bob.security@support.local",
        "name": "Bob Security",
        "role": UserRole.AGENT.value,
        "is_active": True,
    },
    {
        "email": "carol.manager@support.local",
        "name": "Carol Manager",
        "role": UserRole.MANAGER.value,
        "is_active": True,
    },
    {
        "email": "dave.inactive@support.local",
        "name": "Dave Inactive",
        "role": UserRole.AGENT.value,
        "is_active": False,
    },
]


def seed_database(db: Session) -> dict:
    """Seed teams and users idempotently."""
    teams_created = 0
    users_created = 0

    # 1. Seed Teams
    for team_data in SEED_TEAMS:
        existing = db.query(Team).filter(Team.code == team_data["code"]).first()
        if not existing:
            team = Team(
                code=team_data["code"],
                name=team_data["name"],
                description=team_data["description"],
            )
            db.add(team)
            teams_created += 1

    # 2. Seed Users
    hashed_pw = hash_password(DEMO_PASSWORD)
    for user_data in SEED_USERS:
        existing = db.query(User).filter(User.email == user_data["email"]).first()
        if not existing:
            user = User(
                email=user_data["email"],
                name=user_data["name"],
                password_hash=hashed_pw,
                role=user_data["role"],
                is_active=user_data["is_active"],
            )
            db.add(user)
            users_created += 1

    db.commit()
    return {"teams_created": teams_created, "users_created": users_created}


def main():
    db = SessionLocal()
    try:
        results = seed_database(db)
        print(f"Seeding completed: {results['teams_created']} new teams, {results['users_created']} new users.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
