from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required setting: Must be provided via environment variables (no default provided)
    jwt_secret: str

    # Safe local defaults for development
    database_url: str = "sqlite:///./ticket_triage.db"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    frontend_url: str = "http://localhost:5173"
    ai_simulate_failure: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("JWT_SECRET environment variable is required and cannot be empty.")
        return v


# Settings singleton instance loaded lazily or on import if env present
def get_settings() -> Settings:
    return Settings()
