"""
Checkpoint 7 — AI workflow integration tests.

FakeAIProvider is injected via FastAPI dependency override so that
tests NEVER require an Ollama server to be running.

Coverage:
  - Auth guard (both endpoints)
  - 404 for nonexistent tickets
  - POST /tickets has no AI dependency
  - Successful AI run: status 201, correct fields, activities created
  - Ticket authoritative fields NOT mutated by AI analysis
  - Retry: second call creates a second run (new id) on same ticket
  - GET /ai-analysis/latest returns newest run
  - Provider failure → 503 (AI_SIMULATE_FAILURE path)
  - Provider failure: run is marked failed, raw_response is null
  - Malformed JSON → 502, run marked failed
  - Invalid category → 502
  - Invalid priority → 502
  - Invalid team code → 502
  - DB-only team validation: valid TeamCode enum but missing DB row → 502
  - Whitespace-only summary → 502
  - raw_response never in public API response
  - error_message null on success
  - error_message populated on failure
  - suggested response fields null on failed run
  - AIAnalysisRunResponse schema fields
  - GET latest with no analysis → 404
  - AI_ANALYSIS_COMPLETED activity created on success
  - AI_ANALYSIS_FAILED activity created on failure
"""
import json
import os
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["JWT_SECRET"] = "test_secret_key_1234567890_checkpoint7"
os.environ["DATABASE_URL"] = "sqlite:///./test_checkpoint7_temp.db"

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

