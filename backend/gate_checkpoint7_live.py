"""
Checkpoint 7 - Live Integration Gate Script

Exercises the full real code path end-to-end:
  login -> create ticket -> POST /analyze (real OllamaProvider) -> inspect
  -> simulate failure -> inspect failure -> restore

Uses OLLAMA_MODEL=phi:latest (the installed model) because qwen3:4b is not installed.
The code path is identical; only the model binary differs.

Run from backend/ directory:
    python gate_checkpoint7_live.py
"""

import json
import os
import sys
import time

# Force UTF-8 output on Windows consoles
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# -- Environment ---------------------------------------------------------------
os.environ["JWT_SECRET"] = "gate_live_integration_secret_key_1234"
os.environ["DATABASE_URL"] = "sqlite:///./gate_checkpoint7_live.db"
os.environ["OLLAMA_MODEL"] = "phi:latest"   # installed model
os.environ["AI_SIMULATE_FAILURE"] = "false"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models.ai_analysis import AIAnalysisRun
from app.models.ticket import Ticket
from app.seed import seed_database

LIVE_DB = "gate_checkpoint7_live.db"
engine = create_engine(f"sqlite:///./{LIVE_DB}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

ALLOWED_CATEGORIES = {
    "Authentication", "Billing", "Performance", "Data Issue", "Integration",
    "User Interface", "Access Request", "Feature Request", "Security",
    "General Support", "Unknown",
}
ALLOWED_PRIORITIES = {"Low", "Medium", "High", "Critical"}
ALLOWED_TEAM_CODES = {
    "PLATFORM_ENGINEERING", "APPLICATION_ENGINEERING", "SECURITY", "DEVOPS",
    "DATABASE", "BILLING", "CUSTOMER_SUPPORT", "PRODUCT",
}

results = []


def record(label: str, ok: bool, detail: str = ""):
    tag = "[PASS]" if ok else "[FAIL]"
    results.append((label, ok, detail))
    if detail:
        print(f"  {tag}  {label}")
        print(f"         {detail}")
    else:
        print(f"  {tag}  {label}")


def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# -- Setup ---------------------------------------------------------------------
print(f"\n{'='*70}")
print("  CHECKPOINT 7 - LIVE INTEGRATION GATE")
print(f"{'='*70}")

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_database(db)


def override_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
client = TestClient(app)
token = create_access_token(subject=1)
headers = {"Authorization": f"Bearer {token}"}

# ==============================================================================
section("SECTION 1 - Ollama & Model Availability")
# ==============================================================================

import ollama as ollama_lib

try:
    ollama_client = ollama_lib.Client(host="http://localhost:11434")
    models = [m.model for m in ollama_client.list().models]
    qwen_installed = "qwen3:4b" in models
    phi_installed = "phi:latest" in models
    record("Ollama server reachable", True, f"Models: {models}")
    record("qwen3:4b installed", qwen_installed,
           "NOT INSTALLED - using phi:latest as structural substitute" if not qwen_installed else "")
    record("phi:latest installed (fallback)", phi_installed)
    active_model = "phi:latest" if phi_installed else "qwen3:4b"
    print(f"\n  Active model for this gate run: {active_model}")
except Exception as e:
    record("Ollama server reachable", False, str(e))
    print("\nOllama server is unreachable. Aborting live gate.")
    engine.dispose()
    if os.path.exists(LIVE_DB):
        os.remove(LIVE_DB)
    sys.exit(1)

# ==============================================================================
section("SECTION 2 - Application Startup")
# ==============================================================================

r = client.get("/health")
record("/health returns 200", r.status_code == 200, f"-> {r.json()}")

# ==============================================================================
section("SECTION 3 - Authentication")
# ==============================================================================

login_res = client.post("/auth/login", json={"email": "demo@support.local", "password": "DemoPass123!"})
record("POST /auth/login returns 200", login_res.status_code == 200)
login_data = login_res.json()
record("Login returns access_token", "access_token" in login_data)
record("Login token_type = bearer", login_data.get("token_type", "").lower() == "bearer")

# ==============================================================================
section("SECTION 4 - Ticket Creation (no AI)")
# ==============================================================================

ticket_payload = {
    "customer_name": "ABC Enterprises",
    "customer_email": "support@abcenterprises.com",
    "subject": "Production users cannot log in",
    "product_module": "Authentication",
    "description": (
        "After yesterday's production deployment, all users receive an "
        "invalid-token error while logging in. The issue affects every "
        "production account. There is currently no workaround."
    ),
}
ticket_res = client.post("/tickets", json=ticket_payload, headers=headers)
record("POST /tickets returns 201", ticket_res.status_code == 201,
       f"status={ticket_res.status_code}")
ticket_data = ticket_res.json()
ticket_id = ticket_data["id"]
record("Ticket ID assigned", isinstance(ticket_id, int) and ticket_id > 0, f"id={ticket_id}")
record("summary is null after creation", ticket_data["summary"] is None)
record("category is null after creation", ticket_data["category"] is None)
record("priority is null after creation", ticket_data["priority"] is None)
record("priority_reason is null after creation", ticket_data["priority_reason"] is None)
record("recommended_team_id is null after creation", ticket_data["recommended_team_id"] is None)
record("initial_response is null after creation", ticket_data["initial_response"] is None)

print(f"\n  Ticket #{ticket_id} created.")
print(f"  Subject: {ticket_data['subject']}")

# ==============================================================================
section(f"SECTION 5 - Real AI Analysis (model={active_model})")
# ==============================================================================

print(f"\n  Calling POST /tickets/{ticket_id}/analyze with real OllamaProvider...")
print(f"  (This may take 10-90 seconds for the model to respond...)\n")

t0 = time.time()
analyze_res = client.post(f"/tickets/{ticket_id}/analyze", headers=headers, timeout=180)
elapsed = time.time() - t0

print(f"  Provider responded in {elapsed:.1f}s")
record("POST /analyze returns 201", analyze_res.status_code == 201,
       f"status={analyze_res.status_code}" + (
           f"\n         body={analyze_res.text[:400]}" if analyze_res.status_code != 201 else ""
       ))

successful_run_id = None

if analyze_res.status_code == 201:
    ai = analyze_res.json()

    print("\n  -- Raw AI Result ------------------------------------------")
    for k, v in ai.items():
        if k != "raw_response":
            val_str = str(v)
            if len(val_str) > 120:
                val_str = val_str[:120] + "..."
            print(f"  {k:24s}: {val_str}")
    print("  -----------------------------------------------------------\n")

    record("status = success", ai["status"] == "success", f"actual={ai['status']}")
    record("summary is non-empty",
           bool(ai.get("summary") and ai["summary"].strip()),
           f"summary={ai.get('summary', '')[:80]}")
    record("category is allowed value",
           ai.get("category") in ALLOWED_CATEGORIES,
           f"category={ai.get('category')}")
    record("priority is allowed value",
           ai.get("priority") in ALLOWED_PRIORITIES,
           f"priority={ai.get('priority')}")
    record("priority_reason is non-empty",
           bool(ai.get("priority_reason") and ai["priority_reason"].strip()),
           f"priority_reason={ai.get('priority_reason', '')[:80]}")
    record("recommended_team is allowed TeamCode",
           ai.get("recommended_team") in ALLOWED_TEAM_CODES,
           f"recommended_team={ai.get('recommended_team')}")
    record("suggested_response is non-empty",
           bool(ai.get("suggested_response") and ai["suggested_response"].strip()),
           f"suggested_response={ai.get('suggested_response', '')[:80]}")
    record("raw_response NOT in public API response", "raw_response" not in ai)
    record("error_message is null on success", ai.get("error_message") is None)
    record("id is present", isinstance(ai.get("id"), int))
    record("ticket_id matches", ai.get("ticket_id") == ticket_id)
    record("provider = ollama", ai.get("provider") == "ollama")
    record("created_at is present", bool(ai.get("created_at")))

    successful_run_id = ai["id"]

    # Verify DB internals
    with SessionLocal() as db:
        run = db.get(AIAnalysisRun, successful_run_id)
        record("DB: raw_response stored internally on success",
               bool(run and run.raw_response),
               f"len={len(run.raw_response) if run and run.raw_response else 0}")
        record("DB: status = success in DB row",
               run and run.status == "success",
               f"db.status={run.status if run else None}")
        record("DB: recommended_team_code stored",
               bool(run and run.recommended_team_code),
               f"db.recommended_team_code={run.recommended_team_code if run else None}")

    # -- Verify Ticket authoritative fields NOT mutated ----------------------
    section("SECTION 6 - Authoritative Ticket Fields Not Mutated")
    ticket_after = client.get(f"/tickets/{ticket_id}", headers=headers).json()
    record("Ticket.summary still null after AI", ticket_after["summary"] is None)
    record("Ticket.category still null after AI", ticket_after["category"] is None)
    record("Ticket.priority still null after AI", ticket_after["priority"] is None)
    record("Ticket.priority_reason still null after AI", ticket_after["priority_reason"] is None)
    record("Ticket.recommended_team_id still null after AI", ticket_after["recommended_team_id"] is None)
    record("Ticket.initial_response still null after AI", ticket_after["initial_response"] is None)
    record("Ticket.status unchanged (Open)", ticket_after["status"] == "Open",
           f"status={ticket_after['status']}")

    # -- GET /ai-analysis/latest --------------------------------------------
    section("SECTION 7 - GET /ai-analysis/latest")
    latest_res = client.get(f"/tickets/{ticket_id}/ai-analysis/latest", headers=headers)
    record("GET /ai-analysis/latest returns 200", latest_res.status_code == 200)
    if latest_res.status_code == 200:
        latest = latest_res.json()
        record("latest run id matches successful run id",
               latest["id"] == successful_run_id,
               f"latest.id={latest['id']}, expected={successful_run_id}")
        record("latest status = success", latest["status"] == "success")
        record("latest raw_response NOT in public response", "raw_response" not in latest)

    # -- Activity timeline --------------------------------------------------
    section("SECTION 8 - Activity Timeline")
    act_res = client.get(f"/tickets/{ticket_id}/activities", headers=headers)
    record("GET /activities returns 200", act_res.status_code == 200)
    if act_res.status_code == 200:
        activities = act_res.json()
        types = [a["type"] for a in activities]
        print(f"\n  Activity timeline: {types}\n")
        record("TICKET_CREATED activity present", "TICKET_CREATED" in types)
        record("AI_ANALYSIS_COMPLETED activity present", "AI_ANALYSIS_COMPLETED" in types)
        record("No AI_ANALYSIS_FAILED in success timeline", "AI_ANALYSIS_FAILED" not in types)
        if "TICKET_CREATED" in types and "AI_ANALYSIS_COMPLETED" in types:
            i_created = types.index("TICKET_CREATED")
            i_completed = types.index("AI_ANALYSIS_COMPLETED")
            record("TICKET_CREATED precedes AI_ANALYSIS_COMPLETED", i_created < i_completed)

else:
    print(f"\n  WARNING: Analysis returned {analyze_res.status_code}. Skipping dependent checks.")
    print(f"  Response: {analyze_res.text[:500]}")

# ==============================================================================
section("SECTION 9 - Simulated Failure Demonstration")
# ==============================================================================

print("\n  Setting simulate_failure=True on OllamaProvider instance...")

with SessionLocal() as db:
    run_count_before = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == ticket_id).count()
    ticket_count_before = db.query(Ticket).count()

