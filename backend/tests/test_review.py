"""
Checkpoint 8 — Human review of AI suggestions + manual triage fallback.

Tests cover:
  - ACCEPT action (copy AI run fields to ticket)
  - EDIT action (override specific AI run fields)
  - REJECT action (log without modifying ticket)
  - MANUAL action (triage without AI)
  - Validation / ownership rules
  - AIAnalysisRun immutability
  - Ticket intake immutability
  - Transaction rollback
  - Regression for Checkpoint 7
"""
import json
import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint8"
os.environ["DATABASE_URL"] = "sqlite:///./test_checkpoint8_temp.db"

from app.core.dependencies import get_ai_provider
from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.ai_analysis import AIAnalysisRun
from app.models.team import Team
from app.models.ticket import Ticket
from app.seed import seed_database
from app.services import activity_service
from app.services.ai.base import AIProvider
from app.services.ai.exceptions import AIProviderError

# =====================================================================
# Test DB setup
# =====================================================================

TEST_DB_PATH = "test_checkpoint8_temp.db"
test_engine = create_engine(
    f"sqlite:///./{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

_VALID_AI_OUTPUT = {
    "summary": "Authentication service is rejecting valid login tokens after deployment.",
    "category": "Authentication",
    "priority": "High",
    "priority_reason": "Multiple production users are blocked from logging in.",
    "recommended_team": "PLATFORM_ENGINEERING",
    "suggested_response": (
        "Thank you for contacting support. We have received your report and "
        "our team is investigating the authentication issue."
    ),
}


class FakeSuccessProvider(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        return json.dumps(_VALID_AI_OUTPUT)


class FakeProviderFailure(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        raise AIProviderError("Simulated network failure")


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as db:
        seed_database(db)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def _make_client(provider: AIProvider) -> TestClient:
    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_ai_provider] = lambda: provider
    return TestClient(app)


@pytest.fixture
def client_success():
    c = _make_client(FakeSuccessProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_provider_fail():
    c = _make_client(FakeProviderFailure())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    token = create_access_token(subject=1)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_ticket_id(client_success, auth_headers):
    res = client_success.post(
        "/tickets",
        json={
            "customer_name": "Review Test Customer",
            "customer_email": "review@example.com",
            "subject": "Authentication failure after production deployment",
            "description": "After deploying v2.3.1 all users receive invalid token errors when logging into the dashboard.",
            "product_module": "Authentication",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    return res.json()["id"]


@pytest.fixture
def analyzed_ticket_id(client_success, auth_headers, sample_ticket_id):
    """Create a ticket and run successful AI analysis on it."""
    res = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert res.status_code == 201
    run_id = res.json()["id"]
    return sample_ticket_id, run_id


# =====================================================================
# ACCEPT (tests 1-10)
# =====================================================================


def test_accept_copies_summary(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["summary"] == _VALID_AI_OUTPUT["summary"]


def test_accept_copies_category(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["category"] == "Authentication"


def test_accept_copies_priority(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["priority"] == "High"


def test_accept_copies_priority_reason(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["priority_reason"] == _VALID_AI_OUTPUT["priority_reason"]


def test_accept_maps_recommended_team_to_id(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["recommended_team_id"] is not None
    assert isinstance(res.json()["recommended_team_id"], int)


def test_accept_maps_suggested_response_to_initial_response(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["initial_response"] == _VALID_AI_OUTPUT["suggested_response"]


def test_accept_does_not_assign_team(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["assigned_team_id"] is None
    assert res.json()["assigned_user_id"] is None


def test_accept_creates_accepted_activity(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    act_res = client_success.get(f"/tickets/{tid}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "AI_SUGGESTIONS_ACCEPTED" in types


def test_accept_creates_category_changed_when_category_differs(client_success, auth_headers):
    # Create ticket with no AI, then manually set category, then accept AI with different category
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    # Create ticket
    r = c.post("/tickets", json={
        "customer_name": "Cat Change Customer",
        "customer_email": "catchange@example.com",
        "subject": "Category change verification for review endpoint",
        "description": "Testing that accept creates CATEGORY_CHANGED when values differ from existing.",
    }, headers=h)
    tid = r.json()["id"]
    # Analyze
    ar = c.post(f"/tickets/{tid}/analyze", headers=h)
    run_id = ar.json()["id"]
    # Accept
    c.put(f"/tickets/{tid}/review", json={"action": "ACCEPT", "ai_run_id": run_id}, headers=h)
    act_res = c.get(f"/tickets/{tid}/activities", headers=h)
    types = [a["type"] for a in act_res.json()]
    assert "CATEGORY_CHANGED" in types
    assert "PRIORITY_CHANGED" in types


def test_accept_does_not_mutate_ai_analysis_run(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    # Snapshot run before
    with TestingSessionLocal() as db:
        run_before = db.get(AIAnalysisRun, run_id)
        snap_summary = run_before.summary
        snap_category = run_before.category
        snap_status = run_before.status

    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )

    with TestingSessionLocal() as db:
        run_after = db.get(AIAnalysisRun, run_id)
        assert run_after.summary == snap_summary
        assert run_after.category == snap_category
        assert run_after.status == snap_status


# =====================================================================
# EDIT (tests 11-18)
# =====================================================================


def test_edit_one_value_overrides_ai(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={
            "action": "EDIT",
            "ai_run_id": run_id,
            "priority": "Critical",
            "priority_reason": "All production users are blocked.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["priority"] == "Critical"
    assert res.json()["priority_reason"] == "All production users are blocked."
    # Non-edited fields should come from AI
    assert res.json()["category"] == "Authentication"
    assert res.json()["summary"] == _VALID_AI_OUTPUT["summary"]


def test_edit_omitted_fields_use_ai_suggestions(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={
            "action": "EDIT",
            "ai_run_id": run_id,
            "initial_response": "Custom response to customer.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["initial_response"] == "Custom response to customer."
    assert data["summary"] == _VALID_AI_OUTPUT["summary"]
    assert data["category"] == "Authentication"
    assert data["priority"] == "High"
    assert data["priority_reason"] == _VALID_AI_OUTPUT["priority_reason"]


def test_edit_multiple_overrides_applied(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={
            "action": "EDIT",
            "ai_run_id": run_id,
            "priority": "Medium",
            "recommended_team": "APPLICATION_ENGINEERING",
            "initial_response": "We are looking into this issue.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["priority"] == "Medium"
    assert data["initial_response"] == "We are looking into this issue."
    # recommended_team should resolve to APPLICATION_ENGINEERING team ID
    with TestingSessionLocal() as db:
        app_eng = db.query(Team).filter(Team.code == "APPLICATION_ENGINEERING").first()
        assert data["recommended_team_id"] == app_eng.id


def test_edit_recommended_team_maps_correctly(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={
            "action": "EDIT",
            "ai_run_id": run_id,
            "recommended_team": "SECURITY",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    with TestingSessionLocal() as db:
        sec_team = db.query(Team).filter(Team.code == "SECURITY").first()
        assert res.json()["recommended_team_id"] == sec_team.id


def test_edit_creates_edited_activity(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "EDIT", "ai_run_id": run_id, "priority": "Low"},
        headers=auth_headers,
    )
    act_res = client_success.get(f"/tickets/{tid}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "AI_SUGGESTIONS_EDITED" in types


def test_edit_with_zero_override_fields_rejected(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "EDIT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_edit_does_not_mutate_ai_analysis_run(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    with TestingSessionLocal() as db:
        run_before = db.get(AIAnalysisRun, run_id)
        snap = {k: getattr(run_before, k) for k in ["summary", "category", "priority", "status"]}

    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "EDIT", "ai_run_id": run_id, "priority": "Critical"},
        headers=auth_headers,
    )

    with TestingSessionLocal() as db:
        run_after = db.get(AIAnalysisRun, run_id)
        for k, v in snap.items():
            assert getattr(run_after, k) == v


# =====================================================================
# REJECT (tests 19-23)
# =====================================================================


def test_reject_does_not_modify_ticket_triage_fields(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    # Snapshot ticket before rejection
    before = client_success.get(f"/tickets/{tid}", headers=auth_headers).json()
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "REJECT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 200
    after = res.json()
    assert after["summary"] == before["summary"]
    assert after["category"] == before["category"]
    assert after["priority"] == before["priority"]
    assert after["priority_reason"] == before["priority_reason"]
    assert after["recommended_team_id"] == before["recommended_team_id"]
    assert after["initial_response"] == before["initial_response"]


def test_reject_preserves_previous_accepted_values(client_success, auth_headers):
    # Accept first, then reject newer run — original values must survive
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Reject Preserve Customer",
        "customer_email": "reject@example.com",
        "subject": "Reject preserve test with previous accepted values",
        "description": "Verify that rejecting a newer run preserves previously accepted triage values.",
    }, headers=h)
    tid = r.json()["id"]
    # Analyze and accept
    ar1 = c.post(f"/tickets/{tid}/analyze", headers=h)
    run1_id = ar1.json()["id"]
    c.put(f"/tickets/{tid}/review", json={"action": "ACCEPT", "ai_run_id": run1_id}, headers=h)
    # Analyze again (retry)
    ar2 = c.post(f"/tickets/{tid}/analyze", headers=h)
    run2_id = ar2.json()["id"]
    # Reject the second run
    c.put(f"/tickets/{tid}/review", json={"action": "REJECT", "ai_run_id": run2_id}, headers=h)
    # Ticket should still have values from first accepted run
    ticket = c.get(f"/tickets/{tid}", headers=h).json()
    assert ticket["summary"] == _VALID_AI_OUTPUT["summary"]
    assert ticket["category"] == "Authentication"


def test_reject_creates_rejected_activity(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "REJECT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    act_res = client_success.get(f"/tickets/{tid}/activities", headers=auth_headers)
    types = [a["type"] for a in act_res.json()]
    assert "AI_SUGGESTIONS_REJECTED" in types


def test_reject_does_not_modify_ai_analysis_run(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    with TestingSessionLocal() as db:
        run_before = db.get(AIAnalysisRun, run_id)
        snap = {k: getattr(run_before, k) for k in ["summary", "category", "priority", "status"]}

    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "REJECT", "ai_run_id": run_id},
        headers=auth_headers,
    )

    with TestingSessionLocal() as db:
        run_after = db.get(AIAnalysisRun, run_id)
        for k, v in snap.items():
            assert getattr(run_after, k) == v


# =====================================================================
# MANUAL FALLBACK (tests 24-32)
# =====================================================================


def test_manual_works_with_zero_ai_runs(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Manual No AI Customer",
        "customer_email": "manualnoai@example.com",
        "subject": "Manual triage without any prior AI analysis run",
        "description": "Testing that manual triage works when zero AI analysis runs exist.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={
            "action": "MANUAL",
            "summary": "Users cannot log in.",
            "category": "Authentication",
            "priority": "High",
        },
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["summary"] == "Users cannot log in."
    assert res.json()["category"] == "Authentication"
    assert res.json()["priority"] == "High"


def test_manual_works_after_failed_ai_run(client_provider_fail, auth_headers):
    c = client_provider_fail
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Manual After Fail Customer",
        "customer_email": "manualafterfail@example.com",
        "subject": "Manual triage after a failed AI analysis attempt",
        "description": "Testing that manual triage works even when the latest AI analysis failed.",
    }, headers=h)
    tid = r.json()["id"]
    # Attempt analyze — will fail
    c.post(f"/tickets/{tid}/analyze", headers=h)
    # Manual triage should still work
    res = c.put(
        f"/tickets/{tid}/review",
        json={
            "action": "MANUAL",
            "summary": "Manual fallback summary after AI failure.",
            "category": "General Support",
            "priority": "Low",
        },
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["summary"] == "Manual fallback summary after AI failure."


def test_manual_partial_update_preserves_existing_values(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Manual Partial Customer",
        "customer_email": "manualpartial@example.com",
        "subject": "Manual partial update test preserving existing triage values",
        "description": "Testing that manual triage partial updates preserve omitted existing values.",
    }, headers=h)
    tid = r.json()["id"]
    # First manual triage — set category and priority
    c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "category": "Billing", "priority": "Medium"},
        headers=h,
    )
    # Second manual triage — only update priority
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "priority": "Critical"},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["priority"] == "Critical"
    assert res.json()["category"] == "Billing"  # preserved from first manual


def test_manual_invalid_category_rejected(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Invalid Cat Customer",
        "customer_email": "invalidcat@example.com",
        "subject": "Manual triage with invalid category value rejection",
        "description": "Testing that manual triage rejects invalid category values with 422.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "category": "INVALID_CATEGORY"},
        headers=h,
    )
    assert res.status_code == 422


def test_manual_invalid_priority_rejected(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Invalid Pri Customer",
        "customer_email": "invalidpri@example.com",
        "subject": "Manual triage with invalid priority value rejection",
        "description": "Testing that manual triage rejects invalid priority values with 422.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "priority": "MEGA_CRITICAL"},
        headers=h,
    )
    assert res.status_code == 422


def test_manual_recommended_team_maps_correctly(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Team Map Customer",
        "customer_email": "teammap@example.com",
        "subject": "Manual triage recommended team mapping verification",
        "description": "Testing that manual triage correctly resolves team code to team ID.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "recommended_team": "DEVOPS"},
        headers=h,
    )
    assert res.status_code == 200
    with TestingSessionLocal() as db:
        devops = db.query(Team).filter(Team.code == "DEVOPS").first()
        assert res.json()["recommended_team_id"] == devops.id


def test_manual_does_not_invoke_ai_provider(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "No AI Call Customer",
        "customer_email": "noaicall@example.com",
        "subject": "Manual triage must not invoke the AI provider",
        "description": "Verify that manual triage never calls the AI provider even if one is configured.",
    }, headers=h)
    tid = r.json()["id"]
    c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "summary": "Direct manual summary."},
        headers=h,
    )
    with TestingSessionLocal() as db:
        runs = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == tid).count()
    assert runs == 0


def test_manual_creates_triage_updated_activity(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Triage Activity Customer",
        "customer_email": "triageact@example.com",
        "subject": "Manual triage TRIAGE_UPDATED activity verification test",
        "description": "Testing that manual triage creates a TRIAGE_UPDATED activity event.",
    }, headers=h)
    tid = r.json()["id"]
    c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "summary": "Manual summary for activity test."},
        headers=h,
    )
    act_res = c.get(f"/tickets/{tid}/activities", headers=h)
    types = [a["type"] for a in act_res.json()]
    assert "TRIAGE_UPDATED" in types


def test_manual_creates_category_priority_activities_on_change(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Change Activity Customer",
        "customer_email": "changeact@example.com",
        "subject": "Manual triage change activity creation verification",
        "description": "Testing that manual triage creates CATEGORY_CHANGED and PRIORITY_CHANGED activities.",
    }, headers=h)
    tid = r.json()["id"]
    c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "category": "Security", "priority": "Critical"},
        headers=h,
    )
    act_res = c.get(f"/tickets/{tid}/activities", headers=h)
    types = [a["type"] for a in act_res.json()]
    assert "CATEGORY_CHANGED" in types
    assert "PRIORITY_CHANGED" in types


# =====================================================================
# VALIDATION / OWNERSHIP (tests 33-44)
# =====================================================================


def test_unauthenticated_review_rejected(client_success):
    res = client_success.put(
        "/tickets/1/review",
        json={"action": "ACCEPT", "ai_run_id": 1},
    )
    assert res.status_code in (401, 403)


def test_nonexistent_ticket_returns_404(client_success, auth_headers):
    res = client_success.put(
        "/tickets/999999/review",
        json={"action": "ACCEPT", "ai_run_id": 1},
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert "Ticket not found" in res.json()["detail"]


def test_ai_run_from_another_ticket_rejected(client_success, auth_headers):
    # Create two tickets, analyze ticket 1, try to accept run on ticket 2
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r1 = c.post("/tickets", json={
        "customer_name": "Ticket One Customer",
        "customer_email": "ticketone@example.com",
        "subject": "First ticket for cross-ticket ownership test",
        "description": "Verify that accepting an AI run from a different ticket is rejected.",
    }, headers=h)
    r2 = c.post("/tickets", json={
        "customer_name": "Ticket Two Customer",
        "customer_email": "tickettwo@example.com",
        "subject": "Second ticket for cross-ticket ownership test",
        "description": "Verify that accepting an AI run from a different ticket is rejected.",
    }, headers=h)
    tid1 = r1.json()["id"]
    tid2 = r2.json()["id"]
    # Analyze ticket 1
    ar = c.post(f"/tickets/{tid1}/analyze", headers=h)
    run_id = ar.json()["id"]
    # Try to accept run_id on ticket 2
    res = c.put(
        f"/tickets/{tid2}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert "AI analysis not found" in res.json()["detail"]


def test_failed_ai_run_cannot_be_accepted(client_provider_fail, auth_headers):
    c = client_provider_fail
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Failed Run Customer",
        "customer_email": "failedrun@example.com",
        "subject": "Failed AI run cannot be accepted for review",
        "description": "Verify that accepting a failed AI analysis run returns 409 conflict.",
    }, headers=h)
    tid = r.json()["id"]
    c.post(f"/tickets/{tid}/analyze", headers=h)
    # Look up the failed run from DB
    with TestingSessionLocal() as db:
        failed_run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == tid)
            .order_by(AIAnalysisRun.id.desc())
            .first()
        )
        run_id = failed_run.id
    # Try to accept the failed run
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=h,
    )
    assert res.status_code == 409
    assert "Only successful AI analysis can be reviewed" in res.json()["detail"]


def test_pending_ai_run_cannot_be_accepted(client_success, auth_headers):
    # Create a run and manually set it to pending status
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Pending Run Customer",
        "customer_email": "pendingrun@example.com",
        "subject": "Pending AI run cannot be accepted for review",
        "description": "Verify that accepting a pending AI analysis run returns 409 conflict.",
    }, headers=h)
    tid = r.json()["id"]
    with TestingSessionLocal() as db:
        run = AIAnalysisRun(
            ticket_id=tid,
            provider="ollama",
            model="test",
            status="pending",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        pending_id = run.id
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": pending_id},
        headers=h,
    )
    assert res.status_code == 409


