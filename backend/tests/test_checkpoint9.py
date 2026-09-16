"""Tests for Checkpoint 9: Dashboard stats API and ticket search/filter APIs."""
import os
import pytest

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint9"
os.environ["DATABASE_URL"] = "sqlite:///./test_checkpoint9_temp.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.team import Team
from app.models.ticket import Ticket
from app.models.user import User
from app.enums import TicketStatus, TicketPriority, TicketCategory, TeamCode

TEST_DB_PATH = "test_checkpoint9_temp.db"
test_engine = create_engine(
    f"sqlite:///./{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Create fresh schema and seed test data before running tests."""
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        db.add(User(id=1, name="Test User", email="test@example.com", password_hash="hashed", is_active=True))
        db.add(User(id=2, name="Agent User", email="agent@example.com", password_hash="hashed", is_active=True))
        db.add(Team(id=1, code=TeamCode.BILLING.value, name="Billing Team"))
        db.add(Team(id=2, code=TeamCode.SECURITY.value, name="Security Team"))
        db.commit()
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture(autouse=True)
def clean_tickets():
    """Remove all tickets before each test to avoid cross-test data bleed."""
    with TestingSessionLocal() as db:
        db.query(Ticket).delete()
        db.commit()
    yield


@pytest.fixture
def client():
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_access_token(subject=1)}"}