from app.services.ai.ollama_provider import OllamaProvider


def simulated_failure_provider():
    p = OllamaProvider()
    p.simulate_failure = True
    return p


from app.core.dependencies import get_ai_provider
app.dependency_overrides[get_ai_provider] = simulated_failure_provider

fail_res = client.post(f"/tickets/{ticket_id}/analyze", headers=headers)
record("Simulate-failure POST /analyze returns 503",
       fail_res.status_code == 503,
       f"status={fail_res.status_code}, body={fail_res.text[:200]}")

fail_body = {}
try:
    fail_body = fail_res.json()
except Exception:
    pass

record("Error detail is user-safe (no traceback/exception class)",
       "traceback" not in fail_body.get("detail", "").lower()
       and "AIProviderError" not in fail_body.get("detail", ""),
       f"detail={fail_body.get('detail', '')[:120]}")

with SessionLocal() as db:
    failed_run = (
        db.query(AIAnalysisRun)
        .filter(AIAnalysisRun.ticket_id == ticket_id)
        .order_by(AIAnalysisRun.id.desc())
        .first()
    )
    record("New failed AIAnalysisRun created",
           failed_run is not None and (successful_run_id is None or failed_run.id != successful_run_id),
           f"new run id={failed_run.id if failed_run else None}")
    record("Failed run status = failed",
           failed_run and failed_run.status == "failed",
           f"status={failed_run.status if failed_run else None}")
    record("Failed run raw_response is null",
           failed_run is not None and failed_run.raw_response is None,
           f"raw_response={failed_run.raw_response}")
    record("Failed run error_message is non-null and safe",
           failed_run is not None
           and bool(failed_run.error_message)
           and "AIProviderError" not in (failed_run.error_message or "")
           and "Traceback" not in (failed_run.error_message or ""),
           f"error_message={failed_run.error_message[:80] if failed_run and failed_run.error_message else None}")
    failed_run_id = failed_run.id if failed_run else None

