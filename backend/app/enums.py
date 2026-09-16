from enum import Enum


class StrEnum(str, Enum):
    """String enumeration base class."""
    def __str__(self) -> str:
        return str(self.value)


class TicketStatus(StrEnum):
    OPEN = "Open"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    WAITING_FOR_CUSTOMER = "Waiting for Customer"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class TicketPriority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class TicketCategory(StrEnum):
    AUTHENTICATION = "Authentication"
    BILLING = "Billing"
    PERFORMANCE = "Performance"
    DATA_ISSUE = "Data Issue"
    INTEGRATION = "Integration"
    USER_INTERFACE = "User Interface"
    ACCESS_REQUEST = "Access Request"
    FEATURE_REQUEST = "Feature Request"
    SECURITY = "Security"
    GENERAL_SUPPORT = "General Support"
    UNKNOWN = "Unknown"


class AIAnalysisStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class UserRole(StrEnum):
    AGENT = "agent"
    MANAGER = "manager"
    ADMIN = "admin"


class ActivityType(StrEnum):
    TICKET_CREATED = "TICKET_CREATED"
    AI_ANALYSIS_COMPLETED = "AI_ANALYSIS_COMPLETED"
    AI_ANALYSIS_FAILED = "AI_ANALYSIS_FAILED"
    AI_SUGGESTIONS_ACCEPTED = "AI_SUGGESTIONS_ACCEPTED"
    AI_SUGGESTIONS_EDITED = "AI_SUGGESTIONS_EDITED"
    AI_SUGGESTIONS_REJECTED = "AI_SUGGESTIONS_REJECTED"
    CATEGORY_CHANGED = "CATEGORY_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    TEAM_ASSIGNED = "TEAM_ASSIGNED"
    USER_ASSIGNED = "USER_ASSIGNED"
    STATUS_CHANGED = "STATUS_CHANGED"
    COMMENT_ADDED = "COMMENT_ADDED"
    TICKET_RESOLVED = "TICKET_RESOLVED"
    TICKET_CLOSED = "TICKET_CLOSED"
    TRIAGE_UPDATED = "TRIAGE_UPDATED"


class ReviewAction(StrEnum):
    ACCEPT = "ACCEPT"
    EDIT = "EDIT"
    REJECT = "REJECT"
    MANUAL = "MANUAL"


class TeamCode(StrEnum):
    PLATFORM_ENGINEERING = "PLATFORM_ENGINEERING"
    APPLICATION_ENGINEERING = "APPLICATION_ENGINEERING"
    SECURITY = "SECURITY"
    DEVOPS = "DEVOPS"
    DATABASE = "DATABASE"
    BILLING = "BILLING"
    CUSTOMER_SUPPORT = "CUSTOMER_SUPPORT"
    PRODUCT = "PRODUCT"