TEST_DB_PATH = "test_checkpoint7_temp.db"
test_engine = create_engine(
    f"sqlite:///./{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


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


# =====================================================================
# Fake providers
# =====================================================================

_VALID_AI_OUTPUT = {
    "summary": "Customer cannot log in due to an authentication error in the payment module.",
    "category": "Authentication",
    "priority": "High",
    "priority_reason": "Multiple users are affected and core functionality is blocked.",
    "recommended_team": "PLATFORM_ENGINEERING",
    "suggested_response": (
        "Thank you for contacting support. We have received your report about the "
        "authentication issue and our team is investigating. We will update you shortly."
    ),
}


class FakeSuccessProvider(AIProvider):
    """Returns a valid AI analysis JSON response."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        return json.dumps(_VALID_AI_OUTPUT)


class FakeProviderFailure(AIProvider):
    """Simulates a provider network/service failure."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        raise AIProviderError("Simulated network failure")


class FakeMalformedJsonProvider(AIProvider):
    """Returns invalid JSON."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        return "NOT VALID JSON {{{{"


class FakeInvalidCategoryProvider(AIProvider):
    """Returns JSON with an invalid category value."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        output = dict(_VALID_AI_OUTPUT)
        output["category"] = "NONEXISTENT_CATEGORY"
        return json.dumps(output)


class FakeInvalidPriorityProvider(AIProvider):
    """Returns JSON with an invalid priority value."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        output = dict(_VALID_AI_OUTPUT)
        output["priority"] = "ULTRAMAX"
        return json.dumps(output)


class FakeInvalidTeamProvider(AIProvider):
    """Returns JSON with a team code not in the TeamCode enum."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        output = dict(_VALID_AI_OUTPUT)
        output["recommended_team"] = "NONEXISTENT_TEAM"
        return json.dumps(output)


class FakeWhitespaceSummaryProvider(AIProvider):
    """Returns JSON with a whitespace-only summary field."""

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        output = dict(_VALID_AI_OUTPUT)
        output["summary"] = "   "
        return json.dumps(output)


# =====================================================================
# Client fixtures
# =====================================================================

def _make_client(provider: AIProvider) -> TestClient:
    """Return a TestClient with db and provider overridden."""
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
def client_malformed():
    c = _make_client(FakeMalformedJsonProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_invalid_category():
    c = _make_client(FakeInvalidCategoryProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_invalid_priority():
    c = _make_client(FakeInvalidPriorityProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_invalid_team():
    c = _make_client(FakeInvalidTeamProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_whitespace():
    c = _make_client(FakeWhitespaceSummaryProvider())
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    token = create_access_token(subject=1)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_ticket_id(client_success, auth_headers):
    """Create a fresh ticket and return its id."""
    res = client_success.post(
        "/tickets",
        json={
            "customer_name": "AI Test Customer",
            "customer_email": "ai_test@example.com",
            "subject": "Cannot log in after recent password reset",
            "description": (
                "After resetting my password via the forgot-password flow, "
                "I can no longer log into the dashboard. This is affecting "
                "my entire team and we cannot access any reports."
            ),
            "product_module": "Authentication",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    return res.json()["id"]


# =====================================================================
# 1. Auth guards
# =====================================================================

def test_analyze_endpoint_requires_auth(client_success):
    """POST /tickets/{id}/analyze must reject unauthenticated requests."""
    res = client_success.post("/tickets/1/analyze")
    assert res.status_code in (401, 403)


def test_latest_analysis_endpoint_requires_auth(client_success):
    """GET /tickets/{id}/ai-analysis/latest must reject unauthenticated requests."""
    res = client_success.get("/tickets/1/ai-analysis/latest")
    assert res.status_code in (401, 403)


# =====================================================================
# 2. Nonexistent ticket → 404
# =====================================================================

def test_analyze_nonexistent_ticket_returns_404(client_success, auth_headers):
    res = client_success.post("/tickets/999999/analyze", headers=auth_headers)
    assert res.status_code == 404


def test_latest_analysis_nonexistent_ticket_returns_404(client_success, auth_headers):
    res = client_success.get("/tickets/999999/ai-analysis/latest", headers=auth_headers)
    assert res.status_code == 404


# =====================================================================
# 3. POST /tickets has no AI dependency
# =====================================================================

def test_create_ticket_has_no_ai_dependency(client_success, auth_headers):
    """POST /tickets must succeed with a non-AI-invoking provider (FakeSuccess is not called)."""
    res = client_success.post(
        "/tickets",
        json={
            "customer_name": "No AI Customer",
            "customer_email": "noai@example.com",
            "subject": "Simple ticket creation test subject",
            "description": "This ticket creation should succeed without touching the AI provider at all.",
        },
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    # Ticket authoritative AI fields must all be null
    assert data["summary"] is None
    assert data["category"] is None
    assert data["priority"] is None


# =====================================================================
# 4. Successful AI analysis run
# =====================================================================

def test_analyze_success_returns_201(client_success, auth_headers, sample_ticket_id):
    res = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert res.status_code == 201


def test_analyze_success_response_contains_expected_fields(client_success, auth_headers, sample_ticket_id):
    res = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["id"] is not None
    assert data["ticket_id"] == sample_ticket_id
    assert data["provider"] == "ollama"
    assert data["model"] == "qwen3:4b"
    assert data["status"] == "success"
    assert data["summary"] == _VALID_AI_OUTPUT["summary"]
    assert data["category"] == _VALID_AI_OUTPUT["category"]
    assert data["priority"] == _VALID_AI_OUTPUT["priority"]
    assert data["priority_reason"] == _VALID_AI_OUTPUT["priority_reason"]
    assert data["recommended_team"] == _VALID_AI_OUTPUT["recommended_team"]
    assert data["suggested_response"] == _VALID_AI_OUTPUT["suggested_response"]
    assert data["error_message"] is None


def test_analyze_success_raw_response_not_in_public_api(client_success, auth_headers, sample_ticket_id):
    """raw_response must never appear in the public API response."""
    res = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert res.status_code == 201
    assert "raw_response" not in res.json()


# =====================================================================
# 5. Ticket authoritative fields NOT mutated by AI analysis
# =====================================================================

def test_analyze_does_not_mutate_ticket_authoritative_fields(client_success, auth_headers, sample_ticket_id):
    """
    After AI analysis, the Ticket row's human-controlled triage fields
    must remain unchanged (null if never set).
    """
    client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)

    # Re-fetch the ticket
    ticket_res = client_success.get(f"/tickets/{sample_ticket_id}", headers=auth_headers)
    assert ticket_res.status_code == 200
    ticket = ticket_res.json()

    # These are the authoritative human-controlled fields — must be untouched
    assert ticket["summary"] is None
    assert ticket["category"] is None
    assert ticket["priority"] is None
    assert ticket["priority_reason"] is None
    assert ticket["recommended_team_id"] is None
    assert ticket["initial_response"] is None


# =====================================================================
# 6. Retry: second call creates a new run
# =====================================================================

def test_retry_creates_new_run(client_success, auth_headers, sample_ticket_id):
    """Each call to analyze creates a new AIAnalysisRun (different id)."""
    res1 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    res2 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] != res2.json()["id"]
    assert res1.json()["ticket_id"] == res2.json()["ticket_id"] == sample_ticket_id


# =====================================================================
# 7. GET /ai-analysis/latest returns newest run
# =====================================================================

def test_latest_returns_most_recent_run(client_success, auth_headers, sample_ticket_id):
    """GET latest must return the most recently created run."""
    run1 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers).json()
    run2 = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers).json()

    latest = client_success.get(f"/tickets/{sample_ticket_id}/ai-analysis/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["id"] == run2["id"]  # newest


def test_latest_raw_response_not_in_public_api(client_success, auth_headers, sample_ticket_id):
    client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    res = client_success.get(f"/tickets/{sample_ticket_id}/ai-analysis/latest", headers=auth_headers)
    assert res.status_code == 200
    assert "raw_response" not in res.json()


def test_latest_no_analysis_returns_404(client_success, auth_headers):
    """GET latest on a ticket with no runs must return 404."""
    # Create a brand-new ticket (no analysis)
    ticket_res = client_success.post(
        "/tickets",
        json={
            "customer_name": "No Analysis Yet",
            "customer_email": "noanalysis@example.com",
            "subject": "Ticket with no AI analysis yet",
            "description": "This ticket has never had AI analysis run on it.",
        },
        headers=auth_headers,
    )
    assert ticket_res.status_code == 201
    ticket_id = ticket_res.json()["id"]

    res = client_success.get(f"/tickets/{ticket_id}/ai-analysis/latest", headers=auth_headers)
    assert res.status_code == 404
    assert "No AI analysis" in res.json()["detail"]


# =====================================================================
# 8. Provider failure → 503
# =====================================================================

def test_provider_failure_returns_503(client_provider_fail, auth_headers):
    # Create ticket using provider_fail client
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Provider Fail Customer",
            "customer_email": "providerfail@example.com",
            "subject": "Provider failure test ticket subject line",
            "description": "Testing that a provider failure produces a 503 response with a safe message.",
        },
        headers=auth_headers,
    )
    assert ticket_res.status_code == 201
    tid = ticket_res.json()["id"]

    res = client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 503
    detail = res.json()["detail"].lower()
    # Must be a sanitized user-safe message
    assert "unavailable" in detail or "retry" in detail or "saved" in detail


def test_provider_failure_marks_run_failed_with_null_raw_response(client_provider_fail, auth_headers):
    """When provider fails before returning any response, raw_response must remain null."""
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Raw Response Null Test",
            "customer_email": "rawnull@example.com",
            "subject": "Raw response null on provider failure",
            "description": "Verifying that raw_response stays null when the provider never responds.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]

    # Call analyze — it will fail with 503
    client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    # Inspect the DB directly to verify raw_response is null
    with TestingSessionLocal() as db:
        run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == tid)
            .order_by(AIAnalysisRun.id.desc())
            .first()
        )
        assert run is not None
        assert run.status == "failed"
        assert run.raw_response is None


def test_provider_failure_error_message_populated(client_provider_fail, auth_headers):
    """Failed run must have a non-null, sanitized error_message in the DB."""
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Error Msg Test",
            "customer_email": "errmsg@example.com",
            "subject": "Verify error message is stored on failure",
            "description": "Testing that error_message is persisted when provider raises AIProviderError.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    with TestingSessionLocal() as db:
        run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == tid)
            .order_by(AIAnalysisRun.id.desc())
            .first()
        )
        assert run.error_message is not None
        assert len(run.error_message.strip()) > 0
        # Must not expose internal exception details — must be a generic safe message
        assert "AIProviderError" not in run.error_message
        assert "Traceback" not in run.error_message