act_res2 = client.get(f"/tickets/{ticket_id}/activities", headers=headers)
if act_res2.status_code == 200:
    types2 = [a["type"] for a in act_res2.json()]
    print(f"\n  Activity timeline after failure: {types2}\n")
    record("AI_ANALYSIS_FAILED activity logged", "AI_ANALYSIS_FAILED" in types2)
    record("TICKET_CREATED still present", "TICKET_CREATED" in types2)
    if successful_run_id:
        record("AI_ANALYSIS_COMPLETED still present (prev run preserved)",
               "AI_ANALYSIS_COMPLETED" in types2)

ticket_after_fail = client.get(f"/tickets/{ticket_id}", headers=headers).json()
record("Ticket still accessible after failure", bool(ticket_after_fail.get("id")))
record("Ticket status unchanged by failure", ticket_after_fail["status"] == "Open",
       f"status={ticket_after_fail.get('status')}")

latest_res2 = client.get(f"/tickets/{ticket_id}/ai-analysis/latest", headers=headers)
if latest_res2.status_code == 200:
    latest2 = latest_res2.json()
    record("GET latest -> newest failed run",
           latest2["id"] == failed_run_id,
           f"latest.id={latest2['id']}, failed_run_id={failed_run_id}")
    record("Latest status = failed", latest2["status"] == "failed")
    record("Latest raw_response NOT in public response", "raw_response" not in latest2)

