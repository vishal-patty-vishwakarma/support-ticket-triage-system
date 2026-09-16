import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_ai_provider, get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.activity import ActivityResponse
from app.schemas.ai import AIAnalysisRunResponse
from app.schemas.comment import CommentCreate, CommentResponse
from app.schemas.ticket import AssignmentUpdate, StatusUpdate, TicketCreate, TicketResponse
from app.services import activity_service, ai_service, comment_service, ticket_service
from app.services.ai.base import AIProvider
from app.services.ai.exceptions import AIProviderError, AIValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_new_ticket(
    ticket_in: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new customer ticket and log TICKET_CREATED activity in a single atomic transaction."""
    try:
        return ticket_service.create_ticket(db, ticket_in, current_user.id)
    except Exception as exc:
        logger.error(f"Failed to create ticket: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create ticket",
        )


@router.get("", response_model=List[TicketResponse])
def get_all_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all tickets ordered newest first."""
    return ticket_service.list_tickets(db)


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket_by_id(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single ticket by its ID."""
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


@router.get("/{ticket_id}/activities", response_model=List[ActivityResponse])
def get_ticket_activities(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve chronological audit timeline for a specific ticket."""
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    activities = activity_service.list_activities(db, ticket_id)
    return [
        ActivityResponse(
            id=act.id,
            ticket_id=act.ticket_id,
            type=act.type,
            description=act.description,
            actor_id=act.actor_id,
            actor_name=act.actor.name if act.actor else None,
            created_at=act.created_at,
        )
        for act in activities
    ]


@router.put("/{ticket_id}/assignment", response_model=TicketResponse)
def update_ticket_assignment(
    ticket_id: int,
    assignment_in: AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Perform partial assignment update for team and/or user with atomic audit logging."""
    try:
        ticket = ticket_service.update_assignment(
            db=db,
            ticket_id=ticket_id,
            fields_set=assignment_in.model_fields_set,
            team_id=assignment_in.team_id,
            user_id=assignment_in.user_id,
            actor_id=current_user.id,
        )
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )
        return ticket
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update assignment: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update assignment",
        )


@router.put("/{ticket_id}/status", response_model=TicketResponse)
def update_ticket_status(
    ticket_id: int,
    status_in: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update ticket status with atomic audit logging."""
    try:
        ticket = ticket_service.update_status(
            db=db,
            ticket_id=ticket_id,
            new_status=status_in.status.value,
            actor_id=current_user.id,
        )
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found",
            )
        return ticket
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update status: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update status",
        )


@router.post("/{ticket_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_comment(
    ticket_id: int,
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an internal comment with atomic audit logging."""
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    try:
        comment = comment_service.create_comment(
            db=db,
            ticket_id=ticket_id,
            body=comment_in.body,
            author_id=current_user.id,
        )
        return CommentResponse(
            id=comment.id,
            ticket_id=comment.ticket_id,
            body=comment.body,
            author_id=comment.author_id,
            author_name=current_user.name,
            created_at=comment.created_at,
        )
    except Exception as exc:
        logger.error(f"Failed to create comment: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create comment",
        )


@router.get("/{ticket_id}/comments", response_model=List[CommentResponse])
def get_ticket_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve internal comments for a ticket ordered chronologically."""
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    comments = comment_service.list_comments(db, ticket_id)
    return [
        CommentResponse(
            id=c.id,
            ticket_id=c.ticket_id,
            body=c.body,
            author_id=c.author_id,
            author_name=c.author.name if c.author else "Unknown Author",
            created_at=c.created_at,
        )
        for c in comments
    ]


@router.post(
    "/{ticket_id}/analyze",
    response_model=AIAnalysisRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def analyze_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    provider: AIProvider = Depends(get_ai_provider),
):
    """
    Trigger AI analysis for a ticket.

    Creates a new AIAnalysisRun attempt (pending -> success|failed).
    Retries are supported: each call creates a new run on the same ticket.
    AI suggestions are stored in the run and NEVER copied into authoritative Ticket fields.
    """
    # Verify ticket exists first
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    try:
        run = ai_service.run_ai_analysis(db=db, ticket_id=ticket_id, provider=provider)
    except AIProviderError:
        # Provider network / service failure — return 503
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis service is currently unavailable. The ticket is saved and analysis can be retried.",
        )
    except AIValidationError:
        # Model returned unparseable / invalid output — return 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI returned an invalid response. The ticket is saved and analysis can be retried.",
        )
    except Exception as exc:
        logger.error(f"Unexpected error during AI analysis: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )

    return _build_run_response(run)


@router.get(
    "/{ticket_id}/ai-analysis/latest",
    response_model=AIAnalysisRunResponse,
)
def get_latest_ai_analysis(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the most recent AI analysis run for a ticket (any status).

    Returns 404 if the ticket does not exist or if no analysis has ever been run.
    Never exposes raw_response.
    """
    ticket = ticket_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    run = ai_service.get_latest_analysis(db, ticket_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AI analysis found for this ticket",
        )

    return _build_run_response(run)


def _build_run_response(run) -> AIAnalysisRunResponse:
    """Build a public AIAnalysisRunResponse from an AIAnalysisRun ORM instance.
    raw_response is intentionally excluded from the returned schema.
    """
    return AIAnalysisRunResponse(
        id=run.id,
        ticket_id=run.ticket_id,
        provider=run.provider,
        model=run.model,
        summary=run.summary,
        category=run.category,
        priority=run.priority,
        priority_reason=run.priority_reason,
        recommended_team=run.recommended_team_code,
        suggested_response=run.suggested_response,
        status=run.status,
        error_message=run.error_message,
        created_at=run.created_at,
    )