def _create_ticket(db, subject="Test ticket for dashboard stats and search", status=TicketStatus.OPEN, priority=None, category=None, assigned_team_id=None, assigned_user_id=None, customer_name="Test Customer", customer_email="test@example.com", description_original="A detailed description for testing dashboard statistics and search functionality across the ticket system."):
    ticket = Ticket(
        customer_name=customer_name,
        customer_email=customer_email,
        subject=subject,
        description_original=description_original,
        status=status.value,
        priority=priority.value if priority else None,
        category=category.value if category else None,
        assigned_team_id=assigned_team_id,
        assigned_user_id=assigned_user_id,
        created_by=1,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


# ─── Dashboard Stats Tests ──────────────────────────────────────

def test_dashboard_stats_requires_auth(client):
    r = client.get("/dashboard/stats")
    assert r.status_code == 401


def test_dashboard_stats_returns_200(client, auth_headers):
    r = client.get("/dashboard/stats", headers=auth_headers)
    assert r.status_code == 200


def test_dashboard_stats_empty_database(client, auth_headers):
    r = client.get("/dashboard/stats", headers=auth_headers)
    data = r.json()
    assert data["open_count"] == 0
    assert data["assigned_count"] == 0
    assert data["in_progress_count"] == 0
    assert data["critical_count"] == 0
    assert data["resolved_count"] == 0
    assert data["total_count"] == 0
    assert data["recent_tickets"] == []


def test_dashboard_stats_counts_by_status(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Open ticket one for dashboard count test", status=TicketStatus.OPEN)
        _create_ticket(db, subject="Open ticket two for dashboard count test", status=TicketStatus.OPEN)
        _create_ticket(db, subject="Assigned ticket for dashboard count test", status=TicketStatus.ASSIGNED)
        _create_ticket(db, subject="In Progress ticket for dashboard count test", status=TicketStatus.IN_PROGRESS)
        _create_ticket(db, subject="Resolved ticket for dashboard count test", status=TicketStatus.RESOLVED)
    r = client.get("/dashboard/stats", headers=auth_headers)
    data = r.json()
    assert data["open_count"] == 2
    assert data["assigned_count"] == 1
    assert data["in_progress_count"] == 1
    assert data["resolved_count"] == 1
    assert data["total_count"] == 5


def test_dashboard_stats_critical_count(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Critical priority ticket for dashboard stats test", priority=TicketPriority.CRITICAL)
        _create_ticket(db, subject="High priority ticket for dashboard stats test", priority=TicketPriority.HIGH)
        _create_ticket(db, subject="Another critical ticket for dashboard stats test", priority=TicketPriority.CRITICAL)
    r = client.get("/dashboard/stats", headers=auth_headers)
    data = r.json()
    assert data["critical_count"] == 2
    assert data["total_count"] == 3


def test_dashboard_stats_recent_tickets_limit(client, auth_headers):
    with TestingSessionLocal() as db:
        for i in range(7):
            _create_ticket(db, subject=f"Dashboard recent tickets limit test ticket number {i}")
    r = client.get("/dashboard/stats", headers=auth_headers)
    data = r.json()
    assert len(data["recent_tickets"]) == 5
    assert data["total_count"] == 7


def test_dashboard_stats_recent_tickets_newest_first(client, auth_headers):
    with TestingSessionLocal() as db:
        t1 = _create_ticket(db, subject="First created ticket for dashboard ordering test")
        t2 = _create_ticket(db, subject="Second created ticket for dashboard ordering test")
        t3 = _create_ticket(db, subject="Third created ticket for dashboard ordering test")
        t1_id, t2_id, t3_id = t1.id, t2.id, t3.id
    r = client.get("/dashboard/stats", headers=auth_headers)
    ids = [t["id"] for t in r.json()["recent_tickets"]]
    assert ids == [t3_id, t2_id, t1_id]


def test_dashboard_stats_response_has_required_fields(client, auth_headers):
    r = client.get("/dashboard/stats", headers=auth_headers)
    data = r.json()
    for field in ["open_count", "assigned_count", "in_progress_count", "critical_count", "resolved_count", "total_count", "recent_tickets"]:
        assert field in data


# ─── Search Tests ───────────────────────────────────────────────

def test_search_by_subject(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Login authentication failure for SSO integration")
        _create_ticket(db, subject="Billing invoice discrepancy report")
    r = client.get("/tickets", params={"search": "authentication"}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert "authentication" in r.json()[0]["subject"].lower()


def test_search_by_customer_name(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, customer_name="Alice Johnson", subject="Alice login issue for search test")
        _create_ticket(db, customer_name="Bob Smith", subject="Bob billing issue for search test")
    r = client.get("/tickets", params={"search": "Alice"}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["customer_name"] == "Alice Johnson"


def test_search_by_customer_email(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, customer_email="alice@corp.com", subject="Email search test for alice Corp")
        _create_ticket(db, customer_email="bob@corp.com", subject="Email search test for bob Corp")
    r = client.get("/tickets", params={"search": "alice@corp.com"}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["customer_email"] == "alice@corp.com"


def test_search_by_description(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Database connection timeout issue", description_original="Detailed description about database connection pool exhaustion in production environment causing timeouts and errors.")
        _create_ticket(db, subject="UI rendering bug report", description_original="Detailed description about CSS flex layout breaking on mobile devices with specific viewport widths.")
    r = client.get("/tickets", params={"search": "database"}, headers=auth_headers)
    assert len(r.json()) == 1
    assert "database" in r.json()[0]["description_original"].lower()


def test_search_by_ticket_id(client, auth_headers):
    with TestingSessionLocal() as db:
        t = _create_ticket(db, subject="Ticket ID search test for specific lookup")
    r = client.get("/tickets", params={"search": str(t.id)}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == t.id


def test_search_no_results(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Existing ticket for empty search result test")
    r = client.get("/tickets", params={"search": "nonexistent_term"}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 0


def test_search_case_insensitive(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Case Insensitive Search Test For Mixed Case Query")
    r = client.get("/tickets", params={"search": "CASE INSENSITIVE"}, headers=auth_headers)
    assert len(r.json()) == 1


# ─── Filter Tests ───────────────────────────────────────────────

def test_filter_by_status(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Open ticket for status filter test", status=TicketStatus.OPEN)
        _create_ticket(db, subject="Assigned ticket for status filter test", status=TicketStatus.ASSIGNED)
        _create_ticket(db, subject="Another open ticket for status filter test", status=TicketStatus.OPEN)
    r = client.get("/tickets", params={"status": "Open"}, headers=auth_headers)
    assert len(r.json()) == 2
    assert all(t["status"] == "Open" for t in r.json())


def test_filter_by_category(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Billing category ticket for filter test", category=TicketCategory.BILLING)
        _create_ticket(db, subject="Security category ticket for filter test", category=TicketCategory.SECURITY)
    r = client.get("/tickets", params={"category": "Billing"}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["category"] == "Billing"


def test_filter_by_priority(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Critical priority filter test ticket", priority=TicketPriority.CRITICAL)
        _create_ticket(db, subject="Low priority filter test ticket", priority=TicketPriority.LOW)
        _create_ticket(db, subject="Another critical filter test ticket", priority=TicketPriority.CRITICAL)
    r = client.get("/tickets", params={"priority": "Critical"}, headers=auth_headers)
    assert len(r.json()) == 2
    assert all(t["priority"] == "Critical" for t in r.json())


def test_filter_by_assigned_team(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Team 1 assigned ticket for team filter test", assigned_team_id=1)
        _create_ticket(db, subject="Team 2 assigned ticket for team filter test", assigned_team_id=2)
    r = client.get("/tickets", params={"assigned_team_id": 1}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["assigned_team_id"] == 1


def test_filter_by_assigned_user(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="User 1 assigned ticket for user filter test", assigned_user_id=1)
        _create_ticket(db, subject="User 2 assigned ticket for user filter test", assigned_user_id=2)
    r = client.get("/tickets", params={"assigned_user_id": 1}, headers=auth_headers)
    assert len(r.json()) == 1
    assert r.json()[0]["assigned_user_id"] == 1


def test_combined_search_and_filter(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Combined search and filter test open billing", status=TicketStatus.OPEN, category=TicketCategory.BILLING)
        _create_ticket(db, subject="Combined search and filter test open security", status=TicketStatus.OPEN, category=TicketCategory.SECURITY)
        _create_ticket(db, subject="Combined search and filter test assigned billing", status=TicketStatus.ASSIGNED, category=TicketCategory.BILLING)
    r = client.get("/tickets", params={"search": "combined", "status": "Open"}, headers=auth_headers)
    assert len(r.json()) == 2
    assert all(t["status"] == "Open" for t in r.json())


def test_filter_no_results(client, auth_headers):
    with TestingSessionLocal() as db:
        _create_ticket(db, subject="Existing ticket for filter no results test")
    r = client.get("/tickets", params={"status": "Closed"}, headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 0


def test_list_tickets_unauthenticated(client):
    r = client.get("/tickets")
    assert r.status_code == 401


def test_dashboard_stats_unauthenticated(client):
    r = client.get("/dashboard/stats")
    assert r.status_code == 401
