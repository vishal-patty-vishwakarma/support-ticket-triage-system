from typing import Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    ActivityType,
    AIAnalysisStatus,
    ReviewAction,
    TicketCategory,
    TicketPriority,
    TeamCode,
)
from app.models.ai_analysis import AIAnalysisRun
from app.models.team import Team
from app.models.ticket import Ticket
from app.schemas.ticket import TicketReviewRequest
from app.services import activity_service


class ReviewError(Exception):
    """Raised when a review operation fails with a user-safe message."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def process_review(
    db: Session,
    ticket_id: int,
    review: TicketReviewRequest,
    actor_id: int,
) -> Ticket:
    """Process a human review of AI suggestions or manual triage."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise ReviewError(404, "Ticket not found")

    action = review.action

    if action == ReviewAction.ACCEPT:
        return _handle_accept(db, ticket, review, actor_id)
    elif action == ReviewAction.EDIT:
        return _handle_edit(db, ticket, review, actor_id)
    elif action == ReviewAction.REJECT:
        return _handle_reject(db, ticket, review, actor_id)
    elif action == ReviewAction.MANUAL:
        return _handle_manual(db, ticket, review, actor_id)
    else:
        raise ReviewError(422, f"Unknown action: {action}")


def _load_ai_run(db: Session, ticket: Ticket, ai_run_id: int) -> AIAnalysisRun:
    """Load and validate an AI analysis run for review."""
    run = db.get(AIAnalysisRun, ai_run_id)
    if run is None or run.ticket_id != ticket.id:
        raise ReviewError(404, "AI analysis not found for this ticket")
    if run.status != AIAnalysisStatus.SUCCESS.value:
        raise ReviewError(409, "Only successful AI analysis can be reviewed")
    return run


def _resolve_team(db: Session, team_code: TeamCode) -> int:
    """Resolve a TeamCode to a Team.id, raising ReviewError if not found."""
    stmt = select(Team).where(Team.code == team_code.value)
    team = db.scalars(stmt).first()
    if team is None:
        raise ReviewError(422, f"Team '{team_code.value}' not found in database")
    return team.id


def _apply_field_change(
    ticket: Ticket,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
) -> bool:
    """Apply a field change to the ticket if the value actually changed."""
    if new_value is None:
        return False
    if old_value == new_value:
        return False
    setattr(ticket, field_name, new_value)
    return True


def _log_category_change(
    db: Session,
    ticket: Ticket,
    old_category: Optional[str],
    new_category: str,
    actor_id: int,
) -> None:
    """Create CATEGORY_CHANGED activity if category actually changed."""
    if old_category == new_category:
        return
    old_display = old_category if old_category else "unset"
    activity_service.create_activity(
        db=db,
        ticket_id=ticket.id,
        activity_type=ActivityType.CATEGORY_CHANGED,
        description=f"Category changed from {old_display} to {new_category}",
        actor_id=actor_id,
    )


def _log_priority_change(
    db: Session,
    ticket: Ticket,
    old_priority: Optional[str],
    new_priority: str,
    actor_id: int,
) -> None:
    """Create PRIORITY_CHANGED activity if priority actually changed."""
    if old_priority == new_priority:
        return
    old_display = old_priority if old_priority else "unset"
    activity_service.create_activity(
        db=db,
        ticket_id=ticket.id,
        activity_type=ActivityType.PRIORITY_CHANGED,
        description=f"Priority changed from {old_display} to {new_priority}",
        actor_id=actor_id,
    )


def _handle_accept(
    db: Session,
    ticket: Ticket,
    review: TicketReviewRequest,
    actor_id: int,
) -> Ticket:
    """Accept: copy all 6 fields from AI run to ticket."""
    if review.ai_run_id is None:
        raise ReviewError(422, "ai_run_id is required for ACCEPT action")

    # Check no human override fields were supplied
    override_fields = {"summary", "category", "priority", "priority_reason", "recommended_team", "initial_response"}
    supplied = override_fields & review.model_fields_set
    if supplied:
        raise ReviewError(422, f"Cannot supply override fields with ACCEPT action: {', '.join(sorted(supplied))}")

    run = _load_ai_run(db, ticket, review.ai_run_id)

    try:
        # Snapshot old values for activity comparison
        old_category = ticket.category
        old_priority = ticket.priority

        # Resolve recommended_team_code -> team ID
        recommended_team_id = _resolve_team(db, TeamCode(run.recommended_team_code))

        # Apply all 6 fields from AI run
        ticket.summary = run.summary
        ticket.category = run.category
        ticket.priority = run.priority
        ticket.priority_reason = run.priority_reason
        ticket.recommended_team_id = recommended_team_id
        ticket.initial_response = run.suggested_response

        # Primary activity
        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.AI_SUGGESTIONS_ACCEPTED,
            description=f"AI suggestions accepted from analysis run #{run.id}",
            actor_id=actor_id,
        )

        # Change activities
        _log_category_change(db, ticket, old_category, run.category, actor_id)
        _log_priority_change(db, ticket, old_priority, run.priority, actor_id)

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise


