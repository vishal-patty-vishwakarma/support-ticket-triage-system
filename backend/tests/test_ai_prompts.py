"""
Prompt engineering unit tests.

These tests verify the SYSTEM_PROMPT and build_user_prompt helper without
running any database, network, or Ollama server.
"""

import os
import pytest

# Set required env before importing anything from app
os.environ.setdefault("JWT_SECRET", "prompt_test_secret_key_1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_prompts_temp.db")

from app.services.ai.prompts import SYSTEM_PROMPT, build_user_prompt


# =====================================================================
# SYSTEM PROMPT — Human authority
# =====================================================================

def test_system_prompt_declares_human_authority():
    """System prompt must state that human makes final decisions."""
    lower = SYSTEM_PROMPT.lower()
    assert "human" in lower
    assert "final" in lower or "decision" in lower


def test_system_prompt_is_suggestions_only():
    """System prompt must indicate AI provides suggestions, not commands."""
    lower = SYSTEM_PROMPT.lower()
    assert "suggestion" in lower or "only" in lower or "assistant" in lower


# =====================================================================
# SYSTEM PROMPT — Categories
# =====================================================================

EXPECTED_CATEGORIES = [
    "Authentication",
    "Billing",
    "Performance",
    "Data Issue",
    "Integration",
    "User Interface",
    "Access Request",
    "Feature Request",
    "Security",
    "General Support",
    "Unknown",
]


@pytest.mark.parametrize("category", EXPECTED_CATEGORIES)
def test_system_prompt_contains_category(category):
    """System prompt must enumerate all allowed ticket categories."""
    assert category in SYSTEM_PROMPT, f"Category '{category}' missing from SYSTEM_PROMPT"


# =====================================================================
# SYSTEM PROMPT — Priority definitions
# =====================================================================

EXPECTED_PRIORITIES = ["Low", "Medium", "High", "Critical"]


@pytest.mark.parametrize("priority", EXPECTED_PRIORITIES)
def test_system_prompt_contains_priority_definition(priority):
    """System prompt must define all four priority levels."""
    assert priority in SYSTEM_PROMPT, f"Priority '{priority}' missing from SYSTEM_PROMPT"


def test_system_prompt_contains_critical_definition():
    """System prompt must describe 'Critical' with production/major impact language."""
    lower = SYSTEM_PROMPT.lower()
    assert "production" in lower or "all users" in lower or "blocked" in lower


def test_system_prompt_contains_low_definition():
    """System prompt must describe 'Low' with minimal impact language."""
    lower = SYSTEM_PROMPT.lower()
    assert "minimal" in lower or "workaround" in lower or "informational" in lower


# =====================================================================
# SYSTEM PROMPT — Team codes
# =====================================================================

EXPECTED_TEAM_CODES = [
    "PLATFORM_ENGINEERING",
    "APPLICATION_ENGINEERING",
    "SECURITY",
    "DEVOPS",
    "DATABASE",
    "BILLING",
    "CUSTOMER_SUPPORT",
    "PRODUCT",
]


@pytest.mark.parametrize("team_code", EXPECTED_TEAM_CODES)
def test_system_prompt_contains_team_code(team_code):
    """System prompt must enumerate all allowed team codes."""
    assert team_code in SYSTEM_PROMPT, f"Team code '{team_code}' missing from SYSTEM_PROMPT"


# =====================================================================
# SYSTEM PROMPT — Grounding rules
# =====================================================================

def test_system_prompt_contains_grounding_rule():
    """System prompt must instruct the model to use only supplied ticket information."""
    lower = SYSTEM_PROMPT.lower()
    assert "only" in lower
    # Must mention not inventing or fabricating facts
    assert "invent" in lower or "fabricat" in lower or "unsupported" in lower


def test_system_prompt_prohibits_eta_promise():
    """System prompt must prohibit promising a resolution time."""
    lower = SYSTEM_PROMPT.lower()
    assert "eta" in lower or "resolution time" in lower or "promise" in lower


def test_system_prompt_prohibits_claiming_resolved():
    """System prompt must prohibit claiming the issue is resolved when it is not."""
    lower = SYSTEM_PROMPT.lower()
    assert "resolved" in lower or "not resolved" in lower


def test_system_prompt_prohibits_exposing_internal_info():
    """System prompt must prohibit exposing internal technical information."""
    lower = SYSTEM_PROMPT.lower()
    assert "internal" in lower or "sensitive" in lower


def test_system_prompt_mandates_json_output():
    """System prompt must instruct returning structured JSON only."""
    assert "JSON" in SYSTEM_PROMPT or "json" in SYSTEM_PROMPT.lower()


# =====================================================================
# build_user_prompt — Basic structure
# =====================================================================

def test_build_user_prompt_contains_subject():
    """User prompt must include the ticket subject."""
    prompt = build_user_prompt("Login fails on Chrome", "Description goes here.")
    assert "Login fails on Chrome" in prompt


def test_build_user_prompt_contains_description():
    """User prompt must include the ticket description."""
    prompt = build_user_prompt("Subject", "Customer cannot access their account at all.")
    assert "Customer cannot access their account at all." in prompt


def test_build_user_prompt_with_module_includes_module():
    """User prompt must include product/module when provided."""
    prompt = build_user_prompt("Subject", "Description.", product_module="Authentication Service")
    assert "Authentication Service" in prompt


def test_build_user_prompt_without_module_excludes_module_line():
    """User prompt must not include a blank or None module line when module is absent."""
    prompt = build_user_prompt("Subject", "Description.", product_module=None)
    # Must not have a misleading "None" literal in the output
    assert "None" not in prompt
    # No spurious "Product/Module:" heading
    assert "Product/Module:" not in prompt


def test_build_user_prompt_without_module_string():
    """build_user_prompt with no module arg produces valid prompt."""
    prompt = build_user_prompt("Slow page load", "Dashboard takes over 30 seconds to load.")
    assert "Slow page load" in prompt
    assert "Dashboard takes over 30 seconds" in prompt


def test_build_user_prompt_labels_fields():
    """User prompt must label Subject and Original Description clearly."""
    prompt = build_user_prompt("A subject", "A description.")
    assert "Subject" in prompt
    assert "Description" in prompt


def test_build_user_prompt_returns_string():
    """build_user_prompt must return a non-empty string."""
    result = build_user_prompt("s", "d")
    assert isinstance(result, str)
    assert len(result.strip()) > 0
