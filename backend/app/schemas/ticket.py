from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import ReviewAction, TicketCategory, TicketPriority, TicketStatus, TeamCode


class TicketCreate(BaseModel):
    customer_name: str
    customer_email: str
    subject: str
    description: str
    product_module: Optional[str] = None
    attachment_link: Optional[str] = None

    # Extra fields forbidden (returns 422 if client attempts sending server-controlled fields)
    model_config = ConfigDict(extra="forbid")

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Customer name cannot be blank or whitespace-only.")
        if len(v) > 100:
            raise ValueError("Customer name cannot exceed 100 characters.")
        return v

    @field_validator("customer_email")
    @classmethod
    def validate_customer_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Customer email cannot be blank.")
        if len(v) > 150:
            raise ValueError("Customer email cannot exceed 150 characters.")
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid customer email format.")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Subject cannot be blank or whitespace-only.")
        stripped = v.strip()
        if len(stripped) < 10:
            raise ValueError("Subject must be at least 10 characters.")
        if len(v) > 200:
            raise ValueError("Subject cannot exceed 200 characters.")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Description cannot be blank or whitespace-only.")
        stripped = v.strip()
        if len(stripped) < 30:
            raise ValueError("Description must be at least 30 characters.")
        # Returns the exact original string v byte-for-byte without stripping/modifying
        return v

    @field_validator("product_module")
    @classmethod
    def validate_product_module(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError("Product/module cannot be whitespace-only.")
        return v

    @field_validator("attachment_link")
    @classmethod
    def validate_attachment_link(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Attachment link cannot be whitespace-only.")
            if not (stripped.startswith("http://") or stripped.startswith("https://")):
                raise ValueError("Attachment link must be a valid HTTP or HTTPS URL.")
        return v


class AssignmentUpdate(BaseModel):
    team_id: Optional[int] = None
    user_id: Optional[int] = None

    model_config = ConfigDict(extra="forbid")


class StatusUpdate(BaseModel):
    status: TicketStatus

    model_config = ConfigDict(extra="forbid")


class TicketResponse(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    subject: str
    description_original: str
    product_module: Optional[str] = None
    attachment_link: Optional[str] = None

    summary: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    priority_reason: Optional[str] = None
    recommended_team_id: Optional[int] = None

    assigned_team_id: Optional[int] = None
    assigned_user_id: Optional[int] = None

    initial_response: Optional[str] = None
    status: str

    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketReviewRequest(BaseModel):
    action: ReviewAction
    ai_run_id: Optional[int] = None

    summary: Optional[str] = None
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    priority_reason: Optional[str] = None
    recommended_team: Optional[TeamCode] = None
    initial_response: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("summary", "priority_reason", "initial_response")
    @classmethod
    def validate_text_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not v or not v.strip()):
            raise ValueError("Value cannot be blank or whitespace-only.")
        return v