def test_missing_ai_run_id_for_accept_rejected(client_success, auth_headers, analyzed_ticket_id):
    tid, _ = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT"},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_missing_ai_run_id_for_edit_rejected(client_success, auth_headers, analyzed_ticket_id):
    tid, _ = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "EDIT", "priority": "High"},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_missing_ai_run_id_for_reject_rejected(client_success, auth_headers, analyzed_ticket_id):
    tid, _ = analyzed_ticket_id
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "REJECT"},
        headers=auth_headers,
    )
    assert res.status_code == 422


def test_ai_run_id_with_manual_rejected(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Manual With Run Customer",
        "customer_email": "manualwithrun@example.com",
        "subject": "Manual triage with ai_run_id must be rejected",
        "description": "Verify that providing ai_run_id with MANUAL action returns 422.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "ai_run_id": 1, "summary": "test"},
        headers=h,
    )
    assert res.status_code == 422


def test_empty_manual_update_rejected(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Empty Manual Customer",
        "customer_email": "emptymanual@example.com",
        "subject": "Manual triage with no triage fields must be rejected",
        "description": "Verify that manual triage with no triage fields returns 422.",
    }, headers=h)
    tid = r.json()["id"]
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL"},
        headers=h,
    )
    assert res.status_code == 422


def test_intake_fields_remain_immutable_after_accept(client_success, auth_headers, analyzed_ticket_id):
    tid, run_id = analyzed_ticket_id
    before = client_success.get(f"/tickets/{tid}", headers=auth_headers).json()
    client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    after = client_success.get(f"/tickets/{tid}", headers=auth_headers).json()
    assert after["customer_name"] == before["customer_name"]
    assert after["customer_email"] == before["customer_email"]
    assert after["subject"] == before["subject"]
    assert after["description_original"] == before["description_original"]
    assert after["product_module"] == before["product_module"]
    assert after["attachment_link"] == before["attachment_link"]
    assert after["created_by"] == before["created_by"]