# =====================================================================
# 9. Malformed JSON → 502
# =====================================================================

def test_malformed_json_returns_502(client_malformed, auth_headers):
    ticket_res = client_malformed.post(
        "/tickets",
        json={
            "customer_name": "Malformed JSON Customer",
            "customer_email": "malformed@example.com",
            "subject": "Malformed JSON response test ticket",
            "description": "Testing that unparseable AI output produces a 502 response.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    res = client_malformed.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 502


def test_malformed_json_run_marked_failed(client_malformed, auth_headers):
    """Run must be persisted as 'failed' when model returns malformed JSON."""
    ticket_res = client_malformed.post(
        "/tickets",
        json={
            "customer_name": "Malformed Run Status",
            "customer_email": "malformedstatus@example.com",
            "subject": "Run status check for malformed JSON",
            "description": "Verifying that a failed parse results in a failed run persisted in the DB.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_malformed.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    with TestingSessionLocal() as db:
        run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == tid)
            .order_by(AIAnalysisRun.id.desc())
            .first()
        )
        assert run.status == "failed"


# =====================================================================
# 10. Invalid category → 502
# =====================================================================

def test_invalid_category_returns_502(client_invalid_category, auth_headers):
    ticket_res = client_invalid_category.post(
        "/tickets",
        json={
            "customer_name": "Bad Category Customer",
            "customer_email": "badcategory@example.com",
            "subject": "Invalid category validation test case",
            "description": "Testing that an unknown category value in AI output causes 502.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    res = client_invalid_category.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 502


# =====================================================================
# 11. Invalid priority → 502
# =====================================================================

def test_invalid_priority_returns_502(client_invalid_priority, auth_headers):
    ticket_res = client_invalid_priority.post(
        "/tickets",
        json={
            "customer_name": "Bad Priority Customer",
            "customer_email": "badpriority@example.com",
            "subject": "Invalid priority validation test case",
            "description": "Testing that an unknown priority level in AI output causes 502.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    res = client_invalid_priority.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 502


# =====================================================================
# 12. Invalid team code (not in enum) → 502
# =====================================================================

def test_invalid_team_code_returns_502(client_invalid_team, auth_headers):
    ticket_res = client_invalid_team.post(
        "/tickets",
        json={
            "customer_name": "Bad Team Customer",
            "customer_email": "badteam@example.com",
            "subject": "Invalid team code validation test case",
            "description": "Testing that an unknown team code in AI output causes 502 response.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    res = client_invalid_team.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 502


# =====================================================================
# 13. DB-only team validation: valid enum but missing Team row → 502
# =====================================================================

class FakeValidTeamEnumButMissingDbRow(AIProvider):
    """
    Returns a valid TeamCode enum value, but the corresponding team row
    is deleted from the DB before validation occurs.
    This tests the database-level domain validation.
    """

    def analyze_ticket(
        self, subject: str, description: str, product_module: Optional[str] = None
    ) -> str:
        # PRODUCT is a valid TeamCode enum value
        output = dict(_VALID_AI_OUTPUT)
        output["recommended_team"] = "PRODUCT"
        return json.dumps(output)


def test_valid_team_enum_but_missing_db_row_returns_502():
    """If model returns a valid TeamCode but the DB row is missing, must return 502."""
    from app.models.team import Team

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_ai_provider] = lambda: FakeValidTeamEnumButMissingDbRow()

    try:
        client = TestClient(app)
        token = create_access_token(subject=1)
        headers = {"Authorization": f"Bearer {token}"}

        # Create ticket
        ticket_res = client.post(
            "/tickets",
            json={
                "customer_name": "Missing DB Row Test",
                "customer_email": "missingrow@example.com",
                "subject": "DB team row missing validation test",
                "description": "Test that valid enum but missing DB team row causes 502 and failure run.",
            },
            headers=headers,
        )
        assert ticket_res.status_code == 201
        tid = ticket_res.json()["id"]

        # Delete PRODUCT team from DB
        with TestingSessionLocal() as db:
            product_team = db.query(Team).filter(Team.code == "PRODUCT").first()
            if product_team:
                db.delete(product_team)
                db.commit()

        res = client.post(f"/tickets/{tid}/analyze", headers=headers)
        assert res.status_code == 502

        # Verify run is failed
        with TestingSessionLocal() as db:
            run = (
                db.query(AIAnalysisRun)
                .filter(AIAnalysisRun.ticket_id == tid)
                .order_by(AIAnalysisRun.id.desc())
                .first()
            )
            assert run.status == "failed"

    finally:
        app.dependency_overrides.clear()
        # Restore PRODUCT team
        with TestingSessionLocal() as db:
            existing = db.query(Team).filter(Team.code == "PRODUCT").first()
            if not existing:
                db.add(Team(
                    code="PRODUCT",
                    name="Product Team",
                    description="Product roadmap feedback, feature requests, and UX recommendations.",
                ))
                db.commit()


# =====================================================================
# 14. Whitespace-only summary → 502
# =====================================================================

def test_whitespace_summary_returns_502(client_whitespace, auth_headers):
    ticket_res = client_whitespace.post(
        "/tickets",
        json={
            "customer_name": "Whitespace Customer",
            "customer_email": "whitespace@example.com",
            "subject": "Whitespace summary rejection test ticket",
            "description": "Testing that a whitespace-only summary value in AI output causes 502.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    res = client_whitespace.post(f"/tickets/{tid}/analyze", headers=auth_headers)
    assert res.status_code == 502


# =====================================================================
# 15. Failed run: suggestion fields are null in the public response
# =====================================================================

def test_failed_run_suggestion_fields_null_in_public_response(client_provider_fail, auth_headers):
    """On a failed run, the GET latest must show null for all suggestion fields."""
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Failed Fields Customer",
            "customer_email": "failedfields@example.com",
            "subject": "Testing null suggestion fields on failed run",
            "description": "After a provider failure, suggestion fields should all be null in the response.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    latest = client_provider_fail.get(f"/tickets/{tid}/ai-analysis/latest", headers=auth_headers)
    assert latest.status_code == 200
    data = latest.json()
    assert data["status"] == "failed"
    assert data["summary"] is None
    assert data["category"] is None
    assert data["priority"] is None
    assert data["priority_reason"] is None
    assert data["recommended_team"] is None
    assert data["suggested_response"] is None
    assert data["error_message"] is not None
    assert "raw_response" not in data


# =====================================================================
# 16. Pending run committed before provider is called
# =====================================================================

def test_pending_run_exists_in_db_on_provider_failure(client_provider_fail, auth_headers):
    """After a provider failure, a failed run (not pending) must exist in the DB."""
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Pending Before Provider",
            "customer_email": "pendingbefore@example.com",
            "subject": "Pending run pre-commit verification ticket",
            "description": "Verifying that a run row always exists in DB even when provider fails.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    with TestingSessionLocal() as db:
        run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == tid)
            .first()
        )
        # The run must exist (was committed as pending, then finalized as failed)
        assert run is not None
        assert run.status == "failed"


# =====================================================================
# 17. AI activity events
# =====================================================================

def test_ai_analysis_completed_activity_created_on_success(client_success, auth_headers, sample_ticket_id):
    """Successful run must log AI_ANALYSIS_COMPLETED activity."""
    client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    act_res = client_success.get(f"/tickets/{sample_ticket_id}/activities", headers=auth_headers)
    assert act_res.status_code == 200
    types = [a["type"] for a in act_res.json()]
    assert "AI_ANALYSIS_COMPLETED" in types


def test_ai_analysis_failed_activity_created_on_provider_failure(client_provider_fail, auth_headers):
    """Provider failure must log AI_ANALYSIS_FAILED activity."""
    ticket_res = client_provider_fail.post(
        "/tickets",
        json={
            "customer_name": "Activity Fail Test",
            "customer_email": "actfail@example.com",
            "subject": "AI_ANALYSIS_FAILED activity creation test",
            "description": "Verifying that a provider failure results in AI_ANALYSIS_FAILED activity.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_provider_fail.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    act_res = client_provider_fail.get(f"/tickets/{tid}/activities", headers=auth_headers)
    assert act_res.status_code == 200
    types = [a["type"] for a in act_res.json()]
    assert "AI_ANALYSIS_FAILED" in types


def test_ai_analysis_failed_activity_created_on_validation_failure(client_malformed, auth_headers):
    """Schema validation failure must log AI_ANALYSIS_FAILED activity."""
    ticket_res = client_malformed.post(
        "/tickets",
        json={
            "customer_name": "Validation Fail Activity",
            "customer_email": "valfailact@example.com",
            "subject": "Validation failure activity creation test case",
            "description": "Verifying that malformed AI output causes AI_ANALYSIS_FAILED activity.",
        },
        headers=auth_headers,
    )
    tid = ticket_res.json()["id"]
    client_malformed.post(f"/tickets/{tid}/analyze", headers=auth_headers)

    act_res = client_malformed.get(f"/tickets/{tid}/activities", headers=auth_headers)
    assert act_res.status_code == 200
    types = [a["type"] for a in act_res.json()]
    assert "AI_ANALYSIS_FAILED" in types


# =====================================================================
# 18. AI_SIMULATE_FAILURE environment variable support
# =====================================================================

def test_ai_simulate_failure_env_causes_provider_error(auth_headers):
    """
    With AI_SIMULATE_FAILURE=True in OllamaProvider config, provider raises AIProviderError.
    This verifies the simulate failure path in OllamaProvider itself.
    """
    from app.services.ai.ollama_provider import OllamaProvider

    # Construct an OllamaProvider with forced simulate_failure=True
    provider = OllamaProvider()
    provider.simulate_failure = True

    with pytest.raises(AIProviderError):
        provider.analyze_ticket("Subject", "Description")


# =====================================================================
# 19. OllamaProvider does not require Ollama at import time
# =====================================================================

def test_ollama_provider_instantiation_does_not_require_server():
    """
    Importing and instantiating OllamaProvider must not raise even when no
    Ollama server is running. Connection only happens during analyze_ticket().
    """
    from app.services.ai.ollama_provider import OllamaProvider
    # Should not raise
    provider = OllamaProvider()
    assert provider is not None
    assert hasattr(provider, "analyze_ticket")


# =====================================================================
# 20. AIAnalysisRunResponse schema — required fields present
# =====================================================================

def test_run_response_contains_all_required_schema_fields(client_success, auth_headers, sample_ticket_id):
    """Verify all AIAnalysisRunResponse fields are present in the JSON response."""
    res = client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)
    assert res.status_code == 201
    data = res.json()

    required_fields = [
        "id", "ticket_id", "provider", "model", "summary", "category",
        "priority", "priority_reason", "recommended_team", "suggested_response",
        "status", "error_message", "created_at",
    ]
    for field in required_fields:
        assert field in data, f"Field '{field}' missing from AIAnalysisRunResponse"


# =====================================================================
# 21. Provider returned valid JSON but success run stores raw_response internally
# =====================================================================

def test_success_run_stores_raw_response_internally(client_success, auth_headers, sample_ticket_id):
    """Successful runs must store raw_response in the DB for audit purposes."""
    client_success.post(f"/tickets/{sample_ticket_id}/analyze", headers=auth_headers)

    with TestingSessionLocal() as db:
        run = (
            db.query(AIAnalysisRun)
            .filter(AIAnalysisRun.ticket_id == sample_ticket_id)
            .order_by(AIAnalysisRun.id.desc())
            .first()
        )
        assert run is not None
        assert run.raw_response is not None
        assert len(run.raw_response.strip()) > 0
