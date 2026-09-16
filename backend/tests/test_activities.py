import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint5"
os.environ["DATABASE_URL"] = "sqlite:///./test_activities_temp.db"

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.activity import Activity
from app.models.ticket import Ticket
from app.seed import seed_database
from app.services import activity_service

TEST_DB_PATH = "test_activities_temp.db"
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
    "customer_name": "Audit Customer",
    "customer_email": "audit@example.com",
    "subject": "System audit logging verification",
    "description": "Verifying that ticket creation writes audit entries transactionally.",
}


# 1. Creating a valid ticket creates exactly one activity
def test_create_ticket_creates_one_activity(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    assert act_res.status_code == 200
    activities = act_res.json()
    assert len(activities) == 1


# 2. Activity type is TICKET_CREATED
def test_activity_type_is_ticket_created(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    activity = act_res.json()[0]
    assert activity["type"] == "TICKET_CREATED"


# 3. Activity ticket_id matches ticket
def test_activity_ticket_id_matches(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    activity = act_res.json()[0]
    assert activity["ticket_id"] == ticket_id


# 4. Activity actor_id matches authenticated user (1)
def test_activity_actor_id_matches(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    activity = act_res.json()[0]
    assert activity["actor_id"] == 1


# 5. Activity actor_name is returned correctly ("Demo Support Agent")
def test_activity_actor_name_populated(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    activity = act_res.json()[0]
    assert activity["actor_name"] == "Demo Support Agent"


# 6. Activity description is "Ticket created"
def test_activity_description_is_ticket_created(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    activity = act_res.json()[0]
    assert activity["description"] == "Ticket created"


# 7. GET /tickets/{id}/activities requires authentication
def test_get_activities_unauthenticated(client):
    res = client.get("/tickets/1/activities")
    assert res.status_code in (401, 403)


# 8. Nonexistent ticket activity endpoint returns 404
def test_get_activities_nonexistent_ticket(client, auth_headers):
    res = client.get("/tickets/999999/activities", headers=auth_headers)
    assert res.status_code == 404
    assert res.json()["detail"] == "Ticket not found"


# 9. Activities are ordered oldest -> newest (created_at ASC, id ASC)
def test_activities_chronological_ordering(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    ticket_id = res.json()["id"]

    # Manually add a second activity
    with TestingSessionLocal() as db:
        activity_service.create_activity(
            db=db,
            ticket_id=ticket_id,
            activity_type="STATUS_CHANGED",
            description="Status updated to Assigned",
            actor_id=1,
        )
        db.commit()

    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=auth_headers)
    assert act_res.status_code == 200
    activities = act_res.json()
    assert len(activities) == 2
    assert activities[0]["type"] == "TICKET_CREATED"
    assert activities[1]["type"] == "STATUS_CHANGED"
    assert activities[0]["id"] < activities[1]["id"]


# 10. No PUT / DELETE activity endpoints exist
def test_no_update_or_delete_activity_routes(client, auth_headers):
    put_res = client.put("/tickets/1/activities/1", headers=auth_headers, json={"description": "hacked"})
    delete_res = client.delete("/tickets/1/activities/1", headers=auth_headers)
    assert put_res.status_code in (404, 405)
    assert delete_res.status_code in (404, 405)


# 11. Simulated activity creation failure rolls back ticket creation (returns 500)
def test_simulated_activity_failure_rolls_back_transaction(client, auth_headers, monkeypatch):
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Database Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)

    unique_subject = "Unique rollback test subject 12345"
    payload = {**VALID_TICKET_PAYLOAD, "subject": unique_subject}

    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 500
    assert res.json()["detail"] == "Unable to create ticket"


# 12. No ticket remains after simulated activity failure
def test_no_ticket_remains_after_rollback(client, auth_headers, monkeypatch):
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Database Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)

    unique_subject = "Unique rollback check subject 67890"
    payload = {**VALID_TICKET_PAYLOAD, "subject": unique_subject}

    client.post("/tickets", json=payload, headers=auth_headers)

    with TestingSessionLocal() as db:
        ticket = db.query(Ticket).filter(Ticket.subject == unique_subject).first()

    assert ticket is None


# 13. Successful ticket creation still returns 201
def test_successful_ticket_creation_returns_201(client, auth_headers):
    res = client.post("/tickets", json=VALID_TICKET_PAYLOAD, headers=auth_headers)
    assert res.status_code == 201
    assert "id" in res.json()
