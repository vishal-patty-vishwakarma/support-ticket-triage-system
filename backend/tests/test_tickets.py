import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint4"
os.environ["DATABASE_URL"] = "sqlite:///./test_tickets_temp.db"

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.ai_analysis import AIAnalysisRun
from app.models.ticket import Ticket
from app.seed import seed_database

TEST_DB_PATH = "test_tickets_temp.db"
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
        seed_database(db)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


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
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Auth headers for seeded demo user (id=1)."""
    token = create_access_token(subject=1)
    return {"Authorization": f"Bearer {token}"}


VALID_TICKET_PAYLOAD = {
    "customer_name": "Jane Support",
    "customer_email": "jane@example.com",
    "subject": "System login fails intermittently",
    "description": "Users are experiencing random HTTP 500 errors when attempting to log in.",
    "product_module": "Authentication Service",
    "attachment_link": "https://example.com/logs/error.log",
}


# 1. Authenticated user can create valid ticket -> 201 Created
def test_create_ticket_authenticated(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["subject"] == VALID_TICKET_PAYLOAD["subject"]


# 2. Created ticket status is Open
def test_created_ticket_status_is_open(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "Open"


# 3. created_by equals authenticated user (user ID 1)
def test_created_by_equals_authenticated_user(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["created_by"] == 1


# 4. AI/triage fields are initially null
def test_initial_triage_fields_are_null(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["summary"] is None
    assert data["category"] is None
    assert data["priority"] is None
    assert data["priority_reason"] is None
    assert data["recommended_team_id"] is None


# 5. Assignment fields are initially null
def test_initial_assignment_fields_are_null(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["assigned_team_id"] is None
    assert data["assigned_user_id"] is None


# 6. POST /tickets does not call any AI provider (no AI runs created)
def test_post_tickets_does_not_call_ai(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    with TestingSessionLocal() as db:
        ai_runs_count = db.query(AIAnalysisRun).count()
    assert ai_runs_count == 0


# 7. description_original exactly preserves submitted description (byte-for-byte including whitespace)
def test_description_original_preserves_exact_text(client, auth_headers):
    exact_description = "   Production users cannot log in after deployment. Please check logs.   "
    payload = {**VALID_TICKET_PAYLOAD, "description": exact_description}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["description_original"] == exact_description


# 8. Blank customer name rejected (422)
def test_blank_customer_name_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "customer_name": "   "}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 9. Customer name >100 rejected (422)
def test_customer_name_too_long_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "customer_name": "A" * 101}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 10. Invalid email format rejected (422)
def test_invalid_customer_email_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "customer_email": "not-an-email"}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 11. Customer email >150 rejected (422)
def test_customer_email_too_long_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "customer_email": ("a" * 140) + "@example.com"}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 12. Subject <10 rejected (422)
def test_subject_too_short_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "subject": "Short"}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 13. Subject >200 rejected (422)
def test_subject_too_long_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "subject": "S" * 201}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 14. Description <30 rejected (422)
def test_description_too_short_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "description": "Too short description"}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 15. Whitespace-only description rejected (422)
def test_whitespace_description_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "description": " " * 40}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 16. Invalid attachment URL rejected (422)
def test_invalid_attachment_url_rejected(client, auth_headers):
    payload = {**VALID_TICKET_PAYLOAD, "attachment_link": "ftp://invalid-url.com"}
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 422


# 17. Unauthenticated POST /tickets returns 401
def test_unauthenticated_post_tickets_returns_401(client):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD)
    assert res.status_code in (401, 403)


# 18. GET /tickets/{id} returns created ticket
def test_get_ticket_by_id(client, auth_headers):
    create_res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = create_res.json()["id"]

    get_res = client.get(f"/tickets/{ticket_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == ticket_id
    assert get_res.json()["subject"] == VALID_TICKET_PAYLOAD["subject"]


# 19. Nonexistent ticket returns 404
def test_get_nonexistent_ticket_returns_404(client, auth_headers):
    res = client.get("/tickets/999999", headers=auth_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Ticket not found"


# 20. GET /tickets returns newest tickets first
def test_get_tickets_returns_newest_first(client, auth_headers):
    p1 = {**VALID_TICKET_PAYLOAD, "subject": "First ticket created"}
    p2 = {**VALID_TICKET_PAYLOAD, "subject": "Second ticket created"}

    r1 = client.post("/tickets", json=p1, headers=auth_headers)
    r2 = client.post("/tickets", json=p2, headers=auth_headers)
    t1_id = r1.json()["id"]
    t2_id = r2.json()["id"]

    list_res = client.get("/tickets", headers=auth_headers)
    assert list_res.status_code == 200
    tickets = list_res.json()
    assert len(tickets) >= 2
    ids = [t["id"] for t in tickets]
    assert ids.index(t2_id) < ids.index(t1_id)


# 21. Unauthenticated GET /tickets returns 401
def test_unauthenticated_get_tickets_returns_401(client):
    res = client.get("/tickets")
    assert res.status_code in (401, 403)


# 22. Client cannot set status/created_by/triage/assignment (extra fields return 422, no ticket created)
def test_extra_forbidden_fields_return_422(client, auth_headers):
    payload_with_extra = {
        **VALID_TICKET_PAYLOAD,
        "status": "Closed",
        "created_by": 99,
        "priority": "Critical",
        "assigned_team_id": 1,
    }
    with TestingSessionLocal() as db:
        db_before_count = db.query(Ticket).count()

    res = client.post("/tickets", json=payload_with_extra, headers=auth_headers)
    assert res.status_code == 422

    with TestingSessionLocal() as db:
        db_after_count = db.query(Ticket).count()

    assert db_before_count == db_after_count
