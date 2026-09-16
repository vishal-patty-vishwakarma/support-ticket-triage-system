class AIProviderError(Exception):
    """Raised when an AI provider fails to connect, times out, or returns a service error."""
    pass


class AIValidationError(Exception):
    """Raised when AI model output fails schema or domain validation."""
    pass
