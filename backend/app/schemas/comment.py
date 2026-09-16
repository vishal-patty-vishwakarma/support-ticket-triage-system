from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator


class CommentCreate(BaseModel):
    body: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("body")
    @classmethod
    def validate_body(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Comment body cannot be blank or whitespace-only.")
        return v


class CommentResponse(BaseModel):
    id: int
    ticket_id: int
    body: str
    author_id: int
    author_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
