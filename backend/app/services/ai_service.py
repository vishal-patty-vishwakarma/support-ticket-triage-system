import logging
from typing import Optional
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.enums import ActivityType, AIAnalysisStatus
from app.models.ai_analysis import AIAnalysisRun
from app.models.team import Team
from app.models.ticket import Ticket
from app.schemas.ai import AIAnalysisOutput
from app.services import activity_service
from app.services.ai.base import AIProvider
from app.services.ai.exceptions import AIProviderError, AIValidationError

logger = logging.getLogger(__name__)


def run_ai_analysis(
    db: Session,
    ticket_id: int,
    provider: AIProvider,
) -> AIAnalysisRun:
    """Execute 3-phase AI analysis run lifecycle on a ticket."""
    settings = get_settings()

    # Step 1: Verify ticket exists
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise ValueError("Ticket not found")

    # PHASE 1 — Record pending attempt in short transaction
    run = AIAnalysisRun(
        ticket_id=ticket.id,
        provider="ollama",
        model=settings.ollama_model,
        status=AIAnalysisStatus.PENDING.value,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_id = run.id
    raw_response: Optional[str] = None

    # PHASE 2 — Execute AIProvider outside database transaction
    try:
        raw_response = provider.analyze_ticket(
            subject=ticket.subject,
            description=ticket.description_original,
            product_module=ticket.product_module,
        )
    except AIProviderError as pe:
        _finalize_failed_run(
            db,
            run_id=run_id,
            error_message="AI analysis is currently unavailable. The ticket is saved and can be retried.",
            raw_response=None,
        )
        raise pe
    except Exception as exc:
        logger.error(f"Unexpected provider error: {exc}", exc_info=True)
        _finalize_failed_run(
            db,
            run_id=run_id,
            error_message="AI analysis is currently unavailable. The ticket is saved and can be retried.",
            raw_response=None,
        )
        raise AIProviderError("AI analysis service error") from exc

    # PHASE 3 — Validate and finalize
    try:
        # Schema validation
        output = AIAnalysisOutput.model_validate_json(raw_response)

        # Domain/database team code validation
        team_stmt = select(Team).where(Team.code == output.recommended_team.value)
        db_team = db.scalars(team_stmt).first()
        if db_team is None:
            raise AIValidationError(
                f"Recommended team '{output.recommended_team.value}' does not exist in the database."
            )

        # PHASE 3A — Finalize Success
        return _finalize_successful_run(
            db,
            run_id=run_id,
            output=output,
            raw_response=raw_response,
        )
    except (ValidationError, AIValidationError, ValueError) as val_err:
        logger.warning(f"AI output validation failed: {val_err}")
        _finalize_failed_run(
            db,
            run_id=run_id,
            error_message="AI returned an invalid response. The ticket is saved and can be retried.",
            raw_response=raw_response,
        )
        raise AIValidationError("AI output validation failed") from val_err


def _finalize_successful_run(
    db: Session,
    run_id: int,
    output: AIAnalysisOutput,
    raw_response: str,
) -> AIAnalysisRun:
    try:
        run = db.get(AIAnalysisRun, run_id)
        if run is None:
            raise RuntimeError(f"AIAnalysisRun {run_id} not found during finalization.")

        run.summary = output.summary
        run.category = output.category.value
        run.priority = output.priority.value
        run.priority_reason = output.priority_reason
        run.recommended_team_code = output.recommended_team.value
        run.suggested_response = output.suggested_response
        run.raw_response = raw_response
        run.status = AIAnalysisStatus.SUCCESS.value
        run.error_message = None

        activity_service.create_activity(
            db=db,
            ticket_id=run.ticket_id,
            activity_type=ActivityType.AI_ANALYSIS_COMPLETED,
            description="AI analysis completed",
            actor_id=None,
        )

        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        raise


def _finalize_failed_run(
    db: Session,
    run_id: int,
    error_message: str,
    raw_response: Optional[str] = None,
) -> None:
    try:
        run = db.get(AIAnalysisRun, run_id)
        if run:
            run.status = AIAnalysisStatus.FAILED.value
            run.error_message = error_message
            if raw_response:
                run.raw_response = raw_response

            activity_service.create_activity(
                db=db,
                ticket_id=run.ticket_id,
                activity_type=ActivityType.AI_ANALYSIS_FAILED,
                description="AI analysis failed",
                actor_id=None,
            )

            db.commit()
    except Exception as exc:
        logger.error(f"Failed to record AI failure status for run {run_id}: {exc}")
        db.rollback()


def get_latest_analysis(db: Session, ticket_id: int) -> Optional[AIAnalysisRun]:
    """Retrieve the most recent AIAnalysisRun attempt for a ticket."""
    stmt = (
        select(AIAnalysisRun)
        .where(AIAnalysisRun.ticket_id == ticket_id)
        .order_by(AIAnalysisRun.created_at.desc(), AIAnalysisRun.id.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()
