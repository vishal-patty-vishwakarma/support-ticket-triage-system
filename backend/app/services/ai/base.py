from abc import ABC, abstractmethod
from typing import Optional


class AIProvider(ABC):
    """Abstract base class for AI triage analysis providers."""

    @abstractmethod
    def analyze_ticket(
        self,
        subject: str,
        description: str,
        product_module: Optional[str] = None,
    ) -> str:
        """Analyze ticket details and return raw structured JSON output."""
        pass