def test_description_original_unchanged_after_manual(client_success, auth_headers):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    original_desc = "   After deployment users report invalid token errors on every login attempt.   "
    r = c.post("/tickets", json={
        "customer_name": "Desc Immute Customer",
        "customer_email": "descimute@example.com",
        "subject": "Description immutability test after manual review",
        "description": original_desc,
    }, headers=h)
    tid = r.json()["id"]
    c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "summary": "Manual triage with description immutability check."},
        headers=h,
    )
    ticket = c.get(f"/tickets/{tid}", headers=h).json()
    assert ticket["description_original"] == original_desc


# =====================================================================
# TRANSACTION ROLLBACK (tests 48-51)
# =====================================================================


def test_accept_rolls_back_on_activity_failure(client_success, auth_headers, analyzed_ticket_id, monkeypatch):
    tid, run_id = analyzed_ticket_id
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "ACCEPT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 500
    # Ticket triage fields must remain null (rollback)
    with TestingSessionLocal() as db:
        ticket = db.get(Ticket, tid)
        assert ticket.summary is None
        assert ticket.category is None
        assert ticket.priority is None


def test_edit_rolls_back_on_activity_failure(client_success, auth_headers, analyzed_ticket_id, monkeypatch):
    tid, run_id = analyzed_ticket_id
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "EDIT", "ai_run_id": run_id, "priority": "Critical"},
        headers=auth_headers,
    )
    assert res.status_code == 500
    with TestingSessionLocal() as db:
        ticket = db.get(Ticket, tid)
        assert ticket.summary is None
        assert ticket.priority is None