def _handle_edit(
    db: Session,
    ticket: Ticket,
    review: TicketReviewRequest,
    actor_id: int,
) -> Ticket:
    """Edit: start from AI run values, override with human-supplied values."""
    if review.ai_run_id is None:
        raise ReviewError(422, "ai_run_id is required for EDIT action")

    # At least one override field must be supplied
    override_fields = {"summary", "category", "priority", "priority_reason", "recommended_team", "initial_response"}
    supplied = override_fields & review.model_fields_set
    if not supplied:
        raise ReviewError(422, "At least one triage field must be provided for EDIT action")

    run = _load_ai_run(db, ticket, review.ai_run_id)

    try:
        old_category = ticket.category
        old_priority = ticket.priority

        # Start from AI run values
        new_summary = run.summary
        new_category = run.category
        new_priority = run.priority
        new_priority_reason = run.priority_reason
        new_recommended_team_code = run.recommended_team_code
        new_initial_response = run.suggested_response

        # Override with human-supplied values
        if "summary" in supplied:
            new_summary = review.summary
        if "category" in supplied:
            new_category = review.category.value
        if "priority" in supplied:
            new_priority = review.priority.value
        if "priority_reason" in supplied:
            new_priority_reason = review.priority_reason
        if "recommended_team" in supplied:
            new_recommended_team_code = review.recommended_team.value
        if "initial_response" in supplied:
            new_initial_response = review.initial_response

        # Resolve team
        recommended_team_id = _resolve_team(db, TeamCode(new_recommended_team_code))

        # Apply to ticket
        ticket.summary = new_summary
        ticket.category = new_category
        ticket.priority = new_priority
        ticket.priority_reason = new_priority_reason
        ticket.recommended_team_id = recommended_team_id
        ticket.initial_response = new_initial_response

        # Primary activity
        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.AI_SUGGESTIONS_EDITED,
            description=f"AI suggestions edited and applied from analysis run #{run.id}",
            actor_id=actor_id,
        )

        # Change activities
        _log_category_change(db, ticket, old_category, new_category, actor_id)
        _log_priority_change(db, ticket, old_priority, new_priority, actor_id)

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise


def _handle_reject(
    db: Session,
    ticket: Ticket,
    review: TicketReviewRequest,
    actor_id: int,
) -> Ticket:
    """Reject: do NOT modify ticket triage fields, just log activity."""
    if review.ai_run_id is None:
        raise ReviewError(422, "ai_run_id is required for REJECT action")

    # Check no triage fields were supplied
    override_fields = {"summary", "category", "priority", "priority_reason", "recommended_team", "initial_response"}
    supplied = override_fields & review.model_fields_set
    if supplied:
        raise ReviewError(422, f"Cannot supply triage fields with REJECT action: {', '.join(sorted(supplied))}")

    run = _load_ai_run(db, ticket, review.ai_run_id)

    try:
        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.AI_SUGGESTIONS_REJECTED,
            description=f"AI suggestions rejected from analysis run #{run.id}",
            actor_id=actor_id,
        )

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise


def _handle_manual(
    db: Session,
    ticket: Ticket,
    review: TicketReviewRequest,
    actor_id: int,
) -> Ticket:
    """Manual triage: apply human-supplied values directly without AI."""
    # ai_run_id must NOT be provided
    if review.ai_run_id is not None:
        raise ReviewError(422, "ai_run_id must not be provided for MANUAL action")

    # At least one triage field must be supplied
    override_fields = {"summary", "category", "priority", "priority_reason", "recommended_team", "initial_response"}
    supplied = override_fields & review.model_fields_set
    if not supplied:
        raise ReviewError(422, "At least one triage field must be provided for MANUAL action")

    try:
        old_category = ticket.category
        old_priority = ticket.priority

        # Apply only human-supplied fields; leave existing values for omitted fields
        if "summary" in supplied:
            ticket.summary = review.summary
        if "category" in supplied:
            ticket.category = review.category.value
        if "priority" in supplied:
            ticket.priority = review.priority.value
        if "priority_reason" in supplied:
            ticket.priority_reason = review.priority_reason
        if "recommended_team" in supplied:
            team_id = _resolve_team(db, review.recommended_team)
            ticket.recommended_team_id = team_id
        if "initial_response" in supplied:
            ticket.initial_response = review.initial_response

        # Primary activity
        activity_service.create_activity(
            db=db,
            ticket_id=ticket.id,
            activity_type=ActivityType.TRIAGE_UPDATED,
            description="Ticket triage updated manually",
            actor_id=actor_id,
        )

        # Change activities
        _log_category_change(db, ticket, old_category, ticket.category, actor_id)
        _log_priority_change(db, ticket, old_priority, ticket.priority, actor_id)

        db.commit()
        db.refresh(ticket)
        return ticket
    except Exception:
        db.rollback()
        raise
