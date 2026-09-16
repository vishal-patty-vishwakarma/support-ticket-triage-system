"""
Checkpoint 12 — Integration-level workflow tests.

High-value scenario tests covering:
  1. Golden path: login → create → AI → accept → assign → comment → resolve → dashboard
  2. AI failure + manual recovery: full workflow after provider failure
  3. Human authority: accept run #1, reject run #2, verify run #1 retained
  4. Retry history: 3 runs on same ticket, latest returns #3
  5. Raw AI data leakage regression
"""
import json
import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint12"
os.environ["DATABASE_URL"] = "sqlite:///./test_checkpoint12_temp.db"

from app.core.dependencies import get_ai_provider
from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.ai_analysis import AIAnalysisRun
from app.models.ticket import Ticket
from app.seed import seed_database
from app.services.ai.base import AIProvider
from app.services.ai.exceptions import AIProviderError

# =====================================================================
# Test DB setup
# =====================================================================

TEST_DB_PATH = "test_checkpoint12_temp.db"
test_engine = create_engine(
    f"sqlite:///./{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

_VALID_AI_OUTPUT = {
    "summary": "Authentication service is rejecting valid tokens after deployment.",
    "category": "Authentication",
    "priority": "High",
    "priority_reason": "Multiple users are blocked from logging in.",
    "recommended_team": "PLATFORM_ENGINEERING",
    "suggested_response": "Thank you for contacting support. We are investigating.",
}

_SECOND_AI_OUTPUT = {
    "summary": "Token validation service has a race condition under load.",
    "category": "Performance",
    "priority": "Critical",
    "priority_reason": "Affects all authenticated endpoints during peak traffic.",
    "recommended_team": "APPLICATION_ENGINEERING",
    "suggested_response": "We have identified the root cause and are deploying a fix.",
}

_THIRD_AI_OUTPUT = {
    "summary": "Resolved race condition in token validation service.",
    "category": "Performance",
    "priority": "Low",
    "priority_reason": "Fix deployed and verified in staging.",
    "recommended_team": "APPLICATION_ENGINEERING",
    "suggested_response": "The issue has been resolved. Please verify on your end.",
}


class FakeSuccessProvider(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        return json.dumps(_VALID_AI_OUTPUT)


class FakeSecondProvider(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        return json.dumps(_SECOND_AI_OUTPUT)


class FakeThirdProvider(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        return json.dumps(_THIRD_AI_OUTPUT)


class FakeProviderFailure(AIProvider):
    def analyze_ticket(self, subject: str, description: str, product_module: Optional[str] = None) -> str:
        raise AIProviderError("Simulated Ollama connection refused")


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


# =====================================================================
# 1. Golden path integration test
# =====================================================================


class TestGoldenPath:
    def test_full_workflow_login_to_dashboard(self):
        """Exercise the complete golden path through the HTTP API."""
        c = _make_client(FakeSuccessProvider())
        h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}

        # 1. Create ticket
        r = c.post("/tickets", json={
            "customer_name": "Golden Path Customer",
            "customer_email": "golden@example.com",
            "subject": "Golden path integration test with full workflow coverage",
            "description": "This is a detailed description for the golden path integration test.",
            "product_module": "Auth Service",
        }, headers=h)
        assert r.status_code == 201
        tid = r.json()["id"]
        original_desc = r.json()["description_original"]

        # 2. Verify ticket is Open, untriaged
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["status"] == "Open"
        assert ticket["summary"] is None
        assert ticket["category"] is None
        assert ticket["priority"] is None
        assert ticket["assigned_team_id"] is None
        assert ticket["assigned_user_id"] is None

        # 3. Successful AI analysis
        ar = c.post(f"/tickets/{tid}/analyze", headers=h)
        assert ar.status_code == 201
        run_id = ar.json()["id"]
        assert ar.json()["status"] == "success"

        # 4. Verify ticket still untriaged (AI suggestions are separate)
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["summary"] is None
        assert ticket["category"] is None

        # 5. ACCEPT AI suggestions
        res = c.put(f"/tickets/{tid}/review", json={
            "action": "ACCEPT", "ai_run_id": run_id,
        }, headers=h)
        assert res.status_code == 200
        ticket = res.json()
        assert ticket["summary"] == _VALID_AI_OUTPUT["summary"]
        assert ticket["category"] == "Authentication"
        assert ticket["priority"] == "High"
        assert ticket["recommended_team_id"] is not None

        # 6. Assign team + user
        teams = c.get("/teams", headers=h).json()
        users = c.get("/users", headers=h).json()
        team_id = teams[0]["id"]
        user_id = users[0]["id"]

        res = c.put(f"/tickets/{tid}/assignment", json={
            "team_id": team_id, "user_id": user_id,
        }, headers=h)
        assert res.status_code == 200
        assert res.json()["assigned_team_id"] == team_id
        assert res.json()["assigned_user_id"] == user_id

        # 7. Status → In Progress
        res = c.put(f"/tickets/{tid}/status", json={"status": "In Progress"}, headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "In Progress"

        # 8. Add comment
        res = c.post(f"/tickets/{tid}/comments", json={
            "body": "Investigating the authentication issue now.",
        }, headers=h)
        assert res.status_code == 201
        assert res.json()["body"] == "Investigating the authentication issue now."

        # 9. Status → Resolved
        res = c.put(f"/tickets/{tid}/status", json={"status": "Resolved"}, headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "Resolved"

        # 10. Verify activity timeline
        acts = c.get(f"/tickets/{tid}/activities", headers=h).json()
        act_types = [a["type"] for a in acts]
        assert "TICKET_CREATED" in act_types
        assert "AI_ANALYSIS_COMPLETED" in act_types
        assert "AI_SUGGESTIONS_ACCEPTED" in act_types
        assert "TEAM_ASSIGNED" in act_types
        assert "USER_ASSIGNED" in act_types
        assert "STATUS_CHANGED" in act_types
        assert "COMMENT_ADDED" in act_types

        # 11. Verify comments
        comments = c.get(f"/tickets/{tid}/comments", headers=h).json()
        assert len(comments) == 1
        assert comments[0]["body"] == "Investigating the authentication issue now."

        # 12. Verify AI run preserved
        ai_run = c.get(f"/tickets/{tid}/ai-analysis/latest", headers=h).json()
        assert ai_run["id"] == run_id
        assert ai_run["status"] == "success"

        # 13. Verify original description unchanged
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["description_original"] == original_desc

        # 14. Verify dashboard stats
        stats = c.get("/dashboard/stats", headers=h).json()
        assert stats["resolved_count"] >= 1
        assert stats["total_count"] >= 1
        resolved_tickets = [t for t in stats["recent_tickets"] if t["id"] == tid]
        assert len(resolved_tickets) == 1
        assert resolved_tickets[0]["status"] == "Resolved"


# =====================================================================
# 2. AI failure + manual recovery
# =====================================================================


class TestAIFailureManualRecovery:
    def test_full_workflow_after_provider_failure(self):
        """Exercise the complete AI failure → manual recovery workflow."""
        c = _make_client(FakeProviderFailure())
        h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}

        # 1. Create ticket
        r = c.post("/tickets", json={
            "customer_name": "AI Fail Customer",
            "customer_email": "aifail@example.com",
            "subject": "AI failure and manual recovery integration test",
            "description": "Testing that the workflow continues after AI provider failure.",
        }, headers=h)
        assert r.status_code == 201
        tid = r.json()["id"]

        # 2. AI analysis fails
        ar = c.post(f"/tickets/{tid}/analyze", headers=h)
        assert ar.status_code == 503

        # 3. Verify failed AIAnalysisRun persists
        runs = c.get(f"/tickets/{tid}/ai-analysis/latest", headers=h)
        # The latest endpoint returns 404 if the run failed (status != success)
        # But the run should exist in the database
        with TestingSessionLocal() as db:
            db_runs = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == tid).all()
            assert len(db_runs) == 1
            assert db_runs[0].status == "failed"

        # 4. Verify ticket still exists and is untriaged
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["id"] == tid
        assert ticket["summary"] is None
        assert ticket["status"] == "Open"

        # 5. MANUAL review succeeds
        res = c.put(f"/tickets/{tid}/review", json={
            "action": "MANUAL",
            "summary": "Manual triage after AI failure.",
            "category": "General Support",
            "priority": "Medium",
        }, headers=h)
        assert res.status_code == 200
        assert res.json()["summary"] == "Manual triage after AI failure."
        assert res.json()["category"] == "General Support"

        # 6. Assignment succeeds
        teams = c.get("/teams", headers=h).json()
        users = c.get("/users", headers=h).json()
        res = c.put(f"/tickets/{tid}/assignment", json={
            "team_id": teams[0]["id"], "user_id": users[0]["id"],
        }, headers=h)
        assert res.status_code == 200

        # 7. Comment succeeds
        res = c.post(f"/tickets/{tid}/comments", json={
            "body": "Working on this after AI failure.",
        }, headers=h)
        assert res.status_code == 201

        # 8. Status update succeeds
        res = c.put(f"/tickets/{tid}/status", json={"status": "In Progress"}, headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "In Progress"

        # 9. Verify no duplicate ticket
        with TestingSessionLocal() as db:
            tickets = db.query(Ticket).filter(Ticket.id == tid).all()
            assert len(tickets) == 1

        # 10. Verify AI_ANALYSIS_FAILED activity exists
        acts = c.get(f"/tickets/{tid}/activities", headers=h).json()
        act_types = [a["type"] for a in acts]
        assert "AI_ANALYSIS_FAILED" in act_types
        assert "TRIAGE_UPDATED" in act_types

        # 11. Verify ticket has human manual values
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["summary"] == "Manual triage after AI failure."
        assert ticket["category"] == "General Support"
        assert ticket["priority"] == "Medium"
        assert ticket["assigned_team_id"] is not None
        assert ticket["assigned_user_id"] is not None


# =====================================================================
# 3. Human authority regression
# =====================================================================


class TestHumanAuthority:
    def test_accept_then_reject_preserves_accepted_values(self):
        """Accept run #1, reject run #2, verify run #1 values retained."""
        c = _make_client(FakeSuccessProvider())
        h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}

        # Create ticket
        r = c.post("/tickets", json={
            "customer_name": "Authority Customer",
            "customer_email": "authority@example.com",
            "subject": "Human authority regression test for multi-run scenario",
            "description": "Verify that rejecting a later run preserves previously accepted values.",
        }, headers=h)
        tid = r.json()["id"]

        # AI run #1 → ACCEPT
        ar1 = c.post(f"/tickets/{tid}/analyze", headers=h)
        run1_id = ar1.json()["id"]
        res = c.put(f"/tickets/{tid}/review", json={
            "action": "ACCEPT", "ai_run_id": run1_id,
        }, headers=h)
        assert res.status_code == 200
        assert res.json()["summary"] == _VALID_AI_OUTPUT["summary"]
        assert res.json()["category"] == "Authentication"

        # AI run #2 → REJECT
        ar2 = c.post(f"/tickets/{tid}/analyze", headers=h)
        run2_id = ar2.json()["id"]
        res = c.put(f"/tickets/{tid}/review", json={
            "action": "REJECT", "ai_run_id": run2_id,
        }, headers=h)
        assert res.status_code == 200

        # Verify run #1 values still on ticket
        ticket = c.get(f"/tickets/{tid}", headers=h).json()
        assert ticket["summary"] == _VALID_AI_OUTPUT["summary"]
        assert ticket["category"] == "Authentication"
        assert ticket["priority"] == "High"

        # Verify both runs preserved in DB
        with TestingSessionLocal() as db:
            runs = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == tid).all()
            assert len(runs) == 2
            run1 = next(r for r in runs if r.id == run1_id)
            run2 = next(r for r in runs if r.id == run2_id)
            assert run1.status == "success"
            assert run2.status == "success"

        # Verify rejection activity
        acts = c.get(f"/tickets/{tid}/activities", headers=h).json()
        act_types = [a["type"] for a in acts]
        assert "AI_SUGGESTIONS_ACCEPTED" in act_types
        assert "AI_SUGGESTIONS_REJECTED" in act_types


# =====================================================================
# 4. Retry history
# =====================================================================


class TestRetryHistory:
    def test_three_runs_latest_returns_newest(self):
        """Same ticket: 3 AI runs, latest endpoint returns run #3."""
        c = _make_client(FakeSuccessProvider())
        h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}

        # Create ticket
        r = c.post("/tickets", json={
            "customer_name": "Retry Customer",
            "customer_email": "retry@example.com",
            "subject": "Retry history test with multiple AI analysis runs",
            "description": "Testing that the latest endpoint returns the most recent run.",
        }, headers=h)
        tid = r.json()["id"]

        # Run #1
        ar1 = c.post(f"/tickets/{tid}/analyze", headers=h)
        run1_id = ar1.json()["id"]
        assert ar1.json()["status"] == "success"

        # Run #2
        ar2 = c.post(f"/tickets/{tid}/analyze", headers=h)
        run2_id = ar2.json()["id"]
        assert ar2.json()["status"] == "success"
        assert run2_id != run1_id

        # Run #3
        ar3 = c.post(f"/tickets/{tid}/analyze", headers=h)
        run3_id = ar3.json()["id"]
        assert ar3.json()["status"] == "success"
        assert run3_id != run2_id

        # Latest returns run #3
        latest = c.get(f"/tickets/{tid}/ai-analysis/latest", headers=h).json()
        assert latest["id"] == run3_id

        # All 3 runs exist
        with TestingSessionLocal() as db:
            runs = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == tid).all()
            assert len(runs) == 3
            run_ids = {r.id for r in runs}
            assert run1_id in run_ids
            assert run2_id in run_ids
            assert run3_id in run_ids

        # Exactly one ticket
        with TestingSessionLocal() as db:
            tickets = db.query(Ticket).filter(Ticket.id == tid).all()
            assert len(tickets) == 1


# =====================================================================
# 5. Raw AI data leakage regression
# =====================================================================


class TestRawDataLeakage:
    def test_raw_response_not_in_analyze_response(self):
        """Verify raw_response is never exposed in public API."""
        c = _make_client(FakeSuccessProvider())
        h = {"Authorization": f"Bearer {create_access_token(subject=1)}"}

        r = c.post("/tickets", json={
            "customer_name": "Leakage Customer",
            "customer_email": "leakage@example.com",
            "subject": "Raw data leakage regression test for AI responses",
            "description": "Verifying that raw_response is never exposed in public API responses.",
        }, headers=h)
        tid = r.json()["id"]

        ar = c.post(f"/tickets/{tid}/analyze", headers=h)
        assert ar.status_code == 201
        assert "raw_response" not in ar.json()

        latest = c.get(f"/tickets/{tid}/ai-analysis/latest", headers=h)
        assert "raw_response" not in latest.json()