with SessionLocal() as db:
    run_count_after = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == ticket_id).count()
    ticket_count_after = db.query(Ticket).count()

runs_added = run_count_after - run_count_before
record("Exactly 1 new AIAnalysisRun created by failure (no duplicates)",
       runs_added == 1,
       f"runs before={run_count_before}, after={run_count_after}, added={runs_added}")
record("No duplicate Ticket created",
       ticket_count_after == ticket_count_before,
       f"tickets before={ticket_count_before}, after={ticket_count_after}")

# Restore
del app.dependency_overrides[get_ai_provider]
print("\n  AI_SIMULATE_FAILURE restored to false.")

# ==============================================================================
section("SECTION 10 - AIAnalysisRun vs Ticket Row Counts")
# ==============================================================================

with SessionLocal() as db:
    total_tickets = db.query(Ticket).count()
    total_runs = db.query(AIAnalysisRun).count()
    runs_for_ticket = db.query(AIAnalysisRun).filter(AIAnalysisRun.ticket_id == ticket_id).count()
    success_runs = db.query(AIAnalysisRun).filter(
        AIAnalysisRun.ticket_id == ticket_id,
        AIAnalysisRun.status == "success"
    ).count()
    failed_runs_count = db.query(AIAnalysisRun).filter(
        AIAnalysisRun.ticket_id == ticket_id,
        AIAnalysisRun.status == "failed"
    ).count()

print(f"\n  Total Ticket rows          : {total_tickets}")
print(f"  Total AIAnalysisRun rows   : {total_runs}")
print(f"  Runs for ticket #{ticket_id:<10}  : {runs_for_ticket}")
print(f"    -> success runs          : {success_runs}")
print(f"    -> failed runs           : {failed_runs_count}")

record("At least 1 success run exists for ticket", success_runs >= 1, f"count={success_runs}")
record("At least 1 failed run exists for ticket", failed_runs_count >= 1, f"count={failed_runs_count}")
record("Ticket count = 1 (no duplicate)", total_tickets == 1, f"count={total_tickets}")
record("Total AIAnalysisRun rows = success + failed",
       total_runs == success_runs + failed_runs_count,
       f"total={total_runs}, success={success_runs}, failed={failed_runs_count}")

# ==============================================================================
section("FINAL SUMMARY")
# ==============================================================================

passed = sum(1 for _, ok, _ in results if ok)
failed_count_summary = sum(1 for _, ok, _ in results if not ok)

print(f"\n  Total checks : {len(results)}")
print(f"  Passed       : {passed}")
print(f"  Failed       : {failed_count_summary}")

if failed_count_summary > 0:
    print("\n  FAILED CHECKS:")
    for label, ok, detail in results:
        if not ok:
            print(f"    [FAIL]  {label}")
            if detail:
                print(f"            {detail}")

outcome = "ALL CHECKS PASSED" if failed_count_summary == 0 else "SOME CHECKS FAILED"
print(f"\n  *** {outcome} ***")
print(f"{'='*70}\n")

# Cleanup
app.dependency_overrides.clear()
engine.dispose()
if os.path.exists(LIVE_DB):
    os.remove(LIVE_DB)
    print(f"  Temp database '{LIVE_DB}' removed.\n")