def test_manual_rolls_back_on_activity_failure(client_success, auth_headers, monkeypatch):
    c = client_success
    h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}
    r = c.post("/tickets", json={
        "customer_name": "Rollback Manual Customer",
        "customer_email": "rollback@example.com",
        "subject": "Manual triage rollback verification on activity failure",
        "description": "Testing that manual triage rolls back completely on activity service failure.",
    }, headers=h)
    tid = r.json()["id"]

    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)
    res = c.put(
        f"/tickets/{tid}/review",
        json={"action": "MANUAL", "summary": "Should be rolled back."},
        headers=h,
    )
    assert res.status_code == 500
    with TestingSessionLocal() as db:
        ticket = db.get(Ticket, tid)
        assert ticket.summary is None


def test_reject_rolls_back_on_activity_failure(client_success, auth_headers, analyzed_ticket_id, monkeypatch):
    tid, run_id = analyzed_ticket_id
    def failing_create_activity(*args, **kwargs):
        raise RuntimeError("Simulated Activity Failure")

    monkeypatch.setattr(activity_service, "create_activity", failing_create_activity)
    res = client_success.put(
        f"/tickets/{tid}/review",
        json={"action": "REJECT", "ai_run_id": run_id},
        headers=auth_headers,
    )
    assert res.status_code == 500


# =====================================================================
# REGRESSION (tests 52-54)
# =====================================================================


def test_retry_endpoint_still_works(client_success, auth_headers, sample_ticket_id):
    """Checkpoint 7 retry endpoint is not broken by Checkpoint 8."""
    r1 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    r2 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_post_tickets_still_does_not_call_ai(client_success, auth_headers):
    """POST /tickets must not invoke AI provider."""
    res = client_success.post(
        "/tickets",
        json={
            "customer_name": "No AI Regression Customer",
            "customer_email": "noairegression@example.com",
            "subject": "Regression test that POST /tickets avoids AI",
            "description": "Verify that POST /tickets still does not call the AI provider after checkpoint 8.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["summary"] is None
    assert res.json()["category"] is None
    assert res.json()["priority"] is None
