import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint6"
os.environ["DATABASE_URL"] = "sqlite:///./test_checkpoint6_temp.db"

from app.core.security import create_access_token
from app.database import Base, get_db
from app.enums import TicketStatus
from app.main import app
from app.models.activity import Activity
from app.models.comment import Comment
from app.models.ticket import Ticket
from app.seed import seed_database
from app.services import activity_service, comment_service, ticket_service

TEST_DB_PATH = "test_checkpoint6_temp.db"
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


@pytest.fixture
def sample_ticket(client, auth_headers):
    """Helper fixture creating a fresh open ticket."""
    payload = {
        "customer_name": "Checkpoint 6 User",
        "customer_email": "cp6@example.com",
        "subject": "Testing assignment and comments",
        "description": "Comprehensive tests for Checkpoint 6 endpoints and mutations.",
    }
    res = client.post("/tickets", json=payload, headers=auth_headers)
    assert res.status_code == 201
    return res.json()["id"]


# =====================================================================
# TEAMS / USERS LOOKUPS
# =====================================================================

# 1. GET /teams requires authentication
def test_get_teams_unauthenticated(client):
    res = client.get("/teams")
    assert res.status_code in (401, 403)


# 2. GET /teams returns seeded teams
def test_get_teams_authenticated(client, auth_headers):
    res = client.get("/teams", headers=auth_headers)
    assert res.status_code == 200
    teams = res.json()
    assert len(teams) == 8
    codes = [t["code"] for t in teams]
    assert "PLATFORM_ENGINEERING" in codes
    assert "SECURITY" in codes


# 3. GET /users requires authentication
def test_get_users_unauthenticated(client):
    res = client.get("/users")
    assert res.status_code in (401, 403)


# 4. GET /users returns only active users
def test_get_users_returns_active_users_only(client, auth_headers):
    res = client.get("/users", headers=auth_headers)
    assert res.status_code == 200
    users = res.json()
    assert len(users) == 4  # 4 active users out of 5 total seeded
    emails = [u["email"] for u in users]
    assert "demo@support.local" in emails
    assert "dave.inactive@support.local" not in emails


# 5. GET /users never exposes password_hash
def test_get_users_does_not_expose_password_hash(client, auth_headers):
    res = client.get("/users", headers=auth_headers)
    assert res.status_code == 200
    for u in res.json():
        assert "password_hash" not in u
        assert "password" not in u


# =====================================================================
# ASSIGNMENT UPDATES
# =====================================================================

# 6. Assign team successfully (partial update)
def test_assign_team_successfully(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["assigned_team_id"] == 1
    assert data["assigned_user_id"] is None


# 7. Assign active user successfully (partial update preserving team)
def test_assign_user_successfully_partial(client, auth_headers, sample_ticket):
    # First assign team_id = 1
    client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    # Next assign user_id = 2 without team_id
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"user_id": 2}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["assigned_team_id"] == 1  # Team 1 preserved!
    assert data["assigned_user_id"] == 2


# 8. Assign team + user successfully
def test_assign_team_and_user_successfully(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1, "user_id": 2}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["assigned_team_id"] == 1
    assert data["assigned_user_id"] == 2


# 9. Nonexistent team rejected
def test_assign_nonexistent_team_rejected(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 99999}, headers=auth_headers)
    assert res.status_code in (400, 422)


# 10. Nonexistent user rejected
def test_assign_nonexistent_user_rejected(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"user_id": 99999}, headers=auth_headers)
    assert res.status_code in (400, 422)


# 11. Inactive user rejected
def test_assign_inactive_user_rejected(client, auth_headers, sample_ticket):
    # dave.inactive@support.local has ID 5
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"user_id": 5}, headers=auth_headers)
    assert res.status_code in (400, 422)
    assert "inactive" in res.json()["detail"].lower()


# 12. Both team_id and user_id null / omitted rejected
def test_assign_empty_payload_rejected(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={}, headers=auth_headers)
    assert res.status_code in (400, 422)


# 13. Assigning Open ticket changes status to Assigned
def test_assigning_open_ticket_changes_status_to_assigned(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "Assigned"


# 14. Assigning In Progress ticket does not move it backwards
def test_assigning_in_progress_ticket_does_not_move_backwards(client, auth_headers, sample_ticket):
    # Move to In Progress
    client.put(f"/tickets/{sample_ticket}/status", json={"status": "In Progress"}, headers=auth_headers)

    # Reassign team
    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 2}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "In Progress"


