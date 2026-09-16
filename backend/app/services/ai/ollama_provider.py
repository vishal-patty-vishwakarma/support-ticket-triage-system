import logging
from typing import Optional
import ollama

from app.config import get_settings
from app.schemas.ai import AIAnalysisOutput
from app.services.ai.base import AIProvider
from app.services.ai.exceptions import AIProviderError
from app.services.ai.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    """Ollama local LLM provider implementation using official Python client."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        self.simulate_failure = settings.ai_simulate_failure

    def analyze_ticket(
        self,
        subject: str,
        description: str,
        product_module: Optional[str] = None,
    ) -> str:
        """Call local Ollama service for ticket analysis."""
        # Simulated failure switch for dev/testing
        if self.simulate_failure:
            logger.warning("AI_SIMULATE_FAILURE is enabled. Raising simulated AIProviderError.")
            raise AIProviderError("AI analysis service failure simulated.")

        try:
            client = ollama.Client(host=self.base_url)
            user_prompt = build_user_prompt(subject, description, product_module)

            response = client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                format=AIAnalysisOutput.model_json_schema(),
                options={"temperature": 0},
            )
            return response.message.content
        except Exception as exc:
            logger.error(f"Ollama provider execution failed: {exc}", exc_info=True)
            raise AIProviderError("Failed to communicate with local Ollama service.") from exc
