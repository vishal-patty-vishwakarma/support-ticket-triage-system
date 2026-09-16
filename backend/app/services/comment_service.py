from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.enums import ActivityType
from app.models.comment import Comment
from app.services import activity_service


def create_comment(db: Session, ticket_id: int, body: str, author_id: int) -> Comment:
    """Create an internal comment and log COMMENT_ADDED activity in a single transaction."""
    try:
        comment = Comment(
            ticket_id=ticket_id,
            author_id=author_id,
            body=body,
        )
        db.add(comment)
        db.flush()

        activity_service.create_activity(
            db=db,
            ticket_id=ticket_id,
            activity_type=ActivityType.COMMENT_ADDED,
            description="Internal comment added",
            actor_id=author_id,
        )

        db.commit()
        db.refresh(comment)
        return comment
    except Exception:
        db.rollback()
        raise


def list_comments(db: Session, ticket_id: int) -> List[Comment]:
    """Retrieve all internal comments for a ticket chronologically, eager-loading author."""
    stmt = (
        select(Comment)
        .options(joinedload(Comment.author))
        .where(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    )
    return list(db.scalars(stmt).all())