# 15. TEAM_ASSIGNED activity created
def test_team_assigned_activity_created(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "TEAM_ASSIGNED" in types


# 16. USER_ASSIGNED activity created
def test_user_assigned_activity_created(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/assignment", json={"user_id": 2}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "USER_ASSIGNED" in types


# 17. Automatic Open -> Assigned logs STATUS_CHANGED
def test_open_to_assigned_logs_status_changed(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    descriptions = [a["description"] for a in act_res.json()]
    assert any("Status changed from Open to Assigned" in d for d in descriptions)


# 18. Submitting same existing assignment does not create duplicate assignment activity
def test_identical_assignment_no_duplicate_activity(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    act_res1 = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    count1 = len(act_res1.json())

    # Submit same team_id again
    client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    act_res2 = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    count2 = len(act_res2.json())

    assert count1 == count2


# 19. Assignment mutation + activities rollback together on simulated failure
def test_assignment_failure_rolls_back(client, auth_headers, sample_ticket, monkeypatch):
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)

    res = client.put(f"/tickets/{sample_ticket}/assignment", json={"team_id": 1}, headers=auth_headers)
    assert res.status_code == 500

    # Verify assigned_team_id remains null in DB
    with TestingSessionLocal() as db:
        ticket = db.get(Ticket, sample_ticket)
        assert ticket.assigned_team_id is None


# =====================================================================
# STATUS UPDATES
# =====================================================================

# 20. Valid status update succeeds
def test_valid_status_update(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/status", json={"status": "In Progress"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "In Progress"


# 21. Invalid status rejected
def test_invalid_status_rejected(client, auth_headers, sample_ticket):
    res = client.put(f"/tickets/{sample_ticket}/status", json={"status": "NotAStatus"}, headers=auth_headers)
    assert res.status_code == 422


# 22. Nonexistent ticket status update returns 404
def test_status_update_nonexistent_ticket(client, auth_headers):
    res = client.put("/tickets/999999/status", json={"status": "In Progress"}, headers=auth_headers)
    assert res.status_code == 404


# 23. Actual status change creates STATUS_CHANGED activity
def test_status_changed_activity(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/status", json={"status": "In Progress"}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    descriptions = [a["description"] for a in act_res.json()]
    assert any("Status changed from Open to In Progress" in d for d in descriptions)


# 24. Submitting same status does not create duplicate activity
def test_same_status_no_duplicate_activity(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/status", json={"status": "In Progress"}, headers=auth_headers)
    c1 = len(client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers).json())

    client.put(f"/tickets/{sample_ticket}/status", json={"status": "In Progress"}, headers=auth_headers)
    c2 = len(client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers).json())
    assert c1 == c2


# 25. Resolved creates TICKET_RESOLVED
def test_status_resolved_creates_activity(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/status", json={"status": "Resolved"}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "TICKET_RESOLVED" in types


# 26. Closed creates TICKET_CLOSED
def test_status_closed_creates_activity(client, auth_headers, sample_ticket):
    client.put(f"/tickets/{sample_ticket}/status", json={"status": "Closed"}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "TICKET_CLOSED" in types


# 27. Status mutation + activity rollback together on simulated failure
def test_status_failure_rolls_back(client, auth_headers, sample_ticket, monkeypatch):
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)

    res = client.put(f"/tickets/{sample_ticket}/status", json={"status": "Resolved"}, headers=auth_headers)
    assert res.status_code == 500

    with TestingSessionLocal() as db:
        ticket = db.get(Ticket, sample_ticket)
        assert ticket.status == "Open"  # Status remains Open!


# =====================================================================
# INTERNAL COMMENTS
# =====================================================================

# 28. Valid internal comment creation succeeds
def test_create_comment_succeeds(client, auth_headers, sample_ticket):
    body = "Checked auth logs. Issue began after latest deployment."
    res = client.post(f"/tickets/{sample_ticket}/comments", json={"body": body}, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["body"] == body
    assert data["author_id"] == 1


# 29. Comment author is authenticated user
def test_comment_author_is_authenticated_user(client, auth_headers, sample_ticket):
    res = client.post(f"/tickets/{sample_ticket}/comments", json={"body": "Investigating issue..."}, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["author_name"] == "Demo Support Agent"


# 30. Blank comment rejected (422)
def test_blank_comment_rejected(client, auth_headers, sample_ticket):
    res = client.post(f"/tickets/{sample_ticket}/comments", json={"body": "   "}, headers=auth_headers)
    assert res.status_code == 422


# 31. Nonexistent ticket comment rejected (404)
def test_comment_nonexistent_ticket_rejected(client, auth_headers):
    res = client.post("/tickets/999999/comments", json={"body": "Hello"}, headers=auth_headers)
    assert res.status_code == 404


# 32. COMMENT_ADDED activity created
def test_comment_added_activity_created(client, auth_headers, sample_ticket):
    client.post(f"/tickets/{sample_ticket}/comments", json={"body": "New internal note"}, headers=auth_headers)
    act_res = client.get(f"/tickets/{sample_ticket}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "COMMENT_ADDED" in types


# 33. Comment + activity rollback together on simulated failure
def test_comment_failure_rolls_back(client, auth_headers, sample_ticket, monkeypatch):
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)

    res = client.post(f"/tickets/{sample_ticket}/comments", json={"body": "Rollback test"}, headers=auth_headers)
    assert res.status_code == 500

    with TestingSessionLocal() as db:
        comments = db.query(Comment).filter(Comment.ticket_id == sample_ticket).all()
        assert len(comments) == 0


# 34. GET comments ordered oldest -> newest
def test_get_comments_chronological_ordering(client, auth_headers, sample_ticket):
    client.post(f"/tickets/{sample_ticket}/comments", json={"body": "First comment"}, headers=auth_headers)
    client.post(f"/tickets/{sample_ticket}/comments", json={"body": "Second comment"}, headers=auth_headers)

    res = client.get(f"/tickets/{sample_ticket}/comments", headers=auth_headers)
    assert res.status_code == 200
    comments = res.json()
    assert len(comments) == 2
    assert comments[0]["body"] == "First comment"
    assert comments[1]["body"] == "Second comment"


# 35. GET comments includes author_name
def test_get_comments_includes_author_name(client, auth_headers, sample_ticket):
    client.post(f"/tickets/{sample_ticket}/comments", json={"body": "Comment text"}, headers=auth_headers)
    res = client.get(f"/tickets/{sample_ticket}/comments", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()[0]["author_name"] == "Demo Support Agent"


# 36. Comments cannot be edited or deleted
def test_comments_cannot_be_edited_or_deleted(client, auth_headers, sample_ticket):
    put_res = client.put(f"/tickets/{sample_ticket}/comments/1", json={"body": "edited"}, headers=auth_headers)
    del_res = client.delete(f"/tickets/{sample_ticket}/comments/1", headers=auth_headers)
    assert put_res.status_code in (404, 405)
    assert del_res.status_code in (404, 405)
